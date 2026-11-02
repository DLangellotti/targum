"""A noun's root and mishkal on the word card, in a real browser (targum-internal#593,
#596; design.md §12, "A noun's card names its root and mishkal", 2026-11-02).

The lexicon rows here are made up for the test; the real lexicons are private. The page
is opened served and signed in with `/word/met` answered, at a phone's width and a
desk's. Set `TARGUM_ROOT_SHOTS` to a folder to keep a picture of each card.

Skips itself unless Playwright and its Chromium are installed, as
`test_reader_browser.py` does, whose browser this borrows.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest
import test_reader_browser
from test_reader_browser import opened

from targum.models import (
    Annotation,
    Block,
    BlockKind,
    Document,
    Glossary,
    Segment,
    SegmentedDocument,
    Token,
    Translation,
)
from targum.render import render

browser = test_reader_browser.browser

SHOTS = os.environ.get("TARGUM_ROOT_SHOTS", "")

HEBREW = {
    "version": "roots/1+prompt/1-test",
    "language": "he",
    "lemmas": {
        "מכתב": {
            "root": "כ־ת־ב",
            "pattern": "מִקְטָל",
            "borrowed": False,
            "meaning": "write",
            "transparent": "yes",
        },
        "חשבון": {
            "root": "ח־ש־ב",
            "pattern": "קֶטְלוֹן",
            "borrowed": False,
            "meaning": "think, count",
            "transparent": "partly",
        },
        "טלפון": {
            "root": None,
            "pattern": None,
            "borrowed": True,
            "meaning": None,
            "transparent": None,
        },
        "כתב": {
            "root": "כ־ת־ב",
            "pattern": "פעל",
            "borrowed": False,
            "meaning": "write",
            "transparent": "yes",
        },
    },
}
RUSSIAN = {
    "version": "ru-roots/1+prompt/1-test",
    "language": "ru",
    "lemmas": {
        "приходить": {
            "roots": [{"morph": "ход", "variants": ["хож", "ш"], "sense": "go"}],
            "prefixes": ["при"],
            "suffixes": ["и"],
            "transparency": "transparent",
            "borrowed": False,
        }
    },
}

HE_WORDS = [
    ("מכתב", "NOUN", "", "letter"),
    ("חשבון", "NOUN", "", "bill"),
    ("טלפון", "NOUN", "", "telephone"),
    ("כתב", "VERB", "כתב", "to write"),
]


@pytest.fixture(scope="module")
def lexicons(tmp_path_factory: pytest.TempPathFactory) -> Path:
    folder = tmp_path_factory.mktemp("lexicons")
    for language, body in (("he", HEBREW), ("ru", RUSSIAN)):
        (folder / f"roots-{language}.json").write_text(
            json.dumps(body, ensure_ascii=False), encoding="utf-8"
        )
    return folder


def _page(
    folder: Path,
    lexicons: Path,
    monkeypatch: pytest.MonkeyPatch,
    language: str,
    words: list[tuple[str, str, str, str]],
    interface: str = "en",
) -> Path:
    monkeypatch.setenv("TARGUM_ROOTS_HE", str(lexicons / "roots-he.json"))
    monkeypatch.setenv("TARGUM_ROOTS_RU", str(lexicons / "roots-ru.json"))
    text = " ".join(w for w, _, _, _ in words)
    tokens, at = [], 0
    for word, pos, root, _ in words:
        tokens.append(
            Token(
                start=at,
                end=at + len(word),
                surface=word,
                lemma=word,
                band=2,
                pos=pos,
                root=root or None,
                binyan="פעל" if root else None,
            )
        )
        at += len(word) + 1
    segment = Segment(id="0000.000-aaaaaa", block_id="b0", block_index=0, index=0, text=text)
    return render(
        Document(
            source="memory",
            title="A page",
            language=language,
            blocks=[Block(id="b0", kind=BlockKind.paragraph, text=text)],
            content_hash="h",
        ),
        SegmentedDocument(
            document_hash="h", language=language, segmenter="t/1", segments=[segment]
        ),
        [
            Translation(
                name="Rendering",
                document_hash="h",
                source_language=language,
                target_language=interface,
                provider="null",
                segments={segment.id: "A line."},
            )
        ],
        folder / "reader",
        annotation=Annotation(
            document_hash="h",
            language=language,
            annotator="t/1",
            method="frequency",
            method_note="a test",
            tokens={segment.id: tokens},
        ),
        glossaries={
            interface: Glossary(
                source_language=language,
                target_language=interface,
                provider="test",
                entries={w: gloss for w, _, _, gloss in words},
            )
        },
    )[0]


ME = {"signedIn": True, "email": "r@example.com", "revision": 0, "counts": {}, "occurrences": True}


def _card(chromium: Any, page_file: Path, lemma: str, width: int, family: int = 6) -> Any:
    """Open the page served and signed in, tap the word, and hand back the page."""
    html = page_file.read_text(encoding="utf-8")
    said = {"here": 2, "tanakh": 0, "met": [], "more": 0}
    if family:
        said["family"] = {"met": family, "known": 3, "words": []}
    context = opened(chromium, viewport={"width": width, "height": 860})
    page = context.new_page()

    def answer(route: Any, request: Any) -> None:
        if "/account/me" in request.url:
            route.fulfill(status=200, content_type="application/json", body=json.dumps(ME))
        elif "/word/met" in request.url:
            route.fulfill(status=200, content_type="application/json", body=json.dumps(said))
        elif any(p in request.url for p in ("/sync", "/gloss", "/events")):
            route.fulfill(status=200, content_type="application/json", body="{}")
        else:
            route.fulfill(status=200, content_type="text/html", body=html)

    page.route("http://reader.test/**", answer)
    page.goto("http://reader.test/reader/a-build/reader/index.html?k=test")
    page.wait_for_selector(".pair")
    page.wait_for_function("() => window.TargumSync && window.TargumSync.who")
    # A noun's rows are drawn by the rest of the reader, which arrives after the faces.
    page.wait_for_function("() => typeof window.targumReaderRest === 'function'")
    tap = f"() => [...document.querySelectorAll('.w')].find((w) => w.textContent === '{lemma}')"
    page.evaluate(tap + ".click()")
    page.wait_for_selector(".gloss-card .card-facts")
    page.wait_for_timeout(400)
    return context, page


def _facts(page: Any) -> list[str]:
    return page.evaluate(
        "() => [...document.querySelectorAll("
        "'.gloss-card .card-facts dt, .gloss-card .card-facts dd')]"
        ".map((n) => n.textContent.trim())"
    )


def _shot(page: Any, name: str) -> None:
    if SHOTS:
        Path(SHOTS).mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(Path(SHOTS) / f"{name}.png"))


@pytest.mark.parametrize("width", [390, 1440])
def test_a_hebrew_noun_shows_its_root_mishkal_and_family(
    browser: Any, lexicons: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, width: int
) -> None:
    page_file = _page(tmp_path, lexicons, monkeypatch, "he", HE_WORDS)
    context, page = _card(browser, page_file, "מכתב", width)
    try:
        facts = _facts(page)
        assert "Root" in facts and "כ־ת־ב · write" in facts
        assert "Mishkal" in facts and "מִקְטָל · often a place or a thing done" in facts
        lines = page.evaluate(
            "() => [...document.querySelectorAll('.gloss-card .card-root-met')]"
            ".map((l) => l.textContent)"
        )
        assert lines == ["6 words from כ־ת־ב met, 3 known"]
        assert page.is_visible(".gloss-card .card-facts .root-open")
        _shot(page, f"noun-{width}")
    finally:
        context.close()


@pytest.mark.parametrize("width", [390, 1440])
def test_a_pattern_off_the_list_and_a_loanword(
    browser: Any, lexicons: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, width: int
) -> None:
    page_file = _page(tmp_path, lexicons, monkeypatch, "he", HE_WORDS)
    context, page = _card(browser, page_file, "חשבון", width, family=3)
    try:
        facts = _facts(page)
        assert "ח־ש־ב · think, count" in facts and "קֶטְלוֹן" in facts, "the template alone"
        _shot(page, f"pattern-only-{width}")
    finally:
        context.close()
    context, page = _card(browser, page_file, "טלפון", width, family=0)
    try:
        facts = _facts(page)
        assert facts[facts.index("Root") + 1] == "Borrowed, no Hebrew root"
        assert "Mishkal" not in facts
        assert page.query_selector(".gloss-card .card-root-met") is None
        _shot(page, f"borrowed-{width}")
    finally:
        context.close()


@pytest.mark.parametrize("width", [390, 1440])
def test_a_verb_gains_its_roots_meaning(
    browser: Any, lexicons: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, width: int
) -> None:
    page_file = _page(tmp_path, lexicons, monkeypatch, "he", HE_WORDS)
    context, page = _card(browser, page_file, "כתב", width)
    try:
        facts = _facts(page)
        assert "כ־ת־ב · write" in facts and "Binyan" in facts and "Mishkal" not in facts
        _shot(page, f"verb-{width}")
    finally:
        context.close()


@pytest.mark.parametrize("width", [390, 1440])
def test_a_russian_word_shows_its_root_spellings_and_prefix(
    browser: Any, lexicons: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, width: int
) -> None:
    words = [("приходить", "VERB", "", "to come")]
    page_file = _page(tmp_path, lexicons, monkeypatch, "ru", words)
    context, page = _card(browser, page_file, "приходить", width, family=9)
    try:
        facts = _facts(page)
        assert "ход · go · also хож, ш" in facts
        assert facts[facts.index("Prefix") + 1] == "при-"
        lines = page.evaluate(
            "() => [...document.querySelectorAll('.gloss-card .card-root-met')]"
            ".map((l) => l.textContent)"
        )
        assert lines == ["9 words from ход met, 3 known"], "a morph is not spaced with maqafs"
        _shot(page, f"russian-{width}")
    finally:
        context.close()


@pytest.mark.parametrize("width", [390, 1440])
def test_the_russian_interface_leaves_the_english_meaning_off(
    browser: Any, lexicons: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, width: int
) -> None:
    page_file = _page(tmp_path, lexicons, monkeypatch, "he", HE_WORDS, interface="ru")
    context, page = _card(browser, page_file, "מכתב", width)
    try:
        facts = _facts(page)
        assert "Корень" in facts and "כ־ת־ב" in facts, "the root alone, no English meaning"
        assert "Мишкаль" in facts and "מִקְטָל · часто место или то, что сделано" in facts
        _shot(page, f"noun-ru-{width}")
    finally:
        context.close()
