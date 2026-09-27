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
from email.utils import formatdate, make_msgid, parseaddr
from typing import Protocol, TextIO

from .strings import text

# Every mail is plain text and the same words drawn as HTML, sent as multipart/alternative
# (design.md §12, "Mail is drawn, and fetches nothing", 2026-09-27). It was plain text only
# until then. The HTML carries no image, no remote stylesheet or font, no pixel and no
# redirecting link; `letters.py` composes both halves from one list of blocks. The subject
# is the English, kept for what reads it here.
SUBJECT = text("mail.sign_in.subject")

#: Who a mail is from when nothing says otherwise, and where a reply goes. A reply is
#: asked for in the invitation, so the address has to be one somebody reads.
SENDER = "targum <hello@targum.page>"


class Mailer(Protocol):
    def send(self, to: str, link: str, language: str = "en") -> None:
        """The sign-in link, in `language` where the catalogue has it and English where not."""
        ...

    def notify(
        self,
        to: str,
        subject: str,
        body: str,
        headers: Mapping[str, str] | None = None,
        html: str | None = None,
    ) -> None:
        """A message that is not a sign-in link: a build that finished while the reader
        was away, or the week's issue. `body` is the plain text, always sent; `html` is
        the same words drawn, sent beside it as the alternative where given.

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

    def send(self, to: str, link: str, language: str = "en") -> None:
        # The console is the operator's own window, so it stays in English whoever asked.
        out = self.stream if self.stream is not None else sys.stdout
        out.write(
            f"\n  Sign-in link for {to}:\n  {link}\n"
            "  It works once, and only for the next twenty minutes.\n\n"
        )
        out.flush()

    def notify(
        self,
        to: str,
        subject: str,
        body: str,
        headers: Mapping[str, str] | None = None,
        html: str | None = None,
    ) -> None:
        # The console is read in a terminal: the text half is the whole of it.
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
    sender: str = SENDER
    #: Where a reply goes. Empty means the sender's own address.
    reply_to: str = ""

    #: The connection a mailout is holding open, if one is. Not a constructor argument:
    #: it is the state of a `session()`, and outside one this is None and every message
    #: opens and closes its own, exactly as before.
    _open: smtplib.SMTP | None = field(default=None, repr=False)

    def send(self, to: str, link: str, language: str = "en") -> None:
        from .letters import sign_in

        letter = sign_in(link, language)
        self._deliver(to, letter.subject, letter.text, letter.headers, letter.html)

    def notify(
        self,
        to: str,
        subject: str,
        body: str,
        headers: Mapping[str, str] | None = None,
        html: str | None = None,
    ) -> None:
        self._deliver(to, subject, body, headers, html)

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
        self,
        to: str,
        subject: str,
        body: str,
        headers: Mapping[str, str] | None = None,
        html: str | None = None,
    ) -> None:
        note = EmailMessage()
        note["Subject"] = subject
        note["From"] = self.sender
        note["To"] = to
        note["Reply-To"] = self.reply_to or self.sender
        # smtplib adds neither, and a message without a Message-ID reads as a script to a
        # spam filter. The id is under the sender's own domain.
        note["Date"] = formatdate(usegmt=True)
        domain = parseaddr(self.sender)[1].rpartition("@")[2] or None
        note["Message-ID"] = make_msgid(domain=domain)
        for name, value in (headers or {}).items():
            note[name] = value
        # Sent as 7-bit rather than quoted-printable, which is the default and which
        # wraps at 76 characters. A sign-in link is 79: quoted-printable puts a soft
        # break inside the token, and although a correct client rejoins it, plenty of
        # them linkify only as far as the break — which is a link that does not work,
        # in the one email where that is the whole product failing. The body is ASCII
        # and short, and `test_the_link_is_never_wrapped` is what keeps it that way.
        # A title in the body may not be ASCII, and every word of a Russian or Hebrew
        # email is (targum-internal#186). Base64 for that, named rather than left to the
        # encoder: unnamed it picks 8bit, which is raw UTF-8 on the wire and only safe
        # where the whole SMTP path advertises 8BITMIME. Quoted-printable is 7-bit safe
        # and puts the soft break back inside the token, which is the failure the line
        # above exists to avoid. Base64 wraps too, and a client decodes it whole before
        # it looks for a link, so the token arrives in one piece.
        try:
            note.set_content(body, cte="7bit")
        except (UnicodeEncodeError, ValueError):
            note.set_content(body, cte="base64")
        if html:
            # Base64 for the HTML always, for the same reason: its links must arrive
            # whole, and quoted-printable would break them at 76 characters.
            note.add_alternative(html, subtype="html", cte="base64")
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
        sender=os.environ.get("TARGUM_SMTP_FROM", "").strip() or SENDER,
        reply_to=os.environ.get("TARGUM_SMTP_REPLY_TO", "").strip(),
    )
