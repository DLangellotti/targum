"""How far along each language is, as a promise checked against the facts.

design.md §12, "A badge is a promise, checked" (2026-10-12); targum-internal#445.

A language in the menu wears one of three words — Experimental, Alpha, Beta — and each is
a promise to the reader, not a note about how targum was built:

- **Experimental:** we read it and translate it. Nothing else is promised.
- **Alpha:** the learning loop works, and a person has checked it. Every word has a
  lemma above its floor, there is a ladder of levels, the chat talks it, a voice reads
  it, the shelf has texts and recordings at every level a learner sits at, David has
  read ten texts end to end as a learner, and every hard spot on the language's list is
  covered: computed per word, shown on a card or lens, and measured against gold with a
  floor.
- **Beta:** what we would let a stranger pay for, unattended. Alpha plus a bigger shelf
  with a second medium and a feed that grows by itself, the box building a new text with
  no laptop in the loop, chat evals in the language with floors, a practice for every
  hard spot, and no blocker on the known-issues list.

The two tables that used to say this disagreed — `translate/prompts.py` called Hebrew
"alpha" and the rest "R&D", `lang.js` called Hebrew Beta and three others Alpha — and
neither could be checked. This module is the one place the claim is made (`DECLARED`),
and `tests/test_stages.py` fails when a claim outruns the facts (`earned`). A promotion
is a commit here; a regression anywhere in the pipeline fails CI.

**Hebrew is the one exception, by decision and with a date** (`KEPT`). Under the letter
of the rule it is Experimental today — one of its seven hard spots has no gold
set yet — and it keeps the Beta it wore before the standard while its measurements, its
read-through record and its practices catch up. The test prints its shortfall instead of
failing on it, and `targum stages` says "Beta, kept". Nothing else may be added to `KEPT`
without a design.md entry first.

The shelf is counted on the library's own ruler (`levelmap`), which places a text on
three levels. CEFR is finer, and the floors are stated in CEFR by the mapping in
`levelmap.cefr_rows`: A1 is a text meeting the Easy spec in full, A2 the rest of Easy,
B1 is Simplified, and Native is counted as one level, B2 and up, until there is a better
ruler than a median nobody measured (David, 2026-10-12). The counts a test reads are the
committed snapshot in `evals/shelf.json`, written by `targum stages --measure` from a
catalogue and the builds on disk, the way the evals ledger is committed and re-run.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum
from pathlib import Path
from typing import Any

from .translate.prompts import READING


class Stage(StrEnum):
    """The three words, in order. A language wears the highest it has earned."""

    experimental = "experimental"
    alpha = "alpha"
    beta = "beta"

    @property
    def rank(self) -> int:
        return ORDER.index(self)

    def __lt__(self, other: object) -> bool:
        return isinstance(other, Stage) and self.rank < other.rank

    def __ge__(self, other: object) -> bool:
        return isinstance(other, Stage) and self.rank >= other.rank


ORDER: tuple[Stage, ...] = (Stage.experimental, Stage.alpha, Stage.beta)

#: The levels the shelf floors are stated at. "B2+" is Native counted as one level.
CEFR_LEVELS: tuple[str, ...] = ("A1", "A2", "B1", "B2+")

#: The levels a learner sits at, which Alpha must furnish.
LEARNER_LEVELS: tuple[str, ...] = ("A1", "A2", "B1", "B2+")


@dataclass(frozen=True)
class Floor:
    """A shelf floor at one level: texts, and texts with a recording."""

    texts: int
    recordings: int


#: Shelf floors per stage and level, set 2026-10-12 against the measured Hebrew shelf once
#: `scripts/measure_difficulty.py` had written `sentence` for the catalogue (David,
#: 2026-10-11: Beta just under Hebrew, Alpha about two fifths of Beta). Hebrew's thinnest
#: level held 95 texts (A2) and 37 recordings (B2+); one floor serves every level.
SHELF: dict[Stage, dict[str, Floor]] = {
    Stage.alpha: {level: Floor(36, 14) for level in LEARNER_LEVELS},
    Stage.beta: {level: Floor(90, 35) for level in CEFR_LEVELS},
}


@dataclass(frozen=True)
class HardSpot:
    """One of a language's known difficulties, and how targum covers it.

    Covered means all three: `computed` names what the pipeline computes per word or
    line; `shown` names where the reader sees it; `floor` names the (system, corpus,
    metric) in `evals/floors.json` that measures it against gold. A spot with no floor is
    not covered, however well it is drawn.
    """

    name: str
    #: "feature:Case" (a kept morphological feature), "stage:stress" (a pipeline stage),
    #: "dicta:binyan" (derived by the Hebrew annotator), "lookup:openrussian:partners",
    #: or "none".
    computed: str
    #: "card", "lens", "marks" (in the text), "pieces" (the pieces line), or "none".
    shown: str
    floor: tuple[str, str, str] | None = None
    #: Where the research (targum-internal, research/hard-spots-2026-10-11) says a lens
    #: rather than a card is the right surface, because feedback does not fix it.
    lens: bool = False

    @property
    def computed_at_all(self) -> bool:
        return self.computed != "none"

    @property
    def shown_at_all(self) -> bool:
        return self.shown != "none"


@dataclass(frozen=True)
class Kept:
    """A badge kept by decision rather than earned, with its date and its review date."""

    stage: Stage
    since: date
    review: date
    why: str


#: The claim. One word per language targum reads; a language not here wears nothing.
DECLARED: dict[str, Stage] = {
    "he": Stage.beta,
    "ru": Stage.experimental,
    "it": Stage.experimental,
    "fr": Stage.experimental,
    "arc": Stage.experimental,
    "yi": Stage.experimental,
}

#: The one exception the test tolerates (David, 2026-10-12). See the module docstring.
KEPT: dict[str, Kept] = {
    "he": Kept(
        Stage.beta,
        since=date(2026, 10, 12),
        review=date(2026, 12, 31),
        why=(
            "the language targum was built for, read by its alpha readers since August; "
            "measured on its own terms until the standard's evals, read-through record "
            "and practices land"
        ),
    ),
}

_DICTA = "dicta/dicta-il/dictabert-joint"
_MENAKED = "dicta-il/dictabert-large-char-menaked"

#: Each language's hard spots, ranked by how much they block a reader, from the research
#: of 2026-10-11 (targum-internal, research/hard-spots-2026-10-11). Five to seven each.
#: The floors named here must exist in `evals/floors.json` for the spot to count as
#: covered; `tests/test_stages.py` checks that.
HARD_SPOTS: dict[str, tuple[HardSpot, ...]] = {
    "he": (
        HardSpot(
            "root and binyan", "dicta:binyan", "card", (_DICTA, "iahltknesset", "binyan_accuracy")
        ),
        HardSpot(
            "nikkud and homographs",
            "stage:vocalize",
            "marks",
            (_MENAKED, "dicta-modern", "word_exact"),
        ),
        HardSpot(
            "tense, person and the participle",
            "feature:Tense",
            "card",
            (_DICTA, "iahltknesset", "tense_accuracy"),
        ),
        HardSpot(
            "governed prepositions and et",
            "feature:Case",
            "pieces",
            None,
            lens=True,
        ),
        HardSpot(
            "gender and number agreement",
            "feature:Gender",
            "card",
            (_DICTA, "iahltknesset", "gender_accuracy"),
        ),
        HardSpot(
            "construct state and definiteness",
            "feature:Definite",
            "card",
            (_DICTA, "iahltknesset", "construct_precision"),
        ),
        HardSpot(
            "stress and pronunciation",
            "stage:stress",
            "marks",
            ("stress-rule/1", "tanakh-taamim-v2", "rule_accuracy"),
        ),
    ),
    "ru": (
        HardSpot(
            "cases with their governing preposition",
            "feature:Case",
            "lens",
            ("model-lemma", "ud-ru-syntagrus", "case_accuracy"),
        ),
        HardSpot(
            "aspect",
            "feature:Aspect",
            "card",
            ("model-lemma", "ud-ru-syntagrus", "aspect_accuracy"),
        ),
        HardSpot(
            "stress", "stage:stress", "marks", ("stress", "wiktionary-ru", "stress_precision")
        ),
        HardSpot("verbs of motion", "none", "none", None),
        HardSpot(
            "gender and animacy",
            "feature:Gender",
            "card",
            ("model-lemma", "ud-ru-syntagrus", "gender_accuracy"),
        ),
        HardSpot("word order", "none", "none", None, lens=True),
        HardSpot("participles", "feature:VerbForm", "card", None),
    ),
    "fr": (
        HardSpot(
            "gender", "feature:Gender", "card", ("model-lemma", "ud-fr-gsd", "gender_accuracy")
        ),
        HardSpot(
            "object clitics, role and antecedent",
            "feature:Role",
            "card",
            ("model-lemma", "ud-fr-gsd", "role_accuracy"),
        ),
        HardSpot("passé composé against imparfait", "feature:Tense", "card", None),
        HardSpot(
            "liaison and the sound-spelling gap",
            "stage:said",
            "pieces",
            ("morphalou-3.1+gruut-liaison", "pd-fr-drafted", "liaison_precision"),
        ),
        HardSpot("false friends", "none", "none", None),
        HardSpot(
            "subjunctive", "feature:Mood", "card", ("model-lemma", "ud-fr-gsd", "mood_accuracy")
        ),
        HardSpot("register: ne-drop and on/nous", "none", "none", None),
    ),
    "it": (
        HardSpot(
            "gender, agreement and the article system",
            "feature:Gender",
            "card",
            ("model-lemma", "ud-it-isdt", "gender_accuracy"),
        ),
        HardSpot("clitics and clusters", "none", "none", None),
        HardSpot(
            "the past system: essere/avere and the passato remoto", "feature:Tense", "card", None
        ),
        HardSpot(
            "subjunctive", "feature:Mood", "card", ("model-lemma", "ud-it-isdt", "mood_accuracy")
        ),
        HardSpot("articulated prepositions", "none", "none", None),
        HardSpot("stress and gemination", "none", "none", None),
        HardSpot("non-canonical mapping: piacere and si", "none", "none", None),
    ),
    # No list yet: a list is written when somebody who reads the language can review it.
    "yi": (),
    "arc": (),
}

#: Which languages the box can build a new text in with no laptop in the loop. A
#: language whose lemmas are bought by the model is cache-only on the box (memory
#: 2026-09-17): a text built on the laptop ships its reader, not its cache entries.
#: Aramaic has no lemmatiser at all.
BUILDS_UNATTENDED: frozenset[str] = frozenset({"he"})

#: Which languages have chat evals *in the language* with floors in `evals/floors.json`.
#: The `recast` rows for `tatoeba-ru` and `ntrex-128-in-ru` measure Hebrew recast for a
#: Russian-reading account, not Russian talk; Russian's own are targum-internal#286.
CHAT_EVALS: frozenset[str] = frozenset({"he"})

#: What grows a language's shelf without anybody's hand: the parasha, the daily and the
#: weekly for Hebrew; the weekly's Russian edition for Russian.
GROWING: dict[str, str] = {"he": "parasha, daily, weekly", "ru": "weekly, Russian edition"}

#: Where the committed shelf snapshot lives, and where the floors do.
SHELF_SNAPSHOT = Path(__file__).resolve().parent.parent.parent / "evals" / "shelf.json"
FLOORS = Path(__file__).resolve().parent.parent.parent / "evals" / "floors.json"
LEDGER = Path(__file__).resolve().parent.parent.parent / "evals" / "ledger.jsonl"


@dataclass
class Facts:
    """What is true of a language, read off the code, the ledger and the shelf snapshot."""

    language: str
    reads: bool
    #: None where no lemma floors are named for the language; otherwise whether every
    #: named floor holds against the committed ledger.
    lemmatiser: bool | None
    ladder: bool
    talk: bool
    voice: bool
    #: Counts per CEFR level, or None where no snapshot covers the language.
    shelf: dict[str, Floor] | None
    #: Hard spot name -> covered.
    covered: dict[str, bool] = field(default_factory=dict)
    #: Hard spot name -> a practice is registered for it.
    practices: dict[str, bool] = field(default_factory=dict)
    read_through: bool = False
    known_issues: bool = False
    builds_unattended: bool = False
    chat_evals: bool = False
    second_medium: bool | None = None
    growing: bool = False
    no_blocker: bool = False


def reading_codes() -> set[str]:
    return {code for code, _ in READING}


def wears(language: str) -> Stage | None:
    """The word a language wears, or None for one not in the table."""
    return DECLARED.get(_code(language))


def _code(language: str) -> str:
    return (language or "").split("-")[0].lower()


def _floors_for(language: str, floors: Iterable[Any]) -> list[Any]:
    """The lemma floors that measure this language's lemmatiser."""
    corpora = {
        "he": ("iahltwiki", "iahltknesset"),
        "fr": ("ud-fr-gsd", "ud-fr-gsd-curly"),
        "ru": ("ud-ru-syntagrus",),
        "it": ("ud-it-isdt", "ud-it-isdt-curly"),
        "yi": ("ud-yi-yitb",),
    }.get(language, ())
    return [
        floor
        for floor in floors
        if floor.stage == "lemma"
        and floor.corpus in corpora
        and floor.metric in {"lemma", "lemma_accuracy", "token_recall", "pos", "upos_accuracy"}
    ]


def _lemmatiser_holds(language: str, floors: list[Any], rows: list[Any]) -> bool | None:
    from . import evals

    mine = _floors_for(language, floors)
    if not mine:
        return None
    return not evals.breaches(rows, mine)


def _covered(spot: HardSpot, floors: Iterable[Any]) -> bool:
    if spot.floor is None or not spot.computed_at_all or not spot.shown_at_all:
        return False
    system, corpus, metric = spot.floor
    # A floor names a system by prefix, as `evals.breaches` matches it.
    return any(
        system.startswith(f.system) and f.corpus == corpus and f.metric == metric for f in floors
    )


def read_shelf(path: Path = SHELF_SNAPSHOT) -> dict[str, dict[str, Floor]]:
    """The committed shelf snapshot: language -> CEFR level -> counts."""
    if not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    out: dict[str, dict[str, Floor]] = {}
    for language, levels in (raw.get("languages") or {}).items():
        out[language] = {
            level: Floor(int(counts.get("texts", 0)), int(counts.get("recordings", 0)))
            for level, counts in levels.items()
        }
    return out


def write_shelf(
    counts: Mapping[str, Mapping[str, Floor]], *, measured: date, path: Path = SHELF_SNAPSHOT
) -> None:
    """The snapshot `targum stages --measure` writes, dated, for the test to read."""
    payload = {
        "measured": measured.isoformat(),
        "levels": list(CEFR_LEVELS),
        "languages": {
            language: {
                level: {"texts": floor.texts, "recordings": floor.recordings}
                for level, floor in levels.items()
            }
            for language, levels in sorted(counts.items())
        },
    }
    path.write_text(json.dumps(payload, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


def _practices(language: str) -> dict[str, bool]:
    """Which hard spots have a practice registered (targum-internal#440). None yet: the
    registry is that card's to build, and this reads it when it exists."""
    try:
        from . import practices  # type: ignore[attr-defined]
    except ImportError:
        return {spot.name: False for spot in HARD_SPOTS.get(language, ())}
    registered = getattr(practices, "REGISTERED", {}).get(language, {})
    return {spot.name: bool(registered.get(spot.name)) for spot in HARD_SPOTS.get(language, ())}


def facts(
    language: str,
    *,
    floors: list[Any] | None = None,
    rows: list[Any] | None = None,
    shelf: Mapping[str, Mapping[str, Floor]] | None = None,
) -> Facts:
    """Everything the standard asks of a language, read off the code and the committed
    files. Nothing here fetches or spends."""
    from . import evals
    from .chat.hebrew import TALKED
    from .level import ladder_for
    from .speech import SPOKEN

    code = _code(language)
    limits = floors if floors is not None else evals.floors(FLOORS)
    ledger = rows if rows is not None else evals.read(LEDGER)
    snapshot = shelf if shelf is not None else read_shelf()
    spots = HARD_SPOTS.get(code, ())
    counts = snapshot.get(code)
    return Facts(
        language=code,
        reads=code in reading_codes(),
        lemmatiser=_lemmatiser_holds(code, limits, ledger),
        ladder=ladder_for(code) is not None,
        talk=code in TALKED,
        voice=code in SPOKEN,
        shelf=dict(counts) if counts is not None else None,
        covered={spot.name: _covered(spot, limits) for spot in spots},
        practices=_practices(code),
        # The read-through and the known-issues list live in the private record in
        # targum-internal (languages/<code>.md), which is advisory (David, 2026-10-12):
        # nothing public can read it, so both are false here until a public fact exists.
        read_through=False,
        known_issues=False,
        builds_unattended=code in BUILDS_UNATTENDED,
        chat_evals=code in CHAT_EVALS,
        second_medium=(
            None if counts is None else any(level.recordings > 0 for level in counts.values())
        ),
        growing=code in GROWING,
        no_blocker=False,
    )


def _shelf_short(counts: Mapping[str, Floor] | None, wanted: Mapping[str, Floor]) -> list[str]:
    if counts is None:
        return ["shelf not measured (no snapshot in evals/shelf.json)"]
    short: list[str] = []
    for level, floor in wanted.items():
        have = counts.get(level, Floor(0, 0))
        if have.texts < floor.texts:
            short.append(f"shelf at {level}: {have.texts} texts of {floor.texts}")
        if have.recordings < floor.recordings:
            short.append(f"shelf at {level}: {have.recordings} recordings of {floor.recordings}")
    return short


def shortfall(known: Facts, stage: Stage) -> list[str]:
    """What stands between a language and a stage, in words. Empty means earned."""
    if stage is Stage.experimental:
        return [] if known.reads else ["not a language targum reads"]
    missing: list[str] = []
    if not known.reads:
        missing.append("not a language targum reads")
    if known.lemmatiser is None:
        missing.append("no lemma floors named for it")
    elif not known.lemmatiser:
        missing.append("a lemma floor is breached")
    if not known.ladder:
        missing.append("no ladder of levels")
    if not known.talk:
        missing.append("the chat does not talk it")
    if not known.voice:
        missing.append("no voice reads it")
    missing.extend(_shelf_short(known.shelf, SHELF[Stage.alpha]))
    if not known.read_through:
        missing.append("no read-through on record")
    spots = HARD_SPOTS.get(known.language, ())
    if not spots:
        missing.append("no hard-spot list")
    for spot in spots:
        if not known.covered.get(spot.name):
            missing.append(f"hard spot not covered: {spot.name}")
    if not known.known_issues:
        missing.append("no known-issues list")
    if stage is Stage.alpha:
        return missing
    missing.extend(_shelf_short(known.shelf, SHELF[Stage.beta]))
    if known.second_medium is not True:
        missing.append("no second medium on the shelf")
    if not known.growing:
        missing.append("nothing grows the shelf by itself")
    if not known.builds_unattended:
        missing.append("the box cannot build a new text unattended")
    if not known.chat_evals:
        missing.append("no chat evals in the language")
    for spot in spots:
        if not known.practices.get(spot.name):
            missing.append(f"no practice for: {spot.name}")
    if not known.no_blocker:
        missing.append("the known-issues list is not read for blockers")
    return missing


def earned(known: Facts) -> Stage | None:
    """The highest stage every criterion of which holds, or None for a language targum
    does not read at all."""
    best: Stage | None = None
    for stage in ORDER:
        if shortfall(known, stage):
            break
        best = stage
    return best


def kept(language: str) -> Kept | None:
    return KEPT.get(_code(language))


def label_key(stage: Stage) -> str:
    """The string key for the word a reader sees."""
    return f"lang.status.{stage.value}"


def report(language: str, **over: Any) -> dict[str, Any]:
    """One language's row for `targum stages`: declared, kept, earned, shortfall."""
    known = facts(language, **over)
    worn = wears(language)
    held = kept(language)
    got = earned(known)
    return {
        "language": known.language,
        "declared": worn.value if worn else "",
        "kept": held is not None,
        "review": held.review.isoformat() if held else "",
        "earned": got.value if got else "",
        "shortfall": shortfall(known, worn) if worn else [],
    }
