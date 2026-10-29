"""Where the library's texts sit on the weekly's three levels, per language.

targum-internal#382 asks for more of the bottom of the ladder, and a gap cannot be filled
before it has been measured. This is the measurement: every catalogue text placed on the
weekly's levels — Easy, Simplified, Native — by both halves of what the weekly checks
its own editions against, counted per language and per medium, with the texts that meet
the Easy spec in full counted against the target of a hundred a language (David,
2026-09-29).

**Both halves, because one was not enough.** The library's own number is the share of
words a learner looks up, and on its own it cannot tell the first two levels apart: the
weekly's easy edition measured 15% and its simplified one 14%, the wrong way round.
What separated them was words per sentence. So a text is placed by the share *and* the
sentence length, against `weekly.models.LEVELS`, the same bands an issue must fall in
before it may be published. One ruler for the week's writing and the shelf's, so a
reader told "Easy" in one place is told the same thing in the other.

**Placed by the ceilings, and the Easy spec counted separately.** A level's bands have a
floor as well as a ceiling, and the floor is there for the writer: it keeps an issue
from being written down to nothing. A shelf text under the floor is not unplaceable, it
is easier, so it is placed at the first level whose two ceilings it fits under, and
anything over Simplified's is Native, which is open-ended. The Easy spec itself — both
bands in full, floor and ceiling, and short enough to finish in a sitting — is the
stricter count, and the one the target is set in.

**Medium is asked of the disk,** exactly as the library asks it (`spoken.py`): a video
is a curated video or a recording that kept its pictures, audio is a recording or a
voiced dialogue, and everything else is text. #382's gap is spoken as well as easy, so
the map says which is which.

**A text with no sentence length yet is read off its build where one exists.** The
catalogue carries `sentence` from `scripts/measure_difficulty.py`; until a sweep has
written it, the map reads the segmentation a build left on disk, or segments a curated
video's document on the spot — free, local, and the same rule splitter a build runs.
Nothing is fetched and no model is asked. A text with neither is counted as unmeasured,
never as easy.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from math import ceil
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .catalogue import Entry
from .weekly.models import LEVELS, Level

if TYPE_CHECKING:
    from .coverage import Index
    from .segment import HebrewSegmenter

#: Texts a language should have that meet the Easy spec in full (David, 2026-09-29).
TARGET = 100

#: The languages the target was set for, the same day. Aramaic is on the shelf as the
#: Targum beside the Torah and nobody is looking for a hundred easy texts in it, so it
#: is counted and not held to a number.
TARGETED = frozenset({"he", "ru", "it", "fr"})

#: "Short" in the Easy spec, in the reading minutes the shelf prints for a text — about
#: three, at the 130 words a minute `Entry.minutes` reckons a learner manages.
EASY_MINUTES = 3

#: The three media, in the order the map prints them.
MEDIA = ("text", "audio", "video")

#: A row that has not been measured on one half or the other.
UNMEASURED = "unmeasured"


def place(difficulty: int, sentence: float) -> Level | None:
    """The first level whose two ceilings this text fits under, or None if unmeasured.

    Zero on either half is "not measured", as it is everywhere the catalogue is read: a
    text with no sentences counted is not a text of no sentences.
    """
    if difficulty <= 0 or sentence <= 0:
        return None
    for level in (Level.aleph, Level.bet):
        spec = LEVELS[level]
        if difficulty <= spec.band[1] and sentence <= spec.sentence[1]:
            return level
    return Level.gimel


def meets_easy(difficulty: int, sentence: float, minutes: int) -> bool:
    """Whether a text meets the Easy spec in full: both bands, floor and ceiling, and short."""
    spec = LEVELS[Level.aleph]
    low, high = spec.band
    shortest, longest = spec.sentence
    return (
        low <= difficulty <= high
        and shortest <= sentence <= longest
        and 0 < minutes <= EASY_MINUTES
    )


def medium(
    source: str,
    *,
    spoken: Callable[[str], bool],
    video: Callable[[str], bool],
) -> str:
    """Text, audio or video, asked the way the library asks it."""
    if source.startswith("video:") or video(source):
        return "video"
    if spoken(source):
        return "audio"
    return "text"


class Sentences:
    """Where a sentence length comes from when the catalogue row has none yet.

    The row first, because that is what a sweep wrote down. Then a build under `out`
    whose `document.json` names the same source — `library/` first where there are
    several, as `measure_difficulty.py` chooses, though segmentation does not depend on
    the copy. Then, for a curated video, its document on the video shelf, segmented here.
    """

    def __init__(self, out: Path | None = None, videos: Path | None = None) -> None:
        self.out = out
        self.videos = videos
        self._built: dict[str, Path] | None = None
        self._segmenter: HebrewSegmenter | None = None

    def built(self) -> dict[str, Path]:
        if self._built is None:
            found: dict[str, Path] = {}
            if self.out is not None and self.out.is_dir():
                folders = sorted(
                    self.out.glob("*/*/document.json"),
                    key=lambda path: (path.parent.parent.name != "library", str(path)),
                )
                for document in folders:
                    if not (document.parent / "segments.json").is_file():
                        continue
                    try:
                        source = json.loads(document.read_text(encoding="utf-8")).get("source")
                    except (OSError, ValueError):
                        continue
                    if isinstance(source, str) and source not in found:
                        found[source] = document.parent
            self._built = found
        return self._built

    def __call__(self, entry: Entry) -> float:
        if entry.sentence > 0:
            return entry.sentence
        from .annotate.difficulty import sentence_length
        from .models import Document, SegmentedDocument, read_artifact

        home = self.built().get(entry.source)
        if home is not None:
            segmented = read_artifact(SegmentedDocument, home / "segments.json")
            if segmented is not None:
                return sentence_length(segmented)
        if entry.source.startswith("video:") and self.videos is not None:
            document = read_artifact(
                Document, self.videos / entry.source.removeprefix("video:") / "document.json"
            )
            if document is not None:
                from .segment import HebrewSegmenter, segment_document

                if self._segmenter is None:
                    # No download: the rules split every language on the shelf, and a
                    # report must not reach the network to decide what to print.
                    self._segmenter = HebrewSegmenter(auto_download=False)
                return sentence_length(segment_document(document, self._segmenter))
        return 0.0


@dataclass
class Shelf:
    """One language's counts: by level and medium, and against the Easy target."""

    language: str
    #: (level name or UNMEASURED, medium) -> texts.
    cells: Counter[tuple[str, str]] = field(default_factory=Counter)
    easy: Counter[str] = field(default_factory=Counter)
    #: The Native texts again, by the text ruler (`native_level`): (B2, C1, C2 or
    #: `PAST_C2`, medium) -> texts. A Native text the ruler has not counted is on B2.
    native: Counter[tuple[str, str]] = field(default_factory=Counter)

    @property
    def total(self) -> int:
        return sum(self.cells.values())

    @property
    def easy_total(self) -> int:
        return sum(self.easy.values())

    @property
    def targeted(self) -> bool:
        return self.language in TARGETED


def tally(
    entries: Iterable[Entry],
    *,
    sentence: Callable[[Entry], float],
    spoken: Callable[[str], bool],
    video: Callable[[str], bool],
    native: Callable[[Entry], str] | None = None,
) -> dict[str, Shelf]:
    """Every entry counted into its language's shelf, languages in order of size.

    `native` places a Native text on B2, C1, C2 or Past C2 (`native_level` against the
    lemma index beside the catalogue, by default)."""
    if native is None:
        index = _catalogue_index()

        def native(entry: Entry) -> str:
            return native_level(entry, index)

    shelves: dict[str, Shelf] = {}
    for entry in entries:
        shelf = shelves.setdefault(entry.language, Shelf(entry.language))
        length = sentence(entry)
        level = place(entry.difficulty, length)
        how = medium(entry.source, spoken=spoken, video=video)
        shelf.cells[(level.value if level else UNMEASURED, how)] += 1
        if level is Level.gimel:
            shelf.native[(native(entry), how)] += 1
        if meets_easy(entry.difficulty, length, entry.minutes):
            shelf.easy[how] += 1
    return dict(sorted(shelves.items(), key=lambda item: (-item[1].total, item[0])))


#: The ladder the stage standard's floors are held to (David, 2026-10-25; design.md §12, "A
#: badge is a promise, checked"). Modern Hebrew, and every other language, whose rows carry
#: no register. The Tanakh is counted as a row of its own, and revival, rabbinic and
#: medieval Hebrew are counted and reported but held to no floor: before this a learner
#: told Hebrew had ninety texts at B1 was being counted forty-eight of Berdyczewski and
#: Brenner and fifty-four of the Tanakh, and fifty-three of modern Hebrew.
MODERN = "modern"


def ladder_of(entry: Entry) -> str:
    """Which ladder a row is counted on: `MODERN`, or its register where it is an older
    Hebrew. A row with no register is the modern ladder, which is every other language's."""
    register = entry.register.value
    return register if register and register != MODERN else MODERN


def split(entries: Iterable[Entry]) -> tuple[list[Entry], dict[str, list[Entry]]]:
    """The modern ladder's rows, and every other register's, each in the order given."""
    modern: list[Entry] = []
    others: dict[str, list[Entry]] = {}
    for entry in entries:
        ladder = ladder_of(entry)
        if ladder == MODERN:
            modern.append(entry)
        else:
            others.setdefault(ladder, []).append(entry)
    return modern, others


#: The media that count as a recording, for the stage standard's shelf floors.
RECORDED: tuple[str, ...] = ("audio", "video")


def cefr_rows(shelf: Shelf) -> dict[str, tuple[int, int]]:
    """The shelf on CEFR levels, as the stage standard states its floors (design.md §12,
    "A badge is a promise, checked", 2026-10-12): texts and texts with a recording at each.

    The ruler is the one above — three levels by hard share and sentence length — and the
    mapping is stated rather than measured: a text meeting the Easy spec in full is A1,
    the rest of Easy is A2, Simplified is B1. The Easy spec is a subset of Easy, so A2 is
    Easy less the spec. Native is split into B2, C1, C2 and Past C2 by the vocabulary a
    text needs (`native_level`, design.md §12, "Your level, v3", 2026-10-29), and `B2+`
    is still there as the four together: the stage standard's floors are stated at B2 and
    up, and old addresses name it. So the rows do not add up to the shelf — `B2+` is the
    last four again — and nothing should sum them.
    """
    easy = [shelf.cells[(Level.aleph.value, how)] for how in MEDIA]
    spec = [shelf.easy[how] for how in MEDIA]
    simplified = [shelf.cells[(Level.bet.value, how)] for how in MEDIA]
    native = [shelf.cells[(Level.gimel.value, how)] for how in MEDIA]
    recorded = [MEDIA.index(how) for how in RECORDED]

    def counted(cells: list[int]) -> tuple[int, int]:
        return sum(cells), sum(cells[at] for at in recorded)

    rows = {
        "A1": counted(spec),
        "A2": counted([have - met for have, met in zip(easy, spec, strict=True)]),
        "B1": counted(simplified),
    }
    for level in NATIVE_LEVELS:
        rows[level] = counted([shelf.native[(level, how)] for how in MEDIA])
    rows[NATIVE_ALIAS] = counted(native)
    return rows


#: The levels a Native text is split into by the text ruler, easiest first. Past C2 is
#: a text that needs more words than the top rung of its language's ladder.
PAST_C2 = "past-C2"
NATIVE_LEVELS: tuple[str, ...] = ("B2", "C1", "C2", PAST_C2)

#: Native as one level, B2 and up: what the Library's `#see/level/B2+` named until
#: 2026-10-29 and what the stage standard's floors are still stated at.
NATIVE_ALIAS = "B2+"

#: A text's own level, easiest first, as `cefr_rows` names them: the rows of Your
#: Progress's Level ladder (design.md §12, "Your level, v3", 2026-10-29) and the
#: Library's `#see/level/<level>`.
TEXT_LEVELS: tuple[str, ...] = ("A1", "A2", "B1", *NATIVE_LEVELS)

#: The share of a Native text's ranked running words the text ruler covers (design.md §12,
#: "Your level, v3"). Calibrated on 2026-10-29 against the laptop's built library, read
#: only (targum-internal#561): at 95%, as first specified, 10 of 11 Hebrew Native texts
#: and 37 of 59 texts the shelf calls A1 came out past vav, because the last few per cent
#: of any real text is its rarest words and a lemma list's misses. At 85%, with forms the
#: frequency list never ranked left out of the count, the shelf's A1 texts land on A2 to
#: B1 (51 of 59 at B1 or below), its A2 texts on A2 (19 of 24 at A2+ or below) and the
#: Native ones on B2 (7), C1 (3) and C2 (1), none past vav. `text_rung` reads a text at
#: 90% for the same reason (2026-09-27).
RULER_COVERAGE = 0.85

#: The ladders the ruler places a Native text on: the ulpan's, whose rungs are vocabulary
#: sizes a frequency rank can be held against. The European scale's rungs count known
#: words among the commonest five thousand, which is not a rank: held against one, 30 of
#: 46 Russian Native texts came out past C2 and 9 at A1. French, Russian and Italian
#: Native texts stay on B2 until that scale has a ruler of its own.
RULED = frozenset({"weighted"})


def ruler_rank(entry_id: str, language: str, index: Index) -> int | None:
    """The frequency rank that covers `RULER_COVERAGE` of a text's ranked running words, or
    None.

    Read off the lemma index's counts (each dictionary form and how often it comes round),
    each form ranked by its language's frequency list. A form the list never ranked is left
    out of the count rather than counted as past every rung: 4% of Hebrew running words on
    the built shelf, and nearly all of them are lemma spellings the surface-form list does
    not carry, transliterations and names the tagger missed, not rare words. None where
    the index has no counts for the text, the language has no list or nothing in the text
    is ranked: not measured, never easy.
    """
    from .annotate.frequency import rank, ranks

    positions = index.texts.get(entry_id)
    counts = index.counts.get(entry_id)
    if not positions or counts is None or not ranks(language):
        return None
    weighted: list[tuple[int, int]] = []
    for at, count in zip(positions, counts, strict=True):
        if count <= 0:
            continue
        found = rank(index.words[at], language)
        if found is not None:
            weighted.append((found, int(count)))
    total = sum(count for _, count in weighted)
    if not total:
        return None
    need = ceil(RULER_COVERAGE * total)
    covered = 0
    for at, count in sorted(weighted):
        covered += count
        if covered >= need:
            return at
    return max(weighted)[0]


def native_level(entry: Any, index: Index) -> str:
    """Where a Native text sits: B2, C1, C2 or `PAST_C2`, by the vocabulary it needs.

    The rank `ruler_rank` finds, against the thresholds the reader's level climbs: the
    ulpan's dalet, hey and vav (`level.ladder_for`; only a ladder in `RULED`). Never below
    B2, since the text is Native by the shelf's own ruler. B2 where the text cannot be
    measured, and for a language whose ladder is not ruled, as before the ruler (design.md
    §12, "Your level, v3", 2026-10-29). Cached per index, since the index is read once a file.
    """
    entry_id = str(getattr(entry, "id", ""))
    language = str(getattr(entry, "language", "") or "").split("-")[0].lower()
    held = _MEMO.get(id(index))
    if held is None or held[0] is not index:
        held = (index, {})
        _MEMO.clear()
        _MEMO[id(index)] = held
    key = (entry_id, language)
    if key not in held[1]:
        held[1][key] = _native_level(entry_id, language, index)
    return held[1][key]


#: The last index ruled and what it said, by entry: one at a time, so a re-read index
#: frees the old one.
_MEMO: dict[int, tuple[Index, dict[tuple[str, str], str]]] = {}


def _native_level(entry_id: str, language: str, index: Index) -> str:
    from .level import ladder_for

    ladder = ladder_for(language)
    ruled = ladder is not None and ladder.measure in RULED
    needed = ruler_rank(entry_id, language, index) if ruled else None
    if ladder is None or needed is None:
        return NATIVE_LEVELS[0]
    for level in NATIVE_LEVELS[:-1]:
        threshold = rung_at(ladder, level)
        if threshold is not None and needed <= threshold:
            return level
    return PAST_C2


def rung_at(ladder: Any, level: str) -> int | None:
    """The words a ladder wants for a CEFR level: the first rung reckoned at it. The
    ulpan names its CEFR beside each rung (A1 is aleph, B2 dalet, C1 hey); the European
    scale's rungs are the levels themselves. None for a level the ladder has no rung for,
    Past C2 among them."""
    for rung in ladder.rungs:
        if (rung.cefr or rung.name) == level:
            return int(rung.at)
    return None


def _catalogue_index() -> Index:
    """The lemma index beside the catalogue, or an empty one."""
    from . import catalogue as catalogue_module
    from .coverage import read_index

    return read_index(catalogue_module.lemmas_path())


def text_level(entry: Entry, index: Index | None = None) -> str:
    """One text's level on the rule `cefr_rows` counts by, or "" where it has none.

    The catalogue's own measures, `difficulty` and `sentence`, so the server and the
    Library's shelf files say the same thing without either reading a build: a text with
    no sentence length yet is unmeasured, never easy. A Native text is placed on B2, C1,
    C2 or Past C2 by `native_level`, against `index` (the lemma index beside the
    catalogue by default). An older Hebrew is on a ladder of its own (`ladder_of`) and
    has no modern level.
    """
    register = getattr(getattr(entry, "register", None), "value", "") or ""
    if register and register != MODERN:
        return ""
    difficulty = int(getattr(entry, "difficulty", 0) or 0)
    sentence = float(getattr(entry, "sentence", 0) or 0)
    placed = place(difficulty, sentence)
    if placed is None:
        return ""
    if placed is Level.aleph:
        minutes = int(getattr(entry, "minutes", 0) or 0)
        return "A1" if meets_easy(difficulty, sentence, minutes) else "A2"
    if placed is Level.bet:
        return "B1"
    return native_level(entry, _catalogue_index() if index is None else index)


def levels_named(level: str) -> tuple[str, ...]:
    """The text levels an address's level stands for: itself, or for the `B2+` alias the
    four Native levels, so an address written before 2026-10-29 still opens."""
    if level == NATIVE_ALIAS:
        return NATIVE_LEVELS
    return (level,) if level in TEXT_LEVELS else ()


def videos(shelf: Shelf) -> int:
    """Videos on the shelf at any level, measured or not: the second medium the stage
    standard asks of a Beta language (design.md §12)."""
    return sum(count for (_, how), count in shelf.cells.items() if how == "video")


def rows(shelf: Shelf) -> list[tuple[str, list[int]]]:
    """The shelf as printable rows: a label and one count per medium, then the total."""
    labelled = [(level.value, LEVELS[level].name) for level in Level] + [(UNMEASURED, "Unmeasured")]
    out: list[tuple[str, list[int]]] = []
    for key, name in labelled:
        counts = [shelf.cells[(key, how)] for how in MEDIA]
        out.append((name, [*counts, sum(counts)]))
    easy = [shelf.easy[how] for how in MEDIA]
    target = f" (target {TARGET})" if shelf.targeted else ""
    out.append((f"Easy spec{target}", [*easy, sum(easy)]))
    return out
