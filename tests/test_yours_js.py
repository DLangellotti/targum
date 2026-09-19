"""Your Words — the page behind the account (2026-09-11) — run rather than read.

The words you are learning, the commonest words you may already know, and your phrases,
on one page. These lists stood on Learn until 2026-09-11; the tests came with them.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import pytest
from test_learn_js import reader, vocabulary, word

HARNESS = Path(__file__).resolve().parent / "js" / "yours.js"

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")


def draw(stored: dict[str, str] | None = None, **options: Any) -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as where:
        payload = Path(where) / "payload.json"
        payload.write_text(
            json.dumps({"stored": stored or {}, **options}, ensure_ascii=False), encoding="utf-8"
        )
        done = subprocess.run(
            ["node", str(HARNESS), str(payload)], capture_output=True, text=True, timeout=60
        )
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def test_the_word_list_starts_on_what_you_are_still_learning() -> None:
    """Known words are the ones that need no more work. The list opens on the ones that
    do, which is what the markup's selected option says and what the page must obey."""
    drawn = draw(
        vocabulary(
            word("ספר", "book", status=9),
            word("דרך", "road", status=2),
            word("עיר", "city", status=0),
        )
    )
    assert drawn["shown"] and not drawn["nothing"]
    assert [row["term"] for row in drawn["words"]] == ["דרך"]
    assert drawn["wordsTitle"] == "Your Words (1)"


def test_every_word_is_there_when_that_is_what_was_asked_for() -> None:
    drawn = draw(
        vocabulary(word("ספר", "book", status=9), word("דרך", "road", status=2)), filter="all"
    )
    assert sorted(row["term"] for row in drawn["words"]) == ["דרך", "ספר"]


def test_a_search_looks_at_the_word_its_dictionary_form_and_its_meaning() -> None:
    """Three columns, because a reader who remembers only the English is the one most in
    need of the search."""
    kept = vocabulary(
        word("ספר", "book", status=2),
        word("הלך", "walked", status=2, surface="הולך"),
        word("עיר", "city", status=2),
    )
    assert [row["term"] for row in draw(kept, search="book")["words"]] == ["ספר"]
    assert [row["term"] for row in draw(kept, search="הלך")["words"]] == ["הולך"]
    assert draw(kept, search="zzz")["wordsEmpty"] == "Nothing here matches that."


def test_only_one_language_of_meanings_is_shown_and_it_says_which() -> None:
    """A reader of two languages has two answers for every word, and the page shows one:
    the language they last read this one into. The cell says so in its own markup."""
    stored = vocabulary(word("ספר", "book", status=2))
    stored["targum:meanings:he:ru"] = json.dumps(
        {"ספר": {"meaning": "книга", "note": "", "at": 0, "seen": 500}}, ensure_ascii=False
    )
    drawn = draw(stored)
    assert [w["meaning"] for w in drawn["words"]] == ["книга"]
    assert drawn["words"][0]["lang"] == "ru" and drawn["words"][0]["dir"] == "ltr"


def test_a_language_this_account_does_not_read_is_never_offered() -> None:
    """Somebody who tried Russian and then turned it off is not still shown a column of
    it: what the account said (`targum:reads`, mirrored by sync) decides."""
    stored = vocabulary(word("ספר", "book", status=2))
    stored["targum:meanings:he:ru"] = json.dumps(
        {"ספר": {"meaning": "книга", "note": "", "at": 0, "seen": 900}}, ensure_ascii=False
    )
    stored["targum:reads"] = json.dumps(["en"])
    drawn = draw(stored)
    assert [w["meaning"] for w in drawn["words"]] == ["book"]
    assert drawn["words"][0]["lang"] == "en"


def test_with_nobody_signed_in_nothing_is_hidden() -> None:
    stored = vocabulary(word("ספר", "book", status=2))
    stored["targum:meanings:he:ru"] = json.dumps(
        {"ספר": {"meaning": "книга", "note": "", "at": 0, "seen": 900}}, ensure_ascii=False
    )
    assert [w["meaning"] for w in draw(stored)["words"]] == ["книга"]


def test_a_meaning_in_a_language_you_are_not_reading_is_not_shown() -> None:
    stored = vocabulary(word("ספר", "book", status=2))
    stored["targum:meanings:he:ru"] = json.dumps(
        {"אור": {"meaning": "свет", "note": "", "at": 0, "seen": 500}}, ensure_ascii=False
    )
    assert [w["meaning"] for w in draw(stored)["words"]] == [""]


def test_your_own_meaning_is_the_one_shown() -> None:
    drawn = draw(vocabulary(word("ספר", "book", status=2, note="scroll")))
    assert drawn["words"][0]["meaning"] == "scroll"


def test_phrases_are_grouped_by_the_text_they_came_from() -> None:
    """A phrase out of its text is a string of words nobody can place."""
    stored = {
        "targum:docs": json.dumps({"h1": {"language": "he", "title": "אהבת ציון"}}),
        "targum:picked:h1": json.dumps({"s1": [{"text": "לב טוב", "meaning": "a good heart"}]}),
    }
    drawn = draw(stored)
    assert drawn["phrases"] == {"אהבת ציון": ["לב טוב"]}
    assert drawn["phrasesTitle"] == "Your Phrases (1)"


def test_every_row_offers_to_copy_its_word() -> None:
    stored = vocabulary(word("ספר", "book", status=2), word("דרך", "road", status=2))
    stored["targum:docs"] = json.dumps({"h1": {"language": "he", "title": "אהבת ציון"}})
    stored["targum:picked:h1"] = json.dumps({"s1": [{"text": "לב טוב", "meaning": "a good heart"}]})
    drawn = draw(stored)
    assert sorted(drawn["copies"]["words"]) == ["Copy דרך", "Copy ספר"]
    assert drawn["copies"]["phrases"] == ["Copy לב טוב"]


def test_nothing_offers_an_export_to_a_browser_with_no_account() -> None:
    drawn = draw(vocabulary(word("ספר", "book", status=2)))
    assert drawn["exports"] == {"words": True, "anki": True, "phrases": True}, "all hidden"


def test_an_ignored_word_does_not_blank_the_table() -> None:
    """Ignored is 0, and the status table has no 0: it is not a step on the ramp."""
    drawn = draw(
        vocabulary(word("ספר", "book", status=9), word("עיר", "city", status=0)), filter="all"
    )
    rows = {row["term"]: row["well"] for row in drawn["words"]}
    assert rows["עיר"] == "ignored" and rows["ספר"] == "known"


def test_the_words_you_may_already_know_stand_on_this_page_and_feed_the_list() -> None:
    """The checklist lives here after the first visit (2026-09-11). Marking a page known
    puts the words on the ledger and the list is collected again, so the count in its
    title rises without a reload."""
    pages = {
        "0": {
            "words": [{"form": f, "meaning": "m", "band": "easy"} for f in ["של", "את", "הוא"]],
            "offset": 0,
            "next": None,
        }
    }
    drawn = draw(vocabulary(word("ספר", "book", status=2)), pages=pages)
    assert not drawn["claim"]["hidden"] and drawn["claim"]["rows"] == ["של", "את", "הוא"]
    # And the lines that came back changed, once, after the lists are drawn
    # (targum-internal#290). Asserted as the whole list rather than as a membership, so a
    # page that starts asking for something new has to say so here.
    assert drawn["asked"] == ["/words/common?offset=0&limit=50", "/slips", "/slips?all=1"]
    marked = draw(
        vocabulary(word("ספר", "book", status=2)),
        pages=pages,
        filter="all",
        do=[{"type": "all"}, {"type": "yes"}],
    )
    assert sorted(marked["ledger"]) == ["את", "הוא", "ספר", "של"]
    assert marked["claim"]["hidden"] and marked["claim"]["said"] == "That's the whole list."
    assert marked["wordsTitle"] == "Your Words (4)", "collected again, not drawn stale"


def test_a_browser_with_nothing_kept_is_told_so() -> None:
    drawn = draw({})
    assert drawn["nothing"] and not drawn["shown"]


# -- Your targums: the shelf rows (moved here from Learn on 2026-09-11) ---------------


def test_a_shelf_row_is_a_row_of_columns() -> None:
    """It was a stack of two-line entries with the controls floating off to the right —
    three alignments in one row, which reads as none. One cell each now, under a heading
    that says what it is."""
    drawn = draw(
        which="texts",
        readers=[
            reader(
                "genesis-he",
                "בראשית",
                entry="genesis",
                chapters=[{"number": n} for n in range(50)],
                readyChapters=50,
            )
        ],
    )
    (row,) = drawn["shelf"]
    assert drawn["head"] is False, "the columns are labelled"
    assert row["title"] == "בראשית"
    assert row["cover"] is not None
    assert row["chapters"] == "50 chapters", (
        "all of it bought, said as a count rather than a fraction"
    )
    assert "ago" in row["opened"] or row["opened"] == "not opened yet"
    assert row["controls"] == ["Chapters", "Delete"]


def test_a_text_with_one_part_says_so_rather_than_counting_to_one() -> None:
    drawn = draw(which="texts", readers=[reader("article-he", "כתבה")])
    (row,) = drawn["shelf"]
    assert row["chapters"] == "—", "nothing to count, and nothing pretending there is"
    assert row["controls"] == ["Delete"], "and no chapters to open"


def test_a_shelf_with_some_chapters_still_to_come_says_so() -> None:
    """ "2 of 4" is a fraction with nothing to say what it is a fraction of."""
    drawn = draw(
        which="texts",
        readers=[
            reader(
                "genesis-he",
                "בראשית",
                entry="genesis",
                chapters=[{"number": n} for n in range(4)],
                readyChapters=2,
            )
        ],
    )
    (row,) = drawn["shelf"]
    assert row["chapters"] == "2 of 4 translated"


def test_a_text_the_catalogue_never_heard_of_still_gets_a_row() -> None:
    """Covers are drawn on the project's budget, for the library's own texts. Most of a
    reader's shelf is their own, has no cover and never will, and a shelf of empty frames
    would be worse than a shelf of letters — so the tile rests on the text's own first
    letter instead."""
    drawn = draw(which="texts", readers=[reader("ynet-he", "כתבה על משהו")])
    (row,) = drawn["shelf"]
    assert row["title"] == "כתבה על משהו"
    assert row["cover"] is not None, "the row keeps its shape"
    assert row["cover"]["letter"] == "כ", "and rests on the text's own letter"


# --- what to work on (targum-internal#103) --------------------------------------------
#
# Dmitry Z, 2026-09-16, on the one thing in the conversation he called genuinely useful:
# "anki requires bookkeeping and discipline that I lack". And the constraint, three
# minutes later: "if smth gonna ping me or bother me like duolingo I'll fucking delete
# it". So it is pull and never push, and most of what these assert is what is *absent*.


def test_the_fold_offers_the_words_flagged_longest_ago() -> None:
    """The plainest order that is true of the data. `at` is when a word was kept and
    there is nothing else — no record that a word was met again, no count of times seen,
    no interval — so the queue is the ones that have been sitting there longest. Any
    cleverer order would be a claim the ledger cannot support."""
    drawn = draw(
        vocabulary(
            word("ספר", "book", status=2, at=300),
            word("דרך", "road", status=1, at=100),
            word("עיר", "city", status=3, at=200),
        )
    )
    assert not drawn["workOn"]["hidden"]
    assert [row["term"] for row in drawn["workOn"]["rows"]] == ["דרך", "עיר", "ספר"]


def thirty() -> dict[str, str]:
    """Thirty words being learned, stamped in order: w01 is the oldest. The fold on Your
    Words holds twenty."""
    return vocabulary(*[word(f"w{n:02d}", f"m{n}", status=2, at=n * 10) for n in range(1, 31)])


def terms(drawn: dict[str, Any]) -> list[str]:
    return [row["term"] for row in drawn["workOn"]["rows"]]


def test_the_fold_turns_over_between_visits() -> None:
    """targum-internal#336: "show different words each time I come to the page".

    Oldest first and a cap meant the same rows on every visit until one was marked known,
    because `at` is written once. The order stays — it is the only honest one — and what
    moves is where in it the fold opens: each visit starts where the last ended.
    """
    first = draw(thirty())
    assert terms(first) == [f"w{n:02d}" for n in range(1, 21)], "a first visit opens at the oldest"
    assert first["workOn"]["more"], "and there is another screenful to turn to"

    second = draw({**thirty(), "targum:work-at:he": first["workOn"]["left"]})
    assert terms(second)[0] == "w21", "the next visit starts where the last one ended"
    # Thirty words and a screen of twenty: it comes round to the oldest, in order.
    assert terms(second) == [f"w{n:02d}" for n in [*range(21, 31), *range(1, 11)]]


def test_the_press_turns_to_the_next_screenful() -> None:
    turned = draw(thirty(), do=[{"type": "more"}])
    assert terms(turned)[0] == "w21"
    twice = draw(thirty(), do=[{"type": "more"}, {"type": "more"}])
    assert terms(twice)[0] == "w11", "and round again"


def test_marking_a_word_does_not_turn_the_page_under_the_hand() -> None:
    """The place is a row, not a position. A word that leaves the list takes its own row
    and nothing else moves: the fold still opens on the row it stood on."""
    after = draw(thirty(), do=[{"type": "work", "word": "w05", "key": 0}])
    shown = terms(after)
    assert shown[0] == "w01" and "w05" not in shown
    assert shown[-1] == "w21", "the screenful is made up from the far end, not shuffled"


def test_a_fold_that_fits_has_nothing_to_turn_to() -> None:
    """No press with no job (design.md §13), and nothing that says how much is behind it:
    the press says what it does and "12 more" is how a queue starts chasing."""
    small = draw(vocabulary(word("ספר", "book", status=2, at=300)))
    assert not small["workOn"]["more"]
    assert small["workOn"]["left"] is None, "and it keeps no place it does not need"


def test_the_fold_holds_only_words_being_learned() -> None:
    """Known words need no more work and an ignored one is not a word being learned."""
    drawn = draw(
        vocabulary(
            word("ספר", "book", status=9, at=100),
            word("עיר", "city", status=0, at=200),
            word("דרך", "road", status=2, at=300),
        )
    )
    assert [row["term"] for row in drawn["workOn"]["rows"]] == ["דרך"]


def test_a_reader_with_nothing_to_work_on_sees_no_fold() -> None:
    """Not an empty state and not an invitation: absence. A reader who has flagged no
    words is not being told they are behind."""
    drawn = draw(vocabulary(word("ספר", "book", status=9, at=100)))
    assert drawn["workOn"]["hidden"]
    assert drawn["workOn"]["rows"] == []

    empty = draw({})
    assert empty["workOn"]["hidden"]


def test_knowing_a_word_takes_it_off_the_fold_through_the_ordinary_path() -> None:
    """One store and one counter. The same `updateWord` the table's editor calls, so the
    known count rises once and no second ledger exists to disagree with the first."""
    drawn = draw(
        vocabulary(
            word("ספר", "book", status=2, at=100),
            word("דרך", "road", status=1, at=200),
        ),
        do=[{"type": "work", "word": "ספר", "key": 0}],
    )
    assert [row["term"] for row in drawn["workOn"]["rows"]] == ["דרך"]
    assert drawn["ledger"]["ספר"]["status"] == 9, "and it is known in the one ledger"
    # Carried up from a level below, which is what `learned` records.
    assert drawn["ledger"]["ספר"]["learned"] == 1


def test_still_learning_steps_a_word_back_down_its_ladder() -> None:
    """The honest opposite of the button beside it. Both say what the reader knows about
    the word, and both say it in the one ledger — a press that changed nothing would
    have been a control with no job."""
    drawn = draw(
        vocabulary(
            word("ספר", "book", status=3, at=100),
            word("דרך", "road", status=1, at=200),
        ),
        do=[{"type": "work", "word": "ספר", "key": 1}],
    )
    assert [row["term"] for row in drawn["workOn"]["rows"]] == ["דרך"]
    assert drawn["ledger"]["ספר"]["status"] == 2, "nearly there, back to getting there"


def test_stepping_a_word_down_does_not_restamp_when_it_was_kept() -> None:
    """`at` is when a word was kept, it is what the table's Kept column shows, and it is
    written once and preserved for life — so re-stamping it to reorder a queue would
    quietly age every word in the product to today. The fold is ordered by it, which
    means a press does not reorder the fold either."""
    drawn = draw(
        vocabulary(
            word("ספר", "book", status=2, at=100),
            word("דרך", "road", status=1, at=200),
        ),
        do=[{"type": "work", "word": "ספר", "key": 1}],
    )
    assert drawn["ledger"]["ספר"]["status"] == 1
    assert drawn["ledger"]["ספר"]["at"] == 100, "and kept when it was kept"


def test_a_word_just_met_has_nowhere_lower_to_go() -> None:
    """Saying "still learning" about a word marked met once is agreement, and agreement
    is not news. It leaves the sitting and the ledger is untouched — in particular it
    does not fall into the ignored level, which is a different thing the reader chose."""
    drawn = draw(
        vocabulary(
            word("ספר", "book", status=1, at=100),
            word("דרך", "road", status=1, at=200),
        ),
        do=[{"type": "work", "word": "ספר", "key": 1}],
    )
    assert [row["term"] for row in drawn["workOn"]["rows"]] == ["דרך"]
    assert drawn["ledger"]["ספר"]["status"] == 1, "not 0, which is ignored"


def test_a_word_stepped_down_is_gone_for_the_sitting_and_back_tomorrow() -> None:
    """The step down is the ledger and the skip is the sitting, and they are separate.
    Nothing is scheduled and nothing is stored about the skip: come back and the word is
    here again, one level lower, which is true — it is still a word being learned."""
    drawn = draw(
        vocabulary(word("ספר", "book", status=3, at=100)),
        do=[{"type": "work", "word": "ספר", "key": 1}],
    )
    assert drawn["workOn"]["rows"] == []
    again = draw(vocabulary(word("ספר", "book", status=2, at=100)))
    assert [row["term"] for row in again["workOn"]["rows"]] == ["ספר"]


def test_the_fold_offers_a_sitting_rather_than_a_backlog() -> None:
    """Twenty is a cap and never a target. Nothing counts what is behind it: a number
    beside the heading would be the "12 words due" this card exists not to say."""
    many = {}
    for n in range(30):
        many.update(word(f"מילה{n}", f"word {n}", status=1, at=n))
    drawn = draw(vocabulary(*[{k: v} for k, v in many.items()]))
    assert len(drawn["workOn"]["rows"]) == 20
    assert "20" not in drawn["wordsTitle"] or "30" in drawn["wordsTitle"]


def test_a_row_says_the_word_its_meaning_and_two_answers() -> None:
    """Three things about a word and the two questions, and nothing else: no level
    ladder, no note field, no delete."""
    drawn = draw(vocabulary(word("ספר", "book", status=2, at=100)))
    row = drawn["workOn"]["rows"][0]
    assert row["term"] == "ספר"
    assert row["meaning"] == "book"
    assert row["keys"] == ["I know this", "Still learning"]


def test_a_word_passed_over_stays_passed_over_for_the_rest_of_the_sitting() -> None:
    """Marking a word known calls back to the page, which redraws the whole list — and
    clearing the skips there took a word the reader had just passed over and put it back
    in front of them, mid-sitting. Found on the running page, not here."""
    drawn = draw(
        vocabulary(
            word("מלך", "king", status=1, at=100),
            word("ספר", "book", status=2, at=200),
            word("דרך", "road", status=3, at=300),
        ),
        do=[
            {"type": "work", "word": "מלך", "key": 1},
            {"type": "work", "word": "ספר", "key": 0},
        ],
    )
    assert [row["term"] for row in drawn["workOn"]["rows"]] == ["דרך"], (
        "the skipped word does not come back because another was marked"
    )


SLIP = {
    "id": 7,
    "wrote": "אני הלך אתמול",
    "recast": "אֲנִי הָלַכְתִּי אֶתְמוֹל",
    "changed": ["הָלַכְתִּי"],
    "why": "Past tense: הָלַכְתִּי, not הָלַךְ.",
    "language": "he",
    "at": 50,
}


def with_phrase(
    stored: dict[str, str], text: str, status: int = 1, at: int = 0, meaning: str = ""
) -> dict[str, str]:
    """`stored` with one phrase kept from a text, at a level on the ladder. The phrase's
    meaning is merged into the words' own meanings store rather than written over it."""
    meanings = json.loads(stored.get("targum:meanings:he:en", "{}"))
    meanings["phrase:p1"] = {"meaning": meaning, "note": "", "at": 0, "seen": 1}
    return {
        **stored,
        "targum:docs": json.dumps({"h1": {"language": "he", "title": "אהבת ציון"}}),
        "targum:picked:h1": json.dumps(
            {"s1": [{"id": "p1", "text": text, "status": status, "at": at}]}
        ),
        "targum:meanings:he:en": json.dumps(meanings, ensure_ascii=False),
    }


def test_the_fold_has_a_words_tab_and_a_phrases_tab() -> None:
    """The same question — what is worth going over — asked of words and of phrases, so
    one fold with two tabs (2026-09-18). It opens on the words."""
    stored = with_phrase(
        vocabulary(word("ספר", "book", status=2, at=100)), "לב טוב", meaning="a good heart"
    )
    drawn = draw(stored, slips=[SLIP])
    assert drawn["workOn"]["tabs"] == "words"
    assert not drawn["workOn"]["wordsHidden"] and drawn["workOn"]["phrasesHidden"]
    assert drawn["workOn"]["button"] == "Generate sentences with these words"


def test_the_phrases_tab_holds_kept_phrases_and_corrected_lines_oldest_first() -> None:
    """A phrase kept from a text and a line the conversation corrected, in one list: the
    slip at 50 was there before the phrase at 60."""
    stored = with_phrase(
        vocabulary(word("ספר", "book", status=2, at=100)), "לב טוב", at=60, meaning="a good heart"
    )
    drawn = draw(stored, slips=[SLIP], do=[{"type": "tab", "which": "phrases"}])
    fold = drawn["workOn"]
    assert fold["tabs"] == "phrases"
    assert fold["wordsHidden"] and not fold["phrasesHidden"]
    assert [(row["kind"], row["term"]) for row in fold["phrases"]] == [
        ("slip", SLIP["recast"]),
        ("phrase", "לב טוב"),
    ]
    assert all(row["keys"] == ["I know this", "Still learning"] for row in fold["phrases"])
    assert fold["phrases"][1]["meaning"] == "a good heart"
    assert fold["button"] == "Generate sentences with these phrases"


def test_a_known_or_unmarked_phrase_is_not_there_to_work_on() -> None:
    stored = with_phrase(vocabulary(word("ספר", "book", status=2, at=100)), "לב טוב", status=9)
    drawn = draw(stored)
    assert drawn["workOn"]["tabs"] is None, "no tab with nothing under it"
    assert drawn["workOn"]["phrases"] == []


def test_with_only_one_half_there_are_no_tabs() -> None:
    """A tab with nothing under it is an empty state with a label on it. A reader with
    only phrases sees the phrases, and the door speaks about them."""
    drawn = draw(vocabulary(word("ספר", "book", status=9, at=100)), slips=[SLIP])
    fold = drawn["workOn"]
    assert not fold["hidden"] and fold["tabs"] is None
    assert fold["wordsHidden"] and not fold["phrasesHidden"]
    assert [row["term"] for row in fold["phrases"]] == [SLIP["recast"]]
    assert drawn["talk"]["foot"] is False, "the door is offered for the phrases"
    assert fold["button"] == "Generate sentences with these phrases"


def test_knowing_a_kept_phrase_writes_it_where_the_reader_keeps_it() -> None:
    stored = with_phrase(vocabulary(word("ספר", "book", status=2, at=100)), "לב טוב", status=2)
    drawn = draw(
        stored,
        do=[{"type": "tab", "which": "phrases"}, {"type": "phrase", "term": "לב טוב", "key": 0}],
    )
    assert drawn["picked"]["s1"][0]["status"] == 9, "in the text's own store"
    assert drawn["workOn"]["phrases"] == []
    assert drawn["workOn"]["tabs"] is None
    assert not drawn["workOn"]["wordsHidden"], "a worked-through tab hands over to the other"


def test_still_learning_steps_a_phrase_down_and_out_of_the_sitting() -> None:
    stored = with_phrase(vocabulary(word("ספר", "book", status=2, at=100)), "לב טוב", status=3)
    drawn = draw(
        stored,
        filter="all",
        do=[{"type": "tab", "which": "phrases"}, {"type": "phrase", "term": "לב טוב", "key": 1}],
    )
    assert drawn["picked"]["s1"][0]["status"] == 2, "one step down"
    assert drawn["workOn"]["phrases"] == []
    assert drawn["phrases"] == {"אהבת ציון": ["לב טוב"]}, "still kept"


def test_knowing_a_corrected_line_is_said_to_the_account() -> None:
    """The slip lives on the account, so that is where "I know this" goes. The line
    leaves the list; the record keeps it."""
    drawn = draw(
        vocabulary(word("ספר", "book", status=9, at=100)),
        slips=[SLIP],
        do=[{"type": "phrase", "term": SLIP["recast"], "key": 0}],
    )
    assert drawn["told"] == [{"url": "/slips/7", "body": {"known": True}}]
    assert drawn["workOn"]["hidden"], "nothing left to work on"
    assert drawn["rewrote"]["rows"][0]["wrote"] == SLIP["wrote"], "the record keeps it"


def test_a_corrected_line_the_account_refused_comes_back() -> None:
    drawn = draw(
        vocabulary(word("ספר", "book", status=9, at=100)),
        slips=[SLIP],
        refuse=True,
        do=[{"type": "phrase", "term": SLIP["recast"], "key": 0}],
    )
    assert [row["term"] for row in drawn["workOn"]["phrases"]] == [SLIP["recast"]]


def test_still_learning_on_a_corrected_line_writes_nothing() -> None:
    """A slip has no ladder, so the press only moves it out of the sitting."""
    drawn = draw(
        vocabulary(word("ספר", "book", status=9, at=100)),
        slips=[SLIP],
        do=[{"type": "phrase", "term": SLIP["recast"], "key": 1}],
    )
    assert drawn["told"] == []
    assert drawn["workOn"]["phrases"] == []


def test_the_record_of_corrected_lines_stands_under_your_phrases() -> None:
    """Every line, with the words they did not write marked and the model's reason, and
    no control on a row: the record, not the queue."""
    drawn = draw(vocabulary(word("ספר", "book", status=2, at=100)), slips=[SLIP])
    assert not drawn["rewrote"]["hidden"]
    row = drawn["rewrote"]["rows"][0]
    assert row["wrote"] == "אני הלך אתמול"
    assert row["changed"] == ["הָלַכְתִּי"], "the word they did not write is marked"
    assert row["why"].startswith("Past tense")


def test_no_corrected_lines_is_no_heading() -> None:
    drawn = draw(vocabulary(word("ספר", "book", status=2, at=100)))
    assert drawn["rewrote"]["hidden"] and drawn["rewrote"]["rows"] == []


def anki(drawn: dict[str, Any]) -> tuple[dict[str, str], list[list[str]]]:
    """The one saved file, split into its header lines and its notes."""
    assert len(drawn["saved"]) == 1, "one press, one file"
    file = drawn["saved"][0]
    head: dict[str, str] = {}
    notes: list[list[str]] = []
    for line in file["text"].split("\n"):
        if not line:
            continue
        if line.startswith("#"):
            key, _, value = line[1:].partition(":")
            head[key] = value
        else:
            notes.append(line.split("\t"))
    return head, notes


def test_the_anki_export_names_its_deck_and_its_notetype() -> None:
    """Anki 2.1.55 and later reads these five lines, which is the difference between a
    file that imports as a named deck of Basic notes and a file the reader has to
    configure a mapping for before a single card exists."""
    drawn = draw(
        vocabulary(word("ספר", "book", status=2, at=100)),
        do=[{"type": "export", "which": "anki"}],
    )
    head, _ = anki(drawn)
    assert head["separator"] == "tab"
    assert head["notetype"] == "Basic"
    assert head["deck"] == "targum Hebrew", "the language as the reader's page names it"
    assert head["tags column"] == "3"
    assert head["html"] == "false", "a meaning with a < in it reads as <"


def test_an_anki_note_is_the_word_what_it_means_and_where_it_came_from() -> None:
    """Three fields, and the third is tags because Basic has only two. The dictionary
    form joins the back when it is not already the face of the card — a note showing
    ספר and then ספר underneath would be teaching nothing."""
    drawn = draw(
        vocabulary(word("ספר", "books", surface="ספרים", status=3, at=100)),
        do=[{"type": "export", "which": "anki"}],
    )
    _, notes = anki(drawn)
    assert len(notes) == 1
    front, back, tags = notes[0]
    assert front == "ספרים"
    assert "books" in back
    assert "ספר" in back, "the dictionary form, since it is not the front"
    assert tags.split() == ["targum", "targum::he", "targum::level-3"]


def test_the_anki_tag_carries_the_level_as_a_number() -> None:
    """The level names are translated. A tag built from one would put a reader who
    switched the interface to Russian into a second, silently separate deck."""
    drawn = draw(
        vocabulary(word("ספר", "book", status=1, at=100), word("דרך", "road", status=2, at=200)),
        do=[{"type": "export", "which": "anki"}],
    )
    _, notes = anki(drawn)
    levels = sorted(note[2].split()[-1] for note in notes)
    assert levels == ["targum::level-1", "targum::level-2"]


def test_a_reader_s_own_note_travels_with_the_card() -> None:
    """It is the part of the back they wrote, so it is the part they will recognise, so
    it goes before the dictionary form rather than after it."""
    drawn = draw(
        vocabulary(word("ספרר", "book", surface="ספר", status=2, at=100, note="as in a scroll")),
        do=[{"type": "export", "which": "anki"}],
    )
    _, notes = anki(drawn)
    back = notes[0][1]
    assert "as in a scroll" in back
    assert back.index("as in a scroll") < back.index("ספרר")


def test_a_tab_in_a_meaning_does_not_become_a_second_field() -> None:
    """Tabs and newlines are the format itself. A meaning carrying one would have split
    into two fields or two notes, and the reader would have found out by importing a
    deck with a card missing its back."""
    drawn = draw(
        vocabulary(word("ספר", "a book\tor a scroll\nsometimes", status=2, at=100)),
        do=[{"type": "export", "which": "anki"}],
    )
    _, notes = anki(drawn)
    assert len(notes) == 1, "one word, one note"
    assert len(notes[0]) == 3, "one word, three fields"
    assert "a book or a scroll sometimes" in notes[0][1]


def test_the_anki_file_carries_no_byte_order_mark() -> None:
    """The CSV has one so a spreadsheet opens Hebrew. Anki reads UTF-8 and would put the
    mark inside the first field of the first note, where it is invisible and permanent."""
    drawn = draw(
        vocabulary(word("ספר", "book", status=2, at=100)),
        do=[{"type": "export", "which": "anki"}],
    )
    file = drawn["saved"][0]
    assert not file["text"].startswith("﻿")
    assert file["text"].startswith("#separator:tab")
    assert file["name"] == "targum Hebrew words.txt"
    assert file["type"].startswith("text/plain")


def test_the_anki_button_appears_with_the_others_or_not_at_all() -> None:
    """An export is the account's: a file assembled out of whatever is in this browser is
    a subset with no sign that anything is missing. Signed out, none of the three."""
    drawn = draw(vocabulary(word("ספר", "book", status=2, at=100)))
    assert drawn["exports"] == {"words": True, "anki": True, "phrases": True}
    signed = draw(
        vocabulary(word("ספר", "book", status=2, at=100)),
        who={"name": "David", "email": "d@example.com"},
    )
    assert signed["exports"] == {"words": False, "anki": False, "phrases": False}


def test_the_anki_deck_is_what_the_filter_is_showing() -> None:
    """So what you exported is what you were looking at — the same rule as the CSV, and
    the reason both buttons sit in the row with the filter rather than under the table."""
    drawn = draw(
        vocabulary(
            word("ספר", "book", status=2, at=100),
            word("דרך", "road", status=9, at=200),
        ),
        do=[{"type": "export", "which": "anki"}],
    )
    _, notes = anki(drawn)
    assert [note[0] for note in notes] == ["ספר"], "known words are not on screen"


def test_the_fold_offers_one_door_into_a_conversation() -> None:
    """A list of words is a list of words. The thing a reader stuck on six of them wants
    is to meet them in a sentence, and the conversation is where this product does that.
    One control for the sitting, at the foot — not a third button on twenty rows."""
    drawn = draw(
        vocabulary(word("ספר", "book", status=2, at=100), word("דרך", "road", status=1, at=200)),
        do=[{"type": "talk"}],
    )
    assert drawn["talk"]["foot"] is False, "the door is there when there are words"
    assert "ספר" in drawn["talk"]["said"] and "דרך" in drawn["talk"]["said"]
    assert drawn["talk"]["went"].startswith("/chat")


def test_the_line_is_left_for_the_chat_rather_than_put_in_the_address() -> None:
    """A reader's own vocabulary in a query string is their vocabulary in a server log,
    in their history, and in whatever sits between them and the site."""
    drawn = draw(
        vocabulary(word("ספר", "book", status=2, at=100)),
        do=[{"type": "talk"}],
    )
    assert "ספר" not in drawn["talk"]["went"]
    assert "ספר" in drawn["talk"]["said"]


def test_the_door_names_a_sitting_s_worth_of_words_and_not_the_whole_fold() -> None:
    """The line is a sentence a person reads before pressing Send, and twenty Hebrew
    words is not a sentence. The ones nearest the top, which are the oldest marks."""
    many = [word(f"מילה{n}", f"word {n}", status=1, at=n) for n in range(15)]
    drawn = draw(vocabulary(*many), do=[{"type": "talk"}])
    said = drawn["talk"]["said"]
    assert sum(1 for n in range(15) if f"מילה{n}" in said) == 6
    assert "מילה0" in said and "מילה14" not in said, "oldest first, as the fold is ordered"


def test_the_door_on_the_phrases_tab_carries_the_phrases() -> None:
    """The open tab is what the line is about: a kept phrase by its text and a corrected
    line by what it should have been, never by the mistake."""
    stored = with_phrase(vocabulary(word("ספר", "book", status=2, at=100)), "לב טוב", at=60)
    drawn = draw(stored, slips=[SLIP], do=[{"type": "tab", "which": "phrases"}, {"type": "talk"}])
    said = drawn["talk"]["said"]
    assert said.startswith("Use these phrases in new sentences: ")
    assert SLIP["recast"] in said and "לב טוב" in said
    assert SLIP["wrote"] not in said and "ספר" not in said
    assert drawn["talk"]["went"].startswith("/chat")
    assert not [told for told in drawn["told"] if told["url"].startswith("/chat")], "nothing sent"


def test_pressing_the_door_sends_nothing() -> None:
    """A turn spends, and what spends is the reader's own press. The page writes a line
    and opens the conversation with it in the box; Send is theirs."""
    drawn = draw(
        vocabulary(word("ספר", "book", status=2, at=100)),
        do=[{"type": "talk"}],
    )
    assert not [url for url in drawn["asked"] if url.startswith("/chat/say")]


# --- a row's card (2026-09-18) ---------------------------------------------------------


def test_a_word_in_the_fold_opens_its_card() -> None:
    """ "When I click on a word or phrase on any list, I want to be able to open up its
    card, and interact with it." The word, its dictionary form, its meaning and the
    level scale, as the reader's card has them."""
    drawn = draw(
        vocabulary(word("הלך", "walked", status=2, surface="הולך", at=100)),
        do=[{"type": "open", "in": "work-rows", "term": "הולך"}],
    )
    card = drawn["card"]
    assert card is not None and card["role"] == "dialog"
    assert card["head"] == "הולך"
    assert "הלך" in card["form"], "the dictionary form, where it differs"
    assert card["meaning"].startswith("walked")
    assert card["levels"]


def test_a_level_said_on_the_card_is_written_and_the_card_goes() -> None:
    drawn = draw(
        vocabulary(word("ספר", "book", status=2, at=100)),
        do=[{"type": "open", "in": "work-rows", "term": "ספר"}, {"type": "level", "value": 9}],
    )
    assert drawn["ledger"]["ספר"]["status"] == 9
    assert drawn["card"] is None, "said, and put away, as in the reader"
    assert drawn["workOn"]["rows"] == [], "and the fold is drawn again from the store"


def test_a_row_of_the_word_table_opens_the_same_card() -> None:
    drawn = draw(
        vocabulary(word("ספר", "book", status=2, at=100)),
        do=[{"type": "open", "in": "word-rows", "term": "ספר"}],
    )
    assert drawn["card"]["head"] == "ספר" and drawn["card"]["levels"]


def test_a_kept_phrase_opens_its_card_with_the_text_it_came_from() -> None:
    stored = with_phrase(
        vocabulary(word("ספר", "book", status=9, at=100)), "לב טוב", meaning="a good heart"
    )
    for where in ("work-phrase-rows", "phrase-list"):
        drawn = draw(stored, do=[{"type": "open", "in": where, "term": "לב טוב"}])
        card = drawn["card"]
        assert card["head"] == "לב טוב", where
        assert card["meaning"].startswith("a good heart")
        assert card["form"] == "Kept from אהבת ציון"
        assert card["levels"]


def test_a_corrected_line_opens_to_what_it_should_have_been() -> None:
    """The recast first, since that is the thing to learn; what they wrote under it. No
    scale: a sentence has no level."""
    for where in ("work-phrase-rows", "rewrote-rows"):
        drawn = draw(
            vocabulary(word("ספר", "book", status=9, at=100)),
            slips=[SLIP],
            do=[{"type": "open", "in": where, "term": SLIP["recast"]}],
        )
        card = drawn["card"]
        assert card["head"] == SLIP["recast"], where
        assert SLIP["wrote"] in card["form"]
        assert not card["levels"]


def test_a_word_with_no_meaning_says_so_and_offers_the_field() -> None:
    drawn = draw(
        vocabulary(word("ספר", "", status=2, at=100)),
        do=[{"type": "open", "in": "work-rows", "term": "ספר"}],
    )
    assert drawn["card"]["meaning"] == "No meaning yet. Write your own below."


def test_the_same_phrase_kept_twice_is_named_once_in_the_line() -> None:
    stored = vocabulary(word("ספר", "book", status=9, at=100))
    stored["targum:docs"] = json.dumps({"h1": {"language": "he", "title": "אהבת ציון"}})
    stored["targum:picked:h1"] = json.dumps(
        {
            "s1": [{"id": "p1", "text": "ולקחו אותו לחקירה", "status": 1, "at": 1}],
            "s2": [{"id": "p2", "text": "ולקחו אותו לחקירה", "status": 1, "at": 2}],
        }
    )
    drawn = draw(stored, do=[{"type": "talk"}])
    assert drawn["talk"]["said"].count("ולקחו אותו לחקירה") == 1
