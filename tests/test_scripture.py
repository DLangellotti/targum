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
from targum.models import Segment, SegmentedDocument, Token

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

    `oshb/2` kept a contested headword's points and read the binyan and the root off the
    tagging instead of dropping them. `oshb/3` stops an Aramaic noun being read as its own
    suffixed definite article (targum-internal#64). Each is free to re-run: the lookup
    happens on this machine and `SCHEMA_VERSION` never moves.
    """
    assert ScriptureLemmatizer(Stub()).name == "oshb/5+stub/1"


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("Vqp3ms", "UPOS=VERB|Person=3|Gender=Masc|Number=Sing|Tense=Past|VerbForm=Fin"),
        # The waw-consecutive, which is the form biblical narrative is told in. Read as
        # the imperfect it is spelled as, the card would tell a learner that ויאמר is
        # "he will say".
        ("Vqw3ms", "UPOS=VERB|Person=3|Gender=Masc|Number=Sing|Tense=Past|VerbForm=Fin"),
        ("Vqi3ms", "UPOS=VERB|Person=3|Gender=Masc|Number=Sing|Tense=Fut|VerbForm=Fin"),
        # A participle writes no person, so its gender and number sit two places earlier.
        # On the finite layout this came out with no morphology at all.
        ("Vqrmpa", "UPOS=VERB|Gender=Masc|Number=Plur|Tense=Pres|VerbForm=Part"),
        ("Vhrmsa", "UPOS=VERB|Gender=Masc|Number=Sing|Tense=Pres|VerbForm=Part"),
        ("Vqc", "UPOS=VERB|VerbForm=Inf"),
        ("Ncfsa", "UPOS=NOUN|Gender=Fem|Number=Sing"),
        ("Ncmpa", "UPOS=NOUN|Gender=Masc|Number=Plur"),
        ("Sp2ms", "UPOS=PRON|Person=2|Gender=Masc|Number=Sing"),
        ("Td", "UPOS=PART"),
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


@pytest.mark.skipif(not oshb.available(), reason="the Hebrew Bible tagging is not on disk")
def test_every_headword_the_tagging_files_under_is_in_the_band_table() -> None:
    """The invariant the table exists on. It is counted from the tagging through
    `headword_of`, so nothing the lookup can file a word under is a word the table has
    never heard of — which is what made half the Tanakh "not in the Tanakh" when the
    table was Stanza's (targum-internal#156). Deuteronomy, because Nitzavim is where it
    was noticed; every book, if the tagging is there, would pass the same way.
    """
    from targum.annotate.biblical import _table
    from targum.annotate.scripture import headword_of, is_section

    table, _ = _table()
    missing: set[str] = set()
    for _ref, words in oshb.verses(oshb.BOOKS["Deuteronomy"]):
        for word in words:
            if is_section(word):
                continue
            headword = headword_of(word)
            if headword and headword not in table:
                missing.add(headword)
    assert not missing, sorted(missing)[:20]


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


def test_the_grammar_line_has_a_part_of_speech_to_branch_on(tagged: Path) -> None:
    """`reader.js` reads `UPOS=` out of the grammar string before anything else — it is
    what decides whether the card says "past · he" or "noun · f · pl." — and nothing had
    ever written it. So the line rendered empty for every word of every text while the
    features behind it shipped in the payload regardless."""
    got = ScriptureLemmatizer(Stub()).lemmas([verse("Genesis 1:1", FIRST)], "he")
    assert all((token.feats or "").startswith("UPOS=") for token in got["s1"])


def test_a_shared_spelling_keeps_its_points_beside_the_lemma(tagged: Path) -> None:
    """Deuteronomy 30:1 has הָאֵלֶּה, these, and 29:19 has הָאָלָה, the curse. Both are
    filed under אלה, and a meaning bought for the curse was shown for "these" across the
    whole Tanakh. The lemma has to stay bare — it is what a reader's marks are keyed on —
    so the pointed headword rides beside it, and only where the lexicon has more than
    one word spelled that way. The fixture lends ארץ a second pointing to stand in."""
    (tagged / oshb.LEXICON_FILE).write_text(
        json.dumps(
            {
                "7225": "רֵאשִׁית",
                "1254": "בָּרָא",
                "430": "אֱלֹהִים",
                "8064": "שָׁמַיִם",
                "776": "אֶרֶץ",
                "9999": "אָרַץ",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    oshb.forget()
    got = ScriptureLemmatizer(Stub()).lemmas([verse("Genesis 1:1", FIRST)], "he")["s1"]
    earth = got[-1]
    assert earth.lemma == "ארץ", "the identity is still the bare spelling"
    assert earth.headword == "אֶרֶץ", "and the points say which of the two words it is"
    assert earth.glossed_as == "אֶרֶץ"
    heavens = got[4]
    assert heavens.headword is None, "a spelling with one word to its name carries nothing"
    assert heavens.glossed_as == "שמים"


def test_the_scripture_path_says_which_other_language_it_can_read(tagged: Path) -> None:
    """Aramaic, and nothing else. Daniel and Ezra switch into it mid-book and the Open
    Scriptures tagging covers those chapters word for word, so `unread` can let it
    through to here rather than leaving the page blank (targum-internal#64, #195)."""
    lemmatizer = ScriptureLemmatizer(Stub())

    def block(language: str, ref: str = "Daniel 2:4") -> Segment:
        return Segment(
            id="s1",
            text="מלכא",
            ref=ref,
            kind="paragraph",
            block_id="b1",
            block_index=1,
            index=0,
            language=language,
        )

    assert lemmatizer.reads(block("arc")) is True
    assert lemmatizer.reads(block("arc-Hebr")) is True, "a script subtag is still Aramaic"
    for other in ("ru", "en", "yi", "he"):
        assert lemmatizer.reads(block(other)) is False, other

    assert lemmatizer.reads(block("arc", "Onkelos Genesis 1:1")) is False, (
        "Aramaic the tagging does not cover at all — answering yes would let a whole "
        "book through to a lookup that cannot place a word of it"
    )


def test_without_the_tagging_it_offers_to_read_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A box that never fetched the morphology cannot look anything up, so it says so and
    the Aramaic keeps the blank page it had. Saying yes here would hand Aramaic to a
    Hebrew model, which is the whole harm `unread` exists to prevent."""
    monkeypatch.setenv("TARGUM_MODEL_DIR", str(tmp_path))
    oshb.forget()
    blank = Segment(
        id="s1",
        text="מלכא",
        ref="Daniel 2:4",
        kind="paragraph",
        block_id="b1",
        block_index=1,
        index=0,
        language="arc",
    )
    assert ScriptureLemmatizer(Stub()).reads(blank) is False
    oshb.forget()


def test_a_block_the_lemmatizer_reads_is_not_left_unread(tagged: Path) -> None:
    """The rule `unread` states, exercised through both answers."""
    from targum.annotate.base import unread

    aramaic = Segment(
        id="s9",
        text="מלכא לעלמין חיי",
        ref="Daniel 2:4",
        kind="paragraph",
        block_id="b1",
        block_index=1,
        index=0,
        language="arc",
    )
    assert unread(aramaic, "he", ScriptureLemmatizer(Stub())) is False, "it can be looked up"
    assert unread(aramaic, "he", Stub()) is True, "a plain lemmatizer cannot read it"
    assert unread(aramaic, "he") is True, "and neither can nothing at all"


def test_aramaic_the_tagging_cannot_place_is_not_handed_to_a_hebrew_model(
    tagged: Path,
) -> None:
    """14 of Daniel's 200 Aramaic verses do not line up, because editions number them
    differently. Those keep the blank page: passing them to the fallback would be a
    Hebrew model reading Aramaic, which is the thing this whole rule is against."""
    stub = Stub()
    aramaic = Segment(
        id="s9",
        text="מלכא לעלמין חיי",
        ref="Daniel 2:4",
        kind="paragraph",
        block_id="b1",
        block_index=1,
        index=0,
        language="arc",
    )
    got = ScriptureLemmatizer(stub).lemmas([aramaic], "he")
    assert stub.asked == [], "the Hebrew fallback was never asked"
    assert got == {}, "and nothing was invented for it"


def test_hebrew_the_tagging_cannot_place_still_goes_to_the_model(tagged: Path) -> None:
    """The refusal above is about Aramaic only. Most of the shelf is Hebrew the tagging
    does not cover, and that has always been the fallback's job."""
    stub = Stub()
    hebrew = verse("Isaiah 53:1", "מי האמין לשמעתנו")
    ScriptureLemmatizer(stub).lemmas([hebrew], "he")
    assert stub.asked == ["s1"], "the fallback is still what reads it"


def test_the_artifact_says_how_much_the_tagging_actually_read(tagged: Path) -> None:
    """The name says the wrapper was in place. Only this says the lookup worked.

    Wrapping happens when the source is biblical and the tagging is on disk, and the
    fall-through is per verse — so a copy of Genesis whose edition numbers its verses
    differently is read entirely by the model under a name claiming otherwise. Two such
    copies on the shelf carried the same annotator name byte for byte while disagreeing
    by five points of difficulty (targum-internal#180).
    """
    read = ScriptureLemmatizer(Stub())
    assert read.scripture_share is None, "nothing has been asked yet"

    read.lemmas([verse("Genesis 1:1", FIRST)], "he")
    assert read.scripture_share == 1.0

    # The `p4` copy: the wrapper is in place and lines up with nothing at all. It is the
    # case the name cannot tell from the one above, and `0.0` is not `None`.
    read.lemmas([verse("Genesis 1:1", "בראשית ברא אלהים ומשהו נוסף לגמרי", "odd")], "he")
    assert read.scripture_share == 0.0


def test_a_book_the_tagging_read_whole_still_reports_under_one(tagged: Path) -> None:
    """A share rather than a flag, because partial coverage is the ordinary case: a
    chapter heading is not a verse and never lines up. Reading this as a boolean would
    call a fully-read book partly guessed at, or a wholly-guessed one read."""
    read = ScriptureLemmatizer(Stub())
    read.lemmas(
        [verse("Genesis 1:1", FIRST), verse("Genesis 1", "בראשית א׳", "heading")],
        "he",
    )
    assert read.scripture_share == 0.5


# --- through the whole annotator ---------------------------------------------


class Rates:
    """Bands that rate anything, so the pipeline runs without a frequency table."""

    name = "fake-bands/1"
    method = "curated:test"
    note = "A test list."

    def supports(self, language: str) -> bool:
        return True

    def band(self, lemma: str, language: str) -> int:
        return 3


def one_verse(ref: str, text: str) -> SegmentedDocument:
    return SegmentedDocument(
        document_hash="h",
        language="he",
        segmenter="fake/1",
        segments=[verse(ref, text, "0000.000-aaaaaa")],
    )


def test_a_verb_keeps_its_binyan_through_the_whole_annotator(tagged: Path) -> None:
    """The lemmatizer answering correctly is not the same fact as the shelf carrying it.

    `test_a_verb_carries_its_binyan_and_root_off_the_tagging` above pins the lemmatizer.
    This pins the pipeline, which is the layer targum-internal#207 was actually about:
    the built shelf carried a binyan on 0.68% of its scripture verbs — 445 of 65,827,
    with five books at exactly zero — while the lemmatizer beside it answered 100% for
    the same book. Banding, the register and the dictionary stage all run between the
    two, and nothing pinned what came out the far end.

    So this is deliberately the full `Annotator` and not `ScriptureLemmatizer`: a
    shelf-wide drop to zero has to fail a test rather than wait for an audit.
    """
    from targum.annotate import Annotator

    annotation = Annotator(lemmatizer=ScriptureLemmatizer(Stub()), bands=Rates()).annotate(
        one_verse("Genesis 1:1", FIRST)
    )
    verbs = [
        token for tokens in annotation.tokens.values() for token in tokens if token.pos == "VERB"
    ]
    assert [(token.lemma, token.binyan, token.root) for token in verbs] == [("ברא", "פעל", "ברא")]
    assert all("UPOS=VERB" in (token.feats or "") for token in verbs), (
        "the grammar line reads UPOS= before anything else"
    )


def test_the_annotation_records_what_the_tagging_covered(tagged: Path) -> None:
    """The share reaches the artifact, which is the only place anything downstream can
    read it. `measure_difficulty.by_scripture_path` sniffed `PART` tags to recover this
    because the artifact could not answer (targum-internal#180)."""
    from targum.annotate import Annotator

    read = Annotator(lemmatizer=ScriptureLemmatizer(Stub()), bands=Rates())
    assert read.annotate(one_verse("Genesis 1:1", FIRST)).scripture_share == 1.0
    # The wrapper in place, lining up with nothing: the `p4` copy of Genesis.
    missed = read.annotate(one_verse("Genesis 1:1", "בראשית ברא אלהים ומשהו נוסף לגמרי"))
    assert missed.scripture_share == 0.0


def test_a_model_read_annotation_records_no_share_at_all(tagged: Path) -> None:
    """`None` and `0.0` are different facts: nothing asked, against asked and answered
    nowhere. Every text built before this field existed reads `None`, which is why
    `by_scripture_path` still falls back to the tags for those."""
    from targum.annotate import Annotator

    annotation = Annotator(lemmatizer=Stub(), bands=Rates()).annotate(
        one_verse("Genesis 1:1", FIRST)
    )
    assert annotation.scripture_share is None
