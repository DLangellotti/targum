"""Faster internet lookups for a host (2026-10-06): a described link remembered, one
budget over a YouTube lookup, the Data API asked before yt-dlp, and the publishers'
feeds kept warm in the background."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from targum.chat import tools
from targum.errors import OffHere, TargumError
from targum.video import remembered, youtube

ANSWER = {
    "id": "abc123defgh",
    "title": "שיעור",
    "duration": 600.0,
    "webpage_url": "https://www.youtube.com/watch?v=abc123defgh",
    "formats": [{"acodec": "opus", "language": "he", "language_preference": 10}],
    "subtitles": {"iw": [{"ext": "vtt"}]},
    "license": "Creative Commons Attribution license (reuse allowed)",
}


class Clock:
    """A clock a test moves by hand."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def _ytdlp(monkeypatch, answer: dict[str, Any] = ANSWER) -> list[list[str]]:
    """Stand in for the binary; every run it is asked for is recorded."""
    seen: list[list[str]] = []

    def run(args, **kwargs):
        seen.append(list(args))
        return subprocess.CompletedProcess(args, 0, json.dumps(answer).encode(), b"")

    monkeypatch.setattr(youtube.subprocess, "run", run)
    monkeypatch.setattr(youtube, "ytdlp_available", lambda: (True, "yt-dlp"))
    monkeypatch.setattr("targum.video.ytdlp_available", lambda: (True, "yt-dlp"))
    return seen


# -- a described link is remembered ----------------------------------------------------


def test_an_answer_is_remembered_for_its_time_and_then_asked_again() -> None:
    clock = Clock()
    kept = remembered.Remembered(keep_s=60, refused_s=5, clock=clock)
    asked: list[int] = []

    def ask() -> dict[str, Any]:
        asked.append(1)
        return {"n": len(asked)}

    assert kept.through("k", ask) == {"n": 1}
    clock.now += 59
    assert kept.through("k", ask) == {"n": 1}
    clock.now += 2
    assert kept.through("k", ask) == {"n": 2}
    assert len(asked) == 2


def test_a_refusal_is_remembered_briefly_and_a_missing_binary_not_at_all() -> None:
    clock = Clock()
    kept = remembered.Remembered(keep_s=60, refused_s=5, clock=clock)
    asked: list[int] = []

    def refuse() -> dict[str, Any]:
        asked.append(1)
        raise TargumError("Private video.")

    for _ in range(3):
        with pytest.raises(TargumError, match="Private video"):
            kept.through("k", refuse)
    assert len(asked) == 1, "the same refusal, said again without asking"
    clock.now += 6
    with pytest.raises(TargumError):
        kept.through("k", refuse)
    assert len(asked) == 2

    def absent() -> dict[str, Any]:
        asked.append(1)
        raise OffHere("yt-dlp is not installed.")

    for _ in range(2):
        with pytest.raises(OffHere):
            kept.through("gone", absent)
    assert len(asked) == 4, "an operator's fix is seen on the next ask"


def test_it_is_bounded_and_hands_out_copies() -> None:
    kept = remembered.Remembered(most=2)
    for key in ("a", "b", "c"):
        kept.through(key, lambda key=key: {"key": key})
    assert len(kept) == 2
    first = kept.through("c", lambda: pytest.fail("remembered"))
    first["duration"] = 99
    assert "duration" not in kept.through("c", lambda: pytest.fail("remembered"))
    assert kept.through("a", lambda: {"key": "again"}) == {"key": "again"}, "the oldest went"


def test_every_spelling_of_one_video_is_one_lookup(monkeypatch) -> None:
    seen = _ytdlp(monkeypatch)
    for url in (
        "https://youtu.be/abc123defgh",
        "https://www.youtube.com/watch?v=abc123defgh&t=42",
        "https://www.youtube.com/shorts/abc123defgh",
    ):
        assert youtube.describe(url)["title"] == "שיעור"
    assert len(seen) == 1


def test_the_quote_after_describe_source_does_not_ask_youtube_again(
    monkeypatch, tmp_path: Path
) -> None:
    """The pair this exists for: a host's `describe_source`, then the quote it makes from
    the `quote_with` address it was handed. Both used to run `yt-dlp -J` in full."""
    from targum.serve import Job, Library

    seen = _ytdlp(monkeypatch)
    ctx = SimpleNamespace(store=None)
    described = tools.describe_source(ctx, {"url": "https://youtu.be/abc123defgh"})
    assert described["kind"] == "video" and described["seconds"] == 600

    job = Job(id="a", source=described["quote_with"], home=tmp_path)
    Library(tmp_path).prepare(job)
    assert job.error == "" and job.seconds == 600.0
    assert job.options["subtitles"] is True
    assert len(seen) == 1, "the quote answered from what describe_source was told"


def test_a_reel_and_a_tiktok_are_remembered_by_their_one_address(monkeypatch) -> None:
    from targum.video import instagram, tiktok

    asked: list[str] = []

    def run(argv, **kwargs):
        asked.append(argv[-1])
        return subprocess.CompletedProcess(
            argv, 0, json.dumps({"title": "x", "duration": 30}).encode(), b""
        )

    monkeypatch.setattr(instagram, "run_ytdlp", run)
    monkeypatch.setattr(tiktok, "run_ytdlp", run)
    instagram.describe("https://www.instagram.com/reel/DQGn1BljOyO/?igsh=x")
    instagram.describe("https://www.instagram.com/kan_news/reel/DQGn1BljOyO/")
    tiktok.describe("https://www.tiktok.com/@someone/video/7512345678901234567?is_from_webapp=1")
    tiktok.describe("https://www.tiktok.com/@someone/video/7512345678901234567")
    assert len(asked) == 2


# -- one budget over a YouTube lookup --------------------------------------------------

BOT_CHECK = b"ERROR: [youtube] abc123defgh: Sign in to confirm you're not a bot.\n"


def test_each_attempt_gets_what_is_left_and_the_lookup_stops_when_it_is_gone(
    monkeypatch,
) -> None:
    """Five routes at 120 s each held a reader for minutes. Every route together now has
    `LOOKUP_S`; each attempt is given what is left, and the next is not started once it
    is gone."""
    clock = Clock()
    monkeypatch.setattr(youtube, "_clock", clock)
    given: list[float] = []

    def run(args, **kwargs):
        given.append(kwargs["timeout"])
        clock.now += 8  # a flagged exit, refused after eight seconds
        raise subprocess.CalledProcessError(1, args, stderr=BOT_CHECK)

    monkeypatch.setattr(youtube.subprocess, "run", run)
    monkeypatch.setattr(youtube, "ytdlp_available", lambda: (True, "yt-dlp"))
    monkeypatch.setenv(youtube.YTDLP_PROXY_ENV, "http://first:1")
    with pytest.raises(TargumError) as raised:
        youtube.describe("https://youtu.be/abc123defgh")
    assert given == [20.0, 12.0, 4.0], "three attempts fit, the fourth is never started"
    assert raised.value.message == "YouTube is slow right now. Try again in a minute."
    assert raised.value.key == "video.slow" and raised.value.fill == {"host": "YouTube"}


def test_an_attempt_cut_off_by_the_budget_is_slow_not_late(monkeypatch) -> None:
    clock = Clock()
    monkeypatch.setattr(youtube, "_clock", clock)

    def run(args, **kwargs):
        clock.now += kwargs["timeout"]
        raise subprocess.TimeoutExpired(args, kwargs["timeout"])

    monkeypatch.setattr(youtube.subprocess, "run", run)
    monkeypatch.setattr(youtube, "ytdlp_available", lambda: (True, "yt-dlp"))
    with pytest.raises(TargumError, match="YouTube is slow right now"):
        youtube.describe("https://youtu.be/abc123defgh")


def test_the_build_keeps_its_own_two_hours(monkeypatch, tmp_path: Path) -> None:
    given: list[float] = []

    def run(args, **kwargs):
        given.append(kwargs["timeout"])
        (tmp_path / "source.mp4").write_bytes(b"film")
        return subprocess.CompletedProcess(args, 0, b"", b"")

    monkeypatch.setattr(youtube.subprocess, "run", run)
    monkeypatch.setattr(youtube, "ytdlp_available", lambda: (True, "yt-dlp"))
    youtube.fetch("https://youtu.be/abc123defgh", tmp_path)
    assert given == [7200]


def test_a_slow_youtube_reaches_a_host_and_a_russian_reader_plainly(
    monkeypatch, tmp_path: Path
) -> None:
    from targum.serve import Job, Library

    clock = Clock()
    monkeypatch.setattr(youtube, "_clock", clock)

    def run(args, **kwargs):
        clock.now += kwargs["timeout"]
        raise subprocess.TimeoutExpired(args, kwargs["timeout"])

    monkeypatch.setattr(youtube.subprocess, "run", run)
    monkeypatch.setattr(youtube, "ytdlp_available", lambda: (True, "yt-dlp"))
    monkeypatch.setattr("targum.video.ytdlp_available", lambda: (True, "yt-dlp"))
    ctx = SimpleNamespace(store=None)
    got = tools.describe_source(ctx, {"url": "https://youtu.be/abc123defgh"})
    assert got == {"kind": "video", "error": "YouTube is slow right now. Try again in a minute."}

    remembered.DESCRIBED.clear()
    job = Job(id="a", source="https://youtu.be/abc123defgh", home=tmp_path, ui="ru")
    Library(tmp_path).prepare(job)
    assert job.stage == "failed"
    assert job.error == "YouTube сейчас отвечает медленно. Попробуйте через минуту."


# -- the Data API before yt-dlp --------------------------------------------------------

KEY = "AIza-test-key-never-logged"

#: What `videos.list` said for a Khan Academy Hebrew lesson on 2026-10-06, trimmed.
LISTED = {
    "items": [
        {
            "id": "abc123defgh",
            "snippet": {
                "title": "שיעור",
                "channelTitle": "Khan Academy Hebrew",
                "channelId": "UC123",
                "description": "",
                "defaultAudioLanguage": "en",
                "liveBroadcastContent": "none",
            },
            "contentDetails": {"duration": "PT10M", "caption": "true", "contentRating": {}},
            "status": {
                "uploadStatus": "processed",
                "privacyStatus": "public",
                "license": "creativeCommon",
                "embeddable": True,
            },
        }
    ]
}

CAPTIONS = {
    "items": [
        {"snippet": {"language": "iw", "trackKind": "standard", "status": "serving"}},
        {"snippet": {"language": "he", "trackKind": "asr", "status": "serving"}},
        {"snippet": {"language": "en", "trackKind": "standard", "status": "failed"}},
    ]
}


class _Answer:
    def __init__(self, body: dict[str, Any]) -> None:
        self.body = json.dumps(body).encode()

    def __enter__(self) -> _Answer:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def read(self) -> bytes:
        return self.body


def _google(monkeypatch, **said: Any) -> list[str]:
    """Stand in for the Data API. `said` maps a path to a body, or to an exception."""
    import urllib.parse

    asked: list[str] = []

    def urlopen(request, timeout=None):
        address = urllib.parse.urlparse(request.full_url)
        assert address.scheme == "https" and address.hostname == "www.googleapis.com"
        assert urllib.parse.parse_qs(address.query)["key"] == [KEY]
        assert timeout is not None and 0 < timeout <= youtube.API_TIMEOUT_S
        path = address.path.rsplit("/", 1)[-1]
        asked.append(path)
        answer = said[path]
        if isinstance(answer, Exception):
            raise answer
        return _Answer(answer)

    monkeypatch.setattr(youtube.urllib.request, "urlopen", urlopen)
    monkeypatch.setenv(youtube.API_KEY_ENV, KEY)
    return asked


def _refused(code: int, reason: str) -> Exception:
    import io
    import urllib.error

    body = json.dumps({"error": {"code": code, "errors": [{"reason": reason}]}}).encode()
    return urllib.error.HTTPError(
        f"https://www.googleapis.com/youtube/v3/videos?key={KEY}", code, "no", {}, io.BytesIO(body)
    )


def test_the_api_answers_what_ytdlp_would_in_the_shape_the_screen_reads(monkeypatch) -> None:
    """Parity: the five things `screen.from_ytdlp` reads, the same from either door —
    and `describe_source` the same word for word, so nothing downstream can tell."""
    from targum import screen

    asked = _google(monkeypatch, videos=LISTED, captions=CAPTIONS)
    seen = _ytdlp(monkeypatch)
    via_api = youtube.describe("https://youtu.be/abc123defgh")
    assert asked == ["videos", "captions"] and seen == [], "yt-dlp is never asked"
    assert via_api["answered_by"] == "youtube-data-api"

    api, ytdlp = screen.from_ytdlp(via_api), screen.from_ytdlp(ANSWER)
    assert api.title == ytdlp.title == "שיעור"
    assert api.duration == ytdlp.duration == 600.0
    assert api.licence == ytdlp.licence
    assert api.subtitles == ("iw",), "the standard track, not the ASR one or a failed one"
    assert api.audio == ("he",), "the ASR track's language, not the uploader's `en`"
    assert api.source == ytdlp.source

    ctx = SimpleNamespace(store=None)
    from_api = tools.describe_source(ctx, {"url": "https://youtu.be/abc123defgh"})
    remembered.DESCRIBED.clear()
    monkeypatch.delenv(youtube.API_KEY_ENV)
    from_ytdlp = tools.describe_source(ctx, {"url": "https://youtu.be/abc123defgh"})
    assert len(seen) == 1
    assert from_api == from_ytdlp


def test_the_standard_licence_says_nothing_as_ytdlp_does(monkeypatch) -> None:
    import copy

    listed = copy.deepcopy(LISTED)
    listed["items"][0]["status"]["license"] = "youtube"
    listed["items"][0]["contentDetails"]["duration"] = "P0D"
    _google(monkeypatch, videos=listed, captions={"items": []})
    said = youtube.describe("https://youtu.be/abc123defgh")
    assert said["license"] is None
    assert said["duration"] is None, "a live stream has no length, and is refused for it"
    assert said["subtitles"] == {} and said["formats"] == []


@pytest.mark.parametrize(
    "videos",
    [
        _refused(403, "quotaExceeded"),
        _refused(400, "keyInvalid"),
        _refused(500, "backendError"),
        TimeoutError("timed out"),
        {"items": []},
        {"not": "a listing"},
    ],
    ids=["quota", "bad-key", "google-down", "timeout", "no-such-video", "odd-answer"],
)
def test_anything_the_api_cannot_answer_goes_to_ytdlp(monkeypatch, caplog, videos) -> None:
    caplog.set_level("INFO", logger=youtube.__name__)
    _google(monkeypatch, videos=videos, captions=CAPTIONS)
    seen = _ytdlp(monkeypatch)
    assert youtube.describe("https://youtu.be/abc123defgh")["title"] == "שיעור"
    assert len(seen) == 1
    assert KEY not in caplog.text, "the key never reaches the journal"


@pytest.mark.parametrize(
    "change",
    [
        {"status": {"privacyStatus": "private", "uploadStatus": "processed"}},
        {"status": {"privacyStatus": "public", "uploadStatus": "uploaded"}},
        {"contentDetails": {"duration": "PT10M", "contentRating": {"ytRating": "ytAgeRestricted"}}},
        {"contentDetails": {"duration": "PT10M", "regionRestriction": {"blocked": ["IL"]}}},
    ],
    ids=["private", "processing", "age-gated", "region-blocked"],
)
def test_a_video_the_build_might_not_get_is_asked_of_ytdlp(monkeypatch, change) -> None:
    import copy

    listed = copy.deepcopy(LISTED)
    listed["items"][0].update(change)
    asked = _google(monkeypatch, videos=listed, captions=CAPTIONS)
    seen = _ytdlp(monkeypatch)
    youtube.describe("https://youtu.be/abc123defgh")
    assert asked == ["videos"] and len(seen) == 1


def test_a_refused_key_rests_the_api_and_one_video_does_not(monkeypatch) -> None:
    clock = Clock()
    monkeypatch.setattr(youtube, "_clock", clock)
    asked = _google(monkeypatch, videos=_refused(403, "quotaExceeded"), captions=CAPTIONS)
    _ytdlp(monkeypatch)
    youtube.describe("https://youtu.be/abc123defgh")
    youtube.describe("https://youtu.be/zzz123defgh")
    assert asked == ["videos"], "out of quota: not asked again for every lookup"
    clock.now += youtube.API_REST_S + 1
    youtube.describe("https://youtu.be/yyy123defgh")
    assert asked == ["videos", "videos"]

    monkeypatch.setattr(youtube._REST, "until", 0.0)
    again = _google(monkeypatch, videos={"items": []}, captions=CAPTIONS)
    youtube.describe("https://youtu.be/xxx123defgh")
    youtube.describe("https://youtu.be/www123defgh")
    assert again == ["videos", "videos"], "a video Google has not got rests nothing"


def test_a_caption_list_that_fails_is_only_survivable_where_there_are_none(monkeypatch) -> None:
    import copy

    listed = copy.deepcopy(LISTED)
    listed["items"][0]["contentDetails"]["caption"] = "false"
    _google(monkeypatch, videos=listed, captions=_refused(403, "forbidden"))
    seen = _ytdlp(monkeypatch)
    said = youtube.describe("https://youtu.be/abc123defgh")
    assert said["answered_by"] == "youtube-data-api" and said["subtitles"] == {}
    assert seen == []

    remembered.DESCRIBED.clear()
    monkeypatch.setattr(youtube._REST, "until", 0.0)
    _google(monkeypatch, videos=LISTED, captions=_refused(500, "backendError"))
    youtube.describe("https://youtu.be/abc123defgh")
    assert len(seen) == 1, "Google says somebody wrote a track; yt-dlp is asked which"


def test_no_key_and_an_id_that_is_not_one_never_reach_google(monkeypatch) -> None:
    def urlopen(*args, **kwargs):
        raise AssertionError("asked Google")

    monkeypatch.setattr(youtube.urllib.request, "urlopen", urlopen)
    seen = _ytdlp(monkeypatch)
    youtube.describe("https://youtu.be/abc123defgh")
    monkeypatch.setenv(youtube.API_KEY_ENV, KEY)
    assert youtube.from_data_api("abc/../x?y=1") is None
    assert len(seen) == 1


def test_the_api_spends_the_same_budget_as_ytdlp(monkeypatch) -> None:
    """A Google that hangs takes its four seconds out of the twenty, not on top."""
    clock = Clock()
    monkeypatch.setattr(youtube, "_clock", clock)

    def slow(request, timeout=None):
        clock.now += timeout
        raise TimeoutError("timed out")

    monkeypatch.setattr(youtube.urllib.request, "urlopen", slow)
    monkeypatch.setenv(youtube.API_KEY_ENV, KEY)
    given: list[float] = []

    def run(args, **kwargs):
        given.append(kwargs["timeout"])
        return subprocess.CompletedProcess(args, 0, json.dumps(ANSWER).encode(), b"")

    monkeypatch.setattr(youtube.subprocess, "run", run)
    monkeypatch.setattr(youtube, "ytdlp_available", lambda: (True, "yt-dlp"))
    youtube.describe("https://youtu.be/abc123defgh")
    assert given == [youtube.LOOKUP_S - youtube.API_TIMEOUT_S]
