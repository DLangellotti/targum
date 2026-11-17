"""The operator's preview reaches the pay presses and Manage (targum-internal#59 phase 2,
after #1303): with `TARGUM_PLANS_PREVIEW=operators` and plans off, an admin account can
press Start the plan, Top up and Manage against Paddle's sandbox; every other account,
signed in or not, still gets a 404, and nothing anybody may spend changes."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterator
from http.client import HTTPConnection

import pytest
from test_billing_checkout import TXN, Paddle, configure, fetch, press

from targum import billing, plans, serve
from targum.accounts import Store

HOST = "targum.page"


@pytest.fixture
def paddle(monkeypatch: pytest.MonkeyPatch) -> Iterator[Paddle]:
    mock = Paddle()
    monkeypatch.setattr(billing.urllib.request, "urlopen", mock)
    yield mock


@pytest.fixture
def preview(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TARGUM_PLANS", raising=False)
    monkeypatch.setenv(plans.PREVIEW_ENV, "operators")
    configure(monkeypatch)


@pytest.fixture(scope="module")
def box(
    tmp_path_factory: pytest.TempPathFactory, free_port: Callable[[], int]
) -> tuple[int, dict[str, str]]:
    tmp = tmp_path_factory.mktemp("preview-pay")
    store_path = tmp / "targum.db"
    store = Store(store_path)
    sessions = {}
    for name in ("op", "reader"):
        made = store.finish_sign_in(store.start_sign_in(f"{name}@example.com"))
        assert made is not None
        sessions[name] = made[1]
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
    return port, sessions


@pytest.mark.usefixtures("preview")
def test_the_operator_can_press_start_and_top_up_in_the_preview(
    box: tuple[int, dict[str, str]], paddle: Paddle
) -> None:
    port, sessions = box
    status, headers, _ = press(port, serve.PLANS_START, {"cadence": "month"}, sessions["op"])
    assert status == 303 and headers["Location"].startswith(f"/plans?checkout={TXN}&ticket=")
    _, _, page = fetch(port, headers["Location"], sessions["op"])
    assert "cdn.paddle.com/paddle/v2/paddle.js" in page
    status, headers, _ = press(port, serve.PLANS_TOP_UP, {"size": "60"}, sessions["op"])
    assert status == 303 and headers["Location"].startswith("/plans?checkout=")
    assert len(paddle.asked) == 2


@pytest.mark.usefixtures("preview")
def test_nobody_else_reaches_a_press_or_manage_in_the_preview(
    box: tuple[int, dict[str, str]], paddle: Paddle
) -> None:
    port, sessions = box
    reader = sessions["reader"]
    assert press(port, serve.PLANS_START, {"cadence": "month"}, reader)[0] == 404
    assert press(port, serve.PLANS_TOP_UP, {"size": "60"}, reader)[0] == 404
    assert fetch(port, serve.PLANS_MANAGE, reader)[0] == 404
    # Signed out: turned away before any of it, whichever door says so first.
    for status in (
        press(port, serve.PLANS_START, {"cadence": "month"})[0],
        fetch(port, serve.PLANS_MANAGE, "")[0],
    ):
        assert status in (302, 303, 401, 403, 404), status
    assert paddle.asked == []


@pytest.mark.usefixtures("preview")
def test_manage_is_there_for_the_operator_in_the_preview(
    box: tuple[int, dict[str, str]], paddle: Paddle
) -> None:
    """With no Paddle customer yet, Manage sends the operator to /plans, as it does a
    reader who never paid; the point here is that it is not a 404."""
    port, sessions = box
    status, headers, _ = fetch(port, serve.PLANS_MANAGE, sessions["op"])
    assert (status, headers["Location"]) == (303, "/plans")


def test_without_the_preview_the_operator_gets_the_404_too(
    box: tuple[int, dict[str, str]], paddle: Paddle, monkeypatch: pytest.MonkeyPatch
) -> None:
    port, sessions = box
    monkeypatch.delenv("TARGUM_PLANS", raising=False)
    monkeypatch.delenv(plans.PREVIEW_ENV, raising=False)
    configure(monkeypatch)
    assert press(port, serve.PLANS_START, {"cadence": "month"}, sessions["op"])[0] == 404
    assert fetch(port, serve.PLANS_MANAGE, sessions["op"])[0] == 404
    assert paddle.asked == []
