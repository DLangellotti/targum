"""`voice_shelf.py`, the whole-shelf runner (targum-internal#566), with nothing called:
the director and the voicer are fakes, and so is the clock."""

from __future__ import annotations

import argparse
import email.message
import importlib.util
import io
import json
import sys
import urllib.error
from pathlib import Path
from typing import Any

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


def load(name: str) -> Any:
    sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


shelf = load("voice_shelf")
vs = shelf.vs

VERTEX_429 = {
    "error": {
        "code": 429,
        "message": "Quota exceeded for aiplatform.googleapis.com/generate_content_requests",
        "status": "RESOURCE_EXHAUSTED",
        "details": [
            {
                "@type": "type.googleapis.com/google.rpc.QuotaFailure",
                "violations": [
                    {
                        "quotaMetric": "aiplatform.googleapis.com/generate_content_requests",
                        "quotaId": "GenerateContentRequestsPerMinutePerProjectPerModel",
                        "quotaDimensions": {"model": "gemini-3.1-flash-tts"},
                        "quotaValue": "60",
                    }
                ],
            },
            {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "17s"},
        ],
    }
}


def scene(
    sid: str, lang: str = "he", voices: tuple[str, str] = ("Leda", "Charon")
) -> dict[str, Any]:
    text = ("Привет, как дела?", "Хорошо.") if lang == "ru" else ("שָׁלוֹם", "שָׁלוֹם")
    return {
        "id": sid,
        "language": lang,
        "english": "Hello",
        "gloss": "",
        "cast": {
            "A": {"voice": voices[0], "gender": "f", "name": "A"},
            "B": {"voice": voices[1], "gender": "m", "name": "B"},
        },
        "turns": [
            {"who": "A", "text": text[0], "english": "", "start": 0.0, "end": 2.0},
            {"who": "B", "text": text[1], "english": "", "start": 2.5, "end": 4.0},
        ],
    }


def options(**over: Any) -> argparse.Namespace:
    base = dict(cap=30.0, spacing=0, via="vertex", deadline=5, pause=7.0, wait_daily=26.0)
    return argparse.Namespace(**{**base, **over})


class Voicer:
    """Buys `each` seconds per turn, after `refusals` (exceptions) are raised in order."""

    def __init__(self, each: float = 60.0, refusals: list[Exception] | None = None) -> None:
        self.each = each
        self.refusals = list(refusals or [])
        self.voiced: list[str] = []

    def __call__(self, scene: dict[str, Any], key: str, into: Path, *rest: Any) -> Any:
        on_bought = rest[-1]
        if self.refusals:
            raise self.refusals.pop(0)
        for _ in scene["turns"]:
            on_bought(self.each)
        (into / f"{scene['id']}.mp3").write_bytes(b"mp3 " + scene["id"].encode())
        self.voiced.append(scene["id"])
        return [[0.0, 1.0], [1.7, 2.0]], 2.0, self.each * len(scene["turns"])


def directed(scene: dict[str, Any], key: str, store: Path) -> tuple[list[str], float]:
    return ["calm"] * len(scene["turns"]), 0.0


def go(
    tmp_path: Path, scenes: list[dict[str, Any]], voicer: Voicer, **over: Any
) -> tuple[Any, list[float]]:
    slept: list[float] = []
    progress = shelf.Progress(tmp_path / "progress.json", over.get("cap", 30.0))
    shelf.run(
        scenes,
        tmp_path,
        progress,
        "tts",
        "director",
        options(**over),
        sleep=slept.append,
        direct=directed,
        voice=voicer,
    )
    return json.loads((tmp_path / "progress.json").read_text()), slept


def test_every_scene_is_voiced_and_written_down(tmp_path: Path) -> None:
    said, _ = go(tmp_path, [scene("he-01"), scene("ru-01", "ru", ("Kore", "Orus"))], Voicer(1))
    assert said["stopped"] == "finished"
    assert {k: v["state"] for k, v in said["scenes"].items()} == {
        "he-01": "done",
        "ru-01": "done",
    }
    assert (tmp_path / "he-01.seams.json").exists() and (tmp_path / "ru-01.spans.json").exists()
    # Two turns of a second each, twice, at $0.03 a minute.
    assert said["spent_this_run"] == pytest.approx(4 / 60 * vs.PER_MINUTE)


def test_a_finished_scene_is_not_voiced_again_unless_its_words_changed(tmp_path: Path) -> None:
    go(tmp_path, [scene("he-01"), scene("he-02")], Voicer(1))
    changed = scene("he-02")
    changed["turns"][1]["text"] = "לְהִתְרָאוֹת"
    again = Voicer(1)
    go(tmp_path, [scene("he-01"), changed], again)
    assert again.voiced == ["he-02"]


def test_the_cap_stops_the_run_at_the_turn_that_reaches_it(tmp_path: Path) -> None:
    # Each turn is a minute, $0.03; a cap of $0.10 is reached on the fourth turn, the
    # second scene's second. That turn is bought and kept; nothing after it is asked for.
    voicer = Voicer(60)
    said, _ = go(tmp_path, [scene(f"he-0{n}") for n in range(1, 5)], voicer, cap=0.10)
    assert said["stopped"].startswith("cap")
    assert said["spent_this_run"] == pytest.approx(0.12)
    assert voicer.voiced == ["he-01"]
    states = {k: v["state"] for k, v in said["scenes"].items()}
    assert states == {"he-01": "done", "he-02": "partial"}


def test_a_per_day_limit_is_slept_off_and_the_scene_resumed(tmp_path: Path) -> None:
    quota = vs.read_quota(
        json.dumps({"error": {"message": "per day", "details": [{"retryDelay": "3600s"}]}}).encode()
    )
    said, slept = go(tmp_path, [scene("he-01")], Voicer(1, [vs.Daily("per day", quota)]))
    assert slept == [3600.0]
    assert said["scenes"]["he-01"]["state"] == "done" and said["waiting_until"] is None


def test_a_per_day_limit_longer_than_allowed_stops_the_run(tmp_path: Path) -> None:
    quota = vs.Quota(message="per day", retry_after=40 * 3600)
    said, slept = go(tmp_path, [scene("he-01")], Voicer(1, [vs.Daily("per day", quota)]))
    assert slept == [] and said["stopped"].startswith("per-day quota")


def test_a_limit_that_outlasts_the_backoff_pauses_then_resumes(tmp_path: Path) -> None:
    quota = vs.read_quota(json.dumps(VERTEX_429).encode())
    voicer = Voicer(1, [vs.Throttled("still", quota), vs.Throttled("still", quota)])
    said, slept = go(tmp_path, [scene("he-01")], voicer, pause=7.0)
    assert slept == [7.0, 7.0] and said["scenes"]["he-01"]["state"] == "done"


def test_vertex_states_its_quota_and_it_is_read() -> None:
    quota = vs.read_quota(json.dumps(VERTEX_429).encode())
    assert quota.retry_after == 17.0
    assert quota.limits[0]["quotaValue"] == "60"
    assert "GenerateContentRequestsPerMinutePerProjectPerModel = 60" in str(quota)
    assert vs.read_quota(b"not json").limits == []


def test_say_waits_what_the_429_asks_and_reports_it(monkeypatch: pytest.MonkeyPatch) -> None:
    answers: list[Any] = [
        urllib.error.HTTPError(
            "u",
            429,
            "Too Many",
            email.message.Message(),
            io.BytesIO(json.dumps(VERTEX_429).encode()),
        ),
        json.dumps(
            {"candidates": [{"content": {"parts": [{"inlineData": {"data": "AAA="}}]}}]}
        ).encode(),
    ]

    def fetch(request: Any, deadline: float) -> bytes:
        one = answers.pop(0)
        if isinstance(one, Exception):
            raise one
        return bytes(one)

    waited: list[float] = []
    seen: list[Any] = []
    monkeypatch.setattr(vs, "fetch", fetch)
    monkeypatch.setattr(vs.time, "sleep", waited.append)
    vs.say("שלום", "Leda", "k", "Read.", "vertex", on_quota=seen.append)
    assert waited == [17.0] and seen[0].limits[0]["quotaValue"] == "60"


def test_russian_gets_its_own_voices_brief_and_no_hebrew_hints() -> None:
    wrong = scene("ru-02", "ru", ("", "Leda"))
    fixed, notes = shelf.cast_for(wrong)
    assert fixed["cast"]["A"]["voice"] == "Kore" and fixed["cast"]["B"]["voice"] == "Orus"
    assert len(notes) == 2 and "Leda is f" in notes[1]
    assert wrong["cast"]["A"]["voice"] == "", "the scene itself is not changed"
    assert "in Russian" in vs.brief(fixed)
    assert " Read " not in vs.prompt_for(fixed, 0, "calm")
    kept, none = shelf.cast_for(scene("he-03"))
    assert none == [] and kept["cast"]["A"]["voice"] == "Leda"


def test_a_dry_run_counts_and_prices_and_writes_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "shelf"
    source.mkdir()
    for one in (scene("he-01"), scene("ru-01", "ru", ("Kore", "Orus"))):
        (source / f"{one['id']}.json").write_text(json.dumps(one, ensure_ascii=False))
    into = tmp_path / "out"
    progress = shelf.Progress.__new__(shelf.Progress)
    progress.path, progress.data = into / "progress.json", {"scenes": {}}
    shelf.dry_run(shelf.load(source, [], []), into, progress, 3.0, 30.0)
    out = capsys.readouterr().out
    assert "2 scenes: 1 he, 1 ru" in out and "4 turns, so 4 TTS requests" in out
    assert "estimated $" in out and not into.exists()
