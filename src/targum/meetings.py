"""Where a word on Your Words was met: a line it came round in, and the case it came in.

Your Words (design.md §12, "Your Words is one table and a practice card", 2026-10-09)
asks two things of the texts a reader has finished that `occurrences` does not answer:

- **A line they read it in**, for the practice card ("One word at a time, in a line
  you've read"): the first sentence in a finished section that carries the word, with
  the word's place in it and the line's translation.
- **The case it is mostly met in**, for a Russian row ("Often in the instrumental:
  рукой"), from the case the annotation already gave each running word.

"Met" is `occurrences`' — inside a section the reader finished — so a line here is always
one the reader went past, and the counts on the row and the card agree.

**Nothing here is a source of truth, and nothing here spends.** Both answers are read off
the annotation a build already wrote, cached beside it as `meetings.json` and stamped with
the files it came from, exactly as `occurrences.json` is: written on first ask, thrown
away and rebuilt when the text is. No model is asked, nothing is annotated again, and the
annotator's name and `SCHEMA_VERSION` are untouched.

**Memory.** One text's annotation is parsed at a time, and dropped before the answer is
built, for the reason `occurrences.count_text` gives: the box is 7.7 GB.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from .occurrences import FolderFor, _sections, _stamp
from .paths import write_atomic

#: The cached file's name, beside `annotation.json`.
MEETINGS = "meetings.json"

#: The file's shape. Bumped when the encoding changes; an older file is then rebuilt,
#: which is free — it is read off the annotation, not off a model.
VERSION = 1

#: How many words the practice card holds at once (board WordsDesk: "[2] of [10]").
PRACTISE = 10

#: A case is said on a row only when it is most of the meetings that carry one, and there
#: are enough of them to say "often" about.
CASE_SHARE = 0.5
CASE_FROM = 3


@dataclass(frozen=True)
class TextMeetings:
    """One built text's first line for each word in each section, and the cases its
    running words came in.

    `first` maps a dictionary form to, per section, the segment it first comes round in,
    its offsets there (into the segment's bare text, as the annotation counts them) and
    the case it came in there ("" for none).
    `cases` maps a form to, per section, each case it came in, how often, and the first
    form it took in that case. Only words the annotation gave a case have any.
    """

    first: dict[str, dict[int, tuple[str, int, int, str]]]
    cases: dict[str, dict[int, dict[str, tuple[int, str]]]]


def count_text(folder: Path) -> TextMeetings | None:
    """Read one built text's meetings off its annotation, uncached.

    The same words `occurrences.count_text` counts: names, numbers and a post's
    hashtags left out. None where the text has no annotation or no segments.
    """
    from .annotate.base import NOT_A_WORD, not_vocabulary
    from .coverage import ANNOTATION
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

    first: dict[str, dict[int, tuple[str, int, int, str]]] = {}
    cases: dict[str, dict[int, dict[str, tuple[int, str]]]] = {}
    for segment in segmented.segments:
        found = tokens.get(segment.id)
        if not found:
            continue
        spans = unwordly.get(segment.id)
        section = section_of.get(segment.id, 1)
        for token in found:
            lemma = str(token.get("lemma") or "")
            if lemma in NOT_A_WORD or not_vocabulary(token.get("pos"), token.get("entity")):
                continue
            start, end = int(token.get("start") or 0), int(token.get("end") or 0)
            if spans and post_module.inside(start, end, spans):
                continue
            case = _case(token.get("feats"))
            first.setdefault(lemma, {}).setdefault(section, (segment.id, start, end, case))
            if case:
                said = cases.setdefault(lemma, {}).setdefault(section, {})
                count, form = said.get(case, (0, str(token.get("surface") or "")))
                said[case] = (count + 1, form)
    del tokens
    return TextMeetings(first=first, cases=cases)


def _case(feats: object) -> str:
    """`Ins` from "Case=Ins|Number=Sing", or "" where the word has no case."""
    for part in str(feats or "").split("|"):
        name, _, value = part.partition("=")
        if name == "Case" and value:
            return value
    return ""


def text_meetings(folder: Path) -> TextMeetings | None:
    """One built text's meetings, from the cache beside it or read and cached now."""
    stamp = _stamp(folder)
    if stamp is None:
        return None
    return _cached(folder, tuple(stamp))


def _from(loaded: object) -> TextMeetings | None:
    if not isinstance(loaded, dict) or loaded.get("version") != VERSION:
        return None
    first = {
        str(lemma): {
            int(row[0]): (str(row[1]), int(row[2]), int(row[3]), str(row[4])) for row in rows
        }
        for lemma, rows in (loaded.get("first") or {}).items()
    }
    cases: dict[str, dict[int, dict[str, tuple[int, str]]]] = {}
    for lemma, rows in (loaded.get("cases") or {}).items():
        for section, case, count, form in rows:
            cases.setdefault(str(lemma), {}).setdefault(int(section), {})[str(case)] = (
                int(count),
                str(form),
            )
    return TextMeetings(first=first, cases=cases)


@lru_cache(maxsize=8)
def _cached(folder: Path, stamp: tuple[int, ...]) -> TextMeetings | None:
    """The parse, kept while the files it came from are unchanged; eight texts at most,
    as `occurrences._cached` keeps."""
    cached = folder / MEETINGS
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
                    "first": {
                        lemma: [[section, *place] for section, place in rows.items()]
                        for lemma, rows in counted.first.items()
                    },
                    "cases": {
                        lemma: [
                            [section, case, count, form]
                            for section, said in rows.items()
                            for case, (count, form) in said.items()
                        ]
                        for lemma, rows in counted.cases.items()
                    },
                },
                ensure_ascii=False,
                separators=(",", ":"),
            ),
        )
    except OSError:
        pass
    return counted


def _finished_folders(
    finished: Iterable[tuple[str, str, int]],
    folder_for: FolderFor,
    language: str,
) -> Iterator[tuple[str, dict[int, int], Path]]:
    """Each text a reader has finished a section of, latest finish first, with those
    sections (number -> when) and its folder. `occurrences._finished_texts`' rule: a
    text not built here, or in another language, is left out."""
    by_document: dict[str, dict[int, int]] = {}
    for document, section, at in finished:
        try:
            number = int(section)
        except (TypeError, ValueError):
            continue
        by_document.setdefault(document, {})[number] = int(at or 0)
    for document, sections in sorted(
        by_document.items(), key=lambda pair: -max(pair[1].values(), default=0)
    ):
        found = folder_for(document)
        if found is None:
            continue
        folder, its_language = found
        if language and its_language.split("-")[0].lower() != language:
            continue
        yield document, sections, folder


@dataclass(frozen=True)
class Line:
    """Where a reader met a word, for the practice card: the text (its hash and folder),
    the section, the segment and the word's offsets in its bare text, and the case it
    came in there ("" where it has none)."""

    lemma: str
    document: str
    folder: Path
    section: int
    segment: str
    start: int
    end: int
    case: str = ""


def lines_met(
    lemmas: Sequence[str],
    finished: Iterable[tuple[str, str, int]],
    folder_for: FolderFor,
    language: str = "",
) -> dict[str, Line]:
    """A line each of `lemmas` was met in: in the text finished latest that has one, the
    first place in reading order inside a finished section. A word met nowhere has none.
    Stops reading texts as soon as every word has its line."""
    wanted = list(dict.fromkeys(lemmas))
    out: dict[str, Line] = {}
    if not wanted:
        return out
    for document, sections, folder in _finished_folders(finished, folder_for, language):
        meetings = text_meetings(folder)
        if meetings is None:
            continue
        for lemma in wanted:
            if lemma in out:
                continue
            places = meetings.first.get(lemma) or {}
            here = sorted(section for section in places if section in sections)
            if not here:
                continue
            segment, start, end, case = places[here[0]]
            out[lemma] = Line(lemma, document, folder, here[0], segment, start, end, case)
        if len(out) == len(wanted):
            break
    return out


def cases_met(
    lemmas: Iterable[str],
    finished: Iterable[tuple[str, str, int]],
    folder_for: FolderFor,
    language: str = "",
) -> dict[str, tuple[str, str]]:
    """The case each word is mostly met in, and the form it took: `("Ins", "рукой")`.

    Said only where one case is at least half of the meetings that carry a case, there
    are at least `CASE_FROM` of them, and it is not the nominative, which is the word as
    the list already writes it. Everything else is left out rather than guessed.
    """
    wanted = set(lemmas)
    counts: dict[str, dict[str, int]] = {}
    forms: dict[str, dict[str, str]] = {}
    if not wanted:
        return {}
    for _document, sections, folder in _finished_folders(finished, folder_for, language):
        meetings = text_meetings(folder)
        if meetings is None:
            continue
        for lemma, rows in meetings.cases.items():
            if lemma not in wanted:
                continue
            for section, said in rows.items():
                if section not in sections:
                    continue
                for case, (count, form) in said.items():
                    mine = counts.setdefault(lemma, {})
                    mine[case] = mine.get(case, 0) + count
                    forms.setdefault(lemma, {}).setdefault(case, form)
    out: dict[str, tuple[str, str]] = {}
    for lemma, by_case in counts.items():
        total = sum(by_case.values())
        case = max(by_case, key=lambda one: by_case[one])
        if total < CASE_FROM or by_case[case] / total < CASE_SHARE or case == "Nom":
            continue
        out[lemma] = (case, forms[lemma][case])
    return out


# -- the line, as the card draws it -------------------------------------------------------


def _translation(folder: Path, into: str) -> dict[str, str]:
    """The text's translation into `into`, or into anything it has where it has none in
    that language; `{}` where it has none at all. Onkelos is read beside, never into."""
    from .models import Translation, read_artifact
    from .translate.prompts import BESIDE

    best: dict[str, str] = {}
    for path in sorted((folder / "translations").glob("*.json")):
        translation = read_artifact(Translation, path)
        if translation is None or translation.target_language in BESIDE:
            continue
        if translation.target_language.split("-")[0] == into:
            return dict(translation.segments)
        if not best:
            best = dict(translation.segments)
    return best


def _pointed(folder: Path, segment: str) -> str:
    """The segment as the reader points it, where the build pointed it."""
    try:
        loaded = json.loads((folder / "vocalization.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    said = (loaded.get("segments") or {}) if isinstance(loaded, dict) else {}
    return str(said.get(segment) or "")


def drawn(line: Line, text: str, pointed: str = "") -> tuple[str, int, int]:
    """The line as the card shows it, and the word's place in that.

    The annotation counts a word's offsets in the segment as written where the text is
    scripture (its points and chanting marks included) and in its bare letters where the
    annotator read it bare; `_bare_span` tells the two apart. The card shows the pointed
    text where the build pointed it, with its chanting marks gone, so the span is carried
    across by its letters: the same letters stand in both, the points between them do
    not. Where the pointing is not the same letters, the text as written.
    """
    from .vocalize.base import strip_nikkud, strip_taamim

    letters, start_at, end_at = _bare_span(text, line.start, line.end)
    for shown in (strip_taamim(pointed) if pointed else "", strip_taamim(text)):
        if not shown:
            continue
        bare, index = strip_nikkud(shown)
        if bare != letters or end_at > len(bare):
            continue
        start = next(
            (at for at, char in enumerate(shown) if index[at] == start_at and not _is_point(char)),
            -1,
        )
        if start < 0:
            continue
        end = len(shown)
        for at in range(start + 1, len(shown)):
            if index[at] >= end_at and not _is_point(shown[at]):
                end = at
                break
        return shown, start, end
    return text, line.start, line.end


def _bare_span(text: str, start: int, end: int) -> tuple[str, int, int]:
    """The text's bare letters, and the word's span in them.

    Offsets into the text as written land on a letter at the start and stop before a
    letter, a space or the end, never inside a run of points; offsets counted in the bare
    letters, read against a pointed text, almost never do. Read as written where they
    fit, as bare where they do not; on a text with no points the two are the same.
    """
    from .vocalize.base import strip_nikkud

    bare, index = strip_nikkud(text)
    fits = (
        0 <= start < end <= len(text)
        and not _is_point(text[start])
        and (end == len(text) or not _is_point(text[end]))
    )
    if fits:
        return bare, index[start], index[end]
    return bare, start, end


def _is_point(char: str) -> bool:
    import unicodedata

    return unicodedata.category(char) == "Mn"


def card_line(line: Line, into: str) -> dict[str, object] | None:
    """What the practice card says about one line: the text it is in and where, the line
    with the word's place in it, and the line's translation. None where the segment is
    gone from the text."""
    from .models import SegmentedDocument, read_artifact

    segmented = read_artifact(SegmentedDocument, line.folder / "segments.json")
    if segmented is None:
        return None
    segment = next((s for s in segmented.segments if s.id == line.segment), None)
    if segment is None:
        return None
    shown, start, end = drawn(line, segment.text, _pointed(line.folder, line.segment))
    sections = len(list((line.folder / "reader").glob("sec-*.html")))
    try:
        facts = json.loads((line.folder / "document.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        facts = {}
    return {
        "lemma": line.lemma,
        "line": shown,
        "start": start,
        "end": end,
        "word": shown[start:end],
        "translation": _translation(line.folder, into).get(line.segment, ""),
        "title": str(facts.get("title") or ""),
        # A text of more than one part names the one the line is in, as Continue does.
        "chapter": line.section if sections > 1 else 0,
        "name": line.folder.name,
        "language": str(facts.get("language") or segmented.language),
        "case": line.case,
    }
