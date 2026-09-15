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


def sent(subject: str, body: str) -> bytes:
    """What an `SmtpMailer` really puts on the wire, through its own `_deliver`.

    `compose` above rebuilds the message the way the mailer does, which tests the
    intention; this holds the mailer to it.
    """
    from targum.mail import SmtpMailer

    kept: list[object] = []

    class Session:
        def send_message(self, note: object) -> None:
            kept.append(note)

    mailer = SmtpMailer("smtp.example.com", 587, "u", "p", "targum <hello@targum.page>")
    object.__setattr__(mailer, "_open", Session())
    mailer.notify("reader@example.com", subject, body)
    return kept[0].as_bytes()  # type: ignore[attr-defined]


def test_a_link_in_a_russian_email_arrives_in_one_piece() -> None:
    """The email targum sends in a language that is not English (targum-internal#186).

    Non-ASCII cannot go 7-bit, and what it falls back to decides whether the link works.
    Unnamed, the encoder picks 8bit — raw UTF-8 on the wire, safe only where the whole
    path advertises 8BITMIME. Quoted-printable is safe and puts a soft break back inside
    the token. Base64 is safe and does not, because a client decodes it whole first.
    """
    import base64

    token = secrets.token_urlsafe(32)
    link = f"https://targum.page/account/enter?t={token}"
    raw = sent("Ваша ссылка для входа", f"Вот ваша ссылка:\n\n{link}\n")

    assert all(byte < 128 for byte in raw), "8-bit on the wire needs 8BITMIME end to end"
    # `as_bytes` ends its lines with a bare newline, so the blank line is found rather
    # than assumed to be CRLF.
    separator = b"\r\n\r\n" if b"\r\n\r\n" in raw else b"\n\n"
    head, _, encoded = raw.partition(separator)
    assert b"base64" in head.lower(), head
    assert link in base64.b64decode(encoded).decode(), "the token did not survive decoding"


def test_a_subject_that_is_not_latin_is_encoded_for_the_header() -> None:
    """RFC 2047, which `EmailMessage` does on its own — pinned because the day it stops
    being true is the day a Russian reader gets a subject line of mojibake."""
    raw = sent("Ваша ссылка для входа", "text\n")
    assert b"=?utf-8?" in raw, "the subject went out unencoded"
    assert all(byte < 128 for byte in raw)


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


def test_a_finished_build_is_said_plainly_on_the_console() -> None:
    import io

    out = io.StringIO()
    ConsoleMailer(out).notify(
        "reader@example.com", "Ruth is ready", "Ruth is ready to read.\n\nhttp://x\n"
    )
    said = out.getvalue()
    assert "reader@example.com" in said and "Ruth is ready" in said and "http://x" in said


def test_the_link_is_sent_in_the_language_the_person_reads(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Subject and body come from the catalogue in the language asked, and a language
    that has not filled a key yet is sent that key in English (targum-internal#186)."""
    from targum import strings

    real = strings.catalogue

    def catalogue(language: str) -> dict[str, str]:
        if language == "ru":
            return {"mail.sign_in.subject": "Ваша ссылка для входа в targum"}
        return real(language)

    monkeypatch.setattr(strings, "catalogue", catalogue)
    sent: list[tuple[str, str]] = []
    mailer = SmtpMailer(host="h", port=587, user="u", password="p", sender="s")
    monkeypatch.setattr(
        mailer, "_deliver", lambda to, subject, body, headers=None: sent.append((subject, body))
    )

    mailer.send("reader@example.com", "https://targum.page/account/enter?t=x", language="ru")
    mailer.send("reader@example.com", "https://targum.page/account/enter?t=x")
    assert sent[0][0] == "Ваша ссылка для входа в targum"
    assert "https://targum.page/account/enter?t=x" in sent[0][1], "English body, link filled"
    assert sent[1] == (SUBJECT, BODY.format(link="https://targum.page/account/enter?t=x"))


def test_the_sign_in_link_is_sent_in_russian_to_a_reader_who_reads_russian() -> None:
    """The catalogue's Russian (targum-internal#186, #185): the subject and the body in
    Russian, lowercase targum, and the link whole through base64 on the wire."""
    import base64
    from email import message_from_bytes
    from email.header import decode_header, make_header

    kept: list[object] = []

    class Session:
        def send_message(self, note: object) -> None:
            kept.append(note)

    mailer = SmtpMailer("smtp.example.com", 587, "u", "p", "targum <hello@targum.page>")
    object.__setattr__(mailer, "_open", Session())
    link = f"https://targum.page/account/enter?t={secrets.token_urlsafe(32)}"
    mailer.send("reader@example.com", link, language="ru")
    raw = kept[0].as_bytes()  # type: ignore[attr-defined]

    assert all(byte < 128 for byte in raw), "8-bit on the wire needs 8BITMIME end to end"
    note = message_from_bytes(raw)
    subject = str(make_header(decode_header(note["Subject"])))
    assert subject == "Ваша ссылка для входа в targum"
    body = base64.b64decode(note.get_payload()).decode()
    assert link in body and "targum" in body and "Targum" not in body
    assert "!" not in subject + body, "design.md §6: no exclamation marks"
