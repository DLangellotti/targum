"""An РБК article built from its full-text feed (2026-10-07, targum-internal#424).

www.rbc.ru answers every article with `401`, `server: QRATOR`, a bot check neither the
direct door nor the proxy passes, while its feed carries each article whole. A link a
followed feed carries whole is described and quoted from that feed when its page is
behind the check; any other link is fetched as before. The feed here is fabricated
(`fixtures/feeds/ru-full-text.xml`) and nothing touches the network.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from targum import level
from targum.accounts import Person, Store
from targum.chat import tools
from targum.errors import Unreachable
from targum.ingest import url as url_module
from targum.serve import Library
from targum.weekly import feeds

FIXTURE = Path(__file__).parent / "fixtures" / "feeds" / "ru-full-text.xml"
FEED = "https://rssexport.rbc.ru/rbcnews/news/30/full.rss"
WHOLE = "https://www.rbc.ru/society/07/10/2026/0000000000000000000000a1"
BARE = "https://www.rbc.ru/society/07/10/2026/0000000000000000000000b2"
ELSEWHERE = "https://www.rbc.ru/politics/07/10/2026/0000000000000000000000c3"


def test_a_feed_s_full_text_is_kept_on_its_item_and_clean() -> None:
    items = {item.link: item for item in feeds.parse(FIXTURE.read_bytes())}
    whole = items[WHOLE].full_text
    paragraphs = whole.split("\n\n")
    assert len(paragraphs) == 5, "a line of РБК's plain text is a paragraph"
    assert paragraphs[2].startswith("Кошка пьёт молоко")
    for leftover in ("<", ">", "href", "nbsp", "https"):
        assert leftover not in whole, leftover
    assert "кошка пьёт" in paragraphs[1], "&nbsp; is a space, not six letters"
    assert items[BARE].full_text == ""
    # content:encoded, the common spelling, goes down the same path: a <p> is a
    # paragraph, a link is its words, and a script is nothing.
    assert items["https://wp.example/2026/10/07/derevya"].full_text == (
        "Город посадил деревья.\n\nЖители помогали весь день."
    )
    # The summary is still a hook: the full text is never folded into it.
    assert items[WHOLE].summary == "В городском парке открыли библиотеку."


class Door:
    """The fetch door: the feed answers from the fixture, www.rbc.ru with its bot
    check, and every address asked for is written down."""

    def __init__(self) -> None:
        self.asked: list[str] = []

    def fetch(self, url: str, params: Any = None) -> url_module.Fetched:
        self.asked.append(url)
        if url == FEED:
            return url_module.Fetched(
                text="", content_type="application/rss+xml", raw=FIXTURE.read_bytes()
            )
        raise Unreachable(
            f"We couldn't open {url}.",
            "a bot check, not a page",
            status=401,
            host="www.rbc.ru",
            challenge=True,
        )

    def knocked_on_rbc(self) -> list[str]:
        return [url for url in self.asked if "www.rbc.ru" in url]


@pytest.fixture
def world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Library, Store, Person, Door]:
    sources = tmp_path / "sources.json"
    sources.write_text(
        json.dumps(
            {
                "publishers": [
                    {
                        "key": "rbc",
                        "name": "РБК",
                        "feed": FEED,
                        "language": "ru",
                        "licence": "All rights reserved",
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("TARGUM_SOURCES", str(sources))
    door = Door()
    monkeypatch.setattr(url_module, "fetch", door.fetch)
    store = Store(tmp_path / "words.db")
    out = tmp_path / "out"
    out.mkdir()
    library = Library(out, store=store)
    signed = store.finish_sign_in(store.start_sign_in("reader@example.com"))
    assert signed is not None
    person = signed[0]
    store.push(
        person,
        {
            "words": [
                {"language": "ru", "lemma": w, "surface": w, "status": 9, "at": 1, "seen": 1}
                for w in ("кошка", "собака", "молоко", "хлеб")
            ]
        },
    )
    tools.FEEDS.clear()
    return library, store, person, door


def context(library: Library, store: Store, person: Person) -> tools.Ctx:
    return tools.Ctx(
        person=person,
        home=library.home(person),
        library=library,
        store=store,
        chat_id="c1",
        level=level.snapshot(store, person.id, "ru"),
    )


def test_an_rbc_link_from_search_sources_describes_and_quotes_without_a_knock(world) -> None:
    library, store, person, door = world
    # What the box has known since 2026-10-06: www.rbc.ru is behind a bot check.
    store.reach("www.rbc.ru", False, "bot check")
    ctx = context(library, store, person)
    ctx.reads = {"en"}

    found = tools.search_sources(ctx, {"language": "ru"})
    rows = {row["link"]: row for row in found["items"]}
    assert "host_shut" not in rows[WHOLE], "its text is reachable, from the feed"
    assert rows[BARE].get("host_shut") is True, "no full text, so still shut"
    assert [row["link"] for row in found["items"]][-1] == BARE, "and so last"
    assert door.asked == [FEED]

    described = tools.describe_source(ctx, {"url": WHOLE})
    assert described["kind"] == "article", described
    assert described["title"] == "В парке открыли новую библиотеку"
    assert described["language"] == "ru" and described["russian_share"] > 0.95
    assert described["words"] == 140 and described["minutes"] == 1, "five lines of 28"
    assert described["known_share"] is not None and described["known_share"] > 0.5
    assert described["advice"] == []
    # The licence row exactly as for a fetched article: a reader's own import.
    assert described["licence"] == "" and "reader's own shelf" in described["licence_note"]
    assert described["quote_with"] == WHOLE
    assert door.knocked_on_rbc() == [], "describe never knocked on www.rbc.ru"
    assert store.closed(limit=10) == ["www.rbc.ru"], "the feed is no knock, so no answer"

    quoted = tools.quote_build(ctx, {"source": WHOLE})
    job = library.jobs[quoted["quote"]["id"]]
    assert job.error == "" and job.stage != "failed", job.error
    assert job.title == "В парке открыли новую библиотеку"
    assert job.language == "ru" and job.segments > 0
    assert door.knocked_on_rbc() == [], "nor did the quote"


def test_the_first_knock_after_a_restart_falls_back_to_the_feed(world) -> None:
    """With nothing remembered, the page is knocked on once; its bot check is the answer
    that sends the reader to the feed's text, and the next look does not knock."""
    library, store, person, door = world
    ctx = context(library, store, person)
    tools.search_sources(ctx, {"language": "ru"})

    described = tools.describe_source(ctx, {"url": WHOLE})
    assert described["kind"] == "article" and described["language"] == "ru"
    assert door.knocked_on_rbc() == [WHOLE], "once, refused"

    url_module.PAGES.clear()
    again = tools.describe_source(ctx, {"url": WHOLE})
    assert again["kind"] == "article"
    assert door.knocked_on_rbc() == [WHOLE], "and not again"


def test_a_link_no_feed_carries_is_still_fetched_and_still_refused(world) -> None:
    library, store, person, door = world
    store.reach("www.rbc.ru", False, "bot check")
    ctx = context(library, store, person)
    tools.search_sources(ctx, {"language": "ru"})

    elsewhere = tools.describe_source(ctx, {"url": ELSEWHERE})
    assert elsewhere["host_shut"] is True and elsewhere["challenge"] is True
    assert door.knocked_on_rbc() == [ELSEWHERE], "not in the feed, so knocked on as before"


def test_a_feed_item_without_its_full_text_still_refuses_as_before(world) -> None:
    library, store, person, door = world
    store.reach("www.rbc.ru", False, "bot check")
    ctx = context(library, store, person)
    tools.search_sources(ctx, {"language": "ru"})

    bare = tools.describe_source(ctx, {"url": BARE})
    assert bare["host_shut"] is True and bare["challenge"] is True
    assert "bot check" in bare["error"]
    assert door.knocked_on_rbc() == [BARE]


def test_a_reachable_page_is_read_from_the_page_not_the_feed(
    world, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The feed is the way round a bot check and nothing more: where the page opens, the
    page is what is read."""
    library, store, person, door = world
    ctx = context(library, store, person)
    tools.search_sources(ctx, {"language": "ru"})
    page = "<html><title>Со страницы</title><body><p>Слово со страницы.</p></body></html>"

    def opens(url: str, params: Any = None) -> url_module.Fetched:
        door.asked.append(url)
        return url_module.Fetched(text=page, content_type="text/html")

    monkeypatch.setattr(url_module, "fetch", opens)
    got = url_module.page(WHOLE)
    assert got.via == "direct" and "Со страницы" in got.text
    assert door.knocked_on_rbc() == [WHOLE]
