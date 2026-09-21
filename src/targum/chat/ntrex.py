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

**Not gated.** Plain text files on GitHub, one line per sentence, aligned by line
number — the English source and the references beside it. No token, unlike FLORES+.

**Every reference renders the same English source**, so any two of them are aligned to
each other by line number as well. That is what lets a *Russian* reader's line be scored
against the Hebrew a translator wrote for the same sentence, without a Russian–Hebrew
corpus existing anywhere: targum-internal#286, which asked for the Russian evals before
anything the model is told is changed.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from pathlib import Path
from typing import NamedTuple

from ..annotate import gold
from ..errors import TargumError
from ..paths import ensure, write_atomic

CREDIT = "NTREX-128, Microsoft Translator"
LICENCE = "CC BY-SA 4.0"
REPOSITORY = "https://github.com/MicrosoftTranslator/NTREX"
SOURCE = "https://raw.githubusercontent.com/MicrosoftTranslator/NTREX/main/NTREX-128/{file}"

#: The two files every run needs, by the language tag the rest of targum uses. The
#: English is the *source* file — what the translators were given — not one of the
#: three English references beside it.
FILES: dict[str, str] = {"en": "newstest2019-src.eng.txt", "he": "newstest2019-ref.heb.txt"}

#: Further renderings of that same source, fetched alongside. Russian is here so that a
#: Russian speaker's turn can be measured against the Hebrew reference for the same line
#: (targum-internal#286). Kept apart from `FILES` so a checkout that fetched before this
#: existed still reads as available rather than being told to fetch again.
ALSO: dict[str, str] = {"ru": "newstest2019-ref.rus.txt"}

#: What a source language is called when a line is said about it.
NAMED: dict[str, str] = {"en": "English", "ru": "Russian"}


class Line(NamedTuple):
    """One sentence as the reader would write it, and the Hebrew written for it.

    `said` is the source in whatever language was asked for — English by default, and
    Russian for #286's run. It is deliberately not called `en`: the whole point of the
    Russian eval is that the thing the reader wrote is not English, and a field named
    for one language holding another is how a number quietly stops meaning what it says.
    """

    id: str
    said: str
    he: str


def root() -> Path:
    """Beside the treebanks the annotator is scored against, and for the same reason."""
    return gold.root()


def _path(language: str) -> Path:
    return root() / f"ntrex-{language}.txt"


def _file(language: str) -> str:
    """The NTREX file name for a language tag, source or reference."""
    name = FILES.get(language) or ALSO.get(language)
    if name is None:
        raise TargumError(
            f"No NTREX-128 file for {language!r}.",
            f"Known here: {', '.join(sorted({*FILES, *ALSO}))}.",
        )
    return name


def available(source: str = "en") -> bool:
    """Whether a run with this source language has both files it needs."""
    return _path(source).is_file() and _path("he").is_file()


def complete() -> bool:
    """Whether every file this module knows is already on disk.

    `available` answers for one run; this answers for the fetch, so a checkout that got
    the English and Hebrew before the Russian reference was added is not told it has
    everything and left without it.
    """
    return all(_path(language).is_file() for language in (*FILES, *ALSO))


def fetch(
    notify: Callable[[str], None] | None = None, languages: Sequence[str] | None = None
) -> int:
    """Download what is not already here. Returns how many files arrived or were found.

    Idempotent and interruptible the way `gold.fetch` is: a file already on disk is left
    alone. `languages` names what to get; by default every file this module knows, which
    is the two a run needs plus the Russian reference #286 scores against.
    """
    import httpx

    say = notify or (lambda _message: None)
    ensure(root())
    got = 0
    for language in languages if languages is not None else (*FILES, *ALSO):
        file = _file(language)
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


def parse(source: str, hebrew: str, language: str = "en") -> list[Line]:
    """The two files joined by line number, which is how NTREX aligns them.

    The files must be the same length, or the pairing is off by one from the first gap
    onward and every score after it is of the wrong sentence: said, rather than zipped
    short. A line blank on either side is left out; its id is its line number, so a
    saved recast can be found again.
    """
    left = source.splitlines()
    right = hebrew.splitlines()
    if len(left) != len(right):
        raise TargumError(
            f"NTREX-128 files disagree on length: {len(left)} "
            f"{NAMED.get(language, language)} lines, {len(right)} Hebrew.",
            "Delete both from the gold directory and fetch again.",
        )
    return [
        Line(str(n), said.strip(), he.strip())
        for n, (said, he) in enumerate(zip(left, right, strict=True), 1)
        if said.strip() and he.strip()
    ]


def load(source: str = "en") -> list[Line]:
    """Every sentence in `source`, with the Hebrew written for that same line."""
    texts: dict[str, str] = {}
    for language in (source, "he"):
        path = _path(language)
        if not path.is_file():
            raise TargumError(
                f"NTREX-128 {NAMED.get(language, language)} is not downloaded.",
                "Run: targum models fetch ntrex",
            )
        texts[language] = path.read_text(encoding="utf-8")
    return parse(texts[source], texts["he"], source)


def describe(lines: Iterable[Line] | None = None) -> str:
    return f"{CREDIT} · {LICENCE} · {REPOSITORY}"
