from __future__ import annotations

import pytest

from targum import lexicon


@pytest.mark.parametrize(
    "word",
    [
        # Modern, straight out of wordfreq.
        "ממשלה",
        "הקדמה",
        # Modern, inflected past what a frequency list holds. These are the words the
        # spacing repair used to take apart, one and all.
        "סגולתנו",
        "אחוזתנו",
        "משמרתנו",
        "מהלמות",
        # Every clitic Hebrew stacks on the front, at once.
        "וכשלמלכיהם",
        # Biblical, which modern frequency data has never heard of.
        "חסידיו",
        "ועקש",
    ],
)
def test_knows_a_word_in_either_register(word: str) -> None:
    assert lexicon.known(word)


@pytest.mark.parametrize("word", ["ברקוביץהקדמה", "שלוםעולם", ""])
def test_does_not_know_two_words_run_together(word: str) -> None:
    assert not lexicon.known(word)


def test_strength_reads_both_registers_on_one_scale() -> None:
    # A word a reader of the news meets, and a word a reader of Psalms meets. Both are
    # ordinary; neither corpus knows the other's.
    assert lexicon.strength("ממשלה") >= 4.0
    assert lexicon.strength("חסידיו") >= 4.0
    # A biblical lemma reached through its inflection, which is the whole point of the
    # peeling: the table holds חסיד and the text holds חסידיו.
    assert lexicon.strength("חסיד") >= lexicon.strength("חסידיו")
    assert lexicon.strength("ברקוביץהקדמה") == 0.0


def test_peel_finds_the_word_under_the_morphology() -> None:
    assert "מלך" in lexicon.peel("מלכם")
    assert "מלכיהם" in lexicon.peel("וכשלמלכיהם")
    # Feminine construct: the ת goes back to being a ה.
    assert "סגולה" in lexicon.peel("סגולתנו")
    # Nothing is peeled down to a stem too short to mean anything.
    assert all(len(stem) >= 2 for stem in lexicon.peel("ולה"))
