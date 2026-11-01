"""What a reader probably knows of the words they have not marked (design.md §12, "The
chooser estimates the words you have not marked", 2026-11-01; targum-internal#613).

Pages say what the reader marked ("Known means marked"), and keep saying it. The chooser
may estimate (David, 2026-10-31): a reader who has marked 300 words knows more than 300,
and a text chosen on marks alone is chosen for somebody who knows only what they pressed.

**The model is one number per reader.** A word's difficulty `b` is the natural log of its
place in the language's frequency list (`annotate.frequency.rank`), so the 100th word is
4.6 and the 10,000th is 9.2. A reader's `theta` is on the same scale: the place in the
list where they know about half the words. The chance they know a word they have not
marked is σ(SLOPE · (theta − b)) — a one-parameter Rasch model, the shape vocabulary-size
tests assume (ling-he, 2026-10-31, §2.2).

**theta is fitted from what the reader did**, by maximum a posteriori over all of it at
once, and fitted again whenever any of it changes:

- a word marked known says known, with weight 1;
- a word on the list at steps 1–3 says not known, with weight 1;
- a word looked up and not since marked known says not known, with weight 1, once a word;
- a word met in a finished section and neither looked up nor marked says probably known,
  with weight `SKIP_WEIGHT` — weak, because a reader may simply not have pressed;
- a word ticked on "Words you may already know" (`source = 'claimed'`) says known, but a
  tick costs nothing, so it is read as a reader who also ticks `CLAIM_GUESS` of the words
  they do not know would tick it: P(tick) = p + (1 − p) · guess. The check's made-up
  words measure that guess per reader where they answered it;
- a word on the arrival's words check (`check.py`, design.md §12, "The arrival asks which
  words you know") says known where ticked, read with this reader's own guess rate, and
  not known where shown and left. A word they have marked since is the mark's alone.

The prior is the rung the reader named on arrival (`level.seed`), or the rung their marks
reach, or aleph, as a guess with a spread of `PRIOR_SD`. It matters only until there is
evidence: a hundred marks outweigh it.

**A mark always wins.** A word marked known is known (1), a word at steps 1–3 is not
yet (0: "a word somebody is halfway through learning is a word the text will still cost
them something to read", `coverage.KNOWN`), an ignored word is out of every total. Only a
word with no mark gets a probability.

**Measured, 2026-11-01** (`scripts/eval_estimate.py`). On the laptop's own marks (four
readers, 3,388 marked Hebrew words, five folds held out): pooled AUC 0.915, per reader
0.91 and 0.78 where there are enough "not known" words to tell, Brier 0.057 against 0.078
for the base rate, expected calibration error 0.027. On 150 simulated readers a setting,
over 434 Hebrew texts built on the laptop: an unread text's running-word coverage is
predicted within 4–5 points (marks alone are 36–78 points off), and with no reading yet
the chooser's first pick lands in the band for 47–57% of readers against 1% on marks.
After reading the estimate runs 3–4 points high, and the first pick lands in the band
about as often as on marks (51–65%), short of the 63–78% a perfect estimate would.

**What it is not, yet.** Part of speech, loanwords and root families (the card's other
features), pooled difficulty from many readers (#586) and forgetting all come later; each
changes `difficulty` or adds evidence, not the callers.
"""

from __future__ import annotations

import math
import threading
from array import array
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .coverage import IGNORED, KNOWN

if TYPE_CHECKING:
    from .accounts import Store
    from .coverage import Index
    from .level import Level

#: How steeply knowing falls off with a word's log rank. Fitted on the laptop's marks
#: (2026-11-01): 0.8 had the lowest held-out log loss of 0.6, 0.8, 1.0 and 1.3.
SLOPE = 0.8

#: wordfreq ranks surface forms, so a lemma's place is further down the list than the
#: number of lemmas before it: measured on 424 Hebrew texts built on the laptop, the median
#: log gap is 1.4–1.7 at every depth, about 4.5 forms a lemma. A rung counts lemmas, so
#: its theta is its count's log plus this.
FORMS_PER_LEMMA = 1.5

#: The difficulty of a word past the frequency list's last place: twice as far out.
UNRANKED_AT = 40_000

#: How sure the prior is, in log units: one spread is a vocabulary 4.5 times larger or
#: smaller than the rung named.
PRIOR_SD = 1.5

#: The rung assumed of a reader who named none and whose marks reach none: aleph.
PRIOR_WORDS = 250

#: What a word met in a finished section and left alone weighs, against a mark's 1. Some
#: of those words are unknown and simply not looked up: at 0.2 the simulated readers'
#: estimate ran 4 points high after reading, at 0.1 about 3, and with none 2.
SKIP_WEIGHT = 0.1

#: How often a reader is taken to tick a word they do not know on the claim grid, which
#: has no made-up words to measure it. Where the reader took the arrival's words check,
#: its made-up words measure it for them instead (`check.guess`).
CLAIM_GUESS = 0.15

#: Where theta is looked for: the 20th word to past the 400,000th.
LOW, HIGH = math.log(20), math.log(400_000)


def sigmoid(x: float) -> float:
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    e = math.exp(x)
    return e / (1.0 + e)


def difficulty(lemma: str, language: str) -> float:
    """A word's `b`: the log of its place in the language's frequency list."""
    from .annotate import frequency

    place = frequency.rank(lemma, language)
    return math.log(place) if place else math.log(UNRANKED_AT)


def ranked(language: str) -> bool:
    """Whether the language has a frequency list to estimate against at all. Where it has
    none, nothing is estimated and every unmarked word is unknown, as marks say."""
    from .annotate import frequency

    return bool(frequency.ranks(language))


@dataclass(frozen=True)
class Evidence:
    """One thing the reader did that says something about one word."""

    lemma: str
    known: bool
    weight: float = 1.0
    #: Where a "known" can be a guess: the share of unknown words the reader would say
    #: known anyway (`CLAIM_GUESS`, or the check's made-up words). 0 is a plain answer.
    guess: float = 0.0


def evidence(
    words: Iterable[tuple[str, int | None, str]],
    looked_up: Iterable[str] = (),
    met: Iterable[str] = (),
    *,
    claim_guess: float = CLAIM_GUESS,
) -> list[Evidence]:
    """Everything that says something about a reader, one item a word.

    `words` is (lemma, status, source) from the reader's list. A word marked known is a
    plain "known", except one ticked on the claim grid, which may be a guess; a word at
    steps 1–3 is "not known"; an ignored word says nothing. A look-up says "not known"
    where the word has no mark since; a word met in a finished section and neither looked
    up nor on the list is a weak "known". One- letter clitics are never words
    (`touchstones.a_word`).
    """
    from .touchstones import a_word

    out: list[Evidence] = []
    marked: set[str] = set()
    for lemma, status, source in words:
        if not lemma or status is None:
            continue
        marked.add(lemma)
        if not a_word(lemma) or status == IGNORED:
            continue
        if status == KNOWN:
            guess = claim_guess if source == "claimed" else 0.0
            out.append(Evidence(lemma, True, 1.0, guess))
        elif status in (1, 2, 3):
            out.append(Evidence(lemma, False))
    looked = {lemma for lemma in looked_up if lemma and a_word(lemma)} - marked
    out.extend(Evidence(lemma, False) for lemma in sorted(looked))
    left = {lemma for lemma in met if lemma and a_word(lemma)} - marked - looked
    out.extend(Evidence(lemma, True, SKIP_WEIGHT) for lemma in sorted(left))
    return out


def checked_evidence(
    taken: tuple[str, list[str]] | None, marked: Mapping[str, int] | None = None
) -> tuple[list[Evidence], float | None]:
    """What the arrival's words check says, and the guess rate its made-up words measured.

    `taken` is `Store.checked`: the lists' version and the ticked words. A check taken
    against lists this targum no longer has says nothing, because what was shown can no
    longer be worked out. A word the reader has marked since is left to the mark. The
    guess rate is None where there is no check, and the claim grid keeps `CLAIM_GUESS`.
    """
    from . import check

    if taken is None or taken[0] != check.VERSION:
        return [], None
    known, unknown, rate = check.answers(taken[1])
    left = marked or {}
    out = [Evidence(word, True, 1.0, rate) for word in known if word not in left]
    out.extend(Evidence(word, False) for word in unknown if word not in left)
    return out, rate


def prior(level: Level | None) -> float:
    """The guess before any evidence: the rung named on arrival while nothing is measured
    (`level.seed`), else the rung the marks reach, else aleph."""
    from . import level as level_module

    words = PRIOR_WORDS
    if level is not None:
        named = level_module.seed(level)
        if named is not None:
            words = named.at
        elif level.here is not None:
            words = level.here.at
    return math.log(max(words, 1)) + FORMS_PER_LEMMA


def fit(
    items: Iterable[Evidence],
    language: str,
    centre: float,
    spread: float = PRIOR_SD,
    slope: float = SLOPE,
) -> float:
    """The reader's theta: the most probable given the evidence and the prior.

    The log posterior is concave in theta for plain answers and very nearly so with
    guesses, so a golden-section search over [LOW, HIGH] finds it in about sixty steps,
    each one pass over the evidence. Words of the same difficulty are pooled first.
    """
    pooled: dict[tuple[float, bool, float], float] = {}
    for item in items:
        key = (round(difficulty(item.lemma, language), 6), item.known, item.guess)
        pooled[key] = pooled.get(key, 0.0) + item.weight
    rows = [(b, known, guess, weight) for (b, known, guess), weight in pooled.items()]

    def score(theta: float) -> float:
        total = -((theta - centre) ** 2) / (2 * spread * spread)
        for b, known, guess, weight in rows:
            p = sigmoid(slope * (theta - b))
            if known:
                p = p + (1 - p) * guess
                total += weight * math.log(max(p, 1e-12))
            else:
                total += weight * math.log(max(1 - p, 1e-12))
        return total

    golden = (math.sqrt(5) - 1) / 2
    low, high = LOW, HIGH
    left = high - golden * (high - low)
    right = low + golden * (high - low)
    at_left, at_right = score(left), score(right)
    while high - low > 1e-4:
        if at_left < at_right:
            low, left, at_left = left, right, at_right
            right = low + golden * (high - low)
            at_right = score(right)
        else:
            high, right, at_right = right, left, at_left
            left = high - golden * (high - low)
            at_left = score(left)
    return (low + high) / 2


@dataclass(frozen=True)
class Estimate:
    """One reader's estimate in one language: theta, and their marks, which win."""

    language: str
    theta: float
    marked: Mapping[str, int]
    #: How many words said something, for the record and for tests.
    evidence: int = 0
    slope: float = SLOPE
    #: Whether there is a frequency list behind it; without one every unmarked word is 0.
    ranked: bool = True
    _chances: dict[int, tuple[tuple[str, ...], array[float]]] = field(
        default_factory=dict, compare=False, repr=False
    )

    def chance(self, lemma: str) -> float:
        """The chance this reader knows a word they have not marked, between 0 and 1."""
        if not self.ranked:
            return 0.0
        return sigmoid(self.slope * (self.theta - difficulty(lemma, self.language)))

    def p_known(self, lemma: str) -> float | None:
        """The chance this reader knows a word: a mark wins (known 1, learning 0, ignored
        None, which is out of every total); a word with no mark gets `chance`."""
        status = self.marked.get(lemma)
        if status == KNOWN:
            return 1.0
        if status == IGNORED:
            return None
        if status is not None:
            return 0.0
        return self.chance(lemma)

    def chances(self, index: Index) -> array[float]:
        """`chance` for every form in a lemma index's shared table, by position: worked
        out once per estimate and index, so a walk of the whole catalogue is arithmetic.
        A form of another language is the language's own business and gets 0 here."""
        held = self._chances.get(id(index.words))
        if held is not None and held[0] is index.words:
            return held[1]
        table = _difficulties(index, self.language)
        out = array(
            "d",
            (
                sigmoid(self.slope * (self.theta - b)) if self.ranked and b == b else 0.0
                for b in table
            ),
        )
        self._chances.clear()
        self._chances[id(index.words)] = (index.words, out)
        return out

    def words(self) -> int:
        """The vocabulary theta stands for, in lemmas: the place where knowing is even,
        less the forms-per-lemma gap. For the record and the evaluation, never a page."""
        return round(math.exp(self.theta - FORMS_PER_LEMMA))


_DIFFICULTY_LOCK = threading.Lock()
_DIFFICULTIES: dict[tuple[int, str], tuple[tuple[str, ...], array[float]]] = {}


def _difficulties(index: Index, language: str) -> array[float]:
    """`difficulty` of every form in the index's table for one language; NaN for a form
    not written in the language's script, which `chances` reads as 0."""
    key = (id(index.words), language)
    with _DIFFICULTY_LOCK:
        held = _DIFFICULTIES.get(key)
        if held is not None and held[0] is index.words:
            return held[1]
    from .annotate import frequency

    places = frequency.ranks(language)
    unranked = math.log(UNRANKED_AT)
    script = _script(language)
    values = array("d")
    for word in index.words:
        bare = frequency._POINTS.sub("", word)
        if script is not None and not script(bare):
            values.append(math.nan)
            continue
        place = places.get(bare)
        values.append(math.log(place) if place else unranked)
    with _DIFFICULTY_LOCK:
        # One index at a time is all a box ever reads; an old one is let go.
        for stale in [one for one in _DIFFICULTIES if one[0] != key[0]]:
            del _DIFFICULTIES[stale]
        _DIFFICULTIES[key] = (index.words, values)
    return values


def _script(language: str) -> Any:
    """Whether a form is written in the language's script, where that tells languages
    apart in the one shared table: Hebrew letters for Hebrew, Cyrillic for Russian, Latin
    for French and Italian."""
    code = language.split("-")[0].lower()
    if code in ("he", "yi", "arc"):
        return lambda word: any("א" <= c <= "ת" for c in word)
    if code == "ru":
        return lambda word: any("Ѐ" <= c <= "ӿ" for c in word)
    if code in ("fr", "it", "en"):
        return lambda word: (
            any(c.isascii() and c.isalpha() for c in word) or any("À" <= c <= "ɏ" for c in word)
        )
    return None


# -- one reader's estimate, kept until what it was fitted on changes --------------------

_LOCK = threading.Lock()
_KEPT: dict[tuple[int, str], tuple[tuple[Any, ...], Estimate]] = {}
#: How many readers' estimates one process keeps.
KEEP = 256


def for_reader(
    store: Store | None, person_id: int | None, language: str, level: Level | None = None
) -> Estimate:
    """This reader's estimate in one language, fitted again whenever their list, their
    look-ups or the words they met have changed since — which is to say after a sync —
    and kept in memory between. A reader with no account gets the prior alone."""
    code = (language or "he").split("-")[0].lower()
    centre = prior(level)
    if store is None or person_id is None:
        return Estimate(code, centre, {}, 0, ranked=ranked(code))
    words, looked_up, met = store.knowledge(person_id, code)
    taken = store.checked(person_id, code)
    stamp = (
        len(words),
        hash(tuple(words)),
        len(looked_up),
        len(met),
        round(centre, 6),
        None if taken is None else (taken[0], tuple(taken[1])),
    )
    key = (int(person_id), code)
    with _LOCK:
        held = _KEPT.get(key)
        if held is not None and held[0] == stamp:
            return held[1]
    marked = {lemma: status for lemma, status, _ in words if status is not None}
    from_check, rate = checked_evidence(taken, marked)
    items = (
        evidence(words, looked_up, met, claim_guess=CLAIM_GUESS if rate is None else rate)
        + from_check
    )
    has_list = ranked(code)
    theta = fit(items, code, centre) if has_list and items else centre
    made = Estimate(code, theta, marked, len(items), ranked=has_list)
    with _LOCK:
        if len(_KEPT) >= KEEP and key not in _KEPT:
            _KEPT.pop(next(iter(_KEPT)))
        _KEPT[key] = (stamp, made)
    return made


def forget() -> None:
    """Drop every kept estimate (tests)."""
    with _LOCK:
        _KEPT.clear()
