"""A content-addressed cache. Translation costs money, so nothing is paid for twice."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from .ids import content_hash
from .models import SCHEMA_VERSION
from .paths import cache_dir, write_atomic


class Cache:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or cache_dir()

    def key(self, stage: str, **parts: Any) -> str:
        """Content plus every option that could change the answer, plus the schema."""
        payload = json.dumps(parts, sort_keys=True, ensure_ascii=False, default=str)
        return content_hash(str(SCHEMA_VERSION), stage, payload)

    def _path(self, stage: str, key: str) -> Path:
        return self.root / stage / key[:2] / f"{key}.json"

    def get(self, stage: str, key: str) -> Any | None:
        path = self._path(stage, key)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None

    def put(self, stage: str, key: str, value: Any) -> None:
        """Whole or not at all, because a torn entry reads as a miss and a miss is
        paid for a second time. Warm workers share this directory."""
        write_atomic(self._path(stage, key), json.dumps(value, ensure_ascii=False))

    def clear(self) -> int:
        """Drop cached work but keep downloaded language models."""
        removed = 0
        if not self.root.exists():
            return 0
        for child in self.root.iterdir():
            if child.name == "models":
                continue
            removed += sum(1 for _ in child.rglob("*.json")) if child.is_dir() else 1
            shutil.rmtree(child) if child.is_dir() else child.unlink()
        return removed
