"""Continue, picked up on another device, in a real browser (targum-internal#430).

The contents page asks the account where the reader left off and points Continue there
when the account's place is newer than this browser's; the part it opens puts the
reader back on their sentence from the same place. Signed out, this browser's own place
is the whole of it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("playwright.sync_api")

from test_reader_browser import address, browser, chapter, opened  # noqa: E402, F401


@pytest.fixture(scope="module")
def three_chapters(tmp_path_factory: pytest.TempPathFactory) -> Path:
    from test_chapter_ui import book

    from targum.models import Document, SegmentedDocument, Translation, read_artifact
    from targum.render import render

    folder = tmp_path_factory.mktemp("continue") / "book-he"
    book(folder, chapters=3, translated=3)
    segmented = read_artifact(SegmentedDocument, folder / "segments.json")
    translation = read_artifact(Translation, folder / "translations" / "null.natural.en.json")
    assert segmented is not None and translation is not None
    document = Document(source="m", title="A Book", language="he", blocks=[], content_hash="b")
    render(document, segmented, [translation], folder / "reader")
    return folder / "reader"


def answering(page, places: list[dict] | None) -> None:
    """Stand in for the account: `None` is somebody signed out."""

    def on_places(route) -> None:
        if places is None:
            route.fulfill(status=401, content_type="application/json", body='{"signedIn": false}')
        else:
            body = json.dumps({"signedIn": True, "places": places})
            route.fulfill(status=200, content_type="application/json", body=body)

    page.route("**/account/places*", on_places)
    # Nothing else on the contents page is under test here.
    page.route("**/readers*", lambda route: route.fulfill(status=404, body="{}"))
    page.route("**/jobs*", lambda route: route.fulfill(status=404, body="{}"))


def keeping(context, stored: dict[str, object]) -> None:
    context.add_init_script(
        f"(() => {{ const s = {json.dumps(stored)};"
        " for (const k in s) localStorage.setItem(k, JSON.stringify(s[k])); })()"
    )


def test_continue_follows_this_browser_when_signed_out(browser, three_chapters) -> None:  # noqa: F811
    context = opened(browser)
    page = context.new_page()
    try:
        page.goto(address(three_chapters / "index.html"))
        hash_ = page.locator(".toc[data-document]").get_attribute("data-document")
        second = page.locator('[data-chapter="2"] a').get_attribute("href")
        context.close()

        context = opened(browser)
        keeping(context, {"targum:places": {hash_: {"section": "2", "segment": "", "at": 50}}})
        page = context.new_page()
        answering(page, None)
        page.goto(address(three_chapters / "index.html"))
        page.wait_for_function("() => document.getElementById('start').textContent === 'Continue'")
        assert page.locator("#start").get_attribute("href").split("?")[0] == second
    finally:
        context.close()


def test_continue_follows_the_account_when_its_place_is_newer(browser, three_chapters) -> None:  # noqa: F811
    """This browser last read chapter two; the phone, later, chapter three. Continue goes
    to chapter three, and the place is kept here so the chapter opens on its sentence."""
    context = opened(browser)
    page = context.new_page()
    try:
        page.goto(address(three_chapters / "index.html"))
        hash_ = page.locator(".toc[data-document]").get_attribute("data-document")
        third = page.locator('[data-chapter="3"] a').get_attribute("href")
        context.close()

        context = opened(browser)
        keeping(context, {"targum:places": {hash_: {"section": "2", "segment": "", "at": 50}}})
        page = context.new_page()
        theirs = {
            "hash": hash_,
            "section": "3",
            "path": "",
            "segment": "s3-2",
            "seconds": 0,
            "at": 900,
        }
        answering(page, [theirs])
        page.goto(address(three_chapters / "index.html"))
        page.wait_for_function(
            "(want) => document.getElementById('start')"
            ".getAttribute('href').split('?')[0] === want",
            arg=third,
        )
        assert page.locator("#start").inner_text() == "Continue"
        kept = page.evaluate("() => JSON.parse(localStorage.getItem('targum:places'))")
        assert kept[hash_]["section"] == "3" and kept[hash_]["segment"] == "s3-2"
    finally:
        context.close()


def test_an_older_account_place_does_not_move_continue(browser, three_chapters) -> None:  # noqa: F811
    context = opened(browser)
    page = context.new_page()
    try:
        page.goto(address(three_chapters / "index.html"))
        hash_ = page.locator(".toc[data-document]").get_attribute("data-document")
        second = page.locator('[data-chapter="2"] a').get_attribute("href")
        context.close()

        context = opened(browser)
        keeping(context, {"targum:places": {hash_: {"section": "2", "segment": "", "at": 900}}})
        page = context.new_page()
        answering(page, [{"hash": hash_, "section": "3", "segment": "", "seconds": 0, "at": 50}])
        page.goto(address(three_chapters / "index.html"))
        page.wait_for_function("() => document.getElementById('start').textContent === 'Continue'")
        page.wait_for_timeout(300)
        assert page.locator("#start").get_attribute("href").split("?")[0] == second
    finally:
        context.close()


def test_a_part_opens_on_the_sentence_another_device_left_it_at(browser, tmp_path) -> None:  # noqa: F811
    """No place for this page in this browser, and the text's place — handed over by the
    contents page, from the account — names a sentence well down this part. The page
    opens with that sentence on the screen, and writes the place back as its own."""
    built = chapter(tmp_path / "reader")
    context = opened(browser)
    page = context.new_page()
    try:
        page.goto(address(built))
        page.wait_for_selector(".pair")
        facts = page.evaluate(
            """() => {
              const data = JSON.parse(document.getElementById('targum-data').textContent);
              const pairs = [...document.querySelectorAll('.pair[data-id]')];
              return {
                hash: data.document || location.pathname,
                section: String(data.section || 1),
                deep: pairs[Math.floor(pairs.length * 0.8)].getAttribute('data-id'),
              };
            }"""
        )
        context.close()

        context = opened(browser)
        far = {"section": facts["section"], "path": "", "segment": facts["deep"], "at": 900}
        keeping(context, {"targum:places": {facts["hash"]: far}})
        page = context.new_page()
        page.goto(address(built))
        page.wait_for_selector(".pair")
        page.wait_for_function("() => window.scrollY > 2")
        box = page.evaluate(
            '(id) => document.querySelector(`.pair[data-id="${id}"]`).getBoundingClientRect().top',
            facts["deep"],
        )
        assert 0 <= box <= page.viewport_size["height"], "the sentence is on the screen"
        kept = page.evaluate("() => JSON.parse(localStorage.getItem('targum:places'))")
        assert kept[facts["hash"]]["segment"] == facts["deep"], "opening kept the sentence"
    finally:
        context.close()


@pytest.mark.parametrize("its_own", [False, True], ids=["nothing-here", "older-here"])
def test_a_part_opened_signed_in_takes_the_sentence_the_account_holds(
    browser,  # noqa: F811
    tmp_path,
    its_own: bool,
) -> None:
    """The phone, signed in, opens a part straight from a link — not from Continue — with
    nothing of this text in its own store, or with an older sentence of its own. The laptop
    left the reader well down the part a minute ago. Opening the part must not write a
    place of its own, at the top and newer, over the account's sentence before the account
    has answered: the page waits for the answer, opens on the laptop's sentence, and sends
    nothing newer that would undo it."""
    import time

    built = chapter(tmp_path / "reader")
    context = opened(browser)
    page = context.new_page()
    try:
        page.goto(address(built))
        page.wait_for_selector(".pair")
        facts = page.evaluate(
            """() => {
              const data = JSON.parse(document.getElementById('targum-data').textContent);
              const pairs = [...document.querySelectorAll('.pair[data-id]')];
              return {
                hash: data.document || location.pathname,
                section: String(data.section || 1),
                deep: pairs[Math.floor(pairs.length * 0.8)].getAttribute('data-id'),
                early: pairs[Math.floor(pairs.length * 0.3)].getAttribute('data-id'),
                first: pairs[0].getAttribute('data-id'),
              };
            }"""
        )
        context.close()

        laptop = {
            "hash": facts["hash"],
            "section": facts["section"],
            "path": "",
            "segment": facts["deep"],
            "seconds": 0,
            "at": int(time.time() * 1000) - 60_000,
            "seen": int(time.time() * 1000) - 60_000,
        }
        pushed: list[dict] = []

        def on_me(route) -> None:
            body = {"signedIn": True, "email": "d@x.test", "reads": ["en"], "learning": ["he"]}
            route.fulfill(status=200, content_type="application/json", body=json.dumps(body))

        def on_sync(route, request) -> None:
            pushed.append(json.loads(request.post_data or "{}"))
            body = {"signedIn": True, "revision": 1, "places": [laptop]}
            route.fulfill(status=200, content_type="application/json", body=json.dumps(body))

        context = opened(browser)
        stored: dict[str, object] = {
            "targum:sync": {"email": "d@x.test", "revision": 0, "pushed": 0}
        }
        if its_own:
            # Where the phone stopped yesterday, a third of the way down.
            yesterday = laptop["at"] - 86_400_000
            key = f"{facts['hash']}/{facts['first']}"
            stored["targum:place"] = {key: {"segment": facts["early"], "at": yesterday}}
            stored["targum:places"] = {
                facts["hash"]: {
                    "section": facts["section"],
                    "path": "",
                    "segment": facts["early"],
                    "seconds": 0,
                    "at": yesterday,
                }
            }
        keeping(context, stored)
        page = context.new_page()
        page.route("**/account/me*", on_me)
        page.route("**/sync*", on_sync)
        page.route("**/readers*", lambda route: route.fulfill(status=404, body="{}"))
        page.goto(address(built))
        page.wait_for_selector(".pair")
        page.wait_for_function(
            '(id) => { const r = document.querySelector(`.pair[data-id="${id}"]`)'
            ".getBoundingClientRect(); return r.top >= 0 && r.top <= innerHeight; }",
            arg=facts["deep"],
            timeout=5000,
        )
        box = page.evaluate(
            '(id) => document.querySelector(`.pair[data-id="${id}"]`).getBoundingClientRect().top',
            facts["deep"],
        )
        assert 0 <= box <= page.viewport_size["height"], "the laptop's sentence is on the screen"
        kept = page.evaluate("() => JSON.parse(localStorage.getItem('targum:places'))")
        assert kept[facts["hash"]]["segment"] == facts["deep"], "the account's sentence is kept"
        for body in pushed:
            for place in body.get("places") or []:
                if place.get("segment") != facts["deep"]:
                    assert place["at"] < laptop["at"], "nothing newer went up over it"
    finally:
        context.close()
