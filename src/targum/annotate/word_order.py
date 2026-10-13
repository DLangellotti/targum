"""A Russian subject that comes after its verb: Russian's word-order hard spot.

design.md §12, "Subjects after their verb, on a lens" (2026-10-13), and the research it
rests on (targum-internal, research/hard-spots-2026-10-11): Russian says who did what with
endings, so it is free to put the subject last — *Книгу написал Толстой*, the book was
written by Tolstoy — and an English reader takes the first noun for the subject and reads
the sentence backwards. Feedback does not fix it, so the research gives it a lens: the
subject lit where it stands after its verb.

**Read off the stored grammar, not the parse.** Every Russian token already keeps its
case, number, gender and person (`annotate/russian.py`), and the case is settled by the
parse where the ending alone cannot say it (`russian.settle`: a subject is nominative). A
nominative noun or pronoun after a finite verb it agrees with, in the same clause, with no
agreeing nominative before the verb, is that verb's subject come late. Nothing is read
again, so a text annotated before this shows it without a rename.

**Why not the parse itself.** spaCy's parse is not stored for Russian, and storing it
would rename the annotator and re-read every Russian text. Scored first, on all 8,906
SynTagRus dev sentences on 2026-10-13: the parse's own subjects-after-the-verb were right
0.848 of the time and found 0.848 of them; this rule is right 0.951 of the time and finds
0.708. A lens that lights a word that is not the subject teaches the wrong sentence, so
precision is the number that matters, and the rule wins it without a re-read.

**What it misses**, measured: a subject the tagger put in another case (the genitive of
*не хватало денег*, a nominative read as accusative), the second of two coordinated
subjects, and a verb in another clause. It says nothing it is not sure of.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from ..models import Token

#: What can be a subject: a noun, a name, a pronoun, in the nominative.
NOMINAL = frozenset({"NOUN", "PROPN", "PRON"})

#: What ends a clause between two words: a comma, a dash, a bracket, a quotation mark, the
#: end of a sentence. A conjunction does too (`_clauses`).
BREAK = re.compile(r"[,;:()—–\-\"«»?!.…]")
JOINING = frozenset({"CCONJ", "SCONJ"})


@dataclass(frozen=True)
class Inverted:
    """One verb, and its subject standing after it, by token index."""

    verb: int
    subject: int


def feature(feats: str | None, name: str) -> str:
    for part in (feats or "").split("|"):
        key, _, value = part.partition("=")
        if key == name:
            return value
    return ""


def finite(token: Token) -> bool:
    """A verb that can have a subject: a finite form, or a short participle (*был
    обвинён*, *посвящены*), which is a participle with no case."""
    if token.pos != "VERB":
        return False
    form = feature(token.feats, "VerbForm")
    return form == "Fin" or (form == "Part" and not feature(token.feats, "Case"))


def nominative(token: Token) -> bool:
    return token.pos in NOMINAL and feature(token.feats, "Case") == "Nom"


def agrees(verb: Token, subject: Token) -> bool:
    """Whether a verb's number, person and, in the past, gender allow this subject. A
    feature either word leaves out allows anything."""
    said, other = verb.feats or "", subject.feats or ""
    number = feature(said, "Number")
    if number and feature(other, "Number") and number != feature(other, "Number"):
        return False
    person = feature(said, "Person")
    if person and subject.pos in {"NOUN", "PROPN"} and person != "3":
        return False
    if person and feature(other, "Person") and person != feature(other, "Person"):
        return False
    gender = feature(said, "Gender")
    return not (
        gender
        and number == "Sing"
        and feature(other, "Gender")
        and gender != feature(other, "Gender")
    )


def _clauses(text: str, tokens: Sequence[Token]) -> list[int]:
    """Which clause each token is in, counted from 0. Punctuation is never a token, so it
    is read off the text between two of them."""
    out: list[int] = []
    clause = 0
    for at, token in enumerate(tokens):
        if at and (BREAK.search(text[tokens[at - 1].end : token.start]) or token.pos in JOINING):
            clause += 1
        out.append(clause)
    return out


def inverted(text: str, tokens: Sequence[Token]) -> list[Inverted]:
    """Every subject in one segment that comes after its verb. `text` is the segment's own
    text, which the tokens' offsets count in."""
    clause = _clauses(text, tokens)
    out: list[Inverted] = []
    for at, token in enumerate(tokens):
        if not nominative(token) or (at and tokens[at - 1].pos == "ADP"):
            continue
        verbs = [
            before
            for before in range(at)
            if clause[before] == clause[at]
            and finite(tokens[before])
            and agrees(tokens[before], token)
        ]
        if not verbs:
            continue
        verb = verbs[-1]
        # A subject before the verb is the subject: this word is something else.
        if any(
            clause[before] == clause[at]
            and nominative(tokens[before])
            and agrees(tokens[verb], tokens[before])
            for before in range(verb)
        ):
            continue
        # Only the first nominative after the verb: the next is a second subject or an
        # apposition, and the rule cannot tell which.
        if any(nominative(tokens[between]) for between in range(verb + 1, at)):
            continue
        out.append(Inverted(verb, at))
    return out
