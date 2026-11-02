import pytest

from website.markdown import MATH_ERROR_CLASS, render


def html_of(markdown: str) -> str:
    return render(markdown).html


def test_paragraphs_and_emphasis():
    assert html_of('Some **bold** and *soft* text.').strip() == (
        '<p>Some <strong>bold</strong> and <em>soft</em> text.</p>'
    )


def test_tables_scroll_in_their_own_box_and_keep_their_alignment():
    html = html_of('| a | b |\n|:--|--:|\n| 1 | 2 |')

    assert html.startswith('<div class="table-scroll"><table>')
    assert '<th style="text-align:left">a</th>' in html
    assert '<td style="text-align:right">2</td>' in html


def test_strikethrough():
    assert '<s>gone</s>' in html_of('~~gone~~')


def test_footnotes():
    html = html_of('A claim[^1].\n\n[^1]: The source.')

    assert '<sup class="footnote-ref"><a href="#fn1" id="fnref1">' in html
    assert '<li id="fn1" class="footnote-item">' in html
    assert 'The source.' in html


def test_front_matter_is_not_shown():
    assert 'ignored' not in html_of('---\ntitle: ignored\n---\n\nBody')


def test_headings_get_ids_and_a_link_to_themselves():
    html = html_of('## Why & When')

    assert '<h2 id="why--when">Why &amp; When<a class="heading-anchor"' in html
    assert 'href="#why--when"' in html
    assert 'aria-label="Link to section: Why &amp; When">#</a></h2>' in html


def test_repeated_headings_get_different_ids():
    toc = render('## Same\n\n## Same').toc

    assert [heading['id'] for heading in toc] == ['same', 'same-1']


def test_toc_lists_h2_and_h3_as_plain_text():
    toc = render(
        '# Title\n\n## With `code` and **bold**\n\n### Sub\n\n#### Too deep'
    ).toc

    assert toc == [
        {
            'level': 2,
            'id': 'with-code-and-bold',
            'text': 'With code and bold',
        },
        {'level': 3, 'id': 'sub', 'text': 'Sub'},
    ]


def test_an_image_alone_becomes_a_figure_outside_any_paragraph():
    html = html_of('![Axes](/img/a.png "The axes"){width=1920 height=1080}')

    assert html.strip() == (
        '<figure><img src="/img/a.png" alt="Axes" width="1920" height="1080" '
        'loading="lazy" decoding="async"><figcaption>The axes</figcaption></figure>'
    )


def test_a_figure_without_a_title_has_no_caption():
    html = html_of('![Axes](/img/a.png)')

    assert html.startswith('<figure><img')
    assert 'figcaption' not in html


def test_an_image_inside_text_stays_inline():
    html = html_of('See ![icon](/img/a.png) here.')

    assert html.startswith('<p>See <img')
    assert 'figure' not in html


def test_captions_are_escaped():
    html = html_of('![a](/img/a.png "<b>not bold</b>")')

    assert '<figcaption>&lt;b&gt;not bold&lt;/b&gt;</figcaption>' in html


def test_quote_with_attribution_moves_the_author_out_of_the_blockquote():
    html = html_of('::: quote\nWise words.\n\n— Someone\n:::')

    assert html.startswith('<figure class="pull-quote"><blockquote>')
    assert '</blockquote>\n<figcaption>— Someone</figcaption>' in html
    assert html.strip().endswith('</figure>')


def test_quote_without_attribution():
    html = html_of('::: quote\nWise words.\n:::')

    assert '<p>Wise words.</p>\n</blockquote></figure>' in html
    assert 'figcaption' not in html


@pytest.mark.parametrize('kind', ['note', 'warning'])
def test_callouts(kind):
    html = html_of(f'::: {kind}\nCareful **now**.\n:::')

    assert f'<aside class="callout callout-{kind}">' in html
    assert '<strong>now</strong>' in html


def test_code_is_highlighted_with_classes_and_no_inline_colours():
    html = html_of('```python\ndef f(): pass\n```')

    assert '<pre class="highlight"><code class="language-python">' in html
    assert '<span class="k">def</span>' in html
    assert 'style=' not in html


def test_code_in_an_unknown_language_is_still_escaped():
    html = html_of('```nosuchlanguage\n<b>hi</b>\n```')

    assert '&lt;b&gt;hi&lt;/b&gt;' in html


def test_external_links_open_in_a_new_tab_and_internal_ones_do_not():
    html = html_of('[out](https://example.com) and [in](/articles/x)')

    assert (
        '<a href="https://example.com" target="_blank" rel="noopener">out</a>' in html
    )
    assert '<a href="/articles/x">in</a>' in html


def test_block_and_inline_math_become_mathml():
    result = render('Inline $x_1$ here.\n\n$$ { \\frac{a}{b} } $$')

    assert '<span class="math inline"><math' in result.html
    assert 'display="inline"' in result.html
    assert 'display="block"' in result.html
    assert '<mfrac>' in result.html
    assert result.has_math


def test_capital_greek_is_upright_and_latin_is_not():
    html = html_of('$$ \\Delta x $$')

    assert '<mi mathvariant="normal">Δ</mi><mi>x</mi>' in html


def test_text_without_math_says_so():
    assert not render('Just **words**.').has_math


@pytest.mark.parametrize(
    'prose',
    [
        r'A \$100 bill buys a \$50 bill.',
        'A $100 bill buys a $50 bill.',
    ],
)
def test_prices_are_not_equations(prose):
    result = render(prose)

    assert '<math' not in result.html
    assert '$100 bill buys a $50 bill.' in result.html
    assert not result.has_math


def test_invalid_tex_shows_its_source_instead_of_failing_the_save():
    html = html_of('$$ \\frac{ $$')

    assert f'<code class="{MATH_ERROR_CLASS}">\\frac{{</code>' in html


def test_word_count_leaves_out_code_math_and_heading_links():
    markdown = (
        '## Two words\n\n'
        'Three more words `not_this_code` $x + y$.\n\n'
        '```python\nnot counted at all\n```\n\n'
        '$$ a + b + c $$\n\n'
        '![not the alt either](/img/a.png "nor the caption")\n'
    )

    assert render(markdown).word_count == 5


@pytest.mark.parametrize(
    ('markdown', 'forbidden'),
    [
        ('<script>alert(1)</script>', ('<script', 'alert')),
        ('<img src="/a.png" onerror="alert(1)">', ('onerror', 'alert')),
        ('<p onclick="alert(1)">x</p>', ('onclick', 'alert')),
        ('<a href="javascript:alert(1)">x</a>', ('javascript:',)),
        ('<a href="JaVaScRiPt:alert(1)">x</a>', ('alert',)),
        ('<a href="data:text/html,hi">x</a>', ('data:',)),
        ('<img src="data:image/svg+xml,x">', ('data:',)),
        ('[x](javascript:alert(1))', ('href',)),
        ('![x](javascript:alert(1))', ('src=',)),
        ('<iframe src="https://evil.test"></iframe>', ('iframe',)),
        ('<style>p { display: none }</style>', ('<style', 'display')),
        ('<form action="/x"><input></form>', ('<form', '<input')),
        ('<p style="position: fixed">x</p>', ('style', 'fixed')),
        ('<svg onload="alert(1)"></svg>', ('svg', 'onload')),
        ('<math><mi href="javascript:alert(1)">y</mi></math>', ('href', 'javascript:')),
        (
            '<math><annotation-xml encoding="text/html"><img src=x onerror=alert(1)>'
            '</annotation-xml></math>',
            ('onerror', 'annotation-xml'),
        ),
        ('$$ \\href{javascript:alert(1)}{x} $$', ('href', 'javascript:')),
        ('![a](/a.png){onerror="alert(1)"}', ('onerror',)),
    ],
)
def test_nothing_in_the_markdown_can_run_a_script(markdown, forbidden):
    html = html_of(markdown)

    for text in forbidden:
        assert text not in html
