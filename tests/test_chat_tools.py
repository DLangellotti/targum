"""The chat's tools, run against a real store and a real shelf.

Ownership is the headline: every tool reads whose shelf and whose words from the context
the server built, and nothing a model passes as an argument can name somebody else.
"""

from __future__ import annotations

import json
import re
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from targum import level
from targum.accounts import Person, Store
from targum.chat import tools
from targum.serve import Job, Library


def signed_in(store: Store, email: str) -> Person:
    token = store.start_sign_in(email)
    signed = store.finish_sign_in(token)
    assert signed is not None
    return signed[0]


def built(home: Path, name: str, source: str, lemmas: list[str], title: str = "A text") -> None:
    """Enough of a targum on disk for the shelf to list it and coverage to measure it."""
    folder = home / name
    (folder / "reader").mkdir(parents=True)
    (folder / "reader" / "index.html").write_text("<html></html>", encoding="utf-8")
    (folder / "document.json").write_text(
        json.dumps(
            {
                "title": title,
                "language": "he",
                "source": source,
                "content_hash": "h",
                "blocks": [{"text": " ".join(lemmas)}],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (folder / "annotation.json").write_text(
        json.dumps(
            {"tokens": {"0001.001-a": [{"lemma": lemma, "pos": "NOUN"} for lemma in lemmas]}},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


@pytest.fixture
def world(tmp_path: Path) -> tuple[Library, Store, Person, Path]:
    store = Store(tmp_path / "words.db")
    out = tmp_path / "out"
    out.mkdir()
    library = Library(out, store=store)
    person = signed_in(store, "reader@example.com")
    home = library.home(person)
    built(home, "ruth-he", "test:ruth", ["שלום", "בית", "מלך", "ספר"], "רות")
    built(library.shared, "esther-he", "test:esther", ["שלום", "רעב"], "אסתר")
    store.push(
        person,
        {
            "words": [
                {
                    "language": "he",
                    "lemma": "שלום",
                    "status": 9,
                    "band": "easy",
                    "at": 2,
                    "seen": 2,
                },
                {"language": "he", "lemma": "בית", "status": 9, "band": "easy", "at": 3, "seen": 3},
                {
                    "language": "he",
                    "lemma": "מלך",
                    "status": 2,
                    "band": "moderate",
                    "at": 4,
                    "seen": 4,
                },
            ]
        },
    )
    return library, store, person, home


def context(library: Library, store: Store, person: Person | None, home: Path) -> tools.Ctx:
    return tools.Ctx(
        person=person,
        home=home,
        library=library,
        store=store,
        chat_id="c1",
        level=level.snapshot(store, person.id if person else None, "he"),
    )


def test_every_tool_has_a_closed_schema_and_a_distinct_name() -> None:
    names = [tool.name for tool in tools.REGISTRY]
    assert len(names) == len(set(names))
    for tool in tools.REGISTRY:
        assert tool.schema["additionalProperties"] is False, tool.name
        assert tool.description, tool.name
    for shape in tools.anthropic_tools():
        assert set(shape) == {"name", "description", "input_schema"}


def test_search_library_measures_what_is_on_the_shelf(world) -> None:
    library, store, person, home = world
    ctx = context(library, store, person, home)
    got = tools.search_library(ctx, {"register": "biblical"})
    by_id = {row["id"]: row for row in got["texts"]}
    assert set(by_id) >= {"ruth", "esther"}, "the fixture catalogue's biblical shelf"
    assert by_id["ruth"]["on_shelf"] is True
    assert by_id["ruth"]["reader"] == "/reader/ruth-he/reader/index.html"
    assert by_id["ruth"]["known_share"] == pytest.approx(0.5), "two of four lemmas known"
    assert by_id["esther"]["on_shelf"] is True, "the shared shelf counts as built"
    assert by_id["esther"]["known_share"] == pytest.approx(0.5)
    assert all(row["register"] == "biblical" for row in got["texts"])


def test_search_library_filters_and_says_how_many(world) -> None:
    library, store, person, home = world
    ctx = context(library, store, person, home)
    everything = tools.search_library(ctx, {"limit": 20})
    modern = tools.search_library(ctx, {"register": "modern"})
    assert 0 < modern["count"] < everything["count"]
    assert tools.search_library(ctx, {"query": "no such text anywhere"})["count"] == 0
    assert tools.search_library(ctx, {"query": "Declaration"})["count"] >= 1


def test_open_library_text_says_how(world) -> None:
    library, store, person, home = world
    ctx = context(library, store, person, home)
    ruth = tools.open_library_text(ctx, {"id": "ruth"})
    assert ruth["reader"] and "link" in ruth["how_to_open"]
    unbuilt = next(
        row for row in tools.search_library(ctx, {"limit": 20})["texts"] if not row["on_shelf"]
    )
    told = tools.open_library_text(ctx, {"id": unbuilt["id"]})
    assert told["reader"] == ""
    # quote_build is offered only with the chat scope, so the way in is conditional.
    assert "If quote_build is among your tools" in told["how_to_open"]
    assert f"/library/{unbuilt['id']}" in told["how_to_open"]
    assert "error" in tools.open_library_text(ctx, {"id": "nope"})


def test_my_shelf_is_mine_and_the_shared_one(world) -> None:
    library, store, person, home = world
    ctx = context(library, store, person, home)
    got = tools.search_my_shelf(ctx, {})
    names = {row["name"]: row for row in got["texts"]}
    assert set(names) == {"ruth-he", "esther-he"}
    assert names["ruth-he"]["shared"] is False and names["esther-he"]["shared"] is True
    assert names["ruth-he"]["known_share"] == pytest.approx(0.5)
    assert tools.search_my_shelf(ctx, {"query": "רות"})["count"] == 1


def test_my_shelf_says_when_each_text_was_read(world) -> None:
    """ "What was the last targum I read?" was answered "the list does not keep times"
    (2026-09-08). The reader's sync had always written when a text was opened and
    finished; the tool now hands them over, newest opened first."""
    library, store, person, home = world
    ctx = context(library, store, person, home)
    hashes = {row["name"]: row["document"] for row in library.readers(home)}
    assert hashes["ruth-he"], "the fixture reader carries its document hash"
    before = tools.search_my_shelf(ctx, {})
    assert {row["last_opened"] for row in before["texts"]} == {""}, "nothing opened yet"
    assert before["now"].endswith("+00:00")
    store.push(
        person,
        {
            "docs": [
                {
                    "hash": hashes["ruth-he"],
                    "title": "Ruth",
                    "language": "he",
                    "updated": 1_788_000_000_000,
                    "opened": 1_788_000_000_000,
                    "done": 0,
                    "seen": 1_788_000_000_000,
                }
            ],
            "sections": [
                {"hash": hashes["ruth-he"], "section": "2", "at": 1_788_001_000_000, "seen": 2}
            ],
        },
    )
    got = tools.search_my_shelf(ctx, {})
    assert got["texts"][0]["name"] == "ruth-he", "the last one opened comes first"
    ruth = got["texts"][0]
    assert ruth["last_opened"] == "2026-08-29T10:40+00:00"
    assert ruth["finished"] == "2026-08-29T10:56+00:00", "the last chapter finished"
    assert isinstance(ruth["days_since_opened"], int) and ruth["days_since_opened"] >= 0
    # (The fixture's two readers are built from one document and share its hash, so
    # the never-opened case is the `before` assertion above, not Esther's row here.)


def test_another_reader_sees_neither_my_shelf_nor_my_words(world) -> None:
    library, store, person, home = world
    other = signed_in(store, "other@example.com")
    ctx = context(library, store, other, library.home(other))
    mine = tools.search_my_shelf(ctx, {})
    assert [row["name"] for row in mine["texts"]] == ["esther-he"], "the shared shelf only"
    assert mine["texts"][0]["known_share"] == pytest.approx(0.0)
    assert tools.my_vocabulary(ctx, {})["known"] == 0
    assert tools.my_progress(ctx, {})["known"] == 0


# --- find_text: the connector's one finding tool (design.md §12, 2026-10-06) --------


def test_find_text_with_nothing_asked_is_what_suggest_next_says(world) -> None:
    library, store, person, home = world
    ctx = context(library, store, person, home)
    got = tools.find_text(ctx, {})
    suggested = tools.suggest_next(ctx, {"limit": tools.FIND_LIMIT})["suggestions"]
    assert got["texts"] == [{"from": "library", **row} for row in suggested]
    assert got["count"] == len(suggested)


def test_find_text_for_mine_is_what_my_shelf_says(world) -> None:
    library, store, person, home = world
    ctx = context(library, store, person, home)
    got = tools.find_text(ctx, {"where": "mine"})
    shelf = tools.search_my_shelf(ctx, {"limit": tools.FIND_LIMIT})
    assert got["texts"] == [{"from": "mine", **row} for row in shelf["texts"]]
    assert got["count"] == shelf["count"] and got["now"]


def test_find_text_with_a_query_puts_mine_first_and_each_text_once(world) -> None:
    library, store, person, home = world
    ctx = context(library, store, person, home)
    got = tools.find_text(ctx, {"query": "ruth"})
    assert got["texts"][0]["from"] == "mine" and got["texts"][0]["name"] == "ruth-he"
    library_ids = [row.get("id") for row in got["texts"] if row["from"] == "library"]
    assert "ruth" not in library_ids, "on the shelf already, so it is the shelf's row"
    readers = [row["reader"] for row in got["texts"] if row["reader"]]
    assert len(readers) == len(set(readers))
    assert got["count"] == len(got["texts"])
    only_library = tools.find_text(ctx, {"query": "ruth", "where": "library"})
    assert [row["from"] for row in only_library["texts"]] == ["library"] * len(
        only_library["texts"]
    )
    assert "ruth" in [row["id"] for row in only_library["texts"]]


def test_find_text_holds_a_named_text_to_no_ceiling(world, monkeypatch) -> None:
    """A text asked for by name is the one wanted, however hard it is."""
    library, store, person, home = world
    ctx = context(library, store, person, home)
    asked: list[dict[str, Any]] = []
    monkeypatch.setattr(
        tools, "search_library", lambda ctx, args: asked.append(args) or {"count": 0, "texts": []}
    )
    tools.find_text(ctx, {"query": "anything", "where": "library", "register": "biblical"})
    assert asked[0]["max_looked_up_percent"] == 100 and asked[0]["register"] == "biblical"


def test_find_text_with_a_kind_ranks_the_library_s_way(world) -> None:
    """`suggest_next` takes no kind, so a kind asked for is the library's own order."""
    library, store, person, home = world
    ctx = context(library, store, person, home)
    kind = tools.search_library(ctx, {"limit": 1})["texts"][0]["kind"]
    got = tools.find_text(ctx, {"kind": kind})
    assert got["texts"] and all(row["kind"] == kind for row in got["texts"])
    assert got["texts"] == [
        {"from": "library", **row}
        for row in tools.search_library(ctx, {"kind": kind, "limit": 10})["texts"]
    ]


def test_find_text_without_the_record_sees_only_the_library(world) -> None:
    library, store, person, home = world
    ctx = replace(context(library, store, person, home), sees_record=False)
    assert "doesn't share" in tools.find_text(ctx, {"where": "mine"})["error"]
    found = tools.find_text(ctx, {"query": "ruth"})
    assert found["texts"] and {row["from"] for row in found["texts"]} == {"library"}
    assert "now" not in found, "nothing of the shelf's was read"
    ranked = tools.find_text(ctx, {})
    assert ranked["texts"] == [
        {"from": "library", **row} for row in tools.search_library(ctx, {"limit": 10})["texts"]
    ], "gentlest first, not ranked by what the reader has read"


def test_find_text_is_the_connector_s_and_the_three_are_the_chat_s() -> None:
    from targum import connector

    here = {shape["name"] for shape in tools.anthropic_tools()}
    assert {"search_library", "search_my_shelf", "suggest_next"} <= here
    assert "find_text" not in here, "the chat's page draws the three by name"
    for scopes in (None, "library", "library record", "library record check"):
        there = {tool.name for tool in connector.exposed(scopes, person=None)}
        assert "find_text" in there, scopes
        assert not there & {"search_library", "search_my_shelf", "suggest_next"}, scopes
    calling = {tool.name for tool in connector.exposed("library", calling=True)}
    assert "search_library" in calling and "search_my_shelf" not in calling


def test_a_host_on_its_first_day_is_sent_to_find_text(world) -> None:
    library, store, person, home = world
    other = signed_in(store, "first-day@example.com")
    ctx = context(library, store, other, library.home(other))
    contract = tools.how_to_talk(ctx, {})["contract"]
    assert "(find_text)" in contract and "suggest_next" not in contract
    from targum.chat import hebrew

    assert "(suggest_next)" in hebrew.ledger_block(level.EMPTY, [], []), "the chat's own"


def test_vocabulary_and_progress_are_counts(world) -> None:
    library, store, person, home = world
    ctx = context(library, store, person, home)
    words = tools.my_vocabulary(ctx, {"limit": 2})
    assert (words["known"], words["learning"]) == (2, 1)
    assert [w["lemma"] for w in words["recent"]] == ["מלך", "בית"], "newest first"
    progress = tools.my_progress(ctx, {})
    assert progress["known"] == 2
    assert progress["ladder"]["note"] == "A guide, not a placement."


def test_suggest_next_leaves_out_what_is_already_mine(world) -> None:
    library, store, person, home = world
    ctx = context(library, store, person, home)
    got = tools.suggest_next(ctx, {"limit": 10})
    ids = [row["id"] for row in got["suggestions"]]
    assert "ruth" not in ids, "already on the reader's own shelf"
    assert ids[0] == "esther", "measured coverage ranks ahead of a guess"
    assert all(row["because"] for row in got["suggestions"])
    # Said the way the card says it: a host repeats `because`, and never a percentage.
    assert got["suggestions"][0]["because"] == got["suggestions"][0]["known_line"]
    assert "%" not in got["suggestions"][0]["because"]
    assert got["suggestions"][0]["reason"]["share"] == 50, "the page's own line keeps it"


def test_check_job_answers_only_for_the_owner(world) -> None:
    library, store, person, home = world
    theirs = Job(id="j-theirs", source="x", owner=person.id + 1, stage="working")
    mine = Job(
        id="j-mine", source="x", owner=person.id, stage="done", reader="ruth-he/reader/index.html"
    )
    library.jobs.update({theirs.id: theirs, mine.id: mine})
    ctx = context(library, store, person, home)
    assert "error" in tools.check_job(ctx, {"id": "j-theirs"})
    got = tools.check_job(ctx, {"id": "j-mine"})
    assert got["stage"] == "done" and got["open"] == "/reader/ruth-he/reader/index.html"


def test_check_job_says_how_far_a_build_has_got_and_how_long_is_left(world) -> None:
    import time

    library, store, person, home = world
    job = Job(id="j-run", source="x", owner=person.id, stage="working", done=30, total=80)
    # Thirty sentences in sixty seconds: fifty more is a hundred seconds.
    job.started = int(time.time() * 1000) - 60_000
    library.jobs[job.id] = job
    got = tools.check_job(context(library, store, person, home), {"id": "j-run"})
    assert got["done"] == 30 and got["total"] == 80 and got["unit"] == "sentences"
    assert 95 <= got["seconds_left"] <= 105
    assert got["said"] == "30 of 80 sentences ready, about 2 minutes left."
    assert "!" not in got["said"] and "$" not in got["said"]


def test_check_job_says_no_time_left_where_there_is_nothing_to_count_from(world) -> None:
    import time

    library, store, person, home = world
    ctx = context(library, store, person, home)
    # Never seen to start (read back after a restart), nothing done yet, and too soon.
    unseen = Job(id="j-unseen", source="x", owner=person.id, stage="working", done=5, total=9)
    nothing = Job(id="j-nothing", source="x", owner=person.id, stage="working", total=9)
    nothing.started = int(time.time() * 1000) - 60_000
    early = Job(id="j-early", source="x", owner=person.id, stage="working", done=1, total=9)
    early.started = int(time.time() * 1000) - 1_000
    library.jobs.update({one.id: one for one in (unseen, nothing, early)})
    for one in (unseen, nothing, early):
        got = tools.check_job(ctx, {"id": one.id})
        assert "seconds_left" not in got, one.id
        assert "left" not in got["said"] and got["said"].endswith("sentences ready."), one.id
    book = Job(id="j-book", source="x", owner=person.id, stage="working", done=2, total=9)
    book.chapters = 12
    library.jobs[book.id] = book
    assert tools.check_job(ctx, {"id": "j-book"})["said"] == (
        "The first chapter: 2 of 9 sentences ready."
    )


def test_check_job_starts_the_clock_when_the_build_starts_working(world) -> None:
    library, store, person, home = world
    job = Job(id="j-clock", source="x", owner=person.id, stage="queued")
    library.remember(job)
    assert job.started == 0, "waiting in line is not working"
    job.stage = "working"
    library.remember(job)
    first = job.started
    assert first > 0
    library.remember(job)
    assert job.started == first, "stamped once"


def test_check_job_says_how_many_texts_are_ahead_in_the_line(world) -> None:
    library, store, person, home = world
    ahead = Job(id="j-ahead", source="x", owner=person.id + 1, stage="working", made=1)
    mine = Job(id="j-line", source="x", owner=person.id, stage="queued", made=2)
    for one in (ahead, mine):
        library.jobs[one.id] = one
        library.remember(one)
    got = tools.check_job(context(library, store, person, home), {"id": "j-line"})
    assert got["behind"] == 1
    assert got["said"] == "It's waiting to start, behind 1 other text."


def test_check_job_hands_over_the_link_when_done_and_a_sentence_when_failed(world) -> None:
    library, store, person, home = world
    ctx = context(library, store, person, home)
    done = Job(
        id="j-done", source="x", owner=person.id, stage="done", reader="ruth-he/reader/index.html"
    )
    failed = Job(
        id="j-failed",
        source="x",
        owner=person.id,
        stage="failed",
        error="We couldn't open that link. Check it and try again.",
    )
    quiet = Job(id="j-quiet", source="x", owner=person.id, stage="failed")
    library.jobs.update({one.id: one for one in (done, failed, quiet)})
    got = tools.check_job(ctx, {"id": "j-done"})
    assert got["said"] == "It's ready to read."
    assert got["open"] == "/reader/ruth-he/reader/index.html"
    assert "seconds_left" not in got
    got = tools.check_job(ctx, {"id": "j-failed"})
    assert got["said"] == (
        "We couldn't get it ready. We couldn't open that link. Check it and try again. "
        "Nothing was used."
    )
    assert "open" not in got
    assert "Try again later" in tools.check_job(ctx, {"id": "j-quiet"})["said"]


def test_a_check_job_that_works_is_not_a_failed_call_over_the_connector(world) -> None:
    """2026-10-06, the connector eval: a job's state carries `"error": ""`, and `run`
    took the key for a failure, so every `check_job` reached a host — and targum's own
    chat — as `isError`. Failure is an error that says something."""
    from targum import mcp_http

    library, store, person, home = world
    working = Job(id="j-working", source="x", owner=person.id, stage="working", done=4, total=9)
    done = Job(
        id="j-ok", source="x", owner=person.id, stage="done", reader="ruth-he/reader/index.html"
    )
    failed = Job(id="j-broke", source="x", owner=person.id, stage="failed", error="It broke.")
    library.jobs.update({one.id: one for one in (working, done, failed)})

    def called(job_id: str) -> dict[str, Any]:
        answered = mcp_http.handle(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "check_job", "arguments": {"id": job_id}},
            },
            library=library,
            store=store,
            person=person,
            scopes="library record",
            address="https://targum.page",
        )
        assert answered is not None
        return dict(answered["result"])

    for job_id in ("j-working", "j-ok"):
        result = called(job_id)
        assert result["isError"] is False, job_id
        assert json.loads(result["content"][0]["text"])["error"] == "", "the key is still there"
    assert called("j-nobody")["isError"] is True, "a real error still is one"
    assert called("j-broke")["isError"] is True, "and so is a build that failed"
    # targum's own chat reads the same flag.
    ctx = context(library, store, person, home)
    assert tools.run("check_job", {"id": "j-working"}, ctx)[1] is False
    assert tools.run("check_job", {"id": "j-nobody"}, ctx)[1] is True


def test_check_job_says_it_in_the_language_the_card_is_drawn_in(world) -> None:
    """2026-10-06: a Russian card had Russian labels over an English line. `said` now
    takes the card's own rule (`strings.drawn_in`), with Russian's three counted forms,
    and a reader who reads only English is told exactly what they were told before."""
    import time

    library, store, person, home = world
    ctx = replace(context(library, store, person, home), said_reads={"en", "ru"})

    def said(job: Job) -> str:
        library.jobs[job.id] = job
        return str(tools.check_job(ctx, {"id": job.id})["said"])

    running = Job(id="j-ru", source="x", owner=person.id, stage="working", done=30, total=80)
    running.started = int(time.time() * 1000) - 60_000
    assert said(running) == "Готово: 30 из 80 предложений, осталось около 2 минут."
    one = Job(id="j-ru-21", source="x", owner=person.id, stage="working", done=3, total=21)
    one.chapters = 4
    assert said(one) == "Первая глава. Готово: 3 из 21 предложения."
    assert said(Job(id="j-ru-done", source="x", owner=person.id, stage="done")) == ("Можно читать.")
    failed = said(Job(id="j-ru-failed", source="x", owner=person.id, stage="failed"))
    assert failed.startswith("Не получилось") and failed.endswith("Кредиты не списаны.")
    for count, form in ((1, "текст."), (3, "текста."), (5, "текстов."), (11, "текстов.")):
        assert tools._counted(
            "ru", "job.said.behind", count, "{n} other text.", "{n} other texts."
        ).endswith(f"{count} {form}")
    assert tools._in_words(30 * 60, "ru") == "осталось около 30 минут"
    assert tools._in_words(21 * 60, "ru") == "осталось около 21 минуты"

    english = replace(ctx, said_reads={"en"})
    assert tools.check_job(english, {"id": "j-ru"})["said"] == (
        "30 of 80 sentences ready, about 2 minutes left."
    )
    for job in (running, one):
        assert "!" not in said(job)


def away(library: Library, store: Store, person: Person, home: Path) -> tools.Ctx:
    """A connector's context: no conversation of targum's own, as `connector.context`."""
    ctx = context(library, store, person, home)
    ctx.chat_id = ""
    return ctx


def test_check_job_never_holds_targums_own_chat(world, monkeypatch) -> None:
    library, store, person, home = world
    job = Job(id="j-here", source="x", owner=person.id, stage="working", done=1, total=4)
    library.jobs[job.id] = job
    naps: list[float] = []
    monkeypatch.setattr(tools, "_sleep", naps.append)
    got = tools.check_job(
        context(library, store, person, home), {"id": "j-here", "wait_seconds": 20}
    )
    assert not naps and got["done"] == 1, "a turn here answers at once"
    shapes = {shape["name"]: shape for shape in tools.anthropic_tools()}
    assert "wait_seconds" not in shapes["check_job"]["input_schema"]["properties"]
    assert shapes["check_job"]["input_schema"]["required"] == ["id"]
    assert "wait_seconds" in tools.BY_NAME["check_job"].schema["properties"], "hosts keep it"


def test_check_job_asks_a_host_to_wait_and_to_say_said_as_it_is() -> None:
    """2026-10-06, the connector eval: the host left wait_seconds out and retold `said`
    in its own words. The schema says both, and stays short."""
    tool = tools.BY_NAME["check_job"]
    assert "word for word" in tool.description
    wait = tool.schema["properties"]["wait_seconds"]["description"]
    assert "every call" in wait
    assert len(tool.description) < 300 and len(wait) < 120


def test_check_job_waits_for_a_change_and_answers_early(world, monkeypatch) -> None:
    library, store, person, home = world
    job = Job(id="j-wait", source="x", owner=person.id, stage="working", done=1, total=4)
    library.jobs[job.id] = job
    clock = [0.0]
    naps: list[float] = []

    def nap(seconds: float) -> None:
        naps.append(seconds)
        clock[0] += seconds
        if len(naps) == 3:
            job.done = 2  # a worker thread finishes a batch

    monkeypatch.setattr(tools, "_clock", lambda: clock[0])
    monkeypatch.setattr(tools, "_sleep", nap)
    got = tools.check_job(away(library, store, person, home), {"id": "j-wait", "wait_seconds": 20})
    assert got["done"] == 2 and len(naps) == 3, "answered on the change, not at the end"
    assert all(one <= tools.WAIT_STEP for one in naps), "short naps, never a spin"


def test_check_job_waits_no_longer_than_it_was_asked_or_than_the_cap(world, monkeypatch) -> None:
    library, store, person, home = world
    job = Job(id="j-still", source="x", owner=person.id, stage="working", done=1, total=4)
    over = Job(id="j-over", source="x", owner=person.id, stage="done", reader="r/reader/index.html")
    library.jobs.update({job.id: job, over.id: over})
    ctx = away(library, store, person, home)
    clock = [0.0]

    def nap(seconds: float) -> None:
        clock[0] += seconds

    monkeypatch.setattr(tools, "_clock", lambda: clock[0])
    monkeypatch.setattr(tools, "_sleep", nap)
    got = tools.check_job(ctx, {"id": "j-still", "wait_seconds": 3})
    assert clock[0] == 3 and got["done"] == 1
    clock[0] = 0.0
    tools.check_job(ctx, {"id": "j-still", "wait_seconds": 600})
    assert clock[0] == tools.WAIT_MOST
    clock[0] = 0.0
    tools.check_job(ctx, {"id": "j-still", "wait_seconds": "soon"})
    tools.check_job(ctx, {"id": "j-over", "wait_seconds": 20})
    assert clock[0] == 0, "nothing to wait for on a finished build or a nonsense wait"


def test_check_job_holds_for_real_without_blocking_the_build(world) -> None:
    import threading
    import time

    library, store, person, home = world
    job = Job(id="j-real", source="x", owner=person.id, stage="working", done=0, total=2)
    library.jobs[job.id] = job
    threading.Timer(0.2, lambda: setattr(job, "stage", "done")).start()
    began = time.monotonic()
    got = tools.check_job(away(library, store, person, home), {"id": "j-real", "wait_seconds": 5})
    assert got["stage"] == "done" and time.monotonic() - began < 2


def test_run_answers_a_broken_tool_as_an_error_the_model_can_read(world) -> None:
    library, store, person, home = world
    ctx = context(library, store, person, home)
    text, failed = tools.run("no_such_tool", {}, ctx)
    assert failed and "No tool" in text
    text, failed = tools.run("check_job", {"id": "nope"}, ctx)
    assert failed and json.loads(text)["error"]
    text, failed = tools.run("my_progress", {}, ctx)
    assert not failed and json.loads(text)["known"] == 2


# -- quoting -----------------------------------------------------------------------


def priced(job) -> None:  # type: ignore[no-untyped-def]
    """What `Library.prepare` leaves on a job it could price, without the pipeline."""
    job.title = "מאמר"
    job.language = "he"
    job.segments = 40
    job.total = 40
    job.estimate = 0.12
    job.stage = "ready"


def test_a_quote_never_claims_or_enqueues(world, monkeypatch) -> None:
    """The seam: `prepare` is the free half, and nothing here reaches the paid half.
    The card's button posts `/build`; the model has no tool that could."""
    library, store, person, home = world
    monkeypatch.setattr(library, "prepare", priced)

    def forbidden(*_: object) -> str:
        raise AssertionError("a quote must not spend")

    monkeypatch.setattr(library, "claim", forbidden)
    monkeypatch.setattr(library, "enqueue", forbidden)
    ctx = context(library, store, person, home)
    ctx.reads = {"en"}
    got = tools.quote_build(ctx, {"source": "https://example.com/article"})
    quote = got["quote"]
    assert quote["stage"] == "ready" and quote["segments"] == 40
    assert "$" not in got["note"] and "never in money" in got["note"]
    # One sentence, because the card says the rest: asked to say what the text is and how
    # long it takes, the model narrated the card beside it (targum-internal#236).
    assert "Introduce it in ONE sentence" in got["note"]
    assert "do not repeat the card or tell them to press it" in got["note"]
    assert "One card in a reply" in got["note"]
    job = library.jobs[quote["id"]]
    assert job.owner == person.id and job.home == home and job.options["to"] == "en"
    assert job.kind == "build", "a quoted job is a build the strip will follow"
    assert job.options.get("words"), (
        "a text built from the chat has words a reader can tap. Without this the build "
        "writes no annotation.json, the reader has no marks and no control over them, "
        "and nothing says so: the job reports done"
    )
    assert store.committed(0) == 0.0, "nothing was claimed"
    # The chat is offered nothing that spends. `record_turn` is in the registry since
    # 2026-09-22 but never in this list: in *this* conversation targum recasts every
    # line itself, so offering it would record the same mistake twice and charge twice.
    offered = {one["name"] for one in tools.anthropic_tools()}
    by_name = {one.name: one for one in tools.REGISTRY}
    assert not [name for name in offered if by_name[name].spends or by_name[name].needs_consent]
    assert "record_turn" not in offered
    # Nor what exists for a conversation held somewhere else: this one already holds
    # the contract `how_to_talk` would hand over.
    assert not [name for name in offered if by_name[name].elsewhere]
    assert "how_to_talk" not in offered


def test_a_library_text_is_quoted_with_its_published_translation(world, monkeypatch) -> None:
    library, store, person, home = world
    monkeypatch.setattr(library, "prepare", priced)
    ctx = context(library, store, person, home)
    ctx.reads = {"en"}
    unbuilt = next(
        row
        for row in tools.search_library(ctx, {"limit": 20})["texts"]
        if not row["on_shelf"] and row["has_published_translation"]
    )
    got = tools.quote_build(ctx, {"catalogue_id": unbuilt["id"]})
    job = library.jobs[got["quote"]["id"]]
    assert job.options["translations"], "the published English rides on the job — nothing is bought"
    assert job.options["from"] == "he"
    already = tools.quote_build(ctx, {"catalogue_id": "ruth"})
    assert already["already_built"] is True and already["reader"].startswith("/reader/ruth-he/")
    assert "error" in tools.quote_build(ctx, {"catalogue_id": "nope"})


def test_a_quote_takes_a_language_however_the_model_names_it(world, monkeypatch) -> None:
    """A "tech news" turn on 2026-09-14 sent `"to": "English"`, was refused, sent
    `"english"`, was refused again, and only then `"en"`: two whole model round trips on
    a turn the reader was waiting for (targum-internal#270)."""
    from targum.translate.prompts import INTO

    library, store, person, home = world
    monkeypatch.setattr(library, "prepare", priced)
    ctx = context(library, store, person, home)
    ctx.reads = {"en", "ru"}
    for said, code in [
        ("English", "en"),
        ("english", "en"),
        ("EN", "en"),
        ("en", "en"),
        ("en-US", "en"),
        ("Russian", "ru"),
    ]:
        got = tools.quote_build(ctx, {"source": "https://example.com/article", "to": said})
        assert "quote" in got, (said, got)
        assert library.jobs[got["quote"]["id"]].options["to"] == code, said
    refused = tools.quote_build(ctx, {"source": "https://x.org/a", "to": "French"})["error"]
    assert "(en)" in refused and "(ru)" in refused, "a refusal names the codes it takes"
    schema = tools.BY_NAME["quote_build"].schema["properties"]["to"]
    assert schema["enum"] == [code for code, _ in INTO], "the schema offers the codes"


def test_a_quote_is_refused_on_the_add_page_s_grounds(world, monkeypatch) -> None:
    library, store, person, home = world
    monkeypatch.setattr(library, "prepare", priced)
    ctx = context(library, store, person, home)
    ctx.reads = {"en"}
    refused = tools.quote_build(ctx, {"source": "https://x.org/a", "to": "ru"})["error"]
    assert "Your languages" in refused
    assert (
        "translates into"
        in tools.quote_build(ctx, {"source": "https://x.org/a", "to": "fr"})["error"]
    )
    assert "link" in tools.quote_build(ctx, {"source": "just some words"})["error"]
    # A path is read off the server's disk. One with a colon in it passed the old check.
    assert "link" in tools.quote_build(ctx, {"source": "/srv/notes:today.txt"})["error"]
    assert "link" in tools.quote_build(ctx, {"source": "file:///etc/hostname"})["error"]
    assert "address" in tools.quote_build(ctx, {"source": "https:///nothing"})["error"]
    assert "Say what" in tools.quote_build(ctx, {})["error"]
    assert library.jobs == {}, "a refused quote leaves no job behind"


def test_a_link_that_is_in_the_library_is_pointed_there(world, monkeypatch) -> None:
    library, store, person, home = world
    monkeypatch.setattr(library, "prepare", priced)
    ctx = context(library, store, person, home)
    ctx.reads = {"en"}
    got = tools.quote_build(ctx, {"source": "test:esther"})
    assert got["in_library"]["id"] == "esther" and "catalogue_id" in got["in_library"]["note"]
    assert library.jobs == {}


def test_a_quote_that_cannot_be_built_says_why(world, monkeypatch) -> None:
    library, store, person, home = world

    def blocked(job) -> None:  # type: ignore[no-untyped-def]
        job.stage = "blocked"
        job.blocked = "Too long. Try a chapter, or something from the library."

    monkeypatch.setattr(library, "prepare", blocked)
    ctx = context(library, store, person, home)
    ctx.reads = {"en"}
    got = tools.quote_build(ctx, {"source": "https://example.com/novel"})
    assert got["quote"]["blocked"].startswith("Too long") and "cannot be made ready" in got["note"]


def test_the_allowance_is_credits(world) -> None:
    library, store, person, home = world
    store.save_job(
        {"id": "r1", "owner": person.id, "home": str(home), "source": "x", "made": now_ms()}
    )
    store.claim("r1", 0.5, 40.0, 0, owner=person.id, length=2 * 3600.0)
    ctx = context(library, store, person, home)
    got = tools.my_hours(ctx, {})
    assert got["credits_used"] == 120 and got["credits_a_month"] == 480
    assert got["credits_left"] == 360
    assert "480 credits a month is 8 hours" in got["note"], "the rate beside the balance"
    assert "Chatting" in got["note"] and "included" in got["note"]
    assert "$" not in json.dumps(got) and got["month_ends"]
    assert not [key for key in got if "hours" in key]


def now_ms() -> int:
    from targum.accounts import now

    return now()


# -- finding things out there ----------------------------------------------------------


def test_a_video_is_described_from_metadata_and_never_refused_on_licence(
    world, monkeypatch
) -> None:
    from targum.video import youtube

    monkeypatch.setattr(
        youtube,
        "describe",
        lambda url: {
            "title": "שיעור על הלב",
            "duration": 1500,
            "webpage_url": url,
            "license": "Creative Commons Attribution license (reuse allowed)",
            "formats": [{"acodec": "mp4a", "language": "he", "language_preference": 10}],
            "subtitles": {"he": []},
        },
    )
    library, store, person, home = world
    ctx = context(library, store, person, home)
    got = tools.describe_source(ctx, {"url": "https://www.youtube.com/watch?v=abc123"})
    assert got["kind"] == "video" and got["title"] == "שיעור על הלב"
    assert got["hebrew_subtitles"] is True and got["audio_language"] == "he"
    assert got["credits"] == 25 and got["quote_with"] == "https://www.youtube.com/watch?v=abc123"
    assert got["licence_standing"] == "owed" and got["corpus_exportable"] is True
    assert "never here" in got["licence_note"]


def test_a_reel_is_described_and_quoted_by_its_one_address(world, monkeypatch) -> None:
    """targum-internal#255: the chat can quote a reel the way it quotes a YouTube video,
    and a host it cannot fetch from is named with the way in that works."""
    from targum.video import instagram

    monkeypatch.setattr(
        instagram,
        "describe",
        lambda url: {"title": "המיתוג החדש ", "duration": 57.6, "webpage_url": url},
    )
    library, store, person, home = world
    ctx = context(library, store, person, home)
    got = tools.describe_source(
        ctx, {"url": "https://www.instagram.com/kan_news/reel/DQGn1BljOyO/?igsh=x"}
    )
    assert got["kind"] == "video" and got["title"] == "המיתוג החדש"
    assert got["seconds"] == 58 and got["hebrew_subtitles"] is False
    assert got["quote_with"] == "https://www.instagram.com/reel/DQGn1BljOyO"

    shut = tools.describe_source(ctx, {"url": "https://vimeo.com/76979871"})
    assert shut["kind"] == "video" and shut["error"].startswith("Vimeo doesn't let us fetch")


def test_a_post_of_pictures_is_described_and_its_pictures_left_to_the_reader(
    world, monkeypatch
) -> None:
    from targum.video import instagram

    monkeypatch.setattr(
        instagram,
        "backup",
        lambda url: instagram.Post(
            "DdCARhLDF-P", "aviv.bahar", "הופעות הקיץ\nעוד מילים", pictures=("a", "b")
        ),
    )
    monkeypatch.setattr(instagram, "describe", lambda url: pytest.fail("a post is not a film"))
    library, store, person, home = world
    ctx = context(library, store, person, home)
    got = tools.describe_source(ctx, {"url": "https://www.instagram.com/p/DdCARhLDF-P/"})
    assert got["kind"] == "post" and got["title"] == "הופעות הקיץ"
    assert got["author"] == "@aviv.bahar" and got["pictures"] == 2
    assert "only if the reader presses" in got["advice"][0]


def test_a_video_without_hebrew_subtitles_is_advised_not_refused(world, monkeypatch) -> None:
    from targum.video import youtube

    monkeypatch.setattr(
        youtube,
        "describe",
        lambda url: {
            "title": "x",
            "duration": 600,
            "formats": [{"acodec": "a", "language": "en"}],
            "subtitles": {},
        },
    )
    library, store, person, home = world
    got = tools.describe_source(
        context(library, store, person, home), {"url": "https://youtu.be/abc123"}
    )
    assert "error" not in got
    assert any("transcribed" in line for line in got["advice"])
    assert any("tagged en" in line for line in got["advice"])
    assert got["licence_standing"] == "unknown", "recorded as unknown, and still described"


def test_a_recording_and_an_article_are_described(world, monkeypatch) -> None:
    from targum.audio import episode
    from targum.ingest import url as url_module

    library, store, person, home = world
    ctx = context(library, store, person, home)
    monkeypatch.setattr(
        episode,
        "find",
        lambda url: episode.Episode(
            audio_url=url, title="פרק 3", seconds=1800, transcript_url="https://x/t.srt"
        ),
    )
    got = tools.describe_source(ctx, {"url": "https://podcast.example/ep3"})
    assert got["kind"] == "recording" and got["credits"] == 30 and got["has_transcript"] is True
    assert "nothing is transcribed" in got["advice"][0]

    monkeypatch.setattr(episode, "find", lambda url: None)
    page = (
        "<html><title> מאמר  על הים </title><body>"
        + "<p>"
        + " ".join(["שלום"] * 200)
        + "</p></body></html>"
    )
    monkeypatch.setattr(
        url_module, "fetch", lambda url: url_module.Fetched(text=page, content_type="text/html")
    )
    got = tools.describe_source(ctx, {"url": "https://news.example/a"})
    assert got["kind"] == "article" and got["title"] == "מאמר על הים"
    # The extractor keeps the page's title as a paragraph too, so a few over two hundred.
    assert 200 <= got["words"] <= 210 and got["minutes"] == 2 and got["hebrew_share"] == 1.0
    assert got["advice"] == []
    # How much of it this reader has, before it is quoted (targum-internal#244): שלום is
    # on their ledger, and the page is two hundred of it.
    assert got["known_share"] is not None and got["known_share"] >= 0.97
    assert got["known_line"] == "You know nearly every word here."


def test_what_describe_refuses_is_the_door_not_the_licence(world, monkeypatch) -> None:
    from targum.audio import episode
    from targum.errors import UnsupportedSource

    library, store, person, home = world
    ctx = context(library, store, person, home)
    assert "link" in tools.describe_source(ctx, {"url": "just words"})["error"]
    assert "Give a link" in tools.describe_source(ctx, {})["error"]
    assert tools.describe_source(ctx, {"url": "gutenberg:1234"})["kind"] == "fetcher"

    def spotify(url: str) -> None:
        raise UnsupportedSource("Spotify does not hand out its audio.", "Find the show's own feed.")

    monkeypatch.setattr(episode, "find", spotify)
    got = tools.describe_source(ctx, {"url": "https://open.spotify.com/episode/x"})
    assert got["error"].startswith("Spotify") and "feed" in got["error"]


def test_a_private_address_is_refused_by_the_fetch_door(world) -> None:
    """The SSRF guard is the one control a model choosing addresses makes primary."""
    library, store, person, home = world
    got = tools.describe_source(
        context(library, store, person, home), {"url": "http://127.0.0.1:8420/health"}
    )
    assert "private network" in got["error"], "the fetch door's own refusal, in its words"


def test_search_sources_reads_the_registered_feeds(world, monkeypatch, tmp_path) -> None:
    from datetime import UTC, datetime

    from targum.weekly import feeds

    path = tmp_path / "sources.json"
    path.write_text(
        json.dumps(
            {
                "publishers": [
                    {
                        "key": "kan",
                        "name": "כאן",
                        "publisher": "Kan",
                        "feed": "https://kan.example/rss",
                        "kind": "news",
                    },
                    {
                        "key": "pod",
                        "name": "Pod",
                        "feed": "https://pod.example/rss",
                        "kind": "podcast",
                    },
                    {
                        "key": "dead",
                        "name": "Dead",
                        "feed": "https://dead.example/rss",
                        "kind": "news",
                    },
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("TARGUM_SOURCES", str(path))

    def pull(url: str, *, limit: int = 30) -> list[feeds.Item]:
        from targum.errors import TargumError

        if "dead" in url:
            raise TargumError("Could not fetch")
        if "pod" in url:
            return [
                feeds.Item(
                    title="על הים",
                    link="https://pod.example/3",
                    published=datetime(2026, 9, 1, tzinfo=UTC),
                    enclosure="https://pod.example/3.mp3",
                    seconds=1800,
                    transcript="https://pod.example/3.srt",
                )
            ]
        return [
            feeds.Item(
                title="חדשות הים",
                link="https://kan.example/1",
                published=datetime(2026, 9, 4, tzinfo=UTC),
            ),
            feeds.Item(
                title="ספורט",
                link="https://kan.example/2",
                published=datetime(2026, 9, 5, tzinfo=UTC),
            ),
        ]

    monkeypatch.setattr(feeds, "pull", pull)
    tools.FEEDS.clear()
    library, store, person, home = world
    ctx = context(library, store, person, home)
    got = tools.search_sources(ctx, {"query": "הים"})
    assert [row["link"] for row in got["items"]] == [
        "https://kan.example/1",
        "https://pod.example/3",
    ], "newest first"
    assert got["items"][1]["has_transcript"] is True and got["items"][1]["seconds"] == 1800
    assert got["unreachable"] == ["dead"]
    assert tools.search_sources(ctx, {"kind": "podcast"})["count"] == 1

    monkeypatch.setenv("TARGUM_SOURCES", str(tmp_path / "none.json"))
    assert tools.search_sources(ctx, {})["note"] == "We don't follow any publishers yet."


def test_search_sources_holds_to_the_reader_s_language_unless_another_is_named(
    world, monkeypatch, tmp_path
) -> None:
    """2026-10-06: a reader asked ChatGPT for an article from Russian media, the tool said
    it searched "the Hebrew publishers", and ChatGPT went to its own web search and found
    a site targum could not open. Russian publishers are followed now; a Hebrew reader's
    search stays Hebrew, `language` names another or "all", and each item is measured
    against the reader's words in its own language."""
    from datetime import UTC, datetime

    from targum.weekly import feeds

    path = tmp_path / "sources.json"
    path.write_text(
        json.dumps(
            {
                "publishers": [
                    {"key": "kan", "name": "כאן", "feed": "https://kan.example/rss"},
                    {
                        "key": "meduza",
                        "name": "Медуза",
                        "feed": "https://meduza.example/rss",
                        "language": "ru",
                    },
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("TARGUM_SOURCES", str(path))
    when = datetime(2026, 10, 6, tzinfo=UTC)
    known_ru = " ".join(["кошка", "собака", "молоко", "хлеб"] * 6)
    unknown_ru = " ".join(["правительство", "законопроект", "парламентарии", "обсудили"] * 6)

    def pull(url: str, *, limit: int = 30) -> list[feeds.Item]:
        if "meduza" in url:
            return [
                feeds.Item(
                    title="Кошка",
                    summary=known_ru,
                    link="https://meduza.example/easy",
                    published=when,
                ),
                feeds.Item(
                    title="Закон",
                    summary=unknown_ru,
                    link="https://shut.example/hard",
                    published=when,
                ),
            ]
        return [feeds.Item(title="חדשות", link="https://kan.example/1", published=when)]

    monkeypatch.setattr(feeds, "pull", pull)
    tools.FEEDS.clear()
    library, store, person, home = world
    store.push(
        person,
        {
            "words": [
                {"language": "ru", "lemma": w, "surface": w, "status": 9, "at": 1, "seen": 1}
                for w in ("кошка", "собака", "молоко", "хлеб")
            ]
        },
    )
    store.reach("shut.example", False, "403")
    ctx = context(library, store, person, home)

    hebrew = tools.search_sources(ctx, {})
    assert hebrew["language"] == "he"
    assert [row["link"] for row in hebrew["items"]] == ["https://kan.example/1"]

    russian = tools.search_sources(ctx, {"language": "ru"})
    assert russian["language"] == "ru"
    rows = {row["link"]: row for row in russian["items"]}
    assert set(rows) == {"https://meduza.example/easy", "https://shut.example/hard"}
    assert all(row["language"] == "ru" for row in rows.values())
    easy, hard = rows["https://meduza.example/easy"], rows["https://shut.example/hard"]
    assert easy["known_share"] is not None and easy["known_share"] > 0.9
    assert hard["known_share"] is not None and hard["known_share"] < easy["known_share"]
    assert hard.get("host_shut") is True and "host_shut" not in easy

    both = tools.search_sources(ctx, {"language": "all"})
    assert both["language"] == "all" and both["count"] == 3

    none = tools.search_sources(ctx, {"language": "fr"})
    assert none["count"] == 0 and "French" in none["note"]


def test_search_sources_says_it_is_not_only_hebrew_and_takes_a_language() -> None:
    tool = next(tool for tool in tools.REGISTRY if tool.name == "search_sources")
    assert "Hebrew" not in tool.description
    assert "language the reader is learning here" in tool.description
    assert tool.schema["properties"]["language"] == tools._LANGUAGE_FILTER


def test_the_day_s_stories_are_ordered_by_what_the_reader_would_know(
    world, monkeypatch, tmp_path
) -> None:
    """targum-internal#244, change 4b. Two stories published the same day: the one this
    reader would get furthest into comes first. The day stays the window — news is worth
    reading because it is today's, so a familiar story never climbs over a fresher one."""
    from datetime import UTC, datetime

    from targum.weekly import feeds

    path = tmp_path / "sources.json"
    path.write_text(
        json.dumps(
            {"publishers": [{"key": "kan", "name": "כאן", "feed": "https://kan.example/rss"}]},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("TARGUM_SOURCES", str(path))

    # Twenty tokens each, which is `level.MEASURABLE`: below it the estimate answers
    # None rather than guessing, and a headline alone is below it.
    plain = " ".join(["הילד", "אמר", "שלום", "לאבא"] * 5)
    strange = " ".join(["פוליטיקאים", "התכנסו", "בירושלים", "לדיון"] * 5)

    def pull(url: str, *, limit: int = 30) -> list[feeds.Item]:
        return [
            feeds.Item(
                title="הכתבה הקשה",
                summary=strange,
                link="https://kan.example/hard",
                published=datetime(2026, 9, 5, 6, tzinfo=UTC),
            ),
            feeds.Item(
                title="הכתבה הקלה",
                summary=plain,
                link="https://kan.example/easy",
                published=datetime(2026, 9, 5, 20, tzinfo=UTC),
            ),
            feeds.Item(
                title="של אתמול",
                summary=plain,
                link="https://kan.example/yesterday",
                published=datetime(2026, 9, 4, tzinfo=UTC),
            ),
        ]

    monkeypatch.setattr(feeds, "pull", pull)
    tools.FEEDS.clear()
    library, store, person, home = world
    assert person is not None
    store.push(
        person,
        {
            "words": [
                {"language": "he", "lemma": w, "surface": w, "status": 9, "at": 1, "seen": 1}
                for w in ("הילד", "אמר", "שלום", "לאבא")
            ]
        },
    )
    ctx = context(library, store, person, home)

    got = tools.search_sources(ctx, {})

    shares = {row["link"]: row["known_share"] for row in got["items"]}
    # Not 1.0: the title counts too, and its words are not in the ledger. The hook is
    # what is measured, headline and all, because the hook is all the feed gives.
    assert shares["https://kan.example/easy"] > 0.8
    # Not 0 either: the commonest words of the language count as known for everybody,
    # and two of these reduce to one once a prefix comes off.
    assert shares["https://kan.example/hard"] < 0.5
    assert shares["https://kan.example/hard"] < shares["https://kan.example/easy"]
    assert [row["link"] for row in got["items"]] == [
        "https://kan.example/easy",
        "https://kan.example/hard",
        "https://kan.example/yesterday",
    ], "the day's easier one first, and yesterday's still last"


def test_a_story_too_short_to_measure_is_not_treated_as_hard(world, monkeypatch, tmp_path) -> None:
    """`known_share` answers None below twenty tokens, and a headline is below it. A hook
    that says little about its Hebrew is not evidence of hard Hebrew, so it sorts as if
    it were average rather than sinking under everything that was measured."""
    from datetime import UTC, datetime

    from targum.weekly import feeds

    path = tmp_path / "sources.json"
    path.write_text(
        json.dumps(
            {"publishers": [{"key": "kan", "name": "כאן", "feed": "https://kan.example/rss"}]},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("TARGUM_SOURCES", str(path))
    unknown = " ".join(["פוליטיקאים", "התכנסו", "בירושלים", "לדיון"] * 5)

    def pull(url: str, *, limit: int = 30) -> list[feeds.Item]:
        when = datetime(2026, 9, 5, tzinfo=UTC)
        return [
            feeds.Item(title="קשה", summary=unknown, link="https://k/hard", published=when),
            feeds.Item(title="כותרת בלבד", link="https://k/short", published=when),
        ]

    monkeypatch.setattr(feeds, "pull", pull)
    tools.FEEDS.clear()
    library, store, person, home = world
    got = tools.search_sources(context(library, store, person, home), {})

    by_link = {row["link"]: row for row in got["items"]}
    assert by_link["https://k/short"]["known_share"] is None, "not measured, not zero"
    assert [row["link"] for row in got["items"]][0] == "https://k/short"


def test_a_search_reads_the_ledger_once_and_again_only_when_it_changes(
    world, monkeypatch, tmp_path
) -> None:
    """2026-10-06: a search measured each of ~250 feed items by reading the whole ledger
    again, 3.2 s on the box. The ledger is read once, kept until the record changes, and a
    word marked known in between is in the very next search's numbers."""
    from datetime import UTC, datetime

    from targum.weekly import feeds

    path = tmp_path / "sources.json"
    path.write_text(
        json.dumps({"publishers": [{"key": "kan", "name": "כאן", "feed": "https://k/rss"}]}),
        encoding="utf-8",
    )
    monkeypatch.setenv("TARGUM_SOURCES", str(path))
    body = " ".join(["פוליטיקאים", "התכנסו", "בירושלים", "לדיון"] * 6)

    def pull(url: str, *, limit: int = 30) -> list[feeds.Item]:
        when = datetime(2026, 10, 6, tzinfo=UTC)
        return [
            feeds.Item(title=f"כותרת {n}", summary=body, link=f"https://k/{n}", published=when)
            for n in range(30)
        ]

    monkeypatch.setattr(feeds, "pull", pull)
    tools.FEEDS.clear()
    library, store, person, home = world
    reads: list[int] = []
    known_forms = store.known_forms

    def counted(person_id: int | None, language: str) -> set[str]:
        reads.append(1)
        return known_forms(person_id, language)

    monkeypatch.setattr(store, "known_forms", counted)
    ctx = context(library, store, person, home)

    first = tools.search_sources(ctx, {"limit": 30})
    assert tools.search_sources(ctx, {"limit": 30}) == first
    assert len(reads) == 1, "once for thirty items and two searches, not once an item"

    store.push(
        person,
        {
            "words": [
                {"language": "he", "lemma": word, "status": 9, "band": "easy", "at": 9, "seen": 9}
                for word in ("פוליטיקאים", "התכנסו")
            ]
        },
    )
    after = tools.search_sources(ctx, {"limit": 30})
    assert len(reads) == 2, "a changed record is read again"
    assert after["items"][0]["known_share"] > first["items"][0]["known_share"]


def test_search_sources_pulls_the_feeds_side_by_side_and_keeps_them(
    world, monkeypatch, tmp_path
) -> None:
    """Nineteen feeds, pulled one after another at up to thirty seconds each, held a
    "tech news" turn for 21 s on 2026-09-14 and could have held it for nine minutes
    (targum-internal#272)."""
    import threading
    import time
    from datetime import UTC, datetime

    from targum.errors import TargumError
    from targum.weekly import feeds

    path = tmp_path / "sources.json"
    publishers = [
        {"key": f"p{i}", "name": f"P{i}", "feed": f"https://p{i}.example/rss", "kind": "news"}
        for i in range(19)
    ]
    publishers.append(
        {"key": "slow", "name": "Slow", "feed": "https://slow.example/rss", "kind": "news"}
    )
    publishers.append(
        {"key": "dead", "name": "Dead", "feed": "https://dead.example/rss", "kind": "news"}
    )
    path.write_text(json.dumps({"publishers": publishers}), encoding="utf-8")
    monkeypatch.setenv("TARGUM_SOURCES", str(path))
    knocks: dict[str, int] = {}
    counting = threading.Lock()
    slow_may_answer = threading.Event()

    def pull(url: str, *, limit: int = 30) -> list[feeds.Item]:
        with counting:
            knocks[url] = knocks.get(url, 0) + 1
        if "dead" in url:
            raise TargumError("Could not fetch")
        if "slow" in url:
            slow_may_answer.wait(5)
        else:
            time.sleep(0.3)
        return [
            feeds.Item(
                title="חדשות",
                link=url.replace("/rss", "/1"),
                published=datetime(2026, 9, 14, tzinfo=UTC),
            )
        ]

    monkeypatch.setattr(feeds, "pull", pull)
    monkeypatch.setattr(tools, "FEEDS_BUDGET_S", 2.0)
    tools.FEEDS.clear()
    library, store, person, home = world
    ctx = context(library, store, person, home)

    started = time.monotonic()
    got = tools.search_sources(ctx, {"limit": 30})
    took = time.monotonic() - started
    assert took < 2.0 + 1.0, f"nineteen 0.3 s feeds side by side, not {took:.1f} s in a row"
    assert got["count"] == 19
    assert got["unreachable"] == ["dead"]
    assert got["late"] == ["slow"], "a feed past the budget is named, not waited for"

    slow_may_answer.set()
    for _ in range(50):
        if "https://slow.example/rss" not in tools.FEEDS._pending:
            break
        time.sleep(0.02)
    again = tools.search_sources(ctx, {"limit": 30})
    assert again["count"] == 20, "the late feed came in behind, and the next search has it"
    assert "late" not in again
    assert all(count == 1 for count in knocks.values()), (
        "inside the window nothing is pulled again, the dead feed included"
    )


def test_the_search_carries_no_country_the_api_refuses() -> None:
    """The search would rather stand in Israel, and the API does not offer it.

    This test replaces one that asserted `user_location` was `IL`, which is what the code
    sent and what the endpoint rejects:

        tools.0.web_search_20260209: Country code IL is not supported.

    The tool block is validated before the model is reached, so the 400 failed the whole
    turn rather than the search — every conversation, on every message, showing the reader
    "The conversation could not continue." The mocked tests all passed, because a mock is
    never asked whether the block is one the API would take.

    Measured against the live endpoint on 2026-09-08: `IL`, `CY` and `EG` are refused;
    `US`, `GB`, `DE` and no location at all are accepted. So there is no value of
    `country` that means what this wanted, and naming a country that is accepted would
    stand the search somewhere it should not be — which is the failure the removed test's
    own docstring described.

    Pinned as an absence, since what matters is that nothing goes out that the API will
    not take. If localisation becomes available, this test is the place the reason for
    its absence is written down.
    """
    (searching,) = [
        one for one in tools.anthropic_tools(web_search=True) if one.get("name") == "web_search"
    ]
    assert "user_location" not in searching
    assert tools.SEARCH_UNAVAILABLE_FROM["country"] == "IL", "kept as the record of why"


def test_no_web_search_block_carries_a_location() -> None:
    for tool in tools.anthropic_tools(web_search=True):
        assert "user_location" not in tool


def test_the_search_is_held_to_no_list_and_allows_six_a_turn() -> None:
    """Until 2026-09-08 the search was held to the known Hebrew sites and a card let a
    reader widen one turn; a list the model could not see handed back plausible wrong
    answers, and the card cost a second turn every time. The whole web, in Hebrew, and
    six searches a turn: a cent apiece, inside the turn's own meter."""
    (searching,) = [
        t for t in tools.anthropic_tools(web_search=True) if t.get("name") == "web_search"
    ]
    assert "allowed_domains" not in searching and "blocked_domains" not in searching
    assert searching["max_uses"] == tools.WEB_SEARCH_USES == 6
    assert "offer_wider_search" not in [t["name"] for t in tools.anthropic_tools(web_search=True)]


def test_the_search_names_domains_or_blocks_them_but_never_both() -> None:
    """The API returns a 400 when a request carries both lists."""
    for tool in tools.anthropic_tools(web_search=True):
        if tool.get("name") == "web_search":
            assert not ("allowed_domains" in tool and "blocked_domains" in tool)


class Door:
    """A fetch door that answers however a test says, so no network is touched."""

    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.asked: list[str] = []

    def fetch(self, url: str, params: Any = None) -> Any:
        self.asked.append(url)
        if self.error is not None:
            raise self.error
        from targum.ingest import url as url_module

        return url_module.Fetched("<html><body><p>שלום עולם.</p></body></html>", "text/html")


def _door(monkeypatch: Any, error: Exception | None = None) -> Door:
    from targum.ingest import url as url_module

    door = Door(error)
    monkeypatch.setattr(url_module, "fetch", door.fetch)
    return door


def test_a_host_that_refuses_the_box_is_remembered_and_a_missing_page_is_not(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """A 403 is a door that will be shut next time; a 404 is one address mistyped."""
    from targum.errors import Unreachable

    store = Store(tmp_path / "words.db")
    ctx = tools.Ctx(
        person=None, home=tmp_path, library=None, store=store, chat_id="c", level=level.EMPTY
    )
    _door(monkeypatch, Unreachable("no", "403", status=403, host="shut.example"))
    got = tools._describe(ctx, {"url": "https://shut.example/a"})
    assert got["host_shut"] is True and "doesn't answer targum" in got["error"]
    assert store.closed() == ["shut.example"]
    # A host is never told the reader can read it elsewhere (2026-10-06): ChatGPT read
    # "it may open in the reader's own browser" as leave to hand over the original link.
    said = f"{got['error']} {got['advice']}"
    assert "browser" not in said and "original" not in said
    assert "search_sources" in got["advice"] and "Never give the reader this link" in said
    assert len(re.findall(r"[.?]\s", got["error"] + " ")) <= 2, "one or two sentences"

    _door(monkeypatch, Unreachable("no", "404", status=404, host="fine.example"))
    got = tools._describe(ctx, {"url": "https://fine.example/gone"})
    assert "host_shut" not in got, "a missing page says nothing about the host"
    assert "fine.example" not in store.closed()


def test_a_host_that_answers_clears_itself(tmp_path: Path, monkeypatch: Any) -> None:
    from targum.errors import Unreachable

    store = Store(tmp_path / "words.db")
    ctx = tools.Ctx(
        person=None, home=tmp_path, library=None, store=store, chat_id="c", level=level.EMPTY
    )
    _door(monkeypatch, Unreachable("no", "timed out", status=None, host="flaky.example"))
    tools._describe(ctx, {"url": "https://flaky.example/a"})
    assert store.closed() == ["flaky.example"]
    _door(monkeypatch)
    tools._describe(ctx, {"url": "https://flaky.example/a"})
    assert store.closed() == [], "it came back, so it is not a shut door any more"


def test_the_door_is_still_knocked_on_for_a_reader_who_brings_the_link(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """The record informs what the model offers. It never refuses an import: a site that
    refused targum yesterday may answer today, and only knocking finds out."""
    store = Store(tmp_path / "words.db")
    ctx = tools.Ctx(
        person=None, home=tmp_path, library=None, store=store, chat_id="c", level=level.EMPTY
    )
    store.reach("shut.example", False, "403")
    door = _door(monkeypatch)
    tools._describe(ctx, {"url": "https://shut.example/an-article"})
    assert "https://shut.example/an-article" in door.asked, "knocked anyway"


def test_every_door_the_chat_builds_through_asks_for_words() -> None:
    """The two doors are `quote_build` and `quote_conversation`, and both had forgotten.

    Pinned on the constant rather than on either call site, so a third door that spreads
    `BUILD_OPTIONS` gets it, and one that writes its own literal is the thing this cannot
    catch — which is why the constant exists.

    `Library._builder` read `difficulty=bool(options.get("words"))` and `Pipeline.annotate`
    returns None without it, so a missing key was a reader with no tappable word and no
    error anywhere. Since `_builder` reads `options.get("words", True)` a missing key is
    words; the constant stays as the chat's way of saying so out loud.
    """
    assert tools.BUILD_OPTIONS == {"words": True}
    assert "gloss" not in tools.BUILD_OPTIONS, (
        "half a build's cost, mostly unread; a word is bought from the card instead"
    )


def test_search_library_applies_the_reader_s_own_ceiling_when_the_model_names_none(
    world,
) -> None:
    """targum-internal#244: no tool consumed the ledger; now the library search does,
    with the model's own number winning where it gives one."""
    library, store, person, home = world
    ctx = context(library, store, person, home)
    mine = tools.search_library(ctx, {"limit": 20})
    assert mine["ceiling_applied"] == 40, "two known words: the first rung's ceiling"
    assert all((row["looked_up_percent"] or 0) <= 40 for row in mine["texts"])
    theirs = tools.search_library(ctx, {"limit": 20, "max_looked_up_percent": 90})
    assert "ceiling_applied" not in theirs


def test_a_measured_suggestion_says_the_share_in_words(world) -> None:
    library, store, person, home = world
    ctx = context(library, store, person, home)
    got = tools.suggest_next(ctx, {"limit": 3})
    top = got["suggestions"][0]
    assert top["id"] == "esther" and top["known_line"] == "You know about 5 words in 10 here."


def test_a_bigger_ledger_is_offered_a_text_it_knows_more_of(world) -> None:
    """targum-internal#244, acceptance criterion 1: over three nested ledgers the top
    suggestion's `known_share` is monotone non-decreasing in the size of the ledger.

    It is the whole claim of the card in one line — that what is offered follows what the
    reader has, and not a number fixed to the text — and nothing pinned it.

    That the *ranking* reads the share, rather than only reporting it, is pinned next
    door by the register test, which sets two texts against each other. Here there is one
    text to measure: `ruth` is the reader's own and `suggest_next` leaves out what is
    already theirs, so `esther` is the shelf. What this asks is the criterion as written
    — that the number the top card carries never falls as the reader learns more.
    """
    library, store, person, home = world

    def mark(lemmas: list[str], at: int) -> None:
        store.push(
            person,
            {
                "words": [
                    {
                        "language": "he",
                        "lemma": lemma,
                        "surface": lemma,
                        "status": 9,
                        "at": at + n,
                        "seen": at + n,
                    }
                    for n, lemma in enumerate(lemmas)
                ]
            },
        )

    def top() -> tuple[str, float]:
        got = tools.suggest_next(context(library, store, person, home), {"limit": 5})
        measured = [row for row in got["suggestions"] if row.get("known_share") is not None]
        assert measured, "the shelf holds a text that was built and measured"
        return str(measured[0]["id"]), float(measured[0]["known_share"])

    # Nested, the way a reader's own ledger grows: nothing is ever taken back.
    first, nothing = top()
    mark(["מלך", "ספר"], 200)  # words of the other text: this one is unchanged
    _, same = top()
    mark(["רעב"], 300)  # and now the shelf's text is whole
    last, more = top()

    assert nothing <= same <= more, (
        f"the top suggestion's share fell as the ledger grew: {nothing} → {same} → {more}"
    )
    assert first == last == "esther"
    assert (nothing, more) == (0.5, 1.0), "half its words known, then all of them"


def test_a_suggestion_leans_towards_the_registers_the_reader_reads(world, monkeypatch) -> None:
    """2026-09-11: "a text that fits your level and interests". Two texts the reader
    knows equally well: the one in a register they brought in themselves ranks first."""
    from targum import catalogue

    library, store, person, home = world
    ctx = context(library, store, person, home)

    def entry(id: str, register: catalogue.Register) -> catalogue.Entry:
        return catalogue.Entry(
            id=id,
            title=id,
            author="",
            language="he",
            source=f"test:{id}",
            blurb="",
            words=100,
            register=register,
            difficulty=30,
        )

    entries = [entry("m", catalogue.Register.modern), entry("b", catalogue.Register.biblical)]
    monkeypatch.setattr(catalogue, "everything", lambda: entries)
    monkeypatch.setattr(
        tools,
        "_shelf",
        lambda ctx: ([{"name": "x", "source": "test:x", "register": "biblical"}], []),
    )
    got = tools.suggest_next(ctx, {"limit": 2})
    assert [row["id"] for row in got["suggestions"]] == ["b", "m"]
    monkeypatch.setattr(tools, "_shelf", lambda ctx: ([], []))
    got = tools.suggest_next(ctx, {"limit": 2})
    assert [row["id"] for row in got["suggestions"]] == ["m", "b"], (
        "nothing read yet: catalogue order"
    )


def test_a_suggestion_names_which_hebrew_only_for_hebrew(world, monkeypatch) -> None:
    """2026-09-15: an Italian talk on Learn read "modern Hebrew, about 6 minutes. · 6 min".
    Every language's rows carry a register, so the line says which Hebrew only of
    Hebrew, and leaves the minutes to the card that already shows them."""
    from targum import catalogue

    library, store, person, home = world
    ctx = context(library, store, person, home)

    def entry(id: str, language: str) -> catalogue.Entry:
        return catalogue.Entry(
            id=id,
            title=id,
            author="",
            language=language,
            source=f"test:{id}",
            blurb="",
            words=792,
            register=catalogue.Register.modern,
            difficulty=4,
        )

    entries = [entry("paure", "it"), entry("sipur", "he")]
    monkeypatch.setattr(catalogue, "everything", lambda: entries)
    monkeypatch.setattr(tools, "_shelf", lambda ctx: ([], []))
    italian = tools.suggest_next(ctx, {"language": "it"})["suggestions"]
    assert italian[0]["because"] == "4% of its words are rare in everyday use."
    hebrew = tools.suggest_next(ctx, {"language": "he"})["suggestions"]
    assert hebrew[0]["because"] == "4% of its words are rare in everyday use. Modern Hebrew."


def test_suggest_next_leaves_out_what_the_page_says_is_finished(world) -> None:
    """`skip` (2026-09-11): catalogue ids the browser records as finished are left out
    before the cut, so the next text that fits is always in reach — live, the top ten
    were all finished scenes, and skipping after the cut left nothing."""
    library, store, person, home = world
    ctx = context(library, store, person, home)
    everything = [row["id"] for row in tools.suggest_next(ctx, {"limit": 10})["suggestions"]]
    assert everything[0] == "esther"
    got = tools.suggest_next(ctx, {"limit": 10, "skip": ["esther"]})
    ids = [row["id"] for row in got["suggestions"]]
    rest = [one for one in everything if one != "esther"]
    assert "esther" not in ids and ids[: len(rest)] == rest
    assert len(ids) == 10, "left out before the cut, so the cut still fills"


def test_sentences_with_finds_a_word_in_every_form_on_the_shelf(world) -> None:
    """The contrast an aspect question wants comes from the reader's own texts, found by
    dictionary form so сказал and скажу both count (targum-internal#259)."""
    library, store, person, home = world
    built(home, "story-ru", "test:story", ["сказать"], "Рассказ")
    folder = home / "story-ru"
    (folder / "annotation.json").write_text(
        json.dumps(
            {
                "tokens": {
                    "0001.000-a": [{"surface": "сказал", "lemma": "сказать"}],
                    "0002.000-a": [{"surface": "говорил", "lemma": "говорить"}],
                    "0003.000-a": [{"surface": "Скажу", "lemma": "сказать"}],
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (folder / "segments.json").write_text(
        json.dumps(
            {
                "segments": [
                    {"id": "0001.000-a", "text": "Он сказал правду."},
                    {"id": "0002.000-a", "text": "Он долго говорил."},
                    {"id": "0003.000-a", "text": "Скажу завтра."},
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    ctx = context(library, store, person, home)
    got = tools.sentences_with(ctx, {"lemma": "сказа́ть"})
    assert got["count"] == 2
    assert [row["as"] for row in got["sentences"]] == ["сказал", "Скажу"]
    assert got["sentences"][0]["sentence"] == "Он сказал правду."
    assert got["sentences"][0]["title"] == "Рассказ"
    assert tools.sentences_with(ctx, {"lemma": "читать"})["count"] == 0
    assert "error" in tools.sentences_with(ctx, {"lemma": ""})
    assert all("pointed" not in row for row in got["sentences"]), "no file, no field"


def test_sentences_with_hands_over_the_pointing_the_text_was_built_with(world) -> None:
    """2026-10-06: a host adds nikkud itself, slowly and often wrongly. Where the text's
    own `vocalization.json` points a sentence, it goes beside `sentence` as `pointed`,
    saying whether a diacritizer guessed it; a file whose letters are not the sentence's
    is not believed; and a long sentence is cut where `sentence` is."""
    library, store, person, home = world
    built(home, "story-he", "test:story", ["ספר"], "סיפור")
    folder = home / "story-he"
    long = "הספר " + "א" * 400
    (folder / "annotation.json").write_text(
        json.dumps(
            {
                "tokens": {
                    sid: [{"surface": "הספר", "lemma": "ספר"}]
                    for sid in ("0001.000-a", "0002.000-a", "0003.000-a", "0004.000-a")
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (folder / "segments.json").write_text(
        json.dumps(
            {
                "segments": [
                    {"id": "0001.000-a", "text": "קראתי את הספר."},
                    {"id": "0002.000-a", "text": "הספר על השולחן."},
                    {"id": "0003.000-a", "text": "הספר ישן."},
                    {"id": "0004.000-a", "text": long},
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (folder / "vocalization.json").write_text(
        json.dumps(
            {
                "document_hash": "h",
                "language": "he",
                "vocalizer": "test",
                "segments": {
                    "0001.000-a": "קָרָאתִי אֶת הַסֵּפֶר.",
                    "0002.000-a": "הַסֵּפֶר עַל הַשּׁוּלְחָן.",
                    "0003.000-a": "הַסֵּפֶר חָדָשׁ.",  # not this sentence's letters
                    "0004.000-a": "הַסֵּפֶר " + "אָ" * 400,
                },
                "machine": ["0002.000-a"],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    ctx = context(library, store, person, home)
    got = tools.sentences_with(ctx, {"lemma": "ספר", "language": "he"})["sentences"]
    assert got[0]["sentence"] == "קראתי את הספר."
    assert got[0]["pointed"] == "קָרָאתִי אֶת הַסֵּפֶר." and got[0]["pointed_by"] == "edition"
    assert got[1]["pointed_by"] == "machine"
    assert "pointed" not in got[2], "a stale file is not believed"
    cut = got[3]
    assert len(cut["sentence"]) == tools.SENTENCE_CHARS
    from targum.vocalize.base import strip_nikkud

    assert strip_nikkud(cut["pointed"])[0] == cut["sentence"]
    assert cut["pointed"].endswith("אָ")


# -- a direct link to a recording or a video (targum-internal#256) --------------------


def test_a_direct_link_to_a_recording_is_named_and_timed_without_being_pulled(
    world, monkeypatch
) -> None:
    """`episode.find` fetches an address it cannot name from its suffix, and `.mp4` is
    one — so a reader's link to a video was pulled whole, twice, and then described as
    "file". Named from the address now, timed from its front, and never pulled."""
    from targum.audio import probe
    from targum.ingest import url as url_module

    pulled: list[str] = []
    opened: list[str] = []

    def never(url: str, *args: object, **kw: object) -> object:
        pulled.append(url)
        raise AssertionError("a media link must not be fetched as a page")

    monkeypatch.setattr(url_module, "fetch", never)
    monkeypatch.setattr(
        url_module,
        "opening",
        lambda url, most=0: (
            opened.append(url),
            url_module.Opening(b"front", "audio/mpeg", 57_600_000),
        )[1],
    )
    monkeypatch.setattr(probe, "timed", lambda head, declared: 3600.0)

    library, store, person, home = world
    ctx = context(library, store, person, home)
    found = tools.describe_source(ctx, {"url": "https://example.com/shows/ep-12.mp3"})

    assert pulled == [], "nothing was read as a page"
    assert opened == ["https://example.com/shows/ep-12.mp3"], "only its front"
    assert found["kind"] == "recording" and found["medium"] == "audio"
    assert found["seconds"] == 3600 and found["credits"] == 60
    assert found["megabytes"] == 54.9
    assert found["title"] == "ep-12"
    assert any("transcribed" in line for line in found["advice"])


def test_a_direct_link_to_a_video_says_it_is_one(world, monkeypatch) -> None:
    from targum.audio import probe
    from targum.ingest import url as url_module

    monkeypatch.setattr(
        url_module, "opening", lambda url, most=0: url_module.Opening(b"f", "video/mp4", 1024)
    )
    monkeypatch.setattr(probe, "timed", lambda head, declared: 90.0)

    library, store, person, home = world
    found = tools.describe_source(
        context(library, store, person, home), {"url": "https://example.com/a/talk.mp4"}
    )
    assert found["kind"] == "recording" and found["medium"] == "video"
    assert any("only its sound" in line for line in found["advice"])


def test_a_recording_whose_length_could_not_be_read_says_so(world, monkeypatch) -> None:
    """Said rather than guessed: the length is read for certain when the file is
    fetched, and the quote is made from that."""
    from targum.audio import probe
    from targum.ingest import url as url_module

    monkeypatch.setattr(
        url_module, "opening", lambda url, most=0: url_module.Opening(b"f", "audio/mpeg", 0)
    )
    monkeypatch.setattr(probe, "timed", lambda head, declared: 0.0)

    library, store, person, home = world
    found = tools.describe_source(
        context(library, store, person, home), {"url": "https://example.com/a/talk.mp3"}
    )
    assert found["seconds"] == 0 and found["credits"] is None and found["megabytes"] is None
    assert any("could not be read" in line for line in found["advice"])


def test_a_conversation_is_written_in_the_language_the_reader_reads(tmp_path: Path) -> None:
    """targum-internal#286, item 1. `Ctx.language` is the one rule the chrome answers to,
    and this is it against a real `Ctx` rather than a stand-in.

    `said_reads` and `reads` are deliberately different things. `reads` is a permission —
    which languages may be offered — and it is *everything* for a visitor, so a rule that
    picks one language out of it made a signed-out conversation Russian, `INTO` holding
    exactly English and Russian.
    """
    from targum.translate.prompts import INTO

    store = Store(tmp_path / "words.db")

    def ctx_for(said: set[str] | None, reads: set[str]) -> tools.Ctx:
        return tools.Ctx(
            person=None,
            home=tmp_path,
            library=None,
            store=store,
            chat_id="c",
            level=level.EMPTY,
            reads=reads,
            said_reads=said,
        )

    everything = {code for code, _ in INTO}
    assert everything == {"en", "ru"}, "which is why the two must not be confused"

    assert ctx_for(None, everything).language == "en", "nobody signed in"
    assert ctx_for({"en"}, {"en"}).language == "en"
    assert ctx_for({"en", "ru"}, everything).language == "ru", "the common Russian account"
    assert ctx_for({"ru"}, {"ru"}).language == "ru"


# -- what a host is handed (review, 2026-09-24) -------------------------------------


def test_every_tool_has_a_title_a_person_can_read() -> None:
    """Claude prints a tool's name in its own interface; the title is what it shows
    instead, and a title in the registry's vocabulary would be the same leak."""
    for tool in tools.REGISTRY:
        assert tool.title, tool.name
        for jargon in ("quote", "build", "ledger", "hours", "slip", "record"):
            assert jargon not in tool.title.lower(), (tool.name, tool.title)
    assert tools.BY_NAME["my_hours"].title == "My credits"
    assert tools.BY_NAME["quote_build"].title == "Get a text ready"


def test_what_writes_says_so_and_nothing_destroys() -> None:
    for tool in tools.REGISTRY:
        hints = tool.hints()
        assert hints["destructiveHint"] is False
        assert hints["readOnlyHint"] is (not tool.writes), tool.name
    assert tools.BY_NAME["record_turn"].writes and tools.BY_NAME["add_to_playlist"].writes
    # A link is quoted afresh on every call, so adding one twice is two items.
    assert tools.BY_NAME["add_to_playlist"].hints()["idempotentHint"] is False
    assert tools.BY_NAME["add_to_playlist"].hints()["openWorldHint"] is True
    assert tools.BY_NAME["describe_source"].hints()["openWorldHint"] is True
    assert not tools.BY_NAME["my_vocabulary"].writes


def test_no_tool_description_says_hours_or_money() -> None:
    for tool in tools.REGISTRY:
        said = tool.description.lower()
        assert "hours" not in said and "$" not in said, tool.name
        assert "ledger" not in said or tool.name == "quote_conversation", tool.name


def test_a_quote_over_the_connector_carries_credits_and_no_dollars(world, monkeypatch) -> None:
    library, store, person, home = world

    def audio(job) -> None:  # type: ignore[no-untyped-def]
        priced(job)
        job.audio = True
        job.seconds = 125.0
        job.transcription = 0.4

    monkeypatch.setattr(library, "prepare", audio)
    ctx = context(library, store, person, home)
    ctx.reads = {"en"}
    ctx.press_at = "https://targum.test"
    got = tools.quote_build(ctx, {"source": "https://example.com/episode"})
    quote = got["quote"]
    for dollars in tools.DOLLAR_FIELDS:
        assert dollars not in quote, dollars
    assert quote["credits"] == 2 and quote["open"].startswith("https://targum.test/build/")
    assert "quote" in got["note"] and "don't call this a quote" in got["note"]
    # And the in-app card still has what it draws from.
    ctx.press_at = ""
    assert "estimate" in tools.quote_build(ctx, {"source": "https://example.com/e2"})["quote"]


def test_check_job_says_no_dollars_and_quotes_its_link(world) -> None:
    library, store, person, home = world
    job = Job(
        id="j-space", source="x", owner=person.id, stage="done", reader="שיר חדש/reader/index.html"
    )
    job.estimate = 0.3
    library.jobs[job.id] = job
    ctx = context(library, store, person, home)
    ctx.press_at = "https://targum.test"
    got = tools.check_job(ctx, {"id": "j-space"})
    assert "estimate" not in got and "translation" not in got
    assert got["open"].startswith("https://targum.test/reader/%D7%A9")
    assert " " not in got["open"]


def test_my_progress_hands_over_no_streak_and_no_rung(world) -> None:
    """design.md §12: the current streak is refused, and a rung is a level."""
    library, store, person, home = world
    got = tools.my_progress(context(library, store, person, home), {})
    assert "streak" not in got and "longest_run_of_days" in got
    assert "reach" not in got["ladder"] and "cefr" not in got["ladder"]
    assert got["ladder"]["note"] == "A guide, not a placement."
    assert "never say a level" in tools.BY_NAME["my_progress"].description


def test_my_vocabulary_says_a_status_in_words(world) -> None:
    library, store, person, home = world
    got = tools.my_vocabulary(context(library, store, person, home), {})
    assert {row["status"] for row in got["recent"]} == {"known", "learning"}


def test_search_library_holds_to_the_conversation_s_language(world) -> None:
    """An Italian talk came back for a Hebrew reader (2026-09-24)."""
    from targum import catalogue

    library, store, person, home = world
    ctx = context(library, store, person, home)
    got = tools.search_library(ctx, {"limit": 20, "max_looked_up_percent": 100})
    languages = {
        catalogue.by_id(row["id"]).language.split("-")[0]  # type: ignore[union-attr]
        for row in got["texts"]
    }
    assert languages <= {"he", "arc"} and got["language"] == "he"
    everything = tools.search_library(ctx, {"language": "all", "max_looked_up_percent": 100})
    assert everything["count"] >= got["count"] and everything["language"] == "all"


def test_open_library_text_gives_a_library_link_when_it_cannot_be_quoted(world) -> None:
    library, store, person, home = world
    ctx = context(library, store, person, home)
    ctx.press_at = "https://targum.test"
    unbuilt = next(
        row for row in tools.search_library(ctx, {"limit": 20})["texts"] if not row["on_shelf"]
    )
    told = tools.open_library_text(ctx, {"id": unbuilt["id"]})["how_to_open"]
    assert f"https://targum.test/library/{unbuilt['id']}" in told


def test_playlists_come_back_with_absolute_links(world) -> None:
    library, store, person, home = world
    ctx = context(library, store, person, home)
    ctx.press_at = "https://targum.test"
    added = tools.add_to_playlist(ctx, {"playlist": "Morning", "text": "ruth-he"})
    assert added["open"].startswith("https://targum.test/reader/ruth-he/reader/index.html?list=")
    got = tools.my_playlists(ctx, {})["playlists"][0]
    assert got["open"] == added["open"]
    assert got["texts"][0]["reader"] == "https://targum.test/reader/ruth-he/reader/index.html"
    missing = tools.add_to_playlist(ctx, {"playlist": "Morning", "text": "not-there"})
    assert "source or catalogue_id" in missing["error"]


def test_a_tool_that_raises_is_not_its_exception(world, monkeypatch) -> None:
    library, store, person, home = world

    from dataclasses import replace

    def broken(ctx, args):  # type: ignore[no-untyped-def]
        raise KeyError("reader")

    monkeypatch.setitem(
        tools.BY_NAME, "my_progress", replace(tools.BY_NAME["my_progress"], run=broken)
    )
    text, failed = tools.run("my_progress", {}, context(library, store, person, home))
    assert failed and "KeyError" not in text and "reader" not in text


def test_how_to_talk_hands_a_host_only_real_words(world, monkeypatch) -> None:
    library, store, person, home = world
    # No common list, so none of the known words is left out for being in it.
    monkeypatch.setattr(tools.hebrew_module, "common_words", lambda **_: [])
    store.push(
        person,
        {
            "words": [
                {"language": "he", "lemma": w, "status": 9, "band": "easy", "at": 9, "seen": 1}
                for w in ("and", "the", "7", "ב", "ספר")
            ]
        },
    )
    ctx = context(library, store, person, home)
    contract = tools.how_to_talk(ctx, {"language": "he"})["contract"]
    known = next(line for line in contract.splitlines() if line.startswith("The reader's known"))
    assert "ספר" in known
    for junk in (" and", " the", " 7", " ב "):
        assert junk not in known + " ", junk


def test_the_host_is_told_the_contract_s_own_rule_in_its_own_language(world) -> None:
    from targum.chat import hebrew

    library, store, person, home = world
    ctx = context(library, store, person, home)
    italian = tools.how_to_talk(ctx, {"language": "it"})["contract"]
    head = tools.elsewhere("it", "English")
    assert italian.startswith(head)
    assert "Italian" in head and "Hebrew" not in head
    assert "kept on their record" not in head
    # One thing said, not a sentence and its override (2026-10-06): the host's contract
    # has the rewritten sentence, and targum's own still has the original.
    flat = " ".join(italian.split())
    assert "line without its" not in flat and "overrides" not in flat
    assert "Its English only when the reader asks" in flat
    assert "Never an Italian line without its English line." in hebrew.contract_for("it")


def test_suggest_next_says_what_it_does() -> None:
    """It leaves out the reader's own texts and keeps the shared shelf's, which open
    straight away; the description said "not built yet" and hosts were handed on_shelf."""
    said = tools.BY_NAME["suggest_next"].description
    assert "not built" not in said and "on_shelf" in said


def test_suggest_next_points_into_a_harder_text_where_a_section_reads(
    world, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """targum-internal#320. Psalms is the hardest text in the fixture catalogue and ranks
    last on its whole-text number; its second section reads at the reader's rung, so it
    takes the last place in the cut and says which section, with that section's own
    link — and no percentage, like every other reason."""
    from test_sentence_level import EASY, HARD, built_with_sections, kept_levels

    from targum import sentence_level

    library, store, person, home = world
    folder = library.shared / "psalms-he"
    (folder / "reader").mkdir(parents=True)
    (folder / "reader" / "index.html").write_text("<html></html>", encoding="utf-8")
    (folder / "document.json").write_text(
        json.dumps({"title": "תהילים", "language": "he", "source": "test:psalms"}),
        encoding="utf-8",
    )
    built_with_sections(folder, [HARD, EASY])
    where = tmp_path / "levels.json"
    sentence_level.write(kept_levels(), where, "jev-test")
    monkeypatch.setenv(sentence_level.ENV, str(where))
    ctx = context(library, store, person, home)

    got = tools.suggest_next(ctx, {"limit": 3})["suggestions"]
    assert got[0]["id"] == "esther", "measured coverage still ranks first"
    last = got[-1]
    assert last["id"] == "psalms"
    assert last["passage"]["section"] == 2
    assert last["passage"]["reader"].endswith("/psalms-he/reader/sec-0002.html")
    assert "%" not in last["because"] and "פרק 2" in last["because"]
    assert tools.because_in(last, "en") == last["because"]

    # Without the kept file, nothing points into anything and the cut is as it was.
    monkeypatch.setenv(sentence_level.ENV, str(tmp_path / "absent.json"))
    plain = tools.suggest_next(ctx, {"limit": 3})["suggestions"]
    assert all("passage" not in row for row in plain)
    assert "psalms" not in [row["id"] for row in plain]


def test_shorten_rewrites_reader_links_for_a_host_and_nothing_else() -> None:
    """The connector's links are eight letters (2026-10-06); the chat's own are not."""
    name = "בסטארטאפ-שלום"
    key = tools.short_key(name)
    assert len(key) == 8 and key == tools.short_key(name), "short and stable"
    whole = tools.reader_url(name, "https://targum.test")
    said = json.dumps(
        {
            "reader": whole,
            "passage": {"reader": whole.rsplit("/", 1)[0] + "/sec-0005.html"},
            "list": whole + "?list=3",
            "press": "https://targum.test/build/abc",
            "elsewhere": "https://example.com/reader/x/reader/index.html",
        },
        ensure_ascii=False,
    )
    got = json.loads(tools.shorten(said, "https://targum.test/"))
    assert got["reader"] == f"https://targum.test/r/{key}"
    assert got["passage"]["reader"] == f"https://targum.test/r/{key}/sec-0005"
    assert got["list"] == f"https://targum.test/r/{key}?list=3"
    assert got["press"] == "https://targum.test/build/abc"
    assert got["elsewhere"] == "https://example.com/reader/x/reader/index.html"
    # targum's own chat has no address and draws the long path as a door on its page.
    relative = json.dumps({"reader": tools.reader_url(name)})
    assert tools.shorten(relative, "") == relative


def test_my_shelf_answers_ten_and_counts_them_all(world, monkeypatch) -> None:
    """2026-10-06: the connector was handed all 397 texts of a shelf, 177,358 characters,
    each measured first. Now a page of them, measured once cut, and `count` still says how
    many matched so a host knows to ask for more."""
    library, store, person, home = world
    for n in range(12):
        built(home, f"extra-{n:02d}", f"test:extra-{n}", ["שלום"], f"Extra {n}")
    ctx = context(library, store, person, home)
    measured: list[str] = []
    real = tools.coverage_module.against

    def counting(folder, marked):  # type: ignore[no-untyped-def]
        measured.append(folder.name)
        return real(folder, marked)

    monkeypatch.setattr(tools.coverage_module, "against", counting)
    got = tools.search_my_shelf(ctx, {})
    assert got["count"] == 14 and len(got["texts"]) == tools.SHELF_LIMIT
    assert sorted(measured) == sorted(row["name"] for row in got["texts"]), "only those kept"
    assert all(row["known_share"] is not None for row in got["texts"])
    assert len(tools.search_my_shelf(ctx, {"limit": 3})["texts"]) == 3
    assert len(tools.search_my_shelf(ctx, {"limit": 500})["texts"]) == 14
    one = tools.search_my_shelf(ctx, {"query": "רות", "limit": 1})
    assert one["count"] == 1 and one["texts"][0]["known_share"] == pytest.approx(0.5)


def test_how_to_talk_hands_a_host_a_sample_and_says_so(world) -> None:
    """A long ledger reaches a host as its commonest `HOST_KNOWN` words, and the line
    says how many the reader really has (2026-10-06)."""
    wordfreq = pytest.importorskip("wordfreq")
    library, store, person, home = world
    words = tools.hebrew_module.for_host(wordfreq.top_n_list("he", 4000)[1200:1700], "he")
    store.push(
        person,
        {
            "words": [
                {"language": "he", "lemma": w, "status": 9, "band": "easy", "at": 9, "seen": 1}
                for w in words
            ]
        },
    )
    ctx = context(library, store, person, home)
    contract = tools.how_to_talk(ctx, {"language": "he"})["contract"]
    line = next(one for one in contract.splitlines() if one.startswith("A sample of"))
    total = len(words) + 2  # and the fixture's own שלום and בית
    assert f"the commonest {tools.hebrew_module.HOST_KNOWN} of the {total:,}" in line
    assert len(line.split(": ", 1)[1].split()) == tools.hebrew_module.HOST_KNOWN


def _mark(store: Store, person: Person, lemma: str, at: int) -> None:
    store.push(
        person,
        {
            "words": [
                {
                    "language": "he",
                    "lemma": lemma,
                    "status": 9,
                    "band": "easy",
                    "at": at,
                    "seen": at,
                }
            ]
        },
    )


def test_the_ledger_stamp_moves_on_every_write_to_the_record(world) -> None:
    """2026-10-06: the connector's answers are kept under `Store.ledger_stamp`, so every
    write to what they are read from has to move it — a sync, a slip, a slip known, the
    address and rung named, a test account wiped — and another reader's never does."""
    library, store, person, home = world
    other = signed_in(store, "other@example.com")
    seen = [store.ledger_stamp(person.id)]
    theirs = store.ledger_stamp(other.id)

    def moved() -> None:
        now = store.ledger_stamp(person.id)
        assert now not in seen
        seen.append(now)

    store.push(person, {"days": [{"day": "2026-10-06", "count": 1, "seen": 5}]})
    moved()
    slip = store.slip(person.id, wrote="אני הולך לבית", recast="אני הולך הביתה", changed=["x"])
    moved()
    assert store.know_slip(person.id, slip)
    moved()
    assert not store.know_slip(other.id, slip), "not theirs to know"
    assert store.ledger_stamp(person.id) == seen[-1]
    store.set_address(person, "f")
    moved()
    store.set_declared(person, "bet")
    moved()
    store.make_test_account("trying@example.com")
    trying = signed_in(store, "trying@example.com")
    before = store.ledger_stamp(trying.id)
    store.wipe(trying)
    assert store.ledger_stamp(trying.id) != before
    assert store.ledger_stamp(other.id) == theirs
    assert store.ledger_stamp(None) is None and store.ledger_stamp(10_000) is None


def test_how_to_talk_is_kept_until_the_record_changes(world, monkeypatch) -> None:
    """Asked twice, the second answer reads nothing of the ledger; a word marked in
    between is in the next answer; and one reader's answer is never another's."""
    library, store, person, home = world
    tools.KEPT.clear()
    ctx = context(library, store, person, home)
    reads: list[int | None] = []
    real = store.words_with_bands

    def counting(person_id, language):  # type: ignore[no-untyped-def]
        reads.append(person_id)
        return real(person_id, language)

    monkeypatch.setattr(store, "words_with_bands", counting)
    first = tools.how_to_talk(ctx, {"language": "he"})
    assert reads, "worked out the first time"
    reads.clear()
    assert tools.how_to_talk(ctx, {"language": "he"}) == first
    assert reads == [], "kept the second time"

    _mark(store, person, "ספר", 9)
    after = tools.how_to_talk(ctx, {"language": "he"})["contract"]
    assert reads and after != first["contract"] and "ספר" in after

    other = signed_in(store, "other@example.com")
    away = context(library, store, other, library.home(other))
    theirs = tools.how_to_talk(away, {"language": "he"})["contract"]
    tools.KEPT.clear()
    assert theirs == tools.how_to_talk(away, {"language": "he"})["contract"]
    assert theirs != after


def test_a_text_is_measured_once_until_the_ledger_or_the_text_changes(world, monkeypatch) -> None:
    library, store, person, home = world
    tools.KEPT.clear()
    ctx = context(library, store, person, home)
    measured: list[str] = []
    real = tools.coverage_module.against

    def counting(folder, marked):  # type: ignore[no-untyped-def]
        measured.append(folder.name)
        return real(folder, marked)

    monkeypatch.setattr(tools.coverage_module, "against", counting)
    one = tools.search_my_shelf(ctx, {"query": "רות"})["texts"][0]
    assert measured == ["ruth-he"] and one["known_share"] == pytest.approx(0.5)
    tools.search_my_shelf(ctx, {"query": "רות"})
    assert measured == ["ruth-he"], "kept"

    # Another reader's text of the same name is counted against their own words.
    other = signed_in(store, "other@example.com")
    built(library.home(other), "ruth-he", "test:ruth", ["שלום", "בית", "מלך", "ספר"], "רות")
    theirs = tools.search_my_shelf(context(library, store, other, library.home(other)), {})
    assert theirs["texts"][0]["known_share"] == 0

    measured.clear()
    _mark(store, person, "ספר", 9)
    again = tools.search_my_shelf(ctx, {"query": "רות"})["texts"][0]
    assert measured == ["ruth-he"] and again["known_share"] == pytest.approx(0.75)

    # A rebuilt text is counted again, with the ledger unchanged.
    measured.clear()
    (home / "ruth-he" / "annotation.json").write_text(
        json.dumps({"tokens": {"0001.001-a": [{"lemma": "שלום", "pos": "NOUN"}, {"lemma": "x"}]}}),
        encoding="utf-8",
    )
    rebuilt = tools.search_my_shelf(ctx, {"query": "רות"})["texts"][0]
    assert measured == ["ruth-he"] and rebuilt["known_share"] == pytest.approx(0.5)
