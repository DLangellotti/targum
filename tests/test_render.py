from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from targum.models import (
    BlockKind,
    Document,
    Segment,
    SegmentedDocument,
    Translation,
    Vocalization,
    direction_for,
)
from targum.render import MAX_SEGMENTS_PER_SECTION, isolate, render, split_sections
from targum.vocalize import MARKS, strip_nikkud


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
    assert 'class="src plain" data-form="plain" lang="he" dir="rtl"' in html
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


# The one place a reader is allowed to point at the network, and only as somewhere the
# reader can choose to go: full conjugation tables are more than a reader can carry.
OUTBOUND = "https://www.pealim.com/"


def test_loads_nothing_from_the_network(rendered: Path) -> None:
    """Offline, on a phone, in an e-reader browser. Nothing may be fetched."""
    html = rendered.read_text(encoding="utf-8")
    assert "<style>" in html and "<script>" in html
    # Anything the page would fetch by itself: a script, a stylesheet, a font, an image.
    for position in (r'src\s*=\s*["\']', r"url\(", r'<link[^>]+href\s*=\s*["\']'):
        for match in re.finditer(position + r"(https?:)?//", html, re.I):
            raise AssertionError(
                f"reader fetches something external: {html[match.start() : match.start() + 80]!r}"
            )


def test_the_only_outbound_link_is_one_the_reader_must_click(rendered: Path) -> None:
    html = rendered.read_text(encoding="utf-8")
    for match in re.finditer(r"https?://[^\s\"'\\)]+", html):
        assert match.group(0).startswith(OUTBOUND), match.group(0)


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
    assert '<h1 class="src plain" data-form="plain" lang="he" dir="rtl">' in html
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


def test_interlinear_shows_the_translation_not_the_words(tmp_path: Path) -> None:
    """Interlinear sets the sentence translation under its own line.

    It used to print a gloss under every word, which is a different thing and a
    noisier one. Because it is the translation, it needs no glossary and is offered
    on every reader.
    """
    from targum.render.builder import ASSETS

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
    html = re.sub(
        r"<script.*?</script>",
        "",
        render(document, segmented, [translation], tmp_path / "a")[0].read_text(encoding="utf-8"),
        flags=re.S,
    )
    # No annotation, so no words at all — and it is still on offer.
    assert 'data-mode="inter"' in html
    assert "<dt>i</dt>" in html

    css = (ASSETS / "reader.css").read_text(encoding="utf-8")
    # The translation is shown, under the line rather than beside it.
    assert ".mode-inter .tr {" in css
    assert ".mode-inter .tr { display: none; }" not in css
    # And nothing prints a meaning under a word any more.
    assert ".wg" not in css
    assert ".wg" not in (ASSETS / "reader.js").read_text(encoding="utf-8")


def test_words_and_phrases_are_two_lists_with_two_counts(tmp_path: Path) -> None:
    """They are different kinds of thing and one total said neither number.

    A word is a fact about the language and travels with you; a phrase is a piece of
    one text and stays there. Counting them together also put a thing kept for its
    wording beside a thing kept because you did not know it.
    """
    from targum.models import Annotation, Token
    from targum.render.builder import ASSETS

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
    html = render(document, segmented, [translation], tmp_path / "r", annotation=annotation)[
        0
    ].read_text(encoding="utf-8")

    # Two lists, each with somewhere to put its own number.
    assert 'id="list-items"' in html
    assert 'id="phrase-items"' in html
    assert 'id="list-count"' in html
    assert 'id="phrase-count"' in html
    # They are tabs, so the panel holds one at a time rather than burying the phrases
    # under a word list that runs to hundreds.
    assert 'data-list="words"' in html
    assert 'data-list="phrases"' in html
    assert 'role="tablist"' in html
    # Each tab has its own empty state, so the phrase gesture is explained where it
    # would otherwise never be found.
    assert 'id="words-empty"' in html
    assert 'id="phrases-empty"' in html

    script = (ASSETS / "reader.js").read_text(encoding="utf-8")
    assert "function wordEntries()" in script
    assert "function phraseEntries()" in script
    # Nothing builds one merged list any more.
    assert "function entries()" not in script
    # Two files, not one with a column saying which kind each row is.
    assert "function exportWords()" in script
    assert "function exportPhrases()" in script
    assert '" — words.csv"' in script
    assert '" — phrases.csv"' in script


def test_the_words_page_stands_on_its_own() -> None:
    """Everything kept, with what it adds up to. Built from the browser's own stores.

    A source-level guard: the page has no server data behind it, so what can be checked
    here is that it reads the same stores the reader writes and ships its own chart
    colours rather than borrowing the reader's text ink.
    """
    from targum.render.builder import ASSETS, words_page

    html = words_page("test-key")
    assert "Your words" in html
    assert 'id="progress"' in html  # where your words are
    assert 'id="growth"' in html  # kept over time
    assert 'id="bands"' in html  # how common they are

    script = (ASSETS / "words.js").read_text(encoding="utf-8")
    # The same three stores the reader writes, and no fourth copy of anything.
    assert '"targum:vocab:"' in script
    assert '"targum:picked:"' in script
    assert '"targum:docs"' in script

    css = (ASSETS / "words.css").read_text(encoding="utf-8")
    # One ordered ramp, stepped for each surface rather than flipped: on paper the
    # darkest step carries, on a dark ground the lightest one does, and "known" is the
    # step that has to carry in both. Three definitions each: the light base, the
    # system-dark case, and the theme someone chose for themselves.
    for step in ("--step-1", "--step-2", "--step-3", "--step-4"):
        assert css.count(step + ":") == 3, step


def test_the_theme_is_chosen_once_for_every_page(tmp_path: Path) -> None:
    """Light or dark is a choice about targum, not about one page of it.

    The stamp has to be on the document before anything paints, or the page shows one
    theme and swaps to the other; and every page has to carry both the switch and the
    script, or the choice stops at the page you made it on.
    """
    from targum.render.builder import ASSETS, start_page, words_page

    theme = (ASSETS / "theme.js").read_text(encoding="utf-8")
    assert '"targum:theme"' in theme  # one key, one origin, every page
    assert "matchMedia" in theme  # until you choose, the system decides

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
    pages = {
        "start": start_page("k", 2.0, 10.0),
        "words": words_page("k"),
        "reader": render(document, segmented, [translation], tmp_path / "r")[0].read_text(
            encoding="utf-8"
        ),
    }
    for name, html in pages.items():
        assert "data-theme-toggle" in html, name
        # Inlined by the asset helper, and it has to sit above the body: a stamp
        # applied at the end of the document is applied after the first paint.
        assert '"targum:theme"' in html, name
        # ("<body" would match a CSS comment in the inlined stylesheet, so the head's
        # own end is what this measures against.)
        assert html.index('"targum:theme"') < html.index("</head>"), name

    css = (ASSETS / "reader.css").read_text(encoding="utf-8")
    # A light choice has to beat an OS set to dark, which is what the guard is for.
    assert ':root:not([data-theme="light"])' in css
    assert ':root[data-theme="dark"]' in css
    # And the controls follow, or a dark page keeps white dropdowns and scrollbars.
    assert "color-scheme: light" in css and "color-scheme: dark" in css


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
    assert "<script" not in page  # nothing broke out of a script element
    # The reader's own chrome draws its mode icons in SVG, so the tag alone no longer
    # tells a payload from the furniture. What must never survive as live markup is the
    # payload itself: an event handler, or a call it could fire.
    assert "<svg onload" not in page  # the switcher option is escaped
    assert "&lt;svg onload" in page  # and it is there, escaped, where it belongs
    # No element anywhere carries an inline event handler: escaped text may contain the
    # word, but a live attribute is always preceded by a space inside a tag.
    assert not re.search(r"<[a-z][^>]*\son[a-z]+\s*=", page, flags=re.I)
    assert "<\\/script" in html  # because "</" is split across a JSON escape


# --- the nikkud toggle -------------------------------------------------------

POINTED_TEXT = "אֶל־חַלּוֹנִי"
BARE_TEXT = "אל־חלוני"


def hebrew(index: int, text: str) -> Segment:
    return Segment(
        id=f"{index:04d}.000-dddddd",
        block_id=f"b{index:04d}",
        block_index=index,
        index=0,
        text=text,
    )


def render_with_vocalization(
    tmp_path: Path, segments: list[Segment], vocalization: Vocalization | None, **kwargs: object
) -> str:
    segmented = make_segmented(segments)
    document = Document(source="m", title="T", language="he", blocks=[], content_hash="h")
    translation = Translation(
        name="English",
        document_hash="h",
        source_language="he",
        target_language="en",
        provider="null",
        segments={segment.id: "tr" for segment in segments},
    )
    written = render(
        document,
        segmented,
        [translation],
        tmp_path / "r",
        vocalization=vocalization,
        **kwargs,  # type: ignore[arg-type]
    )
    return written[0].read_text(encoding="utf-8")


def vocalization_for(segments: list[Segment], pointed: dict[str, str], machine: list[str]):
    return Vocalization(
        document_hash="h",
        language="he",
        vocalizer="test/1",
        segments=pointed,
        machine=machine,
    )


def test_no_vocalization_means_no_toggle_and_no_second_cell(tmp_path: Path) -> None:
    html = render_with_vocalization(tmp_path, [hebrew(0, BARE_TEXT)], None)
    # The control lives in the header. The script always carries the word, so look
    # where the button would actually be rather than anywhere in the file.
    controls = html.split("<header", 1)[1].split("</header>", 1)[0]
    assert "data-nikkud" not in controls
    assert 'class="src pointed"' not in html


def test_both_forms_are_rendered_and_only_the_bare_one_shows(tmp_path: Path) -> None:
    segment = hebrew(0, BARE_TEXT)
    html = render_with_vocalization(
        tmp_path,
        [segment],
        vocalization_for([segment], {segment.id: POINTED_TEXT}, [segment.id]),
    )
    assert 'class="src plain"' in html and 'class="src pointed"' in html
    assert BARE_TEXT in html and POINTED_TEXT in html
    # Hidden by stylesheet rather than by an attribute, so the toggle is one class and
    # the default holds with no JavaScript at all.
    assert ".src.pointed { display: none; }" in html
    # And the page opens with the vowels off.
    body_class = re.search(r'<body class="([^"]*)"', html)
    assert body_class is not None and "nikkud" not in body_class.group(1)
    controls = html.split("<header", 1)[1].split("</header>", 1)[0]
    assert 'data-nikkud="on"' in controls


def test_the_pointed_cell_differs_from_the_bare_one_only_by_its_marks(tmp_path: Path) -> None:
    segment = hebrew(0, BARE_TEXT)
    html = render_with_vocalization(
        tmp_path,
        [segment],
        vocalization_for([segment], {segment.id: POINTED_TEXT}, [segment.id]),
    )
    cells = re.findall(r'class="src (?:plain|pointed)"[^>]*>(.*?)<', html)
    assert len(cells) == 2
    assert strip_nikkud(cells[1])[0] == cells[0]


def test_only_machine_pointed_segments_are_marked(tmp_path: Path) -> None:
    from_source = hebrew(0, POINTED_TEXT)
    guessed = hebrew(1, BARE_TEXT)
    html = render_with_vocalization(
        tmp_path,
        [from_source, guessed],
        vocalization_for(
            [from_source, guessed],
            {from_source.id: POINTED_TEXT, guessed.id: POINTED_TEXT},
            [guessed.id],
        ),
    )
    marked = re.findall(r'<div class="pair([^"]*)" data-id="([^"]+)"', html)
    by_id = {segment_id: classes for classes, segment_id in marked}
    assert "machine" in by_id[guessed.id]
    assert "machine" not in by_id[from_source.id]


def test_the_machine_marker_only_shows_while_the_vowels_do(tmp_path: Path) -> None:
    segment = hebrew(0, BARE_TEXT)
    html = render_with_vocalization(
        tmp_path,
        [segment],
        vocalization_for([segment], {segment.id: POINTED_TEXT}, [segment.id]),
    )
    css = re.search(r"<style>(.*?)</style>", html, re.S)
    assert css is not None
    for rule in re.findall(r"[^}]*\.pair\.machine[^{]*\{", css.group(1)):
        assert "body.nikkud" in rule


def test_token_offsets_ship_against_the_bare_text(tmp_path: Path) -> None:
    """A pointed source still hands the reader offsets it can use on the bare form."""
    from targum.models import Annotation, Token

    segment = hebrew(0, POINTED_TEXT)
    # 'חַלּוֹנִי' as the segment itself is written: after the maqaf, marks included.
    start = POINTED_TEXT.index("ח")
    annotation = Annotation(
        document_hash="h",
        language="he",
        annotator="t",
        method="frequency",
        method_note="note",
        tokens={
            segment.id: [
                Token(
                    start=start,
                    end=len(POINTED_TEXT),
                    surface="חלוני",
                    lemma="חלון",
                    band=3,
                )
            ]
        },
    )
    html = render_with_vocalization(
        tmp_path,
        [segment],
        vocalization_for([segment], {segment.id: POINTED_TEXT}, []),
        annotation=annotation,
    )
    payload = json.loads(
        re.search(r'<script type="application/json" id="targum-data">(.*?)</script>', html, re.S)
        .group(1)
        .replace("<\\/", "</")
    )
    rows = payload["words"][segment.id]
    bare_start, bare_end = rows[0][0], rows[0][1]
    assert BARE_TEXT[bare_start:bare_end] == "חלוני"


def test_the_reader_agrees_with_python_on_what_a_mark_is() -> None:
    """The one constant that has to mean the same thing in both languages.

    The reader maps offsets between the bare and pointed forms by testing each character
    against its own regex. If that regex and MARKS disagree by even one codepoint — the
    maqaf is the one that invites it, sitting mid-block among the marks — every span
    after it lands on the wrong letters.
    """
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    script = (Path(__file__).parent.parent / "src/targum/render/assets/reader.js").read_text(
        encoding="utf-8"
    )
    match = re.search(r"var MARK = (/\[[^\n]*?\]/);", script)
    assert match is not None, "reader.js no longer declares MARK the way this test reads it"
    probe = (
        f"const MARK = {match.group(1)};"
        "const out = [];"
        "for (let cp = 0x0591; cp <= 0x05C7; cp++)"
        "  if (MARK.test(String.fromCodePoint(cp))) out.push(cp);"
        "console.log(JSON.stringify(out));"
    )
    result = subprocess.run(
        [node, "-e", probe], capture_output=True, text=True, timeout=30, check=True
    )
    assert sorted(json.loads(result.stdout)) == sorted(MARKS)


def test_the_catalogue_pairs_a_text_with_a_published_translation() -> None:
    """The catalogue is the cheap half of targum: a text somebody has already translated.

    Building one asks no model for anything, so every entry has to actually carry a
    translation. Wikisource is full of index pages that look like texts, which is why
    entries are checked by fetching before they are written down.
    """
    from targum.catalogue import CATALOGUE, by_id
    from targum.render.builder import library_page

    assert CATALOGUE, "an empty catalogue is a page with nothing on it"
    for entry in CATALOGUE:
        assert entry.translations, entry.id
        assert entry.words > 100, entry.id  # an index page, not a text
        assert by_id(entry.id) is entry

    # The cards are drawn in the browser, from the payload, so that picking a language
    # can filter them. What the page has to carry is the payload itself.
    html = library_page("k")
    payload = html.split("window.TARGUM_CATALOGUE = ", 1)[1].split("\n", 1)[0].rstrip(";")
    shipped = json.loads(payload)
    assert [entry["id"] for entry in shipped] == [entry.id for entry in CATALOGUE]
    for sent, entry in zip(shipped, CATALOGUE, strict=True):
        assert sent["title"] == entry.title
        assert sent["language"] == entry.language
        assert sent["translations"], entry.id


def test_a_catalogued_source_is_recognised_however_it_is_typed() -> None:
    """So that nobody pays to translate a text that is sitting in the catalogue."""
    from targum.catalogue import CATALOGUE, matching

    entry = CATALOGUE[0]
    assert matching(entry.source) is entry
    assert matching(entry.source.replace(" ", "_")) is entry
    assert matching(f"  {entry.source.upper()}  ") is entry
    # A translation names its own entry too: either half is the same text.
    assert matching(entry.translations[0].source) is entry
    assert matching("wikisource:he:something else entirely") is None
    assert matching("") is None


def test_every_page_shares_one_language_choice() -> None:
    """targum is a Hebrew app, and says so the same way on all three pages.

    The language you pick on the library page is the one your words page opens on, so
    the module that keeps that choice has to be on every page that offers it. Hebrew
    is the default and the only one not marked beta.
    """
    from targum.render.builder import library_page, start_page, words_page

    for html in (start_page("k", 2.0, 10.0), words_page("k"), library_page("k")):
        assert "TargumLang" in html, "the shared language choice is missing"
        assert 'HOME = "he"' in html

    start = start_page("k", 2.0, 10.0)
    # Hebrew is chosen for you; the others say what they are.
    assert '<option value="he" selected>' in start
    assert "(beta)" in start
    assert ">Hebrew (beta)<" not in start


def test_a_hebrew_verb_carries_its_root_and_binyan(tmp_path: Path) -> None:
    """Both come off the machine, so they ride in the page rather than being fetched."""
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
                Token(
                    start=0,
                    end=5,
                    surface="התלבש",
                    lemma="התלבש",
                    band=3,
                    binyan="התפעל",
                    root="לבש",
                ),
                # Not a verb, and so carries neither. The tables still line up with the
                # lemmas, which is the whole reason they are parallel lists.
                Token(start=6, end=9, surface="בית", lemma="בית", band=1),
            ]
        },
    )
    html = render(document, segmented, [translation], tmp_path / "r", annotation=annotation)[
        0
    ].read_text(encoding="utf-8")

    data = json.loads(re.search(r'id="targum-data"[^>]*>(.*?)</script>', html, re.S).group(1))
    assert data["lemmas"] == ["התלבש", "בית"]
    assert data["roots"] == ["לבש", ""]
    assert data["binyanim"] == ["התפעל", ""]
    # Where the reader can go for the full tables, which are more than a page can carry.
    assert OUTBOUND in html


def test_every_page_carries_the_identity(rendered: Path) -> None:
    """The icons ride inside the page: a built reader has no sibling to link to."""
    html = rendered.read_text(encoding="utf-8")
    assert 'rel="icon" href="data:image/svg+xml' in html
    assert 'rel="apple-touch-icon" href="data:image/png;base64,' in html
    assert 'href="brand/' not in html


def test_the_way_back_goes_to_the_library(tmp_path: Path) -> None:
    """Both back links say Library, so both go there — not to the start page.

    The contents page and the section pages set the link from different scripts, and
    only one of them had been taught the difference.
    """
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
    contents, section = render(document, segmented, [translation], tmp_path / "reader")[:2]
    for page in (contents, section):
        html = page.read_text(encoding="utf-8")
        assert '<a class="home" id="home" href="/library" hidden>Library</a>' in html
        assert '"/library"' in html or '"/library?k="' in html
        assert 'home.href = "/" ' not in html


ASSETS = Path(__file__).resolve().parents[1] / "src/targum/render/assets"


def test_the_exports_cannot_carry_a_formula() -> None:
    """A spreadsheet runs a cell opening with =, +, - or @ as a formula.

    An export is a file someone opens somewhere else, and the words in it come from a
    text targum did not write. Both copies of the writer are checked, because there are
    two — the reader bakes its own and the words page has another.
    """
    import re

    for name in ("reader.js", "words.js"):
        source = (ASSETS / name).read_text(encoding="utf-8")
        match = re.search(r"function csvCell\(value\) \{(.*?)\n  \}", source, re.S)
        assert match, f"{name} has no csvCell to check"
        guard = match.group(1)
        assert "^[=+" in guard, f"{name} does not neutralise a leading formula character"
        assert '"\'" +' in guard or '"\'" +' in guard, f"{name} does not prefix anything"


def test_signing_out_keeps_a_list_of_what_to_keep_not_what_to_drop() -> None:
    """A drop-list goes stale the moment a key is added; a keep-list fails safe.

    The version this replaces named six keys and missed six others, among them
    `targum:master` and `targum:saved:` — the vocabulary store from before it was
    reshaped, still holding the words — and `targum:language`, which is a record of
    what somebody reads.
    """
    source = (ASSETS / "sync.js").read_text(encoding="utf-8")
    clearing = source[source.index("function clearLocal") : source.index("function exchange")]

    assert 'indexOf("targum:") === 0' in clearing, "it should sweep every targum key"
    assert "KEEP" in clearing, "and keep only what is named"
    # Only a display preference survives. Anything about the reader must not.
    keep = source[source.index("var KEEP = ") : source.index("\n", source.index("var KEEP = "))]
    assert keep.count('"') == 2, f"exactly one key should survive, found: {keep}"
    assert "targum:theme" in keep


def test_the_language_switcher_offers_only_the_readers_own_languages() -> None:
    """The catalogue holds one Russian novel, and it was putting Russian in front of
    every visitor who had never touched it — against what lang.js says it does.
    """
    source = (ASSETS / "library.js").read_text(encoding="utf-8")
    building = source[source.index("var codes = [lang.HOME]") :]
    building = building[: building.index("lang.order")]

    assert "catalogue" not in building, "the catalogue must not widen the switcher"
    assert "readers" in building and "kept()" in building
