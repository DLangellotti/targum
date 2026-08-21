"""Turning artifacts into readable HTML.

The output is split into sections rather than written as one file. A full-length book
with several translations and, later, per-token annotation runs to tens of megabytes,
and a phone browser will not open it. Splitting is decided here, at the top of the
renderer, because it is not something that can be added later without a rewrite.
"""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass, field
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
    direction_for,
)

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
    """JSON safe to sit inside a <script> element.

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
    return env


def start_page(token: str, limit: float) -> str:
    """The page targum serve hands you, built with the reader's own type and palette."""
    from ..translate.prompts import OFFERED, language_name

    return (
        _environment()
        .get_template("start.html.j2")
        .render(
            token=token,
            limit=limit,
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
) -> list[Path]:
    """Write the reader. Returns every file written, index first."""
    if not translations:
        raise ValueError("a reader needs at least one translation")

    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)

    env = _environment()
    sections = split_sections(segmented)
    by_id = {segment.id: segment for segment in segmented.segments}
    single = len(sections) == 1

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
                    rows.append(
                        [
                            token.start,
                            token.end,
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
            primary=translations[0].segments,
            primary_coarse=set(translations[0].coarse),
            data=embed_json(
                {
                    "translations": payload,
                    "words": words,
                    "lemmas": lemmas,
                    "glosses": glosses,
                    "levelNames": BAND_NAMES,
                    # Which text this is. Lists are kept per document, not per
                    # language, so reading two articles does not pool their words.
                    "document": segmented.document_hash,
                    "title": document.title or "",
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
