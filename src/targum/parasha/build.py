"""Building the corpus, and pointing the calendar at it.

Two passes over a set of years' readings. The first builds every distinct reading once —
the 54 portions, the doubled weeks, and the festival Shabbatot — because the corpus is
fixed and a portion built in one year is the same portion in every other. The second
writes the pointer: which Shabbat reads which, on each schedule.

Nothing here fetches a text or asks a model for anything. The books are already built,
the translation is already bought and cached, and a portion is a range of verses inside
them, so a rebuild costs the time it takes to write the files and no money at all. That
is what makes it safe to run this every week from a cron.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

from ..errors import TargumError
from ..paths import write_atomic
from ..render.builder import render
from .calendar import Reading, Schedule, always, root
from .calendar import year as readings_for
from .cut import BOOKS, MissingBook, books_for, cut, parse_ref
from .models import Index, Portion, Week

#: How many years of calendar to point at. Enough that a box which cannot reach Hebcal
#: for a while still knows what this Shabbat is, and few enough that a build is quick.
YEARS_AHEAD = 2

#: How many years to enumerate the *corpus* from, which is a different question and was
#: answered with the same number once, wrongly.
#:
#: Nineteen, because the Hebrew calendar repeats on the Metonic cycle: any nineteen
#: consecutive years hold every arrangement of leap year and festival, so each of the 54
#: portions is read on its own somewhere inside the span and is therefore cut. Two years
#: was enough to *point at* a Shabbat and not enough to *find* every portion — a pair
#: doubled on both schedules in both years is never emitted as a distinct reading, so it
#: is never cut and has no address. That is how Matot, Masei, Nitzavim and Vayeilech came
#: to be missing from a corpus that called itself fixed and finite, while the other five
#: doubled pairs had both halves: those five happen to split inside two years and these
#: two do not.
#:
#: No smaller number is safe, and the measurement is the argument: walking 2026 onward,
#: four years recovers Nitzavim and Vayeilech, and only ten recovers Matot and Masei. A
#: number chosen to cover what was observed would be right until the year it was not.
#: The cycle's own length is the one that cannot be wrong.
#:
#: It is not slow after the first run. Hebcal years are cached beside the corpus, so a
#: weekly cron reads thirty-eight files off the disk and fetches nothing; only a cold
#: cache pays, and it pays once.
CORPUS_YEARS = 19


def index_path() -> Path:
    return root() / "index.json"


#: The index and what a serve-time reader derives from it, cached the way the weekly's
#: is (`weekly/index.py`) and for the same reason: this file changes while the process is
#: up — a cron rebuilds it — so it is keyed on the file's own mtime and size rather than
#: read once, and it sits behind a lock because `ThreadingHTTPServer` hands every request
#: to a different thread. Without this every view of a portion cost a JSON parse plus a
#: stat of all 63 folders.
_lock = threading.Lock()
_cached: tuple[tuple[Path, int, int], Index, set[str]] | None = None


def _fresh() -> tuple[Index, set[str]]:
    """The index and its readable folders, both off one read of the file."""
    global _cached
    path = index_path()
    try:
        stat = path.stat()
    except OSError:
        return Index(), set()
    stamp = (path, stat.st_mtime_ns, stat.st_size)
    with _lock:
        if _cached is not None and _cached[0] == stamp:
            return _cached[1], _cached[2]
        try:
            index = Index.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            # A half-written or hand-edited index leaves the corpus absent rather than
            # taking the rest of the server down with it.
            return Index(), set()
        folders = {
            portion.folder
            for portion in index.portions.values()
            if (root() / "read" / portion.folder / "reader" / "index.html").is_file()
        }
        _cached = (stamp, index, folders)
        return index, folders


def load() -> Index:
    """The corpus on disk, or an empty one where nothing has been built."""
    return _fresh()[0]


def distinct(
    years: Iterable[int],
    schedules: Iterable[Schedule],
    *,
    allow_fetch: bool = True,
) -> dict[str, Reading]:
    """Every reading that appears in the window, once each.

    Keyed by slug, so a portion read on both schedules and in every one of the years is
    built once. The diaspora is walked first, so where the two disagree about what a
    reading is called the diaspora's name is the one that sticks — it is the schedule
    the page opens on.

    Public because the CLI's `leyning` command needs exactly this set and had a copy of
    the loop; two copies of "which readings exist" is two answers waiting to disagree.
    `allow_fetch=False` is what a command that only reads an existing corpus passes.
    """
    out: dict[str, Reading] = {}
    for schedule in schedules:
        for reading in always(schedule):
            out.setdefault(reading.slug, reading)
        for one in years:
            for reading in readings_for(one, schedule, allow_fetch=allow_fetch):
                out.setdefault(reading.slug, reading)
    return out


def build(
    *,
    years: Iterable[int] | None = None,
    corpus_years: Iterable[int] | None = None,
    schedules: Iterable[Schedule] = (Schedule.diaspora, Schedule.israel),
    library: Path | None = None,
    notify: Callable[[str], None] | None = None,
) -> Index:
    """Build every reading in the corpus and point the calendar at it.

    Two windows, not one. `corpus_years` is what gets built and is wide, because a
    portion has to be read on its own somewhere in the span to be cut at all. `years` is
    what gets pointed at and is narrow, because a pointer only has to reach as far as a
    box might go without Hebcal. Sharing one window meant the shelf lost whichever
    portions this year happened to double.

    Idempotent by construction: the same reading cut from the same books produces the
    same reader, so running it twice is running it once and writing the files again.
    """
    schedules = list(schedules)
    if years is None:
        years = range(date.today().year, date.today().year + YEARS_AHEAD)
    years = list(years)
    # The corpus widens by default, because the only caller that matters in production —
    # `targum parasha build` — always names its pointer years, and a default that only
    # widened when they were absent would have been correct in tests and inert on the
    # box. A caller that cannot reach nineteen years of calendar says so by naming
    # `corpus_years`; every test here does, which is also what keeps the suite off the
    # network.
    if corpus_years is None:
        first = min(years) if years else date.today().year
        corpus_years = range(first, first + CORPUS_YEARS)
    corpus_years = list(corpus_years)

    def say(message: str) -> None:
        if notify is not None:
            notify(message)

    index = Index(built_at=datetime.now(UTC).isoformat(timespec="seconds"))
    # The pointer's own years first, because those must be there or the page has nothing
    # to point at, and a failure in them is a real failure.
    readings = distinct(years, schedules)
    # Then the rest of the corpus span, a year at a time and best effort. A far year that
    # Hebcal will not answer for costs the four portions it might have carried; it must
    # not cost the build. Before the span widened this could not arise, so failing hard
    # here would be a new way for a working cron to start breaking.
    for one in [y for y in corpus_years if y not in set(years)]:
        try:
            for slug, reading in distinct([one], schedules).items():
                readings.setdefault(slug, reading)
        except TargumError as gone:
            say(f"  {one} is not reachable — the corpus is what the other years hold ({gone})")
    say(f"{len(readings)} readings across {len(corpus_years)} years")

    missing: set[str] = set()
    for slug in sorted(readings):
        reading = readings[slug]
        try:
            books = books_for(reading, library)
        except MissingBook as gone:
            # A book that is not on the shelf takes its readings with it and leaves the
            # rest of the corpus alone. Said once per book rather than once per reading,
            # which would be forty identical lines.
            if gone.book not in missing:
                missing.add(gone.book)
                say(f"  {gone.book} is not built — every reading in it is skipped")
            continue
        portion = cut(reading, books)
        folder = root() / "read" / slug
        # Sections, not one page. The aliyot are the sections, and a section is the unit
        # the recording is cut on and the unit whose audio the page carries — so one page
        # per aliyah is one chanted file per page. Built whole, a portion would want all
        # seven files inlined into one document, which is twelve megabytes nobody asked
        # for before they have read a word.
        render(
            portion.document,
            portion.segmented,
            portion.translations,
            folder / "reader",
            annotation=portion.annotation,
            glossaries=portion.glossaries,
            vocalization=portion.vocalization,
            clean=True,
            folder=folder,
        )
        opening, opening_ref = portion.opening()
        index.portions[slug] = Portion(
            slug=slug,
            name=reading.name,
            hebrew=reading.hebrew,
            kind=reading.kind,
            numbers=list(reading.numbers),
            summary=reading.summary,
            books=list(reading.books),
            verses=portion.verses,
            aliyot=len(reading.aliyot),
            opening=opening,
            opening_ref=opening_ref,
            folder=slug,
        )
        say(f"  {reading.name} — {portion.verses} verses")

    for schedule in schedules:
        for one in years:
            for reading in readings_for(one, schedule):
                if reading.slug not in index.portions:
                    continue
                index.weeks.append(
                    Week(
                        day=reading.day.isoformat(),
                        schedule=schedule,
                        slug=reading.slug,
                        hdate=reading.hdate,
                    )
                )
    index.weeks.sort(key=lambda w: (w.day, w.schedule.value))

    write_atomic(
        index_path(),
        json.dumps(index.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
    )
    say(f"{len(index.portions)} portions, {len(index.weeks)} weeks pointed")
    return index


#: The collection the portions sit in on the shelf. Its members are the corpus's to
#: own and are rewritten on every merge; its words are a person's to edit and are kept.
COLLECTION_ID = "torah-portions"


def entries(index: Index | None = None) -> list[dict[str, object]]:
    """The corpus as catalogue entries, for the library to list.

    Returned rather than written: the catalogue is the reader's own file and lives
    outside this repository, so this hands back what belongs in it and the caller — the
    CLI, with the path in front of it — decides where that goes.

    The byline is the book's Hebrew title, the way the five book rows carry theirs, so a
    portion listed under its collection reads like the row above it rather than like a
    label ("Torah · Genesis") somebody typed into a column meant for a name.
    """
    index = index or load()
    out: list[dict[str, object]] = []
    for portion in index.listed():
        out.append(
            {
                "id": f"parasha-{portion.slug}",
                "title": portion.hebrew or portion.name,
                "english": portion.name,
                "author": " · ".join(BOOKS.get(book, book) for book in portion.books),
                "language": "he",
                "source": f"sefaria:{portion.summary}",
                "blurb": f"{portion.summary}. {portion.verses} verses, seven aliyot.",
                "words": 0,
                "tags": ["tanakh"],
                "kind": "prose",
                "register": "biblical",
                "translations": [],
            }
        )
    return out


def collection(index: Index | None = None) -> dict[str, object] | None:
    """The portions as one ordered collection, so the shelf shows a path and not a pile.

    Fifty-four loose rows beside the `torah` collection is exactly the shape
    `catalogue.Collection` exists to prevent. This is the second door onto the same
    text: the five books stay where they are, and beside them the year, בראשית to
    וזאת הברכה in the order it is read. The members are `Index.listed()` in its order,
    which is what keeps a doubled build off the shelf wherever its halves are on it.

    None where the corpus is empty, rather than a collection of nothing.
    """
    index = index or load()
    members = [f"parasha-{portion.slug}" for portion in index.listed()]
    if not members:
        return None
    return {
        "id": COLLECTION_ID,
        "title": "פרשות השבוע",
        "english": "The Torah, by portion",
        "blurb": (
            "The five books cut into the fifty-four weekly readings, in the order of the year."
        ),
        "members": members,
        "ordered": True,
    }


@dataclass(frozen=True, slots=True)
class Start:
    """Where one portion begins inside its book, for a page that lists the book."""

    slug: str
    name: str
    hebrew: str
    chapter: int
    verse: int
    #: Hebcal's own range line: "Genesis 6:9-11:32".
    summary: str


def portions_for(book: str, index: Index | None = None) -> list[Start]:
    """Every listed portion that begins in one book, in the order they are read.

    For the contents page of a book the portions are cut from, so its chapters can be
    grouped under the portion each falls in. `book` may be the name Hebcal uses
    ("Genesis"), the Hebrew title the shelf files it under ("בראשית"), or the source the
    built book carries ("sefaria:Genesis") — the three names one book goes by, and any of
    them is the same question. Anything that is not one of the five answers with nothing,
    and so does an empty corpus: the layer is data, and a page with none renders as it
    always has.

    Read off the index at build time. A reader fetches nothing.
    """
    name = book.strip().removeprefix("sefaria:").strip()
    if name not in BOOKS:
        by_hebrew = {hebrew: english for english, hebrew in BOOKS.items()}
        name = by_hebrew.get(name, "")
    if not name:
        return []
    index = index or load()
    out: list[Start] = []
    for portion in index.listed():
        if not portion.books or portion.books[0] != name:
            continue
        # The first verse's own reference, or the front of the range line where an index
        # written before `opening_ref` existed has none.
        parsed = parse_ref(portion.opening_ref) or parse_ref(
            portion.summary.partition("-")[0].strip()
        )
        if parsed is None or parsed[0] != name:
            continue
        out.append(
            Start(
                slug=portion.slug,
                name=portion.name,
                hebrew=portion.hebrew,
                chapter=parsed[1].chapter,
                verse=parsed[1].verse,
                summary=portion.summary,
            )
        )
    out.sort(key=lambda one: (one.chapter, one.verse))
    return out


def readable(index: Index | None = None) -> set[str]:
    """Every folder that actually has a built reader in it.

    Off the same cached read as `load`, so serving a page is one `stat` of the index
    rather than one of every portion in it. A caller that hands in an index it built
    itself — the build does — still gets the folders checked directly.
    """
    if index is None:
        return _fresh()[1]
    return {
        portion.folder
        for portion in index.portions.values()
        if (root() / "read" / portion.folder / "reader" / "index.html").is_file()
    }


def current(
    schedule: Schedule = Schedule.diaspora,
    moment: datetime | None = None,
    index: Index | None = None,
) -> Portion | None:
    """What is read this Shabbat, off the index rather than off the network."""
    from .calendar import pointing_at

    index = index or load()
    return index.on(pointing_at(moment).isoformat(), schedule)
