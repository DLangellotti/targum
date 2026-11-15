"""Send to Anki in a real browser (targum-internal#540; design.md §12, "Send to Anki talks
to the Anki on your own computer", 2026-11-14), against a fake AnkiConnect on
127.0.0.1:8765.

The page is the one the server renders, served with the policy the server gives it, so a
call the policy refused would be a violation here. At a desk the words go in and nothing
is refused; on a phone there is no Send at all. Skipped where the port is taken (a real
Anki is running) or Playwright and its Chromium are missing.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pytest
from test_words_states_browser import ME, browser  # noqa: F401 - `browser` is a fixture

from targum.render.builder import list_page
from targum.serve import Handler

pytest.importorskip("playwright.sync_api")

LEDGER = {
    "ספר": {"status": 2, "at": 1_760_000_000_000, "seen": 1},
    "בית": {"status": 1, "at": 1_760_000_000_001, "seen": 1},
}
WORDS = [
    {
        "key": f"he:{lemma}",
        "lemma": lemma,
        "term": lemma,
        "meaning": meaning,
        "stage": 2,
        "add": True,
        "before": "",
        "gap": "",
        "after": "",
        "translation": "",
        "source": "",
        "sound": f"/account/anki/sound?key=he%3A{n}",
        "soundFile": f"targum-{n}.mp3",
        "line": "",
        "lineFile": "",
        "tags": "targum targum::he targum::level-2 targum::sent",
        "hash": f"h{n}",
    }
    for n, (lemma, meaning) in enumerate((("ספר", "book"), ("בית", "<house>")))
]


class FakeAnki(BaseHTTPRequestHandler):
    """AnkiConnect, as much of it as the page uses, answering any origin."""

    calls: list[dict[str, Any]] = []
    notes: dict[int, dict[str, Any]] = {}
    models: list[str] = ["Basic"]
    decks: list[str] = ["Default"]

    def log_message(self, *_args: Any) -> None:
        pass

    def _head(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Type", "application/json")
        self.end_headers()

    def do_OPTIONS(self) -> None:  # noqa: N802 - the stdlib's name
        self.calls.append({"action": "OPTIONS"})
        self.send_response(200)
        self.send_header("Access-Control-Allow-Headers", "*")
        self._head()

    def do_POST(self) -> None:  # noqa: N802 - the stdlib's name
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)))
        self.calls.append(
            {"action": body["action"], "type": self.headers.get("Content-Type") or ""}
        )
        result = self.act(body["action"], body.get("params") or {})
        self.send_response(200)
        self._head()
        self.wfile.write(json.dumps({"result": result, "error": None}).encode("utf-8"))

    def act(self, action: str, params: dict[str, Any]) -> Any:
        if action == "requestPermission":
            return {"permission": "granted", "requireApikey": False, "version": 6}
        if action == "version":
            return 6
        if action == "deckNames":
            return self.decks
        if action == "createDeck":
            self.decks.append(params["deck"])
            return 1
        if action == "modelNames":
            return self.models
        if action == "createModel":
            self.models.append(params["modelName"])
            return {}
        if action == "findNotes":
            return [
                i for i, note in self.notes.items() if f'"note:{note["model"]}"' in params["query"]
            ]
        if action == "notesInfo":
            return [
                {
                    "noteId": i,
                    "fields": {k: {"value": v} for k, v in self.notes[i]["fields"].items()},
                }
                for i in params["notes"]
            ]
        if action == "storeMediaFile":
            return params["filename"]
        if action == "addNotes":
            ids = []
            for note in params["notes"]:
                ids.append(len(self.notes) + 1)
                self.notes[ids[-1]] = {"model": note["modelName"], "fields": note["fields"]}
            return ids
        return None


@pytest.fixture
def anki():
    try:
        server = ThreadingHTTPServer(("127.0.0.1", 8765), FakeAnki)
    except OSError:
        pytest.skip("127.0.0.1:8765 is taken (is Anki running?)")
    FakeAnki.calls, FakeAnki.notes = [], {}
    FakeAnki.models, FakeAnki.decks = ["Basic"], ["Default"]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield FakeAnki
    server.shutdown()
    server.server_close()


#: The page's own origin. On loopback, as a reader's own machine sees Anki: a page served
#: from a name that is not loopback meets Chromium's private-network rules, which ask
#: the browser's own permission and are QA's to check by hand against a real Anki.
HERE = "http://localhost:8799"


def served_words(browser, *, phone: bool = False):  # noqa: F811 - the fixture
    html = list_page("", "words")
    policy = Handler._policy(html.encode("utf-8"))
    answers = {
        "/account/me": ME,
        "/account/anki/notes": {"signedIn": True, "words": WORDS, "next": None},
    }

    def answer(route, request):
        path = request.url[len(HERE) :].split("?")[0]
        if request.resource_type == "document":
            return route.fulfill(
                status=200,
                content_type="text/html",
                body=html,
                headers={"Content-Security-Policy": policy},
            )
        if path.startswith("/account/anki/sound"):
            return route.fulfill(status=200, content_type="audio/mpeg", body=b"ID3clip")
        said = answers.get(path, {"signedIn": True})
        route.fulfill(status=200, content_type="application/json", body=json.dumps(said))

    size = {"width": 390, "height": 844} if phone else {"width": 1440, "height": 900}
    extra = {"is_mobile": True, "has_touch": True} if phone else {}
    context = browser.new_context(viewport=size, reduced_motion="reduce", **extra)
    # The browser's own prompt, said yes to, as the help asks a reader to do.
    for name in ("local-network-access", "loopback-network"):
        try:
            context.grant_permissions([name], origin=HERE)
        except Exception:  # noqa: BLE001 - an older Chromium has no such permission
            continue
    state = {"email": ME["email"], "revision": 1, "pushed": 1}
    ledger = json.dumps(LEDGER, ensure_ascii=False)
    context.add_init_script(
        "localStorage.setItem('targum:language', 'he');"
        "localStorage.setItem('targum:learning', '[\"he\"]');"
        f"localStorage.setItem('targum:sync', {json.dumps(json.dumps(state))});"
        f"localStorage.setItem('targum:vocab:he', {json.dumps(ledger)});"
        "window.__refused = [];"
        "document.addEventListener('securitypolicyviolation',"
        " (e) => window.__refused.push(e.violatedDirective + ' ' + e.blockedURI));"
    )
    page = context.new_page()
    thrown: list[str] = []
    page.on("pageerror", lambda error: thrown.append(str(error)))
    page.route(f"{HERE}/**", answer)
    return context, page, thrown, f"{HERE}/words"


def test_a_desk_sends_the_words_with_nothing_refused(browser, anki) -> None:  # noqa: F811
    context, page, thrown, url = served_words(browser)
    page.goto(url)
    page.wait_for_selector("#send-anki:not([hidden])")
    page.click("#send-anki")
    # Polled from here: the page's policy refuses the string a `wait_for_function` sends.
    for _ in range(100):
        line = page.text_content("#export-said") or ""
        if line and not line.startswith(("Anki will ask", "Sending to Anki")):
            break
        page.wait_for_timeout(100)
    said = page.text_content("#export-said")
    refused = page.evaluate("window.__refused")
    page.click("#send-anki-help")
    help_open = page.is_visible("#send-anki-how")
    context.close()

    assert said == "Added 2 words to Anki."
    assert refused == [] and thrown == []
    assert all(call["type"] != "application/json" for call in anki.calls)
    assert "OPTIONS" not in [call["action"] for call in anki.calls], "no preflight"
    sent = [note for note in anki.notes.values() if note["model"] == "targum word and sentence"]
    assert {note["fields"]["Meaning"] for note in sent} == {"book", "&lt;house&gt;"}
    assert help_open


def test_a_phone_has_no_send(browser) -> None:  # noqa: F811
    context, page, thrown, url = served_words(browser, phone=True)
    page.goto(url)
    page.wait_for_selector("#export-anki:not([hidden])")
    shown = page.is_visible("#send-anki") or page.is_visible("#send-anki-help")
    sideways = page.evaluate("document.documentElement.scrollWidth > window.innerWidth")
    context.close()
    assert not shown and not sideways and thrown == []
