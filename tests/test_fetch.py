"""Public domain fetch. The parsing runs offline; the live calls are opt-in."""

from __future__ import annotations

from pathlib import Path

import pytest

from targum import ingest
from targum.errors import TargumError, UnsupportedSource
from targum.ingest import fetch
from targum.ingest.fetch.gutenberg import GutenbergFetcher, strip_boilerplate
from targum.ingest.fetch.wikisource import (
    drop_leading_notices,
    drop_link_lists,
    drop_trailing_navigation,
    drop_unpointed_copies,
    split_identifier,
)
from targum.models import BlockKind


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("gutenberg:1342", True),
        ("wikisource:he:מגילת העצמאות", True),
        ("WIKISOURCE:Title", True),
        ("gutenberg:", False),
        ("http://example.com", False),
        ("book.epub", False),
        ("C:/books/one.txt", False),
    ],
)
def test_recognises_identifiers(source: str, expected: bool) -> None:
    assert fetch.is_identifier(source) is expected


def test_an_unknown_source_lists_the_real_ones() -> None:
    with pytest.raises(UnsupportedSource) as caught:
        fetch.load("archive:12345")
    assert "gutenberg" in (caught.value.hint or "")


# --- Gutenberg ---------------------------------------------------------------


def test_strips_the_licence_wrapper() -> None:
    raw = (
        "Title: A Book\n\n"
        "*** START OF THE PROJECT GUTENBERG EBOOK A BOOK ***\n\n"
        "The actual text.\n\n"
        "*** END OF THE PROJECT GUTENBERG EBOOK A BOOK ***\n\n"
        "Licence terms nobody wants translated."
    )
    assert strip_boilerplate(raw) == "The actual text."


def test_leaves_a_text_without_markers_alone() -> None:
    assert strip_boilerplate("Just text.") == "Just text."


def test_wants_a_number() -> None:
    with pytest.raises(TargumError, match="ebook number"):
        GutenbergFetcher().load("pride-and-prejudice")


# --- Wikisource --------------------------------------------------------------


@pytest.mark.parametrize(
    ("identifier", "expected"),
    [
        ("he:מגילת העצמאות", ("he", "מגילת העצמאות")),
        ("he:מגילת_העצמאות", ("he", "מגילת העצמאות")),
        ("Declaration of Independence", ("en", "Declaration of Independence")),
        ("fr:Déclaration des Droits", ("fr", "Déclaration des Droits")),
        ("United States: A History", ("en", "United States: A History")),
    ],
)
def test_splits_language_from_title(identifier: str, expected: tuple[str, str]) -> None:
    assert split_identifier(identifier) == expected


# --- round trip --------------------------------------------------------------


def test_markdown_round_trip(tmp_path: Path) -> None:
    """fetch writes what build reads, so a text can be hand-fixed in between."""
    source = tmp_path / "one.md"
    source.write_text(
        "---\ntitle: The Title\nauthor: An Author\nlanguage: en\n---\n\n"
        "# The Title\n\nA paragraph.\n\n> A quotation.\n",
        encoding="utf-8",
    )
    first = ingest.load(str(source))

    again = tmp_path / "two.md"
    again.write_text(ingest.to_markdown(first), encoding="utf-8")
    second = ingest.load(str(again))

    assert second.title == first.title
    assert second.author == first.author
    assert second.language == first.language
    assert [(b.kind, b.text) for b in second.blocks] == [(b.kind, b.text) for b in first.blocks]


def test_markdown_output_does_not_double_the_byline(tmp_path: Path) -> None:
    source = tmp_path / "one.md"
    source.write_text("---\nauthor: An Author\n---\n\n# T\n\nBody.\n", encoding="utf-8")
    written = ingest.to_markdown(ingest.load(str(source)))
    assert written.count("An Author") == 1


def _para(kind: BlockKind, text: str) -> tuple[BlockKind, int, str]:
    return (kind, 1, text)


def test_trailing_wiki_navigation_is_dropped() -> None:
    """A "see also" block is the wiki talking, and it was being translated and paid for."""
    kept = drop_trailing_navigation(
        [
            _para(BlockKind.heading, "אל הציפור"),
            _para(BlockKind.paragraph, "שלום רב שובך"),
            _para(BlockKind.heading, "ראו גם"),
            _para(BlockKind.paragraph, "ביאור:אל הציפור"),
            _para(BlockKind.paragraph, "טקסט זה הועתק מפרויקט בן-יהודה."),
        ]
    )
    assert [text for _, _, text in kept] == ["אל הציפור", "שלום רב שובך"]


def test_a_bare_second_copy_of_a_pointed_work_is_dropped() -> None:
    """The Bialik page carried the poem twice, under the wiki's own two headings, and the
    learner paid to translate, vowel and gloss both. The vowels are a toggle; a second
    copy of the same words is not a second text (targum-internal #90, UX review B4)."""
    kept = drop_unpointed_copies(
        [
            _para(BlockKind.heading, "אל הציפור"),
            _para(BlockKind.heading, "עם ניקוד"),
            _para(BlockKind.paragraph, "שָׁלוֹם רָב שׁוּבֵךְ, צִפֹּרָה נֶחְמֶדֶת"),
            _para(BlockKind.heading, "ללא ניקוד"),
            _para(BlockKind.paragraph, "שלום רב שובך ציפור נחמדת"),
        ]
    )

    assert [text for _, _, text in kept] == [
        "אל הציפור",
        "עם ניקוד",
        "שָׁלוֹם רָב שׁוּבֵךְ, צִפֹּרָה נֶחְמֶדֶת",
    ], "the labelled copy goes, heading and all"


def test_the_wiki_saying_its_copy_is_partial_does_not_save_it() -> None:
    """The real heading reads "ללא ניקוד (חלקי)". A partial duplicate is still a
    duplicate, and it is the case that actually shipped, so the match is on the opening
    words rather than the whole heading."""
    kept = drop_unpointed_copies(
        [
            _para(BlockKind.paragraph, "שָׁלוֹם רָב שׁוּבֵךְ"),
            _para(BlockKind.heading, "ללא ניקוד (חלקי)"),
            _para(BlockKind.paragraph, "שלום רב שובך"),
        ]
    )
    assert [text for _, _, text in kept] == ["שָׁלוֹם רָב שׁוּבֵךְ"]


def test_the_drop_stops_at_the_next_heading() -> None:
    """Only that section. Whatever the page puts after it is the page's own text."""
    kept = drop_unpointed_copies(
        [
            _para(BlockKind.paragraph, "שָׁלוֹם רָב שׁוּבֵךְ"),
            _para(BlockKind.heading, "ללא ניקוד"),
            _para(BlockKind.paragraph, "שלום רב שובך"),
            _para(BlockKind.heading, "הערה על הנוסח"),
            _para(BlockKind.paragraph, "הנוסח לפי דפוס ורשה"),
        ]
    )
    assert [text for _, _, text in kept] == [
        "שָׁלוֹם רָב שׁוּבֵךְ",
        "הערה על הנוסח",
        "הנוסח לפי דפוס ורשה",
    ]


def test_a_page_with_no_vowels_anywhere_is_left_alone() -> None:
    """A bare work is not a copy of anything. With nothing pointed on the page to prefer,
    a section headed "ללא ניקוד" is the page's own shape and stays."""
    same = [
        _para(BlockKind.heading, "ללא ניקוד"),
        _para(BlockKind.paragraph, "שלום רב שובך"),
    ]
    assert drop_unpointed_copies(same) == same


def test_the_copies_are_not_matched_by_their_letters() -> None:
    """Pointed Hebrew is written defectively and bare Hebrew is written full, so the same
    line is צִפֹּרָה and ציפור — different strings by convention. Nothing here may depend on
    them matching, which is why the heading is what decides."""
    kept = drop_unpointed_copies(
        [
            _para(BlockKind.paragraph, "מֵאַרְצוֹת הַחֹם"),
            _para(BlockKind.heading, "ללא ניקוד"),
            _para(BlockKind.paragraph, "מארצות החום"),
        ]
    )
    assert [text for _, _, text in kept] == ["מֵאַרְצוֹת הַחֹם"], (
        "dropped on the heading, though the letters differ"
    )


def test_several_navigation_sections_go_together() -> None:
    kept = drop_trailing_navigation(
        [
            _para(BlockKind.heading, "Walden"),
            _para(BlockKind.paragraph, "I went to the woods"),
            _para(BlockKind.heading, "See also"),
            _para(BlockKind.paragraph, "link"),
            _para(BlockKind.heading, "External links"),
            _para(BlockKind.paragraph, "link"),
        ]
    )
    assert [text for _, _, text in kept] == ["Walden", "I went to the woods"]


def test_navigation_wording_inside_a_work_is_kept() -> None:
    """Only the end of a page, so a real chapter called "Notes" survives."""
    paragraphs = [
        _para(BlockKind.heading, "Notes"),
        _para(BlockKind.paragraph, "body"),
        _para(BlockKind.heading, "Chapter 1"),
        _para(BlockKind.paragraph, "text"),
    ]
    assert drop_trailing_navigation(paragraphs) == paragraphs


def test_a_page_that_is_only_a_navigation_heading_is_left_alone() -> None:
    """Emptying the document would turn a thin page into "no readable text"."""
    paragraphs = [_para(BlockKind.heading, "See also"), _para(BlockKind.paragraph, "x")]
    assert drop_trailing_navigation(paragraphs) == paragraphs


def test_the_wikis_note_about_where_it_got_the_text_is_not_the_text() -> None:
    """Three of the Kuzari's five ma'amarim open with one, and it would be translated,
    pointed, glossed and read like anything else on the page."""
    paragraphs = [
        _para(BlockKind.paragraph, "טקסט זה הועתק מפרויקט בן-יהודה (הקישור המקורי)."),
        _para(BlockKind.paragraph, "אָמַר הֶחָבֵר: מִנְהַג הָעוֹבֵד."),
    ]
    assert drop_leading_notices(paragraphs) == paragraphs[1:]


def test_a_note_further_down_the_page_is_left_where_it_is() -> None:
    """Only from the front, and only while the front is one — the same narrow rule
    `drop_trailing_navigation` follows at the other end."""
    paragraphs = [
        _para(BlockKind.paragraph, "אָמַר הֶחָבֵר."),
        _para(BlockKind.paragraph, "טקסט זה הועתק מפרויקט בן-יהודה."),
    ]
    assert drop_leading_notices(paragraphs) == paragraphs


def test_a_row_of_links_at_the_top_of_a_page_is_not_the_text() -> None:
    """What `drop_trailing_navigation` cannot reach.

    Wikisource puts an edition picker and a contents row above every volume of a
    multi-part work — the Kuzari opens with three rows of edition links and then the
    hundred and seventeen numerals of its own chapters — and they sit at the front of the
    page under no heading at all.
    """
    html = (
        '<p><a href="/a">מאמר ראשון</a> • <a href="/b">מאמר שני</a> • '
        '<a href="/c">מאמר שלישי</a></p>'
        "<p>אָמַר הַמְחַבֵּר: שָׁאוֹל שָׁאֲלוּ אוֹתִי.</p>"
    )
    left = drop_link_lists(html)
    assert "מאמר ראשון" not in left
    assert "שָׁאוֹל" in left


def test_a_sentence_that_happens_to_carry_links_is_left_alone() -> None:
    """Measured over letters, which is what makes the threshold hold still.

    Counting the bullets and middots a navigation row is separated by against its links
    puts a row of a hundred and seventeen chapter numerals at 0.63 — indistinguishable by
    the number from a sentence, and nothing like one to read.
    """
    html = (
        "<p>בפרויקט <a href=/a>בן</a> יהודה ישנו גם כן טקסט מקורי של "
        "<a href=/b>ספר</a> <a href=/c>הכוזרי</a> ואפשר לקרוא בו.</p>"
    )
    assert "בפרויקט" in drop_link_lists(html)


def test_a_paragraph_with_one_or_two_links_is_never_furniture() -> None:
    html = '<p><a href="/a">כן</a> <a href="/b">לא</a></p>'
    assert "כן" in drop_link_lists(html)


# --- live ---------------------------------------------------------------------


@pytest.mark.network
def test_wikisource_hebrew_declaration() -> None:
    document = ingest.load("wikisource:he:מגילת העצמאות של מדינת ישראל")
    assert document.language == "he"
    assert any("מדינת ישראל" in block.text for block in document.blocks)
    # Hebrew prefixes stay attached across wiki link boundaries.
    body = " ".join(block.text for block in document.blocks)
    assert "בהצהרת בלפור" in body


@pytest.mark.network
def test_gutenberg_us_declaration() -> None:
    document = ingest.load("gutenberg:1")
    assert document.language == "en"
    assert document.author == "Thomas Jefferson"
    assert document.blocks[0].kind is BlockKind.heading
    assert "PROJECT GUTENBERG" not in " ".join(b.text for b in document.blocks)


def test_a_url_that_answers_with_plain_text_is_read_as_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A text file that happens to live on the web is still a text file.

    Running an article extractor over one finds no article and reports that the page has
    no readable text, which is exactly the wrong answer. Project Ben-Yehuda serves its
    whole library this way, at `/download/<id>.txt`.
    """
    from targum.ingest.url import Fetched, UrlIngester

    body = "First paragraph, in two sentences. Here is the second.\n\nAnd a second paragraph."
    monkeypatch.setattr(
        "targum.ingest.url.fetch",
        lambda url, params=None: Fetched(body, "text/plain; charset=utf-8"),
    )
    document = UrlIngester().load("https://example.com/work.txt")
    assert len(document.blocks) == 2
    assert document.blocks[0].text.startswith("First paragraph")


def test_an_empty_text_file_says_so(monkeypatch: pytest.MonkeyPatch) -> None:
    from targum.errors import TargumError
    from targum.ingest.url import Fetched, UrlIngester

    monkeypatch.setattr(
        "targum.ingest.url.fetch", lambda url, params=None: Fetched("  ", "text/plain")
    )
    with pytest.raises(TargumError, match="No readable text"):
        UrlIngester().load("https://example.com/empty.txt")


@pytest.mark.parametrize(
    ("content_type", "html"),
    [
        ("text/html; charset=utf-8", True),
        ("application/xhtml+xml", True),
        ("", True),
        ("text/plain", False),
        ("text/plain; charset=utf-8", False),
        ("text/markdown", False),
    ],
)
def test_what_counts_as_html(content_type: str, html: bool) -> None:
    """Absent or unrecognised is treated as HTML, which is what the web mostly is."""
    from targum.ingest.url import Fetched

    assert Fetched("", content_type).is_html is html
