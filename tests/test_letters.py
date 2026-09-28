"""What every mail says, and that none of it fetches anything.

design.md §12, "Mail is drawn, and fetches nothing" (2026-09-27): each of the seven mails a
reader can receive is plain text and the same words drawn as HTML on the desk's frame,
with the logo drawn in table cells rather than loaded. Nothing in the HTML reaches for the
network: no image, no stylesheet, no font, no pixel, no redirect.
"""

from __future__ import annotations

import io
import re
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
        "series": letters.series_instalment(
            series.said_in(PORTION, language), SITE, "stop2", language
        ),
        "ready": letters.build_ready(
            "Shakshuka at home", f"{SITE}/reader/x", SITE, language, asked=False, listen=False
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
        # The mark's two columns in its own paper values, and the wordmark as text.
        assert 'bgcolor="#201e1b"' in letter.html and 'bgcolor="#a5824f"' in letter.html
        assert ">targum</td>" in letter.html


def test_only_the_lists_carry_list_headers() -> None:
    for name, letter in every("en").items():
        listed = name in ("weekly", "series")
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
    for name in ("weekly", "series"):
        assert "1 Somewhere St" in after[name].text and "1 Somewhere St" in after[name].html
    for name in ("sign-in", "ready", "invitation"):
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


def test_a_ready_mail_s_button_says_what_the_subject_does() -> None:
    """Copy audit, 2026-09-28 (Q28), and §6: "Open" under "Ready to watch" named no
    action. The button's verb is chosen as the subject's is."""
    for listen, watch, verb in (
        (False, False, "Read"),
        (True, False, "Listen"),
        (True, True, "Watch"),
    ):
        mail = letters.build_ready(
            "Ruth", f"{SITE}/r", SITE, "en", asked=False, listen=listen, watch=watch
        )
        assert f">{verb}<" in mail.html, verb
        assert ">Open<" not in mail.html
    russian = letters.build_ready("Ruth", f"{SITE}/r", SITE, "ru", asked=False, listen=True)
    assert ">Слушать<" in russian.html


def test_a_daily_series_is_never_mailed(tmp_path: Any) -> None:
    """Its instalment lands on Learn and in the bell; a mail every day is the ping a
    reader deletes an app over (design.md §12, 2026-09-27)."""
    store = Store(tmp_path / "words.db")
    store.follow_series("a@example.org", "tehillim")
    store.follow_series("a@example.org", "parasha")
    box = io.StringIO()
    report = series.announce(store, ConsoleMailer(box), SITE, [TEHILLIM, PORTION], pause=0)
    assert report.sent == ["a@example.org"], "the portion, once"
    assert "Daily Tehillim" not in box.getvalue()


def test_every_daily_cycle_says_it_is_daily() -> None:
    from targum.daily.cycles import CYCLES

    ids = {cycle.slug for cycle in CYCLES}
    rows = [row for row in series.current(public=True) if row["id"] in ids]
    assert rows and all(not series.mailed(row) for row in rows)
    assert series.mailed(PORTION)
