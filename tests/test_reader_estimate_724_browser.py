"""One figure for a new reader's first text, in a real browser (targum-internal#724).

A new reader's first text said "0 of 235 known" and the Home that followed it said "You
know about 44% of the whole recording (our estimate)". The reader now says the server's
estimate until anything in the text is marked, the figure Home prints, asked of the same
row (`/readers?name=`); design.md §12, "A reader says our estimate until anything in it is
marked" (2026-11-15). Signed out, and offline, it asks nothing new and says the count.

With `TARGUM_SHOTS` set to a folder, each state is saved there as
`estimate-724-<state>-<width>.png`. Skips itself without Playwright.
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("playwright.sync_api")

from test_finish_695_home_browser import CONTINUE, home  # noqa: E402
from test_finish_695_home_browser import reader as shelf_row  # noqa: E402
from test_reader_browser import browser, chapter, opened  # noqa: E402, F401

from targum.finds import button  # noqa: E402

ORIGIN = "http://targum.test"
NAME = "a-chapter"
FOLDER = f"/reader/{NAME}/reader/"
ME = {
    "signedIn": True, "email": "new@x.test", "initials": "N", "readsSaid": True,
    "declared": "gimel", "reads": ["en"], "language": "he", "learning": ["he"],
}  # fmt: skip
#: The new reader's row as the server sends it: nothing marked, our estimate 44%.
ROW = shelf_row(NAME, title="פרק ראשון", known=0.0, estimated=0.4372)

BAR = "() => (document.getElementById('known') || {}).textContent || ''"
LIST = "() => (document.getElementById('list-stats') || {}).textContent || ''"
QUIET = """() => {
  const label = document.querySelector('#known .estimate-ours');
  if (!label) return null;
  const style = getComputedStyle(label);
  const number = getComputedStyle(label.parentElement.querySelector('b'));
  return {weight: style.fontWeight, colour: style.color,
          numberWeight: number.fontWeight, numberColour: number.color};
}"""


@pytest.fixture(autouse=True)
def finds_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(button.FLAG, "1")


@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The built page: its folder is served, and it is the page opened."""
    return chapter(tmp_path_factory.mktemp("estimate-724") / "reader")


def shot(page: Any, name: str, width: int) -> None:
    where = os.environ.get("TARGUM_SHOTS", "").strip()
    if where:
        Path(where).mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(Path(where) / f"estimate-724-{name}-{width}.png"))


def open_reader(
    browser,  # noqa: F811
    folder: Path,
    width: int,
    me: dict[str, Any] | None = None,
    shelf: str = "readers",
    offline: bool = False,
    row: dict[str, Any] | None = None,
):
    """The reader at `width`, `/account/me` answering `me` and `/readers` holding ROW on
    `shelf` (the reader's own, or the shared shelf's); the caller closes it."""
    context = opened(browser, viewport={"width": width, "height": 900})
    if offline:
        context.add_init_script(
            "Object.defineProperty(Navigator.prototype, 'onLine', {get: () => false});"
        )
    page = context.new_page()
    thrown: list[str] = []
    asked: list[str] = []
    page.on("pageerror", lambda error: thrown.append(str(error)))

    def serve(route, request):
        whole = request.url.removeprefix(ORIGIN)
        path = whole.split("?")[0]
        asked.append(whole)
        if path.startswith(FOLDER):
            target = folder.parent / (path.removeprefix(FOLDER) or "index.html")
            if not target.is_file():
                return route.fulfill(status=404, body="not found")
            return route.fulfill(status=200, path=str(target), content_type="text/html")
        said: dict[str, Any] = {}
        if path == "/account/me":
            said = me if me is not None else ME
        elif path == "/readers":
            said = {"readers": [], "shared": [], "trash": []}
            said[shelf] = [row if row is not None else ROW]
        return route.fulfill(status=200, content_type="application/json", body=json.dumps(said))

    page.route(ORIGIN + "/**", serve)
    page.goto(ORIGIN + FOLDER + folder.name)
    page.wait_for_selector(".pair")
    page.evaluate("() => window.TargumSync && window.TargumSync.settled()")
    return context, page, thrown, asked


def percent_in(said: str) -> int:
    found = re.search(r"(\d+)%", said)
    assert found, said
    return int(found.group(1))


@pytest.mark.parametrize("width", [390, 1440])
def test_home_and_the_reader_say_one_figure_for_a_new_reader(
    browser,  # noqa: F811
    built: Path,
    width: int,
) -> None:
    """The first text's reader and the Home that follows print the same number."""
    context, page, thrown, asked = open_reader(browser, built, width)
    try:
        page.wait_for_function(f"({LIST})().startsWith('About ')")
        bar, line = page.evaluate(BAR), page.evaluate(LIST)
        shot(page, "reader", width)
        assert [one for one in asked if one.startswith("/readers?")] == [
            f"/readers?catalogue=0&name={NAME}"
        ], "asked once, for this text alone"
        assert bar == "About 44% (our estimate)", bar
        assert re.fullmatch(r"About 44% \(our estimate\) · \d+ words to mark", line), line
        assert "known" not in bar and "0 of" not in bar
        quiet = page.evaluate(QUIET)
        assert quiet is not None
        assert quiet["weight"] == "400" and quiet["numberWeight"] == "600", quiet
        assert quiet["colour"] != quiet["numberColour"], "the label is quiet beside the number"
        assert not thrown, thrown
    finally:
        context.close()

    now = int(time.time() * 1000)
    places = {NAME: {"section": "1", "path": FOLDER + built.name, "at": now - 1_000}}
    context, page, thrown, _ = home(browser, width, readers=[ROW], places=places)
    try:
        page.wait_for_function("document.querySelectorAll('#continue-cards .home-card').length")
        facts = page.evaluate(CONTINUE)[0]["facts"]
        shot(page, "home", width)
        assert "(our estimate)" in facts, facts
        assert percent_in(facts) == percent_in(bar) == 44, (facts, bar)
        assert not thrown, thrown
    finally:
        context.close()


def test_a_text_off_the_shared_shelf_says_its_estimate_too(browser, built: Path) -> None:  # noqa: F811
    """A new reader's first text is often the shelf's, not their own."""
    context, page, thrown, _ = open_reader(browser, built, 1440, shelf="shared")
    try:
        page.wait_for_function(f"({BAR})().startsWith('About ')")
        assert page.evaluate(BAR) == "About 44% (our estimate)"
        assert not thrown, thrown
    finally:
        context.close()


def test_the_first_mark_brings_the_count_back(browser, built: Path) -> None:  # noqa: F811
    context, page, thrown, _ = open_reader(browser, built, 1440)
    try:
        page.wait_for_function(f"({BAR})().startsWith('About ')")
        page.locator(".pair .src .w").first.click()
        page.keyboard.press("k")
        page.wait_for_function(f"/^1 of \\d+ known/.test(({BAR})())")
        assert re.match(r"\d+% known here · \d+ words to mark", page.evaluate(LIST))
        assert not thrown, thrown
    finally:
        context.close()


@pytest.mark.parametrize("state", ["signed-out", "offline"])
def test_signed_out_and_offline_ask_nothing_and_say_the_count(
    browser,  # noqa: F811
    built: Path,
    state: str,
) -> None:
    me = {"signedIn": False, "signedOut": True} if state == "signed-out" else None
    context, page, thrown, asked = open_reader(
        browser, built, 1440, me=me, offline=state == "offline"
    )
    try:
        page.wait_for_function(f"/^0 of \\d+ known/.test(({BAR})())")
        # Long enough for an ask after the account's answer to have gone out.
        page.wait_for_load_state("networkidle")
        assert [one for one in asked if one.startswith("/readers")] == [], asked
        assert re.match(r"0 of \d+ known", page.evaluate(BAR)), page.evaluate(BAR)
        # Offline holds back the ask on its own, not by way of a signed-out account.
        signed_in = page.evaluate("() => !!(window.TargumSync && window.TargumSync.who)")
        assert signed_in is (state == "offline"), state
        shot(page, state, 1440)
        assert not thrown, thrown
    finally:
        context.close()


def test_a_word_ignored_keeps_the_estimate(browser, built: Path) -> None:  # noqa: F811
    """Ignore is for names and numbers, not a mark of knowing: the estimate stands."""
    context, page, thrown, _ = open_reader(browser, built, 1440)
    try:
        page.wait_for_function(f"({BAR})().startsWith('About ')")
        page.locator(".pair .src .w").first.click()
        page.keyboard.press("i")
        page.wait_for_function(
            "() => Object.keys(localStorage).some((key) => key.startsWith('targum:vocab:')"
            " && Object.keys(JSON.parse(localStorage.getItem(key) || '{}')).length > 0)"
        )
        assert page.evaluate(BAR) == "About 44% (our estimate)", page.evaluate(BAR)
        assert page.evaluate(LIST).startswith("About 44% (our estimate) · "), page.evaluate(LIST)
        assert not thrown, thrown
    finally:
        context.close()


def test_a_row_with_no_estimate_keeps_the_count(browser, built: Path) -> None:  # noqa: F811
    """A row the server does not estimate (marks settle it, or it is not measured)."""
    bare = {key: value for key, value in ROW.items() if key != "estimated"}
    context, page, thrown, asked = open_reader(browser, built, 1440, row=bare)
    try:
        page.wait_for_function(f"/^0 of \\d+ known/.test(({BAR})())")
        page.wait_for_load_state("networkidle")
        assert any(one.startswith("/readers?") for one in asked), "it asked"
        assert re.match(r"0 of \d+ known", page.evaluate(BAR)), page.evaluate(BAR)
        assert "estimate" not in page.evaluate(LIST)
        assert not thrown, thrown
    finally:
        context.close()


def test_a_reader_opened_from_disk_asks_nothing(browser, built: Path) -> None:  # noqa: F811
    context = opened(browser, viewport={"width": 1440, "height": 900})
    page = context.new_page()
    asked: list[str] = []
    page.on("request", lambda request: asked.append(request.url))
    try:
        page.goto(built.as_uri())
        page.wait_for_selector(".pair")
        page.wait_for_function(f"/^0 of \\d+ known/.test(({BAR})())")
        page.wait_for_load_state("networkidle")
        assert [one for one in asked if "readers" in one] == [], asked
        assert not any(one.startswith("http") for one in asked), asked
    finally:
        context.close()
