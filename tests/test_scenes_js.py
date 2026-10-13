"""The numbered scenes as a sequence (`render/assets/scenes.js`), run rather than read.

Two languages' scenes share numbers, so the next scene is asked of one language at a
time (2026-10-13).
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

SCENES = (
    Path(__file__).resolve().parent.parent / "src" / "targum" / "render" / "assets" / "scenes.js"
)

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")


def run(script: str) -> Any:
    program = (
        "global.window = {};\n"
        f"require({json.dumps(str(SCENES))});\n"
        "const S = window.TargumScenes;\n"
        f"process.stdout.write(JSON.stringify((function () {{ {script} }})()));\n"
    )
    done = subprocess.run(["node", "-e", program], capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def test_a_scene_in_another_language_is_numbered_in_its_own_count() -> None:
    assert run(
        'return [S.numberOf("scene-ru-02-x"), S.numberOf("scene-03-y"), S.numberOf("ruth")];'
    ) == [2, 3, 0]


def test_the_next_scene_is_asked_of_one_language_and_hebrew_by_default() -> None:
    shared = [
        {"entry": "scene-ru-01-a", "language": "ru", "document": "r1"},
        {"entry": "scene-01-a", "language": "he", "document": "h1"},
        {"entry": "scene-02-b", "language": "he", "document": "h2"},
        {"entry": "scene-ru-02-b", "language": "ru", "document": "r2"},
    ]
    docs = {"h1": {"done": True}, "r1": {"done": True}}
    got = run(
        f"const shared = {json.dumps(shared)}; const docs = {json.dumps(docs)};"
        " return [S.next(shared, docs).entry, S.next(shared, docs, 'ru').entry];"
    )
    assert got == ["scene-02-b", "scene-ru-02-b"]
