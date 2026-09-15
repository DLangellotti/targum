"""The parasha page's list of this week's reading, run rather than read (#203).

Same harness shape as `test_lang_js.py`: a stub document in `tests/js/`, not a browser.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import pytest

HARNESS = Path(__file__).resolve().parent / "js" / "parasha.js"

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")

#: When the week began, in the milliseconds the page is given.
BEGAN = 1_788_069_600_000
DAY = 86_400_000


def page(**payload: Any) -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as where:
        given = Path(where) / "payload.json"
        given.write_text(json.dumps({"began": BEGAN, **payload}), encoding="utf-8")
        done = subprocess.run(
            ["node", str(HARNESS), str(given)], capture_output=True, text=True, timeout=60
        )
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


READING = [{"document": "torah", "section": n} for n in (1, 2, 3)]
HAFTARAH = {"document": "prophets", "sections": 1}


def test_a_part_is_read_only_when_it_was_finished_this_week() -> None:
    """A finish this week marks its part, in words as well as tone; a finish of the same
    portion a year ago says nothing about this week, and an unread part stays as it is."""
    docs = {
        "torah": {"sections": {"1": BEGAN + DAY, "2": BEGAN - 365 * DAY}},
        "prophets": {"sections": {"1": BEGAN + 2 * DAY}},
    }
    drawn = page(parts=[*READING, HAFTARAH], docs=docs)["first"]
    assert [one["read"] for one in drawn] == [True, False, False, True]
    assert all(one["read"] == one["said"] for one in drawn), "never by tone alone"


def test_a_haftarah_in_parts_is_read_when_every_part_is() -> None:
    split = {"document": "prophets", "sections": 2}
    some = {"prophets": {"sections": {"1": BEGAN + DAY}}}
    every = {"prophets": {"sections": {"1": BEGAN + DAY, "2": BEGAN + DAY}}}
    assert page(parts=[split], docs=some)["first"] == [{"read": False, "said": False}]
    assert page(parts=[split], docs=every)["first"] == [{"read": True, "said": True}]
    # A one-part record from before sections existed keeps its whole-text finish.
    old = {"prophets": {"done": BEGAN + DAY}}
    assert page(parts=[HAFTARAH], docs=old)["first"] == [{"read": True, "said": True}]


def test_a_finish_inside_the_frame_marks_its_part_at_once() -> None:
    """The reader is another window of this origin; its write reaches the page as a
    storage event, and the list follows it without a reload."""
    drawn = page(
        parts=READING,
        docs={},
        later={"torah": {"sections": {"2": BEGAN + DAY}}},
    )
    assert [one["read"] for one in drawn["first"]] == [False, False, False]
    assert [one["read"] for one in drawn["after"]] == [False, True, False]


def test_nothing_is_read_without_a_record_or_a_week() -> None:
    assert page(parts=READING)["first"] == [{"read": False, "said": False}] * 3
    assert page(parts=READING, began=0, docs={"torah": {"sections": {"1": 5}}})["first"][0] == {
        "read": False,
        "said": False,
    }
