"""Which video addresses targum reads, and the one shape each becomes
(targum-internal#255).

The URL handling is exact and is what these tests cover. Whether yt-dlp can actually
fetch from any of these services is a separate question the card asks to be settled from
the box, through the residential proxy, before this is trusted — and it has not been.

The assertions that matter most are the refusals. A closed host list only means something
if everything outside it is refused, and a canonical `home` only means something if every
spelling of a video reduces to exactly one prefix — `tests/test_render` pins outbound
links by prefix, so a host that produced two shapes would put an unpinned address on a
reader's page.
"""

from __future__ import annotations

import pytest

from targum.errors import TargumError
from targum.video import hosts


def test_youtube_still_works_exactly_as_it_did() -> None:
    """The one host proven end to end. Nothing here may move it."""
    for spelling in (
        "https://www.youtube.com/watch?v=abc123xyz",
        "https://youtu.be/abc123xyz",
        "https://m.youtube.com/watch?v=abc123xyz&t=30",
        "https://www.youtube.com/shorts/abc123xyz",
        "https://www.youtube.com/live/abc123xyz",
    ):
        assert hosts.video_id(spelling) == "abc123xyz", spelling
        assert hosts.home_url(spelling) == "https://www.youtube.com/watch?v=abc123xyz"


def test_every_spelling_of_a_video_becomes_one_address() -> None:
    """The whole reason a host cannot just be added to a set: the allowlist is a prefix."""
    for spellings, wanted in (
        (
            ("https://vimeo.com/76979871", "https://player.vimeo.com/video/76979871"),
            "https://vimeo.com/76979871",
        ),
        (
            (
                "https://www.tiktok.com/@someone/video/7123456789012345678",
                "https://m.tiktok.com/@someone/video/7123456789012345678",
            ),
            "https://www.tiktok.com/video/7123456789012345678",
        ),
        (
            (
                "https://www.instagram.com/reel/Cx3abcDEFgh/",
                "https://instagram.com/reels/Cx3abcDEFgh/",
            ),
            "https://www.instagram.com/reel/Cx3abcDEFgh",
        ),
    ):
        for spelling in spellings:
            assert hosts.home_url(spelling) == wanted, spelling


def test_a_vimeo_unlisted_link_keeps_the_video_not_the_key() -> None:
    """vimeo.com/<id>/<privacy key> — the first number is the video."""
    assert hosts.video_id("https://vimeo.com/76979871/abcdef123") == "76979871"


def test_reddit_takes_the_post_id_from_a_permalink() -> None:
    assert hosts.video_id("https://www.reddit.com/r/aww/comments/1c1ux0h/a_slug_here/") == "1c1ux0h"
    assert hosts.video_id("https://v.redd.it/abcd1234efgh") == "abcd1234efgh"


def test_facebook_reads_its_three_shapes() -> None:
    assert hosts.video_id("https://www.facebook.com/watch/?v=123456789") == "123456789"
    assert hosts.video_id("https://www.facebook.com/somepage/videos/123456789/") == "123456789"
    assert hosts.video_id("https://www.facebook.com/reel/123456789") == "123456789"


def test_a_shelf_is_not_a_video_and_says_so() -> None:
    """A channel, a playlist, a subreddit: a reader to talk to, not a silent refusal."""
    for shelf in (
        "https://www.youtube.com/playlist?list=PL123",
        "https://www.youtube.com/@somebody",
        "https://vimeo.com/channels/staffpicks",
        "https://www.tiktok.com/tag/hebrew",
        "https://www.instagram.com/explore/tags/tel-aviv/",
        "https://www.reddit.com/r/hebrew/",
    ):
        with pytest.raises(TargumError):
            hosts.video_id(shelf)
        # And `home_url` swallows it rather than raising into a page that only wants a
        # link: the refusal belongs where the reader pasted, not where the page is drawn.
        assert hosts.home_url(shelf) == ""


def test_a_host_nobody_decided_on_is_refused() -> None:
    """yt-dlp would happily fetch a thousand sites. The list is the decision."""
    for other in (
        "https://dailymotion.com/video/x8abcde",
        "https://twitter.com/someone/status/123",
        "https://example.com/watch?v=abc123xyz",
        "https://notyoutube.com/watch?v=abc123xyz",
        "file:///etc/passwd",
        "ftp://vimeo.com/76979871",
        "",
    ):
        assert hosts.host_for(other) is None, other
        assert hosts.video_id(other) == ""
        assert hosts.home_url(other) == ""


def test_a_known_host_with_no_video_on_it_is_not_a_video() -> None:
    for bare in (
        "https://www.youtube.com/",
        "https://vimeo.com/",
        "https://www.instagram.com/someone/",
        "https://www.facebook.com/somepage",
    ):
        assert not hosts.is_video(bare), bare
        assert hosts.home_url(bare) == ""


def test_every_host_has_its_own_prefix_and_they_are_all_distinct() -> None:
    """Two hosts sharing a prefix would make the allowlist ambiguous."""
    assert len(set(hosts.HOMES)) == len(hosts.HOMES)
    for home in hosts.HOMES:
        assert home.startswith("https://"), home


def test_the_service_is_named_for_the_line_the_reader_is_shown() -> None:
    assert hosts.named("https://vimeo.com/76979871") == "Vimeo"
    assert hosts.named("https://www.tiktok.com/@a/video/7123456789012345678") == "TikTok"
    assert hosts.named("https://example.com/x") == ""
