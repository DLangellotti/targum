"""The vav-consecutive, read off the pointing (targum-internal#449, 2026-10-21): Hebrew's
eighth hard spot, design.md §12, "Past Beta, the badge drops"."""

from __future__ import annotations

import pytest

from targum.annotate.vav_consecutive import consecutive
from targum.models import Token
from targum.render.builder import _vav_line


@pytest.mark.parametrize(
    "word",
    [
        "וַיֹּ֥אמֶר",  # he said: the yod doubled
        "וַתֹּאמֶר",  # she said
        "וַנֵּלֶךְ",  # we went
        "וַיְהִי",  # and it was: the yod drops its dagesh under a shva
        "וָאֹמַר",  # I said: the א cannot double, so the vav takes a qamats
        "וַיַּ֧רְא",  # and he saw, with its accent
    ],
)
def test_the_narrative_vav_is_read_off_its_points(word: str) -> None:
    assert consecutive(word)


@pytest.mark.parametrize(
    "word",
    [
        "וְיֹאמַר",  # a plain vav, with a shva: "and let him say"
        "וּתְדַבֵּר",  # a plain vav, a shureq
        "וְאָמַרְתָּ",  # a vav on the past form, which is not this spot
        "ויאמר",  # unpointed: nothing to read, so no
        "יֹאמַר",  # no vav at all
        "וַאֲנִי",  # a patah before a hataf, and a pronoun
        "",
    ],
)
def test_the_plain_vav_and_an_unpointed_word_are_not(word: str) -> None:
    assert not consecutive(word)


def _token(text: str, pos: str | None = "VERB", feats: str | None = None) -> Token:
    return Token(start=0, end=len(text), surface=text, lemma="אמר", band=0, pos=pos, feats=feats)


def test_the_build_marks_it_in_scripture_alone_and_never_on_a_noun() -> None:
    """Read off the page's own pointed text, so a verse annotated before 2026-10-21 shows
    it without being annotated again; Biblical only, as the spot is declared."""
    word = "וַיֹּ֥אמֶר"
    assert _vav_line(True, _token(word), word) == "Vav=Cons"
    assert _vav_line(False, _token(word), word) == ""
    # A noun paired with ו is the rule's one kind of false mark; the annotator's part of
    # speech takes it away.
    assert _vav_line(True, _token("וָאָרֶץ", pos="NOUN"), "וָאָרֶץ") == ""
    # Open Scriptures already said so: not twice.
    assert _vav_line(True, _token(word, feats="Tense=Past|Vav=Cons"), word) == ""
