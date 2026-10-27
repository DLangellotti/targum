"""A Hebrew beginner's one card on home is their next scene (design.md §12, 2026-10-27,
targum-internal#545).

The order is the scenes' own — 1 to 100, 101 to 240, then the B1 conversations, each a
series of its own — and it is followed until a measured level is past them.
"""

from __future__ import annotations

import re
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from targum import catalogue as catalogue_module
from targum import level as level_module
from targum.chat import tools

EMPTY = level_module.EMPTY


def rung(name: str) -> level_module.Rung:
    return next(one for one in level_module.ULPAN if one.name == name)


def entry(id_: str, language: str = "he") -> catalogue_module.Entry:
    return catalogue_module._entry(
        {
            "id": id_,
            "title": id_,
            "language": language,
            "source": f"dialogue:{id_}",
            "kind": "dialogue",
            "register": "modern",
            "words": 30,
        }
    )


SCENES = [
    entry(id_)
    for id_ in (
        "scene-he-01-b1-first",
        "scene-03-which-way",
        "scene-101-arnona",
        "scene-01-nice-to-meet-you",
        "scene-ru-01-privet",
        "scene-02-in-a-cafe",
        "esther",
    )
]


@pytest.fixture
def ctx(monkeypatch: pytest.MonkeyPatch) -> Any:
    """A context whose catalogue is the scenes above and whose shelf knows each text by
    the share `known` sets."""
    known: dict[str, float] = {}
    monkeypatch.setattr(catalogue_module, "everything", lambda: list(SCENES))
    monkeypatch.setattr(tools, "_collections", lambda: {})

    def shelf(ctx: Any, measured: bool = True) -> tuple[list[Any], list[Any]]:
        shared = [
            {"source": f"dialogue:{id_}", "reader": f"/reader/{id_}/", "known": share, "fresh": 0}
            for id_, share in known.items()
        ]
        return [], shared

    monkeypatch.setattr(tools, "_shelf", shelf)

    class Fake:
        level = replace(EMPTY, language="he")
        known_shares = known

    return Fake()


def test_a_beginner_is_aleph_or_nothing_said_until_measured_past_the_scenes() -> None:
    he = replace(EMPTY, language="he")
    assert tools.scene_reader(he), "nothing said, nothing measured: a fresh reader"
    assert tools.scene_reader(replace(he, declared="aleph"))
    assert not tools.scene_reader(replace(he, declared="gimel")), "a gimel reader"
    assert not tools.scene_reader(replace(he, declared="bet"))
    assert not tools.scene_reader(replace(he, here=rung("gimel"))), "a measured B1"
    assert tools.scene_reader(replace(he, here=rung("bet plus"), declared="gimel")), (
        "a measured rung outvotes the said one"
    )
    assert not tools.scene_reader(replace(EMPTY, language="ru"))


def test_a_fresh_reader_starts_at_scene_one_and_moves_on(ctx: Any) -> None:
    first = tools.next_scene(ctx)
    assert first is not None and first["id"] == "scene-01-nice-to-meet-you"
    assert first["scene"] == {"first": True}, "Start here"
    after = tools.next_scene(ctx, ["scene-01-nice-to-meet-you"])
    assert after is not None and after["id"] == "scene-02-in-a-cafe"
    assert after["scene"] == {"first": False}, "Your next scene"


def test_the_order_runs_on_past_a_hundred_then_to_the_conversations(ctx: Any) -> None:
    done = ["scene-01-nice-to-meet-you", "scene-02-in-a-cafe", "scene-03-which-way"]
    assert tools.next_scene(ctx, done)["id"] == "scene-101-arnona"  # type: ignore[index]
    done.append("scene-101-arnona")
    assert tools.next_scene(ctx, done)["id"] == "scene-he-01-b1-first"  # type: ignore[index]
    done.append("scene-he-01-b1-first")
    assert tools.next_scene(ctx, done) is None, "never Russian's scenes, never a non-scene"


def test_a_scene_known_well_enough_is_skipped(ctx: Any) -> None:
    ctx.known_shares["scene-02-in-a-cafe"] = 0.5
    ctx.known_shares["scene-03-which-way"] = 0.96
    done = ["scene-01-nice-to-meet-you", "scene-02-in-a-cafe"]
    assert tools.next_scene(ctx, done)["id"] == "scene-101-arnona"  # type: ignore[index]
    ctx.known_shares["scene-03-which-way"] = 0.94
    assert tools.next_scene(ctx, done)["id"] == "scene-03-which-way"  # type: ignore[index]


def test_suggest_hands_a_beginner_their_scene_and_anyone_else_the_ranking(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The route: a beginner's answer is the scene, with `scene` for home's line; a reader
    past them gets `suggest_next`'s pick, untouched."""
    served = Path(__file__).resolve().parent.parent / "src" / "targum" / "serve.py"
    text = served.read_text(encoding="utf-8")
    route = text[text.index("def _suggest(") : text.index("def _chat_suggest")]
    assert route.index("chat_tools.scene_reader(ctx.level)") < route.index("suggest_next(")
    assert "chat_tools.next_scene(ctx, done)" in route


ASSETS = Path(__file__).resolve().parent.parent / "src" / "targum" / "render" / "assets"
STRINGS = Path(__file__).resolve().parent.parent / "src" / "targum" / "strings"
TEMPLATES = Path(__file__).resolve().parent.parent / "src" / "targum" / "render" / "templates"


def test_no_reader_ever_sees_the_word_path() -> None:
    """David, 2026-10-27: the scenes are never called a "path" where a reader can see it —
    not in a string a page draws, not in a template's words, not in design.md's entry."""
    import json

    for catalogue in sorted(STRINGS.glob("*.json")):
        for key, said in json.loads(catalogue.read_text(encoding="utf-8")).items():
            assert not re.search(r"\bpaths?\b", str(said), re.I), (catalogue.name, key, said)
    for page in sorted(TEMPLATES.glob("*.j2")):
        words = re.sub(
            r"<(style|script)\b.*?</\1>|\{#.*?#\}|\{%.*?%\}|\{\{.*?\}\}|<[^>]+>",
            " ",
            page.read_text("utf-8"),
            flags=re.S,
        )
        assert not re.search(r"\bpaths?\b", words, re.I), page.name
    # The English a script falls back to is what a reader sees without a catalogue.
    for script in ("home.js", "library.js", "scenes.js"):
        text = (ASSETS / script).read_text(encoding="utf-8")
        for said in re.findall(r"\bt\(\s*\"[^\"]+\"\s*,\s*\"([^\"]*)\"", text):
            assert not re.search(r"\bpaths?\b", said, re.I), (script, said)
    design = (Path(__file__).resolve().parent.parent / "design.md").read_text(encoding="utf-8")
    start = design.index("### A Hebrew beginner's one card is their next scene")
    entry_text = design[start : design.index("\n### ", start + 1)]
    assert not re.search(r"\bpaths?\b", entry_text, re.I)
