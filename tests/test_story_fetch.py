"""`story:`: a story targum wrote, read off its shelf as paragraphs (targum-internal#739's
narrative path). The shelf is a temporary folder; nothing is fetched or bought."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from targum import correct
from targum.errors import OffHere, UnsupportedSource
from targum.ingest import fetch
from targum.ingest.fetch import story
from targum.models import BlockKind
from targum.tables import imports, registers

STORY = {
    "id": "fr-01-un-dimanche",
    "language": "fr",
    "title": "Un dimanche à Lyon",
    "english": "A Sunday in Lyon",
    "gloss": "A day at the market and by the river.",
    "paragraphs": [
        {"text": "Dimanche, je suis allée au marché. Il faisait beau.", "english": "…"},
        {"text": "", "english": ""},
        {"text": "Après, j'ai marché au bord de la Saône.", "english": "…"},
    ],
}


@pytest.fixture
def shelf(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("TARGUM_STORY_DIR", str(tmp_path))
    (tmp_path / f"{STORY['id']}.json").write_text(json.dumps(STORY), encoding="utf-8")
    return tmp_path


def test_a_story_is_a_document_of_paragraphs(shelf: Path) -> None:
    document = fetch.load(f"story:{STORY['id']}")
    assert document.source == "story:fr-01-un-dimanche"
    assert document.language == "fr" and document.title == "Un dimanche à Lyon"
    assert [b.kind for b in document.blocks] == [BlockKind.paragraph] * 2  # the blank is left out
    assert document.blocks[1].text.startswith("Après")


def test_an_edited_story_is_a_changed_text(shelf: Path) -> None:
    before = fetch.load(f"story:{STORY['id']}").source_hash
    edited = dict(STORY, paragraphs=[{"text": "Dimanche, je suis allée au marché.", "english": ""}])
    (shelf / f"{STORY['id']}.json").write_text(json.dumps(edited), encoding="utf-8")
    assert fetch.load(f"story:{STORY['id']}").source_hash != before


def test_a_missing_story_says_where_it_looked(shelf: Path) -> None:
    with pytest.raises(OffHere) as raised:
        fetch.load("story:nope")
    assert str(shelf) in raised.value.hint


def test_the_shelf_sits_beside_the_dialogues(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("TARGUM_STORY_DIR", raising=False)
    monkeypatch.setenv("TARGUM_DIALOGUE_DIR", str(tmp_path / "dialogues"))
    assert story.root() == tmp_path / "stories"


def test_a_story_is_everybody_s_and_written_by_a_model() -> None:
    assert fetch.is_identifier("story:fr-01-un-dimanche")
    assert not correct.own_source("story:fr-01-un-dimanche")
    assert "story:" in imports.MODEL_WRITTEN
    assert registers.register_of("story:fr-01-un-dimanche") == registers.SCENES_COUNT_AS


@pytest.mark.parametrize("scheme", ["dialogue", "story"])
@pytest.mark.parametrize("name", ["../outside", "..%2Foutside", "a/b", "/etc/passwd", "Fr-01"])
def test_a_shelf_name_cannot_leave_its_shelf(
    scheme: str, name: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """qa on #1306: `story:../outside` read a JSON file off the shelf, and so did
    `dialogue:` before it. Neither door takes such a name, and `load` refuses it too."""
    from targum import ingest

    shelf = tmp_path / "shelf"
    shelf.mkdir()
    (tmp_path / "outside.json").write_text(json.dumps(STORY), encoding="utf-8")
    monkeypatch.setenv("TARGUM_STORY_DIR", str(shelf))
    monkeypatch.setenv("TARGUM_DIALOGUE_DIR", str(shelf))
    assert not ingest.fetchable(f"{scheme}:{name}")
    with pytest.raises(UnsupportedSource):
        fetch.load(f"{scheme}:{name}")


def test_every_good_shelf_name_still_reads(shelf: Path) -> None:
    from targum import ingest

    assert ingest.fetchable(f"story:{STORY['id']}")
    assert ingest.fetchable("dialogue:ru-01-at-the-market")


def test_what_the_scene_loop_writes_is_targum_s(tmp_path: Path) -> None:
    from targum import ledger

    for source in ("story:fr-01-un-dimanche", "dialogue:ru-01-at-the-market", "weekly:2026-w46"):
        assert ledger._licence_of(tmp_path, source) == "targum"
