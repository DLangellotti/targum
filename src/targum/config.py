"""Defaults from a config file. Secrets never live here, only in the environment."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

from .errors import TargumError
from .models import Style
from .paths import config_path

DEFAULT_PROVIDER = "anthropic"


@dataclass(slots=True)
class Config:
    provider: str = DEFAULT_PROVIDER
    model: str | None = None
    style: Style = Style.natural
    out: str | None = None
    batch_size: int = 20
    effort: str = "medium"


def load(path: Path | None = None) -> Config:
    path = path or config_path()
    if not path.exists():
        return Config()
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise TargumError(f"Config file is not valid TOML: {path}", str(exc)) from exc

    for secret in ("api_key", "anthropic_api_key", "key", "token"):
        if secret in raw:
            raise TargumError(
                f"Remove '{secret}' from {path}. Secrets belong in the environment.",
                "export ANTHROPIC_API_KEY=... instead",
            )

    cfg = Config()
    if isinstance(style := raw.get("style"), str):
        cfg.style = Style(style)
    for field in ("provider", "model", "out", "effort"):
        if isinstance(value := raw.get(field), str):
            setattr(cfg, field, value)
    if isinstance(size := raw.get("batch_size"), int) and size > 0:
        cfg.batch_size = size
    return cfg
