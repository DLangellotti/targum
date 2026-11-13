"""Finish Your targums (targum-internal#716): design's §14 pass of 2026-11-14, server side.

P1-1: one text was given three figures for how much of it the reader knows: our estimate
on Continue (97%), the marked share in its playlist (70%) and a third count on its own
page (72%). The shelf row (`_measure`), the playlist (`_playlist_facts`) and the
contents page now measure the whole text the one way and send the one figure
(`estimate.shown`, design.md §12, 2026-11-04). The reader and the text are
`test_estimate_shown.py`'s B1 reader abroad, whose marks do not settle the text.
"""

from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from test_estimate_shown import TEXT, b1  # noqa: F401  (the fixture)

from targum import coverage
from targum import level as level_module
from targum.render.builder import contents_page
from targum.serve import Handler


@pytest.fixture
def built_text(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """A built text of the reader's own whose running words are TEXT."""
    folder = tmp_path / "home" / "everyday"
    folder.mkdir(parents=True)
    monkeypatch.setattr(coverage, "tally", lambda where: dict(TEXT))
    monkeypatch.setattr(coverage, "units_in", lambda where: {})
    return folder


def handler_for(store: Any, person: Any, home: Path) -> Handler:
    handler = Handler.__new__(Handler)
    handler.store = store  # type: ignore[misc]
    handler._person = lambda: person  # type: ignore[method-assign]
    handler._home = lambda: home  # type: ignore[method-assign]
    return handler


def test_the_shelf_row_and_the_playlist_send_the_same_figure(
    b1: Any,  # noqa: F811
    built_text: Path,
) -> None:
    _, _, _, store, person = b1
    home = built_text.parent
    handler = handler_for(store, person, home)

    shelf_row: dict[str, Any] = {"name": built_text.name, "language": "he"}
    handler._measure(home, [shelf_row])
    assert "estimated" in shelf_row, "the B1 reader's marks do not settle this text"

    handler.library = SimpleNamespace(  # type: ignore[misc]
        shared=home.parent / "shared",
        reader_row=lambda where: (
            {"name": where.name, "language": "he", "words": 100} if where == built_text else None
        ),
        playlist_most=lambda *_: 20,
    )
    found = {
        "id": 1,
        "name": "Commute",
        "at": None,
        "items": [
            {"position": 0, "reader": built_text.name, "job": None, "title": "x", "failed": False}
        ],
    }
    facts = handler._playlist_facts(person, found, {})
    row = facts["items"][0]["facts"]
    assert row["known"] == shelf_row["known"]
    assert row["estimated"] == shelf_row["estimated"]
    # The playlist adds up what its rows print, and says it is ours.
    assert facts["estimated"] == level_module.page_share(shelf_row["estimated"])
    assert facts["known"] == shelf_row["known"]


def test_the_contents_page_says_the_whole_text_s_figure_as_ours(tmp_path: Path) -> None:
    """Its own page counted distinct forms per part and said a third number (72% against
    70% and 97%): it now prints the whole text's figure the server sends (`whole`, a
    `coverage.state`), our estimate labelled as ours."""
    from test_contents_page import built, manifest_of

    state = {
        "signed_in": True,
        "place": None,
        "finished": set(),
        "known": {1: (10, 9, 1), 2: (10, 5, 4), 3: (10, 0, 10)},
        "whole": {"known": 0.7, "fresh": 3, "words": 100, "estimated": 0.97},
    }
    page = contents_page(manifest_of(built(tmp_path / "book-he")), state)
    assert "You know about 97% of its words (our estimate)" in page
    assert re.search(r'class="parts-meter"[^>]*value="97"', page)
    # Settled by the marks: the marked share, said plainly.
    state["whole"] = {"known": 0.7, "fresh": 3, "words": 100}
    page = contents_page(manifest_of(built(tmp_path / "book-he-2")), state)
    assert "You know 70% of its words" in page and "of its words (our estimate)" not in page
