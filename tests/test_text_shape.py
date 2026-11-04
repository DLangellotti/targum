"""A text in the shape its edition gives it (design.md §12, "A text keeps the shape its
edition gives it", 2026-11-04): numbers in the text's letters, a chapter named as a
chapter, parashot closed where the scribe closed them, half-lines in the poetic books.

The rule under every test here: shape is markup around the text, never a change to it.
A word's offsets are counted in characters, so a page whose text says one character more
or less is a page whose cards open on the wrong word.
"""

from __future__ import annotations

import re
from html import unescape
from pathlib import Path

from targum.models import BlockKind, Document, Segment, SegmentedDocument, Translation
from targum.render import isolate, render, shape

ETNACHTA = "֑"


def verse(n: int, text: str, ref: str, block: int | None = None) -> Segment:
    return Segment(
        id=f"{n:04d}.000-aaaaaa",
        block_id=f"b{(block if block is not None else n):04d}",
        block_index=n,
        index=0,
        kind=BlockKind.verse,
        text=text,
        ref=ref,
    )


def head(n: int, text: str) -> Segment:
    return Segment(
        id=f"{n:04d}.000-hhhhhh",
        block_id=f"b{n:04d}",
        block_index=n,
        index=0,
        kind=BlockKind.heading,
        level=2,
        text=text,
    )


def built(tmp_path: Path, title: str, segments: list[Segment], english: dict[str, str]) -> str:
    segmented = SegmentedDocument(
        document_hash="h", language="he", segmenter="fake/1", segments=segments
    )
    document = Document(source="sefaria:Test", title=title, language="he", blocks=[])
    translation = Translation(
        name="English",
        document_hash="h",
        source_language="he",
        target_language="en",
        provider="sefaria",
        segments=english,
    )
    pages = render(document, segmented, [translation], tmp_path / "reader")
    return pages[0].read_text(encoding="utf-8")


def visible_text(html: str, sid: str) -> str:
    """The plain cell's text for one row, as the page's script reads it: textContent."""
    found = re.search(
        rf'data-id="{re.escape(sid)}".*?<p class="src plain"[^>]*>(.*?)</p>', html, re.S
    )
    assert found, sid
    return unescape(re.sub(r"<[^>]+>", "", found.group(1)))


# --- the pieces ------------------------------------------------------------------------


def test_a_verse_is_numbered_in_letters_where_the_text_is_written_in_them() -> None:
    assert shape.verse_label("2:1", letters=True) == "א׳"
    assert shape.verse_label("2:15", letters=True) == "ט״ו"
    assert shape.verse_label("2:16", letters=True) == "ט״ז"
    assert shape.verse_label("2:12", letters=False) == "12"
    assert shape.in_letters("he") and shape.in_letters("arc")
    assert not shape.in_letters("en") and not shape.in_letters("ru")


def test_a_chapter_heading_that_is_the_work_and_a_numeral_is_a_plate() -> None:
    work = "משנה תורה, הלכות יסודי התורה"
    segments = [head(0, f"{work} ב׳"), head(1, "הלכות תשובה"), head(2, f"{work} ט״ו")]
    found = shape.plates(work, "he", segments)
    assert set(found) == {segments[0].id, segments[2].id}
    assert found[segments[0].id].said == "פרק ב׳"
    assert found[segments[2].id].number == 15
    # Not on a text in another script, and not without a title to compare.
    assert shape.plates(work, "en", segments) == {}
    assert shape.plates("", "he", segments) == {}


def test_a_parasha_is_read_off_the_end_of_its_verse() -> None:
    assert shape.parasha("וַיְהִי בֹקֶר יוֹם אֶחָד׃ (פ)") == "open"
    assert shape.parasha("תְּחַיּוּן׃ (ס)") == "closed"
    assert shape.parasha("יְהִי אוֹר׃") == ""
    text = "יוֹם אֶחָד׃ (פ)"
    [(start, end, kind)] = shape.parasha_cut(text)
    assert text[start:end] == "(פ)" and kind == "pmark"


def test_a_psalm_breaks_after_its_etnachta_and_nowhere_else() -> None:
    accented = f"מִזְמ֥וֹר לְדָוִ֑{ETNACHTA}ד יְהוָ֥ה רֹ֝עִ֗י"
    assert shape.half_line("Psalms 23:1", accented) == 1
    assert shape.half_line("Genesis 1:1", accented) is None
    assert shape.half_line("Psalms 23:1", "מזמור לדוד") is None
    # The same word in the bare form, which counts the same words.
    bare = "מזמור לדוד יהוה רעי"
    [(at, end, kind)] = shape.break_after(bare, 1, 4)
    assert at == end == len("מזמור לדוד") and kind == "stich"
    # A form that counts other words is left alone rather than broken in the wrong place.
    assert shape.break_after("מזמור לדוד", 1, 4) == []


def test_undressed_text_is_isolated_exactly_as_before() -> None:
    text = "המשחק הסתיים 72-73 בהיכל"
    assert shape.dress(text, "rtl", None, isolate) == isolate(text, "rtl")
    assert shape.dress(text, "rtl", [], isolate) == isolate(text, "rtl")


def test_dressing_adds_markup_and_never_a_character() -> None:
    text = "וַיְהִי בֹקֶר יוֹם אֶחָד׃ (פ)"
    cuts = [*shape.parasha_cut(text), (5, 5, "stich")]
    dressed = shape.dress(text, "rtl", cuts, isolate)
    assert '<span class="pmark">' in dressed and '<br class="stich">' in dressed
    assert unescape(re.sub(r"<[^>]+>", "", dressed)) == text


def test_a_number_range_is_kept_on_one_line() -> None:
    assert '<bdi class="unbroken">72-73</bdi>' in isolate("בתוצאה 72-73.", "rtl")
    # A year alone is a run as it always was, and a Latin name is no number.
    assert "<bdi>2008</bdi>" in isolate("30 במאי 2008", "rtl")
    assert "<bdi>Magma Devs</bdi>" in isolate("של Magma Devs", "rtl")


# --- the page ----------------------------------------------------------------------------


def test_the_page_draws_a_halakha_chapter_in_its_own_shape(tmp_path: Path) -> None:
    work = "משנה תורה, הלכות יסודי התורה"
    segments = [
        head(0, f"{work} ב׳"),
        verse(1, "הָאֵל הַנִּכְבָּד וְהַנּוֹרָא הַזֶּה מִצְוָה לְאָהֳבוֹ", "Mishneh Torah 2:1"),
        verse(2, "וְהֵיאַךְ הִיא הַדֶּרֶךְ לְאַהֲבָתוֹ", "Mishneh Torah 2:2"),
    ]
    english = {
        segments[0].id: "Mishneh Torah, Foundations of the Torah 2",
        segments[1].id: "It is mandatory to love.",
        segments[2].id: "But how?",
    }
    html = built(tmp_path, work, segments, english)
    # The plate: the work once, the chapter as a chapter, Chapter 2 beside it.
    assert 'class="pair head plate' in html
    assert re.search(r'<p class="plate-work"[^>]*>משנה תורה, הלכות יסודי התורה</p>', html)
    assert re.search(r'<h2 class="plate-chapter"[^>]*>פרק ב׳</h2>', html)
    assert "Chapter 2" in html
    # The heading's own cell is still in the page, for whatever reads a row.
    assert f"{work} ב׳" in html
    # Halakhot in letters, still answering to their address.
    assert re.search(r'<a class="verse-number letter" href="#2:1"[^>]*>א׳</a>', html)
    assert re.search(r'<a class="verse-number letter" href="#2:2"[^>]*>ב׳</a>', html)


def test_a_torah_chapter_breaks_where_the_scribe_broke_it(tmp_path: Path) -> None:
    segments = [
        head(0, "בראשית א׳"),
        verse(1, "וַיְהִי עֶרֶב וַיְהִי בֹקֶר יוֹם אֶחָד׃ (פ)", "Genesis 1:5"),
        verse(2, "וַיֹּאמֶר אֱלֹהִים יְהִי רָקִיעַ׃", "Genesis 1:6"),
        verse(3, "וְכָל־הַבַּת תְּחַיּוּן׃ (ס)", "Genesis 1:7"),
    ]
    html = built(tmp_path, "בראשית", segments, {})
    assert re.search(r'class="pair verse ends-open', html)
    assert re.search(r'class="pair verse ends-closed', html)
    assert '<span class="pmark">(פ)</span>' in html
    # Not one character of the verse moved: the plain cell is the bare line, whole.
    from targum.vocalize import strip_nikkud

    assert visible_text(html, segments[1].id) == strip_nikkud(segments[1].text)[0]


def test_a_psalm_stands_in_its_half_lines_with_its_text_whole(tmp_path: Path) -> None:
    line = f"מִזְמ֥וֹר לְדָוִ֑{ETNACHTA}ד יְהוָ֥ה רֹ֝עִ֗י לֹ֣א אֶחְסָֽר׃"
    segments = [head(0, "תהילים כ״ג"), verse(1, line, "Psalms 23:1")]
    html = built(tmp_path, "תהילים", segments, {})
    assert '<br class="stich">' in html
    from targum.vocalize import strip_nikkud

    assert visible_text(html, segments[1].id) == strip_nikkud(line)[0]


def test_the_sentences_of_one_paragraph_sit_together(tmp_path: Path) -> None:
    segments = [
        verse(0, "משפט ראשון.", "", block=0).model_copy(update={"kind": BlockKind.paragraph}),
        Segment(
            id="0000.001-aaaaaa",
            block_id="b0000",
            block_index=0,
            index=1,
            text="משפט שני.",
        ),
        verse(2, "פסקה חדשה.", "", block=2).model_copy(update={"kind": BlockKind.paragraph}),
    ]
    html = built(tmp_path, "מאמר", segments, {})
    assert re.search(r'class="pair cont[^"]*"[^>]*data-id="0000\.001-aaaaaa"', html)
    assert not re.search(r'class="pair cont[^"]*"[^>]*data-id="0002\.000-aaaaaa"', html)


def test_a_modern_text_is_the_page_it_was(tmp_path: Path) -> None:
    """No numbers, no plate, no breaks: an article has none of what this draws."""
    segments = [
        Segment(id="0000.000-aaaaaa", block_id="b0000", block_index=0, index=0, text="שלום עולם.")
    ]
    html = built(tmp_path, "מאמר", segments, {})
    assert "plate-face" not in html.split("</style>")[-1]
    assert "verse-number" not in html.split("</style>")[-1].split("<script")[0]
    assert '<br class="stich">' not in html
