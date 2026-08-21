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
