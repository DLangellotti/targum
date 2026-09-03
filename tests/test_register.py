"""Which Hebrew a word belongs to, where its two registers disagree."""

from __future__ import annotations

import pytest

from targum.annotate import register


@pytest.mark.parametrize(
    "word",
    [
        # Everywhere in scripture, gone from the street. The whole reason the card says
        # anything: `strength` calls this ordinary and a learner reads that as "you will
        # meet this in Tel Aviv", which is false. Not עקש, which was here while the table
        # was counted off four books: over the whole Tanakh it is eleven occurrences, and
        # eleven is the tail, not "ordinary in the Tanakh".
        "זבח",
        "שפחה",
        "אהל",
    ],
)
def test_a_word_out_of_the_tanakh_and_out_of_use_is_biblical(word: str) -> None:
    assert register.of(word, "he") == register.BIBLICAL


@pytest.mark.parametrize("word", ["אוטובוס", "טלוויזיה"])
def test_a_word_in_use_the_tanakh_never_had_is_modern(word: str) -> None:
    assert register.of(word, "he") == register.MODERN


@pytest.mark.parametrize("word", ["מלך", "ארץ", "ממשלה"])
def test_a_word_ordinary_in_both_registers_is_left_alone(word: str) -> None:
    """Nothing to say. The registers agree, and a line saying so would spend a line.

    ממשלה is here on purpose: it is a newspaper word and it is also in Genesis 1, and
    the card that called it modern would be wrong about the reader's own Bible.
    """
    assert register.of(word, "he") is None


def test_a_word_read_off_scripture_is_never_called_modern() -> None:
    """A word on the page of Deuteronomy the reader is looking at is in the Tanakh,
    whatever the table says: a miss there is a spelling the count did not see, and the
    honest line is no line (targum-internal#156). The table cannot know טלוויזיה, and
    on a modern text that is the right "modern"; on scripture the same miss says nothing.
    """
    assert register.of("טלוויזיה", "he") == register.MODERN, "the cold answer, for a modern text"
    assert register.of("טלוויזיה", "he", scripture=True) is None
    # The other direction is untouched: a word the table knows is still what it is.
    assert register.of("זבח", "he", scripture=True) == register.BIBLICAL
    assert register.of("מלך", "he", scripture=True) is None


def test_the_table_knows_a_word_under_both_names() -> None:
    """The word that was noticed. The tagging files נִצָּבִים under נצב and DICTA under
    ניצב; the first table had only Stanza's נצב, so a verse DICTA read was "modern · not
    in the Tanakh" on the first word of Nitzavim. Counted under both, both are the same
    ordinary biblical word, and neither is modern."""
    assert register.of("נצב", "he") == register.BIBLICAL
    assert register.of("ניצב", "he") is not register.MODERN
    from targum.lexicon import biblical_strength

    assert biblical_strength("ניצב") is not None


def test_a_word_rare_in_both_registers_is_left_alone() -> None:
    """The level already says hard. Saying it twice is not saying more."""
    assert register.of("ברקוביץהקדמה", "he") is None
    assert register.of("", "he") is None


def test_the_lemma_is_looked_up_as_it_stands_rather_than_peeled() -> None:
    """`peel` is for running text, and every Hebrew stem is some word's stem.

    משטרה peels down to שטר, and Deuteronomy has שוטרים — but it does not have a police
    force. A lexicon generous enough to read a sentence is too generous to answer this,
    and asking it here left every modern word looking scriptural and the "modern" half
    of the card unreachable.
    """
    from targum import lexicon

    assert lexicon.strengths("משטרה")[1] >= register.ORDINARY
    assert register.of("משטרה", "he") == register.MODERN


def test_only_hebrew_is_asked() -> None:
    """The two corpora behind this are a Hebrew frequency list and the Tanakh."""
    assert not register.supports("ru")
    assert register.of("правительство", "ru") is None
    assert register.supports("he") and register.supports("he-IL")


def test_ordinary_sits_between_the_tanakh_bands_that_carry_the_corpus_and_its_tail() -> None:
    """Bands 1 to 4 clear the bar; 5 and 6, where the hapax legomena live, do not.

    One appearance in scripture is not evidence that scripture is where a word lives,
    and calling a hapax "ordinary in the Tanakh" would be the invention this avoids.
    """
    from targum.lexicon import _BIBLICAL_STRENGTH

    assert all(_BIBLICAL_STRENGTH[band] >= register.ORDINARY for band in (1, 2, 3, 4))
    assert all(_BIBLICAL_STRENGTH[band] < register.ORDINARY for band in (5, 6))
