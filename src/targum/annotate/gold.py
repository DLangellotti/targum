"""Hand-tagged modern Hebrew, fetched to score an annotator against and for nothing else.

Every number targum has ever given for its Hebrew annotation — 75% agreement, 26% of
verbs with a root, 3.7% declined — was one annotator measured against another. Agreement
is not accuracy: two models that make the same mistake agree, and the treebank Stanza was
trained on could not be the judge of Stanza. What was missing was a text somebody tagged
by hand, that neither model was trained on, in the register the shelf is mostly in.

The IAHLT treebanks are that text. `UD_Hebrew-IAHLTwiki` is five thousand Wikipedia
sentences and `UD_Hebrew-IAHLTknesset` is twenty-eight hundred from the Knesset record,
both with the lemma, the part of speech and the binyan of every word written down by a
person. Together they are a hundred and seventy thousand tokens of contemporary Hebrew,
which is enough to say whether a change to the annotator made it better.

**They are CC BY-SA 4.0, and that is why this module does exactly one thing with them.**
ShareAlike is the one door `LICENSING.md` keeps shut on text: a derivative of the
treebank served commercially would carry the licence into the corpus. So nothing here is
trained on, nothing here ships, and nothing here is read at build time. The files go
beside the language models, a scorecard is computed on a laptop, and the treebank's
contribution to targum is a number. Evaluation on a laptop is non-commercial use, which
is the line targum-internal#147 drew for the same reason.

The parse below is the whole of CoNLL-U that a scorecard needs: which run of the
sentence's text is one written word, what that word's dictionary form is, what it is, and
how it is built. The rest of the columns — heads, relations, the empty nodes — are left
where they are.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import NamedTuple

from ..errors import TargumError
from ..paths import ensure, model_dir, write_atomic

#: Named where the licence requires it. The credit is the treebank's, the licence is the
#: reason it is never more than a measurement.
CREDIT = "IAHLT, through Universal Dependencies"
LICENCE = "CC BY-SA 4.0"

SOURCE = (
    "https://raw.githubusercontent.com/UniversalDependencies/"
    "UD_Hebrew-{repo}/master/he_{corpus}-ud-{split}.conllu"
)

#: The two corpora, by the short name the scorecard uses.
CORPORA: dict[str, str] = {
    "iahltwiki": "IAHLTwiki",
    "iahltknesset": "IAHLTknesset",
}

#: The splits a score is computed on. Development and test, not training: training is the
#: bulk of the treebank, and a scorecard that took twenty minutes to run would be run
#: less. Either can be asked for, and "all" is spelled out where somebody wants it.
SPLITS = ("dev", "test")
ALL_SPLITS = ("train", "dev", "test")

#: The one-letter words Hebrew writes onto the front of the next one. A sub-token in the
#: treebank is a prefix when it is one of these letters and tagged as a function word;
#: `את` inside `אותו` is neither, and is the word itself.
_CLITICS = frozenset("והבלכמש")
_PREFIX_POS = frozenset({"ADP", "CCONJ", "SCONJ", "DET"})
_NOT_A_WORD = frozenset({"PUNCT", "SYM"})


class GoldToken(NamedTuple):
    """One written word of a gold sentence, as its annotators recorded it."""

    #: Where the word sits in the sentence text, so it can be paired with what an
    #: annotator returned for the same span.
    start: int
    end: int
    surface: str
    #: The dictionary form of the word under its prefixes. The third-person masculine
    #: singular past for a verb, whatever form the text has it in.
    lemma: str
    #: The Universal part of speech of that same word.
    upos: str
    #: `HebBinyan` as the treebank writes it — PAAL, PIEL, HIFIL … — or "" where the
    #: word has none, which is every word that is not a verb.
    binyan: str
    #: The prefix letters split off the front, in order. Empty for most words.
    prefixes: tuple[str, ...]
    #: Whether a pronoun is written onto the end.
    suffix: bool
    #: The morphology of the content word, in the pipe format the rest of targum reads.
    feats: str


class GoldSentence(NamedTuple):
    id: str
    text: str
    tokens: tuple[GoldToken, ...]


def root() -> Path:
    """Beside the language models, and for the same reason `oshb` is: a `cache clear`
    has no business removing a file that took a network to get."""
    return model_dir() / "gold"


def _path(corpus: str, split: str) -> Path:
    return root() / f"{corpus}-{split}.conllu"


def available(corpora: Iterable[str] | None = None, splits: Iterable[str] = SPLITS) -> bool:
    return all(_path(corpus, split).is_file() for corpus in corpora or CORPORA for split in splits)


def fetch(
    corpora: Iterable[str] | None = None,
    splits: Iterable[str] = SPLITS,
    notify: Callable[[str], None] | None = None,
) -> int:
    """Download what is not already here. Returns how many files arrived or were found.

    Idempotent and interruptible, the way `oshb.fetch` is: a file already on disk is
    left alone, so this is safe to re-run.
    """
    import httpx

    say = notify or (lambda _message: None)
    ensure(root())
    got = 0
    for corpus in corpora or CORPORA:
        repo = CORPORA.get(corpus)
        if repo is None:
            raise TargumError(f"No such gold corpus: {corpus}.", f"Known: {', '.join(CORPORA)}")
        for split in splits:
            path = _path(corpus, split)
            if path.is_file():
                got += 1
                continue
            say(f"Fetching {corpus} {split}…")
            url = SOURCE.format(repo=repo, corpus=corpus, split=split)
            try:
                answer = httpx.get(url, timeout=180.0, follow_redirects=True)
                answer.raise_for_status()
            except Exception as bad:  # noqa: BLE001 - network and HTTP both land here
                raise TargumError(f"Could not fetch {corpus} {split}.", str(bad)) from bad
            write_atomic(path, answer.text)
            got += 1
    return got


def load(corpus: str, splits: Iterable[str] = SPLITS) -> list[GoldSentence]:
    """Every sentence of a corpus that could be laid over its own text."""
    out: list[GoldSentence] = []
    for split in splits:
        path = _path(corpus, split)
        if not path.is_file():
            raise TargumError(
                f"The gold corpus {corpus} ({split}) is not downloaded.",
                "Run: targum models fetch gold",
            )
        out.extend(parse(path.read_text(encoding="utf-8")))
    return out


def parse(conllu: str) -> list[GoldSentence]:
    """CoNLL-U into sentences whose tokens know where they sit in the text.

    A sentence whose words cannot be found in its own `# text` line, in order, is left
    out rather than guessed at. That is rare and it is the treebank's own inconsistency
    to fix; a scorecard built on a misplaced token would be scoring the wrong word.
    """
    sentences: list[GoldSentence] = []
    for block in conllu.split("\n\n"):
        lines = [line for line in block.splitlines() if line.strip()]
        if not lines:
            continue
        sentence = _sentence(lines)
        if sentence is not None:
            sentences.append(sentence)
    return sentences


class _Row(NamedTuple):
    form: str
    lemma: str
    upos: str
    feats: str


def _sentence(lines: list[str]) -> GoldSentence | None:
    sent_id = ""
    text = ""
    rows: dict[int, _Row] = {}
    order: list[tuple[int, int, str]] = []  # (first id, last id, surface) in text order
    for line in lines:
        if line.startswith("#"):
            key, _, value = line[1:].partition("=")
            key = key.strip()
            if key == "sent_id":
                sent_id = value.strip()
            elif key == "text":
                text = value.strip()
            continue
        columns = line.split("\t")
        if len(columns) < 6:
            continue
        ident, form, lemma, upos, _, feats = columns[:6]
        if "-" in ident:
            low, _, high = ident.partition("-")
            order.append((int(low), int(high), form))
            continue
        if "." in ident or not ident.isdigit():
            # An empty node, which is syntax rather than a word.
            continue
        number = int(ident)
        rows[number] = _Row(
            form, "" if lemma == "_" else lemma, upos, "" if feats == "_" else feats
        )
        if not order or number > order[-1][1]:
            order.append((number, number, form))
    if not text or not rows:
        return None

    tokens: list[GoldToken] = []
    cursor = 0
    for first, last, surface in order:
        start = text.find(surface, cursor)
        if start < 0:
            return None
        end = start + len(surface)
        cursor = end
        parts = [rows[number] for number in range(first, last + 1) if number in rows]
        if not parts:
            return None
        token = _token(start, end, surface, parts)
        if token is not None:
            tokens.append(token)
    return GoldSentence(sent_id, text, tuple(tokens))


def _token(start: int, end: int, surface: str, parts: list[_Row]) -> GoldToken | None:
    prefixes: list[str] = []
    rest = list(parts)
    while len(rest) > 1 and rest[0].upos in _PREFIX_POS and set(rest[0].form) <= _CLITICS:
        prefixes.append(rest[0].form)
        rest.pop(0)
    content = rest[0]
    if content.upos in _NOT_A_WORD:
        return None
    feats = dict(part.partition("=")[::2] for part in content.feats.split("|") if "=" in part)
    return GoldToken(
        start=start,
        end=end,
        surface=surface,
        lemma=content.lemma,
        upos=content.upos,
        binyan=feats.get("HebBinyan", ""),
        prefixes=tuple(prefixes),
        suffix=any(part.upos == "PRON" for part in rest[1:]),
        feats=content.feats,
    )


def describe() -> str:
    """One line for a report, so the licence travels with the number."""
    return json.dumps({"credit": CREDIT, "licence": LICENCE, "corpora": sorted(CORPORA)})
