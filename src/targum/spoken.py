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

from functools import cache


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


def is_spoken(source: str) -> bool:
    return source in sources()


@cache
def video_sources() -> frozenset[str]:
    """Every source whose recording kept its pictures: a subset of `sources()`.

    Nothing in the library carries one yet, and this still reads the disk rather than
    answering no: the day a recording arrives with a video part beside its audio, the
    shelf says so with no code changed, and until then no entry can claim a picture
    this machine has not got.
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
    return frozenset(found)


def is_video(source: str) -> bool:
    return source in video_sources()
