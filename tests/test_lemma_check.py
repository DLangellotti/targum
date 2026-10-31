"""A lemma the word does not spell, put right at page-build and count time
(`annotate.lemma_check`; David, 2026-10-31: נשתיק on התקין's card).

Single words only, never a sentence of any text.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from targum.annotate.lemma_check import Mend, checked, mend_row, mended, refused
from targum.models import Annotation, BlockKind, Segment, SegmentedDocument, Syntax, Token
from targum.occurrences import count_text

DICTA = "dicta/dicta-il/dictabert-joint/roots+everyword+entities+syntax+grammar/8"


def test_a_lemma_the_word_does_not_spell_takes_the_table_verb() -> None:
    # התקין's ת־ק־ן with its nun let go is ת־ק, which נשתיק spells; the nun is the
    # root's last letter and no ת follows it, so it stays a letter to spell.
    assert refused("התקין", "נשתיק")
    assert checked("התקין", "נשתיק", 0, "VERB") == Mend("השתיק", "שתק", "הפעיל")


def test_a_pointed_word_is_checked_on_its_letters() -> None:
    assert checked("התקין", "נַשְׁתִּיק", 0, "VERB") == Mend("השתיק", "שתק", "הפעיל")


def test_prefixes_are_cut_before_the_table_is_asked() -> None:
    # והלכו under הלכנו: the ו is the conjunction (lead 1), and הלכו is הלך's.
    found = checked("הלכנו", "והלכו", 1, "VERB")
    assert found is not None and found.lemma == "הלך"


@pytest.mark.parametrize(
    ("lemma", "word"),
    [
        ("נתן", "נתתי"),  # a last nun taken into the suffix's ת
        ("נתן", "תן"),  # a first nun that assimilated
        ("נפל", "יפול"),
        ("לקח", "קח"),  # suppletive
        ("התקין", "התקנו"),  # the root's nun written once before נו
        ("התקין", "נתקין"),  # the right verb
        ("השתיק", "נשתיק"),
        ("משתיק", "השתקתי"),  # a participle's מ left on the lemma
        ("שמר", "שומרים"),
    ],
)
def test_a_lemma_the_word_spells_stands(lemma: str, word: str) -> None:
    assert not refused(lemma, word)
    assert checked(lemma, word, 0, "VERB") is None


def test_with_no_one_verb_in_the_table_the_card_gets_a_gap() -> None:
    # נפדה under נקנה: wrong, and the table holds more than one verb for נפדה.
    assert checked("נקנה", "נפדה", 0, "VERB") == Mend("נפדה", "", "")
    # A noun is never given a verb; a wrong one becomes the word itself.
    assert checked("שמן", "שמו", 0, "NOUN") == Mend("שמו", "", "")


def test_a_gap_stays_a_gap_and_other_words_are_not_checked() -> None:
    assert checked("נשתיק", "נשתיק", 0, "VERB") is None
    assert checked("התקין", "נשתיק", 0, "ADV") is None
    assert checked("התקין", "נשתיק", 0, None) is None


def _annotation(annotator: str, token: Token) -> Annotation:
    return Annotation(
        document_hash="h",
        language="he",
        annotator=annotator,
        method="frequency",
        method_note="",
        tokens={"s1": [token]},
    )


def _word(lemma: str) -> Token:
    return Token(
        start=0,
        end=5,
        surface="נשתיק",
        lemma=lemma,
        band=3,
        pos="VERB",
        root="תקן",
        binyan="הפעיל",
        headword="הִתְקִין",
        syntax=Syntax(head=-1, relation="root"),
    )


def test_a_dicta_annotation_is_mended_and_its_root_follows() -> None:
    fixed = mended(_annotation(DICTA, _word("התקין"))).tokens["s1"][0]
    assert (fixed.lemma, fixed.root, fixed.binyan) == ("השתיק", "שתק", "הפעיל")
    assert fixed.headword is None
    assert fixed.band == 3


def test_an_annotation_with_nothing_to_mend_is_the_same_object() -> None:
    right = _annotation(DICTA, _word("השתיק"))
    assert mended(right) is right


def test_scripture_tagging_is_never_overruled() -> None:
    tagged = _annotation("oshb/8+" + DICTA, _word("התקין"))
    assert mended(tagged) is tagged


def test_a_stored_row_is_mended_for_the_counts() -> None:
    row = {"surface": "נשתיק", "lemma": "התקין", "pos": "VERB", "root": "תקן"}
    assert mend_row(row)["lemma"] == "השתיק"
    assert mend_row(row)["root"] == "שתק"
    kept = {"surface": "נשתיק", "lemma": "השתיק", "pos": "VERB"}
    assert mend_row(kept) is kept


def test_the_count_files_the_word_under_the_lemma_the_page_shows(tmp_path: Path) -> None:
    folder = tmp_path / "text"
    folder.mkdir()
    segment = Segment(
        id="s1", block_id="b1", block_index=0, index=0, kind=BlockKind.paragraph, text="נשתיק"
    )
    document = SegmentedDocument(
        document_hash="h", language="he", segmenter="test", segments=[segment]
    )
    (folder / "segments.json").write_text(document.model_dump_json(), encoding="utf-8")
    row = {"start": 0, "end": 5, "surface": "נשתיק", "lemma": "התקין", "pos": "VERB"}
    (folder / "annotation.json").write_text(
        json.dumps({"annotator": DICTA, "language": "he", "tokens": {"s1": [row]}}),
        encoding="utf-8",
    )
    counted = count_text(folder)
    assert counted is not None
    assert counted.count("השתיק") == 1
    assert counted.count("התקין") == 0
