"""The poll that finds what a subscription's source put out, and the box's own round that
gets a channel's or a podcast's new item ready inside its cap (design.md §12, "A channel
or a podcast is subscribed to, never built from its address" and "A monthly cap is the
second press that lasts", 2026-10-09)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from targum import subscriptions as subs
from targum.accounts import Store
from targum.serve import Job, Library
from targum.weekly.feeds import Item

NOW = int(datetime(2026, 10, 9, 12, tzinfo=UTC).timestamp() * 1000)
DAY = 24 * 3600 * 1000
DEPLOY = Path(__file__).parents[1] / "deploy"


def reader(store: Store, email: str = "one@example.com") -> int:
    signed = store.finish_sign_in(store.start_sign_in(email))
    assert signed is not None
    return signed[0].id


def at(ms: int) -> datetime:
    return datetime.fromtimestamp(ms / 1000, UTC)


def since(store: Store, sub_id: int, when: int) -> None:
    with store.write() as db:
        db.execute("UPDATE subscription SET since = ? WHERE id = ?", (when, sub_id))


# --- the poll -------------------------------------------------------------------------


def test_a_channel_is_looked_at_and_its_new_uploads_are_due(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from targum.video import channels

    store = Store(tmp_path / "targum.db")
    me = reader(store)
    sub = int(store.add_subscription(me, "channel", "UCkan", cap=60)["id"])
    since(store, sub, NOW - 2 * DAY)
    uploads = [
        channels.Upload("v3", "חדש", NOW - DAY, 240),
        channels.Upload("v2", "ישן", NOW - 3 * DAY, 300),
    ]
    found = channels.Channel("UCkan", "כאן", "UUkan")
    monkeypatch.setattr(channels, "find", lambda url: found)
    monkeypatch.setattr(channels, "newest", lambda channel: uploads)
    looked = subs.poll(store, now_ms=NOW)
    assert (looked.looked, looked.found) == (1, 2)
    items = {item["key"]: item for item in store.sub_items(sub)}
    assert items["v3"]["state"] == "due" and items["v3"]["came"] == ""
    assert items["v2"]["state"] == "listed" and items["v2"]["came"] == "before"
    assert items["v3"]["link"] == "https://www.youtube.com/watch?v=v3"
    again = subs.poll(store, now_ms=NOW)
    assert again.found == 0, "a look that runs twice finds nothing the second time"
    assert store.subscription(me, sub)["polled"] > 0  # type: ignore[index]

    # Paused, what comes out is listed for a press when it resumes, never built.
    store.set_subscription_state(me, sub, "paused")
    uploads.insert(0, channels.Upload("v4", "בזמן ההפסקה", NOW, 200))
    subs.poll(store, now_ms=NOW)
    paused = {item["key"]: item for item in store.sub_items(sub)}["v4"]
    assert paused["state"] == "listed" and paused["came"] == "paused"


def test_a_podcast_lists_every_episode_since_the_last_one_seen(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from targum.audio import episode

    store = Store(tmp_path / "targum.db")
    me = reader(store)
    sub = int(
        store.add_subscription(
            me, "podcast", "https://pod.example/feed.xml", source="https://pod.example/feed.xml"
        )["id"]
    )
    since(store, sub, NOW - 10 * DAY)
    items = [
        Item(
            title=f"פרק {n}",
            link="",
            guid=f"g{n}",
            enclosure=f"https://pod.example/{n}.mp3",
            seconds=600.0,
            published=at(NOW - n * 4 * DAY),
        )
        for n in (1, 2, 3)
    ]
    asked: list[str] = []

    def episodes(feed: str) -> tuple[str, list[Item]]:
        asked.append(feed)
        return "A podcast", items

    monkeypatch.setattr(episode, "episodes", episodes)
    subs.poll(store, now_ms=NOW)
    got = {item["key"]: (item["state"], item["came"]) for item in store.sub_items(sub)}
    assert got == {"g1": ("due", ""), "g2": ("due", ""), "g3": ("listed", "before")}
    assert asked == ["https://pod.example/feed.xml"]


def test_news_comes_as_links_a_few_a_day(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from targum.chat import sources

    store = Store(tmp_path / "targum.db")
    me = reader(store)
    topic = int(store.add_subscription(me, "topic", "sport", language="he")["id"])
    outlet = int(store.add_subscription(me, "outlet", "globes", language="he")["id"])
    for one in (topic, outlet):
        since(store, one, NOW - DAY)
    papers = [
        sources.Publisher(key="globes", name="Globes", publisher="גלובס", feed="https://g/rss"),
        sources.Publisher(
            key="one", name="one", publisher="ONE", feed="https://one/rss", topics=("sport",)
        ),
        sources.Publisher(
            key="rbc",
            name="RBC",
            publisher="РБК",
            feed="https://r/rss",
            language="ru",
            topics=("sport",),
        ),
    ]
    monkeypatch.setattr(sources, "load", lambda: papers)
    pulled: list[str] = []

    def pull(url: str) -> list[Item]:
        pulled.append(url)
        if url == "https://r/rss":
            raise AssertionError("a Hebrew topic reads no Russian paper")
        if url == "https://g/rss":
            return [
                Item(
                    title="שוק",
                    link="https://g/a1",
                    published=at(NOW - 3600_000),
                    categories=("כלכלה",),
                ),
                Item(title="ישן", link="https://g/a0", published=at(NOW - 2 * DAY)),
            ]
        return [
            Item(title=f"משחק {n}", link=f"https://one/m{n}", published=at(NOW - n * 60_000))
            for n in range(1, 6)
        ]

    looked = subs.poll(store, now_ms=NOW, pull=pull)
    assert looked.failed == []
    sport = store.sub_items(topic)
    assert [item["key"] for item in sport] == ["https://one/m1", "https://one/m2", "https://one/m3"]
    assert {item["state"] for item in sport} == {"listed"}, "a press each, never built"
    assert [item["key"] for item in store.sub_items(outlet)] == ["https://g/a1"]
    assert pulled.count("https://g/rss") == 1, "one pull of a paper a run"
    subs.poll(store, now_ms=NOW + 60_000, pull=pull)
    assert len(store.sub_items(topic)) == 3, "three a day, and no more"


def test_a_series_instalment_is_ready_to_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from targum import series

    store = Store(tmp_path / "targum.db")
    me = reader(store)
    sub = int(store.add_subscription(me, "series", "parasha")["id"])
    portion = {
        "id": "parasha",
        "name": "The weekly portion",
        "instalment": {
            "id": "noach",
            "title": "Noach",
            "hebrew": "נח",
            "reader": "/parasha/read/noach/sec-0001.html",
        },
    }
    monkeypatch.setattr(series, "current", lambda *a, **k: [portion])
    subs.poll(store, now_ms=NOW)
    (item,) = store.sub_items(sub)
    assert item["state"] == "ready" and item["title"] == "נח"
    assert item["reader"] == "/parasha/read/noach/sec-0001.html"
    assert [one["key"] for one in store.new_sub_items(me)] == ["noach"]


def test_one_source_down_is_not_the_run_down(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from targum.audio import episode
    from targum.video import channels

    store = Store(tmp_path / "targum.db")
    me = reader(store)
    broken = int(store.add_subscription(me, "channel", "UCx")["id"])
    fine = int(store.add_subscription(me, "podcast", "https://p/f", source="https://p/f")["id"])

    def refuse(url: str) -> Any:
        raise RuntimeError("quota")

    monkeypatch.setattr(channels, "find", refuse)
    monkeypatch.setattr(episode, "episodes", lambda feed: ("p", []))
    looked = subs.poll(store, now_ms=NOW)
    assert looked.failed == [(broken, "quota")] and looked.looked == 1
    assert store.subscription(me, broken)["polled"] == 0  # type: ignore[index]
    assert store.subscription(me, fine)["polled"] > 0  # type: ignore[index]


# --- getting it ready -------------------------------------------------------------------


def a_library(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, seconds: float = 240.0, **kwargs: Any
) -> tuple[Library, Store, int]:
    store = Store(tmp_path / "targum.db")
    me = reader(store)
    library = Library(tmp_path / "out", store=store, **kwargs)

    def prepare(job: Job) -> None:
        job.title = "a video"
        job.audio = True
        job.seconds = seconds
        job.estimate = 0.05
        job.stage = "ready"

    monkeypatch.setattr(library, "prepare", prepare)
    return library, store, me


def due(store: Store, me: int, *keys: str, cap: int = 60) -> int:
    sub = int(store.add_subscription(me, "channel", "UCkan", cap=cap)["id"])
    store.add_sub_items(
        sub,
        [
            {"key": key, "title": key, "link": f"https://youtu.be/{key}", "state": "due"}
            for key in keys
        ],
    )
    return sub


def test_a_due_item_is_claimed_as_a_subscription_job_through_the_press(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    library, store, me = a_library(tmp_path, monkeypatch)
    sub = due(store, me, "v1")
    readied = subs.get_ready(library, store)
    assert readied.started == ["v1"]
    (item,) = store.sub_items(sub)
    assert item["state"] == "building" and item["credits"] == 4 and item["job"]
    row = store.job(item["job"])
    assert row is not None and row["kind"] == "subscription" and row["stage"] == "queued"
    assert row["claimed"] > 0 and row["length"] == 240.0, "claimed like any build"
    options = json.loads(row["options"])
    assert options["subscription"] == sub and options["item"] == "v1"
    assert store.month_credits(me, sub, library._month_from()) == 4
    assert item["job"] in library.jobs.builds, "in the bell like any build"
    again = subs.get_ready(library, store)
    assert again.started == [], "a round that runs again claims nothing twice"

    # Its build ends, and the item opens as its text.
    with store.write() as db:
        db.execute("UPDATE job SET stage = 'done', reader = 'a-video' WHERE id = ?", (item["job"],))
    assert subs.get_ready(library, store).settled == 1
    (item,) = store.sub_items(sub)
    assert item["state"] == "ready" and item["reader"] == "/reader/a-video/reader/index.html"


def test_an_item_past_the_cap_waits_and_goes_when_the_cap_is_raised(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    library, store, me = a_library(tmp_path, monkeypatch, seconds=25 * 60)
    sub = due(store, me, "v1", "v2", cap=30)
    readied = subs.get_ready(library, store)
    assert readied.started == ["v1"] and readied.waiting == [("v2", "cap")]
    states = {item["key"]: (item["state"], item["why"]) for item in store.sub_items(sub)}
    assert states["v2"] == ("waiting", "cap")
    prepared = {item["key"]: item["job"] for item in store.sub_items(sub)}["v2"]
    assert subs.get_ready(library, store).waiting == [("v2", "cap")], "known, not asked again"
    assert store.set_subscription_cap(me, sub, 60)
    assert subs.get_ready(library, store).started == ["v2"]
    assert {item["key"]: item["job"] for item in store.sub_items(sub)}["v2"] == prepared


def test_the_plans_credits_and_the_box_hold_it_too(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    library, store, me = a_library(tmp_path, monkeypatch, upload_seconds=60.0)
    sub = due(store, me, "v1")
    assert subs.get_ready(library, store).waiting == [("v1", "credits")]
    assert store.sub_items(sub)[0]["state"] == "waiting"
    assert store.job(store.sub_items(sub)[0]["job"])["claimed"] == 0  # type: ignore[index]

    boxed, other, them = a_library(tmp_path / "b", monkeypatch, budget=0.01)
    held = due(other, them, "v1")
    assert subs.get_ready(boxed, other).waiting == [("v1", "box")]
    assert other.sub_items(held)[0]["why"] == "box"


def test_with_plans_on_a_free_account_builds_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TARGUM_PLANS", "1")
    library, store, me = a_library(tmp_path, monkeypatch)
    sub = due(store, me, "v1")
    assert subs.get_ready(library, store).waiting == [("v1", "plan")]
    assert store.sub_items(sub)[0]["job"] == "", "not even prepared"


def test_a_paused_subscription_gets_nothing_ready(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    library, store, me = a_library(tmp_path, monkeypatch)
    sub = due(store, me, "v1")
    store.set_subscription_state(me, sub, "paused")
    assert subs.get_ready(library, store).started == []
    assert store.sub_items(sub)[0]["state"] == "listed"


def test_a_subscriptions_build_is_never_mailed_on_its_own(tmp_path: Path) -> None:
    """It is in the one mail a day with everything else new (design.md §12)."""
    from targum.mail import ConsoleMailer

    store = Store(tmp_path / "targum.db")
    me = reader(store)
    box: list[str] = []

    class Catch(ConsoleMailer):
        def notify(self, *args: Any, **kwargs: Any) -> None:
            box.append(str(args[0]))

    library = Library(tmp_path / "out", store=store, mailer=Catch(), address="https://t")
    job = Job(id="j", source="s", owner=me, reader="r", kind="subscription")
    job.options["mail"] = True
    library.tell(job)
    assert box == []
    library.tell(Job(id="k", source="s", owner=me, reader="r", options={"mail": True}))
    assert box == ["one@example.com"]


# --- the timer ------------------------------------------------------------------------


def _unit(name: str) -> dict[str, list[str]]:
    fields: dict[str, list[str]] = {}
    for line in (DEPLOY / name).read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.startswith(("#", "[")):
            key, value = line.split("=", 1)
            fields.setdefault(key.strip(), []).append(value.strip())
    return fields


def test_every_deploy_carries_and_enables_the_poll() -> None:
    assert _unit("targum-subscriptions.timer")["Persistent"] == ["true"]
    service = _unit("targum-subscriptions.service")
    assert "targum subscriptions poll" in service["ExecStart"][0]
    assert service["EnvironmentFile"] == ["/etc/targum/targum.env"], "the Data API key"
    assert service["User"] == ["targum"] and service["Type"] == ["oneshot"]
    script = (DEPLOY / "deploy.sh").read_text(encoding="utf-8")
    assert "deploy/targum-subscriptions.service deploy/targum-subscriptions.timer" in script
    assert "targum-weekly-watch.timer targum-subscriptions.timer" in script, "and enables it"
    assert "TARGUM_YOUTUBE_API_KEY=" in (DEPLOY / "box.env.op").read_text(encoding="utf-8")


def test_the_poll_runs_from_the_command_line(tmp_path: Path) -> None:
    from typer.testing import CliRunner

    from targum.cli import app

    store = tmp_path / "targum.db"
    Store(store)
    result = CliRunner().invoke(app, ["subscriptions", "poll", "--store", str(store)])
    assert result.exit_code == 0, result.output
    assert "0 looked at, 0 new" in result.output


def test_an_episode_is_held_to_the_length_its_feed_gave(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An episode's own address says nothing of its length, and was priced at the hour
    `_prepare_episode` guesses: sixty credits against a cap of sixty, for a seven-minute
    episode (the first real run, 2026-10-09)."""
    store = Store(tmp_path / "targum.db")
    me = reader(store)
    library = Library(tmp_path / "out", store=store)

    def prepare(job: Job) -> None:
        job.audio = True
        job.seconds = 3600.0
        job.parts = 5
        job.transcription = 0.3
        job.estimate = 0.9
        job.options["episode"] = True
        job.stage = "ready"

    monkeypatch.setattr(library, "prepare", prepare)
    sub = int(
        store.add_subscription(me, "podcast", "https://p/f", source="https://p/f", cap=60)["id"]
    )
    store.add_sub_items(
        sub,
        [
            {
                "key": "e1",
                "title": "#136",
                "link": "https://p/136.mp3",
                "seconds": 439,
                "state": "due",
            }
        ],
    )
    assert subs.get_ready(library, store).started == ["e1"]
    (item,) = store.sub_items(sub)
    assert item["credits"] == 7
    row = store.job(item["job"])
    assert row is not None and row["length"] == 439.0
