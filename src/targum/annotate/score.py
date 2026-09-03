"""An annotator against a hand tagging, as numbers a change can be held to.

Everything a reader is told about a Hebrew word — its dictionary form, what kind of word
it is, its root and binyan, how it is built — is produced by the annotator, and until
this module none of it was scored against anything but another annotator. This runs the
production path over sentences somebody tagged by hand and counts where it agrees.

**The production path, not the lemmatizer.** Gold sentences go through `Annotator` in
batches, the way `scripts/lemma_map.py` learned to: that is where nikkud comes off, where
`_lemma` corrects and declines, where the binyan is derived and the root worked out. A
score of the model alone would be a score of something nobody ships.

**Paired by span.** A gold word and an annotator token are the same word when they cover
the same run of the sentence. Anything the annotator cut differently from the treebank
is unpaired and counted as such, rather than matched to a neighbour and scored wrong.

**Accuracy and coverage are different numbers and both are kept.** A root the annotator
declines to give is a gap the Pealim link fills; a wrong one is a lie told with
confidence. So a verb counts once under "has a root" and, only where both sides have
one, once under "the root is right". Raising the first while lowering the second is a
regression, and the scorecard says so.

**The derived root is a reference, not a gold standard.** The treebanks write the lemma
and the binyan; the root is worked out from those two by the same `hebrew.root_of` the
annotator uses. Where the two disagree it is worth reading the pair before believing the
number — doing exactly that is how the nifal bug was found, with the reference wrong on
all eleven of ניתן's family and the thing being scored right.
"""

from __future__ import annotations

import collections
import dataclasses
import gc
from collections.abc import Callable, Iterable
from typing import Any

from ..models import Segment, SegmentedDocument, Token
from .canonical import bare, canonical
from .gold import GoldSentence, GoldToken
from .hebrew import BINYANIM, root_of

#: Sentences per call to the annotator. The number `lemma_map.py` settled on after a box
#: running a build alongside it killed a run that asked for two hundred.
BATCH = 16

#: How many of the commonest disagreements a card carries, so the table says not only
#: how often the lemma was wrong but which lemmas.
TOP = 25


class _NoBands:
    """Rates nothing. A score is about the words, not their difficulty, and asking
    wordfreq for a band on every token would only slow the run down."""

    name = "none"
    method = "none"
    note = ""

    def supports(self, language: str) -> bool:
        return False

    def band(self, lemma: str, language: str) -> int:
        return 0


def gold_root(token: GoldToken) -> str | None:
    """The root the treebank implies, by the same derivation the annotator uses.

    The treebank writes the lemma and the binyan and not the root, and `root_of` is what
    turns those two into one. Using it on the gold side too means a verb `root_of`
    cannot handle — a hollow root, a doubly weak one — has no gold root and is left out of
    the accuracy, rather than counted wrong for a derivation nothing could have made.
    """
    if token.upos != "VERB" or not token.binyan:
        return None
    return root_of(token.lemma, BINYANIM.get(token.binyan.upper()))


@dataclasses.dataclass
class Scorecard:
    """What one annotator got right on one corpus."""

    annotator: str
    corpus: str
    sentences: int = 0
    gold_words: int = 0
    paired: int = 0
    counts: collections.Counter[str] = dataclasses.field(default_factory=collections.Counter)
    #: Per part of speech: how many, how many lemmas matched, how many tags matched.
    by_pos: dict[str, collections.Counter[str]] = dataclasses.field(
        default_factory=lambda: collections.defaultdict(collections.Counter)
    )
    lemma_misses: collections.Counter[tuple[str, str]] = dataclasses.field(
        default_factory=collections.Counter
    )
    root_misses: collections.Counter[tuple[str, str, str]] = dataclasses.field(
        default_factory=collections.Counter
    )
    binyan_misses: collections.Counter[tuple[str, str, str]] = dataclasses.field(
        default_factory=collections.Counter
    )
    pos_misses: collections.Counter[tuple[str, str]] = dataclasses.field(
        default_factory=collections.Counter
    )

    def add(self, gold: GoldToken, ours: Token) -> None:
        self.paired += 1
        c = self.counts
        bucket = self.by_pos[gold.upos]
        bucket["n"] += 1

        gold_lemma = bare(gold.lemma)
        our_lemma = bare(ours.lemma)
        if our_lemma == gold_lemma:
            c["lemma"] += 1
            c["lemma_canonical"] += 1
            bucket["lemma"] += 1
        else:
            if canonical(our_lemma) == canonical(gold_lemma):
                c["lemma_canonical"] += 1
            self.lemma_misses[(gold.lemma, ours.lemma)] += 1
            if our_lemma == bare(gold.surface) and gold_lemma != bare(gold.surface):
                # The surface stood in for a lemma, and the surface was not it.
                c["surface_stood_in"] += 1

        if ours.pos == gold.upos:
            c["pos"] += 1
            bucket["pos"] += 1
        else:
            self.pos_misses[(gold.upos, ours.pos or "")] += 1

        if gold.upos == "VERB":
            c["verbs"] += 1
            want_binyan = BINYANIM.get(gold.binyan.upper()) if gold.binyan else None
            if want_binyan:
                c["verbs_with_gold_binyan"] += 1
            if ours.binyan:
                c["binyan_have"] += 1
                if want_binyan:
                    c["binyan_scored"] += 1
                    if ours.binyan == want_binyan:
                        c["binyan_right"] += 1
                    else:
                        self.binyan_misses[(gold.lemma, want_binyan, ours.binyan)] += 1
            want_root = gold_root(gold)
            if want_root:
                c["verbs_with_gold_root"] += 1
            if ours.root:
                c["root_have"] += 1
                if want_root:
                    c["root_scored"] += 1
                    if ours.root == want_root:
                        c["root_right"] += 1
                    else:
                        self.root_misses[(gold.lemma, want_root, ours.root)] += 1

        gold_split = bool(gold.prefixes)
        if gold_split and ours.split:
            c["prefix_tp"] += 1
        elif ours.split and not gold_split:
            c["prefix_fp"] += 1
        elif gold_split and not ours.split:
            c["prefix_fn"] += 1

    def rate(self, numerator: str, denominator: str | int) -> float | None:
        below = self.counts[denominator] if isinstance(denominator, str) else denominator
        if not below:
            return None
        return self.counts[numerator] / below

    def rates(self) -> dict[str, float | None]:
        """Every number the plan holds a change to, as a fraction of its own base."""
        c = self.counts
        tp, fp, fn = c["prefix_tp"], c["prefix_fp"], c["prefix_fn"]
        return {
            "paired": self.paired / self.gold_words if self.gold_words else None,
            "lemma": self.rate("lemma", self.paired),
            "lemma_canonical": self.rate("lemma_canonical", self.paired),
            "pos": self.rate("pos", self.paired),
            "surface_stood_in": self.rate("surface_stood_in", self.paired),
            "declined": (c["declined"] / self.paired) if c["declined"] and self.paired else None,
            "binyan_coverage": self.rate("binyan_have", "verbs"),
            "binyan_accuracy": self.rate("binyan_right", "binyan_scored"),
            "root_coverage": self.rate("root_have", "verbs"),
            "root_accuracy": self.rate("root_right", "root_scored"),
            "gold_root_derivable": self.rate("verbs_with_gold_root", "verbs"),
            "prefix_precision": tp / (tp + fp) if tp + fp else None,
            "prefix_recall": tp / (tp + fn) if tp + fn else None,
        }

    def as_dict(self, top: int = TOP) -> dict[str, Any]:
        return {
            "annotator": self.annotator,
            "corpus": self.corpus,
            "sentences": self.sentences,
            "gold_words": self.gold_words,
            "paired": self.paired,
            "counts": dict(self.counts),
            "rates": self.rates(),
            "by_pos": {
                pos: {
                    "n": bucket["n"],
                    "lemma": bucket["lemma"] / bucket["n"] if bucket["n"] else None,
                    "pos": bucket["pos"] / bucket["n"] if bucket["n"] else None,
                }
                for pos, bucket in sorted(self.by_pos.items(), key=lambda kv: -kv[1]["n"])
            },
            "lemma_misses": [
                {"gold": g, "ours": o, "n": n} for (g, o), n in self.lemma_misses.most_common(top)
            ],
            "root_misses": [
                {"lemma": lemma, "gold": g, "ours": o, "n": n}
                for (lemma, g, o), n in self.root_misses.most_common(top)
            ],
            "binyan_misses": [
                {"lemma": lemma, "gold": g, "ours": o, "n": n}
                for (lemma, g, o), n in self.binyan_misses.most_common(top)
            ],
            "pos_misses": [
                {"gold": g, "ours": o, "n": n} for (g, o), n in self.pos_misses.most_common(top)
            ],
        }


#: The rows of the summary table, in the order the plan lists its targets.
ROWS = (
    ("paired", "words paired"),
    ("lemma", "lemma exact"),
    ("lemma_canonical", "lemma after folding"),
    ("pos", "part of speech"),
    ("surface_stood_in", "surface stood in, wrongly"),
    ("declined", "declined by the model"),
    ("binyan_coverage", "verbs with a binyan"),
    ("binyan_accuracy", "binyan right, where scored"),
    ("root_coverage", "verbs with a root"),
    ("root_accuracy", "root right, where scored"),
    ("gold_root_derivable", "verbs whose gold root derives"),
    ("prefix_precision", "prefix split precision"),
    ("prefix_recall", "prefix split recall"),
)


def _pct(value: float | None) -> str:
    return "—" if value is None else f"{100 * value:.1f}%"


def table(cards: Iterable[Scorecard]) -> str:
    """The scorecards side by side, as Markdown a report can paste."""
    cards = list(cards)
    heads = [f"{card.corpus}<br>{_short(card.annotator)}" for card in cards]
    lines = ["| metric | " + " | ".join(heads) + " |", "|---|" + "---|" * len(cards)]
    rates = [card.rates() for card in cards]
    for key, label in ROWS:
        lines.append(f"| {label} | " + " | ".join(_pct(rate[key]) for rate in rates) + " |")
    lines.append(
        "| gold words / paired | "
        + " | ".join(f"{card.gold_words} / {card.paired}" for card in cards)
        + " |"
    )
    return "\n".join(lines)


def _short(name: str) -> str:
    """The annotator's own part of a composed name, for a column head."""
    head = name.split("+", 1)[0]
    return head.removeprefix("dicta/dicta-il/").removeprefix("stanza/")


def score(
    sentences: Iterable[GoldSentence],
    annotator: Any,
    *,
    corpus: str = "",
    batch: int = BATCH,
    notify: Callable[[str], None] | None = None,
) -> Scorecard:
    """Run the annotator over the gold sentences and count what agreed."""
    held = list(sentences)
    card = Scorecard(annotator=annotator.name, corpus=corpus, sentences=len(held))
    say = notify or (lambda _message: None)
    lemmatizer = getattr(annotator, "lemmatizer", None)
    tally = getattr(lemmatizer, "tally", None)
    if tally is not None:
        tally.clear()

    for start in range(0, len(held), batch):
        chunk = held[start : start + batch]
        segments = [
            Segment(
                id=sentence.id or f"s{start + n}",
                text=sentence.text,
                ref="",
                block_id="b1",
                block_index=1,
                index=start + n,
            )
            for n, sentence in enumerate(chunk)
        ]
        document = SegmentedDocument(
            document_hash="gold", language="he", segmenter="gold/1", segments=segments
        )
        read = annotator.annotate(document).tokens
        for segment, sentence in zip(segments, chunk, strict=True):
            ours = {(token.start, token.end): token for token in read.get(segment.id, [])}
            for gold in sentence.tokens:
                card.gold_words += 1
                token = ours.get((gold.start, gold.end))
                if token is not None:
                    card.add(gold, token)
        gc.collect()
        say(f"{min(start + batch, len(held))}/{len(held)} sentences")

    if tally is not None:
        card.counts["declined"] = tally.get("declined", 0)
    return card


def annotator_for(bands: Any | None = None, **kwargs: Any) -> Any:
    """An `Annotator` that rates nothing, so a score is only about the words."""
    from . import Annotator

    return Annotator(bands=bands or _NoBands(), **kwargs)
