"""Can the stress rule get its morphology without OSHB? Step 3 of targum-internal#325.

`stress-rule/1` (`eval_hebrew_stress.mil_el`) scores 0.9630 on the held-out 3,000 words
of `tanakh-taamim-v2` when it reads OSHB's hand tagging and 0.9137 when it reads only the
pointing. A modern text has no OSHB, so the gap between the two is what a tagger has to
close, and this measures two that cost nothing:

- **DICTA** (`rule_accuracy_dicta`): `dictabert-joint`, the Hebrew annotator targum
  already runs (`annotate/dicta.py`), read over each verse unpointed, the way it reads
  every Hebrew text on the shelf. Its part of speech, person, gender, number, tense and
  pronoun suffix are written into OSHB's code shape (`code_of`) and handed to the same
  rule unchanged. DICTA tags no binyan, and the rule never asks for one.
- **A small tagger** (`rule_accuracy_small_tagger`): a logistic regression over the
  word's letters and vowels, trained on words 3,001 to 23,000 of the sample's order — the
  slice the rule was written against — to predict the few morphological facts the rule
  reads. It never sees the held-out 3,000. `rule_accuracy_small_tagger_dicta` is the
  same tagger reading DICTA's tagging as features too.

The small tagger learns OSHB's tags, which are the Bible's grammar: it is the stronger
number here and the less certain one on a modern text. DICTA is the other way round.

Both are eval only. Nothing shipped reads either: `phonikud/2` and `SCHEMA_VERSION` are
unchanged, and shipping is a rename David schedules.

**There is no modern stress gold.** Every number here is on the Tanakh, whose accents are
the only human-marked Hebrew stress on disk. DICTA was trained on modern Hebrew, so the
Tanakh is the harder text for it, not the easier.

    .venv/bin/python scripts/eval_stress_tagger.py

DICTA's reading of the verses is cached under the model directory, so a second run
scores in seconds. No key and no network beyond the weights already on disk.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from collections.abc import Callable, Iterable
from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from targum import evals  # noqa: E402
from targum.annotate import oshb  # noqa: E402
from targum.paths import model_dir  # noqa: E402


def _stress() -> Any:
    """`eval_hebrew_stress`, loaded from beside this file: the gold, the sample and the
    rule are that script's, and scoring them twice would be two golds."""
    spec = importlib.util.spec_from_file_location(
        "eval_hebrew_stress", ROOT / "scripts" / "eval_hebrew_stress.py"
    )
    assert spec and spec.loader
    loaded = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("eval_hebrew_stress", loaded)
    spec.loader.exec_module(loaded)
    return loaded


stress = _stress()

STAGE = "stress"
CORPUS = stress.CORPUS
HELD = 3000
TRAIN = 20000

#: The letters DICTA is given: the consonants and nothing else, so it reads the verse the
#: way it reads an unpointed modern text. The maqaf goes, and the words it joined are two.
LETTERS = frozenset(chr(code) for code in range(0x05D0, 0x05EB))


def bare(word: str) -> str:
    return "".join(char for char in word if char in LETTERS)


# DICTA's morphology into OSHB's code shape, which is all `mil_el` reads.
TENSES = {"Past": "p", "Fut": "i", "Imp": "v", "Beinoni": "r"}
GENDERS = {"Masc": "m", "Fem": "f"}
NUMBERS = {"Sing": "s", "Plur": "p", "Dual": "d"}


def _png(feats: dict[str, str]) -> str:
    """Person, gender and number as OSHB writes them: `3ms`, `1cs` — the first person
    is common, whatever gender DICTA guessed for it."""
    person = feats.get("Person", "")
    gender = "c" if person == "1" else GENDERS.get(feats.get("Gender", ""), "c")
    return f"{person}{gender}{NUMBERS.get(feats.get('Number', ''), 's')}"


def code_of(token: dict[str, Any], sequential: bool = False) -> tuple[str, str]:
    """One DICTA token as OSHB's (code, suffix): `Vxp1cs` and `Sp3ms`.

    The binyan is written `x`, because DICTA tags none and the rule never reads it. A
    noun's state is written `a`, for the same reason. `sequential` reads a perfect behind
    a vav as the vav-consecutive perfect (`q`), which only the Bible has: the stress of
    וְשָׁמַרְתָּ moves to the end, and the rule's `perfect 1cs/2ms` is for the plain one.
    """
    morph = token.get("morph") or {}
    pos = morph.get("pos") or ""
    feats = morph.get("feats") or {}
    code = ""
    if pos == "VERB" or (pos == "AUX" and feats.get("Tense")):
        tense = TENSES.get(feats.get("Tense", ""), "")
        if sequential and tense == "p" and "CCONJ" in (morph.get("prefixes") or []):
            tense = "q"
        if tense == "r":
            gender = GENDERS.get(feats.get("Gender", ""), "m")
            code = f"Vxr{gender}{NUMBERS.get(feats.get('Number', ''), 's')}a"
        elif tense:
            code = f"Vx{tense}{_png(feats)}"
        else:
            code = "Vx"
    elif pos in ("NOUN", "PROPN", "ADJ"):
        gender = GENDERS.get(feats.get("Gender", ""), "c")
        lead = "A" if pos == "ADJ" else "N"
        code = f"{lead}x{gender}{NUMBERS.get(feats.get('Number', ''), 's')}a"
    elif pos:
        code = pos[:1]
    suffix = ""
    if morph.get("suffix") and morph.get("suffix_feats"):
        suffix = f"Sp{_png(morph['suffix_feats'])}"
    return code, suffix


def cache_path() -> Path:
    from targum.annotate.dicta import REVISION

    return model_dir() / "evals" / f"stress-dicta-{REVISION[:12]}.jsonl"


def dicta_read(verses: dict[str, list[str]], path: Path) -> dict[str, list[dict[str, Any]]]:
    """Each verse's DICTA tokens, one per OSHB word, read once and cached.

    A verse whose tokens do not line up one to one with its words is kept as an empty
    list, and every word of it is scored as untagged: the rule falls back to the pointing.
    """
    done: dict[str, list[dict[str, Any]]] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            done[row["ref"]] = row["tokens"]
    todo = [ref for ref in verses if ref not in done]
    if todo:
        from targum.annotate.dicta import DictaLemmatizer

        class _Nobody:
            name = "none"

        model, tokenizer = DictaLemmatizer(other=_Nobody()).model()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as out:
            for start in range(0, len(todo), 16):
                refs = todo[start : start + 16]
                texts = [" ".join(word for word in verses[ref] if word) for ref in refs]
                read = model.predict(texts, tokenizer, output_style="json")
                for ref, said in zip(refs, read, strict=True):
                    tokens = _aligned(verses[ref], said.get("tokens") or [])
                    done[ref] = tokens
                    out.write(json.dumps({"ref": ref, "tokens": tokens}, ensure_ascii=False))
                    out.write("\n")
                if (start // 16) % 50 == 0:
                    print(f"dicta: {start + len(refs)} of {len(todo)} verses", flush=True)
    return done


def _aligned(words: list[str], tokens: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """DICTA's tokens against the verse's words: the morphology of each, or {} for a
    word DICTA read as something else."""
    out: list[dict[str, Any]] = []
    queue = [token for token in tokens if bare(token.get("token") or "")]
    cursor = 0
    for word in words:
        if not word:
            out.append({})
            continue
        # A token read differently is skipped over, and the next few are looked at for
        # this word, so one mismatch does not untag the rest of the verse.
        ahead = next(
            (
                at
                for at in range(cursor, min(cursor + 3, len(queue)))
                if bare(queue[at].get("token") or "") == word
            ),
            None,
        )
        if ahead is None:
            out.append({})
            cursor += 1
            continue
        out.append({"morph": queue[ahead].get("morph") or {}})
        cursor = ahead + 1
    return out


# The small tagger: a logistic regression per morphological fact the rule reads.

#: What the rule reads, as the facts a tagger has to supply. Each is predicted on its own,
#: as a class, from the pointed word alone.
FACTS = ("pos", "tense", "png", "suffix")


def facts_of(code: str, suffix: str) -> dict[str, str]:
    """OSHB's code for one word as the facts the small tagger learns."""
    pieces = suffix.split("/") if suffix else []
    pronoun = next((piece for piece in pieces if piece.startswith("Sp")), "")
    return {
        "pos": code[:1] or "-",
        "tense": code[2:3] if code.startswith("V") else "-",
        "png": code[3:6] if code.startswith("V") and len(code) >= 6 else "-",
        "suffix": ("Sd" if "Sd" in pieces else pronoun) or "-",
    }


def code_from(facts: dict[str, str]) -> tuple[str, str]:
    """The facts back into OSHB's code shape, for `mil_el`."""
    if facts["pos"] == "V":
        code = f"Vx{facts['tense']}{facts['png'] if facts['png'] != '-' else ''}"
    else:
        code = facts["pos"] if facts["pos"] != "-" else ""
    return code, facts["suffix"] if facts["suffix"] != "-" else ""


def features(word: str) -> list[str]:
    """The pointed word as sparse features: its first and last letters with their
    points, its last syllables, and the word itself. Character n-grams of the end are
    where Hebrew writes its person, number and suffixes."""
    out = [f"w={word}", f"n={len(stress.syllables(word) or ())}"]
    for size in range(1, 9):
        out.append(f"end{size}={word[-size:]}")
        out.append(f"start{size}={word[:size]}")
    letters = bare(word)
    for size in range(1, 5):
        out.append(f"lend{size}={letters[-size:]}")
        out.append(f"lstart{size}={letters[:size]}")
    out.append(f"letters={letters}")
    return out


class SmallTagger:
    """One logistic regression per fact, over hashed features of the pointed word, and
    of anything else `extra` says about it — DICTA's reading, in the variant that asks
    whether the two together beat either."""

    def __init__(self, extra: Callable[[Any], list[str]] | None = None) -> None:
        from sklearn.feature_extraction import FeatureHasher

        self.hasher = FeatureHasher(n_features=2**18, input_type="string")
        self.models: dict[str, Any] = {}
        self.extra = extra

    def _matrix(self, items: list[Any]) -> Any:
        extra = self.extra or (lambda item: [])
        return self.hasher.transform(features(item.word) + extra(item) for item in items)

    def fit(self, items: Iterable[Any]) -> SmallTagger:
        from sklearn.linear_model import LogisticRegression

        rows = list(items)
        matrix = self._matrix(rows)
        for fact in FACTS:
            labels = [facts_of(item.code, item.suffix)[fact] for item in rows]
            model = LogisticRegression(max_iter=2000, C=4.0)
            model.fit(matrix, labels)
            self.models[fact] = model
        return self

    def tag(self, items: list[Any]) -> list[tuple[str, str]]:
        matrix = self._matrix(items)
        guesses = {fact: self.models[fact].predict(matrix) for fact in FACTS}
        return [
            code_from({fact: str(guesses[fact][at]) for fact in FACTS}) for at in range(len(items))
        ]


def score(items: list[Any], tags: list[tuple[str, str]]) -> float:
    right = sum(
        stress.by_rule(replace(item, code=code, suffix=suffix)) == item.gold
        for item, (code, suffix) in zip(items, tags, strict=True)
    )
    return round(right / max(1, len(items)), 4)


def _token(item: Any, read: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    tokens = read.get(item.ref) or []
    return tokens[item.at] if item.at < len(tokens) else {}


def dicta_features(read: dict[str, list[dict[str, Any]]]) -> Callable[[Any], list[str]]:
    """DICTA's reading of a word as features for the small tagger."""

    def said(item: Any) -> list[str]:
        token = _token(item, read)
        if not token:
            return ["d=none"]
        morph = token.get("morph") or {}
        code, suffix = code_of(token, sequential=True)
        out = [
            f"d_code={code}",
            f"d_suffix={suffix}",
            f"d_pos={morph.get('pos')}",
            f"d_prefixes={'+'.join(morph.get('prefixes') or [])}",
        ]
        out += [f"d_{key}={value}" for key, value in (morph.get("feats") or {}).items()]
        return out

    return said


def dicta_tags(
    items: list[Any], read: dict[str, list[dict[str, Any]]], sequential: bool
) -> tuple[list[tuple[str, str]], int]:
    """Each item's DICTA tagging as OSHB's code, and how many words DICTA left untagged."""
    out: list[tuple[str, str]] = []
    missing = 0
    for item in items:
        token = _token(item, read)
        if not token:
            missing += 1
            out.append(("", ""))
            continue
        out.append(code_of(token, sequential))
    return out, missing


#: The system each number is about, and the sentence its row carries.
SAID = {
    "rule_accuracy_dicta": ("stress-rule/1+dicta", "the rule, DICTA's tagging of the verse"),
    "rule_accuracy_dicta_sequential": (
        "stress-rule/1+dicta-seq",
        "the rule, DICTA's tagging, a perfect behind a vav read as vav-consecutive",
    ),
    "rule_accuracy_small_tagger": (
        "stress-rule/1+small-tagger",
        "the rule, a logistic tagger over the pointed word, trained on words 3,001-23,000",
    ),
    "rule_accuracy_small_tagger_dicta": (
        "stress-rule/1+small-tagger-dicta",
        "the rule, the logistic tagger reading DICTA's tagging as well as the word",
    ),
    "dicta_untagged_share": ("dicta", "words DICTA's tokens did not line up with"),
}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--books", nargs="+", default=list(stress.PROSE))
    parser.add_argument("--ledger", type=Path, default=evals.DEFAULT)
    parser.add_argument("--cache", type=Path, default=None)
    parser.add_argument("--dry", action="store_true")
    args = parser.parse_args(argv)

    if not oshb.available():
        raise SystemExit("OSHB is not on disk; run `targum models fetch scripture` first")
    books = tuple(args.books)
    everything = stress.sample(stress.collect(books), HELD + TRAIN)
    held, train = everything[:HELD], everything[HELD:]

    wanted = {item.ref for item in everything}
    verses = {
        ref: [bare(word.text) for word in words]
        for code in books
        for ref, words in oshb.verses(code)
        if ref in wanted
    }
    read = dicta_read(verses, args.cache or cache_path())

    measured: dict[str, tuple[float, int]] = {}
    plain, missing = dicta_tags(held, read, sequential=False)
    measured["dicta_untagged_share"] = (round(missing / len(held), 4), len(held))
    measured["rule_accuracy_dicta"] = (score(held, plain), len(held))
    sequential, _ = dicta_tags(held, read, sequential=True)
    measured["rule_accuracy_dicta_sequential"] = (score(held, sequential), len(held))
    tagger = SmallTagger().fit(train)
    measured["rule_accuracy_small_tagger"] = (score(held, tagger.tag(held)), len(held))
    both = SmallTagger(extra=dicta_features(read)).fit(train)
    measured["rule_accuracy_small_tagger_dicta"] = (score(held, both.tag(held)), len(held))

    # The same, on the slice the rule and the choices here were made against: printed
    # for the reader, never written, because it is not held out.
    seen_plain, _ = dicta_tags(train, read, sequential=False)
    seen_seq, _ = dicta_tags(train, read, sequential=True)
    oshb_seen = score(train, [(item.code, item.suffix) for item in train])
    print(
        f"(the training slice, n={len(train)}: OSHB {oshb_seen}, "
        f"DICTA {score(train, seen_plain)}, DICTA sequential {score(train, seen_seq)})"
    )

    today = date.today().isoformat()
    note = evals.pinned(
        f"books={','.join(books)} words={len(held)}",
        [oshb.root() / f"{code}.json" for code in books],
    )
    rows = []
    for metric, (value, n) in measured.items():
        system, said = SAID[metric]
        rows.append(
            evals.Row(today, STAGE, system, system, metric, value, n, CORPUS, f"{note}; {said}")
        )
    for row in rows:
        print(f"{row.metric:32} {row.score:.4f}  n={row.n}  {row.system}", flush=True)
    if not args.dry:
        evals.append(rows, args.ledger)
        print(f"appended {len(rows)} rows to {args.ledger}")


if __name__ == "__main__":
    main()
