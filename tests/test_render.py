from __future__ import annotations

import re
from pathlib import Path

import pytest

from targum.models import (
    BlockKind,
    Document,
    Segment,
    SegmentedDocument,
    Translation,
    direction_for,
)
from targum.render import MAX_SEGMENTS_PER_SECTION, isolate, render, split_sections


@pytest.mark.parametrize(
    ("tag", "expected"),
    [("he", "rtl"), ("he-IL", "rtl"), ("ar", "rtl"), ("en", "ltr"), ("ru", "ltr")],
)
def test_direction_comes_from_the_language_tag(tag: str, expected: str) -> None:
    assert direction_for(tag) == expected


def test_isolates_latin_runs_inside_rtl() -> None:
    out = str(isolate("בשנת תרנ״ז (1897) נתכנס", "rtl"))
    assert "(<bdi>1897</bdi>)" in out


def test_isolates_rtl_runs_inside_ltr() -> None:
    out = str(isolate("The word שלום means peace", "ltr"))
    assert "<bdi>שלום</bdi>" in out


def test_escapes_before_isolating() -> None:
    out = str(isolate('<script>alert("x")</script> שלום', "ltr"))
    assert "<script>" not in out
    assert "&lt;script&gt;" in out


def test_leaves_same_direction_text_alone() -> None:
    assert str(isolate("plain english words", "ltr")) == "plain english words"


# --- section splitting -------------------------------------------------------


def make_segmented(segments: list[Segment]) -> SegmentedDocument:
    return SegmentedDocument(
        document_hash="h", language="he", segmenter="fake/1", segments=segments
    )


def paragraph(index: int) -> Segment:
    return Segment(
        id=f"{index:04d}.000-aaaaaa",
        block_id=f"b{index:04d}",
        block_index=index,
        index=0,
        text=f"paragraph {index}",
    )


def heading(index: int, level: int, text: str) -> Segment:
    return Segment(
        id=f"{index:04d}.000-bbbbbb",
        block_id=f"b{index:04d}",
        block_index=index,
        index=0,
        kind=BlockKind.heading,
        level=level,
        text=text,
    )


def test_splits_at_top_level_headings() -> None:
    segments = [heading(0, 1, "One"), paragraph(1), heading(2, 1, "Two"), paragraph(3)]
    sections = split_sections(make_segmented(segments))
    assert [s.title for s in sections] == ["One", "Two"]
    assert [len(s.segment_ids) for s in sections] == [2, 2]


def test_does_not_split_at_deep_headings() -> None:
    segments = [heading(0, 1, "One"), paragraph(1), heading(2, 3, "Aside"), paragraph(3)]
    assert len(split_sections(make_segmented(segments))) == 1


def test_splits_long_runs_without_headings() -> None:
    segments = [paragraph(i) for i in range(MAX_SEGMENTS_PER_SECTION + 10)]
    sections = split_sections(make_segmented(segments))
    assert len(sections) == 2
    assert len(sections[0].segment_ids) == MAX_SEGMENTS_PER_SECTION
    assert sum(len(s.segment_ids) for s in sections) == len(segments)


def test_every_segment_lands_in_exactly_one_section() -> None:
    segments = [heading(0, 1, "One"), paragraph(1), heading(2, 2, "Two"), paragraph(3)]
    sections = split_sections(make_segmented(segments))
    placed = [sid for section in sections for sid in section.segment_ids]
    assert sorted(placed) == sorted(s.id for s in segments)


# --- rendering ---------------------------------------------------------------


@pytest.fixture
def rendered(tmp_path: Path, segmented: SegmentedDocument, translation: Translation) -> Path:
    document = Document(
        source="memory", title="Declaration", language="he", blocks=[], content_hash="abc123"
    )
    pages = render(document, segmented, [translation], tmp_path / "reader")
    return pages[0]


def test_one_section_becomes_the_index(rendered: Path) -> None:
    assert rendered.name == "index.html"
    assert not (rendered.parent / "sec-0001.html").exists()


def test_pairs_carry_their_segment_id(rendered: Path, segmented: SegmentedDocument) -> None:
    html = rendered.read_text(encoding="utf-8")
    for segment in segmented.segments:
        if segment.kind is not BlockKind.heading:
            assert f'data-id="{segment.id}"' in html


def test_both_directions_are_explicit(rendered: Path) -> None:
    html = rendered.read_text(encoding="utf-8")
    assert 'class="src" lang="he" dir="rtl"' in html
    assert 'class="tr" lang="en" dir="ltr"' in html
    assert '<html lang="he" dir="rtl">' in html


def test_layout_uses_logical_properties_only(rendered: Path) -> None:
    css = re.search(r"<style>(.*?)</style>", rendered.read_text(encoding="utf-8"), re.S)
    assert css is not None
    body = css.group(1)
    # margin-left in a stylesheet shared by an RTL and an LTR column is a bug waiting.
    for physical in ("margin-left", "margin-right", "padding-left", "padding-right"):
        assert physical not in body
    assert "margin-inline" in body or "padding-inline" in body


def test_is_self_contained(rendered: Path) -> None:
    html = rendered.read_text(encoding="utf-8")
    assert "http://" not in html and "https://" not in html
    assert "<style>" in html and "<script>" in html


def test_multiple_sections_get_an_index_and_pages(tmp_path: Path) -> None:
    segments = [heading(0, 1, "One"), paragraph(1), heading(2, 1, "Two"), paragraph(3)]
    segmented = make_segmented(segments)
    document = Document(source="memory", title="Book", language="he", blocks=[], content_hash="h")
    translation = Translation(
        name="English",
        document_hash="h",
        source_language="he",
        target_language="en",
        provider="null",
        segments={s.id: "x" for s in segments},
    )
    pages = render(document, segmented, [translation], tmp_path / "reader")

    assert [p.name for p in pages] == ["index.html", "sec-0001.html", "sec-0002.html"]
    index = pages[0].read_text(encoding="utf-8")
    assert 'href="sec-0001.html"' in index and 'href="sec-0002.html"' in index
    first = pages[1].read_text(encoding="utf-8")
    assert 'href="sec-0002.html"' in first  # next
    assert "paragraph 3" not in first  # section two's text is not in section one


def test_a_section_ships_only_its_own_translation_data(tmp_path: Path) -> None:
    segments = [heading(0, 1, "One"), paragraph(1), heading(2, 1, "Two"), paragraph(3)]
    segmented = make_segmented(segments)
    document = Document(source="m", title="B", language="he", blocks=[], content_hash="h")
    translation = Translation(
        name="English",
        document_hash="h",
        source_language="he",
        target_language="en",
        provider="null",
        segments={s.id: f"tr {s.text}" for s in segments},
    )
    pages = render(document, segmented, [translation], tmp_path / "reader")
    first = pages[1].read_text(encoding="utf-8")
    assert "tr paragraph 1" in first
    assert "tr paragraph 3" not in first


def test_rerender_replaces_stale_pages(
    tmp_path: Path, segmented: SegmentedDocument, translation: Translation
) -> None:
    out = tmp_path / "reader"
    document = Document(source="m", title="B", language="he", blocks=[], content_hash="h")
    render(document, segmented, [translation], out)
    (out / "sec-9999.html").write_text("stale", encoding="utf-8")
    render(document, segmented, [translation], out)
    assert not (out / "sec-9999.html").exists()


def test_headings_show_their_translation(tmp_path: Path) -> None:
    segments = [heading(0, 1, "מגילת העצמאות"), paragraph(1)]
    segmented = make_segmented(segments)
    document = Document(source="m", title="T", language="he", blocks=[], content_hash="h")
    translation = Translation(
        name="English",
        document_hash="h",
        source_language="he",
        target_language="en",
        provider="null",
        segments={segments[0].id: "Scroll of Independence", segments[1].id: "body"},
    )
    html = render(document, segmented, [translation], tmp_path / "r")[0].read_text(encoding="utf-8")
    assert "Scroll of Independence" in html
    # The source keeps heading semantics; the translation does not, so a table of
    # contents lists each section once.
    assert '<h1 class="src" lang="he" dir="rtl">' in html
    assert html.count("<h1") == 1


def test_bylines_are_paired_too(tmp_path: Path) -> None:
    byline = Segment(
        id="0001.000-cccccc",
        block_id="b0001",
        block_index=1,
        index=0,
        kind=BlockKind.byline,
        text="דוד בן־גוריון",
    )
    segmented = make_segmented([byline])
    document = Document(source="m", title="T", language="he", blocks=[], content_hash="h")
    translation = Translation(
        name="English",
        document_hash="h",
        source_language="he",
        target_language="en",
        provider="null",
        segments={byline.id: "David Ben-Gurion"},
    )
    html = render(document, segmented, [translation], tmp_path / "r")[0].read_text(encoding="utf-8")
    assert 'class="pair byline"' in html
    assert "David Ben-Gurion" in html


def test_front_matter_does_not_become_its_own_section() -> None:
    """A title and a byline belong to the section they introduce."""
    byline = Segment(
        id="0001.000-cccccc",
        block_id="b0001",
        block_index=1,
        index=0,
        kind=BlockKind.byline,
        text="An Author",
    )
    segments = [heading(0, 1, "Title"), byline, paragraph(2), heading(3, 1, "Two"), paragraph(4)]
    sections = split_sections(make_segmented(segments))
    assert [s.title for s in sections] == ["Title", "Two"]
    assert len(sections[0].segment_ids) == 3


def test_word_data_ships_as_offsets_not_spans(tmp_path: Path) -> None:
    """A book has hundreds of thousands of tokens; a span for each will not open."""
    from targum.models import Annotation, Token

    segments = [paragraph(0)]
    segmented = make_segmented(segments)
    document = Document(source="m", title="T", language="he", blocks=[], content_hash="h")
    translation = Translation(
        name="English",
        document_hash="h",
        source_language="he",
        target_language="en",
        provider="null",
        segments={segments[0].id: "tr"},
    )
    annotation = Annotation(
        document_hash="h",
        language="he",
        annotator="t",
        method="frequency",
        method_note="note",
        tokens={
            segments[0].id: [
                Token(start=0, end=9, surface="paragraph", lemma="paragraph", band=3),
                Token(start=10, end=11, surface="0", lemma="0", band=1, split=True),
            ]
        },
    )
    html = render(document, segmented, [translation], tmp_path / "r", annotation=annotation)[
        0
    ].read_text(encoding="utf-8")

    assert 'class="w' not in html  # nothing emitted up front
    assert '"words"' in html and '"lemmas"' in html
    # The margin list is where anything you keep goes.
    assert 'id="list-items"' in html
    controls = html.split("<header", 1)[1].split("</header>", 1)[0]
    assert "band" not in controls.lower()  # a number from inside the program


def test_no_difficulty_means_no_control(
    tmp_path: Path, segmented: SegmentedDocument, translation: Translation
) -> None:
    document = Document(source="m", title="T", language="he", blocks=[], content_hash="abc123")
    html = render(document, segmented, [translation], tmp_path / "r")[0].read_text(encoding="utf-8")
    assert 'id="list-items"' not in html
    assert 'id="gloss-card"' not in html


def test_gloss_mode_appears_only_with_a_glossary(tmp_path: Path) -> None:
    from targum.models import Annotation, Glossary, Token

    segments = [paragraph(0)]
    segmented = make_segmented(segments)
    document = Document(source="m", title="T", language="he", blocks=[], content_hash="h")
    translation = Translation(
        name="English",
        document_hash="h",
        source_language="he",
        target_language="en",
        provider="null",
        segments={segments[0].id: "tr"},
    )
    annotation = Annotation(
        document_hash="h",
        language="he",
        annotator="t",
        method="frequency",
        method_note="n",
        tokens={
            segments[0].id: [Token(start=0, end=9, surface="paragraph", lemma="paragraph", band=3)]
        },
    )
    glossary = Glossary(
        source_language="he",
        target_language="en",
        provider="test",
        entries={"paragraph": "a block of text"},
    )
    html = render(
        document,
        segmented,
        [translation],
        tmp_path / "r",
        annotation=annotation,
        glossary=glossary,
    )[0].read_text(encoding="utf-8")
    assert "a block of text" in html
    assert 'id="gloss-card"' in html


def test_the_reader_draws_words_and_phrases_in_one_pass() -> None:
    """Words and picked phrases overlap, so they are drawn as one set of flat slices.

    A source-level guard rather than a behavioural test; the parse check below is the
    other half of what stands in for real coverage of the reader's JavaScript.
    """
    from targum.render.builder import ASSETS

    script = (ASSETS / "reader.js").read_text(encoding="utf-8")
    assert "function markSegment(cell)" in script
    # Saved words and saved phrases are drawn in one pass, because a phrase can start
    # mid-word and cover several, which the DOM will not nest.
    assert 'classes: ["picked"]' in script
    assert "cuts[layer.start] = true" in script


def test_the_reader_script_parses() -> None:
    """A syntax error in reader.js would ship silently: the page renders, nothing works.

    Skipped where node is not installed, which is why it is a guard rather than the
    whole answer to the reader having no behavioural tests.
    """
    import shutil
    import subprocess

    from targum.render.builder import ASSETS

    node = shutil.which("node")
    if not node:
        pytest.skip("node not installed")

    script = (ASSETS / "reader.js").read_text(encoding="utf-8")
    result = subprocess.run(
        [
            node,
            "--input-type=module",
            "-e",
            "const fs = await import('node:fs');"
            "new Function(fs.readFileSync(process.argv[1], 'utf8'))",
            "--",
            str(ASSETS / "reader.js"),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "function markSegment" in script


def test_the_reader_styles_every_floating_card() -> None:
    """A card with no rules renders as text at the foot of the page, where nobody sees it.

    That is what "adding words does not work" looked like: the definition card was
    being built and shown correctly, with its styles removed by an unrelated cleanup.
    """
    from targum.render.builder import ASSETS

    css = (ASSETS / "reader.css").read_text(encoding="utf-8")
    for selector in (".gloss-card {", ".gloss-card .keep {", ".pick-card {", ".list {"):
        assert selector in css, selector
    # Each floats over the text, so each needs taking out of the flow.
    for block in (".gloss-card {", ".pick-card {", ".list {"):
        rules = css.split(block, 1)[1].split("}", 1)[0]
        assert "position:" in rules, block


def test_pressing_a_card_does_not_cancel_the_selection_behind_it() -> None:
    """Mousedown on the card collapses the selection, the mouseup handler then hides
    the card, and the click never reaches the button under the cursor. Which reads as
    the button doing nothing at all."""
    from targum.render.builder import ASSETS

    script = (ASSETS / "reader.js").read_text(encoding="utf-8")
    assert "chip.contains(event.target)" in script
    assert 'chip.addEventListener("mousedown"' in script

    css = (ASSETS / "reader.css").read_text(encoding="utf-8")
    assert "user-select: none" in css


def test_hostile_source_text_cannot_script_the_reader(tmp_path: Path) -> None:
    """Anything on a fetched web page can end up in a reader: the page title, the
    translation switcher, the JSON block. Each was or would be an injection route.

    Two real holes closed here: select_autoescape() matches on a template's final
    extension, so .j2 names left autoescaping off for every template; and the HTML
    parser ends a <script> element at the first "</script" even inside a JSON string.
    """
    from targum.models import Segment

    hostile = Segment(
        id="0000.000-aaaaaa",
        block_id="b0000",
        block_index=0,
        index=0,
        text="hello </script><script>alert(1)</script> world",
    )
    segmented = make_segmented([hostile])
    document = Document(
        source="m",
        title="<img src=x onerror=alert(2)>",
        language="en",
        blocks=[],
        content_hash="h",
    )
    translations = [
        Translation(
            name="fine",
            document_hash="h",
            source_language="en",
            target_language="he",
            provider="null",
            segments={hostile.id: "also </script><script>alert(3) here"},
        ),
        Translation(
            name="<svg onload=alert(4)>",
            document_hash="h",
            source_language="en",
            target_language="he",
            provider="null",
            segments={hostile.id: "x"},
        ),
    ]
    html = render(document, segmented, translations, tmp_path / "r")[0].read_text(encoding="utf-8")

    # Mirror the parser: a script element ends at the first "</script>". Whatever
    # remains after removing them is live markup, and no payload may be in it. Raw
    # "<" inside the surviving JSON data block is inert and allowed.
    page = re.sub(r"<script.*?</script>", "", html, flags=re.S)
    assert "<img" not in page  # the title is escaped where it renders as HTML
    assert "<svg" not in page  # the switcher option is escaped
    assert "<script" not in page  # nothing broke out of a script element
    assert "<\\/script" in html  # because "</" is split across a JSON escape
