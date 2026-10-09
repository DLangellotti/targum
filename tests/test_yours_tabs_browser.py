"""Your targums' tabs, sifting and series, in a real browser (design.md §12, "Your targums
has tabs, says what a targum is, and folds a series", 2026-09-26).

    uv sync --extra browser && uv run playwright install chromium
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from targum.render.builder import list_page, playlists_page

playwright_api = pytest.importorskip(
    "playwright.sync_api", reason="Playwright is not installed: uv sync --extra browser"
)


def _text(name: str, title: str, **extra: object) -> dict:
    return {
        "name": name,
        "document": name,
        "title": title,
        "language": "he",
        "entry": "",
        "built": int(time.time()) - 3600,
        "minutes": 3,
        "seconds": 0,
        "sections": 1,
        "chapters": [],
        **extra,
    }


#: Three episodes of one series, a text brought by hand, a Library text built, and a
#: shared one opened: seven rows, enough for the sifting to be drawn.
MINE = [
    _text("e63", "עברית אנפלאגד - פרק 63 | שחושבת"),
    _text("e61", "עברית אנפלאגד - פרק 61 | תינוקות"),
    _text("e60", "עברית אנפלאגד - פרק 60 | לעגל פינות"),
    _text("own", "כתבה שהבאתי", english="An article I brought", drawn=False),
    _text("own2", "עוד כתבה", english="Another article"),
    _text("lib", "משנה ברכות", english="Mishnah Berakhot", entry="mishnah-berakhot-1"),
]
SHARED = [_text("shared", "במעלית", english="In the elevator", entry="d-elev")]
DOCS = {"e61": {"done": True}, "e60": {"done": True}}
OPENED = {"shared": 1000}


@pytest.fixture(scope="module")
def browser():
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


def shelf(
    browser, tmp_path: Path, width: int = 1280, html: str | None = None, mine: list | None = None
):
    page_file = tmp_path / "texts.html"
    page_file.write_text(html or list_page("test-key", "texts"), encoding="utf-8")
    # Tall enough that the shelf under home's Continue is on screen (2026-10-08).
    context = browser.new_context(viewport={"width": width, "height": 2000})
    page = context.new_page()
    thrown: list[str] = []
    page.on("pageerror", lambda error: thrown.append(str(error)))
    said = {"readers": MINE if mine is None else mine, "shared": SHARED, "trash": []}
    page.add_init_script(
        f"localStorage.setItem('targum:docs', {json.dumps(json.dumps(DOCS))});"
        f"localStorage.setItem('targum:opened', {json.dumps(json.dumps(OPENED))});"
        f"const said = {json.dumps(said)};"
        "window.fetch = (url) => Promise.resolve(new Response(JSON.stringify("
        "  String(url).split('?')[0].endsWith('/readers') ? said : {})));"
    )
    page.goto(page_file.as_uri())
    if html is None:
        page.wait_for_selector("#library-list li")
    return context, page, thrown


def titles(page) -> list[str]:
    return [one.strip() for one in page.locator("#library-list .book-title").all_inner_texts()]


def test_a_continue_card_s_bar_is_the_share_it_says_you_know(browser, tmp_path: Path) -> None:
    """The bar under "You know 40%" is 40% full (board Main: "274 of 379 known" over a bar
    72% full). It drew the parts finished, so an opened text showed an empty track under
    its known share (design review, 2026-10-09); a text with no share has no bar."""
    mine = [
        _text("known", "ידוע", english="Known", known=0.4, words=120),
        _text("unmeasured", "לא נמדד", english="Unmeasured"),
    ]
    context, page, thrown = shelf(browser, tmp_path, mine=mine)
    page.wait_for_selector("#continue-cards li")
    cards = page.evaluate(
        """() => [...document.querySelectorAll('#continue-cards .home-card')].map(card => ({
             title: card.querySelector('.home-card-title').textContent,
             facts: (card.querySelector('.home-card-facts') || {}).textContent || '',
             done: card.querySelector('.home-fill')
               ? card.querySelector('.home-fill').style.getPropertyValue('--done') : null }))"""
    )
    context.close()
    by = {card["title"]: card for card in cards}
    assert "You know 40%" in by["ידוע"]["facts"] and by["ידוע"]["done"] == "0.4"
    assert by["לא נמדד"]["done"] is None, "no figure, no bar"
    assert not thrown


def test_a_series_is_one_row_until_it_is_opened(browser, tmp_path: Path) -> None:
    context, page, thrown = shelf(browser, tmp_path)
    folded = titles(page)
    facts = page.locator("#library-list li.is-series .book-facts").inner_text()
    status = page.locator("#library-list li.is-series .fact-status").inner_text()
    page.click("#library-list .series-press")
    opened = titles(page)
    named = page.locator("#series-name").inner_text()
    page.click("#series-back")
    back = titles(page)
    context.close()
    assert folded.count("עברית אנפלאגד") == 1 and len(folded) == 5
    assert "3 episodes" in facts and status.strip() == "2 of 3"
    assert named == "עברית אנפלאגד"
    # In episode order, and without the series' name said again on every row.
    assert opened == ["פרק 60 | לעגל פינות", "פרק 61 | תינוקות", "פרק 63 | שחושבת"]
    assert back == folded
    assert not thrown


def test_your_uploads_is_only_what_you_brought(browser, tmp_path: Path) -> None:
    context, page, thrown = shelf(browser, tmp_path)
    page.click("#yours-tabs [data-tab='uploads']")
    uploads = titles(page)
    current = page.get_attribute("#yours-tabs [aria-current='page']", "data-tab")
    address = page.evaluate("() => location.search")
    context.close()
    assert "משנה ברכות" not in uploads, "a Library text you built is not an upload"
    assert "במעלית" not in uploads, "a shared text you opened is not an upload"
    assert "כתבה שהבאתי" in uploads and "עברית אנפלאגד" in uploads
    assert current == "uploads" and "show=uploads" in address
    assert not thrown


def test_all_targums_holds_the_shared_text_you_opened(browser, tmp_path: Path) -> None:
    context, page, _ = shelf(browser, tmp_path)
    everything = titles(page)
    context.close()
    assert "במעלית" in everything and "משנה ברכות" in everything


def test_a_search_sifts_the_shelf(browser, tmp_path: Path) -> None:
    """Board Main draws one field, "Find in your targums", and no chips or order: the
    chips and the native select went in P4 (2026-10-09). The English under a title is
    searched too."""
    context, page, thrown = shelf(browser, tmp_path)
    chips = page.locator("#status-chips, #shelf-order").count()
    page.fill("#shelf-find", "brought")
    found = titles(page)
    page.fill("#shelf-find", "zzz")
    nothing = page.locator("#shelf-note").inner_text()
    context.close()
    assert chips == 0, "no chips and no order"
    assert found == ["כתבה שהבאתי"], "the English under a title is searched too"
    assert nothing == "Nothing here matches that. Try another search."
    assert not thrown


def test_a_short_shelf_is_not_handed_controls(browser, tmp_path: Path) -> None:
    context, page, _ = shelf(browser, tmp_path)
    page.click("#yours-tabs [data-tab='uploads']")
    hidden = page.locator("#shelf-find").is_hidden()
    context.close()
    assert hidden, "five uploads is a shelf that needs no sifting"


def test_the_list_is_rows_in_one_card_with_the_tabs_at_its_head(browser, tmp_path: Path) -> None:
    """Board Main: "All your targums" is one card, its title and the four tabs at its
    head, and every text a row across it, at a desk and on a phone alike. They were
    Learn's cards at a desk, and a long playlist name pushed one past its card."""
    for width in (1280, 390):
        context, page, thrown = shelf(browser, tmp_path, width)
        got = page.evaluate(
            """() => {
              const card = document.getElementById('shelf-panel').getBoundingClientRect();
              const rows = [...document.querySelectorAll('#library-list > li')]
                .map((li) => li.getBoundingClientRect());
              return {
                card: card.width,
                rows: rows.map((r) => r.width),
                inside: rows.every((r) => r.left >= card.left - 1 && r.right <= card.right + 1),
                tabsInHead: !!document.querySelector('#yours-head #yours-tabs'),
                title: document.getElementById('shelf-title').textContent,
                scroll: document.documentElement.scrollWidth,
              };
            }"""
        )
        context.close()
        assert got["tabsInHead"] and got["title"] == "All your targums", got
        assert got["inside"], "no row runs past its card"
        assert min(got["rows"]) > got["card"] * 0.8, "each text is a row across the card"
        assert got["scroll"] <= width, "the page never scrolls sideways"
        assert not thrown


def test_a_long_playlist_name_is_cut_and_never_widens_the_row(browser, tmp_path: Path) -> None:
    long = ["Everyday Hebrew for the kitchen, the market and the bus on the way home"] * 3
    mine = [_text("own", "כתבה שהבאתי", english="An article I brought", playlists=long)]
    for width in (1280, 390):
        context, page, _ = shelf(browser, tmp_path, width, mine=mine)
        got = page.evaluate(
            """() => {
              const line = document.querySelector('#library-list .book-facts');
              const row = line.closest('li').getBoundingClientRect();
              const box = line.getBoundingClientRect();
              return {fits: box.right <= row.right + 1 && box.left >= row.left - 1,
                      scroll: document.documentElement.scrollWidth};
            }"""
        )
        context.close()
        assert got["fits"] and got["scroll"] <= width, got


def test_playlists_wears_the_same_tabs_and_lights_your_targums(browser, tmp_path: Path) -> None:
    context, page, _ = shelf(browser, tmp_path, html=playlists_page("test-key"))
    tabs = page.eval_on_selector_all("#yours-tabs .tab", "all => all.map(a => a.dataset.tab)")
    current = page.get_attribute("#yours-tabs [aria-current='page']", "data-tab")
    here = page.get_attribute(".site-nav a[aria-current='page']", "data-nav")
    context.close()
    assert tabs == ["recent", "playlists", "subscriptions", "uploads"]
    assert current == "playlists" and here == "texts"


@pytest.mark.parametrize("width", [390, 1280])
def test_every_row_can_be_reached_and_pressed_from_a_keyboard(
    browser, tmp_path: Path, width: int
) -> None:
    """The row's link wrapped its cells with `display: contents`, which no browser will
    focus: Tab went from the order to the first row's keys and no text or series could be
    opened without a pointer (2026-09-27). The title is the press now, stretched over the
    row, and a pointer anywhere on the row still opens it."""
    context, page, thrown = shelf(browser, tmp_path, width=width)
    for _ in range(60):
        page.keyboard.press("Tab")
        page.evaluate("document.activeElement.dataset.reached = '1'")
    opens = page.locator("#library-list .book-open").count()
    series = page.locator("#library-list .series-press[data-reached]").count()
    texts = page.locator("#library-list .book-open[data-reached]").count()
    reached = [series, texts, opens]
    page.locator("#library-list .series-press").focus()
    page.keyboard.press("Enter")
    inside = page.locator("#series-name").inner_text()
    # A press on the picture, not the title, still lands on the link.
    box = page.locator("#library-list li:not(.is-series) .thumb").first.bounding_box()
    target = page.evaluate(
        "([x, y]) => document.elementFromPoint(x, y).className",
        [box["x"] + box["width"] / 2, box["y"] + box["height"] / 2],
    )
    context.close()
    assert series == 1, reached
    assert texts == opens and opens >= 4, reached
    assert inside == "עברית אנפלאגד"
    assert target == "book-open", "the stretch covers the picture"
    assert not thrown


def test_a_search_does_not_follow_the_reader_to_a_tab_with_no_search_box(
    browser, tmp_path: Path
) -> None:
    """Typed on All targums, a search went on filtering Your uploads, which is too short to
    draw the box it could be cleared from: "Nothing here matches that." and no way out
    (2026-09-27)."""
    context, page, thrown = shelf(browser, tmp_path)
    page.fill("#shelf-find", "zzz")
    page.click("#yours-tabs [data-tab='uploads']")
    uploads = titles(page)
    page.click("#yours-tabs [data-tab='recent']")
    everything = titles(page)
    typed = page.input_value("#shelf-find")
    context.close()
    assert "כתבה שהבאתי" in uploads and "עברית אנפלאגד" in uploads
    assert len(everything) == 5 and typed == ""
    assert not thrown


def test_a_series_begun_and_not_finished_says_started(browser, tmp_path: Path) -> None:
    """One episode opened and none finished said "0 of 3"."""
    global DOCS, OPENED
    kept = DOCS, OPENED
    DOCS, OPENED = {}, {"e63": 1000}
    try:
        context, page, _ = shelf(browser, tmp_path)
        status = page.locator("#library-list li.is-series .fact-status").inner_text()
        context.close()
    finally:
        DOCS, OPENED = kept
    assert status.strip() == "Started"


def test_a_reader_with_nothing_is_told_what_will_appear_here(browser, tmp_path: Path) -> None:
    """The FirstRun boards (design.md §12, 2026-10-08): with nothing on the shelf, home
    says what will appear here and offers the upload; the tabs and the shelf, which have
    nothing to show, stay away."""
    page_file = tmp_path / "texts.html"
    page_file.write_text(list_page("test-key", "texts"), encoding="utf-8")
    context = browser.new_context(viewport={"width": 390, "height": 900})
    page = context.new_page()
    page.add_init_script(
        "window.fetch = () => Promise.resolve(new Response(JSON.stringify("
        "{readers: [], shared: [], trash: []})));"
    )
    page.goto(page_file.as_uri())
    page.wait_for_selector("#first-home:not([hidden])")
    upload = page.locator(".upload-card").is_visible()
    tabs = page.locator("#yours-tabs").is_visible()
    shelf_shown = page.locator("#shelf-panel").is_visible()
    context.close()
    assert upload and not tabs and not shelf_shown


def test_a_row_s_picture_is_the_board_s_square(browser, tmp_path: Path) -> None:
    """Board Main: a 44px picture at the head of each row, a letter's as much as a frame's."""
    context, page, _ = shelf(browser, tmp_path, width=1280)
    box = page.locator("#library-list li:not(.is-series) .thumb.is-letter").first.bounding_box()
    # 2.75rem, at the desk's clamped rem (§13): 44px at the boards' 1440.
    rem = page.evaluate("() => parseFloat(getComputedStyle(document.documentElement).fontSize)")
    context.close()
    assert box is not None
    assert abs(box["width"] - 2.75 * rem) <= 1 and abs(box["height"] - box["width"]) <= 1, box


def test_a_series_is_read_through_pointing_marks_and_hebrew_numerals(
    browser, tmp_path: Path
) -> None:
    """פֶּרֶק is a marker, an RLM does not split a series, כג is 23, and "The" before
    "Chapter 11" is no series (targum-internal#376)."""
    global MINE
    kept = MINE
    MINE = [
        _text("a", "סיפורי חז״ל - פרק כג"),
        _text("b", "סיפורי חז״ל‏ - פֶּרֶק ב"),
        _text("c", "סיפורי חז״ל - פרק י"),
        _text("d", "The Chapter 11 story"),
        _text("e", "The Chapter 7 again"),
    ]
    try:
        context, page, thrown = shelf(browser, tmp_path)
        folded = titles(page)
        page.click("#library-list .series-press")
        opened = titles(page)
        context.close()
    finally:
        MINE = kept
    assert folded.count("סיפורי חז״ל") == 1
    assert "The Chapter 11 story" in folded and "The Chapter 7 again" in folded
    assert [t.split()[-1] for t in opened] == ["ב", "י", "כג"]
    assert not thrown


def test_subscriptions_is_a_tab_that_draws_the_series_in_place(browser, tmp_path: Path) -> None:
    """Your targums' tabs are Recent · Playlists · Subscriptions · Uploads (design.md §12,
    2026-09-26, amended 2026-10-08). Subscriptions is answered in place: the series with
    their switches, subscribed first, and the address says the tab."""
    page_file = tmp_path / "texts.html"
    page_file.write_text(list_page("test-key", "texts"), encoding="utf-8")
    context = browser.new_context(viewport={"width": 1280, "height": 2000})
    page = context.new_page()
    series = [
        {"id": "weekly", "name": "Weekly", "hebrew": "מבט השבוע", "what": "", "page": "/weekly"},
        {"id": "parasha", "name": "The weekly portion", "what": "", "page": "/parasha"},
    ]
    page.add_init_script(
        "localStorage.setItem('targum:follows', JSON.stringify({parasha: 1}));"
        f"const said = {json.dumps({'readers': MINE, 'shared': SHARED, 'trash': []})};"
        f"const series = {json.dumps({'series': series})};"
        "window.fetch = (url) => { const path = String(url).split('?')[0];"
        "  const body = path.endsWith('/readers') ? said : path.endsWith('/series') ? series : {};"
        "  return Promise.resolve(new Response(JSON.stringify(body))); };"
    )
    page.goto(page_file.as_uri())
    page.wait_for_selector("#library-list li")
    page.click("#yours-tabs [data-tab='subscriptions']")
    page.wait_for_selector("#home-series .series-row")
    got = page.evaluate(
        """() => ({
          rows: [...document.querySelectorAll('#home-series .series-row')]
            .map((li) => [li.dataset.series, li.querySelector('.switch-word').textContent]),
          shelf: document.getElementById('shelf-panel').hidden,
          current: document.querySelector('#yours-tabs [aria-current=page]').dataset.tab,
          address: location.search,
        })"""
    )
    context.close()
    assert got["rows"] == [["parasha", "Subscribed"], ["weekly", "Subscribe"]], got
    assert got["shelf"] and got["current"] == "subscriptions", got
    assert "show=subscriptions" in got["address"], got


def test_subscriptions_takes_the_page_s_width_under_the_title(browser, tmp_path: Path) -> None:
    """Board SubsTab: the tab is the page's whole width, the title stands, the tabs under
    it, and Continue and the side are not beside it. It sat in Continue's two-thirds
    column, about 400px wide, until P4 (2026-10-09)."""
    context, page, thrown = shelf(browser, tmp_path, 1280)
    page.click("#yours-tabs [data-tab='subscriptions']")
    got = page.evaluate(
        """() => ({
          panel: document.getElementById('subs-panel').getBoundingClientRect().width,
          main: document.getElementById('page').getBoundingClientRect().width,
          tabsOnTop: !!document.querySelector('#yours-top #yours-tabs'),
          top: !document.getElementById('yours-top').hidden,
          side: getComputedStyle(document.querySelector('.home-side')).display,
          cont: getComputedStyle(document.getElementById('continue')).display,
          title: getComputedStyle(document.querySelector('.page-title')).position,
        })"""
    )
    page.click("#yours-tabs [data-tab='recent']")
    back = page.evaluate("() => !!document.querySelector('#yours-head #yours-tabs')")
    context.close()
    assert got["tabsOnTop"] and got["top"], got
    assert got["side"] == "none" and got["cont"] == "none", got
    assert got["title"] != "absolute", "the page's title shows"
    assert got["panel"] > got["main"] * 0.9, got
    assert back, "Recent puts the tabs back in the card's head"
    assert not thrown


def _home_in(browser, tmp_path: Path, language: str, answers: dict, mine: list):
    """Home in `language`, every address answered from `answers` by its path's end."""
    page_file = tmp_path / "texts.html"
    page_file.write_text(list_page("test-key", "texts"), encoding="utf-8")
    context = browser.new_context(viewport={"width": 1280, "height": 1600})
    page = context.new_page()
    thrown: list[str] = []
    page.on("pageerror", lambda error: thrown.append(str(error)))
    said = {"readers": mine, "shared": [], "trash": [], **answers}
    page.add_init_script(
        f"localStorage.setItem('targum:language', {json.dumps(language)});"
        f"localStorage.setItem('targum:learning', {json.dumps(json.dumps(['he', language]))});"
        "sessionStorage.setItem('targum:arrival-over', '1');"
        f"const said = {json.dumps(said)};"
        "window.fetch = (url) => { const path = String(url).split('?')[0];"
        "  const key = Object.keys(said).find((end) => path.endsWith('/' + end));"
        "  const body = key === 'readers' ? {readers: said.readers, shared: [], trash: []}"
        "    : key ? said[key] : {};"
        "  return Promise.resolve(new Response(JSON.stringify(body))); };"
    )
    page.goto(page_file.as_uri())
    page.wait_for_selector("#library-list li")
    return context, page, thrown


def test_a_language_the_library_has_nothing_in_says_so_and_names_the_upload(
    browser, tmp_path: Path
) -> None:
    """Board YiHome: where the library has no texts in the language, home says so plainly
    in place of a suggestion, and the upload names the language (P4, 2026-10-09)."""
    mine = [_text("song", "אויפֿן פּריפּעטשיק", language="yi")]
    context, page, thrown = _home_in(
        browser, tmp_path, "yi", {"suggest": {"suggestion": None, "library": False}}, mine
    )
    page.wait_for_selector("#home-note:not([hidden])")
    note = page.locator("#home-note").inner_text()
    upload = page.locator("#upload-head").inner_text()
    context.close()
    assert "The library has no Yiddish texts yet" in note, note
    assert upload == "Upload something in Yiddish"
    assert not thrown


def test_aramaic_says_where_its_words_are_met(browser, tmp_path: Path) -> None:
    """Board ArcHome: Onkelos beside every verse of the Hebrew Torah, and the way there."""
    mine = [_text("onk", "תרגום אונקלוס על בראשית", language="arc")]
    context, page, thrown = _home_in(
        browser, tmp_path, "arc", {"suggest": {"suggestion": None, "library": True}}, mine
    )
    page.wait_for_selector("#home-note:not([hidden])")
    note = page.locator("#home-note").inner_text()
    door = page.get_attribute("#home-note a", "href")
    context.close()
    assert "Onkelos sits beside every verse" in note and door and door.startswith("/parasha")
    assert not thrown


def test_what_a_subscription_brought_leads_continue_and_is_counted_on_its_tab(
    browser, tmp_path: Path
) -> None:
    """Board SubHome: New first, said over Continue, and "1 new" on the Subscriptions tab."""
    item = {
        "kind": "series",
        "name": "Weekly News Digest",
        "title": "מבט השבוע",
        "language": "he",
        "door": "/reader/weekly/reader/index.html",
        "subscription": 1,
        "key": "w1",
    }
    context, page, thrown = _home_in(
        browser, tmp_path, "he", {"new.json": {"signedIn": True, "items": [item]}}, MINE
    )
    page.wait_for_selector("#continue-cards .is-new")
    note = page.locator("#continue-note").inner_text()
    count = page.locator("#subs-new").inner_text()
    context.close()
    assert note.startswith("New from your subscriptions first"), note
    assert count == "1 new"
    assert not thrown
