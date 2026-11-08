import logging
import secrets
from datetime import UTC, datetime, timedelta
from pathlib import Path

from flask import Flask, request

import settings
from website import cache

# Vercel serves public/ from its CDN at the site root, before a request ever
# reaches the function, and advises against Flask's static folder. Locally the
# same directory is mounted at the same root so every asset URL is identical in
# both places.
PUBLIC_DIR = Path(__file__).resolve().parent.parent / 'public'


ADMIN_PREFIX = '/admin'


def is_admin_path(path: str) -> bool:
    return path == ADMIN_PREFIX or path.startswith(ADMIN_PREFIX + '/')


def create_app() -> Flask:
    logging.basicConfig(level=logging.INFO)

    if settings.ON_VERCEL and not settings.SECRET_KEY:
        raise RuntimeError(
            'SECRET_KEY is not set. Add it in the Vercel dashboard: '
            'Settings -> Environment Variables.'
        )

    if settings.ON_VERCEL:
        app = Flask(__name__, static_folder=None)
    else:
        app = Flask(__name__, static_folder=PUBLIC_DIR, static_url_path='')

    app.config.update(
        # Locally, a missing key gets a random one: signing in works, but only
        # until the server restarts.
        SECRET_KEY=settings.SECRET_KEY or secrets.token_hex(32),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE='Lax',
        # Local development runs on plain http.
        SESSION_COOKIE_SECURE=settings.ON_VERCEL,
        PERMANENT_SESSION_LIFETIME=timedelta(hours=settings.ADMIN_SESSION_HOURS),
        MAX_CONTENT_LENGTH=settings.MAX_UPLOAD_BYTES,
    )

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
        Content changes rarely, so successful page loads are cacheable by
        Vercel's CDN, which serves other visitors without running the function.
        The admin clears it after every save through the cache tag (see
        website/cache.py). Browsers keep a copy too but check it on every
        visit, so they never show a page older than the CDN's; the ETag turns
        that check into a 304 with no body.

        Everything else (errors, 404s, the health check) is never stored.
        Files from public/ are left alone: on Vercel the CDN serves them, and
        locally send_file already handles their ETags.
        """
        if request.endpoint == 'static' and response.status_code < 400:
            return response

        # Admin pages are personal: a shared cache must never keep one, or it
        # would serve it to the next visitor. No CDN header either, so Vercel
        # never stores them.
        if is_admin_path(request.path):
            response.headers['Cache-Control'] = 'private, no-store'
            response.headers['X-Robots-Tag'] = 'noindex'
            response.headers['X-Frame-Options'] = 'DENY'
            response.headers.pop('Vercel-CDN-Cache-Control', None)
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
        response.headers['Cache-Control'] = 'public, max-age=0, must-revalidate'
        # Vercel's CDN only caches function responses that carry s-maxage.
        # This header is read by Vercel alone and never reaches the browser,
        # so the Cache-Control above is exactly what visitors see.
        response.headers['Vercel-CDN-Cache-Control'] = (
            f'public, s-maxage={settings.CACHE_MAX_AGE}, '
            f'stale-while-revalidate={settings.CACHE_STALE_WHILE_REVALIDATE}'
        )
        # What the admin clears after a save. Vercel reads it and drops it.
        response.headers['Vercel-Cache-Tag'] = cache.PAGES_TAG
        response.add_etag()
        return response.make_conditional(request)

    from website import filters
    from website.admin import bp as admin_bp
    from website.views import bp

    filters.register(app)
    app.register_blueprint(bp)
    app.register_blueprint(admin_bp, url_prefix=ADMIN_PREFIX)

    return app
