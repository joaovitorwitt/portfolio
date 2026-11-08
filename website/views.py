import logging

from flask import (
    Blueprint,
    Response,
    abort,
    jsonify,
    make_response,
    render_template,
    request,
)

from website import feeds, search
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
        projects_by_slug={
            project['slug']: project
            for project in repository.search(kind='project', limit=LIST_LIMIT)
        },
    )


@bp.route('/about')
def about():
    return render_template('about.html', meta={'title': 'About'})


@bp.route('/articles')
def articles():
    """
    The full list, or search results when `q` is set, optionally within one tag.
    With `partial=1` only the results come back, for search.js to swap in.
    """
    query = search.clean_query(request.args.get('q'))
    tag = request.args.get('tag', '').strip() or None

    if query:
        found = [
            row | {'snippet': search.highlight(row['snippet'])}
            for row in repository.search_text(
                'article', query, tag=tag, limit=LIST_LIMIT
            )
        ]
    else:
        found = repository.search(kind='article', tag=tag, limit=LIST_LIMIT)

    context = {
        'articles': found,
        'query': query,
        'tag': tag,
        'tags': repository.tags('article'),
    }
    # Filtered pages are endless variations on /articles: the canonical link
    # already points there, and noindex keeps them out of search engines.
    filtered = bool(query or tag)

    if request.args.get('partial') == '1':
        response = make_response(render_template('articles/results.html', **context))
        response.headers['X-Robots-Tag'] = 'noindex'
        return response

    return render_template(
        'articles/list.html',
        **context,
        meta={
            'title': 'Articles',
            'description': 'Articles on mathematics, physics, and computer science by João Vitor Witt.',
            'noindex': filtered,
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
        adjacent=repository.adjacent('article', item['created_at']),
        meta={
            'title': item['title'],
            'description': item['description'],
            'type': 'article',
            'image': item['image_url'],
            'image_width': item['image_width'],
            'image_height': item['image_height'],
            'published_time': item['created_at'],
            'modified_time': (
                item['updated_at'] if item['updated_at'] != item['created_at'] else None
            ),
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
            'image_width': item['image_width'],
            'image_height': item['image_height'],
        },
    )


@bp.route('/rss.xml')
def rss():
    articles = repository.search(kind='article', limit=feeds.RSS_LIMIT)
    return Response(feeds.build_rss(articles), mimetype='application/rss+xml')


@bp.route('/sitemap.xml')
def sitemap():
    return Response(
        feeds.build_sitemap(
            repository.search(kind='article', limit=100),
            repository.search(kind='project', limit=100),
        ),
        mimetype='application/xml',
    )


@bp.app_errorhandler(404)
def not_found(_error):
    return render_template('404.html', meta={'title': 'Not Found'}), 404


@bp.route('/health')
def health():
    return jsonify({'status': 'ok'})
