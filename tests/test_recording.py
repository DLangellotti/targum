"""Recordings: what they are, and how a section finds the one it wants.

The audio itself is content and never in the repository, so what is tested here is the
addressing — which is where a recording goes wrong. A wrong file plays the wrong chapter
and says nothing about it, and a reader who does not know the book cannot tell.
"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from targum.recording import Part, Recording
from targum.recording import index as recording_index


def spans(chapter: int, verses: int) -> dict[str, list[float]]:
    return {f"Ruth {chapter}:{n}": [float(n), float(n + 1)] for n in range(1, verses + 1)}


def made(**over: object) -> Recording:
    fields: dict[str, object] = {
        "source": "sefaria:Ruth",
        "credit": "Somebody",
        "licence": "CC BY-SA 3.0",
        "parts": [
            Part(ref="Ruth 1", audio="ruth-1.mp3", spans=spans(1, 22)),
            Part(ref="Ruth 2", audio="ruth-2.mp3", spans=spans(2, 23)),
        ],
    }
    fields.update(over)
    return Recording.model_validate(fields)


def test_a_section_finds_its_part_by_the_verses_it_holds() -> None:
    found = made().part_for(["Ruth 2:1", "Ruth 2:2"])
    assert found is not None
    assert found.audio == "ruth-2.mp3"


def test_the_second_chapter_of_a_range_is_not_the_second_part() -> None:
    """The bug this addressing exists to prevent.

    A reader built for Ruth 2 alone holds one section, and by position that section is
    the first — which by position is chapter one's audio. Asked by ref it is chapter two,
    which is what the reader is actually showing.
    """
    found = made().part_for(["Ruth 2:5"])
    assert found is not None and found.ref == "Ruth 2"


def test_a_section_with_no_recording_gets_none_rather_than_the_nearest() -> None:
    assert made().part_for(["Ruth 4:1"]) is None
    assert made().part_for([]) is None
    assert made().part_for(["", ""]) is None


def test_a_text_with_no_recording_is_silent_rather_than_an_error(tmp_path, monkeypatch) -> None:
    """Most texts have no recording. A library where adding audio to one book breaks
    every other is not a library."""
    monkeypatch.setenv("TARGUM_RECORDING_DIR", str(tmp_path))
    assert recording_index.load("sefaria:Job") is None


def test_a_recording_that_will_not_read_is_silent_too(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("TARGUM_RECORDING_DIR", str(tmp_path))
    folder = tmp_path / recording_index.slug("sefaria:Ruth")
    folder.mkdir()
    (folder / recording_index.MANIFEST).write_text("{not json", encoding="utf-8")
    assert recording_index.load("sefaria:Ruth") is None


def test_a_recording_is_read_back_as_it_was_written(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("TARGUM_RECORDING_DIR", str(tmp_path))
    folder = tmp_path / recording_index.slug("sefaria:Ruth")
    folder.mkdir()
    (folder / recording_index.MANIFEST).write_text(
        json.dumps(made().model_dump()), encoding="utf-8"
    )
    back = recording_index.load("sefaria:Ruth")
    assert back is not None
    assert back.credit == "Somebody"
    assert [part.ref for part in back.parts] == ["Ruth 1", "Ruth 2"]


@pytest.mark.parametrize(
    ("source", "want"),
    [
        ("sefaria:Ruth", "sefaria-ruth"),
        ("sefaria:he:Job", "sefaria-he-job"),
        ("sefaria:I Samuel", "sefaria-i-samuel"),
    ],
)
def test_a_source_keys_the_same_folder_on_any_disk(source: str, want: str) -> None:
    """Lowercase and hyphens only: a folder that resolves on a case-insensitive laptop
    and not on the box is a reader that is silent in production and fine in testing."""
    assert recording_index.slug(source) == want


def test_the_credit_is_required(tmp_path) -> None:
    """Every recording the library can use is used under a licence that names its reader.
    A model that lets the credit be forgotten is how it comes to be forgotten."""
    with pytest.raises(ValidationError):
        Recording.model_validate({"source": "sefaria:Ruth", "licence": "CC BY-SA 3.0"})


def test_a_verse_carries_its_ref_from_ingest_to_segment() -> None:
    """The whole mapping rests on this: the recording is aligned to verses, so a verse
    has to be addressable after segmentation and not only before it."""
    from targum.ingest.fetch import sefaria
    from targum.segment.base import segment_document
    from tests.test_sefaria import payload

    document = sefaria.document_from_payload(payload("he"), "Ruth", "he")

    class Whole:
        name = "test/1"

        def split(self, texts: list[str], language: str) -> list[list[str]]:
            return [[text] for text in texts]

    segmented = segment_document(document, Whole())
    verses = [s for s in segmented.segments if s.kind.value == "verse"]
    assert len(verses) == 85
    assert verses[0].ref == "Ruth 1:1"
    assert verses[-1].ref == "Ruth 4:22"
    assert all(segment.ref == "" for segment in segmented.segments if segment.kind.value != "verse")
