"""Everything new comes in one mail a day (design.md §12, 2026-10-09): one mail a
reader, the daily cycles in it and the weekly left to its Monday mail, with a one-click
unsubscribe that stops every subscription it carried."""

from __future__ import annotations

import io
import json
import threading
import time
from collections.abc import Callable
from http.client import HTTPConnection
from pathlib import Path
from typing import Any

import pytest

from targum import serve
from targum import subscriptions as subs
from targum.accounts import Store
from targum.mail import ConsoleMailer

SITE = "https://targum.page"
HOST = "targum.page"
NOW = int(time.time() * 1000)
DEPLOY = Path(__file__).parents[1] / "deploy"


class Box(ConsoleMailer):
    """A mailer that keeps what it was handed."""

    def __init__(self, fail: str = "") -> None:
        super().__init__(io.StringIO())
        self.sent: list[dict[str, Any]] = []
        self.fail = fail

    def notify(self, to: str, subject: str, text: str, headers: Any = None, html: str = "") -> None:
        if to == self.fail:
            raise RuntimeError("bounced")
        self.sent.append(
            {"to": to, "subject": subject, "text": text, "headers": headers, "html": html}
        )


def reader(store: Store, email: str) -> int:
    signed = store.finish_sign_in(store.start_sign_in(email))
    assert signed is not None
    return signed[0].id


def test_one_mail_a_reader_with_everything_new(tmp_path: Path) -> None:
    store = Store(tmp_path / "targum.db")
    me = reader(store, "one@example.com")
    them = reader(store, "two@example.com")
    tehillim = int(store.add_subscription(me, "series", "tehillim")["id"])
    weekly = int(store.add_subscription(me, "series", "weekly")["id"])
    sport = int(store.add_subscription(me, "topic", "sport", language="he")["id"])
    kan = int(store.add_subscription(me, "channel", "UCkan", name="כאן ארכיון", cap=60)["id"])
    paused = int(store.add_subscription(them, "outlet", "globes", name="גלובס")["id"])
    store.add_sub_items(
        tehillim,
        [{"key": "d1", "title": "תהלים קכ", "reader": "/tehillim/read/1/", "state": "ready"}],
    )
    store.add_sub_items(
        weekly, [{"key": "w1", "title": "מבט השבוע", "reader": "/w/", "state": "ready"}]
    )
    store.add_sub_items(
        sport, [{"key": "a1", "title": "הפועל", "link": "https://one/a1", "state": "listed"}]
    )
    store.add_sub_items(
        kan,
        [
            {
                "key": "v1",
                "title": "פלאפל",
                "reader": "/reader/v1/reader/index.html",
                "state": "ready",
            },
            {"key": "v2", "title": "עוד", "link": "https://youtu.be/v2", "state": "due"},
            {
                "key": "v0",
                "title": "ישן",
                "link": "https://youtu.be/v0",
                "state": "listed",
                "came": "before",
            },
        ],
    )
    store.add_sub_items(
        paused, [{"key": "g1", "title": "שוק", "link": "https://g/1", "state": "listed"}]
    )
    store.set_subscription_state(them, paused, "paused")

    box = Box()
    report = subs.daily(store, box, SITE, now_ms=NOW, pause=0)
    assert report.sent == ["one@example.com"], "a paused subscription mails nothing"
    (mail,) = box.sent
    assert mail["subject"] == "3 new from your subscriptions"
    for said in ("תהלים קכ", "הפועל", "פלאפל", "Daily Tehillim", "Sport", "כאן ארכיון"):
        assert said in mail["text"], said
    for unsaid in ("מבט השבוע", "עוד", "ישן"):
        assert unsaid not in mail["text"], "the weekly has its Monday; the rest is not news yet"
    assert f"{SITE}/add?source=https%3A%2F%2Fone%2Fa1" in mail["text"], "news is a link"
    assert "Ready to watch, under Continue" in mail["text"]
    headers = mail["headers"]
    assert headers["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
    stop = headers["List-Unsubscribe"]
    for sub in (tehillim, sport, kan):
        token = store.subscription(me, sub)["stop"]  # type: ignore[index]
        assert f"t={token}" in stop and f"/series/stop?t={token}" in mail["text"]
    assert "daily.subscriptions.targum.page" in headers["List-Id"]
    assert "<img" not in mail["html"] and 'dir="auto" lang="he"' in mail["html"]

    again = subs.daily(store, box, SITE, now_ms=NOW, pause=0)
    assert again.sent == [] and len(box.sent) == 1, "a run started twice sends nothing twice"


def test_a_reader_hears_once_that_something_waits(tmp_path: Path) -> None:
    store = Store(tmp_path / "targum.db")
    me = reader(store, "one@example.com")
    kan = int(store.add_subscription(me, "channel", "UCkan", name="Kan", cap=30, said="ru")["id"])
    store.add_sub_items(kan, [{"key": "v1", "title": "первое", "link": "https://youtu.be/v1"}])
    store.set_sub_item(kan, "v1", state="waiting", why="cap")
    box = Box()
    subs.daily(
        store, box, SITE, now_ms=NOW, month_from=NOW - 1000, back=lambda ui: "1 ноября", pause=0
    )
    (mail,) = box.sent
    assert "Ждёт до 1 ноября" in mail["text"] and f"/subscriptions/{kan}#sub-cap" in mail["text"]
    assert mail["subject"] == "Kan: ⁨первое⁩", "one thing, named"
    store.add_sub_items(kan, [{"key": "v2", "title": "второе", "link": "https://youtu.be/v2"}])
    store.set_sub_item(kan, "v2", state="waiting", why="cap")
    subs.daily(store, box, SITE, now_ms=NOW, month_from=NOW - 1000, pause=0)
    assert len(box.sent) == 1, "what waits with it is not mailed again"


def test_a_mail_that_did_not_go_is_tried_again(tmp_path: Path) -> None:
    store = Store(tmp_path / "targum.db")
    me = reader(store, "one@example.com")
    sub = int(store.add_subscription(me, "series", "parasha")["id"])
    store.add_sub_items(sub, [{"key": "noach", "title": "נח", "reader": "/p/", "state": "ready"}])
    report = subs.daily(store, Box(fail="one@example.com"), SITE, now_ms=NOW, pause=0)
    assert report.failed == [("one@example.com", "bounced")]
    box = Box()
    assert subs.daily(store, box, SITE, now_ms=NOW, pause=0).sent == ["one@example.com"]
    # And what is a day and a half old is no longer news.
    stale = int(store.add_subscription(me, "series", "tehillim")["id"])
    store.add_sub_items(stale, [{"key": "d1", "title": "old", "reader": "/t/", "state": "ready"}])
    assert subs.daily(store, Box(), SITE, now_ms=NOW + 2 * 24 * 3600 * 1000, pause=0).sent == []


# --- the way out ----------------------------------------------------------------------


@pytest.fixture(scope="module")
def box(tmp_path_factory: pytest.TempPathFactory, free_port: Callable[[], int]) -> tuple[int, Path]:
    tmp = tmp_path_factory.mktemp("subscriptions-mail")
    store_path = tmp / "targum.db"
    Store(store_path)
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
    return port, store_path


def post(port: int, path: str, body: bytes) -> tuple[int, str]:
    conn = HTTPConnection("127.0.0.1", port, timeout=10)
    conn.putrequest("POST", path, skip_host=True)
    conn.putheader("Host", HOST)
    conn.putheader("Content-Type", "application/x-www-form-urlencoded")
    conn.putheader("Content-Length", str(len(body)))
    conn.endheaders()
    conn.send(body)
    response = conn.getresponse()
    got = response.read().decode("utf-8", "replace")
    conn.close()
    return response.status, got


def get(port: int, path: str) -> tuple[int, str]:
    conn = HTTPConnection("127.0.0.1", port, timeout=10)
    conn.putrequest("GET", path, skip_host=True)
    conn.putheader("Host", HOST)
    conn.endheaders()
    response = conn.getresponse()
    got = response.read().decode("utf-8", "replace")
    conn.close()
    return response.status, got


def test_one_click_stops_every_subscription_the_mail_carried(box: tuple[int, Path]) -> None:
    port, store_path = box
    store = Store(store_path)
    me = reader(store, "click@example.com")
    sport = store.add_subscription(me, "topic", "sport")
    kan = store.add_subscription(me, "channel", "UCkan", name="כאן ארכיון")
    keep = store.add_subscription(me, "series", "parasha")
    query = f"t={sport['stop']}&t={kan['stop']}"
    status, page = get(port, f"/subscriptions/stop?{query}")
    assert status == 200 and "Yes, stop" in page and "Sport, כאן ארכיון" in page
    assert store.subscription(me, int(sport["id"]))["state"] == "on", "fetching it stops nothing"  # type: ignore[index]
    status, page = post(port, f"/subscriptions/stop?{query}", b"List-Unsubscribe=One-Click")
    assert status == 200
    assert store.subscription(me, int(sport["id"]))["state"] == "off"  # type: ignore[index]
    assert store.subscription(me, int(kan["id"]))["state"] == "off"  # type: ignore[index]
    assert store.subscription(me, int(keep["id"]))["state"] == "on", "only what it carried"  # type: ignore[index]


def test_one_click_on_a_single_subscription_reads_its_token_from_the_address(
    box: tuple[int, Path],
) -> None:
    """RFC 8058's POST carries only `List-Unsubscribe=One-Click`; the token is in the
    address. The series' stop door read it from the form alone, so a one-click stopped
    nothing."""
    port, store_path = box
    store = Store(store_path)
    me = reader(store, "single@example.com")
    sub = store.add_subscription(me, "series", "tehillim")
    status, _ = post(port, f"/series/stop?t={sub['stop']}", b"List-Unsubscribe=One-Click")
    assert status == 200
    assert store.subscription(me, int(sub["id"]))["state"] == "off"  # type: ignore[index]


# --- the timer ------------------------------------------------------------------------


def _unit(name: str) -> dict[str, list[str]]:
    fields: dict[str, list[str]] = {}
    for line in (DEPLOY / name).read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.startswith(("#", "[")):
            key, value = line.split("=", 1)
            fields.setdefault(key.strip(), []).append(value.strip())
    return fields


def test_every_deploy_carries_and_enables_the_daily_mail() -> None:
    assert _unit("targum-subscriptions-mail.timer")["OnCalendar"] == ["*-*-* 04:30:00 UTC"]
    service = _unit("targum-subscriptions-mail.service")
    assert "targum subscriptions mail" in service["ExecStart"][0]
    assert service["EnvironmentFile"] == ["/etc/targum/targum.env"], "it mails through SMTP"
    script = (DEPLOY / "deploy.sh").read_text(encoding="utf-8")
    assert (
        "deploy/targum-subscriptions-mail.service deploy/targum-subscriptions-mail.timer" in script
    )
    assert "targum-subscriptions.timer targum-subscriptions-mail.timer" in script


def test_the_mail_runs_from_the_command_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from typer.testing import CliRunner

    from targum.cli import app

    store_path = tmp_path / "targum.db"
    store = Store(store_path)
    me = reader(store, "cli@example.com")
    sub = int(store.add_subscription(me, "series", "parasha")["id"])
    store.add_sub_items(sub, [{"key": "noach", "title": "נח", "reader": "/p/", "state": "ready"}])
    monkeypatch.delenv("TARGUM_SMTP_HOST", raising=False)
    monkeypatch.delenv("TARGUM_PUBLIC_ADDRESS", raising=False)
    refused = CliRunner().invoke(app, ["subscriptions", "mail", "--store", str(store_path)])
    assert refused.exit_code == 1 and "TARGUM_PUBLIC_ADDRESS" in refused.output
    monkeypatch.setenv("TARGUM_PUBLIC_ADDRESS", SITE)
    result = CliRunner().invoke(app, ["subscriptions", "mail", "--store", str(store_path)])
    assert result.exit_code == 0, result.output
    assert "subscriptions mail: 1 sent" in result.output
    assert json.dumps("נח")  # the letter went to the console
