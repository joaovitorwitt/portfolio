from datetime import UTC, datetime

import pytest

import settings
import website.db
import website.views
from website import create_app
from website.search import MARK_END, MARK_START

SITE_URL = 'https://site.test'
BLOB_URL = 'https://store1.public.blob.vercel-storage.com'
CREATED_AT = datetime(2024, 10, 12, 15, 30, tzinfo=UTC)


def make_content(slug: str, kind: str = 'article', **overrides) -> dict:
    """A row shaped like ContentRepository returns, with every column present."""
    return {
        'id': 1,
        'kind': kind,
        'title': f'Title of {slug}',
        'slug': slug,
        'description': f'Description of {slug}',
        'content': f'<p>Body of {slug}</p>',
        'body_html': None,
        'has_math': False,
        'toc': [],
        'word_count': 0,
        'image_url': f'{BLOB_URL}/images/{kind}/{slug}/abc123.png',
        'image_width': 1000,
        'image_height': 500,
        'repo_url': None,
        'tags': ['physics'],
        'created_at': CREATED_AT,
        'updated_at': overrides.get('created_at', CREATED_AT),
    } | overrides


class FakeRepository:
    """Same interface as ContentRepository, backed by a list."""

    def __init__(self, rows: list[dict]):
        self.rows = rows

    def search(self, kind=None, tag=None, limit=50, offset=0) -> list[dict]:
        rows = [
            row
            for row in self.rows
            if (kind is None or row['kind'] == kind)
            and (tag is None or tag in row['tags'])
        ]
        rows.sort(key=lambda row: row['created_at'], reverse=True)
        return rows[offset : offset + limit]

    def search_text(self, kind, query, tag=None, limit=50, offset=0) -> list[dict]:
        """
        A stand-in for Postgres: a title match comes first, and a match in
        `body_text` (only these fake rows have it) brings a marked snippet.
        """
        self.searched = (kind, query, tag)
        needle = query.lower()
        found = []
        for row in self.search(kind=kind, tag=tag, limit=1000):
            body = row.get('body_text', '')
            if needle in row['title'].lower():
                found.append((0, row | {'snippet': None}))
            elif needle in body.lower():
                start = body.lower().index(needle)
                marked = (
                    body[:start]
                    + MARK_START
                    + body[start : start + len(needle)]
                    + MARK_END
                    + body[start + len(needle) :]
                )
                found.append((1, row | {'snippet': marked}))

        found.sort(key=lambda pair: pair[0])
        return [row for _, row in found][offset : offset + limit]

    def tags(self, kind: str) -> list[str]:
        return sorted(
            {tag for row in self.rows if row['kind'] == kind for tag in row['tags']}
        )

    def get_by_slug(self, kind: str, slug: str) -> dict | None:
        for row in self.rows:
            if row['kind'] == kind and row['slug'] == slug:
                return row

        return None

    def adjacent(self, kind: str, created_at: datetime) -> dict:
        rows = sorted(
            (row for row in self.rows if row['kind'] == kind),
            key=lambda row: row['created_at'],
        )
        older = [row for row in rows if row['created_at'] < created_at]
        newer = [row for row in rows if row['created_at'] > created_at]
        return {
            'previous': older[-1] if older else None,
            'next': newer[0] if newer else None,
        }


@pytest.fixture(autouse=True)
def no_real_database(monkeypatch):
    """
    The local .env points at production, so every test runs with connections
    disabled. A test that reaches for the real pool fails instead of touching it.
    """

    def refuse():
        pytest.fail('a test tried to open a real database connection')

    monkeypatch.setattr(website.db, 'get_pool', refuse)


@pytest.fixture(autouse=True)
def no_real_cache_purge(monkeypatch):
    """
    The local .env may hold a real Vercel token. Without one, website.cache
    refuses before opening any connection, so no test can clear the live cache.
    """
    monkeypatch.setattr(settings, 'VERCEL_API_TOKEN', None)
    monkeypatch.setattr(settings, 'VERCEL_PROJECT_ID', None)
    monkeypatch.setattr(settings, 'VERCEL_TEAM_ID', None)


@pytest.fixture(autouse=True)
def fixed_site_url(monkeypatch):
    monkeypatch.setattr(settings, 'SITE_URL', SITE_URL)


@pytest.fixture
def rows() -> list[dict]:
    return [
        make_content(
            'newest',
            title='Newest article',
            created_at=datetime(2025, 3, 1, tzinfo=UTC),
        ),
        make_content(
            'middle',
            title='Middle article',
            created_at=datetime(2024, 6, 1, tzinfo=UTC),
        ),
        make_content(
            'oldest',
            title='Oldest article',
            tags=['computer science'],
            created_at=datetime(2023, 1, 1, tzinfo=UTC),
        ),
        make_content('a-project', kind='project', title='A project', tags=['python']),
    ]


@pytest.fixture
def client(monkeypatch, rows):
    monkeypatch.setattr(website.views, 'repository', FakeRepository(rows))
    return create_app().test_client()
