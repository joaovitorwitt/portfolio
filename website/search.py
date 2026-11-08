"""
The Python side of article search: cleaning what the visitor typed, picking the
word to match as a prefix, and turning Postgres's highlighted snippet into safe
HTML. The SQL itself is in website/db.py.
"""

import re
from typing import NamedTuple

from markupsafe import Markup, escape

MAX_QUERY_LENGTH = 100

# ts_headline marks matches with these. They're private-use characters, so they
# can't come from an article, and a snippet without them matched nothing.
MARK_START = ''
MARK_END = ''

_WORD = re.compile(r'[^\W_]+')


class SearchTerms(NamedTuple):
    """
    The query split for websearch_to_tsquery: `head` goes in as written, and
    `prefix`, when there is one, matches any word starting with it. `either` is
    true when the visitor typed "or" before that last word.
    """

    head: str
    prefix: str | None
    either: bool = False


def clean_query(raw: str | None) -> str:
    """Collapses whitespace and caps the length. Empty means no search."""
    return ' '.join((raw or '').split())[:MAX_QUERY_LENGTH].strip()


def split_terms(query: str) -> SearchTerms:
    """
    Searching for "kinem" should already find "kinematics", but
    websearch_to_tsquery has no prefix syntax. The last word gets a prefix match
    of its own unless it's part of a quoted phrase, excluded with "-", or not a
    plain word.
    """
    words = query.split(' ')
    last = words[-1] if words else ''

    in_phrase = query.count('"') % 2 == 1 or last.endswith('"')
    if in_phrase or not _WORD.fullmatch(last) or last.lower() == 'or':
        return SearchTerms(query, None)

    head = words[:-1]
    either = bool(head) and head[-1].lower() == 'or'
    if either:
        head = head[:-1]

    return SearchTerms(' '.join(head), last, either)


def highlight(snippet: str | None) -> Markup | None:
    """
    Escapes the snippet and only then adds <mark>, so nothing from the article
    reaches the page as markup. A snippet without a match is no use as one.
    """
    if not snippet or MARK_START not in snippet:
        return None

    return Markup(
        str(escape(snippet)).replace(MARK_START, '<mark>').replace(MARK_END, '</mark>')
    )
