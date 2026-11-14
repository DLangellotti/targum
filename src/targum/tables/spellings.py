"""Table 3, `readings`: which pointed reading, and which `glossed_as`, a spelling takes in
each register (targum-internal#583; spec §2).

Hebrew is written without its vowels, so one spelling is several words: ספר is סֵפֶר, a
book, far more often in the news than it is סָפַר, he counted. This counts, per unpointed
spelling as written, the pointed form the vocalizer gave each occurrence and the form
its meaning is filed under (`Token.glossed_as`), so "ספר is סֵפֶר 81% in news" is a query.
It feeds pointing (a prior for the diacritizer's choice), glosses (the `glossed_as`
split) and two spellings; nothing visible reads it yet.

Folded by the same fold as `words`, from the same public texts and behind the same guard
(`tables.public_text`), wherever a vocalization sits beside the annotation. Each token is
aligned to its pointed word with `vocalize.aligned_positions`, the alignment two
spellings already trusts. A token that cannot be aligned, or whose pointed word is not
its own spelling, or carries no vowel at all, is counted as `UNALIGNED` under its
spelling and never guessed. A name is not counted (the words table files every name
under one key; a reading has no such key), nor anything that is not a Hebrew word.

What readers bring is counted by the imports pool (`tables.imports`) under its floor of
ten readers a row, exactly as its words are; the privacy notice's clause 3.7 names "each
reading given to a word as written". The finds pool cannot feed this table: a find keeps
a bag of lemmas and never a word as written. Neither can the news count or an outside
corpus, which are annotated in memory with no vocalizer run.

Key: the spelling, bare. Variant: the pointed form, its chanting marks taken off so a
verse's accents do not split one reading in two, a tab, and the `glossed_as` form.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

READINGS = "readings"

#: The version of the counting rule below: a change to what is counted is a new number.
RULE = "readings/1"

#: The pointed form of a token that could not be aligned: counted, never guessed.
UNALIGNED = "?"

#: Between the pointed form and the `glossed_as` in a variant.
SEPARATOR = "\t"

#: Only Hebrew has a vocalizer whose choice this measures.
LANGUAGES = ("he",)

#: The vocalizer whose pointed lines may spell a word with a letter fewer (#568).
_SCENE = "scene/"

#: The matres lectionis a standard ktiv menukad leaves out of a full spelling.
_MATRES = re.compile("[וי]")


def variant(pointed: str, glossed_as: str) -> str:
    return f"{pointed}{SEPARATOR}{glossed_as}"


def split_variant(value: str) -> tuple[str, str]:
    pointed, _, glossed = value.partition(SEPARATOR)
    return pointed, glossed


def _hebrew(word: str) -> bool:
    from ..vocalize.base import LETTERS

    return any(ord(char) in LETTERS for char in word)


def _glossed_as(token: Mapping[str, Any]) -> str:
    from ..models import Syntax, Token

    syntax = token.get("syntax")
    return Token.model_construct(
        lemma=str(token.get("lemma") or ""),
        pos=token.get("pos"),
        headword=token.get("headword"),
        surface=str(token.get("surface") or ""),
        built=token.get("built"),
        syntax=Syntax.model_validate(syntax) if isinstance(syntax, Mapping) else None,
    ).glossed_as


def _same_spelling(pointed_bare: str, surface: str, scene: bool) -> bool:
    if pointed_bare == surface:
        return True
    # A scene's line is in ktiv menukad, its text in full spelling: חִבּוּר for חיבור.
    return scene and _MATRES.sub("", pointed_bare) == _MATRES.sub("", surface)


def count(
    tokens: Mapping[str, Sequence[Mapping[str, Any]]],
    texts: Mapping[str, str],
    pointed: Mapping[str, str],
    vocalizer: str = "",
) -> Counter[tuple[str, str]]:
    """The readings of one annotation's tokens, keyed (spelling, variant): never written,
    only counted. `texts` is each segment's text as ingested (what token offsets are
    measured against), `pointed` the vocalization's segments.

    A segment the vocalization left out carries no marks, so its words are unaligned.
    """
    from ..annotate.base import NOT_A_WORD, is_named
    from ..vocalize.base import aligned_positions, strip_nikkud, strip_taamim

    scene = vocalizer.startswith(_SCENE)
    out: Counter[tuple[str, str]] = Counter()
    for segment_id, run in tokens.items():
        source = texts.get(segment_id)
        line = pointed.get(segment_id)
        to_bare: list[int] = []
        to_pointed: list[int] = []
        if source is not None and line is not None:
            bare_source, to_bare = strip_nikkud(source)
            to_pointed = aligned_positions(line, bare_source)
        for token in run:
            if not isinstance(token, Mapping):
                continue
            lemma = str(token.get("lemma") or "")
            entity = token.get("entity")
            if lemma in NOT_A_WORD:
                continue
            if is_named(entity) if entity else token.get("pos") == "PROPN":
                continue
            surface = strip_nikkud(str(token.get("surface") or ""))[0].strip()
            if not surface or not _hebrew(surface):
                continue
            glossed = _glossed_as(token)
            word = _pointed(token, to_bare, to_pointed, line)
            reading = UNALIGNED
            if word:
                word = strip_taamim(word).strip()
                bare_word = strip_nikkud(word)[0]
                if bare_word != word and _same_spelling(bare_word, surface, scene):
                    reading = word
            out[(surface, variant(reading, glossed))] += 1
    return out


def _pointed(
    token: Mapping[str, Any], to_bare: list[int], to_pointed: list[int], line: str | None
) -> str:
    """The pointed word behind one token, as `Annotator.pronounce` finds it; "" where the
    offsets do not reach."""
    from ..vocalize.base import map_span

    if line is None or not to_bare or not to_pointed:
        return ""
    try:
        start, end = int(token.get("start", -1)), int(token.get("end", -1))
    except (TypeError, ValueError):
        return ""
    if start < 0 or end <= start or end >= len(to_bare):
        return ""
    bare_start, bare_end = map_span(start, end, to_bare)
    if bare_end >= len(to_pointed):
        return ""
    begin, finish = map_span(bare_start, bare_end, to_pointed)
    return line[begin:finish]


@dataclass(frozen=True)
class Beside:
    """What a fold of readings needs from beside the annotation: the vocalization's
    pointed lines and its vocalizer's name, and each segment's text."""

    vocalizer: str
    pointed: Mapping[str, str] = field(repr=False)
    texts: Mapping[str, str] = field(repr=False)


_VOCALIZER = re.compile(r'"vocalizer":\s*"((?:[^"\\]|\\.)*)"')


def vocalizer_on_disk(folder: Path) -> str | None:
    """The vocalizer named at the head of `folder`'s vocalization, without reading the
    rest; None where there is none. What a sweep asks before deciding to read."""
    try:
        with (folder / "vocalization.json").open("rb") as handle:
            head = handle.read(4096).decode("utf-8", "ignore")
    except OSError:
        return None
    found = _VOCALIZER.search(head)
    if found is None:
        return None
    named: Any = json.loads(f'"{found.group(1)}"')
    return str(named) or None


def beside(folder: Path, document_hash: str) -> Beside | None:
    """The vocalization and segments beside one built text, or None where either is
    missing, unreadable or of another document."""
    try:
        vocalization = json.loads((folder / "vocalization.json").read_text(encoding="utf-8"))
        segmented = json.loads((folder / "segments.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(vocalization, dict) or not isinstance(segmented, dict):
        return None
    if str(vocalization.get("document_hash") or "") != document_hash:
        return None
    if str(segmented.get("document_hash") or document_hash) != document_hash:
        return None
    vocalizer = str(vocalization.get("vocalizer") or "")
    lines = vocalization.get("segments")
    segments = segmented.get("segments")
    if not vocalizer or not isinstance(lines, dict) or not isinstance(segments, list):
        return None
    texts = {
        str(one.get("id")): str(one.get("text") or "")
        for one in segments
        if isinstance(one, dict) and one.get("id") is not None
    }
    pointed = {str(key): str(value) for key, value in lines.items() if isinstance(value, str)}
    return Beside(vocalizer=vocalizer, pointed=pointed, texts=texts)


def tool(annotator: str, vocalizer: str) -> str:
    """A readings contribution's tool: the annotator's choice of word and the
    vocalizer's choice of vowels both decide a row, so a rename of either counts again."""
    return f"{annotator}+{vocalizer}"


def folds(language: str) -> bool:
    return any(language == one or language.startswith(f"{one}-") for one in LANGUAGES)


@dataclass(frozen=True)
class Reading:
    """One reading of a spelling, with how often it was given and its share of the
    aligned occurrences."""

    pointed: str
    glossed_as: str
    n: int
    share: float


@dataclass(frozen=True)
class Readings:
    """Every reading one spelling was counted under, commonest first."""

    spelling: str
    register: str | None
    #: The aligned occurrences: what each share is of.
    total: int
    #: Occurrences counted under the spelling that could not be aligned.
    unaligned: int
    choices: tuple[Reading, ...] = ()


def shares(spelling: str, register: str | None, counted: Mapping[str, int]) -> Readings:
    """The readings of one spelling from its variant counts."""
    unaligned = 0
    by: dict[tuple[str, str], int] = {}
    for value, n in counted.items():
        pointed, glossed = split_variant(value)
        if pointed == UNALIGNED:
            unaligned += n
            continue
        by[(pointed, glossed)] = by.get((pointed, glossed), 0) + n
    total = sum(by.values())
    choices = tuple(
        Reading(pointed, glossed, n, n / total if total else 0.0)
        for (pointed, glossed), n in sorted(by.items(), key=lambda item: (-item[1], item[0]))
    )
    return Readings(spelling, register, total, unaligned, choices)
