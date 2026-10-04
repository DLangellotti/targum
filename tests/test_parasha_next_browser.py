"""Next Shabbat's portion at the end of the last aliyah, in a browser (targum-internal#416).

The page asks `/parasha/next/<folder>` on the schedule the browser keeps and counts the
answer's words against its own word list by the header's rule. Served under a portion's
own address, because that address is how the page knows it is one.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from test_reader_browser import browser, chapter, coin, opened  # noqa: F401

ORIGIN = "http://targum.test"
FOLDER = "/parasha/read/bereshit/reader/"


def noach(words: list[str] | None) -> dict[str, object]:
    offered: dict[str, object] = {
        "slug": "noach",
        "name": "Noach",
        "hebrew": "נח",
        "href": "/parasha/read/noach/reader/index.html",
        "page": "/parasha/noach",
    }
    if words is not None:
        offered["lemmas"] = words
    return {"next": offered}


def opened_at_the_end(browser, reader: Path, answer: dict, seeded: str = ""):  # noqa: F811
    context = opened(browser)
    if seeded:
        context.add_init_script(seeded)
    page = context.new_page()
    asked: list[str] = []

    def serve(route, request):
        if "/parasha/next/" in request.url:
            asked.append(request.url)
            return route.fulfill(
                status=200, content_type="application/json", body=json.dumps(answer)
            )
        name = request.url.split("?")[0].removeprefix(ORIGIN + FOLDER) or "index.html"
        target = reader.parent / name
        if not target.is_file():
            return route.fulfill(status=404, body="not found")
        return route.fulfill(status=200, path=str(target), content_type="text/html")

    page.route(ORIGIN + "/**", serve)
    page.goto(ORIGIN + FOLDER + reader.name + "?k=test")
    page.wait_for_selector(".pair")
    return context, page, asked


@pytest.fixture(scope="module")
def portion(tmp_path_factory: pytest.TempPathFactory) -> Path:
    # One section, so it is the last: a haftarah, or a portion's last aliyah.
    return chapter(tmp_path_factory.mktemp("bereshit") / "reader")


def test_the_last_aliyah_offers_next_shabbat_and_counts_what_you_know(
    browser,  # noqa: F811
    portion: Path,
) -> None:
    known = {coin(0): {"status": 9}, coin(1): {"status": 9}, coin(2): {"status": 2}}
    seeded = (
        f"localStorage.setItem('targum:vocab:he', {json.dumps(json.dumps(known))});"
        "localStorage.setItem('targum:schedule', 'israel');"
    )
    words = [coin(0), coin(1), coin(2), "תבה"]
    context, page, asked = opened_at_the_end(browser, portion, noach(words), seeded)
    page.wait_for_selector("#next-shabbat")
    (question,) = asked
    assert question.startswith(ORIGIN + "/parasha/next/bereshit?schedule=israel")
    offer = page.locator("#next-shabbat")
    assert offer.locator(".next-up-lead").inner_text() == "Next Shabbat"
    link = offer.locator(".next-up-link")
    assert "נח" in link.inner_text() and "Noach" in link.inner_text()
    assert link.get_attribute("href") == "/parasha/read/noach/reader/index.html?k=test"
    # Known is known: a word still being learned is not counted, as in the header.
    assert offer.locator(".next-up-known").inner_text() == "You already know 2 of its words."
    # It ends the page: after the foot.
    assert page.evaluate(
        "() => document.getElementById('foot').compareDocumentPosition("
        "document.getElementById('next-shabbat')) & Node.DOCUMENT_POSITION_FOLLOWING"
    )
    context.close()


def test_signed_out_or_with_nothing_known_the_offer_stands_without_a_count(
    browser,  # noqa: F811
    portion: Path,
) -> None:
    # Signed out: the answer carries no words.
    context, page, asked = opened_at_the_end(browser, portion, noach(None))
    page.wait_for_selector("#next-shabbat")
    assert asked[0].startswith(ORIGIN + "/parasha/next/bereshit?schedule=diaspora")
    assert page.locator("#next-shabbat .next-up-known").is_hidden()
    context.close()
    # Signed in, with nothing known yet: still no "you know 0".
    context, page, _ = opened_at_the_end(browser, portion, noach([coin(0), "תבה"]))
    page.wait_for_selector("#next-shabbat")
    assert page.locator("#next-shabbat .next-up-known").is_hidden()
    context.close()


def test_a_section_that_is_not_the_last_asks_nothing(
    browser,  # noqa: F811
    tmp_path: Path,
) -> None:
    first = chapter(tmp_path / "reader", parts=2).parent / "sec-0001.html"
    context, page, asked = opened_at_the_end(browser, first, noach(None))
    page.wait_for_timeout(300)
    assert not asked and page.locator("#next-shabbat").count() == 0
    context.close()
