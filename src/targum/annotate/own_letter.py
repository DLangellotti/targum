"""A letter DICTA cut off as a prefix that is the word's own: a participle's מ and an
infinitive's ל, at page-build and count time (targum-internal#689).

Read off the Shoelace Seller, which Ben-Yehuda prints pointed and in ktiv haser, so
DICTA is handed the letters the points leave: ועיניו משפלות, אותי למכר.

- מֻשְׁפָּלוֹת, "lowered", is the huf'al participle of ש־פ־ל. Spelled משפלות it came back
  as מ "from" and שפלות, lemma שפל, pa'al, and the card had no meaning to give.
- לִמְכֹּר, "to sell", is the infinitive. Spelled למכר it came back as ל "to" and the
  noun מכר, so the card read "ל to + מכר" over the meaning "to sell": to + to sell.

**The tell is what DICTA itself said of the letter.** Where a ל or מ is the preposition
DICTA tags it one: `ADP` among the word's prefixes (למלך, מבית, משדה all carry it). In
both of these it cut the letter and tagged nothing. That alone is not enough, since
DICTA leaves some real prepositions untagged too, so the letter goes back only where
something else says it is the word's:

- a מ, on a word DICTA read as a verb, where the word with it is a present of exactly
  one verb in the CC0 paradigm table, asked in ktiv male as the table is written (a
  pointed word's qubuts and holam written with a vav first, `_male`). Pointed, the vowel
  under the מ must be that verb's binyan's: a shva for a pi'el or pu'al, a patach or
  tsere for a hif'il, a qubuts or qamats for a huf'al, a hiriq only for a hitpa'el
  (מִתְלַבֵּשׁ), so מִן's hiriq stays "from". A noun or adjective DICTA cut after מ keeps
  its cut: across the laptop's shelf those were the preposition on a noun (מבינות,
  משמן, מקצות) far more often than a participle;
- a ל, where DICTA read the word as an infinitive (a verb with no person, gender or
  tense, and a lemma of its own rather than the word itself), or where the word is
  pointed as one: ל in place of the he-future's prefix letter, or לה in place of it for
  a hif'il, nif'al or hitpa'el, with the future's own vowels after it (לִמְכֹּר beside
  יִמְכֹּר, לְהַשְׁפִּיל beside יַשְׁפִּיל). The CC0 table holds almost no infinitives, so it is
  asked for the future instead. Unpointed, a word DICTA did not call a verb keeps its
  ל: only the marks tell לִמְכֹּר "to sell" from לְמֶכֶר "to a sale", and לְדַבֵּר from
  לְדָבָר. Pointed, the article inside the ל (לַמֶּלֶךְ) and a noun's final qamats-he
  (לְבַטָּלָה) keep it too.

An infinitive's ל is the infinitive's own; Hebrew grammars write לִכְתֹּב, not ל + כתב.

The annotation on disk keeps what DICTA said; nothing here renames an annotator, moves
`SCHEMA_VERSION` or runs a model. It runs inside `lemma_check.mend_token` and
`mend_row`, so the page and the counts read the same word. The annotator's own fix
waits for a rename that is happening anyway.
"""

from __future__ import annotations

import re
import unicodedata
from functools import lru_cache
from typing import NamedTuple

from .hebrew import CLITIC_GLOSSES

#: The participle's מ and the infinitive's ל.
MEM, LAMED = "מ", "ל"
#: What DICTA calls a preposition among a word's prefixes.
ADP = "ADP"
#: The hiriq of מִן, the holam ktiv male writes with a vav, and the dagesh.
HIRIQ, HOLAM, DAGESH = "\u05b4", "\u05b9", "\u05bc"
#: The features a present, a past or an imperative carries and an infinitive never does.
_FINITE = ("Person=", "Gender=", "Tense=")
#: Words a ל opens that are no infinitive though DICTA tags them verbs: "after", "quite",
#: "on the contrary", "for nothing". לְאַחַר came through as איחר, "was late", on a
#: children's book (2026-11-13).
NOT_INFINITIVES = frozenset({"לאחר", "למדי", "להפך", "לבטלה"})
#: A future's prefix letters.
_FUTURE = frozenset("אתינ")
#: Marks that say nothing of the reading: cantillation, meteg and rafe.
_SILENT = re.compile("[\u0591-\u05af\u05bd\u05bf]")


class Own(NamedTuple):
    """The token once its letter is given back. `lemma`, `root` and `binyan` are "" where
    they stay what the annotation said."""

    built: str | None
    lead: int
    pos: str
    lemma: str
    root: str
    binyan: str


def _marked(surface: str) -> list[tuple[str, str]]:
    """Each letter of a word with the marks on it, in canonical order."""
    letters: list[tuple[str, str]] = []
    for char in unicodedata.normalize("NFD", surface or ""):
        if "\u0591" <= char <= "\u05c7" and letters:
            letters[-1] = (letters[-1][0], letters[-1][1] + char)
        elif "א" <= char <= "ת":
            letters.append((char, ""))
    return letters


def _holam_male(under: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """`under` with each holam that is not on a vav moved onto one, as ktiv male writes it
    (לִמְכֹּר → לִמְכּוֹר). Not before a vav or an alef, which carry it already (רֹאשׁ)."""
    out: list[tuple[str, str]] = []
    for at, (letter, marks) in enumerate(under):
        after = under[at + 1][0] if at + 1 < len(under) else ""
        if HOLAM in marks and letter != "ו" and after not in ("ו", "א"):
            out += [(letter, marks.replace(HOLAM, "")), ("ו", HOLAM)]
        else:
            out.append((letter, marks))
    return out


def _male(under: list[tuple[str, str]]) -> str:
    """A pointed word as the table writes it: `lemma_check.male`, holam and all
    (מֻשְׁפָּלוֹת → מושפלות)."""
    from .lemma_check import male

    return male("".join(letter + marks for letter, marks in _holam_male(under)))


def _present_of(under: list[tuple[str, str]]) -> tuple[str, str] | None:
    """The one verb of the CC0 table that `under` is a present of, as (lemma in ktiv
    male, binyan); else None."""
    from .paradigms import bare, table

    letters = "".join(letter for letter, _ in under)
    pointed = any(marks for _, marks in under)
    book = table()
    for spelled in dict.fromkeys([_male(under), letters] if pointed else [letters]):
        found = [
            lid
            for lid in book.by_form.get(spelled) or ()
            if lid in book.verbs
            and any(
                bare(form.written) == spelled and "present" in form.features
                for form in book.verbs[lid].forms
            )
        ]
        if found:
            return _named(found)
    return None


def _named(found: list[str]) -> tuple[str, str] | None:
    """`found`'s one verb as (lemma in ktiv male, binyan), or None where they are more."""
    from .lemma_check import _lemma_male
    from .paradigms import table

    book = table()
    verb = _lemma_male(found, book)
    if verb is None:
        return None
    binyans = {book.binyan_of(lid) for lid in found}
    binyan = binyans.pop() if len(binyans) == 1 else None
    return verb, binyan or ""


def _stem(under: list[tuple[str, str]]) -> str:
    """What a future and an infinitive share past their prefix, compared on the vowels:
    holam written male, silent marks dropped, and the first letter's dagesh dropped, since
    whether it takes one depends on the prefix in front of it."""
    units = _holam_male(under)
    if not units:
        return ""
    first, marks = units[0]
    units[0] = (first, marks.replace(DAGESH, ""))
    joined = "".join(letter + _SILENT.sub("", marks) for letter, marks in units)
    return unicodedata.normalize("NFC", joined)


#: What the table calls the future the infinitive is read beside: "he will".
_HE_FUTURE = frozenset({"future", "3rd", "masculine", "singular"})
#: The binyanim whose infinitive is לה in place of the future's prefix.
_WITH_HE = frozenset({"הפעיל", "נפעל", "התפעל"})
#: Which of them the vowel under that ה says: a hif'il's patach or qamats (לְהַשְׁפִּיל,
#: לְהָקִים), a nif'al's or hitpa'el's hiriq or tsere (לְהִכָּנֵס, לְהֵאָמֵר, לְהִתְלַבֵּשׁ).
_HE_VOWELS = {
    "\u05b7": frozenset({"הפעיל"}),
    "\u05b8": frozenset({"הפעיל"}),
    "\u05b4": frozenset({"נפעל", "התפעל"}),
    "\u05b5": frozenset({"נפעל", "התפעל"}),
}


@lru_cache(maxsize=1)
def _futures() -> tuple[dict[str, tuple[str, ...]], dict[str, tuple[str, ...]]]:
    """Every future of the CC0 table past its prefix letter, to the verbs it is a form
    of: the pointed ones by their vowels (`_stem`), and the hif'il, nif'al and hitpa'el
    ones by their letters, since many of the table's forms are written without points."""
    from .paradigms import bare, table

    book = table()
    pointed: dict[str, set[str]] = {}
    spelled: dict[str, set[str]] = {}
    for lid, verb in book.verbs.items():
        with_he = book.binyan_of(lid) in _WITH_HE
        for form in verb.forms:
            # The he-form alone: an infinitive is ל and his future's stem, and the other
            # persons carry endings (תַּכִּי, "you will hit", is not לְכִי, "go").
            if not _HE_FUTURE <= set(form.features) or form.ruled:
                continue
            units = _marked(form.written)
            if len(units) < 3 or units[0][0] not in _FUTURE:
                continue
            if any(marks for _, marks in units):
                # Keyed apart: a hif'il's, nif'al's or hitpa'el's stem follows לה, the
                # rest follow ל.
                pointed.setdefault(("לה" if with_he else "ל") + _stem(units[1:]), set()).add(lid)
            if with_he:
                spelled.setdefault(bare(form.written)[1:], set()).add(lid)
    return (
        {stem: tuple(sorted(lids)) for stem, lids in pointed.items()},
        {stem: tuple(sorted(lids)) for stem, lids in spelled.items()},
    )


def _infinitive_of(under: list[tuple[str, str]]) -> tuple[str, str] | None:
    """The one verb a pointed ל-word is the infinitive of, by its future: ל in place of
    the future's prefix with the future's vowels after it (לִמְכֹּר, יִמְכֹּר), or, for a
    hif'il, nif'al or hitpa'el, לה in place of it (לְהַשְׁפִּיל, יַשְׁפִּיל; לְהִכָּנֵס, יִיכָּנֵס)."""
    by_vowels, by_letters = _futures()
    found = by_vowels.get("ל" + _stem(under[1:]))
    if not found and len(under) > 4 and under[1][0] == "ה":
        found = by_vowels.get("לה" + _stem(under[2:]))
        if not found:
            # Asked in ktiv male, the way the table writes these: לְהִכָּנֵס is להיכנס.
            # Only a verb of the binyan the ה's own vowel says: a hif'il's patach or
            # qamats, a nif'al's or hitpa'el's hiriq or tsere. לְהַצָּלָה, "to the
            # rescue", is spelled like nothing a hif'il future is.
            spelled = _male(under)
            binyanim = _HE_VOWELS.get(next((m for m in under[1][1] if m in _HE_VOWELS), ""))
            if binyanim and spelled.startswith("לה"):
                from .paradigms import table

                book = table()
                found = tuple(
                    lid
                    for lid in by_letters.get(spelled[2:]) or ()
                    if book.binyan_of(lid) in binyanim
                )
    return _named(list(found)) if found else None


def _rebuilt(built: str | None, letter: str) -> str | None:
    """`built` with the clitic `letter` given back to the piece after it, or None where
    the line does not end its prefixes on that letter. "" where the word is left alone,
    which is no line at all, as `dicta._pieces_of` writes none for an unsplit word."""
    if not built:
        return None
    pieces = built.split(" + ")
    clitic = f"{letter} {CLITIC_GLOSSES[letter]}"
    for at, piece in enumerate(pieces[:-1]):
        after = pieces[at + 1]
        if piece == clitic and after.split(" ", 1)[0] not in CLITIC_GLOSSES:
            joined = [*pieces[:at], letter + after, *pieces[at + 2 :]]
            return " + ".join(joined) if len(joined) > 1 else ""
    return None


#: The binyan a participle's מ says by its vowel, where the word is pointed: a pi'el's or
#: pu'al's shva (מְדַבֵּר, מְזֻעְזָע), a hif'il's patach or tsere (מַשְׁפִּיל, מֵקִים), a
#: huf'al's qubuts or qamats (מֻשְׁפָּל, מָקָם), a hitpa'el's hiriq (מִתְלַבֵּשׁ).
_MEM_VOWELS = {
    "\u05b0": frozenset({"פיעל", "פועל"}),
    "\u05b2": frozenset({"פיעל", "פועל"}),
    "\u05b7": frozenset({"הפעיל"}),
    "\u05b5": frozenset({"הפעיל"}),
    "\u05bb": frozenset({"הופעל"}),
    "\u05b8": frozenset({"הופעל"}),
    "\u05c7": frozenset({"הופעל"}),
    "\u05b4": frozenset({"התפעל"}),
}
#: A patach and a qamats, which before a doubled letter are the article inside the ל
#: (לַנַּנָּסִין, "to the dwarfs"), and the mappiq, which is the dagesh's mark in a ה.
PATACH, QAMATS = "\u05b7", "\u05b8"
MAPPIQ = DAGESH


def _same_word(said: str, table: str) -> bool:
    """Whether two lemmas are one word with a yod more or less (איחר and the table's
    אחר, חייב and חיב), so DICTA's ktiv male is kept. Not a vav: שטט and שוטט are two
    verbs, a qal and a po'lel."""
    from .paradigms import _orthographies

    return said == table or _orthographies(said)[1] == _orthographies(table)[1]


def own_letter(
    surface: str,
    lemma: str,
    pos: str | None,
    built: str | None,
    lead: int,
    prefixes: tuple[str, ...] | list[str],
    feats: str | None = None,
) -> Own | None:
    """What a token becomes once a participle's מ or an infinitive's ל is given back to
    it, or None where DICTA's cut stands.

    `lead` is how many letters DICTA cut off (`Syntax.lead`), `prefixes` what it tagged
    them (`Syntax.prefixes`), `feats` the features the token carries.
    """
    if lead < 1 or ADP in prefixes or pos not in ("VERB", "NOUN", "ADJ"):
        return None
    marked = _marked(surface)
    if len(marked) - lead < 2:
        return None
    letter, marks = marked[lead - 1]
    if letter not in (MEM, LAMED):
        return None
    rebuilt = _rebuilt(built, letter)
    if rebuilt is None:
        return None
    under = marked[lead - 1 :]
    pointed = any(one for _, one in marked)
    word = "".join(one for one, _ in marked)
    # DICTA gave the word itself, or kept the letter on its lemma: no verb of its own.
    gap = lemma in (word, word[lead - 1 :]) or lemma.startswith(letter)
    if letter == MEM:
        # A participle is a verb DICTA read as one. A noun it cut the same way is far
        # more often the preposition on a noun (מבינות, משמן, מקצות) than a participle.
        if pos != "VERB":
            return None
        verb = _present_of(under)
        if verb is None:
            return None
        if pointed:
            # The vowel under the מ must be the binyan's: מִן's hiriq, or a tsere on a
            # noun (מֵעֶרֶב), is never a pi'el's.
            said = next((mark for mark in marks if mark in _MEM_VOWELS), "")
            if verb[1] not in _MEM_VOWELS.get(said, ()):
                return None
        new_lemma, binyan = verb
    else:
        if word[lead - 1 :] in NOT_INFINITIVES or (pointed and _not_infinitive(under)):
            return None
        infinitive = (
            pos == "VERB" and not gap and not any(part in (feats or "") for part in _FINITE)
        )
        verb = _infinitive_of(under) if pointed else None
        if verb is None and not infinitive:
            return None
        # A verb DICTA read keeps its lemma, unless it kept the ל on it; a word it took
        # for a noun takes the table's verb.
        new_lemma, binyan = verb if verb is not None and (pos != "VERB" or gap) else ("", "")
    if new_lemma and not gap and _same_word(lemma, new_lemma):
        # One word: DICTA's spelling stands, in the ktiv male the shelf files lemmas in.
        new_lemma = lemma
    root = ""
    if new_lemma:
        from .verb_roots import root_for

        root = root_for(new_lemma, None, "VERB")
    return Own(rebuilt or None, lead - 1, "VERB", new_lemma, root, binyan)


def _not_infinitive(under: list[tuple[str, str]]) -> bool:
    """Whether a pointed ל-word's own marks say it is no infinitive: the article inside
    the ל, a patach or qamats before a doubled letter (לַנַּנָּסִין, לַסִּכּוּךְ), or a noun's
    final qamats-he with no mappiq (לְבַטָּלָה), which no infinitive ends on."""
    first, after = under[0][1], under[1][1] if len(under) > 1 else ""
    if (PATACH in first or QAMATS in first) and DAGESH in after:
        return True
    last, before = under[-1], under[-2] if len(under) > 1 else ("", "")
    return last[0] == "ה" and MAPPIQ not in last[1] and QAMATS in before[1]
