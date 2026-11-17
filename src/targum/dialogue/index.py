"""Where the dialogues are.

Named in the environment, the way the weekly and the catalogue are, and defaulting inside
`targum-out/` — which is gitignored, because the scenes are content and content does not
enter the repository.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from ..errors import OffHere, UnsupportedSource
from .models import Dialogue


def root() -> Path:
    named = os.environ.get("TARGUM_DIALOGUE_DIR", "").strip()
    if named:
        return Path(named).expanduser()
    return Path.cwd() / "targum-out" / "dialogues"


#: What a shelf's file may be called (qa on targum#1306): every dialogue id on the laptop
#: and the box fits (381 of 381, 2026-11-17), Russian's slugs included, which are English.
#: Anything else, `../outside` above all, would read a file off the shelf: `dialogue:` and
#: `story:` are addressable from Add and the chat.
SHELF_ID = re.compile(r"[a-z0-9-]+")


def checked(identifier: str, what: str = "dialogue") -> str:
    """The identifier, if it names a file on a shelf and nothing outside it."""
    if not SHELF_ID.fullmatch(identifier):
        raise UnsupportedSource(
            f"There is no {what} called {identifier}.",
            f"A {what}'s name is lower-case letters, digits and hyphens.",
        )
    return identifier


def path_for(identifier: str) -> Path:
    return root() / f"{checked(identifier)}.json"


def load(identifier: str) -> Dialogue:
    path = path_for(identifier)
    if not path.exists():
        known = ", ".join(sorted(p.stem for p in root().glob("*.json"))[:6]) or "none yet"
        # The shelf's own copy is missing on this machine: the operator's to fix, and
        # said to a reader on a hosted box as their sentence, with this path in the log
        # rather than on the card (QA 2026-10-11).
        raise OffHere(
            f"There is no dialogue called {identifier}.",
            f"Looked in {root()}. Dialogues there: {known}.",
            key="shelf.unavailable",
        )
    return Dialogue.model_validate(json.loads(path.read_text(encoding="utf-8")))


def every() -> list[Dialogue]:
    """Every dialogue on the shelf, in reading order — by level, then by name."""
    out = [load(p.stem) for p in sorted(root().glob("*.json"))]
    return sorted(out, key=lambda d: (d.level, d.id))
