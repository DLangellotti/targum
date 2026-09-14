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
    about_page,
    add_page,
    chat_page,
    holding_page,
    learn_page,
    library_page,
    list_page,
    not_found_page,
    progress_page,
    signin_page,
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
    open_page.fill("#given", "בארץ־ישראל קם העם היהודי")
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


#: A subtitle file, a text and its translation, as the box is given them.
SUBTITLE = b"1\n00:00:01,000 --> 00:00:02,000\nshalom\n"
ENGLISH = b"In the beginning God created the heaven and the earth."
HEBREW = "בראשית ברא אלהים את השמים ואת הארץ".encode()


def _add_served(browser, asked: list[dict]):
    """The Add page from an address, with `/prepare` answered and remembered."""
    html = add_page(TOKEN)

    def answer(route, request):
        if "/prepare" in request.url:
            asked.append(request.post_data_json)
            route.fulfill(status=200, content_type="application/json", body=json.dumps(PRICED))
        elif request.url.endswith(("/add", "/add.html")):
            route.fulfill(status=200, content_type="text/html", body=html)
        else:
            route.fulfill(status=200, content_type="application/json", body="{}")

    context = browser.new_context(viewport={"width": 1280, "height": 900})
    open_page = context.new_page()
    open_page.route("http://add.test/**", answer)
    open_page.goto("http://add.test/add")
    return context, open_page


def test_a_link_in_the_box_is_priced_as_a_link(browser) -> None:
    """One box (2026-09-13, targum-internal#249): a link typed where a text could be is
    sent as the source, and the line under the box says it is a link before anything."""
    asked: list[dict] = []
    context, open_page = _add_served(browser, asked)
    open_page.fill("#given", "https://www.kan.org.il/content/kan/podcasts/p-1/12345/")
    said = open_page.text_content("#understood")
    summary = open_page.is_visible("#summary")
    open_page.click("#go")
    open_page.wait_for_timeout(400)
    context.close()

    assert said and said.startswith("Thanks for the link"), said
    assert summary, "every choice on one line once something is in the box"
    assert asked and asked[0]["source"].startswith("https://www.kan.org.il/"), asked
    assert "content" not in asked[0], "a link is not a pasted text"


def test_a_recording_and_its_subtitles_are_paired_without_asking(browser) -> None:
    """Dropped together, a recording and a subtitle file are a recording with its own
    transcript: Transcript is set to I have one by the box, not by the reader."""
    context, open_page = _add_served(browser, [])
    open_page.set_input_files(
        "#file",
        [
            {"name": "shiur-12.m4a", "mimeType": "audio/mp4", "buffer": b"\x00" * 2048},
            {"name": "shiur-12.srt", "mimeType": "text/plain", "buffer": SUBTITLE},
        ],
    )
    open_page.wait_for_timeout(200)
    got = open_page.evaluate(
        """() => ({
          chips: [...document.querySelectorAll('.given-file-meta')].map((m) => m.textContent),
          said: document.getElementById('understood').textContent,
          mine: document.querySelector('[data-spoken="mine"]').getAttribute('aria-pressed'),
          transcriptRow: !document.getElementById('audio-extra').hidden,
          translationRow: !document.getElementById('translation-row').hidden,
          line: document.getElementById('summary-line').textContent,
        })"""
    )
    context.close()

    assert len(got["chips"]) == 2 and got["chips"][1].startswith("transcript"), got
    assert "the transcript that came with it" in got["said"], got
    assert got["mine"] == "true" and got["transcriptRow"], got
    assert not got["translationRow"], "a recording goes up in pieces, with no translation row"
    assert "your transcript" in got["line"], got


def test_a_text_and_its_translation_are_paired_by_their_script(browser) -> None:
    """Two plain texts, one in Hebrew letters and one in Latin: the Hebrew is the text and
    the other is its translation, and both reach `/prepare`."""
    asked: list[dict] = []
    context, open_page = _add_served(browser, asked)
    open_page.set_input_files(
        "#file",
        [
            {"name": "english.txt", "mimeType": "text/plain", "buffer": ENGLISH},
            {"name": "hebrew.txt", "mimeType": "text/plain", "buffer": HEBREW},
        ],
    )
    open_page.wait_for_timeout(300)
    mine = open_page.get_attribute('[data-how="mine"]', "aria-pressed")
    open_page.click("#go")
    open_page.wait_for_timeout(500)
    context.close()

    assert mine == "true", "the box pressed I have one"
    assert asked, "Continue asked for a price"
    assert asked[0]["name"] == "hebrew.txt", asked[0].get("name")
    assert asked[0]["translationName"] == "english.txt"


#: The line that was refused on 2026-09-14, as it was pasted.
ITALIAN = "Suo marito sta guardando nella macchina. \u201cDov\u2019\u00e8 la tenda?\u201d dice."


def _add_in(browser, code: str, asked: list[dict]):
    """The Add page with `code` chosen in the menu at the top, as a reader left it."""
    html = add_page(TOKEN)

    def answer(route, request):
        if "/prepare" in request.url:
            asked.append(request.post_data_json)
            route.fulfill(status=200, content_type="application/json", body=json.dumps(PRICED))
        elif request.url.endswith(("/add", "/add.html")):
            route.fulfill(status=200, content_type="text/html", body=html)
        else:
            route.fulfill(status=200, content_type="application/json", body="{}")

    context = browser.new_context(viewport={"width": 1280, "height": 900})
    context.add_init_script(f"localStorage.setItem('targum:language', '{code}')")
    open_page = context.new_page()
    open_page.route("http://add.test/**", answer)
    open_page.goto("http://add.test/add")
    return context, open_page


def test_a_paste_is_read_in_the_language_chosen(browser) -> None:
    """Italian chosen at the top, Italian pasted: a text in Italian, priced as one
    (2026-09-14). It was refused as "another script", because the box only ever looked
    for Hebrew letters, and every line on the page said Hebrew."""
    asked: list[dict] = []
    context, open_page = _add_in(browser, "it", asked)
    open_page.fill("#given", ITALIAN)
    got = open_page.evaluate(
        """() => ({
          from: document.getElementById('from').value,
          said: document.getElementById('understood').textContent,
          placeholder: document.getElementById('given').placeholder,
          label: document.getElementById('given').getAttribute('aria-label'),
        })"""
    )
    open_page.click("#change")
    open_page.click('[data-how="mine"]')
    note = open_page.text_content("#how-note")
    open_page.click("#go")
    open_page.wait_for_timeout(400)
    context.close()

    assert got["from"] == "it", got
    assert got["said"] == "That's 10 words of Italian.", got
    assert "Italian" in got["placeholder"] and "Hebrew" not in got["placeholder"], got
    assert "Italian" in got["label"] and "Hebrew" not in got["label"], got
    assert note and "Italian" in note, note
    assert asked and asked[0]["from"] == "it", asked


def test_english_is_a_request_beside_a_latin_alphabet_language(browser) -> None:
    """With French chosen, English letters are French letters, so the words decide: a
    line about what the reader wants is still a request, never priced as French."""
    asked: list[dict] = []
    context, open_page = _add_in(browser, "fr", asked)
    open_page.fill("#given", "a short podcast about why flats in Paris cost so much")
    said = open_page.text_content("#understood")
    open_page.click("#go")
    open_page.wait_for_timeout(400)
    context.close()

    assert said and "what you want to read" in said, said
    assert asked == [], "a description never reaches /prepare"


def test_the_wrong_script_names_the_language_chosen(browser) -> None:
    """Hebrew pasted with Russian chosen is not refused as Hebrew's other script: the
    line names Russian, its letters, and where the language is chosen."""
    context, open_page = _add_in(browser, "ru", [])
    open_page.fill("#given", " ".join(["בראשית ברא אלהים את השמים ואת הארץ"] * 7))
    said = open_page.text_content("#understood")
    context.close()

    assert said == (
        "You're adding Russian, and this isn't in Cyrillic letters. "
        "Choose its language under Change."
    ), said


def test_a_description_is_never_priced(browser) -> None:
    """A sentence about what the reader wants is a request, not a text: Continue sends
    nothing to `/prepare`, and Ask targum — a turn of conversation, the reader's own
    press — is offered where the talk drawer is on the page."""
    asked: list[dict] = []
    context, open_page = _add_served(browser, asked)
    open_page.fill("#given", "a short podcast about why flats in Tel Aviv cost so much")
    said = open_page.text_content("#understood")
    offered = open_page.is_visible("#ask-targum")
    open_page.click("#go")
    open_page.wait_for_timeout(400)
    context.close()

    assert said and "what you want to read" in said, said
    assert offered, "Ask targum is offered for a description"
    assert asked == [], "a description never reaches /prepare"


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
    """On a phone the header is one line — the name at one corner and the bell and the
    account at the other, find and the light switch in the account's sheet since
    2026-09-14 (design.md §13) — and the four places are a bar at the
    foot of the window (phase 4, 2026-09-11), flush with its edges. They used to sit
    under the name, and before that indented under it with Upload cut off at the edge:
    a cascade bug is invisible in the file and obvious on a phone, which is why this is
    measured rather than read."""
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
          const account = box('.account');
          const shown = (s) => getComputedStyle(document.querySelector(s)).display;
          return {
            navFlush: nav.left <= 1 && nav.right >= document.documentElement.clientWidth - 1,
            navBelow: Math.abs(nav.bottom - window.innerHeight) <= 1
              && getComputedStyle(document.querySelector('.site-nav')).position === 'fixed',
            barToggle: shown('.site-head-row > [data-theme-toggle]'),
            barFind: shown('.site-head-row > .palette-open'),
            sheetToggle: !!document.querySelector('.account-panel [data-theme-toggle]'),
            accountBeside: account.top < brand.bottom && account.bottom > brand.top,
            accountAtEdge: account.right >= document.documentElement.clientWidth - 24,
            noUpload: document.querySelector('.upload') === null,
            cut: [...document.querySelectorAll('.site-nav a')]
              .filter((a) => a.scrollWidth > a.clientWidth + 1).map((a) => a.textContent),
            width: document.documentElement.scrollWidth,
          };
        }"""
    )
    context.close()

    assert measured["navFlush"], "the places take the whole foot of the window"
    assert measured["navBelow"], "and stay there"
    assert measured["accountBeside"], "the corner is the account's"
    assert measured["accountAtEdge"], "at the far edge"
    assert measured["barToggle"] == "none" and measured["barFind"] == "none", measured
    assert measured["sheetToggle"], "the light switch is in the account's sheet"
    assert measured["noUpload"], "Upload left the corner on 2026-09-06: it is the + on the box"
    assert measured["cut"] == [], "all four places are read whole, Add among them (2026-09-13)"
    assert measured["width"] <= width, "and the page does not scroll sideways"


@pytest.mark.parametrize("width", [320, 360, 384, 412])
def test_a_signed_in_header_fits_a_phone(browser, width: int) -> None:
    """Signed in, with two languages, the bar holds the name, the language, find, the
    bell, the account and the light switch. It was 385px wide whatever the screen, so a
    phone narrower than that scrolled sideways; the account was squashed into an oval;
    and the language's chevron stood outside its pill, its `::after` taken by the reach
    `reader.css` gives the button on a touch screen (2026-09-14)."""
    html = learn_page(TOKEN)

    def answer(route, request):
        u = request.url
        if "/account/me" in u:
            body = {"signedIn": True, "email": "d@x.test", "initials": "DJ", "language": "he"}
        elif request.resource_type == "document":
            route.fulfill(status=200, content_type="text/html", body=html)
            return
        else:
            body = {}
        route.fulfill(status=200, content_type="application/json", body=json.dumps(body))

    context = browser.new_context(
        viewport={"width": width, "height": 700}, is_mobile=True, has_touch=True
    )
    page = context.new_page()
    page.add_init_script(
        "localStorage.setItem('targum:learning', JSON.stringify(['he', 'it']));"
        "localStorage.setItem('targum:language', 'he')"
    )
    page.route("http://learn.test/**", answer)
    page.goto(f"http://learn.test/learn?k={TOKEN}")
    page.wait_for_selector(".account > button.avatar")
    page.wait_for_selector(".lang-open")
    page.wait_for_timeout(200)
    got = page.evaluate(
        """() => {
          const open = document.querySelector('.lang-open');
          const pill = open.getBoundingClientRect();
          const chevron = getComputedStyle(open, '::before');
          const account = document.querySelector('.account > button').getBoundingClientRect();
          return {
            inner: window.innerWidth, scrollWidth: document.documentElement.scrollWidth,
            chevronDrawn: chevron.content === '""' && chevron.position !== 'absolute',
            flag: open.querySelector('.lang-flag').getBoundingClientRect().left >= pill.left,
            round: Math.abs(account.width - account.height) <= 1,
          };
        }"""
    )
    context.close()
    assert got["inner"] == width and got["scrollWidth"] <= width, f"sideways at {width}px: {got}"
    assert got["chevronDrawn"] and got["flag"], f"the chevron in its pill: {got}"
    assert got["round"], f"the account is a circle: {got}"


def test_the_bell_is_a_sheet_that_fits_a_phone(browser) -> None:
    """A long inbox on a phone ran off the top of the screen with Clear all above it, a
    failure's address ran past the edge, a line with nothing to open put its × in the
    Open column, and the round pill stood over the sheet (2026-09-14)."""
    html = learn_page(TOKEN)
    address = "https://www.example.test/" + "a-long-path-segment-" * 8 + "?utm_source=copy_link"
    jobs = [
        {"id": f"j{n}", "title": f"text {n}", "stage": "done", "reader": f"r{n}/reader/index.html"}
        for n in range(24)
    ] + [
        {"id": "bad", "title": "", "stage": "failed", "error": f"Client error for url '{address}'"}
    ]

    def answer(route, request):
        u = request.url
        if "/jobs" in u:
            body = {"jobs": jobs}
        elif "/account/me" in u:
            body = {"signedIn": True, "email": "d@x.test", "initials": "DJ"}
        elif request.resource_type == "document":
            route.fulfill(status=200, content_type="text/html", body=html)
            return
        else:
            body = {}
        route.fulfill(status=200, content_type="application/json", body=json.dumps(body))

    context = browser.new_context(
        viewport={"width": 384, "height": 694}, is_mobile=True, has_touch=True
    )
    page = context.new_page()
    page.route("http://learn.test/**", answer)
    page.goto(f"http://learn.test/learn?k={TOKEN}")
    page.wait_for_selector("#notices-count:not([hidden])")
    page.click("#notices-open")
    page.wait_for_timeout(300)
    got = page.evaluate(
        """() => {
          const panel = document.getElementById('notices-panel');
          const box = panel.getBoundingClientRect();
          const clear = document.getElementById('notices-clear').getBoundingClientRect();
          const xs = [...panel.querySelectorAll('.notices-x')]
            .map((x) => Math.round(x.getBoundingClientRect().right));
          const pill = document.getElementById('talk-open').getBoundingClientRect();
          const under = document.elementFromPoint(
            pill.left + pill.width / 2, pill.top + pill.height / 2);
          return {
            top: box.top, bottom: box.bottom, height: innerHeight, width: innerWidth,
            scrollWidth: document.documentElement.scrollWidth,
            panelScrolls: panel.scrollHeight > panel.clientHeight,
            clearTop: clear.top, clearBottom: clear.bottom,
            xs: [...new Set(xs)],
            pillCovers: !panel.contains(under),
            wide: [...panel.querySelectorAll('li')]
              .filter((li) => li.scrollWidth > li.clientWidth + 1).length,
          };
        }"""
    )
    context.close()
    assert got["top"] >= 40 and got["bottom"] <= got["height"] + 1, f"on the screen: {got}"
    assert got["panelScrolls"], "the inbox scrolls inside the sheet"
    assert got["top"] <= got["clearTop"] and got["clearBottom"] <= got["bottom"], got
    assert len(got["xs"]) == 1, f"every × in one column: {got['xs']}"
    assert got["wide"] == 0 and got["scrollWidth"] <= got["width"], f"an address runs past: {got}"
    assert not got["pillCovers"], "the pill does not stand over the sheet"


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
    glyphs = open_page.evaluate(
        """() => [...document.querySelectorAll('.site-nav a')]
          .filter((a) => getComputedStyle(a.querySelector('.nav-glyph')).display !== 'none')
          .map((a) => a.dataset.nav)"""
    )
    context.close()
    assert one_line
    assert glyphs == ["add"], "at a desk only Add keeps its glyph, a + before the word"


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


@pytest.mark.parametrize("width", [390, 1280])
def test_the_box_is_one_row_at_every_width(browser, width: int) -> None:
    """Since 2026-09-10 (targum-internal#235) the `+`, the field, Speak and Send share
    the field's row, on a phone as on a desk; the buttons used to sit on a row under it.
    Measured, because a grid template is a promise the stylesheet cannot prove — one
    control with a minimum width the column cannot give would wrap the row."""
    html = chat_page(TOKEN)
    context = browser.new_context(viewport={"width": width, "height": 800})
    page = context.new_page()

    def answer(route, request):
        if "/chat/list" in request.url:
            body = {"chats": [], "usable": True, "talk": True}
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
        route.fulfill(status=200, content_type="application/json", body=json.dumps(body))

    page.route("http://chat.test/**", answer)
    page.goto(f"http://chat.test/chat?k={TOKEN}")
    page.wait_for_timeout(300)
    # A plain http origin has no microphone, so the page hides Speak; shown by hand here
    # so the row is measured with all four of its controls in it.
    page.evaluate("() => { document.getElementById('chat-mic').hidden = false; }")
    boxes = page.evaluate(
        """() => Object.fromEntries(['chat-bring', 'say', 'chat-mic', 'chat-send'].map((id) => {
          const node = document.getElementById(id);
          const r = node.getBoundingClientRect();
          return [id, { bottom: r.bottom, left: r.left, right: r.right, hidden: node.hidden }];
        }))"""
    )
    words = page.evaluate(
        """() => ['chat-mic', 'chat-send']
          .map((id) => document.getElementById(id).textContent.trim())"""
    )
    context.close()
    shown = {name: box for name, box in boxes.items() if not box["hidden"]}
    assert sorted(shown) == ["chat-bring", "chat-mic", "chat-send", "say"]
    # The buttons sit on the field's baseline, so it is the bottoms that agree: the field
    # itself may be two lines tall where its placeholder wraps.
    bottoms = {name: box["bottom"] for name, box in shown.items()}
    assert max(bottoms.values()) - min(bottoms.values()) < 4, f"one row at {width}px: {bottoms}"
    assert shown["chat-bring"]["right"] <= shown["say"]["left"] + 1
    assert shown["say"]["right"] <= shown["chat-mic"]["left"] + 1
    assert shown["chat-mic"]["right"] <= shown["chat-send"]["left"] + 1
    assert words == ["", ""], "glyphs, with the word as the label"


def test_on_a_phone_the_list_is_a_sheet_behind_a_pill_at_the_top(browser) -> None:
    """targum-internal#238. The list stood under the whole thread and the box on a phone,
    past everything. Now the side comes first as one row, the list is out of the flow,
    and the pill opens it as a sheet over the page; at a desk the pill is not drawn and
    the list stands in its column. Measured, because `display` under a media query is
    a promise the file cannot prove."""
    html = chat_page(TOKEN)

    def answer(route, request):
        if "/chat/list" in request.url:
            body = {
                "chats": [{"id": "a", "title": "Something to read", "seen": 1}],
                "usable": True,
                "talk": True,
            }
        elif "/chat/a" in request.url:
            body = {"chat": {"id": "a", "mode": "talk"}, "seconds": 0, "turns": []}
        elif "/account/me" in request.url:
            body = {"signedIn": False}
        else:
            route.fulfill(status=200, content_type="text/html", body=html)
            return
        route.fulfill(status=200, content_type="application/json", body=json.dumps(body))

    seen = {}
    for width in (390, 1280):
        context = browser.new_context(viewport={"width": width, "height": 800})
        page = context.new_page()
        page.route("http://chat.test/**", answer)
        page.goto(f"http://chat.test/chat?k={TOKEN}")
        page.wait_for_timeout(300)
        before = page.evaluate(
            """() => ({
              pill: getComputedStyle(document.getElementById('chat-open-list')).display,
              list: getComputedStyle(document.getElementById('chat-list')).display,
              sideTop: document.querySelector('.chat-side').getBoundingClientRect().top,
              threadTop: document.querySelector('.chat-thread').getBoundingClientRect().top,
            })"""
        )
        if width == 390:
            page.click("#chat-open-list")
            page.wait_for_timeout(100)
            opened = page.evaluate(
                """() => ({
                  list: getComputedStyle(document.getElementById('chat-list')).display,
                  position: getComputedStyle(document.getElementById('chat-list')).position,
                })"""
            )
            page.click(".chat-list button")
            page.wait_for_timeout(200)
            after = page.evaluate(
                """() => ({
                  list: getComputedStyle(document.getElementById('chat-list')).display,
                  hash: location.hash,
                })"""
            )
            seen["phone"] = (before, opened, after)
        else:
            seen["desk"] = before
        context.close()

    before, opened, after = seen["phone"]
    assert before["pill"] != "none" and before["list"] == "none", "a pill, no list in the flow"
    assert before["sideTop"] < before["threadTop"], "the side comes first"
    assert opened["list"] != "none" and opened["position"] == "fixed", "the sheet"
    assert after["list"] == "none" and after["hash"] == "#a", (
        "a row closes it and writes the address"
    )
    assert seen["desk"]["pill"] == "none" and seen["desk"]["list"] != "none", (
        "at a desk, the column"
    )


def test_the_box_stays_in_view_however_long_the_thread(browser) -> None:
    """targum-internal#247: the page is the viewport. Thirty turns, and the box is still
    on screen at a phone's height, with the thread scrolling inside itself; and a
    reader who asked for no motion gets none."""
    html = chat_page(TOKEN)
    turns = []
    for n in range(30):
        turns.append(
            {"n": 2 * n + 1, "role": "user", "said": f"line {n}", "stage": "done", "error": ""}
        )
        turns.append(
            {
                "n": 2 * n + 2,
                "role": "assistant",
                "said": "שָׁלוֹם.\n= Hello.",
                "stage": "done",
                "error": "",
            }
        )

    def answer(route, request):
        if "/chat/list" in request.url:
            body = {"chats": [{"id": "a", "title": "t", "seen": 1}], "usable": True, "talk": True}
        elif "/chat/a" in request.url:
            body = {"chat": {"id": "a", "mode": "talk"}, "seconds": 0, "turns": turns}
        elif "/account/me" in request.url:
            body = {"signedIn": False}
        else:
            route.fulfill(status=200, content_type="text/html", body=html)
            return
        route.fulfill(
            status=200, content_type="application/json", body=json.dumps(body, ensure_ascii=False)
        )

    seen = {}
    for width, height in ((390, 700), (1280, 800)):
        context = browser.new_context(
            viewport={"width": width, "height": height}, reduced_motion="reduce"
        )
        page = context.new_page()
        page.route("http://chat.test/**", answer)
        page.goto(f"http://chat.test/chat?k={TOKEN}")
        page.wait_for_selector(".chat-turn")
        page.wait_for_timeout(300)
        seen[width] = page.evaluate(
            """() => {
              const send = document.getElementById('chat-send').getBoundingClientRect();
              const thread = document.getElementById('chat-thread');
              return {
                sendBottom: send.bottom,
                turns: document.querySelectorAll('.chat-turn').length,
                scrolls: thread.scrollHeight > thread.clientHeight,
                labels: [...document.querySelectorAll('.chat-who')].length,
                motion: getComputedStyle(document.querySelector('.chat-turn')).animationName,
              };
            }"""
        )
        context.close()
    for width, height in ((390, 700), (1280, 800)):
        got = seen[width]
        assert got["turns"] == 60
        assert got["sendBottom"] <= height + 1, f"Send in view at {width}px: {got}"
        assert got["scrolls"], "the thread scrolls inside itself"
        assert got["labels"] == 0, "no word over a turn"
        assert got["motion"] == "none", "asked for no motion, given none"


@pytest.mark.parametrize("width", [320, 375, 430, 768, 1024, 1440, 2560])
def test_the_front_page_holds_at_every_width(browser, width: int) -> None:
    """2026-09-11: "I want this to work on all major modern devices, from a small iPhone
    to a large 32-inch screen". The page never scrolls sideways, a chip never runs past
    the card it stands in, the two-column row is one column below 48rem, and Send is
    on screen at the top of the page."""
    html = learn_page(TOKEN)
    chips = [
        {"id": "read", "line": "Find me something to read"},
        {
            "id": "continue",
            "line": "Continue",
            "title": "יוטיוב מקשיחה תנאים: ליוצרים חדשים יהיה קשה יותר להרוויח כסף - טכנולוגיה",
            "reader": "x/reader/index.html",
        },
        {"id": "words", "line": "Use my new words"},
        {"id": "stuck", "line": "Explain a word I'm stuck on"},
    ]
    readers = [
        {
            "name": "youtube-he",
            "title": "יוטיוב מקשיחה תנאים: ליוצרים חדשים יהיה קשה יותר להרוויח כסף",
            "language": "he",
            "register": "modern",
            "document": "h1",
            "built": 1,
            "chapters": [1],
            "readyChapters": 1,
            "known": 0.31,
            "reader": "youtube-he/reader/index.html",
        }
    ]

    def answer(route, request):
        u = request.url
        if "/chat/list" in u:
            body = {
                "chats": [{"id": "a", "title": "t", "seen": 1}],
                "usable": True,
                "talk": True,
                "chips": chips,
            }
        elif "/reader/" in u:
            route.fulfill(
                status=200,
                content_type="text/html",
                body="<html><body><p>שורה ראשונה ארוכה למדי של טקסט.</p></body></html>",
            )
            return
        elif "/readers" in u:
            body = {"readers": readers, "shared": [], "trash": []}
        elif "/account/me" in u:
            body = {"signedIn": False}
        elif "/words/common" in u:
            body = {"words": [], "offset": 0, "next": None, "into": "en"}
        elif "embed=1" in u:
            route.fulfill(status=200, content_type="text/html", body=chat_page(TOKEN, embed=True))
            return
        else:
            route.fulfill(status=200, content_type="text/html", body=html)
            return
        route.fulfill(
            status=200, content_type="application/json", body=json.dumps(body, ensure_ascii=False)
        )

    context = browser.new_context(viewport={"width": width, "height": 800})
    page = context.new_page()
    page.add_init_script("localStorage.setItem('targum:opened', JSON.stringify({h1: 1}))")
    page.route("http://learn.test/**", answer)
    page.goto(f"http://learn.test/learn?k={TOKEN}")
    # Before the drawer opens, while the pill stands at the corner: on a phone the sheet's
    # window ends above everything fixed at the foot (2026-09-14), so the reader's own bar
    # at the bottom of the frame is never behind the places or the pill.
    page.wait_for_selector("#carry-window:not([hidden])")
    page.wait_for_timeout(300)
    foot = page.evaluate(
        """() => {
          const box = (s) => document.querySelector(s).getBoundingClientRect();
          const open = document.getElementById('carry');
          const hint = document.getElementById('carry-hint');
          return { window: box('#carry-window').bottom, nav: box('.site-nav').top,
                   pill: box('#talk-open').top,
                   open: open.textContent.trim(), openBox: open.getBoundingClientRect().toJSON(),
                   head: box('.page-head').toJSON(),
                   hint: getComputedStyle(hint).display === 'none' ? '' : hint.textContent,
                   hintBox: hint.getBoundingClientRect().toJSON() };
        }"""
    )
    # The conversation is the conversation page framed in the drawer the pill opens
    # (2026-09-11): the chips and the box are measured inside it, against the drawer's
    # own width, with the drawer open.
    page.click("#talk-open")
    talk = page.frame_locator("#talk-frame")
    talk.locator(".chat-ask").first.wait_for()
    page.wait_for_timeout(400)
    got = page.evaluate(
        """() => {
          const doc = document.documentElement;
          const drawer = document.getElementById('talk-drawer').getBoundingClientRect();
          const frame = document.getElementById('talk-frame').getBoundingClientRect();
          const sheet = document.getElementById('carry-sheet').getBoundingClientRect();
          const front = document.getElementById('front').getBoundingClientRect();
          const window_ = document.getElementById('carry-window');
          const nav = document.querySelector('.site-nav');
          const navBox = nav.getBoundingClientRect();
          return {
            navFixed: getComputedStyle(nav).position === 'fixed',
            navBottom: navBox.bottom, navLeft: navBox.left, navRight: navBox.right,
            scrollWidth: doc.scrollWidth, inner: window.innerWidth,
            frameLeft: frame.left, frameRight: frame.right, frameHeight: frame.height,
            talkRight: drawer.right, drawerTop: drawer.top, drawerBottom: drawer.bottom,
            sheetWidth: Math.round(sheet.width), frontWidth: Math.round(front.width),
            reader: window_.hidden ? ''
              : document.getElementById('carry-frame').getAttribute('src'),
            root: parseFloat(getComputedStyle(doc).fontSize),
          };
        }"""
    )
    inside = [f for f in page.frames if "embed=1" in f.url][0].evaluate(
        """() => {
          const doc = document.documentElement;
          const chips = [...document.querySelectorAll('.chat-ask')]
            .map((c) => c.getBoundingClientRect().right);
          const send = document.getElementById('chat-send').getBoundingClientRect();
          const mic = document.getElementById('chat-mic');
          return {
            width: window.innerWidth, scrollWidth: doc.scrollWidth,
            chipsPast: chips.filter((r) => r > window.innerWidth + 1).length,
            sendLeft: send.left, sendRight: send.right, sendBottom: send.bottom,
            height: window.innerHeight,
            mic: !mic.hidden && mic.getBoundingClientRect().width > 0,
            base: document.querySelector('base') && document.querySelector('base').target,
          };
        }"""
    )
    context.close()
    assert got["scrollWidth"] <= got["inner"] + 1, f"sideways scroll at {width}px: {got}"
    assert got["frameLeft"] >= 0 and got["frameRight"] <= got["talkRight"] + 1, got
    assert got["frameHeight"] >= 300, f"the conversation has room at {width}px: {got}"
    assert got["sheetWidth"] == got["frontWidth"], f"the sheet takes the row at {width}px"
    # Phase 4: on a phone the four places are a bar at the foot of the window.
    assert got["navFixed"] == (width <= 640), f"{width}px: {got}"
    if width <= 640:
        assert abs(got["navBottom"] - 800) <= 1 and got["navLeft"] == 0, (
            f"the bar at the foot: {got}"
        )
        assert got["navRight"] == width
    assert 0 <= got["drawerTop"] and got["drawerBottom"] <= 800 + 1, f"the drawer on screen: {got}"
    if width <= 640:
        assert foot["window"] <= min(foot["nav"], foot["pill"]), f"the sheet runs under: {foot}"
        # And the page you were on still shows above the drawer (2026-09-14).
        assert got["drawerTop"] >= 800 * 0.15, f"the drawer covers the page: {got}"
    assert "preview=1" in got["reader"], "the sheet frames the reader, working"
    assert 16 <= got["root"] <= 22, f"the rem is {got['root']} at {width}px"
    assert inside["scrollWidth"] <= inside["width"] + 1, f"the frame scrolls sideways: {inside}"
    assert inside["chipsPast"] == 0, f"a chip runs past the frame at {width}px"
    assert 0 <= inside["sendLeft"] and inside["sendRight"] <= inside["width"], inside
    assert inside["sendBottom"] <= inside["height"] + 1, f"Send is below the frame: {inside}"
    assert inside["base"] == "_top", "every link in the frame opens the page that holds it"
    # 2026-09-14: "people should be able to talk to targum ... on any device".
    assert inside["mic"], f"no microphone in the conversation at {width}px"
    # And the sheet says the reader is the better place to read, at every width: the press
    # names where it goes, the line beside it says why, and neither runs out of the head.
    assert foot["open"] == "Open the reader", foot
    assert foot["hint"] == "Read here, or go full screen.", foot
    for part in ("openBox", "hintBox"):
        box = foot[part]
        assert box["left"] >= foot["head"]["left"] and box["right"] <= foot["head"]["right"] + 1, (
            f"{part} runs out of the sheet's head at {width}px: {foot}"
        )
        assert box["width"] > 0 and box["height"] > 0
    assert foot["hintBox"]["right"] <= foot["openBox"]["left"] + 1 or (
        foot["hintBox"]["bottom"] <= foot["openBox"]["top"] + 1
    ), f"the line and the press overlap at {width}px: {foot}"


def test_two_pictures_chosen_on_the_front_door_become_one_card(browser, tmp_path: Path) -> None:
    """The whole of what a reader does with a phone's worth of pages, on the client's
    side: two files chosen together on Learn sit in the box as chips, Send takes them up
    one after another, `/prepare` is asked once with both, `/build` is pressed by Send
    itself, and the reader opens when the build is done. The server is answered here —
    what is under test is that a real file input with `multiple` reaches the box's
    script as a set, and that the page ends up in the reader."""
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
            embed = "embed=1" in request.url
            route.fulfill(status=200, content_type="text/html", body=chat_page(TOKEN, embed=embed))
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
                body=json.dumps(dict(quote, stage="done", reader="negev-he/reader/index.html")),
            )
        elif path.startswith("reader/"):
            route.fulfill(status=200, content_type="text/html", body="<html>the reader</html>")
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
    # The box is in the conversation page framed in the drawer (2026-09-11); the text it
    # opens must open in the page that holds the drawer.
    open_page.click("#talk-open")
    talk = open_page.frame_locator("#talk-frame")
    talk.locator("#chat-send").wait_for()
    open_page.wait_for_timeout(300)
    talk.locator("#chat-file").set_input_files([str(fixture), str(fixture)])
    chips = talk.locator(".chat-chip").count()
    assert talk.locator(".quote-card").count() == 0, "held, not yet brought"
    talk.locator("#chat-send").click()
    # The text opens in the sheet beside the conversation, not on a page of its own
    # (2026-09-11): the frame offers it to the page, which draws it.
    open_page.wait_for_function(
        "() => (document.getElementById('carry-frame').getAttribute('src') || '')"
        ".indexOf('negev-he') >= 0",
        timeout=5000,
    )
    landed = open_page.evaluate(
        """() => ({
          url: location.href,
          frame: document.getElementById('carry-frame').getAttribute('src'),
          sheet: !document.getElementById('carry-sheet').hidden,
          heading: document.getElementById('carry-heading').textContent,
          open: document.getElementById('carry').getAttribute('href'),
        })"""
    )
    context.close()

    assert chips == 2, "one chip a file"
    assert prepared and prepared[0]["uploads"] == ["u1", "u2"], prepared
    assert built == [{"id": "j1"}], "Send was the press"
    assert "learn.test/learn" in landed["url"], "nobody was sent to another page"
    assert landed["sheet"] and "/reader/negev-he/reader/index.html" in landed["frame"], (
        "and the text opened in the sheet"
    )
    assert "preview=1" in landed["frame"] and "preview" not in landed["open"]
    assert landed["heading"] == "From the conversation"


@pytest.mark.parametrize("width", [390, 1440])
def test_the_pill_opens_the_conversation_as_a_drawer_on_any_page(browser, width: int) -> None:
    """2026-09-11: "'talk to targum' can be in the sticky CTA on every page that opens
    up for you". On the Library: the pill is on screen, nothing is loaded until it is
    pressed, the drawer then stands on screen with the conversation in it, Escape closes
    it, and it is open again on the next page since the conversation is not over. A text
    the conversation offers on a page without a sheet opens the reader itself."""
    html = library_page(TOKEN)

    def answer(route, request):
        u = request.url
        if "/chat/list" in u:
            body = {
                "chats": [],
                "usable": True,
                "talk": True,
                "chips": [{"id": "read", "line": "Find me something"}],
            }
        elif "/readers" in u:
            body = {"readers": [], "shared": [], "trash": [], "covers": False}
        elif "/account/me" in u or "/account/follows" in u:
            body = {"signedIn": False}
        elif "/series" in u:
            body = {"series": []}
        elif "/words/common" in u:
            body = {"words": [], "offset": 0, "next": None}
        elif "/reader/" in u:
            route.fulfill(
                status=200, content_type="text/html", body="<html><body>the reader</body></html>"
            )
            return
        elif "embed=1" in u:
            route.fulfill(status=200, content_type="text/html", body=chat_page(TOKEN, embed=True))
            return
        elif "/library" in u:
            route.fulfill(status=200, content_type="text/html", body=html)
            return
        else:
            body = {}
        route.fulfill(status=200, content_type="application/json", body=json.dumps(body))

    context = browser.new_context(viewport={"width": width, "height": 800})
    page = context.new_page()
    page.route("http://learn.test/**", answer)
    page.goto(f"http://learn.test/library?k={TOKEN}")
    page.wait_for_selector("#talk-open")
    measure = """() => {
      const pill = document.getElementById('talk-open').getBoundingClientRect();
      const drawer = document.getElementById('talk-drawer');
      const box = drawer.getBoundingClientRect();
      return {
        pill: { left: pill.left, right: pill.right, top: pill.top, bottom: pill.bottom },
        pillShown: getComputedStyle(document.getElementById('talk-open')).display !== 'none',
        open: !drawer.hidden,
        drawer: { left: box.left, right: box.right, top: box.top, bottom: box.bottom },
        loaded: !!document.getElementById('talk-frame').getAttribute('src'),
        remembered: localStorage.getItem('targum:talk'),
      };
    }"""
    before = page.evaluate(measure)
    page.click("#talk-open")
    page.frame_locator("#talk-frame").locator(".chat-ask").first.wait_for()
    # Past the drawer's own settling, which is the one motion it has.
    page.wait_for_timeout(300)
    opened = page.evaluate(measure)
    page.keyboard.press("Escape")
    page.wait_for_timeout(300)
    closed = page.evaluate(measure)
    page.click("#talk-open")
    page.goto(f"http://learn.test/library?k={TOKEN}")
    page.wait_for_selector("#talk-open", state="attached")
    page.wait_for_timeout(200)
    again = page.evaluate(measure)
    # A text offered where there is no sheet: the reader itself.
    page.frame_locator("#talk-frame").locator(".chat-ask").first.wait_for()
    frame = [f for f in page.frames if "embed=1" in f.url][0]
    frame.evaluate(
        "() => window.parent.postMessage("
        "{type: 'targum:open', reader: 'negev-he/reader/index.html'}, location.origin)"
    )
    page.wait_for_url("**/reader/negev-he/**", timeout=5000)
    context.close()
    assert before["pillShown"] and not before["open"] and not before["loaded"], before
    assert 0 <= before["pill"]["left"] and before["pill"]["right"] <= width, "the pill on screen"
    assert 0 <= before["pill"]["top"] and before["pill"]["bottom"] <= 800
    assert opened["open"] and opened["loaded"] and not opened["pillShown"], opened
    assert 0 <= opened["drawer"]["left"] and opened["drawer"]["right"] <= width + 1, opened
    assert 0 <= opened["drawer"]["top"] and opened["drawer"]["bottom"] <= 800 + 1, opened
    assert not closed["open"] and closed["pillShown"] and closed["remembered"] is None
    assert again["open"] and again["remembered"] == "open", "open again on the next page"


@pytest.mark.parametrize("width", [320, 390, 1440])
def test_the_pages_in_front_of_the_door_stand_on_the_desk(browser, tmp_path: Path, width) -> None:
    """Sign-in, the holding page, its 404 and What's built were paper with serif headings
    while everything behind the door is the desk (targum-internal#276). Each is on the
    ground in the chrome's face now; none scrolls sideways; and a footer item is never
    broken across two lines — "AGPL-3.0" stood on a line of its own on sign-in."""
    pages = {
        "signin": signin_page(),
        "holding": holding_page(),
        "missing": not_found_page(),
        "about": about_page(),
    }
    context = browser.new_context(viewport={"width": width, "height": 800})
    seen = {}
    for name, html in pages.items():
        page_file = tmp_path / f"{name}.html"
        page_file.write_text(html, encoding="utf-8")
        open_page = context.new_page()
        open_page.goto(page_file.as_uri())
        open_page.wait_for_timeout(100)
        seen[name] = open_page.evaluate(
            """() => {
              const body = getComputedStyle(document.body);
              const ground = getComputedStyle(document.documentElement)
                .getPropertyValue('--ground').trim();
              const probe = document.createElement('i');
              probe.style.color = ground;
              document.body.append(probe);
              const groundRgb = getComputedStyle(probe).color;
              return {
                ground: body.backgroundColor === groundRgb,
                face: body.fontFamily.includes('Source Sans 3'),
                sideways: document.documentElement.scrollWidth > window.innerWidth + 1,
                split: [...document.querySelectorAll('.foot > *')]
                  .filter((el) => el.getClientRects().length > 1).map((el) => el.textContent),
              };
            }"""
        )
        open_page.close()
    context.close()
    for name, got in seen.items():
        assert got == {"ground": True, "face": True, "sideways": False, "split": []}, (
            f"{name} at {width}px: {got}"
        )


def test_the_command_palette_finds_a_text_and_goes_there(browser) -> None:
    """2026-09-11: ⌘K opens one field; typing narrows it to places, texts on the shelf,
    the catalogue's rows and conversations; arrows move and Enter goes. A text opens its
    reader, and Escape closes the palette with nothing chosen."""
    html = library_page(TOKEN)

    def answer(route, request):
        u = request.url
        if "/chat/list" in u:
            body = {"chats": [{"id": "c9", "title": "שיחה על ספרים", "seen": 1}], "usable": True}
        elif "/readers" in u:
            body = {
                "readers": [
                    {
                        "name": "mendele-he",
                        "title": "מסעות בנימין",
                        "language": "he",
                        "document": "h1",
                        "built": 1,
                    }
                ],
                "shared": [],
                "trash": [],
                "covers": False,
            }
        elif "/reader/" in u:
            route.fulfill(
                status=200, content_type="text/html", body="<html><body>the reader</body></html>"
            )
            return
        elif "/account/me" in u or "/account/follows" in u:
            body = {"signedIn": False}
        elif "/series" in u:
            body = {"series": []}
        elif "embed=1" in u:
            route.fulfill(status=200, content_type="text/html", body=chat_page(TOKEN, embed=True))
            return
        elif "/library" in u:
            route.fulfill(status=200, content_type="text/html", body=html)
            return
        else:
            body = {}
        route.fulfill(
            status=200, content_type="application/json", body=json.dumps(body, ensure_ascii=False)
        )

    context = browser.new_context(viewport={"width": 1280, "height": 800})
    page = context.new_page()
    page.route("http://learn.test/**", answer)
    page.goto(f"http://learn.test/library?k={TOKEN}")
    page.wait_for_selector("#palette-open")
    assert page.evaluate("() => document.getElementById('palette').hidden")
    page.keyboard.press("Meta+k")
    page.wait_for_function("() => !document.getElementById('palette').hidden")
    page.wait_for_function("() => document.querySelectorAll('.palette-row').length > 0")
    at_rest = page.evaluate(
        "() => [...document.querySelectorAll('.palette-title')].map((t) => t.textContent)"
    )
    assert at_rest[:3] == ["Learn", "Library", "Your Progress"], "the places, with nothing typed"
    page.keyboard.press("Escape")
    assert page.evaluate("() => document.getElementById('palette').hidden"), "Escape closes it"
    page.click("#palette-open")
    page.wait_for_function("() => !document.getElementById('palette').hidden")
    page.fill("#palette-find", "בנימין")
    page.wait_for_function(
        "() => [...document.querySelectorAll('.palette-title')]"
        ".some((t) => t.textContent.includes('בנימין'))"
    )
    found = page.evaluate(
        "() => [...document.querySelectorAll('.palette-row')].map((r) => r.textContent)"
    )
    assert any("Your shelf" in row for row in found), found
    page.keyboard.press("Enter")
    page.wait_for_url("**/reader/mendele-he/**", timeout=5000)
    context.close()
