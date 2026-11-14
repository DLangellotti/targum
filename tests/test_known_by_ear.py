"""Known by ear (targum-internal#536): the account's half.

design.md §12, "A word can be known by ear, and only the reader says so" (2026-11-14). One
flag beside the stage, `word.ear`, and its date, `word.ear_at`, set by the account the
way `known_at` is. Only the reader's press writes it; a word known by ear and never
marked when reading has no stage and is on no list; every reading figure stays the
reading marks. The card's half is `test_vocab_js.py`; the deck's is `test_anki.py`.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import pytest
from test_chat_tools import context, world  # noqa: F401 - the fixture is used by name

from targum import accounts
from targum.accounts import Store
from targum.chat import tools

KNOWN = 9


def _store(tmp_path: Path) -> tuple[Store, Any]:
    store = Store(tmp_path / "db")
    person, _ = store.finish_sign_in(store.start_sign_in("r@example.com"))  # type: ignore[misc]
    return store, person


def _word(lemma: str, status: int | None, seen: int, **more: Any) -> dict[str, Any]:
    return {"language": "he", "lemma": lemma, "status": status, "at": seen, "seen": seen, **more}


def _row(store: Store, person: Any, lemma: str) -> sqlite3.Row:
    row = store.db.execute(
        "SELECT * FROM word WHERE person = ? AND lemma = ?", (person.id, lemma)
    ).fetchone()
    assert row is not None
    return row


def test_the_schema_is_past_the_ear_columns() -> None:
    assert accounts.SCHEMA_VERSION >= 68
    assert "ear" in accounts.KINDS["words"].fields
    assert "ear_at" in accounts.KINDS["words"].fields
    assert "ear_at" in accounts.NULLABLE and "ear" in accounts.NUMERIC


def test_an_older_database_gains_both_columns_and_nothing_is_filled_in(tmp_path: Path) -> None:
    path = tmp_path / "old.db"
    Store(path)
    raw = sqlite3.connect(path)
    raw.execute("DROP TABLE word")
    raw.execute(
        "CREATE TABLE word (person INTEGER NOT NULL, language TEXT NOT NULL, lemma TEXT NOT"
        " NULL, surface TEXT NOT NULL DEFAULT '', status INTEGER, meaning TEXT NOT NULL"
        " DEFAULT '', note TEXT NOT NULL DEFAULT '', band TEXT NOT NULL DEFAULT '', learned"
        " INTEGER NOT NULL DEFAULT 0, source TEXT NOT NULL DEFAULT '', at INTEGER NOT NULL"
        " DEFAULT 0, seen INTEGER NOT NULL DEFAULT 0, gone INTEGER NOT NULL DEFAULT 0,"
        " revision INTEGER NOT NULL DEFAULT 0, known_at INTEGER, PRIMARY KEY (person,"
        " language, lemma))"
    )
    raw.execute("PRAGMA user_version = 67")
    raw.execute(
        "INSERT INTO word (person, language, lemma, status, seen) VALUES (1, 'he', 'x', 9, 5)"
    )
    raw.commit()
    raw.close()
    store = Store(path)
    row = store.db.execute("SELECT ear, ear_at FROM word WHERE lemma = 'x'").fetchone()
    assert row["ear"] == 0 and row["ear_at"] is None
    assert store.db.execute("PRAGMA user_version").fetchone()[0] == accounts.SCHEMA_VERSION
    # Opening it again is opening it once.
    Store(path)


def test_ear_at_is_the_push_that_marked_it_and_goes_when_it_comes_off(tmp_path: Path) -> None:
    store, person = _store(tmp_path)
    began = store.began()
    store.push(person, {"words": [_word("ספר", 2, began + 10, ear=1)]})
    row = _row(store, person, "ספר")
    assert row["ear"] == 1 and row["ear_at"] == began + 10
    # A later edit keeps the day it became so, whatever the page sent.
    store.push(person, {"words": [_word("ספר", KNOWN, began + 20, ear=1, ear_at=began + 999)]})
    row = _row(store, person, "ספר")
    assert row["ear_at"] == began + 10
    assert row["status"] == KNOWN, "the two marks are independent"
    # Off, and it has none.
    store.push(person, {"words": [_word("ספר", KNOWN, began + 30, ear=0)]})
    row = _row(store, person, "ספר")
    assert row["ear"] == 0 and row["ear_at"] is None
    assert row["status"] == KNOWN and row["known_at"] == began + 20


def test_ear_at_is_never_guessed_for_a_mark_from_before_the_record(tmp_path: Path) -> None:
    store, person = _store(tmp_path)
    store.push(person, {"words": [_word("ים", 2, store.began() - 86_400_000, ear=1)]})
    row = _row(store, person, "ים")
    assert row["ear"] == 1 and row["ear_at"] is None


def test_a_push_from_an_older_page_keeps_the_ear_mark(tmp_path: Path) -> None:
    """An offline saved reader can carry JS from before the mark: its push has no `ear`,
    and what the account holds stays, date and all."""
    store, person = _store(tmp_path)
    began = store.began()
    store.push(person, {"words": [_word("ספר", 2, began + 10, ear=1)]})
    store.push(person, {"words": [_word("ספר", 3, began + 20)]})
    row = _row(store, person, "ספר")
    assert row["status"] == 3
    assert row["ear"] == 1 and row["ear_at"] == began + 10


def test_pull_carries_the_ear_mark_to_the_next_device(tmp_path: Path) -> None:
    store, person = _store(tmp_path)
    began = store.began()
    store.push(person, {"words": [_word("ספר", None, began + 10, ear=1)]})
    pulled = {row["lemma"]: row for row in store.pull(person)["words"]}
    assert pulled["ספר"]["ear"] == 1
    assert pulled["ספר"]["status"] is None


def test_a_word_known_by_ear_alone_is_on_no_list_and_in_no_reading_count(
    tmp_path: Path,
) -> None:
    """D2: status NULL. Not on the list, not in the free cap, not known anywhere, not in
    what the estimate, the ladder or search weigh; and never "saved" on a day."""
    store, person = _store(tmp_path)
    began = store.began()
    store.push(
        person,
        {
            "words": [
                _word("בית", KNOWN, began + 1),
                _word("מלך", 2, began + 2, ear=1),
                {**_word("שמע", None, began + 3, ear=1), "at": 0},
            ]
        },
    )
    assert store.listed_words(person.id) == 1
    assert store.known_count(person, "he") == 1
    assert [lemma for lemma, _ in store.known_dated(person.id, "he")] == ["בית"]
    assert store.known_forms(person.id, "he") >= {"בית"}
    assert "שמע" not in store.known_forms(person.id, "he")
    assert "שמע" not in store.marked(person, "he")
    words, _, _ = store.knowledge(person.id, "he")
    assert "שמע" not in {lemma for lemma, _, _ in words}
    assert "שמע" not in {row[0] for row in store.words_with_bands(person.id, "he")}
    assert "שמע" not in {row[0] for row in store.meanings(person, "he")}
    # The word being learned is still pushed on a capped list; one by ear never counts.
    assert not store._over_cap(store.db, person, _word("שמע", None, began + 4, ear=1), 1)
    # And the two counts that do see it.
    assert store.ear_count(person, "he") == 2
    assert store.ear_words(person.id, "he") == {"מלך": 2, "שמע": None}
    saved = {row["lemma"]: row for row in store.saved_words(person, "he")}
    assert set(saved) == {"בית", "מלך", "שמע"}
    assert saved["שמע"]["status"] is None and saved["שמע"]["ear"] == 1


def test_an_ignored_word_or_a_name_is_not_counted_by_ear(tmp_path: Path) -> None:
    store, person = _store(tmp_path)
    began = store.began()
    store.push(
        person,
        {
            "words": [
                _word("אבג", 0, began + 1, ear=1),
                _word("דוד", KNOWN, began + 2, ear=1, band="name"),
            ]
        },
    )
    assert store.ear_count(person, "he") == 0
    assert "אבג" not in {row["lemma"] for row in store.saved_words(person, "he")}


def test_everything_carries_the_ear_mark_and_forget_takes_it(tmp_path: Path) -> None:
    store, person = _store(tmp_path)
    began = store.began()
    store.push(person, {"words": [_word("ספר", None, began + 5, ear=1)]})
    taken = store.everything(person)
    words = {row["lemma"]: row for row in taken["words"]}
    assert words["ספר"]["ear"] == 1 and words["ספר"]["ear_at"] == began + 5
    store.forget(person)
    store.purge(days=-1)
    assert (
        store.db.execute("SELECT COUNT(*) FROM word WHERE person = ?", (person.id,)).fetchone()[0]
        == 0
    )


# --- never inferred -----------------------------------------------------------------


def test_no_tool_writes_the_ear_mark() -> None:
    """Only the reader's press writes it (§12, 2026-11-14): no chat or connector tool takes
    an `ear` field, and the two that say it are read only and say the reader marks it. A
    scope is still the one press that lasts."""
    for tool in tools.REGISTRY:
        fields = set((tool.schema.get("properties") or {}).keys())
        assert not {"ear", "by_ear", "ear_at"} & fields, tool.name
        if "by ear" in tool.description.lower():
            assert tool.name in {"my_vocabulary", "my_progress"}, tool.name
            assert not tool.spends
            assert "Read only." in tool.description


def test_the_connector_says_by_ear_beside_the_reading_counts(world) -> None:  # noqa: F811
    library, store, person, home = world
    began = store.began()
    store.push(
        person,
        {
            "words": [
                _word("מלך", 2, began + 10, ear=1),
                {**_word("שמע", None, began + 11, ear=1), "at": 0},
            ]
        },
    )
    ctx = context(library, store, person, home)
    said = tools.my_vocabulary(ctx, {})
    assert said["known"] == 2 and said["learning"] == 1, "the reading counts, unchanged"
    assert said["by_ear"] == 2
    recent = {row["lemma"]: row for row in said["recent"]}
    assert recent["מלך"]["by_ear"] is True and recent["שלום"]["by_ear"] is False
    assert "שמע" not in recent, "a word with no stage is not a word marked when reading"
    assert tools.my_progress(ctx, {})["known_by_ear"] == 2


@pytest.mark.parametrize("name", ["my_vocabulary", "my_progress"])
def test_the_connector_says_the_reader_marks_it(name: str) -> None:
    tool = tools.BY_NAME[name]
    assert "only the reader" in tool.description or "never a model" in tool.description
