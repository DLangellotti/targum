"""The back office as a place to decide who to write to (2026-10-15).

Follow up, each week's readers, and how far readers get — and the operator's own
addresses counted nowhere.
"""

from __future__ import annotations

import datetime as dt
import sqlite3
from datetime import date
from pathlib import Path

import pytest

from targum.accounts import SCHEMA, Store
from targum.backoffice import Survey, bare, operators_from_env, survey
from targum.render.builder import back_office_page

TODAY = date(2026, 10, 15)


def stamp(when: date) -> int:
    return int(dt.datetime.combine(when, dt.time(12, 0), dt.UTC).timestamp() * 1000)


def person(db: sqlite3.Connection, who: int, email: str, made: date) -> None:
    db.execute("INSERT INTO person (id, email, made) VALUES (?, ?, ?)", (who, email, stamp(made)))


def let_in(db: sqlite3.Connection, email: str, when: date) -> None:
    db.execute("INSERT INTO invited (email, at) VALUES (?, ?)", (email, stamp(when)))


def opened(db: sqlite3.Connection, who: int, doc: str, when: date) -> None:
    db.execute(
        "INSERT INTO doc (person, hash, opened, updated) VALUES (?, ?, ?, ?)",
        (who, doc, stamp(when), stamp(when)),
    )


def kept(db: sqlite3.Connection, who: int, lemma: str, when: date) -> None:
    db.execute(
        "INSERT INTO word (person, language, lemma, at) VALUES (?, 'he', ?, ?)",
        (who, lemma, stamp(when)),
    )


@pytest.fixture
def db(tmp_path: Path) -> sqlite3.Connection:
    """A small beta: a regular, a quiet one, one who looked once, one who never came,
    one let in yesterday, and the operator testing."""
    Store(tmp_path / "targum.db").close()
    db = sqlite3.connect(tmp_path / "targum.db")
    db.executescript(SCHEMA)
    monday = date(2026, 10, 5)
    # A regular: let in on the 5th, reading on three days.
    let_in(db, "regular@example.com", monday)
    person(db, 1, "regular@example.com", monday)
    opened(db, 1, "a", monday)
    opened(db, 1, "b", date(2026, 10, 8))
    kept(db, 1, "w1", date(2026, 10, 14))
    db.execute("INSERT INTO event (person, kind, day) VALUES (1, 'lookup', '2026-10-14')")
    # Quiet: read on the 6th and twice, not since.
    let_in(db, "quiet@example.com", monday)
    person(db, 2, "quiet@example.com", monday)
    opened(db, 2, "a", date(2026, 10, 6))
    opened(db, 2, "b", date(2026, 10, 7))
    kept(db, 2, "w2", date(2026, 10, 7))
    # Looked once: joined the 12th, opened one text, kept nothing.
    let_in(db, "once@example.com", date(2026, 10, 12))
    person(db, 3, "once@example.com", date(2026, 10, 12))
    opened(db, 3, "a", date(2026, 10, 12))
    # Never came: let in on the 12th, no account.
    let_in(db, "never@example.com", date(2026, 10, 12))
    # Yesterday: let in and read, too soon to say anything about.
    let_in(db, "new@example.com", date(2026, 10, 14))
    person(db, 4, "new@example.com", date(2026, 10, 14))
    opened(db, 4, "a", date(2026, 10, 14))
    # The operator, testing under a +tag, let in and reading.
    let_in(db, "Op.Erator+test2@gmail.com", date(2026, 10, 14))
    person(db, 5, "Op.Erator+test2@gmail.com", date(2026, 10, 14))
    opened(db, 5, "a", date(2026, 10, 14))
    db.execute(
        "INSERT INTO waiting (email, state, stop, asked, invited) VALUES (?, 'on', 's', 1, 1)",
        ("operator+test2@gmail.com",),
    )
    db.commit()
    return db


def found(db: sqlite3.Connection) -> Survey:
    return survey(db, today=TODAY, operators=["operator@gmail.com"])


def test_an_address_is_compared_without_its_tag_or_gmail_dots() -> None:
    assert bare("Op.Erator+test2@gmail.com") == "operator@gmail.com"
    assert bare("o.p+x@googlemail.com") == "op@gmail.com"
    # Dots matter everywhere else.
    assert bare("first.last+x@example.com") == "first.last@example.com"


def test_the_operators_come_from_the_box(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TARGUM_OPERATORS", "me@gmail.com, m.e+2@gmail.com other@example.com")
    assert operators_from_env() == {"me@gmail.com", "other@example.com"}


def test_the_operator_is_counted_nowhere(db: sqlite3.Connection) -> None:
    page = found(db)
    everywhere = [a.email for a in page.accounts] + [w.email for w in page.waiting_list]
    everywhere += [f.email for f in page.follow_up]
    assert not [each for each in everywhere if "erator" in each.lower()]
    assert page.readers == 4
    assert sum(week.let_in for week in page.batches) == 5
    assert not any(5 in day.opened for day in page.days)


def test_follow_up_names_who_to_write_to_and_why(db: sqlite3.Connection) -> None:
    rows = {row.email: row for row in found(db).follow_up}
    assert rows["never@example.com"].action == "resend"
    assert rows["never@example.com"].why == "Let in October 12, not signed in yet"
    assert rows["once@example.com"].action == "write"
    assert "opened 1 text and kept no words" in rows["once@example.com"].why
    assert rows["quiet@example.com"].why == "Last read October 7"
    # Reading this week, or let in too lately to judge.
    assert "regular@example.com" not in rows
    assert "new@example.com" not in rows
    # Oldest first.
    assert [row.email for row in found(db).follow_up][0] == "quiet@example.com"


def test_a_closing_account_is_not_followed_up(db: sqlite3.Connection) -> None:
    db.execute("UPDATE person SET leaving = 1 WHERE id = 2")
    assert "quiet@example.com" not in {row.email for row in found(db).follow_up}


def test_each_week_counts_only_who_has_had_the_chance(db: sqlite3.Connection) -> None:
    weeks = {week.week: week for week in found(db).batches}
    first = weeks["2026-10-05"]
    assert (first.let_in, first.signed_in, first.opened, first.kept) == (2, 2, 2, 2)
    assert (first.came_back, first.old_enough) == (2, 2)
    # Both opened a second text on a later day, and both read in their first week; the
    # fourth week has not ended for anybody.
    assert first.second_text == 2
    assert (first.week_one, first.week_one_over) == (2, 2)
    assert first.week_four_over == 0
    this = weeks["2026-10-12"]
    # never, once and new, but not the operator.
    assert (this.let_in, this.signed_in, this.opened, this.kept) == (3, 2, 2, 0)
    # `new` was let in yesterday and does not count either way.
    assert (this.came_back, this.old_enough) == (0, 1)
    # `once` opened one text: not a second.
    assert this.second_text == 0
    assert this.week_one_over == 0
    assert [week.week for week in found(db).batches] == ["2026-10-12", "2026-10-05"]


def test_a_second_text_needs_a_later_day_and_the_fourth_week_counts_its_own_days(
    db: sqlite3.Connection,
) -> None:
    # Two texts on the day they were let in is one visit, not a return.
    let_in(db, "one-sitting@example.com", date(2026, 9, 7))
    person(db, 6, "one-sitting@example.com", date(2026, 9, 7))
    opened(db, 6, "a", date(2026, 9, 7))
    opened(db, 6, "b", date(2026, 9, 7))
    # Back on day 25, in the fourth week, to a word.
    kept(db, 6, "w3", date(2026, 10, 2))
    let_in(db, "gone@example.com", date(2026, 9, 7))
    person(db, 7, "gone@example.com", date(2026, 9, 7))
    opened(db, 7, "a", date(2026, 9, 9))
    db.commit()
    week = {week.week: week for week in found(db).batches}["2026-09-07"]
    assert week.second_text == 0
    assert (week.week_one, week.week_one_over) == (1, 2)
    assert (week.week_four, week.week_four_over) == (1, 2)


def test_reach_is_counted_with_no_one_in_it(db: sqlite3.Connection) -> None:
    reach = {part.part: part.people for part in found(db).reach}
    assert reach["Opened a text"] == 4
    assert reach["Looked up a word"] == 1
    assert reach["Kept a word"] == 2
    assert reach["Practised a hard spot"] == 0
    assert reach["Read on a second day"] == 2


def test_the_page_puts_the_press_beside_each_person(db: sqlite3.Connection) -> None:
    page = back_office_page(found(db), 30)
    people = page[page.index('id="tab-people"') :]
    assert people.index("Follow up") < people.index("Each week's readers")
    assert people.index("How far readers get") < people.index("<h2>Accounts")
    assert 'action="/back-office/resend"' in page
    assert '<input type="hidden" name="email" value="never@example.com">' in page
    assert 'href="mailto:once%40example.com?subject=targum"' in page
    assert "2 of 2" in page and "0 of 1" in page
    assert "1 of 4" in page
    assert "%" not in page[page.index("How far readers get") : page.index("<h2>Accounts")]
    assert "erator" not in page


def test_a_week_too_young_says_so() -> None:
    from targum.backoffice import Batch

    page = back_office_page(Survey(batches=[Batch("2026-10-12", let_in=3)]), 30)
    assert "too soon" in page


def test_the_waitlist_folds_away_those_already_let_in() -> None:
    from targum.backoffice import Waiting

    page = back_office_page(
        Survey(
            waiting={"pending": 0, "on": 2, "off": 0},
            waiting_list=[
                Waiting("in@example.com", "on", "2026-10-01", "2026-10-01", invited="2026-10-02"),
                Waiting("wait@example.com", "on", "2026-10-03", "2026-10-03"),
            ],
        ),
        30,
    )
    folded = page[page.index('<details class="let-in">') :]
    assert "Let in (1)" in folded and "in@example.com" in folded
    assert "wait@example.com" not in folded
    assert "wait@example.com" in page


def test_resend_writes_only_to_somebody_let_in_who_never_signed_in(tmp_path: Path) -> None:
    from targum.doorway import resend

    store = Store(tmp_path / "targum.db")
    sent: list[str] = []

    class Mailer:
        def notify(self, to: str, *_: object) -> None:
            sent.append(to)

    store.invite("never@example.com")
    store.invite("reading@example.com")
    reader = store.db.execute(
        "INSERT INTO person (email, made) VALUES ('reading@example.com', 1) RETURNING id"
    ).fetchone()[0]
    store.db.execute(
        "INSERT INTO session (hash, person, made, seen) VALUES ('h', ?, 1, 1)", (reader,)
    )
    store.db.commit()

    assert resend(store, Mailer(), "https://targum.page", "stranger@example.com") is None
    assert resend(store, Mailer(), "https://targum.page", "reading@example.com") is None
    assert sent == []
    row = resend(store, Mailer(), "https://targum.page", "Never@example.com")
    assert row is not None and row.ok and sent == ["never@example.com"]


def test_only_an_admin_resends() -> None:
    served = Path(__file__).resolve().parent.parent / "src" / "targum" / "serve.py"
    text = served.read_text(encoding="utf-8")
    handler = text[text.index("def _resend") : text.index("def _balance")]
    assert "not person.admin" in handler
    assert 'self._send(404, b"not found"' in handler


def test_the_notice_says_so() -> None:
    """The notice changed first: the operator's view per account at 3.2, and the counts
    with no one in them at 3.7."""
    from targum.render.builder import legal_page

    notice = legal_page("privacy")
    assert "may write to the Data Subject about their use" in notice
    assert "how many have used each part" in notice
