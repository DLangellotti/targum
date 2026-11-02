"""What the word card knows of a word's root beyond a verb's: a Hebrew noun's or
adjective's root and pattern, whether a word is borrowed, and a Russian word's root, its
other spellings and its prefixes (targum-internal#593 and #596, epic #597).

Read from targum's own root lexicons (`root_lexicon`, `scripts/build_roots.py`): the
agreed rows of the two-model run, one file a language, private like the catalogue. This
module is the open half that reads them; the files are never in the repository or the
wheel. A machine without one shows what it showed before.

**Where the file is.** A path named in `TARGUM_ROOTS_HE` / `TARGUM_ROOTS_RU` is the path,
found or not; otherwise `~/.targum/roots-<language>.json`, then
`/etc/targum/roots-<language>.json`, where `deploy/deploy.sh` puts the laptop's copy.

Page-build and count time only, like `verb_roots`. Nothing here renames an annotator,
moves `SCHEMA_VERSION` or runs a model, and a page carries only the rows of the words on
it.

**The guards.**

- A verb's root stays `verb_roots.root_for`'s. The lexicon gives a root only to a noun or
  an adjective, and only one `verb_roots.denied` lets through: a root denied for a lemma
  is never shown, wherever it came from.
- A root joins a family (`family_root`) only where the lexicon grades the word
  transparent: חשבון has ח־ש־ב on its card and is not counted under "think".
- One root string with unrelated meanings (ע־ר־ב evening, guarantee; лет fly, year) is
  one key, and `same_sense` keeps a family to the meaning of the word asked about.
"""

from __future__ import annotations

import json
import os
import re
import threading
import unicodedata
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .hebrew import ENDINGS, FINALS

LANGUAGES = ("he", "ru")
ENV = {"he": "TARGUM_ROOTS_HE", "ru": "TARGUM_ROOTS_RU"}

#: The versions of the lexicon this module reads. Another is refused, never misread.
VERSIONS = {"he": "roots/1", "ru": "ru-roots/1"}

#: The parts of speech a Hebrew root is shown on from the lexicon. A verb's comes from
#: the annotation and the CC0 table (`verb_roots`); a name or a number has none.
HEBREW_KINDS = frozenset({"NOUN", "ADJ"})
#: The parts of speech a Russian word's root is shown on: the content words.
RUSSIAN_KINDS = frozenset({"NOUN", "ADJ", "VERB", "ADV"})

#: The seven binyanim as the lexicon names them. A noun or adjective whose pattern came
#: back as one is a participle, and its pattern is not a mishkal; it is left out.
BINYANIM = frozenset({"פעל", "נפעל", "פיעל", "פועל", "הפעיל", "הופעל", "התפעל"})


def places(language: str) -> tuple[Path, ...]:
    name = f"roots-{language}.json"
    return (Path.home() / ".targum" / name, Path("/etc/targum") / name)


def path(language: str) -> Path | None:
    """Where this language's lexicon is read from, or None where there is none."""
    language = _code(language)
    if language not in ENV:
        return None
    named = os.environ.get(ENV[language], "").strip()
    if named:
        return Path(named) if Path(named).is_file() else None
    for place in places(language):
        if place.is_file():
            return place
    return None


def _code(language: str) -> str:
    return (language or "").split("-")[0].lower()


# --- Spellings ---------------------------------------------------------------------------


def hebrew_letters(text: str | None) -> str:
    """The Hebrew letters alone, points and maqafs dropped, final forms folded."""
    bare = "".join(
        ch for ch in unicodedata.normalize("NFD", text or "") if not unicodedata.combining(ch)
    )
    return "".join(ch for ch in bare if "א" <= ch <= "ת").translate(FINALS)


def as_drawn(root: str | None) -> str:
    """A lexicon root (כ־ת־ב, ז־מ־נ) in the shape the annotation and the CC0 table give a
    verb's (כתב, זמן): its letters, the last one in its final form. The card joins them
    with maqafs again; the family counts compare this shape."""
    found = hebrew_letters(root)
    return found[:-1] + found[-1:].translate(ENDINGS) if found else ""


def fold_ru(text: str | None) -> str:
    """A Russian spelling made comparable: lower case, ё as е, stress marks dropped."""
    bare = unicodedata.normalize("NFD", text or "").replace("́", "").replace("̀", "")
    return unicodedata.normalize("NFC", bare).lower().replace("ё", "е").strip()


def _sense_words(sense: str | None) -> frozenset[str]:
    """The words of a sense ("show, tell" → show, tell), "to" left off a verb."""
    out = set()
    for part in re.split(r"[,;/]", (sense or "").lower()):
        word = part.strip()
        if word.startswith("to "):
            word = word[3:].strip()
        if word:
            out.add(word)
    return frozenset(out)


def _finder(parent: dict[str, str]) -> Callable[[str], str]:
    """The union-find lookup over one root's senses."""

    def find(sense: str) -> str:
        while parent[sense] != sense:
            parent[sense] = parent[parent[sense]]
            sense = parent[sense]
        return sense

    return find


def _clusters(senses: Mapping[str, Counter[str]]) -> dict[tuple[str, str], int]:
    """For each (root, sense) the lexicon gives, which of the root's meanings it is.

    Senses of one root that share a word are one meaning ("show", "show, tell", "tell");
    the rest are others (лет: "fly", "year"). Numbered from 1 by how many words carry
    them, so the commonest meaning is 1.
    """
    out: dict[tuple[str, str], int] = {}
    for root, counted in senses.items():
        parent = {sense: sense for sense in counted}
        find = _finder(parent)
        by_word: dict[str, str] = {}
        for sense in counted:
            for word in _sense_words(sense):
                if word in by_word:
                    parent[find(sense)] = find(by_word[word])
                else:
                    by_word[word] = sense
        groups: dict[str, list[str]] = {}
        for sense in counted:
            groups.setdefault(find(sense), []).append(sense)
        ranked = sorted(
            groups.values(), key=lambda group: (-sum(counted[s] for s in group), min(group))
        )
        for number, group in enumerate(ranked, 1):
            for sense in group:
                out[(root, sense)] = number
    return out


# --- The lexicons ------------------------------------------------------------------------


@dataclass(frozen=True)
class HebrewRow:
    """One Hebrew lemma's agreed row, as the card and the counts use it."""

    root: str
    """In the annotation's shape (`as_drawn`): כתב, זמן. "" where the word has none."""
    pattern: str
    """A noun's or adjective's mishkal as a pointed template (מִקְטָל), a suffix (־ות),
    or a verb's binyan. "" where the two answers disagreed or there is none."""
    meaning: str
    borrowed: bool
    transparent: bool
    sense: int
    """Which of its root's meanings this word carries (`_clusters`), 0 where unknown."""


@dataclass(frozen=True)
class RussianMorph:
    morph: str
    variants: tuple[str, ...]
    sense: str
    number: int
    """Which of the morph's meanings this is (`_clusters`), 0 where unknown."""


@dataclass(frozen=True)
class RussianRow:
    roots: tuple[RussianMorph, ...]
    prefixes: tuple[str, ...]
    suffixes: tuple[str, ...]
    transparent: bool
    borrowed: bool


@dataclass(frozen=True)
class Lexicon:
    language: str
    version: str
    hebrew: Mapping[str, HebrewRow]
    russian: Mapping[str, RussianRow]


_KEPT: dict[str, tuple[tuple[str, int, int], Lexicon | None]] = {}
_LOCK = threading.Lock()


def stamp(language: str) -> tuple[int, int]:
    """What the lexicon was read from, for a cache built on it: (mtime, size), or zeros
    where there is none."""
    found = path(language)
    if found is None:
        return (0, 0)
    try:
        held = found.stat()
    except OSError:
        return (0, 0)
    return (held.st_mtime_ns, held.st_size)


def lexicon(language: str) -> Lexicon | None:
    """This language's lexicon, read once while its file is unchanged, or None."""
    language = _code(language)
    found = path(language)
    if found is None:
        return None
    try:
        held = found.stat()
    except OSError:
        return None
    key = (str(found), held.st_mtime_ns, held.st_size)
    with _LOCK:
        kept = _KEPT.get(language)
        if kept is not None and kept[0] == key:
            return kept[1]
        try:
            body = json.loads(found.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            body = None
        read = from_body(body, language) if isinstance(body, dict) else None
        _KEPT[language] = (key, read)
        return read


def from_body(body: Mapping[str, Any], language: str) -> Lexicon | None:
    """A lexicon file's body, read, or None for one of another language or version."""
    language = _code(language)
    version = str(body.get("version") or "")
    if body.get("language") != language or not version.startswith(VERSIONS.get(language, "?")):
        return None
    rows = body.get("lemmas")
    if not isinstance(rows, dict):
        return None
    if language == "he":
        return Lexicon(language, version, _hebrew(rows), {})
    return Lexicon(language, version, {}, _russian(rows))


def _hebrew(rows: Mapping[str, Any]) -> dict[str, HebrewRow]:
    senses: dict[str, Counter[str]] = {}
    for row in rows.values():
        if isinstance(row, dict) and row.get("root") and row.get("meaning"):
            root = as_drawn(str(row["root"]))
            senses.setdefault(root, Counter())[str(row["meaning"])] += 1
    clusters = _clusters(senses)
    out: dict[str, HebrewRow] = {}
    for lemma, row in rows.items():
        if not isinstance(row, dict):
            continue
        root = as_drawn(str(row.get("root") or ""))
        if root and not 2 <= len(root) <= 4:
            root = ""
        meaning = str(row.get("meaning") or "") if root else ""
        out[unicodedata.normalize("NFC", str(lemma))] = HebrewRow(
            root=root,
            pattern=unicodedata.normalize("NFC", str(row.get("pattern") or "")),
            meaning=meaning,
            borrowed=row.get("borrowed") is True,
            transparent=bool(root) and row.get("transparent") == "yes",
            sense=clusters.get((root, meaning), 0) if meaning else 0,
        )
    return out


def _strings(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(str(item).strip() for item in value if isinstance(item, str) and item.strip())


def _russian(rows: Mapping[str, Any]) -> dict[str, RussianRow]:
    senses: dict[str, Counter[str]] = {}
    for row in rows.values():
        for morph in (row.get("roots") or []) if isinstance(row, dict) else []:
            if isinstance(morph, dict) and morph.get("morph") and morph.get("sense"):
                senses.setdefault(fold_ru(morph["morph"]), Counter())[str(morph["sense"])] += 1
    clusters = _clusters(senses)
    out: dict[str, RussianRow] = {}
    for lemma, row in rows.items():
        if not isinstance(row, dict):
            continue
        roots = []
        for morph in row.get("roots") or []:
            if not isinstance(morph, dict) or not morph.get("morph"):
                continue
            spelled = fold_ru(morph["morph"])
            sense = str(morph.get("sense") or "")
            roots.append(
                RussianMorph(
                    morph=spelled,
                    variants=tuple(
                        dict.fromkeys(
                            v for v in map(fold_ru, _strings(morph.get("variants"))) if v != spelled
                        )
                    ),
                    sense=sense,
                    number=clusters.get((spelled, sense), 0) if sense else 0,
                )
            )
        out[fold_ru(str(lemma))] = RussianRow(
            roots=tuple(roots),
            prefixes=_strings(row.get("prefixes")),
            suffixes=_strings(row.get("suffixes")),
            transparent=row.get("transparency") == "transparent",
            borrowed=row.get("borrowed") is True,
        )
    return out


def hebrew_row(lemma: str) -> HebrewRow | None:
    found = lexicon("he")
    return found.hebrew.get(unicodedata.normalize("NFC", lemma or "")) if found else None


def russian_row(lemma: str) -> RussianRow | None:
    found = lexicon("ru")
    return found.russian.get(fold_ru(lemma)) if found else None


# --- What a page and a count are given ----------------------------------------------------


def noun_root(lemma: str, pos: str | None) -> str:
    """A Hebrew noun's or adjective's root from the lexicon, in the annotation's shape,
    or "" — never one `verb_roots.denied` refuses for this lemma."""
    from .verb_roots import denied

    if (pos or "") not in HEBREW_KINDS:
        return ""
    row = hebrew_row(lemma)
    if row is None or not row.root or denied(lemma, row.root):
        return ""
    return row.root


def hebrew_shape(lemma: str, pos: str | None, page_root: str) -> list[Any] | int:
    """What a Hebrew word's page row carries of the lexicon: [root, pattern, meaning,
    borrowed, transparent], or 0 for nothing to say.

    `page_root` is the root the page already draws (`verb_roots.root_for`). A noun or
    adjective with none gets the lexicon's (`noun_root`) and its mishkal; a verb keeps its
    own root and binyan, and is given only the root's meaning, and only where the lexicon
    names the same root. Borrowed is said only of a word with no root to show.
    """
    row = hebrew_row(lemma)
    if row is None:
        return 0
    kind = pos or ""
    if kind in HEBREW_KINDS:
        root = page_root or noun_root(lemma, kind)
        if root and hebrew_letters(root) != hebrew_letters(row.root):
            # The annotation gave this noun a root of its own; the lexicon's meaning and
            # pattern are of another root and are not said beside it.
            return [root, "", "", 0, 0]
        if not root:
            # A pattern is said of a root; with none, the one thing left is a loanword.
            return ["", "", "", 1, 0] if row.borrowed else 0
        pattern = "" if row.pattern in BINYANIM else row.pattern
        return [root, pattern, row.meaning, 0, 1 if row.transparent else 0]
    if kind == "VERB" and page_root and row.meaning:
        if hebrew_letters(page_root) == hebrew_letters(row.root):
            return ["", "", row.meaning, 0, 0]
    return 0


def russian_shape(lemma: str, pos: str | None) -> list[Any] | int:
    """What a Russian word's page row carries of the lexicon: [[[morph, [variants],
    sense], ...], [prefixes], borrowed, transparent], or 0 for nothing to say. The
    morph is also the key the family line asks by."""
    if (pos or "") not in RUSSIAN_KINDS:
        return 0
    row = russian_row(lemma)
    if row is None or not row.roots:
        return 0
    return [
        [[m.morph, list(m.variants), m.sense] for m in row.roots],
        list(row.prefixes),
        1 if row.borrowed else 0,
        1 if row.transparent else 0,
    ]


def family_root(lemma: str, pos: str | None, page_root: str, language: str) -> str:
    """The root a word is counted under in "N words from this root met": the page's own
    root for a verb (`verb_roots.root_for`, as before), the lexicon's for a Hebrew noun or
    adjective graded transparent, and for a Russian content word graded transparent its
    root morphs, several joined by a space (пароход: пар ход). "" for none."""
    language = _code(language)
    if language == "he":
        if page_root:
            return page_root
        root = noun_root(lemma, pos)
        if not root:
            return ""
        row = hebrew_row(lemma)
        return root if row is not None and row.transparent else ""
    if language == "ru":
        if (pos or "") not in RUSSIAN_KINDS:
            return ""
        found = russian_row(lemma)
        if found is None or not found.transparent:
            return ""
        return " ".join(dict.fromkeys(m.morph for m in found.roots))
    return page_root


def keys(counted: str) -> Sequence[str]:
    """The roots one counted entry names (`family_root`)."""
    return counted.split(" ") if counted else ()


def same_sense(language: str, asked: str, other: str, root: str) -> bool:
    """Whether two words of one root string carry the same meaning of it, so a family
    asked from ערבות (guarantee) leaves out ערב (evening). Where either word's meaning
    is not in the lexicon, nothing is known against it, and it stays."""
    language = _code(language)
    if asked == other:
        return True
    first, second = _sense(language, asked, root), _sense(language, other, root)
    return not first or not second or first == second


def sense_of(language: str, lemma: str, root: str) -> int:
    """Which of `root`'s meanings `lemma` carries, numbered as `same_sense` compares
    them, or 0 where the lexicon does not say: what keeps ע־ר־ב (evening) and ע־ר־ב
    (guarantee) two roots in "words from N roots"."""
    return _sense(_code(language), lemma, root)


def _sense(language: str, lemma: str, root: str) -> int:
    if language == "he":
        row = hebrew_row(lemma)
        if row is None or hebrew_letters(row.root) != hebrew_letters(root):
            return 0
        return row.sense
    if language == "ru":
        found = russian_row(lemma)
        if found is None:
            return 0
        wanted = fold_ru(root)
        return next((m.number for m in found.roots if m.morph == wanted), 0)
    return 0
