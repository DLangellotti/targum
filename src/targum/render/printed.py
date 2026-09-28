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
from collections.abc import Collection, Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from ..annotate.base import NOT_A_WORD, not_vocabulary
from ..errors import TargumError
from ..models import (
    Annotation,
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

if TYPE_CHECKING:
    from ..accounts import Kept
    from ..parasha.cut import Portion as Cut

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
    #: The word's own language where it is not the page's source — an Onkelos word kept
    #: from the Aramaic column, on a list of the week's words.
    language: str = ""

    @property
    def direction(self) -> str:
        return direction_for(self.language) if self.language else ""


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


@dataclass(slots=True)
class Part:
    """One text on the page, under its own title: the whole of an edition, or one of the
    sheet's two readings. Each keeps its own languages, because the portion is set beside
    Onkelos and the haftarah beside the reader's own language."""

    title: str
    english: str
    chapters: list[Chapter]
    source_language: str
    target_language: str

    @property
    def source_direction(self) -> str:
        return direction_for(self.source_language)

    @property
    def target_direction(self) -> str:
        return direction_for(self.target_language)


def _chapters(
    segmented: SegmentedDocument,
    translation: Translation,
    vocalization: Vocalization | None,
    annotation: Annotation | None,
    glossary: Glossary | None,
    *,
    known: Collection[str] | None,
    vowels: bool,
    accents: bool,
) -> list[Chapter]:
    """A text's sections as the page sets them, each with the words worth listing after
    it — none where `annotation` or `glossary` is None."""
    pointed = dict(vocalization.segments) if vocalization is not None else {}

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
    return chapters


def _page(
    parts: list[Part],
    *,
    title: str,
    english: str,
    chrome: str,
    accented: bool,
    under: bool,
    size: str,
    week: list[Word] | None = None,
    looked: bool = True,
) -> str:
    """The parts, and the week's words after them where there are any, as one page."""
    env = _environment()
    template = env.get_template("print.html.j2")
    return template.render(
        t=page_words(chrome),
        page_language=chrome.split("-")[0],
        page_direction=parts[0].source_direction,
        title=title,
        english=english,
        parts=parts,
        week=week or [],
        week_looked=looked,
        chrome=chrome,
        chrome_direction=direction_for(chrome),
        hebrew_face=_hebrew_face(biblical=accented),
        hebrew_family=(BIBLICAL_FACE if accented else MODERN_FACE)[0],
        chrome_face=_chrome_face(),
        size=SIZES.get(size, "A4"),
        under=under,
        # Tanakh is continuous text that happens to be numbered, and the reader sets it
        # close; the page does the same.
        verses=any(
            line.verse for part in parts for chapter in part.chapters for line in chapter.lines
        ),
    )


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
    annotation = read_artifact(Annotation, folder / "annotation.json")
    glossary = _glossary(glossaries_in(folder), translation, translations)
    chapters = _chapters(
        segmented,
        translation,
        vocalization,
        annotation,
        glossary,
        known=known,
        vowels=vowels,
        accents=accents,
    )
    title = document.title or folder.name
    part = Part(
        title=title,
        english=english_title(document),
        chapters=chapters,
        source_language=segmented.language,
        target_language=translation.target_language,
    )
    return _page(
        [part],
        title=title,
        english=part.english,
        chrome=translation.target_language,
        accented=_accented(vocalization),
        under=under,
        size=size,
    )


def _accented(*vocalizations: Vocalization | None) -> bool:
    """The reader's rule, not the shelf's, and not the switches': the face follows what
    the text holds. Scripture printed without its te'amim is still set in the face cut
    for it, as the reader keeps it when its accents are off."""
    return any(
        has_taamim(text)
        for vocalization in vocalizations
        if vocalization is not None
        for text in vocalization.segments.values()
    )


def own_language(translations: list[Translation], reads: Collection[str] = ("en",)) -> str:
    """The reader's own language among a text's renderings: the first of `reads` the text
    is rendered into, else the first rendering into a language rather than beside it —
    decided by what the reader reads, not by which file sorts first — or English."""
    into = [t.target_language for t in translations if t.target_language not in BESIDE]
    return next((code for code in reads if code in into), into[0] if into else "en")


def week_words(kept: Iterable[Kept], texts: Iterable[Cut], target: str = "en") -> list[Word]:
    """The words of a reader's week — looked up, or kept — as the sheet lists them.

    Each with the meaning the reader kept beside it — their own note first, then what the
    page said when they kept it — and failing both, the first sense the week's texts give
    it, where it is in them. In the form the week's texts cite it, pointed, where it is in
    them, and as kept where it is not. A word with no meaning anywhere is left off, as the
    edition leaves one off: paper cannot offer to look one up. `target` is the language
    the meanings are read in.
    """
    cited: dict[str, tuple[str, str]] = {}
    for text in texts:
        if text.annotation is None:
            continue
        glossary = _glossary(
            text.glossaries,
            _translation(text.translations, own_language(text.translations, (target,))),
            text.translations,
        )
        if glossary is None:
            continue
        for tokens in text.annotation.tokens.values():
            for token in tokens:
                bare = strip_nikkud(token.lemma)[0]
                if bare in cited:
                    continue
                key = token.glossed_as
                meaning = first_sense(glossary.entries.get(key, ""))
                form = glossary.citations.get(key) or token.headword or token.lemma
                cited[bare] = (form, meaning)
    out: list[Word] = []
    seen: set[str] = set()
    for one in kept:
        bare = strip_nikkud(one.lemma)[0]
        if bare in seen:
            continue
        form, found = cited.get(bare, (one.lemma, ""))
        meaning = first_sense(one.meaning) or found
        if not meaning:
            continue
        seen.add(bare)
        out.append(Word(form=form, meaning=meaning, language=one.language))
    return out


def mikra_html(
    portion: Cut,
    haftarah: Cut | None,
    *,
    name: str,
    hebrew: str,
    when: str = "",
    haftarah_note: str = "",
    week: list[Word] | None = None,
    looked: bool = True,
    into: str | None = None,
    reads: Collection[str] = ("en",),
    vowels: bool = True,
    accents: bool = True,
    under: bool = False,
    size: str = "a4",
) -> str:
    """The week's shnayim mikra sheet (targum-internal#105): the portion with Onkelos
    beside each verse, the haftarah with the reader's own language beside it, and the
    reader's words of the week — one page, set once, for a Shabbat without a screen.
    `looked` says which words they are: looked up, or where no look-up names its word,
    kept; the list's heading says which.

    Built from the cut rather than from a folder, because the corpus keeps no artifact
    beside its readers (`parasha.build`): the portion is cut again from the books on the
    shelf, which is free, the way `targum parasha leyning` cuts it. The portion carries
    no per-aliyah word lists — a portion's hard words would be pages of them — and the
    haftarah none either; the one list is the reader's own week.
    """
    arc = next(
        (t.target_language for t in portion.translations if t.target_language in BESIDE), None
    )
    chrome = own_language(portion.translations, reads)
    beside = _translation(portion.translations, into or arc or chrome)

    def part(text: Cut, translation: Translation, english: str) -> Part:
        return Part(
            title=text.document.title or "",
            english=english,
            chapters=_chapters(
                text.segmented,
                translation,
                text.vocalization,
                None,
                None,
                known=None,
                vowels=vowels,
                accents=accents,
            ),
            source_language=text.segmented.language,
            target_language=translation.target_language,
        )

    parts = [part(portion, beside, name)]
    if haftarah is not None and haftarah.translations:
        # Read once, and never beside a targum (targum-internal#203): the reader's own
        # language, as the portion page sets it.
        rendering = _translation(haftarah.translations, own_language(haftarah.translations, reads))
        # Its range as a chumash prints it, and why it is this week's where a special
        # Shabbat has displaced the portion's own.
        summary = haftarah.document.source.removeprefix("sefaria:")
        parts.append(
            part(haftarah, rendering, " · ".join(one for one in (summary, haftarah_note) if one))
        )
    return _page(
        parts,
        title=hebrew or name,
        english=" · ".join(one for one in (name, when) if one),
        chrome=chrome,
        accented=_accented(
            portion.vocalization, haftarah.vocalization if haftarah is not None else None
        ),
        under=under,
        size=size,
        week=week,
        looked=looked,
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
