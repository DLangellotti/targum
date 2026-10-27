"""The Sentences tab in a browser (targum-internal#534; design.md §12, "Sentences: dictation
and fill the gap", 2026-10-27): a line written down is shown back with the differences
marked, a gap is answered with the word, and nothing is ever sent."""

from __future__ import annotations

import json

import pytest
from test_pages_browser import TOKEN, browser

from targum.render.builder import list_page

__all__ = ["browser"]

SENTENCES = {
    "signedIn": True,
    "dictation": [
        {"key": "a:s1", "line": "הַיֶּלֶד הָלַךְ אֶל־הַבַּיִת.", "src": "/heard?t=x", "start": 1.0,
         "end": 3.5, "translation": "The boy went home.", "title": "A Book", "chapter": 0,
         "name": "a", "language": "he"},
    ],
    "gaps": [
        {"lemma": "בית", "line": "הוא בַּבַּיִת עכשיו", "start": 4, "end": 13, "word": "בַּבַּיִת",
         "translation": "He is at home now.", "title": "A Book", "chapter": 2, "name": "a",
         "language": "he"},
    ],
}  # fmt: skip


@pytest.mark.parametrize("width", [390, 1280])
def test_a_line_written_down_is_shown_back_with_the_differences_marked(browser, width: int) -> None:
    html = list_page(TOKEN, "sentences")
    sent: list[str] = []

    def answer(route, request):
        if request.method != "GET":
            sent.append(request.url)
        if request.resource_type == "document":
            return route.fulfill(status=200, content_type="text/html", body=html)
        if "/account/sentences" in request.url:
            return route.fulfill(
                status=200, content_type="application/json", body=json.dumps(SENTENCES)
            )
        route.fulfill(status=200, content_type="application/json", body="{}")

    context = browser.new_context(viewport={"width": width, "height": 900})
    page = context.new_page()
    page.add_init_script("localStorage.setItem('targum:language', 'he')")
    page.route("http://words.test/**", answer)
    page.goto(f"http://words.test/sentences?k={TOKEN}")
    page.wait_for_selector("#sentence-round:not([hidden]) .sentence-field")
    kinds = page.eval_on_selector_all(
        "#sentence-kinds .grammar-spot", "(rows) => rows.map((r) => r.dataset.kind)"
    )
    assert kinds == ["dictation", "gaps"]
    assert page.text_content("#sentence-round-heading") == "Dictation"
    assert page.text_content("#sentence-round-at") == "1 of 1"
    assert page.is_visible(".sentence-play")
    assert not page.is_visible(".practise-translation"), "the translation waits for Check"

    page.fill(".sentence-field", "הילד הלך לבית")
    page.click(".sentence-check")
    page.wait_for_selector(".grammar-feedback")
    missed = page.eval_on_selector_all(".said-missed", "(m) => m.map((x) => x.textContent)")
    assert missed == ["אֶל", "הַבַּיִת."]
    assert page.eval_on_selector_all(".said-extra", "(m) => m.map((x) => x.textContent)") == [
        "לבית"
    ]
    assert page.text_content(".practise-translation") == "The boy went home."
    page.click(".sentence-next")
    page.wait_for_selector(".grammar-done")

    page.click("#sentence-kinds [data-kind='gaps'] .grammar-go")
    page.wait_for_selector(".sentence-gap")
    assert page.text_content("#sentence-round-heading") == "Fill the gap"
    page.fill(".sentence-field", "בבית")
    page.keyboard.press("Enter")
    page.wait_for_selector(".grammar-verdict")
    assert page.text_content(".grammar-verdict") == "Yes, בַּבַּיִת."
    assert page.text_content(".practise-line mark") == "בַּבַּיִת"
    body = page.text_content("#sentence-round-body") or ""
    context.close()
    for verdict in ("%", "score", "due", "streak"):
        assert verdict not in body.lower()
    assert sent == [], "nothing is sent: the comparison is made on the page"
