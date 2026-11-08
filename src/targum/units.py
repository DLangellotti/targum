"""Multiword units: an idiom is one word to know (design.md §12, "An idiom is one word to
know", 2026-11-05; targum-internal#614).

`units.tsv` beside this file is ling-he's hand-picked list (2026-11-05): each row a key of
DICTA lemmas joined by a space, as `tables.words.count` writes a phrase, its written
form, an English gloss, its register and ling-he's note. `needs` is the one column added
for the matcher: for a key that means the expression only with a prefix, the prefix
letter each word must carry, `|` between words (מכל מקום is `מ|`, מפעם לפעם `מ|ל`).

French and Russian lists sit beside it as `units-fr.tsv` and `units-ru.tsv`, written
by ling-fr and ling-ru, in the same columns (targum-internal#636). Their `lemmas` are the
annotator's dictionary forms, so an inflected unit (иметь в виду, имею в виду) matches
however it is inflected. An elided word is folded to its full form on both sides — the
list may write d'abord, and the annotator's l', qu', du are le, que, de — and a word
written with a hyphen matches as one token or as its pieces. `needs` is Hebrew's alone.
A language without a list has no units.

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

#: The folder the lists are in: the package.
FOLDER = Path(__file__).parent

#: Hebrew's list, in the package.
PATH = FOLDER / "units.tsv"

#: The languages the matcher reads: ling-he's list is Hebrew's, and French and Russian
#: are read from `units-<language>.tsv` where it is there (targum-internal#636).
LANGUAGES = frozenset({"he", "fr", "ru"})

#: An elided or contracted French word, folded to the dictionary form the annotator
#: gives (`model_lemma.SYSTEM`: "for a contraction of a preposition and an article give
#: the preposition").
ELIDED = {
    "c'": "ce",
    "d'": "de",
    "j'": "je",
    "l'": "le",
    "m'": "me",
    "n'": "ne",
    "s'": "se",
    "t'": "te",
    "qu'": "que",
    "jusqu'": "jusque",
    "lorsqu'": "lorsque",
    "puisqu'": "puisque",
    "quoiqu'": "quoique",
    "quelqu'": "quelque",
    "du": "de",
    "au": "à",
    "aux": "à",
}

#: A French reflexive pronoun: a list's `se` is said me, te, nous or vous too
#: (je me rends compte, nous nous trompons).
REFLEXIVE = frozenset({"se", "me", "te", "nous", "vous"})

#: The most words a discontinuous French or Russian unit may have between two of its
#: parts, whatever its `needs` says: a segment is a sentence, so it never crosses one.
MOST_BETWEEN = 8

#: Words a clause starts after, besides punctuation and a conjunction (`^`).
RELATIVES = frozenset({"qui", "que", "où", "dont", "lequel", "quoi", "который", "что", "где"})

#: French negation particles. A gap after `ne` stops at any of them that is not the
#: part it looks for: in ne… pas que, ne… pas plus, the ne is pas's, and the que, the
#: plus are other words.
NEGATIONS = frozenset(
    {"pas", "point", "plus", "jamais", "rien", "personne", "guère", "aucun", "nul", "que", "ni"}
)

#: The most characters between two words of one unit: a space or a maqaf.
GAP = 1

#: Letters a Hebrew word may carry before its stem.
PREFIX_LETTERS = frozenset("ובכלמשה")

#: The status a mark says known with (`coverage.KNOWN`), restated so this module has no
#: import cycle with coverage.
KNOWN = 9


@dataclass(frozen=True)
class Rule:
    """What a French or Russian `needs` cell asks of one word besides its gap and its
    written form. Each set holds tags (NOUN), features (VerbForm=Inf) or words."""

    #: `-X`: the word itself is none of these (y avoir, where avoir is not an AUX).
    is_not: frozenset[str] = frozenset()
    #: `+X`: the word right after it is one of these (venir de + an infinitive).
    then: frozenset[str] = frozenset()
    #: `!X`: the word right after it is none of these (même si, not before an adverb).
    then_not: frozenset[str] = frozenset()
    #: `<!X`: the word right before it is none of these (ne… que, not ce que).
    after_not: frozenset[str] = frozenset()
    #: `@X`: the first noun or pronoun after it is one of these (у + a person).
    noun: frozenset[str] = frozenset()
    #: `^`: it starts a clause; `^^`: it starts the segment.
    starts: int = 0


@dataclass(frozen=True)
class Unit:
    """One expression counted as one word."""

    key: str
    parts: tuple[str, ...]
    #: The prefix letter each part must carry, "" where none is needed.
    needs: tuple[str, ...]
    #: Its written forms, unpointed, each as a run of words.
    written: tuple[tuple[str, ...], ...]
    #: French and Russian: how many words may stand between each part and the one
    #: before it, 0 where none may (ne… que, не только… но и). Empty in Hebrew.
    gaps: tuple[int, ...] = ()
    #: French and Russian: the written forms each part must have, empty where any will
    #: do (the est-ce of est-ce que, the может of может быть). Empty in Hebrew.
    forms: tuple[frozenset[str], ...] = ()
    #: French and Russian: whether punctuation may stand in the gap before each part,
    #: as the comma before the но и of не только… но и does. Elsewhere it ends a gap.
    commas: tuple[bool, ...] = ()
    #: French and Russian: what else each part asks of its token and its neighbours
    #: (`Rule`). Empty in Hebrew.
    rules: tuple[Rule, ...] = ()
    #: French and Russian: the unit stands at a clause's edge on one side at least.
    edge: bool = False


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


def base(language: str) -> str:
    """The language a code names, without its region (fr-CA is fr)."""
    return (language or "he").split("-")[0]


def path_for(language: str = "he") -> Path:
    """Where a language's list is: Hebrew's `units.tsv`, any other `units-<code>.tsv`."""
    code = base(language)
    return FOLDER / "units.tsv" if code == "he" else FOLDER / f"units-{code}.tsv"


_APOSTROPHES = str.maketrans({"\u2019": "'", "\u02bc": "'", "\u2018": "'"})


def fold(word: str) -> str:
    """A French or Russian word as the matcher compares it: composed, lowercase, the
    curly apostrophe straight, ё read as е, an elided or contracted French word its
    full form."""
    word = unicodedata.normalize("NFC", word).lower().translate(_APOSTROPHES)
    word = word.replace("ё", "е").strip()
    return ELIDED.get(word, word)


def words(text: str) -> tuple[str, ...]:
    """A French or Russian run of words, each `fold`ed: split at spaces and after an
    apostrophe (d'abord is d' and abord), anything that is not a letter, an apostrophe
    or a hyphen dropped, a hyphen kept inside its word."""
    text = unicodedata.normalize("NFC", text).translate(_APOSTROPHES)
    text = re.sub(r"'(?=\w)", "' ", text)
    out = []
    for one in text.split():
        kept = "".join(char for char in one if char.isalpha() or char in "'-").strip("-")
        if kept:
            out.append(fold(kept))
    return tuple(out)


def _spelled(
    parts: tuple[str, ...],
) -> list[tuple[tuple[str, ...], tuple[tuple[int, bool], ...]]]:
    """Every way the annotator may cut `parts`: a word with a hyphen as one token, or
    as its pieces, one apart (est-à-dire, or est, à, dire). Each with, for every word
    of it, the part it came from and whether it is that part's first."""
    out: list[tuple[tuple[str, ...], tuple[tuple[int, bool], ...]]] = [((), ())]
    for n, part in enumerate(parts):
        pieces = tuple(fold(piece) for piece in part.split("-") if piece)
        ways = [(part,)] if len(pieces) < 2 else [(part,), pieces]
        out = [
            (done + way, came + tuple((n, not k) for k in range(len(way))))
            for done, came in out
            for way in ways
        ]
    return out


def written(word: str) -> str:
    """A word as a `=form` compares it: composed, lowercase, the apostrophe straight, ё
    read as е, but not unfolded, so du is not de and au is not à."""
    word = unicodedata.normalize("NFC", word).lower().translate(_APOSTROPHES)
    return word.replace("ё", "е").strip()


def _set(text: str) -> frozenset[str]:
    return frozenset(
        one if one.isupper() or "=" in one else fold(one) for one in text.split("/") if one
    )


@dataclass(frozen=True)
class Needed:
    """A French or Russian row's `needs`, read (`_needed`)."""

    gaps: tuple[int, ...]
    forms: tuple[frozenset[str], ...]
    commas: tuple[bool, ...]
    rules: tuple[Rule, ...]
    edge: bool


def _needed(cell: str, count: int) -> Needed:
    """A French or Russian `needs` cell, one entry per word, `|` between, each entry's
    marks space-separated:

    - `~N` lets up to N words stand before the word (ne|~6 is ne… que), and `~N,` lets
      punctuation stand among them too (ни|~6, is ни X, ни Y);
    - `=form` holds the word to that written form, alternatives split on "/" (=может);
    - `-X`, `+X`, `!X`, `<!X`, `@X`, `^`, `^^`: a `Rule`;
    - `edge`, on any word: the unit touches a clause's edge (может быть, set off).
    """
    cells = cell.split("|") if cell.strip() else []
    gaps: list[int] = []
    forms: list[frozenset[str]] = []
    commas: list[bool] = []
    rules: list[Rule] = []
    edge = False
    for at in range(count):
        gap = 0
        comma = False
        held: set[str] = set()
        rule: dict[str, Any] = {}
        for one in (cells[at] if at < len(cells) else "").split():
            if one.startswith("~") and one[1:].rstrip(",").isdigit():
                gap = min(int(one[1:].rstrip(",")), MOST_BETWEEN) if at else 0
                comma = bool(at) and one.endswith(",")
            elif one.startswith("=") and one[1:]:
                held.update(written(form) for form in one[1:].split("/") if form)
            elif one in ("^", "^^"):
                rule["starts"] = len(one)
            elif one == "edge":
                edge = True
            elif one.startswith("<!") and one[2:]:
                rule["after_not"] = _set(one[2:])
            elif one[:1] in "-+!@" and one[1:]:
                name = {"-": "is_not", "+": "then", "!": "then_not", "@": "noun"}[one[0]]
                rule[name] = _set(one[1:])
            else:
                raise ValueError(f"units: cannot read {one!r} in needs {cell!r}")
        gaps.append(gap)
        forms.append(frozenset(held))
        commas.append(comma)
        rules.append(Rule(**rule))
    return Needed(tuple(gaps), tuple(forms), tuple(commas), tuple(rules), edge)


def _written_words(surface: str) -> tuple[tuple[str, ...], ...]:
    """`_written` for French and Russian: a hyphen read as a space, as `plain` reads a
    maqaf."""
    out: list[tuple[str, ...]] = []
    for one in surface.split("/"):
        bare = re.sub(r"\([^)]*\)", " ", one)
        full = one.replace("(", " ").replace(")", " ")
        for form in (bare, full):
            found = tuple(piece for word in words(form) for piece in word.split("-") if piece)
            if found and found not in out:
                out.append(found)
    return tuple(out)


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


def load(path: Path | None = None, language: str = "he") -> tuple[Unit, ...]:
    """Every unit on a language's list, in the file's order: Hebrew's unless another
    language is named."""
    if path is None:
        path = PATH if base(language) == "he" else path_for(language)
    if base(language) == "he":
        return _load(path)
    return _load_words(path)


@lru_cache(maxsize=8)
def _load_words(path: Path) -> tuple[Unit, ...]:
    """A French or Russian list: each row a unit under its key, once for every way the
    annotator may cut a hyphenated word of it (`_spelled`)."""
    if not path.is_file():
        return ()
    rows = path.read_text(encoding="utf-8").splitlines()
    if not rows:
        return ()
    header = rows[0].split("\t")
    out: list[Unit] = []
    for line in rows[1:]:
        cells = dict(zip(header, line.split("\t"), strict=False))
        parts = words(str(cells.get("lemmas") or ""))
        if len(parts) < 2:
            continue
        written = _written_words(str(cells.get("surface") or ""))
        need = _needed(str(cells.get("needs") or ""), len(parts))
        gaps, forms, commas = need.gaps, need.forms, need.commas
        # A row may name the key it counts under, where its words are another cut of
        # a key's (être ce que for être que, where est-ce was cut in two).
        key = " ".join(words(str(cells.get("key") or ""))) or " ".join(parts)
        for spelled, at in _spelled(parts):
            out.append(
                Unit(
                    key=key,
                    parts=spelled,
                    needs=("",) * len(spelled),
                    written=written,
                    # A hyphenated word cut into pieces keeps its needs on its first.
                    gaps=tuple(gaps[n] if first else 0 for n, first in at),
                    forms=tuple(forms[n] if first else frozenset() for n, first in at),
                    commas=tuple(commas[n] if first else False for n, first in at),
                    rules=tuple(need.rules[n] if first else Rule() for n, first in at),
                    edge=need.edge,
                )
            )
    return tuple(out)


@lru_cache(maxsize=1)
def _load(path: Path = PATH) -> tuple[Unit, ...]:
    """Every unit on Hebrew's list, in the file's order."""
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


@lru_cache(maxsize=8)
def stamp(path: Path = PATH) -> str:
    """A short digest of the list, so a count cached under another list is counted
    again."""
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()[:12]
    except OSError:
        return ""


def stamps() -> str:
    """`stamp` of every list there is: Hebrew's, and each French or Russian list that is
    there. The stamp is one for every text, so a change to any list counts every text
    again once, Hebrew's too, from its stored lemmas (no spend); with no French or
    Russian list it reads as Hebrew's alone did."""
    out = stamp(PATH)
    for code in sorted(LANGUAGES - {"he"}):
        path = path_for(code)
        if path.is_file():
            out += f"+{code}:{stamp(path)}"
    return out


@lru_cache(maxsize=8)
def _by_first(language: str = "he") -> dict[str, tuple[Unit, ...]]:
    """The units by their first lemma, longest first."""
    held: dict[str, list[Unit]] = {}
    for unit in load(language=language):
        held.setdefault(unit.parts[0], []).append(unit)
    return {
        first: tuple(sorted(units, key=lambda unit: -len(unit.parts)))
        for first, units in held.items()
    }


def clear() -> None:
    """Forget every list read, so a list written since is read."""
    for cached in (_load, _load_words, stamp, _by_first):
        cached.cache_clear()


def keys(language: str = "he") -> frozenset[str]:
    """Every unit's key."""
    return frozenset(unit.key for unit in load(language=language))


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


def _read_as(token: Mapping[str, Any], code: str) -> tuple[str, ...]:
    """What a token may match a unit's word as: in Hebrew its lemma as DICTA gives it;
    in French and Russian its lemma `fold`ed, and its written form folded too, so a word
    of a fixed expression the list writes as it is written (the est of c'est-à-dire, cut
    at its hyphens) matches whatever lemma it was given."""
    lemma = str(token.get("lemma") or "")
    if code == "he":
        return (lemma,)
    folded = fold(lemma)
    said = fold(str(token.get("surface") or ""))
    return (folded,) if said in ("", folded) else (folded, said)


def _fits(unit: Unit, run: Sequence[Mapping[str, Any]]) -> bool:
    for at, token in enumerate(run):
        if str(token.get("lemma") or "") != unit.parts[at]:
            return False
        if at and int(token.get("start") or 0) - int(run[at - 1].get("end") or 0) > GAP:
            return False
        if unit.needs[at] and unit.needs[at] not in _prefix(token):
            return False
    return True


def match(tokens: Sequence[Mapping[str, Any]], language: str = "he") -> list[tuple[int, Unit]]:
    """The units in one segment's tokens, in order, as (index of the first token,
    unit): consecutive tokens whose lemmas are a unit's, with nothing but a space, a
    maqaf or a hyphen between them (an elided word's apostrophe is on its token) and
    each prefix the unit needs, the longest first. A token is in one unit at most.
    A discontinuous French or Russian unit's other tokens are in `found`."""
    return [(at[0], unit) for at, unit in found(tokens, language)]


def found(
    tokens: Sequence[Mapping[str, Any]], language: str = "he"
) -> list[tuple[tuple[int, ...], Unit]]:
    """`match`, with the index of every token of each unit: in Hebrew a run, in French
    and Russian a run or, for a discontinuous unit (ne… que), its parts with the words
    between them left to count as themselves."""
    code = base(language)
    if code != "he":
        return _found_words(tokens, code)
    table = _by_first(code)
    out: list[tuple[tuple[int, ...], Unit]] = []
    at = 0
    while at < len(tokens):
        hit = None
        for unit in table.get(str(tokens[at].get("lemma") or ""), ()):
            run = tokens[at : at + len(unit.parts)]
            if len(run) == len(unit.parts) and _fits(unit, run):
                hit = unit
                break
        if hit is None:
            at += 1
            continue
        out.append((tuple(range(at, at + len(hit.parts))), hit))
        at += len(hit.parts)
    return out


def _is(part: str, token: Mapping[str, Any], code: str) -> bool:
    """Whether a French or Russian token may be a unit's `part`."""
    read = _read_as(token, code)
    if part in read:
        return True
    return code == "fr" and part == "se" and any(one in REFLEXIVE for one in read)


def _place(
    unit: Unit, tokens: Sequence[Mapping[str, Any]], at: int, taken: set[int], code: str
) -> tuple[int, ...] | None:
    """Where a French or Russian unit's parts fall, its first at `at`: each next part
    the nearest token within its gap, held to its written form; a part with no gap
    one space or hyphen after the last, as in Hebrew. A gap ends at punctuation (a
    clause's comma) unless its part is a correlative's, which has one (`~N,`), and in
    French a gap after ne ends at another negation (ne… pas que is not ne… que)."""
    placed = [at]
    for n in range(len(unit.parts)):
        part = unit.parts[n]
        form = unit.forms[n] if n < len(unit.forms) else frozenset()
        gap = unit.gaps[n] if n < len(unit.gaps) else 0
        if n == 0:
            here = [at]
        else:
            last = placed[-1]
            here = list(range(last + 1, min(len(tokens), last + 2 + gap)))
        hit = None
        comma = unit.commas[n] if n < len(unit.commas) else False
        negated = code == "fr" and n > 0 and unit.parts[0] == "ne"
        for where in here:
            # A word another unit holds is never this one's, but a gap may pass it
            # (il n'y a que: y avoir holds y a, and ne… que reaches past it).
            if where in taken:
                continue
            token = tokens[where]
            if gap and not comma and _punctuated(tokens[where - 1], token):
                break
            if not _is(part, token, code):
                if negated and NEGATIONS & set(_read_as(token, code)):
                    break
                continue
            if form and written(str(token.get("surface") or "")) not in form:
                continue
            if n and not gap:
                before = tokens[placed[-1]]
                if int(token.get("start") or 0) - int(before.get("end") or 0) > GAP:
                    continue
            hit = where
            break
        if hit is None:
            return None
        if n < len(unit.rules) and not _keeps(unit.rules[n], tokens, hit, code):
            return None
        if n:
            placed.append(hit)
    if unit.edge and not (_edge_before(tokens, placed[0]) or _edge_after(tokens, placed[-1])):
        return None
    if code == "fr" and not _persons_agree(unit, tokens, placed):
        return None
    if code == "fr" and unit.parts[0] == "ne" and _expletive(tokens, placed):
        return None
    return tuple(placed)


def _one_of(token: Mapping[str, Any], wanted: frozenset[str], code: str) -> bool:
    """Whether a token is one of `wanted`: its tag, a feature it has, or its word."""
    if str(token.get("pos") or "") in wanted:
        return True
    feats = set(str(token.get("feats") or "").split("|"))
    if feats & wanted:
        return True
    return bool(set(_read_as(token, code)) & wanted)


def _edge_before(tokens: Sequence[Mapping[str, Any]], at: int) -> bool:
    return at == 0 or _punctuated(tokens[at - 1], tokens[at])


def _edge_after(tokens: Sequence[Mapping[str, Any]], at: int) -> bool:
    return at == len(tokens) - 1 or _punctuated(tokens[at], tokens[at + 1])


def _keeps(rule: Rule, tokens: Sequence[Mapping[str, Any]], at: int, code: str) -> bool:
    """Whether the token at `at`, and its neighbours, keep a part's `Rule`."""
    token = tokens[at]
    after = tokens[at + 1] if at + 1 < len(tokens) else None
    before = tokens[at - 1] if at else None
    if rule.is_not and _one_of(token, rule.is_not, code):
        return False
    if rule.then and (after is None or not _one_of(after, rule.then, code)):
        return False
    if rule.then_not and after is not None and _one_of(after, rule.then_not, code):
        return False
    if rule.after_not and before is not None and _one_of(before, rule.after_not, code):
        return False
    if rule.noun:
        nouns = [
            t for t in tokens[at + 1 :] if str(t.get("pos") or "") in ("NOUN", "PRON", "PROPN")
        ]
        if not nouns or not _one_of(nouns[0], rule.noun, code):
            return False
    if rule.starts == 2 and at != 0:
        return False
    if rule.starts == 1 and not (
        _edge_before(tokens, at)
        or (before is not None and str(before.get("pos") or "") in ("CCONJ", "SCONJ"))
        or (before is not None and bool(set(_read_as(before, code)) & RELATIVES))
    ):
        return False
    return True


#: The person a French object pronoun says, for a reflexive `se` (`_persons_agree`).
PERSONS = {"me": "1", "nous": "1", "te": "2", "vous": "2"}


def _persons_agree(unit: Unit, tokens: Sequence[Mapping[str, Any]], placed: Sequence[int]) -> bool:
    """A list's `se` said me, te, nous or vous is reflexive only where its verb is in
    that person (je me mis, not un frisson me passa); a verb with no person, an
    infinitive, says nothing against it."""
    for n, part in enumerate(unit.parts[:-1]):
        if part != "se":
            continue
        person = PERSONS.get(fold(str(tokens[placed[n]].get("surface") or "")))
        if person is None:
            continue
        feats = dict(
            one.split("=", 1)
            for one in str(tokens[placed[n + 1]].get("feats") or "").split("|")
            if "=" in one
        )
        if feats.get("Person") and feats["Person"] != person:
            return False
    return True


def _expletive(tokens: Sequence[Mapping[str, Any]], placed: Sequence[int]) -> bool:
    """Whether a ne is expletive, not a negation's: the verb after it is in the
    subjunctive (avant qu'il ne parte, je crains qu'il ne vienne)."""
    for where in range(placed[0] + 1, placed[-1]):
        if "Mood=Sub" in str(tokens[where].get("feats") or "").split("|"):
            return True
    return False


def _punctuated(before: Mapping[str, Any], after: Mapping[str, Any]) -> bool:
    """Whether more than a space, a hyphen or an apostrophe stands between two tokens:
    punctuation, which the annotator does not keep as a token."""
    return int(after.get("start") or 0) - int(before.get("end") or 0) > GAP


def _found_words(
    tokens: Sequence[Mapping[str, Any]], code: str
) -> list[tuple[tuple[int, ...], Unit]]:
    """French and Russian units, chosen across the whole segment, the longest first,
    and of two as long the one with no gap, then the closest, then the earliest; a
    token is in one unit at most. So coup de soleil wins over de coup, не только… но и
    over не только, and parce que keeps its que from ne… que."""
    table = _by_first(code)
    starts: list[tuple[int, Unit]] = []
    for at in range(len(tokens)):
        starting: list[Unit] = []
        for first in _read_as(tokens[at], code):
            starting.extend(table.get(first, ()))
        if code == "fr" and REFLEXIVE & set(_read_as(tokens[at], code)):
            starting.extend(table.get("se", ()))
        starts.extend((at, unit) for unit in dict.fromkeys(starting))
    ranked: list[tuple[tuple[int, int, int, int], int, Unit]] = []
    for at, unit in starts:
        placed = _place(unit, tokens, at, set(), code)
        if placed is None:
            continue
        # The longest; of two as long a correlative (чем… тем keeps its тем from тем
        # более), then one with no gap (parce que keeps its que from ne… que); then the
        # closest (ne mange plus que: ne… plus); then the first.
        gapped = 0 if any(unit.commas) else 2 if any(unit.gaps) else 1
        ranked.append(((-len(unit.parts), gapped, placed[-1] - placed[0], at), at, unit))
    ranked.sort(key=lambda hit: hit[0])
    out: list[tuple[tuple[int, ...], Unit]] = []
    taken: set[int] = set()
    for _, at, unit in ranked:
        if at in taken:
            continue
        # Placed again around what is taken, so a gap may reach past it to another word.
        placed = _place(unit, tokens, at, taken, code)
        if placed is None or taken & set(placed):
            continue
        out.append((placed, unit))
        taken.update(placed)
    out.sort(key=lambda hit: hit[0][0])
    return out


def from_phrases(texts: Iterable[str], language: str = "he") -> frozenset[str]:
    """The units a reader's kept phrases are: each phrase's words against each unit's
    written forms, in Hebrew a prefix on the first word allowed."""
    code = base(language)
    wanted: dict[tuple[str, ...], set[str]] = {}
    for unit in load(language=code):
        for form in unit.written:
            wanted.setdefault(form, set()).add(unit.key)
    out: set[str] = set()
    if code != "he":
        for text in texts:
            said = tuple(piece for word in words(text) for piece in word.split("-") if piece)
            out.update(wanted.get(said, ()))
        return frozenset(out)
    for text in texts:
        words_ = tuple(plain(text).split())
        if not words_:
            continue
        out.update(wanted.get(words_, ()))
        first = words_[0]
        for cut in range(1, min(3, len(first) - 1) + 1):
            if not set(first[:cut]) <= PREFIX_LETTERS:
                break
            out.update(wanted.get((first[cut:], *words_[1:]), ()))
    return frozenset(out)


def with_phrases(
    marked: Mapping[str, int], phrases: Iterable[str], language: str = "he"
) -> dict[str, int]:
    """A reader's marks with each unit they kept as a phrase and marked known, known
    under its key (design.md §12, "An idiom is one word to know")."""
    out = dict(marked)
    for key in from_phrases(phrases, language):
        out.setdefault(key, KNOWN)
    return out
