""" "Find me something" (targum-internal#615): interests, the pool's pick, the live look
on the web and its caps, and `POST /find`."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from test_finds import home, keep  # noqa: F401 - `home` is a fixture
from test_serve import call, sign_in

from targum.accounts import Store
from targum.coverage import IGNORED, KNOWN
from targum.finds import button, chips, interests, live, pool, robots, score

LETTERS = "אבגדהזחטלמנסעפקרשת"


def general(n: int) -> str:
    """A general word, in Hebrew letters only (the scorer reads no digits)."""
    return "מילה" + LETTERS[n // len(LETTERS)] + LETTERS[n % len(LETTERS)]


G1, G2 = general(1), general(2)

# A small lexicon: two shown topics, one not shown, and general words.
LEMMAS: dict[str, tuple[str, ...]] = {
    "עגבנייה": ("food",),
    "ביצה": ("food",),
    "מתכון": ("food",),
    "מחבת": ("food",),
    "בצל": ("food",),
    "שופט": ("law",),
    "משטרה": ("law",),
    "עץ": ("nature",),
    **{general(n): ("general",) for n in range(60)},
}


@pytest.fixture(autouse=True)
def clean(tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(score.ENV, str(tmp_path_factory.mktemp("forms") / "absent.json"))
    monkeypatch.delenv(button.FLAG, raising=False)
    monkeypatch.delenv(live.FLAG, raising=False)
    interests.forget()
    live.forget()


def lexicon() -> interests.Lexicon:
    return interests.from_lemmas(LEMMAS, ("food", "law"))


@pytest.fixture
def store(tmp_path: Path) -> Store:
    return Store(tmp_path / "targum.db")


# -- interests -----------------------------------------------------------------------


def test_what_a_reader_reads_says_what_they_like_and_a_claim_does_not() -> None:
    met = [general(n) for n in range(45)] + ["עגבנייה", "ביצה", "מתכון"]
    words = [("מחבת", KNOWN, "saved"), ("בצל", 1, ""), ("שופט", KNOWN, "claimed")]
    got = interests.inferred(words, met, lexicon())
    assert [one.topic for one in got] == ["food"]
    assert got[0].hits == 5
    assert interests.inferred([], met[:10], lexicon()) == [], "too little read to tell"
    words_only_law = [(lemma, KNOWN, "claimed") for lemma in ("שופט", "משטרה")]
    assert all(one.topic != "law" for one in interests.inferred(words_only_law, met, lexicon()))


def test_an_ignored_word_and_a_topic_not_shown_say_nothing() -> None:
    met = [general(n) for n in range(45)] + ["עץ"] * 1
    words = [(lemma, IGNORED, "") for lemma in ("עגבנייה", "ביצה", "מתכון", "מחבת", "בצל")]
    assert interests.inferred(words, met, lexicon()) == []


def test_a_find_is_about_a_topic_from_its_counts() -> None:
    bag = {"עגבנייה": 3, "ביצה": 2, G1: 90, "שופט": 1}
    assert interests.about(bag, 100, lexicon()) == {"food": 0.05}


def test_the_lexicon_is_read_from_where_the_environment_says(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    file = tmp_path / "topics.json"
    file.write_text(
        json.dumps({"shown": ["food"], "lemmas": {k: list(v) for k, v in LEMMAS.items()}}),
        encoding="utf-8",
    )
    monkeypatch.setenv(interests.ENV, str(file))
    got = interests.lexicon()
    assert got is not None and got.shown == ("food",)
    monkeypatch.setenv(interests.ENV, str(tmp_path / "absent.json"))
    assert interests.lexicon() is None


# -- the pool's pick -----------------------------------------------------------------

FOOD = {"עגבנייה": 3, "ביצה": 3, G1: 89, G2: 5}
LAW = {"שופט": 3, "משטרה": 3, G1: 89, G2: 5}
MARKED = {"עגבנייה": KNOWN, "ביצה": KNOWN, "שופט": KNOWN, "משטרה": KNOWN, G1: KNOWN}


def test_chosen_topics_keep_the_rest_out_and_liked_ones_only_lead(store: Store) -> None:
    keep(store, "https://a.example/law", LAW)
    keep(store, "https://a.example/food", FOOD, credits=5)
    steered = button.ranked(
        store, button.Ask("he", chosen=("food",)), MARKED, known=lexicon(), credits_left=2
    )
    assert [row["url"] for row in steered] == ["https://a.example/food"]
    assert steered[0]["chip"] == "food" and steered[0]["over"] is True
    assert steered[0]["fit"] == "band" and button.fits(steered)
    liked = button.ranked(store, button.Ask("he", liked=("law",)), MARKED, known=lexicon())
    assert [row["url"] for row in liked] == ["https://a.example/law", "https://a.example/food"]
    assert liked[0]["because_topic"] == "law" and "because_topic" not in liked[1]
    passed = button.ranked(
        store, button.Ask("he", liked=("law",), skip=(liked[0]["id"],)), MARKED, known=lexicon()
    )
    assert [row["url"] for row in passed] == ["https://a.example/food"], "Another"


def test_nothing_in_the_band_does_not_fit(store: Store) -> None:
    keep(store, "https://a.example/easy", {G1: 1000})
    rows = button.ranked(store, button.Ask("he"), {G1: KNOWN}, known=lexicon())
    assert rows and rows[0]["fit"] == "easy" and not button.fits(rows)
    assert not button.fits([])


# -- the live look -------------------------------------------------------------------


def test_the_query_is_topic_words_language_and_level_and_nothing_else() -> None:
    said = live.queries(("cooking", "football"), "he", 1)
    allowed = {
        *live.TOPIC_WORDS["he"].values(),
        *(chip.phrases["he"] for chip in chips.CHIPS),
        *(words for _, words in live.LEVEL_WORDS["he"]),
    }
    pieces = {word for one in said for word in one.split()}
    assert pieces <= {word for phrase in allowed for word in phrase.split()}
    # One topic to a query, never joined with "או", and no "כתבה על" (ling-he, 2026-11-01).
    assert said == ("מתכונים ובישול בעברית קלה", "כדורגל בעברית קלה")
    assert len(said) <= live.MAX_USES, "two topics, two searches, inside the cap"
    assert live.queries(("cooking", "football", "army"), "he", 1)[1:] == ("כדורגל בעברית קלה",)
    assert live.queries(("law",), "he", 5) == ("פלילים ומשפט",), "a lexicon topic liked"
    assert live.queries(("army",), "he", 5) == ("צבא ושירות צבאי",), "ling-he's phrase"
    # Easy Hebrew at aleph, aleph plus and bet (rungs 0-2), never past bet.
    assert live.queries(("food",), "he", 0) == ("אוכל ומסעדות בעברית קלה",)
    assert live.queries(("food",), "he", 2) == ("אוכל ומסעדות בעברית קלה",)
    assert live.queries(("food",), "he", 3) == ("אוכל ומסעדות",), "bet plus is past bet"
    assert live.queries((), "he", None) == ("חיי היומיום בעברית קלה",)
    assert live.queries(("food",), "ru", 1) == (), "no words for the language, no look"


class Client:
    """The Messages API, as `live.search` calls it: a record of what was sent."""

    def __init__(self, results: list[dict[str, str]]) -> None:
        self.sent: list[dict[str, Any]] = []
        self.results = results
        self.messages = self

    def create(self, **kwargs: Any) -> Any:
        self.sent.append(kwargs)
        return SimpleNamespace(
            content=[
                SimpleNamespace(type="server_tool_use", name="web_search", input={}),
                SimpleNamespace(
                    type="web_search_tool_result",
                    content=[SimpleNamespace(**one) for one in self.results],
                ),
                SimpleNamespace(type="text", text="done"),
            ],
            usage=SimpleNamespace(input_tokens=20_000, output_tokens=50),
        )


def test_the_search_is_sent_the_query_alone_and_says_what_it_cost() -> None:
    client = Client([{"url": "https://blog.example/a", "title": "שקשוקה"}])
    got = live.search(client, ("מתכונים ובישול",), "he")
    assert got.results == [live.Result("https://blog.example/a", "שקשוקה")]
    assert got.searches == 1
    assert got.cost == pytest.approx(20_000 * 2 / 1e6 + 50 * 10 / 1e6 + 0.01)
    sent = client.sent[0]
    assert sent["messages"] == [{"role": "user", "content": "Query: מתכונים ובישול"}]
    tool = sent["tools"][0]
    assert tool["type"] == live.TOOL and "user_location" not in tool
    assert "pornhub.com" in tool["blocked_domains"]
    assert "@" not in json.dumps(sent, ensure_ascii=False), "no address, no account"
    live.search(client, ("מתכונים ובישול", "כדורגל"), "he")
    two = client.sent[1]
    assert two["messages"] == [{"role": "user", "content": "Queries:\nמתכונים ובישול\nכדורגל"}]
    assert two["tools"][0]["max_uses"] == live.MAX_USES == 2, "one search a topic"


def test_a_look_is_off_until_both_switches_say_so_and_then_capped(
    store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    asked = live.queries(("food",), "he", 1)
    assert live.refused(store, 1, asked) == "off"
    monkeypatch.setenv(button.FLAG, "1")
    assert live.refused(store, 1, asked) == "off", "the button alone does not search"
    monkeypatch.setenv(live.FLAG, "1")
    assert live.refused(store, 1, asked) == ""
    assert live.refused(store, 1, ()) == "language"
    for _ in range(live.READER_DAY_MOST):
        live._count_reader(1, pool.now_ms())
    assert live.refused(store, 1, asked) == "reader"
    assert live.refused(store, 2, asked) == ""
    monkeypatch.setenv(pool.BUDGET_ENV, "0.1")
    assert live.refused(store, 2, asked) == "budget"
    monkeypatch.setenv(pool.BUDGET_ENV, "30")
    run = pool.start_run(store, live.RUN_SOURCE)
    pool.finish_run(store, run, note={"queries": list(asked)})
    assert live.refused(store, 2, asked) == "lately", "its pages are in the pool already"
    both = live.queries(("food", "football"), "he", 1)
    assert live.refused(store, 2, both) == "", "one of the two is new"
    assert live.unrun(store, both) == both[1:], "only the new one is bought"
    for _ in range(live.BOX_DAY_MOST):
        pool.start_run(store, live.RUN_SOURCE)
    assert live.refused(store, 2, live.queries(("law",), "he", 1)) == "box"


PAGE = " ".join(["עגבנייה"] * 3 + ["ביצה"] * 3 + [G1] * 89 + [G2] * 5)


def page_forms() -> score.Forms:
    words = ["עגבנייה", "ביצה", G1, G2, "שופט", "משטרה"]
    return score.Forms(
        language="he",
        forms={word: word for word in words},
        ranks={word: at + 1 for at, word in enumerate(words)},
    )


class Door:
    def __init__(self, pages: dict[str, str]) -> None:
        self.pages = pages
        self.asked: list[str] = []

    def __call__(self, url: str, *, proxy: bool) -> tuple[str, float]:
        self.asked.append(url)
        if url not in self.pages:
            raise RuntimeError("would not open")
        return self.pages[url], 0.0


def look_with(store: Store, results: list[str], door: Door) -> tuple[live.Look, list[int]]:
    look = live.Look(id="x", person=1, language="he", asked=("מתכונים ובישול",))
    searched = live.Searched(
        results=[live.Result(url, "שקשוקה") for url in results], searches=1, cost=0.05
    )
    added = live.top_up(
        store,
        look,
        ask=lambda asked, language: searched,
        read=door,
        robots=robots.Robots(read=lambda url: "User-agent: *\nDisallow: /no/\n"),
        forms_for=lambda language: page_forms(),
    )
    return look, added


def test_a_look_pools_what_passes_the_round_s_own_screens_and_targum_pays(store: Store) -> None:
    door = Door({"https://blog.example/a": PAGE, "https://blog.example/short": "ביצה " * 5})
    look, added = look_with(
        store,
        [
            "https://blog.example/a",
            "https://blog.example/short",
            "https://blog.example/no/b",
            "https://www.pornhub.com/x",
            "https://blog.example/gone",
        ],
        door,
    )
    assert len(added) == 1 and look.stage == "checking" and look.pages == 4
    found = pool.get(store, added[0])
    assert found is not None and found.source == "web" and found.url == "https://blog.example/a"
    assert found.rung is not None, "measured, so the button can offer it"
    assert not any("pornhub" in url or "/no/" in url for url in door.asked)
    run = store.db.execute(
        "SELECT source, spent, kept, dropped, note FROM find_run ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert run["source"] == "live" and run["spent"] == pytest.approx(0.05)
    assert json.loads(run["dropped"]) == {"host": 1, "robots": 1, "short": 1, "unreadable": 1}
    assert json.loads(run["note"])["queries"] == ["מתכונים ובישול"]
    assert store.db.execute("SELECT COUNT(*) FROM job").fetchone()[0] == 0, "never a job row"
    columns = {row[1] for row in store.db.execute("PRAGMA table_info(find_run)")}
    assert not columns & {"person", "reader", "owner"}, "no record of who looked"


# -- POST /find ------------------------------------------------------------------------


@pytest.fixture
def on(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv(button.FLAG, "1")
    file = tmp_path / "topics.json"
    file.write_text(
        json.dumps({"shown": ["food", "law"], "lemmas": {k: list(v) for k, v in LEMMAS.items()}}),
        encoding="utf-8",
    )
    monkeypatch.setenv(interests.ENV, str(file))
    monkeypatch.setattr(Store, "marked", lambda self, who, language: MARKED)
    monkeypatch.setattr(
        Store,
        "knowledge",
        lambda self, person, language: ([(k, v, "") for k, v in MARKED.items()], set(), set()),
    )


def test_the_button_is_off_until_the_deployment_says(home: Any) -> None:  # noqa: F811
    cookie = sign_in(home.port, home.postbox)
    assert call(home.port, "POST", "/find", {"language": "he"}, cookie=cookie)[0] == 404


def test_one_pick_from_the_pool_and_another_after_it(home: Any, on: None) -> None:  # noqa: F811
    cookie = sign_in(home.port, home.postbox)
    assert call(home.port, "POST", "/find", {"language": "he"})[0] == 401
    keep(home.store, "https://a.example/food", FOOD, title="שקשוקה")
    keep(home.store, "https://a.example/law", LAW, title="בית משפט")
    status, offered, _ = call(home.port, "POST", "/find", {"chips": True}, cookie=cookie)
    assert status == 200
    codes = [one["topic"] for one in offered["chips"]]
    assert codes == [chip.code for chip in chips.CHIPS], "nothing liked yet, so the list order"
    assert len(codes) == 40 and offered["chips"][0]["label"] == "Sport"
    assert not any(one["suggested"] for one in offered["chips"])
    status, got, _ = call(
        home.port, "POST", "/find", {"language": "he", "topics": ["food"]}, cookie=cookie
    )
    assert status == 200 and got["pick"]["url"] == "https://a.example/food"
    assert got["pick"]["chip"] == "food" and "because_topic_line" not in got["pick"]
    assert got["more"] == 0
    status, other, _ = call(
        home.port, "POST", "/find", {"language": "he", "skip": [got["pick"]["id"]]}, cookie=cookie
    )
    assert other["pick"]["url"] == "https://a.example/law"


def test_with_nothing_that_fits_a_look_runs_and_the_page_polls_it(
    home: Any,  # noqa: F811
    on: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cookie = sign_in(home.port, home.postbox)
    status, got, _ = call(home.port, "POST", "/find", {"language": "he"}, cookie=cookie)
    assert status == 200 and got["pick"] is None and got["why"] == "off"
    assert got["message"] == "No new text is 90% known for you yet."
    assert "nearest" not in got, "nothing named without the press's own body"

    monkeypatch.setenv(live.FLAG, "1")
    started = live.LOOKS.start

    def start(*args: Any, **kwargs: Any) -> live.Look:
        searched = live.Searched(results=[live.Result("https://blog.example/a", "שקשוקה")])
        return started(
            *args,
            ask=lambda asked, language: searched,
            read=Door({"https://blog.example/a": PAGE}),
            robots=robots.Robots(read=lambda url: ""),
            forms_for=lambda language: page_forms(),
            wait=True,
            **kwargs,
        )

    monkeypatch.setattr(live.LOOKS, "start", start)
    status, got, _ = call(
        home.port, "POST", "/find", {"language": "he", "topics": ["food"]}, cookie=cookie
    )
    assert status == 200 and got["stage"] == "done" and got["search"]
    status, polled, _ = call(home.port, "POST", "/find", {"search": got["search"]}, cookie=cookie)
    assert status == 200 and polled["pick"]["url"] == "https://blog.example/a"
    assert polled["pick"]["origin"] == "find" and polled["pick"]["collection"] == "find:web"
    assert live.reader_looks(home.store.person_by_email("reader@example.com").id) == 1
    other = call(home.port, "POST", "/find", {"search": "nobody"}, cookie=cookie)
    assert other[0] == 404


# -- the forty chips -------------------------------------------------------------------


def test_forty_chips_each_with_a_label_a_hebrew_phrase_and_at_most_a_shown_match() -> None:
    from targum import topics as topics_module
    from targum.strings import catalogue

    codes = [chip.code for chip in chips.CHIPS]
    assert len(codes) == 40 == len(set(codes))
    english = catalogue("en")
    for chip in chips.CHIPS:
        assert english[f"find.chip.{chip.code}"] == chip.label
        assert chip.phrases["he"] and not any(
            ch.isascii() and ch.isalpha() for ch in chip.phrases["he"]
        )
        assert chip.lexicon in ("", *topics_module.TOPICS)
    assert chips.matcher("cooking", ("food",)) == "food"
    assert chips.matcher("cooking", ()) == "", "a topic not shown does not match"
    assert chips.matcher("football", ("food", "law")) == ""


def test_the_reader_s_likely_chips_come_first() -> None:
    got = chips.ordered(("law", "food"))
    first = [(chip.code, suggested) for chip, suggested in got[:3]]
    assert first == [("crime", True), ("cooking", True), ("food", True)]
    assert len(got) == 40 and not any(suggested for _, suggested in got[3:])


def test_a_chip_the_lexicon_lacks_matches_only_what_a_look_brought_for_it(store: Store) -> None:
    keep(store, "https://a.example/plain", FOOD)
    keep(store, "https://a.example/ball", FOOD, topics=(chips.tag("football"),))
    got = button.ranked(store, button.Ask("he", chosen=("football",)), MARKED, known=lexicon())
    assert [row["url"] for row in got] == ["https://a.example/ball"]
    assert got[0]["chip"] == "football" and got[0]["topics"] == []


def test_a_look_tags_what_it_pools_and_what_the_pool_already_held(store: Store) -> None:
    held = keep(store, "https://news.example/held", FOOD, topics=("world",))
    look = live.Look(
        id="y", person=1, language="he", asked=("כדורגל",), tags=(chips.tag("football"),)
    )
    searched = live.Searched(
        results=[
            live.Result("https://news.example/held", ""),
            live.Result("https://b.example/a", ""),
        ]
    )
    added = live.top_up(
        store,
        look,
        ask=lambda asked, language: searched,
        read=Door({"https://b.example/a": PAGE}),
        robots=robots.Robots(read=lambda url: ""),
        forms_for=lambda language: page_forms(),
    )
    fresh = pool.get(store, added[0])
    old = pool.get(store, held)
    assert fresh is not None and fresh.topics == ("chip:football",)
    assert old is not None and old.topics == ("world", "chip:football")


# -- Stop, the looks left, and More that fit you ---------------------------------------


def test_stop_during_the_search_fetches_no_page_and_offers_nothing(store: Store) -> None:
    look = live.Look(id="z", person=1, language="he", asked=("כדורגל",))
    door = Door({"https://b.example/a": PAGE})

    def ask(asked: tuple[str, ...], language: str) -> live.Searched:
        look.stopped = True  # the reader pressed Stop while the search ran
        return live.Searched(results=[live.Result("https://b.example/a", "")], cost=0.05)

    added = live.top_up(
        store,
        look,
        ask=ask,
        read=door,
        robots=robots.Robots(read=lambda url: ""),
        forms_for=lambda language: page_forms(),
    )
    assert added == [] and door.asked == [], "no page after Stop"
    assert look.state()["stage"] == "stopped" and "pick" not in look.state()
    run = store.db.execute("SELECT spent, note FROM find_run").fetchone()
    assert run["spent"] == pytest.approx(0.05), "the search, once asked, is spent"
    assert json.loads(run["note"])["stopped"] == "the reader"


def test_looks_stop_only_for_the_reader_who_started_them(store: Store) -> None:
    looks = live.Looks()
    look = looks.start(
        store, 1, "he", ("q",), lambda: [], ask=lambda q, lang: live.Searched(), wait=False
    )
    assert looks.stop(look.id, 2) is None
    stopped = looks.stop(look.id, 1)
    assert stopped is not None and stopped.state()["stage"] in ("stopped", "done")
    assert live.looks_left(1) == live.READER_DAY_MOST - 1


def test_stop_and_the_looks_left_are_answered_by_post_find(
    home: Any,  # noqa: F811
    on: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cookie = sign_in(home.port, home.postbox)
    monkeypatch.setenv(live.FLAG, "1")
    held = live.Look(id="held", person=0, language="he", asked=("q",), stage="reading")
    person = home.store.person_by_email("reader@example.com")
    assert person is not None
    held.person = person.id
    live.LOOKS._held["held"] = held
    status, got, _ = call(home.port, "POST", "/find", {"stop": "held"}, cookie=cookie)
    assert status == 200 and got["stage"] == "stopped" and held.stopped
    assert got["left"] == live.READER_DAY_MOST
    assert call(home.port, "POST", "/find", {"stop": "nobody"}, cookie=cookie)[0] == 404


def test_more_that_fit_is_three_to_six_library_texts_in_the_band(
    home: Any,  # noqa: F811
    on: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from targum.chat import tools as chat_tools

    def rows(n: int, **more: Any) -> list[dict[str, Any]]:
        return [
            {"id": f"t{i}", "title": "ספר", "fit": "band",
             "reason": {"key": "suggest.known", "share": 95 - i}, **more}
            for i in range(n)
        ]  # fmt: skip

    offered: list[dict[str, Any]] = rows(8) + rows(1, origin="find") + [{"id": "u", "fit": "under"}]
    asked: list[dict[str, Any]] = []

    def suggest_next(ctx: Any, args: dict[str, Any]) -> dict[str, Any]:
        asked.append(args)
        if args.get("limit") == 1:
            return {"suggestions": [{"id": "card", "fit": "band"}]}
        return {"suggestions": offered}

    monkeypatch.setattr(chat_tools, "suggest_next", suggest_next)
    cookie = sign_in(home.port, home.postbox)
    status, got, _ = call(
        home.port,
        "POST",
        "/suggest",
        {"language": "he", "skip": ["done"], "more": True},
        cookie=cookie,
    )
    assert status == 200 and [row["id"] for row in got["more"]] == [f"t{i}" for i in range(6)]
    assert got["more"][0]["percent"] == 95
    assert asked[-1]["skip"] == ["done", "card"], "the card's own pick is left out"
    offered[:] = rows(2)
    status, got, _ = call(
        home.port, "POST", "/suggest", {"language": "he", "more": True}, cookie=cookie
    )
    assert got["more"] == [], "fewer than three draw no row"
    monkeypatch.delenv(button.FLAG)
    status, got, _ = call(
        home.port, "POST", "/suggest", {"language": "he", "more": True}, cookie=cookie
    )
    assert "more" not in got or got["more"] == []


# -- show me something harder (David, 2026-11-02; design.md §12) ------------------------

# 85% and 70% of their running words known: under the floor, the first the nearer miss.
NEAR = {"עגבנייה": 3, "ביצה": 3, G1: 79, G2: 15}
FAR = {"שופט": 3, "משטרה": 3, G1: 64, G2: 30}


def test_harder_is_the_finds_under_the_floor_nearest_miss_first(store: Store) -> None:
    keep(store, "https://a.example/band", FOOD)
    keep(store, "https://a.example/far", FAR)
    keep(store, "https://a.example/near", NEAR)
    plain = button.ranked(store, button.Ask("he"), MARKED, known=lexicon())
    assert [row["url"] for row in plain] == ["https://a.example/band"], "never unasked"
    got = button.ranked(store, button.Ask("he"), MARKED, known=lexicon(), harder=True)
    assert [row["url"] for row in got] == ["https://a.example/near", "https://a.example/far"]
    assert all(row["harder"] and row["fit"] == "under" for row in got)
    assert got[0]["miss"] == 0.05 and got[0]["known_share"] < 0.9
    steered = button.ranked(
        store, button.Ask("he", chosen=("crime",)), MARKED, known=lexicon(), harder=True
    )
    assert [row["url"] for row in steered] == ["https://a.example/far"], "on the topic only"


def test_harder_shelf_rows_join_the_finds_nearest_first_and_topic_inside_a_point() -> None:
    shelf = [
        {"id": "story", "fit": "under", "expected_share": 0.875, "kind": "story"},
        {"id": "law-talk", "fit": "under", "expected_share": 0.871, "about": ["law"]},
        {"id": "far-story", "fit": "under", "running_share": 0.6, "kind": "story"},
        {"id": "fits", "fit": "band", "expected_share": 0.93},
    ]
    found = [{"id": "find-1", "miss": 0.02, "on_topic": False, "harder": True}]
    got = button.nearest([*button.harder(shelf, button.Ask("he", liked=("law",))), *found])
    assert [row["id"] for row in got] == ["find-1", "law-talk", "story", "far-story"]
    assert all(row["harder"] for row in got)
    steered = button.harder(shelf, button.Ask("he", chosen=("crime",)), lexicon())
    assert [row["id"] for row in steered] == ["law-talk"]


def test_post_find_harder_walks_the_nearest_misses_and_never_looks(
    home: Any,  # noqa: F811
    on: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from targum.chat import tools as chat_tools

    monkeypatch.setenv(live.FLAG, "1")

    def no_look(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("a harder pick never searches the web")

    monkeypatch.setattr(live.LOOKS, "start", no_look)
    real = chat_tools.suggest_next
    asked: list[dict[str, Any]] = []

    def suggest_next(ctx: Any, args: dict[str, Any]) -> dict[str, Any]:
        if not args.get("under"):
            return real(ctx, args)
        asked.append(args)
        row = {
            "id": "shelf-story", "title": "סיפור", "language": "he", "kind": "story",
            "fit": "under", "expected_share": 0.88, "running_share": 0.8,
            "reason": {"key": "suggest.known", "share": 80}, "origin": "shelf",
        }  # fmt: skip
        return {"suggestions": [row] if row["id"] not in args.get("skip", []) else []}

    monkeypatch.setattr(chat_tools, "suggest_next", suggest_next)
    # Far enough under that the estimate of its unmarked words cannot lift it to the floor.
    keep(home.store, "https://a.example/near", FAR, title="שקשוקה")
    cookie = sign_in(home.port, home.postbox)
    body: dict[str, Any] = {"language": "he", "harder": True, "skip": [], "done": ["ruth-he"]}
    status, got, _ = call(home.port, "POST", "/find", body, cookie=cookie)
    assert status == 200 and got["harder"] is True
    assert got["pick"]["id"] == "shelf-story" and got["pick"]["harder"] is True
    assert got["more"] == 1 and "ruth-he" in asked[0]["skip"]
    body["skip"] = [got["pick"]["id"]]
    status, got, _ = call(home.port, "POST", "/find", body, cookie=cookie)
    assert got["pick"]["url"] == "https://a.example/near" and got["pick"]["harder"] is True
    body["skip"].append(got["pick"]["id"])
    status, got, _ = call(home.port, "POST", "/find", body, cookie=cookie)
    assert got["pick"] is None and got["why"] == "harder"
    assert got["message"] == "No other new text is close yet."
    assert "nearest" not in got, "no second offer once the misses are walked"


def test_an_empty_answer_names_the_text_the_harder_press_opens_first(
    home: Any,  # noqa: F811
    on: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """David, 2026-11-02 (design.md §12, "Show me something harder", the amendment): the
    empty card says where things stand, from the floor, and its press says the share known
    of the very text it opens. The figure comes with the empty answer, ranked from the
    press's own body (`near`); nothing is searched for it and nothing spends."""
    from targum.chat import tools as chat_tools

    monkeypatch.setenv(live.FLAG, "1")
    real = chat_tools.suggest_next

    def suggest_next(ctx: Any, args: dict[str, Any]) -> dict[str, Any]:
        if not args.get("under"):
            return real(ctx, args)
        rows = [
            {"id": "far-story", "title": "רחוק", "language": "he", "kind": "story",
             "fit": "under", "expected_share": 0.70, "running_share": 0.66,
             "reason": {"key": "suggest.known", "share": 66}, "origin": "shelf"},
            {"id": "near-talk", "title": "קרוב", "language": "he", "kind": "talk",
             "video": True, "fit": "under", "expected_share": 0.88, "running_share": 0.81,
             "reason": {"key": "suggest.known", "share": 81}, "origin": "shelf"},
        ]  # fmt: skip
        return {"suggestions": [row for row in rows if row["id"] not in args.get("skip", [])]}

    monkeypatch.setattr(chat_tools, "suggest_next", suggest_next)
    monkeypatch.setattr(live, "refused", lambda *args, **kwargs: "off")
    looks: list[Any] = []
    monkeypatch.setattr(live.LOOKS, "start", lambda *a, **k: looks.append(a))
    cookie = sign_in(home.port, home.postbox)
    near = {"topics": [], "skip": [], "done": ["ruth-he"]}
    status, got, _ = call(
        home.port, "POST", "/find", {"language": "he", "skip": [], "near": near}, cookie=cookie
    )
    assert status == 200 and got["pick"] is None and not looks
    assert got["message"] == "No new text is 90% known for you yet."
    assert got["nearest"]["id"] == "near-talk" and got["nearest"]["video"] is True
    assert got["nearest"]["reason"]["share"] == 81
    status, pressed, _ = call(
        home.port, "POST", "/find", {"language": "he", "harder": True, **near}, cookie=cookie
    )
    assert pressed["pick"]["id"] == got["nearest"]["id"]
    assert pressed["pick"]["reason"] == got["nearest"]["reason"]
    status, after, _ = call(
        home.port,
        "POST",
        "/find",
        {"language": "he", "near": {**near, "done": ["ruth-he", "near-talk"]}},
        cookie=cookie,
    )
    assert after["nearest"]["id"] == "far-story", "what the page set aside is not named"
    status, none, _ = call(
        home.port,
        "POST",
        "/find",
        {"language": "he", "near": {**near, "done": ["near-talk", "far-story"]}},
        cookie=cookie,
    )
    assert none["pick"] is None and "nearest" not in none, "no text under the floor, no press"


def test_a_look_that_finds_nothing_names_the_nearest_on_its_last_poll(
    home: Any,  # noqa: F811
    on: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from targum.chat import tools as chat_tools

    monkeypatch.setenv(live.FLAG, "1")
    real = chat_tools.suggest_next

    def suggest_next(ctx: Any, args: dict[str, Any]) -> dict[str, Any]:
        if not args.get("under"):
            return real(ctx, args)
        row = {"id": "near-story", "title": "קרוב", "language": "he", "kind": "story",
               "fit": "under", "expected_share": 0.87, "running_share": 0.8,
               "reason": {"key": "suggest.known", "share": 80}, "origin": "shelf"}  # fmt: skip
        return {"suggestions": [row]}

    monkeypatch.setattr(chat_tools, "suggest_next", suggest_next)
    started = live.LOOKS.start

    def start(*args: Any, **kwargs: Any) -> live.Look:
        return started(
            *args,
            ask=lambda asked, language: live.Searched(results=[]),
            robots=robots.Robots(read=lambda url: ""),
            forms_for=lambda language: page_forms(),
            wait=True,
            **kwargs,
        )

    monkeypatch.setattr(live.LOOKS, "start", start)
    cookie = sign_in(home.port, home.postbox)
    near = {"topics": [], "skip": [], "done": []}
    status, got, _ = call(
        home.port, "POST", "/find", {"language": "he", "near": near}, cookie=cookie
    )
    assert status == 200 and got["stage"] == "done" and got["pick"] is None
    assert got["nearest"]["id"] == "near-story"
    bare = call(home.port, "POST", "/find", {"search": got["search"]}, cookie=cookie)[1]
    assert bare["pick"] is None and "nearest" not in bare
    polled = call(
        home.port,
        "POST",
        "/find",
        {"search": got["search"], "language": "he", "near": near},
        cookie=cookie,
    )[1]
    assert polled["stage"] == "done" and polled["nearest"]["reason"]["share"] == 80
    assert polled["message"] == "No new text is 90% known for you yet."


def test_religion_matches_the_shelf_by_register_where_its_lexicon_topic_is_not_shown() -> None:
    """2026-11-03: the religion topic is not shown (its tags failed ling-he's gold set), so
    no shelf text could match the Religion chip and the press vanished with the Tanakh,
    the Mishnah and the siddur all under the floor. The chip matches the shelf by register;
    the shown lexicon topics still match as before."""
    shelf = [
        {"id": "news", "fit": "under", "expected_share": 0.88, "register": "modern"},
        {"id": "avot", "fit": "under", "expected_share": 0.86, "register": "rabbinic"},
        {"id": "ruth", "fit": "under", "expected_share": 0.80, "register": "biblical"},
        {"id": "kuzari", "fit": "under", "expected_share": 0.70, "register": "medieval"},
        {"id": "mapu", "fit": "under", "expected_share": 0.87, "register": "revival"},
    ]
    assert "religion" not in lexicon().shown
    got = button.nearest(button.harder(shelf, button.Ask("he", chosen=("religion",)), lexicon()))
    assert [row["id"] for row in got] == ["avot", "ruth", "kuzari"]
    assert all(row["on_topic"] for row in got)
    assert button.harder(shelf, button.Ask("he", chosen=("football",)), lexicon()) == []


def test_an_empty_answer_on_religion_names_the_nearest_religious_text(
    home: Any,  # noqa: F811
    on: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """David's card on 2026-11-03: Topic set to Religion, "No new text is 90% known for you
    yet." and no press, with religious texts under the floor on the shelf. The empty
    answer names the nearest of them, and the press opens it."""
    from targum.chat import tools as chat_tools

    monkeypatch.setenv(live.FLAG, "1")
    real = chat_tools.suggest_next

    def suggest_next(ctx: Any, args: dict[str, Any]) -> dict[str, Any]:
        if not args.get("under"):
            return real(ctx, args)
        rows = [
            {"id": "news-story", "title": "חדשות", "language": "he", "kind": "story",
             "register": "modern", "fit": "under", "expected_share": 0.89,
             "running_share": 0.85, "reason": {"key": "suggest.known", "share": 85},
             "origin": "shelf"},
            {"id": "avot-1", "title": "פרקי אבות", "language": "he", "kind": "story",
             "register": "rabbinic", "fit": "under", "expected_share": 0.84,
             "running_share": 0.78, "reason": {"key": "suggest.known", "share": 78},
             "origin": "shelf"},
            {"id": "ruth-1", "title": "רות", "language": "he", "kind": "story",
             "register": "biblical", "fit": "under", "expected_share": 0.75,
             "running_share": 0.7, "reason": {"key": "suggest.known", "share": 70},
             "origin": "shelf"},
        ]  # fmt: skip
        return {"suggestions": [row for row in rows if row["id"] not in args.get("skip", [])]}

    monkeypatch.setattr(chat_tools, "suggest_next", suggest_next)
    monkeypatch.setattr(live, "refused", lambda *args, **kwargs: "off")
    cookie = sign_in(home.port, home.postbox)
    near = {"topics": ["religion"], "skip": [], "done": []}
    ask = {"language": "he", "topics": ["religion"], "skip": [], "near": near}
    status, got, _ = call(home.port, "POST", "/find", ask, cookie=cookie)
    assert status == 200 and got["pick"] is None
    assert got["message"] == "No new text is 90% known for you yet."
    assert got["nearest"]["id"] == "avot-1", "the nearest on the topic, not the nearer news"
    assert got["nearest"]["reason"]["share"] == 78
    status, pressed, _ = call(
        home.port, "POST", "/find", {"language": "he", "harder": True, **near}, cookie=cookie
    )
    assert pressed["pick"]["id"] == "avot-1" and pressed["more"] == 1


def test_a_topic_with_nothing_under_the_floor_falls_back_to_any_topic_and_says_so(
    home: Any,  # noqa: F811
    on: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """David, 2026-11-03 (design.md §12): a chosen chip with nothing on it under the floor
    (no shown topic, no registers, nothing pooled) names the nearest text on any topic,
    marked `any_topic` so the press says so, and the press opens that text."""
    from targum.chat import tools as chat_tools

    monkeypatch.setenv(live.FLAG, "1")
    real = chat_tools.suggest_next

    def suggest_next(ctx: Any, args: dict[str, Any]) -> dict[str, Any]:
        if not args.get("under"):
            return real(ctx, args)
        rows = [
            {"id": "far-story", "title": "רחוק", "language": "he", "kind": "story",
             "register": "modern", "fit": "under", "expected_share": 0.70,
             "running_share": 0.66, "reason": {"key": "suggest.known", "share": 66},
             "origin": "shelf"},
            {"id": "news-story", "title": "חדשות", "language": "he", "kind": "story",
             "register": "modern", "fit": "under", "expected_share": 0.89,
             "running_share": 0.82, "reason": {"key": "suggest.known", "share": 82},
             "origin": "shelf"},
        ]  # fmt: skip
        return {"suggestions": [row for row in rows if row["id"] not in args.get("skip", [])]}

    monkeypatch.setattr(chat_tools, "suggest_next", suggest_next)
    monkeypatch.setattr(live, "refused", lambda *args, **kwargs: "off")
    cookie = sign_in(home.port, home.postbox)
    near = {"topics": ["football"], "skip": [], "done": []}
    ask = {"language": "he", "topics": ["football"], "skip": [], "near": near}
    status, got, _ = call(home.port, "POST", "/find", ask, cookie=cookie)
    assert status == 200 and got["pick"] is None
    assert got["nearest"]["id"] == "news-story" and got["nearest"]["any_topic"] is True
    assert got["nearest"]["reason"]["share"] == 82
    status, pressed, _ = call(
        home.port, "POST", "/find", {"language": "he", "harder": True, **near}, cookie=cookie
    )
    assert pressed["pick"]["id"] == "news-story" and pressed["more"] == 1
    # Where the topic has a text under the floor, only that, and no any-topic mark.
    on_topic = {**near, "topics": ["religion"]}
    rows = [{"id": "avot-1", "title": "פרקי אבות", "language": "he", "kind": "story",
             "register": "rabbinic", "fit": "under", "expected_share": 0.75,
             "running_share": 0.7, "reason": {"key": "suggest.known", "share": 70},
             "origin": "shelf"}]  # fmt: skip
    monkeypatch.setattr(
        chat_tools,
        "suggest_next",
        lambda ctx, args: {"suggestions": rows} if args.get("under") else real(ctx, args),
    )
    status, got, _ = call(
        home.port,
        "POST",
        "/find",
        {**ask, "topics": ["religion"], "near": on_topic},
        cookie=cookie,
    )
    assert got["nearest"]["id"] == "avot-1" and "any_topic" not in got["nearest"]
