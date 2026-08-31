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
from .paths import write_atomic

# 2: M2 added source_hash and ingester to Document, and the byline block kind.
# 3: M3 added Link and Alignment. M4 added Token and Annotation.
# 4: added Vocalization.
SCHEMA_VERSION = 4

# BCP-47 primary subtags written right to left.
RTL_LANGUAGES = frozenset({"he", "iw", "ar", "fa", "ur", "yi", "ji", "arc", "dv", "ps", "sd", "ug"})


def direction_for(language: str) -> str:
    """'rtl' or 'ltr' from a BCP-47 tag. No script or direction is ever hardcoded."""
    return "rtl" if language.split("-")[0].lower() in RTL_LANGUAGES else "ltr"


# The one shelf targum serves from a pinned, published, Masoretic edition. Scripture gets
# rules the rest of the library does not: verses are never re-split, never machine-pointed,
# and paired by their numbering rather than matched. Asked in four places, so it is written
# once — four hand-copied prefix tests is how the fifth comes to disagree with the others.
def is_biblical(source: object) -> bool:
    return str(source or "").startswith("sefaria:")


class BlockKind(StrEnum):
    heading = "heading"
    byline = "byline"
    paragraph = "paragraph"
    verse = "verse"
    blockquote = "blockquote"
    #: One person's line in a dialogue. Its own kind rather than a paragraph because a
    #: reader shows it differently — who is speaking sits beside it — and because the
    #: speaker must not be words inside the text, where the diacritizer would point it,
    #: the lemmatizer would count it as vocabulary and a voice would read it aloud.
    turn = "turn"


class Style(StrEnum):
    natural = "natural"
    direct = "direct"


class Artifact(BaseModel):
    """Base for anything written to disk."""

    schema_version: int = SCHEMA_VERSION

    def write(self, path: Path) -> Path:
        """Write it whole, or not at all.

        The glossary is rewritten every batch while a reader is polling for it, so a
        half-written file is a thing someone can actually read.
        """
        body = json.dumps(self.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n"
        return write_atomic(path, body)


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
    #: Where this block sits in the work that numbers itself — "Ruth 1:1". Set only by a
    #: source that has such numbering, which today is scripture. It is not decoration and
    #: it is not the block's id: a recording is aligned to verses, and a verse is the only
    #: thing a recording and a text both agree on. Left out of `body()` on purpose, so
    #: giving an existing document its refs costs a re-ingest and not a re-translation.
    ref: str = ""
    #: Which side of a dialogue said this, where the block is a turn. Absent everywhere
    #: else, and optional so every artifact written before dialogues existed still reads.
    speaker: str | None = None


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
    #: The block's own ref, carried through. A verse is never split, so a segment of a
    #: numbered text is a verse and can be addressed as one.
    ref: str = ""


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
    # The part of speech Stanza gave the content word, as a Universal POS tag. Read by
    # nothing in the reader; it is how a difficulty count leaves names and numerals
    # out, since a name is not a word a learner has to acquire. Absent on annotations
    # written before it existed.
    pos: str | None = None
    # Hebrew verbs only, and only where Stanza tagged a binyan. The root is worked out
    # from the lemma and the binyan together, and is absent wherever that could not be
    # done honestly — see annotate/hebrew.py.
    binyan: str | None = None
    root: str | None = None
    # Which Hebrew this word belongs to, where its two registers disagree: "biblical"
    # for a word ordinary in the Tanakh and rare today, "modern" for one in use that the
    # Tanakh never had. None wherever they agree, which is most words. On the lemma's
    # behalf rather than the occurrence's — see annotate/register.py. Named at length
    # because a field called `register` shadows the metaclass method of the same name
    # and pydantic warns about it; everything downstream of here calls it the register.
    word_register: str | None = None
    # How this occurrence is said, in IPA with the stress marked. On the token rather
    # than on the lemma because the reading is a property of the occurrence: בצל is
    # batsˈal in one sentence and btsˈel in the next, and the lemma cannot say which.
    # Absent where the word has no vowels to read — see annotate/pronounce.py.
    ipa: str | None = None
    # How a split surface is put together, said the card's way: "ו and + ל to + בית".
    # English like the card's other labels, whatever the reader's target language —
    # the precedent `Glossary.parts_of_speech` set. Only on split tokens, and absent
    # on annotations written before it existed — see annotate/hebrew.py.
    built: str | None = None
    # The slice of Stanza's morphology the card reads — person, gender, number, tense,
    # verb form, and the construct state — in the pipe format Stanza gave it. On the
    # occurrence, because agreement is: מילים is Plur where מילה is Sing.
    feats: str | None = None


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
    #: Verbs: the form a learner keeps — the infinitive with its governing preposition.
    #: Facts about the source word riding with the pair, only where there is one to say;
    #: absent for every lemma glossed before 2026-08-31, filling in as words are looked up.
    citations: dict[str, str] = Field(default_factory=dict)
    #: Nouns: the plural, only where it lies about the gender or changes the stem.
    plurals: dict[str, str] = Field(default_factory=dict)


def glossary_path(folder: Path, target: str) -> Path:
    """Where a text's meanings for one target language live.

    Named for the pair, the way a translation already is
    (`{provider}.{style}.{lang}.json`) and the way the standalone `gloss` command already
    writes one. It was `glossary.json`, with nothing in the name to say which language it
    was written in — so building a text into Russian wrote over its English meanings in
    place, and the reader then handed Russian to whoever asked for English.
    """
    return folder / f"glossary.{target}.json"


def glossaries_in(folder: Path) -> dict[str, Glossary]:
    """Every glossary a build folder holds, by target language.

    A `glossary.json` with no language in its name is one written before the name carried
    the language, and it is read rather than ignored — the artifact has always recorded
    its own `target_language`, so nothing has to be guessed and no file has to be
    renamed. That is what keeps this from being a migration.
    """
    found: dict[str, Glossary] = {}
    legacy = read_artifact(Glossary, folder / "glossary.json")
    if legacy is not None:
        found[legacy.target_language or "en"] = legacy
    for path in sorted(folder.glob("glossary.*.json")):
        book = read_artifact(Glossary, path)
        if book is not None:
            # The name is the fallback, not the answer: the file says what it is.
            found[book.target_language or path.stem.rsplit(".", 1)[-1]] = book
    return found


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


class Vocalization(Artifact):
    """The pointed form of each segment, for the reader's nikkud toggle.

    Nikkud only ever adds marks above the letters, never changes them, so every entry
    here has the same consonant skeleton as the segment it belongs to. Segments that end
    up with no marks at all are left out: there is nothing to toggle for them.
    """

    document_hash: str
    language: str
    vocalizer: str
    model: str | None = None
    segments: dict[str, str] = Field(default_factory=dict)
    # Segments carrying at least one word a diacritizer pointed rather than the source.
    # The reader marks these, because a diacritizer is 55-73% right on classical Hebrew
    # and a visibly uncertain vowel beats a confidently wrong one. Same reasoning as
    # Translation.coarse above.
    machine: list[str] = Field(default_factory=list)
    # Segments whose vocalized form was refused because it changed a letter rather than
    # only the marks. Kept rather than merely counted: which sentence broke is the first
    # thing worth knowing when a diacritizer starts misbehaving.
    rejected: list[str] = Field(default_factory=list)
