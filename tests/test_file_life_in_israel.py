"""Filing the olim texts under "Life in Israel" (targum-internal#393).

Scenes 101–200 reached the shelf with no catalogue row, which keeps them out of the
Library; the clips had rows and no subject that said who they were for. The script writes
the one and tags the other, and a second run must change nothing.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest

from targum import catalogue as catalogue_module
from targum.catalogue import Tag

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "file_life_in_israel.py"


def _script() -> Any:
    spec = importlib.util.spec_from_file_location("file_life_in_israel", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _scene(folder: Path, identifier: str) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    scene = {
        "id": identifier,
        "title": "הנחה בארנונה",
        "english": "A discount on the arnona",
        "gloss": "A new immigrant asks the city about the arnona.",
        "named": {"ru": "Скидка на арнону"},
        "glossed": {"ru": "Новая репатриантка спрашивает про арнону."},
        "level": 2,
        "cast": {
            "A": {"voice": "Leda", "gender": "f", "name": "דנה"},
            "B": {"voice": "Charon", "gender": "m", "name": "יונתן"},
        },
        "turns": [{"who": "A", "text": "שָׁלוֹם", "english": "Hello"}],
    }
    (folder / f"{identifier}.json").write_text(json.dumps(scene), encoding="utf-8")


def test_a_missing_scene_gets_a_row_and_a_clip_gains_the_tag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    script = _script()
    dialogues = tmp_path / "dialogues"
    _scene(dialogues, "101-arnona-discount")
    _scene(dialogues, "05-at-the-supermarket")  # not an olim scene: left alone
    monkeypatch.setenv("TARGUM_DIALOGUE_DIR", str(dialogues))
    clip = script.CLIPS[0]
    rows = [{"id": clip, "tags": ["health"], "source": "video:x"}]

    todo = script.plan(rows, script.olim_scenes())

    scene_row = next(row for row in todo if row["id"] == "scene-101-arnona-discount")
    assert scene_row["source"] == "dialogue:101-arnona-discount"
    assert scene_row["tags"] == [Tag.israel.value]
    assert scene_row["blurbs"] == {"ru": "Новая репатриантка спрашивает про арнону."}
    entry = catalogue_module._entry(scene_row)
    assert entry.kind.value == "dialogue" and Tag.israel in entry.tags
    assert {"id": clip, "tags": ["health", "israel"]} in todo
    assert not any(row["id"].startswith("scene-05") for row in todo)


def test_a_second_run_changes_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    script = _script()
    dialogues = tmp_path / "dialogues"
    _scene(dialogues, "101-arnona-discount")
    monkeypatch.setenv("TARGUM_DIALOGUE_DIR", str(dialogues))
    rows = [
        {"id": "scene-101-arnona-discount", "tags": ["israel"]},
        *({"id": clip, "tags": ["israel"]} for clip in script.CLIPS),
    ]
    assert script.plan(rows, script.olim_scenes()) == []
