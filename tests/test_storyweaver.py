"""StoryWeaver picture books, by story number.

Everything here runs against saved answers from `/api/v1/stories/{id}/read` — the Italian
*La luna e il cappello* (7686), the French it was translated from (1124) and the English
original both go back to (234), trimmed of their pictures and scripts — so the network is
never asked.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from targum import ingest
from targum.errors import TargumError
from targum.ingest import fetch
from targum.ingest.fetch import storyweaver
from targum.ingest.fetch.storyweaver import (
    StoryWeaverFetcher,
    attribution,
    book_id,
    document_from,
    drop_capital_copies,
    english_in,
    page_text,
)
from targum.licensing import Standing, verdict
from targum.models import BlockKind

FIXTURES = Path(__file__).parent / "fixtures" / "storyweaver"
SAVED = {7686: "7686.it.json", 1124: "1124.fr.json", 234: "234.en.json"}


def saved(number: int) -> dict[str, Any]:
    body: dict[str, Any] = json.loads((FIXTURES / SAVED[number]).read_text(encoding="utf-8"))
    return body


def answering(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Every address the fetcher asks for, answered from the fixtures by its number."""
    asked: list[str] = []

    def get(url: str) -> str:
        asked.append(url)
        number = int(url.rstrip("/").split("/")[-2])
        return json.dumps(saved(number))

    monkeypatch.setattr(storyweaver, "get", get)
    return asked


def test_it_is_addressed_by_number_or_by_the_slug_in_the_address() -> None:
    assert fetch.is_identifier("storyweaver:7686")
    assert book_id("7686") == 7686
    assert book_id("7686-la-luna-e-il-cappello") == 7686
    with pytest.raises(TargumError, match="story number"):
        book_id("la-luna-e-il-cappello")


# -- the pages -----------------------------------------------------------------------------


def test_a_book_is_its_story_pages_one_paragraph_a_page(monkeypatch: pytest.MonkeyPatch) -> None:
    asked = answering(monkeypatch)
    document = ingest.load("storyweaver:7686")

    assert asked == ["https://storyweaver.org.in/api/v1/stories/7686/read"], "one call a book"
    assert document.source == "storyweaver:7686"
    assert document.language == "it"
    assert document.title == "LA LUNA E IL CAPPELLO"
    assert document.author == "Rohini Nilekani"
    kinds = [block.kind for block in document.blocks]
    assert kinds[:2] == [BlockKind.heading, BlockKind.byline]
    paragraphs = [block.text for block in document.blocks if block.kind is BlockKind.paragraph]
    assert len(paragraphs) == 11, "eleven story pages, and no cover or credits among them"
    assert paragraphs[0] == "Oggi sono andato con tutta la mia famiglia alla fiera."


def test_the_attribution_and_the_back_cover_are_not_the_book(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    answering(monkeypatch)
    body = ingest.load("storyweaver:7686").body()
    for furniture in ("Story Attribution", "Some rights reserved", "Level 1 book", "Pratham"):
        assert furniture not in body


def test_a_page_typed_twice_in_capitals_keeps_one_copy(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every page of 7686 is written once and then again in capitals underneath. Left in,
    each sentence is segmented, aligned and read twice."""
    answering(monkeypatch)
    body = ingest.load("storyweaver:7686").body()
    assert "OGGI SONO ANDATO" not in body
    assert body.count("Oggi sono andato") == 1


def test_the_copy_is_matched_without_its_accents() -> None:
    """The capitals are typed on a keyboard with no capital À: `Papà` is `PAPA'`."""
    page = ["Papà ha comprato un cappello.", "PAPA' HA COMPRATO UN CAPPELLO."]
    assert drop_capital_copies(page) == ["Papà ha comprato un cappello."]


def test_a_shortened_copy_is_still_a_copy() -> None:
    """Measured 0.80 on a real page: the translator dropped a clause as they retyped it."""
    page = [
        "Munia li vide camminare con le loro canne da pesca.",
        '"Stiamo andando al laghetto a pescare. Vieni con noi, Munia, se vuoi!".',
        "MUNIA LI VIDE CAMMINARE CON LE LORO CANNE DA PESCA.",
        '"VIENI CON NOI, MUNIA, SE VUOI!".',
    ]
    assert drop_capital_copies(page) == page[:2]


def test_a_shout_inside_the_story_is_part_of_the_story() -> None:
    page = ["CRAC!", '"Poi bisogna rompere il guscio..."']
    assert drop_capital_copies(page) == page


def test_a_page_in_capitals_throughout_is_written_that_way() -> None:
    page = ["TIMMI HA INSEGNATO AL SUO CANE A PENSARE."]
    assert drop_capital_copies(page) == page


def test_every_text_box_on_a_page_is_read_and_a_nested_paragraph_once() -> None:
    """The newer editor floats boxes over the picture and leaves the page's own box empty,
    and pasted text nests a <p> in a <p>. Reading the first box only, 135 of 1,020 books
    had no words; reading every <p>, a nested one came out twice."""
    html = (
        "<div class='content'> </div>"
        "<div class='newStories content'>"
        '<p><span>"Guarda&nbsp; Chuchu Manthu!"<br/></span></p></div>'
        "<div class='newStories content'><p><span><p><span>Bzzz… Ehi!</span></p></span></p>"
        "<p>Chuchu Manthu si\nvolta<br/>nella direzione.</p></div>"
    )
    assert (
        page_text(html)
        == '"Guarda Chuchu Manthu!" Bzzz… Ehi! Chuchu Manthu si volta nella direzione.'
    )


def test_a_book_with_no_words_says_so() -> None:
    data = saved(7686)["data"]
    data["pages"] = [page for page in data["pages"] if page["pageType"] != "StoryPage"]
    with pytest.raises(TargumError, match="no words"):
        document_from(7686, data, StoryWeaverFetcher.name)


# -- the attribution page -----------------------------------------------------------------


def test_the_licence_and_its_address_are_read_off_the_footer() -> None:
    credits = attribution(saved(7686)["data"])
    assert credits.licence == "CC BY 4.0"
    assert credits.licence_url == "http://creativecommons.org/licenses/by/4.0/"
    assert verdict(credits.licence).standing is Standing.owed


def test_the_credit_names_everybody_the_attribution_page_does() -> None:
    credits = attribution(saved(7686)["data"])
    assert credits.story.names == ("Silvia Lucchin",) and credits.story.made == "translated"
    assert credits.parent is not None and credits.parent.story == 1124
    assert credits.original is not None and credits.original.story == 234
    assert credits.credit == (
        "LA LUNA E IL CAPPELLO, translated by Silvia Lucchin (© Silvia Lucchin, 2016), "
        "from 'La lune et la casquette' by Annie Marois (© Annie Marois, 2015), "
        "based on 'The Moon and The Cap' by Rohini Nilekani (© Pratham Books, 2007). "
        "Illustrations by Angie & Upesh (© Pratham Books). Via StoryWeaver, Pratham Books."
    )


def test_an_original_is_credited_as_written() -> None:
    credits = attribution(saved(234)["data"])
    assert credits.parent is None and credits.original is None
    assert credits.credit.startswith(
        "The Moon and The Cap, written by Rohini Nilekani (© Pratham Books, 2007)."
    )


def _relicensed(number: int, span: str, licence: str) -> dict[str, Any]:
    """A saved book with one credit's terms changed, the way a real page states them."""
    data = saved(number)["data"]
    for page in data["pages"]:
        if page["pageType"] != "BackInnerCoverPage" or span not in page["html"]:
            continue
        head, tail = page["html"].split(span, 1)
        tail = tail.replace(
            "Released under CC BY 4.0 license", f"Released under {licence} license", 1
        )
        page["html"] = head + span + tail
    return data


@pytest.mark.parametrize(
    ("span", "named"),
    [
        ("self-attribution", "the text is under CC BY-NC 4.0"),
        ("parent-story-attribution", "'La lune et la casquette', which it came from"),
        ("original-story-attribution", "the original, 'The Moon and The Cap'"),
        ("illustration-attribution", "the picture on the cover page"),
    ],
)
def test_a_book_is_refused_when_any_credit_is_not_servable_and_says_which(
    span: str, named: str
) -> None:
    data = _relicensed(7686, span, "CC BY-NC 4.0")
    with pytest.raises(TargumError) as caught:
        document_from(7686, data, StoryWeaverFetcher.name)
    assert named in str(caught.value)
    assert "NonCommercial" in (caught.value.hint or "")


def test_a_credit_under_no_stated_licence_is_refused() -> None:
    """Silence is not a licence: `verdict` reads nothing written down as unknown."""
    data = _relicensed(7686, "self-attribution", "")
    with pytest.raises(TargumError, match="no stated licence"):
        document_from(7686, data, StoryWeaverFetcher.name)


def test_a_no_derivatives_footer_is_refused() -> None:
    data = saved(7686)["data"]
    for page in data["pages"]:
        page["html"] = page["html"].replace("licenses/by/4.0", "licenses/by-nd/4.0")
    with pytest.raises(TargumError, match="the book is under CC BY-ND 4.0"):
        document_from(7686, data, StoryWeaverFetcher.name)


def test_a_public_domain_book_is_served() -> None:
    """Pratham's oldest books are under the Public Domain Mark, and say so the same way."""
    data = saved(234)["data"]
    for page in data["pages"]:
        page["html"] = (
            page["html"]
            .replace(
                "http://creativecommons.org/licenses/by/4.0/",
                "http://creativecommons.org/about/pdm",
            )
            .replace(
                "Released under CC BY 4.0 license",
                "Released under Public Domain Mark by Pratham Books",
            )
        )
    credits = attribution(data)
    assert credits.licence == "Public Domain Mark"
    assert {licence for _, licence in credits.terms()} == {"Public Domain Mark"}
    assert document_from(234, data, StoryWeaverFetcher.name).language == "en"


def test_a_page_with_no_attribution_is_not_read() -> None:
    data = saved(7686)["data"]
    data["pages"] = [page for page in data["pages"] if page["pageType"] != "BackInnerCoverPage"]
    with pytest.raises(TargumError, match="no attribution page"):
        document_from(7686, data, StoryWeaverFetcher.name)


# -- the English it came from --------------------------------------------------------------


def test_the_english_is_found_through_a_language_in_between(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """7686 was translated from the French, and the French from the English: the walk goes
    through 1124 to 234, and stops at the first English it meets."""
    asked = answering(monkeypatch)
    assert StoryWeaverFetcher().english_source("7686") == "storyweaver:234"
    assert [url.split("/")[-2] for url in asked] == ["7686", "1124", "234"]


def test_an_english_parent_is_taken_before_the_original() -> None:
    data = saved(7686)["data"]
    asked: list[int] = []

    def read(number: int) -> dict[str, Any]:
        asked.append(number)
        upper = saved(1124)["data"]
        upper["language"] = "English"
        return upper

    assert english_in(7686, data, read) == "storyweaver:1124"
    assert asked == [1124]


def test_an_english_book_has_no_english_source() -> None:
    def never(number: int) -> dict[str, Any]:
        raise AssertionError("an English book is not walked")

    assert english_in(234, saved(234)["data"], never) is None


def test_a_chain_with_no_english_in_it_says_none() -> None:
    def read(number: int) -> dict[str, Any]:
        upper = saved(number)["data"]
        upper["language"] = "Hindi"
        return upper

    assert english_in(7686, saved(7686)["data"], read) is None


def test_the_terms_a_catalogue_row_carries(monkeypatch: pytest.MonkeyPatch) -> None:
    answering(monkeypatch)
    terms = StoryWeaverFetcher().terms("7686")
    assert terms.licence == "CC BY 4.0"
    assert terms.licence_url == "http://creativecommons.org/licenses/by/4.0/"
    assert terms.page == "https://storyweaver.org.in/stories/7686-la-luna-e-il-cappello"
    assert terms.credit.startswith("LA LUNA E IL CAPPELLO, translated by Silvia Lucchin")


def test_a_bot_check_is_named_as_one(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        storyweaver, "get", lambda url: "<!DOCTYPE html><title>Just a moment...</title>"
    )
    with pytest.raises(TargumError, match="something other than story 7686"):
        StoryWeaverFetcher().load("7686")
