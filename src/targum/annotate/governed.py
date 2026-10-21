"""Which preposition a Hebrew verb takes, in this line: Hebrew's fourth hard spot.

design.md §12, "A badge is a promise, checked" (2026-10-12), and the research it rests on
(targum-internal, research/hard-spots-2026-10-11): governed prepositions and *et* are
what a learner gets wrong longest, and the one spot feedback barely moves. חיכה takes
ל־, פחד takes מ־, דיבר takes עם, and a definite object takes את. Nothing in an English
speaker's grammar predicts which, so the reader has to see it, verb by verb.

Nothing here is new computation. DICTA's syntax head already runs on every call and every
token keeps it (`Token.syntax`): a word's head, its relation, and the tags of what is
glued to its front. A verb's argument is a word hanging off it as `obj`, `iobj` or `obl`;
its preposition is a word of its own hanging off the argument as `case` (על, עם, את), a
letter on the argument's front tagged `ADP` (לאוטובוס, מכלבים), or the argument itself
where the pronoun is written onto the preposition (לו, אותו). That is the
whole rule, and it is read off the stored annotation, so a text annotated before this
existed says it without being read again.

**What is measured, and what is not.** The IAHLT treebanks mark every case-marked
argument `obl` and do not separate a governed preposition (חיכה ל־) from an adjunct
(הגיע בבוקר), so a floor can only hold this to which preposition marks which verb's
argument, and that is what the card shows: the preposition this verb has here, not a
claim that it is the one the verb always takes. The core set is the seven a learner
meets on every page; the long tail (למען, בשל, לאחר) is meaning, not government.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from ..models import Token
from ..vocalize.base import strip_nikkud

#: The prepositions this spot is about, as the treebank and DICTA spell their lemma.
#: מן is מ־ written out.
CORE = frozenset({"ל", "ב", "מ", "על", "עם", "אל", "את"})
SPELLED = {"מן": "מ"}

#: How an argument hangs off its verb. `obl:tmod` and the rest of `obl`'s subtypes are
#: time and manner, which no preposition governs.
ARGUMENT = frozenset({"obj", "iobj", "obl", "obl:arg"})

#: The letters that can be a preposition glued to the front of a word.
PREFIX_PREPOSITIONS = "בלמ"


@dataclass(frozen=True)
class Governed:
    """One verb, one argument, and the preposition between them, by token index."""

    verb: int
    argument: int
    preposition: str
    #: The index of the preposition's own token, or None where it is a letter on the
    #: argument's front.
    marker: int | None = None


def preposition_of(word: str) -> str:
    """A preposition's lemma in the spelling `CORE` uses, marks and all removed."""
    bare, _ = strip_nikkud(word or "")
    bare = bare.strip()
    return SPELLED.get(bare, bare)


def _glued(token: Token) -> str | None:
    """The preposition written onto the front of a word, if DICTA tagged one there."""
    syntax = token.syntax
    if syntax is None or "ADP" not in syntax.prefixes or syntax.lead <= 0:
        return None
    bare, _ = strip_nikkud(token.surface)
    for letter in reversed(bare[: syntax.lead]):
        if letter in PREFIX_PREPOSITIONS:
            return letter
    return None


def governed(tokens: Sequence[Token]) -> list[Governed]:
    """Every verb–preposition–argument in one segment's tokens, in the core set.

    Indices are positions in `tokens`, as `Syntax.head` counts them. A head that points
    outside the list, or at something other than a verb, is skipped rather than guessed.
    """
    markers: dict[int, int] = {}
    for at, token in enumerate(tokens):
        syntax = token.syntax
        if syntax is None or token.pos != "ADP" or not syntax.relation.startswith("case"):
            continue
        if 0 <= syntax.head < len(tokens):
            markers.setdefault(syntax.head, at)
    out: list[Governed] = []
    for at, token in enumerate(tokens):
        syntax = token.syntax
        if syntax is None or syntax.relation not in ARGUMENT:
            continue
        verb = syntax.head
        if not 0 <= verb < len(tokens) or tokens[verb].pos != "VERB":
            continue
        marker = markers.get(at)
        if marker is not None:
            preposition = preposition_of(tokens[marker].lemma or tokens[marker].surface)
        elif token.pos == "ADP":
            # The preposition with its pronoun on the end — לו, אותו, ממנו — is the
            # argument itself, and filed under the preposition (`dicta.CARRIED`).
            preposition = preposition_of(token.lemma)
        else:
            preposition = _glued(token) or ""
        if preposition in CORE:
            out.append(Governed(verb, at, preposition, marker))
    return out


def takes(tokens: Sequence[Token]) -> dict[int, list[Governed]]:
    """`governed`, grouped by verb, for the card."""
    out: dict[int, list[Governed]] = {}
    for pair in governed(tokens):
        out.setdefault(pair.verb, []).append(pair)
    return out
