"""The nightly yt-dlp upgrade says when it fails (targum-internal#513).

On 2026-10-22 the 03:30 UTC upgrade stopped on root-owned files after uv had already
deleted `bin/yt-dlp`, and YouTube, Instagram, TikTok and Facebook imports were off for
about 18 hours. The cron's MAILTO=root reaches nobody on a box with no mail transfer
agent, so the line itself now calls `targum ytdlp-stopped` when the install fails.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from typer.testing import CliRunner

from targum.cli import app

DEPLOY = Path(__file__).resolve().parent.parent / "deploy"


def _cron_line() -> str:
    text = (DEPLOY / "provision.sh").read_text(encoding="utf-8")
    block = re.search(r"cat > /etc/cron.d/targum-ytdlp <<CRON\n(.*?)\nCRON", text, re.S)
    assert block, "provision.sh no longer writes /etc/cron.d/targum-ytdlp"
    lines = [line for line in block.group(1).splitlines() if line.startswith("30 3 ")]
    assert len(lines) == 1
    return lines[0]


def test_a_failed_upgrade_runs_the_alert_as_targum() -> None:
    install, _, alert = _cron_line().partition(" || ")
    assert "uv tool install --quiet --upgrade yt-dlp" in install
    assert alert.endswith("/usr/local/bin/targum ytdlp-stopped")
    # As the service account with its settings, never as root: root-owned files in the
    # tool are what broke the upgrade in the first place.
    assert "--uid=targum --gid=targum" in alert
    assert "-p EnvironmentFile=/etc/targum/targum.env" in alert


def test_the_alert_goes_through_the_alert_mailer(monkeypatch: pytest.MonkeyPatch) -> None:
    from targum import alerts

    told: list[tuple[str, str]] = []
    monkeypatch.setattr(alerts, "tell", lambda subject, body: told.append((subject, body)))
    monkeypatch.setenv("TARGUM_ALERT_TO", "ops@example.com")
    result = CliRunner().invoke(app, ["ytdlp-stopped"])
    assert result.exit_code == 0, result.output
    assert len(told) == 1
    subject, body = told[0]
    assert "yt-dlp" in subject
    assert "journalctl -u targum-ytdlp" in body


def test_without_a_recipient_nobody_is_mailed(monkeypatch: pytest.MonkeyPatch) -> None:
    from targum import alerts

    monkeypatch.setattr(alerts, "tell", lambda *_: pytest.fail("mailed with nobody set"))
    monkeypatch.delenv("TARGUM_ALERT_TO", raising=False)
    result = CliRunner().invoke(app, ["ytdlp-stopped"])
    assert result.exit_code == 0
    assert "not configured" in result.output
