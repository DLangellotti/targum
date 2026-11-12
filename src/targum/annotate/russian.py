"""Russian words read on this machine: spaCy tags, Stanza names the dictionary form.

Until 2026-09-27 every Russian word was read by the model one sentence at a time and paid
for (`model_lemma.py`), because every Russian treebank is NonCommercial or ShareAlike and
no tagger trained on one passed `LICENSING.md`. A rebuild buys nothing, so the box could
not re-read a Russian text whose words were bought on the laptop, and the shared Russian
texts stayed frozen on the annotator that built them (targum-internal#310). David carved
Russian out of that rule on 2026-09-27: a Russian model may be used whatever it was trained
on, provided its own licence permits commercial use. This is what the carve-out bought.

**Three readers, each doing what it was measured best at** (SynTagRus dev set,
2026-09-27, `scripts/eval_lemma.py --system ru-local`; the model's figures are its own
run of 2026-09-14 on the same first 120 sentences):

- **spaCy's `ru_core_news_lg`** (MIT, trained on Nerus and Navec, both MIT) tokenizes,
  tags the part of speech and the grammar, and parses. Its own dictionary forms come
  from pymorphy3 and lose DET, PRON and participles to a mapping bug (0.893 on the 120),
  so they are not used as the answer.
- **Stanza's Russian lemmatizer** (`syntagrus_nocharlm`, Apache-2.0, 4 MB, trained on
  SynTagRus) gives the dictionary form from the word and spaCy's part of speech. It is
  the lemmatizer alone: Stanza's Russian tagger and parser load the `conll17` vectors,
  which are CC BY-NC-SA files in their own right and which the carve-out does not cover;
  this does not load them.
- **pymorphy3** (MIT; its dictionary is OpenCorpora, CC BY-SA 3.0) checks both. It says
  which cases a written form can be in (`settle`), which aspect a verb has, which ё a
  dictionary form has (`with_yo`), and what a verb's own infinitive (`own_aspect`), a
  name's nominative (`as_name`) and a word Stanza invented (`known`) should be.

What that comes to, against the model: dictionary forms 0.942 to 0.932, part of speech
0.934 to 0.895, number 0.986 to 0.961, aspect 0.982 to 0.973, gender 0.969 to 0.946 —
and case 0.940 to 0.957, the one it loses. Over all 8,906 dev sentences, which only a
reader that costs nothing can be asked to read: 0.954, 0.946, 0.982, 0.973, 0.967, 0.950.

**Where it is worse: case.** Nearly half of what it misses is nominative read as
accusative or back — 1,750 of 3,650 on the dev set — which for a noun is the same
letters and the same stress, so the stress stage (which reads case and number to tell
руки́ from ру́ки) loses little; the card's grammar line does.

**Kept in targum's spelling, not the treebank's.** SynTagRus writes its dictionary forms
with е for ё; the card, OpenRussian's tables and the model all write ё (учёный), and
OpenRussian files учёный under ё, so a lemma without it finds no table and no stress. The
ё is put back and the score pays for it, as the model's does.

**Free, so the name moves freely.** Nothing is bought, so a Russian text is read whole on
any machine that has the `russian` extra, and a change here renames the annotator and
re-reads every Russian text for nothing but time. Without the extra, Russian is read by
the model exactly as before (`model_lemma.reads`).
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import logging
import threading
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field, replace
from typing import Any

from ..errors import TargumError
from ..models import Segment, Token
from ..paths import model_dir
from ..segment.stanza_segmenter import AUDITED

#: spaCy's Russian pipeline. `lg` over `sm` and `md` by the dev set: case 0.951 against
#: 0.944 and 0.946 over all 8,906 sentences, aspect 0.973 against 0.961 and 0.962. It is
#: 640 MB on disk, most of it Navec's vectors.
SPACY_MODEL = "ru_core_news_lg"

#: Stanza's Russian lemmatizer, by name, never Stanza's default: the build
#: `segment/stanza_segmenter.AUDITED` lists. The `nocharlm` build needs no character model
#: and no word vectors: one 4 MB file.
LEMMA_PACKAGE = AUDITED["ru"]["lemma"]

#: Segments read at a time. The whole SynTagRus dev set in one call, 8,906 sentences, held
#: 1.47 GB; a book is read in pieces so that its length is not the box's problem.
CHUNK = 256

#: Moves when what this module writes changes, which re-reads every Russian text.
#: 2: ё is folded to е before Stanza is asked (targum-internal#650).
VERSION = 2

#: What each spaCy part of speech may be in pymorphy3's tagset, for reading its analyses.
#: A participle is spaCy's VERB with VerbForm=Part, and pymorphy's PRTF.
_COMPATIBLE = {
    "NOUN": frozenset({"NOUN"}),
    "PROPN": frozenset({"NOUN"}),
    "ADJ": frozenset({"ADJF", "PRTF"}),
    "DET": frozenset({"ADJF", "NPRO"}),
    "PRON": frozenset({"NPRO"}),
    "NUM": frozenset({"NUMR", "ADJF"}),
    "VERB": frozenset({"PRTF"}),
}
_VERBISH = frozenset({"VERB", "INFN", "PRTF", "PRTS", "GRND"})

#: pymorphy3's cases in Universal Dependencies' names. The second genitive is the
#: partitive (чаю) and the second locative is the locative still (в лесу).
CASES = {
    "nomn": "Nom",
    "gent": "Gen",
    "gen1": "Gen",
    "gen2": "Par",
    "datv": "Dat",
    "accs": "Acc",
    "acc2": "Acc",
    "ablt": "Ins",
    "loct": "Loc",
    "loc1": "Loc",
    "loc2": "Loc",
    "voct": "Voc",
}
ASPECTS = {"perf": "Perf", "impf": "Imp"}
_NUMBERS = {"Sing": "sing", "Plur": "plur"}
#: spaCy writes the person as a word; the card, and the model, as a digit.
_PERSONS = {"First": "1", "Second": "2", "Third": "3"}

#: A subject is nominative and a direct object accusative, whatever the ending says; a
#: word agreeing with one of them takes its case. Only between those two, which is where
#: the tagger's errors are (1,750 of 3,650 on the dev set) and where the parse knows more
#: than the ending.
_SUBJECTS = frozenset({"nsubj", "nsubj:pass"})
_AGREEING = frozenset({"amod", "det", "nummod", "acl"})


@dataclass
class Analysis:
    """One of pymorphy3's readings of a written form: its case, number and part of speech,
    and how likely it thinks the reading is."""

    case: str
    number: str
    pos: str
    score: float


@dataclass
class Tagged:
    """One word as spaCy read it, with pymorphy3's view of its form beside it."""

    text: str
    pos: str
    feats: dict[str, str]
    dep: str = ""
    #: The head's position, relative to this word's.
    head: int = 0
    analyses: list[Analysis] = field(default_factory=list)
    #: The aspects pymorphy3 gives any verbal reading of the form.
    aspects: frozenset[str] = frozenset()


def parse_feats(morph: str) -> dict[str, str]:
    """spaCy's grammar string as a dict, the person written as the card writes it."""
    out: dict[str, str] = {}
    for part in (morph or "").split("|"):
        name, _, value = part.partition("=")
        if name and value:
            out[name] = _PERSONS.get(value, value) if name == "Person" else value
    return out


def settle(words: Sequence[Tagged]) -> list[dict[str, str]]:
    """Each word's grammar, with the aspect and case corrected where the dictionary or the
    parse knows better than the tagger. The words are not changed; the answer is new."""
    feats = [dict(word.feats) for word in words]
    for word, said in zip(words, feats, strict=True):
        if word.pos in {"VERB", "AUX"} and len(word.aspects) == 1:
            said["Aspect"] = ASPECTS[next(iter(word.aspects))]
        _case_from_form(word, said)
    for word, said in zip(words, feats, strict=True):
        if said.get("Case") not in {"Nom", "Acc"}:
            continue
        if word.dep in _SUBJECTS:
            said["Case"] = "Nom"
        elif word.dep == "obj":
            said["Case"] = "Acc"
    for at, (word, said) in enumerate(zip(words, feats, strict=True)):
        if word.dep not in _AGREEING or said.get("Case") not in {"Nom", "Acc"}:
            continue
        head = at + word.head
        if 0 <= head < len(feats) and feats[head].get("Case") in {"Nom", "Acc"}:
            said["Case"] = feats[head]["Case"]
    return feats


def _case_from_form(word: Tagged, said: dict[str, str]) -> None:
    """A case the written form cannot be in is replaced by the likeliest one it can, and a
    declined word the tagger left without a case is given one."""
    allowed_pos = _COMPATIBLE.get(word.pos)
    if not allowed_pos or not word.analyses:
        return
    if word.pos == "VERB" and said.get("VerbForm") != "Part":
        return
    readings = [a for a in word.analyses if a.pos in allowed_pos and a.case] or [
        a for a in word.analyses if a.case
    ]
    if not readings or said.get("Case") in {a.case for a in readings}:
        return
    number = _NUMBERS.get(said.get("Number", ""))
    agreeing = [a for a in readings if a.number == number] or readings
    said["Case"] = max(agreeing, key=lambda a: a.score).case


def without_yo(word: str) -> str:
    """The word as the treebank Stanza learned from writes it, ё as е.

    SynTagRus never writes ё, so Stanza's lemmatizer has no letter for it and puts one it
    knows in its place: it read ёлке as блок, ёжика as бжик and ёмкости as бмкость, and
    the dictionary, which knows блок, had no reason to doubt it. Asked елке, it answers
    елка, and `with_yo` puts the ё back from the dictionary (targum-internal#650)."""
    return word.replace("ё", "е").replace("Ё", "Е")


def with_yo(lemma: str, spellings: Iterable[str]) -> str:
    """The dictionary form with its ё, where the readings offered spell it one way only, and
    that way has ё. The treebank Stanza learned from writes е; targum does not.

    Where one reading of the word is spelled with е — совершенный, perfect, beside
    совершённый, accomplished — the е is left: which word this is is not a spelling rule's
    to say."""
    if "ё" in lemma or "Ё" in lemma:
        return lemma
    key = lemma.lower()
    matching = {s.lower() for s in spellings if s.lower().replace("ё", "е") == key}
    if len(matching) != 1 or key in matching:
        return lemma
    restored = matching.pop()
    return restored.capitalize() if lemma[:1].isupper() else restored


def yo_checked(surface: str, lemma: str, normal_forms: Iterable[str]) -> str:
    """A word written with ё filed under the dictionary's one form for it, where Stanza's
    answer is none of the dictionary's.

    Stanza is asked the word with е (`without_yo`), and for most ё-words that is what it
    needs; for some it then answers another word's form or none: недотёпа as недотеп,
    копчёная as копченой, уберём as уберь, ушёл as уйел. The ё was the clue it could not
    read, and the dictionary, which reads it, gives one form. Where the dictionary gives
    several, or Stanza's is among them, Stanza's stands (targum-internal#650)."""
    if "ё" not in surface.lower():
        return lemma
    forms = {form.lower() for form in normal_forms}
    if without_yo(lemma.lower()) in {without_yo(form) for form in forms} or len(forms) != 1:
        return lemma
    return forms.pop()


#: The third-person pronouns whose genitive is also the possessive: его дом, её дом, их дом.
_POSSESSIVES = {"его": "он", "её": "она", "их": "они"}


_NOUNS = frozenset({"NOUN", "PROPN"})
_VERBS = frozenset({"VERB", "AUX"})
#: The dependencies spaCy gives a possessive it tags PRON.
_POSSESSIVE_DEPS = frozenset({"nmod", "det", "nmod:poss"})
#: What may stand between a possessive and its noun: его новый дом, их первые два года,
#: её поистине царственные плечи, его же церкви, их «заманчивого предложения».
_MODIFIERS = frozenset({"ADJ", "DET", "NUM"})
_PASSED = frozenset({",", "же", "ли", "«", "»", "и"})
#: A verb's object straight after it, with a noun after that which is not the possessive's:
#: the noun is the verb's subject or another of its arguments (ожидают его просители,
#: хлопнув его рукою), where the possessive's noun would be its object (видел его брата).
_ARGUMENTS = frozenset({"nsubj", "nsubj:pass", "obl", "nmod"})


def _participle(piece: Piece) -> bool:
    return piece.pos == "VERB" and "VerbForm=Part" in piece.morph


def _noun_after(sentence: Sequence[Piece], at: int, reads: Callable[[str, str], bool]) -> int:
    """The noun the word at `at` goes before, past its adjectives, or -1. An adverb may
    stand between only before an adjective (его страшно побледневшим лицом). A word spaCy
    calls a noun is one only where the dictionary has a noun or an adjective reading of it
    (его знакомый): горячечно is an adverb, убей a verb."""
    after = at + 1
    adverb = False
    adjective = -1
    while after < len(sentence):
        word = sentence[after]
        if word.pos == "NOUN" and not reads(word.text, "NOUN"):
            if reads(word.text, "ADJF") or reads(word.text, "PRTF"):
                break  # an adjective standing for its noun: его знакомый, его поверенный
            if reads(word.text, "VERB"):
                return -1
            adverb = True
        elif word.pos in _MODIFIERS or _participle(word):
            adverb = False
            adjective = after
        elif word.text.lower() in _PASSED or word.pos == "CCONJ":
            pass
        elif word.pos == "ADV":
            adverb = True
        else:
            break
        after += 1
    if after < len(sentence) and sentence[after].pos in _NOUNS and not adverb:
        return after
    # An adjective standing for its noun (в его переднюю, её кондитерская), where spaCy has
    # not taken the word for the pronoun.
    if sentence[at].pos != "PRON" and adjective > at and sentence[adjective].pos == "ADJ":
        return adjective
    return -1


#: The personal pronouns, which as a subject straight before его, её or их make it their
#: verb's object (мы его поймаем).
_PERSONAL = frozenset({"я", "ты", "он", "она", "оно", "мы", "вы", "они"})
#: Nouns of quantity, which take the pronoun's genitive after them, not a possessive:
#: тысячи их, сотни их, большинство их.
_QUANTITIES = ("сотн", "тысяч", "миллион", "десят", "множеств", "большинств", "половин")


def possessive(sentence: Sequence[Piece], at: int, reads: Callable[[str, str], bool]) -> bool:
    """Whether его, её or их at `at` is the possessive (его дом), by spaCy's parse and the
    words' order; `reads(word, grammeme)` asks the dictionary whether the word has a
    reading with the grammeme (pymorphy3's `tran`, `anim`).

    spaCy's tag is half a guide. Where it says PRON as an object or a subject (я вижу его,
    его не было) it is right, and that stands. Where it says DET, PART, ADP or PRON hung
    off a noun, it is as often an object (хлопнув его рукою, где его похоронили). So the
    possessive is the word that stands straight after its noun (у отца его, лицо его;
    but тысячи их is the pronoun's) or before it, with only adjectives between (его
    брата, о его новой книге). Straight after a verb with no other object, before a
    noun in the nominative, the noun is the verb's subject, and where the verb is
    transitive the word is its object if the subject is a person or an animal (одел его
    сапожник, ожидают его просители) and the possessive if it is a thing (тревожил его
    покой, шептали его губы); after a verb that takes no object it is the possessive
    (шла его дочь). Before another of a transitive verb's arguments it is the object
    (хлопнув его рукою). бы and ли may stand between (обманул бы его овчинник). After a
    pronoun that is the subject it is the object (мы его поймаем), and next to a word spaCy
    calls a noun that the dictionary has no noun reading of, it is too (Тащи его, хоть его
    убей).
    A participle takes no object there (поражённая его грандиозностью). After a
    preposition the pronoun is spelled него, so it never comes here (targum-internal#683)."""
    word = sentence[at]
    if word.pos == "PRON" and word.dep not in _POSSESSIVE_DEPS:
        return False
    before = sentence[at - 1] if at > 0 else None
    if before is not None and before.pos == "PRON" and before.dep.startswith("nsubj"):
        if before.text.lower().split("-")[0] in _PERSONAL:
            # я его, мы его, ты их, он её: the subject, and then its object, unless a noun
            # that is the verb's object follows (они его справедливость любят).
            noun = _noun_after(sentence, at, reads)
            return noun >= 0 and sentence[noun].dep == "obj"
    if before is not None and before.pos == "NOUN" and not reads(before.text, "NOUN"):
        if reads(before.text, "VERB"):
            # A verb spaCy took for a noun: Одел его, Тащи его, Сложи их.
            return False
        before = None
    if before is not None and before.pos in _NOUNS:
        return word.text.lower() != "их" or not before.text.lower().startswith(_QUANTITIES)
    noun = _noun_after(sentence, at, reads)
    if noun < 0:
        return False
    after = sentence[noun]
    verb = at - 2 if before is not None and before.text.lower() in {"бы", "ли"} else at - 1
    if (
        verb < 0
        or sentence[verb].pos not in _VERBS
        or _participle(sentence[verb])
        or any(other.head == verb and other.dep == "obj" for other in sentence)
        or not reads(sentence[verb].text, "tran")
    ):
        return True
    if "Case=Nom" in after.morph or after.dep.startswith("nsubj"):
        return not reads(after.text, "anim")
    return after.dep not in _ARGUMENTS


def pronoun(
    sentence: Sequence[Piece], at: int, pos: str, reads: Callable[[str, str], bool]
) -> str | None:
    """The dictionary form a learner looks a pronoun up by, where the treebank's is another.

    The possessive его, её and их does not change and is its own word on the card (его
    дом, её дом, их дом; `possessive`); as the pronoun's own case (я вижу его, её, их)
    each is он, она, они (targum-internal#650, #683). всё, everything, is its own word too
    — всё равно, всё ещё, всё в порядке — and not filed under весь, as it is where it
    agrees with a noun (всё время, всё это), which spaCy tags DET (targum-internal#650)."""
    word = sentence[at].text.lower()
    if word in _POSSESSIVES:
        return word if possessive(sentence, at, reads) else _POSSESSIVES[word]
    if word == "всё" and pos != "DET":
        return "всё"
    return None


#: What follows a hyphen and makes the word before it a different word, not a second one:
#: каких-то, какой-либо, где-нибудь, давай-ка, всё-таки. The word takes the first half's
#: grammar. Everywhere else — из-за, по-русски, кое-что, светло-синий — the last half's.
_TAILS = frozenset({"то", "либо", "нибудь", "ка", "таки", "де", "тка"})


@dataclass
class Piece:
    """One word of a sentence as spaCy read it, a word written with a hyphen inside it
    joined back into one."""

    text: str
    idx: int
    pos: str
    morph: str
    dep: str
    #: The head's position among the sentence's pieces.
    head: int
    lemma: str


def pieces(doc: Sequence[Any]) -> list[Piece]:
    """The sentence's words, spaces left out and hyphenated words joined.

    Russian writes a word with a hyphen inside it — из-за, каких-то, по-русски — and the
    treebank, the dictionary and the model's prompt all call that one word. spaCy's
    tokenizer splits it in three and its tagger learned from the split, so it is read
    split and joined afterwards: told to keep из-за whole, the tagger called it a feminine
    plural noun. The joined word takes one half's grammar (`_TAILS`)."""
    tokens = list(doc)
    groups: list[list[int]] = []
    at = 0
    while at < len(tokens):
        if tokens[at].is_space:
            at += 1
            continue
        group = [at]
        while (
            at + 2 < len(tokens)
            and tokens[at + 1].text == "-"
            and not tokens[at].whitespace_
            and not tokens[at + 1].whitespace_
            and tokens[at].text[-1:].isalpha()
            and tokens[at + 2].text[:1].isalpha()
        ):
            group += [at + 1, at + 2]
            at += 2
        groups.append(group)
        at += 1
    where = {i: n for n, group in enumerate(groups) for i in group}
    out: list[Piece] = []
    for n, group in enumerate(groups):
        halves = [tokens[i] for i in group[::2]]
        lead = halves[0] if halves[-1].text.lower() in _TAILS else halves[-1]
        first, last = tokens[group[0]], tokens[group[-1]]
        text = "".join(tokens[i].text for i in group)
        joined = len(group) > 1
        out.append(
            Piece(
                text=text,
                idx=first.idx,
                pos=lead.pos_,
                morph=str(lead.morph),
                dep=lead.dep_,
                head=where.get(lead.head.i, n),
                # spaCy's own dictionary form, which is only asked for its ё: a joined
                # word has none worth asking.
                lemma=text.lower() if joined else last.lemma_,
            )
        )
    return out


#: pymorphy3's marks for a name: a first name, a surname, a patronymic, a place, an
#: organisation, a trademark.
_NAMED = frozenset({"Name", "Surn", "Patr", "Geox", "Orgn", "Trad"})


#: The small words inside a hyphenated name that stay small: Ростов-на-Дону.
_PARTICLES = frozenset(
    {"на", "де", "ла", "ле", "дер", "фон", "ван", "да", "ди", "дель", "аль", "эль", "ибн", "бен"}
)


def _named_form(parse: Any) -> str:
    """A name in the nominative, in its own gender: Чудаковой is Чудакова, not the
    Чудаков pymorphy3 gives as the normal form, and Николаевна stays Николаевна."""
    wanted = {"nomn"} if "Pltm" in parse.tag.grammemes else {"nomn", "sing"}
    inflected = parse.inflect(wanted)
    return str(inflected.word) if inflected is not None else str(parse.normal_form)


def _named_first(parses: Sequence[Any]) -> bool:
    return bool(parses) and bool(_NAMED & set(parses[0].tag.grammemes))


def as_name(lemma: str, named: Sequence[tuple[str, float, str]], case: str) -> str:
    """A name's dictionary form, from the dictionary's readings of it as a name — Герасима
    is Герасим, Матрены is Матрёна, Иваныч is Иванович — the reading in the word's own case
    first. Stanza, which learned names from a treebank of other people's, left Герасима as
    it was and made Матрен of Матрены. A name the dictionary does not know keeps Stanza's
    answer."""
    if not named:
        return lemma
    fitting = [reading for reading in named if reading[0] == case] or list(named)
    best = max(fitting, key=lambda reading: reading[1])[2]
    return "-".join(
        part if at and part in _PARTICLES else part.capitalize()
        for at, part in enumerate(best.split("-"))
    )


def known(lemma: str, parses: Sequence[Any]) -> str:
    """For a dictionary form the dictionary has never heard of — Stanza made барынь of
    барыня — the dictionary's own, where it knows the word and gives it one form."""
    found = {str(p.normal_form) for p in parses if p.is_known}
    return found.pop() if len(found) == 1 else lemma


def own_aspect(lemma: str, infinitives: Sequence[str]) -> str:
    """A verb's dictionary form in its own aspect: the dictionary's infinitive for the form,
    where it gives exactly one.

    Stanza's Russian lemmatizer files a perfective under its imperfective partner — взял
    as брать, сделал as делать, увидел as видеть — though the treebank it learned from does
    not. Over the nineteen Russian texts on the laptop it wrote взял as брать 195 times and
    сделал as делать 146, and a learner's two hardest facts about a verb are that взять and
    брать are two words and which is which: a card that says брать over взял with
    Aspect=Perf beside it contradicts itself."""
    found = {form.lower() for form in infinitives}
    if len(found) != 1:
        return lemma
    return found.pop()


def available() -> bool:
    """Whether this machine has what reads Russian locally: the `russian` extra, and Stanza.
    The lemmatizer's 4 MB file is fetched at first use where it is missing, as every Stanza
    model is. Nothing is imported to answer."""
    return all(
        importlib.util.find_spec(name) is not None
        for name in ("spacy", SPACY_MODEL, "pymorphy3", "stanza")
    )


def installed(name: str) -> str:
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version(name)
    except PackageNotFoundError:
        return "unknown"


def is_fetched() -> bool:
    return (model_dir() / "ru" / "lemma" / f"{LEMMA_PACKAGE}.pt").is_file()


def fetch() -> None:
    """Stanza's Russian lemmatizer, the build `AUDITED` lists, and nothing else of Stanza's
    for Russian."""
    from ..segment.stanza_segmenter import download

    download("ru", processors="lemma")


#: The pipelines, loaded once a process and shared by every reader made here: a rebuild
#: makes one per text, and each would otherwise hold its own 640 MB.
_LOADED: dict[str, Any] = {}
_LOCK = threading.Lock()


class RussianLemmatizer:
    """Tokens, dictionary forms, parts of speech and grammar for Russian, read here."""

    #: A Latin word inside Russian is already left alone by its script (`in_script`).
    marks_foreign = False

    def __init__(self, *, auto_download: bool = True) -> None:
        self.auto_download = auto_download

    @property
    def name(self) -> str:
        """What made this annotation, stable before anything is loaded."""
        return (
            f"ru-local/{SPACY_MODEL}-{installed(SPACY_MODEL)}"
            f"+stanza-{installed('stanza')}/{LEMMA_PACKAGE}"
            f"+pymorphy3-{installed('pymorphy3')}/{VERSION}"
        )

    def _load(self) -> tuple[Any, Any, Any]:
        with _LOCK:
            if not _LOADED:
                if not available():
                    raise TargumError(
                        "Russian words are not read on this machine.",
                        "Install targum with the russian extra.",
                    )
                if not is_fetched():
                    if not self.auto_download:
                        raise TargumError(
                            "The Russian lemmatizer is not downloaded.", "targum models fetch ru"
                        )
                    fetch()
                import pymorphy3
                import spacy
                import stanza

                logging.getLogger("stanza").setLevel(logging.ERROR)
                # The named-entity reader is left out: nothing reads what it says.
                _LOADED["spacy"] = spacy.load(SPACY_MODEL, exclude=["ner"])
                _LOADED["morph"] = pymorphy3.MorphAnalyzer()
                with contextlib.redirect_stdout(io.StringIO()):
                    _LOADED["lemma"] = stanza.Pipeline(
                        lang="ru",
                        processors="lemma",
                        package={"lemma": LEMMA_PACKAGE},
                        lemma_pretagged=True,
                        dir=str(model_dir()),
                        download_method=None,
                        verbose=False,
                    )
            return _LOADED["spacy"], _LOADED["morph"], _LOADED["lemma"]

    def lemmas(self, segments: list[Segment], language: str) -> dict[str, list[Token]]:
        if not segments:
            return {}
        if (language or "").split("-")[0].lower() != "ru":
            raise TargumError(
                f"The Russian reader does not read '{language}'.",
                "See annotate/lemma.for_language.",
            )
        nlp, morph, lemmatizer = self._load()
        out: dict[str, list[Token]] = {}
        with _LOCK:
            for at in range(0, len(segments), CHUNK):
                out.update(_read(segments[at : at + CHUNK], nlp, morph, lemmatizer))
        return out


def stanza_asked(words: Sequence[Sequence[Piece]]) -> list[list[dict[str, Any]]]:
    """What Stanza's lemmatizer is handed: each sentence's words with spaCy's part of
    speech, spelled as its treebank spells them (`without_yo`). An empty sentence is left
    out, and so is not answered."""
    return [
        [
            {"id": at + 1, "text": without_yo(piece.text), "upos": piece.pos or "X"}
            for at, piece in enumerate(sentence)
        ]
        for sentence in words
        if sentence
    ]


#: What each spaCy part of speech may be in pymorphy3's tagset, for asking whether the
#: dictionary has any reading of a word under the tag spaCy gave it.
_READABLE = {
    **_COMPATIBLE,
    "ADJ": frozenset({"ADJF", "ADJS", "PRTF", "PRTS", "COMP"}),
    "VERB": frozenset({"VERB", "INFN", "PRTF", "PRTS", "GRND"}),
    "AUX": frozenset({"VERB", "INFN"}),
    "ADV": frozenset({"ADVB", "COMP", "PRED"}),
    "PRON": frozenset({"NPRO"}),
    "NUM": frozenset({"NUMR", "ADJF"}),
    "ADP": frozenset({"PREP"}),
    "CCONJ": frozenset({"CONJ"}),
    "SCONJ": frozenset({"CONJ"}),
    "PART": frozenset({"PRCL"}),
    "INTJ": frozenset({"INTJ"}),
}


def readable(piece: Piece, morph: Any) -> bool:
    """Whether the dictionary has a reading of the word under the tag spaCy gave it."""
    allowed = _READABLE.get(piece.pos)
    return allowed is None or any(
        p.tag.POS in allowed for p in morph.parse(piece.text) if p.is_known
    )


def has_reading(word: str, grammeme: str, morph: Any) -> bool:
    """Whether the dictionary reads the word with the grammeme: `tran` for a verb with any
    reading that takes a direct object; `anim` for a noun whose likeliest reading names a
    person or an animal (Любовь is a name, любовь is not)."""
    parses = morph.parse(word)
    if grammeme == "anim":
        nouns = [p for p in parses if p.tag.POS == "NOUN"]
        return bool(nouns) and "anim" in nouns[0].tag
    return any(grammeme in p.tag for p in parses)


def yo_repaired(words: list[Piece], folded: list[Piece], morph: Any) -> list[Piece]:
    """The sentence as spaCy read it, with each word written with ё read as spaCy read it
    with е instead, where only that reading is one the dictionary has.

    spaCy's tagger, like Stanza's treebank, barely knows ё: it read идёт as a noun, щёки
    as a verb and поёт as an adjective. Asked the text with е (`without_yo`), it reads
    them right. But asking the whole text so moves words with no ё, by their context
    (Вынимай became a particle, Гингиле a common noun), and a ё-word it already read well
    can move the wrong way (землёю a verb, населённого a verb's form). So the е reading
    is taken word by word, only for a ё-word whose tag the dictionary has no reading under
    and whose е tag it does. Over the laptop's Russian shelf, 610 of 3,123 ё-words read
    differently with е; about 300 of those are repairs of this kind. всё is left as read: its
    tag decides всё or весь (`pronoun`), and the е reading moved it either way about as
    often (targum-internal#683)."""
    if [w.idx for w in words] != [w.idx for w in folded]:
        return words
    out = list(words)
    for at, (word, other) in enumerate(zip(words, folded, strict=True)):
        if (
            "ё" in word.text.lower()
            and word.text.lower() != "всё"
            and word.pos != other.pos
            and not readable(word, morph)
            and readable(other, morph)
        ):
            # spaCy's own form, asked with е, would stand in the ё's way (`with_yo`):
            # pymorphy3's readings of the written word give the ё instead.
            out[at] = replace(other, text=word.text, lemma="")
    return out


def _read(segments: list[Segment], nlp: Any, morph: Any, lemmatizer: Any) -> dict[str, list[Token]]:
    from stanza.models.common.doc import Document

    docs = nlp.pipe([segment.text for segment in segments], batch_size=64)
    words = [pieces(doc) for doc in docs]
    yo = [at for at, segment in enumerate(segments) if "ё" in segment.text.lower()]
    folded = nlp.pipe([without_yo(segments[at].text) for at in yo], batch_size=64)
    for at, doc in zip(yo, folded, strict=True):
        words[at] = yo_repaired(words[at], pieces(doc), morph)
    asked = stanza_asked(words)
    answered = iter(lemmatizer(Document(asked)).sentences if asked else [])
    out: dict[str, list[Token]] = {}
    for segment, sentence in zip(segments, words, strict=True):
        if not sentence:
            out[segment.id] = []
            continue
        out[segment.id] = _tokens(segment.text, sentence, next(answered).words, morph)
    return out


def _tagged(at: int, piece: Piece, morph: Any) -> Tagged:
    parses = morph.parse(piece.text) if piece.pos in _COMPATIBLE or piece.pos == "AUX" else []
    return Tagged(
        text=piece.text,
        pos=piece.pos,
        feats=parse_feats(piece.morph),
        dep=piece.dep,
        head=piece.head - at,
        analyses=[
            Analysis(
                CASES.get(str(p.tag.case), ""), str(p.tag.number or ""), str(p.tag.POS), p.score
            )
            for p in parses
            if p.tag.case
        ],
        aspects=frozenset(
            str(p.tag.aspect) for p in parses if p.tag.POS in _VERBISH and p.tag.aspect
        ),
    )


def _tokens(text: str, sentence: list[Piece], stanza_words: Any, morph: Any) -> list[Token]:
    from .model_lemma import features

    tagged = [_tagged(at, piece, morph) for at, piece in enumerate(sentence)]
    grammar = settle(tagged)
    out: list[Token] = []
    for at, (piece, word, said, read) in enumerate(
        zip(sentence, tagged, grammar, stanza_words, strict=True)
    ):
        pos = word.pos or "X"
        if pos in {"PUNCT", "SYM", "SPACE"}:
            continue
        surface = piece.text
        if not any(char.isalpha() for char in surface):
            if not any(char.isdigit() for char in surface):
                continue
            # A year spaCy calls an adjective is still a number to the reader, which
            # leaves numbers out of what a learner has to know.
            pos = "NUM"
        parses = morph.parse(surface)
        spellings = [piece.lemma, *(p.normal_form for p in parses)]
        lemma = with_yo(read.lemma or surface, spellings)
        lemma = yo_checked(surface, lemma, [p.normal_form for p in parses if p.is_known])
        if pos in _COMPATIBLE and not morph.word_is_known(lemma):
            lemma = known(lemma, [p for p in parses if p.tag.POS in _COMPATIBLE[pos]])
        if pos in {"VERB", "AUX"}:
            lemma = own_aspect(lemma, [p.normal_form for p in parses if p.tag.POS in _VERBISH])
        named = [
            (CASES.get(str(p.tag.case), ""), p.score, _named_form(p))
            for p in parses
            if _NAMED & set(p.tag.grammemes)
        ]
        if pos == "NOUN" and piece.idx > 0 and surface[:1].isupper() and _named_first(parses):
            # A name spaCy took for a noun (Варя, Вари), mid-sentence and capitalised,
            # whose likeliest reading in the dictionary is a name.
            pos = "PROPN"
        if pos == "PROPN":
            lemma = as_name(lemma, named, said.get("Case", ""))
        lemma = pronoun(sentence, at, pos, lambda w, g: has_reading(w, g, morph)) or lemma
        if not any("\u0400" <= char <= "\u04ff" for char in surface):
            # Not a Russian word, and Stanza's answer for one is not to be trusted: it
            # wrote Facebook as Фейсбук.
            lemma = surface
        start = piece.idx
        out.append(
            Token(
                start=start,
                end=start + len(surface),
                surface=text[start : start + len(surface)],
                lemma=lemma if pos == "PROPN" else lemma.lower(),
                band=0,
                pos=pos,
                feats=features("|".join(f"{k}={v}" for k, v in said.items()), pos, "ru"),
            )
        )
    return out
