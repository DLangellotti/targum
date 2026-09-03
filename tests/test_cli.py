from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from targum.cli import app

runner = CliRunner()


@pytest.fixture
def source(tmp_path: Path) -> Path:
    path = tmp_path / "declaration.md"
    path.write_text("# הכרזה\n\nבארץ־ישראל קם העם היהודי בשנת 1897.\n", encoding="utf-8")
    return path


def test_build_writes_a_reader(source: Path, tmp_path: Path, needs_dicta_model: None) -> None:
    out = tmp_path / "out"
    result = runner.invoke(
        app, ["build", str(source), "--to", "en", "--provider", "null", "--out", str(out)]
    )
    assert result.exit_code == 0, result.output
    assert (out / "reader" / "index.html").exists()
    assert "he → en" in result.output


def test_pdf_gets_a_message_not_a_traceback(tmp_path: Path) -> None:
    pdf = tmp_path / "book.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    result = runner.invoke(app, ["build", str(pdf), "--to", "en", "--provider", "null"])
    assert result.exit_code == 1
    assert "PDF ingest is not supported yet" in result.output
    assert "Traceback" not in result.output


def test_missing_key_is_reported_before_any_work(source: Path, monkeypatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    result = runner.invoke(app, ["build", str(source), "--to", "en"])
    assert result.exit_code == 1
    assert "ANTHROPIC_API_KEY" in result.output


def test_providers_lists_both(monkeypatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    result = runner.invoke(app, ["providers"])
    assert result.exit_code == 0
    assert "anthropic" in result.output and "null" in result.output


def test_models_list_when_empty(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("TARGUM_MODEL_DIR", str(tmp_path / "models"))
    result = runner.invoke(app, ["models", "list"])
    assert result.exit_code == 0
    assert "targum models fetch" in result.output


def test_cache_clear_reports(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("TARGUM_CACHE_DIR", str(tmp_path / "cache"))
    result = runner.invoke(app, ["cache", "clear"])
    assert result.exit_code == 0
    assert "Cleared" in result.output


def test_help_lists_every_command() -> None:
    result = runner.invoke(app, ["--help"])
    for command in ("build", "providers", "models", "cache"):
        assert command in result.output


def test_sources_lists_what_can_be_read() -> None:
    result = runner.invoke(app, ["sources"])
    assert result.exit_code == 0
    assert ".epub" in result.output and "gutenberg:" in result.output


def test_fetch_writes_an_editable_file(tmp_path: Path, epub_source: Path) -> None:
    # fetch and build share one ingest path, so a local file exercises the command
    # without reaching the network.
    out = tmp_path / "book.md"
    result = runner.invoke(app, ["fetch", str(epub_source), "--out", str(out)])
    assert result.exit_code == 0
    written = out.read_text(encoding="utf-8")
    assert written.startswith("---")
    assert "author: A Nineteenth Century Author" in written
    assert "# Chapter One" in written
    assert "targum build" in result.output


def test_fetch_reports_a_bad_identifier() -> None:
    result = runner.invoke(app, ["fetch", "archive:12345"])
    assert result.exit_code == 1
    assert "gutenberg" in result.output
    assert "Traceback" not in result.output


def test_rebuild_rewrites_readers_from_disk(tmp_path: Path) -> None:
    """A reader carries the stylesheet and script targum had when it wrote it.

    So a reader built last month is last month's reader, and the only way to give it
    what targum has learned since is to write it again — from the artifacts beside it,
    without fetching anything or spending anything.
    """
    from typer.testing import CliRunner

    from targum.cli import app
    from targum.models import BlockKind, Document, Segment, SegmentedDocument, Translation
    from targum.render import render

    out = tmp_path / "targum-out"
    folder = out / "book-he"
    folder.mkdir(parents=True)

    document = Document(source="m", title="A Book", language="he", blocks=[], content_hash="h")
    segment = Segment(
        id="0000.000-aaa",
        block_id="b0",
        block_index=0,
        index=0,
        text="שלום",
        kind=BlockKind.paragraph,
    )
    segmented = SegmentedDocument(
        document_hash="h", language="he", segmenter="t/1", segments=[segment]
    )
    translation = Translation(
        name="English",
        document_hash="h",
        source_language="he",
        target_language="en",
        provider="null",
        segments={segment.id: "peace"},
    )
    document.write(folder / "document.json")
    segmented.write(folder / "segments.json")
    (folder / "translations").mkdir()
    translation.write(folder / "translations" / "null.natural.en.json")
    # A reader as it was: written once, then left behind by everything since.
    render(document, segmented, [translation], folder / "reader")
    (folder / "reader" / "index.html").write_text("<html>old</html>", encoding="utf-8")

    # And one that was priced but never paid for, which has nothing to show.
    bare = out / "unpaid-he"
    bare.mkdir()
    document.write(bare / "document.json")
    segmented.write(bare / "segments.json")

    result = CliRunner().invoke(app, ["rebuild", "--out", str(out)])
    assert result.exit_code == 0, result.output
    assert "Rewrote 1 targum" in result.output
    assert "never translated" in result.output

    written = (folder / "reader" / "index.html").read_text(encoding="utf-8")
    assert "<html>old</html>" not in written
    assert "peace" in written


def test_a_catalogue_reader_can_be_rebuilt(tmp_path: Path) -> None:
    """A reader built from a published translation must be rewritable like any other.

    It was not. The alignment on disk holds links, not text, and the published
    translation's segments are kept nowhere, so `rebuild` found no `translations/`
    entry and reported the reader as "never translated". The class of reader that
    costs nothing to build was the one class a design change could never reach.
    """
    from targum.align import to_translation
    from targum.models import Alignment, BlockKind, Link, Segment, SegmentedDocument

    source = SegmentedDocument(
        document_hash="src",
        language="he",
        segmenter="t/1",
        segments=[
            Segment(
                id="0000.000-aaa",
                block_id="b0",
                block_index=0,
                index=0,
                text="שלום",
                kind=BlockKind.paragraph,
            )
        ],
    )
    target = SegmentedDocument(
        document_hash="tgt",
        language="en",
        segmenter="t/1",
        segments=[
            Segment(
                id="0000.000-bbb",
                block_id="b0",
                block_index=0,
                index=0,
                text="peace",
                kind=BlockKind.paragraph,
            )
        ],
    )
    alignment = Alignment(
        name="A Published Translation",
        document_hash="src",
        translation_hash="tgt",
        source_language="he",
        target_language="en",
        aligner="t/1",
        links=[Link(source=["0000.000-aaa"], target=["0000.000-bbb"], confidence=1.0)],
    )

    projected = to_translation(alignment, target)
    assert projected.segments == {"0000.000-aaa": "peace"}, projected.segments

    # The projection is what has to survive to disk: the alignment alone cannot
    # reproduce it, because nothing on disk remembers what the target said.
    written = tmp_path / "translations" / "aligned.a-published-translation.en.json"
    projected.write(written)
    assert written.is_file()

    from targum.models import Translation, read_artifact

    reloaded = read_artifact(Translation, written)
    assert reloaded is not None
    assert reloaded.segments == {"0000.000-aaa": "peace"}
    assert source.segments[0].id in reloaded.segments


def test_rebuild_finds_targums_inside_homes(tmp_path: Path) -> None:
    """A regression from the multi-tenancy work.

    Targums used to sit directly under the library root and now sit one level down, in a
    directory per person. Looking only at the top found the homes themselves and reported
    every one as having no text, so `targum rebuild` rewrote nothing at all.
    """
    from typer.testing import CliRunner

    from targum.cli import app
    from targum.models import BlockKind, Document, Segment, SegmentedDocument, Translation
    from targum.render import render

    out = tmp_path / "targum-out"
    folder = out / "p1" / "book-he"
    folder.mkdir(parents=True)

    document = Document(source="m", title="A Book", language="he", blocks=[], content_hash="h")
    segment = Segment(
        id="0000.000-aaa",
        block_id="b0",
        block_index=0,
        index=0,
        text="שלום",
        kind=BlockKind.paragraph,
    )
    segmented = SegmentedDocument(
        document_hash="h", language="he", segmenter="t/1", segments=[segment]
    )
    translation = Translation(
        name="English",
        document_hash="h",
        source_language="he",
        target_language="en",
        provider="null",
        segments={segment.id: "peace"},
    )
    document.write(folder / "document.json")
    segmented.write(folder / "segments.json")
    translation.write(folder / "translations" / "null.natural.en.json")
    render(document, segmented, [translation], folder / "reader")

    result = CliRunner().invoke(app, ["rebuild", "--out", str(out)])
    assert result.exit_code == 0, result.output
    assert "Rewrote 1 targum" in result.output, result.output


def test_rebuild_leaves_the_weekly_as_it_was_built(tmp_path: Path) -> None:
    """An issue of the weekly is one long targum, built with `whole=True` and wired to
    its sibling levels by `targum weekly build`. The generic rewrite turned it back into
    a contents page and chapter files with no player — on the laptop, and then on the
    box on every deploy. The weekly is built where it is written and carried; `rebuild`
    does not touch it."""
    from typer.testing import CliRunner

    from targum.cli import app
    from targum.models import BlockKind, Document, Segment, SegmentedDocument, Translation
    from targum.render import render

    out = tmp_path / "targum-out"
    segment = Segment(
        id="0000.000-aaa",
        block_id="b0",
        block_index=0,
        index=0,
        text="שלום",
        kind=BlockKind.paragraph,
    )
    for folder in (out / "p1" / "book-he", out / "weekly" / "weekly-2026-w35-bet-he"):
        folder.mkdir(parents=True)
        document = Document(source="m", title="A Book", language="he", blocks=[], content_hash="h")
        segmented = SegmentedDocument(
            document_hash="h", language="he", segmenter="t/1", segments=[segment]
        )
        translation = Translation(
            name="English",
            document_hash="h",
            source_language="he",
            target_language="en",
            provider="null",
            segments={segment.id: "peace"},
        )
        document.write(folder / "document.json")
        segmented.write(folder / "segments.json")
        translation.write(folder / "translations" / "null.natural.en.json")
        render(document, segmented, [translation], folder / "reader")

    issue = out / "weekly" / "weekly-2026-w35-bet-he" / "reader" / "index.html"
    issue.write_text("<!-- as the weekly build left it -->", encoding="utf-8")

    result = CliRunner().invoke(app, ["rebuild", "--out", str(out)])
    assert result.exit_code == 0, result.output
    assert "Rewrote 1 targum" in result.output, result.output
    assert issue.read_text(encoding="utf-8") == "<!-- as the weekly build left it -->"


def test_clearing_the_cache_is_refused_on_a_hosted_box(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """On a hosted box `cache clear` is a command that deletes money.

    The cache is what makes a public text free for the second reader and every reader
    after, so clearing it means all of them buy the same translations again. Locally it
    only costs the one person a rebuild, so it stays unguarded there.
    """
    from typer.testing import CliRunner

    from targum.cli import app

    # conftest points this at a temp directory for every test already. Said again here
    # because the second half of this test really does clear a cache, and a test that
    # deletes 5 GB of somebody's models when an autouse fixture is refactored is not a
    # failure anyone would enjoy diagnosing.
    monkeypatch.setenv("TARGUM_CACHE_DIR", str(tmp_path / "cache"))

    monkeypatch.setenv("TARGUM_REQUIRE_ACCOUNT", "1")
    refused = CliRunner().invoke(app, ["cache", "clear"])
    assert refused.exit_code != 0
    assert "paid work" in refused.output

    monkeypatch.delenv("TARGUM_REQUIRE_ACCOUNT")
    allowed = CliRunner().invoke(app, ["cache", "clear"])
    assert allowed.exit_code == 0, "a machine somebody runs themselves keeps the old behaviour"


def test_repair_separates_glued_words_without_paying(tmp_path: Path) -> None:
    """A text built before ingest learned to repair spacing still carries the glue.

    Everything downstream is keyed to the Hebrew, so a sentence one space longer is a
    sentence nothing has ever translated — rebuilding it from the source would buy the
    English again. This carries the English across instead.
    """
    from typer.testing import CliRunner

    from targum.cli import app
    from targum.models import (
        Block,
        BlockKind,
        Document,
        Segment,
        SegmentedDocument,
        Translation,
        read_artifact,
    )

    glued = "מיכל ברקוביץהקדמה"
    clean = "מיכל ברקוביץ הקדמה"

    out = tmp_path / "targum-out"
    folder = out / "p1" / "herzl-he"
    folder.mkdir(parents=True)

    document = Document(
        source="https://benyehuda.org/download/6600.txt",
        title="A Book",
        language="he",
        blocks=[Block(id="b0000", kind=BlockKind.paragraph, text=glued)],
    )
    document.content_hash = document.recompute_hash()
    was = document.content_hash
    segment = Segment(id="0000.000-aaa", block_id="b0000", block_index=0, index=0, text=glued)
    segmented = SegmentedDocument(
        document_hash=was, language="he", segmenter="t/1", segments=[segment]
    )
    translation = Translation(
        name="English",
        document_hash=was,
        source_language="he",
        target_language="en",
        provider="null",
        segments={segment.id: "Michal Berkowitz. Introduction"},
    )
    document.write(folder / "document.json")
    segmented.write(folder / "segments.json")
    (folder / "translations").mkdir()
    translation.write(folder / "translations" / "null.natural.en.json")

    result = CliRunner().invoke(app, ["repair", "--out", str(out)])
    assert result.exit_code == 0, result.output
    assert "nothing was spent" in result.output.lower()

    repaired = read_artifact(Document, folder / "document.json")
    assert repaired is not None
    assert repaired.blocks[0].text == clean
    # The hash the blocks imply, so nothing downstream reads stale text against it.
    assert repaired.content_hash == repaired.recompute_hash() != was

    resegmented = read_artifact(SegmentedDocument, folder / "segments.json")
    assert resegmented is not None
    assert resegmented.segments[0].text == clean
    assert resegmented.document_hash == repaired.content_hash

    carried = read_artifact(Translation, folder / "translations" / "null.natural.en.json")
    assert carried is not None
    # The English is what was paid for and is untouched; only its key moved.
    assert carried.segments == {segment.id: "Michal Berkowitz. Introduction"}
    assert carried.document_hash == repaired.content_hash

    assert (folder / "reader" / "index.html").is_file()


def test_repair_takes_a_space_out_it_once_put_in(tmp_path: Path) -> None:
    """The spacing repair used to cut after every final letter, and a scanned ו read as
    ן came apart into a lone final letter and the rest of its word. The lone letter is
    not a word, so the space comes out again — and is counted as a join, not as a
    separation undone, so the report says what happened (targum-internal#86)."""
    from typer.testing import CliRunner

    from targum.cli import app
    from targum.models import Block, BlockKind, Document, read_artifact

    split = "עיר מלאה תשואות, ן נפשו"
    clean = "עיר מלאה תשואות, ןנפשו"

    out = tmp_path / "targum-out"
    folder = out / "p1" / "psalm-he"
    folder.mkdir(parents=True)
    document = Document(
        source="https://benyehuda.org/download/1.txt",
        title="A Scan",
        language="he",
        blocks=[Block(id="b0000", kind=BlockKind.paragraph, text=split)],
    )
    document.content_hash = document.recompute_hash()
    document.write(folder / "document.json")

    result = CliRunner().invoke(app, ["repair", "--out", str(out)])
    assert result.exit_code == 0, result.output
    assert "1 joined" in result.output
    assert "Separated 0 words, joined 1" in result.output

    repaired = read_artifact(Document, folder / "document.json")
    assert repaired is not None
    assert repaired.blocks[0].text == clean
    assert repaired.content_hash == repaired.recompute_hash()


def test_repair_leaves_a_clean_text_alone(tmp_path: Path) -> None:
    from typer.testing import CliRunner

    from targum.cli import app
    from targum.models import Block, BlockKind, Document, read_artifact

    out = tmp_path / "targum-out"
    folder = out / "p1" / "clean-he"
    folder.mkdir(parents=True)
    document = Document(
        source="m",
        title="A Book",
        language="he",
        blocks=[Block(id="b0000", kind=BlockKind.paragraph, text="הוא הלך הביתה")],
    )
    document.content_hash = document.recompute_hash()
    document.write(folder / "document.json")

    result = CliRunner().invoke(app, ["repair", "--out", str(out)])
    assert result.exit_code == 0, result.output
    assert "in 0 targums" in result.output

    after = read_artifact(Document, folder / "document.json")
    assert after is not None and after.content_hash == document.content_hash


def test_building_a_catalogue_text_reads_its_title_and_model_from_the_catalogue(
    tmp_path: Path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    """Two things the server has always read from the catalogue and the command line did
    not.

    The title, because a plain .txt carries none — five books were built with no name at
    the top of the reader. And the model, because the cache is keyed on it: a build that
    names a different one translates the whole book again at the reader's expense, which
    is a way to pay twice for a book already bought.
    """
    from targum import cli
    from targum.catalogue import CATALOGUE
    from targum.errors import TargumError

    entry = next(e for e in CATALOGUE if e.model and not e.translations)
    seen: dict[str, object] = {}

    def spy(source, **options):  # type: ignore[no-untyped-def]
        seen.update(options)
        raise TargumError("stop here")

    monkeypatch.setattr(cli, "Build", spy)
    from typer.testing import CliRunner

    CliRunner().invoke(
        cli.app, ["build", entry.source, "--to", "en", "--out", str(tmp_path / "out")]
    )

    assert seen.get("title") == entry.title
    assert seen.get("model") == entry.model


def test_a_text_the_catalogue_does_not_know_is_left_alone(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from targum import cli
    from targum.errors import TargumError

    seen: dict[str, object] = {}

    def spy(source, **options):  # type: ignore[no-untyped-def]
        seen.update(options)
        raise TargumError("stop here")

    monkeypatch.setattr(cli, "Build", spy)
    from typer.testing import CliRunner

    source = tmp_path / "mine.txt"
    source.write_text("שלום עולם\n", encoding="utf-8")
    CliRunner().invoke(cli.app, ["build", str(source), "--to", "en"])

    assert seen.get("title") == "", "nothing invented for a text nobody catalogued"


def test_rebuild_words_re_annotates_and_spends_nothing(tmp_path: Path) -> None:
    """A build compares the annotator's name and redoes an old annotation for free — but
    only a build. `rebuild` read the annotation as it found it, so the day every word
    became a token, nothing on anybody's shelf changed. `--words` is how it reaches them.
    """
    from targum.cli import rebuild_one
    from targum.models import (
        Annotation,
        BlockKind,
        Document,
        Segment,
        SegmentedDocument,
        Token,
        Translation,
        read_artifact,
    )

    out = tmp_path / "targum-out"
    folder = out / "book-he"
    (folder / "translations").mkdir(parents=True)
    document = Document(source="m", title="A Book", language="he", blocks=[], content_hash="h")
    segment = Segment(
        id="0000.000-aaa",
        block_id="b0",
        block_index=0,
        index=0,
        text="המלך",
        kind=BlockKind.paragraph,
    )
    segmented = SegmentedDocument(
        document_hash="h", language="he", segmenter="t/1", segments=[segment]
    )
    document.write(folder / "document.json")
    segmented.write(folder / "segments.json")
    Translation(
        name="English",
        document_hash="h",
        source_language="he",
        target_language="en",
        provider="null",
        segments={segment.id: "the king"},
    ).write(folder / "translations" / "null.natural.en.json")
    # As an older annotator left it: the prefix stood in for the word.
    Annotation(
        document_hash="h",
        language="he",
        annotator="stanza/old/tokenize,pos,lemma+roots+wordfreq",
        method="frequency",
        method_note="",
        tokens={segment.id: [Token(start=0, end=4, surface="המלך", lemma="ה", band=1)]},
    ).write(folder / "annotation.json")

    class Newer:
        name = "stanza/new/tokenize,pos,lemma+roots+everyword+wordfreq"
        asked = 0

        def annotate(self, segmented, vocalization=None):  # type: ignore[no-untyped-def]
            self.asked += 1
            return Annotation(
                document_hash="h",
                language="he",
                annotator=self.name,
                method="frequency",
                method_note="",
                tokens={
                    segment.id: [
                        Token(start=0, end=4, surface="המלך", lemma="מלך", band=2, pos="NOUN")
                    ]
                },
            )

    newer = Newer()
    title, pages = rebuild_one(
        folder,
        reads=None,
        covers=out / "thumbs",
        annotate=lambda f, d: newer,  # type: ignore[arg-type,return-value]
    )
    assert title == "A Book" and pages
    assert newer.asked == 1
    written = read_artifact(Annotation, folder / "annotation.json")
    assert written is not None and written.annotator == newer.name
    assert written.tokens[segment.id][0].lemma == "מלך"

    # Up to date already: left alone.
    rebuild_one(folder, reads=None, covers=out / "thumbs", annotate=lambda f, d: newer)  # type: ignore[arg-type,return-value]
    assert newer.asked == 1

    # Without the flag, a rebuild never touches the words.
    (folder / "annotation.json").write_text("{}", encoding="utf-8")
    rebuild_one(folder, reads=None, covers=out / "thumbs")
    assert (folder / "annotation.json").read_text(encoding="utf-8") == "{}"


def test_rebuilt_words_carry_what_they_used_to_be_called(tmp_path: Path) -> None:
    """`rebuild --words` is how an annotator change reaches a box — it is what deploy.sh
    runs — so it is the moment a reader's marks are carried across or lost.

    Marks are filed by lemma. The build path worked the moves out and handed them to the
    page; this one re-annotated and rendered without them, which would have made a deploy
    precisely the event that orphaned a quarter of every reader's words, silently
    (targum-internal#141).
    """
    from targum.cli import rebuild_one
    from targum.models import (
        Annotation,
        BlockKind,
        Document,
        Segment,
        SegmentedDocument,
        Token,
        Translation,
    )

    out = tmp_path / "targum-out"
    folder = out / "book-he"
    (folder / "translations").mkdir(parents=True)
    document = Document(source="m", title="A Book", language="he", blocks=[], content_hash="h")
    segment = Segment(
        id="0000.000-aaa",
        block_id="b0",
        block_index=0,
        index=0,
        text="לאורך הדרך",
        kind=BlockKind.paragraph,
    )
    segmented = SegmentedDocument(
        document_hash="h", language="he", segmenter="t/1", segments=[segment]
    )
    document.write(folder / "document.json")
    segmented.write(folder / "segments.json")
    Translation(
        name="English",
        document_hash="h",
        source_language="he",
        target_language="en",
        provider="null",
        segments={segment.id: "along the way"},
    ).write(folder / "translations" / "null.natural.en.json")
    # As the older annotator left it: the ל stayed on the lemma, which is the bug the
    # newer one fixes and the reason the mark has to move.
    Annotation(
        document_hash="h",
        language="he",
        annotator="stanza/old/tokenize,pos,lemma",
        method="frequency",
        method_note="",
        tokens={
            segment.id: [Token(start=0, end=5, surface="לאורך", lemma="לאורך", band=3)],
        },
    ).write(folder / "annotation.json")

    class Newer:
        name = "dicta/dicta-il/dictabert-joint/roots"

        def annotate(self, segmented, vocalization=None):  # type: ignore[no-untyped-def]
            return Annotation(
                document_hash="h",
                language="he",
                annotator=self.name,
                method="frequency",
                method_note="",
                tokens={
                    segment.id: [
                        Token(start=0, end=5, surface="לאורך", lemma="ארך", band=3, pos="NOUN")
                    ]
                },
            )

    title, pages = rebuild_one(
        folder,
        reads=None,
        covers=out / "thumbs",
        annotate=lambda f, d: Newer(),  # type: ignore[arg-type,return-value]
    )
    assert title == "A Book" and pages

    page = (folder / "reader" / "index.html").read_text(encoding="utf-8")
    assert '"moves"' in page, "the rebuilt page tells the reader what its words were called"
    assert "לאורך" in page and "ארך" in page


def test_seed_builds_ruth_the_news_piece_and_every_scene_in_order() -> None:
    """A path with a gap in it is a row of build buttons a reader who knows no Hebrew
    can press, so every scene is seeded, always, in scene order."""
    from targum.catalogue import CATALOGUE, Kind
    from targum.cli import SEED, seeds

    planned = seeds()
    assert planned[: len(SEED)] == list(SEED)
    scenes = [e.id for e in CATALOGUE if e.kind is Kind.dialogue]
    assert set(planned[len(SEED) :]) == set(scenes) and scenes, "every dialogue entry"
    assert planned[len(SEED) :] == [
        "scene-01-nice-to-meet-you",
        "scene-02-in-a-cafe",
        "scene-03-which-way",
        "scene-18-two-coffees",
    ]


def test_seed_shares_one_lemmatizer_per_register(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A hundred scenes each loading their own Stanza reached six and a half gigabytes
    on the box and were killed twenty-four texts in. The models are shared across the
    run: one lemmatizer for scripture, one for everything else."""
    from targum import cli

    handed: list[object] = []

    class FakeBuild:
        def __init__(self, source: str, **options: object) -> None:
            handed.append(options.get("lemmatizer"))
            self.source = source

        def run(self) -> object:
            out = tmp_path / "shared" / self.source.replace(":", "-").replace("/", "-")
            out.mkdir(parents=True, exist_ok=True)
            return type("Result", (), {"out_dir": out})()

    monkeypatch.setattr(cli, "Build", FakeBuild)
    monkeypatch.setattr("targum.coverage.lemmas", lambda folder: {})
    monkeypatch.setattr("targum.annotate.lemma.for_source", lambda source, **kw: object())
    cli.seed(out=tmp_path)

    from targum.catalogue import by_id
    from targum.models import is_biblical

    registers = {is_biblical(by_id(entry_id).source) for entry_id in cli.seeds()}
    assert len(handed) == len(cli.seeds())
    assert all(lemmatizer is not None for lemmatizer in handed), "every build is handed one"
    assert len({id(lemmatizer) for lemmatizer in handed}) == len(registers), (
        "one per register, not one per text"
    )


def test_licences_reports_the_corpus_by_what_may_leave(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ "What can leave?" is answered by running something rather than by remembering
    where each source came from (targum-internal #115).

    A recording under ShareAlike may leave and owes a credit; one with nothing written
    down is unknown and is counted apart from the free ones, because an unchecked licence
    is not an absent one.
    """
    import json

    monkeypatch.setenv("TARGUM_RECORDING_DIR", str(tmp_path))
    # The catalogue is the private half and is absent on a public checkout; where it is
    # present it would drown three fixtures in four hundred real entries. Asked of the
    # recordings alone, which is the half this test owns.
    monkeypatch.setattr("targum.catalogue.everything", lambda: [])
    for name, licence in (("shared-alike", "CC BY-SA 3.0"), ("older", "public domain")):
        folder = tmp_path / name
        folder.mkdir()
        (folder / "recording.json").write_text(
            json.dumps({"source": name, "credit": "A Reader", "licence": licence, "parts": []}),
            encoding="utf-8",
        )
    nothing = tmp_path / "unchecked"
    nothing.mkdir()
    (nothing / "recording.json").write_text(
        json.dumps({"source": "unchecked", "credit": "A Reader", "licence": "", "parts": []}),
        encoding="utf-8",
    )

    result = runner.invoke(app, ["licences"])

    assert result.exit_code == 0, result.output
    assert "free" in result.output and "owed" in result.output
    assert "unknown" in result.output
    assert "unchecked" in result.output, "it names what to go and check"


def test_parasha_entries_write_puts_the_portions_on_the_shelf_as_one_collection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Added when absent. On a rerun the members are the corpus's to say and the words
    are whoever edited them (targum-internal #145)."""
    import json

    from targum.parasha.models import Index, Portion

    def portion(slug: str, hebrew: str, number: int, summary: str) -> Portion:
        return Portion(
            slug=slug,
            name=slug,
            hebrew=hebrew,
            numbers=[number],
            summary=summary,
            books=["Genesis"],
        )

    corpus = tmp_path / "parasha"
    corpus.mkdir()
    monkeypatch.setenv("TARGUM_PARASHA_DIR", str(corpus))
    index = Index(
        portions={
            "noach": portion("noach", "נֹחַ", 2, "Genesis 6:9-11:32"),
            "bereshit": portion("bereshit", "בְּרֵאשִׁית", 1, "Genesis 1:1-6:8"),
        }
    )
    (corpus / "index.json").write_text(index.model_dump_json(), encoding="utf-8")
    catalogue = tmp_path / "catalogue.json"
    catalogue.write_text(
        json.dumps(
            {
                "entries": [{"id": "genesis", "title": "בראשית"}],
                "collections": [
                    {
                        "id": "torah",
                        "title": "תורה",
                        "english": "The Torah",
                        "members": ["genesis"],
                        "ordered": True,
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("TARGUM_CATALOGUE", str(catalogue))

    printed = runner.invoke(app, ["parasha", "entries"])
    assert printed.exit_code == 0, printed.output
    assert "torah-portions" in printed.output
    assert "parasha-noach" in printed.output

    result = runner.invoke(app, ["parasha", "entries", "--write"])
    assert result.exit_code == 0, result.output
    written = json.loads(catalogue.read_text(encoding="utf-8"))
    assert [row["id"] for row in written["entries"]] == [
        "genesis",
        "parasha-bereshit",
        "parasha-noach",
    ]
    assert [group["id"] for group in written["collections"]] == ["torah", "torah-portions"]
    group = written["collections"][1]
    assert group["members"] == ["parasha-bereshit", "parasha-noach"]
    assert group["ordered"] is True
    assert written["entries"][2]["author"] == "בראשית"

    # A person edits the blurb and drops a member; the corpus grows by one.
    group["blurb"] = "Mine."
    group["members"] = ["parasha-noach"]
    catalogue.write_text(json.dumps(written, ensure_ascii=False), encoding="utf-8")
    index.portions["lech-lecha"] = portion("lech-lecha", "לֶךְ־לְךָ", 3, "Genesis 12:1-17:27")
    (corpus / "index.json").write_text(index.model_dump_json(), encoding="utf-8")

    again = runner.invoke(app, ["parasha", "entries", "--write"])
    assert again.exit_code == 0, again.output
    written = json.loads(catalogue.read_text(encoding="utf-8"))
    assert len(written["collections"]) == 2, "merged into the one it has, not added again"
    group = next(g for g in written["collections"] if g["id"] == "torah-portions")
    assert group["members"] == ["parasha-bereshit", "parasha-noach", "parasha-lech-lecha"]
    assert group["blurb"] == "Mine."


def test_models_fetch_he_fetches_dicta_and_nothing_of_stanzas(monkeypatch, tmp_path: Path) -> None:
    """A licence claim, pinned: Hebrew's sentences are drawn by rule and its words read by
    DICTA, so no model of Stanza's is fetched for it (targum-internal#146)."""
    from targum import segment as segment_module
    from targum.annotate import dicta

    monkeypatch.setenv("TARGUM_MODEL_DIR", str(tmp_path / "models"))
    monkeypatch.setattr(dicta.DictaLemmatizer, "model", lambda self: (object(), object()))

    def refuse(*args: object, **kwargs: object) -> None:
        raise AssertionError("Stanza was asked for a Hebrew model")

    monkeypatch.setattr(segment_module, "download", refuse)
    monkeypatch.setattr(segment_module, "has_processors", refuse)
    result = runner.invoke(app, ["models", "fetch", "he"])
    assert result.exit_code == 0, result.output
    assert dicta.MODEL in result.output


def test_models_fetch_he_says_when_dicta_cannot_be_fetched(monkeypatch, tmp_path: Path) -> None:
    from targum.annotate import dicta

    monkeypatch.setenv("TARGUM_MODEL_DIR", str(tmp_path / "models"))

    def broken(self: object) -> None:
        raise OSError("no route to host")

    monkeypatch.setattr(dicta.DictaLemmatizer, "model", broken)
    result = runner.invoke(app, ["models", "fetch", "he"])
    assert result.exit_code == 1
    assert "Could not download" in result.output
    assert "Traceback" not in result.output


def test_a_rebuilt_import_keeps_its_recording_and_its_pictures(tmp_path: Path) -> None:
    """A deploy runs `rebuild` over every home, so a rebuild that drops the media is the
    one event guaranteed to silence every imported text on the box.

    `speech` finds an import by the manifest beside the reader, and only when it is told
    where the folder is. `rebuild_one` never told it, so a build wrote the audio into the
    page and the reel beside it and the next rebuild wrote neither — a reader that played
    a video came back a fifth of the size with nothing in it (targum-internal#179).
    """
    from typer.testing import CliRunner

    from targum.audio import manifest as manifest_module
    from targum.cli import app
    from targum.models import BlockKind, Document, Segment, SegmentedDocument, Translation
    from targum.render import render

    out = tmp_path / "targum-out"
    folder = out / "talk-he"
    (folder / "audio" / "parts").mkdir(parents=True)
    (folder / "audio" / "parts" / "part-001.mp3").write_bytes(b"ID3sound")
    (folder / "audio" / "parts" / "part-001.mp4").write_bytes(b"ftypmp42film")

    segment = Segment(
        id="0000.000-aaa",
        block_id="b0",
        block_index=0,
        index=0,
        text="שלום",
        kind=BlockKind.paragraph,
    )
    document = Document(
        source="talk.mp4", title="A Talk", language="he", blocks=[], content_hash="h"
    )
    segmented = SegmentedDocument(
        document_hash="h", language="he", segmenter="t/1", segments=[segment]
    )
    translation = Translation(
        name="English",
        document_hash="h",
        source_language="he",
        target_language="en",
        provider="null",
        segments={segment.id: "peace"},
    )
    document.write(folder / "document.json")
    segmented.write(folder / "segments.json")
    (folder / "translations").mkdir()
    translation.write(folder / "translations" / "null.natural.en.json")
    manifest_module.write(
        folder,
        manifest_module.AudioManifest(
            source="talk.mp4",
            sha256="x",
            duration=10.0,
            language="he",
            parts=[
                manifest_module.ManifestPart(
                    number=1,
                    start=0.0,
                    end=10.0,
                    audio="audio/parts/part-001.mp3",
                    video="audio/parts/part-001.mp4",
                    spans={segment.id: [0.0, 10.0]},
                )
            ],
        ),
    )

    render(document, segmented, [translation], folder / "reader", folder=folder)
    built = (folder / "reader" / "index.html").read_text(encoding="utf-8")
    assert "data:audio" in built and "<video" in built
    assert (folder / "reader" / "video" / "part-001.mp4").is_file()

    result = CliRunner().invoke(app, ["rebuild", "--out", str(out)])
    assert result.exit_code == 0, result.output

    again = (folder / "reader" / "index.html").read_text(encoding="utf-8")
    assert "data:audio" in again, "the rebuild wrote a reader with no recording in it"
    assert "<video" in again, "the rebuild wrote a reader with no picture in it"
    assert (folder / "reader" / "video" / "part-001.mp4").is_file()
