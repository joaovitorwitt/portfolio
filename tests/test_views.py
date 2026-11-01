import pytest
from conftest import SITE_URL


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

    assert '/articles/middle' not in html


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
