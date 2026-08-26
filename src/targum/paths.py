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
