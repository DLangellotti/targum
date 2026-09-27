"""The copy that leaves the box: sealed to a public key, sent, and silent until switched on.

targum-internal#16. The box keeps fourteen nights beside the database, which survives
every mistake and none of the disasters. Off the box, a copy is gzipped and encrypted
with age to a public key before rclone ever sees it — so the box can write a backup and
cannot read one — and a failed night mails the operator. Unconfigured, none of that
happens and nothing new is said but one line.
"""

from __future__ import annotations

import gzip
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from typer.testing import CliRunner

from targum import alerts, backup
from targum.accounts import Store
from targum.backup import AGE_HEADER, NotSealed, folders, recipients, seal
from targum.cli import app

KEY = "age1ql3z7hjy54pw3hyww5ayyfg7zqgvc7w3j2elw8zmrj2kg5sfn9aqmcac8p"


class FakeAge:
    """age, without age: writes an age header and the plaintext behind it, so a test can
    see both that it was sealed and what was sealed."""

    def __init__(self, *, fail: bool = False, wrong: bool = False) -> None:
        self.calls: list[tuple[str, ...]] = []
        self.fail = fail
        self.wrong = wrong

    def __call__(self, *args: str, timeout: float = 0.0) -> Any:
        self.calls.append(args)
        if self.fail:
            return SimpleNamespace(returncode=1, stdout="", stderr="bad recipient")
        target = Path(args[args.index("-o") + 1])
        plain = Path(args[-1])
        head = b"not an age file" if self.wrong else AGE_HEADER + b"\n"
        target.write_bytes(head + plain.read_bytes())
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
        if args[0] == "lsjson":
            rows = [{"Name": n, "Size": s} for n, s in self.there.get(args[1], {}).items()]
            return SimpleNamespace(returncode=0, stdout=json.dumps(rows), stderr="")
        raise AssertionError(args)


# -- the recipient ---------------------------------------------------------------------


def test_recipients_are_read_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TARGUM_BACKUP_AGE_RECIPIENT", raising=False)
    assert recipients() == []
    monkeypatch.setenv("TARGUM_BACKUP_AGE_RECIPIENT", f"{KEY}, {KEY[:-1]}q")
    assert recipients() == [KEY, f"{KEY[:-1]}q"], "a spare key rides beside the first"


def test_a_private_key_on_the_box_is_refused_by_name() -> None:
    """It would work — age derives the recipient from it — and it would put the one
    thing that opens every copy on the disk those copies exist to outlive."""
    with pytest.raises(NotSealed, match="private key"):
        recipients("AGE-SECRET-KEY-1QQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQ")


def test_something_that_is_not_a_public_key_is_refused() -> None:
    with pytest.raises(NotSealed, match="not an age public key"):
        recipients("ssh-ed25519")


# -- sealing ---------------------------------------------------------------------------


def test_the_database_is_compressed_then_sealed(tmp_path: Path) -> None:
    db = tmp_path / "targum-20260927-040000.db"
    db.write_bytes(b"SQLite format 3\x00" + b"\x00" * 4000)
    age = FakeAge()

    sealed = seal(db, [KEY], tmp_path / "outgoing", run=age)

    assert sealed.name == "targum-20260927-040000.db.gz.age"
    assert ["-r", KEY] == list(age.calls[0][1:3])
    body = sealed.read_bytes()[len(AGE_HEADER) + 1 :]
    assert gzip.decompress(body) == db.read_bytes(), "what was sealed is the gzipped database"
    assert not (tmp_path / "outgoing" / "targum-20260927-040000.db.gz").exists(), (
        "the plaintext gzip is not left lying next to the sealed copy"
    )


def test_an_archive_is_sealed_as_it_is(tmp_path: Path) -> None:
    bundle = tmp_path / "cache-20260927-040000.zip"
    bundle.write_bytes(b"PK zip already")
    sealed = seal(bundle, [KEY], tmp_path / "outgoing", run=FakeAge())
    assert sealed.name == "cache-20260927-040000.zip.age"


def test_a_failed_seal_is_an_error_and_leaves_nothing(tmp_path: Path) -> None:
    db = tmp_path / "targum-x.db"
    db.write_bytes(b"x" * 100)
    with pytest.raises(NotSealed, match="could not be sealed"):
        seal(db, [KEY], tmp_path / "outgoing", run=FakeAge(fail=True))
    assert list((tmp_path / "outgoing").iterdir()) == []


def test_a_seal_that_wrote_something_else_is_caught(tmp_path: Path) -> None:
    """A zero exit that wrote something other than an age file is the same failure as
    an upload that exited zero and wrote nothing."""
    bundle = tmp_path / "cache-x.zip"
    bundle.write_bytes(b"zip")
    with pytest.raises(NotSealed, match="not an age file"):
        seal(bundle, [KEY], tmp_path / "outgoing", run=FakeAge(wrong=True))


def test_sunday_also_goes_to_the_weekly_folder() -> None:
    assert folders("backblaze:bucket/", datetime(2026, 9, 26)) == ["backblaze:bucket/daily"]
    assert folders("backblaze:bucket", datetime(2026, 9, 27)) == [
        "backblaze:bucket/daily",
        "backblaze:bucket/weekly",
    ]


# -- the nightly command ---------------------------------------------------------------


@pytest.fixture
def box(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """A database with something in it, an empty cache and weekly, and a mailbox."""
    live = tmp_path / "targum.db"
    Store(live)
    monkeypatch.setenv("TARGUM_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("TARGUM_WEEKLY_DIR", str(tmp_path / "weekly"))
    for name in ("TARGUM_BACKUP_TO", "TARGUM_BACKUP_AGE_RECIPIENT"):
        monkeypatch.delenv(name, raising=False)
    mailed: list[tuple[str, str]] = []

    def tell(subject: str, body: str, **_: object) -> bool:
        mailed.append((subject, body))
        return True

    monkeypatch.setattr(alerts, "tell", tell)
    return {
        "store": live,
        "out": tmp_path / "backups",
        "mailed": mailed,
        "args": ["backup", "--store", str(live), "--out", str(tmp_path / "backups")],
    }


def test_unconfigured_says_so_and_changes_nothing(box: dict[str, Any]) -> None:
    """The shipped state: copies beside the database, one line, exit 0, no mail."""
    result = CliRunner().invoke(app, box["args"])

    assert result.exit_code == 0, result.output
    assert "not configured" in result.output
    assert box["mailed"] == []
    assert len(list(box["out"].glob("targum-*.db"))) == 1
    assert not (box["out"] / "outgoing").exists()


def test_a_destination_without_a_key_sends_nothing_and_says_so(
    box: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Half a switch is a failure, because the other reading of it is plaintext."""
    monkeypatch.setenv("TARGUM_BACKUP_TO", "backblaze:bucket")
    rclone = FakeRclone()
    monkeypatch.setattr(backup, "_rclone", rclone)

    result = CliRunner().invoke(app, box["args"])

    assert result.exit_code == 1
    assert rclone.there == {}, "nothing left unencrypted"
    assert box["mailed"] and "backup failed" in box["mailed"][0][0]
    assert len(list(box["out"].glob("targum-*.db"))) == 1, "the local copy still stands"


def test_a_configured_night_seals_sends_and_cleans_up(
    box: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TARGUM_BACKUP_TO", "backblaze:bucket")
    monkeypatch.setenv("TARGUM_BACKUP_AGE_RECIPIENT", KEY)
    monkeypatch.setattr(backup.shutil, "which", lambda name: f"/usr/bin/{name}")
    rclone = FakeRclone()
    monkeypatch.setattr(backup, "_age", FakeAge())
    monkeypatch.setattr(backup, "_rclone", rclone)

    result = CliRunner().invoke(app, box["args"])

    assert result.exit_code == 0, result.output
    sent = rclone.there["backblaze:bucket/daily"]
    assert [name for name in sent if name.startswith("targum-")] == [
        next(iter(box["out"].glob("targum-*.db"))).name + ".gz.age"
    ]
    assert all(name.endswith(".age") for name in sent), "only sealed files leave"
    assert box["mailed"] == []
    assert not (box["out"] / "outgoing").exists(), "sealed copies are not kept on the box"


def test_a_failed_send_mails_the_operator(
    box: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TARGUM_BACKUP_TO", "backblaze:bucket")
    monkeypatch.setenv("TARGUM_BACKUP_AGE_RECIPIENT", KEY)
    monkeypatch.setattr(backup.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(backup, "_age", FakeAge())

    def refused(*args: str, timeout: float = 0.0) -> Any:
        return SimpleNamespace(returncode=1, stdout="", stderr="401 unauthorized")

    monkeypatch.setattr(backup, "_rclone", refused)

    result = CliRunner().invoke(app, box["args"])

    assert result.exit_code == 1
    assert len(box["mailed"]) == 1
    assert "401 unauthorized" in box["mailed"][0][1]
    assert not (box["out"] / "outgoing").exists()


def test_a_missing_database_mails_too(box: dict[str, Any], tmp_path: Path) -> None:
    result = CliRunner().invoke(
        app, ["backup", "--store", str(tmp_path / "absent.db"), "--out", str(box["out"])]
    )
    assert result.exit_code == 1
    assert len(box["mailed"]) == 1


def test_a_mail_that_cannot_go_does_not_hide_the_failure(
    box: dict[str, Any], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def broken(subject: str, body: str, **_: object) -> bool:
        raise OSError("smtp down")

    monkeypatch.setattr(alerts, "tell", broken)
    result = CliRunner().invoke(
        app, ["backup", "--store", str(tmp_path / "absent.db"), "--out", str(box["out"])]
    )
    assert result.exit_code == 1
    assert "No database" in result.output


def test_the_sealed_database_is_the_live_one(
    box: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """What leaves decompresses to a database that passes the same check as the copy."""
    monkeypatch.setenv("TARGUM_BACKUP_TO", "backblaze:bucket")
    monkeypatch.setenv("TARGUM_BACKUP_AGE_RECIPIENT", KEY)
    monkeypatch.setattr(backup.shutil, "which", lambda name: f"/usr/bin/{name}")
    kept: dict[str, bytes] = {}
    age = FakeAge()

    def keeping(*args: str, timeout: float = 0.0) -> Any:
        done = age(*args)
        target = Path(args[args.index("-o") + 1])
        kept[target.name] = target.read_bytes()
        return done

    monkeypatch.setattr(backup, "_age", keeping)
    monkeypatch.setattr(backup, "_rclone", FakeRclone())
    assert CliRunner().invoke(app, box["args"]).exit_code == 0

    name = next(n for n in kept if n.startswith("targum-"))
    restored = box["out"].parent / "restored.db"
    restored.write_bytes(gzip.decompress(kept[name][len(AGE_HEADER) + 1 :]))
    assert backup.check(restored) == ""
    db = sqlite3.connect(restored)
    try:
        assert db.execute("SELECT COUNT(*) FROM person").fetchone()[0] == 0
    finally:
        db.close()
