"""Score the dictionary itself against the hand tagging (targum-internal#116).

    set -a && . ./.env && set +a
    python scripts/score_dictionary.py --verbs 400 --participles 250

`score_annotation.py` scores the annotator as a whole. This scores the one stage that
costs money, on its own and before it is believed, which is the gate the plan puts in
front of it: a field is adopted only where it beats the rule it replaces.

Three questions, each against the IAHLT treebanks:

- **binyan** — ask about verb dictionary forms the treebank records a binyan for, and
  compare. The rules answer for 8.9% of verbs; this is the number to beat.
- **root** — compare against the root derived from the gold lemma and gold binyan by
  `hebrew.root_of`. That reference is a derivation and not a gold standard, so every
  disagreement is printed rather than only counted. Reading them is how the nifal bug
  was found, with the reference wrong and the thing being scored right.
- **dictionary form** — ask about participle surfaces whose gold lemma is a different
  word, which is the case DICTA gets wrong 44% of the time. Scored twice, exactly and
  after `canonical()` folds ktiv variants, because ביקש and בקש are one word and a
  scorecard that called that an error would be measuring a spelling convention.

Answers land in the ordinary cache, so a second run costs nothing and the entries are
the same ones a build would use.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verbs", type=int, default=400, help="dictionary forms to ask about")
    parser.add_argument("--participles", type=int, default=250, help="participle surfaces")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--buy", action="store_true", default=True)
    parser.add_argument("--no-buy", dest="buy", action="store_false", help="score what is held")
    parser.add_argument("--out", type=Path, default=Path("dictionary-scorecard.json"))
    args = parser.parse_args()

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
    from targum.annotate import dictionary, gold
    from targum.annotate.canonical import bare, canonical
    from targum.annotate.hebrew import BINYANIM
    from targum.annotate.score import gold_root

    verbs = [
        token
        for corpus in gold.CORPORA
        for sentence in gold.load(corpus)
        for token in sentence.tokens
        if token.upos == "VERB" and token.binyan
    ]
    # One example per dictionary form, and one per participle surface whose dictionary
    # form is a different word — the case the tagger answers with the participle for.
    forms = {}
    participles = {}
    for token in verbs:
        forms.setdefault(token.lemma, token)
        if "VerbForm=Part" in token.feats and not token.prefixes and token.surface != token.lemma:
            participles.setdefault(token.surface, token)

    rng = random.Random(args.seed)
    asked = _sample(sorted(forms), args.verbs, rng)
    asked_parts = _sample(sorted(participles), args.participles, rng)
    print(f"{len(asked)} dictionary forms, {len(asked_parts)} participle surfaces", file=sys.stderr)
    print(f"estimate ${dictionary.estimate(len(asked) + len(asked_parts)):.2f}", file=sys.stderr)

    provider = dictionary.AnthropicDictionary()
    seen = [0]

    def tick(n: int) -> None:
        seen[0] += n
        print(f"  {seen[0]} forms", end="\r", file=sys.stderr)

    held, _ = dictionary.build(asked, provider, buy=args.buy, on_progress=tick)
    held_parts, _ = dictionary.build(asked_parts, provider, buy=args.buy, on_progress=tick)
    print(f"\nspent ${provider.spent.cost():.4f}", file=sys.stderr)

    report: dict[str, object] = {}
    report["binyan"] = _score(
        "binyan",
        asked,
        held,
        lambda entry: entry.binyan,
        lambda form: BINYANIM.get(forms[form].binyan.upper()),
    )
    report["root"] = _score(
        "root",
        asked,
        held,
        lambda entry: entry.root,
        lambda form: gold_root(forms[form]),
    )
    report["dictionary_form"] = _score(
        "dictionary form",
        asked_parts,
        held_parts,
        lambda entry: entry.dictionary_form,
        lambda form: participles[form].lemma,
        fold=lambda word: canonical(bare(word)),
    )
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"written to {args.out}", file=sys.stderr)
    return 0


def _sample(items: list[str], want: int, rng: random.Random) -> list[str]:
    return sorted(rng.sample(items, want)) if 0 < want < len(items) else items


def _score(
    label: str,
    forms: list[str],
    held: dict[str, object],
    ours: object,
    theirs: object,
    fold: object = None,
) -> dict[str, object]:
    """Coverage, accuracy, and every disagreement — because the disagreements are the
    work list, and on the root they are also how the reference gets checked."""
    asked = have = right = folded = 0
    misses = []
    for form in forms:
        want = theirs(form)  # type: ignore[operator]
        if not want:
            continue
        asked += 1
        entry = held.get(form)
        got = ours(entry) if entry is not None else ""  # type: ignore[operator]
        if not got:
            continue
        have += 1
        if got == want:
            right += 1
            folded += 1
        elif fold is not None and fold(got) == fold(want):  # type: ignore[operator]
            folded += 1
        else:
            misses.append({"form": form, "gold": want, "ours": got})
    coverage = have / asked if asked else 0.0
    accuracy = right / have if have else 0.0
    line = f"{label:16s} coverage {100 * coverage:5.1f}%  accuracy {100 * accuracy:5.1f}%"
    if fold is not None and have:
        line += f"  after folding {100 * folded / have:5.1f}%"
    print(f"{line}   ({right}/{have} of {asked})")
    for miss in misses[:20]:
        print(f"    {miss['form']:14s} gold={miss['gold']:12s} ours={miss['ours']}")
    return {
        "asked": asked,
        "answered": have,
        "right": right,
        "coverage": coverage,
        "accuracy": accuracy,
        "accuracy_folded": (folded / have) if have else None,
        "misses": misses,
    }


if __name__ == "__main__":
    raise SystemExit(main())
