"""The pages a stranger can reach.

These are the only surfaces a search engine ever sees, and the whole reason for
compiling a catalogue: somebody looking for a particular text should be able to find it
rather than meet a page saying "Coming soon". Everything else stays shut.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from targum.catalogue import CATALOGUE, Shelf, on
from targum.render.builder import shelf_page, text_page

ADDRESS = "https://targum.page"


def strip(html: str) -> str:
    """The text a crawler indexes: no style block, no markup."""
    html = re.sub(r"<(style|script)[^>]*>.*?</\1>", " ", html, flags=re.S)
    return " ".join(re.sub(r"<[^>]+>", " ", html).split())


# -- the shelves --------------------------------------------------------------


@pytest.mark.parametrize("shelf", list(Shelf))
def test_a_shelf_page_names_itself_and_lists_its_texts(shelf: Shelf) -> None:
    html = shelf_page(shelf, ADDRESS)
    assert f'href="{ADDRESS}/{shelf.value}"' in html, "a canonical URL, or duplicates compete"
    for entry in on(shelf):
        assert f'href="/{shelf.value}/{entry.id}"' in html


def test_a_shelf_holds_only_its_own_texts() -> None:
    """The point of two shelves. A Tanakh page must never list a novel."""
    for shelf in Shelf:
        html = shelf_page(shelf, ADDRESS)
        for entry in CATALOGUE:
            if entry.shelf is not shelf:
                assert f'href="/{entry.shelf.value}/{entry.id}"' not in html


def test_an_empty_shelf_says_so_rather_than_pretending() -> None:
    """The Beit Midrash is empty until Sefaria lands, and should admit it."""
    empty = [shelf for shelf in Shelf if not on(shelf)]
    for shelf in empty:
        assert "Nothing here yet" in shelf_page(shelf, ADDRESS)


# -- one text -----------------------------------------------------------------


@pytest.mark.parametrize("entry", CATALOGUE, ids=lambda e: e.id)
def test_every_text_page_carries_what_a_search_engine_needs(entry: object) -> None:
    html = text_page(entry, ADDRESS)  # type: ignore[arg-type]
    assert "<title>" in html and "</title>" in html
    described = re.search(r'name="description" content="([^"]+)"', html)
    assert described and len(described.group(1)) > 20, "a description worth showing"
    assert 'property="og:title"' in html
    assert f'rel="canonical" href="{ADDRESS}/' in html


@pytest.mark.parametrize("entry", CATALOGUE, ids=lambda e: e.id)
def test_a_text_page_is_about_the_text(entry: object) -> None:
    """Whoever arrives searched for the book, not for a reading tool."""
    html = text_page(entry, ADDRESS)  # type: ignore[arg-type]
    assert entry.title in html  # type: ignore[attr-defined]
    assert entry.author in html  # type: ignore[attr-defined]
    assert entry.blurb in html  # type: ignore[attr-defined]


def test_the_sample_is_real_reading_in_both_languages() -> None:
    """A page of description ranks for nothing and tells a visitor nothing.

    Where an opening has been chosen, both sides of it have to actually be on the page.
    """
    with_sample = [entry for entry in CATALOGUE if entry.sample]
    assert with_sample, "at least one entry should carry an opening"
    for entry in with_sample:
        text = strip(text_page(entry, ADDRESS))
        for line in entry.sample:
            assert line.source[:40] in text, f"{entry.id}: source missing"
            assert line.target[:40] in text, f"{entry.id}: translation missing"


def test_the_source_side_is_marked_with_its_language_and_direction() -> None:
    """Hebrew rendered left-to-right is the failure this catches, and RTL is structural."""
    hebrew = [entry for entry in CATALOGUE if entry.language == "he" and entry.sample]
    assert hebrew
    for entry in hebrew:
        html = text_page(entry, ADDRESS)
        assert 'dir="rtl"' in html
        assert f'lang="{entry.language}"' in html


def test_a_translation_is_named_wherever_a_text_is_shown() -> None:
    """A reader decides whether to trust a translation by who made it.

    That is why it is body text rather than an attribution footnote — and for CC-BY it
    is also the obligation being discharged by the code rather than by memory.
    """
    for entry in CATALOGUE:
        html = text_page(entry, ADDRESS)
        for rendering in entry.translations:
            assert rendering.name in html
            if rendering.publisher:
                assert rendering.publisher in html
            if rendering.licence:
                assert rendering.licence in html


def test_no_page_leaks_a_route_that_needs_an_account() -> None:
    private = ("/words", "/readers", "/reader/", "/job/", "/glossary/")
    pages = [shelf_page(shelf, ADDRESS) for shelf in Shelf]
    pages += [text_page(entry, ADDRESS) for entry in CATALOGUE]
    for html in pages:
        for route in private:
            assert f'href="{route}' not in html, f"{route} is not for strangers"


def test_samples_belong_to_entries_that_exist() -> None:
    """A sample keyed to a deleted entry is invisible until somebody wonders why a page
    is thin, so fail here instead."""
    import json

    raw = json.loads(Path("src/targum/samples.json").read_text(encoding="utf-8"))
    known = {entry.id for entry in CATALOGUE}
    assert set(raw) <= known, f"samples for unknown entries: {set(raw) - known}"
