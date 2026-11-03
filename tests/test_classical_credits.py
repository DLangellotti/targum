"""The classical shelf as a scholar reads it (beta review 2026-11-03, AS-01 to AS-06).

Every text names its edition and every published rendering beside it, with the licence
linked (AS-01, AS-03); a weekly portion is headed with its own range and its name pointed
right (AS-02, AS-06); an aliyah is called an aliyah (AS-05); and the Tanakh, the targums,
the Mishnah and the Mishneh Torah each stand on a shelf of their own name (AS-04).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from targum import catalogue
from targum.catalogue import Entry, Kind, Rendering, Tag, shelf_of
from targum.models import Document, SegmentedDocument, Translation
from targum.parasha.build import own_blurb
from targum.parasha.calendar import ReadingKind, own_range, pointed_name
from targum.parasha.models import Portion
from targum.render import render
from targum.render.builder import (
    LICENCE_DEEDS,
    credited_entries,
    edition_credit,
    kind_page,
    layer_credits,
    licence_said,
    text_page,
)

TANACH_US = "http://www.tanach.us/Tanach.xml"
RASHI_PAGE = "https://www.sefaria.org/Rashi_on_Genesis"

GENESIS = Entry(
    id="genesis",
    title="בראשית",
    author="Torah · Genesis",
    language="he",
    source="sefaria:Genesis",
    blurb="The first book.",
    words=20000,
    tags=frozenset({Tag.tanakh}),
    kind=Kind.prose,
    licence="Public Domain",
    credit="Tanach with Ta'amei Hamikra, via Sefaria",
    licence_url=TANACH_US,
    translations=[
        Rendering(
            name="Metsudah Chumash, Metsudah Publications, 2009",
            source="sefaria:en:Genesis",
            publisher="Metsudah Publications",
            licence="CC-BY",
        ),
        Rendering(
            name="Targum Onkelos",
            source="sefaria:arc:Genesis",
            publisher="Sefaria",
            licence="Public Domain",
        ),
        Rendering(
            name="Rashi Chumash, Metsudah Publications, 2009",
            source="sefaria:Rashi on Genesis",
            publisher="Metsudah Publications",
            licence="CC-BY",
            licence_url=RASHI_PAGE,
        ),
        Rendering(
            name="Rashi Chumash, Metsudah Publications, 2009",
            source="sefaria:en:Rashi on Genesis",
            publisher="Metsudah Publications",
            licence="CC-BY",
            licence_url=RASHI_PAGE,
        ),
    ],
)

#: A portion's row, as `parasha entries` writes it: the Hebrew credited, no renderings.
CHAYEI_SARA = Entry(
    id="parasha-chayei-sara",
    title="חַיֵּי שָׂרָה",
    author="בראשית",
    language="he",
    source="sefaria:Genesis 23:1-25:18",
    blurb="Genesis 23:1-25:18. 105 verses, seven aliyot.",
    words=1214,
    tags=frozenset({Tag.tanakh}),
    kind=Kind.prose,
    licence="Public Domain",
    credit="Tanach with Ta'amei Hamikra, via Sefaria",
    licence_url=TANACH_US,
)

SIDDUR = Entry(
    id="siddur-shacharit",
    title="תפילת שחרית",
    author="סידור נוסח אשכנז",
    language="he",
    source="siddur:Weekday, Shacharit",
    blurb="The weekday morning service.",
    words=15018,
    kind=Kind.liturgy,
    licence="CC-BY",
    credit="The Metsudah siddur, 1981, via Sefaria",
    licence_url="https://www.nli.org.il/he/books/NNL_ALEPH002211687",
)


@pytest.fixture
def shelf(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(catalogue, "CATALOGUE", [GENESIS, CHAYEI_SARA, SIDDUR])


def rendering(name: str, target: str, segmented: SegmentedDocument) -> Translation:
    return Translation(
        name=name,
        document_hash=segmented.document_hash,
        source_language="he",
        target_language=target,
        provider="aligned",
        segments={s.id: f"[{target}] {s.text}" for s in segmented.segments},
    )


# -- AS-01, AS-03: credits --------------------------------------------------------


def test_a_cc_by_licence_links_its_deed_and_public_domain_links_nothing() -> None:
    assert licence_said("CC-BY") == ("CC-BY", LICENCE_DEEDS["cc by"])
    assert licence_said("CC BY 4.0")[1] == "https://creativecommons.org/licenses/by/4.0/"
    assert licence_said("CC BY-SA 3.0")[1] == "https://creativecommons.org/licenses/by-sa/3.0/"
    assert licence_said("Public Domain") == ("Public Domain", "")
    assert licence_said("Public Domain", TANACH_US) == ("Public Domain", TANACH_US)


def test_a_portion_and_a_haftarah_are_credited_from_the_book_they_were_cut_from(
    shelf: None,
) -> None:
    """A portion's row names the Hebrew and carries no renderings; a haftarah has no row.
    Both carry the book's English, Onkelos and Rashi, so the book credits those."""
    named, carried = credited_entries("sefaria:Genesis 23:1-25:18")
    assert named is CHAYEI_SARA and carried is GENESIS
    named, carried = credited_entries("sefaria:Genesis 41:1-44:17")
    assert named is GENESIS and carried is GENESIS
    assert credited_entries("sefaria:Genesis") == (GENESIS, GENESIS)
    assert credited_entries("memory") == (None, None)


def test_every_rendering_beside_a_verse_is_credited_with_its_licence(
    shelf: None, segmented: SegmentedDocument
) -> None:
    """The Metsudah Rashi is CC BY and was shown on every aliyah with no credit."""
    carried = [
        rendering("Genesis", "en", segmented),
        rendering("Onkelos Genesis", "arc", segmented),
        rendering("Rashi on Genesis", "he", segmented),
        rendering("Rashi on Genesis", "en", segmented),
    ]
    lines = layer_credits(GENESIS, carried, "he", linked=False)
    assert [line.label for line in lines] == ["English", "Onkelos", "Rashi", "Rashi · English"]
    assert lines[0].name == "Metsudah Chumash, Metsudah Publications, 2009"
    assert lines[1].name == "Targum Onkelos, Sefaria"
    assert lines[2].licence == "CC-BY" and lines[2].deed == LICENCE_DEEDS["cc by"]
    assert all(line.href == "" for line in lines), "a reader links no page of its own"
    assert layer_credits(GENESIS, carried, "he")[2].href == RASHI_PAGE


def test_a_reader_names_its_edition_and_renderings_in_its_foot(
    shelf: None, tmp_path: Path, segmented: SegmentedDocument
) -> None:
    document = Document(
        source="sefaria:Genesis 23:1-25:18",
        title="חַיֵּי שָׂרָה",
        language="he",
        blocks=[],
        content_hash="abc123",
    )
    page = render(document, segmented, [rendering("Genesis", "en", segmented)], tmp_path / "r")
    html = page[-1].read_text(encoding="utf-8")
    foot = html[html.index('id="credits"') :]
    assert "Hebrew from Tanach with Ta&#39;amei Hamikra, via Sefaria · Public Domain" in foot
    assert "English from Metsudah Chumash, Metsudah Publications, 2009 · " in foot
    assert f'<a href="{LICENCE_DEEDS["cc by"]}" rel="noopener">CC-BY</a>' in foot
    # Only a deed: the pinned allowlist holds (`test_render.py`).
    for match in re.finditer(r"https?://[^\s\"'\\)]+", html):
        assert TANACH_US not in match.group(0)


def test_the_siddur_credits_its_cc_by_hebrew(shelf: None) -> None:
    line = edition_credit(SIDDUR)
    assert line is not None
    assert (line.label, line.name, line.licence) == (
        "Hebrew",
        "The Metsudah siddur, 1981, via Sefaria",
        "CC-BY",
    )
    assert line.deed == LICENCE_DEEDS["cc by"]


def test_a_library_page_names_the_edition_before_the_translation(shelf: None) -> None:
    html = text_page(GENESIS, "https://targum.page")
    edition = html.index('class="provenance edition"')
    assert edition < html.index("<h2>Translation</h2>")
    assert f'<a href="{TANACH_US}" rel="noopener">Tanach with Ta&#39;amei Hamikra' in html
    # And what the readers set beside the verse, each with its licence.
    beside = html[html.index('class="provenance beside"') :]
    assert "<b>Onkelos</b>" in beside and "<b>Rashi · English</b>" in beside
    assert f'href="{LICENCE_DEEDS["cc by"]}"' in beside


def test_a_portions_library_page_credits_the_books_translation(shelf: None) -> None:
    html = text_page(CHAYEI_SARA, "https://targum.page")
    assert "Metsudah Chumash" in html and "<b>Rashi</b>" in html
    assert "Tanach with Ta&#39;amei Hamikra" in html


# -- AS-02, AS-06: a portion as itself -------------------------------------------


@pytest.mark.parametrize(
    ("hebcal", "own"),
    [
        ("Genesis 37:1-40:23; Numbers 7:1-17", "Genesis 37:1-40:23"),
        ("Exodus 21:1-24:18, 30:11-16", "Exodus 21:1-24:18"),
        ("Exodus 30:11-34:35; Numbers 19:1-22", "Exodus 30:11-34:35"),
        ("Exodus 27:20-30:10; Deuteronomy 25:17-19", "Exodus 27:20-30:10"),
        ("Leviticus 19:1-20:27; Numbers 28:9-15", "Leviticus 19:1-20:27"),
        ("Exodus 35:1-40:38, 12:1-20", "Exodus 35:1-40:38"),
        ("Genesis 23:1-25:18", "Genesis 23:1-25:18"),
    ],
)
def test_a_portion_is_headed_with_its_own_range(hebcal: str, own: str) -> None:
    assert own_range(hebcal) == own


def test_a_stored_portion_is_put_right_as_it_is_read() -> None:
    """An index cut before the fix still says the right thing, without a re-cut."""
    portion = Portion(
        slug="vayeshev",
        name="Vayeshev",
        hebrew="וַיֵּשֶׁב",
        numbers=[9],
        summary="Genesis 37:1-40:23; Numbers 7:1-17",
    )
    assert portion.summary == "Genesis 37:1-40:23"
    festival = Portion(
        slug="pesach-i-on-shabbat",
        name="Pesach I",
        hebrew="פֶּסַח",
        kind=ReadingKind.festival,
        summary="Exodus 12:21-51; Numbers 28:16-25",
    )
    assert festival.summary == "Exodus 12:21-51; Numbers 28:16-25", "a festival reads both"


def test_a_blurb_loses_the_special_maftir_in_any_language() -> None:
    assert own_blurb("Genesis 37:1-40:23; Numbers 7:1-17. 112 verses, seven aliyot.") == (
        "Genesis 37:1-40:23. 112 verses, seven aliyot."
    )
    assert own_blurb("Исход 21:1-24:18, 30:11-16. 118 стихов, семь алий.") == (
        "Исход 21:1-24:18. 118 стихов, семь алий."
    )


def test_portion_names_are_pointed_as_headings() -> None:
    hebcal = {
        5: "חַיֵּי שָֹרָה",
        26: "שְּׁמִינִי",
        35: "נָשׂא",
        23: "פְקוּדֵי",
        27: "תַזְרִיעַ",
    }
    fixed = {number: pointed_name([number], name) for number, name in hebcal.items()}
    assert "ֹ" not in fixed[5].split(" ")[1][:3], "no holam on the sin"
    assert "ׂ" in fixed[5], "the sin dot"
    assert not fixed[26].startswith("שְּ"), "no dagesh in an initial shin"
    assert "ֹ" in fixed[35], "נָשֹׂא has its holam"
    assert fixed[23][1:3] == "ְּ" and fixed[27][1:3] == "ַּ", "dagesh lene"
    doubled = pointed_name([22, 23], "וַיַּקְהֵל־פְקוּדֵי")
    assert doubled == "וַיַּקְהֵל־" + fixed[23]
    assert pointed_name([1], "בְּרֵאשִׁית") == "בְּרֵאשִׁית", "Hebcal's own where it is right"


# -- AS-04: shelves ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("kind", "source", "language", "tanakh", "shelf"),
    [
        ("prose", "sefaria:Mishnah Berakhot", "he", False, "mishnah"),
        ("prose", "sefaria:Pirkei Avot", "he", False, "mishnah"),
        ("prose", "sefaria:Mishneh Torah, Foundations of the Torah", "he", False, "halakhah"),
        ("poetry", "sefaria:Psalms", "he", True, "tanakh"),
        ("poetry", "sefaria:Isaiah", "he", True, "tanakh"),
        ("prose", "sefaria:arc:Genesis", "arc", True, "targum"),
        ("prose", "sefaria:Genesis", "he", False, "tanakh"),
        ("prose", "sefaria:Rashi on Genesis", "he", False, "prose"),
        ("poetry", "wikisource:Bialik", "he", False, "poetry"),
        ("story", "storyweaver:7686", "it", False, "story"),
    ],
)
def test_each_collection_stands_on_its_own_shelf(
    kind: str, source: str, language: str, tanakh: bool, shelf: str
) -> None:
    assert shelf_of(kind, source, language, tanakh=tanakh) == shelf


def test_the_old_tanakh_address_still_answers(shelf: None) -> None:
    html = kind_page("he", "prose", "https://targum.page")
    assert html is not None and "Tanakh" in html


# -- AS-05: an aliyah is an aliyah ------------------------------------------------


def test_an_aliyah_is_called_an_aliyah(tmp_path: Path) -> None:
    """ "Chayei Sara · Chapter 1 of 7" over Genesis 23: the unit was the aliyah."""
    from test_render import heading, make_segmented, paragraph

    from targum.models import Block, BlockKind

    segmented = make_segmented(
        [heading(0, 1, "ראשון"), paragraph(1), heading(2, 1, "שני"), paragraph(3)]
    )
    head = Block(id="aliyah-01", kind=BlockKind.heading, level=2, text="ראשון")
    portion = Document(
        source="sefaria:Genesis 23:1-25:18",
        title="חַיֵּי שָׂרָה",
        language="he",
        blocks=[head],
        content_hash="p1",
        ingester="parasha/1",
    )
    english = rendering("Genesis", "en", segmented)
    html = render(portion, segmented, [english], tmp_path / "p")[1].read_text(encoding="utf-8")
    assert "End of aliyah 1 of 2" in html and "End of chapter" not in html

    book = portion.model_copy(update={"blocks": [], "source": "memory"})
    html = render(book, segmented, [english], tmp_path / "b")[1].read_text(encoding="utf-8")
    assert "End of chapter 1 of 2" in html
