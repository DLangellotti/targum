"""The agreement checks, on lines out of the hundred scenes.

Each positive case is a line a person corrected on 2026-09-22. DICTA's answers are
written out by hand in the shape its JSON takes, so the tests run without the model:
what is tested is what the checks make of a reading, not the reading.
"""

from __future__ import annotations

from typing import Any

from targum.dialogue.agreement import (
    Word,
    article_on_construct,
    check_words,
    construct_ending,
    construct_governs_nothing,
    numeral,
    numeral_agreement,
    numeral_state,
    teen,
    words_from_dicta,
)

M, F = {"Gender": "Masc"}, {"Gender": "Fem"}


def said(line: str, *words: tuple[str, str, dict[str, str], list[str], int, str]) -> list[Word]:
    """DICTA's JSON for `line`, one tuple per word: (surface, pos, feats, seg, head, rel).

    The surface is found in the line to get the offsets, as DICTA reports them.
    """
    tokens: list[dict[str, Any]] = []
    at = 0
    for surface, pos, feats, seg, head, rel in words:
        start = line.index(surface, at)
        at = start + len(surface)
        prefixes = {"ה": "DET", "ו": "CCONJ", "ש": "SCONJ"}
        tags = [prefixes.get(letter, "ADP") for letter in "".join(seg[:-1])]
        tokens.append(
            {
                "token": surface,
                "offsets": {"start": start, "end": at},
                "seg": seg,
                "morph": {"pos": pos, "feats": feats, "prefixes": tags},
                "syntax": {"dep_head_idx": head, "dep_func": rel},
            }
        )
    return words_from_dicta({"tokens": tokens}, line)


def plain(surface: str, pos: str = "NOUN", feats: dict[str, str] | None = None) -> Word:
    return Word(surface=surface, pos=pos, gender=(feats or {}).get("Gender", ""))


# ------------------------------------------------------------------------- numerals


def test_numeral_reads_eight_from_its_points() -> None:
    masculine, feminine = numeral(plain("שְׁמוֹנָה")), numeral(plain("שְׁמוֹנֶה"))
    assert masculine is not None and masculine.gender == "m"
    assert feminine is not None and feminine.gender == "f"
    assert numeral(plain("שמונה")) is None


def test_monday_is_not_a_numeral_and_two_of_is() -> None:
    assert numeral(plain("שֵׁנִי")) is None
    two = numeral(plain("שְׁנֵי"))
    assert two is not None and two.construct and two.value == 2


def test_a_sin_is_not_seven() -> None:
    assert numeral(plain("שָׂבֵעַ")) is None
    assert numeral(plain("שֶׁבַע")) is not None


def test_teen_halves_read_from_the_points() -> None:
    assert teen(plain("עָשָׂר")) == "m"
    assert teen(plain("עֶשְׂרֵה")) == "f"
    assert teen(plain("עֶשֶׂר")) == ""


def test_eight_units_counted_masculine() -> None:
    # 73-the-inheritance t14, settled as שְׁמוֹנֶה יְחִידוֹת.
    words = said(
        "וְיִבְנוּ שְׁמוֹנָה יְחִידוֹת.",
        ("וְיִבְנוּ", "VERB", {}, ["ו", "יבנו"], -1, "root"),
        ("שְׁמוֹנָה", "NUM", F, ["שמונה"], 2, "nummod"),
        ("יְחִידוֹת", "NOUN", F, ["יחידות"], 0, "obj"),
        (".", "PUNCT", {}, ["."], 0, "punct"),
    )
    found = list(numeral_agreement(words, 14))
    assert len(found) == 1 and "feminine" in found[0].what
    assert found[0].word == "שְׁמוֹנָה יְחִידוֹת"


def test_eight_units_counted_right_is_quiet() -> None:
    words = said(
        "שְׁמוֹנֶה יְחִידוֹת",
        ("שְׁמוֹנֶה", "NUM", F, ["שמונה"], 1, "nummod"),
        ("יְחִידוֹת", "NOUN", F, ["יחידות"], -1, "root"),
    )
    assert list(numeral_agreement(words, 0)) == []


def test_eight_hundred_is_feminine() -> None:
    # 38-the-estimate t6.
    words = said(
        "שְׁמוֹנָה מֵאוֹת זֶה הַרְבֵּה.",
        ("שְׁמוֹנָה", "NUM", F, ["שמונה"], 1, "nummod"),
        ("מֵאוֹת", "NUM", F, ["מאות"], -1, "root"),
        ("זֶה", "PRON", M, ["זה"], 1, "nsubj"),
        ("הַרְבֵּה", "ADV", {}, ["הרבה"], 1, "advmod"),
    )
    found = list(numeral_agreement(words, 6))
    assert len(found) == 1 and "מאות" in found[0].what


def test_a_teen_with_halves_that_disagree() -> None:
    # 79-the-double-booking t10: a feminine eight with a masculine ten.
    words = said(
        "הֵם שִׁילְּמוּ בִּשְׁמוֹנֶה עָשָׂר.",
        ("הֵם", "PRON", M, ["הם"], 1, "nsubj"),
        ("שִׁילְּמוּ", "VERB", {}, ["שילמו"], -1, "root"),
        ("בִּשְׁמוֹנֶה", "NUM", F, ["ב", "שמונה"], 1, "obl"),
        ("עָשָׂר", "NUM", M, ["עשר"], 2, "compound"),
    )
    found = list(numeral_agreement(words, 10))
    assert len(found) == 1 and "teen" in found[0].what


def test_a_time_of_day_is_not_counted() -> None:
    # Seven in the morning: the noun after the numeral wears a preposition.
    words = said(
        "מִשֶּׁבַע בַּבּוֹקֶר",
        ("מִשֶּׁבַע", "NUM", F, ["מ", "שבע"], -1, "root"),
        ("בַּבּוֹקֶר", "NOUN", M, ["ב", "בוקר"], 0, "nmod"),
    )
    assert list(numeral_agreement(words, 0)) == []
    assert list(numeral_state(words, 0)) == []


def test_one_agrees_with_the_noun_before_it() -> None:
    wrong = [plain("כּוֹכָב", "NOUN", M), plain("אַחַת", "NUM")]
    right = [plain("כּוֹכָב", "NOUN", M), plain("אֶחָד", "NUM")]
    assert len(list(numeral_agreement(wrong, 0))) == 1
    assert list(numeral_agreement(right, 0)) == []


def test_three_before_a_definite_noun_is_the_construct() -> None:
    # 58-second-opinion t17, settled as וּבִשְׁלוֹשֶׁת הַחוֹדָשִׁים.
    words = said(
        "וּבִשְׁלוֹשָׁה הֶחוֹדָשִׁים הָאֵלֶּה",
        ("וּבִשְׁלוֹשָׁה", "NUM", M, ["וב", "שלושה"], 1, "nummod"),
        ("הֶחוֹדָשִׁים", "NOUN", M, ["ה", "חודשים"], -1, "root"),
        ("הָאֵלֶּה", "DET", {}, ["ה", "אלה"], 1, "det"),
    )
    found = list(numeral_state(words, 17))
    assert len(found) == 1 and "construct" in found[0].what
    assert list(numeral_agreement(words, 17)) == []


def test_three_before_an_indefinite_noun_stays_absolute() -> None:
    words = said(
        "שְׁלוֹשָׁה חוֹדָשִׁים",
        ("שְׁלוֹשָׁה", "NUM", M, ["שלושה"], 1, "nummod"),
        ("חוֹדָשִׁים", "NOUN", M, ["חודשים"], -1, "root"),
    )
    assert list(numeral_state(words, 0)) == []


def test_two_of_with_nothing_after_it() -> None:
    # 09-the-office t16: Monday is שֵׁנִי.
    words = said(
        "בְּיוֹם שְׁנֵי.",
        ("בְּיוֹם", "NOUN", M, ["ב", "יום"], -1, "root"),
        ("שְׁנֵי", "NUM", M, ["שני"], 0, "compound:smixut"),
        (".", "PUNCT", {}, ["."], 0, "punct"),
    )
    found = list(numeral_state(words, 16))
    assert len(found) == 1 and "nothing after it" in found[0].what


def test_two_before_a_noun_is_the_construct() -> None:
    words = said(
        "שְׁתַּיִם כּוֹסוֹת",
        ("שְׁתַּיִם", "NUM", F, ["שתיים"], 1, "nummod"),
        ("כּוֹסוֹת", "NOUN", F, ["כוסות"], -1, "root"),
    )
    assert len(list(numeral_state(words, 0))) == 1


# ------------------------------------------------------------------------ smichut


def test_the_article_on_the_head_of_a_chain() -> None:
    # 65-the-leak t19: לָרוֹב הַדִּירוֹת, settled as לְרוֹב.
    words = said(
        "לָרוֹב הַדִּירוֹת",
        ("לָרוֹב", "DET", M, ["ל", "רוב"], 1, "det"),
        ("הַדִּירוֹת", "NOUN", F, ["ה", "דירות"], 0, "compound:smixut"),
    )
    found = list(article_on_construct(words, 19))
    assert len(found) == 1 and "head of a construct chain" in found[0].what


def test_a_chain_with_the_article_at_the_end_is_quiet() -> None:
    words = said(
        "בְּבֵית הַסֵּפֶר",
        ("בְּבֵית", "NOUN", M, ["ב", "בית"], -1, "root"),
        ("הַסֵּפֶר", "NOUN", M, ["ה", "ספר"], 0, "compound:smixut"),
    )
    assert list(article_on_construct(words, 0)) == []


def test_a_patah_before_a_hataf_is_not_the_article() -> None:
    words = said(
        "לַחֲנוּת סְפָרִים",
        ("לַחֲנוּת", "NOUN", F, ["ל", "חנות"], -1, "root"),
        ("סְפָרִים", "NOUN", M, ["ספרים"], 0, "compound:smixut"),
    )
    assert list(article_on_construct(words, 0)) == []


def test_construct_endings_read_from_the_points() -> None:
    assert construct_ending(plain("הַפְרָעַת")) == "f"
    assert construct_ending(plain("חוּקֵּי")) == "pl"
    assert construct_ending(plain("הִפְרַעְתְּ")) == ""
    assert construct_ending(plain("חוּקִּי")) == ""
    # Absolute nouns in -ַחַת and -ַעַת are patah then patah, not qamats then patah.
    assert construct_ending(plain("צַלַּחַת")) == ""
    assert construct_ending(plain("דַּעַת")) == ""


def test_a_construct_noun_with_nothing_to_govern() -> None:
    # 41-the-neighbour-upstairs t1: the verb הִפְרַעְתְּ, pointed as 'the disturbance of'.
    words = said(
        "לֹא הַפְרָעַת. גַּם אֲנִי עֵר.",
        ("לֹא", "ADV", {}, ["לא"], 1, "advmod"),
        ("הַפְרָעַת", "VERB", {}, ["הפרעת"], -1, "root"),
        (".", "PUNCT", {}, ["."], 1, "punct"),
        ("גַּם", "ADV", {}, ["גם"], 5, "advmod"),
        ("אֲנִי", "PRON", {}, ["אני"], 5, "nsubj"),
        ("עֵר", "ADJ", M, ["ער"], -1, "root"),
    )
    found = list(construct_governs_nothing(words, 1))
    assert [f.word for f in found] == ["הַפְרָעַת"]


def test_a_construct_noun_with_its_noun_is_quiet() -> None:
    words = said(
        "הַפְרָעַת שֵׁינָה",
        ("הַפְרָעַת", "NOUN", F, ["הפרעת"], -1, "root"),
        ("שֵׁינָה", "NOUN", F, ["שינה"], 0, "compound:smixut"),
    )
    assert list(construct_governs_nothing(words, 0)) == []


def test_check_words_runs_only_the_gated_checks(monkeypatch: Any) -> None:
    from targum.dialogue import agreement

    words = said(
        "בְּיוֹם שְׁנֵי.",
        ("בְּיוֹם", "NOUN", M, ["ב", "יום"], -1, "root"),
        ("שְׁנֵי", "NUM", M, ["שני"], 0, "compound:smixut"),
        (".", "PUNCT", {}, ["."], 0, "punct"),
    )
    monkeypatch.setattr(agreement, "GATED", ())
    assert check_words(words, 0) == []
    monkeypatch.setattr(agreement, "GATED", ("numeral_state",))
    assert len(check_words(words, 0)) == 1


def test_a_preposition_that_was_once_a_construct_is_quiet() -> None:
    # לִפְנֵי, אַחֲרֵי, כְּדֵי and לְגַמְרֵי end like construct nouns and stand alone as a
    # matter of course: thirty-one false positives before the check read DICTA's tag.
    words = said(
        "יוֹמַיִים לִפְנֵי.",
        ("יוֹמַיִים", "NOUN", M, ["יומיים"], -1, "root"),
        ("לִפְנֵי", "ADP", {}, ["לפני"], 0, "case"),
        (".", "PUNCT", {}, ["."], 0, "punct"),
    )
    assert list(construct_governs_nothing(words, 0)) == []


def test_a_verb_pointed_with_a_construct_ending() -> None:
    # 93-the-thesis t32: the 2fs future ends -ִי, and -ֵי is the construct plural.
    words = said(
        "תִּכְתְּבֵי עַכְשָׁיו",
        ("תִּכְתְּבֵי", "VERB", {}, ["תכתבי"], -1, "root"),
        ("עַכְשָׁיו", "ADV", {}, ["עכשיו"], 0, "advmod"),
    )
    found = list(construct_governs_nothing(words, 32))
    assert len(found) == 1 and "verb" in found[0].what


def test_one_after_a_noun_with_a_preposition_is_not_counting_it() -> None:
    # 90-the-newsroom t16: two on the committee and one speaks.
    words = said(
        "שְׁנַיִים בַּוַּועֲדָה וְאֶחָד מְדַבֵּר",
        ("שְׁנַיִים", "NUM", M, ["שניים"], 3, "nsubj"),
        ("בַּוַּועֲדָה", "NOUN", F, ["ב", "וועדה"], 0, "nmod"),
        ("וְאֶחָד", "NUM", M, ["ו", "אחד"], 0, "conj"),
        ("מְדַבֵּר", "VERB", {}, ["מדבר"], -1, "root"),
    )
    assert list(numeral_agreement(words, 16)) == []


def test_the_article_on_a_day_in_a_chain() -> None:
    # 54-the-refund t10: nobody marked it, and it is wrong — בְּיוֹם הַבִּיטּוּל.
    words = said(
        "גַּם בַּיּוֹם הַבִּיטּוּל.",
        ("גַּם", "ADV", {}, ["גם"], 1, "advmod"),
        ("בַּיּוֹם", "NOUN", M, ["ב", "יום"], -1, "root"),
        ("הַבִּיטּוּל", "NOUN", M, ["ה", "ביטול"], 1, "compound:smixut"),
        (".", "PUNCT", {}, ["."], 1, "punct"),
    )
    assert len(list(article_on_construct(words, 10))) == 1


def test_a_page_number_is_not_a_chain() -> None:
    # 96-the-translation t21: page two hundred is a label, whatever DICTA calls it.
    words = said(
        "בָּעַמּוּד מָאתַיִים",
        ("בָּעַמּוּד", "NOUN", M, ["ב", "עמוד"], -1, "root"),
        ("מָאתַיִים", "NUM", {}, ["מאתיים"], 0, "compound:smixut"),
    )
    assert list(article_on_construct(words, 0)) == []


def test_a_word_split_at_a_geresh_is_not_a_chain() -> None:
    # 81-the-army-friend t2: DICTA reads הַגּ׳יפּ as three words.
    words = said(
        "עִם הַגּ׳יפּ.",
        ("עִם", "ADP", {}, ["עם"], 1, "case"),
        ("הַגּ", "NOUN", {}, ["ה", "ג"], -1, "root"),
        ("׳", "NOUN", {}, ["׳"], 1, "compound:smixut"),
        ("יפּ", "NOUN", {}, ["יפ"], 1, "nmod"),
        (".", "PUNCT", {}, ["."], 1, "punct"),
    )
    assert list(article_on_construct(words, 0)) == []
