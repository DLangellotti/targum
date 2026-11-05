"""Russian in the finds doors: Find me something's chips, the live look, YouTube, the web
night and the wikis (targum-internal#635; David, 2026-11-05).

Each door is run for Russian against fakes, and Hebrew is checked to be as it was.
Offline: no search, API, wiki or yt-dlp is reached, and nothing is spent. Every word is
synthetic. The Russian phrases are ling-ru's draft of 2026-11-05, awaiting David's read.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from urllib.parse import parse_qs, urlparse

import pytest

from targum import level as level_module
from targum.accounts import Store
from targum.finds import button, chips, live, pool, robots, score, screen, web, wiki
from targum.finds import youtube as finds_youtube
from targum.video import discover

AT = int(datetime(2026, 11, 30, 0, 12, tzinfo=UTC).timestamp() * 1000)
GONE = {"israel", "holidays", "army"}

LETTERS = "бвгдклмнпрст"


def general(n: int) -> str:
    return "слово" + LETTERS[n // len(LETTERS)] + LETTERS[n % len(LETTERS)]


G1, G2 = general(1), general(2)


def page(n: int) -> str:
    """A long enough Russian page, each one different so none is pooled as a copy."""
    return " ".join(["дом"] * 6 + [G1] * (90 + n) + [G2] * 4)


def forms() -> score.Forms:
    words = ["дом", G1, G2]
    return score.Forms(
        language="ru",
        forms={word: word for word in words},
        ranks={word: at + 1 for at, word in enumerate(words)},
    )


@pytest.fixture(autouse=True)
def quiet(monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory) -> None:
    for flag in (web.FLAG, wiki.FLAG, finds_youtube.FLAG, pool.BUDGET_ENV):
        monkeypatch.delenv(flag, raising=False)
    monkeypatch.delenv(finds_youtube.UNITS_ENV, raising=False)
    monkeypatch.setenv("TARGUM_SOURCES", str(tmp_path_factory.mktemp("sources") / "absent.json"))


@pytest.fixture
def store(tmp_path: Path) -> Store:
    return Store(tmp_path / "targum.db")


def languages_kept(store: Store) -> list[str]:
    return [str(row[0]) for row in store.db.execute("SELECT language FROM find ORDER BY id")]


# -- the chips -----------------------------------------------------------------------


def test_russian_has_a_phrase_for_every_chip_but_the_three_david_left_out() -> None:
    """No `israel` or `holidays` (no Russian equivalent) and no `army` (hidden for
    Russian), David, 2026-11-05; every other chip has ling-ru's phrase, without ё."""
    without = {chip.code for chip in chips.CHIPS if not chip.phrases.get("ru")}
    assert without == GONE
    assert set(chips.PHRASES_RU) == set(chips.BY_CODE) - GONE
    assert all("ё" not in phrase for phrase in chips.PHRASES_RU.values())
    assert chips.phrase("football", "ru") == "футбол"
    assert chips.LANGUAGES == ("he", "ru")


def test_a_russian_reader_is_not_offered_a_chip_with_no_russian_phrase() -> None:
    russian = [chip.code for chip, _ in chips.ordered(["security", "religion"], "ru")]
    assert not GONE & set(russian) and len(russian) == len(chips.CHIPS) - 3
    assert not chips.offered("israel", "ru") and chips.offered("israel", "he")
    # Hebrew is as it was: every chip, the likely ones first.
    assert chips.ordered(["security"], "he") == chips.ordered(["security"])
    assert [chip.code for chip, _ in chips.ordered(["security"], "he")][:1] == ["army"]
    # A language with no phrases at all keeps every chip, as before.
    assert len(chips.ordered([], "fr")) == len(chips.CHIPS)


# -- the live look -------------------------------------------------------------------


def test_a_russian_look_asks_the_chips_phrase_with_the_level_words_by_rung() -> None:
    """РКИ at A1–A2, «простым языком» at B1, nothing past it (David, 2026-11-05)."""
    assert live.queries(["football"], "ru", 0) == ("футбол РКИ",)
    assert live.queries(["football"], "ru", 1) == ("футбол РКИ",)
    assert live.queries(["football"], "ru", 2) == ("футбол простым языком",)
    assert live.queries(["football"], "ru", 3) == ("футбол",)
    assert live.queries(["football", "cooking"], "ru-RU", 4) == ("футбол", "кулинарные рецепты")
    assert live.queries([], "ru", None) == ("повседневная жизнь РКИ",)
    assert live.queries(["israel"], "ru", 3) == ("повседневная жизнь",), "no phrase, any topic"
    assert set(live.TOPIC_WORDS["ru"]) == set(live.TOPIC_WORDS["he"])
    # Hebrew is as it was.
    assert live.queries(["football"], "he", 2) == ("כדורגל בעברית קלה",)
    assert live.queries(["football"], "he", 3) == ("כדורגל",)


def test_a_russian_look_tells_the_model_the_language_is_russian() -> None:
    sent: list[dict[str, Any]] = []

    def create(**kwargs: Any) -> Any:
        sent.append(kwargs)
        return SimpleNamespace(content=[], usage=SimpleNamespace(input_tokens=1, output_tokens=1))

    live.search(SimpleNamespace(messages=SimpleNamespace(create=create)), ("футбол РКИ",), "ru")
    assert "written in Russian" in sent[0]["system"]
    assert sent[0]["messages"][0]["content"] == "Query: футбол РКИ"


def test_a_russian_readers_rung_is_counted_on_the_cefr_as_the_pool_counts_it() -> None:
    cefr = level_module.CEFR_LADDER.rungs
    at_b1 = replace(level_module.EMPTY, language="ru", here=cefr[2])
    assert button.rung_for(at_b1, "ru") == 2
    nothing = replace(level_module.EMPTY, language="ru", here=None)
    assert button.rung_for(nothing, "ru") == 0, "unmeasured is the first rung"
    assert button.rung_for(at_b1, "fr") is None, "no pool for French yet"


# -- YouTube -------------------------------------------------------------------------

RU_VIDEO = {
    "kind": "youtube#video",
    "id": "ruVideo0001",
    "snippet": {
        "publishedAt": "2026-11-20T08:00:00Z",
        "channelId": "UCruVideo0001",
        "title": "Рецепт борща за десять минут",
        "description": "",
        "channelTitle": "Пример канала",
        "categoryId": "22",
        "liveBroadcastContent": "none",
        "defaultAudioLanguage": "ru",
    },
    "contentDetails": {"duration": "PT6M10S", "caption": "true", "contentRating": {}},
    "status": {
        "uploadStatus": "processed",
        "privacyStatus": "public",
        "license": "youtube",
        "embeddable": True,
    },
}


class Tube:
    def __init__(self) -> None:
        self.asked: list[dict[str, str]] = []

    def __call__(self, address: str, query: Mapping[str, str]) -> dict[str, Any]:
        if address == discover.SEARCH:
            self.asked.append(dict(query))
            return {"items": [{"id": {"videoId": "ruVideo0001"}}]}
        wanted = set(query.get("id", "").split(","))
        return {"items": [RU_VIDEO] if "ruVideo0001" in wanted else []}


def test_a_russian_night_on_youtube_pools_a_russian_video(store: Store) -> None:
    tube, fetched = Tube(), []

    def fetch(url: str) -> finds_youtube.Track:
        fetched.append(url)
        return finds_youtube.Track(text=page(0), size=2_000)

    found = finds_youtube.refresh(
        store,
        language="ru",
        get=tube,
        api_key="test-key",
        fetch=fetch,
        forms_for=lambda language: forms(),
        budget_units=101,
        at=AT,
    )
    assert found.kept == 1 and languages_kept(store) == ["ru"]
    assert tube.asked[0]["q"] == "спорт" and tube.asked[0]["relevanceLanguage"] == "ru"
    asked = [query.words for query in finds_youtube.queries("ru")]
    assert "армия и военная служба" not in asked and asked[-3:] == list(finds_youtube.EASY["ru"])
    # Its rotation is its own: a Russian night does not move Hebrew's.
    assert pool.last_next(store, finds_youtube.SOURCE, "ru") == 1
    assert pool.last_next(store, finds_youtube.SOURCE, "he") == 0


def test_a_russian_track_is_asked_for_in_russian(monkeypatch: pytest.MonkeyPatch) -> None:
    from targum.video import youtube as video_youtube

    asked: list[tuple[Any, ...]] = []

    def ran(url: str, into: Path, *languages: Any) -> tuple[None, dict[str, Any]]:
        asked.append(languages)
        return None, {"age_limit": 0}

    monkeypatch.setattr(video_youtube, "subtitles_for_finding", ran)
    finds_youtube.track("https://www.youtube.com/watch?v=ruVideo0001", "ru")
    finds_youtube.track("https://www.youtube.com/watch?v=heVideo0001")
    assert asked == [(("ru",),), ()], "Hebrew's call is as it was"


# -- the web night -------------------------------------------------------------------

ALLOW = robots.Robots(read=lambda url: "User-agent: *\nDisallow: /no/\n")


def test_a_russian_web_night_searches_the_russian_phrases_and_pools_russian(
    store: Store,
) -> None:
    asked: list[str] = []
    first = chips.PHRASES_RU["sport"]

    def ask(query: str) -> web.Searched:
        asked.append(query)
        hits = [web.Hit("https://blog.example.ru/a", "Спорт")] if query == first else []
        return web.Searched(hits=hits, searches=1, cost=0.03)

    found = web.refresh(
        store,
        language="ru",
        ask=ask,
        read=lambda url: (page(1), 0),
        robots=ALLOW,
        forms_for=lambda language: forms(),
        publishers=[],
        lean={},
        at=AT,
    )
    assert (
        asked and asked[0] == first and all(query in chips.PHRASES_RU.values() for query in asked)
    )
    assert found.kept == 1 and languages_kept(store) == ["ru"]
    assert pool.last_next(store, web.RUN_SOURCE, "he") == 0, "Hebrew's rotation untouched"


def test_the_nights_dollar_is_shared_so_russian_has_what_hebrew_left(store: Store) -> None:
    """The $1 is the night's, not each language's: no new spend for Russian."""
    run = pool.start_run(store, web.RUN_SOURCE, AT)
    pool.spend(store, run, web.NIGHT_USD)
    pool.finish_run(store, run, note={"next": 7}, at=AT)
    asked: list[str] = []
    found = web.refresh(
        store,
        language="ru",
        ask=lambda query: asked.append(query) or web.Searched(),
        read=lambda url: ("", 0),
        robots=ALLOW,
        forms_for=lambda language: forms(),
        publishers=[],
        lean={},
        at=AT,
    )
    assert asked == [] and found.stopped.startswith("the night's $")
    assert pool.last_next(store, web.RUN_SOURCE, "he") == 7, "an old note is Hebrew's"


# -- the wikis -----------------------------------------------------------------------


class Wikis:
    def __init__(self) -> None:
        self.searched: list[tuple[str, str]] = []

    def __call__(self, url: str) -> Any:
        parsed = urlparse(url)
        host = parsed.hostname or ""
        asked = {key: values[0] for key, values in parse_qs(parsed.query).items()}
        if asked.get("generator") == "search":
            phrase = asked["gsrsearch"]
            self.searched.append((host, phrase))
            title = phrase.replace(" ", "_")
            row = {"ns": 0, "title": phrase, "index": 1}
            return {"query": {"pages": [{**row, "canonicalurl": f"https://{host}/wiki/{title}"}]}}
        text = page(len(self.searched))
        return {"query": {"pages": [{"ns": 0, "title": asked["titles"], "extract": text}]}}


def test_a_russian_night_reads_russian_wikipedia_and_wikivoyage_only(store: Store) -> None:
    api = Wikis()
    found = wiki.refresh(
        store,
        language="ru",
        get=api,
        robots=robots.Robots(read=lambda url: "User-agent: *\nDisallow: /w/\n"),
        forms_for=lambda language: forms(),
        at=AT,
    )
    hosts = {host for host, _ in api.searched}
    assert hosts == {"ru.wikipedia.org", "ru.wikivoyage.org"}
    on_wv = [phrase for host, phrase in api.searched if host == "ru.wikivoyage.org"]
    travel = [chips.PHRASES_RU[one] for one in ("food", "travel", "history", "nature")]
    assert sorted(on_wv) == sorted(travel), "no israel or holidays in Russian"
    assert found.kept == web.HOST_MOST + len(travel) and set(languages_kept(store)) == {"ru"}
    licences = {str(row[0]) for row in store.db.execute("SELECT licence FROM find")}
    assert licences == {wiki.LICENCE}
    note = json.loads(
        store.db.execute("SELECT note FROM find_run WHERE source = 'wiki'").fetchone()[0]
    )
    assert note["language"] == "ru" and set(note["next"]) == hosts


def test_a_hebrew_wiki_night_still_reads_only_the_hebrew_wikis(store: Store) -> None:
    api = Wikis()
    he_forms = score.Forms(language="he", forms={"בית": "בית"}, ranks={"בית": 1})
    wiki.refresh(store, get=api, forms_for=lambda language: he_forms, at=AT, robots=ALLOW)
    assert {host for host, _ in api.searched} == {"he.wikipedia.org", "he.wikivoyage.org"}


# -- the screen ----------------------------------------------------------------------


def test_the_russian_screen_holds_on_every_door() -> None:
    assert screen.term_in("Порнография и прочее") == "Порнограф"
    assert screen.passes("blog.example.ru", "Эротические рассказы") == "words"
    assert screen.term_in("футбол простым языком") == ""
