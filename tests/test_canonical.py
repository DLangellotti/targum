"""One spelling per word, because the lemma is a vocabulary key and not only a word.

The case that made this necessary is real: `dictabert-lex` returns `כל` four times and
`כול` four times over Genesis 1, for the same word, in the same chapter.
"""

from __future__ import annotations

from targum.annotate.canonical import (
    NOT_THE_SAME,
    SAME_WORD,
    bare,
    candidates,
    canonical,
)


def test_the_pointing_comes_off() -> None:
    """Mechanical and always safe: the marks are a reading aid, not part of the word."""
    assert bare("שָׁמַ֖יִם") == "שמים"
    assert bare("בְּרֵאשִׁ֖ית") == "בראשית"
    assert bare("אֱלֹהִ֑ים") == "אלהים"


def test_the_taamim_come_off_too() -> None:
    """A cantillated word and a plain one are the same word, and the whole biblical shelf
    is cantillated."""
    assert bare("וַיֹּ֥אמֶר") == "ויאמר"
    assert bare("כָּל־") == "כל", "and the maqaf goes with them"


def test_a_ktiv_variant_folds_onto_the_spelling_a_reader_meets() -> None:
    """The measured case. Both spellings are real Hebrew; they are one word, and a
    vocabulary page that lists them twice is wrong about how much somebody knows."""
    assert canonical("כול") == "כל"
    assert canonical("כל") == "כל"


def test_a_biblical_headword_and_a_modern_lemma_meet() -> None:
    """The other job this does. A pointed headword out of the biblical morphology and an
    unpointed lemma out of the modern annotator have to land on one key, or one
    vocabulary across the two registers is not true."""
    assert canonical("שָׁמַיִם") == canonical("שמים")


def test_words_that_merely_look_alike_are_left_alone() -> None:
    """The reason the folding is a table and not a rule.

    `ספר` and `ספור` differ by a vav exactly the way `שמים` and `שמיים` do, and they are
    different words. A rule that folded optional matres would merge them silently, and a
    reader cannot see a merge happen — where they can see a word listed twice.
    """
    assert canonical("ספר") != canonical("ספור")
    assert canonical("ספור") == "ספור", "not folded, because nothing said it should be"


def test_nothing_in_it_is_nothing_out() -> None:
    """So a caller can tell "no word here" from "a word spelled oddly"."""
    assert canonical("") == ""
    assert canonical("־") == ""
    assert canonical("(") == ""


def test_the_table_holds_only_what_was_measured() -> None:
    """A guard on the file's own rule. Every row is a pair somebody looked at; a row
    added because it seemed likely is how unrelated words get merged."""
    assert SAME_WORD == {
        "כול": "כל",
        "שמיים": "שמים",
        "לוא": "לא",
        "שלשים": "שלושים",
        "מאד": "מאוד",
        "כח": "כוח",
        "אהרון": "אהרן",
        "דויד": "דוד",
        "מות": "מוות",
        "שמנה": "שמונה",
    }, "add a row only with the evidence that produced it — see candidates()"


def test_a_name_with_two_spellings_is_one_person() -> None:
    """The safest category, and the only one a Tanakh-wide sweep produced reliably: a
    name cannot secretly be two words, so a vav cannot hide a second sense behind it."""
    assert canonical("אהרון") == canonical("אהרן")
    assert canonical("דויד") == canonical("דוד")


def test_the_canonical_side_is_the_commoner_spelling_not_the_modern_one() -> None:
    """Register would have been the tidier rule and the worse one. `שמים` outruns `שמיים`
    in written Hebrew and `לא` outruns `לוא` by four orders of magnitude, while `מאוד` and
    `כוח` go the other way. The rule is what a reader is likely to recognise."""
    assert canonical("שמיים") == "שמים", "the shorter form is the commoner one here"
    assert canonical("לוא") == "לא"
    assert canonical("מאד") == "מאוד", "and here the longer one is"
    assert canonical("כח") == "כוח"


def test_a_pair_a_reader_refused_is_written_down() -> None:
    """`גדול` and `גדל` differ by one vav exactly as `שמים` and `שמיים` do, and are the
    adjective against the verb. The filter offers them; a person refused them; and a
    refusal nobody records is one that gets re-litigated by whoever runs the sweep next.
    """
    assert ("גדול", "גדל") in NOT_THE_SAME
    assert canonical("גדל") != canonical("גדול"), "refused means not folded"
    assert canonical("בת") != canonical("בית"), "daughter is not house"


def test_candidates_finds_what_an_annotator_could_not_spell_twice() -> None:
    """How the table earns a row: feed it every (surface, lemma) a corpus produced and it
    reports the words that came back two ways. Each is then a judgement, not a rule."""
    found = candidates(
        [
            ("כָּל", "כל"),
            ("כָּל", "כול"),
            ("אֱלֹהִים", "אלהים"),
            ("אֱלֹהִים", "אלהים"),
        ]
    )
    # `כול` already folds to `כל`, so the surface no longer disagrees with itself.
    assert "אלהים" not in found, "a surface spelled one way is not a candidate"
    assert found == {}, "and the one that did disagree is already in the table"


def test_candidates_reports_a_disagreement_that_is_not_yet_folded() -> None:
    found = candidates([("מילה", "מילה"), ("מילה", "מלה")])
    assert found == {"מילה": {"מילה", "מלה"}}, "reported, not folded — that is a person's call"
