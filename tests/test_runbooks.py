"""The runbooks in deploy/ name only things that exist (targum-internal#482).

INCIDENT.md, ROLLBACK.md, RESTORE.md and README.md are read in a hurry, on a bad night,
by somebody copying commands. A unit that was renamed or a command that went away fails
there, at the worst moment, so this reads every systemd unit and every `targum` command
they name and checks each against deploy/ and the CLI. Nothing here reaches a box.

And the out-of-credit drill, which mails nothing in this file: it is checked to go
through the same code a failing build does, against its own record, never the live one.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import typer.main
from typer.testing import CliRunner

from targum import alerts
from targum.cli import app

DEPLOY = Path(__file__).resolve().parent.parent / "deploy"
RUNBOOKS = ("INCIDENT.md", "ROLLBACK.md", "RESTORE.md", "README.md")

#: Units the box has that deploy/ does not install: Caddy is the distribution's.
NOT_OURS = {"caddy"}

NOW = datetime(2026, 10, 28, 5, 0, tzinfo=UTC)


def _text(name: str) -> str:
    return (DEPLOY / name).read_text(encoding="utf-8")


def _units_named() -> dict[str, str]:
    found: dict[str, str] = {}
    for name in RUNBOOKS:
        text = _text(name)
        for unit in re.findall(r"(?:-u |--unit=)([a-z][a-z-]*)", text):
            found.setdefault(unit, name)
        for verbs in re.findall(
            r"systemctl (?:is-active|status|show|reset-failed|restart|stop|start)"
            r"((?: [a-z][a-z-]*)+)",
            text,
        ):
            for unit in verbs.split():
                found.setdefault(unit, name)
    return found


def _units_we_have() -> set[str]:
    files = {path.stem for path in DEPLOY.glob("*.service")}
    files |= {path.stem for path in DEPLOY.glob("*.timer")}
    scripts = "\n".join(path.read_text(encoding="utf-8") for path in DEPLOY.glob("*.sh"))
    transient = set(re.findall(r"--unit[= ]([a-z][a-z-]*)", scripts))
    return files | transient | NOT_OURS


def test_every_unit_a_runbook_names_is_one_the_box_has() -> None:
    named = _units_named()
    assert "targum-deploy" in named and "targum-ytdlp" in named, "the reader found nothing"
    missing = {unit: where for unit, where in named.items() if unit not in _units_we_have()}
    assert not missing, f"named in a runbook, installed by nothing in deploy/: {missing}"


def _commands_named() -> dict[str, str]:
    found: dict[str, str] = {}
    for name in RUNBOOKS:
        text = _text(name)
        for command in re.findall(r"/usr/local/bin/targum ([a-z][a-z-]*)", text):
            found.setdefault(command, name)
        for block in re.findall(r"```[a-z]*\n(.*?)```", text, re.S):
            for command in re.findall(r"(?m)^\s*targum ([a-z][a-z-]*)", block):
                found.setdefault(command, name)
    return found


def test_every_targum_command_a_runbook_names_exists() -> None:
    named = _commands_named()
    assert "preflight" in named and "watch-health" in named, "the reader found nothing"
    known = set(typer.main.get_command(app).commands)  # type: ignore[attr-defined]
    missing = {command: where for command, where in named.items() if command not in known}
    assert not missing, f"named in a runbook, not a targum command: {missing}"


def test_the_incident_page_carries_a_drill_for_each_kind_of_trouble() -> None:
    """The card's five: a rollback, last night's database, a provider down, out of
    credit, the box unreachable. Each has its own drill and the date it last ran."""
    text = _text("INCIDENT.md")
    drills = text.partition("## Drills")[2]
    assert drills, "INCIDENT.md has no Drills section"
    for kind in ("Rollback", "Restore", "Provider down", "Out of credit", "Box unreachable"):
        assert re.search(rf"^### {kind}", drills, re.M), f"no drill for {kind}"
    assert "targum drill-credit" in drills


def test_no_runbook_says_an_outside_monitor_is_watching() -> None:
    """None was ever set up, and David's word on 2026-10-28 is "Not before Launch". A
    page that says one hears a box that is off is what lets nobody notice that nothing
    does. When one is set up, this test changes with the pages that say so."""
    for name in RUNBOOKS:
        for raw in re.split(r"\n\s*\n", _text(name)):
            paragraph = " ".join(raw.split())
            if "UptimeRobot" in paragraph or "outside monitor" in paragraph.lower():
                assert re.search(r"no outside monitor yet|Not before Launch", paragraph), (
                    f"{name} speaks of an outside monitor as if it ran: {paragraph}"
                )


# -- the out-of-credit drill -------------------------------------------------------------


@pytest.fixture
def told(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    sent: list[tuple[str, str]] = []

    def tell(subject: str, body: str, **_: object) -> bool:
        sent.append((subject, body))
        return True

    monkeypatch.setattr(alerts, "tell", tell)
    monkeypatch.setenv(alerts.ALERT_ENV, "operator@example.com")
    return sent


@pytest.mark.parametrize("provider", sorted(alerts.DRILL_REFUSALS))
def test_each_providers_refusal_is_known_and_mailed_as_a_drill(
    provider: str, tmp_path: Path, told: list[tuple[str, str]]
) -> None:
    said = alerts.drill_credit(provider, tmp_path / "credit-drill.json", now=NOW)
    assert said == f"mailed: targum: {provider} is out of credit (a drill)"
    [(subject, body)] = told
    assert subject == f"targum: {provider} is out of credit (a drill)"
    assert body.startswith("This is a drill. Nothing ran out.")
    assert "Top up the account" in body, "the real alert's body, not a stand-in"


def test_the_drill_keeps_the_four_hour_limit_in_its_own_file(
    tmp_path: Path, told: list[tuple[str, str]]
) -> None:
    state = tmp_path / "credit-drill.json"
    alerts.drill_credit("OpenAI", state, now=NOW)
    again = alerts.drill_credit("OpenAI", state, now=NOW + timedelta(hours=1))
    assert again.startswith("not mailed")
    assert len(told) == 1
    assert state.exists() and not (tmp_path / alerts.LIVE_CREDIT_STATE).exists()
    assert alerts.CREDIT.state is None and alerts.CREDIT.send is None, "put back as found"


def test_the_drill_never_writes_the_live_record(
    tmp_path: Path, told: list[tuple[str, str]]
) -> None:
    with pytest.raises(ValueError, match="live file"):
        alerts.drill_credit("Anthropic", tmp_path / alerts.LIVE_CREDIT_STATE, now=NOW)
    assert not told


def test_a_mail_that_fails_is_said_rather_than_swallowed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def refuse(*_: object, **__: object) -> bool:
        raise OSError("smtp said no")

    monkeypatch.setattr(alerts, "tell", refuse)
    monkeypatch.setenv(alerts.ALERT_ENV, "operator@example.com")
    with pytest.raises(OSError, match="smtp said no"):
        alerts.drill_credit("Anthropic", tmp_path / "credit-drill.json", now=NOW)


def test_the_command_drills_one_provider(tmp_path: Path, told: list[tuple[str, str]]) -> None:
    state = tmp_path / "drill.json"
    result = CliRunner().invoke(
        app, ["drill-credit", "--provider", "openai", "--state", str(state)]
    )
    assert result.exit_code == 0, result.output
    assert "mailed: targum: OpenAI is out of credit (a drill)" in result.output
    assert [subject for subject, _ in told] == ["targum: OpenAI is out of credit (a drill)"]


def test_the_command_refuses_a_provider_it_has_no_drill_for(
    tmp_path: Path, told: list[tuple[str, str]]
) -> None:
    result = CliRunner().invoke(
        app, ["drill-credit", "--provider", "Mistral", "--state", str(tmp_path / "d.json")]
    )
    assert result.exit_code != 0
    assert not told


def test_without_a_recipient_the_command_mails_nobody(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(alerts, "tell", lambda *_, **__: pytest.fail("mailed with nobody set"))
    monkeypatch.delenv(alerts.ALERT_ENV, raising=False)
    result = CliRunner().invoke(app, ["drill-credit", "--state", str(tmp_path / "d.json")])
    assert result.exit_code == 0
    assert "not configured" in result.output
