"""Sunday's triage (targum-internal#459): the week's messages and faults, with drafts."""

from __future__ import annotations

import os
import shlex
import sqlite3
from pathlib import Path

import pytest

from targum.accounts import Store
from targum.triage import report

NOW = 1_792_000_000_000
DAY = 24 * 60 * 60 * 1000


@pytest.fixture
def store(tmp_path: Path) -> Path:
    path = tmp_path / "targum.db"
    Store(path).close()
    db = sqlite3.connect(path)
    db.execute("INSERT INTO person (id, email, made) VALUES (1, 'reader@example.com', 0)")
    db.execute(
        "INSERT INTO told (person, at, said, page, build, viewport, language)"
        " VALUES (1, ?, 'The audio stops halfway\nthrough Ruth 2.', '/library', 'abc123',"
        " '390x844', 'en')",
        (NOW - DAY,),
    )
    db.execute(
        "INSERT INTO told (person, at, said, page, state)"
        " VALUES (1, ?, 'Fixed already', '/', 'fixed')",
        (NOW - 2 * DAY,),
    )
    for n in range(3):
        db.execute(
            "INSERT INTO fault (person, at, message, place, page, build)"
            " VALUES (?, ?, 'TypeError: boom', 'yours.js:12', '/', 'abc123')",
            (n % 2 or None, NOW - n * 1000),
        )
    db.execute(
        "INSERT INTO fault (at, message, page) VALUES (?, 'Old news', '/x')", (NOW - 30 * DAY,)
    )
    db.commit()
    db.close()
    return path


def test_the_open_messages_are_read_and_the_drafts_keep_them_here(store: Path) -> None:
    page = report(store, now_ms=NOW)
    assert "## Tell us: 1 open" in page
    assert "> The audio stops halfway\n> through Ruth 2." in page
    assert "From reader@example.com." in page
    assert "Fixed already" not in page
    # The draft names the message and never carries its words or its writer (clause 3.14).
    draft = next(line for line in page.splitlines() if line.startswith("gh issue create"))
    args = shlex.split(draft)
    body = args[args.index("--body") + 1]
    assert "Tell us #1" in body and "/library" in body and "abc123" in body
    assert "audio" not in draft and "reader@example.com" not in draft
    assert "--label beta-found" in draft


def test_faults_are_counted_in_the_window_most_often_first(store: Path) -> None:
    page = report(store, now_ms=NOW)
    assert "## Broken in browsers: 1 messages" in page
    assert "On / at yours.js:12, build abc123. 3 reports from 1 reader(s)" in page
    assert "Old news" not in page
    assert "Old news" in report(store, now_ms=NOW, days=31)


def test_a_fault_marked_fixed_is_left_out_until_it_comes_back(store: Path) -> None:
    db = sqlite3.connect(store)
    db.execute("INSERT INTO fault_fixed (message, at) VALUES ('TypeError: boom', ?)", (NOW - 1500,))
    db.commit()
    db.close()
    page = report(store, now_ms=NOW)
    assert "On / at yours.js:12, build abc123. 2 reports from 1 reader(s)" in page


def test_an_empty_week_says_so(tmp_path: Path) -> None:
    path = tmp_path / "targum.db"
    Store(path).close()
    page = report(path, now_ms=NOW)
    assert "Nothing waiting." in page and "Nothing reported." in page


def test_triage_writes_nothing(store: Path) -> None:
    before = os.stat(store).st_mtime_ns, store.read_bytes()
    report(store, now_ms=NOW)
    assert (os.stat(store).st_mtime_ns, store.read_bytes()) == before
