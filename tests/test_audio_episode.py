"""One podcast episode, found from whatever address a reader had in hand."""

from __future__ import annotations

import contextlib
from collections.abc import Iterator

import httpx
import pytest

from targum.audio.episode import find, sounds_like_audio
from targum.weekly.feeds import parse

FEED = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd"
     xmlns:podcast="https://podcastindex.org/namespace/1.0">
  <channel><title>A show</title>
    <item>
      <title>Episode ten</title>
      <link>https://show.example/10</link>
      <enclosure url="https://cdn.example/ep10.mp3" type="audio/mpeg" length="1"/>
      <podcast:transcript url="https://cdn.example/ep10.vtt" type="text/vtt"/>
      <itunes:duration>1:02:03</itunes:duration>
    </item>
    <item>
      <title>Episode nine</title>
      <enclosure url="https://cdn.example/ep9.mp3" type="audio/mpeg" length="1"/>
    </item>
  </channel>
</rss>"""


def test_a_feed_yields_its_newest_episode_with_audio_transcript_and_length() -> None:
    items = parse(FEED)
    assert items[0].enclosure == "https://cdn.example/ep10.mp3"
    assert items[0].transcript == "https://cdn.example/ep10.vtt"
    assert items[0].transcript_type == "text/vtt"
    assert items[0].seconds == 3723.0


def test_a_feed_without_podcast_tags_still_parses() -> None:
    bare = b"<rss><channel><item><title>t</title></item></channel></rss>"
    items = parse(bare)
    assert items[0].enclosure == ""
    assert items[0].seconds == 0.0


def test_an_audio_address_is_its_own_episode() -> None:
    assert sounds_like_audio("https://cdn.example/ep10.mp3?tracker=1")
    assert not sounds_like_audio("https://show.example/10")
    found = find("https://cdn.example/ep10.mp3")
    assert found is not None and found.audio_url == "https://cdn.example/ep10.mp3"


@contextlib.contextmanager
def _answering(pages: dict[str, tuple[str, bytes]]) -> Iterator[None]:
    """Swap httpx's network for a table, keeping the streaming shape ssrf tests use."""

    class Stream:
        def __init__(self, url: str) -> None:
            kind, body = pages[url]
            self.is_redirect = False
            self.headers = {"Content-Type": kind}
            self.charset_encoding = "utf-8"
            self._body = body

        def raise_for_status(self) -> None:
            return None

        def iter_bytes(self) -> Iterator[bytes]:
            yield self._body

        def __enter__(self) -> Stream:
            return self

        def __exit__(self, *args: object) -> None:
            return None

    real = httpx.Client.stream

    def fake(self: httpx.Client, method: str, url: str, **kwargs: object) -> Stream:
        return Stream(str(url))

    httpx.Client.stream = fake  # type: ignore[method-assign, assignment]
    try:
        yield
    finally:
        httpx.Client.stream = real  # type: ignore[method-assign]


def test_an_episode_page_yields_its_one_enclosure(monkeypatch: pytest.MonkeyPatch) -> None:
    from targum.ingest import url as url_module

    monkeypatch.setattr(url_module, "_reachable", lambda target: None)
    page = """<html><head><title>Ep 10 — A show</title>
      <meta property="og:audio" content="https://cdn.example/ep10.mp3">
      </head><body></body></html>"""
    with _answering({"https://show.example/10": ("text/html", page.encode())}):
        found = find("https://show.example/10")
    assert found is not None
    assert found.audio_url == "https://cdn.example/ep10.mp3"


def test_a_page_with_no_audio_is_not_an_episode(monkeypatch: pytest.MonkeyPatch) -> None:
    """An ordinary article must fall through to the article path, never be eaten."""
    from targum.ingest import url as url_module

    monkeypatch.setattr(url_module, "_reachable", lambda target: None)
    page = "<html><head><title>Just prose</title></head><body><p>words</p></body></html>"
    with _answering({"https://site.example/essay": ("text/html", page.encode())}):
        assert find("https://site.example/essay") is None


def test_a_feed_url_yields_its_episode(monkeypatch: pytest.MonkeyPatch) -> None:
    from targum.ingest import url as url_module

    monkeypatch.setattr(url_module, "_reachable", lambda target: None)
    with _answering({"https://show.example/feed": ("application/rss+xml", FEED)}):
        found = find("https://show.example/feed")
    assert found is not None
    assert found.audio_url == "https://cdn.example/ep10.mp3"
    assert found.seconds == 3723.0


"""--- the download door ---"""


def test_a_download_that_redirects_into_the_private_network_is_refused(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Podtrac chains are the ordinary shape of podcast audio, and any hop in one
    could point inward — every hop is checked, the same as every fetch."""
    import ipaddress
    from urllib.parse import urlparse

    from targum.errors import TargumError
    from targum.ingest import url as url_module
    from targum.ingest.url import download

    def literal_only(target: str) -> None:
        """The real check resolves names; the test's table has no DNS, so only an
        address written as one is judged — which is what the metadata endpoint is."""
        host = urlparse(target).hostname or ""
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            return
        if not address.is_global:
            raise TargumError(f"{host} is on a private network, so targum will not fetch it.")

    monkeypatch.setattr(url_module, "_reachable", literal_only)

    class Redirect:
        is_redirect = True
        headers = {"location": "http://169.254.169.254/latest/meta-data/"}

        def __enter__(self):
            return self

        def __exit__(self, *args: object) -> None:
            return None

    sent: list[str] = []

    def fake(self, method, url, **kwargs):
        sent.append(str(url))
        return Redirect()

    monkeypatch.setattr(httpx.Client, "stream", fake)
    with pytest.raises(TargumError, match="private network"):
        download("https://cdn.example/ep.mp3", tmp_path / "ep.mp3")
    # The second request was never sent.
    assert sent == ["https://cdn.example/ep.mp3"]
    assert not (tmp_path / "ep.mp3").exists()


def test_a_download_that_never_ends_is_cut_off_at_its_own_cap(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from targum.errors import TargumError
    from targum.ingest import url as url_module
    from targum.ingest.url import download

    monkeypatch.setattr(url_module, "_reachable", lambda target: None)

    class Forever:
        is_redirect = False
        headers: dict[str, str] = {}

        def raise_for_status(self) -> None:
            return None

        def iter_bytes(self):
            while True:
                yield b"x" * 65536

        def __enter__(self):
            return self

        def __exit__(self, *args: object) -> None:
            return None

    monkeypatch.setattr(httpx.Client, "stream", lambda self, method, url, **kw: Forever())
    with pytest.raises(TargumError, match="too big"):
        download("https://cdn.example/ep.mp3", tmp_path / "ep.mp3", max_bytes=200_000)
    assert not (tmp_path / "ep.mp3").exists()


def test_a_declared_length_over_the_cap_is_refused_before_a_byte_lands(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from targum.errors import TargumError
    from targum.ingest import url as url_module
    from targum.ingest.url import download

    monkeypatch.setattr(url_module, "_reachable", lambda target: None)

    class Declared:
        is_redirect = False
        headers = {"content-length": str(10**10)}

        def raise_for_status(self) -> None:
            return None

        def iter_bytes(self):
            yield b""

        def __enter__(self):
            return self

        def __exit__(self, *args: object) -> None:
            return None

    monkeypatch.setattr(httpx.Client, "stream", lambda self, method, url, **kw: Declared())
    with pytest.raises(TargumError, match="too big"):
        download("https://cdn.example/ep.mp3", tmp_path / "ep.mp3")


def test_an_apple_podcasts_episode_address_is_resolved_through_the_lookup_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The page is a script that draws itself — no audio tag, no og:audio, no feed
    link — so pasting one used to hand the show notes to the article path."""
    from targum.ingest import url as url_module

    monkeypatch.setattr(url_module, "_reachable", lambda target: None)
    lookup = {
        "results": [
            {"kind": "podcast", "feedUrl": "https://feed.example/rss"},
            {
                "wrapperType": "podcastEpisode",
                "trackId": 1000785309151,
                "trackName": "115: Yair Lapid",
                "episodeUrl": "https://cdn.example/lapid.mp3",
                "trackTimeMillis": 3600000,
            },
            {
                "wrapperType": "podcastEpisode",
                "trackId": 42,
                "trackName": "Another",
                "episodeUrl": "https://cdn.example/other.mp3",
            },
        ]
    }

    class Answer:
        is_redirect = False
        headers = {"Content-Type": "application/json"}
        charset_encoding = "utf-8"

        def raise_for_status(self) -> None:
            return None

        def iter_bytes(self):
            import json as json_lib

            yield json_lib.dumps(lookup).encode()

        def __enter__(self):
            return self

        def __exit__(self, *args: object) -> None:
            return None

    asked: list[str] = []

    def fake(self, method, url, params=None, **kwargs):
        asked.append(str(url))
        assert params and params["id"] == "1551521797"
        return Answer()

    monkeypatch.setattr(httpx.Client, "stream", fake)
    found = find(
        "https://podcasts.apple.com/il/podcast/115-yair-lapid/id1551521797?i=1000785309151"
    )
    assert found is not None
    assert found.audio_url == "https://cdn.example/lapid.mp3"
    assert found.title == "115: Yair Lapid"
    assert found.seconds == 3600.0
    # The lookup API answered; the unreadable page was never fetched.
    assert asked == ["https://itunes.apple.com/lookup"]


def test_a_player_page_that_draws_itself_still_yields_its_embedded_enclosure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from targum.ingest import url as url_module

    monkeypatch.setattr(url_module, "_reachable", lambda target: None)
    page = (
        "<html><head><title>Ep</title></head><body><script>"
        '{"assetUrl":"https:\\/\\/cdn.example\\/ep.mp3?x=1"}'
        "</script></body></html>"
    )
    with _answering({"https://player.example/ep": ("text/html", page.encode())}):
        found = find("https://player.example/ep")
    assert found is not None
    assert found.audio_url == "https://cdn.example/ep.mp3?x=1"


def test_a_player_page_resolves_to_its_own_episode_not_the_feeds_newest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The page often carries only the feed it belongs to, and the newest episode is
    not the one somebody pasted. The items name their own pages; the match wins."""
    from targum.ingest import url as url_module

    monkeypatch.setattr(url_module, "_reachable", lambda target: None)
    feed = b"""<rss><channel>
      <item><title>newest</title><link>https://show.example/300</link>
        <enclosure url="https://cdn.example/300.mp3" type="audio/mpeg"/></item>
      <item><title>the one pasted</title><link>https://show.example/286</link>
        <enclosure url="https://cdn.example/286.mp3" type="audio/mpeg"/></item>
    </channel></rss>"""
    page = (
        "<html><head><title>286</title>"
        '<link rel="alternate" type="application/rss+xml" href="https://show.example/rss">'
        "</head><body></body></html>"
    )
    with _answering(
        {
            "https://show.example/286?x=1": ("text/html", page.encode()),
            "https://show.example/rss": ("application/rss+xml", feed),
        }
    ):
        found = find("https://show.example/286?x=1")
    assert found is not None
    assert found.audio_url == "https://cdn.example/286.mp3"
    assert found.title == "the one pasted"


def test_a_spotify_address_is_refused_with_somewhere_to_go() -> None:
    """Spotify's page offers a one-minute preview as og:audio; a reader handed a
    minute titled as the episode has been lied to."""
    from targum.errors import UnsupportedSource

    with pytest.raises(UnsupportedSource, match="Spotify keeps its audio"):
        find("https://open.spotify.com/episode/3HauBQw2qdSdB3VkBjUJfn")


def test_a_feed_named_only_inside_a_pages_scripts_is_still_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """omny and its cousins write the feed address into embedded JSON and nowhere a
    parser of elements looks."""
    from targum.ingest import url as url_module

    monkeypatch.setattr(url_module, "_reachable", lambda target: None)
    feed = b"""<rss><channel>
      <item><title>mine</title><link>https://omny.example/shows/kis/286</link>
        <enclosure url="https://cdn.example/286.mp3" type="audio/mpeg"/></item>
    </channel></rss>"""
    page = (
        "<html><head><title>286</title></head><body><script>"
        '{"feedUrl":"https://content.example/d/playlist/abc/podcast.rss"}'
        "</script></body></html>"
    )
    with _answering(
        {
            "https://omny.example/shows/kis/286": ("text/html", page.encode()),
            "https://content.example/d/playlist/abc/podcast.rss": (
                "application/rss+xml",
                feed,
            ),
        }
    ):
        found = find("https://omny.example/shows/kis/286")
    assert found is not None
    assert found.audio_url == "https://cdn.example/286.mp3"
