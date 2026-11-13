"""Where a podcast episode or a video is from, carried from the find to the job, the card
that waits for it and the reader (targum-internal#691; design.md §12, "A suggested text
says where it comes from").

David, 2026-11-13: Home's pick for a podcast episode named its show in one small link to
the bare audio file, and once Listen was pressed the waiting card's title was that file's
address, its tile an "h" from "https", and its badge "Uploaded" for a suggestion.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from test_finds import home, keep  # noqa: F401 - the served fixture, and the pool helper
from test_serve import call, sign_in

from targum import source_line
from targum.accounts import Store
from targum.finds import podcasts, pool, provider
from targum.render.builder import FROM_FILE, from_card, keep_from
from targum.serve import NAMED, Job, Library, named

AUDIO = "https://traffic.omny.fm/d/clips/23f697a0-aaaa/bbbb/cccc/audio.mp3"
PAGE = "https://www.kan.org.il/content/kan/podcasts/p-1234/56789/"
TITLE = "9.11.2026 - השעה הבינלאומית עם ערן סיקורל"
SHOW = "השעה הבינלאומית"


@pytest.fixture
def store(tmp_path: Path) -> Store:
    return Store(tmp_path / "targum.db")


def episode(store: Store, **more: Any) -> int:
    fields: dict[str, Any] = {
        "language": "he",
        "source": "podcast",
        "url": AUDIO,
        "bag": {"בית": 95, "ספר": 5},
        "tokens": 100,
        "unresolved": 0,
        "rung": 3,
        "title": TITLE,
        "host": "kan.org.il",
        "publisher": SHOW,
        "medium": "podcast",
        "seconds": 48 * 60.0,
        "published": 1794211200000,
    }
    fields.update(more)
    return pool.add(store, **fields)


# -- the pool: the episode's page and who makes the show ------------------------------


def test_a_podcast_find_keeps_its_page_and_who_makes_the_show(store: Store) -> None:
    found = episode(store, page=PAGE, author="כאן")
    got = pool.get(store, found)
    assert got is not None and got.page == PAGE and got.author == "כאן"
    assert episode(store, url=AUDIO + "?2", page="javascript:alert(1)") > 0
    other = pool.get(store, found + 1)
    assert other is not None and other.page == "", "only a web address is kept"


def test_a_feed_item_link_is_the_page_unless_it_is_the_audio_again() -> None:
    assert podcasts._page(PAGE, AUDIO) == PAGE
    assert podcasts._page(AUDIO, AUDIO) == ""
    assert podcasts._page("", AUDIO) == ""


def test_a_find_kept_before_the_author_column_reads_it_off_the_reviewed_list(
    store: Store,
) -> None:
    """The International Hour is Kan's, as `podcasts.json` says."""
    found = pool.get(store, episode(store))
    assert found is not None and found.author == ""
    scored = provider.Scored(find=found, share=0.95)
    row = provider.row(scored)
    assert row["author"] == "כאן" and row["publisher"] == SHOW and row["page"] == ""


# -- Home's line --------------------------------------------------------------------


def test_the_line_names_the_show_who_and_links_the_episode_page() -> None:
    line = source_line.for_find(
        {"find": 1, "publisher": SHOW, "author": "כאן", "url": AUDIO, "page": PAGE, "published": 5}
    )
    assert line == {"name": SHOW, "url": PAGE, "date": 5, "by": "כאן"}
    # No page kept: the audio, as before; and who is not said twice.
    line = source_line.for_find(
        {"find": 1, "publisher": "Geekonomy", "author": "geekonomy", "url": AUDIO}
    )
    assert line == {"name": "Geekonomy", "url": AUDIO, "date": 0}


# -- the job: its title, where it came from and what it is from ----------------------


def test_named_keeps_only_what_is_said_and_only_a_web_page() -> None:
    assert named(show=SHOW, by="כאן", date=5, page=PAGE) == {
        "show": SHOW,
        "by": "כאן",
        "date": 5,
        "page": PAGE,
    }
    assert named(show=SHOW, by=SHOW, page="javascript:x") == {"show": SHOW}
    assert named() == {}


def test_a_waiting_build_says_where_it_came_from() -> None:
    def came(**fields: Any) -> str:
        return str(Job(id="j", source=AUDIO, **fields).state()["came"])

    assert came(options={"via": "find"}) == "suggested"
    assert came(options={"via": "subscription"}) == "subscribed"
    assert came(kind="subscription") == "subscribed"
    assert came() == "uploaded"
    state = Job(id="j", source=AUDIO, options={NAMED: named(show=SHOW, by="כאן")}).state()
    assert state["show"] == SHOW and state["by"] == "כאן"


def test_an_audio_link_with_a_known_title_keeps_it_through_its_price(tmp_path: Path) -> None:
    """`_prepare_episode` named an audio address by the address, so the card waiting for
    a suggested episode showed `https://traffic.omny.fm/…`."""
    library = Library(tmp_path / "out")
    job = Job(id="j", source=AUDIO, title=TITLE, options={"from": "he"})
    library.prepare(job)
    assert job.title == TITLE
    bare = Job(id="k", source=AUDIO, options={"from": "he"})
    library.prepare(bare)
    assert bare.title == AUDIO, "nothing known, nothing invented"


def test_listen_on_a_podcast_find_carries_its_title_and_show_into_the_job(
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
    found = episode(home.store, page=PAGE, author="כאן", credits=48)
    status, got, _ = call(home.port, "POST", f"/finds/{found}/open", {}, cookie=cookie)
    assert status == 200 and got["pressed"] is True, got
    assert got["title"] == TITLE and got["came"] == "suggested"
    assert got["show"] == SHOW and got["by"] == "כאן"
    job = pressed[0]
    assert job.options[NAMED] == {"show": SHOW, "by": "כאן", "date": 1794211200000, "page": PAGE}


def test_a_prepare_request_cannot_name_its_own_source(
    home: Any,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cookie = sign_in(home.port, home.postbox)
    seen: list[Any] = []

    def prepare(job: Any) -> None:
        seen.append(job)
        job.stage = "ready"

    monkeypatch.setattr(home.library, "prepare", prepare)
    answered = call(
        home.port,
        "POST",
        "/prepare",
        {"source": "https://news.example/a", NAMED: {"show": "x", "page": "https://evil.example/"}},
        cookie=cookie,
    )
    assert seen and NAMED not in seen[0].options, answered


def test_a_prepare_request_cannot_say_it_came_from_a_find_or_a_subscription(
    home: Any,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`via`, `find`, `subscription` and `item` are the server's to write (targum-internal
    #706): a reader who posted `find: N` could have any shared find retired for everyone
    by making their own link fail, and `via: "find"` alone counted as a find opened."""
    found = episode(home.store)
    cookie = sign_in(home.port, home.postbox)
    seen: list[Any] = []

    def prepare(job: Any) -> None:
        seen.append(job)
        job.stage = "ready"

    monkeypatch.setattr(home.library, "prepare", prepare)
    answered = call(
        home.port,
        "POST",
        "/prepare",
        {
            "source": "https://news.example/mine",
            "via": "find",
            "find": found,
            "subscription": 1,
            "item": "x",
            "to": "en",
        },
        cookie=cookie,
    )
    assert seen, answered
    options = seen[0].options
    assert not {"via", "find", "subscription", "item"} & set(options), options
    assert options.get("to") == "en", "what the Add page sends is kept"


#: What `Library.run` acts on before the source, each written by the server at its own
#: route and never sent by a page (qa-claude on targum#1209).
SERVER_WRITES = {
    "voice": True,
    "folder": "someone-else",
    "section": 3,
    "parts": [2],
    "chapters": True,
    "cover": True,
    "plan": "x",
    "words_again": True,
    "again": ["s1"],
    "rewrite": {"rung": 1},
    "rewritten": "/etc/passwd",
    "transcript": "/etc/passwd",
    "post": {"kept": "/etc/passwd"},
    "pdf_pages": [1],
    "door": "x",
}


def test_a_prepare_request_keeps_only_what_a_page_sends(
    home: Any,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`/prepare` keeps an allow-list (targum-internal#706): `voice` with a `folder` and
    a `section` made a build that claimed nothing for its seconds and voiced the section
    in `Library.run`, past `/voice`'s own claim. A forged voice build is a plain build of
    the link it names, priced as one."""
    cookie = sign_in(home.port, home.postbox)
    seen: list[Any] = []

    def prepare(job: Any) -> None:
        seen.append(job)
        job.stage = "ready"

    monkeypatch.setattr(home.library, "prepare", prepare)
    answered = call(
        home.port,
        "POST",
        "/prepare",
        {"source": "https://news.example/cheap", "to": "en", "words": True, **SERVER_WRITES},
        cookie=cookie,
    )
    assert seen, answered
    options = seen[0].options
    assert not set(SERVER_WRITES) & set(options), options
    assert options == {"source": "https://news.example/cheap", "to": "en", "words": True}

    # A glossary of the whole text is never priced by the quote, so it is never bought
    # from here either: the field a page sends stays, and always says no.
    seen.clear()
    call(
        home.port,
        "POST",
        "/prepare",
        {"source": "https://news.example/cheap", "to": "en", "gloss": True},
        cookie=cookie,
    )
    assert seen and seen[0].options["gloss"] is False, seen[0].options
    assert seen[0].kind == "build" and home.library.stoppable(seen[0]), "nothing run acts on first"


# -- the reader: what it is from, beside it ------------------------------------------


def test_from_json_is_kept_beside_the_reader_and_read_back_for_its_head(tmp_path: Path) -> None:
    keep_from(tmp_path, named(show=SHOW, by="כאן", date=1794211200000, page=PAGE))
    said = json.loads((tmp_path / FROM_FILE).read_text(encoding="utf-8"))
    assert said == {"show": SHOW, "by": "כאן", "date": 1794211200000, "page": PAGE}
    head = from_card(tmp_path, "en")
    assert head == {
        "show": SHOW,
        "presenter": "",
        "by": "כאן",
        "letter": "ה",
        "day": "9 November 2026",
        "stamp": "2026-11-09",
        "page": PAGE,
    }
    keep_from(tmp_path / "none", {"by": "כאן"})
    assert not (tmp_path / "none" / FROM_FILE).exists(), "nothing without a show"
    assert from_card(tmp_path / "none", "en") is None
