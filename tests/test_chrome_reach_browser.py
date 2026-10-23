"""The shared chrome's reach under a thumb, hit-tested in a real browser (design.md §8;
the Library QA's "wider than the Library", targum#827, decided 2026-10-20).

`test_brand.py` can only see that a selector stands in a coarse-pointer block. What a
tap reaches is the other half: an `::after` that sits flush to one side, a box that
clips its own reach, a neighbour that takes the edge. So each control here is measured
the way a thumb meets it, with `document.elementFromPoint` across a 44px box around its
middle, at 390 wide with a coarse pointer.

The bar's bell and account, the connection banner's Saved texts, the search's All tab,
and the foot's links; the Tanakh map's Read is walked the same way in
`test_tanakh_map_page.py`. Skips itself without Playwright and its
Chromium, as the other browser tests do.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from targum.render.builder import about_page, library_page

playwright_api = pytest.importorskip(
    "playwright.sync_api", reason="Playwright is not installed: uv sync --extra browser"
)

SITE = "http://chrome.test"

#: How far a tap reaches each way from a control's middle, at the least: 44px across.
HALF = 22

#: The point-by-point walk out from a control's middle: how far, left, right, up and
#: down, `elementFromPoint` still lands on the control (or inside it). The answer is the
#: reach across and up, in CSS pixels.
REACH = """(selector) => {
  const el = document.querySelector(selector);
  if (!el) return null;
  el.scrollIntoView({block: 'center', inline: 'center'});
  const r = el.getBoundingClientRect();
  const cx = r.left + r.width / 2, cy = r.top + r.height / 2;
  const hits = (x, y) => {
    const at = document.elementFromPoint(x, y);
    return !!at && (at === el || el.contains(at));
  };
  const walk = (dx, dy) => {
    let n = 0;
    while (n < 60 && hits(cx + dx * (n + 1), cy + dy * (n + 1))) n++;
    return n;
  };
  return {
    across: walk(-1, 0) + walk(1, 0) + 1,
    up: walk(0, -1) + walk(0, 1) + 1,
    drawn: [Math.round(r.width), Math.round(r.height)],
    centre: hits(cx, cy),
  };
}"""


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


def phone(browser, html: str, answers: dict[str, Any], *, offline: bool = False):
    """A page at 390 wide under a coarse pointer, its JSON answered from `answers`."""

    def answer(route, request):
        path = request.url[len(SITE) :].split("?")[0].split("#")[0]
        if request.resource_type == "document":
            return route.fulfill(status=200, content_type="text/html", body=html)
        if path.startswith("/assets/"):
            return route.abort("failed")
        said = answers.get(path, {})
        if said == "abort":
            return route.abort("internetdisconnected")
        route.fulfill(status=200, content_type="application/json", body=json.dumps(said))

    context = browser.new_context(
        viewport={"width": 390, "height": 844},
        is_mobile=True,
        has_touch=True,
        reduced_motion="reduce",
    )
    if offline:
        context.add_init_script(
            "Object.defineProperty(Navigator.prototype, 'onLine', {get: () => false});"
        )
    page = context.new_page()
    thrown: list[str] = []
    page.on("pageerror", lambda error: thrown.append(str(error)))
    page.route(f"{SITE}/**", answer)
    return context, page, thrown


def reach(page, selector: str) -> dict[str, Any]:
    page.locator(selector).first.wait_for(state="visible")
    measured = page.evaluate(REACH, selector)
    assert measured, f"{selector} is not on the page"
    return measured


def reaches_44(measured: dict[str, Any]) -> bool:
    return measured["centre"] and measured["across"] >= 44 and measured["up"] >= 44


@pytest.fixture(scope="module")
def library_html() -> str:
    return library_page("")


SIGNED_OUT = {"/readers": {"readers": [], "shared": []}}


def test_the_bar_s_bell_and_account_reach_44px(browser, library_html) -> None:
    """Drawn 30px wide, and reaching 44px by a centred `::after` (QA 2026-10-11): what
    the Library QA measured was the drawing. Pinned here as a tap meets it."""
    context, page, thrown = phone(browser, library_html, SIGNED_OUT)
    page.goto(f"{SITE}/library")
    for selector in ("#notices-open", "#account-open"):
        measured = reach(page, selector)
        assert reaches_44(measured), (selector, measured)
    # Signed in, the account is a circle of initials, 36px, and its reach the `::after`;
    # the bell beside it keeps its own.
    page.evaluate(
        """() => { const b = document.querySelector('#account-open');
                   b.classList.add('avatar'); b.textContent = 'DL'; }"""
    )
    for selector in ("#account-open", "#notices-open"):
        measured = reach(page, selector)
        assert reaches_44(measured), (selector, measured)
    assert not thrown
    context.close()


def test_the_banner_s_saved_texts_reaches_44px(browser, library_html) -> None:
    context, page, thrown = phone(browser, library_html, {"/readers": "abort"}, offline=True)
    page.goto(f"{SITE}/library")
    measured = reach(page, "#fault-banner .offline-to-saved")
    assert reaches_44(measured), measured
    assert not thrown
    context.close()


def test_the_search_s_all_tab_reaches_44px(browser, library_html) -> None:
    context, page, thrown = phone(browser, library_html, SIGNED_OUT)
    page.goto(f"{SITE}/library")
    # On a phone the search's door is in the account's sheet.
    page.evaluate("document.querySelector('[data-palette-open]').click()")
    measured = reach(page, '.palette-filters .tab[data-filter="all"]')
    assert reaches_44(measured), measured
    assert not thrown
    context.close()


def short_links_in_the_foot(page) -> dict[str, Any]:
    links = page.evaluate(
        """() => [...document.querySelectorAll('.site-footer a')]
                 .filter((a) => a.getClientRects().length)
                 .map((a, n) => { a.dataset.reachProbe = String(n); return n; })"""
    )
    assert len(links) >= 4
    short = {}
    for n in links:
        selector = f'.site-footer a[data-reach-probe="{n}"]'
        measured = reach(page, selector)
        if not reaches_44(measured):
            label = page.locator(selector).get_attribute("aria-label")
            short[label or page.locator(selector).inner_text()] = measured
    return short


def test_every_link_in_the_app_s_foot_reaches_44px(browser, library_html) -> None:
    context, page, thrown = phone(browser, library_html, SIGNED_OUT)
    page.goto(f"{SITE}/library")
    assert not short_links_in_the_foot(page)
    assert page.evaluate("document.scrollingElement.scrollWidth <= innerWidth")
    assert not thrown
    context.close()


def test_every_link_in_the_public_foot_reaches_44px(browser, monkeypatch) -> None:
    """The public foot carries more: the waitlist, Sign in, the legal pages and EN / RU,
    where RU is a 17px word at the edge."""
    monkeypatch.setenv("TARGUM_PUBLIC_LEGAL", "1")
    monkeypatch.setenv("TARGUM_FRONT_DOOR", "1")
    context, page, thrown = phone(browser, about_page(), {})
    page.goto(f"{SITE}/about")
    for name in ("Join the waitlist", "Sign in", "Privacy", "Terms", "RU"):
        assert page.locator(".site-footer a", has_text=name).count(), name
    assert not short_links_in_the_foot(page)
    assert page.evaluate("document.scrollingElement.scrollWidth <= innerWidth")
    assert not thrown
    context.close()


def test_news_lists_the_topics_to_follow_and_reaches_44px(browser, library_html) -> None:
    """The Library's News door opens News, and its eight topics stand there as rows, each
    with Subscribe going to the confirm page (David, 2026-10-22; targum-internal#475 B3:
    "Follow a topic" used to lead to a tab with nothing to follow). Signed in only, since
    following needs an account."""
    signed_in = {"/readers": {"readers": [], "shared": [], "signedIn": True}}
    context, page, thrown = phone(browser, library_html, signed_in)
    page.goto(f"{SITE}/library#see/kind/article")
    page.locator("#see-topics").wait_for(state="visible")
    assert page.inner_text("#see-topics-head") == "Follow a topic"
    names = page.eval_on_selector_all(".see-topic-name", "all => all.map((n) => n.textContent)")
    assert names == [
        "World",
        "Politics",
        "Economy",
        "Culture",
        "Science",
        "Technology",
        "Sport",
        "Health",
    ], names
    first = page.locator("#see-topics a").first
    assert first.get_attribute("href") == (
        "/subscribe?kind=topic&key=world&via=library&language=he"
    ), first.get_attribute("href")
    assert first.inner_text() == "Subscribe"
    assert first.get_attribute("aria-label") == "Subscribe to World"
    assert reaches_44(reach(page, "#see-topics a"))
    # Not on another kind's list, nor on the shelves.
    page.goto(f"{SITE}/library#see/kind/talk")
    page.locator("#see-title").wait_for(state="visible")
    assert page.locator("#see-topics").is_hidden()
    assert not thrown
    context.close()

    context, page, thrown = phone(browser, library_html, SIGNED_OUT)
    page.goto(f"{SITE}/library#see/kind/article")
    page.locator("#see-title").wait_for(state="visible")
    assert page.locator("#see-topics").is_hidden(), "signed out, there is nothing to follow"
    assert not thrown
    context.close()


def test_a_topic_you_follow_says_subscribed_in_news(browser, library_html) -> None:
    """A topic the reader follows already says Subscribed and goes to its own page, not
    to the confirm page again; one they unsubscribed from offers Subscribe as before
    (#475, qa-claude after #890)."""
    signed_in = {
        "/readers": {"readers": [], "shared": [], "signedIn": True},
        "/subscriptions.json": {
            "signedIn": True,
            "subscriptions": [
                {"kind": "topic", "key": "sport", "state": "on", "page": "/subscriptions/3"},
                {"kind": "topic", "key": "world", "state": "off", "page": "/subscriptions/5"},
                {"kind": "channel", "key": "health", "state": "on", "page": "/subscriptions/6"},
            ],
        },
    }
    context, page, thrown = phone(browser, library_html, signed_in)
    page.goto(f"{SITE}/library#see/kind/article")
    page.locator('#see-topics a[data-topic="sport"].is-on').wait_for(state="visible")
    rows = page.eval_on_selector_all(
        "#see-topics a[data-topic]",
        """all => Object.fromEntries(all.map((a) => [a.dataset.topic,
             [a.textContent, a.getAttribute('href'), a.getAttribute('aria-label')]]))""",
    )
    assert rows["sport"] == ["Subscribed", "/subscriptions/3", "Subscribed to Sport"], rows
    assert rows["world"][0] == "Subscribe", rows
    assert rows["world"][1].startswith("/subscribe?kind=topic&key=world"), rows
    assert rows["health"][0] == "Subscribe", "a channel is not a topic"
    assert reaches_44(reach(page, '#see-topics a[data-topic="sport"]'))
    assert not thrown
    context.close()
