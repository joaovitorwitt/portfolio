"""
Converts the hand-written HTML of every article to Markdown and stores it, with
its rendered HTML, next to the legacy `content` column, which stays untouched.
--apply needs migration 004. If any article loses a word, nothing is written.

Each run converts from `content` again and replaces body_md, so don't run it
once articles are being edited in Markdown.

    python scripts/html_to_markdown.py --dry-run    # write backups/markdown/ only
    python scripts/html_to_markdown.py --apply      # back up the table, then store
"""

import argparse
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bs4 import BeautifulSoup  # noqa: E402
from markdownify import MarkdownConverter  # noqa: E402

from scripts.article_fixes import CAPTIONS, FORMULAS, LINK_FIXES  # noqa: E402
from website.db import ContentMarkdown, get_pool  # noqa: E402
from website.markdown import ATTRIBUTION_MARK, MATH_ERROR_CLASS, render  # noqa: E402

OUTPUT_DIR = Path(__file__).resolve().parent.parent / 'backups' / 'markdown'

_TEX = re.compile(r'\$\$(.*?)\$\$', re.DOTALL)
_MD_IMAGE = re.compile(r'!\[(?P<alt>[^\]]*)\]\((?P<url>[^)\s]+)\)(?P<attrs>\{[^}]*\})?')
_IMAGE_HASH = re.compile(r'([0-9a-f]{12})\.\w+$')

_ESCAPED_CHARS = re.compile(r'([\\`*_\[\]<>$])')
_ENTITY_LIKE = re.compile(r'&(?=#?\w+;)')
# What would start a heading or a list when it opens a paragraph.
_BLOCK_MARK = re.compile(r'^(?=#{1,6}\s|[-+](\s|$))')
_ORDERED_MARK = re.compile(r'^(\d+)(?=[.)]\s)')


class ArticleConverter(MarkdownConverter):
    """
    What the stored HTML needs and markdownify's defaults get wrong for it. Its
    own escaping is off: it misses `$` and fills prose with backslashes.
    """

    def __init__(self):
        super().__init__(
            heading_style='ATX',
            escape_asterisks=False,
            escape_underscores=False,
            escape_misc=False,
            autolinks=False,
        )

    def escape(self, text: str, parent_tags) -> str:
        return _ENTITY_LIKE.sub('&amp;', _ESCAPED_CHARS.sub(r'\\\1', text))

    def convert_br(self, el, text, parent_tags) -> str:
        return ' '

    def convert_h3(self, el, text, parent_tags) -> str:
        """Sections become h2: only the page title sits above them."""
        return f'\n\n## {" ".join(text.split())}\n\n'

    def convert_p(self, el, text, parent_tags) -> str:
        raw = el.get_text().strip()
        if _TEX.fullmatch(raw):
            return f'\n\n{raw}\n\n'

        text = _BLOCK_MARK.sub(r'\\', ' '.join(text.split()))
        return f'\n\n{_ORDERED_MARK.sub(r"\1\\", text)}\n\n'

    def convert_quote(self, el, text, parent_tags) -> str:
        return f'\n\n::: quote\n{text.strip()}\n:::\n\n'

    def convert_img(self, el, text, parent_tags) -> str:
        return (
            f'\n\n![{el.get("alt", "")}]({el["src"]})'
            f'{{width={el["width"]} height={el["height"]}}}\n\n'
        )


def parse(html: str) -> BeautifulSoup:
    """
    html5lib, because it repairs markup the way browsers do: readers see
    `<strong/>Velocity</strong>` as bold and `<p>a<p>b` as two paragraphs.
    """
    return BeautifulSoup(html, 'html5lib')


def _wrap_opening_quote(soup: BeautifulSoup) -> None:
    """
    Two articles open with a quote and its author as plain paragraphs. It has to
    be the opening: further down, a leading dash marks a list item.
    """
    paragraphs = soup.body.find_all('p', recursive=False)[:2]
    if len(paragraphs) == 2 and paragraphs[1].get_text().startswith(ATTRIBUTION_MARK):
        quote = soup.new_tag('quote')
        paragraphs[0].insert_before(quote)
        quote.extend(paragraphs)


def to_markdown(html: str) -> str:
    soup = parse(html)
    _wrap_opening_quote(soup)
    markdown = ArticleConverter().convert_soup(soup)
    # A <br> between blocks leaves a line of nothing but its space behind.
    markdown = re.sub(r'^[ \t]+$', '', markdown, flags=re.MULTILINE)
    return re.sub(r'\n{3,}', '\n\n', markdown).strip() + '\n'


def legacy_text(html: str) -> str:
    """What a reader sees of the old HTML, without whitespace or equations."""
    return ''.join(_TEX.sub('', parse(html).get_text()).split())


def rendered_text(html: str) -> str:
    """What a reader sees of the new HTML, without whitespace or equations."""
    soup = parse(html)
    for element in soup.select('math, .heading-anchor'):
        element.decompose()

    return ''.join(soup.get_text().split())


def _tex_list(text: str) -> list[str]:
    return [''.join(tex.split()) for tex in _TEX.findall(text)]


def _strong_list(soup: BeautifulSoup) -> list[str]:
    return [''.join(el.get_text().split()) for el in soup.find_all('strong')]


def _attribute_list(soup: BeautifulSoup, tag: str, attribute: str) -> list[str]:
    return [
        el.get(attribute)
        for el in soup.find_all(tag)
        if 'heading-anchor' not in el.get('class', [])
    ]


def conversion_problems(html: str, markdown: str) -> list[str]:
    """
    Everything that says the conversion lost something, before any deliberate
    fix. Comparing rendered text also catches what Markdown read as syntax.
    """
    rendered = render(markdown).html
    old, new = parse(html), parse(rendered)
    problems = []

    before, after = legacy_text(html), rendered_text(rendered)
    if before != after:
        at = next(
            (
                index
                for index, (a, b) in enumerate(zip(before, after, strict=False))
                if a != b
            ),
            min(len(before), len(after)),
        )
        problems.append(
            f'text differs: {before[at : at + 60]!r} / {after[at : at + 60]!r}'
        )

    if _tex_list(html) != _tex_list(markdown):
        problems.append('equations differ')

    for tag, attribute in (('img', 'src'), ('a', 'href')):
        if _attribute_list(old, tag, attribute) != _attribute_list(new, tag, attribute):
            problems.append(f'<{tag}> differ')

    if _strong_list(old) != _strong_list(new):
        problems.append('bold text differs')

    return problems


def apply_fixes(markdown: str) -> str:
    """Links, captions and formula pictures, from scripts/article_fixes.py."""

    def fix_image(match: re.Match) -> str:
        key = _IMAGE_HASH.search(match['url']).group(1)
        if key in FORMULAS:
            return FORMULAS[key]

        caption = CAPTIONS[key].replace('"', '\\"')
        return f'![{match["alt"]}]({match["url"]} "{caption}"){match["attrs"] or ""}'

    fixed = _MD_IMAGE.sub(fix_image, markdown)
    for old, new in LINK_FIXES.items():
        fixed = fixed.replace(f']({old})', f']({new})')

    return fixed


def final_problems(markdown: str, html: str) -> list[str]:
    """The issue's acceptance criteria, checked against what would be stored."""
    problems = []
    if re.search(r'<br|<quote|class=', markdown):
        problems.append('legacy markup left in the Markdown')
    if MATH_ERROR_CLASS in html:
        problems.append('an equation failed to convert')
    if any(old in markdown for old in LINK_FIXES):
        problems.append('a dead link is left')
    if any(key in markdown for key in FORMULAS):
        problems.append('a formula image is left')
    if parse(html).select('figure > img:not(:has(+ figcaption))'):
        problems.append('an image has no caption')

    return problems


def plan_updates(rows: list[dict]) -> tuple[list[dict], dict[str, list[str]]]:
    updates = []
    problems = {}
    for row in rows:
        base = to_markdown(row['content'])
        fixed = apply_fixes(base)
        result = render(fixed)

        found = conversion_problems(row['content'], base)
        found += final_problems(fixed, result.html)
        if found:
            problems[row['slug']] = found

        updates.append(
            {
                'id': row['id'],
                'slug': row['slug'],
                'body_md': fixed,
                'body_html': result.html,
                'has_math': result.has_math,
                'toc': result.toc,
                'word_count': result.word_count,
            }
        )

    return updates, problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--dry-run', action='store_true', help='write files only')
    mode.add_argument('--apply', action='store_true', help='back up and store')
    args = parser.parse_args()

    repository = ContentMarkdown()
    updates, problems = plan_updates(repository.legacy_articles())

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for update in updates:
        (OUTPUT_DIR / f'{update["slug"]}.md').write_text(
            update['body_md'], encoding='utf-8'
        )
        print(
            f'  {update["slug"]:52} {update["word_count"]:5} words  '
            f'{len(update["toc"]):2} headings  math: {update["has_math"]}'
        )

    print(f'\n{len(updates)} articles, Markdown in {OUTPUT_DIR}')
    if problems:
        for slug, found in problems.items():
            print(f'  {slug}: {found}')

        print(f'aborting: {len(problems)} articles have problems, nothing written')
        return 1

    print('every article keeps its text, equations, images, links and bold')
    if args.dry_run:
        print('dry run, nothing written to the database')
        return 0

    backup_table = f'content_backup_{datetime.now(UTC):%Y%m%d}'
    repository.apply(updates, backup_table)
    print(f'stored {len(updates)} articles, previous data in {backup_table}')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    finally:
        get_pool().close()
