"""The nightly backup, read off `provision.sh` rather than run.

There is no way to test a cron line without a box, and the failure this pins needed no
box to find: it was visible in the text of the command all along. From the day the box
went up until 2026-09-04, every nightly copy was a database holding 0 accounts and 0
words, because the line named no `--store` and `targum backup` falls back to the HOME
default. It said "checked" and exited 0 each time. It had faithfully copied the wrong
file.

So this reads the line and asserts the two things whose absence made it lie.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

PROVISION = Path(__file__).resolve().parent.parent / "deploy" / "provision.sh"


@pytest.fixture(scope="module")
def cron() -> str:
    """The `targum backup` line `provision.sh` writes into /etc/cron.d."""
    text = PROVISION.read_text(encoding="utf-8")
    lines = [
        line
        for line in text.splitlines()
        if "targum backup" in line and not line.lstrip().startswith("#")
    ]
    assert lines, "provision.sh writes no nightly backup line"
    schedule = [line for line in lines if re.match(r"^[\d*]", line.strip())]
    assert len(schedule) == 1, f"expected one scheduled backup, found {len(schedule)}"
    return schedule[0]


def test_the_nightly_backup_names_the_database_it_copies(cron: str) -> None:
    """The whole bug, in one assertion.

    `targum backup` defaults `--store` to `~/.targum/targum.db`. On the box that path is
    an empty leftover and the live database is at /var/lib/targum/targum.db, so a line
    without `--store` copies nothing anybody would want and reports success.
    """
    assert "--store" in cron, "the nightly backup does not say which database to copy"
    assert "/var/lib/targum/targum.db" in cron, "it copies a database that is not the live one"


def test_the_nightly_backup_can_see_the_cache(cron: str) -> None:
    """The cache is the second thing that cannot be rebuilt: it is what makes a public
    text free for the second reader and every reader after. Its location comes from
    TARGUM_CACHE_DIR in the service's EnvironmentFile, and a copy run without that file
    looks in an empty directory and archives nothing — silently, the same way."""
    assert "EnvironmentFile=/etc/targum/targum.env" in cron, (
        "the nightly backup runs without the service's environment, so it cannot find the cache"
    )


def test_a_failed_night_leaves_a_trace(cron: str) -> None:
    """There is no MTA on the box, so cron discards whatever a job prints — two failed
    nights left nothing anywhere. Going through `systemd-run` puts it in the journal
    instead, which is the only reason anybody can find out tomorrow what happened last
    night."""
    assert "systemd-run" in cron, "output goes nowhere a person can read it"
    assert not re.search(r">\s*/dev/null", cron), "the nightly backup throws its own output away"
