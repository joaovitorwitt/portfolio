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

    from website.views import bp

    app.register_blueprint(bp)

    return app
