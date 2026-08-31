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

import pytest

from targum.render.builder import (
    LISTS,
    add_page,
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

    The places used to sit indented under the name with Upload cut off at the edge: the
    rule that reset their auto margin stood above the rule that set it, at the same
    specificity, and lost. A cascade bug is invisible in the file and obvious on a
    phone, which is why this is measured rather than read."""
    page_file = tmp_path / "learn.html"
    page_file.write_text(learn_page(TOKEN), encoding="utf-8")
    context = browser.new_context(viewport={"width": width, "height": 844})
    open_page = context.new_page()
    open_page.goto(page_file.as_uri())
    open_page.wait_for_timeout(300)
    measured = open_page.evaluate(
        """() => {
          const box = (s) => document.querySelector(s).getBoundingClientRect();
          const brand = box('.brand'), nav = box('.site-nav'), upload = box('.upload');
          const toggle = box('[data-theme-toggle]'), account = box('.account');
          return {
            navFlush: Math.abs(nav.left - brand.left) <= 1,
            navBelow: nav.top >= brand.bottom - 1,
            toggleBeside: toggle.top < brand.bottom && toggle.bottom > brand.top,
            accountBeside: account.top < brand.bottom && account.bottom > brand.top,
            toggleAtEdge: toggle.right >= document.documentElement.clientWidth - 24,
            uploadInside: upload.right <= document.documentElement.clientWidth,
            width: document.documentElement.scrollWidth,
          };
        }"""
    )
    context.close()

    assert measured["navFlush"], "the places start where the name starts"
    assert measured["navBelow"], "and sit on the line under it"
    assert measured["toggleBeside"] and measured["accountBeside"], "the corner is the account's"
    assert measured["toggleAtEdge"], "at the far edge"
    assert measured["uploadInside"], "Upload is whole"
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
