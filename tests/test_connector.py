"""The chat's registry, served over MCP: the same tools, none that spend."""

from __future__ import annotations

import asyncio
import inspect
import json
from pathlib import Path

import pytest

from targum import connector
from targum.accounts import Store
from targum.chat import tools
from targum.serve import Library


def test_only_what_spends_nothing_and_needs_no_page_is_exposed() -> None:
    names = {tool.name for tool in connector.exposed()}
    assert "quote_conversation" not in names, "needs a conversation on the page"
    assert "quote_build" in names, "a quote is information"
    assert names <= {tool.name for tool in tools.REGISTRY}
    assert not [tool for tool in connector.exposed() if tool.spends or tool.needs_consent]


def test_a_tool_s_signature_says_what_its_schema_says(tmp_path: Path) -> None:
    library = Library(tmp_path / "out", store=None)
    ctx = connector.context(library, None)
    search = next(tool for tool in tools.REGISTRY if tool.name == "search_library")
    fn = connector.callable_for(search, ctx)
    signature = inspect.signature(fn)
    assert set(signature.parameters) == set(search.schema["properties"])
    assert signature.parameters["limit"].annotation == (int | None)
    assert signature.parameters["query"].default is None, "optional, as the schema says"
    opened = next(tool for tool in tools.REGISTRY if tool.name == "open_library_text")
    required = inspect.signature(connector.callable_for(opened, ctx)).parameters["id"]
    assert required.default is inspect.Parameter.empty and required.annotation is str
    assert fn.__name__ == "search_library" and fn.__doc__ == search.description


def test_the_server_lists_the_tools_and_answers_one(tmp_path: Path) -> None:
    pytest.importorskip("mcp")
    store = Store(tmp_path / "db")
    out = tmp_path / "out"
    out.mkdir()
    library = Library(out, store=store)
    server = connector.build(library, store)
    listed = asyncio.run(server.list_tools())
    by_name = {tool.name: tool for tool in listed}
    assert set(by_name) == {tool.name for tool in connector.exposed()}
    schema = by_name["search_library"].model_dump(by_alias=True)["inputSchema"]
    assert "register" in schema["properties"] and "query" in schema["properties"]

    answered = asyncio.run(server.call_tool("my_progress", {}))
    text = answered.content[0].text  # type: ignore[union-attr]
    assert json.loads(text)["ladder"]["note"] == "A guide, not a placement."

    found = asyncio.run(server.call_tool("search_library", {"register": "biblical", "limit": 3}))
    got = json.loads(found.content[0].text)  # type: ignore[union-attr]
    assert got["count"] >= 1 and all(row["register"] == "biblical" for row in got["texts"])


def test_without_the_sdk_the_connector_says_how_to_get_it(monkeypatch, tmp_path: Path) -> None:
    import builtins

    real = builtins.__import__

    def missing(name, *args, **kwargs):  # type: ignore[no-untyped-def]
        if name.startswith("mcp"):
            raise ImportError("no mcp")
        return real(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", missing)
    from targum.errors import TargumError

    with pytest.raises(TargumError, match="mcp package") as refused:
        connector.build(Library(tmp_path / "out", store=None), None)
    assert "uv sync --extra mcp" in (refused.value.hint or "")


def test_the_command_can_say_what_it_offers() -> None:
    said = connector.describe()
    assert said.startswith("search_library:") and "quote_conversation" not in said
