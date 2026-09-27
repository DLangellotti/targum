"""Is the Hebrew stress right? Scored against the accents the Masoretes already wrote.

`annotate/pronounce.py` says what this measures, in its own words: fed a word without a
stress mark, phonikud "puts the stress on the last syllable and is right about two words
in three". מֶלֶךְ and מָלַךְ come back identically stressed. That is the reading every
modern text on the shelf gets — every transcript, every import, everything that is not the
accented Tanakh — and since Gemini TTS ignores nikkud and the prompt is the only lever,
the reading is the only place the stress can be fixed at all.

**The gold set costs nothing and was already here.** A Masoretic accent sits on the
stressed syllable; `pronounce.stressed()` already reads one off. So the measurement is:
take a word that carries a placed accent, take the accent off, ask what the stress is, and
compare with what the accent said. No labelling, no spend on the gold, and OSHB is on disk
already. It is also public text, which is the other reason to start here: no import of
anybody's private reading reaches a new vendor (targum-internal#309).

**The one way this eval can lie is by leaving a taam in the state**, which would let the
model read the answer off the page instead of working it out. `_clean` raises rather than
sends, because the dangerous version of this run is the one that passes.

What is scored, all over the words that carry a single placed accent and more than one
vowel:

- `default_accuracy`: the last syllable, every time — what phonikud does today, and the
  number the rest are read against.
- `stress_accuracy`: the model's pick, ungated.
- `stress_precision`: of the picks at or above `--confidence`, the share that are right.
- `stress_coverage`: of all the words, the share that got a right pick at or above it.

The last two are the pair `evals/floors.json` already keeps for Russian, and for the same
reason: a wrong mark is worse than no mark, so precision gates and coverage is what it
costs (targum-internal#260).

    .venv/bin/python scripts/eval_hebrew_stress.py --baseline-only
    TYPESAFE_API_KEY=... .venv/bin/python scripts/eval_hebrew_stress.py --words 2000

`--baseline-only` needs no key and no network: it prints the number the model has to beat.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from targum import evals  # noqa: E402
from targum.annotate import oshb  # noqa: E402
from targum.annotate.pronounce import HATAMA, METEG, stressed  # noqa: E402
from targum.vocalize.base import LETTERS, has_taamim, strip_taamim  # noqa: E402

ENDPOINT = "https://api.typesafe.ai/v1/systemone"
KEY = "TYPESAFE_API_KEY"
CORPUS = "tanakh-taamim"
STAGE = "stress"

#: Charged per input token, and output is free: $42 per billion in, so this is dollars
#: per token. Printed at the end because a run that spends says what it spent.
PER_TOKEN = 42 / 1_000_000_000

#: The vowels that can carry a stress. Shva (U+05B0) is not among them — a shva syllable
#: has no stress to take — and dagesh (U+05BC) is not a vowel at all. Qamats qatan
#: (U+05C7) is, on the rare occasions a text writes it out.
VOWELS = frozenset([*range(0x05B1, 0x05BC), 0x05C7])

#: Prose by default. Psalms, Proverbs and Job are pointed with the other accent system,
#: whose prepositive and postpositive members are not all in `pronounce.UNPLACED`, so a
#: gold read off them would carry errors this eval could not see. `--books` takes them
#: for anyone who wants to find out; the default does not decide it quietly.
PROSE = ("Gen", "Exod", "Deut", "1Sam", "Isa", "Jer")


@dataclass(frozen=True)
class Item:
    """One word to be asked about, and everything needed to score the answer."""

    ref: str
    verse: str
    word: str
    syllables: tuple[str, ...]
    gold: int

    @property
    def id(self) -> str:
        return f"{self.ref}:{self.word}"


def syllables(word: str) -> list[str] | None:
    """The word cut before the letter carrying each vowel, or None where the cut is not
    one-to-one with the vowels.

    Approximate, and only ever used to put an option in front of the model in a form a
    person could read: מֶלֶךְ as מֶ and לֶךְ. Where two vowels would open the same
    syllable the alignment between an option and a vowel breaks, and a word whose options
    do not line up with its gold is dropped rather than guessed at.
    """
    nuclei = [i for i, char in enumerate(word) if ord(char) in VOWELS]
    if len(nuclei) < 2:
        return None
    starts = []
    for at in nuclei:
        cut = at
        while cut > 0 and ord(word[cut - 1]) not in LETTERS:
            cut -= 1
        starts.append(max(0, cut - 1))
    starts[0] = 0
    if len(set(starts)) != len(starts) or starts != sorted(starts):
        return None
    ends = [*starts[1:], len(word)]
    return [word[start:end] for start, end in zip(starts, ends, strict=True)]


def gold_syllable(accented: str) -> int | None:
    """Which syllable the accent stresses, counted from the start, or None where the
    accents do not say — `pronounce.stressed` returns None for an unplaced accent and for
    a word carrying several, and neither is a guess worth making."""
    marked = stressed(accented)
    if marked is None:
        return None
    at = marked.find(HATAMA)
    if at < 0:
        return None
    return sum(1 for char in marked[:at] if ord(char) in VOWELS) - 1


def collect(books: tuple[str, ...]) -> list[Item]:
    """Every scorable word of these books, with its verse for context."""
    out: list[Item] = []
    for code in books:
        for ref, words in oshb.verses(code):
            verse = " ".join(strip_taamim(word.text.replace(METEG, "")) for word in words)
            for word in words:
                accented = word.text.replace(METEG, "")
                if not has_taamim(accented):
                    continue
                gold = gold_syllable(accented)
                if gold is None:
                    continue
                bare = strip_taamim(accented)
                parts = syllables(bare)
                if parts is None or not 0 <= gold < len(parts):
                    continue
                out.append(Item(ref, verse, bare, tuple(parts), gold))
    return out


def sample(items: list[Item], count: int) -> list[Item]:
    """A fixed sample: ordered by a hash of the word and its reference, so a rerun scores
    the same words and two runs can be compared."""
    items.sort(key=lambda item: hashlib.sha256(item.id.encode()).hexdigest())
    return items[:count]


def place(index: int, total: int) -> str:
    """Where a syllable sits, said rather than counted. `jev-1.13` reads an instruction
    literally and does not count reliably, so each option is told its own position."""
    from_end = total - 1 - index
    if from_end == 0:
        return "the last syllable"
    if from_end == 1:
        return "the syllable before the last"
    if from_end == 2:
        return "the third syllable from the end"
    return f"the syllable {from_end} from the end, counting the last as none"


def question(item: Item) -> dict[str, object]:
    """One Choice over the syllables of one word.

    The options are the syllables as written, so the model picks a thing it can see rather
    than a number it has to work out. Where a word writes the same syllable twice the
    second one is marked, because an option map cannot hold a key twice.
    """
    criteria: dict[str, str] = {}
    for index, part in enumerate(item.syllables):
        name = part
        while name in criteria:
            name += "‎"
        criteria[name] = place(index, len(item.syllables))
    return {
        "type": "choice",
        "instructions": (
            f"The Hebrew word {item.word} appears in the sentence at `verse`. "
            "It is written with its vowels but without its stress. "
            "Which of its syllables is the stressed one, as the word is read in this "
            "sentence? Each option is one syllable of the word, written out, and says "
            "where in the word it sits."
        ),
        "criteria": criteria,
    }


def _clean(payload: dict[str, object]) -> str:
    """The request as JSON, refusing to send an accent.

    A taam sitting in the state is the one way this measurement can flatter itself: the
    accent is the answer, so a model that can see one is not being asked the question. It
    raises rather than skips, because a run that quietly scored a few thousand words off
    their own answer would pass, and passing is what would make it dangerous.
    """
    body = json.dumps(payload, ensure_ascii=False)
    if has_taamim(body):
        raise SystemExit("a Masoretic accent reached the request; the gold is the answer")
    return body


def ask(batch: list[Item], model: str, key: str, retries: int = 4) -> tuple[dict[str, dict], int]:
    """One request per verse: every word of it, asked together against the verse they
    share. The verse is the state the whole batch needs, which is what keeps it out of
    the "large state full of irrelevant detail" the model card warns about."""
    payload = {
        "state": {"verse": batch[0].verse},
        "model": model,
        "questions": {item.id: question(item) for item in batch},
    }
    body = _clean(payload).encode("utf-8")
    request = urllib.request.Request(
        ENDPOINT,
        data=body,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(request, timeout=60) as answer:
                got = json.loads(answer.read())
            return got.get("answers", {}), int(got.get("usage", {}).get("input_tokens", 0))
        except urllib.error.HTTPError as error:
            if error.code not in (429, 500, 502, 503, 504) or attempt == retries - 1:
                raise
            wait = float(error.headers.get("retry-after") or 2**attempt)
            time.sleep(wait)
        except urllib.error.URLError:
            if attempt == retries - 1:
                raise
            time.sleep(2**attempt)
    return {}, 0


def picked(answer: dict, item: Item) -> tuple[int | None, float]:
    """Which syllable the model picked, as an index, and how sure it was."""
    choice = answer.get("choice")
    confidence = float(answer.get("confidence") or 0.0)
    names = list(question(item)["criteria"])  # type: ignore[arg-type]
    if choice in names:
        return names.index(str(choice)), confidence
    return None, confidence


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--words", type=int, default=2000)
    parser.add_argument("--books", nargs="+", default=list(PROSE))
    parser.add_argument("--model", default="jev-latest")
    parser.add_argument("--confidence", type=float, default=0.8)
    parser.add_argument("--ledger", type=Path, default=evals.DEFAULT)
    parser.add_argument("--baseline-only", action="store_true")
    parser.add_argument("--dry", action="store_true")
    args = parser.parse_args()

    if not oshb.available():
        raise SystemExit("OSHB is not on disk; run `targum fetch oshb` first")

    items = sample(collect(tuple(args.books)), args.words)
    if not items:
        raise SystemExit("no scorable words in those books")
    default_right = sum(item.gold == len(item.syllables) - 1 for item in items)
    today = date.today().isoformat()
    note = f"books={','.join(args.books)} words={len(items)}"

    rows = [
        evals.Row(
            today,
            STAGE,
            "phonikud/2",
            "phonikud/2",
            "default_accuracy",
            round(default_right / len(items), 4),
            len(items),
            CORPUS,
            note + "; the last syllable every time, which is what phonikud does unmarked",
        )
    ]

    if not args.baseline_only:
        key = os.environ.get(KEY, "")
        if not key:
            raise SystemExit(f"{KEY} is not set; --baseline-only needs no key")
        by_verse: dict[str, list[Item]] = {}
        for item in items:
            by_verse.setdefault(item.ref, []).append(item)
        right = placed = placed_right = tokens = 0
        for done, batch in enumerate(by_verse.values(), start=1):
            answers, used = ask(batch, args.model, key)
            tokens += used
            for item in batch:
                index, confidence = picked(answers.get(item.id, {}), item)
                hit = index == item.gold
                right += hit
                if confidence >= args.confidence:
                    placed += 1
                    placed_right += hit
            if done % 50 == 0:
                print(f"{done} of {len(by_verse)} verses", flush=True)
        rows += [
            evals.Row(
                today,
                STAGE,
                args.model,
                args.model,
                "stress_accuracy",
                round(right / len(items), 4),
                len(items),
                CORPUS,
                note,
            ),
            evals.Row(
                today,
                STAGE,
                args.model,
                args.model,
                "stress_precision",
                round(placed_right / max(1, placed), 4),
                placed,
                CORPUS,
                f"{note}; confidence>={args.confidence}",
            ),
            evals.Row(
                today,
                STAGE,
                args.model,
                args.model,
                "stress_coverage",
                round(placed_right / len(items), 4),
                len(items),
                CORPUS,
                f"{note}; confidence>={args.confidence}",
            ),
        ]
        print(f"{tokens} input tokens, ${tokens * PER_TOKEN:.4f}", flush=True)

    for row in rows:
        print(f"{row.metric:18} {row.score:.4f}  n={row.n}  {row.system}", flush=True)
    if not args.dry:
        evals.append(rows, args.ledger)
        print(f"appended {len(rows)} rows to {args.ledger}")


if __name__ == "__main__":
    main()
