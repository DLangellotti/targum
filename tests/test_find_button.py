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
from targum.finds import button, interests, live, pool, robots, score

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
    assert steered[0]["because_topic"] == "food" and steered[0]["over"] is True
    assert steered[0]["fit"] == "band" and button.fits(steered)
    liked = button.ranked(store, button.Ask("he", liked=("law",)), MARKED, known=lexicon())
    assert [row["url"] for row in liked] == ["https://a.example/law", "https://a.example/food"]
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
    said = live.query(("food", "law"), "he", 1)
    allowed = {
        *live.TOPIC_WORDS["he"].values(),
        *(words for _, words in live.LEVEL_WORDS["he"]),
        live.KIND_WORDS["he"],
        "או",
    }
    pieces = set(said.split())
    assert pieces <= {word for phrase in allowed for word in phrase.split()}
    assert "מתכונים" in said and "בעברית קלה" in said
    assert "בעברית קלה" not in live.query(("food",), "he", 5), "a level past the easy rungs"
    assert live.query((), "he", None) == "כתבה על חיי היומיום בעברית קלה"
    assert live.query(("food",), "ru", 1) == "", "no words for the language, no look"


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
    got = live.search(client, "כתבה על מתכונים ובישול", "he")
    assert got.results == [live.Result("https://blog.example/a", "שקשוקה")]
    assert got.searches == 1
    assert got.cost == pytest.approx(20_000 * 2 / 1e6 + 50 * 10 / 1e6 + 0.01)
    sent = client.sent[0]
    assert sent["messages"] == [{"role": "user", "content": "Query: כתבה על מתכונים ובישול"}]
    tool = sent["tools"][0]
    assert tool["type"] == live.TOOL and "user_location" not in tool
    assert "pornhub.com" in tool["blocked_domains"]
    assert "@" not in json.dumps(sent, ensure_ascii=False), "no address, no account"


def test_a_look_is_off_until_both_switches_say_so_and_then_capped(
    store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    asked = live.query(("food",), "he", 1)
    assert live.refused(store, 1, asked) == "off"
    monkeypatch.setenv(button.FLAG, "1")
    assert live.refused(store, 1, asked) == "off", "the button alone does not search"
    monkeypatch.setenv(live.FLAG, "1")
    assert live.refused(store, 1, asked) == ""
    assert live.refused(store, 1, "") == "language"
    for _ in range(live.READER_DAY_MOST):
        live._count_reader(1, pool.now_ms())
    assert live.refused(store, 1, asked) == "reader"
    assert live.refused(store, 2, asked) == ""
    monkeypatch.setenv(pool.BUDGET_ENV, "0.1")
    assert live.refused(store, 2, asked) == "budget"
    monkeypatch.setenv(pool.BUDGET_ENV, "30")
    run = pool.start_run(store, live.RUN_SOURCE)
    pool.finish_run(store, run, note={"query": asked})
    assert live.refused(store, 2, asked) == "lately", "its pages are in the pool already"
    for _ in range(live.BOX_DAY_MOST):
        pool.start_run(store, live.RUN_SOURCE)
    assert live.refused(store, 2, live.query(("law",), "he", 1)) == "box"


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
    look = live.Look(id="x", person=1, language="he", asked="כתבה על מתכונים ובישול")
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
    assert json.loads(run["note"])["query"] == "כתבה על מתכונים ובישול"
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
    status, chips, _ = call(home.port, "POST", "/find", {"chips": True}, cookie=cookie)
    assert status == 200
    assert [one["topic"] for one in chips["chips"]] == ["food", "law"]
    assert chips["chips"][0]["label"] == "Food & drink"
    status, got, _ = call(
        home.port, "POST", "/find", {"language": "he", "topics": ["food"]}, cookie=cookie
    )
    assert status == 200 and got["pick"]["url"] == "https://a.example/food"
    assert got["pick"]["because_topic_line"] == "Because you read about food & drink"
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
    assert "couldn't find one" in got["message"]

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
