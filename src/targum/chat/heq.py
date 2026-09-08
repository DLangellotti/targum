"""HeQ, fetched to score the chat's answers about a text and for nothing else.

The chat answers a question about the text on the reader's screen — Ask on the word
card, in English, about the text (`prompts.SYSTEM`) — and, in Hebrew, asks the reader
one question a turn. Neither was measured. HeQ is 30,147 reading-comprehension
questions over 4,401 paragraphs of modern Hebrew — Hebrew Wikipedia and Geektime, the
technology news site — each answered by a person with the span of the paragraph that
answers it, on SQuAD's shape (targum-internal#223). Handed a paragraph and one of its
questions, the chat's reply can be set against the span: `scripts/eval_ask.py`.

**It is CC BY 4.0**: attribution, nothing else owed, and commercial use permitted — the
licence `licensing.verdict` marks exportable. It is still used here for exactly one thing,
because that is what it is for: nothing here trains on it (#161's row is evaluation),
nothing here ships, and no build reads it. The files go beside the gold sets, the eval
runs on a developer's machine, and the credit is here and in `LICENSING.md`.

**Not gated.** The repository is public on GitHub and the files download plainly, which
is the difference from FLORES+ (`chat/flores.py`) and why there is no token here.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any, NamedTuple

from ..annotate import gold
from ..errors import TargumError
from ..paths import ensure, write_atomic

CREDIT = "HeQ, Webiks for MAFAT under the National NLP Plan of Israel"
LICENCE = "CC BY 4.0"
REPOSITORY = "https://github.com/NNLP-IL/Hebrew-Question-Answering-Dataset"
SOURCE = (
    "https://raw.githubusercontent.com/NNLP-IL/Hebrew-Question-Answering-Dataset/main/"
    "data/data%20v1.1/{file}"
)

#: The splits, by the file HeQ keeps each in. `train` is fourteen megabytes and the eval
#: never draws from it; asked for by name only.
FILES: dict[str, str] = {
    "val": "val%20v1.1.json",
    "test": "test%20v1.1.json",
    "train": "train%20v1.1.json",
}
SPLITS = ("val", "test")
DEFAULT_SPLIT = "test"


class Question(NamedTuple):
    """One question, the paragraph it is asked of, and every span a person accepted."""

    id: str
    #: "Wikipedia" or "Geektime", as the file says.
    source: str
    title: str
    context: str
    question: str
    #: The accepted spans, the main one first. Empty where the paragraph does not
    #: answer the question.
    answers: tuple[str, ...]

    @property
    def answerable(self) -> bool:
        return bool(self.answers)


def root() -> Path:
    """Beside the treebanks the annotator is scored against, and for the same reason."""
    return gold.root()


def _path(split: str) -> Path:
    return root() / f"heq-{split}.json"


def available(splits: Iterable[str] = (DEFAULT_SPLIT,)) -> bool:
    return all(_path(split).is_file() for split in splits)


def fetch(
    splits: Iterable[str] = SPLITS,
    notify: Callable[[str], None] | None = None,
) -> int:
    """Download what is not already here. Returns how many files arrived or were found.

    Idempotent and interruptible the way `gold.fetch` is: a file already on disk is left
    alone.
    """
    import httpx

    say = notify or (lambda _message: None)
    ensure(root())
    got = 0
    for split in splits:
        file = FILES.get(split)
        if file is None:
            raise TargumError(f"No such HeQ split: {split}.", f"Known: {', '.join(FILES)}")
        path = _path(split)
        if path.is_file():
            got += 1
            continue
        say(f"Fetching HeQ {split}…")
        url = SOURCE.format(file=file)
        try:
            answer = httpx.get(url, timeout=300.0, follow_redirects=True)
            answer.raise_for_status()
        except Exception as bad:  # noqa: BLE001 - network and HTTP both land here
            raise TargumError(f"Could not fetch HeQ {split}.", str(bad)) from bad
        write_atomic(path, answer.text)
        got += 1
    return got


def parse(text: str) -> list[Question]:
    """Every question in a HeQ file, in file order, answerable or not.

    SQuAD's shape: articles, each with paragraphs, each with its questions. The spans
    are kept in the order the file gives them, main answer first, and are stripped
    because a span with a trailing space is the same span.
    """
    raw: dict[str, Any] = json.loads(text)
    out: list[Question] = []
    for article in raw.get("data", []):
        source = str(article.get("source", ""))
        title = str(article.get("title", ""))
        for paragraph in article.get("paragraphs", []):
            context = str(paragraph.get("context", "")).strip()
            for asked in paragraph.get("qas", []):
                answers = tuple(
                    dict.fromkeys(
                        span
                        for span in (
                            str(one.get("text", "")).strip() for one in asked.get("answers", [])
                        )
                        if span
                    )
                )
                if asked.get("is_impossible"):
                    answers = ()
                out.append(
                    Question(
                        str(asked.get("id", "")),
                        source,
                        title,
                        context,
                        str(asked.get("question", "")).strip(),
                        answers,
                    )
                )
    return out


def load(split: str = DEFAULT_SPLIT, *, answerable: bool = True) -> list[Question]:
    """The questions of a split — those the paragraph answers, unless asked otherwise."""
    path = _path(split)
    if not path.is_file():
        raise TargumError(f"HeQ ({split}) is not downloaded.", "Run: targum models fetch heq")
    questions = parse(path.read_text(encoding="utf-8"))
    return [one for one in questions if one.answerable] if answerable else questions


def describe() -> str:
    return f"{CREDIT} · {LICENCE} · {REPOSITORY}"
