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

import os
import smtplib
import sys
from dataclasses import dataclass
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


@dataclass
class SmtpMailer:
    """For a hosted install, once there is a provider behind it."""

    host: str
    port: int
    user: str
    password: str
    sender: str

    def send(self, to: str, link: str) -> None:
        note = EmailMessage()
        note["Subject"] = SUBJECT
        note["From"] = self.sender
        note["To"] = to
        # Sent as 7-bit rather than quoted-printable, which is the default and which
        # wraps at 76 characters. A sign-in link is 79: quoted-printable puts a soft
        # break inside the token, and although a correct client rejoins it, plenty of
        # them linkify only as far as the break — which is a link that does not work,
        # in the one email where that is the whole product failing. The body is ASCII
        # and short, and `test_the_link_is_never_wrapped` is what keeps it that way.
        note.set_content(BODY.format(link=link), cte="7bit")
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
