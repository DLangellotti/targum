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
    assert drawn["exports"] == {"words": True, "phrases": True}, "hidden, both of them"


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
    assert drawn["asked"] == ["/words/common?offset=0&limit=50"]
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


def test_still_learning_moves_a_word_out_of_this_sitting_and_stores_nothing() -> None:
    """It does not restamp `at`: that field is when a word was kept, it is what the
    table's Kept column shows, and it is written once and preserved for life — so
    re-stamping it to reorder a queue would quietly age every word in the product to
    today. And nothing is stored, because a stored skip is an interval wearing a
    different coat."""
    drawn = draw(
        vocabulary(
            word("ספר", "book", status=2, at=100),
            word("דרך", "road", status=1, at=200),
        ),
        do=[{"type": "work", "word": "ספר", "key": 1}],
    )
    assert [row["term"] for row in drawn["workOn"]["rows"]] == ["דרך"]
    assert drawn["ledger"]["ספר"]["status"] == 2, "still being learned"
    assert drawn["ledger"]["ספר"]["at"] == 100, "and kept when it was kept"


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
