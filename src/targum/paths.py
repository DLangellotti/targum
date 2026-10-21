"""Where targum keeps its cache, its language models, and its config."""

from __future__ import annotations

import os
from pathlib import Path


def _base(env: str, default: Path) -> Path:
    raw = os.environ.get(env)
    return Path(raw).expanduser() if raw else default


def cache_dir() -> Path:
    """Translation cache and downloaded models. Safe to delete at any time."""
    root = _base("TARGUM_CACHE_DIR", _base("XDG_CACHE_HOME", Path.home() / ".cache"))
    return root if os.environ.get("TARGUM_CACHE_DIR") else root / "targum"


def model_dir() -> Path:
    """Language models. Hundreds of megabytes each, so they outlive `cache clear`
    and can be pointed somewhere with room via TARGUM_MODEL_DIR."""
    override = os.environ.get("TARGUM_MODEL_DIR")
    return Path(override).expanduser() if override else cache_dir() / "models"


def hf_home() -> Path:
    """Where the Hugging Face cache lives: beside the language models, so one directory is
    the whole of what a box has to be given.

    The one place this is said (2026-10-07, targum-internal#426). targum.service set
    `HF_HOME` to models/huggingface while the code defaulted to models/hf, and deploy.sh's
    `systemd-run` steps read the env file but not the unit, so the service and every
    rebuild kept a copy of dictabert-joint each, in two folders.
    """
    return model_dir() / "hf"


def settle_hf_home() -> None:
    """Point the Hugging Face libraries at `hf_home()` unless somebody already chose.

    Before anything imports `huggingface_hub`, which reads `HF_HOME` once, at import: set
    after that, it is not read at all, and the cache lands under $HOME — read-only on the
    box. So every command does it first (`cli._root`), and each loader again for a caller
    that came in without the CLI. An `HF_HOME` already in the environment is kept: a laptop
    that keeps its own Hugging Face cache elsewhere is not moved.
    """
    os.environ.setdefault("HF_HOME", str(hf_home()))


def config_path() -> Path:
    root = _base("XDG_CONFIG_HOME", Path.home() / ".config")
    return root / "targum" / "config.toml"


def ensure(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_atomic(path: Path, text: str) -> Path:
    """Write it whole, or not at all.

    Anything a second reader or a second process may open while it is being written
    needs this. Writing beside the target and renaming makes every read see one
    complete version or the previous one; rename is atomic within a directory on
    every platform targum runs on. The pid in the temporary name is what keeps two
    writers from tearing each other's.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(text, encoding="utf-8")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    return path
