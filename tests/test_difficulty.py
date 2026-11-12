"""Counting how hard a text is (`annotate/difficulty.py`)."""

from __future__ import annotations

from pathlib import Path

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


def test_only_russian_and_french_are_summed(monkeypatch: pytest.MonkeyPatch) -> None:
    from targum.annotate import difficulty
    from targum.annotate.difficulty import _band_of, _bands, band_of

    for lemma, language in (("potere", "it"), ("שלום", "he")):
        assert band_of(lemma, language) == _bands.band(lemma, language)
    # And French as before where this machine never fetched Morphalou.
    monkeypatch.setattr(difficulty, "_french_sums", lambda: None)
    _band_of.cache_clear()
    try:
        assert band_of("sembler", "fr") == _bands.band("sembler", "fr")
    finally:
        _band_of.cache_clear()


#: Morphalou's shape (`tests/test_morphalou.py` has the whole of it): a preamble, the
#: header rows, then a lemma's first row with its spelling and category and its other
#: forms below. luire lists lui, which is mostly the pronoun's.
TABLE = """\
LEMME;;;;;;;;;FLEXION;;;;;;;;
GRAPHIE;ID;CATÉGORIE;SOUS CATÉGORIE;LOCUTION;GENRE;AUTRES LEMMES LIÉS;PHONÉTIQUE;ORIGINES;\
GRAPHIE;ID;NOMBRE;MODE;GENRE;TEMPS;PERSONNE;PHONÉTIQUE;ORIGINES
sembler;1;Verbe;;;-;;;m;sembler;1;-;infinitive;-;-;-;;m
;;;;;;;;;semble;2;singular;indicative;-;present;thirdPerson;;m
;;;;;;;;;semble;3;singular;indicative;-;present;firstPerson;;m
;;;;;;;;;semblait;4;singular;indicative;-;imperfect;thirdPerson;;m
;;;;;;;;;se sembler;5;-;infinitive;-;-;-;;m
lui;2;Pronom;;;-;;;m;lui;6;singular;-;masculine;-;thirdPerson;;m
luire;3;Verbe;;;-;;;m;luire;7;-;infinitive;-;-;-;;m
;;;;;;;;;lui;8;-;participle;-;past;-;;m
;;;;;;;;;luit;9;singular;indicative;-;present;thirdPerson;;m
"""

FREQUENCY = {
    "sembler": 1e-5,
    "semble": 1e-4,
    "semblait": 3e-5,
    "lui": 1e-3,
    "luire": 1e-7,
    "luit": 1e-7,
}


def _sums() -> dict[str, float]:
    from targum.annotate.difficulty import french_sums

    return french_sums(TABLE.splitlines, FREQUENCY)


def test_a_french_lemma_is_counted_by_its_forms() -> None:
    """sembler is read as semble and semblait, so its infinitive alone put it at band 4
    and French verbs counted as looked up twice as often as they are (targum-internal#562,
    2026-11-05). A form listed twice under one lemma counts once."""
    sums = _sums()
    assert sums["sembler"] == pytest.approx(1e-5 + 1e-4 + 3e-5)


def test_a_form_two_lemmas_own_is_shared_by_how_common_each_is() -> None:
    """Morphalou lists lui under luire, and summed whole the rare verb came out as common
    as the pronoun. Shared in proportion to each lemma's own frequency, it keeps almost
    none of it."""
    sums = _sums()
    luire_share = 1e-3 * 1e-7 / (1e-3 + 1e-7)
    assert sums["luire"] == pytest.approx(1e-7 + luire_share + 1e-7)
    assert sums["lui"] == pytest.approx(1e-3 - luire_share)


def test_a_name_spelled_as_a_rare_verb_s_form_is_not_the_verb_s() -> None:
    """luis is luire's, and mostly the name Luis: taken whole it put luire at band 4
    (qa-claude on #1111). A form far commoner than anything else its lemma is read as is
    another word's, and is left out; semble, five times semblait, is still sembler's."""
    from targum.annotate.difficulty import french_sums

    table = TABLE + ";;;;;;;;;luis;10;singular;indicative;-;present;firstPerson;;m\n"
    sums = french_sums(table.splitlines, {**FREQUENCY, "luis": 1e-5})
    luire_share = 1e-3 * 1e-7 / (1e-3 + 1e-7)
    assert sums["luire"] == pytest.approx(1e-7 + luire_share + 1e-7), "no share of Luis"
    assert sums["sembler"] == pytest.approx(1e-5 + 1e-4 + 3e-5)


def test_a_name_is_left_out_even_where_nothing_else_of_the_lemma_was_seen() -> None:
    """hui is huir's in Morphalou and wordfreq saw neither huir nor its other forms, so
    there was nothing to compare hui with and the rare verb took the whole word
    (qa-claude on #1111)."""
    from targum.annotate.difficulty import french_sums

    head = "\n".join(TABLE.splitlines()[:2])
    table = (
        f"{head}\n"
        "huir;1;Verbe;;;-;;;m;huir;1;-;infinitive;-;-;-;;m\n"
        ";;;;;;;;;hui;2;singular;indicative;-;present;thirdPerson;;m\n"
        ";;;;;;;;;huit;3;singular;indicative;-;present;thirdPerson;;m\n"
    )
    assert "huir" not in french_sums(table.splitlines, {"hui": 1e-4})


def test_a_form_owned_only_by_unseen_lemmas_is_split_not_counted_twice() -> None:
    """Two lemmas wordfreq never saw, both listing one common form, take half each
    (qa-claude on #1111): whole to each, the form was counted twice."""
    from targum.annotate.difficulty import french_sums

    head = "\n".join(TABLE.splitlines()[:2])
    table = (
        f"{head}\n"
        "xa;1;Verbe;;;-;;;m;xa;1;-;infinitive;-;-;-;;m\n"
        ";;;;;;;;;commun;2;singular;indicative;-;present;thirdPerson;;m\n"
        "xb;2;Verbe;;;-;;;m;xb;3;-;infinitive;-;-;-;;m\n"
        ";;;;;;;;;commun;4;singular;indicative;-;present;thirdPerson;;m\n"
    )
    sums = french_sums(table.splitlines, {"commun": 1e-3})
    assert sums == {"xa": pytest.approx(5e-4), "xb": pytest.approx(5e-4)}


def test_a_french_lemma_is_never_harder_than_its_own_spelling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A lemma whose forms are mostly another's (été the summer, été of être) can sum to
    less than its own spelling; the sum only ever makes a word easier."""
    from targum.annotate import difficulty
    from targum.annotate.difficulty import _band_of, _bands, band_of

    monkeypatch.setattr(difficulty, "_french_sums", lambda: {"été": 1e-8, "sembler": 1.4e-4})
    _band_of.cache_clear()
    try:
        assert band_of("été", "fr") == _bands.band("été", "fr")
        assert band_of("sembler", "fr") == 2, "Zipf 5.15 is band 2"
        assert band_of("crocodile", "fr") == _bands.band("crocodile", "fr"), "not in it"
    finally:
        _band_of.cache_clear()


def test_french_picks_morphalou_up_once_it_lands_without_a_restart(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """deploy.sh restarts the service before it fetches Morphalou, so on a fresh or
    restored box the first French words are measured without it. That absence was
    remembered, and French stayed without Morphalou until the next restart
    (targum-internal#682). The next word after the table lands is summed."""
    wordfreq = pytest.importorskip("wordfreq")
    from targum.annotate import difficulty, morphalou
    from targum.annotate.difficulty import _band_of, _bands, band_of

    monkeypatch.setenv("TARGUM_MODEL_DIR", str(tmp_path))
    monkeypatch.setattr(difficulty, "_FRENCH_SUMS", None)
    monkeypatch.setattr(wordfreq, "get_frequency_dict", lambda _language: FREQUENCY)
    _band_of.cache_clear()
    try:
        alone = _bands.band("sembler", "fr")
        assert alone > 2, "the infinitive alone is rarer than the verb"
        assert band_of("sembler", "fr") == alone, "no table yet: as before"
        assert difficulty._french_sums() is None

        table = morphalou.directory() / morphalou.TABLE
        table.parent.mkdir(parents=True)
        table.write_text(TABLE, encoding="utf-8")

        assert band_of("sembler", "fr") == 2, "summed now, with no restart in between"
        assert difficulty._french_sums() is difficulty._french_sums(), "read once"
    finally:
        _band_of.cache_clear()
