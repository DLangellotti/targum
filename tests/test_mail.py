"""The one email targum sends, and the ways it silently fails.

A sign-in link that arrives broken is the whole product failing at the door, and it
fails for one reader in ten rather than all of them, which is the hardest kind to
notice.
"""

from __future__ import annotations

import re
import secrets

from targum.mail import BODY, SUBJECT, ConsoleMailer, SmtpMailer, from_environment


def compose(link: str) -> str:
    """The message an SmtpMailer would hand to a server, without a server."""
    from email.message import EmailMessage

    note = EmailMessage()
    note["Subject"] = SUBJECT
    note["From"] = "targum <hello@targum.page>"
    note["To"] = "reader@example.com"
    note.set_content(BODY.format(link=link), cte="7bit")
    return note.as_string()


def test_the_link_is_never_wrapped() -> None:
    """Quoted-printable wraps at 76 characters and a real link is 79.

    It put a soft break inside the token. A correct client rejoins it; a great many
    linkify only up to the break and hand the reader a link that cannot work.
    """
    token = secrets.token_urlsafe(32)
    link = f"https://targum.page/account/enter?t={token}"
    assert len(link) > 76, "if links got shorter, this test is no longer proving anything"

    raw = compose(link)
    assert link in raw, "the link does not survive encoding in one piece"
    for line in raw.splitlines():
        assert not line.endswith("="), f"soft-wrapped line: {line!r}"


def test_nothing_in_the_message_needs_encoding() -> None:
    """7-bit is only safe while the text is ASCII, and an em-dash would break it."""
    for text in (SUBJECT, BODY):
        assert text.isascii(), f"non-ASCII in {text[:40]!r} — 7-bit will fail"


def test_it_is_plain_text_with_nothing_to_track() -> None:
    raw = compose("https://targum.page/account/enter?t=x").lower()
    assert "<html" not in raw and "<img" not in raw
    assert "text/plain" in raw


def test_the_console_is_the_delivery_when_nothing_is_configured(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    for name in ("TARGUM_SMTP_HOST", "TARGUM_SMTP_PORT", "TARGUM_SMTP_USER"):
        monkeypatch.delenv(name, raising=False)
    assert isinstance(from_environment(), ConsoleMailer)


def test_smtp_takes_over_once_a_host_is_set(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("TARGUM_SMTP_HOST", "smtp.resend.com")
    monkeypatch.setenv("TARGUM_SMTP_USER", "resend")
    monkeypatch.setenv("TARGUM_SMTP_FROM", "targum <hello@targum.page>")
    mailer = from_environment()
    assert isinstance(mailer, SmtpMailer)
    assert mailer.host == "smtp.resend.com"
    assert mailer.port == 587
    assert mailer.sender == "targum <hello@targum.page>"


def test_the_console_says_the_link_once_and_plainly() -> None:
    import io

    stream = io.StringIO()
    ConsoleMailer(stream=stream).send("reader@example.com", "https://targum.page/x?t=y")
    said = stream.getvalue()
    assert said.count("https://targum.page/x?t=y") == 1
    assert "reader@example.com" in said
    assert not re.search(r"[\U0001F300-\U0001FAFF]", said), "no emoji, per the guidelines"
