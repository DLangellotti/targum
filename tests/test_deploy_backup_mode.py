"""Database copies on the box are 0600 targum, read off the files that make them.

Until targum-internal#514 every copy, the deploy's `before-<sha12>` one and the nightly
fourteen alike, was written under the default umask and came out 0644: reader data any
account on the box could open. A umask is invisible in a listing until somebody looks,
so the text that sets it is pinned here.
"""

from __future__ import annotations

import re
from pathlib import Path

DEPLOY = Path(__file__).resolve().parent.parent / "deploy"


def test_the_deploy_copy_is_made_under_umask_0077() -> None:
    script = (DEPLOY / "deploy.sh").read_text(encoding="utf-8")
    joined = re.sub(r"\\\n\s*", " ", script)
    (backup,) = [
        line for line in joined.splitlines() if "systemd-run" in line and ".backup '" in line
    ]
    assert "--uid=targum" in backup, "made by the service account, so the copy is targum's"
    assert "-p UMask=0077" in backup, "the copy holds reader data: 0600, never 0644"


def test_the_nightly_copies_are_made_under_umask_0077() -> None:
    text = (DEPLOY / "targum-backup.service").read_text(encoding="utf-8")
    service = text.split("[Service]", 1)[1]
    assert re.search(r"^UMask=0077$", service, re.MULTILINE)
    assert re.search(r"^User=targum$", service, re.MULTILINE)


def test_the_hand_copies_in_the_rollback_are_0600_too() -> None:
    """Step 3b and step 4c take a copy by hand as targum; each is chmodded straight after."""
    doc = (DEPLOY / "ROLLBACK.md").read_text(encoding="utf-8")
    assert "'.backup $COPY' && chmod 0600 $COPY" in doc
    assert "chmod 0600 /var/lib/targum/targum.db.before-restore-$STAMP" in doc
