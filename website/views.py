import logging

from flask import Blueprint, abort, jsonify, render_template

from website.db import ContentRepository

log = logging.getLogger(__name__)

bp = Blueprint('pages', __name__)

repository = ContentRepository()

# The old API's default page size; comfortably above what exists today.
LIST_LIMIT = 50


def get_or_404(kind: str, slug: str) -> dict:
    item = repository.get_by_slug(kind, slug)
    if item is None:
        abort(404)

    return item


@bp.route('/')
def index():
    return render_template(
        'index.html',
        articles=repository.search(kind='article', limit=3),
    )


@bp.route('/about')
def about():
    return render_template('about.html', meta={'title': 'About'})


@bp.route('/articles')
def articles():
    return render_template(
        'articles/list.html',
        articles=repository.search(kind='article', limit=LIST_LIMIT),
        meta={
            'title': 'Articles',
            'description': 'Articles on mathematics, physics, and computer science by João Vitor Witt.',
        },
    )


@bp.route('/articles/<slug>')
def article(slug: str):
    item = get_or_404('article', slug)

    # Fetch one extra so there's still something left after the current
    # article (which necessarily has this tag too) is filtered out.
    related = []
    if item['tags']:
        candidates = repository.search(kind='article', tag=item['tags'][0], limit=4)
        related = [a for a in candidates if a['slug'] != item['slug']][:3]

    return render_template(
        'articles/detail.html',
        article=item,
        related=related,
        meta={
            'title': item['title'],
            'description': item['description'],
            'type': 'article',
            'image': item['image_url'],
            'published_time': item['created_at'],
            'tags': item['tags'],
        },
    )


@bp.route('/projects')
def projects():
    return render_template(
        'projects/list.html',
        projects=repository.search(kind='project', limit=LIST_LIMIT),
        meta={'title': 'Projects'},
    )


@bp.route('/projects/<slug>')
def project(slug: str):
    item = get_or_404('project', slug)

    return render_template(
        'projects/detail.html',
        project=item,
        meta={
            'title': item['title'],
            'description': item['description'],
            'image': item['image_url'],
        },
    )


@bp.route('/health')
def health():
    return jsonify({'status': 'ok'})
