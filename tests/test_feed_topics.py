"""What a feed item is about, and a search held to it (2026-10-07).

Asked in ChatGPT for "something on culture" in Russian, a host had `query` alone, which
matches headline words in the article's language, and went to its own web search. Now
an item's topics come from its feed's own categories (`chat.sources.CATEGORY_TOPICS`)
and from its publisher row where the feed is one section of a paper, and
`search_sources` takes a `topic`. The feeds are fabricated (`fixtures/feeds/`) and
nothing touches the network.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from targum import level
from targum.accounts import Person, Store
from targum.chat import sources, tools
from targum.ingest import url as url_module
from targum.serve import Library
from targum.weekly import feeds

FEEDS = Path(__file__).parent / "fixtures" / "feeds"
RU = "https://rubrics.example/rss"
HE = "https://section.example/atom"


# -- the table ----------------------------------------------------------------------


def test_every_category_maps_into_the_fixed_set() -> None:
    assert sources.TOPICS == (
        "world",
        "politics",
        "economy",
        "culture",
        "science",
        "tech",
        "sport",
        "health",
    )
    for category, topics in sources.CATEGORY_TOPICS.items():
        assert topics and set(topics) <= set(sources.TOPICS), category
        assert category == " ".join(category.casefold().split()), "keys are folded"


@pytest.mark.parametrize(
    ("categories", "topics"),
    [
        (["Культура"], ("culture",)),
        (["Культура и искусство"], ("culture",)),
        (["תרבות"], ("culture",)),
        (["Спорт"], ("sport",)),
        (["ספורט"], ("sport",)),
        (["Наука"], ("science",)),
        (["מדע"], ("science",)),
        (["Наука и техника"], ("science", "tech")),
        (["Экономика и бизнес"], ("economy",)),
        (["В мире"], ("world",)),
        (["Novosti · Kultura"], ("culture",)),
        (["Novosti · Mezhdunarodnaya politika"], ("world", "politics")),
        (["טכנולוגיה: בינה מלאכותית"], ("tech",)),
        (["Спорт", "Мир"], ("world", "sport")),
        (["Из жизни", "הורוסקופ"], ()),
        (["Мировой рынок нефти"], ()),
        ([], ()),
    ],
)
def test_a_category_is_read_as_its_topics(categories: list[str], topics: tuple[str, ...]) -> None:
    assert sources.topics_of(categories) == topics


# -- the feed -----------------------------------------------------------------------


def test_an_item_keeps_the_categories_its_feed_files_it_under() -> None:
    items = {item.link: item for item in feeds.parse((FEEDS / "ru-categories.xml").read_bytes())}
    assert items["https://rubrics.example/culture/2001"].categories == ("Культура",)
    assert items["https://rubrics.example/sport/2002"].categories == ("Спорт", "Мир"), (
        "each once, CDATA or not"
    )
    assert items["https://rubrics.example/science/2003"].categories == ("Наука и техника",)
    assert items["https://rubrics.example/misc/2006"].categories == ()
    atom = feeds.parse((FEEDS / "he-section.xml").read_bytes())
    assert [item.categories for item in atom] == [(), ("מוזיקה",)], "Atom's term"


def test_a_section_feed_s_topic_is_read_from_its_publisher_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "sources.json"
    rows = [
        {"key": "paper", "name": "Paper", "feed": "https://p.example/rss"},
        {
            "key": "paper-culture",
            "name": "Culture",
            "feed": "https://p.example/c",
            "topic": "culture",
        },
        {
            "key": "paper-tech",
            "name": "Tech",
            "feed": "https://p.example/t",
            "topic": ["science", "tech", "gossip"],
        },
    ]
    path.write_text(json.dumps({"publishers": rows}), encoding="utf-8")
    monkeypatch.setenv("TARGUM_SOURCES", str(path))
    assert {one.key: one.topics for one in sources.load()} == {
        "paper": (),
        "paper-culture": ("culture",),
        "paper-tech": ("science", "tech"),
    }, "a word not in the set is dropped"


# -- the search ---------------------------------------------------------------------


@pytest.fixture
def world(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[tuple[Library, Store, Person]]:
    path = tmp_path / "sources.json"
    path.write_text(
        json.dumps(
            {
                "publishers": [
                    {"key": "rubrics", "name": "Рубрики", "feed": RU, "language": "ru"},
                    {
                        "key": "section-culture",
                        "name": "מדור תרבות",
                        "feed": HE,
                        "language": "he",
                        "topic": "culture",
                    },
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("TARGUM_SOURCES", str(path))

    def fetch(url: str, params: Any = None) -> url_module.Fetched:
        name = {RU: "ru-categories.xml", HE: "he-section.xml"}[url]
        return url_module.Fetched(
            text="", content_type="application/rss+xml", raw=(FEEDS / name).read_bytes()
        )

    monkeypatch.setattr(url_module, "fetch", fetch)
    store = Store(tmp_path / "words.db")
    out = tmp_path / "out"
    out.mkdir()
    library = Library(out, store=store)
    signed = store.finish_sign_in(store.start_sign_in("reader@example.com"))
    assert signed is not None
    tools.FEEDS.clear()
    yield library, store, signed[0]
    tools.FEEDS.clear()


def context(library: Library, store: Store, person: Person, language: str) -> tools.Ctx:
    return tools.Ctx(
        person=person,
        home=library.home(person),
        library=library,
        store=store,
        chat_id="c1",
        level=level.snapshot(store, person.id, language),
    )


def test_a_topic_keeps_the_items_that_carry_it(world: tuple[Library, Store, Person]) -> None:
    ctx = context(*world, "ru")
    every = tools.search_sources(ctx, {"language": "ru"})
    assert every["count"] == 6, "no topic, nothing left out — an item with none included"
    culture = tools.search_sources(ctx, {"language": "ru", "topic": "culture"})
    assert [row["link"] for row in culture["items"]] == [
        "https://rubrics.example/culture/2001",
        "https://rubrics.example/novosti/2004",
    ]
    assert all(row["topics"] == ["culture"] for row in culture["items"])
    tech = tools.search_sources(ctx, {"language": "ru", "topic": "tech"})
    assert [row["link"] for row in tech["items"]] == ["https://rubrics.example/science/2003"]
    assert tech["items"][0]["topics"] == ["science", "tech"]
    sport = tools.search_sources(ctx, {"language": "ru", "topic": "sport", "query": "матч"})
    assert [row["link"] for row in sport["items"]] == ["https://rubrics.example/sport/2002"]
    assert tools.search_sources(ctx, {"language": "ru", "topic": "health"})["count"] == 0
    untopical = {row["link"]: row for row in every["items"]}["https://rubrics.example/misc/2006"]
    assert "topics" not in untopical, "no topic is said as no field, not an empty list"
    # A topic the set does not have is no filter rather than an empty answer.
    assert tools.search_sources(ctx, {"language": "ru", "topic": "gossip"})["count"] == 6


def test_a_section_feed_s_items_carry_its_topic(world: tuple[Library, Store, Person]) -> None:
    ctx = context(*world, "he")
    got = tools.search_sources(ctx, {"topic": "culture"})
    assert [row["link"] for row in got["items"]] == [
        "https://section.example/culture/3001",
        "https://section.example/culture/3002",
    ], "both, though only one names a category of its own"
    assert tools.search_sources(ctx, {"topic": "sport"})["count"] == 0


def test_search_sources_offers_the_topics_by_name() -> None:
    schema = tools.BY_NAME["search_sources"].schema["properties"]["topic"]
    assert schema["enum"] == list(sources.TOPICS)
    assert "by topic" in tools.BY_NAME["search_sources"].description


# -- the address, where a feed files nothing (2026-10-07) ----------------------------


@pytest.mark.parametrize(
    ("link", "topics"),
    [
        ("https://www.haaretz.co.il/news/politics/2026-10-07/ty-article/00000", ("politics",)),
        ("https://www.haaretz.co.il/news/world/europe/2026-10-07/ty-article/1", ("world",)),
        ("https://www.rbc.ru/sport/07/10/2026/abc", ("sport",)),
        ("https://www.rbc.ru/business/07/10/2026/abc", ("economy",)),
        ("https://tass.ru/kultura/28188000", ("culture",)),
        ("https://tass.ru/mezhdunarodnaya-panorama/28188665", ("world",)),
        ("https://www.ynet.co.il/sport/article/abc", ("sport",)),
        ("https://www.israelhayom.co.il/culture/internet-culture/article/1", ("culture",)),
        # No section named, so no topic: never a guess.
        ("https://meduza.io/news/2026/10/07/zagolovok", ()),
        ("https://meduza.io/feature/2026/10/07/kultura-i-mir", ()),
        ("https://www.bbc.com/russian/articles/c0000000", ()),
        ("https://news.walla.co.il/item/3871080", ()),
        ("https://lenta.ru/news/2026/10/07/sport/", ()),
        ("https://www.ynet.co.il/entertainment/article/abc", ()),
        ("https://www.ynet.co.il/digital/technews/article/abc", ()),
        ("https://example.org/sportswear/1", ()),
    ],
)
def test_an_address_names_a_topic_only_by_its_section(link: str, topics: tuple[str, ...]) -> None:
    assert sources.topics_of_link(link) == topics
    for segment, named in sources.PATH_TOPICS.items():
        assert set(named) <= set(sources.TOPICS), segment


def test_the_address_is_read_only_where_the_feed_files_nothing() -> None:
    blank = sources.Publisher(key="p", name="p", publisher="")
    bare = feeds.Item(title="t", link="https://www.rbc.ru/sport/07/10/2026/a")
    filed = feeds.Item(
        title="t", link="https://www.rbc.ru/sport/07/10/2026/a", categories=("Политика",)
    )
    assert tools._item_topics(blank, bare) == ("sport",)
    assert tools._item_topics(blank, filed) == ("politics",), "the feed's word wins"


def test_a_search_keeps_sixty_items_of_each_feed(
    world: tuple[Library, Store, Person], monkeypatch: pytest.MonkeyPatch
) -> None:
    """15 held a topic search to a feed's fifteen newest stories (2026-10-07)."""
    asked: list[int] = []
    real = feeds.pull

    def pull(url: str, *, limit: int = 30) -> list[feeds.Item]:
        asked.append(limit)
        return real(url, limit=limit)

    monkeypatch.setattr(feeds, "pull", pull)
    tools.search_sources(context(*world, "ru"), {"language": "all"})
    assert asked and set(asked) == {tools.FEED_ITEMS} and tools.FEED_ITEMS == 60
