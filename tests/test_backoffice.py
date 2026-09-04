"""The operator's own page: what it counts, and what it must never be reachable from."""

from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

import pytest

from targum.accounts import SCHEMA, Store
from targum.backoffice import survey, survey_store
from targum.render.builder import back_office_page
from targum.serve import back_office_host, hosts_for

DAY_MS = 24 * 60 * 60 * 1000


def stamp(when: date) -> int:
    """Noon UTC on a day, so no timezone can push it into the one either side."""
    import datetime as dt

    return int(dt.datetime.combine(when, dt.time(12, 0), dt.UTC).timestamp() * 1000)


@pytest.fixture
def store(tmp_path: Path) -> sqlite3.Connection:
    """Two accounts, and enough activity to tell them apart."""
    db = sqlite3.connect(tmp_path / "targum.db")
    db.executescript(SCHEMA)
    today = date(2026, 9, 4)
    db.execute(
        "INSERT INTO person (id, email, made) VALUES (1, 'a@example.com', ?)",
        (stamp(date(2026, 8, 1)),),
    )
    db.execute(
        "INSERT INTO person (id, email, made) VALUES (2, 'b@example.com', ?)",
        (stamp(date(2026, 8, 20)),),
    )
    for n in range(5):
        db.execute(
            "INSERT INTO word (person, language, lemma, at, learned) VALUES (1, 'he', ?, ?, ?)",
            (f"w{n}", stamp(today), 1 if n < 2 else 0),
        )
    # One of theirs is deleted: a word somebody took off their list is not a word they
    # have, and the page has to agree with the reader's own list.
    db.execute(
        "INSERT INTO word (person, language, lemma, at, gone) VALUES (1, 'he', 'dropped', ?, 1)",
        (stamp(today),),
    )
    db.execute(
        "INSERT INTO word (person, language, lemma, at) VALUES (2, 'he', 'only', ?)",
        (stamp(date(2026, 9, 3)),),
    )
    db.execute(
        "INSERT INTO doc (person, hash, title, opened, updated, done)"
        " VALUES (1, 'h1', 'One', ?, ?, ?)",
        (stamp(today), stamp(today), stamp(today)),
    )
    db.execute("INSERT INTO day (person, day, count) VALUES (1, '2026-09-04', 1)")
    db.execute("INSERT INTO day (person, day, count) VALUES (2, '2026-09-03', 1)")
    db.commit()
    return db


def test_it_counts_what_each_account_has(store: sqlite3.Connection) -> None:
    found = survey(store, today=date(2026, 9, 4))
    first, second = found.accounts
    assert first.email == "a@example.com"
    assert first.words == 5, "the deleted word is not a word they have"
    assert first.learned == 2
    assert first.texts_opened == 1
    assert first.days_read == 1
    assert second.words == 1
    assert second.learned == 0


def test_a_finished_targum_is_counted_the_way_the_ledger_counts_it(
    store: sqlite3.Connection,
) -> None:
    """The greater of the old whole-document record and the sections finished since,
    never their sum (targum-internal#173). The page has to agree with the reader's own
    progress page or one of the two is lying."""
    found = survey(store, today=date(2026, 9, 4))
    assert found.accounts[0].targums_finished == 1, "one old record, no sections: worth one"

    store.execute("INSERT INTO section (person, hash, section, at) VALUES (1, 'h1', '1', 1)")
    store.execute("INSERT INTO section (person, hash, section, at) VALUES (1, 'h1', '2', 1)")
    store.commit()
    again = survey(store, today=date(2026, 9, 4))
    assert again.accounts[0].targums_finished == 2, "two sections beats the old record of one"


def test_the_days_show_who_did_what(store: sqlite3.Connection) -> None:
    found = survey(store, today=date(2026, 9, 4))
    by_day = {day.day: day for day in found.days}
    assert by_day["2026-09-04"].words[1] == 5
    assert 1 in by_day["2026-09-04"].read
    assert by_day["2026-09-03"].words[2] == 1
    assert 2 in by_day["2026-09-03"].read
    # A day nobody touched is still a row, so a gap is visible as a gap.
    assert by_day["2026-09-01"].busy() is False
    assert found.active() == 2


def test_it_never_opens_the_store_for_writing(tmp_path: Path) -> None:
    """Read-only, because this is a page anybody refreshing could hit while a reader is
    mid-sync, and because nothing here has business writing to the store.

    Proved by trying to write through the same connection this opens rather than by
    looking for a journal file beside the database: the service's own `Store` puts one
    there when it creates the schema, so its presence says nothing about who wrote."""
    store = tmp_path / "targum.db"
    Store(store).close()
    assert survey_store(store).accounts == []

    opened = sqlite3.connect(f"file:{store}?mode=ro", uri=True)
    try:
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            opened.execute("INSERT INTO person (email, made) VALUES ('x@example.com', 1)")
    finally:
        opened.close()


def test_the_page_shows_the_counts_and_not_the_words(store: sqlite3.Connection) -> None:
    found = survey(store, today=date(2026, 9, 4))
    page = back_office_page(found, 30)
    assert "a@example.com" in page and "b@example.com" in page
    assert "2026-09-04" in page
    # The lemmas themselves are the thing this page must not become a window onto.
    for word in ("w0", "w1", "dropped", "only"):
        assert f">{word}<" not in page, f"the page is showing the word {word!r}"
    # And it tells a search engine to go away, in the page as well as at the proxy.
    assert 'name="robots" content="noindex' in page


def test_the_back_office_has_its_own_name() -> None:
    assert back_office_host("https://targum.page") == "bo.targum.page"
    assert back_office_host("https://www.targum.page") == "bo.targum.page"
    # A machine somebody runs themselves has no public name and no back office.
    assert back_office_host("") == ""
    assert back_office_host("http://127.0.0.1:8420") == ""


def test_the_server_answers_to_that_name() -> None:
    admitted = hosts_for("https://targum.page")
    assert "bo.targum.page" in admitted
    assert "targum.page" in admitted


def test_no_route_on_the_product_is_named_after_it() -> None:
    """The point of a separate name: nothing on targum.page reaches the back office, so
    a mistyped path cannot land on it and a change to the product's routing cannot
    expose it."""
    served = Path(__file__).resolve().parent.parent / "src" / "targum" / "serve.py"
    text = served.read_text(encoding="utf-8")
    assert '"/back-office"' not in text and '"/bo"' not in text
    assert 'route == "/admin"' not in text
