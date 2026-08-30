"""Where the recordings are.

Named in the environment, the way the dialogues and the catalogue are, and defaulting
inside `targum-out/` — which is gitignored, because a recording is content.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from .models import Recording

#: One folder per work: the recording beside the files it names.
MANIFEST = "recording.json"


def root() -> Path:
    named = os.environ.get("TARGUM_RECORDING_DIR", "").strip()
    if named:
        return Path(named).expanduser()
    return Path.cwd() / "targum-out" / "recordings"


def slug(source: str) -> str:
    """A folder name from a document's source.

    `sefaria:Ruth` is a folder called `sefaria-ruth`. Lowercased and reduced to letters,
    digits and hyphens, so the same text keys identically on a case-insensitive disk and
    a case-sensitive one — a folder that resolves on a laptop and not on the box is a
    reader that is silent in production and fine in testing.
    """
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", source.lower())).strip("-")


def folder(source: str) -> Path:
    return root() / slug(source)


def load(source: str) -> Recording | None:
    """The recording for a text, or None where there is none.

    None rather than an error: most texts have no recording, and a library that raised
    here would be a library where adding audio to one book breaks every other.
    """
    path = folder(source) / MANIFEST
    if not path.exists():
        return None
    try:
        return Recording.model_validate(json.loads(path.read_text(encoding="utf-8")))
    except Exception:  # noqa: BLE001 - a malformed recording must not stop a build
        return None
