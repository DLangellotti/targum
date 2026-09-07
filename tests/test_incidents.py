"""Somewhere an error is recorded, other than the journal (targum-internal#24)."""

from __future__ import annotations

import json
from pathlib import Path

from targum import incidents


def test_an_incident_is_written_down_and_read_back_newest_first(tmp_path: Path) -> None:
    path = tmp_path / "incidents.jsonl"
    assert incidents.recent(path) == [], "no file, no incidents"
    try:
        raise RuntimeError("the box fell over")
    except RuntimeError as error:
        first = incidents.record(path, "/gloss?k=secret&lemma=שלום", error)
    second = incidents.record(path, "build:translating", message="ran out of pages", job="j1")
    found = incidents.recent(path)
    assert [one.where for one in found] == ["build:translating", "/gloss"], (
        "newest first, and the query string is not kept"
    )
    assert found[1].kind == "RuntimeError" and found[1].message == "the box fell over"
    assert "RuntimeError: the box fell over" in found[1].trace
    assert found[0].job == "j1" and found[0].kind == "" and found[0].trace == ""
    assert first.at <= second.at


def test_an_address_never_reaches_the_file_and_a_message_is_cut_short(tmp_path: Path) -> None:
    """The mailer's own errors quote the address they failed to reach, and a message can
    carry a whole response body. Neither belongs in a file the operator reads."""
    path = tmp_path / "incidents.jsonl"
    incidents.record(
        path, "/account", message="could not send to reader@example.com: " + "x" * 1000
    )
    raw = path.read_text(encoding="utf-8")
    assert "reader@example.com" not in raw and "<address>" in raw
    assert len(incidents.recent(path)[0].message) <= incidents.MESSAGE_CHARS


def test_the_file_is_a_ring(tmp_path: Path) -> None:
    path = tmp_path / "incidents.jsonl"
    for n in range(incidents.TRIM_AT + 5):
        incidents.record(path, f"/route/{n}", message=str(n))
    lines = path.read_text(encoding="utf-8").splitlines()
    # Trimmed the moment it passed the ceiling — at the 401st record, back to the last
    # 200 — and then appended to again, so it sits between the two marks.
    assert incidents.KEEP <= len(lines) < incidents.TRIM_AT, "a ring, not a log"
    assert incidents.recent(path, limit=1)[0].where == f"/route/{incidents.TRIM_AT + 4}"
    assert json.loads(lines[0])["where"] == f"/route/{incidents.TRIM_AT + 1 - incidents.KEEP}"


def test_a_recorder_that_cannot_write_says_nothing(tmp_path: Path) -> None:
    """Inside an exception handler, a second exception hides the first."""
    blocked = tmp_path / "not-a-dir" / "incidents.jsonl"
    (tmp_path / "not-a-dir").write_text("a file where a directory should be")
    incident = incidents.record(blocked, "/x", message="lost")
    assert incident.message == "lost" and not blocked.exists()


def test_a_damaged_line_is_skipped(tmp_path: Path) -> None:
    path = tmp_path / "incidents.jsonl"
    incidents.record(path, "/a", message="one")
    with path.open("a", encoding="utf-8") as out:
        out.write("{not json\n")
        out.write(json.dumps({"unexpected": "shape"}) + "\n")
    incidents.record(path, "/b", message="two")
    assert [one.where for one in incidents.recent(path)] == ["/b", "/a"]
