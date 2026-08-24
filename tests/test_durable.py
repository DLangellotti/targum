"""Builds and money outlive the process.

Both used to live in memory: a dictionary of jobs and a float beside it. Restarting
lost every running build and handed the whole budget back to whoever asked next, which
on a laptop is a shrug and on a box anyone can reach is the spending limit not existing.
"""

from __future__ import annotations

from pathlib import Path

from targum.accounts import Store, now
from targum.serve import BUDGET_HOURS, Job, Library


def library(tmp_path: Path, budget: float = 10.0) -> tuple[Library, Store]:
    # max_cost is the per-text ceiling and is not what these tests are about; raised so
    # the session budget is the only thing that can refuse a build.
    store = Store(tmp_path / "targum.db")
    return Library(
        tmp_path / "out", max_cost=budget, budget=budget, store=store, account_budget=None
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
    assert "sitting" in blocked or "take on" in blocked


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
