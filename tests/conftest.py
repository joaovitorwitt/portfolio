from datetime import UTC, datetime

import pytest

import settings
import website.db
import website.views
from website import create_app

SITE_URL = 'https://site.test'


def make_content(slug: str, kind: str = 'article', **overrides) -> dict:
    """A row shaped like ContentRepository returns, with every column present."""
    return {
        'id': 1,
        'kind': kind,
        'title': f'Title of {slug}',
        'slug': slug,
        'description': f'Description of {slug}',
        'content': f'<p>Body of {slug}</p>',
        'image_url': f'https://res.cloudinary.com/demo/image/upload/{slug}.png',
        'repo_url': None,
        'tags': ['physics'],
        'created_at': datetime(2024, 10, 12, 15, 30, tzinfo=UTC),
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

    def get_by_slug(self, kind: str, slug: str) -> dict | None:
        for row in self.rows:
            if row['kind'] == kind and row['slug'] == slug:
                return row

        return None


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
