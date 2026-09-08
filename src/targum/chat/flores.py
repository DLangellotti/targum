"""FLORES+, fetched to score the chat's recast against and for nothing else.

The recast eval (`scripts/eval_recast.py`) sets the chat's `> ` line against a Hebrew
rendering a person wrote of the same English. Its reference has been Tatoeba, where three
volunteers wrote 96% of the pool. FLORES+ is the other kind of reference: 2,009 English
sentences from 842 web articles, each rendered into Hebrew by a professional translator
— 997 in `dev`, 1,012 in `devtest` — and the same sentences across two hundred
languages, so a number here can be set beside a number anybody else publishes
(targum-internal#221).

**It is CC BY-SA 4.0, and that is why this module does exactly one thing with it.**
ShareAlike is the one door `LICENSING.md` keeps shut on text, and the IAHLT treebanks
(`annotate/gold.py`) set the pattern this follows to the letter: evaluation only, fetched
beside the gold sets, nothing served, nothing trained on, nothing derived shipped. Its
whole contribution to targum is a row in `evals/ledger.jsonl` with `corpus=flores-plus`.

**It is gated.** Hugging Face asks a person to accept the dataset's conditions before the
files download, so the fetch carries the operator's own read token, from `HF_TOKEN` in
the environment (`.env`, which is never committed). Without one the fetch stops and says
where to click, rather than trying anonymously and reporting a 401 as a network fault.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import NamedTuple

from ..annotate import gold
from ..errors import TargumError
from ..paths import ensure, write_atomic

CREDIT = "FLORES+, Open Language Data Initiative"
LICENCE = "CC BY-SA 4.0"
DATASET = "openlanguagedata/flores_plus"
CONDITIONS = f"https://huggingface.co/datasets/{DATASET}"
SOURCE = f"https://huggingface.co/datasets/{DATASET}/resolve/main/{{split}}/{{file}}.jsonl"

#: The two languoids the eval joins, by the language tag the rest of targum uses. The
#: file name is FLORES+'s own: ISO 639-3 and the script.
FILES: dict[str, str] = {"en": "eng_Latn", "he": "heb_Hebr"}

#: What FLORES+ splits into. `devtest` is what a published number is taken on, so it is
#: the default; `dev` is there for anybody tuning a prompt who wants to keep the other
#: split clean.
SPLITS = ("dev", "devtest")
DEFAULT_SPLIT = "devtest"

#: Where the operator's Hugging Face read token is looked for, first name wins. The first
#: is what the `huggingface_hub` tools read; the second is its older spelling.
TOKEN_VARIABLES = ("HF_TOKEN", "HUGGINGFACE_HUB_TOKEN")


class Pair(NamedTuple):
    """One sentence in both languages. `id` is FLORES+'s own, aligned across languoids."""

    id: str
    en: str
    he: str


def root() -> Path:
    """Beside the treebanks the annotator is scored against, and for the same reason: a
    `cache clear` has no business removing a file that took a token and a network to get."""
    return gold.root()


def _path(split: str, language: str) -> Path:
    return root() / f"flores-{split}-{language}.jsonl"


def available(splits: Iterable[str] = (DEFAULT_SPLIT,)) -> bool:
    return all(_path(split, language).is_file() for split in splits for language in FILES)


def token() -> str | None:
    for name in TOKEN_VARIABLES:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return None


def fetch(
    splits: Iterable[str] = (DEFAULT_SPLIT,),
    notify: Callable[[str], None] | None = None,
) -> int:
    """Download what is not already here. Returns how many files arrived or were found.

    Idempotent and interruptible the way `gold.fetch` is: a file already on disk is left
    alone. The token is read only when a file is actually missing, so a machine that has
    the files never needs one.
    """
    import httpx

    say = notify or (lambda _message: None)
    ensure(root())
    got = 0
    for split in splits:
        if split not in SPLITS:
            raise TargumError(f"No such FLORES+ split: {split}.", f"Known: {', '.join(SPLITS)}")
        for language, file in FILES.items():
            path = _path(split, language)
            if path.is_file():
                got += 1
                continue
            key = token()
            if key is None:
                raise TargumError(
                    "FLORES+ is gated on Hugging Face, and no token is set.",
                    f"Accept the conditions at {CONDITIONS} while signed in, then put a "
                    f"read token in {TOKEN_VARIABLES[0]} (in .env, never committed).",
                )
            say(f"Fetching FLORES+ {split} {file}…")
            url = SOURCE.format(split=split, file=file)
            try:
                answer = httpx.get(
                    url,
                    headers={"Authorization": f"Bearer {key}"},
                    timeout=180.0,
                    follow_redirects=True,
                )
            except Exception as bad:  # noqa: BLE001 - network and HTTP both land here
                raise TargumError(f"Could not fetch FLORES+ {split} {file}.", str(bad)) from bad
            if answer.status_code in (401, 403):
                raise TargumError(
                    f"Hugging Face refused FLORES+ {split} {file} ({answer.status_code}).",
                    f"The token is set but has not been granted this dataset: accept the "
                    f"conditions at {CONDITIONS} with the account the token belongs to.",
                )
            if answer.status_code != 200:
                raise TargumError(
                    f"Could not fetch FLORES+ {split} {file}.", f"HTTP {answer.status_code}"
                )
            write_atomic(path, answer.text)
            got += 1
    return got


def parse(english: str, hebrew: str) -> list[Pair]:
    """The two languoid files joined on FLORES+'s `id`, in the English file's order.

    A sentence present in one file and not the other is left out rather than paired
    with nothing: the eval sends the English and scores against the Hebrew, and either
    half missing is a pair that cannot be measured.
    """
    rendered: dict[str, str] = {}
    for line in hebrew.splitlines():
        if line.strip():
            row = json.loads(line)
            rendered[str(row["id"])] = str(row.get("text", "")).strip()
    out: list[Pair] = []
    for line in english.splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        key = str(row["id"])
        text = str(row.get("text", "")).strip()
        if text and rendered.get(key):
            out.append(Pair(key, text, rendered[key]))
    return out


def load(split: str = DEFAULT_SPLIT) -> list[Pair]:
    """Every English sentence of a split with its Hebrew rendering."""
    texts: dict[str, str] = {}
    for language in FILES:
        path = _path(split, language)
        if not path.is_file():
            raise TargumError(
                f"FLORES+ ({split}) is not downloaded.",
                "Run: targum models fetch flores",
            )
        texts[language] = path.read_text(encoding="utf-8")
    return parse(texts["en"], texts["he"])


def describe() -> str:
    return f"{CREDIT} · {LICENCE} · {CONDITIONS}"
