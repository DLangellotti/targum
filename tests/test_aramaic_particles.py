"""ד־ and ית, read off the Aramaic annotator's answer (design.md §12, "Aramaic's lenses",
2026-10-25)."""

from __future__ import annotations

from targum.annotate.aramaic import tokens
from targum.annotate.aramaic_particles import DALET, YAT, particle
from targum.models import Segment, Token
from targum.render.builder import _particle_line


def read(word: str) -> Token:
    (token,) = tokens(Segment(id="w", block_id="w", block_index=0, index=0, text=word))
    return token


def test_dalet_is_the_word_di_and_a_d_the_table_took_off_the_front() -> None:
    assert particle(read("דִּי")) == DALET
    assert particle(read("דְאַרְעָא")) == DALET  # of the earth
    assert particle(read("וּדְאַרְעָא")) == DALET  # and of the earth: ו, then ד
    assert particle(read("דִּשְׁמַיָּא")) == DALET


def test_a_d_that_is_the_root_is_not_and_neither_is_a_word_nobody_knows() -> None:
    assert particle(read("דַּהֲבָא")) == ""  # the gold: its ד is the root's
    assert particle(read("אַרְעָא")) == ""
    assert particle(read("דְּזִיזְוָג")) == "", "a ד the table cannot account for is left alone"


def test_yat_in_all_its_forms() -> None:
    for word in ("יָת", "וְיָת", "יָתֵיהּ", "יָתְהוֹן"):
        assert particle(read(word)) == YAT, word


def test_the_build_says_it_on_aramaic_alone() -> None:
    token = read("דְאַרְעָא")
    assert _particle_line(True, token) == "Particle=D"
    assert _particle_line(False, token) == ""
