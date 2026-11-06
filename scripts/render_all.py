"""
Renders every stored body_md again. Run it whenever website/markdown.py changes
what it produces. updated_at stays as it is: nobody edited the articles.

    python scripts/render_all.py --dry-run    # list what would change, no writes
    python scripts/render_all.py --apply      # back up the table, then store
"""

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from website.db import ContentMarkdown, get_pool  # noqa: E402
from website.markdown import MATH_ERROR_CLASS, render  # noqa: E402


def plan_updates(rows: list[dict]) -> list[dict]:
    """Only the rows whose stored output differs from a fresh render."""
    updates = []
    for row in rows:
        result = render(row['body_md'])
        fresh = {
            'body_html': result.html,
            'has_math': result.has_math,
            'toc': result.toc,
            'word_count': result.word_count,
        }
        if any(row[column] != value for column, value in fresh.items()):
            updates.append(
                {'id': row['id'], 'slug': row['slug'], 'body_md': row['body_md']}
                | fresh
            )

    return updates


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--dry-run', action='store_true', help='list changes only')
    mode.add_argument('--apply', action='store_true', help='back up and store')
    args = parser.parse_args()

    repository = ContentMarkdown()
    rows = repository.sources()
    updates = plan_updates(rows)

    for update in updates:
        print(f'  {update["slug"]}')

    print(f'{len(updates)} of {len(rows)} rows change')

    broken = [u['slug'] for u in updates if MATH_ERROR_CLASS in u['body_html']]
    if broken:
        print(f'aborting: an equation failed to convert in {broken}')
        return 1

    if args.dry_run:
        print('dry run, nothing written')
        return 0

    if updates:
        backup_table = f'content_backup_{datetime.now(UTC):%Y%m%d}'
        repository.apply(updates, backup_table)
        print(f'stored {len(updates)} rows, previous data in {backup_table}')

    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    finally:
        get_pool().close()
