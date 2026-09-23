"""FLORES-200, fetched to score the chat's recast against and for nothing else.

The third reference, and the one that exists because the second could not be reached.
`flores.py` is FLORES+, the community continuation, and it is gated: Hugging Face asks a
person to accept the dataset's conditions, so the fetch carries a token. FLORES-200 is
its archived predecessor — Meta's own release, a plain tarball on a public host, no
token, no login, nothing to accept.

**Why it is here at all: Yiddish.** The recast eval needs a professional rendering of an
English sentence to set the chat's line against. NTREX-128 carries 128 languages and
Yiddish is not among them (checked against the repository's own file listing, not assumed
from the count), and FLORES+ has `ydd_Hebr` but needs the token. So without this,
targum-internal#283 ships unreviewed *and* unevaluated with no path to a number at all.

**It is not FLORES+, and a number taken here should say so.** FLORES+ carries
corrections the community made to this data, so a score here is comparable to published
FLORES-200 numbers and only approximately to FLORES+ ones. That is why it files under
`corpus=flores-200` and not under `flores-plus`: the ledger's key is
`(stage, corpus, metric)`, and one reference's number standing in for another's is how a
regression gets read off two things that were never the same measurement.

**It is CC BY-SA 4.0**, the same licence FLORES+ and NTREX-128 are held under and the
same terms `annotate/gold.py` set for the treebanks: evaluation only, fetched beside the
gold sets, nothing served, nothing trained on, nothing derived shipped. Its whole
contribution to targum is a row in `evals/ledger.jsonl`.

**On the Yiddish specifically.** The reference is written in the unpointed orthography the
Yiddish press uses — מאנאטן where YIVO writes מאָנאַטן — and targum's contract asks for
YIVO. That is a difference of spelling and not of language, so the judge is told to ignore
diacritics; a run that did not would score the contract down for doing what it was told.
"""

from __future__ import annotations

import io
import tarfile
from collections.abc import Callable, Iterable
from pathlib import Path

from ..annotate import gold
from ..errors import TargumError
from ..paths import ensure, write_atomic
from .flores import Pair

CREDIT = "FLORES-200, Meta AI (NLLB)"
LICENCE = "CC BY-SA 4.0"
#: The redirect Meta publishes. Followed rather than hard-coded to the bucket, because
#: the short link is the address the dataset card gives and the one that will be kept
#: pointing at whatever the file becomes.
SOURCE = "https://tinyurl.com/flores200dataset"

#: The languoids this module joins, by the tag the rest of targum uses. The file name is
#: FLORES-200's own: ISO 639-3 and the script. Yiddish here is *Eastern* Yiddish, which
#: is the Yiddish anybody learning it today is learning.
FILES: dict[str, str] = {
    "en": "eng_Latn",
    "he": "heb_Hebr",
    "yi": "ydd_Hebr",
    "fr": "fra_Latn",
    "ru": "rus_Cyrl",
}

#: What FLORES-200 splits into. `devtest` is what a published number is taken on, so it
#: is the default; `dev` is there for anybody tuning a prompt who wants to keep the
#: other split clean. `test` is in the tarball and is unlabelled — it is not offered.
SPLITS = ("dev", "devtest")
DEFAULT_SPLIT = "devtest"


def root() -> Path:
    """Beside the treebanks the annotator is scored against, and for the same reason."""
    return gold.root()


def _path(language: str, split: str) -> Path:
    return root() / f"flores200-{split}-{language}.txt"


def available(language: str, split: str = DEFAULT_SPLIT) -> bool:
    return _path("en", split).is_file() and _path(language, split).is_file()


def fetch(
    languages: Iterable[str] | None = None,
    split: str = DEFAULT_SPLIT,
    notify: Callable[[str], None] | None = None,
) -> int:
    """Download the tarball once and keep only the files asked for.

    The archive is 25 MB and holds four hundred files; what a run needs is two of them.
    So it is read in memory and the wanted members are written out — a box with half a
    gigabyte free should not have to hold the unpacked set to score two hundred
    sentences.

    Idempotent: a file already on disk means the tarball is never fetched at all.
    """
    import httpx

    say = notify or (lambda _message: None)
    wanted = list(languages or ["en"])
    if "en" not in wanted:
        wanted.append("en")
    unknown = [code for code in wanted if code not in FILES]
    if unknown:
        raise TargumError(
            f"FLORES-200 is not carried here for {', '.join(unknown)}.",
            f"This module knows {', '.join(sorted(FILES))}; the dataset has two hundred.",
        )
    ensure(root())
    missing = [code for code in wanted if not _path(code, split).is_file()]
    if not missing:
        return len(wanted)

    say(f"Fetching FLORES-200 ({split}: {', '.join(missing)})…")
    try:
        answer = httpx.get(SOURCE, timeout=600.0, follow_redirects=True)
        answer.raise_for_status()
    except Exception as bad:  # noqa: BLE001 - network and HTTP both land here
        raise TargumError("Could not fetch FLORES-200.", str(bad)) from bad

    got = 0
    with tarfile.open(fileobj=io.BytesIO(answer.content), mode="r:gz") as archive:
        for code in missing:
            member = f"./flores200_dataset/{split}/{FILES[code]}.{split}"
            try:
                handle = archive.extractfile(member)
            except KeyError:
                handle = None
            if handle is None:
                raise TargumError(
                    f"FLORES-200 has no {member}.",
                    "The archive's layout changed; check the dataset card.",
                )
            write_atomic(_path(code, split), handle.read().decode("utf-8"))
            got += 1
    return got


def parse(english: str, rendered: str, language: str = "yi") -> list[Pair]:
    """The two files joined by line number, which is how FLORES aligns them.

    The files must be the same length, or the pairing is off by one from the first gap
    onward and every score after it is of the wrong sentence: said, rather than zipped
    short.
    """
    left = english.splitlines()
    right = rendered.splitlines()
    if len(left) != len(right):
        raise TargumError(
            f"FLORES-200 files disagree on length: {len(left)} English lines, "
            f"{len(right)} {language}.",
            "Delete both from the gold directory and fetch again.",
        )
    return [
        Pair(str(n), en.strip(), other.strip())
        for n, (en, other) in enumerate(zip(left, right, strict=True), 1)
        if en.strip() and other.strip()
    ]


def load(language: str = "yi", split: str = DEFAULT_SPLIT) -> list[Pair]:
    """Every English sentence with its rendering in one language.

    `Pair.he` is that rendering whatever language it is in — the name is the corpus's
    first language in `flores.py`, and this module borrows the shape so the eval does not
    know which reference it is scoring against.
    """
    if language not in FILES:
        raise TargumError(
            f"FLORES-200 is not carried here for {language}.",
            f"This module knows {', '.join(sorted(FILES))}.",
        )
    for code in ("en", language):
        if not _path(code, split).is_file():
            raise TargumError(
                "FLORES-200 is not downloaded.",
                f"Run: targum models fetch flores200 --language {language}",
            )
    return parse(
        _path("en", split).read_text(encoding="utf-8"),
        _path(language, split).read_text(encoding="utf-8"),
        language,
    )


def describe(pairs: Iterable[Pair] | None = None) -> str:
    return f"{CREDIT} · {LICENCE} · {SOURCE}"


__all__ = [
    "CREDIT",
    "DEFAULT_SPLIT",
    "FILES",
    "LICENCE",
    "SPLITS",
    "available",
    "describe",
    "fetch",
    "load",
    "parse",
    "root",
]
