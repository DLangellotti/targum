"""Turn a built video targum into a shelf entry the box can read.

Private in the way `recording.attach` is private: this makes content, and content does
not enter the repository. What it does not do is spend anything or fetch anything — the
video was fetched, cut and translated by an ordinary `targum build --video`, and this
copies the four things out of that folder which the box cannot make for itself, plus the
one thing no build knows: who made the video and under what licence.

Everything else the box makes again for free. Segmentation is deterministic and does not
read the source, so a document carried here and re-segmented on the box comes back with
the segment ids it was built with — which is what lets the shipped spans and the shipped
English go on fitting it.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from ..errors import TargumError
from ..models import Document, Translation, read_artifact
from ..paths import write_atomic
from . import store, youtube


def _translation(folder: Path) -> Translation | None:
    """The English this build bought, or None.

    The same rule `warm` uses to tell a bought translation from a matched one: an
    aligned rendering is a published translation someone else wrote, and it belongs to
    that publisher rather than to the shelf.
    """
    for path in sorted((folder / "translations").glob("*.json")):
        held = read_artifact(Translation, path)
        if held is not None and held.provider != "aligned" and held.target_language == "en":
            return held
    return None


def curate(
    built: Path,
    *,
    credit: str,
    licence: str = "",
    licence_url: str = "",
    identifier: str = "",
    into: Path | None = None,
) -> Path:
    """Write one built video into the curated shelf, and return where it landed.

    Refuses rather than half-writes. A shelf entry that reaches the box without its
    reel, its English or its credit is a catalogue row that renders wrong for every
    reader, and the cheapest place to find that out is here.
    """
    from ..audio import manifest as manifest_module

    if not credit.strip():
        # First, before anything is read. Not a default and not derivable: a CC BY
        # video published without naming its maker is a licence breach, and this is
        # the one place it can be caught. It is also the only argument the caller got
        # wrong rather than the disk, so it is the one worth saying first.
        raise TargumError("A curated video has to say who made it.", "Pass --credit.")

    document = read_artifact(Document, built / "document.json")
    if document is None:
        raise TargumError(f"No document in {built}.", "Give the folder a `targum build` wrote.")
    kept = manifest_module.load(built)
    if kept is None:
        raise TargumError(f"No {manifest_module.MANIFEST} in {built}.", "That is not an import.")
    if not any(part.video for part in kept.parts):
        raise TargumError(
            "That import kept no pictures.", "Build it again with --video, or curate it as audio."
        )
    english = _translation(built)
    if english is None:
        raise TargumError(f"No English in {built}.", "The shelf carries the translation with it.")
    home = youtube.watch_url(kept.home)
    name = identifier or youtube.video_id(kept.home)
    if not name:
        raise TargumError(
            "That video has no id to file it under.",
            "It was not fetched from YouTube, so pass --id.",
        )

    folder = (into or store.root()) / name
    (folder / "audio" / "parts").mkdir(parents=True, exist_ok=True)

    # The source is rewritten and nothing else is. The body is untouched, so the content
    # hash, the segment ids and every key hung off them survive the move — which is the
    # whole reason this is a copy rather than a rebuild.
    document.source = f"video:{name}"
    document.write(folder / store.DOCUMENT)
    english.write(folder / store.ENGLISH)

    # Verbatim, because its part paths are relative to the folder it sits in and the
    # layout under it is reproduced exactly. Rewriting them would be one more thing that
    # can be wrong on a box and right on a laptop.
    shutil.copy2(built / manifest_module.MANIFEST, folder / manifest_module.MANIFEST)
    for part in kept.parts:
        for named in (part.audio, part.video):
            if named and (built / named).is_file():
                target = folder / named
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(built / named, target)

    write_atomic(
        folder / store.CURATED,
        store.Curated(
            id=name,
            title=document.title or "",
            home=home,
            credit=credit.strip(),
            licence=licence.strip(),
            licence_url=licence_url.strip(),
        ).model_dump_json(indent=2)
        + "\n",
    )
    return folder
