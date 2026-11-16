"""The rubric a chat reply is held to on a set of learner lines (targum-internal#644).

A case is one line a learner sends, and what the contract says the reply must do with it
(`chat/hebrew.py`, the French contract): say a right line back as it was written, with no
`~ ` line, and fix a wrong one, with one `~ ` line saying why. Every check here is read
off the reply by the contract's own parser (`hebrew.pairs`), with no model judging it, so
a run costs the chat's turns and nothing else, and two people reading the same reply
score it the same way.

Three kinds of case:

- **correct**: written right. The recast must not be shown a `~ ` line, should say the
  line back unchanged, and where the line says the reader is a woman (*je suis allée*,
  *contente*), must keep it: "never change the gender of the reader's own words".
- **register**: spoken French that is right in its register, *je sais pas*, *on va au
  cinéma* (design.md §12, D5, 2026-11-05: register, not error). No `~ ` line.
- **error**: a learner's mistake of a kind the contract names (the auxiliary, the
  participle's agreement, an adjective's gender, an article, elision, an accent, a calque,
  English word order). Fixed means the recast no longer says the error and, where the
  case lists fixes, says one of them. A `~ ` line must be shown under it.

Words are compared whole, lowercased, with one apostrophe and one kind of space, so *est
vert* is not found inside *est verte*.
"""

from __future__ import annotations

import json
import re
import unicodedata
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

#: The French set, in the repository: hand-written, targum's own.
FRENCH_CASES = Path(__file__).resolve().parents[3] / "evals" / "chat-fr-cases.jsonl"

KINDS = ("correct", "register", "error")


@dataclass(frozen=True)
class Case:
    id: str
    sent: str
    kind: str
    spot: str = ""
    fix: tuple[str, ...] = ()
    error: str = ""
    keep: str = ""


@dataclass(frozen=True)
class Verdict:
    """What one reply did with one case."""

    case: Case
    recast: str
    why_shown: bool
    kept: bool
    fixed: bool
    gender_changed: bool


def load(path: Path = FRENCH_CASES) -> list[Case]:
    out: list[Case] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        row = json.loads(raw)
        if row["kind"] not in KINDS:
            raise ValueError(f"{row['id']}: no such kind {row['kind']!r}")
        out.append(
            Case(
                id=str(row["id"]),
                sent=str(row["sent"]),
                kind=str(row["kind"]),
                spot=str(row.get("spot") or ""),
                fix=tuple(str(one) for one in row.get("fix") or ()),
                error=str(row.get("error") or ""),
                keep=str(row.get("keep") or ""),
            )
        )
    return out


def normal(text: str) -> str:
    """Lowercase, one apostrophe, one space, and no punctuation but the apostrophe and
    the hyphen: what two renderings of the same words have in common."""
    said = unicodedata.normalize("NFC", text).lower().replace("’", "'")
    said = re.sub(r"[^\w'\- ]+", " ", said.replace(" ", " ").replace(" ", " "))
    return " ".join(said.split())


def says(text: str, words: str) -> bool:
    """Whether `text` says `words`, whole words only."""
    wanted = normal(words)
    if not wanted:
        return False
    return re.search(rf"(?<![\w']){re.escape(wanted)}(?![\w'])", normal(text)) is not None


def score(case: Case, reply: str, language: str = "fr") -> Verdict:
    """One reply against its case, read by the contract's own parser."""
    from . import hebrew

    pairs = hebrew.pairs(reply, language)
    first = next((pair for pair in pairs if pair.recast), None)
    recast = first.hebrew if first is not None else ""
    why_shown = bool(first is not None and first.why)
    kept = bool(recast) and normal(recast) == normal(case.sent)
    fixed = False
    if case.kind == "error" and recast:
        fixed = not says(recast, case.error) and (
            not case.fix or any(says(recast, one) for one in case.fix)
        )
    gender_changed = bool(case.keep) and not says(recast, case.keep)
    return Verdict(case, recast, why_shown, kept, fixed, gender_changed)


@dataclass
class Summary:
    """The run's numbers, as the ledger records them, and how many cases each is over."""

    scores: dict[str, float] = field(default_factory=dict)
    over: dict[str, int] = field(default_factory=dict)


def summarise(verdicts: Iterable[Verdict]) -> Summary:
    """The metrics of a run.

    `why_shown_on_correct_lines` and `why_shown_on_register_lines` are counts, each wanting
    a ceiling of nought: the contract says "never on a line that was right". So is
    `reader_gender_changed`. `fixed_share` and `why_shown_on_errors_share` are shares of
    the error cases; `recast_kept_share` is the share of correct lines said back as they
    were written."""
    by_kind: dict[str, list[Verdict]] = {kind: [] for kind in KINDS}
    for one in verdicts:
        by_kind[one.case.kind].append(one)
    correct, register, error = by_kind["correct"], by_kind["register"], by_kind["error"]
    out = Summary()

    def put(metric: str, value: float, n: int) -> None:
        out.scores[metric] = value
        out.over[metric] = n

    put("why_shown_on_correct_lines", sum(one.why_shown for one in correct), len(correct))
    put("why_shown_on_register_lines", sum(one.why_shown for one in register), len(register))
    gendered = [one for one in correct if one.case.keep]
    put("reader_gender_changed", sum(one.gender_changed for one in gendered), len(gendered))
    put("recast_kept_share", _share([one.kept for one in correct]), len(correct))
    put("fixed_share", _share([one.fixed for one in error]), len(error))
    put("why_shown_on_errors_share", _share([one.why_shown for one in error]), len(error))
    return out


def _share(flags: Sequence[bool]) -> float:
    return round(sum(flags) / len(flags), 4) if flags else 0.0
