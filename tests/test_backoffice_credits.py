"""Credits in the back office (targum-internal#543).

Each account's month of credits against its allowance, with the model spend beside it;
one account's page by kind at `?who=<id>`; gifts counted as targum's, not the reader's;
and a search that ignores case in every script.
"""

from __future__ import annotations

import datetime as dt
from datetime import date
from pathlib import Path

import pytest

from targum.accounts import Store
from targum.backoffice import (
    ACCOUNT_SORTS,
    Listing,
    credits,
    month_from,
    reader,
    survey,
)
from targum.render.builder import back_office_page

TODAY = date(2026, 10, 27)
DAY_MS = 24 * 60 * 60 * 1000
SECRET_TITLE = "Шир ха-ширим, secret title"
SECRET_SOURCE = "https://private.example/their-own-recording.mp3"


def stamp(when: date) -> int:
    return int(dt.datetime.combine(when, dt.time(12, 0), dt.UTC).timestamp() * 1000)


def job(
    store: Store,
    id_: str,
    owner: int,
    made: date,
    *,
    kind: str = "build",
    length: float = 0.0,
    seconds: float = 0.0,
    spent: float = 0.0,
    gift: bool = False,
    stage: str = "done",
) -> None:
    """A job as the library leaves it: saved, then claimed, then settled."""
    store.save_job(
        {
            "id": id_,
            "owner": owner,
            "home": "h",
            "source": SECRET_SOURCE,
            "title": SECRET_TITLE,
            "options": '{"to": "en"}',
            "stage": stage,
            "kind": kind,
            "made": stamp(made),
            "seconds": seconds,
            "audio": int(bool(seconds)),
        }
    )
    assert store.claim(id_, 0.01, 100.0, 0, owner=owner, length=length, gift=gift) == ""
    store.settle(id_, spent)


@pytest.fixture
def store(tmp_path: Path) -> Store:
    """Two readers and an admin. Dina has a month of builds, a chat and a gift; Ruth one
    build last month; the admin one build this month."""
    store = Store(tmp_path / "targum.db")
    for who, email, name in (
        (1, "dina@example.com", "Дина"),
        (2, "ruth@example.com", "Ruth"),
        (3, "admin@example.com", ""),
    ):
        store.db.execute(
            "INSERT INTO person (id, email, name, made) VALUES (?, ?, ?, ?)",
            (who, email, name, stamp(date(2026, 9, 1))),
        )
    store.db.execute("INSERT INTO admin (email, at) VALUES ('admin@example.com', 1)")
    job(store, "b1", 1, date(2026, 10, 3), length=1200, seconds=1200, spent=0.40)
    job(store, "b2", 1, date(2026, 10, 20), length=600, seconds=600, spent=0.25)
    job(store, "c1", 1, date(2026, 10, 21), kind="chat", length=95, spent=0.02)
    job(store, "g1", 1, date(2026, 10, 22), seconds=900, spent=0.30, gift=True)
    job(store, "old", 1, date(2026, 9, 10), length=3000, seconds=3000, spent=1.00)
    job(store, "r1", 2, date(2026, 9, 28), length=300, seconds=300, spent=0.10)
    job(store, "a1", 3, date(2026, 10, 5), length=60, seconds=60, spent=0.05)
    return store


def test_a_claim_writes_whether_it_was_a_gift(store: Store) -> None:
    rows = dict(store.db.execute("SELECT id, gift FROM job").fetchall())
    assert rows["g1"] == 1 and rows["b1"] == 0
    assert store.db.execute("SELECT length FROM job WHERE id = 'g1'").fetchone()[0] == 0


def test_the_month_is_the_sum_the_allowance_is_held_to(store: Store) -> None:
    found = survey(store.db, today=TODAY, allowance=28800.0, plan_allowance=86400.0)
    by_email = {who.email: who for who in found.accounts}
    month = month_from(TODAY)
    for who in found.accounts:
        assert who.used == store.hours_used(who.id, month), who.email
    dina = by_email["dina@example.com"]
    assert dina.used == 1895.0, "builds and the chat; the gift and last month are not hers"
    assert dina.spent == pytest.approx(0.97), "the month's model spend, the gift's included"
    assert by_email["ruth@example.com"].used == 0.0
    assert dina.allowance == 28800.0
    assert by_email["admin@example.com"].allowance == 86400.0, "an admin is on Plan"

    page = back_office_page(found, 30)
    assert '<th class="n">Credits this month</th>' in page
    assert "32 of 480" in page and "$0.97" in page
    assert f'href="/back-office?who={dina.id}#people"' in page


def test_accounts_sort_by_the_months_credits(store: Store) -> None:
    assert "credits" in ACCOUNT_SORTS
    found = survey(store.db, today=TODAY, accounts=Listing(sort="credits"))
    assert [who.email for who in found.accounts] == [
        "dina@example.com",
        "admin@example.com",
        "ruth@example.com",
    ]


def test_a_readers_page_counts_by_kind_and_a_gift_as_targums(store: Store) -> None:
    one = reader(store.db, 1, today=TODAY, allowance=28800.0)
    assert one is not None
    month = {use.kind: use for use in one.month}
    ever = {use.kind: use for use in one.ever}
    assert [use.kind for use in one.month] == ["build", "subscription", "voice", "chat", "gift"]
    assert (month["build"].jobs, month["build"].seconds) == (2, 1800.0)
    assert ever["build"].jobs == 3 and ever["build"].seconds == 4800.0
    assert month["chat"].seconds == 95.0
    assert (month["gift"].jobs, month["gift"].seconds) == (1, 900.0), "counted at its quote"
    assert one.used == store.hours_used(1, month_from(TODAY)) == 1895.0
    assert [line.kind for line in one.recent][:2] == ["gift", "chat"], "newest first"

    page = back_office_page(survey(store.db, today=TODAY), 30, reader=one)
    panel = page[page.index('id="tab-people"') : page.index("<h2>Follow up")]
    assert "dina@example.com" in panel and "32 of 480 credits this month" in panel
    assert ">95 s<" in panel, "a conversation is counted in seconds"
    assert ">gift<" in panel and ">15<" in panel
    assert 'href="/back-office#people">Back to accounts' in panel


def test_a_readers_page_holds_no_title_and_no_source(store: Store) -> None:
    """Clause 3.14: counts and stages, never what they read or where it came from."""
    one = reader(store.db, 1, today=TODAY)
    page = back_office_page(survey(store.db, today=TODAY), 30, reader=one)
    for secret in (SECRET_TITLE, SECRET_SOURCE, "private.example", "secret title"):
        assert secret not in page
    assert not hasattr(one.recent[0], "title") and not hasattr(one.recent[0], "source")


def test_there_is_no_page_for_nobody_or_for_the_operator(store: Store) -> None:
    assert reader(store.db, 99, today=TODAY) is None
    assert reader(store.db, 2, today=TODAY, operators=["Ruth+test@example.com"]) is None


def test_a_gift_settles_none_of_its_seconds_on_the_month(tmp_path: Path) -> None:
    """A word said from its card is targum's (design.md §12): settling its seconds put
    them on the reader's month after the claim had kept them off."""
    from targum.serve import Job, Library

    store = Store(tmp_path / "words.db")
    person = store.finish_sign_in(store.start_sign_in("r@example.com"))[0]  # type: ignore[index]
    out = tmp_path / "out"
    out.mkdir()
    library = Library(out, store=store, budget=1.0)
    word = Job(
        id="say-w",
        source="word:he",
        estimate=0.001,
        seconds=2.0,
        kind="chat",
        owner=person.id,
        gift=True,
    )
    library.remember(word)
    assert library.claim_turn(word) == ""
    library.settle(word)
    assert store.hours_used(person.id, 0) == 0.0
    row = store.db.execute("SELECT gift, seconds FROM job WHERE id = 'say-w'").fetchone()
    assert tuple(row) == (1, 2.0)

    turn = Job(
        id="chat-1", source="chat:c", estimate=0.001, seconds=30.0, kind="chat", owner=person.id
    )
    library.remember(turn)
    assert library.claim_turn(turn) == ""
    library.settle(turn)
    assert store.hours_used(person.id, 0) == 30.0, "a turn of their own still counts"


def test_search_ignores_case_in_every_script(store: Store) -> None:
    """qa on targum#952: LIKE folds ASCII alone, so «дина» never found «Дина»."""
    found = survey(store.db, today=TODAY, accounts=Listing(q="дИНА", sort="joined"))
    assert [who.email for who in found.accounts] == ["dina@example.com"]
    store.db.execute(
        "INSERT INTO waiting (email, state, stop, asked) VALUES ('ЛЕВ@пример.рф', 'on', 's', 1)"
    )
    waiting = survey(
        store.db,
        today=TODAY,
        waitlist=Listing(q="лев@", sort="oldest"),
        let_in=Listing(q="лев@", sort="oldest"),
    )
    assert [who.email for who in waiting.waiting_list] == ["ЛЕВ@пример.рф"]


def test_credits_are_written_as_the_product_writes_them() -> None:
    assert credits(None) == "—"
    assert credits(1800) == "30"
    assert credits(95) == "1.6"
    assert credits(60) == "1"
    assert credits(0) == "0"
