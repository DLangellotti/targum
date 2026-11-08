"""A lemma checked against the word it is the lemma of, at page-build and count time.

נשתיק, "we will silence", reached a card as התקין, "install", with the root ת־ק־ן and
"All forms of התקין" under it (David, 2026-10-31). DICTA has no השתיק in its vocabulary:
alone it returns `[BLANK]` or a near neighbour (השחית, שיתק, מתקין), and in one sentence
it returned התקין. The annotator's guard (`dicta.unrelated`, grammar/7) refuses a lemma
whose strong letters are not in the word, and counts every nun as optional because a
nun assimilates — so התקין's ת־ק־נ became ת־ק, which נשתיק spells, and the lemma went
through. Everything on the card follows the lemma: the meaning, the root, the family, the
conjugation link and the word the reader's count files it under.

The annotator's own fix waits for a rename that is happening anyway (targum-internal#590);
an annotator rename re-reads every text, about two hours of DICTA on the box. So this runs
where `verb_roots` runs: on what the annotation already says, every time a page is built
or a text's words are counted. Nothing here renames an annotator, moves `SCHEMA_VERSION`
or runs a model, and the annotation on disk keeps what the annotator said.

**The check.** The same letters-in-order test as `dicta.unrelated`, with a nun let go
only where Hebrew lets it go: first in the root (נפל → יפול, נתן → תן), or last before a
suffix's ת (נתן → נתתי). A nun in the middle or at the end of anything else stays a
letter the word has to spell. A participle's מ left on the lemma is let go as before.

**What a refused lemma becomes.** For a verb, the CC0 paradigm table's verb, where the
word as written (under its prefixes) is a form of exactly one verb there: נשתיק is a form
of הִשְׁתִּיק and of nothing else, so the card says השתיק, with the table's root and binyan.
Anywhere else the surface, as the annotator does when it refuses a lemma itself: a gap
on the card rather than the wrong word's meaning, said with confidence.

Measured on 2026-10-31 over the laptop's 212 Hebrew texts annotated by grammar/8: 116 of
89,035 verb tokens, 132 of 151,154 nouns and 21 of 26,797 adjectives carried a lemma
this refuses; 54 of the verbs take the table's verb, and every one read by hand was wrong
before (נבעלה under נאנס, נרכוש under נקנה, נפדה under נקנה).

Only DICTA's annotations (`dicta/…`): a lemma from the hand tagging of scripture is an
editor's, and this never overrules one.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, NamedTuple

from .dicta import GUARDED, SUPPLETIVE, _in_order, _strong
from .hebrew import FINALS

if TYPE_CHECKING:
    from ..models import Annotation, Token

#: The version of what this module answers. A change to the check or to what a refused
#: lemma becomes is a new number, carried by every count that reads it. 2 gives an
#: inflected verb that stands as its own lemma the table's verb, in ktiv male, past
#: ling-he's reviewed lists (targum-internal#660); 3 keeps a yod beside a mater single
#: in that ktiv male (היה, not הייה) and writes ציווה with its yod.
VERSION = 3

#: The annotator this checks: DICTA, and nothing that put a hand tagging in front of it.
DICTA = "dicta/"

_POINTS = re.compile("[֑-ׇ]")


class Mend(NamedTuple):
    """What a refused lemma becomes: the lemma, and the root and binyan that go with it
    ("" where there is none to give)."""

    lemma: str
    root: str
    binyan: str


def applies(annotator: str, language: str) -> bool:
    """Whether an annotation by `annotator` in `language` is checked here."""
    return annotator.startswith(DICTA) and language.split("-")[0].lower() == "he"


def _then(letters: str, word: str, after: str) -> bool:
    """Whether `letters` are in `word` in order with `after` straight after the last."""
    at = 0
    for char in letters:
        at = word.find(char, at) + 1
        if not at:
            return False
    return word[at : at + 1] == after


def refused(lemma: str, base: str) -> bool:
    """Whether `lemma` cannot be the lemma of `base`, the word under its prefixes."""
    if not lemma or " " in lemma or lemma in SUPPLETIVE:
        return False
    if not base or '"' in base or "'" in base:
        return False
    strong = _strong(lemma)
    word = base.translate(FINALS)
    tries = {strong}
    if strong[:1] in "נמ":
        # A first nun that assimilated (יפול, תן), or a participle's מ on the lemma.
        tries.add(strong[1:])
    if any(len(letters) < 2 for letters in tries):
        return False
    if any(_in_order(letters, word) for letters in tries):
        return False
    # A last nun taken into a suffix's ת: נָתַתִּי is נתן's.
    return not (len(strong) > 2 and strong[-1] == "נ" and _then(strong[:-1], word, "ת"))


def _table_verb(base: str) -> tuple[str, str] | None:
    """The one verb of the CC0 table `base` is a form of, as (bare lemma, binyan)."""
    from .paradigms import bare, table

    book = table()
    found = book.by_form.get(base) or ()
    lemmas = {bare(book.verbs[lid].lemma) for lid in found if lid in book.verbs}
    if len(lemmas) != 1:
        return None
    binyans = {book.binyan_of(lid) for lid in found}
    binyan = binyans.pop() if len(binyans) == 1 else None
    return lemmas.pop(), binyan or ""


#: What DICTA's features say, as the CC0 table's form features say it: the tense and the
#: number. Not the person, which a future's prefix leaves open (תריעו is "you" and "they,
#: feminine") and DICTA reads as one of them.
_SAID = {
    "Tense=Past": "past",
    "Tense=Fut": "future",
    "Tense=Pres": "present",
    "Mood=Imp": "imperative",
    "VerbForm=Inf": "infinitive",
    "Number=Sing": "singular",
    "Number=Plur": "plural",
}

#: The tsere a hif'il's short future carries where its hiriq-yod was: תָּרֵעוּ is תָּרִיעוּ
#: written short, and the table spells only the long form.
TSERE = "\u05b5"
#: A future's prefixes, and the marks a nif'al future puts on them: a tsere before a
#: guttural that cannot double (יֵאָמֵר), or a hiriq with the next letter doubled
#: (יִכָּנֵס). A qal of a first-nun root doubles too (יִפֹּל) and is refused with them: a gap
#: on the card rather than a guess.
FUTURE_PREFIXES = frozenset("אתינ")
HIRIQ = "\u05b4"
DAGESH = "\u05bc"


def _nifal_future(letters: list[tuple[str, str]]) -> bool:
    """Whether a pointed word's prefix carries a nif'al future's marks."""
    if len(letters) < 2 or letters[0][0] not in FUTURE_PREFIXES:
        return False
    prefix, after = letters[0][1], letters[1][1]
    return TSERE in prefix or (HIRIQ in prefix and DAGESH in after)


def _marked(surface: str) -> list[tuple[str, str]]:
    """Each letter of a word with the marks on it."""
    letters: list[tuple[str, str]] = []
    for char in surface or "":
        if "\u0591" <= char <= "\u05c7" and letters:
            letters[-1] = (letters[-1][0], letters[-1][1] + char)
        elif "א" <= char <= "ת":
            letters.append((char, ""))
    return letters


def _plene(surface: str, lead: int) -> str | None:
    """The word under its prefixes with a yod after its first tsere past the prefix,
    where a letter follows it: the hif'il future's spelling the table holds (תָּרֵעוּ →
    תריעו). None where there is no such tsere."""
    letters = _marked(surface)
    letters = letters[lead:] if 0 < lead < len(letters) else letters
    # Never where the marks show a nif'al future, whose own tsere before the last letter
    # (יֵאָמֵר) is no hiriq-yod written short.
    if not letters or _nifal_future(letters):
        return None
    for at, (_letter, marks) in enumerate(letters[:-1]):
        if at and TSERE in marks and letters[at + 1][0] != "י":
            spelled = [one for one, _ in letters]
            return "".join([*spelled[: at + 1], "י", *spelled[at + 1 :]])
    return None


#: Letters that are an inflected verb and, unpointed, more often a common noun: modern
#: prose has DICTA tag the noun VERB (ling-he on targum#1135, 2026-11-08). Each moves only
#: where the marks show the verb's qal past: a qamats on the first letter, a shva or a
#: hataf on the second (יָלְדָה, וְהָלְכָה), which none of the nouns has (עֻבְדָּה "fact",
#: שְׁאֵלָה "question", נְשָׁמָה "soul", יַלְדָּה "girl", הֲלָכָה, נְקֵבָה "female").
NOUN_HOMOGRAPHS = frozenset({"עבדה", "שאלה", "נשמה", "ילדה", "הלכה", "נקבה"})
QAMATS = "\u05b8"
SHVA_OR_HATAF = frozenset("\u05b0\u05b1\u05b2\u05b3")

#: Letters that keep their gap whatever the table says (ling-he on targum#1135): מְשַׁנֶּה
#: is pi'el שינה, not שנה's (qal's present is שׁוֹנֶה), and is the Mishnah itself; מְקַדֵּשׁ
#: is pi'el קידש, not הקדיש; הוקרן and הוברר are hof'al forms the table files under a
#: lemma no reader writes.
KEPT_GAPS = frozenset({"משנה", "מקדש", "הוקרן", "הוברר"})

#: Letters that move only when pointed exactly so: נעשה is almost always the nif'al נַעֲשָׂה
#: or נַעֲשֶׂה "is done", and only נַעֲשֶׂה "we will do" is עשה's.
POINTED_ONLY = {"נעשה": "\u05e0\u05b7\u05e2\u05b2\u05e9\u05c2\u05b6\u05d4"}

#: Marks that say nothing about the reading: cantillation, meteg, the sin and shin dots
#: are kept (they are letters' own), the rest compared.
_CANTILLATION = re.compile("[\u0591-\u05af\u05bd]")


def _vowels_of(letters: list[tuple[str, str]]) -> str:
    return _CANTILLATION.sub("", "".join(letter + marks for letter, marks in letters))


def _confirmed(base: str, under: list[tuple[str, str]]) -> bool:
    """Whether the reviewed letters may move here (`NOUN_HOMOGRAPHS`, `POINTED_ONLY`)."""
    if base in POINTED_ONLY:
        import unicodedata

        wanted = unicodedata.normalize("NFC", POINTED_ONLY[base])
        return unicodedata.normalize("NFC", _vowels_of(under)) == wanted
    if base in NOUN_HOMOGRAPHS:
        return len(under) > 1 and QAMATS in under[0][1] and bool(set(under[1][1]) & SHVA_OR_HATAF)
    return True


#: A consonantal vav or yod inside a pointed word, which ktiv male doubles (הִתְכַּוֵּן →
#: התכוון, קִיֵּם → קיים); a qubuts, which it writes with a vav (הֻקְדַּשׁ → הוקדש); and a
#: hiriq before a doubled letter, which it writes with a yod (בִּקֵּשׁ → ביקש).
_VOWELS = frozenset("\u05b0\u05b1\u05b2\u05b3\u05b4\u05b5\u05b6\u05b7\u05b8\u05bb")


def male(pointed: str) -> str:
    """A pointed lemma in ktiv male, the spelling the rest of the shelf files lemmas in
    (ling-he on targum#1135: התכוון, not the table's התכון). The Academy's rules a verb's
    citation form needs: a consonantal vav inside the word is doubled (הִרְוָה → הרווה); a
    consonantal yod too, but not beside a mater (הָיָה → היה, שֻׁיַּךְ → שויך); a qubuts is
    written with a vav (הֻקְדַּשׁ → הוקדש); and a hiriq before a doubled letter with a yod,
    a doubled vav included (בִּקֵּשׁ → ביקש, צִוָּה → ציווה). Anything else keeps its
    letters."""
    letters = _marked(pointed)
    out: list[str] = []
    #: Whether the last letter written is a mater: a vav or yod standing for a vowel.
    mater = False
    for at, (letter, marks) in enumerate(letters):
        nxt = letters[at + 1] if at + 1 < len(letters) else None
        inner = 0 < at < len(letters) - 1
        consonant = bool(set(marks) & _VOWELS) or (letter == "י" and DAGESH in marks)
        if letter == "ו" and DAGESH in marks and not set(marks) & _VOWELS:
            consonant = False  # a shuruq
        if letter in "וי" and inner and consonant and out[-1:] != [letter]:
            # A yod beside a mater is not doubled: before a last ה or א, or after a vowel
            # letter.
            beside = mater or (nxt is not None and at + 1 == len(letters) - 1 and nxt[0] in "הא")
            if letter == "ו" or not beside:
                out.append(letter + letter)
                mater = False
                continue
        out.append(letter)
        mater = letter in "וי" and not consonant
        if "\u05bb" in marks:
            out.append("ו")
            mater = True
        elif HIRIQ in marks and nxt is not None and DAGESH in nxt[1] and nxt[0] != "י":
            if at > 0 or letter not in "הנ":
                out.append("י")
                mater = True
    return "".join(out)


def _lemma_male(found: list[str], book: Any) -> str | None:
    """The one ktiv male lemma of `found`'s verbs, where they agree; where they do not, the
    bare one among them (the qal הלך beside the pi'el הילך); else None."""
    from .paradigms import bare

    spelled = {male(book.verbs[lid].lemma) for lid in found}
    if len(spelled) == 1:
        return spelled.pop()
    plain = {bare(book.verbs[lid].lemma) for lid in found}
    return next(iter(plain & spelled), None) if len(plain) == 1 else None


def _inflected_verb(surface: str, base: str, lead: int, feats: str) -> tuple[str, str] | None:
    """The one verb of the CC0 table an inflected verb is a form of, as (lemma in ktiv
    male, binyan), where the annotator gave the word itself as its lemma (targum-internal#660:
    תרעו under תרעו rather than הריע). The table's form must say what DICTA said of the
    word, its tense and number, so a Mishnaic future יבאו is not filed under the
    past of יבא. None where DICTA said no tense, or the forms find no verb or more than
    one, or only the word itself."""
    from .paradigms import bare, table

    marked = _marked(surface)
    under = marked[lead:] if 0 < lead < len(marked) else marked
    if base in KEPT_GAPS or not _confirmed(base, under):
        return None
    if "Tense=Fut" in (feats or "") and _nifal_future(under):
        # A nif'al the table is not asked about: יֵאָמֵר is not אָמַר's.
        return None
    said = {_SAID[part] for part in (feats or "").split("|") if part in _SAID}
    if not said & {"past", "future", "present", "imperative", "infinitive"}:
        return None
    book = table()
    # The long spelling first where the marks show a hif'il's tsere: pointed תָּרֵעוּ is
    # הריע's, though unpointed תרעו is also רעה's "you will graze".
    for spelled in dict.fromkeys(one for one in (_plene(surface, lead), base) if one):
        found = [
            lid
            for lid in book.by_form.get(spelled) or ()
            if lid in book.verbs
            and any(
                bare(form.written) == spelled and said <= set(form.features)
                for form in book.verbs[lid].forms
            )
        ]
        lemmas = {bare(book.verbs[lid].lemma) for lid in found}
        if len(lemmas) != 1:
            continue
        verb = _lemma_male(found, book)
        if verb is None or verb == base:
            return None
        binyans = {book.binyan_of(lid) for lid in found}
        binyan = binyans.pop() if len(binyans) == 1 else None
        return verb, binyan or ""
    return None


def checked(
    lemma: str, surface: str, lead: int, pos: str | None, feats: str | None = None
) -> Mend | None:
    """What a token's lemma becomes, or None where it stands.

    `lead` is how many letters of `surface` DICTA cut off as prefixes (`Syntax.lead`);
    `feats` the features it read on the word, which an inflected verb standing as its own
    lemma is matched on (`_inflected_verb`).
    """
    if pos not in GUARDED:
        return None
    word = _POINTS.sub("", surface or "")
    base = word[lead:] if 0 < lead < len(word) else word
    lemma = lemma or ""
    # A gap already: the annotator gave the word itself. A verb whose form the table
    # knows takes the table's verb; anything else stays the gap it is.
    if lemma in (word, word.lower(), base):
        if pos != "VERB":
            return None
        found = _inflected_verb(surface, base, lead, feats or "")
        if found is None:
            return None
        from .verb_roots import root_for

        verb, binyan = found
        return Mend(verb, root_for(verb, None, "VERB"), binyan)
    if not refused(lemma, base):
        return None
    if pos == "VERB":
        found = _table_verb(base)
        if found is not None:
            from .verb_roots import root_for

            verb, binyan = found
            return Mend(verb, root_for(verb, None, "VERB"), binyan)
    return Mend(word.lower(), "", "")


def mend_token(token: Token) -> Token:
    """The token with its lemma checked; the same object where nothing changes."""
    lead = token.syntax.lead if token.syntax is not None else 0
    mend = checked(token.lemma, token.surface, lead, token.pos, token.feats)
    if mend is None:
        return token
    return token.model_copy(
        update={
            "lemma": mend.lemma,
            "root": mend.root or None,
            "binyan": mend.binyan or None,
            # Each of these was the refused word's, not this one's.
            "headword": None,
            "lexeme": None,
            "word_register": None,
        }
    )


def mended(annotation: Annotation) -> Annotation:
    """The annotation with every lemma checked; the same object where nothing changes,
    and where the annotation is not DICTA's Hebrew."""
    if not applies(annotation.annotator, annotation.language):
        return annotation
    changed = False
    tokens: dict[str, list[Token]] = {}
    for segment_id, run in annotation.tokens.items():
        out = [mend_token(token) for token in run]
        changed = changed or any(new is not old for new, old in zip(out, run, strict=True))
        tokens[segment_id] = out
    if not changed:
        return annotation
    return annotation.model_copy(update={"tokens": tokens})


def mend_row(row: dict[str, Any]) -> dict[str, Any]:
    """A token as `annotation.json` stores it, with its lemma checked: for the counts,
    which read the file rather than the model. The same dict where nothing changes."""
    syntax = row.get("syntax") or {}
    mend = checked(
        str(row.get("lemma") or ""),
        str(row.get("surface") or ""),
        int(syntax.get("lead") or 0),
        row.get("pos"),
        str(row.get("feats") or ""),
    )
    if mend is None:
        return row
    return row | {"lemma": mend.lemma, "root": mend.root or None, "binyan": mend.binyan or None}
