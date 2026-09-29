"""What DICTA's reading of a scene says about its numbers and its construct chains.

`checks.py` holds no lexicon, and says why: every rule in it is decidable from the
letters and points alone. The two error kinds targum-internal#134 asks for next are not.
Whether שְׁמוֹנָה is right in front of a noun depends on the noun's gender, and whether a
word may carry the article depends on whether another noun hangs off it. Neither is in
the letters. Both are in what DICTA already says about every word: its part of speech,
its gender, its prefixes, and — from the syntax head — which word governs
which. So these checks live here, beside that reading, and not in `checks.py`.

**The one lexicon is the numerals**, and it is closed: one to ten, each in its forms for
a masculine and a feminine noun, absolute and construct. Nothing else is listed.

**DICTA reads the letters, not the points.** It is handed the pointed line and answers
about the unpointed one, so it cannot tell שְׁמוֹנָה from שְׁמוֹנֶה and it cannot see the
article hidden in בַּ. Those come from the points, here; what comes from DICTA is only
what the points cannot say — the counted noun's gender, and which word governs which.

**The stored annotation cannot drive these on its own.** It keeps Gender and Number, and
`kept_feats` would keep `Definite=Cons`, but DICTA's morphology never emits `Definite`:
over the hundred scenes' annotations, not one token carries it. DICTA marks the construct
state only in its syntax head, as `compound:smixut`, and the annotator discards the
syntax. So a scene is read again with the local model (free, no network) to check it.

`scripts/score_scene_checks.py` scores each of these against the author's settled
corrections. Only the ones in `GATED` passed that, and the module says why beside each.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .checks import DAGESH, GUTTURALS, HATAFS, PATAH, QAMATS, SHVA, Finding, bare, units

SEGOL = "ֶ"
TSERE = "ֵ"
SIN_DOT = "ׂ"


@dataclass(frozen=True)
class Word:
    """One word as DICTA read it, with the pointed surface put back.

    `head` is the index, in the same list, of the word this one hangs off, and
    `relation` is how (`compound:smixut`, `nummod`); -1 and "" where there is no syntax.
    `prefixes` are DICTA's tags for what is glued to the front: DET, ADP, CCONJ, SCONJ.
    `lead` is how many letters those prefixes take up.
    """

    surface: str
    pos: str
    gender: str = ""
    prefixes: tuple[str, ...] = ()
    lead: int = 0
    head: int = -1
    relation: str = ""

    def body(self) -> list[tuple[str, str]]:
        """The word under its prefixes, as (letter, marks) pairs."""
        return units(self.surface)[self.lead :]


def words_from_dicta(said: Mapping[str, Any], text: str) -> list[Word]:
    """DICTA's JSON for one line (`predict(..., output_style="json")`) as words.

    The offsets are into the line DICTA was handed, which was the pointed line, so the
    surface sliced back out of it keeps its points.
    """
    out = []
    for token in said.get("tokens") or []:
        morph = token.get("morph") or {}
        feats = morph.get("feats") or {}
        offsets = token.get("offsets") or {}
        seg = list(token.get("seg") or [])
        syntax = token.get("syntax") or {}
        start, end = int(offsets.get("start", 0)), int(offsets.get("end", 0))
        out.append(
            Word(
                surface=text[start:end] if end > start else str(token.get("token") or ""),
                pos=str(morph.get("pos") or ""),
                gender=str(feats.get("Gender") or ""),
                prefixes=tuple(morph.get("prefixes") or ()),
                lead=len("".join(seg[:-1])) if len(seg) > 1 else 0,
                head=int(syntax.get("dep_head_idx", -1)) if syntax else -1,
                relation=str(syntax.get("dep_func") or ""),
            )
        )
    return out


# --------------------------------------------------------------------------- numerals


@dataclass(frozen=True)
class Numeral:
    """What a numeral says about what it counts: 'm' or 'f', and whether it is the
    construct form (שְׁלוֹשֶׁת) or the absolute (שְׁלוֹשָׁה)."""

    value: int
    gender: str
    construct: bool


#: One to ten, by consonants, each with the gender of noun it goes with. Hebrew's
#: polarity is why this is a table and not a rule: שְׁלוֹשָׁה ends like a feminine word and
#: counts masculine nouns. The feminine forms serve as their own construct.
#: שמונה, עשר and עשרה are absent: their letters are the same for both genders, and
#: only the points tell, so `numeral` reads them from the points.
NUMERALS: dict[str, Numeral] = {
    "אחד": Numeral(1, "m", False),
    "אחת": Numeral(1, "f", False),
    "שניים": Numeral(2, "m", False),
    "שנים": Numeral(2, "m", False),
    "שתיים": Numeral(2, "f", False),
    "שתים": Numeral(2, "f", False),
    "שתי": Numeral(2, "f", True),
    "שלושה": Numeral(3, "m", False),
    "שלשה": Numeral(3, "m", False),
    "שלושת": Numeral(3, "m", True),
    "שלשת": Numeral(3, "m", True),
    "שלוש": Numeral(3, "f", False),
    "שלש": Numeral(3, "f", False),
    "ארבעה": Numeral(4, "m", False),
    "ארבעת": Numeral(4, "m", True),
    "ארבע": Numeral(4, "f", False),
    "חמישה": Numeral(5, "m", False),
    "חמשה": Numeral(5, "m", False),
    "חמשת": Numeral(5, "m", True),
    "חמישת": Numeral(5, "m", True),
    "חמש": Numeral(5, "f", False),
    "שישה": Numeral(6, "m", False),
    "ששה": Numeral(6, "m", False),
    "ששת": Numeral(6, "m", True),
    "שישת": Numeral(6, "m", True),
    "שש": Numeral(6, "f", False),
    "שבעה": Numeral(7, "m", False),
    "שבעת": Numeral(7, "m", True),
    "שבע": Numeral(7, "f", False),
    "שמונת": Numeral(8, "m", True),
    "תשעה": Numeral(9, "m", False),
    "תשעת": Numeral(9, "m", True),
    "תשע": Numeral(9, "f", False),
    "עשרת": Numeral(10, "m", True),
}

#: The words a numeral multiplies rather than counts: three hundred is שְׁלוֹשׁ מֵאוֹת,
#: feminine, and three thousand is שְׁלוֹשֶׁת אֲלָפִים, masculine and construct.
HUNDREDS, THOUSANDS = "מאות", "אלפים"


def _vowel(marks: str) -> str:
    return "".join(m for m in marks if m not in (DAGESH, SIN_DOT, "ׁ"))


def numeral(word: Word) -> Numeral | None:
    """The numeral a word is, read from its points where its letters leave it open.

    `שני` is two only as שְׁנֵי; as שֵׁנִי it is second, or Monday. שמונה is masculine as
    שְׁמוֹנָה and feminine as שְׁמוֹנֶה. `עשר` alone is ten, feminine, as עֶשֶׂר; `עשרה` is
    ten, masculine, as עֲשָׂרָה. The other readings of those two are the teens' second
    word, and `teen` reads them. A word whose points do not decide is not a numeral here.
    """
    body = word.body()
    if not body:
        return None
    plain = "".join(letter for letter, _ in body)
    first = body[0][1]
    if SIN_DOT in first and plain in ("שבע", "שבעה", "שש", "ששה"):
        return None  # שָׂבֵעַ, full; שָׂשׂ, glad
    if plain == "שני":
        return Numeral(2, "m", True) if SHVA in first else None
    if plain == "שמונה" and len(body) == 5:
        before_he = _vowel(body[3][1])
        if QAMATS in before_he:
            return Numeral(8, "m", False)
        if SEGOL in before_he:
            return Numeral(8, "f", False)
        return None
    if plain == "עשר" and len(body) == 3:
        return Numeral(10, "f", False) if SEGOL in _vowel(body[1][1]) else None
    if plain == "עשרה" and len(body) == 4:
        return Numeral(10, "m", False) if any(h in first for h in HATAFS) else None
    return NUMERALS.get(plain)


def teen(word: Word) -> str:
    """'m' or 'f' where a word is a teen's second half — עָשָׂר or עֶשְׂרֵה — else ''."""
    body = word.body()
    plain = "".join(letter for letter, _ in body)
    if plain == "עשר" and len(body) == 3 and QAMATS in _vowel(body[1][1]):
        return "m"
    if plain == "עשרה" and len(body) == 4 and TSERE in _vowel(body[2][1]):
        return "f"
    return ""


def _noun_gender(word: Word) -> str:
    """'m' or 'f' where DICTA commits to one, else ''."""
    return {"Masc": "m", "Fem": "f"}.get(word.gender, "")


def _counted(word: Word) -> bool:
    """Whether a word right after a numeral is what it counts.

    A noun with a preposition on it is not: שְׁתַּיִם בַּלַּיְלָה is two at night, not two
    nights, and בְּשֶׁבַע בַּבּוֹקֶר is seven in the morning.
    """
    return word.pos == "NOUN" and not set(word.prefixes) - {"DET", "CCONJ"}


def _said(gender: str) -> str:
    return "feminine" if gender == "f" else "masculine"


def _next(words: Sequence[Word], at: int) -> Word | None:
    return words[at + 1] if at + 1 < len(words) else None


def numeral_agreement(words: Sequence[Word], turn: int) -> Iterator[Finding]:
    """A numeral in the other gender from the noun it counts, or from its own teen.

    Three shapes, all read the same way — the numeral's gender from its points, the
    noun's from DICTA:

    - a numeral straight before a noun it counts: שְׁמוֹנָה יְחִידוֹת;
    - a numeral before מֵאוֹת, which is feminine, or אֲלָפִים, which takes the masculine
      construct: שְׁמוֹנָה מֵאוֹת;
    - the two halves of a teen disagreeing with each other: שְׁמוֹנֶה עָשָׂר.

    אֶחָד/אַחַת follow the noun rather than lead it, and are read against the noun
    before them. A numeral whose next word is not a bare noun — a time of day, a
    preposition, the end of the line — says nothing here, because nothing tells what
    it counts.
    """
    for at, word in enumerate(words):
        said = numeral(word)
        if said is None:
            continue
        after = _next(words, at)
        if said.value == 1:
            # Only straight after a bare noun: in שְׁנַיִים בַּוַּעֲדָה וְאֶחָד מְדַבֵּר the
            # one is a person, not a committee, and the ו and the ב both say so.
            before = words[at - 1] if at else None
            if (
                before is not None
                and before.pos == "NOUN"
                and not word.lead
                and not (set(before.prefixes) - {"DET"})
            ):
                noun = _noun_gender(before)
                if noun and noun != said.gender:
                    yield Finding(
                        turn,
                        "grammar",
                        f"{before.surface} {word.surface}",
                        f"{bare(before.surface)} is {_said(noun)}, but the numeral after it "
                        f"is {_said(said.gender)}.",
                    )
            continue
        gender = said.gender
        span = word.surface
        if after is not None and (half := teen(after)):
            if half != said.gender:
                yield Finding(
                    turn,
                    "grammar",
                    f"{word.surface} {after.surface}",
                    f"A teen with a {_said(said.gender)} unit and a {_said(half)} ten.",
                )
                continue
            gender, span = half, f"{word.surface} {after.surface}"
            after = _next(words, at + 1)
        if after is None:
            continue
        scale = bare(after.surface)
        if scale == HUNDREDS and gender != "f" and not said.construct:
            yield Finding(
                turn,
                "grammar",
                f"{span} {after.surface}",
                "מאות is feminine, so the numeral before it takes the feminine form.",
            )
        elif scale == THOUSANDS and (gender != "m" or not said.construct):
            yield Finding(
                turn,
                "grammar",
                f"{span} {after.surface}",
                "Before אלפים the numeral takes the masculine construct (שְׁלוֹשֶׁת אֲלָפִים).",
            )
        elif scale not in (HUNDREDS, THOUSANDS) and _counted(after):
            noun = _noun_gender(after)
            if noun and noun != gender:
                yield Finding(
                    turn,
                    "grammar",
                    f"{span} {after.surface}",
                    f"{bare(after.surface)} is {_said(noun)}, but the numeral counting it "
                    f"is {_said(gender)}.",
                )


def _definite(word: Word) -> bool:
    """Whether a word carries the article, in its letters or hidden in its points.

    In the letters, DICTA says so (DET). Hidden, it is a ב, כ or ל prefix pointed with
    patah or qamats where the article's own vowel would be — followed by a dagesh, or by
    a guttural or ר, which refuse one. A prefix before a hataf takes patah without any
    article (לַחֲנוֹת), so that is not counted.
    """
    if "DET" in word.prefixes:
        return True
    if "ADP" not in word.prefixes or word.lead < 1:
        return False
    seen = units(word.surface)
    if len(seen) <= word.lead:
        return False
    prefix, marks = seen[word.lead - 1]
    if prefix not in "בכל" or not (PATAH in marks or QAMATS in marks):
        return False
    letter, following = seen[word.lead]
    if any(h in following for h in HATAFS):
        return False
    return DAGESH in following or letter in GUTTURALS or letter == "ר"


def numeral_state(words: Sequence[Word], turn: int) -> Iterator[Finding]:
    """A numeral in the absolute where the construct belongs, or the reverse.

    - Two before a noun is always the construct, שְׁנֵי / שְׁתֵּי; שְׁנַיִם and שְׁתַּיִם
      stand alone.
    - Three to ten before a definite noun take the construct: בִּשְׁלוֹשֶׁת הַחוֹדָשִׁים,
      not בִּשְׁלוֹשָׁה הַחוֹדָשִׁים. Only the masculine shows it in its letters.
    - A construct numeral with nothing after it counts nothing. `בְּיוֹם שְׁנֵי.` is the
      shape: the day is שֵׁנִי, and שְׁנֵי is 'two of'.
    """
    for at, word in enumerate(words):
        said = numeral(word)
        if said is None or said.value == 1:
            continue
        after = _next(words, at)
        if said.construct:
            if after is None or after.pos == "PUNCT":
                yield Finding(
                    turn,
                    "grammar",
                    word.surface,
                    "A construct numeral ('two of', 'three of') with nothing after it.",
                )
            continue
        if after is None or not _counted(after) or teen(after):
            continue
        if said.value == 2:
            yield Finding(
                turn,
                "grammar",
                f"{word.surface} {after.surface}",
                "Two before a noun is the construct, שְׁנֵי or שְׁתֵּי.",
            )
        elif said.gender == "m" and _definite(after):
            yield Finding(
                turn,
                "grammar",
                f"{word.surface} {after.surface}",
                "Before a definite noun the numeral takes its construct form (שְׁלוֹשֶׁת הַ…).",
            )


# ------------------------------------------------------------------------ smichut


def _letters(word: Word) -> int:
    return len(bare(word.surface))


def article_on_construct(words: Sequence[Word], turn: int) -> Iterator[Finding]:
    """The article on the first word of a construct chain.

    In a chain the article goes on the last noun only: בֵּית הַסֵּפֶר, never הַבֵּית סֵפֶר,
    and בְּיוֹם הַבִּיטּוּל, never בַּיּוֹם הַבִּיטּוּל. Which word heads a chain is DICTA's
    syntax (`compound:smixut`); whether it carries the article is its letters or its
    points (`_definite`). A quantifier is the head of its noun the same way — לְרוֹב
    הַדִּירוֹת, never לָרוֹב — and DICTA files that as `det` rather than as a chain.

    Not a chain here, though DICTA calls it one: a number after a noun (בָּעַמּוּד
    מָאתַיִים is page two hundred, a label), and a word split at a geresh (הַגּ׳יפּ).
    A numeral heading a chain is `numeral_state`'s.
    """
    seen: set[int] = set()
    for at, word in enumerate(words):
        if not 0 <= word.head < len(words) or _letters(word) < 2:
            continue
        if word.relation == "compound:smixut":
            first, last = word.head, at
            if words[first].pos not in ("NOUN", "DET") or word.pos == "NUM":
                continue
        elif word.relation == "det" and word.pos == "DET" and word.head == at + 1:
            # The quantifier is this word, and its noun is the one after it.
            first, last = at, at + 1
            if words[last].pos != "NOUN":
                continue
        else:
            continue
        head, tail = words[first], words[last]
        if first in seen or numeral(head) is not None or _letters(head) < 2:
            continue
        if _letters(tail) >= 2 and _definite(head):
            seen.add(first)
            yield Finding(
                turn,
                "grammar",
                f"{head.surface} {tail.surface}",
                "The article is on the head of a construct chain; it belongs on the last noun.",
            )


#: What a construct form can govern: the next word must be one of these.
GOVERNED = frozenset({"NOUN", "PROPN", "PRON", "NUM", "DET", "ADJ"})


def construct_ending(word: Word) -> str:
    """'f' for a -ָXַת ending, 'pl' for a -ֵי ending, else ''.

    These are the construct's own endings: הַפְרָעָה → הַפְרָעַת, חוּקִּים → חוּקֵּי. The
    feminine is read as qamats then patah before a final ת, which no absolute noun has
    (the absolutes in -ַחַת, -ַעַת are patah then patah: צַלַּחַת, דַּעַת).
    """
    body = word.body()
    if len(body) < 3:
        return ""
    (_, a_marks), (_, b_marks), (c, c_marks) = body[-3], body[-2], body[-1]
    if c == "ת" and PATAH in b_marks and QAMATS in a_marks and SHVA not in c_marks:
        return "f"
    if c == "י" and TSERE in b_marks and not _vowel(c_marks):
        return "pl"
    return ""


def construct_governs_nothing(words: Sequence[Word], turn: int) -> Iterator[Finding]:
    """A word pointed as a construct form where the line has no construct.

    `לֹא הַפְרָעַת.` is 'not the disturbance of —': the construct noun, and then a full
    stop. What was meant is the verb, הִפְרַעְתְּ. `הַמִּבְנֶה חוּקֵּי.` is 'the building
    laws of —' where the adjective חוּקִּי was meant. DICTA cannot see the ending, because
    it reads the letters and the letters of הִפְרַעְתְּ and הַפְרָעַת are the same; what it
    can say is that the letters are a verb, or that nothing after them is governed.

    Only on what DICTA calls a noun, an adjective or a verb. The prepositions that were
    once construct nouns — לִפְנֵי, אַחֲרֵי, כְּדֵי, לְגַמְרֵי — stand alone as a matter of
    course, and were thirty-one false positives before this line. A numeral is
    `numeral_state`'s.
    """
    for at, word in enumerate(words):
        if word.pos not in ("NOUN", "ADJ", "VERB") or not construct_ending(word):
            continue
        after = _next(words, at)
        if word.pos == "VERB":
            what = "Pointed with a construct noun's ending, but the letters read as a verb."
        elif after is None or after.pos not in GOVERNED:
            what = "Pointed as a construct form ('the … of'), with nothing after it to govern."
        else:
            continue
        yield Finding(turn, "grammar", word.surface, what)


# ----------------------------------------------------------------------------- all

Check = Callable[[Sequence[Word], int], Iterator[Finding]]

#: Every check here, by the name the scorer reports it under.
CHECKS: dict[str, Check] = {
    "numeral_agreement": numeral_agreement,
    "numeral_state": numeral_state,
    "article_on_construct": article_on_construct,
    "construct_governs_nothing": construct_governs_nothing,
}

#: The checks that run in the gate, and why each earned it. Scored on 2026-09-28 against
#: the 384 settled corrections, over the hundred scenes as they stood before the audit:
#:
#: - `numeral_agreement`: 6 findings, 4 of them settled corrections. The other two are
#:   real: שְׁמוֹנָה מֵאוֹת again in scene 69, the error settled twice in scene 38, and
#:   שְׁתֵּים עֶשְׂרֵה שֶׁקֶל in scene 5, which both of the audit's readings found.
#: - `numeral_state`: 3 findings, all 3 settled corrections.
#: - `article_on_construct`: 2 findings. One settled (לָרוֹב); the other, בַּיּוֹם
#:   הַבִּיטּוּל in scene 54, is wrong and nobody marked it.
#: - `construct_governs_nothing`: 14 findings, all 14 settled corrections. It raised 31
#:   more before it read DICTA's part of speech, every one a preposition (לִפְנֵי, כְּדֵי),
#:   and was not gated until it did.
#:
#: A check that floods is left out of this tuple and stays in `CHECKS`, so the scorer
#: keeps saying what it would find.
GATED: tuple[str, ...] = (
    "numeral_agreement",
    "numeral_state",
    "article_on_construct",
    "construct_governs_nothing",
)


def check_words(words: Sequence[Word], turn: int) -> list[Finding]:
    """Everything the gated checks find in one turn."""
    found: list[Finding] = []
    for name in GATED:
        found += CHECKS[name](words, turn)
    return found
