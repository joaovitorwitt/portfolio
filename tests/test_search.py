import pytest

from website.search import (
    MARK_END,
    MARK_START,
    MAX_QUERY_LENGTH,
    SearchTerms,
    clean_query,
    highlight,
    split_terms,
)


@pytest.mark.parametrize(
    ('raw', 'cleaned'),
    [
        (None, ''),
        ('', ''),
        ('   ', ''),
        ('  newton  ', 'newton'),
        ('newton\t\n laws', 'newton laws'),
    ],
)
def test_queries_are_trimmed_and_collapsed(raw, cleaned):
    assert clean_query(raw) == cleaned


def test_a_long_query_is_cut_to_the_limit():
    cleaned = clean_query('a' * 1024)

    assert cleaned == 'a' * MAX_QUERY_LENGTH


def test_cutting_never_leaves_a_trailing_space():
    assert not clean_query('word ' * 40).endswith(' ')


@pytest.mark.parametrize(
    ('query', 'terms'),
    [
        ('kinem', SearchTerms('', 'kinem')),
        ('newton laws', SearchTerms('newton', 'laws')),
        ('newton or kinem', SearchTerms('newton', 'kinem', either=True)),
        ('Newton OR kinem', SearchTerms('Newton', 'kinem', either=True)),
        ('física', SearchTerms('', 'física')),
    ],
)
def test_the_last_plain_word_is_matched_as_a_prefix(query, terms):
    assert split_terms(query) == terms


@pytest.mark.parametrize(
    'query',
    [
        '"design patterns"',
        '"design patt',
        'physics -units',
        'newton or',
        "o'neil",
        'c++',
        'snake_case',
        r'back\slash',
        '100%',
    ],
)
def test_phrases_exclusions_and_odd_words_get_no_prefix(query):
    assert split_terms(query) == SearchTerms(query, None)


def test_highlight_escapes_the_text_and_keeps_only_marks():
    snippet = f'a <script>alert(1)</script> & {MARK_START}Newton{MARK_END} "laws"'

    html = highlight(snippet)

    assert html == (
        'a &lt;script&gt;alert(1)&lt;/script&gt; &amp; <mark>Newton</mark> '
        '&#34;laws&#34;'
    )


@pytest.mark.parametrize('snippet', [None, '', 'The start of a body, no match.'])
def test_a_snippet_without_a_match_is_dropped(snippet):
    assert highlight(snippet) is None
