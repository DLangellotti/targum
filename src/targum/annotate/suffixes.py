"""The pronoun on the end of a Hebrew word, named: Hebrew's ninth hard spot (targum-internal
#450, 2026-10-21).

שלו, אותך, לפניהם and ספרו are a pronoun fused onto a preposition, the object marker or a
noun, and they are on every page in both registers. The annotators already cut them: DICTA
flags the suffix and the card's pieces line says "with a pronoun on the end"; Open
Scriptures writes the suffix as a piece of its own, ל + פני + הם. Neither line said whose.

**Read at render time, off what every stored token already carries**, so a text annotated
before 2026-10-21 names its suffixes without being annotated again (CLAUDE.md: a rename is
a scheduled operation). The pieces line says that a word has a suffix, and the word's own
letters say which one; the pointing, where the page has it, says the gender of ־ךָ and ־ךְ,
which unpointed Hebrew does not write.

**Measured, not trusted.** `scripts/eval_pronoun_suffixes.py` scores the Biblical reading
against Open Scriptures' own suffix codes (`Sp3mp`), outside the Torah where it was
written; `annotate/score.py` scores the modern reading against IAHLT's split-off pronouns.
A floor per register is in `evals/floors.json`.

A reading is a code, person then gender then number: "3mp", "2fs", and "c" for a gender
the word does not say (the first person, and ־ך unpointed). The card's words are English,
as the pieces line's glosses are (`hebrew.CLITIC_GLOSSES`).
"""

from __future__ import annotations

import re
import unicodedata

#: What DICTA's pieces line says of a suffix (`dicta._pieces_of`).
FLAG = "with a pronoun on the end"

#: A suffix by its written ending, longest first, for a word the pieces line says has one.
#: Modern spelling writes ־ייך for the feminine "-ayikh", so the double yod says her.
ENDINGS: tuple[tuple[str, str], ...] = (
    ("יהם", "3mp"),
    ("יהן", "3fp"),
    ("ייך", "2fs"),
    ("הם", "3mp"),
    ("הן", "3fp"),
    ("כם", "2mp"),
    ("כן", "2fp"),
    ("נו", "1cp"),
    ("ני", "1cs"),
    ("יו", "3ms"),
    ("יה", "3fs"),
    ("ך", "2cs"),
    ("ו", "3ms"),
    ("ה", "3fs"),
    ("ם", "3mp"),
    ("ן", "3fp"),
    ("י", "1cs"),
)

_BY_ENDING = dict(ENDINGS)

#: ממנו is "from him" and "from us" alike, pointed and all; "from him" is far the commoner.
SAID_AS: dict[str, str] = {"ממנו": "3ms"}

#: The written suffix pieces Open Scriptures cuts off, by their letters. Biblical poetry's
#: ־מוֹ is "them"; ־כָה is the long "your".
PIECES: dict[str, str] = {
    "ו": "3ms",
    "הו": "3ms",
    "יו": "3ms",
    "ה": "3fs",
    "יה": "3fs",
    "י": "1cs",
    "ני": "1cs",
    "נו": "1cp",
    "נה": "3fp",
    "ך": "2cs",
    "כה": "2ms",
    "כם": "2mp",
    "כן": "2fp",
    "כנה": "2fp",
    "ם": "3mp",
    "הם": "3mp",
    "המה": "3mp",
    "מו": "3mp",
    "ן": "3fp",
    "הן": "3fp",
    "הנה": "3fp",
}

#: The prepositions written as one letter, which a pronoun can stand on as a piece of its
#: own: בָּהֵן, לָהֶם.
HOSTS = frozenset("בלכמ")

QAMATS = "\u05b8"
HOLAM = "\u05b9"
SHVA = "\u05b0"
MAPPIQ = "\u05bc"
#: The vowels a consonantal ה carries, against the silent ה of direction (אַרְצָה, "to the
#: land") and the long ending, which Open Scriptures also cuts off and which are not
#: pronouns.
VOWELS = frozenset(chr(code) for code in range(0x05B0, 0x05BC))

_LETTERS = re.compile(r"[א-ת]")


def _letters(word: str) -> list[tuple[str, frozenset[str]]]:
    """Each letter with its points, accents left out."""
    out: list[tuple[str, set[str]]] = []
    for char in unicodedata.normalize("NFD", word or ""):
        if unicodedata.combining(char):
            if out and not ("\u0591" <= char <= "\u05af" or char == "\u05bd"):
                out[-1][1].add(char)
            continue
        if _LETTERS.match(char):
            out.append((char, set()))
    return [(letter, frozenset(marks)) for letter, marks in out]


def _bare(word: str) -> str:
    return "".join(letter for letter, _ in _letters(word))


def _second_person(code: str, pointed: str) -> str:
    """־ךָ is "you", a man; ־ךְ is "you", a woman. Only the pointing says so."""
    if code != "2cs":
        return code
    letters = _letters(pointed)
    if not letters or letters[-1][0] != "ך":
        return code
    marks = letters[-1][1]
    if QAMATS in marks:
        return "2ms"
    if SHVA in marks:
        return "2fs"
    return code


#: The pronouns that stand as words of their own, which DICTA now and then flags: והן is
#: "and they", not "and them".
INDEPENDENT = frozenset({"אני", "אנחנו", "אתה", "את", "אתם", "אתן", "הוא", "היא", "הם", "הן"})

_FOLD = str.maketrans("םןץףך", "מנצפכ")


def _flagged(pieces: list[str], surface: str, lemma: str, word: str) -> str:
    """DICTA's: the flag says there is a suffix, and the word's letters say which.

    The word is the piece before the flag, under its prefixes. Where it opens with its own
    lemma, what is left is the suffix, so זמנו is זמן and ו, "his time", and not זמ and נו,
    "our"; and מתוכם is תוך and ם, "from among them", not "you". Otherwise the longest
    ending stands."""
    host = _bare(pieces[-2]) if len(pieces) > 1 else _bare(surface)
    host = host or _bare(surface) or _bare(word)
    if host in SAID_AS:
        return SAID_AS[host]
    if host in INDEPENDENT:
        return ""
    stem = _bare(lemma).translate(_FOLD)
    if stem and host.startswith(stem) and host[len(stem) :] in _BY_ENDING:
        return _second_person(_BY_ENDING[host[len(stem) :]], word)
    for ending, code in ENDINGS:
        if host.endswith(ending) and len(host) > len(ending):
            return _second_person(code, word)
    return ""


def reading(
    *,
    surface: str,
    built: str | None,
    pos: str | None,
    lemma: str,
    pointed: str = "",
) -> str:
    """The suffix a stored Hebrew token carries, as a code, or "" for none.

    `surface` is the word as stored, `built` its pieces line, and `pointed` the word as the
    page writes it, with its points where it has them."""
    if not built or (" + " not in built and FLAG not in built):
        return ""
    word = pointed or surface
    pieces = [piece.strip() for piece in built.split(" + ") if piece.strip()]
    if FLAG in built:
        return _flagged(pieces, surface, lemma, word)
    # A pieces line with a gloss in it is DICTA's, and DICTA says a suffix only by the flag:
    # ל to + כן is לכן, "therefore", not "to you".
    if any(" " in piece for piece in pieces):
        return ""
    # Open Scriptures': the suffix is the last piece, where the last piece is not the word
    # itself. וְכֹה is "and thus", not "and you", and וְהֵם is "and they"; but בָּהֵן is "in
    # them", filed under the pronoun, because a preposition stands before it (and לָכֵן is
    # "therefore", כֵּן with ל, not a pronoun at all). A pronoun after anything else is a
    # word of its own, וְהֵמָּה, "and they".
    last = pieces[-1] if len(pieces) > 1 else ""
    if last not in PIECES:
        return ""
    if pos == "PRON" and pieces[-2] not in HOSTS:
        return ""
    if last == _bare(lemma) and pos != "PRON":
        return ""
    code = PIECES[last]
    letters = _letters(word)
    if not letters or word == surface:
        return code
    end, marks = letters[-1]
    if last == "ה":
        if len(letters) > 1 and HOLAM in letters[-2][1]:
            # The old spelling of "his", אָהֳלֹה for אָהֳלוֹ.
            return "3ms"
        if not (MAPPIQ in marks or marks & VOWELS):
            # A silent ה: direction (אַרְצָה) or the long form, not "her".
            return ""
    if last in ("נו", "נה"):
        # A doubled nun is the third person, מִמֶּנּוּ "from him", יְסִירֶנָּה "he removes
        # it"; a single one is "us", or the long feminine plural, קִרְבֶּנָה.
        doubled = len(letters) > 1 and letters[-2][0] == "נ" and MAPPIQ in letters[-2][1]
        if last == "נו":
            return "3ms" if doubled else "1cp"
        return "3fs" if doubled else "3fp"
    if end == "ן" and last == "ן" and len(letters) > 1 and letters[-2][0] in "וי":
        # The long ending of יִשְׁמְעוּן, not "them".
        return ""
    return _second_person(code, word)


#: Each reading as English says it: whose, and whom.
PRONOUNS: dict[str, tuple[str, str]] = {
    "1cs": ("my", "me"),
    "1cp": ("our", "us"),
    "2ms": ("your (m.)", "you (m.)"),
    "2fs": ("your (f.)", "you (f.)"),
    "2cs": ("your", "you"),
    "2mp": ("your (m. pl.)", "you (m. pl.)"),
    "2fp": ("your (f. pl.)", "you (f. pl.)"),
    "3ms": ("his", "him"),
    "3fs": ("her", "her"),
    "3mp": ("their", "them"),
    "3fp": ("their (f.)", "them (f.)"),
}

#: The prepositions a suffix lands on, by the lemma the annotators file them under, and
#: what the card says before the pronoun. "" for the object marker, which English says with
#: the pronoun alone; של is "of", and says the pronoun as whose.
PREPOSITIONS: dict[str, str] = {
    "ל": "to",
    "ב": "in",
    "כ": "like",
    "מן": "from",
    "מ": "from",
    "את": "",
    "עם": "with",
    "אל": "to",
    "על": "on",
    "עד": "up to",
    "לפני": "before",
    "אחרי": "after",
    "אחר": "after",
    "בין": "between",
    "אצל": "at",
    "בשביל": "for",
    "עבור": "for",
    "בלי": "without",
    "תחת": "under",
    "מול": "facing",
    "נגד": "against",
    "כמו": "like",
    "לגבי": "about",
    "ליד": "next to",
    "בעד": "for",
    "למען": "for the sake of",
    "בגלל": "because of",
    "מאחורי": "behind",
    "מפני": "from",
    "לקראת": "toward",
    "כלפי": "toward",
    "אודות": "about",
    "מעל": "above",
    "סביב": "around",
    "זולת": "except",
    "כל": "all of",
}

#: Biblical Hebrew's compound prepositions, which Open Scriptures files under the noun
#: they are built on: ל + פני is "before", though פנים is a face. By the first piece and
#: the lemma.
COMPOUNDS: dict[tuple[str, str], str] = {
    ("ל", "פנים"): "before",
    ("מ", "פנים"): "from before",
    ("ל", "מען"): "for the sake of",
    ("ב", "תוך"): "among",
    ("מ", "תוך"): "from among",
    ("ב", "עד"): "for",
    ("ל", "עמה"): "beside",
}

#: Strong's 854, את "with", spelled as the object marker is (`oshb.filed_as`).
WITH = "854"


def said(
    code: str,
    *,
    pos: str | None,
    lemma: str,
    built: str | None = None,
    lexeme: str | None = None,
) -> str:
    """The suffix in words, as the card says it: "his", "to you (m.)", "before them"."""
    if code not in PRONOUNS:
        return ""
    whose, whom = PRONOUNS[code]
    head = _bare(lemma)
    pieces = [piece.strip() for piece in (built or "").split(" + ") if piece.strip()]
    first = pieces[0].split(" ")[0] if len(pieces) > 2 else ""
    if (first, head) in COMPOUNDS:
        return f"{COMPOUNDS[(first, head)]} {whom}"
    if head == "את" and (lexeme or "").strip() == WITH:
        return f"with {whom}"
    if head == "של":
        return whose
    if head in PREPOSITIONS and (pos in ("ADP", "PART", None, "") or head == "כל"):
        before = PREPOSITIONS[head]
        return f"{before} {whom}" if before else whom
    if pos in ("VERB", "AUX", "ADP", "PART"):
        return whom
    return whose


#: The reading a learner takes each one for: the look-alike, then one further off. ו and י
#: are a stroke apart; ממנו is him and us at once; ־ך is either gender unpointed.
CONFUSED: dict[str, tuple[str, str]] = {
    "3ms": ("1cs", "3mp"),
    "3fs": ("3ms", "3fp"),
    "3mp": ("3fp", "3ms"),
    "3fp": ("3mp", "3fs"),
    "1cs": ("3ms", "1cp"),
    "1cp": ("3ms", "1cs"),
    "2ms": ("2fs", "3ms"),
    "2fs": ("2ms", "3fs"),
    "2cs": ("2mp", "3ms"),
    "2mp": ("3mp", "2cs"),
    "2fp": ("2mp", "3fp"),
}


def agrees(ours: str, gold: str) -> bool:
    """Whether a reading says what the gold says. Person and number must match; a gender
    must match where both say one, and "c" says none, which is true of either."""
    if len(ours) != 3 or len(gold) != 3:
        return False
    if ours[0] != gold[0] or ours[2] != gold[2]:
        return False
    return "c" in (ours[1], gold[1]) or ours[1] == gold[1]


def code_of(person: str, gender: str, number: str) -> str:
    """A code from features as UD writes them, or from Open Scriptures' letters."""
    gender = {"Masc": "m", "Fem": "f", "m": "m", "f": "f"}.get(gender, "c")
    number = {"Sing": "s", "Plur": "p", "s": "s", "p": "p", "d": "p"}.get(number, "")
    if person not in ("1", "2", "3") or not number:
        return ""
    return f"{person}{gender}{number}"
