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
suffix's ת (נתן → נתתי), or both (נתן → לתת). A nun in the middle or at the end of
anything else stays a letter the word has to spell. A participle's מ left on the lemma
is let go as before.

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

from .dicta import GUARDED, PLURAL_LEMMAS, SUPPLETIVE, _in_order, _strong
from .hebrew import FINALS

if TYPE_CHECKING:
    from ..models import Annotation, Token

#: The version of what this module answers. A change to the check or to what a refused
#: lemma becomes is a new number, carried by every count that reads it. 2 gives an
#: inflected verb that stands as its own lemma the table's verb, in ktiv male, past
#: ling-he's reviewed lists (targum-internal#660); 3 keeps a yod beside a mater single
#: in that ktiv male (היה, not הייה) and writes ציווה with its yod; 4 gives a participle's
#: מ and an infinitive's ל that DICTA cut off as a prefix back to the word
#: (`own_letter`, targum-internal#689); 5 checks a lemma of one strong letter and an
#: auxiliary's, files an unpointed qal future under its qal rather than its nif'al, a verb
#: whose lemma is another of its forms under its verb, a whole infinitive under its verb, an
#: adjective that is a participle under the participle, and a short list of closed-class
#: words under their own lemma (targum-internal#697, #699); 6 takes a prefix the line
#: already shows off the lemma, keeps a fixed word (היום, הכי, למשל) and של's pronoun
#: whole, gives an auxiliary and אין no binyan or root, files מציע under הציע of
#: י־צ־ע, checks a name's lemma, and gives a title's split-off letter the title's
#: (targum-internal#698, #700, #702).
VERSION = 6

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


#: The parts of speech whose lemma is checked: DICTA's guarded ones and the auxiliary,
#: whose היו came back under יש and אין (targum-internal#697).
CHECKED = GUARDED | {"AUX"}
#: What a verb's lemma of one strong letter may leave out of a form: a vav or a yod, a
#: last he (הָיָה, הָיִיתִי), and the hif'il's first he (הֵבִיא, אָבִיא).
_ONE_WEAK = frozenset("וי")


def _one_letter_refused(lemma: str, word: str, pos: str | None) -> bool:
    """Whether a lemma of fewer than two strong letters cannot be `word`'s: its letters
    but a vav or a yod, a last he, and a verb's first he must be in the word in order
    (targum-internal#697). `dicta.unrelated` lets these by whatever the word, so היה came
    back under הביא, היו under יש and אין, and טוב under בא, whose ב is in it."""
    letters = lemma.translate(FINALS)
    if len(letters) > 3 and letters.endswith(PLURAL_LEMMAS):
        letters = letters[:-2]
    if len(letters) > 1 and letters[-1] == "ה":
        letters = letters[:-1]
    letters = "".join(char for char in letters if char not in _ONE_WEAK)
    if pos in ("VERB", "AUX") and len(letters) > 1 and letters[0] == "ה":
        letters = letters[1:]
    if not letters:
        return False
    tries = {letters, letters[1:]} if letters[0] == "נ" and len(letters) > 1 else {letters}
    return not any(_in_order(one, word) for one in tries)


def refused(lemma: str, base: str, pos: str | None = None) -> bool:
    """Whether `lemma` cannot be the lemma of `base`, the word under its prefixes."""
    if not lemma or " " in lemma or lemma in SUPPLETIVE:
        return False
    if not base or '"' in base or "'" in base:
        return False
    strong = _strong(lemma)
    word = base.translate(FINALS)
    if len(strong) < 2:
        return _one_letter_refused(lemma, word, pos)
    tries = {strong}
    if strong[:1] in "נמ":
        # A first nun that assimilated (יפול, תן), or a participle's מ on the lemma.
        tries.add(strong[1:])
    if any(len(letters) < 2 for letters in tries):
        return False
    if any(_in_order(letters, word) for letters in tries):
        return False
    # A last nun taken into a ת after it: נָתַתִּי is נתן's, and so is לָתֵת, which drops
    # both its nuns.
    if len(strong) < 3:
        return True
    return not any(letters[-1] == "נ" and _then(letters[:-1], word, "ת") for letters in tries)


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


#: The words after a verb that make it active: the object marker with its pronoun, or a
#: dative pronoun before a noun ("לא אשכח אותך", "אמצא לך חדר"). A nif'al takes neither.
OBJECTS = frozenset({"את", "אותי", "אותך", "אותו", "אותה", "אותנו", "אתכם", "אתכן", "אותם", "אותן"})
DATIVES = frozenset({"לי", "לך", "לו", "לה", "לנו", "לכם", "לכן", "להם", "להן"})


def object_after(after: list[tuple[str, str | None]]) -> bool:
    """Whether the words after a verb, as (surface, part of speech), open on its object:
    the object marker, or a dative pronoun and then a noun."""
    if not after:
        return False
    first = _POINTS.sub("", after[0][0])
    if first in OBJECTS:
        return True
    return first in DATIVES and len(after) > 1 and after[1][1] in ("NOUN", "PROPN")


def _verbs_of(spelled: str, wanted: set[str] | None = None) -> set[str]:
    """The table's verbs `spelled` is a form of: one whose features hold `wanted`, where
    given."""
    from .paradigms import bare, table

    book = table()
    return {
        lid
        for lid in book.by_form.get(spelled) or ()
        if lid in book.verbs
        and any(
            bare(form.written) == spelled and (wanted is None or wanted <= set(form.features))
            for form in book.verbs[lid].forms
        )
    }


def _qal_future(
    lemma: str, surface: str, base: str, lead: int, feats: str, objected: bool
) -> tuple[str, str] | None:
    """The qal an unpointed future DICTA filed under its nif'al is, as (lemma in ktiv male,
    binyan) (targum-internal#697: תשכח under נשכח, "be forgotten"). Ktiv male writes a
    nif'al future's yod after ת, י and נ (תישכח, יימצא), so where the table reads the
    letters as the qal's future and not the nif'al's, they are the qal's. After א the
    nif'al writes none (אשכח is both), and there an object after the verb settles it, as
    it does wherever the table reads both. Pointed, the marks show a nif'al (`_nifal_future`)."""
    from .paradigms import bare, table

    letters = lemma.translate(FINALS)
    if "Tense=Fut" not in feats or len(letters) != 4 or letters[0] != "נ":
        return None
    marked = _marked(surface)
    under = marked[lead:] if 0 < lead < len(marked) else marked
    if _nifal_future(under):
        return None
    book = table()
    found = _verbs_of(base, {"future"})
    qal = [lid for lid in found if bare(book.verbs[lid].lemma) == lemma[1:]]
    nifal = [lid for lid in found if bare(book.verbs[lid].lemma) == lemma]
    if not qal or (nifal and not objected):
        return None
    verb = _lemma_male(qal, book)
    if verb is None:
        return None
    binyans = {book.binyan_of(lid) for lid in qal}
    binyan = binyans.pop() if len(binyans) == 1 else None
    return verb, binyan or ""


def _infinitive(base: str, surface: str, feats: str) -> tuple[str, str] | None:
    """The verb a ל-word with no person, gender or tense is the infinitive of, by its
    marks or its letters (`own_letter.infinitive_of`)."""
    from .own_letter import _FINITE, infinitive_of

    if not base.startswith("ל") or any(part in feats for part in _FINITE):
        return None
    return infinitive_of(base, surface)


def _same_lemma(said: str, verb: str) -> bool:
    """Whether DICTA's lemma is the table's verb's, in any of the ways ktiv male writes it."""
    from .own_letter import _same_word

    return _same_word(said, verb)


def _lemma_of_form(
    lemma: str, surface: str, base: str, lead: int, feats: str
) -> tuple[str, str] | None:
    """The verb a lemma that is another form of it stands for, as (lemma in ktiv male,
    binyan) (targum-internal#697, #699): תשאלי under the present שואל, רציתי under רוצה,
    אבדוק under the future יבדוק. The lemma and the word must both be forms of exactly one
    verb of the table, and the lemma none's own. Only where DICTA read a past, a future or
    an imperative, or the word is an infinitive: a present keeps its participle, the wrong
    headword with the right meaning (#490), and a word with no tense said is left alone."""
    from .own_letter import _FINITE
    from .paradigms import bare, table

    infinitive = _infinitive(base, surface, feats)
    shaped = base.startswith("ל") and not any(part in feats for part in _FINITE)
    if not shaped and not any(f"Tense={tense}" in feats for tense in ("Past", "Fut", "Imp")):
        return None
    book = table()
    as_lemma = _verbs_of(lemma)
    if not as_lemma:
        return None
    as_word = _verbs_of(base)
    marked = _marked(surface)
    under = marked[lead:] if 0 < lead < len(marked) else marked
    if any(marks for _, marks in under):
        from .own_letter import _male

        as_word |= _verbs_of(_male(under))
    if infinitive is not None:
        as_word |= {
            lid
            for lid in as_lemma
            if _same_lemma(infinitive[0], male(book.verbs[lid].lemma))
            or bare(book.verbs[lid].lemma) == infinitive[0]
        }
    both = sorted(as_lemma & as_word)
    if not both:
        return None
    if any(lemma in (bare(book.verbs[lid].lemma), male(book.verbs[lid].lemma)) for lid in both):
        return None
    verb = _lemma_male(both, book)
    if verb is None or _same_lemma(lemma, verb):
        return None
    binyans = {book.binyan_of(lid) for lid in both}
    binyan = binyans.pop() if len(binyans) == 1 else None
    return verb, binyan or ""


#: The participle's מ.
MEM = "מ"


def _participle_adjective(lemma: str, surface: str, base: str, lead: int) -> str | None:
    """The participle an adjective is, where DICTA filed it under its verb's past
    (targum-internal#699: מכובד under כובד, "weight", מצוין under צוין, "was noted"). The
    word must be a present of a verb of the table whose lemma is DICTA's; the lemma is then
    that verb's masculine singular present, in ktiv male: the adjective's own."""
    from .own_letter import _holam_male
    from .own_letter import _male as own_male
    from .paradigms import bare, table

    if not base.startswith(MEM) or len(base) < 4:
        return None
    marked = _marked(surface)
    under = marked[lead:] if 0 < lead < len(marked) else marked
    pointed = any(marks for _, marks in under)
    book = table()
    found = _verbs_of(base, {"present"})
    if pointed:
        found |= _verbs_of(own_male(under), {"present"})
    said = [
        lid
        for lid in found
        if lemma
        in {
            bare(book.verbs[lid].lemma),
            male(book.verbs[lid].lemma),
            own_male(_marked(book.verbs[lid].lemma)),
            "".join(one for one, _ in _holam_male(_marked(book.verbs[lid].lemma))),
        }
    ]
    spelled = set()
    for lid in said:
        for form in book.verbs[lid].forms:
            if {"present", "masculine", "singular"} <= set(form.features) and not form.ruled:
                units = _marked(form.written)
                spelled.add(own_male(units) if any(m for _, m in units) else bare(form.written))
    if len(spelled) != 1:
        return None
    adjective = spelled.pop()
    return adjective if adjective != lemma and adjective.startswith(MEM) else None


#: The auxiliary verbs a refused or inflected auxiliary may be filed under: היו came
#: back under יש and אין, and נהיה, "we will be", stood as its own lemma.
AUXILIARIES = frozenset({"היה"})


def checked(
    lemma: str,
    surface: str,
    lead: int,
    pos: str | None,
    feats: str | None = None,
    objected: bool = False,
) -> Mend | None:
    """What a token's lemma becomes, or None where it stands.

    `lead` is how many letters of `surface` DICTA cut off as prefixes (`Syntax.lead`);
    `feats` the features it read on the word, which an inflected verb standing as its own
    lemma is matched on (`_inflected_verb`); `objected` whether an object follows the
    word (`object_after`), which settles a first-person future between qal and nif'al.
    """
    if pos == "PROPN":
        return _name(lemma or "", surface, lead)
    if pos not in CHECKED:
        return None
    feats = feats or ""
    word = _POINTS.sub("", surface or "")
    base = word[lead:] if 0 < lead < len(word) else word
    lemma = lemma or ""
    if pos == "VERB" and lemma in PARTICIPLE_HEADWORDS:
        return Mend(*PARTICIPLE_HEADWORDS[lemma])
    # A gap already: the annotator gave the word itself. A verb whose form the table
    # knows takes the table's verb; anything else stays the gap it is.
    if lemma in (word, word.lower(), base):
        if pos not in ("VERB", "AUX"):
            return None
        found = _infinitive(base, surface, feats) if pos == "VERB" else None
        if found is None:
            found = _inflected_verb(surface, base, lead, feats)
        if found is None or (pos == "AUX" and found[0] not in AUXILIARIES):
            return None
        return _verb_mend(found, pos)
    if not refused(lemma, base, pos):
        if pos == "VERB":
            found = _qal_future(lemma, surface, base, lead, feats, objected)
            if found is None:
                found = _lemma_of_form(lemma, surface, base, lead, feats)
            return _verb_mend(found, pos) if found is not None else None
        if pos == "ADJ":
            adjective = _participle_adjective(lemma, surface, base, lead)
            return Mend(adjective, "", "") if adjective is not None else None
        return None
    if pos in ("VERB", "AUX"):
        found = _table_verb(base)
        if found is not None and (pos == "VERB" or found[0] in AUXILIARIES):
            return _verb_mend(found, pos)
    return Mend(word.lower(), "", "")


#: Participles DICTA files a verb under, with a root read off the participle's own
#: letters: מציע came out of י־ע־ץ, "advise", where it is הציע of י־צ־ע, "offer", as
#: הציע itself is (targum-internal#700).
PARTICIPLE_HEADWORDS: dict[str, tuple[str, str, str]] = {"מציע": ("הציע", "יצע", "הפעיל")}


def _name(lemma: str, surface: str, lead: int) -> Mend | None:
    """A name whose lemma is another word, put back to the name under its prefixes
    (targum-internal#702: ללאו under ללא "without", קירשנבל under היפוגליקמיה). The
    letters test `refused` makes of any lemma; an abbreviation's lemma (ד"ר) is left
    alone, since its letters are not the word's."""
    word = _POINTS.sub("", surface or "")
    base = word[lead:] if 0 < lead < len(word) else word
    if not lemma or lemma in (word, base) or '"' in lemma or "'" in lemma:
        return None
    return Mend(base, "", "") if refused(lemma, base, "PROPN") else None


def _verb_mend(found: tuple[str, str], pos: str | None) -> Mend:
    """The table's verb as a mend: with its root and binyan on a verb, bare on an
    auxiliary, which the page gives neither."""
    verb, binyan = found
    if pos == "AUX":
        return Mend(verb, "", "")
    from .verb_roots import root_for

    return Mend(verb, root_for(verb, None, "VERB"), binyan)


def _upos(feats: str | None, pos: str) -> str:
    """`feats` saying `pos` as its part of speech (`hebrew.kept_feats` leads with it)."""
    rest = [part for part in (feats or "").split("|") if part and not part.startswith("UPOS=")]
    return "|".join([f"UPOS={pos}", *rest])


def _given_back(token: Token) -> Token:
    """The token with a participle's מ or an infinitive's ל that DICTA cut off given back
    to it (`own_letter`, targum-internal#689); the same object where nothing changes."""
    from .own_letter import own_letter

    syntax = token.syntax
    if syntax is None or not syntax.lead:
        return token
    own = own_letter(
        token.surface,
        token.lemma,
        token.pos,
        token.built,
        syntax.lead,
        syntax.prefixes,
        token.feats,
    )
    if own is None:
        return token
    update: dict[str, Any] = {
        "built": own.built,
        "split": own.built is not None,
        "pos": own.pos,
        "feats": _upos(token.feats, own.pos),
        "syntax": syntax.model_copy(update={"lead": own.lead}),
    }
    if own.lemma and own.lemma != token.lemma:
        # The table's verb, with its root and binyan; each of the rest was the other word's.
        update |= {
            "lemma": own.lemma,
            "root": own.root or None,
            "binyan": own.binyan or None,
            "headword": None,
            "lexeme": None,
            "word_register": None,
        }
    elif own.lemma and token.pos != own.pos:
        # The same lemma, a verb now: the table's root and binyan, where the noun had none.
        update |= {"root": token.root or own.root or None, "binyan": own.binyan or None}
    return token.model_copy(update=update)


#: Closed-class words DICTA files under another word of the same letters, and what each
#: is (targum-internal#697, ling-he's read of 2026-11-13). Keyed by the word under its
#: prefixes, the part of speech DICTA gave and the lemma it gave; to the lemma, and the
#: part of speech where it changes. יכול is "able", not יכולת "ability"; ליד is
#: "beside", not יד "hand"; בינינו is בין's, not ביניים "interim"; נוכל, "we will be
#: able", is יכול's, not "swindler"; אותה before a noun, "the same", is no "you
#: (feminine)", which DICTA's pronoun reading of it gave.
#: יָכוֹל and its forms, which DICTA files under יכולת, "ability", as often as not.
ABLE = (
    "יכול",
    "יכולה",
    "יכולים",
    "יכולות",
    "יכולתי",
    "יכלה",
    "יכלו",
    "יוכל",
    "תוכל",
    "תוכלי",
    "תוכלו",
    "יוכלו",
    "נוכל",
)
CLOSED_CLASS: dict[tuple[str, str, str], tuple[str, str]] = {
    ("ליד", "ADP", "יד"): ("ליד", "ADP"),
    ("בינינו", "ADP", "ביניים"): ("בין", "ADP"),
    ("נוכל", "AUX", "נוכל"): ("יכול", "AUX"),
    ("נוכל", "VERB", "נוכל"): ("יכול", "AUX"),
    **{(able, pos, "יכולת"): ("יכול", "AUX") for able in ABLE for pos in ("AUX", "VERB")},
    ("אותו", "PRON", "את"): ("אותו", "PRON"),
    ("אותה", "PRON", "את"): ("אותו", "PRON"),
    ("אותם", "PRON", "את"): ("אותו", "PRON"),
    ("אותן", "PRON", "את"): ("אותו", "PRON"),
}
#: אפשר with no person or tense is "possible", not the pi'el אִפְשֵׁר "enabled", which a
#: segol under its alef rules out where the word is pointed.
POSSIBLE = "אפשר"
SEGOL = "\u05b6"


def closed_class(
    surface: str, lemma: str, pos: str | None, built: str | None, lead: int, feats: str
) -> tuple[str, str, bool] | None:
    """What a closed-class word DICTA filed under another word becomes, as (lemma, part
    of speech, whether its split comes off); None where it stands."""
    word = _POINTS.sub("", surface or "")
    base = word[lead:] if 0 < lead < len(word) else word
    found = CLOSED_CLASS.get((base, pos or "", lemma))
    if found is None and lemma == "יד" and pos == "ADP" and word == "ליד":
        # DICTA cut it "ל to + יד" as often as not.
        found = ("ליד", "ADP")
    if found is not None:
        whole = word == "ליד" and lead > 0 and (built or "").startswith("ל ")
        return found[0], found[1], whole
    if base == POSSIBLE and lemma == POSSIBLE and pos == "VERB":
        if any(part in feats for part in ("Person=", "Tense=")):
            return None
        marked = _marked(surface)
        if any(marks for _, marks in marked) and SEGOL not in marked[0][1]:
            return None
        return POSSIBLE, "AUX", False
    return None


def _closed(token: Token) -> Token:
    """`closed_class` on a token; the same object where nothing changes."""
    lead = token.syntax.lead if token.syntax is not None else 0
    found = closed_class(
        token.surface, token.lemma, token.pos, token.built, lead, token.feats or ""
    )
    if found is None:
        return token
    lemma, pos, whole = found
    update: dict[str, Any] = {"lemma": lemma, "pos": pos, "feats": _upos(token.feats, pos)}
    if lemma != token.lemma:
        update |= {"headword": None, "lexeme": None, "word_register": None}
    if pos != token.pos:
        update |= {"binyan": None, "root": None}
    if whole and token.syntax is not None:
        update |= {
            "built": None,
            "split": False,
            "syntax": token.syntax.model_copy(update={"lead": 0}),
        }
    return token.model_copy(update=update)


def _row_closed(row: dict[str, Any]) -> dict[str, Any]:
    """`_closed` for a stored row; the same dict where nothing changes."""
    syntax = row.get("syntax") or {}
    found = closed_class(
        str(row.get("surface") or ""),
        str(row.get("lemma") or ""),
        row.get("pos"),
        row.get("built"),
        int(syntax.get("lead") or 0),
        str(row.get("feats") or ""),
    )
    if found is None:
        return row
    lemma, pos, whole = found
    out = row | {"lemma": lemma, "pos": pos, "feats": _upos(row.get("feats"), pos)}
    if pos != row.get("pos"):
        out |= {"binyan": None, "root": None}
    if whole:
        out |= {"built": None, "split": False, "syntax": syntax | {"lead": 0}}
    return out


#: Words DICTA cuts that are one word: "today", "most", "for example", "sometimes", "at
#: all" (targum-internal#698). To the parts of speech the word is that one in, where it
#: is another in some other: הַיּוֹם the noun is "the day" and keeps its ה.
WHOLE_WORDS: dict[str, frozenset[str] | None] = {
    "היום": frozenset({"ADV"}),
    "הכי": None,
    "למשל": None,
    "לפעמים": None,
    "בכלל": frozenset({"ADV"}),
}
#: של, which with a pronoun on the end is never ש "that" + ל "to" (שלכן).
OF = "של"
PRONOUN_END = "with a pronoun on the end"


def reshaped(
    surface: str,
    lemma: str,
    pos: str | None,
    built: str | None,
    lead: int,
    title: str = "",
    prefixes: tuple[str, ...] | list[str] = (),
) -> dict[str, Any] | None:
    """What a token's lemma and line become where DICTA cut a word that is one, kept a
    prefix on the lemma that the line already shows, or split a title; None where they
    stand (targum-internal#698, #702). The keys are `lemma`, `built` and `lead`.

    `title` is the lemma of the word before, where that word is the start of a title
    whose abbreviation this token finishes (ד, then ר of ד״ר)."""
    word = _POINTS.sub("", surface or "")
    if word in WHOLE_WORDS:
        kinds = WHOLE_WORDS[word]
        if (kinds is None or pos in kinds) and (lemma != word or built or lead):
            return {"lemma": word, "built": None, "lead": 0}
        return None
    pieces = (built or "").split(" + ")
    if lemma == OF and lead and pieces[:2] == ["ש that", "ל to"] and pieces[-1] == PRONOUN_END:
        return {"lemma": OF, "built": f"{word} + {PRONOUN_END}", "lead": 0}
    if title and len(word) == 1 and '"' in title:
        return {"lemma": title, "built": built, "lead": lead}
    base = word[lead:] if 0 < lead < len(word) else word
    if (
        lead
        and built
        and lemma == word
        and base != word
        and len(base) > 1
        and _cut_as_said(surface, word, lead, prefixes)
    ):
        # The line shows the prefixes already: ה the + שיניים under השיניים.
        return {"lemma": base, "built": built, "lead": lead}
    return None


#: Words whose first letter DICTA cut as a prefix and is the word's own, as the laptop's
#: scenes point them: הֶרְגֵּל "habit", הֲפָרָה "breach", הֲכָנוֹת "preparations", וָרֹד
#: "pink", וַעַד "committee".
KEEP_WHOLE = frozenset({"הרגל", "הפרה", "הכנות", "ורוד", "ועד", "ועדה"})
#: The marks under a cut ה or ו that say it is no article or conjunction: a hataf or a
#: shva under ה (הֲפָרָה), a patach, qamats or hataf under ו (וַעַד, וָרֹד).
_NOT_ARTICLE = frozenset("\u05b0\u05b1\u05b2\u05b3")
_NOT_AND = frozenset("\u05b7\u05b8\u05b1\u05b2\u05b3")


def _cut_as_said(surface: str, word: str, lead: int, prefixes: tuple[str, ...] | list[str]) -> bool:
    """Whether DICTA's cut of a word it gave whole as its lemma stands as the prefixes it
    says: the article, the conjunction or ש, each tagged, and none a preposition. A ב, ל,
    מ or כ in front is a fixed phrase as often as not (בסדר, בבקשה, מחוץ, לרוב), and the
    whole word is the lemma DICTA meant; so is one in `KEEP_WHOLE`. Pointed, the cut ה
    and ו must carry the article's and the conjunction's vowels."""
    if not prefixes or "ADP" in prefixes or word in KEEP_WHOLE:
        return False
    from .own_letter import _marked as marked_of

    for letter, marks in marked_of(surface)[:lead]:
        if letter == "ה" and set(marks) & _NOT_ARTICLE:
            return False
        if letter == "ו" and set(marks) & _NOT_AND:
            return False
    return True


def title_before(run: list[tuple[str, str]], at: int) -> str:
    """The title's lemma a one-letter token finishes, read off the word before it as
    (surface, lemma): ד, lemma ד"ר, then ר. "" where there is none."""
    if at < 1:
        return ""
    surface, lemma = run[at - 1]
    here = _POINTS.sub("", run[at][0])
    before = _POINTS.sub("", surface)
    return lemma if lemma.replace('"', "") == before + here and '"' in lemma else ""


def _reshaped(token: Token, title: str) -> Token:
    """`reshaped` on a token; the same object where nothing changes."""
    syntax = token.syntax
    lead = syntax.lead if syntax is not None else 0
    prefixes = syntax.prefixes if syntax is not None else ()
    found = reshaped(token.surface, token.lemma, token.pos, token.built, lead, title, prefixes)
    if found is None:
        return token
    update: dict[str, Any] = {"lemma": found["lemma"], "built": found["built"]}
    if found["lemma"] != token.lemma:
        update |= {"headword": None, "lexeme": None, "word_register": None}
    if found["built"] is None:
        update["split"] = False
    if syntax is not None and found["lead"] != lead:
        update["syntax"] = syntax.model_copy(update={"lead": found["lead"]})
    return token.model_copy(update=update)


def _row_reshaped(row: dict[str, Any], title: str) -> dict[str, Any]:
    """`_reshaped` for a stored row; the same dict where nothing changes."""
    syntax = row.get("syntax") or {}
    lead = int(syntax.get("lead") or 0)
    found = reshaped(
        str(row.get("surface") or ""),
        str(row.get("lemma") or ""),
        row.get("pos"),
        row.get("built"),
        lead,
        title,
        tuple(syntax.get("prefixes") or ()),
    )
    if found is None:
        return row
    out = row | {"lemma": found["lemma"], "built": found["built"]}
    if found["built"] is None:
        out["split"] = False
    if found["lead"] != lead:
        out["syntax"] = syntax | {"lead": found["lead"]}
    return out


def rootless(lemma: str, pos: str | None) -> bool:
    """Whether a word has no root and no binyan to draw: an auxiliary, and the
    existential אין and יש whatever DICTA tagged them (targum-internal#700: every
    existential אין drew pa'al and א־י־ן, and "All forms of" a verb that is none)."""
    from .base import NEVER_A_VERB

    return pos == "AUX" or lemma in NEVER_A_VERB


def mend_token(token: Token, objected: bool = False, title: str = "") -> Token:
    """The token with its lemma checked; the same object where nothing changes.
    `objected` says an object follows it (`object_after`), `title` the title its letter
    finishes (`title_before`)."""
    token = _closed(_reshaped(_given_back(token), title))
    lead = token.syntax.lead if token.syntax is not None else 0
    mend = checked(token.lemma, token.surface, lead, token.pos, token.feats, objected)
    if mend is not None:
        token = token.model_copy(
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
    if rootless(token.lemma, token.pos) and (token.root or token.binyan):
        token = token.model_copy(update={"root": None, "binyan": None})
    return token


def mended(annotation: Annotation, segmented: Any = None) -> Annotation:
    """The annotation with every lemma checked; the same object where nothing changes,
    and where the annotation is neither DICTA's Hebrew nor Russian. Russian is checked
    against OpenRussian's tables (`russian_check`), with the text's segments, which say
    where a sentence starts, where they are given."""
    from . import russian_check

    if russian_check.applies(annotation.language):
        return russian_check.mended(annotation, segmented)
    if not applies(annotation.annotator, annotation.language):
        return annotation
    changed = False
    tokens: dict[str, list[Token]] = {}
    for segment_id, run in annotation.tokens.items():
        said = [(one.surface, one.lemma) for one in run]
        out = [
            mend_token(
                token,
                object_after([(one.surface, one.pos) for one in run[at + 1 : at + 3]]),
                title_before(said, at),
            )
            for at, token in enumerate(run)
        ]
        changed = changed or any(new is not old for new, old in zip(out, run, strict=True))
        tokens[segment_id] = out
    if not changed:
        return annotation
    return annotation.model_copy(update={"tokens": tokens})


def mend_rows(run: list[Any]) -> list[Any]:
    """A segment's tokens as `annotation.json` stores them, each checked with the words
    after it in view (`object_after`), as `mended` checks them for the page."""
    out: list[Any] = []
    said = [
        (str(one.get("surface") or ""), str(one.get("lemma") or ""))
        if isinstance(one, dict)
        else ("", "")
        for one in run
    ]
    for at, row in enumerate(run):
        if not isinstance(row, dict):
            out.append(row)
            continue
        after = [
            (str(one.get("surface") or ""), one.get("pos"))
            for one in run[at + 1 : at + 3]
            if isinstance(one, dict)
        ]
        out.append(mend_row(row, object_after(after), title_before(said, at)))
    return out


def mend_row(row: dict[str, Any], objected: bool = False, title: str = "") -> dict[str, Any]:
    """A token as `annotation.json` stores it, with its lemma checked: for the counts,
    which read the file rather than the model. The same dict where nothing changes.
    `objected` says an object follows it and `title` the title its letter finishes;
    `mend_rows` works both out for a segment."""
    row = _row_closed(_row_reshaped(_row_given_back(row), title))
    syntax = row.get("syntax") or {}
    mend = checked(
        str(row.get("lemma") or ""),
        str(row.get("surface") or ""),
        int(syntax.get("lead") or 0),
        row.get("pos"),
        str(row.get("feats") or ""),
        objected,
    )
    if mend is not None:
        row = row | {
            "lemma": mend.lemma,
            "root": mend.root or None,
            "binyan": mend.binyan or None,
        }
    if rootless(str(row.get("lemma") or ""), row.get("pos")) and (
        row.get("root") or row.get("binyan")
    ):
        row = row | {"root": None, "binyan": None}
    return row


def _row_given_back(row: dict[str, Any]) -> dict[str, Any]:
    """`_given_back` for a stored row; the same dict where nothing changes."""
    from .own_letter import own_letter

    syntax = row.get("syntax") or {}
    lead = int(syntax.get("lead") or 0)
    if not lead:
        return row
    own = own_letter(
        str(row.get("surface") or ""),
        str(row.get("lemma") or ""),
        row.get("pos"),
        row.get("built"),
        lead,
        tuple(syntax.get("prefixes") or ()),
        str(row.get("feats") or ""),
    )
    if own is None:
        return row
    out = row | {
        "built": own.built,
        "split": own.built is not None,
        "pos": own.pos,
        "feats": _upos(row.get("feats"), own.pos),
        "syntax": syntax | {"lead": own.lead},
    }
    if own.lemma and own.lemma != row.get("lemma"):
        out |= {"lemma": own.lemma, "root": own.root or None, "binyan": own.binyan or None}
    elif own.lemma and row.get("pos") != own.pos:
        out |= {"root": row.get("root") or own.root or None, "binyan": own.binyan or None}
    return out
