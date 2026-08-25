"""Turning a source into a normalized Document."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence
from typing import Protocol

from ..ids import block_id
from ..models import Block, BlockKind, Document
from .spacing import unglue

# Enough to tell the v1 languages apart without a detection dependency. Anything else
# falls back to English, and --from overrides it.
_SCRIPT_RANGES: list[tuple[str, range]] = [
    ("he", range(0x0590, 0x0600)),
    ("ru", range(0x0400, 0x0530)),
    ("ar", range(0x0600, 0x0700)),
]


Paragraph = tuple[BlockKind, int | None, str]

# A chapter marker on a line of its own. Gutenberg and most plain-text editions write
# these as bare numerals or roman numerals, which carry no markup at all. Without
# recognising them, structural alignment has nothing to anchor on.
_CHAPTER = re.compile(
    r"^(?:(?:chapter|part|book|глава|часть|פרק)\s+)?"
    r"(?:[IVXLC]{1,7}|\d{1,3}|[\u0590-\u05EA]{1,3})\.?$",
    re.I,
)
_MAX_HEADING_WORDS = 8

# What a section title looks like in a text that carries no markup at all. Ben Yehuda's
# .txt of Der Judenstaat is four hundred paragraphs and not one heading: "הקדמה",
# "השאלה היהודית" and fifty more sit in the file as ordinary paragraphs, so the reader
# has no contents page, no chapters, and no way to see where it is.
#
# A line is a title when it is short, stands alone, does not end the way a sentence
# ends, and has running text under it. That last clause is what keeps a poem out of
# this: verse is short line after short line, and a title with nothing beneath it to
# introduce is not a title.
_TITLE_MAX_CHARS = 60
_SENTENCE_END = ".!?,:;…׃־"
_BODY_WORDS = 20

# And the whole pass steps back where short lines are the shape of the text rather than
# the exception to it. Above this share, the document is verse, dialogue or a list, and
# nothing here can tell a title from a line.
_TITLE_SHARE = 0.3

# The words a Hebrew text names its own parts with. Closed and short on purpose: this
# one is used to take a paragraph apart, which is a stronger claim than marking one, and
# it exists because a source that drops a line break drops it between a title and what
# is above it. Der Judenstaat opens with the translator's name and the word הקדמה run
# together on one line — separating the words is the spacing repair's job, and knowing
# that the second of them is a title rather than the last word of the byline is this.
_TITLES = frozenset(
    {
        "הקדמה",
        "מבוא",
        "פתיחה",
        "פתח דבר",
        "אחרית דבר",
        "דבר המתרגם",
        "דבר המחבר",
        "נספח",
        "סיכום",
        "תוכן העניינים",
    }
)


def with_front_matter(
    paragraphs: list[Paragraph], title: str | None, author: str | None
) -> list[Paragraph]:
    """Put the title and the byline into the text itself.

    A headline is part of what you are reading, not a label on the window, and it
    should be translated and tappable like everything else. Every source does this the
    same way so a news article and a novel come out with the same shape.
    """
    out = list(paragraphs)
    own_title = next(
        (i for i, (kind, level, _) in enumerate(out) if kind is BlockKind.heading and level == 1),
        None,
    )
    if title and own_title is None:
        out.insert(0, (BlockKind.heading, 1, title))
        own_title = 0
    if author:
        # Under the title where there is one, at the top otherwise.
        out.insert(0 if own_title is None else own_title + 1, (BlockKind.byline, None, author))
    return out


def classify_plain_paragraph(chunk: str) -> Paragraph:
    """Tell a chapter marker from a paragraph in text that carries no markup.

    Gutenberg and most plain-text editions write chapter numbers as a bare line. Left
    as paragraphs they are noise, and worse, structural alignment loses the landmarks
    it anchors on.
    """
    line = " ".join(chunk.split())
    if len(line.split()) <= _MAX_HEADING_WORDS and _CHAPTER.match(line):
        return (BlockKind.heading, 2, line)
    return (BlockKind.paragraph, None, line)


def normalize(text: str) -> str:
    """NFC, and nothing else.

    Hebrew arrives in inconsistent normalization, which breaks alignment and lookup in
    ways that are miserable to debug. Niqqud is left alone: absent in most texts, and
    meaningful when present.
    """
    text = unicodedata.normalize("NFC", text.replace("\r\n", "\n").replace("\r", "\n"))
    return re.sub(r"[ \t ]+", " ", text)


def detect_language(text: str) -> str:
    """Guess a BCP-47 tag from the dominant script."""
    counts = dict.fromkeys((tag for tag, _ in _SCRIPT_RANGES), 0)
    latin = 0
    for char in text:
        point = ord(char)
        if not char.isalpha():
            continue
        for tag, span in _SCRIPT_RANGES:
            if point in span:
                counts[tag] += 1
                break
        else:
            if point < 0x0250:
                latin += 1
    best = max(counts, key=lambda tag: counts[tag])
    return best if counts[best] > latin else "en"


def build_document(
    source: str,
    blocks: list[Block],
    *,
    ingester: str,
    language: str | None = None,
    title: str | None = None,
    author: str | None = None,
    structure: bool = False,
) -> Document:
    language = language or detect_language("\n\n".join(b.text for b in blocks))

    # Where the source dropped the space between two words, put it back — here, once,
    # rather than in the reader, which would pay for it on every page it ever opens. See
    # `spacing.unglue` for what it will and will not touch.
    blocks = [block.model_copy(update={"text": unglue(block.text, language)}) for block in blocks]

    # Then, and only for a source with no markup to state its structure with, read the
    # section titles out of the prose. After the spacing repair rather than before it:
    # the title this finds at the end of Der Judenstaat's first line is a title only
    # once the line has stopped being one word — see `split_trailing_title`.
    if structure:
        blocks = blocks_from_paragraphs(infer_headings([(b.kind, b.level, b.text) for b in blocks]))

    document = Document(
        source=source,
        title=title,
        author=author,
        language=language,
        blocks=blocks,
        ingester=ingester,
    )
    document.content_hash = document.recompute_hash()
    return document


def looks_like_a_title(text: str) -> bool:
    """Whether this line is shaped like a section title, read on its own."""
    line = text.strip()
    if not line or "\n" in line:
        return False
    if len(line) > _TITLE_MAX_CHARS or len(line.split()) > _MAX_HEADING_WORDS:
        return False
    if line[-1] in _SENTENCE_END:
        return False
    # A row of asterisks is a divider, not a title, and a line of digits is a page
    # number. Something has to be readable in it.
    return any(char.isalpha() for char in line)


def split_trailing_title(text: str) -> tuple[str, str] | None:
    """A line and the section title a source ran onto the end of it, or None.

    Only for a line with no sentence punctuation anywhere in it — a title, a byline, a
    line of front matter. Running prose ends in a full stop, and a paragraph that ends
    in the word הקדמה after four sentences is a paragraph about an introduction.
    """
    line = " ".join(text.split())
    if any(mark in line for mark in _SENTENCE_END):
        return None
    words = line.split()
    for size in (3, 2, 1):
        if len(words) <= size:
            continue
        tail = " ".join(words[-size:])
        if tail in _TITLES:
            return " ".join(words[:-size]), tail
    return None


def infer_headings(paragraphs: Sequence[Paragraph], *, split: bool = True) -> list[Paragraph]:
    """Find the section titles in a text that arrived with no markup.

    Only called for plain text, and only for a text that has none of its own. Markdown,
    EPUB and HTML all say where their headings are, and a page that says it has none is
    a page saying something — a news front page is nothing but short lines, and reading
    its navigation as chapter titles is worse than leaving it flat. The title a front
    matter added is not structure, so a lone level-1 heading does not count as the text
    having said anything.
    """
    out: list[Paragraph] = []
    for kind, level, text in paragraphs:
        # Taking a paragraph in two renumbers everything after it, which is fine on the
        # way in and is not something to do to a text already on disk: its sentences are
        # keyed to the blocks they came from, and its English is keyed to its sentences.
        # `targum repair` therefore marks whole blocks and never splits one.
        parted = split_trailing_title(text) if split and kind is BlockKind.paragraph else None
        if parted is None:
            out.append((kind, level, text))
            continue
        line, title = parted
        out.append((kind, level, line))
        out.append((BlockKind.heading, 2, title))

    if any(kind is BlockKind.heading and (level or 1) > 1 for kind, level, _ in out):
        return out
    if any(
        kind not in (BlockKind.paragraph, BlockKind.heading, BlockKind.byline) for kind, _, _ in out
    ):
        return out

    candidates = [
        index
        for index, (kind, _, text) in enumerate(out)
        if kind is BlockKind.paragraph and looks_like_a_title(text)
    ]
    if not candidates or len(candidates) > len(out) * _TITLE_SHARE:
        return out

    for index in candidates:
        under = next(
            (out[n] for n in range(index + 1, len(out)) if out[n][2].strip()),
            None,
        )
        # Running text under it, or another title above that text. A title is a thing
        # that introduces something.
        if under is None:
            continue
        if len(under[2].split()) < _BODY_WORDS and index + 1 not in candidates:
            continue
        kind, _, text = out[index]
        out[index] = (BlockKind.heading, 2, text)
    return out


def blocks_from_paragraphs(paragraphs: Sequence[Paragraph]) -> list[Block]:
    return [
        Block(id=block_id(index), kind=kind, level=level, text=text)
        for index, (kind, level, text) in enumerate(paragraphs)
        if text.strip()
    ]


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Pull a leading --- block off a file, if there is one.

    Deliberately small: title, author and language are the only keys that change what
    the reader shows, and a real YAML parser is a dependency for no gain.
    """
    if not text.startswith("---\n"):
        return {}, text
    _, _, rest = text.partition("---\n")
    block, sep, body = rest.partition("\n---")
    if not sep:
        return {}, text
    fields: dict[str, str] = {}
    for line in block.split("\n"):
        key, colon, value = line.partition(":")
        if colon and key.strip():
            fields[key.strip().lower()] = value.strip().strip("\"'")
    return fields, body.lstrip("\n")


class Ingester(Protocol):
    """Every ingester turns one kind of source into a Document."""

    @property
    def name(self) -> str:
        """Name and version. A change here re-ingests rather than looking like an edit."""

    def load(self, source: str) -> Document: ...


def to_markdown(document: Document) -> str:
    """The inverse of ingest, so a fetched text can be edited before it is built.

    The author is written as frontmatter rather than as a byline block, so reading the
    result back produces the same document.
    """
    front: list[str] = []
    if document.title:
        front.append(f"title: {document.title}")
    if document.author:
        front.append(f"author: {document.author}")
    front.append(f"language: {document.language}")

    lines = ["---", *front, "---", ""]
    for block in document.blocks:
        if block.kind is BlockKind.byline:
            continue
        if block.kind is BlockKind.heading:
            lines.append("#" * (block.level or 1) + " " + block.text)
        elif block.kind is BlockKind.blockquote:
            lines.append("> " + block.text)
        else:
            lines.append(block.text)
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
