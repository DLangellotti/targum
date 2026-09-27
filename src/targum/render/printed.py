"""A reader's edition on paper (targum-internal#105).

One PDF from one reader folder: the source with its vowels — and its te'amim, where the
text carries them and the reader would show them — the translation beside each line the
way the reader's parallel mode sets it (or under it, the way its interlinear mode does),
and after each chapter the words from it worth having on the page, with their meanings.

**Drawn from the artifacts, not from the reader's HTML.** The built page is a working
reader — a bar, a player, a card, a pager and a script that fills half of it — and a
printout of it would be a printout of a screen. So this builds its own small page from
the same folder a rebuild reads, with the reader's own values (§5's faces, sizes and
leading, §4's paper and ink) in `print.css`, and hands it to WeasyPrint.

**Why WeasyPrint** (BSD-3). It sets text through Pango and HarfBuzz, which is the shaping
a browser does: the marks of a pointed and accented word are placed by the font's own
positioning rules, and bidi runs are resolved by the Unicode algorithm. ReportLab (BSD
too) has neither — its Hebrew is reversed strings with the nikkud laid beside the letter
rather than on it — and a reader's edition whose vowels sit in the wrong place is not one.
The cost is Pango on the machine, which is why it is an extra (`print`) and not a
dependency: the box and CI never draw a page.

**Nothing is fetched.** The Hebrew face is the reader's own, carried as the reader
carries it (design.md §12, "The Hebrew reading face is carried"); every font the page
uses is embedded in the PDF.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Collection, Mapping
from dataclasses import dataclass, field
from pathlib import Path

from ..annotate.base import NOT_A_WORD, not_vocabulary
from ..errors import TargumError
from ..models import (
    BlockKind,
    Document,
    Glossary,
    SegmentedDocument,
    Translation,
    Vocalization,
    direction_for,
    glossaries_in,
    read_artifact,
)
from ..translate.prompts import BESIDE
from ..vocalize import has_taamim, strip_nikkud, strip_taamim
from .builder import (
    BIBLICAL_FACE,
    MODERN_FACE,
    _chrome_face,
    _environment,
    _hebrew_face,
    english_title,
    page_words,
    split_sections,
    verse_address,
)

#: Where a word stops being one a reader knows and starts being one they look up: bands 4
#: to 6 of six. `annotate.difficulty.LOOKED_UP`, said again rather than imported because
#: that module builds its frequency tables on import and this one needs none of them.
LOOKED_UP = 4

#: Paper the page can be set on. A4 first because it is what a reader in Israel prints on.
SIZES = {"a4": "A4", "letter": "letter"}


@dataclass(slots=True)
class Word:
    """One line of a chapter's word list."""

    form: str
    meaning: str


@dataclass(slots=True)
class Line:
    """One pair as the page draws it."""

    kind: str
    level: int
    source: str
    translation: str
    verse: str = ""


@dataclass(slots=True)
class Chapter:
    title: str
    lines: list[Line] = field(default_factory=list)
    words: list[Word] = field(default_factory=list)


def first_sense(meaning: str) -> str:
    """The meaning up to its first semicolon.

    A scripture meaning is Strong's whole entry — "wind; by resemblance breath, i.e. a
    sensible (or even violent) exhalation; figuratively, life, anger…" — which the card
    has room for and a word list does not. The first sense is the one a reader keeps.
    """
    return meaning.split(";", 1)[0].strip()


def _translation(translations: list[Translation], into: str | None) -> Translation:
    """The rendering the page sets beside the text: the one asked for by language, or the
    reader's own first choice — the first that is into a language rather than beside it."""
    if into:
        for translation in translations:
            if translation.target_language == into:
                return translation
        have = ", ".join(sorted({t.target_language for t in translations}))
        raise TargumError(f"This text has no translation into {into}.", f"It has: {have}.")
    ordered = sorted(translations, key=lambda t: t.target_language in BESIDE)
    return ordered[0]


def _glossary(
    glossaries: Mapping[str, Glossary], translation: Translation, translations: list[Translation]
) -> Glossary | None:
    """The meanings in the language the page is read in. Onkelos is not a language a
    meaning is written in, so a page set beside it takes the reader's own language."""
    wanted = [translation.target_language] + [
        t.target_language for t in translations if t.target_language not in BESIDE
    ]
    for code in [*wanted, "en"]:
        if code in glossaries:
            return glossaries[code]
    return None


def print_html(
    folder: Path,
    *,
    into: str | None = None,
    known: Collection[str] | None = None,
    vowels: bool = True,
    accents: bool = True,
    under: bool = False,
    size: str = "a4",
) -> str:
    """The page WeasyPrint sets, as HTML. Separate from `write_pdf` so everything that
    decides what is on the page is testable on a machine without Pango.

    `known` is the forms the reader has marked known, bare of points — the dictionary
    form and the surface, as `Store.known_forms` gives them. Given, a chapter lists every
    word in it that is not among them; not given — a static export, nobody signed in — it
    lists the words in the looked-up bands. Either way a word is listed once, where it
    first appears, and only where there is a meaning to print beside it: a word with no
    meaning is one the reader's card would offer to look up, and paper has no button.
    """
    document = read_artifact(Document, folder / "document.json")
    segmented = read_artifact(SegmentedDocument, folder / "segments.json")
    if document is None or segmented is None:
        raise TargumError(f"{folder} holds no text.", "Point this at a built targum's folder.")
    translations = [
        translation
        for path in sorted((folder / "translations").glob("*.json"))
        if (translation := read_artifact(Translation, path)) is not None
    ]
    if not translations:
        raise TargumError(f"{folder} has no translation yet.", "Build it first.")
    translation = _translation(translations, into)
    vocalization = read_artifact(Vocalization, folder / "vocalization.json")
    from ..models import Annotation

    annotation = read_artifact(Annotation, folder / "annotation.json")
    glossary = _glossary(glossaries_in(folder), translation, translations)

    pointed = dict(vocalization.segments) if vocalization is not None else {}
    source_direction = direction_for(segmented.language)
    target_direction = direction_for(translation.target_language)

    def form_of(segment_id: str, text: str) -> str:
        # The reader's cells, chosen once: the bare text, or the pointed one, or the
        # pointed one with its chanting marks taken off.
        if not vowels or segment_id not in pointed:
            return strip_nikkud(text)[0]
        shown = pointed[segment_id]
        return shown if accents else strip_taamim(shown)

    by_id = {segment.id: segment for segment in segmented.segments}
    listed: set[str] = set()
    chapters: list[Chapter] = []
    for section in split_sections(segmented):
        chapter = Chapter(title=section.title)
        for sid in section.segment_ids:
            segment = by_id[sid]
            kind = segment.kind.value
            chapter.lines.append(
                Line(
                    kind=kind,
                    level=segment.level or 2,
                    source=form_of(sid, segment.text),
                    translation=translation.segments.get(sid, ""),
                    verse=verse_address(segment.ref) if segment.kind is BlockKind.verse else "",
                )
            )
            if annotation is None or glossary is None:
                continue
            for token in annotation.tokens.get(sid, []):
                if token.lemma in NOT_A_WORD or not_vocabulary(token.pos, token.entity):
                    continue
                key = token.glossed_as
                if key in listed:
                    continue
                if known is None:
                    if token.band < LOOKED_UP:
                        continue
                elif (
                    strip_nikkud(token.lemma)[0] in known or strip_nikkud(token.surface)[0] in known
                ):
                    continue
                meaning = first_sense(glossary.entries.get(key, ""))
                if not meaning:
                    continue
                listed.add(key)
                form = glossary.citations.get(key) or token.headword or token.lemma
                chapter.words.append(Word(form=form, meaning=meaning))
        chapters.append(chapter)

    # The reader's rule, not the shelf's, and not the switches': the face follows what the
    # text holds. Scripture printed without its te'amim is still set in the face cut for
    # it, as the reader keeps it when its accents are off.
    accented = any(has_taamim(text) for text in pointed.values())
    chrome = translation.target_language
    env = _environment()
    template = env.get_template("print.html.j2")
    return template.render(
        t=page_words(chrome),
        page_language=chrome.split("-")[0],
        title=document.title or folder.name,
        english=english_title(document),
        chapters=chapters,
        source_language=segmented.language,
        source_direction=source_direction,
        target_language=translation.target_language,
        target_direction=target_direction,
        hebrew_face=_hebrew_face(biblical=accented),
        hebrew_family=(BIBLICAL_FACE if accented else MODERN_FACE)[0],
        chrome_face=_chrome_face(),
        size=SIZES.get(size, "A4"),
        under=under,
        # Tanakh is continuous text that happens to be numbered, and the reader sets it
        # close; the page does the same.
        verses=any(line.verse for chapter in chapters for line in chapter.lines),
    )


def _find_pango() -> None:
    """Let WeasyPrint find Homebrew's Pango on a Mac.

    WeasyPrint opens Pango by name, and a Python that did not come from Homebrew does not
    look in Homebrew's library folder. `ctypes` reads this variable when it searches, so
    setting it before the import is enough; a variable somebody set themselves is kept.
    """
    if sys.platform != "darwin" or os.environ.get("DYLD_FALLBACK_LIBRARY_PATH"):
        return
    found = [where for where in ("/opt/homebrew/lib", "/usr/local/lib") if Path(where).is_dir()]
    if found:
        os.environ["DYLD_FALLBACK_LIBRARY_PATH"] = ":".join([*found, "/usr/lib"])


def write_pdf(html: str, out: Path) -> Path:
    """Set the page and write it. Refuses in one sentence where the extra is missing."""
    _find_pango()
    try:
        from weasyprint import HTML
    except (ImportError, OSError) as error:
        raise TargumError(
            "Printing needs WeasyPrint and Pango, and this machine has not got them.",
            "Install the extra with `uv sync --extra print`, and Pango with "
            "`brew install pango` or your system's package.",
        ) from error
    out.parent.mkdir(parents=True, exist_ok=True)
    # No base URL: the page names nothing outside itself, and without one a stray
    # relative address resolves to nothing rather than to the working directory.
    HTML(string=html).write_pdf(out)
    return out
