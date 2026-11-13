"""The annotator's own verb roots, fixed at the cause (targum-internal#590).

`verb_roots.WRONG` hides these at page build; this is the annotator no longer writing
them. Single words only, as the card asks: each test is one lemma and the one word it
stands under, so a failure names the word.

None of this reaches a text already on the shelf until the Hebrew annotator is renamed
for some other reason: the fixes ride that rename and never get one of their own.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from targum.annotate.dicta import _binyan_of, _shape, nifal_shown, unrelated
from targum.annotate.dictionary import Entry
from targum.annotate.hebrew import root_of
from targum.models import Token


def _verb(lemma: str, word: str) -> tuple[str | None, str | None]:
    """The (binyan, root) `dicta._tokens` gives a verb `lemma` standing under `word`,
    when nothing else said a binyan (the nif'al check included, as `_tokens` asks it)."""
    binyan = _binyan_of(lemma)
    if binyan is None and nifal_shown(lemma, word):
        binyan = "נפעל"
    return _shape(lemma, binyan, word)


# Three letters that are not a qal: a geminate or I-nun hif'il whose root the lemma does
# not write. Each was given itself as its root.
@pytest.mark.parametrize(
    ("lemma", "word", "root"),
    [
        ("הקל", "להקל", "קלל"),  # הֵקֵל, to lighten: ק־ל־ל
        ("החל", "החלה", "חלל"),  # הֵחֵל, to begin: ח־ל־ל
        ("הכה", "הכתה", "נכה"),  # הִכָּה, to hit: נ־כ־ה
        ("הפר", "להפר", "פרר"),  # הֵפֵר, to break (a promise): פ־ר־ר
        ("הטה", "הטו", "נטה"),  # הִטָּה, to tilt: נ־ט־ה
        ("הצל", "הצלתי", "נצל"),  # הִצַּלְתִּי, I saved: נ־צ־ל
    ],
)
def test_a_three_letter_hifil_gets_its_own_root_not_its_lemma(
    lemma: str, word: str, root: str
) -> None:
    assert _binyan_of(lemma) is None
    assert _verb(lemma, word) == ("הפעיל", root)


@pytest.mark.parametrize(("lemma", "word"), [("הכה", "יכו"), ("הקל", "נקל")])
def test_a_three_letter_hifil_whose_word_shows_no_hifil_keeps_a_gap(lemma: str, word: str) -> None:
    """יַכּוּ unpointed, and the nif'al נָקֵל DICTA files under הקל: no hif'il ה, מ or yod
    to see, so no binyan, and no root rather than the lemma itself."""
    assert _verb(lemma, word) == (None, None)


@pytest.mark.parametrize(("lemma", "word", "root"), [("נמס", "נמס", "מסס"), ("נדם", "נדם", "דמם")])
def test_a_three_letter_nifal_of_a_doubled_root_gets_that_root(
    lemma: str, word: str, root: str
) -> None:
    assert _verb(lemma, word) == ("נפעל", root)


@pytest.mark.parametrize(
    "lemma",
    ["דעת", "מכה", "מטה", "מגן", "מקל", "מצר", "שמה", "מבט", "משא", "שבי"],
)
def test_a_three_letter_word_that_is_no_qal_past_gives_no_root(lemma: str) -> None:
    """An infinitive (דעת), a hif'il present (מכה, מגן), or a noun DICTA tagged a verb
    (מבט, משא): none is a qal past, and its letters are not its root."""
    assert _binyan_of(lemma) is None
    assert _verb(lemma, lemma) == (None, None)


@pytest.mark.parametrize(("lemma", "root"), [("כתב", "כתב"), ("הלך", "הלך"), ("נתן", "נתן")])
def test_a_three_letter_qal_is_still_its_own_root(lemma: str, root: str) -> None:
    assert _binyan_of(lemma) == "פעל"
    assert _verb(lemma, lemma) == ("פעל", root)


# Adjectives and qal passive participles spelled like a nif'al past, whose own נ was
# stripped as the nif'al's.
@pytest.mark.parametrize(
    ("lemma", "word", "root"),
    [
        ("נשוא", "נשואים", "נשא"),  # נָשׂוּא: נ־שׂ־א
        ("נשוי", "נשויה", "נשא"),  # נָשׂוּי: נ־שׂ־א
        ("נקוב", "נקוב", "נקב"),  # נָקוּב: נ־ק־ב
        ("נסוך", "נסוך", "נסך"),  # נָסוּךְ: נ־ס־ך
        ("נטול", "נטולה", "נטל"),  # נְטוּל: נ־ט־ל
    ],
)
def test_a_qal_passive_participle_on_a_nun_root_keeps_its_nun(
    lemma: str, word: str, root: str
) -> None:
    assert _verb(lemma, word) == ("פעל", root)


@pytest.mark.parametrize(
    ("lemma", "word"), [("נזיר", "נזיר"), ("נעים", "נעימה"), ("נקבה", "נקבה"), ("נשמה", "נשמה")]
)
def test_a_word_spelled_like_a_nifal_that_is_not_one_is_no_nifal(lemma: str, word: str) -> None:
    """נָזִיר and נָעִים: no nif'al past has a yod before its last letter. נְקֵבָה and
    נְשָׁמָה are named, since a III-he nif'al (נִבְנָה) is spelled the same."""
    assert not nifal_shown(lemma, word)
    assert _verb(lemma, word) == (None, None)


def test_a_nifal_with_a_yod_before_its_last_letter_has_no_root() -> None:
    assert root_of("נזיר", "נפעל") is None
    assert root_of("נעים", "נפעל") is None


@pytest.mark.parametrize(
    ("lemma", "word", "root"),
    [("נכנס", "נכנס", "כנס"), ("נכון", "נכון", "כון"), ("נשאר", "נשאר", "שאר")],
)
def test_a_real_nifal_keeps_its_root(lemma: str, word: str, root: str) -> None:
    assert _verb(lemma, word) == ("נפעל", root)


def test_hetil_is_tet_vav_lamed() -> None:
    """הֵטִיל, to cast or impose, is ט־ו־ל, not נ־ט־ל."""
    assert root_of("הטיל", "הפעיל") == "טול"
    assert _verb("הטיל", "להטיל") == ("הפעיל", "טול")
    # תִּטֹּל, "she will take", is נ־ט־ל's: filed under הטיל, it shows no hif'il, so a gap.
    assert _verb("הטיל", "תטל") == (None, None)


def test_the_dictionary_fills_no_root_for_a_verb_the_reviewed_list_covers() -> None:
    """The model-made dictionary said נ־ט־ל for הטיל, and filled it wherever the annotator
    gave none. The reviewed list is the word on its own lemmas: a gap, not that root."""
    from targum.annotate import Annotator

    holder = SimpleNamespace(dictionary={"הטיל": Entry(root="נטל", binyan="הפעיל")})
    token = Token(start=0, end=3, surface="תטל", lemma="הטיל", band=0, pos="VERB")
    assert Annotator._from_dictionary(holder, token) == {}  # type: ignore[arg-type]
    # And a verb it does not cover is filled as before.
    holder = SimpleNamespace(dictionary={"כתב": Entry(root="כתב", binyan="פעל")})
    token = Token(start=0, end=3, surface="כתב", lemma="כתב", band=0, pos="VERB")
    assert Annotator._from_dictionary(holder, token) == {"root": "כתב", "binyan": "פעל"}  # type: ignore[arg-type]


@pytest.mark.parametrize("lemma", ["ושב", "ובא", "וקם", "ומת"])
def test_a_conjunction_left_on_a_lemma_is_no_root(lemma: str) -> None:
    """ו + שב is "and returned", not a root ו־שׁ־ב."""
    assert _binyan_of(lemma) is None
    assert _verb(lemma, lemma) == (None, None)


# A nun is let go only where Hebrew lets it go: first in the root, or last before a
# suffix's ת. The rule `lemma_check.refused` holds at page build, now in the annotator.
def test_a_middle_nun_is_a_letter_the_word_must_spell() -> None:
    """נַשְׁתִּיק, "we will silence", is not התקין's: ת־ק־נ's nun is last, and no ת follows it."""
    assert unrelated("התקין", "נשתיק")


@pytest.mark.parametrize(
    ("lemma", "word"),
    [
        ("נפל", "יפול"),  # a first nun, assimilated
        ("נתן", "תן"),
        ("נתן", "נתתי"),  # a last nun, taken into the suffix's ת
        ("נתן", "לתת"),  # both: לָתֵת
        ("התקין", "מתקין"),
        ("התעורר", "מתעורר"),
    ],
)
def test_a_nun_that_assimilates_may_still_drop(lemma: str, word: str) -> None:
    assert not unrelated(lemma, word)
