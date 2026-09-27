"""The closed-class glosses, written by hand because a dictionary is worst at them."""

from __future__ import annotations

import pytest

from targum.annotate import closed


def test_a_number_says_which_language_the_word_is_in() -> None:
    """Strong numbered the whole lexicon once, so the tables need no flag between them.
    `לֹא` is 3808 in Hebrew and `לָא` is 3809 in Aramaic, and a reader of Daniel meeting
    `דִּי` is not meeting a Hebrew word at all."""
    assert closed.gloss_for("3808", "לא") == "not; no"
    assert closed.gloss_for("3809", "לא") == "not; no"
    assert closed.gloss_for("1768", "די") == "that; which; who; of"


def test_the_two_tables_never_claim_the_same_number() -> None:
    """The whole reason a number is safe to key on. An overlap would mean one of them is
    wrong about which word it is describing."""
    assert not set(closed.HEBREW) & set(closed.ARAMAIC)


def test_one_spelling_two_words_told_apart_by_number() -> None:
    """`אֵת` is the direct-object marker and also the preposition "with", spelled alike.
    Strong's own entry for the first is "[as such unrepresented in English]"."""
    assert closed.gloss_for("853", "את") == "[marks the direct object]"
    assert closed.gloss_for("854", "את") == "with; near"


def test_a_suffix_is_found_by_its_spelling() -> None:
    """The tagging numbers a piece that is a word and letters a piece stuck to one, so a
    pronominal suffix has nothing to key on but how it is written. `בּוֹ` is a preposition
    and a suffix, and the suffix is what the word means."""
    assert closed.gloss_for("l", "ו") == "him; his; it"
    assert closed.gloss_for(None, "ך") == "you; your"


def test_a_word_nobody_wrote_down_says_nothing() -> None:
    assert closed.gloss_for("999999", "zzz") == ""
    assert closed.gloss_for(None, "") == ""


def test_every_gloss_reads_as_a_gloss() -> None:
    """House style, pinned: short, lower case, and no trailing full stop — the shape the
    bought glosses already have. A card is a phrase, not a sentence.

    "I" is the one capital English insists on, and `אֲנִי` is common enough that arguing
    with English about it would be the wrong fight.
    """
    for table in (closed.HEBREW, closed.ARAMAIC, closed.BY_FORM):
        for key, gloss in table.items():
            assert gloss == gloss.strip() and gloss, key
            assert not gloss.endswith("."), f"{key}: {gloss}"
            assert len(gloss) <= 48, f"{key} is too long for a card: {gloss}"
            assert gloss[0].islower() or gloss[0] in "[I", f"{key}: {gloss}"


def test_the_commonest_words_read_in_the_sense_a_learner_meets_first() -> None:
    """targum-internal#378: "Words you may already know" glossed `עם` as "people; nation"
    and left `היא`, `הם` and `להיות` bare."""
    assert closed.common_gloss("עם") == "with"
    assert closed.common_gloss("עם", "ru") == "с"
    assert closed.common_gloss("מי") == "who"
    for bare in ("היא", "הם", "זו", "להיות"):
        assert closed.common_gloss(bare), bare
    assert closed.common_gloss("ספר") == "", "a word the glossary has right is left to it"
    assert closed.common_gloss("עם", "fr") == "", "no French here: the glossary answers"


def test_the_modern_table_keeps_the_house_style_in_both_languages() -> None:
    for form, pair in closed.MODERN.items():
        for gloss in pair:
            assert gloss == gloss.strip() and gloss, form
            assert not gloss.endswith("."), f"{form}: {gloss}"
            assert len(gloss) <= 48, f"{form} is too long for a card: {gloss}"
            assert gloss[0].islower() or gloss[0] in "[I", f"{form}: {gloss}"


def test_the_modern_table_is_the_top_of_the_list_and_nothing_else() -> None:
    """Every row is a word the list reaches in its first two hundred: a row past it is a
    row nobody is shown, and a sign the table has drifted from what it is for."""
    pytest.importorskip("wordfreq")
    from targum.chat import hebrew

    top = set(hebrew.common_words(n=200))
    assert set(closed.MODERN) <= top, sorted(set(closed.MODERN) - top)
