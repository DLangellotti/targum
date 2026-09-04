"""Hosted audio: parts bought like chapters, priced by the clock, routed to the build."""

from __future__ import annotations

import json as json_module
import threading
from collections.abc import Iterator
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from targum.accounts import Store
from targum.mail import ConsoleMailer
from targum.pipeline import Build
from targum.serve import Handler, Job, Library
from targum.transcribe.null import NullTranscriber


class SplitsOnFullStops:
    name = "fake/1"

    def split(self, texts: list[str], language: str) -> list[list[str]]:
        return [[part.strip() + "." for part in text.split(".") if part.strip()] for text in texts]


def test_buying_a_part_goes_through_run_part_not_run_chapter(tmp_path: Path) -> None:
    """run_chapter rewrites the translation from disk, and hearing a part changes the
    document hash under it — the build path is the one that knows how to grow."""
    library = Library(tmp_path)
    took: list[str] = []
    library.run_part = lambda job: took.append("part")  # type: ignore[method-assign]
    library.run_chapter = lambda job: took.append("chapter")  # type: ignore[method-assign]
    library.run(Job(id="a", source="s", options={"parts": [3], "folder": "talk-en"}))
    assert took == ["part"]


def test_a_prepared_audio_job_reports_seconds_and_parts(fake_audio, tmp_path: Path) -> None:
    """The card shows a clock and a count, never dollars — so the facts ride on the
    job's state for the page to shape."""
    fake_audio.duration = 1440.0
    source = tmp_path / "talk.mp3"
    source.write_bytes(b"audio")
    build = Build(
        str(source),
        target_language="en",
        source_language="en",
        provider_name="null",
        segmenter=SplitsOnFullStops(),
        transcriber=NullTranscriber(text="a word.", language="en"),
        out_root=tmp_path / "out",
    )
    plan = build.plan(chapters=1)
    assert plan.audio is not None
    assert plan.audio.duration == 1440.0
    assert plan.audio.parts == 2
    assert plan.audio.buying_parts == [1]
    assert plan.audio.buying_seconds == pytest.approx(720.0)
    job = Job(id="a", source=str(source))
    job.audio = True
    job.seconds = plan.audio.duration
    job.parts = plan.audio.parts
    state = job.state()
    assert state["audio"] is True
    assert state["seconds"] == 1440.0
    assert state["parts"] == 2


def test_the_estimate_prices_the_first_part_from_its_duration(fake_audio, tmp_path: Path) -> None:
    """Nothing has been heard, so the price comes from the clock and a speech rate."""

    class PricedTranscriber(NullTranscriber):
        def price_per_minute(self) -> float:
            return 0.006

    fake_audio.duration = 1440.0
    source = tmp_path / "talk.mp3"
    source.write_bytes(b"audio")
    build = Build(
        str(source),
        target_language="en",
        source_language="en",
        provider_name="null",
        segmenter=SplitsOnFullStops(),
        transcriber=PricedTranscriber(text="a word.", language="en"),
        out_root=tmp_path / "out",
    )
    plan = build.plan(chapters=1)
    assert plan.audio is not None
    assert plan.audio.transcription == pytest.approx(720.0 / 60 * 0.006)
    assert plan.estimated_cost >= plan.audio.transcription


def test_a_recording_in_a_language_targum_does_not_read_costs_a_minute_not_a_part(
    fake_audio, tmp_path: Path
) -> None:
    """The probe hears sixty seconds before a part is bought; a Russian audiobook is
    refused for a cent, with the refusal saying what targum does read."""
    from targum.errors import TargumError

    class Russian(NullTranscriber):
        def __init__(self) -> None:
            super().__init__(text="привет мир как дела", language="ru")

        def price_per_minute(self) -> float:
            return 0.006

    fake_audio.duration = 1440.0
    source = tmp_path / "govorit.mp3"
    source.write_bytes(b"audio")
    build = Build(
        str(source),
        target_language="en",
        provider_name="null",
        segmenter=SplitsOnFullStops(),
        transcriber=Russian(),
        out_root=tmp_path / "out",
    )
    with pytest.raises(TargumError, match="targum reads"):
        build.run(chapters=1)
    # The probe clip, not a whole part, is what was heard.
    heard = build.transcriber.spent.seconds_by_model.get("null", 0.0)
    assert 0 < heard <= 61.0


def test_a_from_hint_skips_the_language_probe(fake_audio, tmp_path: Path) -> None:
    """--from is the reader saying what this is; the probe would spend a cent to
    second-guess them."""

    class Priced(NullTranscriber):
        def price_per_minute(self) -> float:
            return 0.006

    fake_audio.duration = 600.0
    source = tmp_path / "talk.mp3"
    source.write_bytes(b"audio")
    engine = Priced(text="a word here.", language="ru")
    build = Build(
        str(source),
        target_language="en",
        source_language="en",
        provider_name="null",
        segmenter=SplitsOnFullStops(),
        transcriber=engine,
        out_root=tmp_path / "out",
    )
    build.run()
    assert engine.spent.calls == 1  # the part alone, no probe


"""--- the chunked door ---"""


@pytest.fixture
def served(tmp_path: Path) -> Iterator[tuple[int, str, Path]]:
    """A running server on a free port — the test_serve fixture's shape, declared here
    because tests never import each other (that import resolved by accident of
    sys.path and stopped a deploy)."""
    import io

    out = tmp_path / "targum-out"
    out.mkdir()
    token = "test-key"
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    handler = type(
        "TestHandler",
        (Handler,),
        {
            "library": Library(out),
            "token": token,
            "page": "<html>start</html>",
            "progress": "<html>your progress</html>",
            "shelf": "<html>library</html>",
            "lists": {k: "<html></html>" for k in ("texts", "words", "phrases")},
            "store": Store(tmp_path / "words.db"),
            "mailer": ConsoleMailer(io.StringIO()),
            "address": f"http://127.0.0.1:{port}",
        },
    )
    server.RequestHandlerClass = handler
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield port, token, out
    finally:
        server.shutdown()
        server.server_close()


def raw(port: int, path: str, body: bytes, kind: str = "application/octet-stream"):
    connection = HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        connection.request("POST", path, body, {"Content-Type": kind})
        response = connection.getresponse()
        return response.status, json_module.loads(response.read())
    finally:
        connection.close()


def begin(port: int, token: str, name: str = "talk.mp3", size: int = 10):
    return raw(
        port,
        f"/upload/begin?k={token}",
        json_module.dumps({"name": name, "size": size}).encode(),
        "application/json",
    )


def test_a_chunked_upload_is_assembled_in_order_and_answered_with_its_length(
    served, fake_audio
) -> None:
    port, token, _out = served
    fake_audio.duration = 600.0
    status, opened = begin(port, token, size=6)
    assert status == 200 and opened["upload"]
    upload = opened["upload"]
    assert raw(port, f"/upload/{upload}/1?k={token}", b"def")[0] == 200
    assert raw(port, f"/upload/{upload}/0?k={token}", b"abc")[0] == 200
    status, done = raw(port, f"/upload/{upload}/end?k={token}", b"{}", "application/json")
    assert status == 200
    assert done["upload"] == upload
    assert done["seconds"] == 600.0
    assert done["parts"] == 1


def test_sound_alone_in_a_video_container_keeps_the_audio_ceiling(
    served, fake_audio, monkeypatch
) -> None:
    """The suffix chose 4 GB at the door; the probe heard no pictures, so the file is
    a recording and a recording's ceiling holds whatever the container claims."""
    import targum.serve as serve_module

    port, token, _out = served
    fake_audio.video = False  # an .mp4 with nothing but sound in it
    monkeypatch.setattr(serve_module, "MAX_AUDIO_BYTES", 2)
    _status, opened = begin(port, token, name="talk.mp4", size=3)
    upload = opened["upload"]
    raw(port, f"/upload/{upload}/0?k={token}", b"abc")
    status, answer = raw(port, f"/upload/{upload}/end?k={token}", b"{}", "application/json")
    assert status == 413
    assert "over 1 GB" in answer["error"]


#: What `yt-dlp -J` says about a ten-minute lesson with a written Hebrew track.
WATCHED = {
    "webpage_url": "https://www.youtube.com/watch?v=abc123",
    "title": "A lesson",
    "duration": 600.0,
    "formats": [{"acodec": "opus", "language": "he", "language_preference": 10}],
    "subtitles": {"iw": [{"ext": "vtt"}]},
    "license": "Creative Commons Attribution license (reuse allowed)",
}


def described(monkeypatch, answer: object) -> list[str]:
    """Stand in for `yt-dlp -J`, and record that nothing else was ever run.

    The point of the door is that a click asking for a price does not download a video,
    so a test of it has to be able to say that no fetch happened.
    """
    from targum.video import youtube as youtube_module

    asked: list[str] = []

    def pretend(url: str) -> object:
        asked.append(url)
        if isinstance(answer, Exception):
            raise answer
        return answer

    monkeypatch.setattr(youtube_module, "describe", pretend)
    monkeypatch.setattr(
        youtube_module, "fetch", lambda *a, **k: pytest.fail("a price must not download")
    )
    monkeypatch.setattr("targum.video.ytdlp_available", lambda: (True, "yt-dlp"))
    return asked


def test_a_pasted_youtube_link_is_priced_from_its_metadata(tmp_path: Path, monkeypatch) -> None:
    """The door #136 left shut, opened. It is the reader's act — they paste the address
    and press the button — and it is priced the way a podcast episode is: from what can
    be said about the recording, before a byte of it moves."""
    asked = described(monkeypatch, WATCHED)
    library = Library(tmp_path)
    job = Job(id="a", source="https://www.youtube.com/watch?v=abc123")
    library.prepare(job)

    assert job.error == ""
    assert job.stage in ("ready", "blocked")
    assert job.title == "A lesson"
    assert asked == ["https://www.youtube.com/watch?v=abc123"], "metadata, once"
    # Charged against the hours, which is the rate limit this needed and already had.
    assert job.audio and job.seconds == 600.0
    # A track somebody wrote means nothing is transcribed, and the import is the price
    # of its English alone.
    assert job.options["subtitles"] is True
    assert job.transcription == 0.0
    assert job.estimate > 0


def test_a_video_with_no_written_track_is_priced_for_hearing_it(
    tmp_path: Path, monkeypatch
) -> None:
    """`from_ytdlp` counts only tracks somebody wrote — a guess YouTube made is not a
    transcript — so a video without one is quoted the transcription as well."""
    described(monkeypatch, {**WATCHED, "subtitles": {}})
    library = Library(tmp_path)
    job = Job(id="a", source="https://www.youtube.com/watch?v=abc123")
    library.prepare(job)
    assert job.options["subtitles"] is False
    assert job.transcription > 0


def test_a_live_stream_is_refused_before_it_can_fill_a_disk(tmp_path: Path, monkeypatch) -> None:
    """No duration is a stream that has not ended or a premiere that has not started.
    Priced at nothing, it would run until the disk did."""
    described(monkeypatch, {**WATCHED, "duration": 0})
    library = Library(tmp_path)
    job = Job(id="a", source="https://www.youtube.com/watch?v=abc123")
    library.prepare(job)
    assert job.stage == "failed"
    assert "live stream" in job.error


def test_a_video_longer_than_the_ceiling_is_refused(tmp_path: Path, monkeypatch) -> None:
    from targum.video import MAX_VIDEO_DURATION_S

    described(monkeypatch, {**WATCHED, "duration": MAX_VIDEO_DURATION_S + 1})
    library = Library(tmp_path)
    job = Job(id="a", source="https://www.youtube.com/watch?v=abc123")
    library.prepare(job)
    assert job.stage == "failed"
    assert "longer than" in job.error


def test_ytdlps_own_sentence_is_what_the_reader_is_told(tmp_path: Path, monkeypatch) -> None:
    """An age gate, a private video, a region block. yt-dlp's last line is better than
    anything written here, and a refusal travels on the job like every other."""
    from targum.errors import TargumError

    described(monkeypatch, TargumError("Sign in to confirm your age."))
    library = Library(tmp_path)
    job = Job(id="a", source="https://www.youtube.com/watch?v=abc123")
    library.prepare(job)
    assert job.stage == "failed"
    assert "confirm your age" in job.error


def test_a_box_without_ytdlp_says_so_rather_than_failing_later(tmp_path: Path, monkeypatch) -> None:
    """A fact about this box, not the reader's mistake."""
    monkeypatch.setattr("targum.video.ytdlp_available", lambda: (False, "install yt-dlp."))
    library = Library(tmp_path)
    job = Job(id="a", source="https://www.youtube.com/watch?v=abc123")
    library.prepare(job)
    assert job.stage == "failed"
    assert "cannot fetch from YouTube" in job.error


def test_a_watch_page_never_reaches_the_generic_ingester(tmp_path: Path, monkeypatch) -> None:
    """The reason the branch existed before it fetched anything, and the one thing that
    must not change: the fallback below it reads the watch page and imports the show
    notes as the text."""
    from targum.audio import episode as episode_module

    described(monkeypatch, WATCHED)
    monkeypatch.setattr(
        episode_module, "find", lambda *a, **k: pytest.fail("the watch page was read as a feed")
    )
    library = Library(tmp_path)
    for address in (
        "https://www.youtube.com/watch?v=abc123",
        "https://youtu.be/abc123",
        "https://m.youtube.com/watch?v=abc123",
    ):
        job = Job(id="a", source=address)
        library.prepare(job)
        assert job.error == "", address


def test_a_protected_audiobook_is_refused_at_the_door(served) -> None:
    port, token, _out = served
    status, answer = begin(port, token, name="book.aax")
    assert status == 400
    assert "protected" in answer["error"]


def test_a_file_that_is_not_audio_or_video_is_refused_at_the_door(served) -> None:
    port, token, _out = served
    status, answer = begin(port, token, name="film.avi")
    assert status == 400
    assert "not an audio or video file" in answer["error"]


def test_a_video_is_taken_at_the_door_and_probed_as_one(served, fake_audio) -> None:
    """The suffix chose the video path, so the probe may say yes to the pictures."""
    port, token, _out = served
    fake_audio.video = True
    fake_audio.duration = 600.0
    status, opened = begin(port, token, name="talk.mp4", size=3)
    assert status == 200 and opened["upload"]
    upload = opened["upload"]
    assert raw(port, f"/upload/{upload}/0?k={token}", b"abc")[0] == 200
    status, done = raw(port, f"/upload/{upload}/end?k={token}", b"{}", "application/json")
    assert status == 200
    assert done["seconds"] == 600.0


def test_a_video_may_be_bigger_than_a_recording_but_not_boundless(served) -> None:
    """4 GB for a video where a recording stops at 1 — and the same sentence past it."""
    port, token, _out = served
    three = 3 * 1024 * 1024 * 1024
    status, _answer = begin(port, token, name="talk.mp4", size=three)
    assert status == 200
    status, answer = begin(port, token, name="talk.mp4", size=5 * 1024 * 1024 * 1024)
    assert status == 413
    assert "over 4 GB" in answer["error"]
    status, answer = begin(port, token, name="talk.mp3", size=three)
    assert status == 413
    assert "over 1 GB" in answer["error"]


def test_an_upload_that_would_pass_the_quota_is_refused_before_a_byte_arrives(served) -> None:
    port, token, _out = served
    status, answer = begin(port, token, size=3 * 1024 * 1024 * 1024)
    assert status == 413
    assert "GB" in answer["error"]


def test_a_chunk_over_the_ceiling_is_refused(served) -> None:
    """The refusal comes before the body is read, so a client mid-send may see the
    pipe close instead of the answer — either way, nothing lands."""
    from targum.serve import CHUNK_BYTES

    port, token, out = served
    _status, opened = begin(port, token, size=CHUNK_BYTES * 2)
    upload = opened["upload"]
    try:
        status, _answer = raw(port, f"/upload/{upload}/0?k={token}", b"x" * (CHUNK_BYTES + 1))
        assert status == 413
    except (BrokenPipeError, ConnectionResetError):
        pass
    assert not any((out / "local" / "uploads" / upload / ".part").glob("*"))


def test_the_same_file_uploaded_twice_is_one_file(served, fake_audio) -> None:
    port, token, _out = served
    fake_audio.duration = 600.0
    _s, first = begin(port, token, size=3)
    raw(port, f"/upload/{first['upload']}/0?k={token}", b"abc")
    raw(port, f"/upload/{first['upload']}/end?k={token}", b"{}", "application/json")
    _s, second = begin(port, token, size=3)
    raw(port, f"/upload/{second['upload']}/0?k={token}", b"abc")
    _s, done = raw(port, f"/upload/{second['upload']}/end?k={token}", b"{}", "application/json")
    assert done == {"upload": first["upload"]}


def test_an_unfinished_upload_is_swept_after_a_day(served, monkeypatch) -> None:
    import targum.serve as serve_module

    port, token, out = served
    _s, opened = begin(port, token, size=1024)
    left = out / "local" / "uploads" / opened["upload"]
    assert left.is_dir()
    monkeypatch.setattr(serve_module, "UPLOAD_TTL_MS", -1)
    begin(port, token, size=8)  # any begin sweeps
    assert not left.exists()


def test_the_shelf_says_video_where_the_import_kept_its_pictures(tmp_path: Path) -> None:
    """A lecture with its slides and a podcast were one row saying "audio". The
    readers list carries both facts, so the page can draw one word and filter on it."""
    from targum.audio import manifest as manifest_module

    library = Library(tmp_path)
    talk = tmp_path / "talk-en"
    talk.mkdir()
    part = manifest_module.ManifestPart(number=1, start=0.0, end=10.0, audio="a.mp3")
    manifest_module.write(
        talk,
        manifest_module.AudioManifest(
            source="talk.mp3", sha256="x", duration=10.0, language="en", parts=[part]
        ),
    )
    heard = library._shape(talk, "talk.mp3", "en", 100)
    assert heard["spoken"] and not heard["video"]

    lecture = tmp_path / "lecture-en"
    lecture.mkdir()
    part.video = "audio/parts/part-001.mp4"
    manifest_module.write(
        lecture,
        manifest_module.AudioManifest(
            source="lecture.mp4", sha256="y", duration=10.0, language="en", parts=[part]
        ),
    )
    seen = library._shape(lecture, "lecture.mp4", "en", 100)
    assert seen["spoken"] and seen["video"], "a video can be listened to as well"


def test_the_hosted_door_takes_one_video_and_never_a_channel(tmp_path: Path) -> None:
    """The harvest guard, and the reason this door can be opened at all.

    What makes a hosted fetch defensible is that it is the reader's act: they paste one
    address and press one button. A door that accepted a channel or a playlist would be
    a harvest with a person's name on it, which is the thing #136 weighed and refused.
    `is_youtube` already draws that line; this pins that the paste cannot get round it.

    No stub and no network: the address is turned away before yt-dlp is reached.
    """
    library = Library(tmp_path)
    for address in (
        "https://www.youtube.com/playlist?list=PLabc",
        "https://www.youtube.com/@KhanAcademyHebrew",
        "https://www.youtube.com/c/KhanAcademyHebrew/videos",
        "https://www.youtube.com/channel/UCabc/videos",
        "https://www.youtube.com/feed/subscriptions",
    ):
        job = Job(id="a", source=address)
        library.prepare(job)
        assert job.stage == "failed", address
        assert "one video at a time" in job.error, address
