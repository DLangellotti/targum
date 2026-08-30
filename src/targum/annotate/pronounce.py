"""How a Hebrew word is said, worked out from the vowels the text already carries.

Hebrew writes the consonants and leaves the vowels to the reader, so nothing can say a
word it has not first been told the vowels of. Fed the bare sentence, phonikud answers
`ˈhj vˈmj ʃˈft`; fed the same sentence pointed, it answers `vajhˈi bimˈej ʃfˈot`. Every
text targum builds is pointed already — from the source where the source has vowels, and
from the diacritizer where it does not — which is what makes this stage possible here and
guesswork anywhere else.

The reading is per occurrence rather than per dictionary form, and that is the whole
point of doing it at all: בצל is `batsˈal` after "I ate" and `btsˈel` under a tree, and
only the vowels above the sentence decide which. A speech engine reading the same page
sees neither.

Nothing is sent anywhere and nothing is spent: this is a rule table over the vowels,
around 12,000 words a second, so a novel is eight seconds.
"""

from __future__ import annotations

import logging

from ..vocalize.base import LETTERS, TAAMIM, has_nikkud, has_taamim, strip_taamim

LOG = logging.getLogger(__name__)

# Modern Israeli Hebrew. Biblical phonology is a different reading of the same marks —
# and a different product — so it is not offered rather than offered wrongly.
LANGUAGES = frozenset({"he"})

# phonikud marks a prefix boundary with an ASCII pipe, which is not a combining mark and
# so survives `strip_nikkud`. Nothing here emits one today — it comes out of phonikud's
# own diacritizer, which targum does not use — but a pipe reaching the phonemizer would
# be read as a word boundary, and a pipe reaching `splice` would change the consonant
# skeleton and lose the sentence. Removed on the way in, where it costs nothing.
PREFIX_MARK = "|"

# phonikud's own mark for the stressed syllable, U+05AB. Fed a word carrying one it says
# where the stress is; fed a word without one it puts the stress on the last syllable and
# is right about two words in three, which is what "mil'el is not audible in the spelling"
# actually costs. מֶלֶךְ and מָלַךְ come back identically stressed without it.
HATAMA = "֫"

# U+05BD, which the vocalizer keeps because it is meteg and silluq at once and deleting it
# would lose the mark that separates a qamats gadol from a qamats qatan. Neither reading of
# it is a sound, and phonikud says otherwise: fed בָּאָֽרֶץ it answers `baʔaeʁˈets`, with an
# `e` that is nobody's vowel. It comes off here, on the way to the phonemizer only, where
# the text the reader sees is not what is being changed. What that costs is the stress on a
# verse-final word — silluq marks it, and no rule can tell silluq from meteg — so those
# words take the default like every unaccented one.
METEG = "ֽ"

# A Masoretic accent sits on the stressed syllable — that is what it is for, before it is
# a tune — so a pointed Tanakh has already answered the question phonikud has to guess at.
# These are the accents that sit somewhere else: prepositive ones on the first letter of
# the word, postpositive ones on the last, wherever the stress actually falls. Reading a
# stress off one of these would be worse than not reading one, so a word carrying only
# these is left to the default.
UNPLACED = frozenset(
    {
        0x0592,  # segolta, postpositive
        0x0599,  # pashta, postpositive
        0x059A,  # yetiv, prepositive
        0x05A0,  # telisha gedola, prepositive
        0x05A9,  # telisha qetana, postpositive
        0x05AD,  # dehi, prepositive
        0x05AE,  # zinor, postpositive
    }
)


def stressed(word: str) -> str | None:
    """The word with its accent rewritten as phonikud's stress mark, or None.

    Canonical ordering puts a vowel before the accent above or below the same letter, so
    the accent's own position is already where the mark belongs and the rewrite is a
    substitution rather than a search.

    `None` where the accents cannot say: a word carrying only an unplaced one, and a word
    carrying several, where picking between them would be a guess dressed as an answer.
    Meteg is not in `TAAMIM` — it shares a codepoint with silluq and the vocalizer keeps
    it on the vowels' side — so it neither counts here nor is stripped.
    """
    marks = [char for char in word if ord(char) in TAAMIM]
    placed = [char for char in marks if ord(char) not in UNPLACED]
    if len(placed) != 1:
        return None
    out: list[str] = []
    for char in word:
        if ord(char) not in TAAMIM:
            out.append(char)
        elif char == placed[0]:
            out.append(HATAMA)
    return "".join(out)


def supports(language: str) -> bool:
    return language in LANGUAGES


def sayable(surface: str) -> bool:
    """Whether this word can be pronounced honestly.

    Two conditions, and the second is the one that matters. It has to be Hebrew, because
    phonikud returns Latin unchanged and would have the card claim `hello` is a
    pronunciation. And it has to carry vowels, because without them phonikud answers
    confidently and wrongly — bare בצל comes back `vˈtsl`, which is not a word. A word
    with no reading is a gap the reader can see past; a wrong one is a lie told with
    confidence, which is the rule the root derivation already follows.
    """
    return has_nikkud(surface) and any(ord(char) in LETTERS for char in surface)


class PhonikudPronouncer:
    """Phonikud, from Interspeech 2026: nikkud and stress to IPA.

    Picked because it is the only Hebrew grapheme-to-phoneme that marks stress, which is
    the feature the field calls underspecified and the one a learner gets wrong for years
    — mil'el against milra is not audible in the spelling and is not in any dictionary
    entry either.

    Underspecified in ordinary pointing, that is. **A Masoretic text has said it all
    along**, in the accents, and until `phonikud/2` this code was throwing them away and
    then guessing at what they had already answered: בָּאָ֑רֶץ came out ba-a-RETS with the
    etnahta sitting on the A. Where the accents can place the stress they are believed,
    because the alternative is preferring a rule table to the Masoretes. Where they
    cannot — an unplaced accent, or more than one — the default stands, which is the same
    guess modern Hebrew gets and no worse than before.
    """

    # The name rides in the annotator's name and so in what a built text records, which
    # is what lets a better reading reach a book already on the shelf: a file made before
    # this names something else, so it is redone. Redoing one is free.
    name = "phonikud/2"

    def available(self) -> tuple[bool, str]:
        try:
            import phonikud  # noqa: F401
        except ImportError:
            return False, "phonikud is not installed"
        return True, ""

    def say(self, surfaces: list[str]) -> dict[str, str]:
        """The reading of each distinct word, keyed by the pointed form given.

        Asked word by word rather than sentence by sentence, which is not an
        approximation: measured against the same words inside their sentence, phonikud
        returns the identical string either way, because the vowels have already settled
        every question the context could answer. So a chapter costs one reading per
        distinct form rather than one per token.
        """
        try:
            import phonikud
        except ImportError:  # pragma: no cover - guarded by available()
            return {}

        out: dict[str, str] = {}
        failed = 0
        for surface in surfaces:
            word = surface.replace(PREFIX_MARK, "")
            if not sayable(word):
                continue
            # The chanting marks have to come off before phonikud sees them: fed
            # שְׁפֹ֣ט whole it answers `ʃˈftˈ`, having read the accents as letters and
            # lost the vowel between them. Taking the stress off them first is what makes
            # removing them a translation rather than a loss.
            if has_taamim(word):
                word = stressed(word) or strip_taamim(word)
            word = word.replace(METEG, "")
            try:
                said = phonikud.phonemize(word)
            except Exception as error:  # noqa: BLE001 - a third-party rule table
                failed += 1
                LOG.debug("no reading for %s: %s", surface, error)
                continue
            said = said.strip()
            # A reading identical to the letters it came from is phonikud handing back
            # what it could not read, which is what it does with Latin and with anything
            # it has no rule for. Nothing is learned from showing it.
            if said and said != word:
                out[surface] = said
        if failed:
            LOG.warning("no reading for %d of %d words", failed, len(surfaces))
        return out


def build() -> PhonikudPronouncer:
    return PhonikudPronouncer()
