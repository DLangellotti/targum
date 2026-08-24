"""The gate between a deploy and a reader.

Every check here exists because of a way a deployment can look fine and not be.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from targum.preflight import (
    Check,
    check_account_required,
    check_address,
    check_api_key,
    check_disk,
    check_mail,
    check_paths,
    fatal,
    preflight,
)

HOSTED = {
    "TARGUM_PUBLIC_ADDRESS": "https://targum.page",
    "TARGUM_REQUIRE_ACCOUNT": "1",
    "TARGUM_SMTP_HOST": "smtp.example.com",
    "TARGUM_SMTP_USER": "resend",
    "TARGUM_SMTP_PASSWORD": "secret",
    "TARGUM_SMTP_FROM": "targum <hello@targum.page>",
    "ANTHROPIC_API_KEY": "sk-test",
}


@pytest.fixture
def hosted_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key, value in HOSTED.items():
        monkeypatch.setenv(key, value)


def test_a_complete_environment_passes(hosted_env: None, tmp_path: Path) -> None:
    checks = preflight(tmp_path / "db" / "targum.db", tmp_path / "out", port=0, connect=False)
    assert fatal(checks) == []


def test_a_missing_public_address_is_fatal(monkeypatch: pytest.MonkeyPatch) -> None:
    """The failure it exists for: links emailed to readers pointing at loopback."""
    monkeypatch.delenv("TARGUM_PUBLIC_ADDRESS", raising=False)
    assert not check_address().ok


def test_a_public_address_must_be_https(monkeypatch: pytest.MonkeyPatch) -> None:
    """A sign-in link is a bearer token in a URL."""
    monkeypatch.setenv("TARGUM_PUBLIC_ADDRESS", "http://targum.page")
    check = check_address()
    assert not check.ok and "https" in check.detail


def test_signed_out_visitors_sharing_a_home_is_fatal(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TARGUM_REQUIRE_ACCOUNT", raising=False)
    assert not check_account_required().ok


def test_no_mail_means_a_door_nobody_can_knock_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TARGUM_SMTP_HOST", raising=False)
    checks = check_mail(connect=False)
    assert not checks[0].ok and checks[0].fatal


def test_each_missing_smtp_value_is_named(
    hosted_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("TARGUM_SMTP_PASSWORD")
    broken = [c for c in check_mail(connect=False) if not c.ok]
    assert len(broken) == 1 and "PASSWORD" in broken[0].name


def test_a_missing_api_key_is_a_warning_not_a_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """Refusing to start over this would take a working library offline.

    Without a key the catalogue, the cache and everything already built still work, so a
    fatal check here would trade a whole reading product for one feature — and systemd
    runs this before every start.
    """
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    check = check_api_key()
    assert not check.ok
    assert not check.fatal


def test_an_unwritable_path_is_caught(hosted_env: None, tmp_path: Path) -> None:
    """`os.access` answers about permission bits; a read-only mount is the real case."""
    locked = tmp_path / "locked"
    locked.mkdir()
    locked.chmod(0o500)
    try:
        checks = check_paths(locked / "sub" / "targum.db", tmp_path / "out")
        assert any(not c.ok for c in checks)
    finally:
        locked.chmod(0o700)


def test_every_failure_says_what_to_do(hosted_env: None, tmp_path: Path) -> None:
    """A check that reports a state without a remedy is one somebody has to interpret."""
    for name in ("TARGUM_PUBLIC_ADDRESS", "TARGUM_REQUIRE_ACCOUNT", "TARGUM_SMTP_HOST"):
        import os

        os.environ.pop(name, None)
    for check in preflight(tmp_path / "targum.db", tmp_path / "out", port=0, connect=False):
        if not check.ok:
            assert check.fix, f"{check.name} fails without saying what to do"


def test_disk_is_measured_not_assumed(tmp_path: Path) -> None:
    assert check_disk(tmp_path).detail.endswith("GB free")


def test_a_check_reports_its_own_state() -> None:
    assert Check("x", True, "").state == "ok"
    assert Check("x", False, "").state == "FAIL"
    assert Check("x", False, "", fatal=False).state == "warn"


def test_a_hosted_box_with_nobody_invited_warns(hosted_env: None, tmp_path: Path) -> None:
    """A box nobody may join is the right default and the wrong thing to find out about
    from a reader saying the link never came.

    A warning rather than a failure on purpose: an empty list is a normal state on the
    way to inviting somebody, and refusing to start would leave no way to run the command
    that fixes it.
    """
    from targum.accounts import Store
    from targum.preflight import check_invitations

    store = tmp_path / "targum.db"
    Store(store)

    empty = check_invitations(store)
    assert not empty.ok and not empty.fatal
    assert "targum invite" in empty.fix

    Store(store).invite("wife@example.com")
    assert check_invitations(store).ok


def test_a_local_machine_is_not_asked_about_a_guest_list(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from targum.preflight import check_invitations

    monkeypatch.delenv("TARGUM_REQUIRE_ACCOUNT", raising=False)
    assert check_invitations(tmp_path / "nothing.db").ok
