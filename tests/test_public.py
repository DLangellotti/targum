"""The pages a stranger can reach.

These are the only surfaces a search engine ever sees, and the whole reason for
compiling a catalogue: somebody looking for a particular text should be able to find it
rather than meet a page saying "Coming soon". Everything else stays shut.
"""

from __future__ import annotations

import re
from html import unescape
from pathlib import Path

import pytest

from targum.catalogue import CATALOGUE, Tag, beit_midrash
from targum.render.builder import shelf_page, text_page

ADDRESS = "https://targum.page"


def strip(markup: str) -> str:
    """The text a crawler indexes: no style block, no markup, entities resolved.

    Unescaping matters: Jinja turns the apostrophe in "Nevi'im" into `&#39;`, correctly,
    so comparing raw catalogue strings against raw HTML fails on exactly the entries
    whose names carry one.
    """
    markup = re.sub(r"<(style|script)[^>]*>.*?</\1>", " ", markup, flags=re.S)
    return " ".join(unescape(re.sub(r"<[^>]+>", " ", markup)).split())


# -- the catalogue ------------------------------------------------------------


def test_the_catalogue_page_names_itself_and_lists_every_text() -> None:
    """One list. There were two — a Library and a Beit Midrash — and the split meant a
    reader had to already know which room a text was in to find it."""
    html = shelf_page(ADDRESS)
    assert f'href="{ADDRESS}/library"' in html, "a canonical URL, or duplicates compete"
    for entry in CATALOGUE:
        assert f'href="/library/{entry.id}"' in html


def test_an_empty_catalogue_says_so_rather_than_pretending(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tested by emptying it rather than by waiting for it to be empty: it has twenty
    texts now, so the earlier version of this found nothing to check and passed without
    asserting anything at all."""
    monkeypatch.setattr("targum.catalogue.CATALOGUE", [])
    assert "Nothing here yet" in shelf_page(ADDRESS)


# -- what a text is -----------------------------------------------------------


def test_the_jewish_texts_are_tagged() -> None:
    """The split is gone; what it was for is not. Some readers — ultra-Orthodox ones
    especially — would rather not be shown secular material at all, and a Beit Midrash
    mode needs to know which entries they came for. That is this tag, and nothing else
    can stand in for it: `sefaria:` is where a text was fetched from, not what it is.
    """
    tagged = beit_midrash()
    assert tagged, "the Tanakh entries carry the tag"
    assert all(Tag.tanakh in entry.tags for entry in tagged)
    # And it is a property of the entry, so it survives into the browser.
    assert tagged[0].state()["tags"] == ["tanakh"]

    untagged = [entry for entry in CATALOGUE if not entry.tags]
    assert untagged, "and the secular texts do not"
    assert untagged[0].state()["tags"] == []


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
    text = strip(text_page(entry, ADDRESS))  # type: ignore[arg-type]
    assert entry.title in text  # type: ignore[attr-defined]
    assert entry.author in text  # type: ignore[attr-defined]
    assert entry.blurb in text  # type: ignore[attr-defined]


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
        text = strip(text_page(entry, ADDRESS))
        for rendering in entry.translations:
            assert rendering.name in text
            if rendering.publisher:
                assert rendering.publisher in text
            if rendering.licence:
                assert rendering.licence in text


def test_no_page_leaks_a_route_that_needs_an_account() -> None:
    private = ("/progress", "/readers", "/reader/", "/job/", "/glossary/")
    pages = [shelf_page(ADDRESS)]
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


def test_every_text_is_classified_and_measured() -> None:
    """The library sorts and filters on these three, and a filter is only worth having
    if what is behind it is true. Difficulty in particular is counted off the whole text
    by `scripts/measure_difficulty.py` rather than judged by eye — an entry added with
    the field left at zero is one the library cannot place."""
    from targum.catalogue import CATALOGUE, Kind, Register

    for entry in CATALOGUE:
        assert isinstance(entry.kind, Kind), entry.id
        assert isinstance(entry.register, Register), entry.id
        assert entry.difficulty, f"{entry.id} has never been measured"
        # A share of running words, so anything outside these is a bug in the counting
        # rather than an unusually hard book.
        assert 5 <= entry.difficulty <= 60, entry.id
        assert entry.minutes >= 1, entry.id
        if entry.language.startswith("he"):
            assert entry.register is not Register.none, entry.id


def test_hebrew_poetry_reads_harder_than_hebrew_narrative() -> None:
    """A sanity check on the measurement rather than on any one number: whatever the
    scale is doing, Psalms cannot come out easier than Genesis."""
    from targum.catalogue import CATALOGUE, Kind

    def hardest(kind: Kind) -> float:
        found = [
            e.difficulty for e in CATALOGUE if e.kind is kind and e.register.value == "biblical"
        ]
        return sum(found) / len(found)

    assert hardest(Kind.poetry) > hardest(Kind.prose)


def test_a_cover_prompt_says_what_the_brand_never_draws() -> None:
    """An image model asked for a Hebrew book cover returns a scroll, a candelabrum and a
    flag every time, and §10 names all three as things this brand does not do."""
    from targum.catalogue import CATALOGUE, cover_prompt

    prompt = cover_prompt(CATALOGUE[0])
    said = prompt.lower()
    for banned in ("no flags", "no lettering", "no gradients", "ritual objects", "no maps"):
        assert banned in said
    # And it is about this text, not a generic cover.
    assert CATALOGUE[0].title in prompt and CATALOGUE[0].blurb in prompt
