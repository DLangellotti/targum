from __future__ import annotations

from pathlib import Path

import pytest

from targum import ingest
from targum.ingest.spacing import reglue, stranded, unglue

# The one this was written for: Ben Yehuda's own .txt of Der Judenstaat runs the
# translator's name into the heading under it.
GLUED = "מדינת היהודים מאת בנימין זאב הרצל תורגם מגרמנית מאת מיכל ברקוביץהקדמה"
CLEAN = "מדינת היהודים מאת בנימין זאב הרצל תורגם מגרמנית מאת מיכל ברקוביץ הקדמה"


def test_splits_where_a_final_letter_cannot_stand() -> None:
    assert unglue(GLUED, "he") == CLEAN


@pytest.mark.parametrize(
    ("glued", "clean"),
    [
        ("בסוףהמשחק הם עזבו", "בסוף המשחק הם עזבו"),
        ("שלוםעולם", "שלום עולם"),
        # Three run together come apart in one pass.
        ("שלוםעולםטוב", "שלום עולם טוב"),
    ],
)
def test_every_final_letter_inside_a_word_is_a_seam(glued: str, clean: str) -> None:
    assert unglue(glued, "he") == clean


@pytest.mark.parametrize(
    "text",
    [
        # A final letter where it belongs.
        "הוא הלך הביתה",
        # Maqaf joins two words and is not a missing space.
        "וַיִּקְרְאוּ בֵית־יִשְׂרָאֵל אֶת־שְׁמוֹ מָן",
        "אֶת־הַמֶּלֶךְ טוֹב",
        # Long, rare and real. The lexical rule leaves anything it cannot prove.
        "ראינו את אבדן סגולתנו הלאומיות",
        "אין אני מאמין במיקרובים",
        "לחיי התרבות משלחנות העשירים",
        # Both ותהי המלחמה and ותהיה מלחמה are readings of this. Neither is guessed at.
        "וַתְּהִיהַמִּלְחָמָה חֲזָקָה",
    ],
)
def test_leaves_alone_what_it_cannot_prove(text: str) -> None:
    assert unglue(text, "he") == text


def test_other_languages_are_untouched() -> None:
    assert unglue("the quick brown fox", "en") == "the quick brown fox"
    assert unglue(GLUED, "en") == GLUED


def test_points_stay_with_their_letter() -> None:
    # The dagesh belongs to the ם, not to the head of the next word.
    assert unglue("בְּיוֹםהַשַּׁבָּת", "he") == "בְּיוֹם הַשַּׁבָּת"


def test_repair_happens_at_ingest(tmp_path: Path) -> None:
    source = tmp_path / "herzl.txt"
    source.write_text(GLUED + "\n", encoding="utf-8")

    document = ingest.load(str(source))

    assert document.language == "he"
    # Separated, and — because this line has no punctuation in it and ends with a word a
    # Hebrew text names its parts with — the title taken off the end of the byline. See
    # `ingest.base.split_trailing_title`.
    assert " ".join(block.text for block in document.blocks) == CLEAN


@pytest.mark.parametrize(
    "text",
    [
        # Ben Yehuda's scans read ו as ן often enough that this is a class rather than a
        # case. One word with one wrong letter looks exactly like a final nun with a word
        # after it, and no guard but this one can tell them apart.
        "ויעל ידידיה עם קרואיו אל בית ה' ןיזבח זבחי תודה",
        "עיר מלאה תשואות, ןנפשו",
        # The same shape at the end of a token.
        "והנה הואם",
    ],
)
def test_a_misspelling_is_not_a_seam(text: str) -> None:
    """No Hebrew word is one letter long. A piece that short means the token was
    misspelled rather than run together, and a misspelling is not this to fix — it once
    cost a whole book's translation, because a repaired word is a word nothing has ever
    been paid to translate."""
    assert unglue(text, "he") == text


@pytest.mark.parametrize(
    ("split", "clean", "stray"),
    [
        # The cut the certain rule made before it learned that a piece one letter long
        # proves the word was misspelled rather than run together. A text built then
        # still carries the space.
        (
            "ויעל ידידיה עם קרואיו אל בית ה' ן יזבח זבחי תודה",
            "ויעל ידידיה עם קרואיו אל בית ה' ןיזבח זבחי תודה",
            "ן",
        ),
        ("עיר מלאה תשואות, ן נפשו", "עיר מלאה תשואות, ןנפשו", "ן"),
        # The same shape the other way round, from a doubled final: joined to the word
        # on its left only when nothing stands on its right.
        ("והנה הוא ם", "והנה הואם", "ם"),
        ("שלום ם עולם", "שלום םעולם", "ם"),
    ],
)
def test_a_lone_final_letter_goes_back_on_its_word(split: str, clean: str, stray: str) -> None:
    assert reglue(split, "he") == clean
    assert stranded(split) == [stray]


@pytest.mark.parametrize(
    "text",
    [
        # A final letter where it belongs.
        "הוא הלך הביתה",
        # Abbreviations end in a final letter after gershayim, and the letter after the
        # mark is a final form on its own by every other measure. These are what the
        # scan of every built text turned up, and all of them are words.
        'תנ"ך של מרים',
        'הרמב"ם אומר',
        "האו”ם באסלאמבאד",
        'בג"ץ ביטל',
        "בשנת ם׳ היה",
        # An alef-bet written out is a row of lone letters, finals among them.
        "כ ך ל מ ם נ ן",
        # The space `unglue` put in was a space, not a line.
        "ן\nנפשו",
        # Not Hebrew, and nothing to do.
        "the quick brown fox",
    ],
)
def test_a_final_letter_that_is_not_stranded_stays(text: str) -> None:
    assert reglue(text, "he") == text
    assert stranded(text) == []


def test_a_clean_text_is_clean_both_ways() -> None:
    """The scan the repair is measured by. Splitting and joining are not each other's
    inverse in general — `unglue` refuses a lone letter now — so a clean text goes
    through both and comes out as it went in."""
    assert reglue(unglue(CLEAN, "he"), "he") == CLEAN
    assert stranded(unglue("ויעל ידידיה ןיזבח זבחי תודה", "he")) == []
