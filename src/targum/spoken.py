"""Which texts can be listened to.

Asked of the disk rather than written down in the catalogue. A recording is content: it
is cut on a laptop and copied to the box, and the two can disagree for the length of a
deploy. An entry that claims audio the box has not got sends a reader to a page with no
player on it and nothing to explain the difference — so the claim is made by whatever is
actually there.

Cached, because it is a directory listing asked once per library page and a recording
folder only changes when somebody copies one in, which on a box means a restart. Same
reasoning as the catalogue's own read.
"""

from __future__ import annotations

from collections.abc import Callable
from functools import cache
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .audio.manifest import ManifestPart


@cache
def sources() -> frozenset[str]:
    """Every source with any audio at all: a dialogue, or a recording of a book.

    A book counts when any chapter of it was recorded. Be'eri's Isaiah stops at chapter
    37 and his Psalms leaves out fifty of them, and both are still worth finding when
    somebody is looking for something to listen to — the reader shows which chapters have
    a recitation, and the library is where you go to find the book at all.
    """
    from .dialogue import index as dialogue_index
    from .recording import index as recording_index

    found: set[str] = set()
    try:
        for scene in dialogue_index.every():
            if scene.voiced:
                found.add(f"dialogue:{scene.id}")
    except Exception:  # noqa: BLE001 - a shelf that is not there is not an error
        pass
    found |= _curated(lambda part: bool(part.audio))
    try:
        for folder in recording_index.root().iterdir():
            if not (folder / recording_index.MANIFEST).is_file():
                continue
            recording = recording_index.load_folder(folder)
            if recording is not None and recording.parts:
                found.add(recording.source)
    except Exception:  # noqa: BLE001 - likewise
        pass
    return frozenset(found)


def _curated(wanted: Callable[[ManifestPart], bool]) -> set[str]:
    """Every curated video whose manifest holds a part answering `wanted`.

    The third shelf, and the one that does not keep a `Recording`: a video's timing is
    per segment, cut from its own subtitle track, where a `Recording` addresses a part
    by verse or by block. So the claim is read off the import manifest the curation
    shipped — the same file, and the same question, as `manifest.keeps_video`.
    """
    from .audio import manifest as manifest_module
    from .video import store as video_store

    found: set[str] = set()
    try:
        for identifier in video_store.every():
            kept = manifest_module.load(video_store.folder(identifier))
            if kept is not None and any(wanted(part) for part in kept.parts):
                found.add(f"video:{identifier}")
    except Exception:  # noqa: BLE001 - a shelf that is not there is not an error
        pass
    return found


def is_spoken(source: str) -> bool:
    return source in sources()


@cache
def video_sources() -> frozenset[str]:
    """Every source whose recording kept its pictures: a subset of `sources()`.

    Two shelves answer, because two things can hold a picture. A `Recording` may carry
    a video part beside its audio — nothing in the library does yet, and this still
    reads the disk rather than answering no, so the day one arrives the shelf says so
    with no code changed. A curated video always does, and is why this stopped being
    hypothetical: it is what puts the chip on a catalogue row.
    """
    from .recording import index as recording_index

    found: set[str] = set()
    try:
        for folder in recording_index.root().iterdir():
            if not (folder / recording_index.MANIFEST).is_file():
                continue
            recording = recording_index.load_folder(folder)
            if recording is not None and any(part.video for part in recording.parts):
                found.add(recording.source)
    except Exception:  # noqa: BLE001 - a shelf that is not there is not an error
        pass
    return frozenset(found | _curated(lambda part: bool(part.video)))


def is_video(source: str) -> bool:
    return source in video_sources()
