"""A news article is never a one-hour episode (targum-internal#736).

An Israel Hayom opinion piece put in a chat set was quoted as a podcast episode of an
hour, 60 credits: its page carries a "listen" button whose <audio> is a machine reading
the article aloud, `episode.find` took that player for an episode, nothing said how long
it ran, and `Library._prepare_episode` stood in an hour. The pages here are saved
fixtures — the publishers' shapes with made-up sentences — and nothing reaches the
network.
"""

from __future__ import annotations

import contextlib
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from targum.audio import episode as episode_module

PAGES = Path(__file__).parent / "fixtures" / "articles"
ISRAEL_HAYOM = "https://www.israelhayom.co.il/opinions/article/21851931"
YNET = "https://www.ynet.co.il/news/article/abc123"
YNET_FEED = "https://www.ynet.co.il/Integration/StoryRss2.xml"
PODCAST = "https://podcast.example/42"
PODCAST_AUDIO = "https://cdn.podcast.example/ep42.mp3"
READ_ALOUD = (
    "https://www.israelhayom.co.il/wp-content/uploads/2026/11/15/speech-21851931-20261115.mp3"
)


def _html(name: str) -> tuple[str, bytes]:
    return ("text/html; charset=utf-8", (PAGES / name).read_bytes())


@contextlib.contextmanager
def _answering(pages: dict[str, tuple[str, bytes]], knocked: list[str]) -> Iterator[None]:
    """The fetch door answered from a table; an address not in it is a failed test, not a
    knock on the world. Every address asked for is written down in `knocked`."""
    from targum.ingest import url as url_module

    class Answer:
        def __init__(self, url: str) -> None:
            knocked.append(url)
            kind, body = pages[url]
            self.status_code = 200
            self.headers = {"content-type": kind, "content-length": str(len(body))}
            self.charset = "utf-8"
            self.encoding = None
            self._body = body

        def iter_content(self, chunk_size: int | None = None) -> Iterator[bytes]:
            yield self._body

        def close(self) -> None:
            return None

    class Client:
        def get(self, url: str, **kwargs: object) -> Answer:
            return Answer(str(url))

    real_session, real_polite = url_module._session, url_module.POLITE_S
    url_module._session = lambda proxy="": Client()  # type: ignore[assignment]
    url_module.POLITE_S = 0.0
    url_module.PAGES.clear()
    episode_module.TIMED.clear()
    try:
        yield
    finally:
        url_module._session = real_session  # type: ignore[assignment]
        url_module.POLITE_S = real_polite
        url_module.PAGES.clear()
        episode_module.TIMED.clear()


@pytest.fixture(autouse=True)
def _no_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    from targum.ingest import url as url_module

    monkeypatch.setattr(url_module, "_reachable", lambda target: None)


def test_an_article_with_a_read_aloud_player_is_not_an_episode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The case as it happened: the player is real audio, served by the publisher, and
    runs about as long as the article's words take to say — the article read by a
    machine (Israel Hayom's ran 258 s for 529 words). The page is an article."""
    from targum.audio import probe

    monkeypatch.setattr(probe, "timed", lambda head, declared: 140.0)
    knocked: list[str] = []
    pages = {ISRAEL_HAYOM: _html("israelhayom-opinion.html"), READ_ALOUD: ("audio/mpeg", b"x")}
    with _answering(pages, knocked):
        assert episode_module.find(ISRAEL_HAYOM) is None
    assert knocked == [ISRAEL_HAYOM, READ_ALOUD], "the page, and the recording's front"


def test_a_read_aloud_nobody_can_time_is_still_the_article() -> None:
    """A recording beside an article that cannot be timed is no evidence of an episode;
    the hour it would have been quoted at was the bug."""
    with _answering({ISRAEL_HAYOM: _html("israelhayom-opinion.html")}, []):
        assert episode_module.find(ISRAEL_HAYOM) is None


def test_an_article_whose_recording_runs_far_past_its_words_is_an_episode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The general rule under the host list: a recording many times longer than the
    article's words take to say is not the article spoken."""
    from targum.audio import probe

    monkeypatch.setattr(probe, "timed", lambda head, declared: 1800.0)
    pages = {ISRAEL_HAYOM: _html("israelhayom-opinion.html"), READ_ALOUD: ("audio/mpeg", b"x")}
    with _answering(pages, []):
        found = episode_module.find(ISRAEL_HAYOM)
    assert found is not None and found.audio_url == READ_ALOUD and found.seconds == 1800.0


def test_a_podcast_page_that_calls_itself_an_article_still_plays(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Streetwise Hebrew on tlv1.fm: Yoast says Article, the show notes run past 200
    words, and the site feed holds only its ten newest posts — so for an older episode
    the feed says nothing. The player is on libsyn, which settles it (qa-claude on
    targum#1265)."""
    from targum.audio import probe

    monkeypatch.setattr(probe, "timed", lambda head, declared: 720.0)
    page = "https://tlv1.fm/streetwise-hebrew/2026/04/01/ep-441/?p=68843"
    audio = "https://traffic.libsyn.com/streetwisehebrew/SWH_Ep441.mp3?_=1"
    with _answering({page: _html("streetwise-episode.html"), audio: ("audio/mpeg", b"x")}, []):
        found = episode_module.find(page)
    assert found is not None
    assert found.audio_url == audio and found.seconds == 720.0


def test_a_list_of_types_is_read_whole_and_an_episode_anywhere_wins() -> None:
    from bs4 import BeautifulSoup

    words = " ".join(["מילה"] * 300)
    html = (
        '<html><head><meta property="og:type" content="article">'
        '<script type="application/ld+json">{"@type":["NewsArticle","PodcastEpisode"]}'
        f"</script></head><body><article><p>{words}</p></article></body></html>"
    )
    assert episode_module._article_words(BeautifulSoup(html, "html.parser"), html) == 0
    plain = html.replace(',"PodcastEpisode"', "")
    assert episode_module._article_words(BeautifulSoup(plain, "html.parser"), plain) >= 200


def test_a_page_named_by_its_query_matches_its_own_item_and_no_other() -> None:
    """WordPress's `?p=` is the page: every post shares the path, so the newest item on
    the path is not this page's."""
    feed = b"""<rss><channel>
      <item><title>newest</title><link>https://tlv1.fm/?p=70000</link>
        <enclosure url="https://cdn.example/70000.mp3" type="audio/mpeg"/></item>
      <item><title>mine</title><link>https://tlv1.fm/?p=68843</link>
        <enclosure url="https://cdn.example/68843.mp3" type="audio/mpeg"/></item>
    </channel></rss>"""
    found = episode_module._from_feed(
        feed, "https://tlv1.fm/", page="https://tlv1.fm/?p=68843&utm_source=x", exact=True
    )
    assert found is not None and found.title == "mine"
    gone = episode_module._from_feed(
        feed, "https://tlv1.fm/", page="https://tlv1.fm/?p=1", exact=True
    )
    assert gone is None


def test_an_untyped_enclosure_with_no_audio_name_is_not_audio() -> None:
    """An image resizer has no suffix; untyped, it is not taken for audio. Typed
    audio/* it is, whatever its name."""
    feed = b"""<rss><channel>
      <item><title>picture</title><link>https://n.example/1</link>
        <enclosure url="https://n.example/img?src=1"/></item>
    </channel></rss>"""
    assert episode_module._from_feed(feed, "https://n.example/") is None
    typed = feed.replace(b'img?src=1"', b'play?id=1" type="audio/mpeg"')
    found = episode_module._from_feed(typed, "https://n.example/")
    assert found is not None and found.audio_url == "https://n.example/play?id=1"


def test_an_article_naming_its_sites_feed_is_not_that_feeds_newest_item() -> None:
    """ynet names its news feed in the head. The feed's items are other stories, and
    their enclosures are pictures — neither is this page's episode."""
    knocked: list[str] = []
    feed = ("application/rss+xml", (PAGES / "ynet-news.rss").read_bytes())
    with _answering({YNET: _html("ynet-article.html"), YNET_FEED: feed}, knocked):
        assert episode_module.find(YNET) is None


def test_a_picture_on_a_feed_item_is_not_audio() -> None:
    """An untyped enclosure passes `feeds._enclosure`; one that names a picture is not
    an episode, even for a page that does not call itself an article."""
    page = (
        '<html><head><title>x</title><link rel="alternate" type="application/rss+xml" '
        f'href="{YNET_FEED}"></head><body><p>short</p></body></html>'
    ).encode()
    feed = ("application/rss+xml", (PAGES / "ynet-news.rss").read_bytes())
    with _answering({"https://site.example/x": ("text/html", page), YNET_FEED: feed}, []):
        assert episode_module.find("https://site.example/x") is None


def test_a_podcast_episode_page_is_still_an_episode_timed_from_its_recording(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A podcast's own page calls itself an article too, and plays. Its show notes are a
    paragraph, so it is still an episode — and how long it runs is read from the
    recording's front rather than guessed, so the quote is its own length."""
    from targum.audio import probe
    from targum.serve import Job, Library
    from targum.translate.anthropic_provider import AnthropicProvider

    monkeypatch.setattr(probe, "timed", lambda head, declared: 1500.0)
    knocked: list[str] = []
    pages = {
        PODCAST: _html("podcast-episode.html"),
        PODCAST_AUDIO: ("audio/mpeg", b"\xff\xfb" * 64),
    }
    with _answering(pages, knocked):
        found = episode_module.find(PODCAST)
    assert found is not None
    assert found.audio_url == PODCAST_AUDIO and found.seconds == 1500.0
    assert knocked == [PODCAST, PODCAST_AUDIO], "the recording's front, once"

    monkeypatch.setattr(AnthropicProvider, "estimate_from_counts", lambda self, t, b: 0.01)
    job = Job(id="p", source=PODCAST, home=tmp_path)
    Library(tmp_path)._prepare_episode(job, found)
    assert job.options["episode"] is True and job.audio
    assert job.seconds == 1500.0, "its own length, not the hour"
    from targum.render.builder import credits_of

    assert credits_of(job.seconds) == 25


def test_a_news_article_in_a_quote_is_priced_as_a_text_in_hebrew(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The quote the chat set made, made again: a text, with no hearing in it and no
    credits, in the language its body is written in — never a word of its title."""
    from targum.serve import Job, Library
    from targum.translate.anthropic_provider import AnthropicProvider

    class Messages:
        @staticmethod
        def count_tokens(**kwargs: Any) -> Any:
            return SimpleNamespace(input_tokens=1000)

    client = SimpleNamespace(messages=Messages())
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    monkeypatch.setattr(AnthropicProvider, "client", lambda self: client)
    monkeypatch.setattr(Library, "_gloss_cost", staticmethod(lambda b, s, buying: (0.0, 0)))

    job = Job(id="ih", source=ISRAEL_HAYOM, home=tmp_path)
    job.options = {"gloss": True, "words": False, "to": "en", "source": ISRAEL_HAYOM}
    knocked: list[str] = []
    pages = {ISRAEL_HAYOM: _html("israelhayom-opinion.html"), READ_ALOUD: ("audio/mpeg", b"x")}
    with _answering(pages, knocked):
        Library(tmp_path).prepare(job)

    assert job.error == "" and job.stage == "ready", job.error
    assert "episode" not in job.options
    assert not job.audio and job.seconds == 0 and job.transcription == 0
    assert job.language == "he"
    assert job.title.startswith("הסכם בדרך")
    assert knocked == [ISRAEL_HAYOM, READ_ALOUD], "read once, and its recording's front"
