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


def test_covers_being_off_is_a_warning_and_says_which_half(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ "Covers are off" and "covers are off because nobody installed Pillow" are
    different afternoons. Never fatal: the shelf drawing initials is the designed
    resting state, and the page never offers to draw what it cannot."""
    from targum import preflight as flight

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(flight, "_env", lambda name: "")
    check = flight.check_covers()

    assert check.ok is False and check.fatal is False
    assert "OPENAI_API_KEY" in check.detail
    assert "first letter" in check.fix, "it says what a reader sees instead"


def test_backups_that_never_leave_are_flagged(monkeypatch: pytest.MonkeyPatch) -> None:
    """The one thing on the list that is invisible until it matters, and the day it
    matters there is nothing to be done about it."""
    from targum import preflight as flight

    monkeypatch.delenv("TARGUM_BACKUP_TO", raising=False)
    check = flight.check_backups_leave()

    assert check.ok is False and check.fatal is False
    assert "beside the database" in check.detail
    assert "rclone" in check.fix


def test_a_destination_with_no_rclone_is_not_reported_as_working(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Set but unusable is worse than unset: it reads as done."""
    from targum import preflight as flight

    monkeypatch.setenv("TARGUM_BACKUP_TO", "b2:targum/backups")
    monkeypatch.setattr(flight.shutil, "which", lambda name: None)
    check = flight.check_backups_leave()

    assert check.ok is False
    assert "nothing has left" in check.detail


def test_backups_leaving_says_where(monkeypatch: pytest.MonkeyPatch) -> None:
    from targum import preflight as flight

    monkeypatch.setenv("TARGUM_BACKUP_TO", "b2:targum/backups")
    monkeypatch.setattr(flight.shutil, "which", lambda name: "/usr/bin/rclone")
    check = flight.check_backups_leave()

    assert check.ok is True and check.detail == "b2:targum/backups"


# --- the deploy itself ------------------------------------------------------------
#
# Not the box, which no test can reach, but the script that drives it: three of the
# things it does are invisible until months later, and all three are one line each.

DEPLOY = (Path(__file__).resolve().parents[1] / "deploy" / "deploy.sh").read_text(encoding="utf-8")


def test_the_deploy_rewrites_the_readers_already_on_the_shelves() -> None:
    """targum bakes its stylesheet and its script into each reader as it writes it, so a
    reader built last month is still the reader targum wrote last month. Installing a new
    wheel changes every page that is rendered per request and not one page that was
    written to disk — which is every reader on the box.

    As the service account. Run as root the rewritten files come out owned by root inside
    a directory owned by targum, and the failure surfaces days later, when the next
    chapter cannot be written, looking like anything but the deploy.
    """
    assert "targum rebuild" in DEPLOY, "the readers on the box keep the old script"
    line = DEPLOY[DEPLOY.index("targum rebuild") - 200 : DEPLOY.index("targum rebuild") + 120]
    assert "--uid=targum" in line, "as root this leaves root-owned files behind"
    assert "--out /var/lib/targum/targums" in line
    # And with the service's environment: the rebuild fills each reader's meanings from
    # the shared cache, and without TARGUM_CACHE_DIR it looked in an empty one.
    assert "EnvironmentFile=/etc/targum/targum.env" in line, "an empty cache fills nothing"


def test_the_deploy_stamps_the_numbers_before_it_builds() -> None:
    """The about page reads `git log`, and the wheel it is served from has no repository.
    Stamped after the build it would be stamped into nothing."""
    assert "about import stamp" in DEPLOY
    assert DEPLOY.index("about import stamp") < DEPLOY.index("uv build")


def test_nothing_in_the_remote_block_is_written_in_backticks() -> None:
    """The heredoc that carries the remote half is unquoted, so `${REMOTE_WHEEL}` is
    filled in from this machine — and so is anything in backticks, comments included. A
    comment mentioning the covers extra in backticks ran `covers` as a command on every
    deploy."""
    remote = DEPLOY.split("<<EOF", 1)[1].split("\nEOF", 1)[0]
    assert "`" not in remote, "backticks in an unquoted heredoc are run, not written"
