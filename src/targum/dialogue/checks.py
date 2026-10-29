"""What can be said about a scene's Hebrew without reading it.

The hundred hand-written scenes were audited on 2026-09-22 by two independent readings
from Opus 5, and 275 real errors came out of it — in the first Hebrew a new account
meets, sitting there unnoticed for months. That audit cost money and took a person a
long evening of judgements. This is the half of it that is free.

**Why a checker at all, when a model reads better.** Because the model is a spend and a
wait, so it runs when somebody remembers; this runs on every scene, every time, for
nothing. The two are not rivals. The model finds what needs Hebrew; this finds what
needs only arithmetic, and it finds it before the model is ever called.

**What is refused here.** An earlier attempt at this hand-rolled a cast check that
compared consonants and so missed every vowel-only gender error *by design*, and a
self-introduction check that returned 102 hits of which one was real. Both were deleted.
The lesson is in what this module will not do: it holds no lexicon, guesses at no
meaning, and every check below is decidable from the letters and points alone. A rule
with defensible exceptions is not in here — `dagesh` on א is always wrong, so it is a
check; a doubled yod is wrong in שֶׁהִשְׂכַּרְתִּיי and right in הָיִיתִי, so it is not.

`scripts/score_scene_checks.py` scores these against the 275 judgements, so the claim
"this catches X" is a measured number and not a hope.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterator
from dataclasses import dataclass

#: Every Hebrew point, including cantillation.
POINTS = re.compile(r"[֑-ׇ]")

#: The vowel signs, not counting shva, dagesh or the shin/sin dots.
VOWELS = "ֱֲֳִֵֶַָׇֹֺֻ"
SHVA = "ְ"
HATAFS = "ֱֲֳ"
DAGESH = "ּ"
QAMATS = "ָ"
PATAH = "ַ"

#: The letters a dagesh can never sit in. ה is not here: a final ה takes a mappiq,
#: which is the same character, so ה is judged by position instead.
NO_DAGESH = "אעחר"

#: The gutturals, which are the letters a hataf vowel belongs under. ר is included
#: because it takes one in a handful of words (חֲרָרָה) and the point of this list is
#: to have no false positives, not to be complete.
GUTTURALS = "אהחער"

FINALS = {"ך": "כ", "ם": "מ", "ן": "נ", "ף": "פ", "ץ": "צ"}

LETTERS = re.compile(r"[א-ת]")


def bare(text: str) -> str:
    """The consonants alone, which is what identifies a word across two pointings."""
    return POINTS.sub("", unicodedata.normalize("NFC", text or ""))


@dataclass(frozen=True)
class Finding:
    """One thing wrong, located well enough to act on without looking for it.

    `kind` matches the audit's own vocabulary so a finding from here and a finding from
    `scripts/audit_scenes.py` can be counted together.
    """

    turn: int
    kind: str
    word: str
    what: str
    fix: str = ""

    def where(self) -> str:
        return f"t{self.turn} «{self.word}»"


def units(word: str) -> list[tuple[str, str]]:
    """A word as (letter, the marks on it) pairs, in order.

    Anything before the first letter is dropped rather than raising: a line may open
    with a quotation mark or an ellipsis and a checker is not the place to find out.
    """
    out: list[tuple[str, str]] = []
    for char in unicodedata.normalize("NFC", word):
        if LETTERS.match(char):
            out.append((char, ""))
        elif POINTS.match(char) and out:
            letter, marks = out[-1]
            out[-1] = (letter, marks + char)
    return out


def words_of(line: str) -> Iterator[str]:
    for piece in re.split(r"[\s־]+", unicodedata.normalize("NFC", line or "")):
        word = piece.strip("\"'.,?!:;()[]׳״“”—-")
        if word and LETTERS.search(word):
            yield word


# --------------------------------------------------------------------------- points


def impossible_dagesh(line: str, turn: int) -> Iterator[Finding]:
    """A dagesh in a letter that cannot hold one.

    א, ע, ח and ר never take a dagesh in any word. ה takes one only as a mappiq, which
    is word-final by definition — `מְקוֹמָהּ` is a correct mappiq and `הּוּא` is not.
    """
    for word in words_of(line):
        seen = units(word)
        for n, (letter, marks) in enumerate(seen):
            if DAGESH not in marks:
                continue
            if letter in NO_DAGESH:
                yield Finding(turn, "nikkud", word, f"A dagesh in {letter}, which never takes one.")
            elif letter == "ה" and n != len(seen) - 1:
                yield Finding(
                    turn,
                    "nikkud",
                    word,
                    "A dagesh in a ה that is not word-final; a mappiq is final.",
                )


def hataf_on_non_guttural(line: str, turn: int) -> Iterator[Finding]:
    """A hataf vowel under a letter that is not a guttural, which no word has."""
    for word in words_of(line):
        for letter, marks in units(word):
            if any(mark in HATAFS for mark in marks) and letter not in GUTTURALS:
                yield Finding(
                    turn, "nikkud", word, f"A hataf vowel under {letter}, which is not a guttural."
                )


# There was a third points check here and it is gone on purpose. A word whose last
# syllable holds no vowel — the final letter bare, the one before it carrying a shva —
# cannot be read, and that is how Herzl Street was pointed in scene 3: הֶרְצְל. But
# measured over the hundred scenes it also flagged בַּנְק, אוֹגוּסְט and טֶסְט, which are
# ordinary. A borrowed word ending in a consonant cluster is pointed exactly like the
# mistake, and nothing in the letters says which is which: Herzl is a borrowed word too.
# It scored one gold error against five false positives, so it is not a check. It is a
# judgement about how loanwords are pointed, and it belongs to whoever is reading.


# ------------------------------------------------------------------------ the cast


#: The words where a final kaf really is the 'you' suffix, and so is pointed ־ךָ for a
#: man and ־ךְ for a woman. A list and not a rule, because the rule does not exist: a
#: final kaf carries a shva in איך, צריך, בְּעֵרֶךְ, הוֹלֵךְ and אָרוֹךְ too, and the first
#: version of this check called all of them feminine — sixty false positives, which is
#: the shape of the hand-rolled checker that had to be deleted in the first place.
#: Every entry is a preposition or a possessive, so the list is closed and stays short.
KAF_IS_YOU = {
    "אותך",
    "לך",
    "שלך",
    "איתך",
    "אתך",
    "אליך",
    "עליך",
    "ממך",
    "בך",
    "כמוך",
    "אצלך",
    "בשבילך",
    "עבורך",
    "לידך",
    "מולך",
}


def addressed_gender(word: str) -> str:
    """'m', 'f' or '' — who a word says it is spoken to, where the points decide it.

    Two endings decide it and nothing else is looked at. A final tav with a qamats is
    the 2ms past (אָמַרְתָּ) and with a shva the 2fs (אָמַרְתְּ); a final kaf is the 'you'
    suffix only in the closed list above, and there ־ךָ is a man and ־ךְ a woman.
    Anything else returns '' rather than a guess.
    """
    seen = units(word)
    if not seen:
        return ""
    letter, marks = seen[-1]
    plain = bare(word)
    if plain == "אתה":
        # אַתָּה "you" has an a under its alef; אִתָּהּ "with her" (אִתָּה once the mappiq
        # is lost) has a hiriq. The letters are the same, so the points decide, and a
        # word without them is no evidence either way (scene 221, qa).
        return "m" if PATAH in seen[0][1] or QAMATS in seen[0][1] else ""
    if plain == "את" and len(seen) == 2:
        return "f" if SHVA in marks else ""
    if letter == "ת" and len(seen) > 2:
        if QAMATS in marks:
            return "m"
        if SHVA in marks:
            return "f"
    if letter in ("ך", "כ") and plain.lstrip("ו") in KAF_IS_YOU:
        if QAMATS in marks:
            return "m"
        if SHVA in marks:
            return "f"
    return ""


#: Lines where a masculine form rightly addresses a woman: Hebrew's impersonal "you"
#: in a general truth. The corpus gate keeps the same list for the same reason and, on
#: 2026-09-22, the same single entry — arrived at independently, which is the strongest
#: thing that can be said for either. An entry earns its place by being read.
GENERIC_YOU = {
    # "as an instructor you hope, and as an examiner you only see"
    ("78-the-driving-test", 23),
}


def cast_disagrees(line: str, turn: int, addressee: str, scene: str = "") -> Iterator[Finding]:
    """A word pointed for a man where a woman is spoken to, or the other way about.

    Only the forms `addressed_gender` will commit to, and only in a scene where the
    other speaker is who is being addressed — which is what a two-hander is. Hebrew's
    generic 'you' is masculine and is not an error, so this is worth running where the
    addressee is a named person and worth ignoring where they are not.
    """
    if addressee not in ("m", "f") or (scene, turn) in GENERIC_YOU:
        return
    for word in words_of(line):
        says = addressed_gender(word)
        if says and says != addressee:
            yield Finding(
                turn,
                "gender",
                word,
                f"Pointed as spoken to a {'man' if says == 'm' else 'woman'}, "
                f"but the other speaker is a {'man' if addressee == 'm' else 'woman'}.",
            )


# --------------------------------------------------------------------------- numbers


#: Only the scale words, and only the ones whose value is not in doubt. Comparing every
#: numeral either way round founders on 'fifteen hundred', which is אלף וחמש מאות and
#: shares no numeral with its English at all. The scales do not have that problem.
SCALES_HE = {
    "מאה": 100,
    "מאות": 100,
    "אלף": 1000,
    "אלפים": 1000,
    "מיליון": 1000000,
    "מיליוני": 1000000,
}
SCALES_EN = {
    "hundred": 100,
    "hundreds": 100,
    "thousand": 1000,
    "thousands": 1000,
    "million": 1000000,
    "millions": 1000000,
    "k": 1000,
}


#: The one-letter prefixes Hebrew glues to the front of a word. A scale word wears them
#: like any other — scene 92 said לְמֵאָה, not מֵאָה, and matching the bare word alone
#: missed the very line this check was written for.
PREFIXES = "ובלכמהשׁכש"


def scale_of(word: str) -> int:
    """The scale a word names, through any prefixes it is wearing, or 0."""
    plain = bare(word)
    for cut in range(3):
        if cut and (len(plain) <= cut + 1 or plain[cut - 1] not in PREFIXES):
            break
        if plain[cut:] in SCALES_HE:
            return SCALES_HE[plain[cut:]]
    return 0


def scales_disagree(hebrew: str, english: str, turn: int) -> Iterator[Finding]:
    """The Hebrew says hundred where the English says thousand, or the reverse.

    Scene 92 said `אֶחָד לְמֵאָה` beside 'So one in a thousand', in a line whose own
    arithmetic — half a per cent of patients, one in five of those — settles it at a
    thousand. A reader comparing the two halves sees the contradiction; nobody had.
    """
    mine = {v for w in words_of(hebrew) if (v := scale_of(w))}
    said = (english or "").lower()
    theirs = {SCALES_EN[w] for w in re.findall(r"[a-z]+", said) if w in SCALES_EN}
    # 'Fifteen hundred' is a thousand and a half, and Hebrew says so: אלף וחצי. English
    # counts hundreds past a thousand and Hebrew does not, so a hundred here is also a
    # thousand. Without this the idiom is a contradiction in every scene that uses it.
    if re.search(
        r"\b(eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|"
        r"eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|"
        r"ninety|\d{2,})\s+hundred\b",
        said,
    ):
        theirs.add(1000)
    # Disjoint, not merely different: a line saying 'a hundred or two thousand' has
    # both scales on one side and one on the other, and that is not a contradiction.
    if mine and theirs and not (mine & theirs):

        def say(values: set[int]) -> str:
            return ", ".join(f"{value:,}" for value in sorted(values))

        yield Finding(
            turn,
            "mismatch",
            "",
            f"The Hebrew counts in {say(mine)} and the English in {say(theirs)}.",
        )


# ------------------------------------------------------------------ across the corpus


def inconsistent_pointing(scenes: dict[str, list[str]], least: int = 2) -> list[str]:
    """Words the corpus points two different ways, minority spelling first.

    This knows no Hebrew at all. It says only that one word cannot be two words, which
    is enough: `מוּכָּר` for 'salesman' stood in two scenes and `מוֹכֵר` in others, and
    whichever is right, they are not both. Returned as lines of text rather than
    findings because the fault is in the corpus and not in any one turn.
    """
    spellings: dict[str, dict[str, int]] = {}
    for lines in scenes.values():
        for line in lines:
            for word in words_of(line):
                if not POINTS.search(word):
                    continue
                spellings.setdefault(bare(word), {}).setdefault(word, 0)
                spellings[bare(word)][word] += 1
    out = []
    for plain, forms in sorted(spellings.items()):
        if len(forms) < least:
            continue
        ordered = sorted(forms.items(), key=lambda kv: (kv[1], kv[0]))
        shown = "  ".join(f"{form}×{count}" for form, count in ordered)
        out.append(f"{plain}: {shown}")
    return out


# ------------------------------------------------------- pointing rules (#563, pattern B)
#
# From ling-he's scene audit of 2026-10-29. Each is decidable from the points. The kinds
# are `pointing`, `homograph`, `speaker` and `addressee`, not `nikkud` or `gender`, so a
# scene generator that files those two as notes refuses on these. Full spelling under
# points (חִיבּוּר for חִבּוּר) is not here: deciding it needs a lexicon, and it lives
# with one in `vocalize/menukad.py`.

SEGOL, TSERE, HIRIQ, HOLAM = "ֶ", "ֵ", "ִ", "ֹ"

#: The kinds that are the diacritizer's and not the writer's: a scene generator puts them
#: through `dialogue.spelling.repair` and never sends them back to the writer, who writes
#: without points (qa on #986). Every other kind is about the words.
POINTING_KINDS = frozenset({"nikkud", "pointing", "homograph"})

#: The letters a prefix can be: the article's ה, the prepositions, the conjunction, שֶׁ.
PREFIX_LETTERS = "ובכלמשה"

#: The six that take a soft dagesh. After a vowel or a vocal shva they take none; a dagesh
#: in any other letter is a doubling, and a doubling needs a full vowel before it.
BEGADKEFAT = "בגדכפת"

#: The prefixes that carry a shva: the prepositions and the conjunction. Not שׁ, whose
#: shva is a root's (שְׁתַּיִם keeps the one dagesh after a shva Hebrew has).
SHVA_PREFIXES = "בכלו"


def second_feminine_shva(line: str, turn: int) -> Iterator[Finding]:
    """קָנִיתְ: a 2fs past ending in ־ִית takes no shva on the tav (קָנִית, הָיִית)."""
    for word in words_of(line):
        seen = units(word)
        if len(seen) < 3:
            continue
        (tav, last), (yod, before), (_, vowel) = seen[-1], seen[-2], seen[-3]
        if (
            tav == "ת"
            and SHVA in last
            and yod == "י"
            and not before
            and (HIRIQ in vowel or TSERE in vowel)
        ):
            yield Finding(turn, "pointing", word, "A 2fs past in ־ית takes no shva on its tav.")


def _after_prefixes(seen: list[tuple[str, str]]) -> int:
    """Where the article could stand: after a leading ו and a שֶׁ, if the word has them."""
    at = 0
    if at < len(seen) - 2 and seen[at][0] == "ו" and (SHVA in seen[at][1] or DAGESH in seen[at][1]):
        at += 1
    if at < len(seen) - 2 and seen[at][0] == "ש" and SEGOL in seen[at][1]:
        at += 1
    return at


def article_without_dagesh(line: str, turn: int) -> Iterator[Finding]:
    """לַקוּרְס, בַּצֵל: the article's patah doubles the letter after it, so a non-guttural
    with a full vowel there takes a dagesh. Before a shva the dagesh may drop (הַמְלַמֵּד),
    so a shva is let pass, and so is י, for בַּיִת."""
    for word in words_of(line):
        seen = units(word)
        at = _after_prefixes(seen)
        if len(seen) - at < 3:
            continue
        (prefix, marks), (letter, after) = seen[at], seen[at + 1]
        if prefix not in "הבלכ" or PATAH not in marks:
            continue
        if letter in GUTTURALS or letter == "י" or DAGESH in after:
            continue
        if letter == "ו" and seen[at + 2][0] == "ו":
            continue  # a borrowed word spelled with וו (WhatsApp), not a doubled vav
        vowel = any(v in after for v in VOWELS) or (
            not after and at + 2 < len(seen) and seen[at + 2] in (("ו", HOLAM), ("ו", DAGESH))
        )
        if vowel:
            yield Finding(
                turn,
                "pointing",
                word,
                f"The article doubles {letter}: it needs a dagesh after {prefix}{PATAH}.",
            )


def spurious_dagesh(line: str, turn: int) -> Iterator[Finding]:
    """A dagesh where none can stand: in the letter after a prefix's vocal shva
    (בְּגַּעְתּוֹן), in a letter outside begadkefat after any shva (תִּשְׁלְּחִי), and in a
    begadkefat after the vocal shva that follows a long vowel (תֵּרְדִּי).

    ב, כ and פ straight after a prefix are let pass: a borrowed word keeps its b, k or p
    behind one (בְּבִּיט), and nothing in the points says which words are borrowed."""
    for word in words_of(line):
        seen = units(word)
        for n in range(1, len(seen)):
            letter, marks = seen[n]
            before_letter, before = seen[n - 1]
            if DAGESH not in marks or SHVA not in before or letter == "ו":
                continue
            if letter == "ה" and n == len(seen) - 1:
                continue  # a mappiq
            if n == 1 and before_letter in SHVA_PREFIXES:
                wrong = letter not in "בכפ"
            elif letter not in BEGADKEFAT:
                wrong = True
            else:
                # After a tsere the shva is vocal (תֵּרְדִי). Not after a holam: יָכֹלְתִּי
                # is right, and its shva is silent.
                wrong = n >= 2 and TSERE in seen[n - 2][1]
            if wrong:
                yield Finding(
                    turn,
                    "pointing",
                    word,
                    f"A dagesh in {letter} after a shva, where none can stand.",
                )
                break


def bit_without_dagesh(line: str, turn: int) -> Iterator[Finding]:
    """Bit, the payment app, is said with a b behind any prefix: בְּבִּיט, never בְּבִיט
    ("be-vit"). One brand, named because three scenes had it wrong."""
    for word in words_of(line):
        plain = bare(word)
        seen = units(word)
        for cut in range(3):
            if cut and (cut >= len(plain) or plain[cut - 1] not in PREFIX_LETTERS):
                break
            if plain[cut:] == "ביט" and DAGESH not in seen[cut][1]:
                yield Finding(turn, "pointing", word, "Bit takes a dagesh in its ב.")
                break


# ---------------------------------------------------------- homographs (#563, pattern C)


@dataclass(frozen=True)
class Homograph:
    """A pointing that makes another word, and what in the English says it was meant.

    `written` is the pointed form as it stands (prefixes in front of it are allowed, and
    the first letter's dagesh, which a prefix takes away or gives); `meant` is the word
    the English asks for. `when` must match the turn's English and `unless` must not;
    with neither, the form is wrong wherever it stands. A closed list, like
    `KAF_IS_YOU`: each entry is a pair the audit found, and the English is what decides
    it, so nothing here guesses at meaning.
    """

    written: str
    meant: str
    gloss: str
    when: str = ""
    unless: str = ""


HOMOGRAPHS = (
    Homograph("פֶּה", "פֹּה", "פֶּה is mouth; here is פֹּה", r"\bhere\b", r"\bmouths?\b"),
    Homograph("שָׁם", "שֵׁם", "שָׁם is there; a name is שֵׁם", r"\bnames?\b", r"\bthere\b"),
    Homograph("מַרְאֶה", "מַרְאָה", "מַרְאֶה is appearance; a mirror is מַרְאָה", r"\bmirror"),
    Homograph("צִיּוֹן", "צִיּוּן", "צִיּוֹן is Zion; a grade is צִיּוּן", r"\b(grade|mark|score)s?\b"),
    Homograph("זָקֵן", "זָקָן", "זָקֵן is an old man; a beard is זָקָן", r"\bbeard"),
    Homograph("סִפְרִי", "סַפְּרִי", "סִפְרִי is count!; tell! is סַפְּרִי", r"\btell\b"),
    Homograph("בִּפְנִים", "בַּפָּנִים", "בִּפְנִים is inside; to my face is בַּפָּנִים", r"\bfaces?\b"),
    Homograph("נָתְנוּ", "נָתַנּוּ", "נָתְנוּ is they gave; we gave is נָתַנּוּ", r"\bwe\b", r"\bthey\b"),
    Homograph("חוֹדָשַׁיִם", "חׇדְשַׁיִם", "no such word: two months is חׇדְשַׁיִם"),
    Homograph("סָבְתָא", "סַבְתָּא", "grandma is סַבְתָּא"),
)


def _same_form(word: str, written: str) -> bool:
    """Whether `word` is `written` behind up to three prefix letters, the first letter's
    dagesh aside."""
    have, want = units(word), units(written)
    cut = len(have) - len(want)
    if cut < 0 or cut > 3 or any(letter not in PREFIX_LETTERS for letter, _ in have[:cut]):
        return False

    def key(pairs: list[tuple[str, str]]) -> list[tuple[str, str]]:
        return [
            (letter, "".join(sorted(m for m in marks if not (n == 0 and m == DAGESH))))
            for n, (letter, marks) in enumerate(pairs)
        ]

    return key(have[cut:]) == key(want)


def homographs(hebrew: str, english: str, turn: int) -> Iterator[Finding]:
    said = (english or "").lower()
    for word in words_of(hebrew):
        for entry in HOMOGRAPHS:
            if not _same_form(word, entry.written):
                continue
            if entry.when and not re.search(entry.when, said):
                continue
            if entry.unless and re.search(entry.unless, said):
                continue
            yield Finding(turn, "homograph", word, entry.gloss + ".", entry.meant)
    # Piel שִׁלַּח is to send away; a message is sent in qal (תִּשְׁלְחִי, שָׁלַחְתִּי).
    if re.search(r"\b(send|sent|sending)\b", said) and re.search(
        r"\b(messages?|texts?|e-?mails?|links?|photos?|pictures?)\b", said
    ):
        for word in words_of(hebrew):
            plain, seen = bare(word), units(word)
            at = plain.find("שלח")
            if (
                at >= 0
                and DAGESH in seen[at + 1][1]
                and (PATAH in seen[at][1] or HIRIQ in seen[at][1])
            ):
                yield Finding(
                    turn,
                    "homograph",
                    word,
                    "Piel שִׁלַּח is to send away; a message is sent in qal (שָׁלַח).",
                )


# ------------------------------------------------- the speaker's gender (#563, pattern D)


#: Words in a present's shape that are not a present: יוֹתֵר is CוֹCֵC and means "more".
NOT_PRESENT = frozenset({"יותר"})


def present_gender(word: str) -> str:
    """'m', 'f' or '' — the gender a present-tense form shows, where its points decide it.

    Only the shapes that cannot be anything else: qal's CוֹCֵC / CוֹCֶCֶת and CוֹCֶה /
    CוֹCָה, the derived stems' מְ־ forms in ־ֵC / ־ֶCֶת and ־ֶה / ־ָה, and the nifal's
    נִCְCֶה / נִCְCֵית. A form in ־ה is feminine with a qamats and masculine with a segol,
    which is the whole of רוֹצֶה against רוֹצָה — a difference the letters never show.
    """
    if bare(word).lstrip("ו") in NOT_PRESENT:
        return ""
    seen = units(word)
    if len(seen) > 3 and seen[0][0] == "ו" and (SHVA in seen[0][1] or seen[0][1] == DAGESH):
        seen = seen[1:]
    if len(seen) < 3:
        return ""
    plain = "".join(letter for letter, _ in seen)
    first = seen[0][1]
    qal = seen[1] == ("ו", HOLAM) or HOLAM in first
    derived = plain[0] == "מ" and any(v in first for v in (SHVA, PATAH, *HATAFS))
    nifal = plain[0] == "נ" and HIRIQ in first and SHVA in seen[1][1]
    last, end = seen[-1]
    before = seen[-2][1]
    if last == "ה" and not end:
        stem = seen[:-1]
        short = (len(stem) == 3 and stem[1] == ("ו", HOLAM)) or (len(stem) == 2 and HOLAM in first)
        if short or derived or nifal:
            if SEGOL in before:
                return "m"
            if QAMATS in before:
                return "f"
        return ""
    if last == "ת" and not end:
        if nifal and plain.endswith("ית") and TSERE in seen[-3][1]:
            return "f"
        if len(seen) >= 4 and (qal or derived):
            if any(v in before for v in (SEGOL, PATAH)) and any(
                v in seen[-3][1] for v in (SEGOL, PATAH)
            ):
                return "f"
        return ""
    if (not end or (last in "חע" and end == PATAH)) and TSERE in before:
        if (len(seen) == 4 and seen[1] == ("ו", HOLAM)) or (derived and len(seen) >= 4):
            return "m"
    return ""


#: What may stand between אני and its verb: negation and a closed set of adverbs. Anything
#: else ends the search, so the object of another verb (אֲנִי אֶקְנֶה כּוֹתֵב) is never read
#: as the speaker's present.
BETWEEN = frozenset(
    "לא כבר עוד פשוט גם ממש רק תמיד עדיין באמת די קצת בדיוק סתם עכשיו כרגע אף פעם".split()
)

#: Words that stand for someone else as a subject; a sentence holding one is not about
#: the speaker or the listener.
OTHER_SUBJECTS = {"הוא", "היא", "אנחנו", "הם", "הן", "זה", "זאת", "זו"}

_SENTENCE = re.compile(r"[^.?!…]+")


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE.findall(text or "") if s.strip()]


def _say(gender: str) -> str:
    return "a man" if gender == "m" else "a woman"


def speaker_disagrees(hebrew: str, english: str, turn: int, speaker: str) -> Iterator[Finding]:
    """אֲנִי רוֹצֶה in a woman's mouth: a first-person present that does not agree with
    the speaker's cast gender.

    The subject is אני, with the present within three words after it in the same
    sentence. Hebrew drops אני in a running commentary (עוֹלָה לְמַעְלָה, "I'm coming up");
    there the English decides it, where the turn has as many sentences in each language
    and the matching English one begins with "I'm" or "I am"."""
    if speaker not in ("m", "f"):
        return
    flagged: set[str] = set()
    for sentence in _sentences(hebrew):
        words = list(words_of(sentence))
        for at, word in enumerate(words):
            if bare(word).lstrip("ו") != "אני":
                continue
            for after in words[at + 1 : at + 4]:
                gender = present_gender(after)
                if not gender:
                    if bare(after) in BETWEEN:
                        continue
                    break
                if gender:
                    if gender != speaker and after not in flagged:
                        flagged.add(after)
                        yield Finding(
                            turn,
                            "speaker",
                            after,
                            f"The form for {_say(gender)}, but the speaker is {_say(speaker)}.",
                        )
                    break
    hebrew_sentences, english_sentences = _sentences(hebrew), _sentences(english)
    if len(hebrew_sentences) != len(english_sentences):
        return
    for sentence, said in zip(hebrew_sentences, english_sentences, strict=True):
        words = list(words_of(sentence))
        if not words or not re.match(r"i('m|’m| am)\b", said.strip("\"'“” ").lower()):
            continue
        gender = present_gender(words[0])
        if gender and gender != speaker and words[0] not in flagged:
            flagged.add(words[0])
            yield Finding(
                turn,
                "speaker",
                words[0],
                f"The form for {_say(gender)}, but the speaker is {_say(speaker)}.",
            )


#: English verbs a scene's imperative opens with. A list rather than a test of the word's
#: shape, because "Valid is what the system accepts" and "Nineteen years" open on a word
#: that is not a verb, and the Hebrew beside them (תַּקִּין, תֵּשַׁע) starts with ת as a
#: future does.
IMPERATIVES = frozenset(
    "come go tell take give send wait look call bring put sit close open try write sign "
    "keep stop check pay leave show say ask get make do eat drink buy turn read listen "
    "remember forget hold stay move meet help use think start walk drive park choose pick "
    "wear run finish enter press click fill charge return cancel book order explain speak "
    "talk answer find let don't be have".split()
)


def addressee_disagrees(hebrew: str, english: str, turn: int, addressee: str) -> Iterator[Finding]:
    """A present or a future pointed for the wrong listener where no אתה or את says so,
    which `cast_disagrees` cannot see. Only where the turn has as many sentences in each
    language, and in two shapes:

    - the English sentence says "you" and no other subject, the Hebrew one names no
      subject and holds exactly one present whose points decide it (נִרְאֵית to a man);
    - the English sentence is an imperative and the Hebrew one opens on a second-person
      future: ת־ with no ending is a man (תָּבוֹא), with ־י a woman (תָּבוֹאִי).
    """
    if addressee not in ("m", "f"):
        return
    hebrew_sentences, english_sentences = _sentences(hebrew), _sentences(english)
    if len(hebrew_sentences) != len(english_sentences):
        return
    for sentence, said in zip(hebrew_sentences, english_sentences, strict=True):
        words = list(words_of(sentence))
        if not words:
            continue
        plain = [bare(w).lstrip("ו") for w in words]
        tokens = re.findall(r"[a-z’']+", said.lower())
        if (
            re.search(
                r"\byou(’re|'re| are| were| look\w*| seem\w*| sound\w*| feel\w*)\b", said.lower()
            )
            and not {"i", "he", "she", "it", "we", "they", "i'm", "i’m"} & set(tokens)
            and not ({"אני", "אתה", "את"} | OTHER_SUBJECTS) & set(plain)
        ):
            genders = [(w, g) for w in words if (g := present_gender(w))]
            if len(genders) == 1 and genders[0][1] != addressee:
                word, gender = genders[0]
                yield Finding(
                    turn,
                    "addressee",
                    word,
                    f"The form for {_say(gender)}, but the listener is {_say(addressee)}.",
                )
                continue
        if not tokens or tokens[0] not in IMPERATIVES:
            continue
        seen = units(words[0])
        if (
            len(seen) >= 3
            and seen[0][0] == "ת"
            and any(v in seen[0][1] for v in (QAMATS, HIRIQ, PATAH, SEGOL, TSERE))
            and plain[0][-1] not in "הו"
            and not plain[0].endswith(("ות", "ים"))
        ):
            gender = "f" if plain[0].endswith("י") else "m"
            if gender != addressee:
                yield Finding(
                    turn,
                    "addressee",
                    words[0],
                    f"Pointed as said to {_say(gender)}, but the listener is {_say(addressee)}.",
                )


# ----------------------------------------------------------------------------- all


def check_turn(
    hebrew: str,
    english: str,
    turn: int,
    addressee: str = "",
    scene: str = "",
    speaker: str = "",
) -> list[Finding]:
    """Everything decidable about one turn. `speaker` is the cast gender of whoever says
    it; without it the speaker check is skipped, as the listener's are without
    `addressee`."""
    found: list[Finding] = []
    found += impossible_dagesh(hebrew, turn)
    found += hataf_on_non_guttural(hebrew, turn)
    found += cast_disagrees(hebrew, turn, addressee, scene)
    found += scales_disagree(hebrew, english, turn)
    found += second_feminine_shva(hebrew, turn)
    found += article_without_dagesh(hebrew, turn)
    found += spurious_dagesh(hebrew, turn)
    found += bit_without_dagesh(hebrew, turn)
    found += homographs(hebrew, english, turn)
    found += speaker_disagrees(hebrew, english, turn, speaker)
    if (scene, turn) not in GENERIC_YOU:
        found += addressee_disagrees(hebrew, english, turn, addressee)
    return found


# ------------------------------------------------------------------------- voices


#: Google's published genders for the Gemini prebuilt voices, which are what a scene's
#: `cast` names. A man read by Leda is not a subtle fault — it is the first thing a
#: listener notices and the last thing anybody thinks to check, because the text, the
#: cast and the audio are three artifacts and only two of them are ever read.
#:
#: This is a table and not a guess: a voice missing from it is reported rather than
#: assumed, so adding a voice to a scene without adding it here fails loudly.
FEMALE_VOICES = {
    "Zephyr",
    "Kore",
    "Leda",
    "Aoede",
    "Callirrhoe",
    "Autonoe",
    "Despina",
    "Erinome",
    "Laomedeia",
    "Achernar",
    "Gacrux",
    "Pulcherrima",
    "Vindemiatrix",
    "Sulafat",
}
MALE_VOICES = {
    "Puck",
    "Charon",
    "Fenrir",
    "Orus",
    "Enceladus",
    "Iapetus",
    "Umbriel",
    "Algieba",
    "Algenib",
    "Rasalgethi",
    "Alnilam",
    "Schedar",
    "Achird",
    "Zubenelgenubi",
    "Sadachbia",
    "Sadaltager",
}


def voice_gender(voice: str) -> str:
    """'m', 'f', or '' where the voice is not one this table knows."""
    if voice in FEMALE_VOICES:
        return "f"
    if voice in MALE_VOICES:
        return "m"
    return ""


def cast_voices_disagree(cast: dict[str, dict[str, str]]) -> list[str]:
    """Speakers whose voice does not match the gender they are declared to be.

    Checked over the hundred scenes on 2026-09-22: none of the two hundred speakers
    disagreed, and the six scenes voiced by two men are six scenes with two men in them.
    The check stays because the cast is edited by hand and the audio is generated from
    it, so the two can drift apart silently — and by the time anybody notices, it is
    because a reader heard it.
    """
    out = []
    for side in ("A", "B"):
        who = cast.get(side) or {}
        voice, gender = str(who.get("voice") or ""), str(who.get("gender") or "")
        said = voice_gender(voice)
        if not voice:
            continue
        if not said:
            out.append(f"{side}: the voice {voice} is not in the table, so nothing can be said")
        elif gender and said != gender:
            name = who.get("name") or side
            out.append(f"{side} ({name}): declared {gender}, but the voice {voice} is {said}")
    return out


# ----------------------------------------------------------- telling the engine how


def pronunciation_hints(text: str, addressee: str = "") -> list[str]:
    """What a speech engine cannot work out from the letters, said in words.

    Gemini ignores nikkud — a pointed line and the same line stripped of every vowel
    come back identical (measured 2026-08-30) — so it reads Hebrew the way a literate
    Israeli reads unpointed text: from context, fluently, and sometimes wrong. On
    `עזבת` that is a coin toss between *azavta* and *azavt*, and a learner who hears
    the wrong one is being taught the wrong one, in the single channel they cannot
    check against the page.

    **targum holds the answer and throws it away.** The pointing says which form it is.
    The engine will not read the pointing, but it will take an instruction: told in
    the prompt how a word is stressed, it changed the reading. So the pointing is
    turned into an instruction here.

    Only the genuinely ambiguous forms get a hint — the ones whose *letters* are the
    same either way. `אתה` is never `את`, so it is left alone; `את` is `at` or `et`,
    and the ending of `עזבת` is `-ta` or `-t`, and those are said.
    """
    # Grouped by what is said about them, not one line per word. Two words can want
    # the identical instruction — אמרת and ואמרת differ by a conjunction and end the
    # same way — and prompt length is the thing that makes this API fail: a 497
    # character prompt was rejected four times in five, a 109 character one never.
    grouped: dict[str, list[str]] = {}
    for word in words_of(text):
        says = addressed_gender(word)
        if not says:
            continue
        plain = bare(word)
        units_ = units(word)
        if not units_:
            continue
        last = units_[-1][0]
        # A leading conjunction does not change the word: ואת is still את.
        stem = plain[1:] if plain[:1] == "\u05d5" and len(plain) > 2 else plain
        if stem == "\u05d0\u05ea":
            said = '"at", the word for "you" to a woman — not "et", the object marker'
        elif last == "\u05ea":
            said = 'ends "-t", the feminine' if says == "f" else 'ends "-ta", the masculine'
        elif last in ("\u05da", "\u05db"):
            said = 'ends "-akh", the feminine' if says == "f" else 'ends "-kha", the masculine'
        else:
            continue
        if addressee and says != addressee:
            # The line disagrees with the cast. Say what is written, not what is meant:
            # the text is the thing being read aloud, and a hint that contradicts it
            # would have the engine say a word that is not on the page.
            said += " (as written, though the cast says otherwise)"
        if plain not in grouped.setdefault(said, []):
            grouped[said].append(plain)
    return [f"{', '.join(words)}: {said}" for said, words in grouped.items()]
