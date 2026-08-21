"""The artifacts every stage reads and writes.

These models are the contract between stages. They are versioned, they go to disk as
readable JSON, and the cache key includes the schema version, so a change here can
never serve a stale artifact against new code.
"""

from __future__ import annotations

import json
from enum import StrEnum
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel, Field

from .ids import content_hash

# 2: M2 added source_hash and ingester to Document, and the byline block kind.
# 3: M3 added Link and Alignment. M4 added Token and Annotation.
SCHEMA_VERSION = 3

# BCP-47 primary subtags written right to left.
RTL_LANGUAGES = frozenset({"he", "iw", "ar", "fa", "ur", "yi", "ji", "arc", "dv", "ps", "sd", "ug"})


def direction_for(language: str) -> str:
    """'rtl' or 'ltr' from a BCP-47 tag. No script or direction is ever hardcoded."""
    return "rtl" if language.split("-")[0].lower() in RTL_LANGUAGES else "ltr"


class BlockKind(StrEnum):
    heading = "heading"
    byline = "byline"
    paragraph = "paragraph"
    verse = "verse"
    blockquote = "blockquote"


class Style(StrEnum):
    natural = "natural"
    direct = "direct"


class Artifact(BaseModel):
    """Base for anything written to disk."""

    schema_version: int = SCHEMA_VERSION

    def write(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return path


A = TypeVar("A", bound=Artifact)


def read_artifact(cls: type[A], path: Path) -> A | None:
    """Load an artifact, or None if it is absent or from an older schema."""
    if not path.exists():
        return None
    try:
        data: Any = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict) or data.get("schema_version") != SCHEMA_VERSION:
        return None
    try:
        return cls.model_validate(data)
    except Exception:
        return None


class Block(Artifact):
    """One structural unit of the source: a paragraph, a heading, a line of verse."""

    id: str
    kind: BlockKind = BlockKind.paragraph
    level: int | None = None
    text: str


class Document(Artifact):
    """Ingest output. Hand-editable: fix a bad extraction here and rerun."""

    source: str
    title: str | None = None
    author: str | None = None
    language: str
    blocks: list[Block] = Field(default_factory=list)
    content_hash: str = ""
    source_hash: str = ""
    ingester: str = ""

    @property
    def direction(self) -> str:
        return direction_for(self.language)

    def body(self) -> str:
        return "\n\n".join(block.text for block in self.blocks)

    def recompute_hash(self) -> str:
        """The hash the blocks actually imply.

        Never trust the stored value: a hand-edited document.json carries the old hash,
        and trusting it would serve stale segments against new text.
        """
        return content_hash(self.body())


class Segment(Artifact):
    """One sentence. The unit everything downstream is keyed to."""

    id: str
    block_id: str
    block_index: int
    index: int
    kind: BlockKind = BlockKind.paragraph
    level: int | None = None
    text: str


class SegmentedDocument(Artifact):
    document_hash: str
    language: str
    segmenter: str
    segments: list[Segment] = Field(default_factory=list)

    @property
    def direction(self) -> str:
        return direction_for(self.language)


class Token(Artifact):
    """One word of the source, with what makes it hard.

    Offsets are into the segment's own text, so the reader can mark words without the
    HTML having to carry a span for every word it might never show.
    """

    start: int
    end: int
    surface: str
    lemma: str
    band: int
    # Hebrew attaches prefixes directly to words, so the same string can be one word or
    # a prefix plus a word. Where the segmenter split a token, that is recorded: the
    # reading is a decision, not a fact.
    split: bool = False


class Annotation(Artifact):
    """Difficulty bands for one document."""

    document_hash: str
    language: str
    annotator: str
    method: str
    method_note: str
    band_count: int = 6
    tokens: dict[str, list[Token]] = Field(default_factory=dict)

    def counts(self) -> dict[int, int]:
        out: dict[int, int] = {}
        for tokens in self.tokens.values():
            for token in tokens:
                out[token.band] = out.get(token.band, 0) + 1
        return dict(sorted(out.items()))


class Glossary(Artifact):
    """Dictionary forms and what they mean, for one language pair.

    Cached per lemma across every text, so the second book in a language costs a
    fraction of the first.
    """

    source_language: str
    target_language: str
    provider: str
    entries: dict[str, str] = Field(default_factory=dict)
    parts_of_speech: dict[str, str] = Field(default_factory=dict)


class Link(Artifact):
    """One pairing between source segments and target segments.

    Both sides are lists because translators merge and split. An empty list on either
    side is a null link: something the translator dropped, or added.
    """

    source: list[str] = Field(default_factory=list)
    target: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    coarse: bool = False

    @property
    def kind(self) -> str:
        return f"{len(self.source)}:{len(self.target)}"


class Alignment(Artifact):
    """How one existing translation maps onto the source."""

    name: str
    document_hash: str
    translation_hash: str
    source_language: str
    target_language: str
    aligner: str
    length_ratio: float = 1.0
    links: list[Link] = Field(default_factory=list)

    def coverage(self) -> float:
        """The share of links that pair something with something."""
        if not self.links:
            return 0.0
        paired = sum(1 for link in self.links if link.source and link.target)
        return paired / len(self.links)


class Translation(Artifact):
    """One rendering of the source, keyed by segment ID.

    Several of these can exist for one document. The reader switches between them by
    swapping which mapping it draws from, which is also how aligned human translations
    will arrive in M3.
    """

    name: str
    document_hash: str
    source_language: str
    target_language: str
    provider: str
    model: str | None = None
    style: Style = Style.natural
    kind: str = "machine"
    segments: dict[str, str] = Field(default_factory=dict)
    # Segments whose pairing is paragraph-level rather than sentence-level. The reader
    # marks these, because a visibly coarser pairing beats a confidently wrong one.
    coarse: list[str] = Field(default_factory=list)
    confidence: dict[str, float] = Field(default_factory=dict)

    @property
    def direction(self) -> str:
        return direction_for(self.target_language)
