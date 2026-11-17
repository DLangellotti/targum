"""The operator's preview of plans while they are off (`TARGUM_PLANS_PREVIEW=operators`,
targum-internal#59 phase 2): an admin account sees `/plans` and its own plan as a reader
would, so paying through Paddle's sandbox can be tried on the box before switch day.

What must hold, adversarially: nobody but an admin ever sees it; `plans.on()` stays off;
nothing about what anybody may spend changes, the operator included; and with the
preview unset, or set to anything else, everything is exactly as before."""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable
from http.client import HTTPConnection
from pathlib import Path
from typing import Any

import pytest

from targum import plans, serve
from targum.accounts import Person, Store
from targum.serve import UPLOAD_SECONDS, Job, Library

HOST = "targum.page"


@pytest.fixture
def preview(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TARGUM_PLANS", raising=False)
    monkeypatch.setenv(plans.PREVIEW_ENV, "operators")


def a_person(admin: bool, plan_until: str = "") -> Person:
    return Person(1, "someone@example.com", admin, plan_until)


# -- who previews --------------------------------------------------------------------


@pytest.mark.usefixtures("preview")
def test_only_an_admin_previews_and_plans_stay_off() -> None:
    assert plans.previewing(a_person(True)) and plans.shown(a_person(True))
    assert not plans.previewing(a_person(False)) and not plans.shown(a_person(False))
    assert not plans.previewing(None) and not plans.shown(None)
    assert not plans.on(), "the switch itself is untouched"


@pytest.mark.parametrize("said", ["", "1", "true", "admins", "everyone", "operator"])
def test_any_other_value_previews_nothing(monkeypatch: pytest.MonkeyPatch, said: str) -> None:
    monkeypatch.delenv("TARGUM_PLANS", raising=False)
    monkeypatch.setenv(plans.PREVIEW_ENV, said)
    assert not plans.previewing(a_person(True)) and not plans.shown(a_person(True))


def test_with_plans_on_the_preview_is_nothing_of_its_own(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TARGUM_PLANS", "1")
    monkeypatch.setenv(plans.PREVIEW_ENV, "operators")
    assert not plans.previewing(a_person(True))
    assert "preview" not in plans.summary(a_person(True))
    assert plans.summary(a_person(True))["plan"] == "plan", "the operator is Plan, as ever"


@pytest.mark.usefixtures("preview")
def test_the_operator_is_drawn_as_the_reader_they_would_be() -> None:
    said = plans.summary(a_person(True))
    assert said["on"] is True and said["preview"] is True
    assert said["plan"] == "free", "so Start the plan is offered to try"
    comped = plans.summary(a_person(True, plan_until="2099-01-01"))
    assert comped["plan"] == "plan" and comped["comp"] == "2099-01-01"
    assert plans.summary(a_person(False)) == {"on": False}, "a reader sees nothing"


# -- nothing anybody may spend changes -------------------------------------------------


def recording(library: Library, who: int, seconds: float, ident: str, admin: bool) -> Job:
    job = Job(
        id=ident,
        source=f"upload:{ident}.mp3",
        estimate=0.10,
        owner=who,
        admin=admin,
        home=library.out / "local",
        audio=True,
        seconds=seconds,
    )
    library.jobs[ident] = job
    library.remember(job)
    return job


@pytest.mark.usefixtures("preview")
def test_no_limit_changes_for_anybody(tmp_path: Path) -> None:
    store = Store(tmp_path / "targum.db")
    library = Library(
        tmp_path / "out", max_cost=1000.0, budget=1000.0, store=store, account_budget=None
    )
    for email in ("reader@example.com", "op@example.com"):
        assert store.finish_sign_in(store.start_sign_in(email)) is not None
    store.make_admin("op@example.com")
    reader = store.person_by_email("reader@example.com")
    operator = store.person_by_email("op@example.com")
    assert reader is not None and operator is not None and operator.admin
    # Plans off: every account keeps the whole month, no cap, subscriptions allowed.
    for who in (reader, operator):
        assert library.allowance(paid_plan=plans.paid(who)) == UPLOAD_SECONDS
        assert plans.word_cap(who) is None and plans.builds_by_itself(who)
        assert not plans.free(who)
    assert plans.paid(operator), "what the operator may spend still counts them as operator"
    assert library.claim(recording(library, reader.id, 7 * 3600.0, "r", False)) == ""
    assert library.claim(recording(library, operator.id, 7 * 3600.0, "o", True)) == ""


# -- the page --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def box(
    tmp_path_factory: pytest.TempPathFactory, free_port: Callable[[], int]
) -> tuple[int, str, str]:
    tmp = tmp_path_factory.mktemp("preview")
    store_path = tmp / "targum.db"
    store = Store(store_path)
    reader = store.finish_sign_in(store.start_sign_in("reader@example.com"))
    operator = store.finish_sign_in(store.start_sign_in("op@example.com"))
    assert reader is not None and operator is not None
    store.make_admin("op@example.com")
    port = free_port()
    threading.Thread(
        target=lambda: serve.start(
            out=tmp / "out",
            port=port,
            open_browser=False,
            store=store_path,
            require_account=True,
            public_address=f"https://{HOST}",
        ),
        daemon=True,
    ).start()
    for _ in range(60):
        try:
            probe = HTTPConnection("127.0.0.1", port, timeout=1)
            probe.request("GET", "/health")
            probe.getresponse().read()
            probe.close()
            break
        except OSError:
            time.sleep(0.1)
    return port, reader[1], operator[1]


def fetch(port: int, path: str, session: str = "") -> tuple[int, Any, dict[str, str]]:
    conn = HTTPConnection("127.0.0.1", port, timeout=10)
    conn.putrequest("GET", path, skip_host=True)
    conn.putheader("Host", HOST)
    if session:
        conn.putheader("Cookie", f"targum_session={session}")
    conn.endheaders()
    response = conn.getresponse()
    got = response.read().decode("utf-8", "replace")
    headers = dict(response.getheaders())
    conn.close()
    try:
        return response.status, json.loads(got), headers
    except json.JSONDecodeError:
        return response.status, got, headers


@pytest.mark.usefixtures("preview")
def test_plans_is_there_for_the_operator_and_nobody_else(box: tuple[int, str, str]) -> None:
    port, reader, operator = box
    status, page, _ = fetch(port, "/plans", operator)
    assert status == 200 and "Start the plan" in page
    assert fetch(port, "/plans", reader)[0] == 404
    assert fetch(port, "/plans")[0] == 404, "signed out: not even a sign-in redirect"


@pytest.mark.usefixtures("preview")
def test_account_me_says_plans_to_the_operator_only(box: tuple[int, str, str]) -> None:
    port, reader, operator = box
    _, mine, _ = fetch(port, "/account/me", operator)
    assert mine["plan"]["on"] is True and mine["plan"]["preview"] is True
    _, theirs, _ = fetch(port, "/account/me", reader)
    assert theirs["plan"] == {"on": False}
    assert theirs["hours"]["allowed"] == 8.0, "the reader's month is the whole one"


def test_without_the_preview_it_is_as_before(
    box: tuple[int, str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    port, reader, operator = box
    monkeypatch.delenv("TARGUM_PLANS", raising=False)
    monkeypatch.delenv(plans.PREVIEW_ENV, raising=False)
    for session in (operator, reader, ""):
        assert fetch(port, "/plans", session)[0] == 404
    assert fetch(port, "/account/me", operator)[1]["plan"] == {"on": False}
