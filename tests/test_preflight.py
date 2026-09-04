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
    check_pot,
    check_scripture,
    check_ytdlp,
    check_ytdlp_proxy,
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


def test_the_box_is_told_when_it_cannot_fetch_from_youtube(
    hosted_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """It used to pass with a note, because the box never fetched from YouTube and a
    standing warning nobody reads takes the real one beside it down with it. The paste
    is a hosted door now, so a box without yt-dlp is a box where every YouTube import
    fails at the button — which is worth saying, and still not fatal."""
    monkeypatch.setattr("shutil.which", lambda name: None)
    check = check_ytdlp()
    assert not check.ok
    assert not check.fatal, "nothing else about the server depends on it"
    assert "YouTube imports are off" in check.detail


def test_a_laptop_without_ytdlp_is_still_told(monkeypatch: pytest.MonkeyPatch) -> None:
    """Off the box the door is real, and the warning stays exactly as it was."""
    monkeypatch.delenv("TARGUM_REQUIRE_ACCOUNT", raising=False)
    monkeypatch.setattr("shutil.which", lambda name: None)
    check = check_ytdlp()
    assert not check.ok and not check.fatal
    assert "install yt-dlp" in check.fix


@pytest.mark.parametrize("hosted", ["1", ""])
def test_ytdlp_on_the_path_passes_everywhere(hosted: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TARGUM_REQUIRE_ACCOUNT", hosted)
    monkeypatch.setattr("shutil.which", lambda name: "/usr/local/bin/yt-dlp")
    assert check_ytdlp().ok


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


def test_scripture_warns_when_the_tagging_is_not_where_the_service_looks(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A box without the Hebrew Bible tagging reads every verse with a model, and the
    only sign used to be a lemma spelled DICTA's way on a card (targum-internal#156).
    Asked in the service's environment, because `model_dir()` follows the process's own
    home and the deployer's is not the service's."""
    monkeypatch.setenv("TARGUM_MODEL_DIR", str(tmp_path))
    check = check_scripture()
    assert not check.ok and not check.fatal, "a working product, read by a model"
    assert str(tmp_path) in check.detail
    assert "targum models fetch scripture" in check.fix


def test_scripture_passes_when_the_tagging_is_on_disk(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("targum.annotate.oshb.available", lambda: True)
    check = check_scripture()
    assert check.ok and check.state == "ok"


def test_no_minter_named_is_a_laptop_and_is_fine(monkeypatch: pytest.MonkeyPatch) -> None:
    """A home IP is proof enough for YouTube. Nothing to knock on, nothing to warn about
    — a standing warning nobody can act on takes the real one beside it down with it."""
    monkeypatch.delenv("TARGUM_POT_PROVIDER", raising=False)
    check = check_pot()
    assert check.ok and not check.fatal


def test_a_named_minter_that_does_not_answer_is_said_out_loud(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Somebody meant to run the provider and it is not there. Without this the next
    symptom is a reader's YouTube import failing after the spinner, and the box's
    journal saying nothing about why."""
    monkeypatch.setenv("TARGUM_POT_PROVIDER", "http://127.0.0.1:4416")

    def refuse(url, timeout=0):
        raise OSError("Connection refused")

    monkeypatch.setattr("targum.preflight.urlopen", refuse)
    check = check_pot()
    assert not check.ok
    # Not fatal, for check_ytdlp's reason: every other door is untouched.
    assert not check.fatal
    assert "bgutil-pot" in check.fix


def test_the_unit_does_not_knock_on_start(monkeypatch: pytest.MonkeyPatch) -> None:
    """`targum.service` runs preflight --no-connect as ExecStartPre. A minter that is
    slow to come up must not be what stops targum from starting at all."""
    monkeypatch.setenv("TARGUM_POT_PROVIDER", "http://127.0.0.1:4416")

    def never(url, timeout=0):
        raise AssertionError("--no-connect knocked anyway")

    monkeypatch.setattr("targum.preflight.urlopen", never)
    assert check_pot(connect=False).ok


def test_a_minter_that_answers_says_which_one(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TARGUM_POT_PROVIDER", "http://127.0.0.1:4416")

    class Answer:
        def read(self) -> bytes:
            return b'{"server_uptime": 12, "version": "1.3.2"}'

        def __enter__(self) -> Answer:
            return self

        def __exit__(self, *_: object) -> None:
            return None

    monkeypatch.setattr("targum.preflight.urlopen", lambda url, timeout=0: Answer())
    check = check_pot()
    assert check.ok
    assert "1.3.2" in check.detail


def test_a_hosted_box_with_no_egress_is_told_the_door_cannot_open(
    hosted_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Measured 2026-09-04: the box's Hetzner address is flagged by YouTube, and neither
    a JS runtime nor a token minter changes that. Without an egress every YouTube paste
    fails at the button, so the deploy is where that should be said."""
    monkeypatch.delenv("TARGUM_YTDLP_PROXY", raising=False)
    check = check_ytdlp_proxy()
    assert not check.ok and not check.fatal
    assert "flagged" in check.detail


def test_a_laptop_fetches_from_itself_and_is_not_nagged(monkeypatch: pytest.MonkeyPatch) -> None:
    """A home address is one YouTube trusts, so there is nothing to configure and a
    standing warning would only teach somebody to ignore the ones beside it."""
    monkeypatch.delenv("TARGUM_REQUIRE_ACCOUNT", raising=False)
    monkeypatch.delenv("TARGUM_YTDLP_PROXY", raising=False)
    assert check_ytdlp_proxy().ok


def test_an_egress_that_stopped_answering_is_loud(monkeypatch: pytest.MonkeyPatch) -> None:
    """The shape a tunnel fails in: the machine at the far end closed its lid."""
    monkeypatch.setenv("TARGUM_YTDLP_PROXY", "socks5://127.0.0.1:1080")

    def refuse(address, timeout=0):
        raise OSError("Connection refused")

    monkeypatch.setattr("socket.create_connection", refuse)
    check = check_ytdlp_proxy()
    assert not check.ok
    assert "did not answer" in check.detail


def test_the_unit_does_not_knock_on_the_egress_either(monkeypatch: pytest.MonkeyPatch) -> None:
    """ExecStartPre runs --no-connect. A sleeping laptop must not stop targum starting."""
    monkeypatch.setenv("TARGUM_YTDLP_PROXY", "socks5://127.0.0.1:1080")

    def never(address, timeout=0):
        raise AssertionError("--no-connect knocked anyway")

    monkeypatch.setattr("socket.create_connection", never)
    assert check_ytdlp_proxy(connect=False).ok


def test_the_egress_password_never_reaches_the_deploy_log(monkeypatch: pytest.MonkeyPatch) -> None:
    """A residential proxy is bought with a username and a password in the URL, and this
    check is printed by the deploy over SSH and again into the journal. The host and the
    port are the whole of what a reader of it needs."""
    monkeypatch.setenv("TARGUM_YTDLP_PROXY", "http://buyer:s3cret@proxy.example.com:8080")
    monkeypatch.setattr("socket.create_connection", lambda address, timeout=0: _Nothing())
    answered = check_ytdlp_proxy()
    refused = check_ytdlp_proxy(connect=False)

    def broken(address, timeout=0):
        raise OSError("Connection refused")

    monkeypatch.setattr("socket.create_connection", broken)
    dead = check_ytdlp_proxy()
    for check in (answered, refused, dead):
        said = f"{check.detail} {check.fix}"
        assert "s3cret" not in said, f"the proxy password is in {said!r}"
        assert "buyer" not in said
        assert "proxy.example.com:8080" in said, "and the host is still named"


class _Nothing:
    def __enter__(self) -> _Nothing:
        return self

    def __exit__(self, *_: object) -> None:
        return None
