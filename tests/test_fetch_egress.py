"""The way out for a host that refuses this address (targum-internal#226).

Seven of the 42 Hebrew hosts probed on 2026-09-07 refuse the caller rather than the
client, so the request has to leave from somewhere else. Nothing here touches a real
proxy or a real refusing host: those seven are evidence on the issue, not fixtures.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import pytest

from targum.accounts import SCHEMA_VERSION, Store
from targum.errors import TargumError, Unreachable
from targum.ingest import url as url_module
from targum.preflight import check_fetch_egress

PROXY = "http://user:secret@egress.example:9000"


@pytest.fixture(autouse=True)
def no_proxy(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (url_module.FETCH_PROXY_ENV, url_module.FALLBACK_PROXY_ENV):
        monkeypatch.delenv(name, raising=False)


def answering(monkeypatch: pytest.MonkeyPatch, *, direct: Any, through: Any) -> list[str]:
    """`_once` swapped for a table of two answers, recording which door was tried."""
    tried: list[str] = []

    def once(url: str, params: Any = None, proxy: str = "") -> url_module.Fetched:
        tried.append("proxy" if proxy else "direct")
        answer = through if proxy else direct
        if isinstance(answer, Exception):
            raise answer
        return answer

    monkeypatch.setattr(url_module, "_once", once)
    return tried


def page(via: str = "direct") -> url_module.Fetched:
    return url_module.Fetched("<html>ok</html>", "text/html", b"", via)


def shut_at(host: str, status: int | None = 403, via: str = "direct") -> Unreachable:
    return Unreachable("Could not fetch", "", status=status, host=host, via=via)


# --- the knob ----------------------------------------------------------------


def test_the_egress_is_read_at_call_time_and_youtubes_stands_in_for_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One account, two knobs — and a box that bought one way out should not have to
    write the same URL twice. Read per call, so unsetting it is the whole rollback."""
    assert url_module.egress() == ""
    monkeypatch.setenv(url_module.FALLBACK_PROXY_ENV, "http://youtube.example:8080")
    assert url_module.egress() == "http://youtube.example:8080"
    monkeypatch.setenv(url_module.FETCH_PROXY_ENV, PROXY)
    assert url_module.egress() == PROXY, "the fetch knob wins where both are set"


# --- when the retry happens, and when it does not ----------------------------


def test_a_page_that_answers_directly_is_never_paid_for(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(url_module.FETCH_PROXY_ENV, PROXY)
    tried = answering(monkeypatch, direct=page(), through=page("proxy"))
    got = url_module.fetch("https://open.example/a")
    assert tried == ["direct"] and got.via == "direct"


def test_a_refused_host_is_tried_once_more_through_the_egress(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The whole of what this buys: the host refuses this address, and the retry from
    somewhere else opens it. `via` says which, because "reachable" and "reachable from
    the egress we pay for" are two different facts."""
    monkeypatch.setenv(url_module.FETCH_PROXY_ENV, PROXY)
    tried = answering(monkeypatch, direct=shut_at("hebrew-academy.org.il"), through=page("proxy"))
    got = url_module.fetch("https://hebrew-academy.org.il/x")
    assert tried == ["direct", "proxy"] and got.via == "proxy"


def test_a_page_that_is_simply_not_there_is_not_fetched_twice(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A 404 is the opposite news: the server answered, so the door is open and the
    address was wrong. Retrying it would pay for somebody's typo."""
    monkeypatch.setenv(url_module.FETCH_PROXY_ENV, PROXY)
    tried = answering(monkeypatch, direct=shut_at("open.example", 404), through=page("proxy"))
    with pytest.raises(Unreachable):
        url_module.fetch("https://open.example/missing")
    assert tried == ["direct"]


def test_with_no_egress_a_refusal_is_the_answer(monkeypatch: pytest.MonkeyPatch) -> None:
    tried = answering(monkeypatch, direct=shut_at("davar1.co.il"), through=page("proxy"))
    with pytest.raises(Unreachable) as refused:
        url_module.fetch("https://davar1.co.il/x")
    assert tried == ["direct"] and refused.value.via == "direct"


def test_a_host_that_refuses_the_egress_too_says_so(monkeypatch: pytest.MonkeyPatch) -> None:
    """The fact worth having before anybody buys a second egress."""
    monkeypatch.setenv(url_module.FETCH_PROXY_ENV, PROXY)
    tried = answering(
        monkeypatch,
        direct=shut_at("nli.org.il"),
        through=shut_at("nli.org.il", via="proxy"),
    )
    with pytest.raises(Unreachable) as refused:
        url_module.fetch("https://nli.org.il/x")
    assert tried == ["direct", "proxy"] and refused.value.via == "proxy"


def test_a_size_refusal_is_not_a_shut_door(monkeypatch: pytest.MonkeyPatch) -> None:
    """`TargumError` is not `Unreachable`: too big is an answer, and answers are not
    retried."""
    monkeypatch.setenv(url_module.FETCH_PROXY_ENV, PROXY)
    tried = answering(monkeypatch, direct=TargumError("too big to read."), through=page("proxy"))
    with pytest.raises(TargumError):
        url_module.fetch("https://open.example/huge")
    assert tried == ["direct"]


# --- what the client is actually given ---------------------------------------


def test_the_client_is_handed_the_proxy_and_trusts_no_other(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`httpx` trusts `HTTP_PROXY` by default, which would route every fetch through a
    variable nobody meant as a targum setting while `via` still said direct."""
    import httpx

    seen: list[dict[str, Any]] = []
    real = httpx.Client.__init__

    def spy(self: httpx.Client, *args: Any, **kwargs: Any) -> None:
        seen.append(dict(kwargs))
        kwargs.pop("proxy", None)
        real(self, *args, **kwargs)

    monkeypatch.setattr(httpx.Client, "__init__", spy)
    monkeypatch.setattr(url_module, "_reachable", lambda target: None)
    with pytest.raises(Unreachable):
        url_module._once("https://nowhere.invalid/x", proxy=PROXY)
    assert seen and seen[0]["proxy"] == PROXY and seen[0]["trust_env"] is False
    seen.clear()
    with pytest.raises(Unreachable):
        url_module._once("https://nowhere.invalid/x")
    assert seen and seen[0]["proxy"] is None


def test_a_download_never_goes_through_the_egress(monkeypatch: pytest.MonkeyPatch) -> None:
    """An episode is 30 to 100 MB against an article's half a megabyte, and an
    unbounded proxied download is the one thing that could make a bill surprising."""
    import inspect

    source = inspect.getsource(url_module.download)
    assert "proxy=" not in source and "trust_env=False" in source


# --- what the store remembers ------------------------------------------------


def test_the_store_keeps_which_door_reached_a_host(tmp_path: Path) -> None:
    store = Store(tmp_path / "words.db")
    store.reach("open.example", True)
    store.reach("hebrew-academy.org.il", True, "", "proxy")
    assert store.egress_of("open.example") == "direct"
    assert store.egress_of("hebrew-academy.org.il") == "proxy", "reached because we pay to"
    assert store.egress_of("never-knocked.example") == ""
    store.reach("hebrew-academy.org.il", False, "403", "proxy")
    assert store.closed() == ["hebrew-academy.org.il"], "and it can shut again"


def test_a_database_from_before_the_column_reads_direct(tmp_path: Path) -> None:
    """Everything knocked before the column existed was knocked from the box itself."""
    path = tmp_path / "old.db"
    raw = sqlite3.connect(path)
    raw.executescript(
        "CREATE TABLE reached (host TEXT NOT NULL PRIMARY KEY, open INTEGER NOT NULL"
        " DEFAULT 0, why TEXT NOT NULL DEFAULT '', tries INTEGER NOT NULL DEFAULT 0,"
        " first INTEGER NOT NULL DEFAULT 0, last INTEGER NOT NULL DEFAULT 0);"
        "INSERT INTO reached (host, open) VALUES ('old.example', 1);"
        "PRAGMA user_version = 14;"
    )
    raw.commit()
    raw.close()

    store = Store(path)
    assert store.egress_of("old.example") == "direct"
    assert int(store.db.execute("PRAGMA user_version").fetchone()[0]) == SCHEMA_VERSION


# --- the deploy's own line ---------------------------------------------------


def test_an_unset_egress_is_quiet_on_a_laptop_and_said_on_a_box(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("TARGUM_REQUIRE_ACCOUNT", raising=False)
    assert check_fetch_egress(connect=False).ok
    monkeypatch.setenv("TARGUM_REQUIRE_ACCOUNT", "1")
    hosted = check_fetch_egress(connect=False)
    assert hosted.ok, "not a failure: it is what the box did until somebody bought one"
    assert url_module.FETCH_PROXY_ENV in (hosted.fix or "")


def test_the_egress_line_never_prints_the_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    """A residential proxy is bought with a username and a password in the URL, and this
    line is printed over SSH and again into the journal."""
    monkeypatch.setenv(url_module.FETCH_PROXY_ENV, PROXY)
    check = check_fetch_egress(connect=False)
    assert "egress.example:9000" in check.detail
    assert "secret" not in check.detail and "user" not in check.detail


def test_an_egress_that_does_not_answer_is_loud(monkeypatch: pytest.MonkeyPatch) -> None:
    """The shape a tunnel fails in, and now a reader waits twice for the same nothing."""
    import socket as socket_module

    monkeypatch.setenv(url_module.FETCH_PROXY_ENV, "http://127.0.0.1:9")

    def refuse(*args: object, **kwargs: object) -> None:
        raise OSError("connection refused")

    monkeypatch.setattr(socket_module, "create_connection", refuse)
    check = check_fetch_egress()
    assert not check.ok and not check.fatal and "did not answer" in check.detail


def test_a_proxy_with_no_host_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(url_module.FETCH_PROXY_ENV, "not-a-url")
    assert not check_fetch_egress(connect=False).ok
