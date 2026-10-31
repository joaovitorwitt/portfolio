import logging
from functools import lru_cache

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

import settings

log = logging.getLogger(__name__)


# Listed explicitly so a schema change cannot silently reshape what templates get.
CONTENT_COLUMNS = (
    'id',
    'kind',
    'title',
    'slug',
    'description',
    'content',
    'image_url',
    'repo_url',
    'tags',
    'created_at',
)

_SELECT = f'SELECT {", ".join(CONTENT_COLUMNS)} FROM content'


def build_conninfo() -> str:
    """
    Builds the libpq connection string. A DATABASE_URL (what Supabase hands you)
    wins over the individual POSTGRES_* settings.
    """
    if settings.DATABASE_URL:
        return settings.DATABASE_URL

    return (
        f'host={settings.DEFAULT_POSTGRES_HOST} '
        f'port={settings.DEFAULT_POSTGRES_PORT} '
        f'dbname={settings.DEFAULT_POSTGRES_DB} '
        f'user={settings.DEFAULT_POSTGRES_USER} '
        f'password={settings.DEFAULT_POSTGRES_PASSWORD} '
        f'sslmode={settings.POSTGRES_SSLMODE}'
    )


@lru_cache(maxsize=1)
def get_pool() -> ConnectionPool:
    """
    One pool per process, built lazily so importing this module never opens a
    socket.

    A function instance can sit frozen between requests long enough for the
    pooler to drop its side of an idle connection, so every checkout is checked
    first; a dead one is replaced instead of failing the request.
    """
    pool = ConnectionPool(
        conninfo=build_conninfo(),
        min_size=settings.POOL_MIN_SIZE,
        max_size=settings.POOL_MAX_SIZE,
        kwargs={
            'row_factory': dict_row,
            'prepare_threshold': settings.PREPARE_THRESHOLD,
        },
        check=ConnectionPool.check_connection,
        open=False,
    )
    pool.open()
    return pool


class ContentRepository:
    """
    Read-only access to the `content` table. Every value reaching SQL goes
    through a bound parameter; nothing is interpolated into the statement.
    """

    def search(
        self,
        kind: str | None = None,
        tag: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        clauses = []
        params: list = []

        if kind is not None:
            clauses.append('kind = %s')
            params.append(kind)

        if tag is not None:
            clauses.append('%s = ANY(tags)')
            params.append(tag)

        where = f' WHERE {" AND ".join(clauses)}' if clauses else ''

        # Ordering in SQL rather than in Python; the index on
        # (kind, created_at desc) serves this directly.
        query = f'{_SELECT}{where} ORDER BY created_at DESC LIMIT %s OFFSET %s'
        params.extend([limit, offset])

        with get_pool().connection() as conn:
            rows = conn.execute(query, params).fetchall()

        return rows

    def get_by_slug(self, kind: str, slug: str) -> dict | None:
        query = f'{_SELECT} WHERE kind = %s AND slug = %s'

        with get_pool().connection() as conn:
            row = conn.execute(query, (kind, slug)).fetchone()

        return row
