"""Aramaic's emphatic state, read off the pointing (design.md §12, "Aramaic has a hard-spot
list" and "Aramaic's lenses", 2026-10-25): the ending that says "the"."""

from __future__ import annotations

import pytest

from targum.annotate.aramaic_state import emphatic
from targum.models import Token
from targum.render.builder import _state_line


@pytest.mark.parametrize(
    "word",
    [
        "אַרְעָא",  # the earth: ־ָא
        "מַיָּא",  # the water, its yod doubled
        "שְׁמַיָּא",  # the heavens
        "כּוֹכְבַיָּא",  # the stars: the plural's ־יָּא
        "גִּינְתָא",  # the garden: the feminine's ־תָא
        "דִּשְׁמַיָּא",  # of the heavens, with ד on the front
        "וְאַרְעָא",  # and the earth
        "מַלְכָּ֗א",  # the king, with an accent: the dagesh between the qamats and the א
        "זִמְנָא",  # the time
    ],
)
def test_the_emphatic_is_read_off_the_qamats_before_its_alef(word: str) -> None:
    assert emphatic(word)


@pytest.mark.parametrize(
    "word",
    [
        "לָא",  # not
        "וְלָא",  # and not
        "הֲדָא",  # this, feminine
        "חֲדָא",  # one, feminine
        "דִּילְמָא",  # lest
        "קְרָא",  # he called: a verb the hand table knows
        "וַחֲזָא",  # and he saw
        "בְּרָא",  # he created: CְCָא, the perfect of a weak verb
        "וּרְמָא",  # and he cast, the same behind ו
        "הֲוָא",  # he was, which the table files under the pronoun הוּא
        "אַרְעָה",  # ends in ה: Onkelos does not write the emphatic so
        "מַלְכִּין",  # absolute plural
        "ארעא",  # unpointed: nothing to read, so no
        "",
    ],
)
def test_particles_verbs_and_unpointed_words_are_not(word: str) -> None:
    assert not emphatic(word)


def _token(text: str, pos: str | None = None, entity: str | None = None) -> Token:
    return Token(start=0, end=len(text), surface=text, lemma=text, band=0, pos=pos, entity=entity)


def test_the_build_marks_it_on_aramaic_alone_and_never_on_a_name() -> None:
    word = "אַרְעָא"
    assert _state_line(True, _token(word), word) == "State=Emph"
    assert _state_line(False, _token(word), word) == "", "a Hebrew word ending ־ָא is not this"
    assert _state_line(True, _token("עֶזְרָא", pos="PROPN"), "עֶזְרָא") == ""
