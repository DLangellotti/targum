"""Turning artifacts into readable HTML.

The output is split into sections rather than written as one file. A full-length book
with several translations and, later, per-token annotation runs to tens of megabytes,
and a phone browser will not open it. Splitting is decided here, at the top of the
renderer, because it is not something that can be added later without a rewrite.
"""

from __future__ import annotations

import base64
import json
import mimetypes
import re
import shutil
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path

from jinja2 import Environment, FileSystemLoader
from markupsafe import Markup, escape

from ..annotate.base import BAND_NAMES, method_label
from ..models import (
    Annotation,
    BlockKind,
    Document,
    Glossary,
    SegmentedDocument,
    Translation,
    Vocalization,
    direction_for,
)
from ..translate.prompts import language_name
from ..vocalize import map_span, strip_nikkud

# A section beyond this many segments is split again. Sized so a section stays under a
# megabyte once M4 adds per-token annotation.
MAX_SEGMENTS_PER_SECTION = 400

TEMPLATES = Path(__file__).parent / "templates"
ASSETS = Path(__file__).parent / "assets"

# A run keeps its interior spaces, so "Magma Devs" isolates as one name rather than
# two words with a gap the bidi algorithm is free to reorder.
_LATIN_RUN = re.compile(r"[A-Za-z0-9][A-Za-z0-9 .,:/'’&-]*[A-Za-z0-9]|[A-Za-z0-9]")
_RTL_RUN = re.compile(r"[֐-׿؀-ۿ][֐-ۿ\s.,'\"־-]*[֐-׿؀-ۿ]|[֐-׿]")


@dataclass(slots=True)
class Section:
    number: int
    title: str
    segment_ids: list[str] = field(default_factory=list)

    @property
    def filename(self) -> str:
        return f"sec-{self.number:04d}.html"


def isolate(text: str, direction: str) -> Markup:
    """Wrap opposite-direction runs in <bdi>.

    Without this, a year or a Latin name inside a Hebrew sentence drags its punctuation
    to the wrong end of the line. The browser's own bidi algorithm is correct and still
    produces this, because it has no way to know where the embedded run ends.
    """
    pattern = _LATIN_RUN if direction == "rtl" else _RTL_RUN
    parts: list[str] = []
    position = 0
    for match in pattern.finditer(text):
        parts.append(str(escape(text[position : match.start()])))
        parts.append(f"<bdi>{escape(match.group())}</bdi>")
        position = match.end()
    parts.append(str(escape(text[position:])))
    return Markup("".join(parts))


def embed_json(payload: object) -> Markup:
    r"""JSON safe to sit inside a <script> element.

    The HTML parser ends the element at the first "</script" it meets, even inside a
    JSON string, so a translation containing that sequence would break out into
    markup. Splitting every "</" across an escape closes the door; "<\/" is the same
    string once JSON-decoded.
    """
    return Markup(json.dumps(payload, ensure_ascii=False).replace("</", "<\\/"))


def split_sections(segmented: SegmentedDocument) -> list[Section]:
    """Break at top-level headings, then on length."""
    sections: list[Section] = []
    current: Section | None = None
    has_body = False

    # A heading only opens a new section once the current one holds actual prose.
    # Otherwise a title, or a title and byline, would each become a section of its own.
    front_matter = {BlockKind.heading, BlockKind.byline}

    for segment in segmented.segments:
        starts_section = (
            segment.kind is BlockKind.heading
            and (segment.level or 1) <= 2
            and current is not None
            and has_body
        )
        too_long = current is not None and len(current.segment_ids) >= MAX_SEGMENTS_PER_SECTION
        if current is None or starts_section or too_long:
            title = segment.text if segment.kind is BlockKind.heading else ""
            current = Section(number=len(sections) + 1, title=title)
            sections.append(current)
            has_body = False
        has_body = has_body or segment.kind not in front_matter
        if not current.title and segment.kind is BlockKind.heading:
            current.title = segment.text
        current.segment_ids.append(segment.id)

    for section in sections:
        if not section.title:
            section.title = f"Section {section.number}"
    return sections


def _environment() -> Environment:
    env = Environment(
        loader=FileSystemLoader(TEMPLATES),
        # Unconditionally, not select_autoescape: that helper matches on the final
        # extension, and these templates end in .j2, so it silently escaped nothing.
        # Every template renders text that can come from a fetched web page.
        autoescape=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["isolate"] = isolate
    env.globals["asset"] = lambda name: Markup((ASSETS / name).read_text(encoding="utf-8"))
    env.globals["data_uri"] = _data_uri
    return env


@cache
def _data_uri(name: str) -> str:
    """An asset as a `data:` URI, for the places only a URL will do.

    A built reader is one file in a folder of its own — there is nowhere to put a
    sibling icon and nothing serving it, so the icons ride inside the page. They are
    small enough (the whole set is under 3 kB) not to matter beside the inlined CSS.
    Cached because the same three icons are asked for on every page of every section.
    """
    path = ASSETS / name
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    if mime == "image/svg+xml":
        mime += ";charset=utf-8"
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"


def start_page(token: str, limit: float, budget: float, no_key: str = "") -> str:
    """The page targum serve hands you, built with the reader's own type and palette.

    `no_key` is the notice to show when nothing can be translated. It is passed in
    rather than worked out here, so the page states the same thing the builder would
    have refused with.
    """
    from ..translate.prompts import OFFERED, language_name

    return (
        _environment()
        .get_template("start.html.j2")
        .render(
            token=token,
            limit=limit,
            budget=budget,
            no_key=no_key,
            languages=[(code, language_name(code)) for code in OFFERED],
        )
    )


def holding_page() -> str:
    """What a stranger sees while the product is not open yet.

    Deliberately not the sign-in page: that is a door, and a door presented to somebody
    with no key is a wall that looks like a mistake. This says where things are, and
    keeps the door in the corner for the people who have one.
    """
    return _environment().get_template("holding.html.j2").render()


def signin_page(*, landing: str = "", token: str = "", expired: bool = False) -> str:
    """The door. Three states, one template.

    Empty is the sign-in form. `landing` is the page an emailed link opens, naming the
    account it would sign in without having spent anything to find out. `expired` is
    what a link that has been used or has aged out arrives at, which is a normal thing
    to hit rather than an error.
    """
    return (
        _environment()
        .get_template("signin.html.j2")
        .render(landing=landing, token=token, expired=expired)
    )


def words_page(token: str) -> str:
    """Everything kept, with what it adds up to.

    Built from the browser's own store like the start page, because that is where a
    word list lives; the server only hands over the page.
    """
    from ..translate.prompts import OFFERED

    return (
        _environment()
        .get_template("words.html.j2")
        .render(
            token=token,
            languages=[(code, language_name(code)) for code in OFFERED],
        )
    )


def library_page(token: str) -> str:
    """Texts worth reading, and the ones you have already built.

    The catalogue is baked in rather than fetched: it is a handful of entries that
    ship with targum, and a page that has to ask the server for them would be a page
    that can be empty.
    """
    from ..catalogue import CATALOGUE
    from ..translate.prompts import OFFERED

    return (
        _environment()
        .get_template("library.html.j2")
        .render(
            token=token,
            catalogue=[entry.state() for entry in CATALOGUE],
            languages=[(code, language_name(code)) for code in OFFERED],
        )
    )


def render(
    document: Document,
    segmented: SegmentedDocument,
    translations: list[Translation],
    out_dir: Path,
    annotation: Annotation | None = None,
    glossary: Glossary | None = None,
    vocalization: Vocalization | None = None,
    clean: bool = True,
    glossary_pending: bool = False,
) -> list[Path]:
    """Write the reader. Returns every file written, index first.

    `clean=False` writes over what is already there instead of emptying the directory
    first. It is for the second pass, once the word meanings have arrived: the same
    segments produce the same section files under the same names, so overwriting leaves
    nothing stale behind, and a reader someone has open does not have the page they are
    reading deleted from under them for the moment it takes to write the new one.
    """
    if not translations:
        raise ValueError("a reader needs at least one translation")

    if clean and out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    env = _environment()
    sections = split_sections(segmented)
    by_id = {segment.id: segment for segment in segmented.segments}
    single = len(sections) == 1

    # Two ways to show the same sentence. The bare form is what the page renders by
    # default and the one every stored offset is measured against; the pointed form is
    # the second cell the toggle reveals. Both are built here rather than in the browser
    # so each goes through isolate() and neither has to be reassembled in JavaScript.
    bare: dict[str, str] = {}
    to_bare: dict[str, list[int]] = {}
    for segment in segmented.segments:
        bare[segment.id], to_bare[segment.id] = strip_nikkud(segment.text)
    pointed = dict(vocalization.segments) if vocalization is not None else {}
    machine = set(vocalization.machine) if vocalization is not None else set()

    # Whose pointing this mostly is. A Tanakh or a pointed poem arrives with its vowels
    # already on the page and someone chose it for them, so it opens pointed; a news
    # article whose points are all guessed opens bare, which is how it was written.
    # The marker on a guessed sentence follows the same fact: when every line is
    # guessed it distinguishes nothing and only adds noise, so it is left off.
    from_source = len(pointed) - len(machine)
    source_pointed = bool(pointed) and from_source * 2 >= len(pointed)
    mark_guessed = bool(machine) and len(machine) * 2 < len(pointed)

    source_direction = direction_for(segmented.language)
    target_direction = direction_for(translations[0].target_language)

    shared = {
        "document": document,
        "title": document.title or "targum",
        "sections": sections,
        "source_language": segmented.language,
        "source_direction": source_direction,
        "target_language": translations[0].target_language,
        "target_direction": target_direction,
        "page_direction": source_direction,
        "has_gloss": bool(glossary and glossary.entries),
        "has_nikkud": bool(pointed),
        "source_pointed": source_pointed,
        "mark_guessed": mark_guessed,
        "difficulty": None
        if annotation is None
        else {
            "method": method_label(annotation.method),
            "note": annotation.method_note,
            "annotator": annotation.annotator,
        },
        "translations": [
            {
                "id": f"t{index}",
                "name": translation.name,
                "language": translation.target_language,
                "direction": direction_for(translation.target_language),
                "kind": translation.kind,
                "style": translation.style.value,
                "provider": translation.provider,
            }
            for index, translation in enumerate(translations)
        ],
    }

    written: list[Path] = []
    for section in sections:
        segments = [by_id[sid] for sid in section.segment_ids]
        # Only this section's translations ship with the page, so a long book stays
        # openable on a phone.
        payload = {
            f"t{index}": {
                "text": {sid: translation.segments.get(sid, "") for sid in section.segment_ids},
                # Regions that fell back to paragraph pairing, so the reader can mark
                # them. A learner needs to know the pairing here is approximate.
                "coarse": [sid for sid in section.segment_ids if sid in set(translation.coarse)],
            }
            for index, translation in enumerate(translations)
        }
        # Per-word data ships as offsets rather than as a span for every word. A book
        # has hundreds of thousands of tokens, and emitting markup for all of them up
        # front is what makes a reader too heavy for a phone.
        # Lemmas go in a table and the words point into it: the same lemma turns up
        # dozens of times in a chapter, and repeating it with every token is what makes
        # a page heavy.
        lemmas: list[str] = []
        lemma_at: dict[str, int] = {}
        # Root and binyan belong to the dictionary form, not to the occurrence, so they
        # ride in tables beside the lemmas rather than on every token. Absent for every
        # word that is not a Hebrew verb, and for the verbs whose root could not be had.
        roots: list[str] = []
        binyanim: list[str] = []
        words: dict[str, list[list[int]]] = {}
        if annotation is not None:
            for sid in section.segment_ids:
                tokens = annotation.tokens.get(sid)
                if not tokens:
                    continue
                rows: list[list[int]] = []
                for token in tokens:
                    if token.lemma not in lemma_at:
                        lemma_at[token.lemma] = len(lemmas)
                        lemmas.append(token.lemma)
                        roots.append(token.root or "")
                        binyanim.append(token.binyan or "")
                    # Offsets arrive measured against the segment as ingested, which may
                    # itself be pointed. They ship measured against the bare form, the
                    # one coordinate system the reader keeps everything in. Where the
                    # source had no marks the map is the identity and this costs nothing.
                    start, end = map_span(token.start, token.end, to_bare[sid])
                    rows.append(
                        [
                            start,
                            end,
                            token.band,
                            1 if token.split else 0,
                            lemma_at[token.lemma],
                        ]
                    )
                words[sid] = rows
        glosses = [glossary.entries.get(lemma, "") for lemma in lemmas] if glossary else []
        html = env.get_template("reader.html.j2").render(
            **shared,
            section=section,
            words=bool(words),
            segments=segments,
            bare=bare,
            pointed=pointed,
            machine=machine,
            primary=translations[0].segments,
            primary_coarse=set(translations[0].coarse),
            data=embed_json(
                {
                    "translations": payload,
                    "words": words,
                    "lemmas": lemmas,
                    "roots": roots,
                    "binyanim": binyanim,
                    "glosses": glosses,
                    "levelNames": BAND_NAMES,
                    # Which text this is. Lists are kept per document, not per
                    # language, so reading two articles does not pool their words.
                    "document": segmented.document_hash,
                    "title": document.title or "",
                    # For naming an export of the language's words, which the reader
                    # otherwise only knows by its tag.
                    "languageName": language_name(segmented.language),
                    # Whether the vowels on this text are its own, and so whether it
                    # should open with them showing.
                    "sourcePointed": source_pointed,
                    # Whether a glossary is on its way. Words are looked up one at a
                    # time now, so most readers have none coming and must not sit
                    # asking for one for ten minutes.
                    "glossPending": glossary_pending,
                }
            ),
            previous=None if section.number == 1 else sections[section.number - 2],
            following=None if section.number == len(sections) else sections[section.number],
            standalone=single,
        )
        name = "index.html" if single else section.filename
        written.append(_write(out_dir / name, html))

    if not single:
        index = env.get_template("index.html.j2").render(
            **shared, counts={s.number: len(s.segment_ids) for s in sections}
        )
        written.insert(0, _write(out_dir / "index.html", index))
    return written


def _write(path: Path, html: str) -> Path:
    path.write_text(html, encoding="utf-8")
    return path
