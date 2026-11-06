import json
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest
from conftest import BLOB_URL

import settings
from website.filters import (
    IMAGE_QUALITY,
    INLINE_IMAGE_WIDTH,
    SRCSET_WIDTHS,
    format_date,
    img_srcset,
    img_url,
    reading_time,
    responsive_images,
    uri_component,
)


def test_format_date_has_no_leading_zero():
    assert format_date(datetime(2024, 10, 2, tzinfo=UTC)) == 'October 2, 2024'


def test_format_date_converts_to_utc():
    # 23:00 at UTC-3 is already the next day in UTC.
    value = datetime(2024, 10, 2, 23, tzinfo=timezone(timedelta(hours=-3)))
    assert format_date(value) == 'October 3, 2024'


@pytest.mark.parametrize(
    ('words', 'minutes'),
    [(0, 1), (10, 1), (299, 1), (300, 2), (500, 3), (1000, 5)],
)
def test_reading_time_rounds_half_up_and_is_at_least_one(words, minutes):
    assert reading_time(' '.join(['word'] * words)) == minutes


def test_reading_time_ignores_tags():
    assert reading_time('<p class="a b c d">' + 'word ' * 300 + '</p>') == 2


def test_reading_time_does_not_join_words_across_tags():
    assert reading_time('<p>' + 'word</p><p>' * 300) == 2


BLOB_IMAGE = f'{BLOB_URL}/images/article/slug/abc.png'
RESIZED = '/_vercel/image?url=https%3A%2F%2Fstore1.public.blob.vercel-storage.com%2Fimages%2Farticle%2Fslug%2Fabc.png'


@pytest.fixture
def on_vercel(monkeypatch):
    monkeypatch.setattr(settings, 'ON_VERCEL', True)


@pytest.mark.usefixtures('on_vercel')
def test_img_url_goes_through_the_optimizer_on_vercel():
    assert img_url(BLOB_IMAGE, 800) == f'{RESIZED}&w=800&q=75'


@pytest.mark.usefixtures('on_vercel')
def test_img_url_includes_local_images_on_vercel():
    assert (
        img_url('/img/me.jpg', 480) == '/_vercel/image?url=%2Fimg%2Fme.jpg&w=480&q=75'
    )


def test_img_url_is_unchanged_off_vercel():
    assert img_url(BLOB_IMAGE, 800) == BLOB_IMAGE
    assert img_srcset(BLOB_IMAGE) == ''


@pytest.mark.usefixtures('on_vercel')
@pytest.mark.parametrize(
    'url', [None, '', 'https://res.cloudinary.com/demo/image/upload/v1/name.png']
)
def test_hosts_vercel_json_does_not_allow_are_left_alone(url):
    assert img_url(url, 800) == url
    assert img_srcset(url) == ''


@pytest.mark.usefixtures('on_vercel')
def test_srcset_lists_every_width():
    assert img_srcset(BLOB_IMAGE) == ', '.join(
        f'{RESIZED}&w={width}&q=75 {width}w' for width in (480, 800, 1200, 1600)
    )


@pytest.mark.usefixtures('on_vercel')
@pytest.mark.parametrize(
    ('intrinsic', 'largest', 'candidates'),
    [(100, 480, 1), (640, 800, 2), (800, 800, 2), (900, 1200, 3), (5000, 1600, 4)],
)
def test_srcset_stops_at_the_first_width_reaching_the_original(
    intrinsic, largest, candidates
):
    srcset = img_srcset(BLOB_IMAGE, intrinsic)

    assert srcset.endswith(f'&w={largest}&q=75 {largest}w')
    assert srcset.count(', ') == candidates - 1


def test_every_requested_width_is_allowed_by_vercel_json():
    images = json.loads(Path('vercel.json').read_text())['images']

    assert {*SRCSET_WIDTHS, INLINE_IMAGE_WIDTH} <= set(images['sizes'])
    assert IMAGE_QUALITY in images['qualities']


@pytest.mark.usefixtures('on_vercel')
def test_responsive_images_rewrites_inline_tags():
    body = f'<p>a</p><img src=\'{BLOB_IMAGE}\' width="1000" height="500" alt=\'Axis\'/><p>b</p>'

    result = responsive_images(body)

    assert f'src="{RESIZED}&amp;w=800&amp;q=75"' in result
    assert 'srcset="' in result
    assert 'sizes="(max-width: 720px) 100vw, 680px"' in result
    assert "alt='Axis'" in result
    assert 'loading="lazy" decoding="async">' in result
    assert result.startswith('<p>a</p><img') and result.endswith('><p>b</p>')


def test_responsive_images_only_adds_lazy_loading_off_vercel():
    result = responsive_images(f"<img src='{BLOB_IMAGE}' alt='Axis'>")

    assert (
        result
        == f'<img src=\'{BLOB_IMAGE}\' alt=\'Axis\' loading="lazy" decoding="async">'
    )


@pytest.mark.usefixtures('on_vercel')
def test_responsive_images_keeps_an_existing_srcset_and_ignores_data_src():
    tag = f'<img data-src="{BLOB_IMAGE}" srcset="a 1w" loading="lazy" decoding="async">'

    assert responsive_images(tag) == tag


def test_uri_component_matches_encode_uri_component():
    assert uri_component("a/b c&d!~*'()") == "a%2Fb%20c%26d!~*'()"
