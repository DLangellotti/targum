"""The shelf grows by itself (design.md §12, draft 2026-11-17): a catalogue collection
whose channel grows has its new Creative Commons uploads built on the box, through
`Library.press` and so `Library.claim`, inside a month's credits, and joined to the
shelf without a deploy. Off unless the box names a language and a cap.

Nothing here reaches the network: the Data API, the track fetch, the build and the
curation are each handed in or replaced, and the press, the claim and the worker are the
Library's own.
"""

from __future__ import annotations

import json
import re
import shutil
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from targum import catalogue, grow, stages
from targum.accounts import Store
from targum.errors import TargumError
from targum.serve import Job, Library
from targum.video import channels, discover

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "catalogue.json"
CHANNEL = "https://www.youtube.com/channel/UCgrowsgrowsgrowsgrows00"


@pytest.fixture
def shelf(tmp_path: Path, monkeypatch: Any) -> Iterator[Path]:
    """The fixture catalogue plus one French video collection whose channel grows, and a
    video shelf of its own."""
    copy = tmp_path / "catalogue.json"
    held = json.loads(FIXTURE.read_text(encoding="utf-8"))
    held["entries"].append(
        {
            "id": "video-fr-old",
            "title": "Une vieille vidéo",
            "language": "fr",
            "source": "video:old",
            "kind": "talk",
            "register": "modern",
            "words": 300,
        }
    )
    held["collections"].append(
        {
            "id": "a-channel-fr",
            "title": "A channel",
            "english": "A channel",
            "members": ["video-fr-old"],
            "channel": CHANNEL,
            "grows": True,
        }
    )
    copy.write_text(json.dumps(held, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setenv("TARGUM_CATALOGUE", str(copy))
    monkeypatch.setenv("TARGUM_VIDEO_DIR", str(tmp_path / "videos"))
    before = list(catalogue.CATALOGUE)
    collections = list(catalogue.COLLECTIONS)
    catalogue.reload()
    yield copy
    catalogue.CATALOGUE[:] = before
    catalogue.COLLECTIONS[:] = collections


def upload(
    identifier: str,
    *,
    licence: str = "creativeCommon",
    caption: str = "true",
    duration: str = "PT4M",
    title: str = "Une journée au marché",
) -> dict[str, Any]:
    return {
        "id": identifier,
        "status": {
            "license": licence,
            "privacyStatus": "public",
            "embeddable": True,
            "uploadStatus": "processed",
        },
        "contentDetails": {"duration": duration, "caption": caption},
        "snippet": {
            "title": title,
            "channelTitle": "Une chaîne",
            "publishedAt": "2026-11-16T10:00:00Z",
            "liveBroadcastContent": "none",
            "categoryId": "22",
            "defaultAudioLanguage": "fr",
            "description": "",
        },
    }


def api(items: list[dict[str, Any]], asked: list[str] | None = None) -> grow.Fetch:
    def get(address: str, query: Any) -> dict[str, Any]:
        if asked is not None:
            asked.append(address)
        if address == channels.CHANNELS:
            return {
                "items": [
                    {
                        "id": "UCgrowsgrowsgrowsgrows00",
                        "snippet": {"title": "Une chaîne"},
                        "contentDetails": {"relatedPlaylists": {"uploads": "UUgrows"}},
                    }
                ]
            }
        if address == channels.PLAYLIST_ITEMS:
            return {"items": [{"contentDetails": {"videoId": item["id"]}} for item in items]}
        if address == discover.VIDEOS:
            wanted = set(query["id"].split(","))
            return {"items": [item for item in items if item["id"] in wanted]}
        raise AssertionError(address)

    return get


def track(address: str, into: Path, languages: tuple[str, ...]) -> Path:
    into.mkdir(parents=True, exist_ok=True)
    written = into / "x.fr.vtt"
    written.write_text("WEBVTT\n", encoding="utf-8")
    return written


@pytest.fixture
def world(tmp_path: Path, monkeypatch: Any, shelf: Path) -> tuple[Library, Store, list[Job]]:
    """A real Library and store, whose prepare and run are the only things stood in for:
    the press, the claim and the worker are its own."""
    store = Store(tmp_path / "targum.db")
    out = tmp_path / "out"
    out.mkdir()
    library = Library(out, store=store, budget=50.0)
    built: list[Job] = []

    def prepare(job: Job) -> None:
        job.audio = True
        job.seconds = 240.0
        job.estimate = 0.2
        job.stage = "ready"

    def run(job: Job) -> None:
        assert job.home is not None
        folder = job.home / f"build-{len(built)}"
        folder.mkdir(parents=True)
        (folder / "document.json").write_text(
            json.dumps({"title": "Une journée", "blocks": []}), encoding="utf-8"
        )
        job.reader = f"{folder.name}/reader/index.html"
        job.spent = 0.12
        job.stage = "done"
        library.settle(job)
        library.remember(job)
        built.append(job)

    def curate(folder: Path, *, credit: str, licence: str, licence_url: str) -> Path:
        assert credit == "Une chaîne"
        assert licence == "CC BY 3.0"
        identifier = built[-1].source.rsplit("=", 1)[-1]
        into = tmp_path / "videos" / identifier
        into.mkdir(parents=True)
        shutil.copy(folder / "document.json", into / "document.json")
        return into

    monkeypatch.setattr(library, "prepare", prepare)
    monkeypatch.setattr(library, "run", run)
    monkeypatch.setattr("targum.video.curate.curate", curate)
    monkeypatch.setenv(grow.FLAG, "fr")
    monkeypatch.setenv(grow.CREDITS_ENV, "120")
    return library, store, built


def test_off_unless_a_language_and_a_cap_are_named(world: Any, monkeypatch: Any) -> None:
    library, store, built = world
    asked: list[str] = []
    monkeypatch.delenv(grow.FLAG)
    report = grow.grow(library, store, get=api([upload("a")], asked), track=track, api_key="k")
    assert report.stopped.startswith("off") and not asked and not built
    monkeypatch.setenv(grow.FLAG, "fr")
    monkeypatch.setenv(grow.CREDITS_ENV, "0")
    report = grow.grow(library, store, get=api([upload("a")], asked), track=track, api_key="k")
    assert report.stopped.startswith("off") and not asked and not built


def test_a_source_is_a_collection_whose_channel_grows(shelf: Path) -> None:
    found = grow.sources()
    assert [(one.collection, one.language, one.channel) for one in found] == [
        ("a-channel-fr", "fr", CHANNEL)
    ]


def test_a_round_builds_through_the_press_and_joins_the_shelf(world: Any) -> None:
    library, store, built = world
    report = grow.grow(library, store, get=api([upload("vid1")]), track=track, api_key="k")
    assert report.built == ["vid1"], report
    (job,) = built
    assert (job.kind, job.gift, job.owner, job.options["from"]) == ("grow", True, None, "fr")
    assert job.options["transcript"].endswith(".vtt")
    # Claimed through the store, as every build is, and settled to what it spent.
    row = store.db.execute("SELECT claimed, stage FROM job WHERE id = ?", (job.id,)).fetchone()
    assert row["stage"] == "done" and row["claimed"] == pytest.approx(0.12)
    entry = catalogue.matching("video:vid1")
    assert entry is not None and entry.language == "fr" and entry.licence == "CC BY 3.0"
    assert entry.credit == "Une chaîne"
    (collection,) = [one for one in catalogue.collections() if one.id == "a-channel-fr"]
    assert collection.members == ("video-fr-old", "video-fr-vid1")
    # The build folder goes; the curated copy is what the shelf reads.
    assert not any((library.out / grow.WORKSPACE).glob("build-*"))
    # And a second round builds nothing again.
    again = grow.grow(library, store, get=api([upload("vid1")]), track=track, api_key="k")
    assert again.built == [] and len(built) == 1


def test_only_creative_commons_with_a_written_track_and_one_part(world: Any) -> None:
    library, store, built = world
    items = [
        upload("closed", licence="youtube"),
        upload("unwritten", caption="false"),
        upload("long", duration="PT13M"),
        upload("sung", title="ok"),
    ]
    items[3]["snippet"]["categoryId"] = discover.MUSIC
    report = grow.grow(library, store, get=api(items), track=track, api_key="k")
    assert not built
    assert dict(report.passed) == {
        "closed": "not Creative Commons",
        "unwritten": "no track anybody wrote",
        "long": "longer than ten minutes",
        "sung": "music",
    }
    held = json.loads(grow.index_path().read_text(encoding="utf-8"))
    assert set(held["passed"]) == {"closed", "unwritten", "long", "sung"}


def test_no_track_is_passed_over_and_a_way_out_down_is_asked_again(world: Any) -> None:
    library, store, built = world

    def none(address: str, into: Path, languages: tuple[str, ...]) -> Path:
        raise TargumError("That video has no subtitle track anybody wrote in fr.")

    report = grow.grow(library, store, get=api([upload("bare")]), track=none, api_key="k")
    assert report.passed == [("bare", "no track anybody wrote")] and not built

    def down(address: str, into: Path, languages: tuple[str, ...]) -> Path:
        raise TargumError("YouTube is out of reach.")

    report = grow.grow(library, store, get=api([upload("later")]), track=down, api_key="k")
    assert [one for one, _ in report.failed] == ["later"]
    assert "later" not in json.loads(grow.index_path().read_text(encoding="utf-8"))["passed"]


def test_the_month_is_held_to_its_cap_off_the_job_rows(world: Any, monkeypatch: Any) -> None:
    library, store, built = world
    monkeypatch.setenv(grow.CREDITS_ENV, "6")
    items = [upload("one"), upload("two")]
    report = grow.grow(library, store, get=api(items), track=track, api_key="k")
    # Four minutes is four credits: the first fits six, the second would not.
    assert report.built == ["one"] and report.stopped.startswith("the month's 6 credits")
    assert grow.credits_this_month(store, int(library._month_from())) == 4


def test_at_most_a_round_a_day(world: Any) -> None:
    library, store, built = world
    items = [upload(f"v{n}") for n in range(5)]
    report = grow.grow(library, store, get=api(items), track=track, api_key="k")
    assert len(report.built) == grow.ROUND == 3


def test_drop_takes_one_down_and_keeps_it_down(world: Any) -> None:
    library, store, built = world
    grow.grow(library, store, get=api([upload("vid1")]), track=track, api_key="k")
    assert grow.drop("vid1")
    assert catalogue.matching("video:vid1") is None
    assert json.loads(grow.index_path().read_text(encoding="utf-8"))["passed"]["vid1"]
    assert not grow.drop("vid1")


def test_french_is_declared_to_grow_and_build_unattended() -> None:
    assert "fr" in stages.GROWING and "fr" in stages.BUILDS_UNATTENDED
    known = stages.facts("fr")
    short = stages.shortfall(known, stages.Stage.beta)
    assert "nothing grows the shelf by itself" not in short
    assert "the box cannot build a new text unattended" not in short


UNIT = ROOT / "deploy" / "targum-grow.service"
TIMER = ROOT / "deploy" / "targum-grow.timer"


def test_the_unit_runs_as_targum_with_the_box_ceiling() -> None:
    unit = UNIT.read_text(encoding="utf-8")
    assert re.search(r"^User=targum$", unit, re.M)
    assert "/usr/local/bin/targum grow run " in unit
    served = (ROOT / "deploy" / "targum.service").read_text(encoding="utf-8")
    ceiling = re.search(r"--budget (\d+)", served)
    assert ceiling and f"--budget {ceiling.group(1)}" in unit
    assert re.search(r"^OnCalendar=", TIMER.read_text(encoding="utf-8"), re.M)


def test_deploy_does_not_arm_it() -> None:
    """Armed by hand, once (deploy/README.md): it spends targum's money unattended."""
    script = (ROOT / "deploy" / "deploy.sh").read_text(encoding="utf-8")
    assert "targum-grow" not in script


def test_a_round_leaves_another_process_running_rows_untouched(world: Any, tmp_path: Path) -> None:
    """A round runs beside a live server on its database. Its Library is a side one: no
    start-up recovery, so the server's builds in hand stay as they are."""
    library, store, built = world
    for stage in ("working", "queued"):
        store.save_job(
            {
                "id": f"server-{stage}",
                "owner": None,
                "home": str(tmp_path),
                "source": "x",
                "options": "{}",
                "stage": stage,
                "kind": "build",
                "made": int(time.time() * 1000),
            }
        )
    side = Library(tmp_path / "out", store=store, budget=50.0, side=True)
    assert side.side
    grow.grow(side, store, get=api([]), track=track, api_key="k")
    stages_now = {
        row["id"]: row["stage"]
        for row in store.db.execute("SELECT id, stage FROM job WHERE id LIKE 'server-%'")
    }
    assert stages_now == {"server-working": "working", "server-queued": "queued"}


def test_a_failed_build_counts_toward_the_month_and_the_round(world: Any, monkeypatch: Any) -> None:
    """A build that failed kept its claim: it spent, so it counts toward the month, and a
    press counts toward the round's three whether or not its build came through."""
    library, store, built = world

    def fails(job: Job) -> None:
        job.stage = "failed"
        job.error = "boom"
        library.remember(job)
        built.append(job)

    monkeypatch.setattr(library, "run", fails)
    items = [upload(f"f{n}") for n in range(5)]
    report = grow.grow(library, store, get=api(items), track=track, api_key="k")
    assert len(built) == grow.ROUND and report.built == []
    assert grow.credits_this_month(store, int(library._month_from())) == 12


def test_a_round_left_working_by_a_dead_process_is_settled_and_counted(world: Any) -> None:
    library, store, built = world
    store.save_job(
        {
            "id": "dead",
            "owner": None,
            "home": "/x",
            "source": "y",
            "options": "{}",
            "stage": "working",
            "kind": grow.KIND,
            "seconds": 300.0,
            "made": int(time.time() * 1000),
        }
    )
    with store.write() as db:
        db.execute("UPDATE job SET claimed = 0.2 WHERE id = 'dead'")
    grow.grow(library, store, get=api([]), track=track, api_key="k")
    row = store.db.execute("SELECT stage FROM job WHERE id = 'dead'").fetchone()
    assert row["stage"] == "failed"
    assert grow.credits_this_month(store, int(library._month_from())) == 5


def test_two_rounds_at_once_do_not_both_run(world: Any) -> None:
    library, store, built = world
    with grow._locked(grow.index_path().with_name(grow.ROUND_LOCK)):
        report = grow.grow(library, store, get=api([upload("a")]), track=track, api_key="k")
    assert report.stopped == "another round is running" and not built


def test_a_drop_during_a_round_is_not_written_back(world: Any, monkeypatch: Any) -> None:
    """The round re-reads the index before each write, so a video taken down while it ran
    stays down."""
    library, store, built = world
    grow.grow(library, store, get=api([upload("vid1")]), track=track, api_key="k")
    real = grow._gate

    def gate(item: Any, language: str) -> str:
        if item["id"] == "vid2":
            assert grow.drop("vid1")
        return real(item, language)

    monkeypatch.setattr(grow, "_gate", gate)
    grow.grow(library, store, get=api([upload("vid2"), upload("vid1")]), track=track, api_key="k")
    assert catalogue.matching("video:vid1") is None
    assert catalogue.matching("video:vid2") is not None


def test_the_real_prepare_prices_the_written_track_and_measures_the_seconds(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """Through `Library.prepare` itself, for a YouTube video whose only track is French:
    the round's own track in hand means the quote buys no hearing, the seconds the cap
    reads are set, and the build reads that track rather than fetching or hearing one."""
    from targum.video import youtube as youtube_module

    monkeypatch.setattr(
        youtube_module,
        "describe",
        lambda url: {
            "webpage_url": url,
            "title": "Une journée",
            "duration": 250.0,
            "formats": [{"acodec": "opus", "language": "fr"}],
            "subtitles": {"fr": [{"ext": "vtt"}]},
        },
    )
    monkeypatch.setattr(
        youtube_module, "fetch", lambda *a, **k: pytest.fail("a price must not download")
    )
    monkeypatch.setattr(youtube_module, "ensure_reachable", lambda *a, **k: None)
    monkeypatch.setattr("targum.video.ytdlp_available", lambda: (True, "yt-dlp"))
    written = track("", tmp_path / "tracks", ("fr",))
    library = Library(tmp_path / "out", side=True)
    options = {"to": "en", "words": True, "from": "fr", "transcript": str(written)}
    job = Job(id="g", source="https://www.youtube.com/watch?v=vid9", options=options)
    library.prepare(job)
    assert job.error == "" and job.stage in ("ready", "blocked")
    assert job.audio and job.seconds == 250.0
    assert job.transcription == 0.0 and job.options["subtitles"] is True
    # Without the round's track, a French video is quoted a hearing: the track is what
    # makes it free, not the video.
    bare = Job(id="h", source="https://www.youtube.com/watch?v=vid9", options={"from": "fr"})
    library.prepare(bare)
    assert bare.transcription > 0.0
    assert library._builder(job).transcript == written
