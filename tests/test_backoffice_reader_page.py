"""One reader's page in the back office (design's plan, 2026-11-17, §1 and PR 5).

Eight sections in the plan's order; a text named only when it is a row of the public
catalogue, and by the catalogue's title; everything a reader saved, noted, brought or
said to the chat kept off the page; erased records gone; the record of use (clause 3.6)
not shown while the reader has recording off; and no page at all for staff or nobody.
"""

from __future__ import annotations

import datetime as dt
from datetime import date
from pathlib import Path

import pytest

from targum import backoffice
from targum.accounts import KNOWN_STATUS, Store
from targum.backoffice import reader
from targum.render.builder import back_office_page

TODAY = date(2026, 11, 18)
#: The library's own text, by hash, and the catalogue's title for it.
LIBRARY_HASH = "lib-hash"
CATALOGUE_TITLE = "Catalogue Title of a Library Text"
#: What the reader wrote, kept, brought or said, none of which the page may show.
SECRETS = {
    "lemma": "סודיביותר",
    "surface": "וסודיביותר",
    "meaning": "a-secret-meaning",
    "note": "a-secret-note",
    "phrase": "a-secret-phrase",
    "doc title": "Their Own Title For It",
    "upload title": "Secret Upload Title",
    "upload source": "https://private.example/their-recording.mp3",
    "chat title": "a-secret-chat-title",
    "chat turn": "a-secret-chat-turn",
    "slip wrote": "a-secret-they-wrote",
    "slip recast": "a-secret-recast",
    "practice line": "a-secret-practice-line",
    "spot as stored": "a-secret-spot-key",
    "erased title": "An Erased Library Title",
}
#: What they wrote to us through Tell us, which the page does show (clause 3.14).
TOLD = "the audio stops on page two"


def stamp(when: date, hour: int = 12) -> int:
    return int(dt.datetime.combine(when, dt.time(hour, 0), dt.UTC).timestamp() * 1000)


def days_ago(n: int) -> date:
    return TODAY - dt.timedelta(days=n)


@pytest.fixture
def store(tmp_path: Path) -> Store:
    """Dina, a reader with a little of everything; an admin, a test account and the
    operator, who have no page."""
    store = Store(tmp_path / "targum.db")
    db = store.db
    for who, email in (
        (1, "dina@example.com"),
        (2, "admin@example.com"),
        (3, "tester@example.com"),
        (4, "ops+x@example.com"),
    ):
        db.execute(
            "INSERT INTO person (id, email, name, made, came_from) VALUES (?, ?, '', ?, ?)",
            (who, email, stamp(date(2026, 10, 1)), "/aliyah" if who == 1 else ""),
        )
    db.execute("INSERT INTO admin (email, at) VALUES ('admin@example.com', 1)")
    db.execute("INSERT INTO test_account (email, at) VALUES ('tester@example.com', 1)")
    # Words: two saved this week, one known, one by ear, one erased.
    db.execute(
        "INSERT INTO word (person, language, lemma, surface, meaning, note, status, at,"
        " known_at, ear, ear_at) VALUES (1, 'he', ?, ?, ?, ?, ?, ?, ?, 1, ?)",
        (
            SECRETS["lemma"],
            SECRETS["surface"],
            SECRETS["meaning"],
            SECRETS["note"],
            KNOWN_STATUS,
            stamp(days_ago(1)),
            stamp(days_ago(1)),
            stamp(days_ago(1)),
        ),
    )
    db.execute(
        "INSERT INTO word (person, language, lemma, at) VALUES (1, 'he', 'שני', ?)",
        (stamp(days_ago(2)),),
    )
    db.execute(
        "INSERT INTO word (person, language, lemma, at, gone) VALUES (1, 'he', 'נמחק', ?, 1)",
        (stamp(days_ago(2)),),
    )
    db.execute(
        "INSERT INTO phrase (person, id, text, note, at) VALUES (1, 'p1', ?, ?, ?)",
        (SECRETS["phrase"], SECRETS["note"], stamp(days_ago(3))),
    )
    db.execute(
        "INSERT INTO meaning (person, source, target, term, meaning, note) VALUES"
        " (1, 'he', 'en', ?, ?, ?)",
        (SECRETS["lemma"], SECRETS["meaning"], SECRETS["note"]),
    )
    # Texts: one from the library (its own row titled by the reader), one they built, and
    # an erased library text.
    db.execute(
        "INSERT INTO doc (person, hash, title, language, opened, updated, done)"
        " VALUES (1, ?, ?, 'he', ?, ?, 1)",
        (LIBRARY_HASH, SECRETS["doc title"], stamp(days_ago(2)), stamp(days_ago(2))),
    )
    db.execute(
        "INSERT INTO doc (person, hash, title, language, opened, updated)"
        " VALUES (1, 'upload-hash', ?, 'he', ?, ?)",
        (SECRETS["upload title"], stamp(days_ago(4)), stamp(days_ago(4))),
    )
    db.execute(
        "INSERT INTO doc (person, hash, title, language, opened, updated, gone)"
        " VALUES (1, 'erased-hash', ?, 'he', ?, ?, 1)",
        (SECRETS["erased title"], stamp(days_ago(5)), stamp(days_ago(5))),
    )
    for section in ("s1", "s2"):
        db.execute(
            "INSERT INTO section (person, hash, section, at) VALUES (1, ?, ?, ?)",
            (LIBRARY_HASH, section, stamp(days_ago(2))),
        )
    store.save_job(
        {
            "id": "b1",
            "owner": 1,
            "home": "h",
            "source": SECRETS["upload source"],
            "title": SECRETS["upload title"],
            "language": "he",
            "options": '{"to": "en"}',
            "stage": "done",
            "kind": "build",
            "made": stamp(days_ago(4)),
            "seconds": 600,
            "audio": 1,
        }
    )
    # The chat, a correction, a practice and a Tell us message.
    db.execute(
        "INSERT INTO chat (id, person, title, made) VALUES ('c1', 1, ?, ?)",
        (SECRETS["chat title"], stamp(days_ago(1))),
    )
    db.execute(
        "INSERT INTO chat_turn (chat, n, role, content) VALUES ('c1', 0, 'user', ?)",
        (SECRETS["chat turn"],),
    )
    db.execute(
        "INSERT INTO slip (person, at, wrote, recast) VALUES (1, ?, ?, ?)",
        (stamp(days_ago(1)), SECRETS["slip wrote"], SECRETS["slip recast"]),
    )
    db.execute(
        "INSERT INTO practised (person, language, spot, step, history, seen, at)"
        " VALUES (1, 'he', 'binyan', 3, ?, ?, ?)",
        (SECRETS["practice line"], f'["{SECRETS["practice line"]}"]', stamp(days_ago(1))),
    )
    db.execute(
        "INSERT INTO practised (person, language, spot, step, at) VALUES (1, 'he', ?, 1, ?)",
        (SECRETS["spot as stored"], stamp(days_ago(1))),
    )
    db.execute(
        "INSERT INTO told (person, at, said, page) VALUES (1, ?, ?, '/texts')",
        (stamp(days_ago(1)), TOLD),
    )
    # The record of use: two lookups, five minutes heard, 250 words read, each in a
    # segment that names a word.
    for kind, amount in (("lookup", 0), ("lookup", 0), ("play", 300), ("section", 250)):
        db.execute(
            "INSERT INTO event (person, kind, day, language, medium, document, segment, word,"
            " amount) VALUES (1, ?, ?, 'he', 'read', ?, 's1', ?, ?)",
            (kind, days_ago(1).isoformat(), LIBRARY_HASH, SECRETS["lemma"], amount),
        )
    db.commit()
    return store


def page_of(store: Store, who: int = 1, **asked: object) -> tuple[backoffice.Reader, str]:
    one = reader(
        store.db,
        who,
        today=TODAY,
        operators=["ops@example.com"],
        titles={LIBRARY_HASH: CATALOGUE_TITLE, "erased-hash": SECRETS["erased title"]},
        **asked,  # type: ignore[arg-type]
    )
    assert one is not None
    return one, back_office_page(None, 30, reader=one, section="reader")


def test_the_eight_sections_come_in_the_plans_order(store: Store) -> None:
    _, page = page_of(store)
    panel = page[page.index('aria-label="Reader"') :]
    heads = [
        "dina@example.com",
        "<h3>Why write",
        '<h3 id="told">Tell us',
        "<h3>The last 30 days",
        "<h3>Reading",
        "<h3>Words and weeks",
        "<h3>Practice",
        "<h3>Credits and jobs",
    ]
    places = [panel.index(head) for head in heads]
    assert places == sorted(places)


def test_the_header_says_who_they_are(store: Store) -> None:
    one, page = page_of(store)
    assert (one.plan, one.came_from, one.joined) == ("Free", "/aliyah", "2026-10-01")
    assert one.last_seen == days_ago(1).isoformat()
    assert 'href="mailto:dina%40example.com?subject=targum">Write' in page
    assert "Free &middot; joined 2026-10-01 from /aliyah" in page


def test_a_library_text_is_named_by_the_catalogue_and_nothing_else_is(store: Store) -> None:
    one, page = page_of(store)
    assert [(text.title, text.sections, text.finished) for text in one.library] == [
        (CATALOGUE_TITLE, 2, True)
    ]
    assert CATALOGUE_TITLE in page
    assert one.other_texts == 1, "the upload, counted"
    assert [(b.kind, b.language, b.medium, b.texts) for b in one.brought] == [
        ("build", "he", "recording", 1)
    ]


def test_nothing_a_reader_wrote_kept_or_brought_reaches_the_page(store: Store) -> None:
    """Clause 3.2: no word, phrase, note, title or source of what they brought, no chat
    and no correction; clause 3.6: no word looked up and no segment."""
    _, page = page_of(store)
    for name, secret in SECRETS.items():
        assert secret not in page, name
    assert TOLD in page, "what they wrote to us is shown, as on the Overview (clause 3.14)"


def test_erased_records_are_not_counted(store: Store) -> None:
    one, _ = page_of(store)
    assert one.totals == {"saved": 2, "learned": 0, "known": 1, "ear": 1, "phrases": 1}
    assert all(text.title != SECRETS["erased title"] for text in one.library)
    week = one.weeks[-1]
    assert (week.saved, week.known, week.ear) == (2, 1, 1)


def test_the_record_of_use_is_counted_by_day_and_week(store: Store) -> None:
    one, page = page_of(store)
    yesterday = one.days[-2]
    assert yesterday.day == days_ago(1).isoformat()
    assert (yesterday.active, yesterday.words, yesterday.lookups, yesterday.minutes) == (
        True,
        1,
        2,
        5.0,
    )
    week = one.weeks[-1]
    assert (week.read, week.lookups, week.heard, week.per_hundred()) == (250, 2, 5.0, 0.8)
    assert sorted((spot.name, spot.step) for spot in one.spots) == [
        ("another spot", 1),
        ("root and binyan", 3),
    ], "a spot is named from the fixed list, never as stored"
    assert ">Lookups<" in page and "Recording is off" not in page


def test_with_recording_off_the_page_says_so_instead_of_zeros(store: Store) -> None:
    store.db.execute("UPDATE person SET events = 'off' WHERE id = 1")
    store.db.commit()
    one, page = page_of(store)
    assert not one.recording and one.spots == []
    assert all(day.lookups == 0 and day.minutes == 0 for day in one.days)
    assert all(week.read is None and week.lookups is None for week in one.weeks)
    assert page.count("Recording is off") == 3
    assert ">Lookups<" not in page and ">Minutes played<" not in page
    assert "root and binyan" not in page
    # What clause 3.2 holds is still there.
    assert one.totals["saved"] == 2 and CATALOGUE_TITLE in page


def test_staff_and_nobody_have_no_page(store: Store) -> None:
    for who in (2, 3, 4, 99):
        assert reader(store.db, who, today=TODAY, operators=["ops@example.com"]) is None, who


def test_why_write_names_the_follow_up_and_its_press(store: Store) -> None:
    """Somebody let in and never signed in is offered Send again, not Write."""
    store.db.execute(
        "INSERT INTO person (id, email, name, made) VALUES (5, 'quiet@example.com', '', ?)",
        (stamp(date(2026, 10, 1)),),
    )
    store.db.execute(
        "INSERT INTO invited (email, at) VALUES ('quiet@example.com', ?)",
        (stamp(date(2026, 11, 1)),),
    )
    store.db.commit()
    one, page = page_of(store, 5)
    assert one.action == "resend" and one.why.startswith("Let in November 1")
    assert 'action="/back-office/resend"' in page and "mailto:quiet" not in page


def test_a_tell_us_press_on_the_page_comes_back_to_it(store: Store) -> None:
    _, page = page_of(store)
    told = page[page.index('<h3 id="told">') :]
    assert '<input type="hidden" name="reader" value="1">' in told


def test_the_page_carries_no_script_of_its_own(store: Store) -> None:
    """Only the shell's, which every back-office page has: nothing in the reader's part."""
    _, page = page_of(store)
    assert "<script" not in page[page.index('aria-label="Reader"') :]
    shell = back_office_page(None, 30, section="waitlist")
    assert page.count("<script") == shell.count("<script")
