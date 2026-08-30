"""What an issue has to pass before anybody may read it.

Public on purpose, unlike the rest of the generation half. This holds the licence guard
and the band gate — the two things in the feature that stop it doing harm — and an
n-gram overlap check gives away no moat whatever. Kept private it would live where CI
can never run it, which is the worst possible home for the code that enforces a licence
boundary.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass

from ..annotate.base import NOT_VOCABULARY
from .models import FACTS_ONLY, LEVELS, Level, Story

#: How many words in a row count as somebody else's sentence rather than the same facts
#: told twice. Five is short enough to catch a lifted clause and long enough that two
#: writers reporting one event do not collide on it: a shared name, a number and a verb
#: run to three or four.
LIFT = 5

#: Letters and digits, not letters alone. A lifted clause is often mostly a figure — a
#: score, a budget, a death toll — and dropping digits let five words containing one
#: past the check by comparing only the four ordinary words around it.
#:
#: It counts toward telling two stories apart as well, though not by much: two headlines
#: that share their subject and their verb and differ only in a number still measure
#: similar, and no threshold that separates those keeps the pairs worth merging. The
#: date and the link do that work.
_WORD = re.compile(r"[^\W_]+", re.UNICODE)


def words_of(text: str) -> list[str]:
    """Words, with Hebrew points and the marks that separate them taken off.

    Nikkud would otherwise let a lifted sentence through by being pointed differently
    from the headline it came out of, which is a difference no reader can see.
    """
    bare = "".join(ch for ch in unicodedata.normalize("NFD", text) if not unicodedata.combining(ch))
    return [word.casefold() for word in _WORD.findall(bare)]


def grams(text: str, size: int = LIFT) -> set[tuple[str, ...]]:
    found = words_of(text)
    return {tuple(found[i : i + size]) for i in range(len(found) - size + 1)}


@dataclass(frozen=True)
class Lift:
    """A run of words that survived out of a source that only gave facts."""

    story: str
    phrase: str

    def __str__(self) -> str:
        return f"{self.phrase!r} (from {self.story!r})"


#: How many named entities a verbless run needs before it counts as the facts rather
#: than as anybody's sentence about them.
ENOUGH_NAMES = 2


def lifted(
    composed: str,
    sources: list[Story],
    size: int = LIFT,
    names: frozenset[str] = frozenset(),
    verbs: frozenset[str] = frozenset(),
) -> list[Lift]:
    """Every run of `size` words the issue shares with a facts-only source.

    The prompt is told not to reproduce their wording. This is what checks. A prompt is
    an instruction and this is a measurement, and only one of them can fail a build.

    `names` and `verbs` are what stop it firing on the facts. A real issue was blocked on
    "באוגוסט הרוג בקפריסין הצפות בסוריה": a month, a fatality, Cyprus, floods, Syria.
    There is no other way in Hebrew to say a death in Cyprus and flooding in Syria, and
    nobody owns a place name — they own the prose around it.

    What marks that run out is not how many names are in it but that it has no verb, no
    function word and no syntax at all. It is a caption of events. A sentence somebody
    composed has a verb in it, so a verbless run carrying two or more named entities is
    let through and everything else is not. Pass what a `Gauge` found in the composed
    text.
    """
    written = grams(composed, size)
    if not written:
        return []
    found: list[Lift] = []
    for story in sources:
        if story.tier < FACTS_ONLY:
            # Tier 1 named a licence that lets its text be used, and the issue credits
            # it at the foot. Overlap there is permitted rather than overlooked.
            continue
        for gram in grams(story.headline, size) | grams(story.excerpt, size):
            if gram not in written:
                continue
            verbless = not any(word in verbs for word in gram)
            entities = sum(1 for word in gram if word in names)
            if verbless and entities >= ENOUGH_NAMES:
                continue
            found.append(Lift(story=story.headline, phrase=" ".join(gram)))
    return found


def no_lifted_wording(composed: str, sources: list[Story], size: int = LIFT) -> None:
    """Raise if any of somebody else's sentence survived into the issue."""
    from ..errors import TargumError

    found = lifted(composed, sources, size)
    if not found:
        return
    raise TargumError(
        f"{len(found)} run(s) of a source's own wording survived into the issue.",
        "A facts-only source gives facts. Rewrite these: "
        + "; ".join(str(one) for one in found[:3]),
    )


@dataclass(frozen=True)
class Gauge:
    """Both halves of what a level is checked against.

    Two numbers because one of them was not enough. `difficulty` is the library's own
    ruler and it cannot separate the first two levels: writing for a small vocabulary
    means explaining who everybody is, and an explanation is more words rather than
    commoner ones — so on the first real issue the easy edition measured 15% and the
    simplified one 14%, the wrong way round. What separated them was sentence length:
    6.7 words against 11.4. It is free, too, because the segmenter has already done the
    work by the time the words are counted.
    """

    difficulty: int
    sentence: float
    #: The proper nouns and numbers in this prose, and separately the verbs, by surface
    #: form. Free here, because the annotation that counts the words has already tagged
    #: them, and both are needed by the lift check: see `lifted`.
    names: frozenset[str] = frozenset()
    verbs: frozenset[str] = frozenset()


def gauge(markdown: str, language: str = "he") -> Gauge:
    """Measure this prose, both ways, off one segmentation.

    Stanza and wordfreq and nothing else — local, free, and the same steps a build runs,
    so the number here is the number the entry will carry rather than an approximation.
    """
    from ..annotate import Annotator
    from ..annotate.difficulty import hard_share
    from ..ingest.base import blocks_from_paragraphs, build_document
    from ..models import BlockKind
    from ..segment import StanzaSegmenter, segment_document

    paragraphs = [
        (BlockKind.paragraph, None, line.strip())
        for line in markdown.split("\n\n")
        # The section headings and the item headlines, both of which are `#` now. They
        # are the same shape every week, so counting them drags every issue's numbers
        # toward every other issue's — and a headline is not a sentence, so it would
        # flatten the mean that does most of the work here.
        if line.strip() and not line.strip().startswith("#")
    ]
    if not paragraphs:
        return Gauge(difficulty=0, sentence=0.0)

    document = build_document(
        "weekly:measured",
        blocks_from_paragraphs(paragraphs),
        ingester="weekly/measure",
        language=language,
    )
    segmented = segment_document(document, StanzaSegmenter())
    sentences = segmented.segments
    words = sum(len(segment.text.split()) for segment in sentences)
    annotation = Annotator().annotate(segmented)

    def surfaces(wanted: Callable[[str | None], bool]) -> frozenset[str]:
        found = {
            token.surface.casefold()
            for tokens in annotation.tokens.values()
            for token in tokens
            if wanted(token.pos)
        }
        return frozenset(word for surface in found for word in words_of(surface))

    return Gauge(
        difficulty=hard_share(annotation, language),
        sentence=round(words / len(sentences), 1) if sentences else 0.0,
        names=surfaces(lambda pos: pos in NOT_VOCABULARY),
        verbs=surfaces(lambda pos: pos in {"VERB", "AUX"}),
    )


def measure(markdown: str, language: str = "he") -> int:
    """Just the word ruler, which is the number the library's own column carries."""
    return gauge(markdown, language).difficulty


#: Phrases that say a machine wrote this, and the em-dash that says it loudest.
#:
#: Checked rather than merely asked for, on the evidence of the licence rule: the model
#: was told plainly not to reuse a source's wording and did it anyway on all three
#: levels of the first real issue. An instruction is an instruction; this is a
#: measurement, and only one of them can fail a build.
#:
#: The list is from Hebrew Wikipedia's guide to spotting AI-written articles. The
#: em-dash is first because it is the clearest: it is not part of ordinary Hebrew
#: punctuation, so its presence is close to proof on its own.
TELLS: dict[str, str] = {
    "—": "an em-dash, which is not Hebrew punctuation",
    "–": "an en-dash used as punctuation",
    "לא רק": '"לא רק... אלא גם"',
    "אין מדובר רק": '"אין מדובר רק ב... אלא ב"',
    "חשוב לציין": '"חשוב לציין"',
    "ראוי להדגיש": '"ראוי להדגיש"',
    "יש לציין": '"יש לציין"',
    "יצוין כי": '"יצוין כי"',
    "לסיכום": '"לסיכום"',
    "יש הסבורים": '"יש הסבורים", attribution with nobody behind it',
    "על פי דיווחים": '"על פי דיווחים", attribution with nobody behind it',
    "גורמים מעריכים": '"גורמים מעריכים", attribution with nobody behind it',
    "מדגיש את החשיבות": '"מדגיש את החשיבות"',
    "ממחיש את המשמעות": '"ממחיש את המשמעות"',
    "מבליט את תרומתו": '"מבליט את תרומתו"',
}


def tells(text: str) -> list[str]:
    """Every mark of machine writing in this prose, named as a person would name it."""
    return sorted({why for mark, why in TELLS.items() if mark in text})


def tell_note(found: list[str]) -> str:
    """What to tell a rewrite about prose that reads as written by a machine."""
    if not found:
        return ""
    return (
        "This reads as machine-written. It contains " + "; ".join(found) + ". "
        "Take them out and write the sentence the way somebody on a news desk would."
    )


def lift_note(found: list[Lift]) -> str:
    """What to tell a rewrite about the wording it borrowed.

    Named phrases rather than a scolding: the model has to know which words to replace,
    and "be more careful" is not something it can act on.
    """
    if not found:
        return ""
    phrases = "; ".join(f'"{one.phrase}"' for one in found[:6])
    return (
        "These runs of words came from a source that gave you facts and nothing else, "
        f"so they may not appear: {phrases}. Report the same events in your own Hebrew."
    )


def in_band(level: Level, measured: Gauge) -> bool:
    spec = LEVELS[level]
    low, high = spec.band
    shortest, longest = spec.sentence
    return low <= measured.difficulty <= high and shortest <= measured.sentence <= longest


def missed(level: Level, measured: Gauge) -> str:
    """Why a level missed, in the words the rewrite is told it in.

    Names whichever half went wrong and says what to do about that half rather than
    about difficulty in general: a model asked to make something "easier" reaches for
    commoner words when the problem was the sentences, and the other way round.
    """
    spec = LEVELS[level]
    low, high = spec.band
    shortest, longest = spec.sentence
    parts: list[str] = []
    if not low <= measured.difficulty <= high:
        way = "commoner" if measured.difficulty > high else "less common"
        parts.append(
            f"The vocabulary came out at {measured.difficulty}%, and {spec.name} wants "
            f"{low}–{high}%. Use {way} words."
        )
    if not shortest <= measured.sentence <= longest:
        way = "Shorter" if measured.sentence > longest else "Longer"
        parts.append(
            f"Sentences averaged {measured.sentence} words, and {spec.name} wants "
            f"{shortest:g}–{longest:g}. {way} sentences."
        )
    return " ".join(parts)
