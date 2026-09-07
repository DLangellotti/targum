"""Which built texts are behind the code that would build them now.

The annotator's name is the cache key: `rebuild --words` re-reads a text whose recorded
name differs from the one this machine would produce. That comparison is made every
deploy and its *result* was never printed anywhere, so a shelf several versions behind
looked exactly like a shelf that was fine — on 2026-09-04, 411 of 418 texts here, every
one in `library/`, carrying three merged and closed fixes that had reached no page
(targum-internal#208).

Loads no model and writes nothing. `for_source` picks the lemmatizer by where a text came
from and its name is a string, so asking costs a hundredth of a second — the same
comparison `rebuild` makes, made out loud and without the rebuild.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

#: A versioned piece of an annotator name: `register/2`, `oshb/2`, `tanakh/1`. The name is
#: a `+`-joined pile of these mixed with unversioned model identifiers, and only these can
#: be compared as older-or-newer.
VERSIONED = re.compile(r"(?:^|\+)([a-z_]+)/(\d+)(?=\+|$)")


def current_name(source: str) -> str | None:
    """What this machine would call the annotator for a text from `source`.

    `None` where it cannot be worked out — a box without the scripture data answers
    differently from one with it, by design, and saying so is better than guessing.
    """
    from . import Annotator, biblical, lemma

    try:
        return Annotator(
            lemmatizer=lemma.for_source(source, auto_download=False),
            bands=biblical.for_source(source),
        ).name
    except Exception:  # noqa: BLE001 - an unbuildable lemmatizer is an unknown, not a failure
        return None


def versions(name: str) -> dict[str, str]:
    """The versioned components of an annotator name, by component."""
    return {piece: number for piece, number in VERSIONED.findall(name)}


def compare(have: str, want: str) -> list[tuple[str, str, str]]:
    """Which versioned components the built text is behind on.

    Compared component by component rather than as whole strings, and only over the
    components both names carry. An `Annotator` built here for the comparison does not
    know what dictionary provider or vocalizer the build used, so its name is missing
    `anthropic/…/dictionary-3` and `phonikud/2` — pieces that say nothing about whether
    the *words* are current. Comparing the strings whole reports every text on the shelf
    as behind, which is how this was caught.
    """
    mine, theirs = versions(have), versions(want)
    return [
        (piece, mine[piece], theirs[piece])
        for piece in sorted(theirs)
        if piece in mine and mine[piece] != theirs[piece]
    ]


@dataclass
class Shelf:
    """How much of a built shelf the current code would annotate differently."""

    current: int = 0
    #: Folder, the name it carries, the name this machine would give it.
    behind: list[tuple[str, str, str]] = field(default_factory=list)
    #: Texts whose annotator cannot be worked out here — no `document.json`, or a
    #: lemmatizer this machine cannot build. Counted rather than assumed either way.
    unknown: int = 0

    @property
    def total(self) -> int:
        return self.current + len(self.behind) + self.unknown

    def moved(self) -> dict[str, int]:
        """How many texts each component move accounts for, commonest first."""
        counted: dict[str, int] = {}
        for _folder, have, want in self.behind:
            for piece, mine, theirs in compare(have, want):
                key = f"{piece}/{mine} -> {piece}/{theirs}"
                counted[key] = counted.get(key, 0) + 1
        return dict(sorted(counted.items(), key=lambda pair: -pair[1]))


def survey(out: Path, home: str = "") -> Shelf:
    """Walk a build directory and say what is behind, reading only what is on disk.

    Hebrew only: the annotator name for another language moves for reasons that have
    nothing to do with the work this watches, and counting them would bury the number.
    """
    shelf = Shelf()
    # Cached because a shelf is mostly a few sources repeated, and the name is a pure
    # function of the source.
    names: dict[str, str | None] = {}

    for path in sorted(out.rglob("annotation.json")):
        if home and path.parent.parent.name != home:
            continue
        try:
            annotation = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            shelf.unknown += 1
            continue
        if annotation.get("language", "").split("-")[0].lower() != "he":
            continue
        document = path.parent / "document.json"
        if not document.is_file():
            shelf.unknown += 1
            continue
        try:
            source = json.loads(document.read_text(encoding="utf-8")).get("source", "")
        except (OSError, ValueError):
            shelf.unknown += 1
            continue
        if source not in names:
            names[source] = current_name(source)
        want = names[source]
        if want is None:
            shelf.unknown += 1
            continue
        have = annotation.get("annotator", "")
        if compare(have, want):
            shelf.behind.append((str(path.parent), have, want))
        else:
            shelf.current += 1
    return shelf
