"""Filter presses tallied with no reader, and the night's search leaning toward thin topics
(targum-internal#622; David, 2026-11-05; design.md §12, "The night's search leans toward
the topics readers ask for").

Offline: the search and the pages are fixtures. Every word is synthetic.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from test_find_button import on  # noqa: F401 - `on` is a fixture
from test_finds import home  # noqa: F401 - `home` is a fixture
from test_serve import call, sign_in

from targum.accounts import Store
from targum.finds import chips, pool, robots, score, steer, web

AT = int(datetime(2026, 11, 30, 0, 12, tzinfo=UTC).timestamp() * 1000)
LAST_MONTH = int(datetime(2026, 10, 3, tzinfo=UTC).timestamp() * 1000)
LONG_AGO = int(datetime(2026, 8, 3, tzinfo=UTC).timestamp() * 1000)


@pytest.fixture(autouse=True)
def clean(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(steer.FLAG, raising=False)
    monkeypatch.delenv(web.FLAG, raising=False)
    monkeypatch.delenv(pool.BUDGET_ENV, raising=False)


@pytest.fixture
def store(tmp_path: Path) -> Store:
    return Store(tmp_path / "targum.db")


def cells(store: Store) -> list[tuple[Any, ...]]:
    return [
        tuple(row)
        for row in store.db.execute(
            "SELECT month, language, medium, topic, rung, n FROM chip_press"
            " ORDER BY language, medium, topic, rung"
        )
    ]


def press(store: Store, topic: str, rung: int, n: int = 1, **more: Any) -> None:
    for _ in range(n):
        steer.count(
            store,
            language=more.get("language", "he"),
            medium=more.get("medium", ""),
            topic=topic,
            rung=rung,
            at=more.get("at", AT),
        )


# -- the count -----------------------------------------------------------------------


def test_off_nothing_is_counted(store: Store) -> None:
    assert not steer.on()
    assert not steer.count(store, language="he", medium="read", topic="sport", rung=2, at=AT)
    assert cells(store) == []


def test_a_press_adds_one_to_its_cell_and_names_nobody(
    store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(steer.FLAG, "1")
    press(store, "sport", 2, n=3, medium="read")
    press(store, "sport", 2, medium="watch")
    press(store, "nonsense", None, medium="sing")  # type: ignore[arg-type]
    month = pool.month_from(AT)
    assert cells(store) == [
        (month, "he", "", "", -1, 1),
        (month, "he", "read", "sport", 2, 3),
        (month, "he", "watch", "sport", 2, 1),
    ]
    columns = {row[1] for row in store.db.execute("PRAGMA table_info(chip_press)")}
    assert columns == {"month", "language", "medium", "topic", "rung", "n"}


def test_demand_is_reading_presses_this_month_and_the_last(
    store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(steer.FLAG, "1")
    press(store, "sport", 2, n=2, medium="read")
    press(store, "sport", 2, medium="", at=LAST_MONTH)
    press(store, "sport", 2, n=5, medium="watch")
    press(store, "sport", 2, n=9, at=LONG_AGO)
    press(store, "music", 1, n=4, language="ru")
    assert steer.demand(store, "he", AT) == {("sport", 2): 3}


# -- the weights ---------------------------------------------------------------------


def find(store: Store, n: int, rung: int, topic: str) -> None:
    pool.add(
        store,
        language="he",
        source="web",
        url=f"https://site.example/{topic}/{rung}/{n}",
        bag={"מילה": 100},
        tokens=100,
        unresolved=0,
        rung=rung,
        title="כותרת",
        topics=(chips.tag(topic),),
        at=AT - 1000,
    )


def test_a_topic_pressed_and_thin_weighs_and_one_held_well_does_not(
    store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(steer.FLAG, "1")
    press(store, "sport", 2, n=6)
    press(store, "music", 2, n=6)
    press(store, "art", 2, n=2)
    for n in range(steer.THIN):
        find(store, n, 2, "music")
    find(store, 0, 2, "sport")
    lean = steer.weights(store, "he", at=AT)
    assert lean == {"sport": 3.0, "art": 2.0}, "6 over 1+1, 2 over 1+0; music is held well"


def test_leaning_puts_the_heaviest_first_and_keeps_the_rest_in_turn() -> None:
    order = [("a", 1), ("b", 2), ("c", 3), ("d", 4)]
    assert steer.leaning(order, {"c": 2.0, "d": 5.0}) == [("d", 4), ("c", 3), ("a", 1), ("b", 2)]
    assert steer.leaning(order, {"c": 2.0, "d": 5.0}, most=1) == [
        ("d", 4),
        ("a", 1),
        ("b", 2),
        ("c", 3),
    ]
    assert steer.leaning(order, {}) == order


# -- the night -----------------------------------------------------------------------


def forms() -> score.Forms:
    return score.Forms(language="he", forms={"מילה": "מילה"}, ranks={"מילה": 1})


class Search:
    def __init__(self) -> None:
        self.asked: list[str] = []

    def __call__(self, query: str) -> web.Searched:
        self.asked.append(query)
        return web.Searched(hits=[], searches=1, cost=0.05)


def night(store: Store, ask: Search, **more: Any) -> web.Night:
    return web.refresh(
        store,
        ask=ask,
        read=lambda url: ("", 0),
        robots=robots.Robots(read=lambda url: ""),
        forms_for=lambda language: forms(),
        publishers=[],
        at=more.pop("at", AT),
        **more,
    )


def phrase(code: str) -> str:
    return chips.BY_CODE[code].phrases["he"]


def test_the_lean_moves_which_topics_the_same_dollar_buys(store: Store) -> None:
    plain = Search()
    first = night(store, plain, lean={})
    store2 = Store(store.path.with_name("other.db"))
    leant = Search()
    second = night(store2, leant, lean={"language": 1.0, "weather": 4.0})
    assert len(leant.asked) == len(plain.asked) and first.allowance == second.allowance
    assert second.spent == pytest.approx(first.spent)
    assert leant.asked[:2] == [phrase("weather"), phrase("language")]
    assert plain.asked[0] == chips.CHIPS[0].phrases["he"]
    assert phrase("weather") not in plain.asked, "the cap stops a plain night before it"


def test_the_rotation_moves_only_for_the_topics_it_reached(store: Store) -> None:
    ask = Search()
    night(store, ask, lean={"weather": 1.0, "language": 1.0})
    took = len(ask.asked) - 2
    import json

    (note,) = store.db.execute(
        "SELECT note FROM find_run WHERE source = 'web' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    said = json.loads(note)
    assert said["next"] == took and said["steered"] == ["weather", "language"]
    ask = Search()
    night(store, ask, lean={}, at=AT + pool.DAY_MS)
    assert ask.asked[0] == chips.CHIPS[took].phrases["he"]


def test_with_the_flag_off_the_night_does_not_lean(
    store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(steer.FLAG, "1")
    press(store, "weather", 0, n=5)
    monkeypatch.delenv(steer.FLAG)
    ask = Search()
    night(store, ask)
    assert ask.asked[0] == chips.CHIPS[0].phrases["he"]
    monkeypatch.setenv(steer.FLAG, "1")
    ask = Search()
    night(store, ask, at=AT + pool.DAY_MS)
    assert ask.asked[0] == phrase("weather")


# -- the press -----------------------------------------------------------------------


def test_a_filter_press_is_counted_and_an_ask_that_is_not_a_press_is_not(
    home: Any,  # noqa: F811
    on: None,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(steer.FLAG, "1")
    cookie = sign_in(home.port, home.postbox)
    body = {"language": "he", "topics": ["sport"], "medium": "read", "skip": [], "pressed": True}
    status, _, _ = call(home.port, "POST", "/find", body, cookie=cookie)
    assert status == 200
    body.pop("pressed")
    call(home.port, "POST", "/find", body, cookie=cookie)
    rows = cells(home.store)
    assert len(rows) == 1
    _, language, medium, topic, rung, n = rows[0]
    assert (language, medium, topic, n) == ("he", "read", "sport", 1)
    assert isinstance(rung, int)
    monkeypatch.delenv(steer.FLAG)
    call(home.port, "POST", "/find", {**body, "pressed": True}, cookie=cookie)
    assert cells(home.store)[0][-1] == 1, "off, nothing more is counted"


def test_the_page_says_pressed_on_a_pill_and_never_on_a_retry() -> None:
    script = (
        Path(__file__).resolve().parent.parent / "src/targum/render/assets/home.js"
    ).read_text(encoding="utf-8")
    assert script.count("askFind(pressedFilters())") == 2
    assert 'if (key !== "pressed") again[key] = body[key];' in script
