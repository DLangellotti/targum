"""Score a Hebrew annotator against the hand-tagged treebanks (targum-internal#116).

    python scripts/score_annotation.py --model joint --model large-parse
    python scripts/score_annotation.py --corpus iahltwiki --split test --limit 500

Runs the production `Annotator` — nikkud stripping, corrections, binyan and root
derivation, the lot — over the IAHLT sentences and reports lemma, part of speech,
binyan, root and prefix-split accuracy per corpus, as a Markdown table on stdout and a
JSON scorecard beside it. The gold files come down with `targum models fetch gold` and
stay beside the language models; they are CC BY-SA 4.0 and are never read at build time
(see `annotate/gold.py`).

The commonest disagreements ride along in the JSON, because "lemma exact 91%" is not a
list of things to fix and "היה was read as היי 81 times" is.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

MODELS = {
    "joint": "dicta-il/dictabert-joint",
    "parse": "dicta-il/dictabert-parse",
    "large-parse": "dicta-il/dictabert-large-parse",
    "stanza": "stanza",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", action="append", help="iahltwiki, iahltknesset (default both)")
    parser.add_argument("--split", action="append", help="dev, test, train (default dev+test)")
    parser.add_argument(
        "--model", action="append", help=", ".join(MODELS) + " (default joint)", default=None
    )
    parser.add_argument("--limit", type=int, default=0, help="sentences per corpus, 0 for all")
    parser.add_argument("--batch", type=int, default=16)
    parser.add_argument("--out", type=Path, default=Path("scorecard.json"))
    parser.add_argument("--top", type=int, default=25, help="disagreements listed per card")
    parser.add_argument(
        "--dictionary",
        action="store_true",
        help="score again with the dictionary's roots and binyanim filled in",
    )
    parser.add_argument(
        "--buy", action="store_true", help="look up the forms the dictionary has not seen"
    )
    args = parser.parse_args()

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
    from targum.annotate import gold, score

    corpora = args.corpus or sorted(gold.CORPORA)
    splits = tuple(args.split or gold.SPLITS)
    if "all" in splits:
        splits = gold.ALL_SPLITS
    if not gold.available(corpora, splits):
        print("fetching the gold treebanks…", file=sys.stderr)
        gold.fetch(corpora, splits, notify=lambda m: print(f"  {m}", file=sys.stderr))

    cards = []
    for wanted in args.model or ["joint"]:
        for corpus in corpora:
            sentences = gold.load(corpus, splits)
            if args.limit:
                sentences = sentences[: args.limit]
            print(f"{wanted} on {corpus}: {len(sentences)} sentences", file=sys.stderr)
            card = _run(sentences, wanted, corpus, args)
            cards.append(card)
            if not args.dictionary:
                continue
            # The dictionary answers about the forms the tagger returned, and nothing
            # knows what those are until it has run. So the pass above is the baseline
            # and this is the same text read again with the answers in hand.
            held = _dictionary(card.verb_forms, buy=args.buy)
            if held:
                cards.append(_run(sentences, wanted, f"{corpus}+dict", args, **held))

    print(score.table(cards))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(
            {"gold": json.loads(gold.describe()), "cards": [c.as_dict(args.top) for c in cards]},
            ensure_ascii=False,
            indent=1,
        ),
        encoding="utf-8",
    )
    print(f"\nwritten to {args.out}", file=sys.stderr)
    return 0


def _run(sentences: list[object], model: str, corpus: str, args: object, **extra: object) -> object:
    from targum.annotate import score

    annotator = score.annotator_for(lemmatizer=_lemmatizer(model), **extra)
    card = score.score(
        sentences,
        annotator,
        corpus=corpus,
        batch=args.batch,  # type: ignore[attr-defined]
        notify=lambda m: print(f"  {m}", end="\r", file=sys.stderr),
    )
    print(file=sys.stderr)
    return card


def _dictionary(forms: set[str], buy: bool) -> dict[str, object]:
    """What the dictionary holds for these forms, buying the rest only when told to.

    Default is cache only, because a scorecard that spent money every time it ran would
    be run once.
    """
    from targum.annotate import dictionary

    provider = dictionary.AnthropicDictionary()
    owing = dictionary.unpaid(forms, provider.name)
    if owing and buy:
        print(
            f"  buying {len(owing)} forms, about ${dictionary.estimate(len(owing)):.2f}",
            file=sys.stderr,
        )
    held, _ = dictionary.build(forms, provider, buy=buy and bool(owing))
    print(f"  dictionary: {len(held)} of {len(forms)} verb forms answered", file=sys.stderr)
    return {"dictionary": held, "dictionary_name": provider.name} if held else {}


def _lemmatizer(wanted: str) -> object:
    if wanted not in MODELS:
        raise SystemExit(f"unknown model {wanted!r}; one of {', '.join(MODELS)}")
    if wanted == "stanza":
        from targum.annotate.lemma import StanzaLemmatizer

        return StanzaLemmatizer()
    from targum.annotate.dicta import DictaLemmatizer

    return DictaLemmatizer(model=MODELS[wanted])


if __name__ == "__main__":
    raise SystemExit(main())
