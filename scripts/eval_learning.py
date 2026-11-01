"""Evaluate learning value and narrow reading in the chooser (targum-internal#614).

Offline and free. The catalogue texts built in a folder are indexed in memory, as
`targum catalogue-lemmas` would index them (nothing is written beside them), with the
catalogue's own collections. Simulated readers, each with a true vocabulary that the
estimate does not see (the same noisier model as `scripts/eval_estimate.py`), read a few
texts — continuing a collection where the first one is in one, as a reader in a series
does — mark some of what they know and look up some of what they do not. Then the
chooser's first pick is made twice: by Phase 1's key (fit alone) and by Phase 2's (fit,
then learning value, then interest), and each pick is scored against the reader's truth:

- **in band / in aim**: the pick's true running-word coverage is 90–99.5% / 94–97%;
- **coverage**: its mean true coverage;
- **recurring new**: words the reader truly does not know that come round two or more
  times in the pick, per hundred running words;
- **useful recurring**: the same, only words of everyday Hebrew (usefulness ≥ 0.3);
- **met 3+ over two**: new words met at least three times across the pick and the pick
  made after it, per thousand running words read — incidental learning's real
  threshold, which narrow reading is meant to raise.

    PYTHONPATH=src .venv/bin/python scripts/eval_learning.py --texts targum-out \\
        --topics ~/.targum/topics-2026-10-31.json --ledger ~/.targum/corpus.db
"""

from __future__ import annotations

import argparse
import json
import math
import random
import statistics
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from targum import catalogue as catalogue_module
from targum import choose, learning
from targum import estimate as est
from targum.coverage import KNOWN, Index, build_index, lemmas
from targum.finds import interests
from targum.occurrences import count_text

TRUE_SLOPE = 1.0
WORD_NOISE = 1.0
LUCK = 0.7
USEFUL_LEAST = 0.3


def index_from(root: Path) -> tuple[Index, dict[str, Any]]:
    """The Hebrew catalogue texts built under `root`, indexed with counts, in memory."""
    by_source = {
        entry.source: entry for entry in catalogue_module.everything() if entry.language == "he"
    }
    found: dict[str, list[str]] = {}
    tallies: dict[str, dict[str, int]] = {}
    entries: dict[str, Any] = {}
    for document in sorted(root.glob("*/*/document.json")):
        try:
            source = str(json.loads(document.read_text(encoding="utf-8")).get("source", ""))
        except (OSError, json.JSONDecodeError):
            continue
        entry = by_source.get(source)
        if entry is None or entry.id in found:
            continue
        words = lemmas(document.parent)
        counted = count_text(document.parent)
        if words and counted is not None:
            found[entry.id] = words
            tallies[entry.id] = counted.totals()
            entries[entry.id] = entry
    return build_index(found, tallies), entries


def useful_from(ledger: Path | None) -> learning.Usefulness:
    """Everyday usefulness from the ledger's conversation and news yardsticks, built in
    memory; the frequency list where there is no ledger."""
    if ledger is None:
        return learning.Usefulness("he", None)
    from targum.tables import yardstick
    from targum.tables.store import Store

    store = Store(ledger)
    built = [made for made in (yardstick.build(store, name) for name in learning.EVERYDAY) if made]
    if not built:
        return learning.Usefulness("he", None)
    print(f"Usefulness from yardsticks: {', '.join(one['register'] for one in built)}\n")
    mixed: dict[str, float] = {}
    for one in built:
        for lemma, weight in one["weights"].items():
            mixed[lemma] = mixed.get(lemma, 0.0) + weight / len(built)
    return learning.Usefulness("he", mixed)


def simulate(
    index: Index,
    entries: dict[str, Any],
    useful: learning.Usefulness,
    lexicon: interests.Lexicon | None,
    readers: int,
    seed: int = 11,
) -> None:
    rng = random.Random(seed)
    ids = sorted(index.counts)
    skip = index._not_words
    words = index.words
    b = [est.difficulty(word, "he") for word in words]
    own = [rng.gauss(0, WORD_NOISE) for _ in words]
    useful_at = learning.useful_table(index, useful)
    collections = [
        (tuple(m for m in one.members if m in index.counts), one.ordered)
        for one in catalogue_module.collections()
    ]
    collections = [one for one in collections if len(one[0]) > 1]
    member_of = {m: members for members, _ in collections for m in members}
    print(
        f"## {readers} simulated readers a row, over {len(ids)} Hebrew catalogue texts "
        f"({len(collections)} collections of two or more)\n"
    )
    tally = {at: dict(zip(index.texts[at], index.counts[at], strict=False)) for at in ids}
    totals = {at: sum(n for p, n in tally[at].items() if p not in skip) for at in ids}

    def scores(pick: str, truth: Sequence[bool]) -> tuple[float, float, float]:
        new = [p for p, n in tally[pick].items() if p not in skip and not truth[p] and n >= 2]
        per = 100 / max(1, totals[pick])
        cover = sum(n for p, n in tally[pick].items() if p not in skip and truth[p])
        return (
            cover / max(1, totals[pick]),
            len(new) * per,
            sum(1 for p in new if useful_at[p] >= USEFUL_LEAST) * per,
        )

    print(
        "| read | key | in band | in aim | coverage | recurring new /100 | useful recurring "
        "/100 | met 3+ over two /1000 |"
    )
    print("|---|---|---|---|---|---|---|---|")
    timings: list[float] = []
    for history in (0, 2, 8):
        rows: dict[str, list[tuple[float, ...]]] = {"fit": [], "learn": []}
        for _ in range(readers):
            vocabulary = math.exp(rng.uniform(math.log(300), math.log(12000)))
            theta = math.log(vocabulary) + est.FORMS_PER_LEMMA
            truth = [
                rng.random()
                < est.sigmoid(TRUE_SLOPE * (theta - b[at] - own[at] + rng.gauss(0, LUCK)))
                for at in range(len(words))
            ]
            true_share = {
                at: sum(n for p, n in tally[at].items() if p not in skip and truth[p])
                / max(1, totals[at])
                for at in ids
            }
            order = sorted(ids, key=lambda at: abs(true_share[at] - 0.93))
            read: list[str] = []
            if history:
                first = order[0]
                read.append(first)
                if first in member_of:
                    rest = [m for m in member_of[first] if m != first]
                    read += rest[: history - 1]
                for at in order[1:]:
                    if len(read) >= history:
                        break
                    if at not in read:
                        read.append(at)
            diligence = rng.uniform(0.2, 0.95)
            marked: dict[str, int] = {}
            looked: set[str] = set()
            met: set[str] = set()
            for at in read:
                for p in tally[at]:
                    if p in skip:
                        continue
                    lemma = words[p]
                    met.add(lemma)
                    if lemma in marked:
                        continue
                    if truth[p]:
                        if rng.random() < diligence:
                            marked[lemma] = KNOWN
                    elif rng.random() < 0.6:
                        looked.add(lemma)
                        if rng.random() < 0.3:
                            marked[lemma] = 1
            items = est.evidence([(w, s, "") for w, s in marked.items()], looked, met)
            centre = est.prior(None)
            fitted = est.fit(items, "he", centre) if items else centre
            estimate = est.Estimate("he", fitted, marked, len(items))
            chances = estimate.chances(index)
            statuses = index.statuses(marked)
            liked: tuple[str, ...] = ()
            if lexicon is not None and history:
                liked = tuple(
                    one.topic
                    for one in interests.inferred(
                        [(w, s, "") for w, s in marked.items()], met, lexicon
                    )
                )
            who = learning.reader(index, statuses, chances, met, liked)

            def choose_first(
                done: list[str],
                weigh: bool,
                statuses: dict[int, int] = statuses,
                chances: Any = chances,
                who: learning.Reader = who,
                liked: tuple[str, ...] = liked,
            ) -> str:
                narrow = learning.narrow(collections, done)
                best: tuple[Any, ...] | None = None
                pick = ""
                started = time.perf_counter()
                for at in ids:
                    if at in done:
                        continue
                    share = index.expected(at, statuses, chances)
                    if share is None:
                        continue
                    entry = entries[at]
                    medium = choose.medium_of(entry.kind.value, source=entry.source)
                    learn, interest = 0.0, 0
                    if weigh and choose.fit(share, medium) == choose.BAND:
                        about = learning.text_topics(index, at, lexicon)
                        cont = at in narrow.continuing
                        learn = (
                            learning.value(
                                index,
                                at,
                                who,
                                useful_at,
                                following=narrow.following.get(at, ()),
                                topics=about,
                                lexicon=lexicon,
                                continuing=cont,
                            )
                            or 0.0
                        )
                        interest = int(cont or bool(set(about) & set(liked)))
                    rank = choose.key(
                        share,
                        scene=bool(catalogue_module.scene_number(at)),
                        gentle=int(entry.difficulty or 0),
                        medium=medium,
                        learn=learn,
                        interest=interest,
                    )
                    if best is None or (rank, at) < (best, pick):
                        best, pick = rank, at
                if weigh:
                    timings.append(time.perf_counter() - started)
                return pick

            for name, weigh in (("fit", False), ("learn", True)):
                first = choose_first(read, weigh)
                second = choose_first([*read, first], weigh)
                cover, recurring, worth = scores(first, truth)
                seen: dict[int, int] = {}
                for at in (first, second):
                    for p, n in tally[at].items():
                        if p not in skip and not truth[p]:
                            seen[p] = seen.get(p, 0) + n
                three = sum(1 for n in seen.values() if n >= 3)
                read_words = totals[first] + totals[second]
                rows[name].append(
                    (
                        float(choose.fit(cover) == choose.BAND),
                        float(choose.from_aim(cover) == 0),
                        cover,
                        recurring,
                        worth,
                        1000 * three / max(1, read_words),
                    )
                )
        for name in ("fit", "learn"):
            got = rows[name]
            mean = [statistics.mean(one[i] for one in got) for i in range(6)]
            print(
                f"| {history} | {'Phase 1 (fit)' if name == 'fit' else 'Phase 2 (learn)'} | "
                f"{mean[0]:.0%} | {mean[1]:.0%} | {mean[2]:.1%} | {mean[3]:.2f} | "
                f"{mean[4]:.2f} | {mean[5]:.2f} |"
            )
    print(
        f"\nWeighing every text for one pick: median {statistics.median(timings) * 1000:.0f} ms "
        f"over {len(ids)} texts (scoring only the ones in band).\n"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--texts", type=Path, required=True, help="a folder of built texts")
    parser.add_argument("--topics", type=Path, help="a topic lexicon file")
    parser.add_argument("--ledger", type=Path, help="the language tables' ledger")
    parser.add_argument("--readers", type=int, default=100)
    args = parser.parse_args()
    index, entries = index_from(args.texts.expanduser())
    lexicon = interests.lexicon(args.topics.expanduser()) if args.topics else None
    if lexicon is not None:
        tagged = sum(1 for word in index.words if word in lexicon.lemmas)
        print(f"Topic lexicon: {len(lexicon.lemmas)} lemmas, {tagged} of the index's words.\n")
    useful = useful_from(args.ledger.expanduser() if args.ledger else None)
    simulate(index, entries, useful, lexicon, args.readers)


if __name__ == "__main__":
    main()
