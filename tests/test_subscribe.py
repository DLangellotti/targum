"""Subscribing, confirmed on targum's own page, and a channel's or a podcast's monthly cap
(design.md §12, "A channel or a podcast is subscribed to, never built from its address"
and "A monthly cap is the second press that lasts", 2026-10-09)."""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from http.client import HTTPConnection
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import pytest

from targum import serve
from targum import subscriptions as subs
from targum.accounts import Store
from targum.errors import TargumError
from targum.render.builder import subscribe_page
from targum.video import channels

HOST = "targum.page"
NOW = int(datetime(2026, 10, 9, tzinfo=UTC).timestamp() * 1000)
DAY = 24 * 3600 * 1000


# --- a channel's address, read only as a subscription -----------------------------------


@pytest.mark.parametrize(
    ("address", "named"),
    [
        ("https://www.youtube.com/channel/UCabc123", ("id", "UCabc123")),
        ("https://youtube.com/@kanarchive", ("handle", "@kanarchive")),
        ("https://www.youtube.com/@kanarchive/videos", ("handle", "@kanarchive")),
        ("https://www.youtube.com/user/oldname", ("username", "oldname")),
        ("https://www.youtube.com/c/Custom", ("handle", "@Custom")),
        ("https://www.youtube.com/watch?v=abc", None),
        ("https://example.org/@someone", None),
        ("ftp://www.youtube.com/@x", None),
    ],
)
def test_a_channels_address_is_read_for_what_it_names(
    address: str, named: tuple[str, str] | None
) -> None:
    assert channels.named(address) == named


def test_every_door_that_builds_still_refuses_a_channel() -> None:
    """The subscription is the only door that reads a channel's address (design.md §12)."""
    from targum.video import youtube

    with pytest.raises(TargumError):
        youtube.is_youtube("https://www.youtube.com/@kanarchive")


def fake_api(uploads: list[tuple[str, str, int, int]], live: str = "") -> Callable[..., Any]:
    """The Data API's three answers, from (id, title, published ms, seconds)."""
    asked: list[tuple[str, Mapping[str, str]]] = []

    def get(address: str, query: Mapping[str, str]) -> dict[str, Any]:
        asked.append((address, dict(query)))
        if address == channels.CHANNELS:
            return {
                "items": [
                    {
                        "id": "UCkan",
                        "snippet": {"title": "כאן ארכיון", "defaultLanguage": "he-IL"},
                        "contentDetails": {"relatedPlaylists": {"uploads": "UUkan"}},
                    }
                ]
            }
        if address == channels.PLAYLIST_ITEMS:
            return {
                "items": [
                    {"contentDetails": {"videoId": one[0]}, "snippet": {"title": one[1]}}
                    for one in uploads
                ]
                + (
                    [{"contentDetails": {"videoId": live}, "snippet": {"title": "live"}}]
                    if live
                    else []
                )
            }
        return {
            "items": [
                {
                    "id": one[0],
                    "snippet": {
                        "title": one[1],
                        "publishedAt": datetime.fromtimestamp(one[2] / 1000, UTC).isoformat(),
                        "liveBroadcastContent": "none",
                    },
                    "contentDetails": {"duration": f"PT{one[3] // 60}M{one[3] % 60}S"},
                }
                for one in uploads
            ]
            + (
                [
                    {
                        "id": live,
                        "snippet": {"liveBroadcastContent": "upcoming"},
                        "contentDetails": {},
                    }
                ]
                if live
                else []
            )
        }

    get.asked = asked  # type: ignore[attr-defined]
    return get


UPLOADS = [
    ("v3", "פלאפל או מקדונלדס?", NOW - 1 * DAY, 240),
    ("v2", "קרובים קרובים", NOW - 4 * DAY, 360),
    ("v1", "ישן", NOW - 40 * DAY, 660),
]


def test_a_channel_is_found_and_its_newest_read_with_their_lengths() -> None:
    get = fake_api(UPLOADS, live="v9")
    found = channels.find("https://www.youtube.com/@kanarchive", get, api_key="k")
    assert found == channels.Channel("UCkan", "כאן ארכיון", "UUkan", "he")
    assert get.asked[0][1]["forHandle"] == "@kanarchive"  # type: ignore[attr-defined]
    newest = channels.newest(found, get, api_key="k")
    assert [one.id for one in newest] == ["v3", "v2", "v1"], "a premiere is not a video yet"
    assert newest[0].seconds == 240 and newest[0].link.endswith("watch?v=v3")


def test_a_channel_that_is_not_there_is_said_so() -> None:
    with pytest.raises(TargumError) as refused:
        channels.find("https://www.youtube.com/@nobody", lambda a, q: {"items": []}, "k")
    assert refused.value.key == "subscribe.no-channel"
    with pytest.raises(TargumError) as refused:
        channels.find("https://example.org/x", lambda a, q: {}, "k")
    assert refused.value.key == "subscribe.not-a-channel"


def test_a_feed_says_its_own_name() -> None:
    from targum.weekly import feeds

    rss = (
        b"<?xml version='1.0'?><rss><channel><title>Hebrew Podcast</title>"
        b"<item><title>e</title></item></channel></rss>"
    )
    atom = b"<feed xmlns='http://www.w3.org/2005/Atom'><title>An Atom one</title></feed>"
    assert feeds.title(rss) == "Hebrew Podcast" and feeds.title(atom) == "An Atom one"
    assert feeds.title(b"not xml") == ""


# --- what the confirm page offers ----------------------------------------------------


def test_a_channel_is_described_by_what_it_put_out(monkeypatch: pytest.MonkeyPatch) -> None:
    get = fake_api(UPLOADS)
    monkeypatch.setattr(channels.discover, "fetch", get)
    monkeypatch.setattr(channels.discover, "key", lambda: "k")
    offer = subs.describe("channel", "https://www.youtube.com/@kanarchive", now_ms=NOW)
    assert offer["key"] == "UCkan" and offer["name"] == "כאן ארכיון" and offer["builds"]
    assert offer["source"] == "https://www.youtube.com/channel/UCkan"
    assert offer["creditsEach"] == 6, "the middle of 4, 6 and 11 minutes"
    assert offer["perWeek"] == round(2 * 7 / 30, 1), "two in the last thirty days"
    assert [one["key"] for one in offer["before"]] == ["v3", "v2", "v1"]


def test_a_podcast_is_described_by_its_feed(monkeypatch: pytest.MonkeyPatch) -> None:
    from targum.audio import episode
    from targum.weekly.feeds import Item

    monkeypatch.setattr(episode, "feed_of", lambda url: "https://Pod.example/feed.xml")
    items = [
        Item(
            title=f"פרק {n}",
            link=f"https://pod.example/{n}",
            guid=f"g{n}",
            enclosure=f"https://pod.example/{n}.mp3",
            seconds=1800.0,
            published=datetime.fromtimestamp((NOW - n * 7 * DAY) / 1000, UTC),
        )
        for n in (1, 2, 3)
    ]
    monkeypatch.setattr(episode, "episodes", lambda feed: ("A Hebrew podcast", items))
    offer = subs.describe("podcast", "https://pod.example/show", now_ms=NOW)
    assert offer["key"] == "https://pod.example/feed.xml", "one feed, however it is spelt"
    assert offer["name"] == "A Hebrew podcast" and offer["creditsEach"] == 30
    assert offer["before"][0] == {
        "key": "g1",
        "title": "פרק 1",
        "link": "https://pod.example/1.mp3",
        "published": NOW - 7 * DAY,
        "seconds": 1800.0,
    }
    monkeypatch.setattr(episode, "feed_of", lambda url: "")
    with pytest.raises(TargumError) as refused:
        subs.describe("podcast", "https://pod.example/show")
    assert refused.value.key == "subscribe.no-feed"


def test_news_is_free_and_a_series_is_named(monkeypatch: pytest.MonkeyPatch) -> None:
    from targum.chat import sources

    papers = [
        sources.Publisher(key="globes", name="Globes", publisher="גלובס", feed="https://g/rss"),
        sources.Publisher(key="ynet", name="ynet", publisher="ynet", feed="https://y/rss"),
        sources.Publisher(
            key="rbc", name="RBC", publisher="РБК", feed="https://r/rss", language="ru"
        ),
    ]
    monkeypatch.setattr(sources, "load", lambda: papers)
    topic = subs.describe("topic", "sport", language="he")
    assert topic["outlets"] == 2 and not topic["builds"] and topic["key"] == "sport"
    outlet = subs.describe("outlet", "rbc")
    assert outlet["name"] == "РБК" and outlet["language"] == "ru"
    for kind, given in (("topic", "gossip"), ("outlet", "nope"), ("series", "nope"), ("x", "y")):
        with pytest.raises(TargumError):
            subs.describe(kind, given)
    monkeypatch.setattr("targum.weekly.index.readable", lambda: [])
    weekly = subs.describe("series", "weekly")
    assert weekly["name"] and weekly["hebrew"] == "מבט השבוע" and weekly["every"] == "monday"


def test_subscribing_lists_what_was_out_before_with_a_press_each(tmp_path: Path) -> None:
    store = Store(tmp_path / "targum.db")
    signed = store.finish_sign_in(store.start_sign_in("one@example.com"))
    assert signed is not None
    me = signed[0].id
    offer = {
        "kind": "channel",
        "key": "UCkan",
        "name": "כאן ארכיון",
        "language": "he",
        "source": "https://www.youtube.com/channel/UCkan",
        "before": [
            {
                "key": one[0],
                "title": one[1],
                "link": f"https://youtu.be/{one[0]}",
                "published": one[2],
                "seconds": one[3],
            }
            for one in UPLOADS
        ],
    }
    row = subs.subscribe(store, me, offer, cap=999, said="ru")
    assert row["cap"] == 60, "a cap the page does not offer is the one chosen for them"
    items = store.sub_items(int(row["id"]))
    assert {item["came"] for item in items} == {"before"}
    assert {item["state"] for item in items} == {"listed"}, "never built by themselves"
    again = subs.subscribe(
        store, me, {**offer, "kind": "series", "key": "weekly"}, cap=120, said=""
    )
    assert again["cap"] == 0, "a series has no cap"


def test_the_confirm_page_draws_for_every_kind() -> None:
    caps = {"left": 354, "back": "November 1"}
    channel = {
        "kind": "channel",
        "key": "UCkan",
        "name": "כאן ארכיון",
        "hebrew": "",
        "what": "",
        "language": "he",
        "source": "https://www.youtube.com/channel/UCkan",
        "perWeek": 2.1,
        "seconds": 480.0,
        "creditsEach": 8,
        "builds": True,
        "outlets": 0,
        "before": [],
    }
    page = subscribe_page(channel, credits=caps, via="connector")
    assert "Asked for in a conversation" in page and "כאן ארכיון" in page
    assert 'value="60" checked' in page and "about 7 new ones" in page
    assert "About 8 credits." in page and "354 credits left in your plan" in page
    assert "About 2 new ones a week." in page
    assert 'name="source" value="https://www.youtube.com/channel/UCkan"' in page
    barred = subscribe_page(channel, credits=caps, allowed=False)
    assert "come with a plan" in barred and "disabled>" in barred
    topic = dict(
        channel, kind="topic", key="sport", name="", builds=False, outlets=3, creditsEach=0
    )
    page = subscribe_page(topic, language="ru")
    assert "Спорт" in page and 'name="key" value="sport"' in page and 'name="cap"' not in page
    assert "Подписаться" in page
    gone = subscribe_page(None, refused="We couldn't find that channel on YouTube.")
    assert "couldn&#39;t find" in gone or "couldn't find" in gone
    held = subscribe_page(channel, already={"id": 7})
    assert 'action="/subscriptions/7"' in held and 'action="/subscribe"' not in held


# --- the doors -------------------------------------------------------------------------


@pytest.fixture(scope="module")
def box(
    tmp_path_factory: pytest.TempPathFactory, free_port: Callable[[], int]
) -> tuple[int, str, str, Path]:
    tmp = tmp_path_factory.mktemp("subscribe")
    store_path = tmp / "targum.db"
    store = Store(store_path)
    one = store.finish_sign_in(store.start_sign_in("one@example.com"))
    two = store.finish_sign_in(store.start_sign_in("two@example.com"))
    assert one is not None and two is not None
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
    return port, one[1], two[1], store_path


def send(
    port: int, method: str, path: str, body: object = None, session: str = "", form: bool = False
) -> tuple[int, Any, dict[str, str]]:
    conn = HTTPConnection("127.0.0.1", port, timeout=10)
    conn.putrequest(method, path, skip_host=True)
    conn.putheader("Host", HOST)
    if form:
        raw = urlencode(body or {}).encode()
        conn.putheader("Content-Type", "application/x-www-form-urlencoded")
    else:
        raw = json.dumps(body).encode() if body is not None else b""
        if raw:
            conn.putheader("Content-Type", "application/json")
    if raw:
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


CHANNEL = {
    "kind": "channel",
    "key": "UCkan",
    "name": "כאן ארכיון",
    "hebrew": "",
    "what": "",
    "language": "he",
    "source": "https://www.youtube.com/channel/UCkan",
    "perWeek": 2.0,
    "seconds": 300.0,
    "creditsEach": 5,
    "builds": True,
    "outlets": 0,
    "before": [
        {"key": "v1", "title": "ישן", "link": "https://youtu.be/v1", "published": 1, "seconds": 300}
    ],
}


def test_a_channel_is_subscribed_to_on_its_confirm_page_with_the_cap_chosen_there(
    box: tuple[int, str, str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    port, mine, _, store_path = box
    asked: list[tuple[str, str]] = []

    def describe(kind: str, given: str, **_: Any) -> dict[str, Any]:
        asked.append((kind, given))
        return dict(CHANNEL)

    monkeypatch.setattr(subs, "describe", describe)
    status, page, _ = send(
        port,
        "GET",
        "/subscribe?kind=channel&source=https%3A%2F%2Fyoutube.com%2F%40kan&via=connector",
        session=mine,
    )
    assert status == 200 and "Subscribe to" in page and 'value="60" checked' in page
    assert asked == [("channel", "https://youtube.com/@kan")]
    status, _, headers = send(
        port,
        "POST",
        "/subscribe",
        {"kind": "channel", "source": CHANNEL["source"], "cap": "120", "via": "connector"},
        mine,
        form=True,
    )
    assert status == 303 and headers["Location"].startswith("/subscriptions/")
    assert asked[-1] == ("channel", CHANNEL["source"]), "read again at the press, never trusted"
    store = Store(store_path)
    me = store.person_by_email("one@example.com")
    assert me is not None
    row = store.subscription_for(me.id, "channel", "UCkan")
    assert row is not None and row["cap"] == 120 and row["name"] == "כאן ארכיון"
    assert [item["came"] for item in store.sub_items(int(row["id"]))] == ["before"]
    # Asked again, the page says it is already theirs and offers its page.
    status, page, _ = send(port, "GET", "/subscribe?kind=channel&source=x", session=mine)
    assert f'action="/subscriptions/{row["id"]}"' in page

    # The cap is changed on its own page, to one the page offers and nothing else.
    status, got, _ = send(
        port, "POST", f"/subscriptions/{row['id']}", {"action": "cap", "cap": 240}, mine
    )
    assert status == 200 and got["subscription"]["cap"] == 240
    status, got, _ = send(
        port, "POST", f"/subscriptions/{row['id']}", {"action": "cap", "cap": 7}, mine
    )
    assert status == 400 and got["error"] == "Choose one of the caps."


def test_with_plans_on_a_channel_needs_a_plan(
    box: tuple[int, str, str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    port, _, theirs, store_path = box
    monkeypatch.setenv("TARGUM_PLANS", "1")
    monkeypatch.setattr(subs, "describe", lambda kind, given, **_: dict(CHANNEL, key="UCother"))
    status, page, _ = send(port, "GET", "/subscribe?kind=channel&source=x", session=theirs)
    assert "come with a plan" in page and "disabled>" in page
    status, page, _ = send(
        port,
        "POST",
        "/subscribe",
        {"kind": "channel", "source": "x", "cap": "60"},
        theirs,
        form=True,
    )
    assert status == 200 and "come with a plan" in page
    store = Store(store_path)
    them = store.person_by_email("two@example.com")
    assert them is not None and store.subscription_for(them.id, "channel", "UCother") is None


def test_a_source_that_cannot_be_read_is_said_plainly(
    box: tuple[int, str, str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    port, mine, _, _ = box

    def refuse(kind: str, given: str, **_: Any) -> dict[str, Any]:
        raise TargumError("We couldn't find that channel on YouTube.", key="subscribe.no-channel")

    monkeypatch.setattr(subs, "describe", refuse)
    status, page, _ = send(port, "GET", "/subscribe?kind=channel&source=x", session=mine)
    assert status == 200 and "find that channel on YouTube" in page
    monkeypatch.setattr(subs, "describe", lambda *a, **k: 1 / 0)
    status, page, _ = send(port, "GET", "/subscribe?kind=channel&source=x", session=mine)
    assert "couldn" in page and "Try again in a moment" in page
