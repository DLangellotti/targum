"""Easier and Harder on any pick on Home's one card (design.md §12, "Home's one card offers
the words to learn first, and a pick moves easier or harder", 2026-11-05;
targum-internal#615): `POST /find` with `step`."""

from __future__ import annotations

from typing import Any

import pytest
from test_find_button import on  # noqa: F401 - `on` is a fixture
from test_finds import home  # noqa: F401 - `home` is a fixture
from test_serve import call, sign_in

from targum.finds import live


def shelf_row(name: str, share: int, fit: str) -> dict[str, Any]:
    return {
        "id": name, "title": "סיפור", "language": "he", "kind": "story", "fit": fit,
        "expected_share": share / 100, "running_share": share / 100,
        "reason": {"key": "suggest.known", "share": share}, "origin": "shelf",
    }  # fmt: skip


BAND = [shelf_row("s96", 96, "band"), shelf_row("s94", 94, "band"), shelf_row("s91", 91, "band")]
UNDER = [shelf_row("u88", 88, "under"), shelf_row("u80", 80, "under")]


@pytest.fixture
def shelf(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    from targum.chat import tools as chat_tools

    asked: list[dict[str, Any]] = []

    def suggest_next(ctx: Any, args: dict[str, Any]) -> dict[str, Any]:
        asked.append(args)
        rows = UNDER if args.get("under") else BAND
        return {"suggestions": [row for row in rows if row["id"] not in args.get("skip", [])]}

    monkeypatch.setattr(chat_tools, "suggest_next", suggest_next)
    monkeypatch.setenv(live.FLAG, "1")

    def no_look(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("a step never searches the web")

    monkeypatch.setattr(live.LOOKS, "start", no_look)
    return asked


def step(home: Any, cookie: str, way: str, at: int, done: list[str]) -> dict[str, Any]:  # noqa: F811
    body = {"language": "he", "step": way, "from": at, "skip": done[-1:], "done": done}
    status, got, _ = call(home.port, "POST", "/find", body, cookie=cookie)
    assert status == 200, got
    return got


def test_harder_walks_down_past_the_floor_and_easier_walks_back_up(
    home: Any,  # noqa: F811
    on: None,  # noqa: F811
    shelf: list[dict[str, Any]],
) -> None:
    cookie = sign_in(home.port, home.postbox)
    got = step(home, cookie, "harder", 94, ["s94"])
    assert got["pick"]["id"] == "s91" and got["step"] == "harder"
    assert not got["pick"].get("harder"), "still in the band"
    got = step(home, cookie, "harder", 91, ["s91"])
    assert got["pick"]["id"] == "u88" and got["pick"]["harder"] is True, "past the floor"
    got = step(home, cookie, "harder", 88, ["u88"])
    assert got["pick"]["id"] == "u80"
    got = step(home, cookie, "harder", 80, ["u80"])
    assert got["pick"] is None and got["why"] == "harder"
    assert got["message"] == "No other new text is close yet."
    got = step(home, cookie, "easier", 88, ["u88"])
    assert got["pick"]["id"] == "s91", "a walk may come back to a pick it passed"
    got = step(home, cookie, "easier", 91, ["s91"])
    assert got["pick"]["id"] == "s94"
    assert not any(args.get("under") for args in shelf if args.get("limit") == 10)


def test_easier_keeps_to_the_band_and_says_when_nothing_is_left(
    home: Any,  # noqa: F811
    on: None,  # noqa: F811
    shelf: list[dict[str, Any]],
) -> None:
    cookie = sign_in(home.port, home.postbox)
    got = step(home, cookie, "easier", 96, ["s96"])
    assert got["pick"] is None and got["why"] == "easier"
    assert got["message"] == "Nothing easier fits yet."
    assert not any(args.get("under") for args in shelf), "Easier never asks under the floor"
    got = step(home, cookie, "easier", 91, ["s91", "s94"])
    assert got["pick"]["id"] == "s96", "a finished text is left out"
