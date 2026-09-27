"""The nightly backup and the health watch, read off the files that install them.

There is no way to test a timer without a box, and the failure this pins needed no box
to find: it was visible in the text of the command all along. From the day the box went
up until 2026-09-04, every nightly copy was a database holding 0 accounts and 0 words,
because the cron line named no `--store` and `targum backup` falls back to the HOME
default. It said "checked" and exited 0 each time. It had faithfully copied the wrong
file.

The cron line became `deploy/targum-backup.service` on 2026-09-27 (targum-internal#16),
so a deploy carries it; the assertions moved with it.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

DEPLOY = Path(__file__).resolve().parent.parent / "deploy"


def unit(name: str) -> dict[str, list[str]]:
    """A unit file's keys, continuation lines joined, comments dropped."""
    text = re.sub(r"\\\n\s*", " ", (DEPLOY / name).read_text(encoding="utf-8"))
    found: dict[str, list[str]] = {}
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith(("#", "[")):
            continue
        key, _, value = line.partition("=")
        found.setdefault(key.strip(), []).append(value.strip())
    return found


@pytest.fixture(scope="module")
def nightly() -> dict[str, list[str]]:
    return unit("targum-backup.service")


def test_the_nightly_backup_names_the_database_it_copies(nightly: dict[str, list[str]]) -> None:
    """The whole bug, in one assertion.

    `targum backup` defaults `--store` to `~/.targum/targum.db`. On the box that path is
    an empty leftover and the live database is at /var/lib/targum/targum.db, so a line
    without `--store` copies nothing anybody would want and reports success.
    """
    (command,) = nightly["ExecStart"]
    assert "targum backup" in command
    assert "--store /var/lib/targum/targum.db" in command, "it copies the live database"


def test_the_nightly_backup_can_see_the_cache(nightly: dict[str, list[str]]) -> None:
    """The cache is the second thing that cannot be rebuilt. Its location comes from
    TARGUM_CACHE_DIR in the service's EnvironmentFile, and so do the off-box settings
    and the remote's credentials; a run without that file archives nothing, silently."""
    assert nightly["EnvironmentFile"] == ["/etc/targum/targum.env"]
    assert nightly["User"] == ["targum"]


def test_a_failed_night_leaves_a_trace(nightly: dict[str, list[str]]) -> None:
    """A unit's output goes to the journal. Nothing may throw it away first."""
    assert not re.search(r">\s*/dev/null", nightly["ExecStart"][0])
    assert "StandardOutput" not in nightly and "StandardError" not in nightly


def test_the_timers_keep_their_hours() -> None:
    assert unit("targum-backup.timer")["OnCalendar"] == ["*-*-* 04:00:00 UTC"]
    assert unit("targum-backup.timer")["Persistent"] == ["true"]
    assert unit("targum-health.timer")["OnCalendar"] == ["*:0/5"]
    health = unit("targum-health.service")
    assert "targum watch-health" in health["ExecStart"][0]
    assert health["EnvironmentFile"] == ["/etc/targum/targum.env"], "it mails through SMTP"


def test_every_deploy_carries_the_units_and_retires_the_cron_line() -> None:
    """Enabled before the cron line goes, so there is no night with neither."""
    script = (DEPLOY / "deploy.sh").read_text(encoding="utf-8")
    for name in (
        "targum-backup.service",
        "targum-backup.timer",
        "targum-health.service",
        "targum-health.timer",
    ):
        assert f"deploy/{name}" in script, f"deploy.sh does not ship {name}"
    enabled = script.index("systemctl enable --now --quiet targum-backup.timer")
    retired = script.index("rm -f /etc/cron.d/targum-backup")
    assert enabled < retired


def test_provision_writes_no_cron_backup_either() -> None:
    """A fresh box and a deployed one run the backup the same way."""
    text = (DEPLOY / "provision.sh").read_text(encoding="utf-8")
    assert "cat > /etc/cron.d/targum-backup" not in text
    assert "targum-backup.timer" in text


def test_the_vault_filter_keeps_names_with_digits() -> None:
    """rclone's remote settings are RCLONE_CONFIG_<NAME>_*; a filter of [A-Z_] alone
    dropped every such line whose name held a digit, with nothing said."""
    script = (DEPLOY / "deploy.sh").read_text(encoding="utf-8")
    (pattern,) = re.findall(r"grep -E '(\^\[A-Z_\][^']*)'", script)
    assert re.match(pattern, "RCLONE_CONFIG_B2_KEY=x")


def test_a_deploy_installs_the_extras_ci_checks_with_before_it_checks() -> None:
    """A deploy runs from a fresh worktree, whose `.venv` had no extras, and its mypy
    then failed on PIL, pypdf and mcp — twice (2026-09-14, 2026-09-27). The extras are
    read from CI's own workflow, so the two lists cannot drift."""
    import subprocess

    script = (DEPLOY / "deploy.sh").read_text(encoding="utf-8")
    line = next(line for line in script.splitlines() if line.startswith("EXTRAS="))
    root = DEPLOY.parent
    got = subprocess.run(
        ["bash", "-c", f'{line}; echo "$EXTRAS"'],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    assert got[::2] == ["--extra"] * (len(got) // 2) and len(got) >= 2
    extras = set(got[1::2])
    assert {"difficulty", "covers", "bring", "mcp"} <= extras, extras
    sync = script.index("check uv sync --frozen --inexact $EXTRAS")
    assert sync < script.index("check uv run mypy"), "synced before anything is checked"


def test_the_box_reads_russian_itself() -> None:
    """targum-internal#310, switched on 2026-09-27: the box installs the russian extra and
    fetches its lemmatizer at deploy, so Russian is read there for nothing rather than
    bought per sentence, and never waits on a download at a reader's first build."""
    script = (DEPLOY / "deploy.sh").read_text(encoding="utf-8")
    install = next(line for line in script.splitlines() if "uv tool install --force" in line)
    assert "russian" in install.split("[", 1)[1].split("]", 1)[0].split(",")
    fetch = script.index("targum models fetch ru\n")
    assert (
        script.index("uv tool install --force") < fetch < script.index("targum rebuild --words")
    ), "fetched after the wheel is in and before the rebuild re-reads Russian"


def test_a_deploy_reads_the_vault_as_the_service_account_when_it_can() -> None:
    """David, 2026-09-27: a deploy need not wait for somebody at the fingerprint reader.
    Like weekly-run.sh, it takes the targum-box service account's token from the login
    keychain before op resolves anything, and never replaces a token already set."""
    script = (DEPLOY / "deploy.sh").read_text(encoding="utf-8")
    lookup = script.index("security find-generic-password -s targum-op-service-account -w")
    assert script.index('[ -z "${OP_SERVICE_ACCOUNT_TOKEN:-}" ]') < lookup
    assert lookup < script.index("op inject -i deploy/box.env.op"), "before the vault is read"
    weekly = (DEPLOY / "weekly-run.sh").read_text(encoding="utf-8")
    assert "targum-op-service-account" in weekly, "the same item the weekly reads"
