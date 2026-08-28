"""How much of a text somebody already knows.

The one number that answers "what should I read next?", and it was already being computed
and thrown away. The reader works it out for the section in front of you —
`"38% known here · 214 you have not marked yet"` — from the lemmas embedded in that one
page, and its own comment says what it is for: *the reason to know it is choosing what to
read next.* But it is never persisted, never synced, and invisible to every other page,
so the choosing happens somewhere it cannot be seen.

It needs no new tracking to recover. Every build writes an annotation carrying a lemma for
every word, and the account already holds the reader's whole vocabulary keyed by lemma.
The intersection is the answer.

**What it is not.** This is vocabulary, not position: nothing anywhere records how far
through a text somebody has read, and this must never be dressed up as if it did. A high
number means a text will be comfortable, not that it has been finished.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .paths import write_atomic

# Statuses that count as knowing a word. The learning ladder (1-3) is deliberately not
# here: a word somebody is halfway through learning is a word the text will still cost
# them something to read.
KNOWN = 9

ANNOTATION = "annotation.json"
LEMMAS = "lemmas.json"


@dataclass(frozen=True)
class Coverage:
    """What one reader already knows of one text."""

    known: float
    fresh: int
    total: int

    def state(self) -> dict[str, float | int]:
        return {"known": round(self.known, 4), "fresh": self.fresh, "words": self.total}


def lemmas(folder: Path) -> list[str]:
    """Every distinct dictionary form in a built targum.

    Cached beside the annotation it came from, because the annotation is large — 4.4 MB
    for Psalms — and this reduces it to about 21 KB. Written on first ask rather than at
    build time, so it works for the targums that already exist rather than only for ones
    built after today.

    Returns nothing for a targum built without word-level annotation, which is a normal
    state rather than a fault: `--words` is a flag.
    """
    annotation = folder / ANNOTATION
    if not annotation.is_file():
        return []
    # The cache is stamped with the annotation it was read from. An annotation is
    # rewritten in place when the annotator learns something — every word became a
    # token on 2026-08-28 — and a cache that outlived that would go on reporting a
    # denominator a tenth too small, for half the shelf, with nothing to say so.
    try:
        stat = annotation.stat()
        stamp = [stat.st_mtime_ns, stat.st_size]
    except OSError:
        return []
    cached = folder / LEMMAS
    if cached.is_file():
        try:
            found = json.loads(cached.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            found = None
        if isinstance(found, dict) and found.get("stamp") == stamp:
            return [str(lemma) for lemma in found.get("lemmas") or []]

    try:
        loaded = json.loads(annotation.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []

    from .annotate.base import NOT_VOCABULARY

    # A name is not a word the reader has to know, so it is not one they can fail to
    # know either: left out of the denominator, or a book of names could never be read.
    distinct = {
        str(token.get("lemma") or "")
        for tokens in (loaded.get("tokens") or {}).values()
        for token in tokens
        if token.get("pos") not in NOT_VOCABULARY
    }
    distinct.discard("")
    out = sorted(distinct)

    try:
        write_atomic(cached, json.dumps({"stamp": stamp, "lemmas": out}, ensure_ascii=False))
    except OSError:
        # A read-only or full disk costs the cache, not the answer.
        pass
    return out


def against(folder: Path, marked: dict[str, int]) -> Coverage | None:
    """This text measured against what one person has marked.

    `marked` maps a dictionary form to how well they know it. None when the text carries
    no word-level annotation — the caller shows what it showed before rather than a zero,
    because "0% known" and "not measured" are very different claims to make about a book.
    """
    words = lemmas(folder)
    if not words:
        return None
    known = sum(1 for lemma in words if marked.get(lemma) == KNOWN)
    fresh = sum(1 for lemma in words if lemma not in marked)
    return Coverage(known=known / len(words), fresh=fresh, total=len(words))
