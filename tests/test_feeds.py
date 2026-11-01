from xml.etree import ElementTree

from conftest import SITE_URL, make_content

from website import feeds

SITEMAP = '{http://www.sitemaps.org/schemas/sitemap/0.9}'


def test_escape_xml_escapes_every_special_character():
    assert feeds.escape_xml('&<>"\'') == '&amp;&lt;&gt;&quot;&apos;'


def test_escape_xml_does_not_double_escape():
    assert feeds.escape_xml('a & b') == 'a &amp; b'


def test_rss_is_well_formed_with_special_characters():
    article = make_content('s', title='Tom & <Jerry>', description='"quoted" & more')

    root = ElementTree.fromstring(feeds.build_rss([article]))

    item = root.find('channel/item')
    assert item.findtext('title') == 'Tom & <Jerry>'
    assert item.findtext('description') == '"quoted" & more'


def test_rss_item_links_and_date():
    root = ElementTree.fromstring(feeds.build_rss([make_content('my-slug')]))

    item = root.find('channel/item')
    assert item.findtext('link') == f'{SITE_URL}/articles/my-slug'
    assert item.findtext('guid') == f'{SITE_URL}/articles/my-slug'
    assert item.findtext('pubDate') == 'Sat, 12 Oct 2024 15:30:00 GMT'


def test_rss_without_articles_is_still_valid():
    root = ElementTree.fromstring(feeds.build_rss([]))

    assert root.findall('channel/item') == []


def test_sitemap_lists_static_routes_articles_and_projects():
    root = ElementTree.fromstring(
        feeds.build_sitemap(
            [make_content('an-article')], [make_content('a-project', kind='project')]
        )
    )

    locations = [url.findtext(f'{SITEMAP}loc') for url in root]
    assert locations == [
        SITE_URL,
        f'{SITE_URL}/about',
        f'{SITE_URL}/articles',
        f'{SITE_URL}/projects',
        f'{SITE_URL}/articles/an-article',
        f'{SITE_URL}/projects/a-project',
    ]


def test_sitemap_only_content_pages_have_lastmod():
    root = ElementTree.fromstring(feeds.build_sitemap([make_content('a')], []))

    urls = list(root)
    assert urls[0].find(f'{SITEMAP}lastmod') is None
    assert urls[-1].findtext(f'{SITEMAP}lastmod') == '2024-10-12T15:30:00+00:00'
