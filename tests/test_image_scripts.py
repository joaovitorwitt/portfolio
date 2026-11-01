import io

import pytest
from conftest import BLOB_URL, make_content
from PIL import Image

import website.db
from scripts.export_images import collect_references, describe, original_url
from scripts.migrate_images import (
    pathname,
    plan_updates,
    rewrite_body,
    store_base_url,
    unmapped_rows,
)
from website.db import ContentImages

OLD_COVER = 'https://res.cloudinary.com/demo/image/upload/v1/covers/a.png'
OLD_INLINE = 'https://res.cloudinary.com/demo/image/upload/v2/inline/b.png'

MANIFEST = {
    OLD_COVER: {'local_file': 'article/s/aaa.png', 'width': 1000, 'height': 500},
    OLD_INLINE: {'local_file': 'article/s/bbb.png', 'width': 640, 'height': 480},
}


def row(**overrides) -> dict:
    return (
        make_content('s', image_url=OLD_COVER, image_width=None, image_height=None)
        | overrides
    )


@pytest.mark.parametrize(
    'url',
    [
        'https://res.cloudinary.com/demo/image/upload/v1/folder/a.png',
        'https://res.cloudinary.com/demo/image/upload/f_auto,q_auto,w_800/v1/folder/a.png',
        'https://res.cloudinary.com/demo/image/upload/c_fill,w_10/e_blur/v1/folder/a.png',
    ],
)
def test_original_url_strips_transformations(url):
    assert original_url(url) == (
        'https://res.cloudinary.com/demo/image/upload/v1/folder/a.png'
    )


def test_original_url_keeps_a_folder_that_looks_like_a_transformation():
    url = 'https://res.cloudinary.com/demo/image/upload/v1/w_800/a.png'

    assert original_url(url) == url


def test_collect_references_finds_covers_and_inline_images_once():
    rows = [
        row(slug='first', content=f"<img src='{OLD_INLINE}' alt='x'>"),
        row(slug='second', content=f'<img alt="x" src="{OLD_INLINE}">'),
        row(slug='third', image_url=None, content='<p>none</p>'),
        row(slug='fourth', image_url='https://example.com/a.png'),
    ]

    references = collect_references(rows)

    assert set(references) == {OLD_COVER, OLD_INLINE}
    assert references[OLD_INLINE]['slug'] == 'first'


def image_bytes(file_format: str, exif=None) -> bytes:
    buffer = io.BytesIO()
    Image.new('RGB', (40, 20)).save(
        buffer, file_format, **({'exif': exif} if exif else {})
    )
    return buffer.getvalue()


def test_describe_reports_the_format_and_size():
    assert describe(image_bytes('PNG')) == ('png', 40, 20)


def test_describe_swaps_the_size_of_rotated_photos():
    exif = Image.Exif()
    exif[0x0112] = 6

    assert describe(image_bytes('JPEG', exif)) == ('jpg', 20, 40)


def test_describe_refuses_what_is_not_an_image():
    with pytest.raises(OSError):
        describe(b'<html>not found</html>')


def test_store_base_url_comes_from_the_token():
    assert store_base_url('vercel_blob_rw_AbC123_secret') == (
        'https://abc123.public.blob.vercel-storage.com'
    )


def test_store_base_url_refuses_other_tokens_without_repeating_them():
    with pytest.raises(ValueError) as error:
        store_base_url('some-secret-value')

    assert 'some-secret-value' not in str(error.value)


def test_rewrite_body_changes_only_known_images_and_keeps_the_rest():
    body = (
        f"<p>Text</p><img src='{OLD_INLINE}' alt='Axis'/>"
        f"<img src='https://example.com/x.png' alt='Other'>"
    )

    assert rewrite_body(body, MANIFEST, BLOB_URL) == (
        f"<p>Text</p><img src='{BLOB_URL}/images/article/s/bbb.png'"
        ' width="640" height="480" alt=\'Axis\'/>'
        "<img src='https://example.com/x.png' alt='Other'>"
    )


def test_plan_rewrites_the_cover_and_inline_images():
    updates = plan_updates(
        [row(content=f"<img src='{OLD_INLINE}' alt='Axis'>")], MANIFEST, BLOB_URL
    )

    assert len(updates) == 1
    assert updates[0]['image_url'] == f'{BLOB_URL}/{pathname(MANIFEST[OLD_COVER])}'
    assert (updates[0]['image_width'], updates[0]['image_height']) == (1000, 500)
    assert 'cloudinary' not in updates[0]['content']


def test_plan_is_empty_once_everything_is_migrated():
    migrated = row(image_url=f'{BLOB_URL}/images/article/s/aaa.png', image_width=1000)

    assert plan_updates([migrated], MANIFEST, BLOB_URL) == []


def test_plan_keeps_the_stored_size_when_only_the_body_changes():
    migrated = row(
        image_url=f'{BLOB_URL}/images/article/s/aaa.png',
        image_width=1000,
        image_height=500,
        content=f"<img src='{OLD_INLINE}' alt='Axis'>",
    )

    update = plan_updates([migrated], MANIFEST, BLOB_URL)[0]

    assert (update['image_width'], update['image_height']) == (1000, 500)


def test_unmapped_rows_catches_urls_missing_from_the_manifest():
    unknown = 'https://res.cloudinary.com/demo/image/upload/v3/unknown.png'
    rows = [row(), row(id=2, slug='other', content=f"<img src='{unknown}' alt='x'>")]

    assert unmapped_rows(rows, plan_updates(rows, MANIFEST, BLOB_URL)) == ['other']


class FakeConnection:
    def __init__(self, remaining):
        self.remaining = remaining
        self.statements = []

    def connection(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def execute(self, query, params=None):
        self.statements.append((query, params))
        return self

    def fetchone(self):
        return {'remaining': self.remaining}


UPDATE = {
    'id': 1,
    'image_url': 'new',
    'image_width': 1,
    'image_height': 2,
    'content': '',
}


def test_apply_backs_up_before_it_updates(monkeypatch):
    connection = FakeConnection(remaining=0)
    monkeypatch.setattr(website.db, 'get_pool', lambda: connection)

    ContentImages().apply([UPDATE], 'content_backup_20261101')

    statements = [str(query) for query, _params in connection.statements]
    assert 'content_backup_20261101' in statements[0]
    assert 'ROW LEVEL SECURITY' in statements[1]
    assert 'UPDATE content' in statements[2]
    assert connection.statements[2][1] == UPDATE


def test_apply_raises_so_the_transaction_rolls_back_if_urls_remain(monkeypatch):
    monkeypatch.setattr(website.db, 'get_pool', lambda: FakeConnection(remaining=2))

    with pytest.raises(RuntimeError, match='2 rows'):
        ContentImages().apply([UPDATE], 'content_backup_20261101')
