"""What a build cost, from the API's numbers rather than the estimate.

An estimate can refuse a build before it runs. It cannot say what a week of reading
cost and it cannot be reconciled against a bill, which is the difference between a
spending limit and a guess with a limit written on it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from targum.accounts import Store, now
from targum.serve import Job, Library
from targum.usage import Usage


def test_tokens_add_up_across_calls_and_models() -> None:
    spent = Usage()
    for _ in range(3):
        spent.add("claude-sonnet-5", 1000, 500)
    spent.add("claude-haiku-4-5", 200, 100)

    assert spent.calls == 4
    assert spent.input_tokens == 3200
    assert spent.output_tokens == 1600
    # Priced per model, because a build can span two and an average is a price for
    # neither: 3000 in and 1500 out on Sonnet, 200 and 100 on Haiku.
    expected = (3000 * 3.0 + 1500 * 15.0) / 1e6 + (200 * 1.0 + 100 * 5.0) / 1e6
    assert abs(spent.cost() - expected) < 1e-9


def test_an_unpriced_model_costs_nothing_rather_than_a_guess() -> None:
    """An unknown price is not zero. Pretending to know it is worse than counting."""
    spent = Usage()
    spent.add("some-model-shipped-after-this-code", 1_000_000, 1_000_000)
    assert spent.cost() == 0.0
    assert spent.input_tokens == 1_000_000, "still counted"


def test_two_usages_can_be_added() -> None:
    """Translation and word meanings run on separate providers and must total."""
    translating, glossing = Usage(), Usage()
    translating.add("claude-sonnet-5", 1000, 1000)
    glossing.add("claude-sonnet-5", 500, 200)
    both = translating + glossing

    assert both.calls == 2
    assert both.by_model["claude-sonnet-5"] == (1500, 1200)
    # And neither original was changed by the addition.
    assert translating.by_model["claude-sonnet-5"] == (1000, 1000)


def test_the_provider_counts_what_it_is_charged_for(monkeypatch: Any) -> None:
    from targum.models import Segment, Style
    from targum.translate.anthropic_provider import AnthropicProvider, _Batch, _Line

    segments = [
        Segment(id=f"s{i}", block_id="b", block_index=0, index=i, text="שלום") for i in range(4)
    ]
    provider = AnthropicProvider(batch_size=2)

    def parse(**kwargs: object) -> object:
        body = str(kwargs.get("messages"))
        asked = [s for s in segments if s.id in body]
        return type(
            "R",
            (),
            {
                "stop_reason": "end_turn",
                "parsed_output": _Batch(segments=[_Line(id=s.id, text="peace") for s in asked]),
                "usage": type("U", (), {"input_tokens": 120, "output_tokens": 80})(),
            },
        )()

    class Client:
        messages = type("M", (), {"parse": staticmethod(parse)})()

    provider._client = Client()
    provider.translate(segments, "he", "en", Style.natural)

    assert provider.spent.calls == 2, "two batches of two"
    assert provider.spent.input_tokens == 240
    assert provider.spent.output_tokens == 160
    assert provider.spent.cost() > 0


def test_the_ledger_holds_the_receipt_not_the_estimate(tmp_path: Path) -> None:
    store = Store(tmp_path / "targum.db")
    library = Library(
        tmp_path / "out", max_cost=10.0, budget=10.0, store=store, account_budget=None
    )

    job = Job(id="j1", source="memory:x", estimate=4.0, home=library.out / "local")
    library.jobs[job.id] = job
    library.remember(job)
    assert library.claim(job) == ""
    assert library.committed == 4.0, "the reservation is the estimate"

    # The API says what it really was.
    job.spent = 1.25
    library.settle(job)
    assert library.committed == 1.25, "the budget should hold the receipt"
    assert library.remaining() == 8.75

    after = Library(
        tmp_path / "out", max_cost=10.0, budget=10.0, store=Store(tmp_path / "targum.db")
    )
    assert after.committed == 1.25
    assert after.jobs["j1"].spent == 1.25


def test_a_build_that_failed_part_way_keeps_what_it_spent(tmp_path: Path) -> None:
    """It paid for the batches it got through, and the API said how much."""
    store = Store(tmp_path / "targum.db")
    library = Library(
        tmp_path / "out", max_cost=10.0, budget=10.0, store=store, account_budget=None
    )

    job = Job(id="j1", source="memory:x", estimate=5.0, home=library.out / "local")
    library.jobs[job.id] = job
    library.remember(job)
    library.claim(job)
    job.spent = 0.80
    library._blame(job, "something went wrong")

    assert library.committed == 0.80, "the money it did spend must not go back"
    assert job.stage == "failed"


def test_a_build_that_spent_nothing_gives_it_all_back(tmp_path: Path) -> None:
    store = Store(tmp_path / "targum.db")
    library = Library(
        tmp_path / "out", max_cost=10.0, budget=10.0, store=store, account_budget=None
    )

    job = Job(id="j1", source="memory:x", estimate=5.0, home=library.out / "local")
    library.jobs[job.id] = job
    library.remember(job)
    library.claim(job)
    library._blame(job, "refused before it started")

    assert library.committed == 0.0


# --- two ceilings, because they stop different things -------------------------


def per_person(tmp_path: Path, account: float, box: float) -> Library:
    return Library(
        tmp_path / "out",
        max_cost=100.0,
        budget=box,
        store=Store(tmp_path / "targum.db"),
        account_budget=account,
    )


def owned(library: Library, who: int | None, estimate: float, ident: str) -> Job:
    job = Job(
        id=ident,
        source="memory:x",
        estimate=estimate,
        owner=who,
        home=library.out / "local",
    )
    library.jobs[ident] = job
    library.remember(job)
    return job


def test_one_reader_running_away_does_not_stop_another(tmp_path: Path) -> None:
    library = per_person(tmp_path, account=3.0, box=100.0)

    assert library.claim(owned(library, 1, 2.5, "a1")) == ""
    refused = library.claim(owned(library, 1, 2.5, "a2"))
    assert refused, "the same reader should hit their own ceiling"
    assert "at once" in refused

    # Somebody else is unaffected: it is a rail per reader, not a shared tap.
    assert library.claim(owned(library, 2, 2.5, "b1")) == ""


def test_the_box_has_a_ceiling_no_per_account_limit_could_give_it(tmp_path: Path) -> None:
    """Ten readers each inside their own budget can still empty the card."""
    library = per_person(tmp_path, account=3.0, box=5.0)

    assert library.claim(owned(library, 1, 2.5, "a")) == ""
    assert library.claim(owned(library, 2, 2.5, "b")) == ""
    refused = library.claim(owned(library, 3, 2.5, "c"))
    assert refused, "a third reader, inside their own limit, should still be stopped"
    assert "at its limit" in refused


def test_a_refusal_says_which_limit_and_when_it_lifts(tmp_path: Path) -> None:
    """A refusal that names neither is indistinguishable from the product being broken."""
    from targum.serve import BUDGET_HOURS

    library = per_person(tmp_path, account=1.0, box=100.0)
    library.claim(owned(library, 1, 1.0, "a"))
    refused = library.claim(owned(library, 1, 1.0, "b"))

    assert str(BUDGET_HOURS) in refused, "it must say when it lifts"
    assert "library" in refused, "and what is still free meanwhile"
    assert "$" not in refused, "the reader pays by the month, never by the text"


def test_every_column_the_code_names_exists_after_opening_an_old_file(tmp_path: Path) -> None:
    """The check that would have caught a migration that was added but never ran.

    Version-gated migrations let the stamp advance past a step that never happened, and
    the file is then marked migrated while missing a column. This asserts the shape
    rather than the bookkeeping.
    """
    import sqlite3

    from targum.accounts import Store

    path = tmp_path / "old.db"
    raw = sqlite3.connect(path)
    raw.executescript(
        "CREATE TABLE person (id INTEGER PRIMARY KEY, email TEXT NOT NULL UNIQUE,"
        " made INTEGER NOT NULL, revision INTEGER NOT NULL DEFAULT 0);"
        "CREATE TABLE job (id TEXT PRIMARY KEY, owner INTEGER, home TEXT NOT NULL,"
        " source TEXT NOT NULL, options TEXT NOT NULL DEFAULT '{}',"
        " stage TEXT NOT NULL DEFAULT 'reading', title TEXT NOT NULL DEFAULT '',"
        " language TEXT NOT NULL DEFAULT '', segments INTEGER NOT NULL DEFAULT 0,"
        " estimate REAL NOT NULL DEFAULT 0, done INTEGER NOT NULL DEFAULT 0,"
        " total INTEGER NOT NULL DEFAULT 0, message TEXT NOT NULL DEFAULT '',"
        " error TEXT NOT NULL DEFAULT '', reader TEXT NOT NULL DEFAULT '',"
        " lemmas INTEGER NOT NULL DEFAULT 0, meanings REAL NOT NULL DEFAULT 0,"
        " blocked TEXT NOT NULL DEFAULT '', claimed REAL NOT NULL DEFAULT 0,"
        " made INTEGER NOT NULL DEFAULT 0);"
        "PRAGMA user_version = 3;"  # stamped as current, and it is not
    )
    raw.commit()
    raw.close()

    store = Store(path)
    columns = {row[1] for row in store.db.execute("PRAGMA table_info(person)")}
    assert "leaving" in columns
    columns = {row[1] for row in store.db.execute("PRAGMA table_info(job)")}
    assert "spent" in columns

    # And the queries that name them work.
    assert store.purge() == []
    assert store.committed(0) == 0.0
    store.save_job({"id": "j", "home": "/x", "source": "s", "made": 1})
    store.settle("j", 1.5)
    assert store.committed(0) == 1.5


# -- the ledger, read back ------------------------------------------------------


def test_an_admin_is_invited_by_being_made_one(tmp_path: Path) -> None:
    """An admin who cannot sign in is not an admin, and having to say it twice is a way
    of getting it half done."""
    from targum.accounts import Store

    store = Store(tmp_path / "targum.db")
    store.make_admin("boss@example.invalid")

    assert store.is_admin("boss@example.invalid")
    assert store.may_join("boss@example.invalid"), "made an admin, still could not get in"


def test_taking_admin_away_leaves_the_invitation(tmp_path: Path) -> None:
    """Two different statements: whether somebody may be here, and whether the spend
    rails apply to them. Undoing the second must not quietly undo the first."""
    from targum.accounts import Store

    store = Store(tmp_path / "targum.db")
    store.make_admin("boss@example.invalid")

    assert store.unadmin("boss@example.invalid") is True
    assert store.is_admin("boss@example.invalid") is False
    assert store.may_join("boss@example.invalid"), "the invitation went with the admin flag"


def test_admin_survives_being_uninvited(tmp_path: Path) -> None:
    """`uninvite` deliberately leaves an existing account alone, which is why admin is a
    table of its own rather than a column on the guest list."""
    from targum.accounts import Store

    store = Store(tmp_path / "targum.db")
    store.make_admin("boss@example.invalid")
    store.uninvite("boss@example.invalid")

    assert store.is_admin("boss@example.invalid")


def test_a_person_carries_whether_the_rails_apply(tmp_path: Path) -> None:
    from targum.accounts import Store

    store = Store(tmp_path / "targum.db")
    store.make_admin("boss@example.invalid")
    store.invite("reader@example.invalid")

    boss = store.finish_sign_in(store.start_sign_in("boss@example.invalid"))
    reader = store.finish_sign_in(store.start_sign_in("reader@example.invalid"))

    assert boss is not None and boss[0].admin is True
    assert reader is not None and reader[0].admin is False

    # And the same again from a session cookie, which is how every later request asks.
    assert store.whoever(boss[1]) is not None
    assert store.whoever(boss[1]).admin is True  # type: ignore[union-attr]


def test_the_ledger_says_what_was_charged_and_what_is_held(tmp_path: Path) -> None:
    """Two different facts. `spent` is what the API really charged, which reconciles
    against an invoice. `claimed` is what the ceilings count — the same figure once a
    build settles, its estimate while one runs, nothing for one that handed it back."""
    from targum.accounts import Store, now

    store = Store(tmp_path / "targum.db")
    store.invite("reader@example.invalid")
    store.start_sign_in("reader@example.invalid")
    who = store.db.execute(
        "SELECT id FROM person WHERE email = ?", ("reader@example.invalid",)
    ).fetchone()["id"]

    store.save_job({"id": "settled", "owner": who, "home": "/tmp", "source": "x", "made": now()})
    store.settle("settled", 1.25)
    store.save_job(
        {
            "id": "running",
            "owner": who,
            "home": "/tmp",
            "source": "x",
            "made": now(),
            "claimed": 2.0,
        }
    )

    rows = store.spending(0)
    assert len(rows) == 1
    assert rows[0]["email"] == "reader@example.invalid"
    assert rows[0]["jobs"] == 2
    assert rows[0]["spent"] == pytest.approx(1.25), "only the settled build has really cost"
    assert rows[0]["claimed"] == pytest.approx(3.25), "the running one is held against the cap"


def test_work_with_no_account_behind_it_still_counts(tmp_path: Path) -> None:
    """Built before there were accounts, or by somebody since forgotten. The money was
    real either way, and a total that quietly drops it is wrong about the bill."""
    from targum.accounts import Store, now

    store = Store(tmp_path / "targum.db")
    store.save_job({"id": "orphan", "owner": None, "home": "/tmp", "source": "x", "made": now()})
    store.settle("orphan", 0.75)

    rows = store.spending(0)
    assert len(rows) == 1
    assert rows[0]["email"] is None
    assert rows[0]["spent"] == pytest.approx(0.75)


def test_the_ledger_keeps_to_its_window(tmp_path: Path) -> None:
    from targum.accounts import Store, now

    store = Store(tmp_path / "targum.db")
    old = now() - 60 * 24 * 60 * 60 * 1000
    store.save_job({"id": "old", "owner": None, "home": "/tmp", "source": "x", "made": old})
    store.settle("old", 5.0)

    assert store.spending(0)[0]["spent"] == pytest.approx(5.0)
    assert store.spending(now() - 24 * 60 * 60 * 1000) == []


# -- the upload allowance, which is the one limit a reader is told about ------


def with_hours(tmp_path: Path, hours: float) -> Library:
    """A library whose money rails are wide open, so only the clock can refuse."""
    from targum.serve import Library as _Library

    return _Library(
        tmp_path / "out",
        max_cost=1000.0,
        budget=1000.0,
        store=Store(tmp_path / "targum.db"),
        account_budget=None,
        upload_seconds=hours * 60 * 60,
    )


def recording(library: Library, who: int | None, seconds: float, ident: str) -> Job:
    job = Job(
        id=ident,
        source="upload:talk.mp3",
        estimate=0.10,
        owner=who,
        home=library.out / "local",
        audio=True,
        seconds=seconds,
    )
    library.jobs[ident] = job
    library.remember(job)
    return job


HOUR = 60.0 * 60.0


def test_recordings_spend_the_hours_and_then_are_refused(tmp_path: Path) -> None:
    library = with_hours(tmp_path, hours=10)

    assert library.claim(recording(library, 1, 6 * HOUR, "a")) == ""
    assert library.claim(recording(library, 1, 3 * HOUR, "b")) == ""
    refused = library.claim(recording(library, 1, 2 * HOUR, "c"))
    assert refused, "eleven hours does not fit in ten"
    assert "10 hours" in refused


def test_the_hours_are_counted_per_reader(tmp_path: Path) -> None:
    """A rail per reader, not a shared tap — the same rule the money rails follow."""
    library = with_hours(tmp_path, hours=10)

    assert library.claim(recording(library, 1, 10 * HOUR, "a")) == ""
    assert library.claim(recording(library, 1, 1 * HOUR, "b")) != ""
    assert library.claim(recording(library, 2, 10 * HOUR, "c")) == ""


def test_a_text_upload_is_never_charged_hours(tmp_path: Path) -> None:
    """Text uploads are unlimited. Only the clock-priced work is metered by the clock."""
    library = with_hours(tmp_path, hours=10)

    library.claim(recording(library, 1, 10 * HOUR, "spent"))
    text = owned(library, 1, 5.0, "text")
    assert library.claim(text) == "", "a text upload passes on an exhausted hour budget"


def test_a_failed_recording_gives_its_hours_back(tmp_path: Path) -> None:
    """A build that transcribed nothing must not cost an hour the reader never heard."""
    library = with_hours(tmp_path, hours=10)

    library.claim(recording(library, 1, 10 * HOUR, "died"))
    library.store.unclaim("died")

    assert library.claim(recording(library, 1, 10 * HOUR, "again")) == ""


def test_the_hours_refusal_names_the_number_and_what_still_works(tmp_path: Path) -> None:
    """The one refusal the pricing page promised, so it says what that page said."""
    library = with_hours(tmp_path, hours=10)
    library.claim(recording(library, 1, 10 * HOUR, "a"))
    refused = library.claim(recording(library, 1, 1 * HOUR, "b"))

    assert "10 hours" in refused, "the number the page named"
    assert "library" in refused, "and what is still free"
    assert "Text uploads" in refused, "and that text is not affected"
    assert "$" not in refused, "never in money"


def test_the_hours_refusal_names_this_library_s_allowance(tmp_path: Path) -> None:
    """Not the module constant. A server given a different allowance must quote the one
    it actually enforces — the refusal and the rail were free to disagree while both
    happened to say ten, and the disagreement only surfaced when the constant moved."""
    library = with_hours(tmp_path, hours=3)
    library.claim(recording(library, 1, 3 * HOUR, "a"))
    refused = library.claim(recording(library, 1, 1 * HOUR, "b"))

    assert "3 hours" in refused, "the allowance this library was built with"
    from targum.serve import UPLOAD_HOURS

    assert f"{UPLOAD_HOURS} hours" not in refused, "never the constant it was not given"


def test_an_admin_is_not_held_to_the_hours(tmp_path: Path) -> None:
    library = with_hours(tmp_path, hours=1)
    job = recording(library, 1, 10 * HOUR, "a")
    job.admin = True
    assert library.claim(job) == ""


def test_no_refusal_ever_says_a_reader_has_read_their_fill(tmp_path: Path) -> None:
    """Nothing targum refuses is a limit on reading.

    Text uploads are unlimited and the library is free, so a refusal that implies the
    reader has used up an allowance of reading is describing a product that does not
    exist. The rate limit says it is a rate limit; the audio allowance names audio.
    """
    library = with_hours(tmp_path, hours=10)
    library.account_budget = 1.0
    library.claim(owned(library, 1, 1.0, "money"))
    rate = library.claim(owned(library, 1, 1.0, "money2"))

    library.claim(recording(library, 2, 10 * HOUR, "audio"))
    clock = library.claim(recording(library, 2, 1 * HOUR, "audio2"))

    for refusal in (rate, clock, library._out_of("everyone")):
        assert refusal
        assert "your fill" not in refusal
        assert "read" not in refusal.lower() or "library" in refusal


def test_a_reader_may_upload_text_all_month_without_a_ceiling(tmp_path: Path) -> None:
    """The rail whose removal is the feature.

    There was a monthly money cap here, and while it existed "unlimited text" was a
    sentence the server did not honour. Twenty long books inside one month, each one
    under the daily rate limit, must all go through.
    """
    library = with_hours(tmp_path, hours=10)
    library.account_budget = 10.0

    for n in range(20):
        assert library.claim(owned(library, 1, 9.0, f"book{n}")) == ""
        # Each lands on a different day, so only a monthly ceiling could refuse it.
        with library.store.write() as db:
            db.execute(
                "UPDATE job SET made = ? WHERE id = ?",
                (now() - (n + 1) * 25 * 60 * 60 * 1000, f"book{n}"),
            )

    assert not hasattr(library, "month_budget"), "no per-reader monthly ceiling exists"
