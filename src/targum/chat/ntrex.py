"""NTREX-128, fetched to score the chat's recast against and for nothing else.

The second reference for the recast eval, in a second register. FLORES+ (`chat/flores.py`)
is sentences from Wikipedia-shaped articles; NTREX-128 is the WMT 2019 news test set —
1,997 English sentences, each rendered into Hebrew by a professional translator, and the
same lines in 128 languages — so the recast number is not one corpus's house style, the
way the pointing eval needed Ben-Yehuda beside DICTA's own set (targum-internal#222).

**It is CC BY-SA 4.0, and that is why this module does exactly one thing with it**, on
the terms `annotate/gold.py` set for the treebanks: fetched beside the gold sets,
nothing served, nothing trained on, nothing derived shipped. Its whole contribution to
targum is a row in `evals/ledger.jsonl` with `corpus=ntrex-128`.

**Not gated.** Two plain text files on GitHub, one line per sentence, aligned by line
number — the English source and the Hebrew reference. No token, unlike FLORES+.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from pathlib import Path

from ..annotate import gold
from ..errors import TargumError
from ..paths import ensure, write_atomic
from .flores import Pair

CREDIT = "NTREX-128, Microsoft Translator"
LICENCE = "CC BY-SA 4.0"
REPOSITORY = "https://github.com/MicrosoftTranslator/NTREX"
SOURCE = "https://raw.githubusercontent.com/MicrosoftTranslator/NTREX/main/NTREX-128/{file}"

#: The two files the eval joins, by the language tag the rest of targum uses. The
#: English is the *source* file — what the translators were given — not one of the
#: three English references beside it.
FILES: dict[str, str] = {"en": "newstest2019-src.eng.txt", "he": "newstest2019-ref.heb.txt"}


def root() -> Path:
    """Beside the treebanks the annotator is scored against, and for the same reason."""
    return gold.root()


def _path(language: str) -> Path:
    return root() / f"ntrex-{language}.txt"


def available() -> bool:
    return all(_path(language).is_file() for language in FILES)


def fetch(notify: Callable[[str], None] | None = None) -> int:
    """Download what is not already here. Returns how many files arrived or were found.

    Idempotent and interruptible the way `gold.fetch` is: a file already on disk is left
    alone.
    """
    import httpx

    say = notify or (lambda _message: None)
    ensure(root())
    got = 0
    for language, file in FILES.items():
        path = _path(language)
        if path.is_file():
            got += 1
            continue
        say(f"Fetching NTREX-128 {file}…")
        try:
            answer = httpx.get(SOURCE.format(file=file), timeout=180.0, follow_redirects=True)
            answer.raise_for_status()
        except Exception as bad:  # noqa: BLE001 - network and HTTP both land here
            raise TargumError(f"Could not fetch NTREX-128 {file}.", str(bad)) from bad
        write_atomic(path, answer.text)
        got += 1
    return got


def parse(english: str, hebrew: str) -> list[Pair]:
    """The two files joined by line number, which is how NTREX aligns them.

    The files must be the same length, or the pairing is off by one from the first gap
    onward and every score after it is of the wrong sentence: said, rather than zipped
    short. A line blank on either side is left out; its id is its line number, so a
    saved recast can be found again.
    """
    left = english.splitlines()
    right = hebrew.splitlines()
    if len(left) != len(right):
        raise TargumError(
            f"NTREX-128 files disagree on length: {len(left)} English lines, {len(right)} Hebrew.",
            "Delete both from the gold directory and fetch again.",
        )
    return [
        Pair(str(n), en.strip(), he.strip())
        for n, (en, he) in enumerate(zip(left, right, strict=True), 1)
        if en.strip() and he.strip()
    ]


def load() -> list[Pair]:
    """Every English sentence with its Hebrew rendering."""
    texts: dict[str, str] = {}
    for language in FILES:
        path = _path(language)
        if not path.is_file():
            raise TargumError("NTREX-128 is not downloaded.", "Run: targum models fetch ntrex")
        texts[language] = path.read_text(encoding="utf-8")
    return parse(texts["en"], texts["he"])


def describe(pairs: Iterable[Pair] | None = None) -> str:
    return f"{CREDIT} · {LICENCE} · {REPOSITORY}"
