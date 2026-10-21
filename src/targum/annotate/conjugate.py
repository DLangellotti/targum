"""Filling a thin verb table by rule, from its root and binyan (targum-internal#307).

Most of the table's verbs carry all thirty-two cells a Hebrew verb has. A few dozen are
stubs: `אָכַל` came through with ten forms and no present singular, so `אוכל` — 819 verb
tokens on the shelf — had no candidate that eats, and the card drew nothing. Filling them
by hand does not scale and buying a source opens a licence door, so this fills them by
rule, at no cost.

**The rule is learned from the table itself.** A verb's root and binyan, with the root's
weak letters said out loud, are the class it conjugates in: `כתב` and `שמר` share one,
`אכל` and `אמר` another, because an א in first place spells differently. Every complete
table of a class is read as a pattern — each cell with the root's ordinary letters taken
out — and a thin verb of the same class is filled by putting its own letters back.

Only tables spelled the way a text is spelled are learned from: unpointed, full spelling
(`כותב`, `יכתוב`). A pointed table writes `כֹּתֵב`, whose letters are `כתב`, and the two
systems would read as two different verbs.

**A wrong table is worse than none, so this refuses more than it fills.**

- Every form the source already has is a constraint. A pattern that would spell any of
  them differently is not this verb's pattern, and a verb no pattern agrees with is
  refused whole.
- Where the patterns that do agree disagree about a cell — `יאכל` against `יאסוף`, the
  future vowel a dictionary has to tell you — that cell is left empty.
- A pointed lemma says its binyan (`paradigms.binyan_of`), and only that binyan's patterns
  are asked. An unpointed one asks all seven, which the forms it has must then settle.
- Too few forms, or too few tables behind the patterns, is a refusal too.

The source's forms are never changed. What this adds is kept apart from them in the
shipped file (`filled`), so it can be told apart, measured, and dropped.
"""

from __future__ import annotations

import itertools
import re
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from functools import cache

#: The thirty-two cells a Hebrew verb table has, in the order a grammar lays them out.
#: Each is the sorted tuple of feature names the shipped table uses, so a form's own
#: `features` is its cell.
CELLS: tuple[tuple[str, ...], ...] = tuple(
    tuple(sorted(cell))
    for cell in (
        ("1st", "past", "singular"),
        ("1st", "past", "plural"),
        ("2nd", "masculine", "past", "singular"),
        ("2nd", "feminine", "past", "singular"),
        ("2nd", "masculine", "past", "plural"),
        ("2nd", "feminine", "past", "plural"),
        ("3rd", "masculine", "past", "singular"),
        ("3rd", "feminine", "past", "singular"),
        ("3rd", "masculine", "past", "plural"),
        ("3rd", "feminine", "past", "plural"),
        ("masculine", "present", "singular"),
        ("feminine", "present", "singular"),
        ("masculine", "plural", "present"),
        ("feminine", "plural", "present"),
        ("masculine", "participle", "present", "singular"),
        ("feminine", "participle", "present", "singular"),
        ("masculine", "participle", "plural", "present"),
        ("feminine", "participle", "plural", "present"),
        ("1st", "future", "singular"),
        ("1st", "future", "plural"),
        ("2nd", "future", "masculine", "singular"),
        ("2nd", "feminine", "future", "singular"),
        ("2nd", "future", "masculine", "plural"),
        ("2nd", "feminine", "future", "plural"),
        ("3rd", "future", "masculine", "singular"),
        ("3rd", "feminine", "future", "singular"),
        ("3rd", "future", "masculine", "plural"),
        ("3rd", "feminine", "future", "plural"),
        ("2nd", "imperative", "masculine", "singular"),
        ("2nd", "feminine", "imperative", "singular"),
        ("2nd", "imperative", "masculine", "plural"),
        ("2nd", "feminine", "imperative", "plural"),
    )
)
_AT = {cell: at for at, cell in enumerate(CELLS)}
#: The third person masculine singular past, which is what a lemma is.
LEMMA_CELL = _AT[("3rd", "masculine", "past", "singular")]
_IMPERATIVE = frozenset(at for at, cell in enumerate(CELLS) if "imperative" in cell)

#: Root letters that change how a verb is spelled, and so are part of its class rather
#: than letters a pattern can carry for any root: the gutturals and ר, which cannot be
#: doubled; א, ה, ו, י and נ, which drop out, assimilate or turn into vowels.
LITERAL = frozenset("אהוחינער")
#: In a הִתְפַּעֵל, a root beginning with one of these trades places with the ת or bends
#: it — הִסְתַּכֵּל, הִצְטָרֵף, הִזְדַּקֵּן, הִדַּבֵּר — so it is part of the class there too.
_SWAPS = frozenset("סשצזדטת")

_FINAL_OF = str.maketrans("כמנפצ", "ךםןףץ")
_PLAIN_OF = str.maketrans("ךםןףץ", "כמנפצ")

#: The fewest standard cells a verb must already have before it is filled, its lemma
#: included where the lemma is unpointed. Below this the forms cannot tell the patterns
#: apart, and agreement among patterns that were never tested is not evidence.
LEAST_SEEN = 3
#: The fewest complete tables that must stand behind the patterns that fill a verb.
LEAST_SUPPORT = 3


def plain(text: str) -> str:
    """The Hebrew letters alone, with every final letter written as the ordinary one."""
    out = "".join(
        ch
        for ch in unicodedata.normalize("NFD", text or "")
        if not unicodedata.combining(ch) and "א" <= ch <= "ת"
    )
    return out.translate(_PLAIN_OF)


def finished(letters: str) -> str:
    """The letters as they are written, the last one in its final form."""
    return letters[:-1] + letters[-1:].translate(_FINAL_OF) if letters else letters


def pointed(text: str) -> bool:
    """Whether a spelling carries any nikkud."""
    return any(unicodedata.combining(ch) for ch in unicodedata.normalize("NFD", text or ""))


def shape(root: str, binyan: str) -> tuple[str, dict[str, str]] | None:
    """A root's class in a binyan, and the ordinary letters the class leaves open.

    The class is the root with each ordinary letter replaced by its position — `כתב` is
    `123`, `אכל` is `א23`, `סבב` is `122` — so two roots of one class differ only in
    letters every pattern of the class carries the same way.
    """
    letters = plain(root)
    if len(letters) != 3:
        return None
    key: list[str] = []
    slots: dict[str, str] = {}
    for at, letter in enumerate(letters):
        if letter in LITERAL or (binyan == "התפעל" and at == 0 and letter in _SWAPS):
            key.append(letter)
        elif at == 2 and "2" in slots and slots["2"] == letter:
            # A doubled root: its last two letters are one, and often written once.
            key.append("2")
        else:
            name = str(at + 1)
            slots[name] = letter
            key.append(name)
    return f"{binyan}:{''.join(key)}", slots


def _order(klass: str) -> list[str]:
    """The open positions of a class, in order: `א23` is `['2', '3']`."""
    return [ch for ch in klass.split(":", 1)[1] if ch.isdigit()]


def templates(letters: str, slots: Mapping[str, str], klass: str) -> set[str]:
    """Every way a written form could be its class's pattern with these root letters.

    Usually one. A root letter that is also an affix's — the מ of `מימש`, the ת of
    `תפסת` — could be either, and both readings are kept for the table-wide count to
    choose between (`learn`).
    """
    wanted = _order(klass)
    once = [name for at, name in enumerate(wanted) if not at or wanted[at - 1] != name]
    choices: list[list[str]] = []
    for letter in letters:
        options = [letter] + [name for name, value in slots.items() if value == letter]
        choices.append(options)
    found: set[str] = set()
    for picked in itertools.product(*choices):
        names = [ch for ch in picked if ch.isdigit()]
        if names == wanted or names == once:
            found.add("".join(picked))
        if len(found) > 8:
            break
    return found


def spell(template: str, slots: Mapping[str, str]) -> str:
    """A pattern's cell with this root's letters put back, in plain letters."""
    return "".join(slots.get(ch, ch) for ch in template)


@cache
def _reader(template: str) -> re.Pattern[str]:
    """A pattern's cell as a question: which root letters would spell this form?"""
    out: list[str] = []
    seen: set[str] = set()
    for ch in template:
        if ch.isdigit():
            out.append(f"(?P=s{ch})" if ch in seen else f"(?P<s{ch}>[א-ת])")
            seen.add(ch)
        else:
            out.append(re.escape(ch))
    return re.compile("".join(out))


@dataclass(frozen=True)
class Pattern:
    """How one class conjugates: a template per cell, or None where it has no such form."""

    klass: str
    cells: tuple[str | None, ...]

    @property
    def binyan(self) -> str:
        return self.klass.split(":", 1)[0]


#: The patterns, by class, each with how many complete tables follow it.
Patterns = dict[str, Counter[Pattern]]


def cells_of(forms: Iterable[tuple[str, tuple[str, ...]]]) -> dict[int, set[str]]:
    """A verb's forms by cell, in plain letters. Forms in no standard cell are left out."""
    out: dict[int, set[str]] = defaultdict(set)
    for written, features in forms:
        at = _AT.get(tuple(sorted(features)))
        letters = plain(written)
        if at is not None and letters:
            out[at].add(letters)
    return out


def learn(verbs: Iterable[tuple[str, str, str, Iterable[tuple[str, tuple[str, ...]]]]]) -> Patterns:
    """The patterns the complete, unpointed tables follow, by class.

    `verbs` is each verb's lemma, binyan, root and forms. A table teaches only where it
    is whole — every cell once, its imperatives all there or all absent, as a passive's
    are — unpointed, and its own third person masculine singular past is its lemma.
    """
    rows: list[tuple[str, list[set[str] | None]]] = []
    counts: dict[tuple[str, int], Counter[str]] = defaultdict(Counter)
    for lemma, binyan, root, forms in verbs:
        forms = list(forms)
        if not forms or any(pointed(written) for written, _ in forms):
            continue
        made = shape(root, binyan)
        if made is None:
            continue
        klass, slots = made
        cells = cells_of(forms)
        if any(len(values) != 1 for values in cells.values()):
            continue
        have = set(cells)
        missing = set(range(len(CELLS))) - have
        if missing and missing != set(_IMPERATIVE):
            continue
        if {_thin(one) for one in cells.get(LEMMA_CELL, ())} != {_thin(plain(lemma))}:
            continue
        options: list[set[str] | None] = []
        for at in range(len(CELLS)):
            if at in missing:
                options.append(None)
                continue
            found = templates(next(iter(cells[at])), slots, klass)
            if not found:
                break
            options.append(found)
        else:
            rows.append((klass, options))
            for at, option in enumerate(options):
                for one in option or ():
                    counts[(klass, at)][one] += 1
    out: Patterns = defaultdict(Counter)
    for klass, options in rows:
        chosen = tuple(
            None if found is None else max(found, key=lambda t: (counts[(klass, at)][t], t))
            for at, found in enumerate(options)
        )
        out[klass][Pattern(klass, chosen)] += 1
    return dict(out)


@dataclass(frozen=True)
class Filled:
    """What filling one verb came to: the cells added, or why none were."""

    forms: tuple[tuple[str, tuple[str, ...]], ...] = ()
    #: Why nothing was added, where nothing was. Empty where something was, or where
    #: the verb lacked nothing.
    refused: str = ""
    #: Cells the agreeing patterns could not agree on, and so left empty.
    withheld: int = 0


def fill(
    lemma: str,
    forms: Iterable[tuple[str, tuple[str, ...]]],
    patterns: Patterns,
    binyan: str | None = None,
) -> Filled:
    """The cells a verb is missing, spelled by rule — or a refusal.

    `binyan` is what the lemma's pointing says, where it says anything; only that
    binyan's patterns are then asked. The forms the verb already has must all be spelled
    exactly as a pattern spells them, or that pattern is not this verb's.
    """
    seen = cells_of(forms)
    if not pointed(lemma) and plain(lemma):
        seen[LEMMA_CELL].add(plain(lemma))
    missing = [at for at in range(len(CELLS)) if at not in seen]
    if not missing:
        return Filled()
    if len(seen) < LEAST_SEEN:
        return Filled(refused="too few forms")

    agreeing: list[tuple[Pattern, dict[str, str], int]] = []
    for klass, counted in patterns.items():
        if binyan and not klass.startswith(binyan + ":"):
            continue
        for pattern, support in counted.items():
            slots = _slots(pattern, seen)
            if slots is None:
                continue
            if pointed(lemma) and not _same_word(lemma, pattern, slots):
                continue
            agreeing.append((pattern, slots, support))
    if not agreeing:
        return Filled(refused="no pattern spells its forms")
    if sum(support for _, _, support in agreeing) < LEAST_SUPPORT:
        return Filled(refused="too few tables behind it")

    added: list[tuple[str, tuple[str, ...]]] = []
    withheld = 0
    for at in missing:
        said = {
            None if pattern.cells[at] is None else spell(str(pattern.cells[at]), slots)
            for pattern, slots, _ in agreeing
        }
        if len(said) != 1:
            withheld += 1
            continue
        (letters,) = said
        if letters:
            added.append((finished(letters), CELLS[at]))
    if not added:
        return Filled(refused="the patterns that fit disagree", withheld=withheld)
    return Filled(forms=tuple(added), withheld=withheld)


def _slots(pattern: Pattern, seen: Mapping[int, set[str]]) -> dict[str, str] | None:
    """The root letters that make this pattern spell every form the verb has, or None."""
    slots: dict[str, str] | None = None
    for at, values in seen.items():
        template = pattern.cells[at]
        if template is None:
            return None
        if slots is None:
            for value in sorted(values):
                found = _reader(template).fullmatch(value)
                if found:
                    slots = {key[1:]: letter for key, letter in found.groupdict().items()}
                    break
            if slots is None:
                return None
        if spell(template, slots) not in values:
            return None
    if slots is None:
        return None
    root = "".join(slots.get(ch, ch) for ch in pattern.klass.split(":", 1)[1])
    made = shape(root, pattern.binyan)
    if made is None or made[0] != pattern.klass:
        # The letters read off are ones the class keeps literal: the verb is of another.
        return None
    return slots


def _same_word(lemma: str, pattern: Pattern, slots: Mapping[str, str]) -> bool:
    """Whether a pointed lemma is the pattern's lemma, spelled without its vowel letters.

    A pointed `אִכֵּל` has the letters `אכל` where the full spelling is `איכל`, so the
    two are compared with the ו and י that only stand for vowels set aside.
    """
    template = pattern.cells[LEMMA_CELL]
    if template is None:
        return False
    return _thin(plain(lemma)) == _thin(spell(template, slots))


def _thin(letters: str) -> str:
    """The letters with every ו and י after the first set aside: a pointed spelling and
    a full one of the same word come out the same."""
    return letters[:1] + letters[1:].replace("ו", "").replace("י", "")
