"""Builds and money outlive the process.

Both used to live in memory: a dictionary of jobs and a float beside it. Restarting
lost every running build and handed the whole budget back to whoever asked next, which
on a laptop is a shrug and on a box anyone can reach is the spending limit not existing.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from targum.accounts import Store, now
from targum.cache import Cache
from targum.paths import write_atomic
from targum.serve import BUDGET_HOURS, Job, Library


def library(tmp_path: Path, budget: float = 10.0) -> tuple[Library, Store]:
    # max_cost is the per-text ceiling and the per-account rail is a rate limit;
    # neither is what these tests are about. Both are off so the whole-box budget is
    # the only thing that can refuse a build.
    store = Store(tmp_path / "targum.db")
    return Library(
        tmp_path / "out",
        max_cost=budget,
        budget=budget,
        store=store,
        account_budget=None,
    ), store


def job(library: Library, estimate: float, **kw: object) -> Job:
    made = Job(
        id=kw.pop("id", "j1"),  # type: ignore[arg-type]
        source="memory:x",
        estimate=estimate,
        home=library.out / "local",
        **kw,  # type: ignore[arg-type]
    )
    library.jobs[made.id] = made
    library.remember(made)
    return made


def test_money_claimed_survives_a_restart(tmp_path: Path) -> None:
    first, store = library(tmp_path)
    assert first.claim(job(first, 4.0)) == ""
    assert first.committed == 4.0

    # The process dies and comes back against the same file.
    second = Library(
        tmp_path / "out", max_cost=10.0, budget=10.0, store=Store(tmp_path / "targum.db")
    )
    assert second.committed == 4.0, "a restart handed the budget back"
    assert second.remaining() == 6.0


def test_the_budget_still_refuses_after_a_restart(tmp_path: Path) -> None:
    first, _ = library(tmp_path, budget=5.0)
    assert first.claim(job(first, 4.0)) == ""

    second = Library(
        tmp_path / "out", max_cost=5.0, budget=5.0, store=Store(tmp_path / "targum.db")
    )
    blocked = second.claim(job(second, 4.0, id="j2"))
    assert blocked, "the second build should not fit in what is left"
    assert "in one day" in blocked or "our limit" in blocked


def test_a_failed_build_gives_its_money_back(tmp_path: Path) -> None:
    lib, _ = library(tmp_path)
    one = job(lib, 3.0)
    assert lib.claim(one) == ""
    assert lib.committed == 3.0
    lib.release(one)
    assert lib.committed == 0.0

    after = Library(
        tmp_path / "out", max_cost=10.0, budget=10.0, store=Store(tmp_path / "targum.db")
    )
    assert after.committed == 0.0


def test_a_build_caught_mid_flight_is_told_the_truth(tmp_path: Path) -> None:
    """It cannot be resumed — the thread is gone — but it must stop saying "working"."""
    lib, _ = library(tmp_path)
    running = job(lib, 2.0)
    assert lib.claim(running) == ""
    running.stage = "working"
    lib.remember(running)

    after = Library(
        tmp_path / "out", max_cost=10.0, budget=10.0, store=Store(tmp_path / "targum.db")
    )
    recovered = after.jobs[running.id]
    assert recovered.stage == "failed"
    assert "restarted" in recovered.error
    # Its claim is kept. It had probably started paying for batches and nothing records
    # how much, so handing it back would let a crash loop spend without limit.
    assert after.committed == 2.0


def test_a_build_caught_mid_flight_gives_its_hours_back(tmp_path: Path) -> None:
    """The money is kept, the hours are not. The box was OOM-killed on the same video
    four times in an hour on 2026-09-14, and each try kept the whole recording's length
    against the month — a reader charged four hours for a video they never got. The
    money claim ages out within the day; the hours stayed until the month turned."""
    lib, store = library(tmp_path)
    running = job(lib, 2.0)
    assert store.claim(running.id, 2.0, 10.0, 0, length=3600.0) == ""
    running.stage = "working"
    lib.remember(running)
    assert store.hours_used(None, 0) == 3600.0

    after = Library(
        tmp_path / "out", max_cost=10.0, budget=10.0, store=Store(tmp_path / "targum.db")
    )
    assert after.jobs[running.id].stage == "failed"
    assert Store(tmp_path / "targum.db").hours_used(None, 0) == 0.0
    assert after.committed == 2.0, "the money claim is still kept"


def test_a_restart_repairs_the_hours_an_earlier_restart_kept(tmp_path: Path) -> None:
    """Rows failed by a restart before the hours went back still hold their length. The
    next start-up gives it back, so no one has to edit the live database by hand."""
    lib, store = library(tmp_path)
    old = job(lib, 2.0, stage="failed", error="targum restarted while this was building.")
    assert store.claim(old.id, 2.0, 10.0, 0, length=1800.0) == ""
    other = job(lib, 1.0, id="j2", stage="failed", error="The video is private.")
    assert store.claim(other.id, 1.0, 10.0, 0, length=600.0) == ""

    Library(tmp_path / "out", max_cost=10.0, budget=10.0, store=Store(tmp_path / "targum.db"))
    assert Store(tmp_path / "targum.db").hours_used(None, 0) == 600.0


def test_a_build_still_in_line_is_let_go_and_its_money_given_back(tmp_path: Path) -> None:
    """The line was memory, and nothing puts a recovered job back on it: a queued build
    sat at "queued" for good. It never started, so its claim goes back."""
    lib, _ = library(tmp_path)
    waiting = job(lib, 2.0)
    assert lib.claim(waiting) == ""
    lib.enqueue(waiting)

    after = Library(
        tmp_path / "out", max_cost=10.0, budget=10.0, store=Store(tmp_path / "targum.db")
    )
    recovered = after.jobs[waiting.id]
    assert recovered.stage == "failed" and "restarted" in recovered.error
    assert after.committed == 0.0, "nothing was spent on a build that never started"


def test_a_chat_turn_caught_mid_answer_is_told_the_truth(tmp_path: Path) -> None:
    """A deploy restarts the box. The turn's job row was swept, and the reader's line
    stayed at "working" for good (targum-internal#269)."""
    _, store = library(tmp_path)
    chat = store.chat_open(None)
    asked = store.chat_say(chat, "user", "find me tech news", "find me tech news", stage="working")
    answered = store.chat_say(chat, "user", "hello", "hello", stage="done")

    Library(tmp_path / "out", max_cost=10.0, budget=10.0, store=Store(tmp_path / "targum.db"))
    turns = {turn["n"]: turn for turn in Store(tmp_path / "targum.db").chat_turns(chat)}
    assert turns[asked]["stage"] == "failed"
    assert "restarted" in turns[asked]["error"] and "Ask again" in turns[asked]["error"]
    assert turns[answered]["stage"] == "done" and turns[answered]["error"] == ""


def test_a_job_comes_back_made_when_it_was_made(tmp_path: Path) -> None:
    """Not at start-up: a history made "lately" by every restart filled the bell with it."""
    lib, _ = library(tmp_path)
    old = job(lib, 1.0)
    old.made = now() - 3 * 24 * 60 * 60 * 1000
    old.stage = "done"
    lib.remember(old)

    after = Library(
        tmp_path / "out", max_cost=10.0, budget=10.0, store=Store(tmp_path / "targum.db")
    )
    assert after.jobs[old.id].made == old.made
    assert after.mine(None) == [], "three days old and settled is not something to follow"


def test_a_refusing_site_is_said_plainly() -> None:
    """A 403 reached the bell as the HTTP library's own paragraph, a link to MDN and all."""
    import httpx

    from targum.serve import unreadable

    request = httpx.Request("GET", "https://example.test/page?utm_source=x")
    for status, words in ((403, "won't let us"), (404, "isn't there"), (502, "didn't answer")):
        error = httpx.HTTPStatusError(
            "Client error", request=request, response=httpx.Response(status, request=request)
        )
        said = unreadable(error)
        assert words in said and "http" not in said, said
    assert "couldn't read" in unreadable(ValueError("a stack of detail"))
    # And in the reader's language: it reached a Russian bell in English (#377).
    assert unreadable(ValueError("x"), "ru").startswith("Не удалось")


def test_a_hosted_box_says_the_readers_sentence_and_keeps_the_detail_for_the_log() -> None:
    """Copy audit, 2026-09-28 (Q5). A link refusal reached readers as "We couldn't open
    https://…. HTTP 403", a curl exception, or an operator's "install yt-dlp". On a box
    the reader is told the sentence for the status; on a laptop the reader is the
    operator, and the detail is the useful part, so it stays."""
    from targum.errors import OffHere, TargumError, Unreachable
    from targum.serve import told

    shut = Unreachable(
        "We couldn't open https://x.test/a.",
        "HTTP 403",
        status=403,
        host="x.test",
        key="fetch.would-not-open",
        url="https://x.test/a",
    )
    hosted = told("en", shut, hosted=True)
    assert "won't let us" in hosted and "HTTP" not in hosted, hosted
    assert "HTTP 403" in told("en", shut, hosted=False), "the laptop keeps the detail"
    gone = Unreachable(
        "We couldn't open https://x.test/a.",
        "404 Not Found",
        status=404,
        key="fetch.would-not-open",
        url="https://x.test/a",
    )
    assert "isn't there" in told("en", gone, hosted=True)
    curl = Unreachable(
        "We couldn't open https://x.test/a.",
        "curl: (28) Operation timed out after 20001 milliseconds",
        key="fetch.would-not-open",
        url="https://x.test/a",
    )
    assert "curl" not in told("en", curl, hosted=True)
    assert "Не удалось" in told("ru", curl, hosted=True), "and in the reader's language"
    nowhere = TargumError(
        "We couldn't find x.test.",
        "[Errno 8] nodename nor servname",
        key="fetch.no-such-site",
        host="x.test",
    )
    assert "Errno" not in told("en", nowhere, hosted=True)
    tool = OffHere(
        "yt-dlp is not installed.", "install yt-dlp. YouTube imports are off until it is."
    )
    assert "install" not in told("en", tool, hosted=True)
    assert "install yt-dlp" in told("en", tool, hosted=False)
    # A refusal written for a reader is said as it always was, box or laptop.
    sign_in = Unreachable(
        "x.test asks you to sign in, so we can't open it.",
        "Open it yourself and paste the text into the box instead.",
        status=401,
        key="fetch.needs-a-sign-in",
        site="x.test",
    )
    assert told("en", sign_in, hosted=True).startswith("x.test asks you to sign in")


def test_a_hosted_box_without_ytdlp_does_not_tell_the_reader_to_install_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "targum.video.ytdlp_available",
        lambda: (False, "install yt-dlp. YouTube imports are off until it is."),
    )
    for hosted, install in ((True, False), (False, True)):
        box = Library(tmp_path / str(hosted), hosted=hosted)
        failed = Job(id="a", source="https://www.youtube.com/watch?v=abc123")
        box.prepare(failed)
        assert failed.stage == "failed"
        assert "can't bring in YouTube" in failed.error
        assert ("install yt-dlp" in failed.error) is install, failed.error


def test_a_refusal_raised_mid_build_is_said_in_the_readers_language_with_its_hint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Copy audit, 2026-09-28 (Q6). `_blame` was handed `error.message`: English whatever
    the reader reads, and the hint dropped on the floor."""
    from targum.errors import TargumError

    box, _ = library(tmp_path)

    def refuse(_job: Job) -> None:
        raise TargumError(
            "https://x.test/a is too big for us to read.",
            "Try a single article.",
            key="fetch.too-big-to-read",
            url="https://x.test/a",
        )

    monkeypatch.setattr(box, "_builder", refuse)
    russian = Job(id="ru1", source="https://x.test/a", ui="ru")
    box.run(russian)
    assert russian.stage == "failed"
    assert russian.error == (
        "https://x.test/a слишком велик, чтобы мы его прочитали. Попробуйте отдельную статью."
    )
    english = Job(id="en1", source="https://x.test/a")
    box.run(english)
    assert english.error.endswith("Try a single article."), "the hint is no longer dropped"


def test_jobs_come_back_with_what_the_page_needs(tmp_path: Path) -> None:
    lib, _ = library(tmp_path)
    done = job(lib, 1.0, owner=7, title="A Book", language="he", segments=41)
    done.stage = "done"
    done.reader = "a-book-he/reader/index.html"
    lib.remember(done)

    after = Library(
        tmp_path / "out", max_cost=10.0, budget=10.0, store=Store(tmp_path / "targum.db")
    )
    back = after.jobs[done.id]
    assert back.stage == "done"
    assert back.title == "A Book"
    assert back.language == "he"
    assert back.segments == 41
    assert back.reader == "a-book-he/reader/index.html"
    assert back.owner == 7
    assert back.home == lib.out / "local"


def test_spending_falls_out_of_the_window(tmp_path: Path) -> None:
    """The budget is a rolling day, not a total that eventually bricks the machine."""
    lib, store = library(tmp_path)
    old = job(lib, 9.0)
    assert lib.claim(old) == ""
    assert lib.committed == 9.0

    stale = now() - (BUDGET_HOURS + 1) * 60 * 60 * 1000
    with store.write() as db:
        db.execute("UPDATE job SET made = ? WHERE id = ?", (stale, old.id))

    assert lib.committed == 0.0, "yesterday's spend still counts against today"
    assert lib.claim(job(lib, 9.0, id="j2")) == ""


def test_two_claims_at_once_cannot_both_pass(tmp_path: Path) -> None:
    lib, _ = library(tmp_path, budget=5.0)
    assert lib.claim(job(lib, 3.0, id="a")) == ""
    assert lib.claim(job(lib, 3.0, id="b")) != ""
    assert lib.committed == 3.0


def test_a_cache_entry_is_never_half_written(tmp_path: Path) -> None:
    """A torn entry reads as a miss, and a miss is a book bought a second time.

    The failure needs two processes to see, so it is staged instead: writing over an
    entry that is already there must leave either the old value or the new one, and
    the target must never be the file the bytes land in.
    """
    cache = Cache(tmp_path)
    cache.put("translate", "abc123", {"segments": ["first"]})
    landed: list[Path] = []
    real = Path.write_text

    def watched(self: Path, *args: object, **kw: object) -> int:
        landed.append(self)
        return real(self, *args, **kw)  # type: ignore[arg-type]

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(Path, "write_text", watched)
        cache.put("translate", "abc123", {"segments": ["second"]})

    assert cache.get("translate", "abc123") == {"segments": ["second"]}
    assert landed and cache._path("translate", "abc123") not in landed
    assert list(tmp_path.rglob(".*.tmp")) == []


def test_a_failed_write_leaves_the_previous_version(tmp_path: Path) -> None:
    target = tmp_path / "glossary.json"
    write_atomic(target, "the old one")

    def explode(self: Path, *args: object, **kw: object) -> int:
        raise OSError("disk full")

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(Path, "write_text", explode)
        with pytest.raises(OSError):
            write_atomic(target, "the new one")

    assert target.read_text(encoding="utf-8") == "the old one"
    assert list(tmp_path.glob(".*.tmp")) == []


# -- the rails and who they apply to --------------------------------------------


def capped(tmp_path: Path, day: float = 10.0) -> tuple[Library, Store]:
    """A library with the rails a hosted box actually runs with.

    A daily rate limit and a box ceiling, and no monthly cap on a reader at all — text
    uploads are unlimited, so the only thing a subscriber is held to is audio hours.
    """
    store = Store(tmp_path / "targum.db")
    return Library(
        tmp_path / "out",
        max_cost=100.0,
        budget=1000.0,
        store=store,
        account_budget=day,
    ), store


def person(store: Store, email: str, *, admin: bool = False) -> int:
    if admin:
        store.make_admin(email)
    store.invite(email)
    store.start_sign_in(email)
    row = store.db.execute("SELECT id FROM person WHERE email = ?", (email,)).fetchone()
    return int(row["id"])


def test_an_admin_is_not_held_to_the_rails(tmp_path: Path) -> None:
    """They exist to stop a reader running up somebody else's bill, and the person
    paying it is not that reader."""
    lib, store = capped(tmp_path)
    boss = person(store, "boss@example.invalid", admin=True)

    for n in range(5):
        assert lib.claim(job(lib, 6.0, id=f"a{n}", owner=boss, admin=True)) == "", (
            "thirty dollars is well past a reader's ten"
        )


def test_the_box_ceiling_is_not_waived_for_an_admin(tmp_path: Path) -> None:
    """That one is the runaway guard, and a loop at three in the morning does not care
    whose account it is on."""
    store = Store(tmp_path / "targum.db")
    lib = Library(
        tmp_path / "out",
        max_cost=100.0,
        budget=5.0,
        store=store,
        account_budget=10.0,
    )
    boss = person(store, "boss@example.invalid", admin=True)

    assert lib.claim(job(lib, 4.0, id="a", owner=boss, admin=True)) == ""
    refused = lib.claim(job(lib, 4.0, id="b", owner=boss, admin=True))
    assert refused and "We've hit our limit for today" in refused


def test_one_readers_spending_does_not_count_against_another(tmp_path: Path) -> None:
    lib, store = capped(tmp_path)
    one = person(store, "one@example.invalid")
    two = person(store, "two@example.invalid")

    assert lib.claim(job(lib, 9.0, id="a", owner=one)) == ""
    assert lib.claim(job(lib, 9.0, id="b", owner=two)) == "", "two people, two allowances"


def test_an_admin_buying_a_chapter_is_never_in_the_way(tmp_path: Path) -> None:
    lib, store = capped(tmp_path)
    boss = person(store, "boss@example.invalid", admin=True)
    lib.claim(job(lib, 50.0, id="a", owner=boss, admin=True))

    assert lib.already_over(job(lib, 0.0, id="ch", owner=boss, admin=True)) == ""


DAY_MS = 24 * 60 * 60 * 1000


def test_a_restart_holds_a_day_of_history_and_reads_the_rest_back(tmp_path: Path) -> None:
    """targum-internal#231: the table is the record and the process holds a window. Two
    thousand settled jobs from last month cost a restart nothing, and any one of them
    still answers by its id, as `/job/<id>` always has."""
    lib, store = library(tmp_path)
    for n in range(2000):
        old = Job(id=f"old{n}", source="x", estimate=0.0, kind="chat" if n % 2 else "build")
        old.made = now() - 30 * DAY_MS
        old.stage = "done"
        lib.remember(old)
    fresh = job(lib, 0.1)
    fresh.stage = "done"
    lib.remember(fresh)
    stuck = Job(id="stuck", source="x", estimate=0.0)
    stuck.made = now() - 30 * DAY_MS
    stuck.stage = "ready"  # a quote nobody has pressed yet
    lib.remember(stuck)

    after = Library(
        tmp_path / "out", max_cost=10.0, budget=10.0, store=Store(tmp_path / "targum.db")
    )
    assert len(after.jobs) == 2, "only the day's job and the unpressed quote are held"
    assert "old7" not in after.jobs
    assert after.jobs["old7"].stage == "done", "and an old one still answers"
    assert after.jobs.get("old7") is after.jobs.get("old7"), "read back once, then held"
    assert after.jobs.get("nothing") is None
    with pytest.raises(KeyError):
        after.jobs["nothing"]


def test_a_settled_job_stops_being_held_and_a_running_one_never_does(tmp_path: Path) -> None:
    lib, _ = library(tmp_path)
    settled = job(lib, 0.1, id="settled")
    settled.stage, settled.made = "failed", now() - 2 * DAY_MS
    working = job(lib, 0.1, id="working")
    working.stage, working.made = "working", now() - 2 * DAY_MS
    lib.remember(settled)
    lib.remember(working)
    settled.finished = now() - 2 * DAY_MS  # it ended long ago, as well as began

    assert lib.jobs.sweep(now() - lib.jobs.HELD_MS) == 1
    assert working.id in lib.jobs, "a worker is writing to it"
    assert settled.id not in lib.jobs
    assert lib.jobs[settled.id].stage == "failed", "still on disk, still answering"


def test_held_jobs_are_swept_as_new_ones_arrive(tmp_path: Path, monkeypatch) -> None:
    """The sweep rides on adding a job, every `SWEEP_EVERY`, so a long-lived process stays
    flat however many turns it takes."""
    from targum.serve import Jobs

    monkeypatch.setattr(Jobs, "SWEEP_EVERY", 10)
    lib, _ = library(tmp_path)
    after = Library(tmp_path / "out", max_cost=10.0, budget=10.0, store=lib.store)
    for n in range(95):
        turn = Job(id=f"t{n}", source="x", estimate=0.0, kind="chat")
        turn.stage, turn.made = "done", now() - 2 * DAY_MS
        after.jobs[turn.id] = turn
    assert len(after.jobs) < 10, "never more than one sweep's worth held"


def test_a_done_build_still_finishing_is_not_let_go(tmp_path: Path) -> None:
    """Review, 2026-10-08: a build says "done" when its reader is up and its worker goes
    on looking up meanings. Pressed a day after its quote, `made` is old; `finished` is
    not, and it is held until both are."""
    lib, _ = library(tmp_path)
    late = job(lib, 0.1, id="late")
    late.made = now() - 2 * DAY_MS
    late.stage = "done"
    lib.remember(late)
    assert late.finished > now() - DAY_MS, "stamped as it settled, just now"
    assert lib.jobs.sweep(now() - lib.jobs.HELD_MS) == 0
    assert lib.jobs.get("late") is late, "the worker's own object, not a second one"


def test_a_quote_pressed_after_a_restart_is_charged_what_it_was_priced_at(
    tmp_path: Path,
) -> None:
    """A recording quoted before a restart and pressed after it was charged no credits
    and built anyway: `audio` and `seconds` lived only in memory, so the job read back
    came with neither, `claim` held it to no hours, and the model was paid for a build
    nobody was charged for (2026-10-09)."""
    first, _ = library(tmp_path)
    quoted = job(
        first,
        0.5,
        stage="ready",
        audio=True,
        seconds=1800.0,
        parts=3,
        transcription=0.18,
        reading=0.02,
    )
    first.remember(quoted)

    # The deploy restarts the box between the quote and the press.
    after, store = library(tmp_path)
    recovered = after.jobs[quoted.id]
    assert (recovered.audio, recovered.seconds) == (True, 1800.0)
    assert (recovered.parts, recovered.transcription, recovered.reading) == (3, 0.18, 0.02)
    assert after.press(recovered) == ""
    assert store.hours_used(None, 0) == 1800.0, "a quote pressed after a restart was free"

    # A job no longer held, read back by id as a press from an old card reads it, is
    # priced the same way.
    from_disk = after._job_from_store(quoted.id)
    assert from_disk is not None and (from_disk.audio, from_disk.seconds) == (True, 1800.0)


def test_a_database_from_before_the_price_columns_gains_them(tmp_path: Path) -> None:
    import sqlite3

    from targum.accounts import SCHEMA_VERSION

    path = tmp_path / "old.db"
    Store(path).save_job({"id": "old", "owner": None, "home": "/tmp", "source": "x"})
    raw = sqlite3.connect(path)
    raw.executescript(
        "ALTER TABLE job DROP COLUMN audio; ALTER TABLE job DROP COLUMN seconds;"
        "ALTER TABLE job DROP COLUMN parts; ALTER TABLE job DROP COLUMN transcription;"
        "ALTER TABLE job DROP COLUMN reading; PRAGMA user_version = 43;"
    )
    raw.close()
    store = Store(path)
    columns = {row["name"] for row in store.db.execute("PRAGMA table_info(job)")}
    assert {"audio", "seconds", "parts", "transcription", "reading"} <= columns
    assert store.db.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
    old = store.job("old")
    assert old is not None and (old["audio"], old["seconds"]) == (0, 0.0)
