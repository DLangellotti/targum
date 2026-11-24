"""Which Hebrew word of its verse each Onkelos word renders (targum-internal G3; design.md
§12, "The card draws Aramaic's Hebrew counterpart, from an alignment", 2026-10-25).

**Rules and counts, no model.** Onkelos renders the Torah almost word for word, 1.036
Aramaic words to a Hebrew one, so the verse pairs themselves are enough to learn which
word goes with which. `scripts/count_onkelos_alignment.py` reads the 5,846 verse pairs
(Onkelos from Sefaria, the Hebrew from Open Scriptures) and learns, both ways, how likely
each Aramaic spelling is to render each Hebrew one: IBM Model 1 with a pull toward the
diagonal, eight rounds, counted on the disk in seconds. Nothing is bought and nothing is
written in Aramaic. The table it keeps, `onkelos_lexicon.json`, is the pairs that carry
weight either way.

**A link is drawn only where both directions agree**: the Hebrew word this Aramaic word
most likely renders, and the Aramaic word that Hebrew word most likely becomes, are each
other, and each direction gives it at least `MIN_SHARE` of the verse. Everything else is
left unlinked, which is what the card is for: a counterpart guessed is a card that lies,
and a blank line costs the reader nothing. The poems and the renderings of God (מימרא,
קדם יי) are paraphrase, and come out mostly blank by this rule without being named.

**Not on the card yet.** design.md's bar is a 300-verse gold read by hand by ling-arc and a
floor in `evals/floors.json`; until `scripts/eval_onkelos_align.py` has that gold to
score against, nothing reads this module but the scripts.
"""

from __future__ import annotations

import json
import math
import re
from functools import cache
from pathlib import Path

from .aramaic import key

NAME = "onkelos-align/1"

LEXICON = Path(__file__).resolve().with_name("onkelos_lexicon.json")

#: How much of its verse a link must hold, each way, to be drawn.
MIN_SHARE = 0.5

#: How strongly a word is expected near its own place in the verse. Onkelos keeps the
#: Hebrew order almost everywhere, so a link far off the diagonal is doubted.
PULL = 3.0

#: What a word is learned and looked up as: its letters, finals folded, with the ו of
#: "and" off the front, which both languages write the same way and which says nothing
#: about which word this is.
_WORDS = re.compile(r"[א-ת֑-ׇ]+")


def norm(word: str) -> str:
    folded = key(word)
    return folded[1:] if len(folded) > 2 and folded[0] == "ו" else folded


def words(text: str) -> list[str]:
    """The words of a verse, pointed or not, in order: every run of letters and points."""
    return _WORDS.findall(text or "")


@cache
def lexicon() -> tuple[dict[str, dict[str, float]], dict[str, dict[str, float]]]:
    """(Aramaic → Hebrew → share, Hebrew → Aramaic → share), or empty where the table has
    not been counted."""
    if not LEXICON.is_file():
        return {}, {}
    raw = json.loads(LEXICON.read_text(encoding="utf-8"))
    return raw["renders"], raw["rendered"]


def _best(
    table: dict[str, dict[str, float]], source: list[str], target: list[str]
) -> list[tuple[int | None, float]]:
    """For each source word, the target word it most likely goes with, and its share."""
    out: list[tuple[int | None, float]] = []
    n, m = len(source), len(target)
    for i, word in enumerate(source):
        row = table.get(word, {})
        scores = [
            row.get(other, 0.0) * math.exp(-PULL * abs(i / max(n, 1) - j / max(m, 1)))
            for j, other in enumerate(target)
        ]
        total = sum(scores) + row.get("", 0.0) * 0.2
        if not m or total <= 0:
            out.append((None, 0.0))
            continue
        j = max(range(m), key=scores.__getitem__)
        out.append((j, scores[j] / total))
    return out


def align(onkelos: list[str], hebrew: list[str]) -> list[int | None]:
    """For each Onkelos word, the index of the Hebrew word of the same verse it renders,
    or None where the two directions do not agree or either is unsure."""
    renders, rendered = lexicon()
    aramaic_words = [norm(word) for word in onkelos]
    hebrew_words = [norm(word) for word in hebrew]
    forward = _best(renders, aramaic_words, hebrew_words)
    backward = _best(rendered, hebrew_words, aramaic_words)
    out: list[int | None] = []
    for i, (j, share) in enumerate(forward):
        if j is None or share < MIN_SHARE:
            out.append(None)
            continue
        back, back_share = backward[j]
        out.append(j if back == i and back_share >= MIN_SHARE else None)
    return out
