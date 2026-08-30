"""Getting a sign-in link to the person who asked for it.

Two ways, and which one is in use is decided by whether anything is configured. On a
machine someone is running targum on themselves, the console *is* the delivery: the
link appears in the same window they started the server in, which is faster than any
email and needs no account anywhere. Once there is a hosted install, SMTP settings in
the environment switch it over with nothing else changing.

The interesting property is that the caller cannot tell the difference. `send` either
delivers or raises, and the page above it says "check your email" either way — so the
route that mints a link never learns whether the address exists, which is the same
reason the sign-in page says the same thing to a known address and an unknown one.
"""

from __future__ import annotations

import contextlib
import os
import smtplib
import sys
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from email.message import EmailMessage
from typing import Protocol, TextIO

SUBJECT = "Your targum sign-in link"

# Plain text, no HTML, no tracking pixel, no logo. It is a link and a sentence; anything
# more is a thing to maintain and a reason to land in a spam folder.
BODY = """Here is your link back into targum:

{link}

It works once, and it stops working in twenty minutes. If you did not ask for it,
nothing has happened to your account and you can ignore this.
"""


class Mailer(Protocol):
    def send(self, to: str, link: str) -> None: ...

    def notify(
        self, to: str, subject: str, body: str, headers: Mapping[str, str] | None = None
    ) -> None:
        """A plain message that is not a sign-in link: a build that finished while
        the reader was away, or the week's issue. Same delivery, same plain text.

        `headers` exists for one thing — RFC 8058's `List-Unsubscribe` pair, which is
        what lets a mail client offer its own unsubscribe button. Without it a reader
        who wants out has the report-as-spam button to hand instead, and enough of those
        cost the sending domain its reputation, which takes the sign-in link down with
        it. Optional, so every existing caller is unaffected.
        """
        ...


@dataclass
class ConsoleMailer:
    """Writes the link where someone running targum themselves will see it.

    Not a stub for a real mailer: for a local install this is the whole feature, and
    it is better than email because there is no round trip and nothing to configure.
    """

    stream: TextIO | None = None

    def send(self, to: str, link: str) -> None:
        out = self.stream if self.stream is not None else sys.stdout
        out.write(
            f"\n  Sign-in link for {to}:\n  {link}\n"
            "  It works once, and only for the next twenty minutes.\n\n"
        )
        out.flush()

    def notify(
        self, to: str, subject: str, body: str, headers: Mapping[str, str] | None = None
    ) -> None:
        out = self.stream if self.stream is not None else sys.stdout
        out.write(f"\n  To {to} — {subject}\n  {body.strip()}\n\n")
        out.flush()


@dataclass
class SmtpMailer:
    """For a hosted install, once there is a provider behind it."""

    host: str
    port: int
    user: str
    password: str
    sender: str

    #: The connection a mailout is holding open, if one is. Not a constructor argument:
    #: it is the state of a `session()`, and outside one this is None and every message
    #: opens and closes its own, exactly as before.
    _open: smtplib.SMTP | None = field(default=None, repr=False)

    def send(self, to: str, link: str) -> None:
        self._deliver(to, SUBJECT, BODY.format(link=link))

    def notify(
        self, to: str, subject: str, body: str, headers: Mapping[str, str] | None = None
    ) -> None:
        self._deliver(to, subject, body, headers)

    @contextmanager
    def session(self) -> Iterator[None]:
        """Hold one connection open across a mailout.

        Without it every address costs a fresh TCP connection, a STARTTLS handshake and
        a login. Two hundred subscribers is two hundred of each, which is slow enough to
        matter and looks enough like a script to be rate-limited by the provider.
        """
        server = smtplib.SMTP(self.host, self.port, timeout=20)
        try:
            server.starttls()
            if self.user:
                server.login(self.user, self.password)
            self._open = server
            yield
        finally:
            self._open = None
            with contextlib.suppress(smtplib.SMTPException, OSError):
                server.quit()

    def _deliver(
        self, to: str, subject: str, body: str, headers: Mapping[str, str] | None = None
    ) -> None:
        note = EmailMessage()
        note["Subject"] = subject
        note["From"] = self.sender
        note["To"] = to
        for name, value in (headers or {}).items():
            note[name] = value
        # Sent as 7-bit rather than quoted-printable, which is the default and which
        # wraps at 76 characters. A sign-in link is 79: quoted-printable puts a soft
        # break inside the token, and although a correct client rejoins it, plenty of
        # them linkify only as far as the break — which is a link that does not work,
        # in the one email where that is the whole product failing. The body is ASCII
        # and short, and `test_the_link_is_never_wrapped` is what keeps it that way.
        # A title in the body may not be ASCII; the encoder falls back on its own.
        try:
            note.set_content(body, cte="7bit")
        except (UnicodeEncodeError, ValueError):
            note.set_content(body)
        if self._open is not None:
            self._open.send_message(note)
            return
        with smtplib.SMTP(self.host, self.port, timeout=20) as server:
            server.starttls()
            if self.user:
                server.login(self.user, self.password)
            server.send_message(note)


def from_environment() -> Mailer:
    """SMTP if it is configured, the console if it is not.

    Deliberately silent about which: a local install should not be nagged about an
    email provider it does not need.
    """
    host = os.environ.get("TARGUM_SMTP_HOST", "").strip()
    if not host:
        return ConsoleMailer()
    return SmtpMailer(
        host=host,
        port=int(os.environ.get("TARGUM_SMTP_PORT", "587")),
        user=os.environ.get("TARGUM_SMTP_USER", ""),
        password=os.environ.get("TARGUM_SMTP_PASSWORD", ""),
        sender=os.environ.get("TARGUM_SMTP_FROM", "targum <no-reply@localhost>"),
    )
