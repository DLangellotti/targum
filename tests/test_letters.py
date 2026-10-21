"""What every mail says, and that none of it fetches anything.

design.md §12, "Mail is drawn, and fetches nothing" (2026-09-27): each of the seven mails a
reader can receive is plain text and the same words drawn as HTML on the desk's frame,
with the logo drawn in table cells rather than loaded. Nothing in the HTML reaches for the
network: no image, no stylesheet, no font, no pixel, no redirect.
"""

from __future__ import annotations

import io
import re
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from targum import letters, series
from targum.accounts import Store
from targum.letters import Letter
from targum.mail import ConsoleMailer
from targum.weekly.models import Edition, Issue, Level, State, entry_id, folder

SITE = "https://targum.page"
WEEK = "2026-w40"

PORTION = {
    "id": "parasha",
    "name": "The weekly portion",
    "what": "",
    "page": "/parasha",
    "instalment": {"id": "haazinu", "title": "Ha'azinu", "hebrew": "הַאֲזִינוּ"},
}
TEHILLIM = {
    "id": "tehillim",
    "name": "Daily Tehillim",
    "what": "",
    "page": "/tehillim",
    "cadence": "daily",
    "instalment": {"id": "27", "title": "Psalms 120–134", "hebrew": "תהלים"},
}


def issue(blurb: str = "הכנסת חזרה, וגל חום סוגר בתי ספר.") -> Issue:
    return Issue(
        id=WEEK,
        dated="2026-09-28",
        title="מבט השבוע",
        blurb=blurb,
        state=State.published,
        editions=[
            Edition(
                level=level, entry_id=entry_id(WEEK, level), folder=folder(WEEK, level), ok=True
            )
            for level in Level
        ],
    )


def every(language: str) -> dict[str, Letter]:
    return {
        "sign-in": letters.sign_in(f"{SITE}/account/enter?t=abc", language),
        "waitlist": letters.waitlist_confirm(f"{SITE}/waitlist/confirm?t=abc", language),
        "invitation": letters.invitation(SITE, language),
        "weekly-confirm": letters.weekly_confirm(f"{SITE}/weekly/confirm?t=abc", language),
        "weekly": letters.weekly_issue(issue(), SITE, "stop1", language),
        "daily": letters.subscriptions_daily(
            [
                {
                    "name": series.said_in(PORTION, language)["name"],
                    "stop": "stop2",
                    "rows": [("הַאֲזִינוּ", "he", "Ready", "/parasha/read/haazinu/")],
                },
                {
                    "name": "Sport",
                    "stop": "stop3",
                    "rows": [("כתבה", "he", "A link", "/add?source=https%3A%2F%2Fx%2Fa")],
                },
            ],
            SITE,
            "t=stop2&t=stop3",
            language,
        ),
        "ready": letters.build_ready(
            "Shakshuka at home", f"{SITE}/reader/x", SITE, language, asked=False, listen=False
        ),
        "deleted": letters.account_deleted(
            SITE, date(2026, 10, 8), language, grace_days=7, backups_kept=14
        ),
    }


LANGUAGES = ("en", "ru")


@pytest.mark.parametrize("language", LANGUAGES)
def test_the_html_fetches_nothing(language: str) -> None:
    """The readers' rule, applied to mail: nothing is loaded, so nothing is tracked and a
    client that blocks images loses nothing."""
    for name, letter in every(language).items():
        page = letter.html.lower()
        for banned in ("<img", "<link", "<script", "@import", "url(", "src=", "<svg", "@font-face"):
            assert banned not in page, f"{name} ({language}) carries {banned}"
        for href in re.findall(r'href="([^"]*)"', letter.html):
            assert href.startswith(SITE + "/"), f"{name}: a link off the site, {href}"
            assert not re.search(r"utm_|[?&](mc_|trk|track)", href), f"{name}: {href} is tracked"
        # Every address in the page is one of its own links: no stray http anywhere else.
        addresses = re.findall(r"https?://[^\s\"'<>]+", letter.html)
        assert all(a.startswith(SITE) for a in addresses), f"{name}: {addresses}"


@pytest.mark.parametrize("language", LANGUAGES)
def test_every_link_in_the_drawing_is_in_the_text(language: str) -> None:
    """The two halves are drawn from one list, so a reader whose client shows no HTML
    has every way in the drawn one has."""
    for name, letter in every(language).items():
        for href in set(re.findall(r'href="([^"]*)"', letter.html)):
            href = href.replace("&amp;", "&")
            assert href in letter.text, f"{name} ({language}): {href} is only in the HTML"


@pytest.mark.parametrize("language", LANGUAGES)
def test_every_mail_keeps_the_voice(language: str) -> None:
    """§6: no exclamation marks, the name lowercase and Latin, no emoji."""
    for name, letter in every(language).items():
        for said in (letter.subject, letter.text):
            assert "!" not in said, f"{name}: {said!r}"
            assert "Targum" not in said and "таргум" not in said.lower(), name
            assert not re.findall(r"[\U0001F300-\U0001FAFF]", said), name


@pytest.mark.parametrize("language", LANGUAGES)
def test_every_mail_is_light_only_and_carries_the_drawn_mark(language: str) -> None:
    for name, letter in every(language).items():
        assert 'content="light only"' in letter.html, name
        assert f'<html lang="{language}"' in letter.html, name
        # The mark's two columns in the app's ink and gold (§12, "Every mail is the
        # board's", 2026-10-09), and the wordmark as text.
        assert 'bgcolor="#1c1a17"' in letter.html and 'bgcolor="#b8935e"' in letter.html
        assert "#201e1b" not in letter.html and "#a5824f" not in letter.html
        assert ">targum</td>" in letter.html


def test_only_the_lists_carry_list_headers() -> None:
    for name, letter in every("en").items():
        listed = name in ("weekly", "daily")
        assert ("List-Unsubscribe" in letter.headers) is listed, name
        if listed:
            assert letter.headers["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
            assert letter.headers["List-Unsubscribe"].startswith(f"<{SITE}/")
            assert re.fullmatch(r".+ <[a-z0-9.-]+>", letter.headers["List-Id"]), name


def test_the_postal_address_is_drawn_only_when_there_is_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(letters.POSTAL_ENV, raising=False)
    before = every("en")
    assert "Somewhere" not in before["weekly"].text
    monkeypatch.setenv(letters.POSTAL_ENV, "targum, 1 Somewhere St, Tel Aviv")
    after = every("en")
    for name in ("weekly", "daily"):
        assert "1 Somewhere St" in after[name].text and "1 Somewhere St" in after[name].html
    for name in ("sign-in", "ready", "invitation", "deleted"):
        assert "Somewhere" not in after[name].text, f"{name} is not a list"


def test_the_digest_is_named_and_says_what_this_week_is() -> None:
    english = letters.weekly_issue(issue(), SITE, "tok")
    assert english.subject == "Weekly News Digest · Monday, September 28, 2026"
    assert "הכנסת חזרה" in english.text, "the issue's own blurb"
    assert "Five sections" not in english.text
    assert f"{SITE}/weekly/{WEEK}/aleph" in english.text
    assert "Easy" in english.text and "1,000 words" in english.text
    assert english.text.count(f"{SITE}/weekly/stop?t=tok") == 1

    russian = letters.weekly_issue(issue(), SITE, "tok", "ru")
    assert russian.subject.startswith("Недельный обзор новостей · ")
    assert f"{SITE}/weekly/{WEEK}/aleph?lang=ru" in russian.text
    assert "/weekly/stop?t=tok&lang=ru" in russian.text
    assert "lang" not in russian.headers["List-Unsubscribe"], "the one-click POST reads no lang"

    quiet = letters.weekly_issue(issue(blurb=""), SITE, "tok")
    assert quiet.text.startswith("Monday, September 28, 2026"), "no blurb, nothing in its place"


def test_the_digest_s_masthead_is_its_hebrew_name_and_the_week() -> None:
    """Board MailsDesk: מבט השבוע and the Monday, in Hebrew, whatever the issue's title."""
    mail = letters.weekly_issue(issue().model_copy(update={"title": "כותרת"}), SITE, "tok")
    assert "מבט השבוע · 28 בספטמבר 2026" in mail.html
    assert ">כותרת<" not in mail.html


def test_a_ready_mail_says_why_it_came_in_the_readers_language() -> None:
    unasked = letters.build_ready("Ruth", f"{SITE}/r", SITE, "ru", asked=False, listen=False)
    assert unasked.subject == "Можно читать: ⁨Ruth⁩"
    assert "дольше нескольких минут" in unasked.text
    asked = letters.build_ready("Ruth", f"{SITE}/r", SITE, "en", asked=True, listen=True)
    assert asked.subject == "Ready to listen: ⁨Ruth⁩"
    assert "you asked us to email you" in asked.text
    film = letters.build_ready(
        "Ruth", f"{SITE}/r", SITE, "ru", asked=False, listen=True, watch=True
    )
    assert film.subject == "Можно смотреть: ⁨Ruth⁩", "a film is watched before it is heard"


def test_a_ready_mail_is_a_tile_the_title_and_open() -> None:
    """Board MailsDesk and David's call of 2026-10-09: a tile, the title and Open, with no
    vocabulary strip. The label over the title says what it is ready for."""
    film = letters.build_ready(
        "האם החשמונאים המציאו את היהדות?",
        f"{SITE}/r",
        SITE,
        "en",
        asked=False,
        listen=True,
        watch=True,
        title_language="he",
        parts=4,
        seconds=24 * 60,
    )
    assert ">Open<" in film.html and ">Watch<" not in film.html
    assert "Ready to watch" in film.html
    assert 'dir="rtl" lang="he"' in film.html, "the title in its own direction"
    assert ">ה</span>" in film.html, "the tile carries its first letter"
    assert "&#9654;&#65038;" in film.html, "a video's tile has the play badge, as text"
    assert "Uploaded by you · Video · 4 parts · 24 min" in film.text
    assert "under Continue" in film.text
    for absent in ("words", "vocabulary", "Words"):
        assert absent not in film.text, "no vocabulary strip"
    book = letters.build_ready("Отец Сергий", f"{SITE}/r", SITE, "ru", asked=False, listen=True)
    assert ">Открыть<" in book.html and "&#9654;" not in book.html
    assert "Загружено вами · Запись" in book.text


def test_the_account_deleted_mail_says_when_what_and_when_the_backups_forget() -> None:
    """Board MailsDesk's last mail: when they asked, when it went, what went, that nothing
    remains, and when the last backup holding it rolls off (14 nights after)."""
    from targum import backup
    from targum.accounts import GRACE_DAYS

    # The mail says "seven days" in words; the grace period it describes is seven.
    assert GRACE_DAYS == 7 and backup.KEEP == 14
    mail = letters.account_deleted(
        SITE, date(2026, 10, 8), "en", grace_days=GRACE_DAYS, backups_kept=backup.KEEP
    )
    assert mail.subject == "Your targum account is deleted"
    assert "on October 8, 2026" in mail.text and "on October 15, 2026" in mail.text
    assert "gone by October 29, 2026" in mail.text and "every 14 days" in mail.text
    assert "can't restore it" in mail.text and "last email" in mail.text
    assert not mail.headers, "transactional: no list headers"
    russian = letters.account_deleted(
        SITE, date(2026, 10, 8), "ru", grace_days=GRACE_DAYS, backups_kept=backup.KEEP
    )
    assert "8 октября 2026" in russian.text and "29 октября 2026" in russian.text


def test_the_harness_draws_every_mail_and_sends_nothing(tmp_path: Path) -> None:
    """`targum mails --out DIR`: every mail, in every language, as HTML and text."""
    from typer.testing import CliRunner

    from targum import mail_samples, strings
    from targum.cli import app

    result = CliRunner().invoke(app, ["mails", "--out", str(tmp_path)])
    assert result.exit_code == 0, result.output
    names = set(mail_samples.samples("en"))
    assert {"sign-in", "ready", "daily", "weekly", "deleted"} <= names
    for code in strings.languages():
        for name in names:
            page = tmp_path / f"{name}.{code}.html"
            assert page.is_file() and (tmp_path / f"{name}.{code}.txt").is_file(), page
            assert f'<html lang="{code}"' in page.read_text(encoding="utf-8")
    assert (tmp_path / "index.html").is_file()


def test_the_daily_mail_draws_each_thing_as_a_tile_and_keeps_its_ways_out() -> None:
    mail = every("en")["daily"]
    assert ">ה</td>" in mail.html or "ה</td>" in mail.html, "the first letter on its tile"
    assert "Unsubscribe from all of these" in mail.html and "Your subscriptions" in mail.html
    assert mail.headers["List-Unsubscribe"] == f"<{SITE}/subscriptions/stop?t=stop2&t=stop3>"
    assert mail.headers["List-Id"].startswith("subscriptions <")


def test_a_daily_cycle_is_in_the_one_mail_a_day(tmp_path: Any) -> None:
    """Reversed on 2026-10-09 (design.md §12, "Everything new comes in one mail a day"):
    a daily cycle's instalment is in the mail, with everything else new, once a day."""
    from targum import subscriptions

    store = Store(tmp_path / "words.db")
    store.finish_sign_in(store.start_sign_in("a@example.org"))
    store.follow_series("a@example.org", "tehillim")
    store.follow_series("a@example.org", "parasha")
    me = store.person_by_email("a@example.org")
    assert me is not None
    for row in store.subscriptions(me.id):
        store.add_sub_items(
            int(row["id"]),
            [{"key": "i1", "title": f"{row['key']} today", "reader": "/x/", "state": "ready"}],
        )
    box = io.StringIO()
    report = subscriptions.daily(store, ConsoleMailer(box), SITE, pause=0)
    assert report.sent == ["a@example.org"], "one mail, with both"
    assert "tehillim today" in box.getvalue() and "parasha today" in box.getvalue()


def test_every_daily_cycle_says_it_is_daily() -> None:
    from targum.daily.cycles import CYCLES

    ids = {cycle.slug for cycle in CYCLES}
    rows = [row for row in series.current(public=True) if row["id"] in ids]
    assert rows and all(row["cadence"] == "daily" for row in rows)


def test_an_account_is_told_once_when_it_is_gone(tmp_path: Path) -> None:
    """The mail goes when the grace period ends and the rows go (`purge_departed`), in the
    language the page was in when they pressed Delete, and never to an account still
    inside its seven days. A recording mailer: nothing is sent anywhere."""
    from targum.accounts import GRACE_DAYS, Store, now
    from targum.serve import Library

    sent: list[tuple[str, str, str]] = []

    class Recording:
        def send(self, to: str, link: str, language: str = "en") -> None:
            raise AssertionError("no sign-in link here")

        def notify(
            self,
            to: str,
            subject: str,
            body: str,
            headers: Any = None,
            html: str | None = None,
        ) -> None:
            sent.append((to, subject, body))

    store = Store(tmp_path / "targum.db")
    for address in ("gone@example.com", "staying@example.com"):
        store.start_sign_in(address)
    gone = store.person_by_email("gone@example.com")
    staying = store.person_by_email("staying@example.com")
    assert gone is not None and staying is not None
    store.forget(gone, "ru-RU")
    store.forget(staying, "en")
    with store.write() as db:
        stale = now() - (GRACE_DAYS + 1) * 24 * 60 * 60 * 1000
        db.execute("UPDATE person SET leaving = ? WHERE id = ?", (stale, gone.id))

    Library(tmp_path / "out", store=store, mailer=Recording(), address=SITE)

    assert [(to, subject) for to, subject, _ in sent] == [
        ("gone@example.com", "Ваш аккаунт targum удалён")
    ]
    assert "14 дней" in sent[0][2]
    assert store.person_by_email("gone@example.com") is None
    sent.clear()
    Library(tmp_path / "out", store=store, mailer=Recording(), address=SITE)
    assert sent == [], "once"


def test_the_purge_runs_every_night_and_mails_once(tmp_path: Path) -> None:
    """The server purges at `PURGE_AT_HOUR` UTC every night, not only on a restart, and a
    second night with nobody new deletes and mails nothing. A recording mailer, and a wait
    that returns at once: nothing is sent and nothing sleeps."""
    from datetime import UTC, datetime

    from targum.accounts import GRACE_DAYS, Store, now
    from targum.serve import PURGE_AT_HOUR, Library, keep_purging

    sent: list[str] = []

    class Recording:
        def send(self, to: str, link: str, language: str = "en") -> None:
            raise AssertionError("no sign-in link here")

        def notify(
            self,
            to: str,
            subject: str,
            body: str,
            headers: Any = None,
            html: str | None = None,
        ) -> None:
            sent.append(to)

    store = Store(tmp_path / "targum.db")
    store.start_sign_in("night@example.com")
    person = store.person_by_email("night@example.com")
    assert person is not None
    store.forget(person, "en")
    library = Library(tmp_path / "out", store=store, mailer=Recording(), address=SITE)
    home = library.home(person)
    home.mkdir(parents=True, exist_ok=True)
    assert sent == [], "inside the seven days at start-up"

    # The seven days run out while the server is up.
    with store.write() as db:
        stale = now() - (GRACE_DAYS + 1) * 24 * 60 * 60 * 1000
        db.execute("UPDATE person SET leaving = ? WHERE id = ?", (stale, person.id))

    waited: list[float] = []
    evening = datetime(2026, 10, 9, 21, 30, tzinfo=UTC)
    keep_purging(library, wait=waited.append, clock=lambda: evening, nights=2)

    assert waited == [(24 + PURGE_AT_HOUR - 21.5) * 3600] * 2
    assert sent == ["night@example.com"], "deleted and mailed once, over two nights"
    assert store.person_by_email("night@example.com") is None
    assert not home.exists()
    assert library.purge_departed() == [], "and again by hand: nothing"
    assert sent == ["night@example.com"]


def test_the_next_purge_is_never_now() -> None:
    from datetime import UTC, datetime, timedelta, timezone

    from targum.serve import until_next

    at = datetime(2026, 10, 9, 3, 0, tzinfo=UTC)
    assert until_next(3, at) == 24 * 3600, "on the hour, it waits for tomorrow's"
    assert until_next(3, at - timedelta(minutes=1)) == 60
    israel = timezone(timedelta(hours=3))
    assert until_next(3, datetime(2026, 10, 9, 5, 0, tzinfo=israel)) == 60 * 60


def test_a_hosted_server_purges_nightly() -> None:
    """`targum serve` turns the nightly purge on wherever it is hosted, as it does the
    subscriptions loop; the suite's servers never start it."""
    import inspect

    from targum import cli
    from targum.serve import start

    assert "keep_purging_nightly=hosted" in inspect.getsource(cli.serve)
    assert inspect.signature(start).parameters["keep_purging_nightly"].default is False
