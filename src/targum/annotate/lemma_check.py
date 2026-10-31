"""A lemma checked against the word it is the lemma of, at page-build and count time.

נשתיק, "we will silence", reached a card as התקין, "install", with the root ת־ק־ן and
"All forms of התקין" under it (David, 2026-10-31). DICTA has no השתיק in its vocabulary:
alone it returns `[BLANK]` or a near neighbour (השחית, שיתק, מתקין), and in one sentence
it returned התקין. The annotator's guard (`dicta.unrelated`, grammar/7) refuses a lemma
whose strong letters are not in the word, and counts every nun as optional because a
nun assimilates — so התקין's ת־ק־נ became ת־ק, which נשתיק spells, and the lemma went
through. Everything on the card follows the lemma: the meaning, the root, the family, the
conjugation link and the word the reader's count files it under.

The annotator's own fix waits for a rename that is happening anyway (targum-internal#590);
an annotator rename re-reads every text, about two hours of DICTA on the box. So this runs
where `verb_roots` runs: on what the annotation already says, every time a page is built
or a text's words are counted. Nothing here renames an annotator, moves `SCHEMA_VERSION`
or runs a model, and the annotation on disk keeps what the annotator said.

**The check.** The same letters-in-order test as `dicta.unrelated`, with a nun let go
only where Hebrew lets it go: first in the root (נפל → יפול, נתן → תן), or last before a
suffix's ת (נתן → נתתי). A nun in the middle or at the end of anything else stays a
letter the word has to spell. A participle's מ left on the lemma is let go as before.

**What a refused lemma becomes.** For a verb, the CC0 paradigm table's verb, where the
word as written (under its prefixes) is a form of exactly one verb there: נשתיק is a form
of הִשְׁתִּיק and of nothing else, so the card says השתיק, with the table's root and binyan.
Anywhere else the surface, as the annotator does when it refuses a lemma itself: a gap
on the card rather than the wrong word's meaning, said with confidence.

Measured on 2026-10-31 over the laptop's 212 Hebrew texts annotated by grammar/8: 116 of
89,035 verb tokens, 132 of 151,154 nouns and 21 of 26,797 adjectives carried a lemma
this refuses; 54 of the verbs take the table's verb, and every one read by hand was wrong
before (נבעלה under נאנס, נרכוש under נקנה, נפדה under נקנה).

Only DICTA's annotations (`dicta/…`): a lemma from the hand tagging of scripture is an
editor's, and this never overrules one.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, NamedTuple

from .dicta import GUARDED, SUPPLETIVE, _in_order, _strong
from .hebrew import FINALS

if TYPE_CHECKING:
    from ..models import Annotation, Token

#: The version of what this module answers. A change to the check or to what a refused
#: lemma becomes is a new number, carried by every count that reads it.
VERSION = 1

#: The annotator this checks: DICTA, and nothing that put a hand tagging in front of it.
DICTA = "dicta/"

_POINTS = re.compile("[֑-ׇ]")


class Mend(NamedTuple):
    """What a refused lemma becomes: the lemma, and the root and binyan that go with it
    ("" where there is none to give)."""

    lemma: str
    root: str
    binyan: str


def applies(annotator: str, language: str) -> bool:
    """Whether an annotation by `annotator` in `language` is checked here."""
    return annotator.startswith(DICTA) and language.split("-")[0].lower() == "he"


def _then(letters: str, word: str, after: str) -> bool:
    """Whether `letters` are in `word` in order with `after` straight after the last."""
    at = 0
    for char in letters:
        at = word.find(char, at) + 1
        if not at:
            return False
    return word[at : at + 1] == after


def refused(lemma: str, base: str) -> bool:
    """Whether `lemma` cannot be the lemma of `base`, the word under its prefixes."""
    if not lemma or " " in lemma or lemma in SUPPLETIVE:
        return False
    if not base or '"' in base or "'" in base:
        return False
    strong = _strong(lemma)
    word = base.translate(FINALS)
    tries = {strong}
    if strong[:1] in "נמ":
        # A first nun that assimilated (יפול, תן), or a participle's מ on the lemma.
        tries.add(strong[1:])
    if any(len(letters) < 2 for letters in tries):
        return False
    if any(_in_order(letters, word) for letters in tries):
        return False
    # A last nun taken into a suffix's ת: נָתַתִּי is נתן's.
    return not (len(strong) > 2 and strong[-1] == "נ" and _then(strong[:-1], word, "ת"))


def _table_verb(base: str) -> tuple[str, str] | None:
    """The one verb of the CC0 table `base` is a form of, as (bare lemma, binyan)."""
    from .paradigms import bare, table

    book = table()
    found = book.by_form.get(base) or ()
    lemmas = {bare(book.verbs[lid].lemma) for lid in found if lid in book.verbs}
    if len(lemmas) != 1:
        return None
    binyans = {book.binyan_of(lid) for lid in found}
    binyan = binyans.pop() if len(binyans) == 1 else None
    return lemmas.pop(), binyan or ""


def checked(lemma: str, surface: str, lead: int, pos: str | None) -> Mend | None:
    """What a token's lemma becomes, or None where it stands.

    `lead` is how many letters of `surface` DICTA cut off as prefixes (`Syntax.lead`).
    """
    if pos not in GUARDED:
        return None
    word = _POINTS.sub("", surface or "")
    base = word[lead:] if 0 < lead < len(word) else word
    lemma = lemma or ""
    # A gap already: the annotator gave the word itself.
    if lemma in (word, word.lower(), base):
        return None
    if not refused(lemma, base):
        return None
    if pos == "VERB":
        found = _table_verb(base)
        if found is not None:
            from .verb_roots import root_for

            verb, binyan = found
            return Mend(verb, root_for(verb, None, "VERB"), binyan)
    return Mend(word.lower(), "", "")


def mend_token(token: Token) -> Token:
    """The token with its lemma checked; the same object where nothing changes."""
    lead = token.syntax.lead if token.syntax is not None else 0
    mend = checked(token.lemma, token.surface, lead, token.pos)
    if mend is None:
        return token
    return token.model_copy(
        update={
            "lemma": mend.lemma,
            "root": mend.root or None,
            "binyan": mend.binyan or None,
            # Each of these was the refused word's, not this one's.
            "headword": None,
            "lexeme": None,
            "word_register": None,
        }
    )


def mended(annotation: Annotation) -> Annotation:
    """The annotation with every lemma checked; the same object where nothing changes,
    and where the annotation is not DICTA's Hebrew."""
    if not applies(annotation.annotator, annotation.language):
        return annotation
    changed = False
    tokens: dict[str, list[Token]] = {}
    for segment_id, run in annotation.tokens.items():
        out = [mend_token(token) for token in run]
        changed = changed or any(new is not old for new, old in zip(out, run, strict=True))
        tokens[segment_id] = out
    if not changed:
        return annotation
    return annotation.model_copy(update={"tokens": tokens})


def mend_row(row: dict[str, Any]) -> dict[str, Any]:
    """A token as `annotation.json` stores it, with its lemma checked: for the counts,
    which read the file rather than the model. The same dict where nothing changes."""
    syntax = row.get("syntax") or {}
    mend = checked(
        str(row.get("lemma") or ""),
        str(row.get("surface") or ""),
        int(syntax.get("lead") or 0),
        row.get("pos"),
    )
    if mend is None:
        return row
    return row | {"lemma": mend.lemma, "root": mend.root or None, "binyan": mend.binyan or None}
