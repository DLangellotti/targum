"""Stripping marks, mapping offsets across the two forms, and who owns a word's vowels."""

from __future__ import annotations

import unicodedata

import pytest

from targum.errors import SkeletonChanged
from targum.models import Segment, SegmentedDocument
from targum.vocalize import vocalize_document
from targum.vocalize.base import (
    LETTERS,
    MARKS,
    TAAMIM,
    has_nikkud,
    has_taamim,
    is_fully_pointed,
    map_span,
    pointed_positions,
    splice,
    strip_nikkud,
    strip_taamim,
)

# One verse, pointed and bare. Carries a maqaf, which is the character three of the four
# surveyed diacritizers damage.
POINTED = "שָׁלוֹם רָב שׁוּבֵךְ, צִפֹּרָה נֶחְמֶדֶת, מֵאַרְצוֹת הַחֹם אֶל־חַלּוֹנִי"
BARE = "שלום רב שובך, צפרה נחמדת, מארצות החם אל־חלוני"

# Ruth 1:2, from the pinned Masoretic edition. Carries accents, a maqaf, a paseq, and —
# the reason this text and not another — four metagim, the mark the accent-stripped
# edition deletes.
TROPE = (
    "וְשֵׁ֣ם הָאִ֣ישׁ אֱ‍ֽלִימֶ֡לֶךְ וְשֵׁם֩ אִשְׁתּ֨וֹ נָעֳמִ֜י וְשֵׁ֥ם שְׁנֵֽי־בָנָ֣יו ׀ "
    "מַחְל֤וֹן וְכִלְיוֹן֙ אֶפְרָתִ֔ים מִבֵּ֥ית לֶ֖חֶם יְהוּדָ֑ה וַיָּב֥וֹאוּ שְׂדֵי־מוֹאָ֖ב וַיִּֽהְיוּ־שָֽׁם׃"
)


class TestMarks:
    def test_punctuation_inside_the_hebrew_block_is_not_a_mark(self) -> None:
        # The whole point of deriving MARKS from Unicode. These four sit inside
        # 0x0591-0x05C7 and stripping any of them would change the text.
        for char in ("־", "׀", "׃", "׆"):
            assert ord(char) not in MARKS, unicodedata.name(char)

    def test_vowels_and_dagesh_are_marks(self) -> None:
        for char in ("ָ", "ְ", "ּ", "ׁ", "ׂ", "ֻ", "ׇ"):
            assert ord(char) in MARKS, unicodedata.name(char)


class TestTaamim:
    """The accents, and where the line between them and the vowels is drawn."""

    def test_the_accents_are_marks_but_not_every_mark_is_an_accent(self) -> None:
        assert TAAMIM < MARKS

    def test_no_vowel_is_an_accent(self) -> None:
        # Sheva, hataf, hiriq, tsere, segol, patah, qamats, holam, qubuts, dagesh, the
        # shin and sin dots, and qamats qatan. None of these ever comes off.
        for char in ("ְ", "ֱ", "ִ", "ֵ", "ֶ", "ַ", "ָ", "ֹ", "ֻ", "ּ", "ׁ", "ׂ", "ׇ"):
            assert ord(char) not in TAAMIM, unicodedata.name(char)

    def test_meteg_stays_with_the_vowels(self) -> None:
        """The whole reason this feature exists, held as a rule.

        U+05BD is meteg and silluq both — Unicode gives them one codepoint. Putting it
        with the accents would delete the meteg that separates a qamats gadol from a
        qamats qatan, which is exactly the damage the accent-stripped Sefaria edition
        does and exactly what moving to the accented one undoes.
        """
        assert ord("ֽ") in MARKS
        assert ord("ֽ") not in TAAMIM
        assert "ֽ" in strip_taamim(TROPE)

    def test_an_accent_is_an_accent(self) -> None:
        # Munah, pashta, zaqef qatan, etnahta, sof pasuq's silluq excepted above.
        for char in ("֣", "֙", "֔", "֑", "֡", "֜"):
            assert ord(char) in TAAMIM, unicodedata.name(char)

    def test_has_taamim_asks_about_accents_only(self) -> None:
        assert has_taamim(TROPE)
        assert not has_taamim(POINTED), "a pointed verse with no accents has none"
        assert not has_taamim(BARE)


class TestStripTaamim:
    def test_the_accents_go_and_the_vowels_stay(self) -> None:
        vowels = strip_taamim(TROPE)
        assert not has_taamim(vowels)
        assert has_nikkud(vowels)

    def test_the_consonants_are_the_same_underneath(self) -> None:
        """The invariant the reader's offset map rests on: all three forms of a sentence
        share one skeleton, so one map drawn off any of them lands on the same letters."""
        assert strip_nikkud(strip_taamim(TROPE))[0] == strip_nikkud(TROPE)[0]

    def test_the_punctuation_of_a_verse_survives(self) -> None:
        # Maqaf, paseq and sof pasuq are characters of the text and sit outside TAAMIM
        # for the same reason they sit outside MARKS.
        for char in ("־", "׀", "׃"):
            assert char in strip_taamim(TROPE), unicodedata.name(char)

    def test_a_text_with_no_accents_is_returned_as_it_was(self) -> None:
        assert strip_taamim(POINTED) == POINTED
        assert strip_taamim(BARE) == BARE


class TestStripNikkud:
    def test_removes_marks_and_keeps_everything_else(self) -> None:
        assert strip_nikkud(POINTED)[0] == BARE

    def test_bare_text_is_unchanged(self) -> None:
        assert strip_nikkud(BARE)[0] == BARE

    def test_keeps_the_maqaf(self) -> None:
        assert "אל־חלוני" in strip_nikkud(POINTED)[0]

    def test_keeps_gershayim_and_an_embedded_latin_run(self) -> None:
        text = "בשנת תרנ״ז (1897) נתכנס Magma Devs"
        assert strip_nikkud(text)[0] == text

    def test_map_has_one_entry_more_than_the_text(self) -> None:
        _, index = strip_nikkud(POINTED)
        assert len(index) == len(POINTED) + 1

    def test_map_never_goes_backwards(self) -> None:
        _, index = strip_nikkud(POINTED)
        assert index == sorted(index)

    def test_map_ends_at_the_length_of_the_bare_text(self) -> None:
        bare, index = strip_nikkud(POINTED)
        assert index[-1] == len(bare)


class TestOffsetsSurviveBothDirections:
    """A token span must name the same word whichever form is on show."""

    @pytest.mark.parametrize("word", ["שלום", "שובך", "צפרה", "מארצות", "חלוני"])
    def test_a_bare_span_maps_onto_the_same_pointed_word(self, word: str) -> None:
        start = BARE.index(word)
        pointed_start, pointed_end = map_span(start, start + len(word), pointed_positions(POINTED))
        assert strip_nikkud(POINTED[pointed_start:pointed_end])[0] == word

    @pytest.mark.parametrize("word", ["שָׁלוֹם", "צִפֹּרָה", "חַלּוֹנִי"])
    def test_a_pointed_span_maps_onto_the_same_bare_word(self, word: str) -> None:
        start = POINTED.index(word)
        _, index = strip_nikkud(POINTED)
        bare_start, bare_end = map_span(start, start + len(word), index)
        assert BARE[bare_start:bare_end] == strip_nikkud(word)[0]

    def test_a_span_covering_the_whole_text_maps_to_the_whole_text(self) -> None:
        start, end = map_span(0, len(BARE), pointed_positions(POINTED))
        assert (start, end) == (0, len(POINTED))

    def test_each_side_of_a_maqaf_maps_separately(self) -> None:
        # If the maqaf were treated as part of a word, these two spans would overlap.
        left = BARE.index("אל־")
        first = map_span(left, left + 2, pointed_positions(POINTED))
        second = map_span(left + 3, len(BARE), pointed_positions(POINTED))
        assert strip_nikkud(POINTED[first[0] : first[1]])[0] == "אל"
        assert strip_nikkud(POINTED[second[0] : second[1]])[0] == "חלוני"


class TestPointedness:
    def test_has_nikkud(self) -> None:
        assert has_nikkud(POINTED)
        assert not has_nikkud(BARE)

    def test_a_maqaf_alone_is_not_nikkud(self) -> None:
        assert not has_nikkud("אל־חלוני")

    def test_fully_pointed(self) -> None:
        assert is_fully_pointed(POINTED)
        assert not is_fully_pointed(BARE)

    def test_a_partly_pointed_line_is_not_fully_pointed(self) -> None:
        # The shape the Wikisource Mishnah actually ships: a bare label above pointed text.
        assert not is_fully_pointed("משנה א מֵאֵימָתַי קוֹרִין")

    def test_text_with_no_hebrew_is_not_fully_pointed(self) -> None:
        # Nothing to point, so there is nothing to claim. Reported as not-done rather
        # than vacuously done, so an English document never looks like a finished job.
        assert not is_fully_pointed("Magma Devs (1897)")


class TestSplice:
    """Source pointing wins per word; the model only fills the bare ones."""

    def test_a_fully_pointed_source_is_returned_verbatim(self) -> None:
        merged, machine = splice(POINTED, POINTED)
        assert merged == POINTED
        assert machine is False

    def test_a_fully_pointed_source_ignores_the_model_entirely(self) -> None:
        # Same consonants, nonsense vowels — a patah on every letter. Built from BARE
        # rather than typed out, so it cannot accidentally differ in its skeleton.
        wrong = "".join(c + ("ַ" if ord(c) in LETTERS else "") for c in BARE)
        assert strip_nikkud(wrong)[0] == BARE
        merged, machine = splice(POINTED, wrong)
        assert merged == POINTED
        assert machine is False

    def test_a_bare_source_takes_the_model_throughout(self) -> None:
        merged, machine = splice(BARE, POINTED)
        assert merged == POINTED
        assert machine is True

    def test_a_mixed_segment_keeps_its_pointed_words_and_fills_only_the_bare_ones(
        self,
    ) -> None:
        source = "משנה א מֵאֵימָתַי קוֹרִין"
        model = "מִשְׁנָה א מאימתי קורין"
        merged, machine = splice(source, model)
        # The source's own pointing survives untouched...
        assert "מֵאֵימָתַי קוֹרִין" in merged
        # ...and the word it left bare took the model's, even though the model happened
        # to leave the rest bare in turn.
        assert merged.startswith("מִשְׁנָה")
        assert machine is True

    def test_each_side_of_a_maqaf_is_decided_on_its_own(self) -> None:
        source = "אֶל־חלוני"
        model = "אַל־חַלּוֹנִי"
        merged, machine = splice(source, model)
        assert merged == "אֶל־חַלּוֹנִי"
        assert machine is True

    def test_a_word_neither_side_points_claims_nothing(self) -> None:
        merged, machine = splice("שלום רב", "שלום רב")
        assert merged == "שלום רב"
        assert machine is False

    def test_punctuation_digits_and_latin_pass_through_from_the_source(self) -> None:
        source = "בשנת תרנ״ז (1897) נתכנס Magma Devs"
        model = "בִּשְׁנַת תרנ״ז (1897) נִתְכַּנֵּס Magma Devs"
        merged, _ = splice(source, model)
        assert "(1897)" in merged and "Magma Devs" in merged and "תרנ״ז" in merged

    def test_a_model_that_changed_a_letter_is_rejected(self) -> None:
        with pytest.raises(SkeletonChanged):
            splice("אל־חלוני", "אַלְחָלוֹנִי")

    def test_a_model_that_dropped_the_maqaf_is_rejected(self) -> None:
        # phonikud does exactly this, and fuses the words either side.
        with pytest.raises(SkeletonChanged):
            splice("בארץ־ישראל", "בְּאֶרֶץיִשְׂרָאֵל")

    def test_a_model_that_dropped_a_matres_lectionis_is_rejected(self) -> None:
        # The silent default in three of the four engines surveyed: ktiv male quietly
        # becomes ktiv haser, which deletes a letter the reader is looking at.
        with pytest.raises(SkeletonChanged):
            splice("שלום", "שָׁלֹם")

    def test_the_merge_never_changes_the_consonants(self) -> None:
        merged, _ = splice(BARE, POINTED)
        assert strip_nikkud(merged)[0] == BARE


class FakeEngine:
    """Points every bare word with a patah, so what it touched is unmistakable."""

    name = "fake/1"
    model = "fake-model"

    def __init__(self, mangle: set[str] | None = None) -> None:
        self.mangle = mangle or set()
        self.asked: list[str] = []

    def available(self) -> tuple[bool, str]:
        return True, ""

    def vocalize(self, segments: list[Segment], language: str) -> dict[str, str]:
        self.asked = [segment.id for segment in segments]
        out = {}
        for segment in segments:
            if segment.id in self.mangle:
                # Drops the maqaf, the way phonikud does.
                out[segment.id] = segment.text.replace("־", "")
            else:
                out[segment.id] = "".join(
                    c + ("ַ" if ord(c) in LETTERS and not has_nikkud(c) else "")
                    for c in segment.text
                )
        return out


def _document(*texts: str) -> SegmentedDocument:
    return SegmentedDocument(
        document_hash="doc123",
        language="he",
        segmenter="fake",
        segments=[
            Segment(id=f"s{i}", block_id="b0", block_index=0, index=i, text=text)
            for i, text in enumerate(texts)
        ],
    )


class TestScriptureIsNeverGuessedAt:
    """The one shelf a diacritizer may not touch, whatever shape the text arrives in.

    Until this existed the refusal was an accident: a Tanakh happens to arrive pointed,
    so `wants_pointing` never loaded a model. That held only while the edition did. If
    one ever degraded, Nakdimon would have invented vowels in Genesis and the page would
    have shown them behind a dotted rule, which a reader has no way to doubt.
    """

    def test_a_biblical_source_never_reaches_the_engine(self) -> None:
        engine = FakeEngine()
        result = vocalize_document(_document(BARE, BARE), engine, source="sefaria:Ruth")
        assert engine.asked == [], "a diacritizer was asked about scripture"
        assert result.segments == {}, "a bare verse was pointed"
        assert result.vocalizer == "source"
        assert result.model is None

    def test_a_bare_verse_stays_bare_rather_than_failing(self) -> None:
        """No guess, and no crash either: the verse renders as the edition published it."""
        result = vocalize_document(_document(POINTED, BARE), FakeEngine(), source="sefaria:Ruth")
        assert result.segments == {"s0": POINTED}
        assert result.machine == []

    def test_a_ketiv_keeps_its_bare_word(self) -> None:
        """`מידע [מוֹדַע]` in Ruth 2:1 is bare on purpose — the one form tradition insists
        is unvowelled. A model filling it in would print an invention as the text."""
        ketiv = "וּֽלְנׇעֳמִי֙ מידע לְאִישָׁ֔הּ"
        result = vocalize_document(_document(ketiv), FakeEngine(), source="sefaria:Ruth")
        assert result.segments == {"s0": ketiv}

    def test_the_rule_is_not_the_call_site_s_to_keep(self) -> None:
        """`targum repair` builds an engine of its own, so a guard in the pipeline would
        be walked straight past. It lives in `vocalize_document`, which both callers use."""
        engine = FakeEngine()
        vocalize_document(_document(BARE), engine, source="sefaria:en:Genesis 1-11")
        assert engine.asked == []

    def test_everything_else_is_still_pointed(self) -> None:
        """The refusal is narrow. A news article is exactly as it was."""
        engine = FakeEngine()
        result = vocalize_document(_document(BARE), engine, source="https://example.com/news")
        assert engine.asked == ["s0"]
        assert result.machine == ["s0"]


class TestVocalizeDocument:
    def test_a_pointed_document_never_consults_the_engine(self) -> None:
        engine = FakeEngine()
        result = vocalize_document(_document(POINTED, POINTED), engine)
        assert engine.asked == []
        assert result.segments == {"s0": POINTED, "s1": POINTED}
        assert result.machine == []

    def test_a_pointed_document_needs_no_engine_at_all(self) -> None:
        result = vocalize_document(_document(POINTED))
        assert result.segments == {"s0": POINTED}
        assert result.vocalizer == "source"
        assert result.model is None

    def test_a_bare_document_with_no_engine_has_nothing_to_toggle(self) -> None:
        assert vocalize_document(_document(BARE)).segments == {}

    def test_the_engine_only_sees_segments_with_bare_words(self) -> None:
        engine = FakeEngine()
        vocalize_document(_document(POINTED, BARE, "משנה א מֵאֵימָתַי"), engine)
        assert engine.asked == ["s1", "s2"]

    def test_machine_lists_only_segments_the_engine_actually_pointed(self) -> None:
        engine = FakeEngine()
        result = vocalize_document(_document(POINTED, BARE), engine)
        assert result.machine == ["s1"]

    def test_a_mixed_segment_keeps_its_own_pointing_and_is_still_marked(self) -> None:
        engine = FakeEngine()
        result = vocalize_document(_document("משנה א מֵאֵימָתַי"), engine)
        assert "מֵאֵימָתַי" in result.segments["s0"]
        assert result.machine == ["s0"]

    def test_a_mangled_segment_falls_back_to_the_source_and_is_recorded(self) -> None:
        engine = FakeEngine(mangle={"s0"})
        result = vocalize_document(_document("בארץ־ישראל קם העם", BARE), engine)
        assert result.rejected == ["s0"]
        # The source had no nikkud of its own, so there is nothing to show for it...
        assert "s0" not in result.segments
        # ...and the rest of the document is untouched by the failure.
        assert "s1" in result.segments

    def test_a_rejection_never_costs_a_pointed_source_its_vowels(self) -> None:
        engine = FakeEngine(mangle={"s0"})
        result = vocalize_document(_document("אֶל־חלוני"), engine)
        assert result.rejected == ["s0"]
        assert result.segments["s0"] == "אֶל־חלוני"

    def test_every_stored_form_keeps_the_segment_skeleton(self) -> None:
        engine = FakeEngine()
        document = _document(POINTED, BARE, "משנה א מֵאֵימָתַי", "Magma Devs 1897")
        result = vocalize_document(document, engine)
        by_id = {segment.id: segment.text for segment in document.segments}
        for sid, text in result.segments.items():
            assert strip_nikkud(text)[0] == strip_nikkud(by_id[sid])[0]

    def test_it_records_which_engine_pointed_the_text(self) -> None:
        result = vocalize_document(_document(BARE), FakeEngine())
        assert (result.vocalizer, result.model) == ("fake/1", "fake-model")


def test_one_sentence_it_dislikes_does_not_cost_the_document_its_vowels() -> None:
    """Nakdimon raises bare AssertionErrors on input it dislikes, and the catch was
    around the whole call. One bad sentence in Judenstaat threw away the pointing for the
    other 1,079: the document came out 123 of 1,080 pointed — every one of those from
    pointing already in the source — and nothing said so.
    """
    import pathlib

    from targum.vocalize import nakdimon

    source = pathlib.Path(nakdimon.__file__).read_text(encoding="utf-8")
    body = source[source.index("def vocalize(") :]
    loop = body[body.index("for segment in segments:") : body.index("return out")]
    assert "try:" in loop and "except" in loop, "the guard belongs inside the loop"
    assert "failed += 1" in loop, "and a sentence that fails is counted, not silent"
