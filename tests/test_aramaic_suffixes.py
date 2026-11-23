"""A pronoun on the end of an Aramaic word (design.md §12, "Aramaic's lenses", 2026-10-25):
how many of its letters are the ending, so the lens can light the ending alone."""

from __future__ import annotations

import pytest

from targum.annotate.aramaic_suffixes import suffix_letters
from targum.models import Token
from targum.render.builder import _arc_suffix_line


@pytest.mark.parametrize(
    ("word", "n"),
    [
        ("יָתֵיהּ", 2),  # him
        ("זַרְעֵהּ", 1),  # his seed
        ("לַהּ", 1),  # to her
        ("עֲלוֹהִי", 3),  # on him
        ("אֲבוּהוֹן", 3),  # their father
        ("לְכוֹן", 3),  # to you, plural
        ("בְּנָךְ", 1),  # your son
        ("אַחָיךְ", 2),  # your brothers
        ("לְהֹם", 2),  # Daniel's "to them"
    ],
)
def test_the_ending_and_how_long_it_is(word: str, n: int) -> None:
    assert suffix_letters(word) == n


@pytest.mark.parametrize(
    "word",
    [
        "אֱלָהּ",  # God: the ה with a mappiq is the root's
        "מֶלֶךְ",  # king: a ך after a segol is the root's
        "סְמַךְ",  # he leaned: and after a patah
        "יְהוֹן",  # they will be: a prefix letter and the root
        "אַרְעָא",
        "עלוהי",  # unpointed: nothing to read, so none
        "",
    ],
)
def test_root_letters_verbs_and_unpointed_words_have_none(word: str) -> None:
    assert suffix_letters(word) == 0


def test_the_build_says_it_on_aramaic_alone_and_never_on_a_name() -> None:
    word = "עֲלוֹהִי"
    token = Token(start=0, end=len(word), surface=word, lemma=word, band=0)
    assert _arc_suffix_line(True, token, word) == "Ending=3"
    assert _arc_suffix_line(False, token, word) == ""
    name = token.model_copy(update={"pos": "PROPN"})
    assert _arc_suffix_line(True, name, word) == ""
