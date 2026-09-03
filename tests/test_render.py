from __future__ import annotations

import json
import re
import shutil
import subprocess
from html import unescape
from pathlib import Path

import pytest

from targum.models import (
    Annotation,
    BlockKind,
    Document,
    Segment,
    SegmentedDocument,
    Token,
    Translation,
    Vocalization,
    direction_for,
)
from targum.render import MAX_SEGMENTS_PER_SECTION, isolate, render, split_sections
from targum.vocalize import MARKS, has_taamim, strip_nikkud, strip_taamim


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
#: Every address a reader may carry. Not "no outbound links" — a reader chooses to click
#: these — but a pinned list, because the rule is that the page fetches nothing by itself
#: and a link that arrived without anyone deciding on it is how that erodes.
#:
#: The licence is here because a recording is used under one that asks to be linked, and
#: discharging that in the page is the point: a credit nobody can follow to the terms is
#: not a credit. It appears only in a reader that carries audio.
#: The conjugation tables a word's card offers, which are more than a page can carry.
PEALIM = "https://www.pealim.com/"
#: The licence a recording is used under.
LICENCE = "https://creativecommons.org/licenses/"
#: The model that read the words. CC BY 4.0 asks for the work to be named and linked
#: wherever it is used, and the words are used in the reader — so discharging it in the
#: page is the decision the recording's licence link already made. Added when Hebrew
#: moved off Stanza's NonCommercial models (targum-internal#116).
DICTA = "https://huggingface.co/dicta-il/"
#: Where a video fetched from YouTube lives. targum holds a study copy and the video's
#: home is not here, and the page says so with the one link that opens there — at the
#: line being read. Decided on 2026-09-02, for the same reason the hosted fetch stays
#: refused: the honest posture is that we did not take the video. One canonical shape,
#: `youtube.WATCH`, whatever address the reader pasted, so this prefix is the whole
#: allowance; and never for an uploaded file, which has no home to link to.
YOUTUBE = "https://www.youtube.com/watch?v="
OUTBOUND = (PEALIM, LICENCE, DICTA, YOUTUBE)


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


def test_a_recorded_reader_links_its_licence_and_nothing_else(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The one page that carries an address the rest of the library does not.

    A recording is used under a licence that asks to be linked, so the reader carries the
    link — and this pins it the same way every other outbound address is pinned. Without
    this the licence link lived in a page no allowlist test ever rendered.
    """
    import wave

    from targum.recording import Part, Recording
    from targum.recording import index as recording_index

    home = tmp_path / "recordings"
    folder = home / recording_index.slug("sefaria:Ruth")
    folder.mkdir(parents=True)
    with wave.open(str(folder / "one.wav"), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(8000)
        out.writeframes(b"\x00" * 16000)
    (folder / recording_index.MANIFEST).write_text(
        Recording(
            source="sefaria:Ruth",
            credit="Rabbi Somebody",
            licence="CC BY-SA 3.0",
            licence_url="https://creativecommons.org/licenses/by-sa/3.0/",
            parts=[Part(ref="Ruth 1", audio="one.wav", spans={"Ruth 1:1": [0.0, 1.0]})],
        ).model_dump_json(),
        encoding="utf-8",
    )
    monkeypatch.setenv("TARGUM_RECORDING_DIR", str(home))
    segment = Segment(
        id="0000.000-aaaaaa",
        block_id="b0000",
        block_index=0,
        index=0,
        kind=BlockKind.verse,
        text="ויהי בימי",
        ref="Ruth 1:1",
    )
    segmented = make_segmented([segment])
    document = Document(
        source="sefaria:Ruth", title="Ruth", language="he", blocks=[], content_hash="h"
    )
    translation = Translation(
        name="English",
        document_hash="h",
        source_language="he",
        target_language="en",
        provider="null",
        segments={segment.id: "In the days."},
    )
    page = render(document, segmented, [translation], tmp_path / "reader")[0]

    html = page.read_text(encoding="utf-8")
    assert "Rabbi Somebody" in html, "the reader is credited on the page"
    for match in re.finditer(r"https?://[^\s\"'\\)]+", html):
        assert match.group(0).startswith(OUTBOUND), match.group(0)


def imported(folder: Path, home: str) -> tuple[Document, SegmentedDocument, Translation]:
    """A reader built from somebody's own recording: the manifest beside it, a part on
    disk, and — where the recording was fetched from YouTube — the address it lives at."""
    import wave

    from targum.audio import manifest as manifest_module

    (folder / "audio" / "parts").mkdir(parents=True)
    with wave.open(str(folder / "audio" / "parts" / "part-001.wav"), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(8000)
        out.writeframes(b"\x00" * 16000)
    segments = [paragraph(1), paragraph(2)]
    manifest_module.write(
        folder,
        manifest_module.AudioManifest(
            source=str(folder / "audio" / "source.mp4"),
            home=home,
            sha256="x",
            duration=200.0,
            language="he",
            parts=[
                manifest_module.ManifestPart(
                    number=1,
                    # The part begins a hundred seconds in; its cut begins a pad earlier.
                    start=100.0,
                    end=200.0,
                    audio="audio/parts/part-001.wav",
                    spans={segments[0].id: [2.0, 4.0], segments[1].id: [5.0, 7.0]},
                )
            ],
        ),
    )
    document = Document(
        source=str(folder / "audio" / "source.mp4"),
        title="A talk",
        language="he",
        blocks=[],
        content_hash="h",
    )
    translation = Translation(
        name="English",
        document_hash="h",
        source_language="he",
        target_language="en",
        provider="null",
        segments={segment.id: "Said." for segment in segments},
    )
    return document, make_segmented(segments), translation


def test_a_video_reader_links_home_and_nowhere_else(tmp_path: Path) -> None:
    """The third outbound address, pinned the way the licence is: a video fetched from
    YouTube links to where it lives, an uploaded file links nowhere, and neither page
    carries any other address."""
    document, segmented, translation = imported(tmp_path, "https://youtu.be/abc123")
    page = render(document, segmented, [translation], tmp_path / "reader", folder=tmp_path)[0]
    html = page.read_text(encoding="utf-8")
    assert f'data-home href="{YOUTUBE}abc123"' in html, "one shape, whatever was pasted"
    assert 'target="_blank" rel="noreferrer noopener"' in html
    # The time is the reader's line, decided at the click: the markup carries none.
    assert not re.search(r'data-home href="[^"]*[?&]t=', html)
    # And the part's place in the whole video, so the script can add the two.
    assert '"offset": 99.65' in html
    for match in re.finditer(r"https?://[^\s\"'\\)]+", html):
        assert match.group(0).startswith(OUTBOUND), match.group(0)

    plain = tmp_path / "plain"
    plain.mkdir()
    document, segmented, translation = imported(plain, "")
    page = render(document, segmented, [translation], plain / "reader", folder=plain)[0]
    html = page.read_text(encoding="utf-8")
    assert "data-home href=" not in html, "an uploaded file has no home to go to"
    assert '"home": ' not in html and '"offset": ' not in html
    assert YOUTUBE not in html


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
        glossaries={"en": glossary},
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
    assert "<dt>l</dt>" in html

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


def test_the_progress_page_stands_on_its_own() -> None:
    """Everything kept, with what it adds up to. Built from the browser's own stores.

    A source-level guard: the page has no server data behind it, so what can be checked
    here is that it reads the same stores the reader writes and ships its own chart
    colours rather than borrowing the reader's text ink.
    """
    from targum.render.builder import ASSETS, progress_page

    html = progress_page("test-key")
    # The page's own heading, not the nav's. `assert "Your words" in html` used to stand
    # here and passed on "Your words follow you" in the account panel, which every page
    # carries — so it would have gone on passing with every heading stripped out.
    assert "<h1>Your Progress</h1>" in html
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
    for page in ("progress.js", "learn.js"):
        source = (ASSETS / page).read_text(encoding="utf-8")
        assert "function collect(" not in source, f"{page} should share the collector"

    css = (ASSETS / "words.css").read_text(encoding="utf-8")
    # One ordered ramp, faint → full, climbing to leaf. It was four gold hexes written
    # out three times over — the light base, the system-dark case, and the theme someone
    # chose — because a gold ramp has to be reordered by hand for each surface. Mixed
    # against --paper instead, both ends flip on their own: one definition now carries
    # every surface, and "known" is the most present step on each of them.
    for step in ("--step-1", "--step-2", "--step-3"):
        assert css.count(step + ":") == 1, f"{step} is defined once, for both surfaces"
        assert f"{step}: color-mix(in srgb, var(--leaf)" in css, f"{step} climbs to leaf"
    assert "--step-4: var(--leaf);" in css, "the top of the ramp is leaf itself"


def test_the_theme_is_chosen_once_for_every_page(tmp_path: Path) -> None:
    """Light or dark is a choice about targum, not about one page of it.

    The stamp has to be on the document before anything paints, or the page shows one
    theme and swaps to the other; and every page has to carry both the switch and the
    script, or the choice stops at the page you made it on.
    """
    from targum.render.builder import ASSETS, add_page, learn_page, library_page, progress_page

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
        "progress": progress_page("k"),
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
    for selector in (".gloss-card {", ".pick-card {", ".list {"):
        assert selector in css, selector
    # Each floats over the text, so each needs taking out of the flow.
    for block in (".gloss-card {", ".pick-card {", ".list {"):
        rules = css.split(block, 1)[1].split("}", 1)[0]
        assert "position:" in rules, block


def test_every_word_a_reader_meets_offers_to_copy_itself() -> None:
    """One control, built once in vocab.js and placed beside every word: the three lines
    of the card, the phrase and its reading, a row on the list beside the text, and a row
    on the words and phrases pages. Its rules live in the one stylesheet every page
    carries, and in the reader it speaks through the reader's own live region."""
    from targum.render.builder import ASSETS

    css = (ASSETS / "reader.css").read_text(encoding="utf-8")
    assert ".copy {" in css and ".gloss-card .copy-line {" in css
    reader = (ASSETS / "reader.js").read_text(encoding="utf-8")
    assert reader.count("window.TargumVocab.copyButton(") == 5, (
        "the word, its meaning, the phrase, its reading, a row"
    )
    assert reader.count("copyButton(") == reader.count(", { say: say })"), (
        "in the reader, every copy announces through #spoken"
    )
    lists = (ASSETS / "lists.js").read_text(encoding="utf-8")
    assert lists.count("window.TargumVocab.copyButton(") == 2, "a word row and a phrase row"
    vocab = (ASSETS / "vocab.js").read_text(encoding="utf-8")
    assert 'setAttribute("role", "status")' in vocab and 'aria-live", "polite"' in vocab, (
        "and elsewhere through a region of its own"
    )


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
# Ruth 1:1 as the pinned Masoretic edition writes it: vowels and accents both.
TROPE_TEXT = "וַיְהִ֗י בִּימֵי֙ שְׁפֹ֣ט הַשֹּׁפְטִ֔ים"
VOWELS_TEXT = strip_taamim(TROPE_TEXT)


def hebrew(index: int, text: str) -> Segment:
    return Segment(
        id=f"{index:04d}.000-dddddd",
        block_id=f"b{index:04d}",
        block_index=index,
        index=0,
        text=text,
    )


def render_with_vocalization(
    tmp_path: Path,
    segments: list[Segment],
    vocalization: Vocalization | None,
    source: str = "m",
    **kwargs: object,
) -> str:
    segmented = make_segmented(segments)
    document = Document(source=source, title="T", language="he", blocks=[], content_hash="h")
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
    # Every form, not just the two this text has — so the day a third appears on a page
    # this reads, it is counted rather than quietly skipped over.
    cells = re.findall(r'class="src (?:plain|pointed|trope)"[^>]*>(.*?)<', html)
    assert len(cells) == 2
    assert strip_nikkud(cells[1])[0] == cells[0]


def test_a_biblical_reader_says_its_dictionary_forms_are_less_reliable(tmp_path: Path) -> None:
    """The analyser is trained on modern unpointed Hebrew, so on the Tanakh it guesses at
    waw-consecutive, pausal and archaic forms. Said once in the keys panel rather than
    left for a reader to infer from a card that is quietly wrong (targum-internal #87).

    Only on scripture: on a modern text the caveat is not true enough to be worth the
    doubt it would plant.
    """
    segment = hebrew(0, TROPE_TEXT)
    voc = vocalization_for([segment], {segment.id: TROPE_TEXT}, [])
    scripture = render_with_vocalization(tmp_path / "a", [segment], voc, source="sefaria:Esther")
    news = render_with_vocalization(tmp_path / "b", [hebrew(0, BARE_TEXT)], None)

    assert "Dictionary forms on biblical Hebrew are less reliable" in scripture
    assert "Dictionary forms on biblical Hebrew" not in news, "a modern text is not warned"
    # Never in money, never in jargon: the sentence names what a reader would see go
    # wrong, not the tool that gets it wrong.
    assert "Stanza" not in scripture, "the reader is told the effect, not the dependency"


def test_the_page_carries_the_face_it_needs_and_not_the_other(tmp_path: Path) -> None:
    """A font a page merely names is a font some readers do not have.

    Two faces, one per shelf, and a page carries exactly one: paying for both would
    double the cost of the thing for no reader's benefit.
    """
    from targum.render.builder import BIBLICAL_FACE, MODERN_FACE

    segment = hebrew(0, TROPE_TEXT)
    voc = vocalization_for([segment], {segment.id: TROPE_TEXT}, [])
    scripture = render_with_vocalization(tmp_path / "a", [segment], voc, source="sefaria:Esther")
    news = render_with_vocalization(tmp_path / "b", [hebrew(0, BARE_TEXT)], None)

    # What matters is which face is *embedded*, not which names appear: `--reading-hebrew`
    # in reader.css still lists the faces worth reaching for, and one of them shares a
    # name with the face this shelf carries.
    def embedded(html: str) -> set[str]:
        return set(re.findall(r'@font-face\{font-family:"([^"]+)"', html))

    assert embedded(scripture) == {BIBLICAL_FACE[0]}, "scripture carries the wrong face"
    assert embedded(news) == {MODERN_FACE[0]}, "a modern text carries the wrong face"
    # One face per page, and one only: paying for both helps no reader.
    assert scripture.count("url(data:font/woff2") == 1
    assert news.count("url(data:font/woff2") == 1
    # And the face is actually reached for, not merely defined.
    assert f'--reading-hebrew:"{BIBLICAL_FACE[0]}"' in scripture
    # Carried in the page, not fetched. `test_loads_nothing_from_the_network` holds the
    # general rule; this says the font in particular obeys it.
    assert "url(data:font/woff2;base64," in scripture


def test_the_page_is_measured_again_when_the_face_arrives(tmp_path: Path) -> None:
    """A page measured in the wrong font is a page whose last verse falls off it.

    The face rides inside the page, but the browser still resolves it a beat after the
    first layout. Paginating before that happened put a verse outside the window — which
    the paging tests in `test_reader_browser.py` caught, and which this records so the
    two halves of the fix are not quietly separated later.
    """
    from targum.render.builder import ASSETS

    segment = hebrew(0, TROPE_TEXT)
    html = render_with_vocalization(
        tmp_path, [segment], vocalization_for([segment], {segment.id: TROPE_TEXT}, [])
    )
    # Nothing painted in a fallback, so nothing is measured in one either.
    assert "font-display:block" in html
    assert "font-display:swap" not in html

    script = (ASSETS / "reader.js").read_text(encoding="utf-8")
    assert "document.fonts.ready" in script, "the page never measures itself again"


def test_every_page_that_reads_hebrew_carries_a_face() -> None:
    """A page that carries the stylesheet carries the face, or it has neither.

    The face is per page rather than per stylesheet, because a page needs one of the two
    and paying for both helps nobody — which means a new template can be written, or an
    existing one rewritten, without it, and nothing would say so. The page would simply
    fall back to whatever the machine has, which for Hebrew on a stock Mac is a font with
    no accents in it. That is the whole bug this began as, so it is checked rather than
    remembered.
    """
    from targum.render.builder import ASSETS

    templates = sorted((ASSETS.parent / "templates").glob("*.j2"))
    assert templates, "no templates found"
    missing = [
        path.name
        for path in templates
        if "asset('reader.css')" in path.read_text(encoding="utf-8")
        and "hebrew_face(" not in path.read_text(encoding="utf-8")
    ]
    assert not missing, f"these carry the stylesheet but no Hebrew face: {', '.join(missing)}"


def test_the_embedded_faces_can_draw_every_mark(tmp_path: Path) -> None:
    """The check that would have caught this before a reader did.

    The reading font was New Peninim MT for years, which cannot draw one of the 31
    accents, nor meteg, paseq, sof pasuq or qamats qatan. Nothing said so until a
    Masoretic edition arrived and every accented letter came out in a borrowed font at a
    borrowed size. A face that cannot draw the text is not a candidate.
    """
    fontTools = pytest.importorskip("fontTools.ttLib", reason="fontTools reads the faces")
    from targum.render.builder import ASSETS, BIBLICAL_FACE, MODERN_FACE

    # Every mark and every letter a Hebrew page can hold, plus the maqaf that joins words,
    # the digits a modern sentence carries, and a Latin letter for a name in the middle.
    letters = list(range(0x05D0, 0x05EB)) + [0x05BE, ord("0"), ord("9"), ord(":"), ord("A")]
    # Everything a Masoretic text holds, against everything a modern one can. The two
    # differ by more than the accents: the masoretic dots (U+05C4, U+05C5) and the nun
    # hafukha (U+05C6) occur in scripture and nowhere else.
    masoretic = list(range(0x0591, 0x05C8))
    points = list(range(0x05B0, 0x05BE)) + [0x05BF, 0x05C1, 0x05C2, 0x05C7]

    # The biblical face has to draw everything a Masoretic text holds.
    cmap = fontTools.TTFont(ASSETS / BIBLICAL_FACE[1]).getBestCmap()
    missing = [f"U+{c:04X}" for c in letters + masoretic if c not in cmap]
    assert not missing, f"{BIBLICAL_FACE[1]} cannot draw {', '.join(missing[:8])}"

    # The modern face is only ever asked for text without accents — `builder.accented`
    # sends anything carrying one to the biblical face instead — so it owes the letters
    # and the vowel points, and nothing that belongs to scripture.
    cmap = fontTools.TTFont(ASSETS / MODERN_FACE[1]).getBestCmap()
    missing = [f"U+{c:04X}" for c in letters + points if c not in cmap]
    assert not missing, f"{MODERN_FACE[1]} cannot draw {', '.join(missing[:8])}"


def test_an_accented_text_keeps_its_accents_in_the_pointed_cell(tmp_path: Path) -> None:
    """The pointed cell is the whole text — vowels and accents together.

    This is the regression that matters and has never changed: whatever else the page
    offers, the cell the vowel switch reveals must be everything the edition wrote. A
    build that quietly dropped the accents from it would be publishing a different text.

    What did change, on 2026-09-01: scripture now ships a third cell as well, the vowels
    without the chanting marks, for `/parasha`. It is not the middle step of the vowel
    switch that existed for a day and went — that was one control with three positions,
    and the accents are their own two-position control now. See the note in
    `render/builder.py` and §12 of design.md.
    """
    segment = hebrew(0, TROPE_TEXT)
    html = render_with_vocalization(
        tmp_path, [segment], vocalization_for([segment], {segment.id: TROPE_TEXT}, [])
    )
    cells = re.findall(r'class="src (?:plain|pointed|unaccented)"[^>]*>(.*?)<', html)
    assert len(cells) == 3
    bare, pointed, unaccented = cells
    assert strip_nikkud(pointed)[0] == bare
    assert pointed == TROPE_TEXT, "the accents came off the pointed cell"
    # The third cell is the pointed one with the accents taken off and nothing else
    # touched: same letters, same vowels, no te'amim.
    assert unaccented == strip_taamim(TROPE_TEXT)
    assert strip_nikkud(unaccented)[0] == bare
    assert not has_taamim(unaccented)
    # The name the first attempt used is not the name this one uses, so a stale asset
    # cannot half-work.
    assert 'class="src trope"' not in html


def test_a_text_with_no_accents_ships_two_cells_and_one_switch(tmp_path: Path) -> None:
    """Every modern text is untouched by the third form.

    A newspaper has vowels and no cantillation, so there is nothing for the second
    control to do and it must not be drawn — which is what keeps "one switch, two
    positions" true everywhere except scripture.
    """
    pointed_text = "שָׁלוֹם עֲלֵיכֶם"
    assert not has_taamim(pointed_text)
    segment = hebrew(0, pointed_text)
    html = render_with_vocalization(
        tmp_path, [segment], vocalization_for([segment], {segment.id: pointed_text}, [])
    )
    cells = re.findall(r'class="src (?:plain|pointed|unaccented)"[^>]*>(.*?)<', html)
    assert len(cells) == 2, "no third cell where there are no accents to take off"
    assert 'data-form="unaccented"' not in html
    # The button, not the script that looks for it: reader.js is inlined into every page
    # and names the attribute whether or not the control is drawn.
    assert '<button type="button" data-taamim-toggle' not in html


def test_a_quoted_verse_keeps_its_accents_and_gets_the_face_for_them(tmp_path: Path) -> None:
    """One verse among many pointed sentences keeps its accents inside the pointed cell,
    and the page carries the face that can draw them — which face follows the text, not
    the shelf."""
    from targum.render.builder import BIBLICAL_FACE

    quote = hebrew(0, TROPE_TEXT)
    prose = [hebrew(i, BARE_TEXT) for i in range(1, 4)]
    segments = [quote, *prose]
    pointed = {quote.id: TROPE_TEXT}
    pointed.update({segment.id: POINTED_TEXT for segment in prose})
    html = render_with_vocalization(
        tmp_path, segments, vocalization_for(segments, pointed, [s.id for s in prose])
    )
    assert TROPE_TEXT in html
    assert f'@font-face{{font-family:"{BIBLICAL_FACE[0]}"' in html


def test_token_offsets_still_land_on_the_vowels_of_an_accented_text(tmp_path: Path) -> None:
    """Offsets are measured against the bare text, and there are now two pointed forms
    to map them onto. Both share one consonant skeleton, which is what makes one map do."""
    bare = strip_nikkud(TROPE_TEXT)[0]
    assert strip_nikkud(VOWELS_TEXT)[0] == bare
    # Every position in the bare text has a home in both pointed forms, and the two
    # agree on how many consonants there are — the thing markMap counts in the browser.
    for form in (VOWELS_TEXT, TROPE_TEXT):
        assert len([c for c in form if ord(c) not in MARKS]) == len(bare)


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


def test_every_catalogue_text_is_free_to_build_and_says_why() -> None:
    """The catalogue is the cheap half of targum, and there are two ways to be cheap.

    Most entries carry a `Rendering`: somebody published a translation, and a build asks
    no model for anything. The rest were translated once, by us, and paid for once — free
    to the second reader because public sources share a cache. That only holds if the
    build names the model the first one used, since the key is keyed on it. So an entry
    has to be one or the other, and never neither: neither means every reader pays.

    Words are checked because Wikisource is full of index pages that look like texts.
    """
    from targum.catalogue import CATALOGUE, by_id
    from targum.render.builder import library_page

    assert CATALOGUE, "an empty catalogue is a page with nothing on it"
    for entry in CATALOGUE:
        assert by_id(entry.id) is entry
        # A scene is the third way to be cheap: its English is authored beside the
        # Hebrew, so a build asks no model for anything and names none. And twenty
        # words is the whole of it, by design, not an index page.
        if entry.kind.value == "dialogue":
            assert not entry.translations and not entry.model, entry.id
            continue
        assert entry.translations or entry.model, f"{entry.id} would cost a reader money"
        assert not (entry.translations and entry.model), f"{entry.id} claims to be both"
        assert entry.words > 100, entry.id  # an index page, not a text

    # The cards are drawn in the browser, from the payload, so that picking a language
    # can filter them. What the page has to carry is the payload itself.
    html = library_page("k")
    payload = html.split("window.TARGUM_CATALOGUE = ", 1)[1].split("\n", 1)[0].rstrip(";")
    shipped = json.loads(payload)
    assert [entry["id"] for entry in shipped] == [entry.id for entry in CATALOGUE]
    for sent, entry in zip(shipped, CATALOGUE, strict=True):
        assert sent["title"] == entry.title
        assert sent["english"] == entry.english, "the title a reader with no Hebrew reads"
        assert sent["language"] == entry.language
        assert sent["translations"] == [
            {
                "name": t.name,
                "source": t.source,
                "note": t.note,
                "publisher": t.publisher,
                "licence": t.licence,
            }
            for t in entry.translations
        ], entry.id
        # The model is not the browser's business, and asking for one would be a way to
        # spend somebody else's money. The server reads it back from the catalogue.
        assert "model" not in sent, entry.id


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


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_only_hebrew_is_offered_on_the_reading_pages() -> None:
    """One language, for now. Everything those pages are made of is Hebrew — the
    difficulty bands, the word levels, the ulpan rungs — and a Russian view of them was
    the same page with most of it missing and a switcher inviting you into it.

    A remembered choice must not bring it back either: somebody who last looked at Russian
    has that code sitting in localStorage, and `current` would have handed it straight
    back if the list it picks from were not filtered first.
    """
    from targum.render.builder import ASSETS

    program = """
      global.window = {{}};
      global.localStorage = {{ getItem: () => "ru", setItem: () => {{}} }};
      require({where});
      const lang = window.TargumLang;
      const names = {{ he: "Hebrew", ru: "Russian", arc: "Aramaic" }};
      const shown = lang.order(["ru", "he", "arc"], names);
      console.log(JSON.stringify({{ shown, current: lang.current(shown) }}));
    """.format(where=json.dumps(str(ASSETS / "lang.js")))
    done = subprocess.run(["node", "-e", program], capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stderr
    answer = json.loads(done.stdout)

    assert answer["shown"] == ["he"], "the switcher hides itself at one, so this is the switch"
    assert answer["current"] == "he", "a remembered Russian choice cannot reopen it"


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_the_reading_pages_offer_what_the_account_says_is_being_learned() -> None:
    """The one above holds until the account answers. Once it has — `sync.js` mirrors
    the profile's answer into `targum:learning` — the switcher offers those and nothing
    else, and a remembered choice in one of them stands. Nothing is deleted by an
    unticked language: it is simply not offered."""
    from targum.render.builder import ASSETS

    program = """
      global.window = {{}};
      const stored = {{ "targum:learning": JSON.stringify(["he", "yi"]), "targum:language": "yi" }};
      global.localStorage = {{ getItem: (name) => stored[name] || null, setItem: () => {{}} }};
      require({where});
      const lang = window.TargumLang;
      const names = {{ he: "Hebrew", ru: "Russian", arc: "Aramaic", yi: "Yiddish" }};
      const shown = lang.order(["ru", "yi", "he", "arc"], names);
      console.log(JSON.stringify({{ shown, current: lang.current(shown) }}));
    """.format(where=json.dumps(str(ASSETS / "lang.js")))
    done = subprocess.run(["node", "-e", program], capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stderr
    answer = json.loads(done.stdout)

    assert answer["shown"] == ["he", "yi"], "what was ticked, Hebrew first, and no more"
    assert answer["current"] == "yi", "a remembered choice within them stands"


def test_every_page_shares_one_language_choice() -> None:
    """targum is a Hebrew app, and says so the same way on all three pages.

    The language you pick on the library page is the one your words page opens on, so
    the module that keeps that choice has to be on every page that offers it. Hebrew
    is the default and the only one not marked beta.
    """
    from targum.render.builder import add_page, learn_page, library_page, progress_page

    for html in (add_page("k"), learn_page("k"), progress_page("k"), library_page("k")):
        assert "TargumLang" in html, "the shared language choice is missing"
        assert 'HOME = "he"' in html

    start = add_page("k")
    # Hebrew is chosen for you; the others say how far along they are. "Beta" was one
    # word for every language that was not Hebrew; an upload picker that offers three
    # says which of them is which, and says it the same way the note under it does.
    assert '<option value="he" selected>' in start
    said = unescape(start)
    assert "(Experimental)" in said
    assert ">Hebrew (Experimental)<" not in said
    assert ">Hebrew (alpha)<" in start
    # One word in the picker, two behind it: the note says which kind of experimental.
    from targum.translate.prompts import stage_label

    assert stage_label("R&D") == stage_label("beta") == "Experimental"
    assert stage_label("alpha") == "alpha"


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
    assert data["extensions"] == {"roots": ["לבש", ""], "binyanim": ["התפעל", ""]}
    # Where the reader can go for the full tables, which are more than a page can carry.
    assert PEALIM in html


def test_how_a_word_is_built_and_conjugated_ride_in_tables_of_their_own(tmp_path: Path) -> None:
    """Both are facts about the occurrence, like the sound, and ride the same way: a
    table of distinct strings with an index on each token, index 0 meaning nothing to
    say. A reader with no Hebrew ships neither table at all."""
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
                    end=6,
                    surface="לביתו",
                    lemma="בית",
                    band=1,
                    split=True,
                    built="ל to + בית + his",
                    feats="Gender=Masc|Number=Sing",
                ),
                # The same grammar again: the table holds it once, both rows point at it.
                Token(
                    start=7,
                    end=10,
                    surface="ספר",
                    lemma="ספר",
                    band=1,
                    feats="Gender=Masc|Number=Sing",
                ),
                # Nothing to say on either count: both indices are 0.
                Token(start=10, end=11, surface="גם", lemma="גם", band=1),
            ]
        },
    )
    html = render(document, segmented, [translation], tmp_path / "r", annotation=annotation)[
        0
    ].read_text(encoding="utf-8")

    data = json.loads(re.search(r'id="targum-data"[^>]*>(.*?)</script>', html, re.S).group(1))
    assert data["built"] == ["", "ל to + בית + his"]
    assert data["grammar"] == ["", "Gender=Masc|Number=Sing"]
    rows = data["words"][segments[0].id]
    assert [row[7] for row in rows] == [1, 0, 0]
    assert [row[8] for row in rows] == [1, 1, 0]


def test_a_reader_with_nothing_built_ships_no_built_table(tmp_path: Path) -> None:
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
        tokens={segments[0].id: [Token(start=0, end=3, surface="גם", lemma="גם", band=1)]},
    )
    html = render(document, segmented, [translation], tmp_path / "r", annotation=annotation)[
        0
    ].read_text(encoding="utf-8")
    data = json.loads(re.search(r'id="targum-data"[^>]*>(.*?)</script>', html, re.S).group(1))
    assert "built" not in data
    assert "grammar" not in data


def test_citations_and_lying_plurals_ride_beside_the_lemmas(tmp_path: Path) -> None:
    """Facts about the source word itself, from whichever glossary holds them — they do
    not vary by target language. Left out entirely while no word on the page has one."""
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
        method_note="note",
        tokens={
            segments[0].id: [
                Token(start=0, end=5, surface="השתמש", lemma="השתמש", band=3),
                Token(start=6, end=9, surface="ספר", lemma="ספר", band=1),
            ]
        },
    )
    glossary = Glossary(
        source_language="he",
        target_language="en",
        provider="p",
        entries={"השתמש": "use", "ספר": "book"},
        citations={"השתמש": "להשתמש ב־"},
        plurals={"ספר": "ספרים"},
    )
    html = render(
        document,
        segmented,
        [translation],
        tmp_path / "r",
        annotation=annotation,
        glossaries={"en": glossary},
    )[0].read_text(encoding="utf-8")
    data = json.loads(re.search(r'id="targum-data"[^>]*>(.*?)</script>', html, re.S).group(1))
    assert data["citations"] == ["להשתמש ב־", ""]
    assert data["plurals"] == ["", "ספרים"]


def test_the_readings_ride_in_a_table_of_their_own(tmp_path: Path) -> None:
    """How a word is said belongs to the occurrence, so it cannot ride beside the lemmas.

    Both tokens here are the same dictionary form and are said differently — בצל is an
    onion in one sentence and shade in the other — which is the case a table keyed on the
    lemma gets wrong, silently, and only in the sentences a reader would notice.
    """
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
                Token(start=0, end=3, surface="בצל", lemma="בצל", band=2, ipa="batsˈal"),
                Token(start=4, end=7, surface="בצל", lemma="בצל", band=2, ipa="btsˈel"),
                # No vowels above it, so no reading, so index 0 — the empty first row
                # every token without one points at.
                Token(start=8, end=11, surface="עץ", lemma="עץ", band=1),
            ]
        },
    )
    html = render(document, segmented, [translation], tmp_path / "r", annotation=annotation)[
        0
    ].read_text(encoding="utf-8")

    data = json.loads(re.search(r'id="targum-data"[^>]*>(.*?)</script>', html, re.S).group(1))
    assert data["lemmas"] == ["בצל", "עץ"], "one dictionary form for the two בצל"
    assert data["sounds"] == ["", "batsˈal", "btsˈel"], "two readings of that one form"
    said = [row[5] for row in data["words"][segments[0].id]]
    assert said == [1, 2, 0]


def test_a_reader_with_nothing_to_say_ships_no_table(tmp_path: Path) -> None:
    """An empty table in every English reader is a cost with no reader behind it."""
    from targum.models import Annotation, Token

    segments = [paragraph(0)]
    segmented = make_segmented(segments)
    document = Document(source="m", title="T", language="en", blocks=[], content_hash="h")
    translation = Translation(
        name="Hebrew",
        document_hash="h",
        source_language="en",
        target_language="he",
        provider="null",
        segments={segments[0].id: "tr"},
    )
    annotation = Annotation(
        document_hash="h",
        language="en",
        annotator="t",
        method="frequency",
        method_note="note",
        tokens={segments[0].id: [Token(start=0, end=4, surface="tree", lemma="tree", band=1)]},
    )
    html = render(document, segmented, [translation], tmp_path / "r", annotation=annotation)[
        0
    ].read_text(encoding="utf-8")

    data = json.loads(re.search(r'id="targum-data"[^>]*>(.*?)</script>', html, re.S).group(1))
    assert "sounds" not in data


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
    two — the reader bakes its own and the vocabulary lists have another.
    """
    import re

    for name in ("reader.js", "lists.js"):
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
    building = source[source.index("var all = [lang.HOME]") :]
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


def test_a_commit_from_tomorrow_counts_as_today(monkeypatch) -> None:
    """Git prints the author's date in the author's timezone. A commit made late in the
    evening three hours east of UTC is dated tomorrow on a runner whose today is still
    today — and on a shallow checkout that one commit is the whole log. It has to land
    in the window, on its last day, rather than fall off the end and leave the page
    drawing nothing."""
    from datetime import date

    from targum import about

    monkeypatch.setattr(about, "_git", lambda *args: "2026-08-30\n2026-08-29\n")
    work = about._from_git(date(2026, 8, 29))
    assert len(work.days) == about.DAYS
    assert work.days[-1] == ("2026-08-29", 2), "the day from tomorrow did not land on today"
    assert work.commits == 2
    assert work.through == "29 August"


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
    assert "biblical = is_biblical(document.source)" in builder
    assert '"verse_by_verse": biblical,' in builder


# -- a verse answers to its address ----------------------------------------------


def verse(index: int, chapter: int, number: int) -> Segment:
    return Segment(
        id=f"{index:04d}.000-cccccc",
        block_id=f"b{index:04d}",
        block_index=index,
        index=0,
        kind=BlockKind.verse,
        text=f"וַיְהִי בִּימֵי {index}",
        ref=f"Ruth {chapter}:{number}",
    )


def tanakh(out: Path, first_chapter: int = 1, verses: int = 3) -> Path:
    """Two chapters of Ruth the way `sefaria/3` ingests them: a heading, then verses
    with their refs. From `first_chapter`, because a range does not start at one."""
    segments: list[Segment] = []
    for chapter in (first_chapter, first_chapter + 1):
        segments.append(heading(len(segments), 2, f"רות {chapter}"))
        for number in range(1, verses + 1):
            segments.append(verse(len(segments), chapter, number))
    document = Document(
        source="sefaria:Ruth", title="רות", language="he", blocks=[], content_hash="h"
    )
    segmented = SegmentedDocument(
        document_hash="h", language="he", segmenter="fake/1", segments=segments
    )
    translation = Translation(
        name="English",
        document_hash="h",
        source_language="he",
        target_language="en",
        provider="null",
        segments={s.id: f"[en] {s.text}" for s in segments},
    )
    render(document, segmented, [translation], out)
    return out


@pytest.mark.parametrize(
    ("ref", "address"),
    [
        ("Ruth 2:1", "2:1"),
        ("I Samuel 10:2", "10:2"),
        ("Song of Songs 1:1", "1:1"),
        ("Mishnah Berakhot 1:3", "1:3"),
        ("Psalms 119:176", "119:176"),
        # Not addresses: an imported recording's part still waiting for its transcript,
        # a chapter with no verse, and the nothing a prose block carries.
        ("Ruth 1:waiting", ""),
        ("Ruth 2", ""),
        ("", ""),
    ],
)
def test_a_verse_address_is_the_end_of_its_ref(ref: str, address: str) -> None:
    from targum.render.builder import verse_address

    assert verse_address(ref) == address


def test_a_verse_answers_to_its_address(tmp_path: Path) -> None:
    """Chapter:verse is how every learner of a Biblical text locates a line, so the row
    is `#2:1`, says which verse it is in the margin, and can hand its address on
    (targum-internal#28)."""
    folder = tanakh(tmp_path / "reader")
    second = (folder / "sec-0002.html").read_text(encoding="utf-8")
    row = re.search(r'<div class="pair verse[^"]*"[^>]*\bid="2:1"[^>]*>', second)
    assert row, "the row is the address"
    assert 'data-ref="Ruth 2:1"' in row.group(0)
    assert re.search(
        r'<a class="verse-number" href="#2:1" aria-label="Ruth 2:1" title="Ruth 2:1">1</a>',
        second,
    ), "the number stands in the margin and is a link to the verse"
    # The chapter's heading is the chapter's address, not a verse's.
    head = re.search(r'<div class="pair head[^"]*"[^>]*>', second)
    assert head and " id=" not in head.group(0)


def test_prose_has_no_address(rendered: Path) -> None:
    html = rendered.read_text(encoding="utf-8")
    assert 'class="verse-number"' not in html
    assert not re.search(r'<div class="pair[^"]*"[^>]* id="', html)


def test_the_contents_page_knows_which_file_holds_a_chapter(tmp_path: Path) -> None:
    """A range ingested from chapter 12 puts chapter 12 in the first file. The contents
    page carries the chapter numbers so `index.html#12:1` can go on to the right one."""
    folder = tanakh(tmp_path / "reader", first_chapter=12)
    index = (folder / "index.html").read_text(encoding="utf-8")
    assert '<li data-chapter="1" data-chapters="12" ' in index
    assert '<li data-chapter="2" data-chapters="13" ' in index


def portion(out: Path) -> Path:
    """A portion the way `targum parasha build` cuts one: chapter 16 runs across two
    aliyot, each under its own heading, so the chapter is two files and only the verse
    ranges know which file holds a verse."""
    segments: list[Segment] = []
    segments.append(heading(len(segments), 2, "ראשון"))
    for number in range(1, 4):
        segments.append(verse(len(segments), 16, number))
    segments.append(heading(len(segments), 2, "שני"))
    for number in range(4, 7):
        segments.append(verse(len(segments), 16, number))
    segments.append(heading(len(segments), 2, "שלישי"))
    for number in range(1, 3):
        segments.append(verse(len(segments), 17, number))
    document = Document(
        source="sefaria:Leviticus", title="אחרי מות", language="he", blocks=[], content_hash="h"
    )
    segmented = SegmentedDocument(
        document_hash="h", language="he", segmenter="fake/1", segments=segments
    )
    translation = Translation(
        name="English",
        document_hash="h",
        source_language="he",
        target_language="en",
        provider="null",
        segments={s.id: f"[en] {s.text}" for s in segments},
    )
    render(document, segmented, [translation], out)
    return out


def test_the_contents_page_knows_which_verses_each_file_holds(tmp_path: Path) -> None:
    """A portion's files are aliyot and a chapter runs across them, so the chapter
    number alone sends `index.html#16:5` to the first file of chapter 16, which does not
    hold verse 5. Each row carries its first and last verse so the script can pick the
    file that has the verse (targum-internal#142)."""
    folder = portion(tmp_path / "reader")
    index = (folder / "index.html").read_text(encoding="utf-8")
    assert '<li data-chapter="1" data-chapters="16" data-from="16:1" data-to="16:3">' in index
    assert '<li data-chapter="2" data-chapters="16" data-from="16:4" data-to="16:6">' in index
    assert '<li data-chapter="3" data-chapters="17" data-from="17:1" data-to="17:2">' in index


def test_a_book_of_one_chapter_a_file_carries_its_range_too(tmp_path: Path) -> None:
    folder = tanakh(tmp_path / "reader", first_chapter=12)
    index = (folder / "index.html").read_text(encoding="utf-8")
    assert '<li data-chapter="1" data-chapters="12" data-from="12:1" data-to="12:3">' in index
    assert '<li data-chapter="2" data-chapters="13" data-from="13:1" data-to="13:3">' in index


def test_a_file_with_no_verse_carries_no_range(tmp_path: Path) -> None:
    """Prose has no address, so a prose reader's rows say nothing about verses."""
    segments = [heading(0, 1, "One"), paragraph(1), heading(2, 1, "Two"), paragraph(3)]
    document = Document(source="memory", title="Book", language="he", blocks=[], content_hash="h")
    translation = Translation(
        name="English",
        document_hash="h",
        source_language="he",
        target_language="en",
        provider="null",
        segments={s.id: "x" for s in segments},
    )
    pages = render(document, make_segmented(segments), [translation], tmp_path / "reader")
    index = pages[0].read_text(encoding="utf-8")
    rows = re.findall(r"<li data-chapter=[^>]*>", index)
    assert rows == ['<li data-chapter="1">', '<li data-chapter="2">']


def torah(out: Path, monkeypatch: pytest.MonkeyPatch, corpus: Path | None) -> str:
    """Three chapters of Genesis — 5, 6 and 7 — and, where `corpus` is given, an index
    there with בראשית ending at 6:8 and נח beginning at 6:9. Returns the contents page."""
    from targum.parasha.models import Index, Portion

    if corpus is not None:
        corpus.mkdir(parents=True, exist_ok=True)
        index = Index(
            portions={
                "bereshit": Portion(
                    slug="bereshit",
                    name="Bereshit",
                    hebrew="בְּרֵאשִׁית",
                    numbers=[1],
                    summary="Genesis 1:1-6:8",
                    books=["Genesis"],
                    opening_ref="Genesis 1:1",
                ),
                "noach": Portion(
                    slug="noach",
                    name="Noach",
                    hebrew="נֹחַ",
                    numbers=[2],
                    summary="Genesis 6:9-11:32",
                    books=["Genesis"],
                    opening_ref="Genesis 6:9",
                ),
            }
        )
        (corpus / "index.json").write_text(index.model_dump_json(), encoding="utf-8")
        monkeypatch.setenv("TARGUM_PARASHA_DIR", str(corpus))
    else:
        monkeypatch.setenv("TARGUM_PARASHA_DIR", str(out / "nowhere"))

    segments: list[Segment] = []
    for chapter in (5, 6, 7):
        segments.append(heading(len(segments), 2, f"בראשית {chapter}"))
        for number in range(1, 11):
            segments.append(verse(len(segments), chapter, number))
    document = Document(
        source="sefaria:Genesis", title="בראשית", language="he", blocks=[], content_hash="g"
    )
    segmented = SegmentedDocument(
        document_hash="g", language="he", segmenter="fake/1", segments=segments
    )
    translation = Translation(
        name="English",
        document_hash="g",
        source_language="he",
        target_language="en",
        provider="null",
        segments={s.id: f"[en] {s.text}" for s in segments},
    )
    render(document, segmented, [translation], out / "reader")
    return (out / "reader" / "index.html").read_text(encoding="utf-8")


def test_a_torah_books_contents_page_groups_its_chapters_by_portion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Genesis 6 is listed once, under בראשית, which is where it starts; נח's own name
    goes to 6:9 in the file that holds chapter 6 (targum-internal #145)."""
    html = torah(tmp_path, monkeypatch, tmp_path / "parasha")

    assert re.findall(r'<li class="portion" data-portion="([^"]+)">', html) == [
        "bereshit",
        "noach",
    ]
    rows = re.findall(r'<li data-chapter="(\d+)" data-chapters="(\d+)"', html)
    assert rows == [("1", "5"), ("2", "6"), ("3", "7")], "every chapter, once"
    before, after = html.split('data-portion="noach"')
    assert 'data-chapters="6"' in before, "chapter 6 sits under the portion it starts in"
    assert 'data-chapters="7"' in after
    assert '<a class="portion-name" href="sec-0002.html#6:9">נֹחַ</a>' in html
    assert '<span class="portion-span">Genesis 6:9–11:32</span>' in html
    assert '<a class="portion-page" href="/parasha/noach" hidden>' in html
    # The inner lists carry the numbering on rather than starting again at one.
    assert '<ol start="1">' in before
    assert '<ol start="3">' in after
    # A first verse this range does not hold has only its address to point at.
    assert '<a class="portion-name" href="#1:1">' in before


def test_a_torah_book_with_no_corpus_lists_its_chapters_as_it_always_has(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The layer is data: with nothing built there is nothing to draw, and a fresh
    machine gets the page it got before the corpus existed."""
    html = torah(tmp_path, monkeypatch, None)
    # The body, not the page: the stylesheet is inlined into every reader and carries the
    # rules for a layer this page does not draw.
    body = html[html.index("<body") : html.index("</main>")]
    assert 'class="portion"' not in body
    assert "portion-" not in body
    # The rows carry the verse range each file holds, the way every other contents
    # page does since a verse link learned to land on the file that has it — the
    # portion layer is what a machine with no corpus goes without, not the range.
    assert '<li data-chapter="1" data-chapters="5" data-from="5:1" data-to="5:10">' in html
    assert '<li data-chapter="3" data-chapters="7" data-from="7:1" data-to="7:10">' in html


def test_the_contents_script_keeps_the_key_in_front_of_a_verse_hash() -> None:
    """`sec-0006.html?k=…#6:9`, not `sec-0006.html#6:9?k=…` — and a portion's own page
    is a route, which needs no key and is offered only where there is a server."""
    from targum.render.builder import ASSETS

    contents = (ASSETS / "contents.js").read_text(encoding="utf-8")
    assert "href.slice(0, cut) + suffix + href.slice(cut)" in contents
    assert 'href.charAt(0) === "/"' in contents
    assert '".toc .portion-page"' in contents


def test_the_scripts_take_a_verse_link_the_rest_of_the_way() -> None:
    """The scrolling reader lands on an id by itself. The pages do not — a verse on
    another page is not rendered — and the contents page has to pick the file."""
    from targum.render.builder import ASSETS

    reader = (ASSETS / "reader.js").read_text(encoding="utf-8")
    assert 'window.addEventListener("hashchange", arrive);' in reader
    boot = reader[reader.index("  resume();\n") :]
    assert "arrive();" in boot[: boot.index("took(")], "after the layout, like resume"
    assert "if (paged()) turnTo(pair);" in reader[reader.index("function jumpToPair") :]

    contents = (ASSETS / "contents.js").read_text(encoding="utf-8")
    assert "[data-from]" in contents, "a verse takes the file whose range holds it"
    assert "[data-chapters~=" in contents, "a chapter, or a verse no file holds, the chapter's"
    assert "location.replace(row.href + hash);" in contents


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

    It was one hue, a fainter accent at each step, and the first alpha reader said what
    that did: "the words I clicked on need to change colour, now I can hardly see them."
    So it is two. Unmet is accent, the loudest thing on the page; the three working
    levels are leaf — §4's colour for progress — and still descend, so the page still
    clears as you learn it, but a word you are working on is a colour, not an absence.
    Decided 2026-08-28.
    """
    css = _reader_css()
    assert "body.marking .w:not([data-status])" in css, "never-marked words carry the top step"

    def wash(selector: str, hue: str) -> int:
        rules = css.split(selector, 1)[1].split("}", 1)[0]
        found = re.search(r"background:.*?var\(--" + hue + r"\) (\d+)%", rules)
        return int(found.group(1)) if found else 0

    fresh = wash("body.marking .w:not([data-status])", "accent")
    one = wash('body.marking .w[data-status="1"]', "leaf")
    two = wash('body.marking .w[data-status="2"]', "leaf")
    three = wash('body.marking .w[data-status="3"]', "leaf")
    # §4 caps a wash at 22%; the unmet word takes all of it and nothing else comes near.
    assert fresh == 22, "the unmet word is the loudest thing on the page"
    assert fresh > one > two > three > 0, "saying more about a word makes it quieter"
    assert wash('body.marking .w[data-status="1"]', "accent") == 0, "your words are not accent"

    # Every working level keeps its underline: leaf and accent are near neighbours
    # under protanopia at these washes, and a mark never rests on colour alone.
    for level in ("1", "2", "3"):
        rules = css.split(f'body.marking .w[data-status="{level}"]', 1)[1].split("}", 1)[0]
        assert "box-shadow: inset 0 -1px 0" in rules, f"level {level} has no underline"

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
    stats = script[script.index("function renderStats()") : script.index("function countInto(")]
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
    stats = script[script.index("function renderStats()") : script.index("function countInto(")]
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
    # Through `seatNear`, which is `placeNear` on a wide window and the band at the foot
    # on a narrow one — see the phone rules at the foot of reader.css.
    assert "seatNear(card, word.getBoundingClientRect());" in script
    # The phrase card already did this; one placer now, so the two cannot drift.
    assert script.count("function placeNear(") == 1
    assert "seatNear(chip, rect)" in script
    assert script.count("placeNear(element, rect);") == 1, "and only seatNear calls it"

    css = _reader_css()
    rules = css.split(".gloss-card {", 1)[1].split("}", 1)[0]
    assert "position: absolute" in rules, "it has to scroll with the word"
    assert "inset-block-end" not in rules, "no longer pinned to the window"


def test_the_level_keys_are_the_letters_outright() -> None:
    """`k` is known and `i` is ignore, and that is the whole of what either one does. They
    used to be lent to the levels while a word was in hand and given back to
    previous-sentence and interlinear the moment it was not, which meant the same key did
    different things depending on a state the page never showed.

    A word under the arrows counts, card or no card. Saying how well you know a word is
    an answer you already had — the card is a question you have to ask for, and needing
    it open first would have made every decision two keypresses.
    """
    from targum.render.builder import ASSETS

    script = (ASSETS / "reader.js").read_text(encoding="utf-8")
    assert "var KEYED_STATUS = { 1: 1, 2: 2, 3: 3, 4: KNOWN, k: KNOWN, i: IGNORED };" in script
    # The word the arrows are on, or failing that the one a pointer opened a card about.
    assert "var word = standing || (lookedUp && card && !card.hidden ? lookedUp : null);" in script
    assert "if (pickLevel && chip && !chip.hidden) {" in script, "and the phrase card"
    # Nothing downstream can claim them back.
    keys = script[script.index("switch (key) {") :]
    assert 'case "k":' not in keys and 'case "i":' not in keys

    # A bare lookup would treat "constructor" as a level.
    assert "hasOwnProperty.call(KEYED_STATUS, key)" in script


def test_the_level_keys_are_written_down() -> None:
    from targum.render.builder import ASSETS

    template = (ASSETS.parent / "templates/reader.html.j2").read_text(encoding="utf-8")
    assert "<dt>1 2 3</dt>" in template
    # One key a row: `k` and `i` shared a row while they shared their letters.
    assert "<dt>k 4</dt><dd>known</dd>" in template
    assert "<dt>i</dt><dd>ignore it" in template


def test_the_growth_line_leaves_out_what_was_ignored() -> None:
    """ "Words kept over time" drew every word with a date on it, ignored ones included.
    The line is stubbed in the node harness because it draws into an SVG, so the rule is
    pinned here instead."""
    from targum.render.builder import ASSETS

    charts = (ASSETS / "charts.js").read_text(encoding="utf-8")
    body = charts[charts.index("function drawGrowth(host, words) {") :]
    assert "kept(words).filter(function (word) {" in body[: body.index("\n  }\n")]
    # And the one place that decides it, so the four charts cannot drift apart.
    assert "return word.status !== IGNORED;" in charts


def test_taking_a_mark_off_is_asked_for_rather_than_inferred() -> None:
    """`setStatus` used to decide it was a second press by re-reading the store — and
    `setNote` writes a record at level 1 on its way past, so it saw the level it had just
    written itself. Typing a definition and then saying "just met it" deleted the word and
    the definition together, which is the one combination a reader is most likely to use.
    """
    from targum.render.builder import ASSETS

    script = (ASSETS / "reader.js").read_text(encoding="utf-8")
    body = script[script.index("function setStatus(index, surface, band, status) {") :]
    body = body[: body.index("\n  }\n")]
    assert "var current = statusOf(lemma);" not in body, "nothing is inferred from the store"
    assert "if (status === null || status === undefined) {" in body

    # The callers that do want a toggle say so, and ask before anything has been written.
    assert (
        "function toggled(index, status) {\n    return statusOf(lemmas[index]) === status" in script
    )
    assert "setStatus(index, surface, band, value);" in script, "the card's own row"
    # The keys do not toggle. The back arrow lands on words already marked, and a level
    # pressed to confirm one took the mark off instead and walked on — silently.
    assert "setStatus(index, surface, levelOf(word), status);" in script, "the keys"
    assert "setStatus(index, surface, levelOf(word), toggled(index, status));" not in script


def test_the_phrase_card_lets_its_own_field_take_focus() -> None:
    """Preventing the default on mousedown is exactly what stops the browser moving
    focus. The card does it to keep a mousedown on itself from collapsing the selection
    it was opened for — but applied to the whole card it also meant the note field could
    never be clicked into, so the caret never arrived and nothing typed went anywhere.

    Safe to exempt: the mouseup handler already ignores everything inside the chip, so
    the card does not close when the selection collapses under the caret.
    """
    from targum.render.builder import ASSETS

    script = (ASSETS / "reader.js").read_text(encoding="utf-8")
    down = script[script.index('chip.addEventListener("mousedown"') :]
    down = down[: down.index("});")]
    assert "/^(INPUT|SELECT|TEXTAREA)$/.test(to.tagName)) return;" in down
    assert down.index("return;") < down.index("event.preventDefault();")
    # The half that makes the exemption safe.
    up = script[script.index('document.addEventListener("mouseup"') :]
    assert "if (chip.contains(event.target)) return;" in up[: up.index("});")]


def test_no_name_in_the_reader_is_both_a_function_and_a_variable() -> None:
    """`var x` and `function x` in one scope are one binding, not two. The function is
    hoisted, the assignment runs straight over it, and every call after that throws
    `x is not a function` — at runtime, in one feature, silently.

    This is not hypothetical. The word queue introduced `var place` for the position it
    is standing on, into a scope that already had `function place` positioning the phrase
    chip. `placeNear` is the only thing that takes the chip out of `hidden`, so dragging
    a phrase stopped working outright and nothing said so.
    """
    from targum.render.builder import ASSETS

    script = (ASSETS / "reader.js").read_text(encoding="utf-8")
    # Per IIFE, not per file: this reader is several, and a name in one says nothing
    # about the same name in another. Two spaces inside one of them is its own scope.
    for part in script.split("\n})();"):
        declared = re.findall(r"^  function (\w+)\(", part, re.M)
        assigned = re.findall(r"^  var (\w+)\b", part, re.M)
        clash = sorted(set(declared) & set(assigned))
        assert not clash, f"declared as both a function and a variable: {clash}"


def test_dragging_a_phrase_shows_the_chip() -> None:
    """Filling the chip and showing it are two different calls, and only the second one
    puts it on the screen — `pickCard` writes the content into an element that is still
    `hidden`."""
    from targum.render.builder import ASSETS

    script = (ASSETS / "reader.js").read_text(encoding="utf-8")
    body = script[script.index("function showPick(picked)") : script.index("/* --- export ---")]
    # Both branches: a drag over one word, and a drag over several.
    assert body.count("placeChip(picked.rect);") == 2
    assert 'function placeChip(rect) {\n    occupy("chip");\n    seatNear(chip, rect);' in script
    assert "element.hidden = false;" in script[script.index("function placeNear(") :]


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
    # Each branch redraws it, and so does Keep: the card comes back with the scale on.
    # And a phrase's meaning arriving from the server redraws it once more, so the card
    # that said "looking…" is the one that says what came.
    assert body.count("showPick(picked);") == 4, "each redraws it"
    # And it stops being live the moment the card goes. There is one way to put the chip
    # away and it takes the keys down with it, because the two being separate lines meant
    # remembering them together at four call sites — and a level pressed at a phrase
    # nobody can see any more would be saved against it all the same.
    assert script.count("chip.hidden = true;") == 1, "more than one way to hide the chip"
    one_way = r"function hideChip\(\) \{\n[^}]*chip\.hidden = true;\n[^}]*pickLevel = null;"
    assert re.search(one_way, script), "hiding the chip does not take the keys down with it"
    assert script.count("hideChip()") >= 4, "somewhere hides the chip without going through it"


def test_a_phrase_asks_only_where_the_page_can() -> None:
    """A few words selected ask the server what they mean against the sentence's
    translation, so the card can quote the parallel text instead of stringing glosses
    together. Same origin, and only behind `canAsk()`: a page opened off the disk fetches
    nothing, and `test_loads_nothing_from_the_network` stays true of it."""
    from targum.render.builder import ASSETS

    script = (ASSETS / "reader.js").read_text(encoding="utf-8")
    ask = script[script.index("function askPhrase(picked") : script.index("function statusOf(")]
    assert ask.index("canAsk()") < ask.index('fetch(keyed("/phrase")'), "asked before it can"
    assert "translation: translationFor(picked.segmentId)" in ask, "the parallel text goes too"
    pending = script[
        script.index("function phrasePending(picked)") : script.index("function askPhrase(")
    ]
    assert "canAsk()" in pending and "translationFor(picked.segmentId)" in pending
    # The caption says only what is still owed or standing in — never provenance:
    # "in the parallel text" and "as it is used here" told the reader where an answer
    # came from, which nobody could act on. Removed 2026-08-31.
    chip = script[script.index("function showPick(picked)") : script.index("/* --- export ---")]
    for caption in (
        "word by word — looking…",
        "word by word — the sentence is in parallel",
    ):
        assert caption in chip, caption
    for gone in ("in the parallel text", "as it is used here"):
        assert gone not in chip, gone
    # An answer that lands after Keep reaches the kept phrase, and the card is restated
    # only if it is still open on that selection.
    assert "keepMeaning(phraseTerm(item), answer.meaning, into);" in chip
    assert "if (picking === picked) showPick(picked);" in chip
    assert "picking = null;" in script[script.index("function hideChip()") :]


def test_a_quoted_phrase_is_marked_in_the_parallel_text() -> None:
    """The caption "in the parallel text" points at something: while the card quotes a
    piece of the translation, that piece is marked in the translation cell, in the
    phrase hue as a flat wash (§4), and unmarked the moment the card goes or another
    one opens."""
    from targum.render.builder import ASSETS

    script = (ASSETS / "reader.js").read_text(encoding="utf-8")
    sheet = (ASSETS / "reader.css").read_text(encoding="utf-8")
    rule = sheet[sheet.index(".tr .echo {") : sheet.index("}", sheet.index(".tr .echo {"))]
    assert re.search(r"var\(--iris\) (1[2-9]|2[0-2])%", rule), "the wash is iris, 12–22%"
    assert "transition" not in rule and "gradient" not in rule, "flat"
    chip = script[script.index("function showPick(picked)") : script.index("/* --- export ---")]
    assert "if (held && held.quoted) echoIn(picked.segmentId, held.meaning);" in chip
    assert chip.index("unecho();") < chip.index("var touching"), "the last mark goes first"
    hide = script[
        script.index("function hideChip()") : script.index('document.addEventListener("mouseup"')
    ]
    assert "unecho();" in hide, "hiding the chip leaves the mark behind"
    # Around characters, not across elements: the cell wraps opposite-direction runs.
    echo = script[script.index("function echoIn(") : script.index("function pickCard(")]
    assert "createTreeWalker(cell, NodeFilter.SHOW_TEXT)" in echo
    assert 'document.createElement("mark")' in echo


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
    for name in (
        "function lemmasHere(everything)",
        "function coverage()",
        "function wordEntries()",
    ):
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
    # And not written down: what the page took to draw is for whoever is building targum,
    # not for whoever is reading, so the card a reader opens does not offer it.
    template = (ASSETS.parent / "templates/reader.html.j2").read_text(encoding="utf-8")
    assert "<dt>t</dt>" not in template
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
    assert "var DEFAULTS = 4;" in script
    # 3: pages, for every browser that had a preference from before there were pages.
    # Decided 2026-08-28 — the first alpha reader is the target reader and asked twice.
    assert "var RESET = { marking: true, paged: true };" in script
    assert "if ((prefs.defaults || 0) < DEFAULTS) {" in script
    # Stored, or it re-applies on every load and the reader can never turn it off.
    reset = script[script.index("if ((prefs.defaults || 0) < DEFAULTS) {") :][:600]
    # The fourth generation hands pages back on a narrow window only: a choice made on
    # a wide window was made in a bar with room for the button, and stands.
    assert '(max-width: 60rem)").matches) prefs.paged = true;' in reset
    assert "if ((prefs.defaults || 0) < 3) for (var changed in RESET)" in reset
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
    # Matched on the attribute, not on `:lang(he)`. `:lang()` matches an element's
    # *inherited* language, so on a reader whose <html> says lang="he" it also matched
    # <body> and every wrapper — outranking the font-family on `body` — and the English
    # translation column inherited the Hebrew face. Harmless while that stack could not
    # draw Latin at all; the day the page carried a Hebrew face with Latin glyphs, every
    # translation on the shelf was set in them.
    assert '[lang|="he"]:not(html) { font-family: var(--reading-hebrew); }' in css
    assert ":lang(he) { font-family: var(--reading-hebrew); }" not in css


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
                stray.append(
                    f"{name} scope {n} reads {const}, declared in {owner} scope {owner_scope}"
                )
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


def test_the_speed_is_a_pair_in_the_player_and_only_where_there_is_a_voice(
    rendered: Path,
) -> None:
    """A step down, the number, a step up. Typed rather than drawn — §7 has − and + as
    themselves, and × after a number as a multiplier — and in the player, not the bar."""
    from targum.render.builder import ASSETS

    template = (ASSETS.parent / "templates/reader.html.j2").read_text(encoding="utf-8")
    player = re.search(r'<div class="player".*?</div>', template, re.S)
    assert player is not None
    card = player.group(0)
    assert '<button type="button" class="player-slower" aria-label="Slower">−</button>' in card
    assert '<button type="button" class="player-faster" aria-label="Faster">+</button>' in card
    assert 'class="player-rate" role="group" aria-label="Speed"' in card
    assert ">1×<" in card, "the reading's own pace, to begin with"
    assert ">-<" not in card, "a minus sign, not a hyphen"
    assert card.index("player-rate") < card.index("player-get"), "before the download"

    # The keys card lists them beside Space, under the same guard.
    guard = r"{% if spoken_audio %}<dt>Space</dt>.*?"
    keys = r"<dt>&lt; &gt;</dt><dd>slower, faster</dd>{% endif %}"
    assert re.search(guard + keys, template, re.S)

    # A text with no voice has no player and so no speed, and the keys card does not
    # promise keys that do nothing. (The stylesheet rides in every page; the markup is
    # what is looked for.)
    silent = rendered.read_text(encoding="utf-8")
    assert 'class="player-slower"' not in silent
    assert "&lt; &gt;" not in silent


def test_the_vowel_control_is_one_switch_not_two_choices(tmp_path: Path) -> None:
    """It is a thing that is on or off. Two buttons made a scale out of it, and for a day
    a third position did the same in one button."""
    controls = _reader_controls(tmp_path)
    assert controls.count("data-nikkud") == 1
    assert 'data-nikkud="on"' not in controls and 'data-nikkud="off"' not in controls

    vowels = re.search(r"<button\b[^>]*data-nikkud-toggle.*?</button>", controls, re.S)
    assert vowels is not None
    assert 'aria-pressed="false"' in vowels.group(0)
    assert "data-step" not in vowels.group(0)
    assert 'class="dots"' in vowels.group(0)

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


def test_a_bought_text_names_the_model_that_makes_it_free() -> None:
    """Public sources share a cache, so the second reader of a text targum translated
    pays nothing — but the key is keyed on the model among other things, and a hosted
    build asks for Sonnet. The prose canon was bought on Opus. Without this the whole
    book would be translated again, per reader, silently.
    """
    from targum.catalogue import BOUGHT_WITH, CATALOGUE

    bought = [e for e in CATALOGUE if e.model]
    assert bought, "the prose canon is in the catalogue"
    assert {e.model for e in bought} == {BOUGHT_WITH}, "one place says what bought them"

    from targum.render.builder import ASSETS

    server = (ASSETS.parents[1] / "serve.py").read_text(encoding="utf-8")
    # Read from the catalogue, never from the request.
    assert "entry = catalogue_module.matching(job.source)" in server
    assert "model=(entry.model if entry and entry.model else HOSTED_MODEL)," in server
    assert '"model"' not in server.split("def _builder")[1].split("def ")[1][:400]


def test_the_upsell_only_fires_when_there_is_something_better() -> None:
    """A bought text has no published translation to point at. Offering it as an
    alternative to itself left the catalogue's own button unable to build it."""
    from targum.render.builder import ASSETS

    server = (ASSETS.parents[1] / "serve.py").read_text(encoding="utf-8")
    assert "if already is not None and already.translations:" in server


def test_a_bought_book_is_free_to_the_second_reader(tmp_path: Path) -> None:
    """The whole argument for buying a text once: public sources share a cache.

    It holds a translation under the exact run of segments it was asked for. Bought from
    the command line a book is one run — the whole thing — and served it is bought a
    chapter at a time, so a reader's build asked for a key that was never written and
    paid again for a book already sitting on the disk. `targum warm` writes the
    chapter-shaped keys from the English already bought.

    Checked here on a book made up for the purpose, so it does not depend on what happens
    to be in anybody's cache.
    """
    from targum.cache import Cache
    from targum.models import BlockKind, Segment, SegmentedDocument
    from targum.pipeline import Build
    from targum.translate.base import Style

    segments = []
    for c in (1, 2):
        segments.append(
            Segment(
                id=f"h{c}",
                block_id=f"b{c}",
                block_index=c,
                index=len(segments),
                text=f"Chapter {c}",
                kind=BlockKind.heading,
                level=1,
            )
        )
        for n in range(3):
            segments.append(
                Segment(
                    id=f"s{c}-{n}",
                    block_id=f"b{c}",
                    block_index=c,
                    index=len(segments),
                    text=f"line {n} of chapter {c}",
                    kind=BlockKind.paragraph,
                )
            )
    segmented = SegmentedDocument(
        document_hash="b", language="he", segmenter="t/1", segments=segments
    )

    def build(model: str) -> Build:
        return Build(
            "https://example.org/book.txt",
            target_language="en",
            source_language="he",
            style=Style.natural,
            model=model,
            owner="",
        )

    cache = Cache(tmp_path / "cache")
    bought, hosted = build("claude-opus-5"), build("claude-sonnet-5")
    chapter = bought.chapter_segments(segmented, 1)
    assert chapter, "the book has chapters"

    # What `warm` writes: the chapter run, under the model it was bought with.
    cache.put(
        "translate",
        bought.cache_key(segmented, chapter),
        {"segments": {s.id: "x" for s in chapter}},
    )

    assert cache.get("translate", bought.cache_key(segmented, chapter)) is not None
    # And the same request under the hosted default finds nothing, which is the whole
    # reason the catalogue names the model.
    assert cache.get("translate", hosted.cache_key(segmented, chapter)) is None


def test_a_sentence_with_no_points_still_shows_its_source(tmp_path: Path) -> None:
    """A vocalizer does not always reach every sentence — Judenstaat came out 123 of 1080
    pointed. The stylesheet hid the bare form whenever vowels were on, so those pairs had
    no source at all, and the translation fell into the first grid column, which on an RTL
    page is the right one. It read as a mirrored, broken layout; it was a missing one.
    """
    pointed_one, bare_one = hebrew(0, BARE_TEXT), hebrew(1, BARE_TEXT + " ב")
    html = render_with_vocalization(
        tmp_path,
        [pointed_one, bare_one],
        vocalization_for([pointed_one], {pointed_one.id: POINTED_TEXT}, [pointed_one.id]),
    )
    pairs = dict(re.findall(r'<div class="(pair[^"]*)" data-id="([^"]+)"', html))
    pairs = {sid: cls for cls, sid in pairs.items()}
    assert "points" in pairs[pointed_one.id], "this one has a pointed form"
    assert "points" not in pairs[bare_one.id], "and this one does not"

    css = _reader_css()
    assert "body.nikkud .pair.points .src.plain { display: none; }" in css
    assert "body.nikkud .src.plain { display: none; }" not in css, "never unconditionally"


# -- a drawn cover, inlined ------------------------------------------------------


def cover_at(where: Path, name: str) -> Path:
    """A cover on disk, as the drawing step would leave one."""
    from io import BytesIO

    from PIL import Image

    where.mkdir(parents=True, exist_ok=True)
    made = BytesIO()
    Image.new("RGB", (320, 480), (170, 140, 100)).save(made, format="WEBP")
    drawn = where / f"{name}.webp"
    drawn.write_bytes(made.getvalue())
    return drawn


def book(tmp_path: Path, **extra: object) -> list[Path]:
    """A rendered book — two chapters, so it has a contents page for a cover to sit on —
    for a text the catalogue describes, since that is what a cover is drawn from."""
    from targum.catalogue import CATALOGUE

    entry = next(e for e in CATALOGUE if e.id == "psalms")
    segments = [heading(0, 1, "One"), paragraph(1), heading(2, 1, "Two"), paragraph(3)]
    segmented = make_segmented(segments)
    document = Document(
        source=entry.source, title=entry.title, language="he", blocks=[], content_hash="h"
    )
    translation = Translation(
        name="English",
        document_hash="h",
        source_language="he",
        target_language="en",
        provider="null",
        segments={s.id: "x" for s in segments},
    )
    return render(document, segmented, [translation], tmp_path / "reader", **extra)  # type: ignore[arg-type]


def test_the_contents_page_carries_the_cover(tmp_path: Path) -> None:
    """A reader off a disk has nowhere to fetch from, so the picture rides inside it —
    the same way the icons already do."""
    covers = tmp_path / "thumbs"
    cover_at(covers, "psalms")

    pages = book(tmp_path, covers=covers)

    contents = pages[0].read_text(encoding="utf-8")
    assert pages[0].name == "index.html"
    assert '<figure class="cover">' in contents
    assert 'src="data:image/webp;base64,' in contents

    chapter = pages[1].read_text(encoding="utf-8")
    assert '<figure class="plate">' in chapter, "and a stamp on the chapter"
    assert '<figure class="cover">' not in chapter, "the big one belongs to the contents"


def test_a_text_with_no_cover_drawn_says_nothing_about_it(tmp_path: Path) -> None:
    """Covers arrive one at a time and over months. A reader without one is a reader."""
    for page in book(tmp_path, covers=tmp_path / "thumbs"):
        html = page.read_text(encoding="utf-8")
        assert "<figure" not in html
        assert "data:image/webp" not in html


def test_a_cover_is_never_something_the_page_goes_and_gets(tmp_path: Path) -> None:
    covers = tmp_path / "thumbs"
    cover_at(covers, "psalms")

    for page in book(tmp_path, covers=covers):
        html = page.read_text(encoding="utf-8")
        for position in (r'src\s*=\s*["\']', r"url\(", r'<link[^>]+href\s*=\s*["\']'):
            assert not re.search(position + r"(https?:)?//", html, re.I)


def test_a_chapter_carries_a_smaller_one_than_the_contents_page(tmp_path: Path) -> None:
    """A book of a hundred and fifty chapters would otherwise put three megabytes of the
    same picture into one reader."""
    from targum.render.builder import cover_uri, plate_uri

    covers = tmp_path / "thumbs"
    cover_at(covers, "psalms")

    whole = cover_uri(covers, "psalms")
    plate = plate_uri(covers, "psalms")

    assert whole.startswith("data:image/webp;base64,")
    assert plate.startswith("data:image/webp;base64,")
    assert len(plate) < len(whole) / 2, "the stamp is a fraction of the cover"
    assert (covers / "small" / "psalms.webp").is_file(), "and is shrunk once, not per page"


def test_a_chapter_falls_back_to_its_book(tmp_path: Path) -> None:
    """Most chapters are numbered rather than titled and have no cover of their own."""
    from targum.render.builder import plate_uri

    covers = tmp_path / "thumbs"
    cover_at(covers, "psalms")

    assert plate_uri(covers, "psalms-c007") == "", "nothing drawn for this chapter"
    assert plate_uri(covers, "psalms") != "", "so the page uses the book's"


# -- the word queue the arrows walk -----------------------------------------------


def test_the_arrows_are_the_whole_of_the_navigation() -> None:
    """A word at a time, and nothing else. Stepping sentences was a second way through the
    text that shared `k` and `i` with the levels, so neither key meant one thing."""
    from targum.render.builder import ASSETS

    script = (ASSETS / "reader.js").read_text(encoding="utf-8")
    keys = script[script.index("switch (key) {") :]
    assert 'case "ArrowRight":\n        if (!walk(!rtl)) return;' in keys
    assert 'case "ArrowLeft":\n        if (!walk(rtl)) return;' in keys
    # Nothing steps a sentence any more, by any key.
    assert "function move(" not in script, "sentence stepping is gone, not just unbound"
    for gone in ('case "ArrowDown":', 'case "ArrowUp":', 'case "j":'):
        assert gone not in keys, f"{gone} steps sentences"
    # And unhandled means the browser's: a reader with nothing to mark gets scrolling
    # back, which is what this file used to take away.
    assert "function walk(forward) {\n    if (!card) return false;" in script


def test_no_key_does_two_things() -> None:
    """`k` is known and `i` is ignore, on a word, and neither can also be something else.
    Interlinear moved to `l` — the translation under each line — because `i` was spoken
    for."""
    from targum.render.builder import ASSETS

    script = (ASSETS / "reader.js").read_text(encoding="utf-8")
    keys = script[script.index("switch (key) {") :]
    # The level keys are read before the switch and never reach it.
    assert "var KEYED_STATUS = { 1: 1, 2: 2, 3: 3, 4: KNOWN, k: KNOWN, i: IGNORED };" in script
    for taken in ('case "k":', 'case "i":'):
        assert taken not in keys, f"{taken} is a level, and cannot be anything else"
    assert 'case "l":\n        prefs.mode = "inter";' in keys


def test_the_queue_never_reads_the_page() -> None:
    """Most of a chapter's word spans do not exist — `markSegment` draws a screenful and
    leaves the rest until it is scrolled to — so a queue built by asking the document
    which words are on it would stop at the bottom of the first screen."""
    from targum.render.builder import ASSETS

    script = (ASSETS / "reader.js").read_text(encoding="utf-8")
    body = script[script.index("function buildQueue() {") : script.index("var segmentAt")]
    assert "querySelector" not in body and "document." not in body
    assert "Object.keys(wordData)" in body
    # Everything neither known nor ignored, which is `fresh` plus `learning`.
    assert "if (status === KNOWN || status === IGNORED) return;" in body
    # A text using the word "constructor" would otherwise skip every word in it.
    assert "Object.prototype.hasOwnProperty.call(seen, lemma)" in body


def test_the_embedded_words_come_out_in_reading_order(tmp_path: Path) -> None:
    """The queue takes the order sentences read in from the order they arrive in, having
    no other way to compare two opaque segment ids. Nothing else depended on it, so
    nothing else would have noticed it changing."""
    from targum.models import Annotation, Token

    segments = [paragraph(index) for index in range(4)]
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
    annotation = Annotation(
        document_hash="h",
        language="he",
        annotator="t",
        method="frequency",
        method_note="note",
        # Deliberately not in document order: what is embedded has to be sorted by the
        # builder rather than by whatever order the annotator happened to finish in.
        tokens={
            segment.id: [Token(start=0, end=5, surface="בית", lemma=f"w{n}", band=1)]
            for n, segment in reversed(list(enumerate(segments)))
        },
    )
    html = render(document, segmented, [translation], tmp_path / "r", annotation=annotation)[
        0
    ].read_text(encoding="utf-8")

    data = json.loads(re.search(r'id="targum-data"[^>]*>(.*?)</script>', html, re.S).group(1))
    assert list(data["words"]) == [segment.id for segment in segments]


def test_a_queued_word_wears_the_focus_ring() -> None:
    """A word you tapped and a word the arrows are standing on are not the same thing,
    and only one of them is holding the keyboard."""
    css = _reader_css()
    rules = css.split(".w.queued {", 1)[1].split("}", 1)[0]
    # §8's ring, not a colour of its own: focus looks the same everywhere in the app.
    assert "outline: 2px solid var(--focus)" in rules


def test_the_count_of_what_is_left_is_not_the_colour_of_an_achievement() -> None:
    """§4 gives leaf to progress and to what you know. Work outstanding is neither, and
    painting it as though it were would say the opposite of what the number says."""
    css = _reader_css()
    assert ".bar-title .known b.left { color: var(--ink); }" in css
    # And the one moment it is an achievement.
    assert ".bar-title .known.done { color: var(--leaf); }" in css

    from targum.render.builder import ASSETS

    script = (ASSETS / "reader.js").read_text(encoding="utf-8")
    # The same rule the queue is built from, so the two cannot disagree.
    assert "var left = counts.fresh + counts.learning;" in script
    assert '"nothing left to mark here"' in script


def test_the_card_carries_no_key_legend() -> None:
    """It used to teach its own keys on every opening, in 11px mono — the card carrying
    a manual. The keys card (?) is the manual; the card is the answer. Decided with the
    perfected middle road, 2026-08-31."""
    from targum.render.builder import ASSETS

    script = (ASSETS / "reader.js").read_text(encoding="utf-8")
    assert '" next · k known · 1 2 3 · i ignore · "' not in script
    assert 'className = "legend"' not in script
    css = _reader_css()
    assert ".gloss-card .legend" not in css
    # The manual itself is still there to open.
    assert 'id="keys"' in (ASSETS.parent / "templates" / "reader.html.j2").read_text(
        encoding="utf-8"
    )


def test_the_queue_keys_are_written_down() -> None:
    """Every shortcut in this reader has a row in the card, and the two that changed
    meaning say what they mean now."""
    from targum.render.builder import ASSETS

    template = (ASSETS.parent / "templates/reader.html.j2").read_text(encoding="utf-8")
    # The arrows are not each other's mirror and the card says so: forward walks the
    # words still owed, back walks the chapter as it is written. A back key built on the
    # queue skipped everything the reader had just marked.
    assert "forward through the words you have not finished with" in template
    assert "back through the words as they are written" in template
    # Nothing steps a sentence, so nothing says it does.
    for gone in ("<dt>&uarr; &darr;</dt>", "<dt>j</dt>", "next sentence", "previous sentence"):
        assert gone not in template, gone
    # The card is the one thing here you have to ask for, so it has to be written down.
    assert "<dt>Enter</dt>" in template
    # And the one action on it that used to need a pointer is on the same key: `g` is
    # what the code calls a gloss, and nothing a reader ever sees.
    assert "again to look it up" in template
    assert "<dt>g</dt>" not in template
    # The sheet lists the key that opens it.
    assert "<dt>?</dt>" in template
    # In the order they get pressed: the walk and the levels are most of a session.
    assert template.index("<dt>&larr; &rarr;</dt>") < template.index("<dt>k 4</dt>")
    assert template.index("<dt>k 4</dt>") < template.index("<dt>1 2 3</dt>")
    assert template.index("<dt>1 2 3</dt>") < template.index("<dt>p</dt>")


def test_a_sentence_scrolled_to_clears_the_bar() -> None:
    """The bar is sticky, so a sentence scrolled to the top of the window went behind it.
    Every way of reaching one goes through `scrollIntoView`, so the clearance belongs to
    the sentence rather than to each of the call sites."""
    css = _reader_css()
    rules = css.split(".pair {", 1)[1].split("}", 1)[0]
    assert "scroll-margin-block-start" in rules


def test_nothing_scrolls_for_a_reader_who_asked_it_not_to() -> None:
    """`scrollIntoView` took a hard-coded `smooth`, which is the one animation on the
    page that prefers-reduced-motion could not switch off."""
    from targum.render.builder import ASSETS

    script = (ASSETS / "reader.js").read_text(encoding="utf-8")
    assert 'window.matchMedia("(prefers-reduced-motion: reduce)")' in script
    assert 'behavior: "smooth"' not in script
    # The rule is that nothing hard-codes the answer, which the line above is. It used
    # to also count `behaviour()` to exactly one, back when walking the word queue was
    # the only animated scroll; jumping to a section is a second, and a count that has
    # to be edited every time a legitimate one is added was measuring the wrong thing.
    assert "behavior: behaviour()" in script


def test_walking_the_page_opens_no_windows() -> None:
    """A card at every step would put a window between a reader and the page they are
    walking, forty times in a row. Standing on a word is the ring and the keyboard;
    Enter is what asks the question — and asks the card's own question, the look-up,
    when it is offering one — and pressing it once more puts the answer away."""
    from targum.render.builder import ASSETS

    script = (ASSETS / "reader.js").read_text(encoding="utf-8")
    stand = script[script.index("function focusQueued(") : script.index("function goTo(")]
    # The only opening in there is the one carried from a card already up.
    assert "showCard" not in stand, "standing on a word must not open anything"
    assert "if (open) openCard();" in stand

    keys = script[script.index("switch (key) {") :]
    assert 'case "Enter":\n        if (!standing) return;' in keys
    assert "if (!asking()) openCard();\n        else if (!askMeaning()) hideCard();" in keys


def test_escape_puts_the_card_away_before_it_puts_you_out() -> None:
    """One key that did both would cost a reader their place in the chapter to close a
    window they had opened on one word."""
    from targum.render.builder import ASSETS

    script = (ASSETS / "reader.js").read_text(encoding="utf-8")
    escape = script[script.index('case "Escape": {') : script.index("      default:")]
    assert escape.index("hideCard();") < escape.index("leaveQueue();")


def test_escape_takes_the_panel_off_before_it_takes_your_place() -> None:
    """Escape peels one layer: the help, then the word, then the panel over the
    translation, then the queue. It used to close the two windows and then drop you out
    of the queue while leaving the saved-words panel — the one thing still covering the
    text — exactly where it was."""
    from targum.render.builder import ASSETS

    script = (ASSETS / "reader.js").read_text(encoding="utf-8")
    escape = script[script.index('case "Escape": {') : script.index("      default:")]
    assert escape.index("showKeys(false);") < escape.index("hideCard();")
    assert escape.index("hideCard();") < escape.index("showList(false);")
    assert escape.index("showList(false);") < escape.index("leaveQueue();")
    # The phrase chip is a layer too. It sits over the word card, and Escape never
    # reached it at all: the first alpha reader was left with a card she could not close.
    assert escape.index("hideChip();") < escape.index("hideCard();")
    # The menu behind ⋯ is the outermost layer of all, on a phone.
    assert escape.index("showMore(false);") < escape.index("showKeys(false);")
    # And each layer stops there: closing the keys used to fall straight through and drop
    # you out of the queue in the same press.
    assert escape.count("return;") == 6


def test_the_ring_does_not_outlive_the_focus_that_drew_it() -> None:
    """The word is the page's one tab stop, so one Tab takes a reader off it — and the
    ring, the card and `standing` all stayed behind. The next `k` then marked that word,
    silently, on a word out of sight. The bar is the exception: sticky, the word still in
    front of you, and Shift+Tab straight back to it."""
    from targum.render.builder import ASSETS

    script = (ASSETS / "reader.js").read_text(encoding="utf-8")
    guard = script[script.index('document.addEventListener("focusin"') :]
    guard = guard[: guard.index("});")]
    assert "if (!standing || event.target === standing) return;" in guard
    # The card's own level buttons and note field are reached by Tab from the word, and
    # reaching them is not leaving.
    assert "card.contains(event.target)" in guard
    assert "bar.contains(event.target)" in guard
    assert "leaveQueue();" in guard


def test_a_key_is_the_letter_printed_on_it_whatever_the_layout() -> None:
    """Under the Hebrew layout the P key arrives as "פ", and every letter the reader
    answers to was dead — for the reader this page is for. A Latin letter is taken as
    typed, so a Dvorak keyboard keeps its mnemonics; anything else falls back to the key
    it sits on. Digits and `?` are the same on both layouts and are left alone."""
    from targum.render.builder import ASSETS

    script = (ASSETS / "reader.js").read_text(encoding="utf-8")
    assert 'if (!/^[a-z0-9?]$/.test(key) && /^Key[A-Z]$/.test(event.code || "")) {' in script
    assert "key = event.code.charAt(3).toLowerCase();" in script


def test_enter_asks_the_question_the_card_is_offering() -> None:
    """Enter opens the card; on a card offering a look-up, Enter presses it; once there is
    nothing left to ask, Enter closes the card. `g` had the look-up once — for the gloss,
    which is what the code calls it and nothing a reader ever sees."""
    from targum.render.builder import ASSETS

    script = (ASSETS / "reader.js").read_text(encoding="utf-8")
    keys = script[script.index("switch (key) {") :]
    assert 'case "g":' not in keys
    # A question already asked and still waiting is not "nothing to ask": Enter must not
    # close the card out from under a look-up in flight.
    ask = script[script.index("function askMeaning() {") :]
    ask = ask[: ask.index("\n  }\n")]
    assert 'if (button.disabled) return button.classList.contains("looking");' in ask
    assert 'ask.classList.add("looking");' in script


def test_a_key_is_the_letter_on_it_whatever_the_shift_was() -> None:
    """Read literally, `event.key` is "K" with caps lock down — and every letter the
    reader answers to is dead, on a state nothing on the page shows."""
    from targum.render.builder import ASSETS

    script = (ASSETS / "reader.js").read_text(encoding="utf-8")
    assert 'if (typeof key === "string" && key.length === 1) key = key.toLowerCase();' in script
    assert "switch (event.key) {" not in script, "the switch reads the normalised key"
    assert "markLookedUp(key)" in script


def test_the_word_list_does_not_open_itself_over_a_walk(tmp_path: Path) -> None:
    """The panel covers the translation column. Opening it in the middle of somebody
    stepping the chapter a word at a time takes away the thing they are grading against,
    at the one moment they are not looking for it."""
    from targum.render.builder import ASSETS

    script = (ASSETS / "reader.js").read_text(encoding="utf-8")
    assert "if (isLearning(status) && !standing && listBox && listBox.hidden) showList(true);" in (
        script
    )


def test_the_keyboard_card_is_in_the_page_before_the_script_that_finds_it(
    tmp_path: Path,
    segmented: SegmentedDocument,
    translation: Translation,
) -> None:
    """`reader.js` asks for it by id as it loads. For as long as it sat below the script
    tag the answer was null, so `showKeys` returned at its first line — the `?` key and
    the `?` button in the bar both went to a card that was never found, and the one page
    that says which keys exist could not be opened by either."""
    document = Document(
        source="memory", title="Declaration", language="he", blocks=[], content_hash="abc123"
    )
    html = render(document, segmented, [translation], tmp_path / "r")[0].read_text(encoding="utf-8")
    # The script is inlined, so "before the script" means before the code itself.
    assert html.index('id="keys"') < html.index("window.TargumReader = {")


def test_a_card_a_pointer_opened_survives_the_key_that_marks_it() -> None:
    """`markSegment` replaces the text nodes inside the cell, so the span is detached
    once the page is redrawn and has no ancestors left to search. The sentence was being
    read off the word *after* that, which answers null — so the card shut itself on every
    word marked with a pointer, which is the one path that is supposed to keep it."""
    from targum.render.builder import ASSETS

    script = (ASSETS / "reader.js").read_text(encoding="utf-8")
    body = script[script.index("function markLookedUp(") : script.index("function statusRow(")]
    assert body.index('word.closest(".pair")') < body.index("redraw();"), "read it first"


def test_the_word_decides_whether_to_scroll_and_the_sentence_moves() -> None:
    """Asking the sentence whether it is on screen scrolled the page whenever a long
    verse ran past the fold, with the word you were standing on in plain sight the whole
    time. Centring the word alone is the opposite mistake: it puts the line it belongs to
    at the very edge of the window."""
    from targum.render.builder import ASSETS

    script = (ASSETS / "reader.js").read_text(encoding="utf-8")
    body = script[
        script.index("function bring(word, pair) {") : script.index("function focusQueued(")
    ]
    assert "var box = word.getBoundingClientRect();" in body, "the word decides"
    assert "(tall ? word : pair).scrollIntoView(" in body, "the sentence moves"
    # A sentence taller than the window would hide the word the scroll was for.
    assert "var room = window.innerHeight - top - 16;" in body


def test_the_arrows_stop_at_the_end_rather_than_coming_round() -> None:
    """A reader who walks to the end of a text is at the end of it.

    This came round to the first waiting word for a while, which is right by the counter
    — it can still say five left while the arrow refuses — and wrong by the reading:
    being thrown back to page one at the moment you finish is the page taking the text
    away from you. The words earlier are still reachable by the other arrow and by tapping
    one, so what went is a shortcut.
    """
    from targum.render.builder import ASSETS

    script = (ASSETS / "reader.js").read_text(encoding="utf-8")
    onward = script[script.index("  function onward(from, forward) {") :]
    onward = onward[: onward.index("\n  }\n")]
    assert onward.startswith(
        "  function onward(from, forward) {\n    var entry = step(from, forward);"
    )
    assert "step(null, forward)" not in onward, (
        "onward must not fall back to the first waiting word any more"
    )
    # On pages, forward stops at the foot of the page and turns one page from there —
    # loudly, the way PageDown does — rather than turning straight to the next word owed
    # and leaving the lines under this one unread.
    assert "var foot = footOf(current);" in onward
    assert "if (!turnBy(1)) return entry;" in onward
    # The first press on a page already clear goes to its foot, not some pages on.
    assert "return onward(edge, forward) || step(null, forward);" in script
    # And off the foot of the last page, the next chapter — the one place the walk
    # leaves the file, and by the same door PageDown and the page control use.
    walk = script[script.index("  function walk(forward) {") :]
    walk = walk[: walk.index("\n  }\n")]
    assert "current === pages.length - 1 && nextChapter()" in walk
    assert script.count("nextChapter()") == 5, (
        "defined once; PageDown, the control, the walk, the swipe"
    )
    assert script.count("location.href = ") == 1, "one door out of the chapter"
    # Both the arrows and a decision go through it.
    assert "var entry = place ? onward(place, forward) : enterFrom(forward);" in script
    # `false`: a card is spent by the level it was answered with, so what the arrows
    # carry on to the next word is the queue and not the window.
    assert "if (!goTo(onward(from, true), true, false)) {" in script


def test_a_card_goes_once_the_level_it_asked_for_has_been_said() -> None:
    """The card is a question, and a level is the answer to it — so it leaves rather than
    riding the arrows on to the next word, which put a window between the reader and the
    page they were walking for as long as they went on marking.

    Not in the frame the key was pressed in, though. A card that vanished on the keystroke
    took the level it had just taken with it, and a chapter cleared a word at a time was a
    window blinking forty times. It holds the answer for a beat, then fades — and §8, so a
    reader who asked for stillness gets the beat and nothing moving.
    """
    from targum.render.builder import ASSETS

    script = (ASSETS / "reader.js").read_text(encoding="utf-8")
    css = (ASSETS / "reader.css").read_text(encoding="utf-8")

    assert "if (open) spendCard();" in script, "a level said on an open card spends it"
    spend = script[script.index("function spendCard() {") : script.index("function stopFade() {")]
    assert "letGo();" in spend, "the word is let go of at once; only the card waits"
    assert 'card.classList.add("going");' in spend
    assert "fading = setTimeout(hideCard, FADE);" in spend

    beat = re.search(r"var LINGER = (\d+);", script)
    fade = re.search(r"var FADE = (\d+);", script)
    assert beat and fade, "reader.js no longer names the two waits the way this test reads them"
    assert 400 <= int(beat[1]) <= 1200, "long enough to read the level, short enough to be gone"
    assert f"transition: opacity {fade[1]}ms ease" in css, "the sheet and the script must agree"

    still = css.split("@media (prefers-reduced-motion: reduce) {", 1)[1].split("\n}", 1)[0]
    assert ".gloss-card.going { transition: none; }" in still


def test_the_about_page_is_not_a_list_of_commits() -> None:
    """The page says how much has landed and never what each change was. A commit subject
    is written for whoever maintains the code — "Bind the chart kit before start-up reads
    it" — and a page that prints those is a changelog wearing a product page's clothes.
    The word itself is for maintainers too: thirty days of work are thirty days of
    changes."""
    from targum.render.builder import about_page

    # The words on the page, not the markup: the link to the history is allowed to point
    # at a URL with "commits" in it, because that is where the history lives.
    words = re.sub(r"<[^>]+>", " ", about_page())
    for inside_baseball in ("commit", "refactor", "changelog", ".py", "src/"):
        assert inside_baseball not in words, f"{inside_baseball!r} is for maintainers"


def test_the_about_page_says_targum_is_under_construction_and_little_else() -> None:
    """It described targum at length — what it does, what had shipped, what it could not
    do yet — and none of that is what somebody arriving early needs to be told. What is
    left is the state of the thing, the evidence for it, and where the work is."""
    from targum.render.builder import about_page

    page = about_page()
    assert "targum is under construction" in page
    assert 'href="https://github.com/DLangellotti/targum"' in page
    for gone in ("What it does", "Recently shipped", "What it cannot do yet", "reading app"):
        assert gone not in page, f"{gone!r} was cut from this page"


def test_the_about_page_keeps_its_numbers_where_there_is_no_repository(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The page is served from a wheel on the box, and a wheel has no `git log` to read.
    Without a stamp the whole calendar disappears in production and nowhere else, which
    is the kind of fault that is only ever found by looking at the live page.
    """
    from targum import about
    from targum.render.builder import about_page

    live = about.work()
    if not live.days:
        pytest.skip("no repository to read the numbers out of")

    monkeypatch.setattr(about, "STAMP", tmp_path / "activity.json")
    assert about.stamp() is not None, "there is a repository, so there is a stamp"
    # A directory with no `.git` in it is what the package sits in once it is installed.
    monkeypatch.setattr(about, "_root", lambda: tmp_path)
    assert about.work().commits == live.commits, "the stamp is what the box reads"

    page = about_page()
    assert page.count('class="day level-') >= about.DAYS
    assert f"<b>{live.commits}</b>" in page


def test_the_about_page_names_the_day_its_count_ends_on() -> None:
    """ "In the last 30 days" is true of a wheel for about a day. The numbers are stamped
    when it is built and served until the next deploy, so the sentence has to name the
    day it counted to rather than implying today."""
    from targum import about
    from targum.render.builder import about_page

    found = about.work()
    if not found.days:
        pytest.skip("no repository to read the numbers out of")
    assert found.through in about_page()
    assert "in the last" not in about_page()


def test_the_stamp_is_packed_into_the_wheel() -> None:
    """It is ignored by git so it cannot be committed stale, and hatchling leaves
    VCS-ignored files out of a build unless it is told otherwise. Miss the second half
    and the first half silently empties the page on the box."""
    root = Path(__file__).resolve().parents[1]
    assert "src/targum/activity.json" in (root / ".gitignore").read_text(encoding="utf-8")
    packaging = (root / "pyproject.toml").read_text(encoding="utf-8")
    assert 'artifacts = ["/src/targum/activity.json"]' in packaging


# --- what gets baked in ------------------------------------------------------


def test_comments_are_stripped_from_what_the_page_carries(
    tmp_path: Path, document: Document, segmented: SegmentedDocument, translation: Translation
) -> None:
    """The source keeps its comments; the reader does not carry them.

    A reader inlines its whole stylesheet and script, so a comment is paid for once per
    page and a book of 151 chapters pays 151 times.
    """
    from targum.render.builder import ASSETS

    source = (ASSETS / "reader.js").read_text(encoding="utf-8")
    # A line of prose from the file itself, so this cannot pass against a stub.
    landmark = "/* --- keeping your place"
    assert landmark in source

    html = render(document, segmented, [translation], tmp_path / "r")[0].read_text(encoding="utf-8")
    assert landmark not in html
    # And the code it sat above is still there.
    assert "function keep(held)" in html


def test_stripping_leaves_strings_and_regular_expressions_alone() -> None:
    """The whole risk in the stripper. `//` inside a URL is not a comment, and neither
    is a `/` that opens a regular expression — telling them apart is why this works on
    whole lines only."""
    from targum.render.builder import _strip

    out = _strip(
        "x.js",
        "\n".join(
            [
                "// gone",
                "/* also",
                "   gone */",
                'var a = "http://example.com";',
                "var b = /\\bmode-\\w+/g;",
                "var c = width / 2; // kept, and so is this",
                "",
                "/* one line */ var d = 1;",
            ]
        ),
    )
    assert "gone" not in out
    assert 'var a = "http://example.com";' in out
    assert "var b = /\\bmode-\\w+/g;" in out
    assert "var c = width / 2; // kept, and so is this" in out
    assert out.strip().endswith("var d = 1;")
    assert "\n\n" not in out  # blank lines go with the comments


def test_no_asset_carries_a_template_literal_across_a_line() -> None:
    """The assumption the stripper rests on, held rather than trusted.

    It takes out any line that opens with `//` or `/*`, which is only safe while no
    string in these files spans a line — a template literal is the one kind that can.
    The day somebody writes one, this fails here rather than in a reader's browser with
    half a script missing.
    """
    from targum.render.builder import ASSETS

    for path in sorted(ASSETS.glob("*.js")) + sorted(ASSETS.glob("*.css")):
        # Comments out of the way first: the one pair of backticks in the set that spans
        # a line is prose inside a CSS comment, and prose is not a string.
        code = re.sub(r"/\*.*?\*/", "", path.read_text(encoding="utf-8"), flags=re.S)
        spanning = [run for run in re.findall(r"`[^`]*`", code, re.S) if "\n" in run]
        assert not spanning, f"{path.name} has a template literal across a line"


def test_the_script_a_reader_gets_still_parses(tmp_path: Path) -> None:
    """Stripping is source surgery, so the result has to be run past a parser.

    `node --check` on every asset as it is baked, which is the same check
    `tests/test_reader_js.py` leans on to run the reader at all.
    """
    if shutil.which("node") is None:
        pytest.skip("node is not installed")
    from targum.render.builder import ASSETS, _strip

    for path in sorted(ASSETS.glob("*.js")):
        baked = tmp_path / path.name
        baked.write_text(_strip(path.name, path.read_text(encoding="utf-8")), encoding="utf-8")
        done = subprocess.run(["node", "--check", str(baked)], capture_output=True, text=True)
        assert done.returncode == 0, f"{path.name} does not parse after stripping:\n{done.stderr}"


def test_the_first_time_line_is_only_on_a_page_with_words() -> None:
    """It says to tap a word. A reader with no word-level annotation has none to tap."""
    from targum.render.builder import ASSETS

    template = (ASSETS.parent / "templates" / "reader.html.j2").read_text(encoding="utf-8")
    line = template[template.index('id="first"') - 200 : template.index('id="first"')]
    assert "{% if words %}" in line


def test_pages_are_a_preference_with_a_key_a_button_and_a_turn() -> None:
    """Listed like every other key, switchable from the bar, and turned from a control
    at the foot of the window with arrows drawn per reading direction."""
    from targum.render.builder import ASSETS

    template = (ASSETS.parent / "templates/reader.html.j2").read_text(encoding="utf-8")
    assert "<dt>b</dt>" in template
    assert "<dt>Space</dt>" in template
    assert "data-paged" in template
    assert 'id="turn"' in template and 'data-turn="1"' in template and 'data-turn="-1"' in template
    css = _reader_css()
    assert '.turn .back::before { content: "\\2190"; }' in css
    assert '[dir="rtl"] .turn .back::before { content: "\\2192"; }' in css, (
        "arrows follow the direction"
    )


def test_printing_a_paged_chapter_prints_the_whole_chapter() -> None:
    css = _reader_css()
    printing = css[css.index("@media print") :]
    assert "body.paged .pair[hidden] { display: grid; }" in printing
    assert ".turn" in printing.split("}", 1)[0], "and not the control"


def test_the_pager_and_the_offer_belong_to_the_last_page() -> None:
    css = _reader_css()
    assert "body.paged:not(.last-page) .pager" in css
    assert "body.paged:not(.last-page) .rest" in css


def test_the_foot_of_a_narrow_window_is_one_band() -> None:
    """Under 60rem everything that stands over the text is an occupant of one band at
    the foot, one at a time; the player is a strip standing on the occupant, the arrows
    stand on the strip, and the page is laid out above the highest. The stylesheet is
    told the measured heights — `--occupant`, `--strip`, `--foot` — rather than working
    from the sheet's ceiling, which is what once parked the player in mid-page."""
    from targum.render.builder import ASSETS

    css = _reader_css()
    tab = css.split("\n.list-tab {", 1)[1].split("}", 1)[0]
    assert "inset-inline-start: 1rem" in tab
    assert "inset-inline-end" not in tab, "the end corner is the player's and the arrows'"
    assert "body.paged .list-tab { inset-block-end: 5.5rem; }" in css, "the player's row, wide"
    phone = css[css.index("/* --- the phone: one band at the foot") :]
    # The video panel is in the occupant list by design — §12's moving-pictures entry.
    shared = "\n  .list, .gloss-card, .pick-card, .keys-card, .video, .bar-more.open {"
    occupants = phone.split(shared, 1)[1]
    occupants = occupants.split("\n  }\n", 1)[0]
    assert "position: fixed;" in occupants and "inset-block: auto 0;" in occupants
    assert "max-block-size: 45svh;" in occupants, "the band's ceiling"
    assert "inset-block-end: var(--occupant, 0px);" in phone, "the strip stands on the occupant"
    assert "var(--occupant, 0px) + var(--strip, 0px)" in phone, "the arrows stand on the strip"
    assert "body { padding-block-end: var(--foot, 0px); }" in phone, "the page above the lot"
    assert "42svh + " not in css, "nothing is lifted by a ceiling"
    assert "--sheet" not in css

    script = (ASSETS / "reader.js").read_text(encoding="utf-8")
    for told in ("--occupant", "--strip", "--tab", "--foot"):
        assert f'"{told}"' in script, told
    room = script[script.index("  function room() {") :]
    room = room[: room.index("\n  }\n")]
    assert "seatFoot();" in room, "measured before the things it lifts are"
    # The occupants count on a narrow window only, and everything at the foot is
    # measured where it will stand once it has stopped moving, not mid-flight.
    assert "if (!roomy.matches) {" in room and "occupants().forEach" in room
    assert room.count("settledTop(thing, false)") == 1
    assert room.count("settledTop(thing, true)") == 1
    # One occupant at a time, and the sheet given back after a card.
    assert "function occupy(which)" in script and "function vacate(which)" in script
    assert 'if (open) occupy("list");' in script
    assert 'occupy("card");' in script and 'vacate("card");' in script
    assert 'if (open) occupy("keys");' in script and 'if (open) occupy("more");' in script


def test_nothing_about_a_page_is_fixed_height_or_clipped() -> None:
    """A single pair taller than the window fits on no page, and that page has to
    scroll. A fixed-height, overflow-hidden reader would swallow it."""
    css = _reader_css()
    paged = css[css.index("/* --- pages, not a scroll") : css.index("@media print")]
    assert "overflow: hidden" not in paged
    assert "block-size: calc(100" not in paged and "height: 100vh" not in paged


def test_the_register_rides_beside_the_lemmas(tmp_path: Path) -> None:
    """Which Hebrew a word belongs to is a fact about the dictionary form, so it goes in
    a table parallel to the lemmas rather than on every token that spells it.

    Codes rather than sentences: the words the card says are in `reader.js`, so they can
    be rewritten without re-annotating a library.
    """
    from targum.models import Annotation, Token

    segments = [paragraph(0)]
    segmented = make_segmented(segments)
    document = Document(
        source="sefaria:Ruth", title="T", language="he", blocks=[], content_hash="h"
    )
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
        method="curated:tanakh",
        method_note="note",
        tokens={
            segments[0].id: [
                Token(start=0, end=3, surface="זבח", lemma="זבח", band=2, word_register="biblical"),
                # The registers agreed about this one, and the table still lines up.
                Token(start=4, end=7, surface="בית", lemma="בית", band=1),
            ]
        },
    )
    html = render(document, segmented, [translation], tmp_path / "r", annotation=annotation)[
        0
    ].read_text(encoding="utf-8")

    data = json.loads(re.search(r'id="targum-data"[^>]*>(.*?)</script>', html, re.S).group(1))
    assert data["lemmas"] == ["זבח", "בית"]
    assert data["registers"] == ["biblical", ""]
    # Where the reader is standing, so the card can say the same fact from here.
    assert data["sourceRegister"] == "biblical"


def test_a_page_whose_registers_all_agreed_ships_no_table(tmp_path: Path) -> None:
    """Rather than a row of empty strings nothing would ever read."""
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
        tokens={segments[0].id: [Token(start=0, end=3, surface="בית", lemma="בית", band=1)]},
    )
    html = render(document, segmented, [translation], tmp_path / "r", annotation=annotation)[
        0
    ].read_text(encoding="utf-8")

    data = json.loads(re.search(r'id="targum-data"[^>]*>(.*?)</script>', html, re.S).group(1))
    assert "registers" not in data
    assert data["sourceRegister"] == "modern"


def _one_page(tmp_path: Path, tokens: list[Token]) -> dict[str, object]:
    """The payload of a one-paragraph Hebrew page annotated with exactly these tokens."""
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
        tokens={segments[0].id: tokens},
    )
    html = render(document, segmented, [translation], tmp_path / "r", annotation=annotation)[
        0
    ].read_text(encoding="utf-8")
    data: dict[str, object] = json.loads(
        re.search(r'id="targum-data"[^>]*>(.*?)</script>', html, re.S).group(1)
    )
    return data


def test_the_payload_says_which_shape_it_is(tmp_path: Path) -> None:
    """One field, so a payload can be told apart from an older one by a reader it did not
    ship with. Not the cache's `SCHEMA_VERSION`: this one is free to move."""
    from targum.render.builder import PAYLOAD_VERSION

    data = _one_page(tmp_path, [Token(start=0, end=3, surface="בית", lemma="בית", band=1)])
    assert data["schemaVersion"] == PAYLOAD_VERSION == 1


def test_a_page_with_no_verb_ships_no_root_or_binyan_table(tmp_path: Path) -> None:
    """Like the registers and the sounds: a row of empty strings nothing would read is
    left out, rather than shipped in every reader whose language has no binyanim and
    every one annotated before there was a root to give."""
    data = _one_page(tmp_path, [Token(start=0, end=3, surface="בית", lemma="בית", band=1)])
    assert data["lemmas"] == ["בית"]
    assert "extensions" not in data


def test_a_binyan_without_a_root_ships_the_one_table_it_has(tmp_path: Path) -> None:
    """The two are decided apart. A verb whose binyan Stanza tagged and whose root could
    not honestly be had is the common case for a weak verb, and the card still says the
    binyan — so the binyanim table rides alone, and the roots table is not sent empty
    beside it."""
    data = _one_page(
        tmp_path, [Token(start=0, end=3, surface="קם", lemma="קם", band=2, binyan="פעל")]
    )
    assert data["extensions"] == {"binyanim": ["פעל"]}


# -- what to read next -------------------------------------------------------------


def catalogue_of(*rows: tuple[str, str, int, str]) -> list[object]:
    """A stand-in catalogue: id, source, difficulty, register."""
    from targum.catalogue import Entry, Kind, Register

    return [
        Entry(
            id=entry_id,
            title=entry_id,
            author="",
            language="he",
            source=source,
            blurb="A line about it.",
            words=100 * (n + 1),
            kind=Kind.prose,
            register=Register(register),
            difficulty=difficulty,
        )
        for n, (entry_id, source, difficulty, register) in enumerate(rows)
    ]


def suggestion(monkeypatch: pytest.MonkeyPatch, source: str, rows: list[object]) -> str:
    from targum.render.builder import next_after

    monkeypatch.setattr("targum.catalogue.CATALOGUE", rows)
    document = Document(source=source, language="he", blocks=[], content_hash="h")
    return str(next_after(document).get("id", ""))


def test_the_next_text_is_the_next_step_up(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = catalogue_of(
        ("here", "s:here", 10, "modern"),
        ("easier", "s:easier", 4, "modern"),
        ("just-above", "s:above", 12, "modern"),
        ("far-above", "s:far", 30, "modern"),
    )
    assert suggestion(monkeypatch, "s:here", rows) == "just-above"


def test_it_never_suggests_the_text_you_are_reading(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = catalogue_of(("here", "s:here", 10, "modern"), ("other", "s:other", 12, "modern"))
    assert suggestion(monkeypatch, "s:here", rows) == "other"


def test_it_stays_in_the_same_hebrew(monkeypatch: pytest.MonkeyPatch) -> None:
    """Somebody who has just finished a dialogue is not looking for scripture, and a
    step of one point of difficulty is no reason to hand them some."""
    rows = catalogue_of(
        ("here", "s:here", 10, "modern"),
        ("scripture", "s:bible", 11, "biblical"),
        ("modern-next", "s:modern", 18, "modern"),
    )
    assert suggestion(monkeypatch, "s:here", rows) == "modern-next"


def test_the_hardest_text_still_gets_an_offer(monkeypatch: pytest.MonkeyPatch) -> None:
    """Nothing harder exists, so the nearest does — a door out beats a dead end."""
    rows = catalogue_of(("here", "s:here", 40, "modern"), ("near", "s:near", 36, "modern"))
    assert suggestion(monkeypatch, "s:here", rows) == "near"


def test_a_text_the_catalogue_never_heard_of_is_still_offered_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An upload. It has no difficulty of its own, so the easiest thing is the answer."""
    rows = catalogue_of(("easy", "s:easy", 5, "modern"), ("hard", "s:hard", 30, "modern"))
    assert suggestion(monkeypatch, "https://example.com/mine.txt", rows) == "easy"


def test_an_empty_catalogue_offers_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    assert suggestion(monkeypatch, "s:here", []) == ""


def test_after_a_scene_comes_the_next_scene(monkeypatch: pytest.MonkeyPatch) -> None:
    """A numbered sequence has one order; the nearest harder text is not it."""
    rows = catalogue_of(
        ("scene-01-nice-to-meet-you", "dialogue:01-nice-to-meet-you", 5, "modern"),
        ("scene-02-in-a-cafe", "dialogue:02-in-a-cafe", 0, "modern"),
        ("scene-03-which-way", "dialogue:03-which-way", 2, "modern"),
        ("news-a", "s:news", 6, "modern"),
    )
    assert suggestion(monkeypatch, "dialogue:01-nice-to-meet-you", rows) == "scene-02-in-a-cafe"
    assert suggestion(monkeypatch, "dialogue:02-in-a-cafe", rows) == "scene-03-which-way"
    from targum.render.builder import next_after

    monkeypatch.setattr("targum.catalogue.CATALOGUE", rows)
    offered = next_after(
        Document(source="dialogue:01-nice-to-meet-you", language="he", blocks=[], content_hash="h")
    )
    assert offered["scene"] == "Scene 2"


def test_after_the_last_scene_the_step_up_takes_over(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = catalogue_of(
        ("scene-03-which-way", "dialogue:03-which-way", 2, "modern"),
        ("news-a", "s:news", 6, "modern"),
    )
    assert suggestion(monkeypatch, "dialogue:03-which-way", rows) == "news-a"


def test_a_reader_dicta_read_names_dicta_and_one_that_stanza_read_does_not(
    tmp_path: Path, segmented: SegmentedDocument, translation: Translation
) -> None:
    """CC BY 4.0 asks for the work to be named where it is used, and the words are used
    here (targum-internal#116). Keyed to the annotator that actually ran, so a reader
    built before the swap does not claim a credit it did not earn — which is also what
    keeps the credit honest once both kinds of reader are on the shelf at once."""
    from targum.models import Annotation, Token

    document = Document(
        source="memory", title="Declaration", language="he", blocks=[], content_hash="abc123"
    )

    def page(annotator: str) -> str:
        annotation = Annotation(
            document_hash="h",
            language="he",
            annotator=annotator,
            method="frequency",
            method_note="note",
            tokens={
                segmented.segments[0].id: [
                    Token(start=0, end=4, surface="ספר", lemma="ספר", band=1),
                ]
            },
        )
        out = tmp_path / annotator.split("/")[0]
        return render(document, segmented, [translation], out, annotation=annotation)[0].read_text(
            encoding="utf-8"
        )

    read_by_dicta = page("dicta/dicta-il/dictabert-joint/roots+everyword+names+grammar")
    assert "Dictionary forms by" in read_by_dicta
    assert "https://huggingface.co/dicta-il/dictabert-joint" in read_by_dicta
    assert "https://creativecommons.org/licenses/by/4.0/" in read_by_dicta

    read_by_stanza = page("stanza/1.10.1/tokenize,pos,lemma+roots")
    assert "Dictionary forms by" not in read_by_stanza
    assert "huggingface.co" not in read_by_stanza
