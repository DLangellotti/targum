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
import re
from pathlib import Path
from urllib.parse import urlparse

import pytest

from targum.render.builder import (
    LISTS,
    about_page,
    add_page,
    chat_page,
    holding_page,
    library_page,
    list_page,
    not_found_page,
    playlists_page,
    progress_page,
    signin_page,
    subscription_page,
    tanakh_map_page,
    welcome_page,
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
        "welcome": welcome_page(TOKEN),
        "library": library_page(TOKEN),
        "playlists": playlists_page(TOKEN),
        "subscription": subscription_page(TOKEN),
        "progress": progress_page(TOKEN),
        "tanakh": tanakh_map_page(TOKEN),
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


def test_a_library_card_holds_together_at_phone_width(browser, tmp_path: Path) -> None:
    """A text carries a scene label, a chip, a Hebrew title and an English one. At 390px
    the chip takes a line of its own under the Hebrew, and the Hebrew title never breaks
    across lines — a title in two pieces reads as two titles.

    Measured on the card, which is what the page opens in since 2026-09-17 (design.md
    §12) and so what a phone actually shows. It measured the table's row until then, and
    the row is still there behind List view; what this is really pinning is the phone,
    and the phone gets cards.
    """
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
    # The list, which is behind See all since the Library landed on its shelves
    # (design.md §12, 2026-10-09): sent to the scene, as Learn's links were, so its
    # shelf is open and the card is in the list.
    open_page.goto("http://targum.test/library#scene-01-nice-to-meet-you")
    open_page.wait_for_timeout(500)
    measured = open_page.evaluate(
        """() => {
          const row = document.querySelector('[data-row="scene-01-nice-to-meet-you"]');
          if (!row) return { missing: true };
          const bdi = row.querySelector('.card-title');
          const chip = row.querySelector('.row-next');
          if (!bdi) return { missing: true };
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

    assert not measured.get("missing"), "the shared scene has a card"
    assert measured["titleLines"] == 1, "the Hebrew title never breaks"
    assert measured["chipText"] == "Start here"
    assert measured["chipBelow"] is True, "the chip sits on its own line under the title"
    assert measured["width"] <= 390, "and the page does not scroll sideways"


@pytest.mark.parametrize("width", [320, 390, 430, 540])
def test_the_header_holds_its_corners_at_phone_width(browser, tmp_path: Path, width: int) -> None:
    """On a phone the header is one line — the name at one corner and the bell and the
    account at the other, find in the account's sheet since 2026-09-14 (design.md §13;
    the light switch that sat beside it left on 2026-09-19) — and the four places are a bar at the
    foot of the window (phase 4, 2026-09-11), flush with its edges. They used to sit
    under the name, and before that indented under it with Upload cut off at the edge:
    a cascade bug is invisible in the file and obvious on a phone, which is why this is
    measured rather than read."""
    page_file = tmp_path / "home.html"
    page_file.write_text(list_page(TOKEN, "texts"), encoding="utf-8")
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
            barFind: shown('.site-head-row > .palette-open'),
            anySwitch: !!document.querySelector('[data-theme-toggle]'),
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
    assert measured["barFind"] == "none", measured
    assert not measured["anySwitch"], "there is one look, and no switch for another"
    assert measured["noUpload"], "Upload left the corner on 2026-09-06: it is the + on the box"
    assert measured["cut"] == [], "all four places are read whole, Add among them (2026-09-13)"
    assert measured["width"] <= width, "and the page does not scroll sideways"


@pytest.mark.parametrize("width", [320, 360, 384, 412])
def test_a_signed_in_header_fits_a_phone(browser, width: int) -> None:
    """Signed in, with two languages, the bar holds the name, the language, find, the
    bell and the account. It was 385px wide whatever the screen, so a
    phone narrower than that scrolled sideways; the account was squashed into an oval;
    and the language's chevron stood outside its pill, its `::after` taken by the reach
    `reader.css` gives the button on a touch screen (2026-09-14)."""
    html = list_page(TOKEN, "texts")

    def answer(route, request):
        u = request.url
        if "/account/me" in u:
            # The two languages said by the account as well as by this browser, as the
            # server always says them (2026-10-07, targum-internal#425). Without them
            # `sync.js` mirrored `me.learning || []` over the init script's two, so the
            # menu was drawn twice: with two by the nav's own default at load, visible,
            # and again by Learn once the shelf answered, with one and hidden. Which of
            # the two the wait below met was a matter of timing, and on a slow runner it
            # met the second and waited 30 s for a button that never shows.
            body = {
                "signedIn": True,
                "email": "d@x.test",
                "initials": "DJ",
                "language": "he",
                "learning": ["he", "it"],
            }
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
        "localStorage.setItem('targum:language', 'he');"
        "sessionStorage.setItem('targum:arrival-over', '1');"
    )
    page.route("http://learn.test/**", answer)
    page.goto(f"http://learn.test/learn?k={TOKEN}")
    page.wait_for_selector(".account > button.avatar")
    # Home's own menu, not the nav's default drawn before it: the waiting line is hidden
    # once the shelf is drawn, so once it is gone the menu measured is the last one.
    page.wait_for_selector("#home-waiting", state="hidden")
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
            worn: (open.querySelector('.lang-status') || {}).textContent || '',
            listed: [...document.querySelectorAll('.lang-panel [role="menuitemradio"]')].map(
              (item) => [item.getAttribute('data-code'),
                         (item.querySelector('.lang-status') || {}).textContent || '']),
          };
        }"""
    )
    context.close()
    assert got["inner"] == width and got["scrollWidth"] <= width, f"sideways at {width}px: {got}"
    assert got["chevronDrawn"] and got["flag"], f"the chevron in its pill: {got}"
    assert got["round"], f"the account is a circle: {got}"
    # How far along each language is, a badge and nothing more (design.md §12, 2026-10-09).
    assert got["worn"] == "Beta", got
    assert got["listed"] == [["he", "Beta"], ["it", "Alpha"]], got


def _arrival_page(
    browser,
    width: int,
    height: int = 667,
    language: str | None = "English",
    locale: str = "ru-RU",
):
    """The arrival for a brand-new account on a shelf of three, at a phone's size.

    A brand-new account whose browser gives a sign of Russian is asked which language it
    reads before anything else (design.md §12, 2026-09-20 and 2026-09-28), so the page
    handed back is the one after that answer — the subjects — unless `language` is None,
    which leaves it on the first screen for the test that is about it. The browser says
    Russian unless `locale` says otherwise; with no sign, nothing is asked and the page
    starts on the subjects."""
    html = welcome_page(TOKEN)
    shelf = [
        {
            "name": name, "document": name, "entry": name, "title": title, "language": "he",
            "register": "modern", "kind": "article", "tags": ["sport"], "difficulty": hard,
            "sections": 1, "chapters": [], "readyChapters": 0, "built": 1, "opened": 0,
            "drawn": True,
        }
        for name, title, hard in (("easy", "קל", 5), ("mid", "בינוני", 20), ("hard", "קשה", 45))
    ]  # fmt: skip
    went: list[str] = []

    def answer(route, request):
        u = request.url
        if "/reader/" in u:
            went.append(u)
            return route.fulfill(status=200, content_type="text/html", body="<p>reader</p>")
        if request.resource_type == "document":
            return route.fulfill(status=200, content_type="text/html", body=html)
        if "/account/me" in u:
            body = {"signedIn": True, "email": "new@x.test", "initials": "N", "language": "he"}
        elif "/readers" in u:
            body = {"readers": [], "shared": shelf, "trash": [], "covers": False}
        else:
            body = {}
        route.fulfill(status=200, content_type="application/json", body=json.dumps(body))

    context = browser.new_context(
        viewport={"width": width, "height": height},
        is_mobile=True,
        has_touch=True,
        locale=locale,
    )
    page = context.new_page()
    page.route("http://learn.test/**", answer)
    page.goto(f"http://learn.test/welcome?k={TOKEN}")

    def past_welcome() -> None:
        # The welcome (2026-09-28) asks nothing; these tests are about what comes after
        # it, so they go on the way a reader does, with Continue.
        page.wait_for_selector("#arrival-welcome:not([hidden])")
        page.locator("#arrival-done").tap()

    if not locale.startswith("ru"):
        past_welcome()
        page.wait_for_selector("#arrival-subjects:not([hidden]) .arrival-door")
        page.wait_for_timeout(150)
        return context, page, went
    page.wait_for_selector("#arrival-language:not([hidden]) .arrival-rung")
    if language is not None:
        page.locator("#arrival-tongues .arrival-rung", has_text=language).tap()
        past_welcome()
        page.wait_for_selector("#arrival-subjects:not([hidden]) .arrival-door")
    page.wait_for_timeout(150)
    return context, page, went


ARRIVAL_MEASURE = """() => {
  const seen = (el) => {
    if (!el || el.hidden) return false;
    const box = el.getBoundingClientRect();
    return box.width > 0 && box.height > 0 && getComputedStyle(el).visibility !== 'hidden';
  };
  // In the page itself: the pill at the corner is the chrome's, and is on every page.
  const filled = [...document.querySelectorAll('main button, main a')].filter((el) => {
    if (!seen(el)) return false;
    const paint = getComputedStyle(el).backgroundColor;
    return paint === 'rgb(31, 111, 107)';  // the primary, filled (§13)
  });
  const foot = document.querySelector('.arrival-foot').getBoundingClientRect();
  const doors = [...document.querySelectorAll('.arrival-door')]
    .map((d) => d.getBoundingClientRect());
  return {
    filled: filled.map((el) => el.id || el.className),
    footInView: foot.top >= 0 && foot.bottom <= window.innerHeight,
    footFixed: getComputedStyle(document.querySelector('.arrival-foot')).position,
    rows: new Set(doors.map((d) => Math.round(d.top))).size,
    short: doors.every((d) => d.height >= 43.5),
    cards: seen(document.querySelector('.learn-cards')),
    pill: seen(document.querySelector('.talk-cta')),
    pillClear: (() => {
      const pill = document.querySelector('.talk-cta').getBoundingClientRect();
      return [...document.querySelectorAll('.arrival-foot > *')].every((el) => {
        const box = el.getBoundingClientRect();
        return box.width === 0 || box.right <= pill.left || box.left >= pill.right;
      });
    })(),
    sideways: document.documentElement.scrollWidth > window.innerWidth,
    skip: seen(document.getElementById('arrival-skip')),
    nextOff: document.getElementById('arrival-done').disabled,
  };
}"""


@pytest.mark.parametrize("width", [320, 375, 412])
def test_the_arrival_is_the_screen_on_a_phone(browser, width: int) -> None:
    """targum-internal#334. A new reader's first screen on a phone was nineteen full-width
    rows with the only filled button on the page below all of them, disabled, and no way
    past but to answer. It is the screen now: the question, the subjects wrapped as
    pills, and Next and Skip at the foot of the window where a thumb is.

    Measured in a browser because none of this is visible in the file — it is a cascade,
    a fixed foot and a wrap, and the last notes' bugs were all found by opening the page.
    """
    context, page, _ = _arrival_page(browser, width)
    got = page.evaluate(ARRIVAL_MEASURE)
    context.close()
    assert got["footFixed"] == "fixed" and got["footInView"], got
    assert got["skip"] and got["nextOff"], "Skip is live from the start; Next waits for three"
    assert got["filled"] == [], f"nothing filled competes while Next is asleep: {got['filled']}"
    assert got["rows"] < 19, f"the subjects wrap, they do not stack: {got['rows']} rows"
    assert got["short"], "and every one of them is a thumb's height"
    assert not got["cards"], "no other text is drawn while it is up"
    # §13: the pill is on every page. The foot stops short of it rather than putting it away.
    assert got["pill"] and got["pillClear"], got
    assert not got["sideways"]


def test_the_arrival_leads_into_a_text_in_six_presses(browser) -> None:
    """A language, three subjects, Next, a rung — and the reader is open, at the rung
    they named. Not Learn again with a card to find (design.md §12, 2026-09-19; five
    presses until the language was asked first, 2026-09-20)."""
    context, page, went = _arrival_page(browser, 375)
    for label in ("Sport", "History", "Art"):
        page.locator(".arrival-door", has_text=label).first.tap()
    # A press fades in over `--in`; measured mid-fade, Next is still transparent.
    page.wait_for_timeout(400)
    woke = page.evaluate(ARRIVAL_MEASURE)
    assert woke["filled"] == ["arrival-done"], (
        f"three picked, and Next is the one filled press: {woke}"
    )
    page.locator("#arrival-done").tap()
    page.wait_for_selector("#arrival-level:not([hidden]) .arrival-rung")
    second = page.evaluate(
        """() => ({
          step: document.getElementById('arrival-step').textContent,
          rungs: document.querySelectorAll('#arrival-levels .arrival-rung').length,
          asked: document.getElementById('arrival-asks-level').getBoundingClientRect().top
                 >= document.querySelector('.site-head').getBoundingClientRect().bottom - 1,
          fits: document.querySelector('.arrival-levels').getBoundingClientRect().bottom
                <= document.querySelector('.arrival-foot').getBoundingClientRect().top + 1
                || document.documentElement.scrollHeight > window.innerHeight,
        })"""
    )
    assert second["step"] == "3 of 3" and second["rungs"] == 8 and second["fits"], second
    assert second["asked"], "the second question starts at its top, not where the first was left"
    page.locator(".arrival-rung", has_text="I follow almost anything").tap()
    page.wait_for_timeout(300)
    context.close()
    assert went and "/reader/hard" in went[-1], f"hey opens the hardest sport text: {went}"


LANGUAGE_MEASURE = """() => {
  const foot = document.querySelector('.arrival-foot').getBoundingClientRect();
  const rows = [...document.querySelectorAll('#arrival-tongues .arrival-rung')];
  const seen = (el) => !!el && !el.hidden && el.getBoundingClientRect().width > 0;
  const pill = document.querySelector('.talk-cta').getBoundingClientRect();
  return {
    step: document.getElementById('arrival-step').textContent,
    rows: rows.map((row) => row.textContent),
    spoken: rows.map((row) => row.getAttribute('lang')),
    asks: [...document.querySelectorAll('#arrival-asks-language span')].map((s) => s.textContent),
    tall: rows.every((row) => row.getBoundingClientRect().height >= 43.5),
    footInView: foot.top >= 0 && foot.bottom <= window.innerHeight,
    rowsClearOfFoot: rows.every((row) => row.getBoundingClientRect().bottom <= foot.top + 1),
    skip: seen(document.getElementById('arrival-skip')),
    back: seen(document.getElementById('arrival-back')),
    next: seen(document.getElementById('arrival-done')),
    subjects: seen(document.getElementById('arrival-subjects')),
    pillClear: [...document.querySelectorAll('.arrival-foot > *')].every((el) => {
      const box = el.getBoundingClientRect();
      return box.width === 0 || box.right <= pill.left || box.left >= pill.right;
    }),
    sideways: document.documentElement.scrollWidth > window.innerWidth,
  };
}"""


@pytest.mark.parametrize("width", [320, 375, 412])
def test_the_arrival_asks_which_language_first_on_a_phone(browser, width: int) -> None:
    """design.md §12, 2026-09-20. The first screen a new reader meets is the one they can
    read whatever they read: the question a line a language, a row each in its own name,
    and nothing else to press but Skip."""
    context, page, _ = _arrival_page(browser, width, language=None)
    got = page.evaluate(LANGUAGE_MEASURE)
    context.close()
    assert got["step"] == "1 of 3", got
    assert got["rows"] == ["English", "Русский", "Other · Другой"], got
    # Each language's row says which language it is in; the last is in both, and says none.
    assert got["spoken"] == ["en", "ru", None], got
    assert len(got["asks"]) == 2, f"asked once in each language: {got['asks']}"
    assert got["tall"] and got["rowsClearOfFoot"] and got["footInView"], got
    assert got["skip"] and not got["back"] and not got["next"], got
    assert not got["subjects"], "one question a screen"
    assert got["pillClear"] and not got["sideways"], got


def _progress_with(browser, totals: dict, reading: dict | None = None, width: int = 390):
    from datetime import date, timedelta

    from targum.render.builder import progress_page

    html = progress_page(TOKEN)
    today = date.today()

    def row(day: date, language: str, medium: str, **amounts: int) -> dict[str, object]:
        base = {"listened": 0, "watched": 0, "words": 0}
        return {"day": str(day), "language": language, "medium": medium, **base, **amounts}

    rows = [
        row(today, "he", "listen", listened=5700),
        row(today, "he", "watch", watched=1500),
        row(today - timedelta(days=60), "he", "read", words=12400),
        row(today, "ru", "read", words=999),
    ]
    said = {"signedIn": True, "kept": True, "on": True, "totals": rows, **totals}

    def answer(route, request):
        if request.resource_type == "document":
            return route.fulfill(status=200, content_type="text/html", body=html)
        body = said if "/account/totals" in request.url else {}
        if "/account/reading" in request.url and reading is not None:
            body = {"signedIn": True, "reading": reading}
        route.fulfill(status=200, content_type="application/json", body=json.dumps(body))

    context = browser.new_context(viewport={"width": width, "height": 844})
    page = context.new_page()
    page.add_init_script(
        "localStorage.setItem('targum:vocab:he', JSON.stringify({a: {surface: 'a', status: 9,"
        " band: 'easy', at: 1}})); localStorage.setItem('targum:language', 'he')"
    )
    page.route("http://progress.test/**", answer)
    page.goto(f"http://progress.test/progress?k={TOKEN}")
    page.wait_for_timeout(600)
    return context, page


SPENT = """() => ({
  shown: !document.getElementById('spent').hidden,
  off: !document.getElementById('spent-off').hidden,
  figures: [...document.querySelectorAll('.spent-figure')].map(
    (f) => [...f.children].map((c) => c.textContent).join(' ')
  ),
  sideways: document.documentElement.scrollWidth > window.innerWidth,
})"""


def test_progress_says_time_listened_watched_and_words_read_and_narrows_them(browser) -> None:
    """targum-internal#339: "track hours/minutes listened/watched + words read… displayed
    and filterable on Progress." Read off the account's own record, in the page's language
    (the Russian row is not counted here), in hours and minutes and words — no invented
    unit — and a figure that is nought is not drawn."""
    context, page = _progress_with(browser, {})
    everything = page.evaluate(SPENT)
    page.locator("#spent-medium .chip", has_text="Watching").click()
    watching = page.evaluate(SPENT)
    page.locator("#spent-medium .chip", has_text="Everything").click()
    page.locator("#spent-period .chip", has_text="Last 7 days").click()
    lately = page.evaluate(SPENT)
    context.close()

    assert everything["shown"] and not everything["sideways"]
    assert everything["figures"] == ["1 h 35 min listened", "25 min watched", "12,400 words read"]
    assert watching["figures"] == ["25 min watched"]
    assert lately["figures"] == ["1 h 35 min listened", "25 min watched"], (
        "the book was two months ago"
    )


def test_progress_draws_no_such_figures_where_there_is_no_record(browser) -> None:
    """Absent, not nought. Where the box keeps no record the panel is not drawn; where the
    reader has stopped theirs, one quiet line says why and where to start it again."""
    context, page = _progress_with(browser, {"kept": False, "totals": []})
    none = page.evaluate(SPENT)
    context.close()
    assert not none["shown"] and not none["off"]

    context, page = _progress_with(browser, {"on": False, "totals": []})
    stopped = page.evaluate(SPENT)
    context.close()
    assert not stopped["shown"] and stopped["off"]


READING = """() => {
  const panel = document.getElementById('reading');
  const svg = panel.querySelector('svg');
  const box = svg ? svg.getBoundingClientRect() : null;
  return {
    shown: !panel.hidden && panel.getBoundingClientRect().height > 0,
    points: panel.querySelectorAll('.reading-point').length,
    said: [...panel.querySelectorAll('.reading-words p')].map((p) => p.textContent),
    width: box ? box.width : 0,
    height: box ? box.height : 0,
    panelWidth: panel.getBoundingClientRect().width,
    sideways: document.documentElement.scrollWidth > window.innerWidth,
    rem: parseFloat(getComputedStyle(document.documentElement).fontSize),
    text: panel.textContent,
  };
}"""


@pytest.mark.parametrize("width", [390, 1280])
def test_progress_draws_what_you_knew_of_what_you_read_at_phone_and_desk(
    browser, width: int
) -> None:
    """targum-internal#291. Three months draw one line that fits the panel at a phone's
    width and stays a reading width on the desk; a fall is said in one sentence; nothing
    in the block is a percentage."""
    import os

    line = [
        {"month": "2026-06", "known": 70, "tokens": 100, "sections": 3},
        {"month": "2026-07", "known": 80, "tokens": 100, "sections": 5},
        {"month": "2026-08", "known": 55, "tokens": 100, "sections": 2},
    ]
    context, page = _progress_with(
        browser, {}, reading={"he": {"line": line, "months": 3, "sections": 10}}, width=width
    )
    got = page.evaluate(READING)
    shots = os.environ.get("TARGUM_SHOTS")
    if shots:
        page.locator("#reading").screenshot(path=f"{shots}/reading-{width}.png")
    context.close()

    assert got["shown"] and got["points"] == 3, got
    assert got["said"][0] == "In August you knew about 6 words in 10 of what you read."
    assert got["said"][1].startswith("It fell because"), got
    assert "%" not in got["text"]
    assert not got["sideways"], got
    assert 0 < got["width"] <= got["panelWidth"], got
    # 30rem, and the rem is §13's clamped one rather than 16px.
    assert got["width"] <= 30 * got["rem"] + 1, "held to a reading width on the desk"


def test_progress_says_what_would_draw_the_line_under_three_months(browser) -> None:
    context, page = _progress_with(
        browser, {}, reading={"he": {"line": [], "months": 1, "sections": 2}}
    )
    got = page.evaluate(READING)
    context.close()
    assert got["shown"] and got["points"] == 0, got
    assert got["said"] == [
        "We'll draw this once you've finished sections in three different months. Months so far: 1."
    ]


def test_a_deleted_text_says_where_it_went_and_can_be_undone_in_place(
    browser, tmp_path: Path
) -> None:
    """Delete sits beside Chapters, and a reload used to take the row away with Put back
    in a panel further down. The row stays, says it is in Trash, and Undo is where Delete
    was (targum-internal#278)."""
    page_file = tmp_path / "texts.html"
    page_file.write_text(list_page(TOKEN, "texts"), encoding="utf-8")
    chapters = [{"number": 1, "title": "א", "ready": True, "file": "1.html"}]
    readers = [
        {
            "name": name,
            "document": name,
            "title": title,
            "language": "he",
            "chapters": chapters,
            "readyChapters": 1,
            "sections": 1,
            "built": 1,
        }
        for name, title in (("jonah", "יונה"), ("ruth", "רות"))
    ]
    # Tall enough that the shelf under home's Continue is on screen without a scroll: a
    # scroll closes an open ⋯, which is right for a reader and not what this is about.
    context = browser.new_context(viewport={"width": 390, "height": 1600})
    open_page = context.new_page()
    # The page asks the server with fetch; this answers for it, and keeps what was posted
    # across the reload Undo ends with.
    open_page.add_init_script(
        f"const readers = {json.dumps(readers)};"
        """
        const said = (x) => Promise.resolve(new Response(JSON.stringify(x)));
        window.fetch = (url, opts) => {
          const path = String(url).split('?')[0];
          if (path.endsWith('/readers')) return said({ readers, trash: [] });
          if (path.endsWith('/trash') || path.endsWith('/restore')) {
            const posted = JSON.parse(sessionStorage.getItem('posted') || '[]');
            posted.push([path.split('/').pop(), JSON.parse(opts.body).name]);
            sessionStorage.setItem('posted', JSON.stringify(posted));
            return said({ ok: true });
          }
          return said({});
        };
        """
    )
    open_page.goto(page_file.as_uri())
    # Chapters and Delete are under the row's ⋯ since 2026-09-24 (design.md §12).
    open_page.wait_for_selector(".row-more")
    open_page.locator(".row-more").first.click()
    open_page.locator(".row-menu .open-chapters").click()
    open_page.locator(".row-more").first.click()
    open_page.locator(".row-menu .bin").click()
    open_page.wait_for_selector("li.binned")
    got = open_page.evaluate(
        """() => ({
          note: document.querySelector('li.binned .binned-note').textContent,
          focused: document.activeElement.textContent,
          tree: !!document.querySelector('.chapters'),
          rows: document.querySelectorAll('#library-list > li').length,
        })"""
    )
    assert got == {"note": "יונה is in Trash", "focused": "Undo", "tree": False, "rows": 2}
    # Undo reloads the page. Waiting on the navigation itself, not on a selector the old
    # page still matches, or the evaluate below can land in the middle of the reload.
    with open_page.expect_navigation():
        open_page.locator("li.binned .restore").click()
    open_page.wait_for_selector(".row-more")
    posted = open_page.evaluate("() => JSON.parse(sessionStorage.getItem('posted'))")
    context.close()
    assert posted == [["trash", "jonah"], ["restore", "jonah"]]


def test_the_bell_is_a_sheet_that_fits_a_phone(browser) -> None:
    """A long inbox on a phone ran off the top of the screen with Clear all above it, a
    failure's address ran past the edge, a line with nothing to open put its × in the
    Open column, and the round pill stood over the sheet (2026-09-14)."""
    html = list_page(TOKEN, "texts")
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
    # Home, past the arrival a new account would be sent to first (2026-10-08).
    page.add_init_script("sessionStorage.setItem('targum:arrival-over', '1');")
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
    page_file = tmp_path / "home.html"
    page_file.write_text(list_page(TOKEN, "texts"), encoding="utf-8")
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


def test_a_menu_chevron_points_down_in_either_direction(browser, tmp_path: Path) -> None:
    """A chevron drawn from two logical borders and a turn: under RTL the borders swap
    sides, so the same turn pointed the language menu's chevron sideways. (The doors'
    menu, which had one too, went with Learn on 2026-10-08.)"""
    page_file = tmp_path / "home.html"
    page_file.write_text(list_page(TOKEN, "texts"), encoding="utf-8")
    context = browser.new_context(viewport={"width": 1280, "height": 800})
    open_page = context.new_page()
    open_page.goto(page_file.as_uri())
    open_page.wait_for_timeout(300)
    pointing = open_page.evaluate(
        """() => {
          const out = {};
          for (const dir of ['ltr', 'rtl']) {
            const host = document.createElement('div');
            host.dir = dir;
            host.innerHTML = '<span class="lang-menu">'
              + '<button class="lang-open">Hebrew</button></span>';
            document.body.append(host);
            for (const [name, sel, pseudo] of [['lang', '.lang-open', '::before']]) {
              const st = getComputedStyle(host.querySelector(sel), pseudo);
              const on = (side) => parseFloat(st['border' + side + 'Width']) > 0;
              // The corner the two borders make, as a vector, then turned by the transform.
              const x = (on('Right') ? 1 : 0) - (on('Left') ? 1 : 0);
              const y = (on('Bottom') ? 1 : 0) - (on('Top') ? 1 : 0);
              const m = new DOMMatrix(st.transform === 'none' ? undefined : st.transform);
              out[name + ':' + dir] = [m.a * x + m.c * y, m.b * x + m.d * y];
            }
          }
          return out;
        }"""
    )
    context.close()
    for key, (x, y) in pointing.items():
        assert abs(x) < 0.01 and y > 1, f"{key} points down, not {(x, y)}"


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


def test_two_pictures_chosen_on_the_front_door_become_one_card(browser, tmp_path: Path) -> None:
    """The whole of what a reader does with a phone's worth of pages, on the client's
    side: two files chosen together in the drawer sit in the box as chips, Send takes them up
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
            route.fulfill(status=200, content_type="text/html", body=list_page(TOKEN, "texts"))
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
    open_page.add_init_script("sessionStorage.setItem('targum:arrival-over', '1');")
    open_page.route("http://learn.test/**", answer)
    open_page.goto("http://learn.test/")
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
    # The text opens the reader itself (2026-10-08): Learn's sheet, which held it beside
    # the conversation, went with Learn.
    open_page.wait_for_url("**/reader/negev-he/reader/index.html*", timeout=5000)
    landed = open_page.url
    context.close()

    assert chips == 2, "one chip a file"
    assert prepared and prepared[0]["uploads"] == ["u1", "u2"], prepared
    assert built == [{"id": "j1"}], "Send was the press"
    assert "/reader/negev-he/reader/index.html" in landed, landed


@pytest.mark.parametrize("width", [390, 1280])
def test_the_beit_midrash_opens_on_its_doors_and_two_presses_reach_ruth(
    browser, width: int
) -> None:
    """targum-internal#340, in a browser because both of its bugs were only visible in one.

    The first build hid the subject chips, the sorts and the Cards/List switch with the
    `hidden` attribute, and each of them is `display: flex`, which beats it — so the doors
    stood under three rows of controls with no list to act on. And a first visit opens
    All texts on the Scenes, which carried into the tree left every door empty.
    """
    html = library_page(TOKEN)

    def answer(route, request):
        if request.resource_type == "document":
            return route.fulfill(status=200, content_type="text/html", body=html)
        body: dict[str, object] = {}
        if "/readers" in request.url:
            body = {"readers": [], "shared": [], "trash": [], "covers": False, "catalogue": {}}
        elif "/jobs" in request.url:
            body = {"jobs": []}
        route.fulfill(status=200, content_type="application/json", body=json.dumps(body))

    context = browser.new_context(viewport={"width": width, "height": 844})
    page = context.new_page()
    page.route("http://library.test/**", answer)
    page.goto(f"http://library.test/library?k={TOKEN}#bm")
    page.wait_for_selector(".door-card")
    page.wait_for_timeout(300)
    at_doors = page.evaluate(
        """() => {
          const shown = (id) => {
            const el = document.getElementById(id);
            return !!el && getComputedStyle(el).display !== 'none';
          };
          const tops = [...document.querySelectorAll('.door-card')]
            .map((d) => Math.round(d.getBoundingClientRect().top));
          return {
            doors: [...document.querySelectorAll('.door-card')].map((d) => d.dataset.door),
            controls: ['subject-chips', 'subject-label', 'said', 'sorts', 'shape', 'crumbs']
              .filter(shown),
            texts: document.querySelectorAll('#cards .card-item').length,
            sameRow: tops.length > 1 && tops[0] === tops[1],
            on: document.querySelector('#where [aria-selected="true"]').textContent,
            sideways: document.documentElement.scrollWidth > window.innerWidth,
          };
        }"""
    )
    page.locator('.door-card[data-door="tanakh"]').click()
    page.wait_for_selector("#cards .card-item")
    inside = page.evaluate(
        """() => ({
          hash: location.hash,
          crumbs: document.getElementById('crumbs').innerText,
          titles: [...document.querySelectorAll('#cards .card-title')].map((t) => t.textContent),
          sorts: getComputedStyle(document.getElementById('sorts')).display !== 'none',
          map: (document.querySelector('#crumbs a.crumb-map') || {}).href || '',
          sideways: document.documentElement.scrollWidth > window.innerWidth,
        })"""
    )
    page.locator("#crumbs button").click()
    page.wait_for_selector(".door-card")
    back = page.evaluate("() => location.hash")
    context.close()

    assert at_doors["on"] == "Beit Midrash" and at_doors["doors"] == ["tanakh", "targum"]
    assert at_doors["controls"] == [], f"nothing that narrows a list there is not: {at_doors}"
    assert at_doors["texts"] == 0 and at_doors["sameRow"] and not at_doors["sideways"], at_doors
    assert inside["hash"] == "#bm/tanakh" and "Tanakh" in inside["crumbs"], inside
    assert "רות" in inside["titles"], "the tab, then Tanakh, and Ruth is on the page"
    assert inside["sorts"], "and inside a door the list has its sorts back"
    assert "/tanakh-map" in inside["map"], "the Tanakh door leads on to its map (#144)"
    assert not inside["sideways"], inside
    assert back == "#bm"


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


def test_the_drawer_speaks_the_language_of_the_page_holding_it(browser) -> None:
    """The drawer's frame loads once and stays up, and home switches language in place.
    The conversation read the language for itself as it loaded, so it was one switch
    behind the page: Italian under a Hebrew header, "Write in Hebrew" under an Italian
    one (2026-09-14). It follows the page now, as it opens and after."""
    html = list_page(TOKEN, "texts")
    asked: list[str] = []

    def answer(route, request):
        u = request.url
        if "embed=1" in u:
            route.fulfill(status=200, content_type="text/html", body=chat_page(TOKEN, embed=True))
            return
        if "/chat/list" in u:
            asked.append(u.split("language=")[1].split("&")[0] if "language=" in u else "")
            body: dict = {"chats": [], "usable": True, "talk": True, "chips": []}
        elif "/readers" in u:
            body = {"readers": [], "shared": [], "trash": []}
        elif "/account/me" in u:
            body = {"signedIn": False}
        elif "/words/common" in u:
            body = {"words": [], "offset": 0, "next": None, "into": "en"}
        elif u.split("?")[0].endswith("/learn"):
            route.fulfill(status=200, content_type="text/html", body=html)
            return
        else:
            body = {}
        route.fulfill(status=200, content_type="application/json", body=json.dumps(body))

    context = browser.new_context(viewport={"width": 390, "height": 844})
    page = context.new_page()
    page.add_init_script(
        "localStorage.setItem('targum:learning', JSON.stringify(['he', 'it']));"
        "localStorage.setItem('targum:language', 'he');"
        "sessionStorage.setItem('targum:arrival-over', '1');"
    )
    page.route("http://learn.test/**", answer)
    page.goto(f"http://learn.test/learn?k={TOKEN}")
    page.wait_for_timeout(300)
    page.click("#talk-open")
    talk = page.frame_locator("#talk-frame")
    field = talk.locator("#say")
    field.wait_for()
    page.wait_for_timeout(300)
    hebrew = field.get_attribute("placeholder")
    # The page changes language in place, the way Learn's menu does.
    page.evaluate("() => window.TargumLang.remember('it')")
    page.wait_for_timeout(400)
    italian = field.get_attribute("placeholder")
    context.close()
    assert hebrew == "Write in Hebrew or English", hebrew
    assert italian == "Write in Italian or English", italian
    # Learn asks for its own chips without a language; the drawer asks in the page's.
    assert [code for code in asked if code] == ["he", "it"], asked


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
    assert at_rest[:3] == ["Your targums", "Library", "Your Progress"], (
        "the places, with nothing typed, in the nav's order"
    )
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
    assert any("Yours" in row for row in found), found
    page.keyboard.press("Enter")
    page.wait_for_url("**/reader/mendele-he/**", timeout=5000)
    context.close()


#: What `/describe` says about a link, in the shape `chat.tools._describe` returns.
FOUND = {
    "kind": "video",
    "title": "מה קרה היום",
    "seconds": 754,
    "hebrew_subtitles": False,
    "advice": ["No written Hebrew subtitles: the recording would be transcribed."],
    "licence": "standard YouTube licence",
    "known_share": 0.7,
}


def test_a_pasted_link_says_what_was_found_before_it_says_the_price(
    browser, tmp_path: Path
) -> None:
    """targum-internal#250. The box showed a price and a title and nothing about what
    was being bought. `describe_source` has read this for the model since #126; the page
    asks it now, and says it while `/prepare` is still fetching."""
    html = add_page(TOKEN)
    order: list[str] = []
    let_price_through: list[object] = []

    def answer(route, request):
        if "/describe" in request.url:
            order.append("describe")
            route.fulfill(status=200, content_type="application/json", body=json.dumps(FOUND))
        elif "/prepare" in request.url:
            order.append("prepare")
            let_price_through.append(request.post_data_json)
            route.fulfill(status=200, content_type="application/json", body=json.dumps(PRICED))
        elif request.url.endswith(("/add", "/add.html")):
            route.fulfill(status=200, content_type="text/html", body=html)
        else:
            route.fulfill(status=200, content_type="application/json", body="{}")

    context = browser.new_context(viewport={"width": 1280, "height": 900})
    open_page = context.new_page()
    open_page.route("http://add.test/**", answer)
    open_page.goto("http://add.test/add")
    open_page.fill("#given", "https://www.youtube.com/watch?v=abc")
    open_page.click("#go")
    open_page.wait_for_selector(".found", timeout=4000)
    found_text = open_page.inner_text(".found")
    open_page.wait_for_timeout(400)
    still_there = open_page.is_visible(".found")
    context.close()

    assert order[:2] == ["describe", "prepare"], "what it is, before what it costs"
    assert "What we found" in found_text
    assert "12:34" in found_text, "the length, as a clock"
    assert "standard YouTube licence" in found_text
    assert "No written Hebrew subtitles" not in found_text, (
        "the advice is written for the model: English, Hebrew-only, and it says the cost "
        "the card says again (2026-10-01)"
    )
    assert "7 words in 10" in found_text, "how much of it the reader already has"
    assert still_there, "the price is drawn under what was found, not over it"
    assert let_price_through, "the price still follows"


def test_what_was_found_still_says_the_price_is_coming(browser, tmp_path: Path) -> None:
    """`/prepare` can take minutes on a video. What was found used to replace the
    waiting line, so the reader saw a finished-looking card with nothing to press and
    nothing saying more was on its way."""
    html = add_page(TOKEN)

    def answer(route, request):
        if "/describe" in request.url:
            route.fulfill(status=200, content_type="application/json", body=json.dumps(FOUND))
        elif "/prepare" in request.url:
            return  # held open: the price has not arrived yet
        elif request.url.endswith(("/add", "/add.html")):
            route.fulfill(status=200, content_type="text/html", body=html)
        else:
            route.fulfill(status=200, content_type="application/json", body="{}")

    context = browser.new_context(viewport={"width": 1280, "height": 900})
    open_page = context.new_page()
    open_page.route("http://add.test/**", answer)
    open_page.goto("http://add.test/add")
    open_page.fill("#given", "https://www.youtube.com/watch?v=abc")
    open_page.click("#go")
    open_page.wait_for_selector(".found", timeout=4000)
    status = open_page.inner_text("#status")
    context.close()

    assert "What we found" in status
    assert "We're reading it" in status, "the waiting line stays under what was found"
    assert status.index("What we found") < status.index("We're reading it")


def test_progress_without_a_total_says_no_percentage(browser, tmp_path: Path) -> None:
    """A stage can count what it has done before it knows the total, and done over a
    total of nothing was drawn as "Infinity%"."""
    html = add_page(TOKEN)

    def answer(route, request):
        if "/describe" in request.url:
            route.fulfill(status=500, content_type="application/json", body="{}")
        elif "/prepare" in request.url:
            route.fulfill(status=200, content_type="application/json", body=json.dumps(PRICED))
        elif "/job/" in request.url:
            body = {"stage": "transcribe", "done": 3, "total": 0, "message": ""}
            route.fulfill(status=200, content_type="application/json", body=json.dumps(body))
        elif request.url.endswith(("/add", "/add.html")):
            route.fulfill(status=200, content_type="text/html", body=html)
        else:
            route.fulfill(status=200, content_type="application/json", body="{}")

    context = browser.new_context(viewport={"width": 1280, "height": 900})
    open_page = context.new_page()
    open_page.route("http://add.test/**", answer)
    open_page.goto("http://add.test/add")
    open_page.fill("#given", "https://www.youtube.com/watch?v=abc")
    open_page.click("#go")
    open_page.click("#status button.filled", timeout=4000)
    open_page.wait_for_selector("#status .bar", timeout=4000)
    open_page.wait_for_timeout(1200)  # past the first poll
    status = open_page.inner_text("#status")
    context.close()

    assert "Infinity" not in status and "NaN" not in status, status
    assert "We're getting it ready" in status


def test_open_says_a_lost_build_and_is_pressed_once(browser, tmp_path: Path) -> None:
    """The card's title is isolated, so a Hebrew title keeps its facts after it rather
    than in front of it. And Open: one press while `/build` is answering, and the
    server's own sentence when the build was lost to a restart — it used to poll a job
    that no longer existed."""
    html = add_page(TOKEN)
    built: list[object] = []
    priced = dict(PRICED, title="זו מדינת אויב?")

    def answer(route, request):
        if "/describe" in request.url:
            route.fulfill(status=500, content_type="application/json", body="{}")
        elif "/prepare" in request.url:
            route.fulfill(status=200, content_type="application/json", body=json.dumps(priced))
        elif "/build" in request.url:
            built.append(request.post_data_json)
            lost = {"error": "We lost that build when we restarted."}
            route.fulfill(status=404, content_type="application/json", body=json.dumps(lost))
        elif request.url.endswith(("/add", "/add.html")):
            route.fulfill(status=200, content_type="text/html", body=html)
        else:
            route.fulfill(status=200, content_type="application/json", body="{}")

    context = browser.new_context(viewport={"width": 1280, "height": 900})
    open_page = context.new_page()
    open_page.route("http://add.test/**", answer)
    open_page.goto("http://add.test/add")
    open_page.fill("#given", "https://www.youtube.com/watch?v=abc")
    open_page.click("#go")
    open_page.wait_for_selector("#status button.filled", timeout=4000)
    isolated = open_page.evaluate("() => !!document.querySelector('#status bdi > b')")
    open_page.evaluate(
        "() => { const b = document.querySelector('#status button.filled'); b.click(); b.click(); }"
    )
    open_page.wait_for_function(
        "() => document.getElementById('status').textContent.includes('lost that build')",
        timeout=4000,
    )
    context.close()

    assert isolated, "the title in a <bdi>"
    assert len(built) == 1, "two presses, one build"


def test_the_card_says_each_thing_once(browser, tmp_path: Path) -> None:
    """2026-10-01. The length was said by what was found and again beside the title; the
    line under the box promised the card while the card was up; and a text priced after
    a link was shown under the link's facts."""
    html = add_page(TOKEN)
    heard = dict(PRICED, title="זו מדינת אויב?", audio=True, seconds=754, parts=1)

    def answer(route, request):
        if "/describe" in request.url:
            route.fulfill(status=200, content_type="application/json", body=json.dumps(FOUND))
        elif "/prepare" in request.url:
            body = heard if request.post_data_json.get("source") else PRICED
            route.fulfill(status=200, content_type="application/json", body=json.dumps(body))
        elif request.url.endswith(("/add", "/add.html")):
            route.fulfill(status=200, content_type="text/html", body=html)
        else:
            route.fulfill(status=200, content_type="application/json", body="{}")

    context = browser.new_context(viewport={"width": 1280, "height": 900})
    open_page = context.new_page()
    open_page.route("http://add.test/**", answer)
    open_page.goto("http://add.test/add")
    open_page.fill("#given", "https://www.youtube.com/watch?v=abc")
    assert open_page.is_visible("#understood"), "the box says what it was given"
    open_page.click("#go")
    open_page.wait_for_selector("#status button.filled", timeout=4000)
    status = open_page.inner_text("#status")
    note_while_card = open_page.is_visible("#understood")

    open_page.fill("#given", "בארץ־ישראל קם העם היהודי, בה עוצבה דמותו הרוחנית.")
    note_after_edit = open_page.is_visible("#understood")
    open_page.click("#go")
    open_page.wait_for_function(
        "() => document.querySelector('#status button.filled') && "
        "!document.getElementById('status').textContent.includes('זו מדינת')",
        timeout=4000,
    )
    stale = open_page.is_visible("#status .found")
    context.close()

    assert status.count("12:34") == 1, status
    assert not note_while_card, "the card is up, so its promise is put away"
    assert note_after_edit, "and back when the box holds something else"
    assert not stale, "a text is not priced under the last link's facts"


def test_a_link_nothing_can_be_found_about_is_still_priced(browser, tmp_path: Path) -> None:
    """The reading never decides anything. A `/describe` that refuses, or falls over, is
    passed over in silence and the price follows exactly as it did before."""
    html = add_page(TOKEN)
    priced: list[object] = []

    def answer(route, request):
        if "/describe" in request.url:
            route.fulfill(status=500, content_type="application/json", body="{}")
        elif "/prepare" in request.url:
            priced.append(request.post_data_json)
            route.fulfill(status=200, content_type="application/json", body=json.dumps(PRICED))
        elif request.url.endswith(("/add", "/add.html")):
            route.fulfill(status=200, content_type="text/html", body=html)
        else:
            route.fulfill(status=200, content_type="application/json", body="{}")

    context = browser.new_context(viewport={"width": 1280, "height": 900})
    open_page = context.new_page()
    open_page.route("http://add.test/**", answer)
    open_page.goto("http://add.test/add")
    open_page.fill("#given", "https://www.youtube.com/watch?v=abc")
    open_page.click("#go")
    open_page.wait_for_timeout(600)
    drawn = open_page.is_visible(".found")
    context.close()

    assert priced, "a link that could not be described was not priced either"
    assert not drawn, "nothing was found, so nothing is said about it"


def test_the_library_answers_while_the_box_is_typed_in(browser, tmp_path: Path) -> None:
    """targum-internal#251. `instead()` says a text is already here, but only after
    Continue and only once `/prepare` has answered — so a reader was told after being
    quoted a price for a second copy. This is asked while they type, and asks nothing
    of `/prepare`."""
    html = add_page(TOKEN)
    asked: list[str] = []

    def answer(route, request):
        if "/already" in request.url:
            asked.append("already")
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(
                    {"id": "genesis", "title": "בראשית", "english": "Genesis", "translations": 1}
                ),
            )
        elif "/prepare" in request.url:
            asked.append("prepare")
            route.fulfill(status=200, content_type="application/json", body=json.dumps(PRICED))
        elif request.url.endswith(("/add", "/add.html")):
            route.fulfill(status=200, content_type="text/html", body=html)
        else:
            route.fulfill(status=200, content_type="application/json", body="{}")

    context = browser.new_context(viewport={"width": 1280, "height": 900})
    open_page = context.new_page()
    open_page.route("http://add.test/**", answer)
    open_page.goto("http://add.test/add")
    open_page.fill("#given", "בראשית")
    open_page.wait_for_selector(".already", timeout=4000)
    said = open_page.inner_text("#already")
    context.close()

    assert "prepare" not in asked, "nothing was priced"
    assert "בראשית" in said and "already in the library" in said
    assert "a translation a person published" in said
    assert "Bring my own copy" in said, "and the way past it"


def test_a_box_the_library_does_not_know_says_nothing(browser, tmp_path: Path) -> None:
    """Empty is the ordinary state of this: most of what a reader pastes is not in the
    catalogue, and a card that appeared for everything would be noise under the box."""
    html = add_page(TOKEN)

    def answer(route, request):
        if "/already" in request.url:
            route.fulfill(status=200, content_type="application/json", body="{}")
        elif request.url.endswith(("/add", "/add.html")):
            route.fulfill(status=200, content_type="text/html", body=html)
        else:
            route.fulfill(status=200, content_type="application/json", body="{}")

    context = browser.new_context(viewport={"width": 1280, "height": 900})
    open_page = context.new_page()
    open_page.route("http://add.test/**", answer)
    open_page.goto("http://add.test/add")
    open_page.fill("#given", "https://example.com/an-article")
    open_page.wait_for_timeout(700)
    drawn = open_page.is_visible("#already")
    context.close()

    assert not drawn


def test_add_records_a_voice_note_and_prices_it_like_a_dropped_file(
    browser, tmp_path: Path
) -> None:
    """targum-internal#254. The recorder is `speak.js`'s, the same one the composer's
    Speak uses; what a clip is for is the caller's, and here it is a file like any
    dropped one — up the chunked door, priced as a recording."""
    html = add_page(TOKEN)
    sent: list[dict] = []

    def answer(route, request):
        if "/upload/begin" in request.url:
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps({"upload": "u1", "chunk": 1024 * 1024}),
            )
        elif "/upload/" in request.url:
            route.fulfill(
                status=200, content_type="application/json", body=json.dumps({"upload": "u1"})
            )
        elif "/prepare" in request.url:
            sent.append(request.post_data_json or {})
            route.fulfill(status=200, content_type="application/json", body=json.dumps(PRICED))
        elif request.url.endswith(("/add", "/add.html")):
            route.fulfill(status=200, content_type="text/html", body=html)
        else:
            route.fulfill(status=200, content_type="application/json", body="{}")

    context = browser.new_context(
        viewport={"width": 1280, "height": 900}, permissions=["microphone"]
    )
    open_page = context.new_page()
    open_page.route("http://add.test/**", answer)
    # A recorder that answers without a microphone: what is under test is the page's
    # half — that a clip becomes a held file and goes up as a recording.
    open_page.add_init_script(
        """
        navigator.mediaDevices = navigator.mediaDevices || {};
        navigator.mediaDevices.getUserMedia = () =>
          Promise.resolve({ getTracks: () => [{ stop() {} }] });
        window.MediaRecorder = class {
          constructor() { this.mimeType = "audio/webm"; }
          start() { setTimeout(() => this.ondataavailable(
            { data: new Blob([new Uint8Array(2048)], { type: "audio/webm" }) }), 0); }
          stop() { setTimeout(() => this.onstop(), 0); }
        };
        """
    )
    open_page.goto("http://add.test/add")
    open_page.wait_for_selector("#record:not([hidden])", timeout=4000)
    open_page.click("#record")
    open_page.wait_for_timeout(200)
    while_recording = open_page.inner_text("#record-word")
    open_page.click("#record")
    open_page.wait_for_selector(".given-file", timeout=4000)
    chip = open_page.inner_text("#given-files")
    open_page.click("#go")
    open_page.wait_for_timeout(600)
    context.close()

    assert while_recording == "Stop", "the word follows the press"
    assert "Recorded just now" in chip, f"the chip says what it is: {chip!r}"
    assert sent, "Continue sent nothing"
    assert sent[0].get("upload") == "u1", "up the chunked door, like any recording"


def test_a_browser_that_cannot_record_is_not_offered_the_button(browser, tmp_path: Path) -> None:
    """The page never offers what it cannot do — the same rule the composer's Speak
    follows. Nothing here defines `MediaRecorder`."""
    html = add_page(TOKEN)

    def answer(route, request):
        if request.url.endswith(("/add", "/add.html")):
            route.fulfill(status=200, content_type="text/html", body=html)
        else:
            route.fulfill(status=200, content_type="application/json", body="{}")

    context = browser.new_context(viewport={"width": 1280, "height": 900})
    open_page = context.new_page()
    open_page.route("http://add.test/**", answer)
    open_page.add_init_script("delete window.MediaRecorder;")
    open_page.goto("http://add.test/add")
    open_page.wait_for_timeout(400)
    drawn = open_page.is_visible("#record")
    context.close()

    assert not drawn


def test_an_english_phone_is_shown_no_russian(browser) -> None:
    """ "I don't want a non russian to see any russian" (David, 2026-09-28). A browser with
    no sign of Russian starts on the subjects; the one way into Russian is EN · RU, and
    nothing on the screen is Cyrillic."""
    context, page, _ = _arrival_page(browser, 375, locale="en-US")
    try:
        seen = page.evaluate(
            """() => ({
              language: !document.getElementById('arrival-language').hidden,
              switch: document.getElementById('arrival-switch').innerText,
              text: document.getElementById('arrival').innerText,
            })"""
        )
        assert not seen["language"]
        assert "EN" in seen["switch"] and "RU" in seen["switch"]
        assert not re.search("[\u0400-\u04ff]", seen["text"]), seen["text"]
    finally:
        context.close()


def _home(browser, width: int, readers: list[dict], stored: dict[str, str], over: bool = True):
    """Home, served as the box would serve it, with `readers` on the shelf and `stored` in
    this browser's storage. Signed out: the account's places are refused, and this
    browser's are all there are."""
    html = list_page(TOKEN, "texts")
    went: list[str] = []

    def answer(route, request):
        u = request.url
        path = urlparse(u).path
        if path in ("/welcome", "/reader/new/reader/index.html") or path.startswith("/reader/"):
            went.append(path)
            return route.fulfill(status=200, content_type="text/html", body="<p>elsewhere</p>")
        if request.resource_type == "document":
            return route.fulfill(status=200, content_type="text/html", body=html)
        if path == "/readers":
            body: dict = {"readers": readers, "shared": [], "trash": []}
        elif path == "/account/places":
            return route.fulfill(status=401, content_type="application/json", body="{}")
        elif path == "/account/me":
            body = {"signedIn": False}
        elif path == "/suggest":
            body = {"suggestion": {"id": "ruth", "title": "רות", "language": "he", "minutes": 9}}
        else:
            body = {}
        route.fulfill(status=200, content_type="application/json", body=json.dumps(body))

    context = browser.new_context(
        viewport={"width": width, "height": 844}, is_mobile=width < 640, has_touch=width < 640
    )
    page = context.new_page()
    script = "".join(
        f"localStorage.setItem({json.dumps(k)}, {json.dumps(v)});" for k, v in stored.items()
    )
    if over:
        script += "sessionStorage.setItem('targum:arrival-over', '1');"
    page.add_init_script(script)
    page.route("http://home.test/**", answer)
    page.goto(f"http://home.test/?k={TOKEN}")
    return context, page, went


def _shelf_row(name: str, title: str, built: int, **extra: object) -> dict:
    row = {
        "name": name, "document": name, "entry": "", "title": title, "language": "he",
        "register": "modern", "kind": "article", "sections": 1, "chapters": [],
        "readyChapters": 0, "built": built, "drawn": False, "words": 100,
    }  # fmt: skip
    row.update(extra)
    return row


@pytest.mark.parametrize("width", [320, 390, 1280])
def test_home_leads_with_continue_and_picks_up_where_you_stopped(browser, width: int) -> None:
    """design.md §12, "Home is Your targums, and Continue leads it" (2026-10-08): the last
    texts opened or uploaded, newest first, four at a desk and two on a phone, each one
    press back to the part it was left in; the upload under Continue on a phone and
    beside the shelf at a desk; and nothing scrolls sideways."""
    chapters = [
        {"number": n, "title": str(n), "file": f"sec-000{n}.html", "ready": True} for n in (1, 2, 3)
    ]
    readers = [
        _shelf_row("book", "ספר", 100, kind="novel", chapters=chapters, sections=3),
        *(_shelf_row(f"up{n}", f"העלאה {n}", 200 + n) for n in range(4)),
    ]
    now = 1_900_000_000_000
    places = {"book": {"section": "2", "path": "/reader/book/reader/sec-0002.html", "segment": "s9",
                       "seconds": 0, "at": now}}  # fmt: skip
    context, page, went = _home(browser, width, readers, {"targum:places": json.dumps(places)})
    page.wait_for_selector("#continue:not([hidden]) .home-card")
    page.wait_for_selector("#try-next:not([hidden])")
    got = page.evaluate(
        """() => {
          const seen = (el) => !!el && el.getBoundingClientRect().height > 0
            && getComputedStyle(el).display !== 'none';
          const cards = [...document.querySelectorAll('#continue-cards > li')];
          const top = (s) => document.querySelector(s).getBoundingClientRect().top;
          return {
            cards: cards.length,
            shown: cards.filter(seen).length,
            first: cards[0].querySelector('.home-card-title').textContent,
            go: cards[0].querySelector('.home-card-go').textContent,
            href: cards[0].querySelector('.home-card-open').getAttribute('href'),
            picture: (cards[0].querySelector('img') || {}).src || '',
            uploadFirst: top('.upload-card') < top('.home-shelf'),
            sideways: document.documentElement.scrollWidth > window.innerWidth,
          };
        }"""
    )
    page.locator("#continue-cards .home-card-open").first.click()
    page.wait_for_timeout(300)
    context.close()
    assert got["cards"] == 4, got
    assert got["shown"] == (2 if width < 640 else 4), got
    assert got["first"] == "ספר" and got["go"] == "Pick up at part 2", got
    assert got["href"].startswith("/reader/book/reader/sec-0002.html"), got
    assert got["uploadFirst"] == (width < 640), got
    assert not got["sideways"], got
    assert went == ["/reader/book/reader/sec-0002.html"], went


def test_a_new_reader_is_asked_first_and_then_sees_an_honest_home(browser) -> None:
    """Nothing opened and nothing answered: the arrival's questions, on their own page.
    Once they are over, home says what will appear here, with one to start with and the
    upload (the FirstRun boards)."""
    context, page, went = _home(browser, 1280, [], {}, over=False)
    page.wait_for_timeout(500)
    context.close()
    assert went == ["/welcome"], went

    context, page, went = _home(browser, 1280, [], {})
    page.wait_for_selector("#first-home:not([hidden])")
    page.wait_for_selector("#try-next:not([hidden])")
    got = page.evaluate(
        """() => ({
          label: document.querySelector('#try-next .home-label').textContent,
          tabs: getComputedStyle(document.getElementById('yours-tabs')).display,
          shelf: document.getElementById('shelf-panel').hidden,
        })"""
    )
    context.close()
    assert went == []
    assert got == {"label": "One to start with", "tabs": "none", "shelf": True}, got


WORDS_SEEN = """() => ({
  back: document.querySelector('.words-back').getAttribute('href'),
  summary: document.getElementById('words-summary').textContent,
  tabs: [...document.querySelectorAll('.list-tabs a')].map(
    (a) => a.textContent.trim().replace(/\\s+/g, ' ')
  ),
  current: document.querySelector('.list-tabs a[aria-current="page"]').textContent.trim(),
  chips: [...document.querySelectorAll('#stage-chips .chip')].map((c) => c.textContent),
  steps: [...document.querySelectorAll('#word-rows tr')].map(
    (row) => [...row.querySelectorAll('.stage .level')].map((b) => b.textContent)
  ),
  sideways: document.documentElement.scrollWidth > window.innerWidth,
})"""


@pytest.mark.parametrize("width", [390, 1280])
def test_your_words_opens_from_progress_with_the_five_stages_on_every_row(
    browser, width: int
) -> None:
    """design.md §12, "Your Words is reached from Your Progress, by stage" (2026-10-09)."""
    import os

    html = list_page(TOKEN, "words")

    def answer(route, request):
        if request.resource_type == "document":
            return route.fulfill(status=200, content_type="text/html", body=html)
        route.fulfill(status=200, content_type="application/json", body="{}")

    context = browser.new_context(viewport={"width": width, "height": 900})
    page = context.new_page()
    page.add_init_script(
        "localStorage.setItem('targum:vocab:he', JSON.stringify({"
        "'ספר': {surface: 'ספר', status: 9, at: 1},"
        "'דרך': {surface: 'דרכים', status: 2, at: 2},"
        "'עיר': {surface: 'עיר', status: 1, at: 3}}));"
        "localStorage.setItem('targum:language', 'he')"
    )
    page.route("http://words.test/**", answer)
    page.goto(f"http://words.test/words?k={TOKEN}")
    page.wait_for_timeout(500)
    got = page.evaluate(WORDS_SEEN)
    shots = os.environ.get("TARGUM_SHOTS")
    if shots:
        page.screenshot(path=f"{shots}/words-{width}.png", full_page=True)
    page.locator("#word-rows tr", has_text="עיר").locator(".level-3").click()
    page.wait_for_timeout(200)
    stored = page.evaluate("JSON.parse(localStorage.getItem('targum:vocab:he'))['עיר'].status")
    context.close()

    assert got["back"].startswith("/progress")
    assert got["summary"] == "3 on your list · 1 known"
    assert got["tabs"] == ["Words 3", "Phrases 0"] and got["current"].startswith("Words")
    assert got["chips"][0] == "To work on" and "Getting there" in got["chips"]
    five = ["1", "2", "3", "known", "ignore"]
    assert got["steps"] and all(steps == five for steps in got["steps"])
    assert not got["sideways"], got
    assert stored == 3
