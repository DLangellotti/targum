"""An address on the waitlist that never confirmed is deleted thirty days after it asked,
with the link it tried (the Data Retention Schedule as David approved it on 2026-11-17;
design.md §12). Nothing that confirmed or was let in is touched, the sweep can run any
number of times, and the log says how many and never who."""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime
from http.client import HTTPConnection
from pathlib import Path

import pytest
import test_serve
from test_serve import Postbox, sign_in

from targum.accounts import UNCONFIRMED_KEEP_DAYS, Store, now
from targum.backoffice import Listing, survey
from targum.render.builder import back_office_page
from targum.serve import Library, keep_purging

served = test_serve.served
postbox = test_serve.postbox

DAY_MS = 24 * 60 * 60 * 1000
LINK = "https://www.youtube.com/watch?v=abcdefghijk"


def asked(store: Store, email: str, days_ago: float) -> None:
    store.db.execute(
        "UPDATE waiting SET asked = ? WHERE email = ?", (now() - int(days_ago * DAY_MS), email)
    )
    store.db.commit()


@pytest.fixture
def store(tmp_path: Path) -> Store:
    """Every kind of row, all of them asked long ago, save the two at the boundary."""
    kept = Store(tmp_path / "targum.db")
    kept.join_waitlist("day29@example.com", "en", "/", LINK)
    kept.join_waitlist("day31@example.com", "en", "/", LINK)
    token = kept.join_waitlist("confirmed@example.com", "en")
    assert token is not None and kept.confirm_waiting(token)
    kept.join_waitlist("invited@example.com", "en")
    kept.waiting_invited("invited@example.com")
    kept.join_waitlist("12345678@mailinator.com", "en")
    assert kept.turn_off_waiting("12345678@mailinator.com")
    for email, days in (
        ("day29@example.com", 29),
        ("day31@example.com", 31),
        ("confirmed@example.com", 400),
        ("invited@example.com", 400),
        ("12345678@mailinator.com", 45),
    ):
        asked(kept, email, days)
    return kept


def left(store: Store) -> set[str]:
    return {str(row[0]) for row in store.db.execute("SELECT email FROM waiting")}


def test_thirty_days_is_the_line(store: Store) -> None:
    assert UNCONFIRMED_KEEP_DAYS == 30
    assert store.sweep_unconfirmed() == 2
    assert left(store) == {
        "day29@example.com",
        "confirmed@example.com",
        "invited@example.com",
    }, "day 31 and the unconfirmed address turned off go; day 29 stays"


def test_the_link_goes_with_the_address(store: Store) -> None:
    assert store.waiting_link("day31@example.com") == LINK
    store.sweep_unconfirmed()
    assert store.waiting_link("day31@example.com") == ""
    assert (
        store.db.execute("SELECT COUNT(*) FROM waiting WHERE link = ?", (LINK,)).fetchone()[0] == 1
    ), "only day 29's link is left"


def test_confirmed_and_let_in_are_never_touched_however_old(store: Store) -> None:
    asked(store, "confirmed@example.com", 4000)
    asked(store, "invited@example.com", 4000)
    store.sweep_unconfirmed(days=0)
    assert {"confirmed@example.com", "invited@example.com"} <= left(store)
    assert store.waiting_state("confirmed@example.com") == "on"


def test_a_second_sweep_finds_nothing(store: Store) -> None:
    assert store.sweep_unconfirmed() == 2
    assert store.sweep_unconfirmed() == 0
    assert len(left(store)) == 3


def test_asking_again_starts_the_thirty_days_again(store: Store) -> None:
    store.join_waitlist("day31@example.com", "en")
    assert store.sweep_unconfirmed() == 1
    assert "day31@example.com" in left(store)


def test_start_up_sweeps_it(store: Store) -> None:
    store.sweep()
    assert "day31@example.com" not in left(store)


def test_the_night_sweeps_it_and_logs_a_count_only(
    store: Store, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    library = Library(tmp_path / "out", store=store)
    evening = datetime(2026, 11, 18, 21, 30, tzinfo=UTC)
    with caplog.at_level(logging.INFO, logger="targum"):
        keep_purging(library, wait=lambda _: None, clock=lambda: evening, nights=2)
    assert "day31@example.com" not in left(store)
    said = caplog.text
    assert "2 unconfirmed address(es) deleted" in said
    assert said.count("unconfirmed address") == 1, "the second night deleted nothing"
    assert "@" not in said and "example.com" not in said and "mailinator" not in said


def test_the_waitlist_page_folds_the_unconfirmed(store: Store) -> None:
    found = survey(store.db, today=date.today())
    page = back_office_page(found, 30, section="waitlist")
    folds = page[page.index("<summary>Unconfirmed (") :]
    assert "<summary>Unconfirmed (2)</summary>" in page
    assert "day29@example.com" in folds and "day31@example.com" in folds
    main = page[page.index("<h2>The waitlist") : page.index("<summary>Unconfirmed (")]
    assert "confirmed@example.com" in main and "day29@example.com" not in main
    assert "<summary>Let in (1)</summary>" in page
    assert "waiting to be let in" in page and "deleted thirty days after it asked" in page


def test_the_unconfirmed_page_their_own_way(tmp_path: Path) -> None:
    kept = Store(tmp_path / "targum.db")
    for n in range(60):
        kept.join_waitlist(f"u{n:02d}@example.com", "en")
    found = survey(kept.db, today=date.today(), unconfirmed=Listing(sort="oldest", page=2))
    assert found.unconfirmed_listing.matches == 60 and found.unconfirmed_listing.page == 2
    page = back_office_page(found, 30, section="waitlist")
    assert 'rel="prev" href="/back-office/waitlist"' in page
    assert "Unconfirmed pages" in page


def get(port: int, path: str, cookie: str = "") -> tuple[int, dict[str, str], str]:
    connection = HTTPConnection("127.0.0.1", port, timeout=10)
    try:
        connection.request("GET", path, headers={"Cookie": cookie} if cookie else {})
        response = connection.getresponse()
        body = response.read().decode("utf-8", "replace")
        return response.status, {k.lower(): v for k, v in response.getheaders()}, body
    finally:
        connection.close()


def test_the_fold_is_the_admins_and_kept_nowhere(
    served: tuple[int, str, Path], postbox: Postbox, tmp_path: Path
) -> None:
    port, _, _ = served
    kept = Store(tmp_path / "words.db")
    kept.join_waitlist("never-confirmed@example.com", "en")
    reader = sign_in(port, postbox, "reader@example.com")
    kept.make_admin("ops@example.com")
    admin = sign_in(port, postbox, "ops@example.com")
    for path in ("/back-office/waitlist", "/back-office/waitlist?upage=2"):
        for cookie, status in (("", 200), (reader, 404), (admin, 200)):
            got, headers, body = get(port, path, cookie)
            assert got == status, (path, bool(cookie), got)
            assert headers["cache-control"] == "no-store"
            shown = "never-confirmed@example.com" in body
            assert shown == (cookie == admin), (path, bool(cookie))
