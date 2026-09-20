"""A local page for building readers without the terminal.

Not a hosted service: it binds to the loopback address, holds nothing but the readers
you build, and stops when you close it. It exists because pointing at a text and
choosing a language should not require remembering a command.

The pipeline runs in this process, so the page can only do what the CLI can do, and
the cost gate works the same way: ingest and segment first, show what a translation
would cost, and spend nothing until you say so.
"""

from __future__ import annotations

import base64
import contextlib
import email.utils
import errno
import gzip
import json
import logging
import os
import queue
import re
import secrets
import shutil
import threading
import time
import traceback
import webbrowser
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from functools import cache, lru_cache, partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, ClassVar
from urllib.parse import parse_qs, quote, unquote, urlparse

from . import incidents as incidents_module
from . import level as level_module
from .accounts import CHAT_RESTARTED, Person, Store, now, plausible
from .errors import TargumError, UnsupportedSource
from .mail import Mailer
from .models import Segment, SegmentedDocument, Style, glossary_path, is_biblical
from .pipeline import Build, Result
from .remembered import Remembered
from .render.builder import (
    LEGAL,
    about_page,
    back_office_page,
    daily_page,
    front_page,
    holding_page,
    legal_is_public,
    legal_page,
    not_found_page,
    parasha_page,
    shelf_page,
    signin_page,
    text_page,
    weekly_note,
    weekly_page,
)
from .segment.stanza_segmenter import telling
from .usage import Usage
from .video import MAX_VIDEO_BYTES
from .vision import MAX_PAGES, PICTURE_SUFFIXES
from .weekly import index as weekly_index
from .weekly.models import Issue as WeeklyIssue
from .weekly.models import Level as WeeklyLevel
from .weekly.models import parse_identifier as parse_weekly_id

MAX_UPLOAD = 32 * 1024 * 1024

#: The chunked door, for recordings. An audiobook is a gigabyte and the JSON door reads
#: its whole body into memory as base64; chunks arrive raw, 8 MiB at a time — under
#: Caddy's 48 MB body ceiling with room to spare — and are assembled on disk.
CHUNK_BYTES = 8 * 1024 * 1024
MAX_AUDIO_BYTES = 1024 * 1024 * 1024
#: A picture or a PDF comes through the same door as a recording (2026-09-07), because
#: a phone photo is ten megabytes and the JSON door reads its body into memory as
#: base64. Twenty-five is a photo at any phone's full size, and no handout.
MAX_PICTURE_BYTES = 25 * 1024 * 1024
#: A video is allowed more than a recording — an hour of 480p is most of a gigabyte
#: before anything is cut from it. The ceiling itself is `video.MAX_VIDEO_BYTES`,
#: imported above: two copies of a ceiling drift, and a door that refuses what
#: another door accepted is a bug somebody has to find twice.
#: Per account, measured from the disk, audio and video in one figure: `used()` makes
#: one measurement, and two quotas over one measurement cannot be enforced honestly.
MEDIA_QUOTA_BYTES = 8 * 1024 * 1024 * 1024
#: An upload nobody finished is swept after a day.
UPLOAD_TTL_MS = 24 * 60 * 60 * 1000

# Which `Host` a request may claim. Loopback always, because that is what a machine
# somebody runs themselves is reached by and what a reverse proxy connects to. Hosted,
# the public address is added: behind a proxy the original Host survives the hop, so a
# signed-in reader at targum.page arrives claiming targum.page, and a loopback-only
# allowlist refuses every page they ask for — with a message telling them to open a
# Terminal they do not have. `www.` is included because a registrar's default redirect
# is not always in place on the first day.
SAFE_HOSTS = ("127.0.0.1", "localhost", "[::1]")


#: The operator's own name, in front of the public one. Its own host rather than a path
#: on the product, so the door is a vhost in Caddy with a password on it and no route on
#: `targum.page` reaches the back office at all — a mistyped path cannot land on it, and
#: a bug in the product's routing cannot expose it.
BACK_OFFICE = "bo."

#: Where the page actually lives. On the product's own origin, because that is where the
#: session cookie is: host-only, so nothing made on `targum.page` reaches a subdomain.
BACK_OFFICE_ROUTE = "/back-office"


def back_office_host(public_address: str) -> str:
    """`bo.<domain>`, or "" where there is no public name to put it in front of."""
    host = urlparse(public_address).hostname if public_address else ""
    if not host or host.replace(".", "").isdigit():
        return ""
    return BACK_OFFICE + (host[4:] if host.startswith("www.") else host)


def hosts_for(public_address: str) -> frozenset[str]:
    """The names this server will answer to."""
    allowed = set(SAFE_HOSTS)
    host = urlparse(public_address).hostname if public_address else ""
    if host and host not in allowed:
        allowed.add(host)
        # A name, not an address: `www.` means nothing in front of an IP.
        if not host.replace(".", "").isdigit():
            allowed.add(host[4:] if host.startswith("www.") else f"www.{host}")
    behind = back_office_host(public_address)
    if behind:
        allowed.add(behind)
    return frozenset(allowed)


# A base64 body is a third larger than the file inside it, so this is the real ceiling
# on what someone can drop, and the number the page quotes when it refuses one.
MAX_FILE_MB = int(MAX_UPLOAD / 1.37 / (1024 * 1024))

# Said once, in the page, rather than as a stack trace after the wait. Without a key the
# builder can still open everything already built, so this blocks a text rather than
# stopping the server.
NO_KEY = "We can't make anything new right now. Everything you have still opens."


def said_in(ui: str, key: str, english: str, **fill: object) -> str:
    """A sentence the server writes — into an answer, or onto a job a thread finishes
    later — in the language `ui` names, and `english` where its catalogue has not said it
    (targum-internal#184). `tests/test_strings.py` holds every call to `en.json`."""
    from .strings import SOURCE, catalogue

    code = (ui or SOURCE).split("-")[0].lower()
    text = catalogue(code).get(key, english) if code != SOURCE else english
    return text.format(**fill) if fill else text


# A full-length novel costs real money to translate, and a page anyone on this machine
# can reach should not be able to spend it by accident. Both are estimates rather than
# billed amounts, so they are deliberately conservative.
HTML = "text/html; charset=utf-8"

# What the hosted product translates with. Opus stays reachable from the command line
# for anyone who wants it and is paying for it themselves.
HOSTED_MODEL = "claude-sonnet-5"

# A deleted Targum waits in the trash before it goes. Deleting is one press on a day
# somebody is tidying up, and a week is what makes that survivable — the same reasoning,
# and the same seven days, as an account that asks to be forgotten.
# How much of a book is bought before anybody has read a word of it. One: the reader
# waits under a minute instead of half an hour, and the next chapter is started while
# they are most of the way through this one.
FIRST_CHAPTERS = 1

TRASH_DAYS = 7

# Written inside the folder rather than kept in a table: the folder is the thing being
# deleted, and a marker inside it cannot drift away from what it describes.
TRASHED = "trashed"

#: How many rewritten lines the queue offers at once (targum-internal#290). The same
#: twenty the word queue offers, for the same reason: a sitting rather than a syllabus.
SLIPS_SHOWN = 20
#: How many of them the phrases page lists as the record, newest first.
SLIPS_LISTED = 500

# What a page is allowed to do. Readers are self-contained by construction — no script,
# stylesheet, font or image from anywhere, and the tests hold that — so the policy can
# be the strict one rather than a shrug: nothing loads from outside, the page cannot be
# framed, and there is no form to post anywhere.
#
# Inline script and style are the whole design here: a reader is one file that works off
# a disk with no server. Rather than `unsafe-inline`, which would allow anything a
# defect managed to inject, each block is named by the hash of its own contents, so only
# the code targum wrote will run.
#: What a word's card may say about where the reader is, and how much of each. The
#: sentence is the long one; the rest name things.
ABOUT_FIELDS = {
    "document": 200,
    # The text's title, so "let's talk about it" from the front page names what the
    # reader sees rather than a folder (2026-09-11).
    "title": 200,
    "section": 20,
    "sentence": 1000,
    "surface": 80,
    "lemma": 80,
    # What the card says the word means. Without it the model answered a reader who
    # said "the definition here is change, not teachings" with a correct parsing and no
    # idea it was contradicting the card (2026-09-08).
    "meaning": 200,
    # What the card says the form is — "noun · f · accusative" — sent only for a word
    # whose line names a case or an aspect, so the model explains the tag it was shown
    # rather than a parsing of its own (targum-internal#258).
    "grammar": 120,
}


def _about(raw: object) -> dict[str, str] | None:
    """Where the reader is, when a line came from a word's card or the drawer in a reader:
    the text, the section, the sentence and the word. Strings, capped, and nothing else —
    a page can say anything here and the model reads it, so it is quoted as the reader's
    note and never trusted as a fact about the shelf. Typed or spoken, the same note.
    """
    if not isinstance(raw, dict):
        return None
    about = {
        key: str(raw.get(key) or "")[:limit] for key, limit in ABOUT_FIELDS.items() if raw.get(key)
    }
    # A word, a sentence, or the text alone (2026-09-11: "let's talk about it" from the
    # sheet on Learn names the text and nothing narrower).
    if not (about.get("surface") or about.get("sentence") or about.get("document")):
        return None
    return about


POLICY = (
    "default-src 'none'; "
    "img-src 'self' data:; "
    # The Hebrew faces ride inside the page as data: URIs, the same way the icons do,
    # and `default-src 'none'` covers fonts unless they are named. Without this line the
    # font is refused by policy, `document.fonts` reports it as an error, and every
    # accented letter is borrowed from whatever face the machine has — which was invisible
    # for as long as readers were checked by opening the file, where no policy applies.
    "font-src data:; "
    # And the recordings, which ride inside the page the same way. Left out, `default-src
    # 'none'` refuses the audio and the player reports a recording that will not play —
    # the identical bug the font line above exists for, missed the identical way: every
    # check of the player was made by opening the file, where no policy applies. The one
    # served page is the only place either of them can be seen to fail.
    #
    # `'self'` is for the one thing too heavy to ride inside the page: a video part is a
    # sidecar file beside the reader, named by a relative address, and without `'self'`
    # the served page refuses the very file sitting next to it — the third writing of
    # the same bug, headed off this time (design.md §12).
    "media-src 'self' data:; "
    "connect-src 'self'; "
    "base-uri 'none'; "
    # 'self', not 'none'. The sign-in landing page posts a real form back to targum —
    # it has to work with no JavaScript, because it arrives from an email in whatever
    # browser opened it — and 'none' forbids exactly that. A reader has no form at all,
    # so this permits nothing it could use.
    "form-action 'self'; "
    "frame-ancestors 'none'"
)

# What one reader may spend in a day. **A rate limit and nothing else** — it exists to
# stop a loop or a scraper, never to ration reading, and the message it produces says so.
# Sized so that no honest reader meets it: at $0.125 per thousand words this is around
# eighty thousand words a day, a novel between breakfast and bed. A reader who wants two
# novels in one day waits until tomorrow; a script that wants two hundred does not get
# them. Raised from $3.00 when text uploads became unlimited, since $3.00 refused a
# single long book and made "unlimited" a word the server did not honour.
ACCOUNT_BUDGET = 10.00

# What one reader is allowed in a calendar month. The daily rail above is a rate limit —
# it stops one afternoon running away — and for a while it was standing in for a plan
# limit as well, which it is bad at: thirty days of $3.00 is $90.00, and nobody agreed to
# that. This is the number a reader is actually held to.
#
# A calendar month rather than a rolling thirty days, because it is the one a refusal can
# name — "back on the 1st" is a date somebody can plan around, where "back in a few days"
# is a shrug. It costs a month boundary where readers get their allowance back at once,
# which for an alpha of a handful of people is not a thundering herd.
# There was a monthly money cap on a reader here, and its removal is the feature: text
# uploads are unlimited, so the only thing a subscriber is held to is the audio allowance
# below. What remains in money is a rate limit and a runaway guard, both of which stop a
# loop rather than ration reading. Nothing may reintroduce a per-reader monthly ceiling
# without making the pricing page a lie — `test_usage.py` holds that.

# What a subscription allows in a month, and the only limit a reader is ever told about:
# eight hours of audio. Both directions count against it — a recording transcribed on the
# way in, speech synthesised on the way out — because those are the two things this
# product buys by the clock, and a reader who has spent an hour does not care which
# direction it went. Text uploads are not metered here at all; they are bounded by the
# money rails above, which the reader never sees.
#
# In seconds, because every duration in the codebase is: `probe.duration`, the audio
# manifest, the recording spans. Hours are the unit on the pricing page and nowhere else.
#
# Eight rather than ten, and the reason is the sentence rather than the cost: eight hours
# is roughly two hours a week, which is a shape a reader can picture against their own
# week, where ten hours a month is a quantity they have to convert first. Seven would
# have been cheaper still and maps onto no phrase at all. The page says "8 hours a
# month" and never "two hours a week" — a calendar month is 4.35 weeks, so eight hours
# is 1.84 of them, and printing the rounder sentence would over-promise by 9%.
UPLOAD_HOURS = 8
UPLOAD_SECONDS = UPLOAD_HOURS * 60 * 60

# What one reader's conversation may spend in a day. **A rate limit, like the account
# rail above, and a narrower one**: a turn is uncacheable and the reader controls the
# volume, so the rail that was sized for builds — where a novel is the unit — is the
# wrong size for a sentence. A dollar is on the order of fifty turns at the effort the
# chat runs at, which is an afternoon of asking; a script asking every second is what
# this stops. Counted on rows of kind `chat` alone, and the same rows count against the
# account rail too, so neither can be used to get round the other. The refusal names
# when it lifts and never implies that reading is used up.
CHAT_BUDGET = 1.00

# Hosted, everyone signs in first. Signed out, every home would be the same `local`
# directory, so one visitor would be reading another's library — and there is nowhere
# to put a build that belongs to nobody. On a machine somebody runs themselves the
# opposite is true: there is one person, they are the only one who can reach it, and
# making them make an account to read their own files would be absurd. So it is a
# switch, off by default, and the hosted deployment is what turns it on.
#: The privacy notice, the terms, the retention schedule and the erasure procedure.
#: Derived from the documents themselves rather than typed again here, so the routes,
#: robots and the sitemap cannot disagree about which four exist.
#:
#: Shut for the alpha behind `legal_is_public()`. They are dispatched before
#: `_needs_account` so that shut means 404 rather than the holding page — a legal page
#: that answers with "Coming soon" is worse than one that answers with nothing, because
#: it looks like it is there. They stay in `OPEN_TO_STRANGERS` for when the switch is
#: thrown: reaching them has never needed an account and never will.
LEGAL_ROUTES = tuple(f"/{name}" for name in LEGAL)

OPEN_TO_STRANGERS = frozenset(
    {
        "/about",
        "/account/signin",
        "/account/enter",
        "/account/sign-in",
        "/account/me",
        "/health",
        # The door out of a series, followed from an email with no account at hand
        # (2026-09-11): its token is the whole of what it needs.
        "/series/stop",
        # The front door's form and the two doors its mail carries (2026-09-16). Nobody
        # joining a waitlist has an account, and the point of the list is that they
        # cannot get one yet.
        "/waitlist",
        "/waitlist/confirm",
        "/waitlist/stop",
    }
) | frozenset(LEGAL_ROUTES)

# The public shelves, and every text on them. Built, tested, and deliberately shut:
# nothing is open to strangers until there is something worth arriving at and a
# whitelist deciding who may come in.
#
# Shut means shut all the way down. A robots.txt that invites a crawler while every
# page it reaches says "Coming soon" is worse than none at all — what gets indexed is
# the holding page, and that is then what ranks for the product's own name later. So
# while this is off the sitemap is gone and robots refuses the whole site.
PUBLIC_TEXT = re.compile(r"^/library/([a-z0-9][a-z0-9-]{0,63})$")


#: Which level `/weekly` and `/weekly/<week>` land on. The middle one, because it is
#: the one most readers can read and the other two are one click either side of it.
DEFAULT_LEVEL = WeeklyLevel.bet


def weekly_url(entry_id: str) -> str | None:
    """The address an edition would rather be found at, or None if this is not one.

    Only for a *published* edition: a catalogue id that names a draft is not a thing to
    redirect to, because there is nothing at the other end.
    """
    if not entry_id.startswith("weekly-"):
        return None
    parsed = parse_weekly_id(entry_id.removeprefix("weekly-"))
    if parsed is None:
        return None
    week, level = parsed
    issue = next((one for one in weekly_index.readable() if one.id == week), None)
    if issue is None or issue.edition(level) is None:
        return None
    return f"/weekly/{week}/{level.value}"


def parasha_url(entry_id: str) -> str | None:
    """The address a portion would rather be found at, or None if this is not one.

    The same move `weekly_url` makes, for the same reason: a portion is a catalogue
    entry so the library lists it, and it has a page of its own that says which Shabbat
    reads it and offers the chanting marks either way. Two URLs for one text is a
    duplicate a search engine has to choose between, and this is which one wins.

    Only for a portion that is actually built. An entry naming one that is not is an
    entry pointing at a 404, and sending a reader there is worse than not listing it.
    """
    if not entry_id.startswith("parasha-"):
        return None
    from .parasha import build as corpus

    slug = entry_id.removeprefix("parasha-")
    index = corpus.load()
    portion = index.portions.get(slug)
    if portion is None or portion.folder not in corpus.readable(index):
        return None
    return f"/parasha/{slug}"


#: The three the weekly's own door answers, all of them plain forms so they work with
#: no JavaScript at all — which matters because two of them are followed out of an email
#: client, where JavaScript is not a thing that exists.
log = logging.getLogger(__name__)

WEEKLY_POSTS = frozenset({"/weekly/subscribe", "/weekly/confirm", "/weekly/stop"})

#: The front door's three, and the only doors that answer while the product is shut
#: (2026-09-16, targum-internal#69). Joining is a plain form post; confirming and
#: leaving are a page with a button, for the reason the weekly's two are.
WAITLIST_POSTS = frozenset({"/waitlist", "/waitlist/confirm", "/waitlist/stop"})

#: A series id as `series.py` names them: a slug, nothing else.
SERIES_ID = re.compile(r"^[a-z][a-z0-9-]{0,40}$")

#: How often the server looks for an instalment that landed since anyone was told
#: (2026-09-11): the portion turns weekly and a cycle daily, so an hour is prompt enough
#: and cheap — a look is one read of what is built and one query per series.
ANNOUNCE_EVERY = 3600

#: A file inside a published edition's built reader.
#:
#: The path mirrors the folder on disk — `<edition>/reader/<file>` — so the level
#: switcher's relative hrefs resolve the same way served as they do off a disk. A reader
#: that travels is the promise this product makes, and two link shapes for one file is
#: how a promise like that quietly stops being true.
#:
#: The names are deliberately narrow: a reader writes `index.html` and `sec-0001.html`
#: and nothing else, so a path carrying a slash or a dot-dot never reaches the
#: filesystem check at all.
WEEKLY_READER = re.compile(r"^/weekly/read/([a-z0-9-]{1,64})/reader/([a-z0-9-]{0,40}\.html)?$")


#: The same shape for the corpus. A portion's folder is its slug, which is lowercase
#: letters and the hyphen that joins a doubled week.
def daily_is_indexed() -> bool:
    """Whether search engines are invited to the daily learning pages.

    Its own switch rather than the parasha's, which is what they rode on for the
    afternoon they were built. Sharing one would mean that inviting crawlers to fifty-four
    portions — a corpus that is finished, and the same fifty-four every year — also
    invited them to four pages that change every night and were a day old. The two are
    ready at different times and now say so separately.

    Off unless the deployment says. While it is off every daily response carries
    `X-Robots-Tag: noindex` and the sitemap does not mention the cycles. Not robots.txt,
    for the reason `weekly_is_indexed` gives: a crawler barred there never fetches the
    page, so it never sees the noindex, and an address it learned elsewhere can still be
    indexed bare. The header is the instruction; the open door is what lets it be read.
    """
    return os.environ.get("TARGUM_INDEX_DAILY", "").strip().lower() in {"1", "true", "yes"}


def daily_cycles() -> tuple[Any, ...]:
    """The learning cycles this shelf carries. A function rather than an import at the
    top, because `serve` is imported to answer one request and `daily` pulls the
    catalogue in behind it."""
    from .daily.cycles import CYCLES

    return CYCLES


PARASHA_READER = re.compile(r"^/parasha/read/([a-z0-9-]{1,64})/reader/([a-z0-9-]{0,40}\.html)?$")

#: A learning cycle at its own address: `/mishna-yomi`, `/mishna-yomi/2026-09-01`, and
#: one file of a built reader under `/mishna-yomi/read/<date>/reader/…`. The slugs are the
#: four this shelf carries and nothing else matches, so a cycle Hebcal publishes and
#: targum does not is a 404 rather than an empty page.
DAILY_ROUTE = re.compile(r"^/(mishna-yomi|nach-yomi|tanakh-yomi|tehillim)(/.*)?$")
#: How many days either side of the one on screen the chip row offers.
NEARBY_DAYS = 3

DAILY_READER = re.compile(r"^/read/(\d{4}-\d{2}-\d{2})/reader/([a-z0-9-]{0,40}\.html)?$")

#: How often one address may ask to be subscribed. The `asked` table and its rail are
#: reused exactly: a subscribe endpoint anybody can call is, like the sign-in one, a way
#: to send mail from this domain into somebody else's inbox.
SUBSCRIBE_ASKS_PER_HOUR = 3

#: A cap on how many unconfirmed rows may sit there at once, so the address rail cannot
#: be walked around by using a different address every time.
MAX_PENDING = 500


def shelves_are_public() -> bool:
    """Whether strangers may see the catalogue. Off unless the deployment says so."""
    return os.environ.get("TARGUM_PUBLIC_SHELVES", "").strip().lower() in {"1", "true", "yes"}


def keeps_events() -> bool:
    """Whether the record of what a reader does in a text is kept (targum-internal#127).

    Off unless the deployment says so, and for a different reason from the other switches
    here. What is kept, for how long, what it is used for and what a reader can do about it
    were all decided on 2026-09-19. What was not is the sentence that says so: the privacy
    notice names a legal basis for every category of data it lists, and this is a new
    category with two purposes — a reader's own figures, and an aggregate signal about the
    texts. Turning this on and publishing that paragraph are one decision, and it is not
    one to take by merging a pull request. The draft is on the card.

    While it is off, `/events` keeps nothing and says so, `/account/totals` answers
    nothing, and Your Progress draws none of the three figures that read from it.
    """
    return os.environ.get("TARGUM_EVENTS", "").strip().lower() in {"1", "true", "yes"}


def front_door_is_open() -> bool:
    """Whether a stranger at `/` gets the front door or the holding page.

    Off unless the deployment says so, which is what lets the page merge, deploy and be
    looked at on the box before anybody outside sees it: the day it goes public is one
    line in `targum.env` rather than a release (targum-internal#69, 2026-09-16).

    While it is off, `/waitlist` and its two doors answer 404 as well — a form that
    takes an address is not something to leave reachable beside a page that says
    "Coming soon".
    """
    return os.environ.get("TARGUM_FRONT_DOOR", "").strip().lower() in {"1", "true", "yes"}


def weekly_is_indexed() -> bool:
    """Whether search engines are invited to the weekly. Off unless the deployment says.

    Public and indexed are different facts. The weekly can be readable by anyone with
    the address — sent in a message, linked from a chat — while the address is not yet
    something a search for Hebrew news should surface. While this is off, every weekly
    response says `X-Robots-Tag: noindex` and the sitemap does not mention the issues.

    Deliberately not robots.txt: a crawler barred by robots.txt never fetches the page,
    so it never sees the noindex — and a URL it learned elsewhere can be indexed bare.
    The header is the instruction; the open door is what lets it be read.
    """
    return os.environ.get("TARGUM_INDEX_WEEKLY", "").strip().lower() in {"1", "true", "yes"}


def parasha_is_indexed() -> bool:
    """Whether search engines are invited to the parasha. Off unless the deployment says.

    Same switch as the weekly and for the same reason, but the stakes are the other way
    round. The weekly's issues age; a portion's page is the same page every year, so
    whatever ranks for "parashat Bereshit" ranks for a long time. Better to let the
    reading, the audio and the shelf settle first than to have the first crawl decide.

    While this is off every parasha response says `X-Robots-Tag: noindex` and the sitemap
    does not mention the portions. Not robots.txt, for the reason `weekly_is_indexed`
    gives: a crawler barred there never fetches the page, so it never sees the noindex,
    and an address it learned elsewhere can still be indexed bare.
    """
    return os.environ.get("TARGUM_INDEX_PARASHA", "").strip().lower() in {"1", "true", "yes"}


# What somebody who has not been invited is told. Honest about the state of things and
# says nothing about who is on the list.
NOT_OPEN = "Thanks for asking. targum isn't open yet."

#: What a drawn cover may be saved as. No SVG: these arrive from an image model and an
#: SVG is a script that runs, which is not a thing to serve from a directory anybody can
#: drop files into. Both halves of the app read this — one plans covers, one serves them.
THUMBS = ((".webp", "image/webp"), (".png", "image/png"), (".jpg", "image/jpeg"))

MAX_COST = 2.00
# The runaway guard for the whole box in a day, and the one rail waived for nobody —
# not even an admin, because a loop at three in the morning does not care whose account
# it is on. It has to sit well clear of `ACCOUNT_BUDGET`: at parity, one reader having a
# long day would close the box for everybody else, which is a worse failure than the one
# it prevents. Four readers at their daily rate.
SESSION_BUDGET = 40.00

# The budget used to last as long as the process, which meant restarting handed it back
# in full. It is a rolling day instead: it survives a restart, and it does not brick the
# machine a week later the way a permanent total would. A4 replaces it with a per-account
# monthly limit; until then this is the ceiling on what one box will spend in a day.
BUDGET_HOURS = 24

# Builds run one at a time. Stanza and LaBSE are large enough that two at once is worse
# than two in sequence, and a thread per request is a way for one visitor to exhaust the
# machine — which mattered less on a laptop than it does on a box anyone can reach.
WORKERS = 1


# The dead end anyone reaches by bookmarking the address or leaving a tab open over a
# restart. The key changes every start, so this is a normal thing to hit, and a blank
# line of plain text left no way back.
STALE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>targum</title>
<style>
  :root { color-scheme: light; }
  body {
    margin: 0; min-height: 100vh; display: grid; place-items: center;
    padding: 2rem; background: #faf8f4; color: #2b2724;
    font: 16px/1.6 system-ui, sans-serif;
  }
  main { max-width: 30rem; }
  h1 { font-size: 1.5rem; margin: 0 0 0.75rem; }
  p { margin: 0 0 0.75rem; }
  code { background: #ece7de; padding: 0.1em 0.35em; border-radius: 3px; font-size: 0.9em; }
  form { display: flex; gap: 0.5rem; flex-wrap: wrap; margin: 1.25rem 0 0.75rem; }
  input, button {
    font: inherit; padding: 0.5rem 0.75rem; border-radius: 6px;
    border: 1px solid #d9d2c5; background: #fff; color: inherit;
  }
  input { flex: 1 1 14rem; min-width: 0; }
  button { background: #7a5c3a; border-color: #7a5c3a; color: #fff; cursor: pointer; }
  .said, .aside { color: #6b625a; font-size: 0.9375rem; }
  .said[hidden] { display: none; }
</style>
</head>
<body>
<main>
  <h1>This tab has gone stale</h1>
  <p>Nothing is lost. Everything you were reading and every word you've kept is still
  here.</p>
  <p>Sign in and this won't happen again. A signed-in tab keeps working, and your words
  follow you to whatever you read next.</p>
  <form id="in">
    <input type="email" id="email" placeholder="you@example.com" autocomplete="email"
           spellcheck="false" required>
    <button type="submit">Send a link</button>
  </form>
  <p class="said" id="said" hidden></p>
  <p class="aside">Running targum yourself? The Terminal window also prints a link, and
  that one works straight away.</p>
</main>
<script>
document.getElementById("in").addEventListener("submit", function (event) {
  event.preventDefault();
  var said = document.getElementById("said");
  said.hidden = false;
  said.textContent = "Sending\u2026";
  fetch("/account/sign-in", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email: document.getElementById("email").value }),
  })
    .then(function (response) { return response.json(); })
    .then(function (answer) { said.textContent = answer.message || answer.error; })
    .catch(function () { said.textContent = "We couldn't send that. Try again."; });
});
</script>
</body>
</html>"""


@cache
def _icon() -> bytes:
    """The tab icon for /favicon.ico, which only takes a raster."""
    brand = Path(__file__).parent / "render" / "assets" / "brand"
    return (brand / "favicon-32.png").read_bytes()


def grounding_note(
    store: Store | None, lemma: str, source: str, target: str
) -> Callable[[Any, Any, str], None]:
    """What a grounding writes to the correction store (targum-internal#164, door 1).

    A reader tapped a word in a sentence and the sense was bought again with that
    sentence; the row keeps the bare sense that stood, the grounded one that stands,
    and the line — under `who = reader`, never a person. Nothing here may fail the
    look-up: the reader asked what a word means, not for a record to be kept.
    """

    def note(before: Any, after: Any, context: str) -> None:
        if store is None:
            return
        try:
            store.correct(
                "gloss",
                who="reader",
                term=lemma,
                language=source,
                target=target,
                before=str(getattr(before, "gloss", "") or ""),
                after=str(getattr(after, "gloss", "") or ""),
                context=context,
                reason="grounded on the sentence the reader was in",
            )
        except Exception:  # noqa: BLE001 - see the docstring
            traceback.print_exc()

    return note


@dataclass
class Job:
    id: str
    source: str
    title: str = ""
    language: str = ""
    segments: int = 0
    estimate: float = 0.0
    stage: str = "reading"
    done: int = 0
    total: int = 0
    message: str = ""
    error: str = ""
    reader: str = ""
    lemmas: int = 0
    meanings: float = 0.0
    blocked: str = ""
    options: dict[str, Any] = field(default_factory=dict)
    # Whose build this is, and where its reader lands. The thread that runs it has no
    # request to ask, so both travel with the job rather than being looked up later.
    owner: int | None = None
    home: Path | None = None
    # Whether the person who asked for it is held to the per-account spend rails. Read
    # at claim time and never written down: it is a fact about who they are now, not
    # about this job, and a job recovered after a restart has already been claimed.
    admin: bool = False
    # The language whoever asked for it reads the product in, so a refusal written later
    # by the thread that runs it is said in theirs (targum-internal#184). Never stored.
    ui: str = "en"
    # What it really cost, once the API has said. Zero until it has.
    spent: float = 0.0
    # What the prompt cache did on this job: tokens read, written, and their dollars,
    # already inside `spent`. Only a turn of conversation caches (targum-internal#239).
    cached: tuple[int, int, float] | None = None
    # How many chapters the text has. One means it is not a book.
    chapters: int = 1
    # An imported recording: its length, how it divides, and what hearing it costs.
    # Zero and false for every text that is not one.
    audio: bool = False
    seconds: float = 0.0
    parts: int = 0
    transcription: float = 0.0
    made: int = field(default_factory=now)
    #: Seconds a build of this shape has taken here lately, or zero where this box has
    #: not finished enough of them to say. Never stored — a fact about the box, not
    #: about this job — and worked out once, when the quote is written.
    usually: float = 0.0
    #: When it stopped, however it stopped: done, failed or blocked. Zero while it runs.
    #: How long a build takes was never written down, so nothing could answer "when will
    #: this be ready?" with a number anybody had counted (targum-internal#303).
    finished: int = 0
    #: `build` for everything the queue runs; `chat` for one turn of conversation, which
    #: takes a row here so the rails see it and is never queued. See `chat/session.py`.
    kind: str = "build"
    # A text that arrived as pages — pictures the model read, or a PDF's text layer.
    # How many, how many lines could not be read cleanly, the first lines as read (the
    # card shows them, so the reader sees what will be built before pressing), and what
    # the reading cost: the one spend before a card, settled into the receipt at the end.
    pages: int = 0
    doubtful: int = 0
    excerpt: list[str] = field(default_factory=list)
    #: Whether the pictures were a messaging conversation, read as its messages.
    conversation: bool = False
    reading: float = 0.0
    #: How much of the text the reader already has, estimated at quote time from the
    #: ledger (`level.known_share`, targum-internal#244); None where nobody is signed
    #: in or the text is too short to say.
    known_share: float | None = None

    def state(self) -> dict[str, Any]:
        from . import catalogue as catalogue_module

        # Worked out when asked rather than stored on the job: the catalogue is the one
        # place a title's English lives, and a column here would be a second.
        entry = catalogue_module.matching(self.source) if self.source else None
        return {
            "blocked": self.blocked,
            "id": self.id,
            "made": self.made,
            "title": self.title,
            "english": entry.english if entry else "",
            "language": self.language,
            "segments": self.segments,
            "chapters": self.chapters,
            "estimate": round(self.estimate, 2),
            "stage": self.stage,
            "done": self.done,
            "total": self.total,
            "message": self.message,
            "error": self.error,
            "reader": self.reader,
            "lemmas": self.lemmas,
            # Translation and word meanings are priced separately because they are
            # bought separately: one line quoting the sum made the meanings look free
            # and hid that unticking the box halves the bill.
            "meanings": round(self.meanings, 2),
            "translation": round(max(0.0, self.estimate - self.meanings - self.transcription), 2),
            # The audio card's facts: shown in ui-monospace as a clock and a count,
            # never as dollars — the page already takes that position.
            "audio": self.audio,
            "seconds": round(self.seconds, 1),
            "parts": self.parts,
            "transcription": round(self.transcription, 2),
            # The pages card's facts: what was read, and how well.
            "pages": self.pages,
            "doubtful": self.doubtful,
            "conversation": self.conversation,
            "excerpt": list(self.excerpt),
            # How long one of these has taken here lately. Zero means "not enough
            # finished builds to say", and the card shows nothing rather than a guess.
            "usually": round(self.usually, 1),
            "known_share": None if self.known_share is None else round(self.known_share, 2),
            "known_line": level_module.words_in_ten(self.known_share),
            # Where the text is from, so the card can link to it (2026-09-11: "don't
            # see the link to the article"). A link for a page on the web; a fetcher
            # id or a filename otherwise, which the page shows no link for.
            "source": self.source,
            # An Instagram post whose pictures were not read: how many there are, so the
            # card can offer to read them. Offered, never run: the press is the consent.
            "pictures_offered": (
                0 if self.options.get("pictures") else int(self.options.get("post_pictures") or 0)
            ),
        }


def sent_as(job: Job) -> str:
    """What kind of thing a job's source is, for the note the model gets with a line
    sent beside it: `pictures`, `pdf`, `recording`, `link` or `text`."""
    from .ingest import picture as picture_module

    source = str(job.source)
    if picture_module.is_pictures(source):
        return "pictures"
    if source.lower().endswith(".pdf"):
        return "pdf"
    if job.audio:
        return "recording"
    if source.startswith(("http://", "https://")):
        return "link"
    return "text"


def excerpt_of(lines: list[str], count: int = 4, width: int = 120) -> list[str]:
    """The first lines of a text as read, for the card. What the reader will get, shown
    before they press, in place of a filename that says nothing about a picture."""
    out: list[str] = []
    for line in lines:
        text = " ".join(line.split())
        if not text:
            continue
        out.append(text if len(text) <= width else text[: width - 1].rstrip() + "…")
        if len(out) == count:
            break
    return out


# A person's home is `p` and their number, and nothing else. Matching on the `p` alone
# would treat a text called "poem-he" as somebody's home and leave it unadopted, which
# is to say invisible.
HOME = re.compile(r"p\d+")

# Either kind of home, in front of an uploaded text's cover — `p` and a number for
# somebody signed in, `local` for the machine's own signed-out shelf. A name arriving
# with one of these already on it is asking for a file by somebody else's key rather
# than its own; `_serve_thumb` puts the asker's own home on and never reads a name that
# came carrying one.
OWNED = re.compile(r"(?:p\d+|local)-")


def free_name(home: Path, name: str) -> Path:
    """A name in this home that nothing is using yet.

    Two documents can slug to the same name and hold different texts, and adopting one
    over the other would silently destroy work. Renaming over a directory that already
    has something in it does not even fail cleanly — it raises, part-way through
    start-up, and the server never comes up.
    """
    target = home / name
    nth = 2
    while target.exists():
        target = home / f"{name}-{nth}"
        nth += 1
    return target


@dataclass(frozen=True)
class Drawable:
    """A text a cover can be drawn for, whether or not the catalogue has heard of it.

    A catalogue `Entry` answers all four of these already; an upload answers them from
    its own document. Everything downstream of `cover_plan` asks for exactly this much,
    so neither has to know which it is holding.
    """

    id: str
    source: str
    title: str
    language: str


def unreadable(error: Exception) -> str:
    """What a reader is told when bringing something in failed for a reason nobody wrote a
    sentence for. A web page's refusal carries its status, and the status says what to do."""
    response = getattr(error, "response", None)
    status = getattr(response, "status_code", None)
    if status in (401, 403, 451):
        return "That site won't let us read the page. Copy the text and paste it here instead."
    if status in (404, 410):
        return "That page isn't there. Check the link and try again."
    if isinstance(status, int) and status >= 400:
        return "That site didn't answer properly. Try again, or paste the text itself."
    return "We couldn't read that. Try again, or paste the text itself."


class Jobs(dict[str, Job]):
    """Every job the process knows about, with the ones that can be in a line indexed.

    A plain dict held all of these and `Library.mine` walked the whole thing to answer
    "where am I in the queue?". Since 2026-09-05 every chat turn is a job row — which is
    right, because it is how the spending rails see a turn — so that dict grows with
    every turn anybody ever takes, and a question about the two builds in the queue was
    being answered by walking a hundred thousand conversations
    (targum-internal#231).

    So the builds are indexed as they arrive, and the index forgets a build at exactly
    the moment `mine` stops showing it: settled, and older than `Library.RECENT_MS`.
    That is not a second policy to keep in step with the first — it is the same
    condition, which is why `waiting` takes the cutoff rather than deciding one.

    **What this deliberately does not change is what the server remembers.** `self` still
    holds every job, `/job/<id>` still answers about one from three months ago, and the
    ledger on disk is still the record. Only the per-request cost moves.

    The index is maintained here rather than at the thirteen places that assign a job,
    because an index the caller has to remember to update is an index that drifts. The
    tests that assign a whole dict at once go through `Library.jobs`'s setter, which
    wraps a plain mapping in this.
    """

    def __init__(self, initial: Mapping[str, Job] | None = None) -> None:
        super().__init__()
        self.builds: dict[str, Job] = {}
        if initial:
            self.update(initial)

    def __setitem__(self, key: str, job: Job) -> None:
        super().__setitem__(key, job)
        if job.kind == "build":
            self.builds[key] = job

    # `dict.update` does not go through `__setitem__` on a subclass, so it is spelled
    # out. A silent bypass here would be a drifted index, which shows up as a build
    # missing from somebody's strip rather than as an error.
    def update(self, *args: Any, **kwargs: Job) -> None:
        for key, job in dict(*args, **kwargs).items():
            self[key] = job

    def waiting(self, cutoff: int) -> list[Job]:
        """The builds worth answering about, and a sweep of the ones that are not.

        Everything settled before `cutoff` is dropped from the index on the way past:
        it is on disk, it is still in the registry, and nothing will ask about it again.
        A key that has left the registry by any route goes too, which is why removal is
        checked here rather than hooked in `__delitem__` and `pop` — an index that can
        only be right if every caller remembers it is an index that eventually is not.

        A copy is taken first because a worker thread may finish a build while this
        runs, and mutating what you are iterating is how that would show up.
        """
        keep: list[Job] = []
        for key, job in list(self.builds.items()):
            gone = key not in self
            settled = job.stage in ("done", "failed", "blocked") and job.made < cutoff
            if gone or settled:
                self.builds.pop(key, None)
                continue
            keep.append(job)
        return keep


class Library:
    """Everything built so far, and the jobs building more."""

    #: Every job this process knows about. A `Jobs` rather than a plain dict, because
    #: the builds are indexed inside it; the setter wraps a plain mapping so that
    #: `library.jobs = {...}` — which several tests do to stage a queue — keeps the
    #: index rather than quietly replacing the thing that maintains it.
    @property
    def jobs(self) -> Jobs:
        return self._jobs

    @jobs.setter
    def jobs(self, value: Mapping[str, Job]) -> None:
        self._jobs = value if isinstance(value, Jobs) else Jobs(value)

    def __init__(
        self,
        out: Path,
        max_cost: float = MAX_COST,
        budget: float = SESSION_BUDGET,
        store: Store | None = None,
        account_budget: float | None = ACCOUNT_BUDGET,
        upload_seconds: float | None = UPLOAD_SECONDS,
        mailer: Mailer | None = None,
        address: str = "",
        chat_budget: float | None = CHAT_BUDGET,
    ) -> None:
        self.out = out
        self.chat_budget = chat_budget
        #: Where an error is written down, other than the journal (targum-internal#24).
        self.incidents = out / "incidents.jsonl"
        # How to reach somebody whose build finished while they were away, and where
        # the reader is. Neither is needed on a machine somebody runs themselves.
        self.mailer = mailer
        self.address = address
        # A home nobody owns, read by everybody: what a reader with nothing on their
        # shelf is handed to start with. Written only by `targum seed`, never by a
        # request — nothing routed through `within(home, …)` can reach it, so a shared
        # text cannot be bought, trashed or rebuilt by whoever is reading it.
        self.shared = out / "shared"
        # What each shelf row says, kept beside each reader (`remembered`). The one
        # thing a request writes on the shared shelf, as `coverage.lemmas` already did:
        # an answer about a text, never the text.
        self.remembered = Remembered()
        # Where published issues of the weekly land. A third read-only home, owned by
        # nobody, written only by `targum weekly publish` and never by a request.
        self.weekly = out / "weekly"
        # Where the weekly's loader should look, since nothing but this process knows
        # where a given box keeps its readers and the fallback is the working directory,
        # which on a box is `/`. `setdefault`, not assignment: a caller who named one
        # meant it, and overwriting theirs is how two servers in one process end up
        # reading each other's issues.
        os.environ.setdefault("TARGUM_WEEKLY_DIR", str(self.weekly))
        self.max_cost = max_cost
        self.budget = budget
        self.account_budget = account_budget
        self.upload_seconds = upload_seconds
        self.store = store
        self.adopt()
        self.empty_trash()
        self.purge_departed()
        self._committed = 0.0
        # Every job, with the builds indexed beside them; see `Jobs`. Assigned through
        # the property below so a plain dict handed in by a test is wrapped, not lost.
        self.jobs = Jobs()
        # The quota's view of each home, cached a minute: a gigabyte arrives in a
        # hundred chunks and the disk should not be walked for every one of them.
        self._used: dict[Path, tuple[int, int]] = {}
        self.lock = threading.Lock()
        self.queue: queue.Queue[str] = queue.Queue()
        self._workers: list[threading.Thread] = []
        if store is not None:
            self._recover(store)

    # -- durability -------------------------------------------------------------

    def _recover(self, store: Store) -> None:
        """Read back what the last run was doing.

        A build cannot be picked up from the middle: the work was in a thread that no
        longer exists. What it can do is stop lying about itself — a job left at
        "working" would sit there forever — and hand back the money it never spent.
        """
        store.interrupt_running()
        for row in store.jobs():
            job = Job(
                id=str(row["id"]),
                source=str(row["source"]),
                title=str(row["title"]),
                language=str(row["language"]),
                segments=int(row["segments"]),
                estimate=float(row["estimate"]),
                stage=str(row["stage"]),
                done=int(row["done"]),
                total=int(row["total"]),
                message=str(row["message"]),
                error=str(row["error"]),
                reader=str(row["reader"]),
                lemmas=int(row["lemmas"]),
                meanings=float(row["meanings"]),
                blocked=str(row["blocked"]),
                spent=float(row["spent"]),
                chapters=int(row["chapters"]),
                options=json.loads(row["options"] or "{}"),
                owner=row["owner"],
                home=Path(str(row["home"])),
                kind=str(row["kind"] or "build"),
                # When it was made, not when it was read back. Left out, every job ever
                # run came back made at start-up, so each deploy made the whole history
                # "lately finished" for an hour and the bell filled with it (2026-09-14).
                made=int(row["made"] or 0) or now(),
                finished=int(row["finished"] or 0),
            )
            self.jobs[job.id] = job

    #: Stages a job does not come back from. Reaching one stamps `finished`.
    SETTLED = ("done", "failed", "blocked")

    def remember(self, job: Job) -> None:
        """Put a job's current state on disk. Cheap, and safe to call often."""
        if self.store is None:
            return
        # Stamped here rather than at each of the nine places a stage becomes "done":
        # this is the one road they all travel, and a stamp that depends on somebody
        # remembering to write it is a stamp that is missing from the interesting rows.
        # Written once — the first settled state wins, so a job remembered again after
        # it ended keeps the time it actually ended.
        if not job.finished and job.stage in self.SETTLED:
            job.finished = now()
        self.store.save_job(
            {
                "id": job.id,
                "owner": job.owner,
                "home": str(job.home or self.out),
                "source": job.source,
                "options": json.dumps(job.options, ensure_ascii=False),
                "stage": job.stage,
                "title": job.title,
                "language": job.language,
                "segments": job.segments,
                "chapters": job.chapters,
                "estimate": job.estimate,
                "done": job.done,
                "total": job.total,
                "message": job.message,
                "error": job.error,
                "reader": job.reader,
                "lemmas": job.lemmas,
                "meanings": job.meanings,
                "blocked": job.blocked,
                "spent": job.spent,
                "made": job.made,
                "kind": job.kind,
                "finished": job.finished,
            }
        )

    # -- the queue --------------------------------------------------------------

    def start_workers(self, count: int = WORKERS) -> None:
        for _ in range(count):
            worker = threading.Thread(target=self._drain, daemon=True)
            worker.start()
            self._workers.append(worker)

    def _drain(self) -> None:
        while True:
            job = self.jobs.get(self.queue.get())
            if job is not None:
                self.run(job)
            self.queue.task_done()

    #: A finished build stays on the list this long, so the strip on every page can say
    #: it is ready and hand over the link. The page forgets one the reader has dismissed.
    RECENT_MS = 60 * 60 * 1000

    #: A build longer than this earns an email when it finishes: the reader has most
    #: likely gone to do something else, and the page they started it from is gone.
    LONG_BUILD_MS = 3 * 60 * 1000

    def mine(self, owner: int | None) -> list[dict[str, Any]]:
        """One person's builds, newest first, each saying how far back in the line it is.

        The queue itself is not safely introspectable, so the position is derived: the
        jobs waiting, in the order they were made, plus one for the job being worked on
        — which with one worker is exact. The reader's page can then say "waiting
        behind one other build" rather than leaving a second build to look stuck.
        """
        # Builds only, on both counts: a chat turn is never in this line, so one that is
        # working must not put every waiting build one place further back.
        #
        # Asked of the index rather than of every job ever run. `Jobs.waiting` also
        # sweeps what the loop below would have skipped anyway, so this walks the line
        # and the last hour rather than the whole history (targum-internal#231).
        cutoff = now() - self.RECENT_MS
        builds = self.jobs.waiting(cutoff)
        working = any(job.stage == "working" for job in builds)
        waiting = sorted((job for job in builds if job.stage == "queued"), key=lambda j: j.made)
        position = {job.id: index + (1 if working else 0) for index, job in enumerate(waiting)}
        out: list[dict[str, Any]] = []
        for job in sorted(builds, key=lambda j: j.made, reverse=True):
            if job.owner != owner:
                continue
            if job.stage in ("reading", "ready"):
                # Priced and not yet started: nothing is building, so there is nothing
                # to follow. The page that asked for the price is still showing it.
                continue
            out.append(
                {
                    **job.state(),
                    "behind": position.get(job.id, 0),
                    # Whether putting the strip away can honestly promise an email.
                    "mail": self.can_mail(owner),
                }
            )
        return out

    def can_mail(self, owner: int | None) -> bool:
        """Whether a finished build could reach this person by email at all: hosted,
        with an address to put in the link, and somebody signed in to send it to."""
        return (
            self.mailer is not None
            and bool(self.address)
            and self.store is not None
            and owner is not None
        )

    def tell(self, job: Job) -> None:
        """Email whoever asked for a build that took long enough for them to have left —
        or who put the strip away and was promised one.

        Best effort, and never a reason for a finished build to count as failed: the
        reader is on disk whether or not the message about it arrives.
        """
        # Spelt out rather than asked of `can_mail`, so the checker sees each is there.
        if self.mailer is None or self.store is None or job.owner is None:
            return
        if not self.address or not job.reader:
            return
        if not job.options.get("mail") and now() - job.made < self.LONG_BUILD_MS:
            return
        with contextlib.suppress(Exception):
            person = self.store.person_by_id(job.owner)
            if person is None:
                return
            path = "/".join(quote(part) for part in job.reader.split("/"))
            link = f"{self.address}/reader/{path}" if self.address else ""
            # English first, the title isolated (U+2068 … U+2069): a subject that began
            # with a Hebrew title took "is ready" into its direction and showed as
            # "is ready בראשית" in a mail client (2026-09-14).
            title = f"\u2068{job.title or job.source}\u2069"
            self.mailer.notify(
                person.email,
                f"Ready to read: {title}",
                f"Ready to read: {title}\n\n{link}\n".rstrip() + "\n",
            )

    def enqueue(self, job: Job) -> None:
        job.stage = "queued"
        self.remember(job)
        self.queue.put(job.id)

    def home(self, person: Person | None) -> Path:
        """Where this person's readers live.

        Every home is a directory of its own, including the signed-out one, so that no
        home contains another and the traversal guard below has something real to
        resolve against. Before this, one output directory was shared by whoever could
        reach the server, which on a machine somebody runs themselves is the same
        person and hosted is not.

        Signed out, everyone shares `local`. That is right for a single-user machine
        and wrong for a hosted box, which is why hosted has to require an account —
        the sign-in page in A2 is what closes it.
        """
        return self.out / (f"p{person.id}" if person else "local")

    def _sole_owner(self) -> Path | None:
        """The one person on this machine, if there is exactly one.

        A machine somebody runs themselves has one account on it, and everything built
        on it is theirs — including everything built before they made the account.
        Two or more, and who owns an old build is a guess, so it is not made.
        """
        if self.store is None:
            return None
        people = self.store.db.execute("SELECT id FROM person LIMIT 2").fetchall()
        if len(people) != 1:
            return None
        return self.out / f"p{int(people[0]['id'])}"

    def adopt(self) -> None:
        """Move what was built before homes existed into the home it belongs to.

        Without this, upgrading hides every reader already on disk: the code starts
        looking one directory deeper and finds nothing.

        Where they land is the part that is easy to get wrong, and I got it wrong once:
        everything went to the signed-out home, so the one person on the machine signed
        in and found an empty library. If there is exactly one account here, the
        builds are theirs.
        """
        if not self.out.is_dir():
            return
        local = self.out / "local"
        owner = self._sole_owner()
        home = owner or local
        # Builds already adopted into the signed-out home before this was understood.
        # Only when the person has no home yet, so this is a one-time upgrade and never
        # a way for one account to inherit what other people built while signed out.
        if owner is not None and not owner.exists() and local.is_dir():
            owner.mkdir(parents=True, exist_ok=True)
            for folder in list(local.iterdir()):
                if folder.is_dir():
                    with contextlib.suppress(OSError):
                        folder.rename(free_name(owner, folder.name))
        for folder in list(self.out.iterdir()):
            if not folder.is_dir() or folder.name == "local" or HOME.fullmatch(folder.name):
                continue
            # Any document folder, not only one that reached a rendered reader:
            # "ingested, then never translated" is a real state and orphaning it
            # would lose the work already paid for.
            if not (folder / "document.json").is_file():
                continue
            home.mkdir(parents=True, exist_ok=True)
            try:
                folder.rename(free_name(home, folder.name))
            except OSError:
                # One folder that will not move is not a reason for targum not to
                # start. It stays where it is and is tried again next time.
                continue

    def remaining(self) -> float:
        return max(0.0, self.budget - self.committed)

    @property
    def committed(self) -> float:
        if self.store is None:
            return self._committed
        return self.store.committed(self._since())

    @staticmethod
    def _since() -> int:
        return now() - BUDGET_HOURS * 60 * 60 * 1000

    @staticmethod
    def _month_from() -> int:
        """Midnight UTC on the first of this month, in the milliseconds `job.made` uses.

        UTC rather than the box's zone: the box moves and the ledger does not, and a
        budget that resets an hour early because somebody changed a timezone is a bug
        nobody would find.
        """
        today = datetime.now(UTC)
        first = datetime(today.year, today.month, 1, tzinfo=UTC)
        return int(first.timestamp() * 1000)

    @staticmethod
    def _month_ends(ui: str = "en") -> str:
        """When this month's allowance comes back, as a date a refusal can name, in the
        language `ui` names."""
        today = datetime.now(UTC)
        year, month = (today.year + 1, 1) if today.month == 12 else (today.year, today.month + 1)
        # Month first, as every other date in the product is written ("Monday, September
        # 14" on Learn); "1 October" beside it was a second convention on one screen.
        english = datetime(year, month, 1, tzinfo=UTC).strftime("%B")
        named = said_in(ui, f"date.month.{month}", english)
        return said_in(ui, "date.month-day", "{month} {day}", month=named, day=1)

    def settle(self, job: Job) -> None:
        """Swap what a build reserved for what it spent — and, for a turn of
        conversation, the seconds it was reserved at for the seconds it ran to."""
        if self.store is not None:
            # A turn of conversation and a voice made for a text both come out of the
            # hours, so both settle their seconds (targum-internal#246).
            metered = job.kind in ("chat", "voice")
            self.store.settle(
                job.id, job.spent, length=job.seconds if metered else None, cache=job.cached
            )

    def release(self, job: Job) -> None:
        """Give back what a failed build had claimed but never spent."""
        if self.store is not None:
            return self.store.unclaim(job.id)
        with self.lock:
            self._committed = max(0.0, self._committed - job.estimate)

    def already_over(self, job: Job) -> str:
        """Whether this person is out of money before the work is priced.

        `claim` is the real gate: it reserves an estimate inside a transaction, so two
        builds cannot both pass on the same balance. Buying a chapter cannot use it,
        because pricing one means lemmatising it and that is Stanza inside the request
        that a reader is waiting on.

        So this is the weaker check that path can afford: not "is there room for this",
        which needs a price, but "is there any room at all". It cannot stop a reader
        going over — the chapter that takes them past the line still runs — but it stops
        the one after it, and a chapter is small. Without it the cap does not apply to
        the way a book is actually bought, and the reader prefetches the next chapter at
        60% of this one, so that path spends on its own.
        """
        if job.admin or self.store is None:
            return ""
        day = self._since()
        if self.store.committed(day) >= self.budget:
            return self._out_of("everyone", job.ui)
        if self.account_budget is not None:
            if self.store.committed(day, job.owner) >= self.account_budget:
                return self._out_of("account", job.ui)
        return ""

    def _out_of(self, whose: str, ui: str = "en") -> str:
        """Which ceiling stopped this, and when it lifts, in the language `ui` names.

        A refusal that does not say which limit was hit, or when it stops applying, is
        indistinguishable from the product being broken.
        """
        if whose == "hours":
            # The one refusal a reader was warned about on the pricing page, so it says
            # the same number that page did rather than translating into money — and it
            # reads that number off this library's own allowance rather than the module
            # constant, because a server configured to a different one must not quote a
            # limit it does not enforce. The two agreed while both said ten; they stopped
            # agreeing the moment the constant moved, which is the whole bug.
            allowed = self.upload_seconds if self.upload_seconds is not None else UPLOAD_SECONDS
            return said_in(
                ui,
                "job.out-of.hours",
                "You've used your {hours} hours of audio for this month. They come back on "
                "{date}. Text uploads still work, and the library is always free.",
                hours=f"{allowed / 3600:g}",
                date=self._month_ends(ui),
            )
        if whose == "account":
            # Never "you have read your fill". Nothing here is a limit on reading — text
            # is unlimited and the library is free — so a refusal must not imply that a
            # reader has used something up. This one is a rate limit and says so.
            return said_in(
                ui,
                "job.out-of.account",
                "That's a lot to build at once. Try again in {hours} hours. The library is "
                "always free.",
                hours=BUDGET_HOURS,
            )
        if whose == "talk-hours":
            # The allowance, reached by talking rather than by uploading. The same number
            # the pricing page names, and the same promise that reading carries on.
            allowed = self.upload_seconds if self.upload_seconds is not None else UPLOAD_SECONDS
            return said_in(
                ui,
                "job.out-of.talk-hours",
                "You've used your {hours} hours of audio and conversation for this month. "
                "They come back on {date}. Everything you have stays open, and the library is "
                "always free.",
                hours=f"{allowed / 3600:g}",
                date=self._month_ends(ui),
            )
        if whose == "chat":
            # The same rule for the conversation's own rail: a lot of talking is not a
            # lot of reading, and the shelf is still open.
            return said_in(
                ui,
                "job.out-of.chat",
                "That's a lot of conversation for one day. Try again in {hours} hours. The "
                "library is always free.",
                hours=BUDGET_HOURS,
            )
        return said_in(
            ui,
            "job.out-of.everyone",
            "We've hit our limit for today. Try again in {hours} hours, or open something from "
            "the library.",
            hours=BUDGET_HOURS,
        )

    def _how_long(self, job: Job) -> float:
        """How long a build of this shape has taken here lately, in seconds.

        Asked of the store when the quote is written and never stored on the job: it is
        a fact about the box's recent history, and one kept on the row would be the
        answer as it stood the day that row was written.

        Zero — and the card says nothing — until enough builds have finished to have a
        middle worth quoting.
        """
        if self.store is None:
            return 0.0
        return self.store.how_long_builds_take(language=job.language, audio=job.audio)

    def why_blocked(self, estimate: float, ui: str = "en") -> str:
        """Whether this build may go ahead, in words the page can show."""
        if estimate > self.max_cost:
            # The reader pays by the month and never by the text, so what stops them is
            # a limit on the thing itself, not a sum of money they have never been shown.
            return said_in(
                ui,
                "job.too-long",
                "That's too long to take in one go. Try a shorter piece, or something from the "
                "library.",
            )
        if estimate > self.remaining():
            return said_in(
                ui, "job.all-we-can-take", "That's all we can take on for now. Come back later."
            )
        return ""

    @staticmethod
    def trashed_at(folder: Path) -> int:
        """When this was thrown away, or 0 if it was not."""
        marker = folder / TRASHED
        if not marker.is_file():
            return 0
        try:
            return int(marker.read_text(encoding="utf-8").strip() or 0)
        except (OSError, ValueError):
            return 0

    def trash(self, home: Path, name: str) -> bool:
        """Throw one away. Nothing is deleted yet."""
        folder = self.within(home, name)
        if folder is None or not (folder / "reader" / "index.html").is_file():
            return False
        (folder / TRASHED).write_text(str(now()), encoding="utf-8")
        return True

    def restore(self, home: Path, name: str) -> bool:
        """Change your mind, while there is still something to change it about."""
        folder = self.within(home, name)
        if folder is None:
            return False
        (folder / TRASHED).unlink(missing_ok=True)
        return True

    def used(self, home: Path) -> int:
        """What this home's recordings hold, in bytes, asked of the disk.

        Uploads in flight, media already imported, and the video sidecars a build
        copies beside each reader — the three places a recording's bytes can be. The
        sidecar is a second full copy of every part, and a quota that does not see
        it undercounts a video import by roughly half.
        """
        cached = self._used.get(home)
        if cached is not None and now() - cached[0] < 60_000:
            return cached[1]
        total = 0
        for area in (home / "uploads", *home.glob("*/audio"), *home.glob("*/reader/video")):
            if not area.is_dir():
                continue
            for path in area.rglob("*"):
                try:
                    if path.is_file():
                        total += path.stat().st_size
                except OSError:
                    continue
        self._used[home] = (now(), total)
        return total

    def sweep_uploads(self, home: Path) -> None:
        """Chunked uploads nobody finished, gone after a day.

        Only folders carrying `.meta.json` — the chunked door's own mark. The JSON
        door's uploads live beside them and are the source a document points back at,
        which is exactly what a sweep must never eat.
        """
        uploads = home / "uploads"
        if not uploads.is_dir():
            return
        for folder in uploads.iterdir():
            meta = folder / ".meta.json"
            if not meta.is_file():
                continue
            try:
                made = int(json.loads(meta.read_text(encoding="utf-8")).get("made") or 0)
            except (json.JSONDecodeError, OSError, TypeError, ValueError):
                made = 0
            if now() - made > UPLOAD_TTL_MS:
                shutil.rmtree(folder, ignore_errors=True)
        self._used.pop(home, None)

    def holding(self, home: Path, sha256: str, except_for: Path) -> dict[str, Any] | None:
        """Whether these bytes are already here, and how the page should point at them.

        The same file uploaded twice is one file: a finished chunk upload answers with
        its own id, a recording already imported with its reader. Asked of hashes
        already written down rather than by hashing everything again — a quota's worth
        of re-reading per upload would be the expensive way to save disk.
        """
        uploads = home / "uploads"
        if uploads.is_dir():
            for folder in uploads.iterdir():
                if folder == except_for:
                    continue
                mark = folder / ".sha256"
                if mark.is_file() and mark.read_text(encoding="utf-8").strip() == sha256:
                    if any(f.is_file() and not f.name.startswith(".") for f in folder.iterdir()):
                        return {"upload": folder.name}
        for probe in home.glob("*/audio/probe.json"):
            try:
                if json.loads(probe.read_text(encoding="utf-8")).get("sha256") == sha256:
                    reader = probe.parent.parent / "reader" / "index.html"
                    if reader.is_file():
                        return {"reader": f"{probe.parent.parent.name}/reader/index.html"}
            except (json.JSONDecodeError, OSError):
                continue
        return None

    @staticmethod
    def within(home: Path, name: str) -> Path | None:
        """A folder in this home, and nowhere else.

        The name arrives from a request, so it is resolved and checked rather than
        trusted: `../` in it would otherwise reach another person's Targums.
        """
        try:
            folder = (home / name).resolve()
        except OSError:
            return None
        if home.resolve() not in folder.parents or not folder.is_dir():
            return None
        return folder

    def purge_departed(self) -> list[int]:
        """Delete for real anyone whose grace period is up: their rows, and their home.

        Called at start-up beside `empty_trash`, which is the same kind of promise — a
        deletion that waits, and then happens. `Store.purge` had nothing calling it, so
        "Delete account" ended the session and the grace period never ended anything.
        """
        if self.store is None:
            return []
        gone = self.store.purge()
        for person_id in gone:
            shutil.rmtree(self.out / f"p{person_id}", ignore_errors=True)
        return gone

    def empty_trash(self, days: int = TRASH_DAYS) -> list[str]:
        """Delete for real anything whose week is up. Called at start-up."""
        gone: list[str] = []
        cutoff = now() - days * 24 * 60 * 60 * 1000
        if not self.out.is_dir():
            return gone
        for home in self.out.iterdir():
            if not home.is_dir():
                continue
            for folder in home.iterdir():
                when = self.trashed_at(folder) if folder.is_dir() else 0
                if when and when < cutoff:
                    shutil.rmtree(folder, ignore_errors=True)
                    gone.append(folder.name)
        return gone

    def _reads_of(self, owner: int | None) -> set[str] | None:
        """Which languages a build's owner reads, or None where there is nobody to ask —
        a signed-out build on a machine somebody runs themselves."""
        return None if self.store is None else (self.store.reads(owner) or None)

    @staticmethod
    def targets(folder: Path) -> list[str]:
        """Which languages a targum can be read in, most complete first.

        A folder holds a translation per language it was built into, and the reader's
        picker offers them all. Anything that has to name one — buying the next chapter,
        asking for the meanings — asks here rather than assuming English.

        Onkelos is not one of them. It is read beside the Torah rather than into, and a
        whole book of it beside a whole book of English ties on completeness and sorts
        first by name — which would have made Aramaic the language Genesis opens in and
        the one its next chapter is bought in (`BESIDE`).
        """
        from .models import Translation, read_artifact
        from .translate.prompts import BESIDE

        weight: dict[str, int] = {}
        for path in sorted((folder / "translations").glob("*.json")):
            translation = read_artifact(Translation, path)
            if translation is None or translation.target_language in BESIDE:
                continue
            said = sum(1 for text in translation.segments.values() if text)
            code = translation.target_language
            weight[code] = max(weight.get(code, 0), said)
        return sorted(weight, key=lambda code: (-weight[code], code))

    @staticmethod
    def chapters(folder: Path, target: str = "") -> list[dict[str, Any]]:
        """Every chapter of a targum, and whether it has been translated.

        Derived from the artifacts rather than recorded anywhere: a chapter is ready when
        every one of its segments has a translation. A second place saying so would drift
        from the truth the first time a build died between writing them.

        `target` asks about one language. Without it the question is "is there anything to
        read here", which is what a shelf wants; with it, "is there anything to read here
        in Russian" — which is what buying the next chapter has to ask, or a book whose
        English runs to chapter nine would refuse to sell chapter two in Russian on the
        grounds that it already exists.
        """
        from .models import SegmentedDocument, Translation, read_artifact
        from .render.builder import split_sections

        segmented = read_artifact(SegmentedDocument, folder / "segments.json")
        if segmented is None:
            return []
        sections = split_sections(segmented)
        if len(sections) < 2:
            # One section is a targum, not a book. A tree of one is furniture.
            return []
        done: set[str] = set()
        for path in sorted((folder / "translations").glob("*.json")):
            translation = read_artifact(Translation, path)
            if translation is None:
                continue
            if target and translation.target_language != target:
                continue
            done |= {sid for sid, text in translation.segments.items() if text}
        return [
            {
                "number": section.number,
                "title": section.title,
                "file": section.filename,
                "sentences": len(section.segment_ids),
                "ready": bool(section.segment_ids) and all(s in done for s in section.segment_ids),
            }
            for section in sections
        ]

    #: What a text this reader added is, worked out from where it came from. A catalogue
    #: text says what it is itself; everything else has only its address to go on, and an
    #: address is enough for the one distinction that matters here — an article somebody
    #: pasted in this morning against a book.
    OWN_KINDS = (("http://", "article"), ("https://", "article"), ("sefaria:", "prose"))

    @staticmethod
    @lru_cache(maxsize=512)
    def _own_difficulty(path: str, changed: float, language: str) -> int:
        """How hard a text nobody catalogued is, counted the same way the catalogue is.

        Keyed on the file's own modification time, so a rebuilt text is recounted and an
        unchanged one is counted once for the life of the process. Reading a whole
        annotation is not free — a book's worth is megabytes — and the library page is
        drawn every time somebody opens it.
        """
        from .annotate.base import NOT_VOCABULARY
        from .annotate.frequency import FrequencyBands
        from .models import Annotation, read_artifact

        annotation = read_artifact(Annotation, Path(path))
        if annotation is None:
            return 0
        bands = FrequencyBands()
        code = language.split("-")[0].lower()
        if not bands.supports(code):
            return 0
        looked_up = total = 0
        seen: dict[str, int] = {}
        for tokens in annotation.tokens.values():
            for token in tokens:
                if token.pos in NOT_VOCABULARY:
                    continue
                band = seen.get(token.lemma)
                if band is None:
                    band = seen[token.lemma] = bands.band(token.lemma, code)
                total += 1
                looked_up += band >= 4
        return round(looked_up / total * 100) if total else 0

    def _shape(self, folder: Path, source: str, language: str, words: int) -> dict[str, Any]:
        """What this text is, for a library that sorts and filters by it.

        A catalogue text is described by the catalogue: those numbers are measured off
        the whole text by `scripts/measure_difficulty.py` and are better than anything
        that could be worked out here. Everything else is the reader's own.
        """
        from . import catalogue as catalogue_module
        from . import spoken
        from .audio import manifest as manifest_module

        entry = next((e for e in catalogue_module.CATALOGUE if e.source == source), None)
        if entry is not None:
            return {
                "kind": entry.kind.value,
                "register": entry.register.value,
                # What the text is about, so the arrival's subject doors can be answered
                # from the shelf rather than from a second request (2026-09-17).
                "tags": sorted(tag.value for tag in entry.tags),
                "difficulty": entry.difficulty,
                "minutes": entry.minutes,
                "spoken": spoken.is_spoken(source),
                "video": spoken.is_video(source),
                # Whether it *began* as something said (targum-internal#337). `spoken` is
                # true of most of the shelf — the Tanakh has a reading attached, every
                # scene is voiced — and those are texts somebody reads with a voice beside
                # them. A talk is the other thing: the recording is the work and the text
                # is what was said. It is what decides "Continue listening".
                "heard": entry.kind is catalogue_module.Kind.talk,
                "entry": entry.id,
                "english": entry.english,
                # When it joined the catalogue, so the shelf can say what is new
                # (targum-internal#315). An upload has no such date and needs none: the
                # reader's own row already carries `built`, which is when it arrived for
                # them, and that is the more honest answer for a text only they have.
                "added": entry.added,
                "drawn": any(
                    (self.out / "thumbs" / (entry.id + suffix)).is_file() for suffix, _ in THUMBS
                ),
            }
        manifest = folder / manifest_module.MANIFEST
        # Kept its pictures, by the manifest's own word — the sidecar folder is a
        # copy the build remakes, and the manifest is the claim.
        video = spoken.is_video(source) or bool(
            self.remembered.get(
                folder, "video", [manifest], lambda: manifest_module.keeps_video(folder)
            )
        )
        # Nothing said is better than something wrong. This was "prose" until 2026-09-18,
        # which the library labels "Bible narrative", so every upload with no address to
        # go on — a file, a picture, a recording — was filed as one of the Bible's story
        # books.
        kind = ""
        for prefix, named in self.OWN_KINDS:
            if source.startswith(prefix):
                kind = named
                break
        if video:
            # Somebody talking to a camera, and the text is what they said: the kind the
            # catalogue made for its own videos. Before the address, because a YouTube
            # link is https and is not journalism. Only video: narration writes a
            # manifest too, so a recording alone does not make an article a talk.
            kind = "talk"
        if source.endswith(".chat"):
            # A conversation read back: shaped like a scene, filed like one.
            kind = "dialogue"
        annotation = folder / "annotation.json"
        difficulty = self.remembered.get(
            folder,
            f"difficulty:{language}",
            [annotation],
            lambda: (
                self._own_difficulty(str(annotation), annotation.stat().st_mtime, language)
                if annotation.is_file()
                else 0
            ),
        )
        return {
            "kind": kind,
            "register": "biblical" if is_biblical(source) else "modern",
            # A reader's own text is not filed by subject: nothing has read it to say
            # what it is about, and guessing would be worse than the empty list.
            "tags": [],
            "difficulty": difficulty,
            "minutes": max(1, round(words / 130)),
            # The claim is made by whatever is actually there — for an import, the
            # manifest sitting beside the reader.
            "spoken": spoken.is_spoken(source) or manifest.is_file(),
            "video": video,
            # An import with a manifest beside it came in as a recording: a podcast, a
            # voice note, a film. The text is its transcript, and the reader came to hear it.
            "heard": manifest.is_file(),
            "entry": "",
            # An upload has no English title anywhere: the reader gave it a Hebrew one
            # and that is what every page shows.
            "english": "",
            "drawn": False,
        }

    def talks(self, home: Path, person_id: int | None) -> bool:
        """Whether this reader is offered a conversation in Hebrew.

        One conversation, always in Hebrew (2026-09-06) — for a reader who has modern
        Hebrew to hold it in. A reader whose every text is scripture is not offered one:
        nobody converses in the Hebrew of Judges, and a model writing it graded to a
        ledger of biblical words would be pastiche on the one shelf where every line must
        be right. That reader's box finds and answers in English, about the text.

        Decided from the shelf, because the ledger is one bucket per language and cannot
        say which Hebrew a word came from: modern if any text of their own is modern, or
        any modern text on the shared shelf has been opened; scripture-only if what they
        have is scripture and nothing else; and a reader with nothing yet is offered the
        conversation, since nothing says otherwise.
        """
        registers: set[str] = set()
        for reader in self.readers(home):
            registers.add(str(reader.get("register") or ""))
        if "modern" in registers:
            return True
        if self.store is not None and person_id is not None:
            opened = self.store.opened_documents(person_id)
            for reader in self.readers(self.shared):
                if reader.get("document") in opened:
                    registers.add(str(reader.get("register") or ""))
        if "modern" in registers:
            return True
        return "biblical" not in registers

    def built_from(self, home: Path, source: str) -> str | None:
        """The folder holding this reader's copy of one source, or None.

        `readers()` answers this too, and answers a great deal else with it: every
        chapter, every share, every cover, for every text on the shelf. That is the right
        shape for a page being drawn and the wrong one for a link being followed — it
        took seventeen seconds on a cold box, and a link is something somebody is waiting
        on. This reads one cached fact per folder and stops at the first match.
        """
        if not home.is_dir():
            return None
        for folder in sorted(home.iterdir()):
            if not (folder / "reader" / "index.html").is_file():
                continue
            # A text in the bin is not on the shelf, and sending somebody into it would
            # be answering a question they did not ask.
            if self.trashed_at(folder):
                continue
            document = folder / "document.json"
            facts = self.remembered.get(
                folder, "document", [document], partial(self._document_facts, document)
            )
            if facts.get("source") == source:
                return folder.name
        return None

    def readers(self, home: Path, trashed: bool = False) -> list[dict[str, Any]]:
        """Everything built, newest first, with what the page needs to show progress."""
        found: list[dict[str, Any]] = []
        if not home.is_dir():
            return found
        for folder in home.iterdir():
            index = folder / "reader" / "index.html"
            if not index.is_file():
                continue
            when = self.trashed_at(folder)
            if bool(when) != trashed:
                continue
            # Every read below goes through `remembered`: the answers are small and the
            # files they come from are not (2026-09-14, Learn waiting 31 s on a cold box).
            remember = self.remembered.get
            document = folder / "document.json"
            facts = remember(
                folder, "document", [document], partial(self._document_facts, document)
            )
            title = facts["title"] or folder.name
            language = facts["language"]
            words = facts["words"]
            translations = sorted((folder / "translations").glob("*.json"))
            chapters = remember(
                folder,
                "chapters",
                [folder / "segments.json", *translations],
                partial(self.chapters, folder),
            )
            sections = remember(
                folder,
                "sections",
                # A section added or taken away changes the folder's own time.
                [folder / "reader"],
                partial(self._sections, folder),
            )
            found.append(
                {
                    "name": folder.name,
                    "title": title,
                    "author": facts["author"],
                    "language": language,
                    "languages": facts["contains"] or ([language] if language else []),
                    # And which languages it can be read *into*. A text built twice is
                    # one text with two translations, and a shelf that said only what
                    # language it was in could not tell a reader of two which of them
                    # this one would open in.
                    "targets": remember(
                        folder, "targets", translations, partial(self.targets, folder)
                    ),
                    "document": facts["content_hash"],
                    "words": words,
                    **self._shape(folder, facts["source"], language, words),
                    "sections": sections or 1,
                    "chapters": chapters,
                    "readyChapters": sum(1 for c in chapters if c["ready"]),
                    "trashed": when,
                    # How long is left, so the page can say it rather than imply it.
                    "goesIn": max(0, TRASH_DAYS - (now() - when) // (24 * 60 * 60 * 1000))
                    if when
                    else 0,
                    "built": int(index.stat().st_mtime),
                }
            )
        found.sort(key=lambda reader: reader["built"], reverse=True)
        return found

    @staticmethod
    def _sections(folder: Path) -> int:
        return len(list((folder / "reader").glob("sec-*.html")))

    @staticmethod
    def _document_facts(document: Path) -> dict[str, Any]:
        """What the shelf takes from a reader's document, which is the whole text."""
        facts: dict[str, Any] = {
            "title": "",
            "author": "",
            "language": "",
            "contains": [],
            "source": "",
            "words": 0,
            "content_hash": "",
        }
        if not document.is_file():
            return facts
        try:
            data = json.loads(document.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return facts
        language = data.get("language", "")
        blocks = data.get("blocks", [])
        facts.update(
            title=data.get("title") or "",
            # Who wrote it, which for the weekly is how it was made. It rides on the
            # document rather than being looked up per row, so the shelf cannot show an
            # issue without also showing that a model compiled it.
            author=data.get("author", ""),
            language=language,
            # Every language the text is written in, its blocks' own included: a Daniel
            # is Hebrew and Aramaic, and shows under both (2026-09-13).
            contains=sorted(
                ({language} | {str(b.get("language")) for b in blocks if b.get("language")}) - {""}
            ),
            source=data.get("source", ""),
            words=sum(len(str(b.get("text", "")).split()) for b in blocks),
            # The same identity the reader keeps its word list under, so the page can say
            # how far through each text you are.
            content_hash=data.get("content_hash", ""),
        )
        return facts

    @staticmethod
    def can_draw() -> bool:
        """Whether this deployment has an image key. A page with none never offers."""
        from . import covers as covers_module

        return covers_module.ready()

    def prepare(self, job: Job) -> None:
        """Ingest and segment, which costs nothing, then price the rest."""
        try:
            from urllib.parse import urlparse

            from .video import instagram as instagram_module

            if instagram_module.is_post(job.source) and self._prepare_post(job):
                return
            if urlparse(job.source).scheme in ("http", "https"):
                from .audio import episode as episode_module
                from .video import youtube as youtube_module

                if (urlparse(job.source).hostname or "").lower() in youtube_module.HOSTS:
                    # By name, and to its own door — never falling through to the line
                    # below. The generic ingester would read the watch page and import
                    # the show notes as the text, which is the reason this branch has
                    # always existed and the one thing that must not change.
                    return self._prepare_youtube(job)
                from .video import hosts as hosts_module

                host = hosts_module.host_for(job.source)
                if host is hosts_module.INSTAGRAM:
                    # Its own door for the same reason: the generic ingester would read
                    # the login wall and call it the text (targum-internal#255).
                    return self._prepare_reel(job)
                if host is hosts_module.TIKTOK:
                    return self._prepare_tiktok(job)
                if host is not None:
                    # A service we can name and cannot fetch from: TikTok, Vimeo, Reddit,
                    # Facebook. Said by name with the way that works, rather than read
                    # as an article and answered with "save the page as .txt".
                    job.error = said_in(
                        job.ui,
                        "job.video-host-closed",
                        "{service} doesn't let us fetch its videos. Download the video "
                        "there and drop the file here.",
                        service=host.name,
                    )
                    job.stage = "failed"
                    return
                if episode_module.sounds_like_audio(job.source):
                    # A recording on the other end of a link is not downloaded inside
                    # the request — that is a gigabyte on a click that only asked for a
                    # price. The estimate leans on what the address says; the worker
                    # fetches when the reader has said yes.
                    return self._prepare_episode(job, episode_module.Episode(audio_url=job.source))
                try:
                    found = episode_module.find(job.source)
                except UnsupportedSource as refusal:
                    # This is Library.prepare, not the handler: a refusal travels on
                    # the job, the way every prepare failure does.
                    job.error = f"{refusal.message} {refusal.hint or ''}".strip()
                    job.stage = "failed"
                    return
                if found is not None:
                    return self._prepare_episode(job, found)
            # A text that arrived as pages is read before it is priced: the pictures by
            # the model (the one spend before a card, reserved and settled here), a
            # PDF's text layer by nothing that costs. Either way the card can then show
            # the first lines as read, which for a picture is the only honest title.
            refused = self._read_pages(job)
            if refused:
                job.blocked = refused
                job.stage = "blocked"
                return
            builder = self._builder(job)
            # Priced for what the build will buy, which for a book is one chapter. The
            # cap then applies to a chapter, not to a novel — which is the difference
            # between "no books at all" and "no chapter over two dollars".
            plan = builder.plan(chapters=FIRST_CHAPTERS)
            job.title = plan.document.title or job.source
            job.language = plan.document.language
            if not job.options.get("from") and not self._reads_language(job.language):
                # Nobody said, and the guess landed on a language targum does not read —
                # Latin script with nothing chosen guesses English. Asked rather than
                # built: the door that checks a chosen language cannot check a guess.
                from .translate.prompts import language_name

                job.error = (
                    f"This looks like {language_name(job.language)}, and we can't read that "
                    "yet. Choose the language it's in."
                )
                job.stage = "failed"
                return
            job.segments = len(plan.segmented.segments) if plan.segmented else 0
            job.known_share = self._known_share(job, plan.document)
            job.chapters = plan.chapters
            job.estimate = plan.estimated_cost
            if plan.audio is not None:
                job.audio = True
                job.seconds = plan.audio.duration
                job.parts = plan.audio.parts
                job.transcription = plan.audio.transcription
            # The progress bar counts what is being translated now, not the whole book.
            job.total = plan.buying or job.segments
            usable, _ = builder.provider.available()
            if builder.machine and plan.carried is None and not usable:
                # Checked here, not at the first API call. The estimate falls back to a
                # character count when there is no key, so without this the page quotes
                # a plausible price, takes the click, and only then fails.
                #
                # And never for a text that brought its own English. A dialogue's was
                # written with the scene and a curated video's was bought before it
                # shipped, so neither needs a key — and a box that has lost its key
                # should still hand a reader the whole shelf that costs nothing.
                job.blocked = said_in(job.ui, "job.no-key", NO_KEY)
            else:
                job.usually = self._how_long(job)
                job.blocked = self.why_blocked(job.estimate, job.ui)
            if not job.blocked and builder.gloss and plan.segmented is not None:
                # Glossing is priced from the real count of distinct dictionary forms,
                # which means lemmatizing first. Only worth the wait once the
                # translation itself has cleared the cap.
                job.stage = "looking up words"
                cost, job.lemmas = self._gloss_cost(builder, plan.segmented, plan.buying_segments)
                job.meanings = cost
                job.estimate += cost
                job.usually = self._how_long(job)
                job.blocked = self.why_blocked(job.estimate, job.ui)
            job.stage = "blocked" if job.blocked else "ready"
        except TargumError as error:
            job.error = f"{error.message} {error.hint or ''}".strip()
            job.stage = "failed"
        except Exception as error:  # a bad file should not take the server down
            # Said plainly, with the library's own words kept for the back office: a
            # page that refused us came to the bell as "Client error '403 Forbidden' for
            # url …, For more information check: developer.mozilla.org" (2026-09-14).
            traceback.print_exc()
            incidents_module.record(self.incidents, "prepare", error, job=job.id)
            job.error = unreadable(error)
            job.stage = "failed"

    @staticmethod
    def _reads_language(language: str) -> bool:
        """Whether a language, however it is tagged, is one targum reads."""
        from .segment import stanza_code
        from .translate.prompts import READING

        return stanza_code(language or "") in {code for code, _ in READING}

    def _known_share(self, job: Job, document: Any) -> float | None:
        """How much of a text the reader already has, at quote time (targum-internal#244):
        the ledger's known forms and the commonest words against the text's tokens. The
        card says it in words; the model is given the number. Nothing for a signed-out
        build, a text that is not Hebrew, or one too short to measure."""
        if self.store is None or job.owner is None:
            return None
        if str(getattr(document, "language", "") or "").split("-")[0] not in ("he",):
            return None
        from .chat import hebrew as hebrew_module

        forms = self.store.known_forms(job.owner, "he") | set(hebrew_module.common_words())
        text = "\n".join(str(getattr(block, "text", "") or "") for block in document.blocks)
        return level_module.known_share(text, forms)

    def _read_pages(self, job: Job) -> str:
        """Read a source that arrived as pages, or say why it may not be read.

        Pictures cost: they are reserved against the same rails a build is claimed on,
        at `vision.PAGE_RESERVE` a page still unread, read, and settled to what the API
        charged — the reader's file choice is the consent, and the ceiling is thirty
        pages (targum-internal#217). Every picture read is cached by its bytes, so the
        build that follows, and a second drop of the same screenshot, read for nothing.
        A PDF's text layer is free and is only described here: how many pages, how many
        lines came out mixed, and the first lines for the card.

        Returns the sentence that blocks the card, or "" when the pages were read.
        Anything else wrong raises, and `prepare` writes it on the job like every
        other failure.
        """
        from . import vision
        from .annotate.gloss import GLOSS_MODEL
        from .ingest import pdf as pdf_module
        from .ingest import picture as picture_module

        source = Path(job.source)
        if source.is_file() and source.suffix.lower() == ".pdf":
            pages = pdf_module.page_lines(source)
            job.pages = len(pages)
            job.doubtful = pdf_module.doubtful_lines(pages)
            job.excerpt = excerpt_of([line for lines in pages for line in lines])
            return ""
        if not picture_module.is_pictures(source):
            return ""
        paths = picture_module.pages_of(source)
        if len(paths) > MAX_PAGES:
            raise TargumError(
                f"That's {len(paths)} pictures. We can read up to {MAX_PAGES} at a time."
            )
        job.pages = len(paths)
        usable, _ = vision.can_read()
        if not usable:
            return said_in(job.ui, "job.no-key", NO_KEY)
        waiting = vision.unread(paths, GLOSS_MODEL)
        usage = Usage()
        if waiting:
            job.estimate = vision.reserve(waiting)
            refused = self.claim(job)
            if refused:
                job.estimate = 0.0
                return refused
            job.stage = "reading"
            self.remember(job)
            try:
                reads = vision.read_pages(paths, usage=usage, model=GLOSS_MODEL)
            finally:
                # Whatever was read was paid for, whether or not the rest arrived. The
                # reservation becomes the receipt now, not at the end of a build the
                # reader may never press for.
                job.reading = usage.cost()
                job.spent = job.reading
                job.estimate = 0.0
                self.settle(job)
        else:
            reads = vision.read_pages(paths, usage=usage, model=GLOSS_MODEL)
        job.doubtful = sum(read.doubtful for read in reads)
        job.conversation = any(read.conversation for read in reads)
        job.excerpt = excerpt_of([line for read in reads for line in read.lines])
        return ""

    #: Manual subtitle tracks worth looking for before paying to transcribe. Hebrew in
    #: both spellings YouTube uses — `iw` is the old ISO code and half the Israeli
    #: catalogue is still filed under it, which is why `fetch_subtitles` asks for both.
    SUBTITLES = ("he", "iw")

    def _prepare_youtube(self, job: Job) -> None:
        """A YouTube address, priced through `_prepare_video`."""
        from .video import youtube as youtube_module

        self._prepare_video(
            job,
            vetted=youtube_module.is_youtube,
            described=youtube_module.describe,
            unavailable=said_in(
                job.ui, "job.youtube-unavailable", "We can't fetch from YouTube here."
            ),
            subtitled=True,
        )
        if job.stage != "failed":
            job.options["youtube"] = True

    def _prepare_reel(self, job: Job) -> None:
        """An Instagram reel, priced through `_prepare_video` (targum-internal#255)."""
        from .video import instagram as instagram_module

        self._prepare_video(
            job,
            vetted=instagram_module.is_reel,
            described=instagram_module.describe,
            unavailable=said_in(
                job.ui, "job.instagram-unavailable", "We can't fetch from Instagram here."
            ),
            # Instagram never says how long a reel runs; `describe` reads the header, and
            # where even that is silent the reel is priced long rather than refused as a
            # live stream, which a reel never is.
            unmeasured=instagram_module.GUESS_S,
        )

    def _prepare_tiktok(self, job: Job) -> None:
        """A TikTok video, priced through `_prepare_video` (targum-internal#255).

        A shared link names no video until it is followed. yt-dlp follows it at the quote,
        and the job then carries the one canonical address it found, so the build fetches
        the same video and the reader links home to it.
        """
        from .video import tiktok as tiktok_module

        def described(url: str) -> dict[str, Any]:
            info = tiktok_module.describe(url)
            found = tiktok_module.home_url(str(info.get("webpage_url") or ""))
            if found:
                job.source = found
            return info

        self._prepare_video(
            job,
            vetted=tiktok_module.is_tiktok,
            described=described,
            unavailable=said_in(
                job.ui, "job.tiktok-unavailable", "We can't fetch from TikTok here."
            ),
        )

    def _prepare_post(self, job: Job) -> bool:
        """An Instagram post, read off its embed page (targum-internal#255).

        A post that is a film goes to the reel's door. One that is pictures becomes a
        text: its caption, with the author as its byline and the post as its home, and —
        only when the reader pressed for it — the words in its pictures after it, read on
        the same terms as pictures brought by the `+` (`_read_pages`: reserved, claimed,
        settled, thirty at most). The caption alone costs nothing to read.

        Returns True when the job is settled here — a film, a refusal — and False when
        `job.source` is now the caption's text, for the text path below to price.
        """
        import secrets

        from . import vision
        from .annotate.gloss import GLOSS_MODEL
        from .video import instagram as instagram_module

        post = instagram_module.backup(job.source)
        if post is None or post.video:
            # A film, or a page that would not say: yt-dlp's door, with its own backup.
            self._prepare_reel(job)
            return True
        address = job.source
        job.options["came_from"] = address
        job.options["post_pictures"] = len(post.pictures)
        wanted = bool(job.options.get("pictures")) and bool(post.pictures)
        if not post.caption.strip() and not wanted:
            job.error = said_in(
                job.ui,
                "job.post-only-pictures",
                "That post's words are all in its pictures. Read the pictures to bring it in.",
            )
            job.stage = "failed"
            return True
        folder = Path(job.home or self.out) / "uploads" / secrets.token_hex(8)
        text = instagram_module.caption_text(post)
        if wanted:
            paths = instagram_module.pictures_into(post, folder / "pictures")
            job.source = str(folder / "pictures")
            refused = self._read_pages(job)
            if refused:
                job.blocked = refused
                job.stage = "blocked"
                return True
            # Read a moment ago and cached by their bytes, so this costs nothing: it is
            # the same words `_read_pages` paid for, put after the caption.
            reads = vision.read_pages(paths, usage=Usage(), model=GLOSS_MODEL)
            text = "\n\n".join([text.rstrip(), *(read.text for read in reads)]) + "\n"
        target = folder / f"{post.code}.txt"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        job.source = str(target)
        return False

    def _prepare_video(
        self,
        job: Job,
        *,
        vetted: Callable[[str], bool],
        described: Callable[[str], dict[str, Any]],
        unavailable: str,
        unmeasured: float = 0.0,
        subtitled: bool = False,
    ) -> None:
        """Price a video from what yt-dlp can say about it, before a byte of it moves.

        The reader's act, not ours: they paste the address and press the button, the
        fetch is charged against their own hours, and what comes back is their private
        import and never the catalogue (targum-internal#126). That is the distinction
        #136 turned on, and it is the whole of what makes this door different from a
        harvest — so nothing here may be reached except by a reader who asked for it.

        Metadata only, for the reason `_prepare_episode` records: a click that asked for
        a price must not download a video. `yt-dlp -J` is a few hundred kilobytes of
        JSON, and the duration in it is what the estimate and the hours both lean on.
        """
        from .screen import from_ytdlp
        from .video import MAX_VIDEO_DURATION_S, ytdlp_available

        # What the address is, before what this box has. A playlist is a playlist on a
        # machine with no yt-dlp at all, and telling a reader to install something before
        # telling them targum takes one video at a time answers a question they did not
        # ask. It is also the harvest guard, and a guard that depends on what is
        # installed is not one.
        try:
            vetted(job.source)
        except TargumError as refusal:
            job.error = f"{refusal.message} {refusal.hint or ''}".strip()
            job.stage = "failed"
            return

        usable, hint = ytdlp_available()
        if not usable:
            # Said as a fact about this box rather than as the reader's mistake, and it
            # names the path that still works on their own machine.
            job.error = f"{unavailable} {hint}"
            job.stage = "failed"
            return
        try:
            found = from_ytdlp(described(job.source))
        except TargumError as refusal:
            # An age gate, a private video, a region block — yt-dlp's own sentence is
            # better than anything written here, and a refusal travels on the job the
            # way every prepare failure does.
            job.error = f"{refusal.message} {refusal.hint or ''}".strip()
            job.stage = "failed"
            return
        if not found.duration and unmeasured:
            from dataclasses import replace

            found = replace(found, duration=unmeasured)
        if not found.duration:
            # A live stream has no duration, and neither has a premiere that has not
            # started. Both would price at nothing and then run until the disk filled.
            job.error = said_in(
                job.ui,
                "job.live-stream",
                "That video has no length yet. We can't bring in a live stream.",
            )
            job.stage = "failed"
            return
        if found.duration > MAX_VIDEO_DURATION_S:
            hours = MAX_VIDEO_DURATION_S / 3600
            job.error = said_in(
                job.ui,
                "job.video-too-long",
                "That video is longer than {hours} hours. That's more than we can take at once.",
                hours=f"{hours:g}",
            )
            job.stage = "failed"
            return

        job.title = found.title.strip() or job.source
        # Charged against the hours, like every other recording: `claim` spends
        # `job.seconds` against the month's allowance when `job.audio` is set, so the
        # rate limit this needed is the one the pricing page already promised rather
        # than a second one invented here.
        job.audio = True
        job.seconds = found.duration
        job.parts = max(1, round(job.seconds / 720))

        # A track somebody wrote is a transcript; one YouTube guessed is not, and
        # `from_ytdlp` counts only the first. Where there is one the hearing is free and
        # the whole import is the price of the English — which is the difference between
        # twenty cents and two dollars on a ten-minute lesson.
        # YouTube's alone: the build fetches a written track only from YouTube
        # (`Build._fetch_youtube_transcript`), so a track another host lists would price
        # a hearing the build then buys anyway.
        written = (
            [tag for tag in found.subtitles if tag.split("-")[0] in self.SUBTITLES]
            if subtitled
            else []
        )
        job.options["subtitles"] = bool(written)
        self._price_recording(job, transcribed=not written)

    def _price_recording(self, job: Job, *, transcribed: bool) -> None:
        """What a recording of `job.seconds` costs to hear and to render into English.

        The arithmetic `_prepare_episode` does, lifted out so the two doors quote the
        same coin. Both buy a part at a time, so both price a part.
        """
        import math

        from .audio import SPEECH_WORDS_PER_MINUTE, TOKENS_PER_SPOKEN_WORD, WORDS_PER_SENTENCE
        from .transcribe import PRICES, default_name
        from .transcribe import build as build_transcriber
        from .translate.anthropic_provider import AnthropicProvider

        rate = 0.0
        if transcribed:
            try:
                rate = float(build_transcriber(default_name()).price_per_minute())
            except Exception:  # noqa: BLE001 - an unkeyed transcriber prices at nothing
                rate = max(PRICES.values()) if PRICES else 0.0
        first = job.seconds / max(1, job.parts) / 60
        transcription = first * (rate + _punctuation_rate(rate))
        words = first * SPEECH_WORDS_PER_MINUTE
        batches = max(1, math.ceil(words / WORDS_PER_SENTENCE / 20))
        translating = AnthropicProvider(model=HOSTED_MODEL).estimate_from_counts(
            words * TOKENS_PER_SPOKEN_WORD, batches
        )
        job.transcription = round(transcription, 4)
        job.estimate = round(transcription + translating, 4)
        job.usually = self._how_long(job)
        job.blocked = self.why_blocked(job.estimate, job.ui)
        job.stage = "blocked" if job.blocked else "ready"

    def _prepare_episode(self, job: Job, found: Any) -> None:
        """Price an episode from the feed's own claims, before a byte of audio moves.

        The feed says how long it runs, or says nothing; an hour stands in where it
        says nothing, which errs on the side the budget wants. Hearing is bought a
        part at a time either way, so the first click is bounded by a part.
        """
        from .audio import SPEECH_WORDS_PER_MINUTE, TARGET_MINUTES_GUESS
        from .transcribe import PRICES, default_name
        from .transcribe import build as build_transcriber

        job.title = found.title or job.source
        job.audio = True
        job.seconds = float(found.seconds or 0.0) or TARGET_MINUTES_GUESS * 60.0
        job.parts = max(1, round(job.seconds / 720))
        rate = 0.0
        try:
            chosen = build_transcriber(default_name())
            rate = float(chosen.price_per_minute())
        except Exception:  # noqa: BLE001 - an unkeyed transcriber prices at nothing
            rate = max(PRICES.values()) if PRICES else 0.0
        first = job.seconds / job.parts / 60
        transcription = first * (rate + _punctuation_rate(rate))
        # The first part's words, guessed at speech rate and priced on the arithmetic
        # the real estimate uses — the same coin, counted the same way.
        import math

        from .audio import TOKENS_PER_SPOKEN_WORD, WORDS_PER_SENTENCE
        from .translate.anthropic_provider import AnthropicProvider

        words = first * SPEECH_WORDS_PER_MINUTE
        batches = max(1, math.ceil(words / WORDS_PER_SENTENCE / 20))
        translating = AnthropicProvider(model=HOSTED_MODEL).estimate_from_counts(
            words * TOKENS_PER_SPOKEN_WORD, batches
        )
        job.transcription = round(transcription, 4)
        job.estimate = round(transcription + translating, 4)
        if found.transcript_url:
            job.transcription = 0.0
            job.estimate = round(translating, 4)
        job.options["episode"] = True
        job.usually = self._how_long(job)
        job.blocked = self.why_blocked(job.estimate, job.ui)
        job.stage = "blocked" if job.blocked else "ready"

    def claim(self, job: Job) -> str:
        """Check the budget and spend from it in one step.

        Two builds started at once would otherwise both see the same money left and
        both pass, which is exactly how a budget gets overrun.
        """
        if job.estimate > self.max_cost:
            return self.why_blocked(job.estimate, job.ui)
        if self.store is not None:
            # One transaction decides and spends. It holds across processes as well as
            # threads, which the lock below never did.
            # An admin is not held to the per-account rails. They exist to stop a reader
            # running up somebody else's bill, and the person paying it is not that
            # reader. The box ceiling below is not waived: that one is the runaway guard,
            # and a loop at three in the morning does not care whose account it is on.
            admin = bool(job.admin)
            refused = self.store.claim(
                job.id,
                job.estimate,
                self.budget,
                self._since(),
                owner=job.owner,
                per_account=None if admin else self.account_budget,
                month_from=self._month_from(),
                # Only a recording spends the hours. A text upload is any length and
                # costs no clock time, so it is not charged against them.
                length=job.seconds if job.audio else 0.0,
                per_month_length=None if admin else self.upload_seconds,
            )
            if not refused:
                return ""
            return self._out_of(refused, job.ui)
        with self.lock:
            blocked = self.why_blocked(job.estimate, job.ui)
            if not blocked:
                self._committed += job.estimate
            return blocked

    def claim_turn(self, job: Job, kind: str = "chat") -> str:
        """Reserve one turn of conversation against the rails, or say which refused.

        The same transaction a build takes, narrowed: the per-account ceiling is the
        chat's own (`CHAT_BUDGET`, over rows of kind `chat`), and the box ceiling is the
        one every kind of work shares. Admins pass the account rail as they do for
        builds, and never the box one.
        """
        if self.store is None:
            with self.lock:
                if job.estimate > self.remaining():
                    return self._out_of("everyone", job.ui)
                self._committed += job.estimate
                return ""
        admin = bool(job.admin)
        refused = self.store.claim(
            job.id,
            job.estimate,
            self.budget,
            self._since(),
            owner=job.owner,
            per_account=None if admin else self.chat_budget,
            kind=kind,
            # Conversation comes out of the eight hours (decided 2026-09-05): the same
            # sum a recording's seconds land in, so there is one ledger and not two. A
            # voice made for a text (kind `voice`, targum-internal#246) comes out of it
            # the same way.
            month_from=self._month_from(),
            length=job.seconds,
            per_month_length=None if admin else self.upload_seconds,
        )
        if not refused:
            return ""
        if refused == "hours":
            return self._out_of("talk-hours", job.ui)
        return self._out_of("chat" if refused == "account" else refused, job.ui)

    @staticmethod
    def _gloss_cost(
        builder: Build, segmented: SegmentedDocument, buying: list[Segment]
    ) -> tuple[float, int]:
        """What the word meanings will cost, for the chapters being bought.

        Two things this used to do to every text it priced, both of them over the whole
        book however little of it was being bought. It quoted for meanings the build
        would not look up yet — Altneuland's first chapter costs $0.21 to translate and
        was quoted $4.23 of meanings, which the cap then refused, so a long book could
        not be opened at all. And it lemmatised five thousand sentences inside the
        request that draws the card: forty-eight seconds of Stanza before the page could
        say anything.

        The count is worth returning rather than discarding: it is what lets the page say
        how long they will keep arriving for after the reader opens.
        """
        from .annotate import Annotator, biblical, lemma
        from .annotate import dictionary as dictionary_module
        from .annotate.gloss import AnthropicGlosses, estimate, unique_lemmas, unpaid

        run = SegmentedDocument(
            document_hash=segmented.document_hash,
            language=segmented.language,
            segmenter=segmented.segmenter,
            segments=buying or segmented.segments,
        )
        # Deliberately not `builder.annotate`, which writes annotation.json: a file
        # covering one chapter, written under the whole document's name, would be reused
        # by the build that follows and leave every other chapter unmarked.
        try:
            annotation = Annotator(
                # Cache only: pricing a card may never buy the words it is pricing.
                lemmatizer=lemma.for_text(builder.source, run.language),
                bands=biblical.for_source(builder.source),
                **dictionary_module.for_language(segmented.language),
            ).annotate(run)
        except TargumError:
            # Word help is worth saying goodbye to out loud; it is not worth a card that
            # will not draw. The build itself says so when it gets there.
            return 0.0, 0
        glosser = AnthropicGlosses(builder.gloss_model or builder.model)
        # A lemma looked up for another text is already bought. Quoting for it again
        # prices work that is about to be free.
        owed = unpaid(
            unique_lemmas(annotation),
            segmented.language,
            builder.target_language,
            glosser.name,
            builder.cache,
        )
        return estimate(len(owed), glosser.model), len(owed)

    def run(self, job: Job) -> None:
        # Covers first: a cover job carries no source to ingest, and everything below
        # would try to read its folder name as a file.
        if job.options.get("cover"):
            return self.run_covers(job)
        # On the list, not on `chapter`: preparing a whole book sets no single chapter
        # number, and a falsy 0 sent this down the ordinary build path — which then tried
        # to ingest the folder name as though it were a file.
        if job.options.get("parts"):
            return self.run_part(job)
        if job.options.get("chapters"):
            return self.run_chapter(job)
        if job.options.get("voice"):
            return self.run_voice(job)
        try:
            job.stage = "working"
            self.remember(job)
            builder = self._builder(job)
            builder.notify = lambda message: setattr(job, "message", message)

            def progress(done: int) -> None:
                job.done += done

            def ready(result: Result) -> None:  # noqa: D401
                # The page is watching for this and navigates as soon as it sees it.
                # Looking up word meanings carries on in this thread afterwards, into a
                # reader that is already open.
                job.reader = f"{result.out_dir.name}/reader/index.html"
                job.stage = "done"
                job.message = ""
                self.remember(job)
                self.tell(job)

            # One chapter. A book is bought as it is read; a text with no chapters is
            # translated whole, which the pipeline decides for itself.
            #
            # Inside `telling`, so that a first build on a fresh box says what it is
            # waiting for. Stanza downloads a few hundred megabytes the first time a
            # language is used, and until this the page held whatever line it had last
            # printed for the whole of it — a line that has not moved in four minutes
            # reads as a hang, and the reader closes a tab on a build that was working.
            # Wrapped here rather than inside `run`, because `run` calls `plan`, and the
            # segmenter downloads its tokenizer there.
            with telling(builder.notify):
                result = builder.run(on_progress=progress, on_ready=ready, chapters=FIRST_CHAPTERS)
            # The reservation becomes the receipt. Until this, the ledger held an
            # estimate and the budget was an approximation of itself. What reading the
            # pictures cost at the quote is on the same receipt: one text, one line.
            job.spent = result.spent.cost() + job.reading
            self.settle(job)
            self.remember(job)
            self.propose(job)
        except TargumError as error:
            self._blame(job, error.message)
        except Exception as error:
            # Whatever a library chose to say about itself is not a sentence for someone
            # who wanted to read a poem. The detail belongs in the terminal, and on the
            # back office, which is where it is read.
            traceback.print_exc()
            incidents_module.record(self.incidents, f"build:{job.stage}", error, job=job.id)
            self._blame(
                job,
                "Something went wrong on our side. The Terminal has the detail.",
            )

    def propose(self, job: Job) -> None:
        """Offer a finished build to the shelf, if its licence allows a public copy.

        Never a reason for the build to fail: the reader has their text whatever the
        shelf decides, so whatever goes wrong here is printed for the operator and the
        job stays done.
        """
        from . import promote as promote_module

        try:
            promote_module.candidate(self, self.store, job)
        except Exception as error:  # noqa: BLE001 - the shelf's business, not the reader's build
            traceback.print_exc()
            incidents_module.record(self.incidents, "promote", error, job=job.id)

    def cover_plan(self, folder: Path, chapters: bool) -> tuple[Any, list[tuple[str, str]]]:
        """What this text is, and every image worth drawing for it.

        A catalogue text is drawn from what the catalogue says it is — its title, its
        author, the sentence describing it — and those covers are shared between readers,
        because the catalogue is the same catalogue for everyone. An upload has none of
        that, so its subject is its title and its opening lines, and the picture is filed
        under the reader's own folder name rather than a catalogue id: it belongs to one
        text on one shelf.

        Most chapters are left out. See `catalogue.names_something`: a hundred and fifty
        psalms are numbered rather than titled, and a number is not a subject anything
        could draw. Those fall back to the book's cover when they are asked for.
        """
        from . import catalogue as catalogue_module
        from .catalogue import chapter_prompt, cover_prompt, cover_prompt_for, names_something
        from .models import Document, read_artifact

        document = read_artifact(Document, folder / "document.json")
        if document is None:
            return None, []
        entry = catalogue_module.matching(document.source)
        where = self.out / "thumbs"
        if entry is None:
            # An upload's cover carries its owner as well as its name. `thumbs/` is one
            # directory for the whole box, and a folder name is unique only within one
            # shelf — `free_name` keeps two of a reader's own texts apart and knows
            # nothing of anybody else's. Filed under the bare name, two readers who each
            # upload something called "notes" share one file: the second is told it is
            # already drawn, and shown the first reader's picture of the first reader's
            # text. A catalogue cover stays unprefixed, because that one really is the
            # same picture for everyone.
            mine = Drawable(
                id=f"{folder.parent.name}-{folder.name}",
                source=document.source,
                title=document.title or folder.name,
                language=document.language,
            )
            if any((where / (mine.id + suffix)).is_file() for suffix, _ in THUMBS):
                return mine, []
            opening = document.blocks[0].text if document.blocks else ""
            return mine, [(mine.id, cover_prompt_for(mine.title, opening))]

        wanted: list[tuple[str, str]] = []
        if not any((where / (entry.id + suffix)).is_file() for suffix, _ in THUMBS):
            wanted.append((entry.id, cover_prompt(entry)))
        if chapters:
            for chapter in self.chapters(folder):
                title = str(chapter.get("title") or "")
                name = f"{entry.id}-c{int(chapter['number']):03d}"
                if not names_something(title, entry.title):
                    continue
                if any((where / (name + suffix)).is_file() for suffix, _ in THUMBS):
                    continue
                wanted.append((name, chapter_prompt(entry, title)))
        return entry, wanted

    def run_covers(self, job: Job) -> None:
        """Draw a book's cover, then the chapters that have something of their own.

        The cover is drawn first and handed to every chapter after it as a reference —
        which is what makes a set look like a set. A chapter is therefore never drawn
        before its book, and if the book's own cover fails there is nothing to match.
        """
        from . import covers as covers_module

        illustrator = covers_module.build()
        usable, detail = illustrator.available()
        if not usable:
            return self._blame(job, detail)

        where = self.out / "thumbs"
        plan: list[tuple[str, str]] = job.options.get("plan") or []
        entry_id = str(job.options.get("cover") or "")
        job.stage = "working"
        job.total = len(plan)
        self.remember(job)

        drawn = 0
        # The book's cover as it came back, full size, for its chapters to be drawn
        # against. What gets kept on disk is a 320px tile — plenty to look at and thin
        # enough for a page, but a poor thing to hand an image model as a reference.
        # Only for the length of this run: a chapter drawn later matches the tile.
        original: bytes | None = None

        def owed() -> float:
            """What the answers said it cost, or the reservation rate if they did not.

            An image is billed by tokens rather than by the picture, so `drawn × price`
            was a receipt only while the price was flat. The illustrator counts what came
            back; this falls through to the old arithmetic for one that cannot.
            """
            counted = float(getattr(illustrator, "spent", 0.0) or 0.0)
            return counted or drawn * illustrator.price

        try:
            for name, prompt in plan:
                job.message = "We're drawing…"
                self.remember(job)
                reference = None
                if name != entry_id:
                    reference = original or next(
                        (
                            (where / (entry_id + suffix)).read_bytes()
                            for suffix, _ in THUMBS
                            if (where / (entry_id + suffix)).is_file()
                        ),
                        None,
                    )
                    if reference is None:
                        # Its book was never drawn, so there is nothing for this to look
                        # like. Skipping beats drawing an orphan that matches nothing.
                        continue
                where.mkdir(parents=True, exist_ok=True)
                drawing = illustrator.draw(prompt, reference)
                if name == entry_id:
                    original = drawing
                (where / f"{name}.webp").write_bytes(covers_module.shrink(drawing))
                drawn += 1
                job.done = drawn
                self.remember(job)
        except TargumError as error:
            job.spent = owed()
            self.settle(job)
            return self._blame(job, error.message)

        job.spent = owed()
        self.settle(job)
        job.stage = "done"
        job.message = ""
        self.remember(job)

    def run_chapter(self, job: Job) -> None:
        """Buy one more chapter of a book already on disk.

        Nothing is ingested or segmented again — those are done, they are free, and they
        are sitting in the folder. This translates one chapter and rewrites the reader
        around it, which is the whole of what asking for a chapter costs.
        """
        from .models import Document, SegmentedDocument, Vocalization, glossaries_in
        from .models import read_artifact as read
        from .render import render as render_reader

        folder = self.within(job.home or self.out, str(job.options.get("folder") or ""))
        if folder is None:
            return self._blame(job, "We can't find that one any more.")
        document = read(Document, folder / "document.json")
        segmented = read(SegmentedDocument, folder / "segments.json")
        if document is None or segmented is None:
            return self._blame(job, "We can't find that one any more.")

        builder = self._builder(job)
        builder._resolved_out = folder
        numbers = job.options.get("chapters") or []
        wanted = [
            segment
            for number in numbers
            for segment in builder.chapter_segments(segmented, int(number))
        ]
        if not wanted:
            return self._blame(job, "We can't find that chapter.")

        job.stage = "working"
        job.total = len(wanted)
        self.remember(job)
        try:
            translation = builder.translate(
                segmented, lambda done: setattr(job, "done", job.done + done), only=wanted
            )
            # A text whose words the model reads is read a chapter at a time too, so the
            # chapter just bought gets its words here; for every other text this is the
            # annotation already on disk, read back.
            annotation = builder.annotate_chapter(segmented, wanted)
            # Every translation the folder holds, with the one just bought at the front.
            # Rendering from this chapter's alone rewrote the reader without the others —
            # so buying chapter two of a book somebody reads in two languages took the
            # other language off every chapter of it.
            pages = render_reader(
                document,
                segmented,
                [translation, *builder.already_here([translation])],
                folder / "reader",
                annotation=annotation,
                glossaries=glossaries_in(folder),
                vocalization=read(Vocalization, folder / "vocalization.json"),
                clean=False,
                covers=self.out / "thumbs",
                # The same narrowing `_builder` hands a whole build. Without it, buying
                # a chapter put back every language the reader had said they do not read.
                reads=sorted(self._reads_of(job.owner) or ()) or None,
            )
        except TargumError as error:
            return self._blame(job, error.message)
        except Exception as error:
            traceback.print_exc()
            incidents_module.record(self.incidents, f"build:{job.stage}", error, job=job.id)
            return self._blame(
                job, "Something went wrong on our side. The Terminal has the detail."
            )

        job.spent = builder.spent.cost()
        job.reader = f"{folder.name}/reader/{pages[0].name}"
        job.stage = "done"
        self.settle(job)
        self.remember(job)
        self.tell(job)

    def run_voice(self, job: Job) -> None:
        """Make the audio for one section of a silent text, and rewrite the reader
        around it (targum-internal#246).

        One request a line, so the spans are exact without an aligner; the lines land
        as one part in the audio manifest beside the reader, the same file an import
        keeps, and the page is rendered again from what is on disk — which is how the
        clip ends up inline in it, and how every per-line control appears. The seconds
        charged are the clip's, read off the WAV; the estimate the press was claimed at
        is settled to them.
        """
        from . import speech
        from .audio import manifest as manifest_module
        from .models import Annotation, Document, SegmentedDocument, Vocalization, glossaries_in
        from .models import read_artifact as read
        from .render import render as render_reader
        from .render import split_sections

        folder = self.within(job.home or self.out, str(job.options.get("folder") or ""))
        if folder is None:
            return self._blame(job, "We can't find that one any more.")
        document = read(Document, folder / "document.json")
        segmented = read(SegmentedDocument, folder / "segments.json")
        if document is None or segmented is None:
            return self._blame(job, "We can't find that one any more.")
        number = int(job.options.get("section") or 0)
        sections = split_sections(segmented)
        section = next((one for one in sections if one.number == number), None)
        if section is None:
            return self._blame(job, "We can't find that section.")
        wanted = set(section.segment_ids)
        segments = [segment for segment in segmented.segments if segment.id in wanted]
        lines = [segment.text for segment in segments]
        job.stage = "working"
        job.total = len(lines)
        job.message = "We're reading it aloud…"
        self.remember(job)
        try:
            clip, spans = speech.render_lines(
                lines, folder / "audio" / f"voice-{number:03d}", language=document.language
            )
        except speech.Interrupted as error:
            # Some of it was said, and Google charged for what was. `_blame` settles a
            # job with money on it rather than releasing the claim.
            self._charge_speech(job, error.seconds)
            return self._blame(job, error.message)
        except TargumError as error:
            return self._blame(job, error.message)
        except Exception as error:
            traceback.print_exc()
            incidents_module.record(self.incidents, "voice", error, job=job.id)
            return self._blame(
                job, "Something went wrong on our side. The Terminal has the detail."
            )
        # Paid for from here on, whatever happens to the page below.
        self._charge_speech(job, clip.seconds)
        kept = manifest_module.load(folder) or manifest_module.AudioManifest(
            source=str(folder),
            sha256=str(document.content_hash or ""),
            duration=0.0,
            language="he",
        )
        kept.parts = [part for part in kept.parts if part.number != number]
        kept.parts.append(
            manifest_module.ManifestPart(
                number=number,
                title=section.title,
                start=0.0,
                end=clip.seconds,
                audio=str(clip.path.relative_to(folder)),
                transcribed=True,
                provider=speech.NAME,
                spans={
                    segment.id: [start, end]
                    for segment, (start, end) in zip(segments, spans, strict=True)
                    if end > start
                },
            )
        )
        kept.parts.sort(key=lambda part: part.number)
        kept.duration = sum(part.end - part.start for part in kept.parts)
        manifest_module.write(folder, kept)
        try:
            builder = self._builder(job)
            builder._resolved_out = folder
            pages = render_reader(
                document,
                segmented,
                builder.already_here([]),
                folder / "reader",
                annotation=read(Annotation, folder / "annotation.json"),
                glossaries=glossaries_in(folder),
                vocalization=read(Vocalization, folder / "vocalization.json"),
                clean=False,
                covers=self.out / "thumbs",
                reads=sorted(self._reads_of(job.owner) or ()) or None,
                folder=folder,
            )
        except TargumError as error:
            return self._blame(job, error.message)
        except Exception as error:
            traceback.print_exc()
            incidents_module.record(self.incidents, "voice:render", error, job=job.id)
            return self._blame(
                job, "Something went wrong on our side. The Terminal has the detail."
            )
        job.reader = f"{folder.name}/reader/{pages[0].name}"
        job.message = ""
        job.stage = "done"
        self.settle(job)
        self.remember(job)
        self.tell(job)

    @staticmethod
    def _charge_speech(job: Job, seconds: float) -> None:
        """What a voice job has spent: the seconds made, at the voice's price."""
        from . import speech

        job.seconds = seconds
        spent = Usage()
        spent.add_seconds(speech.NAME, seconds)
        job.spent = spent.cost()

    def run_part(self, job: Job) -> None:
        """Hear one more part of an imported recording, and rebuild around it.

        Through `Build.run` rather than `run_chapter`: hearing a part grows the
        document, so everything keyed to its hash — segments, spans, the manifest —
        must follow, and the build path is the one that knows how. What is already
        bought is a cache hit, so the rerun pays for the new part alone.
        """
        try:
            job.stage = "working"
            self.remember(job)
            # The folder rides in from the request with the rest of the options, so it
            # is resolved and checked the way every other folder in this file is —
            # joined bare, "../" in it would write a reader into someone else's home.
            folder = self.within(job.home or self.out, str(job.options.get("folder") or ""))
            if folder is None:
                return self._blame(job, "We can't find that one any more.")
            builder = self._builder(job)
            builder._resolved_out = folder
            builder.notify = lambda message: setattr(job, "message", message)
            wanted = [int(n) for n in job.options.get("parts") or []]

            def ready(result: Result) -> None:
                job.reader = f"{result.out_dir.name}/reader/index.html"
                job.stage = "done"
                job.message = ""
                self.remember(job)
                self.tell(job)

            result = builder.run(
                on_progress=lambda done: setattr(job, "done", job.done + done),
                on_ready=ready,
                chapters=FIRST_CHAPTERS,
                also=wanted,
            )
            job.spent = result.spent.cost()
            self.settle(job)
            self.remember(job)
        except TargumError as error:
            self._blame(job, error.message)
        except Exception as error:
            traceback.print_exc()
            incidents_module.record(self.incidents, f"build:{job.stage}", error, job=job.id)
            self._blame(job, "Something went wrong on our side. The Terminal has the detail.")

    def _blame(self, job: Job, message: str) -> None:
        """Record a failure, unless there is already a reader to show for the work.

        Everything after the reader opens is a bonus. Failing the job at that point
        would replace a book someone is reading with an error, and the page has stopped
        watching for one anyway.
        """
        if job.stage == "done":
            job.message = message
            self.remember(job)
            return
        job.error = message
        job.stage = "failed"
        # The money was committed when the build was claimed. A build that failed spent
        # little or none of it, and without this three failures in a row exhaust a
        # session budget that paid for nothing.
        # Not simply released: a build that failed part-way still paid for the batches
        # it got through, and the API said how much. Releasing the whole claim would
        # hand that money back to the budget as though it had never gone.
        if job.spent > 0:
            self.settle(job)
        else:
            self.release(job)
        self.remember(job)

    def _builder(self, job: Job) -> Build:
        options = job.options

        # What the catalogue says about this source, if it is one of ours. Read here
        # rather than taken from the request: the model decides what a build costs, and
        # one that arrived in a payload would be a way to spend somebody else's money.
        from . import catalogue as catalogue_module
        from .annotate.gloss import GLOSS_MODEL

        entry = catalogue_module.matching(job.source)
        build = Build(
            job.source,
            target_language=options.get("to", "en"),
            # What the door said, or else what the catalogue row says. The Library's own
            # button sends the row's language, but a door that does not — a pasted
            # catalogue source, a door written later — would leave it to the script,
            # which reads every Latin alphabet as English.
            source_language=options.get("from") or (entry.language if entry else None),
            # Natural, always. The word-for-word style is a command line option:
            # anyone who wants it can say so there, and putting the choice on this
            # page cost more in confusion than it bought.
            style=Style.natural,
            # Sonnet, not the provider's Opus default. Measured, a Hebrew novel is
            # $12.64 on Opus against $7.58 on Sonnet, and the difference in a reader's
            # translation does not show up beside the difference in the bill. The CLI
            # keeps the provider default: that is somebody spending their own key.
            # Sonnet, unless the catalogue says this text's English was bought with
            # something else. The cache is keyed on the model, so a book we translated
            # once on Opus would be translated again — at a reader's expense — by a build
            # that quietly asked for Sonnet instead.
            model=(entry.model if entry and entry.model else HOSTED_MODEL),
            # Whose build this is, which scopes the cache for anything that is not a
            # public text. Without it one person's uploaded book would be translated
            # once and served to everyone who happened to upload the same file.
            owner=f"p{job.owner}" if job.owner else "",
            # Whose reader this will be, and so which languages it may offer. A build
            # into a language they do not read is refused before it starts; this is the
            # other end of it — a folder that already holds one stops showing it.
            reads=sorted(self._reads_of(job.owner) or ()) or None,
            out_root=job.home or self.out,
            gloss=bool(options.get("gloss")),
            # Meanings are bought on the hosted model whatever the prose was bought with:
            # the catalogue is translated on Opus, and its 25k lemmas are cached under
            # Sonnet. Quoting or buying them under Opus paid twice for the same words.
            gloss_model=GLOSS_MODEL,
            # On unless a door says otherwise, and none does. Being able to tap a word is
            # most of what a reader is for, and this key was the one thing a door had to
            # remember: the chat's two doors forgot it once (targum 8b4cf17), and the
            # part and chapter doors — which write their own options — never had it. So
            # buying a recording's second part rebuilt the whole reader with no word
            # to tap, the first part's marks included, and the job said `done`.
            difficulty=bool(options.get("words", True)),
            # A catalogue text arrives with a translation somebody already made, so
            # nothing is asked of a model and nothing is spent.
            translations=[str(t) for t in options.get("translations") or []],
            # Ben Yehuda's plain-text downloads carry no title: the first line of the file
            # is the title and the author, as prose. Without this a book lands on somebody's
            # shelf called "6600".
            title=entry.title if entry else "",
            # For an imported recording: the transcript that came with it, and nothing
            # else — the transcriber is the box's own choice, never the request's.
            transcript=str(options.get("transcript")) if options.get("transcript") else None,
        )
        # A video file the reader downloaded after its link was refused: the link they
        # pasted first is its home, so the page still says whose film it is. Taken only
        # in the one shape the host table writes, so a request cannot put an address of
        # its choosing on the page — anything else reduces to "" and is dropped.
        from urllib.parse import urlparse

        from .video import hosts as hosts_module

        if urlparse(job.source).scheme not in ("http", "https"):
            build.home = hosts_module.home_url(str(options.get("came_from") or ""))
        return build


# The cookie the browser carries once somebody has signed in. Not `Secure`, because
# this build serves plain HTTP on loopback and a Secure cookie would simply never be
# sent; a hosted install serving HTTPS must add it.
SESSION_COOKIE = "targum_session"

# What the sign-in page says, whether or not the address has an account, and whether or
# not the mail went out. Anything more specific turns the form into a way of asking
# which addresses are registered here.
SENT = "Thanks. Check your email."


class Handler(BaseHTTPRequestHandler):
    # Overridden on the type built in start(). Off here so a Handler made by hand —
    # which is how the tests make one — behaves like a machine somebody runs themselves.
    require_account = False

    server_version = "targum"
    hosts: frozenset[str] = frozenset(SAFE_HOSTS)
    library: Library
    token: str
    page: str
    adding: str
    progress: str
    catalogue: str
    you: str
    #: The conversation page, and the workers that answer it. Empty and None on a
    #: handler built by hand, which is how the tests build one that has no chat.
    chatting: str = ""
    embedded: str = ""
    chats: Any = None
    #: The three list pages, by route name: everything Learn shows the top of. Empty by
    #: default so a handler built with only the pages it needs — which is what the tests
    #: build — serves no list pages rather than failing on the way past them.
    lists: dict[str, str] = {}
    store: Store
    mailer: Mailer
    address: str

    def log_message(self, format: str, *args: Any) -> None:
        return  # the console belongs to the build output

    def finish(self) -> None:
        """Answer, then let go of this thread's database connection.

        `ThreadingHTTPServer` gives every request a thread of its own, and the store
        opens one connection per thread. Nothing closes it when the thread ends: a
        thread-local's contents are reclaimed by the cyclic collector, not on exit, and
        on a long-running process with a large heap the old generation is visited
        rarely enough that hundreds of dead threads' connections sit open together.
        Each holds two descriptors, the database and its WAL, and at 1024 the process
        can no longer open a template — which is how targum.page answered 502 for an
        hour on 2026-08-31 after one reader loaded a shelf of thumbnails.

        `finally`, so a request that ended in a broken pipe still lets go; `getattr`,
        because a handler made by hand in a test may carry no store at all.
        """
        try:
            super().finish()
        finally:
            store = getattr(self, "store", None)
            if store is not None:
                store.close()

    # -- plumbing -----------------------------------------------------------

    # -- who is asking ------------------------------------------------------

    def _cookie(self, name: str) -> str:
        """One cookie by name. `SimpleCookie` would do this, and would also raise on a
        cookie somebody else's extension left behind with a character it dislikes."""
        for part in (self.headers.get("Cookie") or "").split(";"):
            key, _, value = part.strip().partition("=")
            if key == name:
                return unquote(value)
        return ""

    def _person(self) -> Person | None:
        return self.store.whoever(self._cookie(SESSION_COOKIE) or None)

    def _reads(self, person: Person | None = None) -> set[str]:
        """Which languages to offer whoever is asking.

        Everything, where there is nobody to ask: signed out, or a machine somebody runs
        themselves, where the person choosing and the person paying are the same and the
        command line is right there anyway. The gate is about a hosted box handing an
        account a language nobody said that account reads.
        """
        from .translate.prompts import INTO

        everything = {code for code, _ in INTO}
        who = person if person is not None else self._person()
        if who is None:
            return everything
        return self.store.reads(who.id) & everything

    def _learning(self, person: Person | None = None) -> set[str]:
        """Which languages whoever is asking is learning. Everything where there is
        nobody to ask, for the reason `_reads` gives."""
        from .translate.prompts import READING

        everything = {code for code, _ in READING}
        who = person if person is not None else self._person()
        if who is None:
            return everything
        return self.store.learning(who.id) & everything

    #: Every address a person can be looking at, or that a page asks for data from.
    #: Anything else is not a page, and says so rather than answering "Coming soon".
    PAGES = frozenset(
        {
            "/",
            "/add",
            "/chat",
            "/progress",
            "/library",
            "/you",
            "/readers",
            "/suggest",
            "/series",
            "/words/common",
            "/jobs",
            "/account/export",
            "/account/follows",
        }
    )
    #: `/open/` is here because a person clicks it (targum-internal#313): a signed-out
    #: visitor following a link to a text should meet the door, not a 404 saying the text
    #: does not exist. It is not a page in the sense of having markup — it redirects —
    #: but it is a page in the sense this list is about, which is "could somebody be
    #: looking at this".
    PAGE_PREFIXES = ("/reader/", "/thumb/", "/chat/", "/glossary/", "/job/", "/open/")

    def _is_a_page(self, route: str) -> bool:
        return (
            route in self.PAGES
            or route.lstrip("/") in self.lists
            or route.startswith(self.PAGE_PREFIXES)
        )

    def _not_found(self) -> None:
        """A page that is not there, said as a page (2026-09-14): a bare `not found` in
        plain text, or the holding page with a 200, were both a dead end."""
        self._send(404, not_found_page().encode("utf-8"), HTML)

    def _needs_account(self, route: str) -> bool:
        """Whether this request has to be turned away at the door.

        Hosted, always. On a machine somebody runs themselves, only once an account
        exists on it — because until then "signed out" describes nobody. A fresh install
        opens and works with nothing to sign into, which is what the README promises and
        what the command line is for; the moment somebody signs up, signing out means
        what it means everywhere else.
        """
        if route in OPEN_TO_STRANGERS or self._person() is not None:
            return False
        return self.require_account or self.store.anyone()

    def _home(self) -> Path:
        """The only directory this request is allowed to see."""
        return self.library.home(self._person())

    def _own_job(self, job_id: str) -> Job | None:
        """A job, but only if it belongs to whoever is asking.

        Ids are unguessable, so this is not the only thing standing between two
        people's builds — but an id is a bearer token, and one that leaks through a
        log or a shared screen should not hand over someone else's text.
        """
        job = self.library.jobs.get(job_id)
        if job is None:
            return None
        person = self._person()
        return job if job.owner == (person.id if person else None) else None

    def _host_is_ours(self) -> bool:
        # A page on another origin resolving a name to this address should not be able
        # to drive the builder, whatever else it can prove.
        return (self.headers.get("Host") or "").rsplit(":", 1)[0] in self.hosts

    def _authorised(self) -> bool:
        if not self._host_is_ours():
            return False
        query = parse_qs(urlparse(self.path).query)
        given = query.get("k", [""])[0] or (self.headers.get("X-Targum-Key") or "")
        # `self.token` guards the comparison rather than only the value. Hosted the key
        # is the empty string, and `compare_digest("", "")` is True — so without this,
        # taking the key away would authorise every anonymous request instead of none.
        if self.token and secrets.compare_digest(given, self.token):
            return True
        # A signed-in session is a stronger claim than the start-up key, and it is the
        # one thing here that survives a restart. Before this, someone who had signed in
        # still met the stale-session page every time targum was restarted, which is the
        # opposite of what signing in is for.
        return self._person() is not None

    @staticmethod
    def _policy(body: bytes, frames: str = "") -> str:
        """The content policy for one page, naming its own inline blocks by hash.

        A page that holds an `<iframe>` may frame its own origin — read off the page as
        written, like the hashes, because the talk drawer rides the shared header onto
        every chrome page and the reader as well, and a hand-kept list of which routes
        frame was four pages long while the drawer was on eleven (2026-09-11: the pill
        opened a broken frame everywhere but Learn). `frames` is `"out"` for a page that
        is itself framed — the conversation without its bar, a reader in the front
        page. Both are same-origin only: targum may frame targum and nothing else, and
        may be framed by targum and nobody else. The clickjacking guard that
        `frame-ancestors 'none'` gives every other page is kept exactly — `'self'` is
        not `'*'`.
        """
        import base64
        import hashlib

        hashes: list[str] = []
        for block in re.findall(rb"<(?:script|style)[^>]*>(.*?)</(?:script|style)>", body, re.S):
            digested = base64.b64encode(hashlib.sha256(block).digest()).decode("ascii")
            hashes.append(f"'sha256-{digested}'")
        allowed = " ".join(dict.fromkeys(hashes))
        policy = POLICY
        if frames == "out":
            policy = policy.replace("frame-ancestors 'none'", "frame-ancestors 'self'")
        if re.search(rb"<iframe\b", body):
            policy = policy + "; frame-src 'self'"
        return f"{policy}; script-src {allowed}; style-src {allowed}"

    # A reader page is around 180 kB, most of it the same stylesheet and script every
    # other page carries, and gzip takes it to a third of that. In front of the deployed
    # server Caddy already does this, so this is for the copy running on a laptop, which
    # has nothing in front of it at all. Below a packet there is nothing to win.
    COMPRESSIBLE = ("text/html", "application/json", "text/plain", "image/svg+xml")
    COMPRESS_OVER = 1400

    def _worth_zipping(self, body: bytes, kind: str) -> bool:
        return (
            len(body) >= self.COMPRESS_OVER
            and kind.startswith(self.COMPRESSIBLE)
            and "gzip" in self.headers.get("Accept-Encoding", "")
        )

    def _send(
        self, status: int, body: bytes, kind: str, cache: str = "no-store", frames: str = ""
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", kind)
        # Read off the page as written. The policy names this page's own inline blocks
        # by their hash, so it has to be taken before the bytes are compressed.
        policy = self._policy(body, frames) if kind.startswith("text/html") else None
        zipped = self._worth_zipping(body, kind)
        if zipped:
            body = gzip.compress(body, 6)
        self.send_header("Content-Length", str(len(body)))
        if zipped:
            self.send_header("Content-Encoding", "gzip")
        # A page said in the language the browser asked for varies with that header as
        # well as with compression; only such a page says so, so a reader stays cacheable.
        varies = "Accept-Encoding"
        if getattr(self, "_said_by_browser", False):
            varies += ", Accept-Language"
        self.send_header("Vary", varies)
        self.send_header("Cache-Control", cache)
        # Set by the weekly's entry points while the deployment keeps it unindexed:
        # reachable by anyone with the address, surfaced by no search engine.
        if getattr(self, "_robots_tag", ""):
            self.send_header("X-Robots-Tag", self._robots_tag)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        if policy is not None:
            self.send_header("Content-Security-Policy", policy)
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            # The browser moved on before the answer landed — a page that navigated
            # away with a fetch in flight. Not an error of ours, and the stream already
            # treats it so; without this each one printed a traceback in the terminal.
            self.close_connection = True

    # The sidecar video parts beside a reader. A closed table rather than `mimetypes`:
    # these are the only files a build writes that a page addresses by name, and a table
    # that cannot grow by accident is a door that cannot open by accident.
    MEDIA_KINDS = {".mp4": "video/mp4", ".m4v": "video/mp4", ".webm": "video/webm"}

    # How long a slow client may sit on one 64 KiB chunk before the thread is taken
    # back, and how long the whole response may run. A part is tens of megabytes and
    # ThreadingHTTPServer spends a whole thread per request, so a stalled connection
    # has to cost minutes, not forever — per chunk and in total.
    MEDIA_CHUNK = 64 * 1024
    MEDIA_TIMEOUT_S = 60.0
    MEDIA_RESPONSE_S = 600.0

    def _send_file(self, target: Path, kind: str) -> None:
        """A slice of a file on disk, the way a browser asks for video.

        Ranges, because seeking is Range requests — and because Safari opens every
        video with a `bytes=0-1` probe and refuses to play unless it comes back as a
        real 206 with `Accept-Ranges`. Streamed from an open handle rather than read
        whole: a part runs to tens of megabytes, and `read_bytes()` is that much
        resident memory per concurrent viewer. Never gzipped — the codec already did.
        """
        told = target.stat()
        size = told.st_size
        stamp = email.utils.formatdate(told.st_mtime, usegmt=True)
        # A validator, because a part is tens of megabytes and content-stable: the
        # browser that kept it asks again with If-Modified-Since, and 304 is the
        # whole answer. If-Range is honoured a few lines down, where a validator that
        # no longer matches turns a range back into a whole-file answer.
        held = self.headers.get("If-Modified-Since", "")
        if held == stamp and "Range" not in self.headers:
            self.send_response(304)
            self.send_header("Last-Modified", stamp)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        status, start, end = 200, 0, size - 1
        asked = self.headers.get("Range", "")
        # If-Range with a stale validator means the range is against bytes the
        # browser no longer has the rest of: per the RFC the range is ignored and
        # the whole current file answers, or a re-cut part splices into an old one.
        conditional = self.headers.get("If-Range", "")
        if conditional and conditional != stamp:
            asked = ""
        found = re.fullmatch(r"bytes=(\d*)-(\d*)", asked.strip()) if asked else None
        if found and (found.group(1) or found.group(2)):
            if found.group(1):
                start = int(found.group(1))
                if found.group(2):
                    end = min(int(found.group(2)), size - 1)
            else:
                # A suffix range: the last N bytes, which is how a player reads the
                # index a plain mp4 keeps at the tail.
                start = max(0, size - int(found.group(2)))
            if start >= size or end < start:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{size}")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            status = 206
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(end - start + 1))
        self.send_header("Accept-Ranges", "bytes")
        if status == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        # Private rather than no-store: the same reasoning as the covers — refetching
        # tens of megabytes on every visit is the whole reader's weight many times
        # over, and `private` keeps it in the one browser it already travelled to.
        self.send_header("Cache-Control", "private, max-age=86400")
        self.send_header("Last-Modified", stamp)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        was_timeout = self.connection.gettimeout()
        self.connection.settimeout(self.MEDIA_TIMEOUT_S)
        # The socket timeout bounds one write; this bounds the response. A client
        # draining a chunk a minute would otherwise hold a thread for hours — and a
        # ThreadingHTTPServer's threads are the whole machine. A playing browser
        # never hits this: it asks in ranges and comes back for more.
        deadline = time.monotonic() + self.MEDIA_RESPONSE_S
        left = end - start + 1
        try:
            with target.open("rb") as handle:
                handle.seek(start)
                while left > 0 and time.monotonic() < deadline:
                    piece = handle.read(min(self.MEDIA_CHUNK, left))
                    if not piece:
                        break
                    self.wfile.write(piece)
                    left -= len(piece)
        except (BrokenPipeError, ConnectionResetError, TimeoutError, OSError):
            # A viewer who stopped watching, or stalled past the timeout. Not an error
            # worth a traceback: the response is theirs to abandon.
            pass
        finally:
            # The connection may be kept alive for ordinary requests, whose patience
            # is not the media loop's to shorten.
            with contextlib.suppress(OSError):
                self.connection.settimeout(was_timeout)
        if left > 0:
            self.close_connection = True

    def _json(self, payload: Any, status: int = 200) -> None:
        self._send(status, json.dumps(payload).encode("utf-8"), "application/json")

    def _go(self, where: str, cookie: str | None = None) -> None:
        """Send them on, optionally handing over or taking back the session."""
        self.send_response(303)
        self.send_header("Location", where)
        if cookie is not None:
            self.send_header("Set-Cookie", cookie)
        self.send_header("Content-Length", "0")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

    def _moved(self, where: str) -> None:
        """Permanently, for an address that has a better name now.

        A link that exists should not die: an edition of the weekly answers under its
        catalogue id too, because it is a catalogue entry, and that address is the one
        somebody may already have written down.
        """
        self.send_response(301)
        self.send_header("Location", where)
        self.send_header("Content-Length", "0")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

    def _sent_on(self, where: str) -> None:
        """Temporarily, for a name that is a front door rather than an address.

        302 and not 301: `bo.targum.page` points at where the back office happens to be
        served from today, and a browser that has cached a permanent redirect keeps
        following it long after that stops being true — including to an origin that no
        longer answers. A door is allowed to change what it opens onto.
        """
        self.send_response(302)
        self.send_header("Location", where)
        self.send_header("Content-Length", "0")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

    @staticmethod
    def _session_cookie(token: str, days: int) -> str:
        # HttpOnly so a script on the page cannot read it, SameSite=Lax so another site
        # cannot make the browser use it, Path=/ so the readers carry it too.
        return (
            f"{SESSION_COOKIE}={token}; HttpOnly; SameSite=Lax; Path=/; "
            f"Max-Age={days * 24 * 60 * 60}"
        )

    # -- routes -------------------------------------------------------------

    def _serve_parasha(self, route: str) -> None:
        """The weekly portion, at three addresses.

            /parasha                 whatever is read this Shabbat
            /parasha/<name>          one portion, any week of the year
            /parasha/read/<name>/…   one file of a built reader

        The middle one is what makes the corpus a shelf rather than a page that changes:
        the fifty-four are all built, all the time, and a link to any of them keeps
        working after the week it was this week's.
        """
        if not parasha_is_indexed():
            self._robots_tag = "noindex"
        from .parasha import build as corpus
        from .parasha.calendar import Schedule

        reading = PARASHA_READER.match(route)
        if reading is not None:
            return self._serve_parasha_reader(reading.group(1), reading.group(2))

        index = corpus.load()
        if not index.portions:
            return self._send(404, b"not found", "text/plain")

        wanted = route.removeprefix("/parasha").strip("/")
        query = parse_qs(urlparse(self.path).query)
        schedule = (
            Schedule.israel
            if query.get("schedule", ["diaspora"])[0] == "israel"
            else Schedule.diaspora
        )
        # Two literals and a comparison on one line pair their quotes in a way
        # `test_brand.prose` reads as copy, and it then finds an exclamation mark in the
        # operator. The value gets a name instead; the extractor is a blunt instrument on
        # purpose and this is cheaper than sharpening it.
        asked_taamim = query.get("taamim", ["on"])[0]
        taamim = asked_taamim != "off"

        readable = corpus.readable(index)
        other_schedule = Schedule.israel if schedule is Schedule.diaspora else Schedule.diaspora
        here = corpus.current(schedule, index=index)
        elsewhere = corpus.current(other_schedule, index=index)
        # A box that built only one schedule — or a week the other one has no pointer
        # for — should still answer with the reading it does have rather than 404 the
        # page over a query string. The chip then shows what is actually on screen.
        if here is None and elsewhere is not None:
            schedule, other_schedule = other_schedule, schedule
            here, elsewhere = elsewhere, here
        if wanted:
            portion = index.portions.get(wanted)
            if portion is None or portion.folder not in readable:
                return self._send(404, b"not found", "text/plain")
            # A portion asked for by name is not a week, so it has neither a date nor a
            # Hebrew one: it is read on a different one every year. Its haftarah is the
            # one it ordinarily has, for the same reason.
            shabbat = None
            hdate = ""
            haftarah = index.haftarot.get(portion.haftarah) if portion.haftarah else None
            haftarah_reason = ""
            parts = None
        else:
            portion = here
            if portion is None or portion.folder not in readable:
                return self._send(404, b"not found", "text/plain")
            from .parasha.calendar import pointing_at

            shabbat = pointing_at()
            week = index.week(shabbat.isoformat(), schedule)
            hdate = week.hdate if week is not None else ""
            # The week's haftarah, not the portion's: on a Shabbat Rosh Chodesh or in
            # Chanukah the congregation reads the special one, and a page that named the
            # portion's own would be naming the wrong thing to prepare.
            haftarah, haftarah_reason = index.haftarah_on(shabbat.isoformat(), schedule)
            parts = self._parasha_week(portion, haftarah, shabbat, readable)

        page = parasha_page(
            portion,
            language=self._page_language(),
            schedule=schedule,
            other=elsewhere,
            diaspora=here if schedule is Schedule.diaspora else elsewhere,
            israel=elsewhere if schedule is Schedule.diaspora else here,
            listed=[one for one in index.listed() if one.folder in readable],
            taamim=taamim,
            shabbat=shabbat,
            hdate=hdate,
            haftarah=haftarah,
            haftarah_reason=haftarah_reason,
            # The frame only where there is a reader behind it; the reference is said
            # either way, because knowing what is read is most of what somebody
            # preparing needs.
            haftarah_readable=haftarah is not None and haftarah.folder in readable,
            address=self.address,
            # Where "all portions" goes: a reader with a shelf has them on it, in their
            # collection; a visitor has the list at the foot of this page.
            signed_in=self._person() is not None,
            week=parts,
        )
        return self._send(200, page.encode("utf-8"), HTML)

    @staticmethod
    def _parasha_week(
        portion: Any, haftarah: Any, shabbat: date, readable: set[str]
    ) -> dict[str, Any] | None:
        """What the page needs to say which parts of this week's reading are read.

        The moment the week began, off `calendar.week_began`, and the document each part
        is kept under — so the page compares the reader's own finish times against the
        server's week and keeps no clock of its own (targum-internal#203). None where the
        reading's reader has no document to find, which a page draws as no list.
        """
        from .parasha.build import document_of
        from .parasha.calendar import week_began
        from .parasha.cut import ALIYOT, HAFTARAH

        document, sections = document_of(portion.folder)
        if not document:
            return None
        # A reading the renderer wrote as one page — too short to split — is one part,
        # read when that page is.
        whole = {
            "name": portion.hebrew or portion.name,
            "href": f"/parasha/read/{portion.folder}/reader/index.html",
            "frame": "reading",
            "document": document,
            "section": 0,
            "sections": 1,
        }
        parts = [
            {
                "name": ALIYOT[n - 1] if n <= len(ALIYOT) else str(n),
                "href": f"/parasha/read/{portion.folder}/reader/sec-{n:04d}.html",
                "frame": "reading",
                "document": document,
                "section": n,
                "sections": 0,
            }
            for n in range(1, sections + 1)
        ] or [whole]
        if haftarah is not None and haftarah.folder in readable:
            kept, count = document_of(haftarah.folder, haftarah.opens)
            count = count or 1
            if kept:
                parts.append(
                    {
                        "name": HAFTARAH,
                        "href": f"/parasha/read/{haftarah.folder}/reader/{haftarah.opens}",
                        "frame": "haftarah",
                        "document": kept,
                        "section": 0,
                        "sections": count,
                    }
                )
        return {"began": int(week_began(shabbat).timestamp() * 1000), "parts": parts}

    def _serve_daily(self, slug: str, rest: str) -> None:
        """One learning cycle, at three addresses.

            /mishna-yomi                  what is read today
            /mishna-yomi/<date>           one day, while it is in the window
            /mishna-yomi/read/<date>/…    one file of a built reader

        The middle one is not the parasha's equivalent and cannot be: the corpus there is
        fifty-four readings that are all built all the time, and a cycle is two thousand
        days of which fourteen are. So a day outside the window is a 404 — the text is
        still on the shelf under its own name, which is where somebody looking for last
        spring's mishnayot is actually going.
        """
        from .daily import build as corpus
        from .daily.calendar import Day, for_day, today
        from .daily.cycles import ABSENT, BY_SLUG, CYCLES

        if not daily_is_indexed():
            self._robots_tag = "noindex"
        cycle = BY_SLUG.get(slug)
        if cycle is None:
            return self._send(404, b"not found", "text/plain")

        reading = DAILY_READER.match(rest)
        if reading is not None:
            return self._serve_daily_reader(slug, reading.group(1), reading.group(2))

        wanted = rest.strip("/")
        when = today()
        if wanted:
            try:
                when = date.fromisoformat(wanted)
            except ValueError:
                return self._send(404, b"not found", "text/plain")
        if not corpus.readable(slug, when):
            return self._send(404, b"not found", "text/plain")

        day = for_day(cycle, when, allow_fetch=False)
        if day is None:
            return self._send(404, b"not found", "text/plain")

        # The days either side, and only a few of them. The window holds three weeks and
        # all twenty-one as chips ran off the edge of the page with today among the ones
        # that had gone — the row scrolls, so what was cut was the one chip somebody
        # needs. Three each way fits a desktop whole and puts today in the middle of a
        # phone's scroll.
        built = corpus.days_of(slug)
        around: list[Day] = []
        for iso in sorted(built):
            try:
                other = date.fromisoformat(iso)
            except ValueError:
                continue
            one = for_day(cycle, other, allow_fetch=False)
            if one is not None and corpus.readable(slug, other):
                around.append(one)
        here = next((i for i, one in enumerate(around) if one.day == when), 0)
        nearby = around[max(0, here - NEARBY_DAYS) : here + NEARBY_DAYS + 1]

        others: list[tuple[object, str]] = []
        for one_cycle in CYCLES:
            if one_cycle.slug == slug:
                continue
            elsewhere = for_day(one_cycle, today(), allow_fetch=False)
            if elsewhere is not None and corpus.readable(one_cycle.slug, today()):
                others.append((one_cycle, elsewhere.hebrew or elsewhere.title))

        page = daily_page(
            cycle,
            day,
            language=self._page_language(),
            nearby=nearby,
            others=others,
            absent=list(ABSENT.items()),
            opens=corpus.opens_at(slug, when),
            is_today=when == today(),
            address=self.address,
        )
        return self._send(200, page.encode("utf-8"), HTML)

    def _serve_daily_reader(self, slug: str, when: str, name: str | None) -> None:
        """One file out of a built day, and nothing else.

        The same two gates the portion's reader has: the day must be one this box built,
        and the file must resolve inside its folder — which is what makes a name carrying
        a dot-dot a 404 rather than a way out of the corpus.
        """
        from .daily import build as corpus

        if not daily_is_indexed():
            self._robots_tag = "noindex"
        try:
            day = date.fromisoformat(when)
        except ValueError:
            return self._send(404, b"not found", "text/plain")
        if not corpus.readable(slug, day):
            return self._send(404, b"not found", "text/plain")
        base = (corpus.folder_for(slug, day) / "reader").resolve()
        target = (base / (name or "index.html")).resolve()
        if not target.is_file() or base not in target.parents:
            return self._send(404, b"not found", "text/plain")
        kind = "text/html; charset=utf-8" if target.suffix == ".html" else "text/plain"
        return self._send(200, target.read_bytes(), kind, frames="out")

    def _serve_parasha_reader(self, folder: str, name: str | None) -> None:
        """One file out of a built portion, and nothing else.

        The same two gates the weekly's reader has: the folder must be one the index
        knows and has a built reader for, and the file must resolve inside it — which is
        what makes a name carrying a dot-dot a 404 rather than a way out of the corpus.
        """
        from .parasha import build as corpus
        from .parasha.calendar import root as corpus_root

        if not parasha_is_indexed():
            self._robots_tag = "noindex"
        if folder not in corpus.readable():
            return self._send(404, b"not found", "text/plain")
        base = (corpus_root() / "read" / folder / "reader").resolve()
        target = (base / (name or "index.html")).resolve()
        if not target.is_file() or base not in target.parents:
            return self._send(404, b"not found", "text/plain")
        kind = "text/html; charset=utf-8" if target.suffix == ".html" else "text/plain"
        return self._send(200, target.read_bytes(), kind, frames="out")

    def _serve_weekly(self, route: str) -> None:
        """The weekly, at three addresses.

            /weekly                  the newest issue, at the middle level
            /weekly/<week>           sent on to that issue's middle level
            /weekly/<week>/<level>   one edition, canonical to itself

        Self-canonical rather than pointing every level at one page, because the three
        are genuinely different Hebrew rather than near-duplicates. Answered before
        `_needs_account` is consulted: a variable path cannot be named in the exact-match
        `OPEN_TO_STRANGERS`, so the only way to make it public is to return first.
        """
        if not weekly_is_indexed():
            self._robots_tag = "noindex"
        from .weekly import index as weekly
        from .weekly.models import Level

        rest = route.removeprefix("/weekly").strip("/")

        # The two doors that arrive from an email. Both are a page with a button rather
        # than a link that acts: a mail client that fetches every link in a message
        # would otherwise answer for the person it was sent to, which is the same reason
        # `/account/enter` stopped being a bare GET.
        if rest in {"confirm", "stop"}:
            store = self.library.store
            token = parse_qs(urlparse(self.path).query).get("t", [""])[0]
            if store is None:
                return self._send(404, b"not found", "text/plain")
            if rest == "confirm":
                waiting = store.peek_subscription(token)
                if waiting is None:
                    return self._send(
                        200,
                        weekly_note(
                            "That link has already been used, or it's expired.",
                            address=self.address,
                            done=False,
                        ).encode("utf-8"),
                        HTML,
                    )
                message = f"Should we send the weekly to {waiting} every Monday?"
                button = "Yes, send it"
            else:
                message = "Should we stop sending you the weekly?"
                button = "Yes, stop"
            page = weekly_note(
                message,
                address=self.address,
                pending={"action": f"/weekly/{rest}", "token": token, "button": button},
            )
            return self._send(200, page.encode("utf-8"), HTML)

        # The reader itself, for anybody at all. A published issue is already public at
        # its own address, and the built reader is a self-contained file that fetches
        # nothing — its meanings, its vowel points and its word list are all baked in —
        # so serving it to a stranger hands over exactly what the prose page already
        # hands over, and the whole of what makes this worth signing up for.
        #
        # A route of its own rather than opening `/reader/`, which reaches a person's
        # own home and the shared one. Those must never answer without an account, and
        # the surest way to keep that true is not to touch the branch that serves them.
        reading = WEEKLY_READER.match(route)
        if reading is not None:
            return self._serve_weekly_reader(reading.group(1), reading.group(2))

        # Readable, not merely published: an issue whose reader never arrived is one
        # nobody can open, and offering it is offering a 404.
        published = weekly.readable()
        if not rest:
            # The newest issue somebody can actually read, at a level that is actually
            # there. An index says an issue is published; the built reader is what makes
            # it readable, and the two can disagree — a half-finished copy to the box, a
            # publish that ran before a build. Sending a visitor to a page whose reader
            # 404s is worse than sending them to the issue before it.
            newest = published[0] if published else None
            if newest is None:
                return self._send(404, b"not found", "text/plain")
            return self._go(f"/weekly/{newest.id}/{self._opens_at(newest).value}")

        week, _, wanted = rest.partition("/")
        issue = next((one for one in published if one.id == week), None)
        if issue is None:
            # A draft is on disk and is not published, which from out here is the same
            # thing as not existing. Saying "not yet" would be telling a stranger what
            # is coming.
            return self._send(404, b"not found", "text/plain")
        if not wanted:
            return self._go(f"/weekly/{issue.id}/{self._opens_at(issue).value}")
        if wanted not in set(Level) or issue.edition(Level(wanted)) is None:
            return self._send(404, b"not found", "text/plain")

        page = weekly_page(
            issue,
            Level(wanted),
            address=self.address,
            archive=published,
            language=self._page_language(),
        )
        return self._send(200, page.encode("utf-8"), HTML)

    def _weekly_said(self, message: str, done: bool = True) -> None:
        """One sentence, on the weekly page's own furniture.

        Says the same thing whatever state the address is in — subscribed already,
        never seen, or stopped — for the reason `start_sign_in` does: an endpoint that
        answered differently would be a way to ask whether somebody is a reader here.
        """
        page = weekly_note(message, address=self.address, done=done)
        return self._send(200 if done else 429, page.encode("utf-8"), HTML)

    def _waitlist_note(self, message: str, done: bool = True, **rest: Any) -> None:
        """A sentence back from the front door, on the furniture the weekly's doors use.

        The same page, a different heading and a different way home: this is read in a
        mail client by somebody who has no account, may never have seen targum, and is
        being asked one question about an address they typed.
        """
        page = weekly_note(
            message, address=self.address, done=done, heading="the waitlist", home="/", **rest
        )
        return self._send(200 if done else 429, page.encode("utf-8"), HTML)

    def _waitlist_get(self, route: str) -> None:
        """The two doors that arrive from an email: a page with a button, never an act.

        A mail client that fetches every link in a message would otherwise answer for
        the person it was sent to, which is why `/account/enter` and the weekly's own
        two stopped being bare GETs.
        """
        store = self.library.store
        if store is None:
            return self._send(404, b"not found", "text/plain")
        token = parse_qs(urlparse(self.path).query).get("t", [""])[0]
        if route == "/waitlist/confirm":
            waiting = store.peek_waiting(token)
            if waiting is None:
                return self._waitlist_note("That link has already been used, or it's expired.")
            message = f"Should we keep {waiting} on the waitlist?"
            button = "Yes, keep me on it"
        else:
            message = "Should we take you off the waitlist?"
            button = "Yes, take me off"
        return self._waitlist_note(
            message, pending={"action": route, "token": token, "button": button}
        )

    def _waitlist_post(self, route: str, form: dict[str, str]) -> None:
        """Joining, confirming and leaving. Public by necessity, and public by design:
        nobody joining a waitlist has an account, and the whole point is that they
        cannot get one yet."""
        store = self.library.store
        if store is None:
            return self._send(404, b"not found", "text/plain")

        if route == "/waitlist":
            address = (form.get("email") or "").strip()
            if not plausible(address):
                return self._waitlist_note(
                    "We couldn't read that as an email address. Check it and try again.",
                    done=False,
                )
            if store.asking_too_often(address, limit=SUBSCRIBE_ASKS_PER_HOUR):
                return self._waitlist_note(
                    "We've had a few requests for that address. Try again in an hour.", False
                )
            # The language the door was in when they pressed, kept so the invitation is
            # written in it rather than in English by default (targum-internal#292).
            token = store.join_waitlist(address, self._front_language())
            # `can_mail` asks about a build's owner, and somebody waiting has none; the
            # two halves it actually needs are checked here, as the weekly's door does.
            postable = self.library.mailer is not None and bool(self.address)
            if token is not None and postable:
                where = f"{self.address.rstrip('/')}/waitlist/confirm?t={token}"
                with contextlib.suppress(Exception):
                    self.library.mailer.notify(  # type: ignore[union-attr]
                        address,
                        "Confirm your place on the targum waitlist",
                        f"Press the button on this page and you're on the list:\n\n{where}\n\n"
                        f"We're opening in small groups, and we'll email you when it's "
                        f"your turn.\n\n"
                        f"If you did not ask for this, nothing has happened and you can "
                        f"ignore this.\n",
                    )
            # The same sentence whatever state the address is in, including already on:
            # an endpoint that answered differently would be a way to ask who is waiting.
            return self._waitlist_note("Thanks. Check your email and press the button in it.")

        if route == "/waitlist/confirm":
            if store.confirm_waiting(form.get("t", "")) is None:
                return self._waitlist_note("That link has already been used, or it's expired.")
            return self._waitlist_note("You're on the list. We'll email you when it's your turn.")

        # Nothing is said about whether the token was one, for the reason the weekly's
        # unsubscribe says nothing: an endpoint that reported back would answer whether
        # an address is on the list.
        store.leave_waitlist(form.get("t", ""))
        return self._waitlist_note("We've taken you off the waitlist.")

    def _weekly_post(self, route: str, form: dict[str, str]) -> None:
        store = self.library.store
        if store is None:
            return self._send(404, b"not found", "text/plain")

        if route == "/weekly/subscribe":
            address = (form.get("email") or "").strip()
            if not plausible(address):
                return self._weekly_said(
                    "We couldn't read that as an email address. Check it and try again.", done=False
                )
            if store.asking_too_often(address, limit=SUBSCRIBE_ASKS_PER_HOUR):
                return self._weekly_said(
                    "We've had a few requests for that address. Try again in an hour.", False
                )
            token = store.subscribe(address)
            # `can_mail` asks about a build's owner; a subscriber has none, so the two
            # halves it actually needs are checked here instead.
            postable = self.library.mailer is not None and bool(self.address)
            if token is not None and postable:
                where = f"{self.address.rstrip('/')}/weekly/confirm?t={token}"
                with contextlib.suppress(Exception):
                    self.library.mailer.notify(  # type: ignore[union-attr]
                        address,
                        "Confirm the targum weekly",
                        f"Press the button on this page and the weekly starts arriving "
                        f"on Mondays:\n\n{where}\n\n"
                        f"If you did not ask for it, nothing has happened and you can "
                        f"ignore this.\n",
                    )
            # The same sentence either way, including when the address is already on.
            return self._weekly_said("Thanks. Check your email and press the button in it.")

        if route == "/weekly/confirm":
            found = store.confirm_subscription(form.get("t", ""))
            if found is None:
                return self._weekly_said("That link has already been used, or it's expired.", False)
            return self._weekly_said("Thanks. You'll get the weekly every Monday.")

        if route == "/weekly/stop":
            store.stop_subscription(form.get("t", ""))
            # Nothing is said about whether the token was one: an unsubscribe endpoint
            # that reported back would answer whether an address is on the list.
            return self._weekly_said("We won't send you the weekly again.")

        return self._send(404, b"not found", "text/plain")

    def _follows(self, payload: dict[str, Any] | None) -> None:
        """Which series this account follows (2026-09-11), read or changed.

        Reads the session's own address and never the payload's, as the weekly's door
        does. The weekly stays on its own rails (`subscriber`); every other series is a
        `follow` row. Signed out there is nothing to follow with, and the browser keeps
        its own list.
        """
        person = self._person()
        store = self.store
        if person is None or store is None:
            return self._json({"signedIn": False, "follows": []}, 401)
        if payload is not None:
            series = str(payload.get("series") or "").strip()
            if not series or not SERIES_ID.match(series):
                return self._json(
                    {
                        "error": self._say(
                            "serve.we-couldn-t-tell-which-series",
                            "We couldn't tell which series you meant.",
                        )
                    },
                    400,
                )
            wanted = bool(payload.get("on", True))
            if series == "weekly":
                store.follow(person.email, wanted)
            else:
                store.follow_series(person.email, series, wanted)
        follows = store.series_followed(person.email)
        if store.following(person.email):
            follows = ["weekly", *follows]
        return self._json({"signedIn": True, "follows": follows})

    def _series_stop(self, form: dict[str, str] | None) -> None:
        """The one-click door out of a series, from an email: a page with a button, and
        the button is what spends the token — a mail client that fetches every link must
        not be able to answer for the person it was sent to."""
        store = self.store
        if store is None:
            return self._send(404, b"not found", "text/plain")
        if form is None:
            token = parse_qs(urlparse(self.path).query).get("t", [""])[0]
            page = weekly_note(
                "Should we stop telling you when a new one comes out?",
                address=self.address,
                done=False,
                pending={"action": "/series/stop", "token": token, "button": "Yes, stop"},
                heading="your subscriptions",
                home="/library",
            )
            return self._send(200, page.encode("utf-8"), HTML)
        store.stop_following(form.get("t", ""))
        page = weekly_note(
            "We won't tell you about it again.",
            address=self.address,
            heading="your subscriptions",
            home="/library",
        )
        return self._send(200, page.encode("utf-8"), HTML)

    def _weekly_follow(self, payload: dict[str, Any]) -> None:
        """The signed-in door. Reads the session's address and never the payload's."""
        person = self._person()
        store = self.library.store
        if person is None or store is None:
            return self._json(
                {
                    "error": self._say(
                        "serve.you-ll-need-to-sign-in", "You'll need to sign in first."
                    )
                },
                401,
            )
        wanted = bool(payload.get("on", True))
        store.follow(person.email, wanted)
        return self._json({"following": store.following(person.email)})

    @staticmethod
    def _opens_at(issue: WeeklyIssue) -> WeeklyLevel:
        """Which level to open an issue at: the usual one where it is there, otherwise
        whichever is.

        Only ever called with an issue from `weekly.readable`, whose editions are the
        ones with a reader on disk — so there is always one, and the caller never has to
        wonder what an issue nobody can open would redirect to.
        """
        if issue.edition(DEFAULT_LEVEL) is not None:
            return DEFAULT_LEVEL
        return issue.editions[0].level

    def _serve_weekly_reader(self, edition: str, name: str | None) -> None:
        """One file out of a published edition's built reader, and nothing else.

        Two gates, each on its own: the folder has to belong to an edition of a
        *published* issue, and the file has to resolve inside that folder's reader
        directory. The second is what makes a name carrying a dot-dot a 404 rather than
        a way out of the weekly.
        """
        from .weekly import index as weekly

        if not weekly_is_indexed():
            self._robots_tag = "noindex"
        known = {one.folder for issue in weekly.readable() for one in issue.editions}
        if edition not in known:
            return self._send(404, b"not found", "text/plain")

        root = (weekly.root() / edition / "reader").resolve()
        target = (root / (name or "index.html")).resolve()
        if not target.is_file() or root not in target.parents:
            return self._send(404, b"not found", "text/plain")
        kind = "text/html; charset=utf-8" if target.suffix == ".html" else "text/plain"
        # Framed by the issue's own page and by nothing else on the web.
        return self._send(200, target.read_bytes(), kind, frames="out")

    def _robots(self) -> str:
        """What a crawler may have.

        Everything public is public on purpose; everything else needs an account and
        would answer with the door anyway. Naming the private routes here keeps crawlers
        from spending their budget on pages that will never be worth an index entry.
        """
        if not shelves_are_public():
            # Every page a crawler could reach is the holding page. Letting it in now
            # means "Coming soon" is what ranks for targum later.
            return "User-agent: *\nDisallow: /\n"
        lines = [
            "User-agent: *",
            "Allow: /$",
            "Allow: /about",
            "Allow: /library",
            "Allow: /weekly",
            "Allow: /parasha",
            # The learning cycles, each at its own address. On the same terms as the
            # parasha — invited only where the deployment invites the shelves at all.
            *(f"Allow: /{cycle.slug}" for cycle in daily_cycles()),
            *(f"Allow: {route}" for route in LEGAL_ROUTES if legal_is_public()),
            "Disallow: /account/",
            "Disallow: /reader/",
            "Disallow: /readers",
            "Disallow: /progress",
            "Disallow: /job/",
            "Disallow: /glossary/",
            "Disallow: /health",
        ]
        if self.address:
            lines.append(f"Sitemap: {self.address}/sitemap.xml")
        return "\n".join(lines) + "\n"

    def _sitemap(self) -> str:
        """Every public page, generated from the catalogue rather than kept by hand.

        A hand-maintained sitemap is one that is wrong the first time somebody adds an
        entry and forgets, and being wrong here is invisible until traffic does not
        arrive.
        """
        from . import catalogue as catalogue_module

        where = self.address or ""
        paths = ["/", "/about", "/library"]
        if legal_is_public():
            paths += list(LEGAL_ROUTES)
        # A portion's catalogue id redirects to its own page, so the id is left out here
        # and the page named below instead: listing both is asking a crawler to pick.
        paths += [
            f"/library/{entry.id}"
            for entry in catalogue_module.CATALOGUE
            if not entry.id.startswith("parasha-")
        ]
        # The corpus by its own addresses, for the same reason. Every portion, not just
        # this week's: they are all built, all the time, and each is what somebody
        # searching that portion's name is looking for. Only once the deployment invites
        # search engines to it, on the same terms as the weekly below.
        from .parasha import build as corpus

        built = corpus.load()
        readable_portions = corpus.readable(built) if parasha_is_indexed() else set()
        if readable_portions:
            paths.append("/parasha")
            paths += [
                f"/parasha/{portion.slug}"
                for portion in built.listed()
                if portion.folder in readable_portions
            ]
        # A learning cycle by the one address that is always right: `/mishna-yomi` is
        # today, forever, and is the page worth indexing. The dated ones are not in here
        # on purpose — they fall out of the window in a fortnight, and a sitemap naming a
        # page that will 404 next week is a sitemap that teaches a crawler to distrust it.
        from .daily import build as daily_corpus
        from .daily.calendar import today as daily_today

        if daily_is_indexed():
            paths += [
                f"/{cycle.slug}"
                for cycle in daily_cycles()
                if daily_corpus.readable(cycle.slug, daily_today())
            ]

        # The weekly by its own addresses rather than its catalogue ids, which redirect.
        from .weekly import index as weekly

        # Only once the deployment invites search engines to it: a sitemap naming pages
        # whose every response says noindex would be the site contradicting itself.
        published = weekly.readable() if weekly_is_indexed() else []
        paths += ["/weekly"] if published else []
        paths += [
            f"/weekly/{issue.id}/{edition.level.value}"
            for issue in published
            for edition in issue.editions
        ]
        urls = "".join(f"<url><loc>{where}{path}</loc></url>" for path in paths)
        return (
            f'<?xml version="1.0" encoding="UTF-8"?>\n'
            f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>\n'
        )

    def _measure(self, home: Path, readers: list[dict[str, Any]]) -> None:
        """Say how much of each targum the reader already knows.

        Added in place rather than returned, and silently skipped for anyone signed out or
        any text without word-level annotation — the page shows what it showed before
        rather than a zero, because "0% known" and "not measured" are very different
        claims to make about a book.

        One vocabulary query per language, not per text: a shelf of twenty Hebrew books
        asks once and measures all twenty against the answer.
        """
        person = self._person()
        if person is None:
            return
        from . import coverage as coverage_module

        vocabulary: dict[str, dict[str, int]] = {}
        for reader in readers:
            language = str(reader.get("language") or "")
            name = str(reader.get("name") or "")
            # The folder is resolved here rather than carried in the payload: an absolute
            # path on the server is not something a browser has any business being told.
            if not language or not name:
                continue
            if language not in vocabulary:
                vocabulary[language] = self.store.marked(person, language)
            measured = coverage_module.against(home / name, vocabulary[language])
            if measured is not None:
                reader.update(measured.state())

    def _measure_catalogue(self) -> dict[str, dict[str, float | int]]:
        """How much of each *unbuilt* catalogue text the reader knows
        (targum-internal#293).

        The shelf's own promise — sorted by the words you already know — was true only of
        texts this reader had built, which for somebody who has just arrived is none of
        them. The index beside the catalogue carries every text's dictionary forms, so
        the same intersection answers for a row nobody has opened.

        One vocabulary query per language, as `_measure` does, and nothing at all where
        the box has no index: an empty answer leaves every row saying what it said
        before, which is nothing.
        """
        from . import catalogue as catalogue_module
        from . import coverage as coverage_module

        person = self._person()
        if person is None:
            return {}
        index = coverage_module.read_index(catalogue_module.lemmas_path())
        if not index.texts:
            return {}
        vocabulary: dict[str, dict[str, int]] = {}
        out: dict[str, dict[str, float | int]] = {}
        for entry in catalogue_module.everything():
            if entry.id not in index.texts:
                continue
            language = entry.language
            if language not in vocabulary:
                vocabulary[language] = self.store.marked(person, language)
            measured = index.against(entry.id, vocabulary[language])
            if measured is not None:
                out[entry.id] = measured.state()
        return out

    def _health(self) -> None:
        """Whether the process is alive and can still reach the one file that matters.

        Behind the key and the account check, because the thing asking is a monitor
        rather than a reader — and behind the host check too, or anyone who resolves a
        name here could use it to find out the box exists. It touches the store on
        purpose: a process that is running with a database it can no longer read is the
        failure worth catching, and one that only answers "yes I am a process" would
        report that as healthy.

        `queue` is what is waiting; `jobs` is how many this process has seen since it
        started. They used to be one number under the first name, and the first name was
        the wrong one: `jobs` is never pruned, so a healthy box that had served a hundred
        builds read `queue: 100` and an operator had no way to tell that from a hundred
        waiting. It is the number that would have shown targum-internal#228 — every chat
        turn hanging until four dead workers left the queue growing with nobody on it —
        and it showed 172 either way.
        """
        try:
            self.store.anyone()
        except Exception:
            return self._json({"ok": False, "store": False}, 503)
        self._json(
            {
                "ok": True,
                "store": True,
                "queue": self.library.queue.qsize(),
                "jobs": len(self.library.jobs),
            }
        )

    def _asked_for_the_back_office(self) -> bool:
        """Whether this request arrived on the operator's own name."""
        wanted = getattr(self, "back_office", "")
        if not wanted:
            return False
        return (self.headers.get("Host") or "").rsplit(":", 1)[0] == wanted

    def _back_office(self) -> None:
        """Who has an account and what they did, for whoever runs the box.

        **An admin session is the door.** Not a password on the vhost, which is what
        this was for a day: the session cookie is host-only — `Path=/`, no `Domain` — so
        a session made on `targum.page` is never sent to `bo.targum.page`, and the only
        ways to change that are to widen the cookie to `.targum.page`, which hands every
        future subdomain every reader's session, or to serve this from the origin the
        session already belongs to. The second is the cheap one. `bo.targum.page` stays
        as the address a person types and redirects here.

        A signed-in reader who is not an admin gets 404 rather than 403. 403 is an
        answer: it says there is something here. There are two accounts on this box and
        one of them is not the operator, and "you may not" is a thing to tell a stranger,
        not the person you live with.
        """
        from .backoffice import DAYS, survey_store

        person = self._person()
        if person is None:
            # Signed out. The holding page rather than the sign-in form, for the reason
            # `_needs_account` gives: a door shown to somebody with no key is a wall that
            # looks like a mistake. The door is one click away, in the corner.
            return self._send(
                200, holding_page(language=self._page_language()).encode("utf-8"), HTML
            )
        if not person.admin:
            return self._send(404, b"not found", "text/plain")
        if self.store is None:
            return self._send(503, b"no store", "text/plain")
        # Read-only, and off the same file the service is writing to. `_send` already
        # answers `no-store`, which is what a page listing accounts wants: not in a
        # proxy, and not in the back button after the laptop is shut.
        found = survey_store(self.store.path)
        said = parse_qs(urlparse(self.path).query).get("said", [""])[0][:300]
        page = back_office_page(
            found,
            DAYS,
            proposed=self.store.proposals(),
            wanted=self.store.wanted(),
            said=said,
            incidents=incidents_module.recent(self.library.incidents),
            balances=self.store.balances(),
        )
        self._send(200, page.encode("utf-8"), HTML)

    def _open_the_door(self, form: dict[str, str]) -> None:
        """Let the next few off the waitlist in, from the back office's own form.

        The same door `_promote` is: an admin session, and 404 for anyone else. The
        count is read from the form and clamped, because a batch is a small group by
        definition and a typed nought is not an instruction to let everybody in.
        """
        from .doorway import open_the_door

        person = self._person()
        if person is None or not person.admin or self.store is None:
            return self._send(404, b"not found", "text/plain")
        try:
            count = max(1, min(self.DOOR_AT_ONCE, int(form.get("count", "5"))))
        except ValueError:
            count = 5
        try:
            rows = open_the_door(self.store, self.mailer, self.address, count)
        except ValueError as error:
            return self._go(f"{BACK_OFFICE_ROUTE}?said={quote(str(error))}")
        let_in = sum(1 for row in rows if row.ok)
        failed = len(rows) - let_in
        if not rows:
            said = "Nobody is waiting who has not already been let in."
        elif failed:
            said = f"Let {let_in} in. {failed} could not be written to."
        else:
            said = f"Let {let_in} in."
        self._go(f"{BACK_OFFICE_ROUTE}?said={quote(said)}")

    def _balance(self, form: dict[str, str]) -> None:
        """Record what a service's console said was left, from the back office's form.

        The same door as `_promote`: an admin session, and 404 for anyone else. What is
        typed is kept as typed, because a console writes dollars, credits or gigabytes
        and a number with the unit taken off it is a number nobody can read back.
        """
        from .services import BY_ID, SAID_MAX

        person = self._person()
        if person is None or not person.admin or self.store is None:
            return self._send(404, b"not found", "text/plain")
        service = form.get("service", "")
        said = " ".join(form.get("said", "").split())[:SAID_MAX]
        if service not in BY_ID or not said:
            return self._send(400, b"bad request", "text/plain")
        self.store.balance_read(service, said)
        self._go(f"{BACK_OFFICE_ROUTE}#services")

    def _promote(self, form: dict[str, str]) -> None:
        """Accept or decline a proposal, from the back office's own form.

        The same door the page is: an admin session, and 404 for anyone else. A plain
        form post rather than JSON, because the back office carries no script and
        `form-action 'self'` is already what the policy allows.
        """
        from . import promote as promote_module

        person = self._person()
        if person is None or not person.admin or self.store is None:
            return self._send(404, b"not found", "text/plain")
        proposal_id = form.get("id", "")
        try:
            if form.get("action") == "accept":
                promote_module.accept(
                    self.library,
                    self.store,
                    proposal_id,
                    register=form.get("register", ""),
                    kind=form.get("kind", ""),
                    credit=form.get("credit", "").strip(),
                )
            elif form.get("action") == "decline":
                promote_module.decline(self.store, proposal_id)
            else:
                return self._send(400, b"bad request", "text/plain")
        except TargumError as error:
            said = f"{error.message} {error.hint or ''}".strip()
            return self._go(f"{BACK_OFFICE_ROUTE}?said={quote(said)}")
        self._go(BACK_OFFICE_ROUTE)

    def do_GET(self) -> None:  # noqa: N802
        self._answer(self._get)

    def do_POST(self) -> None:  # noqa: N802
        self._answer(self._post)

    def _answer(self, route: Callable[[], None]) -> None:
        """A route, with whatever escapes it written down (targum-internal#24).

        `socketserver` prints the traceback and drops the connection, which is what a
        request thread should do with an exception nobody caught; what it did not do was
        leave a trace anywhere but the journal. Recorded, then re-raised, so nothing
        about the failure itself changes.
        """
        # Whether this answer was chosen by the browser's language, asked afresh each time.
        self._said_by_browser = False
        try:
            route()
        except Exception as error:
            incidents_module.record(self.library.incidents, self.path, error)
            raise

    def _get(self) -> None:
        route = urlparse(self.path).path
        # No key, no account, no cookie: a monitor asks this every minute from off the
        # box, and A6 is "I find out it broke before she tells me".
        if route == "/health":
            return self._health()
        # The operator's own name answers one page and nothing else. Ahead of every
        # other route so that nothing on the product is reachable through it either:
        # the two names are disjoint in both directions.
        # The operator's name is a front door and nothing else: it sends everything to
        # the product's own origin, which is where the session cookie lives. Ahead of
        # every other route, so nothing on the product is reachable through that name.
        if self._asked_for_the_back_office():
            return self._sent_on(f"{self.address}{BACK_OFFICE_ROUTE}")
        if route == BACK_OFFICE_ROUTE:
            return self._back_office()
        # The browser asks for this on every page load without being told to, and it
        # carries no key, so it would otherwise answer the stale-session page and put a
        # failed request in the console each time. Answered before the key check and
        # served for real: the monogram is public, and a tab with no icon is the one
        # place the identity is visibly missing.
        if route == "/favicon.ico":
            return self._send(200, _icon(), "image/png")
        if route == "/robots.txt":
            return self._send(200, self._robots().encode("utf-8"), "text/plain; charset=utf-8")
        if route == "/sitemap.xml":
            if not shelves_are_public():
                return self._send(404, b"not found", "text/plain")
            return self._send(200, self._sitemap().encode("utf-8"), "application/xml")
        # The four legal documents, and the switch that keeps them shut until beta.
        # Ahead of `_needs_account` on purpose: shut has to be 404 for everybody, signed
        # in or out, rather than the holding page a stranger would otherwise be handed.
        if route in LEGAL_ROUTES:
            if not legal_is_public():
                return self._send(404, b"not found", "text/plain")
            page = legal_page(route.lstrip("/"), self.address)
            return self._send(200, page.encode("utf-8"), HTML)
        # A text's own page. It carries a sample rather than the whole text, so there is
        # nothing here to protect — but it stays shut with the rest until the catalogue
        # is opened, because a shop window onto an empty shop is not worth having.
        # The two doors the waitlist's mail carries, read by somebody with no account.
        if front_door_is_open() and route in {"/waitlist/confirm", "/waitlist/stop"}:
            return self._waitlist_get(route)
        if shelves_are_public() and (route == "/weekly" or route.startswith("/weekly/")):
            return self._serve_weekly(route)
        if shelves_are_public() and (route == "/parasha" or route.startswith("/parasha/")):
            return self._serve_parasha(route)
        daily_cycle = DAILY_ROUTE.match(route) if shelves_are_public() else None
        if daily_cycle is not None:
            return self._serve_daily(daily_cycle.group(1), daily_cycle.group(2) or "")

        naming = PUBLIC_TEXT.match(route) if shelves_are_public() else None
        if naming is not None:
            from . import catalogue as catalogue_module

            # An edition is a catalogue entry, so it answers here too — but it has a
            # better address of its own, and two URLs for one page is a duplicate a
            # search engine has to guess between.
            weekly_at = weekly_url(naming.group(1))
            if weekly_at is not None:
                return self._moved(weekly_at)
            # A portion is a catalogue entry so the library lists it, and its own page is
            # where it says which Shabbat reads it.
            portion_at = parasha_url(naming.group(1))
            if portion_at is not None:
                return self._moved(portion_at)
            entry = catalogue_module.by_id(naming.group(1))
            if entry is None:
                return self._send(404, b"not found", "text/plain")
            return self._send(
                200,
                text_page(entry, self.address, language=self._page_language()).encode("utf-8"),
                HTML,
            )
        # The shelves answer to whoever is asking. Signed out that is the public index —
        # the shop window, and the thing a search engine indexes. Signed in it is the
        # product. Same address either way, because a text somebody found on Google
        # should still be there after they sign in to read it.
        if route == "/library":
            if self._person() is None and not self._authorised():
                if not shelves_are_public():
                    return self._send(
                        200, holding_page(language=self._page_language()).encode("utf-8"), HTML
                    )
                page = shelf_page(self.address, language=self._page_language())
                return self._send(200, page.encode("utf-8"), HTML)

        if self._needs_account(route):
            # Data routes answer as data. Anything a person could be looking at gets a
            # page rather than a 401 — and not the sign-in page either, because a door
            # shown to somebody with no key is a wall that looks like a mistake. The
            # door is one click away, in the corner.
            if route.startswith(
                (
                    "/readers",
                    "/job/",
                    "/jobs",
                    "/glossary/",
                    "/account/export",
                    "/chat/",
                    "/slips",
                )
            ):
                return self._json(
                    {
                        "error": self._say(
                            "serve.you-ll-need-to-sign-in", "You'll need to sign in first."
                        ),
                        "signIn": "/account/signin",
                    },
                    401,
                )
            if not self._is_a_page(route):
                return self._not_found()
            # The front door, once there is one. Only at `/`: every other page a
            # signed-out visitor asks for is still the holding page, because the front
            # door is a page about the product and not a stand-in for one of its rooms.
            if route == "/" and front_door_is_open():
                page = front_page(
                    language=self._front_language(), address=self.address, asked=self._asked()
                )
                return self._send(200, page.encode("utf-8"), HTML)
            return self._send(
                200, holding_page(language=self._page_language()).encode("utf-8"), HTML
            )
        # The one route that needs no key: it carries a single-use token of its own,
        # which is a stronger claim than the key it would otherwise be asked for. It
        # has to work from a mail client, hours later, possibly after a restart.
        if route == "/about":
            return self._send(200, about_page(language=self._page_language()).encode("utf-8"), HTML)
        if route == "/series/stop":
            # Followed out of an email, with no account and no key.
            return self._series_stop(None)
        if route == "/account/signin":
            return self._send(
                200,
                # In the language pressed on the front door, where one was: the link there
                # carries it, and a stranger who chose Russian a page ago is not handed
                # English to sign in with (2026-09-20).
                signin_page(language=self._front_language(), asked=self._asked()).encode("utf-8"),
                HTML,
            )
        # Google's two halves (targum-internal#304). Exempt from the start-up key for the
        # reason the sign-in page is — somebody signing in has no key yet — and never
        # exempt from the host check below. 404 where no client is configured, which is a
        # machine somebody runs themselves, and the box until it has one.
        if route == "/account/google":
            return self._google_out()
        if route == "/account/google/back":
            return self._google_back(parse_qs(urlparse(self.path).query))
        if route == "/account/enter":
            # Exempt from the key, never from the host check: a page on another origin
            # that resolves a name to this address still gets nothing.
            if not self._host_is_ours():
                return self._send(404, b"not found", "text/plain")
            # A page, not a sign-in. A mail client that fetches links to preview them
            # spends nothing here; the button below posts, and that is what signs in.
            token = parse_qs(urlparse(self.path).query).get("t", [""])[0]
            person = self.store.peek_sign_in(token) if token else None
            if person is None:
                return self._send(
                    200,
                    signin_page(expired=True, language=self._page_language()).encode("utf-8"),
                    HTML,
                )
            page = signin_page(landing=person.email, token=token, language=self._page_language())
            return self._send(200, page.encode("utf-8"), HTML)
        if not self._authorised():
            return self._send(403, STALE.encode("utf-8"), "text/html; charset=utf-8")
        if route.startswith("/reader/"):
            return self._serve_reader(route[len("/reader/") :])
        if route.startswith("/open/"):
            return self._open_entry(route[len("/open/") :])
        if route.startswith("/thumb/"):
            return self._serve_thumb(route[len("/thumb/") :])
        if route == "/":
            return self._send(200, self._desk("page", self.page).encode("utf-8"), HTML)
        if route == "/add":
            return self._send(
                200, self._desk("adding", self.adding).encode("utf-8"), "text/html; charset=utf-8"
            )
        if route == "/chat":
            if not self.chatting:
                return self._send(404, b"not found", "text/plain")
            # `?embed=1` is the same conversation without the bar and the foot, drawn
            # inside the front page (2026-09-11): it may be framed by this origin only.
            if parse_qs(urlparse(self.path).query).get("embed", [""])[0] == "1":
                page = self._desk("embedded", self.embedded)
                return self._send(200, page.encode("utf-8"), HTML, frames="out")
            page = self._desk("chatting", self.chatting)
            return self._send(200, page.encode("utf-8"), "text/html; charset=utf-8")
        if route.startswith("/chat/"):
            return self._chat_get(route[len("/chat/") :])
        if route == "/progress":
            page = self._desk("progress", self.progress)
            return self._send(200, page.encode("utf-8"), "text/html; charset=utf-8")
        # Learn holds the top of each of these; this is the rest. `/words` was a redirect
        # to the progress page for a while, from when the word list lived there — an old
        # tab pointing here now lands on the word list itself, which is what it wanted.
        if route.lstrip("/") in self.lists:
            which = route.lstrip("/")
            page = self._desk(f"lists:{which}", self.lists[which])
            return self._send(200, page.encode("utf-8"), "text/html; charset=utf-8")
        if route == "/library":
            return self._send(
                200,
                self._desk("catalogue", self.catalogue).encode("utf-8"),
                "text/html; charset=utf-8",
            )
        if route == "/you":
            return self._send(
                200, self._desk("you", self.you).encode("utf-8"), "text/html; charset=utf-8"
            )
        if route == "/slips":
            # Lines this reader wrote that came back changed (targum-internal#290).
            # Theirs and nobody else's: signed out there is nobody to have any, and the
            # store answers with an empty list rather than with somebody else's.
            person = self._person()
            # `?all=1` is the record on the phrases page, newest first and with the lines
            # already known; without it, the queue What to work on draws.
            if parse_qs(urlparse(self.path).query).get("all") == ["1"]:
                every = self.store.slips(person.id if person else None, limit=SLIPS_LISTED)
                return self._json({"slips": every})
            oldest = self.store.slips(
                person.id if person else None,
                limit=SLIPS_SHOWN,
                oldest=True,
                open_only=True,
            )
            return self._json({"slips": oldest})
        if route == "/readers":
            # Not "/library": that name belongs to the page a person opens.
            home = self._home()
            mine = self.library.readers(home)
            self._measure(home, mine)
            # And the shared one, measured against this reader's words like their own.
            # The page shows it only to a reader with nothing of their own in that
            # language: it is where to start, not another row on a full shelf.
            shared = self.library.readers(self.library.shared)
            for reader in shared:
                reader["shared"] = True
            self._measure(self.library.shared, shared)
            person = self._person()
            return self._json(
                {
                    "readers": mine,
                    "shared": shared,
                    "trash": self.library.readers(home, trashed=True),
                    # Whether this reader is offered a conversation in Hebrew — the same
                    # word `/chat/list` gives, decided the same way (`Library.talks`).
                    "talk": self.library.talks(home, person.id if person else None),
                    # Whether this deployment can draw a cover at all. A page with no
                    # image key offers nothing rather than offering and failing.
                    "covers": self.library.can_draw(),
                    # Every catalogue text measured against this reader's words, built or
                    # not (targum-internal#293). Keyed by entry id; a built copy's own
                    # measurement above wins, because that is the text they actually have.
                    "catalogue": self._measure_catalogue(),
                }
            )
        if route == "/account/me":
            return self._me()
        if route == "/account/totals":
            return self._totals()
        if route == "/suggest":
            return self._suggest()
        if route == "/account/follows":
            return self._follows(None)
        if route == "/series":
            # What comes out on its own clock, and where each is this week (2026-09-11):
            # the page draws the row to follow, and Learn puts a new instalment of a
            # followed one in the sheet.
            from . import series as series_module

            schedule = parse_qs(urlparse(self.path).query).get("schedule", ["diaspora"])[0]
            return self._json(
                {"series": series_module.current(schedule, public=shelves_are_public())}
            )
        if route == "/words/common":
            return self._common_words(parse_qs(urlparse(self.path).query))
        if route == "/account/export":
            # Everything the account holds, for somebody who wants to take it away. A
            # download rather than a page: the point of this is that it needs nobody's
            # help, and a wall of JSON in a browser tab is not a thing anybody can keep.
            person = self._person()
            if person is None:
                return self._json(
                    {
                        "error": self._say(
                            "serve.you-ll-need-to-sign-in", "You'll need to sign in first."
                        )
                    },
                    401,
                )
            body = json.dumps(self.store.everything(person), ensure_ascii=False, indent=1).encode(
                "utf-8"
            )
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Disposition", 'attachment; filename="targum.json"')
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return None
        if route.startswith("/glossary/"):
            return self._serve_glossary(route[len("/glossary/") :])
        if route == "/jobs":
            # Every build of yours that is running, waiting, or lately finished. The id
            # of a build used to live only in the page that started it, so leaving that
            # page made the build look cancelled — it was not, but nothing could find it.
            person = self._person()
            return self._json({"jobs": self.library.mine(person.id if person else None)})
        if route.startswith("/job/"):
            job = self._own_job(route[len("/job/") :])
            return self._json(
                job.state()
                if job
                else {
                    "error": self._say(
                        "serve.we-lost-that-build-when-we",
                        "We lost that build when we restarted. Start it again.",
                    )
                }
            )
        self._not_found()

    def _post(self) -> None:
        route = urlparse(self.path).path
        if not self._host_is_ours():
            return self._json({"error": "not found"}, 404)
        # Asking for a sign-in link is how somebody with an expired tab gets back in, so
        # it cannot be behind the key that expired. It is still loopback-only, it says
        # the same thing whatever address it is given, and all it can cause is one email
        # to an address the asker typed themselves.
        if route == "/account/enter":
            return self._enter(self._form().get("t", ""))
        # The back office's one action, a form post from the page an admin is on.
        if route == BACK_OFFICE_ROUTE + "/promote":
            return self._promote(self._form())
        if route == BACK_OFFICE_ROUTE + "/open-the-door":
            return self._open_the_door(self._form())
        if route == BACK_OFFICE_ROUTE + "/balance":
            return self._balance(self._form())
        # Subscribing to the weekly, confirming it, and stopping it. Public by
        # necessity: somebody who reads an issue signed out has no account and is not
        # going to open one to be told when the next is out. Plain forms, before the
        # account check and before the start-up key, exactly as the door above is.
        if route in WEEKLY_POSTS and shelves_are_public():
            return self._weekly_post(route, self._form())
        # The front door's form, and the two doors its mail carries. Open exactly while
        # the door itself is, and before the account check for the same reason the
        # weekly's are: nobody here has an account, or could get one.
        if route in WAITLIST_POSTS and front_door_is_open():
            return self._waitlist_post(route, self._form())
        if route == "/series/stop":
            return self._series_stop(self._form())
        if self._needs_account(route):
            return self._json(
                {
                    "error": self._say(
                        "serve.you-ll-need-to-sign-in", "You'll need to sign in first."
                    ),
                    "signIn": "/account/signin",
                },
                401,
            )
        if route != "/account/sign-in" and not self._authorised():
            return self._json(
                {
                    "error": self._say(
                        "serve.this-page-is-from-an-earlier",
                        "This page is from an earlier session. Open the new link in the Terminal.",
                    )
                },
                403,
            )
        # The chunked door, before the JSON parse: a chunk's body is raw bytes, and
        # holding it to the JSON ceiling would refuse the very uploads it exists for.
        if route.startswith("/upload/"):
            return self._upload(route)
        # A spoken line: raw audio, not JSON, so it is read before the JSON parse too.
        if route == "/chat/hear":
            return self._chat_hear(parse_qs(urlparse(self.path).query))
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_UPLOAD:
            return self._json(
                {
                    "error": self._say(
                        "serve.file-over-mb",
                        "That file is over {size} MB. Try sending us one part of it.",
                        size=MAX_FILE_MB,
                    )
                },
                413,
            )
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            return self._json({"error": "bad request"}, 400)

        if route == "/chat/say":
            return self._chat_say(payload)
        if route == "/chat/suggest":
            return self._chat_suggest(payload)
        if route == "/voice":
            return self._voice(payload)
        if route == "/chat/save":
            return self._chat_save(payload)
        if route == "/weekly/follow":
            # Takes no address at all: it reads the session's own. With nothing to
            # supply there is no way to sign somebody else's inbox up and nothing to
            # validate, which is a shorter argument than any amount of checking.
            return self._weekly_follow(payload)
        if route == "/account/follows":
            return self._follows(payload)
        if route == "/prepare":
            return self._prepare(payload)
        if route == "/build":
            return self._build(payload)
        if route == "/gloss":
            return self._gloss_word(payload)
        if route == "/phrase":
            return self._gloss_phrase(payload)
        if route == "/chapter":
            return self._chapter(payload)
        if route == "/cover":
            return self._cover(payload)
        if route == "/jobs/watch":
            return self._watch_job(payload)
        if route == "/trash":
            return self._trash(payload)
        if route == "/restore":
            return self._restore(payload)
        if route == "/account/sign-in":
            return self._sign_in(payload)
        if route == "/account/sign-out":
            return self._sign_out()
        if route == "/account/forget":
            return self._forget()
        if route == "/sync":
            return self._sync(payload)
        if route == "/account/name":
            return self._rename(payload)
        if route == "/account/interest":
            return self._interest(payload)
        if route == "/account/level":
            return self._declared(payload)
        if route == "/events":
            return self._events(payload)
        if route == "/account/events":
            return self._events_choice(payload)
        if route == "/account/address":
            return self._address(payload)
        if route.startswith("/slips/"):
            return self._know_slip(route[len("/slips/") :], payload)
        if route == "/account/languages":
            return self._languages(payload)
        if route == "/account/language":
            return self._language(payload)
        self._json({"error": "not found"}, 404)

    # -- the conversation ---------------------------------------------------

    def _chat_get(self, rest: str) -> None:
        """`/chat/list`, `/chat/<id>`, `/chat/turn/<id>/<n>` and `/chat/stream/<id>/<n>`.

        Every one checks the conversation is the asker's before it says anything, the
        way `_own_job` does for a build: an id is unguessable and is still not a key.
        """
        if self.chats is None or self.chats.store is None:
            return self._json({"error": "not found"}, 404)
        store = self.chats.store
        person = self._person()
        person_id = person.id if person else None
        if rest == "list":
            from .chat import hebrew as hebrew_module
            from .chat.session import mode_for

            # The hours beside the list: the one limit a reader is told about, in the
            # unit they were told. The page says them only when they matter (2026-09-10,
            # targum-internal#237); the whole count lives on Your Progress.
            query = parse_qs(urlparse(self.path).query)
            try:
                limit = min(200, max(1, int(query.get("limit", ["50"])[0])))
                offset = max(0, int(query.get("offset", ["0"])[0]))
            except ValueError:
                limit, offset = 50, 0
            # One language's conversations (2026-09-13): each has its own, and the page
            # asks in the language the switcher shows.
            spoken = self._asked_language(query.get("language", [""])[0])
            return self._json(
                {
                    # A page of them, newest first (targum-internal#238): the list used to
                    # be every conversation ever, and the page draws "More" at its foot.
                    "chats": store.chats(person_id, limit=limit, offset=offset, language=spoken),
                    "language": spoken,
                    # The language the conversation's meanings are in, so a word looked
                    # up from it matches the ones it already carries (targum-internal#287).
                    "into": hebrew_module.gloss_language(self._reads(person)),
                    "usable": self.chats.usable,
                    # Whether a new conversation here is held in the talk shape: Hebrew for
                    # a reader with modern Hebrew to speak, and Italian (targum-internal
                    # #280). Scripture-only readers, and every language with no talk mode
                    # yet, are answered in English, about the text (`Library.talks`,
                    # `session.mode_for`). Speak is offered either way since 2026-09-14.
                    "talk": mode_for(spoken, self.library.talks(self._home(), person_id)) == "talk",
                    "hours": self._hours(person_id),
                    "chips": self.chats.chips(
                        person, self._home(), spoken, ui=self._page_language()
                    ),
                }
            )
        pieces = rest.split("/")
        if pieces[0] in ("turn", "stream", "audio") and len(pieces) == 3 and pieces[2].isdigit():
            chat_id, n = pieces[1], int(pieces[2])
            if store.chat_owned(person_id, chat_id) is None:
                return self._json({"error": "not found"}, 404)
            if pieces[0] == "turn":
                state = self._chat_turn_state(chat_id, n)
                if state.get("done"):
                    # A page polling rather than streaming saw the answer too.
                    store.chat_opened(chat_id)
                return self._json(state)
            if pieces[0] == "audio":
                return self._chat_audio(chat_id, n, person)
            return self._chat_stream(chat_id, n)
        if len(pieces) == 1:
            chat = store.chat_owned(person_id, pieces[0])
            if chat is None:
                return self._json({"error": "not found"}, 404)
            # Opened by its person: an answer made after this is one they have not seen.
            store.chat_opened(chat["id"])
            turns: list[dict[str, Any]] = []
            # The cards a turn quoted come back with it (2026-09-11): they were drawn
            # from the live stream only, so a conversation opened again — the drawer
            # in a reader is reopened on every page it rides — had the model saying
            # "press the card" over a thread with no card in it. A quote lives in
            # the tool result the model was handed; it is drawn under the answer that
            # followed, in the state the job is in now.
            waiting: list[dict[str, Any]] = []
            for turn in store.chat_turns(chat["id"]):
                waiting.extend(self._quoted(turn))
                if not (turn["said"] or turn["role"] == "user"):
                    continue
                content = turn["content"]
                if (
                    turn["role"] == "user"
                    and isinstance(content, list)
                    and content
                    and all(block.get("type") == "tool_result" for block in content)
                ):
                    # The tool traffic rides as `user` rows, and it is not the reader's
                    # line. Handed to the page, each was an empty bubble, and each —
                    # being `done` — told a page reopened mid-turn that nothing was
                    # still being answered, so it never took the stream up again
                    # (2026-09-14). Its cards are already gathered above.
                    continue
                entry: dict[str, Any] = {
                    "n": turn["n"],
                    "role": turn["role"],
                    "said": turn["said"],
                    "stage": turn["stage"],
                    "error": turn["error"],
                    "made": turn["made"],
                    # The words of the answer to a reader's turn, read as a text is
                    # read (`chat/record.py`); None where none were.
                    "words": turn.get("words"),
                }
                if turn["role"] == "assistant" and turn["said"] and waiting:
                    entry["quotes"] = waiting
                    waiting = []
                turns.append(entry)
            return self._json(
                {
                    "chat": chat,
                    "turns": turns,
                    # How long it has run, in the seconds it is metered in.
                    "seconds": round(store.chat_seconds(chat["id"]), 1),
                }
            )
        return self._json({"error": "not found"}, 404)

    def _quoted(self, turn: dict[str, Any]) -> list[dict[str, Any]]:
        """The cards quoted in a tool-result turn, as the jobs stand now.

        A quote is the `quote` of a `quote_build` or `quote_conversation` result
        (`Chats.answer`). The job it names is read back live where the process still
        has it — built since, or refused — and the stored quote stands in where it
        does not, which is a restart: the card then says what it said, and its press
        finds out.
        """
        content = turn.get("content")
        if turn.get("role") != "user" or not isinstance(content, list):
            return []
        found: list[dict[str, Any]] = []
        for block in content:
            if not isinstance(block, dict) or block.get("type") != "tool_result":
                continue
            try:
                result = json.loads(str(block.get("content") or ""))
            except json.JSONDecodeError:
                continue
            quote = result.get("quote") if isinstance(result, dict) else None
            if not isinstance(quote, dict) or not quote.get("id"):
                continue
            job = self._own_job(str(quote["id"]))
            found.append(job.state() if job is not None else quote)
        return found

    def _chat_turn_state(self, chat_id: str, n: int) -> dict[str, Any]:
        """What became of the answer to turn `n`, from the live feed or the store.

        The feed is the live copy and dies with the process; the store is what a tab
        that reconnects after a restart finds. Both say the same thing.
        """
        feed = self.chats.feed_for(chat_id, n)
        if feed is not None:
            errors = [json.loads(data) for kind, data in feed.events if kind == "error"]
            read = [json.loads(data) for kind, data in feed.events if kind == "words"]
            return {
                "text": feed.text(),
                "done": feed.closed,
                "error": errors[-1]["message"] if errors else "",
                # The cards this turn quoted, for a page polling rather than streaming.
                "quotes": [json.loads(data) for kind, data in feed.events if kind == "quote"],
                "words": read[-1] if read else None,
            }
        turns = self.chats.store.chat_turns(chat_id)
        asked = next((turn for turn in turns if turn["n"] == n), None)
        answered = "".join(
            str(turn["said"]) for turn in turns if turn["n"] > n and turn["role"] == "assistant"
        )
        stage = str(asked["stage"]) if asked else "done"
        error = str(asked["error"]) if asked else ""
        if stage == "working":
            # Nothing in this process is answering it: every turn it answers has a feed.
            # Start-up marks such a turn failed, so this is the moment between; said as
            # over, rather than `done: false` to a page that would wait for good
            # (targum-internal#269).
            error = error or CHAT_RESTARTED
        return {
            "text": answered,
            "done": True,
            "error": error,
            "words": asked.get("words") if asked else None,
        }

    #: How long a tail waits for the next event before it says it is still here.
    STREAM_PATIENCE_S = 15.0

    def _chat_stream(self, chat_id: str, n: int) -> None:
        """Tail one turn as server-sent events.

        Written past `_send` on purpose: that sets a `Content-Length` and gzips, and a
        stream has neither. Caddy sits in front on the box and buffers what it is not
        told not to, hence `X-Accel-Buffering`. A tab that reconnects sends the last id
        it saw and gets what it missed; a tab that closed is a broken pipe, which ends
        this thread and nothing else.
        """
        feed = self.chats.feed_for(chat_id, n)
        after = 0
        held = self.headers.get("Last-Event-ID", "")
        if held.isdigit():
            after = int(held) + 1
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Accel-Buffering", "no")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True
        try:
            if feed is None:
                # After a restart there is no live copy; the store's answer is the whole
                # stream, sent as the one closing event.
                state = self._chat_turn_state(chat_id, n)
                kind = "error" if state["error"] else "done"
                payload = {"message": state["error"]} if state["error"] else {"text": state["text"]}
                self._chat_event(0, kind, json.dumps(payload, ensure_ascii=False))
                self._chat_seen(chat_id)
                return
            while True:
                fresh, closed = feed.wait(after, self.STREAM_PATIENCE_S)
                for index, kind, data in fresh:
                    self._chat_event(index, kind, data)
                    after = index + 1
                if closed and after >= len(feed.events):
                    # The whole answer reached a page that was showing it, so it is not
                    # news. Every reply used to ring the bell as "We replied: …" though
                    # the reader had watched it arrive (2026-09-14).
                    self._chat_seen(chat_id)
                    return
                if not fresh:
                    self.wfile.write(b": still here\n\n")
                    self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            return

    def _chat_seen(self, chat_id: str) -> None:
        """An answer was delivered to a page that was open on it."""
        store = getattr(self.chats, "store", None)
        if store is not None:
            store.chat_opened(chat_id)

    def _chat_event(self, index: int, kind: str, data: str) -> None:
        lines = "".join(f"data: {line}\n" for line in data.split("\n"))
        self.wfile.write(f"id: {index}\nevent: {kind}\n{lines}\n".encode())
        self.wfile.flush()

    def _chat_audio(self, chat_id: str, n: int, person: Person | None) -> None:
        """The answer to turn `n`, read aloud. Push-to-talk out: a clip, not a stream.

        Made once and kept beside the transcript, then served like any media file. The
        press is the spend — a reader who did not press hears nothing and pays nothing —
        and the clip's seconds come out of the same eight hours a recording does, read
        off the clip and never off the text. It is claimed at the voice's price for the
        words, so the box's day and the account's see it before it is spent, and settled
        to the clip — including a clip that was made and then could not be kept.
        """
        from . import speech
        from .chat import hebrew as hebrew_module

        store = self.chats.store
        home = self._home()
        where = home / "chats" / "audio"
        kept = (
            next((p for p in where.glob(f"{chat_id}-{n}.*") if p.is_file()), None)
            if where.is_dir()
            else None
        )
        if kept is not None:
            return self._send_file(kept, "audio/mpeg" if kept.suffix == ".mp3" else "audio/wav")
        usable, why = speech.available()
        if not usable:
            return self._json(
                {
                    "error": self._say(
                        "serve.cannot-read-aloud", "We can't read aloud here: {why}.", why=why
                    )
                },
                402,
            )
        turns = store.chat_turns(chat_id)
        said = "".join(
            str(turn["said"]) for turn in turns if turn["n"] > n and turn["role"] == "assistant"
        )
        # In the conversation's own language: a French conversation is read in French,
        # and only its own lines are read, never the translations under them.
        opened = store.chat_owned(person.id if person else None, chat_id) or {}
        spoken_in = str(opened.get("language") or "he")
        found = hebrew_module.pairs(said, spoken_in)
        text = "\n".join(pair.hebrew for pair in found) if found else said.strip()
        if not text:
            return self._json(
                {
                    "error": self._say(
                        "serve.there-s-nothing-for-us-to",
                        "There's nothing for us to read aloud yet.",
                    )
                },
                404,
            )
        seconds = hebrew_module.seconds_for(hebrew_module.words_in(text))
        job = Job(
            ui=self._page_language(),
            id=f"speak-{chat_id}-{n}",
            source=f"chat:{chat_id}",
            estimate=seconds / 60 * speech.PRICES[speech.NAME],
            seconds=seconds,
            stage="working",
            owner=person.id if person else None,
            home=home,
            admin=bool(person and self.store.is_admin(person.email)),
            kind="chat",
        )
        self.library.jobs[job.id] = job
        self.library.remember(job)
        refused = self.library.claim_turn(job)
        if refused:
            job.stage = "blocked"
            job.blocked = refused
            self.library.remember(job)
            return self._json({"error": refused}, 402)
        try:
            clip = speech.render(text, where / f"{chat_id}-{n}", language=spoken_in)
        except Exception as error:
            # Anything, not only what `speech` says in words: a claim left held by an
            # exception nobody caught stays counted against the day until it ages out.
            job.stage = "failed"
            made = error.seconds if isinstance(error, speech.Interrupted) else 0.0
            if made > 0:
                self._settle_speech(job, made, chat_id)
            else:
                self.library.release(job)
            self.library.remember(job)
            if not isinstance(error, TargumError):
                traceback.print_exc()
                incidents_module.record(self.library.incidents, "speak", error, job=job.id)
            said = error.message if isinstance(error, TargumError) else "The voice did not answer."
            return self._json({"error": said}, 502)
        job.stage = "done"
        self._settle_speech(job, clip.seconds, chat_id)
        self.library.remember(job)
        self._send_file(clip.path, clip.kind)

    def _settle_speech(self, job: Job, seconds: float, chat_id: str) -> None:
        """Settle a spoken reply to the seconds the voice made, and put what they cost on
        the conversation's own total beside what its turns cost."""
        from . import speech

        job.seconds = seconds
        spent = Usage()
        spent.add_seconds(speech.NAME, seconds)
        job.spent = spent.cost()
        self.library.settle(job)
        if job.spent > 0:
            self.chats.store.chat_add_spent(chat_id, job.spent)

    def _chat_hear(self, query: dict[str, list[str]]) -> None:
        """A line spoken into the microphone, written down and asked. Push-to-talk in.

        The clip's seconds are metered as the reader's words — the same allowance, the
        same sum — and the turn it becomes counts the reply alone, so nothing is charged
        twice. The transcriber the recording pipeline uses is the one used here.

        Offered in every conversation since 2026-09-14 ("people should be able to talk to
        targum"), not only a Hebrew one: a conversation held in Hebrew is written down as
        Hebrew, and every other one lets the transcriber hear which language it was — a
        reader of Italian asks in Italian or in English. The line carries the language
        and the note of where the reader is, as a typed line does.
        """
        from . import transcribe as transcribe_module
        from .audio import probe as probe_module
        from .chat.session import mode_for, talking

        if self.chats is None or self.chats.store is None:
            return self._json({"error": "not found"}, 404)
        if not self.chats.usable:
            return self._json({"error": self._say("job.no-key", NO_KEY)}, 402)
        person = self._person()
        person_id = person.id if person else None
        chat_id = query.get("chat", [""])[0]
        owned = self.chats.store.chat_owned(person_id, chat_id) if chat_id else None
        if chat_id and owned is None:
            return self._json({"error": "not found"}, 404)
        spoken = self._asked_language(query.get("language", [""])[0])
        about = None
        try:
            about = _about(json.loads(query.get("about", [""])[0] or "null"))
        except ValueError:
            about = None
        home = self._home()
        # What the conversation is held in decides what the clip is heard as: a Hebrew
        # conversation in the talk shape is Hebrew, and anything else is left to the
        # transcriber to recognise. Italian is too, though it talks (targum-internal
        # #280): its readers ask in Italian or in English, and a clip told it is Italian
        # comes back as Italian whatever was said.
        if owned is not None:
            held_in = str(owned.get("language") or spoken)
            held = talking(owned, held_in)
        else:
            held_in = spoken
            held = mode_for(spoken, self.library.talks(home, person_id)) == "talk"
        hear_as = "he" if held and held_in.split("-")[0].lower() == "he" else ""
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return self._json(
                {
                    "error": self._say(
                        "serve.we-didn-t-hear-anything-try", "We didn't hear anything. Try again."
                    )
                },
                400,
            )
        if length > MAX_UPLOAD:
            return self._json(
                {
                    "error": self._say(
                        "serve.that-s-too-long-for-one",
                        "That's too long for one line. Try a shorter one.",
                    )
                },
                413,
            )
        body = self.rfile.read(length)
        kind = (self.headers.get("Content-Type") or "audio/webm").split(";")[0].strip()
        suffixes = {
            "audio/webm": ".webm",
            "audio/ogg": ".ogg",
            "audio/mp4": ".m4a",
            # What a phone's own recorder hands back, where the browser cannot record
            # live and the press opens it (2026-09-14).
            "audio/x-m4a": ".m4a",
            "audio/aac": ".aac",
            "audio/3gpp": ".3gp",
            "audio/amr": ".amr",
            "audio/mpeg": ".mp3",
            "audio/wav": ".wav",
            "audio/x-wav": ".wav",
        }
        clips = home / "chats" / "clips"
        clips.mkdir(parents=True, exist_ok=True)
        clip = clips / f"{secrets.token_hex(8)}{suffixes.get(kind, '.webm')}"
        clip.write_bytes(body)
        try:
            heard = probe_module.examine(clip).duration
        except TargumError as error:
            clip.unlink(missing_ok=True)
            return self._json({"error": error.message}, 400)
        transcriber = transcribe_module.build(transcribe_module.default_name())
        usable, why = transcriber.available()
        if not usable:
            clip.unlink(missing_ok=True)
            return self._json(
                {
                    "error": self._say(
                        "serve.cannot-transcribe",
                        "We can't write speech down here: {why}.",
                        why=why,
                    )
                },
                402,
            )
        admin = bool(person and self.store.is_admin(person.email))
        job = Job(
            ui=self._page_language(),
            id=f"hear-{secrets.token_hex(6)}",
            source=f"chat:{chat_id or 'new'}",
            estimate=heard / 60 * transcriber.price_per_minute(),
            seconds=heard,
            stage="working",
            owner=person_id,
            home=home,
            admin=admin,
            kind="chat",
        )
        self.library.jobs[job.id] = job
        self.library.remember(job)
        refused = self.library.claim_turn(job)
        if refused:
            job.stage = "blocked"
            job.blocked = refused
            self.library.remember(job)
            clip.unlink(missing_ok=True)
            return self._json({"error": refused}, 402)
        try:
            transcript = transcriber.transcribe(clip, hear_as)
        except TargumError as error:
            job.stage = "failed"
            self.library.release(job)
            self.library.remember(job)
            return self._json({"error": error.message}, 502)
        job.spent = transcriber.spent.cost()
        job.stage = "done"
        self.library.settle(job)
        self.library.remember(job)
        text = " ".join(
            str(getattr(word, "text", "")) for word in getattr(transcript, "words", [])
        ).strip()
        if not text:
            return self._json(
                {
                    "error": self._say(
                        "serve.we-didn-t-catch-that-try",
                        "We didn't catch that. Try again a little closer.",
                    )
                },
                400,
            )
        asked = self.chats.say(
            person,
            home,
            chat_id,
            text,
            admin=admin,
            heard_seconds=heard,
            about=about,
            language=spoken,
            ui=self._page_language(),
        )
        self._json({"chat": asked.chat_id, "turn": asked.n, "heard": text})

    def _chat_say(self, payload: dict[str, Any]) -> None:
        """The reader's line. Written down and handed to a worker; the answer streams."""
        if self.chats is None or self.chats.store is None:
            return self._json({"error": "not found"}, 404)
        if not self.chats.usable:
            return self._json({"error": self._say("job.no-key", NO_KEY)}, 402)
        text = str(payload.get("text") or "").strip()
        if not text:
            return self._json(
                {"error": self._say("serve.say-something-first", "Say something first.")}, 400
            )
        if len(text) > 4000:
            return self._json(
                {
                    "error": self._say(
                        "serve.that-s-too-long-for-one-2",
                        "That's too long for one turn. Try a shorter one.",
                    )
                },
                413,
            )
        person = self._person()
        person_id = person.id if person else None
        chat_id = str(payload.get("chat") or "")
        if chat_id and self.chats.store.chat_owned(person_id, chat_id) is None:
            return self._json({"error": "not found"}, 404)
        admin = bool(person and self.store.is_admin(person.email))
        about = _about(payload.get("about"))
        # The text sent with the line, if one was: read from its own job, never from
        # the payload, so what the model is told about it is what the server knows.
        brought = None
        sent = self._own_job(str(payload.get("brought") or ""))
        if sent is not None:
            state = sent.state()
            brought = {
                key: state[key]
                for key in (
                    "title",
                    "pages",
                    "doubtful",
                    "segments",
                    "excerpt",
                    "stage",
                    "blocked",
                    "error",
                    "conversation",
                )
            }
            brought["from"] = sent_as(sent)
        asked = self.chats.say(
            person,
            self._home(),
            chat_id,
            text,
            admin=admin,
            about=about,
            brought=brought,
            language=self._asked_language(payload.get("language")),
            ui=self._page_language(),
        )
        return self._json({"chat": asked.chat_id, "turn": asked.n})

    def _voice(self, payload: dict[str, Any]) -> None:
        """Hear a silent text: the press in the reader that makes one section's audio
        (targum-internal#246). The press is the spend — claimed at the estimate, in the
        hours a recording comes out of, settled to the clip's own seconds — and only
        where the voice has a price: an unpriced voice is not for sale.
        """
        from . import speech
        from .audio import manifest as manifest_module
        from .chat import hebrew as hebrew_module
        from .models import SegmentedDocument
        from .models import read_artifact as read
        from .render import split_sections

        home = self._home()
        folder = self.library.within(home, str(payload.get("name") or ""))
        if folder is None:
            return self._json({"error": "not found"}, 404)
        if not speech.priced():
            return self._json(
                {
                    "error": self._say(
                        "serve.we-can-t-give-this-text", "We can't give this text a voice yet."
                    )
                },
                402,
            )
        usable, why = speech.available()
        if not usable:
            return self._json(
                {
                    "error": self._say(
                        "serve.cannot-read-aloud", "We can't read aloud here: {why}.", why=why
                    )
                },
                402,
            )
        try:
            number = int(payload.get("section") or 0)
        except (TypeError, ValueError):
            return self._json({"error": "not found"}, 404)
        segmented = read(SegmentedDocument, folder / "segments.json")
        if segmented is None:
            return self._json({"error": "not found"}, 404)
        if not speech.speaks(segmented.language):
            # Yiddish and Aramaic: the voice does not read them, so it is not for sale.
            return self._json(
                {
                    "error": self._say(
                        "serve.we-can-t-read-this-language",
                        "We can't read this language aloud yet.",
                    )
                },
                402,
            )
        section = next((one for one in split_sections(segmented) if one.number == number), None)
        if section is None:
            return self._json({"error": "not found"}, 404)
        kept = manifest_module.load(folder)
        if kept is not None:
            part = kept.part_for(section.segment_ids)
            if part is not None and part.audio:
                return self._json({"ready": True})
        # A second press while the first is still being made joins it. Two presses
        # would otherwise make the same section twice and pay for both.
        underway = next(
            (
                other
                for other in list(self.library.jobs.values())
                if other.kind == "voice"
                and other.home == home
                and other.options.get("folder") == folder.name
                and other.options.get("section") == number
                and other.stage not in ("done", "failed", "blocked")
            ),
            None,
        )
        if underway is not None:
            return self._json(underway.state())
        wanted = set(section.segment_ids)
        words = hebrew_module.words_in(
            *(segment.text for segment in segmented.segments if segment.id in wanted)
        )
        seconds = hebrew_module.seconds_for(words)
        person = self._person()
        job = Job(
            ui=self._page_language(),
            id=secrets.token_hex(8),
            source=str(folder),
            options={"voice": True, "folder": folder.name, "section": number},
            owner=person.id if person else None,
            home=home,
            admin=bool(person and self.store.is_admin(person.email)),
            kind="voice",
            seconds=seconds,
            estimate=seconds / 60 * speech.PRICES[speech.NAME],
            title=section.title,
        )
        # Written down before it is claimed. `Store.claim` reserves by updating the job's
        # row, and a row that is not there yet takes the update silently: the press was
        # claimed at nothing, in money and in hours, until the worker settled it.
        self.library.jobs[job.id] = job
        self.library.remember(job)
        refused = self.library.claim_turn(job, kind="voice")
        if refused:
            job.stage = "blocked"
            job.blocked = refused
            self.library.remember(job)
            return self._json({"error": refused}, 402)
        self.library.enqueue(job)
        self._json(job.state())

    def _suggest(self) -> None:
        """One text that fits this reader's level and interests, for the Suggested door
        on Learn (2026-09-11): the same pick the conversation's "Something to read"
        makes, with no conversation, no turn and no card — the sheet draws it and Open
        goes to its library row, or to the text where it is built already."""
        if self.chats is None or self.chats.store is None:
            return self._json({"suggestion": None})
        from .chat import tools as chat_tools

        person = self._person()
        admin = bool(person and self.store.is_admin(person.email))
        query = parse_qs(urlparse(self.path).query)
        # In the language Learn is showing, which is the switcher's (2026-09-13).
        spoken = self._asked_language(query.get("language", [""])[0])
        ctx = self.chats.context(person, self._home(), "", admin, spoken)
        # What the page says the reader has finished, by catalogue id: that is kept in
        # the browser, and a finished suggestion makes way for the next (2026-09-11).
        skip = query.get("skip", [""])[0]
        done = sorted({one.strip() for one in skip.split(",") if one.strip()})[:200]
        rows = chat_tools.suggest_next(ctx, {"limit": 1, "skip": done}).get("suggestions") or []
        if rows:
            # Said on Learn, in the page's language (targum-internal#287).
            rows[0]["because"] = chat_tools.because_in(rows[0], self._page_language())
        return self._json({"suggestion": rows[0] if rows else None})

    def _chat_suggest(self, payload: dict[str, Any]) -> None:
        """The commonest ask, answered without the model (targum-internal#240): the
        press is the ask, the card's button is still the build's press, and no turn is
        run. `Chats.suggest` does the work; this is the door."""
        if self.chats is None or self.chats.store is None:
            return self._json({"error": "not found"}, 404)
        person = self._person()
        person_id = person.id if person else None
        chat_id = str(payload.get("chat") or "")
        if chat_id and self.chats.store.chat_owned(person_id, chat_id) is None:
            return self._json({"error": "not found"}, 404)
        skip = [str(one) for one in payload.get("skip") or [] if isinstance(one, str)]
        admin = bool(person and self.store.is_admin(person.email))
        answer = self.chats.suggest(
            person,
            self._home(),
            chat_id,
            admin=admin,
            skip=skip,
            language=self._asked_language(payload.get("language")),
            ui=self._page_language(),
        )
        if "error" in answer:
            return self._json({"error": answer["error"]}, int(answer.get("status") or 409))
        return self._json(answer)

    def _chat_save(self, payload: dict[str, Any]) -> None:
        """Save as targum, pressed at the foot of the record: the conversation written
        down and priced, the same card the model's `quote_conversation` hands the page.
        The reader's own press, no model turn, and still only a quote — the card's
        button is the spend, as it is everywhere.
        """
        if self.chats is None or self.chats.store is None:
            return self._json({"error": "not found"}, 404)
        from .chat import tools as chat_tools

        person = self._person()
        person_id = person.id if person else None
        chat_id = str(payload.get("chat") or "")
        if not chat_id or self.chats.store.chat_owned(person_id, chat_id) is None:
            return self._json({"error": "not found"}, 404)
        admin = bool(person and self.store.is_admin(person.email))
        ctx = self.chats.context(person, self._home(), chat_id, admin)
        answer = chat_tools.quote_conversation(ctx, {})
        if answer.get("error"):
            return self._json({"error": answer["error"]}, 409)
        return self._json({"quote": answer["quote"], "lines": answer.get("lines", 0)})

    # -- accounts -----------------------------------------------------------

    #: How many of the commonest words the page may ask for at once, and how far down the
    #: list it may go: past a few thousand the "commonest" claim stops meaning much.
    COMMON_PAGE = 50
    COMMON_REACH = 3000
    #: The most the back office will let in at one press. A batch is a small group
    #: by definition, and the command line is there for a bigger one.
    DOOR_AT_ONCE = 25

    def _common_words(self, query: dict[str, list[str]]) -> None:
        """The commonest words of modern Hebrew, in order, with the meaning the glossary
        already holds and the band each sits in (targum-internal#245). For "Words you
        may already know" on Learn: a reader who reads Hebrew already marks the ones
        they know, fifty at a time, and the count rises because the count did. The
        page leaves out what is on the ledger; nothing here is bought — a word the
        glossary does not hold is shown bare."""
        from .annotate.base import BAND_NAMES
        from .annotate.frequency import FrequencyBands
        from .annotate.gloss import cached_gloss, gloss_provider_name
        from .chat import hebrew as hebrew_module

        try:
            offset = max(0, int(query.get("offset", ["0"])[0]))
            limit = max(
                1, min(self.COMMON_PAGE, int(query.get("limit", [str(self.COMMON_PAGE)])[0]))
            )
        except ValueError:
            offset, limit = 0, self.COMMON_PAGE
        offset = min(offset, self.COMMON_REACH)
        # In the language the page is in (2026-09-13). wordfreq has lists for French,
        # Russian and Italian as well as Hebrew; a language with none gets an empty page.
        spoken = self._asked_language(query.get("language", [""])[0])
        forms = hebrew_module.common_words(
            n=min(self.COMMON_REACH, offset + limit), language=spoken
        )
        page = forms[offset : offset + limit]
        target = hebrew_module.gloss_language(self._reads(self._person()))
        bands = FrequencyBands()
        provider = gloss_provider_name()
        rows = []
        for form in page:
            held = cached_gloss(form, spoken, target, provider)
            rows.append(
                {
                    "form": form,
                    "band": BAND_NAMES.get(bands.band(form, spoken), ""),
                    "meaning": held.gloss if held else "",
                }
            )
        self._json(
            {
                "words": rows,
                "offset": offset,
                "next": offset + len(page)
                if len(page) == limit and offset + limit < self.COMMON_REACH
                else None,
                "into": target,
                "language": spoken,
            }
        )

    def _hours(self, person_id: int | None) -> dict[str, Any]:
        """The month's hours, used and allowed, and when the month turns. Reckoned in one
        place for the two answers that carry it: the conversation list, and who is
        signed in — which every page asks, so Your Progress and the account panel can
        say the count without a request of their own (targum-internal#237)."""
        allowed = self.library.upload_seconds
        # `self.store` rather than the chat's: the same store, and this answer is owed
        # whether or not a conversation is configured at all.
        used = self.store.hours_used(person_id, self.library._month_from()) if self.store else 0.0
        return {
            "used": round(used / 3600, 2),
            "allowed": None if allowed is None else round(allowed / 3600, 2),
            "ends": self.library._month_ends(),
        }

    def _me(self) -> None:
        person = self._person()
        if person is None:
            return self._json({"signedIn": False})
        answer = {
            "signedIn": True,
            "email": person.email,
            "revision": self.store.revision(person),
            "counts": self.store.counts(person),
            # The month's hours, for the account panel and Your Progress: the real count,
            # off the chat page where it stood in every reader's face (2026-09-10).
            "hours": self._hours(person.id),
            # Which languages this account is learning, and which it is offered a
            # translation into. The pages that offer either narrow to these; `_prepare`
            # refuses anything else whatever a picker was showing, because a picker is
            # not a boundary.
            "learning": sorted(self._learning(person)),
            "reads": sorted(self._reads(person)),
            # Whether `reads` is their answer or the default, so the arrival asks which
            # language they read only of somebody who has never said (2026-09-20).
            "readsSaid": self.store.said_reading(person.id),
            # The language the switcher shows (2026-09-13), so every page and every device
            # opens in the language the reader last chose.
            "language": self.store.language(person.id),
            # Which series this account follows (2026-09-11), so a browser that has just
            # signed in draws the same row as the one they followed from.
            "follows": (["weekly"] if self.store.following(person.email) else [])
            + self.store.series_followed(person.email),
            # Whether what they do in a text is being recorded: whether this box keeps such
            # a record at all, and whether this reader has left it on (#127). A page sends
            # nothing unless both are true.
            "events": {"kept": keeps_events(), "on": self.store.collects(person.id)},
        }
        answer.update(self.store.profile(person))
        self._json(answer)

    def _events(self, payload: dict[str, Any]) -> None:
        """What a reader did in a text, appended (targum-internal#127). Signed in only, and
        only where the deployment keeps such a record; otherwise it keeps nothing and says
        so, which is an answer a page can stop sending on."""
        person = self._person()
        if person is None:
            return self._json({"signedIn": False}, 401)
        if not keeps_events():
            return self._json({"signedIn": True, "kept": 0, "keeping": False})
        sent = payload.get("events")
        kept = self.store.add_events(person, sent if isinstance(sent, list) else [])
        self._json({"signedIn": True, "kept": kept, "keeping": self.store.collects(person.id)})

    def _events_choice(self, payload: dict[str, Any]) -> None:
        """The reader's own two controls over it: stop or start the record, and erase it."""
        person = self._person()
        if person is None:
            return self._json({"signedIn": False}, 401)
        erased = self.store.forget_events(person) if payload.get("forget") else 0
        if "collect" in payload:
            self.store.set_collects(person, bool(payload.get("collect")))
        self._json(
            {
                "signedIn": True,
                "events": {"kept": keeps_events(), "on": self.store.collects(person.id)},
                "erased": erased,
            }
        )

    def _totals(self) -> None:
        """Time listened, time watched and words read, by day, language and medium."""
        person = self._person()
        if person is None:
            return self._json({"signedIn": False}, 401)
        showing = keeps_events() and self.store.collects(person.id)
        self._json(
            {
                "signedIn": True,
                "kept": keeps_events(),
                "on": self.store.collects(person.id),
                "totals": self.store.totals(person.id) if showing else [],
            }
        )

    def _rename(self, payload: dict[str, Any]) -> None:
        """What to call them. Empty clears it, and the avatar goes back to the address."""
        person = self._person()
        if person is None:
            return self._json({"signedIn": False}, 401)
        stored = self.store.rename(person, str(payload.get("name") or ""))
        answer = {"signedIn": True, "name": stored}
        answer.update(self.store.profile(person))
        self._json(answer)

    def _interest(self, payload: dict[str, Any]) -> None:
        """The subjects a reader named on arrival (targum-internal#294).

        A list since 2026-09-17. A bare string is still read, because the column held
        one word for three weeks and a page cached in somebody's browser will go on
        sending one until it is reloaded.
        """
        person = self._person()
        if person is None:
            return self._json({"signedIn": False}, 401)
        asked = payload.get("interest")
        named: str | list[str]
        if isinstance(asked, list):
            named = [str(word) for word in asked]
        else:
            named = str(asked or "")
        try:
            kept = self.store.set_interest(person, named)
        except ValueError as error:
            return self._json({"error": str(error)}, 400)
        self._json({"signedIn": True, "interest": list(kept)})

    def _declared(self, payload: dict[str, Any]) -> None:
        """The rung a reader named on arrival (targum-internal#306, 2026-09-19).

        Kept as a seed: `level.seed` reads it only while nothing about the reader has
        been measured, and no page prints it back."""
        person = self._person()
        if person is None:
            return self._json({"signedIn": False}, 401)
        try:
            kept = self.store.set_declared(person, str(payload.get("level") or ""))
        except ValueError as error:
            return self._json({"error": str(error)}, 400)
        self._json({"signedIn": True, "declared": kept})

    def _know_slip(self, rest: str, payload: dict[str, Any]) -> None:
        """ "I know this" on a line that came back changed (2026-09-18).

        `{"known": true}` takes it out of What to work on; false puts it back. The slip
        itself stays: it is the record, and the record is not the queue.
        """
        person = self._person()
        if person is None:
            return self._json({"signedIn": False}, 401)
        try:
            slip_id = int(rest)
        except ValueError:
            return self._json({"error": "not found"}, 404)
        if not self.store.know_slip(person.id, slip_id, bool(payload.get("known", True))):
            return self._json({"error": "not found"}, 404)
        self._json({"ok": True})

    def _address(self, payload: dict[str, Any]) -> None:
        """How the conversation addresses them in Hebrew (2026-09-14)."""
        person = self._person()
        if person is None:
            return self._json({"signedIn": False}, 401)
        try:
            stored = self.store.set_address(person, str(payload.get("address") or ""))
        except ValueError as error:
            return self._json({"error": str(error)}, 400)
        self._json({"signedIn": True, "address": stored})

    def _languages(self, payload: dict[str, Any]) -> None:
        """What they are learning and what they read into, from the profile page.

        Both lists at once, replaced whole: a form that submits a set of ticks is
        saying what the set is, not what changed. Refused whole too — a request that
        fails on one list leaves the other as it was, so the page can put its boxes
        back from the answer.
        """
        person = self._person()
        if person is None:
            return self._json({"signedIn": False}, 401)
        before = self._reads(person)
        try:
            learning = self.store.choose(person, "learning", list(payload.get("learning") or []))
            reads = self.store.choose(person, "reading", list(payload.get("reads") or []))
        except ValueError as error:
            return self._json(
                {
                    "error": str(error),
                    "learning": sorted(self._learning(person)),
                    "reads": sorted(self._reads(person)),
                },
                400,
            )
        # A reader is a file, and a language taken away only leaves one when the file is
        # written again. Adding one never needs this: a translation is only in a folder
        # if it was bought, and buying writes the reader. Off this thread, because a
        # home full of long books is seconds of work and the page is waiting.
        if before - reads:
            from .cli import rebuild_home

            home = self.library.home(person)
            threading.Thread(
                target=rebuild_home,
                args=(home,),
                kwargs={"reads": sorted(reads)},
                daemon=True,
            ).start()
        answer = {"signedIn": True, "learning": sorted(learning), "reads": sorted(reads)}
        answer.update(self.store.profile(person))
        self._json(answer)

    def _language(self, payload: dict[str, Any]) -> None:
        """The language switcher's press (2026-09-13): which of their languages the reader
        is in now. Kept on the account so another device opens in it too; refused for a
        language they are not learning, whatever the page offered."""
        person = self._person()
        if person is None:
            return self._json({"signedIn": False}, 401)
        try:
            chosen = self.store.use_language(person, str(payload.get("language") or ""))
        except ValueError as error:
            return self._json(
                {"error": str(error), "language": self.store.language(person.id)}, 400
            )
        self._json({"signedIn": True, "language": chosen})

    def _asked_language(self, raw: object) -> str:
        """The language a page asked in, where it is one of the reader's; otherwise the
        one the switcher shows. A page is not a boundary."""
        person = self._person()
        code = str(raw or "").strip().lower()
        if code and code in self._learning(person):
            return code
        if person is not None and self.store is not None:
            return self.store.language(person.id)
        return "he"

    def _form(self) -> dict[str, str]:
        """A form post, read as a form. The landing page is a page, not an app."""
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > 8192:
            return {}
        body = self.rfile.read(length).decode("utf-8", errors="replace")
        return {key: values[0] for key, values in parse_qs(body).items() if values}

    def _mail_language(self, email: str, into: object) -> str:
        """The language a sign-in email is written in (targum-internal#186).

        The page's own `targum:into` first, which is what the person chose to read in on
        this device — never `Accept-Language`, which for an olah is often Hebrew or English
        on a phone bought in Israel whatever she reads. It is taken only where it is a
        language targum reads into, and, for an address that already has an account, one
        that account reads or an account that has not said (the English default). Failing
        that, the one language the account reads, and English.
        """
        from .translate.prompts import INTO

        offered = {code for code, _ in INTO}
        asked = str(into or "").strip().lower()
        person = self.store.person_by_email(email) if self.store is not None else None
        reads = self.store.reads(person.id) if person is not None else set()
        if asked in offered and (person is None or asked in reads or reads == {"en"}):
            return asked
        if len(reads) == 1:
            return next(iter(reads))
        return "en"

    #: Desk pages rendered in another language, by language and then by page.
    translated: dict[str, dict[str, str]] = {}

    def _desk(self, name: str, english: str) -> str:
        """A desk page in the language this reader's interface is in, where one was
        rendered for it, and the English otherwise (targum-internal#184)."""
        pages = self.translated.get(self._ui_language(), {})
        return pages.get(name) or english

    def _ui_language(self) -> str:
        """The language the chrome speaks to this reader in: the one language their account
        reads other than English, where a desk rendering in it exists — English beside it
        or not, since reading Russian is the choice that says so. English otherwise: for a
        visitor, for an account that reads only English, and for one that reads two other
        languages, where nothing says which."""
        person = self._person()
        if person is None or self.store is None:
            return "en"
        others = [code for code in self.store.reads(person.id) if code != "en"]
        return others[0] if len(others) == 1 and others[0] in self.translated else "en"

    def _say(self, key: str, english: str, **fill: object) -> str:
        """A sentence the server sends back, in the language of whoever asked
        (targum-internal#184): `english` where their catalogue has not said it."""
        return said_in(self._page_language(), key, english, **fill)

    def _named(self, code: str) -> str:
        """A language's name in the language of whoever asked."""
        from .strings import SOURCE, catalogue
        from .translate.prompts import language_name

        asked = self._page_language()
        said = catalogue(asked).get(f"language.{code}") if asked != SOURCE else None
        return said or language_name(code)

    def _page_language(self) -> str:
        """The language a public page speaks to whoever asked: a signed-in reader's
        interface language, by the same rule as the desk; for a visitor, the first
        language their browser asks for that targum has a catalogue in — English where it
        has none of them (David, 2026-09-15, targum-internal#184)."""
        if self._person() is not None:
            return self._ui_language()
        self._said_by_browser = True
        return best_language(self.headers.get("Accept-Language", ""))

    def _front_language(self) -> str:
        """The language the front door answers in.

        The browser's, as every other public page, unless the visitor pressed the
        switcher in the bar: `?lang=` is the whole of the choice, kept in the address
        rather than on a cookie or an account, because a stranger reading a landing page
        has neither and should not be given one to change the language of a page.
        """
        from .strings import languages

        asked = parse_qs(urlparse(self.path).query).get("lang", [""])[0].strip().lower()
        return asked if asked in set(languages()) else self._page_language()

    def _asked(self) -> str:
        """The language a visitor pressed for — `?lang=` — or "" where they pressed nothing
        and the browser decided. The difference is a choice: what was pressed is carried
        to the next page and kept, and what was inferred is only ever used."""
        from .strings import languages

        asked = parse_qs(urlparse(self.path).query).get("lang", [""])[0].strip().lower()
        return asked if asked in set(languages()) else ""

    def _sign_in(self, payload: dict[str, Any]) -> None:
        email = str(payload.get("email") or "")
        if not plausible(email):
            return self._json(
                {
                    "error": self._say(
                        "serve.we-couldn-t-read-that-as",
                        "We couldn't read that as an email address. Check it and try again.",
                    )
                },
                400,
            )
        # Hosted, an address has to have been invited. Without this, standing a box up
        # on a public address with a funded key lets whoever finds it open an account and
        # start spending — held back only by a per-account rail that is $3.00 a *day*,
        # which is a rate limit and not a plan limit.
        #
        # Said plainly rather than answered with a silent "check your email". That does
        # tell an asker whether an address is on the list, and for an alpha of a handful
        # of people the confusion of a link that never arrives costs more than the
        # enumeration is worth. Revisit when the list is long enough to be worth probing.
        if self.require_account and not self.store.may_join(email):
            return self._json({"error": NOT_OPEN}, 403)
        if self.store.asking_too_often(email):
            return self._json(
                {
                    "error": self._say(
                        "serve.we-ve-sent-a-few-links",
                        "We've sent a few links to that address already. Check your spam folder.",
                    )
                },
                429,
            )
        language = self._mail_language(email, payload.get("into"))
        token = self.store.start_sign_in(email)
        link = f"{self.address}/account/enter?t={token}"
        try:
            self.mailer.send(email, link, language=language)
        except Exception:
            # Said plainly, because a link that never arrives with a cheerful "check
            # your email" is the worst version of this failing.
            return self._json(
                {
                    "error": self._say(
                        "serve.we-couldn-t-send-the-link",
                        "We couldn't send the link. Try again in a minute.",
                    )
                },
                502,
            )
        self._json({"sent": True, "message": SENT})

    #: Sign-ins started with Google and not yet finished, by `state`. In memory and not
    #: on disk: they live ten minutes, they belong to no account yet, and a restart
    #: losing them costs somebody one press of a button.
    _google_begun: ClassVar[dict[str, Any]] = {}

    def _google_redirect(self) -> str:
        """Where Google sends them back. Must match the console's registered URI exactly."""
        return f"{self.address.rstrip('/')}/account/google/back"

    def _google_out(self) -> None:
        """Send a reader to Google, remembering what is needed to finish."""
        from . import google as google_module

        if not google_module.configured() or not self._host_is_ours() or not self.address:
            return self._send(404, b"not found", "text/plain")
        begun = google_module.begin(self._google_redirect())
        # Swept before it grows: nothing here is ever read after ten minutes, and a box
        # left running would otherwise keep every abandoned sign-in for ever.
        for state, old in list(self._google_begun.items()):
            if google_module.stale(old):
                self._google_begun.pop(state, None)
        self._google_begun[begun.state] = begun
        self._go(begun.where)

    def _google_back(self, query: dict[str, list[str]]) -> None:
        """Finish a sign-in Google has proved, or say plainly why not.

        The order matters. `state` first, so a request nobody started is refused before
        anything is spent; then the exchange, which is the only network call; then the
        address, refused unless Google says it has verified it; and only then
        `may_join`, which is the same gate the mailed link goes through and the reason
        this is not a way around the guest list.
        """
        from . import google as google_module

        if not google_module.configured() or not self._host_is_ours() or not self.address:
            return self._send(404, b"not found", "text/plain")

        def refuse(said: str) -> None:
            page = signin_page(language=self._page_language(), said=said)
            return self._send(200, page.encode("utf-8"), HTML)

        state = (query.get("state") or [""])[0]
        begun = self._google_begun.pop(state, None) if state else None
        if begun is None or google_module.stale(begun):
            # Also what an abandoned tab looks like an hour later, so it is said the way
            # a spent link is: not an error, just start again.
            return refuse(
                self._say(
                    "serve.that-sign-in-took-too-long",
                    "That sign-in took too long. Try again.",
                )
            )
        if (query.get("error") or [""])[0]:
            # They pressed Cancel on Google's own screen. Nothing went wrong.
            return refuse(
                self._say("serve.no-harm-done", "No harm done. Sign in whichever way suits you.")
            )
        code = (query.get("code") or [""])[0]
        if not code:
            return refuse(
                self._say(
                    "serve.that-sign-in-didn-t-finish", "That sign-in didn't finish. Try again."
                )
            )
        try:
            answer = google_module.exchange(code, begun.verifier, self._google_redirect())
            email = google_module.address_from(answer)
        except google_module.Refused as error:
            return refuse(str(error))

        # The same gate the mailed link goes through. Without it, standing OAuth up on a
        # funded box lets anybody with a Google account open one and start spending.
        if self.require_account and not self.store.may_join(email):
            return refuse(NOT_OPEN)
        got = self.store.sign_in_verified(email)
        if got is None:
            return refuse(NOT_OPEN)
        _, session = got
        from .accounts import SESSION_DAYS

        where = f"/?k={self.token}&signin=welcome" if self.token else "/?signin=welcome"
        self._go(where, self._session_cookie(session, SESSION_DAYS))

    def _enter(self, token: str) -> None:
        got = self.store.finish_sign_in(token) if token else None
        if got is None:
            # Not an error: a spent or stale link is what a second press looks like,
            # and the way out of it is to ask for another, which that page offers.
            return self._send(
                200, signin_page(expired=True, language=self._page_language()).encode("utf-8"), HTML
            )
        _, session = got
        from .accounts import SESSION_DAYS

        where = f"/?k={self.token}&signin=welcome" if self.token else "/?signin=welcome"
        self._go(where, self._session_cookie(session, SESSION_DAYS))

    def _sign_out(self) -> None:
        self.store.sign_out(self._cookie(SESSION_COOKIE) or None)
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header(
            "Set-Cookie", f"{SESSION_COOKIE}=; HttpOnly; SameSite=Lax; Path=/; Max-Age=0"
        )
        body = json.dumps({"signedIn": False}).encode("utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _forget(self) -> None:
        person = self._person()
        if person is None:
            return self._json(
                {"error": self._say("serve.you-re-not-signed-in", "You're not signed in.")}, 401
            )
        self.store.forget(person)
        self._sign_out()

    def _sync(self, payload: dict[str, Any]) -> None:
        """Take what the browser has, hand back what it is missing.

        Push and pull in one call rather than two, because they are one act: a browser
        that pushed and then failed to pull is a browser showing stale data it just
        contributed to. The pull uses the revision the client came in with, so a push
        does not echo straight back at whoever made it.
        """
        person = self._person()
        if person is None:
            return self._json({"signedIn": False}, 401)
        try:
            since = int(payload.get("since") or 0)
        except (TypeError, ValueError):
            since = 0
        # An allowlist of kinds, and every row filtered down to the dicts. The list check
        # alone let `{"words": ["nonsense"]}` through to the merge, which calls .get on
        # each row and raised on a string — a signed-in reader breaking their own sync
        # rather than a hole, but a 500 where a quiet skip belongs.
        changes = {
            name: [row for row in payload[name] if isinstance(row, dict)]
            for name in ("words", "meanings", "phrases", "docs", "days")
            if isinstance(payload.get(name), list)
        }
        if changes:
            self.store.push(person, changes)
        # The counts go back with the answer because the page asked for them before it
        # pushed, and a panel that says "nothing kept yet" to somebody who has just had
        # eight hundred words claimed is worse than saying nothing at all.
        answer = {"signedIn": True, "counts": self.store.counts(person)}
        answer.update(self.store.pull(person, since))
        self._json(answer)

    def _prepare(self, payload: dict[str, Any]) -> None:
        """Price a build, and say what it will take before anything is spent."""
        from .translate.prompts import INTO, READING

        # A picker is not a boundary. The page offers three languages in and two out
        # because those are the pairs an upload has been taken end to end in; a request
        # naming anything else is refused here rather than half-built.
        wanted = str(payload.get("to") or "en")
        if wanted not in {code for code, _ in INTO}:
            offered = ", ".join(self._named(code) for code, _ in INTO)
            return self._json(
                {
                    "error": self._say(
                        "serve.we-translate-into",
                        "We translate into {languages}.",
                        languages=offered,
                    )
                },
                400,
            )
        # And of those, the ones this account reads. Buying a translation into a language
        # nobody said they read spends money on a page they cannot use — and every word
        # they keep from it carries a meaning in it into every text they own. The
        # sentence names where to change that, because it is theirs to change now.
        if wanted not in self._reads():
            return self._json(
                {
                    "error": self._say(
                        "serve.not-in-profile",
                        "{language} isn't in your profile yet. Add it there and try again.",
                        language=self._named(wanted),
                    )
                },
                400,
            )
        # `from` is allowed to be empty: that means work it out from the text. A catalogue
        # text names its own language and is not somebody's upload, so it is let past.
        #
        # Carrying `translations` used to let any `from` past as well. Nothing needed it:
        # the catalogue's button names a catalogue source, which the line below lets
        # through, and a reader's own translation is uploaded rather than named.
        reading = str(payload.get("from") or "")
        known = {code for code, _ in READING}
        if reading and reading not in known:
            from . import catalogue as catalogue_module

            if catalogue_module.matching(str(payload.get("source") or "")) is None:
                names = ", ".join(self._named(code) for code, _ in READING)
                return self._json(
                    {
                        "error": self._say(
                            "serve.we-can-read", "We can read {languages}.", languages=names
                        )
                    },
                    400,
                )
        # And of those, the ones this account said it is learning.
        if reading in known and reading not in self._learning():
            return self._json(
                {
                    "error": self._say(
                        "serve.not-in-profile",
                        "{language} isn't in your profile yet. Add it there and try again.",
                        language=self._named(reading),
                    )
                },
                400,
            )

        try:
            source = self._source_from(payload)
            # A reader's own translation is a file like the source is, and it is written
            # down here so the price — and then the build — is worked out with it in hand.
            mine = self._translation_from(payload)
        except TargumError as error:
            return self._json({"error": error.message}, 400)
        if mine:
            payload = dict(payload, translations=mine)
        elif payload.get("translations"):
            # The Library's button names the published translations a catalogue text
            # has, and the reader switches between them. That list is taken only where the
            # catalogue itself holds it for this source: anything else in it is a path or
            # a link the request chose, and `Build` would read it — off this server's
            # disk, for a path — and put it on the reader's page as a translation.
            from . import catalogue as catalogue_module

            entry = catalogue_module.matching(source)
            published = {rendering.source for rendering in entry.translations} if entry else set()
            asked = payload.get("translations")
            if not isinstance(asked, list) or not {str(one) for one in asked} <= published:
                return self._json(
                    {
                        "error": self._say(
                            "serve.that-translation-is-not-one-targum",
                            "That translation is not one targum has.",
                        )
                    },
                    400,
                )
        try:
            spoken_text = self._transcript_from(payload)
        except TargumError as error:
            return self._json({"error": error.message}, 400)
        if spoken_text:
            payload = dict(payload, transcript=spoken_text)

        # Somebody has already translated this one, and that translation is better and
        # free. Said before anything is priced, not after it has been paid for.
        #
        # Only where there is something better to offer, though. Half the catalogue is
        # texts nobody published an English for, which targum translated once and paid for
        # once — those have no `Rendering` to point at, and offering one as an alternative
        # to itself would leave the catalogue's own button unable to build them.
        if not payload.get("translations") and not payload.get("force_machine"):
            from . import catalogue as catalogue_module

            already = catalogue_module.matching(source)
            if already is not None and already.translations:
                return self._json({"catalogue": already.state()})

        person = self._person()
        job = Job(
            ui=self._page_language(),
            id=secrets.token_hex(8),
            source=source,
            options=payload,
            owner=person.id if person else None,
            admin=bool(person and person.admin),
            home=self.library.home(person),
        )
        self.library.jobs[job.id] = job
        self.library.remember(job)
        self.library.prepare(job)
        self.library.remember(job)
        self._json(job.state())

    def _build(self, payload: dict[str, Any]) -> None:
        job = self._own_job(str(payload.get("id", "")))
        if job is None:
            return self._json(
                {
                    "error": self._say(
                        "serve.we-lost-that-build-when-we-2",
                        "We lost that build when we restarted. Start it again, and "
                        "nothing counts twice.",
                    )
                },
                404,
            )
        if job.stage in {"working", "done"}:
            return self._json(job.state())
        blocked = self.library.claim(job)
        if blocked:
            job.blocked = blocked
            job.stage = "blocked"
            return self._json(job.state(), 402)
        self.library.enqueue(job)
        self._json(job.state())

    def _cover(self, payload: dict[str, Any]) -> None:
        """Draw the covers for one text, from the key this deployment runs with.

        Priced and claimed against the same budget as everything else that costs money,
        and refused by the same sentences when there is none left. A reader is never
        shown the number — see the guidelines on what the product says about cost — but
        the ceiling is real and this is inside it.
        """
        from . import covers as covers_module

        home = self._home()
        folder = self.library.within(home, str(payload.get("name") or ""))
        if folder is None:
            return self._json({"error": "not found"}, 404)

        illustrator = covers_module.build()
        usable, detail = illustrator.available()
        if not usable:
            return self._json({"error": detail}, 400)

        entry, plan = self.library.cover_plan(folder, bool(payload.get("chapters")))
        if entry is None:
            return self._json(
                {
                    "error": self._say(
                        "serve.we-can-t-find-anything-here", "We can't find anything here to draw."
                    )
                },
                400,
            )
        if not plan:
            return self._json(
                {"drawn": 0, "message": self._say("serve.already-drawn", "Already drawn.")}
            )

        person = self._person()
        job = Job(
            ui=self._page_language(),
            id=secrets.token_hex(8),
            source=entry.source,
            title=entry.title,
            language=entry.language,
            owner=person.id if person else None,
            admin=bool(person and person.admin),
            home=home,
            options={"cover": entry.id, "plan": plan, "chapters": bool(payload.get("chapters"))},
            estimate=len(plan) * illustrator.price,
            total=len(plan),
        )
        blocked = self.library.claim(job)
        if blocked:
            return self._json({"error": blocked}, 400)
        self.library.jobs[job.id] = job
        self.library.enqueue(job)
        self._json(job.state())

    def _chapter(self, payload: dict[str, Any]) -> None:
        """Translate one chapter of a targum already on disk, and rewrite its page.

        A book is bought a chapter at a time. This is the asking — from the contents
        page, from the end of the one before, or from a reader who wants chapter nine.
        """
        home = self._home()
        folder = self.library.within(home, str(payload.get("name") or ""))
        if folder is None:
            return self._json({"error": "not found"}, 404)
        # `number` names one chapter; `all` buys every one still waiting. The second is
        # for somebody about to lose their connection, which is the one case where the
        # whole book at once is what a reader actually wants.
        whole = bool(payload.get("all"))
        try:
            number = 0 if whole else int(payload.get("number") or 0)
        except (TypeError, ValueError):
            return self._json({"error": "not found"}, 404)
        # What is already here, whichever way it was asked for. `all` had this check and
        # one chapter did not, so the reader's prefetch — which asks for the next chapter
        # at 60% of this one, every time, knowing nothing about what is on disk — bought
        # a chapter of Song of Songs that the published translation already covered.
        # A catalogue text is free and arrives complete, so every one of its chapters is
        # ready from the start and every prefetch against it was a purchase waiting to
        # happen. Readiness is derived from the artifacts by `chapters()`, so this asks
        # the only thing that can answer it.
        # Which language to buy it in. The reader asks in the one it is showing; without
        # that this fell through to English, so the second chapter of a Russian book came
        # back in English — and `run_chapter` then rebuilt the whole reader around it.
        #
        # Checked against what the folder already holds rather than taken at its word: a
        # prefetch nobody pressed must not be able to buy a language nobody asked for.
        here = self.library.targets(folder)
        wanted = str(payload.get("to") or "").strip()
        target = wanted if wanted in here else (here[0] if here else "en")

        # An imported recording buys by the part: a chapter that is waiting is waiting
        # on a transcript, and the build path — not run_chapter — is what knows how to
        # grow the document around one.
        if (folder / "audio" / "parts.json").is_file():
            return self._buy_parts(folder, number, whole, target)

        standing = self.library.chapters(folder, target)
        waiting: list[int] = []
        if whole:
            waiting = [c["number"] for c in standing if not c["ready"]]
            if not waiting:
                return self._json({"ready": True})
        elif any(c["number"] == number and c["ready"] for c in standing):
            return self._json({"ready": True})

        person = self._person()
        job = Job(
            ui=self._page_language(),
            id=secrets.token_hex(8),
            source=str(folder),
            options={
                "chapters": waiting if whole else [number],
                "folder": folder.name,
                "to": target,
            },
            owner=person.id if person else None,
            admin=bool(person and person.admin),
            home=home,
        )
        blocked = self.library.already_over(job)
        if blocked:
            job.blocked = blocked
            job.stage = "blocked"
            return self._json(job.state(), 402)
        self.library.jobs[job.id] = job
        self.library.remember(job)
        self.library.enqueue(job)
        self._json(job.state())

    def _buy_parts(self, folder: Path, number: int, whole: bool, target: str) -> None:
        """Queue the hearing of one page's parts — or of every page still waiting.

        `number` is the page's, as it is for any book: the reader and the contents page
        both send the section they show, and a part that ran long fills two of them.

        Ready is what the page can show, never whether a transcript is on disk. This
        answered `ready` to any part that had been heard, and the page reloaded itself
        onto the same "not transcribed yet" — pressed again and again, nothing happened —
        whenever the hearing had landed and the rest had not: a build still translating
        it, the next-part prefetch that bought it a minute before the press, or a build
        the box killed at the words, which left the transcript, the segments and even
        the translation behind a page that was never rewritten. Rebuilding around a
        transcript already heard spends nothing; its hearing and its English are cached.
        """
        from .models import SegmentedDocument, read_artifact
        from .render.builder import split_sections

        try:
            data = json.loads((folder / "document.json").read_text(encoding="utf-8"))
            source = str(data.get("source") or "")
        except (OSError, json.JSONDecodeError):
            source = ""
        segmented = read_artifact(SegmentedDocument, folder / "segments.json")
        if not source or segmented is None:
            return self._json({"error": "not found"}, 404)
        plan = json.loads((folder / "audio" / "parts.json").read_text(encoding="utf-8"))
        known = {int(span.get("number") or 0) for span in plan.get("parts") or []}
        sections = split_sections(segmented)
        by_id = {segment.id: segment for segment in segmented.segments}
        ready = {c["number"]: c["ready"] for c in self.library.chapters(folder, target)}

        if whole:
            pages = [section for section in sections if not ready.get(section.number, True)]
        else:
            page = next((section for section in sections if section.number == number), None)
            if page is None:
                return self._json({"error": "not found"}, 404)
            pages = [page]
        buying = sorted({n for one in pages for n in _parts_on(one, by_id)} & known)
        if not buying:
            return self._json({"ready": True})

        # Already on its way: the press waits on that build rather than queueing a second
        # one behind it, or being told `ready` while it is still translating.
        home = self._home()
        coming: dict[int, Job] = {}
        for job in self.library.jobs.waiting(now() - self.library.RECENT_MS):
            if job.stage not in ("queued", "working") or job.home != home:
                continue
            if job.options.get("folder") != folder.name:
                continue
            for n in job.options.get("parts") or []:
                coming.setdefault(int(n), job)
        if all(n in coming for n in buying):
            return self._json(coming[buying[0]].state())
        buying = [n for n in buying if n not in coming]

        if (
            not whole
            and ready.get(number)
            and not _still_waiting(folder / "reader" / pages[0].filename)
        ):
            return self._json({"ready": True})

        person = self._person()
        job = Job(
            ui=self._page_language(),
            id=secrets.token_hex(8),
            source=source,
            options={"parts": buying, "folder": folder.name, "to": target},
            owner=person.id if person else None,
            admin=bool(person and person.admin),
            home=home,
        )
        blocked = self.library.already_over(job)
        if blocked:
            job.blocked = blocked
            job.stage = "blocked"
            return self._json(job.state(), 402)
        self.library.jobs[job.id] = job
        self.library.remember(job)
        self.library.enqueue(job)
        self._json(job.state())

    def _watch_job(self, payload: dict[str, Any]) -> None:
        """The reader put the strip away: tell them by email instead, however short the
        build. A promise made on the page is kept whatever the clock says."""
        job = self._own_job(str(payload.get("id") or ""))
        if job is None:
            return self._json({"error": "not found"}, 404)
        finished = job.stage in ("done", "failed", "blocked")
        watching = self.library.can_mail(job.owner) and not finished
        if watching:
            job.options["mail"] = True
            self.library.remember(job)
        self._json({"watching": watching})

    def _trash(self, payload: dict[str, Any]) -> None:
        name = str(payload.get("name") or "")
        if not self.library.trash(self._home(), name):
            return self._json({"error": "not found"}, 404)
        self._json({"trashed": True, "days": TRASH_DAYS})

    def _restore(self, payload: dict[str, Any]) -> None:
        name = str(payload.get("name") or "")
        if not self.library.restore(self._home(), name):
            return self._json({"error": "not found"}, 404)
        self._json({"restored": True})

    def _gloss_word(self, payload: dict[str, Any]) -> None:
        """One word, because a reader asked for it.

        A whole-text glossary is bought before anything is read and most of it never
        is. This is the other way round: nothing is looked up until you want it, and
        what you look up is cached, so the same word is free everywhere after that.
        """
        lemma = str(payload.get("lemma", "")).strip()
        source = str(payload.get("source", "")).strip()
        target = str(payload.get("target", "en")).strip() or "en"
        # The sentence it was tapped in, which is what tells עם from עם. Capped: a
        # sentence is what this is for, and a paragraph is what a page could send.
        sentence = str(payload.get("sentence", "")).strip()[:400]
        if not lemma or not source:
            return self._json({"error": "bad request"}, 400)

        from .annotate.gloss import GLOSS_MODEL, AnthropicGlosses, cached_gloss, gloss_one

        # The same model the build's own glossary was bought with. The provider's name
        # is part of the cache key, so asking here with the provider's default — Opus,
        # where a hosted build uses Sonnet — made every word the build had already paid
        # for cost a second time, on the dearer of the two, the moment a reader tapped
        # it. Bought once, free everywhere is the claim; this is what makes it true.
        provider = AnthropicGlosses(GLOSS_MODEL)
        if payload.get("free"):
            # A card opening asks this first: is the meaning already held? Answered from
            # the cache and never bought, so a page can ask for every word it shows.
            held = cached_gloss(lemma, source, target, provider.name)
            return self._json(
                {
                    "lemma": lemma,
                    "meaning": held.gloss if held else None,
                    "citation": held.citation if held else "",
                    "plural": held.plural if held else "",
                    "cached": bool(held),
                    # Whether a sentence chose the sense. A held meaning with no
                    # sentence behind it is what the page asks again, with its own.
                    "grounded": bool(held and held.grounded),
                }
            )
        usable, _ = provider.available()
        if not usable:
            return self._json({"error": self._say("job.no-key", NO_KEY)}, 402)
        try:
            sense = gloss_one(
                lemma,
                source,
                target,
                provider,
                context=sentence,
                on_grounded=grounding_note(self.store, lemma, source, target),
            )
        except TargumError as error:
            return self._json({"error": error.message}, 502)
        except Exception as error:
            traceback.print_exc()
            incidents_module.record(self.library.incidents, "/gloss", error)
            return self._json(
                {
                    "error": self._say(
                        "serve.we-couldn-t-look-that-word",
                        "We couldn't look that word up just now. Try again in a moment.",
                    )
                },
                502,
            )
        return self._json(
            {
                "lemma": lemma,
                "meaning": sense.gloss if sense else "",
                "citation": sense.citation if sense else "",
                "plural": sense.plural if sense else "",
                "grounded": bool(sense and sense.grounded),
            }
        )

    def _gloss_phrase(self, payload: dict[str, Any]) -> None:
        """A few words of a sentence, because a reader selected them.

        The sentence's translation is already on the page; what is asked is which piece
        of it these words are, so the answer can be the parallel text and not a second
        translation of it. Cached on the sentence, the translation and the run: the same
        selection in the same text is free for everyone after the first.
        """
        phrase = str(payload.get("phrase", "")).strip()
        sentence = str(payload.get("sentence", "")).strip()
        translation = str(payload.get("translation", "")).strip()
        source = str(payload.get("source", "")).strip()
        target = str(payload.get("target", "en")).strip() or "en"

        from .annotate.phrase import (
            PHRASE_MODEL,
            AnthropicPhrases,
            cached_phrase,
            phrase_one,
            within_limits,
        )

        # A phrase-in-context service, not a translator: the run has to be in the
        # sentence, and both texts have to be the size of a sentence.
        if not source or not within_limits(phrase, sentence, translation):
            return self._json({"error": "bad request"}, 400)

        # The model glosses are bought on, for the reason `_gloss_word` gives: the
        # provider's name is in the key, and a different one here would pay twice.
        provider = AnthropicPhrases(PHRASE_MODEL)
        held = cached_phrase(phrase, sentence, translation, source, target, provider.name)
        if held is not None:
            # Answered from the cache and never bought, so it needs no key to ask.
            return self._json(
                {
                    "meaning": held.meaning,
                    "quoted": held.quoted,
                    "kind": held.kind,
                    "citation": held.citation,
                    "cached": True,
                }
            )
        usable, _ = provider.available()
        if not usable:
            return self._json({"error": self._say("job.no-key", NO_KEY)}, 402)
        try:
            answer = phrase_one(phrase, sentence, translation, source, target, provider)
        except TargumError as error:
            return self._json({"error": error.message}, 502)
        except Exception as error:
            traceback.print_exc()
            incidents_module.record(self.library.incidents, "/phrase", error)
            return self._json(
                {
                    "error": self._say(
                        "serve.we-couldn-t-look-that-phrase",
                        "We couldn't look that phrase up just now. Try again in a moment.",
                    )
                },
                502,
            )
        return self._json(
            {
                "meaning": answer.meaning,
                "quoted": answer.quoted,
                "kind": answer.kind,
                "citation": answer.citation,
            }
        )

    #: What a text or a translation may arrive as. An epub is a book; the rest is text.
    #: Subtitles are a transcript with its timings, which is the cheapest transcript
    #: there is. Audio rides through the same door while it fits under MAX_UPLOAD —
    #: a podcast episode does; an audiobook waits on the chunked door.
    READABLE = frozenset(
        {".txt", ".md", ".markdown", ".epub", ".srt", ".vtt"}
        | {".mp3", ".m4a", ".m4b", ".aac", ".ogg", ".opus", ".flac", ".wav"}
    )

    def _written(self, name: str, content: str) -> Path:
        """One uploaded file on disk, under a directory nothing else will land in.

        A directory of its own per upload. Two people — or one person twice — dropping
        files with the same name used to overwrite each other, because the basename was
        the whole path.
        """
        suffix = Path(name).suffix.lower()
        if suffix in {".aax", ".aa"}:
            raise TargumError("This file is protected, so we can't read it.")
        if suffix not in self.READABLE:
            raise TargumError(
                f"We can't read '{suffix}' files. Save it as plain text or "
                "markdown and drop that in instead."
            )
        uploads = self._home() / "uploads" / secrets.token_hex(8)
        uploads.mkdir(parents=True, exist_ok=True)
        # Only the file's own name, never a path it carries.
        path = uploads / Path(name).name
        path.write_bytes(base64.b64decode(content))
        return path

    def _source_from(self, payload: dict[str, Any]) -> str:
        """A dropped file is written next to the readers; anything else is a source."""
        many = payload.get("uploads")
        if isinstance(many, list) and many:
            return str(self._gathered([str(one) for one in many]))
        upload = str(payload.get("upload") or "")
        if upload:
            held = self._upload_folder(upload)
            if held is None:
                raise TargumError("We can't find that upload any more. Send it again.")
            folder, meta = held
            target = folder / Path(str(meta.get("name") or "")).name
            if not target.is_file():
                raise TargumError("We can't find that upload any more. Send it again.")
            if target.suffix.lower() in PICTURE_SUFFIXES or target.suffix.lower() == ".pdf":
                return str(self._gathered([upload]))
            return str(target)
        name = payload.get("name")
        content = payload.get("content")
        if name and content:
            return str(self._written(str(name), str(content)))

        source = str(payload.get("source", "")).strip()
        # A link or an identifier, never a path: see `ingest.fetchable`. A source the
        # catalogue names is ours whatever its shape. The same sentence answers an empty
        # source and a refused one, because both are somebody not yet having given a text.
        from . import catalogue as catalogue_module
        from . import ingest as ingest_module

        if not source or (
            not ingest_module.fetchable(source) and catalogue_module.matching(source) is None
        ):
            raise TargumError("Paste a link, drop a file, or give a Gutenberg or Wikisource id.")
        return source

    def _gathered(self, uploads: list[str]) -> Path:
        """Chunked uploads of pages, made into one source that stays.

        A set of pictures is one text, in the order the reader chose them, and the
        folder is the source: the first upload's folder keeps the lot, numbered, and
        the others are emptied. The chunked door's own marks come off — `.meta.json`
        is what the sweep eats after a day, and a document points back at this folder
        for as long as it is on the shelf, the way the JSON door's uploads are kept.
        A lone PDF goes through the same motions so it, too, outlives the sweep.
        """
        from . import vision

        if len(uploads) > MAX_PAGES:
            raise TargumError(
                f"That's {len(uploads)} pictures. We can read up to {MAX_PAGES} at a time."
            )
        found: list[tuple[Path, Path]] = []
        for upload in uploads:
            held = self._upload_folder(upload)
            if held is None:
                raise TargumError("We can't find that upload any more. Send it again.")
            folder, meta = held
            target = folder / Path(str(meta.get("name") or "")).name
            if not target.is_file():
                raise TargumError("We can't find that upload any more. Send it again.")
            found.append((folder, target))
        pictures = all(vision.is_picture(target) for _, target in found)
        if not pictures and (len(found) > 1 or found[0][1].suffix.lower() != ".pdf"):
            raise TargumError(
                "When you send several files, they all need to be pictures of one text."
            )
        home, _ = found[0]
        kept: list[Path] = []
        for number, (folder, target) in enumerate(found, start=1):
            moved = home / f"{number:02d}-{target.name}"
            if folder == home:
                target.rename(moved)
            else:
                shutil.move(str(target), str(moved))
                shutil.rmtree(folder, ignore_errors=True)
            kept.append(moved)
        for mark in (".meta.json", ".sha256"):
            (home / mark).unlink(missing_ok=True)
        shutil.rmtree(home / ".part", ignore_errors=True)
        self.library._used.pop(self._home(), None)
        return home if pictures else kept[0]

    def _translation_from(self, payload: dict[str, Any]) -> list[str]:
        """A translation the reader already has, written down for the aligner.

        Supplying one is what makes a build free: the pipeline pays for a machine
        translation only when nothing else was handed to it. What comes back goes into
        the job's options, where `Build` reads it — and it goes in on the way past the
        door rather than out of the request, so nothing can name a file it did not
        upload.
        """
        name = payload.get("translationName")
        content = payload.get("translationContent")
        if not (name and content):
            return []
        return [str(self._written(str(name), str(content)))]

    # -- the chunked door ---------------------------------------------------

    UPLOAD_ID = re.compile(r"^[0-9a-f]{16}$")

    def _upload(self, route: str) -> None:
        pieces = route.split("/")[2:]
        if pieces == ["begin"]:
            return self._upload_begin(self._small_json())
        if len(pieces) == 2 and self.UPLOAD_ID.match(pieces[0]):
            if pieces[1] == "end":
                return self._upload_end(pieces[0], self._small_json())
            if pieces[1].isdigit():
                return self._upload_chunk(pieces[0], int(pieces[1]))
        self._json({"error": "not found"}, 404)

    def _small_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        if length > 4096:
            return {}
        try:
            data = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            return {}
        return data if isinstance(data, dict) else {}

    def _upload_begin(self, payload: dict[str, Any]) -> None:
        """Refuse everything refusable before a byte arrives."""
        from .audio import AUDIO_SUFFIXES, DRM_SUFFIXES
        from .video import VIDEO_SUFFIXES

        name = Path(str(payload.get("name") or "")).name
        suffix = Path(name).suffix.lower()
        try:
            size = int(payload.get("size") or 0)
        except (TypeError, ValueError):
            size = 0
        if suffix in DRM_SUFFIXES:
            return self._json(
                {
                    "error": self._say(
                        "serve.this-file-is-protected-so-we",
                        "This file is protected, so we can't read it.",
                    )
                },
                400,
            )
        if suffix in PICTURE_SUFFIXES or suffix == ".pdf":
            # A picture or a handout, through the recording's door: the same chunks, the
            # same quota, a ceiling of its own.
            if size <= 0 or size > MAX_PICTURE_BYTES:
                limit = MAX_PICTURE_BYTES // (1024 * 1024)
                said = (
                    self._say(
                        "serve.pdf-over-mb",
                        "That PDF is over {size} MB. Try a smaller one.",
                        size=limit,
                    )
                    if suffix == ".pdf"
                    else self._say(
                        "serve.picture-over-mb",
                        "That picture is over {size} MB. Try a smaller one.",
                        size=limit,
                    )
                )
                return self._json({"error": said}, 413)
        elif suffix not in AUDIO_SUFFIXES | VIDEO_SUFFIXES:
            return self._json(
                {
                    "error": self._say(
                        "serve.we-can-only-read-a-recording",
                        "We can only read a recording, a video, a picture or a PDF.",
                    )
                },
                400,
            )
        else:
            moving = suffix in VIDEO_SUFFIXES
            ceiling = MAX_VIDEO_BYTES if moving else MAX_AUDIO_BYTES
            if size <= 0 or size > ceiling:
                limit = ceiling // (1024 * 1024 * 1024)
                said = (
                    self._say(
                        "serve.video-over-gb",
                        "That video is over {size} GB. Try a shorter one.",
                        size=limit,
                    )
                    if moving
                    else self._say(
                        "serve.recording-over-gb",
                        "That recording is over {size} GB. Try a shorter one.",
                        size=limit,
                    )
                )
                return self._json({"error": said}, 413)
        home = self._home()
        self.library.sweep_uploads(home)
        if self.library.used(home) + size > MEDIA_QUOTA_BYTES:
            gigs = MEDIA_QUOTA_BYTES // (1024 * 1024 * 1024)
            return self._json(
                {
                    "error": self._say(
                        "serve.over-quota",
                        "That would take your recordings over {size} GB. Delete one and try again.",
                        size=gigs,
                    )
                },
                413,
            )
        upload = secrets.token_hex(8)
        folder = home / "uploads" / upload
        (folder / ".part").mkdir(parents=True, exist_ok=True)
        (folder / ".meta.json").write_text(
            json.dumps({"name": name, "size": size, "made": now()}), encoding="utf-8"
        )
        self._json({"upload": upload, "chunk": CHUNK_BYTES})

    def _upload_folder(self, upload: str) -> tuple[Path, dict[str, Any]] | None:
        folder = self.library.within(self._home() / "uploads", upload)
        if folder is None or not (folder / ".meta.json").is_file():
            return None
        try:
            meta = json.loads((folder / ".meta.json").read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None
        return folder, meta

    def _upload_chunk(self, upload: str, number: int) -> None:
        held = self._upload_folder(upload)
        if held is None:
            return self._json({"error": "not found"}, 404)
        folder, meta = held
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > CHUNK_BYTES:
            return self._json(
                {"error": self._say("serve.that-chunk-is-too-big", "That chunk is too big.")}, 413
            )
        expected = int(meta.get("size") or 0)
        if number * CHUNK_BYTES >= expected + CHUNK_BYTES:
            # A chunk the declared size has no room for is a lie about the size.
            return self._json({"error": "not found"}, 404)
        body = self.rfile.read(length)
        (folder / ".part" / f"{number:06d}").write_bytes(body)
        self._json({"got": number})

    def _upload_end(self, upload: str, payload: dict[str, Any]) -> None:
        """Assemble the chunks in order, prove the file, and say what it is."""
        import hashlib

        from .audio import parts as parts_module
        from .audio import probe as probe_module

        held = self._upload_folder(upload)
        if held is None:
            return self._json({"error": "not found"}, 404)
        folder, meta = held
        name = Path(str(meta.get("name") or "recording.mp3")).name
        target = folder / name
        pieces = sorted((folder / ".part").glob("[0-9]*"), key=lambda piece: int(piece.name))
        if [int(piece.name) for piece in pieces] != list(range(len(pieces))):
            return self._json(
                {
                    "error": self._say(
                        "serve.part-of-the-upload-didn-t",
                        "Part of the upload didn't reach us. Send it again.",
                    )
                },
                400,
            )
        digest = hashlib.sha256()
        with target.open("wb") as out:
            for piece in pieces:
                body = piece.read_bytes()
                digest.update(body)
                out.write(body)
        claimed = str(payload.get("sha256") or "")
        if claimed and claimed != digest.hexdigest():
            target.unlink()
            return self._json(
                {
                    "error": self._say(
                        "serve.the-upload-reached-us-damaged-send",
                        "The upload reached us damaged. Send it again.",
                    )
                },
                400,
            )
        for piece in pieces:
            piece.unlink()
        (folder / ".sha256").write_text(digest.hexdigest(), encoding="utf-8")
        # The same bytes already here — another upload, or a recording already
        # imported — are the same file: point at what exists rather than keep two.
        twin = self.library.holding(self._home(), digest.hexdigest(), except_for=folder)
        if twin is not None:
            shutil.rmtree(folder, ignore_errors=True)
            return self._json(twin)
        if target.suffix.lower() in PICTURE_SUFFIXES:
            # Proved as a picture, and nothing more: it is read when the reader asks
            # for a price, which is where the reading is reserved and settled.
            from . import vision

            try:
                vision.probe(target)
            except TargumError as error:
                shutil.rmtree(folder, ignore_errors=True)
                return self._json({"error": error.message}, 400)
            return self._json({"upload": upload, "picture": True})
        if target.suffix.lower() == ".pdf":
            # Counted at the door so a book is refused before a page of it is read.
            from .ingest import pdf as pdf_module

            try:
                pages = pdf_module.page_count(target)
            except TargumError as error:
                shutil.rmtree(folder, ignore_errors=True)
                return self._json({"error": error.message}, 400)
            if pages > MAX_PAGES:
                shutil.rmtree(folder, ignore_errors=True)
                too_many = f"That PDF has {pages} pages. We can read up to {MAX_PAGES} at a time."
                return self._json({"error": too_many}, 413)
            return self._json({"upload": upload, "pages": pages})
        from .video import VIDEO_SUFFIXES

        moving = target.suffix.lower() in VIDEO_SUFFIXES
        try:
            found = probe_module.examine(target, allow_video=moving)
        except TargumError as error:
            shutil.rmtree(folder, ignore_errors=True)
            return self._json({"error": error.message}, 400)
        if not found.has_video and target.stat().st_size > MAX_AUDIO_BYTES:
            # The ceiling was chosen at the door by the suffix's word; the probe has
            # now heard the file. Sound alone in a video container is a recording,
            # and a recording's ceiling is 1 GB whatever the container claims.
            shutil.rmtree(folder, ignore_errors=True)
            return self._json(
                {
                    "error": self._say(
                        "serve.that-recording-is-over-1-gb",
                        "That recording is over 1 GB. Try a shorter one.",
                    )
                },
                413,
            )
        drafted = parts_module.plan(found)
        self._json(
            {"upload": upload, "seconds": round(found.duration, 1), "parts": len(drafted.parts)}
        )

    def _transcript_from(self, payload: dict[str, Any]) -> str:
        """A transcript the reader already has, for the audio they are importing.

        Timings and all, which is what makes the import free of transcription. Same
        door as every upload, for the same reason as `_translation_from`.
        """
        name = payload.get("transcriptName")
        content = payload.get("transcriptContent")
        if not (name and content):
            return ""
        return str(self._written(str(name), str(content)))

    def _serve_glossary(self, folder: str) -> None:
        """The word meanings for one build and one target language, once they exist.

        A reader opens before these are looked up, so it asks for them afterwards and
        fills them in without a reload. Answering "not yet" is a normal reply, not an
        error: the file appears when the lookups finish.

        `?to=` names the language, and the answer says which language it is answering
        about. A reader holding two translations polls for the one it is showing, and a
        reply that arrived after the reader switched has to be fileable rather than
        guessable — a meaning is only ever right about the pair it was written for.
        """
        from .translate.prompts import INTO

        wanted = parse_qs(urlparse(self.path).query).get("to", ["en"])[0]
        # An allowlist rather than a pattern, because this decides a filename. The
        # containment check below is the second lock, not the only one.
        if wanted not in {code for code, _ in INTO}:
            return self._json({"error": "not found"}, 404)
        root = self._home().resolve()
        home = (root / unquote(folder)).resolve()
        target = glossary_path(home, wanted).resolve()
        # English before the files carried a language in the name. Nothing is renamed;
        # the old name is simply still a place a glossary can be.
        if not target.is_file() and wanted == "en":
            target = (home / "glossary.json").resolve()
        if root not in target.parents:
            return self._json({"error": "not found"}, 404)
        if not target.is_file():
            return self._json({"ready": False, "target": wanted})
        try:
            data = json.loads(target.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            # Caught mid-write. The reader is still polling; it will ask again.
            return self._json({"ready": False, "target": wanted})
        entries = data.get("entries")
        if not isinstance(entries, dict):
            return self._json({"ready": False, "target": wanted})
        self._json({"ready": True, "target": wanted, "entries": entries})

    def _open_entry(self, name: str) -> None:
        """One door onto a catalogue text, wherever the link to it was written.

        "When I click on any link to a targum anywhere it should open that targum
        immediately, and not merely bring me to library" (2026-09-17). Every such link
        pointed at `/library#<id>`, which marks the row and scrolls to it — five call
        sites, in the reader, on Learn twice and in the command palette, each of which
        would otherwise have to learn this reader's shelf for itself. A door is one
        place instead, and it works from a page that fetches nothing.

        Two answers, and the second is the one that matters:

        * Built already — go to it. That is the address the library row is a link to.
        * Not built — go to its row with the offer up. **Never straight into a build.**
          What pressing an unbuilt row does is start spending, and a redirect the reader
          did not press is exactly the thing that must not be able to do that. The row
          is one press from reading, which is the whole of the fixable complaint.

        An id nobody has heard of lands on the library too, rather than on a 404: the
        library is the honest answer to "I could not find that text".
        """
        from . import catalogue as catalogue_module

        # The key the request itself arrived with, carried on. Locally it rides in every
        # address and a redirect that dropped it would land on a 403; hosted there is no
        # key and the session cookie travels on its own.
        query = urlparse(self.path).query

        def sent(where: str, fragment: str = "") -> None:
            if query:
                where += ("&" if "?" in where else "?") + query
            self._sent_on(where + fragment)

        entry_id = unquote(name).strip("/")
        entry = next((e for e in catalogue_module.CATALOGUE if e.id == entry_id), None)
        if entry is None:
            return sent("/library")
        # Their own shelf first, then the shared one — the precedence the library page
        # already uses when it merges the two into one list. A reader with nothing of
        # their own is handed the shared copy to start with, and it opens like any built
        # text; a door that looked only at their own home sent them to the offer for a
        # text they can already read.
        folder = self.library.built_from(self._home(), entry.source) or self.library.built_from(
            self.library.shared, entry.source
        )
        if folder:
            return sent("/reader/" + quote(folder) + "/reader/index.html")
        # `#build:` rather than `#<id>`: the library opens the row's offer on this one
        # instead of only marking it, so the press that spends is still a press.
        return sent("/library", "#build:" + quote(entry.id))

    def _serve_thumb(self, name: str) -> None:
        """The cover drawn for one text, where somebody has made one.

        Missing is the ordinary case and not an error: the library draws the text's own
        first letter until an image exists, so a library with no covers at all looks
        deliberate rather than broken. See `scripts/thumbnails.py` for where they come
        from and `catalogue.cover_prompt` for what they are asked to be.

        A chapter falls back to its book. Most chapters in this library are numbered
        rather than titled — a hundred and fifty psalms — and a number is not a subject
        anything could draw, so only chapters that name something get their own image.
        The rest show the book's, which is both free and exactly as consistent with it as
        a reader could ask for.
        """
        root = (self.library.out / "thumbs").resolve()
        wanted = unquote(name)
        if OWNED.match(wanted):
            # An upload's cover is asked for by the text's own name; the home in front
            # of it is put there below, from whoever is asking. A name that arrives
            # already carrying one is asking for another reader's, and the fact that
            # `thumbs/` is one directory for the whole box is what would answer.
            return self._send(404, b"not found", "text/plain")
        # The asker's own first, so a reader who called an upload "genesis" gets their
        # own picture rather than the catalogue's. A chapter falls back to its book, and
        # both halves of that are tried the same way round.
        mine = self._home().name
        chapterless = re.sub(r"-c\d+$", "", wanted)
        for candidate in (f"{mine}-{wanted}", wanted, f"{mine}-{chapterless}", chapterless):
            for suffix, kind in THUMBS:
                target = (root / (candidate + suffix)).resolve()
                if root not in target.parents or not target.is_file():
                    continue
                # The one thing here worth a browser keeping. Everything else this
                # server sends is somebody's reading — no-store, and rightly. A cover is
                # a picture of a book, the same picture for every reader, and refetching
                # it on every visit to the library is the whole page's weight again.
                # Private rather than public: it still travelled a signed-in connection.
                return self._send(200, target.read_bytes(), kind, cache="private, max-age=86400")
        return self._send(404, b"not found", "text/plain")

    def _serve_reader(self, relative: str) -> None:
        """This person's readers, and the shared ones — never another person's.

        Three roots, each guarded on its own: the file has to resolve to *inside* the
        root it was looked for under. The shared home and the weekly are further allowed
        roots, not a relaxation of the first, and the person's own wins where a name is
        in more than one.
        """
        roots = (
            self._home().resolve(),
            self.library.shared.resolve(),
            self.library.weekly.resolve(),
        )
        wanted = unquote(relative)
        for root in roots:
            target = (root / wanted).resolve()
            if target.is_file() and root in target.parents:
                moving = self.MEDIA_KINDS.get(target.suffix.lower())
                if moving:
                    return self._send_file(target, moving)
                kind = "text/html; charset=utf-8" if target.suffix == ".html" else "text/plain"
                # Framed by the front page as a picture of itself (design.md §13,
                # 2026-09-11), and by nothing else on the web: `'self'`, not `'*'`.
                return self._send(200, target.read_bytes(), kind, frames="out")
        # A door the model wrote by hand. It is told to copy a path exactly as the tool
        # returned it, and it copied בסטארטאפ as בסטארטאף — twice in one conversation
        # (2026-09-08) — because a final letter is how Hebrew is spelled and a folder
        # name is not Hebrew. A folder that differs from the one asked for only in its
        # final letters is the folder meant; sent on rather than served in place, so the
        # page's own relative addresses (a video part beside it) still resolve.
        folder, _, rest = wanted.partition("/")
        if folder and rest:
            for root in roots:
                real = _spelled_like(root, folder)
                if real is not None and real != folder:
                    query = urlparse(self.path).query
                    where = f"/reader/{quote(real)}/{quote(rest)}" + (f"?{query}" if query else "")
                    return self._sent_on(where)
        return self._not_found()


def _punctuation_rate(hearing: float) -> float:
    """Dollars a minute for the punctuation a paid hearing may come back without.

    Priced beside the hearing rather than inside it, because it is bought from a
    different provider, and only where a hearing is bought at all.
    """
    from .transcribe.refine import Punctuator

    if not hearing:
        return 0.0
    punctuator = Punctuator()
    return punctuator.dollars_per_minute() if punctuator.available()[0] else 0.0


def _spelled_like(root: Path, folder: str) -> str | None:
    """The one folder under `root` whose name is `folder` with its final letters spelled
    the other way — ף for פ, or פ for ף — or None. Two such folders would be a tie no
    rule should break, so that is None too."""
    from .annotate.moves import FINALS

    folded = folder.translate(FINALS)
    try:
        found = [
            child.name
            for child in root.iterdir()
            if child.is_dir() and child.name.translate(FINALS) == folded
        ]
    except OSError:
        return None
    return found[0] if len(found) == 1 else None


def _parts_on(section: Any, by_id: Mapping[str, Any]) -> set[int]:
    """Which parts of a recording one page holds, from its segments' refs — "part 3",
    "part 3:2", "part 3:waiting" — rather than by assuming page three is part three."""
    found: set[int] = set()
    for sid in section.segment_ids:
        segment = by_id.get(sid)
        head = segment.ref.split(":", 1)[0] if segment is not None else ""
        if head.startswith("part ") and head[5:].isdigit():
            found.add(int(head[5:]))
    return found


def _still_waiting(page: Path) -> bool:
    """Whether the page on disk still says its part is waiting. A page that is missing
    is waiting too: there is nothing there to read."""
    try:
        return 'id="waiting-note"' in page.read_text(encoding="utf-8")
    except OSError:
        return True


#: The key prefixes a desk page says its words under (targum-internal#184).
def best_language(header: str) -> str:
    """The language an `Accept-Language` header prefers among those with a catalogue:
    by weight, then by order, and English where none of them has one."""
    from .strings import SOURCE, languages

    have = set(languages())
    asked: list[tuple[float, int, str]] = []
    for n, part in enumerate(header.split(",")):
        name, _, rest = part.strip().partition(";")
        weight = 1.0
        for setting in rest.split(";"):
            key, _, value = setting.strip().partition("=")
            if key == "q":
                try:
                    weight = float(value)
                except ValueError:
                    weight = 0.0
        code = name.strip().split("-")[0].lower()
        if code and weight > 0:
            asked.append((-weight, n, code))
    for _, _, code in sorted(asked):
        if code in have:
            return code
    return SOURCE


DESK_KEYS = (
    "nav.",
    "progress.",
    "learn.",
    "library.",
    "you.",
    "add.",
    "charts.",
    "lang.",
    "building.",
    "account.",
    "shelf.",
    "follow.",
    "bring.",
    "yours.",
    "lists.",
    "vocab.",
    "claim.",
    "palette.",
    "chat.",
    "speak.",
)


def desk_languages() -> list[str]:
    """The languages besides English with a catalogue that says something on a desk page."""
    from .strings import catalogue, languages

    return [
        code
        for code in languages()
        if code != "en" and any(key.startswith(DESK_KEYS) for key in catalogue(code))
    ]


def default_store() -> Path:
    """Where a word list lives, which is deliberately not where the readers live.

    Readers are rebuildable and take up room, so `targum-out` is a directory somebody
    will reasonably delete one day. A vocabulary is the one thing here that cannot be
    rebuilt from anything, so it sits outside, in the home directory, and survives.
    """
    return Path.home() / ".targum" / "targum.db"


def start(
    out: Path,
    port: int = 8420,
    open_browser: bool = True,
    max_cost: float = MAX_COST,
    budget: float = SESSION_BUDGET,
    store: Path | None = None,
    mailer: Mailer | None = None,
    announce: Callable[[str], None] | None = None,
    require_account: bool = False,
    public_address: str = "",
) -> str:
    """Run until interrupted. Returns the address it is listening on."""
    from .chat.session import Chats
    from .mail import from_environment
    from .render.builder import (
        LISTS,
        add_page,
        chat_page,
        learn_page,
        library_page,
        list_page,
        progress_page,
        you_page,
    )
    from .translate.anthropic_provider import AnthropicProvider

    # The start-up key is a single-user mechanism: it proves you can read the terminal
    # this process was started from, which is the same as proving you are the person
    # sitting at the machine. Hosted there is no terminal and no such person, accounts
    # are what identify anybody, and a key in the address would only be a bearer token
    # riding in every URL — through browser history, over a shared screen, and out in a
    # Referer. So hosted has no key at all, and `_authorised()` falls to the session.
    token = "" if require_account else secrets.token_urlsafe(12)
    usable, _ = AnthropicProvider().available()
    keeping = Store(store or default_store())
    keeping.sweep()
    # The store comes first: the library reads back what the last run was doing, so a
    # build caught mid-flight stops claiming to be working and keeps its claim on the
    # budget rather than handing it back for money it had probably already spent.
    delivering = mailer or from_environment()
    public = (public_address or f"http://127.0.0.1:{port}").rstrip("/")
    library = Library(
        out,
        max_cost=max_cost,
        budget=budget,
        store=keeping,
        mailer=delivering,
        # Only where an email could reach anybody: a link with a key in it would be a
        # bearer token in a mailbox, so on a machine somebody runs themselves the
        # library is told no address and says nothing.
        address=public if require_account else "",
        # The chat's daily rail is a hosted account's (2026-09-06): on a machine
        # somebody runs themselves the reader is the operator, who set `--budget` at
        # the prompt and is the ceiling. An evening of testing hit a dollar a day and
        # was told to come back tomorrow by their own laptop.
        chat_budget=CHAT_BUDGET if require_account else None,
    )
    library.start_workers()
    # The conversation's own workers, beside the build queue and never in it.
    chats = Chats(library, keeping, usable=usable)
    chats.start_workers()

    handler = type(
        "TargumHandler",
        (Handler,),
        {
            "library": library,
            "require_account": require_account,
            "hosts": hosts_for(public_address),
            # The operator's own name, or "" where there is no public one — on a machine
            # somebody runs themselves there is no back office and no vhost in front of
            # it, so the route simply does not exist.
            "back_office": back_office_host(public_address) if require_account else "",
            "token": token,
            "store": keeping,
            "mailer": delivering,
            # Where a sign-in link points. Loopback is right for a machine somebody
            # runs themselves and useless in an email: hosted, the link has to name the
            # address the reader can actually reach, not the one the server binds to.
            "address": (public_address or f"http://127.0.0.1:{port}").rstrip("/"),
            "page": learn_page(token),
            "you": you_page(token),
            "lists": {which: list_page(token, which) for which in LISTS},
            "adding": add_page(token, no_key="" if usable else NO_KEY),
            "chatting": chat_page(token),
            "embedded": chat_page(token, embed=True),
            "chats": chats,
            "progress": progress_page(token),
            # The desk pages said in another language, rendered once each at start-up
            # like the English ones, and chosen per request (targum-internal#184).
            "translated": {
                code: {
                    "progress": progress_page(token, language=code),
                    "page": learn_page(token, language=code),
                    "you": you_page(token, language=code),
                    "adding": add_page(token, no_key="" if usable else NO_KEY, language=code),
                    "catalogue": library_page(token, language=code),
                    "chatting": chat_page(token, language=code),
                    "embedded": chat_page(token, embed=True, language=code),
                    **{f"lists:{which}": list_page(token, which, language=code) for which in LISTS},
                }
                for code in desk_languages()
            },
            "catalogue": library_page(token),
        },
    )
    try:
        server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    except OSError as error:
        if error.errno not in (errno.EADDRINUSE, errno.EACCES):
            raise
        # A traceback here reads as a crash in targum. It is almost always a second
        # copy started while the first is still running, and the fix is one flag.
        raise TargumError(
            f"Port {port} is already in use.",
            f"Another targum may already be running. Stop it, or: targum serve --port {port + 1}",
        ) from error
    # Hosted, the address a reader is given is the one in the email and the one on the
    # certificate — not a loopback address with a key on it.
    address = (
        f"{public_address.rstrip('/')}/"
        if require_account
        else f"http://127.0.0.1:{port}/?k={token}"
    )
    if announce:
        announce(address)
    if open_browser:
        threading.Timer(0.4, lambda: webbrowser.open(address)).start()
    # Followers are told by email when a series' instalment lands (2026-09-11): hosted,
    # with a mailer and an address to put in the link, and never on a laptop, where the
    # console mailer would print a letter to nobody every hour.
    if mailer is not None and public_address and require_account:
        from . import series as series_module

        def keep_telling() -> None:
            while True:
                time.sleep(ANNOUNCE_EVERY)
                try:
                    report = series_module.announce(keeping, mailer, public_address)
                    if report.sent or report.failed or report.stopped:
                        log.info("series: %s", report)
                except Exception as error:  # noqa: BLE001 - never takes the server down
                    log.warning("series: announcing failed: %s", error)

        threading.Thread(target=keep_telling, name="series-announce", daemon=True).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return address
