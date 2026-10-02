"""A Monday without an issue reaches somebody (targum-internal#404)."""

from __future__ import annotations

import json
import shutil
import stat
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from typer.testing import CliRunner

from targum.cli import app
from targum.weekly import watch
from targum.weekly.watch import check, due, load, stopped, week_of

ROOT = Path(__file__).resolve().parents[1]
DEPLOY = ROOT / "deploy"

#: Monday 2026-09-28, the morning w40 was refused.
MONDAY = datetime(2026, 9, 28, tzinfo=UTC)


class Mail:
    def __init__(self, *, fails: bool = False, nobody: bool = False) -> None:
        self.sent: list[tuple[str, str]] = []
        self.fails = fails
        self.nobody = nobody

    def __call__(self, subject: str, body: str) -> bool:
        if self.fails:
            raise OSError("smtp said no")
        if self.nobody:
            return False
        self.sent.append((subject, body))
        return True


def test_the_week_is_named_as_the_run_names_it() -> None:
    assert week_of(MONDAY) == "2026-w40"
    assert week_of(datetime(2026, 1, 1, tzinfo=UTC)) == "2026-w01"


def test_an_issue_is_due_from_monday_noon_utc_to_the_next_monday() -> None:
    assert due(MONDAY + timedelta(hours=11, minutes=59)) == ""
    assert due(MONDAY + timedelta(hours=12)) == "2026-w40"
    assert due(MONDAY + timedelta(days=6, hours=23)) == "2026-w40"
    assert due(MONDAY + timedelta(days=7, hours=1)) == "", "next week's is not due yet"


def test_a_missing_week_mails_once(tmp_path: Path) -> None:
    state, mail = tmp_path / "watch.json", Mail()
    for hours in (12, 13, 40):
        check(state, lambda week: "missing", mail, now=MONDAY + timedelta(hours=hours))
    assert len(mail.sent) == 1
    subject, body = mail.sent[0]
    assert subject == "targum: no weekly for 2026-w40"
    assert "launchctl list page.targum.weekly" in body and "/tmp/targum-weekly.log" in body


def test_a_published_week_mails_nobody_and_is_still_recorded(tmp_path: Path) -> None:
    state, mail = tmp_path / "watch.json", Mail()
    check(state, lambda week: "published", mail, now=MONDAY + timedelta(hours=12))
    assert mail.sent == []
    assert load(state)["2026-w40"].found == "published", "every Monday is a line, out or not"


def test_before_noon_nothing_is_looked_at(tmp_path: Path) -> None:
    state, mail = tmp_path / "watch.json", Mail()
    check(state, lambda week: "missing", mail, now=MONDAY + timedelta(hours=6))
    assert mail.sent == [] and not state.exists()


def test_a_mail_that_did_not_go_is_owed_on_the_next_look(tmp_path: Path) -> None:
    state = tmp_path / "watch.json"
    with pytest.raises(OSError):
        check(state, lambda week: "missing", Mail(fails=True), now=MONDAY + timedelta(hours=12))
    assert load(state)["2026-w40"].told == ""
    mail = Mail()
    check(state, lambda week: "missing", mail, now=MONDAY + timedelta(hours=13))
    assert len(mail.sent) == 1


def test_with_nobody_to_tell_the_week_is_recorded_and_left_untold(tmp_path: Path) -> None:
    state = tmp_path / "watch.json"
    said = check(state, lambda week: "missing", Mail(nobody=True), now=MONDAY + timedelta(hours=12))
    assert "nobody" in said
    week = load(state)["2026-w40"]
    assert week.found == "missing" and week.told == ""


def test_a_run_that_stopped_is_mailed_with_its_reason_and_not_again(tmp_path: Path) -> None:
    state, mail = tmp_path / "watch.json", Mail()
    reason = "1 level(s) missed the band. Simplified: Sentences averaged 8.3 words."
    stopped(state, "2026-w40", reason, mail, now=MONDAY + timedelta(hours=4))
    assert mail.sent[0][0] == "targum: the weekly run for 2026-w40 stopped"
    assert reason in mail.sent[0][1]
    check(state, lambda week: "missing", mail, now=MONDAY + timedelta(hours=12))
    assert len(mail.sent) == 1, "the watch does not tell the same week twice"
    assert load(state)["2026-w40"].reason == reason


def test_an_unreadable_record_starts_over(tmp_path: Path) -> None:
    state = tmp_path / "watch.json"
    state.write_text("{not json", encoding="utf-8")
    assert load(state) == {}
    state.write_text(json.dumps({"weeks": []}), encoding="utf-8")
    assert load(state) == {}


# -- the commands ------------------------------------------------------------------------


def test_the_watch_needs_a_weekly_dir_or_every_monday_reads_as_missed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("TARGUM_ALERT_TO", "ops@example.com")
    monkeypatch.delenv("TARGUM_WEEKLY_DIR", raising=False)
    result = CliRunner().invoke(app, ["watch-weekly", "--state", str(tmp_path / "w.json")])
    assert result.exit_code == 0
    assert "TARGUM_WEEKLY_DIR is not set" in result.output
    assert not (tmp_path / "w.json").exists()


def test_the_commands_go_through_the_alert_mailer(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from targum import alerts

    told: list[tuple[str, str]] = []
    monkeypatch.setattr(alerts, "tell", lambda subject, body: told.append((subject, body)))
    monkeypatch.setenv("TARGUM_WEEKLY_DIR", str(tmp_path / "weekly"))
    monkeypatch.setattr(watch, "datetime", _Frozen)
    state = tmp_path / "w.json"

    result = CliRunner().invoke(
        app, ["weekly", "stopped", "2026-w40", "--state", str(state)], input="draft failed\n"
    )
    assert result.exit_code == 0, result.output
    assert told and "draft failed" in told[0][1]

    result = CliRunner().invoke(app, ["watch-weekly", "--state", str(state)])
    assert result.exit_code == 0, result.output
    assert len(told) == 1, "already told about w40"


class _Frozen(datetime):
    @classmethod
    def now(cls, tz: object = None) -> _Frozen:  # type: ignore[override]
        return cls(2026, 9, 28, 13, 0, tzinfo=UTC)


# -- the box and the laptop ------------------------------------------------------------


def _unit(name: str) -> dict[str, list[str]]:
    fields: dict[str, list[str]] = {}
    for line in (DEPLOY / name).read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.startswith(("#", "[")):
            key, value = line.split("=", 1)
            fields.setdefault(key.strip(), []).append(value.strip())
    return fields


def test_the_box_watches_every_hour_and_every_deploy_carries_it() -> None:
    assert _unit("targum-weekly-watch.timer")["Persistent"] == ["true"]
    service = _unit("targum-weekly-watch.service")
    assert "targum watch-weekly" in service["ExecStart"][0]
    assert service["EnvironmentFile"] == ["/etc/targum/targum.env"], "it mails through SMTP"
    assert service["User"] == ["targum"]
    script = (DEPLOY / "deploy.sh").read_text(encoding="utf-8")
    assert "deploy/targum-weekly-watch.service deploy/targum-weekly-watch.timer" in script
    assert "targum-visits.timer targum-weekly-watch.timer" in script, "and enables it"


def _fake_tree(tmp_path: Path) -> tuple[Path, Path, dict[str, str]]:
    """The run's script in a checkout of its own, with an ssh that writes down what it
    was asked to carry and a targum that never runs."""
    (tmp_path / "deploy").mkdir()
    shutil.copy(DEPLOY / "weekly-run.sh", tmp_path / "deploy" / "weekly-run.sh")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    carried = tmp_path / "carried"
    ssh = bin_dir / "ssh"
    ssh.write_text(f'#!/bin/sh\necho "$@" > "{carried}.args"\ncat > "{carried}.stdin"\n')
    targum = bin_dir / "targum"
    targum.write_text("#!/bin/sh\nexit 0\n")
    for tool in (ssh, targum):
        tool.chmod(tool.stat().st_mode | stat.S_IEXEC)
    env = {
        "PATH": f"{bin_dir}:/usr/bin:/bin",
        "HOME": str(tmp_path),
        "TARGUM_UNDER_OP": "1",
        "ANTHROPIC_API_KEY": "not-a-key",
        "TARGUM_BIN": str(targum),
    }
    return tmp_path / "deploy" / "weekly-run.sh", carried, env


def test_a_run_that_stops_tells_the_box_and_leaves_a_line(tmp_path: Path) -> None:
    """No weekly writer here, so it stops before it spends: the cheapest real stop."""
    script, carried, env = _fake_tree(tmp_path)
    run = subprocess.run(
        ["bash", str(script), "2026-w40"],
        env={**env, "TARGUM_HOST": "root@box"},
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert run.returncode == 1
    args = Path(f"{carried}.args").read_text()
    assert "targum weekly stopped '2026-w40'" in args
    assert "--state /var/lib/targum/weekly-watch.json" in args
    assert "no weekly writer" in Path(f"{carried}.stdin").read_text(), "what it said is mailed"
    line = (tmp_path / "targum-out" / "weekly" / "runs.log").read_text()
    assert "2026-w40  stopped: this checkout has no weekly writer" in line


def test_without_a_host_the_run_still_leaves_its_line(tmp_path: Path) -> None:
    script, carried, env = _fake_tree(tmp_path)
    run = subprocess.run(
        ["bash", str(script), "2026-w40"], env=env, capture_output=True, text=True, timeout=60
    )
    assert run.returncode == 1
    assert "nobody was told" in run.stderr
    assert not Path(f"{carried}.args").exists()
    assert "stopped" in (tmp_path / "targum-out" / "weekly" / "runs.log").read_text()


def test_the_scheduled_run_still_never_waives_a_refusal() -> None:
    """The stop is reported, not routed around."""
    code = "\n".join(
        line
        for line in (DEPLOY / "weekly-run.sh").read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith("#")
    )
    assert "--anyway" not in code
