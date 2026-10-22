"""A Tanakh text with no verse refs is refused, not read by the wrong engine (#507).

The morphology (OSHB) is looked up by ref. The shared Ruth was ingested before refs, so
every verse fell through to DICTA while the annotator's name still said `oshb`: the page
claimed one reading and showed another. A build and a rebuild now refuse such a text
with the way out (`targum refs`), and a text that has its refs is read from the tagging.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from test_scripture import FIRST, Stub, tagged  # noqa: F401  (the OSHB fixture)

from targum.annotate.scripture import ScriptureLemmatizer
from targum.errors import TargumError
from targum.models import (
    Block,
    BlockKind,
    Document,
    Segment,
    SegmentedDocument,
    Translation,
)
from targum.pipeline import Build
from targum.refs import NO_REFS


def genesis(with_refs: bool) -> Document:
    document = Document(
        source="sefaria:Genesis 1",
        title="Genesis",
        language="he",
        blocks=[
            Block(
                id=f"b{n:04d}",
                kind=BlockKind.verse,
                text=text,
                ref=f"Genesis 1:{n + 1}" if with_refs else "",
            )
            for n, text in enumerate([FIRST])
        ],
        content_hash="",
    )
    document.content_hash = document.recompute_hash()
    return document


def builder(tmp_path: Path, fake_segmenter: object, **options: object) -> Build:
    return Build(
        "sefaria:Genesis 1",
        target_language="en",
        provider_name="null",
        out=tmp_path / "genesis-he",
        segmenter=fake_segmenter,  # type: ignore[arg-type]
        **options,  # type: ignore[arg-type]
    )


def test_a_tanakh_text_with_no_refs_is_refused(tmp_path: Path, fake_segmenter: object) -> None:
    with pytest.raises(TargumError) as refused:
        builder(tmp_path, fake_segmenter).segment(genesis(with_refs=False))
    assert refused.value.message == NO_REFS
    assert "Run targum refs, then rebuild it." in refused.value.message
    assert not (tmp_path / "genesis-he" / "segments.json").exists(), "nothing is written"


def test_segments_kept_from_before_refs_are_refused_too(
    tmp_path: Path, fake_segmenter: object
) -> None:
    """A rebuild reuses the segments on disk, which is how a refless text was carried."""
    document = genesis(with_refs=True)
    kept = builder(tmp_path, fake_segmenter).segment(document)
    for segment in kept.segments:
        segment.ref = ""
    kept.write(tmp_path / "genesis-he" / "segments.json")
    with pytest.raises(TargumError, match="no verse refs"):
        builder(tmp_path, fake_segmenter).segment(document)


def test_with_refs_it_builds_and_is_read_from_the_morphology(
    tmp_path: Path,
    fake_segmenter: object,
    tagged: Path,  # noqa: F811
) -> None:
    stub = Stub()
    build = builder(tmp_path, fake_segmenter, lemmatizer=ScriptureLemmatizer(stub), difficulty=True)
    segmented = build.segment(genesis(with_refs=True))
    first = segmented.segments[0]
    assert first.kind is BlockKind.verse and first.ref == "Genesis 1:1"
    annotation = build.annotate(segmented)
    assert annotation is not None
    assert annotation.annotator.startswith("oshb/")
    assert stub.asked == [], "no verse reaches the fallback"
    lemmas = [token.lemma for token in annotation.tokens[first.id]]
    assert lemmas[:3] == ["ראשית", "ברא", "אלהים"]


def test_other_texts_are_never_asked_about_refs(tmp_path: Path, fake_segmenter: object) -> None:
    document = Document(
        source="https://benyehuda.org/x.txt",
        title="x",
        language="he",
        blocks=[Block(id="b0000", kind=BlockKind.paragraph, text="שלום עולם.")],
        content_hash="",
    )
    document.content_hash = document.recompute_hash()
    build = Build(
        document.source,
        target_language="en",
        provider_name="null",
        out=tmp_path / "x-he",
        segmenter=fake_segmenter,  # type: ignore[arg-type]
    )
    assert build.segment(document).segments


def test_a_rebuild_keeps_a_refless_copy_and_does_not_read_it_again(tmp_path: Path) -> None:
    """`rebuild_one` re-reads a text whose annotator changed; a refless Tanakh text is
    refused there instead, so the caller keeps the copy on the shelf and names it."""
    from targum import cli
    from targum.models import Annotation

    folder = tmp_path / "genesis-he"
    folder.mkdir()
    document = genesis(with_refs=False)
    document.write(folder / "document.json")
    segmented = SegmentedDocument(
        document_hash=document.content_hash,
        language="he",
        segmenter="test/1",
        segments=[
            Segment(
                id=f"{n:04d}.000-aaaaaa",
                block_id=block.id,
                block_index=n,
                index=0,
                kind=BlockKind.verse,
                text=block.text,
            )
            for n, block in enumerate(document.blocks)
        ],
    )
    segmented.write(folder / "segments.json")
    Annotation(
        document_hash=document.content_hash,
        annotator="older/1",
        language="he",
        method="test",
        method_note="",
        tokens={},
    ).write(folder / "annotation.json")
    (folder / "translations").mkdir()
    Translation(
        name="English",
        document_hash=document.content_hash,
        source_language="he",
        target_language="en",
        provider="null",
        segments={segment.id: "In the beginning." for segment in segmented.segments},
    ).write(folder / "translations" / "null.natural.en.json")
    before = (folder / "annotation.json").read_text(encoding="utf-8")

    class Newer:
        name = "oshb/7+newer/1"

        def annotate(self, *args: object, **kwargs: object) -> object:
            raise AssertionError("a refless Tanakh text is not read again")

    with pytest.raises(TargumError, match="no verse refs"):
        cli.rebuild_one(
            folder,
            reads=None,
            covers=tmp_path / "thumbs",
            annotate=lambda folder, document: Newer(),  # type: ignore[arg-type,return-value]
        )
    assert (folder / "annotation.json").read_text(encoding="utf-8") == before
    assert json.loads(before)["annotator"] == "older/1"


def test_seed_skips_a_refless_row_names_it_and_builds_the_rest(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The seed meets the refusal as it meets any row it cannot build: one skipped row,
    named at the end, and every other row built."""
    from targum import cli
    from targum.catalogue import by_id

    refused = by_id(cli.seeds()[0])
    built: list[str] = []

    class FakeBuild:
        def __init__(self, source: str, **options: object) -> None:
            self.source = source

        def run(self) -> object:
            if self.source == refused.source:
                raise TargumError(NO_REFS)
            built.append(self.source)
            out = tmp_path / "shared" / self.source.replace(":", "-").replace("/", "-")
            out.mkdir(parents=True, exist_ok=True)
            return type("Result", (), {"out_dir": out})()

    monkeypatch.setattr(cli, "Build", FakeBuild)
    monkeypatch.setattr("targum.coverage.lemmas", lambda folder: {})
    monkeypatch.setattr("targum.annotate.lemma.for_source", lambda source, **kw: object())
    cli.seed(out=tmp_path)
    assert len(built) == len(cli.seeds()) - 1
    said = " ".join(capsys.readouterr().out.split())
    assert f"unbuilt: {refused.title} — {NO_REFS}" in said
