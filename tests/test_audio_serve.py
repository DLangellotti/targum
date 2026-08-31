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


def test_a_pasted_youtube_link_is_refused_by_name(tmp_path: Path) -> None:
    """The one guard between a pasted watch page and the fallback that would read its
    show notes as the text. Refused before any fetch — no network in this test."""
    library = Library(tmp_path)
    job = Job(id="a", source="https://www.youtube.com/watch?v=abc123")
    library.prepare(job)
    assert job.stage == "failed"
    assert "command line" in job.error


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
