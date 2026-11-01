from datetime import UTC, datetime, timedelta, timezone

import pytest

from website.filters import cloudinary, format_date, reading_time, uri_component


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


def test_cloudinary_inserts_the_transformation():
    url = 'https://res.cloudinary.com/demo/image/upload/v1/name.png'
    assert cloudinary(url, 800) == (
        'https://res.cloudinary.com/demo/image/upload/'
        'f_auto,q_auto,c_limit,w_800/v1/name.png'
    )


@pytest.mark.parametrize(
    'url', [None, '', 'https://example.com/image/upload/name.png', '/img/local.jpg']
)
def test_cloudinary_leaves_everything_else_alone(url):
    assert cloudinary(url, 800) == url


def test_uri_component_matches_encode_uri_component():
    assert uri_component("a/b c&d!~*'()") == "a%2Fb%20c%26d!~*'()"
