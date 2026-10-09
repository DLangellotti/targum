"""What each email says, and the one frame every one of them is drawn in.

Every mail a reader can receive is composed here: the sign-in link, the two double
opt-ins (the waitlist's and the Weekly News Digest's), the invitation off the waitlist,
the digest itself, a followed series' instalment, and a build that finished while the
reader was away. `mail.py` delivers; this decides the words and the shape.

Each is a `Letter`: a subject, a plain-text body, the same body as HTML, and the headers
it needs. The two bodies are made from one list of blocks, so they cannot say different
things. The mail goes as multipart/alternative, plain text first.

**The HTML fetches nothing** (design.md §12, "Mail is drawn, and fetches nothing").
There are no images, no remote stylesheets or fonts, no tracking pixel and no redirecting
links. The logo is drawn rather than loaded: the mark's two columns are table cells with
a background colour, and the wordmark is live text in the reading face. That survives a
client that blocks images, because there is no image to block. The colours are §13's
desk, card, ink and teal, and the scheme is declared light only, because there is one
look (§12, 2026-09-19).

The words come from the strings catalogue in the reader's language. English is the
fallback.
"""

from __future__ import annotations

import html
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit

from .strings import counted, said_date, text

if TYPE_CHECKING:
    from .weekly.models import Issue

#: A postal address for the foot of the list mails (the digest and the series). Empty
#: until one is given, and an empty one draws nothing.
POSTAL_ENV = "TARGUM_POSTAL_ADDRESS"

# §4 and §13, written out because a mail cannot read `reader.css`.
DESK = "#ece7de"
CARD = "#fffdf9"
RAISED = "#f3efe7"
INK = "#1c1a17"
MUTED = "#6b645c"
RULE = "#e2dcd1"
TEAL = "#1f6f6b"
PAPER = "#fbf9f5"
MARK_INK = "#201e1b"
MARK_ACCENT = "#a5824f"

SANS = "'Source Sans 3','Segoe UI',system-ui,-apple-system,Roboto,Helvetica,Arial,sans-serif"
SERIF = "'Iowan Old Style','Palatino Linotype',Palatino,Georgia,serif"
HEBREW = "'Taamey Frank CLM','Frank Ruehl CLM','Times New Roman',David,serif"
MONO = "ui-monospace,Menlo,Consolas,monospace"

#: RFC 8058. The URL in `List-Unsubscribe` must stop the mail on a POST with this body,
#: with no page in between.
ONE_CLICK = "List-Unsubscribe=One-Click"


@dataclass(frozen=True)
class Letter:
    subject: str
    text: str
    html: str
    headers: Mapping[str, str] = field(default_factory=dict)


# -- blocks ------------------------------------------------------------------------------
#
# Each block is drawn twice, as text and as HTML, by the same object.


def _e(value: str) -> str:
    return html.escape(value, quote=True)


def isolate(value: str) -> str:
    """A title that may be Hebrew, inside English: U+2068 … U+2069 (§12, 2026-09-14)."""
    return f"⁨{value}⁩"


@dataclass(frozen=True)
class Label:
    words: str

    def as_text(self) -> str:
        return self.words

    def as_html(self) -> str:
        return (
            f'<p style="margin:0 0 6px 0;font-family:{SANS};font-size:12px;line-height:16px;'
            f"font-weight:600;letter-spacing:0.08em;text-transform:uppercase;"
            f'color:{MUTED};">{_e(self.words)}</p>'
        )


@dataclass(frozen=True)
class Heading:
    words: str

    def as_text(self) -> str:
        return self.words

    def as_html(self) -> str:
        return (
            f'<h1 class="h1" style="margin:0 0 12px 0;font-family:{SANS};font-size:22px;'
            f'line-height:28px;font-weight:700;color:{INK};">{_e(self.words)}</h1>'
        )


@dataclass(frozen=True)
class Title:
    """A text's own name, in the reading face (§13: the serif is for a text's words)."""

    words: str

    def as_text(self) -> str:
        return isolate(self.words)

    def as_html(self) -> str:
        return (
            f'<p dir="auto" style="margin:0 0 16px 0;font-family:{SERIF};font-size:24px;'
            f'line-height:32px;font-weight:600;color:{INK};">{_e(self.words)}</p>'
        )


@dataclass(frozen=True)
class Hebrew:
    words: str

    def as_text(self) -> str:
        return isolate(self.words)

    def as_html(self) -> str:
        return (
            f'<p dir="rtl" lang="he" style="margin:0 0 16px 0;text-align:right;'
            f"font-family:{HEBREW};font-size:26px;line-height:40px;font-weight:600;"
            f'color:{INK};">{_e(self.words)}</p>'
        )


@dataclass(frozen=True)
class HebrewLine:
    """A sentence in Hebrew at reading size: the digest's standfirst, which the weekly's
    writer is told to write in Hebrew whatever language the mail is in."""

    words: str

    def as_text(self) -> str:
        return isolate(self.words)

    def as_html(self) -> str:
        return (
            f'<p dir="rtl" lang="he" style="margin:0 0 16px 0;text-align:right;'
            f"font-family:{HEBREW};font-size:19px;line-height:30px;"
            f'color:{INK};">{_e(self.words)}</p>'
        )


@dataclass(frozen=True)
class Para:
    words: str
    muted: bool = False

    def as_text(self) -> str:
        return self.words

    def as_html(self) -> str:
        colour = MUTED if self.muted else INK
        return f'<p dir="auto" style="margin:0 0 16px 0;color:{colour};">{_e(self.words)}</p>'


@dataclass(frozen=True)
class Button:
    """The one call to action: ink-filled, paper text, a pill (§9, §13).

    In plain text it is its words, and the link on a line of its own under them, so no
    client joins the link to anything.
    """

    words: str
    href: str

    def as_text(self) -> str:
        return f"{self.words}:\n{self.href}"

    def as_html(self) -> str:
        return (
            '<table role="presentation" cellpadding="0" cellspacing="0" border="0" '
            'style="margin:8px 0 24px 0;"><tr>'
            f'<td bgcolor="{INK}" style="background:{INK};border-radius:999px;">'
            f'<a href="{_e(self.href)}" style="display:inline-block;padding:12px 28px;'
            f"font-family:{SANS};font-size:16px;line-height:20px;font-weight:600;"
            f'color:{PAPER};text-decoration:none;border-radius:999px;">{_e(self.words)}</a>'
            "</td></tr></table>"
        )


@dataclass(frozen=True)
class Fallback:
    """The button's address, spelt out for a client that draws no buttons. HTML only:
    in plain text the button already is the address."""

    words: str
    href: str

    def as_text(self) -> str:
        return ""

    def as_html(self) -> str:
        return (
            f'<p style="margin:0 0 4px 0;font-size:14px;line-height:20px;color:{MUTED};">'
            f"{_e(self.words)}</p>"
            f'<p style="margin:0 0 16px 0;font-family:{MONO};font-size:13px;line-height:20px;'
            f'word-break:break-all;"><a href="{_e(self.href)}" style="color:{TEAL};">'
            f"{_e(self.href)}</a></p>"
        )


@dataclass(frozen=True)
class Rows:
    """A short list of ways in, each a row: its name in teal and a note under it."""

    rows: Sequence[tuple[str, str, str]]

    def as_text(self) -> str:
        return "\n".join(f"  {name} ({note}): {href}" for name, note, href in self.rows)

    def as_html(self) -> str:
        cells = "".join(
            '<tr><td style="padding:0 0 8px 0;">'
            f'<a href="{_e(href)}" style="display:block;background:{RAISED};border-radius:12px;'
            'padding:12px 16px;text-decoration:none;">'
            f'<span style="display:block;font-family:{SANS};font-size:16px;line-height:22px;'
            f'font-weight:600;color:{TEAL};">{_e(name)}</span>'
            f'<span style="display:block;font-family:{SANS};font-size:14px;line-height:20px;'
            f'color:{MUTED};">{_e(note)}</span></a></td></tr>'
            for name, note, href in self.rows
        )
        return (
            '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
            f'border="0" style="margin:0 0 20px 0;">{cells}</table>'
        )


@dataclass(frozen=True)
class Rule:
    def as_text(self) -> str:
        return ""

    def as_html(self) -> str:
        return (
            f'<div style="height:1px;line-height:1px;font-size:0;background:{RULE};'
            'margin:8px 0 16px 0;">&nbsp;</div>'
        )


@dataclass(frozen=True)
class Listed:
    """What one subscription brought, a row each: its title in its own direction and the
    face its language reads in, and a note under it — the daily mail's (design.md §12,
    "Everything new comes in one mail a day", 2026-10-09)."""

    rows: Sequence[tuple[str, str, str, str]]
    #: (title, its language, a note, where it opens)

    def as_text(self) -> str:
        return "\n".join(
            f"  {isolate(title)} ({note}):\n  {href}" for title, _, note, href in self.rows
        )

    def as_html(self) -> str:
        cells = "".join(
            '<tr><td style="padding:0 0 8px 0;">'
            f'<a href="{_e(href)}" style="display:block;background:{RAISED};border-radius:12px;'
            'padding:12px 16px;text-decoration:none;">'
            f'<span dir="auto" lang="{_e(language)}" style="display:block;'
            f"font-family:{HEBREW if language in ('he', 'yi', 'arc') else SERIF};"
            f'font-size:17px;line-height:24px;font-weight:600;color:{INK};">{_e(title)}</span>'
            f'<span style="display:block;font-family:{SANS};font-size:14px;line-height:20px;'
            f'color:{TEAL};">{_e(note)}</span></a></td></tr>'
            for title, language, note, href in self.rows
        )
        return (
            '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
            f'border="0" style="margin:0 0 8px 0;">{cells}</table>'
        )


@dataclass(frozen=True)
class Small:
    """A quiet line inside the card with a link at its end: a subscription's own way out."""

    words: str
    link: str
    href: str

    def as_text(self) -> str:
        return f"{self.words} {self.link}: {self.href}".strip()

    def as_html(self) -> str:
        return (
            f'<p style="margin:0 0 20px 0;font-size:13px;line-height:20px;color:{MUTED};">'
            f'{_e(self.words)} <a href="{_e(self.href)}" style="color:{MUTED};'
            f'text-decoration:underline;">{_e(self.link)}</a></p>'
        )


Block = (
    Label
    | Heading
    | Title
    | Hebrew
    | HebrewLine
    | Para
    | Button
    | Fallback
    | Rows
    | Rule
    | Listed
    | Small
)


@dataclass(frozen=True)
class Foot:
    """A line under the card, with an optional link at its end (a stop link)."""

    words: str
    link: str = ""
    href: str = ""

    def as_text(self) -> str:
        return f"{self.words} {self.link}: {self.href}" if self.href else self.words

    def as_html(self) -> str:
        tail = (
            f' <a href="{_e(self.href)}" style="color:{MUTED};text-decoration:underline;">'
            f"{_e(self.link)}</a>"
            if self.href
            else ""
        )
        return f'<p style="margin:0 0 8px 0;">{_e(self.words)}{tail}</p>'


# -- the frame ---------------------------------------------------------------------------

#: The mark at 26px: the 96-unit drawing's two columns (22 by 62, twelve apart, the
#: translation ten lower) as 7 by 20 cells, 4 apart, the second 3 lower. Table cells
#: with `bgcolor`, because Gmail and Outlook strip inline SVG and an image is a thing to
#: block. The wordmark is text in the reading face at 600, lowercase (§3).
LOCKUP = (
    '<table role="presentation" cellpadding="0" cellspacing="0" border="0" '
    'style="border-collapse:collapse;"><tr><td valign="top" style="padding:0;">'
    '<table role="presentation" cellpadding="0" cellspacing="0" border="0" '
    'style="border-collapse:collapse;"><tr>'
    f'<td width="7" height="20" bgcolor="{MARK_INK}" style="width:7px;height:20px;'
    f'background:{MARK_INK};border-radius:2px;font-size:0;line-height:0;">&nbsp;</td>'
    '<td width="4" style="width:4px;font-size:0;line-height:0;">&nbsp;</td>'
    '<td valign="top" style="padding-top:3px;font-size:0;line-height:0;">'
    '<table role="presentation" cellpadding="0" cellspacing="0" border="0" '
    'style="border-collapse:collapse;"><tr>'
    f'<td width="7" height="20" bgcolor="{MARK_ACCENT}" style="width:7px;height:20px;'
    f'background:{MARK_ACCENT};border-radius:2px;font-size:0;line-height:0;">&nbsp;</td>'
    "</tr></table></td></tr></table></td>"
    f'<td valign="middle" style="padding:0 0 0 9px;font-family:{SERIF};font-size:22px;'
    f'line-height:22px;font-weight:600;letter-spacing:-0.01em;color:{INK};">targum</td>'
    "</tr></table>"
)


_TABLE = 'role="presentation" cellpadding="0" cellspacing="0" border="0"'
_CARD_STYLE = (
    f"background:{CARD};border-radius:16px;padding:32px;font-family:{SANS};"
    f"font-size:16px;line-height:24px;color:{INK};"
)
_FOOT_STYLE = (
    f"padding:20px 4px 0 4px;font-family:{SANS};font-size:13px;line-height:20px;color:{MUTED};"
)


def frame(language: str, subject: str, preheader: str, body: str, foot: str) -> str:
    """The page every mail is drawn on: the desk, the lockup, one card, a foot."""
    # The preheader is the line an inbox shows after the subject. The run of joiners
    # after it keeps a client from filling the rest of that line with the body.
    pad = "&#847;&zwnj;&nbsp;" * 12
    return f"""<!doctype html>
<html lang="{_e(language)}" dir="ltr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light only">
<meta name="supported-color-schemes" content="light">
<meta name="format-detection" content="telephone=no, date=no, address=no, email=no">
<title>{_e(subject)}</title>
<style>
:root {{ color-scheme: light only; supported-color-schemes: light; }}
body {{ margin:0; padding:0; background:{DESK}; }}
a {{ color:{TEAL}; }}
@media (max-width: 620px) {{
  .wrap {{ padding:16px 8px !important; }}
  .card {{ padding:24px 20px !important; border-radius:12px !important; }}
  .h1 {{ font-size:20px !important; line-height:26px !important; }}
}}
</style>
</head>
<body style="margin:0;padding:0;background:{DESK};-webkit-text-size-adjust:100%;">
<div style="display:none;max-height:0;overflow:hidden;opacity:0;">{_e(preheader)}{pad}</div>
<table {_TABLE} width="100%" bgcolor="{DESK}" style="background:{DESK};">
<tr><td class="wrap" align="center" style="padding:32px 12px;">
<table {_TABLE} width="100%" style="max-width:600px;">
<tr><td style="padding:0 4px 20px 4px;">{LOCKUP}</td></tr>
<tr><td class="card" bgcolor="{CARD}" style="{_CARD_STYLE}">
{body}
</td></tr>
<tr><td style="{_FOOT_STYLE}">
{foot}
</td></tr>
</table>
</td></tr>
</table>
</body>
</html>
"""


def site(address: str) -> str:
    """The host a link points at, for the last line of every mail."""
    return urlsplit(address).netloc or address.removeprefix("https://").strip("/")


def compose(
    language: str,
    subject: str,
    preheader: str,
    blocks: Sequence[Block],
    foot: Sequence[Foot],
    *,
    address: str,
    headers: Mapping[str, str] | None = None,
    postal: bool = False,
) -> Letter:
    """One letter from its blocks: the text and the HTML are drawn from the same list."""
    lines = list(foot)
    if postal:
        where = os.environ.get(POSTAL_ENV, "").strip()
        if where:
            lines.append(Foot(where))
    home = site(address)
    lines.append(Foot(f"targum · {home}" if home else "targum"))

    said = [block.as_text() for block in blocks]
    body_text = "\n\n".join(part for part in said if part)
    foot_text = "\n".join(line.as_text() for line in lines)
    plain = f"{body_text}\n\n--\n{foot_text}\n"

    drawn = frame(
        language,
        subject,
        preheader,
        "\n".join(block.as_html() for block in blocks),
        "\n".join(line.as_html() for line in lines),
    )
    return Letter(subject, plain, drawn, dict(headers or {}))


def list_id(name: str, slug: str, address: str) -> str:
    """RFC 2919: a name, and an id under the sending site's own domain."""
    host = site(address).split(":")[0] or "localhost"
    return f"{name} <{slug}.{host}>"


def listed(stop: str, list_id: str) -> dict[str, str]:
    """The headers a mail that goes to a list carries (RFC 2369, 2919, 8058). With them a
    client offers its own unsubscribe button, and a reader who wants out has something
    to press other than "report spam"."""
    return {
        "List-Unsubscribe": f"<{stop}>",
        "List-Unsubscribe-Post": ONE_CLICK,
        "List-Id": list_id,
    }


def _code(language: str) -> str:
    return (language or "en").split("-")[0].lower()


# -- the mails ---------------------------------------------------------------------------


def sign_in(link: str, language: str = "en") -> Letter:
    """The link back in. Transactional: no list headers and no stop link."""
    code = _code(language)
    return compose(
        code,
        text("mail.sign_in.subject", code),
        text("mail.sign_in.preheader", code),
        [
            Heading(text("mail.sign_in.heading", code)),
            Para(text("mail.sign_in.lead", code)),
            Button(text("mail.sign_in.button", code), link),
            Fallback(text("mail.fallback", code), link),
        ],
        [Foot(text("mail.sign_in.ignore", code))],
        address=link,
    )


def waitlist_confirm(link: str, language: str = "en") -> Letter:
    """The waitlist's double opt-in."""
    code = _code(language)
    return compose(
        code,
        text("mail.waitlist.subject", code),
        text("mail.waitlist.preheader", code),
        [
            Heading(text("mail.waitlist.heading", code)),
            Para(text("mail.waitlist.lead", code)),
            Button(text("mail.confirm", code), link),
            Para(text("mail.waitlist.next", code)),
            Fallback(text("mail.fallback", code), link),
        ],
        [Foot(text("mail.not-you", code))],
        address=link,
    )


def invitation(address: str, language: str = "en", connector: bool | None = None) -> Letter:
    """Off the waitlist. It carries no sign-in token, only the way to ask for one.

    And, while the connector is open, a paragraph saying targum works inside Claude and
    ChatGPT, with the way to `/connect` spelt out (design.md §12, "The connector is met on
    the way in"): the mail is the first thing a new reader holds, before any page of
    ours. `connector` is for a caller that knows; left out, the deployment says.
    """
    from .serve import connector_is_open

    code = _code(language)
    base = address.rstrip("/")
    link = f"{base}/account/signin"
    said: list[Any] = [
        Heading(text("mail.invitation.heading", code)),
        Para(text("mail.invitation.lead", code)),
        Para(text("mail.invitation.free", code)),
        Button(text("mail.invitation.button", code), link),
    ]
    if connector_is_open() if connector is None else connector:
        said.append(Para(text("mail.invitation.connector", code, link=f"{base}/connect")))
    return compose(
        code,
        text("mail.invitation.subject", code),
        text("mail.invitation.preheader", code),
        [
            *said,
            Rule(),
            Para(text("mail.invitation.reply", code), muted=True),
        ],
        [Foot(text("mail.invitation.why", code))],
        address=address,
    )


def weekly_confirm(link: str, language: str = "en") -> Letter:
    """The Weekly News Digest's double opt-in."""
    code = _code(language)
    return compose(
        code,
        text("mail.weekly.confirm.subject", code),
        text("mail.weekly.confirm.preheader", code),
        [
            Heading(text("mail.weekly.confirm.heading", code)),
            Para(text("mail.weekly.confirm.lead", code)),
            Button(text("mail.confirm", code), link),
            Fallback(text("mail.fallback", code), link),
        ],
        [Foot(text("mail.not-you", code))],
        address=link,
    )


def _day(dated: str) -> date | None:
    try:
        return date.fromisoformat(dated)
    except ValueError:
        return None


def weekly_issue(issue: Issue, address: str, stop_token: str, language: str = "en") -> Letter:
    """One issue of the Weekly News Digest, for one subscriber.

    Links, not the issue itself: the reader is the product, and Hebrew pasted into a mail
    has no meanings, no recording and no translation beside it. A language the issue was
    built into links to its own edition (`?lang=`); the stop link carries it too, because
    the stop page must not read it off the token.
    """
    from .weekly.models import LEVELS, Level

    code = _code(language)
    base = address.rstrip("/")
    asked = "" if code == "en" else f"?lang={code}"
    where = f"{base}/weekly/{issue.id}"
    stop = f"{base}/weekly/stop?t={stop_token}" + (f"&lang={code}" if asked else "")
    day = _day(issue.dated)
    dated = said_date(day, code) if day else issue.dated
    levels = [
        (
            text(f"weekly.level.{level.value}", code),
            text("weekly.page.figure-words", code, figure=LEVELS[level].figure_in(code)),
            f"{where}/{level.value}{asked}",
        )
        for level in Level
        if issue.edition(level) is not None
    ]
    blocks: list[Block] = [Label(dated), Hebrew(issue.title)]
    if issue.blurb:
        blocks.append(HebrewLine(issue.blurb))
    blocks.append(Button(text("mail.weekly.button", code), where + asked))
    if levels:
        blocks += [Label(text("mail.weekly.levels", code)), Rows(levels)]
    return compose(
        code,
        text("mail.weekly.subject", code, dated=dated),
        issue.blurb or text("mail.weekly.preheader", code),
        blocks,
        [Foot(text("mail.weekly.why", code), text("mail.weekly.stop", code), stop)],
        address=address,
        # The header carries no `lang`: the one-click POST is answered by nobody.
        headers=listed(
            f"{base}/weekly/stop?t={stop_token}",
            list_id("Weekly News Digest", "weekly", address),
        ),
        postal=True,
    )


def subscriptions_daily(
    groups: Sequence[Mapping[str, Any]], address: str, stop_all: str, language: str = "en"
) -> Letter:
    """Everything new from somebody's subscriptions, in one mail (design.md §12,
    "Everything new comes in one mail a day", 2026-10-09).

    `groups` is one subscription each: its `name`, its `stop` token and its `rows` —
    (title, language, note, where it opens). `stop_all` is the token list the one-click
    unsubscribe carries, every subscription this mail does.
    """
    code = _code(language)
    base = address.rstrip("/")
    count = sum(len(group["rows"]) for group in groups)
    first = groups[0]
    if count == 1:
        subject = text(
            "mail.daily.subject-one", code, name=first["name"], title=isolate(first["rows"][0][0])
        )
    else:
        subject = counted(
            "mail.daily.subject",
            count,
            code,
            {"one": "{n} new from your subscriptions", "other": "{n} new from your subscriptions"},
        ).format(n=count)
    blocks: list[Block] = [Heading(text("mail.daily.heading", code))]
    for group in groups:
        blocks.append(Label(group["name"]))
        blocks.append(
            Listed(
                [
                    (title, lang, note, href if href.startswith("http") else f"{base}{href}")
                    for title, lang, note, href in group["rows"]
                ]
            )
        )
        blocks.append(
            Small(
                "",
                text("mail.daily.stop-one", code, name=group["name"]),
                f"{base}/series/stop?t={group['stop']}",
            )
        )
    stop = f"{base}/subscriptions/stop?{stop_all}"
    return compose(
        code,
        subject,
        text("mail.daily.preheader", code),
        blocks,
        [
            Foot(
                text("mail.daily.why", code),
                text("mail.daily.yours", code),
                f"{base}/?show=subscriptions",
            ),
            Foot("", text("mail.daily.stop", code), stop),
        ],
        address=address,
        headers=listed(stop, list_id("subscriptions", "daily.subscriptions", address)),
        postal=True,
    )


def build_ready(
    title: str,
    link: str,
    address: str,
    language: str = "en",
    *,
    asked: bool,
    listen: bool,
    watch: bool = False,
) -> Letter:
    """A build finished while its reader was away. `asked` is whether they put the strip
    away and were promised this; otherwise the build simply took long enough. A film is
    watched before it is listened to, so `watch` wins over `listen`."""
    code = _code(language)
    verb = "watch" if watch else "listen" if listen else "read"
    return compose(
        code,
        text(f"mail.ready.subject.{verb}", code, title=isolate(title)),
        text("mail.ready.preheader", code),
        [
            Label(text(f"mail.ready.label.{verb}", code)),
            Title(title),
            Para(text("mail.ready.lead", code)),
            # Its verb, chosen as the subject's is (§6; copy audit, 2026-09-28): "Open"
            # under "Ready to watch" named no action.
            Button(text(f"mail.ready.button.{verb}", code), link),
        ],
        [Foot(text("mail.ready.asked" if asked else "mail.ready.why", code))],
        address=address,
    )
