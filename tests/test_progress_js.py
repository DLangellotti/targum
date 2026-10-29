"""The Your Progress page, run rather than read.

A story in three parts under the totals (design.md §12, "Your Progress is a story in three
parts", 2026-10-09): the touchstones the account places the reader on, the words taken up
week by week, and what next — and the totals, which do arithmetic of their own: how many
words count as known, how many were learned here, how many targums finished.

`progress.js` is eight hundred lines and had no test that ran any of it — a parse check
and source greps stood in. Same harness as `test_learn_js.py`: a stub document in
`tests/js/`, not a browser.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any

import pytest

HARNESS = Path(__file__).resolve().parent / "js" / "progress.js"

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")

KNOWN = 9


def vocab(known: int = 0, learning: int = 0) -> dict[str, Any]:
    """A Hebrew word list: `known` words finished with, `learning` still in hand."""
    out: dict[str, Any] = {}
    for i in range(known):
        out[f"known-{i}"] = {"status": KNOWN, "surface": f"known-{i}", "at": 1_700_000_000_000 + i}
    for i in range(learning):
        out[f"soft-{i}"] = {"status": 2, "surface": f"soft-{i}", "at": 1_700_000_000_000 + i}
    return out


def draw(
    stored: dict[str, Any],
    chosen: str = "",
    strings: dict[str, Any] | None = None,
    reading: dict[str, Any] | None = None,
    story: dict[str, Any] | None = None,
    totals: list[dict[str, Any]] | None = None,
    story_fails: bool = False,
    story_held: bool = False,
    reading_fails: bool = False,
    raw: dict[str, str] | None = None,
) -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as where:
        payload = Path(where) / "payload.json"
        # The store holds strings, the way localStorage does.
        payload.write_text(
            json.dumps(
                {
                    "stored": {k: json.dumps(v) for k, v in stored.items()},
                    "chosen": chosen,
                    "strings": strings,
                    "reading": reading,
                    "story": story,
                    "storyFails": story_fails,
                    "storyHeld": story_held,
                    "readingFails": reading_fails,
                    # Stored as written, the way the page writes a remembered choice.
                    "raw": raw or {},
                    "totals": totals,
                }
            ),
            encoding="utf-8",
        )
        done = subprocess.run(
            ["node", str(HARNESS), str(payload)], capture_output=True, text=True, timeout=60
        )
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def test_the_ledger_counts_what_the_reader_actually_did() -> None:
    """Four real counts, and only four. Known is known — the learning ladder is not
    rounded up into it, because a word somebody is halfway through still costs them the
    page. Words saved and texts opened were here too and are not: a total that is two
    other totals added up, and a fact about browsing rather than about Hebrew."""
    drawn = draw(
        {
            "targum:vocab:he": vocab(known=12, learning=5),
            "targum:docs": {
                "a": {"language": "he", "title": "One"},
                "b": {"language": "he", "title": "Two"},
                "c": {"language": "ru", "title": "Another language"},
            },
            "targum:opened": {"a": 1, "b": 2, "c": 3},
            "targum:days": {"2026-08-24": 1, "2026-08-25": 1},
        }
    )

    assert drawn["counts"]["words known"] == 12
    assert drawn["counts"]["saved words"] == 17, "known and still learning together"
    assert "texts opened" not in drawn["counts"], "a fact about browsing"
    # Days do not follow the language switcher, because a day is not in a language and
    # you can read both in one.
    assert drawn["counts"]["days on targum"] == 2


def test_one_of_a_thing_is_not_said_in_the_plural() -> None:
    """The labels are read at display size beside the number they belong to, so "1 days
    reading" is the kind of thing that is only ever noticed by the reader."""
    drawn = draw(
        {
            "targum:vocab:he": vocab(known=1),
            "targum:docs": {"a": {"language": "he", "title": "One"}},
            "targum:opened": {"a": 1},
            "targum:days": {"2026-08-25": 1},
        }
    )

    assert drawn["counts"]["word known"] == 1
    assert drawn["counts"]["day on targum"] == 1


# --- an ignored word is ignored -----------------------------------------------


def marked(**spec: int) -> dict[str, Any]:
    """A Hebrew word list by status name, every word in the same difficulty band."""
    status = {"known": KNOWN, "learning": 2, "ignored": 0}
    out: dict[str, Any] = {}
    n = 0
    for kind, count in spec.items():
        for _ in range(count):
            out[f"w{n}"] = {
                "status": status[kind],
                "surface": f"w{n}",
                "band": "easy",
                "at": 1_700_000_000_000 + n,
            }
            n += 1
    return out


def page(words: dict[str, Any]) -> dict[str, Any]:
    return draw(
        {
            "targum:vocab:he": words,
            "targum:docs": {"a": {"language": "he", "title": "One"}},
            "targum:opened": {"a": 1},
            "targum:days": {"2026-08-25": 1},
        }
    )


def tile(drawn: dict[str, Any], label: str) -> int:
    for box in drawn["tiles"]:
        if box["label"] == label:
            return int(box["value"].replace(",", ""))
    raise AssertionError(f"no tile called {label!r}")


def test_a_word_you_ignored_is_not_a_word_you_counted() -> None:
    """Ignore means "this is not vocabulary". It was being counted as a word saved, which
    is the plainest way of getting it wrong; nothing in the block counts it now."""
    drawn = page(marked(known=4, learning=3, ignored=5))
    assert tile(drawn, "words known") == 4
    figures = {int(box["value"].replace(",", "")) for box in drawn["tiles"]}
    # 12 would be everything added up and 9 would be known plus ignored. Neither is a
    # number this reader's four figures can honestly hold.
    assert 12 not in figures and 9 not in figures


def test_a_name_marked_known_is_not_a_word_marked_known() -> None:
    """The line Learn opens with — "You know N Hebrew words" — leaves out every name and
    number, because knowing that אחשורוש is a king is not knowing a word of Hebrew. The
    ledger counted them, so its figure sat above Learn's by exactly the names the reader
    had ticked off while reading. Every figure on the page leaves them out, from one rule."""
    words = marked(known=4, learning=2)
    for n, kind in enumerate(("name", "number", "name")):
        words[f"n{n}"] = {"status": KNOWN, "surface": f"n{n}", "band": kind, "at": 1}
    words["n3"] = {"status": 2, "surface": "n3", "band": "name", "at": 1}
    # A name carried up to known is not a word targum taught either.
    words["n0"]["learned"] = 1
    drawn = page(words)
    plain = page(marked(known=4, learning=2))
    assert tile(drawn, "words known") == 4
    assert tile(drawn, "saved words") == 6
    assert tile(drawn, "learned on targum") == 0
    assert drawn["weeks"] == plain["weeks"], "nor among the words taken up"


# --- what targum taught, and what you already had -----------------------------


def test_words_learned_counts_only_what_was_carried_up_to_known() -> None:
    """The difference the tile is for: a word saved at a level below known and worked up
    to it, against one opened in a text and ticked off as already known. Both are known
    now, and only one of them was learned here."""
    words = marked(known=4)
    for key in list(words)[:2]:
        words[key]["learned"] = 1
    drawn = page(words)
    assert tile(drawn, "words known") == 4
    assert tile(drawn, "learned on targum") == 2


def test_a_word_still_being_learned_is_not_yet_learned() -> None:
    """The flag is set on the way up, so it can be sitting on a word that has since been
    put back down a level. Until it is known again it is not one you have learned."""
    words = marked(learning=3)
    for key in words:
        words[key]["learned"] = 1
    assert tile(page(words), "learned on targum") == 0


def test_nothing_was_learned_before_the_flag_existed() -> None:
    """Nothing in a finished record says which of the two a word was, so words marked
    before this was written count as neither and the figure starts from nought. Said
    plainly rather than guessed at from dates."""
    assert tile(page(marked(known=6)), "learned on targum") == 0


def test_one_word_saved_or_learned_is_not_said_in_the_plural() -> None:
    """These labels sit at display size beside the figure they belong to, which is where
    "1 words learned" is impossible not to read."""
    words = marked(known=1)
    words[next(iter(words))]["learned"] = 1
    drawn = page(words)
    assert tile(drawn, "word known") == 1
    assert tile(drawn, "learned on targum") == 1


def learned_by(*pairs: tuple[int | None, int]) -> list[bool]:
    """Ask the rule that writes the flag, as the Words page asks it, of (was, now) pairs."""
    with tempfile.TemporaryDirectory() as where:
        payload = Path(where) / "payload.json"
        payload.write_text(json.dumps({"learnedBy": [list(pair) for pair in pairs]}))
        done = subprocess.run(
            ["node", str(HARNESS), str(payload)], capture_output=True, text=True, timeout=60
        )
    assert done.returncode == 0, done.stderr
    return list(json.loads(done.stdout))


def test_any_stage_other_than_known_carried_to_known_was_learned_here() -> None:
    """David, 2026-10-24: "learned on targum should not just count words saved as new,
    but any word marked as anything other than known, which becomes known." New, still
    learning, almost known and ignored all count once they cross to known; a word that
    arrives at known from nowhere, or was known already — ticked off, or imported from
    "Words you may already know" — was one the reader had."""
    assert learned_by((1, KNOWN), (2, KNOWN), (3, KNOWN), (0, KNOWN)) == [True] * 4
    assert learned_by((None, KNOWN), (KNOWN, KNOWN)) == [False, False]
    assert learned_by((1, 2), (2, 3), (KNOWN, 2), (2, 0)) == [False] * 4, "only known is the end"


def test_an_imported_known_word_is_not_learned_on_targum() -> None:
    """A word claimed on "Words you may already know" is written known with the flag at
    nought (`claim.js`), and stays out of the figure however it is marked known again."""
    words = marked(known=3)
    for record in words.values():
        record.update(source="claimed", learned=0)
    assert tile(page(words), "learned on targum") == 0
    assert learned_by((KNOWN, KNOWN)) == [False]


def test_every_figure_is_said_once_on_the_page() -> None:
    """The tiles under the block counted the same words again in a different shape, and
    said "phrases saved" twice between them. One block, one count each."""
    drawn = page(marked(known=4, learning=3, ignored=5))
    labels = [box["label"] for box in drawn["tiles"]]
    assert len(labels) == len(set(labels)), f"a figure is said twice: {labels}"
    assert labels == [
        "saved words",
        "words known",
        "learned on targum",
        "phrases saved",
        "targums finished",
        "day on targum",
    ], "in the order somebody would say them, and no run of days (§12, 2026-10-09)"


def test_a_figure_carries_its_name_and_nothing_else() -> None:
    """ "90% of the way" was known against still-learning — a fraction whose denominator
    is however many words happen to be part-way up the ladder, so it fell when a reader
    saved a new word and rose when they gave up on one."""
    drawn = page(marked(known=9, learning=1))
    assert [box["delta"] for box in drawn["tiles"]] == [""] * 6


# --- what was finished ----------------------------------------------------------


def test_a_text_said_finished_is_counted_once() -> None:
    """targum-internal#112: the ledger says how many targums the reader finished. One
    record per text, so a text finished twice — or opened again after — is one."""
    drawn = draw(
        {
            "targum:vocab:he": vocab(known=1),
            "targum:docs": {
                "a": {"language": "he", "title": "One", "done": 1_700_000_000_000},
                "b": {"language": "he", "title": "Two", "done": 0},
                "c": {"language": "he", "title": "Three"},
            },
            "targum:opened": {"a": 1, "b": 2, "c": 3},
            "targum:days": {"2026-08-25": 1},
        }
    )
    assert drawn["counts"]["targum finished"] == 1


def test_a_finished_chapter_is_a_finished_targum() -> None:
    """targum-internal#173. Genesis is one document, so the ledger used to see one
    finished thing at the end of fifty chapters — and a reader three chapters in had
    finished nothing. A chapter is a targum now, and the count can move in an evening."""
    drawn = draw(
        {
            "targum:vocab:he": vocab(known=1),
            "targum:docs": {
                "gen": {
                    "language": "he",
                    "title": "Genesis",
                    "sections": {"1": 1_700_000_000_000, "2": 1_700_000_001_000},
                }
            },
            "targum:opened": {"gen": 1},
            "targum:days": {"2026-08-25": 1},
        }
    )
    assert drawn["counts"]["targums finished"] == 2


def test_an_old_record_and_its_chapters_are_never_added_together() -> None:
    """The rule stated once in #173, so nothing re-derives it: a document is worth the
    greater of its old whole-document record and its finished sections, never the sum.

    A book finished before the change sits at 1. Its first chapter re-read leaves it at
    1, because the old record already claimed that much. Its second takes it to 2."""

    def count(sections: dict[str, int]) -> int:
        drawn = draw(
            {
                "targum:vocab:he": vocab(known=1),
                "targum:docs": {
                    "gen": {
                        "language": "he",
                        "title": "Genesis",
                        "done": 1_600_000_000_000,
                        **({"sections": sections} if sections else {}),
                    }
                },
                "targum:opened": {"gen": 1},
                "targum:days": {"2026-08-25": 1},
            }
        )
        counts = drawn["counts"]
        return counts.get("targum finished", counts.get("targums finished", 0))

    assert count({}) == 1, "the old record stands"
    assert count({"1": 1_700_000_000_000}) == 1, "and the first chapter is what it claimed"
    assert count({"1": 1_700_000_000_000, "2": 1_700_000_001_000}) == 2, "the second is new"


def test_nobody_count_jumps_on_the_day_of_the_change() -> None:
    """The migration, and the reason back-filling was rejected: with no floor it turns
    one finished Genesis into fifty overnight, and every reader's count leaps without
    them having read anything that morning. A number that jumps fifty overnight is the
    one that teaches a reader not to trust the rest of the page."""
    before = draw(
        {
            "targum:vocab:he": vocab(known=1),
            "targum:docs": {
                "gen": {"language": "he", "title": "Genesis", "done": 1_600_000_000_000},
                "ruth": {"language": "he", "title": "Ruth", "done": 1_600_000_001_000},
            },
            "targum:opened": {"gen": 1, "ruth": 2},
            "targum:days": {"2026-08-25": 1},
        }
    )
    assert before["counts"]["targums finished"] == 2, "two books, two targums, unchanged"


def _on(day: date, n: int, tag: str) -> dict[str, Any]:
    """`n` words marked on `day`, at noon so no timezone can push them into another."""
    at = int(datetime.combine(day, time(12, 0)).timestamp() * 1000)
    return {
        f"{tag}-{i}": {"status": KNOWN, "surface": f"{tag}-{i}", "at": at + i} for i in range(n)
    }


def test_a_language_with_no_words_in_it_yet_draws_an_empty_ledger() -> None:
    """The menu lists every language the reader learns, and the page opens in the one they
    chose even where nothing is kept in it yet (2026-09-14). The page used to reach for
    that language's words and throw, leaving the page half drawn."""
    drawn = draw({"targum:vocab:he": vocab(known=3)}, chosen="arc")
    assert drawn["nothing"] is False
    assert all(not any(ch.isdigit() and ch != "0" for ch in label) for label in drawn["counts"])


# -- what you knew of what you read (targum-internal#291) -----------------------------


def day(when: date, known: int, tokens: int = 100, sections: int = 1) -> dict[str, Any]:
    """A day's bucket as `/account/reading` sends it (design.md §12, "Your level, v3")."""
    return {"day": when.isoformat(), "known": known, "tokens": tokens, "sections": sections}


def days_ago(n: int) -> date:
    return date.today() - timedelta(days=n)


def month_day(
    year: int, month_: int, known: int, tokens: int = 100, sections: int = 2
) -> dict[str, Any]:
    """A bucket on the 10th of a past month."""
    return day(date(year, month_, 10), known, tokens, sections)


def reading_of(*days: dict[str, Any]) -> dict[str, Any]:
    return {"he": {"line": [], "months": 0, "days": list(days), "sections": len(days)}}


def test_months_of_reading_draw_a_line_said_as_an_exact_percentage() -> None:
    """Month is the default where it has two points: a dot a month, each with its month,
    its exact percentage and the sections behind it; the latest said in a sentence
    (design.md §12, "Your level, v3": "In October you knew 91% of the words you read.")."""
    drawn = draw(
        {"targum:vocab:he": vocab(known=3)},
        reading=reading_of(
            month_day(2025, 6, 52),
            month_day(2025, 7, 61, sections=1),
            month_day(2025, 8, 70, sections=4),
        ),
    )["reading"]

    assert drawn["shown"] and drawn["drawn"] and drawn["by"] == "month"
    assert drawn["said"] == ["In August 2025 you knew 70% of the words you read."]
    assert drawn["titles"] == [
        "June 2025: 52% · 2 sections",
        "July 2025: 61% · 1 section",
        "August 2025: 70% · 4 sections",
    ]
    assert drawn["ticks"] == []
    assert drawn["months"] == ["June 2025", "July 2025", "August 2025"]
    assert drawn["focusable"] == "0", "the line is one tab stop"
    assert drawn["label"] == "Words you knew, June 2025 to August 2025"


def test_weeks_and_months_are_summed_from_days_by_words_not_shares() -> None:
    """A 40-word day at 0% and a 4,000-word day at 90% in one month are 89%, not 45%."""
    drawn = draw(
        {"targum:vocab:he": vocab(known=3)},
        reading=reading_of(
            day(date(2025, 6, 3), 0, tokens=40),
            day(date(2025, 6, 4), 3600, tokens=4000),
            month_day(2025, 7, 50),
        ),
    )["reading"]
    assert drawn["titles"][0] == "June 2025: 89% · 2 sections"


def test_a_line_that_falls_says_why_on_month_and_week_and_never_on_day() -> None:
    """Graded dialogue in July, Agnon in August: the line drops, and one sentence names
    the reason. On Day it would be said most mornings, so it is not."""
    drawn = draw(
        {"targum:vocab:he": vocab(known=3)},
        reading=reading_of(month_day(2025, 6, 70), month_day(2025, 7, 80), month_day(2025, 8, 55)),
    )["reading"]
    assert drawn["said"] == [
        "In August 2025 you knew 55% of the words you read.",
        "It fell because what you read in August 2025 had more words new to you, not because "
        "you lost any.",
    ]
    for said in drawn["said"]:
        assert "!" not in said and "don't worry" not in said.lower() and "keep" not in said

    daily = draw(
        {"targum:vocab:he": vocab(known=3)},
        reading=reading_of(day(days_ago(3), 80), day(days_ago(1), 55)),
    )["reading"]
    assert daily["by"] == "day"
    assert len(daily["said"]) == 1 and "fell" not in daily["said"][0]


def test_the_coarsest_view_with_two_points_is_the_default() -> None:
    """Month where it has two points, else Week, else Day (David, 2026-10-29)."""
    two_days = draw(
        {"targum:vocab:he": vocab(known=3)},
        reading=reading_of(day(date.today(), 68), day(days_ago(1), 60)),
    )["reading"]
    # Two days a week apart are also two weeks; in one week, Day is the only view.
    assert two_days["by"] in ("day", "week")
    assert two_days["shown"] and two_days["drawn"]
    if two_days["by"] == "day":
        assert two_days["said"] == ["Today you knew 68% of the words you read."]

    weeks = draw(
        {"targum:vocab:he": vocab(known=3)},
        reading=reading_of(day(days_ago(14), 60), day(days_ago(0), 70)),
    )["reading"]
    if date.today().day > 14:
        assert weeks["by"] == "week"
        assert weeks["said"] == ["This week you knew 70% of the words you read."]


def test_two_days_draw_the_card_and_one_day_does_not() -> None:
    """The card is there once two days have points, and absent with one, with none and
    signed out: no chart for a chart that isn't there."""
    one = draw({"targum:vocab:he": vocab(known=3)}, reading=reading_of(day(days_ago(1), 60)))[
        "reading"
    ]
    assert not one["shown"] and one["said"] == []

    nothing = draw({"targum:vocab:he": vocab(known=3)}, reading={})["reading"]
    assert not nothing["shown"] and nothing["said"] == []

    signed_out = draw({"targum:vocab:he": vocab(known=3)})["reading"]
    assert not signed_out["shown"], "absent signed out, not nought"


def test_a_short_day_is_counted_in_its_month_but_is_no_point_of_its_own() -> None:
    """Under twenty words a point is a guess and is left off; its words still count in
    the week and month it is part of."""
    drawn = draw(
        {"targum:vocab:he": vocab(known=3)},
        reading=reading_of(day(days_ago(40), 50), day(days_ago(1), 5, tokens=10)),
    )["reading"]
    assert not drawn["shown"], "one measurable day is not two"


def test_an_empty_view_says_what_would_draw_it() -> None:
    """Old reading only: Month draws, and Day, with nothing in the last thirty days, says
    so in the chart's place, which keeps its height."""
    drawn = draw(
        {"targum:vocab:he": vocab(known=3)},
        reading=reading_of(month_day(2025, 6, 52), month_day(2025, 7, 61)),
        raw={"targum.progress.reading-by": "day"},
    )["reading"]
    assert drawn["shown"] and drawn["by"] == "day" and not drawn["drawn"]
    assert drawn["empty"] == "We'll draw this once you've finished sections on two different days."


def test_a_reading_that_cannot_be_reached_says_so_in_the_charts_place() -> None:
    drawn = draw(
        {"targum:vocab:he": vocab(known=3)},
        reading=None,
        reading_fails=True,
    )["reading"]
    assert drawn["failed"] and not drawn["drawn"]


# -- the story (design.md §12, "Your Progress is a story in three parts", 2026-10-09) ---


LADDER = {
    "library": True,
    "known": 1240,
    "ladder": [
        {
            "kind": "A1",
            "name": "A1",
            "state": "easy",
            "texts": 120,
            "readable": 118,
            "covered": True,
            "toGo": None,
        },
        {
            "kind": "A2",
            "name": "A2",
            "state": "easy",
            "texts": 150,
            "readable": 143,
            "covered": True,
            "toGo": None,
        },
        {
            "kind": "B1",
            "name": "B1",
            "state": "easy",
            "texts": 90,
            "readable": 41,
            "covered": True,
            "toGo": None,
        },
        {
            "kind": "B2",
            "name": "B2",
            "state": "next",
            "texts": 45,
            "readable": 13,
            "covered": True,
            "toGo": None,
        },
        {
            "kind": "C1",
            "name": "C1",
            "state": "ahead",
            "texts": 20,
            "readable": 2,
            "covered": False,
            "toGo": 637,
        },
        {
            "kind": "C2",
            "name": "C2",
            "state": "ahead",
            "texts": 0,
            "readable": 0,
            "covered": False,
            "toGo": 2041,
        },
        {
            "kind": "past-C2",
            "name": "past-C2",
            "state": "ahead",
            "texts": 0,
            "readable": 0,
            "covered": False,
            "toGo": None,
        },
    ],
    "here": 2,
    "next": 3,
    "conversations": True,
    "level": {
        "scale": "ulpan",
        "letter": "ד",
        "name": "dalet",
        "cefr": "B2",
        "next": {"letter": "ה", "name": "hey"},
        "toward": 0.52,
        "toGo": 637,
    },
    "first": None,
    "texts": [
        {
            "id": "jonah",
            "title": "יונה",
            "english": "Jonah",
            "author": "",
            "kind": "prose",
            "known": 91,
        },
    ],
    "words": [{"lemma": "soft-0", "texts": 4}, {"lemma": "elsewhere", "texts": 2}],
}


def story(**changes: Any) -> dict[str, Any]:
    return draw({"targum:vocab:he": vocab(known=3, learning=2)}, story={**LADDER, **changes})


def week_one(**changes: Any) -> dict[str, Any]:
    """Under aleph: no letter, A1 the next step, every row above it words to go."""
    ladder = [dict(rung, state="ahead", readable=0, covered=False) for rung in LADDER["ladder"]]
    for rung, left in zip(ladder, (148, 1712, 3688, 4874, 6530, 8046, None), strict=True):
        rung["toGo"] = left
    ladder[0]["state"] = "next"
    first = {"scale": "ulpan", "letter": "א", "name": "aleph", "toward": 0.4, "toGo": 148}
    return story(
        **{
            "ladder": ladder,
            "here": None,
            "next": 0,
            "known": 86,
            "level": None,
            "first": first,
            **changes,
        }
    )


def test_the_card_is_the_level_and_nothing_else() -> None:
    """design.md §12, "Your level, v3" (2026-10-29): the letter alone with its geresh, its
    name said before it and the glyph hidden, "About B2" beside it, no headline about
    texts, and one press to Read it now."""
    drawn = story()["where"]
    assert drawn["mark"] == {
        "spoken": "Ulpan level dalet,",
        "big": "ד׳",
        "lang": "he",
        "dir": "rtl",
        "hidden": "true",
        "cefr": "About B2",
    }
    assert drawn["head"] == "" and drawn["step"] == "" and drawn["known"] == ""
    assert drawn["go"] == "Show texts you can read now"
    assert drawn["goHref"] == "/library?k=k#see/now"
    assert drawn["shown"] and not drawn["note"]


def test_the_words_to_the_next_rung_are_exact() -> None:
    """ "637 words to ה׳": no "Roughly", no "more", no rounding; the number in bold and the
    letter in its own right-to-left run. The bar is said in words, never as a figure."""
    toward = story()["where"]["toward"]
    assert toward == {
        "line": "637 words to ה׳",
        "number": "637",
        "letter": {"text": "ה׳", "dir": "rtl", "lang": "he"},
        "valuetext": "Toward hey",
        "now": "52",
        "width": "52%",
    }
    one = story(level={**LADDER["level"], "toGo": 1})["where"]["toward"]
    assert one["line"] == "1 word to ה׳"
    many = story(level={**LADDER["level"], "toGo": 12345})["where"]["toward"]
    assert many["line"] == "12,345 words to ה׳"


def test_every_row_says_its_state_or_its_words_to_go() -> None:
    """Rows the reader's words cover say Easy for you or Next and the texts they can read
    now; rows above say the words to go, exact, with no count; Past C2 says nothing. C1's
    number is the card's."""
    rungs = story()["where"]["rungs"]
    assert [(rung["name"], rung["said"], rung["count"]) for rung in rungs] == [
        ("Beginner · A1", "Easy for you", "118 you can read now"),
        ("A2", "Easy for you", "143 you can read now"),
        ("B1", "Easy for you", "41 you can read now"),
        ("B2", "Next", "13 you can read now"),
        ("C1", "637 words to go", ""),
        ("C2", "2,041 words to go", ""),
        ("Past C2", "", ""),
    ]
    assert [rung["state"] for rung in rungs] == ["easy"] * 3 + ["next"] + ["ahead"] * 3
    assert rungs[3]["current"] == "step"
    assert story()["where"]["toward"]["number"] == "637" == rungs[4]["said"].split()[0]


def test_a_row_with_no_texts_is_plain_text_with_no_chevron() -> None:
    rungs = story()["where"]["rungs"]
    assert [(rung["tag"], rung["chevron"]) for rung in rungs] == [("a", "›")] * 5 + [
        ("span", ""),
        ("span", ""),
    ]


def test_a_row_with_a_count_opens_exactly_the_texts_it_counted() -> None:
    """A count is the Library's Read it now at that level, and the row opens that shelf; a
    row with none opens every text at its level."""
    rungs = story()["where"]["rungs"]
    assert rungs[0]["href"] == "/library?k=k#see/now/level/A1"
    assert rungs[3]["href"] == "/library?k=k#see/now/level/B2"
    assert rungs[4]["href"] == "/library?k=k#see/level/C1", "above the words: no count"


def test_no_percentage_is_drawn_in_the_level_card_or_ladder() -> None:
    """The card and the ladder are counts; only Words you knew says a percentage."""
    for drawn in (story()["where"], week_one()["where"]):
        said = [drawn[key] for key in ("head", "step", "known", "go", "note")]
        said += [rung["text"] for rung in drawn["rungs"]]
        if drawn["toward"]:
            said += [drawn["toward"]["line"], drawn["toward"]["valuetext"]]
        if drawn["mark"]:
            said += list(drawn["mark"].values())
        assert not [line for line in said if "%" in line], said


def test_week_one_keeps_the_bar_and_the_words_to_aleph() -> None:
    """Under aleph: "Start with beginner texts.", the bar and "148 words to א׳", and
    "Start learning", which opens the first beginner conversation (David, 2026-10-29)."""
    drawn = week_one()["where"]
    assert drawn["mark"] is None
    assert drawn["head"] == "Start with beginner texts."
    assert drawn["step"] == "" and drawn["known"] == ""
    assert drawn["toward"]["line"] == "148 words to א׳"
    assert drawn["go"] == "Start learning"
    assert drawn["goHref"] == "/library?k=k#see/kind/dialogue"
    assert [rung["said"] for rung in drawn["rungs"]] == [
        "Next",
        "1,712 words to go",
        "3,688 words to go",
        "4,874 words to go",
        "6,530 words to go",
        "8,046 words to go",
        "",
    ]


def test_week_one_without_conversations_opens_the_first_level() -> None:
    drawn = week_one(conversations=False)["where"]
    assert drawn["go"] == "Show texts at this level"
    assert drawn["goHref"] == "/library?k=k#see/level/A1"


def test_the_top_rung_has_no_bar_and_no_number() -> None:
    level = {
        "scale": "ulpan",
        "letter": "ו",
        "name": "vav",
        "cefr": "C2",
        "next": None,
        "toward": None,
        "toGo": None,
    }
    drawn = story(level=level)["where"]
    assert drawn["mark"]["big"] == "ו׳" and drawn["mark"]["cefr"] == "About C2"
    assert drawn["toward"] is None
    assert drawn["go"] == "Show texts you can read now"


def test_a_plus_rung_keeps_its_plus_after_the_geresh() -> None:
    level = dict(
        LADDER["level"],
        letter="א+",
        name="aleph plus",
        cefr="A1",
        next={"letter": "ב", "name": "bet"},
        toGo=412,
    )
    drawn = story(level=level)["where"]
    assert drawn["mark"]["big"] == "א׳+"
    assert drawn["mark"]["spoken"] == "Ulpan level aleph plus,"
    assert drawn["toward"]["line"] == "412 words to ב׳"
    plus_next = story(
        level={**level, "letter": "א", "next": {"letter": "א+", "name": "aleph plus"}}
    )
    assert plus_next["where"]["toward"]["letter"]["text"] == "א׳+"


def test_the_european_scale_leads_with_itself() -> None:
    """French, Russian and Italian lead with the CEFR level, no second scale, words to the
    next CEFR rung."""
    level = {
        "scale": "cefr",
        "letter": "B1",
        "name": "B1",
        "cefr": "",
        "next": {"letter": "B2", "name": "B2"},
        "toward": 0.4,
        "toGo": 237,
    }
    drawn = draw(
        {"targum:vocab:fr": vocab(known=3)}, chosen="fr", story={**LADDER, "level": level}
    )["where"]
    assert drawn["mark"] == {
        "spoken": "",
        "big": "B1",
        "lang": "",
        "dir": "",
        "hidden": "",
        "cefr": "",
    }
    assert drawn["toward"]["line"] == "237 words to B2"
    assert drawn["toward"]["letter"] is None
    assert drawn["toward"]["valuetext"] == "Toward B2"


def test_aramaic_unmeasured_shows_known_words_and_says_why() -> None:
    """Aramaic climbs a ladder of Targums since 2026-10-25 (design.md §12); until the
    catalogue's Aramaic is measured it has none to draw, and says so as any language does.
    The line that blamed a missing frequency list is gone with the reason for it."""
    drawn = draw(
        {"targum:vocab:arc": vocab(known=12)},
        chosen="arc",
        story={
            "library": True,
            "known": 12,
            "ladder": [],
            "here": None,
            "said": "",
            "texts": [],
            "words": [],
        },
    )
    assert drawn["where"]["head"] == "You know 12 words so far"
    assert not drawn["where"]["shown"]
    assert "once we've measured the Library" in drawn["where"]["note"]
    assert drawn["how"] == "Reading"
    assert drawn["next"]["wordsTitle"].startswith("Words you keep meeting, from your Aramaic list")
    # Part 3 says the texts wait on the measuring, not that Aramaic is never placed.
    assert drawn["next"]["levelEmpty"] == (
        "We'll list Aramaic texts at your level once we've measured the library's Aramaic."
    )
    assert drawn["next"]["level"] == []


def test_aramaic_texts_at_your_level_are_listed_once_measured() -> None:
    """Since targum#936 Aramaic has a ladder, so once its rows are measured part 3 lists
    the texts at the reader's level as any language does, and no longer says it can't."""
    drawn = draw(
        {"targum:vocab:arc": vocab(known=40)},
        chosen="arc",
        story={
            "library": True,
            "known": 40,
            "ladder": [{"kind": "onkelos", "name": "onkelos", "state": "easy", "share": 96}],
            "here": 0,
            "next": None,
            "texts": [{"id": "onkelos-genesis", "title": "אונקלוס בראשית", "known": 92}],
            "words": [],
        },
    )["next"]
    assert drawn["level"] == [
        {"text": "אונקלוס בראשית | 92% known", "href": "/library?k=k#onkelos-genesis"}
    ]
    assert drawn["levelEmpty"] == ""


def test_yiddish_has_no_library_so_what_next_is_what_you_bring() -> None:
    drawn = draw(
        {"targum:vocab:yi": vocab(known=5)},
        chosen="yi",
        story={
            "library": False,
            "known": 5,
            "ladder": [],
            "here": None,
            "said": "",
            "texts": [],
            "words": [],
            "uploads": [{"name": "song", "title": "אויפֿן פּריפּעטשיק", "known": 84}],
        },
    )
    assert "Library has nothing in this language" in drawn["where"]["note"]
    assert drawn["how"] == "Reading and watching", "nobody's voice in Yiddish"
    nxt = drawn["next"]
    assert nxt["textsTitle"] == "Upload something of your own."
    assert nxt["level"][0]["href"] == "/add?k=k"
    assert nxt["level"][1]["text"] == "אויפֿן פּריפּעטשיקUploaded by you | 84% known"
    assert nxt["more"] == "All your uploads →"


def test_signed_out_the_story_says_what_signing_in_would_show() -> None:
    drawn = draw({"targum:vocab:he": vocab(known=3)})
    assert drawn["where"]["head"] == "Sign in to see which texts you can read on your own."
    assert not drawn["where"]["shown"] and drawn["where"]["mark"] is None
    assert drawn["next"]["metEmpty"].startswith("Sign in")


def test_what_next_names_the_words_with_their_own_meanings_and_the_texts() -> None:
    words = vocab(known=3, learning=2)
    words["soft-0"]["surface"] = "מושלים"
    drawn = draw(
        {
            "targum:vocab:he": words,
            "targum:meanings:he:en": {"soft-0": {"meaning": "rulers"}},
        },
        story=LADDER,
    )["next"]
    assert drawn["met"][0]["text"].startswith("מושלים")
    # With its meaning, in the language meanings are read in (targum-internal#471, B3).
    assert "rulers" in drawn["met"][0]["text"]
    assert drawn["met"][0]["text"].endswith("met in 4 texts")
    # A word the server met that this browser has not seen yet is still named.
    assert drawn["met"][1]["text"] == "elsewhere | met in 2 texts"
    # The title alone and its share known, as the board has it.
    assert drawn["level"] == [{"text": "יונה | 91% known", "href": "/library?k=k#jonah"}]
    assert drawn["more"] == "More in the Library →"


def test_nothing_met_twice_is_one_quiet_line() -> None:
    drawn = story(words=[], texts=[])["next"]
    assert drawn["met"] == [] and drawn["metEmpty"] == "None yet. They show up as you read."
    assert drawn["levelEmpty"].startswith("Nothing is quite at your level yet")


def test_the_story_is_asked_for_the_language_on_the_page() -> None:
    drawn = draw({"targum:vocab:ru": vocab(known=3)}, chosen="ru", story=LADDER)
    assert any(url.startswith("/account/story?language=ru") for url in drawn["asked"])


def test_the_words_taken_up_are_a_column_a_week_shaded_by_height() -> None:
    """By the week a word was saved: nothing records the day a word became known (§12,
    2026-10-09). From the first week with anything in it, each column one shade of the
    stage ramp by its height, leaf for the tallest, and no legend (the board's)."""
    today = date.today()
    words: dict[str, Any] = {}
    words |= _on(today, 3, "now")
    words |= _on(today - timedelta(days=8), 2, "last")
    words["last-0"]["status"] = 2
    words |= _on(today - timedelta(days=200), 40, "long-ago")
    drawn = draw({"targum:vocab:he": words})["weeks"]
    assert drawn["columns"] == 2, "from the first week with a word in it"
    assert drawn["label"].startswith("5 words saved in the last twelve weeks. Week of ")
    assert drawn["shades"] == ["var(--step-2)", "var(--step-4)"]
    assert drawn["titles"][-1].endswith(": 3 words")
    assert not drawn["legend"]


def test_no_words_lately_is_said_rather_than_drawn_flat() -> None:
    words = _on(date.today() - timedelta(days=300), 4, "old")
    assert draw({"targum:vocab:he": words})["weeks"]["said"] == (
        "No words saved in the last twelve weeks."
    )


def test_words_read_joins_the_totals_where_the_account_keeps_a_record() -> None:
    today = date.today().isoformat()
    totals = [
        {
            "day": today,
            "language": "he",
            "medium": "read",
            "words": 1200,
            "listened": 0,
            "watched": 0,
        },
        {"day": today, "language": "ru", "medium": "read", "words": 5, "listened": 0, "watched": 0},
    ]
    drawn = draw({"targum:vocab:he": vocab(known=3)}, totals=totals)
    assert drawn["counts"]["words read"] == 1200
    assert "words read" not in draw({"targum:vocab:he": vocab(known=3)})["counts"]


def test_while_the_story_is_asked_nothing_false_is_said() -> None:
    """targum-internal#471, B2: before the account answers, one quiet line, and What next
    does not say "None yet" to a reader who may have a record."""
    drawn = draw({"targum:vocab:he": vocab(known=3, learning=2)}, story_held=True)
    assert drawn["next"]["waiting"]
    assert drawn["next"]["metEmpty"] == "We're finding the words and texts for you."
    assert drawn["next"]["levelEmpty"] == ""


def test_a_story_that_cannot_be_reached_says_so_with_try_again() -> None:
    """Part 1 says it with Try again, and What next's two halves each say it under their
    heading rather than standing empty (targum-internal#522, §14.1)."""
    drawn = draw({"targum:vocab:he": vocab(known=3, learning=2)}, story_fails=True)
    assert drawn["next"]["failed"] and not drawn["next"]["waiting"]
    assert drawn["next"]["metEmpty"] == "We couldn't load this part."
    assert drawn["next"]["levelEmpty"] == "We couldn't load this part."


def test_nothing_to_practise_offers_no_practise_press() -> None:
    drawn = story(words=[], texts=[])["next"]
    assert not drawn["practise"]


# --- the finish bar's polish (targum-internal#471, design's §14 pass) ------------------

CSS = (
    Path(__file__).resolve().parent.parent / "src" / "targum" / "render" / "assets" / "progress.css"
).read_text(encoding="utf-8")


def _rule(selector: str, css: str = CSS) -> str:
    """The body of the first rule whose selector is exactly `selector`."""
    plain = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    for found, body in re.findall(r"([^{}]+)\{([^{}]*)\}", plain):
        if found.strip() == selector:
            return body
    raise AssertionError(f"no rule for {selector}")


def test_the_week_chart_names_its_first_and_last_week_under_it() -> None:
    """Polish 2: the bars had no dates. The first and the last week's dates sit under
    them, as wide as the weeks drawn, and are for the eye: the label says every week."""
    today = date.today()
    words: dict[str, Any] = {}
    words |= _on(today, 3, "now")
    words |= _on(today - timedelta(days=15), 2, "earlier")
    drawn = draw({"targum:vocab:he": words})["weeks"]
    assert drawn["columns"] == 3
    assert len(drawn["dates"]) == 2, "the first week's date and the last's"
    assert drawn["titles"][0].startswith(f"Week of {drawn['dates'][0]}:")
    assert drawn["titles"][-1].startswith(f"Week of {drawn['dates'][1]}:")
    assert drawn["datesSpan"] == "3", "as wide as the three weeks drawn"
    assert not drawn["legend"]


def test_one_week_of_words_names_one_date() -> None:
    drawn = draw({"targum:vocab:he": _on(date.today(), 2, "now")})["weeks"]
    assert len(drawn["dates"]) == 1


def test_this_week_is_always_at_the_end_edge() -> None:
    """Polish 2: bars started at the left, so this week moved with how many came before."""
    assert "justify-content: flex-end" in _rule(".progress .weeks")
    dates = _rule(".progress .weeks-dates")
    assert "margin-inline-start: auto" in dates and "var(--weeks" in dates


def test_the_period_chips_are_tinted_pills_at_the_control_size() -> None:
    """Polish 4 (§12 "The mockups win" and "The boards are the desk"; §13 controls):
    tinted on the wash with no border, the chosen one teal, 0.9375rem and 40px."""
    chip = _rule(".progress .spent .chip")
    assert "background: var(--teal-wash)" in chip
    assert "border: 0" in chip
    assert "font-size: 0.9375rem" in chip
    assert "min-block-size: 2.5rem" in chip
    chosen = _rule('.progress .spent .chip[aria-pressed="true"]')
    assert "background: var(--teal)" in chosen


def test_a_story_step_is_a_label_on_the_scale() -> None:
    """Polish 5: §13 labels are 0.6875rem uppercase at 0.08em, and the sub is meta."""
    step = _rule(".progress .story-step")
    assert "font-size: 0.6875rem" in step and "letter-spacing: 0.08em" in step
    assert "font-size: 0.875rem" in _rule(".progress .story-sub")


def test_the_upload_row_stacks_its_aside_on_a_phone() -> None:
    """Polish 9: at 390 Yiddish's "A link, a file, or a photo of a page" was cut short.
    The Upload row is marked to stack, and under 40rem its aside goes under the term."""
    drawn = draw(
        {"targum:vocab:yi": vocab(known=5)},
        chosen="yi",
        story={
            "library": False,
            "known": 5,
            "ladder": [],
            "here": None,
            "said": "",
            "texts": [],
            "words": [],
            "uploads": [{"name": "song", "title": "אויפֿן פּריפּעטשיק", "known": 84}],
        },
    )
    classes = drawn["next"]["levelClasses"]
    assert "next-stack" in classes[0].split()
    assert "next-stack" not in classes[1].split(), "an upload's own row is not"
    phone = CSS[CSS.index("@media (max-width: 40rem)") :]
    assert "white-space: normal" in _rule(".progress .next-stack .next-aside", phone)
    assert "flex-direction: column" in _rule(".progress .next-stack .next-link", phone)


def test_a_reading_point_rings_round_not_square() -> None:
    """Polish 11: the outline drew a square box round an 8px dot. The point the arrows are
    on rings with the dot's own stroke, in the focus colour; the line itself is the one
    tab stop and carries the focus ring (design.md §12, "Your level, v3")."""
    ring = _rule(".reading .reading-point.on")
    assert "stroke: var(--focus)" in ring
    assert "outline: 2px solid var(--focus)" in _rule(".reading .chart svg:focus-visible")


def test_a_tip_with_no_room_above_goes_under_its_point() -> None:
    """Polish 11: clamped to the chart's top, the first month's tip sat on its point."""
    script = """
const path = require("path");
const { install, element } = require(path.resolve(DOM_DIR, "dom.js"));
install({});
require(path.resolve(CHARTS));
const host = element("div");
host.rect = { width: 400, height: 120 };
const tip = window.TargumCharts.tipFor(host);
const drawn = host.children[0];
drawn.rect = { width: 80, height: 30 };
tip.show("x", 20, 10);
const low = drawn.style.top;
tip.show("x", 200, 90);
process.stdout.write(JSON.stringify({ low: low, high: drawn.style.top }));
"""
    charts = HARNESS.parent.parent.parent / "src" / "targum" / "render" / "assets" / "charts.js"
    script = script.replace("DOM_DIR", json.dumps(str(HARNESS.parent))).replace(
        "CHARTS", json.dumps(str(charts))
    )
    done = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stderr
    placed = json.loads(done.stdout)
    assert placed["low"] == "24px", "under a point near the top"
    assert placed["high"] == "50px", "above a point with room"


def test_aramaic_rungs_are_said_without_a_link_count_or_level() -> None:
    """Aramaic's rungs are bodies of Targum (design.md §12, 2026-10-25), and the Library has
    no shelf for each yet: a rung is a row, not a link to an empty list, with no count to
    check against a shelf, and Aramaic has no scale, so no foot line (2026-10-28)."""
    drawn = draw(
        {"targum:vocab:arc": vocab(known=40)},
        chosen="arc",
        story={
            "library": True,
            "known": 40,
            "ladder": [
                {"kind": "onkelos", "name": "onkelos", "state": "easy", "share": 96, "readable": 3},
                {
                    "kind": "jonathan-torah",
                    "name": "jonathan-torah",
                    "state": "next",
                    "share": 60,
                    "readable": 0,
                },
            ],
            "here": 0,
            "next": 1,
            "level": None,
            "texts": [],
            "words": [],
        },
    )
    where = drawn["where"]
    assert where["head"] == "You can read Onkelos on your own."
    assert where["step"] == "Your next step is Pseudo-Jonathan."
    assert [rung["tag"] for rung in where["rungs"]] == ["span", "span"]
    assert [rung["state"] for rung in where["rungs"]] == ["easy", "next"]
    assert not any(rung.get("href") for rung in where["rungs"])
    assert [rung["count"] for rung in where["rungs"]] == ["", ""]
    assert where["mark"] is None and where["toward"] is None


def test_aramaic_week_one_starts_with_onkelos() -> None:
    drawn = draw(
        {"targum:vocab:arc": vocab(known=4)},
        chosen="arc",
        story={
            "library": True,
            "known": 4,
            "ladder": [
                {"kind": "onkelos", "name": "onkelos", "state": "next", "share": 40, "readable": 0}
            ],
            "here": None,
            "next": 0,
            "level": None,
            "texts": [],
            "words": [],
        },
    )["where"]
    assert drawn["head"] == "Start with Onkelos."
    assert drawn["step"] == "It uses the most common words, so it's the easiest place to begin."
    assert drawn["go"] == "Show the easiest texts"
