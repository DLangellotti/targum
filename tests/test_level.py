"""The ulpan ladder, now in two places, and the fixture that keeps them one.

`level.py` is `charts.js` ported so the chat can read a rung on the server. A port is a
copy, and a copy drifts, so `tests/fixtures/level.json` holds one ledger with the answer
both must give — checked here in Python and, where node is installed, against the
browser's own code.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from datetime import date
from pathlib import Path

import pytest

from targum import level
from targum.accounts import Store

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "level.json"
CHARTS = Path(__file__).resolve().parents[1] / "src" / "targum" / "render" / "assets" / "charts.js"


def fixture() -> dict[str, object]:
    return dict(json.loads(FIXTURE.read_text(encoding="utf-8")))


def test_the_python_ladder_gives_the_fixture_s_answer() -> None:
    given = fixture()
    words = [(int(w["status"]), str(w["band"])) for w in given["words"]]  # type: ignore[index]
    weighted, known = level.reach(words)
    assert weighted == pytest.approx(given["weighted"])
    assert known == given["known"]
    here, following = level.standing(weighted)
    assert (here.name if here else "") == given["here"]
    assert (following.name if following else "") == given["next"]


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_the_browser_s_ladder_gives_the_same_answer() -> None:
    """`charts.js` run under node against the same words. The ladder's weights, its
    rungs and its filter for names are all in that one file; if any of them moves, this
    is the test that says the server disagrees."""
    given = fixture()
    script = f"""
      global.window = {{}};
      global.document = {{ createElement: () => ({{ style: {{}}, setAttribute() {{}} }}) }};
      require({json.dumps(str(CHARTS))});
      const charts = window.TargumCharts;
      const words = {json.dumps(given["words"], ensure_ascii=False)};
      const got = charts.reach(words);
      const stood = charts.standingIn(got.weighted);
      console.log(JSON.stringify({{
        weighted: got.weighted, known: got.words,
        here: stood.here ? stood.here.name : "", next: stood.next ? stood.next.name : "",
        rungs: charts.ULPAN.map(r => [r.at, r.name]),
      }}));
    """
    done = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=30)
    assert done.returncode == 0, done.stderr
    theirs = json.loads(done.stdout)
    assert theirs["weighted"] == pytest.approx(given["weighted"])
    assert theirs["known"] == given["known"]
    assert theirs["here"] == given["here"]
    assert theirs["next"] == given["next"]
    assert theirs["rungs"] == [[rung.at, rung.name] for rung in level.ULPAN], "the rungs"


def test_a_streak_counts_back_from_today_or_from_yesterday() -> None:
    today = date(2026, 9, 5)
    assert level.streaks(["2026-09-03", "2026-09-04", "2026-09-05"], today) == (3, 3)
    assert level.streaks(["2026-09-03", "2026-09-04"], today) == (2, 2), "not yet today"
    assert level.streaks(["2026-09-01", "2026-09-02"], today) == (0, 2), "broken, but longest kept"
    assert level.streaks(["2026-09-05", "not a day"], today) == (1, 1)
    assert level.streaks([], today) == (0, 0)


def test_a_snapshot_reads_the_account(tmp_path: Path) -> None:
    store = Store(tmp_path / "words.db")
    token = store.start_sign_in("reader@example.com")
    signed = store.finish_sign_in(token)
    assert signed is not None
    person = signed[0]
    store.push(
        person,
        {
            "words": [
                {
                    "language": "he",
                    "lemma": "שלום",
                    "status": 9,
                    "band": "easy",
                    "at": 5,
                    "seen": 5,
                },
                {"language": "he", "lemma": "רעב", "status": 2, "band": "hard", "at": 6, "seen": 6},
                {"language": "he", "lemma": "דוד", "status": 9, "band": "name", "at": 7, "seen": 7},
            ],
            "days": [
                {"day": "2026-09-04", "count": 1, "seen": 1},
                {"day": "2026-09-05", "count": 1, "seen": 1},
            ],
        },
    )
    got = level.snapshot(store, person.id, "he", today=date(2026, 9, 5))
    assert (got.known, got.learning) == (1, 1), "a name is neither known nor learned"
    assert got.days == 2 and got.streak == 2 and got.longest == 2
    assert got.here is None and got.next is not None and got.next.name == "aleph"
    assert level.snapshot(store, None, "he") == level.EMPTY


def test_the_description_quotes_counts_and_refuses_to_place() -> None:
    told = level.describe(
        level.Level("he", 1240, 87, 2000.0, level.ULPAN[2], level.ULPAN[3], 12, 3, 9, 31, 4)
    )
    assert "1,240 words marked known" in told
    assert "12 days read" in told and "streak of 3" in told
    assert "'bet'" in told, "the rung is given, for grading"
    assert "not a placement" in told and "Never tell the reader" in told
    assert "!" not in told
