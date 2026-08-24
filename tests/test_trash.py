"""Deleting a targum, and the week before it is really gone.

Deleting is one press on a day somebody is tidying up. The trash is what makes that
survivable, and it is the same seven days an account gets when it asks to be forgotten.
"""

from __future__ import annotations

from pathlib import Path

from targum.accounts import now
from targum.serve import TRASH_DAYS, Library


def built(home: Path, name: str) -> Path:
    folder = home / name
    (folder / "reader").mkdir(parents=True)
    (folder / "reader" / "index.html").write_text("<p>x</p>", encoding="utf-8")
    (folder / "document.json").write_text('{"title": "' + name + '", "language": "he"}', "utf-8")
    return folder


def test_a_deleted_targum_leaves_the_shelf_but_not_the_disk(tmp_path: Path) -> None:
    library = Library(tmp_path)
    home = library.home(None)
    built(home, "one-he")
    built(home, "two-he")

    assert library.trash(home, "one-he")

    assert [r["name"] for r in library.readers(home)] == ["two-he"]
    binned = library.readers(home, trashed=True)
    assert [r["name"] for r in binned] == ["one-he"]
    assert binned[0]["goesIn"] == TRASH_DAYS
    assert (home / "one-he" / "reader" / "index.html").is_file(), "nothing is deleted yet"


def test_it_can_be_put_back(tmp_path: Path) -> None:
    library = Library(tmp_path)
    home = library.home(None)
    built(home, "one-he")

    library.trash(home, "one-he")
    assert library.restore(home, "one-he")
    assert [r["name"] for r in library.readers(home)] == ["one-he"]
    assert library.readers(home, trashed=True) == []


def test_the_week_is_real(tmp_path: Path) -> None:
    library = Library(tmp_path)
    home = library.home(None)
    built(home, "one-he")
    library.trash(home, "one-he")
    marker = home / "one-he" / "trashed"

    marker.write_text(str(now() - (TRASH_DAYS - 1) * 24 * 60 * 60 * 1000))
    assert library.empty_trash() == [], "it must not go early"
    assert (home / "one-he").is_dir()

    marker.write_text(str(now() - (TRASH_DAYS + 1) * 24 * 60 * 60 * 1000))
    assert library.empty_trash() == ["one-he"]
    assert not (home / "one-he").exists()


def test_emptying_the_trash_leaves_everything_else_alone(tmp_path: Path) -> None:
    library = Library(tmp_path)
    home = library.home(None)
    built(home, "keep-he")
    built(home, "bin-he")
    library.trash(home, "bin-he")
    (home / "bin-he" / "trashed").write_text(str(now() - 30 * 24 * 60 * 60 * 1000))

    library.empty_trash()

    assert (home / "keep-he").is_dir()
    assert not (home / "bin-he").exists()


def test_nobody_can_delete_somebody_elses(tmp_path: Path) -> None:
    """The name arrives from a request, so `../` in it must not reach another home."""
    from targum.accounts import Person

    library = Library(tmp_path)
    mine = library.home(Person(1, "me@example.com"))
    theirs = library.home(None)
    mine.mkdir(parents=True, exist_ok=True)
    built(theirs, "theirs-he")

    for crafted in ("../local/theirs-he", "../local", "..", "../../etc"):
        assert not library.trash(mine, crafted), f"{crafted} should be refused"
    assert (theirs / "theirs-he" / "reader" / "index.html").is_file()


def test_deleting_something_that_is_not_there_is_refused(tmp_path: Path) -> None:
    library = Library(tmp_path)
    home = library.home(None)
    home.mkdir(parents=True, exist_ok=True)
    assert not library.trash(home, "never-built-he")


def test_the_trash_survives_a_restart(tmp_path: Path) -> None:
    """The marker is inside the folder, so it cannot drift from what it describes."""
    library = Library(tmp_path)
    home = library.home(None)
    built(home, "one-he")
    library.trash(home, "one-he")

    again = Library(tmp_path)
    assert [r["name"] for r in again.readers(home, trashed=True)] == ["one-he"]
    assert again.readers(home) == []
