"""A word's pointing put right on the page, from a hand-kept table (targum-internal#689).

Kan's video about cola says קולה forty times, and the reader pointed every one קוֹלָהּ,
"her voice". DICTA's menaked reads the spelling as קול with a feminine suffix, and its
joint model agrees, so neither the pointing nor the lemma can tell the drink from the
voice. Nothing pointed it at all before: `menukad`'s lexicon is a spelling normaliser for
scenes, and a lexicon entry would be wrong anyway, because קוֹלָהּ is real Hebrew and
only the words around it can pick cola.

So the table (`pointing_overrides.json`) names a bare spelling, the pointing it should
have, and the words that say so: a cue (בקבוק, פחית, קוקה, a form of שתה) within three
words of it and inside its clause, and nothing that says the other reading. A guard is a
word of the voice's (את before it, שמע, נתנה, הרימה, רעד, and the speech verbs
אמרה, ענתה, קראה, שאלה, המשיכה in their common forms), or a definite adjective
straight after a bare word (קולה הצעיר is "her young voice"; cola would be הקולה הצעיר).
Where the entry says `whole_text`, one sense holds for a text: once one occurrence is
cued and none is guarded, every occurrence in the text takes the pointing, because a
text about cola that also speaks of a woman's voice under the same spelling is not one
anybody has found. A text with one guarded occurrence gets only its cued ones.

**Where it runs.** On the page, when a reader is built or rebuilt (`render`), and on a
printed copy. The Vocalization on disk keeps what the diacritizer said; nothing here
renames an annotator, moves `SCHEMA_VERSION` or runs a model, so a plain `targum
rebuild`, which spends nothing, takes it to every page already on a shelf.

**What it never touches.** A segment its edition pointed: the source's pointing is what
the reader shows (`vocalize`), so only a segment a model pointed (`Vocalization.machine`)
is read. A word whose letters differ from the entry's after its prefixes, so a letter is
never changed. Where an annotation is given, a word whose lemma is not one the entry
names (`lemmas`), so a word the annotator read as something else entirely is left to it.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import cache
from importlib import resources
from typing import TYPE_CHECKING

from .base import MARKS, strip_nikkud

if TYPE_CHECKING:
    from ..models import Annotation, SegmentedDocument, Vocalization

#: How many words either side a cue or a guard may stand.
WINDOW = 3
#: Letters a word may carry in front of a cue: and, the, in, as, to. Not מ or ש, which
#: would turn משתה, "a feast", into שתה.
CUE_PREFIXES = "ובהכל"
#: A guard is read more freely: a missed guard costs a wrong vowel, a missed cue nothing.
GUARD_PREFIXES = "ובהכלמש"
#: Adjectives' article that is not one: הכי, "the most", follows an indefinite noun.
NOT_ARTICLE = frozenset({"הכי"})
DAGESH = "ּ"

_MARK_CLASS = "".join(chr(cp) for cp in sorted(MARKS))
#: A word in a pointed or bare line: Hebrew letters, each with the marks after it.
_WORD = re.compile(f"(?:[א-ת][{_MARK_CLASS}]*)+")
#: What may stand between two words of one clause: spaces, a maqaf or a hyphen, and the
#: direction marks a subtitle file carries.
_SAME_CLAUSE = re.compile("[\\s־\\-‎‏‪-‮⁦-⁩]*")


@dataclass(frozen=True)
class Entry:
    bare: str
    pointed: str
    prefixes: str
    lemmas: frozenset[str]
    cues: frozenset[str]
    guards: frozenset[str]
    whole_text: bool


@cache
def table() -> tuple[Entry, ...]:
    """The table in the repository, checked: an entry's pointing must spell its word."""
    raw = json.loads(
        resources.files("targum.vocalize").joinpath("pointing_overrides.json").read_text("utf-8")
    )
    out = []
    for item in raw["entries"]:
        entry = Entry(
            bare=item["bare"],
            pointed=item["pointed"],
            prefixes=item.get("prefixes", ""),
            lemmas=frozenset(item.get("lemmas", ())),
            cues=frozenset(item.get("cues", ())),
            guards=frozenset(item.get("guards", ())),
            whole_text=bool(item.get("whole_text")),
        )
        if strip_nikkud(entry.pointed)[0] != entry.bare:
            raise ValueError(f"{entry.pointed} does not spell {entry.bare}")
        out.append(entry)
    return tuple(out)


@dataclass(frozen=True)
class _Word:
    start: int
    end: int
    bare: str
    #: Whether the next word is in the same clause, and whether the one before is.
    joined_after: bool


def _words(text: str) -> list[_Word]:
    found = list(_WORD.finditer(text))
    out = []
    for at, match in enumerate(found):
        after = found[at + 1].start() if at + 1 < len(found) else None
        joined = after is not None and bool(_SAME_CLAUSE.fullmatch(text, match.end(), after))
        out.append(_Word(match.start(), match.end(), strip_nikkud(match.group())[0], joined))
    return out


def _is(word: str, wanted: frozenset[str], prefixes: str) -> bool:
    if word in wanted:
        return True
    for cut in range(1, 3):
        if len(word) > cut and all(letter in prefixes for letter in word[:cut]):
            if word[cut:] in wanted:
                return True
    return False


def _prefix(word: str, entry: Entry) -> str | None:
    """The letters in front of the entry's word, or None where this is not it."""
    if not word.endswith(entry.bare):
        return None
    front = word[: len(word) - len(entry.bare)]
    if len(front) > 3 or any(letter not in entry.prefixes for letter in front):
        return None
    return front


def _clause(words: list[_Word], at: int) -> list[str]:
    """The words within `WINDOW` of `at` and in its clause, itself left out."""
    near = []
    j = at
    while j > 0 and at - j < WINDOW and words[j - 1].joined_after:
        j -= 1
        near.append(words[j].bare)
    j = at
    while j + 1 < len(words) and j - at < WINDOW and words[j].joined_after:
        j += 1
        near.append(words[j].bare)
    return near


def _reading(words: list[_Word], at: int, entry: Entry, front: str) -> str:
    """ "cue", "guard" or "" for the occurrence at `at`."""
    near = _clause(words, at)
    definite = "ה" in front
    guards = entry.guards - {"את"} if definite else entry.guards
    if any(_is(word, guards, GUARD_PREFIXES) for word in near):
        return "guard"
    if (
        not definite
        and words[at].joined_after
        and words[at + 1].bare.startswith("ה")
        and words[at + 1].bare not in NOT_ARTICLE
        and len(words[at + 1].bare) > 2
    ):
        return "guard"
    if any(_is(word, entry.cues, CUE_PREFIXES) for word in near):
        return "cue"
    return ""


def _repointed(word: str, entry: Entry, front: str) -> str:
    """The pointed word with the entry's pointing on its own letters and the prefixes'
    left as they were, the dagesh an article puts in the first letter included."""
    letters = [at for at, char in enumerate(word) if ord(char) not in MARKS] + [len(word)]
    head = word[: letters[len(front)]]
    had = word[letters[len(front)] + 1 : letters[len(front) + 1]]
    new = entry.pointed
    if front and DAGESH in had and DAGESH not in new[1 : 1 + len(had)]:
        new = new[0] + DAGESH + new[1:]
    return head + new


def _lemma_at(annotation: Annotation | None, segment_id: str, offset: int) -> str | None:
    """The lemma of the token over an offset in the segment's text (its word's last
    letter, so a prefix cut off as a token of its own is not the one asked), None where
    nothing says."""
    if annotation is None:
        return None
    for token in annotation.tokens.get(segment_id, ()):
        if token.start <= offset < token.end:
            return token.lemma
    return None


def overridden(
    vocalization: Vocalization | None,
    segmented: SegmentedDocument,
    annotation: Annotation | None = None,
) -> Vocalization | None:
    """The vocalization with the table's words pointed where their cue says so; the same
    object where nothing changes."""
    if vocalization is None or not vocalization.machine:
        return vocalization
    if not vocalization.language.startswith("he"):
        return vocalization
    machine = set(vocalization.machine)
    texts = {segment.id: segment.text for segment in segmented.segments}
    segments = dict(vocalization.segments)
    changed = False
    for entry in table():
        # Every occurrence in the text, read off the segment's own line, so a line with
        # no pointing still counts towards the text's one sense.
        found: list[tuple[str, int, str, str]] = []
        for segment in segmented.segments:
            words = _words(segment.text)
            for at, word in enumerate(words):
                front = _prefix(word.bare, entry)
                if front is None:
                    continue
                lemma = _lemma_at(annotation, segment.id, word.end - 1)
                if lemma is not None and entry.lemmas and lemma not in entry.lemmas:
                    continue
                found.append((segment.id, at, front, _reading(words, at, entry, front)))
        said = {reading for *_, reading in found}
        if "cue" not in said:
            continue
        whole = entry.whole_text and "guard" not in said
        wanted: dict[str, set[int]] = {}
        for segment_id, at, _, reading in found:
            if reading == "cue" or (whole and reading == ""):
                wanted.setdefault(segment_id, set()).add(at)
        for segment_id, places in wanted.items():
            line = segments.get(segment_id)
            if segment_id not in machine or line is None:
                continue
            own = texts.get(segment_id, "")
            if strip_nikkud(own)[0] != own:
                # The edition pointed some of this line: its pointing is what shows.
                continue
            words = _words(line)
            if [word.bare for word in words] != [word.bare for word in _words(own)]:
                continue
            pieces, last = [], 0
            for at in sorted(places):
                word = words[at]
                front = _prefix(word.bare, entry)
                if front is None:
                    continue
                fixed = _repointed(line[word.start : word.end], entry, front)
                pieces += [line[last : word.start], fixed]
                last = word.end
            fresh = "".join(pieces) + line[last:]
            if fresh != line and strip_nikkud(fresh)[0] == strip_nikkud(line)[0]:
                segments[segment_id] = fresh
                changed = True
    if not changed:
        return vocalization
    return vocalization.model_copy(update={"segments": segments})
