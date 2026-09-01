"""Tanakh from Sefaria, and the pairing that costs nothing.

Scripture is numbered by verse and its published translations are numbered the same way,
so the correspondence is stated rather than inferred. Everything here defends that: the
verse stays one unit, the licence is checked rather than assumed, and a disagreement
between the two sides stops the build instead of quietly mispairing scripture.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from targum.align import parallel
from targum.errors import TargumError
from targum.ingest.fetch import sefaria
from targum.models import BlockKind, is_biblical
from targum.segment import segment_document
from targum.vocalize.base import is_fully_pointed, wants_pointing

FIXTURES = Path(__file__).parent / "fixtures" / "sefaria"


def payload(language: str) -> dict[str, Any]:
    body = json.loads((FIXTURES / f"ruth.{language}.json").read_text(encoding="utf-8"))
    return {"edition": body["versions"][0], "body": body}


def document(language: str) -> Any:
    return sefaria.document_from_payload(payload(language), "Ruth", language)


# -- reading what Sefaria sends ----------------------------------------------


def test_a_book_comes_back_as_chapters_of_verses() -> None:
    for language, chapters, verses in (("he", 4, 85), ("en", 4, 85)):
        blocks = document(language).blocks
        assert sum(1 for b in blocks if b.kind is BlockKind.heading) == chapters
        assert sum(1 for b in blocks if b.kind is BlockKind.verse) == verses


def test_both_sides_count_the_same() -> None:
    """The whole basis on which a Tanakh pairs for nothing."""
    he = [b for b in document("he").blocks if b.kind is BlockKind.verse]
    en = [b for b in document("en").blocks if b.kind is BlockKind.verse]
    assert len(he) == len(en)


def test_chapters_are_numbered_in_the_language_they_are_in() -> None:
    """A Latin digit inside a Hebrew heading is the bidi mess `isolate()` exists for."""
    heads = [b.text for b in document("he").blocks if b.kind is BlockKind.heading]
    assert heads == ["רות א׳", "רות ב׳", "רות ג׳", "רות ד׳"]
    latin = [b.text for b in document("en").blocks if b.kind is BlockKind.heading]
    assert latin == ["Ruth 1", "Ruth 2", "Ruth 3", "Ruth 4"]


def test_no_markup_reaches_the_text() -> None:
    """Metsudah carries HTML where the Hebrew does not — 214 tags in Genesis alone."""
    for language in ("he", "en"):
        for block in document(language).blocks:
            assert "<" not in block.text and ">" not in block.text


@pytest.mark.parametrize(
    ("number", "written"),
    [(1, "א׳"), (5, "ה׳"), (11, "י״א"), (15, "ט״ו"), (16, "ט״ז"), (20, "כ׳"), (150, "ק״נ")],
)
def test_hebrew_numerals(number: int, written: str) -> None:
    """Fifteen and sixteen are ט״ו and ט״ז, never י״ה or י״ו, which spell the Name."""
    assert sefaria.hebrew_numeral(number) == written


@pytest.mark.parametrize(
    ("identifier", "expected"),
    [
        ("Ruth", ("he", "Ruth")),
        ("en:Ruth", ("en", "Ruth")),
        ("sefaria:Ruth", ("he", "Ruth")),
        ("sefaria:en:Ruth", ("en", "Ruth")),
        ("Genesis 1-11", ("he", "Genesis 1-11")),
        ("I_Samuel", ("he", "I Samuel")),
    ],
)
def test_identifiers(identifier: str, expected: tuple[str, str]) -> None:
    assert sefaria.split_ref(identifier) == expected


def test_the_registry_knows_the_scheme() -> None:
    from targum.ingest import fetch

    assert fetch.is_identifier("sefaria:Ruth")
    assert not fetch.is_identifier("sefaria:")


# -- what is refused ----------------------------------------------------------


def test_a_noncommercial_edition_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    """The trap this exists for.

    `Metsudah Chumash, Metsudah Publications, 2009` is CC-BY; `… 2009 [with Onkelos
    translation]` is CC-BY-NC, which a paid product may not use. They differ by a
    bracketed suffix, so the licence is asserted rather than the name trusted.
    """
    body = json.loads((FIXTURES / "ruth.en.json").read_text(encoding="utf-8"))
    body["versions"][0]["license"] = "CC-BY-NC"
    monkeypatch.setattr(sefaria, "get", lambda url: json.dumps(body))
    with pytest.raises(TargumError, match="may not serve"):
        sefaria.SefariaFetcher().load("en:Ruth")


def test_pd_is_public_domain_by_another_name(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sefaria spells public domain two ways and means the same by both.

    Surveyed across twelve works, 85 editions said "Public Domain" and 5 said "PD" — and
    those five carry the only modern-Hebrew Tanakh on the shelf and the Kaufmann Mishnah.
    A set that knows one spelling refuses a free text over a typo, so both are in it.
    """
    body = json.loads((FIXTURES / "ruth.he.json").read_text(encoding="utf-8"))
    body["versions"][0]["license"] = "PD"
    monkeypatch.setattr(sefaria, "get", lambda url: json.dumps(body))
    document = sefaria.SefariaFetcher().load("Ruth")
    assert document.blocks, "a PD edition is public domain and must be served"


def test_sharealike_stays_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    """A decision, not an oversight.

    ShareAlike permits commercial use, so the CC-BY-NC reasoning does not reach it — but a
    build makes derivatives and ShareAlike would carry onto them. Refusing it costs the
    Ibn Tibbon Kuzari and the Wikisource Mishneh Torah, not the Talmud: that is Aramaic,
    and `he` on a Sefaria version means Hebrew script rather than Hebrew. Change this test
    only when the ShareAlike trade is made deliberately.
    """
    body = json.loads((FIXTURES / "ruth.he.json").read_text(encoding="utf-8"))
    body["versions"][0]["license"] = "CC-BY-SA"
    monkeypatch.setattr(sefaria, "get", lambda url: json.dumps(body))
    with pytest.raises(TargumError, match="may not serve"):
        sefaria.SefariaFetcher().load("Ruth")


def test_a_missing_edition_says_what_is_on_offer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        sefaria,
        "get",
        lambda url: json.dumps({"versions": [], "available_versions": [{"versionTitle": "Other"}]}),
    )
    with pytest.raises(TargumError, match="has no"):
        sefaria.SefariaFetcher().load("Ruth")


def test_a_shape_this_does_not_read_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    """Talmud and the commentaries are shaped differently; a wrong shape would put
    headings over the wrong things rather than fail."""
    body = json.loads((FIXTURES / "ruth.he.json").read_text(encoding="utf-8"))
    body["textDepth"] = 3
    monkeypatch.setattr(sefaria, "get", lambda url: json.dumps(body))
    with pytest.raises(TargumError, match="chapters-and-verses"):
        sefaria.SefariaFetcher().load("Ruth")


def test_a_book_with_no_chosen_english_is_refused() -> None:
    """Every text on the shelf names the edition its English comes from, and one that
    names none is refused rather than quietly missing from a list.

    The example has moved twice, which is the point of writing it down. It was Jonah
    while Jonah's only Orthodox English was CC-BY-NC; it became Jeremiah when Jonah went
    on the shelf in JPS 1917; and Jeremiah went on the same way on 2026-09-01, with the
    eight other books that finished the Tanakh. So there is no book of the Tanakh left to
    use, and the example is a text outside it — which is what the refusal is really for
    now. The licence stopped deciding this a while ago: JPS is public domain and covers
    every book. The choosing is editorial.
    """
    with pytest.raises(TargumError, match="no English edition"):
        sefaria.version_for("en", "Zohar")


def test_every_book_of_the_tanakh_now_names_one() -> None:
    """Thirty-nine, which is all of them as Sefaria divides them. Nach Yomi reads a
    chapter of the Prophets and the Writings every day and walks all thirty-four of
    those, so a gap anywhere in them is a daily page that stops."""
    assert len(sefaria.ENGLISH) == 39
    for book in ("Jeremiah", "Ezekiel", "Hosea", "Micah", "Nehemiah", "II Chronicles"):
        assert sefaria.version_for("en", book)


# -- works that are not Tanakh ------------------------------------------------


def test_a_work_beyond_the_tanakh_pins_both_its_sides() -> None:
    """The Tanakh has one Hebrew edition and this does not.

    `HEBREW` is a constant because one edition covers all twenty-four books. Nothing
    outside the Tanakh is like that — the Mishneh Torah's Hebrew is Torat Emet 363 for
    most sections and 370 for two of them — so both sides are pinned per text.
    """
    assert sefaria.version_for("he", "Mishneh Torah, Repentance") == "Torat Emet 363"
    assert sefaria.version_for("he", "Mishneh Torah, Reading the Shema") == "Torat Emet 370"
    assert "Glazer" in sefaria.version_for("en", "Mishneh Torah, Repentance")


def test_a_reference_with_a_part_number_still_finds_its_edition() -> None:
    """`Kuzari 1` is the first ma'amar; the edition is the Kuzari's."""
    assert sefaria.version_for("en", "Kuzari 1") == sefaria.version_for("en", "Kuzari 5")


def test_the_hebrew_kuzari_is_not_taken_from_sefaria() -> None:
    """The one side of the shelf that ShareAlike actually costs.

    Sefaria's Ibn Tibbon is Project Ben-Yehuda's and CC-BY-SA, and the Even Shmuel is a
    1973 translation Sefaria will not name a licence for. The vocalized Zifroni text of
    the same Ibn Tibbon is on Hebrew Wikisource, so the refusal points there rather than
    reading as "targum does not have the Kuzari".
    """
    with pytest.raises(TargumError, match="no hebrew edition") as caught:
        sefaria.version_for("he", "Kuzari 1")
    assert "wikisource" in (caught.value.hint or "").lower()


def test_every_pinned_english_edition_is_named() -> None:
    """A half-filled row would fail at fetch time with a confusing message."""
    for name, pair in sefaria.BEYOND_TANAKH.items():
        assert pair.english, f"{name} names no English edition"


def test_nothing_beyond_the_tanakh_is_treated_as_scripture() -> None:
    """`sefaria:` stopped meaning the Tanakh, and four places in the code read it.

    Scripture's words are banded against a table counted from the Tanakh itself. Banding
    the Mishneh Torah against it would hand a reader an unrated word wherever a rabbinic
    one appears, which on that shelf is where it matters most. This is what binds
    `models.BEYOND_SCRIPTURE` to `BEYOND_TANAKH`: add a work to one and forget the other,
    and this fails rather than quietly calling it scripture.
    """
    for name in sefaria.BEYOND_TANAKH:
        assert not is_biblical(f"sefaria:{name}"), name
        assert not is_biblical(f"sefaria:en:{name}"), name


def test_the_tanakh_is_still_scripture() -> None:
    """However it is addressed — a book, a range, a side."""
    for source in (
        "sefaria:Ruth",
        "sefaria:en:Ruth",
        "sefaria:Genesis 1-11",
        # What `parasha/cut.py` writes: Hebcal's own range line, which carries a colon.
        "sefaria:Deuteronomy 29:9-31:30",
    ):
        assert is_biblical(source), source


def test_the_mishnah_is_pinned_once_rather_than_sixty_three_times() -> None:
    """One pair of editions covers the whole work, so a row per tractate would be
    sixty-three chances to mistype a version title that is the same on all of them."""
    for ref in ("Mishnah Berakhot", "Mishnah Kelim", "Mishnah Bikkurim 1-3"):
        assert sefaria.version_for("he", ref) == "Torat Emet 357"
        assert sefaria.version_for("en", ref) == "Mishnah Yomit by Dr. Joshua Kulp"


def test_the_one_tractate_that_is_not_called_mishnah_something() -> None:
    """Sefaria files Avot under its own name, and it is the most read of the sixty-three:
    a prefix rule that missed it would miss the one that matters."""
    assert sefaria.is_mishnah("Pirkei Avot")
    assert sefaria.version_for("he", "Pirkei Avot") == "Torat Emet 357"


@pytest.mark.parametrize(
    "book",
    [
        # A word apart, and two works six hundred years apart.
        "Mishneh Torah, Repentance",
        # A commentary on a tractate is not the tractate.
        "Bartenura on Mishnah Berakhot",
        "Genesis",
    ],
)
def test_what_the_mishnah_rule_does_not_reach(book: str) -> None:
    assert not sefaria.is_mishnah(book)


def test_a_hebrew_chapter_range_is_not_part_of_the_book_s_name() -> None:
    """`heRef` for a ranged reference comes back as `משנה ביכורים א׳-ג׳`, and a heading
    built on that reads "משנה ביכורים א׳-ג׳ א׳"."""
    assert sefaria.book_of("משנה ביכורים א׳-ג׳") == "משנה ביכורים"
    assert sefaria.book_of("בראשית א׳-י״א") == "בראשית"


def test_a_book_whose_name_ends_in_a_letter_keeps_it() -> None:
    """`שמואל א` is the name of a book of the Tanakh and its last word is not a chapter
    number. Only a range — which has a hyphen in it — is ever taken off."""
    assert sefaria.book_of("שמואל א") == "שמואל א"
    assert sefaria.book_of("מלכים ב") == "מלכים ב"
    assert sefaria.book_of("רות") == "רות"


def test_a_footnote_is_dropped_rather_than_glued_into_the_sentence() -> None:
    """Metsudah's siddur prints its commentary inline, and it is three times the prayer.

    Stripping tags and keeping what is between them — which is what every other edition
    on this shelf wants — puts a paragraph of Avudraham in the middle of the blessing.
    """
    raw = (
        'Blessed<sup class="footnote-marker">1</sup>'
        '<i class="footnote">The word is similar to <i>merciful</i>.—<i>Avudraham</i></i>'
        " are You, Adonoy"
    )
    assert sefaria.plain(raw) == "Blessed are You, Adonoy"


def test_an_edition_with_no_apparatus_is_left_exactly_as_it_was() -> None:
    """The Tanakh carries no footnotes, and must not start round-tripping through a
    parser that could normalise something."""
    assert sefaria.plain("In the <b>beginning</b>") == "In the beginning"
    assert sefaria.plain("א[ב]ג") == "א[ב]ג"


# -- the verse stays one unit -------------------------------------------------


class _AlwaysSplits:
    """Cuts every text it is given in half.

    Deliberately brutal. A segmenter that splits on full stops would leave Hebrew verses
    alone — they end in sof pasuq — and the test would pass without proving anything.
    """

    name = "always-splits/1"

    def split(self, texts: list[str], language: str) -> list[list[str]]:
        return [[text[: len(text) // 2], text[len(text) // 2 :]] for text in texts]


def test_a_verse_is_never_split() -> None:
    """Let the segmenter cut one verse in two and the 1:1 correspondence is gone —
    along with the only reason a Tanakh pairs for nothing."""
    segmented = segment_document(document("he"), _AlwaysSplits())
    verses = [s for s in segmented.segments if s.kind is BlockKind.verse]
    assert len(verses) == 85, "a verse was split"

    # And the guard is doing the work: this segmenter really does cut anything it is
    # allowed to. Without that check the test would pass on a segmenter that split
    # nothing, and prove nothing.
    from targum.models import Block, Document

    ordinary = Document(
        source="x",
        language="he",
        blocks=[Block(id="b1", kind=BlockKind.paragraph, text="אחת שתיים שלוש ארבע")],
    )
    cut = segment_document(ordinary, _AlwaysSplits())
    assert len(cut.segments) == 2, "the segmenter is not splitting, so the test is empty"


# -- the edition -------------------------------------------------------------


def test_the_hebrew_is_the_accented_edition() -> None:
    """`Tanach with Nikkud` is not an edition; it is this one with the accents deleted
    by machine, and that delete is lossy. Pinned here so the shorter name cannot creep
    back in as a simplification."""
    assert sefaria.HEBREW == "Tanach with Ta'amei Hamikra"


def test_the_edition_carries_its_accents() -> None:
    """Every test below about the trope is vacuous on an unaccented fixture, so the
    fixture is checked rather than trusted."""
    text = "".join(verse for chapter in payload("he")["edition"]["text"] for verse in chapter)
    assert any(0x0591 <= ord(char) <= 0x05AF for char in text), "no accents in the fixture"


def test_no_meteg_was_lost_on_the_way_in() -> None:
    """The bug this edition exists to undo, held as a number.

    Unicode gives meteg and silluq one codepoint, so a program stripping accents takes
    the metagim with them — and meteg is what separates a qamats gadol from a qamats
    qatan. The accent-stripped edition has none at all in the whole of Ruth.
    """
    document = sefaria.document_from_payload(payload("he"), "Ruth", "he")
    text = "".join(block.text for block in document.blocks)
    assert text.count("\u05bd") > 100, "the accented edition lost its metagim"


def test_both_sides_of_the_shelf_count_their_verses_the_same() -> None:
    """`parallel.pair` matches by position inside a chapter, so an edition that numbered
    its verses differently would shift the pairing of a whole book without saying so."""
    hebrew = [len(chapter) for chapter in payload("he")["edition"]["text"]]
    english = [len(chapter) for chapter in payload("en")["edition"]["text"]]
    assert hebrew == english


# -- pointing -----------------------------------------------------------------


def test_the_source_keeps_its_own_pointing() -> None:
    """A Tanakh is published pointed. Nothing here should want a model."""
    segmented = segment_document(document("he"), _WholeBlocks())
    assert not wants_pointing(segmented.segments)


def test_ketiv_and_qere_are_not_treated_as_missing_vowels() -> None:
    """The Masoretic text carries a written form left deliberately consonantal beside
    the pointed form it is read as — `מידע [מוֹדַע]` at Ruth 2:1.

    Counting those as gaps would have a diacritizer invent vowels for the one form
    tradition insists is unvowelled, and print the guess as if it were the text.
    """
    segmented = segment_document(document("he"), _WholeBlocks())
    prose = [s for s in segmented.segments if s.kind is BlockKind.verse]
    bare = [s for s in prose if not is_fully_pointed(s.text)]
    assert bare, "Ruth carries ketiv/qere; this test is pointless without it"
    assert len(bare) / len(prose) < 0.5
    assert not wants_pointing(segmented.segments)


# -- pairing ------------------------------------------------------------------


def test_two_sides_of_one_book_claim_each_other() -> None:
    assert parallel.parallel_key(document("he")) == parallel.parallel_key(document("en"))


def test_nothing_else_claims_parallelism() -> None:
    """Declared, never inferred. Two unrelated texts that happen to line up must not
    be paired silently, and silence is the failure that matters on scripture."""

    class Elsewhere:
        source = "wikisource:he:something"
        ingester = "wikisource/1"

    assert parallel.parallel_key(Elsewhere()) is None


def test_different_ranges_do_not_pair() -> None:
    class Ref:
        def __init__(self, source: str) -> None:
            self.source, self.ingester = source, "sefaria/1"

    assert parallel.parallel_key(Ref("sefaria:Genesis")) != parallel.parallel_key(
        Ref("sefaria:en:Genesis 1-11")
    )


def test_the_pairing_is_one_to_one_at_full_confidence() -> None:
    source = segment_document(document("he"), _WholeBlocks())
    target = segment_document(document("en"), _WholeBlocks())
    alignment = parallel.pair(source, target, "Ruth")

    assert alignment.aligner == "parallel/1", "the artifact must not claim LaBSE made it"
    assert alignment.coverage() == 1.0
    assert len(alignment.links) == len(source.segments)
    assert all(len(link.source) == 1 and len(link.target) == 1 for link in alignment.links)
    assert all(link.confidence == 1.0 and not link.coarse for link in alignment.links)
    assert alignment.length_ratio > 1, "descriptive, but it should be real"


def test_a_translation_may_stop_short_of_a_chapter() -> None:
    """Silverstein's Psalm 82 has seven verses to the Hebrew's eight, and 82:8 has no
    English at all. One missing verse should not cost the shelf a hundred and fifty
    psalms.

    Safe only because of how Sefaria writes a gap: a verse it has no text for in the
    middle of a chapter is an empty string *in place* — Psalms 30:7, 41:9 and 73:5 are
    all like that — so a genuinely shorter chapter is the end falling off, and the end
    falling off shifts nothing before it.
    """
    source = segment_document(document("he"), _WholeBlocks())
    target = segment_document(document("en"), _WholeBlocks())
    object.__setattr__(target, "segments", target.segments[:-1])

    alignment = parallel.pair(source, target, "Ruth")
    orphans = [link for link in alignment.links if not link.target]
    assert len(orphans) == 1, "the untranslated verse should be recorded, not dropped"
    assert orphans[0].source == [source.segments[-1].id]
    assert alignment.coverage() < 1.0, "and coverage should say so"


def test_everything_before_a_gap_is_still_paired_correctly() -> None:
    """The property that makes the allowance safe at all.

    A gap that shifted the verses after it would be far worse than a missing verse: it
    would put the wrong English under Hebrew, silently, forever.
    """
    source = segment_document(document("he"), _WholeBlocks())
    target = segment_document(document("en"), _WholeBlocks())
    whole = {
        link.source[0]: link.target[0]
        for link in parallel.pair(source, target, "Ruth").links
        if link.target
    }

    object.__setattr__(target, "segments", target.segments[:-1])
    gapped = {
        link.source[0]: link.target[0]
        for link in parallel.pair(source, target, "Ruth").links
        if link.target
    }
    assert gapped == {k: v for k, v in whole.items() if k in gapped}


def test_a_chapter_count_disagreement_stops_the_build() -> None:
    """Pairing chapter n against chapter n+1 would be a quiet, durable mistranslation of
    scripture. Refusing to build is the smaller harm by a long way."""
    source = segment_document(document("he"), _WholeBlocks())
    target = segment_document(document("en"), _WholeBlocks())
    trimmed = [s for s in target.segments if not s.text.startswith("Ruth 4")]
    object.__setattr__(target, "segments", trimmed[: trimmed.index(trimmed[-1])])
    with pytest.raises(TargumError, match="chapters against"):
        parallel.pair(source, target, "Ruth")


def test_a_translation_with_more_verses_than_the_text_is_refused() -> None:
    """Not a gap but a different numbering, and pairing through it would misalign the
    rest of the chapter."""
    source = segment_document(document("he"), _WholeBlocks())
    target = segment_document(document("en"), _WholeBlocks())
    object.__setattr__(source, "segments", source.segments[:-1])
    with pytest.raises(TargumError, match="23 units to 22 in the source"):
        parallel.pair(source, target, "Ruth")


def test_a_sefaria_build_is_shared_between_readers() -> None:
    """Without this every Tanakh is cached per person and the second reader pays."""
    from targum.pipeline import Build

    assert "sefaria:" in Build.PUBLIC_SOURCES


class _WholeBlocks:
    """A segmenter that keeps every block whole, so these tests need no Stanza."""

    name = "whole/1"

    def split(self, texts: list[str], language: str) -> list[list[str]]:
        return [[text] for text in texts]
