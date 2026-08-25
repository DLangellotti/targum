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

    # The same three stores the reader writes, and no fourth copy of anything. The
    # reading of them lives in charts.js, because Learn draws the same numbers from the
    # same shape and a second collector is the one that stops matching.
    script = (ASSETS / "charts.js").read_text(encoding="utf-8")
    assert '"targum:vocab:"' in script
    assert '"targum:picked:"' in script
    assert '"targum:docs"' in script
    for page in ("words.js", "learn.js"):
        source = (ASSETS / page).read_text(encoding="utf-8")
        assert "function collect(" not in source, f"{page} should share the collector"

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
    from targum.render.builder import ASSETS, add_page, learn_page, library_page, words_page

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
        "add": add_page("k"),
        "learn": learn_page("k"),
        "library": library_page("k"),
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
    # One button that is on or off, not two to choose between: a switch, not a scale.
    assert "data-nikkud-toggle" in controls
    assert controls.count("data-nikkud") == 1


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
    from targum.render.builder import add_page, learn_page, library_page, words_page

    for html in (add_page("k"), learn_page("k"), words_page("k"), library_page("k")):
        assert "TargumLang" in html, "the shared language choice is missing"
        assert 'HOME = "he"' in html

    start = add_page("k")
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


def test_the_way_back_goes_to_learn(tmp_path: Path) -> None:
    """Both back links say Learn, so both go there.

    Somebody leaving a text wants their own shelf and the thing they were part way
    through — not the catalogue. The contents page and the section pages set the link
    from different scripts, and only one of them had ever been taught the difference,
    which is why both are checked.
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
        # The mark in the corner is the way back — the oldest convention there is, and
        # it was sitting inert beside a link that said the same thing.
        assert '<a class="bar-brand" id="home" href="/"' in html
        assert 'title="Your Learn page"' in html
        assert ">Learn</a>" not in html, "the word beside it said it twice"
        assert '"/library"' not in html, "the way out is not the catalogue any more"


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


def test_the_about_page_shows_thirty_days_and_no_inline_styles() -> None:
    """Thirty, not ninety: ninety days of empty squares says "abandoned" about a project
    that is three days old.

    And no `style="..."` attributes anywhere. The content policy names style blocks by
    hash rather than allowing inline generally, so an attribute is delivered and then
    silently ignored — which is how the first version of the bars on this page came out
    invisible.
    """
    import re

    from targum.about import DAYS
    from targum.render.builder import about_page

    assert DAYS == 30
    page = about_page()
    assert page.count('class="day level-') >= DAYS
    assert not re.search(r'<[^>]+\sstyle="', page), "inline style attributes will not apply"


def test_the_activity_shading_never_rounds_an_empty_day_up() -> None:
    """A day with nothing on it must read as nothing, not as a faint success."""
    from targum.render.builder import about_page

    assert about_page()  # renders
    from targum.render import builder

    source = (Path(builder.__file__)).read_text(encoding="utf-8")
    assert "if not count or not busiest:" in source


def test_a_pair_is_not_separated_by_a_blank_line() -> None:
    """The gap between pairs used to be a whole line of empty space.

    §5 of the guidelines sets reading at 1.0625rem with leading 1.95 on Hebrew, so a
    Hebrew line is about 2.07rem. `.pair` carried 1.35rem of margin plus the 0.35rem of
    padding on each side of it, which comes to 2.05rem — a paragraph break spent between
    every sentence, and between every verse of a chapter.

    Pinned as a fraction of a line rather than as a number, because the number only means
    anything against the leading.
    """
    from targum.render.builder import ASSETS

    css = (ASSETS / "reader.css").read_text(encoding="utf-8")
    line = 1.0625 * 1.95  # a Hebrew line, per §5

    def gap(*blocks: str) -> float:
        """The space between two pairs: the margin, plus the padding on each side of it.

        Read rather than assumed, because the padding turned out to be most of the
        answer — cutting the margin alone still left a visible step between one-line
        pesukim, and no amount of margin-tuning could close it.
        """
        margin, padding = 1.35, 0.35
        for block in blocks:
            rules = css.split(block, 1)[1].split("}", 1)[0]
            if found := re.search(r"margin-block-end:\s*([\d.]+)rem", rules):
                margin = float(found.group(1))
            if found := re.search(r"padding(?:-block)?:\s*([\d.]+)rem", rules):
                padding = float(found.group(1))
        return margin + padding * 2

    prose = gap(".pair {\n")
    assert prose < line * 0.6, "a paragraph break, not a blank line"

    # A verse is not a paragraph. Spacing pesukim apart makes a chapter read as a list.
    verses = gap(".pair {\n", "body.verses .pair {")
    assert verses < prose, "tighter again where a pair is one pasuk"

    # And with the translation hidden there is no pairing left for the space to serve,
    # so it goes almost entirely: one-line verses should run as continuous text.
    alone = gap(".pair {\n", "body.verses .pair {", ".mode-source .pair { margin")
    assert alone < verses
    assert alone < line * 0.2, "source-only should read as a chapter, not as a list"


def test_only_a_verse_text_is_spaced_like_verses() -> None:
    """Asked of the source rather than guessed from the content — the same way
    `biblical.for_source()` picks the difficulty bands, and for the same reason."""
    from targum.render.builder import ASSETS

    template = (ASSETS.parent / "templates/reader.html.j2").read_text(encoding="utf-8")
    assert "{% if verse_by_verse %} verses{% endif %}" in template

    builder = (Path(__file__).resolve().parents[1] / "src/targum/render/builder.py").read_text(
        encoding="utf-8"
    )
    assert '"verse_by_verse": document.source.startswith("sefaria:")' in builder


# -- reading, or marking ---------------------------------------------------------


def _reader_css() -> str:
    from targum.render.builder import ASSETS

    return (ASSETS / "reader.css").read_text(encoding="utf-8")


def test_marking_is_what_a_text_opens_in() -> None:
    """It was off for a day, on the argument that a page covered in marks is a worksheet.
    A reader who has to find a key before the product does its one distinctive thing has
    to know the key is there; the quiet page is one keystroke away and the choice sticks.
    """
    from targum.render.builder import ASSETS

    script = (ASSETS / "reader.js").read_text(encoding="utf-8")
    prefs = script[script.index("var prefs = {") : script.index("try {", script.index("var prefs"))]
    assert re.search(r"\bmarking:\s*true\b", prefs), "marking is the default"
    assert "mark: true" not in prefs, "the old half-measure is gone"


def test_the_marking_class_is_not_one_applymode_eats() -> None:
    """`applyMode()` strips every `mode-*` token off body.className to swap the reading
    mode. A marking class named `mode-…` would vanish the first time somebody pressed
    p, o or i — silently, and only for people who use those keys."""
    from targum.render.builder import ASSETS

    script = (ASSETS / "reader.js").read_text(encoding="utf-8")
    assert 'classList.toggle("marking"' in script
    assert 'classList.toggle("mode-marking"' not in script
    stripper = re.search(r"body\.className\.replace\((/[^)]+/g)", script)
    assert stripper is not None, "applyMode no longer strips the way this test reads it"
    assert re.match(stripper.group(1)[1:-2], "marking") is None


def test_nothing_about_reading_mode_can_reflow_the_page() -> None:
    """Switching must not rebreak a line. Every rule that differs between the two modes
    is a paint property, so the boxes are identical and the text cannot move."""
    css = _reader_css()
    block = css[css.index(".w { border-radius") : css.index("/* --- what a word means")]
    allowed = {"border-radius", "cursor", "background", "box-shadow"}

    # Parsed by declaration block rather than by line: these rules are written one to a
    # line as often as not, and an anchored regex silently skips those — which would let
    # exactly the property this test exists to catch through.
    seen = []
    for chunk in re.findall(r"\{([^}]*)\}", block):
        for declaration in chunk.split(";"):
            name = declaration.split(":", 1)[0].strip()
            if name:
                seen.append(name)
    assert len(seen) >= 6, "the rules moved; this is reading the wrong slice"
    for prop in seen:
        assert prop in allowed, f"{prop} changes a box, so switching modes would reflow"


def test_a_word_is_markable_in_both_modes() -> None:
    """Marking changes what the page shows you, never what it lets you do.

    You have to be able to mark a word in order to clear it, and clearing them is the
    whole point of the mode — so gating the card on the mode would make the mode
    impossible to get out of.
    """
    css = _reader_css()
    assert ".w { border-radius: 4px; cursor: pointer; }" in css, "tappable either way"
    assert "body.marking .w { cursor" not in css

    from targum.render.builder import ASSETS

    script = (ASSETS / "reader.js").read_text(encoding="utf-8")
    handler = script[script.index("/* --- clicks ---") : script.index("/* --- keyboard ---")]
    assert "prefs.marking &&" not in handler, "a tap opens the card in either mode"
    picking = script[script.index('document.addEventListener("mouseup"') :][:600]
    assert "prefs.marking" not in picking, "so does a selection"


def test_a_word_you_have_never_marked_is_the_loudest_thing_on_the_page() -> None:
    """The point of the mode: everything you do not know starts lit, and you put it out
    by marking it. A scale that only began once you had already said something told you
    nothing about the words you had not.
    """
    css = _reader_css()
    assert "body.marking .w:not([data-status])" in css, "never-marked words carry the top step"

    # One hue, and monotone down the scale, or it does not read as one scale.
    def wash(selector: str) -> int:
        rules = css.split(selector, 1)[1].split("}", 1)[0]
        found = re.search(r"background:.*?var\(--accent\) (\d+)%", rules)
        return int(found.group(1)) if found else 0

    fresh = wash("body.marking .w:not([data-status])")
    one = wash('body.marking .w[data-status="1"]')
    two = wash('body.marking .w[data-status="2"]')
    assert fresh > one > two > 0, "saying anything about a word must make it quieter"
    # §4 caps the accent wash at 22%.
    assert fresh <= 22 and two >= 12, "every step stays inside the sanctioned wash range"

    # Known and ignored take no wash at all — the page empties as you learn it.
    assert 'body.marking .w[data-status="9"]' not in css
    assert 'body.marking .w[data-status="0"]' not in css


def test_the_words_are_wrapped_in_both_modes_so_copying_is_the_same() -> None:
    """The spans are what a status hangs off, and they stay in the page either way —
    reading mode is CSS. If it ever became a re-render, the copied string would differ
    between modes and nothing would say so.
    """
    from targum.render.builder import ASSETS

    script = (ASSETS / "reader.js").read_text(encoding="utf-8")
    body = script[script.index("function markSegment(cell)") : script.index("function redraw()")]
    assert "prefs.marking" not in body, "marking up must not depend on the mode"


def test_the_shortcut_is_listed_like_every_other_one() -> None:
    from targum.render.builder import ASSETS

    template = (ASSETS.parent / "templates/reader.html.j2").read_text(encoding="utf-8")
    assert "<dt>m</dt>" in template
    assert "data-marking" in template


# -- how much of this you can already read ----------------------------------------


def test_the_header_counts_the_words_here_and_the_knowing_everywhere() -> None:
    """Words are kept per language, so a word first met in another text already counts
    the moment you open this one. That is what makes the number answer "how hard is this
    for me" rather than "how far through this text am I"."""
    from targum.render.builder import ASSETS

    script = (ASSETS / "reader.js").read_text(encoding="utf-8")
    stats = script[script.index("function renderStats()") : script.index("var lastCounts")]
    # coverage() walks lemmasHere() — this text — and asks statusOf(), which reads the
    # language-wide store. Both halves come from that one call.
    assert "var counts = coverage();" in stats
    assert "counts.known" in stats


def test_ignored_words_leave_the_total_rather_than_counting_as_known() -> None:
    """Ignore means "this is not vocabulary" — a name, a numeral, a word from another
    language. Counting it as known would make the figure one you could raise by ignoring
    things, which is not what the label claims.
    """
    from targum.render.builder import ASSETS

    script = (ASSETS / "reader.js").read_text(encoding="utf-8")
    assert "var scored = counts.total - counts.ignored;" in script
    stats = script[script.index("function renderStats()") : script.index("var lastCounts")]
    assert "counts.known + counts.ignored" not in stats


def test_a_text_with_no_words_shows_no_count() -> None:
    """ "0 of 0 known" is worse than saying nothing. Some builds carry no annotation."""
    from targum.render.builder import ASSETS

    script = (ASSETS / "reader.js").read_text(encoding="utf-8")
    assert "headerKnown.hidden = !scored;" in script
    template = (ASSETS.parent / "templates/reader.html.j2").read_text(encoding="utf-8")
    assert '<span class="known" id="known" hidden></span>' in template


def test_the_known_count_reads_the_same_way_on_a_hebrew_page() -> None:
    """`.bar-title` takes the page's direction, so on a Hebrew text this line came out
    "of 142 known 0" — an English phrase reordered around its own numbers."""
    css = _reader_css()
    rules = css.split(".bar-title .known {", 1)[1].split("}", 1)[0]
    assert "direction: ltr" in rules
    assert "unicode-bidi: isolate" in rules


def test_a_word_card_opens_beside_its_word() -> None:
    """It was pinned to the foot of the window wherever you tapped, so marking a word in
    the first line meant crossing the page to press a button about it and crossing back.
    """
    from targum.render.builder import ASSETS

    script = (ASSETS / "reader.js").read_text(encoding="utf-8")
    assert "placeNear(card, word.getBoundingClientRect());" in script
    # The phrase card already did this; one placer now, so the two cannot drift.
    assert script.count("function placeNear(") == 1
    assert "placeNear(chip, rect)" in script

    css = _reader_css()
    rules = css.split(".gloss-card {", 1)[1].split("}", 1)[0]
    assert "position: absolute" in rules, "it has to scroll with the word"
    assert "inset-block-end" not in rules, "no longer pinned to the window"


def test_the_level_keys_only_borrow_the_letters_while_a_card_is_open() -> None:
    """`k` is previous-sentence and `i` is interlinear. Taking them outright would break
    two shortcuts that have nothing to do with words; the card borrows them and gives
    them straight back."""
    from targum.render.builder import ASSETS

    script = (ASSETS / "reader.js").read_text(encoding="utf-8")
    assert "var KEYED_STATUS = { 1: 1, 2: 2, 3: 3, k: KNOWN, i: IGNORED };" in script
    # Only ever while one of the two cards is up.
    assert "if (lookedUp && card && !card.hidden) {" in script, "the word card"
    assert "if (pickLevel && chip && !chip.hidden) {" in script, "and the phrase card"
    # And the letters still do their old job, which is only true if the switch is intact.
    keys = script[script.index("switch (event.key) {") :]
    assert 'case "k":' in keys and 'case "i":' in keys

    # A bare lookup would treat "constructor" as a level.
    assert "hasOwnProperty.call(KEYED_STATUS, key)" in script


def test_the_level_keys_are_written_down() -> None:
    from targum.render.builder import ASSETS

    template = (ASSETS.parent / "templates/reader.html.j2").read_text(encoding="utf-8")
    assert "<dt>1 2 3</dt>" in template
    assert "known, or ignore it" in template


def test_a_phrase_takes_the_same_keys_as_a_word() -> None:
    """Same keys, different saving: a word is filed by lemma and travels between texts,
    a phrase is offsets into one sentence and stays with it. The two cards share the
    keys rather than the path.

    The card is drawn again afterwards because `TargumVocab.editor` reads its pressed
    state once, when it is built — without that, the level would be saved and the button
    would go on looking unpressed.
    """
    from targum.render.builder import ASSETS

    script = (ASSETS / "reader.js").read_text(encoding="utf-8")
    assert "function showPick(picked)" in script, "rebuildable, so the card can restate"
    body = script[script.index("function showPick(picked)") : script.index("/* --- export ---")]
    assert body.count("pickLevel = function (status)") == 2, "both branches of the card"
    assert body.count("showPick(picked);") == 2, "each redraws it"
    # And it stops being live the moment the card goes: both places that hide the card
    # clear it, or the keys would go on marking a phrase you can no longer see.
    hides = [line for line in script.splitlines() if "chip.hidden = true;" in line]
    assert len(hides) == 2
    for spot in (
        "chip.hidden = true;\n      pickLevel = null;",
        "chip.hidden = true;\n        pickLevel = null;",
    ):
        assert spot in script, spot


def test_the_page_marks_what_you_are_looking_at_first() -> None:
    """Marking a pair turns a few text nodes into hundreds of inline spans, and doing the
    whole chapter before the browser paints means every line of Hebrew is re-shaped
    before the first mark can be seen. The work is the same; the order is not.

    Measured on a 400-pair chapter: marks on screen at 60ms, against 330ms to mark the
    page — and the 330ms is a headless browser with no fonts to shape and no display.
    """
    from targum.render.builder import ASSETS

    script = (ASSETS / "reader.js").read_text(encoding="utf-8")
    redraw = script[script.index("function redraw()") : script.index("/* --- the list ---")]
    assert "ordered.slice(0, AHEAD).forEach(markPair);" in redraw, "a screenful, now"
    assert "markVisible();" in redraw, "the rest of the screen once it is laid out"
    # Ordered from the pair you are looking at, not from the top of the document.
    assert "pairs.slice(first).concat(pairs.slice(0, first))" in redraw


def test_the_marking_pass_cannot_run_twice_over_itself() -> None:
    """A redraw while a fill is in flight, a scroll that reaches a pair the fill has not,
    and a scroll frame over a pair already done — all three arrive at the same pair.
    Marking rebuilds the cell from scratch, so doing it twice is wasted work and doing it
    from two passes at once would interleave them.
    """
    from targum.render.builder import ASSETS

    script = (ASSETS / "reader.js").read_text(encoding="utf-8")
    assert "if (generation !== pending) return;" in script, "an old fill abandons itself"
    assert "if (pair.__targumDrawn === pending) return;" in script, "and a pair is done once"


def test_lazy_marking_degrades_rather_than_breaks() -> None:
    """The reader's standing rule. With no requestAnimationFrame the whole page is marked
    at once, which is what it always did."""
    from targum.render.builder import ASSETS

    script = (ASSETS / "reader.js").read_text(encoding="utf-8")
    redraw = script[script.index("function redraw()") : script.index("/* --- the list ---")]
    assert "if (!window.requestAnimationFrame) {" in redraw
    assert "ordered.forEach(markPair);" in redraw, "everything, immediately, as before"


def test_no_count_on_the_page_reads_the_dom() -> None:
    """What makes lazy marking safe. If any figure were counted from the spans, drawing
    fewer of them would quietly change what the reader is told."""
    from targum.render.builder import ASSETS

    script = (ASSETS / "reader.js").read_text(encoding="utf-8")
    for name in ("function lemmasHere()", "function coverage()", "function wordEntries()"):
        body = script[script.index(name) :]
        body = body[: body.index("\n  }\n")]
        assert "querySelector" not in body, f"{name} must not count spans"
        assert "getElementsBy" not in body, f"{name} must not count spans"


def test_a_reader_can_be_asked_where_the_time_went() -> None:
    """A page that felt slow measured fast everywhere it could be measured. Guessing at
    that is how the wrong thing gets optimised."""
    from targum.render.builder import ASSETS

    script = (ASSETS / "reader.js").read_text(encoding="utf-8")
    # Matched on the raw address, not parsed: a reader already carries a key in its
    # query, so `?debug=timing` appended to it makes a second `?` and a parser reads the
    # whole lot as the key. The switch then does nothing, silently.
    assert 'indexOf("debug=timing") >= 0' in script
    assert "location.search + location.hash" in script
    assert "var began = performance.now();" in script
    # And through a key, because asking for it through the address failed twice: a
    # reader already carries a key in its query, so `?debug=timing` on the end makes a
    # second `?`. A diagnostic whose address must be hand-edited is one that does not
    # work when it is needed.
    assert 'case "t":' in script
    assert "showTimings(!readout || readout.hidden)" in script
    template = (ASSETS.parent / "templates/reader.html.j2").read_text(encoding="utf-8")
    assert "<dt>t</dt>" in template, "and it is written down like every other key"
    # Measured from the top of the file, or it is measuring the wrong span.
    assert script.index("var began") < script.index("function markSegment")
    # Recorded always, shown only when asked. Four numbers and a string cost nothing to
    # keep, and a diagnostic that has to be switched on before the thing goes wrong is
    # one you never have when it does.
    took = script[script.index("function took(what)") :]
    took = took[: took.index("\n  }")]
    assert "timings.push(" in took
    assert "if (timing) showTimings(true);" in took, "and shown at once if asked up front"


def test_a_changed_default_reaches_a_browser_that_already_has_one() -> None:
    """`prefs` loads stored values over the defaults, so a preference already in a
    browser beats a new default forever — which means a default can only be changed for
    somebody who has not got one. A day after shipping, that is nobody.

    Marking was shipped off, then changed to on, and the second change reached no one who
    had already opened a reader. The generation stamp is what makes a default changeable.
    """
    from targum.render.builder import ASSETS

    script = (ASSETS / "reader.js").read_text(encoding="utf-8")
    assert "var DEFAULTS = 2;" in script
    assert "var RESET = { marking: true };" in script
    assert "if ((prefs.defaults || 0) < DEFAULTS) {" in script
    # Stored, or it re-applies on every load and the reader can never turn it off.
    reset = script[script.index("if ((prefs.defaults || 0) < DEFAULTS) {") :][:300]
    assert "prefs.defaults = DEFAULTS;" in reset
    assert "save();" in reset
    # And `defaults` has to be a known key, or the stored value is discarded on load.
    prefs = script[script.index("var prefs = {") : script.index("var DEFAULTS")]
    assert "defaults: 0," in prefs


def test_the_page_is_never_marked_further_than_it_is_read() -> None:
    """It used to fill the whole chapter in the background, a slice per frame. Measured
    at 1,539ms on a real chapter in a real browser — work for text that was mostly never
    looked at, competing with the scrolling of the text that was.

    What is on screen is marked; scrolling marks what it reaches; the rest is never done.
    """
    from targum.render.builder import ASSETS

    script = (ASSETS / "reader.js").read_text(encoding="utf-8")
    assert "function markOnward" not in script, "no background fill"
    assert "PER_FRAME" not in script
    # Scrolling and resizing are the two ways a pair arrives on screen.
    assert 'window.addEventListener("scroll", catchUp, { passive: true });' in script
    assert 'window.addEventListener("resize", catchUp);' in script
    # And the walk stops at the first pair below the fold rather than crossing the rest.
    visible = script[script.index("function markVisible()") :]
    assert "break;" in visible[: visible.index("\n  }")]


def test_hebrew_is_set_from_its_own_stack() -> None:
    """The reader was never slow; the page could not be laid out.

    §5 names Latin faces then Hebrew ones, and they were one stack — so every pointed
    Hebrew cluster walked Iowan Old Style, Palatino Linotype, Palatino and Georgia before
    reaching a face that could carry a letter with its marks. Measured on the Declaration:
    901ms to first frame, against 5ms once Hebrew had a stack of its own. Hiding the
    nikud fixed it too, which is what identified it.
    """
    css = _reader_css()
    latin = css[css.index("--reading:") : css.index("--reading-hebrew")]
    for face in ("Taamey Frank CLM", "Frank Ruhl CLM", "SBL Hebrew"):
        assert face not in latin, f"{face} in the Latin stack is the whole cost"
    hebrew = css[css.index("--reading-hebrew:") : css.index("--measure:")]
    for face in ("Taamey Frank CLM", "Frank Ruhl CLM", "SBL Hebrew"):
        assert face in hebrew, f"{face} is named by §5 and has to stay somewhere"
    assert ":lang(he) { font-family: var(--reading-hebrew); }" in css


def test_no_scope_reads_a_constant_from_another_one() -> None:
    """`DAY` was declared in words.js and used in charts.js. Separate IIFEs, so the chart
    kit threw `DAY is not defined` on any page that had words on it — the words page drew
    nothing, and Learn's growth chart would have gone the same way.

    Third of these in a day: `keyed`, `keyHeaders`, `DAY`. All the same shape — something
    moved between files and left a name behind — and none is a syntax error, so
    `node --check` is blind to them. This looks only for a name *declared in one scope and
    read in another*, which is the shape itself rather than a guess at what is global.
    """
    from targum.render.builder import ASSETS

    def scopes_of(source: str) -> list[str]:
        parts = re.split(r"^\(function \(\) \{", source, flags=re.M)[1:]
        out = []
        for part in parts:
            body = re.sub(r"/\*.*?\*/", "", part, flags=re.S)
            out.append(re.sub(r"^\s*//.*$", "", body, flags=re.M))
        return out

    scoped: list[tuple[str, int, str]] = []
    for path in sorted(ASSETS.glob("*.js")):
        for n, body in enumerate(scopes_of(path.read_text(encoding="utf-8"))):
            scoped.append((path.name, n + 1, body))

    # Every SHOUTED constant, and the one scope that declares it.
    declared: dict[str, tuple[str, int]] = {}
    for name, n, body in scoped:
        for const in re.findall(r"\bvar\s+([A-Z][A-Z0-9_]{2,})\s*=", body):
            declared[const] = (name, n)

    stray = []
    for name, n, body in scoped:
        mine = set(re.findall(r"\bvar\s+([A-Z][A-Z0-9_]{2,})\s*=", body))
        for const, (owner, owner_scope) in declared.items():
            if const in mine:
                continue
            # Read as a bare name, never as somebody's property.
            if re.search(rf"(?<![.\w]){const}\b", body):
                stray.append(f"{name} scope {n} reads {const}, declared in {owner} scope {owner_scope}")
    assert not stray, "a constant crossed a scope:\n  " + "\n  ".join(sorted(stray))


def test_every_scope_defines_the_helpers_it_calls() -> None:
    """`keyed` and `keyHeaders` were called five times in reader.js and defined nowhere.

    The first served page load threw `keyed is not defined` two milliseconds in, and
    everything after it — the type size, the reading mode, the marking, the vowels, the
    word list, the sync — never ran. It was invisible three ways: unreachable on a page
    opened off the disk, silent in a console nobody had open, and indistinguishable from
    slowness, because a reader that half-starts looks like a reader that is thinking.

    Checked per IIFE, not per file: the next-chapter block is its own scope and was
    reaching into the reader's for both of them.
    """
    from targum.render.builder import ASSETS

    shared = ("keyed", "keyHeaders")
    for path in sorted(ASSETS.glob("*.js")):
        source = path.read_text(encoding="utf-8")
        # Top-level IIFEs start at column zero; nothing else in these files does.
        scopes = re.split(r"^\(function \(\) \{", source, flags=re.M)[1:] or [source]
        for n, scope in enumerate(scopes):
            body = re.sub(r"/\*.*?\*/", "", scope, flags=re.S)
            body = re.sub(r"^\s*//.*$", "", body, flags=re.M)
            for name in shared:
                if re.search(rf"\b{name}\(", body) and f"function {name}(" not in body:
                    raise AssertionError(f"{path.name} scope {n + 1} calls {name} without it")


def _reader_controls(tmp_path: Path) -> str:
    """The header of a rendered reader, which is where every control lives."""
    segment = hebrew(0, BARE_TEXT)
    html = render_with_vocalization(
        tmp_path,
        [segment],
        vocalization_for([segment], {segment.id: POINTED_TEXT}, [segment.id]),
    )
    return html.split("<header", 1)[1].split("</header>", 1)[0]


def test_the_toggles_are_drawings_with_a_sentence_behind_them(tmp_path: Path) -> None:
    """§7: icons are line diagrams of what the thing does, not a library and not a word.
    A control small enough to be a glyph needs the words on hover instead."""
    controls = _reader_controls(tmp_path)
    buttons = re.findall(r"<button\b.*?</button>", controls, re.S)

    def control(marker: str) -> str:
        found = [b for b in buttons if marker in b]
        assert len(found) == 1, f"{marker}: expected one button, found {len(found)}"
        return found[0]

    vowels = control("data-nikkud-toggle")
    assert "<svg" in vowels and ">Vowels<" not in vowels and ">No vowels<" not in vowels
    assert "title=" in vowels, "the words move to the hover"
    assert "aria-label=" in vowels, "and stay for anyone not hovering"

    # The marking control only renders on a text that has words to mark, so it is read
    # from the template rather than from a fixture built without annotation.
    from targum.render.builder import ASSETS

    template = (ASSETS.parent / "templates/reader.html.j2").read_text(encoding="utf-8")
    mark = re.search(r"<button\b[^>]*data-marking.*?</button>", template, re.S)
    assert mark is not None
    assert "<svg" in mark.group(0) and ">Mark<" not in mark.group(0)
    assert "title=" in mark.group(0) and "aria-label=" in mark.group(0)


def test_the_vowel_control_is_one_switch_not_two_choices(tmp_path: Path) -> None:
    """It is a thing that is on or off. Two buttons made a scale out of it."""
    controls = _reader_controls(tmp_path)
    assert controls.count("data-nikkud") == 1
    assert 'data-nikkud="on"' not in controls and 'data-nikkud="off"' not in controls

    from targum.render.builder import ASSETS

    script = (ASSETS / "reader.js").read_text(encoding="utf-8")
    assert "prefs.nikkud = !prefs.nikkud;" in script, "it toggles rather than being set"
    assert 'aria-pressed", prefs.nikkud ? "true" : "false"' in script


def test_the_mark_is_the_way_back(tmp_path: Path) -> None:
    """The oldest convention on the web, and it was sitting inert beside a link that
    said the same thing. Two drawings of it, so a reader opened off the disk shows a mark
    rather than a link to nowhere."""
    controls = _reader_controls(tmp_path)
    assert '<a class="bar-brand" id="home" href="/"' in controls
    assert 'id="home-plain"' in controls, "the unlinked one, for a page off the disk"
    assert ">Learn</a>" not in controls, "the word beside it said it twice"

    from targum.render.builder import ASSETS

    script = (ASSETS / "reader.js").read_text(encoding="utf-8")
    assert "if (homePlain) homePlain.hidden = true;" in script
    # A link wherever there is a Learn page, which hosted means without a key: there the
    # cookie identifies the reader and `keyed` is the identity.
    assert "if (home && served) {" in script
