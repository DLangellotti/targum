"""One Hugging Face folder on the box, whichever way targum was started (targum-internal#426).

targum.service set `HF_HOME` to models/huggingface; deploy.sh's `systemd-run` steps read
the env file but not the unit and fell to the code's default, models/hf. So the service
and every rebuild each kept a copy of dictabert-joint (2026-10-07). The folder is now said
once, in `paths.hf_home()`, set by `targum` itself before any command runs, and set by
nothing in deploy/.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

from targum import cli, paths
from targum.vocalize import dicta as menaked

ROOT = Path(__file__).resolve().parent.parent


def _unset_hf_home(monkeypatch: pytest.MonkeyPatch) -> None:
    # Set and then deleted, so monkeypatch puts back whatever was there before, set or not.
    monkeypatch.setenv("HF_HOME", "placeholder")
    monkeypatch.delenv("HF_HOME")


def test_the_folder_is_beside_the_models(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TARGUM_MODEL_DIR", str(tmp_path / "models"))
    assert paths.hf_home() == tmp_path / "models" / "hf"
    assert menaked.hub_root() == paths.hf_home(), "the menaked keeps no folder of its own"


def test_settling_sets_it_where_nothing_has(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TARGUM_MODEL_DIR", str(tmp_path / "models"))
    _unset_hf_home(monkeypatch)
    paths.settle_hf_home()
    assert os.environ["HF_HOME"] == str(tmp_path / "models" / "hf")


def test_settling_keeps_one_already_chosen(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TARGUM_MODEL_DIR", str(tmp_path / "models"))
    monkeypatch.setenv("HF_HOME", str(tmp_path / "elsewhere"))
    paths.settle_hf_home()
    assert os.environ["HF_HOME"] == str(tmp_path / "elsewhere")


def test_every_command_starts_with_it_set(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The service (`targum serve`) and deploy.sh's steps (`targum rebuild`, `targum seed`,
    `targum models fetch`) all start at `main`, so all of them see the same folder before a
    command imports anything that reads it."""
    monkeypatch.setenv("TARGUM_MODEL_DIR", str(tmp_path / "models"))
    _unset_hf_home(monkeypatch)
    seen: list[str | None] = []
    monkeypatch.setattr(cli, "app", lambda: seen.append(os.environ.get("HF_HOME")))
    cli.main()
    assert seen == [str(tmp_path / "models" / "hf")]


def test_nothing_in_deploy_sets_another() -> None:
    """An `HF_HOME` in the unit, the env file or a `systemd-run --setenv` would split the
    folder again: setting it is `targum`'s, and only where nothing has."""
    setting = re.compile(r"^(?!\s*#).*HF_HOME\s*=", re.M)
    found = [
        f"{path.relative_to(ROOT)}: {match.group(0).strip()}"
        for path in sorted((ROOT / "deploy").rglob("*"))
        if path.is_file()
        for match in setting.finditer(path.read_text(encoding="utf-8", errors="replace"))
    ]
    assert found == []
