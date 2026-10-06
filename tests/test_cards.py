"""A card in someone else's chat (design.md §12, 2026-10-06), as a host meets it.

The build card is a `ui://` resource a host that draws MCP Apps puts beside a
`check_job` result. What must stay true: a connection is offered the card only where it
holds the tool; the resource is handed over whole, with the extension's type; the page
fetches nothing and presses nothing; and a host that draws no card reads exactly the
text it read before.
"""

from __future__ import annotations

import json
import re
from types import SimpleNamespace
from typing import Any

import pytest

from targum import connector, mcp_http
from targum.chat import tools as tools_module
from targum.render.builder import ASSETS, build_card

BUILD = tools_module.BUILD_CARD
RECORD = "library record"


def ask(method: str, scopes: str = RECORD, **over: Any) -> dict[str, Any]:
    params = over.pop("params", None)
    message: dict[str, Any] = {"jsonrpc": "2.0", "id": 7, "method": method}
    if params is not None:
        message["params"] = params
    asked: dict[str, Any] = {"library": None, "store": None, "person": None, "scopes": scopes}
    asked.update(over)
    # Through the batch's own wrapper, so a refusal comes back as the error a host sees.
    answered = mcp_http._one(message, asked)
    assert answered is not None
    return answered


# --- what a host is told -----------------------------------------------------------


def test_the_server_says_it_has_resources_now() -> None:
    said = ask("initialize", params={"protocolVersion": "2025-06-18"})
    assert said["result"]["capabilities"]["resources"] == {"listChanged": False}


def test_the_card_is_listed_with_the_extension_s_type() -> None:
    listed = ask("resources/list")["result"]["resources"]
    assert [one["uri"] for one in listed] == [BUILD]
    card = listed[0]
    assert card["mimeType"] == "text/html;profile=mcp-app"
    assert card["name"] and card["title"] and card["description"]
    assert card["_meta"]["ui"]["csp"] == {"connectDomains": [], "resourceDomains": []}


def test_a_connection_without_check_job_is_offered_no_card() -> None:
    """The prompts' rule (`prompt_shapes`): nothing that sends a host to a tool it lacks."""
    assert "check_job" not in {tool.name for tool in connector.exposed("library")}
    assert ask("resources/list", scopes="library")["result"]["resources"] == []
    refused = ask("resources/read", scopes="library", params={"uri": BUILD})
    assert refused["error"]["code"] == mcp_http.RESOURCE_NOT_FOUND


def test_a_resource_nobody_made_is_not_found() -> None:
    refused = ask("resources/read", params={"uri": "ui://targum/somebody-else.html"})
    assert refused["error"]["code"] == mcp_http.RESOURCE_NOT_FOUND


def test_there_are_no_templates_and_saying_so_is_an_answer() -> None:
    assert ask("resources/templates/list")["result"] == {"resourceTemplates": []}


def test_the_card_is_read_whole() -> None:
    read = ask("resources/read", params={"uri": BUILD})["result"]["contents"]
    assert len(read) == 1
    one = read[0]
    assert one["uri"] == BUILD and one["mimeType"] == "text/html;profile=mcp-app"
    assert one["text"].lstrip().lower().startswith("<!doctype html>")
    assert one["_meta"]["ui"] == {
        "csp": {"connectDomains": [], "resourceDomains": []},
        "prefersBorder": False,
    }


def test_only_check_job_names_the_card_and_only_where_it_is_held() -> None:
    tools = ask("tools/list")["result"]["tools"]
    carded = {tool["name"]: tool["_meta"] for tool in tools if "_meta" in tool}
    assert set(carded) == {"check_job"}
    meta = carded["check_job"]
    assert meta["ui"]["resourceUri"] == BUILD
    assert meta["ui"]["visibility"] == ["model", "app"]
    # The flat key the extension's SDK still writes beside the new one.
    assert meta["ui/resourceUri"] == BUILD
    library = ask("tools/list", scopes="library")["result"]["tools"]
    assert not [tool for tool in library if "_meta" in tool]


def test_the_card_s_labels_follow_the_reader_s_language() -> None:
    store = SimpleNamespace(reads=lambda _person: {"ru"}, prompts=lambda _person: [])
    person = SimpleNamespace(id=1)
    page = ask("resources/read", params={"uri": BUILD}, store=store, person=person)
    text = page["result"]["contents"][0]["text"]
    assert '<html lang="ru">' in text and "Открыть" in text
    assert '<html lang="en">' in build_card() and ">Open<" in build_card()


# --- the floor ---------------------------------------------------------------------


def test_check_job_s_text_is_unchanged_and_the_card_reads_the_same_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """§12, "Text is still the floor". The rows go in `structuredContent`, which is
    exactly the text's own JSON: a host that reads that field to its model in place of
    the text (Claude Code does) reads what it always read."""
    state = {
        "id": "j1",
        "stage": "working",
        "done": 12,
        "total": 40,
        "unit": "sentences",
        "said": "12 of 40 sentences ready, about 3 minutes left.",
        "title": "שיר השירים",
    }
    text = json.dumps(state, ensure_ascii=False)
    monkeypatch.setattr(connector, "context", lambda *_a, **_k: None)
    monkeypatch.setattr(tools_module, "run", lambda *_a: (text, False))
    result = ask("tools/call", params={"name": "check_job", "arguments": {"id": "j1"}})["result"]
    assert result["content"] == [{"type": "text", "text": text}]
    assert result["isError"] is False
    assert result["structuredContent"] == state


def test_a_tool_with_no_card_has_no_structured_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(connector, "context", lambda *_a, **_k: None)
    monkeypatch.setattr(tools_module, "run", lambda *_a: ('{"results": []}', False))
    result = ask("tools/call", params={"name": "search_library", "arguments": {"q": "x"}})
    assert "structuredContent" not in result["result"]


def test_the_card_s_rows_carry_the_short_door(monkeypatch: pytest.MonkeyPatch) -> None:
    """The door the card draws is the link the text gives, shortened on the way out."""
    long = tools_module.reader_url("שיר", "https://targum.page")
    text = json.dumps({"id": "j1", "stage": "done", "open": long})
    monkeypatch.setattr(connector, "context", lambda *_a, **_k: None)
    monkeypatch.setattr(tools_module, "run", lambda *_a: (text, False))
    result = ask(
        "tools/call",
        params={"name": "check_job", "arguments": {"id": "j1"}},
        address="https://targum.page",
    )["result"]
    door = result["structuredContent"]["open"]
    assert door.startswith("https://targum.page/r/") and door in result["content"][0]["text"]


# --- the page: fetches nothing, presses nothing ------------------------------------


def _script() -> str:
    return (ASSETS / "card.js").read_text(encoding="utf-8")


def test_the_card_fetches_nothing() -> None:
    page = build_card()
    assert not re.search(r"https?://", page), "no address of anybody's in the card"
    assert not re.search(r"\b(?:src|srcset|action|poster)\s*=", page)
    # The door is the one href, and it has none until a tool result gives it one.
    assert re.findall(r"\bhref\s*=", page) == []
    for stray in ("url(", "@import", "<link", "<img", "<iframe", "fetch(", "XMLHttpRequest"):
        assert stray not in page, stray
    assert "WebSocket" not in page and "EventSource" not in page


def test_the_card_says_nothing_it_should_not() -> None:
    """§6: no emoji and no exclamation, in what the reader reads."""
    page = build_card()
    assert not re.findall(r"[\U0001F300-\U0001FAFF☀-➿️⬀-⯿]", page)
    visible = re.sub(r"<(script|style)>.*?</\1>", " ", page, flags=re.S)
    visible = re.sub(r"<[^>]+>", " ", visible)
    assert "!" not in visible
    assert "Targum" not in visible


def test_the_card_carries_both_readings_of_the_palette() -> None:
    page = build_card()
    assert ':root[data-theme="dark"]' in page
    assert '<meta name="color-scheme" content="light dark">' in page
    assert "prefers-reduced-motion: no-preference" in page


def test_the_card_asks_for_check_job_and_nothing_else() -> None:
    """§12: "A card never presses." The one tool its script may name is check_job; it
    never starts a build, confirms a quote or calls record_turn."""
    script = re.sub(r"^\s*//.*$", "", _script(), flags=re.M)
    named = set(re.findall(r"\bname:\s*[\"'](\w+)[\"'],\s*arguments", script))
    assert named == {"check_job"}, named
    called = re.findall(r"callTool\(\s*[\"'](\w+)[\"']", script)
    assert called and set(called) == {"check_job"}
    assert script.count('"tools/call"') == 1
    for tool in tools_module.REGISTRY:
        if tool.name != "check_job":
            assert tool.name not in script, f"the card names {tool.name}"
    # Nothing that posts a message into the conversation or writes the model's context.
    for door in ("ui/message", "ui/update-model-context", "sendFollowUpMessage"):
        assert door not in script, door


def test_the_card_holds_the_tool_s_own_wait() -> None:
    assert f"var WAIT = {int(tools_module.WAIT_MOST)};" in _script()
