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


def pointed_by(source: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *texts: str):
    engine = Diacritizer()
    monkeypatch.setattr(vocalize_module, "for_source", lambda *_a, **_k: engine)
    build = Build(source, target_language="en", provider_name="null", out=tmp_path / "book")
    build._resolved_out = tmp_path / "book"
    return engine, build.vocalize(book(*texts))


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
