"""Cancel a build, waiting or running (targum-internal#694).

David, 2026-11-13, on a waiting card: "add a way to cancel the previous builds in the
queue". A reader cancels their own builds and nobody else's; one that never started
gives back every credit it held; one that is running stops at its next step and is
settled to its receipt like any build, so the reader pays for what was done and no more.
Everything goes through the job's own row: `Library.claim` took it, `release` or
`settle` gives it back. There is no second counter.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import threading
from collections.abc import Iterator
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

from targum.accounts import Store, now
from targum.serve import Handler, Job, Library, Stopped
from targum.usage import Usage

HARNESS = Path(__file__).resolve().parent / "js" / "cancel.js"


def _person(store: Store, email: str) -> tuple[Any, str]:
    person, session = store.finish_sign_in(store.start_sign_in(email))  # type: ignore[misc]
    return person, session


def _row(store: Store, job_id: str) -> dict[str, Any]:
    row = store.db.execute(
        "SELECT stage, claimed, spent, length FROM job WHERE id = ?", (job_id,)
    ).fetchone()
    return dict(row)


def _recording(job_id: str, owner: int, home: Path, **extra: Any) -> Job:
    """A 47-minute video, as David's waiting card had: credits by the second."""
    return Job(
        id=job_id,
        source=f"https://example.com/{job_id}",
        title=f"Video {job_id}",
        owner=owner,
        home=home,
        audio=True,
        seconds=47 * 60.0,
        estimate=0.40,
        **extra,
    )


def _claimed(library: Library, job: Job) -> None:
    library.jobs[job.id] = job
    library.remember(job)
    assert library.press(job) == "", job.blocked


# -- waiting --------------------------------------------------------------------------


def test_a_waiting_cancel_gives_back_every_credit_it_held(tmp_path: Path) -> None:
    store = Store(tmp_path / "db")
    person, _ = _person(store, "reader@example.com")
    library = Library(tmp_path / "out", store=store)
    job = _recording("w1", person.id, library.home(person))
    _claimed(library, job)
    held = _row(store, "w1")
    assert held["claimed"] == pytest.approx(0.40) and held["length"] == pytest.approx(2820.0)
    assert store.hours_used(person.id, 0) == pytest.approx(2820.0)

    assert library.cancel(job) == "cancelled"

    row = _row(store, "w1")
    assert row["stage"] == "cancelled"
    assert row["claimed"] == 0 and row["length"] == 0 and row["spent"] == 0
    assert store.hours_used(person.id, 0) == 0, "every credit back"
    assert store.committed(0, person.id) == 0, "and every dollar"
    assert library.cancel(job) == "cancelled", "a second press changes nothing"
    assert store.hours_used(person.id, 0) == 0, "and never gives back more than was held"


def test_the_worker_never_builds_a_cancelled_build(tmp_path: Path, monkeypatch: Any) -> None:
    library = Library(tmp_path)
    ran: list[str] = []
    monkeypatch.setattr(Library, "run", lambda _self, job: ran.append(job.id))
    gone = Job(id="gone", source="x", owner=1)
    kept = Job(id="kept", source="x", owner=1)
    for one in (gone, kept):
        library.jobs[one.id] = one
        library.enqueue(one)
    assert library.cancel(gone) == "cancelled"
    library.start_workers(1)
    library.queue.join()
    assert ran == ["kept"], "a cancelled build is skipped; the one behind it runs"


def test_a_cancel_that_loses_to_the_worker_is_a_stop_never_a_refund(tmp_path: Path) -> None:
    """The worker took it a moment before the press: it is about to spend, so its claim
    must stay. The press becomes a stop, and the build settles to its receipt."""
    store = Store(tmp_path / "db")
    person, _ = _person(store, "reader@example.com")
    library = Library(tmp_path / "out", store=store)
    job = _recording("t1", person.id, library.home(person))
    _claimed(library, job)
    assert library._take(job)
    assert library.cancel(job) == "stopping"
    assert job.stop and job.stage == "queued"
    assert _row(store, "t1")["claimed"] == pytest.approx(0.40), "nothing handed back yet"


def test_places_behind_a_cancelled_build_move_up_and_nothing_is_reordered(
    tmp_path: Path,
) -> None:
    library = Library(tmp_path)
    library.jobs = {
        "a": Job(id="a", source="s", title="Theirs", owner=2, stage="working", made=100),
        "b": Job(id="b", source="s", title="Mine first", owner=1, stage="queued", made=200),
        "c": Job(id="c", source="s", title="Theirs too", owner=2, stage="queued", made=300),
        "d": Job(id="d", source="s", title="Mine second", owner=1, stage="queued", made=400),
    }
    mine = {row["id"]: row for row in library.mine(1)}
    assert mine["d"]["behind"] == 3
    assert [one["id"] for one in mine["d"]["ahead"]] == ["b"], "only mine are named"
    assert mine["d"]["ahead"][0]["cancellable"] is True
    assert mine["d"]["ahead_others"] == 2, "the rest only counted"
    assert "Theirs" not in json.dumps(mine), "another reader's title is never sent"

    assert library.cancel(library.jobs["b"]) == "cancelled"

    mine = {row["id"]: row for row in library.mine(1)}
    assert "b" not in mine, "a cancelled build leaves the list"
    assert mine["d"]["behind"] == 2 and mine["d"]["ahead"] == []
    theirs = {row["id"]: row for row in library.mine(2)}
    assert theirs["c"]["behind"] == 1, "everyone behind moves up"
    assert [row["id"] for row in library.mine(2)] == ["c", "a"], "in the order they were made"


# -- running --------------------------------------------------------------------------


class Halfway:
    """A build that fetches, hears two minutes, translates one batch, and is stopped
    while it does: the reader presses Stop between the batch and the page."""

    def __init__(self, library: Library, job: Job) -> None:
        self.library, self.job = library, job
        self.notify: Any = lambda message: None
        self.usage = Usage()
        self.drawn = False

    @property
    def spent(self) -> Usage:
        return self.usage

    def run(self, on_progress: Any, on_ready: Any, chapters: Any = None, **_: Any) -> Any:
        self.notify("Fetching the video…")
        self.usage.add_seconds("openai/whisper-1", 120.0)
        self.notify("Transcribing part 1 of 4…")
        self.usage.add("claude-sonnet-5", 10_000, 4_000)
        on_progress(20)
        assert self.library.cancel(self.job) == "stopping"
        self.notify("Building the reader…")
        self.drawn = True  # never reached: the stop is heard first
        on_ready(None)
        raise AssertionError("a stopped build went on")


def test_a_running_cancel_stops_and_settles_to_its_receipt(
    tmp_path: Path, monkeypatch: Any
) -> None:
    store = Store(tmp_path / "db")
    person, _ = _person(store, "reader@example.com")
    library = Library(tmp_path / "out", store=store)
    job = _recording("r1", person.id, library.home(person))
    _claimed(library, job)
    build = Halfway(library, job)
    monkeypatch.setattr(Library, "_builder", lambda _self, _job: build)

    library.run(job)

    assert not build.drawn and job.reader == "", "no reader that looks finished"
    assert job.stage == "cancelled" and not job.error
    receipt = build.usage.cost()
    assert receipt > 0
    row = _row(store, "r1")
    assert row["stage"] == "cancelled"
    assert row["spent"] == pytest.approx(receipt) and row["claimed"] == pytest.approx(receipt)
    assert row["length"] == pytest.approx(120.0), "the two minutes heard, not 47"
    assert row["claimed"] < 0.40 and row["length"] < 2820.0, "never more than was held"


def test_a_stopped_text_uses_no_credits_and_pays_what_the_api_said(
    tmp_path: Path, monkeypatch: Any
) -> None:
    store = Store(tmp_path / "db")
    person, _ = _person(store, "reader@example.com")
    library = Library(tmp_path / "out", store=store)
    job = Job(id="x1", source="text", owner=person.id, home=library.home(person), estimate=0.2)
    _claimed(library, job)
    build = Halfway(library, job)
    monkeypatch.setattr(Library, "_builder", lambda _self, _job: build)
    library.run(job)
    row = _row(store, "x1")
    assert row["length"] == 0 and row["spent"] == pytest.approx(build.usage.cost())


def test_a_build_already_done_is_not_stopped(tmp_path: Path) -> None:
    """Its reader is drawn: a stop asked a moment too late takes nothing back."""
    library = Library(tmp_path)
    job = Job(id="d", source="s", owner=1, stage="working")
    job.stop = True
    job.stage = "done"
    library._checkpoint(job)  # does not raise
    assert library.cancel(job) == "finished"
    working = Job(id="w", source="s", owner=1, stage="working")
    working.stop = True
    with pytest.raises(Stopped):
        library._checkpoint(working)


def test_a_build_that_rewrites_a_reader_is_cancelled_waiting_and_never_stopped(
    tmp_path: Path,
) -> None:
    library = Library(tmp_path)
    for option in ("chapters", "voice", "cover", "again", "words_again"):
        job = Job(id=option, source="s", owner=1, stage="working", options={option: [1]})
        assert library.cancel(job) == "unstoppable", option
        assert not job.stop
        assert library.cancelling(job)["cancellable"] is False
        waiting = Job(id=option + "-q", source="s", owner=1, stage="queued", options={option: [1]})
        assert library.cancelling(waiting)["cancellable"] is True
    assert library.cancelling(Job(id="t", source="s", owner=1, stage="working"))["cancellable"]


# -- whose ----------------------------------------------------------------------------


@pytest.fixture
def two(tmp_path: Path) -> Iterator[tuple[int, Library, Store, str, str]]:
    """A server with two readers signed in; the first has a build waiting."""
    store = Store(tmp_path / "db")
    library = Library(tmp_path / "out", store=store)
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    server.RequestHandlerClass = type(
        "CancelHandler",
        (Handler,),
        {
            "library": library,
            "store": store,
            "token": "k",
            "address": f"http://127.0.0.1:{port}",
            "translated": {},
        },
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    _, mine = _person(store, "owner@example.com")
    _, theirs = _person(store, "stranger@example.com")
    try:
        yield port, library, store, mine, theirs
    finally:
        server.shutdown()
        server.server_close()


def _cancel(port: int, job_id: str, session: str) -> tuple[int, Any]:
    connection = HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        connection.request(
            "POST",
            "/jobs/cancel?k=k",
            json.dumps({"id": job_id}).encode(),
            {"Content-Type": "application/json", "Cookie": f"targum_session={session}"},
        )
        response = connection.getresponse()
        return response.status, json.loads(response.read())
    finally:
        connection.close()


def test_nobody_cancels_another_reader_s_build(two: Any) -> None:
    port, library, store, mine, theirs = two
    owner = store.whoever(mine)
    job = _recording("o1", owner.id, library.home(owner))
    _claimed(library, job)

    status, answer = _cancel(port, "o1", theirs)
    assert status == 404 and answer == {"error": "not found"}
    assert job.stage == "queued", "untouched"
    assert _row(store, "o1")["claimed"] == pytest.approx(0.40), "and its claim held"

    status, answer = _cancel(port, "o1", mine)
    assert status == 200 and answer == {"cancelled": True, "stopping": False}
    assert _row(store, "o1")["length"] == 0


def test_a_build_that_cannot_stop_says_so(two: Any) -> None:
    port, library, store, mine, _theirs = two
    owner = store.whoever(mine)
    job = Job(id="c1", source="s", owner=owner.id, stage="working", options={"chapters": [2]})
    library.jobs[job.id] = job
    status, answer = _cancel(port, "c1", mine)
    assert status == 409 and "can't be stopped" in answer["error"]
    done = Job(id="d1", source="s", owner=owner.id, stage="done", made=now())
    library.jobs[done.id] = done
    status, answer = _cancel(port, "d1", mine)
    assert status == 409 and "finished" in answer["error"]


# -- the three places ---------------------------------------------------------------


def _drawn(**payload: Any) -> dict[str, Any]:
    if shutil.which("node") is None:
        pytest.skip("node is not installed")
    with tempfile.TemporaryDirectory() as where:
        path = Path(where) / "payload.json"
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        done = subprocess.run(
            ["node", str(HARNESS), str(path)], capture_output=True, text=True, timeout=60
        )
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


WAITING = {
    "id": "w1",
    "title": "Un film",
    "language": "fr",
    "stage": "queued",
    "cancellable": True,
    "stopping": False,
    "behind": 1,
}
RUNNING = {**WAITING, "id": "r1", "stage": "working", "behind": 0, "total": 10, "done": 4}


@pytest.mark.parametrize("place", ["row", "card"])
def test_a_waiting_build_is_cancelled_at_one_quiet_press(place: str) -> None:
    said = _drawn(
        place=place,
        job=WAITING,
        press=["Cancel"],
        answers={"/jobs/cancel": {"cancelled": True, "stopping": False}},
    )
    (press,) = said["before"]["presses"]
    assert press["text"] == "Cancel" and press["label"] == "Cancel Un film"
    assert "ghost outline" in press["className"] and "filled" not in press["className"]
    assert [one for one in said["asked"] if one["path"] == "/jobs/cancel"] == [
        {"path": "/jobs/cancel", "method": "POST", "body": {"id": "w1", "waiting": True}}
    ], "no question first: nothing is lost"
    assert said["gone"], "and it leaves the list"


@pytest.mark.parametrize("place", ["row", "card"])
def test_a_running_build_asks_once_before_it_stops(place: str) -> None:
    asked = _drawn(place=place, job=RUNNING, press=["Cancel"])
    assert "Stop this build? You'll still pay for what's done so far." in asked["after"]["words"]
    assert [p["text"] for p in asked["after"]["presses"]] == ["Stop it", "Keep building"]
    assert not [one for one in asked["asked"] if one["path"] == "/jobs/cancel"], "not yet"

    kept = _drawn(place=place, job=RUNNING, press=["Cancel", "Keep building"])
    assert [p["text"] for p in kept["after"]["presses"]] == ["Cancel"]
    assert not [one for one in kept["asked"] if one["path"] == "/jobs/cancel"]

    stopped = _drawn(
        place=place,
        job=RUNNING,
        press=["Cancel", "Stop it"],
        answers={
            "/jobs/cancel": {"cancelled": False, "stopping": True},
            "/job/r1": {"id": "r1", "stage": "cancelled"},
        },
    )
    assert [one["body"] for one in stopped["asked"] if one["path"] == "/jobs/cancel"] == [
        {"id": "r1"}
    ]


def test_a_build_not_yours_to_cancel_draws_no_cancel() -> None:
    for place in ("row", "card"):
        said = _drawn(place=place, job={**RUNNING, "cancellable": False})
        assert said["before"]["presses"] == [], place


def test_the_waiting_card_names_yours_ahead_and_counts_the_rest() -> None:
    said = _drawn(
        place="ahead",
        job={
            **WAITING,
            "ahead": [
                {"id": "a1", "title": "Mon autre film", "stage": "working", "cancellable": True}
            ],
            "ahead_others": 2,
        },
    )
    assert "Mon autre film" in said["before"]["words"]
    assert [p["label"] for p in said["before"]["presses"]] == ["Cancel Mon autre film"]
    assert (
        "2 builds ahead are other people's. Only they can cancel them." in said["before"]["words"]
    )


def test_the_waiting_card_draws_cancel() -> None:
    """add.js's card is not harnessed (it needs the whole Upload page); what it draws is
    `cancel.js`'s, pinned above, and this holds that it draws it, from the state it is
    following, and says the server's own line when the build has gone."""
    source = (Path(__file__).resolve().parents[1] / "src/targum/render/assets/add.js").read_text(
        encoding="utf-8"
    )
    watch = source[source.index("function watch(job, first)") :]
    watch = watch[: watch.index("/* --- a post, brought by hand")]
    assert "undo.ahead(state" in watch and "undo.control(" in watch
    assert 'end.stage === "cancelled"' in watch


# -- qa-claude on #1199 ----------------------------------------------------------------


def test_a_waiting_cancel_keeps_what_reading_the_pictures_cost(tmp_path: Path) -> None:
    """`_read_pages` reads pictures before the press and settles them to their receipt
    on the job's own row. A waiting cancel gives back what was held and not spent: the
    credits and the build's claim, never the dollars the pictures already cost."""
    store = Store(tmp_path / "db")
    person, _ = _person(store, "reader@example.com")
    library = Library(tmp_path / "out", store=store)
    job = Job(id="pic", source="pic.jpg", owner=person.id, home=library.home(person))
    library.jobs[job.id] = job
    library.remember(job)
    job.estimate = 0.30  # as `_read_pages` reserves, reads and settles
    assert library.claim(job) == ""
    job.reading = job.spent = 0.22
    job.estimate = 0.0
    library.settle(job)
    job.stage = "ready"
    job.estimate = 0.15
    assert library.press(job) == ""
    assert store.committed(0, person.id) == pytest.approx(0.15)

    assert library.cancel(job) == "cancelled"

    row = _row(store, "pic")
    assert row["claimed"] == pytest.approx(0.22) and row["spent"] == pytest.approx(0.22)
    assert row["length"] == 0
    assert store.committed(0, person.id) == pytest.approx(0.22), "the pictures stay paid for"


def test_a_stopped_build_pressed_again_keeps_its_receipt(tmp_path: Path, monkeypatch: Any) -> None:
    """A press on a cancelled build would claim over its receipt. It is left as it is;
    starting it again is a new quote with a new id."""
    store = Store(tmp_path / "db")
    person, _ = _person(store, "reader@example.com")
    library = Library(tmp_path / "out", store=store)
    job = _recording("again", person.id, library.home(person))
    _claimed(library, job)
    library.queue.get_nowait()  # the worker's take, run by hand below
    monkeypatch.setattr(Library, "_builder", lambda _self, _job: Halfway(library, job))
    library.run(job)
    receipt = _row(store, "again")
    assert receipt["stage"] == "cancelled" and receipt["length"] == pytest.approx(120.0)

    assert library.press(job) == ""
    assert job.stage == "cancelled" and library.queue.empty(), "not back in the line"
    assert _row(store, "again") == receipt, "the receipt stands"

    waiting = _recording("gone", person.id, library.home(person))
    _claimed(library, waiting)
    library.queue.get_nowait()
    assert library.cancel(waiting) == "cancelled"
    assert library.press(waiting) == "" and waiting.stage == "cancelled"
    assert _row(store, "gone")["claimed"] == 0 and library.queue.empty()


def test_a_page_that_saw_it_waiting_is_asked_before_a_stop(tmp_path: Path) -> None:
    """The page's last look said waiting; the worker took it since. The press is not a
    stop: the server says it started, and the page asks its one question first."""
    store = Store(tmp_path / "db")
    person, _ = _person(store, "reader@example.com")
    library = Library(tmp_path / "out", store=store)
    job = _recording("st", person.id, library.home(person))
    _claimed(library, job)
    assert library._take(job)
    assert library.cancel(job, waiting=True) == "started"
    assert not job.stop
    job.stage = "working"
    assert library.cancel(job, waiting=True) == "started" and not job.stop
    assert library.cancel(job) == "stopping" and job.stop, "the answer to the question stops it"


@pytest.mark.parametrize("stage", ["failed", "blocked", "ready", "reading"])
def test_a_build_that_is_not_being_made_says_so_and_changes_nothing(
    tmp_path: Path, stage: str
) -> None:
    store = Store(tmp_path / "db")
    person, _ = _person(store, "reader@example.com")
    library = Library(tmp_path / "out", store=store)
    job = _recording("end", person.id, library.home(person))
    _claimed(library, job)
    job.spent = 0.31
    library.settle(job)
    job.stage = stage
    library.remember(job)
    before = _row(store, "end")
    assert library.cancel(job) == "over"
    assert _row(store, "end") == before and job.stage == stage


def test_the_server_says_started_and_over_in_its_own_words(two: Any) -> None:
    port, library, store, mine, _theirs = two
    owner = store.whoever(mine)
    job = _recording("h1", owner.id, library.home(owner))
    _claimed(library, job)
    library._take(job)
    connection = HTTPConnection("127.0.0.1", port, timeout=5)
    connection.request(
        "POST",
        "/jobs/cancel?k=k",
        json.dumps({"id": "h1", "waiting": True}).encode(),
        {"Content-Type": "application/json", "Cookie": f"targum_session={mine}"},
    )
    response = connection.getresponse()
    assert response.status == 409 and json.loads(response.read())["started"] is True
    connection.close()
    assert not job.stop
    failed = Job(id="f1", source="s", owner=owner.id, stage="failed")
    library.jobs[failed.id] = failed
    status, answer = _cancel(port, "f1", mine)
    assert status == 409 and "nothing to cancel" in answer["error"]
    assert "finished" not in answer["error"]


def test_a_card_that_finds_its_build_started_asks_before_stopping() -> None:
    for place in ("row", "card"):
        said = _drawn(
            place=place,
            job=WAITING,
            press=["Cancel"],
            answers={"/jobs/cancel": {"started": True, "stage": "working"}},
        )
        assert "Stop this build? You'll still pay for what's done so far." in said["after"]["words"]
        assert [p["text"] for p in said["after"]["presses"]] == ["Stop it", "Keep building"]
        posts = [one["body"] for one in said["asked"] if one["path"] == "/jobs/cancel"]
        assert posts == [{"id": "w1", "waiting": True}], "one look, and no stop yet"
