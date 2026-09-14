"""Are the Russian stress marks right? Scored on stressed Russian written by people.

`vocalize/stress.py` marks a word only where silero-stress and OpenRussian's tables agree,
because a learner believes a printed mark (targum-internal#260). This measures what that
rule costs and buys, on sentences a person stressed by hand: the usage examples and
quotations of English Wiktionary's Russian entries, which print every stress.

**Evaluation only.** Wiktionary's text is CC BY-SA 4.0 and GFDL. The sentences are read
from Kaikki.org's extraction of it into the model directory, scored here, and contribute
numbers to `evals/ledger.jsonl` and nothing else. Nothing is trained on them and none
ships — the discipline `LICENSING.md` keeps for the treebanks.

**A caveat the numbers carry.** OpenRussian's tables were built from Wiktionary's too, so
on the words both know the dictionary half of the rule is not independent of this gold.
silero-stress is: its data is its own. So `silero_precision`, silero on its own over every
word, is the independent number, and the rule's `stress_precision` is the one the reader
sees.

**What is scored.** Each sentence goes in with its acutes removed and its ё kept, the way
Russian is usually printed.

- `stress_precision`: of the marks placed, the share on the vowel the person stressed.
- `stress_coverage`: of the words that need a mark — more than one vowel, no ё, stressed
  in the gold — the share that got the right one.
- `silero_precision`: silero alone, on the same words, before anything confirms it.
- `yo_precision` and `yo_recall`: the same sentences with ё written as е, and ё restored
  where the rule restores it.

    .venv/bin/python scripts/eval_stress.py --sentences 1000

Fetching the sentences reads Kaikki's 900 MB Russian file once, as a stream, and keeps
only the fully stressed sentences.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import unicodedata
import urllib.request
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from targum import evals  # noqa: E402
from targum.annotate import openrussian  # noqa: E402
from targum.paths import model_dir  # noqa: E402
from targum.vocalize import stress  # noqa: E402

SOURCE = "https://kaikki.org/dictionary/Russian/kaikki.org-dictionary-Russian.jsonl"
CORPUS = "wiktionary-ru"
ACUTE = stress.ACUTE
VOWELS = stress.VOWELS
WORD = re.compile(r"[А-Яа-яЁё" + ACUTE + r"]+")
#: A sentence short enough to be a phrase rather than a sentence is left out.
SHORTEST = 6


def target() -> Path:
    return model_dir() / "wiktionary-ru" / "stressed-sentences.jsonl"


def fully_stressed(text: str) -> bool:
    words = WORD.findall(text)
    if len(words) < SHORTEST:
        return False
    for word in words:
        vowels = sum(char in VOWELS for char in word)
        marks = word.count(ACUTE)
        if marks > 1 or (vowels > 1 and not marks and "ё" not in word.lower()):
            return False
    return True


def fetch() -> Path:
    path = target()
    if path.is_file():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    seen: set[str] = set()
    kept = 0
    temporary = path.with_suffix(".part")
    with urllib.request.urlopen(SOURCE, timeout=300) as answer, temporary.open("w") as out:
        for raw in answer:
            line = raw.decode("utf-8")
            if '"examples"' not in line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            for sense in entry.get("senses", []):
                for example in sense.get("examples", []):
                    text = unicodedata.normalize("NFC", str(example.get("text") or ""))
                    if text in seen or not fully_stressed(text):
                        continue
                    seen.add(text)
                    out.write(json.dumps({"text": text}, ensure_ascii=False) + "\n")
                    kept += 1
    temporary.rename(path)
    print(f"kept {kept} stressed sentences", flush=True)
    return path


def sample(path: Path, count: int) -> list[str]:
    """A fixed sample: ordered by a hash of the text, so a rerun scores the same sentences."""
    texts = [json.loads(line)["text"] for line in path.read_text(encoding="utf-8").splitlines()]
    texts.sort(key=lambda text: hashlib.sha256(text.encode()).hexdigest())
    return texts[:count]


def stressed_vowels(text: str) -> dict[int, int]:
    """Where each word of the gold starts in the unmarked text, and its stressed vowel's
    position in that word."""
    out: dict[int, int] = {}
    for match in WORD.finditer(text):
        word = match.group(0)
        start = len(text[: match.start()].replace(ACUTE, ""))
        at = word.find(ACUTE)
        if at > 0:
            out[start] = at - 1
    return out


def marks_in(text: str) -> dict[int, int]:
    """The same, for a marked output whose marks are the stage's own."""
    return stressed_vowels(text.replace(stress.DIAERESIS, ""))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--sentences", type=int, default=1000)
    parser.add_argument("--ledger", type=Path, default=evals.DEFAULT)
    parser.add_argument("--dry", action="store_true")
    args = parser.parse_args()

    from targum.vocalize.russian import StressVocalizer

    engine = StressVocalizer()
    usable, why = engine.available()
    if not usable:
        raise SystemExit(why)
    lexicon = openrussian.load()
    texts = sample(fetch(), args.sentences)

    placed = right = needed = covered = silero_placed = silero_right = 0
    yo_placed = yo_right = yo_needed = 0
    for n, gold in enumerate(texts):
        bare = gold.replace(ACUTE, "")
        proposals = engine.propose(bare)
        if proposals is None:
            continue
        truth = stressed_vowels(gold)
        marked = marks_in(stress.mark(bare, proposals, lexicon))
        for match in WORD.finditer(bare):
            start, word = match.start(), match.group(0)
            vowels = sum(char in VOWELS for char in word)
            if vowels < 2 or "ё" in word.lower():
                continue
            gold_at = truth.get(start)
            if gold_at is None:
                continue
            needed += 1
            mine = marked.get(start)
            if mine is not None:
                placed += 1
                right += mine == gold_at
                covered += mine == gold_at
            proposal = proposals.get(start)
            if proposal is not None and proposal.stress is not None:
                silero_placed += 1
                silero_right += proposal.stress == gold_at
        # ё: the same sentence with every ё written е.
        folded = bare.replace("ё", "е").replace("Ё", "Е")
        yo_proposals = engine.propose(folded)
        if yo_proposals is None:
            continue
        restored = stress.mark(folded, yo_proposals, lexicon)
        restored_letters = unicodedata.normalize("NFC", restored.replace(ACUTE, ""))
        for want, got in zip(bare, restored_letters, strict=False):
            if want in "ёЁ":
                yo_needed += 1
                yo_right += got in "ёЁ"
            if got in "ёЁ":
                yo_placed += 1
        if n and n % 200 == 0:
            print(f"{n} sentences", flush=True)

    today = date.today().isoformat()
    version = engine.name
    note = f"sentences={len(texts)}"
    rows = [
        evals.Row(
            today,
            "stress",
            "stress",
            version,
            "stress_precision",
            round(right / max(1, placed), 4),
            placed,
            CORPUS,
            note,
        ),
        evals.Row(
            today,
            "stress",
            "stress",
            version,
            "stress_coverage",
            round(covered / max(1, needed), 4),
            needed,
            CORPUS,
            note,
        ),
        evals.Row(
            today,
            "stress",
            "silero-stress",
            version,
            "silero_precision",
            round(silero_right / max(1, silero_placed), 4),
            silero_placed,
            CORPUS,
            note,
        ),
        evals.Row(
            today,
            "stress",
            "stress",
            version,
            "yo_precision",
            round(yo_right / max(1, yo_placed), 4),
            yo_placed,
            CORPUS,
            note,
        ),
        evals.Row(
            today,
            "stress",
            "stress",
            version,
            "yo_recall",
            round(yo_right / max(1, yo_needed), 4),
            yo_needed,
            CORPUS,
            note,
        ),
    ]
    for row in rows:
        print(f"{row.metric:18} {row.score:.4f}  n={row.n}", flush=True)
    if not args.dry:
        evals.append(rows, args.ledger)
        print(f"appended {len(rows)} rows to {args.ledger}")


if __name__ == "__main__":
    main()
