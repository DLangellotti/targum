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
import re
import sys
from collections.abc import Callable, Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from markupsafe import Markup, escape

from ..annotate.base import NOT_A_WORD, not_vocabulary
from ..errors import TargumError
from ..models import (
    Annotation,
    BlockKind,
    Document,
    Glossary,
    SegmentedDocument,
    Token,
    Translation,
    Vocalization,
    direction_for,
    glossaries_in,
    read_artifact,
)
from ..translate.prompts import BESIDE, language_name
from ..vocalize import has_taamim, pointed_positions, strip_nikkud, strip_taamim
from .builder import (
    BIBLICAL_FACE,
    MODERN_FACE,
    _chrome_face,
    _environment,
    _hebrew_face,
    english_title,
    isolate,
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
class Cell:
    """One companion's line beside (or under) the source: a translation, Onkelos, Rashi."""

    text: str
    language: str
    #: The work's name over its line where it is a commentary — "Rashi", "Rashi ·
    #: English" — and whether its comments keep their line breaks (targum-internal#414).
    label: str = ""
    commented: bool = False

    @property
    def direction(self) -> str:
        return direction_for(self.language)


@dataclass(slots=True)
class Line:
    """One pair as the page draws it."""

    kind: str
    level: int
    source: str
    cells: list[Cell] = field(default_factory=list)
    verse: str = ""
    #: The source with its marked words drawn in — the reader's learning words lit, and a
    #: meaning set above a word — where any are (targum-internal#415). None where the
    #: line has none, and the template sets `source` as it always has.
    source_html: Markup | None = None

    @property
    def translation(self) -> str:
        """The first companion's line: what a page with one companion sets."""
        return self.cells[0].text if self.cells else ""


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


#: What a companion is called in a view: a translation by its language, Onkelos as
#: `targum`, Rashi as `rashi` and Rashi in English as `rashi-en` — the reader's own
#: companion keys (`renderings.companion_key`, targum-internal#414) — with `arc` taken
#: for Onkelos as well. A key the text has no rendering for is passed over rather than
#: refused, so a link made by a newer reader still prints.
TARGUM_KEYS = frozenset({"targum", "arc"})


@dataclass(frozen=True, slots=True)
class View:
    """What a sheet shows: the reader's view when Download was pressed (targum-internal#415).

    Each default is the reader's own. `companions` is None for "the page's choice" — the
    reader's language on the box, Onkelos on the command line, as each always was — and
    empty for the text alone, the reader's source-only mode.
    """

    companions: tuple[str, ...] | None = None
    vowels: bool = True
    taamim: bool = True
    under: bool = False
    #: The reader's learning words lit, with their meaning above them — or for nobody
    #: signed in, the rarer words' meanings. Off is the reader's quiet page.
    gloss: bool = True
    #: One aliyah, counted from 1, or None for the whole portion.
    aliyah: int | None = None
    haftarah: bool = True
    size: str = "a4"


def companion(translations: Sequence[Translation], key: str) -> Translation | None:
    """The rendering a view's companion key names in this text, or None."""
    from ..renderings import companion_key, is_commentary

    for translation in translations:
        code = translation.target_language
        if key in TARGUM_KEYS and code in BESIDE:
            return translation
        if is_commentary(translation.name):
            if companion_key(translation, translation.source_language, BESIDE) == key:
                return translation
            continue
        if code == key and code not in BESIDE:
            return translation
    return None


def _translations_into(translations: Sequence[Translation]) -> list[Translation]:
    """The renderings into a language a reader reads: not Onkelos, which is beside the
    text, and not a commentary, which is about it (targum-internal#414)."""
    from ..renderings import is_commentary

    return [
        t for t in translations if t.target_language not in BESIDE and not is_commentary(t.name)
    ]


def _cell(translation: Translation, segment_id: str) -> Cell:
    """One companion's line for one verse; a commentary's named, its comments kept apart,
    and an unremarked verse left blank rather than drawn as a dash."""
    from ..renderings import EMPTY, commentator, is_commentary

    text = translation.segments.get(segment_id, "")
    if not is_commentary(translation.name):
        return Cell(text=text, language=translation.target_language)
    who = commentator(translation.name)
    own = translation.target_language.split("-")[0] == translation.source_language.split("-")[0]
    return Cell(
        text="" if text.strip() == EMPTY else text,
        language=translation.target_language,
        label=who if own else f"{who} · {language_name(translation.target_language)}",
        commented=True,
    )


@dataclass(frozen=True, slots=True)
class Mark:
    """A word the page marks: the reader's step on it, 1 to 3, or 0 for a word marked
    only for being rare; and the meaning set above it, where there is one."""

    status: int
    meaning: str


#: Which words a page marks, and how: handed a token and the text's glossary.
Marker = Callable[[Token, "Glossary | None"], "Mark | None"]


def gloss_of(meaning: str, most: int = 16) -> str:
    """A meaning as it fits above a word: its first sense, without what a dictionary
    puts in brackets, up to its first comma, and no longer than `most` characters. ""
    where nothing is left — `[marks the direct object]` is a grammar note, not a word."""
    sense = re.sub(r"\([^)]*\)|\[[^\]]*\]", "", first_sense(meaning))
    sense = re.sub(r"\s+", " ", sense.split(",", 1)[0]).strip(" .;:")
    if len(sense) <= most:
        return sense
    cut = sense[:most].rsplit(" ", 1)[0].rstrip(" .;:")
    return (cut or sense[:most]) + "…"


def _vocabulary(token: Token) -> bool:
    return token.lemma not in NOT_A_WORD and not not_vocabulary(token.pos, token.entity)


def _glossary_meaning(token: Token, glossary: Glossary | None) -> str:
    return glossary.entries.get(token.glossed_as, "") if glossary is not None else ""


def learning_marker(learning: Mapping[str, tuple[int, str]]) -> Marker:
    """The reader's own marks: a word they are learning, steps 1 to 3, by its dictionary
    form or the form they met it in, bare of points (`Store.learning_words`). Its meaning
    is theirs where they kept one, else the text's own glossary; with neither it is lit
    and has nothing above it — nothing is looked up for paper."""

    def mark(token: Token, glossary: Glossary | None) -> Mark | None:
        if not _vocabulary(token):
            return None
        for form in (strip_nikkud(token.lemma)[0], strip_nikkud(token.surface)[0]):
            if form in learning:
                status, own = learning[form]
                meaning = gloss_of(own) or gloss_of(_glossary_meaning(token, glossary))
                return Mark(status=status, meaning=meaning)
        return None

    return mark


def rare_marker(token: Token, glossary: Glossary | None) -> Mark | None:
    """For nobody in particular: a word in the looked-up bands gets its meaning above it,
    the same measure the edition's word lists use (`LOOKED_UP`). Nothing is lit."""
    if token.band < LOOKED_UP or not _vocabulary(token):
        return None
    meaning = gloss_of(_glossary_meaning(token, glossary))
    return Mark(status=0, meaning=meaning) if meaning else None


#: What ends a word on the page: a space, the maqaf, the paseq and the sof pasuq. A mark
#: is drawn on the whole word it stands in, prefixes and all, so the word is never cut
#: where the typesetter could break the line.
_WORD_EDGE = frozenset(" \t\n\u05be\u05c0\u05c3:;,.()")


def _marked(
    text: str,
    shown: str,
    tokens: Sequence[Token],
    marker: Marker,
    glossary: Glossary | None,
    seen: set[str],
    *,
    direction: str,
    chrome: str,
) -> Markup | None:
    """`shown` — the form of `text` the page sets — with its marked words drawn in, or
    None where none is. A token's offsets are into `text`, as the reader's are, and are
    carried through its bare letters onto `shown`. A meaning is set above a word the
    first time it comes in the chapter (`seen`): the second time, the reader has it."""
    bare, to_bare = strip_nikkud(text)
    if strip_nikkud(shown)[0] != bare:
        return None
    onto = pointed_positions(shown)
    spans: list[tuple[int, int, int, str]] = []
    for token in sorted(tokens, key=lambda one: one.start):
        if token.end > len(text):
            continue
        mark = marker(token, glossary)
        if mark is None:
            continue
        start, end = onto[to_bare[token.start]], onto[to_bare[token.end]]
        while start > 0 and shown[start - 1] not in _WORD_EDGE:
            start -= 1
        while end < len(shown) and shown[end] not in _WORD_EDGE:
            end += 1
        if spans and start < spans[-1][1]:
            continue
        gloss = mark.meaning if mark.meaning and token.glossed_as not in seen else ""
        if not gloss and not mark.status:
            continue
        if gloss:
            seen.add(token.glossed_as)
        spans.append((start, end, mark.status, gloss))
    if not spans:
        return None
    out: list[str] = []
    position = 0
    for start, end, status, gloss in spans:
        out.append(isolate(shown[position:start], direction))
        word = isolate(shown[start:end], direction)
        # The light is on the word's own line, never on the box that holds its meaning.
        lit = f'<span class="lit s{status}">{word}</span>' if status else str(word)
        if gloss:
            out.append(
                f'<span class="g"><span class="gl" lang="{chrome}" '
                f'dir="{direction_for(chrome)}">{escape(gloss)}</span>'
                f'<span class="gw">{lit}</span></span>'
            )
        else:
            out.append(lit)
        position = end
    out.append(isolate(shown[position:], direction))
    return Markup("".join(out))


def listed_word(token: Token, glossary: Glossary, known: Collection[str] | None) -> Word | None:
    """One word of the text as a line of a word list, or None where it is not one.

    The rule the page's list keeps, said once so the reader's list before a chapter
    (`render.preread`, targum-internal#97) keeps the same one: never a name or a number;
    a word the reader has not marked known, where `known` says what they have, and a
    word in the looked-up bands where it does not; and only with a meaning to set beside
    it. Which words are listed once, and in what order, is the caller's.
    """
    if token.lemma in NOT_A_WORD or not_vocabulary(token.pos, token.entity):
        return None
    if known is None:
        if token.band < LOOKED_UP:
            return None
    elif strip_nikkud(token.lemma)[0] in known or strip_nikkud(token.surface)[0] in known:
        return None
    key = token.glossed_as
    meaning = first_sense(glossary.entries.get(key, ""))
    if not meaning:
        return None
    return Word(form=glossary.citations.get(key) or token.headword or token.lemma, meaning=meaning)


def _translation(translations: list[Translation], into: str | None) -> Translation:
    """The rendering the page sets beside the text: the one asked for by language, or the
    reader's own first choice — the first that is into a language rather than beside it."""
    from ..renderings import is_commentary

    plain = [t for t in translations if not is_commentary(t.name)] or translations
    if into:
        for translation in plain:
            if translation.target_language == into:
                return translation
        have = ", ".join(sorted({t.target_language for t in plain}))
        raise TargumError(f"This text has no translation into {into}.", f"It has: {have}.")
    ordered = sorted(plain, key=lambda t: t.target_language in BESIDE)
    return ordered[0]


def _glossary(
    glossaries: Mapping[str, Glossary], translation: Translation, translations: list[Translation]
) -> Glossary | None:
    """The meanings in the language the page is read in. Onkelos is not a language a
    meaning is written in, so a page set beside it takes the reader's own language."""
    wanted = [translation.target_language] + [
        t.target_language for t in _translations_into(translations)
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
    #: The first companion's language, or the page's where the text stands alone: what
    #: a heading's translation and a word list's meanings are set in.
    target_language: str

    @property
    def source_direction(self) -> str:
        return direction_for(self.source_language)

    @property
    def target_direction(self) -> str:
        return direction_for(self.target_language)


def _chapters(
    segmented: SegmentedDocument,
    translations: Sequence[Translation],
    vocalization: Vocalization | None,
    annotation: Annotation | None,
    glossary: Glossary | None,
    *,
    known: Collection[str] | None,
    vowels: bool,
    accents: bool,
    lists: bool = True,
    marker: Marker | None = None,
    chrome: str = "en",
) -> list[Chapter]:
    """A text's sections as the page sets them, each with the words worth listing after
    it — none where `annotation` or `glossary` is None, or `lists` is off — and each
    companion's line beside its source. With a `marker` and an annotation, the words it
    marks are drawn into the source, their meanings in `chrome`."""
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
    direction = direction_for(segmented.language)
    for section in split_sections(segmented):
        chapter = Chapter(title=section.title)
        glossed: set[str] = set()
        for sid in section.segment_ids:
            segment = by_id[sid]
            kind = segment.kind.value
            shown = form_of(sid, segment.text)
            marked = None
            if marker is not None and annotation is not None and kind != "heading":
                marked = _marked(
                    segment.text,
                    shown,
                    annotation.tokens.get(sid, []),
                    marker,
                    glossary,
                    glossed,
                    direction=direction,
                    chrome=chrome,
                )
            chapter.lines.append(
                Line(
                    kind=kind,
                    level=segment.level or 2,
                    source=shown,
                    cells=[_cell(one, sid) for one in translations],
                    verse=verse_address(segment.ref) if segment.kind is BlockKind.verse else "",
                    source_html=marked,
                )
            )
            if annotation is None or glossary is None or not lists:
                continue
            for token in annotation.tokens.get(sid, []):
                if token.glossed_as in listed:
                    continue
                word = listed_word(token, glossary, known)
                if word is None:
                    continue
                listed.add(token.glossed_as)
                chapter.words.append(word)
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
    address: str = "targum.page",
) -> str:
    """The parts, and the week's words after them where there are any, as one page.
    `address` is where the text lives online, printed at the foot of every page beside
    the mark."""
    env = _environment()
    template = env.get_template("print.html.j2")
    return template.render(
        address=address,
        mark=_mark_uri(),
        glossed=any(
            line.source_html is not None
            for part in parts
            for chapter in part.chapters
            for line in chapter.lines
        ),
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


def _mark_uri() -> str:
    """The mark as the foot of a page draws it: two-colour, at 4 mm — §2's print
    minimum — as a `data:` URI, because a margin box takes an image and not an element."""
    from urllib.parse import quote

    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="12 4 72 88" width="11.4pt" '
        'height="14pt"><rect x="20" y="12" width="22" height="62" rx="5" fill="#201e1b"/>'
        '<rect x="54" y="22" width="22" height="62" rx="5" fill="#a5824f"/></svg>'
    )
    return "data:image/svg+xml," + quote(svg)


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
        [translation],
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
    into = [t.target_language for t in _translations_into(translations)]
    return next((code for code in reads if code in into), into[0] if into else "en")


def week_words(
    kept: Iterable[Kept],
    texts: Iterable[Cut] = (),
    target: str = "en",
    *,
    cited: Mapping[str, tuple[str, str]] | None = None,
) -> list[Word]:
    """The words of a reader's week — looked up, or kept — as the sheet lists them.

    Each with the meaning the reader kept beside it — their own note first, then what the
    page said when they kept it — and failing both, the first sense the week's texts give
    it, where it is in them. In the form the week's texts cite it, pointed, where it is in
    them, and as kept where it is not. A word with no meaning anywhere is left off, as the
    edition leaves one off: paper cannot offer to look one up. `target` is the language
    the meanings are read in.

    `cited` is `cited_forms` of the week's texts, given where it was worked out earlier —
    the box keeps it beside each portion rather than the annotation it comes from
    (`parasha.sheet`) — and then `texts` is not read.
    """
    if cited is None:
        cited = cited_forms(texts, target)
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


def cited_forms(texts: Iterable[Cut], target: str = "en") -> dict[str, tuple[str, str]]:
    """Every word the texts carry, bare of points, with the form they cite it in and its
    first sense in `target` — what `week_words` sets a reader's word beside. The first
    text to carry a word decides it."""
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
    return cited


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
    view: View | None = None,
    marker: Marker | None = None,
    address: str = "targum.page/parasha",
) -> str:
    """The week's shnayim mikra sheet (targum-internal#105): the portion with Onkelos
    beside each verse, the haftarah with the reader's own language beside it, and the
    reader's words of the week — one page, set once, for a Shabbat without a screen.
    `looked` says which words they are: looked up, or where no look-up names its word,
    kept; the list's heading says which.

    A `view` is the reader's page as it was when they pressed Download (targum-internal
    #415): which companions, the vowels and the te'amim, beside or under, the marks, one
    aliyah or the whole portion and whether the haftarah follows. Given, it decides those
    in place of `into`, `vowels`, `accents`, `under` and `size`. `marker` says which words
    are marked and what is set above them (`learning_marker`, `rare_marker`); the view's
    `gloss` turns it off.

    Built from the cut rather than from a folder: on a laptop the portion is cut again
    from the books on the shelf, which is free, the way `targum parasha leyning` cuts it,
    and on the box from what the build kept beside its reader (`parasha.sheet`). The
    portion carries no per-aliyah word lists — a portion's hard words would be pages of
    them — and the haftarah none either; the one list is the reader's own week.
    """
    if view is not None:
        vowels, accents, under, size = view.vowels, view.taamim, view.under, view.size
        if not view.gloss:
            marker = None
    chrome = own_language(portion.translations, reads)

    def companions_of(text: Cut, *, targum: bool) -> list[Translation]:
        if view is not None and view.companions is not None:
            chosen = [companion(text.translations, key) for key in view.companions]
            found = [
                one
                for one in chosen
                if one is not None and (targum or one.target_language not in BESIDE)
            ]
            unique = list({id(one): one for one in found}.values())
            if unique or not view.companions:
                return unique
        if not targum:
            # Read once, and never beside a targum (targum-internal#203): the reader's
            # own language, as the portion page sets it.
            return [_translation(text.translations, own_language(text.translations, reads))]
        arc = next(
            (t.target_language for t in text.translations if t.target_language in BESIDE), None
        )
        return [_translation(text.translations, into or arc or chrome)]

    def part(text: Cut, english: str, *, targum: bool) -> Part:
        beside = companions_of(text, targum=targum)
        # The meanings set above a word are in the page's language, whatever stands
        # beside the verse: Onkelos is not a language a meaning is written in.
        glossary = next(
            (text.glossaries[code] for code in (chrome, "en") if code in text.glossaries), None
        )
        chapters = _chapters(
            text.segmented,
            beside,
            text.vocalization,
            text.annotation,
            glossary,
            known=None,
            vowels=vowels,
            accents=accents,
            lists=False,
            marker=marker,
            chrome=chrome,
        )
        return Part(
            title=text.document.title or "",
            english=english,
            chapters=chapters,
            source_language=text.segmented.language,
            target_language=beside[0].target_language if beside else chrome,
        )

    first = part(portion, name, targum=True)
    if view is not None and view.aliyah is not None:
        if not 1 <= view.aliyah <= len(first.chapters):
            raise TargumError(
                f"{name} has no aliyah {view.aliyah}.",
                f"It has {len(first.chapters)}.",
            )
        first.chapters = [first.chapters[view.aliyah - 1]]
    parts = [first]
    wants_haftarah = view is None or view.haftarah
    if haftarah is not None and haftarah.translations and wants_haftarah:
        # Its range as a chumash prints it, and why it is this week's where a special
        # Shabbat has displaced the portion's own.
        summary = haftarah.document.source.removeprefix("sefaria:")
        parts.append(
            part(
                haftarah,
                " · ".join(one for one in (summary, haftarah_note) if one),
                targum=False,
            )
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
        address=address,
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


def write_pdf_within(html: str, out: Path, seconds: float) -> Path:
    """`write_pdf` in a process of its own, stopped after `seconds` (targum-internal#415).

    For the server, where a page is set because somebody pressed Download. WeasyPrint
    holds the thread it runs on until it is done and cannot be told to stop; in a child
    process a page that runs long is killed rather than waited on, and what it held goes
    back when it exits. Bereshit with its haftarah, measured on 2026-10-04: seven seconds
    of CPU and a hundred megabytes at the peak.
    """
    import subprocess
    import tempfile

    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=out.parent) as scratch:
        page = Path(scratch) / "page.html"
        page.write_text(html, encoding="utf-8")
        setting = Path(scratch) / "page.pdf"
        try:
            done = subprocess.run(
                [sys.executable, "-m", "targum.render.printed", str(page), str(setting)],
                capture_output=True,
                text=True,
                timeout=seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as error:
            raise TargumError(
                f"The PDF took longer than {seconds:.0f} seconds to set, and was stopped.",
                "Try again in a minute.",
            ) from error
        if done.returncode != 0 or not setting.is_file():
            said = [line for line in done.stderr.strip().splitlines() if line.strip()]
            raise TargumError(said[-1] if said else "The PDF could not be set.")
        setting.replace(out)
    return out


def _main(arguments: list[str]) -> int:
    """`python -m targum.render.printed page.html page.pdf`: what `write_pdf_within`
    runs. The refusal is the last line on stderr, which is what the caller reads."""
    page, out = (Path(one) for one in arguments)
    try:
        write_pdf(page.read_text(encoding="utf-8"), out)
    except TargumError as error:
        print(error.message, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
