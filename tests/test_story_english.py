"""A story's English is the one the scene loop wrote beside it, never bought (builder-2's
note on the French A2 ship, 2026-11-19: a box build of `story:` fell through to the
machine and would have paid for an English it already had)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from targum.ingest import fetch
from targum.models import Segment, SegmentedDocument
from targum.pipeline import _story_english

STORY = {
    "id": "fr-01-un-dimanche",
    "language": "fr",
    "title": "Un dimanche à Lyon",
    "english": "A Sunday in Lyon",
    "gloss": "",
    "paragraphs": [
        {
            "text": "Dimanche, je suis allée au marché. Il faisait beau.",
            "english": "On Sunday, I went to the market. The weather was fine.",
        },
        {"text": "", "english": ""},
        {
            "text": "Après, j'ai marché au bord de la Saône. C'était calme. J'ai lu.",
            "english": "Afterwards I walked by the Saône, where it was calm, and read.",
        },
    ],
}


def segmented(document_hash: str, by_block: dict[str, list[str]]) -> SegmentedDocument:
    segments = []
    for block_index, (block, texts) in enumerate(by_block.items()):
        for index, text in enumerate(texts):
            segments.append(
                Segment(
                    id=f"{block}-s{index}",
                    block_id=block,
                    block_index=block_index,
                    index=len(segments),
                    text=text,
                )
            )
    return SegmentedDocument(
        document_hash=document_hash, language="fr", segmenter="test", segments=segments
    )


@pytest.fixture
def shelf(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("TARGUM_STORY_DIR", str(tmp_path))
    (tmp_path / f"{STORY['id']}.json").write_text(json.dumps(STORY), encoding="utf-8")
    return tmp_path


def test_a_story_carries_its_own_english(shelf: Path) -> None:
    document = fetch.load(f"story:{STORY['id']}")
    split = segmented(
        document.content_hash,
        {
            "b0000": ["Dimanche, je suis allée au marché.", "Il faisait beau."],
            "b0001": ["Après, j'ai marché au bord de la Saône.", "C'était calme.", "J'ai lu."],
        },
    )
    english = _story_english(document, split)
    assert english is not None
    assert (english.provider, english.kind, english.target_language) == (
        "authored",
        "authored",
        "en",
    )
    # One to one where the English has as many sentences as the French.
    assert english.segments["b0000-s0"] == "On Sunday, I went to the market."
    assert english.segments["b0000-s1"] == "The weather was fine."
    # The whole paragraph on its first sentence where it has fewer, the rest empty.
    assert english.segments["b0001-s0"] == STORY["paragraphs"][2]["english"]
    assert english.segments["b0001-s1"] == "" and english.segments["b0001-s2"] == ""
    assert set(english.segments) == {s.id for s in split.segments}, "every sentence is answered"


def test_a_story_with_no_english_is_left_to_the_build(shelf: Path, tmp_path: Path) -> None:
    bare = {**STORY, "id": "fr-02-sans", "paragraphs": [{"text": "Bonjour.", "english": ""}]}
    (tmp_path / "fr-02-sans.json").write_text(json.dumps(bare), encoding="utf-8")
    document = fetch.load("story:fr-02-sans")
    assert (
        _story_english(document, segmented(document.content_hash, {"b0000": ["Bonjour."]})) is None
    )


def test_the_build_asks_the_story_and_buys_nothing(shelf: Path) -> None:
    """Through `Build.authored`: a `story:` source is answered from its file, so
    `wants_buying` is false for an English build and no translator is asked."""
    from targum.pipeline import Build

    document = fetch.load(f"story:{STORY['id']}")
    split = segmented(document.content_hash, {"b0000": ["a.", "b."], "b0001": ["c."]})
    held = Build.authored(Build.__new__(Build), document, split)
    assert held is not None and held.kind == "authored"
