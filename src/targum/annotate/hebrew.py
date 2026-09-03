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

from typing import Any

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

# The one-letter words Hebrew writes onto the front of the next word, glossed the way
# the card says them. English on purpose: the card's own labels are English whatever
# the reader's target language is, the way `Glossary.parts_of_speech` already is.
CLITIC_GLOSSES = {
    "ו": "and",
    "ה": "the",
    "ל": "to",
    "ב": "in",
    "כ": "as",
    "מ": "from",
    "ש": "that",
}

# The slice of Stanza's morphology the card reads. Everything else it says about a
# word — HebBinyan aside, which has its own field — is thrown away as before.
KEPT_FEATS = ("Person", "Gender", "Number", "Tense", "VerbForm", "Definite")

# A pronominal suffix, said in English. Keyed by (person, gender, number), gender ""
# where it does not matter; two forms because ספרו is "his book" and ממנו is "from him".
_PRONOUNS = {
    ("1", "", "Sing"): ("my", "me"),
    ("1", "", "Plur"): ("our", "us"),
    ("2", "", "Sing"): ("your", "you"),
    ("2", "", "Plur"): ("your", "you"),
    ("3", "Masc", "Sing"): ("his", "him"),
    ("3", "Fem", "Sing"): ("her", "her"),
    ("3", "", "Plur"): ("their", "them"),
}


def _feat(feats: str | None, key: str) -> str:
    for part in (feats or "").split("|"):
        name, _, value = part.partition("=")
        if name == key:
            return value
    return ""


def kept_feats(feats: str | None, pos: str | None = None) -> str | None:
    """The card's slice of the morphology, in Stanza's own pipe format.

    `Definite` is kept only as `Cons` — the construct state is a fact the card names,
    while ordinary definiteness is the ה the pieces line already shows.

    The part of speech leads, as `UPOS=`. The reader has always read it — `useLine`
    branches on it to decide whether to say "past · he" or "noun · f · pl." — and
    nothing had ever written it, so the whole grammar line rendered empty for every word
    of every text while the features behind it shipped in the payload regardless. It
    goes here rather than in the reader off the kind column because that column only
    distinguishes a word from a name from a number, which is not a part of speech.
    """
    kept = [f"UPOS={pos}"] if pos else []
    for key in KEPT_FEATS:
        value = _feat(feats, key)
        if key == "Definite" and value != "Cons":
            continue
        if value:
            kept.append(f"{key}={value}")
    return "|".join(kept) or None


def pieces_of(words: list[Any], content: Any) -> str | None:
    """How a split token is put together, as the card's own line.

    "ו and + ל to + בית" for ולבית; "ל to + בית + his" for לביתו — the clitics carry
    their gloss, the content word stands bare, and a pronominal suffix is said in
    English alone, because the written suffix cannot be recovered from the word
    Stanza reconstructs for it (הוא, not ־וֹ).
    """
    if len(words) < 2:
        return None
    seen_content = False
    chunks: list[str] = []
    for word in words:
        text = (word.text or "").strip()
        if word is content:
            seen_content = True
            chunks.append(text)
        elif seen_content and (word.upos or "") == "PRON":
            possessive = (content.upos or "") == "NOUN"
            gloss = _pronoun(word.feats, possessive)
            chunks.append(gloss or text)
        elif not seen_content and text in CLITIC_GLOSSES:
            chunks.append(f"{text} {CLITIC_GLOSSES[text]}")
        elif text:
            chunks.append(text)
    return " + ".join(chunk for chunk in chunks if chunk) or None


def _pronoun(feats: str | None, possessive: bool) -> str:
    person = _feat(feats, "Person")
    gender = _feat(feats, "Gender")
    number = _feat(feats, "Number")
    for key in ((person, gender, number), (person, "", number)):
        if key in _PRONOUNS:
            mine, me = _PRONOUNS[key]
            return mine if possessive else me
    return ""


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
        letters = _nifal(letters)
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


def _nifal(letters: list[str]) -> list[str]:
    """נפעל, whose prefix is a נ and whose weak roots hide behind a vowel letter.

    A regular verb writes נ plus the three radicals and taking the נ off is the whole
    job: נכתב is כ־ת־ב. Two families do not, and stripping the נ on those invented a
    root that is not one — measured against the IAHLT treebanks, all eleven of the
    irregular nifal lemmas in them came out wrong, and ניתן was shown to readers as
    י־ת־ן.

    The vowel letter in second place says which family it is, and says it unambiguously:

    - a ו stands where a root's first radical י has dropped, exactly as it does in
      הפעיל — נודע is י־ד־ע, נולד is י־ל־ד, נוסף is י־ס־ף;
    - a י stands where the root's own first radical נ has assimilated into the pattern's
      נ, so the two are written once — ניתן is נ־ת־ן, נישא is נ־שׂ־א, ניצב is נ־צ־ב.

    Hebrew roots essentially never begin with ו, which is what makes the first safe; and
    a נ that is not doubled in writing is the ordinary fate of a root-initial נ, which is
    what makes the second.
    """
    if len(letters) == 4 and letters[:1] == ["נ"]:
        if letters[1] == "ו":
            return ["י"] + letters[2:]
        if letters[1] == "י":
            return ["נ"] + letters[2:]
    return _strip(letters, "נ")


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
