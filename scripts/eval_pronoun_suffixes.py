"""The pronoun-suffix reading against Open Scriptures' own codes (targum-internal#450).

`annotate/suffixes.reading` names the pronoun on the end of a word from what a stored token
carries: its pieces line and its pointed letters. For a verse Open Scriptures tagged, the
pieces line is Open Scriptures' own cut, ל + פני + הם, and the code beside the last piece
(`Sp3mp`, a pronominal suffix, third person masculine plural) is the gold here. The
reading never sees the code: it reads the letters of the piece and the points of the word,
which is what the build reads for every Biblical text.

**Held out.** The reading was written from the grammar and checked on the Torah before it
was scored, and was not changed after. The rows are every word outside the Torah. A word
is gold when its last piece is a pronominal suffix (`Sp`); the directional ה and the long
endings (`Sd`, `Sh`, `Sn`) are suffixes in the tagging and not pronouns, so a reading that
names one is a false positive. A reading counts as right when it says the person and the
number, and the gender wherever it says one (`suffixes.agrees`).

The modern half is scored by `scripts/score_annotation.py`, against IAHLT
(`suffix_precision`, `suffix_recall` under `lemma/iahlt`).

    .venv/bin/python scripts/eval_pronoun_suffixes.py

No key and no network; OSHB must be on disk (`targum models fetch scripture`).
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from targum import evals  # noqa: E402
from targum.annotate import oshb, scripture, suffixes  # noqa: E402

STAGE = "lemma"
CORPUS = "oshb-wlc"
SYSTEM = "suffix-rule/1"

#: Where the reading was written and checked, and so not scored.
TORAH = ("Gen", "Exod", "Lev", "Num", "Deut")

#: Every book OSHB tags, in the Bible's order. The Aramaic chapters of Daniel and Ezra are
#: left out (`ARAMAIC`): the spot is Hebrew's, and Aramaic writes its suffixes otherwise.
BOOKS = (
    *TORAH,
    "Josh", "Judg", "1Sam", "2Sam", "1Kgs", "2Kgs", "Isa", "Jer", "Ezek", "Hos", "Joel",
    "Amos", "Obad", "Jonah", "Mic", "Nah", "Hab", "Zeph", "Hag", "Zech", "Mal", "Ps",
    "Prov", "Job", "Song", "Ruth", "Lam", "Eccl", "Esth", "Dan", "Ezra", "Neh", "1Chr",
    "2Chr",
)  # fmt: skip

#: Chapters written in Aramaic, whole: Daniel 2:4 to 7:28 and Ezra 4:8 to 6:18 and 7:12-26,
#: rounded out to the chapter. The few Hebrew verses lost with them cost nothing.
ARAMAIC = {"Dan": range(2, 8), "Ezra": range(4, 8)}


def aramaic(ref: str) -> bool:
    book, chapter, _ = ref.split(".")
    return int(chapter) in ARAMAIC.get(book, ())


def gold(word: oshb.Word) -> str:
    """The pronoun Open Scriptures wrote on the end of this word, as a code, or ""."""
    code = word.morph[-1] if len(word.morph) > 1 else ""
    if not code.startswith("Sp") or len(code) < 5:
        return ""
    return suffixes.code_of(code[2], code[3], code[4])


def ours(word: oshb.Word) -> str:
    """The reading, from the token `scripture.ScriptureLemmatizer` stores for this word."""
    content = word.morph[word.content] if word.morph else ""
    return suffixes.reading(
        surface=oshb.bare(word.text),
        built=scripture.built_from(word),
        pos=scripture.part_of(content),
        lemma=scripture.headword_of(word),
        pointed=word.text,
    )


def score(books: tuple[str, ...]) -> tuple[Counter[str], Counter[str]]:
    """True and false positives and negatives over the books, and the misses by word."""
    counts: Counter[str] = Counter()
    wrong: Counter[str] = Counter()
    for book in books:
        for ref, words in oshb.verses(book):
            if aramaic(ref):
                continue
            for word in words:
                want, said = gold(word), ours(word)
                if want and said and suffixes.agrees(said, want):
                    counts["tp"] += 1
                    continue
                if said:
                    counts["fp"] += 1
                if want:
                    counts["fn"] += 1
                if said or want:
                    line = (
                        f"{said or '-'}/{want or '-'} {oshb.bare(word.text)} {'/'.join(word.morph)}"
                    )
                    wrong[line] += 1
    return counts, wrong


def rates(counts: Counter[str]) -> tuple[float, float]:
    tp, fp, fn = counts["tp"], counts["fp"], counts["fn"]
    return round(tp / max(1, tp + fp), 4), round(tp / max(1, tp + fn), 4)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--ledger", type=Path, default=evals.DEFAULT)
    parser.add_argument("--dry", action="store_true")
    parser.add_argument("--torah", action="store_true", help="score the Torah alone, and stop")
    args = parser.parse_args(argv)

    if not oshb.available():
        raise SystemExit("OSHB is not on disk; run `targum models fetch scripture` first")

    seen, missed = score(TORAH)
    precision, recall = rates(seen)
    print(f"(the Torah, where the reading was checked: precision {precision}, recall {recall})")
    if args.torah:
        for line, n in missed.most_common(30):
            print(f"  {n:4} {line}")
        return

    held = tuple(book for book in BOOKS if book not in TORAH)
    counts, wrong = score(held)
    precision, recall = rates(counts)
    for line, n in wrong.most_common(12):
        print(f"  {n:4} {line}")
    note = evals.pinned(
        f"books={len(held)} tp={counts['tp']} fp={counts['fp']} fn={counts['fn']}",
        [oshb.root() / f"{book}.json" for book in held],
    )
    today = date.today().isoformat()
    rows = [
        evals.Row(
            today,
            STAGE,
            SYSTEM,
            SYSTEM,
            "suffix_precision",
            precision,
            counts["tp"] + counts["fp"],
            CORPUS,
            note,
        ),
        evals.Row(
            today,
            STAGE,
            SYSTEM,
            SYSTEM,
            "suffix_recall",
            recall,
            counts["tp"] + counts["fn"],
            CORPUS,
            note,
        ),
    ]
    for row in rows:
        print(f"{row.metric:18} {row.score:.4f}  n={row.n}  {row.system}", flush=True)
    if not args.dry:
        evals.append(rows, args.ledger)
        print(f"appended {len(rows)} rows to {args.ledger}")


if __name__ == "__main__":
    main()
