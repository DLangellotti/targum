"""The free checks, and the lines they were written from.

Every case here is a real line out of the hundred scenes, with the judgement a person
settled on it on 2026-09-22 — not an invented example. A checker tested on Hebrew
somebody made up to suit it is a checker that passes and finds nothing.

The negatives matter more than the positives. Two hand-rolled checks were deleted
earlier for firing on ordinary Hebrew, so the words they wrongly flagged are pinned
here: if a future rule calls איך feminine again, this fails.
"""

from __future__ import annotations

from targum.dialogue.checks import (
    addressed_gender,
    bare,
    cast_disagrees,
    cast_voices_disagree,
    hataf_on_non_guttural,
    impossible_dagesh,
    inconsistent_pointing,
    pronunciation_hints,
    scales_disagree,
    units,
    voice_gender,
)


def test_bare_strips_points_but_keeps_letters() -> None:
    assert bare("שֶׁהִשְׂכַּרְתִּי") == "שהשכרתי"
    assert bare("") == ""


def test_units_pairs_each_letter_with_its_marks() -> None:
    assert units("אַתְּ") == [("א", "ַ"), ("ת", "ְּ")]


def test_impossible_dagesh_finds_a_dagesh_in_an_alef() -> None:
    found = list(impossible_dagesh("הּוּא בָּא", 0))
    assert [f.word for f in found] == ["הּוּא"]
    assert "not word-final" in found[0].what


def test_a_mappiq_is_not_an_error() -> None:
    # מְקוֹמָהּ was wrong for another reason entirely, but its mappiq was correct, and
    # 48 findings were once waved away on the strength of that. The mappiq is fine.
    assert list(impossible_dagesh("אֲנִי רוֹאֶה אוֹתָהּ", 0)) == []
    assert list(impossible_dagesh("מְקוֹמָהּ", 0)) == []


def test_hataf_under_a_guttural_is_ordinary() -> None:
    assert list(hataf_on_non_guttural("אֲנִי חֲצִי שָׁעָה", 0)) == []


def test_hataf_under_a_non_guttural_is_not() -> None:
    found = list(hataf_on_non_guttural("שְׁלֲוֹם", 0))
    assert len(found) == 1 and "not a guttural" in found[0].what


def test_addressed_gender_reads_the_tav_ending() -> None:
    assert addressed_gender("עָזַבְתָּ") == "m"
    assert addressed_gender("עָזַבְתְּ") == "f"
    assert addressed_gender("אַתָּה") == "m"
    assert addressed_gender("אַתְּ") == "f"


def test_addressed_gender_reads_the_kaf_suffix_only_where_it_is_one() -> None:
    assert addressed_gender("אֵלֶיךָ") == "m"
    assert addressed_gender("אֵלֶיךְ") == "f"
    assert addressed_gender("שֶׁלְּךָ") == "m"


def test_ordinary_words_ending_in_kaf_are_not_feminine() -> None:
    """The sixty false positives that killed the first version of this check.

    Every one of these ends in ךְ and none of them is spoken to anybody. A rule that
    reads a final kaf as the 'you' suffix calls all of them feminine.
    """
    for word in ("אֵיךְ", "צָרִיךְ", "בְּעֵרֶךְ", "הוֹלֵךְ", "אָרוֹךְ", "לְתוֹךְ", "בַּדֶּרֶךְ"):
        assert addressed_gender(word) == "", word


def test_cast_disagrees_finds_the_form_spoken_to_the_wrong_person() -> None:
    # 42-the-interview t2, addressed to Maya: the masculine past where the feminine
    # was meant. One of the twenty-five the audit found and a person confirmed.
    found = list(cast_disagrees("לָמָּה עָזַבְתָּ?", 2, "f"))
    assert [f.word for f in found] == ["עָזַבְתָּ"]
    assert found[0].kind == "gender"


def test_cast_agreeing_says_nothing() -> None:
    assert list(cast_disagrees("לָמָּה עָזַבְתְּ?", 2, "f")) == []
    assert list(cast_disagrees("לָמָּה עָזַבְתָּ?", 2, "m")) == []


def test_an_unknown_addressee_turns_the_check_off() -> None:
    assert list(cast_disagrees("לָמָּה עָזַבְתָּ?", 2, "")) == []


def test_scales_disagree_catches_a_hundred_against_a_thousand() -> None:
    # 92-the-consent-form t17. The line's own arithmetic — half a per cent, one in five
    # of those — settles it at a thousand, and the Hebrew said a hundred.
    found = list(scales_disagree("כְּלוֹמַר אֶחָד לְמֵאָה.", "So one in a thousand.", 17))
    assert len(found) == 1 and found[0].kind == "mismatch"


def test_fifteen_hundred_is_not_a_contradiction() -> None:
    """English counts hundreds past a thousand and Hebrew does not.

    71-the-raise t15: 'fifteen hundred' beside אלף וחצי. Both say 1,500.
    """
    line = "אֲנִי יָכוֹל לָתֵת אֶלֶף וַחֵצִי הַיּוֹם."
    assert list(scales_disagree(line, "I can give fifteen hundred today.", 15)) == []


def test_scales_agreeing_says_nothing() -> None:
    assert list(scales_disagree("מֵאָה שֶׁקֶל", "A hundred shekels", 0)) == []
    assert list(scales_disagree("שָׁלוֹם", "Hello", 0)) == []


def test_inconsistent_pointing_reports_a_word_pointed_two_ways() -> None:
    # Really in the corpus: אֶלֶף (a thousand) and אָלֶף (the letter's name), and in
    # 71-the-raise both stand in the same line.
    rows = inconsistent_pointing({"a": ["אֶלֶף שֶׁקֶל"], "b": ["אָלֶף שֶׁקֶל"]})
    assert len(rows) == 1 and rows[0].startswith("אלף:")


def test_inconsistent_pointing_ignores_a_word_pointed_one_way() -> None:
    assert inconsistent_pointing({"a": ["אֶלֶף שֶׁקֶל"], "b": ["אֶלֶף שֶׁקֶל"]}) == []


def test_unpointed_words_are_not_compared() -> None:
    """A scene may carry an unpointed word; it is not a second spelling of a pointed one."""
    assert inconsistent_pointing({"a": ["אלף"], "b": ["אֶלֶף"]}) == []


def test_a_man_read_by_a_man_and_a_woman_by_a_woman() -> None:
    # 48-the-cleaning, as it stands: Orit is Achernar and Dor is Orus.
    cast = {
        "A": {"voice": "Achernar", "gender": "f", "name": "אורית"},
        "B": {"voice": "Orus", "gender": "m", "name": "דור"},
    }
    assert cast_voices_disagree(cast) == []


def test_two_men_may_share_two_mens_voices() -> None:
    """Six of the hundred scenes have two men in them, and are voiced by two men."""
    cast = {"A": {"voice": "Charon", "gender": "m"}, "B": {"voice": "Orus", "gender": "m"}}
    assert cast_voices_disagree(cast) == []


def test_a_man_read_by_a_womans_voice_is_caught() -> None:
    cast = {
        "A": {"voice": "Leda", "gender": "m", "name": "דור"},
        "B": {"voice": "Kore", "gender": "f"},
    }
    found = cast_voices_disagree(cast)
    assert len(found) == 1 and "Leda" in found[0] and "declared m" in found[0]


def test_a_voice_the_table_does_not_know_is_reported_not_assumed() -> None:
    """Adding a voice without adding it here has to fail, not pass quietly."""
    cast = {"A": {"voice": "Betelgeuse", "gender": "f"}, "B": {"voice": "Puck", "gender": "m"}}
    found = cast_voices_disagree(cast)
    assert len(found) == 1 and "not in the table" in found[0]


def test_voice_gender_knows_the_voices_the_scenes_use() -> None:
    for voice in ("Achernar", "Leda", "Kore", "Callirrhoe", "Sulafat", "Aoede"):
        assert voice_gender(voice) == "f", voice
    for voice in ("Charon", "Orus", "Puck", "Enceladus"):
        assert voice_gender(voice) == "m", voice


def test_a_hint_is_given_where_the_letters_do_not_decide() -> None:
    """`עזבת` is azavta or azavt and the letters are the same either way."""
    assert pronunciation_hints("לָמָּה עָזַבְתְּ?", "f") == ['עזבת: ends "-t", the feminine']
    assert pronunciation_hints("לָמָּה עָזַבְתָּ?", "m") == ['עזבת: ends "-ta", the masculine']


def test_no_hint_where_the_letters_already_decide() -> None:
    """אתה is never את, so the engine cannot get it wrong and is not told about it."""
    assert pronunciation_hints("אַתָּה בָּא?", "m") == []
    assert pronunciation_hints("שָׁלוֹם, מָה נִשְׁמָע?", "f") == []


def test_at_is_hinted_because_it_is_also_et() -> None:
    """The one two-letter word that is both a pronoun and the object marker."""
    assert pronunciation_hints("וְאַתְּ?", "f") == [
        'ואת: "at", the word for "you" to a woman — not "et", the object marker'
    ]


def test_a_hint_says_what_is_written_even_against_the_cast() -> None:
    """The engine reads the page. A hint that contradicts the page is a hint that
    makes it say a word which is not there."""
    said = pronunciation_hints("לָמָּה עָזַבְתְּ?", "m")
    assert said and 'ends "-t", the feminine' in said[0]
    assert "though the cast says otherwise" in said[0]


def test_each_word_is_hinted_once() -> None:
    twice = pronunciation_hints("אָמַרְתָּ וְאָמַרְתָּ שׁוּב", "m")
    assert twice == ['אמרת, ואמרת: ends "-ta", the masculine']


def test_the_impersonal_you_is_not_a_disagreement() -> None:
    """78-the-driving-test t23: "as an instructor you hope" — masculine, to a woman.

    Hebrew's generic "you" takes the masculine and is not an error. This was the only
    false positive the check had over the hundred scenes, and the corpus gate keeps
    the same exception, reached independently, with the same single entry.
    """
    line = "כִּי בְּתוֹר מוֹרֶה אַתָּה מְקַוֶּוה, וּבְתוֹר בּוֹחֵן אַתָּה רַק רוֹאֶה."
    assert list(cast_disagrees(line, 23, "f", "78-the-driving-test")) == []
    # The same line anywhere else is still a finding.
    assert list(cast_disagrees(line, 23, "f", "99-somewhere-else")) != []
