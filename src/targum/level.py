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
from collections.abc import Iterable, Set
from dataclasses import dataclass
from datetime import date, timedelta
from math import ceil
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
    #: The CEFR level this rung is reckoned to correspond to, where it has one.
    cefr: str = ""


#: The ladder, with the vocabulary each rung is usually reckoned to want. Estimates, and
#: round on purpose: the figures behind ulpan levels vary between ulpanim.
#:
#: Each rung's CEFR equivalent since 2026-09-13. CEFR-aligned Hebrew teaching treats the
#: six ulpan levels as roughly A1 to C2 (Scripta Judaica Cracoviensia 17, 2019, pp.
#: 43–48); the two plus rungs take the level below and, for bet, the CEFR's own A2+.
ULPAN: tuple[Rung, ...] = (
    Rung(250, "א", "aleph", "A1"),
    Rung(900, "א+", "aleph plus", "A1"),
    Rung(1800, "ב", "bet", "A2"),
    Rung(3000, "ב+", "bet plus", "A2+"),
    Rung(4500, "ג", "gimel", "B1"),
    Rung(6500, "ד", "dalet", "B2"),
    Rung(9000, "ה", "hey", "C1"),
    Rung(12000, "ו", "vav", "C2"),
)

#: The CEFR levels, by how many of the language's commonest words a reader knows.
#:
#: The research ties CEFR levels to recognition of a language's 5,000 most frequent
#: lemmas (Meara and Milton's XLex), and Milton and Alexiou (2009), tabulated in Milton
#: (2010), *EUROSLA Monographs* 1, Table 6, give the mean for learners of French at each
#: level in Spain and in Greece. A level starts halfway between its mean and the one below
#: it; A1 starts where aleph does. **Measured for French.** No study covers Italian or
#: Russian, so both borrow these figures until one does.
#:
#: "The commonest 5,000" is read off the bands a word already carries: the 5,000th form
#: in wordfreq sits at Zipf 4.17 in French, 4.30 in Russian and 4.23 in Italian, and the
#: "moderate" band ends at 4.1 — so a known word in the three commonest bands is, near
#: enough, a known word among them (`COMMON_BANDS`). Measured 2026-09-13.
CEFR: tuple[Rung, ...] = (
    Rung(250, "A1", "A1"),
    Rung(1350, "A2", "A2"),
    Rung(2000, "B1", "B1"),
    Rung(2400, "B2", "B2"),
    Rung(2750, "C1", "C1"),
    Rung(3300, "C2", "C2"),
)

#: The bands inside a language's commonest five thousand or so words. See `CEFR`.
COMMON_BANDS = frozenset({"easy", "fairly easy", "moderate"})


@dataclass(frozen=True)
class Ladder:
    """A language's ladder: what it is called, its rungs, and what reaches them."""

    title: str
    rungs: tuple[Rung, ...]
    #: `weighted` for the ulpan ladder (`reach`); `common` for the CEFR (`common`).
    measure: str


ULPAN_LADDER = Ladder("Ulpan level", ULPAN, "weighted")
CEFR_LADDER = Ladder("CEFR level", CEFR, "common")

#: Which languages have a ladder. Yiddish and Aramaic have none: there is no frequency
#: table to measure a vocabulary in either against.
LADDERS: dict[str, Ladder] = {
    "he": ULPAN_LADDER,
    "fr": CEFR_LADDER,
    "ru": CEFR_LADDER,
    "it": CEFR_LADDER,
}


def ladder_for(language: str) -> Ladder | None:
    return LADDERS.get((language or "").split("-")[0].lower())


def common(words: Iterable[tuple[int | None, str]]) -> int:
    """How many known words sit among the language's commonest: the CEFR's measure."""
    return sum(
        1
        for status, band in words
        if status == KNOWN and band not in NOT_VOCABULARY and band in COMMON_BANDS
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


def standing(weighted: float, rungs: tuple[Rung, ...] = ULPAN) -> tuple[Rung | None, Rung | None]:
    """Which rung that reaches, and the one after it."""
    here: Rung | None = None
    following: Rung | None = None
    for rung in rungs:
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
    #: What the language's ladder is called — "Ulpan level", "CEFR level" — or "" where
    #: it has none.
    ladder: str = "Ulpan level"
    #: Known words among the commonest, for a ladder that counts those.
    common: int = 0
    #: How the reader wants to be addressed in Hebrew: 'm', 'f', or '' for not said.
    address: str = ""
    #: The rung they named on arrival, by its arrival id ("bet-plus"), or "". A seed: see
    #: `seed`. Deliberately absent from `state()` — no page is handed it to print.
    declared: str = ""

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
                "name": self.ladder,
                "reach": self.here.name if self.here else "",
                "next": self.next.name if self.next else "",
                "cefr": self.here.cefr if self.here else "",
                "note": "A guide, not a placement.",
            },
        }


EMPTY = Level("he", 0, 0, 0.0, None, ULPAN[0], 0, 0, 0, 0, 0)


def seed(level: Level) -> Rung | None:
    """The rung a reader *said*, while nothing about them has been measured.

    targum-internal#306, decided on 2026-09-19 after being decided the other way twice
    (design.md §12, "The arrival is two questions…"). Every other level here is counted
    off words the reader marked. This one is declared, and what keeps that small is this
    function's one rule: **a measured rung outvotes it.** Once `here` exists — by reading,
    or by the claim grid a minute after the first text — this answers None and the
    declared rung is not consulted. Hebrew only: the arrival asks over the ulpan ladder.
    """
    if level.here is not None or not level.declared:
        return None
    if (level.language or "he").split("-")[0].lower() != "he":
        return None
    name = level.declared.replace("-", " ")
    for rung in ULPAN:
        if rung.name == name:
            return rung
    return None


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
    among = common((status, band) for _, status, band, _ in words)
    ladder = ladder_for(language)
    if ladder is None:
        here, following = None, None
    else:
        here, following = standing(
            weighted if ladder.measure == "weighted" else among, ladder.rungs
        )
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
        ladder=ladder.title if ladder else "",
        common=among,
        address=store.address(person_id) if hasattr(store, "address") else "",
        declared=store.declared(person_id) if hasattr(store, "declared") else "",
    )


def describe(level: Level) -> str:
    """The ledger as a paragraph the chat's system prompt can carry.

    Real counts, the way §6 asks. The rung is given so what the chat writes can be graded
    to it, and the same sentence says it is never to be quoted as a placement.
    """
    from .translate.prompts import language_name

    code = (level.language or "he").split("-")[0].lower()
    ladder = _ladder_sentence(level, ladder_for(code))
    # The longest run and never the current one (design.md §12, "The streak is the
    # longest one, and the current one is refused"): a model handed a current streak says
    # it back, and a connector's host says it to a reader on a page we do not draw.
    return (
        f"The reader is learning {language_name(code)}. Their ledger: {level.known:,} words "
        f"marked known, {level.learning:,} still being learned; {level.days:,} days read, "
        f"their longest run of days {level.longest:,}; "
        f"{level.sections:,} sections finished across {level.texts:,} texts. {ladder}"
        "Never tell the reader they are 'at a level' or name the rung as a placement — it is "
        "a guide from self-reported words, not a placement and not a test. Quote the real "
        "counts instead."
        # Hebrew's "you" is gendered and the others' here are not written that way; an
        # Italian conversation told how to say אַתָּה was told it was a Hebrew one.
        f"{_address_sentence(level.address) if code == 'he' else ''}"
    )


def _address_sentence(address: str) -> str:
    """How to say "you" to this reader in Hebrew, and how to point their "I" (2026-09-14).

    A recast once turned a man's unpointed רוצה into רוֹצָה and labelled it corrected; the
    same reply then called him אַתָּה. Nothing had told the model either way."""
    if address == "m":
        return (
            " Address the reader as a man (אַתָּה, רוֹצֶה, שֶׁלְּךָ), and point their own "
            "first-person present in the masculine."
        )
    if address == "f":
        return (
            " Address the reader as a woman (אַתְּ, רוֹצָה, שֶׁלָּךְ), and point their own "
            "first-person present in the feminine."
        )
    return (
        " The reader has not said how to be addressed in Hebrew: use forms that do not "
        "choose a gender, and keep the gender of their own words in a recast."
    )


def _ladder_sentence(level: Level, ladder: Ladder | None) -> str:
    if ladder is None:
        return "There is no level ladder for this language. "
    if ladder.measure == "weighted":
        said = (
            f"Weighted by how common each word is, their known words reach about the "
            f"'{level.here.name}' rung of the ulpan ladder (about {level.here.cefr} on the "
            "CEFR)"
            if level.here
            else "Weighted by how common each word is, their known words have not yet "
            "reached the first rung of the ulpan ladder"
        )
        said_rung = seed(level)
        if said_rung is not None:
            # Nothing is measured yet, so what they said on arrival stands in. It is
            # for grading what is written for them and for nothing else.
            return (
                f"{said}, so there is no measured rung yet. When they arrived they said "
                f"they were at about the '{said_rung.name}' rung (about {said_rung.cefr} on "
                "the CEFR): grade anything you write for them in Hebrew to that until their "
                "own marked words say otherwise, and never quote it back to them. "
            )
        if level.next:
            said += f"; the next rung, '{level.next.name}', wants about {level.next.at:,} words"
        return f"{said}. Use the rung to grade anything you write for them in Hebrew. "
    said = (
        f"{level.common:,} of their known words are among the language's commonest, which "
        f"is about {level.here.name} on the CEFR"
        if level.here
        else f"{level.common:,} of their known words are among the language's commonest, "
        "short of A1 on the CEFR"
    )
    if level.next:
        said += f"; {level.next.name} wants about {level.next.at:,}"
    return f"{said}. A reader may name a CEFR level for themselves; take it as a guide. "


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


#: The two letters ktiv male writes that ktiv haser leaves out. Stripping the points off
#: a pointed text gives the haser spelling (ארועים), while the common words and most
#: forms a reader marks are male (אירועים): targum-internal#349.
MATRES = "וי"


def _skeleton(word: str) -> str:
    """The word with every vav and yod between its first and last letter taken out. The
    first and last stay: a vav or yod there is a letter of the word or an ending, and
    haser does not drop it."""
    if len(word) <= 2:
        return word
    return word[0] + "".join(ch for ch in word[1:-1] if ch not in MATRES) + word[-1]


def _haser_of(token: str, form: str) -> bool:
    """Whether `token` is `form` with one or more of its inner vavs and yods left out,
    and nothing else changed. Letters only ever come out of the known form, never go in:
    a token with a letter the form lacks is a different word."""
    if len(token) >= len(form) or token[:1] != form[:1] or token[-1:] != form[-1:]:
        return False
    inner, whole = token[1:-1], form[1:-1]
    # reach[i]: the first i letters of `inner` can be matched into what is read so far.
    reach = [True] + [False] * len(inner)
    for ch in whole:
        for i in range(len(inner), 0, -1):
            reach[i] = (reach[i] and ch in MATRES) or (reach[i - 1] and inner[i - 1] == ch)
        reach[0] = reach[0] and ch in MATRES
    return reach[len(inner)]


def _male_index(forms: Set[str]) -> dict[str, list[str]]:
    """Each known form that has an inner vav or yod, filed under its skeleton."""
    index: dict[str, list[str]] = {}
    for form in forms:
        skeleton = _skeleton(form)
        if skeleton != form:
            index.setdefault(skeleton, []).append(form)
    return index


#: The languages `known_share` reads as Hebrew letters, with Hebrew's prefixes.
_HEBREW_SCRIPT = frozenset({"he", "yi", "arc"})

#: A word in any other alphabet: a run of letters, an apostrophe inside it kept.
_ANY_WORD = re.compile(r"[^\W\d_]+(?:['’][^\W\d_]+)*")


def _known_share_spaced(text: str, forms: Set[str]) -> float | None:
    """`known_share` for a language written in words with spaces between — Russian,
    French, Italian — rather than Hebrew letters (2026-10-06).

    The Hebrew rule finds no Hebrew token in a Russian headline and answers "not
    measured", which is right about Hebrew and useless once `search_sources` offers
    Russian publishers. Here a token is a run of letters, lower-cased, with ё read as е
    on both sides because publishers write it either way; known when it is among
    `forms`. No prefixes and no stemming, so an inflected word the ledger never saw in
    that form is unknown — an undercount, like the Hebrew one, and the exact figure is
    still the built text's coverage.
    """

    def fold(word: str) -> str:
        return word.lower().replace("ё", "е")

    tokens = [fold(token) for token in _ANY_WORD.findall(text)]
    if len(tokens) < MEASURABLE:
        return None
    folded = {fold(form) for form in forms}
    return sum(1 for token in tokens if token in folded) / len(tokens)


def known_share(text: str, forms: Set[str], language: str = "he") -> float | None:
    """The share of a text's Hebrew tokens the reader already has, cheaply.

    In a language not written in Hebrew letters, `_known_share_spaced` (2026-10-06).

    A token counts as known when it, or it less a prefix or two, is among `forms` — the
    reader's known words as surface forms and dictionary forms, plus the commonest
    words of the language (`hebrew.common_words`), all bare of their points. No
    lemmatizer: that costs about a minute a text on the box (memory 2026-09-03), and
    this is asked at quote time on a page nobody has built yet. It undercounts an
    inflected known word whose form the ledger never saw; the exact figure is the
    coverage a built text is measured with (`coverage.against`). None below
    `MEASURABLE` tokens: "not measured" and "0% known" are different claims.

    A token spelled haser also counts when putting back an inner vav or yod gives a known
    form: ארועים off a pointed page is the אירועים the reader knows (targum-internal#349).
    Only insertions into the token, and only those two letters, and never at its first
    or last letter: no letter is dropped from the known side to meet it, so a token
    with a letter the known form lacks stays unknown. Tried on the token and on it less
    a prefix or two, so והארועים counts too. Only a token that came with points is
    tried: haser is what taking them off leaves, while an unpointed page is written
    male already, and there the rule would only add collisions (קם for קיים, פחת for
    פחות), so an unpointed page measures exactly as it did. The known forms are filed
    by skeleton only when a pointed token misses outright, once a call.
    """
    if (language or "he").split("-")[0].lower() not in _HEBREW_SCRIPT:
        return _known_share_spaced(text, forms)
    found = [(_bare(t), _POINTS.search(t) is not None) for t in _WORD.findall(text)]
    tokens = [(t, pointed) for t, pointed in found if t]
    if len(tokens) < MEASURABLE:
        return None
    index: dict[str, list[str]] | None = None

    def is_known(token: str, pointed: bool) -> bool:
        nonlocal index
        candidates = _forms_of(token)
        if any(form in forms for form in candidates):
            return True
        if not pointed:
            return False
        if index is None:
            index = _male_index(forms)
        return any(
            _haser_of(form, male) for form in candidates for male in index.get(_skeleton(form), ())
        )

    known = sum(1 for token, pointed in tokens if is_known(token, pointed))
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


#: The share of a text's running words a reader has to know to read it. The research
#: puts adequate unassisted reading at 95–98% (Laufer 1989; Hu and Nation 2000), and
#: this was 0.95 until 2026-09-27. Measured against wordfreq, 95% fell past the list for
#: nearly every real text: 153 of 186 on the live shelf read Vav · C2, and a 17-word
#: scene read C1, because a list of spellings misses what a reader's lemmas are. At 90%
#: the scenes land at gimel and the shelf spreads. David's call (targum-internal#372):
#: a reader here reads with a dictionary one tap away, which is what the other 10% is.
TEXT_COVERAGE = 0.90


def text_rung(
    ranks: Iterable[int | None], ladder: Ladder, coverage: float = TEXT_COVERAGE
) -> Rung | None:
    """The rung a text needs, which is the text's and never the reader's (design.md §12,
    2026-09-24).

    `ranks` is the frequency rank of every running word's lemma, in order of the text,
    with None for a word past the frequency list. The text needs the vocabulary that
    covers `coverage` of its running words: the rank at that point in the sorted list. The
    rung is the lowest one whose vocabulary reaches it, and a text that needs more than
    the top rung has the top rung. None for a text with no words to count.
    """
    ordered = sorted(RANKED_PAST if one is None else one for one in ranks)
    if not ordered or not ladder.rungs:
        return None
    needed = ordered[max(0, ceil(coverage * len(ordered)) - 1)]
    for rung in ladder.rungs:
        if rung.at >= needed:
            return rung
    return ladder.rungs[-1]


#: What a word the frequency list never reached counts as: past every rung.
RANKED_PAST = 10**9
