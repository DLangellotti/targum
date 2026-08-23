"""Root and binyan for a Hebrew verb, worked out on the machine.

Stanza tags the binyan itself, in the `HebBinyan` feature, so that half is read off
what the lemmatizer already produced and costs nothing. The root is not in there and
is derived here, by undoing the pattern the binyan spells the lemma in.

The derivation is sound for the regular verb and fails on the weak ones, where a
radical is missing from the written form: a hollow root keeps its middle letter
nowhere in קָם, and no rule recovers it. Every rule here therefore ends at the same
guard — a Hebrew root is three letters, and anything that does not come out at three
is dropped rather than shown. A missing root is a gap the Pealim link fills; a wrong
one is a lie told with confidence.
"""

from __future__ import annotations

# Stanza's values, in the order a learner meets them. The name is what the reader sees.
BINYANIM = {
    "PAAL": "פעל",
    "NIFAL": "נפעל",
    "PIEL": "פיעל",
    "PUAL": "פועל",
    "HIFIL": "הפעיל",
    "HUFAL": "הופעל",
    "HITPAEL": "התפעל",
}

# A final letter is folded in while the root is being worked out, so a rule can see
# past it, and folded back at the end: the root of הזדקן is written ז־ק־ן, not ז־ק־נ.
FINALS = str.maketrans("םןץףך", "מנצפכ")
ENDINGS = str.maketrans("מנצפכ", "םןץףך")

# The letter that swaps places with the ת of התפעל, and what it becomes after it.
SIBILANTS = frozenset("סשׂשׁשזצ")
INFIXES = frozenset("תטד")


def binyan_of(feats: str | None) -> str | None:
    """The binyan Stanza tagged, as its Hebrew name. None when it tagged none."""
    if not feats:
        return None
    for part in feats.split("|"):
        key, _, value = part.partition("=")
        if key == "HebBinyan":
            return BINYANIM.get(value.upper())
    return None


def root_of(lemma: str, binyan: str | None) -> str | None:
    """The three-letter root behind a verb lemma, or None where it cannot be had.

    The lemma is the third-person masculine singular past, which is the form each
    binyan has its own spelling for, so undoing that spelling is the whole method.
    """
    if not binyan or not lemma:
        return None
    letters = [c for c in lemma.translate(FINALS) if "א" <= c <= "ת"]

    if binyan == "פעל":
        pass
    elif binyan == "נפעל":
        letters = _strip(letters, "נ")
    elif binyan == "פיעל":
        letters = _drop_mater(letters, 1, "י")
    elif binyan == "פועל":
        letters = _drop_mater(letters, 1, "ו")
    elif binyan == "הפעיל":
        letters = _hifil(_strip(letters, "ה"))
    elif binyan == "הופעל":
        letters = _strip(_strip(letters, "ה"), "ו")
    elif binyan == "התפעל":
        letters = _untangle(_strip(letters, "ה"))
    else:
        return None

    if len(letters) != 3:
        return None
    return "".join(letters[:2]) + letters[2].translate(ENDINGS)


def _strip(letters: list[str], first: str) -> list[str]:
    return letters[1:] if letters[:1] == [first] else letters


def _drop_mater(letters: list[str], at: int, mater: str) -> list[str]:
    """Remove a vowel letter the pattern writes but the root does not have.

    Only when taking it out leaves three letters. פיעל writes דיבר for ד־ב־ר, but the
    י of הביא is a radical, and dropping it there would invent a two-letter root.
    """
    if len(letters) == 4 and letters[at : at + 1] == [mater]:
        return letters[:at] + letters[at + 1 :]
    return letters


def _hifil(letters: list[str]) -> list[str]:
    """הפעיל, once its ה is off.

    A strong root spells four letters with a י before the last, and taking it out
    leaves the root. Three letters with a י in the middle is a different word
    entirely: הקים is ק־ו־ם and הגיש is נ־ג־ש, the י standing in for a radical that
    is not written, and nothing in the spelling says which. Those are dropped.
    """
    if len(letters) == 4 and letters[2] == "י":
        letters = letters[:2] + letters[3:]
    elif len(letters) == 3 and letters[1] == "י":
        return []
    # A root that begins with י writes it as a ו here: הוריש is י־ר־ש, הודיע is י־ד־ע.
    # Hebrew roots essentially never begin with a ו of their own, so this is safe.
    if letters[:1] == ["ו"]:
        return ["י"] + letters[1:]
    return letters


def _untangle(letters: list[str]) -> list[str]:
    """Take the ת of התפעל back out, from wherever the word put it.

    It sits after the prefix, except against a sibilant, which makes it swap places
    (השתמש for ש־מ־ש) and, after ז, become a ד (הזדקן for ז־ק־ן).
    """
    if letters[:1] == ["ת"]:
        return letters[1:]
    if len(letters) > 1 and letters[0] in SIBILANTS and letters[1] in INFIXES:
        return [letters[0]] + letters[2:]
    return letters
