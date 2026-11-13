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
    #: Long enough to be placed Native by the measure (`levelmap.NATIVE_MIN_WORDS`).
    words: int = 1000


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


# -- Texts by level agrees with Reading level (targum-internal#693, 2026-11-13) ----------


def reader_at(weighted: float, language: str = "he") -> Any:
    """A reader's `level.snapshot` with this many weighted known words, nothing else."""
    from targum.level import Level, ladder_for, standing

    ladder = ladder_for(language)
    assert ladder is not None
    here, following = standing(weighted, ladder.rungs)
    return Level(
        language=language,
        known=int(weighted),
        learning=0,
        weighted=weighted,
        here=here,
        next=following,
        days=0,
        streak=0,
        longest=0,
        sections=0,
        texts=0,
        per_word=1.3,
    )


def davids_shelf() -> tuple[list[touchstones.Rung], dict[str, float]]:
    """Hebrew as David's Progress counted it on 2026-11-13: A1 179 readable, A2 67, B1 61,
    B2 9, C1 1 and C2 1, out of many measured texts below C1 and very few above."""
    measured = {"A1": 200, "A2": 100, "B1": 120, "B2": 69, "C1": 3, "C2": 1}
    readable = {"A1": 179, "A2": 67, "B1": 61, "B2": 9, "C1": 1, "C2": 1}
    entries: list[Entry] = []
    level_of: dict[str, str] = {}
    shares: dict[str, float] = {}
    for level, n in measured.items():
        for k in range(n):
            entry_id = f"{level}-{k}"
            entries.append(Entry(entry_id, "he", "article", 10))
            level_of[entry_id] = level
            shares[entry_id] = 0.97 if k < readable[level] else 0.7
    rungs = touchstones.ladder(entries, "he", lambda entry: level_of[entry.id])
    return rungs, shares


def story(rungs: list[touchstones.Rung], shares: dict[str, float], found: Any) -> dict[str, Any]:
    """The ladder as `/account/story` sends it: texts, then the reader's words."""
    got = touchstones.standing(rungs, shares.get, touchstones.reached_by(found))
    touchstones.words_to_go(got["ladder"], found)
    return got


def test_a_b2_reader_is_never_easy_at_c1_on_one_readable_text() -> None:
    """David's case: the card says dalet, about B2, 410 words to hey, and the ladder ticked
    every row to C2 because C2's one measured text was readable and the climb ticked
    everything under it. Now C1 and C2 say their words to go, and B2, where 9 of 69 texts
    are readable, is the next step."""
    from targum.level import words_to

    found = reader_at(9000 - 410 * 1.3)
    assert found.here is not None and found.here.cefr == "B2"
    assert found.next is not None
    card = words_to(found, found.next.at)
    assert card == 410
    got = story(*davids_shelf(), found)
    rows = {row["kind"]: row for row in got["ladder"]}
    assert [(row["kind"], row["state"]) for row in got["ladder"]] == [
        ("A1", "easy"),
        ("A2", "easy"),
        ("B1", "easy"),
        ("B2", "next"),
        ("C1", "ahead"),
        ("C2", "ahead"),
        ("past-C2", "ahead"),
    ]
    assert got["here"] == 2 and got["next"] == 3
    # The C1 row's words to go are the card's.
    assert rows["C1"]["toGo"] == card and rows["C1"]["covered"] is False
    assert rows["C2"]["toGo"] > card
    assert rows["B2"]["covered"] is True and rows["B2"]["readable"] == 9


def test_no_row_above_the_readers_words_is_easy_whatever_its_texts_say() -> None:
    """Every text readable at every level: the ladder still stops where the words do."""
    rungs, shares = davids_shelf()
    every = dict.fromkeys(shares, 0.99)
    got = story(rungs, every, reader_at(7000))
    assert [row["state"] for row in got["ladder"]] == ["easy"] * 4 + ["ahead"] * 3
    assert got["here"] == 3 and got["next"] is None


def test_a_level_with_too_few_measured_texts_is_decided_by_the_words() -> None:
    """Under `SAMPLE` measured texts a level is not decided by its texts: reached by the
    words, it is easy; not reached, it says its words to go."""
    a1 = [Entry(f"a{k}", "he", "article", 10) for k in range(touchstones.SAMPLE)]
    b1 = [Entry(f"b{k}", "he", "article", 10) for k in range(touchstones.SAMPLE - 1)]
    levels = {**{e.id: "A1" for e in a1}, **{e.id: "B1" for e in b1}}
    rungs = touchstones.ladder([*a1, *b1], "he", lambda entry: levels[entry.id])
    # A1's texts are all hard, B1's few all hard too; the reader stands at gimel, B1.
    shares = dict.fromkeys(levels, 0.5)
    got = story(rungs, shares, reader_at(5000))
    states = {row["kind"]: row["state"] for row in got["ladder"]}
    # A1 has a full sample against it: the next step. A2 and B1 sit above it.
    assert states["A1"] == "next" and states["A2"] == "ahead" and states["B1"] == "ahead"
    # With A1 readable, A2 (no texts) and B1 (too few to judge) are easy by the words.
    shares = {**shares, **dict.fromkeys((e.id for e in a1), 0.95)}
    got = story(rungs, shares, reader_at(5000))
    states = {row["kind"]: row["state"] for row in got["ladder"]}
    assert [states[k] for k in ("A1", "A2", "B1", "B2")] == ["easy", "easy", "easy", "ahead"]


def test_the_words_check_level_reaches_its_rows_until_the_marks_do() -> None:
    """A reader whose card shows the words check's level (B1) has rows up to it decided
    as a measured reader's are, and none above it easy."""
    rungs, shares = davids_shelf()
    every = dict.fromkeys(shares, 0.99)
    got = touchstones.standing(rungs, every.get, touchstones.reached_by(reader_at(10), "B1"))
    assert [row["state"] for row in got["ladder"]] == ["easy"] * 3 + ["ahead"] * 4


def test_texts_at_your_level_are_ninety_and_up_nearest_the_line_first() -> None:
    index = index_of(
        {
            "a1": {f"ww{n}": 1 for n in range(10)},
            "t1": {f"ww{n}": 1 for n in range(20)},
            "p1": {"ww0": 1, "zz": 1},
        }
    )
    marked = {f"ww{n}": KNOWN for n in range(19)}
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
    marked = {"אב": 1, "בת": 3, "גן": KNOWN, "דג": 0}
    assert sorted(touchstones.learning(marked)) == ["אב", "בת"]


@pytest.mark.parametrize("letter", list("והבכלמש") + ["כְּ", "x"])
def test_a_one_letter_form_is_never_a_word_to_learn(letter: str) -> None:
    """A clitic DICTA split off has a lemma of one letter, pointed or not, and a reader
    who tapped it has it on their list; "כ" headed "Words you keep meeting" on
    2026-10-30. Any one-letter form, in any language, is left out."""
    assert not touchstones.a_word(letter)
    assert touchstones.learning({letter: 1, "ספר": 1}) == ["ספר"]


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

    # Two finished texts, each with ספר in its first section, and a כ DICTA split off a
    # word and a של, both closed-class (2026-10-30: "כ" headed the list on the box).
    for name in ("one", "two"):
        line = [word("ספר"), word("ים")] * 3 + [word("כ", "ADP"), word("של", "ADP")]
        folder = built(out / "shared" / name, {1: [line]})
        facts = json.loads((folder / "document.json").read_text(encoding="utf-8"))
        facts["content_hash"] = name
        (folder / "document.json").write_text(json.dumps(facts), encoding="utf-8")

    cookie = sign_in(port, postbox)
    words = [
        {"language": "he", "lemma": "ים", "status": KNOWN, "at": 1, "seen": 1},
        {"language": "he", "lemma": "ספר", "status": 2, "at": 1, "seen": 1},
        # Tapped while reading, so on the list and still being learned; never words to
        # learn, so never words they keep meeting.
        {"language": "he", "lemma": "כ", "status": 1, "at": 1, "seen": 1},
        {"language": "he", "lemma": "של", "status": 1, "at": 1, "seen": 1},
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
    # By running words, as the Library since 2026-11-01 ("The Library's bands count
    # running words"): d2 is all known, d1 nine in ten, a1 one in ten; t1 is not indexed.
    # So A1's one text, d1, is readable now, and so is A2's d2. One text is no sample, and
    # one known word reaches no level, so neither row is easy: they say their words to go,
    # as the card says its words to aleph (targum-internal#693).
    assert said["ladder"][0] == {
        "kind": "A1",
        "name": "A1",
        "state": "ahead",
        "texts": 1,
        "readable": 1,
        # One word known, weighing 1.0 with no band, and nothing marked in the last 30
        # days: the next word is reckoned at the commonest band's 0.8, so (250 - 1) / 0.8
        # is 311.25, which is 312 words to aleph (design.md §12, "Your level, v3").
        "covered": False,
        "toGo": 312,
    }
    assert said["ladder"][1]["readable"] == 1 and said["ladder"][1]["state"] == "ahead"
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
    assert said["here"] is None and said["next"] is None
    # One word known is no rung of the ulpan's: no foot line until the first is reached.
    assert said["level"] is None
    # By running words, as Home's card chooses (design.md §12, 2026-10-31): d1 is 9 of
    # its 10 words, in the band and first; d2 is all known, after it; a1 is 1 in 10.
    # d1's one unmarked word is a common one, so its figure is our estimate, labelled
    # (design.md §12, "A text's figure is our estimate until your marks settle it",
    # 2026-11-04); d2's marks settle it.
    texts = [(text["id"], text["estimated"]) for text in said["texts"]]
    assert texts == [("d1", True), ("d2", False)]
    assert said["texts"][0]["known"] > 90 and said["texts"][1]["known"] == 100
    assert said["words"] == [{"lemma": "ספר", "texts": 2}]

    status, said, _ = call(port, "GET", f"/account/story?language=arc&k={token}", cookie=cookie)
    assert said["ladder"] == [] and said["library"] is False and said["uploads"] == []


def test_the_story_draws_the_grammar_grid_from_verbs_met_in_finished_sections(
    served: tuple[int, str, Path], postbox: Postbox, monkeypatch: pytest.MonkeyPatch
) -> None:
    """What next's Grammar grid (design.md §12, "What next leads with your biggest grammar
    gap", 2026-10-30): read off the binyan and tense each verb token already carries, met
    inside a finished section, and never for a language other than Hebrew."""
    from targum import catalogue as catalogue_module

    port, token, out = served
    monkeypatch.setattr(catalogue_module, "everything", list)

    def verb(lemma: str, binyan: str) -> dict[str, str]:
        return {"lemma": lemma, "pos": "VERB", "binyan": binyan, "feats": "UPOS=VERB|Tense=Past"}

    folder = built(
        out / "shared" / "verbs",
        {
            1: [[verb("כתב", "פעל")] * 30 + [verb("התלבש", "התפעל")] * 30],
            # Unfinished: none of these is met.
            2: [[verb("נכנס", "נפעל")] * 40],
        },
    )
    facts = json.loads((folder / "document.json").read_text(encoding="utf-8"))
    facts["content_hash"] = "verbs"
    (folder / "document.json").write_text(json.dumps(facts), encoding="utf-8")

    cookie = sign_in(port, postbox)
    words = [{"language": "he", "lemma": "כתב", "status": KNOWN, "at": 1, "seen": 1}]
    sections = [{"hash": "verbs", "section": "1", "at": ms(2026, 9), "seen": ms(2026, 9)}]
    status, answer, _ = call(
        port, "POST", f"/sync?k={token}", {"words": words, "sections": sections}, cookie=cookie
    )
    assert status == 200, answer

    status, said, _ = call(port, "GET", f"/account/story?language=he&k={token}", cookie=cookie)
    assert status == 200, said
    rows = {row["binyan"]: row for row in said["grammar"]["rows"]}
    assert rows["paal"]["cells"]["past"]["known"] == 100
    assert rows["hitpael"]["cells"]["past"]["known"] == 0
    assert rows["nifal"]["tokens"] == 0, "a section not finished is not met"
    assert said["grammar"]["gap"]["binyan"] == "hitpael"
    assert said["grammar"]["gap"]["examples"] == ["התלבש"]

    status, said, _ = call(port, "GET", f"/account/story?language=arc&k={token}", cookie=cookie)
    assert said["grammar"] is None


def test_the_story_draws_the_mishkal_list_where_there_is_a_lexicon(
    served: tuple[int, str, Path],
    postbox: Postbox,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The Mishkal list (design.md §12, 2026-11-02): nouns met inside a finished section,
    by the pattern the root lexicon gives the card; What next names its gap when it is the
    only one; and a machine with no lexicon draws no list."""
    from targum import catalogue as catalogue_module

    port, token, out = served
    monkeypatch.setattr(catalogue_module, "everything", list)

    def noun(lemma: str) -> dict[str, str]:
        return {"lemma": lemma, "pos": "NOUN"}

    folder = built(out / "shared" / "nouns", {1: [[noun("מכתב")] * 30 + [noun("כתיבה")] * 30]})
    facts = json.loads((folder / "document.json").read_text(encoding="utf-8"))
    facts["content_hash"] = "nouns"
    (folder / "document.json").write_text(json.dumps(facts), encoding="utf-8")

    cookie = sign_in(port, postbox)
    words = [{"language": "he", "lemma": "כתיבה", "status": KNOWN, "at": 1, "seen": 1}]
    sections = [{"hash": "nouns", "section": "1", "at": ms(2026, 9), "seen": ms(2026, 9)}]
    status, answer, _ = call(
        port, "POST", f"/sync?k={token}", {"words": words, "sections": sections}, cookie=cookie
    )
    assert status == 200, answer

    status, said, _ = call(port, "GET", f"/account/story?language=he&k={token}", cookie=cookie)
    assert said["mishkal"] is None, "no lexicon on this machine, no list"
    assert said["roots"] is None, "no lexicon, no roots line"

    row = {"root": "כ־ת־ב", "borrowed": False, "meaning": "write", "transparent": "yes"}
    lexicon = tmp_path / "roots-he.json"
    lexicon.write_text(
        json.dumps(
            {
                "version": "roots/1",
                "language": "he",
                "lemmas": {
                    "מכתב": dict(row, pattern="מִקְטָל"),
                    "כתיבה": dict(row, pattern="קְטִילָה"),
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("TARGUM_ROOTS_HE", str(lexicon))
    status, said, _ = call(port, "GET", f"/account/story?language=he&k={token}", cookie=cookie)
    assert status == 200, said
    rows = {row["pattern"]: row for row in said["mishkal"]["rows"]}
    assert rows["miqtal"]["known"] == 0 and rows["qtila"]["known"] == 100
    assert said["mishkal"]["gap"]["pattern"] == "miqtal"
    assert said["lead"] == "mishkal"
    assert said["grammar"] is None
    # "words from N roots" (targum-internal#594): the one known word's root, כ־ת־ב.
    assert said["roots"] == 1

    status, said, _ = call(port, "GET", f"/account/story?language=arc&k={token}", cookie=cookie)
    assert said["mishkal"] is None
    assert said["roots"] is None


def test_the_story_draws_russian_grammar_and_hebrew_is_unchanged(
    served: tuple[int, str, Path], postbox: Postbox, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Russian's Grammar on What next (design.md §12, "Russian grammar on Your Progress",
    2026-11-09): read off the feats each Russian token already carries, met inside a
    finished section; Russian only, so Hebrew's story carries none and keeps its own."""
    from targum import catalogue as catalogue_module

    port, token, out = served
    monkeypatch.setattr(catalogue_module, "everything", list)

    def verb(surface: str, lemma: str, aspect: str) -> dict[str, str]:
        feats = f"UPOS=VERB|Aspect={aspect}|Tense=Past|VerbForm=Fin"
        return {"surface": surface, "lemma": lemma, "pos": "VERB", "feats": feats}

    folder = built(
        out / "shared" / "glagoly",
        {
            1: [
                [verb("говорил", "говорить", "Imp")] * 30 + [verb("сказал", "сказать", "Perf")] * 30
            ],
            2: [[verb("шёл", "идти", "Imp")] * 40],
        },
    )
    for name in ("document.json", "segments.json"):
        facts = json.loads((folder / name).read_text(encoding="utf-8"))
        facts["language"] = "ru"
        if name == "document.json":
            facts["content_hash"] = "glagoly"
        (folder / name).write_text(json.dumps(facts), encoding="utf-8")

    cookie = sign_in(port, postbox)
    words = [{"language": "ru", "lemma": "говорить", "status": KNOWN, "at": 1, "seen": 1}]
    sections = [{"hash": "glagoly", "section": "1", "at": ms(2026, 9), "seen": ms(2026, 9)}]
    status, answer, _ = call(
        port, "POST", f"/sync?k={token}", {"words": words, "sections": sections}, cookie=cookie
    )
    assert status == 200, answer

    status, said, _ = call(port, "GET", f"/account/story?language=ru&k={token}", cookie=cookie)
    assert status == 200, said
    russian = said["russian"]
    rows = {row["row"]: row for row in russian["aspect"]["rows"]}
    assert rows["imperfective"]["cells"]["past"]["known"] == 100
    assert rows["perfective"]["cells"]["past"]["known"] == 0
    assert rows["perfective"]["cells"]["past"]["words"][0]["form"] == "сказал"
    assert russian["aspect"]["gap"]["row"] == "perfective"
    assert russian["lead"] == "aspect"
    assert russian["motion"] is None, "a section not finished is not met"
    assert said["grammar"] is None and said["mishkal"] is None

    status, said, _ = call(port, "GET", f"/account/story?language=he&k={token}", cookie=cookie)
    assert said["russian"] is None


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
    # Words of two letters and up: a one-letter form is a clitic, never a word, and is
    # out of every running count (`touchstones.a_word`).
    known = [f"w{chr(ord('a') + n)}" for n in range(9)]
    lemmas = tmp_path / "lemmas.json"
    write_index(
        lemmas,
        index_of(
            {
                # Every word known; nine in ten, on the line; eight in ten; all again.
                "d1": {word: 1 for word in known},
                "d2": {**{word: 1 for word in known}, "rare": 1},
                "d3": {**{word: 1 for word in known[:8]}, "xq": 1, "yq": 1},
                "d4": {word: 1 for word in known[:4]},
                "t1": {word: 1 for word in known},
                "t2": {"wa": 1, "xq": 1},
                "a1": {**{word: 1 for word in known}, "rare": 1},
                "p1": {"wa": 1, "x": 1, "y": 1, "xq": 1, "yq": 1},
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
    # p1's "wa", "xq" and "yq" are on no frequency list and are not counted; "x" and "y"
    # rank 3,231 and 7,019 in Hebrew's, so 85% of what is ranked needs 7,019 words, past
    # dalet: C1.
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


# -- What you can read in our library (design.md §12, 2026-11-08) ------------------------


def test_coverage_counts_texts_ready_a_stretch_and_not_yet() -> None:
    """98% and up is ready, 95 to 98% a stretch, under 95% not yet; a text with no measure
    is on no row, and a text named twice is counted once."""
    shares = {"a": 1.0, "b": 0.98, "c": 0.979, "d": 0.95, "e": 0.949, "f": 0.2, "g": None}
    got = touchstones.coverage(["a", "b", "c", "d", "e", "f", "g", "a"], shares.get)
    assert got == {"ready": 2, "stretch": 2, "notYet": 2}


def test_the_story_counts_what_you_can_read_in_french_and_not_in_hebrew(
    served: tuple[int, str, Path], postbox: Postbox, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """French, Russian and Italian send the three counts over every text in the language
    the Library measures, by the Library's own share known; Hebrew sends none, and keeps
    its ladder."""
    from targum import catalogue as catalogue_module
    from targum.coverage import write_index

    port, token, _ = served
    known = [f"m{chr(ord('a') + n)}{chr(ord('a') + m)}" for n in range(5) for m in range(4)]
    entries = [
        Entry("f1", "fr", "story", 6, "Tout", sentence=6),
        Entry("f2", "fr", "story", 8, "Presque", sentence=8),
        Entry("f3", "fr", "story", 12, "Moitié", sentence=10),
        Entry("f0", "fr", "story", 0, "Pas mesuré"),
        Entry("h1", "he", "dialogue", 6, "שיחה", sentence=6),
    ]
    lemmas = tmp_path / "lemmas.json"
    write_index(
        lemmas,
        index_of(
            {
                "f1": {word: 1 for word in known},  # 100%
                "f2": {**{word: 1 for word in known[:19]}, "zzq": 1},  # 95%
                "f3": {**{word: 1 for word in known[:10]}, **{f"zq{n}": 1 for n in range(10)}},
                "h1": {word: 1 for word in known},
            }
        ),
    )
    monkeypatch.setattr(catalogue_module, "everything", lambda: entries)
    monkeypatch.setattr(catalogue_module, "lemmas_path", lambda: lemmas)
    cookie = sign_in(port, postbox)
    words = [
        {"language": lang, "lemma": word, "status": KNOWN, "at": 1, "seen": 1}
        for lang in ("fr", "he")
        for word in known
    ] + [
        # Every other word marked as still being learned, so each share is the marked one
        # and no estimate stands in for it.
        {"language": "fr", "lemma": word, "status": 1, "at": 1, "seen": 1}
        for word in ("zzq", *(f"zq{n}" for n in range(10)))
    ]
    status, _, _ = call(port, "POST", f"/sync?k={token}", {"words": words}, cookie=cookie)
    assert status == 200

    status, said, _ = call(port, "GET", f"/account/story?language=fr&k={token}", cookie=cookie)
    assert status == 200, said
    assert said["coverage"] == {"ready": 1, "stretch": 1, "notYet": 1, "among": 5000}
    status, said, _ = call(port, "GET", f"/account/story?language=he&k={token}", cookie=cookie)
    assert status == 200, said
    assert "coverage" not in said and said["ladder"]


def french(entry_id: str, title: str) -> Any:
    """A real catalogue row in French (`catalogue.Entry`), with a source a built copy can
    name, as the shelf links a copy to its row (`Handler._shape`)."""
    from targum import catalogue as catalogue_module

    return catalogue_module.Entry(
        id=entry_id,
        title=title,
        author="",
        language="fr",
        source=f"test:{entry_id}",
        blurb="",
        words=1000,
        kind=catalogue_module.Kind.story,
        difficulty=8,
        sentence=8,
    )


def test_a_text_the_card_calls_ready_is_never_missing_from_what_next(
    served: tuple[int, str, Path], postbox: Postbox, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """ "What you can read in our library" and What next read a text by one figure
    (targum-internal#664): a copy on the shared shelf, measured on its own words, counts
    the text ready on the card, so the text is on What next too, with the same figure,
    though the catalogue's index measures it under the floor. Before, the card said one
    text was ready and What next said nothing was at the reader's level."""
    from targum import catalogue as catalogue_module
    from targum.coverage import write_index

    port, token, out = served
    conte = french("fr-conte", "Le conte")
    chevre = french("fr-chevre", "La chèvre")
    folle = french("fr-folle", "La folle")
    known = [f"m{chr(ord('a') + n)}{chr(ord('a') + m)}" for n in range(5) for m in range(4)]
    unknown = [f"zq{n}" for n in range(20)]
    lemmas = tmp_path / "lemmas.json"
    write_index(
        lemmas,
        index_of(
            {
                # The index read a fuller edition of the tale: half its words known.
                conte.id: {**{w: 1 for w in known}, **{w: 1 for w in unknown}},
                chevre.id: {**{w: 1 for w in known[:19]}, unknown[0]: 1},  # 95%
                folle.id: {**{w: 1 for w in known[:6]}, **{w: 1 for w in unknown}},  # 23%
            }
        ),
    )
    shelf_rows = [conte, chevre, folle]
    monkeypatch.setattr(catalogue_module, "everything", lambda: shelf_rows)
    monkeypatch.setattr(catalogue_module, "CATALOGUE", shelf_rows)
    monkeypatch.setattr(catalogue_module, "lemmas_path", lambda: lemmas)
    # The copy on the shared shelf is the edition the reader opens: every word known.
    folder = built(out / "shared" / "conte", {1: [[word(lemma) for lemma in known]]})
    facts = json.loads((folder / "document.json").read_text(encoding="utf-8"))
    facts.update(language="fr", source=conte.source, content_hash="conte")
    (folder / "document.json").write_text(json.dumps(facts), encoding="utf-8")

    cookie = sign_in(port, postbox)
    words = [
        {"language": "fr", "lemma": lemma, "status": KNOWN, "at": 1, "seen": 1} for lemma in known
    ] + [
        # Every other word marked as still being learned, so no estimate stands in.
        {"language": "fr", "lemma": lemma, "status": 1, "at": 1, "seen": 1}
        for lemma in unknown
    ]
    status, _, _ = call(port, "POST", f"/sync?k={token}", {"words": words}, cookie=cookie)
    assert status == 200

    status, said, _ = call(port, "GET", f"/account/story?language=fr&k={token}", cookie=cookie)
    assert status == 200, said
    assert said["coverage"] == {"ready": 1, "stretch": 1, "notYet": 1, "among": 5000}
    listed = {row["id"]: row["known"] for row in said["texts"]}
    # Both texts in the band fit in the list's three; the tale, ready on the card, is on
    # it at the card's figure. La folle, under the floor, is not.
    assert len(said["texts"]) <= touchstones.TEXTS
    assert listed == {chevre.id: 95, conte.id: 100}


def test_what_next_lists_a_row_by_any_language_it_is_written_in() -> None:
    """Daniel is on the Aramaic shelf as well as the Hebrew one (`Entry.languages`), so
    an Aramaic reader's What next has it, as the card counts it (targum-internal#664)."""
    from targum import catalogue as catalogue_module

    daniel = catalogue_module.Entry(
        id="daniel",
        title="דניאל",
        author="",
        language="he",
        source="sefaria:Daniel",
        blurb="",
        words=1000,
        difficulty=10,
    )
    assert daniel.languages == ["he", "arc"]
    index = index_of({"daniel": {"מלכא": 19, "ספר": 1}})
    listed = touchstones.at_level([daniel], index, {"מלכא": KNOWN}, "arc")
    assert [row["id"] for row in listed] == ["daniel"] and listed[0]["known"] == 95


def test_the_story_sends_topics_behind_both_floors_and_none_without_a_lexicon(
    served: tuple[int, str, Path], postbox: Postbox, monkeypatch: pytest.MonkeyPatch
) -> None:
    """What next's Topics (targum-internal#608): weighed off the yardstick snapshots,
    only for a shown topic with 60 lemmas in them, rows only past the reader's 100 known
    words; nothing at all where the machine has no lexicon (the laptop's and CI's case),
    and never for a language other than Hebrew."""
    import os

    from targum import catalogue as catalogue_module
    from targum import topics

    port, token, _ = served
    monkeypatch.setattr(catalogue_module, "everything", list)
    cookie = sign_in(port, postbox)
    food = [f"אוכל{n}" for n in range(80)]
    law = [f"חוק{n}" for n in range(59)]
    words = [
        {"language": "he", "lemma": lemma, "status": KNOWN, "at": 1, "seen": 1}
        for lemma in food[:32] + [f"מלה{n}" for n in range(68)]
    ]
    status, answer, _ = call(port, "POST", f"/sync?k={token}", {"words": words}, cookie=cookie)
    assert status == 200, answer

    status, said, _ = call(port, "GET", f"/account/story?language=he&k={token}", cookie=cookie)
    assert status == 200 and said["topics"] is None, "no lexicon here: nothing is drawn"

    lexicon = {lemma: ["food"] for lemma in food} | {lemma: ["law"] for lemma in law}
    Path(os.environ[topics.ENV]).write_text(
        json.dumps({"version": topics.VERSION, "shown": ["food", "law"], "lemmas": lexicon}),
        encoding="utf-8",
    )
    status, said, _ = call(port, "GET", f"/account/story?language=he&k={token}", cookie=cookie)
    assert said["topics"] is None, "no yardstick to weigh by: nothing is drawn"

    tables = Path(os.environ["TARGUM_TABLES_DIR"])
    share = 1 / (len(food) + len(law))
    held = {"register": "news", "made_at": "2026-11-01", "weights": {}}
    held["weights"] = {lemma: share for lemma in food + law}
    (tables / "yardstick-news-v1.json").write_text(json.dumps(held), encoding="utf-8")
    # A verb's meaning is held only under its verb entry (targum#69): it is read from
    # there, and nothing is bought for the words that hold none.
    from targum.annotate import gloss as gloss_module
    from targum.cache import Cache
    from targum.models import VERB_MARK

    cache = Cache()
    provider = gloss_module.gloss_provider_name()
    key = gloss_module.gloss_key(cache, "אוכל32" + VERB_MARK, "he", "en", provider)
    cache.put("gloss", key, {"gloss": "to eat", "part_of_speech": "verb"})
    key = gloss_module.gloss_key(cache, "אוכל33", "he", "en", provider)
    cache.put("gloss", key, {"gloss": "food", "part_of_speech": "noun"})

    def bought(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("a meaning was bought for Your Progress")

    monkeypatch.setattr(gloss_module, "gloss_one", bought, raising=False)
    status, said, _ = call(port, "GET", f"/account/story?language=he&k={token}", cookie=cookie)
    assert said["known"] == 100
    shown = said["topics"]
    meanings = {word["lemma"]: word["meaning"] for word in shown["rows"][0]["words"]}
    assert meanings["אוכל32"] == "to eat" and meanings["אוכל33"] == "food"
    assert meanings["אוכל34"] == "", "none held: none shown, none bought"
    assert [row["topic"] for row in shown["rows"]] == ["food"], "law is under 60 lemmas"
    assert shown["rows"][0]["known"] == 40, "32 of 80 equally common words"
    assert shown["rows"][0]["words"][0]["lemma"] == "אוכל32"
    assert shown["weakest"] == "food"

    gone = [dict(word, status=2, at=2, seen=2) for word in words[-1:]]
    call(port, "POST", f"/sync?k={token}", {"words": gone}, cookie=cookie)
    status, said, _ = call(port, "GET", f"/account/story?language=he&k={token}", cookie=cookie)
    assert said["known"] == 99 and said["topics"] == {"floor": 100, "rows": [], "weakest": None}

    status, said, _ = call(port, "GET", f"/account/story?language=ru&k={token}", cookie=cookie)
    assert said["topics"] is None
