"""Your Progress's story (design.md §12, "Your Progress is a story in three parts",
2026-10-09): the ladder of kinds of text, where a reader is on it, the texts at their level
and the words they keep meeting.

The arithmetic in `touchstones`, then the whole of `/account/story` end to end.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
import test_serve
from test_reading_line import built, ms, word
from test_serve import Postbox, call, sign_in

from targum import touchstones
from targum.coverage import KNOWN, build_index

served = test_serve.served
postbox = test_serve.postbox


@dataclass(frozen=True)
class Entry:
    id: str
    language: str
    kind: str
    difficulty: int
    title: str = ""
    english: str = ""
    author: str = ""
    named: dict[str, str] = field(default_factory=dict)


def shelf() -> list[Entry]:
    """A Hebrew shelf of four kinds, and one Russian story."""
    return [
        Entry("d1", "he", "dialogue", 6, "שיחה"),
        Entry("d2", "he", "dialogue", 8, "שיחה ב"),
        Entry("d0", "he", "dialogue", 0, "לא נמדד"),
        Entry("a1", "he", "article", 17, "ידיעה", english="A report"),
        Entry("t1", "he", "talk", 14, "הרצאה"),
        Entry("p1", "he", "poetry", 25, "שיר"),
        # Not a touchstone kind: it stays on its shelf and off the ladder.
        Entry("x1", "he", "prose", 19, "בראשית"),
        Entry("r1", "ru", "story", 22, "Муму"),
    ]


def test_the_ladder_is_the_kinds_by_their_median_measured_difficulty() -> None:
    rungs = touchstones.ladder(shelf(), "he")
    assert [rung.kind for rung in rungs] == ["dialogue", "talk", "article", "poetry"]
    assert rungs[0].difficulty == 7, "the unmeasured dialogue is not counted as easy"
    assert "x1" not in {text for rung in rungs for text in rung.texts}


def test_aramaic_and_an_empty_library_have_no_ladder() -> None:
    """wordfreq has no Aramaic list, so every Aramaic text measures 0, which is false."""
    arc = [Entry("o1", "arc", "prose", 0), Entry("o2", "arc", "poetry", 12)]
    assert touchstones.ladder(arc, "arc") == []
    assert touchstones.ladder(shelf(), "yi") == []


def test_italian_stories_are_its_childrens_books() -> None:
    """StoryWeaver's children's books, said in everyday words: "what is a picture book?"
    (David, 2026-10-09). The rung still opens the story shelf."""
    rungs = touchstones.ladder([Entry("i1", "it", "story", 13)], "it")
    assert [(rung.kind, rung.name) for rung in rungs] == [("story", "children-book")]


@pytest.mark.parametrize(
    ("share", "said"),
    [
        (100, "follow"),
        (95, "follow"),
        (94, "nearly"),
        (90, "nearly"),
        (89, "most"),
        (75, "most"),
        (74, ""),
    ],
)
def test_the_wording_is_by_the_share_of_running_words(share: int, said: str) -> None:
    assert touchstones.said(share) == said


def index_of(texts: dict[str, dict[str, int]]) -> Any:
    """An index with running counts: entry -> {lemma: how often}."""
    return build_index({entry: list(counts) for entry, counts in texts.items()}, texts)


def test_a_share_is_of_running_words_not_of_distinct_ones() -> None:
    """Known: the one word that comes round nine times in ten. Of its distinct words
    that is half; of its running words, nine in ten."""
    index = index_of({"a1": {"common": 9, "rare": 1}})
    assert touchstones.running_share(index, "a1", {"common": KNOWN}) == pytest.approx(0.9)
    assert touchstones.running_share(index, "nowhere", {"common": KNOWN}) is None


def test_a_share_falls_back_to_distinct_words_where_nothing_was_counted() -> None:
    index = index_of({"a1": {"common": 9, "rare": 1}})
    index.counts.clear()
    assert touchstones.running_share(index, "a1", {"common": KNOWN}) == pytest.approx(0.5)


def test_here_is_the_hardest_rung_followed_and_the_next_one_after_it() -> None:
    rungs = touchstones.ladder(shelf(), "he")
    index = index_of(
        {
            "d1": {"שלום": 10},
            "d2": {"שלום": 10},
            "t1": {"שלום": 19, "מדע": 1},
            "a1": {"שלום": 93, "חדשות": 7},
            "p1": {"שלום": 86, "שיר": 14},
        }
    )
    got = touchstones.standing(rungs, index, {"שלום": KNOWN})
    assert [(rung["kind"], rung["state"], rung["share"]) for rung in got["ladder"]] == [
        ("dialogue", "passed", 100),
        ("talk", "passed", 95),
        ("article", "here", 93),
        ("poetry", "next", 86),
    ]
    assert got["said"] == "nearly"


def test_with_nothing_at_ninety_here_is_the_hardest_at_seventy_five() -> None:
    rungs = touchstones.ladder(shelf(), "he")
    index = index_of({"d1": {"a": 8, "b": 2}, "t1": {"a": 3, "b": 7}})
    got = touchstones.standing(rungs, index, {"a": KNOWN})
    assert got["here"] == 0 and got["said"] == "most"
    assert [rung["state"] for rung in got["ladder"]] == ["here", "next", "ahead", "ahead"]
    # The article and the poem were never measured: no share, never 0%.
    assert got["ladder"][2]["share"] is None


def test_with_no_rung_reached_the_first_is_the_place_to_start() -> None:
    rungs = touchstones.ladder(shelf(), "he")
    got = touchstones.standing(rungs, index_of({"d1": {"a": 1, "b": 9}}), {"a": KNOWN})
    assert got["here"] is None and got["said"] == ""
    assert [rung["state"] for rung in got["ladder"]] == ["next", "ahead", "ahead", "ahead"]


def test_texts_at_your_level_are_ninety_and_up_nearest_the_line_first() -> None:
    index = index_of(
        {
            "a1": {f"w{n}": 1 for n in range(10)},
            "t1": {f"w{n}": 1 for n in range(20)},
            "p1": {"w0": 1, "zz": 1},
        }
    )
    marked = {f"w{n}": KNOWN for n in range(19)}
    got = touchstones.at_level(shelf(), index, marked, "he", ui_language="en")
    assert [(text["id"], text["known"]) for text in got] == [("t1", 95), ("a1", 100)]
    assert got[1]["english"] == "A report"


def test_a_word_met_once_is_not_one_you_keep_meeting() -> None:
    met = {"often": 4, "twice": 2, "once": 1}
    got = touchstones.met_often(
        ["once", "often", "twice", "never"], lambda lemma: met.get(lemma, 0)
    )
    assert got == [{"lemma": "often", "texts": 4}, {"lemma": "twice", "texts": 2}]


def test_only_the_words_still_being_learned_are_asked_about() -> None:
    assert sorted(touchstones.learning({"a": 1, "b": 3, "c": KNOWN, "d": 0})) == ["a", "b"]


# -- /account/story, end to end ---------------------------------------------------------


def test_the_story_is_nobodys_business_signed_out(served: tuple[int, str, Path]) -> None:
    port, token, _ = served
    status, said, _ = call(port, "GET", f"/account/story?language=he&k={token}")
    assert status == 401 and said == {"signedIn": False}


def test_the_story_places_a_reader_and_finds_what_they_keep_meeting(
    served: tuple[int, str, Path], postbox: Postbox, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from targum import catalogue as catalogue_module
    from targum.coverage import write_index

    port, token, out = served
    lemmas = tmp_path / "lemmas.json"
    write_index(
        lemmas,
        index_of({"d1": {"ים": 9, "בית": 1}, "d2": {"ים": 10}, "a1": {"ים": 1, "ספר": 9}}),
    )
    monkeypatch.setattr(catalogue_module, "everything", shelf)
    monkeypatch.setattr(catalogue_module, "lemmas_path", lambda: lemmas)

    # Two finished texts, each with ספר in its first section.
    for name in ("one", "two"):
        folder = built(out / "shared" / name, {1: [[word("ספר"), word("ים")] * 3]})
        facts = json.loads((folder / "document.json").read_text(encoding="utf-8"))
        facts["content_hash"] = name
        (folder / "document.json").write_text(json.dumps(facts), encoding="utf-8")

    cookie = sign_in(port, postbox)
    words = [
        {"language": "he", "lemma": "ים", "status": KNOWN, "at": 1, "seen": 1},
        {"language": "he", "lemma": "ספר", "status": 2, "at": 1, "seen": 1},
    ]
    sections = [
        {"hash": name, "section": "1", "at": ms(2026, 9), "seen": ms(2026, 9)}
        for name in ("one", "two")
    ]
    status, answer, _ = call(
        port, "POST", f"/sync?k={token}", {"words": words, "sections": sections}, cookie=cookie
    )
    assert status == 200, answer

    status, said, _ = call(port, "GET", f"/account/story?language=he&k={token}", cookie=cookie)
    assert status == 200, said
    assert said["library"] is True and said["known"] == 1
    assert said["ladder"][0] == {
        "kind": "dialogue",
        "name": "dialogue",
        "share": 95,
        "state": "here",
        "texts": 3,
    }
    assert said["said"] == "follow"
    # By distinct words, as the Library's Read it now: only d2 is all known.
    assert [text["id"] for text in said["texts"]] == ["d2"]
    assert said["words"] == [{"lemma": "ספר", "texts": 2}]

    status, said, _ = call(port, "GET", f"/account/story?language=arc&k={token}", cookie=cookie)
    assert said["ladder"] == [] and said["library"] is False and said["uploads"] == []
