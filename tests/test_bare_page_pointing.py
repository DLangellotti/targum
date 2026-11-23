"""A pointed upload with a page that lost its marks gets that page pointed (2026-11-23).

A photographed children's book was read with its nikkud on every page but one, whose
five paragraphs came back bare. The text was mostly pointed, so it was taken to be a
pointed edition and no diacritizer ran: those paragraphs stayed bare in the reader. An
edition's own bare words are its editor's choice; a whole bare paragraph in an upload is
a reading that lost its marks.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from targum import vocalize as vocalize_module
from targum.models import Segment, SegmentedDocument
from targum.pipeline import Build
from targum.vocalize.base import LETTERS, has_nikkud

POINTED = "אִילִי מַגְבִּיר אֶת קֶצֶב הֲלִיכָתוֹ."
PARTLY = "לָמָּה הָאֲחֵרִים הולכים לְאַט?"
BARE = "סוסים לעולם לא יסכימו שבני אדם ירכבו עליהם."


class Diacritizer:
    name = "fake/1"
    model = "fake-model"

    def __init__(self) -> None:
        self.asked: list[str] = []

    def available(self) -> tuple[bool, str]:
        return True, ""

    def vocalize(self, segments: list[Segment], language: str) -> dict[str, str]:
        self.asked += [segment.id for segment in segments]
        return {
            segment.id: "".join(
                c + ("ַ" if ord(c) in LETTERS and not has_nikkud(c) else "") for c in segment.text
            )
            for segment in segments
        }


def book(*texts: str) -> SegmentedDocument:
    return SegmentedDocument(
        document_hash=str(abs(hash(texts))),
        language="he",
        segmenter="fake",
        segments=[
            Segment(id=f"s{i}", block_id=f"b{i}", block_index=i, index=0, text=text)
            for i, text in enumerate(texts)
        ],
    )


def pointed_by(
    source: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *texts: str,
    pictures: bool = True,
):
    engine = Diacritizer()
    monkeypatch.setattr(vocalize_module, "for_source", lambda *_a, **_k: engine)
    build = Build(source, target_language="en", provider_name="null", out=tmp_path / "book")
    build._resolved_out = tmp_path / "book"
    return engine, build.vocalize(book(*texts), read_from_pictures=pictures)


def test_a_bare_page_in_a_pointed_upload_is_pointed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine, result = pointed_by(
        "/uploads/4ffd65", tmp_path, monkeypatch, POINTED, POINTED, PARTLY, POINTED, BARE
    )
    assert result is not None
    assert engine.asked == ["s4"], "only the sentence with no marks at all"
    assert has_nikkud(result.segments["s4"])
    assert result.machine == ["s4"], "and marked as the machine's"
    assert result.segments["s2"] == PARTLY, "a sentence the page pointed in part stays as printed"
    assert result.segments["s0"] == POINTED


def test_an_edition_keeps_its_bare_sentences(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine, result = pointed_by(
        "sefaria:Ruth 1", tmp_path, monkeypatch, POINTED, POINTED, POINTED, BARE
    )
    assert engine.asked == []
    assert result is not None and "s3" not in result.segments


def test_a_bare_line_in_a_text_read_from_its_own_file_stays_bare(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ben-Yehuda's pages carry a bare line or two of their own: the file has them so."""
    engine, result = pointed_by(
        "https://benyehuda.org/read/1",
        tmp_path,
        monkeypatch,
        POINTED,
        POINTED,
        POINTED,
        BARE,
        pictures=False,
    )
    assert engine.asked == []
    assert result is not None and "s3" not in result.segments


def test_the_rebuild_points_a_photographed_book_s_bare_page(tmp_path: Path) -> None:
    """The book already on the shelf: the next deploy's `rebuild --words` mends it."""
    from targum import cli
    from targum.models import Block, BlockKind, Document, Translation, Vocalization

    folder = tmp_path / "3-he"
    folder.mkdir()
    texts = (POINTED, POINTED, BARE)
    document = Document(
        source="/uploads/4ffd65",
        title="ספר",
        language="he",
        ingester="picture/2",
        content_hash="c",
        source_hash="s",
        blocks=[
            Block(id=f"b{i}", kind=BlockKind.paragraph, text=text) for i, text in enumerate(texts)
        ],
    )
    document.write(folder / "document.json")
    segmented = book(*texts)
    segmented.write(folder / "segments.json")
    Vocalization(
        document_hash=segmented.document_hash,
        language="he",
        vocalizer="source",
        segments={"s0": POINTED, "s1": POINTED},
    ).write(folder / "vocalization.json")
    (folder / "translations").mkdir()
    Translation(
        name="null",
        document_hash=segmented.document_hash,
        source_language="he",
        target_language="en",
        provider="null",
        segments={f"s{i}": "A line." for i in range(len(texts))},
    ).write(folder / "translations" / "null.natural.en.json")
    engine = Diacritizer()

    title, _written = cli.rebuild_one(
        folder,
        reads=None,
        covers=tmp_path / "thumbs",
        vocalize=lambda _document: engine,  # type: ignore[arg-type,return-value]
    )
    assert title == "ספר"
    after = Vocalization.model_validate_json((folder / "vocalization.json").read_text())
    assert engine.asked == ["s2"]
    assert has_nikkud(after.segments["s2"]) and after.machine == ["s2"]
    assert after.segments["s0"] == POINTED
