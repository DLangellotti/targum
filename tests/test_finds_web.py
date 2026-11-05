"""The nightly round over the open web (targum-internal#622; David, 2026-11-03; design.md
§12, "The open web is searched each night, on the forty topics").

Offline: the search, the pages and robots.txt are fixtures. Every word is synthetic.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from typer.testing import CliRunner

from targum.accounts import Store
from targum.chat.sources import Publisher
from targum.cli import app
from targum.finds import chips, live, pool, robots, score, web

DEPLOY = Path(__file__).resolve().parent.parent / "deploy"

LETTERS = "אבגדהזחטלמנסעפקרשת"


def general(n: int) -> str:
    return "מילה" + LETTERS[n // len(LETTERS)] + LETTERS[n % len(LETTERS)]


G1, G2 = general(1), general(2)
PAGE = " ".join(["עגבנייה"] * 3 + ["ביצה"] * 3 + [G1] * 89 + [G2] * 5)
OTHER = " ".join(["ביצה"] * 6 + [G1] * 90 + [G2] * 4)

#: The last day of a month, so the month's pacing leaves the night its whole dollar.
AT = int(datetime(2026, 11, 30, 0, 12, tzinfo=UTC).timestamp() * 1000)
PUBLISHED = int(datetime(2026, 10, 28, 9, 0, tzinfo=UTC).timestamp() * 1000)


def forms() -> score.Forms:
    words = ["עגבנייה", "ביצה", G1, G2]
    return score.Forms(
        language="he",
        forms={word: word for word in words},
        ranks={word: at + 1 for at, word in enumerate(words)},
    )


@pytest.fixture(autouse=True)
def clean(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(web.FLAG, raising=False)
    monkeypatch.delenv(pool.BUDGET_ENV, raising=False)


@pytest.fixture
def store(tmp_path: Path) -> Store:
    return Store(tmp_path / "targum.db")


class Search:
    """The search, as the round asks it: each query answered from `answers`, else empty."""

    def __init__(self, answers: dict[str, list[web.Hit]] | None = None, cost: float = 0.03):
        self.answers = answers or {}
        self.cost = cost
        self.asked: list[str] = []

    def __call__(self, query: str) -> web.Searched:
        self.asked.append(query)
        return web.Searched(hits=list(self.answers.get(query, [])), searches=1, cost=self.cost)


class Pages:
    def __init__(self, pages: dict[str, tuple[str, int]]) -> None:
        self.pages = pages
        self.asked: list[str] = []

    def __call__(self, url: str) -> tuple[str, int]:
        self.asked.append(url)
        if url not in self.pages:
            raise RuntimeError("would not open")
        return self.pages[url]


ROBOTS = robots.Robots(read=lambda url: "User-agent: *\nDisallow: /no/\n")
FIRST = chips.CHIPS[0]
QUERY = FIRST.phrases["he"]
PAPER = Publisher(
    key="paper",
    name="The Paper",
    publisher="Paper Media",
    homepage="https://www.paper.co.il/",
    licence="CC BY 4.0",
    licence_url="https://www.paper.co.il/licence",
)


def night(store: Store, ask: Search, pages: Pages | None = None, **more: Any) -> web.Night:
    return web.refresh(
        store,
        ask=ask,
        read=pages or Pages({}),
        robots=more.pop("robots", ROBOTS),
        forms_for=lambda language: forms(),
        publishers=more.pop("publishers", [PAPER]),
        at=more.pop("at", AT),
        **more,
    )


# -- the queries -----------------------------------------------------------------------


def test_the_queries_are_the_forty_chips_phrases_and_nothing_else() -> None:
    asked = web.queries("he")
    assert len(asked) == len(chips.CHIPS) == 40
    assert [query for _, query in asked] == [chip.phrases["he"] for chip in chips.CHIPS]
    assert web.queries("fr") == [], "no phrases, no search"
    assert len(web.queries("ru")) == 37, "Russian has no israel, holidays or army"


def test_the_search_sends_the_query_alone_and_costs_what_the_api_says() -> None:
    sent: list[dict[str, Any]] = []

    class Client:
        messages = SimpleNamespace(
            create=lambda **kwargs: (
                sent.append(kwargs),
                SimpleNamespace(
                    content=[
                        SimpleNamespace(type="server_tool_use", name="web_search", input={}),
                        SimpleNamespace(
                            type="web_search_tool_result",
                            content=[
                                SimpleNamespace(
                                    url="https://blog.example/a",
                                    title="שקשוקה",
                                    page_age="November 28, 2026",
                                ),
                                SimpleNamespace(url="https://blog.example/a", title="again"),
                                SimpleNamespace(url="ftp://nope", title="x"),
                            ],
                        ),
                        SimpleNamespace(type="text", text="done"),
                    ],
                    usage=SimpleNamespace(
                        input_tokens=12_000,
                        output_tokens=20,
                        cache_read_input_tokens=0,
                        cache_creation_input_tokens=0,
                        server_tool_use=SimpleNamespace(web_search_requests=1),
                    ),
                ),
            )[1]
        )

    got = web.search(Client(), QUERY)
    assert got.hits == [web.Hit("https://blog.example/a", "שקשוקה", "November 28, 2026")]
    assert got.searches == 1
    assert got.cost == pytest.approx(12_000 * 1 / 1e6 + 20 * 5 / 1e6 + 0.01)
    (request,) = sent
    assert request["model"] == web.MODEL
    assert request["messages"] == [{"role": "user", "content": f"Query: {QUERY}"}]
    (tool,) = request["tools"]
    assert tool["type"] == web.TOOL and tool["max_uses"] == 1 and "user_location" not in tool
    assert "output_config" not in request, "Haiku takes no effort"
    assert "@" not in json.dumps(request, ensure_ascii=False), "no address, no account"


def test_the_usage_count_of_searches_wins_over_the_blocks() -> None:
    reply = SimpleNamespace(
        content=[],
        usage=SimpleNamespace(
            input_tokens=0, output_tokens=0, server_tool_use={"web_search_requests": 2}
        ),
    )
    client = SimpleNamespace(messages=SimpleNamespace(create=lambda **kwargs: reply))
    assert web.search(client, QUERY).searches == 2


# -- one night -------------------------------------------------------------------------


def test_a_night_pools_what_passes_with_its_outlet_day_and_chip(store: Store) -> None:
    hits = [
        web.Hit("https://www.paper.co.il/a", "שקשוקה"),
        web.Hit("https://blog.example/b", "ביצים", "October 27, 2026"),
        web.Hit("https://blog.example/short", "קצר"),
        web.Hit("https://blog.example/no/c", "חסום"),
        web.Hit("https://www.pornhub.com/x", "x"),
        web.Hit("https://blog.example/gone", "נעלם"),
    ]
    pages = Pages(
        {
            "https://www.paper.co.il/a": (PAGE, PUBLISHED),
            "https://blog.example/b": (OTHER, 0),
            "https://blog.example/short": ("ביצה " * 5, 0),
        }
    )
    found = night(store, Search({QUERY: hits}, cost=0.02), pages)
    assert found.kept == 2 and found.searches == len(found.queries) == 40
    assert dict(found.dropped) == {"host": 1, "robots": 1, "short": 1, "unreadable": 1}
    assert not any("/no/" in url or "pornhub" in url for url in pages.asked)
    paper = next(one for one in pool.pick(store, "he", None, at=AT) if "paper" in one.url)
    assert paper.source == "web" and paper.publisher == "Paper Media"
    assert paper.published == PUBLISHED, "the day the page says"
    assert paper.topics == (chips.tag(FIRST.code),)
    assert (paper.licence, paper.licence_from) == ("CC BY 4.0", "publisher")
    assert paper.licence_url == "https://www.paper.co.il/licence"
    blog = next(one for one in pool.pick(store, "he", None, at=AT) if "blog" in one.url)
    assert blog.publisher == "blog.example" and blog.licence == ""
    assert blog.published == int(datetime(2026, 10, 27, tzinfo=UTC).timestamp() * 1000)
    columns = {row[1] for row in store.db.execute("PRAGMA table_info(find)")}
    assert not columns & {"text", "body", "words"}, "no text is kept"
    run = store.db.execute(
        "SELECT source, spent, note FROM find_run ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert run["source"] == web.RUN_SOURCE
    assert run["spent"] == pytest.approx(40 * 0.02)
    assert store.db.execute("SELECT COUNT(*) FROM job").fetchone()[0] == 0, "never a job row"


def test_what_the_pool_holds_is_tagged_not_fetched_and_one_article_is_pooled_once(
    store: Store,
) -> None:
    pool.add(
        store,
        language="he",
        source="news",
        url="https://www.paper.co.il/a",
        bag={"ביצה": 1},
        tokens=100,
        unresolved=0,
        rung=1,
        at=AT,
    )
    hits = [
        web.Hit("https://www.paper.co.il/a", "x"),
        web.Hit("https://blog.example/one", "x"),
        web.Hit("https://mirror.example/one", "x"),
    ]
    pages = Pages({"https://blog.example/one": (PAGE, 0), "https://mirror.example/one": (PAGE, 0)})
    found = night(store, Search({QUERY: hits}), pages)
    assert "https://www.paper.co.il/a" not in pages.asked
    (topics,) = store.db.execute(
        "SELECT topics FROM find WHERE url = 'https://www.paper.co.il/a'"
    ).fetchone()
    assert chips.tag(FIRST.code) in topics
    assert found.kept == 1 and found.dropped["same"] == 1


def test_a_night_stops_before_its_dollar_never_after(store: Store) -> None:
    ask = Search(cost=0.3)
    found = night(store, ask)
    assert found.allowance == pytest.approx(web.NIGHT_USD)
    assert found.spent <= web.NIGHT_USD
    # 0.3 each, and the next would need 0.45 of room (the dearest yet, with headroom).
    assert len(ask.asked) == 2 and found.stopped == "the night's $1.00"
    again = night(store, ask, at=AT + 60_000)
    assert again.allowance == pytest.approx(web.NIGHT_USD - 0.6), "a run by hand shares it"
    assert web.spent_today(store, AT + 60_000) <= web.NIGHT_USD


def test_the_night_is_paced_inside_the_month_s_budget(
    store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    early = int(datetime(2026, 11, 1, 0, 12, tzinfo=UTC).timestamp() * 1000)
    assert web.allowance(store, early) == pytest.approx((30 - web.LEAVE_USD) / 30)
    monkeypatch.setenv(pool.BUDGET_ENV, "100")
    assert web.allowance(store, early) == web.NIGHT_USD
    monkeypatch.setenv(pool.BUDGET_ENV, "10")
    assert web.allowance(store, early) == 0.0, "the other sources keep their share"
    ask = Search()
    found = night(store, ask, at=early)
    assert ask.asked == [] and found.stopped == "the night's $0.00"


def test_the_next_night_starts_where_this_one_stopped(
    store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    ask = Search(cost=0.3)
    night(store, ask)
    assert ask.asked == [query for _, query in web.queries("he")[:2]]
    monkeypatch.setenv(pool.BUDGET_ENV, "100")
    later = Search(cost=0.3)
    night(store, later, at=AT + pool.DAY_MS - 60_000)
    assert later.asked == [query for _, query in web.queries("he")[2:4]]


def test_a_query_a_live_look_bought_lately_is_not_bought_again(store: Store) -> None:
    run = pool.start_run(store, live.RUN_SOURCE, AT - 60_000)
    pool.finish_run(store, run, note={"queries": [QUERY]})
    ask = Search(cost=0.02)
    night(store, ask)
    assert QUERY not in ask.asked and len(ask.asked) == 39


def test_a_refused_search_ends_the_night_spends_nothing_and_waits(store: Store) -> None:
    def refuse(query: str) -> web.Searched:
        raise RuntimeError("credit balance too low")

    found = night(store, refuse)  # type: ignore[arg-type]
    assert found.stopped == "the search failed (RuntimeError)" and found.spent == 0
    assert web._start(store) == 0, "the same topic comes first next night"


def test_one_host_gives_at_most_five_pages_a_night(store: Store) -> None:
    hits = [web.Hit(f"https://blog.example/p{n}", "x") for n in range(8)]
    pages = Pages({hit.url: (PAGE + " " + G2 * n, 0) for n, hit in enumerate(hits)})
    night(store, Search({QUERY: hits}), pages)
    assert len(pages.asked) == web.HOST_MOST


def test_a_page_is_read_direct_never_through_the_proxy(monkeypatch: pytest.MonkeyPatch) -> None:
    from targum.ingest import url as url_module

    asked: list[bool] = []
    html = (
        '<html><head><meta property="article:published_time" content="2026-10-02T08:00:00Z">'
        "</head><body><article><p>" + PAGE + "</p></article></body></html>"
    )

    def fetch(address: str, params: Any = None, *, proxy: bool = True) -> Any:
        asked.append(proxy)
        return url_module.Fetched(text=html, content_type="text/html")

    monkeypatch.setattr(url_module, "fetch", fetch)
    text, published = web.page("https://blog.example/a")
    assert asked == [False]
    assert "עגבנייה" in text
    assert published == int(datetime(2026, 10, 2, 8, tzinfo=UTC).timestamp() * 1000)


def test_the_day_a_page_was_published_is_read_from_its_tags() -> None:
    assert web.published_of('<script>{"datePublished": "2026-09-01"}</script>') == int(
        datetime(2026, 9, 1, tzinfo=UTC).timestamp() * 1000
    )
    assert web.published_of('<meta itemprop="datePublished" content="2026-08-05">') > 0
    assert web.published_of("<p>nothing</p>") == 0
    assert web.published_of('<meta name="date" content="soon">') == 0
    assert web.published_of('<meta name="date" content="2999-01-01">') == 0, "never ahead"


# -- the switch and the timer -------------------------------------------------------------


def test_it_is_off_unless_the_box_says_so(monkeypatch: pytest.MonkeyPatch) -> None:
    assert not web.on()
    said = CliRunner().invoke(app, ["finds", "web"])
    assert said.exit_code == 0 and "off" in said.output
    monkeypatch.setenv(web.FLAG, "1")
    assert web.on()


def test_the_timer_runs_nightly_as_targum_at_its_own_hour() -> None:
    def unit(name: str) -> dict[str, list[str]]:
        fields: dict[str, list[str]] = {}
        for line in (DEPLOY / name).read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.startswith(("#", "[")):
                key, value = line.split("=", 1)
                fields.setdefault(key.strip(), []).append(value.strip())
        return fields

    service = unit("targum-finds-web.service")
    assert service["User"] == ["targum"], "never as root"
    assert service["ExecStart"] == [
        "/usr/local/bin/targum finds web --store /var/lib/targum/targum.db"
    ]
    assert service["EnvironmentFile"] == ["/etc/targum/targum.env"]
    assert service["TimeoutStartSec"] == ["50min"]
    (when,) = unit("targum-finds-web.timer")["OnCalendar"]
    others = {
        unit(name.name)["OnCalendar"][0]
        for name in DEPLOY.glob("*.timer")
        if name.name != "targum-finds-web.timer"
    }
    assert when == "*-*-* 00:10:00 UTC" and when not in others
    # Started at 00:10 plus at most two minutes, stopping its searches at 45: before 01:00.
    assert 10 + 2 + web.DEADLINE_S / 60 < 60
    script = (DEPLOY / "deploy.sh").read_text(encoding="utf-8")
    assert "deploy/targum-finds-web.service deploy/targum-finds-web.timer" in script
    installed = next(line for line in script.splitlines() if "for unit in" in line)
    assert "targum-finds-web.service targum-finds-web.timer" in installed
    enable = next(line for line in script.splitlines() if "systemctl enable --now" in line)
    assert "targum-finds-web.timer" in enable
