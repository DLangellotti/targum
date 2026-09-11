"""How far into Hebrew one person is, computed where the chat can read it.

The ulpan ladder lives in `render/assets/charts.js`: the weights a known word carries by
how common it is, and the vocabulary each rung is usually reckoned to want. It was drawn
in the browser and nowhere else, because until the chat nothing on the server had any
reason to ask. The chat runs on the server, so this is the same ladder in Python — and
`tests/fixtures/level.json` holds one set of words with the answer both must give, so
the two cannot drift apart without a test saying so.

What this is not: a placement. `design.md` §6 says engagement counts real things and
never levels, and the progress page prints "A guide, not a placement" over the ladder.
A `Level` carries the rung so the chat can grade the Hebrew it writes; what the chat may
*say* is the counts, and `describe()` tells it so in as many words.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .accounts import Store

#: The status a word reaches when it is finished with; the learning ladder (1-3) is
#: deliberately not counted. Same value as `coverage.KNOWN` and `charts.js`.
KNOWN = 9

#: A name or a number, marked while reading. Knowing that אחשורוש is a king is not
#: knowing a word of Hebrew, so nothing that counts vocabulary counts these.
NOT_VOCABULARY = frozenset({"name", "number"})

#: Rarer words count for more, because a word further out is evidence of the commoner
#: ones behind it. Centred near one so the total still reads as a vocabulary size —
#: the reasoning is written out beside the same table in `charts.js`.
BAND_WEIGHT: dict[str, float] = {
    "easy": 0.8,
    "fairly easy": 1.0,
    "moderate": 1.3,
    "hard": 1.7,
    "very hard": 2.2,
    "extremely hard": 2.8,
}
#: A word from a language with no frequency data behind it, counted at face value.
UNRATED_WEIGHT = 1.0


@dataclass(frozen=True)
class Rung:
    at: int
    letter: str
    name: str


#: The ladder, with the vocabulary each rung is usually reckoned to want. Estimates, and
#: round on purpose: the figures behind ulpan levels vary between ulpanim.
ULPAN: tuple[Rung, ...] = (
    Rung(250, "א", "aleph"),
    Rung(900, "א+", "aleph plus"),
    Rung(1800, "ב", "bet"),
    Rung(3000, "ב+", "bet plus"),
    Rung(4500, "ג", "gimel"),
    Rung(6500, "ד", "dalet"),
    Rung(9000, "ה", "hey"),
    Rung(12000, "ו", "vav"),
)


def reach(words: Iterable[tuple[int | None, str]]) -> tuple[float, int]:
    """The known words, weighted by how common each is: (weighted total, how many)."""
    total = 0.0
    counted = 0
    for status, band in words:
        if band in NOT_VOCABULARY or status != KNOWN:
            continue
        counted += 1
        total += BAND_WEIGHT.get(band, UNRATED_WEIGHT)
    return total, counted


def standing(weighted: float) -> tuple[Rung | None, Rung | None]:
    """Which rung that reaches, and the one after it."""
    here: Rung | None = None
    following: Rung | None = None
    for rung in ULPAN:
        if weighted >= rung.at:
            here = rung
        elif following is None:
            following = rung
    return here, following


def streaks(days: Iterable[str], today: date) -> tuple[int, int]:
    """The current run of reading days and the longest ever, from `YYYY-MM-DD` strings.

    A day is the reader's own calendar day, written by the browser at its local midnight.
    The current streak counts back from today, or from yesterday — a reader who has not
    opened targum yet this morning has not broken anything.
    """
    have: set[date] = set()
    for day in days:
        try:
            have.add(date.fromisoformat(day))
        except ValueError:
            continue
    if not have:
        return 0, 0
    longest = 0
    run = 0
    previous: date | None = None
    for when in sorted(have):
        run = run + 1 if previous is not None and when - previous == timedelta(days=1) else 1
        longest = max(longest, run)
        previous = when
    start = today if today in have else today - timedelta(days=1)
    current = 0
    while start in have:
        current += 1
        start -= timedelta(days=1)
    return current, longest


@dataclass(frozen=True)
class Level:
    """What one reader's ledger says, as numbers and not as a verdict."""

    language: str
    known: int
    learning: int
    weighted: float
    here: Rung | None
    next: Rung | None
    days: int
    streak: int
    longest: int
    sections: int
    texts: int

    def state(self) -> dict[str, Any]:
        return {
            "language": self.language,
            "known": self.known,
            "learning": self.learning,
            "days": self.days,
            "streak": self.streak,
            "longest": self.longest,
            "sections": self.sections,
            "texts": self.texts,
            # The rung is here for grading and for the page's own ledger line. It is
            # labelled for what it is so nobody downstream prints it as a score.
            "ladder": {
                "reach": self.here.name if self.here else "",
                "next": self.next.name if self.next else "",
                "note": "A guide, not a placement.",
            },
        }


EMPTY = Level("he", 0, 0, 0.0, None, ULPAN[0], 0, 0, 0, 0, 0)


def snapshot(
    store: Store, person_id: int | None, language: str, today: date | None = None
) -> Level:
    """One person's level, read from the account. Empty for nobody."""
    if person_id is None:
        return EMPTY
    words = store.words_with_bands(person_id, language)
    weighted, known = reach((status, band) for _, status, band, _ in words)
    learning = sum(
        1 for _, status, band, _ in words if status in (1, 2, 3) and band not in NOT_VOCABULARY
    )
    here, following = standing(weighted)
    activity = store.activity(person_id)
    days = [str(day) for day in activity.get("days") or []]
    current, longest = streaks(days, today or date.today())
    return Level(
        language=language,
        known=known,
        learning=learning,
        weighted=weighted,
        here=here,
        next=following,
        days=len(days),
        streak=current,
        longest=longest,
        sections=int(activity.get("sections") or 0),
        texts=int(activity.get("texts") or 0),
    )


def describe(level: Level) -> str:
    """The ledger as a paragraph the chat's system prompt can carry.

    Real counts, the way §6 asks. The rung is given so the Hebrew the chat writes can be
    graded to it, and the same sentence says it is never to be quoted as a placement.
    """
    ladder = (
        f"Weighted by how common each word is, their known words reach about the "
        f"'{level.here.name}' rung of the ulpan ladder"
        if level.here
        else "Weighted by how common each word is, their known words have not yet reached "
        "the first rung of the ulpan ladder"
    )
    if level.next:
        ladder += f"; the next rung, '{level.next.name}', wants about {level.next.at:,} words"
    return (
        f"The reader is learning Hebrew. Their ledger: {level.known:,} words marked known, "
        f"{level.learning:,} still being learned; {level.days:,} days read, a current streak "
        f"of {level.streak:,} (longest {level.longest:,}); {level.sections:,} sections "
        f"finished across {level.texts:,} texts. {ladder}. Use the rung to grade any Hebrew "
        "you write for them. Never tell the reader they are 'at a level' or name the rung "
        "as a placement — it is a guide from self-reported words, not a placement and not a "
        "test. Quote the real counts instead."
    )


# -- how much of a text a reader already has (targum-internal#244) -------------------

#: The one-letter clitics Hebrew writes onto the front of a word — and, that, in, to,
#: from, which, as, the — tried off a page's token before it is looked up, so a known
#: word still counts when it arrives with a prefix. One or two of them, never more.
PREFIXES = "והבלמשכ"

#: Under this many Hebrew tokens a share is a guess, and `known_share` says "not
#: measured" rather than a number.
MEASURABLE = 20

_WORD = re.compile(r"[\u05d0-\u05ea][\u05b0-\u05c7\u05d0-\u05ea\u05f3\u05f4\"']*")
_POINTS = re.compile(r"[\u0591-\u05c7]")


def _bare(word: str) -> str:
    return _POINTS.sub("", word).strip("\"'\u05f3\u05f4")


def _forms_of(token: str) -> list[str]:
    """The token, and the token with one and then two prefix letters taken off, where
    what is left is still a word of two letters or more."""
    out = [token]
    if len(token) > 2 and token[0] in PREFIXES:
        out.append(token[1:])
        if len(token) > 3 and token[1] in PREFIXES:
            out.append(token[2:])
    return out


def known_share(text: str, forms: set[str]) -> float | None:
    """The share of a text's Hebrew tokens the reader already has, cheaply.

    A token counts as known when it, or it less a prefix or two, is among `forms` — the
    reader's known words as surface forms and dictionary forms, plus the commonest
    words of the language (`hebrew.common_words`), all bare of their points. No
    lemmatizer: that costs about a minute a text on the box (memory 2026-09-03), and
    this is asked at quote time on a page nobody has built yet. It undercounts an
    inflected known word whose form the ledger never saw; the exact figure is the
    coverage a built text is measured with (`coverage.against`). None below
    `MEASURABLE` tokens: "not measured" and "0% known" are different claims.
    """
    tokens = [_bare(t) for t in _WORD.findall(text)]
    tokens = [t for t in tokens if t]
    if len(tokens) < MEASURABLE:
        return None
    known = sum(1 for token in tokens if any(form in forms for form in _forms_of(token)))
    return known / len(tokens)


def words_in_ten(share: float | None) -> str:
    """The share said the way the page says it: a count, never a percentage or a level.
    "you know about 7 words in 10 here." Empty where it was not measured."""
    if share is None:
        return ""
    tenths = max(0, min(10, round(share * 10)))
    if tenths >= 10:
        return "You know nearly every word here."
    if tenths <= 0:
        return "You know almost none of the words here yet."
    return f"You know about {tenths} {'word' if tenths == 1 else 'words'} in 10 here."


#: What share of a library text's words a learner at a rung is reckoned to look up
#: before it stops being a first read: the ceiling `search_library` applies when the
#: model names none, by the rung the ledger reaches. A starting table, round on purpose.
LOOKED_UP_CEILING: tuple[tuple[int, int], ...] = ((250, 40), (900, 30), (1800, 25), (3000, 20))


def ceiling_for(level: Level) -> int | None:
    """The default `max_looked_up_percent` for this reader, or None past the table."""
    for words, ceiling in LOOKED_UP_CEILING:
        if level.weighted < words:
            return ceiling
    return None
