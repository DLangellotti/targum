"""Evaluate the estimate of the words a reader has not marked (targum-internal#613).

Two halves, both offline and both free:

1. **Held out, on real marks.** Every reader in an accounts database with enough Hebrew
   marks: five folds of their marked words (known against steps 1–3), theta fitted on
   four and the fifth predicted. Pooled and per-reader AUC, log loss, Brier against the
   base rate, and expected calibration error in ten bins.
2. **Simulated readers**, over the Hebrew texts built in a folder. Each reader has a true
   vocabulary, and knows a word by a noisier model than the estimate's (a word's own
   difficulty off its frequency, and the reader's own luck on it). They read a few texts,
   mark some of what they know, look up some of what they do not, and maybe answer the
   cold-start check (36 words across the bands and 8 made-up ones, over-claiming at a rate
   of their own). Then every unread text's running-word coverage is predicted by marks
   alone (Phase 0) and by the estimate, against the truth, and the chooser's first pick
   is checked for landing in the band.

    PYTHONPATH=src .venv/bin/python scripts/eval_estimate.py \\
        --accounts ~/.targum/targum.db --texts targum-out

The accounts database is opened read-only, through a copy, so a running server's file is
never locked. Nothing is written but the report on stdout.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import re
import shutil
import sqlite3
import statistics
import tempfile
from collections import Counter
from collections.abc import Sequence
from pathlib import Path

from targum import choose
from targum import estimate as est
from targum.annotate.base import not_vocabulary
from targum.touchstones import a_word

HEBREW = re.compile("[א-ת]")


def auc(scores: Sequence[float], labels: Sequence[int]) -> float:
    """The chance a random known word scores above a random unknown one."""
    pairs = sorted(zip(scores, labels, strict=True))
    positive = sum(labels)
    negative = len(labels) - positive
    if not positive or not negative:
        return math.nan
    total = 0.0
    i = 0
    while i < len(pairs):
        j = i
        while j < len(pairs) and pairs[j][0] == pairs[i][0]:
            j += 1
        total += (i + j + 1) / 2 * sum(label for _, label in pairs[i:j])
        i = j
    return (total - positive * (positive + 1) / 2) / (positive * negative)


def calibration(scores: Sequence[float], labels: Sequence[int]) -> tuple[float, float, float]:
    """Log loss, Brier and expected calibration error over ten bins."""
    loss = -sum(
        math.log(max(1e-9, p if y else 1 - p)) for p, y in zip(scores, labels, strict=True)
    ) / len(labels)
    brier = sum((p - y) ** 2 for p, y in zip(scores, labels, strict=True)) / len(labels)
    bins = [[0.0, 0.0] for _ in range(10)]
    for p, y in zip(scores, labels, strict=True):
        at = min(9, int(p * 10))
        bins[at][0] += p
        bins[at][1] += y
    ece = sum(abs(said - was) for said, was in bins) / len(labels)
    return loss, brier, ece


def held_out(accounts: Path, folds: int = 5) -> None:
    with tempfile.TemporaryDirectory() as scratch:
        copy = Path(scratch) / "accounts.db"
        shutil.copy(accounts, copy)
        db = sqlite3.connect(copy)
        rows = db.execute(
            "SELECT person, lemma, status FROM word"
            " WHERE language = 'he' AND gone = 0 AND status IN (1, 2, 3, 9)"
        ).fetchall()
    readers: dict[int, list[tuple[str, int]]] = {}
    for person, lemma, status in rows:
        if a_word(lemma):
            readers.setdefault(person, []).append((lemma, 1 if status == 9 else 0))
    readers = {person: marks for person, marks in readers.items() if len(marks) >= 50}
    print(f"## Held out, real marks ({accounts})\n")
    print(
        f"{len(readers)} readers, {sum(len(m) for m in readers.values())} marked words, "
        f"{sum(len(m) - sum(y for _, y in m) for m in readers.values())} of them not known.\n"
    )
    scores: list[float] = []
    labels: list[int] = []
    who: list[int] = []
    centre = est.prior(None)
    for person, marks in readers.items():
        shuffled = marks[:]
        random.Random(person).shuffle(shuffled)
        for fold in range(folds):
            test = shuffled[fold::folds]
            train = [one for at, one in enumerate(shuffled) if at % folds != fold]
            items = [est.Evidence(lemma, bool(y)) for lemma, y in train]
            theta = est.fit(items, "he", centre)
            for lemma, y in test:
                scores.append(est.sigmoid(est.SLOPE * (theta - est.difficulty(lemma, "he"))))
                labels.append(y)
                who.append(person)
    loss, brier, ece = calibration(scores, labels)
    base = sum(labels) / len(labels)
    base_brier = sum((base - y) ** 2 for y in labels) / len(labels)
    print(f"- pooled AUC {auc(scores, labels):.3f}")
    for person in sorted(readers):
        mine = [(s, y) for s, y, w in zip(scores, labels, who, strict=True) if w == person]
        known = sum(y for _, y in mine)
        print(
            f"  - reader {person}: {len(mine)} words, {len(mine) - known} not known, AUC "
            f"{auc([s for s, _ in mine], [y for _, y in mine]):.3f}"
        )
    print(f"- log loss {loss:.3f}, Brier {brier:.3f} (base rate {base:.3f}: {base_brier:.3f})")
    print(f"- expected calibration error {ece:.3f}\n")


def corpus(folder: Path) -> list[Counter[str]]:
    """Each Hebrew text built in a folder, as its lemmas' running counts: names, numbers
    and one-letter clitics out, as the index counts them."""
    texts: list[Counter[str]] = []
    for annotation in sorted(folder.rglob("annotation.json")):
        try:
            loaded = json.loads(annotation.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not str(loaded.get("language") or "").startswith("he"):
            continue
        tally: Counter[str] = Counter()
        for tokens in (loaded.get("tokens") or {}).values():
            for token in tokens:
                lemma = str(token.get("lemma") or "")
                if not lemma or not HEBREW.search(lemma) or not a_word(lemma):
                    continue
                if not_vocabulary(token.get("pos"), token.get("entity")):
                    continue
                tally[lemma] += 1
        if sum(tally.values()) >= 100:
            texts.append(tally)
    return texts


#: The simulated truth: knowing falls off a little more steeply than the estimate says,
#: but a word's own difficulty is off its frequency by `WORD_NOISE` and each reader's luck
#: on it by `LUCK`, so the estimate's frequency-only view is honestly wrong.
TRUE_SLOPE = 1.0
WORD_NOISE = 1.0
LUCK = 0.7
CHECK_WORDS = 36
CHECK_MADE_UP = 8


def simulate(texts: list[Counter[str]], readers: int, seed: int = 7) -> None:
    rng = random.Random(seed)
    lexicon = sorted({lemma for text in texts for lemma in text})
    b = {lemma: est.difficulty(lemma, "he") for lemma in lexicon}
    own = {lemma: rng.gauss(0, WORD_NOISE) for lemma in lexicon}
    totals = [sum(text.values()) for text in texts]
    by_band: dict[int, list[str]] = {}
    for lemma in lexicon:
        if b[lemma] < math.log(est.UNRANKED_AT):
            by_band.setdefault(min(5, int((b[lemma] - math.log(50)) / 1.0)), []).append(lemma)
    rungs = [250, 900, 1800, 3000, 4500, 6500, 9000, 12000]

    def share(text: int, says: dict[str, float]) -> float:
        return sum(n * says.get(lemma, 0.0) for lemma, n in texts[text].items()) / totals[text]

    print(f"## Simulated readers ({readers} each way, {len(texts)} Hebrew texts)\n")
    print(
        "MAE is points of running-word coverage over every unread text. In band is how "
        "often the chooser's first pick truly sits at 90–99.5%, and where any text does.\n"
    )
    print(
        "| read | check | MAE marks | MAE estimate | bias | first pick in band, marks"
        " | estimate | truth | words: true / estimated |"
    )
    print("|---|---|---|---|---|---|---|---|---|")
    for history in (0, 2, 8):
        for check in ("none", "plain", "corrected"):
            if history and check == "plain":
                continue
            errors_marks: list[float] = []
            errors_est: list[float] = []
            bias: list[float] = []
            hits = {"marks": 0, "estimate": 0, "truth": 0}
            sizes: list[tuple[int, int]] = []
            for _ in range(readers):
                vocabulary = math.exp(rng.uniform(math.log(300), math.log(12000)))
                theta = math.log(vocabulary) + est.FORMS_PER_LEMMA
                truth = {
                    lemma: rng.random()
                    < est.sigmoid(TRUE_SLOPE * (theta - b[lemma] - own[lemma] + rng.gauss(0, LUCK)))
                    for lemma in lexicon
                }
                diligence = rng.uniform(0.2, 0.95)
                words: list[tuple[str, int | None, str]] = []
                looked: set[str] = set()
                met: set[str] = set()
                true_share = [
                    sum(n for lemma, n in text.items() if truth[lemma]) / totals[at]
                    for at, text in enumerate(texts)
                ]
                order = sorted(range(len(texts)), key=lambda at: abs(true_share[at] - 0.92))
                read = set(order[:history])
                marked: dict[str, int] = {}
                for at in read:
                    for lemma in texts[at]:
                        met.add(lemma)
                        if lemma in marked:
                            continue
                        if truth[lemma]:
                            if rng.random() < diligence:
                                marked[lemma] = 9
                        elif rng.random() < 0.6:
                            looked.add(lemma)
                            if rng.random() < 0.3:
                                marked[lemma] = 1
                words = [(lemma, status, "") for lemma, status in marked.items()]
                items = est.evidence(words, looked, met)
                if check != "none":
                    over = rng.uniform(0.0, 0.3)
                    picked = [
                        rng.choice(by_band[band])
                        for band in sorted(by_band)
                        for _ in range(CHECK_WORDS // len(by_band))
                    ]
                    said_made_up = sum(rng.random() < over for _ in range(CHECK_MADE_UP))
                    guess = (said_made_up + 0.25) / (CHECK_MADE_UP + 5)
                    for lemma in picked:
                        yes = truth[lemma] or rng.random() < over
                        items.append(
                            est.Evidence(lemma, yes, 1.0, guess if check == "corrected" else 0)
                        )
                said = math.log(vocabulary) + rng.gauss(0, 0.6)
                named = min(rungs, key=lambda r: abs(math.log(r) - said))
                centre = est.prior(None)
                if rng.random() < 0.7:
                    centre = math.log(named) + est.FORMS_PER_LEMMA
                fitted = est.fit(items, "he", centre)
                sizes.append((round(vocabulary), round(math.exp(fitted - est.FORMS_PER_LEMMA))))
                by_marks = {lemma: 1.0 for lemma, status in marked.items() if status == 9}
                by_estimate = {
                    lemma: (
                        1.0
                        if marked.get(lemma) == 9
                        else 0.0
                        if lemma in marked
                        else est.sigmoid(est.SLOPE * (fitted - b[lemma]))
                    )
                    for lemma in lexicon
                }
                unread = [at for at in range(len(texts)) if at not in read]
                marks_share = {at: share(at, by_marks) for at in unread}
                est_share = {at: share(at, by_estimate) for at in unread}
                for at in unread:
                    errors_marks.append(abs(marks_share[at] - true_share[at]) * 100)
                    errors_est.append(abs(est_share[at] - true_share[at]) * 100)
                    bias.append((est_share[at] - true_share[at]) * 100)
                for name, said in (
                    ("marks", marks_share),
                    ("estimate", est_share),
                    ("truth", {at: true_share[at] for at in unread}),
                ):
                    first = min(unread, key=lambda at: choose.key(said[at]))
                    if choose.fit(true_share[first]) == choose.BAND:
                        hits[name] += 1
            ratio = statistics.median(e / t for t, e in sizes)
            print(
                f"| {history} | {check} | {statistics.mean(errors_marks):.1f} | "
                f"{statistics.mean(errors_est):.1f} | {statistics.mean(bias):+.1f} | "
                f"{hits['marks'] / readers:.0%} | "
                f"{hits['estimate'] / readers:.0%} | {hits['truth'] / readers:.0%} | "
                f"median ratio {ratio:.2f} |"
            )
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--accounts", type=Path, help="an accounts database to hold out from")
    parser.add_argument("--texts", type=Path, help="a folder of built texts to simulate over")
    parser.add_argument("--readers", type=int, default=200)
    args = parser.parse_args()
    if args.accounts:
        held_out(args.accounts.expanduser())
    if args.texts:
        simulate(corpus(args.texts.expanduser()), args.readers)


if __name__ == "__main__":
    main()
