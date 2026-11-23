"""A text that arrived as pages — pictures read by the model, or a PDF's own text layer.

Both hand over the same thing: for each page, its lines. This turns that into a
Document the pipeline reads like any other, and it is one place rather than two so a
screenshot and a handout come out the same shape.

A page's lines are grouped into paragraphs at blank lines, and the lines of one
paragraph are joined with a space — a printed page wraps its paragraphs, and a
segmenter given one line per wrapped line would cut every sentence at the margin. A
messaging conversation — WhatsApp, Telegram, SMS, photographed off a phone — is turns
instead (2026-09-07): each `name: message` paragraph becomes a `turn` block with the
name on the block and out of the text, which is how the shelf's own dialogues are
drawn — the speaker beside the line, never pointed, never counted, never read aloud.
Each block carries the page it came from as its `ref` ("p3"), which is what a
facsimile could stand on later and what the reader can show now. A block with no
Hebrew letters and some Latin ones is marked English, so the Hebrew lemmatizer leaves
it alone rather than tagging it (`annotate.base.unread`).

Two things a photographed page hands over that are not the text (2026-11-23, a reader's
book): its printed page number, which came back as a paragraph of its own, became a
heading and named the book "3"; and a paragraph the model began, broke off and read
again from the start, which put its opening words in the reader twice. A paragraph
that is only a number is left out, and so is one that the next paragraph begins again.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from pathlib import Path

from ..ids import block_id
from ..models import Block, BlockKind, Document
from .base import build_document, classify_plain_paragraph, detect_language, normalize

_HEBREW = re.compile(r"[א-ת]")
_LATIN = re.compile(r"[A-Za-z]")
#: `name: message`. A name is short and has no sentence punctuation before the colon,
#: so a line of prose with a colon in its middle stays prose.
_TURN = re.compile(r"^([^:：\n.!?،؛]{1,40}?)\s*[:：]\s*(.+)$", re.S)

#: A printed page number: digits alone, perhaps between dashes ("- 12 -").
_FOLIO = re.compile(r"^[\s\-–—]*\d{1,4}[\s\-–—]*$")

#: How alike a paragraph and the start of the next must be for the first to be a false
#: start of the second. A false start is at least this long, so a short refrain a page
#: repeats on purpose stays.
RESTART_SIMILARITY = 0.85
RESTART_CHARS = 20

#: How much of a title is a title. The first line of a page names it well enough for a
#: shelf; a whole first paragraph does not.
TITLE_CHARS = 60


def paragraphs_of(lines: list[str], *, conversation: bool = False) -> list[str]:
    """Blank-line groups, each joined into one line of prose, without page numbers and
    false starts. A conversation keeps them all: "5" is a fair answer in a chat."""
    out: list[str] = []
    held: list[str] = []
    for line in [*lines, ""]:
        if line.strip():
            held.append(" ".join(line.split()))
            continue
        if held:
            out.append(" ".join(held))
            held = []
    if conversation:
        return out
    out = [paragraph for paragraph in out if not is_folio(paragraph)]
    return [
        paragraph
        for here, paragraph in enumerate(out)
        if here + 1 == len(out) or not restarted(paragraph, out[here + 1])
    ]


def is_folio(paragraph: str) -> bool:
    """Whether a paragraph is nothing but a printed page number."""
    return bool(_FOLIO.match(paragraph))


def restarted(paragraph: str, following: str) -> bool:
    """Whether `following` begins `paragraph` over again: a reading that broke off."""
    if len(paragraph) < RESTART_CHARS or len(following) <= len(paragraph):
        return False
    start = following[: len(paragraph)]
    return SequenceMatcher(None, paragraph, start).ratio() >= RESTART_SIMILARITY


def mixed(line: str) -> bool:
    """Whether a line carries both scripts, which is where a text layer scrambles."""
    return bool(_HEBREW.search(line)) and bool(_LATIN.search(line))


def turn_of(paragraph: str) -> tuple[str, str] | None:
    """The speaker and what they said, or None for a paragraph that names nobody."""
    found = _TURN.match(paragraph.strip())
    if found is None:
        return None
    speaker, said = found.group(1).strip(), found.group(2).strip()
    if not speaker or not said or speaker.split()[0][:1].isdigit():
        return None
    return speaker, said


def conversation_title(speakers: list[str]) -> str:
    """The other side's name, for the shelf: a chat with אמא is called אמא."""
    others = []
    for name in speakers:
        if name.lower() in ("me", "אני", "you") or name in others:
            continue
        others.append(name)
    return ", ".join(others[:3])


def title_of(pages: list[list[str]]) -> str:
    for lines in pages:
        for line in lines:
            words = line.split()
            if not words or is_folio(line):
                continue
            title = " ".join(words)
            if len(title) <= TITLE_CHARS:
                return title
            short: list[str] = []
            for word in words:
                if len(" ".join([*short, word])) > TITLE_CHARS:
                    break
                short.append(word)
            return " ".join(short) or title[:TITLE_CHARS]
    return ""


def document_from_pages(
    source: str,
    pages: list[list[str]],
    *,
    ingester: str,
    source_hash: str,
    title: str | None = None,
    language: str | None = None,
    conversation: bool = False,
) -> Document:
    """One Document from pages of lines. Raises nothing; an empty text is the caller's
    to refuse, since what to say about it depends on where it came from. With
    `conversation`, a `name: message` paragraph is a turn said by that name."""
    blocks: list[Block] = []
    speakers: list[str] = []
    last = ""
    for number, lines in enumerate(pages, start=1):
        for text in paragraphs_of([normalize(line) for line in lines], conversation=conversation):
            said = turn_of(text) if conversation else None
            if said is not None:
                last, text = said
                if last not in speakers:
                    speakers.append(last)
            if conversation and last:
                # A message with no name is the same person, still talking.
                kind, level, line = BlockKind.turn, None, " ".join(text.split())
            else:
                kind, level, line = classify_plain_paragraph(text)
            own = "en" if not _HEBREW.search(line) and _LATIN.search(line) else None
            blocks.append(
                Block(
                    id=block_id(len(blocks)),
                    kind=kind,
                    level=level,
                    text=line,
                    ref=f"p{number}",
                    language=own,
                    speaker=last if kind is BlockKind.turn else None,
                )
            )
    hebrew = "\n".join(block.text for block in blocks if block.language is None)
    if title is None and conversation:
        title = conversation_title(speakers) or None
    document = build_document(
        source,
        blocks,
        ingester=ingester,
        language=language or (detect_language(hebrew) if hebrew.strip() else None),
        title=title if title is not None else (title_of(pages) or Path(source).stem),
    )
    # The pipeline's own fallback hashes the source decoded as UTF-8, which for a
    # picture says nothing. The bytes, then — set by the ingester that read them.
    # `ref` and `language` ride on the blocks handed over, and `build_document` copies
    # blocks rather than rebuilding them from paragraph tuples, so both survive.
    document.source_hash = source_hash
    return document
