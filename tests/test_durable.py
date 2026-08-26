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
    # max_cost is the per-text ceiling and the two per-account rails are a reader's
    # allowance; neither is what these tests are about. All three are off so the
    # whole-box budget is the only thing that can refuse a build — which matters for the
    # window tests especially, where a job aged out of the day is still inside the month.
    store = Store(tmp_path / "targum.db")
    return Library(
        tmp_path / "out",
        max_cost=budget,
        budget=budget,
        store=store,
        account_budget=None,
        month_budget=None,
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
    assert "your fill" in blocked or "its limit" in blocked


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


# -- the monthly cap and who it applies to --------------------------------------


def capped(tmp_path: Path, month: float = 10.0) -> tuple[Library, Store]:
    """A library with the rails a hosted box actually runs with."""
    store = Store(tmp_path / "targum.db")
    return Library(
        tmp_path / "out",
        max_cost=100.0,
        budget=1000.0,
        store=store,
        account_budget=None,
        month_budget=month,
    ), store


def person(store: Store, email: str, *, admin: bool = False) -> int:
    if admin:
        store.make_admin(email)
    store.invite(email)
    store.start_sign_in(email)
    row = store.db.execute("SELECT id FROM person WHERE email = ?", (email,)).fetchone()
    return int(row["id"])


def test_a_reader_is_held_to_the_month_not_only_the_day(tmp_path: Path) -> None:
    """The daily rail is a rate limit — it stops one afternoon running away. Thirty days
    of it is thirty times the number anybody agreed to, which is why this exists."""
    lib, store = capped(tmp_path)
    who = person(store, "reader@example.invalid")

    assert lib.claim(job(lib, 6.0, id="a", owner=who)) == ""
    assert lib.claim(job(lib, 3.0, id="b", owner=who)) == ""
    refused = lib.claim(job(lib, 3.0, id="c", owner=who))

    assert refused, "nine spent and three more is over ten"
    assert "this month" in refused
    assert "library is always free" in refused, "the free way in is named, not just the refusal"


def test_the_refusal_names_a_date_rather_than_a_duration(tmp_path: Path) -> None:
    """A month away is not a number to do arithmetic on. "Back on 1 September" is
    something somebody can plan around; "in 30 days" is a shrug."""
    lib, store = capped(tmp_path, month=1.0)
    who = person(store, "reader@example.invalid")
    lib.claim(job(lib, 1.0, id="a", owner=who))

    refused = lib.claim(job(lib, 1.0, id="b", owner=who))
    assert "Back on" in refused
    assert "hours" not in refused


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
        account_budget=None,
        month_budget=10.0,
    )
    boss = person(store, "boss@example.invalid", admin=True)

    assert lib.claim(job(lib, 4.0, id="a", owner=boss, admin=True)) == ""
    refused = lib.claim(job(lib, 4.0, id="b", owner=boss, admin=True))
    assert refused and "targum is at its limit" in refused


def test_one_readers_spending_does_not_count_against_another(tmp_path: Path) -> None:
    lib, store = capped(tmp_path)
    one = person(store, "one@example.invalid")
    two = person(store, "two@example.invalid")

    assert lib.claim(job(lib, 9.0, id="a", owner=one)) == ""
    assert lib.claim(job(lib, 9.0, id="b", owner=two)) == "", "two people, two allowances"


def test_buying_a_chapter_is_refused_once_the_month_is_spent(tmp_path: Path) -> None:
    """Chapters cannot go through `claim` — pricing one means running Stanza inside the
    request a reader is waiting on — so they were going through nothing at all, and the
    reader prefetches the next chapter at 60% of this one. A cap that does not apply to
    the way a book is actually bought is not a cap."""
    lib, store = capped(tmp_path)
    who = person(store, "reader@example.invalid")

    chapter = job(lib, 0.0, id="ch", owner=who)
    assert lib.already_over(chapter) == "", "with nothing spent, nothing is in the way"

    lib.claim(job(lib, 10.0, id="a", owner=who))
    assert "this month" in lib.already_over(chapter)


def test_an_admin_buying_a_chapter_is_never_in_the_way(tmp_path: Path) -> None:
    lib, store = capped(tmp_path)
    boss = person(store, "boss@example.invalid", admin=True)
    lib.claim(job(lib, 50.0, id="a", owner=boss, admin=True))

    assert lib.already_over(job(lib, 0.0, id="ch", owner=boss, admin=True)) == ""
