"""The script that drafts an English title for every catalogue text, with the model
stubbed: the three rules, what they refuse to overwrite, and what a title may not be."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
SCRIPT = HERE.parent / "scripts" / "english_titles.py"


def load_script() -> Any:
    spec = importlib.util.spec_from_file_location("english_titles", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def entry(**raw: Any) -> dict[str, Any]:
    base = {
        "id": "x",
        "title": "ט",
        "author": "",
        "language": "he",
        "source": "test:x",
        "blurb": "",
        "kind": "story",
        "tags": [],
        "english": "",
    }
    base.update(raw)
    return base


def test_a_scene_takes_its_english_from_its_slug_when_the_file_is_absent() -> None:
    script = load_script()
    scene = entry(id="scene-07-at-the-bank", kind="dialogue", source="dialogue:07-at-the-bank")
    assert script.from_scene(scene) == "At the bank"


def test_a_book_of_the_bible_is_named_in_its_byline() -> None:
    script = load_script()
    assert script.from_byline(entry(author="Ketuvim · Ruth", tags=["tanakh"])) == "Ruth"
    assert script.from_byline(entry(author="Torah · Genesis")) == "Genesis"


def test_the_rest_go_to_the_model_in_batches_and_come_back_tidy() -> None:
    script = load_script()
    asked: list[str] = []

    def ask(prompt: str) -> str:
        asked.append(prompt)
        given = json.loads(prompt.split("\n\n", 1)[1])
        return json.dumps(
            [{"id": row["id"], "english": f'"The Story of {row["id"]}!"'} for row in given]
        )

    entries = [entry(id=f"story-{n}") for n in range(35)]
    drafted = script.draft(entries, ask)
    assert len(asked) == 2, "thirty at a time"
    assert drafted["story-0"] == "The Story of story-0", "quotation marks and the exclamation gone"
    assert len(drafted) == 35


def test_a_title_already_written_is_never_overwritten() -> None:
    script = load_script()
    entries = [
        entry(id="ruth", author="Ketuvim · Ruth", tags=["tanakh"], english="Ruth, my way"),
        entry(
            id="scene-01-nice-to-meet-you", kind="dialogue", source="dialogue:01-nice-to-meet-you"
        ),
        entry(id="story-a"),
    ]
    planned = script.plan(
        entries, lambda prompt: json.dumps([{"id": "story-a", "english": "A Story"}])
    )
    assert [row[0] for row in planned] == ["scene-01-nice-to-meet-you", "story-a"]
    assert dict((r[0], r[2]) for r in planned) == {
        "scene-01-nice-to-meet-you": "Nice to meet you",
        "story-a": "A Story",
    }
    assert [r[1] for r in planned] == ["scene", "model"]


def test_tidy_keeps_a_title_within_what_the_brand_allows() -> None:
    script = load_script()
    assert script.tidy(" “Old New Land.” ") == "Old New Land"
    assert script.tidy("Wow! What a day!") == "Wow What a day"
    # A question keeps its mark; nothing else ends with one.
    assert script.tidy("How was the weekend?") == "How was the weekend?"
    assert script.tidy("What time is it?!") == "What time is it?"
    # Never cut short: a title chopped at six words is worse than a long one.
    assert script.tidy("one two three four five six seven") == "one two three four five six seven"


def test_a_long_title_is_asked_for_again_shorter_rather_than_cut() -> None:
    script = load_script()
    asks: list[str] = []

    def ask(prompt: str) -> str:
        asks.append(prompt)
        given = json.loads(prompt.split("\n\n", 1)[1])
        if prompt.startswith(script.SHORTEN):
            return json.dumps([{"id": r["id"], "english": "The Long Walk"} for r in given])
        return json.dumps(
            [
                {
                    "id": r["id"],
                    "english": "The Woman Who Walked Thousands of Miles For Her Brother",
                }
                for r in given
            ]
        )

    drafted = script.draft([entry(id="gv-baloch-march")], ask)
    assert len(asks) == 2, "one draft, one shortening"
    assert drafted["gv-baloch-march"] == "The Long Walk"
