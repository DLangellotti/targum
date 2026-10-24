"""Where a pointed modern word is stressed when a suffix holds the stress back.

phonikud stresses the last syllable of a word no mark places, and the past tense's first
and second person, -nu and -cha all take it one syllable back: כָּתַבְתִּי came out
`katavtˈi` for katˈavti, שֶׁלָּנוּ `ʃelanˈu`, אֵלֶיךָ `ʔeleχˈa`. About 2.7% of the tokens in
the laptop's modern texts, among them the commonest words there are (לנו, אנחנו, הייתי,
אמרתי, אליך). This reads it off the pointing and the word's grammar, beside the segolate
rule (`segolate`), and leaves every other word to the default (targum-internal#500;
ling-he's rule and 83-word set, 2026-10-21; David chose to ship it with grammar/7).

Stress the vowel before the suffix when:

1. **A past, first person or second masculine singular** (VERB or AUX, `Tense=Past`):
   ending תִּי with `Person=1`, נוּ with `Person=1|Number=Plur`, or תָּ / תָּה with
   `Person=2|Number=Sing`. Every binyan and weak root: נָתַתִּי, רָאִיתִי, קַמְתִּי, בָּאנוּ.
   Never the second plural (כְּתַבְתֶּם), the third person (כָּתְבוּ, בָּנוּ "they built"),
   the second feminine (כָּתַבְתְּ). The features keep אִשְׁתִּי and בִּתִּי (noun + "my") out.
2. **-nu on anything that is not a verb**, after a full vowel (qamats, tsere, segol,
   hiriq, holam, a vowel letter allowed): לָנוּ, שֶׁלָּנוּ, עָלֵינוּ, מִמֶּנּוּ. Listed:
   אֲנַחְנוּ and אָנוּ.
3. **-cha after a full vowel** (segol, hiriq, holam): אֵלֶיךָ, אָבִיךָ, כָּמוֹךָ. After a
   shva it is final, and the default is already right (לְךָ, סִפְרְךָ). And **-ájich**:
   עֵינַיִךְ.

The grammar is the reason the annotator asks for a reading per form *and* class
(`gate`): בָּנוּ "in us" and בָּנוּ "they built" are spelled and pointed the same.

**Never in a text that carries its accents**: the sequential perfect (וְאָמַרְתָּ) is a
plain past in the tagging and stressed at the end by the Masoretes, and the rule would be
wrong on most of them. `pronounce` asks this only of a word with no accent at all.
"""

from __future__ import annotations

import unicodedata

QAMATS, TSERE, SEGOL, PATAH, HIRIQ = "ָ", "ֵ", "ֶ", "ַ", "ִ"
SHVA, DAGESH, HOLAM, HOLAM_VAV = "ְ", "ּ", "ֹ", "ֺ"

#: The words no pattern states, by their letters: the penult.
LISTED = frozenset({"אנחנו", "אנו"})

#: What separates a word from its class in the key the annotator hands `pronounce`.
GATE = "\x1f"


def gate(pos: str | None, feats: str | None) -> str:
    """The part of a token's grammar the rule reads, as one string: its part of speech
    and, for a verb, its tense, person and number. Two tokens with the same pointing and
    the same gate get the same reading."""
    part = pos or ""
    if part not in ("VERB", "AUX"):
        return "word"
    kept = [
        f"{key}={value}"
        for key, value in (_feat(feats, "Tense"), _feat(feats, "Person"), _feat(feats, "Number"))
        if value
    ]
    return "|".join([part, *kept])


def _feat(feats: str | None, key: str) -> tuple[str, str]:
    for piece in (feats or "").split("|"):
        name, _, value = piece.partition("=")
        if name == key:
            return key, value
    return key, ""


def _clusters(word: str) -> list[list[str]]:
    out: list[list[str]] = []
    for char in unicodedata.normalize("NFC", word):
        if "א" <= char <= "ת":
            out.append([char, ""])
        elif out and "֑" <= char <= "ׇ":
            out[-1][1] += char
    return out


def _ends(clusters: list[list[str]], pattern: list[tuple[str, set[str] | None]]) -> bool:
    if len(clusters) < len(pattern):
        return False
    for (letter, marks), (want, need) in zip(clusters[-len(pattern) :], pattern, strict=True):
        if letter != want or (need is not None and not all(mark in marks for mark in need)):
            return False
    return True


SHURUQ = ("ו", {DAGESH})


def stressed_letter(clusters: list[list[str]]) -> int:
    """The letter whose vowel is the second syllable from the end: the nucleus before the
    last. A holam or shuruq vav counts as the vowel of the letter before it."""
    nuclei: list[int] = []
    for at, (letter, marks) in enumerate(clusters):
        before = clusters[at - 1][1] if at else ""
        vav_vowel = (
            letter == "ו"
            and at > 0
            and not any(
                v in before
                for v in (QAMATS, TSERE, SEGOL, PATAH, HIRIQ, HOLAM, SHVA, "ֻ", "ֱ", "ֲ", "ֳ")
            )
        )
        if vav_vowel and (HOLAM in marks or HOLAM_VAV in marks or marks == DAGESH):
            nuclei.append(at)
            continue
        if any(
            v in marks
            for v in (QAMATS, TSERE, SEGOL, PATAH, HIRIQ, HOLAM, HOLAM_VAV, "ֻ", "ֱ", "ֲ", "ֳ")
        ):
            nuclei.append(at)
    return nuclei[-2] if len(nuclei) >= 2 else -1


def _first_singular(clusters: list[list[str]]) -> bool:
    """A past's -ְתִּי, -ִיתִי or -אתִי, by the pointing alone."""
    if len(clusters) < 3 or not _ends(clusters, [("ת", {HIRIQ}), ("י", None)]):
        return False
    letter, marks = clusters[-3]
    if SHVA in marks or letter == "א":
        return True
    return letter == "י" and len(clusters) > 3 and HIRIQ in clusters[-4][1]


def fires(word: str, key: str) -> bool:
    """Whether the rule stresses `word`, of the class `key` (`gate`), on the penult."""
    clusters = _clusters(word)
    if len(clusters) < 3:
        return False
    letters = "".join(letter for letter, _ in clusters)
    if letters in LISTED:
        return True
    pos, _, rest = key.partition("|")
    feats = dict(piece.partition("=")[::2] for piece in rest.split("|") if piece)
    verb = pos in ("VERB", "AUX")
    if verb and feats.get("Tense") == "Past":
        person, number = feats.get("Person", ""), feats.get("Number", "")
        if _first_singular(clusters):
            # -ְתִּי, -ִיתִי or -אתִי on a past is the first person whatever the tag says: no
            # third person ends that way, and שָׁתַלְתִּי came back Person=3 (grammar/8).
            return True
        if (
            person == "1"
            and _ends(clusters, [("ת", None), ("י", None)])
            and HIRIQ in clusters[-2][1]
        ):
            return True
        if person == "1" and number == "Plur" and _ends(clusters, [("נ", None), SHURUQ]):
            return True
        if person == "2" and number == "Sing":
            if clusters[-1][0] == "ת" and QAMATS in clusters[-1][1]:
                return True
            if _ends(clusters, [("ת", {QAMATS}), ("ה", None)]):
                return True
        return False
    # -nu on a verb is the verb's own (נָתְנוּ, בָּנוּ "they built"): only on anything else.
    if not verb and _ends(clusters, [("נ", None), SHURUQ]):
        before = clusters[-3]
        if before[0] in "יו" and len(clusters) > 3 and not before[1].strip(DAGESH):
            before = clusters[-4]
        if any(v in before[1] for v in (QAMATS, TSERE, SEGOL, HIRIQ, HOLAM, HOLAM_VAV)):
            return SHVA not in before[1]
    if clusters[-1][0] == "ך" and QAMATS in clusters[-1][1]:
        before = clusters[-2]
        if before[0] in "יו" and len(clusters) > 2 and not before[1].strip(DAGESH):
            before = clusters[-3]
        if any(v in before[1] for v in (SEGOL, HIRIQ, HOLAM, HOLAM_VAV)):
            return SHVA not in before[1]
    return _ends(clusters, [("י", {HIRIQ}), ("ך", None)]) and PATAH in clusters[-3][1]


def place(word: str, key: str) -> str | None:
    """The word with phonikud's stress mark (U+05AB) after the stressed vowel, or None."""
    if not fires(word, key):
        return None
    at = stressed_letter(_clusters(word))
    if at < 0:
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
        if not done and letter == at and not ("֑" <= following <= "ׇ"):
            out.append("֫")
            done = True
    return "".join(out)
