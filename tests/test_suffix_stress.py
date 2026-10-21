"""The suffix stress rule against ling-he's 83-word set (targum-internal#500).

Each row is a class, a pointed word, its part of speech and features as the annotator
gives them, and whether the stress is on the second syllable from the end. 62 targets
(the past's first and second person, -nu, -cha, -ájich) and 21 traps that end the same
way and keep the stress at the end.
"""

from __future__ import annotations

import pytest

from targum.annotate import suffix_stress

P1S = ("VERB", "Tense=Past|Person=1|Number=Sing")
P2MS = ("VERB", "Tense=Past|Person=2|Number=Sing|Gender=Masc")
P1P = ("VERB", "Tense=Past|Person=1|Number=Plur")
ADP = ("ADP", "")
NOUN = ("NOUN", "")
PRON = ("PRON", "")

TARGETS = [
    *[(w, *P1S) for w in (
        "כָּתַבְתִּי", "אָמַרְתִּי", "שָׁמַעְתִּי", "לָמַדְתִּי", "יָדַעְתִּי", "הָלַכְתִּי", "זָכַרְתִּי",
        "רָאִיתִי", "עָשִׂיתִי", "קָנִיתִי", "קַמְתִּי", "בָּאתִי", "שַׂמְתִּי", "נָתַתִּי", "דִּבַּרְתִּי",
        "הִכְנַסְתִּי", "הִתְחַלְתִּי", "הִתְלַבַּשְׁתִּי", "נִכְנַסְתִּי", "הֵבֵאתִי",
    )],
    *[(w, *P2MS) for w in (
        "כָּתַבְתָּ", "אָמַרְתָּ", "רָאִיתָ", "עָשִׂיתָ", "דִּבַּרְתָּ", "הִבְטַחְתָּ", "קַמְתָּ",
    )],
    *[(w, *P1P) for w in (
        "כָּתַבְנוּ", "אָמַרְנוּ", "רָאִינוּ", "עָשִׂינוּ", "הָלַכְנוּ", "דִּבַּרְנוּ", "הִגַּעְנוּ",
        "נָתַנּוּ", "בָּאנוּ", "קַמְנוּ",
    )],
    *[(w, *ADP) for w in (
        "שֶׁלָּנוּ", "לָנוּ", "אוֹתָנוּ", "אִתָּנוּ", "עָלֵינוּ", "אֵלֵינוּ", "לְפָנֵינוּ", "מִמֶּנּוּ",
        "עִמָּנוּ",
    )],
    *[(w, *NOUN) for w in ("בֵּיתֵנוּ", "אַרְצֵנוּ", "אֱלֹהֵינוּ", "אֲבוֹתֵינוּ")],
    *[(w, *PRON) for w in ("אֲנַחְנוּ", "אָנוּ")],
    *[(w, *ADP) for w in ("אֵלֶיךָ", "עָלֶיךָ", "לְפָנֶיךָ", "אַחֲרֶיךָ")],
    *[(w, *NOUN) for w in ("אֱלֹהֶיךָ", "בָּנֶיךָ", "יָדֶיךָ", "עֵינֶיךָ", "עֵינַיִךְ", "יָדַיִךְ")],
]  # fmt: skip

TRAPS = [
    ("כָּתְבוּ", "VERB", "Tense=Past|Person=3|Number=Plur"),
    ("כְּתַבְתֶּם", "VERB", "Tense=Past|Person=2|Number=Plur|Gender=Masc"),
    ("כָּתְבָה", "VERB", "Tense=Past|Person=3|Number=Sing|Gender=Fem"),
    ("כָּתַבְתְּ", "VERB", "Tense=Past|Person=2|Number=Sing|Gender=Fem"),
    ("אֶכְתֹּב", "VERB", "Tense=Fut|Person=1|Number=Sing"),
    ("נִכְתֹּב", "VERB", "Tense=Fut|Person=1|Number=Plur"),
    ("תִּכְתְּבִי", "VERB", "Tense=Fut|Person=2|Number=Sing|Gender=Fem"),
    ("כִּתְבוּ", "VERB", "Mood=Imp|Person=2|Number=Plur"),
    ("נָתְנוּ", "VERB", "Tense=Past|Person=3|Number=Plur"),
    ("בָּנוּ", "VERB", "Tense=Past|Person=3|Number=Plur"),
    ("קָנוּ", "VERB", "Tense=Past|Person=3|Number=Plur"),
    ("בָּאוּ", "VERB", "Tense=Past|Person=3|Number=Plur"),
    ("אִשְׁתִּי", "NOUN", ""),
    ("דַּעְתִּי", "NOUN", ""),
    ("בִּתִּי", "NOUN", ""),
    ("לְךָ", "ADP", ""),
    ("שֶׁלְּךָ", "ADP", ""),
    ("אוֹתְךָ", "PRON", ""),
    ("סִפְרְךָ", "NOUN", ""),
    ("בָּנָיו", "NOUN", ""),
    ("שֶׁלָּהֶם", "ADP", ""),
]


@pytest.mark.parametrize(("word", "pos", "feats"), TARGETS, ids=[t[0] for t in TARGETS])
def test_a_suffix_that_holds_the_stress_back_is_read(word: str, pos: str, feats: str) -> None:
    assert suffix_stress.fires(word, suffix_stress.gate(pos, feats)), word


@pytest.mark.parametrize(("word", "pos", "feats"), TRAPS, ids=[t[0] for t in TRAPS])
def test_a_word_that_only_ends_the_same_way_keeps_the_last(word: str, pos: str, feats: str) -> None:
    assert not suffix_stress.fires(word, suffix_stress.gate(pos, feats)), word


def test_in_us_and_they_built_are_stressed_apart() -> None:
    """בָּנוּ is pointed the same both ways; the class says which."""
    assert suffix_stress.fires("בָּנוּ", suffix_stress.gate("ADP", ""))
    assert not suffix_stress.fires("בָּנוּ", suffix_stress.gate("VERB", "Tense=Past|Person=3"))


def test_a_modern_reading_holds_the_stress_back_and_a_masoretic_one_keeps_its_accent() -> None:
    pytest.importorskip("phonikud")
    from targum.annotate.pronounce import PhonikudPronouncer

    key = suffix_stress.GATE
    said = PhonikudPronouncer().say(
        [
            "אָמַרְתִּי" + key + suffix_stress.gate(*P1S),
            "שֶׁלָּנוּ" + key + suffix_stress.gate(*ADP),
            "אֵלֶיךָ" + key + suffix_stress.gate(*ADP),
            # The sequential perfect, accented at the end: the accent wins.
            "וְאָמַרְתָּ֣" + key + suffix_stress.gate(*P2MS),
        ]
    )
    values = list(said.values())
    assert values[0] == "ʔamˈaʁti"
    assert values[1] == "ʃelˈanu"
    assert values[2].startswith("ʔelˈe")
    assert values[3].endswith("tˈa"), values[3]
