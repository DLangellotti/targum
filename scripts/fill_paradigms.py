"""Fill the stub verbs of the shipped conjugation table by rule (targum-internal#307).

Reads `paradigms.json.gz`, works out what each verb lacks from its root and binyan
(`targum.annotate.conjugate`), and writes it back under `filled` — beside the source's own
forms, never over them. Run again, it starts from the source's forms alone, so it gives
the same file every time.

No model, no network, nothing bought. It prints what it filled and what it refused.

    .venv/bin/python scripts/fill_paradigms.py            # rewrite the shipped table
    .venv/bin/python scripts/fill_paradigms.py --dry-run  # say what it would do
    .venv/bin/python scripts/fill_paradigms.py --check    # how often the rule is right
"""

from __future__ import annotations

import argparse
import collections
import gzip
import json
import random
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from targum.annotate import conjugate  # noqa: E402
from targum.annotate.hebrew import root_of  # noqa: E402
from targum.annotate.paradigms import TABLE, binyan_of, fill, from_shipped  # noqa: E402


def filled(loaded: dict[str, Any]) -> tuple[dict[str, Any], collections.Counter[str]]:
    """The shipped shape with `filled` worked out afresh, and a tally of what happened."""
    attested = from_shipped(loaded, ruled=False)
    names: list[str] = [str(name) for name in loaded.get("features") or ()]
    codes = {name: at for at, name in enumerate(names)}
    out: dict[str, list[list[object]]] = {}
    tally: collections.Counter[str] = collections.Counter()
    for lid, done in sorted(fill(attested).items(), key=lambda pair: int(pair[0])):
        verb = attested.verbs[lid]
        # A stub is short of more than a passive's missing imperatives.
        have = conjugate.cells_of((form.written, form.features) for form in verb.forms)
        kind = "stub" if len(have) < len(conjugate.CELLS) - 4 else "near-whole"
        if done.forms:
            for _, features in done.forms:
                for feature in features:
                    if feature not in codes:
                        codes[feature] = len(names)
                        names.append(feature)
            out[lid] = [
                [written, [codes[feature] for feature in features]]
                for written, features in done.forms
            ]
            tally[f"{kind}: filled"] += 1
            tally["cells added"] += len(done.forms)
            tally["cells withheld"] += done.withheld
        elif done.refused:
            tally[f"{kind}: refused, {done.refused}"] += 1
        else:
            tally["nothing missing"] += 1
    shipped = {key: value for key, value in loaded.items() if key != "filled"}
    shipped["features"] = names
    shipped["filled"] = out
    return shipped, tally


def write(shipped: dict[str, Any], where: Path) -> None:
    """Gzipped with `mtime=0`, as `hebrew_paradigms.py` writes it: same input, same bytes."""
    text = json.dumps(shipped, ensure_ascii=False, separators=(",", ":"))
    with where.open("wb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as out:
        out.write(text.encode("utf-8"))


def check(loaded: dict[str, Any], seed: int = 7) -> None:
    """Leave one out: every complete table is cut down to a few of its own cells, filled
    from the patterns of all the *other* tables, and what comes back is scored against
    what the source really has. The binyan is given, as a pointed lemma gives it, and
    then withheld, as an unpointed one does."""
    attested = from_shipped(loaded, ruled=False)
    rows = []
    for verb in attested.verbs.values():
        binyan = binyan_of(verb.lemma)
        root = root_of(verb.lemma, binyan) if binyan else None
        if binyan and root:
            rows.append((verb.lemma, binyan, root, [(f.written, f.features) for f in verb.forms]))
    patterns = conjugate.learn(rows)
    rng = random.Random(seed)
    for kept in (3, 6, 10):
        for given in (True, False):
            right = wrong = verbs = 0
            for lemma, binyan, root, forms in rows:
                own = conjugate.learn([(lemma, binyan, root, forms)])
                if not own:
                    continue
                ((klass, counted),) = own.items()
                ((pattern, _),) = counted.items()
                others = {key: collections.Counter(value) for key, value in patterns.items()}
                others[klass][pattern] -= 1
                others[klass] = +others[klass]
                cells = conjugate.cells_of(forms)
                keep = set(rng.sample(sorted(cells), kept))
                cut = [
                    (written, features)
                    for written, features in forms
                    if conjugate.cells_of([(written, features)]).keys() & keep
                ]
                lem = lemma if given else conjugate.plain(lemma)
                done = conjugate.fill(lem, cut, others, binyan if given else None)
                verbs += 1
                for written, features in done.forms:
                    truth = conjugate.cells_of([(written, features)])
                    ((at, _),) = truth.items()
                    if conjugate.plain(written) in cells.get(at, set()):
                        right += 1
                    else:
                        wrong += 1
            said = "binyan given" if given else "binyan withheld"
            print(
                f"  {kept:2} cells kept, {said:15}  {verbs:,} tables  "
                f"{right:,} cells right, {wrong:,} wrong  = {right / max(1, right + wrong):.2%}"
            )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--table", type=Path, default=TABLE)
    parser.add_argument("--dry-run", action="store_true", help="Say what it would do.")
    parser.add_argument("--check", action="store_true", help="Score the rule, leave one out.")
    args = parser.parse_args()
    with gzip.open(args.table, "rt", encoding="utf-8") as raw:
        loaded = json.load(raw)
    if args.check:
        check(loaded)
        return
    shipped, tally = filled(loaded)
    for what, count in sorted(tally.items()):
        print(f"  {what:40} {count:6,}")
    if not args.dry_run:
        write(shipped, args.table)
        print(f"→ {args.table}")


if __name__ == "__main__":
    main()
