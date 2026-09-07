"""HTML extraction, which every one of EPUB, URL and Wikisource ingest runs through."""

from __future__ import annotations

from targum.ingest.htmltext import paragraphs_from_html
from targum.models import BlockKind


def kinds(html: str) -> list[BlockKind]:
    return [kind for kind, _, _ in paragraphs_from_html(html)]


def texts(html: str) -> list[str]:
    return [text for _, _, text in paragraphs_from_html(html)]


def test_keeps_headings_with_their_level() -> None:
    found = paragraphs_from_html("<body><h1>One</h1><h3>Three</h3></body>")
    assert found == [(BlockKind.heading, 1, "One"), (BlockKind.heading, 3, "Three")]


def test_drops_page_furniture() -> None:
    html = """<body><nav>Contents</nav><header>Site</header><p>Real text.</p>
    <footer>Copyright</footer><script>var x=1</script></body>"""
    assert texts(html) == ["Real text."]


def test_drops_footnotes_and_their_markers() -> None:
    html = """<body><p>A claim<sup class="noteref">3</sup> is made.</p>
    <div class="footnotes"><p>3. Apparatus, not text.</p></div>
    <aside class="footnote">Also apparatus.</aside></body>"""
    assert texts(html) == ["A claim is made."]


def test_a_wrapper_div_does_not_duplicate_its_paragraphs() -> None:
    html = "<body><div class='chapter'><p>One.</p><p>Two.</p></div></body>"
    assert texts(html) == ["One.", "Two."]


def test_blockquotes_keep_their_kind() -> None:
    assert kinds("<body><blockquote><p>Quoted.</p></blockquote></body>") == [BlockKind.blockquote]


def test_inline_elements_join_without_a_space() -> None:
    # Hebrew attaches prefixes to the next word, and a link often starts after the
    # prefix. Joining with a space would split one word into two.
    html = '<body><p>ב<a href="#">הצהרת בלפור</a> מיום</p></body>'
    assert texts(html) == ["בהצהרת בלפור מיום"]


def test_real_whitespace_between_elements_survives() -> None:
    html = "<body><p>A <a href='#'>link</a> mid sentence.</p></body>"
    assert texts(html) == ["A link mid sentence."]


def test_tightens_space_before_punctuation() -> None:
    html = "<body><p>the word <span>,</span> and ( a note ) here.</p></body>"
    assert texts(html) == ["the word, and (a note) here."]


def test_leaves_french_spacing_alone() -> None:
    # French takes a space before ; : ! ?. Only marks that never do are tightened.
    assert texts("<body><p>Vraiment ?</p></body>") == ["Vraiment ?"]


def test_maqaf_never_takes_a_space() -> None:
    html = '<body><p>בארץ<a href="#">־ישראל</a> קם</p></body>'
    assert texts(html) == ["בארץ־ישראל קם"]


def test_empty_html_gives_nothing() -> None:
    assert paragraphs_from_html("") == []


def test_transcription_fill_rules_are_not_text() -> None:
    html = "<body><p>the separation. __________ We hold these truths</p></body>"
    assert texts(html) == ["the separation. We hold these truths"]


def test_a_real_dash_survives() -> None:
    assert texts("<body><p>the well-known case</p></body>") == ["the well-known case"]


def test_a_skin_flag_on_the_root_does_not_take_the_page_with_it() -> None:
    """MediaWiki's Vector 2022 writes `vector-toc-available` on <html>, and the furniture
    patterns match inside a word, so every Wikipedia page came back blank (2026-09-07)."""
    html = """<html class="vector-toc-available client-nojs"><body class="mw-editable">
    <main id="content"><p>ירושלים היא עיר.</p></main></body></html>"""
    assert texts(html) == ["ירושלים היא עיר."]


def test_furniture_inside_the_page_is_still_dropped() -> None:
    html = """<html class="vector-toc-available"><body><p>Real text.</p>
    <div class="vector-toc">Contents</div><div class="navbox">See also</div>
    <article class="teaser"><p>Read more from us.</p></article></body></html>"""
    assert texts(html) == ["Real text."]


def test_a_framework_namespace_is_not_a_furniture_word() -> None:
    """Elementor builds a large share of the WordPress web and wraps every block it
    makes in `elementor-widget`. Matching `widget` inside it threw the whole article
    away on hayadan.org.il and shakuf.co.il (2026-09-07)."""
    html = """<body><div class="elementor-widget-container"><div class="elementor-widget">
    <p>הידען מדווח על מחקר חדש.</p></div></div>
    <div class="widget-area"><p>Furniture.</p></div></body>"""
    assert texts(html) == ["הידען מדווח על מחקר חדש."]


def test_a_generic_word_still_counts_where_a_name_begins() -> None:
    html = """<body><p>Real text.</p><div class="share-tools">Share this</div>
    <div class="comments"><p>A comment.</p></div><aside class="promo">Buy</aside>
    <div class="social_links">Follow</div></body>"""
    assert texts(html) == ["Real text."]


def test_a_long_furniture_word_still_counts_anywhere_in_a_name() -> None:
    html = """<body><p>Real text.</p><div class="wp-block-taboola">Around the web</div>
    <div class="mw-editsection">edit</div><div class="site-newsletter-box">Sign up</div>
    <div class="vector-toc-contents">Contents</div></body>"""
    assert texts(html) == ["Real text."]


def test_an_element_holding_most_of_the_page_is_the_page() -> None:
    """The backstop for the framework nobody has met yet: whatever it is classed, an
    element carrying most of the text is not furniture."""
    body = "מילה " * 200
    html = f'<body><div class="promo-wrapper"><p>{body}</p></div></body>'
    assert texts(html) == [body.strip()]


def test_but_not_a_short_one_that_merely_outweighs_a_short_page() -> None:
    """Share alone would protect the apparatus in a two-line document."""
    html = '<body><p>A claim.</p><div class="footnotes"><p>Apparatus, not text.</p></div></body>'
    assert texts(html) == ["A claim."]
