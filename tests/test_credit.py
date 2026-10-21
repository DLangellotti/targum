"""A provider out of credit is a sentence for the reader and a mail for the operator
(known issues 1.10). Nothing here touches the network or sends mail."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from targum import alerts, serve
from targum.errors import ProviderError

# What the box's job table held, word for word (2026-09-29, 2026-10-09).
ANTHROPIC = (
    "Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', "
    "'message': 'Your credit balance is too low to access the Anthropic API. Please go to "
    "Plans & Billing to upgrade or purchase credits.'}, 'request_id': 'req_011CfXy'}"
)
OPENAI = (
    'OpenAI 429: {\n    "error": {\n        "message": "You have no credits remaining. Add '
    "credits to continue using the API at https://platform.openai.com/settings/organization/"
    'billing/.",\n        "type": "insufficient_quota"'
)
RATE_LIMITED = '{"error": {"type": "rate_limit_error", "message": "Rate limited"}}'

NOW = datetime(2026, 10, 12, 3, 0, tzinfo=UTC)


@pytest.fixture
def mailed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    sent: list[tuple[str, str]] = []
    monkeypatch.setattr(
        alerts,
        "CREDIT",
        alerts.CreditWatch(tmp_path / "credit-watch.json", lambda *mail: sent.append(mail)),
    )
    monkeypatch.setenv(alerts.ALERT_ENV, "operator@example.com")
    return sent


def test_each_provider_is_known_by_what_it_says() -> None:
    assert alerts.out_of_credit(f"Anthropic API error 400. {ANTHROPIC}") == "Anthropic"
    assert alerts.out_of_credit(OPENAI) == "OpenAI"
    assert alerts.out_of_credit('{"detail": {"status": "quota_exceeded"}} elevenlabs') == (
        "ElevenLabs"
    )
    assert alerts.out_of_credit("BILLING_DISABLED generativelanguage.googleapis.com") == "Google"


def test_a_rate_limit_or_an_ordinary_failure_is_not_credit() -> None:
    assert alerts.out_of_credit(RATE_LIMITED) == ""
    assert alerts.out_of_credit("Anthropic API error 529. Overloaded") == ""
    assert alerts.out_of_credit("") == ""


@pytest.mark.parametrize("hosted", [True, False])
def test_the_reader_is_told_a_sentence_not_the_body(
    hosted: bool, mailed: list[tuple[str, str]]
) -> None:
    error = ProviderError("Anthropic API error 400.", ANTHROPIC)
    said = serve.told("en", error, hosted=hosted)
    assert said.startswith("Our account with the service that does this has run out")
    assert "{" not in said and "Anthropic" not in said
    russian = serve.told("ru", error, hosted=hosted)
    assert "Our account" not in russian and "{" not in russian


def test_the_operator_is_told_once_per_provider_until_the_wait_is_up(
    tmp_path: Path, mailed: list[tuple[str, str]]
) -> None:
    assert alerts.credit_ran_out("OpenAI", OPENAI, now=NOW)
    assert not alerts.credit_ran_out("OpenAI", OPENAI, now=NOW + timedelta(hours=1))
    assert alerts.credit_ran_out("Anthropic", ANTHROPIC, now=NOW + timedelta(hours=1))
    assert alerts.credit_ran_out("OpenAI", OPENAI, now=NOW + alerts.CREDIT_REMIND)
    assert [subject for subject, _ in mailed] == [
        "targum: OpenAI is out of credit",
        "targum: Anthropic is out of credit",
        "targum: OpenAI is out of credit",
    ]
    assert "no credits remaining" in mailed[0][1]


def test_the_limit_survives_a_restart(tmp_path: Path, mailed: list[tuple[str, str]]) -> None:
    """Kept on disk, because a deploy restarts the process, 32 times on 2026-10-09."""
    assert alerts.credit_ran_out("OpenAI", OPENAI, now=NOW)
    assert (tmp_path / "credit-watch.json").exists()
    alerts.CREDIT.send = lambda *mail: mailed.append(mail)
    assert not alerts.credit_ran_out("OpenAI", OPENAI, now=NOW + timedelta(minutes=5))
    assert len(mailed) == 1


def test_a_build_out_of_credit_mails_through_the_reader_path(
    mailed: list[tuple[str, str]],
) -> None:
    serve.told("en", ProviderError("The recording could not be transcribed.", OPENAI), hosted=True)
    assert [subject for subject, _ in mailed] == ["targum: OpenAI is out of credit"]


def test_nobody_configured_means_no_mail(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    sent: list[object] = []
    monkeypatch.setattr(
        alerts, "CREDIT", alerts.CreditWatch(tmp_path / "w.json", lambda *m: sent.append(m))
    )
    monkeypatch.delenv(alerts.ALERT_ENV, raising=False)
    assert not alerts.credit_ran_out("OpenAI", OPENAI, now=NOW)
    monkeypatch.setattr(alerts, "CREDIT", alerts.CreditWatch())
    monkeypatch.setenv(alerts.ALERT_ENV, "operator@example.com")
    assert not alerts.credit_ran_out("OpenAI", OPENAI, now=NOW)
    assert sent == []


def test_a_mail_that_fails_does_not_change_what_the_reader_is_told(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def refuse(*mail: object) -> None:
        raise OSError("smtp down")

    monkeypatch.setattr(alerts, "CREDIT", alerts.CreditWatch(tmp_path / "w.json", refuse))
    monkeypatch.setenv(alerts.ALERT_ENV, "operator@example.com")
    said = serve.told("en", ProviderError("Anthropic API error 400.", ANTHROPIC), hosted=True)
    assert said.startswith("Our account")


def test_any_other_provider_refusal_on_a_box_is_a_sentence_too(
    mailed: list[tuple[str, str]],
) -> None:
    error = ProviderError("Anthropic API error 500.", "{'type': 'error', 'error': {}}")
    said = serve.told("en", error, hosted=True)
    assert said == "We couldn't finish this on our side. Try again in a few minutes."
    # On a machine somebody runs themselves the reader is the operator, and the detail
    # is the useful part.
    assert "500" in serve.told("en", error, hosted=False)
    assert mailed == []


def test_an_exception_nobody_wrapped_is_checked_for_credit_too(
    mailed: list[tuple[str, str]],
) -> None:
    assert serve.broke("en", RuntimeError(ANTHROPIC)).startswith("Our account")
    assert serve.broke("en", RuntimeError("boom")).startswith("We couldn't finish this on our side")
