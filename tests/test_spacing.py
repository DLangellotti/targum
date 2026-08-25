from __future__ import annotations

from pathlib import Path

import pytest

from targum import ingest
from targum.ingest.spacing import unglue

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
