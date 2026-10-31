import logging
from datetime import UTC, datetime
from pathlib import Path

from flask import Flask, request

import settings

# Vercel serves public/ from its CDN at the site root, before a request ever
# reaches the function, and advises against Flask's static folder. Locally the
# same directory is mounted at the same root so every asset URL is identical in
# both places.
PUBLIC_DIR = Path(__file__).resolve().parent.parent / 'public'


def create_app() -> Flask:
    logging.basicConfig(level=logging.INFO)

    if settings.ON_VERCEL:
        app = Flask(__name__, static_folder=None)
    else:
        app = Flask(__name__, static_folder=PUBLIC_DIR, static_url_path='')

    @app.context_processor
    def inject_site():
        """
        `site` carries the site-wide metadata defaults; `page_url` is the
        canonical absolute URL of the current page, for og:url and sharing.
        Dates are UTC throughout, the footer year included.
        """
        return {
            'site': {
                'url': settings.SITE_URL,
                'title': settings.SITE_TITLE,
                'description': settings.SITE_DESCRIPTION,
                'creator': settings.SITE_CREATOR,
                'keywords': settings.SITE_KEYWORDS,
                'image': settings.SITE_IMAGE,
                'image_width': settings.SITE_IMAGE_WIDTH,
                'image_height': settings.SITE_IMAGE_HEIGHT,
            },
            'page_url': settings.SITE_URL + request.path,
            'now_year': datetime.now(UTC).year,
        }

    @app.after_request
    def add_cache_headers(response):
        """
        Content changes rarely, so successful page loads are cacheable. Inside
        max-age the browser skips the request entirely, a CDN in front can
        serve other visitors without running the function, and the ETag turns
        a repeat request into a 304 with no body. stale-while-revalidate lets
        a cache keep serving the old copy while it refreshes in the background.

        Everything else (errors, 404s, the health check) is never stored.
        Files from public/ are left alone: on Vercel the CDN serves them, and
        locally send_file already handles their ETags.
        """
        if request.endpoint == 'static' and response.status_code < 400:
            return response

        cacheable = (
            request.method in ('GET', 'HEAD')
            and response.status_code == 200
            and request.endpoint != 'pages.health'
        )
        if not cacheable:
            response.cache_control.no_store = True
            return response

        # One header rather than appended directives; some CDNs only honour
        # the first Cache-Control line.
        response.headers['Cache-Control'] = (
            f'public, max-age={settings.CACHE_MAX_AGE}, '
            f'stale-while-revalidate={settings.CACHE_STALE_WHILE_REVALIDATE}'
        )
        response.add_etag()
        return response.make_conditional(request)

    from website import filters
    from website.views import bp

    filters.register(app)
    app.register_blueprint(bp)

    return app
