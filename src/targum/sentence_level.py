"""How hard a sentence is, not how hard a book is (targum-internal#320).

`annotate/difficulty.py` gives a text one number, and a shelf sorted on one number offers
easy books and never the readable chapter of a hard one. This asks the question per
sentence instead: *how much Hebrew does a learner need to follow this one?* — answered on
the fixed ulpan ladder `level.ULPAN` already writes down, so it never needs a reader
present and is asked once per sentence for everybody.

**Who answers.** TypeSafe's Jev (`jev.py`), as a Score over the rungs. Jev picks; it does
not count. So nothing here asks it how many words a sentence has or how many it knows —
`coverage.py` counts that, correctly, and this is the other question: whether the
sentence *reads*. The unit of work is a passage of a few sentences as the state, with one
question per sentence, because a sentence alone has no context and a whole text does not
fit the ~32k-token budget.

**What is kept.** Per sentence, keyed by `key()` — a hash of its text, so the answer
follows the sentence into every copy of the text on every shelf and falls away the day
the sentence is edited — three numbers: the rung the model put most weight on, the
score (the probability-weighted rung, which is what `readable` reads) and the model's
confidence. The file is library data, so it is private like the catalogue: it is written
on the laptop by `scripts/sentence_levels.py`, never committed, and reaches the box beside
the catalogue (`deploy/deploy.sh`). A box without it answers exactly as before.

**The first reader of it** is `suggest_next`, which can now point at a section of a harder
text that reads at the reader's rung — `best_passage` — rather than only rank whole texts.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from .ids import short_hash
from .level import ULPAN

#: What each rung reads, said as the situation a sentence is in rather than as a degree
#: — the model judges every level on its own and never sees the neighbours, so "harder
#: than the last" would mean nothing to it. One entry per `level.ULPAN` rung, in order,
#: and one past the top for the sentence nobody on the ladder follows. A test holds the
#: names to the ladder so the two cannot drift.
#:
#: Plain on purpose. In #318 a description that narrated a position ("the last
#: syllable") moved the score further than the whole gap it was measuring, so nothing
#: here says "easier" or "harder", and a wording change wants a number beside it.
#:
#: **Measured against one alternative, 2026-09-27**, on the same 471 sentences of nine
#: texts. These situations put the scenes at a mean of 1.3-1.9 and spread the shelf to
#: Mishnah Berakhot at 7.4, Genesis (5.9) below Psalms (6.8). The alternative said only
#: how common the words were ("Every word is a common everyday word, of the thousand or
#: so...") and told the model to judge by dictionary form: it squeezed the shelf into
#: 2.1-5.9, clustered the answers on three levels, and put "בוקר טוב. באתי לחדש דרכון"
#: at bet plus. What these cost is that the register words ("archaic", "rabbinic") pull
#: scripture up: Genesis 1:1 lands at hey with a confidence of 0.13.
LEVELS: tuple[tuple[str, str], ...] = (
    (
        "aleph",
        "Uses only the few hundred commonest everyday words — family, food, home, "
        "numbers, simple verbs — in a short plain sentence. A beginner in a first ulpan "
        "course follows it.",
    ),
    (
        "aleph plus",
        "Uses everyday words of home, work, shopping and travel, about a thousand of "
        "them, in simple sentences. A learner who has finished a first ulpan course "
        "follows it.",
    ),
    (
        "bet",
        "Uses the common words of daily life and simple stories, about two thousand, "
        "with ordinary verb forms. A second-course ulpan learner follows it.",
    ),
    (
        "bet plus",
        "Uses the general words of easy news and plain storytelling, about three "
        "thousand, and some longer sentences.",
    ),
    (
        "gimel",
        "Uses the words of newspapers, opinions and ordinary books, about five thousand. "
        "An intermediate learner follows it.",
    ),
    (
        "dalet",
        "Uses the rich vocabulary of journalism, modern fiction and essays, about seven "
        "thousand words.",
    ),
    (
        "hey",
        "Uses literary, formal or academic words, about ten thousand. An advanced learner "
        "follows it.",
    ),
    (
        "vav",
        "Uses rare, literary or classical words, about twelve thousand. Only a reader "
        "close to native follows it.",
    ),
    (
        "beyond",
        "Uses archaic, poetic, rabbinic or specialist words that even a native reader of "
        "modern Hebrew would look up.",
    ),
)

#: The same ladder with the register taken off its top rungs (targum-internal#320,
#: 2026-09-28): hey, vav and beyond say how rare their words are and no longer call them
#: literary, classical, archaic, poetic or rabbinic. The rungs below are `LEVELS`' own,
#: word for word, so the only thing that differs is what the top of the ladder says old
#: Hebrew is. Measured on a sample of scripture and modern prose matched on coverage
#: (`scripts/sentence_bias.py`); switchable, and not the default.
WITHOUT_REGISTER: tuple[tuple[str, str], ...] = (
    *LEVELS[:6],
    (
        "hey",
        "Uses formal or academic words, about ten thousand. An advanced learner follows it.",
    ),
    (
        "vav",
        "Uses rare words, about twelve thousand. Only a reader close to native follows it.",
    ),
    (
        "beyond",
        "Uses words so rare or specialised that even a native reader of Hebrew would look them up.",
    ),
)

#: The wordings a sentence can be asked in, by name. An answer is only comparable with
#: answers asked in the same wording, so the name travels with them.
PROMPTS: dict[str, tuple[tuple[str, str], ...]] = {
    "situations": LEVELS,
    "without-register": WITHOUT_REGISTER,
}
#: The wording the library was scored in, and the one asked unless another is named.
PROMPT = "situations"

#: The level past the ladder's top.
BEYOND = len(ULPAN)

INSTRUCTIONS = (
    "A learner of Hebrew is reading the passage at `passage`. This sentence is from it: "
    "{sentence}\n"
    "How much Hebrew vocabulary does a learner need to follow this sentence without a "
    "dictionary?"
)

#: How many sentences share one request. A passage is the state its sentences share, and
#: each extra question on the same state is close to free (targum-internal#309).
PER_REQUEST = 8

#: And how long the shared state may run, in characters, so a paragraph of very long
#: sentences is split rather than sent whole against the token budget.
STATE_CHARS = 2400

#: Where the kept answers are read from on the box and on the laptop, in the same order
#: `catalogue_path` and `exemplars.pool_path` keep: a path named in the environment is
#: the path, found or not.
ENV = "TARGUM_SENTENCE_LEVELS"
PLACES = (
    Path.home() / ".targum" / "sentence-difficulty" / "sentence-levels.json",
    Path("/etc/targum/sentence-levels.json"),
)

#: A passage is offered when this share of its measured sentences reads at the rung.
FLOOR = 0.8
#: And only a section of at least this many sentences — one easy verse is not a passage.
LEAST = 3
#: A section counts as measured when this share of its sentences has an answer.
MEASURED = 0.8


def key(text: str) -> str:
    """The sentence's identity: its text, normalised, hashed. Sixteen hex characters is
    comfortably unique across a library of a few hundred thousand sentences."""
    return short_hash(text, 16)


@dataclass(frozen=True)
class Level:
    """What was answered for one sentence."""

    #: The rung the model put most probability on, 0 (aleph) to `BEYOND`.
    rung: int
    #: The probability-weighted rung, which can fall between two.
    score: float
    confidence: float

    def readable(self, at: int) -> bool:
        """Whether a reader at rung `at` follows it: the weighted rung rounds to theirs or
        below. The weighted rung rather than the top pick, so a sentence the model was
        torn about leans where its probability leans — confidence spent, not ignored."""
        return self.score <= at + 0.5

    def row(self) -> list[float]:
        return [self.rung, round(self.score, 2), round(self.confidence, 2)]


def answered(answer: dict[str, Any]) -> Level | None:
    """A Score answer as a `Level`, or None where it is not one."""
    probabilities = answer.get("probabilities") or {}
    try:
        weights = {int(level): float(p) for level, p in probabilities.items()}
        score = float(answer["score"])
    except (KeyError, TypeError, ValueError):
        return None
    if not weights:
        return None
    rung = max(weights, key=lambda level: (weights[level], -level))
    return Level(rung, score, float(answer.get("confidence") or 0.0))


# -- asking ---------------------------------------------------------------------------


@dataclass
class Chunk:
    """Sentences asked together, and the passage they are asked against."""

    keys: list[str] = field(default_factory=list)
    sentences: list[str] = field(default_factory=list)

    @property
    def passage(self) -> str:
        return " ".join(self.sentences)


def chunks(
    blocks: Iterable[list[str]], show: Callable[[str], str] = lambda text: text
) -> Iterator[Chunk]:
    """Consecutive sentences grouped into requests, a block at a time.

    `blocks` is the text's own paragraphs (or verses), each a list of sentence texts as
    stored — the key is taken from that form. `show` is the form sent, which is where a
    caller takes the chanting marks off. A chunk never splits a paragraph unless the
    paragraph alone is too long, and closes once it holds `PER_REQUEST` sentences or
    `STATE_CHARS` characters — so a book of verses goes eight verses to a request and a
    paragraph of prose goes whole.
    """
    current = Chunk()
    for stored in blocks:
        pairs = [(key(text), show(text)) for text in stored if text.strip()]
        if not pairs:
            continue
        size = sum(len(text) for _, text in pairs)
        if current.sentences and (
            len(current.sentences) + len(pairs) > PER_REQUEST
            or len(current.passage) + size > STATE_CHARS
        ):
            yield current
            current = Chunk()
        for sentence_key, text in pairs:
            if current.sentences and (
                len(current.sentences) >= PER_REQUEST
                or len(current.passage) + len(text) > STATE_CHARS
            ):
                yield current
                current = Chunk()
            current.keys.append(sentence_key)
            current.sentences.append(text)
    if current.sentences:
        yield current


def question(sentence: str, prompt: str = PROMPT) -> dict[str, Any]:
    return {
        "type": "score",
        "instructions": INSTRUCTIONS.format(sentence=sentence),
        "criteria": [description for _, description in PROMPTS[prompt]],
    }


def request(
    chunk: Chunk, asking: set[str] | None = None, prompt: str = PROMPT
) -> tuple[Any, dict[str, Any]]:
    """The state and the questions for one chunk: the whole passage as state, and a
    question for each sentence in `asking` (every one, by default), in the wording named
    `prompt`. A sentence already answered somewhere else in the library stays in the
    passage as context and is not asked, or paid for, twice."""
    questions = {
        k: question(text, prompt)
        for k, text in zip(chunk.keys, chunk.sentences, strict=True)
        if asking is None or k in asking
    }
    return {"passage": chunk.passage}, questions


# -- reading what was kept ------------------------------------------------------------


def path() -> Path | None:
    named = os.environ.get(ENV, "").strip()
    if named:
        return Path(named) if Path(named).is_file() else None
    for place in PLACES:
        if place.is_file():
            return place
    return None


def write(levels: dict[str, Level], to: Path, model: str, prompt: str = PROMPT) -> None:
    """The kept answers, whole or not at all: a file beside the target, then a rename."""
    to.parent.mkdir(parents=True, exist_ok=True)
    body = {
        "version": 1,
        "model": model,
        "prompt": prompt,
        "levels": [name for name, _ in PROMPTS[prompt]],
        "sentences": {k: level.row() for k, level in sorted(levels.items())},
    }
    temporary = to.with_name(to.name + ".tmp")
    temporary.write_text(json.dumps(body, ensure_ascii=False, separators=(",", ":")), "utf-8")
    temporary.replace(to)


@lru_cache(maxsize=2)
def _load(where: str, changed: float) -> dict[str, Level]:
    try:
        raw = json.loads(Path(where).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    out: dict[str, Level] = {}
    for k, row in (raw.get("sentences") or {}).items():
        try:
            out[str(k)] = Level(int(row[0]), float(row[1]), float(row[2]))
        except (IndexError, TypeError, ValueError):
            continue
    return out


def load() -> dict[str, Level]:
    """Every kept answer, read once per change of the file. Empty where there is none."""
    where = path()
    if where is None:
        return {}
    try:
        changed = where.stat().st_mtime
    except OSError:
        return {}
    return _load(str(where), changed)


# -- the first reader: a passage that reads at a rung -------------------------------


@dataclass(frozen=True)
class Passage:
    number: int
    title: str
    file: str
    sentences: int
    measured: int
    readable: int

    @property
    def share(self) -> float:
        return self.readable / self.measured if self.measured else 0.0


def passages(folder: Path, at: int, levels: dict[str, Level] | None = None) -> list[Passage]:
    """Every section of a built text, with how many of its sentences read at rung `at`.

    The sections are the reader's own (`render.builder.split_sections`), so a passage's
    file is the page it opens on. Counting is here, in code: the model was asked about
    one sentence at a time and never how many.
    """
    levels = load() if levels is None else levels
    if not levels:
        return []
    try:
        changed = (folder / "segments.json").stat().st_mtime
    except OSError:
        return []
    return [
        Passage(number, title, file, len(keys), *_counted(keys, levels, at))
        for number, title, file, keys in _sections(str(folder), changed)
    ]


def _counted(keys: list[str], levels: dict[str, Level], at: int) -> tuple[int, int]:
    measured = readable = 0
    for k in keys:
        level = levels.get(k)
        if level is None:
            continue
        measured += 1
        readable += level.readable(at)
    return measured, readable


@lru_cache(maxsize=256)
def _sections(folder: str, changed: float) -> list[tuple[int, str, str, list[str]]]:
    """A built text's sections as (number, title, file, sentence keys), headings left
    out. Keyed on the file's modification time, so a rebuilt text is read again."""
    from .models import BlockKind, SegmentedDocument, read_artifact
    from .render.builder import split_sections

    segmented = read_artifact(SegmentedDocument, Path(folder) / "segments.json")
    if segmented is None:
        return []
    text = {
        segment.id: segment.text
        for segment in segmented.segments
        if segment.kind not in (BlockKind.heading, BlockKind.byline)
    }
    return [
        (
            section.number,
            section.title,
            section.filename,
            [key(text[sid]) for sid in section.segment_ids if sid in text],
        )
        for section in split_sections(segmented)
    ]


def best_passage(
    folder: Path, at: int, levels: dict[str, Level] | None = None
) -> tuple[Passage, float] | None:
    """The section of a harder text that reads best at rung `at`, and the whole text's
    own share for comparison — or None where the text already reads whole (nothing to
    point into), where too little of it is measured, or where no section reaches `FLOOR`.
    The first such section wins a tie, because the start of a book is where a reader
    would rather begin."""
    found = passages(folder, at, levels)
    measured = sum(one.measured for one in found)
    if not measured:
        return None
    whole = sum(one.readable for one in found) / measured
    if whole >= FLOOR:
        return None
    fit = [
        one
        for one in found
        if one.sentences >= LEAST
        and one.measured >= MEASURED * one.sentences
        and one.share >= FLOOR
    ]
    if not fit:
        return None
    return max(fit, key=lambda one: (one.share, -one.number)), whole
