from datetime import UTC, datetime

import pytest

import settings
import website.db
from website.db import CONTENT_COLUMNS, ContentRepository, build_conninfo


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


def test_adjacent_looks_both_ways_with_bound_parameters(connection):
    created_at = datetime(2024, 1, 1, tzinfo=UTC)

    result = ContentRepository().adjacent('article', created_at)

    (older, older_params), (newer, newer_params) = connection.calls
    assert 'created_at < %s ORDER BY created_at DESC LIMIT 1' in older
    assert 'created_at > %s ORDER BY created_at ASC LIMIT 1' in newer
    assert older_params == newer_params == ('article', created_at)
    assert set(result) == {'previous', 'next'}


def test_body_md_stays_out_of_what_pages_read():
    assert 'body_md' not in CONTENT_COLUMNS
    assert {'body_html', 'has_math', 'toc', 'word_count', 'updated_at'} <= set(
        CONTENT_COLUMNS
    )


class SequencedConnection(FakeConnection):
    """Answers each statement with the next batch of rows."""

    def __init__(self, *batches):
        super().__init__([])
        self.batches = list(batches)

    def execute(self, query, params):
        self.calls.append((query, params))
        return FakeResult(self.batches.pop(0) if self.batches else [])


@pytest.fixture
def sequenced(monkeypatch):
    def install(*batches):
        fake = SequencedConnection(*batches)
        monkeypatch.setattr(website.db, 'get_pool', lambda: fake)
        return fake

    return install


def test_search_text_ranks_matches_and_asks_for_a_snippet(sequenced):
    fake = sequenced([{'slug': 'found'}])

    rows = ContentRepository().search_text('article', 'newton laws', limit=5)

    query, params = fake.calls[0]
    assert rows == [{'slug': 'found'}]
    assert len(fake.calls) == 1
    assert 'search @@ q.tsquery' in query
    assert 'ORDER BY ts_rank_cd(search, q.tsquery) DESC, created_at DESC' in query
    assert "ts_headline('english', coalesce(body_text, '')" in query
    assert "websearch_to_tsquery('english', %(head)s) && " in query
    assert "to_tsquery('english', %(prefix)s || ':*')" in query
    assert 'ANY(tags)' not in query
    assert params['head'] == 'newton'
    assert params['prefix'] == 'laws'
    assert params['limit'] == 5


def test_search_text_or_before_the_last_word_widens_the_match(sequenced):
    fake = sequenced([{'slug': 'found'}])

    ContentRepository().search_text('article', 'newton or kinem')

    assert '%(head)s) || to_tsquery' in fake.calls[0][0]


def test_search_text_phrases_go_in_as_written(sequenced):
    fake = sequenced([{'slug': 'found'}])

    ContentRepository().search_text('article', '"design patterns"')

    query, params = fake.calls[0]
    assert 'to_tsquery(' not in query.replace('websearch_to_tsquery(', '')
    assert params['head'] == '"design patterns"'


def test_search_text_combines_with_a_tag(sequenced):
    fake = sequenced([{'slug': 'found'}])

    ContentRepository().search_text('article', 'newton', tag='physics')

    query, params = fake.calls[0]
    assert 'kind = %(kind)s AND %(tag)s = ANY(tags) AND search @@' in query
    assert params['tag'] == 'physics'


def test_search_text_falls_back_to_lookalike_titles(sequenced):
    fake = sequenced([], [{'slug': 'kinematics'}])

    rows = ContentRepository().search_text('article', 'kinmatics', tag='physics')

    fallback, params = fake.calls[1]
    assert rows == [{'slug': 'kinematics'}]
    assert 'extensions.word_similarity(%(query)s, title) > %(threshold)s' in fallback
    assert '%(tag)s = ANY(tags)' in fallback
    assert 'NULL AS snippet' in fallback
    assert params['query'] == 'kinmatics'


def test_search_text_skips_the_fallback_past_the_first_page(sequenced):
    fake = sequenced([])

    assert ContentRepository().search_text('article', 'kinmatics', offset=50) == []
    assert len(fake.calls) == 1


@pytest.mark.parametrize(
    'hostile', ["x'; DROP TABLE content; --", r'back\slash', '100% \' " :* & | !']
)
def test_search_text_binds_every_value(sequenced, hostile):
    fake = sequenced([], [])

    ContentRepository().search_text(hostile, hostile, tag=hostile)

    for query, params in fake.calls:
        assert hostile not in query
        assert 'DROP TABLE' not in query
        assert params['query'] == hostile
        assert params['tag'] == hostile


def test_tags_are_distinct_and_sorted_in_sql(connection):
    connection.rows = [{'tag': 'computer science'}, {'tag': 'physics'}]

    assert ContentRepository().tags('article') == ['computer science', 'physics']
    query, params = connection.calls[0]
    assert 'SELECT DISTINCT unnest(tags) AS tag' in query
    assert query.endswith('ORDER BY tag')
    assert params == ('article',)
