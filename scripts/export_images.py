"""
Backs up every Cloudinary image the site uses into backups/images/, along with
a manifest.json that scripts/migrate_images.py works from. Only reads: from the
database and from Cloudinary.

Safe to run more than once: entries for URLs that are gone from the database
stay in the manifest, so running it after the migration loses nothing.

    python scripts/export_images.py
"""

import hashlib
import io
import json
import re
import sys
from pathlib import Path
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image  # noqa: E402

from website.db import ContentImages, get_pool  # noqa: E402
from website.filters import IMG_SRC, IMG_TAG  # noqa: E402

BACKUP_DIR = Path(__file__).resolve().parent.parent / 'backups' / 'images'
MANIFEST = BACKUP_DIR / 'manifest.json'

CLOUDINARY = 'https://res.cloudinary.com/'
EXTENSIONS = {'JPEG': 'jpg', 'PNG': 'png'}

# Cloudinary paths read /image/upload/[transformations/][v123/]public_id. The
# version is what tells a transformation apart from a folder in the public id.
_UPLOAD_PATH = re.compile(r'^(.*?/image/upload/)(?:.*?/)?(v\d+/.*)$')

# EXIF orientations that rotate by 90 degrees, swapping width and height.
_SIDEWAYS = {5, 6, 7, 8}
_EXIF_ORIENTATION = 0x0112


def original_url(url: str) -> str:
    """The same image with any transformation removed."""
    return _UPLOAD_PATH.sub(r'\1\2', url)


def inline_urls(body: str) -> list[str]:
    sources = (IMG_SRC.search(tag) for tag in IMG_TAG.findall(body or ''))
    return [src.group(2) for src in sources if src]


def collect_references(rows: list[dict]) -> dict[str, dict]:
    """
    Maps each distinct Cloudinary URL to the first row using it, whose kind and
    slug name the file. Several projects share one cover, so a URL can appear
    more than once.
    """
    references = {}
    for row in rows:
        for url in [row['image_url'], *inline_urls(row['content'])]:
            if url and url.startswith(CLOUDINARY):
                references.setdefault(url, {'kind': row['kind'], 'slug': row['slug']})

    return references


def describe(data: bytes) -> tuple[str, int, int]:
    """Extension and displayed size. Fails on anything that isn't a real image."""
    with Image.open(io.BytesIO(data)) as image:
        image.load()
        width, height = image.size
        if image.getexif().get(_EXIF_ORIENTATION) in _SIDEWAYS:
            width, height = height, width

        return EXTENSIONS[image.format], width, height


def download(url: str) -> bytes:
    request = Request(original_url(url), headers={'User-Agent': 'portfolio-backup'})
    with urlopen(request, timeout=60) as response:
        return response.read()


def main() -> int:
    references = collect_references(ContentImages().references())
    manifest = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {}

    total = 0
    for url, owner in references.items():
        data = download(url)
        extension, width, height = describe(data)
        sha256 = hashlib.sha256(data).hexdigest()

        local_file = f'{owner["kind"]}/{owner["slug"]}/{sha256[:12]}.{extension}'
        path = BACKUP_DIR / local_file
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

        manifest[url] = {
            'local_file': local_file,
            'sha256': sha256,
            'width': width,
            'height': height,
        }
        total += len(data)
        print(f'  {local_file}  {width}x{height}')

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(manifest, indent=2))

    print(f'\n{len(references)} images, {total / 1024 / 1024:.1f} MiB in {BACKUP_DIR}')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    finally:
        get_pool().close()
