"""The catalogue entry's English title: read from the file, sent to the page, never
invented."""

from __future__ import annotations

import json
import os
from pathlib import Path


def test_an_entry_carries_its_english_title() -> None:
    from targum.catalogue import CATALOGUE, by_id

    assert by_id("ruth").english == "Ruth"
    assert by_id("scene-01-nice-to-meet-you").english == "Nice to meet you"
    # Every entry in the fixture has one, as every entry in the live catalogue must after
    # review: there is no fallback, because a blurb where a title goes reads as a title.
    assert all(entry.english for entry in CATALOGUE), [e.id for e in CATALOGUE if not e.english]


def test_the_page_is_sent_the_english_and_an_old_file_still_loads() -> None:
    from targum.catalogue import _entry, by_id

    assert by_id("ruth").state()["english"] == "Ruth"
    # A catalogue written before the field existed loads with it empty rather than failing.
    old = _entry({"id": "x", "title": "ט", "language": "he", "source": "test:x"})
    assert old.english == ""
    assert old.state()["english"] == ""


def test_the_live_catalogue_has_an_english_title_for_every_entry() -> None:
    """The private file the box is deployed from, when this machine has it. Skipped where
    it does not — the fixture is the catalogue under test everywhere else."""
    import pytest

    live = Path(os.path.expanduser("~/.targum/catalogue.json"))
    if not live.is_file():
        pytest.skip("no live catalogue on this machine")
    loaded = json.loads(live.read_text(encoding="utf-8"))
    entries = loaded["entries"] if isinstance(loaded, dict) else loaded
    missing = [e["id"] for e in entries if not str(e.get("english", "")).strip()]
    assert not missing, f"{len(missing)} entries without an English title: {missing[:8]}"


def test_a_scene_knows_its_number_and_nothing_else_has_one() -> None:
    from targum.catalogue import scene_number

    assert scene_number("scene-01-nice-to-meet-you") == 1
    assert scene_number("scene-100-the-same-spot") == 100
    assert scene_number("ruth") == 0
    assert scene_number("") == 0
