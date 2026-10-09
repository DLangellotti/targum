"""Every mail, drawn from sample data, for looking at (design.md §12, "Every mail is the
board's", 2026-10-09).

A mail is HTML nobody sees until it lands in an inbox, which made it the one surface the
boards could not be compared with. `targum mails --out DIR` writes each of these as an
HTML page and its text half, in every language the catalogue has, and sends nothing: no
mailer is constructed and no address is real. The tests draw the same set, so a mail that
stops rendering fails there before anybody opens a browser.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

from . import letters
from .letters import Letter
from .strings import text

if TYPE_CHECKING:
    from .weekly.models import Issue

#: Where the links point. Not a real address of anybody's: the sample is the site's own.
SITE = "https://targum.page"


def _issue() -> Issue:
    from .weekly.models import Edition, Issue, Level, State, entry_id, folder

    week = "2026-w39"
    return Issue(
        id=week,
        dated="2026-09-21",
        title="מבט השבוע",
        blurb=(
            "שבוע של יום קטלני בכבישים, איומים הדדיים בין וושינגטון לטהרן, "
            "ופרידה מעיתונאי ותיק בפריז."
        ),
        state=State.published,
        editions=[
            Edition(
                level=level, entry_id=entry_id(week, level), folder=folder(week, level), ok=True
            )
            for level in Level
        ],
    )


def samples(language: str = "en") -> dict[str, Letter]:
    """Each mail a reader can receive, with the board's sample data, in `language`."""
    from .accounts import GRACE_DAYS
    from .backup import KEEP

    issue = _issue()
    if language == "ru":
        ready = letters.build_ready(
            "Отец Сергий",
            f"{SITE}/reader/otets-sergii/reader/index.html",
            SITE,
            language,
            asked=False,
            listen=True,
            title_language="ru",
            parts=9,
            seconds=0,
        )
    else:
        ready = letters.build_ready(
            "האם החשמונאים המציאו את היהדות?",
            f"{SITE}/reader/hashmonaim/reader/index.html",
            SITE,
            language,
            asked=False,
            listen=True,
            watch=True,
            title_language="he",
            parts=4,
            seconds=24 * 60,
        )
    return {
        "sign-in": letters.sign_in(f"{SITE}/account/enter?t=one-time-token", language),
        "waitlist": letters.waitlist_confirm(f"{SITE}/waitlist/confirm?t=token", language),
        "invitation": letters.invitation(SITE, language, connector=True),
        "weekly-confirm": letters.weekly_confirm(f"{SITE}/weekly/confirm?t=token", language),
        "weekly": letters.weekly_issue(issue, SITE, "stop-token", language),
        "daily": letters.subscriptions_daily(
            [
                {
                    "name": "כאן ארכיון",
                    "stop": "stop-kan",
                    "rows": [
                        (
                            "פלאפל או מקדונלדס?",
                            "he",
                            text("mail.daily.ready-watch", language),
                            "/reader/kan-falafel/reader/index.html",
                        ),
                    ],
                },
                {
                    "name": "Daily Tehillim" if language == "en" else "Псалмы на каждый день",
                    "stop": "stop-tehillim",
                    "rows": [
                        (
                            "תהלים קכ–קלד",
                            "he",
                            text("mail.daily.ready-read", language),
                            "/tehillim/read/27/",
                        ),
                    ],
                },
                {
                    "name": "Sport" if language == "en" else "Спорт",
                    "stop": "stop-sport",
                    "rows": [
                        (
                            "הפועל חולון אלופת המדינה בכדורסל",
                            "he",
                            text("mail.daily.link", language),
                            "/add?source=https%3A%2F%2Ftargum.page%2Fa",
                        ),
                    ],
                },
            ],
            SITE,
            "t=stop-kan&t=stop-tehillim&t=stop-sport",
            language,
        ),
        "ready": ready,
        "deleted": letters.account_deleted(
            SITE, date(2026, 10, 8), language, grace_days=GRACE_DAYS, backups_kept=KEEP
        ),
    }


def write(out: Path, languages: list[str]) -> list[Path]:
    """Each sample as `<name>.<language>.html` and `.txt` in `out`, and an index page that
    shows them side by side. Returns the HTML files written."""
    import html

    out.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    rows: list[str] = []
    for language in languages:
        for name, letter in samples(language).items():
            page = out / f"{name}.{language}.html"
            page.write_text(letter.html, encoding="utf-8")
            (out / f"{name}.{language}.txt").write_text(
                f"Subject: {letter.subject}\n"
                + "".join(f"{key}: {value}\n" for key, value in letter.headers.items())
                + "\n"
                + letter.text,
                encoding="utf-8",
            )
            written.append(page)
            rows.append(
                f'<li><a href="{page.name}">{html.escape(name)} · {language}</a> — '
                f"{html.escape(letter.subject)}</li>"
            )
    (out / "index.html").write_text(
        '<!doctype html><meta charset="utf-8"><title>targum mails</title><ul>'
        + "".join(rows)
        + "</ul>\n",
        encoding="utf-8",
    )
    return written
