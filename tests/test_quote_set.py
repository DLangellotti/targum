"""One press takes a named set (targum-internal#365, design.md §12).

A model quotes a set; the reader presses it on a page of ours; every text is claimed or
none is. What must stay true underneath: quoting never spends, the claim is all or
nothing, an address that names somebody else's list is still refused, and a set is
nobody's but its owner's.
"""

from __future__ import annotations

import json
import re
import threading
from collections.abc import Iterator
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

from targum import level
from targum.accounts import Person, Store
from targum.chat import tools
from targum.render.builder import set_page
from targum.serve import Handler, Job, Library, desk_languages


def signed_in(store: Store, email: str) -> tuple[Person, str]:
    signed = store.finish_sign_in(store.start_sign_in(email))
    assert signed is not None
    return signed


def priced(job: Job) -> None:
    """What `Library.prepare` leaves on a job it could price, without the pipeline: a
    one-minute reel, so each text in a set uses one credit."""
    job.title = "סרטון"
    job.language = "he"
    job.segments = 6
    job.total = 6
    job.estimate = 0.02
    job.audio = True
    job.seconds = 60.0
    job.stage = "ready"


@pytest.fixture
def world(tmp_path: Path) -> tuple[Library, Store, Person, Path]:
    store = Store(tmp_path / "words.db")
    out = tmp_path / "out"
    out.mkdir()
    library = Library(out, store=store)
    person, _ = signed_in(store, "reader@example.com")
    return library, store, person, library.home(person)


def context(library: Library, store: Store, person: Person, home: Path) -> tools.Ctx:
    ctx = tools.Ctx(
        person=person,
        home=home,
        library=library,
        store=store,
        chat_id="c1",
        level=level.snapshot(store, person.id, "he"),
    )
    ctx.reads = {"en"}
    return ctx


REELS = [
    {"source": f"https://www.instagram.com/reel/r{n}/", "title": f"Reel {n}"} for n in range(3)
]


# --- the quote -------------------------------------------------------------------


def test_a_set_is_quoted_as_one_and_never_spends(world, monkeypatch) -> None:
    library, store, person, home = world
    monkeypatch.setattr(library, "prepare", priced)

    def forbidden(*_: object) -> Any:
        raise AssertionError("a quote must not spend")

    for name in ("claim", "claim_set", "enqueue"):
        monkeypatch.setattr(library, name, forbidden)
    got = tools.quote_set(context(library, store, person, home), {"name": "Reels", "items": REELS})
    held = got["set"]
    assert [one["title"] for one in held["items"]] == ["Reel 0", "Reel 1", "Reel 2"]
    assert held["credits"] == 3 and all(one["credits"] == 1 for one in held["items"])
    assert got["open"] == f"/set/{held['id']}", "in the chat, a path the page draws as a door"
    saved = store.playlist(person.id, held["id"])
    assert saved is not None and saved["made_by"] == "chat"
    assert [item["job"] for item in saved["items"]] == [one["job"] for one in held["items"]]
    assert all(library.jobs[one["job"]].stage == "ready" for one in held["items"])
    assert "cannot press" in got["note"]


def test_over_the_connector_the_set_comes_back_as_a_link(world, monkeypatch) -> None:
    library, store, person, home = world
    monkeypatch.setattr(library, "prepare", priced)
    ctx = context(library, store, person, home)
    ctx.press_at = "https://targum.page"
    got = tools.quote_set(ctx, {"name": "Reels", "items": REELS[:1]})
    assert got["open"] == f"https://targum.page/set/{got['set']['id']}"
    assert (store.playlist(person.id, got["set"]["id"]) or {})["made_by"] == "connector"


def test_an_item_that_cannot_be_made_is_named_and_left_out(world, monkeypatch) -> None:
    library, store, person, home = world

    def some(job: Job) -> None:
        if job.source.endswith("r1/"):
            job.stage = "failed"
            job.error = "We can take one video at a time."
        else:
            priced(job)

    monkeypatch.setattr(library, "prepare", some)
    got = tools.quote_set(context(library, store, person, home), {"name": "Reels", "items": REELS})
    assert len(got["set"]["items"]) == 2
    assert got["set"]["refused"] == [
        {"source": REELS[1]["source"], "why": "We can take one video at a time."}
    ]


def test_a_set_nothing_in_which_can_be_made_makes_no_playlist(world, monkeypatch) -> None:
    library, store, person, home = world

    def refused(job: Job) -> None:
        job.stage = "failed"
        job.error = "No."

    monkeypatch.setattr(library, "prepare", refused)
    got = tools.quote_set(context(library, store, person, home), {"name": "R", "items": REELS})
    assert "error" in got and store.playlists(person.id) == []


def test_a_set_holds_twenty(world, monkeypatch) -> None:
    library, store, person, home = world
    monkeypatch.setattr(library, "prepare", priced)
    many = [{"source": f"https://example.com/{n}"} for n in range(21)]
    got = tools.quote_set(context(library, store, person, home), {"name": "Many", "items": many})
    assert "at most 20" in got["error"]


def test_the_chat_is_offered_it_and_the_connector_needs_the_scope_that_spends() -> None:
    from targum import connector

    assert "quote_set" in {one["name"] for one in tools.anthropic_tools()}
    assert "quote_set" not in {one.name for one in connector.exposed("library record")}
    assert "quote_set" in {one.name for one in connector.exposed("library record chat")}


# --- the claim -------------------------------------------------------------------


def saved_job(store: Store, job_id: str, owner: int, home: Path) -> None:
    from targum.accounts import now

    store.save_job({"id": job_id, "owner": owner, "home": str(home), "source": "x", "made": now()})


def test_a_set_is_claimed_whole_or_not_at_all(world) -> None:
    _, store, person, home = world
    for name in ("a", "b", "c"):
        saved_job(store, name, person.id, home)
    claims = [(name, 0.01, 600.0) for name in ("a", "b", "c")]
    refused, room = store.claim_all(
        claims, 40.0, 0, owner=person.id, month_from=0, per_month_length=1500.0
    )
    assert refused == "hours" and room == 1500.0
    claimed = store.db.execute("SELECT COUNT(*) AS n FROM job WHERE claimed > 0").fetchone()
    assert int(claimed["n"]) == 0, "none of it, not the two that would have fitted"
    refused, _ = store.claim_all(
        claims[:2], 40.0, 0, owner=person.id, month_from=0, per_month_length=1500.0
    )
    assert refused == ""
    claimed = store.db.execute("SELECT COUNT(*) AS n FROM job WHERE claimed > 0").fetchone()
    assert int(claimed["n"]) == 2


def test_a_finished_build_fills_its_place_in_the_playlist(world, monkeypatch) -> None:
    library, store, person, home = world
    monkeypatch.setattr(library, "prepare", priced)
    got = tools.quote_set(context(library, store, person, home), {"name": "R", "items": REELS[:2]})
    first, second = (library.jobs[one["job"]] for one in got["set"]["items"])
    first.reader = "reel-he/reader/index.html"
    first.stage = "done"
    library.remember(first)
    second.stage = "failed"
    library.remember(second)
    items = (store.playlist(person.id, got["set"]["id"]) or {})["items"]
    assert items[0]["reader"] == "reel-he" and not items[0]["failed"]
    assert items[1]["failed"] is True


# --- the page --------------------------------------------------------------------


def prose(page: str) -> str:
    body = re.sub(r"<(style|script)\b.*?</\1>", " ", page, flags=re.S | re.I)
    return " ".join(re.sub(r"<[^>]+>", " ", body).split())


def test_the_page_lists_every_text_with_a_tick_and_says_the_total_once() -> None:
    playlist = {
        "id": 7,
        "name": "Reels",
        "items": [
            {"position": n, "reader": None, "job": f"j{n}", "title": f"Reel {n}", "failed": False}
            for n in range(2)
        ],
    }
    jobs = [
        {"id": f"j{n}", "stage": "ready", "audio": True, "seconds": 120.0, "known_line": ""}
        for n in range(2)
    ]
    page = set_page(playlist, jobs)
    said = prose(page)
    assert "Reel 0" in said and "Reel 1" in said
    assert said.count("2 credits") == 2 and "Uses 4 credits in all" in said
    assert page.count('name="keep"') == 2 and 'action="/set/7"' in page
    assert "$" not in said and "!" not in said
    assert "<script" not in page, "no script at all, so nothing for the CSP to hash"


# --- the press, through the door --------------------------------------------------


@pytest.fixture
def door(tmp_path: Path) -> Iterator[tuple[int, Library, Store, Person, str, str]]:
    out = tmp_path / "out"
    out.mkdir()
    store = Store(tmp_path / "words.db")
    library = Library(out, store=store, upload_seconds=150.0)
    person, mine = signed_in(store, "one@example.com")
    _, theirs = signed_in(store, "two@example.com")
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    server.RequestHandlerClass = type(
        "SetHandler",
        (Handler,),
        {
            "library": library,
            "store": store,
            "token": "test-key",
            "require_account": True,
            "address": f"http://127.0.0.1:{port}",
            "translated": {code: {} for code in desk_languages()},
        },
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield port, library, store, person, mine, theirs
    finally:
        server.shutdown()
        server.server_close()


def call(port: int, method: str, path: str, session: str, body: object = None) -> tuple:
    conn = HTTPConnection("127.0.0.1", port, timeout=10)
    raw = json.dumps(body).encode() if body is not None else b""
    headers = {"Cookie": f"targum_session={session}", "X-Targum-Key": "test-key"}
    if method == "POST":
        headers["X-Targum-Press"] = "1"
        headers["Content-Type"] = "application/json"
    conn.request(method, f"{path}?k=test-key", body=raw or None, headers=headers)
    response = conn.getresponse()
    got = response.read()
    conn.close()
    try:
        return response.status, json.loads(got)
    except json.JSONDecodeError:
        return response.status, got.decode("utf-8", "replace")


def a_quoted_set(library: Library, store: Store, person: Person, count: int) -> dict:
    ctx = context(library, store, person, library.home(person))
    got = tools.quote_set(ctx, {"name": "Reels", "items": REELS[:count]})
    return got["set"]


def test_one_press_claims_every_text_and_starts_them_in_order(door, monkeypatch) -> None:
    port, library, store, person, mine, _ = door
    monkeypatch.setattr(library, "prepare", priced)
    started: list[str] = []
    monkeypatch.setattr(library, "enqueue", lambda job: started.append(job.id))
    held = a_quoted_set(library, store, person, 2)
    status, page = call(port, "GET", f"/set/{held['id']}", mine)
    assert status == 200 and "Reel 0" in page
    status, said = call(port, "POST", f"/set/{held['id']}", mine, {"keep": [0, 1]})
    assert status == 200, said
    assert started == [one["job"] for one in held["items"]], "in the set's order"


def test_a_set_that_does_not_fit_claims_nothing_and_says_how_many_do(door, monkeypatch) -> None:
    port, library, store, person, mine, _ = door
    monkeypatch.setattr(library, "prepare", priced)
    monkeypatch.setattr(library, "enqueue", lambda job: pytest.fail("nothing may start"))
    held = a_quoted_set(library, store, person, 3)  # 180 seconds against 150
    status, said = call(port, "POST", f"/set/{held['id']}", mine, {"keep": [0, 1, 2]})
    assert status == 402 and said["credits_left"] == 2
    assert "untick" in said["error"]
    claimed = store.db.execute("SELECT COUNT(*) AS n FROM job WHERE claimed > 0").fetchone()
    assert int(claimed["n"]) == 0


def test_what_was_unticked_leaves_the_set_and_is_not_claimed(door, monkeypatch) -> None:
    port, library, store, person, mine, _ = door
    monkeypatch.setattr(library, "prepare", priced)
    started: list[str] = []
    monkeypatch.setattr(library, "enqueue", lambda job: started.append(job.id))
    held = a_quoted_set(library, store, person, 3)
    status, _ = call(port, "POST", f"/set/{held['id']}", mine, {"keep": [0, 2]})
    assert status == 200
    kept = (store.playlist(person.id, held["id"]) or {})["items"]
    assert [item["title"] for item in kept] == ["Reel 0", "Reel 2"]
    assert started == [held["items"][0]["job"], held["items"][2]["job"]]


def test_another_account_cannot_see_or_press_it(door, monkeypatch) -> None:
    port, library, store, person, _, theirs = door
    monkeypatch.setattr(library, "prepare", priced)
    monkeypatch.setattr(library, "enqueue", lambda job: pytest.fail("not theirs to press"))
    held = a_quoted_set(library, store, person, 1)
    assert call(port, "GET", f"/set/{held['id']}", theirs)[0] == 404
    assert call(port, "POST", f"/set/{held['id']}", theirs, {"keep": [0]})[0] == 404
