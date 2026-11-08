"""
Clears Vercel's CDN copy of the public pages, so a change made in the admin is
live on the next visit instead of after the 5-minute cache.

Every public page carries the same cache tag (`Vercel-Cache-Tag: pages`), so a
single call clears them all: the article, the lists, the home page, search
results, rss.xml and sitemap.xml. With a handful of articles, refreshing every
page is cheaper than working out which ones changed.

It uses "delete by tags", not "invalidate": after an invalidation the next
visitor still gets the old copy once while Vercel refreshes it in the
background. After a delete, the next visitor gets a fresh page.
"""

import json
import logging
import urllib.error
import urllib.parse
import urllib.request

import settings

log = logging.getLogger(__name__)

PAGES_TAG = 'pages'

API_URL = 'https://api.vercel.com/v1/edge-cache/dangerously-delete-by-tags'

# Cache tags are kept per environment. Previews read the same database, so both
# are cleared.
TARGETS = ('production', 'preview')

TIMEOUT_SECONDS = 10


class PurgeError(Exception):
    pass


def configured() -> bool:
    return bool(settings.VERCEL_API_TOKEN and settings.VERCEL_PROJECT_ID)


def purge_url() -> str:
    query = {'projectIdOrName': settings.VERCEL_PROJECT_ID}
    if settings.VERCEL_TEAM_ID:
        query['teamId'] = settings.VERCEL_TEAM_ID

    return f'{API_URL}?{urllib.parse.urlencode(query)}'


def purge_pages(opener=urllib.request.urlopen) -> None:
    """
    Deletes every cached public page. Raises PurgeError with the reason, never
    with the token.
    """
    if not configured():
        raise PurgeError('VERCEL_API_TOKEN or VERCEL_PROJECT_ID is not set')

    for target in TARGETS:
        request = urllib.request.Request(
            purge_url(),
            data=json.dumps({'tags': [PAGES_TAG], 'target': target}).encode(),
            headers={
                'Authorization': f'Bearer {settings.VERCEL_API_TOKEN}',
                'Content-Type': 'application/json',
            },
            method='POST',
        )
        try:
            with opener(request, timeout=TIMEOUT_SECONDS) as response:
                response.read()
        except urllib.error.HTTPError as error:
            raise PurgeError(f'Vercel answered {error.code} for {target}') from error
        except (urllib.error.URLError, TimeoutError) as error:
            raise PurgeError(f'could not reach Vercel: {error}') from error
