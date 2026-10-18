"""Tell us, and a page that breaks telling us itself (targum-internal#456, #457).

What is held here is the half a reader cannot see: that a message is kept with what
clause 3.14 of the privacy notice says it is kept with and nothing more, that it reaches
the operator's mail and the back office, that only an admin changes its state, that a
fault report from a browser loses every query on the way in, that both are deleted when
the notice says they are, and that a page breaking for everybody mails the operator once.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
import test_serve
from test_serve import Postbox, call, form, sign_in

from targum import accounts, alerts, serve
from targum.accounts import FAULT_KEEP_DAYS, TOLD_KEEP_DAYS, Store
from targum.render.builder import back_office_page

served = test_serve.served
postbox = test_serve.postbox

DAY_MS = 24 * 60 * 60 * 1000


def store_of(tmp_path: Path) -> Store:
    """The fixture's own database, opened beside it."""
    return Store(tmp_path / "words.db")


# -- the store ---------------------------------------------------------------------------


def test_a_message_is_kept_with_its_page_and_nothing_more(tmp_path: Path) -> None:
    store = store_of(tmp_path)
    signed = store.finish_sign_in(store.start_sign_in("reader@example.com"))
    assert signed is not None
    person = signed[0]
    told_id = store.tell(
        person, "  The word card covers the line  ", "/texts", "abc123", "390x844", "en"
    )
    [row] = store.told()
    assert row["id"] == told_id
    assert row["said"] == "The word card covers the line"
    assert (row["page"], row["build"], row["viewport"], row["language"]) == (
        "/texts",
        "abc123",
        "390x844",
        "en",
    )
    assert row["email"] == "reader@example.com" and row["state"] == "open"
    with pytest.raises(ValueError):
        store.tell(person, "   ")


def test_closing_a_message_starts_its_year_and_opening_it_again_stops_it(tmp_path: Path) -> None:
    store = store_of(tmp_path)
    told_id = store.tell(None, "hello")
    assert store.settle_told(told_id, "asked")
    assert store.told()[0]["closed"] == 0, "asked is still waiting on us"
    assert store.settle_told(told_id, "fixed")
    closed = store.told()[0]["closed"]
    assert closed > 0
    assert store.settle_told(told_id, "won't")
    assert store.told()[0]["closed"] == closed, "closed once, counted from then"
    assert store.settle_told(told_id, "open")
    assert store.told()[0]["closed"] == 0
    with pytest.raises(ValueError):
        store.settle_told(told_id, "deleted")
    assert not store.settle_told(told_id + 99, "fixed"), "no such message"


def test_the_sweep_keeps_what_the_schedule_says_and_deletes_the_rest(tmp_path: Path) -> None:
    """Twelve months after closing for a message, thirty days for a fault report; an open
    message is kept however old it is. Run at start-up with the store's other sweeps."""
    store = store_of(tmp_path)
    old = store.tell(None, "closed long ago")
    recent = store.tell(None, "closed lately")
    waiting = store.tell(None, "open and old")
    store.settle_told(old, "fixed")
    store.settle_told(recent, "won't")
    then = accounts.now() - (TOLD_KEEP_DAYS + 1) * DAY_MS
    store.db.execute("UPDATE told SET closed = ? WHERE id = ?", (then, old))
    store.db.execute("UPDATE told SET at = ? WHERE id = ?", (then, waiting))
    store.fault(None, "TypeError: x is undefined", "", "/texts")
    store.fault(None, "old fault", "", "/texts")
    store.db.execute(
        "UPDATE fault SET at = ? WHERE message = 'old fault'",
        (accounts.now() - (FAULT_KEEP_DAYS + 1) * DAY_MS,),
    )

    store.sweep()

    assert {row["id"] for row in store.told()} == {recent, waiting}
    assert [row["message"] for row in store.faults()] == ["TypeError: x is undefined"]
    assert store.db.execute("SELECT COUNT(*) FROM fault").fetchone()[0] == 1


def test_both_go_with_the_account(tmp_path: Path) -> None:
    store = store_of(tmp_path)
    signed = store.finish_sign_in(store.start_sign_in("leaver@example.com"))
    assert signed is not None
    person = signed[0]
    store.tell(person, "something broke")
    store.fault(person, "TypeError: boom", "", "/texts")
    store.tell(None, "somebody else's")
    store.forget(person)
    assert store.purge(days=-1) == [person.id]
    assert [row["said"] for row in store.told()] == ["somebody else's"]
    assert store.db.execute("SELECT COUNT(*) FROM fault").fetchone()[0] == 0


def test_the_numbers_the_schedule_says_are_the_ones_the_sweep_uses() -> None:
    from test_legal import said

    from targum.render.builder import legal_page

    assert TOLD_KEEP_DAYS == 365, "the schedule says twelve months"
    assert FAULT_KEEP_DAYS == 30, "the schedule says thirty days"
    schedule = said(legal_page("retention"))
    assert "Twelve months from the day upon which the matter it raises is marked fixed" in schedule
    assert "Thirty days from receipt" in schedule
    notice = said(legal_page("privacy"))
    assert "clauses 3.6, 3.7 and 3.14" in notice
    assert "Tell us" in notice and "No part of the text being read and no cookie" in notice


# -- the doors ---------------------------------------------------------------------------


def test_a_message_is_kept_and_mailed_to_the_operator(
    served: tuple[int, str, Path],
    postbox: Postbox,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(alerts.ALERT_ENV, "ops@example.com")
    port, _, _ = served
    cookie = sign_in(port, postbox)
    status, answer, _ = call(
        port,
        "POST",
        "/tell-us",
        {
            "said": "The Hebrew line jumps when I tap",
            "page": "/reader/ruth/reader/2.html?k=secret#b3",
            "build": "abc123def456",
            "viewport": "390x844",
            "language": "en",
        },
        cookie,
    )
    assert status == 200 and answer == {"kept": True}, answer
    [row] = store_of(tmp_path).told()
    assert row["said"] == "The Hebrew line jumps when I tap"
    assert row["page"] == "/reader/ruth/reader/2.html", "never a query or a fragment"
    assert row["email"] == "reader@example.com"
    mail = postbox.getvalue()
    assert "To ops@example.com — targum: reader@example.com told us something" in mail
    assert "The Hebrew line jumps when I tap" in mail
    assert "secret" not in mail


def test_an_empty_message_is_refused_and_too_many_are_held(
    served: tuple[int, str, Path], postbox: Postbox, monkeypatch: pytest.MonkeyPatch
) -> None:
    port, _, _ = served
    cookie = sign_in(port, postbox)
    status, answer, _ = call(port, "POST", "/tell-us", {"said": "  "}, cookie)
    assert status == 400 and answer["error"] == "Write something first."
    monkeypatch.setattr(serve, "TOLD_PER_HOUR", 2)
    for _ in range(2):
        assert call(port, "POST", "/tell-us", {"said": "again"}, cookie)[0] == 200
    status, answer, _ = call(port, "POST", "/tell-us", {"said": "again"}, cookie)
    assert status == 429 and "hello@targum.page" in answer["error"]


def test_a_signed_out_message_is_turned_away_once_there_are_accounts(
    served: tuple[int, str, Path], postbox: Postbox
) -> None:
    port, _, _ = served
    sign_in(port, postbox)
    status, answer, _ = call(port, "POST", "/tell-us", {"said": "hi"})
    assert status == 401 and answer["error"] == "You'll need to sign in first."


def test_a_fault_report_is_kept_signed_out_without_its_queries(
    served: tuple[int, str, Path], postbox: Postbox, tmp_path: Path
) -> None:
    """A page breaks for strangers too, so the door is open to them; the account is
    whoever is signed in, and nobody when nobody is."""
    port, _, _ = served
    sign_in(port, postbox)  # an account exists, so signed out now means signed out
    status, answer, _ = call(
        port,
        "POST",
        "/errors",
        {
            "message": "TypeError: x is undefined at https://targum.page/texts?k=secret:10:4",
            "place": "at render (/texts?k=secret:10:4)",
            "page": "https://targum.page/texts?k=secret#top",
            "build": "abc123",
        },
    )
    assert status == 200 and answer == {"kept": True}, answer
    [row] = [dict(r) for r in store_of(tmp_path).db.execute("SELECT * FROM fault")]
    assert row["person"] is None
    assert row["page"] == "/texts"
    assert "secret" not in row["message"] and "secret" not in row["place"]
    assert row["place"] == "at render (/texts:10:4)"
    assert row["build"] == "abc123"


def test_a_fault_report_names_the_account_signed_in(
    served: tuple[int, str, Path], postbox: Postbox, tmp_path: Path
) -> None:
    port, _, _ = served
    cookie = sign_in(port, postbox)
    call(port, "POST", "/errors", {"message": "Error: boom", "page": "/"}, cookie)
    [row] = [dict(r) for r in store_of(tmp_path).db.execute("SELECT * FROM fault")]
    assert row["person"] is not None


def test_fault_reports_are_held_to_a_rate(
    served: tuple[int, str, Path], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    port, _, _ = served
    monkeypatch.setattr(serve, "FAULTS_PER_HOUR", 3)
    statuses = [
        call(port, "POST", "/errors", {"message": f"Error: {n}", "page": "/"})[0] for n in range(4)
    ]
    assert statuses == [200, 200, 200, 429]
    assert store_of(tmp_path).db.execute("SELECT COUNT(*) FROM fault").fetchone()[0] == 3


def test_a_fault_report_that_is_not_one_is_refused(served: tuple[int, str, Path]) -> None:
    port, _, _ = served
    assert call(port, "POST", "/errors", {"message": "  "})[0] == 400
    assert call(port, "POST", "/errors", ["not", "an", "object"])[0] == 400


def test_only_an_admin_changes_a_messages_state(
    served: tuple[int, str, Path], postbox: Postbox, tmp_path: Path
) -> None:
    port, _, _ = served
    store = store_of(tmp_path)
    told_id = store.tell(None, "please fix")
    reader = sign_in(port, postbox, "reader@example.com")
    status, _, _ = form(port, "/back-office/told", {"id": str(told_id), "state": "fixed"}, reader)
    assert status == 404
    assert store.told()[0]["state"] == "open"

    store.make_admin("ops@example.com")
    admin = sign_in(port, postbox, "ops@example.com")
    status, _, where = form(
        port, "/back-office/told", {"id": str(told_id), "state": "fixed"}, admin
    )
    assert status in (302, 303) and where.endswith("#people")
    assert store.told()[0]["state"] == "fixed"
    status, _, _ = form(port, "/back-office/told", {"id": str(told_id), "state": "gone"}, admin)
    assert status == 400


def test_only_an_admin_settles_a_message_in_the_source() -> None:
    """The form's door is the page's door, as `_balance`'s is."""
    text = Path(serve.__file__).read_text(encoding="utf-8")
    handler = text[text.index("def _settle_told") :]
    handler = handler[: handler.index("\n    def ", 10)]
    assert "not person.admin" in handler
    assert 'self._send(404, b"not found"' in handler


# -- the alert ---------------------------------------------------------------------------


def test_a_page_breaking_for_everybody_mails_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(alerts.ALERT_ENV, "ops@example.com")
    sent: list[tuple[str, str]] = []
    monkeypatch.setattr(alerts.FAULTS, "state", tmp_path / "fault-watch.json")
    monkeypatch.setattr(alerts.FAULTS, "send", lambda subject, body: sent.append((subject, body)))
    moment = datetime(2026, 10, 18, 12, tzinfo=UTC)

    assert not alerts.page_broke("TypeError: x", 4, "/texts", now=moment)
    assert alerts.page_broke("TypeError: x", 5, "/texts", "at f (/texts:1:2)", now=moment)
    assert not alerts.page_broke("TypeError: x", 6, "/texts", now=moment + timedelta(minutes=5))
    assert alerts.page_broke("TypeError: y", 5, "/", now=moment), "another message is news"
    assert alerts.page_broke("TypeError: x", 5, "/texts", now=moment + timedelta(hours=25))
    assert len(sent) == 3
    assert "reported 5 times in the last hour" in sent[0][1] and "/texts" in sent[0][1]


def test_the_alert_never_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(alerts.ALERT_ENV, "ops@example.com")

    def broken(*_: Any) -> None:
        raise OSError("no mail today")

    monkeypatch.setattr(alerts.FAULTS, "state", tmp_path / "fault-watch.json")
    monkeypatch.setattr(alerts.FAULTS, "send", broken)
    assert not alerts.page_broke("TypeError: x", 5)


def test_unconfigured_the_alert_is_silent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(alerts.FAULTS, "state", None)
    assert not alerts.page_broke("TypeError: x", 50)


# -- the back office ---------------------------------------------------------------------


def test_the_back_office_lists_messages_and_counts_faults(tmp_path: Path) -> None:
    from targum.backoffice import Survey

    store = store_of(tmp_path)
    store.tell(None, "first", "/texts", "abc", "390x844", "en")
    closed = store.tell(None, "second")
    store.settle_told(closed, "fixed")
    for _ in range(3):
        store.fault(None, "TypeError: boom", "at f (/texts:1:2)", "/texts", "abc")
    page = back_office_page(Survey(), 30, told=store.told(), faults=store.faults())
    assert "1 message waiting on us" in page[: page.index('class="bo-tabs"')]
    people = page[page.index('id="tab-people"') : page.index('id="tab-traffic"')]
    assert '<h2 id="told">Tell us</h2>' in people and ">first<" in people
    assert "Closed (1)" in people and ">second<" in people
    assert 'action="/back-office/told"' in people
    operations = page[page.index('id="tab-operations"') :]
    assert "Broken in browsers" in operations
    assert "TypeError: boom" in operations and '<td class="n">3</td>' in operations
    assert "save the\n    messages readers write to us through Tell us" in page


# -- the build ---------------------------------------------------------------------------


def test_the_stamp_carries_the_build_and_a_wheel_reads_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from targum import about

    about.build.cache_clear()
    if not about.work().days:
        pytest.skip("no repository to stamp from")
    monkeypatch.setattr(about, "STAMP", tmp_path / "activity.json")
    assert about.stamp() is not None
    written = json.loads((tmp_path / "activity.json").read_text(encoding="utf-8"))
    assert len(written["build"]) == 12
    monkeypatch.setattr(about, "_root", lambda: tmp_path)
    about.build.cache_clear()
    try:
        assert about.build() == written["build"]
    finally:
        about.build.cache_clear()


def test_a_checkout_is_its_head_until_it_is_edited(monkeypatch: pytest.MonkeyPatch) -> None:
    from targum import about

    said = {"status": "", "rev-parse": "0123456789ab\n"}
    monkeypatch.setattr(about, "_root", lambda: Path(__file__).resolve().parents[1])
    monkeypatch.setattr(about, "_git", lambda *args: said[args[0]])
    about.build.cache_clear()
    try:
        # As committed: the parasha cut from the main checkout says which commit it is.
        assert about.build() == "0123456789ab"
        # An edited tracked file makes it work in progress.
        said["status"] = " M src/targum/about.py\n"
        about.build.cache_clear()
        assert about.build() == "dev"
    finally:
        about.build.cache_clear()


def test_every_page_with_the_fault_script_carries_the_reporter_first() -> None:
    from targum.render.builder import TEMPLATES

    for name in (
        "_nav.html.j2",
        "reader.html.j2",
        "index.html.j2",
        "signin.html.j2",
        "chat.html.j2",
    ):
        text = (TEMPLATES / name).read_text(encoding="utf-8")
        assert "script('report.js'" in text, name
        assert text.index("script('report.js'") < text.index("script('fault.js')"), name
        assert "data_build=build()" in text, name
