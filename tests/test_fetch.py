"""Public domain fetch. The parsing runs offline; the live calls are opt-in."""

from __future__ import annotations

from pathlib import Path

import pytest

from targum import ingest
from targum.errors import TargumError, UnsupportedSource
from targum.ingest import fetch
from targum.ingest.fetch.gutenberg import GutenbergFetcher, strip_boilerplate
from targum.ingest.fetch.wikisource import split_identifier
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
