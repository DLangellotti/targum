"""What a build cost, from the API's numbers rather than the estimate.

An estimate can refuse a build before it runs. It cannot say what a week of reading
cost and it cannot be reconciled against a bill, which is the difference between a
spending limit and a guess with a limit written on it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from targum.accounts import Store
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
    assert "for you" in refused

    # Somebody else is unaffected: it is a rail per reader, not a shared tap.
    assert library.claim(owned(library, 2, 2.5, "b1")) == ""


def test_the_box_has_a_ceiling_no_per_account_limit_could_give_it(tmp_path: Path) -> None:
    """Ten readers each inside their own budget can still empty the card."""
    library = per_person(tmp_path, account=3.0, box=5.0)

    assert library.claim(owned(library, 1, 2.5, "a")) == ""
    assert library.claim(owned(library, 2, 2.5, "b")) == ""
    refused = library.claim(owned(library, 3, 2.5, "c"))
    assert refused, "a third reader, inside their own limit, should still be stopped"
    assert "everyone" in refused


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
