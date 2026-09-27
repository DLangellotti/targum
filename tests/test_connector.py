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


# --- who is asking, and what they may see (targum-internal#80) --------------------


def test_stdio_keeps_the_posture_it_shipped_with() -> None:
    """No token means the whole registry, and it is not the same thing as no scopes."""
    names = {tool.name for tool in connector.exposed()}
    assert "search_library" in names and "my_vocabulary" in names
    assert not [tool for tool in connector.exposed() if tool.spends]


def test_no_scope_is_not_every_scope() -> None:
    """An empty scope string is a token that was granted nothing, and gets the library."""
    names = {tool.name for tool in connector.exposed("")}
    assert "search_library" in names, "the library's scope is the unsaid default"
    assert "my_vocabulary" not in names
    assert "quote_build" not in names


def test_a_scope_decides_what_is_listed() -> None:
    library_only = {tool.name for tool in connector.exposed("library")}
    with_record = {tool.name for tool in connector.exposed("library record")}
    with_check = {tool.name for tool in connector.exposed("library record check")}
    assert library_only < with_record < with_check, "each one only ever adds"
    assert "my_progress" in with_record - library_only
    assert "quote_build" in with_check - with_record


def test_nothing_that_spends_is_offered_without_the_scope_that_consented() -> None:
    """design.md §12, "A scope is a press that lasts": one scope may say otherwise, and
    it is the only thing that may. Before 2026-09-22 this read "nothing that spends"."""
    from targum import oauth

    for scopes in ("", "library", "library record"):
        assert not [tool for tool in connector.exposed(scopes) if tool.spends]
    allowed = connector.exposed(f"library record {oauth.SPENDING_SCOPE}")
    assert all(tool.scope == oauth.SPENDING_SCOPE for tool in allowed if tool.spends)


def test_the_conversation_tool_is_never_offered_however_much_is_granted() -> None:
    from targum import oauth

    every = " ".join(name for name, _ in oauth.SCOPES)
    assert "quote_conversation" not in {tool.name for tool in connector.exposed(every)}


def test_a_context_built_for_a_person_is_that_person_s(tmp_path: Path) -> None:
    store = Store(tmp_path / "db")
    person, _ = store.finish_sign_in(store.start_sign_in("reader@example.com"))  # type: ignore[misc]
    library = Library(tmp_path / "out", store=store)
    ctx = connector.context(library, store, person)
    assert ctx.person is not None and ctx.person.id == person.id
    assert ctx.home == library.home(person), "their own home, never the shared one"
    assert ctx.admin is False, "read from the store, and this address is not one"


def test_a_context_built_for_nobody_is_the_machine_s_own_reader(tmp_path: Path) -> None:
    library = Library(tmp_path / "out", store=None)
    ctx = connector.context(library, None)
    assert ctx.person is None
    assert ctx.home == library.home(None)
    assert ctx.admin is False
