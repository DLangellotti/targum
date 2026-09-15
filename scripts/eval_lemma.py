"""Are the model's dictionary forms right? Scored against a treebank before a card trusts them.

French, Russian, Italian and Yiddish words are read by the model (`annotate/model_lemma.py`)
because no Stanza model for them clears the licence bar. This scores what it gives against
the Universal Dependencies dev set for each language: a sentence goes in exactly as
production sends one, and every word that comes back is set against the hand annotation.

**Evaluation only.** The treebanks are CC BY-SA or CC BY-NC-SA. Nothing is trained on
them and nothing derived from them ships: they are fetched to this machine, read here, and
contribute a number to `evals/ledger.jsonl` and nothing else — the discipline
`LICENSING.md` keeps for FLORES+ and the IAHLT treebanks.

**Three numbers per language.** `token_recall`: of the treebank's words (punctuation left
out), the share the model returned with the same characters in the same place — a word
it split or joined differently is a miss. Over the words that matched, `lemma_accuracy`
(case-insensitive) and `upos_accuracy`. A contraction the treebank splits into two
syntactic words (French *du*, Italian *della*) is scored as one word whose dictionary form
is the first part's, which is what the prompt asks for.

**And the grammar** (prompt 2, targum-internal#258). Over the matched words whose hand
annotation carries the feature, the share the model gave the same value: `case_accuracy`,
`aspect_accuracy`, `gender_accuracy`, `number_accuracy`. A word the model left without the
feature counts as wrong. A language whose treebank never marks a feature, or whose card
does not keep it (`model_lemma.KEPT`), gets no row for it. The run also prints output
tokens per word, which is the figure the quote uses (`model_lemma.TOKENS_PER_WORD_OUT`).

**Written the way texts arrive** (`--curly`, targum-internal#262). The dev sets write the
straight apostrophe; a French or Italian text usually writes ’. The same sentences with
every ' turned into ’ are scored under the treebank's name plus `-curly`, so a word
dropped at the curly one shows up as a gap between the two recalls.

**What it costs.** A few cents a language at the default sample. Nothing is read from or
written to the production cache: the question is what the model does today.

    set -a && . ./.env && set +a && \\
      .venv/bin/python scripts/eval_lemma.py --sentences 120
"""

from __future__ import annotations

import argparse
import sys
import tempfile
import urllib.request
from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from targum import evals  # noqa: E402
from targum.annotate import model_lemma  # noqa: E402
from targum.cache import Cache  # noqa: E402
from targum.models import BlockKind, Segment  # noqa: E402
from targum.paths import model_dir  # noqa: E402

#: Language, treebank name in the ledger, and the raw dev file.
TREEBANKS = {
    "fr": (
        "ud-fr-gsd",
        "https://raw.githubusercontent.com/UniversalDependencies/UD_French-GSD/master/fr_gsd-ud-dev.conllu",
    ),
    "ru": (
        "ud-ru-syntagrus",
        "https://raw.githubusercontent.com/UniversalDependencies/UD_Russian-SynTagRus/master/ru_syntagrus-ud-dev.conllu",
    ),
    "it": (
        "ud-it-isdt",
        "https://raw.githubusercontent.com/UniversalDependencies/UD_Italian-ISDT/master/it_isdt-ud-dev.conllu",
    ),
    "yi": (
        "ud-yi-yitb",
        "https://raw.githubusercontent.com/UniversalDependencies/UD_Yiddish-YiTB/master/yi_yitb-ud-dev.conllu",
    ),
}


@dataclass(frozen=True)
class Word:
    form: str
    lemma: str
    upos: str
    feats: str = ""


#: The features scored, by the metric each is written under.
SCORED = {
    "Case": "case_accuracy",
    "Aspect": "aspect_accuracy",
    "Gender": "gender_accuracy",
    "Number": "number_accuracy",
}


def feature(feats: str, name: str) -> str:
    for part in (feats or "").split("|"):
        key, _, value = part.partition("=")
        if key == name:
            return value
    return ""


def fetch(language: str) -> Path:
    """The dev file, downloaded once beside the other evaluation data."""
    name, url = TREEBANKS[language]
    target = model_dir() / "ud" / f"{name}-dev.conllu"
    if not target.is_file():
        target.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(url, timeout=60) as answer:
            target.write_bytes(answer.read())
    return target


def sentences(path: Path) -> list[tuple[str, list[Word]]]:
    """Each sentence's text and its words, a split contraction scored as the one word
    written."""
    out: list[tuple[str, list[Word]]] = []
    text = ""
    words: list[Word] = []
    covered: set[int] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("# text = "):
            text = line[len("# text = ") :]
        elif not line.strip():
            if text and words:
                out.append((text, words))
            text, words, covered = "", [], set()
        elif not line.startswith("#"):
            cells = line.split("\t")
            if len(cells) < 4:
                continue
            ident, form, lemma, upos = cells[0], cells[1], cells[2], cells[3]
            feats = cells[5] if len(cells) > 5 and cells[5] != "_" else ""
            if "." in ident:
                continue
            if "-" in ident:
                first, last = (int(n) for n in ident.split("-"))
                covered.update(range(first, last + 1))
                words.append(Word(form, "", "ADP"))
                continue
            number = int(ident)
            if number in covered:
                if words and not words[-1].lemma:
                    words[-1] = Word(words[-1].form, lemma, upos, feats)
                continue
            words.append(Word(form, lemma, upos, feats))
    return out


def spans(text: str, words: list[Word]) -> dict[tuple[int, int], Word]:
    """Each word's place in the sentence, found in order."""
    placed: dict[tuple[int, int], Word] = {}
    cursor = 0
    for word in words:
        at = text.find(word.form, cursor)
        if at < 0:
            continue
        placed[(at, at + len(word.form))] = word
        cursor = at + len(word.form)
    return placed


def curled(text: str) -> str:
    return text.replace("'", "\u2019")


def score(language: str, count: int, model: str, curly: bool = False) -> list[evals.Row]:
    corpus, _ = TREEBANKS[language]
    picked = sentences(fetch(language))[:count]
    if curly:
        corpus = f"{corpus}-curly"
        picked = [
            (curled(text), [replace(word, form=curled(word.form)) for word in words])
            for text, words in picked
        ]
    segments = [
        Segment(
            id=f"{n:04d}.000-eval",
            block_id=f"b{n:04d}",
            block_index=n,
            index=0,
            kind=BlockKind.paragraph,
            text=text,
        )
        for n, (text, _) in enumerate(picked)
    ]
    with tempfile.TemporaryDirectory() as scratch:
        reader = model_lemma.ModelLemmatizer(model, buy=True, cache=Cache(Path(scratch)))
        read = reader.lemmas(segments, language)
    gold_words = found = lemma_right = upos_right = 0
    marked = dict.fromkeys(SCORED, 0)
    agreed = dict.fromkeys(SCORED, 0)
    for segment, (text, words) in zip(segments, picked, strict=True):
        gold = {
            span: word
            for span, word in spans(text, words).items()
            if word.upos not in {"PUNCT", "SYM"}
        }
        gold_words += len(gold)
        mine = {(token.start, token.end): token for token in read.get(segment.id, [])}
        for span, word in gold.items():
            token = mine.get(span)
            if token is None:
                continue
            found += 1
            lemma_right += token.lemma.casefold() == word.lemma.casefold()
            upos_right += token.pos == word.upos
            for name in SCORED:
                gold_value = feature(word.feats, name)
                if gold_value:
                    marked[name] += 1
                    agreed[name] += feature(token.feats or "", name) == gold_value
    today = date.today().isoformat()
    version = model_lemma.provider_name(model)
    words_in = sum(len(text.split()) for text, _ in picked)
    per_word = reader.spent.output_tokens / max(1, words_in)
    note = f"sentences={len(picked)} spent=${reader.spent.cost():.3f}"
    print(f"{language}  output tokens per word {per_word:.1f}", flush=True)
    rows = [
        evals.Row(
            today,
            "lemma",
            "model-lemma",
            version,
            "token_recall",
            round(found / max(1, gold_words), 4),
            gold_words,
            corpus,
            note,
        ),
        evals.Row(
            today,
            "lemma",
            "model-lemma",
            version,
            "lemma_accuracy",
            round(lemma_right / max(1, found), 4),
            found,
            corpus,
            note,
        ),
        evals.Row(
            today,
            "lemma",
            "model-lemma",
            version,
            "upos_accuracy",
            round(upos_right / max(1, found), 4),
            found,
            corpus,
            note,
        ),
    ]
    rows.extend(
        evals.Row(
            today,
            "lemma",
            "model-lemma",
            version,
            metric,
            round(agreed[name] / marked[name], 4),
            marked[name],
            corpus,
            note,
        )
        for name, metric in SCORED.items()
        if marked[name] and name in model_lemma.KEPT.get(language, frozenset(model_lemma.FEATURES))
    )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--languages", nargs="+", default=sorted(TREEBANKS))
    parser.add_argument("--sentences", type=int, default=120)
    parser.add_argument("--model", default=model_lemma.MODEL)
    parser.add_argument("--ledger", type=Path, default=evals.DEFAULT)
    parser.add_argument("--curly", action="store_true", help="the sentences written with ’")
    parser.add_argument("--dry", action="store_true", help="print, and append nothing")
    args = parser.parse_args()
    rows: list[evals.Row] = []
    for language in args.languages:
        found = score(language, args.sentences, args.model, args.curly)
        rows.extend(found)
        for row in found:
            print(f"{language}  {row.metric:15} {row.score:.4f}  n={row.n}  {row.note}", flush=True)
    if not args.dry:
        evals.append(rows, args.ledger)
        print(f"appended {len(rows)} rows to {args.ledger}")


if __name__ == "__main__":
    main()
