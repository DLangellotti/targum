"""A departed reader's home and corpus rows go even when a step fails (targum-internal#679).

Clause 3.14: an account whose grace period is up loses its rows, its home and its texts'
rows in `corpus.db`. Each home is written down before its account goes, so a lock on the
ledger, a delete that fails, or a crash in between is finished by the next purge instead
of lost; and a person id is never given twice, so whatever stands under a departed name
is always theirs to delete and never anybody else's to be handed.
"""

from __future__ import annotations

import contextlib
import json
import logging
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

World = tuple[Store, Library, ledger.Ledger]


@pytest.fixture
def world(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> World:
    monkeypatch.setenv(ledger.ENV, str(tmp_path / "corpus.db"))
    # A lock held longer than a purge waits, without waiting seconds for it.
    monkeypatch.setattr(serve_module, "FORGET_TIMEOUT", 0.05)
    store = Store(tmp_path / "targum.db")
    library = Library(tmp_path / "out", store=store)
    return store, library, ledger.Ledger(tmp_path / "corpus.db")


def _person(store: Store, email: str) -> Person:
    person, _ = store.finish_sign_in(store.start_sign_in(email))  # type: ignore[misc]
    return person


def _text(book: ledger.Ledger, home: Path, name: str, document_hash: str, *homes: str) -> None:
    folder = home / name
    folder.mkdir(parents=True)
    document = {"source": "https://x.example/a", "blocks": [], "content_hash": document_hash}
    (folder / "document.json").write_text(json.dumps(document), encoding="utf-8")
    owners = frozenset({home.name, *homes})
    book.record_text(ledger.Text(document_hash, "https://x.example/a", "", owners))


def _leave(store: Store, person: Person) -> None:
    with store.write() as db:
        db.execute("UPDATE person SET leaving = 1 WHERE id = ?", (person.id,))


def _notes_folder(store: Store) -> Path:
    return Path(store.path).parent / f"{Path(store.path).name}.departing"


def _notes(store: Store) -> list[dict[str, object]]:
    folder = _notes_folder(store)
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


@contextlib.contextmanager
def _crash_after_the_note(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """The process dies once the rows are gone, before the home is touched."""
    with monkeypatch.context() as crash:
        crash.setattr(Library, "_remove_home", lambda *_a: None)
        crash.setattr(Library, "_finish_departures", lambda *_a: None)
        yield


@contextlib.contextmanager
def _undeletable(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    with monkeypatch.context() as stuck:
        stuck.setattr(shutil, "rmtree", lambda *_a, **_k: None)
        yield


# -- an id is never given twice ---------------------------------------------------


def test_an_id_is_never_given_twice(tmp_path: Path) -> None:
    """sqlite gives `max(id) + 1`, so the newest account deleted made its id the next
    sign-up's, and with it whatever of theirs was still on disk (qa-claude on #1174)."""
    store = Store(tmp_path / "targum.db")
    first = _person(store, "first@example.com")
    _leave(store, first)
    assert store.purge() == [first.id]
    second = _person(store, "second@example.com")
    assert second.id == first.id + 1
    _leave(store, second)
    store.purge()
    again = Store(tmp_path / "targum.db")
    assert _person(again, "third@example.com").id == second.id + 1, "and across a restart"


# -- the ledger step ----------------------------------------------------------------


def test_a_purge_the_ledger_lock_stopped_is_finished_by_the_next(world: World) -> None:
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
    assert [(one["home"], one["hashes"]) for one in _notes(store)] == [(home.name, ["a" * 64])]

    assert library.purge_departed() == [], "nobody new is due"
    assert book.text("a" * 64) is None
    with sqlite3.connect(book.file) as db:
        assert db.execute("SELECT COUNT(*) FROM text_homes").fetchone()[0] == 0
    assert _notes(store) == [], "the note goes once the ledger step holds"


def test_a_held_lock_costs_a_sweep_one_wait(monkeypatch: pytest.MonkeyPatch, world: World) -> None:
    """Start-up waits on the purge, so three departures under a lock wait once."""
    store, library, book = world
    people = [_person(store, f"p{n}@example.com") for n in range(3)]
    for n, person in enumerate(people):
        _text(book, library.home(person), "theirs", str(n) * 64)
        _leave(store, person)
    tries: list[str] = []
    real = ledger.depart

    def counted(home: str, *args: object, **kwargs: object) -> int:
        tries.append(home)
        return real(home, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(ledger, "depart", counted)
    with _locked(book):
        assert sorted(library.purge_departed()) == sorted(one.id for one in people)
    assert len(tries) == 1
    assert len(_notes(store)) == 3


def test_a_text_another_reader_holds_stays_theirs(
    monkeypatch: pytest.MonkeyPatch, world: World
) -> None:
    """Only what was theirs alone goes; a shared text loses the departed home only, even
    while the departed's folder still stands."""
    store, library, book = world
    live = _person(store, "live@example.com")
    person = _person(store, "leaving@example.com")
    home = library.home(person)
    _text(book, library.home(live), "mine", "d" * 64)
    _text(book, library.home(live), "shared", "5" * 64)
    _text(book, home, "shared", "5" * 64, f"p{live.id}")
    _text(book, home, "alone", "a" * 64)
    _leave(store, person)
    with _undeletable(monkeypatch):
        library.purge_departed()
        library.purge_departed()
        assert home.is_dir()
    assert book.text("a" * 64) is None
    shared = book.text("5" * 64)
    assert shared is not None and shared.homes == {f"p{live.id}"}
    mine = book.text("d" * 64)
    assert mine is not None and mine.homes == {f"p{live.id}"}
    assert (library.home(live) / "mine").is_dir()


def test_a_text_held_by_another_home_only_in_the_ledger_stays(world: World) -> None:
    """Another reader's copy may not be readable on disk; `text_homes` still says it is
    theirs too, and that is enough to keep it."""
    store, library, book = world
    live = _person(store, "live@example.com")
    person = _person(store, "leaving@example.com")
    _text(book, library.home(person), "shared", "5" * 64, f"p{live.id}")
    _leave(store, person)
    library.purge_departed()
    shared = book.text("5" * 64)
    assert shared is not None and shared.homes == {f"p{live.id}"}


def test_a_text_only_the_ledger_knows_is_theirs_goes_too(world: World) -> None:
    """A text whose folder is already gone (trashed, or never finished) is still theirs in
    `text_homes`, and goes with them though no file names it."""
    store, library, book = world
    person = _person(store, "leaving@example.com")
    home = library.home(person)
    _text(book, home, "my-upload", "a" * 64)
    book.record_text(ledger.Text("f" * 64, "https://x.example/f", "", frozenset({home.name})))
    _leave(store, person)
    library.purge_departed()
    assert book.text("f" * 64) is None


def test_a_text_the_note_missed_is_forgotten_by_what_the_ledger_knows(world: World) -> None:
    """qa-claude's fourth read of #1174 (R4-6): a text unreadable when the note was
    written, in a home that would not go. Once it can go, it goes, and so do its rows,
    found through `text_homes` where the note had no hash for it."""
    store, library, book = world
    person = _person(store, "leaving@example.com")
    home = library.home(person)
    _text(book, home, "my-upload", "a" * 64)
    _text(book, home, "secret", "c" * 64)
    (home / "secret").chmod(0o000)
    _leave(store, person)
    try:
        assert library.purge_departed() == [person.id]
        assert home.exists(), "the unreadable folder holds the home up"
        assert [one["hashes"] for one in _notes(store)] == [["a" * 64]]
        newcomer = _person(store, "new@example.com")
        assert newcomer.id != person.id
        (home / "secret").chmod(0o755)  # ops fixes the permissions
        library.purge_departed()
    finally:
        with contextlib.suppress(OSError):
            (home / "secret").chmod(0o755)
    assert not home.exists()
    assert not library.home(newcomer).exists()
    assert book.text("a" * 64) is None
    assert book.text("c" * 64) is None
    assert _notes(store) == []


# -- the folder ----------------------------------------------------------------


def test_a_home_that_will_not_go_keeps_its_note_until_it_does(
    monkeypatch: pytest.MonkeyPatch, world: World
) -> None:
    store, library, book = world
    person = _person(store, "leaving@example.com")
    home = library.home(person)
    _text(book, home, "my-upload", "a" * 64)
    _leave(store, person)
    with _undeletable(monkeypatch):
        assert library.purge_departed() == [person.id]
        library.purge_departed()
        assert (home / "my-upload").is_dir()
        assert book.text("a" * 64) is None, "the rows go even while the folder stands"
        assert len(_notes(store)) == 1, "kept while it stands"
        newcomer = _person(store, "new@example.com")
    assert library.home(newcomer) != home, "never handed to anybody"
    library.purge_departed()
    assert not home.exists()
    assert _notes(store) == []


def test_what_a_delete_leaves_is_tried_again(world: World) -> None:
    """Files a deletion cannot take (a root run's) keep the note, across purges and a
    restart, until they go."""
    store, library, book = world
    person = _person(store, "leaving@example.com")
    home = library.home(person)
    _text(book, home, "my-upload", "a" * 64)
    audio = home / "my-upload" / "audio"
    audio.mkdir()
    (audio / "private.mp3").write_bytes(b"x")
    audio.chmod(0o500)
    _leave(store, person)
    try:
        assert library.purge_departed() == [person.id]
        library.purge_departed()
        Library(library.out, store=store)
        assert (audio / "private.mp3").exists()
        assert len(_notes(store)) == 1
    finally:
        audio.chmod(0o755)
    library.purge_departed()
    assert not home.exists()
    assert _notes(store) == []


def test_a_crash_after_the_note_is_finished_at_start_up(
    monkeypatch: pytest.MonkeyPatch, world: World
) -> None:
    store, library, book = world
    person = _person(store, "leaving@example.com")
    home = library.home(person)
    _text(book, home, "my-upload", "a" * 64)
    _leave(store, person)
    with _crash_after_the_note(monkeypatch):
        assert library.purge_departed() == [person.id]
    assert home.is_dir() and book.text("a" * 64) is not None

    Library(library.out, store=store)

    assert not home.exists()
    assert book.text("a" * 64) is None
    assert _notes(store) == []


def test_a_build_that_lands_after_the_purge_is_cleared_too(world: World) -> None:
    store, library, book = world
    person = _person(store, "leaving@example.com")
    home = library.home(person)
    _text(book, home, "my-upload", "a" * 64)
    _leave(store, person)
    with _locked(book):
        assert library.purge_departed() == [person.id]
    _text(book, home, "late-build", "e" * 64)
    # Its texts row written, its home not (`mirror_text` refused): only the disk knows.
    with sqlite3.connect(book.file) as db:
        db.execute("DELETE FROM text_homes WHERE document_hash = ?", ("e" * 64,))

    library.purge_departed()

    assert not home.exists()
    assert book.text("a" * 64) is None
    assert book.text("e" * 64) is None
    assert _notes(store) == []


# -- the note ----------------------------------------------------------------


def test_a_note_for_an_account_still_here_touches_nothing(
    monkeypatch: pytest.MonkeyPatch, world: World
) -> None:
    """Written for a purge that then never happened (`Store.purge` failed, then Keep):
    the account, its home and its rows stay."""
    store, library, book = world
    person = _person(store, "staying@example.com")
    home = library.home(person)
    _text(book, home, "my-upload", "a" * 64)
    _leave(store, person)

    def locked(*_args: object, **_kwargs: object) -> list[int]:
        raise sqlite3.OperationalError("database is locked")

    with monkeypatch.context() as failing:
        failing.setattr(Store, "purge", locked)
        with pytest.raises(sqlite3.OperationalError):
            library.purge_departed()
    assert len(_notes(store)) == 1
    with store.write() as db:  # Keep pressed
        db.execute("UPDATE person SET leaving = NULL WHERE id = ?", (person.id,))

    library.purge_departed()

    assert (home / "my-upload").is_dir()
    held = book.text("a" * 64)
    assert held is not None and held.homes == {home.name}
    assert _notes(store) == []


def test_a_note_that_cannot_be_removed_stops_no_deletion_and_no_start(world: World) -> None:
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
    folder = _notes_folder(store)
    folder.chmod(0o555)
    try:
        assert library.purge_departed() == [second.id]
        assert not library.home(second).exists()
        assert book.text("b" * 64) is None, "with no note, the ledger step runs at once"
        assert book.text("a" * 64) is None, "the earlier one is finished too"
        Library(library.out, store=store)
    finally:
        folder.chmod(0o755)
    library.purge_departed()
    assert _notes(store) == []


def test_a_note_that_cannot_be_written_leaves_no_draft_and_forgets_at_once(
    monkeypatch: pytest.MonkeyPatch, world: World
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
    assert list(_notes_folder(store).iterdir()) == [], "no draft left behind"
    assert not home.exists()
    assert book.text("a" * 64) is None


def test_two_notes_written_in_one_purge_are_both_finished(world: World) -> None:
    """Notes are named by when they were written and a random tail, never overwritten."""
    store, library, book = world
    people = [_person(store, f"p{n}@example.com") for n in range(2)]
    for n, person in enumerate(people):
        _text(book, library.home(person), "theirs", str(n) * 64)
        _leave(store, person)
    with _locked(book):
        library.purge_departed()
    assert len({one.name for one in _notes_folder(store).iterdir()}) == 2
    library.purge_departed()
    assert _notes(store) == []
    assert book.text("0" * 64) is None and book.text("1" * 64) is None


def test_a_departure_with_the_ledger_off_still_finishes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv(ledger.ENV, raising=False)
    store = Store(tmp_path / "targum.db")
    library = Library(tmp_path / "out", store=store)
    person = _person(store, "leaving@example.com")
    home = library.home(person)
    (home / "my-upload").mkdir(parents=True)
    _leave(store, person)
    with _crash_after_the_note(monkeypatch):
        library.purge_departed()
    Library(library.out, store=store)
    assert not home.exists()
    assert _notes(store) == []


def test_an_unreadable_note_is_logged_and_kept(
    world: World, caplog: pytest.LogCaptureFixture
) -> None:
    store, library, _book = world
    folder = _notes_folder(store)
    folder.mkdir(exist_ok=True)
    (folder / "p9-1-abcdef.json").write_text("{not json", encoding="utf-8")
    with caplog.at_level(logging.WARNING, logger="targum.serve"):
        library.purge_departed()
    assert "unreadable departure" in caplog.text
    assert (folder / "p9-1-abcdef.json").exists()


# -- ids given before the count was kept, and builds that outlive the account --------


@pytest.mark.parametrize("left_behind", ["a home on disk", "a pending note"])
def test_an_id_given_before_the_count_was_kept_is_not_given_again(
    left_behind: str, tmp_path: Path
) -> None:
    """qa-claude's fifth read of #1174 (P2-a, P2-b): an older targum purged the newest
    account and kept no `person_high`, or a restore lost it under a pending note. The
    server seeds the count at start from what it can see, so the id is not given again."""
    store = Store(tmp_path / "targum.db")
    people = [_person(store, f"{n}@example.com") for n in range(3)]
    newest = people[-1]
    _leave(store, newest)
    assert store.purge() == [newest.id]
    with store.write() as db:  # what the old purge left: the rows gone, no count kept
        db.execute("DELETE FROM person_high")
    out = tmp_path / "out"
    if left_behind == "a home on disk":
        (out / f"p{newest.id}" / "my-upload").mkdir(parents=True)
    else:
        notes = _notes_folder(store)
        notes.mkdir()
        said = {"home": f"p{newest.id}", "made": None, "hashes": []}
        (notes / f"p{newest.id}-1-abcdef.json").write_text(json.dumps(said), encoding="utf-8")
        out.mkdir()

    Library(out, store=store)

    assert _person(store, "new@example.com").id == newest.id + 1


def test_a_build_that_finishes_after_its_owner_went_is_cleared_with_them(
    monkeypatch: pytest.MonkeyPatch, world: World
) -> None:
    """P2-c (probe P7): the account goes while its build runs; what the build writes
    into the home afterwards goes too, rows and all, with nothing left to retry."""
    store, library, book = world
    person = _person(store, "leaving@example.com")
    home = library.home(person)
    _text(book, home, "my-upload", "a" * 64)

    def building(_self: Library, _job: serve_module.Job) -> None:
        _leave(store, person)
        assert library.purge_departed() == [person.id]
        assert not home.exists()
        _text(book, home, "late", "9" * 64)  # the build lands after the sweep

    monkeypatch.setattr(Library, "run", building)
    library.jobs["late"] = serve_module.Job(id="late", source="x", owner=person.id, home=home)
    library.start_workers(1)
    library.queue.put("late")
    library.queue.join()

    assert not home.exists()
    assert book.text("9" * 64) is None
    assert _notes(store) == []


def test_a_build_queued_for_an_account_that_went_never_runs(
    monkeypatch: pytest.MonkeyPatch, world: World
) -> None:
    store, library, _book = world
    person = _person(store, "leaving@example.com")
    ran: list[str] = []
    monkeypatch.setattr(Library, "run", lambda _self, job: ran.append(job.id))
    library.jobs["queued"] = serve_module.Job(id="queued", source="x", owner=person.id)
    _leave(store, person)
    library.purge_departed()
    library.start_workers(1)
    library.queue.put("queued")
    library.queue.join()
    assert ran == []
