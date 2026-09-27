"""The health watch: one mail per outage, not one per failed check (targum-internal#20)."""

from __future__ import annotations

import io
import json
import urllib.error
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from targum import alerts
from targum.alerts import REMIND, THRESHOLD, Watch, load, step, watch
from targum.cli import app
from targum.mail import ConsoleMailer

URL = "https://targum.page/health"
T0 = datetime(2026, 9, 27, 10, 0, tzinfo=UTC)
FIVE = timedelta(minutes=5)


def run(states: list[str], *, start: datetime = T0) -> list[str | None]:
    """Feed a sequence of answers ("" is healthy) through `step`; the subjects mailed."""
    now, state, subjects = start, Watch(), []
    for problem in states:
        state, mail = step(state, problem, now, URL)
        subjects.append(mail[0] if mail else None)
        now += FIVE
    return subjects


def test_one_failed_check_is_not_news() -> None:
    """A deploy's restart costs one check's worth of 502s."""
    assert run(["HTTP 502", ""]) == [None, None]


def test_two_in_a_row_mail_once_and_recovery_mails_once() -> None:
    said = run(["HTTP 502"] * 6 + ["", ""])
    mailed = [s for s in said if s]
    assert THRESHOLD == 2
    assert said[1] is not None and "failing since 2026-09-27 10:00 UTC" in said[1]
    assert len(mailed) == 2, said
    assert mailed[1] == "targum: /health is answering again"


def test_a_long_outage_is_reminded_not_repeated() -> None:
    checks = int(REMIND / FIVE) + 3
    mailed = [s for s in run(["no answer"] * checks) if s]
    assert len(mailed) == 2
    assert "still failing" in mailed[1]


def test_healthy_resets_the_count() -> None:
    assert run(["HTTP 502", "", "HTTP 502", ""]) == [None] * 4


def test_the_watch_keeps_its_count_between_runs(tmp_path: Path) -> None:
    state = tmp_path / "watch.json"
    sent: list[tuple[str, str]] = []

    def send(subject: str, body: str) -> None:
        sent.append((subject, body))

    watch(state, URL, now=T0, knock=lambda url: "HTTP 503", send=send)
    assert sent == [] and load(state).failures == 1
    watch(state, URL, now=T0 + FIVE, knock=lambda url: "HTTP 503", send=send)
    assert len(sent) == 1 and "HTTP 503" in sent[0][1]
    watch(state, URL, now=T0 + 2 * FIVE, knock=lambda url: "", send=send)
    assert len(sent) == 2 and load(state) == Watch()


def test_a_mail_that_did_not_go_is_owed_on_the_next_check(tmp_path: Path) -> None:
    """Never mark an outage as told when it was not."""
    state = tmp_path / "watch.json"
    sent: list[str] = []

    def down(url: str) -> str:
        return "HTTP 503"

    def broken(subject: str, body: str) -> None:
        raise OSError("smtp down")

    watch(state, URL, now=T0, knock=down, send=broken)
    with pytest.raises(OSError):
        watch(state, URL, now=T0 + FIVE, knock=down, send=broken)
    assert load(state).alerted_at == ""
    watch(state, URL, now=T0 + 2 * FIVE, knock=down, send=lambda s, b: sent.append(s))
    assert len(sent) == 1

    with pytest.raises(OSError):
        watch(state, URL, now=T0 + 3 * FIVE, knock=lambda url: "", send=broken)
    assert load(state).alerted_at, "the recovery mail is still owed"
    watch(state, URL, now=T0 + 4 * FIVE, knock=lambda url: "", send=lambda s, b: sent.append(s))
    assert sent[-1] == "targum: /health is answering again"


def test_an_unreadable_state_file_starts_over(tmp_path: Path) -> None:
    state = tmp_path / "watch.json"
    state.write_text("{not json", encoding="utf-8")
    assert load(state) == Watch()
    state.write_text(json.dumps({"failures": 3, "surprise": 1}), encoding="utf-8")
    assert load(state).failures == 3


# -- the knock -------------------------------------------------------------------------


class Answer(io.BytesIO):
    def __init__(self, body: bytes, status: int = 200) -> None:
        super().__init__(body)
        self.status = status

    def __enter__(self) -> Answer:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        (b'{"ok": true, "store": true, "queue": 0}', ""),
        (b'{"ok": false, "store": false}', "ok is not true"),
        (b"<html>sign in</html>", "not JSON"),
    ],
)
def test_the_knock_reads_ok_not_just_the_status(
    monkeypatch: pytest.MonkeyPatch, body: bytes, expected: str
) -> None:
    monkeypatch.setattr(alerts.urllib.request, "urlopen", lambda req, timeout: Answer(body))
    said = alerts.probe(URL)
    assert (said == "") if not expected else (expected in said)


def test_the_knock_names_an_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(req: Any, timeout: float) -> Any:
        raise urllib.error.HTTPError(URL, 503, "unavailable", None, None)  # type: ignore[arg-type]

    monkeypatch.setattr(alerts.urllib.request, "urlopen", refuse)
    assert alerts.probe(URL) == "HTTP 503"


def test_the_knock_names_silence(monkeypatch: pytest.MonkeyPatch) -> None:
    def silent(req: Any, timeout: float) -> Any:
        raise urllib.error.URLError("timed out")

    monkeypatch.setattr(alerts.urllib.request, "urlopen", silent)
    assert alerts.probe(URL).startswith("no answer")


# -- switched off ----------------------------------------------------------------------


def test_nobody_to_tell_is_not_configured(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """The shipped state: the timer runs, knocks on nothing, writes nothing."""
    monkeypatch.delenv("TARGUM_ALERT_TO", raising=False)
    knocked: list[str] = []
    monkeypatch.setattr(alerts, "probe", lambda url, **_: knocked.append(url) or "")
    state = tmp_path / "watch.json"

    result = CliRunner().invoke(app, ["watch-health", "--state", str(state)])

    assert result.exit_code == 0
    assert "not configured" in result.output
    assert knocked == [] and not state.exists()
    assert alerts.tell("s", "b") is False, "and nothing is mailed"


def test_the_url_defaults_to_the_public_address(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TARGUM_HEALTH_URL", raising=False)
    monkeypatch.setenv("TARGUM_PUBLIC_ADDRESS", "https://targum.page/")
    assert alerts.health_url() == URL
    monkeypatch.setenv("TARGUM_HEALTH_URL", "http://127.0.0.1:8420/health")
    assert alerts.health_url() == "http://127.0.0.1:8420/health"


def test_it_goes_through_targums_own_mailer(monkeypatch: pytest.MonkeyPatch) -> None:
    """No second provider: the same `notify` that tells a reader a build finished."""
    monkeypatch.setenv("TARGUM_ALERT_TO", "ops@example.com")
    out = io.StringIO()
    assert alerts.tell("targum: test", "body", mailer=ConsoleMailer(stream=out)) is True
    assert "ops@example.com" in out.getvalue() and "targum: test" in out.getvalue()


def test_the_command_mails_on_the_second_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("TARGUM_ALERT_TO", "ops@example.com")
    monkeypatch.setattr(alerts, "probe", lambda url, **_: "HTTP 502")
    sent: list[str] = []
    monkeypatch.setattr(alerts, "tell", lambda subject, body, **_: sent.append(subject) or True)
    state = tmp_path / "watch.json"
    args = ["watch-health", "--state", str(state), "--url", URL]

    assert CliRunner().invoke(app, args).exit_code == 0
    assert sent == []
    assert CliRunner().invoke(app, args).exit_code == 0
    assert len(sent) == 1
