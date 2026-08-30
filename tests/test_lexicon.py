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


def test_strengths_keeps_the_two_registers_apart() -> None:
    """What `strength` collapses, said separately — which is the word card's question.

    A modern word the Tanakh never had, and a biblical word modern Hebrew has let go
    of. `strength` calls both of them ordinary and cannot say why.
    """
    modern, biblical = lexicon.strengths("אוטובוס")
    assert modern >= 4.0 and biblical == 0.0
    modern, biblical = lexicon.strengths("חסידיו")
    assert biblical >= 4.0 and modern < 4.0
    assert lexicon.strengths("") == (0.0, 0.0)


def test_the_two_halves_answer_the_same_questions_apart() -> None:
    """`strengths` peels because it reads running text; the halves do not.

    The peeling is what lets a lexicon recognise a word in a sentence, and it is exactly
    what makes it the wrong tool for asking whether the Tanakh had a word: משטרה peels
    down to שטר, and Deuteronomy has שוטרים, but it does not have a police force.
    """
    assert lexicon.strengths("משטרה")[1] >= 4.0, "the generous reading calls it biblical"
    assert lexicon.biblical_strength("משטרה") is None, "the exact one does not"
    assert lexicon.modern_strength("משטרה") == lexicon.strengths("משטרה")[0]
    assert lexicon.modern_strength("") == 0.0


def test_strength_is_still_the_better_of_the_two() -> None:
    for word in ("ממשלה", "חסידיו", "ברקוביץהקדמה", ""):
        assert lexicon.strength(word) == max(lexicon.strengths(word))
