"""How a French word is said, looked up in Morphalou rather than guessed.

French spelling is a poor guide to French sound, and a learner stores the written shape
(targum-internal#266). Morphalou 3.1 is the ATILF's open lexicon of French: 159,271
lemmas and 976,570 inflected forms, about half of them with a phonetic transcription,
merged from Morphalou 2, DELA, Dicollecte, Lefff and LGLex. It is distributed by ORTOLANG
under the Lesser General Public License for Linguistic Resources (LGPL-LR).

**Looked up, never learned from, never committed** (David's decision of 2026-09-14). The
file is fetched into the model directory by `targum models fetch morphalou`, checked
against a pinned checksum, and read here. No row of it is in this repository or in the
wheel, no model is trained on it, and any correction to its data is published under
LGPL-LR. The licence text is in `LICENSING.md`, and a copy is fetched beside the data.

**Only a lookup, and nothing shown yet.** This module answers which transcriptions a
written form has. `scripts/measure_pronunciation.py` counts how much of the French shelf
that reaches, which is the first step of the card: below about 95%, espeak-ng is
reconsidered, and that is the owner's call. No card reads this yet.

The transcriptions are in Morphalou's own notation, close to SAMPA: `@` schwa, `E/` and
`O/` the mid vowels where either height is heard, `~` nasal, `2` and `9` the front
rounded vowels, and `OU` between two acceptable readings. Turning that into IPA is the
card's work, not this module's.
"""

from __future__ import annotations

import csv
import functools
import hashlib
import io
import zipfile
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import NamedTuple

from ..errors import TargumError
from ..paths import ensure, model_dir, write_atomic

#: ORTOLANG publishes the lexicon as numbered versions of one workspace; version 5 holds
#: Morphalou 3.1. The file is the CSV with every form in one table, and the checksum is
#: what makes a build today and a build next year read the same lexicon.
VERSION = "3.1"
ARCHIVE = "Morphalou3.1_formatCSV_toutEnUn.zip"
SOURCE = f"https://repository.ortolang.fr/api/content/morphalou/5/{ARCHIVE}"
SHA256 = "4fc815cbf17aecdf1b47f6bbc263489a460fd8d11ae17e6b522336c72bd0e333"
TABLE = "Morphalou3.1_CSV.csv"
LICENCE_FILE = "licenceLGPLLR.txt"
LICENCE_SOURCE = f"https://repository.ortolang.fr/api/content/morphalou/5/{LICENCE_FILE}"
LICENCE_SHA256 = "301c33ad62b3a431975ecb325c3855b95a7c8bf6f2df9a7a4d479146c904193c"

CREDIT = "Morphalou 3.1, ATILF CNRS"
LICENCE = "LGPL-LR"
PAGE = "https://www.ortolang.fr/market/lexicons/morphalou"

#: The two header rows the table's column names are in; everything above is a preamble.
_HEADER = "GRAPHIE;ID;"
#: Columns of the table, counted from zero: the lemma's spelling and category on the
#: first row of each lemma, then the form, its grammar and its transcription on every row.
_LEMMA, _CATEGORY, _FORM, _PHONETIC = 0, 2, 9, 16
#: Number, mood, gender, tense and person, in that order.
_GRAMMAR = slice(11, 16)

#: Universal Dependencies' part of speech, as Morphalou names the category.
CATEGORIES = {
    "NOUN": {"Nom commun"},
    "PROPN": {"Nom commun"},
    "VERB": {"Verbe"},
    "AUX": {"Verbe"},
    "ADJ": {"Adjectif qualificatif"},
    "ADV": {"Adverbe"},
    "ADP": {"Préposition"},
    "CCONJ": {"Conjonction"},
    "SCONJ": {"Conjonction"},
    "PRON": {"Pronom"},
    "DET": {"Déterminant", "Nombre"},
    "NUM": {"Nombre", "Déterminant"},
    "INTJ": {"Interjection"},
}

#: Universal Dependencies' features, as Morphalou's columns spell them. French's card is
#: never told the imperfect apart from the past (`model_lemma.FEATURES` has no `Imp`), so
#: a past is any of the three.
FEATURES = {
    "Number": {"Sing": {"singular"}, "Plur": {"plural"}},
    "Gender": {"Masc": {"masculine"}, "Fem": {"feminine"}},
    "Person": {"1": {"firstPerson"}, "2": {"secondPerson"}, "3": {"thirdPerson"}},
    "Mood": {
        "Ind": {"indicative"},
        "Sub": {"subjunctive"},
        "Cnd": {"conditional"},
        "Imp": {"imperative"},
    },
    "Tense": {
        "Pres": {"present"},
        "Fut": {"future"},
        "Past": {"simplePast", "past", "imperfect"},
    },
    "VerbForm": {"Inf": {"infinitive"}, "Part": {"participle"}},
}
#: A noun's row leaves mood and tense unmarked, and a verb's leaves gender unmarked. So an
#: unmarked number or gender agrees with anything, but a word tagged with a mood, a tense
#: or a person is a verb form, and a row without one is not it.
_UNMARKED = frozenset({"", "-", "invariable"})
_LENIENT = frozenset({"Number", "Gender"})

#: Written the same way by a text and by the table: the curly apostrophe becomes the
#: straight one the table uses, and a ligature is tried spelled out, since the table files
#: `oeil` with a transcription and `œil` without one.
_APOSTROPHES = str.maketrans({"’": "'", "ʼ": "'"})
_LIGATURES = str.maketrans({"œ": "oe", "Œ": "Oe", "æ": "ae", "Æ": "Ae"})


Grammar = tuple[str, str, str, str, str]


class Reading(NamedTuple):
    """One row of the table that has a transcription: a form of a lemma, and how it is said."""

    lemma: str
    category: str
    #: Number, mood, gender, tense and person, in the table's own words.
    grammar: Grammar
    phonetic: str

    def variants(self) -> frozenset[str]:
        return frozenset(part.strip() for part in self.phonetic.split(" OU ") if part.strip())


@dataclass
class Lexicon:
    #: Every form with at least one transcription, as the table spells it.
    readings: dict[str, list[Reading]] = field(default_factory=dict)
    #: Every form the table lists without any transcription.
    bare: set[str] = field(default_factory=set)

    def keys(self, form: str) -> list[str]:
        """The spellings a written form is looked up under, in order: as written, then in
        lower case, then with a ligature spelled out."""
        written = form.translate(_APOSTROPHES)
        out: list[str] = []
        for key in (written, written.lower()):
            for spelled in (key, key.translate(_LIGATURES)):
                if spelled not in out:
                    out.append(spelled)
        return out

    def lookup(self, form: str) -> list[Reading]:
        """The readings of the first spelling that has any."""
        for key in self.keys(form):
            if key in self.readings:
                return self.readings[key]
        return []

    def listed(self, form: str) -> bool:
        """Whether the table has the form at all, with a transcription or without one."""
        return any(key in self.readings or key in self.bare for key in self.keys(form))

    def transcriptions(
        self, form: str, lemma: str = "", pos: str = "", feats: str = ""
    ) -> list[frozenset[str]]:
        """How the form is said: one set of acceptable readings per distinct way.

        More than one is a form the spelling does not decide — `est` is /ɛ/ as a verb and
        /ɛst/ as the east. Where the word's lemma, part of speech and features are known,
        the readings that disagree with them are dropped, and only if that leaves nothing
        is the whole list given back. Readings that share a variant are one way of saying
        the word, not two.
        """
        found = self.lookup(form)
        if lemma or pos or feats:
            kept = [row for row in found if _agrees(row, lemma, pos, feats)]
            found = kept or found
        return _distinct(row.variants() for row in found)


def _bare_lemma(lemma: str) -> str:
    """A verb's lemma without the reflexive the table writes into it: `s'abader`."""
    low = lemma.lower().translate(_APOSTROPHES)
    for prefix in ("s'", "se "):
        if low.startswith(prefix):
            return low[len(prefix) :]
    return low


def _agrees(row: Reading, lemma: str, pos: str, feats: str) -> bool:
    if lemma and _bare_lemma(row.lemma) != _bare_lemma(lemma):
        return False
    if pos in CATEGORIES and row.category not in CATEGORIES[pos]:
        return False
    number, mood, gender, tense, person = row.grammar
    cells = {
        "Number": number,
        "Gender": gender,
        "Person": person,
        "Mood": mood,
        "Tense": tense,
        "VerbForm": mood,
    }
    for part in (feats or "").split("|"):
        name, _, value = part.partition("=")
        allowed = FEATURES.get(name, {}).get(value)
        if not allowed or cells[name] in allowed:
            continue
        if name not in _LENIENT or cells[name] not in _UNMARKED:
            return False
    return True


def _distinct(groups: Iterable[frozenset[str]]) -> list[frozenset[str]]:
    out: list[frozenset[str]] = []
    for group in groups:
        joined = [known for known in out if known & group]
        for known in joined:
            out.remove(known)
        out.append(frozenset(group.union(*joined)))
    return out


def directory() -> Path:
    return model_dir() / "morphalou" / VERSION


def available() -> bool:
    return (directory() / TABLE).is_file()


def _download(url: str, sha256: str) -> bytes:
    import httpx

    try:
        answer = httpx.get(url, timeout=300.0, follow_redirects=True)
        answer.raise_for_status()
    except httpx.HTTPError as error:
        raise TargumError(f"Could not download {url}.", str(error)) from error
    body = answer.content
    got = hashlib.sha256(body).hexdigest()
    if got != sha256:
        raise TargumError(
            f"{url} is not the file this version of targum pins.",
            f"Expected sha256 {sha256}, got {got}. Nothing was written.",
        )
    return body


def fetch(notify: Callable[[str], None] | None = None) -> int:
    """The table and the licence, checked against their checksums, into the model
    directory. Returns the table's size in bytes."""
    say = notify or (lambda _message: None)
    say(ARCHIVE)
    archive = _download(SOURCE, SHA256)
    say(LICENCE_FILE)
    licence = _download(LICENCE_SOURCE, LICENCE_SHA256)
    with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
        name = next(entry for entry in bundle.namelist() if entry.endswith(f"/{TABLE}"))
        table = bundle.read(name).decode("utf-8")
    target = ensure(directory())
    write_atomic(target / LICENCE_FILE, licence.decode("utf-8"))
    write_atomic(target / TABLE, table)
    load.cache_clear()
    return len(table.encode("utf-8"))


def rows(lines: Iterable[str]) -> Iterator[tuple[str, str, str, Grammar, str]]:
    """The table's rows as (lemma, category, form, grammar, transcription).

    A lemma's spelling and category are written on its first row only, so they are carried
    down to the forms that follow it.
    """
    lines = iter(lines)
    for line in lines:
        if line.startswith(_HEADER):
            break
    lemma = category = ""
    for cells in csv.reader(lines, delimiter=";"):
        if len(cells) <= _PHONETIC:
            continue
        if cells[_LEMMA]:
            lemma, category = cells[_LEMMA], cells[_CATEGORY]
        number, mood, gender, tense, person = cells[_GRAMMAR]
        yield (
            lemma,
            category,
            cells[_FORM],
            (number, mood, gender, tense, person),
            cells[_PHONETIC].strip(),
        )


def parse(lines: Iterable[str]) -> Lexicon:
    lexicon = Lexicon()
    for lemma, category, form, grammar, phonetic in rows(lines):
        if not form:
            continue
        if phonetic:
            lexicon.readings.setdefault(form, []).append(
                Reading(lemma, category, grammar, phonetic)
            )
        else:
            lexicon.bare.add(form)
    lexicon.bare -= lexicon.readings.keys()
    return lexicon


@functools.lru_cache(maxsize=1)
def load(folder: Path | None = None) -> Lexicon:
    """The table, read once a process. Raises where it was never fetched."""
    path = (folder or directory()) / TABLE
    if not path.is_file():
        raise TargumError("Morphalou is not downloaded.", "targum models fetch morphalou")
    with path.open(encoding="utf-8", newline="") as handle:
        return parse(line.rstrip("\r\n") for line in handle)


def lexicon() -> Lexicon | None:
    """The table where this machine has it, and None where it does not."""
    if not available():
        return None
    return load()
