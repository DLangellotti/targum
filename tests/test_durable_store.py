"""The store that keeps what a reader is told, on a targum opened from disk.

`localStorage` does not, on `file://`. Measured, paired, 2,000 write-then-reload rounds:
it lost the most recent write 66 times where IndexedDB lost none, and the rate climbed as
the store filled — so the reader with the most to lose is the likeliest to lose it
(targum-internal#137).

These tests are about the part that is targum's: that a write goes to both stores, that
recovery puts back the durable copy when it is ahead, and — the one that matters most —
that recovery leaves alone a value it has no business overwriting. A first draft trusted
IndexedDB unconditionally and reverted 100 writes out of 100 that had not gone through
`keep`, which is a worse bug than the one being fixed.
"""

from __future__ import annotations

from pathlib import Path

import pytest

# The fixtures live in the browser module rather than a conftest, so they are
# imported by name to register them here.
from test_reader_browser import (  # noqa: F401
    browser,
    built,
    opened,
)

READY = """
() => new Promise((done) => (window.TargumStore ? window.TargumStore.ready(done) : done()))
"""

SHELF = """
async () => {
  const db = await new Promise((ok, no) => {
    const r = indexedDB.open('targum', 1);
    r.onsuccess = () => ok(r.result);
    r.onerror = () => no(r.error);
  });
  const got = await new Promise((ok) => {
    const r = db.transaction('kept', 'readonly').objectStore('kept').get('targum:probe');
    r.onsuccess = () => ok(r.result ?? null);
    r.onerror = () => ok(null);
  });
  db.close();
  return got;
}
"""


@pytest.fixture
def reader(browser, built: Path):  # noqa: F811
    context = opened(browser)
    page = context.new_page()
    page.goto(built.as_uri())
    page.wait_for_selector(".pair")
    page.evaluate(READY)
    yield page
    context.close()


def test_a_write_reaches_both_stores(reader) -> None:
    """The fast copy and the durable one. `localStorage` is what the page reads at
    startup, which is what lets it draw before anything is awaited; IndexedDB is the copy
    that survives being carried."""
    reader.evaluate("() => window.targumKeep('targum:probe', 'written')")
    assert reader.evaluate("() => localStorage.getItem('targum:probe')") == "written"
    kept = reader.evaluate(SHELF)
    assert kept is not None, "nothing reached the durable store"
    assert kept["value"] == "written"


def test_the_durable_copy_carries_when_it_was_written(reader) -> None:
    """Without a stamp, recovery cannot tell which copy is newer and can only guess."""
    reader.evaluate("() => window.targumKeep('targum:probe', 'first')")
    early = reader.evaluate(SHELF)["at"]
    reader.evaluate("() => window.targumKeep('targum:probe', 'second')")
    later = reader.evaluate(SHELF)["at"]
    assert later > early, "two writes to one name must be orderable"


def test_recovery_puts_back_a_value_localStorage_lost(reader, built: Path) -> None:  # noqa: F811
    """The whole point. A write that did not reach disk leaves `localStorage` a version
    behind; the durable copy is ahead, says so, and is restored on the way back in."""
    reader.evaluate("() => window.targumKeep('targum:probe', 'kept')")
    # Exactly what a lost flush looks like from the next load: the value and its stamp
    # are gone from localStorage while the durable copy still has both.
    reader.evaluate(
        "() => { localStorage.removeItem('targum:probe');"
        "        localStorage.removeItem('targum:at:targum:probe'); }"
    )

    reader.goto(built.as_uri())
    reader.wait_for_selector(".pair")
    reader.evaluate(READY)

    assert reader.evaluate("() => localStorage.getItem('targum:probe')") == "kept"


def test_recovery_leaves_alone_what_it_did_not_write(reader, built: Path) -> None:  # noqa: F811
    """The bug a first draft shipped, pinned so it cannot come back.

    A value written straight to `localStorage` has no durable copy, so the shelf holds
    something older — or nothing. Trusting the shelf unconditionally puts the older one
    back, which loses a write rather than saving one. Measured at the time: 100 out of
    100 reverted.
    """
    reader.evaluate("() => window.targumKeep('targum:probe', 'old')")
    reader.evaluate("() => localStorage.setItem('targum:probe', 'newer, and not ours')")

    reader.goto(built.as_uri())
    reader.wait_for_selector(".pair")
    reader.evaluate(READY)

    assert reader.evaluate("() => localStorage.getItem('targum:probe')") == "newer, and not ours"


def test_forgetting_reaches_both_stores(reader) -> None:
    """A word unmarked has to stay unmarked. Removed from the fast copy only, the durable
    one would put it back on the next opening."""
    reader.evaluate("() => window.targumKeep('targum:probe', 'here')")
    reader.evaluate("() => window.targumForget('targum:probe')")
    assert reader.evaluate("() => localStorage.getItem('targum:probe')") is None
    assert reader.evaluate(SHELF) is None, "the durable copy outlived the removal"


def test_the_reader_still_starts_when_the_store_will_not_answer(browser, built: Path) -> None:  # noqa: F811
    """A page that will not draw because a database is wedged is a worse failure than the
    one this file is for, so the wait gives up and the reader starts anyway."""
    context = opened(browser)
    page = context.new_page()
    page.add_init_script("window.indexedDB = undefined;")
    page.goto(built.as_uri())
    page.wait_for_selector(".pair")
    # The reader is alive: its own marks are on the page, which only its script draws.
    page.wait_for_function("() => !!document.querySelector('.w')")
    assert page.evaluate("() => !!document.querySelector('.w')")
    context.close()
