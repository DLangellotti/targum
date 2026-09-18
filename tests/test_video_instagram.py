"""The Instagram door: one reel, through the YouTube door's binary and egress
(targum-internal#255).

Everything here is offline: yt-dlp and ffprobe are both `subprocess.run`, and each test
stands in for them. What was measured against Instagram itself is in `video/instagram.py`.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from targum.errors import TargumError
from targum.video import instagram, youtube

REEL = "https://www.instagram.com/kan_news/reel/DSkLv4UE196/?igsh=abc"

#: What yt-dlp said from the box on 2026-09-17, verbatim, the day #255 was written.
EMPTY = (
    b"ERROR: [Instagram] DSkLv4UE196: Instagram sent an empty media response. Check if "
    b"this post is accessible in your browser without being logged-in. If it is not, then "
    b"use --cookies-from-browser or --cookies for the authentication. See "
    b"https://github.com/yt-dlp/yt-dlp/wiki/FAQ#how-do-i-pass-cookies-to-yt-dlp\n"
)

#: A `yt-dlp -J` answer shaped like the real one: no duration, formats on Meta's CDN.
ANSWER = {
    "id": "DSkLv4UE196",
    "title": "Video by kan_news",
    "duration": None,
    "formats": [
        {"format_id": "dash-a", "acodec": "mp4a.40.5", "url": "https://a.fna.fbcdn.net/o1/a.mp4"},
        {"format_id": "3", "acodec": None, "url": "https://b.fna.fbcdn.net/o1/b.mp4"},
    ],
}


@pytest.fixture(autouse=True)
def no_embed_page(monkeypatch):
    """The backup is a fetch, and no test here may make one: every refusal would otherwise
    fall through to the network and be swallowed as "the backup failed too". A test that
    wants the embed page says what it holds."""

    def offline(url):
        raise TargumError("No embed page in a test.")

    monkeypatch.setattr(instagram, "embedded", offline)


@pytest.fixture
def binary(monkeypatch):
    """yt-dlp answering with `ANSWER` and ffprobe with a length, every call written down."""
    seen: list[list[str]] = []
    state = {"answer": ANSWER, "length": b"49.385375\n"}

    def run(args, **kwargs):
        seen.append(list(args))
        if args[0] == "ffprobe":
            return subprocess.CompletedProcess(args, 0, state["length"], b"")
        return subprocess.CompletedProcess(args, 0, json.dumps(state["answer"]).encode(), b"")

    monkeypatch.setattr(youtube.subprocess, "run", run)
    monkeypatch.setattr(youtube, "ytdlp_available", lambda: (True, "yt-dlp"))
    monkeypatch.delenv(youtube.YTDLP_PROXY_ENV, raising=False)
    monkeypatch.delenv(youtube.POT_PROVIDER_ENV, raising=False)
    return seen, state


def test_a_reel_is_recognised_however_it_was_shared() -> None:
    for url in (
        "https://www.instagram.com/reel/DSkLv4UE196/",
        "https://instagram.com/reels/DSkLv4UE196",
        REEL,
    ):
        assert instagram.is_reel(url), url
        assert instagram.home_url(url) == "https://www.instagram.com/reel/DSkLv4UE196", url
    # A post keeps the `/p/` it was pasted with: `/reel/` opens a film and nothing else.
    post = "https://www.instagram.com/p/DSkLv4UE196/"
    assert instagram.is_reel(post) and instagram.is_post(post)
    assert instagram.home_url(post) == "https://www.instagram.com/p/DSkLv4UE196"
    assert not instagram.is_post(REEL)


def test_anything_else_is_not_a_reel() -> None:
    for url in (
        "https://www.instagram.com/kan_news/",
        "https://www.youtube.com/shorts/abc123xyz",
        "https://www.tiktok.com/@a/video/7123456789012345678",
        "https://instagram.com.evil.example/reel/DSkLv4UE196/",
        "",
    ):
        assert not instagram.is_reel(url), url
        assert instagram.home_url(url) == "", url


def test_a_grid_is_one_video_at_a_time() -> None:
    with pytest.raises(TargumError, match="one video at a time"):
        instagram.is_reel("https://www.instagram.com/explore/tags/tel-aviv/")


def test_a_stranger_address_never_reaches_the_binary(binary, tmp_path: Path) -> None:
    seen, _ = binary
    for url in ("https://example.com/reel/abc123", "https://www.youtube.com/watch?v=abc123"):
        with pytest.raises(TargumError):
            instagram.describe(url)
        with pytest.raises(TargumError):
            instagram.fetch(url, tmp_path)
    assert seen == []


def test_the_egress_rides_and_the_minter_does_not(binary, monkeypatch) -> None:
    """The proxy is every door's. The minter is YouTube's plugin, and Instagram's
    extractor is not handed an argument addressed to it."""
    seen, _ = binary
    monkeypatch.setenv(youtube.YTDLP_PROXY_ENV, "socks5://127.0.0.1:1080")
    monkeypatch.setenv(youtube.POT_PROVIDER_ENV, "http://127.0.0.1:4416")
    instagram.describe(REEL)
    argv = seen[0]
    assert argv[-1] == REEL, "yt-dlp wants the address last"
    assert argv[argv.index("--proxy") + 1] == "socks5://127.0.0.1:1080"
    assert "--extractor-args" not in argv


def test_the_title_is_taken_from_the_caption_on_both_calls(
    binary, monkeypatch, tmp_path: Path
) -> None:
    """ "Video by kan_news" is a byline. The caption's first line is set before the
    tags are written, so the quote and the reader say the same thing."""
    seen, _ = binary

    def fetched(args, **kwargs):
        seen.append(list(args))
        (tmp_path / "source.mp4").write_bytes(b"film")
        return subprocess.CompletedProcess(args, 0, b"", b"")

    instagram.describe(REEL)
    monkeypatch.setattr(youtube.subprocess, "run", fetched)
    instagram.fetch(REEL, tmp_path)
    for argv in (seen[0], seen[-1]):
        assert argv[argv.index("--parse-metadata") + 1].startswith("description:")
    assert "--embed-metadata" in seen[-1]
    assert seen[-1].index("--parse-metadata") < seen[-1].index(REEL)


def test_the_length_instagram_leaves_out_is_read_off_the_header(binary) -> None:
    seen, _ = binary
    assert instagram.describe(REEL)["duration"] == pytest.approx(49.385375)
    probe = seen[1]
    assert probe[0] == "ffprobe"
    assert probe[-1] == "https://a.fna.fbcdn.net/o1/a.mp4"
    assert probe[probe.index("-protocol_whitelist") + 1] == "https,tls,tcp"


def test_the_header_probe_goes_nowhere_but_the_cdn(binary) -> None:
    """The address came out of JSON a platform wrote, and ffprobe is not behind the SSRF
    guard: a format pointing anywhere else is not followed."""
    seen, state = binary
    state["answer"] = dict(
        ANSWER,
        formats=[
            {"url": "http://a.fna.fbcdn.net/o1/a.mp4"},
            {"url": "https://169.254.169.254/latest/meta-data"},
            {"url": "https://fbcdn.net.evil.example/a.mp4"},
            {"url": "file:///etc/passwd"},
        ],
    )
    assert instagram.describe(REEL)["duration"] == 0.0
    assert [argv[0] for argv in seen] == ["yt-dlp"]


def test_a_length_yt_dlp_did_give_is_not_asked_again(binary) -> None:
    seen, state = binary
    state["answer"] = dict(ANSWER, duration=31.0)
    assert instagram.describe(REEL)["duration"] == 31.0
    assert [argv[0] for argv in seen] == ["yt-dlp"]


def test_a_header_that_will_not_say_leaves_the_length_at_nothing(binary) -> None:
    """Two formats asked and no more; the caller prices the nothing on `GUESS_S`."""
    seen, state = binary
    state["length"] = b"N/A\n"
    state["answer"] = dict(
        ANSWER, formats=[{"url": f"https://x{n}.fbcdn.net/v.mp4"} for n in range(5)]
    )
    assert instagram.describe(REEL)["duration"] == 0.0
    assert [argv[0] for argv in seen].count("ffprobe") == instagram.PROBES


def test_an_empty_answer_earns_one_more_exit_and_no_more(monkeypatch) -> None:
    """The refusal of 2026-09-17 did not come back the next day: worth a second process,
    which through the proxy is a second address. A third would be asking twice."""
    calls: list[list[str]] = []

    def refuse(args, **kwargs):
        calls.append(list(args))
        raise subprocess.CalledProcessError(1, args, stderr=EMPTY)

    monkeypatch.setattr(youtube.subprocess, "run", refuse)
    monkeypatch.setattr(youtube, "ytdlp_available", lambda: (True, "yt-dlp"))
    with pytest.raises(TargumError) as raised:
        instagram.describe(REEL)
    assert len(calls) == 2
    said = f"{raised.value.message} {raised.value.hint or ''}"
    # Instagram's sentence is written for somebody logged in; the reader gets ours.
    for leak in ("--cookies", "http", "logged-in", "browser"):
        assert leak not in said, f"{leak!r} reached the reader in {said!r}"
    assert raised.value.hint == instagram.OTHER_DOOR


def test_a_second_try_that_answers_is_the_answer(binary, monkeypatch) -> None:
    seen, _ = binary
    answered = youtube.subprocess.run
    tries = {"n": 0}

    def flaky(args, **kwargs):
        tries["n"] += 1
        if tries["n"] == 1:
            raise subprocess.CalledProcessError(1, args, stderr=EMPTY)
        return answered(args, **kwargs)

    monkeypatch.setattr(youtube.subprocess, "run", flaky)
    assert instagram.describe(REEL)["id"] == "DSkLv4UE196"


def test_any_other_refusal_is_not_retried(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def refuse(args, **kwargs):
        calls.append(list(args))
        raise subprocess.CalledProcessError(1, args, stderr=b"ERROR: [Instagram] x: Private\n")

    monkeypatch.setattr(youtube.subprocess, "run", refuse)
    monkeypatch.setattr(youtube, "ytdlp_available", lambda: (True, "yt-dlp"))
    with pytest.raises(TargumError):
        instagram.fetch(REEL, tmp_path)
    assert len(calls) == 1


"""--- the embed page: the reel's backup, and the only way in for a post ---"""


def page_with(media: dict | None) -> str:
    """An embed page as Instagram writes one: the post as JSON inside a JSON string."""
    context = json.dumps({"context": {}, "gql_data": {"shortcode_media": media}} if media else None)
    return f'<html><script>requireLazy([],{{"contextJSON":{json.dumps(context)}}})</script></html>'


CAPTION = {"edges": [{"node": {"text": "\u2068\t\u2068\tשלום עולם\n\nשורה שנייה\u2069"}}]}
FILM = {
    "__typename": "GraphVideo",
    "shortcode": "DSkLv4UE196",
    "is_video": True,
    "video_url": "https://a.fna.fbcdn.net/o1/v/film.mp4?x=1",
    "video_duration": 49.28,
    "owner": {"username": "kan_news"},
    "edge_media_to_caption": CAPTION,
}
CAROUSEL = {
    "__typename": "GraphSidecar",
    "is_video": False,
    "owner": {"username": "aviv.bahar"},
    "edge_media_to_caption": CAPTION,
    "edge_sidecar_to_children": {
        "edges": [
            {"node": {"is_video": False, "display_url": "https://a.fna.fbcdn.net/one.jpg"}},
            {"node": {"is_video": True, "display_url": "https://a.fna.fbcdn.net/film.jpg"}},
            {"node": {"is_video": False, "display_url": "https://evil.example/two.jpg"}},
            {"node": {"is_video": False, "display_url": "https://b.cdninstagram.com/three.jpg"}},
        ]
    },
}
#: A single picture: no data, only markup — the shape measured on 2026-09-18.
MARKUP = (
    '<div class="Caption"><a class="CaptionUsername" href="x">aviv.bahar</a><br /><br />'
    'פוסט יום הולדת<br />שורה &amp; עוד<div class="CaptionComments">8 comments</div></div>'
    '<img class="EmbeddedMediaImage" alt="x" src="https://a.fna.fbcdn.net/small.jpg" '
    'srcset="https://a.fna.fbcdn.net/small.jpg 150w,https://a.fna.fbcdn.net/big.jpg 1080w" />'
    '"contextJSON":null'
)


def test_a_reel_is_read_off_its_embed_page() -> None:
    post = instagram.read_embed(page_with(FILM), "DSkLv4UE196")
    assert post.video == FILM["video_url"] and post.duration == 49.28
    assert post.author == "kan_news"
    assert post.title == "שלום עולם", "the marks Instagram wraps a caption in are not a title"


def test_a_carousel_keeps_its_pictures_in_order_and_only_meta_s() -> None:
    post = instagram.read_embed(page_with(CAROUSEL), "DdCARhLDF-P")
    assert not post.video
    assert post.pictures == (
        "https://a.fna.fbcdn.net/one.jpg",
        "https://b.cdninstagram.com/three.jpg",
    )


def test_a_single_picture_is_read_off_the_markup() -> None:
    post = instagram.read_embed(MARKUP, "Csx-rFztGlE")
    assert post.author == "aviv.bahar"
    assert post.caption == "פוסט יום הולדת\nשורה & עוד"
    assert post.pictures == ("https://a.fna.fbcdn.net/big.jpg",), "the widest rendition"


def test_a_film_off_the_cdn_is_not_a_film() -> None:
    post = instagram.read_embed(page_with({**FILM, "video_url": "https://evil.example/f.mp4"}), "x")
    assert not post.video


def test_the_caption_becomes_a_text_with_its_author() -> None:
    from targum.ingest.base import parse_frontmatter

    post = instagram.read_embed(page_with(CAROUSEL), "DdCARhLDF-P")
    fields, body = parse_frontmatter(instagram.caption_text(post))
    assert fields == {"title": "שלום עולם", "author": "@aviv.bahar"}
    assert body.strip() == "שלום עולם\n\nשורה שנייה"


def test_when_yt_dlp_is_refused_the_reel_is_described_from_its_embed_page(monkeypatch) -> None:
    def refuse(args, **kwargs):
        raise subprocess.CalledProcessError(1, args, stderr=EMPTY)

    monkeypatch.setattr(youtube.subprocess, "run", refuse)
    monkeypatch.setattr(youtube, "ytdlp_available", lambda: (True, "yt-dlp"))
    monkeypatch.setattr(
        instagram, "embedded", lambda url: instagram.read_embed(page_with(FILM), "DSkLv4UE196")
    )
    info = instagram.describe(REEL)
    assert info["duration"] == 49.28 and info["title"] == "שלום עולם"
    assert info["webpage_url"] == "https://www.instagram.com/reel/DSkLv4UE196"


def test_when_the_backup_fails_too_the_first_refusal_stands(monkeypatch) -> None:
    def refuse(args, **kwargs):
        raise subprocess.CalledProcessError(1, args, stderr=EMPTY)

    def down(url):
        raise TargumError("The page did not answer.")

    monkeypatch.setattr(youtube.subprocess, "run", refuse)
    monkeypatch.setattr(youtube, "ytdlp_available", lambda: (True, "yt-dlp"))
    monkeypatch.setattr(instagram, "embedded", down)
    with pytest.raises(TargumError) as raised:
        instagram.describe(REEL)
    assert raised.value.hint == instagram.OTHER_DOOR


def test_when_yt_dlp_cannot_fetch_the_film_comes_from_the_embed_page(
    monkeypatch, tmp_path: Path
) -> None:
    """Downloaded through the guarded door and tagged, so the reader is titled from the
    caption and bylined to the account exactly as yt-dlp's copy would have been."""
    import targum.ingest.url as url_module

    ran: list[list[str]] = []

    def run(args, **kwargs):
        ran.append(list(args))
        if args[0] == "yt-dlp":
            raise subprocess.CalledProcessError(1, args, stderr=b"ERROR: [Instagram] x: gone\n")
        Path(args[-1]).write_bytes(b"tagged film")
        return subprocess.CompletedProcess(args, 0, b"", b"")

    pulled: list[str] = []

    def download(url, into, max_bytes=0):
        pulled.append(url)
        into.write_bytes(b"film")

    monkeypatch.setattr(youtube.subprocess, "run", run)
    monkeypatch.setattr(youtube, "ytdlp_available", lambda: (True, "yt-dlp"))
    monkeypatch.setattr(url_module, "download", download)
    monkeypatch.setattr(
        instagram, "embedded", lambda url: instagram.read_embed(page_with(FILM), "DSkLv4UE196")
    )
    got = instagram.fetch(REEL, tmp_path)
    assert got == tmp_path / "source.mp4" and got.read_bytes() == b"tagged film"
    assert pulled == [FILM["video_url"]]
    tagging = ran[-1]
    assert tagging[0] == "ffmpeg"
    assert "title=שלום עולם" in tagging and "artist=kan_news" in tagging
    assert not (tmp_path / "embedded.mp4").exists()


def test_a_post_s_pictures_are_numbered_in_order_and_capped(monkeypatch, tmp_path: Path) -> None:
    import targum.ingest.url as url_module
    from targum.vision import MAX_PAGES

    monkeypatch.setattr(
        url_module, "download", lambda url, into, max_bytes=0: into.write_bytes(url.encode())
    )
    post = instagram.read_embed(page_with(CAROUSEL), "DdCARhLDF-P")
    written = instagram.pictures_into(post, tmp_path / "pictures")
    assert [path.name for path in written] == ["01.jpg", "02.jpg"]
    assert written[1].read_bytes() == b"https://b.cdninstagram.com/three.jpg"
    many = instagram.Post(
        "x", "a", "", pictures=tuple(f"https://a.fbcdn.net/{n}.jpg" for n in range(MAX_PAGES + 1))
    )
    with pytest.raises(TargumError):
        instagram.pictures_into(many, tmp_path / "many")
