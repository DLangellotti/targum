"""The chanting marks named, and verses divided into the phrases they sing.

Every verse here is the Westminster Leningrad Codex (public domain) as the Open Scriptures
file carries it, with the maqaf, paseq and sof pasuq that file keeps apart put back where
the codex writes them. The expected phrases were checked by hand against the verse's
chanting as a tikkun lays it out. Nothing here touches the network.
"""

from __future__ import annotations

import pytest

from targum.annotate.pronounce import UNPLACED
from targum.vocalize import trope
from targum.vocalize.trope import Rank

GEN_1_1 = "בְּרֵאשִׁ֖ית בָּרָ֣א אֱלֹהִ֑ים אֵ֥ת הַשָּׁמַ֖יִם וְאֵ֥ת הָאָֽרֶץ׃"
GEN_1_2 = "וְהָאָ֗רֶץ הָיְתָ֥ה תֹ֨הוּ֙ וָבֹ֔הוּ וְחֹ֖שֶׁךְ עַל־פְּנֵ֣י תְה֑וֹם וְר֣וּחַ אֱלֹהִ֔ים מְרַחֶ֖פֶת עַל־פְּנֵ֥י הַמָּֽיִם׃"
GEN_1_3 = "וַיֹּ֥אמֶר אֱלֹהִ֖ים יְהִ֣י א֑וֹר וַֽיְהִי־אֽוֹר׃"
GEN_1_5 = "וַיִּקְרָ֨א אֱלֹהִ֤ים ׀ לָאוֹר֙ י֔וֹם וְלַחֹ֖שֶׁךְ קָ֣רָא לָ֑יְלָה וַֽיְהִי־עֶ֥רֶב וַֽיְהִי־בֹ֖קֶר י֥וֹם אֶחָֽד׃ פ"
GEN_1_7 = "וַיַּ֣עַשׂ אֱלֹהִים֮ אֶת־הָרָקִיעַ֒ וַיַּבְדֵּ֗ל בֵּ֤ין הַמַּ֨יִם֙ אֲשֶׁר֙ מִתַּ֣חַת לָרָקִ֔יעַ וּבֵ֣ין הַמַּ֔יִם אֲשֶׁ֖ר מֵעַ֣ל לָרָקִ֑יעַ וַֽיְהִי־כֵֽן׃"
GEN_1_21 = (
    "וַיִּבְרָ֣א אֱלֹהִ֔ים אֶת־הַתַּנִּינִ֖ם הַגְּדֹלִ֑ים וְאֵ֣ת כָּל־נֶ֣פֶשׁ "
    "הַֽחַיָּ֣ה ׀ הָֽרֹמֶ֡שֶׂת אֲשֶׁר֩ שָׁרְצ֨וּ הַמַּ֜יִם לְמִֽינֵהֶ֗ם וְאֵ֨ת "
    "כָּל־ע֤וֹף כָּנָף֙ לְמִינֵ֔הוּ וַיַּ֥רְא אֱלֹהִ֖ים כִּי־טֽוֹב׃"
)
GEN_1_30 = (
    "וּֽלְכָל־חַיַּ֣ת הָ֠אָרֶץ וּלְכָל־ע֨וֹף הַשָּׁמַ֜יִם וּלְכֹ֣ל ׀ רוֹמֵ֣שׂ עַל־הָאָ֗רֶץ אֲשֶׁר־בּוֹ֙ נֶ֣פֶשׁ חַיָּ֔ה אֶת־כָּל־יֶ֥רֶק עֵ֖שֶׂב לְאָכְלָ֑ה וַֽיְהִי־כֵֽן׃"
)
GEN_2_6 = "וְאֵ֖ד יַֽעֲלֶ֣ה מִן־הָאָ֑רֶץ וְהִשְׁקָ֖ה אֶֽת־כָּל־פְּנֵֽי־הָֽאֲדָמָֽה׃"
PS_1_1_OPENING = "אַ֥שְֽׁרֵי הָאִ֗ישׁ אֲשֶׁ֤ר לֹ֥א הָלַךְ֮ בַּעֲצַ֪ת רְשָׁ֫עִ֥ים"
JOB_3_3 = "יֹ֣אבַד י֭וֹם אִוָּ֣לֶד בּ֑וֹ וְהַלַּ֥יְלָה אָ֝מַ֗ר הֹ֣רָה גָֽבֶר׃"
JOB_1_1_OPENING = "אִ֛ישׁ הָיָ֥ה בְאֶֽרֶץ־ע֖וּץ אִיּ֣וֹב שְׁמ֑וֹ"


def closers(verse: trope.Verse) -> list[str | None]:
    return [phrase.closer.key if phrase.closer else None for phrase in verse.phrases]


def sizes(verse: trope.Verse) -> list[int]:
    return [len(phrase.words) for phrase in verse.phrases]


def named(verse: trope.Verse) -> list[str | None]:
    return [word.accent.key if word.accent else None for word in verse.words]


def test_the_first_verse_is_four_phrases_in_two_halves() -> None:
    """tipcha | munach etnachta ‖ mercha tipcha | mercha silluk."""
    verse = trope.read(GEN_1_1, "Genesis 1:1")
    assert named(verse) == ["tipcha", "munach", "etnachta", "mercha", "tipcha", "mercha", "silluq"]
    assert closers(verse) == ["tipcha", "etnachta", "tipcha", "silluq"]
    assert sizes(verse) == [1, 2, 2, 2]
    # Each tipcha subdivides the half its emperor closes; the emperors are the top.
    assert [phrase.parent for phrase in verse.phrases] == [1, None, 3, None]


def test_every_accent_carries_its_name_its_kind_and_its_rank() -> None:
    assert trope.TIPCHA.label == "tipcha · disjunctive"
    assert trope.MUNACH.label == "munach · conjunctive"
    assert trope.ETNACHTA.rank is Rank.EMPEROR
    assert trope.ZAKEF_KATAN.rank is Rank.KING
    assert trope.PASHTA.rank is Rank.DUKE
    assert trope.GERESH.rank is Rank.COUNT
    assert trope.MUNACH.rank is None
    assert trope.ETNACHTA.hebrew == "אֶתְנַחְתָּא"


def test_the_table_covers_the_whole_accent_range() -> None:
    assert set(trope.ACCENTS) == set(range(0x0591, 0x05AF))
    prose = [accent for accent in trope.ACCENTS.values() if not accent.poetic]
    assert all(accent.rank is not None for accent in prose if accent.disjunctive)
    assert all(accent.rank is None for accent in prose if not accent.disjunctive)


def test_the_marks_that_sit_off_the_stress_agree_with_the_pronunciation_stage() -> None:
    """`pronounce.UNPLACED` refuses to read a stress off these; the two lists are one fact.

    Less U+0598, zarka's copy on the stressed syllable: the accent is postpositive, but
    that one mark of it sits exactly where the stress is."""
    off = {code for code, accent in trope.ACCENTS.items() if accent.place != "stress"}
    assert off - {0x0598} == set(UNPLACED)


def test_pashta_written_twice_is_one_pashta_in_either_encoding() -> None:
    """תֹ֨הוּ֙: the Leningrad encoding writes the copy on the stress as the kadma codepoint,
    Sefaria's writes pashta twice. Either way it is one pashta, and not a kadma."""
    leningrad = trope.read(GEN_1_2, "Genesis 1:2")
    sefaria = trope.read(GEN_1_2.replace("֨", "֙"), "Genesis 1:2")
    for verse in (leningrad, sefaria):
        tohu = verse.words[2]
        assert [accent.key for accent in tohu.accents] == ["pashta"]
        assert closers(verse) == [
            "revia",
            "pashta",
            "zakef-katan",
            "tipcha",
            "etnachta",
            "zakef-katan",
            "tipcha",
            "silluq",
        ]
    # Revia and pashta both subdivide the zakef katan after them.
    assert [phrase.parent for phrase in leningrad.phrases][:3] == [2, 2, 4]


def test_kadma_on_its_own_is_kadma() -> None:
    verse = trope.read(GEN_1_5, "Genesis 1:5")
    assert verse.words[0].accent is trope.KADMA
    assert verse.words[2].accent is trope.PASHTA


def test_meteg_is_not_an_accent_and_silluq_is_the_last_one_on_the_last_word() -> None:
    """וַֽיְהִי־אֽוֹר: the same codepoint twice, a meteg and then the silluk."""
    verse = trope.read(GEN_1_3, "Genesis 1:3")
    vayhi, light = verse.words[-2:]
    assert vayhi.accents == () and vayhi.accent is None and vayhi.joined
    assert light.accent is trope.SILLUQ and light.verse_end


def test_a_last_word_with_a_meteg_and_a_silluk_has_one_silluk() -> None:
    """הָֽאֲדָמָֽה, at the end of a maqaf chain whose earlier words carry metegs too."""
    verse = trope.read(GEN_2_6, "Genesis 2:6")
    assert [word.accent for word in verse.words[-4:]] == [None, None, None, trope.SILLUQ]
    assert verse.words[-1].accents == (trope.SILLUQ,)
    assert closers(verse) == ["tipcha", "etnachta", "tipcha", "silluq"]


def test_a_verse_given_without_its_stop_still_ends() -> None:
    verse = trope.read(GEN_1_1.rstrip("׃"))
    assert verse.words[-1].accent is trope.SILLUQ


def test_maqaf_makes_one_unit_and_the_last_word_carries_it() -> None:
    verse = trope.read(GEN_1_7, "Genesis 1:7")
    et, sky = verse.words[2], verse.words[3]
    assert et.joined and et.accent is None
    assert sky.accent is trope.SEGOL
    assert verse.phrase_of(2) == verse.phrase_of(3)


def test_zarka_and_segol_and_the_phrases_under_etnachta() -> None:
    verse = trope.read(GEN_1_7, "Genesis 1:7")
    assert closers(verse) == [
        "zarka",
        "segol",
        "revia",
        "pashta",
        "pashta",
        "zakef-katan",
        "zakef-katan",
        "tipcha",
        "etnachta",
        "silluq",
    ]
    parents = [phrase.parent for phrase in verse.phrases]
    # zarka under segol, segol under etnachta; revia and both pashtas under the first
    # zakef; the zakefs and tipcha under etnachta.
    assert parents == [1, 8, 5, 5, 5, 8, 8, 8, None, None]


def test_munach_before_paseq_is_legarmeh_and_other_accents_keep_their_name() -> None:
    legarmeh = trope.read(GEN_1_21, "Genesis 1:21")
    chayah = legarmeh.words[8]
    assert chayah.paseq and chayah.accent is trope.LEGARMEH
    assert chayah.accent.disjunctive and chayah.accent.rank is Rank.COUNT
    # Genesis 1:5 has a paseq after a mahpach: a pause, and still a mahpach.
    plain = trope.read(GEN_1_5, "Genesis 1:5")
    elohim = plain.words[1]
    assert elohim.paseq and elohim.accent is trope.MAHPACH


def test_the_counts_pazer_and_geresh_and_the_telishas() -> None:
    verse = trope.read(GEN_1_21, "Genesis 1:21")
    assert closers(verse) == [
        "zakef-katan",
        "tipcha",
        "etnachta",
        "munach-legarmeh",
        "pazer",
        "geresh",
        "revia",
        "pashta",
        "zakef-katan",
        "tipcha",
        "silluq",
    ]
    asher = verse.words[10]
    assert asher.accent is trope.TELISHA_KETANAH and asher.accent.place == "postpositive"
    # The three counts all subdivide the revia that follows them.
    assert [phrase.parent for phrase in verse.phrases][3:6] == [6, 6, 6]
    # A section mark after the verse is not a word.
    assert trope.read(GEN_1_5).words[-1].text == "אֶחָֽד"


def test_telisha_gedolah_is_prepositive_and_disjunctive() -> None:
    verse = trope.read(GEN_1_30, "Genesis 1:30")
    haaretz = verse.words[2]
    assert haaretz.accent is trope.TELISHA_GEDOLAH
    assert haaretz.accent.place == "prepositive" and haaretz.accent.disjunctive
    assert closers(verse)[:3] == ["telisha-gedolah", "geresh", "munach-legarmeh"]


def test_a_word_with_a_conjunctive_and_a_disjunctive_is_ruled_by_the_disjunctive() -> None:
    accents = trope.accents_of("וְהַֽמְּכַסֶּ֣ה֔")
    assert [accent.key for accent in accents] == ["munach", "zakef-katan"]
    assert trope.ruling(accents) is trope.ZAKEF_KATAN


def test_a_phrase_left_open_has_no_closer() -> None:
    verse = trope.read("בְּרֵאשִׁ֖ית בָּרָ֣א׃ וַיֹּ֥אמֶר")
    assert closers(verse) == ["tipcha", None, None]
    assert verse.phrases[1].rank is Rank.EMPEROR


@pytest.mark.parametrize("ref", ["Psalms 1:1", "Ps.1.1", "Proverbs 1:1", "Job 3:3", "Job.42.6"])
def test_the_poetic_books_are_refused_by_reference(ref: str) -> None:
    assert trope.system(ref) == "poetic"
    with pytest.raises(trope.PoeticAccents, match="poetic system"):
        trope.read(GEN_1_1, ref)


@pytest.mark.parametrize("text", [PS_1_1_OPENING, JOB_3_3])
def test_the_poetic_accents_are_refused_without_a_reference(text: str) -> None:
    with pytest.raises(trope.PoeticAccents):
        trope.read(text)


@pytest.mark.parametrize("ref", ["Job 1:1", "Job.2.13", "Job 3:1", "Job 42:7", "Job 42:17"])
def test_the_prose_frame_of_job_is_prose(ref: str) -> None:
    assert trope.system(ref) == "prose"
    verse = trope.read(JOB_1_1_OPENING, ref)
    assert closers(verse)[-1] == "etnachta"


def test_everything_else_is_prose() -> None:
    assert trope.system("Genesis 1:1") == "prose"
    assert trope.system("Gen.1.1") == "prose"
    assert trope.system("I Samuel 3:4") == "prose"
