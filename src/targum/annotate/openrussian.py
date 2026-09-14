"""Russian words as a dictionary spells them: stress, aspect partners, how a word inflects.

A Russian learner's two facts no spelling gives are where the stress falls and which verb
is the other half of an aspect pair, and both are in one open dictionary: OpenRussian.org,
built from Wiktionary and corrected by its users, whose tables carry every noun's and
adjective's declension and every verb's conjugation with the stress marked, and every
verb's aspect and partner.

**Looked up, never learned from, never shipped** (David's decision of 2026-09-14,
targum-internal#259). The data is CC BY-SA 4.0. It is fetched into the model directory by
`targum models fetch openrussian` and read here; no row of it is in this repository or in
the wheel, and no model is trained on it. What reaches a reader is a fact about one word —
говори́ть is сказа́ть's partner, рука́ is ру́ку in the accusative — and the reader credits
OpenRussian at its foot wherever one was shown. A machine without the data builds exactly
as it did before.

**Where the dictionary is unsure, nothing is said.** Its README says the data "is not void
of flaws", and a spelling can be two words — за́мок and замо́к are two rows. A lemma the
dictionary files twice with different stress, or different partners, gets no partner and
no stress line: a learner believes what a card says.

The accent is written in the tables as an apostrophe after the stressed vowel; ё is
stressed by definition and carries no mark. Here it becomes U+0301, the combining acute,
which is what a Russian textbook prints.
"""

from __future__ import annotations

import csv
import functools
import urllib.request
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path

from ..errors import TargumError
from ..paths import ensure, model_dir, write_atomic

#: The commit the tables are read at, so a build today and a build next year say the same
#: thing about a word. The CSVs are the project's public backup; its README says they lag
#: the live database, which is the price of a pinned, reproducible copy.
COMMIT = "50e210c4803237779cb562bc1abcea529066031c"
SOURCE = f"https://raw.githubusercontent.com/Badestrand/russian-dictionary/{COMMIT}/{{name}}.csv"
FILES = ("nouns", "verbs", "adjectives", "others")

CREDIT = "OpenRussian.org"
LICENCE = "CC BY-SA 4.0"
LICENCE_URL = "https://creativecommons.org/licenses/by-sa/4.0/"
NAME = f"openrussian/{COMMIT[:7]}"

ACUTE = "́"
VOWELS = frozenset("аеёиоуыэюяАЕЁИОУЫЭЮЯ")

#: The noun and adjective columns a stress line may quote, in the order a table reads.
NOUN_COLUMNS = (
    "sg_nom sg_gen sg_dat sg_acc sg_inst sg_prep pl_nom pl_gen pl_dat pl_acc pl_inst pl_prep"
).split()
#: A verb's, in the order a learner meets them: the infinitive stands in front.
VERB_COLUMNS = (
    "presfut_sg1 presfut_sg2 presfut_sg3 presfut_pl1 presfut_pl2 presfut_pl3 "
    "past_m past_f past_n past_pl imperative_sg imperative_pl"
).split()

#: The columns that hold an inflected form rather than a fact about the word.
INFLECTED = ("sg_", "pl_", "decl_", "short_", "past_", "presfut_", "imperative_")

#: How many forms a stress line quotes, the dictionary form included.
STRESS_LINE = 3

#: Universal Dependencies' case and number, as the tables head their columns.
CASE_COLUMNS = {
    "Nom": "nom",
    "Gen": "gen",
    "Dat": "dat",
    "Acc": "acc",
    "Ins": "inst",
    "Loc": "prep",
}
NUMBER_COLUMNS = {"Sing": "sg", "Plur": "pl"}


def directory() -> Path:
    return model_dir() / "openrussian" / COMMIT


def available() -> bool:
    return all((directory() / f"{name}.csv").is_file() for name in FILES)


def fetch(notify: Callable[[str], None] | None = None) -> int:
    """The four tables, from the pinned commit, into the model directory."""
    target = ensure(directory())
    for name in FILES:
        if notify:
            notify(f"{name}.csv")
        try:
            with urllib.request.urlopen(SOURCE.format(name=name), timeout=120) as answer:
                body = answer.read()
        except OSError as error:
            raise TargumError(f"Could not download OpenRussian's {name}.", str(error)) from error
        write_atomic(target / f"{name}.csv", body.decode("utf-8"))
    load.cache_clear()
    return len(FILES)


def accented(written: str) -> str:
    """A table's spelling — рука' — as print spells it: рука́."""
    return written.replace("'", ACUTE)


def vowels(word: str) -> int:
    return sum(char in VOWELS for char in word)


def stressed_syllable(written: str) -> int | None:
    """Which vowel carries the stress, counted from the start, or None where the table
    does not say. A word with ё is stressed on it; a word of one vowel on that vowel."""
    at = written.find("'")
    if at > 0:
        return vowels(written[:at]) - 1
    if "ё" in written or "Ё" in written:
        return vowels(written[: max(written.find("ё"), written.find("Ё"))])
    return 0 if vowels(written) == 1 else None


def bare(written: str) -> str:
    return written.replace("'", "").strip()


def fold(written: str) -> str:
    """The key a spelling is filed under: no mark, lower case, ё as е — since running text
    mostly writes ё as е, and the tables always write it."""
    return bare(written).replace(ACUTE, "").lower().replace("ё", "е")


def plain(word: str) -> str:
    """For display: the mark left off a word of one vowel, which no textbook marks."""
    return word.replace(ACUTE, "") if vowels(word) <= 1 else word


def _variants(cell: str) -> list[str]:
    parts = (part.strip() for part in (cell or "").split(","))
    return [part for part in parts if part and part != "0"]


@dataclass
class Entry:
    """One row of a table: a word and what the dictionary says about it."""

    kind: str
    written: str
    aspect: str = ""
    partners: tuple[str, ...] = ()
    forms: dict[str, list[str]] = field(default_factory=dict)


@dataclass
class Lexicon:
    entries: dict[str, list[Entry]] = field(default_factory=dict)
    #: Every written form, folded (`fold`), to the stressed spellings the tables give it.
    spellings: dict[str, set[str]] = field(default_factory=dict)

    def rows(self, lemma: str, kind: str | None = None) -> list[Entry]:
        found = self.entries.get(lemma.lower().replace(ACUTE, ""), [])
        return [row for row in found if kind is None or row.kind == kind]

    def headword(self, lemma: str) -> str:
        """The dictionary form stressed, where every row that spells it agrees."""
        heads = {accented(row.written) for row in self.rows(lemma) if "'" in row.written}
        return heads.pop() if len(heads) == 1 else ""

    def aspect(self, lemma: str) -> str:
        found = {row.aspect for row in self.rows(lemma, "verb")}
        return found.pop() if len(found) == 1 else ""

    def partners(self, lemma: str) -> list[str]:
        """The other half of a verb's aspect pair, stressed, where the dictionary names one
        partner set for the spelling. A lemma filed twice with different partners — писать
        is two verbs in the tables — gets none."""
        sets = {row.partners for row in self.rows(lemma, "verb")}
        if len(sets) != 1:
            return []
        out = []
        for partner in sets.pop():
            out.append(self.headword(partner) or partner)
        return out

    def stress_line(self, lemma: str) -> list[str]:
        """The dictionary form and the forms where its stress lands elsewhere, stressed.

        Empty where the stress never moves, or where the dictionary spells the lemma two
        ways. Each form is quoted only if its stress falls on a syllable no earlier form
        in the line has, counted from the start of the word — рука́ · ру́ку · ру́ки, but
        not a fourth form stressed like one already there.
        """
        rows = self.rows(lemma)
        if len(rows) != 1 or rows[0].kind not in {"noun", "verb"}:
            return []
        row = rows[0]
        columns = NOUN_COLUMNS if row.kind == "noun" else VERB_COLUMNS
        head = row.forms.get("sg_nom", [row.written])[0] if row.kind == "noun" else row.written
        first = stressed_syllable(head)
        if first is None:
            return []
        seen = {first}
        line = [head]
        for column in columns:
            for form in row.forms.get(column, [])[:1]:
                place = stressed_syllable(form)
                if place is None or place in seen:
                    continue
                seen.add(place)
                line.append(form)
            if len(line) >= STRESS_LINE:
                break
        return [plain(accented(form)) for form in line] if len(line) > 1 else []

    def form(self, lemma: str, feats: str) -> list[str]:
        """The stressed spellings a noun's table gives for the case and number a word is
        tagged with, all the variants the cell holds."""
        values = dict(part.partition("=")[::2] for part in (feats or "").split("|"))
        case = CASE_COLUMNS.get(values.get("Case", ""))
        number = NUMBER_COLUMNS.get(values.get("Number", ""))
        if not case or not number:
            return []
        out: list[str] = []
        for row in self.rows(lemma, "noun"):
            out.extend(accented(form) for form in row.forms.get(f"{number}_{case}", []))
        return out


def _read(path: Path) -> Iterator[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        yield from csv.DictReader(handle, delimiter="\t")


@functools.lru_cache(maxsize=1)
def load(folder: Path | None = None) -> Lexicon:
    """The tables, read once a process. Raises where they were never fetched."""
    where = folder or directory()
    if not all((where / f"{name}.csv").is_file() for name in FILES):
        raise TargumError(
            "OpenRussian's tables are not downloaded.", "targum models fetch openrussian"
        )
    lexicon = Lexicon()
    for name in FILES:
        kind = {"nouns": "noun", "verbs": "verb", "adjectives": "adjective"}.get(name, "other")
        for row in _read(where / f"{name}.csv"):
            word = bare(row.get("bare") or "").lower()
            if not word:
                continue
            forms = {
                column: _variants(value)
                for column, value in row.items()
                if column and value and column.startswith(INFLECTED)
            }
            partners = tuple(
                p.strip()
                for p in (row.get("partner") or "").split(";")
                if p.strip() and p.strip() != "-"
            )
            entry = Entry(
                kind=kind,
                written=(row.get("accented") or word).strip(),
                aspect=(row.get("aspect") or "").strip(),
                partners=partners if kind == "verb" else (),
                forms={column: values for column, values in forms.items() if values},
            )
            lexicon.entries.setdefault(word, []).append(entry)
            for written in [entry.written, *(v for vs in entry.forms.values() for v in vs)]:
                lexicon.spellings.setdefault(fold(written), set()).add(written)
    return lexicon


def lexicon() -> Lexicon | None:
    """The tables where this machine has them, and None where it does not."""
    if not available():
        return None
    return load()
