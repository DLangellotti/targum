"""A recording stopped part way is credited to its retry (targum-internal#694; David,
2026-11-13: "credit the retry").

A stopped build is charged for the minutes it heard. Starting it again hears them from
the cache, so the new build's claim takes only the minutes not already paid for by the
reader's stopped attempts at the same source: summed across every stopped attempt since
the last build that went ahead, never below nothing, never another reader's or another
source's, never twice. It is the claim's own `length`, taken in `Store.claim`'s one
transaction: there is no second counter.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

import pytest

from targum.accounts import Store
from targum.serve import Job, Library
from targum.usage import Usage

LONG = 47 * 60.0  # David's 47-minute French video
SOURCE = "https://example.com/film"


def _person(store: Store, email: str) -> Any:
    person, _ = store.finish_sign_in(store.start_sign_in(email))  # type: ignore[misc]
    return person


def _length(store: Store, job_id: str) -> float:
    row = store.db.execute("SELECT length FROM job WHERE id = ?", (job_id,)).fetchone()
    return float(row["length"])


class World:
    def __init__(self, tmp_path: Path) -> None:
        self.store = Store(tmp_path / "db")
        self.library = Library(tmp_path / "out", store=self.store)
        self.made = 1_000

    def build(self, job_id: str, person: Any, source: str = SOURCE, seconds: float = LONG) -> Job:
        """A recording, priced and pressed: claimed, in the line."""
        self.made += 1_000
        job = Job(
            id=job_id,
            source=source,
            title="Un film",
            owner=person.id,
            home=self.library.home(person),
            audio=True,
            seconds=seconds,
            estimate=0.40,
            made=self.made,
        )
        self.library.jobs[job.id] = job
        self.library.remember(job)
        assert self.library.press(job) == "", job.blocked
        return job

    def stop(self, job: Job, heard: float) -> None:
        """Stopped while running, having heard `heard` seconds: `_stopped`'s receipt."""
        self.library._take(job)
        job.stage = "working"

        class Built:
            spent = Usage()

        Built.spent.add_seconds("openai/whisper-1", heard)
        self.library._stopped(job, Built())  # type: ignore[arg-type]

    def finish(self, job: Job) -> None:
        """Went ahead and was settled, as `run` settles a build."""
        job.stage = "done"
        job.spent = 0.05
        self.library.settle(job)
        self.library.remember(job)

    def used(self, person: Any) -> float:
        return self.store.hours_used(person.id, 0)


@pytest.fixture
def world(tmp_path: Path) -> World:
    return World(tmp_path)


def test_a_retry_claims_only_the_minutes_not_already_paid_for(world: World) -> None:
    reader = _person(world.store, "reader@example.com")
    first = world.build("a", reader)
    world.stop(first, heard=120.0)
    assert _length(world.store, "a") == pytest.approx(120.0)

    world.build("b", reader)

    assert _length(world.store, "b") == pytest.approx(LONG - 120.0)
    assert world.used(reader) == pytest.approx(LONG), "47 minutes paid once, in all"


def test_every_stopped_attempt_counts_once(world: World) -> None:
    """Stopped, retried and stopped again: the third pays for what neither heard."""
    reader = _person(world.store, "reader@example.com")
    world.stop(world.build("a", reader), heard=120.0)
    second = world.build("b", reader)
    assert _length(world.store, "b") == pytest.approx(LONG - 120.0)
    world.stop(second, heard=300.0)
    third = world.build("c", reader)
    assert _length(world.store, "c") == pytest.approx(LONG - 420.0)
    world.finish(third)
    assert world.used(reader) == pytest.approx(LONG)


def test_a_credit_is_never_taken_twice(world: World) -> None:
    """Once a retry went ahead it used the credit. A later build of the same source is
    a new build, paid in full."""
    reader = _person(world.store, "reader@example.com")
    world.stop(world.build("a", reader), heard=120.0)
    world.finish(world.build("b", reader))
    world.build("c", reader)
    assert _length(world.store, "c") == pytest.approx(LONG)


def test_two_retries_pressed_together_share_one_credit(world: World) -> None:
    reader = _person(world.store, "reader@example.com")
    world.stop(world.build("a", reader), heard=120.0)
    jobs = []
    for job_id in ("b", "c"):
        world.made += 1_000
        job = Job(
            id=job_id,
            source=SOURCE,
            owner=reader.id,
            home=world.library.home(reader),
            audio=True,
            seconds=LONG,
            estimate=0.40,
            made=world.made,
        )
        world.library.jobs[job.id] = job
        world.library.remember(job)
        jobs.append(job)
    gate = threading.Barrier(2)

    def press(job: Job) -> None:
        gate.wait()
        world.library.press(job)

    threads = [threading.Thread(target=press, args=(job,)) for job in jobs]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    lengths = sorted(_length(world.store, job.id) for job in jobs)
    assert lengths == [pytest.approx(LONG - 120.0), pytest.approx(LONG)], lengths


def test_never_below_nothing(world: World) -> None:
    reader = _person(world.store, "reader@example.com")
    world.stop(world.build("a", reader), heard=2000.0)
    world.stop(world.build("b", reader), heard=1500.0)
    again = world.build("c", reader)
    assert _length(world.store, "c") == 0.0
    assert again.stage == "queued"


def test_another_reader_s_minutes_are_never_credited(world: World) -> None:
    reader = _person(world.store, "reader@example.com")
    stranger = _person(world.store, "stranger@example.com")
    world.stop(world.build("a", stranger), heard=600.0)
    world.build("b", reader)
    assert _length(world.store, "b") == pytest.approx(LONG)


def test_another_source_s_minutes_are_never_credited(world: World) -> None:
    reader = _person(world.store, "reader@example.com")
    world.stop(world.build("a", reader, source="https://example.com/other"), heard=600.0)
    world.build("b", reader)
    assert _length(world.store, "b") == pytest.approx(LONG)


def test_a_waiting_cancel_credits_nothing(world: World) -> None:
    """A build cancelled before it started heard nothing and was charged nothing."""
    reader = _person(world.store, "reader@example.com")
    waiting = world.build("a", reader)
    assert world.library.cancel(waiting) == "cancelled"
    world.build("b", reader)
    assert _length(world.store, "b") == pytest.approx(LONG)


def test_a_retry_that_hears_less_than_was_paid_for_refunds_nothing(world: World) -> None:
    reader = _person(world.store, "reader@example.com")
    first = world.build("a", reader)
    world.stop(first, heard=120.0)
    retry = world.build("b", reader)
    claimed = _length(world.store, "b")
    world.finish(retry)  # it heard nothing new: every part came from the cache
    assert _length(world.store, "b") == pytest.approx(claimed), "settled at its claim"
    assert _length(world.store, "a") == pytest.approx(120.0), "the stopped receipt stands"
    assert world.used(reader) == pytest.approx(LONG)


def test_a_credited_retry_stopped_again_is_charged_no_more_than_it_claimed(
    world: World,
) -> None:
    reader = _person(world.store, "reader@example.com")
    world.stop(world.build("a", reader), heard=2700.0)
    retry = world.build("b", reader)
    assert _length(world.store, "b") == pytest.approx(LONG - 2700.0)
    world.stop(retry, heard=1000.0)
    assert _length(world.store, "b") == pytest.approx(LONG - 2700.0)
    assert world.used(reader) == pytest.approx(LONG), "never more than the whole recording"


def test_a_credit_that_makes_room_lets_the_retry_through(world: World) -> None:
    """The month's allowance is checked against what the retry claims, not the whole."""
    world.library.upload_seconds = LONG + 60.0
    reader = _person(world.store, "reader@example.com")
    world.stop(world.build("a", reader), heard=LONG - 60.0)
    again = world.build("b", reader)
    assert again.stage == "queued" and _length(world.store, "b") == pytest.approx(60.0)


# -- qa-claude on #1200 ----------------------------------------------------------------


def _quote(world: World, job_id: str, person: Any, made: int) -> Job:
    """A quote opened at `made` and not pressed yet: a paste in another tab."""
    job = Job(
        id=job_id,
        source=SOURCE,
        owner=person.id,
        home=world.library.home(person),
        audio=True,
        seconds=LONG,
        estimate=0.40,
        made=made,
    )
    world.library.jobs[job.id] = job
    world.library.remember(job)
    return job


def test_a_quote_opened_before_the_stop_and_pressed_after_frees_no_second_credit(
    world: World,
) -> None:
    """A quote's `made` is when it was opened, not pressed: the credit is decided by
    which claim took it, not by when anything was made."""
    reader = _person(world.store, "reader@example.com")
    old = _quote(world, "old", reader, made=1_500)
    world.stop(world.build("a", reader), heard=120.0)
    assert world.library.press(old) == ""
    assert _length(world.store, "old") == pytest.approx(LONG - 120.0)
    world.finish(old)
    world.build("d", reader)
    assert _length(world.store, "d") == pytest.approx(LONG)


def test_a_retry_that_finished_for_nothing_still_used_the_credit(world: World) -> None:
    """Every part came from the cache, so it settled at $0: it went ahead all the same."""
    reader = _person(world.store, "reader@example.com")
    world.stop(world.build("a", reader), heard=120.0)
    retry = world.build("b", reader)
    retry.stage = "done"
    retry.spent = 0.0
    world.library.settle(retry)
    world.library.remember(retry)
    world.build("c", reader)
    assert _length(world.store, "c") == pytest.approx(LONG)


def test_a_fully_credited_retry_that_went_ahead_used_it(world: World) -> None:
    reader = _person(world.store, "reader@example.com")
    world.stop(world.build("a", reader), heard=LONG)
    retry = world.build("b", reader)
    assert _length(world.store, "b") == 0.0
    retry.spent = 0.0
    world.finish(retry)
    world.build("c", reader)
    assert _length(world.store, "c") == pytest.approx(LONG)


def test_a_credited_retry_given_back_gives_its_credit_back(world: World) -> None:
    """Cancelled while it waited, failed with nothing spent, or lost to a restart: it
    never went ahead, so the stopped seconds are the reader's again."""
    reader = _person(world.store, "reader@example.com")
    world.stop(world.build("a", reader), heard=120.0)
    waiting = world.build("b", reader)
    assert world.library.cancel(waiting) == "cancelled"
    failed = world.build("c", reader)
    assert _length(world.store, "c") == pytest.approx(LONG - 120.0)
    world.library.release(failed)
    restarted = world.build("d", reader)
    assert _length(world.store, "d") == pytest.approx(LONG - 120.0)
    restarted.stage = "working"
    world.library.remember(restarted)
    world.store.interrupt_running()
    world.build("e", reader)
    assert _length(world.store, "e") == pytest.approx(LONG - 120.0)


# -- qa-claude on #1217 ----------------------------------------------------------------


def test_a_free_reader_s_press_on_a_retry_says_what_its_quote_said(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The quote took the stopped build's credit off what a retry needs; the press said
    the whole length. A free reader is told the same need at both (targum-internal#715)."""
    from targum.accounts import now

    monkeypatch.setenv("TARGUM_PLANS", "1")
    world.made = now()  # this month, where the month's credits are counted
    reader = _person(world.store, "reader@example.com")
    world.stop(world.build("a", reader, seconds=50 * 60.0), heard=45 * 60.0)
    world.build("other", reader, source="https://example.com/other", seconds=12 * 60.0)

    quote = _quote(world, "b", reader, made=now())
    quote.seconds, quote.stage = 50 * 60.0, "ready"
    world.library.short_of_month(quote)
    said = str(quote.blocked)
    assert said.startswith("It needs 5 credits and you have 3 left this month."), said

    quote.stage, quote.blocked = "ready", ""
    assert str(world.library.claim(quote)) == said
