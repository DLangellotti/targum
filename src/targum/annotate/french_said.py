"""How a French word is said in its sentence: its IPA, the liaisons always made, the
elisions and the final consonants nobody says (targum-internal#266).

**Morphalou alone** (David, 2026-09-28). Every reading here is a row of Morphalou 3.1
(`annotate/morphalou.py`), chosen by the word's lemma, part of speech and features where
the spelling is said more than one way. A word the table has no reading for shows none;
nothing is guessed from the spelling and no other lexicon is asked. A hyphenated compound
the table lists without a reading (`là-bas`, `peut-être`) is said by its parts, each of
which must have one reading of its own.

**Two things in the table are not taken as they stand.** Both were found by the
measurement on the French shelf:

- `un` has a numeral row that reads `y n @`, which is `une`'s reading copied onto the
  masculine. The spelling `un` is masculine whatever its part of speech, and the table's
  own masculine determiner row says `9~`, so a reading of `un` that is the feminine's is
  dropped. That is a choice between two of the table's readings of the same form, and
  asserts nothing the table does not already say.
- `c'` reads `k`, where the elided `ce` is /s/. That is a correction: /s/ is a reading the
  table does not give the form. It is applied here, at lookup, from
  `morphalou_corrections.tsv`, a file of one row under LGPL-LR with the change and its date
  in its header, which is the smallest correction the owner's rule (LICENSING.md, "Any
  correction targum makes to its data is published under LGPL-LR") can be published as.
  The table itself is never altered and never shipped.

**What is shown is the everyday reading.** The table's first variant, in IPA, with the
final schwa it writes after a consonant (`femme` `f a m @`) left off, as a dictionary
does: a word's last `e` is not said in ordinary speech. A one-syllable word keeps its
schwa (`le`, `je`), and so does a word before its liaison (*quelques‿amis*). That is how
the reading is shown, not a change to it: the table's `@` is a schwa that may be said.

**The liaison is gruut's** (`fr_post_process_sentence`, MIT, archived; credited in
LICENSING.md): a liaison needs a first word ending in a letter its reading leaves silent
and a second word whose reading begins with a vowel, and the consonant heard is gruut's —
s, x or z is /z/, d is /t/, and t, p and n are themselves. gruut marks a liaison after
any determiner, numeral, preposition, adjective or verb; this marks only the ones every
speaker makes, which is where the card promised to stop (the issue, and a measured
precision floor of 0.98 against a gold set):

- a determiner or numeral before its noun or adjective: *les‿enfants*, *deux‿heures*;
- a clitic pronoun before its verb, or before *en* and *y*: *ils‿ont*, *on‿en‿a*;
- a verb before its inverted subject pronoun: *dit-il*, *prend-il*.

Not before an h aspiré (`H_ASPIRE`) or the few vowel-initial words that behave as one
(*onze*, *oui*); never after *et*; never across punctuation; never after a pronoun that is
itself inverted (*sont-ils / allés*) or that stands after a preposition (*chez nous*).
Optional liaisons — *pas‿encore*, *mais‿il*, *était‿allé* — are left unmarked: natives
make about one in five of them in speech, and a learner told they are required is told
something false.
"""

from __future__ import annotations

import functools
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from . import morphalou

#: The switch, read when a reader is written (targum-internal#266). Off until the gold set
#: the liaisons are scored against has been read by a person.
FLAG = "TARGUM_FRENCH_IPA"


def is_on() -> bool:
    return os.environ.get(FLAG, "").strip().lower() in {"1", "true", "yes"}


#: Morphalou's notation, symbol by symbol, in IPA. `E/` and `O/` are the mid vowels where
#: either height is heard and `6` the front rounded one; they appear only in a second
#: variant, which is never the one shown, and are given the open vowel if they ever lead.
PHONES = {
    "a": "a",
    "a~": "ɑ̃",
    "b": "b",
    "d": "d",
    "e": "e",
    "e~": "ɛ̃",
    "E": "ɛ",
    "E/": "ɛ",
    "f": "f",
    "g": "ɡ",
    "H": "ɥ",
    "i": "i",
    "j": "j",
    "J": "ɲ",
    "k": "k",
    "l": "l",
    "m": "m",
    "n": "n",
    "N": "ŋ",
    "o": "o",
    "o~": "ɔ̃",
    "O": "ɔ",
    "O/": "ɔ",
    "p": "p",
    "R": "ʁ",
    "s": "s",
    "S": "ʃ",
    "t": "t",
    "u": "u",
    "v": "v",
    "w": "w",
    "y": "y",
    "z": "z",
    "Z": "ʒ",
    "2": "ø",
    "6": "œ",
    "9": "œ",
    "9~": "œ̃",
    "@": "ə",
}

#: gruut's French vowels (`fr_is_vowel`).
VOWELS = frozenset({"i", "y", "u", "e", "ø", "o", "ə", "ɛ", "œ", "ɔ", "a", "ɔ̃", "ɛ̃", "ɑ̃", "œ̃"})
NASALS = frozenset({"ɔ̃", "ɛ̃", "ɑ̃", "œ̃"})
#: A glide at the start of a word written with a vowel letter links like a vowel:
#: *les‿yeux* /lezjø/, *les‿oiseaux* /lezwazo/, *les‿huîtres* /lezɥitʁ/.
GLIDES = frozenset({"j", "w", "ɥ"})

#: Words that begin with an h or a vowel and still take no liaison: the h aspiré, as a
#: lemma, and *onze*, *oui* and the borrowings that behave the same way. A closed list of
#: common words, written out; a rarer one missing from it is a liaison marked in error,
#: which the gold set is there to find.
H_ASPIRE = frozenset(
    """
    hache hacher hachette hachis hagard haie haillon haine haineux haïr hâle haleter hall
    halle hallebarde halte hamac hameau hampe hamster hanche handicap hangar hanneton
    hanter happer harangue harasser harceler hardes hardi hardiesse harem hareng hargne
    hargneux haricot harnais harpe harpon hasard hasarder hâte hâter hâtif hausse hausser
    haut hautain hautbois hauteur havre hennir hérisser hérisson hernie héron héros hêtre
    heurt heurter hibou hideux hiérarchie hisser hocher hochet hockey hollandais homard
    hongrois honnir honte honteux hoquet horde hors hotte houblon houille houle houlette
    houppe housse houx hublot huche huer huguenot huit huitième humer hurler hurlement
    hussard hutte hâbleur
    onze onzième oui ouistiti uhlan ululer yacht yaourt yoga yak yankee yéti
    """.split()
)

#: The pronouns that lean on the verb after them. *eux*, *elles* after a preposition and
#: the like are tonic, and link to nothing (`_tonic`).
CLITICS = frozenset({"nous", "vous", "ils", "elles", "on", "les", "en"})
#: The subject pronouns a verb can take after a hyphen: *dit-il*, *vont-elles*.
INVERTED = frozenset({"il", "elle", "on", "ils", "elles"})
#: What a determiner links into: the noun, or an adjective or numeral before it.
NOMINAL = frozenset({"NOUN", "ADJ", "NUM", "PROPN"})
#: *des* and *aux* are the article inside a preposition, and link as the article does
#: whichever of the two the tagger called them.
ARTICLES = frozenset({"des", "aux"})

#: gruut's fixed rules for the consonant heard: s, x, z → z; d → t; t, p, n as written.
LIAISON = {"s": "z", "x": "z", "z": "z", "d": "t", "t": "t", "p": "p", "n": "n"}

#: What a letter says, where it ends a word's said part: the consonant before the silent
#: ones (*corps* /kɔʁ/, the r said and the ps not).
_LETTER_SAYS = {
    "b": "b",
    "c": "k",
    "d": "d",
    "f": "f",
    "g": "ɡ",
    "k": "k",
    "l": "l",
    "m": "m",
    "n": "n",
    "p": "p",
    "q": "k",
    "r": "ʁ",
    "s": "s",
    "t": "t",
    "v": "v",
    "z": "z",
}
_VOWEL_LETTERS = frozenset("aeiouyàâäéèêëîïôöûùüÿœæ")
_APOSTROPHES = str.maketrans({"’": "'", "ʼ": "'"})

#: Readings of a form that belong to another form: `un`'s numeral row carries `une`'s.
_MISREAD = {"un": frozenset({"y n @"})}

CORRECTIONS_FILE = Path(__file__).with_name("morphalou_corrections.tsv")


class Word(Protocol):
    """What a tagged word carries: `models.Token` is one."""

    start: int
    end: int
    surface: str
    lemma: str
    pos: str | None
    feats: str | None


@dataclass(frozen=True)
class Said:
    """One word as it is said in its sentence."""

    #: The word's reading in IPA, before the liaison; "" where the table has none.
    ipa: str = ""
    #: The consonant it carries onto the next word, or "".
    liaison: str = ""
    #: Whether it is elided (`l'`, `qu'`): said as one with the word after it.
    elided: bool = False
    #: The letters of the word not said here, as offsets into its sentence: [start, end).
    #: Empty where every written letter is said, or nothing is known.
    silent: tuple[int, int] | None = None

    @property
    def as_said(self) -> str:
        """The reading for the card: with its liaison consonant and a tie where it has one."""
        if not self.ipa:
            return ""
        return f"{self.ipa}{self.liaison}‿" if self.liaison else self.ipa


@functools.lru_cache(maxsize=1)
def corrections() -> dict[str, str]:
    """The published corrections: a written form and the reading that replaces the table's."""
    out: dict[str, str] = {}
    for line in CORRECTIONS_FILE.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        form, _lemma, _category, reading, _replaced = line.split("\t")
        out[form] = reading
    return out


def to_ipa(notation: str) -> str:
    """The first variant of a reading in Morphalou's notation, in IPA; "" where a symbol is
    not one this knows."""
    phones: list[str] = []
    for symbol in notation.split(" OU ")[0].split():
        if symbol not in PHONES:
            return ""
        phones.append(PHONES[symbol])
    return "".join(phones)


def everyday(ipa: str) -> str:
    """A reading as a dictionary prints it: the final schwa after a consonant left off
    (*femme* /fam/), except in a word of one syllable (*le*, *je*)."""
    phones = _phones(ipa)
    if (
        len(phones) > 1
        and phones[-1] == "ə"
        and phones[-2] not in VOWELS
        and any(phone in VOWELS for phone in phones[:-1])
    ):
        return "".join(phones[:-1])
    return ipa


def _phones(ipa: str) -> list[str]:
    """An IPA string split into phones, a nasal vowel's tilde kept with its vowel."""
    out: list[str] = []
    for char in ipa:
        if char == "̃" and out:
            out[-1] += char
        else:
            out.append(char)
    return out


def reading(
    lexicon: morphalou.Lexicon, surface: str, lemma: str = "", pos: str = "", feats: str = ""
) -> str:
    """How a word is said alone, in IPA as the table writes it (its final schwa kept:
    `everyday` drops it), or "" where the table cannot say it with one voice.

    Readings the word's lemma, part of speech and features disagree with are dropped first
    (`Lexicon.agreeing`); what is left must be one way of saying it, or nothing is shown.
    """
    form = surface.translate(_APOSTROPHES)
    fixed = corrections().get(form.lower())
    if fixed is not None:
        return to_ipa(fixed)
    rows = lexicon.agreeing(form, lemma, pos, feats)
    misread = _MISREAD.get(form.lower())
    if misread:
        rows = [row for row in rows if row.phonetic not in misread]
    if rows:
        if len(morphalou.distinct(row.variants() for row in rows)) != 1:
            return ""
        return to_ipa(rows[0].phonetic)
    if "-" in form.strip("-"):
        return _by_parts(lexicon, form)
    return ""


def _by_parts(lexicon: morphalou.Lexicon, form: str) -> str:
    """A hyphenated compound the table has no reading for, said by its parts: each part's
    one reading, and across a hyphen the liaison the parts make (*peut-être* /pøtɛtʁ/)."""
    parts = form.split("-")
    if not all(parts):
        return ""
    said: list[str] = []
    for part in parts:
        one = reading(lexicon, part)
        if not one:
            return ""
        said.append(one)
    out = everyday(said[0])
    for at in range(1, len(parts)):
        letter = parts[at - 1][-1].lower()
        consonant = LIAISON.get(letter, "")
        if (
            consonant
            and _silent_consonant(letter, _phones(out)[-1])
            and _opens(parts[at], said[at])
        ):
            out += consonant
        out += everyday(said[at])
    return out


def _silent_consonant(letter: str, phone: str) -> bool:
    """gruut's `fr_has_silent_consonant`: whether a word's last letter goes unsaid.

    Ported from gruut (Copyright (c) 2020 Michael Hansen, MIT; the notice is in
    LICENSING.md), which credits PoemesProfonds for it."""
    if letter in {"d", "p", "t"}:
        return phone != letter
    if letter == "r":
        return phone != "ʁ"
    if letter in {"s", "x", "z"}:
        return phone not in {"s", "z"}
    if letter == "n":
        return phone not in {"n", "ŋ"}
    return False


def _opens(written: str, ipa: str) -> bool:
    """Whether a word lets a liaison in: its reading opens on a vowel (or on a glide it
    writes with a vowel letter), and it is no h aspiré."""
    written = written.lower()
    if not ipa or written in H_ASPIRE:
        return False
    first = _phones(ipa)[0]
    return first in VOWELS or (first in GLIDES and written[:1] in _VOWEL_LETTERS | {"h"})


def _aspirated(word: Word) -> bool:
    for name in (word.surface, word.lemma):
        low = (name or "").lower()
        if low in H_ASPIRE or low.rstrip("sx") in H_ASPIRE:
            return True
    return False


def liaison(
    text: str,
    before: Word | None,
    first: Word,
    second: Word,
    first_ipa: str,
    second_ipa: str,
) -> str:
    """The consonant `first` carries onto `second`, where the liaison is always made; "".

    Ported from gruut's `fr_post_process_sentence`, narrowed to the liaisons every speaker
    makes (the module's docstring says which).
    """
    if not (first_ipa and second_ipa):
        return ""
    written = first.surface.translate(_APOSTROPHES).lower()
    last = written[-1:]
    consonant = LIAISON.get(last, "")
    if not consonant or written == "et":
        return ""
    if not _silent_consonant(last, _phones(first_ipa)[-1]):
        return ""
    if _aspirated(second) or not _opens(second.surface, second_ipa):
        return ""
    gap = text[first.end : second.start]
    pos1, pos2 = first.pos or "", second.pos or ""
    if gap.strip("  ") == "" and gap:
        if (pos1 in {"DET", "NUM"} or written in ARTICLES) and pos2 in NOMINAL:
            return consonant
        if (
            pos1 == "PRON"
            and written in CLITICS
            and not _tonic(text, before, first)
            and (
                pos2 in {"VERB", "AUX"}
                or (pos2 == "PRON" and second.surface.lower() in {"en", "y"})
            )
        ):
            return consonant
        return ""
    if gap == "-" and pos1 in {"VERB", "AUX"} and second.surface.lower() in INVERTED:
        return consonant
    return ""


def _tonic(text: str, before: Word | None, pronoun: Word) -> bool:
    """A pronoun that is not leaning on a verb: inverted after one (*sont-ils*), or after
    a preposition (*chez nous*, *avec eux*)."""
    if before is None:
        return False
    gap = text[before.end : pronoun.start]
    if gap == "-":
        return True
    return (before.pos or "") == "ADP" and gap.strip() == ""


def silent(word: Word, ipa: str, linked: bool) -> tuple[int, int] | None:
    """The final consonant letters the reading leaves unsaid, as offsets into the sentence.

    Only where the reading confirms it: a word ending in consonant letters whose reading
    ends in a vowel (*petit*, *est*, *parler*; after a nasal vowel the n or m is the vowel's
    own, so *temps* keeps its m); a word whose reading stops at the first of its final
    consonants (*corps*, *fort*); and a mute e's s or nt (*femmes*, *parlent*). The e
    itself is never greyed: the card is about the consonants. A consonant carried onto the
    next word is said, and is not greyed.
    """
    if not ipa:
        return None
    letters = word.surface.translate(_APOSTROPHES).lower()
    if not letters or letters.endswith("'") or not letters.isalpha():
        return None
    phones = _phones(ipa)
    tail = len(letters)
    while tail > 0 and letters[tail - 1] not in _VOWEL_LETTERS:
        tail -= 1
    run = letters[tail:]
    if not run or tail == 0:
        return None
    start = tail
    end_phone = phones[-1]
    if end_phone in VOWELS:
        if end_phone in NASALS and run[0] in "nm":
            start += 1
    elif letters[tail - 1] == "e" and run in {"s", "nt"} and end_phone not in {"s", "z"}:
        # The mute e's consonants: *femmes* /fam/, *parlent* /paʁl/.
        if end_phone == "t" and run == "nt":
            return None
    elif len(run) > 1 and _LETTER_SAYS.get(run[0]) == end_phone:
        start += 1
    else:
        return None
    end = len(letters)
    if linked:
        end -= 1
    if start >= end:
        return None
    return (word.start + start, word.start + end)


def sentence(text: str, words: list[Word], lexicon: morphalou.Lexicon) -> list[Said]:
    """Each word of a sentence as it is said there, in the order given.

    A word that carries a liaison keeps the schwa before it: *quelques‿amis* is
    /kɛlkəz‿ami/, and only a word said alone loses it.
    """
    full = [
        reading(lexicon, word.surface, word.lemma or "", word.pos or "", word.feats or "")
        for word in words
    ]
    ipas = [everyday(one) for one in full]
    out: list[Said] = []
    for at, word in enumerate(words):
        following = words[at + 1] if at + 1 < len(words) else None
        linked = (
            liaison(
                text,
                words[at - 1] if at else None,
                word,
                following,
                ipas[at],
                ipas[at + 1],
            )
            if following is not None
            else ""
        )
        elided = word.surface.translate(_APOSTROPHES).endswith("'")
        out.append(
            Said(
                ipa=full[at] if linked else ipas[at],
                liaison=linked,
                elided=elided,
                silent=None if elided else silent(word, ipas[at], bool(linked)),
            )
        )
    return out


#: The kinds of mark the "as said" switch draws, as the page receives them.
TIE, ELIDED, SILENT = 1, 2, 3


def marks(text: str, words: list[Word], said: list[Said]) -> list[tuple[int, int, int, str]]:
    """What the switch draws over a sentence, as (start, end, kind, consonant): a tie over
    the space a liaison crosses, the apostrophe of an elision, and the silent letters."""
    out: list[tuple[int, int, int, str]] = []
    for at, (word, one) in enumerate(zip(words, said, strict=True)):
        if one.silent:
            out.append((one.silent[0], one.silent[1], SILENT, ""))
        if one.elided:
            out.append((word.end - 1, word.end, ELIDED, ""))
        if one.liaison and at + 1 < len(words):
            out.append((word.end, words[at + 1].start, TIE, one.liaison))
    return sorted(out)
