# portfolio

Source for [joaovitorwitt.com](https://www.joaovitorwitt.com): a Flask app that
server-renders every page with Jinja, reads articles and projects from Supabase
Postgres, and deploys to Vercel. It replaces the old Next.js front end
(`websitefront`) and Flask JSON API (`website-backend`).

## Layout

```
app.py              Vercel entrypoint: exposes `app`
settings.py         configuration, read from the environment / .env
website/
  __init__.py       create_app()
  views.py          page routes, rss.xml, sitemap.xml
  db.py             connection pool + ContentRepository
  templates/        Jinja templates
public/             static files (css, js, img, resume), served at the site root
migrations/         SQL schema, applied by hand in order
scripts/            one-off maintenance scripts
```

Static files live in `public/` rather than Flask's `static/`, because Vercel
serves `public/` straight from its CDN. In local development Flask mounts the
same folder at `/`, so asset URLs are the same in both places.

## Local development

Needs Python 3.12+ (Vercel runs 3.12, pinned in `.python-version`).

```bash
python -m venv .venv
./run.sh install          # runtime + dev requirements into .venv
cp .env.example .env      # then fill in DATABASE_URL
./run.sh server           # http://localhost:8000
./run.sh lint             # ruff check + format check
```

`run.sh` uses `.venv` automatically, so the venv doesn't need to be activated.
On Windows, run it from Git Bash.

## Database

There is one `content` table holding both articles (`kind = 'article'`) and
projects (`kind = 'project'`). See `migrations/`. All queries go through
`ContentRepository` in `website/db.py` and use bound parameters.

On Vercel, `DATABASE_URL` must be Supabase's **transaction pooler** URI
(port 6543) with `USE_TRANSACTION_POOLER=1`, which turns off psycopg's prepared
statements. Each function instance keeps a small pool (`POOL_MAX_SIZE`,
default 2).

To import articles from a JSON export:

```bash
python scripts/import_articles.py --dry-run
python scripts/import_articles.py
```

## Deployment

Vercel detects the Flask app from `app.py` with zero configuration. Set
`DATABASE_URL` and `USE_TRANSACTION_POOLER` in the project's environment
variables.
