"""
The admin area under /admin: sign in, then publish, edit and delete articles by
uploading their Markdown file and images. create_app() marks every response
here private and no-store.
"""

import logging
from datetime import UTC, datetime

from flask import (
    Blueprint,
    abort,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from psycopg.errors import UniqueViolation

import settings
from website import auth, cache, publish
from website.db import AdminUsers, ArticleAdmin

log = logging.getLogger(__name__)

bp = Blueprint('admin', __name__)

users = AdminUsers()
articles = ArticleAdmin()
uploader = publish.upload_to_blob
purge = cache.purge_pages


def clear_site_cache(done: str) -> None:
    """
    Clears the CDN after a change and says how it went. A failure never undoes
    the change: the page then catches up within the usual cache time.
    """
    minutes = settings.CACHE_MAX_AGE // 60
    try:
        purge()
    except cache.PurgeError as error:
        log.warning('cache purge failed: %s', error)
        flash(
            f'{done} The site cache could not be cleared ({error}), so the '
            f'change shows within {minutes} minutes.',
            'warning',
        )
        return

    flash(f'{done} It is live on the site now.', 'success')


@bp.before_request
def protect_posts():
    if request.method == 'POST':
        auth.check_csrf()


@bp.context_processor
def inject_admin():
    return {
        'csrf_field': auth.CSRF_FIELD,
        'csrf_token': auth.csrf_token,
        'admin_name': session.get('admin_name'),
    }


@bp.errorhandler(400)
def bad_request(error):
    return render_template('admin/error.html', message=error.description), 400


@bp.errorhandler(413)
def too_large(_error):
    limit_mb = settings.MAX_UPLOAD_BYTES / 1_000_000
    message = (
        f'The upload is over {limit_mb:g} MB, which Vercel refuses. Save the '
        'article with fewer images, then add the rest through Edit.'
    )
    return render_template('admin/error.html', message=message), 413


@bp.route('/login', methods=['GET', 'POST'])
def login():
    if auth.signed_in():
        return redirect(url_for('admin.index'))

    error = None
    username = ''
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        user, error = auth.authenticate(
            users, username, request.form.get('password', '')
        )
        if user is not None:
            auth.sign_in(user)
            return redirect(url_for('admin.index'))

    status = 401 if error else 200
    return render_template('admin/login.html', error=error, username=username), status


@bp.route('/logout', methods=['POST'])
def logout():
    auth.sign_out()
    return redirect(url_for('admin.login'))


@bp.route('')
@auth.login_required
def index():
    return render_template('admin/articles.html', articles=articles.rows())


@bp.route('/cache/clear', methods=['POST'])
@auth.login_required
def clear_cache():
    """For changes made outside the admin, such as SQL or a script."""
    clear_site_cache('Cleared the site cache.')
    return redirect(url_for('admin.index'))


@bp.route('/articles/new', methods=['GET', 'POST'])
@auth.login_required
def new_article():
    if request.method == 'POST':
        return save_article(None)

    return render_form(None, {}, [])


@bp.route('/articles/<int:article_id>', methods=['GET', 'POST'])
@auth.login_required
def edit_article(article_id: int):
    existing = articles.get(article_id)
    if existing is None:
        abort(404)

    if request.method == 'POST':
        return save_article(existing)

    return render_form(existing, values_of(existing), [])


@bp.route('/articles/<int:article_id>/delete', methods=['GET', 'POST'])
@auth.login_required
def delete_article(article_id: int):
    existing = articles.get(article_id)
    if existing is None:
        abort(404)

    if request.method == 'POST':
        articles.delete(article_id)
        clear_site_cache(f'Deleted "{existing["title"]}".')
        return redirect(url_for('admin.index'))

    return render_template('admin/delete.html', article=existing)


def values_of(article: dict) -> dict:
    return {
        'title': article['title'],
        'slug': article['slug'],
        'description': article['description'],
        'tags': ', '.join(article['tags']),
        'date': article['created_at'].date().isoformat(),
    }


def render_form(existing: dict | None, values: dict, errors: list[str], status=200):
    missing = []
    if existing and existing['body_md']:
        missing = publish.referenced_images(existing['body_md'])

    return (
        render_template(
            'admin/form.html',
            article=existing,
            values=values,
            errors=errors,
            missing=missing,
            description_limit=publish.DESCRIPTION_LIMIT,
        ),
        status,
    )


def read_uploads(name: str) -> list[publish.Upload]:
    return [
        publish.Upload(file.filename, file.read())
        for file in request.files.getlist(name)
        if file.filename
    ]


def save_article(existing: dict | None):
    """
    Checks everything first and uploads images only once nothing is wrong, so
    a rejected form leaves no files behind. A value typed in the form wins
    over the front matter.
    """
    form = request.form
    errors = []

    markdown = None
    markdown_file = request.files.get('markdown')
    if markdown_file and markdown_file.filename:
        try:
            markdown = publish.normalise_newlines(
                markdown_file.read().decode('utf-8-sig')
            )
        except UnicodeDecodeError:
            errors.append('The Markdown file is not UTF-8 text.')
    elif existing is None or not existing['body_md']:
        errors.append("Choose the article's .md file.")

    fields = publish.front_matter(markdown) if markdown else {}
    title = form.get('title', '').strip() or publish.field_text(fields, 'titulo')
    description = form.get('description', '').strip() or publish.field_text(
        fields, 'descricao'
    )
    tags = publish.parse_tags(form.get('tags', '')) or publish.parse_tags(
        fields.get('tags', '')
    )
    day = (
        publish.parse_date(form.get('date', ''))
        or publish.parse_date(fields.get('data', ''))
        or (existing['created_at'].date() if existing else datetime.now(UTC).date())
    )
    slug = form.get('slug', '').strip().lower() or publish.slugify(title)

    values = {
        'title': title,
        'slug': slug,
        'description': description,
        'tags': ', '.join(tags),
        'date': day.isoformat(),
    }
    existing_id = existing['id'] if existing else None

    if not title:
        errors.append('The title is empty.')
    if not publish.SLUG.match(slug):
        errors.append('The slug may only have lowercase letters, digits and dashes.')
    elif articles.slug_taken(slug, existing_id):
        errors.append(f'Another article already uses the slug "{slug}".')
    if markdown is not None and not publish.body_without_front_matter(markdown).strip():
        errors.append('The Markdown file has no text after the front matter.')

    images = read_uploads('images')
    covers = read_uploads('cover')
    for upload in images + covers:
        try:
            publish.inspect_image(upload)
        except publish.ImageError as error:
            errors.append(f'{error}.')

    if errors:
        return render_form(existing, values, errors, status=400)

    body = markdown if markdown is not None else existing['body_md']
    known = publish.stored_images(existing['body_md']) if existing else {}
    try:
        for upload in images:
            known[publish.image_key(upload.filename)] = publish.store_image(
                upload, slug, uploader
            )
        cover = publish.store_image(covers[0], slug, uploader) if covers else None
    except Exception:
        log.exception('image upload failed')
        errors.append('Uploading the images to Vercel Blob failed. Try again.')
        return render_form(existing, values, errors, status=502)

    body, missing = publish.link_images(body, known)
    row = publish.rendered_fields(body) | {
        'title': title,
        'slug': slug,
        'description': description,
        'tags': tags,
        'image_url': cover.url if cover else (existing or {}).get('image_url'),
        'image_width': cover.width if cover else (existing or {}).get('image_width'),
        'image_height': (
            cover.height if cover else (existing or {}).get('image_height')
        ),
        # Re-saving on the same day keeps the exact time, and with it the order.
        'created_at': (
            existing['created_at']
            if existing and existing['created_at'].date() == day
            else publish.publish_datetime(day)
        ),
    }

    try:
        if existing:
            articles.update(existing['id'], row)
            article_id = existing['id']
        else:
            article_id = articles.create(row)
    except UniqueViolation:
        errors.append(f'Another article already uses the slug "{slug}".')
        return render_form(existing, values, errors, status=400)

    for warning in save_warnings(fields, description, row['body_html'], missing):
        flash(warning, 'warning')
    clear_site_cache('Saved.')
    return redirect(url_for('admin.edit_article', article_id=article_id))


def save_warnings(
    fields: dict, description: str, body_html: str, missing: list[str]
) -> list[str]:
    """Things worth a second look that don't stop the save."""
    warnings = []
    if missing:
        warnings.append(
            f'No image uploaded for {", ".join(missing)}. Add it through Edit.'
        )

    status = publish.field_text(fields, 'status')
    if status and status != publish.READY_STATUS:
        warnings.append(
            f'The front matter says status: {status}, not {publish.READY_STATUS}.'
        )

    if len(description) > publish.DESCRIPTION_LIMIT:
        warnings.append(
            f'The description has {len(description)} characters; search engines '
            f'cut it at about {publish.DESCRIPTION_LIMIT}.'
        )

    if publish.has_math_errors(body_html):
        warnings.append('An equation could not be converted; it shows as TeX.')

    return warnings
