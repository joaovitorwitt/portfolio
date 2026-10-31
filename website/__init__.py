import logging
from pathlib import Path

from flask import Flask

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

    from website.views import bp

    app.register_blueprint(bp)

    return app
