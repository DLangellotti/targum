"""Share > targum, and the extension that does the same from a computer (design.md §12,
"Share > targum lands in Add", 2026-10-27; targum-internal#532).

What is held here: the manifest declares a share target and names icons that are there;
`/share` answers with Add holding what was shared and spends nothing; the manifest is on
Add and on no other page, least of all a reader; and the extension asks for two
permissions, fetches nothing, and opens Add the way a share does.
"""

from __future__ import annotations

import json
import re
import threading
from collections.abc import Iterator
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlencode

import pytest

from targum.accounts import Store
from targum.render.builder import ASSETS
from targum.serve import (
    MANIFEST_ROUTE,
    POLICY,
    SHARE_ROUTE,
    Handler,
    Library,
    shared_to_add,
    web_manifest,
)

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ASSETS.parent / "templates"
EXTENSION = ROOT / "extension"


@pytest.fixture
def port(tmp_path: Path) -> Iterator[int]:
    out = tmp_path / "targum-out"
    out.mkdir()
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    number = server.server_address[1]
    server.RequestHandlerClass = type(
        "TestHandler",
        (Handler,),
        {
            "library": Library(out),
            "token": "test-key",
            "store": Store(tmp_path / "words.db"),
            "address": f"http://127.0.0.1:{number}",
            "translated": {},
        },
    )
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield number
    finally:
        server.shutdown()
        server.server_close()


def ask(
    port: int, method: str, path: str, body: str = "", host: str = ""
) -> tuple[int, dict[str, str], bytes]:
    connection = HTTPConnection("127.0.0.1", port, timeout=10)
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    if host:
        headers["Host"] = host
    connection.request(method, path, body=body.encode("utf-8"), headers=headers)
    answer = connection.getresponse()
    read = answer.read()
    connection.close()
    return answer.status, {k.lower(): v for k, v in answer.getheaders()}, read


# -- the manifest ------------------------------------------------------------------


def test_the_manifest_declares_a_share_target_that_posts_to_share() -> None:
    manifest = web_manifest()
    assert manifest["name"] == "targum" and manifest["short_name"] == "targum"
    assert manifest["display"] == "standalone" and manifest["start_url"] == "/"
    target = manifest["share_target"]
    assert target["action"] == SHARE_ROUTE
    # A post, so shared text never rides in a query string and so never in a log.
    assert target["method"] == "POST"
    assert target["enctype"] == "application/x-www-form-urlencoded"
    assert target["params"] == {"title": "title", "text": "text", "url": "url"}


def test_the_manifest_names_installable_icons_that_are_served(port: int) -> None:
    sizes = {icon["sizes"] for icon in web_manifest()["icons"]}
    assert {"192x192", "512x512"} <= sizes, "Chrome installs only with both"
    for icon in web_manifest()["icons"]:
        status, head, body = ask(port, "GET", icon["src"])
        assert status == 200, icon["src"]
        assert head["content-type"] == "image/png" and body[:4] == b"\x89PNG"


def test_the_manifest_is_served_to_anyone_on_our_name(port: int) -> None:
    status, head, body = ask(port, "GET", MANIFEST_ROUTE)
    assert status == 200, "no key: a browser asks for a manifest without its cookie"
    assert head["content-type"] == "application/manifest+json"
    assert json.loads(body) == web_manifest()
    assert POLICY.count("manifest-src 'self'") == 1


def test_the_manifest_is_linked_from_add_alone() -> None:
    """Anywhere it is linked the browser may ask to install, which §12 keeps to Add."""
    linking = sorted(
        path.name
        for path in TEMPLATES.glob("*.j2")
        if "_manifest.html.j2" in path.read_text(encoding="utf-8")
    )
    assert linking == ["add.html.j2"]
    reader = (TEMPLATES / "reader.html.j2").read_text(encoding="utf-8")
    assert "manifest" not in reader, "a reader fetches nothing"


# -- what a share opens ------------------------------------------------------------


def test_a_shared_link_opens_add_with_it_in_source() -> None:
    assert shared_to_add({"url": "https://www.ynet.co.il/a?b=1"}) == (
        "/add?source=https%3A%2F%2Fwww.ynet.co.il%2Fa%3Fb%3D1"
    )


def test_a_link_inside_shared_text_is_the_link() -> None:
    """Android puts a page's address in `text` as often as in `url`, with the title around it."""
    where = shared_to_add({"title": "A video", "text": "Look at this https://youtu.be/v0."})
    assert where == "/add?source=https%3A%2F%2Fyoutu.be%2Fv0"


def test_shared_text_rides_after_the_hash() -> None:
    where = shared_to_add({"text": "שלום עולם"})
    assert where.startswith("/add#shared=")
    assert "?" not in where, "the reader's words are never in a query string"


def test_a_long_text_with_a_link_in_it_is_still_text() -> None:
    text = "מילים " * 100 + "https://example.com/x"
    assert shared_to_add({"text": text}).startswith("/add#shared=")


def test_a_share_with_nothing_usable_opens_add_empty() -> None:
    assert shared_to_add({}) == "/add"
    assert shared_to_add({"url": "javascript:alert(1)"}) == "/add"


def test_share_answers_with_add_and_spends_nothing(port: int) -> None:
    body = urlencode({"title": "t", "text": "", "url": "https://kan.org.il/item/1"})
    status, head, read = ask(port, "POST", SHARE_ROUTE, body)
    assert status == 303, "a GET follows, and a reload never posts again"
    assert head["location"] == "/add?source=https%3A%2F%2Fkan.org.il%2Fitem%2F1"
    assert read == b""
    status, _, _ = ask(port, "POST", SHARE_ROUTE, body, host="elsewhere.example")
    assert status == 404


def test_share_is_not_behind_the_account_check(port: int) -> None:
    """Add asks for the sign-in itself, and `?source=` survives it."""
    status, head, _ = ask(port, "POST", SHARE_ROUTE, urlencode({"text": "שלום"}))
    assert status == 303 and head["location"].startswith("/add#shared=")


def test_add_reads_the_shared_text_and_offers_install_only_when_the_browser_does() -> None:
    script = (ASSETS / "add.js").read_text(encoding="utf-8")
    assert '"#shared="' in script
    assert "replaceState" in script, "a reload does not bring the text back"
    assert "beforeinstallprompt" in script and "preventDefault" in script
    page = (TEMPLATES / "add.html.j2").read_text(encoding="utf-8")
    assert re.search(r'id="share-menu" hidden', page), "shown only where install is offered"


# -- the extension -----------------------------------------------------------------


def test_the_extension_asks_for_two_permissions_and_no_hosts() -> None:
    manifest = json.loads((EXTENSION / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["manifest_version"] == 3
    assert sorted(manifest["permissions"]) == ["activeTab", "contextMenus"]
    for wider in ("host_permissions", "optional_host_permissions", "content_scripts"):
        assert wider not in manifest, f"{wider}: it reads nothing of a page"
    for size in manifest["icons"].values():
        assert (EXTENSION / size).is_file()


def test_the_extension_fetches_nothing_and_opens_add() -> None:
    script = (EXTENSION / "background.js").read_text(encoding="utf-8")
    for reach in ("fetch(", "XMLHttpRequest", "executeScript", "storage", "cookies"):
        assert reach not in script, reach
    assert 'var TARGUM = "https://targum.page";' in script
    assert '"/add?source=" + encodeURIComponent(' in script
    assert '"/add#shared=" + encodeURIComponent(' in script


def test_the_extension_speaks_english_and_russian_alike() -> None:
    english = json.loads((EXTENSION / "_locales/en/messages.json").read_text(encoding="utf-8"))
    russian = json.loads((EXTENSION / "_locales/ru/messages.json").read_text(encoding="utf-8"))
    assert english.keys() == russian.keys()
    used = set(
        re.findall(r"__MSG_(\w+)__", (EXTENSION / "manifest.json").read_text(encoding="utf-8"))
    )
    used |= set(
        re.findall(r'getMessage\("(\w+)"\)', (EXTENSION / "background.js").read_text("utf-8"))
    )
    assert used <= english.keys()
    for said in (english, russian):
        assert said["name"]["message"] == "targum", "the name is lowercase"
        assert not any("!" in entry["message"] for entry in said.values())
