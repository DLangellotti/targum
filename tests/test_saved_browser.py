"""Saved on this device, as a reader sees it (design.md §12, 2026-10-09; the §14 finish
bar, targum-internal#720).

What `test_offline_browser.py` does not pin: the desk table gives every title room and
keeps its columns in line, a device nearly full says so and puts the largest first, and a
Hebrew title is said as Hebrew. The rows are the index's as a stub hands them over, so a
title can be as long as a real one and the browser's estimate can be any size, without
saving six films first. The full device's press is pinned beside the rest of saving, in
`test_offline_browser.py`.

    uv sync --extra browser && uv run playwright install chromium
"""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("playwright.sync_api")

from test_offline import TOKEN  # noqa: E402
from test_offline_browser import Served  # noqa: E402
from test_reader_browser import browser  # noqa: E402, F401

from targum.accounts import Store  # noqa: E402
from targum.serve import Handler, Library  # noqa: E402

#: The rows as the design pass found them (`finish-saved-2026-11-14`, 04 and 05): a
#: playlist, Hebrew titles long and short, two films a size apart, an English title, and
#: two saved by hand.
ROWS: list[dict[str, Any]] = [
    {
        "id": "playlist:7",
        "kind": "playlist",
        "title": "On the bus to work every morning",
        "members": ["/reader/held-he/reader/"],
        "how": "auto",
        "bytes": 16_000_000,
        "opened": 6,
    },
    {
        "id": "/reader/news-he/reader/",
        "open": "/reader/news-he/reader/index.html",
        "kind": "article",
        "name": "news-he",
        "language": "he",
        "title": "אנרגיה מתחדשת: מה השתנה השנה בחדשות",
        "how": "auto",
        "pages": 1,
        "bytes": 300_000,
        "opened": 5,
    },
    {
        "id": "/reader/flow-he/reader/",
        "open": "/reader/flow-he/reader/index.html",
        "kind": "talk",
        "name": "flow-he",
        "title": "זורמים 1",
        "film": True,
        "withFilm": True,
        "how": "auto",
        "pages": 1,
        "bytes": 6_500_000,
        "opened": 4,
    },
    {
        "id": "/reader/heart-he/reader/",
        "open": "/reader/heart-he/reader/index.html",
        "kind": "talk",
        "name": "heart-he",
        "title": "A very long English title of a video about how the heart works",
        "film": True,
        "withFilm": True,
        "how": "auto",
        "pages": 1,
        "bytes": 8_800_000,
        "opened": 3,
    },
    {
        "id": "/reader/ruth-he/reader/",
        "open": "/reader/ruth-he/reader/index.html",
        "kind": "tanakh",
        "name": "ruth-he",
        "title": "רות",
        "how": "you",
        "pages": 5,
        "bytes": 4_000_000,
        "at": 3,
    },
    {
        "id": "/reader/will-he/reader/",
        "open": "/reader/will-he/reader/index.html",
        "kind": "story",
        "name": "will-he",
        "title": "צוואה",
        "sound": True,
        "how": "you",
        "pages": 1,
        "bytes": 6_300_000,
        "at": 2,
    },
]

#: The index and the browser's estimate as the test says, in place of the real ones:
#: `offline.js` is left whole and only its `list` answered.
STUB = """
((args) => {
  let real;
  Object.defineProperty(window, 'TargumOffline', {
    configurable: true,
    get() { return real; },
    set(v) {
      real = v;
      v.list = () => Promise.resolve(args.rows.map((row) => Object.assign({}, row)));
    },
  });
  if (args.estimate) {
    StorageManager.prototype.estimate = () => Promise.resolve(args.estimate);
  }
})
"""


def stubbed(rows: list[dict[str, Any]], estimate: dict[str, int] | None = None) -> str:
    return f"{STUB}({json.dumps({'rows': rows, 'estimate': estimate})});"


@pytest.fixture(params=["en", "ru"])
def saved_in(request: pytest.FixtureRequest, tmp_path: Path) -> Iterator[Served]:
    """The Saved page served in English and in Russian, whose words are longer."""
    from targum.render.builder import saved_page

    out = tmp_path / "targum-out"
    out.mkdir()
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    server.RequestHandlerClass = type(
        "TestHandler",
        (Handler,),
        {
            "library": Library(out),
            "token": TOKEN,
            "store": Store(tmp_path / "words.db"),
            "address": f"http://127.0.0.1:{port}",
            "translated": {},
            "saved_html": saved_page(TOKEN, request.param),
        },
    )
    threading.Thread(target=server.serve_forever, daemon=True).start()
    holder = Served(out, port, server, [])
    try:
        yield holder
    finally:
        try:
            holder.gone()
        except Exception:
            pass


#: Each drawn row measured: its title's box and whether its words are all shown, Keep's
#: and the cross's edges, and every column's.
MEASURE = """
() => {
  const rem = parseFloat(getComputedStyle(document.documentElement).fontSize);
  const box = (node) => (node ? node.getBoundingClientRect() : null);
  const rows = [...document.querySelectorAll('.saved-row')].map((row) => {
    const name = row.querySelector('.saved-name');
    const keep = box(row.querySelector('.saved-keep-it'));
    const x = box(row.querySelector('.saved-x'));
    return {
      title: name.textContent,
      width: box(name).width,
      whole: name.scrollHeight <= name.clientHeight + 1 && name.scrollWidth <= name.clientWidth + 1,
      gap: keep ? x.left - keep.right : null,
      size: box(row.querySelector('.saved-size')).right,
      kind: box(row.querySelector('.saved-kind')).left,
      inside: x.right <= row.closest('.card').getBoundingClientRect().right + 0.5,
    };
  });
  const heads = [...document.querySelectorAll('#saved-auto .saved-cols > span')]
    .filter((span) => getComputedStyle(span).display !== 'none')
    .map((span) => { const b = box(span); return [b.left, b.right]; });
  return {
    rem,
    rows,
    heads,
    sideways: document.documentElement.scrollWidth - document.documentElement.clientWidth,
  };
}
"""


def drawn(browser, served: Served, rows, *, width: int, estimate=None, **context: Any):  # noqa: F811
    made = browser.new_context(
        service_workers="allow", viewport={"width": width, "height": 1000}, **context
    )
    made.add_init_script(stubbed(rows, estimate))
    page = made.new_page()
    page.goto(served.url("/you/saved"))
    page.wait_for_selector("#saved-mine:not([hidden]) .saved-row")
    page.wait_for_function("() => document.fonts.status === 'loaded'")
    return made, page


def test_at_a_desk_every_title_has_room_and_keep_stands_clear_of_remove(
    browser,  # noqa: F811
    saved_in: Served,
) -> None:
    """P1 1: the Title column was about 70px at a desk (40px in Russian), so no title
    could be read, the heads ran together, and Keep touched the ×."""
    context, page = drawn(browser, saved_in, ROWS, width=1440)
    try:
        seen = page.evaluate(MEASURE)
        assert seen["sideways"] <= 0, "nothing scrolls sideways"
        assert len(seen["rows"]) == 6
        for row in seen["rows"]:
            assert row["width"] >= 12 * seen["rem"] - 1, row
            assert row["inside"], row
            if row["gap"] is not None:
                assert row["gap"] >= 8, f"Keep and the × stand apart: {row}"
        short = [row for row in seen["rows"] if len(row["title"]) <= 40]
        assert short and all(row["whole"] for row in short), [r for r in short if not r["whole"]]
        # The columns still line up from row to row, as one table.
        for group in (seen["rows"][:4], seen["rows"][4:]):
            assert len({round(row["size"]) for row in group}) == 1, group
            assert len({round(row["kind"]) for row in group}) == 1, group
        # And the heads stand apart: "Title" and "Kind" read as two words.
        for (_, right), (left, _) in zip(seen["heads"], seen["heads"][1:], strict=False):
            assert left - right >= 8, seen["heads"]
    finally:
        context.close()


@pytest.mark.parametrize("width", [1024, 390])
def test_narrower_the_table_still_fits_its_card(
    browser,  # noqa: F811
    saved_in: Served,
    width: int,
) -> None:
    """Between the phone and a wide desk the card is narrower than every column needs, and
    the Saved column goes first; on a phone the rows are their own, as they were."""
    context, page = drawn(browser, saved_in, ROWS, width=width)
    try:
        seen = page.evaluate(MEASURE)
        assert seen["sideways"] <= 0
        floor = 8 if width > 400 else 6
        for row in seen["rows"]:
            assert row["width"] >= floor * seen["rem"] - 1, row
            assert row["inside"], f"the row ends inside its card: {row}"
            if row["gap"] is not None:
                assert row["gap"] >= 0
    finally:
        context.close()


def test_under_a_thumb_keep_and_the_title_answer_a_tap(browser, saved_in: Served) -> None:  # noqa: F811
    """P2 11: Keep was 42px wide and the title's link 25px tall at 390."""
    context, page = drawn(browser, saved_in, ROWS, width=390, has_touch=True, is_mobile=True)
    try:
        assert page.evaluate("() => matchMedia('(pointer: coarse)').matches")
        # Measured in one go: the rows are drawn again whenever the index says so.
        keeps = page.evaluate(
            "() => [...document.querySelectorAll('.saved-keep-it')]"
            ".map((k) => [k.getBoundingClientRect().width, k.getBoundingClientRect().height])"
        )
        assert keeps and all(wide >= 44 and tall >= 44 for wide, tall in keeps), keeps
        # The link's reach is the row's title column.
        reach = page.evaluate(
            """() => [...document.querySelectorAll('a.saved-name')].map((a) => {
                 const after = getComputedStyle(a, '::after');
                 return [after.position, a.parentNode.getBoundingClientRect().height];
               })"""
        )
        assert reach and all(position == "absolute" and tall >= 44 for position, tall in reach)
        # A tap under the title, on the line of what was kept, opens the text.
        page.locator("#saved-auto .saved-kept-phone").nth(1).click(force=True)
        page.wait_for_url("**/reader/news-he/**")
    finally:
        context.close()


def test_nearly_full_says_so_in_clay_and_puts_the_largest_first(
    browser,  # noqa: F811
    saved_in: Served,
) -> None:
    """P1 3: at 2.1 GB of 2.2 GB the meter filled in the same teal and the page said only
    that the browser sets the room. From nine tenths it says what to do, and the tables put
    what makes the most room at the top."""
    full = {"usage": 2_100_000_000, "quota": 2_200_000_000}
    context, page = drawn(browser, saved_in, ROWS, width=1440, estimate=full)
    try:
        page.wait_for_selector("#saved-nearly:not([hidden])")
        said = page.locator("#saved-nearly").inner_text()
        assert said in (
            "Nearly full. Remove what you've finished to make room.",
            "Места почти не осталось. Удалите то, что уже прочитали.",
        )
        meter = page.locator(".saved-meter")
        assert "is-full" in (meter.get_attribute("class") or "")
        assert page.evaluate(
            "() => getComputedStyle(document.querySelector('#saved-meter')).backgroundColor"
        ) == page.evaluate(
            "() => { const s = document.createElement('span'); s.style.color = 'var(--clay)';"
            " document.body.appendChild(s); const c = getComputedStyle(s).color; s.remove();"
            " return c; }"
        )
        titles = page.locator("#saved-auto .saved-name").all_inner_texts()
        assert titles[0] == "On the bus to work every morning"
        assert titles[1].startswith("A very long English title"), "8.8 MB before 6.5 MB"
        assert page.locator("#saved-mine .saved-name").all_inner_texts() == ["צוואה", "רות"]
    finally:
        context.close()


def test_with_room_nothing_is_said_and_the_newest_comes_first(
    browser,  # noqa: F811
    saved_in: Served,
) -> None:
    room = {"usage": 68_000_000, "quota": 2_200_000_000}
    context, page = drawn(browser, saved_in, ROWS, width=1440, estimate=room)
    try:
        page.wait_for_selector("#saved-room:not([hidden])")
        assert page.locator("#saved-nearly").is_hidden()
        assert "is-full" not in (page.locator(".saved-meter").get_attribute("class") or "")
        titles = page.locator("#saved-auto .saved-name").all_inner_texts()
        assert titles[1] == "אנרגיה מתחדשת: מה השתנה השנה בחדשות", "by when it was opened"
        assert page.locator("#saved-mine .saved-name").all_inner_texts() == ["רות", "צוואה"]
    finally:
        context.close()


def test_a_hebrew_title_is_said_as_hebrew(browser, saved_in: Served) -> None:  # noqa: F811
    """P2 10: every row's `<bdi>` stood inside the page's `lang`, so a Hebrew title was
    English to a screen reader and to the face it is drawn in."""
    context, page = drawn(browser, saved_in, ROWS, width=1440)
    try:
        said = page.evaluate(
            "() => [...document.querySelectorAll('.saved-name bdi')]"
            ".map((b) => [b.textContent, b.getAttribute('lang'), b.getAttribute('dir')])"
        )
        langs = {title: lang for title, lang, _ in said}
        assert langs["רות"] == "he" and langs["צוואה"] == "he"
        assert langs["אנרגיה מתחדשת: מה השתנה השנה בחדשות"] == "he"
        assert langs["A very long English title of a video about how the heart works"] is None
        assert langs["On the bus to work every morning"] is None
        assert all(direction == "auto" for _, _, direction in said)
    finally:
        context.close()


def test_a_recording_inside_the_page_is_said_as_one(browser, saved_in: Served) -> None:  # noqa: F811
    """P2 7: a text whose recording rides inside its page said "text"."""
    context, page = drawn(browser, saved_in, ROWS, width=1440)
    try:
        kept = page.locator("#saved-mine .saved-row", has_text="צוואה").locator(".saved-kept")
        assert kept.inner_text() in ("text and recording", "текст и запись")
    finally:
        context.close()


def test_the_lede_stands_over_rows_and_not_over_nothing(browser, saved_in: Served) -> None:  # noqa: F811
    """P2 6: "These open, play and show their word cards without a connection." stood
    over nothing saved."""
    context = browser.new_context(service_workers="allow")
    context.add_init_script(stubbed([]))
    page = context.new_page()
    try:
        page.goto(saved_in.url("/you/saved"))
        page.wait_for_selector("#saved-none:not([hidden])")
        assert page.locator("#saved-lede").is_hidden()
    finally:
        context.close()
    context, page = drawn(browser, saved_in, ROWS, width=1440)
    try:
        assert page.locator("#saved-lede").is_visible()
    finally:
        context.close()
