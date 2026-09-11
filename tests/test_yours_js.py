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
from test_learn_js import vocabulary, word

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
    assert marked["claim"]["hidden"] and marked["claim"]["said"] == "That is the whole list."
    assert marked["wordsTitle"] == "Your Words (4)", "collected again, not drawn stale"


def test_a_browser_with_nothing_kept_is_told_so() -> None:
    drawn = draw({})
    assert drawn["nothing"] and not drawn["shown"]
