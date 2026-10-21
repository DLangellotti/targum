"""The segolate stress rule against ling-he's 106-word set (targum-internal#454).

Each row is a pattern, a pointed word, and the syllable from the end that carries its
stress in standard modern Hebrew: 2 is the one before the last. 72 segolates and their
kin, 16 whose stress moves to the end with a plural or a suffix, and 17 that look like
segolates and are not. Provenance and the Tanakh's agreement are on the card.
"""

from __future__ import annotations

import pytest

from targum.annotate import segolate

ROWS = [
    ("CeCeC", "מֶלֶךְ", 2),  # king
    ("CeCeC", "כֶּסֶף", 2),  # money
    ("CeCeC", "יֶלֶד", 2),  # boy
    ("CeCeC", "דֶּרֶךְ", 2),  # way
    ("CeCeC", "אֶרֶץ", 2),  # land
    ("CeCeC", "בֶּגֶד", 2),  # garment
    ("CeCeC", "גֶּשֶׁם", 2),  # rain
    ("CeCeC", "לֶחֶם", 2),  # bread
    ("CeCeC", "שֶׁמֶשׁ", 2),  # sun
    ("CeCeC", "עֶרֶב", 2),  # evening
    ("CeCeC", "קֶשֶׁר", 2),  # connection
    ("CeCeC", "חֶדֶר", 2),  # room
    ("CeCeC", "מֶזֶג", 2),  # temper/weather
    ("CeCeC", "רֶגֶל", 2),  # foot
    ("CeCeC", "כֶּלֶב", 2),  # dog
    ("CeCeC", "שֶׁקֶל", 2),  # shekel
    ("CeCeC", "חֶסֶד", 2),  # kindness
    ("CeCeC", "נֶפֶשׁ", 2),  # soul
    ("CeCeC", "דֶּלֶת", 2),  # door
    ("CeCeC-alef", "פֶּלֶא", 2),  # wonder (quiescent alef)
    ("tsere-segol", "סֵפֶר", 2),  # book
    ("tsere-segol", "חֵלֶק", 2),  # part
    ("tsere-segol", "חֵפֶץ", 2),  # object
    ("CoCeC", "בֹּקֶר", 2),  # morning
    ("CoCeC", "בּוֹקֶר", 2),  # morning, plene
    ("CoCeC", "אֹהֶל", 2),  # tent
    ("CoCeC", "אֹזֶן", 2),  # ear
    ("CoCeC", "קֹדֶשׁ", 2),  # holiness
    ("CoCeC", "חֹדֶשׁ", 2),  # month
    ("CoCeC", "גֹּדֶל", 2),  # size
    ("CoCeC", "אֹרֶךְ", 2),  # length
    ("CoCeC", "שֹׁרֶשׁ", 2),  # root
    ("CoCaC-gutt", "רֹחַב", 2),  # width
    ("CaCaC-gutt", "לַחַץ", 2),  # pressure
    ("CaCaC-gutt", "נַעַר", 2),  # youth
    ("CaCaC-gutt", "שַׁעַר", 2),  # gate
    ("CaCaC-gutt", "פַּחַד", 2),  # fear
    ("CaCaC-gutt", "רַעַשׁ", 2),  # noise
    ("CaCaC-gutt", "זַעַם", 2),  # rage
    ("CaCaC-gutt", "בַּעַל", 2),  # husband/owner
    ("CeCaC-gutt", "רֶגַע", 2),  # moment
    ("CeCaC-gutt", "זֶרַע", 2),  # seed
    ("CeCaC-gutt", "פֶּתַח", 2),  # opening
    ("CeCaC-gutt", "מֶלַח", 2),  # salt
    ("CeCaC-gutt", "קֶמַח", 2),  # flour
    ("CeCaC-gutt", "שֶׁבַע", 2),  # seven
    ("CeCaC-gutt", "צֶבַע", 2),  # colour
    ("CeCaC-gutt", "טֶבַע", 2),  # nature
    ("CeCaC-gutt", "תֵּשַׁע", 2),  # nine
    ("bayit", "בַּיִת", 2),  # house
    ("bayit", "זַיִת", 2),  # olive
    ("bayit", "עַיִן", 2),  # eye
    ("bayit", "יַיִן", 2),  # wine
    ("mavet", "מָוֶת", 2),  # death
    ("dual", "מַיִם", 2),  # water
    ("dual", "שָׁמַיִם", 2),  # sky
    ("dual", "עֵינַיִם", 2),  # eyes
    ("dual", "רַגְלַיִם", 2),  # legs
    ("dual", "יוֹמַיִם", 2),  # two days
    ("dual", "שְׁבוּעַיִם", 2),  # two weeks
    ("dual", "פַּעֲמַיִם", 2),  # twice
    ("fem-et", "רַכֶּבֶת", 2),  # train
    ("fem-et", "מַחְבֶּרֶת", 2),  # notebook
    ("fem-et", "מִשְׁמֶרֶת", 2),  # shift
    ("fem-et", "כּוֹתֶבֶת", 2),  # writes (f.)
    ("fem-et", "יוֹשֶׁבֶת", 2),  # sits (f.)
    ("fem-et", "שׁוֹמַעַת", 2),  # hears (f.)
    ("fem-et", "יוֹדַעַת", 2),  # knows (f.)
    ("fem-et", "טַבַּעַת", 2),  # ring
    ("prefixed", "הַיֶּלֶד", 2),  # the boy
    ("prefixed", "בַּבֹּקֶר", 2),  # in the morning
    ("prefixed", "לַבַּיִת", 2),  # home(ward)
    ("prefixed", "וְהַכֶּסֶף", 2),  # and the money
    ("moves", "סְפָרִים", 1),  # books
    ("moves", "בָּתִּים", 1),  # houses
    ("moves", "יְלָדִים", 1),  # children
    ("moves", "מְלָכִים", 1),  # kings
    ("moves", "דְּרָכִים", 1),  # ways
    ("moves", "חֳדָשִׁים", 1),  # months
    ("moves", "נְעָרִים", 1),  # youths
    ("moves", "סִפְרִי", 1),  # my book
    ("moves", "בֵּיתִי", 1),  # my house
    ("moves", "יַלְדָּה", 1),  # girl
    ("moves", "מַלְכָּה", 1),  # queen
    ("moves", "דַּרְכּוֹ", 1),  # his way
    ("moves", "רַגְלוֹ", 1),  # his foot
    ("moves", "סִפְרֵי", 1),  # books of (cstr.)
    ("moves", "רַכָּבוֹת", 1),  # trains
    ("moves", "עֵינֶיהָ", 2),  # her eyes (suffix -eha is penult)
    ("trap", "מָלַךְ", 1),  # reigned (verb; qamats first)
    ("trap", "לָחַץ", 1),  # pressed (verb)
    ("trap", "נָעַר", 1),  # shook (verb)
    ("trap", "פָּתַח", 1),  # opened (verb)
    ("trap", "כָּתַב", 1),  # wrote
    ("trap", "אֱמֶת", 1),  # truth (hataf first: not segolate)
    ("trap", "שָׂדֶה", 1),  # field (ends in ה)
    ("trap", "מוֹרֶה", 1),  # teacher (holam-segol + ה)
    ("trap", "עוֹלֶה", 1),  # goes up / immigrant
    ("trap", "מַעֲשֶׂה", 1),  # deed
    ("trap", "מִקְרֶה", 1),  # case
    ("trap", "כּוֹתֵב", 1),  # writes (holam-tsere)
    ("trap", "יוֹדֵעַ", 1),  # knows (furtive patah)
    ("trap", "זָקֵן", 1),  # old
    ("trap", "מֶרְכָּז", 1),  # centre (segol-qamats)
    ("trap", "אֶפְשָׁר", 1),  # possible
    ("trap", "אֵלֶּה", 2),  # these (ends in ה but penult: listed exception)
]


@pytest.mark.parametrize(("pattern", "word", "stress"), ROWS, ids=[f"{r[0]}-{r[1]}" for r in ROWS])
def test_the_rule_places_the_stress_where_modern_hebrew_says_it(
    pattern: str, word: str, stress: int
) -> None:
    placed = segolate.penult(word) is not None
    assert placed == (stress == 2), (pattern, word)


def test_the_mark_is_handed_to_phonikud_after_the_stressed_vowel() -> None:
    assert segolate.place("כֶּסֶף") == "כֶּ֫סֶף"
    assert segolate.place("בּוֹקֶר") == "בּוֹ֫קֶר", "a holam vav carries the mark"
    assert segolate.place("סְפָרִים") is None


def test_a_modern_reading_says_a_segolate_on_its_first_syllable() -> None:
    pytest.importorskip("phonikud")
    from targum.annotate.pronounce import PhonikudPronouncer

    said = PhonikudPronouncer().say(["כֶּסֶף", "בַּיִת", "רַכֶּבֶת", "סְפָרִים", "מָלַךְ"])
    assert said["כֶּסֶף"] == "kˈesef"
    assert said["בַּיִת"] == "bˈajit"
    assert said["רַכֶּבֶת"] == "ʁakˈevet"
    assert said["סְפָרִים"] == "sfaʁˈim", "a plural keeps the last"
    assert said["מָלַךְ"] == "malˈaχ", "the verb keeps the last"


def test_a_one_syllable_word_behind_a_prefix_is_not_a_segolate() -> None:
    """ling-he's modern hand-read (2026-10-21): הַחַג is the article and חַג, שֶׁאֶת is ש
    and אֶת, and both keep the last syllable."""
    for word in ("הַחַג", "שֶׁאֶת", "בַּחַג", "וְהַחַם"):
        assert segolate.penult(word) is None, word
    assert segolate.penult("הַבַּיִת") is not None, "a segolate behind the article still is"


def test_a_segolate_placed_by_the_rule_is_not_inferred() -> None:
    from targum.annotate.pronounce import STRESS_GUESSED, guessed

    # The source bare, the menaked's pointing, and the rule's reading: the vowels were
    # guessed, the stress was placed and measured.
    assert not guessed("כסף", "kˈesef", pointed="כֶּסֶף") & STRESS_GUESSED
    assert guessed("כסף", "kesˈef", pointed="כֶּסֶף") & STRESS_GUESSED, "the reading disagrees"
    assert guessed("ספרים", "sfaʁˈim", pointed="סְפָרִים") & STRESS_GUESSED, "not the rule's word"
    assert guessed("כסף", "kˈesef") & STRESS_GUESSED, "no pointing given, no claim"
