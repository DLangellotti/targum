"""What a Russian verb's prefix adds, said beside it on the card (targum-internal#600).

`ru_prefixes.json` is a list targum owns. It has twenty verbal prefixes, each with the one
or two spatial or lexical senses a learner can see in a verb ("вы- out", "при- arriving"),
in English for the English interface and in Russian for the Russian one, and a prefix's
other spellings (со-, съ- for с-; рас- for раз-) share its senses. Beside them are the
verbs whose prefix is read in one of those senses, each verb with the one sense it carries:
выйти is вы- "out", пойти is по- "start" and поговорить is по- "for a while". ling-ru
wrote it from its sublexical research of 2026-10-30 (§5, slice 2); no published list was
copied.

**A sense is said only where it is there to see.** The card names a prefix's sense:

- on a verb the root lexicon grades transparent, and not on an opaque or partial one: the
  по- of понять, the за- of заниматься and the вы- of выиграть mean none of their senses;
- and only on a verb the list names. The lexicon's grade is the word's, not the prefix's:
  узнать, показать and начинать are graded transparent, and "у- away", "по- for a while"
  and "на- onto" would each teach something false. So would "с- down" on сделать, whose
  prefix only makes делать's partner. A verb the list does not name gets no line until it
  is read and added.

Page-build time only: the senses ride in the page's `morphemes` table beside the words
that carry them, nothing is annotated again and no cache key moves.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from functools import cache
from pathlib import Path
from typing import NamedTuple

_TABLE = Path(__file__).with_name("ru_prefixes.json")


class Sense(NamedTuple):
    en: str
    ru: str


def fold(word: str) -> str:
    """Lower case, ё as е, no stress mark: how a lemma or a prefix is looked up."""
    return word.replace("́", "").lower().replace("ё", "е").strip()


@cache
def _read() -> tuple[dict[str, str], dict[str, dict[str, Sense]], dict[str, tuple[str, str]]]:
    body = json.loads(_TABLE.read_text(encoding="utf-8"))
    spelled: dict[str, str] = {}
    senses: dict[str, dict[str, Sense]] = {}
    for row in body["prefixes"]:
        prefix = fold(str(row["prefix"]))
        senses[prefix] = {
            str(key): Sense(str(said["en"]), str(said["ru"])) for key, said in row["senses"].items()
        }
        for spelling in (prefix, *row.get("spellings", [])):
            spelled[fold(str(spelling))] = prefix
    verbs: dict[str, tuple[str, str]] = {}
    for verb, read in body["verbs"].items():
        prefix, _, key = str(read).partition(":")
        verbs[fold(str(verb))] = (fold(prefix), key)
    return spelled, senses, verbs


def prefix_of(spelling: str) -> str:
    """The prefix a spelling is filed under (со → с), or "" for one not on the list."""
    return _read()[0].get(fold(spelling), "")


def senses_of(prefix: str) -> dict[str, Sense]:
    """A prefix's senses by key, under any of its spellings."""
    return _read()[1].get(prefix_of(prefix), {})


def verb_sense(lemma: str) -> tuple[str, str] | None:
    """The prefix and the sense key the list reads a verb's prefix in, or None."""
    return _read()[2].get(fold(lemma))


def senses(
    lemma: str, pos: str | None, prefixes: Sequence[str], transparent: bool
) -> list[list[str]]:
    """What the card says of a verb's prefix: [[prefix as the verb spells it, English,
    Russian]], or [] where nothing is to be said (see the module's rules). One prefix:
    a verb of two (подождать) is not on the list."""
    if (pos or "") != "VERB" or not transparent or len(prefixes) != 1:
        return []
    read = verb_sense(lemma)
    if read is None or prefix_of(prefixes[0]) != read[0]:
        return []
    sense = senses_of(read[0]).get(read[1])
    if sense is None:
        return []
    return [[prefixes[0], sense.en, sense.ru]]
