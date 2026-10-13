"""Counting how hard a text is (`annotate/difficulty.py`)."""

from __future__ import annotations

import pytest


def test_a_russian_lemma_is_counted_by_all_its_forms() -> None:
    """мочь is everywhere as могу and может and nowhere as мочь; counted by its
    dictionary form alone it was band 6, and Russian measured 12 to 15 points too hard
    (2026-10-13). Summed over its forms it is as common as it is."""
    pytest.importorskip("pymorphy3")
    from targum.annotate.difficulty import band_of, russian_zipf

    assert band_of("мочь", "ru") == 1
    assert band_of("хотеть", "ru") == 1
    assert band_of("крокодил", "ru") >= 4, "a word that is rare stays rare"
    assert russian_zipf("ыбвгд") is None, "no word, no answer"


def test_only_russian_is_summed() -> None:
    from targum.annotate.difficulty import _bands, band_of

    for lemma, language in (("potere", "it"), ("שלום", "he"), ("pouvoir", "fr")):
        assert band_of(lemma, language) == _bands.band(lemma, language)
