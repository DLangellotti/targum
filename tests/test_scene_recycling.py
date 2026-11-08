"""`scripts/scene_recycling.py`: how well the scenes bring their words back
(targum-internal#656). Synthetic scenes only."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


def load() -> Any:
    spec = importlib.util.spec_from_file_location("scene_recycling", SCRIPTS / "scene_recycling.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_the_three_shares_count_forms_not_running_words() -> None:
    script = load()
    report = script.measure(
        [
            (1, {"a": 5, "b": 1, "c": 1}),
            (2, {"a": 5, "d": 1}),
            (3, {"b": 1}),
        ]
    )
    # a 10, b 2, c 1, d 1: two of four seen once, one 10+, two in one scene only.
    assert report.forms == 4
    assert report.running == 14
    assert report.once == pytest.approx(0.5)
    assert report.ten_plus == pytest.approx(0.25)
    assert report.one_scene == pytest.approx(0.5)


def test_order_comes_from_the_scene_numbers_not_the_input() -> None:
    script = load()
    shuffled = script.measure([(3, {"x": 1}), (1, {"x": 1, "y": 1}), (2, {"x": 1})])
    assert [s["number"] for s in shuffled.per_scene] == [1, 2, 3]
    assert shuffled.per_scene[0]["introduced"] == ["x", "y"]


def test_a_form_is_owed_when_its_window_closes_short_and_pending_while_open() -> None:
    script = load()
    scenes = [(n, {"filler": 1}) for n in range(1, 25)]
    scenes[0] = (1, {"filler": 1, "kept": 1, "dropped": 1})
    scenes[3] = (4, {"filler": 1, "kept": 1})
    scenes[7] = (8, {"filler": 1, "kept": 1})
    scenes[19] = (20, {"filler": 1, "late": 1})
    report = script.measure(scenes)
    first = report.per_scene[0]
    assert first["owed"] == ["dropped"]
    assert "kept" not in first["owed"] and "kept" not in first["pending"]
    # Scene 20's window runs past scene 24, so its unreturned form is pending, not owed.
    assert report.per_scene[19]["pending"] == ["late"]
    assert report.per_scene[19]["owed"] == []
    assert not report.passes


def test_a_series_that_recycles_passes_and_an_empty_one_is_not_a_failure() -> None:
    script = load()
    good = script.measure([(n, {"a": 1, "b": 1}) for n in range(1, 13)])
    assert good.once == 0 and good.passes
    empty = script.measure([])
    assert empty.scenes == 0 and empty.passes
    assert script.summary("ru", empty) == "ru: no scenes"


def _reader(root: Path, name: str, source: str) -> None:
    folder = root / name
    folder.mkdir()
    (folder / "document.json").write_text(json.dumps({"source": source}), encoding="utf-8")
    (folder / "annotation.json").write_text("{}", encoding="utf-8")
    (folder / "segments.json").write_text("{}", encoding="utf-8")


def test_readers_are_filed_by_series_and_unreadable_ones_are_listed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    script = load()
    _reader(tmp_path, "a", "dialogue:01-hello")
    _reader(tmp_path, "b", "dialogue:02-cafe")
    _reader(tmp_path, "c", "dialogue:ru-01-privet")
    _reader(tmp_path, "d", "dialogue:150-the-allergy")
    _reader(tmp_path, "e", "url:https://example.org")

    class Found:
        def __init__(self, counts: dict[str, int]) -> None:
            self.lemmas = counts

        def count(self, form: str) -> int:
            return self.lemmas[form]

    by_folder = {"a": Found({"x": 1}), "b": Found({"x": 2}), "c": Found({"y": 1}), "d": None}
    monkeypatch.setattr(script, "text_occurrences", lambda folder: by_folder[folder.name])

    found = script.from_readers(tmp_path)
    assert sorted(found) == ["he-1", "he-101", "ru"]
    assert [n for n, _ in found["he-1"][0]] == [1, 2]
    assert found["he-101"] == ([], [150])

    out = tmp_path / "report.json"
    assert script.main(["--from", str(tmp_path), "--out", str(out)]) == 0
    written = json.loads(out.read_text(encoding="utf-8"))
    assert written["he"]["missing"] == [150]
    assert "he-1: 2 scenes" in capsys.readouterr().out
    assert script.main(["--from", str(tmp_path), "--strict"]) == 1


def test_the_index_path_reads_the_same_counts_as_the_readers() -> None:
    script = load()
    from array import array

    from targum.coverage import Index

    words = ("a", "b", "c")
    index = Index(
        words=words,
        texts={"scene-01-x": (0, 1), "scene-02-y": (0, 2), "not-a-scene": (0,)},
        counts={"scene-01-x": array("I", [3, 1]), "scene-02-y": array("I", [1, 1])},
    )
    found = script.from_index(index)
    assert list(found) == ["he-1"]
    scenes, missing = found["he-1"]
    assert dict(scenes) == {1: {"a": 3, "b": 1}, 2: {"a": 1, "c": 1}}
    assert missing == []
