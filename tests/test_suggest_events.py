"""What became of a suggestion, and how well targum estimates difficulty (targum-internal
#612; privacy notice clauses 3.6 and 3.7 as amended 2026-11-01).

A `suggest` row says shown, opened, finished or aside, where the text came from, a find's
pool id and the share of its running words the chooser estimated the reader to know. A
finished `section` row adds the estimate for that section and the words looked up in it,
which the back office pools into lookups per hundred words against the predicted unknown
rate: across readers, naming none, from at least ten, over redistributable library texts.
"""

from __future__ import annotations

import re
import sqlite3
from html import unescape
from pathlib import Path
from typing import Any

from targum.accounts import Store
from targum.backoffice import FIT_FLOOR, fit_counts
from targum.render.builder import LEGAL_CHANGED, back_office_page, legal_page

DAY = "2026-11-01"


def _person(store: Store, n: int = 1) -> Any:
    signed = store.finish_sign_in(store.start_sign_in(f"reader{n}@example.com"))
    assert signed is not None
    return signed[0]


def _said(markup: str) -> str:
    markup = re.sub(r"<(style|script)[^>]*>.*?</\1>", " ", markup, flags=re.S)
    return " ".join(unescape(re.sub(r"<[^>]+>", " ", markup)).split())


def test_a_suggestion_keeps_what_became_of_it_and_nothing_else(tmp_path: Path) -> None:
    store = Store(tmp_path / "words.db")
    person = _person(store)
    kept = store.add_events(
        person,
        [
            # A shelf text drawn on the card, at 95% of its running words.
            {"kind": "suggest", "day": DAY, "act": "shown", "origin": "shelf",
             "document": "ruth-he", "language": "he", "coverage": 0.95,
             "pool": 7, "segment": "s1", "amount": 9, "word": "x"},
            # A find opened, with its pool id.
            {"kind": "suggest", "day": DAY, "act": "opened", "origin": "find",
             "document": "find-12", "language": "he", "pool": 12, "coverage": 0.931},
            # Set aside, with no estimate: unknown, never a nought.
            {"kind": "suggest", "day": DAY, "act": "aside", "origin": "shelf",
             "document": "scene-01"},
            {"kind": "suggest", "day": DAY, "act": "finished", "origin": "shelf",
             "document": "ruth-he", "coverage": 1.5},
            # Dropped: an act, an origin or a text it does not know.
            {"kind": "suggest", "day": DAY, "act": "liked", "origin": "shelf", "document": "a"},
            {"kind": "suggest", "day": DAY, "act": "shown", "origin": "web", "document": "a"},
            {"kind": "suggest", "day": DAY, "act": "shown", "origin": "shelf"},
        ],
    )  # fmt: skip
    assert kept == 4
    rows = store.db.execute(
        "SELECT act, origin, pool, coverage, document, segment, amount, word FROM event ORDER BY id"
    ).fetchall()
    assert [tuple(row) for row in rows] == [
        ("shown", "shelf", None, 0.95, "ruth-he", "", 0.0, ""),
        ("opened", "find", 12, 0.931, "find-12", "", 0.0, ""),
        ("aside", "shelf", None, None, "scene-01", "", 0.0, ""),
        ("finished", "shelf", None, None, "ruth-he", "", 0.0, ""),
    ]


def test_a_finished_section_keeps_its_estimate_and_its_look_ups(tmp_path: Path) -> None:
    store = Store(tmp_path / "words.db")
    person = _person(store)
    store.add_events(
        person,
        [
            {"kind": "section", "day": DAY, "amount": 200, "segment": "1",
             "coverage": 0.92, "looked": 6},
            {"kind": "section", "day": DAY, "amount": 100, "segment": "2"},
            {"kind": "page", "day": DAY, "amount": 50, "coverage": 0.5, "looked": 3},
            {"kind": "lookup", "day": DAY, "word": "w", "act": "shown", "origin": "shelf"},
        ],
    )  # fmt: skip
    rows = store.db.execute("SELECT kind, coverage, looked, act, origin FROM event ORDER BY id")
    assert [tuple(row) for row in rows] == [
        ("section", 0.92, 6, "", ""),
        ("section", None, None, "", ""),
        ("page", None, None, "", ""),
        ("lookup", None, None, "", ""),
    ]


def test_the_switch_and_erase_reach_suggestions(tmp_path: Path) -> None:
    """The reader's record-of-use switch stops them and Erase takes them, as every other
    row of the record."""
    store = Store(tmp_path / "words.db")
    person = _person(store)
    shown = {"kind": "suggest", "day": DAY, "act": "shown", "origin": "shelf", "document": "a"}
    assert store.add_events(person, [shown]) == 1
    store.set_collects(person, False)
    assert store.add_events(person, [shown]) == 0
    store.set_collects(person, True)
    assert store.forget_events(person) == 1
    assert store.db.execute("SELECT COUNT(*) FROM event").fetchone()[0] == 0


def test_a_store_from_before_gains_the_columns_empty(tmp_path: Path) -> None:
    old = tmp_path / "old.db"
    Store(old)
    with sqlite3.connect(old) as db:
        for column in ("act", "origin", "pool", "coverage", "looked"):
            db.execute(f"ALTER TABLE event DROP COLUMN {column}")
        db.execute(
            "INSERT INTO event (person, kind, day, amount) VALUES (1, 'section', ?, 3)", (DAY,)
        )
    reopened = Store(old)
    row = reopened.db.execute("SELECT act, origin, pool, coverage, looked FROM event").fetchone()
    assert tuple(row) == ("", "", None, None, None)


def _finish(
    store: Store, person: Any, document: str, coverage: float, words: int, looked: int
) -> None:
    store.add_events(
        person,
        [
            {"kind": "section", "day": DAY, "amount": words, "segment": "1",
             "document": document, "coverage": coverage, "looked": looked},
        ],
    )  # fmt: skip


def test_the_pooled_count_needs_ten_readers_and_a_shareable_library_text(tmp_path: Path) -> None:
    store = Store(tmp_path / "words.db")
    readers = [_person(store, n) for n in range(FIT_FLOOR)]
    for reader in readers:
        # In the aim, 95%: five words in a hundred predicted new, three looked up.
        _finish(store, reader, "shared-hash", 0.95, 100, 3)
        # An upload, or a text whose licence does not let it go: never counted.
        _finish(store, reader, "upload-hash", 0.95, 1000, 900)
    # Under the floor, from fewer than ten readers: its tally alone, no figures.
    for reader in readers[:3]:
        _finish(store, reader, "shared-hash", 0.70, 100, 40)
    # A section with no estimate is not in any band.
    store.add_events(
        readers[0], [{"kind": "section", "day": DAY, "amount": 500, "document": "shared-hash"}]
    )

    found = fit_counts(store.db, {"shared-hash"})
    by_band = {row.band: row for row in found}
    assert set(by_band) == {"under 80%", "94–97%"}
    aim = by_band["94–97%"]
    assert aim.shown and aim.readers == FIT_FLOOR and aim.words == 1000 and aim.looked == 30
    assert round(aim.looked_per_100, 2) == 3.0
    assert round(aim.unknown_per_100, 2) == 5.0
    under = by_band["under 80%"]
    assert not under.shown and under.readers == 3 and under.words == 0 and under.looked == 0

    # Staff are not readers: one fewer, and the band falls under the floor.
    staff = fit_counts(store.db, {"shared-hash"}, operators=["reader0@example.com"])
    assert not {row.band: row for row in staff}["94–97%"].shown
    # Nothing shareable, nothing counted.
    assert fit_counts(store.db, set()) == []

    page = _said(back_office_page(_empty_survey(), 30, fit=found))
    assert "Difficulty estimate" in page
    assert "94–97% 10 1000 3.0 5.0" in page
    assert "under 80% Fewer than ten readers" in page


def _empty_survey() -> Any:
    from targum.backoffice import Survey

    return Survey()


def test_the_notice_says_both_new_sentences_word_for_word() -> None:
    """David approved the wording on 2026-11-01; the date the page gives moved with it."""
    assert LEGAL_CHANGED == "1 November 2026"
    page = _said(legal_page("privacy"))
    assert (
        "the controls of the reader that were pressed. Also, for each text, recording or"
        " page the Service suggests to the Data Subject, whether the suggestion was shown,"
        " opened, finished or set aside for another, and the share of its words the Service"
        " estimated the Data Subject to know at the time, and, for each section the Data"
        " Subject marks as finished, the share of its words the Service estimated the Data"
        " Subject to know when it was opened, and how many of its words were looked up." in page
    )
    assert (
        "in a given week and of choosing the texts the Service suggests to the Data Subject."
        in page
    )
    assert (
        "Also counts, across all Data Subjects and bearing no identifier of any of them, of"
        " the words looked up and the words read in sections marked as finished, grouped by"
        " the share of the words of each such section the Service had estimated the Data"
        " Subject to know, confined to documents the licence of which permits their"
        " redistribution and made in no respect of material uploaded by a Data Subject; no"
        " such count is used unless it is drawn from at least ten Data Subjects. Processed"
        " for the purpose of measuring how well the Service estimates the difficulty of a"
        " text for a reader. Legal basis: Article 6(1)(f)." in page
    )
    assert FIT_FLOOR == 10, "the notice says at least ten"


def test_the_notice_names_the_words_check_word_for_word() -> None:
    """David approved the wording on 2026-11-01 (targum-internal#613): clause 3.2 names the
    words a reader marks as known on the arrival's words check, in his words."""
    assert LEGAL_CHANGED == "1 November 2026"
    page = _said(legal_page("privacy"))
    assert (
        "the date on which each word was marked as known, and the words the Data Subject"
        " marked as known on the check offered on arrival, with the date, which are used"
        " only to estimate which texts suit them, and the dictionary forms of the words in"
        " sections the Data Subject has marked as finished" in page
    )
