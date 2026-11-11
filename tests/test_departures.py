"""A departed reader's home and corpus rows go even when a step fails (targum-internal#679).

Clause 3.14: an account whose grace period is up loses its rows, its home and its texts'
rows in `corpus.db`. Each home is written down before its account goes, so a lock on the
ledger, a removal that leaves part of the folder, or a crash in between is finished by
the next purge instead of lost, and a person id given again is never handed what was
left of the last one's.
"""

from __future__ import annotations

import contextlib
import json
import os
import shutil
import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

from targum import ledger
from targum import serve as serve_module
from targum.accounts import Person, Store
from targum.serve import Library


@pytest.fixture
def world(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> tuple[Store, Library, ledger.Ledger]:
    monkeypatch.setenv(ledger.ENV, str(tmp_path / "corpus.db"))
    # A lock held longer than a purge waits, without waiting seconds for it.
    monkeypatch.setattr(serve_module, "FORGET_TIMEOUT", 0.05)
    store = Store(tmp_path / "targum.db")
    library = Library(tmp_path / "out", store=store)
    return store, library, ledger.Ledger(tmp_path / "corpus.db")


def _person(store: Store, email: str) -> Person:
    person, _ = store.finish_sign_in(store.start_sign_in(email))  # type: ignore[misc]
    return person


def _text(book: ledger.Ledger, home: Path, name: str, document_hash: str) -> None:
    folder = home / name
    folder.mkdir(parents=True)
    document = {"source": "https://x.example/a", "blocks": [], "content_hash": document_hash}
    (folder / "document.json").write_text(json.dumps(document), encoding="utf-8")
    book.record_text(ledger.Text(document_hash, "https://x.example/a", "", frozenset({home.name})))


def _leave(store: Store, person: Person) -> None:
    with store.write() as db:
        db.execute("UPDATE person SET leaving = 1 WHERE id = ?", (person.id,))


def _notes(store: Store) -> list[dict[str, object]]:
    folder = Path(store.path).parent / f"{Path(store.path).name}.departing"
    if not folder.is_dir():
        return []
    return [json.loads(one.read_text(encoding="utf-8")) for one in sorted(folder.iterdir())]


@contextlib.contextmanager
def _locked(book: ledger.Ledger) -> Iterator[None]:
    holder = sqlite3.connect(book.file, isolation_level=None)
    holder.execute("BEGIN IMMEDIATE")
    try:
        yield
    finally:
        holder.execute("ROLLBACK")
        holder.close()


def test_a_purge_the_ledger_lock_stopped_is_finished_by_the_next(
    world: tuple[Store, Library, ledger.Ledger],
) -> None:
    """The card's done-when: the lock held through the purge, the rows are there after
    it, gone after the next, and the note goes only then."""
    store, library, book = world
    person = _person(store, "leaving@example.com")
    home = library.home(person)
    _text(book, home, "my-upload", "a" * 64)
    _leave(store, person)

    with _locked(book):
        assert library.purge_departed() == [person.id]

    assert not home.exists(), "the home goes on time, whatever the ledger says"
    assert book.text("a" * 64) is not None, "the lock held: the rows are there"
    assert [(one["home"], one["hashes"], one["left"]) for one in _notes(store)] == [
        (home.name, ["a" * 64], False)
    ]

    assert library.purge_departed() == [], "nobody new is due"
    assert book.text("a" * 64) is None
    with sqlite3.connect(book.file) as db:
        assert db.execute("SELECT COUNT(*) FROM text_homes").fetchone()[0] == 0
    assert _notes(store) == [], "the note goes once the ledger step holds"


def test_a_note_that_cannot_be_removed_stops_no_deletion_and_no_start(
    world: tuple[Store, Library, ledger.Ledger],
) -> None:
    """qa-claude on #1174: a folder of notes the server cannot change (a root run's)
    raised out of the purge before anyone was deleted, and out of start-up."""
    store, library, book = world
    first = _person(store, "first@example.com")
    _text(book, library.home(first), "theirs", "a" * 64)
    _leave(store, first)
    with _locked(book):
        library.purge_departed()
    second = _person(store, "second@example.com")
    _text(book, library.home(second), "theirs", "b" * 64)
    _leave(store, second)
    folder = Path(store.path).parent / f"{Path(store.path).name}.departing"
    folder.chmod(0o555)
    try:
        assert library.purge_departed() == [second.id]
        assert not library.home(second).exists()
        assert book.text("b" * 64) is None, "with no note, the ledger step runs at once"
        Library(library.out, store=store)
    finally:
        folder.chmod(0o755)


def test_a_home_that_will_not_go_keeps_its_note_and_is_never_handed_on(
    monkeypatch: pytest.MonkeyPatch, world: tuple[Store, Library, ledger.Ledger]
) -> None:
    """A removal that leaves the folder standing keeps the note; the next account given
    the same id gets an empty home, not the departed's texts (clause 3.14)."""
    store, library, book = world
    person = _person(store, "leaving@example.com")
    home = library.home(person)
    _text(book, home, "my-upload", "a" * 64)
    _leave(store, person)

    def refused(*_args: object, **_kwargs: object) -> None:
        raise PermissionError("no")

    with monkeypatch.context() as stuck:
        stuck.setattr(os, "rename", refused)
        stuck.setattr(shutil, "rmtree", lambda *_a, **_k: None)
        assert library.purge_departed() == [person.id]
        assert (home / "my-upload").is_dir()
        assert book.text("a" * 64) is None, "the rows go even while the folder stands"
        assert [one["left"] for one in _notes(store)] == [True]
        library.purge_departed()
        assert [one["left"] for one in _notes(store)] == [True], "kept while it stands"

    newcomer = _person(store, "new@example.com")
    assert newcomer.id == person.id, "sqlite gives the highest id again"
    assert not (library.home(newcomer) / "my-upload").exists()
    library.purge_departed()
    assert _notes(store) == []
    assert store.db.execute("SELECT id FROM person").fetchall()[0]["id"] == newcomer.id


def test_a_crash_after_the_note_is_finished_at_start_up(
    monkeypatch: pytest.MonkeyPatch, world: tuple[Store, Library, ledger.Ledger]
) -> None:
    store, library, book = world
    person = _person(store, "leaving@example.com")
    home = library.home(person)
    _text(book, home, "my-upload", "a" * 64)
    _leave(store, person)
    with monkeypatch.context() as crash:
        crash.setattr(Library, "_remove_home", lambda *_a: None)
        crash.setattr(Library, "_finish_departures", lambda *_a: None)
        assert library.purge_departed() == [person.id]
    assert home.is_dir() and book.text("a" * 64) is not None

    Library(library.out, store=store)

    assert not home.exists()
    assert book.text("a" * 64) is None
    assert _notes(store) == []


def test_a_note_for_an_account_still_here_touches_nothing(
    monkeypatch: pytest.MonkeyPatch, world: tuple[Store, Library, ledger.Ledger]
) -> None:
    """Written for a purge that then never happened: the account and its home stay."""
    store, library, book = world
    person = _person(store, "staying@example.com")
    home = library.home(person)
    _text(book, home, "my-upload", "a" * 64)
    _leave(store, person)
    monkeypatch.setattr(Store, "purge", lambda *_a, **_k: [])
    assert library.purge_departed() == []
    assert (home / "my-upload").is_dir()
    assert book.text("a" * 64) is not None
    assert _notes(store) == []


def test_an_id_given_twice_keeps_both_notes_and_the_newcomer_s_texts(
    world: tuple[Store, Library, ledger.Ledger],
) -> None:
    """qa-claude on #1174: a reused id wrote its note over the one still owed."""
    store, library, book = world
    first = _person(store, "first@example.com")
    _text(book, library.home(first), "theirs", "a" * 64)
    _leave(store, first)
    with _locked(book):
        library.purge_departed()

    second = _person(store, "second@example.com")
    assert second.id == first.id
    _text(book, library.home(second), "mine", "b" * 64)
    library.purge_departed()
    assert book.text("a" * 64) is None, "the first account's text went"
    held = book.text("b" * 64)
    assert held is not None and held.homes == {f"p{second.id}"}, "the newcomer's stayed"

    _text(book, library.home(second), "more", "c" * 64)
    _leave(store, second)
    with _locked(book):
        assert library.purge_departed() == [second.id]
    third = _person(store, "third@example.com")
    _text(book, library.home(third), "theirs", "d" * 64)
    _leave(store, third)
    with _locked(book):
        assert library.purge_departed() == [third.id]
    assert len(_notes(store)) == 2, "one note each, neither written over"

    library.purge_departed()
    for hash_ in ("b", "c", "d"):
        assert book.text(hash_ * 64) is None
    assert _notes(store) == []


def test_a_held_lock_costs_a_sweep_one_wait(
    monkeypatch: pytest.MonkeyPatch, world: tuple[Store, Library, ledger.Ledger]
) -> None:
    """Start-up waits on the purge, so three departures under a lock wait once."""
    store, library, book = world
    people = [_person(store, f"p{n}@example.com") for n in range(3)]
    for n, person in enumerate(people):
        _text(book, library.home(person), "theirs", str(n) * 64)
        _leave(store, person)
    tries: list[str] = []
    real = ledger.disown

    def counted(home: str, *args: object, **kwargs: object) -> int:
        tries.append(home)
        return real(home, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(ledger, "disown", counted)
    with _locked(book):
        assert sorted(library.purge_departed()) == sorted(one.id for one in people)
    assert len(tries) == 1
    assert len(_notes(store)) == 3


def test_a_note_that_cannot_be_written_leaves_no_draft_and_forgets_at_once(
    monkeypatch: pytest.MonkeyPatch, world: tuple[Store, Library, ledger.Ledger]
) -> None:
    store, library, book = world
    person = _person(store, "leaving@example.com")
    home = library.home(person)
    _text(book, home, "my-upload", "a" * 64)
    _leave(store, person)

    def refused(*_args: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", refused)
    assert library.purge_departed() == [person.id]
    folder = Path(store.path).parent / f"{Path(store.path).name}.departing"
    assert list(folder.iterdir()) == [], "no draft left behind"
    assert not home.exists()
    assert book.text("a" * 64) is None


def test_a_build_that_lands_after_the_purge_is_cleared_too(
    world: tuple[Store, Library, ledger.Ledger],
) -> None:
    """A folder of the departed's name with no account behind it is theirs, not somebody
    new's: the store says who has the id, never the disk (qa-claude on #1174)."""
    store, library, book = world
    person = _person(store, "leaving@example.com")
    home = library.home(person)
    _text(book, home, "my-upload", "a" * 64)
    _leave(store, person)
    with _locked(book):
        assert library.purge_departed() == [person.id]
    (home / "late-build").mkdir(parents=True)

    library.purge_departed()

    assert not home.exists()
    assert book.text("a" * 64) is None
    assert _notes(store) == []
