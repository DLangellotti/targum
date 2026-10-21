"""Where a pointed modern word is stressed when no accent says: the segolate rule.

phonikud puts the stress on the last syllable of any word that carries no stress mark,
which is right about two words in three and wrong on the commonest nouns in the language:
כֶּסֶף came out `kesˈef`, סֵפֶר `sefˈeʁ`, בַּיִת `bajˈit`, רַכֶּבֶת `ʁakevˈet`. The Tanakh says
the stress in its accents (`pronounce.stressed`); a modern text never does. This reads it
off the pointing instead, for the families whose stress the vowels settle, and leaves
every other word to phonikud's default (targum-internal#454; ling-he's rule and test set,
2026-10-21; David chose to ship it with the grammar/7 re-read).

Stress the vowel before the last one when:

1. **-ayim / bayit**: patah (or qamats) + י with hiriq + a bare final letter: בַּיִת, מַיִם.
2. **-éha**: segol + י + ה with qamats: עֵינֶיהָ.
3. **CéCeC**: the last vowel a segol on the second-to-last letter, with no dagesh; the last
   letter bare and not י, ו or ה (a quiescent א is fine); the vowel before a segol, tsere,
   holam or patah on the adjacent letter, or a qamats before a ו or on a guttural:
   מֶלֶךְ, סֵפֶר, בֹּקֶר, רַכֶּבֶת, מָוֶת, הָאָרֶץ.
4. **CáCaC with a guttural**: the last vowel a patah on the second-to-last letter, with no
   dagesh; the last letter bare and not י, ו or ה; the vowel before a segol, patah or
   holam on the adjacent letter; a guttural carrying that patah, or ending the word where
   the vowel before is not a holam: נַעַר, רֶגַע, רֹחַב, שׁוֹמַעַת. A furtive patah sits on
   the last letter and never fires it (יוֹדֵעַ).

Never the pronoun endings and the past's -tem/-ten (ֶם, ֶן after ה, כ, ת), a qamats then a
patah (the verbs מָלַךְ, פָּתַח), a hataf or shva before (אֱמֶת), or a word ending in ה
(שָׂדֶה). Listed, because no pattern states them: אֵלֶּה, הֵמָּה, לַיְלָה and תֵּשַׁע on the
penult; אַחַת, אַחַר, אַחַד, מֵעַל, שֶׁעַל on the last.

Measured on the Tanakh with its accents taken off (`scripts/eval_segolate.py`): where it
fires it agrees with the accents at the floor in `evals/floors.json`, `stress-rule/2`.
"""

from __future__ import annotations

import unicodedata

SEGOL, TSERE, HOLAM, HOLAM_VAV, PATAH, QAMATS = "ֶ", "ֵ", "ֹ", "ֺ", "ַ", "ָ"
HIRIQ, QUBUTS, SHVA, DAGESH = "ִ", "ֻ", "ְ", "ּ"
HATAFS = frozenset("ֱֲֳ")
GUTTURALS = frozenset("אהחע")
#: Vowels that make a full syllable before a segol, and before a patah.
BEFORE_SEGOL = frozenset({SEGOL, TSERE, HOLAM, PATAH, QAMATS})
BEFORE_PATAH = frozenset({SEGOL, HOLAM, PATAH})
_ANY_VOWEL = BEFORE_SEGOL | {HIRIQ, QUBUTS} | HATAFS
_FINALS = str.maketrans("ךםןףץ", "כמנפצ")

#: phonikud's own stress mark (`pronounce.HATAMA`).
HATAMA = "֫"

#: Words no pattern states, by their letters after the prefixes: always the last syllable.
FINAL_ENDINGS = ("אחת", "אחר", "אחד", "מעל", "שעל")
#: One-syllable words behind a prefix, which a CéCeC or CáCaC reading would take for a
#: segolate: הַחַג is the article and חַג, שֶׁאֶת is ש and אֶת (ling-he's modern hand-read,
#: 2026-10-21). Always the last syllable.
FINAL_STEMS = {"חג": PATAH, "חד": PATAH, "חמ": PATAH, "את": SEGOL}
FINAL_PREFIXES = frozenset("ובכלמשה")
#: And on the penult, by their letters, where the pointing is the listed one.
PENULT_LETTERS = frozenset({"תשע"})
PENULT_POINTED = frozenset(
    unicodedata.normalize("NFC", word) for word in ("אֵלֶּה", "הֵמָּה", "לַיְלָה", "הַלַּיְלָה")
)


def _clusters(word: str) -> list[list[str]]:
    out: list[list[str]] = []
    for char in unicodedata.normalize("NFC", word):
        if "א" <= char <= "ת":
            out.append([char, ""])
        elif out and "֑" <= char <= "ׇ":
            out[-1][1] += char
    return out


def _nuclei(clusters: list[list[str]]) -> list[tuple[int, str, int]]:
    """Each syllable's nucleus as (letter, vowel, where its mark is): a holam or shuruq vav
    counts as the vowel of the letter before it, and its mark is on the vav."""
    found: list[tuple[int, str, int]] = []
    for at, (letter, marks) in enumerate(clusters):
        before = clusters[at - 1][1] if at else ""
        if (
            letter == "ו"
            and (HOLAM in marks or HOLAM_VAV in marks)
            and at > 0
            and not any(v in before for v in _ANY_VOWEL | {SHVA})
        ):
            found.append((at - 1, HOLAM, at))
            continue
        if (
            letter == "ו"
            and DAGESH in marks
            and not any(v in marks for v in _ANY_VOWEL | {SHVA})
            and at > 0
            and not any(v in before for v in _ANY_VOWEL)
        ):
            found.append((at - 1, "u", at))
            continue
        for vowel in (SEGOL, TSERE, HOLAM, HOLAM_VAV, PATAH, QAMATS, HIRIQ, QUBUTS):
            if vowel in marks:
                found.append((at, HOLAM if vowel == HOLAM_VAV else vowel, at))
                break
        else:
            for vowel in HATAFS:
                if vowel in marks:
                    found.append((at, vowel, at))
                    break
    return found


def penult(word: str) -> int | None:
    """The cluster whose vowel carries the stress, where the rule places it on the
    syllable before the last; None to leave phonikud's default."""
    clusters = _clusters(word)
    if len(clusters) < 2:
        return None
    nuclei = _nuclei(clusters)
    if len(nuclei) < 2:
        return None
    letters = "".join(letter for letter, _ in clusters).translate(_FINALS)
    stressed = nuclei[-2][2]
    if unicodedata.normalize("NFC", word) in PENULT_POINTED or letters in PENULT_LETTERS:
        return stressed
    last = len(clusters) - 1
    last_at, last_vowel, _ = nuclei[-1]
    before_vowel = nuclei[-2][1]
    # 1. -ayim, bayit.
    if (
        last >= 2
        and clusters[last - 1][0] == "י"
        and HIRIQ in clusters[last - 1][1]
        and (PATAH in clusters[last - 2][1] or QAMATS in clusters[last - 2][1])
        and not clusters[last][1].strip(DAGESH)
    ):
        return stressed
    # 2. -éha.
    if (
        last >= 2
        and clusters[last][0] == "ה"
        and QAMATS in clusters[last][1]
        and clusters[last - 1][0] == "י"
        and SEGOL in clusters[last - 2][1]
    ):
        return stressed
    bare_end = (
        not any(v in clusters[last][1] for v in _ANY_VOWEL | {HOLAM_VAV})
        and clusters[last][0] not in "יוה"
    )
    between = [clusters[k] for k in range(nuclei[-2][0] + 1, last_at)]
    adjacent = all(
        letter == "ו" and (HOLAM in marks or HOLAM_VAV in marks or marks == DAGESH)
        for letter, marks in between
    )
    if DAGESH in clusters[last_at][1]:
        return None  # a doubled or hardened letter: not a segolate
    if any(letters.endswith(ending) for ending in FINAL_ENDINGS):
        return None
    for cut in range(1, min(4, len(letters) - 1)):
        stem = letters[cut:]
        # The stem as one closed syllable: חַג with its patah, אֶת with its segol, and
        # nothing on its last letter. לֶחֶם is ל + חֶם only by its letters.
        if (
            set(letters[:cut]) <= FINAL_PREFIXES
            and stem in FINAL_STEMS
            and FINAL_STEMS[stem] in clusters[cut][1]
            and not any(v in clusters[last][1] for v in _ANY_VOWEL)
        ):
            return None
    # The pronoun endings -hem, -hen, -khem, -khen and the past's -tem, -ten are final.
    if (
        clusters[last][0] in "םן"
        and SEGOL in clusters[last - 1][1]
        and clusters[last - 1][0] in "הכת"
    ):
        return None
    first_of_pair = clusters[nuclei[-2][0]][0]
    # 3. CéCeC.
    if (
        last_vowel == SEGOL
        and last_at == last - 1
        and bare_end
        and adjacent
        and (
            before_vowel in BEFORE_SEGOL - {QAMATS}
            or (
                before_vowel == QAMATS
                and (clusters[last - 1][0] == "ו" or first_of_pair in GUTTURALS)
            )
        )
    ):
        return stressed
    # 4. CáCaC with a guttural.
    if (
        last_vowel == PATAH
        and last_at == last - 1
        and bare_end
        and adjacent
        and (
            clusters[last - 1][0] in GUTTURALS
            or (clusters[last][0] in GUTTURALS and before_vowel != HOLAM)
        )
        and before_vowel in BEFORE_PATAH
    ):
        return stressed
    return None


def place(word: str) -> str | None:
    """The word with phonikud's stress mark on the syllable the rule stresses, or None
    where the rule says nothing. The mark goes after the stressed letter's vowel, the way
    `pronounce.stressed` hands an accent to phonikud."""
    at = penult(word)
    if at is None:
        return None
    normal = unicodedata.normalize("NFC", word)
    out: list[str] = []
    letter = -1
    done = False
    for index, char in enumerate(normal):
        out.append(char)
        if "א" <= char <= "ת":
            letter += 1
        following = normal[index + 1] if index + 1 < len(normal) else ""
        if not done and letter == at and not ("\u0591" <= following <= "\u05c7"):
            out.append(HATAMA)
            done = True
    return "".join(out)
