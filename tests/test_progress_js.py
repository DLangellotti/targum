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
    assert drawn["counts"]["words on your list"] == 17, "known and still learning together"
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
    assert tile(drawn, "words on your list") == 6
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


def test_every_figure_is_said_once_on_the_page() -> None:
    """The tiles under the block counted the same words again in a different shape, and
    said "phrases saved" twice between them. One block, one count each."""
    drawn = page(marked(known=4, learning=3, ignored=5))
    labels = [box["label"] for box in drawn["tiles"]]
    assert len(labels) == len(set(labels)), f"a figure is said twice: {labels}"
    assert labels == [
        "words on your list",
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


def month(name: str, known: int, tokens: int = 100, sections: int = 2) -> dict[str, Any]:
    return {"month": name, "known": known, "tokens": tokens, "sections": sections}


def test_three_months_of_reading_draw_a_line_said_as_a_count_in_ten() -> None:
    """One point a month, each carrying its month, its count in ten and the sections
    behind it; the latest said in a sentence. Never a percentage, never a score."""
    drawn = draw(
        {"targum:vocab:he": vocab(known=3)},
        reading={
            "he": {
                "line": [
                    month("2026-06", 52),
                    month("2026-07", 61, sections=1),
                    month("2026-08", 70, sections=4),
                ],
                "months": 3,
                "sections": 7,
            }
        },
    )["reading"]

    assert drawn["shown"] and drawn["drawn"]
    assert drawn["said"] == ["In August you knew about 7 words in 10 of what you read."]
    assert drawn["points"] == [
        "June 2026: about 5 in 10 · 2 sections",
        "July 2026: about 6 in 10 · 1 section",
        "August 2026: about 7 in 10 · 4 sections",
    ]
    # The board's line: no grid and no scale, each month named under its dot.
    assert drawn["ticks"] == []
    assert drawn["months"] == ["June", "July", "August"] or drawn["months"] == [
        "June 2026",
        "July 2026",
        "August 2026",
    ]
    assert "%" not in json.dumps(drawn)


def test_a_line_that_falls_says_why_and_nothing_else() -> None:
    """Graded dialogue in July, Agnon in August: the line drops, and one sentence names
    the reason — the text, not lost ground — with no apology and no encouragement."""
    drawn = draw(
        {"targum:vocab:he": vocab(known=3)},
        reading={
            "he": {
                "line": [month("2026-06", 70), month("2026-07", 80), month("2026-08", 55)],
                "months": 3,
                "sections": 6,
            }
        },
    )["reading"]

    assert drawn["said"] == [
        "In August you knew about 6 words in 10 of what you read.",
        "It fell because what you read in August had more words new to you, not because you "
        "lost any.",
    ]
    for said in drawn["said"]:
        assert "!" not in said and "don't worry" not in said.lower() and "keep" not in said

    # A dip inside the same count in ten is not a fall anybody was told about.
    level = draw(
        {"targum:vocab:he": vocab(known=3)},
        reading={
            "he": {
                "line": [month("2026-06", 70), month("2026-07", 72), month("2026-08", 68)],
                "months": 3,
                "sections": 6,
            }
        },
    )["reading"]
    assert len(level["said"]) == 1


def test_two_months_draw_the_line() -> None:
    """The board draws its line from two points (§12, "The mockups win on Your Progress",
    2026-10-09)."""
    drawn = draw(
        {"targum:vocab:he": vocab(known=3)},
        reading={"he": {"line": [month("2026-08", 80), month("2026-09", 90)], "months": 2}},
    )["reading"]
    assert drawn["shown"] and drawn["drawn"] and len(drawn["points"]) == 2


def test_under_two_months_the_part_is_not_there() -> None:
    """Under two points there is no line, and no paragraph promising one: the board
    has no waiting state (David, 2026-10-09, "a wall of text"), so the part is hidden
    until there is something to draw."""
    drawn = draw(
        {"targum:vocab:he": vocab(known=3)},
        reading={"he": {"line": [], "months": 1, "sections": 5}},
    )["reading"]
    assert not drawn["shown"] and not drawn["drawn"]
    assert drawn["said"] == []

    nothing = draw({"targum:vocab:he": vocab(known=3)}, reading={})["reading"]
    assert not nothing["shown"] and nothing["said"] == []

    signed_out = draw({"targum:vocab:he": vocab(known=3)})["reading"]
    assert not signed_out["shown"], "absent signed out, not nought"


# -- the story (design.md §12, "Your Progress is a story in three parts", 2026-10-09) ---


LADDER = {
    "library": True,
    "known": 3,
    "ladder": [
        {"kind": "dialogue", "name": "dialogue", "share": 99, "state": "passed", "texts": 9},
        {"kind": "talk", "name": "talk", "share": 96, "state": "passed", "texts": 9},
        {"kind": "article", "name": "article", "share": 93, "state": "here", "texts": 9},
        {"kind": "story", "name": "story", "share": 86, "state": "next", "texts": 9},
        {"kind": "novel", "name": "novel", "share": 70, "state": "ahead", "texts": 9},
        {"kind": "poetry", "name": "poetry", "share": None, "state": "ahead", "texts": 9},
    ],
    "here": 2,
    "said": "nearly",
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


def test_where_you_are_names_the_hardest_kind_you_would_follow() -> None:
    """The headline is worded by the share: 90–95% is "nearly all of"."""
    drawn = story()["where"]
    assert drawn["head"] == "You'd follow nearly all of a news article"
    assert drawn["shown"] and not drawn["note"]
    assert [rung["state"] for rung in drawn["rungs"]] == [
        "passed",
        "passed",
        "here",
        "next",
        "ahead",
        "ahead",
    ]
    # The share is on the rung you are on and the next one, and nowhere else.
    assert [rung["text"] for rung in drawn["rungs"]] == [
        "A conversation",
        "A video",
        "A news article93%",
        "A short story86%",
        "A novel",
        "A poem",
    ]
    assert [rung["ticked"] for rung in drawn["rungs"]] == [True, True, False, False, False, False]
    assert drawn["rungs"][2]["current"] == "step"


def test_every_touchstone_opens_its_shelf_in_the_library() -> None:
    rungs = story()["where"]["rungs"]
    assert rungs[3]["href"] == "/library?k=k#see/kind/story"
    assert all("#see/kind/" in rung["href"] for rung in rungs)


@pytest.mark.parametrize(
    ("said", "head"),
    [
        ("follow", "You'd follow a news article"),
        ("most", "You'd follow most of a news article"),
    ],
)
def test_the_three_wordings(said: str, head: str) -> None:
    assert story(said=said)["where"]["head"] == head


def test_with_no_rung_reached_the_first_is_where_to_start() -> None:
    ladder = [dict(rung, state="ahead") for rung in LADDER["ladder"]]
    ladder[0]["state"] = "next"
    drawn = story(ladder=ladder, here=None, said="")["where"]
    assert drawn["head"] == "A conversation is the place to start"


def test_italian_childrens_books_are_called_so() -> None:
    ladder = [{"kind": "story", "name": "children-book", "share": 97, "state": "here", "texts": 19}]
    drawn = story(ladder=ladder, here=0, said="follow")["where"]
    assert drawn["head"] == "You'd follow a children's book"
    assert drawn["rungs"][0]["text"] == "A children's book97%"
    assert drawn["rungs"][0]["href"].endswith("#see/kind/story")


def test_aramaic_shows_known_words_and_no_ladder() -> None:
    """wordfreq has no Aramaic list, so its texts cannot be measured (David, 2026-10-08)."""
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
    assert "no ladder of texts for Aramaic" in drawn["where"]["note"]
    assert drawn["how"] == "Reading"
    assert drawn["next"]["wordsTitle"].startswith("Words you keep meeting, from your Aramaic list")


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
    assert "library has nothing in this language" in drawn["where"]["note"]
    assert drawn["how"] == "Reading and watching", "nobody's voice in Yiddish"
    nxt = drawn["next"]
    assert nxt["textsTitle"].startswith("The library has nothing in this language yet")
    assert nxt["level"][0]["href"] == "/add?k=k"
    assert nxt["level"][1]["text"] == "אויפֿן פּריפּעטשיקUploaded by you | 84% known"
    assert nxt["more"] == "All your uploads →"


def test_signed_out_the_story_says_what_signing_in_would_show() -> None:
    drawn = draw({"targum:vocab:he": vocab(known=3)})
    assert drawn["where"]["head"] == "Sign in and we'll say which texts you'd follow."
    assert not drawn["where"]["shown"]
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
    assert drawn["met"][0]["text"].endswith("met in 4 texts")
    # A word the server met that this browser has not seen yet is still named.
    assert drawn["met"][1]["text"] == "elsewhere | met in 2 texts"
    # The title alone and its share known, as the board has it.
    assert drawn["level"] == [{"text": "יונה | 91% known", "href": "/library?k=k#jonah"}]
    assert drawn["more"] == "More in the Library →"


def test_nothing_met_twice_is_one_quiet_line() -> None:
    drawn = story(words=[], texts=[])["next"]
    assert drawn["met"] == [] and drawn["metEmpty"] == "None yet."
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
    assert drawn["label"] == "5 words taken up in the last twelve weeks"
    assert drawn["shades"] == ["var(--step-2)", "var(--step-4)"]
    assert drawn["titles"][-1].endswith(": 3 words")
    assert not drawn["legend"]


def test_no_words_lately_is_said_rather_than_drawn_flat() -> None:
    words = _on(date.today() - timedelta(days=300), 4, "old")
    assert draw({"targum:vocab:he": words})["weeks"]["said"] == (
        "No words taken up in the last twelve weeks."
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
