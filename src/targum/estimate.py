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

**A borrowed word is easier than its place says** (design.md §12, "A borrowed word is
easier than its frequency says", 2026-11-05). A Hebrew word targum's root lexicon marks
borrowed (טלפון, אינטרנט, קפה: `annotate.root_card`, the file already on the box) has
`BORROWED` taken off its `b`. Measured on the laptop's marks, five folds held out, the
weight fitted on the four: pooled AUC 0.915 → 0.918, Brier 0.0566 → 0.0560, log loss
0.1865 → 0.1848, calibration error unchanged at 0.027; with the weight fitted on the
other readers only, 0.917. A machine without the lexicon estimates as before.

**Russian borrows the same term** (targum-internal#633, 2026-11-11): a Russian word the
Russian root lexicon marks borrowed (телефон, интернет, кофе: `roots-ru`, which agreed
with ling-ru's read on 98.9% of words, #596) has the same `BORROWED` taken off. The weight
is Hebrew's until Russian marks can fit their own: on 2026-11-11 the laptop held one
Russian reader with 125 marked words, nine of them not known, and no French reader with
any (`scripts/eval_estimate.py --language ru`). Held out on that one reader, AUC 0.831
with the term and 0.843 without, Brier 0.058 and 0.059: nine words decide nothing either
way. French has no lexicon and estimates as before.

**Tried and left out** (2026-11-05, the same run, `scripts/eval_difficulty_features.py`):
part of speech (verb, adjective, adverb and the closed classes against nouns) loses, AUC
0.914 and 0.909 with the weights from the other readers; a loanword list drawn from the
glosses (a Hebrew word whose English gloss it transliterates) is level, 0.916, inside
the noise; and the share of the root family the reader knows is level, 0.916, its weight
the wrong way round. Pooled difficulty from many readers (#586) and forgetting come
later; each changes `difficulty` or adds evidence, not the callers.
"""

from __future__ import annotations

import math
import threading
import unicodedata
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

#: How much easier, in log rank, a word the root lexicon marks borrowed is than its
#: place in the frequency list says: about five times commoner. Fitted on the laptop's
#: marks (2026-11-05, five folds): 1.60, the mean of the folds' weights.
BORROWED = 1.6

#: Where theta is looked for: the 20th word to past the 400,000th.
LOW, HIGH = math.log(20), math.log(400_000)


def sigmoid(x: float) -> float:
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    e = math.exp(x)
    return e / (1.0 + e)


def difficulty(lemma: str, language: str) -> float:
    """A word's `b`: the log of its place in the language's frequency list, less
    `BORROWED` for a word the language's root lexicon marks borrowed (Hebrew, Russian)."""
    return _difficulty(lemma, language, _borrowed(language))


#: Each word's `b` by language, kept while the frequency list and the borrowed words it
#: was worked out from are the same objects. A word's difficulty is the language's, not a
#: reader's, so it outlives every estimate: Home and Progress measure the whole shared
#: shelf against a fresh estimate after every sync, and working out each of its ~80,000
#: forms again — each a stat of the root lexicon — was most of their time on the box
#: (3–4 s a page, targum-internal#484, 2026-11-10).
_BS: dict[str, tuple[Any, frozenset[str], dict[str, float]]] = {}
_BS_MOST = 400_000
_NO_LOANS: frozenset[str] = frozenset()


def _difficulty(lemma: str, language: str, loans: frozenset[str]) -> float:
    """`difficulty` with the borrowed words already in hand, kept per word."""
    from .annotate import frequency

    places = frequency.ranks(language)
    held = _BS.get(language)
    if held is None or held[0] is not places or held[1] is not loans:
        held = (places, loans, {})
        _BS[language] = held
    memo = held[2]
    b = memo.get(lemma)
    if b is not None:
        return b
    place = _place(places, frequency._POINTS.sub("", lemma), language)
    b = math.log(place) if place else math.log(UNRANKED_AT)
    if loans and _loan_key(frequency._POINTS.sub("", lemma), language) in loans:
        b -= BORROWED
    if len(memo) < _BS_MOST:
        memo[lemma] = b
    return b


def _borrowed(language: str) -> frozenset[str]:
    """The words the language's root lexicon marks borrowed (`root_card.LANGUAGES`:
    Hebrew and Russian), as `_loan_key` spells them; none for another language, or where
    the lexicon is not on this machine. Read again when the file changes."""
    from .annotate import root_card

    code = language.split("-")[0].lower()
    if code not in root_card.LANGUAGES:
        return _NO_LOANS
    found = root_card.lexicon(code)
    if found is None:
        return _NO_LOANS
    with _DIFFICULTY_LOCK:
        held = _LOANS.get(code)
        if held is not None and held[0] is found:
            return held[1]
    rows = found.hebrew if code == "he" else found.russian
    loans = frozenset(lemma for lemma, row in rows.items() if row.borrowed)
    with _DIFFICULTY_LOCK:
        _LOANS[code] = (found, loans)
    return loans


def _loan_key(bare: str, language: str) -> str:
    """A lemma (points already off) spelled as its lexicon keys it: NFC for Hebrew,
    `root_card.fold_ru` for Russian (lower case, ё as е, no stress marks)."""
    if language.split("-")[0].lower() == "ru":
        from .annotate.root_card import fold_ru

        return fold_ru(bare)
    return unicodedata.normalize("NFC", bare)


def _place(places: Mapping[str, int], bare: str, language: str) -> int | None:
    """A word's place in the frequency list. In Russian ё and е are one letter written two
    ways, and wordfreq ranks the two spellings apart: еще is the 38th word and ещё the
    155th, черный the 2,425th and чёрный the 5,929th. A lemma spelled with ё takes the
    commoner of its two spellings, as `root_card.fold_ru` folds it for the borrowed words
    (targum-internal#684): ru-local restores ё in lemmas, and мёд or ещё would otherwise
    be scored rarer than they are. Most Russian is printed without ё, so the е spelling
    carries most of a word's uses; where it is also another word (все and всё) the two
    share its place, which errs easy."""
    place = places.get(bare)
    if ("ё" in bare or "Ё" in bare) and language.split("-")[0].lower() == "ru":
        plain = places.get(bare.replace("ё", "е").replace("Ё", "Е"))
        if plain is not None and (place is None or plain < place):
            return plain
    return place


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
    taken: tuple[str, list[str]] | None,
    marked: Mapping[str, int] | None = None,
    language: str = "he",
) -> tuple[list[Evidence], float | None]:
    """What the arrival's words check says, and the guess rate its made-up words measured.

    `taken` is `Store.checked`: the lists' version and the ticked words, in `language`,
    whose own lists it is read by (`check.LISTS`). A check taken against lists this
    targum no longer has says nothing, because what was shown can no longer be worked
    out. A word the reader has marked since is left to the mark. The guess rate is None
    where there is no check, and the claim grid keeps `CLAIM_GUESS`.
    """
    from . import check

    lists = check.lists_for(language)
    if taken is None or lists is None or taken[0] != lists.version:
        return [], None
    known, unknown, rate = check.answers(taken[1], lists.language)
    left = marked or {}
    out = [Evidence(word, True, 1.0, rate) for word in known if word not in left]
    out.extend(Evidence(word, False) for word in unknown if word not in left)
    return out, rate


def prior(level: Level | None) -> float:
    """The guess before any evidence: the rung named on arrival while nothing is measured
    (`level.seed`), else the rung the marks reach, else aleph.

    A rung's `at` is read as a vocabulary on both ladders. The ulpan's counts words; the
    CEFR's counts known words among the commonest five thousand lemmas (`level.CEFR`), and
    the words check reads theta back onto it the same way, as the vocabulary theta stands
    for (`check.common_reach`, calibrated by David on 2026-11-05: the *expected* count at
    the Rasch slope ran every band a step high). So a reader who names A2 and has done
    nothing else stands at A2, not at A1 or B1, and `tests/test_estimate.py` holds the two
    together for every rung of every ladder (targum-internal#633)."""
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
    loans = _borrowed(language)
    for item in items:
        key = (round(_difficulty(item.lemma, language, loans), 6), item.known, item.guess)
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

    _memo: dict[str, float] = field(default_factory=dict, compare=False, repr=False)
    #: The borrowed words, looked up once for the estimate's life rather than once a word.
    _loans: list[frozenset[str]] = field(default_factory=list, compare=False, repr=False)

    def chance(self, lemma: str) -> float:
        """The chance this reader knows a word they have not marked, between 0 and 1.
        Kept per word for the estimate's life: a shelf of built texts asks about the
        same common words hundreds of times (`coverage.running_against`)."""
        if not self.ranked:
            return 0.0
        held = self._memo.get(lemma)
        if held is None:
            if not self._loans:
                self._loans.append(_borrowed(self.language))
            b = _difficulty(lemma, self.language, self._loans[0])
            held = sigmoid(self.slope * (self.theta - b))
            if len(self._memo) < 200_000:
                self._memo[lemma] = held
        return held

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
_DIFFICULTIES: dict[tuple[int, str], tuple[tuple[str, ...], frozenset[str], array[float]]] = {}
#: Each language's borrowed words, with the lexicon they were read from.
_LOANS: dict[str, tuple[Any, frozenset[str]]] = {}


def _difficulties(index: Index, language: str) -> array[float]:
    """`difficulty` of every form in the index's table for one language; NaN for a form
    not written in the language's script, which `chances` reads as 0."""
    key = (id(index.words), language)
    loans = _borrowed(language)
    with _DIFFICULTY_LOCK:
        held = _DIFFICULTIES.get(key)
        if held is not None and held[0] is index.words and held[1] is loans:
            return held[2]
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
        place = _place(places, bare, language)
        b = math.log(place) if place else unranked
        if loans and _loan_key(bare, language) in loans:
            b -= BORROWED
        values.append(b)
    with _DIFFICULTY_LOCK:
        # One index at a time is all a box ever reads; an old one is let go.
        for stale in [one for one in _DIFFICULTIES if one[0] != key[0]]:
            del _DIFFICULTIES[stale]
        _DIFFICULTIES[key] = (index.words, loans, values)
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


# -- the one figure a page prints for a text -------------------------------------------


def shown(marked: float | None, expected: float | None) -> tuple[float | None, bool]:
    """The one figure every page prints for a text, and whether it is our estimate
    (design.md §12, "A text's figure is our estimate until your marks settle it",
    2026-11-04; David, 2026-11-03).

    The share the reader marked (`marked`) where their marks settle the text: where the
    estimate (`expected`, which a mark always wins inside) would print the same whole
    percentage (`level.known_percent`), so the estimate adds nothing a page could show.
    Otherwise the estimate, which a page always labels "our estimate". The estimate is
    never under the marked share, so "settled" is the moment the words a reader has not
    marked stop being worth a printed point. A text the reader has read and marked
    through says what they marked; a text they have never opened says what we estimate.

    `(None, False)` where neither was measured."""
    from .level import known_percent

    if expected is None:
        return marked, False
    if marked is not None and (
        expected <= marked or known_percent(marked) == known_percent(expected)
    ):
        return marked, False
    return expected, True


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
    from_check, rate = checked_evidence(taken, marked, code)
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
    """Drop every kept estimate, and every word's kept difficulty (tests)."""
    with _LOCK:
        _KEPT.clear()
    _BS.clear()
