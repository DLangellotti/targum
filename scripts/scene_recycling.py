"""How well the scenes bring their own words back (targum-internal#656).

A reader who does the next scene and nothing else keeps what the scenes themselves
bring back, so for the beginner on Home's one card, recycling decides what sticks. The
measure is the one Language Jones used on Rosetta Stone and the textbooks in 2026:
Rosetta Stone has 3–5% of its words seen once, textbooks 25–33%. Scenes 1–100 measured
43% on 2026-11-07, which is why this exists.

**The bar** (David, 2026-11-07): in each series, at most 15% of dictionary forms seen
once, and every form a scene introduces comes back in at least 2 of the next 10 scenes.
A form whose ten-scene window is still open is `pending`, not owed. A form whose window
closed short is `owed`.

**Free.** It reads what a build already wrote: each built reader's occurrences
(`--from`, a directory of built scene readers) or the catalogue's lemma index
(`--index`, on the box, where every scene is built). Nothing is annotated, bought or
called.

**Before a new scene is written**, run it and give the author the owed and pending
forms introduced in the last ten scenes. The scene uses at least five of them where a
person would say them, and `--strict` is run again before it ships (design.md §12,
"Scenes bring their words back", 2026-11-07).

Existing scenes failing the bar is the expected first result, not a fault in this
script: it reports, and exits 1 only under `--strict`.

    .venv/bin/python scripts/scene_recycling.py --from targum-out/dialogue-readers
    targum's python on the box: scripts/scene_recycling.py --index --out recycling.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

from targum import catalogue as catalogue_module
from targum import coverage as coverage_module
from targum.occurrences import text_occurrences

#: At most this share of a series' forms may be seen only once.
ONCE_AT_MOST = 0.15
#: A form a scene introduces must come back in this many scenes ...
RETURNS = 2
#: ... among this many that follow it.
WINDOW = 10

#: A built scene reader's source, `dialogue:NN-slug` (`document.json`).
SOURCE = re.compile(r"^dialogue:(?:([a-z]{2,3})-)?(\d+)-")

#: The series a beginner reads, by the label this report gives them: the Hebrew A1 path
#: and Hebrew 101+ separately, and as the one run a beginner reads them in.
SERIES_OF = {"": "he-1", "he": "he-101", "ru": "ru"}
JOINED = ("he", ("he-1", "he-101"))

#: One scene: its number, and each dictionary form's running count in it.
Scene = tuple[int, Mapping[str, int]]


@dataclass
class Report:
    """One series measured against the bar."""

    scenes: int = 0
    forms: int = 0
    running: int = 0
    once: float = 0.0
    ten_plus: float = 0.0
    one_scene: float = 0.0
    passes: bool = True
    owed: int = 0
    per_scene: list[dict[str, object]] = field(default_factory=list)
    missing: list[int] = field(default_factory=list)

    def as_json(self) -> dict[str, object]:
        return {
            "scenes": self.scenes,
            "forms": self.forms,
            "running": self.running,
            "once": round(self.once, 4),
            "ten_plus": round(self.ten_plus, 4),
            "one_scene": round(self.one_scene, 4),
            "owed": self.owed,
            "passes": self.passes,
            "scenes_detail": self.per_scene,
            "missing": self.missing,
        }


def measure(scenes: Iterable[Scene], missing: Iterable[int] = ()) -> Report:
    """A series of scenes, in any order, measured against the bar."""
    ordered = sorted(scenes, key=lambda s: s[0])
    report = Report(scenes=len(ordered), missing=sorted(missing))
    if not ordered:
        return report
    total: dict[str, int] = {}
    seen_in: dict[str, list[int]] = {}
    for at, (_, counts) in enumerate(ordered):
        for form, n in counts.items():
            if n <= 0:
                continue
            total[form] = total.get(form, 0) + n
            seen_in.setdefault(form, []).append(at)
    forms = len(total)
    report.forms = forms
    report.running = sum(total.values())
    report.once = sum(1 for n in total.values() if n == 1) / forms
    report.ten_plus = sum(1 for n in total.values() if n >= 10) / forms
    report.one_scene = sum(1 for at in seen_in.values() if len(at) == 1) / forms

    last = len(ordered) - 1
    window_ok = True
    for at, (number, _) in enumerate(ordered):
        introduced = sorted(form for form, places in seen_in.items() if places[0] == at)
        owed: list[str] = []
        pending: list[str] = []
        for form in introduced:
            back = sum(1 for p in seen_in[form][1:] if p <= at + WINDOW)
            if back >= RETURNS:
                continue
            (pending if at + WINDOW > last else owed).append(form)
        window_ok = window_ok and not owed
        report.owed += len(owed)
        report.per_scene.append(
            {"number": number, "introduced": introduced, "owed": owed, "pending": pending}
        )
    report.passes = report.once <= ONCE_AT_MOST and window_ok
    return report


def series_label(series: str, number: int) -> str:
    """The label a scene is reported under. Scenes 101+ on the A1 path's numbering are
    reported as Hebrew 101+, whichever id prefix they carry."""
    label = SERIES_OF.get(series, series)
    return "he-101" if label == "he-1" and number > 100 else label


def from_readers(root: Path) -> dict[str, tuple[list[Scene], list[int]]]:
    """Each series' scenes from a directory of built readers, and the ones unreadable."""
    found: dict[str, tuple[list[Scene], list[int]]] = {}
    for folder in sorted(p for p in root.iterdir() if p.is_dir()):
        try:
            source = json.loads((folder / "document.json").read_text(encoding="utf-8"))
            matched = SOURCE.match(str(source.get("source", "")))
        except (OSError, ValueError):
            continue
        if not matched:
            continue
        number = int(matched.group(2))
        label = series_label(matched.group(1) or "", number)
        scenes, missing = found.setdefault(label, ([], []))
        occurrences = text_occurrences(folder)
        if occurrences is None:
            missing.append(number)
            continue
        scenes.append((number, {form: occurrences.count(form) for form in occurrences.lemmas}))
    return found


def from_index(index: coverage_module.Index) -> dict[str, tuple[list[Scene], list[int]]]:
    """Each series' scenes from the catalogue's lemma index."""
    found: dict[str, tuple[list[Scene], list[int]]] = {}
    for entry_id in sorted(index.texts):
        number = catalogue_module.scene_number(entry_id)
        if not number:
            continue
        label = series_label(catalogue_module.scene_series(entry_id), number)
        scenes, missing = found.setdefault(label, ([], []))
        if entry_id not in index.counts:
            missing.append(number)
            continue
        counts = {
            lemma: index.count_in(entry_id, lemma) or 0 for lemma in index.lemmas_for(entry_id)
        }
        scenes.append((number, counts))
    return found


def run(found: Mapping[str, tuple[list[Scene], list[int]]]) -> dict[str, Report]:
    """Every series, plus Hebrew 1–240 as the one run a beginner reads."""
    reports = {label: measure(scenes, missing) for label, (scenes, missing) in found.items()}
    name, parts = JOINED
    if all(part in found for part in parts):
        scenes = [s for part in parts for s in found[part][0]]
        missing = [m for part in parts for m in found[part][1]]
        reports[name] = measure(scenes, missing)
    return reports


def summary(label: str, report: Report) -> str:
    if not report.scenes:
        return f"{label}: no scenes"
    lines = [
        f"{label}: {report.scenes} scenes, {report.forms} forms, {report.running} running words",
        f"  seen once {report.once:.0%} (bar {ONCE_AT_MOST:.0%}), seen 10+ {report.ten_plus:.0%},"
        f" in one scene only {report.one_scene:.0%}",
        f"  forms owed a return ({RETURNS} in the next {WINDOW} scenes): {report.owed}",
        f"  {'passes' if report.passes else 'misses'} the bar",
    ]
    if report.missing:
        lines.append(f"  unreadable, skipped: {len(report.missing)} ({report.missing[:10]})")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    where = parser.add_mutually_exclusive_group(required=True)
    where.add_argument("--from", dest="readers", type=Path, help="directory of built scene readers")
    where.add_argument("--index", action="store_true", help="the catalogue's lemma index")
    parser.add_argument("--out", type=Path, help="write the full report, owed lists included")
    parser.add_argument("--strict", action="store_true", help="exit 1 when a series misses")
    args = parser.parse_args(argv)

    if args.index:
        path = catalogue_module.lemmas_path()
        if path is None:
            print("No lemma index here: run where the catalogue's lemmas.json is.", file=sys.stderr)
            return 2
        found = from_index(coverage_module.read_index(path))
    else:
        found = from_readers(args.readers)

    reports = run(found)
    if not reports:
        print("no scenes")
    for label in sorted(reports):
        print(summary(label, reports[label]))
    if args.out:
        args.out.write_text(
            json.dumps({k: r.as_json() for k, r in reports.items()}, ensure_ascii=False, indent=1),
            encoding="utf-8",
        )
    if args.strict and not all(r.passes for r in reports.values()):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
