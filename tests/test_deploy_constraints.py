"""The box installs what CI tested: deploy.sh pins the tool to uv.lock.

`uv tool install` resolves a wheel's requirements fresh and never reads the lockfile, so a
requirement with only a floor took whatever PyPI had on deploy day. transformers 5.17.0
broke every Hebrew build on 2026-09-13 and stanza 1.15.0 stopped the rebuild at the first
Russian text on 2026-10-01, both with CI green on the lockfile's versions. deploy.sh now
exports the lockfile as constraints and installs with them; what is pinned here is that
the install uses them, that they hold the lockfile's versions, and that torch, which the
box takes from PyTorch's CPU index as a build CI never sees, is left to that index.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "deploy" / "deploy.sh"


def text() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def test_the_install_on_the_box_is_constrained() -> None:
    install = re.search(r"/usr/local/bin/uv tool install[^\n]*\n(?:[^\n]*\\\n)*[^\n]*", text())
    assert install, "deploy.sh no longer installs the tool with uv"
    assert "--constraints" in install.group(0), install.group(0)


def test_the_extras_exported_are_the_extras_installed() -> None:
    script = text()
    extras = re.search(r'^BOX_EXTRAS="([^"]+)"', script, re.M)
    assert extras, "deploy.sh no longer names the box's extras once"
    assert "${REMOTE_EXTRAS}" in script and "$BOX_EXTRAS" in script
    declared = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    known = set(declared["project"]["optional-dependencies"])
    assert set(extras.group(1).split()) <= known


def left_out() -> re.Pattern[str]:
    found = re.search(r"grep -vE '([^']+)' > \"\$CONSTRAINTS\"", text())
    assert found, "deploy.sh no longer filters the export"
    return re.compile(found.group(1))


@pytest.mark.skipif(shutil.which("uv") is None, reason="uv is what deploy.sh exports with")
def test_the_constraints_hold_the_lockfile_and_leave_torch_to_its_index() -> None:
    extras = re.search(r'^BOX_EXTRAS="([^"]+)"', text(), re.M)
    assert extras
    command = ["uv", "export", "--frozen", "--no-hashes", "--no-emit-project", "--no-header"]
    command += ["--no-annotate"]
    for extra in extras.group(1).split():
        command += ["--extra", extra]
    exported = subprocess.run(
        command, cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.splitlines()
    skip = left_out()
    kept = [line for line in exported if line and not skip.search(line)]
    names = {re.split(r"[=; @]", line, maxsplit=1)[0] for line in kept}
    assert {"stanza", "transformers", "numpy"} <= names
    assert not {"torch", "triton", "ru-core-news-lg"} & names
    assert not any(name.startswith("nvidia-") for name in names)
    # Every kept line is an exact pin, so nothing on the box can drift past it.
    for line in kept:
        assert re.match(r"^[A-Za-z0-9_.-]+==[^ ;]+", line), line
