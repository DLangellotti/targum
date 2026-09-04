"""Where the curated videos are: the shelf a `video:` source is resolved against.

The third content store, beside the recordings and the dialogues, and here for a reason
neither of those has. `Library.prepare` refuses a YouTube address by name — YouTube
throttles datacenter addresses and yt-dlp breaks on YouTube's schedule, so a hosted door
would be a pager (targum-internal#136, and that decision stands). A catalogue row whose
source was a watch URL would therefore fail on the box every time a reader pressed
build. So a curated video is fetched, cut and translated on a laptop and carried here,
and the box resolves `video:<id>` against this folder without reaching the network at
all.

What is kept is what the box cannot make for itself:

    <root>/<id>/video.json      who made it, under what licence, and where it lives
    <root>/<id>/document.json   the text, with `source` already `video:<id>`
    <root>/<id>/english.json    the translation, bought once by the operator
    <root>/<id>/audio.json      the import manifest, verbatim
    <root>/<id>/audio/parts/…   the cut mp3 and the 480p mp4 it names

Segmentation is not kept, and does not need to be: it is deterministic, free, and does
not read the source — a document carried here and re-segmented on the box comes back
with the same segment ids it was built with, which is what lets the shipped spans and
the shipped English go on matching.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from pydantic import BaseModel

from ..models import Document, Translation, read_artifact

#: The record that says what the box may print about a video it did not fetch.
CURATED = "video.json"
#: The text, as it was ingested from the soundtrack. `source` is already `video:<id>`.
DOCUMENT = "document.json"
#: The English, which arrives with the video and is never bought again.
ENGLISH = "english.json"


class Curated(BaseModel):
    """A video the operator chose, and the three facts a page has to state about it.

    Not derived and not guessed. `credit` and `licence` are checked by hand before the
    fetch and written down here, which is the whole difference between this and a
    reader's own upload: `builder._imported` prints neither, on the grounds that a
    licence targum cannot verify is one it must not print. Here it can, so here it does.
    """

    #: The video's own id, which is also the folder's name and the second half of the
    #: source. YouTube's for a YouTube video, so a curated shelf can be checked against
    #: the addresses it was drawn from.
    id: str
    #: The title as the page shows it. Kept beside the document rather than read out of
    #: it, so a listing can be printed without loading every text.
    title: str = ""
    #: The canonical address the video lives at, or "" for one with no home. Written
    #: through `youtube.watch_url` at curation, so the page's one outbound link is the
    #: one shape `test_render.OUTBOUND` pins.
    home: str = ""
    #: Who made it, named on the page. Never empty for a curated video: a video used
    #: under CC BY that names nobody is a licence breach, and the curation refuses it.
    credit: str
    #: The licence as it is written — "CC BY 3.0".
    licence: str = ""
    #: Where that licence can be read. Left empty rather than guessed, for the reason
    #: `Recording.licence_url` records: a wrong licence link is worse than none.
    licence_url: str = ""


def root() -> Path:
    named = os.environ.get("TARGUM_VIDEO_DIR", "").strip()
    if named:
        return Path(named).expanduser()
    return Path.cwd() / "targum-out" / "videos"


def folder(identifier: str) -> Path:
    return root() / identifier


def load(identifier: str) -> Curated | None:
    """What may be said about this video, or None where there is no such video.

    None rather than an error, the way `recording.index.load` answers: a shelf that is
    not on this machine is not a broken build, and every caller here has something
    sensible to do with nothing.
    """
    path = folder(identifier) / CURATED
    if not path.is_file():
        return None
    try:
        return Curated.model_validate(json.loads(path.read_text(encoding="utf-8")))
    except Exception:  # noqa: BLE001 - a malformed record must not stop a build
        return None


def document(identifier: str) -> Document | None:
    return read_artifact(Document, folder(identifier) / DOCUMENT)


def english(identifier: str) -> Translation | None:
    return read_artifact(Translation, folder(identifier) / ENGLISH)


def every() -> list[str]:
    """Every curated video on this machine, by id, in name order.

    A folder without a `video.json` is not one: a half-copied shelf is a thing that
    happens mid-rsync, and a video nothing can be said about is one the shelf must not
    claim to have.
    """
    home = root()
    if not home.is_dir():
        return []
    return sorted(child.name for child in home.iterdir() if (child / CURATED).is_file())
