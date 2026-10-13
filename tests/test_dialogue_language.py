"""A scene says which language it is written in (2026-10-13); every scene before that is
Hebrew and says nothing."""

from __future__ import annotations

from pathlib import Path

import pytest

from targum.dialogue.models import Cast, Dialogue, Speaker, Turn
from targum.ingest.fetch.dialogue import DialogueFetcher


def scene(**over: object) -> Dialogue:
    fields: dict[str, object] = {
        "id": "ru-01-at-the-market",
        "title": "На рынке",
        "english": "At the market",
        "level": 1,
        "cast": Cast(A=Speaker(voice="Leda", gender="f"), B=Speaker(voice="Charon", gender="m")),
        "turns": [
            Turn(who="A", text="Сколько стоят яблоки?", english="How much are the apples?"),
            Turn(who="B", text="Сто рублей.", english="A hundred roubles."),
        ],
    }
    fields.update(over)
    return Dialogue.model_validate(fields)


def test_a_scene_that_says_nothing_is_hebrew() -> None:
    assert scene().language == "he"
    assert scene(language="ru").language == "ru"


def test_the_document_is_in_the_scene_s_language(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TARGUM_DIALOGUE_DIR", str(tmp_path))
    written = scene(language="ru")
    (tmp_path / f"{written.id}.json").write_text(written.model_dump_json(), encoding="utf-8")
    document = DialogueFetcher().load(written.id)
    assert document.language == "ru"
    assert [block.text for block in document.blocks] == [turn.text for turn in written.turns]
