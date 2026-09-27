"""The TikTok door: direct, not through the proxy (targum-internal#255, 2026-09-18)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from targum.errors import TargumError
from targum.video import tiktok, youtube

VIDEO = "https://www.tiktok.com/@yiramne/video/7485073076758007056"
HOME = "https://www.tiktok.com/@/video/7485073076758007056"
BLOCKED = (
    b"ERROR: [TikTok] 7485073076758007056: Your IP address is blocked from accessing this post\n"
)
FORBIDDEN = (
    b"ERROR: [TikTok] 7485073076758007056: Unable to download webpage: HTTP Error 403: Forbidden\n"
)


@pytest.fixture
def seen(monkeypatch):
    calls: list[list[str]] = []

    def run(args, **kwargs):
        calls.append(list(args))
        answer = {"id": "7485073076758007056", "duration": 11, "webpage_url": VIDEO}
        return subprocess.CompletedProcess(args, 0, json.dumps(answer).encode(), b"")

    monkeypatch.setattr(youtube.subprocess, "run", run)
    monkeypatch.setattr(youtube, "ytdlp_available", lambda: (True, "yt-dlp"))
    monkeypatch.setenv(youtube.YTDLP_PROXY_ENV, "socks5://127.0.0.1:1080")
    monkeypatch.setenv(youtube.POT_PROVIDER_ENV, "http://127.0.0.1:4416")
    return calls


def test_every_shape_a_tiktok_is_shared_in_is_one() -> None:
    for url in (
        VIDEO,
        "https://m.tiktok.com/@yiramne/video/7485073076758007056?lang=he-IL",
        HOME,
    ):
        assert tiktok.is_tiktok(url), url
        assert tiktok.home_url(url) == HOME, url
    for short in ("https://vm.tiktok.com/ZMabc123/", "https://www.tiktok.com/t/ZTabc123/"):
        assert tiktok.is_tiktok(short) and tiktok.is_short(short), short
        assert tiktok.home_url(short) == "", "a short link names no video until followed"


def test_anything_else_is_not_a_tiktok() -> None:
    for url in (
        "https://www.tiktok.com/@yiramne",
        "https://www.tiktok.com/@yiramne/photo/7485073076758007056",
        "https://tiktok.com.evil.example/@a/video/7485073076758007056",
        "https://www.youtube.com/shorts/abc123xyz",
        "",
    ):
        assert not tiktok.is_tiktok(url), url
    with pytest.raises(TargumError, match="one video at a time"):
        tiktok.is_tiktok("https://www.tiktok.com/tag/hebrew")


def test_the_first_ask_is_direct_and_never_names_the_minter(seen) -> None:
    """TikTok refuses the proxy's exits and serves the box: direct first."""
    tiktok.describe(VIDEO)
    assert seen[0][-1] == VIDEO
    assert "--proxy" not in seen[0]
    assert "--extractor-args" not in seen[0]


def test_a_refusal_asks_directly_once_more_then_through_the_proxy(seen, monkeypatch) -> None:
    def refuse(args, **kwargs):
        seen.append(list(args))
        raise subprocess.CalledProcessError(1, args, stderr=FORBIDDEN)

    monkeypatch.setattr(youtube.subprocess, "run", refuse)
    with pytest.raises(TargumError) as raised:
        tiktok.describe(VIDEO)
    assert len(seen) == 3
    assert "--proxy" not in seen[0] and "--proxy" not in seen[1]
    assert seen[2][seen[2].index("--proxy") + 1] == "socks5://127.0.0.1:1080"
    assert "--extractor-args" not in seen[2]
    said = f"{raised.value.message} {raised.value.hint}"
    assert "IP address" not in said and "403" not in said
    assert raised.value.hint == tiktok.OTHER_DOOR


def test_a_stranger_address_never_reaches_the_binary(seen, tmp_path: Path) -> None:
    for url in ("https://example.com/@a/video/1234567", "https://vimeo.com/76979871"):
        with pytest.raises(TargumError):
            tiktok.describe(url)
        with pytest.raises(TargumError):
            tiktok.fetch(url, tmp_path)
    assert seen == []


def test_the_fetch_is_direct_and_lands_as_source_mp4(seen, monkeypatch, tmp_path: Path) -> None:
    def fetched(args, **kwargs):
        seen.append(list(args))
        (tmp_path / "source.mp4").write_bytes(b"film")
        return subprocess.CompletedProcess(args, 0, b"", b"")

    monkeypatch.setattr(youtube.subprocess, "run", fetched)
    assert tiktok.fetch(VIDEO, tmp_path) == tmp_path / "source.mp4"
    assert "--proxy" not in seen[-1] and "--embed-metadata" in seen[-1]
