import math
import re
from datetime import UTC, datetime
from urllib.parse import quote

WORDS_PER_MINUTE = 200

_TAG = re.compile(r'<[^>]*>')

# Cloudinary delivery URLs take transformations as a path segment right after
# /image/upload/, e.g. .../image/upload/f_auto,q_auto,w_800/v123/name.png
_CLOUDINARY_UPLOAD = re.compile(r'^(https://res\.cloudinary\.com/[^/]+/image/upload/)')


def format_date(value: datetime) -> str:
    """
    'October 12, 2024'. The stored timestamps are wall-clock times recorded as
    UTC, so formatting in UTC keeps the date identical to what was written.
    """
    value = value.astimezone(UTC)
    return f'{value:%B} {value.day}, {value.year}'


def reading_time(html: str) -> int:
    """
    Minutes to read an HTML body: tags stripped, words counted, divided by 200
    and rounded half up the way Math.round did, never below 1.
    """
    words = len(_TAG.sub(' ', html).split())
    return max(1, math.floor(words / WORDS_PER_MINUTE + 0.5))


def cloudinary(url: str | None, width: int) -> str | None:
    """
    Asks Cloudinary for a resized, modern-format copy, which is what next/image
    used to do on the fly. c_limit only ever scales down. URLs from anywhere
    else pass through untouched.
    """
    if not url:
        return url

    return _CLOUDINARY_UPLOAD.sub(rf'\1f_auto,q_auto,c_limit,w_{width}/', url, count=1)


def uri_component(value: str) -> str:
    """
    JavaScript's encodeURIComponent, which the share links were built with.
    Jinja's own urlencode leaves '/' alone.
    """
    return quote(value, safe="!~*'()")


def register(app):
    app.add_template_filter(format_date, 'date')
    app.add_template_filter(reading_time)
    app.add_template_filter(cloudinary)
    app.add_template_filter(uri_component)
