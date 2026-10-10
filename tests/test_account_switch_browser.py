"""One browser, two accounts: nothing of one may come back under the other.

David, 2026-10-10: a test account's data deleted, signed out, signed in as himself — and
his own account looked as if everything had gone, until it came back by itself a few
minutes later. The server had lost nothing.

The browser had two copies of the record and sign-out emptied one. A reader mirrors
every write into IndexedDB (`durable.js`, the copy that survives a `file://` flush), but
sign-out on any other page runs `keep.js`, whose `targumForget` only knows
`localStorage`. So the shelf kept the last account's words, its tombstones and its
`targum:sync` — and since a page that is not a reader writes no stamps, the next reader
opened found the shelf "ahead" of every key and put it all back over the account now
signed in. The reader then drew the old account's empty list until sync noticed the
email did not match, swept everything and pulled the whole account again.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

# The fixtures live in the browser module rather than a conftest, so they are
# imported by name to register them here.
from test_reader_browser import (  # noqa: F401
    browser,
    built,
    opened,
)

from targum.render.builder import ASSETS

READY = """
() => new Promise((done) => (window.TargumStore ? window.TargumStore.ready(done) : done()))
"""

# Every name on the shelf, once its writes have committed.
SHELF_NAMES = """
async () => {
  const db = await new Promise((ok, no) => {
    const r = indexedDB.open('targum', 1);
    r.onupgradeneeded = () => r.result.createObjectStore('kept');
    r.onsuccess = () => ok(r.result);
    r.onerror = () => no(r.error);
  });
  const names = await new Promise((ok) => {
    const r = db.transaction('kept', 'readonly').objectStore('kept').getAllKeys();
    r.onsuccess = () => ok(r.result.map(String).sort());
    r.onerror = () => ok([]);
  });
  db.close();
  return names;
}
"""

TEST = "djlangellotti+targumtest@example.com"
MAIN = "djlangellotti@example.com"

MAIN_WORDS = {"ספר": {"status": 2, "at": 100, "seen": 100}}


def keep(page, name: str, value: object) -> None:
    page.evaluate("([name, value]) => window.targumKeep(name, value)", [name, json.dumps(value)])


def shelf_until(page, done, seconds: float = 5.0) -> list[str]:
    """The shelf's names once `done` holds of them. Polled from here: a mirror commits
    on its own time, and `wait_for_function` takes a pending promise for a yes."""
    deadline = time.monotonic() + seconds
    while True:
        names = page.evaluate(SHELF_NAMES)
        if done(names) or time.monotonic() > deadline:
            return names
        page.wait_for_timeout(50)


def until_shelf_has(page, name: str) -> None:
    assert name in shelf_until(page, lambda names: name in names), f"{name} never reached the shelf"


def chrome_page(tmp_path: Path) -> Path:
    """A page that is not a reader: `keep.js` and `sync.js`, nothing durable — the shape
    of the account page, You, Progress and home, where somebody signs out."""
    page = tmp_path / "chrome.html"
    page.write_text(
        "<!doctype html><meta charset=utf-8><title>chrome</title>"
        f'<script src="{(ASSETS / "keep.js").as_uri()}"></script>'
        f'<script src="{(ASSETS / "sync.js").as_uri()}"></script>',
        encoding="utf-8",
    )
    return page


@pytest.fixture
def reader(browser, built: Path):  # noqa: F811
    context = opened(browser)
    page = context.new_page()
    page.goto(built.as_uri())
    page.wait_for_selector(".pair")
    page.evaluate(READY)
    yield page
    context.close()


def as_the_test_account(reader) -> None:
    """The test account, reading: its record on both copies, its list emptied."""
    keep(reader, "targum:sync", {"email": TEST, "revision": 7, "pushed": 7})
    keep(reader, "targum:vocab:he", {})
    keep(reader, "targum:gone", {"w:he:ספר": 9_999_999_999_999})
    until_shelf_has(reader, "targum:gone")


def signed_in_elsewhere_as_main(page) -> None:
    """What a page that is not a reader leaves after the main account signs in on it:
    the whole account pulled into `localStorage`, written with no stamps, because
    `keep.js` writes none."""
    page.evaluate(
        "([state, words]) => {"
        "  localStorage.setItem('targum:sync', state);"
        "  localStorage.setItem('targum:vocab:he', words);"
        "}",
        [
            json.dumps({"email": MAIN, "revision": 40, "pushed": 40}),
            json.dumps(MAIN_WORDS, ensure_ascii=False),
        ],
    )


def test_signing_out_off_a_reader_empties_the_durable_copy(reader, tmp_path: Path) -> None:
    """Sign-out happens on the account page, You or home — never on a reader — and there
    `targumForget` is `keep.js`'s, which knows only `localStorage`. Sign-out has to reach
    the shelf itself, or the account just left is still in this browser."""
    as_the_test_account(reader)

    out = reader.context.new_page()
    out.add_init_script(
        "window.fetch = () => Promise.resolve({ ok: true, status: 200,"
        " json: () => Promise.resolve({ signedIn: false }) });"
    )
    out.goto(chrome_page(tmp_path).as_uri())
    out.wait_for_function("() => !!window.TargumSync")
    out.evaluate("() => window.TargumSync.signOut()")

    assert shelf_until(out, lambda names: not names) == [], "the shelf still holds them"
    assert (
        out.evaluate("() => Object.keys(localStorage).filter((k) => k.startsWith('targum:'))") == []
    )


def test_a_reader_never_restores_another_accounts_copy(reader, built: Path) -> None:  # noqa: F811
    """The bug as it happened. The shelf holds the test account; `localStorage` holds
    the main account, freshly pulled on a page that writes no stamps. Opening a reader
    must not put the test account back — not its empty list, not its tombstones, and
    above all not its `targum:sync`, which is what decides whose record this is."""
    as_the_test_account(reader)
    # Sign-out as it was before the fix: `localStorage` swept, the shelf left alone.
    reader.evaluate(
        "() => Object.keys(localStorage).filter((k) => k.startsWith('targum:'))"
        ".forEach((k) => localStorage.removeItem(k))"
    )
    signed_in_elsewhere_as_main(reader)

    reader.goto(built.as_uri())
    reader.wait_for_selector(".pair")
    reader.evaluate(READY)

    state = json.loads(reader.evaluate("() => localStorage.getItem('targum:sync')") or "{}")
    words = json.loads(reader.evaluate("() => localStorage.getItem('targum:vocab:he')") or "{}")
    gone = reader.evaluate("() => localStorage.getItem('targum:gone')")
    assert state.get("email") == MAIN, "the record in this browser is the main account's"
    assert words == MAIN_WORDS, "and its words are the ones it pulled"
    assert gone is None, "the other account's deletes are not this one's"
    # And the shelf no longer holds the other account at all: what it has now is what
    # `localStorage` has, seeded from it.
    until_shelf_has(reader, "targum:sync")
    assert "targum:gone" not in reader.evaluate(SHELF_NAMES)
