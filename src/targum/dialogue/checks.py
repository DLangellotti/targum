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
        return "m"
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


def cast_disagrees(line: str, turn: int, addressee: str) -> Iterator[Finding]:
    """A word pointed for a man where a woman is spoken to, or the other way about.

    Only the forms `addressed_gender` will commit to, and only in a scene where the
    other speaker is who is being addressed — which is what a two-hander is. Hebrew's
    generic 'you' is masculine and is not an error, so this is worth running where the
    addressee is a named person and worth ignoring where they are not.
    """
    if addressee not in ("m", "f"):
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


# ----------------------------------------------------------------------------- all


def check_turn(hebrew: str, english: str, turn: int, addressee: str = "") -> list[Finding]:
    """Everything decidable about one turn."""
    found: list[Finding] = []
    found += impossible_dagesh(hebrew, turn)
    found += hataf_on_non_guttural(hebrew, turn)
    found += cast_disagrees(hebrew, turn, addressee)
    found += scales_disagree(hebrew, english, turn)
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
