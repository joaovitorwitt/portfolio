import io
from datetime import UTC, date, datetime

import pytest
from PIL import Image

from website import publish
from website.markdown import render
from website.publish import StoredImage, Upload

BLOB = 'https://store1.public.blob.vercel-storage.com'

# The header of a real article in joaovitorwitt/articles.
ARTICLE = """---
titulo: "Axiomas da aritmética"
descricao: 'Os conjuntos numéricos, do zero aos reais.'
serie: matematica-basica
ordem: 1
tags: [Matematica, matematica-basica, "Axiomas"]
data: "2026-11-02"
status: rascunho
---

## Introdução

Texto com uma fórmula $a/b$.

![Conjuntos](<imagens/Conjuntos Numéricos.png> "Os conjuntos")
"""


def image_bytes(kind='PNG', size=(40, 20)) -> bytes:
    buffer = io.BytesIO()
    Image.new('RGB', size, 'white').save(buffer, kind)
    return buffer.getvalue()


def test_front_matter_reads_every_field_as_text():
    fields = publish.front_matter(ARTICLE)

    assert publish.field_text(fields, 'titulo') == 'Axiomas da aritmética'
    assert publish.field_text(fields, 'descricao') == (
        'Os conjuntos numéricos, do zero aos reais.'
    )
    assert publish.field_text(fields, 'status') == 'rascunho'
    assert fields['ordem'] == '1'


def test_no_front_matter_gives_no_fields():
    assert publish.front_matter('## Just text\n\n---\n\nmore') == {}


def test_body_without_front_matter_keeps_the_text():
    body = publish.body_without_front_matter(ARTICLE)

    assert body.startswith('\n## Introdução')
    assert 'titulo' not in body


@pytest.mark.parametrize(
    ('value', 'expected'),
    [
        (
            '[Matematica, matematica-basica, "Axiomas"]',
            ['matematica', 'matematica-basica', 'axiomas'],
        ),
        ('Physics, physics,  Computer   Science ', ['physics', 'computer science']),
        ('[]', []),
        ('', []),
    ],
)
def test_tags_are_lowercase_without_repeats(value, expected):
    assert publish.parse_tags(value) == expected


def test_dates_parse_with_or_without_quotes():
    assert publish.parse_date('"2026-11-02"') == date(2026, 11, 2)
    assert publish.parse_date('2026-11-02') == date(2026, 11, 2)
    assert publish.parse_date('""') is None
    assert publish.parse_date('2 de novembro') is None


def test_publish_time_is_midday_utc():
    assert publish.publish_datetime(date(2026, 11, 2)) == datetime(
        2026, 11, 2, 12, tzinfo=UTC
    )


@pytest.mark.parametrize(
    ('text', 'slug'),
    [
        ('Axiomas da aritmética', 'axiomas-da-aritmetica'),
        ('Introdução à Física: parte 2!', 'introducao-a-fisica-parte-2'),
        ('  --  ', ''),
    ],
)
def test_slugify(text, slug):
    assert publish.slugify(text) == slug
    assert slug == '' or publish.SLUG.match(slug)


@pytest.mark.parametrize(
    ('name', 'key'),
    [
        ('imagens/Conjuntos Numéricos.png', 'conjuntos-numericos.png'),
        ('imagens/Conjuntos%20Num%C3%A9ricos.png', 'conjuntos-numericos.png'),
        ('Figura 1.PNG', 'figura-1.png'),
        ('../x/foto.jpeg', 'foto.jpeg'),
    ],
)
def test_image_key_matches_files_to_references(name, key):
    assert publish.image_key(name) == key


@pytest.mark.parametrize(
    ('kind', 'content_type'),
    [
        ('PNG', 'image/png'),
        ('JPEG', 'image/jpeg'),
        ('WEBP', 'image/webp'),
        ('GIF', 'image/gif'),
    ],
)
def test_inspect_image_reads_type_and_size_from_the_bytes(kind, content_type):
    upload = Upload('named-wrong.txt', image_bytes(kind))

    assert publish.inspect_image(upload) == (content_type, 40, 20)


def test_a_renamed_text_file_is_not_an_image():
    with pytest.raises(publish.ImageError, match='evil.png is not a readable image'):
        publish.inspect_image(Upload('evil.png', b'<script>alert(1)</script>'))


def test_other_image_formats_are_refused():
    with pytest.raises(publish.ImageError, match='BMP'):
        publish.inspect_image(Upload('old.bmp', image_bytes('BMP')))


def test_blob_pathname_keeps_the_name_and_adds_the_content_hash():
    upload = Upload('Figura 1.PNG', b'bytes')

    path = publish.blob_pathname('axiomas', upload)

    assert path.startswith('images/article/axiomas/figura-1-')
    assert path.endswith('.png')
    assert path == publish.blob_pathname('axiomas', Upload('figura 1.png', b'bytes'))
    assert path != publish.blob_pathname('axiomas', Upload('Figura 1.PNG', b'other'))


def test_store_image_uploads_with_the_detected_type():
    calls = []

    def uploader(pathname, _data, content_type):
        calls.append((pathname, content_type))
        return f'{BLOB}/{pathname}'

    stored = publish.store_image(Upload('a.png', image_bytes()), 'slug', uploader)

    assert calls[0][1] == 'image/png'
    assert stored == StoredImage(f'{BLOB}/{calls[0][0]}', 40, 20)


def test_referenced_images_lists_relative_paths_once():
    markdown = (
        '![a](imagens/a.png) ![a again](imagens/a.png)\n'
        '![web](https://example.com/b.png) ![root](/img/c.png)\n'
        '![d](imagens/d.webp "Caption"){.wide}\n'
    )

    assert publish.referenced_images(markdown) == ['imagens/a.png', 'imagens/d.webp']


def test_link_images_points_references_at_blob_with_their_size():
    image = StoredImage(
        f'{BLOB}/images/article/axiomas/conjuntos-numericos-0123456789ab.png', 800, 600
    )

    body, missing = publish.link_images(ARTICLE, {'conjuntos-numericos.png': image})

    assert f'![Conjuntos]({image.url} "Os conjuntos"){{width=800 height=600}}' in body
    assert missing == []
    html = render(body).html
    assert 'width="800" height="600"' in html
    assert '<figcaption>Os conjuntos</figcaption>' in html


def test_link_images_reports_what_is_missing_and_leaves_it():
    markdown = '![a](imagens/a.png)\n\n![b](imagens/b.png)\n'
    image = StoredImage(f'{BLOB}/a.png', 1, 1)

    body, missing = publish.link_images(markdown, {'a.png': image})

    assert '![b](imagens/b.png)' in body
    assert missing == ['imagens/b.png']


def test_link_images_keeps_the_authors_attributes_and_absolute_urls():
    markdown = '![a](imagens/a.png){width=300}\n\n![w](https://example.com/w.png)\n'
    image = StoredImage(f'{BLOB}/a.png', 800, 600)

    body, _ = publish.link_images(markdown, {'a.png': image})

    assert f'![a]({BLOB}/a.png){{width=300}}' in body
    assert '![w](https://example.com/w.png)' in body


def test_stored_images_reads_back_what_link_images_wrote():
    url = f'{BLOB}/images/article/axiomas/conjuntos-numericos-0123456789ab.png'
    body, _ = publish.link_images(
        ARTICLE, {'conjuntos-numericos.png': StoredImage(url, 800, 600)}
    )

    assert publish.stored_images(body) == {
        'conjuntos-numericos.png': StoredImage(url, 800, 600)
    }


def test_stored_images_ignores_images_it_did_not_upload():
    markdown = (
        '![x](https://example.com/x-0123456789ab.png){width=1 height=1}\n'
        f'![y]({BLOB}/images/article/s/y-0123456789ab.png)\n'
    )

    assert publish.stored_images(markdown) == {}


def test_rendered_fields_are_the_whole_render():
    fields = publish.rendered_fields(ARTICLE)
    result = render(ARTICLE)

    assert fields == {
        'body_md': ARTICLE,
        'body_html': result.html,
        'has_math': True,
        'toc': result.toc,
        'word_count': result.word_count,
        'body_text': result.text,
    }
    assert 'titulo' not in fields['body_html']


def test_newlines_are_normalised():
    assert publish.normalise_newlines('a\r\nb\rc\n') == 'a\nb\nc\n'
