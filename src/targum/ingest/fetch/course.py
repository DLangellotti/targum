"""One lesson of a course book, paired with the book's own translation by line.

    course:it:assimil-italian:3       the lesson's Italian
    course:en:assimil-italian:3       the same lesson's English, as the book prints it

A bilingual course (Assimil, Colloquial, Teach Yourself) prints each lesson as numbered
lines with the translation numbered the same way on the facing page, and notes keyed to
the lines by a marker in the text: `(1)`, `(2)`. Reading the scan is a separate step,
which leaves a *course extract* (targum-internal#652): the book's lessons as numbered
lines in both languages, the notes, and what the reader leaves out (the pronunciation,
the exercises and their key, kept for practice cards later).

This turns one lesson of that extract into the two documents `align/parallel.py` pairs by
construction: a heading, then one verse block per numbered line, each with its ref,
`L3:1`, `L3:2`. The book numbered both sides, so the pairing is stated rather than
inferred, and nothing is bought. The markers come out of the text, so they are never
glossed or read aloud, and each note goes onto the translation's line it is keyed to, as
a translator's footnote does (`Block.notes`). A note the book points at from another
lesson, `(N.2)` in Assimil, is the revision lesson's numbered section, carried to the line
that points at it when the extract holds that lesson.

**A course is always somebody's own import.** A course book is in copyright, so its
extract is a reader's file and never the library's: `course:` is not addressable from a
link, a chat or a request (`fetch.PRIVATE`), only from a build that names a file the
reader brought. The extracts live in the first of `TARGUM_COURSES` and
`~/.targum/courses`, as `<book>.json`; never in `/etc`, where every reader's build could
reach them.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from ...errors import TargumError
from ...ids import block_id
from ...models import BlockKind, Document, Note
from ..base import Paragraph, blocks_from_paragraphs, build_document, normalize

NAME = "course/1"

_BOOK = re.compile(r"^[a-z0-9][a-z0-9-]{0,79}$")
#: A note marker as the book prints it: `(1)`, or `(N.2)` for a revision lesson's section.
_MARKER = re.compile(r"\s*\((?P<mark>\d{1,2}|N\.\s?\d{1,2})\)")
_RESPELT = re.compile(r"\s*\([^()]*\)")


def home() -> Path | None:
    """Where the course extracts are, or None on a machine that has none."""
    named = os.environ.get("TARGUM_COURSES")
    places = [Path(named)] if named else []
    places.append(Path.home() / ".targum" / "courses")
    return next((place for place in places if place.is_dir()), None)


def split(identifier: str) -> tuple[str, str, int]:
    """`course:it:assimil-italian:3` -> ("it", "assimil-italian", 3)."""
    rest = identifier.split(":", 1)[1] if identifier.lower().startswith("course:") else identifier
    language, _, tail = rest.partition(":")
    book, _, lesson = tail.partition(":")
    if not (language.isalpha() and 2 <= len(language) <= 3 and _BOOK.match(book)):
        raise TargumError(
            "A course lesson names its language, its book and its lesson.",
            "Try: course:it:assimil-italian:1",
        )
    if not lesson.isdigit() or int(lesson) < 1:
        raise TargumError("A course lesson is numbered from 1.", "Try: course:it:assimil-italian:1")
    return language.lower(), book, int(lesson)


def extract(book: str) -> dict[str, Any]:
    """One book's extract, as read. Read every time rather than cached: it is a reader's
    file, and an edit to it should reach the next build."""
    where = home()
    path = where / f"{book}.json" if where else None
    if path is None or not path.is_file():
        raise TargumError(
            f"We have no course called {book} on this machine.",
            "Put its extract at ~/.targum/courses/<book>.json or name the folder in "
            "TARGUM_COURSES.",
        )
    loaded = json.loads(path.read_text(encoding="utf-8"))
    return loaded if isinstance(loaded, dict) else {}


def _unmarked(text: str) -> tuple[str, list[str]]:
    """The line without its note markers, and the markers in the order printed."""
    marks = [
        " ".join(found.group("mark").split()).replace(". ", ".") for found in _MARKER.finditer(text)
    ]
    return " ".join(_MARKER.sub("", text).split()), marks


def _title_part(text: str) -> str:
    """One line of a lesson's heading as a reader sees it: a part wholly in brackets
    unwrapped, a respelling in brackets dropped, and capitals set in sentence case."""
    text = " ".join(text.split())
    if text.startswith("(") and text.endswith(")"):
        text = text[1:-1].strip()
    text = " ".join(_RESPELT.sub("", text).split())
    if text.isupper():
        text = text[:1] + text[1:].lower()
    return text


def heading(lesson: dict[str, Any], language: str) -> str:
    parts = [_title_part(str(one)) for one in dict(lesson.get("title") or {}).get(language) or []]
    return " — ".join(part for part in parts if part)


def _numbered(held: dict[str, Any]) -> list[tuple[int, Any]]:
    return sorted((int(key), value) for key, value in held.items() if str(key).isdigit())


def _revision_after(lessons: dict[str, Any], number: int) -> dict[str, Any] | None:
    """The revision lesson a `(N.k)` marker in this lesson points at: the next lesson,
    from this one on, that has notes and no lines."""
    for later, held in _numbered(lessons):
        if (
            later >= number
            and isinstance(held, dict)
            and held.get("notes")
            and not held.get("lines")
        ):
            return held
    return None


def documents(
    book: dict[str, Any], number: int, language: str, translation: str, *, name: str = ""
) -> tuple[Document, Document]:
    """One lesson as its two sides: the course's language and the book's translation.

    Built together, because the two must agree in count and in kind or `pair` refuses
    them, and because what goes on a translation's line is read off the other side's
    markers. A line the translation lacks keeps its place as a dash, as a published
    translation's missing verse does; a line with no text in the course's language is a
    misread page and is refused.
    """
    lessons = dict(book.get("lessons") or {})
    lesson = lessons.get(str(number))
    if not isinstance(lesson, dict):
        raise TargumError(f"The course has no lesson {number}.")
    lines = _numbered(dict(lesson.get("lines") or {}))
    notes = {str(k): " ".join(str(v).split()) for k, v in dict(lesson.get("notes") or {}).items()}
    revision = _revision_after(lessons, number)
    sections = {str(k): str(v) for k, v in dict((revision or {}).get("notes") or {}).items()}

    mine: list[Paragraph] = [(BlockKind.heading, 2, heading(lesson, language) or str(number))]
    theirs: list[Paragraph] = [(BlockKind.heading, 2, heading(lesson, translation) or str(number))]
    refs: dict[int, str] = {}
    keyed: dict[int, list[tuple[str, str]]] = {}
    placed: set[str] = set()
    for line, pair in lines:
        pair = dict(pair or {})
        said, marks = _unmarked(normalize(str(pair.get(language) or "")))
        if not said:
            raise TargumError(
                f"Lesson {number}, line {line} has no {language} text.",
                "Read that page again before building it. Nothing has been written.",
            )
        rendered, _ = _unmarked(normalize(str(pair.get(translation) or "")))
        refs[len(mine)] = f"L{number}:{line}"
        here: list[tuple[str, str]] = []
        for mark in marks:
            if mark.startswith("N."):
                section = sections.get(mark[2:])
                if section:
                    here.append((mark, " ".join(section.split())))
            elif mark in notes:
                here.append((mark, notes[mark]))
                placed.add(mark)
        if here:
            keyed[len(mine)] = here
        mine.append((BlockKind.verse, None, said))
        theirs.append((BlockKind.verse, None, rendered or "—"))
    # A note no line points at — the whole of a revision lesson, whose numbered sections
    # are its notes — goes on the heading, so it is read rather than lost.
    left = [
        (mark, text) for mark, text in sorted(notes.items(), key=_by_number) if mark not in placed
    ]
    if left:
        keyed[0] = left

    title = str(book.get("title") or "")
    made = []
    for side, paragraphs in ((language, mine), (translation, theirs)):
        blocks = blocks_from_paragraphs(paragraphs)
        by_id = {block_id(index): ref for index, ref in refs.items()}
        for block in blocks:
            block.ref = by_id.get(block.id, "")
        document = build_document(
            f"course:{side}:{name}:{number}",
            blocks,
            ingester=NAME,
            language=side,
            title=paragraphs[0][2] or (f"{title} {number}" if title else str(number)),
            author=str(book.get("author") or "") or None,
        )
        made.append(document)
    # On the translation's line, after the text is final: a note stands at the end of the
    # line it is keyed to, since the translation carries no marker to stand beside.
    by_index = {block_id(index): held for index, held in keyed.items()}
    for block in made[1].blocks:
        held = by_index.get(block.id)
        if held:
            block.notes = [Note(at=len(block.text), mark=mark, text=text) for mark, text in held]
    return made[0], made[1]


def _by_number(item: tuple[str, str]) -> tuple[int, str]:
    mark = item[0]
    return (int(mark), mark) if mark.isdigit() else (10_000, mark)


class CourseFetcher:
    name = NAME

    def load(self, identifier: str) -> Document:
        language, book, number = split(identifier)
        held = extract(book)
        own = str(held.get("language") or "")
        other = str(held.get("translation") or "")
        if language not in (own, other):
            raise TargumError(f"The course {book} is in {own} with {other} beside it.")
        source, translation = documents(held, number, own, other, name=book)
        return source if language == own else translation
