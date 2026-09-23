"""A playlist's neighbours (targum-internal#366), run rather than read."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import pytest

HARNESS = Path(__file__).resolve().parent / "js" / "list.js"

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")


def run(*cases: dict[str, Any]) -> list[dict[str, Any]]:
    with tempfile.TemporaryDirectory() as where:
        path = Path(where) / "payload.json"
        path.write_text(json.dumps({"cases": list(cases)}), encoding="utf-8")
        done = subprocess.run(
            ["node", str(HARNESS), str(path)], capture_output=True, text=True, timeout=60
        )
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def item(n: int, *, open_: bool = True, failed: bool = False) -> dict[str, Any]:
    return {
        "position": n,
        "title": f"item {n}",
        "failed": failed,
        "open": f"/reader/r{n}/reader/index.html" if open_ and not failed else None,
    }


def test_the_next_one_is_the_next_that_can_be_opened() -> None:
    [got] = run({"items": [item(0), item(1), item(2)], "at": 0})
    assert got["near"] == {"next": 1, "back": None, "waiting": 0, "last": False}
    assert got["next"] == "/reader/r1/reader/index.html?list=7&at=1&go=1"


def test_going_back_is_never_a_press() -> None:
    """design.md §12: a swipe back plays nothing new."""
    [got] = run({"items": [item(0), item(1)], "at": 1})
    assert got["back"] == "/reader/r0/reader/index.html?list=7&at=0"
    assert "go=1" not in got["back"]


def test_a_failed_item_is_passed_over_and_not_counted() -> None:
    [got] = run({"items": [item(0), item(1, failed=True), item(2)], "at": 0})
    assert got["near"]["next"] == 2
    assert got["near"]["waiting"] == 0


def test_one_getting_ready_is_passed_over_and_said() -> None:
    [got] = run({"items": [item(0), item(1, open_=False), item(2)], "at": 0})
    assert got["near"]["next"] == 2
    assert got["near"]["waiting"] == 1


def test_the_last_one_leads_to_the_end() -> None:
    [got] = run({"items": [item(0), item(1), item(2, open_=False)], "at": 1})
    assert got["near"]["last"] is True and got["next"] is None
    assert got["near"]["waiting"] == 1, "what is still getting ready is said at the end"
