"""The pointing's stress rules against the Masoretic accents (targum-internal#454, #500).

`annotate/segolate.py` places the stress on the syllable before the last where a pointed
word's vowels settle it, for the modern text that carries no accent. The Tanakh carries
one, so the rule is scored there: every OSHB word with a single placed accent and more
than one syllable, its accents taken off, the rule asked, and its answer compared with the
syllable the accent stresses (read the way `pronounce` reads it, through phonikud).

- `segolate_precision`: where the rule fires, the share the accents stress on the
  syllable before the last.
- `segolate_recall`: of the nouns and adjectives with no suffix that the accents stress
  there, the share the rule reaches.
- `suffix_precision`, `suffix_recall` (system `stress-rule/3`, `annotate/suffix_stress.py`):
  the same for the suffix rule, its class read off Open Scriptures' own tagging the way
  the annotator reads a token's, the sequential perfect (aspect `q`) left out because the
  Masoretes stress it at the end and a modern text never has one. Recall is over the
  words of the rule's classes — a past in the first person or the second masculine
  singular, -nu on anything but a verb, -cha, -ájich — that the accents stress there.

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
from targum.annotate import oshb, scripture, segolate, suffix_stress  # noqa: E402
from targum.annotate.pronounce import METEG, stressed, syllables, vocal_shva  # noqa: E402
from targum.vocalize.base import has_taamim, strip_taamim  # noqa: E402

STAGE = "stress"
CORPUS = "tanakh-taamim-v2"
SYSTEM = "stress-rule/2"
SUFFIX_SYSTEM = "stress-rule/3"


def _in_class(word: str, key: str) -> bool:
    """Whether a word is of one of the suffix rule's classes, whatever the vowel before
    its suffix: a past in the first person (תִּי, נוּ) or the second masculine singular
    (תָּ, תָּה), or -nu (נוּ), -cha (ךָ) or -ájich (יִךְ) on anything but a verb."""
    import unicodedata

    plain = unicodedata.normalize("NFC", word).replace("\u05bc", "")
    pos, _, rest = key.partition("|")
    feats = dict(piece.partition("=")[::2] for piece in rest.split("|") if piece)
    if pos in ("VERB", "AUX"):
        if feats.get("Tense") != "Past":
            return False
        if feats.get("Person") == "1":
            return plain.endswith(("תִי", "נו"))
        if feats.get("Person") == "2" and feats.get("Number") == "Sing":
            return plain.endswith(("תָ", "תָה"))
        return False
    return plain.endswith(("נו", "ךָ", "יִךְ"))


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
    suffix_wrong: Counter[str] = Counter()
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
                code = word.code
                if not (code[:1] == "V" and len(code) > 2 and code[2] == "q"):
                    pos = scripture.part_of(code) or ""
                    key = suffix_stress.gate(pos, scripture.word_features(word))
                    said_fires = suffix_stress.fires(bare, key)
                    if said_fires:
                        counts["suffix_fired"] += 1
                        if penult:
                            counts["suffix_tp"] += 1
                        else:
                            suffix_wrong[bare] += 1
                    if penult and _in_class(bare, key):
                        counts["suffix_class"] += 1
                        if said_fires:
                            counts["suffix_class_hit"] += 1
                noun = any(m[:1] in "NA" for m in word.morph) and not any(
                    m[:1] == "S" for m in word.morph
                )
                if noun and penult:
                    counts["nouns"] += 1
                    if fired:
                        counts["nouns_hit"] += 1
                    else:
                        missed[bare] += 1
    suffix_p = round(counts["suffix_tp"] / max(1, counts["suffix_fired"]), 4)
    suffix_r = round(counts["suffix_class_hit"] / max(1, counts["suffix_class"]), 4)
    print("suffix wrong:", suffix_wrong.most_common(15))
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
        evals.Row(
            today, STAGE, SUFFIX_SYSTEM, SUFFIX_SYSTEM, "suffix_precision", suffix_p,
            counts["suffix_fired"], CORPUS, note,
        ),
        evals.Row(
            today, STAGE, SUFFIX_SYSTEM, SUFFIX_SYSTEM, "suffix_recall", suffix_r,
            counts["suffix_class"], CORPUS, note,
        ),
    ]  # fmt: skip
    for row in rows:
        print(f"{row.metric:20} {row.score:.4f}  n={row.n}  {row.system}", flush=True)
    if not args.dry:
        evals.append(rows, args.ledger)
        print(f"appended {len(rows)} rows to {args.ledger}")


if __name__ == "__main__":
    main()
