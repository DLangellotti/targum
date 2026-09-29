"""The questions a shelf search asks of every candidate, asked of Jev instead (#319).

Every shelf so far was filled by a research run — the Italian search, the Russian run,
the Khan shortlist, the LibriVox survey — and each one asked the same few questions of
every candidate: is this prose, is it an original or a translation, is it the language it
claims, what is it about, would a learner get through it, and does its licence line clear.
Five of those are a Choice or a Noul over what a candidate says about itself; this module
writes them down once so a sweep can ask them of any catalogue at a fraction of a cent a
row.

**The sixth is not asked.** A licence verdict is never probabilistic (targum-internal#309):
`licensing.verdict` reads the licence line as it reads it everywhere else, and a candidate
whose line it does not know goes to a person. So the licence is not in the state either —
nothing the model says can lean on it.

**Only what a candidate says before anybody accepts it goes in.** A catalogue row also
carries a blurb, an English title, tags and a kind, all written after the row was taken;
a screen that saw them would be reading the answer. `Candidate` keeps the title, the
author, the source, the claimed language, the publisher's credit line and a few opening
sentences where there are any, and nothing else.

**Jev ranks a queue; a person confirms.** `passes` is the triage rule the sweep is scored
on, not a decision to build, and nothing here spends or fetches — `jev.ask` is handed
what this builds, by the script that owns the sweep (`scripts/screen_shelf.py`), the
shape `screen.py` set.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

from .catalogue import Tag
from .licensing import Standing, verdict
from .translate.prompts import language_name

#: How many opening sentences go in the state. Enough to tell a story from a table of
#: contents, and far inside the ~32k-token budget with five questions beside it.
SAMPLE_LINES = 3

#: A Noul at or above this is a yes.
YES = 0.5

#: What each subject is, said to the model the way `catalogue.Tag` says it to a reader.
#: A test holds the keys to `Tag`, so a new door cannot be left out of the question.
SUBJECTS: dict[str, str] = {
    Tag.tanakh: "The Hebrew Bible, or a translation or retelling of it.",
    Tag.judaica: "Jewish religious writing other than the Bible: liturgy, Mishnah, "
    "Talmud, rabbinic law and commentary.",
    Tag.journalism: "News reporting, written to be read the week it happened.",
    Tag.sport: "Sport and match reports.",
    Tag.science: "How things work: physics, chemistry, biology, maths, the sky.",
    Tag.history: "What happened in the past, and writing about it.",
    Tag.archaeology: "Digs, finds and what they settle.",
    Tag.technology: "Machines, software, the internet.",
    Tag.health: "Bodies, medicine, what to do about them.",
    Tag.food: "Cooking and eating.",
    Tag.travel: "Places, and going to them.",
    Tag.music: "Songs, musicians, the making of music.",
    Tag.art: "Pictures, buildings, and looking at them.",
    Tag.politics: "Government, elections, political argument.",
    Tag.business: "Work, money, what things cost.",
    Tag.philosophy: "Ideas, argued.",
    Tag.language: "The language itself: its words, grammar and how it is said, as a "
    "lesson or an explanation.",
}

#: The subject option for a text that is none of the above — a novel, a folk tale.
NO_SUBJECT = "none"

#: Notes on a row's published English that say the English came first, so the row is a
#: translation of it. Read off the catalogue's own wording, which is the only place the
#: owner wrote the answer down: "The English original", "The Italian is a translation of
#: this, not the other way round", "Made from the Judeo-Arabic original rather than from
#: the Hebrew beside it".
_FROM = re.compile(
    r"translated from|is a translation of this|english original|the original\b"
    r"|came to it through|original rather than|not a translation but",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Candidate:
    """What a candidate says about itself, before anybody has accepted it."""

    id: str
    title: str
    author: str
    source: str
    language: str
    credit: str = ""
    licence: str = ""
    sample: tuple[str, ...] = ()


def from_row(raw: dict[str, Any], sample: Iterable[str] = ()) -> Candidate:
    """A catalogue row reduced to what it said before it was taken. The blurb, English
    title, tags and kind are left behind on purpose: they were written after."""
    return Candidate(
        id=str(raw.get("id") or ""),
        title=str(raw.get("title") or ""),
        author=str(raw.get("author") or ""),
        source=str(raw.get("source") or ""),
        language=str(raw.get("language") or ""),
        credit=str(raw.get("credit") or ""),
        licence=str(raw.get("licence") or ""),
        sample=tuple(line for line in sample if line.strip())[:SAMPLE_LINES],
    )


def state(candidate: Candidate) -> dict[str, str]:
    """The state sent. No licence, and no id: neither is evidence of anything the model
    is asked, and the id of a catalogue row is a label."""
    out = {
        "title": candidate.title,
        "author": candidate.author,
        "source": candidate.source,
        "claimed_language": language_name(candidate.language),
    }
    if candidate.credit and candidate.credit != candidate.author:
        out["credit"] = candidate.credit
    if candidate.sample:
        out["opening"] = " ".join(candidate.sample)
    return out


def questions(candidate: Candidate) -> dict[str, dict[str, Any]]:
    """The issue's questions, one request's worth. `prose` is asked only where there is an
    opening to read: a title cannot say whether the text behind it is a table of
    contents."""
    name = language_name(candidate.language)
    asked: dict[str, dict[str, Any]] = {
        "language": {
            "type": "noul",
            "instructions": f"Is this text written in {name}?",
            "criteria": {
                "true": f"The title and any opening are in {name}.",
                "false": f"They are in another language or a dialect of it, or mostly "
                f"quote another language, and only claim to be {name}.",
            },
        },
        "origin": {
            "type": "choice",
            "instructions": f"Was this {name} text first written in {name}, or is it a "
            "translation into it from another language?",
            "criteria": {
                "original": f"First written in {name}.",
                "translation": f"Translated into {name} from another language, directly "
                "or through a third.",
            },
        },
        "subject": {
            "type": "choice",
            "instructions": "Which one subject is this text about?",
            "criteria": {
                **SUBJECTS,
                NO_SUBJECT: "None of these: a story, a novel, a poem "
                "or anything else not filed by subject.",
            },
        },
        "learner": {
            "type": "noul",
            "instructions": f"Would an adult who has studied {name} for about a year get "
            "through this text with a dictionary beside them?",
        },
    }
    if candidate.sample:
        asked["prose"] = {
            "type": "noul",
            "instructions": "Is the opening running text somebody reads for itself?",
            "criteria": {
                "true": "A story, article, talk, dialogue, poem, law or scripture: "
                "sentences meant to be read.",
                "false": "A table of contents, a preface or editor's note, a list, "
                "a licence or navigation notice, or scanning debris.",
            },
        }
    return asked


@dataclass(frozen=True)
class Screened:
    """What came back for one candidate, plus the licence read in code."""

    id: str
    language: float | None
    origin: str
    origin_confidence: float
    subject: str
    learner: float | None
    prose: float | None
    licence: Standing
    derivatives: bool

    @property
    def passes(self) -> bool:
        """The triage rule the sweep is scored on: in its language, prose where that
        was asked, and a licence line `licensing.py` knows that allows a reader. The
        learner question is not in it — the owner shelves Dante — and neither is the
        subject, which files a text rather than admitting it."""
        return (
            self.language is not None
            and self.language >= YES
            and (self.prose is None or self.prose >= YES)
            and self.licence is not Standing.unknown
            and self.derivatives
        )


def _noul(answer: Any) -> float | None:
    try:
        return float(answer["noul"])
    except (KeyError, TypeError, ValueError):
        return None


def read(candidate: Candidate, answers: dict[str, Any]) -> Screened:
    """One response's answers as a `Screened`. A missing or malformed answer is None or
    empty, never a default that reads as a verdict."""
    origin = answers.get("origin") or {}
    subject = answers.get("subject") or {}
    call = verdict(candidate.licence)
    return Screened(
        id=candidate.id,
        language=_noul(answers.get("language")),
        origin=str(origin.get("choice") or ""),
        origin_confidence=float(origin.get("confidence") or 0.0),
        subject=str(subject.get("choice") or ""),
        learner=_noul(answers.get("learner")),
        prose=_noul(answers.get("prose")) if "prose" in answers else None,
        licence=call.standing,
        derivatives=call.derivatives,
    )


# -- what the owner wrote down, and scoring against it ------------------------------------


def said_translation(raw: dict[str, Any]) -> bool | None:
    """Whether the catalogue says this row is a translation: True where a note on its
    published English says the English came first, False where it has an English and no
    note says so (the English was made from it), None where it has no English at all and
    so the owner wrote nothing down."""
    notes = [str(one.get("note") or "") for one in raw.get("translations") or []]
    if not notes:
        return None
    return any(_FROM.search(note) for note in notes)


@dataclass(frozen=True)
class Agreement:
    """How often the screen said what the owner said, over the rows where the owner
    said anything."""

    right: int
    n: int

    @property
    def rate(self) -> float | None:
        return self.right / self.n if self.n else None


def agreement(pairs: Iterable[tuple[object, object]]) -> Agreement:
    """Pairs of (the owner's label, the screen's answer), a label of None skipped."""
    right = n = 0
    for gold, got in pairs:
        if gold is None:
            continue
        n += 1
        right += gold == got
    return Agreement(right, n)


@dataclass(frozen=True)
class Confusion:
    """Accept against the owner's accept, counted. Precision is None where no row was
    rejected, because a set with no rejects cannot say how many the screen let through."""

    true_pos: int
    false_pos: int
    false_neg: int
    true_neg: int

    @property
    def recall(self) -> float | None:
        accepted = self.true_pos + self.false_neg
        return self.true_pos / accepted if accepted else None

    @property
    def precision(self) -> float | None:
        if not self.true_neg + self.false_pos:
            return None
        passed = self.true_pos + self.false_pos
        return self.true_pos / passed if passed else None


def confusion(labelled: Sequence[tuple[bool, bool]]) -> Confusion:
    """(the owner accepted it, the screen passed it), for every row."""
    tp = sum(1 for owner, got in labelled if owner and got)
    fp = sum(1 for owner, got in labelled if not owner and got)
    fn = sum(1 for owner, got in labelled if owner and not got)
    tn = sum(1 for owner, got in labelled if not owner and not got)
    return Confusion(tp, fp, fn, tn)
