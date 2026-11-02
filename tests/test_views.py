from datetime import UTC, datetime
from pathlib import Path

import pytest
from conftest import BLOB_URL, SITE_URL, FakeRepository, make_content

import settings
import website.views
from website import create_app


@pytest.mark.parametrize(
    'path',
    [
        '/',
        '/about',
        '/articles',
        '/articles/newest',
        '/projects',
        '/projects/a-project',
        '/rss.xml',
        '/sitemap.xml',
        '/health',
    ],
)
def test_route_responds(client, path):
    assert client.get(path).status_code == 200


@pytest.mark.parametrize(
    'path',
    [
        '/nope',
        '/articles/nope',
        '/projects/nope',
        # Same slug, wrong kind: the kinds don't share URLs.
        '/articles/a-project',
        '/projects/newest',
    ],
)
def test_unknown_urls_are_real_404s(client, path):
    response = client.get(path)

    assert response.status_code == 404
    assert 'text/html' in response.content_type


def test_home_shows_the_latest_three_articles_only(client, rows):
    oldest = rows[2]['created_at'].replace(year=2000)
    rows.append(
        rows[0] | {'slug': 'fourth', 'title': 'Should be cut off', 'created_at': oldest}
    )

    html = client.get('/').text

    assert 'Newest article' in html
    assert 'Oldest article' in html
    assert 'Should be cut off' not in html


def test_article_list_is_newest_first_without_projects(client):
    html = client.get('/articles').text

    assert html.index('Newest article') < html.index('Middle article')
    assert html.index('Middle article') < html.index('Oldest article')
    assert 'A project' not in html


def test_article_detail_renders_the_body_as_html(client):
    assert '<p>Body of newest</p>' in client.get('/articles/newest').text


def test_article_detail_relates_only_other_articles_with_the_same_tag(client):
    html = client.get('/articles/newest').text

    assert '/articles/middle' in html
    assert '/articles/oldest' not in html


def test_article_without_tags_has_no_related_articles(client, rows):
    rows[0]['tags'] = []

    html = client.get('/articles/newest').text

    assert 'Related articles' not in html


def test_article_canonical_url_uses_the_site_url(client):
    assert f'{SITE_URL}/articles/newest' in client.get('/articles/newest').text


def test_feeds_have_xml_content_types(client):
    assert client.get('/rss.xml').mimetype == 'application/rss+xml'
    assert client.get('/sitemap.xml').mimetype == 'application/xml'


def test_feeds_list_the_content(client):
    assert f'{SITE_URL}/articles/newest' in client.get('/rss.xml').text
    assert f'{SITE_URL}/projects/a-project' in client.get('/sitemap.xml').text


def test_pages_are_cacheable_by_browsers_and_the_cdn(client):
    response = client.get('/articles')

    assert response.headers['Cache-Control'].startswith('public, max-age=')
    assert 's-maxage=' not in response.headers['Cache-Control']
    assert 's-maxage=' in response.headers['Vercel-CDN-Cache-Control']


def test_repeat_request_with_the_etag_gets_a_304(client):
    etag = client.get('/articles').headers['ETag']

    response = client.get('/articles', headers={'If-None-Match': etag})

    assert response.status_code == 304
    assert response.data == b''


@pytest.mark.parametrize('path', ['/nope', '/articles/nope', '/health'])
def test_errors_and_health_are_never_stored(client, path):
    response = client.get(path)

    assert 'no-store' in response.headers['Cache-Control']
    assert 'public' not in response.headers['Cache-Control']
    assert 'Vercel-CDN-Cache-Control' not in response.headers


def test_public_files_do_not_get_page_cache_headers(client):
    response = client.get('/img/profile-picture.jpg')

    assert response.status_code == 200
    assert 'Vercel-CDN-Cache-Control' not in response.headers


def test_covers_carry_their_stored_size_and_alt(client):
    html = client.get('/articles/newest').text

    assert 'alt="Newest article" width="1000" height="500"' in html


def test_cover_without_a_stored_size_falls_back_to_16_by_9(monkeypatch, rows):
    rows[0] |= {'image_width': None, 'image_height': None}
    monkeypatch.setattr(website.views, 'repository', FakeRepository(rows))

    html = create_app().test_client().get('/articles/newest').text

    assert 'alt="Newest article" width="1920" height="1080"' in html


def test_covers_share_their_size_with_link_unfurls(client):
    html = client.get('/articles/newest').text

    assert '<meta property="og:image:width" content="1000">' in html
    assert '<meta property="og:image:height" content="500">' in html


def test_covers_are_resized_on_vercel(monkeypatch, client):
    monkeypatch.setattr(settings, 'ON_VERCEL', True)

    html = client.get('/articles/newest').text

    assert 'src="/_vercel/image?url=' in html
    assert 'srcset="/_vercel/image?url=' in html
    assert 'sizes="(max-width: 900px) 100vw, 900px"' in html


def test_inline_images_are_rewritten_on_article_pages(monkeypatch, rows):
    monkeypatch.setattr(settings, 'ON_VERCEL', True)
    rows[0]['content'] = f"<img src='{BLOB_URL}/a.png' alt='Axis'>"
    monkeypatch.setattr(website.views, 'repository', FakeRepository(rows))

    html = create_app().test_client().get('/articles/newest').text

    assert '<div class="article-body"><img src="/_vercel/image?url=' in html


def test_homepage_cards_take_images_from_the_database(monkeypatch, rows):
    rows.append(make_content('halting', kind='project'))
    monkeypatch.setattr(website.views, 'repository', FakeRepository(rows))

    html = create_app().test_client().get('/').text

    assert f'{BLOB_URL}/images/project/halting/abc123.png" alt="Halting"' in html


def test_nothing_rendered_or_in_a_template_mentions_cloudinary(client):
    for path in (
        '/',
        '/about',
        '/articles',
        '/articles/newest',
        '/projects',
        '/rss.xml',
    ):
        assert 'cloudinary' not in client.get(path).text

    for template in Path('website/templates').rglob('*.html'):
        assert 'cloudinary' not in template.read_text(encoding='utf-8')


def article_with(monkeypatch, rows, **overrides):
    rows[0].update(overrides)
    monkeypatch.setattr(website.views, 'repository', FakeRepository(rows))
    return create_app().test_client().get('/articles/newest').text


def test_rendered_body_wins_over_the_legacy_one(monkeypatch, rows):
    html = article_with(monkeypatch, rows, body_html='<p>Rendered body</p>')

    assert '<div class="article-body prose"><p>Rendered body</p></div>' in html
    assert 'Body of newest' not in html


def test_articles_not_yet_converted_keep_the_legacy_body_and_mathjax(client):
    html = client.get('/articles/newest').text

    assert '<div class="article-body"><p>Body of newest</p></div>' in html
    assert 'mathjax' in html
    assert 'prose.modules.css' not in html


def test_rendered_bodies_need_no_mathjax(monkeypatch, rows):
    html = article_with(
        monkeypatch, rows, body_html='<p><math></math></p>', has_math=True
    )

    assert 'mathjax' not in html
    assert 'prose.modules.css' in html


def test_inline_images_in_rendered_bodies_are_resized_on_vercel(monkeypatch, rows):
    monkeypatch.setattr(settings, 'ON_VERCEL', True)
    src = f'{BLOB_URL}/images/article/newest/inline.png'

    html = article_with(
        monkeypatch,
        rows,
        body_html=f'<figure><img src="{src}" alt="a" width="1920" height="1080"></figure>',
    )

    assert '<figure><img src="/_vercel/image?url=' in html
    assert 'sizes="(max-width: 720px) 100vw, 680px"' in html


def test_reading_time_comes_from_the_stored_word_count(monkeypatch, rows):
    html = article_with(monkeypatch, rows, body_html='<p>x</p>', word_count=1000)

    assert '5 min read' in html


TOC = [{'level': 2, 'id': f'section-{n}', 'text': f'Section {n}'} for n in range(3)]


def test_three_headings_get_a_table_of_contents(monkeypatch, rows):
    html = article_with(monkeypatch, rows, body_html='<p>x</p>', toc=TOC)

    assert '<details class="toc toc-collapsed">' in html
    assert '<nav class="toc toc-side" aria-label="Contents">' in html
    assert html.count('<a href="#section-1">Section 1</a>') == 2


def test_two_headings_are_not_worth_a_table_of_contents(monkeypatch, rows):
    html = article_with(monkeypatch, rows, body_html='<p>x</p>', toc=TOC[:2])

    assert 'class="toc' not in html
    assert 'has-toc' not in html


def test_previous_and_next_follow_the_publishing_order(client):
    html = client.get('/articles/middle').text

    assert (
        '<a href="/articles/oldest" class="article-pagination-link" rel="prev">' in html
    )
    assert (
        '<a href="/articles/newest" class="article-pagination-link is-next" rel="next">'
        in html
    )
    assert 'A project' not in html


def test_the_newest_article_has_no_next_and_the_oldest_no_previous(client):
    assert 'rel="next"' not in client.get('/articles/newest').text
    assert 'rel="prev"' not in client.get('/articles/oldest').text


def test_an_unedited_article_does_not_claim_an_update(client):
    html = client.get('/articles/newest').text

    assert 'Updated on' not in html
    assert 'article:modified_time' not in html


def test_an_edited_article_shows_when(monkeypatch, rows):
    html = article_with(
        monkeypatch, rows, updated_at=datetime(2026, 11, 2, 12, 0, tzinfo=UTC)
    )

    assert 'Updated on November 2, 2026' in html
    assert 'article:modified_time" content="2026-11-02T12:00:00+00:00"' in html


def test_an_edit_on_the_day_of_publishing_is_not_worth_mentioning(monkeypatch, rows):
    created = rows[0]['created_at']

    html = article_with(
        monkeypatch, rows, updated_at=created.replace(hour=created.hour + 1)
    )

    assert 'Updated on' not in html


def test_the_title_is_the_only_h1(client):
    assert client.get('/articles/newest').text.count('<h1') == 1
