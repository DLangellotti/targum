"""Two scorings of the library side by side (targum-internal#320).

The library was scored per sentence in one wording (`situations`, the deployed file) and
again in another (`without-register`, a home of its own). This reads both compiled files
and the built shelf and says, for free:

- the mean rung (probability-weighted) per register, and the biblical minus modern gap;
- Spearman's rho of the per-text means, so whether the texts keep their order;
- the texts that move most;
- for each rung, how many texts the passage pointer would point into
  (`sentence_level.best_passage`), per register — which is where "the pointer only fires
  for scripture from dalet up" is read.

    .venv/bin/python scripts/sentence_levels_compare.py --out targum-out \\
        --a ~/.targum/sentence-difficulty/sentence-levels.json \\
        --b ~/.targum/sentence-difficulty-without-register/sentence-levels.json

Reads only. Nothing is asked of a model and nothing is written.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from collections import defaultdict
from pathlib import Path
from statistics import mean

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from targum import sentence_level as sl  # noqa: E402
from targum.level import ULPAN  # noqa: E402

HERE = Path(__file__).resolve().parent


def _script(name: str) -> object:
    spec = importlib.util.spec_from_file_location(name, HERE / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # a dataclass looks its module up while it is defined
    spec.loader.exec_module(module)
    return module


def load(where: Path) -> dict[str, sl.Level]:
    raw = json.loads(where.read_text(encoding="utf-8"))
    return {
        str(k): sl.Level(int(row[0]), float(row[1]), float(row[2]))
        for k, row in (raw.get("sentences") or {}).items()
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=Path("targum-out"))
    parser.add_argument("--a", type=Path, required=True, help="the deployed scoring")
    parser.add_argument("--b", type=Path, required=True, help="the scoring to compare")
    parser.add_argument("--moved", type=int, default=10)
    args = parser.parse_args()

    levels = _script("sentence_levels")
    bias = _script("sentence_bias")
    a, b = load(args.a), load(args.b)
    library = list(levels.texts(args.out, []))  # type: ignore[attr-defined]

    by_register: dict[str, dict[str, list[float]]] = defaultdict(lambda: {"a": [], "b": []})
    per_text: list[tuple[str, str, float, float]] = []
    for text in library:
        keys = [sl.key(s) for block in text.blocks for s in block if s.strip()]
        both = [k for k in keys if k in a and k in b]
        if not both:
            continue
        ma, mb = mean(a[k].score for k in both), mean(b[k].score for k in both)
        per_text.append((text.title, text.register, ma, mb))
        by_register[text.register]["a"].extend(a[k].score for k in both)
        by_register[text.register]["b"].extend(b[k].score for k in both)

    print(f"{len(per_text)} texts; {len(a)} sentences in a, {len(b)} in b\n")
    print(f"{'register':<12}{'sentences':>10}{'a':>8}{'b':>8}{'b-a':>8}")
    means = {}
    for register, got in sorted(by_register.items()):
        means[register] = (mean(got["a"]), mean(got["b"]))
        ma, mb = means[register]
        print(f"{register:<12}{len(got['a']):>10}{ma:>8.2f}{mb:>8.2f}{mb - ma:>+8.2f}")
    if "biblical" in means and "modern" in means:
        gap_a = means["biblical"][0] - means["modern"][0]
        gap_b = means["biblical"][1] - means["modern"][1]
        print(f"\nbiblical - modern: a {gap_a:.2f}, b {gap_b:.2f}")
    rho = bias.spearman([t[2] for t in per_text], [t[3] for t in per_text])  # type: ignore[attr-defined]
    print(f"Spearman rho of per-text means: {rho:.3f}\n")

    print("moved most (a -> b):")
    for title, register, ma, mb in sorted(per_text, key=lambda t: -abs(t[3] - t[2]))[: args.moved]:
        print(f"  {mb - ma:+.2f}  {ma:.2f} -> {mb:.2f}  {register:<10} {title}")

    print("\ntexts the passage pointer points into, by reader rung (a / b):")
    registers = sorted(by_register)
    print(f"{'rung':<12}" + "".join(f"{r:>16}" for r in registers))
    for at, rung in enumerate(ULPAN):
        counts: dict[str, list[int]] = {r: [0, 0] for r in registers}
        for text in library:
            if text.register not in counts:
                continue
            for i, kept in enumerate((a, b)):
                if sl.best_passage(text.folder, at, kept) is not None:
                    counts[text.register][i] += 1
        print(
            f"{rung.name:<12}"
            + "".join(f"{f'{c[0]} / {c[1]}':>16}" for c in (counts[r] for r in registers))
        )


if __name__ == "__main__":
    main()
