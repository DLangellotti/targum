"""How French is said on the card, scored (targum-internal#266).

Two numbers the card's acceptance criteria ask for, against `evals/french-said-gold.jsonl`:

- **Liaison precision**: of the liaisons the "as said" switch marks, the share the gold
  calls always made (liaison obligatoire). The floor is 0.98: a learner told a liaison is
  required that is optional or forbidden is told something false. Recall is printed beside
  it, over the always-made sites between two words, and is not the promise.
- **IPA word accuracy**: of the words the card gives a reading for, the share whose reading
  is the one the gold gives — Morphalou's own transcription of the word as it is used
  there, and for the words the table says two ways, or that the card says by their parts,
  the reading the gold chose. Coverage, the share of words given any reading, beside it.

**The gold is model-drafted and has not been read by a person.** 342 sentences of four
public-domain texts on the French shelf (Perrault, Daudet, Maupassant, Allais), split as
the tagger splits them. Each word's part of speech was drafted by a model following the
tagger's own instruction (`model_lemma.SYSTEM`) and placed by the tagger's own parser;
each place where a liaison could be made — a word ending in a consonant letter before one
beginning with a vowel, h or y — was labelled `always`, `optional` or `never` by a second
model that was not shown the rule; the readings of words the table says two ways were
chosen by a third. So the precision here is the rule's, given the tags the gold drafted:
the tagger's own tags are not in the loop until the script is run with `--tagger`, which
spends (about a dollar's worth of Haiku for the whole set; load the keys with `op run`).
See `evals/SOURCES.md`.

    python scripts/eval_liaison.py [--gold evals/french-said-gold.jsonl] [--tagger] [--record]

Morphalou must be fetched first: `targum models fetch morphalou`.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from targum import evals  # noqa: E402
from targum.annotate import french_said, morphalou  # noqa: E402
from targum.models import Segment, Token  # noqa: E402

GOLD = Path(__file__).resolve().parents[1] / "evals" / "french-said-gold.jsonl"
CORPUS = "pd-fr-drafted"
STAGE = "said"
SYSTEM = "morphalou-3.1+gruut-liaison"


def words_of(row: dict) -> list[Token]:
    return [
        Token(start=a, end=b, surface=surface, lemma=lemma, band=0, pos=pos, feats=feats or None)
        for a, b, surface, lemma, pos, feats in row["words"]
    ]


def tagged(rows: list[dict]) -> list[list[Token]]:
    """The tagger's own words for every sentence, bought where not cached."""
    from targum.annotate.model_lemma import ModelLemmatizer

    segments = [
        Segment(id=f"{n:04d}", block_id=f"b{n}", block_index=n, index=n, text=row["sentence"])
        for n, row in enumerate(rows)
    ]
    reader = ModelLemmatizer(buy=True)
    found = reader.lemmas(segments, "fr")
    print(f"tagger spent: {reader.spent}")
    return [found.get(segment.id, []) for segment in segments]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gold", type=Path, default=GOLD)
    parser.add_argument("--tagger", action="store_true", help="Tag with the model (spends).")
    parser.add_argument("--record", action="store_true", help="Append the rows to the ledger.")
    parser.add_argument("--ledger", type=Path, default=evals.DEFAULT)
    args = parser.parse_args()

    lexicon = morphalou.load()
    rows = [json.loads(line) for line in args.gold.read_text(encoding="utf-8").splitlines()]
    all_words = tagged(rows) if args.tagger else [words_of(row) for row in rows]

    marked = right = 0
    wrong: Counter[str] = Counter()
    consonant_right = 0
    always = found_always = inside = 0
    shown = words = ipa_right = 0
    judged = judged_right = 0
    misses: list[str] = []
    for row, tokens in zip(rows, all_words, strict=True):
        text = row["sentence"]
        said = french_said.sentence(text, tokens, lexicon)
        sites = {(site["at"][1], site["at"][2]): site for site in row["sites"]}
        by_end = {token.end for token in tokens}
        by_start = {token.start for token in tokens}
        for site in row["sites"]:
            if site["label"] != "always":
                continue
            if site["at"][1] in by_end and site["at"][2] in by_start:
                always += 1
            else:
                inside += 1  # inside one word: peut-être, sous-officier
        chosen = {ipa["at"][0]: ipa for ipa in row.get("ipa", [])}
        for at, (token, one) in enumerate(zip(tokens, said, strict=True)):
            if any(char.isalpha() for char in token.surface):
                words += 1
                if one.ipa:
                    shown += 1
                    base = french_said.everyday(one.ipa) if one.liaison else one.ipa
                    expected = chosen.get(token.start, {}).get("said") or _morphalou(lexicon, token)
                    if token.start in chosen:
                        judged += 1
                        judged_right += base in expected
                    if base in expected:
                        ipa_right += 1
                    elif len(misses) < 40:
                        misses.append(f"{token.surface}: shown {base}, gold {sorted(expected)}")
            if not one.liaison:
                continue
            marked += 1
            following = tokens[at + 1]
            site = sites.get((token.end, following.start))
            label = site["label"] if site else "not a site"
            if label == "always":
                right += 1
                found_always += 1
                consonant_right += site["consonant"] == one.liaison
            else:
                wrong[label] += 1
                print(f"  marked, gold {label}: {token.surface}‿{following.surface} | {text[:80]}")

    precision = right / marked if marked else 0.0
    recall = found_always / always if always else 0.0
    accuracy = ipa_right / shown if shown else 0.0
    coverage = shown / words if words else 0.0
    print(f"\nliaison precision {precision:.4f} ({right} of {marked} marked; wrong: {dict(wrong)})")
    print(
        f"liaison recall {recall:.4f} ({found_always} of {always} always-made sites between words;"
    )
    print(f"  {inside} more inside one word, said by the compound's reading)")
    print(f"liaison consonant right {consonant_right} of {right}")
    print(f"IPA word accuracy {accuracy:.4f} ({ipa_right} of {shown} shown)")
    print(
        "  of which chosen by the gold (said two ways, corrected, or by parts): "
        f"{judged_right} of {judged}"
    )
    print(f"IPA coverage {coverage:.4f} ({shown} of {words} words)")
    for line in misses:
        print(f"  {line}")

    tags = "tagger" if args.tagger else "gold"
    note = evals.pinned(
        f"sentences={len(rows)} tags={tags}; gold model-drafted, not yet read by a person",
        [args.gold],
    )
    version = f"{morphalou.VERSION}/{tags}"
    out = [
        evals.Row(
            at=date.today().isoformat(),
            stage=STAGE,
            corpus=CORPUS,
            system=SYSTEM,
            version=version,
            metric=metric,
            score=round(score, 4),
            n=n,
            note=note,
        )
        for metric, score, n in (
            ("liaison_precision", precision, marked),
            ("liaison_recall", recall, always),
            ("ipa_word_accuracy", accuracy, shown),
            ("ipa_coverage", coverage, words),
        )
    ]
    if args.record:
        evals.append(out, args.ledger)
        print(f"appended {len(out)} rows to {args.ledger}")


def _morphalou(lexicon: morphalou.Lexicon, token: Token) -> set[str]:
    """Every reading the table gives the word under its tags, as the card would print it."""
    rows = lexicon.agreeing(token.surface, token.lemma, token.pos or "", token.feats or "")
    return {
        french_said.everyday(french_said.to_ipa(variant))
        for row in rows
        for variant in row.phonetic.split(" OU ")
    }


if __name__ == "__main__":
    main()
