"""The one file a text card may play, and the short-lived address it plays it from.

design.md §12, "A card in someone else's chat" (2026-10-06): a text card can play audio
the text already has, streamed from targum.page, never spending. A card is drawn in a
host's sandboxed frame on another origin, and the reader's session cookie is
`SameSite=Lax` and third-party besides, so a `<audio>` in that frame reaches
`/reader/...` signed out and is turned away. The card is handed an address that needs
no cookie instead.

**The address names nothing.** It is `/heard?t=<token>`, the token a random string kept
here against the one file it opens and the minute it stops, never a path, a signature
over one, or anything a holder could change to reach a second file. There was no signed
address anywhere in targum to reuse (sign-in links and OAuth codes are rows in the store
and are spent once; a file that may be played, paused and seeked is asked for many
times), and a token that is a key into this table needs no secret to keep: what it can
open was decided when it was made.

- **One file.** A token opens the file it was made for and nothing else; a token not
  made here, or made for another file, is a 404 like any address that is not there.
- **Twenty minutes.** The sign-in link's span. Long enough to scroll back up and press
  play, short enough that a token copied out of a conversation is dead by the time it
  is anywhere else. The card hides its button when the token has run out.
- **In this process only.** A restart forgets every token, which costs a card made in
  the minutes before it its play button and nothing else; there is no table to migrate,
  no secret to rotate and nothing on disk to leak.
- **Only audio, and only from where a text's audio lives.** Checked when a token is made
  and again when it is opened: the file's suffix is one of `AUDIO_KINDS` and the file is
  inside one of the folders handed over (the reader's home, the shared shelf, the
  recordings, the dialogues).
- **Never spends.** Everything here reads a file that is already on the disk. A text with
  no recording has no file, so its card has no button: making one is still a press on
  targum's own page.
"""

from __future__ import annotations

import json
import secrets
import threading
import time
from collections import OrderedDict
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

#: Where a card's audio is asked for: `/heard?t=<token>`. The token rides in `t`, the
#: query field the proxy's log already drops (deploy/Caddyfile), so a live token is
#: never written down.
ROUTE = "/heard"

#: How long a token opens its file, in seconds: the sign-in link's twenty minutes.
LIFETIME_S = 20 * 60

#: The most tokens kept at once, oldest out first. A find answers with at most twenty
#: texts, so this is two hundred finds in twenty minutes before a live token is dropped.
MOST = 4096

#: The only files a token opens, and the type each is served as. A closed table, like
#: `Handler.MEDIA_KINDS`: a door that cannot grow by accident cannot open by accident.
AUDIO_KINDS: dict[str, str] = {
    ".mp3": "audio/mpeg",
    ".m4a": "audio/mp4",
    ".ogg": "audio/ogg",
    ".opus": "audio/ogg",
    ".wav": "audio/wav",
}


@dataclass(frozen=True)
class Recorded:
    """A text's recording, as a card needs it: the file, and whose reading it is."""

    path: Path
    #: Whose reading, where the licence asks for them to be named (Be'eri, PocketTorah,
    #: LibriVox). "" for a scene or a voice we made, which are ours.
    credit: str = ""


def _inside(path: Path, roots: Iterable[Path]) -> bool:
    try:
        real = path.resolve()
    except OSError:
        return False
    if not real.is_file() or real.suffix.lower() not in AUDIO_KINDS:
        return False
    return any(root.resolve() in real.parents for root in roots if str(root))


class Heard:
    """The live tokens, each against the one file it opens and when it stops."""

    def __init__(self, most: int = MOST, clock: Callable[[], float] = time.time) -> None:
        self._most = most
        self._clock = clock
        self._kept: OrderedDict[str, tuple[Path, float, tuple[Path, ...]]] = OrderedDict()
        self._lock = threading.Lock()

    def issue(self, path: Path, roots: Iterable[Path]) -> tuple[str, float] | None:
        """A token for `path` and the moment it stops, in seconds since the epoch; None
        where the file is not audio or is not inside one of `roots`."""
        roots = tuple(roots)
        if not _inside(path, roots):
            return None
        token = secrets.token_urlsafe(24)
        ends = self._clock() + LIFETIME_S
        with self._lock:
            self._sweep()
            self._kept[token] = (path.resolve(), ends, roots)
            while len(self._kept) > self._most:
                self._kept.popitem(last=False)
        return token, ends

    def opened(self, token: str) -> Path | None:
        """The file a live token opens, or None: unknown, run out, or no longer the audio
        file inside its folder that it was when the token was made."""
        if not token:
            return None
        with self._lock:
            kept = self._kept.get(token)
        if kept is None:
            return None
        path, ends, roots = kept
        if self._clock() >= ends:
            with self._lock:
                self._kept.pop(token, None)
            return None
        return path if _inside(path, roots) else None

    def clear(self) -> None:
        with self._lock:
            self._kept.clear()

    def _sweep(self) -> None:
        now = self._clock()
        for token in [token for token, (_, ends, _) in self._kept.items() if ends <= now]:
            del self._kept[token]


HEARD = Heard()


def roots(home: Path, shared: Path) -> tuple[Path, ...]:
    """Every folder a text's audio may live in, for a reader whose home is `home`."""
    from .dialogue import index as dialogue_index
    from .recording import index as recording_index

    return (home, shared, recording_index.root(), dialogue_index.root())


def recording_of(folder: Path) -> Recorded | None:
    """The file a card plays for a built text, or None where it has no recording.

    Asked in the order the reader's own build asks (`builder.speech`), and only of what
    is already on the disk:

    1. the manifest beside the text (`audio.json`): an import's recording, or a voice
       the reader already paid for on Hear — its first part that has a file;
    2. a scene's own voicing, for a `dialogue:` text;
    3. the recording attached to the text's source — Be'eri's Tanakh, PocketTorah, a
       LibriVox reading — the part that holds the text's first verse, or its first.

    A curated video is left out: its picture is the point of it, and a card is not a
    player for one.
    """
    from .audio import manifest as manifest_module

    if (folder / manifest_module.MANIFEST).is_file():
        try:
            manifest = manifest_module.load(folder)
        except Exception:  # noqa: BLE001 - a manifest that will not read plays nothing
            manifest = None
        if manifest is None:
            return None
        for cut in sorted(manifest.parts, key=lambda one: one.number):
            if cut.audio and (folder / cut.audio).is_file():
                return Recorded(folder / cut.audio)
        return None
    source, first_ref = _source(folder)
    if source.startswith("dialogue:"):
        return _scene(source.split(":", 1)[1])
    if not source or source.startswith(("video:", "weekly:")):
        return None
    from .recording import index as recording_index

    recording = recording_index.load(source)
    if recording is None or not recording.parts:
        return None
    part = (recording.part_for([first_ref]) if first_ref else None) or recording.parts[0]
    path = recording_index.folder(source) / part.audio
    return Recorded(path, recording.credit) if path.is_file() else None


def _source(folder: Path) -> tuple[str, str]:
    """A built text's source and the ref of its first line, "" for either it lacks."""
    try:
        source = str(
            json.loads((folder / "document.json").read_text(encoding="utf-8")).get("source") or ""
        )
    except (OSError, ValueError, AttributeError):
        return "", ""
    try:
        segments = json.loads((folder / "segments.json").read_text(encoding="utf-8"))
        rows = segments.get("segments", segments) if isinstance(segments, dict) else segments
        first = next((str(row.get("ref") or "") for row in rows if row.get("ref")), "")
    except (OSError, ValueError, AttributeError, TypeError):
        first = ""
    return source, first


def _scene(identifier: str) -> Recorded | None:
    from .dialogue import index as dialogue_index

    try:
        scene = dialogue_index.load(identifier)
    except Exception:  # noqa: BLE001 - a scene that is not on this box plays nothing
        return None
    if not scene.audio or not any(turn.voiced for turn in scene.turns):
        return None
    path = dialogue_index.root() / scene.audio
    return Recorded(path) if path.is_file() else None


__all__ = [
    "AUDIO_KINDS",
    "HEARD",
    "LIFETIME_S",
    "ROUTE",
    "Heard",
    "Recorded",
    "recording_of",
    "roots",
]
