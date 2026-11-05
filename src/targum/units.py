"""Multiword units: an idiom is one word to know (design.md §12, "An idiom is one word to
know", 2026-11-05; targum-internal#614).

`units.tsv` beside this file is ling-he's hand-picked list (2026-11-05): each row a key of
DICTA lemmas joined by a space, as `tables.words.count` writes a phrase, its written
form, an English gloss, its register and ling-he's note. `needs` is the one column added
for the matcher: for a key that means the expression only with a prefix, the prefix
letter each word must carry, `|` between words (מכל מקום is `מ|`, מפעם לפעם `מ|ל`).

Nothing here reads a text or a reader's list by itself: `match` is handed a segment's
tokens, and `from_phrases` the text of the phrases a reader kept and marked known.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

#: The list, in the package.
PATH = Path(__file__).with_name("units.tsv")

#: The languages the list is for: ling-he's is Hebrew.
LANGUAGES = frozenset({"he"})

#: The most characters between two words of one unit: a space or a maqaf.
GAP = 1

#: Letters a Hebrew word may carry before its stem.
PREFIX_LETTERS = frozenset("ובכלמשה")

#: The status a mark says known with (`coverage.KNOWN`), restated so this module has no
#: import cycle with coverage.
KNOWN = 9


@dataclass(frozen=True)
class Unit:
    """One expression counted as one word."""

    key: str
    parts: tuple[str, ...]
    #: The prefix letter each part must carry, "" where none is needed.
    needs: tuple[str, ...]
    #: Its written forms, unpointed, each as a run of words.
    written: tuple[tuple[str, ...], ...]


def plain(text: str) -> str:
    """Hebrew without points or cantillation, a maqaf read as a space, and anything
    that is not a letter or a space dropped."""
    out = []
    for char in unicodedata.normalize("NFD", text):
        if unicodedata.category(char).startswith("M"):
            continue
        if char in "־-":
            out.append(" ")
        elif char.isalpha() or char.isspace():
            out.append(char)
    return " ".join("".join(out).split())


def _written(surface: str) -> tuple[tuple[str, ...], ...]:
    """The unpointed written forms a `surface` cell gives: alternatives split on "/", a
    part in brackets both with and without."""
    out: list[tuple[str, ...]] = []
    for one in surface.split("/"):
        bare = re.sub(r"\([^)]*\)", " ", one)
        full = one.replace("(", " ").replace(")", " ")
        for form in (bare, full):
            words = tuple(plain(form).split())
            if words and words not in out:
                out.append(words)
    return tuple(out)


@lru_cache(maxsize=1)
def load(path: Path = PATH) -> tuple[Unit, ...]:
    """Every unit on the list, in the file's order."""
    if not path.is_file():
        return ()
    rows = path.read_text(encoding="utf-8").splitlines()
    if not rows:
        return ()
    header = rows[0].split("\t")
    out: list[Unit] = []
    for line in rows[1:]:
        cells = dict(zip(header, line.split("\t"), strict=False))
        parts = tuple(str(cells.get("lemmas") or "").split())
        if len(parts) < 2:
            continue
        needed = str(cells.get("needs") or "").split("|") if cells.get("needs") else []
        needs = tuple((needed[at] if at < len(needed) else "").strip() for at in range(len(parts)))
        out.append(
            Unit(
                key=" ".join(parts),
                parts=parts,
                needs=needs,
                written=_written(str(cells.get("surface") or "")),
            )
        )
    return tuple(out)


@lru_cache(maxsize=1)
def stamp(path: Path = PATH) -> str:
    """A short digest of the list, so a count cached under another list is counted
    again."""
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()[:12]
    except OSError:
        return ""


@lru_cache(maxsize=1)
def _by_first() -> dict[str, tuple[Unit, ...]]:
    """The units by their first lemma, longest first."""
    held: dict[str, list[Unit]] = {}
    for unit in load():
        held.setdefault(unit.parts[0], []).append(unit)
    return {
        first: tuple(sorted(units, key=lambda unit: -len(unit.parts)))
        for first, units in held.items()
    }


def keys() -> frozenset[str]:
    """Every unit's key."""
    return frozenset(unit.key for unit in load())


#: Between a unit's key and the words of it that were counted, where not all were.
COUNTED = "|"


def entry(key: str, counted: Sequence[str]) -> str:
    """How a unit is recorded in a text's counts: its key, and after `COUNTED` the
    words of it that were counted where some were not (a numeral, a name)."""
    if tuple(counted) == tuple(key.split()):
        return key
    return f"{key}{COUNTED}{' '.join(counted)}"


def counted_in(name: str) -> tuple[str, tuple[str, ...]]:
    """A recorded unit's key, and the words of it that were counted (`entry`)."""
    key, _, counted = name.partition(COUNTED)
    return key, tuple((counted or key).split())


def _prefix(token: Mapping[str, Any]) -> str:
    """The prefix letters a token carries: as many of its first letters as DICTA split
    off (`syntax.lead`)."""
    syntax = token.get("syntax") or {}
    lead = int(syntax.get("lead") or 0) if isinstance(syntax, Mapping) else 0
    if lead <= 0:
        return ""
    return plain(str(token.get("surface") or "")).replace(" ", "")[:lead]


def _fits(unit: Unit, run: Sequence[Mapping[str, Any]]) -> bool:
    for at, token in enumerate(run):
        if str(token.get("lemma") or "") != unit.parts[at]:
            return False
        if at and int(token.get("start") or 0) - int(run[at - 1].get("end") or 0) > GAP:
            return False
        if unit.needs[at] and unit.needs[at] not in _prefix(token):
            return False
    return True


def match(tokens: Sequence[Mapping[str, Any]]) -> list[tuple[int, Unit]]:
    """The units in one segment's tokens, in order, as (index of the first token,
    unit): consecutive tokens whose lemmas are a unit's, with nothing but a space or a
    maqaf between them and each prefix the unit needs, the longest first. A token is in
    one unit at most."""
    table = _by_first()
    out: list[tuple[int, Unit]] = []
    at = 0
    while at < len(tokens):
        found = None
        for unit in table.get(str(tokens[at].get("lemma") or ""), ()):
            run = tokens[at : at + len(unit.parts)]
            if len(run) == len(unit.parts) and _fits(unit, run):
                found = unit
                break
        if found is None:
            at += 1
            continue
        out.append((at, found))
        at += len(found.parts)
    return out


def from_phrases(texts: Iterable[str]) -> frozenset[str]:
    """The units a reader's kept phrases are: each phrase's words against each unit's
    written forms, a prefix on the first word allowed."""
    wanted: dict[tuple[str, ...], set[str]] = {}
    for unit in load():
        for words in unit.written:
            wanted.setdefault(words, set()).add(unit.key)
    out: set[str] = set()
    for text in texts:
        words = tuple(plain(text).split())
        if not words:
            continue
        out.update(wanted.get(words, ()))
        first = words[0]
        for cut in range(1, min(3, len(first) - 1) + 1):
            if not set(first[:cut]) <= PREFIX_LETTERS:
                break
            out.update(wanted.get((first[cut:], *words[1:]), ()))
    return frozenset(out)


def with_phrases(marked: Mapping[str, int], phrases: Iterable[str]) -> dict[str, int]:
    """A reader's marks with each unit they kept as a phrase and marked known, known
    under its key (design.md §12, "An idiom is one word to know")."""
    out = dict(marked)
    for key in from_phrases(phrases):
        out.setdefault(key, KNOWN)
    return out
