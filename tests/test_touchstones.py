"""Your Progress's story (design.md §12, "Your Progress is a story in three parts",
2026-10-09, and "Your level leads with what you can read", 2026-10-28): the ladder of kinds
of text, where a reader is on it, how many of each kind they could read now, the level at
the foot, the texts at their level and the words they keep meeting.

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
from targum.coverage import IGNORED, KNOWN, build_index

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


def test_aramaic_outside_the_targums_and_an_empty_library_have_no_ladder() -> None:
    """Aramaic's rungs are bodies of Targum (design.md §12, 2026-10-25), so Aramaic rows
    that are none of them make no rung, and Yiddish, with no library, has none."""
    arc = [Entry("o1", "arc", "prose", 0), Entry("o2", "arc", "poetry", 12)]
    assert touchstones.ladder(arc, "arc") == []
    assert touchstones.ladder(shelf(), "yi") == []


def test_italian_stories_are_its_childrens_books() -> None:
    """StoryWeaver's children's books, said in everyday words: "what is a picture book?"
    (David, 2026-10-09). The rung still opens the story shelf."""
    rungs = touchstones.ladder([Entry("i1", "it", "story", 13)], "it")
    assert [(rung.kind, rung.name) for rung in rungs] == [("story", "children-book")]


def index_of(texts: dict[str, dict[str, int]]) -> Any:
    """An index with running counts: entry -> {lemma: how often}."""
    return build_index({entry: list(counts) for entry, counts in texts.items()}, texts)


def test_a_share_is_of_running_words_not_of_distinct_ones() -> None:
    """Known: the one word that comes round nine times in ten. Of its distinct words
    that is half; of its running words, nine in ten."""
    index = index_of({"a1": {"common": 9, "rare": 1}})
    assert touchstones.running_share(index, "a1", {"common": KNOWN}) == pytest.approx(0.9)
    assert touchstones.running_share(index, "nowhere", {"common": KNOWN}) is None


def test_an_ignored_word_is_left_out_of_the_running_share() -> None:
    """Ignored is not vocabulary: left out of the running words, as the reader does."""
    index = index_of({"a1": {"common": 6, "name": 3, "rare": 1}})
    marked = {"common": KNOWN, "name": IGNORED}
    assert touchstones.running_share(index, "a1", marked) == pytest.approx(6 / 7)


def test_a_share_falls_back_to_distinct_words_where_nothing_was_counted() -> None:
    index = index_of({"a1": {"common": 9, "rare": 1}})
    index.counts.clear()
    assert touchstones.running_share(index, "a1", {"common": KNOWN}) == pytest.approx(0.5)


def test_easy_is_ninety_five_and_up_and_the_next_step_follows_the_hardest_easy() -> None:
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
    got = touchstones.standing(rungs, index, {"שלום": KNOWN}, {"dialogue": 2, "article": 1})
    assert [(rung["kind"], rung["state"], rung["readable"]) for rung in got["ladder"]] == [
        ("dialogue", "easy", 2),
        ("talk", "easy", 0),
        ("article", "next", 1),
        ("poetry", "ahead", 0),
    ]
    assert got["here"] == 1 and got["next"] == 2
    assert "said" not in got, "no wording by share any more"


def test_a_rung_below_the_hardest_easy_one_is_easy_too() -> None:
    """The ladder climbs: a reader who reads news on their own reads conversations."""
    rungs = touchstones.ladder(shelf(), "he")
    index = index_of({"d1": {"a": 9, "b": 1}, "t1": {"a": 20}})
    got = touchstones.standing(rungs, index, {"a": KNOWN})
    assert [rung["state"] for rung in got["ladder"]] == ["easy", "easy", "next", "ahead"]
    # The article and the poem were never measured: no share, never 0%.
    assert got["ladder"][2]["share"] is None


def test_with_no_rung_easy_the_first_is_the_next_step() -> None:
    rungs = touchstones.ladder(shelf(), "he")
    got = touchstones.standing(rungs, index_of({"d1": {"a": 9, "b": 1}}), {"a": KNOWN})
    assert got["here"] is None and got["next"] == 0
    assert [rung["state"] for rung in got["ladder"]] == ["next", "ahead", "ahead", "ahead"]


def test_the_top_rung_easy_has_no_next_step() -> None:
    rungs = touchstones.ladder(shelf(), "he")
    index = index_of({entry: {"a": 1} for entry in ("d1", "d2", "t1", "a1", "p1")})
    got = touchstones.standing(rungs, index, {"a": KNOWN})
    assert got["here"] == 3 and got["next"] is None


def test_readable_counts_the_librarys_read_it_now_by_kind() -> None:
    """The Library's rule: 90% and up of a text's words, any of its languages, and a
    built copy's measure over the catalogue's. Unmeasured is never on the shelf."""

    @dataclass(frozen=True)
    class Two(Entry):
        languages: tuple[str, ...] = ()

    entries = [*shelf(), Two("both", "arc", "dialogue", 5, languages=("arc", "he"))]
    shares = {"d1": 0.9, "d2": 0.8999, "a1": 0.95, "t1": None, "p1": 1.0, "x1": 1.0, "both": 0.97}
    got = touchstones.readable(entries, "he", shares.get)
    assert got == {"dialogue": 2, "article": 1, "poetry": 1}, "prose is no ladder kind"
    assert touchstones.readable(entries, "ru", shares.get) == {}


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
    assert said["ladder"][0] == {
        "kind": "dialogue",
        "name": "dialogue",
        "share": 95,
        "state": "easy",
        "texts": 3,
        "readable": 1,
    }
    assert said["here"] == 0 and said["next"] == 1
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
    read" and opens `#see/now/kind/<kind>`, and the Library, drawn from what `/readers`
    hands it on the same server for the same reader, shows exactly N texts there."""
    from test_library_js import draw as library
    from test_library_js import text

    from targum import catalogue as catalogue_module
    from targum.coverage import write_index

    port, token, _ = served
    entries = [
        Entry("d1", "he", "dialogue", 5, "שיחה א"),
        Entry("d2", "he", "dialogue", 6, "שיחה ב"),
        Entry("d3", "he", "dialogue", 7, "שיחה ג"),
        Entry("d4", "he", "dialogue", 8, "שיחה ד"),
        Entry("t1", "he", "talk", 12, "הרצאה א"),
        Entry("t2", "he", "talk", 13, "הרצאה ב"),
        Entry("a1", "he", "article", 17, "ידיעה"),
        Entry("p1", "he", "poetry", 25, "שיר"),
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
    assert counts == {"dialogue": 3, "talk": 1, "article": 1, "poetry": 0}

    status, shelf_said, _ = call(port, "GET", f"/readers?k={token}", cookie=cookie)
    assert status == 200
    rows = [
        text(entry.id, entry.title, kind=entry.kind, difficulty=entry.difficulty)
        for entry in entries
    ]
    for kind, count in counts.items():
        drawn = library(
            tmp_path,
            catalogue=rows,
            collections=[],
            catalogueKnown=shelf_said["catalogue"],
            readers=shelf_said["readers"],
            shared=shelf_said["shared"],
            hash=f"#see/now/kind/{kind}",
        )
        assert len(drawn["rows"]) == count, (kind, drawn["rows"])
        assert drawn["fitOn"] == "Read it now"


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

    status, said, _ = call(port, "GET", f"/account/story?language=yi&k={token}", cookie=cookie)
    assert said["level"] is None
