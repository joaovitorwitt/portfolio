import pytest
from psycopg.types.json import Jsonb

import website.db
from scripts import article_fixes, html_to_markdown, render_all
from scripts.html_to_markdown import (
    apply_fixes,
    conversion_problems,
    final_problems,
    plan_updates,
    to_markdown,
)
from website.db import ContentMarkdown
from website.markdown import render

BLOB = 'https://store1.public.blob.vercel-storage.com/images/article/x'
CAPTIONED = 'cb5b772bf4e5'
FORMULA = '68cbe1481300'


def test_br_between_blocks_leaves_no_trace():
    markdown = to_markdown('<p>One.</p><br>\n    <br>\n<p>Two.</p>')

    assert markdown == 'One.\n\nTwo.\n'


def test_h3_becomes_h2():
    assert to_markdown('<h3>A section </h3>') == '## A section\n'


def test_quote_element_becomes_a_container():
    markdown = to_markdown(
        '<quote>\n<p class="quote">"Wise."</p>\n'
        '<p class="quote-author">— Someone</p>\n</quote>'
    )

    assert markdown == '::: quote\n"Wise."\n\n— Someone\n:::\n'


def test_a_quote_and_author_opening_an_article_become_a_container():
    markdown = to_markdown('<p>“Wise.”</p>\n<p>— Someone</p><br><p>Text.</p>')

    assert markdown == '::: quote\n“Wise.”\n\n— Someone\n:::\n\nText.\n'


def test_a_leading_dash_further_down_stays_a_paragraph():
    markdown = to_markdown('<p>Intro.</p><p>Two things:</p><p>— The first.</p>')

    assert ':::' not in markdown
    assert '— The first.' in markdown


def test_tex_is_kept_as_it_is():
    tex = r'$$ { a_1 = -g \, \text{m/s}^2 * [x] } $$'

    assert to_markdown(f'<p>{tex}</p>') == f'{tex}\n'


def test_dollars_in_prose_are_escaped():
    markdown = to_markdown('<p>a $100 bill for a $50 bill</p>')

    assert markdown == 'a \\$100 bill for a \\$50 bill\n'


@pytest.mark.parametrize(
    'html',
    [
        '<p>&lt;type&gt; (&lt;scope&gt;): &lt;subject&gt;</p>',
        '<p>start with an underscore (_) and * star</p>',
        '<p>clicking here [insert link here]</p>',
        '<p>1. not a list</p>',
        '<p>2) not a list</p>',
        '<p># not a heading</p>',
        '<p>- not a bullet</p>',
        '<p>the &amp;amp; entity</p>',
        '<p>back`tick and \\ backslash</p>',
    ],
)
def test_text_that_looks_like_syntax_survives(html):
    markdown = to_markdown(html)

    assert conversion_problems(html, markdown) == []
    rendered = render(markdown).html
    assert rendered.startswith('<p>')
    assert not any(tag in rendered for tag in ('<li', '<h1', '<h2', '<a '))


def test_broken_markup_is_read_the_way_browsers_read_it():
    html = '<p><strong/>Velocity</strong> refers to<p>the next one.'
    markdown = to_markdown(html)

    assert markdown == '**Velocity** refers to\n\nthe next one.\n'
    assert conversion_problems(html, markdown) == []


def test_links_lose_their_attributes():
    markdown = to_markdown(
        "<p><a href='https://a.test' target='_blank' rel='noreferrer' "
        "class='newpage-link'><u>text</u></a></p>"
    )

    assert markdown == '[text](https://a.test)\n'


def test_images_keep_their_size():
    markdown = to_markdown(
        f'<img src=\'{BLOB}/{CAPTIONED}.png\' width="1920" height="1080" alt=\'Axes\'/>'
    )

    assert markdown == f'![Axes]({BLOB}/{CAPTIONED}.png){{width=1920 height=1080}}\n'


@pytest.mark.parametrize(
    ('tampered', 'problem'),
    [
        ('A lost sentence here.', 'text differs'),
        ('Good **words** here.\n\nExtra words.', 'text differs'),
        ('Good words here.', 'bold text differs'),
        ('Good **words** here.\n\n$$ b $$', 'equations differ'),
        ('Good **words** here.\n\n$$ a $$\n\n![x](/other.png)', '<img> differ'),
    ],
)
def test_the_check_notices_a_bad_conversion(tampered, problem):
    html = '<p>Good <strong>words</strong> here.</p><p>$$ a $$</p>'

    problems = conversion_problems(html, tampered)

    assert any(found.startswith(problem) for found in problems), problems


def test_the_check_notices_markdown_reading_text_as_syntax():
    html = '<p>&lt;type&gt; here</p>'

    assert conversion_problems(html, '<type> here\n') != []


def test_the_check_notices_a_changed_link():
    html = '<p><a href="https://a.test">x</a></p>'

    assert conversion_problems(html, '[x](https://b.test)\n') == ['<a> differ']


def test_captions_are_added_to_their_images():
    fixed = apply_fixes(f'![Axes]({BLOB}/{CAPTIONED}.png){{width=1 height=2}}\n')

    caption = article_fixes.CAPTIONS[CAPTIONED]
    assert fixed == f'![Axes]({BLOB}/{CAPTIONED}.png "{caption}"){{width=1 height=2}}\n'


def test_formula_images_are_replaced_by_their_tex():
    fixed = apply_fixes(f'![First]({BLOB}/{FORMULA}.png){{width=1 height=2}}\n')

    assert fixed == f'{article_fixes.FORMULAS[FORMULA]}\n'


def test_an_image_without_a_decision_stops_the_conversion():
    with pytest.raises(KeyError):
        apply_fixes(f'![New]({BLOB}/000000000000.png)\n')


def test_the_dead_link_points_at_the_newton_article():
    fixed = apply_fixes('his [laws.](https://joaovitorwitt.com/articles/10)')

    assert fixed == 'his [laws.](/articles/how-the-laws-of-newton-shape-our-reality)'


def test_text_fixes_apply_only_to_their_article(monkeypatch):
    monkeypatch.setitem(html_to_markdown.TEXT_FIXES, 'x', (('old\n\n', ''),))

    assert apply_fixes('old\n\nkept\n', 'x') == 'kept\n'
    assert apply_fixes('old\n\nkept\n', 'y') == 'old\n\nkept\n'


@pytest.mark.parametrize('text', ['nothing here\n', 'old\n\nold\n\n'])
def test_a_text_fix_that_does_not_match_once_stops_the_conversion(monkeypatch, text):
    monkeypatch.setitem(html_to_markdown.TEXT_FIXES, 'x', (('old\n\n', ''),))

    with pytest.raises(ValueError, match='expected one match'):
        apply_fixes(text, 'x')


@pytest.mark.parametrize('tex', article_fixes.FORMULAS.values())
def test_every_written_out_formula_renders(tex):
    assert 'math-error' not in render(tex).html


@pytest.mark.parametrize(
    ('markdown', 'problem'),
    [
        ('text<br>more', 'legacy markup left in the Markdown'),
        ('<quote>x</quote>', 'legacy markup left in the Markdown'),
        ('$$ \\frac{ $$', 'an equation failed to convert'),
        ('[x](https://joaovitorwitt.com/articles/10)', 'a dead link is left'),
        (f'![x](/a/{FORMULA}.png "c")', 'a formula image is left'),
        ('![x](/a/b.png)', 'an image has no caption'),
    ],
)
def test_the_acceptance_criteria_are_enforced(markdown, problem):
    assert problem in final_problems(markdown, render(markdown).html)


def test_a_clean_article_has_no_final_problems():
    markdown = '## Title\n\n![x](/a/b.png "Caption")\n\n$$ a $$\n'

    assert final_problems(markdown, render(markdown).html) == []


def test_plan_updates_reports_what_it_would_store():
    rows = [
        {
            'id': 7,
            'slug': 'x',
            'content': '<h3>Section</h3><br><p>Some words.</p><p>$$ a $$</p>',
        }
    ]

    updates, problems = plan_updates(rows)

    assert problems == {}
    assert updates[0]['id'] == 7
    assert updates[0]['body_md'] == '## Section\n\nSome words.\n\n$$ a $$\n'
    assert '<h2 id="section">' in updates[0]['body_html']
    assert updates[0]['has_math'] is True
    assert updates[0]['word_count'] == 3
    assert updates[0]['toc'] == [{'level': 2, 'id': 'section', 'text': 'Section'}]


def test_apply_refuses_to_write_when_an_article_has_problems(monkeypatch, tmp_path):
    written = []

    class Repository:
        def legacy_articles(self):
            return [{'id': 1, 'slug': 'x', 'content': '<p>$$ \\frac{ $$</p>'}]

        def apply(self, *args):
            written.append(args)

    monkeypatch.setattr(html_to_markdown, 'ContentMarkdown', Repository)
    monkeypatch.setattr(html_to_markdown, 'OUTPUT_DIR', tmp_path)
    monkeypatch.setattr('sys.argv', ['html_to_markdown.py', '--apply'])

    assert html_to_markdown.main() == 1
    assert written == []


def test_render_all_only_plans_rows_that_changed():
    current = render('Same.')
    rows = [
        {
            'id': 1,
            'slug': 'same',
            'body_md': 'Same.',
            'body_html': current.html,
            'has_math': current.has_math,
            'toc': current.toc,
            'word_count': current.word_count,
        },
        {
            'id': 2,
            'slug': 'stale',
            'body_md': 'Fresh words.',
            'body_html': '<p>Old.</p>',
            'has_math': False,
            'toc': [],
            'word_count': 1,
        },
    ]

    updates = render_all.plan_updates(rows)

    assert [update['slug'] for update in updates] == ['stale']
    assert updates[0]['word_count'] == 2


class RecordingConnection:
    def __init__(self):
        self.calls = []

    def execute(self, query, params=None):
        self.calls.append((query, params))

    def connection(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_applying_backs_up_first_and_leaves_content_and_updated_at_alone(monkeypatch):
    fake = RecordingConnection()
    monkeypatch.setattr(website.db, 'get_pool', lambda: fake)
    row = {
        'id': 1,
        'slug': 'x',
        'body_md': 'md',
        'body_html': 'html',
        'has_math': False,
        'toc': [{'level': 2, 'id': 'a', 'text': 'A'}],
        'word_count': 1,
    }

    ContentMarkdown().apply([row], 'content_backup_test')

    create, enable, update = fake.calls
    assert 'CREATE TABLE IF NOT EXISTS' in str(create[0])
    assert 'ENABLE ROW LEVEL SECURITY' in str(enable[0])
    assert 'UPDATE content' in update[0]
    assert 'updated_at' not in update[0]
    assert ' content =' not in update[0]
    assert isinstance(update[1]['toc'], Jsonb)
