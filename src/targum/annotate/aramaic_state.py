"""The emphatic state, read off the pointing: Aramaic's second hard spot (design.md §12,
"Aramaic has a hard-spot list" and "Aramaic's lenses", 2026-10-25).

Aramaic says "the" with an ending, not a prefix: אַרְעָא is הָאָרֶץ, מַיָּא is הַמַּיִם, and
the plural's ־יָּא is the stars of כּוֹכְבַיָּא. A reader who comes from Hebrew looks for ה־
at the front and finds nothing, so the state lens lights the words that carry the ending.

**The rule.** A word ends in א, and the letter before it is pointed with a qamats. That is
the emphatic of every noun, adjective and participle in Onkelos, singular (־ָא), plural
(־יָּא) and feminine (־תָא). It also catches words that only look the part, and three
checks take them out:

- **The particles** that end in ־ָא: לָא, הָא, דָא, הֲדָא, חֲדָא, דִּלְמָא and the rest of
  `NOT_EMPHATIC`, with ו or another of the prefix letters on the front or not.
- **A verb the hand table knows** (`closed.TARGUM`): its gloss says "to …" (קְרָא, חֲזָא),
  and a verb has no state.
- **The perfect of a weak verb**, CְCָא: three letters, a shva or hataf on the first and
  no dagesh in the second (בְּרָא, רְמָא, בְּנָא), and the same behind ו or ב. Nouns of three
  letters double their middle letter or carry a full vowel first (יַמָּא, חַיָּא, דְּמָא is
  the one loss).

Biblical Aramaic writes some emphatics with ה (עִלָּאָה, רָזָה), and Onkelos does not, so the
rule reads א alone: it is the Targum's spelling, and the floor says what it costs in Daniel.

**Measured, not trusted.** `scripts/eval_aramaic_state.py` scores it against Open
Scriptures' state letter (`Ncmsd`) over the Aramaic of Daniel and Ezra, the one Aramaic
with hand-tagged state. It is not held out: the checks above were found reading that text
and Onkelos Genesis 1–3, so the floor is a guard against getting worse rather than an
estimate on unseen text. ling-arc's hand gold on Onkelos is the estimate, and is owed.

**The absolute and the construct** (2026-11-24) are the lens's other two states, shown one
at a time as design.md asks. Each is lit only where its form says so, and a word whose form
does not is left unlit rather than guessed:

- **Absolute**: the plural's ־ִין, which has no "the" (שְׁנִין, "years"; בְּנִין, "sons").
  Not a participle: פָּלְחִין "serving" is a verb to the reader, and the participle lens
  that is to come is its place, so CָCְCִין and the derived stems' מְ־/מִתְ־ are left out,
  as is anything the hand table glosses "to …". The singular absolute (מֶלֶךְ) looks the
  same as the singular construct, and is not lit.
- **Construct**, "of", bound to the word after it: the plural's ־ֵי (בְּנֵי, יוֹמֵי, אַפֵּי),
  ־וּת (בִּמְצִיעוּת, "in the midst of"), a feminine ־ַת the table knows as a noun, and כָּל
  and בֵּית, which the Targum writes in no other state before a noun. Less what ends the same
  way and is not a noun: אֲרֵי "for", לְוַת "to", the imperfect (יְהֵי), the infinitive
  (לְמֶחֱזֵי), the afel (אַסְגֵּי) and the participle (גָּלֵי, יָדְעֵי). And a singular the
  table knows as a noun, with no ending of its own, standing before a word in the emphatic
  or a name with no ו or preposition on its front: בֵּית אֲבוּהִי, אֱלָהּ אַבְרָהָם. Not before
  anything else: מֶלֶךְ רַב is "a great king", and nothing on the page says which.

`scripts/eval_aramaic_state.py` scores both against the same state letters, a word gold
only where Open Scriptures tags a noun or an adjective (no participle, no name) in that
state, and, for the construct, with no pronoun on it: OSHB files בַּיְתֵהּ as construct,
and the suffix lens is where an ending shows.

An unpointed word says nothing, and answers no: the Gemara is printed unpointed, and the
lens is not offered on it until a rule for it is written and measured.
"""

from __future__ import annotations

from .aramaic import key, look_up
from .vav_consecutive import pointed_letters

NAME = "arc-state/2"

QAMATS = "ָ"
SHVA = "ְ"
HATAF = frozenset({"ֱ", "ֲ", "ֳ"})
DAGESH = "ּ"

#: Words that end in ־ָא and are not a noun in the emphatic: negation, demonstratives,
#: pronouns, "one" in the feminine, "lest", "here" and "there". Folded spellings.
NOT_EMPHATIC = frozenset(
    {
        "לא",
        "הלא",
        "דא",
        "הא",
        "כא",
        "מא",
        "הכא",
        "תמא",
        "מכא",
        "היכא",
        "אנא",
        "אנחנא",
        "אנתא",
        "חדא",
        "הדא",
        "דילמא",
        "דלמא",
        "כדנא",
    }
)


def _weak_perfect(letters: list[tuple[str, frozenset[str]]]) -> bool:
    """CְCָא: the perfect of a verb whose last root letter is weak, "he created"."""
    if len(letters) != 3:
        return False
    first, second = letters[0][1], letters[1][1]
    return (SHVA in first or bool(first & HATAF)) and DAGESH not in second


def emphatic(word: str) -> bool:
    """Whether a pointed Aramaic word is in the emphatic state."""
    letters = pointed_letters(word)
    if len(letters) < 2 or letters[-1][0] != "א" or QAMATS not in letters[-2][1]:
        return False
    folded = key(word)
    if folded in NOT_EMPHATIC:
        return False
    # Before the table: it files הֲוָא, "he was", under the pronoun הוּא.
    if _weak_perfect(letters):
        return False
    # The same behind ו or ב: וּרְמָא, "and he cast".
    if len(letters) == 4 and letters[0][0] in "וב" and _weak_perfect(letters[1:]):
        return False
    found = look_up(word)
    if found is not None:
        from .closed import TARGUM_GLOSSES

        if key(found.headword) in NOT_EMPHATIC:
            return False
        if TARGUM_GLOSSES.get(found.headword, "").startswith("to "):
            return False
    return True


PATAH = "ַ"
TSERE = "ֵ"
HIRIQ = "ִ"
SHVAS = frozenset({SHVA, *HATAF})
VOWELS = frozenset("ְֱֲֳִֵֶַָֹֻ")

#: The one-letter words that go on the front, for the forms below.
FRONT = "ובדלכ"

#: Words the Targum writes only in the construct before a noun: "all of", "house of".
ALWAYS_CONSTRUCT = frozenset({"כל", "בית"})

#: Words that end like a construct and are not a noun: "for", "to", "you", "after".
NOT_CONSTRUCT = frozenset({"ארי", "לות", "את", "אחרי"})

#: Words the table knows that do not head a construct: particles, prepositions and
#: pronouns, folded as `key` folds them.
FUNCTION = frozenset(
    key(word)
    for word in (
        "די מן על קדם עם עד כען הוא היא מה קבל לקבל אלין לא אנון אנין הא דא אן אף הן כדי "
        "בין תמן כן כדו אנא את אתון אנת אנתון הדין דין אלו ארו לות בתר ברם בגין מטול עוד "
        "כמה כל ארי אחרי ית יי אלהים תחות מתחות מעל הדא הדין אלין דילמא"
    ).split()
)


def _bare_front(word: str) -> str:
    """The word folded, with up to two of the letters that go on the front taken off where
    what is left is one of the words named above."""
    folded = key(word)
    for cut in (0, 1, 2):
        if cut and (len(folded) <= cut + 1 or folded[cut - 1] not in FRONT):
            break
        stem = folded[cut:]
        if stem in ALWAYS_CONSTRUCT or stem in NOT_CONSTRUCT:
            return stem
    return folded


def _participle(stem: list[tuple[str, frozenset[str]]]) -> bool:
    """The letters before an ending are a participle of the first stem: CָCְC, or the
    hollow CָיְC (פָּלְח־, דָּיְר־), behind one of the front letters or not."""
    if len(stem) == 4 and stem[0][0] in FRONT:
        stem = stem[1:]
    return len(stem) == 3 and QAMATS in stem[0][1] and (SHVA in stem[1][1] or stem[1][0] == "י")


def _derived(letters: list[tuple[str, frozenset[str]]]) -> bool:
    """A participle of a derived stem: מְ־, מִתְ־, מַ־ with a shva after it."""
    at = 1 if letters[0][0] in FRONT and len(letters) > 4 else 0
    first = letters[at]
    return first[0] == "מ" and bool(first[1] & (SHVAS | {HIRIQ}))


def _finite(letters: list[tuple[str, frozenset[str]]]) -> bool:
    """A verb that ends in ־ֵי: the imperfect, the infinitive, the afel, the weak
    participle CָCֵי."""
    if (
        letters[0][0] == "ו"
        and HIRIQ in letters[0][1]
        and len(letters) > 1
        and letters[1][0] == "י"
    ):
        return True  # וִיחֵי: ו before an imperfect's yod
    core = letters[1:] if letters[0][0] in "וד" and len(letters) == 4 else letters
    if len(core) == 3 and QAMATS in core[0][1]:
        return True  # גָּלֵי, "he reveals"
    at = 1 if letters[0][0] == "ו" and len(letters) > 3 else 0
    first = letters[at]
    after = letters[at + 1] if len(letters) > at + 1 else ("", frozenset())
    if first[0] == "ל" and after[0] == "מ":
        return True  # לְמֶחֱזֵי, the infinitive
    if first[0] in "יתנא" and first[1] & (SHVAS | {HIRIQ}):
        return True  # יְהֵי, the imperfect
    if first[0] in "יתנא" and PATAH in first[1] and after[1] & SHVAS:
        return True  # אַסְגֵּי, the afel
    return first[0] == "ה" and bool(first[1] & (SHVAS | {PATAH}))


def _gloss(word: str) -> str | None:
    """What the hand table says the word means, "" where it knows the word and has no
    gloss, None where it does not know it."""
    from .closed import TARGUM_GLOSSES

    found = look_up(word)
    if found is None:
        return None
    return TARGUM_GLOSSES.get(found.headword, "")


def _a_verb(word: str) -> bool:
    return (_gloss(word) or "").startswith("to ")


def absolute(word: str) -> bool:
    """Whether a pointed Aramaic word is a plural in the absolute state: ־ִין, no "the"."""
    letters = pointed_letters(word)
    if len(letters) < 3 or letters[-1][0] != "ן" or letters[-2][0] != "י":
        return False
    if HIRIQ not in letters[-3][1]:
        return False
    if _participle(letters[:-2]) or _derived(letters):
        return False
    return not _a_verb(word)


def _construct_form(word: str) -> bool:
    """Whether the word's own form says construct, with nothing after it to go on."""
    stem = _bare_front(word)
    if stem in ALWAYS_CONSTRUCT:
        return True
    if stem in NOT_CONSTRUCT:
        return False
    letters = pointed_letters(word)
    if len(letters) < 3:
        return False
    before, last = letters[-2], letters[-1]
    if last[0] == "י" and not last[1] - {DAGESH} and TSERE in before[1]:
        if _a_verb(word) or _derived(letters) or _finite(letters):
            return False
        return not _participle(letters[:-1])
    if last[0] == "ת" and DAGESH not in last[1]:
        if (
            len(letters) >= 5
            and before[0] == "ו"
            and DAGESH in before[1]
            and not letters[-3][1] & VOWELS
        ):
            return True  # ־וּת
        if PATAH in before[1]:
            gloss = _gloss(word)
            return gloss is not None and not gloss.startswith("to ")
    return False


def construct(word: str, after: str = "", after_is_name: bool = False) -> bool:
    """Whether a pointed Aramaic word is in the construct state, "of", bound to the word
    after it. `after` is that word as pointed, and `after_is_name` whether it is a name;
    without them only the forms that say so themselves are read."""
    if _construct_form(word):
        # Not כָּל־קֳבֵל, "because", which is one word to a reader.
        return not (_bare_front(word) == "כל" and key(after).endswith("קבל"))
    if not after or not (after_is_name or emphatic(after)):
        return False
    # What a construct binds to carries no "and", "in", "to" or "from" of its own: דְּכַר
    # וְנוּקְבָא is "male and female", and תְּרֵין מִכֹּלָּא "two of every kind".
    if key(after)[:1] in "ובלמכ" and not after_is_name:
        heard = look_up(after)
        if heard is None or heard.prefixes:
            return False
    if emphatic(word) or absolute(word):
        return False
    from .aramaic_suffixes import suffix_letters

    if suffix_letters(word):
        return False
    found = look_up(word)
    if found is None or found.name:
        return False
    from .closed import TARGUM_GLOSSES

    gloss = TARGUM_GLOSSES.get(found.headword, "")
    if not gloss or gloss.startswith("to "):
        return False
    stem = key(word)[len(found.prefixes) :]
    if key(found.headword) in FUNCTION or stem in FUNCTION:
        return False
    return gloss.split(";")[0] not in {"from", "with", "before", "now", "these", "but", "to", "in"}


def state(word: str, after: str = "", after_is_name: bool = False) -> str:
    """`Emph`, `Abs` or `Cstr`, or "" where the form does not say."""
    if emphatic(word):
        return "Emph"
    if absolute(word):
        return "Abs"
    if construct(word, after, after_is_name):
        return "Cstr"
    return ""
