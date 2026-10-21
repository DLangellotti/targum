"""A portion's reader reads on in the order of the book, in a browser (targum-internal#446).

The last aliyah's pager leads on to the next portion's first and the first aliyah's back
to the last of the one before, as links written into the page at build time: the page
asks nobody which portion is next, only for its words, to count them. Next Shabbat's is
offered at the end of a haftarah instead, which belongs to a Shabbat rather than to the
book (targum-internal#416). Served under a reading's own address, the way the box serves it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from test_reader_browser import browser, chapter, coin, opened  # noqa: F401

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


def open_at(
    browser,  # noqa: F811
    reader: Path,
    name: str,
    answer: dict | None = None,
    seeded: str = "",
    folder: str = FOLDER,
):
    context = opened(browser)
    if seeded:
        context.add_init_script(seeded)
    page = context.new_page()
    asked: list[str] = []

    def serve(route, request):
        asked.append(request.url)
        path = request.url.split("?")[0].removeprefix(ORIGIN)
        if path.startswith("/parasha/next/"):
            return route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(answer if answer is not None else {"next": None}),
            )
        if not path.startswith(folder):
            return route.fulfill(status=200, body="<html>elsewhere</html>")
        target = reader / (path.removeprefix(folder) or "index.html")
        if not target.is_file():
            return route.fulfill(status=404, body="not found")
        return route.fulfill(status=200, path=str(target), content_type="text/html")

    page.route(ORIGIN + "/**", serve)
    page.goto(ORIGIN + folder + name + "?k=test")
    page.wait_for_selector(".pair")
    return context, page, asked


def noach(words: list[str] | None, href: str = "/parasha/read/noach/reader/index.html") -> dict:
    offered: dict[str, object] = {
        "slug": "noach",
        "name": "Noach",
        "hebrew": "נח",
        "href": href,
        "page": "/parasha/noach",
    }
    if words is not None:
        offered["lemmas"] = words
    return {"next": offered}


#: Two words known and one still being learned, which is not counted, as in the header.
KNOWN = {coin(0): {"status": 9}, coin(1): {"status": 9}, coin(2): {"status": 2}}
SEEDED = f"localStorage.setItem('targum:vocab:he', {json.dumps(json.dumps(KNOWN))});"


def test_the_last_aliyah_reads_on_into_the_next_portion(browser, portion: Path) -> None:  # noqa: F811
    words = [coin(0), coin(1), coin(2), "תבה"]
    context, page, asked = open_at(
        browser, portion, "sec-0002.html", noach(words, AROUND["after"]["href"]), SEEDED
    )
    onward = page.locator(".pager a.next")
    assert onward.get_attribute("href") == "/parasha/read/noach/reader/sec-0001.html?k=test"
    assert onward.inner_text() == "נֹחַ"
    # Another text: nothing is bought ahead for it, and next Shabbat is not asked: only
    # the book's next, for its words.
    assert onward.get_attribute("data-next") is None
    page.wait_for_selector("#next-up.beyond .next-up-known", state="attached")
    assert not [url for url in asked if "/chapter" in url]
    (question,) = [url for url in asked if "/parasha/next/" in url]
    assert question.startswith(ORIGIN + "/parasha/next/bereshit?order=book")
    assert page.locator("#next-shabbat").count() == 0
    # The offer at the foot names it once the aliyah is finished, and not before, with
    # how many of its words are known.
    offer = page.locator("#next-up.beyond")
    assert offer.is_hidden()
    assert "Noach" in offer.locator(".next-up-link").inner_text()
    assert offer.locator(".next-up-link").get_attribute("href") == (
        "/parasha/read/noach/reader/sec-0001.html?k=test"
    )
    assert offer.locator(".next-up-known").text_content() == "You already know 2 of its words."
    onward.click()
    page.wait_for_url(ORIGIN + "/parasha/read/noach/reader/sec-0001.html?k=test")
    context.close()


def test_signed_out_the_next_portion_stands_without_a_count(browser, portion: Path) -> None:  # noqa: F811
    context, page, asked = open_at(browser, portion, "sec-0002.html", noach(None), SEEDED)
    page.wait_for_timeout(300)
    assert [url for url in asked if "/parasha/next/bereshit?order=book" in url]
    assert page.locator("#next-up.beyond .next-up-known").count() == 0
    context.close()


def test_the_first_aliyah_goes_back_to_the_last_of_the_portion_before(
    browser,  # noqa: F811
    portion: Path,
) -> None:
    context, page, asked = open_at(browser, portion, "sec-0001.html")
    back = page.locator(".pager a.prev")
    assert back.get_attribute("href") == "/parasha/read/vzot-haberachah/reader/sec-0007.html?k=test"
    # Its own next is its own second aliyah, as it always was.
    assert page.locator(".pager a.next").get_attribute("href") == "sec-0002.html?k=test"
    assert page.locator("#next-up.beyond").count() == 0
    page.wait_for_timeout(300)
    assert not [url for url in asked if "/parasha/next/" in url]
    context.close()


HAFTARAH = "/parasha/read/haftarah-h-bereshit/reader/"


@pytest.fixture(scope="module")
def haftarah(tmp_path_factory: pytest.TempPathFactory) -> Path:
    # One section, so it is the last.
    return chapter(tmp_path_factory.mktemp("haftarah") / "reader")


def test_a_haftarah_ends_on_next_shabbat_and_counts_what_you_know(
    browser,  # noqa: F811
    haftarah: Path,
) -> None:
    words = [coin(0), coin(1), coin(2), "תבה"]
    seeded = SEEDED + "localStorage.setItem('targum:schedule', 'israel');"
    context, page, asked = open_at(
        browser, haftarah.parent, haftarah.name, noach(words), seeded, HAFTARAH
    )
    page.wait_for_selector("#next-shabbat")
    (question,) = [url for url in asked if "/parasha/next/" in url]
    assert question.startswith(ORIGIN + "/parasha/next/haftarah-h-bereshit?schedule=israel")
    offer = page.locator("#next-shabbat")
    assert offer.locator(".next-up-lead").inner_text() == "Next Shabbat"
    link = offer.locator(".next-up-link")
    assert "נח" in link.inner_text() and "Noach" in link.inner_text()
    assert link.get_attribute("href") == "/parasha/read/noach/reader/index.html?k=test"
    assert offer.locator(".next-up-known").inner_text() == "You already know 2 of its words."
    # It ends the page: after the foot.
    assert page.evaluate(
        "() => document.getElementById('foot').compareDocumentPosition("
        "document.getElementById('next-shabbat')) & Node.DOCUMENT_POSITION_FOLLOWING"
    )
    context.close()


def test_a_haftarah_with_nothing_known_offers_next_shabbat_without_a_count(
    browser,  # noqa: F811
    haftarah: Path,
) -> None:
    context, page, asked = open_at(
        browser, haftarah.parent, haftarah.name, noach(None), "", HAFTARAH
    )
    page.wait_for_selector("#next-shabbat")
    assert [url for url in asked if "?schedule=diaspora" in url]
    assert page.locator("#next-shabbat .next-up-known").is_hidden()
    context.close()
