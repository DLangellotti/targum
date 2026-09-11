"""Your subscriptions (2026-09-11), run rather than read."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import pytest

HARNESS = Path(__file__).resolve().parent / "js" / "follow.js"

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")


def run(**payload: Any) -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as where:
        path = Path(where) / "payload.json"
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        done = subprocess.run(
            ["node", str(HARNESS), str(path)], capture_output=True, text=True, timeout=60
        )
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


WEEKLY = {
    "id": "weekly",
    "name": "The weekly",
    "hebrew": "מבט השבוע",
    "what": "Hebrew news, written three ways, every week.",
    "page": "/weekly",
    "instalment": {
        "id": "2026-09-07",
        "title": "מבט השבוע · 7 בספטמבר",
        "when": "2026-09-07",
        "levels": [
            {
                "level": "easy",
                "name": "Easy",
                "folder": "w-easy-he",
                "reader": "/reader/w-easy-he/reader/index.html",
            },
            {
                "level": "medium",
                "name": "Medium",
                "folder": "w-medium-he",
                "reader": "/reader/w-medium-he/reader/index.html",
            },
        ],
    },
}
PARASHA = {
    "id": "parasha",
    "name": "The weekly portion",
    "hebrew": "פרשת השבוע",
    "what": "This Shabbat's reading.",
    "page": "/parasha",
    "instalment": {
        "id": "ki-tavo",
        "title": "Ki Tavo",
        "hebrew": "כי תבוא",
        "when": "2026-09-12",
        "reader": "/parasha/read/ki-tavo/reader/sec-0001.html",
    },
}
QUIET = {
    "id": "mishna-yomi",
    "name": "Mishna Yomi",
    "what": "Two mishnayot a day.",
    "page": "/mishna-yomi",
    "instalment": None,
}


def test_the_row_names_every_series_and_where_it_is_this_week() -> None:
    got = run(series=[WEEKLY, PARASHA, QUIET])
    assert got["asked"] == ["/series"] and got["shown"]
    assert [r["id"] for r in got["rows"]] == ["weekly", "parasha", "mishna-yomi"]
    assert got["rows"][1]["now"].startswith("כי תבוא") and "Sep" in got["rows"][1]["now"]
    assert got["rows"][2]["now"] == "Nothing this week yet."
    assert all(r["follow"] == "Follow" and r["pressed"] == "false" for r in got["rows"])
    assert got["rows"][0]["open"] == "/weekly?k=k"
    assert run(series=[])["shown"] is False, "no series named, no row"


def test_following_is_a_press_that_says_so_and_is_remembered() -> None:
    got = run(series=[WEEKLY, PARASHA], do=[{"type": "follow", "id": "parasha"}])
    assert got["rows"][1]["follow"] == "Following" and got["rows"][1]["pressed"] == "true"
    assert got["follows"] == {"parasha": 1}
    off = run(
        series=[WEEKLY, PARASHA], follows={"parasha": 1}, do=[{"type": "follow", "id": "parasha"}]
    )
    assert off["follows"] == {} and off["rows"][1]["follow"] == "Follow"


def test_what_is_fresh_is_followed_unseen_and_newest_first() -> None:
    got = run(
        series=[WEEKLY, PARASHA, QUIET], follows={"weekly": 1, "parasha": 1, "mishna-yomi": 1}
    )
    assert got["fresh"] == ["parasha", "weekly"], "newest first; nothing this week is nothing"
    seen = run(
        series=[WEEKLY, PARASHA], follows={"weekly": 1, "parasha": 1}, seen={"parasha": "ki-tavo"}
    )
    assert seen["fresh"] == ["weekly"], "seen once, not again"
    nobody = run(series=[WEEKLY, PARASHA])
    assert nobody["fresh"] == [], "only what is followed"


def test_the_weekly_opens_at_the_lowest_level_for_a_reader_with_no_words() -> None:
    got = run(series=[WEEKLY, PARASHA])
    assert got["readers"] == [
        "/reader/w-easy-he/reader/index.html",
        "/parasha/read/ki-tavo/reader/sec-0001.html",
    ]
