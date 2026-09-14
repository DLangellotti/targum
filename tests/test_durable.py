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
    assert "at once" in blocked or "our limit" in blocked


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
