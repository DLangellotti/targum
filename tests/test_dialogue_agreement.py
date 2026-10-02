"""The agreement checks, on lines out of the hundred scenes.

Each positive case is a line a person corrected on 2026-09-22. DICTA's answers are
written out by hand in the shape its JSON takes, so the tests run without the model:
what is tested is what the checks make of a reading, not the reading.
"""

from __future__ import annotations

from typing import Any

import pytest

from targum.annotate.dicta import _moved, _tokens
from targum.dialogue import agreement
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
    words_from_annotation,
    words_from_dicta,
    words_from_tokens,
)
from targum.models import Annotation, Segment, Syntax, Token

M, F = {"Gender": "Masc"}, {"Gender": "Fem"}


Said = tuple[str, str, dict[str, str], list[str], int, str]


def said(line: str, *words: Said) -> list[Word]:
    """DICTA's reading of `line` as the checks see it, made by `reply`."""
    return words_from_dicta(reply(line, *words), line)


def reply(line: str, *words: Said) -> dict[str, Any]:
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
    return {"tokens": tokens}


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


# ------------------------------------------------- the stored annotation (targum-internal#134)

#: The two errors the gate found on the shelf, as DICTA reads them, and the same two
#: lines corrected.
REFUND: tuple[str, tuple[Said, ...]] = (
    "אֲבָל הָיִיתִי חוֹלָה גַּם בַּיּוֹם הַבִּיטּוּל.",
    (
        ("אֲבָל", "CCONJ", {}, ["אבל"], 2, "cc"),
        ("הָיִיתִי", "AUX", M, ["הייתי"], 2, "cop"),
        ("חוֹלָה", "VERB", M, ["חולה"], -1, "root"),
        ("גַּם", "ADV", {}, ["גם"], 4, "advmod"),
        ("בַּיּוֹם", "NOUN", M, ["ב", "יום"], 2, "obl"),
        ("הַבִּיטּוּל", "NOUN", M, ["ה", "ביטול"], 4, "compound:smixut"),
        (".", "PUNCT", {}, ["."], 2, "punct"),
    ),
)
LAWYER: tuple[str, tuple[Said, ...]] = (
    "מִכְתָּב אֶחָד, שְׁמוֹנָה מֵאוֹת.",
    (
        ("מִכְתָּב", "NOUN", M, ["מכתב"], -1, "root"),
        ("אֶחָד", "NUM", M, ["אחד"], 0, "nummod"),
        (",", "PUNCT", {}, [","], 4, "punct"),
        ("שְׁמוֹנָה", "NUM", F, ["שמונה"], 4, "nummod"),
        ("מֵאוֹת", "NUM", F, ["מאות"], 0, "appos"),
        (".", "PUNCT", {}, ["."], 0, "punct"),
    ),
)


def _fixed(
    case: tuple[str, tuple[Said, ...]], wrong: str, right: str
) -> tuple[str, tuple[Said, ...]]:
    line, words = case
    return line.replace(wrong, right), tuple(
        (w[0].replace(wrong, right), *w[1:])
        for w in words  # type: ignore[misc]
    )


def stored(line: str, *words: Said) -> list[Token]:
    """What the annotator keeps of DICTA's reply, which is what the shelf holds."""
    return _tokens(reply(line, *words))


def test_the_annotator_keeps_which_word_governs_which() -> None:
    tokens = stored(*REFUND[0:1], *REFUND[1])
    by = {token.surface: token for token in tokens}
    # Punctuation is no token, so the heads are counted without it.
    assert by["הַבִּיטּוּל"].syntax == Syntax(
        head=4, relation="compound:smixut", prefixes=("DET",), lead=1
    )
    assert by["בַּיּוֹם"].syntax is not None and by["בַּיּוֹם"].syntax.prefixes == ("ADP",)
    # The head of the chain says so where the card reads it.
    assert by["בַּיּוֹם"].feats is not None and "Definite=Cons" in by["בַּיּוֹם"].feats
    assert "Definite" not in (by["הַבִּיטּוּל"].feats or "")
    assert by["חוֹלָה"].syntax is not None and by["חוֹלָה"].syntax.head == -1


def test_a_number_hanging_off_a_noun_does_not_make_it_a_construct() -> None:
    tokens = stored(
        "בָּעַמּוּד מָאתַיִים",
        ("בָּעַמּוּד", "NOUN", M, ["ב", "עמוד"], -1, "root"),
        ("מָאתַיִים", "NUM", {}, ["מאתיים"], 0, "compound:smixut"),
    )
    assert "Definite" not in (tokens[0].feats or "")


@pytest.mark.parametrize("case", [REFUND, LAWYER])
def test_the_stored_reading_finds_what_dicta_finds(case: tuple[str, tuple[Said, ...]]) -> None:
    line, words = case
    from_dicta = check_words(said(line, *words), 3)
    from_store = words_from_tokens(stored(line, *words), line)
    assert from_store is not None
    assert from_dicta and check_words(from_store, 3) == from_dicta


@pytest.mark.parametrize(
    "case",
    [_fixed(REFUND, "בַּיּוֹם", "בְּיוֹם"), _fixed(LAWYER, "שְׁמוֹנָה", "שְׁמוֹנֶה")],
)
def test_the_two_lines_corrected_are_quiet(case: tuple[str, tuple[Said, ...]]) -> None:
    line, words = case
    from_store = words_from_tokens(stored(line, *words), line)
    assert from_store is not None and check_words(from_store, 3) == []
    assert check_words(said(line, *words), 3) == []


def test_punctuation_comes_back_between_the_stored_words() -> None:
    # `בְּיוֹם שְׁנֵי.` is 'two of' and then a full stop: the stop has to be there.
    line = "בְּיוֹם שְׁנֵי."
    words = (
        ("בְּיוֹם", "NOUN", M, ["ב", "יום"], -1, "root"),
        ("שְׁנֵי", "NUM", M, ["שני"], 0, "nummod"),
        (".", "PUNCT", {}, ["."], 0, "punct"),
    )
    from_store = words_from_tokens(stored(line, *words), line)
    assert from_store is not None
    assert [w.pos for w in from_store] == ["NOUN", "NUM", "PUNCT"]
    assert from_store[1].head == 0
    assert check_words(from_store, 0) == check_words(said(line, *words), 0) != []


def test_an_annotation_from_before_the_rename_has_no_reading() -> None:
    old = [t.model_copy(update={"syntax": None}) for t in stored(LAWYER[0], *LAWYER[1])]
    assert words_from_tokens(old, LAWYER[0]) is None


def _scene(line: str, tokens: list[Token], second: str = "") -> tuple[list[Segment], Annotation]:
    segments = [Segment(id="s0", block_id="b0000", block_index=0, index=0, text=line)]
    held = {"s0": tokens}
    if second:
        segments.append(Segment(id="s1", block_id="b0000", block_index=0, index=1, text=second))
        held["s1"] = stored(LAWYER[0], *LAWYER[1])
    annotation = Annotation(
        document_hash="x", language="he", annotator="dicta", method="m", method_note=""
    )
    annotation.tokens = held
    return segments, annotation


def test_a_turn_of_two_sentences_is_one_list_with_its_heads_moved() -> None:
    first = "גַּם בַּיּוֹם הַבִּיטּוּל."
    tokens = stored(
        first,
        ("גַּם", "ADV", {}, ["גם"], 1, "advmod"),
        ("בַּיּוֹם", "NOUN", M, ["ב", "יום"], -1, "root"),
        ("הַבִּיטּוּל", "NOUN", M, ["ה", "ביטול"], 1, "compound:smixut"),
        (".", "PUNCT", {}, ["."], 1, "punct"),
    )
    segments, annotation = _scene(first, tokens, second=LAWYER[0])
    turns = words_from_annotation(segments, annotation)
    assert turns is not None and list(turns) == [0]
    words = turns[0]
    # Four words and a stop, then the second sentence: its root's dependents point past them.
    assert words[4].surface == "מִכְתָּב" and words[5].head == 4
    assert len(check_words(words, 0)) == 2


def test_turn_words_reads_the_store_and_falls_back_to_dicta(monkeypatch: Any) -> None:
    line = LAWYER[0]
    tokens = stored(line, *LAWYER[1])
    segments, annotation = _scene(line, tokens)
    asked: list[list[str]] = []

    def local(texts: list[str], dicta: Any = None) -> list[list[Word]]:
        asked.append(list(texts))
        return [said(line, *LAWYER[1])]

    monkeypatch.setattr(agreement, "words_by_dicta", local)
    assert check_words(agreement.turn_words([line], segments, annotation)[0], 0)
    assert asked == []
    # An annotation from before the rename: read again.
    annotation.tokens = {"s0": [t.model_copy(update={"syntax": None}) for t in tokens]}
    agreement.turn_words([line], segments, annotation)
    assert asked == [[line]]
    # A scene edited since it was annotated: its stored words are not its words.
    annotation.tokens = {"s0": tokens}
    agreement.turn_words(["מִכְתָּב אֶחָד, שְׁמוֹנֶה מֵאוֹת וְעוֹד."], segments, annotation)
    assert len(asked) == 2


def test_a_later_piece_keeps_its_heads_pointing_at_its_own_words() -> None:
    tokens = stored(LAWYER[0], *LAWYER[1])
    moved = _moved(tokens[1], 100, 7)
    assert moved.start == tokens[1].start + 100
    assert moved.syntax is not None and moved.syntax.head == 7
    root = _moved(tokens[0], 100, 7)
    assert root.syntax is not None and root.syntax.head == -1
