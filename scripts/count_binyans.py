"""Count how targum's own tagging reads each written verb form, for the conjugation table.

targum-internal#307 decided on 2026-09-27 to break the ties Wikidata cannot — `אומר` is a
form of both `אָמַר` and `הוּמַר`, and the source says nothing about which — from targum's
own `Token.binyan`, with nothing bought. The annotator tags a binyan on most verbs; what
it tags a *written form* as, counted over the shelf, is evidence about the same form
where it tagged nothing. This is the count, and `paradigms.Table.of` is what reads it.

It reads `annotation.json` beside each built text: no model, no network, no annotator.

**Private, and packed into the wheel.** Decided 2026-09-27: the readings are counted off
the library, so the file is gitignored like the catalogue, and packed into the wheel the
way `activity.json` is (`artifacts` in pyproject.toml). The copy that lasts is
`~/.targum/binyans.json`, beside the catalogue; this writes there and into the package,
and `deploy/deploy.sh` puts it into the package again before every build, so a deploy
from a fresh worktree carries it. A checkout without it — CI's, any worktree — draws the
tables the binyan settles and none of the ones only the readings settle.

**Only what may leave.** Even so it is counted only
over documents whose catalogue row carries a licence `licensing.exportable` accepts —
public domain, CC BY, CC BY-SA, targum's own writing — and never over a reader's import,
a page with no row, or a row nobody has checked. What leaves is a written form, the
lemma and binyan it was read as, and two counts: an aggregate fact below the threshold of
expression, the second of the four layers targum-internal#161 lets derived data become.
Measured 2026-09-27, 98% of the shelf's Hebrew verb tokens are on exportable rows.

**One build per document.** The same text is built on several shelves, some by an older
annotator that tagged fewer binyanim; counting every copy would count one text several
times. The build with the most tagged verbs stands for the document.

**Only what decides, and only what can be used.** A form is kept where at least `LEAST`
tagged occurrences were read and at least `SHARE` of them as one lemma in one binyan,
and only where that lemma and binyan name exactly one verb in the shipped table — a
reading that names nothing, or two things, could never settle a tie.

    .venv/bin/python scripts/count_binyans.py --out ~/.targum/targums
"""

from __future__ import annotations

import argparse
import collections
import datetime
import json
import sys
from collections.abc import Callable
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from targum.annotate.paradigms import (  # noqa: E402
    READINGS,
    Table,
    bare,
    binyan_of,
    table,
    written_form,
)

#: The fewest tagged occurrences of a form before its reading is believed, and the share
#: of them that must agree. Chosen 2026-09-27 against the Open Scriptures hand tagging of
#: the same tokens in an older build of the Tanakh, each document's own counts held out:
#: 20 and 0.95 are right 97.9% of the time (737 of 753 tokens), against 95.8% for the
#: tables the binyan already settles. 10 and 0.9 settle twice as many and fall to 95.2%,
#: which is not a trade a wrong table is worth.
LEAST = 20
SHARE = 0.95

#: Where the readings are kept, beside the catalogue, private data for the same reason.
KEPT = Path.home() / ".targum" / "binyans.json"


def exportable_licence(source: str) -> bool:
    """Whether the catalogue row for `source` may leave targum. No row is no."""
    from targum import catalogue
    from targum.licensing import exportable

    entry = catalogue.matching(source) if source else None
    return bool(entry and exportable(entry.licence))


def count(
    out: Path,
    may_leave: Callable[[str], bool] = exportable_licence,
    language: str = "he",
) -> tuple[dict[str, collections.Counter[tuple[str, str]]], dict[str, int]]:
    """Every tagged verb under `out`, counted by the form it was written in.

    Returns the counts, and a tally of what was read and what was left out, so the file
    can say what it was counted over.
    """
    best: dict[str, tuple[int, str, list[tuple[str, str, str]]]] = {}
    tally: collections.Counter[str] = collections.Counter()
    for path in sorted(out.glob("**/annotation.json")):
        try:
            found = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not str(found.get("language") or "").startswith(language):
            continue
        try:
            source = str(
                json.loads((path.parent / "document.json").read_text(encoding="utf-8")).get(
                    "source"
                )
                or ""
            )
        except (OSError, ValueError, AttributeError):
            source = ""
        if not may_leave(source):
            tally["builds left out: licence"] += 1
            continue
        read: list[tuple[str, str, str]] = []
        for tokens in (found.get("tokens") or {}).values():
            for token in tokens:
                if not isinstance(token, dict) or token.get("pos") != "VERB":
                    continue
                lemma, binyan = str(token.get("lemma") or ""), str(token.get("binyan") or "")
                if not lemma or not binyan:
                    continue
                form = written_form(str(token.get("surface") or ""), token.get("built"))
                if form:
                    read.append((form, bare(lemma), binyan))
        key = str(found.get("document_hash") or path.parent)
        tally["builds read"] += 1
        if key not in best or len(read) > best[key][0]:
            best[key] = (len(read), str(found.get("annotator") or ""), read)

    counts: dict[str, collections.Counter[tuple[str, str]]] = collections.defaultdict(
        collections.Counter
    )
    for _n, _annotator, read in best.values():
        for form, lemma, binyan in read:
            counts[form][(lemma, binyan)] += 1
    tally["documents"] = len(best)
    tally["tagged verb tokens"] = sum(n for n, _a, _r in best.values())
    return counts, dict(tally)


def decided(
    counts: dict[str, collections.Counter[tuple[str, str]]],
    verbs: Table,
    least: int = LEAST,
    share: float = SHARE,
) -> dict[str, list[object]]:
    """The forms whose reading is settled, and names exactly one verb in the table."""
    named: collections.Counter[tuple[str, str]] = collections.Counter()
    for verb in verbs.verbs.values():
        binyan = binyan_of(verb.lemma)
        if binyan:
            named[(bare(verb.lemma), binyan)] += 1
    out: dict[str, list[object]] = {}
    for form in sorted(counts):
        seen = counts[form]
        total = sum(seen.values())
        (lemma, binyan), agree = seen.most_common(1)[0]
        if total < least or agree / total < share or named[(lemma, binyan)] != 1:
            continue
        out[form] = [lemma, binyan, agree, total]
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=Path,
        default=Path.home() / ".targum" / "targums",
        help="Where the built texts are. Default: ~/.targum/targums",
    )
    parser.add_argument(
        "--write",
        type=Path,
        default=KEPT,
        help=f"Where to keep the readings. Default: {KEPT}; a copy goes to {READINGS}",
    )
    args = parser.parse_args()
    if not args.out.is_dir():
        sys.exit(f"nothing built at {args.out}")

    counts, tally = count(args.out)
    forms = decided(counts, table())
    if not forms:
        sys.exit(f"no reading settled under {args.out}; nothing written")
    head = {
        "source": "targum's own Token.binyan, counted by written form",
        "why": "targum-internal#307: break the ties Wikidata's lexemes cannot",
        "counted": {
            "on": datetime.date.today().isoformat(),
            "over": "documents whose catalogue licence is exportable (#161, layer 2)",
            **tally,
        },
        "least": LEAST,
        "share": SHARE,
        "columns": ["lemma", "binyan", "agree", "tagged"],
    }
    # One form to a line, so a change to the counts reads as a diff of the forms it moved.
    lines = [
        f"  {json.dumps(form, ensure_ascii=False)}: {json.dumps(row, ensure_ascii=False)}"
        for form, row in forms.items()
    ]
    body = json.dumps(head, ensure_ascii=False, indent=2)[:-2]
    text = body + ',\n  "forms": {\n' + ",\n".join("  " + line for line in lines) + "\n  }\n}\n"
    args.write.parent.mkdir(parents=True, exist_ok=True)
    args.write.write_text(text, encoding="utf-8")
    # And into the package, where this checkout's builds and its `targum serve` read it.
    READINGS.write_text(text, encoding="utf-8")
    print(f"{len(forms):,} forms settled, from {len(counts):,} counted")
    print(f"  written to {args.write} and {READINGS}")
    for name, value in tally.items():
        print(f"  {name:28} {value:,}")


if __name__ == "__main__":
    main()
