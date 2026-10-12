"""What a card says "inferred" about: the stress we guessed and the vowels we supplied.

design.md §12, "What we inferred says so" (2026-09-27). The rule is guessed
against read: a stress read off a mark and vowels the source carried are never
qualified, and everything phonikud or the menaked had to supply is. None of this needs
phonikud installed — it reads the word as written and the reading already stored.
"""

from __future__ import annotations

from targum.annotate.pronounce import (
    CONFIDENCE_BAR,
    HATAMA,
    STRESS_GUESSED,
    VOWELS_GUESSED,
    guessed,
    syllables,
)

# הַשָּׁמַיִם with tipcha (U+0596) on the stressed syllable, where the Masoretes placed it;
# and the same letters with pashta (U+0599) instead, which is postpositive — it sits on
# the last letter wherever the stress is, so it places nothing.
ACCENTED = "הַשָּׁמַ\u0596יִם"
UNPLACED_ONLY = "הַשָּׁמַיִ\u0599ם"
POINTED = "בָּצָל"
BARE = "בצל"


def test_a_pointed_word_with_no_stress_mark_says_its_stress_was_guessed() -> None:
    assert guessed(POINTED, "batsˈal") == STRESS_GUESSED


def test_a_word_the_source_left_bare_says_both() -> None:
    """The menaked supplied the vowels, and phonikud then guessed the stress on them."""
    assert guessed(BARE, "batsˈal") == STRESS_GUESSED | VOWELS_GUESSED


def test_a_placed_accent_is_read_not_guessed() -> None:
    assert guessed(ACCENTED, "haʃamˈajim") == 0


def test_phonikuds_own_mark_is_read_not_guessed() -> None:
    assert guessed("מֶ" + HATAMA + "לֶךְ", "mˈeleχ") == 0


def test_an_unplaced_accent_places_nothing() -> None:
    """A postpositive accent sits on the last letter wherever the stress is."""
    assert guessed(UNPLACED_ONLY, "haʃamajˈim") == STRESS_GUESSED


def test_a_word_of_one_syllable_has_nowhere_else_to_put_it() -> None:
    assert guessed("כָּל", "kˈol") == 0
    assert guessed("כל", "kˈol") == VOWELS_GUESSED


def test_no_reading_says_nothing() -> None:
    assert guessed(BARE, "") == 0


def test_a_calibrated_answer_over_the_bar_is_shown_plainly() -> None:
    """The hook for a calibrated stress source. None is wired in today."""
    assert guessed(POINTED, "batsˈal", stress_confidence=0.99, stress_threshold=0.9) == 0
    assert (
        guessed(POINTED, "batsˈal", stress_confidence=0.8, stress_threshold=0.9) == STRESS_GUESSED
    )
    assert CONFIDENCE_BAR == 0.95


def test_syllables_are_runs_of_vowels() -> None:
    assert syllables("batsˈal") == 2
    assert syllables("vajhˈi") == 2
    assert syllables("kˈol") == 1
    assert syllables("") == 0


# -- the qamats qatan ---------------------------------------------------------------
#
# design.md §12, "The card says a Hebrew word in letters you read" (2026-10-12): a closed
# list of words whose qamats is qatan, said "o", because phonikud says every plain
# qamats "a" and כָּל came out "kal".


def test_kol_is_said_kol_with_its_prefixes_and_its_accent() -> None:
    from targum.annotate.pronounce import qatan

    assert qatan("כָּל", "kˈal") == "kˈol"
    assert qatan("כָּ֥ל", "kˈal") == "kˈol", "a chanting mark changes nothing"
    assert qatan("כָּל־", "kˈal") == "kˈol"
    assert qatan("וְכָל", "veχˈal") == "veχˈol"
    assert qatan("מִכָּל", "mikˈal") == "mikˈol"
    assert qatan("כל", "kˈal") == "kˈol", "bare כל is never anything else"
    assert qatan("כָּֽל", "kˈal") == "kˈol", "nor is it with a gaya before its maqaf"


def test_the_list_reaches_past_kol() -> None:
    from targum.annotate.pronounce import qatan

    assert qatan("הַחָכְמָה", "haχaχmˈa") == "haχoχmˈa"
    assert qatan("קָרְבָּן", "kaʁbˈan") == "koʁbˈan"
    assert qatan("אָמְנָם", "ʔamnˈam") == "ʔomnˈam"
    assert qatan("תָּכְנִית", "taχnˈit") == "toχnˈit"


def test_what_is_not_on_the_list_is_left_alone() -> None:
    from targum.annotate.pronounce import qatan

    assert qatan("חָֽכְמָה", "χaχmˈa") == "χaχmˈa", "a meteg says the qamats is gadol"
    assert qatan("כָּלָה", "kalˈa") == "kalˈa", "kala, a bride"
    assert qatan("שכל", "ʃekˈal") == "ʃekˈal", "bare, it could be sechel"
    assert qatan("קָרְבוּ", "kaʁvˈu") == "kaʁvˈu"
    assert qatan(POINTED, "batsˈal") == "batsˈal"
    assert qatan("כָּל", "") == ""
    assert qatan("ו", "vu") == "vu", "a word shorter than its prefixes"
    assert qatan("", "a") == "a"
