"""Table 5, `difficulty`: how hard a word is found at each level, pooled across readers
(targum-internal#586; spec `docs/language-tables-2026-10-30.md` §5 in targum-internal;
design.md §12, "How hard a word is, counted across readers").

Each night `targum tables pool` reads the account database's record of use and counts,
per (dictionary form, rung):

- **exposed**: the readers who finished a section the word is in;
- **lookups**: how often it was looked up;
- **known**: the readers who marked it known (`word`, any source but `claimed`);
- **skips**: how often it sat in a section the reader marked finished and they neither
  looked it up in that text nor have it marked known (David, 2026-10-30);
- **readers**: the readers behind the cell at all, which is what the floor is drawn on.

The rung is the one `level.py` gave the reader at the time of each event, worked out
from when each of their known words became known (`known_at`, else `at`), the rung they
named on arrival standing in while nothing is measured, as `level.seed` lets it.

The rules, each of which a test holds:

- **No person, no document, no text in a row.** A tally's key is a dictionary form and
  its variant is a rung and a measure; the contribution's unit is the night, `pool-<date>`.
  Who did what is worked out in memory and only the counts are written.
- **Made afresh every night, and only one night is kept.** The night's pool is put in
  place of the last one in one transaction, and the last one is deleted, not superseded
  (`Store.replace_difficulty`): a night kept beside the next is a diff, and the diff
  between two nights is what one reader who left brought. So a reader who erases their
  record (`Store.forget_events`), turns it off, or leaves is gone from the file by the
  next morning, as clause 3.7 says.
- **Everything a reader is counted for hangs off their record.** Exposure and skips come
  from `section` events and lookups from `lookup` events, never from the synced `section`
  table, and a mark counts only for a word the record has them meeting or looking up in a
  counted text. With the record erased nothing is left to count them by, marks included.
- **Operators are not readers.** The operator's addresses, admins, test accounts, anybody
  who has asked to leave and anybody who has turned the record off are never read
  (`accounts.Store.pooled_readers`).
- **Public, redistributable texts only.** A document counts when the tables may count it
  (`tables.public_text`: not in a reader's home, not a private import, a kind listed
  public in `kinds.PUBLIC_KINDS`) and its licence lets it be redistributed
  (`licensing.exportable`). A `course` book, an upload, a pasted link: never.
- **A cell under the floor reads as absent.** It is written, with the rest of the night,
  and `cell` answers None for it: a number is used only once `FLOOR` distinct readers
  stand behind it, the privacy notice's "at least ten Data Subjects".
- **No count of readers leaves this module.** `cell` answers shares, never a head count,
  so nothing downstream can print one. Nothing on a page reads this table yet.
- **Not before the notice says so.** `notice_carries_clause` is what the nightly job asks
  first: the privacy notice the running service serves must carry `CLAUSE` word for word.

Reads the account database and the built folders' `annotation.json` files (through
`occurrences`); runs no annotator and spends nothing.
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
from bisect import bisect_left
from collections import Counter
from collections.abc import Collection, Iterable
from contextlib import closing
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from html import unescape
from pathlib import Path

from .. import ledger as ledger_module
from .registers import in_language
from .store import DIFFICULTY, Contribution, Store

log = logging.getLogger(__name__)

__all__ = ["CLAUSE", "DIFFICULTY", "FLOOR", "Cell", "PoolResult", "cell", "pool"]

#: How many distinct readers a (word, rung) cell needs before any number in it is used
#: (David, 2026-10-30: ten, not the twenty the spec proposed). The notice says "at least
#: ten Data Subjects"; `test_tables_difficulty` holds the two together.
FLOOR = 10

#: The pooling rule's version, the contributions' `tool` and `rule`: a change to who is
#: read or what is counted is a new number.
RULE = f"difficulty/1+floor{FLOOR}"

SOURCE = "readers' record of use"
LICENCE = "counts only, no reader, no document; public redistributable texts only"

#: The measures a cell holds, as the variant's second half.
READERS = "readers"
EXPOSED = "exposed"
LOOKUPS = "lookups"
KNOWN = "known"
SKIPS = "skips"
MEASURES = (READERS, EXPOSED, LOOKUPS, KNOWN, SKIPS)

#: The rung of a reader whose level has nothing measured or named behind it yet.
UNRANKED = "unranked"

#: Where the running service serves the privacy notice, on the box.
NOTICE = "http://127.0.0.1:8420/privacy"

#: The sentence clause 3.7 carries for this pool, word for word as David approved it on
#: 2026-10-30 (targum-internal#586) with the floor at ten. The nightly job refuses unless
#: the notice the service serves carries it, so the pool cannot run before the clause is
#: live, nor go on running if the clause is ever taken out.
CLAUSE = (
    "Also counts, across all Data Subjects and bearing no identifier of any of them, of how"
    " often each word, in its dictionary form, was looked up, marked as known, or passed"
    " over in a section marked as finished, grouped by the level the Service had assigned"
    " to the reader at the time, confined to documents the licence of which permits their"
    " redistribution and made in no respect of material uploaded by a Data Subject; no such"
    " count is used unless it is drawn from at least ten Data Subjects, and each count is"
    " made afresh daily, so that records erased under clause 3.6 cease to contribute to it."
    " Processed for the purpose of measuring how difficult each word is found at each"
    " level. Legal basis: Article 6(1)(f)."
)


def said(markup: str) -> str:
    """The prose of a page, with its markup and its line-wrapping gone, as a reader meets
    it and as `test_legal` reads it."""
    markup = re.sub(r"<(style|script)[^>]*>.*?</\1>", " ", markup, flags=re.S)
    return " ".join(unescape(re.sub(r"<[^>]+>", " ", markup)).split())


def notice_carries_clause(page: str) -> bool:
    """Whether a served privacy notice carries `CLAUSE`, word for word."""
    return CLAUSE in said(page)


def fetch_notice(address: str = NOTICE, *, timeout: float = 10) -> str | None:
    """The privacy notice as the running service serves it, or None where it could not be
    read: the service down, the legal pages shut (404), anything but a page."""
    from urllib.error import URLError
    from urllib.request import urlopen

    try:
        with urlopen(address, timeout=timeout) as answer:  # noqa: S310 - a fixed local address
            status = getattr(answer, "status", 200)
            if status is not None and status != 200:
                return None
            return bytes(answer.read()).decode("utf-8", "replace")
    except (URLError, OSError, ValueError):
        return None


@dataclass(frozen=True)
class Cell:
    """One word at one rung, pooled: shares only, never a count of readers.

    `looked_up` is lookups per reader behind the cell; `known` the share of those readers
    who marked it known; `skipped` the finished sections it was passed over in, per reader
    who met it in one. None where there was nobody to divide by.
    """

    looked_up: float | None
    known: float | None
    skipped: float | None


def _per(n: int, of: int) -> float | None:
    return round(n / of, 4) if of > 0 else None


def cell(lemma: str, rung: str, language: str = "he", store: Store | None = None) -> Cell | None:
    """How hard one word is found at one rung, or None: under the floor, never counted,
    or the ledger off. A cell under `FLOOR` distinct readers is written and reads as
    absent, here and everywhere, since this is the only reader of the table."""
    store = store if store is not None else Store.from_env()
    if store is None or not lemma:
        return None
    held = store.counts(DIFFICULTY, lemma, in_language(DIFFICULTY, language))
    measured = {measure: int(held.get(f"{rung}|{measure}", 0)) for measure in MEASURES}
    if measured[READERS] < FLOOR:
        return None
    return Cell(
        looked_up=_per(measured[LOOKUPS], measured[READERS]),
        known=_per(measured[KNOWN], measured[READERS]),
        skipped=_per(measured[SKIPS], measured[EXPOSED]),
    )


# -- the night's pool -------------------------------------------------------------------


@dataclass
class PoolResult:
    """What one night's pool did. Counts of readers and texts, never which."""

    readers: int = 0
    #: The public, redistributable texts that could be counted tonight.
    documents: int = 0
    #: Events about a text that is not one of those: a reader's home, a private import,
    #: a licence that does not let it leave, or a text no longer built.
    withheld: int = 0
    #: Cells written, and of them the ones under the floor (written, read as absent).
    cells: int = 0
    under_floor: int = 0
    by_language: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class _Text:
    folder: Path
    language: str


def _code(language: str) -> str:
    return (language or "").split("-")[0].lower()


def counted_texts(library: Path) -> dict[str, _Text]:
    """Every built text under `library` the pool may count, by its content hash: public
    to the tables (`tables.public_text`) and under a licence that lets it leave
    (`licensing.exportable`). A reader's home is never among them."""
    from ..licensing import exportable
    from . import public_text

    found: dict[str, _Text] = {}
    for folder in ledger_module.text_folders(library):
        text = public_text(folder, library)
        if text is None or not exportable(text.licence):
            continue
        try:
            document = json.loads((folder / "document.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        language = _code(str(document.get("language") or "")) if isinstance(document, dict) else ""
        found.setdefault(text.document_hash, _Text(folder, language or "he"))
    return found


class _Ladder:
    """One reader's rung in one language at any moment, from when each known word became
    known: the ladder `level.snapshot` climbs, replayed."""

    def __init__(self, language: str, words: Iterable[tuple[str, int]], declared: str) -> None:
        from .. import level

        self.ladder = level.ladder_for(language)
        self.times: list[int] = []
        self.totals: list[float] = []
        self.seed = ""
        if self.ladder is None:
            return
        weighted = self.ladder.measure == "weighted"
        total = 0.0
        for band, at in sorted(words, key=lambda one: one[1]):
            if band in level.NOT_VOCABULARY:
                continue
            if weighted:
                total += level.BAND_WEIGHT.get(band, level.UNRATED_WEIGHT)
            elif band in level.COMMON_BANDS:
                total += 1
            else:
                continue
            self.times.append(at)
            self.totals.append(total)
        if language == "he" and declared:
            name = declared.replace("-", " ")
            self.seed = next((rung.name for rung in level.ULPAN if rung.name == name), "")

    def at(self, moment: int) -> str:
        """The rung at `moment` (ms), from the words known before it."""
        from .. import level

        if self.ladder is None:
            return UNRANKED
        index = bisect_left(self.times, moment)
        reached = self.totals[index - 1] if index else 0.0
        here, _ = level.standing(reached, self.ladder.rungs)
        if here is not None:
            return here.name
        return self.seed or UNRANKED


def _moment(at: object, day: object) -> int:
    """When an event happened, in ms: its own stamp, else the end of its day."""
    stamp = at if isinstance(at, int) and not isinstance(at, bool) else 0
    if stamp > 0:
        return stamp
    try:
        when = date.fromisoformat(str(day)[:10]) + timedelta(days=1)
    except ValueError:
        return 0
    return int(datetime(when.year, when.month, when.day, tzinfo=UTC).timestamp() * 1000) - 1


def pool(
    library: Path,
    store: Store,
    accounts: sqlite3.Connection,
    readers: Collection[int],
    *,
    today: date | None = None,
) -> PoolResult:
    """Make tonight's difficulty pool and put it in place of last night's.

    `accounts` is the account database, opened read-only; `readers` the person ids whose
    record may be read (`accounts.Store.pooled_readers`), every other person passed over.
    """
    from .. import occurrences
    from ..level import KNOWN as KNOWN_STATUS

    result = PoolResult()
    texts = counted_texts(library)
    result.documents = len(texts)
    wanted = sorted(int(one) for one in readers)
    result.readers = len(wanted)
    people = json.dumps(wanted)
    accounts.row_factory = sqlite3.Row

    # Each reader's words, for their ladder and for what they have marked known.
    timeline: dict[tuple[int, str], list[tuple[str, int]]] = {}
    known_now: dict[int, dict[str, set[str]]] = {}
    marks: list[tuple[int, str, str, int]] = []
    for row in accounts.execute(
        "SELECT person, language, lemma, band, source, at, known_at FROM word"
        " WHERE gone = 0 AND status = ? AND person IN (SELECT value FROM json_each(?))",
        (KNOWN_STATUS, people),
    ):
        person, language = int(row["person"]), _code(str(row["language"]))
        moment = int(row["known_at"] if row["known_at"] is not None else row["at"] or 0)
        timeline.setdefault((person, language), []).append((str(row["band"] or ""), moment))
        known_now.setdefault(person, {}).setdefault(language, set()).add(str(row["lemma"]))
        if str(row["source"] or "") != "claimed":
            marks.append((person, language, str(row["lemma"]), moment))
    declared: dict[int, str] = {}
    for row in accounts.execute(
        "SELECT id, declared FROM person WHERE id IN (SELECT value FROM json_each(?))", (people,)
    ):
        declared[int(row["id"])] = str(row["declared"] or "")
    ladders: dict[tuple[int, str], _Ladder] = {}

    def rung(person: int, language: str, moment: int) -> str:
        key = (person, language)
        if key not in ladders:
            ladders[key] = _Ladder(language, timeline.get(key, ()), declared.get(person, ""))
        return ladders[key].at(moment)

    #: (language, lemma, rung) -> measure -> n, and the readers behind each cell.
    counts: dict[tuple[str, str, str], Counter[str]] = {}
    behind: dict[tuple[str, str, str], set[int]] = {}
    exposed: dict[tuple[str, str, str], set[int]] = {}
    #: What each reader's record has them meeting or looking up, per language: a mark
    #: counts only for one of these, so an erased record takes the marks with it.
    evidenced: dict[tuple[int, str], set[str]] = {}
    looked: dict[tuple[int, str], set[str]] = {}

    for row in accounts.execute(
        "SELECT person, document, language, word, day, at FROM event WHERE kind = 'lookup'"
        " AND word <> '' AND person IN (SELECT value FROM json_each(?))",
        (people,),
    ):
        document = str(row["document"])
        text = texts.get(document)
        if text is None:
            result.withheld += 1
            continue
        person, word = int(row["person"]), str(row["word"])
        language = _code(str(row["language"])) or text.language
        cell_key = (language, word, rung(person, language, _moment(row["at"], row["day"])))
        counts.setdefault(cell_key, Counter())[LOOKUPS] += 1
        behind.setdefault(cell_key, set()).add(person)
        looked.setdefault((person, document), set()).add(word)
        evidenced.setdefault((person, language), set()).add(word)

    # Each finished section once a reader, at its first finish: (document) -> person ->
    # section -> moment.
    finished: dict[str, dict[int, dict[int, int]]] = {}
    for row in accounts.execute(
        "SELECT person, document, segment, day, at FROM event WHERE kind = 'section'"
        " AND person IN (SELECT value FROM json_each(?))",
        (people,),
    ):
        document = str(row["document"])
        if document not in texts:
            result.withheld += 1
            continue
        try:
            section = int(str(row["segment"]))
        except ValueError:
            continue
        moment = _moment(row["at"], row["day"])
        sections = finished.setdefault(document, {}).setdefault(int(row["person"]), {})
        if section not in sections or moment < sections[section]:
            sections[section] = moment

    for document, by_person in finished.items():
        text = texts[document]
        counted = occurrences.text_occurrences(text.folder)
        if counted is None:
            continue
        in_section: dict[int, set[str]] = {}
        for lemma, flat in counted.lemmas.items():
            for place in flat[0::2]:
                if place < len(counted.places):
                    in_section.setdefault(counted.places[place][0], set()).add(lemma)
        language = text.language
        for person, sections in by_person.items():
            knows = known_now.get(person, {}).get(language, set())
            asked = looked.get((person, document), set())
            seen = evidenced.setdefault((person, language), set())
            for section, moment in sections.items():
                here = rung(person, language, moment)
                for lemma in in_section.get(section, ()):
                    cell_key = (language, lemma, here)
                    exposed.setdefault(cell_key, set()).add(person)
                    behind.setdefault(cell_key, set()).add(person)
                    tally = counts.setdefault(cell_key, Counter())
                    if lemma not in asked and lemma not in knows:
                        tally[SKIPS] += 1
                    seen.add(lemma)

    for person, language, lemma, moment in marks:
        if lemma not in evidenced.get((person, language), ()):
            continue
        cell_key = (language, lemma, rung(person, language, moment))
        counts.setdefault(cell_key, Counter())[KNOWN] += 1
        behind.setdefault(cell_key, set()).add(person)

    night = (today or datetime.now(UTC).date()).isoformat()
    by_language: dict[str, dict[tuple[str, str], int]] = {}
    for cell_key, people_behind in behind.items():
        language, lemma, here = cell_key
        tally = counts.get(cell_key, Counter())
        rows = by_language.setdefault(language, {})
        rows[(lemma, f"{here}|{READERS}")] = len(people_behind)
        rows[(lemma, f"{here}|{EXPOSED}")] = len(exposed.get(cell_key, ()))
        for measure in (LOOKUPS, KNOWN, SKIPS):
            rows[(lemma, f"{here}|{measure}")] = int(tally.get(measure, 0))
        result.cells += 1
        result.by_language[language] = result.by_language.get(language, 0) + 1
        if len(people_behind) < FLOOR:
            result.under_floor += 1
    made = [contribution(language, night) for language in sorted(by_language)]
    store.replace_difficulty(made, {one.id: by_language[_language_of(one)] for one in made})
    return result


def contribution(language: str, night: str) -> Contribution:
    """The night's contribution for one language: its unit is the night, `pool-<date>`,
    never a document or a reader."""
    unit = f"pool-{night}" if language == "he" else f"{language}:pool-{night}"
    return Contribution(
        table=DIFFICULTY,
        register=in_language(DIFFICULTY, language),
        unit=unit,
        source=SOURCE,
        licence=LICENCE,
        tool=RULE,
        rule=RULE,
    )


def _language_of(made: Contribution) -> str:
    head, sep, _ = made.register.partition(":")
    return head if sep else "he"


def read_only(file: Path) -> sqlite3.Connection:
    """The account database, opened so the pool cannot write to it."""
    return sqlite3.connect(f"file:{file}?mode=ro", uri=True)


def clear(store: Store) -> bool:
    """Delete the pool, every night of it. True when there was one."""
    return store.clear_difficulty()


def held(store: Store) -> list[str]:
    """The units the pool holds now: one night, or none."""
    if not store.file.is_file():
        return []
    with closing(sqlite3.connect(store.file)) as db:
        try:
            return [
                str(row[0])
                for row in db.execute(
                    "SELECT unit FROM contribution WHERE tbl = ? ORDER BY unit", (DIFFICULTY,)
                )
            ]
        except sqlite3.Error:
            return []
