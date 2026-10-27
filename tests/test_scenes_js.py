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


def test_hebrew_b1_is_a_series_of_its_own() -> None:
    """Hebrew's B1 conversations are `scene-he-NN` (2026-10-27): Hebrew, and numbered
    from 1 again. Order never interleaves the two, and Hebrew's path is A1's."""
    got = run(
        'return [S.seriesOf("scene-he-01-x"), S.seriesOf("scene-01-y"),'
        ' S.numberOf("scene-he-01-x"), S.onPath("scene-he-01-x", "he"),'
        ' S.onPath("scene-01-y", "he"), S.onPath("scene-ru-01-z", "ru")];'
    )
    assert got == ["he", "", 1, False, True, True]
    ids = ["scene-he-02-b", "ruth", "scene-02-b", "scene-he-01-a", "scene-01-a"]
    ordered = run(
        f"return S.ordered({json.dumps([{'id': i} for i in ids])}).map(function (r) {{"
        " return r.id; });"
    )
    assert ordered == ["scene-01-a", "scene-02-b", "scene-he-01-a", "scene-he-02-b", "ruth"]


def test_a_new_hebrew_reader_starts_on_a1_even_with_b1_built_newer() -> None:
    """`/readers` lists shared texts newest-built first, so B1 arrives ahead of A1."""
    shared = [
        {"entry": "scene-he-01-a", "language": "he", "document": "b1"},
        {"entry": "scene-he-02-b", "language": "he", "document": "b2"},
        {"entry": "scene-02-b", "language": "he", "document": "h2"},
        {"entry": "scene-01-a", "language": "he", "document": "h1"},
    ]
    got = run(
        f"const shared = {json.dumps(shared)};"
        " return [S.next(shared, {}).entry, S.next(shared, {h1: {done: 1}}).entry,"
        " S.next(shared, {h1: {done: 1}, h2: {done: 1}})];"
    )
    assert got == ["scene-01-a", "scene-02-b", None]
