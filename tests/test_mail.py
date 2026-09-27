"""Delivering mail, and the ways it silently fails.

A sign-in link that arrives broken is the whole product failing at the door, and it
fails for one reader in ten rather than all of them, which is the hardest kind to
notice. What each mail says, and that none of it fetches anything, is `test_letters.py`.
"""

from __future__ import annotations

import re
import secrets

from targum.mail import SUBJECT, ConsoleMailer, SmtpMailer, from_environment


def signed_in(link: str, language: str = "en") -> bytes:
    """The sign-in mail exactly as an `SmtpMailer` puts it on the wire, without a server."""
    kept: list[object] = []

    class Session:
        def send_message(self, note: object) -> None:
            kept.append(note)

    mailer = SmtpMailer("smtp.example.com", 587, "u", "p", "targum <hello@targum.page>")
    object.__setattr__(mailer, "_open", Session())
    mailer.send("reader@example.com", link, language=language)
    return kept[0].as_bytes()  # type: ignore[attr-defined]


def parts(raw: bytes) -> dict[str, str]:
    """Each part of a message by its content type, decoded."""
    from email import message_from_bytes

    out: dict[str, str] = {}
    for part in message_from_bytes(raw).walk():
        if part.get_content_maintype() == "text":
            payload = part.get_payload(decode=True)
            assert isinstance(payload, bytes)
            out[part.get_content_type()] = payload.decode(part.get_content_charset() or "utf-8")
    return out


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
    linkify only up to the break and hand the reader a link that cannot work. Both halves
    of the mail go as base64, which a client decodes whole before it looks for a link.
    """
    token = secrets.token_urlsafe(32)
    link = f"https://targum.page/account/enter?t={token}"
    assert len(link) > 76, "if links got shorter, this test is no longer proving anything"

    raw = signed_in(link)
    assert b"quoted-printable" not in raw.lower()
    said = parts(raw)
    assert link in said["text/plain"], "the link does not survive encoding in one piece"
    assert f'href="{link}"' in said["text/html"]
    assert link + "\n" in said["text/plain"], "the link has a line of its own"


def test_the_english_subject_needs_no_encoding() -> None:
    assert SUBJECT.isascii()


def test_every_mail_has_a_text_part_and_a_drawn_one() -> None:
    """design.md §12, "Mail is drawn, and fetches nothing": plain text first, HTML as the
    alternative, so a client that shows no HTML still has the whole message."""
    raw = signed_in("https://targum.page/account/enter?t=x")
    head = raw.split(b"\n\n", 1)[0].lower()
    assert b"multipart/alternative" in head
    said = parts(raw)
    assert set(said) == {"text/plain", "text/html"}
    assert raw.lower().index(b"text/plain") < raw.lower().index(b"text/html"), "text first"


def test_a_mail_names_its_date_its_id_and_where_a_reply_goes() -> None:
    """smtplib adds neither a Date nor a Message-ID, and a mail without them reads as a
    script to a spam filter. The reply goes to the sender unless told otherwise, because
    the invitation asks for one."""
    from email import message_from_bytes

    note = message_from_bytes(signed_in("https://targum.page/account/enter?t=x"))
    assert note["Date"]
    assert note["Message-ID"].endswith("@targum.page>")
    assert note["Reply-To"] == "targum <hello@targum.page>"
    assert note["From"] == "targum <hello@targum.page>"
    assert note["List-Unsubscribe"] is None, "a sign-in link is not a list"


def test_the_sender_is_hello_at_targum_page_unless_told(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("TARGUM_SMTP_HOST", "smtp.resend.com")
    monkeypatch.delenv("TARGUM_SMTP_FROM", raising=False)
    monkeypatch.delenv("TARGUM_SMTP_REPLY_TO", raising=False)
    mailer = from_environment()
    assert isinstance(mailer, SmtpMailer)
    assert mailer.sender == "targum <hello@targum.page>"
    assert "localhost" not in mailer.sender
    monkeypatch.setenv("TARGUM_SMTP_REPLY_TO", "david@targum.page")
    mailer = from_environment()
    assert isinstance(mailer, SmtpMailer) and mailer.reply_to == "david@targum.page"


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
        mailer, "_deliver", lambda to, subject, body, *rest: sent.append((subject, body))
    )

    mailer.send("reader@example.com", "https://targum.page/account/enter?t=x", language="ru")
    mailer.send("reader@example.com", "https://targum.page/account/enter?t=x")
    assert sent[0][0] == "Ваша ссылка для входа в targum"
    assert "https://targum.page/account/enter?t=x" in sent[0][1], "English body, link filled"
    assert "Press the button to sign in" in sent[0][1], "the gaps are said in English"
    assert sent[1][0] == SUBJECT
    assert "https://targum.page/account/enter?t=x" in sent[1][1]


def test_the_sign_in_link_is_sent_in_russian_to_a_reader_who_reads_russian() -> None:
    """The catalogue's Russian (targum-internal#186, #185): the subject and the body in
    Russian, lowercase targum, and the link whole through base64 on the wire."""
    from email import message_from_bytes
    from email.header import decode_header, make_header

    link = f"https://targum.page/account/enter?t={secrets.token_urlsafe(32)}"
    raw = signed_in(link, "ru")

    assert all(byte < 128 for byte in raw), "8-bit on the wire needs 8BITMIME end to end"
    note = message_from_bytes(raw)
    subject = str(make_header(decode_header(note["Subject"])))
    assert subject == "Ваша ссылка для входа в targum"
    said = parts(raw)
    body = said["text/plain"]
    assert link in body and "targum" in body and "Targum" not in body
    assert "Войти" in said["text/html"] and 'lang="ru"' in said["text/html"]
    assert "!" not in subject + body, "design.md §6: no exclamation marks"
