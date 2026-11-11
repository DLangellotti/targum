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
    assert [(one["home"], one["hashes"]) for one in _notes(store)] == [(home.name, ["a" * 64])]

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
        with pytest.raises(PermissionError):
            library.home(newcomer)

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


def _departed_folder(library: Library) -> Path:
    return library.out / ".departed"


@pytest.mark.parametrize("cause", ["rename refused", "departed folder read-only"])
def test_a_refused_rename_deletes_the_home_where_it_stands(
    cause: str, monkeypatch: pytest.MonkeyPatch, world: tuple[Store, Library, ledger.Ledger]
) -> None:
    """qa-claude's second read of #1174: a refused rename left the home standing for
    good, and the next account given the id was handed it."""
    store, library, book = world
    person = _person(store, "leaving@example.com")
    home = library.home(person)
    _text(book, home, "my-upload", "a" * 64)
    _leave(store, person)
    departed = _departed_folder(library)
    if cause == "rename refused":

        def refused(*_args: object, **_kwargs: object) -> None:
            raise OSError(18, "Invalid cross-device link")

        monkeypatch.setattr(os, "rename", refused)
    else:
        departed.mkdir()
        departed.chmod(0o555)
    try:
        assert library.purge_departed() == [person.id]
        assert not home.exists()
        assert book.text("a" * 64) is None
        newcomer = _person(store, "new@example.com")
        assert newcomer.id == person.id
        assert not library.home(newcomer).exists()
        library.purge_departed()
        assert _notes(store) == []
    finally:
        if departed.exists():
            departed.chmod(0o755)


def test_what_a_removal_leaves_in_the_set_aside_folder_is_tried_again(
    world: tuple[Store, Library, ledger.Ledger],
) -> None:
    """Files a deletion cannot take (a root run's) keep the note, and every purge tries
    them again until they go."""
    store, library, book = world
    person = _person(store, "leaving@example.com")
    home = library.home(person)
    _text(book, home, "my-upload", "a" * 64)
    audio = home / "my-upload" / "audio"
    audio.mkdir()
    (audio / "private.mp3").write_bytes(b"x")
    audio.chmod(0o500)
    _leave(store, person)
    departed = _departed_folder(library)
    try:
        assert library.purge_departed() == [person.id]
        assert not home.exists()
        assert len(_notes(store)) == 1, "kept while part of the home is on disk"
        library.purge_departed()
        Library(library.out, store=store)
        assert len(_notes(store)) == 1
        assert [one.name for one in departed.rglob("private.mp3")] == ["private.mp3"]
    finally:
        for one in departed.rglob("audio"):
            one.chmod(0o755)
    library.purge_departed()
    assert _notes(store) == []
    assert list(departed.iterdir()) == []
    assert book.text("a" * 64) is None


def test_a_note_that_cannot_be_changed_never_clears_a_newcomer_s_home(
    monkeypatch: pytest.MonkeyPatch, world: tuple[Store, Library, ledger.Ledger]
) -> None:
    """qa-claude's second read of #1174: a note whose `left` could not be cleared made
    every nightly purge delete the live home of the next account given the id."""
    store, library, book = world
    person = _person(store, "leaving@example.com")
    home = library.home(person)
    _text(book, home, "my-upload", "a" * 64)
    _leave(store, person)
    with monkeypatch.context() as crash:
        crash.setattr(Library, "_remove_home", lambda *_a: None)
        crash.setattr(Library, "_finish_departures", lambda *_a: None)
        library.purge_departed()
    notes = Path(store.path).parent / f"{Path(store.path).name}.departing"
    notes.chmod(0o555)
    try:
        library = Library(library.out, store=store)
        assert not home.exists()
        newcomer = _person(store, "new@example.com")
        assert newcomer.id == person.id
        _text(book, library.home(newcomer), "newcomers-own", "b" * 64)
        library.purge_departed()
        Library(library.out, store=store).purge_departed()
        assert (library.home(newcomer) / "newcomers-own").is_dir()
        held = book.text("b" * 64)
        assert held is not None and held.homes == {f"p{newcomer.id}"}
        assert book.text("a" * 64) is None, "what was owed went"
    finally:
        notes.chmod(0o755)
    library.purge_departed()
    assert _notes(store) == [], "the note goes once its folder can be changed"
    assert (library.home(newcomer) / "newcomers-own").is_dir()


def test_a_newcomer_s_home_is_never_cleared_when_no_record_of_freed_could_be_written(
    monkeypatch: pytest.MonkeyPatch, world: tuple[Store, Library, ledger.Ledger]
) -> None:
    """qa-claude's third read of #1174 (probe C2): the notes folder and `out/.departed`
    both unwritable (one root run). The departed's home goes at start-up with neither
    record of it, then the newcomer builds; nothing may clear their home after that."""
    store, library, book = world
    person = _person(store, "leaving@example.com")
    home = library.home(person)
    _text(book, home, "my-upload", "a" * 64)
    _leave(store, person)
    with monkeypatch.context() as crash:
        crash.setattr(Library, "_remove_home", lambda *_a: None)
        crash.setattr(Library, "_finish_departures", lambda *_a: None)
        library.purge_departed()
    notes = Path(store.path).parent / f"{Path(store.path).name}.departing"
    departed = _departed_folder(library)
    departed.mkdir()
    notes.chmod(0o555)
    departed.chmod(0o555)
    try:
        library = Library(library.out, store=store)
        assert not home.exists()
        newcomer = _person(store, "new@example.com")
        assert newcomer.id == person.id
        _text(book, library.home(newcomer), "newcomers-own", "b" * 64)
        for _night in range(2):
            library.purge_departed()
            library.home(newcomer)
        assert (library.home(newcomer) / "newcomers-own").is_dir()
        held = book.text("b" * 64)
        assert held is not None and held.homes == {f"p{newcomer.id}"}
        assert book.text("a" * 64) is None
    finally:
        notes.chmod(0o755)
        departed.chmod(0o755)
    library.purge_departed()
    assert _notes(store) == [], "what stands is the newcomer's: the note is finished"
    assert (library.home(newcomer) / "newcomers-own").is_dir()


def test_the_set_aside_folder_says_freed_where_the_note_could_not(
    monkeypatch: pytest.MonkeyPatch, world: tuple[Store, Library, ledger.Ledger]
) -> None:
    """A note left at `left: true` because its folder was read-only: the set-aside folder
    still says the name was freed, so a newcomer's empty home does not hold it up."""
    store, library, book = world
    person = _person(store, "leaving@example.com")
    home = library.home(person)
    _text(book, home, "my-upload", "a" * 64)
    _leave(store, person)
    with monkeypatch.context() as crash:
        crash.setattr(Library, "_remove_home", lambda *_a: None)
        crash.setattr(Library, "_finish_departures", lambda *_a: None)
        library.purge_departed()
    notes = Path(store.path).parent / f"{Path(store.path).name}.departing"
    notes.chmod(0o555)
    try:
        library = Library(library.out, store=store)
    finally:
        notes.chmod(0o755)
    assert [one["left"] for one in _notes(store)] == [True]
    newcomer = _person(store, "new@example.com")
    library.home(newcomer).mkdir()
    library.purge_departed()
    assert _notes(store) == []
    assert library.home(newcomer).is_dir()


def test_a_departed_s_folder_under_a_newcomer_s_id_is_cleared_before_they_get_it(
    monkeypatch: pytest.MonkeyPatch, world: tuple[Store, Library, ledger.Ledger]
) -> None:
    """The other side of C2: what stands is all the departed's and older than the
    newcomer, so `home` still takes it away before handing the id's home out."""
    store, library, book = world
    person = _person(store, "leaving@example.com")
    home = library.home(person)
    _text(book, home, "my-upload", "a" * 64)
    old = 1_000_000_000
    for here, _dirs, files in os.walk(home):
        for one in files:
            os.utime(os.path.join(here, one), (old, old))
    _leave(store, person)
    with monkeypatch.context() as stuck:
        stuck.setattr(Library, "_remove_home", lambda *_a: None)
        stuck.setattr(Library, "_finish_departures", lambda *_a: None)
        library.purge_departed()
    newcomer = _person(store, "new@example.com")
    assert newcomer.id == person.id
    library._remains.add(home.name)
    assert not (library.home(newcomer) / "my-upload").exists()


def test_a_newcomer_made_before_the_note_by_the_clock_is_still_a_newcomer(
    world: tuple[Store, Library, ledger.Ledger],
) -> None:
    """Told apart by identity, not by clock order: a clock that stepped back must not
    make a newcomer look like the departing account and drop what is owed."""
    store, library, book = world
    person = _person(store, "leaving@example.com")
    _text(book, library.home(person), "my-upload", "a" * 64)
    _leave(store, person)
    with _locked(book):
        library.purge_departed()
    (note,) = _notes(store)
    newcomer = _person(store, "new@example.com")
    assert newcomer.id == person.id
    with store.write() as db:
        db.execute(
            "UPDATE person SET made = ? WHERE id = ?",
            (int(str(note["purged"])) - 60_000, newcomer.id),
        )
    _text(book, library.home(newcomer), "newcomers-own", "b" * 64)

    library.purge_departed()

    assert book.text("a" * 64) is None, "what was owed went"
    assert (library.home(newcomer) / "newcomers-own").is_dir()
    assert _notes(store) == []


def test_a_set_aside_folder_nobody_s_note_names_goes_at_the_next_purge(
    world: tuple[Store, Library, ledger.Ledger],
) -> None:
    _store, library, _book = world
    stray = _departed_folder(library) / "p9-1-abcdef"
    (stray / "my-upload").mkdir(parents=True)
    (stray / "my-upload" / "document.json").write_text("{}", encoding="utf-8")
    library.purge_departed()
    assert not stray.exists()
