"""Onkelos's words to the Hebrew words they render, learned from the verse pairs and drawn
only where both directions agree (targum-internal G3; design.md §12, 2026-10-25)."""

from __future__ import annotations

import pytest

from targum.annotate import onkelos_align
from targum.annotate.onkelos_align import align, words

pytestmark = pytest.mark.skipif(
    not onkelos_align.LEXICON.is_file(), reason="the alignment lexicon is not counted"
)


def test_a_word_for_word_verse_is_linked_word_for_word() -> None:
    """Genesis 37:4, narrative, as Sefaria prints it: each word to its own."""
    onkelos = words("וַחֲזוֹ אֲחוֹהִי אֲרֵי יָתֵהּ רְחֵם אֲבוּהוֹן מִכָּל אֲחוֹהִי וּסְנוֹ יָתֵהּ")
    hebrew = words("וַיִּרְאוּ אֶחָיו כִּי אֹתוֹ אָהַב אֲבִיהֶם מִכָּל אֶחָיו וַיִּשְׂנְאוּ אֹתוֹ")
    assert align(onkelos, hebrew) == [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]


def test_a_word_the_rendering_adds_is_left_unlinked() -> None:
    """Genesis 1:2: מִן קֳדָם יְיָ, "from before the LORD", is the Targum's reverence, and
    רוּחַ אֱלֹהִים has no word for it: no counterpart is guessed."""
    onkelos = words("וְרוּחָא מִן קֳדָם יְיָ מְנַשְּׁבָא עַל אַפֵּי מַיָּא")
    hebrew = words("וְרוּחַ אֱלֹהִים מְרַחֶפֶת עַל פְּנֵי הַמָּיִם")
    drawn = align(onkelos, hebrew)
    assert drawn[0] == 0 and drawn[1] is None and drawn[2] is None
    assert drawn[-3:] == [3, 4, 5]


def test_nothing_is_drawn_without_a_lexicon(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(onkelos_align, "lexicon", lambda: ({}, {}))
    assert align(words("אַרְעָא"), words("הָאָרֶץ")) == [None]
