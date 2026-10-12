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


def article(chapters: int = 4) -> dict[str, Any]:
    return {
        "name": "hapoel-he",
        "document": "hapoel",
        "title": "הפועל חולון",
        "language": "he",
        "built": 1,
        "chapters": [
            {"number": n, "file": f"sec-{n:04d}.html", "ready": True}
            for n in range(1, chapters + 1)
        ],
    }


def next_part(reader: dict[str, Any], place: dict[str, Any], docs: dict[str, Any]) -> Any:
    with tempfile.TemporaryDirectory() as where:
        written = Path(where) / "payload.json"
        written.write_text(
            json.dumps({"next": {"reader": reader, "place": place, "docs": docs}}),
            encoding="utf-8",
        )
        done = subprocess.run(
            ["node", str(HARNESS), str(written)], capture_output=True, text=True, timeout=60
        )
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def test_a_finished_chapter_is_not_where_the_card_picks_up() -> None:
    """QA, 2026-10-12: "Pick up at chapter 1" under the line that said chapter 1 was just
    finished, and still after reloads. A finish leaves the place where Done was pressed,
    so the record of finished parts says the place is behind them: the card goes on to
    the next part not finished."""
    here = {"section": "1", "path": "/reader/hapoel-he/reader/sec-0001.html"}
    finished = {"hapoel": {"sections": {"1": 1000}}}
    assert next_part(article(), here, finished) == {
        "n": 2,
        "path": "/reader/hapoel-he/reader/sec-0002.html",
    }
    # Part 2 already finished too: on to 3.
    both = {"hapoel": {"sections": {"1": 1000, "2": 900}}}
    assert next_part(article(), here, both)["n"] == 3
    # Not finished: the place stands.
    assert next_part(article(), here, {}) is None
    # The last part finished: nothing ahead, the place stands.
    last = {"section": "4", "path": "/reader/hapoel-he/reader/sec-0004.html"}
    assert next_part(article(), last, {"hapoel": {"sections": {"4": 1}}}) is None


def portion_place(at: int, **fields: Any) -> dict[str, Any]:
    return {
        "section": "1",
        "path": "/parasha/read/noach/reader/sec-0001.html",
        "segment": "",
        "seconds": 0,
        "at": at,
        **fields,
    }


def test_a_finished_portion_heads_continue() -> None:
    """QA, 2026-10-12: Noach finished from the Library, home said "Finished נֹחַ", and no
    card carried it. A portion is not on the shelf, so its card is named by its place,
    and this browser's place carries no title: the reader writes the part, not the name.
    The name comes from this browser's own record of the text, or the account's row."""
    stored = {
        "targum:places": json.dumps({"noach": portion_place(5000)}),
        "targum:docs": json.dumps({"noach": {"title": "נֹחַ", "language": "he"}}),
    }
    cards = gather(readers=[video("now")], opened={"now": 100}, stored=stored, account=[])
    assert cards[0]["place"] == {
        "hash": "noach",
        "path": "/parasha/read/noach/reader/sec-0001.html",
        "title": "נֹחַ",
    }
    # Named only by the account: its row is older than this browser's place, and still
    # gives the card its name.
    named = {"targum:places": json.dumps({"noach": portion_place(500)})}
    account = [{"hash": "noach", **portion_place(400), "title": "נֹחַ", "language": "he"}]
    cards = gather(readers=[], stored=named, account=account)
    assert [card["place"]["title"] for card in cards] == ["נֹחַ"]
