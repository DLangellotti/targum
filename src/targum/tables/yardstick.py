"""The yardsticks (targum-internal#579): one fixed word-frequency list per register, which
"How much Hebrew you understand" measures a reader against (#575, design.md §12, "How
much Hebrew you understand is measured on a fixed yardstick", 2026-10-30).

A snapshot is the commonest content lemmas of one register, at most `DEPTH`, each with
its share of the list's running words, so the weights add up to one. It is read from the
language tables (`Store.top`, which already leaves out function words, names and numbers
by `weights.weighed`) and written as a versioned JSON file, `yardstick-<register>-v<N>.json`,
to the tables directory: `/var/lib/targum/tables/` on the box, `~/.targum/tables/` on a
laptop. Neither is in the repository, and no page serves a file from it: a page is shown
one reader's percentage, never the list.

Consumers read the snapshot, never the live counts, so a reader's figure moves only when
they learn a word. The counts keep growing underneath; a new version is written once a
month (David, 2026-10-30, the spec's question 4), and every reader's history is then
recomputed against it from the dates their words became known (`level.coverage_days`).
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
from collections.abc import Iterable, Mapping
from contextlib import closing
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .registers import PICKER

if TYPE_CHECKING:
    from .store import Store

#: How deep a yardstick goes: the commonest 20,000 content lemmas of its register.
DEPTH = 20_000

#: The running content words a register must hold before its first snapshot. Below it
#: the list is a handful of texts, and freezing it for a month would measure readers
#: against whatever those few happened to be about. A register short of it is left out
#: of the picker, as one with no counts at all is.
FLOOR = 50_000

#: The version of the snapshot's own rule (what is read, and how it is weighed). A new
#: number writes a new version at the next run, whatever the month.
RULE = "yardstick/1"

#: Where a snapshot file is looked for and written, unless `TARGUM_TABLES_DIR` says.
BOX_DIR = Path("/var/lib/targum/tables")
LAPTOP_DIR = Path.home() / ".targum" / "tables"

_FILE = re.compile(r"^yardstick-(?P<register>[a-z]+)-v(?P<version>\d+)\.json$")


def directory() -> Path:
    """The tables directory: `TARGUM_TABLES_DIR`, the box's where the box's state is,
    the laptop's everywhere else."""
    named = os.environ.get("TARGUM_TABLES_DIR", "").strip()
    if named:
        return Path(named).expanduser()
    return BOX_DIR if BOX_DIR.parent.is_dir() else LAPTOP_DIR


def bare(lemma: str) -> str:
    """A lemma as a yardstick keys it: without points, so a word kept from a pointed
    headword meets the list's unpointed lemma (`level.known_share` does the same)."""
    from ..vocalize.base import strip_nikkud

    return strip_nikkud(lemma)[0].strip()


@dataclass(frozen=True)
class Yardstick:
    """One register's snapshot, as a reader's figure is measured against it."""

    register: str
    version: int
    made_at: str
    #: Bare lemma → its share of the list's running words; the shares add up to one.
    weights: Mapping[str, float] = field(repr=False)
    tokens: int = 0
    digest: str = ""

    def coverage(self, known: Iterable[str]) -> float:
        """The share of the list's running words that `known` covers. A word not on the
        list — a function word, a name, a word too rare to be on it — adds nothing."""
        keys = {bare(lemma) for lemma in known}
        # fsum, so the same words give the same share in whatever order a set yields them.
        return min(1.0, math.fsum(self.weights.get(key, 0.0) for key in keys))


def build(store: Store, register: str, depth: int = DEPTH) -> dict[str, Any] | None:
    """The snapshot of one register as it stands in the tables now, or None where the
    register holds fewer than `FLOOR` running content words. Not written: `write` does."""
    from .words import WORDS

    top = store.top(WORDS, register, limit=depth * 2)
    counts: dict[str, int] = {}
    for key, n in top:
        lemma = bare(key)
        if lemma:
            counts[lemma] = counts.get(lemma, 0) + int(n)
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:depth]
    total = sum(n for _, n in ranked)
    if total < FLOOR:
        return None
    weights = {lemma: n / total for lemma, n in ranked}
    digest = hashlib.sha256(
        json.dumps([RULE, ranked], ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return {
        "register": register,
        "rule": RULE,
        "depth": depth,
        "tokens": total,
        "lemmas": len(ranked),
        "digest": digest,
        "provenance": provenance(store, register),
        "weights": weights,
    }


def provenance(store: Store, register: str) -> list[dict[str, Any]]:
    """What a register's counts came from: per licence and tool, how many units and
    running words (every word, function words included), and up to five of its sources."""
    from .words import WORDS

    if not store.file.is_file():
        return []
    with closing(store._connect()) as db:
        rows = db.execute(
            "SELECT c.licence, c.tool, COUNT(DISTINCT c.id), COALESCE(SUM(t.n), 0),"
            " GROUP_CONCAT(DISTINCT c.source) FROM contribution c"
            " LEFT JOIN tally t ON t.contribution_id = c.id"
            " WHERE c.superseded_at IS NULL AND c.tbl = ? AND c.register = ?"
            " GROUP BY c.licence, c.tool ORDER BY 4 DESC",
            (WORDS, register),
        ).fetchall()
    return [
        {
            "licence": str(licence),
            "tool": str(tool),
            "units": int(units),
            "tokens": int(tokens),
            "sources": sorted(str(sources or "").split(","))[:5],
        }
        for licence, tool, units, tokens, sources in rows
    ]


def versions(register: str, where: Path | None = None) -> list[tuple[int, Path]]:
    """Every snapshot file of one register in the tables directory, oldest first."""
    folder = where or directory()
    if not folder.is_dir():
        return []
    found = []
    for file in folder.iterdir():
        matched = _FILE.match(file.name)
        if matched and matched["register"] == register:
            found.append((int(matched["version"]), file))
    return sorted(found)


def _month(stamp: str) -> str:
    return stamp[:7]


@dataclass
class Written:
    """What `write` did for one register."""

    register: str
    #: `written`, `unchanged` (the counts give the same list), `held` (this month's
    #: version stands until the month turns), or `short` (under `FLOOR`, nothing written).
    outcome: str
    version: int = 0
    file: Path | None = None
    tokens: int = 0


def write(
    store: Store,
    register: str,
    where: Path | None = None,
    *,
    force: bool = False,
    now: datetime | None = None,
) -> Written:
    """Write a new snapshot of one register when one is due: there is none yet, the last
    one was made in an earlier month (UTC), its rule is not this one, or `force`. A list
    the counts give unchanged is never written twice. The file is written whole and then
    renamed into place, so a reader never meets half of one.
    """
    folder = where or directory()
    stamp = (now or datetime.now(UTC)).isoformat(timespec="seconds")
    held = versions(register, folder)
    last: dict[str, Any] | None = None
    if held:
        try:
            last = json.loads(held[-1][1].read_text(encoding="utf-8"))
        except (OSError, ValueError):
            last = None
    if (
        not force
        and last is not None
        and last.get("rule") == RULE
        and _month(str(last.get("made_at") or "")) == _month(stamp)
    ):
        return Written(register, "held", held[-1][0], held[-1][1], int(last.get("tokens") or 0))
    made = build(store, register)
    if made is None:
        return Written(register, "short")
    if last is not None and last.get("digest") == made["digest"]:
        return Written(register, "unchanged", held[-1][0], held[-1][1], made["tokens"])
    version = (held[-1][0] if held else 0) + 1
    made = {"version": version, "made_at": stamp, **made}
    folder.mkdir(parents=True, exist_ok=True)
    file = folder / f"yardstick-{register}-v{version}.json"
    partial = file.with_suffix(".json.partial")
    partial.write_text(json.dumps(made, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    partial.replace(file)
    return Written(register, "written", version, file, made["tokens"])


def write_all(
    store: Store, where: Path | None = None, *, force: bool = False, now: datetime | None = None
) -> list[Written]:
    """`write` for each register the card's picker may offer, and no other: targum's own
    scenes and the weekly are never a yardstick (David, 2026-10-30). What learners bring
    is (`registers.IMPORTS`, 2026-11-01), once its pool crosses `FLOOR` like any other:
    every row of it already stands on ten readers' material."""
    return [write(store, register, where, force=force, now=now) for register in PICKER]


#: (file, its mtime) → the yardstick read from it, so a page load reads no file twice.
_LOADED: dict[tuple[str, float], Yardstick] = {}


def load(register: str, where: Path | None = None) -> Yardstick | None:
    """The newest snapshot of one register, or None where there is none (or it cannot be
    read). A register with none is absent from the card, never a 0%."""
    if register not in PICKER:
        return None
    held = versions(register, where)
    for version, file in reversed(held):
        try:
            key = (str(file), file.stat().st_mtime)
        except OSError:
            continue
        if key in _LOADED:
            return _LOADED[key]
        try:
            raw = json.loads(file.read_text(encoding="utf-8"))
            weights = {str(k): float(v) for k, v in dict(raw["weights"]).items()}
        except (OSError, ValueError, KeyError, TypeError):
            continue
        if not weights:
            continue
        one = Yardstick(
            register=register,
            version=version,
            made_at=str(raw.get("made_at") or ""),
            weights=weights,
            tokens=int(raw.get("tokens") or 0),
            digest=str(raw.get("digest") or ""),
        )
        _LOADED[key] = one
        return one
    return None
