"""Finding CC videos through the Data API, answered from recorded responses.

No test here reaches a network: `discover` takes its GET as a parameter, and every
answer below is shaped like the API's own (targum-internal#382).
"""

from __future__ import annotations

import math
from typing import Any

import pytest

from targum.errors import OffHere, TargumError
from targum.video import discover as d


def _item(
    identifier: str,
    *,
    licence: str = "creativeCommon",
    duration: str = "PT2M30S",
    privacy: str = "public",
    embeddable: bool = True,
    channel: str = "Kan Digital",
    language: str = "",
    live: str = "none",
) -> dict[str, Any]:
    snippet: dict[str, Any] = {
        "title": f"video {identifier}",
        "channelTitle": channel,
        "liveBroadcastContent": live,
    }
    if language:
        snippet["defaultAudioLanguage"] = language
    return {
        "id": identifier,
        "snippet": snippet,
        "contentDetails": {"duration": duration},
        "status": {
            "license": licence,
            "privacyStatus": privacy,
            "embeddable": embeddable,
            "uploadStatus": "processed",
        },
    }


class Recorded:
    """The API, from a script: each search answers with the next page of ids."""

    def __init__(self, pages: list[list[str]], items: dict[str, dict[str, Any]]) -> None:
        self.pages = list(pages)
        self.items = items
        self.calls: list[tuple[str, dict[str, str]]] = []

    def __call__(self, address: str, query: Any) -> dict[str, Any]:
        self.calls.append((address, dict(query)))
        if address == d.SEARCH:
            ids = self.pages.pop(0) if self.pages else []
            answer: dict[str, Any] = {"items": [{"id": {"videoId": i}} for i in ids]}
            if self.pages:
                answer["nextPageToken"] = "next"
            return answer
        assert address == d.VIDEOS
        wanted = query["id"].split(",")
        return {"items": [self.items[i] for i in wanted if i in self.items]}


def _run(api: Recorded, **options: Any) -> d.Found:
    options.setdefault("shelf", [])
    options.setdefault("api_key", "test-key")
    return d.discover(
        options.pop("languages", ["he"]), options.pop("count", 10), get=api, **options
    )


def test_licence_is_asked_again_and_the_second_answer_counts() -> None:
    api = Recorded(
        [["a", "b", "c"]],
        {"a": _item("a"), "b": _item("b", licence="youtube"), "c": _item("c")},
    )
    found = _run(api)
    assert [c.id for c in found.candidates] == ["a", "c"]
    assert found.dropped == {"not Creative Commons": 1}
    search = next(query for address, query in api.calls if address == d.SEARCH)
    assert search["videoLicense"] == "creativeCommon"
    assert search["relevanceLanguage"] == "he"
    assert search["videoEmbeddable"] == "true"
    assert search["videoDuration"] == "short"


def test_each_status_check_drops_with_its_reason() -> None:
    items = {
        "private": _item("private", privacy="unlisted"),
        "locked": _item("locked", embeddable=False),
        "tiny": _item("tiny", duration="PT12S"),
        "long": _item("long", duration="PT1H2M"),
        "nobody": _item("nobody", channel=" "),
        "russian": _item("russian", language="ru"),
        "live": _item("live", live="live"),
        "old-code": _item("old-code", language="iw"),
    }
    found = _run(Recorded([list(items)], items))
    assert [c.id for c in found.candidates] == ["old-code"]
    assert found.dropped == {
        "not public": 1,
        "not embeddable": 1,
        "too short": 1,
        "too long": 1,
        "names nobody to credit": 1,
        "in another language": 1,
        "live or upcoming": 1,
    }


def test_what_is_on_the_shelf_or_found_twice_is_not_asked_about() -> None:
    items = {i: _item(i) for i in ("held", "new", "again")}
    api = Recorded([["held", "new", "again"], ["again"]], items)
    found = _run(api, shelf=["held"])
    assert [c.id for c in found.candidates] == ["new", "again"]
    assert found.dropped == {"already on the shelf": 1, "found twice": 1}
    asked = [query["id"] for address, query in api.calls if address == d.VIDEOS]
    assert asked == ["new,again"]


def test_the_count_is_per_language_and_stops_the_asking() -> None:
    items = {f"{p}{n}": _item(f"{p}{n}") for p in "vw" for n in range(6)}
    api = Recorded([[f"v{n}" for n in range(6)], [f"w{n}" for n in range(6)]], items)
    found = _run(api, count=2, languages=["ru"])
    # One from each term in turn, so the second comes from the second term's search.
    assert [c.id for c in found.candidates] == ["v0", "w0"]
    assert [c.found_by for c in found.candidates] == list(d.TOPICS["ru"][:2])
    assert sum(1 for address, _ in api.calls if address == d.SEARCH) == 2


def test_the_budget_stops_the_next_search_and_says_so() -> None:
    items = {f"v{n}": _item(f"v{n}", licence="youtube") for n in range(50)}
    pages = [[f"v{n}"] for n in range(50)]
    api = Recorded(pages, items)
    found = _run(api, budget=350)
    searches = sum(1 for address, _ in api.calls if address == d.SEARCH)
    assert searches == 3
    assert found.units == 3 * (d.SEARCH_UNITS + d.VIDEOS_UNITS)
    assert found.units <= 350
    assert found.short


def test_quota_refuses_an_overrun() -> None:
    quota = d.Quota(budget=150)
    quota.spend(100)
    with pytest.raises(d.OverBudget):
        quota.spend(100)
    assert quota.used == 100


def test_a_missing_key_is_a_plain_refusal(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(d.KEY_ENV, raising=False)
    with pytest.raises(OffHere) as refused:
        d.discover(["he"], 1, get=Recorded([], {}), shelf=[])
    assert d.KEY_ENV in refused.value.message


def test_an_unknown_language_is_refused() -> None:
    with pytest.raises(TargumError):
        d.discover(["xx"], 1, get=Recorded([], {}), shelf=[], api_key="k")


def test_fetch_asks_only_the_api() -> None:
    with pytest.raises(TargumError):
        d.fetch("https://example.com/youtube/v3/search", {})


@pytest.mark.parametrize(
    ("clock", "expected"),
    [
        ("PT2M30S", 150),
        ("PT45S", 45),
        ("PT1H", 3600),
        ("PT1H2M3S", 3723),
        ("P1DT1S", 86401),
        ("", 0),
        ("x", 0),
    ],
)
def test_durations_are_read(clock: str, expected: int) -> None:
    assert d.seconds(clock) == expected


def test_the_estimate_is_the_pipelines_arithmetic() -> None:
    from targum.audio import SPEECH_WORDS_PER_MINUTE, TOKENS_PER_SPOKEN_WORD, WORDS_PER_SENTENCE
    from targum.transcribe import PRICES
    from targum.transcribe.refine import Punctuator
    from targum.translate.anthropic_provider import AnthropicProvider

    hearing, translating = d.estimate(180)
    rate = max(PRICES.values())
    assert hearing == pytest.approx(3 * (rate + Punctuator().dollars_per_minute()))
    provider = AnthropicProvider()
    words = 3 * SPEECH_WORDS_PER_MINUTE
    batches = max(1, math.ceil(words / WORDS_PER_SENTENCE / provider.batch_size))
    assert translating == pytest.approx(
        provider.estimate_from_counts(words * TOKENS_PER_SPOKEN_WORD, batches)
    )
    assert d.estimate(360)[0] == pytest.approx(2 * hearing)


def test_the_batch_total_is_the_sum_and_the_table_says_it() -> None:
    items = {"a": _item("a", duration="PT1M"), "b": _item("b", duration="PT3M")}
    found = _run(Recorded([["a", "b"]], items), languages=["ru"])
    assert found.total == pytest.approx(sum(c.cost for c in found.candidates))
    printed = d.table(found)
    assert "| [ ] | ru | — | video a | Kan Digital | CC BY 3.0 | 1:00 |" in printed
    assert "https://www.youtube.com/watch?v=b" in printed
    assert "2 candidates, 4 minutes" in printed
    assert f"${found.total:.2f}" in printed
    written = d.to_json(found)
    assert written["units"] == found.units
    assert [c["id"] for c in written["candidates"]] == ["a", "b"]


def test_a_search_answering_more_than_fifty_is_asked_about_in_fifties() -> None:
    # The first real Hebrew run: a search asked for 50 answered with 53, and one
    # videos.list call for all 53 came back 400 (2026-09-29).
    items = {f"v{n}": _item(f"v{n}") for n in range(53)}
    api = Recorded([list(items)], items)
    found = _run(api, count=53, languages=["ru"])
    asked = [query["id"].split(",") for address, query in api.calls if address == d.VIDEOS]
    assert [len(ids) for ids in asked] == [50, 3]
    assert len(found.candidates) == 53
    searches = len(d.TOPICS["ru"])  # the short band only: it held all 53
    assert found.units == searches * d.SEARCH_UNITS + 2 * d.VIDEOS_UNITS


class ByTerm(Recorded):
    """The API, answering each search by its term: one page per term, then nothing."""

    def __init__(self, by_term: dict[str, list[str]], items: dict[str, dict[str, Any]]) -> None:
        super().__init__([], items)
        self.by_term = {term: list(ids) for term, ids in by_term.items()}

    def __call__(self, address: str, query: Any) -> dict[str, Any]:
        if address != d.SEARCH:
            return super().__call__(address, query)
        self.calls.append((address, dict(query)))
        return {"items": [{"id": {"videoId": i}} for i in self.by_term.pop(query["q"], [])]}


def test_hebrew_is_asked_subject_by_subject_in_even_shares() -> None:
    # targum-internal#386: four subjects, each held to its share, so a batch of eight
    # is two of each even when one subject's first term could fill it alone.
    by_term = {
        terms[0]: [f"{n}-{k}" for k in range(10)]
        for n, terms in enumerate(d.SUBJECTS["he"].values())
    }
    items = {i: _item(i) for ids in by_term.values() for i in ids}
    found = _run(ByTerm(by_term, items), count=8)
    subjects = [c.subject for c in found.candidates]
    assert subjects == [s for s in d.SUBJECTS["he"] for _ in range(2)]
    assert "| [ ] | he | health |" in d.table(found)


def test_a_subject_is_spread_over_its_terms() -> None:
    # The first real run filled every subject from its first term; ארנונה and the rest
    # were never asked (2026-09-30). Each term now gives one before any gives a second.
    money = d.SUBJECTS["he"]["bureaucracy and money"]
    by_term = {term: [f"{n}-{k}" for k in range(5)] for n, term in enumerate(money)}
    items = {i: _item(i) for ids in by_term.values() for i in ids}
    found = _run(ByTerm(by_term, items), count=4 * len(money))
    first = [c for c in found.candidates if c.subject == "bureaucracy and money"]
    assert [c.found_by for c in first] == list(money)


def test_an_unsteered_language_has_no_subject() -> None:
    items = {"a": _item("a")}
    found = _run(Recorded([["a"]], items), count=1, languages=["fr"])
    assert [c.subject for c in found.candidates] == [""]


def test_music_and_a_rival_script_are_dropped() -> None:
    song = _item("song")
    song["snippet"]["categoryId"] = "10"
    russian = _item("russian")
    russian["snippet"]["title"] = "Приглашаем в детсад ארץ הקטקטים"
    mixed = _item("mixed")
    mixed["snippet"]["title"] = "VLOG פסטיבל התלתלים"
    assert d.check(song, "he") == "music"
    assert d.check(russian, "he") == "titled in another script"
    assert d.check(mixed, "he") == ""
    assert d.check(russian, "ru") == ""


def test_an_earlier_batch_is_skipped_like_the_shelf() -> None:
    items = {i: _item(i) for i in ("listed", "new")}
    found = _run(Recorded([["listed", "new"]], items), count=2, languages=["ru"], skip=["listed"])
    assert [c.id for c in found.candidates] == ["new"]
    assert found.dropped == {"already on the shelf": 1}
