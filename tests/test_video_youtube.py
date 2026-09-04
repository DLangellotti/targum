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
    assert "--embed-metadata" in argv, "without the tags a video is titled after its id"


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


#: What a reader was actually shown on the /add page on 2026-09-04, one line, verbatim.
BOT_CHECK = (
    b"ERROR: [youtube] 7djXzciYGEg: Sign in to confirm you're not a bot. Use "
    b"--cookies-from-browser or --cookies for the authentication. See "
    b"https://github.com/yt-dlp/yt-dlp/wiki/FAQ#how-do-i-pass-cookies-to-yt-dlp for how to "
    b"manually pass cookies. Also see "
    b"https://github.com/yt-dlp/yt-dlp/wiki/Extractors#exporting-youtube-cookies for tips "
    b"on effectively exporting YouTube cookies\n"
)


def _refusing(stderr: bytes):
    def refuse(args, **kwargs):
        raise subprocess.CalledProcessError(1, args, stderr=stderr)

    return refuse


def test_a_note_to_the_operator_is_never_shown_to_a_reader(monkeypatch, tmp_path: Path) -> None:
    """The bot check names flags a reader cannot pass and two wiki pages nobody on the
    /add page is going to read. yt-dlp's sentence is carried where it is a fact about
    the video and dropped where it is addressed to whoever runs the binary."""
    monkeypatch.setattr(youtube.subprocess, "run", _refusing(BOT_CHECK))
    monkeypatch.setattr(youtube, "ytdlp_available", lambda: (True, "yt-dlp"))
    with pytest.raises(TargumError) as raised:
        youtube.describe("https://youtu.be/abc123")
    said = f"{raised.value.message} {raised.value.hint or ''}"
    for leak in ("--cookies", "http", "yt-dlp", "bot"):
        assert leak not in said, f"{leak!r} reached the reader in {said!r}"
    assert youtube.OTHER_DOOR in said, "a reader told nothing is a reader told to leave"


def test_the_same_holds_for_the_download_not_only_the_lookup(monkeypatch, tmp_path: Path) -> None:
    """`describe` is the call the /add page makes and `fetch` is the one the worker
    makes. They had two copies of this logic and only one of them was ever read."""
    monkeypatch.setattr(youtube.subprocess, "run", _refusing(BOT_CHECK))
    monkeypatch.setattr(youtube, "ytdlp_available", lambda: (True, "yt-dlp"))
    with pytest.raises(TargumError) as raised:
        youtube.fetch("https://youtu.be/abc123", tmp_path)
    assert "--cookies" not in raised.value.message
    assert "https://" not in raised.value.message


def test_a_warning_above_the_error_is_not_promoted_to_the_reason(monkeypatch) -> None:
    """Dropping the ERROR line and reading the line above it would hand a reader a
    WARNING as the reason the import stopped, which is a different untruth."""
    stderr = b"WARNING: falling back to something\n" + BOT_CHECK
    monkeypatch.setattr(youtube.subprocess, "run", _refusing(stderr))
    monkeypatch.setattr(youtube, "ytdlp_available", lambda: (True, "yt-dlp"))
    with pytest.raises(TargumError) as raised:
        youtube.describe("https://youtu.be/abc123")
    assert "falling back" not in raised.value.message


def test_a_fact_about_the_video_still_travels_word_for_word(monkeypatch) -> None:
    """The reason the binary's line was ever carried: nothing written here beats it."""
    stderr = b"WARNING: something\nERROR: [youtube] abc123: Video unavailable\n"
    monkeypatch.setattr(youtube.subprocess, "run", _refusing(stderr))
    monkeypatch.setattr(youtube, "ytdlp_available", lambda: (True, "yt-dlp"))
    with pytest.raises(TargumError) as raised:
        youtube.describe("https://youtu.be/abc123")
    assert raised.value.message == "[youtube] abc123: Video unavailable"
    assert not raised.value.hint, "a whole answer does not need a second door named after it"


def test_the_minter_is_named_to_ytdlp_and_the_address_stays_last(monkeypatch) -> None:
    """`_run` reads the address off the end of argv to check it is YouTube's, so
    anything appended has to go in front of it."""
    seen: list[list[str]] = []

    def watch(args, **kwargs):
        seen.append(list(args))
        return subprocess.CompletedProcess(args, 0, b"{}", b"")

    monkeypatch.setattr(youtube.subprocess, "run", watch)
    monkeypatch.setattr(youtube, "ytdlp_available", lambda: (True, "yt-dlp"))
    monkeypatch.setenv(youtube.POT_PROVIDER_ENV, "http://127.0.0.1:4416")
    youtube.describe("https://youtu.be/abc123")
    argv = seen[-1]
    assert argv[-1] == "https://youtu.be/abc123"
    assert "youtubepot-bgutilhttp:base_url=http://127.0.0.1:4416" in argv
    assert argv[argv.index("--extractor-args")] == "--extractor-args"


def test_a_laptop_asks_ytdlp_for_nothing_extra(monkeypatch, tmp_path: Path) -> None:
    """Unset is a home IP, which is proof enough. A flag naming a provider that is not
    running is a fetch that fails on a machine where it used to work."""
    seen: list[list[str]] = []

    def watch(args, **kwargs):
        seen.append(list(args))
        (tmp_path / "source.mp4").write_bytes(b"film")
        return subprocess.CompletedProcess(args, 0, b"", b"")

    monkeypatch.setattr(youtube.subprocess, "run", watch)
    monkeypatch.setattr(youtube, "ytdlp_available", lambda: (True, "yt-dlp"))
    monkeypatch.delenv(youtube.POT_PROVIDER_ENV, raising=False)
    youtube.fetch("https://youtu.be/abc123", tmp_path)
    assert "--extractor-args" not in seen[-1]


def test_the_add_page_never_carries_ytdlps_note_to_the_operator(
    monkeypatch, tmp_path: Path
) -> None:
    """The whole point, at the layer the reader meets.

    `Library.prepare` routes a YouTube paste to `_prepare_youtube`, which joins the
    refusal's message and hint into `job.error` — and `job.error` is the red box on
    /add. On 2026-09-04 that box held `--cookies-from-browser` and two GitHub wiki
    addresses. Everything above this test is machinery; this is the surface.
    """
    from targum.serve import Job, Library

    monkeypatch.setattr(youtube.subprocess, "run", _refusing(BOT_CHECK))
    monkeypatch.setattr(youtube, "ytdlp_available", lambda: (True, "yt-dlp"))
    monkeypatch.setattr("targum.video.ytdlp_available", lambda: (True, "yt-dlp"))

    job = Job(id="a", source="https://www.youtube.com/watch?v=7djXzciYGEg", home=tmp_path)
    Library(tmp_path).prepare(job)

    assert job.stage == "failed"
    for leak in ("--cookies", "http", "yt-dlp", "bot", "wiki"):
        assert leak not in job.error, f"{leak!r} is in the box a reader reads: {job.error!r}"
    assert job.error, "a red box with nothing in it is worse than the sentence it replaced"
    assert "!" not in job.error, "design.md §6: no exclamation marks"


def test_the_egress_is_named_to_ytdlp_and_the_address_stays_last(monkeypatch) -> None:
    """The one knob that answers a flagged datacenter address: the fetch has to leave
    from somewhere YouTube trusts, and nothing installed on the box can substitute."""
    seen: list[list[str]] = []

    def watch(args, **kwargs):
        seen.append(list(args))
        return subprocess.CompletedProcess(args, 0, b"{}", b"")

    monkeypatch.setattr(youtube.subprocess, "run", watch)
    monkeypatch.setattr(youtube, "ytdlp_available", lambda: (True, "yt-dlp"))
    monkeypatch.setenv(youtube.YTDLP_PROXY_ENV, "socks5://127.0.0.1:1080")
    monkeypatch.delenv(youtube.POT_PROVIDER_ENV, raising=False)
    youtube.describe("https://youtu.be/abc123")
    argv = seen[-1]
    assert argv[-1] == "https://youtu.be/abc123", "yt-dlp wants the address last"
    assert argv[argv.index("--proxy") + 1] == "socks5://127.0.0.1:1080"


def test_the_egress_and_the_minter_ride_together(monkeypatch, tmp_path: Path) -> None:
    """Two separate things — where the fetch leaves from, and who mints its token. The
    box needs both, and having one is indistinguishable from having neither."""
    seen: list[list[str]] = []

    def watch(args, **kwargs):
        seen.append(list(args))
        (tmp_path / "source.mp4").write_bytes(b"film")
        return subprocess.CompletedProcess(args, 0, b"", b"")

    monkeypatch.setattr(youtube.subprocess, "run", watch)
    monkeypatch.setattr(youtube, "ytdlp_available", lambda: (True, "yt-dlp"))
    monkeypatch.setenv(youtube.YTDLP_PROXY_ENV, "socks5://127.0.0.1:1080")
    monkeypatch.setenv(youtube.POT_PROVIDER_ENV, "http://127.0.0.1:4416")
    youtube.fetch("https://youtu.be/abc123", tmp_path)
    argv = seen[-1]
    assert "--proxy" in argv and "--extractor-args" in argv


def test_an_unset_egress_is_not_a_flag(monkeypatch) -> None:
    """A laptop's own address is one YouTube trusts. `--proxy` naming nothing would be
    a fetch that fails on the machine where it used to work."""
    seen: list[list[str]] = []

    def watch(args, **kwargs):
        seen.append(list(args))
        return subprocess.CompletedProcess(args, 0, b"{}", b"")

    monkeypatch.setattr(youtube.subprocess, "run", watch)
    monkeypatch.setattr(youtube, "ytdlp_available", lambda: (True, "yt-dlp"))
    monkeypatch.delenv(youtube.YTDLP_PROXY_ENV, raising=False)
    monkeypatch.delenv(youtube.POT_PROVIDER_ENV, raising=False)
    youtube.describe("https://youtu.be/abc123")
    assert seen[-1] == [
        "yt-dlp",
        "-J",
        "--no-playlist",
        "--skip-download",
        "https://youtu.be/abc123",
    ]
