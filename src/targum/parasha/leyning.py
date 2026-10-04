"""The chanted reading, from PocketTorah, attached to a portion.

PocketTorah is a set of recordings of the whole Torah made for an app of the same name
and released under CC BY-SA 3.0 — Avery-Binder style, which is the Ashkenazi trope. Two
things about it make this much less work than attaching a recording usually is:

* It is **already one file per aliyah** (`Bereshit-1.mp3` … `-7`), and an aliyah is
  exactly what a section of a built portion is. Nothing has to be cut.
* It is chanted rather than read, which sounded like it would defeat a forced aligner
  trained on speech. Measured on Bereshit's first aliyah — 404 words against 449 seconds
  of leyning — it does not: every word came back, monotonic, spanning the whole file.
  That is why this stores a clock for every word rather than giving each aliyah one span
  and letting the reader guess. Until 2026-09-28 the clocks were collapsed to verses
  before they were stored; they are kept now, because a trope phrase and a word on the
  card both need what the verse span threw away (targum-internal#329).

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
from ..recording.models import Part, Recording, spoken_words, verse_spans
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

#: A portion's haftarah, which the collection files beside its aliyot as `Noach-H.mp3`.
#: The same narrow stem, for the same reason.
_HAFTARAH = re.compile(r"^(?P<stem>[A-Za-z0-9'’!._ -]+)-H\.mp3$")

#: The two names that do not meet even closed up. Hebcal transliterates the ת of
#: Va'etchanan as "tch" and PocketTorah as "th"; V'Zot HaBerachah is "VezotHaberakhah"
#: there. Keyed by Hebcal's flattened name, valued by PocketTorah's. Without these the
#: two portions were silent with all fourteen files on the disk (targum-internal#413).
_SPELLED = {
    "vaetchanan": "vaethanan",
    "vzothaberachah": "vezothaberakhah",
}


def _flat(name: str) -> str:
    """A name with everything but its letters and digits taken out.

    The two sides spell the same portions differently — Hebcal writes "Achrei Mot" and
    "Ki Tisa", PocketTorah writes `AchreiMot` and `KiTisa` — and neither is wrong. Both
    go through this and meet in the middle.
    """
    return "".join(c for c in name.lower() if c.isalnum())


def pocket_name(name: str) -> str:
    """A reading's name as the collection's stems are keyed: flattened, then respelled
    where the two sides transliterate differently."""
    flat = _flat(name)
    return _SPELLED.get(flat, flat)


def stems(files: Iterable[str]) -> dict[str, dict[int, str]]:
    """The collection's mp3s grouped by portion, keyed by the flattened name."""
    out: dict[str, dict[int, str]] = {}
    for name in files:
        found = _PART.match(name)
        if not found:
            continue
        out.setdefault(_flat(found["stem"]), {})[int(found["number"])] = name
    return out


def haftarah_files(files: Iterable[str]) -> dict[str, str]:
    """The collection's haftarot, one per portion, keyed by the portion's flattened name."""
    out: dict[str, str] = {}
    for name in files:
        found = _HAFTARAH.match(name)
        if found:
            out[_flat(found["stem"])] = name
    return out


def listing() -> dict[str, dict[int, str]]:
    """What the collection holds, asked once and cached with everything else."""
    return stems(names())


def haftarah_listing() -> dict[str, str]:
    """The collection's haftarah files, from the same cached listing."""
    return haftarah_files(names())


def names() -> list[str]:
    """Every file name in the collection, asked once and cached."""
    import httpx

    cache = Cache()
    key = cache.key("pockettorah", collection=COLLECTION)
    stored = cache.get("pockettorah", key)
    if isinstance(stored, list):
        return [str(one) for one in stored]
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
    listed = [str(one.get("name", "")) for one in payload.get("files", [])]
    cache.put("pockettorah", key, listed)
    return listed


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
    found = have.get(pocket_name(reading.name), {})
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
        found = have.get(pocket_name(half), {})
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
    if target.parent != into.resolve() or not (_PART.match(name) or _HAFTARAH.match(name)):
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


def clocks_for(
    audio: Path,
    verses: list[tuple[str, str]],
    notify: Callable[[str], None],
    scores: list[float] | None = None,
) -> dict[str, list[list[float]]]:
    """Each verse's words as [start, end] inside this file, from a forced alignment.

    The accents come off before the text goes to the aligner: they are not pronounced,
    and a model trained on speech has never seen one. The vowels stay, because they are
    what the letters are said as. The words are the ones `spoken_words` counts, so row n
    of a verse is the verse's nth word to the build that reads it back.

    `scores`, where given, is filled with the aligner's own score for each word, which
    is how a caller that is not sure the text and the recording are the same reading
    asks how well they matched.
    """
    aligner = CtcAligner()
    usable, hint = aligner.available()
    if not usable:
        raise TargumError("The forced aligner is not installed.", hint)

    words: list[str] = []
    owners: list[str] = []
    for ref, text in verses:
        pieces = [strip_taamim(text[start:end]) for start, end in spoken_words(text)]
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

    if scores is not None:
        scores.extend(float(score) for _, _, score in timed)
    clocks: dict[str, list[list[float]]] = {}
    for ref, (start, end, _score) in zip(owners, timed, strict=True):
        clocks.setdefault(ref, []).append([round(float(start), 3), round(float(end), 3)])
    return clocks


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
        clocks = clocks_for(target, verses, notify)
        if not clocks:
            continue
        parts.append(
            Part(
                ref=f"{reading.name} {number}",
                audio=audio_name,
                spans=verse_spans(clocks),
                clocks=clocks,
            )
        )
        notify(f"    aliyah {number}: {len(clocks)} verses")
    return parts


def _clocks_by_file(
    halves: list[Reading],
    portion: Portion,
    files: list[Path],
    duration_of: Callable[[Path], float],
    notify: Callable[[str], None],
) -> dict[str, list[list[float]]] | None:
    """A doubled week's clock, put together a file at a time instead of in one pass.

    Each of the fourteen files is one aliyah of one half, so it is aligned against that
    aliyah's verses — the same short alignment a portion read on its own gets — and moved
    along by the length of every file before it. The joined file is the same files end
    to end, so the result is the clock one pass over it would give.

    One pass over forty minutes is what torchaudio's `forced_align` could not do for
    Tazria-Metzora or Chukat-Balak: it died with SIGSEGV every time, which no `except`
    catches (targum-internal#413). None where the files and the halves' aliyot do not
    pair up one for one, and the caller falls back to the single pass.
    """
    named = [
        (half, aliyah.number)
        for half in halves
        for aliyah in sorted(half.aliyot, key=lambda one: one.number)
    ]
    if len(named) != len(files):
        return None
    clocks: dict[str, list[list[float]]] = {}
    elapsed = 0.0
    for (half, number), file in zip(named, files, strict=True):
        verses = _verses(portion, number, half)
        if not verses:
            return None
        for ref, rows in clocks_for(file, verses, notify).items():
            clocks.setdefault(ref, []).extend(
                [round(start + elapsed, 3), round(end + elapsed, 3)] for start, end in rows
            )
        elapsed += duration_of(file)
    return clocks


def _cut_from_the_pair(
    reading: Reading,
    portion: Portion,
    names: list[str],
    into: Path,
    keep: Path,
    notify: Callable[[str], None],
    halves: list[Reading] | None = None,
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
    clocks = _clocks_by_file(halves, portion, files, duration_of, notify) if halves else None
    if clocks is None:
        clocks = clocks_for(master, verses, notify)
    spans = verse_spans(clocks)
    if not spans:
        return []

    parts: list[Part] = []
    total = duration_of(master)
    # Where each aliyah's own verses begin and end on the joined clock.
    bounds: list[tuple[int, float, float, dict[str, list[list[float]]]]] = []
    for aliyah in reading.aliyot:
        mine = {
            ref: clocks[ref]
            for ref, _ in _verses(portion, aliyah.number, reading)
            if clocks.get(ref)
        }
        if not mine:
            continue
        starts = [rows[0][0] for rows in mine.values()]
        ends = [rows[-1][1] for rows in mine.values()]
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
                [round(max(0.0, one[0] - start), 3), round(min(end - start, one[1] - start), 3)]
                for one in rows
            ]
            for ref, rows in mine.items()
        }
        parts.append(
            Part(
                ref=f"{reading.name} {number}",
                audio=audio_name,
                spans=verse_spans(rebased),
                clocks=rebased,
            )
        )
        notify(f"    aliyah {number}: {len(rebased)} verses, {end - start:.0f}s")
    master.unlink(missing_ok=True)
    master.with_suffix(".txt").unlink(missing_ok=True)
    return parts


def downloads_root() -> Path:
    """Where the collection's own mp3s are kept between runs.

    Beside the recordings, never inside them. These are somebody else's files, held so a
    re-run does not fetch thirty-two hours again — a download cache, not a reading
    attached to anything. Inside the shelf it was a folder with no `recording.json`, and
    `ship-audio.sh` refuses the whole shelf on one of those, because half-cut is exactly
    what it cannot tell this apart from. That cost a deploy on 2026-09-04.
    """
    return recording_index.root().parent / "leyning" / "pockettorah"


def attach(
    reading: Reading,
    portion: Portion,
    *,
    downloads: Path | None = None,
    notify: Callable[[str], None] = print,
    halves: list[Reading] | None = None,
) -> Recording | None:
    """Give one portion its chanted reading. None where there is none to give.

    Two ways in, because a doubled week is not a portion with more verses in it — it is
    the same verses divided somewhere else. See the two helpers above. `halves`, for a
    doubled week, are the two portions read on their own, whose aliyot say which verses
    each of the fourteen files holds.
    """
    into = recording_index.folder(portion.document.source)
    keep = downloads or downloads_root()
    wanted = files_for(reading)
    pair = [] if wanted else halves_of(reading)
    if not wanted and not pair:
        notify(f"  {reading.name}: no recording for this reading")
        return None

    into.mkdir(parents=True, exist_ok=True)
    if wanted:
        parts = _one_file_per_aliyah(reading, portion, wanted, into, keep, notify)
    else:
        parts = _cut_from_the_pair(reading, portion, pair, into, keep, notify, halves)

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


def attach_haftarah(
    name: str,
    portion: Portion,
    file: str,
    *,
    downloads: Path | None = None,
    notify: Callable[[str], None] = print,
) -> Recording | None:
    """Give a haftarah its chanted reading: one file, one section, one part.

    The file is the one PocketTorah filed beside a portion (`Noach-H.mp3`), and which
    haftarah that is was PocketTorah's choice, not the calendar's: a portion whose
    custom varies — Ashkenazi or Sephardi, or the haftarah a neighbouring portion lends
    it — may hold a different reading from the one this corpus shows. So the match is
    measured rather than assumed. The whole text is aligned against the file and kept
    only where the aligner's mean score clears `MATCH_FLOOR`, the line it already uses
    to say a part does not follow its recording; below it the haftarah stays silent and
    nothing is left in the shelf, because a folder with no manifest stops `ship-audio`.
    """
    from statistics import mean

    from ..audio.align import MATCH_FLOOR

    keep = downloads or downloads_root()
    verses = [
        (segment.ref, segment.text)
        for segment in portion.segmented.segments
        if segment.kind is BlockKind.verse and segment.ref
    ]
    if not verses:
        return None
    source_file = fetch(file, keep)
    scores: list[float] = []
    clocks = clocks_for(source_file, verses, notify, scores)
    score = mean(scores) if scores else MATCH_FLOOR - 1
    if not clocks or score < MATCH_FLOOR:
        notify(f"  {name}: {file} does not read this haftarah (score {score:.2f})")
        return None

    into = recording_index.folder(portion.document.source)
    into.mkdir(parents=True, exist_ok=True)
    audio_name = "haftarah.mp3"
    target = into / audio_name
    if not target.is_file() or target.stat().st_size != source_file.stat().st_size:
        target.write_bytes(source_file.read_bytes())
    recording = Recording(
        source=portion.document.source,
        credit=CREDIT,
        licence=LICENCE,
        licence_url=LICENCE_URL,
        parts=[
            Part(
                ref=f"{name} haftarah",
                audio=audio_name,
                spans=verse_spans(clocks),
                clocks=clocks,
            )
        ],
    )
    (into / recording_index.MANIFEST).write_text(
        recording.model_dump_json(indent=2) + "\n", encoding="utf-8"
    )
    notify(f"  {name}: haftarah attached, {len(clocks)} verses (score {score:.2f})")
    return recording


def attached(source: str) -> bool:
    """Whether a portion already has its reading, so a rerun can skip it."""
    return (recording_index.folder(source) / recording_index.MANIFEST).is_file()


__all__ = [
    "CREDIT",
    "LICENCE",
    "LICENCE_URL",
    "attach",
    "attach_haftarah",
    "attached",
    "clocks_for",
    "files_for",
    "haftarah_files",
    "haftarah_listing",
    "listing",
    "pocket_name",
]
