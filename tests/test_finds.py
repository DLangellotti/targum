"""Web finds, slice 1: the pool, the cheap scorer and news in Read next
(targum-internal#619; design.md §12, "A web find is a pasted link targum found",
2026-10-31)."""

from __future__ import annotations

import gzip
import json
import statistics
import threading
import time
from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, datetime
from http.server import ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from test_serve import Postbox, call, sign_in

from targum import choose
from targum import level as level_module
from targum.accounts import Store
from targum.chat import tools
from targum.coverage import IGNORED, KNOWN
from targum.finds import news, pool, provider, robots, score, screen
from targum.mail import ConsoleMailer
from targum.serve import Handler, Library, desk_languages

FIXTURES = Path(__file__).parent / "fixtures"
ASSETS = Path(__file__).parent.parent / "src" / "targum" / "render" / "assets"


@pytest.fixture(autouse=True)
def no_map(tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    """No laptop's `~/.targum/forms.json` reaches a test unless it writes one."""
    monkeypatch.setenv(score.ENV, str(tmp_path_factory.mktemp("forms") / "absent.json"))


def forms(**pairs: str) -> score.Forms:
    return score.Forms(language="he", forms=dict(pairs), names=frozenset({"ישראל"}))


# -- the scorer ------------------------------------------------------------------------


def test_a_token_is_found_as_itself_then_less_one_or_two_prefix_letters() -> None:
    held = forms(בית="בית", ספר="ספר")
    assert held.resolve("בית") == ("בית", score.EXACT)
    assert held.resolve("הבית") == ("בית", score.ONE)
    assert held.resolve("ובבית") == ("בית", score.TWO)
    assert held.resolve("ישראל") == ("", score.NAME), "a name is never counted"
    assert held.resolve("שולחן") == ("", score.UNRESOLVED)


def test_a_pointed_token_spelled_haser_finds_its_male_form() -> None:
    held = forms(אירועים="אירוע")
    assert held.resolve("אֵרוּעִים") == ("אירוע", score.HASER)
    assert held.resolve("ארועים")[1] != score.HASER, "an unpointed page is written male already"


def test_an_unseen_inflection_finds_a_lemma_the_map_holds() -> None:
    held = forms(חלום="חלום", מערה="מערה", תשתית="תשתית", ספר="ספר")
    assert held.resolve("חלומות") == ("חלום", score.SUFFIX), "a final mem put back"
    assert held.resolve("מערת") == ("מערה", score.SUFFIX), "a construct of a feminine"
    assert held.resolve("תשתיות") == ("תשתית", score.SUFFIX)
    assert held.resolve("וספרים") == ("ספר", score.SUFFIX), "prefix and suffix both"
    assert held.resolve("קרוביי")[1] == score.UNRESOLVED, "never a stem the map lacks"


def test_a_maqaf_joins_two_words_and_the_scorer_reads_two() -> None:
    assert score.tokens_of("בית־ספר", "he") == ["בית", "ספר"]


def test_coverage_counts_running_words_and_leaves_ignored_ones_out() -> None:
    held = forms(בית="בית", ספר="ספר", ים="ים")
    page = " ".join(["בית"] * 18 + ["ספר"] * 2 + ["ישראל"] * 5 + ["שולחן"] * 2)
    scored = held.score(page)
    assert scored.tokens == 22, "names out, unresolved in"
    assert scored.bag == {"בית": 18, "ספר": 2} and scored.unresolved == 2
    assert scored.coverage({"בית": KNOWN}) == pytest.approx(18 / 22)
    assert scored.coverage({"בית": KNOWN, "ספר": IGNORED}) == pytest.approx(18 / 20)


def test_a_page_the_map_cannot_place_is_not_measured() -> None:
    held = forms(בית="בית")
    assert held.score(" ".join(["בית"] * 46 + ["שולחן"] * 4)).measured, "8% unresolved"
    assert not held.score(" ".join(["בית"] * 45 + ["שולחן"] * 5)).measured, "10% is not"
    assert not held.score("בית בית").measured, "too short to say"


def test_the_calibration_holds_the_mean_error_under_two_and_a_half_points() -> None:
    """Acceptance 4 (plan §2.3): a frozen sample of held-out public texts, each scored with
    the slice of its fold's map its words can reach, against DICTA's running-word
    coverage for readers who know the commonest 2,000 to 6,500 lemmas."""
    body = json.loads(gzip.decompress((FIXTURES / "finds_calibration.json.gz").read_bytes()))
    cases = score.fixture_cases(body)
    assert len(cases) >= 15
    rows = score.table(cases)
    assert [row.known for row in rows] == list(score.READERS)
    for row in rows:
        assert row.mean_abs <= 0.025, row
        assert row.same_side >= 0.8, row


# -- the map: public texts only ----------------------------------------------------------


def annotate(folder: Path, words: list[tuple[str, str, str]], source: str) -> None:
    folder.mkdir(parents=True)
    tokens = [
        {"surface": surface, "lemma": lemma, "pos": pos, "entity": None}
        for surface, lemma, pos in words
    ]
    (folder / "annotation.json").write_text(
        json.dumps(
            {
                "document_hash": "f" * 16,
                "language": "he",
                "scripture_share": 0.0,
                "annotator": "test",
                "tokens": {"s1": tokens},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (folder / "document.json").write_text(
        json.dumps({"content_hash": "a" * 16 + folder.name, "source": source}), encoding="utf-8"
    )


def test_the_map_is_built_from_public_texts_and_never_from_a_reader_s_home(
    tmp_path: Path,
) -> None:
    library = tmp_path / "out"
    annotate(
        library / "public-he",
        [("הבית", "בית", "NOUN"), ("בית", "בית", "NOUN"), ("דוד", "דוד", "PROPN")],
        "https://he.wikipedia.org/wiki/x",
    )
    annotate(library / "p1" / "mine-he", [("סוד", "סוד", "NOUN")], "https://example.com/mine")
    annotate(library / "local" / "also-he", [("חלון", "חלון", "NOUN")], "file:///x")
    body = score.build(library, ["he"])
    held = body["languages"]["he"]
    assert held["forms"] == {"בית": "בית", "הבית": "בית"}
    assert held["names"] == ["דוד"]
    assert held["texts"] == 1, "a reader's home is left out whatever it holds"


def test_a_shipped_map_is_checked_first(tmp_path: Path) -> None:
    small = tmp_path / "forms.json"
    score.write({"version": score.VERSION, "languages": {"he": {"forms": {"a": "a"}}}}, small)
    assert score.check(small), "a map too small to be the shelf's"
    big = {f"צורה{n}": "צורה" for n in range(score.CHECK_LEAST_FORMS)}
    score.write({"version": score.VERSION, "languages": {"he": {"forms": big}}}, small)
    assert score.check(small) == []
    small.write_text("{}", encoding="utf-8")
    assert score.check(small)


def test_deploy_builds_and_checks_the_map_on_the_box() -> None:
    text = (Path(__file__).parent.parent / "deploy" / "deploy.sh").read_text(encoding="utf-8")
    assert "targum finds forms --library /var/lib/targum/targums" in text
    assert "targum finds forms --check /var/lib/targum/forms.json" in text
    assert "/etc/targum/forms.json" in text


# -- the pool --------------------------------------------------------------------------


@pytest.fixture
def store(tmp_path: Path) -> Store:
    return Store(tmp_path / "targum.db")


def keep(store: Store, url: str, bag: dict[str, int], **more: Any) -> int:
    tokens = more.pop("tokens", sum(bag.values()))
    return pool.add(
        store,
        language=more.pop("language", "he"),
        source="news",
        url=url,
        bag=bag,
        tokens=tokens,
        unresolved=more.pop("unresolved", 0),
        rung=more.pop("rung", 3),
        title=more.pop("title", "כותרת"),
        host="www.example.co.il",
        **more,
    )


def test_a_find_keeps_its_counts_and_never_its_text(store: Store) -> None:
    found = keep(store, "https://www.example.co.il/a", {"בית": 40, "ספר": 2})
    got = pool.get(store, found)
    assert got is not None and got.bag == {"בית": 40, "ספר": 2} and got.tokens == 42
    columns = {row[1] for row in store.db.execute("PRAGMA table_info(find)")}
    assert not columns & {"text", "body", "content", "transcript", "person", "reader"}
    assert keep(store, "https://www.example.co.il/a", {"בית": 1}) == 0, "an address once"


def test_a_find_expires_with_its_counts(store: Store) -> None:
    now = pool.now_ms()
    found = keep(store, "https://www.example.co.il/a", {"בית": 30}, at=now - 8 * pool.DAY_MS)
    assert pool.get(store, found) is None, "a week of news"
    assert pool.expire(store) == 1
    assert store.db.execute("SELECT COUNT(*) FROM find_lemma").fetchone()[0] == 0


def test_home_reads_the_finds_near_the_rung(store: Store) -> None:
    for rung in range(8):
        keep(store, f"https://www.example.co.il/{rung}", {"בית": 30}, rung=rung)
    keep(store, "https://www.example.co.il/u", {"בית": 30}, rung=None)
    assert sorted(find.rung or 0 for find in pool.pick(store, "he", 3)) == [2, 3, 4]
    assert len(pool.pick(store, "he", None)) == 8, "never one that is not measured"


def test_what_finding_costs_targum_is_held_to_its_budget(
    store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(pool.BUDGET_ENV, "2")
    run = pool.start_run(store, "news")
    pool.spend(store, run, 1.5)
    pool.finish_run(store, run, seen=3, kept=1)
    assert pool.month_spent(store) == pytest.approx(1.5)
    assert pool.left(store) == pytest.approx(0.5)
    assert store.db.execute("SELECT COUNT(*) FROM job").fetchone()[0] == 0, "never a job row"


# -- the screen ------------------------------------------------------------------------


def test_a_denied_host_is_dropped_with_its_subdomains_and_tlds() -> None:
    assert screen.host_denied("www.pornhub.com")
    assert screen.host_denied("anything.xxx")
    assert not screen.host_denied("www.ynet.co.il")


def test_explicit_and_graphic_words_drop_a_find_and_hard_news_stays() -> None:
    assert screen.term_in("סרטון עם תוכן פורנוגרפי")
    assert screen.term_in("והפורנו נמצא")
    assert screen.term_in("Watch the beheading video")
    assert screen.term_in("видео: обезглавленный")
    for hard in (
        "מלחמה בעזה: שלושה חיילים נהרגו בפיגוע",
        "רצח בתל אביב, המשטרה חוקרת",
        "Election results and the war in Ukraine",
        "Теракт в Москве: погибли люди",
    ):
        assert screen.term_in(hard) == "", hard
    assert screen.passes("www.ynet.co.il", "מלחמה") == ""
    assert screen.passes("www.ynet.co.il", "תמונות עירום") == "words"


def test_the_operator_adds_hosts_beside_sources(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    deny = tmp_path / "finds-deny.json"
    deny.write_text(json.dumps(["casino-news.example"]), encoding="utf-8")
    monkeypatch.setenv("TARGUM_FINDS_DENY", str(deny))
    assert screen.host_denied("www.casino-news.example")


# -- robots.txt ------------------------------------------------------------------------


def test_robots_is_read_once_a_day_and_honoured() -> None:
    asked: list[str] = []

    def read(url: str) -> str | None:
        asked.append(url)
        if "closed" in url:
            return None
        if "missing" in url:
            return ""
        return "User-agent: *\nDisallow: /private/\n"

    held = robots.Robots(read=read)
    assert held.allowed("https://news.example/story")
    assert not held.allowed("https://news.example/private/story")
    assert asked == ["https://news.example/robots.txt"], "once for the host"
    assert held.allowed("https://missing.example/x"), "no robots.txt allows"
    assert not held.allowed("https://closed.example/x"), "a host that cannot say is skipped"


# -- the news round --------------------------------------------------------------------


def publisher(feed: str = "https://feed.example/rss", **more: Any) -> Any:
    from targum.chat.sources import Publisher

    return Publisher(key="p", name="Paper", publisher="The Paper", feed=feed, **more)


def item(link: str, title: str = "כותרת", full_text: str = "") -> Any:
    from targum.weekly.feeds import Item

    return Item(
        title=title,
        link=link,
        published=datetime(2026, 10, 31, 9, tzinfo=UTC),
        full_text=full_text,
    )


PAGE = " ".join(["בית"] * 90 + ["ספר"] * 10)


class Door:
    """The fetch door, as the round calls it: no network, and a record of each knock."""

    def __init__(self, pages: dict[str, str], cost: float = 0.0) -> None:
        self.pages = pages
        self.cost = cost
        self.asked: list[tuple[str, bool]] = []

    def __call__(self, url: str, *, proxy: bool) -> tuple[str, float]:
        self.asked.append((url, proxy))
        if url not in self.pages:
            raise RuntimeError("would not open")
        return self.pages[url], self.cost


def round_with(store: Store, items: list[Any], door: Door, **more: Any) -> news.Round:
    held = forms(בית="בית", ספר="ספר")
    return news.refresh(
        store,
        kept={"https://feed.example/rss": items},
        publishers=[publisher()],
        read=door,
        robots=robots.Robots(read=lambda url: "User-agent: *\nDisallow: /no/\n"),
        forms_for=lambda language: held,
        **more,
    )


def test_a_round_pools_new_articles_and_keeps_only_their_counts(store: Store) -> None:
    door = Door({"https://news.example/a": PAGE, "https://news.example/b": "בית " * 10})
    found = round_with(
        store,
        [
            item("https://news.example/a"),
            item("https://news.example/b"),
            item("https://news.example/no/c"),
            item("https://news.example/d"),
            item("https://www.pornhub.com/x"),
            item("https://news.example/e", title="תמונות עירום"),
            item("https://news.example/f", full_text=PAGE + " ספר"),
        ],
        door,
    )
    assert found.kept == 2
    assert dict(found.dropped) == {
        "short": 1,
        "robots": 1,
        "unreadable": 1,
        "host": 1,
        "words": 1,
    }
    assert ("https://news.example/f", True) not in door.asked, "a feed's full text is enough"
    assert not any("pornhub" in url or "no/c" in url for url, _ in door.asked)
    again = round_with(store, [item("https://news.example/a")], Door({}))
    assert again.seen == 0, "an address the pool holds is not fetched again"


def test_the_same_article_at_two_addresses_is_pooled_once(store: Store) -> None:
    door = Door({"https://news.example/a": PAGE, "https://news.example/a?ref=x": PAGE})
    found = round_with(
        store, [item("https://news.example/a"), item("https://news.example/a?ref=x")], door
    )
    assert found.kept == 1 and found.dropped["same"] == 1


def test_a_closed_host_is_never_knocked_on(store: Store) -> None:
    store.reach("news.example", False)
    door = Door({"https://news.example/a": PAGE})
    found = round_with(store, [item("https://news.example/a")], door)
    assert door.asked == [] and found.dropped["closed"] == 1


def test_a_proxied_page_is_targum_s_spend_and_stops_at_the_budget(
    store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(pool.BUDGET_ENV, "0.001")
    door = Door({"https://news.example/a": PAGE, "https://news.example/b": PAGE + " ספר"}, 0.001)
    found = round_with(
        store, [item("https://news.example/a"), item("https://news.example/b")], door
    )
    assert found.spent == pytest.approx(0.002)
    assert [proxy for _, proxy in sorted(door.asked)] in ([True, False], [False, True]), (
        "once the month's budget is spent, the direct knock alone"
    )


def test_a_language_with_no_map_is_not_fetched(store: Store) -> None:
    door = Door({"https://news.example/a": PAGE})
    found = news.refresh(
        store,
        kept={"https://feed.example/rss": [item("https://news.example/a")]},
        publishers=[publisher(language="ru")],
        read=door,
        robots=robots.Robots(read=lambda url: ""),
        forms_for=lambda language: forms(),
    )
    assert found.seen == 0 and door.asked == [], "Russian waits for a map of its own"


# -- offered on Read next ------------------------------------------------------------


def test_the_provider_s_floor_is_the_chooser_s() -> None:
    assert provider.FLOOR == choose.FLOOR


def test_only_a_measured_find_clear_of_the_floor_is_offered(store: Store) -> None:
    marked = {"בית": KNOWN}
    keep(store, "https://n.example/95", {"בית": 95, "ספר": 5})
    keep(store, "https://n.example/91", {"בית": 91, "ספר": 9})
    keep(store, "https://n.example/80", {"בית": 80, "ספר": 20})
    keep(store, "https://n.example/unres", {"בית": 95}, tokens=105, unresolved=10)
    keep(store, "https://n.example/paid", {"בית": 96, "ספר": 4}, credits=5)
    got = provider.offered(store, "he", marked, credits_left=2)
    assert [one.find.url for one in got] == ["https://n.example/95"]
    assert got[0].share == pytest.approx(0.95)
    assert (
        provider.offered(store, "he", marked, built={"https://n.example/95"}, credits_left=2) == []
    )
    row = provider.row(got[0])
    assert row["origin"] == "find" and row["id"] == f"find-{got[0].find.id}"
    assert row["because"] == "You know 95% of the words here."
    assert row["credits"] == 0 and row["minutes"] == 1


class Marks:
    def __init__(self, store: Store, marked: dict[str, int]) -> None:
        self.inner = store
        self.marked_words = marked

    def marked(self, person: Any, language: str) -> dict[str, int]:
        return self.marked_words

    def __getattr__(self, name: str) -> Any:
        return getattr(self.inner, name)


def ctx_for(store: Store, marked: dict[str, int]) -> Any:
    return SimpleNamespace(
        level=replace(level_module.EMPTY, language="he"),
        store=Marks(store, marked),
        person=SimpleNamespace(id=1, email="r@example.com", admin=False),
        admin=False,
        library=SimpleNamespace(allowance=lambda paid_plan=False: None),
    )


def test_a_find_in_band_is_chosen_by_the_same_key_and_says_where_it_came_from(
    store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(tools, "CANDIDATE_SOURCES", [("shelf", lambda ctx: [])])
    monkeypatch.setattr(tools, "_shelf", lambda ctx, measured=True: ([], []))
    monkeypatch.setattr(tools, "_collections", lambda: {})
    ctx = ctx_for(store, {"בית": KNOWN})
    assert tools.suggest_next(ctx, {"limit": 3, "finds": True})["suggestions"] == [], (
        "an empty pool leaves Read next as the shelf makes it"
    )
    keep(store, "https://n.example/95", {"בית": 95, "ספר": 5})
    keep(store, "https://n.example/99", {"בית": 999, "ספר": 1})
    got = tools.suggest_next(ctx, {"limit": 3, "finds": True})["suggestions"]
    assert [row["url"] for row in got] == ["https://n.example/95", "https://n.example/99"]
    assert got[0]["origin"] == "find" and got[0]["fit"] == "band" and got[1]["fit"] == "easy"
    assert tools.suggest_next(ctx, {"limit": 3})["suggestions"] == [], (
        "only a caller that can open a find is offered one"
    )
    other = tools.suggest_next(ctx, {"limit": 1, "finds": True, "instead_of": got[0]["id"]})
    assert other["suggestions"][0]["url"] == "https://n.example/99"


def test_home_adds_under_30_ms_scoring_a_full_pick(store: Store) -> None:
    """Acceptance 5: 300 finds of 300 lemmas each, scored for one reader."""
    lemmas = [f"מילה{n}" for n in range(3000)]
    marked = dict.fromkeys(lemmas[:2500], KNOWN)
    for at in range(pool.PICK_MOST):
        bag = {lemmas[(at * 7 + n) % 3000]: 1 + n % 3 for n in range(300)}
        keep(store, f"https://n.example/{at}", bag)
    provider.offered(store, "he", marked)  # the counts are read once a process
    took = []
    for _ in range(20):
        started = time.perf_counter()
        provider.offered(store, "he", marked)
        took.append(time.perf_counter() - started)
    assert statistics.quantiles(took, n=20)[-1] < 0.030, took


# -- served: Home and Open -----------------------------------------------------------


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Any]:
    from targum.chat import session as session_module

    out = tmp_path / "out"
    out.mkdir()
    store = Store(tmp_path / "targum.db")
    library = Library(out, store=store)
    postbox = Postbox()
    chats = session_module.Chats(library, store, client_factory=lambda: None)
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    server.RequestHandlerClass = type(
        "FindsHandler",
        (Handler,),
        {
            "library": library,
            "token": "k",
            "welcome": "<html>start</html>",
            "chats": chats,
            "store": store,
            "mailer": ConsoleMailer(postbox),
            "address": f"http://127.0.0.1:{port}",
            "translated": {code: {} for code in desk_languages()},
        },
    )
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setattr(tools, "CANDIDATE_SOURCES", [("shelf", lambda ctx: [])])
    try:
        yield SimpleNamespace(port=port, store=store, library=library, postbox=postbox)
    finally:
        server.shutdown()
        server.server_close()


def test_a_news_find_in_band_shows_on_home_with_nothing_fetched(
    home: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Acceptance 1. The suite cannot reach the network at all, so a request that
    fetched would fail here; the counts are the pool's, read off the database."""
    cookie = sign_in(home.port, home.postbox)
    person = home.store.person_by_email("reader@example.com")
    monkeypatch.setattr(Store, "marked", lambda self, who, language: {"בית": KNOWN})
    keep(home.store, "https://news.example/a", {"בית": 95, "ספר": 5}, title="חדשות")
    status, got, _ = call(
        home.port, "POST", "/suggest", {"language": "he", "skip": []}, cookie=cookie
    )
    assert status == 200 and person is not None
    found = got["suggestion"]
    assert found["origin"] == "find" and found["title"] == "חדשות"
    assert found["host"] == "www.example.co.il" and found["credits"] == 0


def test_open_builds_through_the_press_and_a_higher_quote_builds_nothing(
    home: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Acceptance 2: Open prices the link as Add would, and presses where the quote is
    the card's; where it costs more, the page is sent to Add and nothing is pressed."""
    cookie = sign_in(home.port, home.postbox)
    pressed: list[Any] = []
    seconds = {"value": 0.0}

    def prepare(job: Any) -> None:
        job.stage = "ready"
        job.audio = bool(seconds["value"])
        job.seconds = seconds["value"]

    def press(job: Any) -> str:
        pressed.append(job)
        job.stage = "queued"
        return ""

    monkeypatch.setattr(home.library, "prepare", prepare)
    monkeypatch.setattr(home.library, "press", press)
    found = keep(home.store, "https://news.example/a", {"בית": 95, "ספר": 5})
    status, got, _ = call(home.port, "POST", f"/finds/{found}/open", {}, cookie=cookie)
    assert status == 200 and got["pressed"] is True
    job = pressed[0]
    person = home.store.person_by_email("reader@example.com")
    assert person is not None and job.owner == person.id
    assert job.home == home.library.home(person), "the reader's own import"
    assert job.options["via"] == "find" and job.options["find"] == found
    assert job.source == "https://news.example/a"

    seconds["value"] = 600.0
    status, got, _ = call(home.port, "POST", f"/finds/{found}/open", {}, cookie=cookie)
    assert status == 200 and got["pressed"] is False and len(pressed) == 1
    assert got["confirm"] == "/add?source=https%3A%2F%2Fnews.example%2Fa"

    assert call(home.port, "POST", "/finds/9999/open", {}, cookie=cookie)[0] == 404
    assert call(home.port, "POST", f"/finds/{found}/open", {})[0] == 401


def test_a_tables_sweep_never_sees_a_pool_address(home: Any, tmp_path: Path) -> None:
    """Acceptance 3: the pool writes no file, and a find a reader built is their import,
    in their home, which `tables.public_text` refuses."""
    from targum import tables

    keep(home.store, "https://news.example/secret", {"בית": 95, "ספר": 5})
    person = SimpleNamespace(id=7, email="r@example.com", admin=False)
    folder = home.library.home(person) / "built-find"
    annotate(folder, [("בית", "בית", "NOUN")], "https://news.example/secret")
    assert tables.public_text(folder, home.library.out) is None
    swept = tables.Store(tmp_path / "corpus.db")
    result = tables.sweep(home.library.out, swept)
    assert result.folded == 0 and result.private == 1
    import sqlite3

    if swept.file.is_file():
        dumped = "\n".join(sqlite3.connect(swept.file).iterdump())
        assert "news.example" not in dumped


def test_home_draws_a_find_with_its_credits_and_opens_it_with_a_post() -> None:
    text = (ASSETS / "home.js").read_text(encoding="utf-8")
    assert '"/finds/" + encodeURIComponent(row.find) + "/open"' in text
    assert 't("home.find.uses-no-credits", "Uses none of your credits")' in text
    assert "got.confirm" in text, "a higher quote goes to Add's own confirm"


def test_the_back_office_counts_the_pool_and_names_no_link(store: Store) -> None:
    import sqlite3

    from targum.render.builder import _find_rungs

    keep(store, "https://news.example/hidden", {"בית": 95}, rung=4, topics=("tech",))
    pool.drop(store, language="he", source="news", url="https://x.example/y", reason="words")
    db = sqlite3.connect(f"file:{store.path}?mode=ro", uri=True)
    try:
        found = pool.survey(db)
    finally:
        db.close()
    assert found.by_language == {"he": 1} and found.dropped == {"words": 1}
    assert found.by_topic == {"tech": 1}
    assert _find_rungs(found) == [("he", "ג", 1)]
