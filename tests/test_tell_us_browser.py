"""Tell us and the fault reporter, in a real browser (targum-internal#456, #457).

What a reader sees of Tell us — one box, Send, a line of thanks, at a phone's width — and
what a page sends when it breaks: the message, the path, the build, and never a query.

Skips itself without Playwright and its Chromium, as the other browser tests do.
"""

from __future__ import annotations

import json

import pytest
from test_fault_browser import browser, json_answer, served  # noqa: F401

from targum import about
from targum.render.builder import not_found_page

pytest.importorskip("playwright.sync_api", reason="Playwright is not installed")


def recording(posted: list[tuple[str, dict]], status: int = 200):
    def answer(route, request):
        if request.method == "POST":
            path = request.url.split("fault.test", 1)[1]
            posted.append((path, json.loads(request.post_data or "{}")))
        if request.url.endswith("/sync"):
            return route.fulfill(status=502, body="bad gateway")
        json_answer(route, {"kept": True}, status)

    return answer


def test_an_uncaught_error_is_reported_without_its_query(browser) -> None:  # noqa: F811
    posted: list[tuple[str, dict]] = []
    context, page, _ = served(browser, not_found_page(), "/nowhere", recording(posted))
    page.evaluate("() => { setTimeout(() => { throw new Error('boom'); }, 0); }")
    page.wait_for_timeout(300)
    context.close()

    reports = [body for path, body in posted if path == "/errors"]
    assert len(reports) == 1, posted
    report = reports[0]
    assert "boom" in report["message"]
    assert report["page"] == "/nowhere"
    assert report["build"] == about.build()
    assert "?" not in json.dumps(report)


def test_a_5xx_from_targum_is_reported_once(browser) -> None:  # noqa: F811
    posted: list[tuple[str, dict]] = []
    context, page, _ = served(browser, not_found_page(), "/nowhere", recording(posted))
    page.evaluate("() => Promise.all([fetch('/sync'), fetch('/sync')])")
    page.wait_for_timeout(300)
    context.close()

    reports = [body["message"] for path, body in posted if path == "/errors"]
    assert reports == ["HTTP 502 from /sync"], posted


@pytest.mark.parametrize("width", [390, 1280])
def test_tell_us_is_one_box_send_and_a_line_of_thanks(browser, width: int) -> None:  # noqa: F811
    posted: list[tuple[str, dict]] = []
    context, page, thrown = served(browser, not_found_page(), "/nowhere", recording(posted), width)
    page.click("main [data-tell-us]")
    page.wait_for_selector("dialog.tell-us[open]")
    drawn = page.evaluate(
        """() => {
          const box = document.querySelector('dialog.tell-us');
          const rect = box.getBoundingClientRect();
          const said = box.querySelector('textarea');
          return {
            title: box.querySelector('h2').textContent,
            label: box.querySelector('label').textContent,
            focused: document.activeElement === said,
            dir: said.getAttribute('dir'),
            presses: [...box.querySelectorAll('button')].map((b) => b.textContent),
            inside: rect.left >= 0 && rect.right <= window.innerWidth,
            sideways: document.documentElement.scrollWidth > window.innerWidth + 1,
          };
        }"""
    )
    assert drawn == {
        "title": "Tell us",
        "label": "What happened, or what would help?",
        "focused": True,
        "dir": "auto",
        "presses": ["Send", "Cancel"],
        "inside": True,
        "sideways": False,
    }

    page.click("dialog.tell-us .fault-go")
    assert page.text_content(".tell-us .fault-under") == "Write something first."
    assert not [p for p, _ in posted if p.startswith("/tell-us")], "nothing sent empty"

    page.fill("dialog.tell-us textarea", "The card covers the line")
    page.click("dialog.tell-us .fault-go")
    page.wait_for_selector(".tell-us-thanks")
    thanks = page.text_content(".tell-us-thanks")
    page.click("dialog.tell-us .fault-go")
    page.wait_for_function("() => !document.querySelector('dialog.tell-us')", timeout=2000)
    gone = True
    context.close()

    assert not thrown, thrown
    assert thanks == "Thanks for telling us. We read every message."
    assert gone
    [body] = [body for path, body in posted if path.startswith("/tell-us")]
    assert body["said"] == "The card covers the line"
    assert body["page"] == "/nowhere"
    assert body["viewport"].startswith(f"{width}x")
    assert body["build"] == about.build() and body["language"] == "en"


def test_a_refusal_from_the_server_is_said_under_the_box(browser) -> None:  # noqa: F811
    def answer(route, request):
        if "/tell-us" in request.url:
            return json_answer(route, {"error": "You'll need to sign in first."}, 401)
        json_answer(route, {})

    context, page, _ = served(browser, not_found_page(), "/nowhere", answer)
    page.click("main [data-tell-us]")
    page.fill("dialog.tell-us textarea", "hello")
    page.click("dialog.tell-us .fault-go")
    page.wait_for_selector(".tell-us .fault-under")
    said = page.text_content(".tell-us .fault-under")
    context.close()
    assert said == "You'll need to sign in first."


def test_every_fault_panel_carries_tell_us_and_out_of_credits_does_not(browser) -> None:  # noqa: F811
    context, page, _ = served(
        browser, not_found_page(), "/nowhere", lambda route, request: json_answer(route, {})
    )
    drawn = page.evaluate(
        """() => {
          const fault = window.TargumFault.panel("We couldn't read that page.", {
            act: "Try again", onAct: () => {},
          });
          const credits = window.TargumFault.panel("You've used this month's credits.", {
            topUp: true,
          });
          return [fault, credits].map((box) => !!box.querySelector('[data-tell-us]'));
        }"""
    )
    context.close()
    assert drawn == [True, False]


def test_a_stranger_is_not_offered_tell_us_on_the_missing_page() -> None:
    assert "data-tell-us" not in not_found_page(stranger=True).split("<main", 1)[1]
