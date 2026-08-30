"""Where the dialogues are.

Named in the environment, the way the weekly and the catalogue are, and defaulting inside
`targum-out/` — which is gitignored, because the scenes are content and content does not
enter the repository.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from ..errors import TargumError
from .models import Dialogue


def root() -> Path:
    named = os.environ.get("TARGUM_DIALOGUE_DIR", "").strip()
    if named:
        return Path(named).expanduser()
    return Path.cwd() / "targum-out" / "dialogues"


def path_for(identifier: str) -> Path:
    return root() / f"{identifier}.json"


def load(identifier: str) -> Dialogue:
    path = path_for(identifier)
    if not path.exists():
        known = ", ".join(sorted(p.stem for p in root().glob("*.json"))[:6]) or "none yet"
        raise TargumError(
            f"There is no dialogue called {identifier}.",
            f"Looked in {root()}. Dialogues there: {known}.",
        )
    return Dialogue.model_validate(json.loads(path.read_text(encoding="utf-8")))


def every() -> list[Dialogue]:
    """Every dialogue on the shelf, in reading order — by level, then by name."""
    out = [load(p.stem) for p in sorted(root().glob("*.json"))]
    return sorted(out, key=lambda d: (d.level, d.id))
