import html
import math
import re
from datetime import UTC, datetime
from urllib.parse import quote

import settings

WORDS_PER_MINUTE = 200

# Every width requested here must also be listed under images.sizes in
# vercel.json, or /_vercel/image answers 400.
SRCSET_WIDTHS = (480, 800, 1200, 1600)
IMAGE_QUALITY = 75

# Inline images sit in the article column: .prose is 68ch, about 680px.
INLINE_IMAGE_WIDTH = 800
INLINE_IMAGE_SIZES = '(max-width: 720px) 100vw, 680px'

IMG_TAG = re.compile(r'<img\b[^>]*>', re.IGNORECASE)
IMG_SRC = re.compile(
    r"""(?<![\w-])src\s*=\s*(["'])(.*?)\1""", re.IGNORECASE | re.DOTALL
)
IMG_WIDTH = re.compile(r"""(?<![\w-])width\s*=\s*["']?(\d+)""", re.IGNORECASE)

_TAG = re.compile(r'<[^>]*>')
_TAG_END = re.compile(r'\s*/?>$')

# What vercel.json's remotePatterns and localPatterns allow through.
_OPTIMIZABLE = re.compile(
    r'^(https://[a-z0-9]+\.public\.blob\.vercel-storage\.com/|/img/)'
)


def format_date(value: datetime) -> str:
    """
    'October 12, 2024'. The stored timestamps are wall-clock times recorded as
    UTC, so formatting in UTC keeps the date identical to what was written.
    """
    value = value.astimezone(UTC)
    return f'{value:%B} {value.day}, {value.year}'


def minutes_to_read(words: int) -> int:
    """Divided by 200 and rounded half up the way Math.round did, never below 1."""
    return max(1, math.floor(words / WORDS_PER_MINUTE + 0.5))


def reading_time(html: str) -> int:
    """Minutes to read a legacy HTML body, with its tags stripped."""
    return minutes_to_read(len(_TAG.sub(' ', html).split()))


def _optimizable(url: str | None) -> bool:
    """
    /_vercel/image only exists on Vercel, and refuses hosts vercel.json doesn't
    allow, so anything else has to be served from where it already is.
    """
    return bool(settings.ON_VERCEL and url and _OPTIMIZABLE.match(url))


def img_url(url: str | None, width: int) -> str | None:
    """A resized, modern-format copy on Vercel; the URL itself anywhere else."""
    if not _optimizable(url):
        return url

    return f'/_vercel/image?url={uri_component(url)}&w={width}&q={IMAGE_QUALITY}'


def img_srcset(url: str | None, intrinsic_width: int | None = None) -> str:
    """
    The srcset for an image, empty when it can't be resized. It stops at the
    first width that reaches the original: the optimizer never scales up, so
    that one serves the full image and anything larger would be the same file.
    """
    if not _optimizable(url):
        return ''

    widths = []
    for width in SRCSET_WIDTHS:
        widths.append(width)
        if intrinsic_width and width >= intrinsic_width:
            break

    return ', '.join(f'{img_url(url, width)} {width}w' for width in widths)


def _responsive_img(match: re.Match) -> str:
    tag = match.group(0)
    extra = ''.join(
        f' {attr}="{value}"'
        for attr, value in (('loading', 'lazy'), ('decoding', 'async'))
        if f'{attr}=' not in tag.lower()
    )
    tag = _TAG_END.sub(f'{extra}>', tag)

    src = IMG_SRC.search(tag)
    if not src or 'srcset=' in tag.lower():
        return tag

    url = html.unescape(src.group(2))
    width = IMG_WIDTH.search(tag)
    srcset = img_srcset(url, int(width.group(1)) if width else None)
    if not srcset:
        return tag

    attrs = (
        f'src="{html.escape(img_url(url, INLINE_IMAGE_WIDTH))}" '
        f'srcset="{html.escape(srcset)}" sizes="{INLINE_IMAGE_SIZES}"'
    )
    return f'{tag[: src.start()]}{attrs}{tag[src.end() :]}'


def responsive_images(body: str) -> str:
    """
    Gives every <img> in an authored HTML body the treatment the image macro
    gives covers: resized sources on Vercel, lazy loading everywhere.
    """
    return IMG_TAG.sub(_responsive_img, body)


def uri_component(value: str) -> str:
    """
    JavaScript's encodeURIComponent, which the share links were built with.
    Jinja's own urlencode leaves '/' alone.
    """
    return quote(value, safe="!~*'()")


def register(app):
    app.add_template_filter(format_date, 'date')
    app.add_template_filter(minutes_to_read)
    app.add_template_filter(reading_time)
    app.add_template_filter(img_url)
    app.add_template_filter(img_srcset)
    app.add_template_filter(responsive_images)
    app.add_template_filter(uri_component)
