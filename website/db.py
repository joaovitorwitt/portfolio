import logging
from functools import lru_cache

from psycopg import sql
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
    'image_width',
    'image_height',
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


class ContentImages:
    """
    Write access for the image migration in scripts/, kept apart from
    ContentRepository so that the site itself stays read-only.
    """

    def references(self) -> list[dict]:
        """
        What the backup needs. It runs before migration 003, so it can't ask for
        the size columns.
        """
        # A stable order, so the first row using a shared image always names it.
        query = 'SELECT kind, slug, image_url, content FROM content ORDER BY kind, slug'

        with get_pool().connection() as conn:
            return conn.execute(query).fetchall()

    def rows(self) -> list[dict]:
        query = (
            'SELECT id, kind, slug, image_url, image_width, image_height, content '
            'FROM content ORDER BY kind, slug'
        )

        with get_pool().connection() as conn:
            return conn.execute(query).fetchall()

    def apply(self, updates: list[dict], backup_table: str) -> None:
        """
        Copies the table, applies every update and checks that no Cloudinary URL
        is left, all in one transaction: any failure rolls the whole thing back.
        """
        backup = sql.Identifier(backup_table)
        update = """
            UPDATE content
            SET image_url = %(image_url)s,
                image_width = %(image_width)s,
                image_height = %(image_height)s,
                content = %(content)s
            WHERE id = %(id)s
        """
        remaining = """
            SELECT count(*) AS remaining FROM content
            WHERE image_url LIKE %(pattern)s OR content LIKE %(pattern)s
        """

        with get_pool().connection() as conn:
            conn.execute(
                sql.SQL('CREATE TABLE IF NOT EXISTS {} AS TABLE content').format(backup)
            )
            # Tables in Supabase's public schema are reachable through its REST
            # API. The script connects as the owner, which RLS does not restrict.
            conn.execute(
                sql.SQL('ALTER TABLE {} ENABLE ROW LEVEL SECURITY').format(backup)
            )

            for row in updates:
                conn.execute(update, row)

            left = conn.execute(remaining, {'pattern': '%cloudinary%'}).fetchone()
            if left['remaining']:
                raise RuntimeError(
                    f'{left["remaining"]} rows still reference Cloudinary, rolled back'
                )
