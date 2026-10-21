"""The segolate stress rule against the Masoretic accents (targum-internal#454).

`annotate/segolate.py` places the stress on the syllable before the last where a pointed
word's vowels settle it, for the modern text that carries no accent. The Tanakh carries
one, so the rule is scored there: every OSHB word with a single placed accent and more
than one syllable, its accents taken off, the rule asked, and its answer compared with the
syllable the accent stresses (read the way `pronounce` reads it, through phonikud).

- `segolate_precision`: where the rule fires, the share the accents stress on the
  syllable before the last.
- `segolate_recall`: of the nouns and adjectives with no suffix that the accents stress
  there, the share the rule reaches.

The existing `stress-rule/1` row (`scripts/eval_hebrew_stress.py`) is a different rule and
is not touched. The modern half, a hand-read gold of rule firings on the shelf, is
ling-he's to read (`modern-stress-handread`).

    .venv/bin/python scripts/eval_segolate.py

No key and no network; OSHB must be on disk (`targum models fetch scripture`).
"""

from __future__ import annotations

import argparse
import sys
import unicodedata
from collections import Counter
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from targum import evals  # noqa: E402
from targum.annotate import oshb, segolate  # noqa: E402
from targum.annotate.pronounce import METEG, stressed, syllables, vocal_shva  # noqa: E402
from targum.vocalize.base import has_taamim, strip_taamim  # noqa: E402

STAGE = "stress"
CORPUS = "tanakh-taamim-v2"
SYSTEM = "stress-rule/2"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--ledger", type=Path, default=evals.DEFAULT)
    parser.add_argument("--dry", action="store_true")
    args = parser.parse_args(argv)
    import phonikud

    if not oshb.available():
        raise SystemExit("OSHB is not on disk; run `targum models fetch scripture` first")
    counts: Counter[str] = Counter()
    wrong: Counter[str] = Counter()
    missed: Counter[str] = Counter()
    books = []
    for code in oshb.BOOKS.values():
        try:
            verses = list(oshb.verses(code))
        except Exception:  # noqa: BLE001 - a book not on disk is left out
            continue
        books.append(code)
        for _ref, words in verses:
            for word in words:
                if not has_taamim(word.text) or not (marked := stressed(word.text)):
                    continue
                try:
                    said = phonikud.phonemize(vocal_shva(marked.replace(METEG, "")))
                except Exception:  # noqa: BLE001
                    continue
                at = said.find("ˈ")
                if at < 0 or syllables(said) < 2:
                    continue
                penult = syllables(said[at:]) == 2
                bare = unicodedata.normalize(
                    "NFC",
                    strip_taamim(word.text).replace(METEG, "").replace("־", "").replace("/", ""),
                )
                fired = segolate.penult(bare) is not None
                counts["words"] += 1
                if fired:
                    counts["fired"] += 1
                    if penult:
                        counts["tp"] += 1
                    else:
                        wrong[bare] += 1
                noun = any(m[:1] in "NA" for m in word.morph) and not any(
                    m[:1] == "S" for m in word.morph
                )
                if noun and penult:
                    counts["nouns"] += 1
                    if fired:
                        counts["nouns_hit"] += 1
                    else:
                        missed[bare] += 1
    precision = round(counts["tp"] / max(1, counts["fired"]), 4)
    recall = round(counts["nouns_hit"] / max(1, counts["nouns"]), 4)
    print(dict(counts))
    print("wrong:", wrong.most_common(15))
    print("missed:", missed.most_common(15))
    note = evals.pinned(
        f"words={counts['words']} fired={counts['fired']} tp={counts['tp']} "
        f"nouns={counts['nouns']} reached={counts['nouns_hit']}",
        [oshb.root() / f"{book}.json" for book in books],
    )
    today = date.today().isoformat()
    rows = [
        evals.Row(
            today, STAGE, SYSTEM, SYSTEM, "segolate_precision", precision, counts["fired"],
            CORPUS, note,
        ),
        evals.Row(
            today, STAGE, SYSTEM, SYSTEM, "segolate_recall", recall, counts["nouns"], CORPUS,
            note,
        ),
    ]  # fmt: skip
    for row in rows:
        print(f"{row.metric:20} {row.score:.4f}  n={row.n}  {row.system}", flush=True)
    if not args.dry:
        evals.append(rows, args.ledger)
        print(f"appended {len(rows)} rows to {args.ledger}")


if __name__ == "__main__":
    main()
