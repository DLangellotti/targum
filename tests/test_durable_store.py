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
    page.close()


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
    page.close()


# The shelf answering later than the reader is willing to wait. `onsuccess` is held back
# past PATIENCE, so the page starts on `localStorage` alone and recovery lands on a page
# that is already running — every open, the mirrors included, so nothing reaches the
# shelf any sooner than recovery reads it.
SLOW_SHELF = """
(() => {
  const real = indexedDB.open.bind(indexedDB);
  indexedDB.open = (...args) => {
    const ask = real(...args);
    let success = null;
    Object.defineProperty(ask, "onsuccess", {
      set(fn) { success = fn; },
      get() { return success; },
    });
    ask.addEventListener("success", (event) => {
      setTimeout(() => { if (success) success(event); }, 1500);
    });
    return ask;
  };
})();
"""


def shelf_holds(value: str) -> str:
    """A wait for the shelf to hold `value`, since a mirror commits on its own time."""
    return "async () => ((await (" + SHELF + ")()) || {}).value === '" + value + "'"


def lost_flush(page) -> None:
    """A shelf holding the better copy and a `localStorage` a version behind it, which is
    what a write that never reached disk looks like from the next opening."""
    page.evaluate("() => window.targumKeep('targum:probe', 'stale')")
    stale_at = page.evaluate("() => localStorage.getItem('targum:at:targum:probe')")
    page.evaluate("() => window.targumKeep('targum:probe', 'better')")
    page.wait_for_function(shelf_holds("better"))
    page.evaluate(
        "(at) => { localStorage.setItem('targum:probe', 'stale');"
        "          localStorage.setItem('targum:at:targum:probe', at); }",
        stale_at,
    )


def reopened(page, built: Path) -> None:  # noqa: F811
    """The next opening, on a page whose shelf answers at once."""
    page.goto(built.as_uri())
    page.wait_for_selector(".pair")
    page.evaluate(READY)


def slow(reader, built: Path):  # noqa: F811
    """A second page in the same context — the same `localStorage` and the same shelf —
    whose shelf answers later than the reader is willing to wait."""
    page = reader.context.new_page()
    page.add_init_script(SLOW_SHELF)
    page.goto(built.as_uri())
    page.wait_for_selector(".pair")
    page.evaluate(READY)
    return page


def test_a_page_that_did_not_wait_starts_on_what_localStorage_holds(reader, built: Path) -> None:  # noqa: F811
    """The premise of targum-internal#154, reproduced before it is fixed: the shelf is
    slower than the reader's patience, so the page starts on the copy that lost a write.
    That is the right trade — a reader must not hang behind a store — and the tests below
    are about what the page is then allowed to write."""
    lost_flush(reader)
    page = slow(reader, built)
    assert page.evaluate("() => localStorage.getItem('targum:probe')") == "stale"
    page.close()


def test_a_blind_write_before_the_shelf_answers_does_not_outrank_it(reader, built: Path) -> None:  # noqa: F811
    """The bug. The page starts on the stale copy, writes out of that state before the
    shelf has answered, and is gone before it does. Written with a fresh stamp, that
    write would have been provably ahead of the better copy at the next opening and
    the better copy could never win again. It is written with the stamp the page read,
    so the shelf is still ahead of it."""
    lost_flush(reader)
    page = slow(reader, built)
    page.evaluate("() => window.targumKeep('targum:probe', 'stale, and further')")
    # Gone before recovery lands: the next load has a shelf that answers at once.
    page.close()
    reopened(reader, built)
    assert reader.evaluate("() => localStorage.getItem('targum:probe')") == "better"


def test_a_blind_write_the_shelf_lands_on_is_kept_below_it(reader, built: Path) -> None:  # noqa: F811
    """The same write, with the page still open when recovery lands. The page is live on
    its own value and keeps it where it reads; the shelf's copy is the one that survives
    the next opening, because the page never saw it."""
    lost_flush(reader)
    page = slow(reader, built)
    page.evaluate("() => window.targumKeep('targum:probe', 'stale, and further')")
    page.wait_for_timeout(2500)
    assert page.evaluate("() => localStorage.getItem('targum:probe')") == "stale, and further"
    assert page.evaluate(SHELF)["value"] == "better"
    page.close()
    reopened(reader, built)
    assert reader.evaluate("() => localStorage.getItem('targum:probe')") == "better"


def test_a_write_after_the_shelf_lands_on_a_blind_page_does_not_outrank_it(
    reader,
    built: Path,  # noqa: F811
) -> None:
    """Recovery landing puts the better copy where the page reads, but the page read
    before it landed and its state comes from the stale one. A write out of that state,
    stamped fresh, would bury the better copy; it is stamped below it instead."""
    lost_flush(reader)
    page = slow(reader, built)
    page.wait_for_timeout(2500)
    assert page.evaluate("() => localStorage.getItem('targum:probe')") == "better"
    page.evaluate("() => window.targumKeep('targum:probe', 'from a copy never seen')")
    assert page.evaluate(SHELF)["value"] == "better"
    page.close()
    reopened(reader, built)
    assert reader.evaluate("() => localStorage.getItem('targum:probe')") == "better"


def test_a_blind_write_the_shelf_was_not_ahead_of_is_a_real_write(reader, built: Path) -> None:  # noqa: F811
    """Holding a blind write back must not cost a write the shelf had no better copy
    than. Once recovery lands and finds the shelf behind it, the write gets the fresh
    stamp it was held back from and reaches the shelf."""
    reader.evaluate("() => window.targumKeep('targum:probe', 'first')")
    reader.wait_for_function(shelf_holds("first"))
    page = slow(reader, built)
    page.evaluate("() => window.targumKeep('targum:probe', 'second')")
    page.wait_for_timeout(2500)
    page.wait_for_function(shelf_holds("second"))
    page.close()
    reopened(reader, built)
    assert reader.evaluate("() => localStorage.getItem('targum:probe')") == "second"


def test_a_mirror_that_never_committed_is_caught_up_on_the_next_opening(
    reader,
    built: Path,  # noqa: F811
) -> None:
    """`mirror()` is fire-and-forget on the way out of a page, so a write can reach
    `localStorage` and not the shelf. Recovery finding `localStorage` ahead now sends the
    shelf what it missed, rather than leaving that write with one copy for good."""
    reader.evaluate("() => window.targumKeep('targum:probe', 'kept')")
    reader.wait_for_function(shelf_holds("kept"))
    # A later write whose mirror was lost: `localStorage` has it and a fresher stamp,
    # and the shelf still has the one before.
    reader.evaluate(
        "() => { localStorage.setItem('targum:probe', 'later');"
        "        localStorage.setItem('targum:at:targum:probe',"
        "          String(Number(localStorage.getItem('targum:at:targum:probe')) + 10)); }"
    )
    reader.goto(built.as_uri())
    reader.wait_for_selector(".pair")
    reader.evaluate(READY)
    reader.wait_for_function(shelf_holds("later"))
    assert reader.evaluate("() => localStorage.getItem('targum:probe')") == "later"
