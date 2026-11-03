"""Web finds, the podcast slice: a nightly round on the box that pools new episodes of a
reviewed list of Hebrew shows, scored on their transcript or on two minutes from the
middle (targum-internal#621; design.md §12, "Podcast finds are scored on a transcript or
two minutes", 2026-11-02).

The feed and the transcript are fixtures, whisper is a fake and robots.txt is answered
by the test: nothing here reaches a network. Every show, title and word is synthetic.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from targum import accounts
from targum.accounts import Store
from targum.chat import sources
from targum.cli import app
from targum.finds import chips, podcasts, pool, provider, score
from targum.finds.robots import Robots
from targum.tables import finds as table_finds
from targum.tables.registers import PODCASTS
from targum.weekly import feeds

FIXTURES = Path(__file__).parent / "fixtures" / "podcast_finds"
DEPLOY = Path(__file__).resolve().parent.parent / "deploy"
AT = int(datetime(2026, 11, 2, 2, tzinfo=UTC).timestamp() * 1000)
FEED = "https://feeds.example/show.rss"
FEED_BODY = (FIXTURES / "feed.xml").read_bytes()
SRT = (FIXTURES / "ep-transcript.srt").read_text(encoding="utf-8")
TRANSCRIPT = "https://audio.example/show/ep-transcript/transcript.srt"
SAMPLED = "https://audio.example/show/ep-sample.mp3"
SHOW = podcasts.Show(
    key="example",
    name="תוכנית לדוגמה",
    publisher="מגיש לדוגמה",
    feed=FEED,
    site="show.example",
    tags=(chips.tag("science"), chips.tag("history")),
    licence="All rights reserved; a free public feed.",
)
SAMPLE = podcasts.Heard(text="בית " * 85 + "ספר " * 5, seconds=120.0, cost=0.012)


@pytest.fixture(autouse=True)
def quiet(tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    """No laptop's map, budget, sources list or switch reaches a test unless it sets one."""
    monkeypatch.setenv(score.ENV, str(tmp_path_factory.mktemp("forms") / "absent.json"))
    monkeypatch.setenv("TARGUM_SOURCES", str(tmp_path_factory.mktemp("src") / "none.json"))
    monkeypatch.delenv(pool.BUDGET_ENV, raising=False)
    monkeypatch.delenv(podcasts.FLAG, raising=False)


@pytest.fixture
def store(tmp_path: Path) -> Store:
    return Store(tmp_path / "targum.db")


def forms() -> score.Forms:
    return score.Forms(
        language="he", forms={"בית": "בית", "ספר": "ספר"}, names=frozenset({"ישראל"})
    )


def allowing(*refused: str) -> Robots:
    """robots.txt as the test says: every host allows everything but the ones named."""

    def read(url: str) -> str | None:
        host = url.split("/")[2]
        return "User-agent: *\nDisallow: /\n" if host in refused else ""

    return Robots(read=read)


class Ears:
    """whisper, faked: two minutes heard per episode asked for, and every one counted."""

    def __init__(self, heard: podcasts.Heard = SAMPLE) -> None:
        self.heard = heard
        self.asked: list[str] = []

    def __call__(self, episode: podcasts.Episode) -> podcasts.Heard:
        self.asked.append(episode.audio)
        return self.heard


def night(store: Store, ears: Ears | None = None, **more: Any) -> podcasts.Round:
    read_asked: list[str] = more.pop("read_asked", [])

    def read(url: str) -> str:
        read_asked.append(url)
        return SRT

    return podcasts.refresh(
        store,
        listed=more.pop("listed", [SHOW]),
        pull=more.pop("pull", lambda url: FEED_BODY),
        read=more.pop("read", read),
        hear=ears or Ears(),
        ready=more.pop("ready", lambda: ""),
        robots=more.pop("robots", allowing()),
        forms_for=lambda language: forms(),
        at=more.pop("at", AT),
        **more,
    )


def by_url(store: Store) -> dict[str, pool.Find]:
    return {find.url: find for find in pool.pick(store, "he", None, at=AT)}


def test_an_episode_with_a_transcript_is_scored_on_it_for_nothing(store: Store) -> None:
    ears, asked = Ears(), []
    found = night(store, ears, read_asked=asked)
    assert asked == [TRANSCRIPT], "the SRT, not the HTML listed before it"
    find = by_url(store)["https://audio.example/show/ep-transcript.mp3"]
    assert find.medium == "podcast" and find.source == "podcast"
    assert find.host == "show.example" and find.publisher == "תוכנית לדוגמה"
    assert find.title == "פרק עם תמליל"
    assert find.seconds == 1800 and find.minutes == 30
    assert find.credits == 30, "a credit a minute: what Listen will quote"
    assert find.topics == (chips.tag("science"), chips.tag("history")), "the show's chips"
    assert find.bag == {"בית": 80, "ספר": 10}, "the counts, from the transcript"
    assert find.rate == 90.0, "ninety words in the minute the cues cover"
    assert found.transcripts == 1 and found.spent >= 0
    assert ears.asked == [SAMPLED], "the episode with no transcript is the one sampled"

    # Its card: a podcast, opened by Listen through the pasted link's press.
    row = provider.row(provider.Scored(find, 0.95))
    assert row["kind"] == "podcast" and row["credits"] == 30 and row["origin"] == "find"


def test_a_sampled_episode_keeps_counts_and_speech_rate_and_no_words(store: Store) -> None:
    """Acceptance 1 (#621): the pool row holds counts and speech rate, no transcript."""
    found = night(store)
    find = by_url(store)[SAMPLED]
    assert find.bag == {"בית": 85, "ספר": 5}
    assert find.rate == 45.0, "ninety words in two minutes"
    assert find.seconds == 2400 and find.credits == 40
    assert found.sampled == 1 and found.spent == pytest.approx(0.012)
    assert pool.month_spent(store, AT) == pytest.approx(0.012), "targum's spend, on the run"
    columns = {row[1] for row in store.db.execute("PRAGMA table_info(find)")}
    assert "rate" in columns
    assert not columns & {"text", "transcript", "subtitles", "audio"}, "no words are kept"
    held = " ".join(str(value) for row in store.db.execute("SELECT * FROM find") for value in row)
    assert "בית בית" not in held


def test_the_sample_cap_stops_the_run_and_says_so(
    store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Acceptance 2 (#621): the cap stops the sampling and the round reports it."""
    monkeypatch.setattr(podcasts, "PER_FEED", 10)
    monkeypatch.setattr(podcasts, "DAY_SAMPLES", 0)
    ears = Ears()
    found = night(store, ears)
    assert ears.asked == [] and found.sampled == 0
    assert found.stopped == "the day's 0 samples"
    assert found.left == [SAMPLED], "left for another night, neither pooled nor dropped"
    assert not pool.known(store, SAMPLED), "never measured, never offered"
    (note,) = store.db.execute("SELECT note FROM find_run WHERE source = 'podcast'").fetchone()
    said = json.loads(note)
    assert said["stopped"] == "the day's 0 samples" and said["left"] == 1
    # The transcript, which costs nothing, is still read and pooled.
    assert found.transcripts == 1 and found.kept == 1


def test_a_day_samples_at_most_its_cap_however_often_it_runs(
    store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(podcasts, "DAY_SAMPLES", 1)
    second_show = podcasts.Show(**{**SHOW.__dict__, "key": "other", "feed": FEED + "?2"})
    other = FEED_BODY.replace(b"https://audio.example/show/", b"https://audio.example/other/")
    bodies = {FEED: FEED_BODY, FEED + "?2": other}
    ears = Ears()
    first = night(store, ears, listed=[SHOW, second_show], pull=bodies.__getitem__)
    assert len(ears.asked) == 1 and first.stopped == "the day's 1 samples"
    again = night(store, ears, listed=[SHOW, second_show], pull=bodies.__getitem__, at=AT + 60_000)
    assert len(ears.asked) == 1 and again.sampled == 0, "the day's cap holds across runs"
    later = night(
        store, ears, listed=[SHOW, second_show], pull=bodies.__getitem__, at=AT + pool.DAY_MS
    )
    assert len(ears.asked) == 2 and later.sampled == 1, "and a new day has its own"


def test_the_month_s_cap_holds_too(store: Store, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(podcasts, "MONTH_SAMPLES", 0)
    found = night(store)
    assert found.sampled == 0 and found.stopped == "the month's 0 samples"


def test_samples_stay_inside_the_discovery_budget(
    store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert podcasts.sample_cost() == pytest.approx(0.012), "two minutes at whisper's $0.006"
    monkeypatch.setenv(pool.BUDGET_ENV, "0.005")
    ears = Ears()
    found = night(store, ears)
    assert ears.asked == [] and found.stopped == "the month's discovery budget"


def test_no_transcriber_samples_nothing(store: Store) -> None:
    ears = Ears()
    found = night(store, ears, ready=lambda: "no transcriber (set OPENAI_API_KEY)")
    assert ears.asked == [] and found.stopped.startswith("no transcriber")
    assert found.kept == 1, "the transcript's episode is still pooled"


def test_the_gate_drops_before_anything_is_fetched(
    store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(podcasts, "PER_FEED", 10)
    ears = Ears()
    found = night(store, ears)
    assert found.dropped["age"] == 1, "the episode its feed marks explicit"
    assert found.dropped["gate"] == 2, "a one-minute trailer; an episode of no stated length"
    assert found.dropped["words"] == 1, "the title the screen refuses"
    assert ears.asked == [SAMPLED]
    assert not pool.known(store, "https://audio.example/show/ep-old.mp3"), "past thirty days"
    assert found.seen == 6


def test_robots_keep_a_feed_and_an_audio_host_unread(store: Store) -> None:
    ears = Ears()
    pulled: list[str] = []

    def pull(url: str) -> bytes:
        pulled.append(url)
        return FEED_BODY

    found = night(store, ears, pull=pull, robots=allowing("feeds.example"))
    assert pulled == [] and found.kept == 0
    found = night(store, ears, robots=allowing("audio.example"), at=AT + 1)
    assert ears.asked == [] and found.dropped["robots"] == 2 and found.kept == 0


def test_an_episode_once_pooled_is_not_heard_again(store: Store) -> None:
    night(store)
    ears = Ears()
    asked: list[str] = []
    again = night(store, ears, at=AT + pool.DAY_MS, read_asked=asked)
    assert ears.asked == [] and asked == [] and again.kept == 0
    assert again.seen == 4, "the next new episodes are looked at, and gated"


def test_a_killed_round_has_kept_what_it_found(store: Store) -> None:
    class Killed(Ears):
        def __call__(self, episode: podcasts.Episode) -> podcasts.Heard:
            raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        night(store, Killed())
    assert set(by_url(store)) == {"https://audio.example/show/ep-transcript.mp3"}
    (note,) = store.db.execute("SELECT note FROM find_run WHERE source = 'podcast'").fetchone()
    assert json.loads(note)["transcripts"] == 1


def test_an_unreadable_sample_is_dropped_says_why_and_eats_no_cap(store: Store) -> None:
    class Deaf(Ears):
        def __call__(self, episode: podcasts.Episode) -> podcasts.Heard:
            raise podcasts.Unheard("cut", "ffmpeg: Invalid data found when processing input")

    found = night(store, Deaf())
    assert found.dropped["unreadable"] == 1
    assert found.sampled == 0, "nothing was transcribed, so the day's cap is untouched"
    assert "cut: ffmpeg: Invalid data" in str(found)
    (note,) = store.db.execute("SELECT note FROM find_run WHERE source = 'podcast'").fetchone()
    assert json.loads(note)["unheard"] == {
        "cut: ffmpeg: Invalid data found when processing input": 1
    }


#: What OpenAI answered every sample on the box's first run (2026-11-02).
NO_CREDITS = (
    'OpenAI 429: {\n    "error": {\n        "message": "You have no credits remaining.",\n'
    '        "type": "insufficient_quota",\n        "param": null,\n'
    '        "code": "credit_balance_exhausted"\n    }\n}\n'
)


def test_a_transcriber_refusal_stops_the_sampling_and_drops_nothing(
    store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    """targum-internal#621, the first run on the box: whisper refused all ten samples
    (no credits), and ten good episodes were dropped and counted against the cap."""
    from targum.errors import ProviderError

    monkeypatch.setattr(podcasts, "PER_FEED", 10)
    second = podcasts.Show(**{**SHOW.__dict__, "key": "other", "feed": FEED + "?2"})
    other = FEED_BODY.replace(b"https://audio.example/show/", b"https://audio.example/other/")
    bodies = {FEED: FEED_BODY, FEED + "?2": other}

    class Refused(Ears):
        def __call__(self, episode: podcasts.Episode) -> podcasts.Heard:
            self.asked.append(episode.audio)
            error = ProviderError("The recording could not be transcribed.", NO_CREDITS)
            raise podcasts.Unheard("transcriber", podcasts._why(error)) from error

    ears = Refused()
    found = night(store, ears, listed=[SHOW, second], pull=bodies.__getitem__)
    assert len(ears.asked) == 1, "one refusal stops the night's sampling"
    assert found.stopped == "the transcriber refused (OpenAI 429 credit_balance_exhausted)"
    assert found.sampled == 0 and found.spent == 0 and found.dropped["unreadable"] == 0
    assert SAMPLED in found.left and not pool.known(store, SAMPLED), "it waits for a night"
    again = night(store, Ears(), listed=[SHOW, second], pull=bodies.__getitem__, at=AT + 1)
    assert again.sampled == 2, "the next run hears them, the cap untouched"


def test_samples_failing_in_a_row_stop_the_sampling(
    store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(podcasts, "UNHEARD_MOST", 1)
    second = podcasts.Show(**{**SHOW.__dict__, "key": "other", "feed": FEED + "?2"})
    other = FEED_BODY.replace(b"https://audio.example/show/", b"https://audio.example/other/")
    bodies = {FEED: FEED_BODY, FEED + "?2": other}

    class Deaf(Ears):
        def __call__(self, episode: podcasts.Episode) -> podcasts.Heard:
            self.asked.append(episode.audio)
            raise podcasts.Unheard("fetch", "HTTP 403")

    ears = Deaf()
    found = night(store, ears, listed=[SHOW, second], pull=bodies.__getitem__)
    assert len(ears.asked) == 1 and found.stopped == "1 samples not heard in a row"


def test_why_a_sample_was_not_heard_names_the_step(monkeypatch: pytest.MonkeyPatch) -> None:
    import subprocess

    from targum.audio import tools
    from targum.errors import ProviderError, TargumError
    from targum.ingest import url as door
    from targum.transcribe import openai_whisper

    episode = podcasts.Episode(
        show=SHOW, audio=SAMPLED, title="", published=0, seconds=2400, length=38_400_000
    )

    def refused(url: str, into: Path, start: int, most: int) -> Any:
        raise TargumError("We couldn't open it.", "HTTP 403")

    monkeypatch.setattr(door, "window", refused)
    with pytest.raises(podcasts.Unheard) as caught:
        podcasts.hear(episode)
    assert caught.value.where == "fetch" and "HTTP 403" in caught.value.why

    monkeypatch.setattr(door, "window", lambda url, into, s, m: into.write_bytes(b"x"))

    def broken(source: Path, into: Path, start: float, end: float) -> None:
        failed = subprocess.CalledProcessError(1, ["ffmpeg"], stderr=b"x\nInvalid data found\n")
        raise TargumError("We couldn't read the recording.") from failed

    monkeypatch.setattr(tools, "cut", broken)
    with pytest.raises(podcasts.Unheard) as caught:
        podcasts.hear(episode)
    assert caught.value.where == "cut" and caught.value.why.endswith("Invalid data found")

    monkeypatch.setattr(tools, "cut", lambda source, into, a, b: into.write_bytes(b"x"))

    def no_credits(self: Any, audio: Path, language: str = "", **more: Any) -> Any:
        raise ProviderError("The recording could not be transcribed.", NO_CREDITS)

    monkeypatch.setattr(openai_whisper.WhisperTranscriber, "transcribe", no_credits)
    with pytest.raises(podcasts.Unheard) as caught:
        podcasts.hear(episode)
    assert caught.value.where == "transcriber"
    assert caught.value.why == "OpenAI 429 credit_balance_exhausted"


def test_music_with_hardly_a_word_is_not_offered(store: Store) -> None:
    sparse = podcasts.Heard(text="בית " * 85 + "ספר " * 5, seconds=600.0)
    found = night(store, Ears(sparse))
    assert SAMPLED not in by_url(store) and found.dropped["short"] == 1


def test_the_two_minutes_come_from_the_middle() -> None:
    episode = podcasts.Episode(
        show=SHOW, audio=SAMPLED, title="", published=0, seconds=2400, length=38_400_000
    )
    start, most, lead = podcasts.window_of(episode)
    assert lead == podcasts.PAD_SECONDS
    assert start == (1200 - 60 - podcasts.PAD_SECONDS) * 16_000, "the feed's own bit rate"
    assert most == (2 * podcasts.PAD_SECONDS + podcasts.SAMPLE_SECONDS) * 16_000
    short = podcasts.Episode(show=SHOW, audio=SAMPLED, title="", published=0, seconds=130)
    start, _, lead = podcasts.window_of(short)
    assert start == 0 and lead == 5, "a short episode: read from its start, cut at its middle"


def test_hearing_a_sample_keeps_nothing_on_disk(monkeypatch: pytest.MonkeyPatch) -> None:
    from targum.audio import tools
    from targum.ingest import url as door
    from targum.transcribe import openai_whisper
    from targum.transcribe.models import Transcript, Word

    folders: list[Path] = []
    asked: list[tuple[int, int]] = []

    def window(url: str, into: Path, start: int, most: int) -> Any:
        folders.append(into.parent)
        asked.append((start, most))
        into.write_bytes(b"\xff\xfb" * 100)

    def cut(source: Path, into: Path, start: float, end: float) -> None:
        assert end - start == podcasts.SAMPLE_SECONDS
        into.write_bytes(source.read_bytes())

    def transcribe(self: Any, audio: Path, language: str = "", **more: Any) -> Transcript:
        assert language == "he"
        return Transcript(
            provider="openai/whisper-1",
            duration=120.0,
            words=[Word(text="בית", start=n, end=n + 0.5) for n in range(90)],
        )

    monkeypatch.setattr(door, "window", window)
    monkeypatch.setattr(tools, "cut", cut)
    monkeypatch.setattr(openai_whisper.WhisperTranscriber, "transcribe", transcribe)
    episode = podcasts.Episode(
        show=SHOW, audio=SAMPLED, title="פרק", published=0, seconds=2400, length=38_400_000
    )
    heard = podcasts.hear(episode)
    assert heard.rate == 45.0 and heard.cost == pytest.approx(0.012)
    assert asked == [podcasts.window_of(episode)[:2]]
    assert folders and not folders[0].exists(), "the sound and its words are deleted"


def test_the_door_asks_for_a_stretch_and_reads_no_more(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from targum.ingest import url as door

    class Answer:
        status_code = 206
        headers = {"content-type": "audio/mpeg"}

        def iter_content(self, chunk_size: int | None = None) -> Any:
            yield b"a" * 600
            yield b"b" * 600

        def close(self) -> None:
            pass

    knocks: list[dict[str, Any]] = []

    class Client:
        def get(self, url: str, **kw: Any) -> Answer:
            knocks.append(kw)
            return Answer()

    monkeypatch.setattr(door, "POLITE_S", 0.0)
    monkeypatch.setattr(door, "_reachable", lambda url: None)
    monkeypatch.setattr(door, "_session", lambda proxy="": Client())
    got = door.window("https://audio.example/a.mp3", tmp_path / "w.mp3", 5_000, 1_000)
    assert knocks[0]["headers"] == {"Range": "bytes=5000-5999"}
    assert got.path.read_bytes() == b"a" * 600 + b"b" * 400, "never past what was asked for"


def test_a_feed_says_its_size_its_flag_and_its_timed_transcript() -> None:
    items = {item.guid: item for item in feeds.parse(FEED_BODY)}
    first = items["ep-transcript"]
    assert first.transcript == TRANSCRIPT and first.transcript_type == "application/x-subrip"
    assert first.length == 28_800_000 and first.seconds == 1800 and not first.explicit
    assert items["ep-explicit"].explicit
    assert items["ep-no-length"].length == 0


def test_a_kept_episode_counts_into_the_podcasts_register(store: Store) -> None:
    night(store)
    counted = table_finds.public_finds(store)
    assert counted and {one.register for one in counted} == {PODCASTS}
    assert {one.kind for one in counted} == {"podcast"}


def test_the_reviewed_list_names_every_show_s_licence() -> None:
    listed = podcasts.shows()
    assert len(listed) >= 40
    assert len({show.feed for show in listed}) == len(listed), "no show twice"
    raw = json.loads(podcasts.SHOWS.read_text(encoding="utf-8"))
    for row in raw["feeds"]:
        assert row["feed"].startswith("https://"), row["key"]
        assert row["licence"] and row["checked"], row["key"]
        assert row["chips"] and all(code in chips.BY_CODE for code in row["chips"]), row["key"]
    assert all(show.tags for show in listed)
    assert raw["excluded"], "what was looked at and left out, and why"


def test_a_curator_s_podcast_in_sources_json_is_read_too(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    listed = tmp_path / "sources.json"
    listed.write_text(
        json.dumps(
            {
                "publishers": [
                    {"key": "paper", "feed": "https://paper.example/rss", "kind": "news"},
                    {
                        "key": "added",
                        "name": "תוכנית שנוספה",
                        "feed": "https://added.example/feed.xml",
                        "homepage": "https://www.added.example/",
                        "kind": "podcast",
                        "licence": "All rights reserved.",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("TARGUM_SOURCES", str(listed))
    assert sources.load()
    shows = podcasts.shows(path=tmp_path / "empty.json")
    assert [(show.key, show.site) for show in shows] == [("added", "added.example")]


def test_an_older_pool_gains_the_speech_rate(tmp_path: Path) -> None:
    file = tmp_path / "old.db"
    with sqlite3.connect(file) as old:
        old.executescript(
            pool.SCHEMA.replace(",\n  rate       REAL    NOT NULL DEFAULT 0", "")
            + "PRAGMA user_version = 55;"
        )
    before = sqlite3.connect(file).execute("PRAGMA table_info(find)")
    assert "rate" not in {row[1] for row in before}
    opened = Store(file)
    assert "rate" in {row[1] for row in opened.db.execute("PRAGMA table_info(find)")}
    assert opened.db.execute("PRAGMA user_version").fetchone()[0] == accounts.SCHEMA_VERSION


def test_it_is_off_unless_the_box_says_so(monkeypatch: pytest.MonkeyPatch) -> None:
    assert not podcasts.on()
    said = CliRunner().invoke(app, ["finds", "podcasts"])
    assert said.exit_code == 0 and "off" in said.output
    monkeypatch.setenv(podcasts.FLAG, "1")
    assert podcasts.on()


def test_the_timer_runs_nightly_as_targum_at_its_own_hour() -> None:
    def unit(name: str) -> dict[str, list[str]]:
        fields: dict[str, list[str]] = {}
        for line in (DEPLOY / name).read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.startswith(("#", "[")):
                key, value = line.split("=", 1)
                fields.setdefault(key.strip(), []).append(value.strip())
        return fields

    service = unit("targum-finds-podcasts.service")
    assert service["User"] == ["targum"], "never as root"
    assert service["ExecStart"] == [
        "/usr/local/bin/targum finds podcasts --store /var/lib/targum/targum.db"
    ]
    assert service["EnvironmentFile"] == ["/etc/targum/targum.env"]
    (when,) = unit("targum-finds-podcasts.timer")["OnCalendar"]
    others = {
        unit(name.name)["OnCalendar"][0]
        for name in DEPLOY.glob("*.timer")
        if name.name != "targum-finds-podcasts.timer"
    }
    assert when == "*-*-* 02:00:00 UTC" and when not in others
    script = (DEPLOY / "deploy.sh").read_text(encoding="utf-8")
    assert "deploy/targum-finds-podcasts.service deploy/targum-finds-podcasts.timer" in script
    installed = next(line for line in script.splitlines() if "for unit in" in line)
    assert "targum-finds-podcasts.service targum-finds-podcasts.timer" in installed
    enable = next(line for line in script.splitlines() if "systemctl enable --now" in line)
    assert "targum-finds-podcasts.timer" in enable


def test_a_transcript_in_another_language_gives_way_to_a_sample(store: Store) -> None:
    english = "1\n00:00:00,000 --> 00:01:00,000\n" + "speaker says something here " * 30 + "\n"
    ears = Ears()
    found = night(store, ears, read=lambda url: english)
    assert found.transcripts == 0
    assert ears.asked == ["https://audio.example/show/ep-transcript.mp3", SAMPLED]


def test_the_caps_are_thirty_a_night_and_six_hundred_a_month() -> None:
    """David, 2026-11-03: "30 a night, 600 a month", inside the discovery budget."""
    assert podcasts.DAY_SAMPLES == 30
    assert podcasts.MONTH_SAMPLES == 600
    assert podcasts.MONTH_SAMPLES * podcasts.sample_cost() < pool.BUDGET_DEFAULT / 2, (
        "a full month of samples leaves the other sources most of the default budget"
    )
