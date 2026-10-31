"""
One-off import of articles.json into the `content` table.

Safe to run more than once: rows are matched on (kind, slug) and updated in
place, so a second run refreshes content instead of duplicating it.

    python scripts/import_articles.py --dry-run     # parse and report, no writes
    python scripts/import_articles.py               # write to DATABASE_URL
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import psycopg  # noqa: E402

from website.db import build_conninfo  # noqa: E402

SOURCE_FORMAT = '%Y%m%d T%H:%M:%S'

UPSERT = """
INSERT INTO content (kind, title, slug, description, content, image_url, repo_url,
                     tags, created_at)
VALUES (%(kind)s, %(title)s, %(slug)s, %(description)s, %(content)s,
        %(image_url)s, %(repo_url)s, %(tags)s, %(created_at)s)
ON CONFLICT (kind, slug) DO UPDATE SET
    title       = EXCLUDED.title,
    description = EXCLUDED.description,
    content     = EXCLUDED.content,
    image_url   = EXCLUDED.image_url,
    repo_url    = EXCLUDED.repo_url,
    tags        = EXCLUDED.tags,
    created_at  = EXCLUDED.created_at
RETURNING id, (xmax = 0) AS inserted
"""


def parse_tags(raw) -> list[str]:
    """
    Tags arrive as a single string ('physics') or a comma separated one. The
    column is text[], so normalise everything to a list.
    """
    if isinstance(raw, list):
        values = raw
    else:
        values = str(raw or '').split(',')

    return [tag.strip() for tag in values if tag and tag.strip()]


def to_row(record: dict, kind: str) -> dict:
    """
    Maps one articles.json record onto the content schema. The legacy `id` and
    `UUID` fields are dropped: the table owns identity now, and `slug` is the
    public key. `date` is dropped too, being a display format derived from
    created_at.
    """
    missing = [
        field for field in ('Title', 'url_title', 'created_at') if not record.get(field)
    ]
    if missing:
        raise ValueError(f'record {record.get("id")!r} missing {missing}')

    # In the project export `Content` holds a repository link rather than a
    # body, so it is routed to repo_url and `content` is left empty for a
    # write-up later. Articles keep their HTML in `content`.
    body = record.get('Content') or ''
    is_link = body.startswith(('http://', 'https://'))

    return {
        'kind': kind,
        'title': record['Title'],
        'slug': record['url_title'],
        'description': record.get('Description') or '',
        'content': '' if is_link else body,
        'image_url': record.get('image_url') or None,
        'repo_url': body if is_link else None,
        'tags': parse_tags(record.get('tags')),
        'created_at': datetime.strptime(record['created_at'], SOURCE_FORMAT),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', default='fixtures/articles.json', type=Path)
    parser.add_argument('--kind', default='article')
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='parse and validate without touching the database',
    )
    args = parser.parse_args()

    records = json.loads(args.source.read_text())
    rows = [to_row(record, args.kind) for record in records]

    slugs = [row['slug'] for row in rows]
    duplicates = {slug for slug in slugs if slugs.count(slug) > 1}
    if duplicates:
        print(f'aborting: duplicate slugs in source: {sorted(duplicates)}')
        return 1

    print(f'parsed {len(rows)} rows from {args.source}')
    for row in sorted(rows, key=lambda r: r['created_at'], reverse=True):
        print(f'  {row["created_at"]:%Y-%m-%d}  {row["slug"][:52]:52} {row["tags"]}')

    if args.dry_run:
        print('\ndry run, nothing written')
        return 0

    inserted = updated = 0
    with psycopg.connect(build_conninfo()) as conn:
        with conn.cursor() as cur:
            for row in rows:
                cur.execute(UPSERT, row)
                if cur.fetchone()[1]:
                    inserted += 1
                else:
                    updated += 1
        conn.commit()

    print(f'\ninserted {inserted}, updated {updated}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
