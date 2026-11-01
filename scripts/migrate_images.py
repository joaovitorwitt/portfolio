"""
Moves the images backed up by scripts/export_images.py to Vercel Blob and points
the `content` table at them. Needs BLOB_READ_WRITE_TOKEN and migration 003.

Safe to run more than once: files already in Blob are skipped (the content hash
in the name means they are identical), and rows already rewritten are left alone.

    python scripts/migrate_images.py --dry-run    # print the changes, no writes
    python scripts/migrate_images.py --apply      # upload, back up table, rewrite
"""

import argparse
import json
import mimetypes
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from vercel.blob.errors import BlobNotFoundError  # noqa: E402
from vercel.blob.sync import head_blob, put_blob  # noqa: E402

import settings  # noqa: E402, F401  (loads .env, where the Blob SDK finds its token)
from scripts.export_images import BACKUP_DIR, MANIFEST  # noqa: E402
from website.db import ContentImages, get_pool  # noqa: E402
from website.filters import IMG_SRC, IMG_TAG, IMG_WIDTH  # noqa: E402

TOKEN_PREFIX = 'vercel_blob_rw_'

# Content hashes make the URLs immutable, so they can be cached for a long time.
CACHE_MAX_AGE = 31536000


def store_base_url(token: str) -> str:
    """The store's public origin, which is part of its token. Never the secret."""
    if not token.startswith(TOKEN_PREFIX):
        raise ValueError('BLOB_READ_WRITE_TOKEN is not a read-write token')

    store_id = token.removeprefix(TOKEN_PREFIX).split('_', 1)[0].lower()
    return f'https://{store_id}.public.blob.vercel-storage.com'


def pathname(entry: dict) -> str:
    """images/<kind>/<slug>/<sha256-12>.<ext>"""
    return f'images/{entry["local_file"]}'


def rewrite_body(body: str, manifest: dict, base_url: str) -> str:
    """Points each known <img> at Blob and adds its size, keeping the rest as is."""

    def rewrite_tag(match) -> str:
        tag = match.group(0)
        src = IMG_SRC.search(tag)
        entry = manifest.get(src.group(2)) if src else None
        if entry is None:
            return tag

        quote = src.group(1)
        new_src = f'src={quote}{base_url}/{pathname(entry)}{quote}'
        if not IMG_WIDTH.search(tag):
            new_src += f' width="{entry["width"]}" height="{entry["height"]}"'

        return f'{tag[: src.start()]}{new_src}{tag[src.end() :]}'

    return IMG_TAG.sub(rewrite_tag, body)


def plan_updates(rows: list[dict], manifest: dict, base_url: str) -> list[dict]:
    """Only the rows that change, each with every column apply() writes."""
    updates = []
    for row in rows:
        content = rewrite_body(row['content'], manifest, base_url)
        cover = manifest.get(row['image_url'])
        if cover is None and content == row['content']:
            continue

        updates.append(
            {
                'id': row['id'],
                'slug': row['slug'],
                'old_image_url': row['image_url'],
                'image_url': (
                    f'{base_url}/{pathname(cover)}' if cover else row['image_url']
                ),
                'image_width': cover['width'] if cover else row['image_width'],
                'image_height': cover['height'] if cover else row['image_height'],
                'old_content': row['content'],
                'content': content,
            }
        )

    return updates


def unmapped_rows(rows: list[dict], updates: list[dict]) -> list[str]:
    """Slugs that would still mention Cloudinary after the updates."""
    planned = {update['id']: update for update in updates}
    left = []
    for row in rows:
        final = planned.get(row['id'], row)
        if 'cloudinary' in f'{final["image_url"]} {final["content"]}':
            left.append(row['slug'])

    return left


def print_plan(updates: list[dict]) -> None:
    for update in updates:
        print(f'\n{update["slug"]}')
        if update['image_url'] != update['old_image_url']:
            print(f'  - {update["old_image_url"]}')
            print(f'  + {update["image_url"]}')

        old_tags = IMG_TAG.findall(update['old_content'])
        new_tags = IMG_TAG.findall(update['content'])
        for old, new in zip(old_tags, new_tags, strict=True):
            if old != new:
                print(f'  - {old}')
                print(f'  + {new}')


def upload(manifest: dict, apply: bool) -> None:
    uploaded = skipped = 0
    for entry in {pathname(entry): entry for entry in manifest.values()}.values():
        try:
            head_blob(pathname(entry))
            skipped += 1
            continue
        except BlobNotFoundError:
            pass

        if apply:
            put_blob(
                pathname(entry),
                (BACKUP_DIR / entry['local_file']).read_bytes(),
                access='public',
                content_type=mimetypes.guess_type(entry['local_file'])[0],
                cache_control_max_age=CACHE_MAX_AGE,
            )

        uploaded += 1

    verb = 'uploaded' if apply else 'would upload'
    print(f'{verb} {uploaded} files, {skipped} already in Blob')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--dry-run', action='store_true', help='print changes only')
    mode.add_argument('--apply', action='store_true', help='upload and rewrite')
    args = parser.parse_args()

    token = os.environ.get('BLOB_READ_WRITE_TOKEN')
    if not token:
        print('aborting: BLOB_READ_WRITE_TOKEN is not set')
        return 1

    if not MANIFEST.exists():
        print('aborting: no manifest, run scripts/export_images.py first')
        return 1

    manifest = json.loads(MANIFEST.read_text())
    repository = ContentImages()
    rows = repository.rows()
    updates = plan_updates(rows, manifest, store_base_url(token))

    left = unmapped_rows(rows, updates)
    if left:
        print(f'aborting: URLs missing from the manifest in {left}')
        return 1

    print_plan(updates)
    print(f'\n{len(updates)} of {len(rows)} rows change')
    upload(manifest, apply=args.apply)

    if args.dry_run:
        print('dry run, nothing written')
        return 0

    if updates:
        backup_table = f'content_backup_{datetime.now(UTC):%Y%m%d}'
        repository.apply(updates, backup_table)
        print(f'rewrote {len(updates)} rows, previous data in {backup_table}')

    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    finally:
        get_pool().close()
