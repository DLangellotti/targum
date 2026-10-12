"""A portion's reader reads on in the order of the book, in a browser (targum-internal#446).

The last aliyah's pager leads on to the next portion's first and the first aliyah's back
to the last of the one before, as links written into the page at build time: the page
asks nobody which portion is next, and it no longer offers next Shabbat's (that is the
portion page's). Served under a portion's own address, the way the box serves it.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from test_reader_browser import browser, chapter, opened  # noqa: F401

ORIGIN = "http://targum.test"
FOLDER = "/parasha/read/bereshit/reader/"

AROUND = {
    "before": {
        "href": "/parasha/read/vzot-haberachah/reader/sec-0007.html",
        "hebrew": "וְזֹאת הַבְּרָכָה",
        "name": "Vezot Haberakhah",
        "page": "/parasha/vzot-haberachah",
    },
    "after": {
        "href": "/parasha/read/noach/reader/sec-0001.html",
        "hebrew": "נֹחַ",
        "name": "Noach",
        "page": "/parasha/noach",
    },
}


@pytest.fixture(scope="module")
def portion(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Two aliyot, so the first has only a previous past its end and the last only a next."""
    first = chapter(tmp_path_factory.mktemp("bereshit") / "reader", parts=2, beyond=AROUND)
    return first.parent


def open_at(browser, reader: Path, name: str):  # noqa: F811
    context = opened(browser)
    page = context.new_page()
    asked: list[str] = []

    def serve(route, request):
        asked.append(request.url)
        path = request.url.split("?")[0].removeprefix(ORIGIN)
        if not path.startswith(FOLDER):
            return route.fulfill(status=200, body="<html>elsewhere</html>")
        target = reader / (path.removeprefix(FOLDER) or "index.html")
        if not target.is_file():
            return route.fulfill(status=404, body="not found")
        return route.fulfill(status=200, path=str(target), content_type="text/html")

    page.route(ORIGIN + "/**", serve)
    page.goto(ORIGIN + FOLDER + name + "?k=test")
    page.wait_for_selector(".pair")
    return context, page, asked


def test_the_last_aliyah_reads_on_into_the_next_portion(browser, portion: Path) -> None:  # noqa: F811
    context, page, asked = open_at(browser, portion, "sec-0002.html")
    onward = page.locator(".pager a.next")
    assert onward.get_attribute("href") == "/parasha/read/noach/reader/sec-0001.html?k=test"
    assert onward.inner_text() == "נֹחַ"
    # Another text: nothing is bought ahead for it, and nothing asks what next Shabbat is.
    assert onward.get_attribute("data-next") is None
    page.wait_for_timeout(300)
    assert not [url for url in asked if "/parasha/next/" in url or "/chapter" in url]
    assert page.locator("#next-shabbat").count() == 0
    # The offer at the foot names it once the aliyah is finished, and not before.
    offer = page.locator("#next-up.beyond")
    assert offer.is_hidden()
    assert "Noach" in offer.locator(".next-up-link").inner_text()
    assert offer.locator(".next-up-link").get_attribute("href") == (
        "/parasha/read/noach/reader/sec-0001.html?k=test"
    )
    onward.click()
    page.wait_for_url(ORIGIN + "/parasha/read/noach/reader/sec-0001.html?k=test")
    context.close()


def test_the_first_aliyah_goes_back_to_the_last_of_the_portion_before(
    browser,  # noqa: F811
    portion: Path,
) -> None:
    context, page, _ = open_at(browser, portion, "sec-0001.html")
    back = page.locator(".pager a.prev")
    assert back.get_attribute("href") == "/parasha/read/vzot-haberachah/reader/sec-0007.html?k=test"
    # Its own next is its own second aliyah, as it always was.
    assert page.locator(".pager a.next").get_attribute("href") == "sec-0002.html?k=test"
    assert page.locator("#next-up.beyond").count() == 0
    context.close()
