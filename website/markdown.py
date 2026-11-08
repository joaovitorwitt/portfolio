"""
Turns an article's Markdown into the HTML its page serves. This runs when saving,
never per request: pages read the stored result, so the site itself doesn't need
these packages and they live in requirements-dev.txt.
"""

import logging
import re
from typing import NamedTuple

import latex2mathml.converter
import nh3
from markdown_it import MarkdownIt
from markdown_it.common.utils import escapeHtml
from markdown_it.token import Token
from mdit_py_plugins.anchors import anchors_plugin
from mdit_py_plugins.attrs import attrs_plugin
from mdit_py_plugins.container import container_plugin
from mdit_py_plugins.dollarmath import dollarmath_plugin
from mdit_py_plugins.footnote import footnote_plugin
from mdit_py_plugins.front_matter import front_matter_plugin
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import get_lexer_by_name
from pygments.util import ClassNotFound

log = logging.getLogger(__name__)

TOC_LEVELS = (2, 3)
ATTRIBUTION_MARK = '—'
MATH_ERROR_CLASS = 'math-error'

# Capital Greek letters, as latex2mathml writes them.
_CAPITAL_GREEK = re.compile(r'<mi>(&#x003(?:9[1-9A-F]|A[0-9]);)</mi>')

_MATHML_TAGS = {
    'math',
    'menclose',
    'merror',
    'mfrac',
    'mi',
    'mmultiscripts',
    'mn',
    'mo',
    'mover',
    'mpadded',
    'mphantom',
    'mprescripts',
    'mroot',
    'mrow',
    'ms',
    'mspace',
    'msqrt',
    'mstyle',
    'msub',
    'msubsup',
    'msup',
    'mtable',
    'mtd',
    'mtext',
    'mtr',
    'munder',
    'munderover',
}

_TOKEN_MATHML = {'mathvariant'}

# Everything a rendered article may contain. Anything else, raw HTML inside the
# Markdown included, is removed: no <script>, <style>, <iframe> or <form>, no
# on* attributes and no URL schemes beyond those in clean_html().
_ALLOWED_TAGS = _MATHML_TAGS | {
    'a',
    'abbr',
    'aside',
    'blockquote',
    'br',
    'code',
    'del',
    'details',
    'div',
    'em',
    'figcaption',
    'figure',
    'h1',
    'h2',
    'h3',
    'h4',
    'h5',
    'h6',
    'hr',
    'img',
    'kbd',
    'li',
    'ol',
    'p',
    'pre',
    's',
    'section',
    'span',
    'strong',
    'sub',
    'summary',
    'sup',
    'table',
    'tbody',
    'td',
    'th',
    'thead',
    'tr',
    'ul',
}

_HEADING_ATTRIBUTES = {'id'}

_ALLOWED_ATTRIBUTES = {
    'a': {'class', 'href', 'id', 'rel', 'target', 'title', 'aria-label'},
    'aside': {'class'},
    'code': {'class'},
    'div': {'class'},
    'figure': {'class'},
    'h1': _HEADING_ATTRIBUTES,
    'h2': _HEADING_ATTRIBUTES,
    'h3': _HEADING_ATTRIBUTES,
    'h4': _HEADING_ATTRIBUTES,
    'h5': _HEADING_ATTRIBUTES,
    'h6': _HEADING_ATTRIBUTES,
    'hr': {'class'},
    'img': {'alt', 'class', 'decoding', 'height', 'loading', 'src', 'title', 'width'},
    'li': {'class', 'id'},
    'ol': {'class', 'start'},
    'pre': {'class'},
    'section': {'class'},
    'span': {'class'},
    'sup': {'class', 'id'},
    # GFM column alignment is the only inline style that gets through.
    'td': {'style'},
    'th': {'scope', 'style'},
    # MathML. No href or xlink:href here: latex2mathml turns \href into an href
    # attribute, whatever URL the TeX asked for.
    'math': {'display', 'xmlns'},
    'menclose': {'notation'},
    'mfrac': {'linethickness'},
    'mi': _TOKEN_MATHML,
    'mn': _TOKEN_MATHML,
    'mo': {
        'fence',
        'form',
        'largeop',
        'lspace',
        'mathvariant',
        'maxsize',
        'minsize',
        'movablelimits',
        'rspace',
        'separator',
        'stretchy',
        'symmetric',
    },
    'mover': {'accent'},
    'mspace': {'depth', 'height', 'width'},
    'mstyle': {'displaystyle', 'scriptlevel'},
    'mtd': {'columnspan', 'rowspan'},
    'mtext': _TOKEN_MATHML,
    'munder': {'accentunder'},
    'munderover': {'accent', 'accentunder'},
}

_CALLOUTS = ('note', 'warning')

_code_formatter = HtmlFormatter(nowrap=True)


class RenderResult(NamedTuple):
    html: str
    toc: list[dict]
    has_math: bool
    word_count: int
    text: str


def _highlight_code(code: str, language: str, _attrs: str) -> str:
    """
    Classes rather than inline colours, so the theme stylesheet can follow
    data-theme. An unknown language falls back to markdown-it's plain block.
    """
    try:
        lexer = get_lexer_by_name(language)
    except ClassNotFound:
        return ''

    return (
        f'<pre class="highlight"><code class="language-{escapeHtml(language)}">'
        f'{highlight(code, lexer, _code_formatter)}</code></pre>'
    )


def _render_tex(tex: str, config: dict) -> str:
    """
    MathML, which browsers lay out themselves. TeX that doesn't parse is shown as
    source rather than failing the save, and the class lets a script spot it.
    """
    display = 'block' if config['display_mode'] else 'inline'
    try:
        mathml = latex2mathml.converter.convert(tex, display=display)
    except Exception as error:  # latex2mathml has no common base exception
        log.warning('could not convert TeX %r: %s', tex, error)
        return f'<code class="{MATH_ERROR_CLASS}">{escapeHtml(tex)}</code>'

    # Upright, as TeX sets them. Browsers slant any single-letter <mi>.
    return _CAPITAL_GREEK.sub(r'<mi mathvariant="normal">\1</mi>', mathml)


def _is_external(href: str) -> bool:
    return href.startswith(('http://', 'https://', '//'))


def _external_links(state) -> None:
    """The one place that decides how links leave the site."""
    for token in state.tokens:
        for child in token.children or []:
            if child.type == 'link_open' and _is_external(child.attrGet('href') or ''):
                child.attrSet('target', '_blank')
                child.attrSet('rel', 'noopener')


def _figures(state) -> None:
    """
    An image alone in its paragraph becomes a figure: the paragraph is hidden, as
    a <figure> inside a <p> would make the browser split the paragraph apart.
    """
    tokens = state.tokens
    for index, token in enumerate(tokens):
        if token.type != 'inline' or tokens[index - 1].type != 'paragraph_open':
            continue

        children = token.children or []
        if len(children) == 1 and children[0].type == 'image':
            children[0].meta['figure'] = True
            tokens[index - 1].hidden = True
            tokens[index + 1].hidden = True


def _render_image(self, tokens, idx, options, env) -> str:
    token = tokens[idx]
    token.attrSet('alt', self.renderInlineAsText(token.children or [], options, env))
    token.attrSet('loading', 'lazy')
    token.attrSet('decoding', 'async')

    if not token.meta.get('figure'):
        return self.renderToken(tokens, idx, options, env)

    caption = token.attrGet('title')
    if caption:
        del token.attrs['title']

    figcaption = f'<figcaption>{escapeHtml(caption)}</figcaption>' if caption else ''
    return f'<figure>{self.renderToken(tokens, idx, options, env)}{figcaption}</figure>'


def _quote_attributions(state) -> None:
    """
    In a `::: quote` container, a closing paragraph starting with an em dash is
    who said it, which belongs in the figure's caption and outside the quote.
    """
    tokens = state.tokens
    containers = []
    unclosed = []
    for index, token in enumerate(tokens):
        if token.type == 'container_quote_open':
            unclosed.append(index)
        elif token.type == 'container_quote_close':
            containers.append((unclosed.pop(), index))

    # Last one first: each insertion shifts everything after it.
    for opening, closing in sorted(containers, reverse=True):
        paragraph = closing - 3
        if (
            paragraph <= opening + 1
            or tokens[paragraph].type != 'paragraph_open'
            or not tokens[paragraph + 1].content.startswith(ATTRIBUTION_MARK)
        ):
            continue

        tokens[paragraph].tag = 'figcaption'
        tokens[paragraph + 2].tag = 'figcaption'
        tokens[closing].meta['attributed'] = True

        closing_quote = Token('html_block', '', 0)
        closing_quote.content = '</blockquote>\n'
        tokens.insert(paragraph, closing_quote)


def _render_quote(_self, tokens, idx, _options, _env) -> str:
    token = tokens[idx]
    if token.nesting == 1:
        return '<figure class="pull-quote"><blockquote>\n'

    return '</figure>\n' if token.meta.get('attributed') else '</blockquote></figure>\n'


def _render_callout(kind: str):
    def render(_self, tokens, idx, _options, _env) -> str:
        if tokens[idx].nesting == 1:
            return f'<aside class="callout callout-{kind}">\n'

        return '</aside>\n'

    return render


def _render_table_open(self, tokens, idx, options, env) -> str:
    # Wide tables scroll inside their own box instead of widening the page.
    return f'<div class="table-scroll">{self.renderToken(tokens, idx, options, env)}'


def _render_table_close(self, tokens, idx, options, env) -> str:
    return f'{self.renderToken(tokens, idx, options, env)}</div>'


def _text_of(token: Token) -> str:
    return ''.join(
        child.content
        for child in token.children or []
        if child.type in ('text', 'code_inline')
    )


def _heading_links(state) -> None:
    """
    Fills the table of contents and appends each heading's `#` link. The link
    comes last, so that the words counted afterwards can tell it apart: it has no
    place in the contents or in the reading time.
    """
    state.env['toc'] = []
    tokens = state.tokens
    for index, token in enumerate(tokens):
        if token.type != 'heading_open' or not token.attrGet('id'):
            continue

        heading_id = token.attrGet('id')
        inline = tokens[index + 1]
        text = _text_of(inline)

        if int(token.tag[1]) in TOC_LEVELS:
            state.env['toc'].append(
                {'level': int(token.tag[1]), 'id': heading_id, 'text': text}
            )

        link_open = Token('link_open', 'a', 1)
        link_open.attrSet('class', 'heading-anchor')
        link_open.attrSet('href', f'#{heading_id}')
        link_open.attrSet('aria-label', f'Link to section: {text}')
        mark = Token('text', '', 0)
        mark.content = '#'
        inline.children = [
            *(inline.children or []),
            link_open,
            mark,
            Token('link_close', 'a', -1),
        ]


def _measure(state) -> None:
    """
    The prose as plain text, one line per block, and its words. Both leave out
    code, math, alt text and heading links. The text is what search indexes.
    """
    words = 0
    has_math = False
    blocks = []
    for token in state.tokens:
        has_math = has_math or token.type.startswith('math')
        in_anchor = False
        pieces = []
        for child in token.children or []:
            has_math = has_math or child.type.startswith('math')
            if child.type == 'link_open' and child.attrGet('class') == 'heading-anchor':
                in_anchor = True
            elif child.type == 'link_close':
                in_anchor = False
            elif child.type in ('softbreak', 'hardbreak'):
                pieces.append(' ')
            elif child.type == 'text' and not in_anchor:
                pieces.append(child.content)
                words += sum(
                    any(char.isalnum() for char in word)
                    for word in child.content.split()
                )

        block = ' '.join(''.join(pieces).split())
        if block:
            blocks.append(block)

    state.env['word_count'] = words
    state.env['has_math'] = has_math
    state.env['text'] = '\n'.join(blocks)


def _build_parser() -> MarkdownIt:
    md = MarkdownIt(
        'commonmark',
        # Raw HTML is parsed here and made safe by clean_html() afterwards.
        {'html': True, 'highlight': _highlight_code},
    ).enable(['table', 'strikethrough'])

    md.use(front_matter_plugin)
    md.use(footnote_plugin)
    md.use(attrs_plugin)
    md.use(anchors_plugin, min_level=2, max_level=3)
    # Without allow_digits, a price such as $100 never opens an equation.
    md.use(
        dollarmath_plugin, allow_digits=False, double_inline=False, renderer=_render_tex
    )
    md.use(container_plugin, name='quote', render=_render_quote)
    for kind in _CALLOUTS:
        md.use(container_plugin, name=kind, render=_render_callout(kind))

    md.core.ruler.push('external_links', _external_links)
    md.core.ruler.push('figures', _figures)
    md.core.ruler.push('quote_attributions', _quote_attributions)
    md.core.ruler.push('heading_links', _heading_links)
    md.core.ruler.push('measure', _measure)

    md.add_render_rule('image', _render_image)
    md.add_render_rule('table_open', _render_table_open)
    md.add_render_rule('table_close', _render_table_close)
    return md


_parser = _build_parser()


def clean_html(html: str) -> str:
    return nh3.clean(
        html,
        tags=_ALLOWED_TAGS,
        attributes=_ALLOWED_ATTRIBUTES,
        # The renderer sets rel itself, on external links only.
        link_rel=None,
        url_schemes={'http', 'https', 'mailto'},
        filter_style_properties={'text-align'},
    )


def render(markdown: str) -> RenderResult:
    env = {}
    tokens = _parser.parse(markdown, env)
    html = _parser.renderer.render(tokens, _parser.options, env)

    return RenderResult(
        html=clean_html(html),
        toc=env['toc'],
        has_math=env['has_math'],
        word_count=env['word_count'],
        text=env['text'],
    )
