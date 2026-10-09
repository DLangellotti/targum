"""A card in someone else's chat (design.md §12, 2026-10-06), as a host meets it.

The build card is a `ui://` resource a host that draws MCP Apps puts beside a
`check_job` result, and the text card one it puts beside `find_text` or
`open_library_text`. What must stay true: a connection is offered a card only where it
holds the tool; the resource is handed over whole, with the extension's type; the page
fetches nothing and presses nothing (the text card's one fetch is a recording, from our
own origin, through a short-lived address for that one file); and a host that draws no
card reads exactly the text it read before.
"""

from __future__ import annotations

import json
import re
from types import SimpleNamespace
from typing import Any

import pytest

from targum import connector, heard, mcp_http
from targum.chat import tools as tools_module
from targum.render.builder import ASSETS, build_card, build_text_card

BUILD = tools_module.BUILD_CARD
TEXT = tools_module.TEXT_CARD
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
    assert [one["uri"] for one in listed] == [BUILD, TEXT]
    for card in listed:
        assert card["mimeType"] == "text/html;profile=mcp-app"
        assert card["name"] and card["title"] and card["description"]
    assert listed[0]["_meta"]["ui"]["csp"] == {"connectDomains": [], "resourceDomains": []}


def test_a_connection_without_check_job_is_offered_no_build_card() -> None:
    """The prompts' rule (`prompt_shapes`): nothing that sends a host to a tool it lacks.
    The library scope holds find_text, so it is offered the text card and that alone."""
    assert "check_job" not in {tool.name for tool in connector.exposed("library")}
    listed = ask("resources/list", scopes="library")["result"]["resources"]
    assert [one["uri"] for one in listed] == [TEXT]
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


def test_only_check_job_names_the_card_and_only_where_it_is_held(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _following(monkeypatch)
    tools = ask("tools/list")["result"]["tools"]
    carded = {tool["name"]: tool["_meta"] for tool in tools if "_meta" in tool}
    assert set(carded) == {"check_job", "find_text", "open_library_text", "search_sources"}
    meta = carded["check_job"]
    assert meta["ui"]["resourceUri"] == BUILD
    assert meta["ui"]["visibility"] == ["model", "app"]
    # The flat key the extension's SDK still writes beside the new one.
    assert meta["ui/resourceUri"] == BUILD
    for name in ("find_text", "open_library_text", "search_sources"):
        assert carded[name]["ui"]["resourceUri"] == TEXT
        assert carded[name]["ui/resourceUri"] == TEXT
    library = ask("tools/list", scopes="library")["result"]["tools"]
    assert {tool["name"] for tool in library if "_meta" in tool} == {
        "find_text",
        "open_library_text",
        "search_sources",
    }


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


def test_the_bridge_names_no_tool_and_asks_for_none() -> None:
    """`card-bridge.js` is shared by both cards, so a tool named there would be a tool
    every card could ask for. Each card names its own, in its own file."""
    bridge = re.sub(
        r"^\s*//.*$", "", (ASSETS / "card-bridge.js").read_text(encoding="utf-8"), flags=re.M
    )
    assert '"tools/call"' not in bridge and "callTool" not in bridge
    for tool in tools_module.REGISTRY:
        assert tool.name not in bridge, f"the bridge names {tool.name}"
    for door in ("ui/message", "ui/update-model-context", "sendFollowUpMessage"):
        assert door not in bridge, door
    # And both cards speak it, rather than a copy of it each.
    for card in ("card.js", "card-text.js"):
        assert "ui/initialize" not in (ASSETS / card).read_text(encoding="utf-8"), card
    for page in (build_card(), build_text_card()):
        assert page.count("ui/initialize") == 1 and "var TargumCard" in page


# --- the text card -----------------------------------------------------------------

ADDRESS = "https://targum.page"


def test_the_text_card_asks_for_our_origin_for_media_and_nothing_more() -> None:
    """§12's second exception: the one fetch is a recording from targum.page, so the one
    domain named is ours, in `resourceDomains` (the extension's field that reaches
    `media-src`), and nothing in `connectDomains`."""
    listed = ask("resources/list", address=ADDRESS)["result"]["resources"]
    frames = {one["uri"]: one["_meta"]["ui"] for one in listed}
    assert frames[TEXT]["csp"] == {"connectDomains": [], "resourceDomains": [ADDRESS]}
    assert frames[BUILD]["csp"] == {"connectDomains": [], "resourceDomains": []}
    read = ask("resources/read", params={"uri": TEXT}, address=ADDRESS + "/")["result"]
    one = read["contents"][0]
    assert one["mimeType"] == "text/html;profile=mcp-app"
    assert one["_meta"]["ui"]["csp"]["resourceDomains"] == [ADDRESS]
    assert one["text"] == build_text_card()


def test_the_text_card_is_refused_where_find_text_is_not_held(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _following(monkeypatch)
    exposed = connector.exposed

    def without(*args: Any, **kwargs: Any) -> list[tools_module.Tool]:
        return [
            tool
            for tool in exposed(*args, **kwargs)
            if tool.name not in ("find_text", "open_library_text", "search_sources")
        ]

    monkeypatch.setattr(connector, "exposed", without)
    assert TEXT not in [one["uri"] for one in ask("resources/list")["result"]["resources"]]
    refused = ask("resources/read", params={"uri": TEXT})
    assert refused["error"]["code"] == mcp_http.RESOURCE_NOT_FOUND


def _text_script() -> str:
    return (ASSETS / "card-text.js").read_text(encoding="utf-8")


def test_the_text_card_fetches_nothing_but_a_recording() -> None:
    """No address of anybody's in the page, ours included: the recording's and the cover's
    come in with the result. Two elements may load, the `<audio>` and a cover's `<img>`
    (design.md §12, "A card's picture comes from targum.page", 2026-10-09), and only by
    the script's own hand."""
    page = build_text_card()
    assert not re.search(r"https?://", page), "no address of anybody's in the card"
    without_script = re.sub(r"<script>.*?</script>", " ", page, flags=re.S)
    assert not re.search(r"\b(?:src|srcset|action|poster|href)\s*=", without_script)
    for stray in ("url(", "@import", "<link", "<img", "<iframe", "<video", "<source"):
        assert stray not in page, stray
    for stray in ("fetch(", "XMLHttpRequest", "WebSocket", "EventSource", "sendBeacon"):
        assert stray not in page, stray
    script = re.sub(r"^\s*//.*$", "", _text_script(), flags=re.M)
    # The two things it ever loads: the recording, into the one <audio>, and a cover.
    assert sorted(re.findall(r"(\w+)\.src\s*=", script)) == ["ear", "picture"]
    assert set(re.findall(r'createElement\("(\w+)"\)', script)) == {"img", "span"}
    assert "innerHTML" not in script
    assert page.count("<audio") == 1 and '<audio id="ear" preload="none">' in page


def test_the_text_card_calls_no_tool() -> None:
    """§12: "A card never presses." The text card's rows are the result; it asks the
    host for nothing but to open a page of ours."""
    script = re.sub(r"^\s*//.*$", "", _text_script(), flags=re.M)
    assert "tools/call" not in script and "callTool" not in script
    assert ".request(" not in script
    for tool in tools_module.REGISTRY:
        assert tool.name not in script, f"the card names {tool.name}"
    for door in ("ui/message", "ui/update-model-context", "sendFollowUpMessage"):
        assert door not in script, door


def test_the_text_card_says_nothing_it_should_not() -> None:
    for language in ("en", "ru"):
        page = build_text_card(language)
        assert not re.findall(r"[\U0001F300-\U0001FAFF☀-➿️⬀-⯿]", page)
        visible = re.sub(r"<(script|style)>.*?</\1>", " ", page, flags=re.S)
        visible = re.sub(r"<[^>]+>", " ", visible)
        assert "!" not in visible
        assert "Targum" not in visible
    # The known share is said the way the app says it, every tenth of it.
    page = build_text_card()
    from targum.level import words_in_ten

    for tenths in range(11):
        said = words_in_ten(tenths / 10).replace("'", "&#39;")
        assert said in page, said


def test_the_text_card_carries_both_readings_of_the_palette() -> None:
    page = build_text_card()
    assert ':root[data-theme="dark"]' in page
    assert '<meta name="color-scheme" content="light dark">' in page
    assert "prefers-reduced-motion: no-preference" in page


def test_the_text_card_s_labels_follow_the_reader_s_language() -> None:
    page = build_text_card("ru")
    assert '<html lang="ru">' in page and "Открыть" in page and "Слушать" in page
    assert "примерно 5 слов из 10" in page


@pytest.fixture
def shelves(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    """A home and a shared shelf, a recording folder and a dialogue folder, all empty,
    and a context that names them."""
    home, shared = tmp_path / "home", tmp_path / "shared"
    recordings, dialogues = tmp_path / "recordings", tmp_path / "dialogues"
    for one in (home, shared, recordings, dialogues):
        one.mkdir()
    monkeypatch.setenv("TARGUM_RECORDING_DIR", str(recordings))
    monkeypatch.setenv("TARGUM_DIALOGUE_DIR", str(dialogues))
    tools_module.KEPT.clear()
    heard.HEARD.clear()
    ctx = SimpleNamespace(home=home, library=SimpleNamespace(shared=shared))
    return SimpleNamespace(
        home=home, shared=shared, recordings=recordings, dialogues=dialogues, ctx=ctx
    )


def _imported(folder: Any, audio: str = "audio/part-001.mp3") -> None:
    from targum.audio import manifest as manifest_module

    folder.mkdir(parents=True, exist_ok=True)
    (folder / audio).parent.mkdir(parents=True, exist_ok=True)
    (folder / audio).write_bytes(b"ID3 a recording")
    manifest_module.write(
        folder,
        manifest_module.AudioManifest(
            source="talk.mp3",
            sha256="0" * 64,
            duration=60.0,
            language="he",
            parts=[manifest_module.ManifestPart(number=1, start=0.0, end=60.0, audio=audio)],
        ),
    )


def _attached(shelves: SimpleNamespace, folder: Any, source: str) -> None:
    """A built text whose source has a recording attached, as Be'eri's Tanakh does."""
    from targum.recording import index as recording_index

    folder.mkdir(parents=True, exist_ok=True)
    (folder / "document.json").write_text(json.dumps({"source": source}), encoding="utf-8")
    (folder / "segments.json").write_text(
        json.dumps({"segments": [{"ref": "Ruth 2:1"}]}), encoding="utf-8"
    )
    home = recording_index.folder(source)
    home.mkdir(parents=True)
    (home / "part-001.mp3").write_bytes(b"ID3 one")
    (home / "part-002.mp3").write_bytes(b"ID3 two")
    (home / "recording.json").write_text(
        json.dumps(
            {
                "source": source,
                "credit": "Shmuel Be'eri",
                "licence": "CC BY-SA 4.0",
                "parts": [
                    {"ref": "Ruth 1", "audio": "part-001.mp3", "spans": {"Ruth 1:1": [0, 1]}},
                    {"ref": "Ruth 2", "audio": "part-002.mp3", "spans": {"Ruth 2:1": [0, 1]}},
                ],
            }
        ),
        encoding="utf-8",
    )


def test_a_text_with_a_recording_is_given_one_address_for_that_one_file(
    shelves: SimpleNamespace,
) -> None:
    _imported(shelves.home / "שיחה")
    found = heard.recording_of(shelves.home / "שיחה")
    assert found is not None and found.path == shelves.home / "שיחה" / "audio" / "part-001.mp3"
    answer = {
        "count": 2,
        "texts": [
            {"from": "mine", "name": "שיחה", "title": "שיחה", "reader": "x"},
            {"from": "library", "id": "ruth", "title": "רות", "reader": "", "on_shelf": False},
        ],
    }
    answer["texts"][0]["reader"] = tools_module.reader_url("שיחה", ADDRESS)
    meta = mcp_http.text_card_meta(json.dumps(answer), shelves.ctx, ADDRESS)
    assert len(meta) == 2
    first, second = meta
    assert first["door"].startswith(ADDRESS + "/r/")
    src = first["audio"]["src"]
    assert src.startswith(ADDRESS + heard.ROUTE + "?t=")
    assert "שיחה" not in src and "part-001" not in src, "the address names no file"
    token = src.split("?t=", 1)[1]
    assert heard.HEARD.opened(token) == found.path.resolve()
    ends = first["audio"]["ends"] / 1000
    assert heard.LIFETIME_S - 5 < ends - __import__("time").time() <= heard.LIFETIME_S
    # A library text not on the shelf: its door is our library page, and no recording.
    assert second == {"door": ADDRESS + "/library/ruth", "cover": ADDRESS + "/cover/ruth"}


def test_a_text_without_a_recording_has_no_button(shelves: SimpleNamespace) -> None:
    folder = shelves.home / "מאמר"
    folder.mkdir()
    (folder / "document.json").write_text(json.dumps({"source": "https://x"}), encoding="utf-8")
    assert heard.recording_of(folder) is None
    answer = {"texts": [{"name": "מאמר", "title": "מאמר", "reader": "r"}]}
    meta = mcp_http.text_card_meta(json.dumps(answer), shelves.ctx, ADDRESS)
    assert "audio" not in meta[0]


def test_an_attached_recording_plays_the_part_that_holds_the_text(
    shelves: SimpleNamespace,
) -> None:
    """Be'eri, PocketTorah, LibriVox: a recording kept apart from the text, found by the
    text's source and its first verse, and credited."""
    _attached(shelves, shelves.shared / "רות-ב", "sefaria:Ruth")
    found = heard.recording_of(shelves.shared / "רות-ב")
    assert found is not None
    assert found.path.name == "part-002.mp3" and found.credit == "Shmuel Be'eri"
    reader = tools_module.reader_url("רות-ב", ADDRESS)
    answer = {"title": "רות", "id": "ruth", "reader": reader, "on_shelf": True}
    meta = mcp_http.text_card_meta(json.dumps(answer), shelves.ctx, ADDRESS)
    assert meta[0]["audio"]["credit"] == "Shmuel Be'eri"
    assert heard.HEARD.opened(meta[0]["audio"]["src"].split("?t=")[1]) == found.path.resolve()


def test_a_scene_plays_its_own_voicing(
    shelves: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    from targum.dialogue import index as dialogue_index

    (shelves.dialogues / "01-hello.mp3").write_bytes(b"ID3 scene")
    scene = SimpleNamespace(audio="01-hello.mp3", turns=[SimpleNamespace(voiced=True)])
    monkeypatch.setattr(dialogue_index, "load", lambda _identifier: scene)
    folder = shelves.shared / "שלום"
    folder.mkdir()
    (folder / "document.json").write_text(
        json.dumps({"source": "dialogue:01-hello"}), encoding="utf-8"
    )
    found = heard.recording_of(folder)
    assert found is not None and found.path == shelves.dialogues / "01-hello.mp3"
    unvoiced = SimpleNamespace(audio="01-hello.mp3", turns=[SimpleNamespace(voiced=False)])
    monkeypatch.setattr(dialogue_index, "load", lambda _identifier: unvoiced)
    assert heard.recording_of(folder) is None


def test_no_address_and_no_error_means_no_card_meta(shelves: SimpleNamespace) -> None:
    _imported(shelves.home / "שיחה")
    answer = {"texts": [{"name": "שיחה", "title": "שיחה", "reader": "/reader/x"}]}
    assert "audio" not in mcp_http.text_card_meta(json.dumps(answer), shelves.ctx, "")[0]
    assert mcp_http.text_card_meta(json.dumps({"error": "no"}), shelves.ctx, ADDRESS) == []
    # A row's name cannot walk out of the shelf.
    for name in ("../x", ".", "..", "a/b"):
        rows = {"texts": [{"name": name, "title": "t", "reader": "r"}]}
        assert "audio" not in mcp_http.text_card_meta(json.dumps(rows), shelves.ctx, ADDRESS)[0]


def test_find_text_s_text_is_unchanged_and_the_card_reads_the_same_rows(
    monkeypatch: pytest.MonkeyPatch, shelves: SimpleNamespace
) -> None:
    """§12, "Text is still the floor", and "The model is told less": the rows go in
    `structuredContent`, exactly the text's own JSON; the doors and the recording's
    address go in `_meta`, which a host hands the card and not the model."""
    _imported(shelves.home / "שיחה")
    rows = {
        "count": 1,
        "texts": [
            {
                "from": "mine",
                "name": "שיחה",
                "title": "שיחה",
                "reader": tools_module.reader_url("שיחה", ADDRESS),
                "known_share": 0.72,
                "words": 400,
            }
        ],
    }
    text = json.dumps(rows, ensure_ascii=False)
    monkeypatch.setattr(connector, "context", lambda *_a, **_k: shelves.ctx)
    monkeypatch.setattr(tools_module, "run", lambda *_a: (text, False))
    result = ask(
        "tools/call", params={"name": "find_text", "arguments": {"query": "x"}}, address=ADDRESS
    )["result"]
    said = result["content"][0]["text"]
    assert said == tools_module.shorten(text, ADDRESS)
    assert result["structuredContent"] == json.loads(said)
    assert heard.ROUTE not in said and heard.ROUTE not in json.dumps(result["structuredContent"])
    beside = result["_meta"][mcp_http.TEXT_CARD_META]
    assert beside[0]["door"] == result["structuredContent"]["texts"][0]["reader"]
    assert beside[0]["audio"]["src"].startswith(ADDRESS + heard.ROUTE)


def test_a_failed_find_carries_no_card_meta(monkeypatch: pytest.MonkeyPatch) -> None:
    text = json.dumps({"error": "This connection doesn't share the reader's own texts."})
    monkeypatch.setattr(connector, "context", lambda *_a, **_k: SimpleNamespace())
    monkeypatch.setattr(tools_module, "run", lambda *_a: (text, True))
    result = ask("tools/call", params={"name": "find_text", "arguments": {}})["result"]
    assert "_meta" not in result


# --- what a publisher put out (2026-10-06) -------------------------------------------

#: An article as `search_sources` answers with one: a text not yet on targum. Its link
#: has a query and a fragment of its own, which the door has to carry whole.
YNET = "https://www.ynet.co.il/news/article/abc123?utm=feed&x=1#top"
FOUND = {
    "count": 3,
    "items": [
        {
            "title": "הכנסת אישרה את התקציב",
            "link": YNET,
            "publisher": "Ynet",
            "kind": "news",
            "published": "2026-10-06T08:00:00+00:00",
            "seconds": 0,
            "has_transcript": False,
            "licence": "",
            "known_share": 0.71,
        },
        {
            "title": "כותרת קצרה",
            "link": "https://www.kan.org.il/item/1",
            "publisher": "Kan",
            "kind": "video",
            "published": "2026-10-06T07:00:00+00:00",
            "seconds": 250,
            "has_transcript": True,
            "licence": "",
            "known_share": None,
        },
        {"title": "x", "link": "javascript:alert(1)", "publisher": "?", "known_share": None},
    ],
}


def _following(monkeypatch: pytest.MonkeyPatch) -> None:
    """A box that follows a publisher, which is the only kind offered `search_sources`."""
    from targum.chat import sources as sources_module

    one = sources_module.Publisher(key="ynet", name="Ynet", publisher="Ynet", feed="https://x")
    monkeypatch.setattr(sources_module, "load", lambda: [one])


def test_search_sources_names_the_text_card(monkeypatch: pytest.MonkeyPatch) -> None:
    _following(monkeypatch)
    tools = ask("tools/list")["result"]["tools"]
    carded = {tool["name"]: tool["_meta"] for tool in tools if "_meta" in tool}
    assert carded["search_sources"]["ui"]["resourceUri"] == TEXT
    assert "_meta" not in {t["name"]: t for t in tools}["describe_source"]


def test_the_text_card_is_listed_where_only_search_sources_is_held(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _following(monkeypatch)
    exposed = connector.exposed

    def only(names: tuple[str, ...]) -> Any:
        def held(*args: Any, **kwargs: Any) -> list[tools_module.Tool]:
            return [tool for tool in exposed(*args, **kwargs) if tool.name in names]

        return held

    monkeypatch.setattr(connector, "exposed", only(("search_sources",)))
    assert [one["uri"] for one in ask("resources/list")["result"]["resources"]] == [TEXT]
    monkeypatch.setattr(connector, "exposed", only(("describe_source", "quote_build")))
    assert ask("resources/list")["result"]["resources"] == []
    refused = ask("resources/read", params={"uri": TEXT})
    assert refused["error"]["code"] == mcp_http.RESOURCE_NOT_FOUND


def test_a_found_article_s_door_is_our_add_page_never_the_publisher(
    shelves: SimpleNamespace,
) -> None:
    """§12: the door opens a page of ours, where the text is got ready, and never presses.
    The add page takes the address from `?source=` (the weekly's "Read the whole thing"),
    so the whole address is encoded and its own query stays its own. No recording."""
    from urllib.parse import parse_qs, urlsplit

    meta = mcp_http.text_card_meta(json.dumps(FOUND), shelves.ctx, ADDRESS)
    assert len(meta) == 3
    first, second, third = meta
    door = urlsplit(first["door"])
    assert f"{door.scheme}://{door.netloc}" == ADDRESS and door.path == "/add"
    assert parse_qs(door.query) == {"source": [YNET]}
    assert "ynet" not in door.netloc and "#" not in first["door"] and "&x=" not in first["door"]
    assert second == {"door": ADDRESS + "/add?source=https%3A%2F%2Fwww.kan.org.il%2Fitem%2F1"}
    assert third == {}, "an address that is not http or https gets no door"
    assert not any("audio" in one for one in meta)
    # No public address, no door: the card never falls back to the publisher's link.
    assert mcp_http.text_card_meta(json.dumps(FOUND), shelves.ctx, "") == [{}, {}, {}]


def test_search_sources_text_is_unchanged_and_the_card_reads_the_same_rows(
    monkeypatch: pytest.MonkeyPatch, shelves: SimpleNamespace
) -> None:
    """The model's text and `structuredContent` stay exactly what they were; the doors
    ride beside them in `_meta`, which a host hands the card and not the model."""
    _following(monkeypatch)
    text = json.dumps(FOUND, ensure_ascii=False)
    monkeypatch.setattr(connector, "context", lambda *_a, **_k: shelves.ctx)
    monkeypatch.setattr(tools_module, "run", lambda *_a: (text, False))
    result = ask(
        "tools/call",
        params={"name": "search_sources", "arguments": {"query": "x"}},
        address=ADDRESS,
    )["result"]
    said = result["content"][0]["text"]
    assert said == tools_module.shorten(text, ADDRESS)
    assert result["structuredContent"] == json.loads(said)
    assert "/add?source=" not in said
    beside = result["_meta"][mcp_http.TEXT_CARD_META]
    assert beside[0]["door"].startswith(ADDRESS + "/add?source=https%3A%2F%2Fwww.ynet")


def test_the_text_card_s_found_labels_say_what_the_reader_will_do() -> None:
    page = build_text_card()
    for said in ("Read on targum", "Watch on targum", "Listen on targum"):
        assert said in page
    russian = build_text_card("ru")
    assert "Читать в targum" in russian and "Смотреть в targum" in russian
    # The script never reaches for a found item's own link: its door comes only from
    # beside it, and it is never given a recording.
    script = re.sub(r"^\s*//.*$", "", _text_script(), flags=re.M)
    assert "row.link" not in script
    assert "found ? null : beside.audio" in script


# --- the address a recording is played from ----------------------------------------


def test_a_token_opens_its_one_file_and_runs_out(tmp_path: Any) -> None:
    clock = [1000.0]
    kept = heard.Heard(clock=lambda: clock[0])
    root = tmp_path / "home"
    (root / "t" / "audio").mkdir(parents=True)
    one = root / "t" / "audio" / "part-001.mp3"
    two = root / "t" / "audio" / "part-002.mp3"
    one.write_bytes(b"a")
    two.write_bytes(b"b")
    issued = kept.issue(one, [root])
    assert issued is not None
    token, ends = issued
    assert ends == 1000.0 + heard.LIFETIME_S
    assert kept.opened(token) == one.resolve()
    # Nothing about the token reaches another file: it is a key, never a path.
    assert kept.opened(token + "x") is None
    assert kept.opened("") is None
    assert kept.opened(token.replace(token[0], "A" if token[0] != "A" else "B")) is None
    clock[0] = ends - 1
    assert kept.opened(token) == one.resolve()
    clock[0] = ends
    assert kept.opened(token) is None, "a token stops at its twentieth minute"
    clock[0] = 1000.0
    assert kept.opened(token) is None, "and once stopped it is gone"


def test_a_token_is_made_only_for_audio_inside_a_shelf(tmp_path: Any) -> None:
    kept = heard.Heard()
    root = tmp_path / "home"
    root.mkdir()
    (root / "document.json").write_text("{}")
    (root / "a.mp3").write_bytes(b"a")
    outside = tmp_path / "elsewhere.mp3"
    outside.write_bytes(b"x")
    assert kept.issue(root / "document.json", [root]) is None
    assert kept.issue(outside, [root]) is None
    assert kept.issue(root / "missing.mp3", [root]) is None
    link = root / "link.mp3"
    link.symlink_to(outside)
    assert kept.issue(link, [root]) is None, "a link out of the shelf is outside it"
    assert kept.issue(root / "a.mp3", [root]) is not None


def test_a_file_swapped_after_its_token_is_not_opened(tmp_path: Any) -> None:
    kept = heard.Heard()
    root = tmp_path / "home"
    root.mkdir()
    one = root / "a.mp3"
    one.write_bytes(b"a")
    token, _ = kept.issue(one, [root]) or ("", 0.0)
    one.unlink()
    assert kept.opened(token) is None


def test_the_table_is_bounded() -> None:
    assert heard.MOST >= tools_module.FIND_MOST * 100


def test_the_box_plays_a_token_s_file_with_no_cookie_and_nothing_else(tmp_path: Any) -> None:
    """`/heard` answers a live token with its one file, in ranges, signed out and on an
    account box; anything else is a 404."""
    import io
    import threading
    from http.client import HTTPConnection
    from http.server import ThreadingHTTPServer
    from urllib.parse import quote

    from targum.accounts import Store
    from targum.mail import ConsoleMailer
    from targum.serve import Handler, Library

    out = tmp_path / "targum-out"
    out.mkdir()
    store = Store(tmp_path / "words.db")
    library = Library(out)
    folder = library.shared / "שיחה" / "audio"
    folder.mkdir(parents=True)
    played = folder / "part-001.mp3"
    played.write_bytes(b"ID3" + b"x" * 97)
    (library.shared / "שיחה" / "document.json").write_text("{}")
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    server.RequestHandlerClass = type(
        "TestHandler",
        (Handler,),
        {
            "library": library,
            "token": "",
            "require_account": True,
            "store": store,
            "mailer": ConsoleMailer(io.StringIO()),
            "address": f"http://127.0.0.1:{port}",
        },
    )
    threading.Thread(target=server.serve_forever, daemon=True).start()

    def get(path: str, headers: dict[str, str] | None = None) -> tuple[int, bytes, Any]:
        connection = HTTPConnection("127.0.0.1", port, timeout=5)
        try:
            connection.request("GET", path, headers=headers or {})
            response = connection.getresponse()
            return response.status, response.read(), response.headers
        finally:
            connection.close()

    try:
        issued = heard.HEARD.issue(played, [library.shared])
        assert issued is not None
        token = issued[0]
        status, body, headers = get(f"{heard.ROUTE}?t={token}")
        assert status == 200 and body == played.read_bytes()
        assert headers["Content-Type"] == "audio/mpeg"
        status, body, _ = get(f"{heard.ROUTE}?t={token}", {"Range": "bytes=0-2"})
        assert status == 206 and body == b"ID3"
        for asked in (
            f"{heard.ROUTE}?t=",
            f"{heard.ROUTE}?t={token}x",
            f"{heard.ROUTE}?t=../../document.json",
            f"{heard.ROUTE}/{token}",
        ):
            assert get(asked)[0] in (403, 404), asked
        # The reader's own address for the same file is still behind the account.
        assert get(quote("/reader/שיחה/audio/part-001.mp3"))[1] != played.read_bytes()
    finally:
        server.shutdown()
        server.server_close()
        heard.HEARD.clear()
