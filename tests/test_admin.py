import io
from datetime import UTC, datetime

import pytest
from conftest import BLOB_URL, FakeRepository
from PIL import Image
from psycopg.errors import UniqueViolation

import settings
import website.admin
import website.views
from website import auth, create_app
from website.db import ARTICLE_WRITE_COLUMNS
from website.markdown import render

PASSWORD = 'correct horse battery staple'
PASSWORD_HASH = auth.hash_password(PASSWORD)
TOKEN = 'test-csrf-token'
CREATED = datetime(2026, 1, 5, 9, 30, tzinfo=UTC)

MARKDOWN = b"""---
titulo: "Axiomas da aritmetica"
descricao: "Os conjuntos numericos."
tags: [Matematica, Axiomas]
data: "2026-11-02"
status: pronto
---

## Introducao

Um texto com $x^2$.

![Figura](<imagens/Figura 1.png>)
"""


def png(size=(40, 20)) -> bytes:
    buffer = io.BytesIO()
    Image.new('RGB', size, 'white').save(buffer, 'PNG')
    return buffer.getvalue()


class FakeUsers:
    def __init__(self):
        self.user = {
            'id': 1,
            'username': 'joao',
            'password_hash': PASSWORD_HASH,
            'locked': False,
        }
        self.failures = 0

    def get(self, username):
        return dict(self.user) if username == self.user['username'] else None

    def record_failure(self, user_id, max_attempts, lock_minutes):
        self.failures += 1
        if self.failures >= max_attempts:
            self.user['locked'] = True
            self.failures = 0

    def record_success(self, user_id):
        self.failures = 0


class FakeArticles:
    def __init__(self, existing=()):
        self.by_id = {row['id']: dict(row) for row in existing}
        self.saved = []
        self.deleted = []

    def rows(self):
        return list(self.by_id.values())

    def get(self, article_id):
        row = self.by_id.get(article_id)
        return dict(row) if row else None

    def slug_taken(self, slug, exclude_id=None):
        return any(
            row['slug'] == slug and row['id'] != exclude_id
            for row in self.by_id.values()
        )

    def create(self, fields):
        assert set(fields) == set(ARTICLE_WRITE_COLUMNS)
        article_id = max(self.by_id, default=0) + 1
        self.by_id[article_id] = fields | {
            'id': article_id,
            'updated_at': fields['created_at'],
        }
        self.saved.append(fields)
        return article_id

    def update(self, article_id, fields):
        assert set(fields) == set(ARTICLE_WRITE_COLUMNS)
        self.by_id[article_id] |= fields
        self.saved.append(fields)

    def delete(self, article_id):
        self.deleted.append(article_id)
        del self.by_id[article_id]


class FakeUploader:
    def __init__(self):
        self.calls = []

    def __call__(self, pathname, data, content_type):
        self.calls.append((pathname, content_type))
        return f'{BLOB_URL}/{pathname}'


def stored_article(**overrides) -> dict:
    url = f'{BLOB_URL}/images/article/old/figura-1-0123456789ab.png'
    return {
        'id': 7,
        'slug': 'old',
        'title': 'Old title',
        'description': 'Old description',
        'tags': ['physics'],
        'image_url': f'{BLOB_URL}/images/article/old/cover-0123456789ab.png',
        'image_width': 1200,
        'image_height': 630,
        'body_md': f'## Old\n\n![Figura]({url}){{width=40 height=20}}\n\n![b](imagens/b.png)\n',
        'created_at': CREATED,
        'updated_at': CREATED,
    } | overrides


@pytest.fixture(autouse=True)
def users(monkeypatch):
    fake = FakeUsers()
    monkeypatch.setattr(website.admin, 'users', fake)
    return fake


@pytest.fixture(autouse=True)
def articles(monkeypatch):
    fake = FakeArticles([stored_article()])
    monkeypatch.setattr(website.admin, 'articles', fake)
    return fake


@pytest.fixture(autouse=True)
def uploader(monkeypatch):
    fake = FakeUploader()
    monkeypatch.setattr(website.admin, 'uploader', fake)
    return fake


@pytest.fixture
def app(monkeypatch, rows):
    monkeypatch.setattr(website.views, 'repository', FakeRepository(rows))
    return create_app()


@pytest.fixture
def anonymous(app):
    client = app.test_client()
    with client.session_transaction() as session:
        session[auth.CSRF_FIELD] = TOKEN
    return client


@pytest.fixture
def admin(app):
    client = app.test_client()
    with client.session_transaction() as session:
        session[auth.CSRF_FIELD] = TOKEN
        session['admin_id'] = 1
        session['admin_name'] = 'joao'
    return client


def form(**fields) -> dict:
    return {auth.CSRF_FIELD: TOKEN} | fields


def article_form(**fields) -> dict:
    return form(
        markdown=(io.BytesIO(MARKDOWN), 'artigo.md'),
        images=[(io.BytesIO(png()), 'Figura 1.png')],
        **fields,
    )


def flashes(client) -> list[tuple[str, str]]:
    with client.session_transaction() as session:
        return session.get('_flashes', [])


# Caching and headers


def assert_private(response):
    assert response.headers['Cache-Control'] == 'private, no-store'
    assert response.headers['X-Robots-Tag'] == 'noindex'
    assert response.headers['X-Frame-Options'] == 'DENY'
    assert 'Vercel-CDN-Cache-Control' not in response.headers
    assert 'ETag' not in response.headers


@pytest.mark.parametrize(
    'path', ['/admin/login', '/admin', '/admin/articles/new', '/admin/nothing']
)
def test_admin_responses_are_never_cached_when_signed_out(anonymous, path):
    assert_private(anonymous.get(path))


@pytest.mark.parametrize(
    'path',
    ['/admin', '/admin/articles/new', '/admin/articles/7', '/admin/articles/7/delete'],
)
def test_admin_pages_are_never_cached_when_signed_in(admin, path):
    response = admin.get(path)

    assert response.status_code == 200
    assert_private(response)


def test_admin_posts_are_never_cached(admin):
    assert_private(admin.post('/admin/articles/new', data=form()))


def test_public_pages_stay_public_and_set_no_cookie(anonymous):
    response = anonymous.get('/articles')

    assert response.headers['Cache-Control'].startswith('public')
    assert 'Vercel-CDN-Cache-Control' in response.headers
    assert 'Set-Cookie' not in response.headers


def test_a_path_that_only_starts_like_admin_is_public(anonymous):
    response = anonymous.get('/administrator')

    assert response.status_code == 404
    assert response.headers.get('X-Robots-Tag') is None


# Signing in


@pytest.mark.parametrize(
    'path',
    ['/admin', '/admin/articles/new', '/admin/articles/7', '/admin/articles/7/delete'],
)
def test_every_page_redirects_to_login_when_signed_out(anonymous, path):
    response = anonymous.get(path)

    assert response.status_code == 302
    assert response.headers['Location'] == '/admin/login'


@pytest.mark.parametrize(
    'path', ['/admin/articles/new', '/admin/articles/7', '/admin/articles/7/delete']
)
def test_posts_redirect_to_login_when_signed_out(anonymous, articles, path):
    response = anonymous.post(path, data=form())

    assert response.headers['Location'] == '/admin/login'
    assert articles.saved == [] and articles.deleted == []


def test_right_password_signs_in(anonymous):
    response = anonymous.post(
        '/admin/login', data=form(username='joao', password=PASSWORD)
    )

    assert response.headers['Location'] == '/admin'
    with anonymous.session_transaction() as session:
        assert session['admin_id'] == 1
        assert session.permanent


def test_signing_in_starts_a_fresh_session(anonymous):
    with anonymous.session_transaction() as session:
        session['planted'] = 'value'

    anonymous.post('/admin/login', data=form(username='joao', password=PASSWORD))

    with anonymous.session_transaction() as session:
        assert 'planted' not in session


def test_session_cookie_flags(anonymous):
    anonymous.post('/admin/login', data=form(username='joao', password=PASSWORD))

    cookie = anonymous.get_cookie('session')
    assert cookie.http_only
    assert cookie.same_site == 'Lax'


def test_session_cookie_is_secure_on_vercel(monkeypatch):
    monkeypatch.setattr(settings, 'ON_VERCEL', True)
    monkeypatch.setattr(settings, 'SECRET_KEY', 'x' * 64)

    assert create_app().config['SESSION_COOKIE_SECURE'] is True


def test_session_lasts_eight_hours(app):
    assert app.config['PERMANENT_SESSION_LIFETIME'].total_seconds() == 8 * 3600


@pytest.mark.parametrize(
    ('username', 'password'), [('joao', 'wrong password'), ('nobody', PASSWORD)]
)
def test_wrong_credentials_get_the_same_answer(anonymous, username, password):
    response = anonymous.post(
        '/admin/login', data=form(username=username, password=password)
    )

    assert response.status_code == 401
    assert auth.WRONG_CREDENTIALS in response.text
    with anonymous.session_transaction() as session:
        assert 'admin_id' not in session


def test_wrong_passwords_lock_the_account(anonymous):
    for _ in range(settings.ADMIN_MAX_ATTEMPTS):
        anonymous.post('/admin/login', data=form(username='joao', password='nope'))

    response = anonymous.post(
        '/admin/login', data=form(username='joao', password=PASSWORD)
    )

    assert response.status_code == 401
    assert 'Too many wrong attempts' in response.text
    with anonymous.session_transaction() as session:
        assert 'admin_id' not in session


def test_a_right_password_resets_the_count(anonymous, users):
    anonymous.post('/admin/login', data=form(username='joao', password='nope'))
    anonymous.post('/admin/login', data=form(username='joao', password=PASSWORD))

    assert users.failures == 0


def test_signing_out_clears_the_session(admin):
    response = admin.post('/admin/logout', data=form())

    assert response.headers['Location'] == '/admin/login'
    with admin.session_transaction() as session:
        assert 'admin_id' not in session
    assert admin.get('/admin').status_code == 302


def test_login_page_sends_a_signed_in_admin_on(admin):
    assert admin.get('/admin/login').headers['Location'] == '/admin'


def test_secret_key_is_required_on_vercel(monkeypatch):
    monkeypatch.setattr(settings, 'ON_VERCEL', True)
    monkeypatch.setattr(settings, 'SECRET_KEY', None)

    with pytest.raises(RuntimeError, match='SECRET_KEY'):
        create_app()


# CSRF


@pytest.mark.parametrize('token', [None, '', 'wrong-token'])
@pytest.mark.parametrize(
    'path',
    [
        '/admin/login',
        '/admin/logout',
        '/admin/articles/new',
        '/admin/articles/7',
        '/admin/articles/7/delete',
    ],
)
def test_posts_without_the_right_csrf_token_are_refused(admin, articles, path, token):
    data = {} if token is None else {auth.CSRF_FIELD: token}

    response = admin.post(path, data=data)

    assert response.status_code == 400
    assert 'did not come from this site' in response.text
    assert articles.saved == [] and articles.deleted == []
    assert 7 in articles.by_id


def test_csrf_is_refused_when_the_session_has_no_token(app):
    client = app.test_client()

    response = client.post(
        '/admin/login',
        data={auth.CSRF_FIELD: '', 'username': 'joao', 'password': PASSWORD},
    )

    assert response.status_code == 400


def test_forms_carry_the_sessions_token(admin):
    assert f'value="{TOKEN}"' in admin.get('/admin/articles/new').text


# Listing and deleting


def test_list_shows_articles_with_their_links(admin):
    page = admin.get('/admin').text

    assert 'Old title' in page
    assert 'href="/admin/articles/7"' in page
    assert 'href="/articles/old"' in page


def test_delete_asks_first(admin, articles):
    page = admin.get('/admin/articles/7/delete').text

    assert 'Delete "Old title"?' in page
    assert articles.deleted == []


def test_delete(admin, articles):
    response = admin.post('/admin/articles/7/delete', data=form())

    assert response.headers['Location'] == '/admin'
    assert articles.deleted == [7]


@pytest.mark.parametrize('path', ['/admin/articles/99', '/admin/articles/99/delete'])
def test_unknown_article_is_404(admin, path):
    assert admin.get(path).status_code == 404


# Publishing


def test_publish_from_markdown_and_images(admin, articles, uploader):
    response = admin.post('/admin/articles/new', data=article_form())

    assert response.status_code == 302
    row = articles.saved[-1]
    assert row['title'] == 'Axiomas da aritmetica'
    assert row['slug'] == 'axiomas-da-aritmetica'
    assert row['description'] == 'Os conjuntos numericos.'
    assert row['tags'] == ['matematica', 'axiomas']
    assert row['created_at'] == datetime(2026, 11, 2, 12, tzinfo=UTC)
    assert row['has_math'] is True

    pathname, content_type = uploader.calls[0]
    assert pathname.startswith('images/article/axiomas-da-aritmetica/figura-1-')
    assert content_type == 'image/png'
    assert f'![Figura]({BLOB_URL}/{pathname}){{width=40 height=20}}' in row['body_md']

    article_id = max(articles.by_id)
    assert response.headers['Location'] == f'/admin/articles/{article_id}'
    assert ('success', 'Saved. The site shows the change within 5 minutes.') in flashes(
        admin
    )


def test_saving_stores_the_whole_render(admin, articles):
    admin.post('/admin/articles/new', data=article_form())

    row = articles.saved[-1]
    result = render(row['body_md'])
    assert row['body_text'] == result.text
    assert row['body_html'] == result.html
    assert row['toc'] == result.toc
    assert row['word_count'] == result.word_count
    assert 'search' not in row
    assert 'content' not in row


def test_form_values_win_over_the_front_matter(admin, articles):
    admin.post(
        '/admin/articles/new',
        data=article_form(
            title='Typed title',
            slug='typed-slug',
            description='Typed',
            tags='Physics, PHYSICS, Math',
            date='2026-12-01',
        ),
    )

    row = articles.saved[-1]
    assert row['title'] == 'Typed title'
    assert row['slug'] == 'typed-slug'
    assert row['description'] == 'Typed'
    assert row['tags'] == ['physics', 'math']
    assert row['created_at'] == datetime(2026, 12, 1, 12, tzinfo=UTC)


def test_cover_image(admin, articles):
    data = article_form()
    data['cover'] = (io.BytesIO(png((1200, 630))), 'capa.png')

    admin.post('/admin/articles/new', data=data)

    row = articles.saved[-1]
    assert row['image_url'].startswith(
        f'{BLOB_URL}/images/article/axiomas-da-aritmetica/capa-'
    )
    assert (row['image_width'], row['image_height']) == (1200, 630)


def test_missing_images_and_a_draft_status_are_warnings(admin, articles):
    draft = MARKDOWN.replace(b'status: pronto', b'status: rascunho')

    response = admin.post(
        '/admin/articles/new',
        data=form(markdown=(io.BytesIO(draft), 'artigo.md')),
    )

    assert response.status_code == 302
    assert '![Figura](<imagens/Figura 1.png>)' in articles.saved[-1]['body_md']
    messages = [
        message for category, message in flashes(admin) if category == 'warning'
    ]
    assert any('imagens/Figura 1.png' in message for message in messages)
    assert any('status: rascunho' in message for message in messages)


def test_a_long_description_is_a_warning(admin, articles):
    admin.post('/admin/articles/new', data=article_form(description='x' * 200))

    assert articles.saved
    assert any('200 characters' in message for _, message in flashes(admin))


def test_markdown_is_required_for_a_new_article(admin, articles):
    response = admin.post('/admin/articles/new', data=form(title='No file'))

    assert response.status_code == 400
    assert 'Choose the article&#39;s .md file.' in response.text
    assert articles.saved == []


def test_a_file_that_is_not_an_image_stops_the_save(admin, articles, uploader):
    data = article_form()
    data['images'] = [
        (io.BytesIO(png()), 'Figura 1.png'),
        (io.BytesIO(b'<svg/>'), 'x.png'),
    ]

    response = admin.post('/admin/articles/new', data=data)

    assert response.status_code == 400
    assert 'x.png is not a readable image' in response.text
    assert uploader.calls == []
    assert articles.saved == []


def test_a_slug_in_use_stops_the_save(admin, articles, uploader):
    response = admin.post('/admin/articles/new', data=article_form(slug='old'))

    assert response.status_code == 400
    assert 'already uses the slug &#34;old&#34;' in response.text
    assert uploader.calls == []
    assert articles.saved == []


def test_a_slug_race_is_caught(admin, articles, monkeypatch):
    def collide(_fields):
        raise UniqueViolation()

    monkeypatch.setattr(articles, 'create', collide)

    response = admin.post('/admin/articles/new', data=article_form())

    assert response.status_code == 400
    assert 'already uses the slug' in response.text


def test_bad_slug_and_empty_body(admin):
    response = admin.post(
        '/admin/articles/new',
        data=form(
            markdown=(io.BytesIO(b'---\ntitulo: X\n---\n\n'), 'artigo.md'),
            slug='Not A Slug',
        ),
    )

    assert response.status_code == 400
    assert 'lowercase letters, digits and dashes' in response.text
    assert 'no text after the front matter' in response.text


def test_markdown_must_be_utf8(admin):
    response = admin.post(
        '/admin/articles/new',
        data=form(markdown=(io.BytesIO('título'.encode('latin-1')), 'a.md'), title='T'),
    )

    assert response.status_code == 400
    assert 'not UTF-8' in response.text


def test_failed_upload_saves_nothing(admin, articles, monkeypatch):
    def broken(*_args):
        raise ConnectionError('Blob is down')

    monkeypatch.setattr(website.admin, 'uploader', broken)

    response = admin.post('/admin/articles/new', data=article_form())

    assert response.status_code == 502
    assert 'Vercel Blob failed' in response.text
    assert articles.saved == []


def test_too_large_an_upload_gets_a_clear_answer(app, admin):
    app.config['MAX_CONTENT_LENGTH'] = 1000

    response = admin.post(
        '/admin/articles/new',
        data=form(markdown=(io.BytesIO(b'x' * 5000), 'artigo.md')),
    )

    assert response.status_code == 413
    assert 'add the rest through Edit' in response.text
    assert_private(response)


# Editing


def test_edit_form_is_prefilled(admin):
    page = admin.get('/admin/articles/7').text

    assert 'value="Old title"' in page
    assert 'value="old"' in page
    assert 'value="physics"' in page
    assert 'value="2026-01-05"' in page
    assert 'Still without an image: imagens/b.png' in page


def test_edit_without_a_new_file_keeps_the_text_and_adds_images(
    admin, articles, uploader
):
    response = admin.post(
        '/admin/articles/7',
        data=form(
            title='Old title',
            slug='old',
            description='Old description',
            tags='physics',
            date='2026-01-05',
            images=[(io.BytesIO(png((10, 10))), 'b.png')],
        ),
    )

    assert response.headers['Location'] == '/admin/articles/7'
    row = articles.saved[-1]
    pathname = uploader.calls[0][0]
    assert f'![b]({BLOB_URL}/{pathname}){{width=10 height=10}}' in row['body_md']
    assert 'figura-1-0123456789ab.png){width=40 height=20}' in row['body_md']
    # Same date: the exact time stays, and with it the order of the list.
    assert row['created_at'] == CREATED
    # No new cover: the old one stays.
    assert row['image_url'] == stored_article()['image_url']
    assert (row['image_width'], row['image_height']) == (1200, 630)


def test_a_new_file_reuses_images_uploaded_before(admin, articles, uploader):
    admin.post(
        '/admin/articles/7',
        data=form(
            markdown=(io.BytesIO(MARKDOWN), 'artigo.md'),
            title='Old title',
            slug='old',
            date='2026-01-05',
        ),
    )

    row = articles.saved[-1]
    assert uploader.calls == []
    assert (
        f'![Figura]({BLOB_URL}/images/article/old/figura-1-0123456789ab.png)'
        '{width=40 height=20}' in row['body_md']
    )
    assert '## Introducao' in row['body_md']


def test_changing_the_date_moves_the_article(admin, articles):
    admin.post(
        '/admin/articles/7',
        data=form(title='Old title', slug='old', date='2025-06-30'),
    )

    assert articles.saved[-1]['created_at'] == datetime(2025, 6, 30, 12, tzinfo=UTC)


def test_an_article_may_keep_its_own_slug(admin):
    response = admin.post('/admin/articles/7', data=form(title='Old title', slug='old'))

    assert response.status_code == 302


def test_editing_an_article_without_markdown_needs_a_file(admin, articles):
    articles.by_id[7]['body_md'] = None

    response = admin.post('/admin/articles/7', data=form(title='Old title', slug='old'))

    assert response.status_code == 400
    assert '.md file' in response.text
