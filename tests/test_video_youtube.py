"""The YouTube door: a closed address list, and a binary that does the fetching."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from targum.errors import TargumError
from targum.video import youtube


def test_a_single_video_address_is_recognised() -> None:
    for url in (
        "https://www.youtube.com/watch?v=abc123",
        "https://youtube.com/watch?v=abc123",
        "https://m.youtube.com/watch?v=abc123",
        "https://youtu.be/abc123",
        "https://www.youtube.com/shorts/abc123",
        "https://www.youtube.com/live/abc123",
    ):
        assert youtube.is_youtube(url), url


def test_everything_else_is_not(monkeypatch) -> None:
    for url in (
        "https://example.com/watch?v=abc123",
        "https://vimeo.com/12345",
        "https://www.youtube.com.evil.example/watch?v=abc",
        "ftp://youtube.com/watch?v=abc",
        "https://youtu.be/",
        "sefaria:Ruth",
        "talk.mp4",
    ):
        assert not youtube.is_youtube(url), url


def test_a_playlist_is_refused_by_name() -> None:
    """A playlist is a queue of separate decisions, and a channel is a whole shelf."""
    for url in (
        "https://www.youtube.com/playlist?list=PL123",
        "https://www.youtube.com/channel/UC123",
        "https://www.youtube.com/@somebody",
        "https://www.youtube.com/user/somebody",
    ):
        with pytest.raises(TargumError, match="one video at a time"):
            youtube.is_youtube(url)


def test_fetch_pins_the_arguments_that_guard_it(monkeypatch, tmp_path: Path) -> None:
    """The ceiling, the single video, and the modest format are decided at the
    download, not after it — fetching 1080p to throw away is paying twice."""
    argv: list[str] = []

    def pretend(args, **kwargs):
        argv.extend(args)
        (tmp_path / "source.mp4").write_bytes(b"film")
        return subprocess.CompletedProcess(args, 0, b"", b"")

    monkeypatch.setattr(youtube.subprocess, "run", pretend)
    monkeypatch.setattr(youtube, "ytdlp_available", lambda: (True, "yt-dlp"))
    got = youtube.fetch("https://youtu.be/abc123", tmp_path)
    assert got == tmp_path / "source.mp4"
    assert "--no-playlist" in argv
    assert "--max-filesize" in argv
    assert "--merge-output-format" in argv and "mp4" in argv
    assert any("height<=480" in part for part in argv), "the format is chosen at the download"


def test_a_stranger_address_never_reaches_the_binary(monkeypatch, tmp_path: Path) -> None:
    def explode(args, **kwargs):
        raise AssertionError("yt-dlp was handed an address outside the allowlist")

    monkeypatch.setattr(youtube.subprocess, "run", explode)
    with pytest.raises(TargumError, match="not a YouTube video"):
        youtube.fetch("https://example.com/watch?v=abc", tmp_path)


def test_a_missing_binary_is_a_sentence_not_a_traceback(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(youtube, "ytdlp_available", lambda: (False, "install yt-dlp."))
    with pytest.raises(TargumError, match="yt-dlp is not installed"):
        youtube.fetch("https://youtu.be/abc123", tmp_path)


def test_a_binary_that_vanishes_mid_call_is_the_same_sentence(monkeypatch, tmp_path: Path) -> None:
    def gone(args, **kwargs):
        raise OSError("no such file")

    monkeypatch.setattr(youtube.subprocess, "run", gone)
    monkeypatch.setattr(youtube, "ytdlp_available", lambda: (True, "yt-dlp"))
    with pytest.raises(TargumError, match="yt-dlp is not installed"):
        youtube.fetch("https://youtu.be/abc123", tmp_path)


def test_a_fetch_that_merges_nothing_is_refused(monkeypatch, tmp_path: Path) -> None:
    """yt-dlp can exit zero without producing the mp4 the pipeline expects."""

    def pretend(args, **kwargs):
        return subprocess.CompletedProcess(args, 0, b"", b"")

    monkeypatch.setattr(youtube.subprocess, "run", pretend)
    monkeypatch.setattr(youtube, "ytdlp_available", lambda: (True, "yt-dlp"))
    with pytest.raises(TargumError, match="fetched nothing"):
        youtube.fetch("https://youtu.be/abc123", tmp_path)


def test_an_oversized_fetch_is_deleted_not_kept(monkeypatch, tmp_path: Path) -> None:
    """--max-filesize is advisory on some formats; the check after the download is
    the one that holds, and it must not leave the oversized file behind."""

    def pretend(args, **kwargs):
        (tmp_path / "source.mp4").write_bytes(b"film")
        return subprocess.CompletedProcess(args, 0, b"", b"")

    monkeypatch.setattr(youtube.subprocess, "run", pretend)
    monkeypatch.setattr(youtube, "ytdlp_available", lambda: (True, "yt-dlp"))
    monkeypatch.setattr(youtube, "MAX_VIDEO_BYTES", 2)
    with pytest.raises(TargumError, match="larger than"):
        youtube.fetch("https://youtu.be/abc123", tmp_path)
    assert not (tmp_path / "source.mp4").exists()


def test_ytdlps_own_last_line_is_the_error(monkeypatch, tmp_path: Path) -> None:
    """An age gate or a region block: the binary's sentence is the honest one."""

    def refuse(args, **kwargs):
        raise subprocess.CalledProcessError(
            1, args, stderr=b"WARNING: something\nERROR: Private video.\n"
        )

    monkeypatch.setattr(youtube.subprocess, "run", refuse)
    monkeypatch.setattr(youtube, "ytdlp_available", lambda: (True, "yt-dlp"))
    with pytest.raises(TargumError, match="Private video"):
        youtube.fetch("https://youtu.be/abc123", tmp_path)


def test_every_spelling_of_a_video_has_one_home() -> None:
    """The reader carries one address for a video however it was pasted, because the
    allowlist in `test_render.py` pins outbound links by prefix and a prefix is one
    string — and because `&t=` is appended to it without asking what it already has."""
    home = "https://www.youtube.com/watch?v=abc123"
    for url in (
        "https://www.youtube.com/watch?v=abc123",
        "https://www.youtube.com/watch?v=abc123&t=42s&list=PL9",
        "https://youtube.com/watch?v=abc123",
        "https://m.youtube.com/watch?v=abc123",
        "https://youtu.be/abc123",
        "https://youtu.be/abc123?si=share",
        "https://www.youtube.com/shorts/abc123",
        "https://www.youtube.com/live/abc123/",
    ):
        assert youtube.watch_url(url) == home, url
    assert youtube.watch_url(home).startswith(youtube.WATCH)


def test_anything_that_is_not_one_video_has_no_home() -> None:
    for url in (
        "https://example.com/watch?v=abc123",
        "https://www.youtube.com/playlist?list=PL123",
        "https://www.youtube.com/@somebody",
        "https://www.youtube.com/watch",
        "talk.mp4",
        "",
    ):
        assert youtube.watch_url(url) == "", url
