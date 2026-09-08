"""Where a score goes so the next one can be compared with it (targum-internal#163).

Every Hebrew stage has been measured at most once, and none of the numbers survive a
change. `annotate/score.py` fixed the hard half of that for the annotator: it runs the
production path over a hand tagging and produces a scorecard. What it does not do is
remember. A scorecard is written, read once by whoever ran it, and superseded by the next
one, so "did that change make it better" is answered from memory or not at all.

This is the remembering. One append-only file of rows, each one a stage, the system that
ran, the version of it, a metric and a number.

**Rows, not scorecards.** A scorecard is a shape that belongs to the annotator, and
alignment, nikkud and transcription will each want their own. What they have in common is
exactly a row: on this date, this system at this version scored this on this metric over
this many items. Keeping the common part means one file holds every stage and a trend is
a filter rather than a join.

**JSONL, in the repository, appended to.** A score is a number about content rather than
content — `LICENSING.md`'s line, and the reason #163 can keep scores for sources whose
text may never ship. So this file is public, and putting it in git rather than beside the
models means the trend has a history with commits attached: what changed on the day the
number moved is the next question every time, and `git log -p` already answers it.

**Nothing is de-duplicated.** Running the same version twice appends twice, and the two
rows agreeing is the evidence that the harness is deterministic — which is #163's fourth
acceptance criterion and cannot be checked by a file that silently collapses them.
"""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Iterable, Sequence
from datetime import date
from pathlib import Path
from typing import Any

#: In the repository, beside the code that produced the numbers.
DEFAULT = Path("evals/ledger.jsonl")

#: Where a score may not fall below, or rise above, before a PR fails. One file, beside
#: the ledger, so that accepting a worse number is an edit a reviewer sees rather than a
#: threshold argued with somewhere else (targum-internal#163, criterion 5).
FLOORS = Path("evals/floors.json")

#: The stages #163 names, and the chat's two (`grading`, #213; `recast`, #219). Not an
#: enum: a stage nobody has written yet should be recordable the day somebody does,
#: without this file being the thing in the way.
STAGES = (
    "segment",
    "lemma",
    "vocalize",
    "difficulty",
    "align",
    "transcribe",
    "grading",
    "recast",
)


@dataclasses.dataclass(frozen=True)
class Row:
    """One number, and everything needed to know what it is a number about."""

    at: str
    stage: str
    system: str
    version: str
    metric: str
    score: float
    n: int
    corpus: str = ""
    note: str = ""

    def key(self) -> tuple[str, str, str]:
        """What makes two rows comparable: the same measurement, taken twice.

        The system is deliberately *not* in it. In this codebase the annotator's name is
        its version — the name is the cache key, so it changes whenever anything about
        the annotator does — and keying on it would file every change under a heading of
        its own, so nothing would ever be seen to move. What a trend is about is the
        measurement: lemma accuracy on iahltwiki, across whatever produced it.
        """
        return (self.stage, self.corpus, self.metric)

    def as_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


def read(path: Path = DEFAULT) -> list[Row]:
    """Every row, oldest first. A ledger that is not there yet is an empty one."""
    if not path.exists():
        return []
    rows: list[Row] = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        rows.append(Row(**json.loads(line)))
    return rows


def append(rows: Sequence[Row], path: Path = DEFAULT) -> int:
    """Add rows to the end. Returns how many were written.

    Appended rather than rewritten: two people scoring different stages on the same
    afternoon should not be able to lose each other's numbers, and an append of a whole
    line is the one write a filesystem will not tear.
    """
    if not rows:
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as out:
        for row in rows:
            out.write(json.dumps(row.as_dict(), ensure_ascii=False, sort_keys=True) + "\n")
    return len(rows)


def latest(rows: Iterable[Row]) -> dict[tuple[str, str, str], Row]:
    """The most recent row for each measurement, by position in the file.

    By position and not by date, because two runs on one day are ordinary and the file
    is the record of what happened in what order.
    """
    found: dict[tuple[str, str, str], Row] = {}
    for row in rows:
        found[row.key()] = row
    return found


def moved(rows: Sequence[Row], key: tuple[str, str, str]) -> tuple[Row, Row] | None:
    """The last two rows of one measurement that came from different systems, older first.

    The pair a regression is read off. Two rows from the same system at the same version
    are the determinism check rather than a trend, so they are skipped: comparing a
    thing with itself reports no movement and hides the movement before it.
    """
    seen = [row for row in rows if row.key() == key]
    if len(seen) < 2:
        return None
    last = seen[-1]
    for row in reversed(seen[:-1]):
        if (row.system, row.version) != (last.system, last.version):
            return (row, last)
    return None


@dataclasses.dataclass(frozen=True)
class Floor:
    """One line a measurement may not cross, for one system.

    Named for the system because the ledger holds every system ever measured against a
    key — the one the shelf runs and the ones it was compared with — and a comparison run
    of a worse system is a measurement, not a regression. `system` is a prefix, so a
    name that carries a revision after it still matches. One of `at_least` and `at_most`
    is set: a rate wants a floor, a count of failures wants a ceiling.
    """

    stage: str
    corpus: str
    metric: str
    system: str
    at_least: float | None = None
    at_most: float | None = None
    why: str = ""

    def key(self) -> tuple[str, str, str]:
        return (self.stage, self.corpus, self.metric)

    def holds(self, score: float) -> bool:
        if self.at_least is not None and score < self.at_least:
            return False
        return not (self.at_most is not None and score > self.at_most)

    def line(self) -> str:
        if self.at_least is not None:
            return f"at least {self.at_least}"
        return f"at most {self.at_most}"


@dataclasses.dataclass(frozen=True)
class Breach:
    floor: Floor
    row: Row

    def __str__(self) -> str:
        return (
            f"{self.row.stage} {self.row.metric} on {self.row.corpus or '-'}: "
            f"{self.row.system} scored {self.row.score} on {self.row.at}, "
            f"wanted {self.floor.line()}"
        )


def floors(path: Path = FLOORS) -> list[Floor]:
    """Every floor in the file. No file, no floors — and no gate, which is said in the
    table rather than hidden."""
    if not path.exists():
        return []
    loaded = json.loads(path.read_text(encoding="utf-8"))
    out: list[Floor] = []
    for raw in loaded:
        one = Floor(**raw)
        if (one.at_least is None) == (one.at_most is None):
            raise ValueError(f"a floor sets exactly one of at_least and at_most: {raw}")
        out.append(one)
    return out


def breaches(rows: Sequence[Row], limits: Sequence[Floor]) -> list[Breach]:
    """Every floor the ledger's newest matching row crosses.

    Newest by position, among the rows of the floor's key whose system starts with the
    floor's. A floor with no row yet is not a breach: nothing has been measured, and a
    gate that failed on a stage nobody has run would be a gate everybody learns to
    ignore. It is the table's job to say that the floor is waiting.
    """
    found: list[Breach] = []
    for floor in limits:
        matching = [
            row for row in rows if row.key() == floor.key() and row.system.startswith(floor.system)
        ]
        if matching and not floor.holds(matching[-1].score):
            found.append(Breach(floor, matching[-1]))
    return found


def rows_from_scorecard(
    payload: dict[str, Any],
    *,
    stage: str = "lemma",
    at: str | None = None,
    note: str = "",
) -> list[Row]:
    """Turn a `scripts/score_annotation.py` scorecard into ledger rows.

    That script already writes `{"gold": ..., "cards": [...]}` with a `rates` block per
    card, so the numbers exist and the only thing missing was somewhere to put them.
    Reading its output rather than re-running the annotator is deliberate: scoring loads
    a BERT model and takes minutes, and nothing about recording a number should need one.

    A rate of `None` is not a score of zero — it is a base of zero, a metric that had
    nothing to measure — so it is left out rather than written down as a nought that a
    trend would later read as a collapse.
    """
    when = at or date.today().isoformat()
    rows: list[Row] = []
    for card in payload.get("cards", []):
        system = str(card.get("annotator", "?"))
        version = str(card.get("version") or system)
        corpus = str(card.get("corpus", ""))
        paired = int(card.get("paired") or 0)
        for metric, score in (card.get("rates") or {}).items():
            if score is None:
                continue
            rows.append(
                Row(
                    at=when,
                    stage=stage,
                    system=system,
                    version=version,
                    metric=str(metric),
                    score=float(score),
                    n=paired,
                    corpus=corpus,
                    note=note,
                )
            )
    return rows


def table(rows: Sequence[Row]) -> str:
    """The ledger as one table: where each measurement stands, and what it did last.

    Movement is shown against the last different version, so a re-run says nothing and a
    change says how much. Blank where there is only one version to go on, because a first
    measurement has not moved — it has arrived.
    """
    if not rows:
        return "No scores recorded yet."
    lines = [f"{'stage':11} {'metric':22} {'corpus':14} {'score':>8} {'moved':>9}  system"]
    for key, row in sorted(latest(rows).items()):
        pair = moved(rows, key)
        shift = ""
        if pair:
            delta = row.score - pair[0].score
            shift = f"{delta:+.4f}"
        lines.append(
            f"{row.stage:11} {row.metric:22} {row.corpus:14} "
            f"{row.score:8.4f} {shift:>9}  {row.system[:44]}"
        )
    return "\n".join(lines)
