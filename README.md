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
  admin.py          the admin area under /admin
  auth.py           admin login: password hashes, lockout, session, CSRF
  publish.py        turns an uploaded artigo.md and its images into a row
  db.py             connection pool, ContentRepository and the admin's writes
  markdown.py       renders Markdown to safe HTML, when saving
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
./run.sh test             # pytest, never touches a database
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

## Articles

An article's source is the Markdown in `body_md`. Saving renders it once, through
`website/markdown.py`, into `body_html`, `has_math`, `toc`, `word_count` and
`body_text`, and
pages only read those, so rendering costs nothing per request. An article with no
`body_html` falls back to the legacy HTML in `content`.

The renderer is in `requirements.txt`, because the admin renders on save.

Besides CommonMark:

| Write | Get |
| --- | --- |
| `![alt](url "caption"){width=1920 height=1080}` | a figure with a caption; the size stops the page jumping as it loads |
| `$x_1$`, `$$ \frac{a}{b} $$` | MathML, which needs no script. A price like `$100` stays text |
| `::: quote` ... `— Author` ... `:::` | a pull quote, with a last line starting with `—` as its attribution |
| `::: note`, `::: warning` | a callout |
| ` ```python ` | code highlighted by Pygments, coloured by `code.modules.css` |
| tables, `~~gone~~`, `[^1]` footnotes | the usual |

Links starting with `http` open in a new tab with `rel="noopener"`. Everything is
sanitised with `nh3` against a fixed allow-list, raw HTML included, so nothing in
the Markdown can run a script. `## ` and `### ` headings get an id and a `#` link,
and a page with at least three of them shows a table of contents.

To convert the legacy HTML, or to render everything again after changing the
renderer:

```bash
python scripts/html_to_markdown.py --dry-run  # writes backups/markdown/, reads the database
python scripts/html_to_markdown.py --apply    # copies the table, then stores everything
python scripts/render_all.py --dry-run        # lists the rows that would change
python scripts/render_all.py --apply          # copies the table, then stores them
```

`html_to_markdown.py` stops without writing if any article loses a word, an
equation, an image, a link or bold text. Hand-written changes, such as captions
and formula images written out as TeX, are in `scripts/article_fixes.py`. Neither
`--apply` touches `content` or `updated_at`: rendering again isn't an edit.

## Admin

`/admin` is where articles are published, edited and deleted, without SQL.
Articles are written and reviewed in
[joaovitorwitt/articles](https://github.com/joaovitorwitt/articles); once one is
ready, upload its `artigo.md` together with the files from its `imagens/` folder.

- **Fields:** title, description, tags and date fill in from the front matter
  (`titulo`, `descricao`, `tags`, `data`). Anything typed in the form wins. The
  slug comes from the title. Tags are saved in lowercase.
- **Images:** each relative reference, such as `![x](imagens/x.png)`, is matched
  to a chosen file by name, uploaded to Blob and pointed at it with its size. A
  path with spaces must be written as `<imagens/a b.png>` or with `%20`. Images
  already uploaded are found again on a later edit, so re-uploading a corrected
  `artigo.md` doesn't need them a second time.
- **Saving** stores the whole render, as `render_all.py` does, and never writes
  the generated `search` column. A change shows up within the 5-minute cache.
- **Warnings, not errors:** images still missing, a `status` other than
  `pronto`, a description over 160 characters, an equation that didn't convert.
- **Limit:** Vercel refuses requests over 4.5 MB. Save with fewer images and add
  the rest through Edit.

Signing in uses the `admin_users` table (migration `006`): a username and a
scrypt password hash. Five wrong passwords lock the account for 15 minutes,
counted in the table so every function instance agrees. The session is Flask's
signed cookie (`SECRET_KEY`), lasts 8 hours, and every form carries a CSRF
token. Every response under `/admin` is `private, no-store` and `noindex`, and
never gets the CDN header.

To create the account, or set a new password and unlock it:

```bash
python scripts/create_admin.py   # asks for the username and password
```

## Search

`/articles?q=…` searches with Postgres full-text search, and `&tag=…` narrows the
list to one tag, with or without a query. Migration `005` adds:

- `body_text`, the plain prose that the renderer produces, without code or math.
- `search`, a generated `tsvector` that weights the title highest, then the
  description and tags, then `body_text`. It has a GIN index.
- `pg_trgm` and a trigram index on `title`. When nothing matches, titles close
  to the query are shown instead, so "kinmatics" still finds kinematics.

The query reads quoted phrases, `-word` and `or`, and the last word also matches
as a prefix, so "kinem" finds "kinematics". The SQL is in `website/db.py` and the
query handling in `website/search.py`.

The page is a plain GET form, so search works without JavaScript.
`public/js/search.js` fetches `?partial=1`, which returns only the results, and
swaps them in as you type. Filtered pages are `noindex`, and their canonical
link points at `/articles`. Each query string is its own CDN cache entry.

After changing the renderer, `scripts/render_all.py --apply` also refreshes
`body_text`, and with it the search index.

## Images

Originals live in a public Vercel Blob store, named
`images/<kind>/<slug>/<sha256-12>.<ext>`. The content hash makes each URL
immutable. On Vercel the `img_url` filter sends them through Vercel Image
Optimization (`/_vercel/image`, configured under `images` in `vercel.json`) for
resized AVIF/WebP copies. Locally that endpoint doesn't exist, so images load
straight from their Blob URLs and no Vercel service is needed.

Cover sizes are stored in `image_width` and `image_height`; inline images carry
theirs in the Markdown or legacy markup. Images uploaded through the admin keep
their file name: `images/article/<slug>/<name>-<sha256-12>.<ext>`. A new store means updating `remotePatterns` in
`vercel.json`.

To move images from Cloudinary (`pip` installs what these need with
`./run.sh install`):

```bash
python scripts/export_images.py             # backup to backups/images/, read-only
python scripts/migrate_images.py --dry-run  # print the changes, no writes
python scripts/migrate_images.py --apply    # upload, copy the table, rewrite it
```

`--apply` first copies `content` to `content_backup_<yyyymmdd>`, then rewrites
every row in one transaction, and rolls back if any Cloudinary URL is left.

## Deployment

Vercel deploys every push through its GitHub integration: `main` goes to
production, other branches to preview URLs. It detects the Flask app from
`app.py` with no build step. `vercel.json` pins the function to São Paulo
(`gru1`), next to the Supabase pooler, and keeps `public/`, `migrations/` and
`scripts/` out of the function bundle.

Project environment variables:

| Name | Value |
| --- | --- |
| `DATABASE_URL` | Supabase transaction pooler URI (port 6543) |
| `USE_TRANSACTION_POOLER` | `1` |
| `SITE_URL` | optional; defaults to the project's production domain |
| `BLOB_READ_WRITE_TOKEN` | Vercel Blob store token, set by connecting the store to the project; the admin uploads with it, and the scripts read it from the local `.env` |
| `SECRET_KEY` | 32+ random bytes that sign the admin session, for Production and Preview. Without it the app won't start on Vercel |

Pages are cached for 5 minutes by browsers (`Cache-Control`) and by Vercel's
CDN (`Vercel-CDN-Cache-Control`, which never reaches the browser), so a new
article shows up within about five minutes of being inserted.
