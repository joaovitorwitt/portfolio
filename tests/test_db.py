import pytest

import settings
import website.db
from website.db import ContentRepository, build_conninfo


class FakeResult:
    def __init__(self, rows):
        self.rows = rows

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.rows[0] if self.rows else None


class FakeConnection:
    """Records each statement so tests can inspect the SQL and its parameters."""

    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def execute(self, query, params):
        self.calls.append((query, params))
        return FakeResult(self.rows)

    def connection(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture
def connection(monkeypatch):
    fake = FakeConnection([{'slug': 'found'}])
    monkeypatch.setattr(website.db, 'get_pool', lambda: fake)
    return fake


def test_search_without_filters_has_no_where_clause(connection):
    ContentRepository().search()

    query, params = connection.calls[0]
    assert 'WHERE' not in query
    assert query.endswith('ORDER BY created_at DESC LIMIT %s OFFSET %s')
    assert params == [50, 0]


def test_search_combines_kind_and_tag(connection):
    ContentRepository().search(kind='article', tag='physics', limit=3, offset=6)

    query, params = connection.calls[0]
    assert 'WHERE kind = %s AND %s = ANY(tags)' in query
    assert params == ['article', 'physics', 3, 6]


def test_values_never_reach_the_statement_text(connection):
    hostile = "x'; DROP TABLE content; --"

    ContentRepository().search(kind=hostile, tag=hostile)
    ContentRepository().get_by_slug(hostile, hostile)

    for query, params in connection.calls:
        assert 'DROP TABLE' not in query
        assert hostile in params


def test_get_by_slug_returns_the_row(connection):
    assert ContentRepository().get_by_slug('article', 'found') == {'slug': 'found'}
    assert connection.calls[0][1] == ('article', 'found')


def test_get_by_slug_returns_none_when_missing(connection):
    connection.rows = []

    assert ContentRepository().get_by_slug('article', 'missing') is None


def test_database_url_wins_over_individual_settings(monkeypatch):
    monkeypatch.setattr(settings, 'DATABASE_URL', 'postgresql://example/db')

    assert build_conninfo() == 'postgresql://example/db'


def test_conninfo_falls_back_to_individual_settings(monkeypatch):
    monkeypatch.setattr(settings, 'DATABASE_URL', None)
    monkeypatch.setattr(settings, 'DEFAULT_POSTGRES_HOST', 'db.local')
    monkeypatch.setattr(settings, 'DEFAULT_POSTGRES_PORT', 5433)

    conninfo = build_conninfo()

    assert 'host=db.local' in conninfo
    assert 'port=5433' in conninfo


def test_the_guard_stops_tests_reaching_the_real_database():
    with pytest.raises(pytest.fail.Exception):
        ContentRepository().search()
