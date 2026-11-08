"""
Turns an uploaded artigo.md and its images into what an article row stores.

Articles are written in the joaovitorwitt/articles repository, one folder each,
with front matter (titulo, descricao, tags, data, status) and images in
imagens/. Each image the Markdown references by a relative path is uploaded to
Vercel Blob and the reference is pointed at it, with its size, so the page can
reserve the space and build a srcset.

The Blob path keeps the file's name: images/article/<slug>/<name>-<sha>.<ext>.
That's how a later edit, given a new artigo.md that still says imagens/x.png,
finds the x.png uploaded before without needing it again.
"""

import hashlib
import io
import posixpath
import re
import unicodedata
from datetime import UTC, date, datetime, time
from typing import NamedTuple
from urllib.parse import unquote

from PIL import Image, UnidentifiedImageError

from website.markdown import MATH_ERROR_CLASS, render

FRONT_MATTER = re.compile(r'\A---[ \t]*\n(.*?)\n---[ \t]*(?:\n|\Z)', re.S)
_FIELD = re.compile(r'^([A-Za-z_]\w*)\s*:\s*(.*)$')

SLUG = re.compile(r'^[a-z0-9]+(?:-[a-z0-9]+)*$')

# The status an article has in the articles repository once its review is done.
READY_STATUS = 'pronto'

# Search engines cut meta descriptions at about this length.
DESCRIPTION_LIMIT = 160

# Detected from the file's first bytes by Pillow, never from its extension.
IMAGE_TYPES = {
    'PNG': 'image/png',
    'JPEG': 'image/jpeg',
    'WEBP': 'image/webp',
    'GIF': 'image/gif',
}

# ![alt](path "title"){attrs}. A path with spaces has to be written as <path>
# (or with %20), as in CommonMark.
IMAGE_REF = re.compile(
    r'(?P<open>!\[[^\]]*\]\()\s*(?:<(?P<angled>[^>\n]+)>|(?P<bare>[^)\s]+))'
    r'(?P<close>(?:\s+"[^"]*")?\s*\))(?P<attrs>\{[^}\n]*\})?'
)

# A Blob URL this module made, and the size written after it.
_STORED_IMAGE = re.compile(
    r'/images/article/[^/]+/(?P<stem>[a-z0-9-]+)-[0-9a-f]{12}\.(?P<ext>[a-z0-9]+)$'
)
_SIZE_ATTRS = re.compile(r'^\{width=(\d+) height=(\d+)\}$')

# Content hashes make each URL immutable, so browsers can keep it for a year.
BLOB_CACHE_MAX_AGE = 31536000


class Upload(NamedTuple):
    filename: str
    data: bytes


class StoredImage(NamedTuple):
    url: str
    width: int
    height: int


class ImageError(ValueError):
    pass


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in '"\'':
        return value[1:-1]

    return value


def normalise_newlines(text: str) -> str:
    return text.replace('\r\n', '\n').replace('\r', '\n')


def front_matter(markdown: str) -> dict[str, str]:
    """
    The front matter's fields as raw strings, the way the articles repository's
    checagens.py reads them: one `key: value` per line, nothing nested.
    """
    match = FRONT_MATTER.match(markdown)
    if match is None:
        return {}

    fields = {}
    for line in match.group(1).split('\n'):
        field = _FIELD.match(line)
        if field:
            fields[field.group(1)] = field.group(2).strip()

    return fields


def field_text(fields: dict[str, str], name: str) -> str:
    return _unquote(fields.get(name, ''))


def parse_tags(value: str) -> list[str]:
    """
    `[a, "B"]` from front matter or `a, B` from the form, as lowercase tags with
    no repeats: "Physics" and "physics" would otherwise be two chips.
    """
    value = value.strip()
    if value.startswith('[') and value.endswith(']'):
        value = value[1:-1]

    tags = []
    for part in value.split(','):
        tag = ' '.join(_unquote(part).split()).lower()
        if tag and tag not in tags:
            tags.append(tag)

    return tags


def parse_date(value: str) -> date | None:
    try:
        return date.fromisoformat(_unquote(value))
    except ValueError:
        return None


def publish_datetime(day: date) -> datetime:
    """Midday UTC, so the date reads the same in Brazil and in Europe."""
    return datetime.combine(day, time(12), UTC)


def slugify(text: str) -> str:
    """'Introdução à Física' -> 'introducao-a-fisica'"""
    ascii_text = (
        unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('ascii')
    )
    return re.sub(r'[^a-z0-9]+', '-', ascii_text.lower()).strip('-')


def image_key(filename: str) -> str:
    """How a file is matched to a reference: 'Figura 1.PNG' -> 'figura-1.png'."""
    stem, _, ext = posixpath.basename(unquote(filename)).rpartition('.')
    return f'{slugify(stem) or "image"}.{ext.lower()}'


def inspect_image(upload: Upload) -> tuple[str, int, int]:
    """(content type, width, height), or ImageError if it isn't a known image."""
    try:
        with Image.open(io.BytesIO(upload.data)) as image:
            kind = image.format
            width, height = image.size
            image.verify()
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError) as error:
        raise ImageError(f'{upload.filename} is not a readable image') from error

    if kind not in IMAGE_TYPES:
        raise ImageError(
            f'{upload.filename} is {kind}; use PNG, JPEG, WebP or GIF instead'
        )

    return IMAGE_TYPES[kind], width, height


def blob_pathname(slug: str, upload: Upload) -> str:
    stem, _, ext = image_key(upload.filename).rpartition('.')
    digest = hashlib.sha256(upload.data).hexdigest()[:12]
    return f'images/article/{slug}/{stem}-{digest}.{ext}'


def upload_to_blob(pathname: str, data: bytes, content_type: str) -> str:
    """
    Stores a file in Vercel Blob and returns its public URL. The SDK reads
    BLOB_READ_WRITE_TOKEN itself, and is imported here so public pages never
    load it.
    """
    from vercel.blob.sync import put_blob

    # The name holds the content hash, so overwriting can only write the same bytes.
    result = put_blob(
        pathname,
        data,
        access='public',
        content_type=content_type,
        allow_overwrite=True,
        cache_control_max_age=BLOB_CACHE_MAX_AGE,
    )
    return result.url


def store_image(upload: Upload, slug: str, uploader=upload_to_blob) -> StoredImage:
    content_type, width, height = inspect_image(upload)
    url = uploader(blob_pathname(slug, upload), upload.data, content_type)
    return StoredImage(url, width, height)


def _ref_path(match: re.Match) -> str:
    return match['angled'] or match['bare']


def _is_relative(path: str) -> bool:
    return not (re.match(r'^[a-z][a-z0-9+.-]*:', path, re.I) or path.startswith('/'))


def referenced_images(markdown: str) -> list[str]:
    """Every relative image path the Markdown uses, in order, without repeats."""
    paths = []
    for match in IMAGE_REF.finditer(markdown):
        path = _ref_path(match)
        if _is_relative(path) and path not in paths:
            paths.append(path)

    return paths


def stored_images(markdown: str) -> dict[str, StoredImage]:
    """
    The images an earlier save already uploaded, by key, read back from their
    URLs and the size written after each one.
    """
    found = {}
    for match in IMAGE_REF.finditer(markdown):
        url = _ref_path(match)
        stored = _STORED_IMAGE.search(url)
        size = _SIZE_ATTRS.match(match['attrs'] or '')
        if stored and size:
            key = f'{stored["stem"]}.{stored["ext"]}'
            found[key] = StoredImage(url, int(size.group(1)), int(size.group(2)))

    return found


def link_images(markdown: str, images: dict[str, StoredImage]) -> tuple[str, list[str]]:
    """
    Points each relative reference with a matching image at its URL and adds
    the size, unless the author wrote attributes of their own. Returns the new
    Markdown and the paths left without an image.
    """
    missing = []

    def replace(match: re.Match) -> str:
        path = _ref_path(match)
        if not _is_relative(path):
            return match.group(0)

        image = images.get(image_key(path))
        if image is None:
            if path not in missing:
                missing.append(path)
            return match.group(0)

        size = match['attrs'] or f'{{width={image.width} height={image.height}}}'
        return f'{match["open"]}{image.url}{match["close"]}{size}'

    return IMAGE_REF.sub(replace, markdown), missing


def rendered_fields(body_md: str) -> dict:
    """The whole render, the same set scripts/render_all.py stores."""
    result = render(body_md)
    return {
        'body_md': body_md,
        'body_html': result.html,
        'has_math': result.has_math,
        'toc': result.toc,
        'word_count': result.word_count,
        'body_text': result.text,
    }


def has_math_errors(body_html: str) -> bool:
    return MATH_ERROR_CLASS in body_html


def body_without_front_matter(markdown: str) -> str:
    return FRONT_MATTER.sub('', markdown, count=1)
