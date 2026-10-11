"""Home's Continue — what it holds, run rather than read (`home.js`, 2026-10-08).

One text, one card. A place is matched to its text by the hash it was left under, and by
the folder its address names when that hash is gone: a rebuild gives a text a new hash,
and every place left before it keeps the old one.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import pytest

HARNESS = Path(__file__).resolve().parent / "js" / "home.js"

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")


def gather(**payload: Any) -> list[dict[str, Any]]:
    with tempfile.TemporaryDirectory() as where:
        written = Path(where) / "payload.json"
        written.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        done = subprocess.run(
            ["node", str(HARNESS), str(written)], capture_output=True, text=True, timeout=60
        )
    assert done.returncode == 0, done.stderr
    result: list[dict[str, Any]] = json.loads(done.stdout)
    return result


def video(document: str = "now") -> dict[str, Any]:
    return {
        "name": "da0mnhlnbhk-he",
        "document": document,
        "title": "שיחה על הבוקר",
        "language": "he",
        "video": True,
        "sections": 6,
        "built": 1,
    }


def place(hash_: str, at: int, part: int, **fields: Any) -> dict[str, Any]:
    return {
        "hash": hash_,
        "at": at,
        "section": str(part),
        "path": f"/reader/da0mnhlnbhk-he/reader/sec-{part:04d}.html",
        "seconds": 0,
        "title": "",
        "language": "",
        **fields,
    }


def test_places_left_before_a_rebuild_are_one_card_with_its_text() -> None:
    """What David saw on 2026-10-11: one video, six parts, three cards — two of them a
    thumbnail, "Text" and no title, because their hashes were from before a rebuild."""
    cards = gather(
        readers=[video("now")],
        places=[
            place("cd3e", 300, 2),
            place("2fac", 200, 2),
            place("2ffe", 100, 1, title="שיחה על הבוקר", language="he"),
        ],
    )
    assert len(cards) == 1
    assert cards[0]["reader"] == "now", "the card carries the text on the shelf"
    assert cards[0]["place"]["path"].endswith("sec-0002.html"), "the newest place leads"


def test_a_place_under_the_current_hash_is_not_drawn_twice() -> None:
    cards = gather(readers=[video("now")], places=[place("old", 300, 3), place("now", 200, 2)])
    assert [card["reader"] for card in cards] == ["now"]
    assert cards[0]["place"]["hash"] == "old"


def test_a_place_with_no_text_and_no_title_is_left_out() -> None:
    """A card with nothing to say what it is helps nobody back to it."""
    stranger = place("gone", 300, 2)
    stranger["path"] = "/reader/elsewhere/reader/sec-0002.html"
    titled = place("kept", 200, 1, title="Ruth", language="he")
    titled["path"] = "/reader/ruth/reader/sec-0001.html"
    cards = gather(readers=[], places=[stranger, titled])
    assert [card["place"]["hash"] for card in cards] == ["kept"]
