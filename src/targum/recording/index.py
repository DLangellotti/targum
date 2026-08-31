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

    A source with a Hebrew title in it loses the title to that reduction, and every
    `wikisource:he:` text then keys the same folder — so what the reduction drops, a
    hash of the whole source puts back. ASCII-only sources keep the folders they have:
    the Tanakh recordings are already on the box under these names.
    """
    reduced = re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", source.lower())).strip("-")
    # Asked directly, not inferred from what the reduction dropped: an underscore is
    # `\w` but not `[a-z0-9]`, and inferring made every ASCII source with one — half
    # the wikisource URLs — grow a hash and quietly re-key a folder already on the box.
    if not source.isascii():
        import hashlib

        reduced = f"{reduced}-{hashlib.sha256(source.encode('utf-8')).hexdigest()[:8]}"
    return reduced


def folder(source: str) -> Path:
    return root() / slug(source)


def load_folder(folder: Path) -> Recording | None:
    """The recording in a folder, or None where it will not read.

    Split out so a caller walking the whole directory does not have to work out which
    source each folder is the slug of — a slug is not reversible, and guessing at it is
    how a book comes to be listed under a name nothing else uses.
    """
    path = folder / MANIFEST
    if not path.exists():
        return None
    try:
        return Recording.model_validate(json.loads(path.read_text(encoding="utf-8")))
    except Exception:  # noqa: BLE001 - a malformed recording must not stop a build
        return None


def load(source: str) -> Recording | None:
    """The recording for a text, or None where there is none.

    None rather than an error: most texts have no recording, and a library that raised
    here would be a library where adding audio to one book breaks every other. The
    manifest's own source has the last word — a folder reached by the wrong slug must
    not hand one text the sound of another.
    """
    recording = load_folder(folder(source))
    if recording is not None and recording.source != source:
        return None
    return recording
