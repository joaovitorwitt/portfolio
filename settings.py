import os

from dotenv import load_dotenv

load_dotenv()

# Vercel sets VERCEL=1 in every build and function environment.
ON_VERCEL = os.environ.get('VERCEL') == '1'

# Supabase hands you a single connection string. When it is set it wins over the
# individual POSTGRES_* vars below, which stay around for a local postgres.
DATABASE_URL = os.environ.get('DATABASE_URL')

DEFAULT_POSTGRES_HOST = os.environ.get('POSTGRES_HOST', 'localhost')
DEFAULT_POSTGRES_PORT = int(os.environ.get('POSTGRES_PORT', 5432))
DEFAULT_POSTGRES_USER = os.environ.get('POSTGRES_USER', 'postgres')
DEFAULT_POSTGRES_PASSWORD = os.environ.get('POSTGRES_PASSWORD', 'password')
DEFAULT_POSTGRES_DB = os.environ.get('POSTGRES_DB', 'postgres')

# Supabase requires TLS; a local postgres normally does not have it configured.
POSTGRES_SSLMODE = os.environ.get('POSTGRES_SSLMODE', 'prefer')

# Every function instance builds its own pool, so the real ceiling against
# Supabase is POOL_MAX_SIZE * live instances. A min of 0 means an idle instance
# holds no connection open.
POOL_MIN_SIZE = int(os.environ.get('POOL_MIN_SIZE', 0))
POOL_MAX_SIZE = int(os.environ.get('POOL_MAX_SIZE', 2))

# Supabase's transaction pooler (port 6543) cannot hold session-level prepared
# statements, so psycopg's automatic preparing has to be turned off there.
PREPARE_THRESHOLD = None if os.environ.get('USE_TRANSACTION_POOLER') else 5

CONTENT_KINDS = ('article', 'project')

# How long a page stays fresh. Articles are published rarely, so minutes are
# safe; a new post simply takes up to this long to appear.
CACHE_MAX_AGE = int(os.environ.get('CACHE_MAX_AGE', 300))

# Window after expiry where a cache may serve the stale copy while it refetches.
CACHE_STALE_WHILE_REVALIDATE = int(
    os.environ.get('CACHE_STALE_WHILE_REVALIDATE', 86400)
)
