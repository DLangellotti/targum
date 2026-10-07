"""`scripts/eval_connector.py` with its scripted host (2026-10-06): no key, no network,
no cost. The paid run is by hand and never here; what is checked is that the host's
calls really go through `mcp_http.handle`, that the cap stops a run before a call it
cannot afford, that every scenario is on disk as soon as it ends, and that the rules
say what they mean."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "eval_connector.py"


@pytest.fixture(scope="module")
def ec() -> Any:
    spec = importlib.util.spec_from_file_location("eval_connector", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    # Registered before it runs: a dataclass looks its own module up by name.
    sys.modules["eval_connector"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def quick(ec: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """The build finishes at once, so the done scenario does not hold for four seconds."""
    original = ec.finish_build
    scenarios = tuple(
        one
        if one.name != "done"
        else ec.Scenario(one.name, one.turns, one.checks, setup=lambda world: original(world, 0.0))
        for one in ec.SCENARIOS
    )
    monkeypatch.setattr(ec, "SCENARIOS", scenarios)


def rows_in(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


# --- the run, end to end ------------------------------------------------------------


def test_a_dry_run_goes_through_the_connector_and_passes(
    ec: Any, quick: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from targum import mcp_http

    seen: list[str] = []
    real = mcp_http.handle

    def watched(message: dict[str, Any], **kw: Any) -> Any:
        seen.append(message["params"]["name"])
        assert kw["address"] == ec.ADDRESS and kw["scopes"] == ec.SCOPES
        return real(message, **kw)

    monkeypatch.setattr(mcp_http, "handle", watched)
    path, rows = ec.run(ec.DryHost(), into=tmp_path)
    assert seen == ["how_to_talk", "suggest_next", "check_job", "quote_build", "search_sources"]
    assert [row["scenario"] for row in rows] == ["talk", "next", "done", "ready", "news"]
    for row in rows:
        assert row["passed"], (row["scenario"], row["checks"])
        assert row["result_bytes"] > 0 and row["tool_calls"] == 1
        assert row["catalogue"].startswith("fixture")
    by = {row["scenario"]: row for row in rows}
    # The reply is built from what the tool really said: a short link off the real shelf,
    # the build's own `said`, and a press link on targum's origin.
    assert f"{ec.ADDRESS}/r/" in by["next"]["turns"][0]["reply"]
    assert "It's ready to read." in by["done"]["turns"][0]["reply"]
    assert f"{ec.ADDRESS}/build/" in by["ready"]["turns"][0]["reply"]
    assert by["talk"]["first_hebrew_s"] is not None
    # The culture item off the fabricated Russian feed, held to the topic.
    assert "https://news.example.org/ru/culture/101" in by["news"]["turns"][0]["reply"]
    written = rows_in(path)
    assert [row["scenario"] for row in written] == ["talk", "next", "done", "ready", "news"]
    assert all("_results" not in turn for row in written for turn in row["turns"])


def test_tools_are_the_connector_s_in_the_api_s_shape(ec: Any, tmp_path: Path) -> None:
    from targum import connector, mcp_http

    with ec.isolated(tmp_path):
        world = ec.build_world(tmp_path)
        shapes = ec.host_tools(world)
        exposed = [tool.name for tool in connector.exposed(ec.SCOPES, person=world.person)]
    assert [shape["name"] for shape in shapes] == exposed
    assert "search_sources" not in exposed, "no publishers' feeds fetched live"
    assert all(set(shape) == {"name", "description", "input_schema"} for shape in shapes)
    assert (
        "wait_seconds" in {s["name"]: s for s in shapes}["check_job"]["input_schema"]["properties"]
    ), "a host is offered what the box offers it"
    assert ec.host_system().endswith(f"{mcp_http.INSTRUCTIONS}\n</app>")


def test_the_cap_stops_a_run_before_a_call_it_cannot_afford(
    ec: Any, quick: None, tmp_path: Path
) -> None:
    host = ec.DryHost()
    path, rows = ec.run(host, cap=0.0001, into=tmp_path)
    assert host.calls == 0, "not one call made"
    assert len(rows) == 1 and rows[0]["stopped"].startswith("stopped before a call")
    assert rows[0]["checks"] == {} and not rows[0]["passed"]
    assert rows_in(path)[0]["stopped"], "the stop is written down too"


def test_the_cap_counts_what_was_already_spent(ec: Any) -> None:
    meter = ec.Meter(model="claude-sonnet-5-5", cap=1.0)
    # About $0.21 at worst: a thousand tokens sent, twenty thousand written.
    request = {"max_tokens": 20_000, "messages": [], "system": "x" * 2000}
    meter.allow(request)
    meter.add(SimpleNamespace(input_tokens=400_000, output_tokens=10_000))
    assert meter.spent == pytest.approx(0.9)
    with pytest.raises(ec.SpendCapReached):
        meter.allow(request)


def test_a_model_with_no_price_is_refused(ec: Any) -> None:
    with pytest.raises(SystemExit):
        ec.Meter(model="claude-unknown", cap=5.0)


def test_each_scenario_is_on_disk_before_the_next_is_asked(
    ec: Any, quick: None, tmp_path: Path
) -> None:
    class Breaks(ec.DryHost):  # type: ignore[name-defined,misc]
        def stream(self, **request: Any) -> Any:
            if "What should I read next?" in json.dumps(request["messages"][0], default=str):
                files = list(tmp_path.glob("*.jsonl"))
                assert files and [r["scenario"] for r in rows_in(files[0])] == ["talk"]
                raise RuntimeError("stopped here")
            return super().stream(**request)

    with pytest.raises(RuntimeError, match="stopped here"):
        ec.run(Breaks(), into=tmp_path)
    (written,) = tmp_path.glob("*.jsonl")
    assert [row["scenario"] for row in rows_in(written)] == ["talk"]


def test_only_runs_the_named_and_refuses_a_name_it_does_not_have(
    ec: Any, quick: None, tmp_path: Path
) -> None:
    _, rows = ec.run(ec.DryHost(), only=("ready",), into=tmp_path)
    assert [row["scenario"] for row in rows] == ["ready"]
    with pytest.raises(SystemExit):
        ec.run(ec.DryHost(), only=("nope",), into=tmp_path)


def test_main_dry_run_prints_the_table(
    ec: Any, quick: None, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert ec.main(["--dry-run", "--only", "next", "--out", str(tmp_path)]) == 0
    said = capsys.readouterr().out
    assert said.splitlines()[0].startswith("scenario")
    assert "next" in said and "pass" in said and "nothing spent" in said


def test_nothing_leaves_the_machine_for_a_pasted_link(ec: Any, tmp_path: Path) -> None:
    """The suite's own socket guard would fail this if `stubbed` let a fetch through."""
    with ec.isolated(tmp_path), ec.stubbed():
        world = ec.build_world(tmp_path)
        text, failed = ec.call_tool(world, 1, "describe_source", {"url": ec.LINK})
        assert not failed and json.loads(text)["kind"] == "article"
        text, failed = ec.call_tool(world, 2, "quote_build", {"source": ec.LINK})
    quoted = json.loads(text)["quote"]
    assert not failed and quoted["credits"] == 9 and quoted["open"].startswith(ec.ADDRESS)


# --- the rules ------------------------------------------------------------------------


def test_nikkud_ratio(ec: Any) -> None:
    assert ec.nikkud_ratio("שָׁלוֹם עוֹלָם") == 1.0
    assert ec.nikkud_ratio("שָׁלוֹם עולם") == 0.5
    assert ec.nikkud_ratio("hello") is None
    assert ec.nikkud_ratio("https://targum.page/r/abc שָׁלוֹם") == 1.0


def test_links_alone(ec: Any) -> None:
    link = "https://targum.page/r/abcdefgh"
    assert ec.links_alone(f"Esther is gentle.\n{link}")
    assert ec.links_alone(f"- {link}\n<{link}>\n[Esther]({link})")
    assert not ec.links_alone(f"Read it here: {link}")
    assert not ec.links_alone(f"{link} {link}")
    assert ec.links_alone("no links at all")


def test_money_and_presses(ec: Any) -> None:
    assert ec.money_words("It costs $3") and ec.money_words("Here's a quote")
    assert ec.money_words("the price is fine") and ec.money_words("₪12")
    assert not ec.money_words("It uses 9 credits.")
    assert ec.PRESS.search("Press the button") and not ec.PRESS.search("It's ready.")


def test_hebrew_words_said_leaves_out_their_line_and_the_meanings(ec: Any) -> None:
    reply = "> אֲנִי הָלַכְתִּי\n= I went\n~ Past tense.\nאֵיפֹה הָיִיתָ?\n= Where were you?"
    assert ec.hebrew_words_said(reply) == 2
    assert ec.meaning_lines(reply) == 2
    assert len(ec.lines(reply)) == 5


def turn(reply: str, events: list[list[Any]], tools: list[tuple[str, dict[str, Any], str]]) -> dict:
    return {
        "reply": reply,
        "events": events,
        "tools": [{"name": n, "arguments": a} for n, a, _ in tools],
        "_results": [(n, r) for n, _, r in tools],
    }


def test_talk_wants_the_contract_before_the_first_hebrew(ec: Any) -> None:
    good = "שָׁלוֹם! מָה שְׁלוֹמְךָ?\n= You can ask for the translation."
    first = turn(good, [["tool", "how_to_talk"], ["text", True]], [("how_to_talk", {}, "{}")])
    second = turn("> הָלַכְתִּי לַשּׁוּק\nמָה קָנִיתָ?", [["text", True]], [])
    checks = ec.check_talk([first, second])
    assert all(checks.values()), checks
    late = turn(good, [["text", True], ["tool", "how_to_talk"]], [("how_to_talk", {}, "{}")])
    assert not ec.check_talk([late, second])["how_to_talk_first"]
    translated = "\n".join(["שָׁלוֹם", "= Hello", "מָה נִשְׁמָע", "= How are you", "טוֹב", "= Good"])
    assert not ec.check_talk([turn(translated, first["events"], [])])["1_meaning_lines_at_most_2"]
    bare = turn("שלום מה שלומך", first["events"], [])
    assert not ec.check_talk([bare])["1_pointed"]


def test_next_wants_one_search_and_short_links(ec: Any) -> None:
    link = "https://targum.page/r/abcdefgh"
    one = turn(f"Esther.\n{link}", [], [("suggest_next", {}, "{}")])
    assert all(ec.check_next([one]).values())
    two = turn(f"Esther.\n{link}", [], [("suggest_next", {}, "{}"), ("search_my_shelf", {}, "{}")])
    assert not ec.check_next([two])["one_search"]
    # After #596 the connector lists `find_text` in place of the three.
    found = turn(f"Esther.\n{link}", [], [("find_text", {}, "{}")])
    assert ec.check_next([found])["one_search"]
    both = turn(f"Esther.\n{link}", [], [("find_text", {}, "{}"), ("suggest_next", {}, "{}")])
    assert not ec.check_next([both])["one_search"]
    long = turn(
        "Esther.\nhttps://targum.page/reader/%D7%90/reader/index.html",
        [],
        [("suggest_next", {}, "{}")],
    )
    assert not ec.check_next([long])["short_links"]


def test_done_wants_the_wait_and_the_said_line(ec: Any) -> None:
    said = json.dumps({"said": "It's ready to read.", "open": "https://targum.page/r/x"})
    good = turn(
        "It's ready to read.\nhttps://targum.page/r/x",
        [],
        [("check_job", {"id": "j", "wait_seconds": 20}, said)],
    )
    assert all(ec.check_done([good]).values()), ec.check_done([good])
    rushed = turn(good["reply"], [], [("check_job", {"id": "j"}, said)] * 3)
    checks = ec.check_done([rushed])
    assert not checks["waited"] and not checks["asked_at_most_twice"]
    reworded = turn(
        "Your text is done!\nhttps://targum.page/r/x",
        [],
        [("check_job", {"id": "j", "wait_seconds": 5}, said)],
    )
    assert not ec.check_done([reworded])["says_said"]


def test_ready_wants_the_link_alone_credits_and_no_quote(ec: Any) -> None:
    quoted = json.dumps({"quote": {"open": "https://targum.page/build/abc", "credits": 9}})
    good = turn(
        "A morning at the market, and it uses 9 credits.\nhttps://targum.page/build/abc",
        [],
        [("quote_build", {"source": "x"}, quoted)],
    )
    assert all(ec.check_ready([good]).values()), ec.check_ready([good])
    bad = turn(
        "Here's your quote, press Confirm: https://targum.page/build/abc",
        [],
        [("quote_build", {"source": "x"}, quoted)],
    )
    checks = ec.check_ready([bad])
    assert not checks["links_alone"] and not checks["no_money_or_quote"]
    assert not checks["nothing_to_press"] and not checks["says_credits"]


def test_only_the_news_scenario_follows_publishers(ec: Any, tmp_path: Path) -> None:
    """2026-10-07: `followed` lists search_sources for the news scenario and puts the
    world back after, so the other scenarios are measured as they were."""
    with ec.isolated(tmp_path):
        world = ec.build_world(tmp_path)
        with ec.followed(world):
            inside = {shape["name"] for shape in ec.host_tools(world)}
            text, failed = ec.call_tool(
                world, 1, "search_sources", {"language": "ru", "topic": "culture"}
            )
        outside = {shape["name"] for shape in ec.host_tools(world)}
    assert "search_sources" in inside and "search_sources" not in outside
    assert not failed
    assert [row["link"] for row in json.loads(text)["items"]] == [
        "https://news.example.org/ru/culture/101"
    ]


def test_news_wants_search_sources_first_held_to_russian_and_a_feed_article(ec: Any) -> None:
    link = "https://news.example.org/ru/culture/101"
    found = json.dumps({"items": [{"title": "Выставка", "link": link}]})
    asked = {"language": "ru", "topic": "culture"}
    good = turn(f"Выставка\n{link}", [], [("search_sources", asked, found)])
    assert all(ec.check_news([good]).values()), ec.check_news([good])
    by_words = turn(
        good["reply"], [], [("search_sources", {"language": "ru", "query": "выставка"}, found)]
    )
    assert ec.check_news([by_words])["held_to_culture"]
    elsewhere = "https://tsn.example/ru/article"
    web = turn(
        f"An article\n{elsewhere}",
        [],
        [("describe_source", {"url": elsewhere}, "{}"), ("search_sources", asked, found)],
    )
    checks = ec.check_news([web])
    assert not checks["search_sources_first"] and not checks["only_links_it_found"]
    assert not checks["offers_a_feed_article"]
    hebrew = turn(good["reply"], [], [("search_sources", {"topic": "culture"}, found)])
    assert not ec.check_news([hebrew])["held_to_russian"]
