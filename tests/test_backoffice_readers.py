"""The back office's Readers table (design's plan, 2026-11-17, §1 and PR 4).

One table of every account but staff: address, plan, last seen, a 14-day sparkline,
texts, words, credits, spend, languages and flags; last seen first; searched as `bq`,
filtered by language, activity, follow-up, flags and plan; fifty a page; no script; and
counts, dates and language codes only, never a word, a title or a source (clause 3.2).
The languages are drawn only once the Privacy Notice says the Controller may see them.
"""

from __future__ import annotations

import datetime as dt
import sqlite3
import time
from collections.abc import Iterator
from pathlib import Path

import pytest

from targum import backoffice
from targum.accounts import Store
from targum.backoffice import (
    ACCOUNT_SEARCH,
    PER_PAGE,
    READER_SORTS,
    SPARK_DAYS,
    Listing,
    ReaderFilter,
    readers,
)
from targum.render.builder import back_office_page

NOW = dt.datetime(2026, 11, 18, 12, tzinfo=dt.UTC)
TODAY = NOW.date()
DAY_MS = 24 * 60 * 60 * 1000


def stamp(day: dt.date, hour: int = 12) -> int:
    return int(dt.datetime.combine(day, dt.time(hour), dt.UTC).timestamp() * 1000)


def listing(**asked: str) -> Listing:
    query = {(ACCOUNT_SEARCH if k == "q" else k): [v] for k, v in asked.items()}
    return Listing.read(query, ACCOUNT_SEARCH, "sort", "page", READER_SORTS)


@pytest.fixture
def store(tmp_path: Path) -> Iterator[Store]:
    """Five readers, an admin and a test account.

    - dina: paid Plan, Hebrew and Russian, active today and five days ago;
    - ruth: comped to Plan, Hebrew, seen by session yesterday only;
    - mosh: Free, French, last active 40 days ago;
    - lea: Free, nothing at all;
    - 12345678@mailinator.com: two flags."""
    made = Store(tmp_path / "targum.db")
    db = made.db
    rows = [
        (1, "dina@example.com", "Dina", stamp(TODAY - dt.timedelta(days=60)), ""),
        (2, "ruth@example.com", "", stamp(TODAY - dt.timedelta(days=30)), "2027-03-04"),
        (3, "mosh@example.com", "", stamp(TODAY - dt.timedelta(days=90)), ""),
        (4, "lea@example.com", "", stamp(TODAY - dt.timedelta(days=1)), ""),
        (5, "12345678@mailinator.com", "", stamp(TODAY - dt.timedelta(days=3)), ""),
        (6, "admin@example.com", "", stamp(TODAY), ""),
        (7, "tester@example.com", "", stamp(TODAY), ""),
    ]
    db.executemany(
        "INSERT INTO person (id, email, name, made, plan_until) VALUES (?, ?, ?, ?, ?)", rows
    )
    db.execute("INSERT INTO admin (email, at) VALUES ('admin@example.com', 1)")
    db.execute("INSERT INTO test_account (email, at) VALUES ('tester@example.com', 1)")
    words = [
        (1, "he", "שלום", stamp(TODAY), 1),
        (1, "he", "בית", stamp(TODAY - dt.timedelta(days=5)), 0),
        (1, "ru", "дом", stamp(TODAY - dt.timedelta(days=5)), 0),
        (2, "he", "ספר", stamp(TODAY - dt.timedelta(days=20)), 0),
        (3, "fr", "maison", stamp(TODAY - dt.timedelta(days=40)), 1),
        (6, "he", "סוד", stamp(TODAY), 0),
    ]
    db.executemany(
        "INSERT INTO word (person, language, lemma, at, learned) VALUES (?, ?, ?, ?, ?)", words
    )
    db.execute(
        "INSERT INTO doc (person, hash, title, language, opened, updated, done)"
        " VALUES (1, 'h1', 'A secret title', 'he', ?, ?, 0)",
        (stamp(TODAY), stamp(TODAY)),
    )
    db.execute(
        "INSERT INTO session (hash, person, made, seen) VALUES ('s', 2, ?, ?)",
        (stamp(TODAY - dt.timedelta(days=1)), stamp(TODAY - dt.timedelta(days=1))),
    )
    db.execute(
        "INSERT INTO job (id, owner, home, source, length, spent, made, claimed)"
        " VALUES ('j1', 1, '', 'upload:a-secret-source.mp3', 1800, 0.42, ?, 0.5)",
        (stamp(TODAY),),
    )
    made.set_billing(
        1,
        cadence="month",
        status="active",
        period_end="2026-12-18T00:00:00Z",
        cancel_at_end=False,
        customer="ctm_1",
        subscription="sub_1",
    )
    yield made


def table(store: Store, wanted: ReaderFilter | None = None, **asked: str) -> backoffice.ReadersPage:
    return readers(
        store.db,
        listing(**asked),
        wanted or ReaderFilter(),
        now=NOW,
        allowance=3600.0,
        plan_allowance=28800.0,
        languages_on=True,
    )


def test_staff_are_counted_nowhere(store: Store) -> None:
    found = table(store)
    emails = [row.email for row in found.rows]
    assert "admin@example.com" not in emails and "tester@example.com" not in emails
    assert found.total == 5
    # TARGUM_OPERATORS too, compared bare.
    without = readers(store.db, listing(), ReaderFilter(), now=NOW, operators=["Lea+x@example.com"])
    assert "lea@example.com" not in [row.email for row in without.rows]


def test_last_seen_comes_first_and_each_row_says_its_figures(store: Store) -> None:
    found = table(store)
    assert [row.email for row in found.rows][:2] == ["dina@example.com", "ruth@example.com"]
    dina, ruth = found.rows[0], found.rows[1]
    assert dina.plan == "Plan" and ruth.plan == "Beta until March 4"
    assert dina.last_seen == TODAY.isoformat()
    assert ruth.last_seen == (TODAY - dt.timedelta(days=1)).isoformat(), "seen by its session"
    assert (dina.texts, dina.words, dina.learned) == (1, 3, 1)
    assert dina.used == 1800.0 and dina.spent == pytest.approx(0.42)
    assert dina.allowance == 28800.0 and found.rows[-1].allowance == 3600.0
    assert dina.languages == ["he", "ru"]
    assert len(dina.spark) == SPARK_DAYS and dina.spark[-1] and dina.spark[-6]
    assert sum(dina.spark) == 2
    flagged = next(row for row in found.rows if row.email.startswith("12345678"))
    assert len(flagged.flags) >= 2


def test_each_sort_orders_the_whole_list(store: Store) -> None:
    for sort in READER_SORTS:
        assert len(table(store, sort=sort).rows) == 5, sort
    assert table(store, sort="joined").rows[0].email == "lea@example.com"
    assert table(store, sort="words").rows[0].email == "dina@example.com"
    assert table(store, sort="spend").rows[0].email == "dina@example.com"
    assert table(store, sort="credits").rows[0].email == "dina@example.com"
    assert table(store, sort="flags").rows[0].email == "12345678@mailinator.com"


def test_search_is_by_address_or_name_and_only_text(store: Store) -> None:
    assert [row.email for row in table(store, q="DINA").rows] == ["dina@example.com"]
    assert [row.email for row in table(store, q="ruth@").rows] == ["ruth@example.com"]
    assert table(store, q="%").rows == []
    assert table(store, q="admin").rows == [], "staff are not found either"


def test_each_filter_narrows(store: Store) -> None:
    def emails(**said: object) -> list[str]:
        return sorted(row.email for row in table(store, ReaderFilter(**said)).rows)  # type: ignore[arg-type]

    assert emails(language="ru") == ["dina@example.com"]
    assert emails(language="he") == ["dina@example.com", "ruth@example.com"]
    assert emails(active="7") == ["dina@example.com"]
    assert emails(active="30") == ["dina@example.com", "ruth@example.com"]
    assert "mosh@example.com" in emails(active="inactive")
    assert "dina@example.com" not in emails(active="inactive")
    assert emails(plan="plan") == ["dina@example.com"]
    assert emails(plan="beta") == ["ruth@example.com"]
    assert "dina@example.com" not in emails(plan="free") and "lea@example.com" in emails(
        plan="free"
    )
    assert emails(flagged=True) == ["12345678@mailinator.com"]


def test_the_filter_is_read_off_the_address_and_anything_odd_is_none() -> None:
    read = ReaderFilter.read(
        {"lang": ["HE"], "active": ["7"], "plan": ["beta"], "follow": ["1"], "flagged": ["1"]}
    )
    assert (read.language, read.active, read.plan, read.follow, read.flagged) == (
        "he",
        "7",
        "beta",
        True,
        True,
    )
    odd = ReaderFilter.read(
        {"lang": ["he' OR 1=1 --"], "active": ["365"], "plan": ["gold"], "follow": ["yes"]}
    )
    assert (odd.language, odd.active, odd.plan, odd.follow) == ("", "", "", False)


def test_the_page_draws_counts_and_never_a_word_title_or_source(store: Store) -> None:
    page = back_office_page(None, 30, listed=table(store), section="readers")
    assert "dina@example.com" in page and 'href="/back-office/readers/1"' in page
    for secret in ("שלום", "בית", "дом", "maison", "A secret title", "a-secret-source"):
        assert secret not in page, secret
    assert "<script" not in page.split('<section class="bo-page"')[1], "no script"
    assert '<svg class="spark"' in page and "Active on 2 of the last 14 days" in page
    assert "Beta until March 4" in page and "30 of 480" in page and "$0.42" in page


def test_languages_wait_for_the_notice(store: Store, monkeypatch: pytest.MonkeyPatch) -> None:
    """The column and its filter are drawn only once clause 3.2 says the Controller may
    see the languages an account reads in; until then a language asked for is ignored."""
    hidden = readers(store.db, listing(), ReaderFilter(language="ru"), now=NOW, languages_on=False)
    assert len(hidden.rows) == 5, "the filter does nothing until the Notice allows it"
    assert all(row.languages == [] for row in hidden.rows) and hidden.languages == []
    page = back_office_page(None, 30, listed=hidden, section="readers")
    assert "<th>Languages</th>" not in page and 'name="lang"' not in page
    shown = back_office_page(None, 30, listed=table(store), section="readers")
    assert "<th>Languages</th>" in shown and '<option value="ru">ru</option>' in shown
    # An explicit switch beside LEGAL_CHANGED, flipped by the Notice PR (qa on #1309),
    # never the Notice's words found anywhere in its template.
    from targum.render import builder

    assert backoffice.languages_shown() is builder.NOTICE_ALLOWS_LANGUAGES
    monkeypatch.setattr(builder, "NOTICE_ALLOWS_LANGUAGES", False)
    off = readers(store.db, listing(), ReaderFilter(language="ru"), now=NOW)
    assert not off.languages_shown and len(off.rows) == 5
    page = back_office_page(None, 30, listed=off, section="readers")
    assert "<th>Languages</th>" not in page and 'name="lang"' not in page
    monkeypatch.setattr(builder, "NOTICE_ALLOWS_LANGUAGES", True)
    on = readers(store.db, listing(), ReaderFilter(language="ru"), now=NOW)
    assert on.languages_shown and [row.email for row in on.rows] == ["dina@example.com"]


def test_the_language_filter_offers_readers_languages_only(store: Store) -> None:
    """The admin's Hebrew word is not why "he" is offered; a language only staff read in
    is no reader's (qa on #1309)."""
    store.db.execute("INSERT INTO word (person, language, lemma, at) VALUES (6, 'it', 'casa', 1)")
    assert "it" not in table(store).languages
    assert table(store).languages == ["fr", "he", "ru"]


def test_pages_keep_the_search_order_and_filters(store: Store) -> None:
    db = store.db
    db.execute("BEGIN")
    db.executemany(
        "INSERT INTO person (id, email, made) VALUES (?, ?, ?)",
        [(100 + n, f"more{n:03d}@example.com", stamp(TODAY) - n * 1000) for n in range(120)],
    )
    db.execute("COMMIT")
    found = table(store, ReaderFilter(plan="free"), sort="joined", q="more")
    assert len(found.rows) == PER_PAGE and found.listing.matches == 120
    page = back_office_page(None, 30, listed=found, section="readers")
    assert (
        'rel="next" href="/back-office/readers?bq=more&amp;sort=joined&amp;plan=free&amp;page=2"'
        in page
    )
    later = table(store, ReaderFilter(plan="free"), sort="joined", q="more", page="3")
    assert len(later.rows) == 20 and later.listing.page == 3


# -- five thousand accounts (design's plan: "5k timing") ---------------------------------


@pytest.fixture
def five_thousand(tmp_path: Path) -> sqlite3.Connection:
    """5,000 readers, each with a few words, a text, a day, a session and a job."""
    made = Store(tmp_path / "big.db")
    db = made.db
    now = stamp(TODAY)
    db.execute("BEGIN")
    db.executemany(
        "INSERT INTO person (id, email, name, made, plan_until) VALUES (?, ?, ?, ?, ?)",
        [
            (
                n,
                f"reader{n:04d}@example.com",
                "",
                now - n * 60_000,
                "2027-03-04" if n % 9 == 0 else "",
            )
            for n in range(1, 5001)
        ],
    )
    db.executemany(
        "INSERT INTO word (person, language, lemma, at, learned) VALUES (?, ?, ?, ?, ?)",
        [
            (n, "he" if n % 3 else "ru", f"w{k}", now - ((n + k) % 40) * DAY_MS, k % 2)
            for n in range(1, 5001)
            for k in range(6)
        ],
    )
    db.executemany(
        "INSERT INTO doc (person, hash, title, language, opened, updated, done)"
        " VALUES (?, ?, '', 'he', ?, ?, 0)",
        [(n, f"h{n}", now - (n % 50) * DAY_MS, now - (n % 50) * DAY_MS) for n in range(1, 5001)],
    )
    db.executemany(
        "INSERT INTO day (person, day, count) VALUES (?, ?, 10)",
        [(n, (TODAY - dt.timedelta(days=n % 20)).isoformat()) for n in range(1, 5001)],
    )
    db.executemany(
        "INSERT INTO session (hash, person, made, seen) VALUES (?, ?, ?, ?)",
        [(f"s{n}", n, now - n * 1000, now - (n % 30) * DAY_MS) for n in range(1, 5001)],
    )
    db.executemany(
        "INSERT INTO job (id, owner, home, source, length, spent, made, claimed)"
        " VALUES (?, ?, '', 'x', ?, ?, ?, 0.1)",
        [
            (f"j{n}", n, (n % 60) * 60.0, (n % 7) / 10, now - (n % 10) * DAY_MS)
            for n in range(1, 5001)
        ],
    )
    db.execute("COMMIT")
    return db


#: Generous for CI's machines; measured locally well under it.
FAST_ENOUGH = 1.0
#: Follow-up due reads `_growth` over every reader, as the overview's Follow up does:
#: about 0.45 s locally and 1.01 s on CI's 3.12 runner (targum-internal#748), so its
#: bar is its own. It is the one filter to watch past five thousand.
FOLLOW_UP_FAST_ENOUGH = 2.5


@pytest.mark.parametrize(
    ("asked", "wanted"),
    [
        ({}, ReaderFilter()),
        ({"sort": "spend"}, ReaderFilter()),
        ({"sort": "flags"}, ReaderFilter()),
        ({"q": "reader4"}, ReaderFilter()),
        ({}, ReaderFilter(language="ru", active="30")),
        ({}, ReaderFilter(active="inactive", plan="free")),
        ({"page": "60"}, ReaderFilter(plan="beta")),
        ({}, ReaderFilter(follow=True)),
    ],
)
def test_five_thousand_readers_are_quick(
    five_thousand: sqlite3.Connection, asked: dict[str, str], wanted: ReaderFilter
) -> None:
    started = time.perf_counter()
    found = readers(
        five_thousand,
        listing(**asked),
        wanted,
        now=NOW,
        allowance=3600.0,
        plan_allowance=28800.0,
        languages_on=True,
    )
    took = time.perf_counter() - started
    assert found.total == 5000
    assert len(found.rows) <= PER_PAGE
    bar = FOLLOW_UP_FAST_ENOUGH if wanted.follow else FAST_ENOUGH
    assert took < bar, f"{asked} {wanted}: {took:.2f} s"


#: One reader's page asks Follow up's rule and the flags of everybody, as the Overview
#: does, so that the page and the list never disagree: its own bar, generous for CI.
READER_PAGE_FAST_ENOUGH = 2.5


def test_one_readers_page_is_quick_among_five_thousand(
    five_thousand: sqlite3.Connection,
) -> None:
    started = time.perf_counter()
    one = backoffice.reader(five_thousand, 2500, today=TODAY, titles={"h2500": "A Title"})
    took = time.perf_counter() - started
    assert one is not None and [text.title for text in one.library] == ["A Title"]
    assert took < READER_PAGE_FAST_ENOUGH, f"{took:.2f} s"
