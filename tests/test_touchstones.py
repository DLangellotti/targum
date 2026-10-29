"""Your Progress's story (design.md §12, "Your Progress is a story in three parts",
2026-10-09, and "Your level leads with what you can read", 2026-10-28): the ladder of kinds
of text, where a reader is on it, how many of each kind they could read now, the level at
the foot, the texts at their level and the words they keep meeting.

The arithmetic in `touchstones`, then the whole of `/account/story` end to end.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from math import ceil
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
    sentence: float = 0.0
    minutes: int = 0


def shelf() -> list[Entry]:
    """A Hebrew shelf at every level, one text unmeasured, and one Russian story."""
    return [
        Entry("d1", "he", "dialogue", 6, "שיחה", sentence=6, minutes=2),  # A1
        Entry("d2", "he", "dialogue", 8, "שיחה ב", sentence=8, minutes=10),  # A2
        Entry("d0", "he", "dialogue", 0, "לא נמדד"),  # unmeasured
        Entry("a1", "he", "article", 17, "ידיעה", english="A report", sentence=12),  # B1
        Entry("t1", "he", "talk", 14, "הרצאה", sentence=9, minutes=10),  # A2
        Entry("p1", "he", "poetry", 25, "שיר", sentence=20),  # Native, B2 with no index
        Entry("r1", "ru", "story", 22, "Муму", sentence=15),
    ]


#: The rows a language with a word ladder always has (design.md §12, "Your level, v3").
EVERY = ("A1", "A2", "B1", "B2", "C1", "C2", "past-C2")


def test_the_ladder_is_the_texts_own_levels_not_kinds() -> None:
    """David, 2026-10-28: an easy video is easier than a hard conversation, so a row is a
    level and holds every kind at it. Unmeasured texts are on no row."""
    rungs = touchstones.ladder(shelf(), "he")
    assert [(rung.kind, rung.texts) for rung in rungs] == [
        ("A1", ("d1",)),
        ("A2", ("d2", "t1")),
        ("B1", ("a1",)),
        ("B2", ("p1",)),
        ("C1", ()),
        ("C2", ()),
        ("past-C2", ()),
    ]
    assert [(rung.kind, rung.texts) for rung in touchstones.ladder(shelf(), "ru")][3] == (
        "B2",
        ("r1",),
    )


def test_every_level_is_a_row_where_the_language_has_a_word_ladder() -> None:
    """2026-10-29 ("Your level, v3"): C1, C2 and Past C2 are rows with no texts, because
    the words to go are worth showing; "a level with nothing at it is not a row" gave way."""
    rungs = touchstones.ladder([Entry("b", "he", "story", 17, sentence=12)], "he")
    assert tuple(rung.kind for rung in rungs) == EVERY
    assert [rung.texts for rung in rungs if rung.texts] == [("b",)]


def test_a_level_with_nothing_at_it_is_no_row_without_a_word_ladder() -> None:
    rungs = touchstones.ladder([Entry("b", "yi", "story", 17, sentence=12)], "yi")
    assert [rung.kind for rung in rungs] == ["B1"]


def test_a_text_in_two_languages_is_on_both_ladders() -> None:
    @dataclass(frozen=True)
    class Two(Entry):
        languages: tuple[str, ...] = ()

    both = Two("dan", "he", "prose", 17, sentence=12, languages=("he", "arc"))
    assert [rung.texts for rung in touchstones.ladder([both], "he") if rung.texts] == [("dan",)]


def test_aramaic_outside_the_targums_and_an_empty_library_have_no_ladder() -> None:
    """Aramaic's rungs are bodies of Targum (design.md §12, 2026-10-25), so Aramaic rows
    that are none of them make no rung, and Yiddish, with no library, has none."""
    arc = [Entry("o1", "arc", "prose", 0), Entry("o2", "arc", "poetry", 12)]
    assert touchstones.ladder(arc, "arc") == []
    assert touchstones.ladder(shelf(), "yi") == []


def index_of(texts: dict[str, dict[str, int]]) -> Any:
    """An index with running counts: entry -> {lemma: how often}."""
    return build_index({entry: list(counts) for entry, counts in texts.items()}, texts)


def test_easy_is_most_of_a_level_readable_and_the_next_step_follows() -> None:
    """A row counts its texts on the Library's Read it now (90%), and is easy where more
    than half its measured texts are; unmeasured ones are left out of both."""
    rungs = touchstones.ladder(shelf(), "he")
    shares = {"d1": 1.0, "d2": 0.95, "t1": 0.5, "a1": 0.9, "p1": None}
    got = touchstones.standing(rungs, shares.get)
    assert [(rung["kind"], rung["state"], rung["readable"]) for rung in got["ladder"]] == [
        ("A1", "easy", 1),
        ("A2", "easy", 1),
        ("B1", "easy", 1),
        ("B2", "next", 0),
        ("C1", "ahead", 0),
        ("C2", "ahead", 0),
        ("past-C2", "ahead", 0),
    ]
    assert got["here"] == 2 and got["next"] == 3
    assert "said" not in got and "share" not in got["ladder"][0], "no percentage to print"


def test_half_a_level_is_not_most_of_it() -> None:
    rungs = touchstones.ladder(shelf(), "he")
    got = touchstones.standing(rungs, {"d1": 0.5, "d2": 0.95, "t1": 0.5}.get)
    assert [rung["state"] for rung in got["ladder"]] == ["next"] + ["ahead"] * 6
    assert got["ladder"][1]["readable"] == 1, "counted, even where the level is not easy"


def test_a_row_below_the_hardest_easy_one_is_easy_too() -> None:
    """The ladder climbs: a reader who reads B1 on their own reads beginner texts."""
    rungs = touchstones.ladder(shelf(), "he")
    got = touchstones.standing(rungs, {"a1": 0.97}.get)
    assert [rung["state"] for rung in got["ladder"]][:5] == [
        "easy",
        "easy",
        "easy",
        "next",
        "ahead",
    ]


def test_with_no_row_easy_the_first_is_the_next_step() -> None:
    rungs = touchstones.ladder(shelf(), "he")
    got = touchstones.standing(rungs, {"d1": 0.4}.get)
    assert got["here"] is None and got["next"] == 0
    assert [rung["state"] for rung in got["ladder"]] == ["next"] + ["ahead"] * 6


def test_the_top_row_easy_has_no_next_step() -> None:
    rungs = touchstones.ladder([Entry("p1", "yi", "poetry", 25, sentence=20)], "yi")
    got = touchstones.standing(rungs, {"p1": 1.0}.get)
    assert got["here"] == 0 and got["next"] is None


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
        # A name and a number marked known: not vocabulary, so not counted, as the
        # ledger above does not count them (audit Q8, 2026-10-09: 1,743 against 1,688).
        {"language": "he", "lemma": "דוד", "status": KNOWN, "at": 1, "seen": 1, "band": "name"},
        {"language": "he", "lemma": "שלוש", "status": KNOWN, "at": 1, "seen": 1, "band": "number"},
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
    # By distinct words, as the Library: d2 is all known, d1 half, a1 half; t1 is not
    # indexed. A2 is easy on d2 alone, so A1 below it is easy too, with none to count.
    assert said["ladder"][0] == {
        "kind": "A1",
        "name": "A1",
        "state": "easy",
        "texts": 1,
        "readable": 0,
        # One word known, weighing 1.0 with no band, and nothing marked in the last 30
        # days: the next word is reckoned at the commonest band's 0.8, so (250 - 1) / 0.8
        # is 311.25, which is 312 words to aleph (design.md §12, "Your level, v3").
        "covered": False,
        "toGo": 312,
    }
    assert said["ladder"][1]["readable"] == 1 and said["ladder"][1]["state"] == "easy"
    # The rows above say their words to go, exact and growing down the ladder, and Past C2
    # has none.
    assert [row["toGo"] for row in said["ladder"]] == [
        312,
        ceil((1800 - 1) / 0.8),
        ceil((4500 - 1) / 0.8),
        ceil((6500 - 1) / 0.8),
        ceil((9000 - 1) / 0.8),
        ceil((12000 - 1) / 0.8),
        None,
    ]
    # Week one: no rung, and the card's bar and words toward aleph from the same function.
    assert said["first"] == {
        "scale": "ulpan",
        "letter": "א",
        "name": "aleph",
        "toward": 1 / 250,
        "toGo": 312,
    }
    assert said["conversations"] is True
    assert said["here"] == 1 and said["next"] == 2
    # One word known is no rung of the ulpan's: no foot line until the first is reached.
    assert said["level"] is None
    # By distinct words, as the Library's Read it now: only d2 is all known.
    assert [text["id"] for text in said["texts"]] == ["d2"]
    assert said["words"] == [{"lemma": "ספר", "texts": 2}]

    status, said, _ = call(port, "GET", f"/account/story?language=arc&k={token}", cookie=cookie)
    assert said["ladder"] == [] and said["library"] is False and said["uploads"] == []


def test_each_ladder_count_is_its_library_shelf_count(
    served: tuple[int, str, Path], postbox: Postbox, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The acceptance line of targum-internal#553: a row of the ladder says "N you can
    read" and opens `#see/now/level/<level>`, and the Library, drawn from what `/readers`
    hands it on the same server for the same reader and from its shelf rows as the
    builder writes them (each with its `cefr`), shows exactly N texts there."""
    from urllib.parse import quote

    from test_library_js import draw as library
    from test_library_js import text

    from targum import catalogue as catalogue_module
    from targum.coverage import write_index

    port, token, _ = served
    entries = [
        Entry("d1", "he", "dialogue", 5, "שיחה א", sentence=6, minutes=2),  # A1
        Entry("d2", "he", "dialogue", 6, "שיחה ב", sentence=6, minutes=2),  # A1
        Entry("d3", "he", "dialogue", 7, "שיחה ג", sentence=8, minutes=10),  # A2
        Entry("d4", "he", "dialogue", 8, "שיחה ד", sentence=8, minutes=10),  # A2
        Entry("t1", "he", "talk", 12, "הרצאה א", sentence=9, minutes=10),  # A2
        Entry("t2", "he", "talk", 13, "הרצאה ב", sentence=12),  # B1
        Entry("a1", "he", "article", 17, "ידיעה", sentence=12),  # B1
        Entry("p1", "he", "poetry", 25, "שיר", sentence=20),  # Native: C1 by the ruler
    ]
    known = [f"w{n}" for n in range(9)]
    lemmas = tmp_path / "lemmas.json"
    write_index(
        lemmas,
        index_of(
            {
                # Every word known; nine in ten, on the line; eight in ten; all again.
                "d1": {word: 1 for word in known},
                "d2": {**{word: 1 for word in known}, "rare": 1},
                "d3": {**{word: 1 for word in known[:8]}, "x": 1, "y": 1},
                "d4": {word: 1 for word in known[:4]},
                "t1": {word: 1 for word in known},
                "t2": {"w0": 1, "x": 1},
                "a1": {**{word: 1 for word in known}, "rare": 1},
                "p1": {"w0": 1, "x": 1, "y": 1},
            }
        ),
    )
    monkeypatch.setattr(catalogue_module, "everything", lambda: entries)
    monkeypatch.setattr(catalogue_module, "lemmas_path", lambda: lemmas)

    cookie = sign_in(port, postbox)
    words = [
        {"language": "he", "lemma": word, "status": KNOWN, "at": 1, "seen": 1} for word in known
    ]
    status, _, _ = call(port, "POST", f"/sync?k={token}", {"words": words}, cookie=cookie)
    assert status == 200

    status, said, _ = call(port, "GET", f"/account/story?language=he&k={token}", cookie=cookie)
    assert status == 200, said
    counts = {rung["kind"]: rung["readable"] for rung in said["ladder"]}
    assert counts == {"A1": 2, "A2": 2, "B1": 1, "B2": 0, "C1": 0, "C2": 0, "past-C2": 0}
    # p1's "w0" is on no frequency list and is not counted; "x" and "y" rank 3,231 and
    # 7,019 in Hebrew's, so 85% of what is ranked needs 7,019 words, past dalet: C1.
    assert {rung["kind"]: rung["texts"] for rung in said["ladder"]}["C1"] == 1

    status, shelf_said, _ = call(port, "GET", f"/readers?k={token}", cookie=cookie)
    assert status == 200
    from targum.levelmap import text_level

    rows = [
        text(
            entry.id,
            entry.title,
            kind=entry.kind,
            difficulty=entry.difficulty,
            cefr=text_level(entry),  # type: ignore[arg-type]
        )
        for entry in entries
    ]
    for level, count in counts.items():
        drawn = library(
            tmp_path,
            catalogue=rows,
            collections=[],
            catalogueKnown=shelf_said["catalogue"],
            readers=shelf_said["readers"],
            shared=shelf_said["shared"],
            hash=f"#see/now/level/{quote(level)}",
        )
        assert len(drawn["rows"]) == count, (level, drawn["rows"])
        assert drawn["fitOn"] == "Read it now"
    # B2 and up, an address from before the split, still opens onto the four it became.
    drawn = library(
        tmp_path,
        catalogue=rows,
        collections=[],
        catalogueKnown=shelf_said["catalogue"],
        readers=shelf_said["readers"],
        shared=shelf_said["shared"],
        hash="#see/level/B2%2B",
    )
    assert [row["id"] for row in drawn["rows"]] == ["p1"], drawn["rows"]


def test_the_foot_level_is_the_measured_rung_and_the_way_to_the_next(
    served: tuple[int, str, Path], postbox: Postbox
) -> None:
    """level.py's rung, measured from weighted known words, with the share of the way to
    the next rung for the bar; nothing for a language with no scale."""
    port, token, _ = served
    cookie = sign_in(port, postbox)
    words = [
        {
            "language": "he",
            "lemma": f"מלה{n}",
            "status": KNOWN,
            "at": 1,
            "seen": 1,
            "band": "fairly easy",
        }
        for n in range(300)
    ]
    status, _, _ = call(port, "POST", f"/sync?k={token}", {"words": words}, cookie=cookie)
    assert status == 200
    status, said, _ = call(port, "GET", f"/account/story?language=he&k={token}", cookie=cookie)
    assert status == 200, said
    level = said["level"]
    assert {key: level[key] for key in ("scale", "letter", "name", "cefr", "next")} == {
        "scale": "ulpan",
        "letter": "א",
        "name": "aleph",
        "cefr": "A1",
        "next": {"letter": "א+", "name": "aleph plus"},
    }
    assert level["toward"] == pytest.approx(50 / 650)
    # 600 weighted words to aleph plus. Nothing was marked in the last 30 days and most
    # known words are fairly easy, so the next ones are reckoned moderate, 1.3 each:
    # 461.5, which is 462 words, exact (design.md §12, "Your level, v3", 2026-10-29).
    assert level["toGo"] == 462
    assert said["first"] is None, "a rung is reached, so there is no week-one bar"

    status, said, _ = call(port, "GET", f"/account/story?language=yi&k={token}", cookie=cookie)
    assert said["level"] is None
