"""Plans, behind `TARGUM_PLANS` (design.md §12, "Free and Plan, behind a switch", "The
plans page is the one place money shows" and "A free reader meets the plan where they
reach for it", 2026-10-09).

Every rule is tested with the switch off as well as on, because the promise that matters
most today is the first one: **off, nothing changes for anybody.**"""

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
from targum.accounts import Store
from targum.render.builder import plans_page, you_page
from targum.serve import UPLOAD_SECONDS, Job, Library

HOST = "targum.page"
HOUR = 60.0 * 60.0


@pytest.fixture
def off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TARGUM_PLANS", raising=False)


@pytest.fixture
def on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TARGUM_PLANS", "1")


def a_library(tmp_path: Path) -> Library:
    """Money rails wide open, so only the month's credits can refuse."""
    return Library(
        tmp_path / "out",
        max_cost=1000.0,
        budget=1000.0,
        store=Store(tmp_path / "targum.db"),
        account_budget=None,
    )


def recording(library: Library, who: int, seconds: float, ident: str, admin: bool = False) -> Job:
    job = Job(
        id=ident,
        source="upload:talk.mp3",
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


def words(n: int, status: int = 1, start: int = 0) -> list[dict[str, Any]]:
    return [
        {"language": "he", "lemma": f"w{i}", "surface": f"w{i}", "status": status, "seen": 10 + i}
        for i in range(start, start + n)
    ]


# -- the allowance ------------------------------------------------------------------


@pytest.mark.usefixtures("off")
def test_off_every_account_keeps_the_whole_month(tmp_path: Path) -> None:
    library = a_library(tmp_path)
    assert library.allowance() == UPLOAD_SECONDS
    assert library.claim(recording(library, 1, 7 * HOUR, "a")) == ""
    assert plans.summary(None) == {"on": False}
    assert plans.word_cap(None) is None


@pytest.mark.usefixtures("on")
def test_on_free_gets_sixty_credits_and_plan_the_whole_month(tmp_path: Path) -> None:
    library = a_library(tmp_path)
    assert library.allowance() == 60 * 60
    assert library.allowance(paid_plan=True) == UPLOAD_SECONDS
    assert library.claim(recording(library, 1, 50 * 60, "a")) == ""
    refused = library.claim(recording(library, 1, 45 * 60, "b"))
    # The plan, not Top up: there is no top-up on Free.
    assert refused.act == "plan"
    assert "It needs 45 credits and you have 10 left this month" in refused
    assert "A plan gives you 480 a month, which is 8 hours" in refused
    assert "reset on" in refused.fact
    assert "$" not in refused and "$" not in refused.fact, "never money outside /plans"
    # The operator stands in for Plan, and is held to no month at all.
    assert library.claim(recording(library, 2, 7 * HOUR, "c", admin=True)) == ""


@pytest.mark.usefixtures("on")
def test_on_a_spent_month_says_so_and_offers_the_plan(tmp_path: Path) -> None:
    library = a_library(tmp_path)
    assert library.claim(recording(library, 1, 60 * 60, "a")) == ""
    refused = library.claim(recording(library, 1, 60, "b"))
    assert "You've used this month's 60 credits" in refused and refused.act == "plan"


@pytest.mark.usefixtures("off")
def test_off_the_refusal_is_top_up_as_it_was(tmp_path: Path) -> None:
    library = a_library(tmp_path)
    library.claim(recording(library, 1, 8 * HOUR, "a"))
    refused = library.claim(recording(library, 1, 60, "b"))
    assert refused.act == "top-up" and "Top up" in refused


@pytest.mark.usefixtures("on")
def test_on_chatting_is_held_by_the_day_and_not_the_month(tmp_path: Path) -> None:
    library = a_library(tmp_path)
    library.chat_budget = None
    library.claim(recording(library, 1, 60 * 60, "spent"))
    turn = Job(id="t", source="chat", estimate=0.001, owner=1, seconds=5.0)
    assert library.claim_turn(turn, kind="chat") == "", "chatting stays included"
    voice = Job(id="v", source="voice", estimate=0.001, owner=1, seconds=60.0)
    assert library.claim_turn(voice, kind="voice").act == "plan", "a voice is audio"


def test_monthly_credits_do_not_carry_over(tmp_path: Path, on: None) -> None:
    """Last month's spend and last month's leftovers are both forgotten on the 1st."""
    library = a_library(tmp_path)
    assert library.store is not None
    used = library.store.hours_used(1, library._month_from())
    assert used == 0.0
    # A month that starts later than anything claimed sees none of it.
    library.claim(recording(library, 1, 30 * 60, "a"))
    assert library.store.hours_used(1, library._month_from()) == 30 * 60
    assert library.store.hours_used(1, int(time.time() * 1000) + 10_000) == 0.0
    assert library.allowance() == 60 * 60, "and the month is 60 again, never 60 plus what was left"


# -- the word list ------------------------------------------------------------------


def test_off_a_word_list_takes_any_number(tmp_path: Path, off: None) -> None:
    store = Store(tmp_path / "targum.db")
    person = store.finish_sign_in(store.start_sign_in("a@example.com"))
    assert person is not None
    me = store.person_by_email("a@example.com")
    assert me is not None
    store.push(me, {"words": words(320)}, word_cap=plans.word_cap(me))
    assert store.listed_words(me.id) == 320


def test_on_a_free_word_list_stops_at_three_hundred(tmp_path: Path, on: None) -> None:
    store = Store(tmp_path / "targum.db")
    store.finish_sign_in(store.start_sign_in("a@example.com"))
    me = store.person_by_email("a@example.com")
    assert me is not None
    cap = plans.word_cap(me)
    assert cap == 300
    store.push(me, {"words": words(305)}, word_cap=cap)
    assert store.listed_words(me.id) == 300, "the five past the cap are not taken"
    # A word already on the list moves between stages; known and ignored are never held.
    moved = [{"language": "he", "lemma": "w0", "status": 3, "seen": 10_000}]
    store.push(me, {"words": moved + words(5, status=9, start=400)}, word_cap=cap)
    assert store.listed_words(me.id) == 300
    known = {row["lemma"] for row in store.pull(me)["words"] if row["status"] == 9}
    assert {"w400", "w404"} <= known
    # A word taken off makes room for one more.
    store.push(me, {"words": [{**words(1)[0], "gone": 1, "seen": 20_000}]}, word_cap=cap)
    store.push(me, {"words": words(1, start=900)}, word_cap=cap)
    assert store.listed_words(me.id) == 300


def test_on_the_operator_keeps_every_word(tmp_path: Path, on: None) -> None:
    store = Store(tmp_path / "targum.db")
    store.finish_sign_in(store.start_sign_in("op@example.com"))
    store.make_admin("op@example.com")
    me = store.person_by_email("op@example.com")
    assert me is not None and plans.word_cap(me) is None


# -- the pages ----------------------------------------------------------------------


def test_the_plans_page_says_both_plans_and_greys_every_pay_button(on: None) -> None:
    page = plans_page(plans.summary(None))
    assert "Free" in page and "$0" in page and "$16" in page and "$39" in page
    assert "60 credits a month" in page and "up to 300 words" in page
    assert "480 credits a month, which is 8 hours of audio or video" in page
    assert "Start the plan</button>" in page and 'class="btn soon plan-start" disabled' in page
    assert "Payments open soon" in page and "Prices are in US dollars." in page
    assert "Your channel and podcast subscriptions pause" in page
    assert "Your plan</span>" in page
    russian = plans_page(plans.summary(None), language="ru")
    assert "Тарифы" in russian and "Оформить тариф" in russian


def test_the_foot_links_the_plans_only_while_they_are_on(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("TARGUM_PLANS", raising=False)
    assert '<li><a href="/plans">' not in you_page("")
    monkeypatch.setenv("TARGUM_PLANS", "1")
    assert '<li><a href="/plans">' in you_page("")


def test_the_account_page_carries_both_plan_cards(off: None) -> None:
    """The early-access card is what shows with the switch off; the other is drawn only
    when `/account/me` says plans are on."""
    page = you_page("")
    assert 'id="plan"' in page and 'id="plan-on"' in page
    assert 'id="plan-on" aria-labelledby="plan-on-title" hidden' in page


# -- the server, both ways ----------------------------------------------------------


@pytest.fixture(scope="module")
def box(
    tmp_path_factory: pytest.TempPathFactory, free_port: Callable[[], int]
) -> tuple[int, str, str, Path]:
    tmp = tmp_path_factory.mktemp("plans")
    store_path = tmp / "targum.db"
    store = Store(store_path)
    one = store.finish_sign_in(store.start_sign_in("one@example.com"))
    op = store.finish_sign_in(store.start_sign_in("op@example.com"))
    assert one is not None and op is not None
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
    return port, one[1], op[1], store_path


def send(
    port: int, method: str, path: str, body: object = None, session: str = ""
) -> tuple[int, Any, dict[str, str]]:
    conn = HTTPConnection("127.0.0.1", port, timeout=10)
    conn.putrequest(method, path, skip_host=True)
    conn.putheader("Host", HOST)
    raw = json.dumps(body).encode() if body is not None else b""
    if raw:
        conn.putheader("Content-Type", "application/json")
        conn.putheader("Content-Length", str(len(raw)))
    if session:
        conn.putheader("Cookie", f"targum_session={session}")
    conn.endheaders()
    if raw:
        conn.send(raw)
    response = conn.getresponse()
    got = response.read()
    headers = dict(response.getheaders())
    conn.close()
    try:
        return response.status, json.loads(got), headers
    except json.JSONDecodeError:
        return response.status, got.decode("utf-8", "replace"), headers


def test_off_the_server_says_nothing_of_plans(
    box: tuple[int, str, str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    port, mine, _, _ = box
    monkeypatch.delenv("TARGUM_PLANS", raising=False)
    status, me, _ = send(port, "GET", "/account/me", session=mine)
    assert me["plan"] == {"on": False}
    assert me["hours"]["allowed"] == 8.0, "480 credits, as every account has"
    status, _, _ = send(port, "GET", "/plans", session=mine)
    assert status == 404


def test_on_the_server_says_which_plan_and_serves_the_page(
    box: tuple[int, str, str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    port, mine, operator, _ = box
    monkeypatch.setenv("TARGUM_PLANS", "1")
    status, me, _ = send(port, "GET", "/account/me", session=mine)
    assert me["plan"]["on"] is True and me["plan"]["plan"] == "free"
    assert me["plan"]["words"] == 300 and me["plan"]["credits"] == 60
    assert me["hours"]["allowed"] == 1.0, "an hour: 60 credits"
    status, op, _ = send(port, "GET", "/account/me", session=operator)
    assert op["plan"]["plan"] == "plan" and op["plan"]["words"] is None
    status, page, _ = send(port, "GET", "/plans", session=mine)
    assert status == 200 and "Start the plan" in page
    status, _, headers = send(port, "GET", "/plans")
    assert status in (302, 303) and headers.get("Location", "").endswith("/account/signin")


def test_on_a_free_reader_cannot_push_past_the_cap(
    box: tuple[int, str, str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    port, mine, _, store_path = box
    monkeypatch.setenv("TARGUM_PLANS", "1")
    status, answer, _ = send(port, "POST", "/sync", {"words": words(310)}, session=mine)
    assert status == 200
    store = Store(store_path)
    me = store.person_by_email("one@example.com")
    assert me is not None and store.listed_words(me.id) == 300


def test_on_resuming_a_channel_needs_the_plan(
    box: tuple[int, str, str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    port, mine, _, store_path = box
    store = Store(store_path)
    me = store.person_by_email("one@example.com")
    assert me is not None
    row = store.add_subscription(
        me.id, "channel", "UCplan", name="A channel", language="he", source="https://x"
    )
    sub = int(row["id"])
    store.set_subscription_state(me.id, sub, "paused")
    monkeypatch.setenv("TARGUM_PLANS", "1")
    status, answer, _ = send(port, "POST", f"/subscriptions/{sub}", {"action": "resume"}, mine)
    assert status == 403 and answer["plan"] is True
    monkeypatch.delenv("TARGUM_PLANS")
    status, answer, _ = send(port, "POST", f"/subscriptions/{sub}", {"action": "resume"}, mine)
    assert status == 200, "off, anybody may"


def test_a_press_refused_for_credits_draws_the_plan_on_free_and_top_up_off(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The quote page a conversation hands over (board PlanUpgradeMoment, 2): a free
    reader's refused press draws the plan in place; with plans off it is the sentence it
    always was."""
    from targum.render.builder import press_page

    for switch, act in (("1", "plan"), ("", "top-up")):
        monkeypatch.setenv("TARGUM_PLANS", switch)
        library = a_library(tmp_path / (switch or "off"))
        assert library.claim(recording(library, 1, library.allowance() or 0, "spent")) == ""
        job = recording(library, 1, 14 * 60, "part")
        job.stage = "ready"
        refused = library.press(job)
        assert refused.act == act
        page = press_page(job.state())
        assert ('class="fault-panel fault-upgrade"' in page) is (act == "plan")
        assert ('href="/plans"' in page) is (act == "plan")
