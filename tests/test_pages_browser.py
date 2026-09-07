"""Every chrome page, opened in a real browser, asked one question: did it throw?

A page's scripts are one scope. A `ReferenceError` on the way down it does not fail the
line it is on and carry on — it ends the run, so everything below it never happens. The
Add page lost its button that way: a `var` moved into an IIFE, two things outside reached
for it, and `go.onclick = …` sat below the throw and was never assigned. The page drew
perfectly. Nothing on it did anything.

Nothing else catches this. `node --check` parses and does not run. The node harnesses in
`tests/js` cover the pages that have one, and the Add page has none. Python cannot see
inside a `<script>` at all. So this is the cheapest thing that would have caught it: open
the page, and listen.

It asks nothing about what the pages look like or do — `test_pages.py` and the node
harnesses do that. Uncaught errors only, which is why every page fits in one file and one
loop.

Skips itself unless Playwright and its Chromium are installed, the way the node tests skip
without node:

    uv sync --extra browser && uv run playwright install chromium
"""

from __future__ import annotations

import base64
import json
from pathlib import Path
from urllib.parse import urlparse

import pytest

from targum.render.builder import (
    LISTS,
    add_page,
    chat_page,
    learn_page,
    library_page,
    list_page,
    progress_page,
    you_page,
)

playwright_api = pytest.importorskip(
    "playwright.sync_api", reason="Playwright is not installed: uv sync --extra browser"
)

TOKEN = "test-key"


def pages() -> dict[str, str]:
    """Every page the server renders at start-up, as it renders them."""
    built = {
        "add": add_page(TOKEN),
        "chat": chat_page(TOKEN),
        "learn": learn_page(TOKEN),
        "library": library_page(TOKEN),
        "progress": progress_page(TOKEN),
        "you": you_page(TOKEN),
    }
    built.update({f"words:{which}": list_page(TOKEN, which) for which in LISTS})
    return built


@pytest.fixture(scope="module")
def browser():
    """One Chromium for the file. Launching one a test is most of the run."""
    try:
        driver = playwright_api.sync_playwright().start()
    except Exception as why:  # pragma: no cover - environment, not behaviour
        pytest.skip(f"Playwright will not start: {why}")
    try:
        running = driver.chromium.launch()
    except Exception as why:  # pragma: no cover - the browser itself is not installed
        driver.stop()
        pytest.skip(f"no Chromium: run `playwright install chromium` ({why})")
    yield running
    running.close()
    driver.stop()


@pytest.mark.parametrize("name", sorted(pages()))
def test_a_page_runs_its_scripts_without_throwing(browser, tmp_path: Path, name: str) -> None:
    """Opened off the disk, so there is no server behind it.

    That is the harsher of the two cases and the right one to hold: every fetch fails,
    every page has to survive it, and what is left is the page's own code. A failed fetch
    should be a rejected promise the page catches — the You page and the library did not,
    which this found on its first run, and a You page whose request failed showed nothing
    at all, not even the line telling somebody where to sign in.
    """
    page_file = tmp_path / f"{name.replace(':', '-')}.html"
    page_file.write_text(pages()[name], encoding="utf-8")

    context = browser.new_context(viewport={"width": 1280, "height": 900})
    open_page = context.new_page()
    thrown: list[str] = []
    open_page.on("pageerror", lambda error: thrown.append(str(error)))
    open_page.goto(page_file.as_uri())
    # Long enough for the account to have been asked for and refused.
    open_page.wait_for_timeout(300)
    context.close()

    assert not thrown, f"{name} threw: {thrown}"


def test_the_add_page_wires_its_button(browser, tmp_path: Path) -> None:
    """The one assertion that says what the throw cost, rather than that there was one.

    `go.onclick` is assigned near the bottom of `add.js`, below everything else the page
    sets up, which makes it a good witness: if anything above it threw, this is null and
    the button a reader presses does nothing at all — no upload, no pasted text, no link.
    """
    page_file = tmp_path / "add.html"
    page_file.write_text(add_page(TOKEN), encoding="utf-8")

    context = browser.new_context(viewport={"width": 1280, "height": 900})
    open_page = context.new_page()
    open_page.goto(page_file.as_uri())
    open_page.wait_for_timeout(300)
    wired = open_page.evaluate("() => !!document.getElementById('go').onclick")
    context.close()

    assert wired, "the Add button is not wired to anything"


#: What the page sends when somebody presses Add. `/prepare` is answered here rather than
#: by a server: what is under test is the client's half — that pressing the button reads
#: what was given and asks for a price — and a real one would ingest, segment and cost
#: real time to say the same thing.
PRICED = {"id": "j1", "title": "A text", "cost": 0.02, "chapters": 1, "buying": 1, "words": 4}


def test_pasted_text_reaches_the_server_when_the_button_is_pressed(browser, tmp_path: Path) -> None:
    """The whole of what a reader does on this page, end to end on the client's side.

    It is not enough that the button is wired: what broke was a throw above it, and the
    thing that made it invisible is that the page still drew perfectly. So this presses
    it, and reads what came out the other end.
    """
    # Served from an address rather than opened off the disk, unlike the tests above: a
    # `file://` page cannot fetch a relative path at all — the browser refuses the scheme
    # before anything can answer — and what is under test here is the request.
    html = add_page(TOKEN)
    asked: list[dict] = []

    def answer(route, request):
        if "/prepare" in request.url:
            asked.append(request.post_data_json)
            route.fulfill(status=200, content_type="application/json", body=json.dumps(PRICED))
        elif request.url.endswith(("/add", "/add.html")):
            route.fulfill(status=200, content_type="text/html", body=html)
        else:
            # Everything else the page asks for on the way up — the account, mostly.
            route.fulfill(status=200, content_type="application/json", body="{}")

    context = browser.new_context(viewport={"width": 1280, "height": 900})
    open_page = context.new_page()
    open_page.route("http://add.test/**", answer)
    open_page.goto("http://add.test/add")
    open_page.fill("#pasted", "בארץ־ישראל קם העם היהודי")
    open_page.click("#go")
    open_page.wait_for_timeout(400)
    context.close()

    assert asked, "pressing Add asked for nothing"
    sent = asked[0]
    # Pasted text is a file like any other by the time it leaves: named for its first
    # line, because a paste has no other way of carrying a title.
    assert sent["name"].endswith(".txt")
    assert base64.b64decode(sent["content"]).decode("utf-8") == "בארץ־ישראל קם העם היהודי"
    assert sent["to"] and sent["words"] is True


def test_a_library_row_holds_together_at_phone_width(browser, tmp_path: Path) -> None:
    """A row now carries a scene label, a chip, a Hebrew title and an English one. At
    390px the chip takes a line of its own under the Hebrew, and the Hebrew title never
    breaks across lines — a title in two pieces reads as two titles."""
    page_file = tmp_path / "library.html"
    page_file.write_text(library_page(TOKEN), encoding="utf-8")

    shared = [
        {
            "name": "scene-01-nice-to-meet-you-he",
            "title": "נעים מאוד",
            "english": "Nice to meet you",
            "language": "he",
            "document": "h1",
            "entry": "scene-01-nice-to-meet-you",
            "kind": "dialogue",
            "register": "modern",
            "difficulty": 5,
            "minutes": 1,
            "words": 22,
            "spoken": True,
            "shared": True,
            "drawn": False,
            "sections": 1,
            "chapters": [],
            "readyChapters": 0,
            "built": 0,
        }
    ]
    context = browser.new_context(viewport={"width": 390, "height": 844})
    open_page = context.new_page()
    # Over http, not off the disk: a page on `file:` cannot fetch at all, and the shared
    # rows arrive by fetch. Both the page and its one request are answered here.
    html = page_file.read_text(encoding="utf-8")
    # The last route registered is asked first, so the catch-all goes in before the two
    # that answer.
    open_page.route("http://targum.test/**", lambda route: route.fulfill(status=404, body=""))
    open_page.route(
        "http://targum.test/library*",
        lambda route: route.fulfill(status=200, content_type="text/html", body=html),
    )
    open_page.route(
        "**/readers*",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({"readers": [], "shared": shared, "trash": [], "covers": False}),
        ),
    )
    open_page.goto("http://targum.test/library")
    open_page.wait_for_timeout(500)
    measured = open_page.evaluate(
        """() => {
          const row = document.querySelector('[data-row="scene-01-nice-to-meet-you"]');
          if (!row) return { missing: true };
          const bdi = row.querySelector('.row-title bdi');
          const chip = row.querySelector('.row-next');
          const b = bdi.getBoundingClientRect();
          const c = chip ? chip.getBoundingClientRect() : null;
          return {
            titleLines: bdi.getClientRects().length,
            chipBelow: c ? c.top >= b.bottom - 1 : null,
            chipText: chip ? chip.textContent : "",
            width: document.documentElement.scrollWidth,
          };
        }"""
    )
    context.close()

    assert not measured.get("missing"), "the shared scene has a row"
    assert measured["titleLines"] == 1, "the Hebrew title never breaks"
    assert measured["chipText"] == "Start here"
    assert measured["chipBelow"] is True, "the chip sits on its own line under the title"
    assert measured["width"] <= 390, "and the page does not scroll sideways"


@pytest.mark.parametrize("width", [320, 390, 430, 540])
def test_the_header_holds_its_corners_at_phone_width(browser, tmp_path: Path, width: int) -> None:
    """Under 46rem the header is two lines: the name at one corner and the account and
    the light switch at the other, then the places under them, flush with the name.

    The places used to sit indented under the name with Upload (then a corner, now the
    `+` on the box) cut off at the edge: the rule that reset their auto margin stood
    above the rule that set it, at the same specificity, and lost. A cascade bug is
    invisible in the file and obvious on a phone, which is why this is measured rather
    than read."""
    page_file = tmp_path / "learn.html"
    page_file.write_text(learn_page(TOKEN), encoding="utf-8")
    context = browser.new_context(viewport={"width": width, "height": 844})
    open_page = context.new_page()
    open_page.goto(page_file.as_uri())
    open_page.wait_for_timeout(300)
    measured = open_page.evaluate(
        """() => {
          const box = (s) => document.querySelector(s).getBoundingClientRect();
          const brand = box('.brand'), nav = box('.site-nav');
          const toggle = box('[data-theme-toggle]'), account = box('.account');
          return {
            navFlush: Math.abs(nav.left - brand.left) <= 1,
            navBelow: nav.top >= brand.bottom - 1,
            toggleBeside: toggle.top < brand.bottom && toggle.bottom > brand.top,
            accountBeside: account.top < brand.bottom && account.bottom > brand.top,
            toggleAtEdge: toggle.right >= document.documentElement.clientWidth - 24,
            noUpload: document.querySelector('.upload') === null,
            width: document.documentElement.scrollWidth,
          };
        }"""
    )
    context.close()

    assert measured["navFlush"], "the places start where the name starts"
    assert measured["navBelow"], "and sit on the line under it"
    assert measured["toggleBeside"] and measured["accountBeside"], "the corner is the account's"
    assert measured["toggleAtEdge"], "at the far edge"
    assert measured["noUpload"], "Upload left the corner on 2026-09-06: it is the + on the box"
    assert measured["width"] <= width, "and the page does not scroll sideways"


def test_the_header_is_one_line_on_a_tablet(browser, tmp_path: Path) -> None:
    """At 768px everything fits, and the two-line arrangement must not apply."""
    page_file = tmp_path / "learn.html"
    page_file.write_text(learn_page(TOKEN), encoding="utf-8")
    context = browser.new_context(viewport={"width": 768, "height": 1024})
    open_page = context.new_page()
    open_page.goto(page_file.as_uri())
    open_page.wait_for_timeout(300)
    one_line = open_page.evaluate(
        """() => {
          const brand = document.querySelector('.brand').getBoundingClientRect();
          const nav = document.querySelector('.site-nav').getBoundingClientRect();
          return nav.top < brand.bottom && nav.bottom > brand.top;
        }"""
    )
    context.close()
    assert one_line


def test_a_long_title_does_not_push_the_conversation_rail_under_the_thread(browser) -> None:
    """A conversation is titled with its first line, and a first line can be long. The
    rail's column is 14rem; a grid item's minimum width is its content unless told
    otherwise, so a long title widened the rail out under the raised thread, where every
    title was cut off behind it (2026-09-06). Measured, because a cascade rule is
    invisible in the file."""
    import json

    html = chat_page(TOKEN)
    long_title = "Can you find for me something interesting to read at about a bet plus level"
    context = browser.new_context(viewport={"width": 1280, "height": 800})
    page = context.new_page()

    def answer(route, request):
        if "/chat/list" in request.url:
            body = {
                "chats": [
                    {"id": "a", "title": long_title},
                    {"id": "b", "title": "שלום בוקר טוב אני רוצה משהו מעניין תקחו"},
                ],
                "usable": True,
                "talk": True,
                "hours": {"used": 0.14, "allowed": 8, "ends": "1 October"},
            }
        elif "/chat/a" in request.url:
            body = {"chat": {"id": "a", "mode": "talk"}, "seconds": 0, "turns": []}
        elif "/account/me" in request.url:
            body = {
                "signedIn": True,
                "email": "r@example.org",
                "counts": {},
                "learning": ["he"],
                "reads": ["en"],
            }
        else:
            route.fulfill(status=200, content_type="text/html", body=html)
            return
        route.fulfill(
            status=200, content_type="application/json", body=json.dumps(body, ensure_ascii=False)
        )

    page.route("http://chat.test/**", answer)
    page.goto(f"http://chat.test/chat?k={TOKEN}")
    page.wait_for_selector(".chat-list button")
    page.wait_for_timeout(200)
    measured = page.evaluate(
        """() => {
          const rail = document.querySelector('.chat-side').getBoundingClientRect();
          const thread = document.querySelector('.chat-thread').getBoundingClientRect();
          const buttons = [...document.querySelectorAll('.chat-list button')]
            .map((b) => b.getBoundingClientRect().right);
          return {
            railRight: rail.right,
            threadLeft: thread.left,
            buttonsRight: Math.max(...buttons),
          };
        }"""
    )
    context.close()
    assert measured["railRight"] <= measured["threadLeft"] + 1, "the rail keeps to its column"
    assert measured["buttonsRight"] <= measured["threadLeft"] + 1, "and so does every title in it"


def test_two_pictures_chosen_on_the_front_door_become_one_card(browser, tmp_path: Path) -> None:
    """The whole of what a reader does with a phone's worth of pages, on the client's
    side: two files chosen together on Learn sit in the box as chips, Send takes them up
    one after another, `/prepare` is asked once with both, and the conversation page
    opens on the card as a turn in the thread. Pressing it posts `/build`. The server is
    answered here — what is under test is that a real file input with `multiple` reaches
    the box's script as a set, and that the page it goes to draws the card."""
    fixture = Path(__file__).parent / "fixtures" / "pages" / "screenshot.png"
    prepared: list[dict] = []
    built: list[dict] = []
    begun = 0
    quote = {
        "id": "j1",
        "title": "נָסַעְתִּי לַנֶּגֶב",
        "language": "he",
        "segments": 6,
        "total": 6,
        "chapters": 1,
        "pages": 2,
        "doubtful": 1,
        "excerpt": ["נָסַעְתִּי לַנֶּגֶב בַּשָּׁבוּעַ שֶׁעָבַר", "בבוקר יצאנו לטיול"],
        "estimate": 0.02,
        "stage": "ready",
        "blocked": "",
        "error": "",
        "audio": False,
    }

    def answer(route, request):
        nonlocal begun
        # The path under the host, without the key: "chat/list", "upload/u1/end".
        path = urlparse(request.url).path.strip("/")
        if path in ("", "learn", "learn.html"):
            route.fulfill(status=200, content_type="text/html", body=learn_page(TOKEN))
        elif path == "chat":
            route.fulfill(status=200, content_type="text/html", body=chat_page(TOKEN))
        elif path == "chat/list":
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps({"chats": [], "usable": True, "talk": True}),
            )
        elif path == "upload/begin":
            begun += 1
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps({"upload": f"u{begun}", "chunk": 1_000_000}),
            )
        elif path.startswith("upload/") and path.endswith("/end"):
            which = path.split("/")[1]
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps({"upload": which, "picture": True}),
            )
        elif path.startswith("upload/"):
            route.fulfill(status=200, content_type="application/json", body='{"got": 0}')
        elif path == "prepare":
            prepared.append(request.post_data_json)
            route.fulfill(status=200, content_type="application/json", body=json.dumps(quote))
        elif path == "job/j1":
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(dict(quote, stage="working")),
            )
        elif path == "build":
            built.append(request.post_data_json)
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(dict(quote, stage="working")),
            )
        else:
            route.fulfill(status=200, content_type="application/json", body="{}")

    context = browser.new_context(viewport={"width": 1280, "height": 900})
    open_page = context.new_page()
    open_page.route("http://learn.test/**", answer)
    open_page.goto("http://learn.test/learn")
    open_page.wait_for_timeout(300)
    open_page.set_input_files("#chat-file", [str(fixture), str(fixture)])
    chips = open_page.locator(".chat-chip").count()
    assert open_page.locator(".quote-card").count() == 0, "held, not yet brought"
    open_page.click("#chat-send")
    open_page.wait_for_url("**/chat?**", timeout=5000)
    open_page.wait_for_selector(".chat-turn .quote-card.started", timeout=5000)
    cards = open_page.locator(".quote-card").count()
    excerpt = open_page.locator(".quote-excerpt").inner_text()
    doubt = open_page.locator(".quote-doubt").inner_text()
    buttons = open_page.locator(".quote-go").count()
    context.close()

    assert chips == 2, "one chip a file"
    assert prepared and prepared[0]["uploads"] == ["u1", "u2"], prepared
    assert cards == 1, "several pictures are one text and one card, in the thread"
    assert "נָסַעְתִּי לַנֶּגֶב" in excerpt
    assert doubt == "1 line could not be read clearly."
    assert built == [{"id": "j1"}], "Send was the press"
    assert buttons == 0, "nothing left to press"
