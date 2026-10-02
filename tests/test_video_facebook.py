"""The Facebook door: direct once, then the proxy, and a title that is not a count
(2026-09-30)."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest

from targum.errors import TargumError
from targum.video import facebook, youtube

REEL = "https://www.facebook.com/reel/1445068414180254/"
HOME = "https://www.facebook.com/watch/?v=1445068414180254"
FORBIDDEN = b"ERROR: [facebook] 1445068414180254: HTTP Error 403: Forbidden\n"
#: What the box heard directly on every reel the afternoon of 2026-09-30.
UNPARSED = (
    b"ERROR: [facebook] 1445068414180254: Cannot parse data; please report this issue on "
    b"https://github.com/yt-dlp/yt-dlp/issues\n"
)


@pytest.fixture
def seen(monkeypatch):
    calls: list[list[str]] = []

    def run(args, **kwargs):
        calls.append(list(args))
        answer = {"id": "1445068414180254", "duration": 39.3, "webpage_url": HOME}
        return subprocess.CompletedProcess(args, 0, json.dumps(answer).encode(), b"")

    monkeypatch.setattr(youtube.subprocess, "run", run)
    monkeypatch.setattr(youtube, "ytdlp_available", lambda: (True, "yt-dlp"))
    monkeypatch.setenv(youtube.YTDLP_PROXY_ENV, "socks5://127.0.0.1:1080")
    monkeypatch.setenv(youtube.POT_PROVIDER_ENV, "http://127.0.0.1:4416")
    return calls


def test_every_shape_a_facebook_video_is_shared_in_is_one() -> None:
    """A reel, a watch page and a page's video all reduce to the one prefix — a reel's
    id opens there too (checked from the box, 2026-09-30)."""
    for url in (
        REEL,
        "https://m.facebook.com/reel/1445068414180254",
        "https://www.facebook.com/watch/?v=1445068414180254",
        "https://m.facebook.com/watch/?v=1445068414180254&_rdr",
        "https://www.facebook.com/kannews/videos/1445068414180254/",
        "https://facebook.com/kannews/videos/1445068414180254/?rdid=abc&share_url=x",
    ):
        assert facebook.is_facebook(url), url
        assert facebook.home_url(url) == HOME, url
    for short in (
        "https://www.facebook.com/share/r/15tSkFTgxb/",
        "https://www.facebook.com/share/v/17eDczhKhA/",
        "https://m.facebook.com/share/r/15tSkFTgxb/",
        "https://fb.watch/72TEK5emY-/",
    ):
        assert facebook.is_facebook(short) and facebook.is_short(short), short
        assert facebook.home_url(short) == "", "a short link names no video until followed"


def test_anything_else_is_not_a_facebook_video() -> None:
    for url in (
        "https://www.facebook.com/kannews",
        "https://www.facebook.com/kannews/posts/1445068414180254",
        "https://www.facebook.com/watch/?v=not-a-number",
        "https://www.facebook.com/share/p/15tSkFTgxb/",
        "https://fb.watch/",
        "https://facebook.com.evil.example/reel/1445068414180254",
        "https://www.tiktok.com/@a/video/7123456789012345678",
        "",
    ):
        assert not facebook.is_facebook(url), url
    with pytest.raises(TargumError, match="one video at a time"):
        facebook.is_facebook("https://www.facebook.com/groups/hebrew")


def test_the_home_is_the_films_own_number_wherever_the_link_landed() -> None:
    """A shared `/share/v/` link once landed on a group's post: the address names the
    post, and the answer's id is the film's."""
    group = "https://www.facebook.com/groups/somegroup/permalink/9263929620305536/"
    assert facebook.home_from({"id": "2342010796191740", "webpage_url": group}) == (
        "https://www.facebook.com/watch/?v=2342010796191740"
    )
    assert facebook.home_from({"id": "", "webpage_url": REEL}) == HOME
    assert facebook.home_from({"id": "x", "webpage_url": group}) == ""


def test_the_first_ask_is_direct_and_carries_the_title_rule(seen) -> None:
    facebook.describe(REEL)
    assert seen[0][-1] == REEL
    assert "--proxy" not in seen[0]
    assert "--extractor-args" not in seen[0]
    assert seen[0].count("--parse-metadata") == 2


def test_a_refusal_asks_through_the_proxy_twice_after_the_direct_ask(seen, monkeypatch) -> None:
    def refuse(args, **kwargs):
        seen.append(list(args))
        raise subprocess.CalledProcessError(1, args, stderr=FORBIDDEN)

    monkeypatch.setattr(youtube.subprocess, "run", refuse)
    with pytest.raises(TargumError) as raised:
        facebook.describe(REEL)
    assert len(seen) == 3
    assert "--proxy" not in seen[0]
    for proxied in seen[1:]:
        assert proxied[proxied.index("--proxy") + 1] == "socks5://127.0.0.1:1080"
        assert "--extractor-args" not in proxied
    said = f"{raised.value.message} {raised.value.hint}"
    assert "403" not in said
    assert raised.value.hint == facebook.OTHER_DOOR


@pytest.mark.parametrize("fetching", [False, True])
def test_cannot_parse_data_directly_goes_on_to_the_proxy(
    seen, monkeypatch, tmp_path: Path, fetching: bool
) -> None:
    """The afternoon of 2026-09-30: every reel failed directly with "Cannot parse data"
    and answered through the proxy. It is not a refusal to stop at, at the quote or at
    the fetch."""

    def unparsed_then_answered(args, **kwargs):
        seen.append(list(args))
        if "--proxy" not in args:
            raise subprocess.CalledProcessError(1, args, stderr=UNPARSED)
        (tmp_path / "source.mp4").write_bytes(b"film")
        answer = {"id": "1445068414180254", "duration": 39.3}
        return subprocess.CompletedProcess(args, 0, json.dumps(answer).encode(), b"")

    monkeypatch.setattr(youtube.subprocess, "run", unparsed_then_answered)
    if fetching:
        assert facebook.fetch(REEL, tmp_path) == tmp_path / "source.mp4"
    else:
        assert facebook.describe(REEL)["duration"] == 39.3
    assert len(seen) == 2
    assert "--proxy" not in seen[0] and "--proxy" in seen[1]


def test_without_a_proxy_the_direct_ask_is_made_twice(seen, monkeypatch) -> None:
    monkeypatch.delenv(youtube.YTDLP_PROXY_ENV)

    def unparsed(args, **kwargs):
        seen.append(list(args))
        raise subprocess.CalledProcessError(1, args, stderr=UNPARSED)

    monkeypatch.setattr(youtube.subprocess, "run", unparsed)
    with pytest.raises(TargumError):
        facebook.describe(REEL)
    assert len(seen) == 2 and not any("--proxy" in asked for asked in seen)


def test_a_null_answer_asks_the_next_route_and_is_a_refusal_at_the_end(seen, monkeypatch) -> None:
    """What the proxy said once of five on 2026-09-30: not a crash, and not the last
    word while a route is left to ask."""

    def nothing(args, **kwargs):
        seen.append(list(args))
        return subprocess.CompletedProcess(args, 0, b"null\n", b"")

    monkeypatch.setattr(youtube.subprocess, "run", nothing)
    with pytest.raises(TargumError, match="Facebook wouldn't show us that video"):
        facebook.describe(REEL)
    assert len(seen) == 3

    def then_something(args, **kwargs):
        seen.append(list(args))
        if len(seen) == 1:
            return subprocess.CompletedProcess(args, 0, b"null\n", b"")
        return subprocess.CompletedProcess(args, 0, b'{"id": "1", "duration": 5}', b"")

    seen.clear()
    monkeypatch.setattr(youtube.subprocess, "run", then_something)
    assert facebook.describe(REEL)["duration"] == 5
    assert len(seen) == 2 and "--proxy" in seen[1]


def test_a_stranger_address_never_reaches_the_binary(seen, tmp_path: Path) -> None:
    for url in ("https://example.com/reel/1445068414180254", "https://vimeo.com/76979871"):
        with pytest.raises(TargumError):
            facebook.describe(url)
        with pytest.raises(TargumError):
            facebook.fetch(url, tmp_path)
    assert seen == []


def test_the_fetch_is_direct_titled_and_lands_as_source_mp4(
    seen, monkeypatch, tmp_path: Path
) -> None:
    """The title rule rides the fetch too, where `--embed-metadata` writes the tag the
    ingester reads: the quote and the reader say the same thing."""

    def fetched(args, **kwargs):
        seen.append(list(args))
        (tmp_path / "source.mp4").write_bytes(b"film")
        return subprocess.CompletedProcess(args, 0, b"", b"")

    monkeypatch.setattr(youtube.subprocess, "run", fetched)
    assert facebook.fetch(REEL, tmp_path) == tmp_path / "source.mp4"
    assert "--proxy" not in seen[-1] and "--embed-metadata" in seen[-1]
    assert seen[-1].count("--parse-metadata") == 2
    assert seen[-1][-1] == REEL


def _titled(field: str, value: str) -> str | None:
    """What one of `TITLED`'s steps makes of a field, the way yt-dlp's `--parse-metadata`
    reads it: the named group of a match, or nothing."""
    for at, arg in enumerate(facebook.TITLED):
        if arg == "--parse-metadata" and facebook.TITLED[at + 1].startswith(f"{field}:"):
            found = re.search(facebook.TITLED[at + 1].split(":", 1)[1], value)
            return found.group("title") if found else None
    raise AssertionError(field)


def test_the_counts_come_off_the_title_and_the_caption_names_it() -> None:
    """Recorded from the box on 2026-09-30: yt-dlp's title is a count, the caption, and
    the page."""
    counted = "2.1K views · 43 reactions | כשניקו נבון נפצע קשה בראשו במלחמה | כאן חדשות"
    assert _titled("title", counted) == "כשניקו נבון נפצע קשה בראשו במלחמה | כאן חדשות"
    assert _titled("title", "24K reactions · 43 shares | Emilia | Someone") == "Emilia | Someone"
    assert _titled("title", "12 reactions | שלום") == "שלום"
    assert _titled("title", "TouchOSC Template Makers | Pan & Zoom") is None
    caption = "⁧ כשניקו נבון נפצע קשה בראשו במלחמה בעזה - המשפחה שלו יצאה לקרב משל עצמה."
    long = caption + " שנתיים ושלושה חודשים אחרי הפציעה, המשפחה שלו כבר חוגגת ניצחונות קטנים"
    named = _titled("description", long + "\n\nNofar Moshe Ferdo")
    assert named is not None and len(named) <= 120
    assert named.startswith("כשניקו") and long.startswith("⁧ " + named)
    assert long[len(named) + 2] == " ", "cut at a word, never inside one"
    assert _titled("description", "Pan & Zoom feature.\nMore") == "Pan & Zoom feature."
