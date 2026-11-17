"""The practice cache knows which spots it was counted for (qa on targum#1295): a text
cached before a spot was registered gets that spot on its next read, with no VERSION bump
for each practice's PR to fight over."""

from __future__ import annotations

import json
from pathlib import Path

from test_meetings import text
from test_practices import verb

from targum import practices


def _built(tmp_path: Path) -> Path:
    line = [("כתבתי מכתב", [verb("כתבתי", "כתב", "UPOS=VERB|Tense=Past|Person=1|Number=Sing")])]
    return text(tmp_path / "t", {1: line})


def test_a_cache_records_the_spots_it_was_counted_for(tmp_path: Path) -> None:
    folder = _built(tmp_path)
    practices._cached.cache_clear()
    assert practices.text_practice(folder) is not None
    cached = json.loads((folder / practices.CACHE).read_text(encoding="utf-8"))
    assert cached["version"] == practices.VERSION
    assert cached["spots"] == practices.spots_key()
    assert "binyan" in cached["spots"].split(",")


def test_a_cache_from_before_a_spot_existed_is_counted_again(tmp_path: Path) -> None:
    """A v4 file with the right stamp, written when fewer spots were registered (here, no
    record of them at all, as every file written before this change has), is not trusted:
    the text is counted again and the spots it has now appear."""
    folder = _built(tmp_path)
    practices._cached.cache_clear()
    practices.text_practice(folder)
    path = folder / practices.CACHE
    stale = json.loads(path.read_text(encoding="utf-8"))
    stale.pop("spots")
    stale["sections"] = {"1": []}
    path.write_text(json.dumps(stale), encoding="utf-8")
    practices._cached.cache_clear()
    found = practices.text_practice(folder)
    assert found is not None
    assert {c.spot for c in found.by_section[1]} >= {"binyan", "tense"}
    assert json.loads(path.read_text(encoding="utf-8"))["spots"] == practices.spots_key()


def test_a_cache_counted_for_the_spots_there_are_is_used(tmp_path: Path) -> None:
    folder = _built(tmp_path)
    practices._cached.cache_clear()
    practices.text_practice(folder)
    path = folder / practices.CACHE
    kept = json.loads(path.read_text(encoding="utf-8"))
    kept["sections"] = {"1": []}
    path.write_text(json.dumps(kept), encoding="utf-8")
    practices._cached.cache_clear()
    found = practices.text_practice(folder)
    assert found is not None and found.by_section[1] == []


def test_registering_a_spot_changes_the_key(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    before = practices.spots_key()
    monkeypatch.setitem(practices.KEYS, "a new spot", "zz-new")
    monkeypatch.setitem(
        practices.REGISTERED, "xx", {"a new spot": practices.Practice("a new spot", "choice", "")}
    )
    assert practices.spots_key() != before and "zz-new" in practices.spots_key()
