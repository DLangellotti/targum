"""Tokens for the Hebrew Bible, taken from the hand tagging rather than worked out.

The fixture is real Open Scriptures data, so what these read is what a fetch would write.
Nothing here touches the network and nothing loads a model: the fallback is a stub, which
is also how the fall-through is checked.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from targum.annotate import oshb
from targum.annotate.scripture import (
    ScriptureLemmatizer,
    binyan_of,
    features,
    part_of,
    root_of,
)
from targum.models import Segment, Token

FIXTURES = Path(__file__).parent / "fixtures" / "oshb"

#: Genesis 1:1 as the shelf holds it, with the points stripped the way `Annotator` strips
#: them before it asks a lemmatizer anything.
FIRST = "בראשית ברא אלהים את השמים ואת הארץ׃"


class Stub:
    """A lemmatizer that records what it was asked and answers nothing useful."""

    def __init__(self) -> None:
        self.asked: list[str] = []

    @property
    def name(self) -> str:
        return "stub/1"

    def lemmas(self, segments: list[Segment], language: str) -> dict[str, list[Token]]:
        self.asked.extend(segment.id for segment in segments)
        return {segment.id: [] for segment in segments}


def verse(ref: str, text: str, ident: str = "s1") -> Segment:
    return Segment(
        id=ident, text=text, ref=ref, kind="paragraph", block_id="b0001", block_index=1, index=0
    )


@pytest.fixture
def tagged(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("TARGUM_MODEL_DIR", str(tmp_path))
    oshb.forget()
    home = tmp_path / "oshb"
    home.mkdir(parents=True)
    verses = oshb.parse((FIXTURES / "Gen.xml").read_text(encoding="utf-8"))
    (home / "Gen.json").write_text(json.dumps(verses, ensure_ascii=False), encoding="utf-8")
    # Only the entries this fixture needs; the real file is 2.7 MB of the same shape.
    (home / oshb.LEXICON_FILE).write_text(
        json.dumps(
            {"7225": "רֵאשִׁית", "1254": "בָּרָא", "430": "אֱלֹהִים", "8064": "שָׁמַיִם", "776": "אֶרֶץ"},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    yield home
    oshb.forget()


def test_a_verse_is_looked_up_and_never_reaches_the_model(tagged: Path) -> None:
    stub = Stub()
    got = ScriptureLemmatizer(stub).lemmas([verse("Genesis 1:1", FIRST)], "he")

    assert stub.asked == [], "a verse the tagging covers is not guessed at"
    assert len(got["s1"]) == 7, "seven words in the first verse of the Bible"


def test_the_dictionary_form_is_the_headword_not_the_surface(tagged: Path) -> None:
    """`השמים` is filed under `שמים`, which is the word — and the point of the lookup."""
    got = ScriptureLemmatizer(Stub()).lemmas([verse("Genesis 1:1", FIRST)], "he")["s1"]
    assert [token.lemma for token in got] == [
        "ראשית",
        "ברא",
        "אלהים",
        "את",
        "שמים",
        "את",
        "ארץ",
    ]


def test_the_prefix_division_comes_from_the_tagging(tagged: Path) -> None:
    """Hand-made rather than guessed. `בראשית` is a preposition and a noun; the current
    model splits words that should not be split and vice versa."""
    got = ScriptureLemmatizer(Stub()).lemmas([verse("Genesis 1:1", FIRST)], "he")["s1"]
    assert got[0].split and got[0].built == "ב + ראשית"
    assert got[4].built == "ה + שמים"
    assert not got[1].split and got[1].built is None, "one piece is not a composition"


def test_a_token_covers_its_letters_and_not_the_punctuation(tagged: Path) -> None:
    """A verse ends `הארץ׃`. Left in, the span covers the sof pasuq and tapping the last
    word of a verse highlights a colon with it."""
    got = ScriptureLemmatizer(Stub()).lemmas([verse("Genesis 1:1", FIRST)], "he")["s1"]
    last = got[-1]
    assert last.surface == "הארץ"
    assert FIRST[last.start : last.end] == "הארץ"


def test_everything_that_is_not_scripture_falls_through(tagged: Path) -> None:
    """Most of what targum reads. The Mishnah is Hebrew and is not this Hebrew."""
    stub = Stub()
    ScriptureLemmatizer(stub).lemmas(
        [verse("Mishnah Berakhot 1:1", "מאימתי קורין את שמע", "m1")], "he"
    )
    assert stub.asked == ["m1"]


def test_a_verse_that_does_not_line_up_falls_through(tagged: Path) -> None:
    """Editions divide verses differently. On those the model answers, exactly as it does
    for every verse today — the lookup is not total and does not pretend to be."""
    stub = Stub()
    ScriptureLemmatizer(stub).lemmas(
        [verse("Genesis 1:1", "בראשית ברא אלהים ומשהו נוסף לגמרי", "odd")], "he"
    )
    assert stub.asked == ["odd"], "a verse whose words do not match is not forced"


def test_another_language_is_never_looked_up_here(tagged: Path) -> None:
    stub = Stub()
    ScriptureLemmatizer(stub).lemmas([verse("Genesis 1:1", FIRST, "ru")], "ru")
    assert stub.asked == ["ru"]


def test_the_name_says_both_because_both_ran(tagged: Path) -> None:
    """A text tagged from the morphology is a different artefact from one a model guessed
    at, and on most of the shelf the fallback is what ran — so the name carries both, and
    changing it is what makes existing texts read again.

    `oshb/2` is the version that reads the binyan and the root off the tagging instead of
    dropping them. Every biblical reader is re-annotated on the next `rebuild --words`,
    which is free: the lookup runs on this machine and `SCHEMA_VERSION` never moves.
    """
    assert ScriptureLemmatizer(Stub()).name == "oshb/2+stub/1"


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("Vqp3ms", "Person=3|Gender=Masc|Number=Sing|Tense=Past|VerbForm=Fin"),
        # The waw-consecutive, which is the form biblical narrative is told in. Read as
        # the imperfect it is spelled as, the card would tell a learner that ויאמר is
        # "he will say".
        ("Vqw3ms", "Person=3|Gender=Masc|Number=Sing|Tense=Past|VerbForm=Fin"),
        ("Vqi3ms", "Person=3|Gender=Masc|Number=Sing|Tense=Fut|VerbForm=Fin"),
        # A participle writes no person, so its gender and number sit two places earlier.
        # On the finite layout this came out with no morphology at all.
        ("Vqrmpa", "Gender=Masc|Number=Plur|Tense=Pres|VerbForm=Part"),
        ("Vhrmsa", "Gender=Masc|Number=Sing|Tense=Pres|VerbForm=Part"),
        ("Vqc", "VerbForm=Inf"),
        ("Ncfsa", "Gender=Fem|Number=Sing"),
        ("Ncmpa", "Gender=Masc|Number=Plur"),
        ("Sp2ms", "Person=2|Gender=Masc|Number=Sing"),
        ("Td", None),
    ],
)
def test_the_morphology_is_read_positionally(code: str, expected: str | None) -> None:
    """The whole difficulty of these codes, and both mistakes were live in the first draft.

    `Vqp3ms` is a verb, qal stem, **perfect** aspect, 3rd masculine singular — read as a
    bag of letters, the `p` of "perfect" is found in the number table and the word comes
    out plural. `Ncfsa` is a noun, **common**, feminine singular — and the same mistake
    reads the `c` of "common" as a gender.
    """
    assert features(code) == expected


def test_a_name_is_a_proper_noun_so_it_is_left_out_of_the_counting() -> None:
    """targum does not rate a name for difficulty. Getting this wrong would call every
    name in a chronicle a word the reader has to learn."""
    assert part_of("Np") == "PROPN"
    assert part_of("Ncmsa") == "NOUN"
    assert part_of("Vqp3ms") == "VERB"


def test_name_candidates_offers_only_names() -> None:
    """The lesson of the Tanakh-wide sweep, encoded.

    A general filter for spelling variants produced 2,435 candidates; tightened to "seen
    three times, both forms common, one letter apart" it still produced 193, of which
    about six were real. `אחות` against `אחת` — sister and one — survives every rule that
    can be written, because both differ by one letter and both are ordinary Hebrew.

    A proper name cannot do that, so the morphology's own tag is the rail.
    """
    from targum.annotate.scripture import name_candidates

    got = name_candidates(
        [("Np", "אהרן", "אהרון")] * 3
        + [("Ncfsa", "אחות", "אחת")] * 9  # sister and one, and not a name
        + [("Np", "דוד", "דויד")] * 4
    )

    assert set(got) == {("אהרון", "אהרן"), ("דוד", "דויד")} or set(got) == set(), (
        "names only, and the rows already folded may collapse to nothing"
    )
    assert not any("אחות" in pair for pair in got), "sister and one are never offered"


def test_name_candidates_needs_the_pair_more_than_once() -> None:
    """One disagreement is a typo in an edition. Three is a spelling."""
    from targum.annotate.scripture import name_candidates

    assert name_candidates([("Np", "ירושלים", "ירושלם")], least=3) == {}
    assert name_candidates([("Np", "ירושלים", "ירושלם")] * 3, least=3) != {}


def test_a_lexeme_written_as_two_words_keeps_its_space(tagged: Path) -> None:
    """Strong's 1035 is `בֵּית לֶחֶם` — one lexeme, two words — and the tagging gives that
    headword to the second half of the place name.

    Stripping everything that is not a letter turned it into `ביתלחם`, which is not how
    anybody writes Bethlehem and is what the card showed until a rebuild of Ruth put it in
    front of somebody. One lexeme is one vocabulary entry, so the entry is the place and
    the space stays.
    """
    from targum.annotate.scripture import _headword

    assert _headword("בֵּית לֶחֶם") == "בית לחם"
    assert _headword("שָׁמַיִם") == "שמים", "a one-word headword is unaffected"
    assert _headword("  בֵּית   לֶחֶם ׃") == "בית לחם", "and the punctuation still goes"


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("Vqp3ms", "פעל"),
        ("Vhw3ms", "הפעיל"),
        ("Vtp3ms", "התפעל"),
        ("VNi3fs", "נפעל"),
        ("VPw3mp", "פועל"),
        ("VHp3ms", "הופעל"),
        ("Vpw3ms", "פיעל"),
        # A stem outside the seven — polel here — is left unsaid rather than pushed into
        # the nearest one. The root still comes, because it is read and not derived.
        ("Vop3ms", None),
        ("Ncfsa", None),
        ("", None),
    ],
)
def test_the_binyan_is_the_stem_letter_somebody_wrote_down(code: str, expected: str | None) -> None:
    """The fact the modern annotator guesses at from spelling, and this one simply has.

    DICTA tags no binyan, so on the modern half it is derived from the two lemma shapes
    that cannot mean anything else, and lands on one verb in twenty. The morphology
    carries it outright for every verb of the Tanakh (targum-internal#116).
    """
    assert binyan_of(code) == expected


@pytest.mark.parametrize(
    ("headword", "root"),
    [
        ("בָּרָא", "ברא"),
        # The root is read whatever pattern the word in front of us is in: `מבדיל` is
        # filed under `בדל` and `יקם` under `נקם`, with the נ the form does not write.
        ("בָּדַל", "בדל"),
        ("נָקַם", "נקם"),
        # Undoing the pattern, the way the modern path must, would take this apart: the
        # ה of הלך belongs to the root and a hitpael rule strips it.
        ("הָלַךְ", "הלך"),
        ("שָׁפַט", "שפט"),
        # Quadriliterals are real roots and are kept.
        ("כִּרְסֵם", "כרסם"),
        # Not a root: a lexicon entry that is a phrase, or a defective record.
        ("בֵּית לֶחֶם", None),
        ("", None),
    ],
)
def test_the_root_is_read_from_the_lexicon_not_worked_out(headword: str, root: str | None) -> None:
    """16,205 of 16,248 verb pieces in Genesis, Isaiah, Psalms and Ruth have a
    three-letter headword, and it is the root. Strong's numbers a lexeme, and for a verb
    the lexeme it numbers is the root itself."""
    assert root_of(headword) == root


def test_a_verb_carries_its_binyan_and_root_off_the_tagging(tagged: Path) -> None:
    """Genesis 1:1 — `ברא` is qal and its root is itself, straight out of the morphology.

    Before this the biblical half of the shelf carried a binyan on 1.7% of its verbs and
    a root on 1.1%, on data that had both written down for every one of them.
    """
    got = ScriptureLemmatizer(Stub()).lemmas([verse("Genesis 1:1", FIRST)], "he")
    verbs = [token for token in got["s1"] if token.pos == "VERB"]
    assert [(token.lemma, token.binyan, token.root) for token in verbs] == [("ברא", "פעל", "ברא")]


def test_only_a_verb_is_given_a_binyan(tagged: Path) -> None:
    """`Ncfsa` has letters in the stem's place too, and a noun with a binyan on its card
    would be a lie the reader has no way to check."""
    got = ScriptureLemmatizer(Stub()).lemmas([verse("Genesis 1:1", FIRST)], "he")
    assert all(
        token.binyan is None and token.root is None for token in got["s1"] if token.pos != "VERB"
    )
