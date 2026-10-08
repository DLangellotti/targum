"""Where a word comes round: per text, across the library, and where a reader met it.

The index under targum-internal#95 ("met in Jonah 1:4, Ruth 2:1") and #96 ("4× in
Jonah, 12× in the Tanakh"). Built with no UI on David's call of 2026-09-27; since
2026-09-28 the word card reads it, behind `TARGUM_OCCURRENCES`, off unless the deployment
says so (`serve.shows_occurrences`), because neither card's gate can be met while there
are no readers to meet it.

**Nothing here is a source of truth.** Every number is derived from the annotation a
build already writes beside each reader, and can be thrown away and rebuilt from it:

- **In one text** — `text_occurrences(folder)` reads `annotation.json` and
  `segments.json` and keeps, for each dictionary form, the places it comes round (a
  section number and the verse reference where the segment carries one) with a count
  at each. Cached beside the annotation as `occurrences.json`, stamped with the files it
  was read from, written on first ask the way `coverage.lemmas` writes `lemmas.json`.
  So it costs nothing for a text nobody asks about, and works for texts built before
  today.
- **Across the library** — the catalogue's lemma index (`coverage.Index`, written by
  `targum catalogue-lemmas`) now carries a running count beside each entry's words, so
  `Index.count_in` and `Index.count_across` answer "how often in this text" and "how
  often across the shelf, or across one register" without opening a build. `across`
  below narrows by register. The Tanakh has its own answer that needs no build at all:
  `in_tanakh` sums the chapter file that already ships in the package.
- **Where a reader met it** — `met`, from the sections they have finished; and `family`,
  the words of one root a reader has met, from the root the annotation already carries.

**"Met" means a section the reader finished.** Three definitions were on the table, and
the store holds the data for each:

- *opened* (`doc`): a text opened is the whole text, and Genesis is one document — a
  reader who opened it and read a page would be told they met every word in fifty
  chapters. Too wide to say "met in" about.
- *marked* (`word`): a mark is filed by dictionary form with no place, so it says
  *that* somebody has the word and never *where* — which is the whole of the line.
- *read past* (`section`): one row per chapter the reader finished, synced across
  devices since targum-internal#173, un-finished as a `gone` row, and the same rows
  `coverage.section_reading` already measures on finish (#291). It carries a place,
  and a finished chapter is one the reader actually went through.

So a meeting is a place the word comes round inside a section with a live `section`
row. It undercounts a chapter read and never finished, and says so by not claiming it,
which is the right way round for a line that tells somebody what they have done.

**Memory.** The box is 7.7 GB and was OOM-killed before. Nothing here holds more than one
text's annotation at a time; `met` reads one text's cached places at a time and keeps
only the matches; the library counts ride in the index the server already holds, as
four-byte arrays. Nothing is annotated, bought or renamed: the annotator and
`SCHEMA_VERSION` are untouched, so building this index is free in money and in time.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterable, Iterator, Mapping
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING

from .coverage import ANNOTATION, Index, read_map
from .paths import write_atomic

if TYPE_CHECKING:
    from .models import SegmentedDocument

#: The cached file's name, beside `annotation.json`.
OCCURRENCES = "occurrences.json"

#: The file's shape. Bumped when the encoding changes; an older file is then rebuilt,
#: which is free — it is read off the annotation, not off a model. 2 added the roots.
VERSION = 2


@dataclass(frozen=True)
class Place:
    """One place a word comes round: the section the reader's page calls it by, the
    verse reference where the text has one ("" where it does not), and how many times."""

    section: int
    ref: str
    count: int


@dataclass(frozen=True)
class Occurrences:
    """Every dictionary form in one built text, and where each one comes round.

    `places` is the text's places in reading order, as (section, ref); `lemmas` maps a
    dictionary form to a flat run of (place, count) pairs into it, in the same order;
    `roots` maps a form to the root its annotation gave it, where it gave one.
    """

    places: tuple[tuple[int, str], ...]
    lemmas: dict[str, tuple[int, ...]]
    roots: dict[str, str] = field(default_factory=dict)

    def count(self, lemma: str) -> int:
        """How many running words in the text have this dictionary form."""
        return sum(self.lemmas.get(lemma, ())[1::2])

    def where(self, lemma: str, sections: Iterable[int] | None = None) -> list[Place]:
        """Every place this form comes round, in reading order; only in `sections`
        where they are named."""
        wanted = None if sections is None else set(sections)
        flat = self.lemmas.get(lemma, ())
        out: list[Place] = []
        for at, count in zip(flat[0::2], flat[1::2], strict=True):
            if at >= len(self.places):
                continue
            section, ref = self.places[at]
            if wanted is None or section in wanted:
                out.append(Place(section=section, ref=ref, count=count))
        return out

    def totals(self) -> dict[str, int]:
        """Each dictionary form's running count in the whole text — what the catalogue
        index keeps beside the form."""
        return {lemma: sum(flat[1::2]) for lemma, flat in self.lemmas.items()}


def _sections(folder: Path, segmented: SegmentedDocument) -> dict[str, int]:
    """Each segment's section number, as the reader's page numbers it.

    The same rule `coverage.section_lemmas` finds a finished section by, so a place here
    and a `section` row name the same stretch of text: a text rendered whole is one
    section of everything; otherwise the build's own split.
    """
    from .render.builder import split_sections

    written = len(list((folder / "reader").glob("sec-*.html")))
    if written <= 1:
        return {segment.id: 1 for segment in segmented.segments}
    return {sid: part.number for part in split_sections(segmented) for sid in part.segment_ids}


def _stamp(folder: Path) -> list[int] | None:
    """What the cache was read from, so a rewritten annotation or a re-split reader is a
    miss rather than a stale answer — the reason `coverage.lemmas` stamps its cache."""
    try:
        annotation = (folder / ANNOTATION).stat()
        segments = (folder / "segments.json").stat()
    except OSError:
        return None
    return [
        annotation.st_mtime_ns,
        annotation.st_size,
        segments.st_mtime_ns,
        segments.st_size,
        len(list((folder / "reader").glob("sec-*.html"))),
    ]


def _from(loaded: object) -> Occurrences | None:
    if not isinstance(loaded, dict) or loaded.get("version") != VERSION:
        return None
    places = tuple((int(p[0]), str(p[1])) for p in loaded.get("places") or ())
    lemmas = {
        str(lemma): tuple(int(n) for n in flat)
        for lemma, flat in (loaded.get("lemmas") or {}).items()
        if isinstance(flat, list) and len(flat) % 2 == 0
    }
    roots = {str(lemma): str(root) for lemma, root in (loaded.get("roots") or {}).items()}
    return Occurrences(places=places, lemmas=lemmas, roots=roots)


def count_text(folder: Path) -> Occurrences | None:
    """Read one built text's occurrences off its annotation, uncached.

    The same words `coverage.lemmas` counts: names and numbers left out, and a post's
    hashtags, mentions and addresses left out as the page leaves them out. None where the
    text has no word-level annotation or no segments — not counted, which is a different
    claim from a text with no words.
    """
    from .annotate.base import NOT_A_WORD, not_vocabulary
    from .ingest import post as post_module
    from .models import SegmentedDocument, read_artifact

    annotation = folder / ANNOTATION
    segmented = read_artifact(SegmentedDocument, folder / "segments.json")
    if segmented is None or not annotation.is_file():
        return None
    try:
        tokens = json.loads(annotation.read_text(encoding="utf-8")).get("tokens") or {}
    except (OSError, json.JSONDecodeError, AttributeError):
        return None
    section_of = _sections(folder, segmented)
    unwordly = post_module.left_out(folder) or {}

    place_at: dict[tuple[int, str], int] = {}
    # lemma -> place -> count, insertion-ordered, so a lemma's places stay in reading order.
    tally: dict[str, dict[int, int]] = {}
    roots: dict[str, str] = {}
    for segment in segmented.segments:
        found = tokens.get(segment.id)
        if not found:
            continue
        spans = unwordly.get(segment.id)
        key = (section_of.get(segment.id, 1), segment.ref or "")
        for token in found:
            lemma = str(token.get("lemma") or "")
            if lemma in NOT_A_WORD or not_vocabulary(token.get("pos"), token.get("entity")):
                continue
            if spans and post_module.inside(
                int(token.get("start") or 0), int(token.get("end") or 0), spans
            ):
                continue
            at = place_at.setdefault(key, len(place_at))
            row = tally.setdefault(lemma, {})
            row[at] = row.get(at, 0) + 1
            if token.get("root") and lemma not in roots:
                roots[lemma] = str(token["root"])
    # Drop the parsed annotation before building the answer: Jeremiah's is 10 MB on disk
    # and several times that as objects, and it is the one large thing here.
    del tokens
    return Occurrences(
        places=tuple(place_at),
        lemmas={
            lemma: tuple(n for at, count in row.items() for n in (at, count))
            for lemma, row in tally.items()
        },
        roots=roots,
    )


def text_occurrences(folder: Path) -> Occurrences | None:
    """One built text's occurrences, from the cache beside it or read and cached now.

    A cache that cannot be written costs the cache, not the answer.
    """
    stamp = _stamp(folder)
    if stamp is None:
        return None
    return _cached(folder, tuple(stamp))


@lru_cache(maxsize=8)
def _cached(folder: Path, stamp: tuple[int, ...]) -> Occurrences | None:
    """The parse, kept while the files it came from are unchanged. Eight texts, not all
    of them: a reader's finished chapters span a handful of books, and a bounded cache is
    the point on a box with 7.7 GB."""
    cached = folder / OCCURRENCES
    if cached.is_file():
        try:
            loaded = json.loads(cached.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            loaded = None
        if isinstance(loaded, dict) and loaded.get("stamp") == list(stamp):
            found = _from(loaded)
            if found is not None:
                return found
    counted = count_text(folder)
    if counted is None:
        return None
    try:
        write_atomic(
            cached,
            json.dumps(
                {
                    "version": VERSION,
                    "stamp": list(stamp),
                    "places": [list(place) for place in counted.places],
                    "lemmas": {lemma: list(flat) for lemma, flat in counted.lemmas.items()},
                    "roots": counted.roots,
                },
                ensure_ascii=False,
                separators=(",", ":"),
            ),
        )
    except OSError:
        pass
    return counted


# -- across the library -----------------------------------------------------------------


def across(index: Index, lemma: str, register: str = "", language: str = "") -> tuple[int, int]:
    """How often a dictionary form comes round across the counted catalogue, and in how
    many texts: all of it, or one register (`catalogue.Register`) or language of it.

    Only entries with a built, counted copy on this machine answer — which on the box is
    what the seed and the rebuild leave on the shelf — so this is "across the library as
    counted", never "across everything ever written in the register".
    """
    if not register and not language:
        return index.count_across(lemma)
    from . import catalogue as catalogue_module

    wanted = [
        entry.id
        for entry in catalogue_module.everything()
        if (not register or str(entry.register) == register)
        and (not language or entry.language.split("-")[0] == language)
    ]
    return index.count_across(lemma, wanted)


def in_tanakh(lemma: str, language: str = "he", path: Path | None = None) -> int:
    """How many running words of the Tanakh have this dictionary form.

    Read from the chapter file that ships in the package (`coverage.MAP`), counted off
    the Open Scriptures tagging and filed by `headword_of` — the key a reader's marks on
    scripture are kept under — so it needs no build and answers the same on every box.
    0 for a form the Tanakh does not have in that language.
    """
    return _tanakh_totals(path, language).get(lemma, 0)


@lru_cache(maxsize=4)
def _tanakh_totals(path: Path | None, language: str) -> dict[str, int]:
    """Every form's Tanakh total, summed once. A few thousand entries a language."""
    chapters = read_map(path)
    table = chapters.words.get(language, ())
    totals: dict[str, int] = {}
    for chapter in chapters.chapters.values():
        part = chapter.parts.get(language)
        if part is None:
            continue
        for at, count in zip(part.positions, part.counts, strict=True):
            if at < len(table):
                totals[table[at]] = totals.get(table[at], 0) + count
    return totals


# -- where a reader met it ---------------------------------------------------------------


@dataclass(frozen=True)
class Meeting:
    """One place a reader met a word: the document (its content hash, the `doc` and
    `section` tables' key), the section, the verse reference where there is one, how
    many times it came round there, and when that section was finished."""

    document: str
    section: int
    ref: str
    count: int
    at: int


#: Finds a document's built folder and language from its content hash —
#: `Library.document_folder(homes, hash)` on the server.
FolderFor = Callable[[str], tuple[Path, str] | None]


def met(
    lemma: str,
    finished: Iterable[tuple[str, str, int]],
    folder_for: FolderFor,
    language: str = "",
) -> list[Meeting]:
    """Every place a reader has met a dictionary form, oldest finish first.

    `finished` is the reader's finished sections as (document hash, section, at) —
    `Store.finished` — and a meeting is a place the form comes round inside one of them
    (see the module docstring for why "met" is that). `language`, where named, keeps to
    texts in it: Hebrew and Aramaic share spellings, and a word is kept in the language
    of the row it was met in.

    A section whose text is not built here, or not annotated, is left out rather than
    guessed at. One text's places are read at a time.
    """
    out: list[Meeting] = []
    for document, sections, counted in _finished_texts(finished, folder_for, language):
        for place in counted.where(lemma, sections):
            out.append(
                Meeting(
                    document=document,
                    section=place.section,
                    ref=place.ref,
                    count=place.count,
                    at=sections[place.section],
                )
            )
    # Stable, so places inside one section keep their reading order.
    out.sort(key=lambda meeting: (meeting.at, meeting.document, meeting.section))
    return out


def family(
    root: str,
    finished: Iterable[tuple[str, str, int]],
    folder_for: FolderFor,
    language: str = "",
) -> list[str]:
    """Every dictionary form of one root a reader has met, in the order the texts give
    them (targum-internal#96: "6 words from כ־ת־ב met").

    Met the way `met` means it — inside a finished section — and the root is the one the
    annotation gave the form, which is the one the card draws, so the card and this
    count never disagree about which root a word has. A form the annotation gave no root
    is in no family: nothing is guessed.
    """
    if not root:
        return []
    out: dict[str, None] = {}
    for _document, sections, counted in _finished_texts(finished, folder_for, language):
        for lemma, its_root in counted.roots.items():
            if its_root == root and lemma not in out and counted.where(lemma, sections):
                out[lemma] = None
    return list(out)


def _finished_texts(
    finished: Iterable[tuple[str, str, int]],
    folder_for: FolderFor,
    language: str,
) -> Iterator[tuple[str, dict[int, int], Occurrences]]:
    """Each text a reader has finished a section of, with those sections (number -> when)
    and its occurrences; one text's places read at a time.

    `language`, where named, keeps to texts in it: Hebrew and Aramaic share spellings, and
    a word is kept in the language of the row it was met in. A section whose text is not
    built here, or not annotated, is left out rather than guessed at.
    """
    by_document: dict[str, dict[int, int]] = {}
    for document, section, at in finished:
        try:
            number = int(section)
        except (TypeError, ValueError):
            continue
        by_document.setdefault(document, {})[number] = int(at or 0)
    for document, sections in by_document.items():
        found = folder_for(document)
        if found is None:
            continue
        folder, its_language = found
        if language and its_language.split("-")[0].lower() != language:
            continue
        counted = text_occurrences(folder)
        if counted is not None:
            yield document, sections, counted


def finished_chapters(
    finished: Iterable[tuple[str, str, int]],
    folder_for: FolderFor,
    language: str = "he",
    verses: Mapping[str, int] | None = None,
) -> set[str]:
    """The chapters a reader has read every verse of, named as the Tanakh map names
    them, "Genesis 12" (targum-internal#144: "chapters the reader has finished are solid
    leaf").

    `verses`, where given, is how many verses each chapter has — the Tanakh map's own
    count — and then a chapter is read only when that many of its verses have been read,
    whichever texts they were read in: Noach starts at Genesis 6:9, so finishing it reads
    6:9–22 and not 6:1–8, and Bereshit's last section is what completes the chapter
    (review, 2026-10-08). A chapter the count does not know is read when every verse of
    it the text carries sits in a finished section. Texts with no verse references, which
    name no chapter, add nothing.
    """
    out: set[str] = set()
    pooled: dict[str, set[str]] = {}
    for _document, sections, counted in _finished_texts(finished, folder_for, language):
        every: dict[str, set[str]] = {}
        read: dict[str, set[str]] = {}
        for section, ref in counted.places:
            if not _VERSE.fullmatch(ref):
                continue
            chapter = ref.rsplit(":", 1)[0]
            every.setdefault(chapter, set()).add(ref)
            if section in sections:
                read.setdefault(chapter, set()).add(ref)
        for chapter, refs in read.items():
            if verses is not None and chapter in verses:
                pooled.setdefault(chapter, set()).update(refs)
            elif refs == every[chapter]:
                out.add(chapter)
    if verses is not None:
        out.update(chapter for chapter, refs in pooled.items() if len(refs) >= verses[chapter] > 0)
    return out


# -- what the card says ----------------------------------------------------------------

#: How many places the card names before it says how many more (targum-internal#95: "a
#: common word is met hundreds of times").
NAMED = 3

#: A verse's reference as a text carries it — "Jonah 1:4", "Berakhot 2a:3" — and not a
#: recording's "part 1:2" or a page's "p1", which name nothing a reader would recognise.
_VERSE = re.compile(r"(?!part )[^\d\s][^:]*\s\d+[ab]?:\d+")


def places_named(
    meetings: Iterable[Meeting],
    title_of: Callable[[str], str],
    leave_out: tuple[str, int] | None = None,
    most: int = NAMED,
) -> tuple[list[str], int]:
    """The places the card names, latest finish first, and how many more there are.

    A verse is named by its reference; anything else by its text's title, once however
    many sections of it the word came round in. `leave_out` is the (document, section)
    the reader is on: being told you met a word on the page you are reading it on says
    nothing.
    """
    named: dict[str, None] = {}
    for meeting in sorted(meetings, key=lambda m: -m.at):
        if leave_out and (meeting.document, meeting.section) == leave_out:
            continue
        label = meeting.ref if _VERSE.fullmatch(meeting.ref) else title_of(meeting.document)
        if label:
            named.setdefault(label, None)
    labels = list(named)
    return labels[:most], max(0, len(labels) - most)
