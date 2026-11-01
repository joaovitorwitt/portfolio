# Portfolio

Flask/Jinja site on Vercel with Supabase Postgres. `README.md` covers the setup.

## Commands

Run from Git Bash. `run.sh` finds `.venv` by itself.

- `./run.sh test`: pytest. Never touches a database.
- `./run.sh lint`: ruff check and format check.
- `gh` isn't on PATH: use `"/c/Program Files/GitHub CLI/gh.exe"`.

## Production safety

The local `.env` points at the **production** database, and every push to `main`
deploys to production.

- Never run a migration, data script or any other write against the database
  without an explicit yes from the owner in this conversation. Reads are fine.
- Back up before any data change, and offer a dry run first.
- Never print, commit or ask for secrets in chat. The owner adds them to `.env`
  and the Vercel dashboard.
- Tests must stay offline. `tests/conftest.py` fails any test that opens a real
  connection; keep that guard.

## Implementing an issue

Features are built one at a time from GitHub issues, in this order: #1 images,
#2 Markdown, #3 search, #4 admin. Each issue holds the plan and acceptance
criteria. Sessions are cleared between features, so read the issue first and
check `git log` and merged PRs for what earlier features changed.

1. Branch from an up-to-date `main`: `feature/<issue>-<short-name>`.
2. Implement in small commits, adding tests for new behaviour.
3. `./run.sh test` and `./run.sh lint` must pass.
4. Push and open a PR that closes the issue. List under **Manual steps** anything
   the owner must do: secrets, dashboard setup, migrations, data scripts.
5. Stop there. Only the owner decides when to merge.

The owner often works from a phone: batch questions, keep them answerable in one
line, and list anything that needs the desktop up front.

## Conventions

- Migrations are numbered and additive: `003` images, `004` Markdown, `005`
  search, `006` admin. Removing anything goes in a later migration, after a backup.
- A migration must run on production before the PR that depends on it merges.
- All SQL lives in `website/db.py` and uses bound parameters.
- Dependencies are pinned. Runtime ones go in `requirements.txt` and dev ones in
  `requirements-dev.txt`. Don't add a `pyproject.toml`: Vercel would read it as a
  dependency manifest.
- Static files live in `public/`, served from the site root.
