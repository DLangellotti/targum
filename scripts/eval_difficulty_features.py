"""Which word features beat frequency alone in the estimate's difficulty (targum-internal#613).

`estimate.difficulty` began as the log of a word's place in the frequency list. Each
feature here is added to it on its own, as `b = log rank + w · x`, and kept only if it
beats that baseline on the laptop's own marks, held out:

- **pos**: the part of speech DICTA gave the lemma most often in the built texts, as
  verb, adjective, adverb and closed class against nouns (`pos` also gives names and
  lemmas no built text has their own weight, which measures where a mark came from rather
  than the word, so `pos-content` is the honest one);
- **loan-gloss**: a loanword list drawn here from the glosses, a Hebrew lemma whose
  English gloss its letters transliterate (`draw_loans`), written to
  `~/.targum/research/loanwords/` because the glosses are private;
- **loan-lexicon**: the `borrowed` flag of targum's own root lexicon (`root_card`);
- **root**: the share of the word's root family (`root_card.family_root`) the reader has
  marked known among their other training words, and whether the family has any.

Five folds of each reader's marks (known against steps 1–3). On the four, each reader's
theta and the shared weights are fitted in turn (the weights by Newton, with a small
ridge); the fifth is predicted. `--transfer` also fits each reader's weights on the other
readers only. Every row is set against the baseline on the same folds, with a 95% paired
bootstrap over the held-out words.

    PYTHONPATH=src .venv/bin/python scripts/eval_difficulty_features.py \\
        --accounts ~/.targum/targum.db --texts targum-out --transfer

Offline and free: no model is called. The accounts database is read through a copy.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import re
import shutil
import sqlite3
import tempfile
from collections import Counter
from collections.abc import Callable, Sequence
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from eval_estimate import auc, calibration

from targum import estimate as est
from targum.annotate import frequency, root_card
from targum.annotate.verb_roots import root_for
from targum.touchstones import a_word

LOANS = Path.home() / ".targum" / "research" / "loanwords"
CLOSED = {"ADP", "PRON", "DET", "CCONJ", "SCONJ", "AUX", "PART", "NUM", "INTJ"}

# -- what the built texts say of each lemma --------------------------------------------


def gather(folder: Path) -> dict[str, Any]:
    """Each Hebrew lemma's commonest part of speech and verb root, and each lemma's
    commonest English gloss, from the texts built in a folder."""
    pos: dict[str, Counter[str]] = {}
    roots: dict[str, Counter[str]] = {}
    gloss: dict[str, Counter[str]] = {}
    for annotation in sorted(folder.rglob("annotation.json")):
        try:
            loaded = json.loads(annotation.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not str(loaded.get("language") or "").startswith("he"):
            continue
        for tokens in (loaded.get("tokens") or {}).values():
            for token in tokens:
                lemma = str(token.get("lemma") or "")
                if not lemma:
                    continue
                tag = str(token.get("pos") or "")
                pos.setdefault(lemma, Counter())[tag] += 1
                if tag == "VERB":
                    root = root_for(lemma, token.get("root"), "VERB", "he")
                    if root:
                        roots.setdefault(lemma, Counter())[root] += 1
        glossary = annotation.parent / "glossary.en.json"
        if glossary.is_file():
            try:
                entries = json.loads(glossary.read_text(encoding="utf-8")).get("entries") or {}
            except (OSError, json.JSONDecodeError):
                entries = {}
            for lemma, said in entries.items():
                if said:
                    gloss.setdefault(lemma, Counter())[str(said)] += 1
    return {
        "pos": {k: c.most_common(1)[0][0] for k, c in pos.items()},
        "verb_root": {k: c.most_common(1)[0][0] for k, c in roots.items()},
        "gloss": {k: c.most_common(1)[0][0] for k, c in gloss.items()},
    }


# -- a loanword list from the glosses ---------------------------------------------------

#: Hebrew letters as consonant classes; א ה ו י ע are left out as the vowel letters.
HEBREW = dict(zip("בגדזחטכךלמםנןסעפףצץקרשת", "BGDSKTKKLMMNNS PPSSKRST", strict=True))
#: ג׳ צ׳ ז׳: j, ch and zh.
GERESH = {"ג": "G", "צ": "K", "ז": "S"}


def hebrew_skeleton(word: str) -> str:
    letters = [c for c in word if "א" <= c <= "ת" or c in "׳'"]
    out = []
    for at, c in enumerate(letters):
        if c in "׳'":
            continue
        after = letters[at + 1] if at + 1 < len(letters) else ""
        mapped = GERESH[c] if after in "׳'" and c in GERESH else HEBREW.get(c, "").strip()
        out.append(mapped)
    return re.sub(r"(.)\1+", r"\1", "".join(out))


def english_skeleton(word: str) -> str:
    w = re.sub(r"[^a-z]", "", word.lower())
    for old, new in (("ph", "p"), ("th", "t"), ("sh", "s"), ("ch", "k"), ("ck", "k")):
        w = w.replace(old, new)
    w = w.replace("qu", "k").replace("x", "ks")
    w = re.sub(r"c(?=[eiy])", "s", w)
    for old, new in (("c", "k"), ("q", "k"), ("j", "g"), ("z", "s"), ("f", "p")):
        w = w.replace(old, new)
    w = w.replace("v", "b").replace("w", "b")
    w = re.sub(r"[aeiouyh]", "", w)
    return re.sub(r"(.)\1+", r"\1", w).upper()


def loan_score(lemma: str, gloss: str) -> tuple[float, str]:
    """How closely the lemma's consonants spell one word of its gloss, and which word.
    Three consonants at least, the first the same, a capitalised word (a name) never."""
    hebrew = hebrew_skeleton(lemma)
    if len(hebrew) < 3:
        return 0.0, ""
    best = (0.0, "")
    for piece in re.split(r"[,;/()]| or ", gloss):
        piece = re.sub(r"^\s*(to|a|an|the)\s+", "", piece.strip(), flags=re.I)
        for word in piece.split():
            if not word[0].islower():
                continue
            english = english_skeleton(word)
            if len(english) < 3 or english[0] != hebrew[0]:
                continue
            ratio = SequenceMatcher(None, hebrew, english).ratio()
            if ratio > best[0]:
                best = (ratio, word)
    return best


def draw_loans(glosses: dict[str, str], threshold: float = 0.85) -> dict[str, list[Any]]:
    """Unpointed Hebrew lemmas whose English gloss is a near-transliteration of them, with
    the gloss, the word it matched and the score. Names are left out."""
    out: dict[str, list[Any]] = {}
    for lemma, gloss in glosses.items():
        if not re.search("[א-ת]", lemma) or re.search("[֑-ׇ]", lemma):
            continue
        if re.search(r"\bname\b|\bsurname\b|descendant|inhabitant", gloss, re.I):
            continue
        ratio, word = loan_score(lemma, gloss)
        if ratio >= threshold:
            out[lemma] = [gloss, word, round(ratio, 3)]
    return dict(sorted(out.items(), key=lambda item: -item[1][2]))


# -- the held-out comparison ------------------------------------------------------------


def golden(score: Callable[[float], float]) -> float:
    g = (math.sqrt(5) - 1) / 2
    low, high = est.LOW, est.HIGH
    left, right = high - g * (high - low), low + g * (high - low)
    at_left, at_right = score(left), score(right)
    while high - low > 1e-4:
        if at_left < at_right:
            low, left, at_left = left, right, at_right
            right = low + g * (high - low)
            at_right = score(right)
        else:
            high, right, at_right = right, left, at_left
            left = high - g * (high - low)
            at_left = score(left)
    return (low + high) / 2


def fit_theta(bs: Sequence[float], ys: Sequence[int], centre: float) -> float:
    def score(theta: float) -> float:
        total = -((theta - centre) ** 2) / (2 * est.PRIOR_SD**2)
        for b, y in zip(bs, ys, strict=True):
            p = est.sigmoid(est.SLOPE * (theta - b))
            total += math.log(max(p if y else 1 - p, 1e-12))
        return total

    return golden(score)


def solve(a: list[list[float]], b: list[float]) -> list[float]:
    n = len(b)
    m = [row[:] + [b[i]] for i, row in enumerate(a)]
    for c in range(n):
        pivot = max(range(c, n), key=lambda r: abs(m[r][c]))
        m[c], m[pivot] = m[pivot], m[c]
        for r in range(n):
            if r != c and m[c][c]:
                f = m[r][c] / m[c][c]
                m[r] = [x - f * y for x, y in zip(m[r], m[c], strict=True)]
    return [m[i][n] / m[i][i] if m[i][i] else 0.0 for i in range(n)]


def fit_weights(
    rows: list[tuple[float, float, list[float], int]], dim: int, ridge: float = 1.0
) -> list[float]:
    """w for p = σ(s(θ − b0 − w·x)), each row's θ held fixed."""
    w = [0.0] * dim
    s = est.SLOPE
    for _ in range(25):
        grad = [-ridge * wi for wi in w]
        hess = [[ridge if i == j else 0.0 for j in range(dim)] for i in range(dim)]
        for theta, b0, x, y in rows:
            p = est.sigmoid(s * (theta - b0 - sum(a * c for a, c in zip(w, x, strict=True))))
            for i in range(dim):
                grad[i] -= (y - p) * s * x[i]
                for j in range(dim):
                    hess[i][j] += p * (1 - p) * s * s * x[i] * x[j]
        step = solve(hess, grad)
        w = [a + b for a, b in zip(w, step, strict=True)]
        if max(abs(v) for v in step) < 1e-6:
            break
    return w


class Features:
    def __init__(self, facts: dict[str, Any], gloss_loans: set[str]) -> None:
        self.facts = facts
        self.gloss_loans = gloss_loans
        lexicon = root_card.lexicon("he")
        self.lexicon_loans = (
            {k for k, row in lexicon.hebrew.items() if row.borrowed} if lexicon else set()
        )
        self._family: dict[str, str] = {}

    def family(self, lemma: str) -> str:
        if lemma not in self._family:
            pos = self.facts["pos"].get(lemma)
            page = self.facts["verb_root"].get(lemma, "") if pos == "VERB" else ""
            self._family[lemma] = root_card.family_root(lemma, pos, page, "he")
        return self._family[lemma]

    def of(self, kind: str, lemma: str, families: dict[str, dict[str, int]]) -> list[float]:
        tag = self.facts["pos"].get(lemma, "")
        group = "CLOSED" if tag in CLOSED else tag if tag in ("NOUN", "VERB", "ADJ", "ADV") else ""
        if kind == "pos":
            group = group or ("PROPN" if tag == "PROPN" else "NONE")
            return [float(group == g) for g in ("VERB", "ADJ", "ADV", "CLOSED", "PROPN", "NONE")]
        if kind == "pos-content":
            return [float(group == g) for g in ("VERB", "ADJ", "ADV", "CLOSED")]
        if kind == "loan-gloss":
            return [float(lemma in self.gloss_loans)]
        if kind == "loan-lexicon":
            return [float(lemma in self.lexicon_loans)]
        if kind in ("root", "root-share"):
            family = self.family(lemma)
            marks = [y for other, y in families.get(family, {}).items() if other != lemma]
            if not family or not marks:
                return [0.0] if kind == "root-share" else [0.0, 0.0]
            share = (sum(marks) + 0.5) / (len(marks) + 1) - 0.5
            return [share] if kind == "root-share" else [share, 1.0]
        return []


Fold = tuple[
    dict[int, list[tuple[str, int]]], dict[int, list[list[float]]], dict[str, float], float
]


def thetas(fold: Fold, w: list[float], persons: list[int]) -> dict[int, float]:
    """Each reader's theta on their training words, with the features weighted by w."""
    train, xs, base, centre = fold
    out = {}
    for p in persons:
        bs = [
            base[lemma] + sum(a * c for a, c in zip(w, x, strict=True))
            for (lemma, _), x in zip(train[p], xs[p], strict=True)
        ]
        out[p] = fit_theta(bs, [y for _, y in train[p]], centre)
    return out


def learn(fold: Fold, persons: list[int]) -> list[float]:
    """The shared weights, fitted in turn with the readers' thetas."""
    train, xs, base, _ = fold
    dim = len(next(iter(xs.values()))[0])
    w = [0.0] * dim
    for _ in range(4 if dim else 0):
        fitted = thetas(fold, w, persons)
        rows = [
            (fitted[p], base[lemma], x, y)
            for p in persons
            for (lemma, y), x in zip(train[p], xs[p], strict=True)
        ]
        w = fit_weights(rows, dim)
    return w


def held_out(
    readers: dict[int, list[tuple[str, int]]],
    features: Features,
    kind: str,
    *,
    transfer: bool = False,
    folds: int = 5,
) -> tuple[list[float], list[int], list[int], list[list[float]]]:
    centre = est.prior(None)
    base = {
        lemma: math.log(frequency.rank(lemma, "he") or est.UNRANKED_AT)
        for marks in readers.values()
        for lemma, _ in marks
    }
    shuffled = {}
    for person, marks in readers.items():
        mine = marks[:]
        random.Random(person).shuffle(mine)
        shuffled[person] = mine
    scores: list[float] = []
    labels: list[int] = []
    who: list[int] = []
    learned: list[list[float]] = []
    for fold in range(folds):
        train = {
            p: [o for at, o in enumerate(m) if at % folds != fold] for p, m in shuffled.items()
        }
        test = {p: m[fold::folds] for p, m in shuffled.items()}
        families: dict[int, dict[str, dict[str, int]]] = {}
        for p, marks in train.items():
            families[p] = {}
            for lemma, y in marks:
                if family := features.family(lemma):
                    families[p].setdefault(family, {})[lemma] = y
        xs = {
            p: [features.of(kind, lemma, families[p]) for lemma, _ in m] for p, m in train.items()
        }

        fold_data = (train, xs, base, centre)
        if transfer:
            weights = {p: learn(fold_data, [q for q in readers if q != p]) for p in readers}
        else:
            shared = learn(fold_data, list(readers))
            weights = dict.fromkeys(readers, shared)
            learned.append(shared)
        for p in readers:
            theta = thetas(fold_data, weights[p], [p])[p]
            for lemma, y in test[p]:
                x = features.of(kind, lemma, families[p])
                b = base[lemma] + sum(a * c for a, c in zip(weights[p], x, strict=True))
                scores.append(est.sigmoid(est.SLOPE * (theta - b)))
                labels.append(y)
                who.append(p)
    return scores, labels, who, learned


def row(
    name: str,
    result: tuple[list[float], list[int], list[int], list[list[float]]],
    base: tuple[list[float], list[int], list[int], list[list[float]]] | None,
) -> str:
    scores, labels, who, learned = result
    loss, brier, ece = calibration(scores, labels)
    per = []
    for person in sorted(set(who)):
        mine = [(s, y) for s, y, w in zip(scores, labels, who, strict=True) if w == person]
        if len(mine) - sum(y for _, y in mine) >= 20:
            per.append(f"{person}: {auc([s for s, _ in mine], [y for _, y in mine]):.3f}")
    line = (
        f"| {name} | {auc(scores, labels):.3f} | {', '.join(per)} | {loss:.4f} "
        f"| {brier:.4f} | {ece:.3f} |"
    )
    if base is None:
        return line + " | | |"
    rng = random.Random(1)
    n = len(labels)
    gaps_auc: list[float] = []
    gaps_brier: list[float] = []
    for _ in range(300):
        pick = [rng.randrange(n) for _ in range(n)]
        ys = [labels[i] for i in pick]
        gaps_auc.append(auc([scores[i] for i in pick], ys) - auc([base[0][i] for i in pick], ys))
        gaps_brier.append(
            sum((scores[i] - labels[i]) ** 2 - (base[0][i] - labels[i]) ** 2 for i in pick) / n
        )
    gaps_auc.sort()
    gaps_brier.sort()
    weights = ""
    if learned and learned[0]:
        weights = ", ".join(
            f"{sum(w[i] for w in learned) / len(learned):+.2f}" for i in range(len(learned[0]))
        )
    return (
        line
        + f" {auc(scores, labels) - auc(base[0], base[1]):+.4f}"
        + f" [{gaps_auc[7]:+.4f}, {gaps_auc[292]:+.4f}]"
        + f" | [{gaps_brier[7]:+.4f}, {gaps_brier[292]:+.4f}] | {weights} |"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--accounts", type=Path, required=True)
    parser.add_argument("--texts", type=Path, required=True)
    parser.add_argument("--transfer", action="store_true")
    parser.add_argument(
        "--kinds", default="pos,pos-content,loan-gloss,loan-lexicon,root,root-share"
    )
    args = parser.parse_args()
    facts = gather(args.texts.expanduser())
    loans = draw_loans(facts["gloss"])
    LOANS.mkdir(parents=True, exist_ok=True)
    (LOANS / "loans-he-en.json").write_text(
        json.dumps({"rule": "gloss-skeleton>=0.85", "lemmas": loans}, ensure_ascii=False, indent=0),
        encoding="utf-8",
    )
    with tempfile.TemporaryDirectory() as scratch:
        copy = Path(scratch) / "accounts.db"
        shutil.copy(args.accounts.expanduser(), copy)
        db = sqlite3.connect(copy)
        rows = db.execute(
            "SELECT person, lemma, status FROM word"
            " WHERE language = 'he' AND gone = 0 AND status IN (1, 2, 3, 9)"
        ).fetchall()
        db.close()
    readers: dict[int, list[tuple[str, int]]] = {}
    for person, lemma, status in rows:
        if a_word(lemma):
            readers.setdefault(person, []).append((lemma, 1 if status == 9 else 0))
    readers = {p: m for p, m in readers.items() if len(m) >= 50}
    features = Features(facts, set(loans))
    marked = [lemma for m in readers.values() for lemma, _ in m]
    print(f"## Difficulty features, held out ({args.accounts})\n")
    print(
        f"{len(marked)} marked words, {sum(1 for m in readers.values() for _, y in m if not y)} "
        f"not known. Part of speech for {sum(1 for w in marked if w in facts['pos'])}; "
        f"on the gloss loanword list ({len(loans)} lemmas) "
        f"{sum(1 for w in marked if w in features.gloss_loans)}; borrowed in the lexicon "
        f"({len(features.lexicon_loans)}) {sum(1 for w in marked if w in features.lexicon_loans)}; "
        f"in a root family {sum(1 for w in marked if features.family(w))}.\n"
    )
    print(
        "| feature | AUC | per reader | log loss | Brier | ECE "
        "| ΔAUC [95%] | ΔBrier [95%] | weights |"
    )
    print("|---|---|---|---|---|---|---|---|---|")
    base = held_out(readers, features, "base")
    print(row("frequency alone (#1041)", base, None))
    for kind in args.kinds.split(","):
        print(row(kind, held_out(readers, features, kind), base), flush=True)
        if args.transfer:
            print(
                row(
                    f"{kind}, weights from the others",
                    held_out(readers, features, kind, transfer=True),
                    base,
                ),
                flush=True,
            )


if __name__ == "__main__":
    main()
