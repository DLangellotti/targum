"""One figure for a new reader's first text, server side (targum-internal#724).

The reader asks `/readers?catalogue=0&name=<folder>` for its own text's figure, and is
answered with the row Home's shelf call measures (`_measure`, `estimate.shown`), whether
the text is the reader's own or the shared shelf's; design.md §12, "A reader says our
estimate until anything in it is marked" (2026-11-15). The reader is `test_estimate_shown.py`'s
B1 reader abroad, whose one mark does not settle the text.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from test_estimate_shown import TEXT, b1  # noqa: F401  (the fixture)

from targum import coverage
from targum.serve import Handler


@pytest.fixture
def shelves(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> tuple[Path, Path]:
    """The reader's own shelf and the shared one, each a text whose running words are
    TEXT, and a second shared text nobody asked about."""
    home, shared = tmp_path / "home", tmp_path / "shared"
    for folder in (home / "mine", shared / "first", shared / "other"):
        folder.mkdir(parents=True)
    monkeypatch.setattr(coverage, "tally", lambda where: dict(TEXT))
    monkeypatch.setattr(coverage, "units_in", lambda where: {})
    return home, shared


def asking(store: Any, person: Any, home: Path, shared: Path) -> Any:
    handler = Handler.__new__(Handler)
    handler.store = store  # type: ignore[misc]
    handler._person = lambda: person  # type: ignore[method-assign]
    handler._home = lambda: home  # type: ignore[method-assign]
    handler._may_draw = lambda: False  # type: ignore[method-assign]

    def rows(where: Path, trashed: bool = False) -> list[dict[str, Any]]:
        if trashed:
            return []
        return [
            {"name": one.name, "document": f"{one.name}0000000000000", "language": "he"}
            for one in sorted(where.iterdir())
        ]

    handler.library = SimpleNamespace(  # type: ignore[misc]
        shared=shared,
        readers=rows,
        talks=lambda home, person_id: False,
        can_draw=lambda: False,
    )
    said: list[dict[str, Any]] = []
    handler._json = lambda body, *a, **k: said.append(body)  # type: ignore[method-assign]

    def ask(**query: str) -> dict[str, Any]:
        handler._readers({key: [value] for key, value in query.items()})
        return said.pop()

    return ask


def test_the_reader_s_ask_gets_home_s_row_for_a_shared_text(
    b1: Any,  # noqa: F811
    shelves: tuple[Path, Path],
) -> None:
    _, _, _, store, person = b1
    ask = asking(store, person, *shelves)
    homes = ask(catalogue="0", shared="first0000000")
    readers = ask(catalogue="0", name="first")
    assert [row["name"] for row in readers["shared"]] == ["first"], "that text and no other"
    assert readers["readers"] == [] and readers["trash"] == []
    on_home = next(row for row in homes["shared"] if row["name"] == "first")
    on_reader = readers["shared"][0]
    assert "estimated" in on_reader, "the B1 reader's marks do not settle this text"
    assert (on_reader["known"], on_reader["estimated"]) == (
        on_home["known"],
        on_home["estimated"],
    )


def test_the_reader_s_ask_gets_home_s_row_for_its_own_text(
    b1: Any,  # noqa: F811
    shelves: tuple[Path, Path],
) -> None:
    _, _, _, store, person = b1
    ask = asking(store, person, *shelves)
    homes = ask(catalogue="0", shared="-")
    readers = ask(catalogue="0", name="mine")
    assert [row["name"] for row in readers["readers"]] == ["mine"]
    assert readers["shared"] == []
    assert readers["readers"][0]["estimated"] == homes["readers"][0]["estimated"]


def test_the_contents_page_s_ask_still_takes_nothing_off_the_shelf(
    b1: Any,  # noqa: F811
    shelves: tuple[Path, Path],
) -> None:
    _, _, _, store, person = b1
    ask = asking(store, person, *shelves)
    assert ask(shared="0", catalogue="0", name="first")["shared"] == []


def test_a_name_on_neither_shelf_is_answered_with_nothing(
    b1: Any,  # noqa: F811
    shelves: tuple[Path, Path],
) -> None:
    _, _, _, store, person = b1
    ask = asking(store, person, *shelves)
    for name in ("nowhere", "../home/mine"):
        said = ask(catalogue="0", name=name)
        assert (said["readers"], said["shared"]) == ([], []), name
