"""Web finds, the YouTube slice: a nightly round on the box that pools Hebrew videos with a
Hebrew track somebody wrote, scored on that track (targum-internal#620; design.md §12,
"YouTube finds are scored on the track somebody wrote", 2026-11-01).

The Data API's answers are fixtures in the shape `search.list` and `videos.list` return,
and yt-dlp is a fake: nothing here reaches a network. Every title and track is synthetic.
"""

from __future__ import annotations

import json
import shutil
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from targum.accounts import Store
from targum.cli import app
from targum.finds import button, chips, pool, provider, score
from targum.finds import youtube as finds_youtube
from targum.video import discover
from targum.video import youtube as video_youtube

FIXTURES = Path(__file__).parent / "fixtures" / "youtube_finds"
DEPLOY = Path(__file__).resolve().parent.parent / "deploy"
AT = int(datetime(2026, 11, 1, 1, tzinfo=UTC).timestamp() * 1000)
TRACK = (FIXTURES / "goodVideo01.he.vtt").read_text(encoding="utf-8")


@pytest.fixture(autouse=True)
def quiet(tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    """No laptop's map, proxy or budget reaches a test unless it sets one."""
    monkeypatch.setenv(score.ENV, str(tmp_path_factory.mktemp("forms") / "absent.json"))
    monkeypatch.delenv(video_youtube.YTDLP_PROXY_ENV, raising=False)
    monkeypatch.delenv(pool.BUDGET_ENV, raising=False)
    monkeypatch.delenv(finds_youtube.UNITS_ENV, raising=False)
    monkeypatch.delenv(finds_youtube.FLAG, raising=False)


@pytest.fixture
def store(tmp_path: Path) -> Store:
    return Store(tmp_path / "targum.db")


def forms() -> score.Forms:
    return score.Forms(
        language="he", forms={"בית": "בית", "ספר": "ספר"}, names=frozenset({"ישראל"})
    )


class Api:
    """The Data API as the round asks it: recorded answers, and every query written down."""

    def __init__(self, search: str = "search.json", videos: str = "videos.json") -> None:
        self.search = json.loads((FIXTURES / search).read_text(encoding="utf-8"))
        self.videos = json.loads((FIXTURES / videos).read_text(encoding="utf-8"))
        self.asked: list[tuple[str, dict[str, str]]] = []

    def __call__(self, address: str, query: Mapping[str, str]) -> dict[str, Any]:
        self.asked.append((address, dict(query)))
        if address == discover.SEARCH:
            return self.search
        wanted = set(query["id"].split(","))
        return {"items": [one for one in self.videos["items"] if one["id"] in wanted]}

    def searches(self) -> list[dict[str, str]]:
        return [query for address, query in self.asked if address == discover.SEARCH]


class Tracks:
    """yt-dlp's subtitle run, faked: a track per watch address, and every run counted."""

    def __init__(self, tracks: Mapping[str, finds_youtube.Track]) -> None:
        self.tracks = dict(tracks)
        self.asked: list[str] = []

    def __call__(self, url: str) -> finds_youtube.Track:
        self.asked.append(url)
        found = self.tracks.get(url.rsplit("=", 1)[-1])
        if found is None:
            raise RuntimeError("yt-dlp would not answer")
        return found


def night(store: Store, api: Api, tracks: Tracks, **more: Any) -> finds_youtube.Round:
    return finds_youtube.refresh(
        store,
        get=api,
        api_key="test-key",
        fetch=tracks,
        forms_for=lambda language: forms(),
        at=more.pop("at", AT),
        **more,
    )


GOOD = finds_youtube.Track(text=TRACK, size=2_000)


def test_a_video_with_a_written_hebrew_track_is_pooled_as_a_video_find(store: Store) -> None:
    api, tracks = Api(), Tracks({"goodVideo01": GOOD})
    found = night(store, api, tracks, budget_units=101)
    assert found.kept == 1 and found.asked == 1 and found.units == 101
    rows = pool.pick(store, "he", None, at=AT)
    assert len(rows) == 1
    find = rows[0]
    assert find.url == "https://www.youtube.com/watch?v=goodVideo01"
    assert find.medium == "video" and find.source == "youtube" and find.host == "www.youtube.com"
    assert find.seconds == 370 and find.minutes == 6
    assert find.credits == 6, "a credit a minute: what Watch will quote"
    assert find.publisher == "ערוץ לדוגמה" and find.title == "מתכון לשקשוקה בעשר דקות"
    assert find.topics == (chips.tag(chips.CHIPS[0].code),), "tagged with the chip that found it"
    assert find.bag == {"בית": 81, "ספר": 9}, "the counts, from the track"
    columns = {row[1] for row in store.db.execute("PRAGMA table_info(find)")}
    assert not columns & {"text", "subtitles", "transcript"}, "the track is never kept"

    # The search asked for what the plan says, and never for a licence.
    (query,) = api.searches()
    assert query["videoCaption"] == "closedCaption"
    assert query["safeSearch"] == "strict"
    assert query["relevanceLanguage"] == "he" and query["regionCode"] == "IL"
    assert query["publishedAfter"] == "2026-10-02T01:00:00Z"
    assert "videoLicense" not in query, "any licence: a find is the reader's own"
    assert query["q"] == chips.CHIPS[0].phrases["he"]

    # Its card: a video, opened by Watch through the pasted link's press.
    row = provider.row(provider.Scored(find, 0.95))
    assert row["kind"] == "video" and row["credits"] == 6 and row["origin"] == "find"
    ask = button.Ask(language="he", chosen=(chips.CHIPS[0].code,))
    assert button._chip_matched(ask, find.topics, {}, ()) == chips.CHIPS[0].code


def test_the_gate_drops_before_anything_crosses_the_proxy(store: Store) -> None:
    api, tracks = Api(), Tracks({"goodVideo01": GOOD, "goodVideo02": finds_youtube.Track()})
    found = night(store, api, tracks, budget_units=101)
    asked = {url.rsplit("=", 1)[-1] for url in tracks.asked}
    assert asked == {"goodVideo01", "goodVideo02"}, "only what passed the gate is fetched"
    assert found.dropped["age"] == 1, "an age-restricted video"
    assert found.dropped["subs"] == 2, "no track anybody wrote: YouTube's word, and yt-dlp's"
    assert found.dropped["gate"] == 2, "over thirty minutes; blocked in Israel"
    assert found.dropped["words"] == 1, "the description the screen refuses"


def test_an_age_restricted_video_never_reaches_the_pool(store: Store) -> None:
    api = Api()
    tracks = Tracks(
        {
            "goodVideo01": finds_youtube.Track(text=TRACK, age_limit=18),
            "goodVideo02": GOOD,
            "ageRestrict": GOOD,
        }
    )
    found = night(store, api, tracks, budget_units=101)
    urls = {find.url for find in pool.pick(store, "he", None, at=AT)}
    assert urls == {"https://www.youtube.com/watch?v=goodVideo02"}
    assert found.dropped["age"] == 2, "YouTube's rating, then yt-dlp's age limit"
    assert not any("ageRestrict" in url for url in tracks.asked)


def test_the_track_s_own_words_are_screened(store: Store) -> None:
    tracks = Tracks({"goodVideo01": finds_youtube.Track(text=TRACK + "\nתמונות עירום")})
    found = night(store, Api(), tracks, budget_units=101)
    assert found.kept == 0 and found.dropped["words"] == 2


def test_hard_news_stays() -> None:
    item = json.loads((FIXTURES / "videos.json").read_text(encoding="utf-8"))["items"][0]
    item["snippet"]["title"] = "פיגוע בירושלים: שלושה נהרגו, המלחמה בצפון"
    assert finds_youtube.gate(item, "he") == ""


def test_a_title_with_no_hebrew_letter_is_not_fetched() -> None:
    item = json.loads((FIXTURES / "videos.json").read_text(encoding="utf-8"))["items"][0]
    item["snippet"]["title"] = "Top 10 goals of the week"
    item["snippet"].pop("defaultAudioLanguage")
    assert finds_youtube.gate(item, "he") == "gate"


def test_a_day_fetches_at_most_its_tracks_however_often_it_runs(
    store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(finds_youtube, "NIGHT_MOST", 1)
    tracks = Tracks({"goodVideo01": GOOD, "goodVideo02": GOOD})
    first = night(store, Api(), tracks, budget_units=1000)
    assert len(tracks.asked) == 1 and first.stopped == "the day's 1 tracks"
    second = night(store, Api(), tracks, budget_units=101, at=AT + 60_000)
    assert len(tracks.asked) == 1 and second.fetched == 0, "the day's cap holds across runs"
    third = night(store, Api(), tracks, budget_units=101, at=AT + pool.DAY_MS)
    assert len(tracks.asked) == 2 and third.fetched == 1, "and a new day has its own"


def test_the_proxy_is_targum_s_spend_inside_the_discovery_budget(
    store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(video_youtube.YTDLP_PROXY_ENV, "http://user:pass@proxy.example:823")
    one = finds_youtube.run_cost(2_000)
    assert one == pytest.approx((finds_youtube.RUN_BYTES + 2_000) / 1e9)
    monkeypatch.setenv(pool.BUDGET_ENV, str(one * 1.5))
    tracks = Tracks({"goodVideo01": GOOD, "goodVideo02": GOOD})
    found = night(store, Api(), tracks, budget_units=101)
    assert len(tracks.asked) == 1 and found.stopped == "the month's discovery budget"
    assert pool.month_spent(store, AT) == pytest.approx(one)
    assert found.spent == pytest.approx(one)


def test_no_proxy_costs_nothing(store: Store) -> None:
    found = night(store, Api(), Tracks({"goodVideo01": GOOD}), budget_units=101)
    assert found.spent == 0 and pool.month_spent(store, AT) == 0


def test_a_night_keeps_to_its_units_and_the_next_starts_where_it_stopped(store: Store) -> None:
    api = Api()
    first = night(store, api, Tracks({}), budget_units=250)
    assert first.asked == 2 and first.units <= 250
    assert first.stopped == "the night's 250 units"
    second_api = Api()
    night(store, second_api, Tracks({}), budget_units=101, at=AT + pool.DAY_MS)
    assert second_api.searches()[0]["q"] == chips.CHIPS[2].phrases["he"]
    everything = finds_youtube.queries("he")
    assert len(everything) == len(chips.CHIPS) + len(finds_youtube.EASY["he"])


def test_a_video_already_pooled_is_not_asked_about_again(store: Store) -> None:
    night(store, Api(), Tracks({"goodVideo01": GOOD}), budget_units=101)
    api, tracks = Api(), Tracks({"goodVideo01": GOOD})
    again = night(store, api, tracks, budget_units=101, at=AT + pool.DAY_MS)
    assert tracks.asked == [] and again.seen == 0
    assert [address for address, _ in api.asked] == [discover.SEARCH]


def test_a_killed_round_has_kept_what_it_found(store: Store) -> None:
    class Killed(Tracks):
        def __call__(self, url: str) -> finds_youtube.Track:
            if self.asked:
                raise KeyboardInterrupt
            return super().__call__(url)

    with pytest.raises(KeyboardInterrupt):
        night(store, Api(), Killed({"goodVideo01": GOOD, "goodVideo02": GOOD}), budget_units=101)
    assert len(pool.pick(store, "he", None, at=AT)) == 1
    (fetched,) = store.db.execute("SELECT note FROM find_run WHERE source = 'youtube'").fetchone()
    assert json.loads(fetched)["fetched"] == 1


def test_a_track_is_read_and_its_folder_deleted(monkeypatch: pytest.MonkeyPatch) -> None:
    folders: list[Path] = []

    def ran(url: str, into: Path) -> tuple[Path | None, dict[str, Any]]:
        folders.append(into)
        written = into / "goodVideo01.he.vtt"
        shutil.copy(FIXTURES / "goodVideo01.he.vtt", written)
        return written, {"age_limit": 0, "id": "goodVideo01"}

    monkeypatch.setattr(video_youtube, "subtitles_for_finding", ran)
    got = finds_youtube.track("https://www.youtube.com/watch?v=goodVideo01")
    assert got.text.split()[:2] == ["בית", "בית"] and got.size > 0 and got.age_limit == 0
    assert folders and not folders[0].exists(), "nothing of the track is left on disk"


def test_the_subtitle_run_fetches_no_media_and_no_guessed_track(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ran: list[list[str]] = []

    def run(argv: list[str], *, timeout: int) -> Any:
        ran.append(argv)
        (tmp_path / "x.info.json").write_text('{"age_limit": 18}', encoding="utf-8")
        return None

    monkeypatch.setattr(video_youtube, "_run", run)
    track, info = video_youtube.subtitles_for_finding(
        "https://www.youtube.com/watch?v=goodVideo01", tmp_path
    )
    (argv,) = ran
    assert "--skip-download" in argv and "--write-subs" in argv
    assert "--write-auto-subs" not in argv, "a track somebody wrote, never YouTube's guess"
    assert argv[argv.index("--sub-langs") + 1] == "he.*,iw.*"
    assert track is None and info["age_limit"] == 18


def test_it_is_off_unless_the_box_says_so(monkeypatch: pytest.MonkeyPatch) -> None:
    assert not finds_youtube.on()
    said = CliRunner().invoke(app, ["finds", "youtube"])
    assert said.exit_code == 0 and "off" in said.output
    monkeypatch.setenv(finds_youtube.FLAG, "1")
    assert finds_youtube.on()


def test_the_timer_runs_nightly_as_targum_and_every_deploy_carries_it() -> None:
    def unit(name: str) -> dict[str, list[str]]:
        fields: dict[str, list[str]] = {}
        for line in (DEPLOY / name).read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.startswith(("#", "[")):
                key, value = line.split("=", 1)
                fields.setdefault(key.strip(), []).append(value.strip())
        return fields

    service = unit("targum-finds-youtube.service")
    assert service["User"] == ["targum"], "never as root"
    assert service["ExecStart"] == [
        "/usr/local/bin/targum finds youtube --store /var/lib/targum/targum.db"
    ]
    assert service["EnvironmentFile"] == ["/etc/targum/targum.env"]
    timer = unit("targum-finds-youtube.timer")
    assert timer["OnCalendar"] == ["*-*-* 01:00:00 UTC"]
    script = (DEPLOY / "deploy.sh").read_text(encoding="utf-8")
    assert "deploy/targum-finds-youtube.service deploy/targum-finds-youtube.timer" in script
    assert "targum-finds-youtube.service targum-finds-youtube.timer; do" in script
    enable = next(line for line in script.splitlines() if "systemctl enable --now" in line)
    assert "targum-finds-youtube.timer" in enable
