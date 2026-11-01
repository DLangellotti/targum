"""The cheap scorer: a page's words turned into lemma counts without DICTA
(targum-internal#619; plan §2.2–2.3).

DICTA reads about a text a minute on the box, which is out of reach for the hundreds of
candidates a day the pool sees. `level.known_share` is fast, but it scores against one
reader's surface forms, so it gives one figure per reader per page and nothing to keep.
What makes per-reader scoring cheap is to turn a page into **lemma counts once**, the
shape `coverage.Index.counts` holds for a shelf text; any reader's running-word coverage
is then a sum (`Score.coverage`).

**The map** (`forms.json`). For each surface form, bare of points, the lemma DICTA gave it
most often across the **public shelf's** modern texts, read through `tables.public_text`
and nothing else, so a reader's import can never enter it. A form DICTA mostly read as a
name or a number, or as a one-letter clitic, is filed as not a word, and a page's token
of it is left out of the count as Phase 0 leaves them out (`coverage.Index.running`). It
is library data, so it is private like the catalogue: built on the laptop by `targum
finds forms`, never committed, and shipped to the box beside the catalogue by
`deploy/deploy.sh`, which checks it first.

**A token is looked up** as itself, then less one prefix letter, then less two
(`level.PREFIXES`); a pointed token that still misses tries the haser rule
`level.known_share` uses (`level._haser_of`). Anything else is **unresolved**, and
counts as unknown: conservative, and where the measured bias comes from.

**Calibration** (`calibrate`) reruns plan §2.3 over whatever shelf it is pointed at: the
map built from four fifths of the modern texts, split by series, and the other fifth
scored both ways for readers who know exactly the commonest N lemmas.
"""

from __future__ import annotations

import json
import os
import re
from collections import Counter
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import lru_cache
from math import ceil
from pathlib import Path
from typing import Any

from .. import level as level_module
from ..coverage import IGNORED, KNOWN
from ..ids import short_hash
from ..paths import write_atomic
from ..touchstones import a_word

#: The file's shape. A file of another version is refused rather than misread.
VERSION = "forms/1"

#: Where the map is read from, in the order `sentence_level.PLACES` keeps: a path named
#: in the environment is the path, found or not.
ENV = "TARGUM_FORMS"
PLACES = (Path.home() / ".targum" / "forms.json", Path("/etc/targum/forms.json"))

#: A text whose annotation says more than this share of it is scripture is not modern
#: Hebrew, and is left out of the map and the calibration: the Tanakh alone would outvote
#: every modern text on a shared spelling.
MODERN_SCRIPTURE = 0.2

#: The register left out of the map whatever its share of scripture says
#: (`tables.register_of`).
BIBLE = "bible"

#: The registers the calibration does not test on: the pool scores news, and the
#: Mishnah's Hebrew is not what a news page is written in. They stay in the map, where
#: they were measured to help (more forms seen, fewer unresolved; 2026-10-31).
NOT_TESTED = frozenset({"rabbinic", "medieval"})

#: A page with more than this share of its running words unresolved is not measured
#: (plan §2.3): it gets no Read next slot.
UNRESOLVED_MOST = 0.08

#: Under this many running words a share is a guess (`level.MEASURABLE`).
MEASURABLE = level_module.MEASURABLE

#: How many of the commonest lemmas the map keeps a rank for, to place a page on its
#: language's ladder (`rung_of`).
RANKS_KEPT = 30_000

MAQAF = "\u05be"

#: The languages whose finds are pooled: those whose calibration holds the bound. Russian
#: was measured on 2026-10-31 at 15% unresolved and 4–8.5 points off DICTA's figure (no
#: prefixes to strip, and a thin shelf), so its finds would nearly all be "not measured";
#: it waits for a map of its own (a pymorphy3 one is a later card, plan §2.3).
POOLED = frozenset({"he"})

#: The languages written in Hebrew letters, with Hebrew's prefixes (`level._HEBREW_SCRIPT`).
HEBREW_SCRIPT = frozenset({"he", "yi", "arc"})


def code(language: str) -> str:
    return (language or "").split("-")[0].lower()


def fold(word: str) -> str:
    """A word in a spaced language as the map files it: lower case, ё read as е
    (`level._known_share_spaced`)."""
    return word.lower().replace("ё", "е")


def tokens_of(text: str, language: str) -> list[str]:
    """A page's words as the scorer reads them. Hebrew keeps its points, which the haser
    rule needs; the map is looked up bare. A maqaf joins two words, as DICTA reads them,
    and taking the points off would otherwise run them together (בית־ספר)."""
    if code(language) in HEBREW_SCRIPT:
        return [
            token
            for joined in level_module._WORD.findall(text)
            for token in joined.split(MAQAF)
            if level_module._bare(token)
        ]
    return [fold(token) for token in level_module._ANY_WORD.findall(text)]


def form_of(surface: str, language: str) -> str:
    """The one form an annotated token's surface is filed under, or "" where it is not
    one word."""
    found = tokens_of(surface, language)
    if len(found) != 1:
        return ""
    return level_module._bare(found[0]) if code(language) in HEBREW_SCRIPT else found[0]


#: How a token was resolved, for the calibration's table.
EXACT, ONE, TWO, HASER, SUFFIX, NAME, UNRESOLVED = (
    "exact",
    "one",
    "two",
    "haser",
    "suffix",
    "name",
    "unresolved",
)

#: The endings tried off a Hebrew token the map has never seen, longest first: plurals,
#: the construct and the possessives. What is left is taken only where it is itself a
#: lemma the map holds, with a final letter put back in its final form, or a feminine ה
#: put back on (מערת is מערה). Measured on the laptop's shelf, 2026-10-31: unresolved
#: words fell from 8.9% to 5.5% of a modern text and the mean error at every simulated
#: reader from 1.7–2.9 points to 1.1–1.5, its bias from −1.3–−2.6 to about nought.
SUFFIXES = (
    "ותיהם",
    "ותיהן",
    "יהם",
    "יהן",
    "ותיו",
    "ותיה",
    "ותיך",
    "ותי",
    "ותנו",
    "יכם",
    "כם",
    "הם",
    "הן",
    "נו",
    "יו",
    "יה",
    "ים",
    "ות",
    "יי",
    "ה",
    "ו",
    "י",
    "ך",
    "ת",
)

#: A letter's final form, for a stem whose ending was taken off.
FINAL = {"כ": "ך", "מ": "ם", "נ": "ן", "פ": "ף", "צ": "ץ"}


def _final(stem: str) -> str:
    return stem[:-1] + FINAL.get(stem[-1], stem[-1]) if stem else stem


@dataclass
class Score:
    """One page as lemma counts: what a pool row keeps, and all it keeps."""

    #: Running words counted: names, numbers and clitics out, unresolved in.
    tokens: int = 0
    unresolved: int = 0
    bag: dict[str, int] = field(default_factory=dict)

    @property
    def unresolved_share(self) -> float:
        return self.unresolved / self.tokens if self.tokens else 1.0

    @property
    def measured(self) -> bool:
        """Whether a share off this page means anything: enough words, and few enough
        the map could not place."""
        return self.tokens >= MEASURABLE and self.unresolved_share <= UNRESOLVED_MOST

    def coverage(self, marked: Mapping[str, int]) -> float | None:
        """The share of the page's running words this reader has marked known
        (`coverage.Index.running`'s rule): a word they ignored comes out of the total, an
        unresolved word stays in it as unknown. None where nothing is left to count."""
        known = ignored = 0
        for lemma, n in self.bag.items():
            status = marked.get(lemma)
            if status == KNOWN:
                known += n
            elif status == IGNORED:
                ignored += n
        scored = self.tokens - ignored
        return known / scored if scored > 0 else None

    def expected(self, p_known: Callable[[str], float | None]) -> float | None:
        """The share of the page's running words this reader is estimated to know, each
        lemma counted at `p_known` (`estimate.Estimate.p_known`; None is ignored, out of
        the total). An unresolved word stays in as unknown, as in `coverage`."""
        known = 0.0
        ignored = 0
        for lemma, n in self.bag.items():
            chance = p_known(lemma)
            if chance is None:
                ignored += n
            else:
                known += n * chance
        scored = self.tokens - ignored
        return known / scored if scored > 0 else None


@dataclass
class Forms:
    """One language's map, loaded."""

    language: str
    forms: dict[str, str]
    #: Forms DICTA mostly read as a name, a number or a lone clitic: never counted.
    names: frozenset[str] = frozenset()
    #: Each kept lemma's rank among the shelf's running words, commonest first, from 1.
    ranks: dict[str, int] = field(default_factory=dict)
    _male: dict[str, list[str]] | None = field(default=None, repr=False)
    _lemmas: frozenset[str] | None = field(default=None, repr=False)

    @property
    def hebrew(self) -> bool:
        return code(self.language) in HEBREW_SCRIPT

    def _haser(self, candidates: Sequence[str]) -> str:
        if self._male is None:
            self._male = level_module._male_index(set(self.forms) | set(self.names))
        for form in candidates:
            for male in self._male.get(level_module._skeleton(form), ()):
                if level_module._haser_of(form, male):
                    return male
        return ""

    @property
    def lemmas(self) -> frozenset[str]:
        """Every lemma the map files a form under."""
        if self._lemmas is None:
            self._lemmas = frozenset(self.forms.values())
        return self._lemmas

    def _lookup(self, form: str) -> str:
        """A form's lemma: the one the map files it under, or itself where it is spelled
        as a lemma the map holds and was never seen inflected that way."""
        return self.forms.get(form) or (form if form in self.lemmas else "")

    def _suffixed(self, candidates: Sequence[str]) -> str:
        for form in candidates:
            for ending in SUFFIXES:
                if not form.endswith(ending) or len(form) - len(ending) < 2:
                    continue
                stem = form[: -len(ending)]
                # תשתיות is תשתית: a plural in ות of a word ending in ת.
                after: tuple[str, ...] = (stem + "ת",) if ending == "ות" else ()
                tried: tuple[str, ...] = (_final(stem), stem + "ה", *after, stem)
                for lemma in tried:
                    if lemma in self.lemmas:
                        return lemma
        return ""

    def resolve(self, token: str) -> tuple[str, str]:
        """The lemma a token is counted under and how it was found; "" for a name or an
        unresolved token."""
        if not self.hebrew:
            if token in self.names:
                return "", NAME
            lemma = self._lookup(token)
            return (lemma, EXACT) if lemma else ("", UNRESOLVED)
        bare = level_module._bare(token)
        candidates = level_module._forms_of(bare)
        for how, form in zip((EXACT, ONE, TWO), candidates, strict=False):
            if form in self.names:
                return "", NAME
            lemma = self._lookup(form)
            if lemma:
                return lemma, how
        if level_module._POINTS.search(token):
            male = self._haser(candidates)
            if male in self.names:
                return "", NAME
            if male:
                return self.forms[male], HASER
        lemma = self._suffixed(candidates)
        if lemma:
            return lemma, SUFFIX
        return "", UNRESOLVED

    def score_tokens(self, tokens: Iterable[str]) -> Score:
        return self.score_counts(Counter(tokens))

    def score_counts(self, counts: Mapping[str, int]) -> Score:
        """A page given as each token and how often it comes round."""
        out = Score()
        bag: Counter[str] = Counter()
        for token, n in counts.items():
            lemma, how = self.resolve(token)
            if how == NAME or (lemma and not a_word(lemma)):
                continue
            out.tokens += n
            if lemma:
                bag[lemma] += n
            else:
                out.unresolved += n
        out.bag = dict(bag)
        return out

    def score(self, text: str) -> Score:
        return self.score_tokens(tokens_of(text, self.language))

    def rung_of(self, score: Score) -> int | None:
        """Where on its language's ladder a page sits, as an index into the rungs
        (`level.text_rung`, at 90% of its running words), with an unresolved word past
        every rung. None where the language has no ladder or the page is not measured."""
        ladder = level_module.ladder_for(self.language)
        if ladder is None or not score.measured:
            return None
        ranks: list[int | None] = []
        for lemma, n in score.bag.items():
            ranks.extend([self.ranks.get(lemma)] * n)
        ranks.extend([None] * score.unresolved)
        rung = level_module.text_rung(ranks, ladder)
        return None if rung is None else ladder.rungs.index(rung)


# -- reading an annotation ----------------------------------------------------------


@dataclass(frozen=True)
class Annotated:
    """One public text's tokens as DICTA read them: (surface, lemma, a word to count)."""

    key: str
    series: str
    language: str
    licence: str
    register: str
    tokens: tuple[tuple[str, str, bool], ...]

    def words(self) -> int:
        return sum(1 for _, _, counted in self.tokens if counted)


_PART = re.compile(r"(?:[-_ ](?:part|chapter|ch|p)?\d+)+$", re.I)


def series_of(name: str) -> str:
    """A folder's series: its name with a trailing part number taken off, so the 36
    parts of one declaration cannot fall on both sides of the split."""
    return _PART.sub("", name) or name


def annotated(library: Path, languages: Iterable[str]) -> Iterator[Annotated]:
    """Every public modern text under `library` in one of `languages`, through
    `tables.public_text` only: a reader's home, a private import and anything doubtful
    are skipped, whatever they hold."""
    from ..annotate.base import not_vocabulary
    from ..ledger import text_folders
    from ..tables import public_text

    wanted = {code(one) for one in languages}
    for folder in text_folders(library):
        file = folder / "annotation.json"
        if not file.is_file():
            continue
        text = public_text(folder, library)
        if text is None:
            continue
        try:
            loaded = json.loads(file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(loaded, dict):
            continue
        language = code(str(loaded.get("language") or ""))
        if language not in wanted:
            continue
        if float(loaded.get("scripture_share") or 0.0) > MODERN_SCRIPTURE:
            continue
        if text.register == BIBLE:
            continue
        rows: list[tuple[str, str, bool]] = []
        for _sid, tokens in sorted((loaded.get("tokens") or {}).items()):
            for token in tokens or ():
                surface = str(token.get("surface") or "")
                lemma = str(token.get("lemma") or "")
                counted = (
                    bool(lemma)
                    and a_word(lemma)
                    and not not_vocabulary(token.get("pos"), token.get("entity"))
                )
                rows.append((surface, lemma, counted))
        yield Annotated(
            key=text.document_hash,
            series=series_of(folder.name),
            language=language,
            licence=text.licence,
            register=text.register,
            tokens=tuple(rows),
        )


def build_language(texts: Iterable[Annotated], language: str) -> dict[str, Any]:
    """One language's map from its texts: each form's commonest lemma, the forms that
    are mostly not a word, and the commonest lemmas' ranks."""
    by_form: dict[str, Counter[str]] = {}
    not_words: Counter[str] = Counter()
    seen: Counter[str] = Counter()
    lemmas: Counter[str] = Counter()
    count = tokens = 0
    for text in texts:
        count += 1
        for surface, lemma, counted in text.tokens:
            form = form_of(surface, language)
            if not form:
                continue
            tokens += 1
            seen[form] += 1
            if not counted:
                not_words[form] += 1
                continue
            by_form.setdefault(form, Counter())[lemma] += 1
            lemmas[lemma] += 1
    names = sorted(form for form, n in not_words.items() if n * 2 > seen[form])
    named = set(names)
    forms = {
        form: max(counts.items(), key=lambda pair: (pair[1], pair[0]))[0]
        for form, counts in by_form.items()
        if form not in named
    }
    ranked = [lemma for lemma, _ in sorted(lemmas.items(), key=lambda p: (-p[1], p[0]))]
    return {
        "texts": count,
        "tokens": tokens,
        "forms": dict(sorted(forms.items())),
        "names": names,
        "ranked": ranked[:RANKS_KEPT],
    }


def build(library: Path, languages: Iterable[str] = ("he",)) -> dict[str, Any]:
    """The whole `forms.json` body, from the public shelf under `library`."""
    wanted = [code(one) for one in languages]
    by_language: dict[str, list[Annotated]] = {one: [] for one in wanted}
    for text in annotated(library, wanted):
        by_language[text.language].append(text)
    return {
        "version": VERSION,
        "built": datetime.now(UTC).isoformat(timespec="seconds"),
        "languages": {one: build_language(texts, one) for one, texts in by_language.items()},
    }


def write(body: Mapping[str, Any], to: Path) -> None:
    to.parent.mkdir(parents=True, exist_ok=True)
    write_atomic(to, json.dumps(body, ensure_ascii=False, separators=(",", ":")))


def path() -> Path | None:
    named = os.environ.get(ENV, "").strip()
    if named:
        return Path(named) if Path(named).is_file() else None
    for place in PLACES:
        if place.is_file():
            return place
    return None


def forms_from(body: Mapping[str, Any], language: str) -> Forms | None:
    if body.get("version") != VERSION:
        return None
    held = (body.get("languages") or {}).get(code(language))
    if not isinstance(held, dict) or not held.get("forms"):
        return None
    ranked = held.get("ranked") or []
    return Forms(
        language=code(language),
        forms={str(k): str(v) for k, v in (held.get("forms") or {}).items()},
        names=frozenset(str(one) for one in held.get("names") or ()),
        ranks={str(lemma): at for at, lemma in enumerate(ranked, start=1)},
    )


@lru_cache(maxsize=2)
def _read(where: str, stamp: tuple[int, int]) -> dict[str, Any]:
    try:
        loaded = json.loads(Path(where).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


@lru_cache(maxsize=8)
def _forms(where: str, stamp: tuple[int, int], language: str) -> Forms | None:
    return forms_from(_read(where, stamp), language)


def load(language: str, where: Path | None = None) -> Forms | None:
    """One language's map, read once per change of the file; None where there is none.
    A box without the file pools nothing, and Read next is as it was."""
    file = where or path()
    if file is None:
        return None
    try:
        stat = file.stat()
    except OSError:
        return None
    return _forms(str(file), (stat.st_mtime_ns, stat.st_size), code(language))


def check(file: Path) -> list[str]:
    """What is wrong with a map before it ships, or nothing: the version, a language
    with no forms, and a map so small it could only have been built from the wrong
    folder (deploy.sh runs this before it copies the file)."""
    try:
        body = json.loads(file.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        return [f"{file} is not readable JSON: {error}"]
    if not isinstance(body, dict) or body.get("version") != VERSION:
        return [f"{file} is not a {VERSION} file"]
    wrong: list[str] = []
    languages = body.get("languages") or {}
    if not languages:
        wrong.append("it holds no language")
    for language, held in languages.items():
        forms = (held or {}).get("forms") or {}
        if len(forms) < CHECK_LEAST_FORMS:
            wrong.append(
                f"{language} has {len(forms)} forms, under {CHECK_LEAST_FORMS}: "
                "built from the wrong folder?"
            )
    return wrong


#: The fewest forms a shipped language may hold. 193 modern Hebrew texts gave 80k.
CHECK_LEAST_FORMS = 5_000


# -- calibration (plan §2.3) -------------------------------------------------------

#: The simulated readers: they know exactly the commonest N lemmas of the map's texts.
READERS = (2000, 3000, 4500, 6500)

#: A text shorter than this, in words counted, says too little to calibrate on.
CALIBRATE_LEAST = 150

#: The folds the texts are split into, by series: each fold is scored with a map built
#: from the other four, so every text is tested once and never against its own words.
FOLDS = 5


def fold_of(series: str) -> int:
    return int(short_hash(series, 8), 16) % FOLDS


def tested(text: Annotated) -> bool:
    return text.register not in NOT_TESTED and text.words() >= CALIBRATE_LEAST


@dataclass
class Row:
    known: int
    mean: float
    mean_abs: float
    p90_abs: float
    over_dicta: int
    over_cheap: int
    same_side: float


@dataclass
class Calibration:
    language: str
    texts: int
    test: int
    test_tokens: int
    #: Share of the test's running words found each way (`resolve`).
    found: dict[str, float]
    #: Share of the test's resolved running words given DICTA's own lemma.
    agree: float
    rows: list[Row]

    def worst(self) -> float:
        return max((row.mean_abs for row in self.rows), default=0.0)

    def state(self) -> dict[str, Any]:
        return {
            "language": self.language,
            "texts": self.texts,
            "test": self.test,
            "test_tokens": self.test_tokens,
            "found": {k: round(v, 4) for k, v in self.found.items()},
            "agree": round(self.agree, 4),
            "rows": [
                {
                    "known": row.known,
                    "mean": round(row.mean, 4),
                    "mean_abs": round(row.mean_abs, 4),
                    "p90_abs": round(row.p90_abs, 4),
                    "over_dicta": row.over_dicta,
                    "over_cheap": row.over_cheap,
                    "same_side": round(row.same_side, 4),
                }
                for row in self.rows
            ],
        }


def _p90(values: Sequence[float]) -> float:
    ordered = sorted(values)
    return ordered[max(0, ceil(0.9 * len(ordered)) - 1)] if ordered else 0.0


@dataclass(frozen=True)
class Case:
    """One test text as both sides see it, with the map and readers of its fold."""

    forms: Forms
    #: Its words as the scorer reads them off the page.
    tokens: Mapping[str, int]
    #: DICTA's lemmas of the words it counts.
    lemmas: Mapping[str, int]
    #: For each simulated reader, the lemmas they know.
    known: Mapping[int, frozenset[str]]


def table(cases: Sequence[Case], floor: float = level_module.TEXT_COVERAGE) -> list[Row]:
    """Plan §2.3's rows: the cheap figure against DICTA's, reader by reader."""
    scored = [case.forms.score_counts(case.tokens) for case in cases]
    readers = sorted({n for case in cases for n in case.known})
    rows: list[Row] = []
    for n in readers:
        errors: list[float] = []
        over_dicta = over_cheap = same = 0
        for case, score in zip(cases, scored, strict=True):
            known = case.known.get(n, frozenset())
            total = sum(case.lemmas.values())
            if not total:
                continue
            real = sum(c for lemma, c in case.lemmas.items() if lemma in known) / total
            cheap = score.coverage(dict.fromkeys(known, KNOWN)) or 0.0
            errors.append(cheap - real)
            over_dicta += real >= floor
            over_cheap += cheap >= floor
            same += (real >= floor) == (cheap >= floor)
        count = len(errors) or 1
        rows.append(
            Row(
                known=n,
                mean=sum(errors) / count,
                mean_abs=sum(abs(e) for e in errors) / count,
                p90_abs=_p90([abs(e) for e in errors]),
                over_dicta=over_dicta,
                over_cheap=over_cheap,
                same_side=same / count,
            )
        )
    return rows


def page_counts(text: Annotated, language: str) -> tuple[Counter[str], Counter[str]]:
    """A test text as the two sides compare it: its words as the scorer reads them off
    the page, and DICTA's lemmas of the words it counts."""
    tokens: Counter[str] = Counter()
    for surface, _, _ in text.tokens:
        tokens.update(tokens_of(surface, language))
    lemmas = Counter(lemma for _, lemma, counted in text.tokens if counted)
    return tokens, lemmas


def cases(
    texts: Sequence[Annotated], language: str = "he", readers: Sequence[int] = READERS
) -> Iterator[tuple[Annotated, Case]]:
    """Every testable text with the map and readers built from the other folds."""
    mine = [one for one in texts if one.language == code(language)]
    for at in range(FOLDS):
        test = [one for one in mine if fold_of(one.series) == at and tested(one)]
        if not test:
            continue
        built = build_language([one for one in mine if fold_of(one.series) != at], language)
        forms = forms_from({"version": VERSION, "languages": {code(language): built}}, language)
        if forms is None:
            forms = Forms(language=code(language), forms={})
        ranked = built["ranked"]
        known = {n: frozenset(ranked[:n]) for n in readers}
        for one in test:
            tokens, lemmas = page_counts(one, language)
            yield one, Case(forms=forms, tokens=tokens, lemmas=lemmas, known=known)


def calibrate(
    texts: Sequence[Annotated], language: str = "he", readers: Sequence[int] = READERS
) -> Calibration:
    """Plan §2.3's table over `texts`, which `annotated` read off a shelf."""
    held = list(cases(texts, language, readers))
    found: Counter[str] = Counter()
    agree = resolved = 0
    for one, case in held:
        for surface, lemma, counted in one.tokens:
            for token in tokens_of(surface, language):
                got, how = case.forms.resolve(token)
                if how == NAME or not counted:
                    continue
                found[how] += 1
                if got:
                    resolved += 1
                    agree += got == lemma
    total = sum(found.values()) or 1
    return Calibration(
        language=code(language),
        texts=sum(1 for one in texts if one.language == code(language)),
        test=len(held),
        test_tokens=sum(sum(case.lemmas.values()) for _, case in held),
        found={how: found[how] / total for how in (EXACT, ONE, TWO, HASER, SUFFIX, UNRESOLVED)},
        agree=agree / resolved if resolved else 0.0,
        rows=table([case for _, case in held]),
    )


def _reach(forms: Forms, tokens: Iterable[str]) -> tuple[dict[str, str], list[str]]:
    """The slice of a map a page's tokens can reach, and the not-words among it: what
    a fixture needs to score the page exactly as the whole map does."""
    reach: dict[str, str] = {}
    names: set[str] = set()
    for token in tokens:
        bare = level_module._bare(token) if forms.hebrew else token
        candidates = level_module._forms_of(bare) if forms.hebrew else [bare]
        for form in candidates:
            if form in forms.names:
                names.add(form)
            lemma = forms._lookup(form)
            if lemma:
                reach[form] = lemma
        if forms.hebrew and level_module._POINTS.search(token):
            male = forms._haser(candidates)
            if male in forms.names:
                names.add(male)
            elif male:
                reach[male] = forms.forms[male]
        if forms.hebrew:
            lemma = forms._suffixed(candidates)
            if lemma:
                reach[lemma] = lemma
    return reach, sorted(names)


def fixture(
    texts: Sequence[Annotated],
    language: str = "he",
    readers: Sequence[int] = READERS,
    licences: Iterable[str] = (),
    registers: Iterable[str] = (),
    most: int = 20,
) -> dict[str, Any]:
    """A frozen sample of the calibration for the suite: each held-out text whose
    licence is among `licences` as two bags of counts (never the text, and no title or
    address), the slice of its fold's map its tokens can reach, and which of its lemmas
    each reader knows. Scoring a bag with its slice gives what the whole map gives.

    `registers` widens the sample to texts the calibration does not test on (the
    Mishnah's public-domain tractates), so a frozen sample can be drawn from a shelf with
    few open modern texts. At most `most` texts, the tested registers first, so the file
    stays small enough to commit."""
    allowed = {one.strip() for one in licences if one.strip()}
    also = set(registers)
    mine = [one for one in texts if one.language == code(language)]
    eligible = [
        one
        for one in mine
        if (not allowed or one.licence in allowed)
        and one.words() >= CALIBRATE_LEAST
        and (tested(one) or one.register in also)
    ]
    eligible.sort(key=lambda one: (not tested(one), one.words(), one.key))
    chosen = {one.key for one in eligible[:most]}
    out: list[dict[str, Any]] = []
    for at in range(FOLDS):
        test = [one for one in eligible if fold_of(one.series) == at and one.key in chosen]
        if not test:
            continue
        built = build_language([one for one in mine if fold_of(one.series) != at], language)
        forms = forms_from({"version": VERSION, "languages": {code(language): built}}, language)
        if forms is None:
            continue
        ranked = built["ranked"]
        for one in test:
            tokens, lemmas = page_counts(one, language)
            reach, names = _reach(forms, tokens)
            used = set(lemmas) | set(reach.values())
            top = max(readers, default=0)
            out.append(
                {
                    "register": one.register,
                    "forms": dict(sorted(reach.items())),
                    "names": names,
                    # Each of its lemmas' rank, where it is within the widest reader:
                    # the reader who knows N knows those ranked N or better.
                    "ranks": {
                        lemma: at for at, lemma in enumerate(ranked[:top], start=1) if lemma in used
                    },
                    "tokens": dict(sorted(tokens.items())),
                    "lemmas": dict(sorted(lemmas.items())),
                }
            )
    return {"version": 2, "language": code(language), "readers": list(readers), "texts": out}


def fixture_cases(body: Mapping[str, Any]) -> list[Case]:
    """A frozen sample read back as cases `table` scores."""
    language = str(body.get("language") or "he")
    readers = [int(n) for n in body.get("readers") or READERS]
    out: list[Case] = []
    for text in body.get("texts") or ():
        ranks = {str(k): int(v) for k, v in text["ranks"].items()}
        forms = Forms(
            language=language,
            forms={str(k): str(v) for k, v in text["forms"].items()},
            names=frozenset(text.get("names") or ()),
        )
        out.append(
            Case(
                forms=forms,
                tokens={str(k): int(v) for k, v in text["tokens"].items()},
                lemmas={str(k): int(v) for k, v in text["lemmas"].items()},
                known={n: frozenset(k for k, at in ranks.items() if at <= n) for n in readers},
            )
        )
    return out
