"""`scripts/scene_corrections.py` writing through the corrections ledger
(targum-internal#585). Synthetic scenes and judgements only."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

from targum.accounts import Store

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


def load() -> Any:
    spec = importlib.util.spec_from_file_location(
        "scene_corrections", SCRIPTS / "scene_corrections.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_each_judgement_is_kept_once_with_its_kind_and_older_rows_are_classed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    script = load()
    scenes = tmp_path / "dialogues"
    scenes.mkdir()
    (scenes / "s-01.json").write_text(
        json.dumps(
            {"id": "s-01", "turns": [{"text": "אָבָג דָהו", "english": "placeholder"}]},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    decisions = tmp_path / "audit-01.json"
    decisions.write_text(
        json.dumps(
            [
                {"scene": "s-01", "turn": 0, "word": "אָבָג", "to": "אַבַג", "why": "points"},
                {"scene": "s-01", "turn": 0, "word": "דָהו", "to": "דָהוּז", "why": "letters"},
                {"scene": "s-01", "turn": None, "word": "cast", "to": "x"},
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    db = tmp_path / "targum.db"
    # One judgement kept before the ledger had its columns.
    Store(db).correct("scene", who="author", span="s-01 t0", before="אָבָג", after="אַבַג")
    argv = ["x", "--decisions", str(decisions), "--scenes", str(scenes), "--store", str(db)]
    for _ in range(2):
        monkeypatch.setattr(sys, "argv", [*argv, "--write"])
        script.main()
    rows = {row["before"]: row for row in Store(db).corrections("scene")}
    assert len(rows) == 2, "run twice, and over a row already kept: one row a judgement"
    assert rows["אָבָג"]["kind"] == "nikkud" and rows["אָבָג"]["run"] == "audit-01"
    assert rows["דָהו"]["kind"] == "wording" and rows["דָהו"]["reason"] == "letters"
    assert rows["דָהו"]["context"] == "אָבָג דָהו" and rows["דָהו"]["term"] == "דהו"
    assert "1 kept before the ledger" in capsys.readouterr().out
