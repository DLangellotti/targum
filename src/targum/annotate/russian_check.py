"""A Russian word's lemma and grammar checked against OpenRussian, at page-build and count
time (targum-internal#708, #709, #710).

ling-ru read 814 Russian tokens by hand on 2026-11-13 and ran detectors over the laptop's
245,368. Three kinds of error stand on the card whichever annotator read the text, and
OpenRussian's tables can witness each one:

- **A short form or a comparative given a case.** "я была слишком строга" said "adjective ·
  f · nominative", "подписаны правительством" "participle · … · nominative", and "гора
  выше других" was высокий in the nominative. A short form takes no case. Where the table
  has the word only as a short form or the comparative of its adjective, the case goes
  and the card says which; a participle with a short ending loses its case the same way.
- **The future read as the present, and imperatives missed.** будет and будешь said
  "present"; a perfective's present-future (промыслишь) said "present · perfective"; and
  "войди в купель" was a future first person, "Бери его" and "Пей, батюшка" were names.
  будет is a closed list; a perfective's present-future cell is its future; and a word the
  table has only as some verb's imperative is that imperative, whatever it was tagged. A
  form the table files under the lemma's aspect partner and not the lemma (даёт under
  дать) is the partner's.
- **An invented or wrong lemma.** Stanza gave пирах as пира, "в уху" as ухо and плакать-то
  as itself. Where the lemma is not the table's word for the form — unknown to it, or the
  form not in its paradigm, or not in the cell the tagger named — and the form is in
  exactly one other row of the same kind, that row's word is the lemma. A particle on a
  hyphen (-то, -ка, -де, -с) is not part of the lemma. A lower-case word tagged as a name,
  and a capitalised one at the start of a sentence that the text uses lower-case
  elsewhere, is the table's common word.

Nothing here renames an annotator, moves `SCHEMA_VERSION` or runs a model: the annotation
on disk keeps what the annotator said, and the page (`lemma_check.mended`) and the counts
(`occurrences.count_text`) read the same mended rows. A machine without the tables builds
exactly as before. Where the table is unsure — a form of two words, a lemma it files
twice — nothing changes: a gap on the card is better than a confident wrong word.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import TYPE_CHECKING, Any

from .openrussian import Lexicon, fold

if TYPE_CHECKING:
    from ..models import Annotation

#: The version of what this module answers, carried by every count that reads it
#: (`occurrences.VERSION`). 1: short forms, the future, imperatives and witnessed lemmas
#: (targum-internal#708, #709, #710).
VERSION = 1

#: The tables' kinds by the part of speech whose lemma they can witness.
_KIND = {"NOUN": "noun", "VERB": "verb", "AUX": "verb", "ADJ": "adjective"}
_UPOS = {"noun": "NOUN", "verb": "VERB", "adjective": "ADJ"}

_SHORT = {
    "short_m": ("Masc", "Sing"),
    "short_f": ("Fem", "Sing"),
    "short_n": ("Neut", "Sing"),
    "short_pl": ("", "Plur"),
}
_COMPARATIVE = "comparative"
_IMPERATIVE = {"imperative_sg": "Sing", "imperative_pl": "Plur"}
_PRESFUT = re.compile(r"^presfut_(sg|pl)([123])$")
_GENDER = {"m": "Masc", "f": "Fem", "n": "Neut"}
_CASES = {"Nom": "nom", "Gen": "gen", "Dat": "dat", "Acc": "acc", "Ins": "inst", "Loc": "prep"}
_NUMBERS = {"Sing": "sg", "Plur": "pl"}

#: быть's own future, which a tagger reads as the present because быть has no other.
_BUD = frozenset({"буду", "будешь", "будет", "будем", "будете", "будут"})

#: A particle on a hyphen, kept off the lemma: плакать-то, дай-ка, да-с, мол-де. Not
#: -таки, which is part of всё-таки; and not after a pronoun that is a word with it
#: (кто-то, что-то, как-то).
_HYPHEN = re.compile(r"^(?P<word>.+)-(?P<particle>то|ка|де|с)$")
_HYPHEN_WORDS = re.compile(
    r"^(кто|что|где|как|какой|какая|какое|какие|какого|каком|каким|какую|чей|чья|чьё|чье|"
    r"чьи|куда|когда|почему|зачем|сколько|кое|откуда|отчего|так|то|вот|ну|уж|тут|там)$"
)

#: A full adjectival ending, which a short form never has.
_FULL = re.compile(
    r"(ый|ий|ой|ая|яя|ое|ее|ые|ие|ого|его|ому|ему|ым|им|ом|ем|ую|юю|ых|их|ыми|ими|ою|ею)$"
)
#: A short passive participle's ending: сказан, сказана, сказано, сказаны, взят, взята.
_SHORT_PARTICIPLE = re.compile(r"(?:[аяеё]нн?|т)(?P<end>[аоы]?)$")
_SHORT_AGREEMENT = {"": ("Masc", "Sing"), "а": ("Fem", "Sing"), "о": ("Neut", "Sing")}

_LETTER = re.compile(r"[а-яёА-ЯЁa-zA-Z]")
_VOWEL = re.compile(r"[аеёиоуыэюяАЕЁИОУЫЭЮЯ]")

#: What stands between two words where the second starts a sentence: an end stop or a
#: line break. Direct speech opens on a colon, a dash or a quotation mark too, which is
#: where an imperative stands (сказал: «Пой»), but so does a title («Бумага»), so only
#: an imperative is read there.
_SENTENCE = re.compile(r"[.!?…\n]")
_SPEECH = re.compile(r"[.!?…\n:«\"“„—–]")
#: What stands between two words inside one sentence and says nothing of a name: spaces
#: and a comma. A capitalised word after one is a name the text uses as a name.
_INSIDE = re.compile(r"^[\s,]*$")

#: The small words of a foreign name, written lower case and tagged as names, that the
#: tables know as common words: фон Рихтер is not "background".
_NAME_PARTICLES = frozenset(
    "фон ван дер де ди да дю ла ле дель делла оглы ибн бен бин аль эль сан сэр мисс "
    "мистер миссис мадам мсье месье фрау герр синьор синьора дон донья".split()
)

#: Forms a table files under another word than the dictionary does: лет is год's.
_SUPPLETIVE = {"лет": "год"}


def applies(language: str) -> bool:
    """Whether an annotation in `language` is checked here: any Russian, whichever
    annotator read it."""
    return language.split("-")[0].lower() == "ru"


def lexicon() -> Lexicon | None:
    from . import openrussian

    return openrussian.lexicon()


def feats_of(feats: str | None) -> dict[str, str]:
    """`UPOS=ADJ|Case=Nom` as an ordered map."""
    out: dict[str, str] = {}
    for part in (feats or "").split("|"):
        key, sep, value = part.partition("=")
        if sep and key:
            out[key] = value
    return out


def _written(values: Mapping[str, str]) -> str:
    return "|".join(f"{key}={value}" for key, value in values.items())


class _Reader:
    """One lexicon, asked about one text's words."""

    def __init__(self, table: Lexicon) -> None:
        self.table = table

    def cells(self, form: str, kind: str, lemma: str | None = None) -> set[tuple[str, str]]:
        """The (lemma, column) of every row of `kind` with `form` in it, or of `lemma`'s
        rows alone."""
        want = fold(lemma) if lemma is not None else None
        return {
            (found, column)
            for found, row_kind, column in self.table.whose(form)
            if row_kind == kind and (want is None or fold(found) == want)
        }

    def known(self, lemma: str, kind: str) -> bool:
        return any(
            row_kind == kind and column == "bare" and fold(found) == fold(lemma)
            for found, row_kind, column in self.table.whose(lemma)
        )

    def rows(self, lemma: str, kind: str) -> list[Any]:
        return self.table.rows(lemma, kind) or self.table.rows(
            _yo(self.table, lemma, kind) or lemma, kind
        )

    def aspect(self, lemma: str) -> str:
        found = {row.aspect for row in self.rows(lemma, "verb")}
        return found.pop() if len(found) == 1 else ""

    def gender(self, lemma: str) -> str:
        found = {row.gender for row in self.rows(lemma, "noun")}
        return _GENDER.get(found.pop(), "") if len(found) == 1 else ""


def _yo(table: Lexicon, lemma: str, kind: str) -> str:
    """The table's own spelling of a lemma written without its ё, where there is one."""
    found = {
        name
        for name, row_kind, column in table.whose(lemma)
        if row_kind == kind and column == "bare"
    }
    return found.pop() if len(found) == 1 else ""


def _gap(run: list[Any], at: int, text: str | None) -> str | None:
    """What stands between the word at `at` and the one before it in the segment's text,
    or None where the text is not given or the offsets do not fit it."""
    if text is None or at == 0 or not isinstance(run[at - 1], dict):
        return None
    start, end = int(run[at - 1].get("end") or 0), int(run[at].get("start") or 0)
    if not 0 <= start <= end <= len(text):
        return None
    return text[start:end]


def _initial(run: list[Any], at: int, text: str | None, opening: re.Pattern[str]) -> bool:
    """Whether the word at `at` opens a sentence (`_SENTENCE`) or a line of speech
    (`_SPEECH`): the segment's first, or the first after one. Without the segment's text
    only the segment's first word is known to."""
    if at == 0:
        return True
    gap = _gap(run, at, text)
    return gap is not None and bool(opening.search(gap))


def _named(tokens: Mapping[str, list[Any]], texts: Mapping[str, str]) -> set[str]:
    """The names a text uses as names: a capitalised word tagged PROPN inside a sentence,
    by its lemma and its form."""
    out: set[str] = set()
    for segment_id, run in tokens.items():
        text = texts.get(segment_id)
        for at, row in enumerate(run):
            if not isinstance(row, dict) or row.get("pos") != "PROPN" or at == 0:
                continue
            surface = str(row.get("surface") or "")
            gap = _gap(run, at, text)
            inside = (
                _INSIDE.match(gap)
                if gap is not None
                else (
                    int(row.get("start") or 0) - int(run[at - 1].get("end") or 0) == 1
                    if isinstance(run[at - 1], dict)
                    else False
                )
            )
            if surface[:1].isupper() and inside:
                out.add(fold(surface))
                out.add(fold(str(row.get("lemma") or "")))
    return out


def _common(tokens: Mapping[str, list[Any]]) -> set[str]:
    """The lemmas a text writes lower case as a word that is not a name."""
    return {
        fold(str(row.get("lemma") or ""))
        for run in tokens.values()
        for row in run
        if isinstance(row, dict)
        and row.get("pos") not in (None, "PROPN")
        and str(row.get("surface") or "")[:1].islower()
    }


def mend_tokens(
    tokens: Mapping[str, list[Any]], texts: Mapping[str, str] | None = None
) -> dict[str, list[Any]]:
    """Every segment's tokens as `annotation.json` stores them, checked; each row the same
    dict where nothing changes, and the same lists where no row of a segment does.
    `texts` is each segment's text by its id, which says where a sentence starts."""
    table = lexicon()
    if table is None:
        return dict(tokens)
    return _mend_tokens(tokens, table, texts or {})


def texts_of(segmented: Any) -> dict[str, str]:
    """Each segment's text by its id, from a `SegmentedDocument`, or nothing."""
    if segmented is None:
        return {}
    return {segment.id: segment.text for segment in segmented.segments}


def _mend_tokens(
    tokens: Mapping[str, list[Any]], table: Lexicon, texts: Mapping[str, str]
) -> dict[str, list[Any]]:
    reader = _Reader(table)
    names = _named(tokens, texts)
    common = _common(tokens)
    out: dict[str, list[Any]] = {}
    for segment_id, run in tokens.items():
        text = texts.get(segment_id)
        mended = [
            mend_row(
                row,
                reader,
                initial=_initial(run, at, text, _SENTENCE),
                speech=_initial(run, at, text, _SPEECH),
                names=names,
                common=common,
            )
            if isinstance(row, dict)
            else row
            for at, row in enumerate(run)
        ]
        same = all(new is old for new, old in zip(mended, run, strict=True))
        out[segment_id] = run if same else mended
    return out


def mended(annotation: Annotation, segmented: Any = None) -> Annotation:
    """The annotation with every Russian word checked; the same object where nothing
    changes, where it is not Russian, and where this machine has no tables. `segmented`
    is the text's segments, which say where a sentence starts."""
    if not applies(annotation.language):
        return annotation
    table = lexicon()
    if table is None:
        return annotation
    from ..models import Token

    rows = {
        segment_id: [token.model_dump() for token in run]
        for segment_id, run in annotation.tokens.items()
    }
    fixed = _mend_tokens(rows, table, texts_of(segmented))
    changed = False
    tokens: dict[str, list[Token]] = {}
    for segment_id, run in annotation.tokens.items():
        new_rows = fixed[segment_id]
        if new_rows is rows[segment_id]:
            tokens[segment_id] = run
            continue
        out = []
        for token, old, new in zip(run, rows[segment_id], new_rows, strict=True):
            if new is old:
                out.append(token)
            else:
                changed = True
                out.append(Token.model_validate(new))
        tokens[segment_id] = out
    if not changed:
        return annotation
    return annotation.model_copy(update={"tokens": tokens})


def mend_row(
    row: dict[str, Any],
    reader: _Reader,
    *,
    initial: bool = False,
    speech: bool = False,
    names: Iterable[str] = (),
    common: Iterable[str] = (),
) -> dict[str, Any]:
    """One stored token, checked. The same dict where nothing changes."""
    surface = str(row.get("surface") or "")
    lemma = str(row.get("lemma") or "")
    pos = str(row.get("pos") or "")
    feats = feats_of(row.get("feats"))
    if not surface or not _LETTER.search(surface):
        return row
    was = (lemma, pos, dict(feats))
    word = surface

    # A particle on a hyphen is not part of the word's lemma (плакать-то, дай-ка).
    hyphen = _HYPHEN.match(lemma.lower())
    said = _HYPHEN.match(surface.lower())
    if hyphen and said and not _HYPHEN_WORDS.match(hyphen["word"]):
        lemma = lemma[: len(hyphen["word"])]
        word = surface[: len(said["word"])]

    names = set(names)
    lowered = surface == surface.lower()
    is_name = (
        fold(surface) in names
        or fold(lemma) in names
        or fold(word) in _NAME_PARTICLES
        or (pos == "PROPN" and not lowered and not (initial or speech))
    )

    # An imperative, whatever it was tagged as: a form the table has as some verb's
    # imperative and as nothing else (войди, Бери, Пей). Not a word tagged as one the
    # table has no forms for (нашей is наш's, not нашить's) or an interjection
    # (прощай); and a name only where it opens a line and the text never uses it as one.
    imperative = _imperative(word, lemma, reader) if _MAY_BE_IMPERATIVE(pos, word, lemma) else None
    if imperative and feats.get("Mood") != "Imp" and not (pos == "PROPN" and is_name):
        verb, number = imperative
        lemma = verb
        pos = pos if pos in ("VERB", "AUX") else "VERB"
        feats = {"UPOS": pos}
        if aspect := _ASPECT.get(reader.aspect(verb), ""):
            feats["Aspect"] = aspect
        feats |= {"Mood": "Imp", "Number": number, "Person": "2", "VerbForm": "Fin"}

    # A word tagged as a name that the table knows as a common word: lower case, or at the
    # start of a sentence where the text writes the word lower case elsewhere.
    if pos == "PROPN" and not is_name:
        if lowered or (initial and _common_word(word, reader) in set(common)):
            found = _common_word(word, reader, kinds=True)
            if found:
                lemma, pos, feats = _as_common(word, found, feats, reader)
        elif (initial or speech) and _only_small(word, reader):
            # Эка, Ну, Ох opening a line: a small word the table has, of a kind it does
            # not say; a card with no kind on it rather than "noun, proper".
            lemma, pos, feats = word.lower(), "X", {"UPOS": "X"}

    kind = _KIND.get(pos)
    form = feats.get("VerbForm")
    if kind and not (kind == "verb" and form in ("Part", "Conv")):
        better = _witnessed(word, lemma, kind, feats, reader)
        if better and better != lemma:
            lemma = better
            if kind == "noun" and (gender := reader.gender(lemma)):
                feats["Gender"] = gender
            if kind == "verb" and (aspect := _ASPECT.get(reader.aspect(lemma), "")):
                feats["Aspect"] = aspect

    if pos == "ADJ" and "Case" in feats:
        feats, lemma = _short_adjective(word, lemma, feats, reader)
    if pos in ("VERB", "AUX", "ADJ") and form == "Part" and "Case" in feats:
        feats = _short_participle(word, feats)
    if pos in ("VERB", "AUX") and form == "Fin" and feats.get("Tense") == "Past":
        feats = _past_or_participle(word, lemma, feats, reader)
    if pos in ("VERB", "AUX") and feats.get("Mood") != "Imp" and feats.get("Tense") == "Pres":
        lemma, feats = _future(word, lemma, feats, reader)
    if feats.get("Mood") == "Imp" and "Tense" in feats:
        # An imperative has no tense: Будьте was "present" beside it.
        feats = {k: v for k, v in feats.items() if k != "Tense"}

    if (lemma, pos, feats) == was:
        return row
    feats = {"UPOS": pos, **{k: v for k, v in feats.items() if k != "UPOS"}}
    out = row | {"lemma": lemma, "pos": pos, "feats": _written(feats)}
    return out


_ASPECT = {"perfective": "Perf", "imperfective": "Imp"}

#: The parts of speech an imperative may have been tagged as. Not DET, ADJ, PRON or NUM,
#: whose forms the tables do not all spell (нашей, умней), and not INTJ: прощай and
#: пожалуйте are said as interjections.
_IMPERATIVE_TAGS = frozenset({"VERB", "AUX", "NOUN", "PROPN", "ADV", "PART", "X", ""})


#: What an old model reading wrote as a lemma where it shifted a column: the part of
#: speech's name (targum-internal#711). Only "verb" may stand on an imperative.
_POS_NAMES = frozenset(
    "adj adp adv aux cconj det intj noun num part pron propn punct sconj sym x".split()
)


def _MAY_BE_IMPERATIVE(pos: str, word: str, lemma: str = "") -> bool:
    if pos not in _IMPERATIVE_TAGS or lemma.lower() in _POS_NAMES:
        return False
    # A comparative in -ей (веселей, теплей) is an adverb a tagger may call one; пей is
    # too short to be one.
    return not (pos == "ADV" and word.lower().endswith("ей") and len(word) > 4)


def _as_common(
    word: str, found: tuple[str, str], feats: dict[str, str], reader: _Reader
) -> tuple[str, str, dict[str, str]]:
    """A word tagged as a name, as the table's common word: its lemma, part of speech and
    the grammar its cells give it."""
    lemma, kind = found
    rest = {k: v for k, v in feats.items() if k != "UPOS"}
    if kind == "noun":
        return lemma, "NOUN", _fit_noun(word, lemma, {"UPOS": "NOUN", **rest}, reader)
    columns = {column for _, column in reader.cells(word, kind, lemma)}
    if kind == "adjective":
        if columns == {"short_n"} and word.lower().endswith("о"):
            # лукаво, бойко, сердито: the short neuter a manner adverb is spelled as.
            return word.lower(), "ADV", {"UPOS": "ADV"}
        out = {"UPOS": "ADJ"}
        decl = [c.split("_") for c in columns if c.startswith("decl_")]
        agrees = {agree for _, agree, _ in decl}
        if len(agrees) == 1:
            agree = agrees.pop()
            named = {value: key for key, value in _CASES.items()}
            if agree != "pl":
                out["Gender"] = _GENDER.get(agree[0], "")
            out["Number"] = "Plur" if agree == "pl" else "Sing"
            cases = {named[case] for _, _, case in decl if case in named}
            if len(cases) == 1 or feats.get("Case") in cases:
                out["Case"] = cases.pop() if len(cases) == 1 else feats["Case"]
        elif columns and columns <= set(_SHORT):
            out["Case"] = "Nom"
        return lemma, "ADJ", {k: v for k, v in out.items() if v}
    out = {"UPOS": "VERB"}
    if aspect := _ASPECT.get(reader.aspect(lemma), ""):
        out["Aspect"] = aspect
    if columns == {"bare"}:
        return lemma, "VERB", out | {"VerbForm": "Inf"}
    finite = [c for c in columns if _PRESFUT.match(c)]
    past = [c for c in columns if c.startswith("past_")]
    if len(finite) == 1 and not past:
        number, person = _PRESFUT.match(finite[0]).groups()  # type: ignore[union-attr]
        tense = "Fut" if out.get("Aspect") == "Perf" else "Pres"
        return (
            lemma,
            "VERB",
            out
            | {
                "Mood": "Ind",
                "Number": "Sing" if number == "sg" else "Plur",
                "Person": person,
                "Tense": tense,
                "VerbForm": "Fin",
            },
        )
    if len(past) == 1 and not finite:
        agree = past[0].split("_")[1]
        values = (
            {"Number": "Plur"}
            if agree == "pl"
            else {"Gender": _GENDER.get(agree, ""), "Number": "Sing"}
        )
        return lemma, "VERB", out | {"Mood": "Ind", "Tense": "Past", "VerbForm": "Fin"} | values
    return lemma, "VERB", out


def _imperative(word: str, lemma: str, reader: _Reader) -> tuple[str, str] | None:
    """(verb, number) where every row the table has `word` in is a verb's imperative and
    the verb is one, or the lemma is among them."""
    found = reader.table.whose(word)
    if not found or any(kind != "verb" or col not in _IMPERATIVE for _, kind, col in found):
        return None
    verbs = {name for name, _, _ in found}
    numbers = {_IMPERATIVE[col] for _, _, col in found}
    if len(numbers) != 1:
        return None
    mine = {name for name in verbs if fold(name) == fold(lemma)}
    if mine:
        return mine.pop(), numbers.pop()
    if len(verbs) == 1:
        return verbs.pop(), numbers.pop()
    return None


def _common_word(word: str, reader: _Reader, *, kinds: bool = False) -> Any:
    """The one common word — noun, adjective or verb — the table has `word` as a form of:
    its folded lemma, or with `kinds` (lemma, kind). None where it is none or several."""
    found = {
        (name, kind)
        for name, kind, _ in reader.table.whose(word)
        if kind in ("noun", "adjective", "verb")
    }
    if len({fold(name) for name, _ in found}) != 1 or len(found) != 1:
        return None
    name, kind = found.pop()
    return (name, kind) if kinds else fold(name)


def _only_small(word: str, reader: _Reader) -> bool:
    """Whether the table has `word` only as a small word of its own (эка, ну)."""
    found = reader.table.whose(word)
    return bool(found) and all(kind == "other" and column == "bare" for _, kind, column in found)


def _fit_noun(word: str, lemma: str, feats: dict[str, str], reader: _Reader) -> dict[str, str]:
    """A name's tags made a common noun's: the table's gender, and the number and case of
    the cells the form is in where they agree."""
    cells = {column for _, column in reader.cells(word, "noun", lemma) if column != "bare"}
    out = dict(feats)
    if gender := reader.gender(lemma):
        out["Gender"] = gender
    numbers = {column.split("_")[0] for column in cells}
    if len(numbers) == 1:
        out["Number"] = {"sg": "Sing", "pl": "Plur"}[numbers.pop()]
    want = _cell(out)
    if cells and want not in cells:
        cases = {column.split("_")[1] for column in cells}
        named = {value: key for key, value in _CASES.items()}
        if len(cases) == 1 and cases.issubset(named):
            out["Case"] = named[cases.pop()]
        else:
            out.pop("Case", None)
    return out


def _cell(feats: Mapping[str, str]) -> str | None:
    case, number = _CASES.get(feats.get("Case", "")), _NUMBERS.get(feats.get("Number", ""))
    return f"{number}_{case}" if case and number else None


def _paradigm(cells: set[tuple[str, str]], kind: str, feats: Mapping[str, str]) -> set[str]:
    """The columns of `cells` a word of `kind` tagged `feats` could be in."""
    columns = {column for _, column in cells}
    if kind == "verb":
        return {
            c for c in columns if c == "bare" or c.startswith(("past_", "presfut_", "imperative_"))
        }
    if kind == "adjective":
        return {
            c
            for c in columns
            if c == "bare" or c.startswith(("decl_", "short_")) or c == _COMPARATIVE
        }
    return {c for c in columns if c == "bare" or c.startswith(("sg_", "pl_"))}


def _witnessed(
    word: str, lemma: str, kind: str, feats: Mapping[str, str], reader: _Reader
) -> str | None:
    """The table's lemma for `word`, where it differs from `lemma` and the table is sure:
    the lemma is not the table's word for the form — unknown to it, or the form not in
    its paradigm, or (a noun) not in the cell the tagger named while one other noun's
    is — and exactly one row of the kind has the form."""
    lower = word.lower()
    if lower in _SUPPLETIVE or "-" in lower or not _VOWEL.search(lower) or word.isupper():
        # лет is год's; г-жа, млрд, ВИК are abbreviations the tables file as words.
        return None
    if any(kind_ == "other" and column == "bare" for _, kind_, column in reader.table.whose(word)):
        # A small word the table has as one (нет, кругом) is not a form of another.
        return None
    every = reader.cells(word, kind)
    if not every:
        return None
    others = {name for name, _ in every}
    mine = {(name, column) for name, column in every if fold(name) == fold(lemma)}
    if mine and _paradigm(mine, kind, feats):
        if kind != "noun":
            return None
        cell = _cell(feats)
        if cell is None or any(column == cell for _, column in mine):
            return None
        if (
            cell in ("sg_gen", "sg_acc", "sg_prep")
            and any(column == "sg_dat" for _, column in mine)
            and lower.endswith(("у", "ю"))
            and reader.gender(lemma) == "Masc"
        ):
            # A masculine's -у after в, на or a quantity is its second locative or its
            # partitive (в чаду, корму), which the tables file as the dative.
            return None
        # The form is the lemma's, but not in the case and number the tagger named: в уху
        # was ухо (its dative) for уха in the accusative.
        fits = {name for name, column in every if column == cell and fold(name) != fold(lemma)}
        return fits.pop() if len(fits) == 1 else None
    if len({fold(name) for name in others}) != 1 or len(others) != 1:
        return None
    if reader.known(lemma, kind) and (
        mine or not any(row.forms for row in reader.rows(lemma, kind))
    ):
        # The table has the lemma but spells none of its forms (чад): it cannot say
        # чаду is not one of them.
        return None
    if kind == "noun" and not _fits(feats, {column for _, column in every}):
        # The tagger's number, and a case it is not known to swap, say the form is not
        # the other word's: талью tagged accusative is not таль's instrumental.
        return None
    return others.pop()


#: The cases a tagger is known to swap on a noun whose forms fall together.
_SWAPPED = ({"nom", "acc"}, {"gen", "acc"})


def _fits(feats: Mapping[str, str], columns: set[str]) -> bool:
    """Whether a noun tagged `feats` could be in one of `columns`."""
    case, number = _CASES.get(feats.get("Case", "")), _NUMBERS.get(feats.get("Number", ""))
    for column in columns - {"bare"}:
        has_number, _, has_case = column.partition("_")
        if number and has_number != number:
            continue
        if case and has_case != case and {case, has_case} not in _SWAPPED:
            continue
        return True
    return not number and not case


def _short_adjective(
    word: str, lemma: str, feats: dict[str, str], reader: _Reader
) -> tuple[dict[str, str], str]:
    """An adjective tagged with a case that the table has only as a short form or a
    comparative: the case comes off and the card says which."""
    if word.lower().endswith(("ий", "ый", "ой")):
        # больший stands in большой's comparative cell beside больше, and declines.
        return feats, lemma
    cells = reader.cells(word, "adjective", lemma)
    if not cells:
        every = reader.cells(word, "adjective")
        if len({fold(name) for name, _ in every}) != 1:
            return feats, lemma
        cells = every
    columns = {column for _, column in cells}
    if not columns or not columns <= (set(_SHORT) | {_COMPARATIVE}):
        return feats, lemma
    out = {k: v for k, v in feats.items() if k not in ("Case", "Animacy")}
    if columns == {_COMPARATIVE}:
        out = {k: v for k, v in out.items() if k not in ("Gender", "Number")}
        out["Degree"] = "Cmp"
    elif _COMPARATIVE not in columns:
        agreements = {_SHORT[column] for column in columns}
        if len(agreements) == 1:
            gender, number = agreements.pop()
            out.pop("Gender", None)
            if gender:
                out["Gender"] = gender
            out["Number"] = number
        out["Variant"] = "Short"
    else:
        return feats, lemma
    return out, next(iter(cells))[0]


def _short_participle(word: str, feats: dict[str, str]) -> dict[str, str]:
    """A participle with a short ending tagged with a case (подписаны, навьючен): the case
    comes off, and the ending says its gender and number."""
    lower = word.lower()
    found = _SHORT_PARTICIPLE.search(lower)
    if not found or _FULL.search(lower):
        return feats
    out = {k: v for k, v in feats.items() if k not in ("Case", "Animacy")}
    end = found["end"]
    out.pop("Gender", None)
    if end == "ы":
        out["Number"] = "Plur"
    else:
        gender, number = _SHORT_AGREEMENT[end]
        out["Gender"], out["Number"] = gender, number
    # A short passive participle in -н or -т is a past one, whatever the tagger said.
    out["Tense"] = "Past"
    out["Variant"] = "Short"
    return out


def _past_or_participle(
    word: str, lemma: str, feats: dict[str, str], reader: _Reader
) -> dict[str, str]:
    """A finite past that is a short participle (сказано): a Russian past ends in -л or a
    consonant the table spells, never in -но or -то."""
    lower = word.lower()
    if lower.endswith(("л", "ла", "ло", "ли")) or not _SHORT_PARTICIPLE.search(lower):
        return feats
    if not reader.known(lemma, "verb"):
        return feats
    if any(column.startswith("past_") for _, column in reader.cells(word, "verb", lemma)):
        return feats
    out = {k: v for k, v in feats.items() if k not in ("Mood", "Person")}
    out["VerbForm"] = "Part"
    out["Voice"] = "Pass"
    return _short_participle(word, out | {"Case": "Nom"})


def _future(
    word: str, lemma: str, feats: dict[str, str], reader: _Reader
) -> tuple[str, dict[str, str]]:
    """A present that is a future: быть's own (будет), or a perfective's, or a form the
    table files under the lemma's aspect partner instead (даёт is давать's)."""
    if fold(word) in _BUD:
        return "быть", feats | {"Tense": "Fut"}
    cells = {column for _, column in reader.cells(word, "verb", lemma)}
    table = reader.aspect(lemma)
    if any(_PRESFUT.match(column) for column in cells) or not reader.known(lemma, "verb"):
        # A perfective has no present. Where the table and the tagger do not disagree —
        # поводить is two verbs, one of either aspect, and the tagger's aspect says which —
        # its present-future is its future; a verb the table lacks (промыслить) goes by
        # the tagger's aspect.
        tagged = feats.get("Aspect")
        if (table == "perfective" and tagged != "Imp") or (
            tagged == "Perf" and table not in ("imperfective", "both")
        ):
            return lemma, feats | {"Tense": "Fut", "Aspect": "Perf"}
        return lemma, feats
    if cells:
        return lemma, feats
    partners = {p for row in reader.rows(lemma, "verb") for p in row.partners}
    hits = {
        name
        for name, column in reader.cells(word, "verb")
        if _PRESFUT.match(column) and name in partners
    }
    if len(hits) != 1:
        return lemma, feats
    partner = hits.pop()
    aspect = _ASPECT.get(reader.aspect(partner), "")
    if not aspect:
        return lemma, feats
    out = feats | {"Aspect": aspect, "Tense": "Fut" if aspect == "Perf" else "Pres"}
    return partner, out
