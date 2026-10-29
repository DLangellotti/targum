"""Standard ktiv menukad for pointed Hebrew that arrives in full spelling (targum-internal#563).

Pointed Hebrew is written in *defective* spelling: the vowel points do the work the
matres lectionis do in unpointed text, so חיבור is pointed חִבּוּר, בוקר בֹּקֶר, יופי יֹפִי.
What the pipeline produced is the full spelling with points laid over it: חִיבּוּר,
בּוֹקֶר, and in the B1 Conversations a mixed form with the vowel on the letter and the
mater left bare beside it (יֹופִי, מְעֻולֶּה), which is the menaked's own output with its
matres kept. ling-he's audit of 2026-10-29 counted 1,151 such words across both scene
sets, every scene in both. This puts them right.

**At the source, the menaked can already do it.** Its head classes each letter it reads
as a mater lectionis `<MAT_LECT>`, and `vocalize.dicta.assemble(drop_matres=True)` drops
those letters instead of keeping them bare. Probed on 2026-10-29, it keeps שָׁלוֹם, הוּא
and הַיּוֹם whole and gives יֹפִי, חִבּוּר, בֹּקֶר, תׇּכְנִית, כֻּלָּם, עֲדַיִן and בִּנְיָן —
the distinction between a holam male that stays and one that goes is learnt, which no
rule here can match. So a line the menaked points fresh should be pointed that way; this
module is for the text already pointed in full spelling, and for the few words the model
still gets wrong (loanwords, טֶלֶפוֹן).

**It changes letters, and that is why it is not a vowel step.** Everything else in
`vocalize` adds marks and nothing else (`base.py`). A pointed form in defective spelling
has fewer letters than the plain form, and a reader that derives the plain cell by
stripping the points off the pointed one would show the defective spelling unpointed.
A caller has to keep the plain text and the pointed text apart before using this.

**What it holds.** Rules that are decidable from the letters and points, each named so a
change says which one made it; an exceptions list of words where the full spelling is
right under points too (הָיִיתִי, plural ־ִיִּים, consonantal vav, loanwords, the qtilut
nouns בְּטִיחוּת and שְׁלִיחוּת); and a lexicon for the words no rule reaches (a hiriq
before a guttural, qamats qatan, a tsere with a bare yod). `dialogue/checks.py` holds no
lexicon on principle; this cannot work without one, so it lives here.

It is idempotent: normalising its own output changes nothing. `residue` is the miss
detector — what still looks like full spelling after normalising — and a pointing step
that uses this fails on a non-empty residue rather than shipping it.

    python -m targum.vocalize.menukad SCENE.json [...]          # print every change
    python -m targum.vocalize.menukad --out DIR SCENE.json [...]  # and write copies
    python -m targum.vocalize.menukad --pointed --out DIR SCENE.json [...]

`--pointed` is for a scene (targum-internal#568): the normalised line goes into each
turn's `pointed` and `text` keeps its full spelling, which is the shape a scene holds now.
A turn that already has a `pointed` line is normalised there instead.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from collections import Counter
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

SHIN_DOT, SIN_DOT, DAGESH = "ׁ", "ׂ", "ּ"
SHVA, HATAF_QAMATS = "ְ", "ֳ"
HIRIQ, TSERE, SEGOL, PATAH = "ִ", "ֵ", "ֶ", "ַ"
QAMATS, HOLAM, QUBUTS, QATAN = "ָ", "ֹ", "ֻ", "ׇ"

L = "א-ת"
#: The points a letter carries here: vowels, shva, dagesh, the shin and sin dots, qamats
#: qatan. Not maqaf, paseq or sof pasuq, which sit in the same range and are not marks.
P = "ְ-ׇֽֿׁׂׅׄ"
_MARK = re.compile(f"[{P}֑-֯]")
_WORD = re.compile(f"[{L}](?:[{L}{P}֑-֯]|['׳](?=[{L}{P}]))*")


def reorder(text: str) -> str:
    """Each letter's marks in one order — shin or sin dot, then dagesh, then the vowel —
    so a rule written once matches however the marks arrived. NFC orders them by
    combining class instead (vowel first), so both sides are put into this order."""
    out: list[str] = []
    marks: list[str] = []

    def flush() -> None:
        marks.sort(key=lambda m: 0 if m in (SHIN_DOT, SIN_DOT) else 1 if m == DAGESH else 2)
        out.extend(marks)
        marks.clear()

    for char in unicodedata.normalize("NFC", text):
        if _MARK.match(char):
            marks.append(char)
        else:
            flush()
            out.append(char)
    flush()
    return "".join(out)


def bare(word: str) -> str:
    return re.sub(f"[^{L}]", "", word)


# ------------------------------------------------------------------------- exceptions

#: Loanwords, matched as a stretch of a word's letters: the full spelling is how they are
#: pointed too, because the mater is the only thing saying which vowel a borrowed word has.
LOANWORDS = (
    "מייל",
    "קייס",
    "הייטק",
    "היטק",
    "וואטסאפ",
    "פריידיי",
    "טיימר",
    "וייט",
    "יוטיוב",
    "ביבליוגרפ",
    "אנטיביו",
    "סופר",
    "קורס",
    "אוגוסט",
    "טוסט",
    "קיוסק",
    "פקולט",
    "כדורסל",
    "מודל",
    "פיצה",
    "פיצרי",
    "ליגה",
    "אפליקצי",
    "סטודיו",
    "רדיו",
    "וידאו",
    "אייפון",
    "פייסבוק",
    "אינסטגרם",
    "טיקטוק",
    "ג'וב",
    "פוקוס",
    # From ling-he's second audit (2026-10-29): a brand, a loan, a city.
    "אקמול",
    "בייביסיט",
    "קייב",
    "שווארמ",
    "שוארמ",
)

#: Loanwords too short to look for inside other words (לגזום is not Zoom): matched as
#: the whole word, behind its prefixes.
LOANWORD_WORDS = frozenset({"זום", "בוס", "ביט"})

PREFIX_LETTERS = "ובכלמשה"


def behind_prefixes(plain: str, words: Iterable[str]) -> bool:
    """Whether `plain` is one of `words` with up to three prefix letters in front."""
    wanted = set(words)
    for cut in range(4):
        if cut and (cut >= len(plain) or plain[cut - 1] not in PREFIX_LETTERS):
            return False
        if plain[cut:] in wanted:
            return True
    return False


#: Interjections whose doubled letters are the word.
INTERJECTIONS = frozenset({"וואו", "וואי", "וואלה", "ביי", "היי", "ביייי", "אוי", "יאללה"})

#: The prefixes a word may wear in front of the words below.
_PREFIX = f"(?:[ובכלמשה][{P}]*){{0,3}}"

#: הָיִיתִי, הָיִיתָ and every prefixed form: the doubled yod is the root's and the
#: suffix's, not a mater. And the qtilut nouns, whose hiriq male is the pattern's own.
_KEEP = re.compile(f"^{_PREFIX}ה{QAMATS}י{HIRIQ}י(?![{P}])[תנ]")
QTILUT = ("בטיחו", "שליחו")

#: Nouns and names a future-shaped rule would read as a verb: לִרְחוֹב is to a street,
#: not a verb, and אֶשְׁכּוֹל keeps its holam male under points.
NOT_FUTURE = frozenset(
    {
        "אתמול",
        "אלבום",
        "רחוב",
        "אשכול",
        "אגרוף",
        "אשדוד",
        "אשקלון",
    }
)


#: How a loanword is pointed, put right even though the word is otherwise kept: מייל with a
#: shva on its first yod reads "mey-yl" (ling-he, audit 2: six lines).
_LOAN_POINTING = (
    (re.compile(f"מ({DAGESH}?)[{TSERE}{SEGOL}]י{SHVA}י(?![{P}])"), f"מ\\1{TSERE}יי"),
    # and any loan's ey written the same way: בֶּיְיבִּיסִיטֶר → בֶּייבִּיסִיטֶר
    (re.compile(f"([{TSERE}{SEGOL}])י{SHVA}י(?![{P}])"), "\\1יי"),
)


def loan_pointing(word: str) -> str:
    w = reorder(word)
    for rx, new in _LOAN_POINTING:
        w = rx.sub(new, w)
    return w


def kept(word: str, names: frozenset[str] = frozenset()) -> bool:
    """Whether a word is left exactly as it is: an exception, a loanword, a name."""
    plain = bare(word)
    if not plain or plain in INTERJECTIONS:
        return True
    if any(stem in plain for stem in LOANWORDS + QTILUT):
        return True
    if behind_prefixes(plain, LOANWORD_WORDS) or _KEEP.match(reorder(word)):
        return True
    return behind_prefixes(plain, names)


# ------------------------------------------------------------------------------ rules

Rule = tuple[str, Callable[[str], str]]


def _sub(pattern: str, repl: str | Callable[[re.Match[str]], str]) -> Callable[[str], str]:
    rx = re.compile(pattern)
    return lambda w: rx.sub(repl, w)


def _future(word: str) -> str:
    """Qal future and infinitive, C ְ C וֹ C at the end: holam haser (לִשְׁמֹעַ, תִּסְגֹּר)."""
    shape = re.compile(
        f"^(?:[ושכ][{P}]*)?[לתינא][{HIRIQ}{SEGOL}{PATAH}{DAGESH}]+[{L}][{SHIN_DOT}{SIN_DOT}{DAGESH}]*"
        f"[{SHVA}ֱֲ][{L}][{SHIN_DOT}{SIN_DOT}{DAGESH}]*ו{HOLAM}"
        f"[א-מנ-ש][{SHIN_DOT}{SIN_DOT}{DAGESH}{SHVA}]*{PATAH}?$"
    )
    core = re.sub(f"[^{L}{P}]", "", word)
    plain = bare(word)
    if not shape.search(core) or behind_prefixes(plain, NOT_FUTURE):
        return word
    return re.sub(
        f"ו{HOLAM}(?=[{L}][{SHIN_DOT}{SIN_DOT}{DAGESH}{SHVA}]*{PATAH}?(?![{L}{P}]))", HOLAM, word
    )


#: In application order; each is tried until nothing changes. Written in `reorder`'s mark
#: order. The counts in the comments are ling-he's (box B1 / dialogue scenes).
RULES: tuple[Rule, ...] = (
    # First, a vowel written on the letter before its own vav is put on the vav: יֹופִי is
    # יוֹפִי written another way, and מְעֻולֶּה is מְעוּלֶּה. The menaked writes a mater so,
    # and so does any text that puts a holam male on the letter before (שָׁלֹום, לֹו). Moved,
    # not dropped: whether the vav goes is for the rules below to say (segolate, qal
    # future, the lexicon), and שָׁלוֹם keeps it. Dropping it here lost the vav of every
    # holam male written that way (qa, #986).
    ("holam written before its vav", _sub(f"{HOLAM}ו(?![{P}])", f"ו{HOLAM}")),
    ("qubuts written before its vav", _sub(f"{QUBUTS}ו(?![{P}])", f"ו{DAGESH}")),
    # חׇודְשַׁיִים → חׇדְשַׁיִם, but not קְצָווֹת, whose second vav is a consonant.
    ("qamats + bare vav", _sub(f"([{QAMATS}{QATAN}])ו(?![{P}])(?=[{L}])(?!ו{HOLAM})", r"\1")),
    # חִיבּוּר → חִבּוּר, שִׁישִּׁי → שִׁשִּׁי (118 / 242).
    (
        "hiriq + bare yod before dagesh",
        _sub(f"{HIRIQ}י(?![{P}])(?=[{L}][{SHIN_DOT}{SIN_DOT}]*{DAGESH})", HIRIQ),
    ),
    # כּוּלָּם → כֻּלָּם, מְצוּיָּן → מְצֻיָּן (24 / 68).
    (
        "shuruk before dagesh",
        _sub(
            f"(?<=[{L}])([{SHIN_DOT}{SIN_DOT}{DAGESH}]*)[{SHVA}]?ו{DAGESH}(?![{P}])"
            f"(?=[{L}][{SHIN_DOT}{SIN_DOT}]*{DAGESH})",
            lambda m: m.group(1) + QUBUTS,
        ),
    ),
    # שְׁנָתַיִים → שְׁנָתַיִם, עֲדַיִין → עֲדַיִן (33 / 89).
    ("-ayim with two yods", _sub(f"{PATAH}י{HIRIQ}י(?![{P}])(?=[םן])", f"{PATAH}י{HIRIQ}")),
    # בִּנְיָין → בִּנְיָן, לְטַיֵּיל → לְטַיֵּל (41 / 78), not the plural ־ִיִּים.
    (
        "doubled consonantal yod",
        _sub(f"(י(?![{HIRIQ}{DAGESH}]+ים)[{P}]+)י(?![{P}])(?=[{L}])", r"\1"),
    ),
    # צֶוֶות → צֶוֶת, לְוַותֵּר → לְוַתֵּר (14 / 38).
    ("doubled consonantal vav", _sub(f"(ו[{P}]+)ו(?![{P}])(?=[{L}])(?!ו{HOLAM})", r"\1")),
    # אֵלַיי → אֵלַי.
    ("final -ay with two yods", _sub(f"([{PATAH}{QAMATS}])יי(?![{P}])(?![{L}])", r"\1י")),
    ("hataf qamats + bare vav", _sub(f"{HATAF_QAMATS}ו(?![{P}])", HATAF_QAMATS)),
    # נִיהוּל → נִהוּל, שִׁיעוּר → שִׁעוּר: a piel noun before a guttural, no dagesh to see.
    # Only where the word goes on after the shuruk: a hif'il plural ends there (הִגִּיעוּ,
    # יַצְלִיחוּ), and its hiriq male is the binyan's, not a mater (ling-he, audit 2: P0).
    (
        "hiriq + bare yod before a guttural",
        _sub(f"{HIRIQ}י(?![{P}])(?=[החע]ו{DAGESH}[{L}])", HIRIQ),
    ),
    # הַכּוֹל → הַכֹּל: the word itself behind its prefixes, never the end of אֶשְׁכּוֹל.
    (
        "kol",
        _sub(f"^({_PREFIX})כ({DAGESH}?)ו{HOLAM}ל$", lambda m: f"{m.group(1)}כ{m.group(2)}{HOLAM}ל"),
    ),
    # לִשְׁמוֹעַ → לִשְׁמֹעַ (44 / 96).
    ("qal future or infinitive", _future),
    # בּוֹקֶר → בֹּקֶר, טוֹפֶס → טֹפֶס (19 / 60): the whole word is a segolate.
    (
        "segolate",
        _sub(
            f"^({_PREFIX}[{L}][{SHIN_DOT}{SIN_DOT}{DAGESH}]*)ו{HOLAM}"
            f"([{L}][{SHIN_DOT}{SIN_DOT}{DAGESH}]*{SEGOL}[א-דו-ת]"
            f"[{SHIN_DOT}{SIN_DOT}{DAGESH}{SHVA}]*)$",
            lambda m: m.group(1) + HOLAM + m.group(2),
        ),
    ),
    # פּוֹתֵח → פּוֹתֵחַ, לִשְׁמֹע → לִשְׁמֹעַ: a final ח or ע after a vowel that is not
    # an a takes the furtive patah.
    (
        "furtive patah",
        _sub(
            f"((?:[{HIRIQ}{TSERE}{HOLAM}{QUBUTS}]|ו[{HOLAM}{DAGESH}]|{HIRIQ}י)[{SHIN_DOT}{SIN_DOT}]?)"
            f"([חע])$",
            lambda m: m.group(1) + m.group(2) + PATAH,
        ),
    ),
)

#: Words no rule reaches, as (full spelling, standard), matched as part of a word so a
#: prefix or suffix rides along. Stems end where the word may go on; a key that is a
#: whole word says so with `$`. From ling-he's audit tables A and B.
_LEXICON_SOURCE: tuple[tuple[str, str], ...] = (
    # shuruk for qubuts in a closed syllable
    ("שׁוּלְח", "שֻׁלְח"),
    ("חוּפְשׁ", "חֻפְשׁ"),
    ("חוּלְצ", "חֻלְצ"),
    ("מוּדְפּ", "מֻדְפּ"),
    ("פּוּמְבּ", "פֻּמְבּ"),
    ("הוּפְע", "הֻפְע"),
    ("מוּקְד", "מֻקְד"),
    ("מוּתְא", "מֻתְא"),
    ("קוּיְמ", "קֻיְּמ"),
    ("קוּפְס", "קֻפְס"),
    ("הוּזְמ", "הֻזְמ"),
    ("דּוּכְנ", "דֻּכְנ"),
    ("מְאוּח", "מְאֻח"),
    ("מְיוּח", "מְיֻח"),
    ("מוּזְמ", "מֻזְמ"),
    ("מוּשְׁל", "מֻשְׁל"),
    ("מוּגְב", "מֻגְב"),
    ("מוּמְלָ", "מֻמְלָ"),
    ("מוּסְכָּ", "מֻסְכָּ"),
    ("סוּכָּר", "סֻכָּר"),
    ("מוּכְשָׁ", "מֻכְשָׁ"),
    ("תּוּכְנ", "תֻּכְנ"),
    ("אוּמְנָ", "אֻמְנָ"),
    ("חוּרְבּ", "חֻרְבּ"),
    ("פּוּרְסַ", "פֻּרְסַ"),
    ("מוּעֲמָד", "מֻעֲמָד"),
    # a tsere with a bare yod
    ("שֵׁירוּת", "שֵׁרוּת"),
    ("תֵּיבָ", "תֵּבָ"),
    ("תֵּיהָנ", "תֵּהָנ"),
    ("אֲסֵיפ", "אֲסֵפ"),
    ("טֵירוּף", "טֵרוּף"),
    ("פֵּירוּשׁ", "פֵּרוּשׁ"),
    ("תֵּיאוּר", "תֵּאוּר"),
    ("תִּיאוּר", "תֵּאוּר"),
    ("מְגֵיר", "מְגֵר"),
    # a hiriq with a bare yod where no dagesh follows
    ("אִיחוּר", "אִחוּר"),
    ("תִּיקְח", "תִּקְח"),
    ("כִּיסְא", "כִּסְא"),
    ("כִּיוּוּן", "כִּוּוּן"),
    ("כִּיוּוּנ", "כִּוּוּנ"),
    ("גִּילְיוֹן", "גִּלָּיוֹן"),
    # qamats qatan, written U+05C7 as the menaked writes it
    ("אוֹזְנִי", "אׇזְנִי"),
    ("אוֹזְנַיִים", "אׇזְנַיִם"),
    ("אוֹזְנַיִם", "אׇזְנַיִם"),
    ("תּוֹכְנִית", "תׇּכְנִית"),
    ("תָּכְנִית", "תׇּכְנִית"),
    ("אוֹבְדָן", "אׇבְדָן"),
    ("אוֹבְדַן", "אׇבְדַן"),
    ("אָבְדָן", "אׇבְדָן"),
    ("גּוֹלְמִי", "גׇּלְמִי"),
    ("גׇּולְמִי", "גׇּלְמִי"),
    ("חוֹדְשַׁיִים", "חׇדְשַׁיִם"),
    ("חׇודְשַׁיִים", "חׇדְשַׁיִם"),
    ("חוֹדְשַׁיִם", "חׇדְשַׁיִם"),
    ("חוֹדָשַׁיִים", "חׇדְשַׁיִם"),
    ("חוֹדָשַׁיִם", "חׇדְשַׁיִם"),
    ("חוֹדָשִׁים", "חֳדָשִׁים"),
    # other words
    ("טֵלֵפוֹן", "טֶלֶפוֹן"),
    ("טֵלֶפוֹן", "טֶלֶפוֹן"),
    ("טֶלֵפוֹן", "טֶלֶפוֹן"),
    ("נוֹהַל", "נֹהַל"),
    ("נוֹהָל", "נֹהָל"),
    ("חֲתוּנָה", "חֲתֻנָּה"),
    ("חֲתוּנּ", "חֲתֻנּ"),
    ("אַלְמוֹגּ", "אַלְמֻגּ"),
    ("בְּיּוֹמַיִים", "בְּיוֹמַיִם"),
    ("טֵסְט$", "טֶסְט$"),
    ("אַסְטֵמָה", "אַסְתְּמָה"),
    ("מִקְדֵּמָה", "מִקְדָּמָה"),
    ("סָבְתָא", "סַבְתָּא"),
    ("בּוּרוֹכוֹב", "בּוֹרוֹכוֹב"),
    ("מְדוּזוֹת", "מֵדוּזוֹת"),
    ("מְדוּזָה", "מֵדוּזָה"),
    ("ג'וֹנְיוֹר", "ג'וּנְיוֹר"),
    # a pi'el whose doubled yod is a geminate: one yod, with its dagesh
    ("מְעַיְיפ", "מְעַיְּפ"),
    # holam haser that no rule reaches once a holam is back on its vav
    ("יוֹפִי", "יֹפִי"),
    ("מְטוֹרָף", "מְטֹרָף"),
    ("מְטוֹרֶפֶת", "מְטֹרֶפֶת"),
    ("חוֹם$", "חֹם$"),
    ("לִישׁוֹן", "לִישֹׁן"),
)


def _lexicon() -> tuple[tuple[re.Pattern[str], str], ...]:
    """Each entry as a pattern and its replacement. The first letter's dagesh is left to
    the text, since a prefix takes it away or the article puts it there (טֵלֵפוֹן,
    הַטֵּלֵפוֹן): the pattern accepts either and the replacement keeps what was there."""
    out = []
    for old, new in _LEXICON_SOURCE:
        whole = old.endswith("$")
        old, new = reorder(old.rstrip("$")), reorder(new.rstrip("$"))
        lead = re.match(f"[{L}][{SHIN_DOT}{SIN_DOT}]*", old)
        assert lead is not None
        head = lead.group(0)
        old_rest = old[len(head) :].removeprefix(DAGESH)
        new_rest = new[len(head) :].removeprefix(DAGESH)
        rx = re.escape(head) + f"({DAGESH}?)" + re.escape(old_rest)
        if whole:
            rx += f"(?![{L}{P}])"
        out.append((re.compile(rx), head + "\\1" + new_rest.replace("\\", "\\\\")))
    return tuple(out)


LEXICON = _lexicon()


def _lex(word: str) -> str:
    for rx, new in LEXICON:
        word = rx.sub(new, word)
    return word


# -------------------------------------------------------------------------- the API


@dataclass(frozen=True)
class Change:
    word: str
    becomes: str
    rules: tuple[str, ...]


def normalise_word(word: str, names: frozenset[str] = frozenset()) -> tuple[str, tuple[str, ...]]:
    """The word in standard ktiv menukad, and the rules that changed it (none: as it was)."""
    if not _MARK.search(word):
        return word, ()
    if kept(word, names):
        loaned = unicodedata.normalize("NFC", loan_pointing(word))
        if loaned != unicodedata.normalize("NFC", word):
            return loaned, ("loanword pointing",)
        return word, ()
    w = reorder(word)
    fired: list[str] = []
    # A word with a geresh is borrowed (ג'וּנְיוֹר): the lexicon may correct it, and no
    # rule touches it.
    borrowed = "'" in word or "׳" in word
    for _ in range(4):
        before = w
        # The lexicon each pass, since the first rules can put a word into the shape
        # it lists (שֻׁולְחָן becomes שׁוּלְחָן, which it knows).
        lexed = _lex(w)
        if lexed != w:
            fired.append("lexicon")
            w = lexed
        for name, rule in () if borrowed else RULES:
            after = rule(w)
            if after != w:
                fired.append(name)
                w = after
        if w == before:
            break
    if not fired:
        return word, ()
    out = unicodedata.normalize("NFC", w)
    if out == unicodedata.normalize("NFC", word):
        return word, ()
    return out, tuple(dict.fromkeys(fired))


def normalise(text: str, names: Iterable[str] = ()) -> tuple[str, list[Change]]:
    """The text with every word in standard ktiv menukad. A word nothing changes is left
    byte for byte as it came, so a second run is a no-op and a diff shows only fixes."""
    keep = frozenset(bare(n) for n in names if n)
    changes: list[Change] = []

    def one(match: re.Match[str]) -> str:
        word = match.group(0)
        new, rules = normalise_word(word, keep)
        if rules:
            changes.append(Change(word, new, rules))
        return new

    return _WORD.sub(one, text), changes


#: What full spelling under points looks like, for `residue`: the rules' own patterns as
#: detectors, so a word they should have changed and did not is named.
_DETECT: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("qubuts + bare vav", re.compile(f"{QUBUTS}ו(?![{P}])")),
    ("holam + bare vav", re.compile(f"{HOLAM}ו(?![{P}])")),
    ("qamats + bare vav", re.compile(f"[{QAMATS}{QATAN}]ו(?![{P}])(?=[{L}])(?!ו{HOLAM})")),
    (
        "hiriq + bare yod before dagesh",
        re.compile(f"{HIRIQ}י(?![{P}])[{L}][{SHIN_DOT}{SIN_DOT}]*{DAGESH}"),
    ),
    ("-ayim with two yods", re.compile(f"{PATAH}י{HIRIQ}י(?![{P}])[םן]")),
    (
        "doubled consonantal yod",
        re.compile(f"י(?![{HIRIQ}{DAGESH}]+ים)[{P}]+י(?![{P}])(?=[{L}])"),
    ),
    ("doubled consonantal vav", re.compile(f"ו[{P}]+ו(?![{P}])(?=[{L}])(?!ו{HOLAM})")),
)


#: The rules allowed to take a vav out of a word. Anything else that loses one has lost it.
TAKES_A_VAV = frozenset(
    {
        "lexicon",
        "shuruk before dagesh",
        "qamats + bare vav",
        "hataf qamats + bare vav",
        "doubled consonantal vav",
        "kol",
        "qal future or infinitive",
        "segolate",
    }
)


def residue(
    text: str, names: Iterable[str] = (), source: str | None = None
) -> list[tuple[str, str]]:
    """(rule, word) for every word that still looks like full spelling under points.

    Given the `source` the text was made from, word for word, it also names a word that
    has lost a vav no rule takes out: שָׁלֹם for שָׁלוֹם is a holam male gone missing, not
    a correction, and nothing in the word alone says so."""
    keep = frozenset(bare(n) for n in names if n)
    out: list[tuple[str, str]] = []
    if source is not None:
        for old, new in zip(_WORD.findall(source), _WORD.findall(text), strict=False):
            if bare(new).count("ו") >= bare(old).count("ו") or kept(old, keep):
                continue
            if not set(normalise_word(old, keep)[1]) & TAKES_A_VAV:
                out.append(("lost vav", new))
    for match in _WORD.finditer(text):
        word = match.group(0)
        if _MARK.search(word) and kept(word, keep) and reorder(word) != loan_pointing(word):
            out.append(("loanword pointing", word))
            continue
        if not _MARK.search(word) or kept(word, keep) or "'" in word or "׳" in word:
            continue
        w = reorder(word)
        for name, rx in _DETECT:
            if rx.search(w):
                out.append((name, word))
                break
    return out


# ------------------------------------------------------------------------------- CLI


def _lines(data: object) -> Iterator[tuple[str, dict[str, str] | None, str, list[str]]]:
    """(where, the dict holding the line, its key, the cast's names) for each line of a
    scene file (`turns[].text`, bare or under `scene`) or a `pointed.json` map."""
    if isinstance(data, dict) and isinstance(data.get("scene"), dict):
        data = data["scene"]
    if isinstance(data, dict) and isinstance(data.get("turns"), list):
        cast = data.get("cast") or {}
        names = [str(v.get("name") or "") for v in cast.values() if isinstance(v, dict)]
        for n, turn in enumerate(data["turns"]):
            if isinstance(turn, dict) and isinstance(turn.get("text"), str):
                yield f"t{n}", turn, "text", names
    elif isinstance(data, dict):
        for key, value in data.items():
            if isinstance(value, str):
                yield str(key), data, key, []


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m targum.vocalize.menukad",
        description="Normalise pointed Hebrew to standard ktiv menukad. Prints every change; "
        "reads only, unless --out names a folder for the normalised copies.",
    )
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument("--out", type=Path, help="write normalised copies here")
    parser.add_argument(
        "--pointed",
        action="store_true",
        help="for scenes: write each line into the turn's `pointed`, keeping `text`",
    )
    args = parser.parse_args(argv)
    total: Counter[str] = Counter()
    missed = 0
    for path in args.files:
        data = json.loads(path.read_text(encoding="utf-8"))
        for where, holder, key, names in _lines(data):
            assert holder is not None
            into = key
            if args.pointed and key == "text":
                into = "pointed"
                if not holder.get("pointed"):
                    if not _MARK.search(holder["text"]):
                        continue  # nothing pointed, so nothing for a pointed cell
                    holder["pointed"] = holder["text"]
            text, changes = normalise(holder[into], names)
            for change in changes:
                total.update(change.rules)
                rules = ", ".join(change.rules)
                print(f"{path.stem}\t{where}\t{change.word} → {change.becomes}\t{rules}")
            for rule, word in residue(text, names, source=holder[into]):
                missed += 1
                print(f"{path.stem}\t{where}\tMISSED {word}\t{rule}")
            holder[into] = text
        if args.out:
            args.out.mkdir(parents=True, exist_ok=True)
            (args.out / path.name).write_text(
                json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
    print(
        f"{sum(total.values())} rule applications: "
        + ", ".join(f"{k} {v}" for k, v in total.most_common())
    )
    print(f"{missed} words still in full spelling")
    return 1 if missed else 0


if __name__ == "__main__":
    sys.exit(main())
