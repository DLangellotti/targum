"""The chanted reading, from PocketTorah, attached to a portion.

PocketTorah is a set of recordings of the whole Torah made for an app of the same name
and released under CC BY-SA 3.0 — Avery-Binder style, which is the Ashkenazi trope. Two
things about it make this much less work than attaching a recording usually is:

* It is **already one file per aliyah** (`Bereshit-1.mp3` … `-7`), and an aliyah is
  exactly what a section of a built portion is. Nothing has to be cut.
* It is chanted rather than read, which sounded like it would defeat a forced aligner
  trained on speech. Measured on Bereshit's first aliyah — 404 words against 449 seconds
  of leyning — it does not: every word came back, monotonic, spanning the whole file.
  That is why this stores real per-verse spans rather than giving each aliyah one span
  and letting the reader guess.

**Licence.** CC BY-SA, which the audio bar admits: ND is the line, because the pipeline
makes derivatives, and SA is not ND. The credit and the licence ride in the manifest and
the reader draws them under the player.

**Doubled weeks are re-divided rather than skipped.** PocketTorah has Matot and Masei as
separate recordings and nothing called "Matot-Masei" — but the audio is not missing, only
divided in the wrong places: a doubled week reads the same verses as its two halves, end
to end, and only the seven aliyah boundaries move. So the fourteen files are joined into
one waveform, aligned against the combined text in a single pass, and cut where *this*
reading divides, seams in the silence between words. Matching the files up one for one
instead would put the wrong sound under five sections out of seven.

A festival Shabbat has no recording here at all, and gets none: its reading is not a
portion and PocketTorah does not carry it. Silence is the same answer a missing span
already gets everywhere else in the reader.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from pathlib import Path

from ..audio.align import CtcAligner
from ..cache import Cache
from ..errors import TargumError
from ..models import BlockKind
from ..recording import index as recording_index
from ..recording.models import Part, Recording
from ..vocalize import strip_taamim
from .calendar import Reading
from .cut import Portion, parse_place, parse_ref

#: Where the files live, and what they are.
COLLECTION = "PockettorahAudioFiles"
DOWNLOAD = f"https://archive.org/download/{COLLECTION}"
METADATA = f"https://archive.org/metadata/{COLLECTION}"

CREDIT = "PocketTorah, Avery-Binder trope"
LICENCE = "CC BY-SA 3.0"
LICENCE_URL = "https://creativecommons.org/licenses/by-sa/3.0/"

TIMEOUT = 120.0

#: What a file in the collection may be called. Deliberately narrow: these names come
#: off somebody else's listing and are then joined onto a directory to write into, so
#: `.+` here is a way for a remote name carrying `../` to put a download anywhere on the
#: disk. The stem is letters, digits and the punctuation the collection actually uses
#: (`3megillot`, `AchreiMot`, `V'Zot`), and a separator never gets in.
_PART = re.compile(r"^(?P<stem>[A-Za-z0-9'’!._ -]+)-(?P<number>\d+)\.mp3$")


def _flat(name: str) -> str:
    """A name with everything but its letters and digits taken out.

    The two sides spell the same portions differently — Hebcal writes "Achrei Mot" and
    "Ki Tisa", PocketTorah writes `AchreiMot` and `KiTisa` — and neither is wrong. Both
    go through this and meet in the middle.
    """
    return "".join(c for c in name.lower() if c.isalnum())


def stems(files: Iterable[str]) -> dict[str, dict[int, str]]:
    """The collection's mp3s grouped by portion, keyed by the flattened name."""
    out: dict[str, dict[int, str]] = {}
    for name in files:
        found = _PART.match(name)
        if not found:
            continue
        out.setdefault(_flat(found["stem"]), {})[int(found["number"])] = name
    return out


def listing() -> dict[str, dict[int, str]]:
    """What the collection holds, asked once and cached with everything else."""
    import httpx

    cache = Cache()
    key = cache.key("pockettorah", collection=COLLECTION)
    stored = cache.get("pockettorah", key)
    if isinstance(stored, list):
        return stems(str(one) for one in stored)
    try:
        with httpx.Client(timeout=TIMEOUT, follow_redirects=True) as client:
            answer = client.get(METADATA)
            answer.raise_for_status()
            payload = answer.json()
    except Exception as bad:  # noqa: BLE001 — one failure, one message
        raise TargumError(
            "The recordings could not be listed.",
            f"{METADATA} said: {bad}",
        ) from bad
    names = [str(one.get("name", "")) for one in payload.get("files", [])]
    cache.put("pockettorah", key, names)
    return stems(names)


def files_for(reading: Reading, have: dict[str, dict[int, str]] | None = None) -> dict[int, str]:
    """Which file reads which aliyah of this reading, one for one.

    Only for a portion read on its own, where PocketTorah's files and this reading's
    aliyot are the same seven divisions of the same text. A doubled week divides the
    same verses differently and goes through `halves_of` instead; a festival has no
    recording here at all. Empty is the answer in both cases, not an error.
    """
    if reading.doubled or not reading.numbers:
        return {}
    have = listing() if have is None else have
    found = have.get(_flat(reading.name), {})
    if len(found) < len(reading.aliyot):
        return {}
    return {
        number: found[number] for number in range(1, len(reading.aliyot) + 1) if number in found
    }


def halves_of(reading: Reading, have: dict[str, dict[int, str]] | None = None) -> list[str]:
    """Every file of a doubled week's reading, in the order it is chanted.

    A doubled week is read as one continuous stretch of Torah, and PocketTorah has that
    stretch — as two recordings, one per portion, because the portions also exist on
    their own. What it does not have is the *division*: Matot-Masei's seven aliyot fall
    in different places from Matot's seven and Masei's seven, so no file is an aliyah of
    the combined reading and matching them up one for one would put the wrong sound
    under five sections out of seven.

    So the files are handed back whole and in order, and `attach` treats them the way
    `recording.attach` treats a book that arrives as discs: one waveform, aligned once,
    cut where this reading actually divides.

    Empty where either half is missing. The names come apart on the hyphen that joins
    them — every doubled name is written that way and no single name has one in it.
    """
    if not reading.doubled:
        return []
    have = listing() if have is None else have
    out: list[str] = []
    for half in reading.name.split("-"):
        found = have.get(_flat(half), {})
        if not found:
            return []
        numbers = sorted(found)
        if numbers != list(range(1, len(numbers) + 1)):
            return []
        out.extend(found[number] for number in numbers)
    return out


def fetch(name: str, into: Path) -> Path:
    """One file, kept on disk so a re-attach never downloads it twice.

    The name is checked again here rather than trusted from `_PART`. It arrives from a
    listing on somebody else's server and is about to be joined onto a directory and
    written to, and a name is the one part of a download nobody thinks of as input.
    """
    import httpx

    into.mkdir(parents=True, exist_ok=True)
    target = (into / name).resolve()
    if target.parent != into.resolve() or not _PART.match(name):
        raise TargumError(
            f"{name!r} is not a name this collection can have.",
            "A file name that leaves its own directory is refused, not fetched.",
        )
    if target.is_file() and target.stat().st_size > 0:
        return target
    try:
        with httpx.Client(timeout=TIMEOUT, follow_redirects=True) as client:
            answer = client.get(f"{DOWNLOAD}/{name}")
            answer.raise_for_status()
            target.write_bytes(answer.content)
    except Exception as bad:  # noqa: BLE001
        raise TargumError(f"{name} could not be fetched.", str(bad)) from bad
    return target


def _verses(portion: Portion, number: int, reading: Reading) -> list[tuple[str, str]]:
    """The verses of one aliyah, as (ref, text) in reading order."""
    aliyah = next((one for one in reading.aliyot if one.number == number), None)
    if aliyah is None:
        return []
    first, last = parse_place(aliyah.begin), parse_place(aliyah.end)
    if first is None or last is None:
        return []
    out = []
    for segment in portion.segmented.segments:
        if segment.kind is not BlockKind.verse:
            continue
        parsed = parse_ref(segment.ref)
        if parsed is None or parsed[0] != aliyah.book:
            continue
        if first <= parsed[1] <= last:
            out.append((segment.ref, segment.text))
    return out


def spans_for(
    audio: Path, verses: list[tuple[str, str]], notify: Callable[[str], None]
) -> dict[str, list[float]]:
    """Each verse's [start, end] inside this file, from a forced alignment.

    The accents come off before the text goes to the aligner: they are not pronounced,
    and a model trained on speech has never seen one. The vowels stay, because they are
    what the letters are said as.
    """
    aligner = CtcAligner()
    usable, hint = aligner.available()
    if not usable:
        raise TargumError("The forced aligner is not installed.", hint)

    words: list[str] = []
    owners: list[str] = []
    for ref, text in verses:
        pieces = strip_taamim(text).split()
        words.extend(pieces)
        owners.extend([ref] * len(pieces))
    if not words:
        return {}

    cache = Cache()
    key = cache.key(
        "pockettorah-align",
        audio=audio.name,
        size=audio.stat().st_size,
        words=len(words),
        text="".join(words)[:400],
    )
    stored = cache.get("pockettorah-align", key)
    if isinstance(stored, list) and len(stored) == len(words):
        timed = [(float(a), float(b), float(c)) for a, b, c in stored]
    else:
        notify(f"    lining up {len(words)} words with {audio.name}…")
        timed = aligner.align(audio, words, "he")
        if len(timed) != len(words):
            raise TargumError(
                f"{audio.name}: {len(timed)} clocks for {len(words)} words.",
                "The recording and the text do not match.",
            )
        cache.put("pockettorah-align", key, [list(row) for row in timed])

    spans: dict[str, list[float]] = {}
    for ref, (start, end, _score) in zip(owners, timed, strict=True):
        if ref in spans:
            spans[ref][1] = round(float(end), 3)
        else:
            spans[ref] = [round(float(start), 3), round(float(end), 3)]
    return spans


def _one_file_per_aliyah(
    reading: Reading,
    portion: Portion,
    wanted: dict[int, str],
    into: Path,
    keep: Path,
    notify: Callable[[str], None],
) -> list[Part]:
    """A portion read on its own: PocketTorah's divisions are already this reading's.

    Each file is copied across as it is and aligned against its own aliyah. Nothing is
    re-encoded, so the audio a reader hears is the audio that was published.
    """
    parts: list[Part] = []
    for number in sorted(wanted):
        verses = _verses(portion, number, reading)
        if not verses:
            continue
        source_file = fetch(wanted[number], keep)
        audio_name = f"aliyah-{number:02d}.mp3"
        target = into / audio_name
        if not target.is_file() or target.stat().st_size != source_file.stat().st_size:
            target.write_bytes(source_file.read_bytes())
        spans = spans_for(target, verses, notify)
        if not spans:
            continue
        parts.append(Part(ref=f"{reading.name} {number}", audio=audio_name, spans=spans))
        notify(f"    aliyah {number}: {len(spans)} verses")
    return parts


def _cut_from_the_pair(
    reading: Reading,
    portion: Portion,
    names: list[str],
    into: Path,
    keep: Path,
    notify: Callable[[str], None],
) -> list[Part]:
    """A doubled week: the two portions' recordings, re-divided where this week divides.

    The fourteen files are one continuous reading of the same verses, so they are joined
    into one waveform and aligned against the whole combined text in a single pass. That
    gives every verse a place on one clock, and the seven aliyot of *this* reading can
    then be cut out of it wherever they actually fall — including the one that begins in
    the middle of the first portion's last file.

    The seam between two aliyot is put at the midpoint of the silence between the last
    word of one and the first word of the next, which is `recording.attach`'s rule and
    for its reason: cutting on a word boundary clips the breath either side of it.

    `recording.attach` is in the half of the tree that is gitignored, so the import is
    here rather than at the top of the file: a public checkout must still be able to
    import this module — the tests do, and so does `targum parasha leyning` before it
    knows whether the week is doubled. Only this one path needs the waveform tools, and
    only a maintainer ever walks it.
    """
    try:
        from ..recording.attach import concatenated, cut, duration_of
    except ImportError as exc:  # pragma: no cover - the public tree has no attach.py
        raise TargumError(
            "cutting a doubled week needs targum.recording.attach, which is not in this "
            "checkout. Single portions are unaffected."
        ) from exc

    files = [fetch(name, keep) for name in names]
    verses = [
        (segment.ref, segment.text)
        for segment in portion.segmented.segments
        if segment.kind is BlockKind.verse and segment.ref
    ]
    if not verses:
        return []

    master = into / "whole.mp3"
    if not master.is_file():
        notify(f"    joining {len(files)} files into one reading…")
        concatenated(files, master)
    spans = spans_for(master, verses, notify)
    if not spans:
        return []

    parts: list[Part] = []
    total = duration_of(master)
    # Where each aliyah's own verses begin and end on the joined clock.
    bounds: list[tuple[int, float, float, dict[str, list[float]]]] = []
    for aliyah in reading.aliyot:
        mine = {
            ref: span
            for ref, _ in _verses(portion, aliyah.number, reading)
            if (span := spans.get(ref))
        }
        if not mine:
            continue
        starts = [one[0] for one in mine.values()]
        ends = [one[1] for one in mine.values()]
        bounds.append((aliyah.number, min(starts), max(ends), mine))
    if not bounds:
        return []

    # The seams: halfway through the silence between one aliyah's last word and the
    # next's first, with the ends of the reading left where they are.
    seams = [0.0]
    for (_, _, before, _), (_, after, _, _) in zip(bounds, bounds[1:], strict=False):
        low, high = sorted((before, after))
        seams.append(round((low + high) / 2, 3))
    seams.append(total)

    for index, (number, _, _, mine) in enumerate(bounds):
        start, end = seams[index], seams[index + 1]
        audio_name = f"aliyah-{number:02d}.mp3"
        cut(master, into / audio_name, start, end)
        rebased = {
            ref: [
                round(max(0.0, span[0] - start), 3),
                round(min(end - start, span[1] - start), 3),
            ]
            for ref, span in mine.items()
        }
        parts.append(Part(ref=f"{reading.name} {number}", audio=audio_name, spans=rebased))
        notify(f"    aliyah {number}: {len(rebased)} verses, {end - start:.0f}s")
    master.unlink(missing_ok=True)
    master.with_suffix(".txt").unlink(missing_ok=True)
    return parts


def attach(
    reading: Reading,
    portion: Portion,
    *,
    downloads: Path | None = None,
    notify: Callable[[str], None] = print,
) -> Recording | None:
    """Give one portion its chanted reading. None where there is none to give.

    Two ways in, because a doubled week is not a portion with more verses in it — it is
    the same verses divided somewhere else. See the two helpers above.
    """
    into = recording_index.folder(portion.document.source)
    keep = downloads or (into.parent / "pockettorah")
    wanted = files_for(reading)
    pair = [] if wanted else halves_of(reading)
    if not wanted and not pair:
        notify(f"  {reading.name}: no recording for this reading")
        return None

    into.mkdir(parents=True, exist_ok=True)
    if wanted:
        parts = _one_file_per_aliyah(reading, portion, wanted, into, keep, notify)
    else:
        parts = _cut_from_the_pair(reading, portion, pair, into, keep, notify)

    if not parts:
        return None
    recording = Recording(
        source=portion.document.source,
        credit=CREDIT,
        licence=LICENCE,
        licence_url=LICENCE_URL,
        parts=parts,
    )
    (into / recording_index.MANIFEST).write_text(
        recording.model_dump_json(indent=2) + "\n", encoding="utf-8"
    )
    notify(f"  {reading.name}: {len(parts)} aliyot attached")
    return recording


def attached(source: str) -> bool:
    """Whether a portion already has its reading, so a rerun can skip it."""
    return (recording_index.folder(source) / recording_index.MANIFEST).is_file()


__all__ = [
    "CREDIT",
    "LICENCE",
    "LICENCE_URL",
    "attach",
    "attached",
    "files_for",
    "listing",
    "spans_for",
]
