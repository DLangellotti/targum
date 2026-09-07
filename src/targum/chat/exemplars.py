"""Sentences a Hebrew speaker wrote, inside the reader's words (targum-internal#218).

Three fixes in a row fought Hebrew that was translated from English: the model thinks of
an English sentence and renders it, and the record fills with calques. An instruction
("write as a Hebrew speaker would say it") moved it some of the way. A real sentence is a
stronger nudge than an instruction, and a real sentence that uses a word the reader saved
last week is a stronger bring-back than one the model invents to order.

**Where the sentences come from.** Tatoeba, under CC BY 2.0 FR: the Hebrew sentences
written by contributors who declare Hebrew native, each with a linked English sentence,
lemmatized once with the build lemmatizer so the lemmas mean what the ledger's lemmas
mean. `scripts/tatoeba_pool.py` builds the file; this module only reads it. The file is
data and lives beside `sources.json` — named by `TARGUM_EXEMPLARS`, else in the home or
`/etc/targum` — and a box with no such file has no exemplars and says nothing false.

**What is picked.** For one turn, a handful of sentences whose content lemmas all fall
inside the reader's known words plus the common floor, so every exemplar is something
they could already read, with first claim on sentences that carry a word they saved
lately. Originals — sentences written in Hebrew rather than translated into it — come
before translations. Retrieval is local; no model call, no spend, nothing a reader fetches.

**What the model is told.** That these are idiom, word order and register to prefer, and
never lines to repeat. They ride unpointed, as Tatoeba writes them; the contract still
asks the model to point every word of its own.

**Attribution.** Every row keeps its contributors' usernames, and `LICENSING.md` credits
Tatoeba. Nothing trains on them (targum-internal#161).
"""

from __future__ import annotations

import json
import os
import random
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..annotate.base import NOT_VOCABULARY

#: How many sentences ride in one turn. Six is a paragraph the model reads, at a cost of
#: a couple of hundred tokens after the cache breakpoint.
PICK = 6

#: How many of the picked may be claimed by a word the reader saved lately, so the block
#: is never all bring-backs and never none when one fits.
LATELY_SHARE = 3


@dataclass(frozen=True)
class Exemplar:
    id: int
    hebrew: str
    english: str
    #: Content lemmas only — names and numbers are not vocabulary, on the ledger or here.
    lemmas: frozenset[str]
    by: str
    english_by: str = ""
    original: bool = False

    @property
    def credit(self) -> str:
        return f"tatoeba.org/sentences/show/{self.id} by {self.by}"


def pool_path() -> Path | None:
    """Where the pool is. A path named in the environment is the path, found or not —
    the same rule `sources_path` and `catalogue_path` keep, for the same reason."""
    named = os.environ.get("TARGUM_EXEMPLARS", "").strip()
    if named:
        return Path(named) if Path(named).is_file() else None
    for path in (
        Path.home() / ".targum" / "exemplars.jsonl",
        Path("/etc/targum/exemplars.jsonl"),
    ):
        if path.is_file():
            return path
    return None


def _row(raw: dict[str, Any]) -> Exemplar | None:
    words = raw.get("words")
    hebrew = str(raw.get("he") or "").strip()
    if not words or not hebrew:
        # Not lemmatized yet: the pool is built in tranches, and a row without its
        # lemmas cannot be matched against anybody's words.
        return None
    lemmas = frozenset(
        str(lemma) for lemma, pos in words if lemma and str(pos) not in NOT_VOCABULARY
    )
    return Exemplar(
        id=int(raw.get("id") or 0),
        hebrew=hebrew,
        english=str(raw.get("en") or "").strip(),
        lemmas=lemmas,
        by=str(raw.get("by") or ""),
        english_by=str(raw.get("en_by") or ""),
        original=bool(raw.get("original", False)),
    )


def load(path: Path | None = None) -> list[Exemplar]:
    """Every lemmatized row of the pool, in file order. No file, no exemplars."""
    where = path if path is not None else pool_path()
    if where is None or not where.is_file():
        return []
    out: list[Exemplar] = []
    with where.open(encoding="utf-8") as lines:
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError:
                continue
            row = _row(raw) if isinstance(raw, dict) else None
            if row is not None:
                out.append(row)
    return out


def pick(
    pool: list[Exemplar],
    allowed: set[str],
    lately: Iterable[str] = (),
    *,
    count: int = PICK,
    seed: int = 0,
) -> list[Exemplar]:
    """A turn's exemplars: inside `allowed`, bring-backs first, originals before
    translations, and otherwise drawn by `seed` so one conversation sees different
    sentences from turn to turn and the same turn sees the same ones twice.

    A sentence with no content lemmas at all (a bare "yes") is skipped — it teaches
    nothing about the reader's words.
    """
    if count <= 0 or not pool:
        return []
    saved = set(lately)
    # A word saved lately is on the ledger but usually not yet known, and the whole
    # point of a bring-back is to meet it again: it is inside the reader's words here.
    within = set(allowed) | saved
    inside = [row for row in pool if row.lemmas and row.lemmas <= within]
    if not inside:
        return []
    draw = random.Random(seed)
    draw.shuffle(inside)
    # Originals before translations, bring-backs before either. The shuffle above is
    # what breaks ties, and a stable sort keeps it.
    inside.sort(key=lambda row: (not (row.lemmas & saved), not row.original))
    carrying = [row for row in inside if row.lemmas & saved][:LATELY_SHARE]
    rest = [row for row in inside if row not in carrying]
    return (carrying + rest)[:count]


def block(picked: list[Exemplar]) -> str:
    """The per-turn block, for the ledger's side of the cache breakpoint."""
    if not picked:
        return ""
    lines = [
        f"Sentences a Hebrew speaker wrote, inside the reader's words ({len(picked)}). They "
        "are the idiom, the word order and the register to write in — not lines to repeat, "
        "and not a list to show. They are unpointed; point every word of your own as the "
        "contract asks."
    ]
    for row in picked:
        lines.append(f"{row.hebrew} = {row.english}" if row.english else row.hebrew)
    return "\n".join(lines)


def turn_seed(chat_id: str, n: int) -> int:
    """A seed that is the same for one turn every time and different for the next."""
    import zlib

    return zlib.crc32(f"{chat_id}:{n}".encode())
