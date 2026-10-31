"""
rss.xml and sitemap.xml, built as strings the way the Next.js route handlers
did, so the output stays byte-for-byte close to what feed readers and search
engines already have.
"""

from email.utils import format_datetime

import settings

RSS_LIMIT = 50

# Same priorities and frequencies as the old src/app/sitemap.ts.
STATIC_ROUTES = (
    ('', 'monthly', 1),
    ('/about', 'yearly', 0.6),
    ('/articles', 'weekly', 0.8),
    ('/projects', 'monthly', 0.7),
)
ARTICLE_PRIORITY = 0.6
PROJECT_PRIORITY = 0.5

_XML_ESCAPES = (
    ('&', '&amp;'),
    ('<', '&lt;'),
    ('>', '&gt;'),
    ('"', '&quot;'),
    ("'", '&apos;'),
)


def escape_xml(value: str) -> str:
    for char, entity in _XML_ESCAPES:
        value = value.replace(char, entity)

    return value


def build_rss(articles: list[dict]) -> str:
    base = settings.SITE_URL
    items = ''.join(
        f"""
    <item>
      <title>{escape_xml(article['title'])}</title>
      <link>{base}/articles/{article['slug']}</link>
      <guid>{base}/articles/{article['slug']}</guid>
      <pubDate>{format_datetime(article['created_at'], usegmt=True)}</pubDate>
      <description>{escape_xml(article['description'])}</description>
    </item>"""
        for article in articles
    )

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>{escape_xml(settings.SITE_TITLE)}</title>
    <link>{base}</link>
    <description>{escape_xml(settings.SITE_DESCRIPTION)}</description>
    <language>en-us</language>
    <atom:link href="{base}/rss.xml" rel="self" type="application/rss+xml" />
    {items}
  </channel>
</rss>"""


def _url(loc: str, frequency: str, priority: float, lastmod=None) -> str:
    lastmod_tag = f'<lastmod>{lastmod.isoformat()}</lastmod>\n' if lastmod else ''
    return (
        f'<url>\n<loc>{escape_xml(loc)}</loc>\n{lastmod_tag}'
        f'<changefreq>{frequency}</changefreq>\n<priority>{priority}</priority>\n</url>\n'
    )


def build_sitemap(articles: list[dict], projects: list[dict]) -> str:
    base = settings.SITE_URL
    urls = [
        _url(base + path, frequency, priority)
        for path, frequency, priority in STATIC_ROUTES
    ]
    urls += [
        _url(
            f'{base}/articles/{a["slug"]}', 'monthly', ARTICLE_PRIORITY, a['created_at']
        )
        for a in articles
    ]
    urls += [
        _url(
            f'{base}/projects/{p["slug"]}', 'monthly', PROJECT_PRIORITY, p['created_at']
        )
        for p in projects
    ]

    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f'{"".join(urls)}</urlset>\n'
    )
