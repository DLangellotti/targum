"""Global Storybooks stories, by site, number and language.

Everything here runs against recorded files from the `global-asp` source repositories —
Storybooks Canada's *A very tall man* in Russian and English and *I like to read!* in
English, and LIDA's *Finding a job* in Russian — against GitHub's folder listings for
those folders, trimmed to four stories, and against one file written here in the same
shape under a NonCommercial line, so the network is never asked.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from urllib.parse import unquote

import pytest

from targum import ingest
from targum.errors import TargumError, Unreachable
from targum.ingest import fetch
from targum.ingest.fetch import globalstorybooks
from targum.ingest.fetch.globalstorybooks import GlobalStorybooksFetcher, address, credit, parse
from targum.licensing import Standing, verdict
from targum.models import BlockKind

FIXTURES = Path(__file__).parent / "fixtures" / "globalstorybooks"


@pytest.fixture(autouse=True)
def no_listings_kept() -> Iterator[None]:
    """A listing kept by one test would answer the next one without asking."""
    globalstorybooks._listings.clear()
    yield
    globalstorybooks._listings.clear()


def answering(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Every address the fetcher asks for, answered from the fixtures."""
    asked: list[str] = []

    def get(url: str) -> str:
        asked.append(url)
        if url.startswith("https://api.github.com/"):
            # .../repos/global-asp/sbc-source/contents/ru?ref=master
            repo, _, language = url.split("?")[0].split("/")[-3:]
            listing = FIXTURES / repo.removesuffix("-source") / f"{language}.json"
            if not listing.is_file():
                raise Unreachable("no such folder", status=404)
            return listing.read_text(encoding="utf-8")
        # .../global-asp/sbc-source/master/ru/0001_очень-высокий-человек.md
        repo, _, language, name = unquote(url).split("/")[-4:]
        story = FIXTURES / repo.removesuffix("-source") / language / f"{name[:4]}.md"
        return story.read_text(encoding="utf-8")

    monkeypatch.setattr(globalstorybooks, "get", get)
    return asked


def saved(path: str) -> str:
    return (FIXTURES / path).read_text(encoding="utf-8")


def test_it_is_addressed_by_site_number_and_language() -> None:
    assert fetch.is_identifier("globalstorybooks:sbc/0001/ru")
    where = address("sbc/1/ru")
    assert (where.site, where.story, where.language) == ("sbc", "0001", "ru")
    assert where.key == "globalstorybooks:sbc/0001/ru"
    assert address("LIDA/0014/RU").key == "globalstorybooks:lida/0014/ru"
    with pytest.raises(TargumError, match="site/number/language"):
        address("sbc/0001")
    with pytest.raises(TargumError, match="no site"):
        address("storyweaver/0001/ru")
    with pytest.raises(TargumError, match="not a story number"):
        address("sbc/very-tall-man/ru")


# -- the file ------------------------------------------------------------------------------


def test_a_story_is_one_paragraph_a_page_under_its_title(monkeypatch: pytest.MonkeyPatch) -> None:
    asked = answering(monkeypatch)
    document = ingest.load("globalstorybooks:sbc/0001/ru")

    assert asked[0] == "https://api.github.com/repos/global-asp/sbc-source/contents/ru?ref=master"
    assert unquote(asked[1]) == (
        "https://raw.githubusercontent.com/global-asp/sbc-source/master/ru/"
        "0001_очень-высокий-человек.md"
    )
    assert len(asked) == 2, "one listing and one file"
    assert document.source == "globalstorybooks:sbc/0001/ru"
    assert document.language == "ru"
    assert document.title == "Очень высокий человек"
    assert document.author == "Cornelius Gulere"
    kinds = [block.kind for block in document.blocks]
    assert kinds[:2] == [BlockKind.heading, BlockKind.byline]
    paragraphs = [block.text for block in document.blocks if block.kind is BlockKind.paragraph]
    assert len(paragraphs) == 11, "eleven pages, and the list of credits is not one of them"
    assert paragraphs[0] == "Тяпка была для него слишком короткая."
    assert paragraphs[-1] == "Он ушёл из своего дома и жил в большом лесу. Он прожил много лет."
    assert not any("License" in text or "Ania Voznaia" in text for text in paragraphs)


def test_a_page_over_several_lines_is_one_paragraph() -> None:
    story = parse("# Two lines\n\n##\nWhy do I work so hard...\n\n... while my brother plays?\n")
    assert story.pages == ("Why do I work so hard... ... while my brother plays?",)


def test_the_foot_of_the_file_is_what_the_story_owes() -> None:
    story = parse(saved("sbc/ru/0001.md"))
    assert story.licence_as_written == "[CC-BY]"
    assert story.licence == "CC BY"
    assert story.fields["illustration"] == "Catherine Groenewald"
    assert story.fields["translation"] == "Ania Voznaia"
    assert story.words() == 76, "the pages' words, and not the title's or the credits'"


def test_both_ways_of_writing_a_licence_read_the_same() -> None:
    lida = parse(saved("lida/ru/0001.md"))
    assert lida.licence_as_written == "CC BY" and lida.licence == "CC BY"
    written = parse("# T\n\n##\nA page.\n\n##\n* License: [CC-BY-NC]\n")
    assert written.licence == "CC BY-NC"
    assert verdict(written.licence).standing is Standing.closed


def test_the_credit_names_everybody_the_file_does() -> None:
    line = credit(parse(saved("sbc/ru/0001.md")), "sbc")
    assert line == (
        "Очень высокий человек, text by Cornelius Gulere, illustrations by Catherine "
        "Groenewald, translated by Ania Voznaia. Via Storybooks Canada, Global Storybooks."
    )
    english = credit(parse(saved("sbc/en/0087.md")), "sbc")
    assert "translated by Letta Machoga" in english, "the English's own `Translated By`"


# -- the licence -----------------------------------------------------------------------------


def test_a_noncommercial_story_is_refused_with_its_terms_named(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    answering(monkeypatch)
    with pytest.raises(TargumError, match=r"sbc/0002/ru is not ours to use.*\[CC-BY-NC\]"):
        ingest.load("globalstorybooks:sbc/0002/ru")


def test_a_story_with_no_licence_line_is_refused() -> None:
    where = address("sbc/0001/ru")
    story = parse("# Untold\n\n##\nA page.\n")
    with pytest.raises(TargumError, match="no stated licence"):
        globalstorybooks.document_from(where, story, "globalstorybooks/1")


def test_the_terms_are_read_off_the_file(monkeypatch: pytest.MonkeyPatch) -> None:
    answering(monkeypatch)
    terms = GlobalStorybooksFetcher().terms("lida/0001/ru")
    assert terms.licence == "CC BY"
    assert terms.credit.startswith("Поиск работы, text by Espen Stranger-Johannessen")
    assert terms.credit.endswith("translated by Liubov Denoi. Via LIDA Stories, Global Storybooks.")
    assert unquote(terms.page) == (
        "https://github.com/global-asp/lida-source/blob/master/ru/0001_поиск-работы.md"
    )


# -- the English beside it -------------------------------------------------------------------


def test_the_english_is_the_same_number_in_the_english_folder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    answering(monkeypatch)
    fetcher = GlobalStorybooksFetcher()
    assert fetcher.english_source("sbc/0001/ru") == "globalstorybooks:sbc/0001/en"
    assert fetcher.english_source("sbc/0001/en") is None, "an English story is the English"
    assert fetcher.english_source("lida/0001/ru") is None, "no English folder recorded for LIDA"

    english = ingest.load("globalstorybooks:sbc/0001/en")
    assert english.language == "en" and english.title == "A very tall man"
    paragraphs = [block.text for block in english.blocks if block.kind is BlockKind.paragraph]
    assert len(paragraphs) == 11, "page for page with the Russian"


def test_a_folder_is_listed_once_a_process(monkeypatch: pytest.MonkeyPatch) -> None:
    asked = answering(monkeypatch)
    ingest.load("globalstorybooks:sbc/0001/ru")
    GlobalStorybooksFetcher().terms("sbc/0001/ru")
    assert sum(url.startswith("https://api.github.com/") for url in asked) == 1


def test_a_story_the_site_does_not_have_says_where_to_look(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    answering(monkeypatch)
    with pytest.raises(TargumError, match="Storybooks Canada has no story 0005 in 'ru'"):
        ingest.load("globalstorybooks:sbc/0005/ru")
    with pytest.raises(TargumError, match="no story 0001 in 'he'"):
        ingest.load("globalstorybooks:sbc/0001/he")


def test_a_github_that_stops_answering_says_to_wait(monkeypatch: pytest.MonkeyPatch) -> None:
    def get(url: str) -> str:
        raise Unreachable("rate limited", status=403)

    monkeypatch.setattr(globalstorybooks, "get", get)
    with pytest.raises(TargumError, match="GitHub stopped listing") as refused:
        ingest.load("globalstorybooks:sbc/0001/ru")
    assert refused.value.hint is not None and "Wait an hour" in refused.value.hint
