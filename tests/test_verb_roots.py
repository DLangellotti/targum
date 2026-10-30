"""A verb's root as the page draws it and the tables count it (sublexical slice 1): the
annotation's, less the ones known wrong, filled from the CC0 table where it had none.

Single words only, never a sentence of any text.
"""

from __future__ import annotations

from collections import Counter

import pytest

from targum.annotate import verb_roots
from targum.annotate.paradigms import family_of
from targum.annotate.verb_roots import WRONG, denied, filled, root_for
from targum.tables import roots as roots_table


@pytest.mark.parametrize(
    ("lemma", "root"),
    [
        ("הקל", "הקל"),  # ק־ל־ל: a hif'il read as a qal, its "root" the lemma itself
        ("הכה", "הכה"),  # נ־כ־ה
        ("נזיר", "זיר"),  # נ־ז־ר: an adjective's own נ taken for nif'al's
        ("הטיל", "נטל"),  # ט־ו־ל
        ("מימש", "מממש"),
    ],
)
def test_a_known_wrong_root_is_not_drawn(lemma: str, root: str) -> None:
    assert denied(lemma, root)
    assert root_for(lemma, root, "VERB") == ""


def test_the_deny_is_for_that_lemma_only() -> None:
    # The root itself is not banned: כ־ת־ב is right for כתב, and ק־ל־ל for הקל would be.
    assert root_for("כתב", "כתב", "VERB") == "כתב"
    assert not denied("הקל", "קלל")
    # Pointed or final forms make no difference to the match.
    assert denied("הִכָּה", "הכה")
    assert denied("נסוך", "סוך")


def test_a_root_on_vav_is_a_conjunction_left_on() -> None:
    assert denied("ויך", "ויך")
    assert denied("הוכח", "וכח")  # י־כ־ח
    assert denied("התווה", "ווה")  # ת־ו־ה
    # The modern pi'els on a real ו root keep it.
    assert not denied("ויתר", "ותר")
    assert not denied("וידא", "ודא")


def test_every_entry_is_letters_and_names_a_root() -> None:
    for lemma, wrong in WRONG.items():
        assert lemma and all("א" <= ch <= "ת" for ch in lemma)
        assert wrong and all(len(root) in (3, 4) for root in wrong)


def test_a_rootless_verb_is_filled_where_the_table_agrees() -> None:
    # The plene pi'el DICTA writes, which the annotator's rule could not undo.
    assert root_for("דיבר", None, "VERB") == "דבר"
    assert root_for("הכניס", "", "VERB") == "כנס"
    # A participle, which DICTA lemmatises as itself.
    assert root_for("מגיע", None, "VERB") == "נגע"
    # A lemma ending in a final letter, which the table is keyed on as written.
    assert root_for("הלך", None, "VERB") == "הלך"


def test_a_lemma_spelled_like_another_verbs_form_is_not_that_verb() -> None:
    # אישר is also יִשֵּׁר's "I will straighten"; the table's answer is not taken.
    assert filled("אישר") != "ישר"
    assert root_for("אישר", None, "VERB") != "ישר"


def test_only_a_hebrew_verb_is_filled() -> None:
    assert root_for("דיבר", None, "NOUN") == ""
    assert root_for("דיבר", None, "VERB", "arc") == ""
    assert root_for("делать", None, "VERB", "ru") == ""
    assert root_for("דיבר", None, "VERB", "he-IL") == "דבר"


def test_a_denied_root_has_no_family() -> None:
    assert family_of("הטיל", "הפעיל") == ()


def test_the_roots_table_counts_verbs_by_root_and_binyan() -> None:
    tokens = {
        "s0": [
            {"lemma": "כתב", "pos": "VERB", "root": "כתב", "binyan": "פעל"},
            {"lemma": "הקל", "pos": "VERB", "root": "הקל", "binyan": "פעל"},
            {"lemma": "דיבר", "pos": "VERB"},
            {"lemma": "מכתב", "pos": "NOUN"},
        ],
        "s1": [
            {"lemma": "כתב", "pos": "VERB", "root": "כתב", "binyan": "פעל"},
            {"lemma": "דוד", "pos": "VERB", "entity": "B-PER", "root": "דוד"},
        ],
    }
    assert roots_table.count(tokens, "he") == Counter({("כתב", "פעל"): 2, ("דבר", ""): 1})


def test_the_rule_carries_the_version() -> None:
    assert roots_table.rule().endswith(f"verb-roots/{verb_roots.VERSION}")
