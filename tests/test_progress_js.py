"""The Your Progress page's ledger, run rather than read.

The page was analytics and is now an account of what a reader has built, which means it
does arithmetic it never used to: how many words count as known, which milestone that has
passed, how many are left to the next, and which of the last twelve weeks were read on.

`progress.js` is eight hundred lines and had no test that ran any of it — a parse check
and source greps stood in. Same harness as `test_learn_js.py`: a stub document in
`tests/js/`, not a browser.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from datetime import date, timedelta
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


def draw(stored: dict[str, Any]) -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as where:
        payload = Path(where) / "payload.json"
        # The store holds strings, the way localStorage does.
        payload.write_text(
            json.dumps({"stored": {k: json.dumps(v) for k, v in stored.items()}}),
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

    assert drawn["counts"]["words marked known"] == 12
    assert drawn["counts"]["words saved"] == 17, "known and still learning together"
    assert "texts opened" not in drawn["counts"], "a fact about browsing"
    # Days do not follow the language switcher, because a day is not in a language and
    # you can read both in one.
    assert drawn["counts"]["days reading"] == 2


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

    assert drawn["counts"]["word marked known"] == 1
    assert drawn["counts"]["day reading"] == 1


def test_a_milestone_is_reached_or_it_is_not() -> None:
    """Ten known words passes the first one and leaves the rest listed and quiet. The
    unreached ones are still shown: what is next is the point of a ledger."""
    drawn = draw({"targum:vocab:he": vocab(known=12)})

    assert drawn["marks"]["on"] == [10]
    assert drawn["marks"]["off"][:3] == [50, 100, 250]


def test_the_next_milestone_says_how_far_it_is() -> None:
    """The arithmetic somebody would notice being wrong, and the thousands separator —
    these numbers are the thing the page is for and they get read.

    In a language with no ulpan behind it, which is where the word-count ladder still
    leads the block. Hebrew shows the rung it has reached instead.
    """
    drawn = draw(
        {
            "targum:vocab:ru": vocab(known=962),
            "targum:docs": {"a": {"language": "ru", "title": "One"}},
            "targum:opened": {"a": 1},
        }
    )

    assert drawn["reached"] == "500 words known"
    assert drawn["next"] == "Another 38 to 1,000."


def test_nothing_kept_yet_asks_rather_than_boasting() -> None:
    """A word marked while reading is the one thing that starts this page off, so that is
    what it says. No zero-state milestone, no encouragement."""
    drawn = draw({"targum:vocab:he": vocab(learning=3)})

    assert drawn["counts"]["words marked known"] == 0
    assert drawn["reached"] == "", "nothing has been reached, so no chip"
    assert drawn["next"] == "Mark a word as known and this starts."


def test_the_day_strip_is_twelve_weeks_ending_today() -> None:
    """Days are the one count that is not per-language — a day is not in a language — and
    a day outside the window is still counted in the total, just not drawn."""
    today = date.today()
    days = {
        (today - timedelta(days=n)).isoformat(): 1
        for n in (0, 1, 5, 40, 200)  # the last one is outside the twelve weeks
    }
    drawn = draw({"targum:vocab:he": vocab(known=3), "targum:days": days})

    assert drawn["days"]["cells"] == 84, "twelve weeks of squares"
    assert drawn["days"]["read"] == 4, "and the one 200 days ago is off the end of it"
    assert drawn["counts"]["days reading"] == 5, "though the count still knows about it"
    assert "4 days reading in the last twelve weeks" == drawn["days"]["label"]


def test_a_day_nobody_read_on_says_nothing_at_all() -> None:
    """§6: missed days are quiet, never red. A gap is the resting colour and no label."""
    drawn = draw({"targum:vocab:he": vocab(known=3)})

    assert drawn["days"]["read"] == 0
    assert drawn["days"]["said"] == "Today is the first."


# --- how far into Hebrew ------------------------------------------------------


def banded(**spec: int) -> dict[str, Any]:
    """A Hebrew word list of known words, so many in each difficulty band."""
    out: dict[str, Any] = {}
    n = 0
    for band, count in spec.items():
        for _ in range(count):
            key = f"w{n}"
            out[key] = {"status": KNOWN, "surface": key, "at": 1_700_000_000_000 + n}
            if band != "unrated":
                out[key]["band"] = band.replace("_", " ")
            n += 1
    return out


def ulpan(words: dict[str, Any], language: str = "he") -> dict[str, Any]:
    return draw(
        {
            f"targum:vocab:{language}": words,
            "targum:docs": {"a": {"language": language, "title": "One"}},
            "targum:opened": {"a": 1},
            "targum:days": {"2026-08-25": 1},
        }
    )["ulpan"]


def test_a_rung_is_reached_on_words_weighted_by_how_common_they_are() -> None:
    """Both halves of it: how many words, and how far out they sit. A thousand words that
    reach into the harder bands is a different vocabulary from a thousand of the commonest
    ones, and the ladder has to be able to tell them apart."""
    common = ulpan(banded(easy=1000))
    spread = ulpan(banded(easy=400, fairly_easy=300, moderate=200, hard=100))
    assert "aleph" in common["rung"]
    assert "aleph plus" in spread["rung"]
    assert "aleph plus" not in common["rung"], "the same count, not the same reach"


def test_the_ladder_does_not_flatter() -> None:
    """A mixed six thousand words is somebody who reads; it is not somebody at the top of
    the ulpan ladder. Weighted upward from one rather than around it, this said hey."""
    assert (
        "dalet"
        in ulpan(banded(easy=1500, fairly_easy=1500, moderate=1500, hard=1000, very_hard=500))[
            "rung"
        ]
    )


def test_below_the_first_rung_is_said_plainly() -> None:
    """And is not an achievement: the reader is told the distance, not congratulated for
    standing at the bottom of the ladder."""
    early = ulpan(banded(easy=120, fairly_easy=55, moderate=16))
    assert early["rung"] == "", "no chip, because nothing has been reached"
    assert "words to" in early["next"]


def test_the_distance_to_the_next_rung_is_counted_in_words() -> None:
    """Words, because words are what the reader has and what they can go and get. The
    weighted total is the page's own arithmetic and is never shown — a score on a scale
    nobody else uses is the invented currency §7 rules out."""
    said = ulpan(banded(easy=400, fairly_easy=300, moderate=200, hard=100))["next"]
    assert said.startswith("Another ")
    assert "words to" in said and "(bet)" in said


def test_the_top_of_the_ladder_stops_rather_than_inventing_more() -> None:
    said = ulpan(banded(easy=3000, fairly_easy=3000, moderate=3000, hard=2000, very_hard=1000))
    assert "vav" in said["rung"]
    assert said["next"] == "Past every rung an ulpan keeps."


def test_ulpan_levels_are_shown_for_hebrew_and_nowhere_else() -> None:
    """An ulpan is a Hebrew institution. Hung off a Russian word list it would be a number
    dressed up as a standard — so every other language keeps the count of words known,
    which is a real thing in any of them."""
    hebrew = ulpan(banded(easy=400), language="he")
    assert "aleph" in hebrew["rung"]
    assert hebrew["shown"], "and the block says what the rung is estimated from"

    russian = ulpan(banded(easy=400), language="ru")
    assert russian["rung"] == "250 words known", "the milestone it always had"
    assert not russian["shown"], "and no caveat about a ladder it is not on"


def test_a_word_no_frequency_data_can_rate_still_counts() -> None:
    """Counted at its face value rather than guessed at, the way `annotate/base.py` shows
    an unrated word as no level at all rather than as a level it invented."""
    assert "aleph" in ulpan(banded(unrated=400))["rung"]


# --- an ignored word is ignored -----------------------------------------------


def marked(**spec: int) -> dict[str, Any]:
    """A Hebrew word list by status name, every word in the same difficulty band so the
    band chart has one row to look at."""
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
    assert tile(drawn, "words marked known") == 4
    figures = {int(box["value"].replace(",", "")) for box in drawn["tiles"]}
    # 12 would be everything added up and 9 would be known plus ignored. Neither is a
    # number this reader's four figures can honestly hold.
    assert 12 not in figures and 9 not in figures


def test_nothing_on_the_page_says_how_many_you_ignored() -> None:
    """The line under "Where they are" kept a tally of them. Being shown a count of what
    you dismissed is not being allowed to dismiss it."""
    drawn = page(marked(known=4, ignored=5))
    assert drawn["progressNote"] == ""
    assert "ignor" not in json.dumps(drawn).lower()


def test_ignored_words_are_not_drawn_among_the_others() -> None:
    """Not in the bar of where they are, and not in the chart of how common they are —
    both of which would otherwise put them back in front of the reader as a slice."""
    only_known = page(marked(known=4))
    with_ignored = page(marked(known=4, ignored=5))
    assert with_ignored["bands"] == only_known["bands"]


def test_a_word_with_no_difficulty_is_not_a_kind_of_word() -> None:
    """ "not rated" was a seventh row that read as a category a word could belong to. It is
    not: it is the absence of frequency data for a language, which is a fact about targum
    rather than about the word."""
    words = marked(known=3)
    words["nameless"] = {"status": KNOWN, "surface": "nameless", "at": 1_700_000_000_100}
    drawn = page(words)
    assert "not rated" not in drawn["bands"]
    assert "easy" in drawn["bands"]


# --- what targum taught, and what you already had -----------------------------


def test_words_learned_counts_only_what_was_carried_up_to_known() -> None:
    """The difference the tile is for: a word saved at a level below known and worked up
    to it, against one opened in a text and ticked off as already known. Both are known
    now, and only one of them was learned here."""
    words = marked(known=4)
    for key in list(words)[:2]:
        words[key]["learned"] = 1
    drawn = page(words)
    assert tile(drawn, "words marked known") == 4
    assert tile(drawn, "words learned") == 2


def test_a_word_still_being_learned_is_not_yet_learned() -> None:
    """The flag is set on the way up, so it can be sitting on a word that has since been
    put back down a level. Until it is known again it is not one you have learned."""
    words = marked(learning=3)
    for key in words:
        words[key]["learned"] = 1
    assert tile(page(words), "words learned") == 0


def test_nothing_was_learned_before_the_flag_existed() -> None:
    """Nothing in a finished record says which of the two a word was, so words marked
    before this was written count as neither and the figure starts from nought. Said
    plainly rather than guessed at from dates."""
    assert tile(page(marked(known=6)), "words learned") == 0


def test_one_word_saved_or_learned_is_not_said_in_the_plural() -> None:
    """These labels sit at display size beside the figure they belong to, which is where
    "1 words learned" is impossible not to read."""
    words = marked(known=1)
    words[next(iter(words))]["learned"] = 1
    drawn = page(words)
    assert tile(drawn, "word marked known") == 1
    assert tile(drawn, "word learned") == 1


def test_every_figure_is_said_once_on_the_page() -> None:
    """The tiles under the block counted the same words again in a different shape, and
    said "phrases saved" twice between them. One block, one count each."""
    drawn = page(marked(known=4, learning=3, ignored=5))
    labels = [box["label"] for box in drawn["tiles"]]
    assert len(labels) == len(set(labels)), f"a figure is said twice: {labels}"
    assert labels == [
        "words saved",
        "words marked known",
        "words learned",
        "phrases saved",
        "day reading",
    ], "in the order somebody would say them"


def test_a_figure_carries_its_name_and_nothing_else() -> None:
    """ "90% of the way" was known against still-learning — a fraction whose denominator
    is however many words happen to be part-way up the ladder, so it fell when a reader
    saved a new word and rose when they gave up on one."""
    drawn = page(marked(known=9, learning=1))
    assert [box["delta"] for box in drawn["tiles"]] == [""] * 5
