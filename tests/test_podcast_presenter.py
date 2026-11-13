"""Who presents a podcast, as its feed says (targum-internal#691, the follow-up to #1197).

#1197 named an episode's show and who makes it (כאן, off the reviewed list) but not who
presents it (ערן סיקורל), because the feed's `itunes:author` was never kept. The pool
keeps it now off the feed it already reads: the item's own where a show has several
presenters, else the channel's. Home's pick, the card waiting for a build and the
reader's head say "presenter · maker". A find kept before it says the maker, as it did.

Every feed here is a fixture and every name synthetic; nothing reaches a network.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from test_finds import home, keep  # noqa: F401 - the served fixture, and the pool helper
from test_finds_podcasts import AT, SHOW, Ears, night, quiet  # noqa: F401 - quiet is autouse
from test_serve import call, sign_in

from targum import source_line
from targum.accounts import Store
from targum.finds import pool, provider
from targum.render.builder import FROM_FILE, from_card, keep_from
from targum.serve import NAMED, Job, named
from targum.weekly import feeds

FIXTURES = Path(__file__).parent / "fixtures" / "podcast_finds"
HOSTS = (FIXTURES / "hosts.xml").read_bytes()
GUEST = "https://audio.example/show/ep-guest.mp3"
CHANNEL = "https://audio.example/show/ep-channel.mp3"


@pytest.fixture
def store(tmp_path: Path) -> Store:
    return Store(tmp_path / "targum.db")


# -- the feed ---------------------------------------------------------------------------


def test_a_feed_says_who_presents_an_item_and_the_show() -> None:
    """The item's own `itunes:author`, as plain text; RSS's `<author>`, an e-mail
    address, is not who presents it, and `itunes:owner` is not either."""
    items = {item.guid: item for item in feeds.parse(HOSTS)}
    assert items["ep-guest"].author == "מגישה אורחת"
    assert items["ep-channel"].author == ""
    assert feeds.author(HOSTS) == "מגיש הערוץ"
    assert feeds.author(b"<not a feed") == ""


def test_a_presenter_is_plain_short_and_has_no_controls() -> None:
    said = feeds.plain_name("<i>ערן</i>\u202e סיקורל\u0000 " + "א" * 400)
    assert said == "ערן סיקורל", "markup, controls and a run-on word are gone"
    assert len(feeds.plain_name("א" * 400)) == feeds.MAX_NAME


# -- the pool -----------------------------------------------------------------------------


def heard_apart(episode: Any) -> Any:
    """whisper, faked: each episode heard as words of its own, so neither is the other's
    double (`news.digest`)."""
    import dataclasses

    from test_finds_podcasts import SAMPLE

    return dataclasses.replace(SAMPLE, text=SAMPLE.text + episode.audio.rsplit("/", 1)[-1])


def test_the_round_keeps_the_item_s_presenter_else_the_channel_s(store: Store) -> None:
    night(store, heard_apart, pull=lambda url: HOSTS)
    kept = {find.url: find for find in pool.pick(store, "he", None, at=AT)}
    assert kept[GUEST].presenter == "מגישה אורחת"
    assert kept[CHANNEL].presenter == "מגיש הערוץ"
    # Who makes the show stays the reviewed list's, a meaning of its own.
    assert kept[GUEST].author == SHOW.publisher


def test_the_pool_caps_a_presenter_and_an_old_row_has_none(store: Store) -> None:
    fields: dict[str, Any] = {
        "language": "he",
        "source": "podcast",
        "bag": {"בית": 95, "ספר": 5},
        "tokens": 100,
        "unresolved": 0,
        "rung": 3,
        "title": "פרק",
        "host": "kan.org.il",
        "publisher": "השעה הבינלאומית",
        "medium": "podcast",
        "seconds": 1800.0,
    }
    long = pool.get(store, pool.add(store, url=GUEST, presenter="א" * 500, **fields))
    assert long is not None and len(long.presenter) <= feeds.MAX_NAME
    old = pool.get(store, pool.add(store, url=CHANNEL, **fields))
    assert old is not None and old.presenter == ""


# -- Home's line --------------------------------------------------------------------------


def row(**more: Any) -> dict[str, Any]:
    return {
        "find": 1,
        "publisher": "השעה הבינלאומית",
        "author": "כאן",
        "url": GUEST,
        "published": 5,
        **more,
    }


def test_the_line_names_the_presenter_before_the_maker() -> None:
    line = source_line.for_find(row(presenter="ערן סיקורל"))
    assert line == {
        "name": "השעה הבינלאומית",
        "url": GUEST,
        "date": 5,
        "presenter": "ערן סיקורל",
        "by": "כאן",
    }
    # Kept before the presenter was: the maker, as #1197 said it.
    assert "presenter" not in (source_line.for_find(row()) or {})


@pytest.mark.parametrize(
    "said",
    ["כאן", "כאן | תאגיד השידור הישראלי", "השעה הבינלאומית", "  "],
)
def test_a_presenter_that_is_the_maker_or_the_show_is_not_said_twice(said: str) -> None:
    assert "presenter" not in (source_line.for_find(row(presenter=said)) or {})
    assert source_line.presenter_of(said, show="השעה הבינלאומית", by="כאן") == ""


def test_a_find_s_row_carries_its_presenter(store: Store) -> None:
    night(store, heard_apart, pull=lambda url: HOSTS)
    find = next(f for f in pool.pick(store, "he", None, at=AT) if f.url == GUEST)
    got = provider.row(provider.Scored(find, 0.95))
    assert got["presenter"] == "מגישה אורחת" and got["author"] == SHOW.publisher


# -- the job and the card waiting for it ---------------------------------------------------


def test_named_and_the_waiting_card_carry_the_presenter() -> None:
    said = named(show="השעה הבינלאומית", presenter="ערן סיקורל", by="כאן")
    assert said == {"show": "השעה הבינלאומית", "presenter": "ערן סיקורל", "by": "כאן"}
    assert "presenter" not in named(show="השעה הבינלאומית", presenter="כאן", by="כאן")
    state = Job(id="j", source=GUEST, options={NAMED: said}).state()
    assert state["presenter"] == "ערן סיקורל" and state["by"] == "כאן"
    assert Job(id="k", source=GUEST).state()["presenter"] == ""


def test_listen_carries_the_presenter_into_the_job(
    home: Any,  # noqa: F811 - the fixture imported above
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cookie = sign_in(home.port, home.postbox)
    pressed: list[Any] = []

    def prepare(job: Any) -> None:
        job.stage = "ready"

    def press(job: Any) -> str:
        pressed.append(job)
        job.stage = "queued"
        return ""

    monkeypatch.setattr(home.library, "prepare", prepare)
    monkeypatch.setattr(home.library, "press", press)
    found = pool.add(
        home.store,
        language="he",
        source="podcast",
        url=GUEST,
        bag={"בית": 95, "ספר": 5},
        tokens=100,
        unresolved=0,
        rung=3,
        title="פרק",
        host="kan.org.il",
        publisher="השעה הבינלאומית",
        medium="podcast",
        seconds=48 * 60.0,
        credits=48,
        author="כאן",
        presenter="ערן סיקורל",
    )
    status, got, _ = call(home.port, "POST", f"/finds/{found}/open", {}, cookie=cookie)
    assert status == 200 and got["pressed"] is True, got
    assert got["presenter"] == "ערן סיקורל" and got["by"] == "כאן"
    assert pressed[0].options[NAMED]["presenter"] == "ערן סיקורל"


# -- the reader's head ---------------------------------------------------------------------


def test_from_json_keeps_the_presenter_and_the_head_says_it(tmp_path: Path) -> None:
    keep_from(tmp_path, named(show="השעה הבינלאומית", presenter="ערן סיקורל", by="כאן"))
    head = from_card(tmp_path, "en")
    assert head is not None
    assert head["presenter"] == "ערן סיקורל" and head["by"] == "כאן"
    # A from.json written before it: the maker, as it was.
    (tmp_path / FROM_FILE).write_text('{"show": "השעה הבינלאומית", "by": "כאן"}', "utf-8")
    head = from_card(tmp_path, "en")
    assert head is not None and head["presenter"] == "" and head["by"] == "כאן"
