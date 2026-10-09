"""The Russian portion page in a browser, and the wait for its PDF (QA, 2026-10-05).

Against the real server and the real corpus `test_parasha_russian` builds, because what
is under test is a page and the frame inside it, and the frame is the reader built in
Russian. Only the PDF itself is stood in for: its making is `test_parasha_sheet`'s, and
what is asked here is what the page says while it waits.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from test_parasha_russian import SLUG, built, serving  # noqa: F401
from test_reader_browser import browser  # noqa: F401

pytest.importorskip("playwright.sync_api", reason="Playwright is not installed")

PDF = b"%PDF-1.4\n%%EOF\n"
BUSY = "() => document.querySelector('a.series-pdf').ariaBusy === 'true'"


def opened(browser, port: int, path: str):  # noqa: F811
    context = browser.new_context(viewport={"width": 1280, "height": 900}, accept_downloads=True)
    page = context.new_page()
    page.goto(f"http://127.0.0.1:{port}{path}")
    return context, page


def test_the_russian_page_opens_a_reader_in_russian(browser, serving: int) -> None:  # noqa: F811
    """No frame since 2026-10-09 (design.md §12): the press opens the reader built in
    Russian, and the column it opens on is the Russian."""
    context, page = opened(browser, serving, f"/parasha/{SLUG}?lang=ru")
    try:
        page.locator(".series-go .btn.filled").click()
        page.wait_for_url(f"**/parasha/read/{SLUG}-ru/reader/sec-0001.html")
        page.locator(".pair").first.wait_for()
        assert page.evaluate("document.documentElement.lang") == "ru"
        column = page.locator(".pair .tr", has_text="Русский стих").first
        assert column.is_visible()
        assert column.get_attribute("lang") == "ru"
        assert page.locator(".pair .tr", has_text="verse 1").count() == 0, "not the English"
    finally:
        context.close()


def held_pdf(page, answer: dict):
    """Hold every request for the sheet until the test answers it."""
    waiting: list = []
    page.route(f"**/parasha/{SLUG}.pdf*", lambda route: waiting.append(route))
    return waiting


def test_the_download_says_it_is_preparing_until_the_file_arrives(
    browser,  # noqa: F811
    serving: int,  # noqa: F811
) -> None:
    context, page = opened(browser, serving, f"/parasha/{SLUG}?lang=ru")
    try:
        waiting = held_pdf(page, {})
        button = page.locator("a.series-pdf")
        assert button.get_attribute("aria-label") == "Скачать PDF"
        button.click()
        page.wait_for_function(BUSY)
        assert button.get_attribute("aria-label") == "Готовим PDF…"
        assert page.locator(".series-pdf-note").inner_text() == "Готовим PDF…"
        page.wait_for_timeout(200)
        assert len(waiting) == 1, "asked once"
        asked = waiting[0].request.url
        assert "lang=ru" in asked, "the reader's own defaults, in the page's language"
        # A second press while it is preparing asks nothing more.
        button.click()
        page.wait_for_timeout(200)
        assert len(waiting) == 1
        with page.expect_download() as arriving:
            waiting[0].fulfill(
                status=200,
                body=PDF,
                headers={
                    "Content-Type": "application/pdf",
                    "Content-Disposition": f'attachment; filename="{SLUG}-2026-09-05.pdf"',
                },
            )
        assert arriving.value.suggested_filename == f"{SLUG}-2026-09-05.pdf"
        # The file itself, all of it, before anything closes. The download event fires
        # when the file starts, and closing the context cancels every download it has
        # seen and disposes the context around them. Closed on a download that may not
        # have finished, CI's Chromium died in that close — twice in PRs, three times in
        # 4,800 runs looped on a runner, and not once in 3,600 with this wait
        # (targum-internal#427, 2026-10-07). It is also the stronger test: the reader
        # gets the PDF.
        assert Path(arriving.value.path()).read_bytes() == PDF
        page.wait_for_function(
            "() => !document.querySelector('a.series-pdf').hasAttribute('aria-busy')"
        )
        assert button.get_attribute("aria-label") == "Скачать PDF"
        assert page.locator(".series-pdf-note").is_hidden()
    finally:
        context.close()


def test_a_sheet_the_box_cannot_make_says_so_in_one_sentence(
    browser,  # noqa: F811
    serving: int,  # noqa: F811
) -> None:
    context, page = opened(browser, serving, f"/parasha/{SLUG}?lang=ru")
    try:
        waiting = held_pdf(page, {})
        page.locator("a.series-pdf").click()
        page.wait_for_function(BUSY)
        waiting[0].fulfill(status=503, body="no", content_type="text/plain")
        note = page.locator(".series-pdf-note")
        page.wait_for_function(
            "() => document.querySelector('.series-pdf-note').textContent.indexOf('PDF.') > 0"
        )
        assert note.inner_text() == "Сейчас мы не можем сделать PDF. Попробуйте через минуту."
        assert note.get_attribute("role") == "status"
        assert page.locator("a.series-pdf").get_attribute("aria-label") == "Скачать PDF"
    finally:
        context.close()


def test_in_english_the_wait_is_said_in_english(browser, serving: int) -> None:  # noqa: F811
    context, page = opened(browser, serving, f"/parasha/{SLUG}")
    try:
        held_pdf(page, {})
        button = page.locator("a.series-pdf")
        button.click()
        page.wait_for_function(BUSY)
        assert button.get_attribute("aria-label") == "Preparing PDF…"
    finally:
        context.close()
