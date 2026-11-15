"""Send to Anki: what Your Words hands the reader's own Anki (targum-internal#540;
design.md §12, "Send to Anki talks to the Anki on your own computer", 2026-11-14).

At a desk the page talks to AnkiConnect on the reader's own machine itself; the server
never does. What the server adds is the reader's words as notes, read afresh on every ask
off the account's rows and off builds already on this disk:

- **The words.** Every saved word in the language at stages 1 to 4, to be added, and every
  known word, to be updated only where Anki already has it. Ignored words never leave.
- **The line.** The first line the word was met in: the earliest finished text, at the
  line the word first comes round in, so a note does not change between sends. Where the
  reader finished nothing that carries it, the first place on their own shelf. A line in
  a shared-shelf text whose licence does not let it leave is never chosen.
- **The sounds already on disk.** The word's clip where the voice already made one, and
  the line cut out of a recording the text already has, at most `LINE_MOST` seconds, its
  credit carried in Source.

**Nothing here spends.** No voice is asked, no job is written, nothing is claimed: a word
with no clip goes in silent, and a line clip is cut locally with ffmpeg from a file that is
already here.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

#: The notetype the page makes in Anki where it is missing. Not the `.apkg`'s `targum
#: word`: AnkiConnect cannot set a model id, and the same name would collide.
NOTETYPE = "targum word and sentence"

#: The `.apkg`'s own notetype (`anki.MODEL_NAME`), whose notes are left alone: a word a
#: reader already imported gets only its Gap card (design.md §12, decision 6).
IMPORTED_NOTETYPE = "targum word"

#: Words in one answer of `/account/anki/notes`.
PAGE = 200

#: The stages that are added. Known (9) is only ever updated; ignored (0) never leaves.
ADDED = (1, 2, 3, 4)
KNOWN = 9

#: The longest line that gets its sound, in seconds, and the room left either side.
LINE_MOST = 20.0
PAD = 0.15

#: The tag every sent note carries beside the `.apkg`'s own.
SENT_TAG = "targum::sent"

FolderFor = Callable[[str], "tuple[Path, str] | None"]


@dataclass(frozen=True)
class Place:
    """Where a word's line is: the text, its section, the segment and the word's
    offsets there, as the annotation counts them (`meetings.Line`'s shape)."""

    lemma: str
    document: str
    folder: Path
    section: int
    segment: str
    start: int
    end: int


def _order(finished: Iterable[tuple[str, str, int]]) -> list[tuple[str, set[int]]]:
    """Each text a section of which was finished, the earliest finish first, with the
    sections finished. Ties fall to the document's hash, so the order never moves."""
    by_document: dict[str, dict[int, int]] = {}
    for document, section, at in finished:
        try:
            number = int(section)
        except (TypeError, ValueError):
            continue
        by_document.setdefault(str(document), {})[number] = int(at or 0)
    ordered = sorted(by_document.items(), key=lambda pair: (min(pair[1].values()), pair[0]))
    return [(document, set(sections)) for document, sections in ordered]


def first_lines(
    lemmas: Iterable[str],
    finished: Iterable[tuple[str, str, int]],
    folder_for: FolderFor,
    language: str,
    *,
    own: Iterable[tuple[str, Path]] = (),
    may_leave: Callable[[Path], bool] = lambda _folder: True,
) -> dict[str, Place]:
    """The line each word is sent with: the earliest finished text first, and in it the
    first finished section the word comes round in; then, for a word met in no finished
    section, the reader's own shelf (`own`, in the order given), any section. One pass
    over each text's cached meetings for every word at once, never a pass per word."""
    from .meetings import text_meetings

    wanted = set(lemmas)
    out: dict[str, Place] = {}

    def take(document: str, folder: Path, sections: set[int] | None) -> None:
        if not may_leave(folder):
            return
        meetings = text_meetings(folder)
        if meetings is None:
            return
        for lemma in wanted & meetings.first.keys():
            if lemma in out:
                continue
            places = meetings.first[lemma]
            here = sorted(n for n in places if sections is None or n in sections)
            if not here:
                continue
            segment, start, end, _case = places[here[0]]
            out[lemma] = Place(lemma, document, folder, here[0], segment, start, end)

    for document, sections in _order(finished):
        if len(out) == len(wanted):
            return out
        found = folder_for(document)
        if found is None:
            continue
        folder, its_language = found
        if language and its_language.split("-")[0].lower() != language:
            continue
        take(document, folder, sections)
    for document, folder in own:
        if len(out) == len(wanted):
            break
        take(document, folder, None)
    return out


@dataclass(frozen=True)
class Heard:
    """A line's clock in a recording already on disk, and what the recording asks."""

    path: Path
    start: float
    end: float
    credit: str = ""
    licence: str = ""


@dataclass
class Texts:
    """The files of the texts one ask reads, each read once however many words it holds."""

    into: str
    _segments: dict[Path, tuple[dict[str, Any], dict[str, int]]] = field(default_factory=dict)
    _translations: dict[Path, dict[str, str]] = field(default_factory=dict)
    _pointed: dict[Path, dict[str, str]] = field(default_factory=dict)
    _titles: dict[Path, str] = field(default_factory=dict)
    _heard: dict[tuple[Path, int], dict[str, Heard]] = field(default_factory=dict)

    def segments(self, folder: Path) -> dict[str, Any]:
        """The text's segments by id."""
        return self._read(folder)[0]

    def sections(self, folder: Path) -> dict[str, int]:
        """Each segment's section, as the reader's page numbers it (`occurrences._sections`)."""
        return self._read(folder)[1]

    def _read(self, folder: Path) -> tuple[dict[str, Any], dict[str, int]]:
        if folder not in self._segments:
            from .models import SegmentedDocument, read_artifact
            from .occurrences import _sections

            segmented = read_artifact(SegmentedDocument, folder / "segments.json")
            if segmented is None:
                self._segments[folder] = ({}, {})
            else:
                self._segments[folder] = (
                    {segment.id: segment for segment in segmented.segments},
                    _sections(folder, segmented),
                )
        return self._segments[folder]

    def translation(self, folder: Path) -> dict[str, str]:
        if folder not in self._translations:
            from .meetings import _translation

            self._translations[folder] = _translation(folder, self.into)
        return self._translations[folder]

    def pointed(self, folder: Path) -> dict[str, str]:
        if folder not in self._pointed:
            try:
                loaded = json.loads((folder / "vocalization.json").read_text(encoding="utf-8"))
            except (OSError, ValueError):
                loaded = {}
            said = (loaded.get("segments") or {}) if isinstance(loaded, dict) else {}
            self._pointed[folder] = {str(k): str(v) for k, v in said.items()}
        return self._pointed[folder]

    def title(self, folder: Path) -> str:
        if folder not in self._titles:
            try:
                facts = json.loads((folder / "document.json").read_text(encoding="utf-8"))
            except (OSError, ValueError):
                facts = {}
            title = str(facts.get("title") or "") if isinstance(facts, dict) else ""
            self._titles[folder] = title or folder.name
        return self._titles[folder]

    def heard(self, folder: Path, section: int) -> dict[str, Heard]:
        """Every line of one section that a recording already on disk says, by segment:
        `render.builder.on_disk`, the question the reader's own build asks."""
        if (folder, section) not in self._heard:
            self._heard[(folder, section)] = _heard(
                folder, section, self.segments(folder), self.sections(folder)
            )
        return self._heard[(folder, section)]

    def line(self, place: Place) -> dict[str, Any] | None:
        """The line as the note shows it, split at the word: pointed where the build
        pointed it (`meetings.drawn`), with its translation. None where it is gone."""
        from .meetings import Line, drawn

        segment = self.segments(place.folder).get(place.segment)
        if segment is None:
            return None
        line = Line(
            place.lemma,
            place.document,
            place.folder,
            place.section,
            place.segment,
            place.start,
            place.end,
        )
        shown, start, end = drawn(
            line, segment.text, self.pointed(place.folder).get(place.segment, "")
        )
        if not 0 <= start < end <= len(shown):
            return None
        return {
            "before": shown[:start],
            "gap": shown[start:end],
            "after": shown[end:],
            "translation": self.translation(place.folder).get(place.segment, ""),
            "title": self.title(place.folder),
        }


def _heard(
    folder: Path, section: int, segments: dict[str, Any], section_of: dict[str, int]
) -> dict[str, Heard]:
    from .models import BlockKind
    from .render.builder import on_disk
    from .sentences import _document

    facts = _document(folder)
    if facts is None or not segments:
        return {}
    rows = list(segments.values())
    mine = [
        segment
        for segment in rows
        if section_of.get(segment.id, 1) == section and segment.kind is not BlockKind.heading
    ]
    if not mine:
        return {}
    try:
        spoken = on_disk(facts, mine, folder)
    except Exception:  # noqa: BLE001 - a recording that will not read says nothing
        return {}
    if not spoken.audio:
        return {}
    path = Path(spoken.audio)
    if not path.is_file():
        return {}
    out: dict[str, Heard] = {}
    for segment in mine:
        span = spoken.spans.get(segment.id) or []
        if len(span) >= 2:
            out[segment.id] = Heard(
                path, float(span[0]), float(span[1]), spoken.credit or "", spoken.licence or ""
            )
    return out


def held(heard: Heard | None) -> bool:
    """Whether a line's clock is one that gets a sound: there, and at most `LINE_MOST`."""
    return heard is not None and 0 < heard.end - heard.start <= LINE_MOST


def recording_may_leave(heard: Heard) -> bool:
    """A recording under a licence that does not let it leave stays here. A recording
    with no licence on it is targum's own voice or the reader's own file."""
    from .licensing import exportable

    return not heard.licence or exportable(heard.licence)


def _short(text: str, n: int = 20) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:n]


def line_name(heard: Heard) -> str:
    """The stable name of a line's clip, in Anki's media and in the cache here."""
    return f"targum-line-{_short(f'{heard.path}|{heard.start:.3f}|{heard.end:.3f}')}.mp3"


def sound_name(kept: Path) -> str:
    """The stable name of a word's clip in Anki's media: the clip's own key, which is
    what was said and in which language (`serve.said_clip`)."""
    return f"targum-{_short(kept.name)}{kept.suffix or '.mp3'}"


def stamp(note: dict[str, Any]) -> str:
    """What targum last wrote, as Anki's `Sent` keeps it: every field targum writes and
    the stage's tag, and nothing else. A second send with nothing changed is a skip."""
    parts = [
        note["term"],
        note["meaning"],
        note["soundFile"],
        note["before"],
        note["gap"],
        note["after"],
        note["translation"],
        note["lineFile"],
        note["source"],
        note["tags"],
    ]
    return _short(json.dumps(parts, ensure_ascii=False), 16)


def tags(language: str, stage: int) -> str:
    """The `.apkg`'s tags and `SENT_TAG`, so sent cards sit beside imported ones."""
    return f"targum targum::{language} targum::level-{stage} {SENT_TAG}"


def note(
    row: dict[str, Any],
    language: str,
    line: dict[str, Any] | None,
    heard: Heard | None,
    kept: Path | None,
) -> dict[str, Any]:
    """One word as the page sends it. Values are as written; the page escapes each one
    into the note's HTML."""
    import unicodedata
    from urllib.parse import quote

    lemma = str(row["lemma"])
    stage = int(row["status"])
    key = f"{language}:{lemma}"
    surface = unicodedata.normalize("NFC", str(row.get("surface") or lemma)).strip() or lemma
    sounded = heard is not None and line is not None
    source = ""
    if line is not None:
        source = line["title"]
        if sounded and heard is not None:
            source = " · ".join(part for part in (source, heard.credit, heard.licence) if part)
    out: dict[str, Any] = {
        "key": key,
        "lemma": lemma,
        "term": line["gap"] if line is not None else surface,
        "meaning": " · ".join(part for part in (row.get("meaning"), row.get("note")) if part),
        "stage": stage,
        "add": stage in ADDED,
        "before": line["before"] if line else "",
        "gap": line["gap"] if line else "",
        "after": line["after"] if line else "",
        "translation": line["translation"] if line else "",
        "source": source,
        "sound": f"/account/anki/sound?key={quote(key)}" if kept is not None else "",
        "soundFile": sound_name(kept) if kept is not None else "",
        "line": f"/account/anki/line?key={quote(key)}" if sounded else "",
        "lineFile": line_name(heard) if sounded and heard is not None else "",
        "tags": tags(language, stage),
    }
    out["hash"] = stamp(out)
    return out


def sendable(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """The account's words that may be sent: learning ones to add, known ones to update.
    Ignored words never leave."""
    return [row for row in rows if row.get("status") in ADDED or row.get("status") == KNOWN]


def cut(heard: Heard, *, run: Callable[..., Any] | None = None) -> Path | None:
    """The line's clip, cut once into the cache: mono, 64k, `PAD` either side. None for a
    line too long to hold in the ear, or where ffmpeg could not cut it. Local compute
    only: nothing is asked of anybody."""
    from .paths import cache_dir

    if not held(heard):
        return None
    into = cache_dir() / "anki-lines" / line_name(heard)
    if into.is_file() and into.stat().st_size > 0:
        return into
    into.parent.mkdir(parents=True, exist_ok=True)
    begin = max(0.0, heard.start - PAD)
    length = heard.end + PAD - begin
    part = into.with_name(into.stem + ".part.mp3")
    run = run or subprocess.run
    try:
        done = run(
            [
                "ffmpeg",
                "-nostdin",
                "-loglevel",
                "error",
                "-y",
                "-ss",
                f"{begin:.3f}",
                "-t",
                f"{length:.3f}",
                "-i",
                str(heard.path),
                "-vn",
                "-ac",
                "1",
                "-b:a",
                "64k",
                "-f",
                "mp3",
                str(part),
            ],
            capture_output=True,
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        part.unlink(missing_ok=True)
        return None
    if getattr(done, "returncode", 1) != 0 or not part.is_file() or part.stat().st_size == 0:
        part.unlink(missing_ok=True)
        return None
    part.replace(into)
    return into


def shared_may_leave(folder: Path) -> bool:
    """Whether a shared-shelf text's lines may leave targum: its catalogue row's licence,
    by `licensing.exportable`, the rule `targum licences` counts "may leave" by. A text
    the catalogue does not know stays here."""
    from . import catalogue
    from .licensing import exportable

    try:
        facts = json.loads((folder / "document.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    source = str(facts.get("source") or "") if isinstance(facts, dict) else ""
    entry = catalogue.matching(source) if source else None
    return entry is not None and exportable(entry.licence)
