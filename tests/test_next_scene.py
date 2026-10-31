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
import test_chat_serve
from test_serve import call

from targum import catalogue as catalogue_module
from targum import level as level_module
from targum.chat import tools

chatting = test_chat_serve.chatting
_record_by_spaces = test_chat_serve._record_by_spaces

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
    assert tools.scene_reader(replace(he, declared="bet")), "bet too (David, 2026-10-28)"
    assert not tools.scene_reader(replace(he, declared="bet-plus"))
    assert not tools.scene_reader(replace(he, declared="bet", here=rung("gimel"))), (
        "measured outvotes a said bet"
    )
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
    chatting: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Asked of the running server (qa on targum#958): a signed-out Hebrew visitor, who
    has said and measured nothing, is handed scene 1 with `scene` for home's line, then
    the next once it is finished; a reader past the scenes gets the ranking's pick."""
    port, key, _store, _chats = chatting
    status, got, _ = call(port, "GET", f"/suggest?language=he&k={key}")
    assert status == 200
    assert got["suggestion"]["id"] == "scene-01-nice-to-meet-you"
    assert got["suggestion"]["scene"] == {"first": True}
    got = call(port, "GET", f"/suggest?language=he&skip=scene-01-nice-to-meet-you&k={key}")[1]
    assert got["suggestion"]["id"] == "scene-02-in-a-cafe"
    assert got["suggestion"]["scene"] == {"first": False}

    monkeypatch.setattr(tools, "scene_reader", lambda level: False)
    picked = {"id": "esther", "title": "אסתר", "because": "Not measured yet."}
    monkeypatch.setattr(tools, "suggest_next", lambda ctx, args: {"suggestions": [picked]})
    got = call(port, "GET", f"/suggest?language=he&k={key}")[1]
    assert got["suggestion"]["id"] == "esther" and "scene" not in got["suggestion"]


def test_a_real_text_that_fits_a_beginner_comes_before_their_scene(
    chatting: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """David, 2026-10-31: the scenes are beginner supply until real easy content fills
    the gap, and a real text in the band wins (design.md §12, "What to read next is
    chosen on running words"). One under the floor does not: the scene is still the card.
    "Something else" on the scene is the ranking's pick, and never the scene again."""
    port, key, _store, _chats = chatting
    asked: list[dict[str, Any]] = []

    def suggest_next(ctx: Any, args: dict[str, Any]) -> dict[str, Any]:
        asked.append(dict(args))
        return {"suggestions": [dict(picked)]}

    monkeypatch.setattr(tools, "suggest_next", suggest_next)
    picked = {"id": "esther", "title": "אסתר", "fit": "band", "because": ""}
    got = call(port, "GET", f"/suggest?language=he&k={key}")[1]
    assert got["suggestion"]["id"] == "esther" and "scene" not in got["suggestion"]

    picked = {"id": "esther", "title": "אסתר", "fit": "under", "because": ""}
    got = call(port, "GET", f"/suggest?language=he&k={key}")[1]
    assert got["suggestion"]["id"] == "scene-01-nice-to-meet-you"

    picked = {"id": "scene-02-in-a-cafe", "title": "x", "fit": "band", "because": ""}
    got = call(port, "GET", f"/suggest?language=he&k={key}")[1]
    assert got["suggestion"]["id"] == "scene-01-nice-to-meet-you", "a scene in band is no real text"

    picked = {"id": "esther", "title": "אסתר", "fit": "under", "because": ""}
    status, got, _ = call(
        port,
        "POST",
        f"/suggest?k={key}",
        {"language": "he", "skip": [], "instead_of": "scene-01-nice-to-meet-you"},
    )
    assert status == 200 and got["suggestion"]["id"] == "esther"
    assert asked[-1]["instead_of"] == "scene-01-nice-to-meet-you"


def test_home_offers_something_else_with_no_reason_asked() -> None:
    """The card's second press asks for the next best with the text it set aside, and
    asks nothing of the reader (David, 2026-10-31: no reason picker)."""
    text = (ASSETS / "home.js").read_text(encoding="utf-8")
    assert 't("home.try.else", "Something else")' in text
    assert "instead_of: row.id" in text
    for asked in ("too hard", "too easy", "not for me"):
        assert asked not in text.lower()


def test_a_finished_scene_is_never_offered_however_much_is_finished(chatting: Any) -> None:
    """qa on targum#958: the ids were cut at 200, alphabetically, so a reader who had
    finished more than that lost the scenes off the end and was offered scene 1 again."""
    port, key, _store, _chats = chatting
    finished = [f"article-{n:04d}" for n in range(400)] + ["scene-01-nice-to-meet-you"]
    got = call(port, "GET", f"/suggest?language=he&skip={','.join(finished)}&k={key}")[1]
    assert got["suggestion"]["id"] == "scene-02-in-a-cafe"


def test_five_thousand_finished_ids_ride_in_the_body(chatting: Any) -> None:
    """qa on targum#958: in the address, about 2,000 finished ids passed the server's
    64 KB request line and home drew no card. Home posts them in the body now, and 5,000
    still find the next scene."""
    port, key, _store, _chats = chatting
    finished = [f"article-{n:05d}-a-long-catalogue-slug" for n in range(5000)]
    finished.append("scene-01-nice-to-meet-you")
    assert len(",".join(finished)) > 64 * 1024, "past what the address could carry"
    status, got, _ = call(port, "POST", f"/suggest?k={key}", {"language": "he", "skip": finished})
    assert status == 200
    assert got["suggestion"]["id"] == "scene-02-in-a-cafe"
    assert got["suggestion"]["scene"] == {"first": False}
    # Anything not a list of ids is no ids, not an error.
    status, got, _ = call(port, "POST", f"/suggest?k={key}", {"language": "he", "skip": "x"})
    assert status == 200 and got["suggestion"]["id"] == "scene-01-nice-to-meet-you"


def test_home_asks_with_a_body() -> None:
    """The page's own ask: a POST whose body carries the ids, never the address."""
    text = (ASSETS / "home.js").read_text(encoding="utf-8")
    assert 'askWith("/suggest", { language: code, skip: skip })' in text
    assert "/suggest?" not in text


def test_a_scene_collection_runs_by_number_and_takes_new_scenes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """David, 2026-10-28: Scenes run 1 to 240 as one collection, "also we'll add more
    soon". Its order is built from the numbers, so a scene the file never listed joins
    it, and nothing splits it at 100."""
    shelf = [entry(f"scene-{n:02d}-x{n}") for n in (2, 1, 101, 241, 100)] + [
        entry("scene-he-01-b1"),
        entry("scene-ru-01-r", language="ru"),
        entry("esther"),
    ]
    listed = catalogue_module._collection(
        {
            "id": "scenes",
            "title": "סצנות",
            "ordered": True,
            "members": ["scene-01-x1", "scene-02-x2"],
        }
    )
    other = catalogue_module._collection(
        {"id": "books", "title": "ספרים", "members": ["esther", "scene-01-x1"]}
    )
    monkeypatch.setattr(catalogue_module, "everything", lambda: list(shelf))
    monkeypatch.setattr(catalogue_module, "COLLECTIONS", [listed, other])
    found = {one.id: one.members for one in catalogue_module.collections()}
    assert found["scenes"] == (
        "scene-01-x1",
        "scene-02-x2",
        "scene-100-x100",
        "scene-101-x101",
        "scene-241-x241",
    )
    assert found["books"] == ("esther", "scene-01-x1"), "a mixed collection keeps its list"


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
            # And in Russian (qa on targum#958). "В пути", on the way, is a motion verb's
            # gloss on the grammar card and says nothing of the scenes.
            assert not re.search(r"\bпуть\b|маршрут", str(said), re.I), (catalogue.name, key)
    for page in sorted(TEMPLATES.glob("*.j2")):
        words = re.sub(
            r"<(style|script)\b.*?</\1>|\{#.*?#\}|\{%.*?%\}|\{\{.*?\}\}|<[^>]+>",
            " ",
            page.read_text("utf-8"),
            flags=re.S,
        )
        assert not re.search(r"\bpaths?\b|\bпуть\b|маршрут", words, re.I), page.name
    # The English a script falls back to is what a reader sees without a catalogue.
    for script in ("home.js", "library.js", "scenes.js"):
        text = (ASSETS / script).read_text(encoding="utf-8")
        for said in re.findall(r"\bt\(\s*\"[^\"]+\"\s*,\s*\"([^\"]*)\"", text):
            assert not re.search(r"\bpaths?\b", said, re.I), (script, said)
    design = (Path(__file__).resolve().parent.parent / "design.md").read_text(encoding="utf-8")
    start = design.index("### A Hebrew beginner's one card is their next scene")
    entry_text = design[start : design.index("\n### ", start + 1)]
    assert not re.search(r"\bpaths?\b|\bпуть\b|маршрут", entry_text, re.I)
