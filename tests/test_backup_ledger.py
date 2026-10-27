"""The corpus ledger in the nightly backup and the restore (targum-internal#162).

The ledger-only step needs `corpus.db` in the nightly copy and the drill first: once a
stage stops writing its cache file, the ledger is the only copy of what it made.
"""

from __future__ import annotations

import json
import re
import shutil
import sqlite3
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from typer.testing import CliRunner

from targum import alerts, backup, ledger
from targum.accounts import Store
from targum.backup import check_ledger, restore, snapshot, sweep
from targum.cli import app
from targum.models import Vocalization

DEPLOY = Path(__file__).resolve().parent.parent / "deploy"


def _pointed(n: int) -> dict[str, Any]:
    return Vocalization(
        document_hash=f"doc{n}",
        language="he",
        vocalizer="dicta/menaked/1",
        model="m",
        segments={"s0": "שָׁלוֹם."},
        machine=[],
        rejected=[],
    ).model_dump(mode="json")


def _ledger(file: Path, values: int) -> ledger.Ledger:
    book = ledger.Ledger(file)
    for n in range(values):
        book.record("vocalize", f"k{n}", _pointed(n))
    return book


def _held(path: Path) -> int:
    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        return int(db.execute("SELECT COUNT(*) FROM vocalizations").fetchone()[0])
    except sqlite3.OperationalError:
        return -1
    finally:
        db.close()


def test_a_ledger_snapshot_holds_what_its_live_wal_holds(tmp_path: Path) -> None:
    """The ledger runs in WAL mode, so its newest rows live in `corpus.db-wal`. A file
    copy of the live database misses them; the snapshot does not."""
    live = tmp_path / "corpus.db"
    _ledger(live, 1)
    # A reader held open, as the service holds one: the log is not checkpointed away
    # when the writer closes, so the newest rows are in `corpus.db-wal` only.
    holder = sqlite3.connect(live)
    holder.execute("SELECT COUNT(*) FROM meta").fetchone()
    try:
        book = ledger.Ledger(live)
        for n in range(1, 5):
            book.record("vocalize", f"k{n}", _pointed(n))
        assert (tmp_path / "corpus.db-wal").is_file()
        naive = tmp_path / "naive.db"
        shutil.copy2(live, naive)
        taken = snapshot(live, tmp_path / "backups", prefix="corpus")
    finally:
        holder.close()
    assert taken.name.startswith("corpus-") and taken.suffix == ".db"
    assert _held(taken) == 5
    assert _held(naive) < 5, "if a plain copy were enough this would not be needed"
    assert check_ledger(taken) == ""


def test_a_copy_that_is_not_a_ledger_is_refused(tmp_path: Path) -> None:
    accounts = tmp_path / "targum.db"
    Store(accounts)
    assert "not a corpus ledger" in check_ledger(snapshot(accounts, tmp_path / "b"))
    (tmp_path / "empty.db").write_bytes(b"")
    assert check_ledger(tmp_path / "empty.db") != ""


def test_ledger_copies_are_swept_on_their_own_count(tmp_path: Path) -> None:
    for day in range(1, 6):
        (tmp_path / f"corpus-2026100{day}-040000.db").write_bytes(b"x")
        (tmp_path / f"targum-2026100{day}-040000.db").write_bytes(b"x")
    sweep(tmp_path, keep=2)
    assert sorted(path.name for path in tmp_path.glob("corpus-*.db")) == [
        "corpus-20261004-040000.db",
        "corpus-20261005-040000.db",
    ]
    assert len(list(tmp_path.glob("targum-*.db"))) == 2


def test_a_restore_puts_the_ledger_back_and_keeps_what_was_there(tmp_path: Path) -> None:
    live = tmp_path / "corpus.db"
    _ledger(live, 3)
    taken = snapshot(live, tmp_path / "backups", prefix="corpus")
    _ledger(live, 7)
    (tmp_path / "corpus.db-shm").write_bytes(b"stale")
    aside = restore(taken, live, ledger=True)
    assert aside.is_file()
    assert not (tmp_path / "corpus.db-shm").exists(), "the old log is not carried over"
    assert _held(live) == 3
    assert ledger.Ledger(live).get("vocalize", "k2") == _pointed(2)


def test_a_restore_refuses_a_ledger_copy_that_is_not_one(tmp_path: Path) -> None:
    accounts = tmp_path / "targum.db"
    Store(accounts)
    with pytest.raises(ValueError, match="not a corpus ledger"):
        restore(snapshot(accounts, tmp_path / "b"), tmp_path / "corpus.db", ledger=True)


# -- the nightly command ---------------------------------------------------------------


class FakeAge:
    """age, without age: an age header and the plaintext behind it."""

    def __call__(self, *args: str, timeout: float = 0.0) -> Any:
        target = Path(args[args.index("-o") + 1])
        target.write_bytes(backup.AGE_HEADER + b"\n" + Path(args[-1]).read_bytes())
        return SimpleNamespace(returncode=0, stdout="", stderr="")


class FakeRclone:
    """rclone, keeping what it was sent per folder and answering lsjson from it."""

    def __init__(self) -> None:
        self.there: dict[str, dict[str, int]] = {}

    def __call__(self, *args: str, timeout: float = 0.0) -> Any:
        if args[0] == "copyto":
            folder, name = args[2].rsplit("/", 1)
            self.there.setdefault(folder, {})[name] = Path(args[1]).stat().st_size
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        rows = [{"Name": n, "Size": s} for n, s in self.there.get(args[1], {}).items()]
        return SimpleNamespace(returncode=0, stdout=json.dumps(rows), stderr="")


@pytest.fixture
def box(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    live = tmp_path / "targum.db"
    Store(live)
    monkeypatch.setenv("TARGUM_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("TARGUM_WEEKLY_DIR", str(tmp_path / "weekly"))
    for name in ("TARGUM_BACKUP_TO", "TARGUM_BACKUP_AGE_RECIPIENT", ledger.ENV):
        monkeypatch.delenv(name, raising=False)
    mailed: list[tuple[str, str]] = []

    def tell(subject: str, body: str, **_: object) -> bool:
        mailed.append((subject, body))
        return True

    monkeypatch.setattr(alerts, "tell", tell)
    return {
        "out": tmp_path / "backups",
        "ledger": tmp_path / "corpus.db",
        "mailed": mailed,
        "args": ["backup", "--store", str(live), "--out", str(tmp_path / "backups")],
    }


def test_the_night_copies_the_ledger_it_is_pointed_at(box: dict[str, Any]) -> None:
    _ledger(box["ledger"], 4)
    result = CliRunner().invoke(app, [*box["args"], "--ledger", str(box["ledger"])])
    assert result.exit_code == 0, result.output
    (copy,) = box["out"].glob("corpus-*.db")
    assert _held(copy) == 4
    assert "Corpus ledger copied" in result.output


def test_the_night_finds_the_ledger_through_the_environment(
    box: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    _ledger(box["ledger"], 2)
    monkeypatch.setenv(ledger.ENV, str(box["ledger"]))
    result = CliRunner().invoke(app, box["args"])
    assert result.exit_code == 0, result.output
    assert len(list(box["out"].glob("corpus-*.db"))) == 1


def test_no_ledger_is_one_line_and_no_failure(box: dict[str, Any]) -> None:
    result = CliRunner().invoke(app, box["args"])
    assert result.exit_code == 0 and "Corpus ledger: off" in result.output
    result = CliRunner().invoke(app, [*box["args"], "--ledger", str(box["ledger"])])
    assert result.exit_code == 0 and "no file at" in result.output
    assert not list(box["out"].glob("corpus-*.db")) and box["mailed"] == []


def test_a_ledger_that_will_not_copy_mails_and_the_night_goes_on(box: dict[str, Any]) -> None:
    box["ledger"].write_bytes(b"this is not a database")
    result = CliRunner().invoke(app, [*box["args"], "--ledger", str(box["ledger"])])
    assert result.exit_code == 0, result.output
    assert box["mailed"] and "backup failed" in box["mailed"][0][0]
    assert "corpus ledger" in box["mailed"][0][1].lower()
    assert len(list(box["out"].glob("targum-*.db"))) == 1, "the database copy still stands"
    assert not list(box["out"].glob("corpus-*.db"))


def test_the_ledger_leaves_sealed_with_the_rest(
    box: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TARGUM_BACKUP_TO", "backblaze:bucket")
    monkeypatch.setenv(
        "TARGUM_BACKUP_AGE_RECIPIENT",
        "age1ql3z7hjy54pw3hyww5ayyfg7zqgvc7w3j2elw8zmrj2kg5sfn9aqmcac8p",
    )
    monkeypatch.setattr(backup.shutil, "which", lambda name: f"/usr/bin/{name}")
    rclone = FakeRclone()
    monkeypatch.setattr(backup, "_age", FakeAge())
    monkeypatch.setattr(backup, "_rclone", rclone)
    _ledger(box["ledger"], 1)
    result = CliRunner().invoke(app, [*box["args"], "--ledger", str(box["ledger"])])
    assert result.exit_code == 0, result.output
    sent = rclone.there["backblaze:bucket/daily"]
    (copy,) = box["out"].glob("corpus-*.db")
    assert copy.name + ".gz.age" in sent


def test_the_restore_command_puts_a_ledger_copy_where_the_ledger_lives(
    box: dict[str, Any], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _ledger(box["ledger"], 3)
    taken = snapshot(box["ledger"], tmp_path / "kept", prefix="corpus")
    box["ledger"].unlink()
    result = CliRunner().invoke(app, ["restore", str(taken)])
    assert result.exit_code != 0 and "Where should the corpus ledger go" in result.output
    monkeypatch.setenv(ledger.ENV, str(box["ledger"]))
    result = CliRunner().invoke(app, ["restore", str(taken)])
    assert result.exit_code == 0, result.output
    assert _held(box["ledger"]) == 3


# -- what installs it ------------------------------------------------------------------


def test_the_nightly_unit_names_the_ledger_it_copies() -> None:
    """Named, not left to the environment: the account database was copied empty for
    months because the unit left `--store` to a default (2026-09-04)."""
    text = re.sub(r"\\\n\s*", " ", (DEPLOY / "targum-backup.service").read_text("utf-8"))
    (command,) = [line for line in text.splitlines() if line.startswith("ExecStart=")]
    assert "--ledger /var/lib/targum/corpus.db" in command


def test_the_drill_decrypts_and_counts_the_ledger() -> None:
    drill = (DEPLOY / "restore-drill.sh").read_text(encoding="utf-8")
    assert "corpus-*.db.gz.age" in drill
    assert "PRAGMA integrity_check" in drill.split("corpus-*.db.gz.age", 1)[1]
    assert "SELECT value FROM meta WHERE key = 'schema'" in drill
