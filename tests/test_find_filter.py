"""Filter on Home's one card (design.md §12, "Home's one card offers the words to learn
first, and a pick moves easier or harder", 2026-11-05; targum-internal#615): medium and
length beside the topics, on `POST /find`."""

from __future__ import annotations

from typing import Any

import pytest
from test_find_button import on  # noqa: F401 - `on` is a fixture
from test_finds import home  # noqa: F401 - `home` is a fixture
from test_serve import call, sign_in

from targum.finds import live
from targum.serve import filter_holds


@pytest.mark.parametrize(
    ("row", "medium", "length", "holds"),
    [
        ({"kind": "video", "minutes": 7}, "watch", "mid", True),
        ({"kind": "story", "video": True, "minutes": 7}, "watch", "", True),
        ({"kind": "article", "minutes": 7}, "watch", "", False),
        ({"kind": "podcast", "minutes": 30}, "listen", "long", True),
        ({"kind": "article", "minutes": 4}, "read", "short", True),
        ({"kind": "article", "minutes": 5}, "read", "short", False),
        ({"kind": "article", "minutes": 15}, "", "mid", True),
        ({"kind": "article", "minutes": 16}, "", "long", True),
        ({"kind": "article"}, "", "mid", False),
        ({"kind": "article"}, "", "", True),
        ({"kind": "article"}, "sing", "forever", True),
    ],
)  # fmt: skip
def test_a_row_passes_the_medium_and_length_chosen(
    row: dict[str, Any], medium: str, length: str, holds: bool
) -> None:
    assert filter_holds(row, medium, length) is holds


def shelf_row(name: str, kind: str, minutes: int) -> dict[str, Any]:
    return {
        "id": name, "title": "סיפור", "language": "he", "kind": kind, "fit": "band",
        "minutes": minutes, "reason": {"key": "suggest.known", "share": 94}, "origin": "shelf",
    }  # fmt: skip


def test_watch_picks_a_shelf_video_and_never_looks_on_the_web(
    home: Any,  # noqa: F811
    on: None,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from targum.chat import tools as chat_tools

    rows = [shelf_row("story", "story", 6), shelf_row("talk", "video", 20)]
    asked: list[dict[str, Any]] = []

    def suggest_next(ctx: Any, args: dict[str, Any]) -> dict[str, Any]:
        asked.append(args)
        return {"suggestions": [row for row in rows if row["id"] not in args.get("skip", [])]}

    monkeypatch.setattr(chat_tools, "suggest_next", suggest_next)
    monkeypatch.setenv(live.FLAG, "1")

    def no_look(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("Watch never starts a look on the web")

    monkeypatch.setattr(live.LOOKS, "start", no_look)
    cookie = sign_in(home.port, home.postbox)
    body = {"language": "he", "medium": "watch", "skip": [], "done": ["ruth"]}
    status, got, _ = call(home.port, "POST", "/find", body, cookie=cookie)
    assert status == 200 and got["pick"]["id"] == "talk", got
    assert "ruth" in asked[0]["skip"]
    body = {"language": "he", "medium": "watch", "length": "short", "skip": [], "done": []}
    status, got, _ = call(home.port, "POST", "/find", body, cookie=cookie)
    assert status == 200 and got["pick"] is None, got
    status, chips, _ = call(home.port, "POST", "/find", {"chips": True}, cookie=cookie)
    assert chips["listen"] is False, "nothing in the pool to listen to"
