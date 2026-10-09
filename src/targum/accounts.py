"""Who someone is, and everything they have kept.

Until now a reader's vocabulary lived in their browser. That was right while targum was
a thing you ran on your own machine: nothing to sign into, nothing to leak, and the
words sat next to the readers they came from. It stops being right the moment someone
pays monthly for it. A word list that a cleared browser can end is not something to
charge for, it never reaches a second device, and there is no way to back it up.

So this is the other half: a per-person store, and enough identity to know whose it is.

**Identity is a link in an email, never a password.** There is nothing here to steal
that is worth a password's failure modes, and a password is one more thing for someone
who wants to read Hebrew to manage. A link is minted, hashed, mailed, and dies on first
use or after twenty minutes.

**Nothing is stored in the clear that arrives from outside.** Link and session tokens
are held as SHA-256 digests, so a copy of the database does not let anyone in. The
tokens themselves exist only in the email and the cookie.

**Merging is last-write-wins on the client's own clock.** Every record carries `seen`,
the moment the person last touched it, and a write only lands if it is newer than what
is already there. Two devices with badly skewed clocks can therefore lose an edit, which
is the accepted cost of a sync that needs no coordination and no conflict UI. What it
buys is that a phone that has been offline all week can push its week and take everyone
else's without either side having to reason about order.

**Deletes are tombstones.** Taking a word off the list sets `gone`, and the row stays.
Without that, a delete on the laptop is indistinguishable from a word the phone has not
heard of yet, and the phone puts it back on the next sync.
"""

from __future__ import annotations

import hashlib
import json
import re
import secrets
import sqlite3
import threading
import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Long enough that guessing is not a strategy, short enough to paste into a browser.
TOKEN_BYTES = 32

# A link is for the person who just asked for it, in the next few minutes. Twenty is
# long enough to switch to a mail client and back, short enough that a link sitting in
# an inbox a month later is not a way in.
LINK_MINUTES = 20

# A session lasts until it is not used. Someone who reads every few days stays signed
# in indefinitely; a browser abandoned for three months does not.
GRACE_DAYS = 7
# Asking for a link is the one thing anyone can do without an account, and every ask
# sends mail to an address the asker chose. Enough for someone who mistyped their own
# address twice and is trying again; not enough to use targum as a way to post mail
# into somebody else's inbox.
ASKS_PER_HOUR = 5
SESSION_DAYS = 90

# The connector's three lifetimes (targum-internal#80). An authorization code is spent
# within seconds by a client that already has it; a minute would be enough and ten is
# slack for a slow round trip, not for a code left lying about.
GRANT_MINUTES = 10
# An access token is short because a refresh token is the thing that lasts: a leaked
# access token stops working within the hour, and a leaked refresh token is discovered
# the next time the real client tries to use it and finds it rotated.
ACCESS_MINUTES = 60
# A refresh token does not expire on a clock. It ends when the reader disconnects the
# client, when they leave, or when it is rotated — a connector that goes unused for a
# year and then asks is the reader coming back to a machine, not an attack.
#
# Rows are swept long after they stop working rather than on expiry, so that "expired"
# and "never existed" stay tellable apart for as long as that is worth anything.
TOKEN_SWEEP_DAYS = 30

#: How many prompts one reader may keep, and how long each may be. Enough for somebody
#: who has worked out a handful of ways they like to be asked; not a place to keep an
#: essay, because what is here is said to a model on every listing.
MOST_PROMPTS = 20
PROMPT_LENGTH = 2000

#: How many playlists one reader may keep, how many texts one may hold, and how long its
#: name may be (targum-internal#364). Twenty is design.md §12's cap on a set, "A playlist
#: is swiped, and one press takes the set" (2026-09-23); the number is the build's to
#: tune, the cap is not.
MOST_PLAYLISTS = 50
MOST_IN_PLAYLIST = 20
PLAYLIST_NAME = 80

#: Who made a playlist. The reader by hand, targum's own chat, a connector on their
#: behalf, or targum's own set copied onto their account (#368).
PLAYLIST_MAKERS = ("reader", "chat", "connector", "targum")

#: How many clients may register themselves in an hour, across the whole box. Dynamic
#: registration is open by definition — a client that has never spoken to us asks for an
#: id and gets one — so there is nobody to key a limit on, and this is a ceiling on the
#: act rather than on an asker. Generous against every real burst (a directory's review,
#: a reader adding targum to three apps at once) and a floor under the one thing an open
#: endpoint invites, which is somebody filling a table for the sake of it.
#:
#: An id on its own is worth nothing: every token behind it needs a reader to have
#: pressed Approve. What this protects is the disk, not the account.
REGISTRATIONS_PER_HOUR = 60

# 2: person.leaving, for a deletion that waits out a grace period.
# 3: job.spent, what a build really cost once the API said so.
# 4: job.chapters, how a text divides — one means it is not a book.
# 5: the day table, which days somebody read on. A new table rather than a new column,
#    so it needs no entry in MIGRATIONS below: `CREATE TABLE IF NOT EXISTS` does add a
#    table that is not there yet, and it is only columns on existing tables it skips.
# 6: who a person is beyond an address — a display name and a picture. Reading
#    preferences rode along here for a day and were taken out again: a setting that
#    lives in two places is a setting that can disagree with itself. They stay in the
#    browser. A database that ran the old migration keeps two unused columns, which is
#    cheaper than another migration to drop them.
# 7: word.learned — whether a word was saved at a level below known and got there. It
#    is the difference between a word targum taught somebody and a word they already had
#    and ticked off, and it cannot be worked out after the fact from status and dates.
# 8: the meaning table — a meaning belongs to a language pair, a word to a language — and
#    the reads table, an allowlist of which languages an address may be translated into.
# 9: the chosen table, which replaces that allowlist with the person's own answer: what
#    they are learning and what they read into. The objection at 6 still stands and this
#    is not a second place for the setting — it is the one place, and the browser keeps a
#    copy of it the way it keeps a copy of the words. Old `reads` rows are read across
#    once for anybody who has signed in; the table stays on disk, empty of meaning.
# 12: job.kind, and the two chat tables. A conversation turn takes a `job` row of its
#    own kind so that it lands in the same ledger a build does — the money rails and,
#    later, the hours — rather than in a second counter beside it that would drift. The
#    chat tables are new, so `CREATE TABLE IF NOT EXISTS` is the whole migration.
#
# 15: reached.egress — which door the last knock at a host went through. A host that
#    refuses this address and answers the egress is a different fact from one that
#    refuses both, and without the column the two are one row (targum-internal#226).
#
# 16: job.cache_read, cache_write and cache_cost — what the prompt cache did on a turn of
#    conversation, so the receipt can show it (targum-internal#239).
#
# 17: the waiting table — who is at the front door (targum-internal#69). A new table, so
#    `CREATE TABLE IF NOT EXISTS` is the whole of it.
#
# 18: waiting.language — which language the front door was in when they joined, so the
#    invitation is written in the language they read rather than in English by default
#    (targum-internal#292). Empty for every row written before it existed, which reads as
#    English, and is the truth about them: the door was in English when they came through.
#
# 19: job.finished — when a build stopped, so how long one takes is a thing that can be
#    counted rather than guessed at. Nothing could say "ready in about four minutes"
#    honestly because nothing recorded how long the last thousand took
#    (targum-internal#303).
#
# 20: person.interest — what a reader said they came to read, asked once on arrival and
#    never again (targum-internal#294). It held one of four words describing a shelf.
#    Since 21 it holds a comma-separated list of subjects; the migration below carries
#    the old four across.
#
# 21: person.interest holds a list. The arrival asks in subjects a person would use
#    rather than in the registers the shelf is built from, and takes three or more
#    (targum-internal#294, 2026-09-17). A level is deliberately **not** asked here:
#    targum-internal#306 is open and undecided, and until it is answered nothing about
#    how good a reader says they are is stored.
#
# 22: the balance table — what each paid service's console said was left, typed into the
#    back office with the day it was read (2026-09-18). A new table, so `CREATE TABLE IF
#    NOT EXISTS` is the whole of it.
#
# 23: person.declared — the ulpan rung a reader said they were at, on arrival
#    (targum-internal#306, reopened and decided for on 2026-09-19). Version 21 says a
#    level is deliberately not stored; this is the decision it was waiting for. A seed,
#    read only while nothing about the reader has been measured — see `level.seed`.
#
# 24: the event table, and person.events — what a reader did in a text, appended and never
#    merged (targum-internal#127, decided 2026-09-19). See `EVENTS` below for why it is a
#    table of its own and not a seventh kind of `/sync`.
#
# 25: word.source — how a word came to be in the ledger. '' for the ordinary way, a word
#    met in a text and marked there, which is everything written before this. 'claimed'
#    for a row ticked off on "Words you may already know" (targum-internal#245), where
#    the reader is telling us about a word they never met here. The count is the same
#    either way; what differs is what the corpus may say about it, and a claim is the
#    reader's own word rather than evidence from a text.
#
# 29: the three oauth tables — client, grant, token (targum-internal#80, 2026-09-22). A
#    reader adds targum to Claude or ChatGPT by pressing Connect, which needs a token that
#    names a person rather than a cookie. All three are new tables, so `CREATE TABLE IF
#    NOT EXISTS` is the whole migration and nothing is added to MIGRATIONS below.
#
# 31: slip.source — which surface a mistake was recorded from (targum-internal#80).
#    '' for targum's own chat, which is every row written before this; 'connector' for a
#    line checked through Claude or ChatGPT. One judge writes both — `record_turn` recasts
#    on targum's own model against targum's own contract — so this is not a quality mark.
#    It is there because two surfaces is a fact worth being able to measure later, and a
#    column added afterwards could not say anything about the rows already written.
#
# 30: the prompt table — what a reader wrote for their own connector to offer
#    (targum-internal#80, note 17). A new table, so `CREATE TABLE IF NOT EXISTS` is
#    the whole of it.
#
# 31→32: the playlist and playlist_item tables — a list of texts a reader keeps, in an
#    order, to swipe through (targum-internal#364; design.md §12, 2026-09-23). New tables,
#    so `CREATE TABLE IF NOT EXISTS` is the whole of it.
#
# 32→33: playlist.next_set — the one set a finished playlist offered at its end
#    (targum-internal#367; design.md §12, 2026-09-23: the end offers more, once, and never
#    refills itself). Remembered so a second visit to the end shows the same set rather
#    than quoting another. 0 means one was looked for and none could be made.
#
# 33→34: the telegram table, and link.purpose (targum-internal#328). A chat on Telegram
#    bound to the person who opened a one-time link from /account. The table is new, so
#    `CREATE TABLE IF NOT EXISTS` is its whole migration; the column is on a table every
#    box has, so it is in MIGRATIONS, and every row written before it is a sign-in link,
#    which is what its default says.
#
# 34→35: the reading table — one row a finished section, measured against the ledger as
#    it stood that moment and never again (targum-internal#291). A new table, so `CREATE
#    TABLE IF NOT EXISTS` is the whole of it. Nothing is backfilled: the line on Your
#    Progress starts the day this lands, and the page says so.
#
# 35→36: subscriber.language — the language somebody asked for the weekly in
#    (targum-internal#288), so the digest, the confirmation and the pages they lead to are
#    in it, and so a Russian reader is sent the Russian edition. On a table every box has,
#    so it is in MIGRATIONS; empty means English, which every row before it was.
#
# 36→37: waiting.page — which of targum's own pages somebody pressed Join on
#    (targum-internal#388), now that `/aliyah` stands beside the front door and the list
#    cannot otherwise say whether it brings anybody. Empty means unknown, which every row
#    before it is. On a table every box has, so it is in MIGRATIONS.
#
# 37→38: waiting.link — the link somebody pasted into the front page's box before they
#    joined (targum-internal#399), kept with their place so it is theirs when they are
#    let in. Empty for everybody who joined without one. In MIGRATIONS for the same
#    reason as `page`.
#
# 38→39: event.word — the dictionary form a `lookup` was for (targum-internal#105, David
#    2026-09-28), so the week's sheet can list the words a reader actually looked up and
#    not only the ones they kept. On a table every box with the record has, so it is in
#    MIGRATIONS; empty for every lookup before it, and for every other kind of event.
#
# 39→40: person.ledger — a counter bumped by every write to what a reader's record says
#    that a sync does not already stamp with `revision`: a slip written or marked known,
#    the address and the rung they named, a test account wiped (2026-10-06). The two
#    together are what the connector's answers are kept under (`Store.ledger_stamp`), so
#    a change to either is a new key and nothing kept is read across it. On a table every
#    box has, so it is in MIGRATIONS.
#
# 40→41: the place table — where a reader left off in each text, one row a text, so
#    Continue picks up on any device (targum-internal#430). A new table, so `CREATE
#    TABLE IF NOT EXISTS` is the whole of it. Nothing is backfilled: until now the place
#    lived only in the browser, and the first sync from each browser carries it up.
#
# 41→42: playlist.at and playlist.visited — where in a playlist the reader is, and when
#    they were last in it (targum-internal#434). The playlist visited last, and not yet
#    gone through, is "the one you're in": its card is marked on the Playlists tab, and
#    "Play next" puts a text after the item they are on. Columns on a table every box
#    has, so they are in MIGRATIONS; NULL until the first item opened from a list.
#
# 42→43: the subscription and sub_item tables — what a reader subscribed to and what each
#    one brought (design.md §12, "A subscription is the account's", 2026-10-09). New
#    tables, so `CREATE TABLE IF NOT EXISTS` makes them; MIGRATIONS carries every `follow`
#    row across to its account, and every account's own weekly subscription, once each
#    (`INSERT OR IGNORE`, so running it again on every open changes nothing). `follow` is
#    no longer written.
#
# Not to be confused with `models.SCHEMA_VERSION`, which is a cache key: bumping that one
# invalidates every stage and forces paid re-translation of every text. This one versions
# the sqlite file behind an account and costs a column.
SCHEMA_VERSION = 43

#: What a `link` row may be spent on. A sign-in link signs somebody in and a Telegram
#: link binds a chat to an account, and neither can do the other's job: the lookups name
#: the purpose they spend (targum-internal#328).
SIGN_IN = "sign-in"
TELEGRAM = "telegram"

#: What a conversation is for. `find` is the door onto the shelf; `talk` is Hebrew.
#: `talk` since 2026-09-06, when the two modes became one: every conversation is in
#: Hebrew. `find` survives on rows written before that and means the same thing now.
MODES = ("find", "talk")

#: What a reader's correction is held under (targum-internal#164, David 2026-09-22): a
#: licence to targum rather than the public domain, whose sentence is in CONTRIBUTING.md.
#: Dated, because if that sentence ever changes, the rows written under the old one must
#: still say which one they meant.
CONTRIBUTOR_GRANT = "reader-grant-2026-09-22"

#: What makes one editor's judgement the same judgement twice (targum-internal#354): the
#: word, where, and what it went from and to. A note reworded is not a second judgement.
EDITOR_FIELDS = ("language", "target", "term", "span", "before", "after")

# Columns added to tables that already exist on somebody's disk. `CREATE TABLE IF NOT
# EXISTS` does nothing to a table that is already there, so a new column has to be added
# by hand or the first query naming it fails against every database but a brand new one
# — which is exactly what a test suite full of temporary files does not catch.
# Who may open an account. Hosted, an address has to be here first — see `may_join`.
# A table rather than an environment variable so the list survives a redeploy, gets
# backed up with everything else, and can be changed without one.
INVITED = """
CREATE TABLE IF NOT EXISTS invited (
  email TEXT PRIMARY KEY,
  at    INTEGER NOT NULL
);
"""

# Accounts for testing the product as a new reader would meet it, again and again
# (David, 2026-09-28: "a testing account that you and I can use, and whose memory is
# wiped each time it logs out"). Signing out of one wipes everything it holds — see
# `Store.wipe` — and keeps the account and its invitation, so the next sign-in is a first
# visit. Written only from the command line on the box, and only for an address that has
# no account yet or is already one of these: a real reader's account can never become
# one by a typo, because the thing that happens to it next is that it is emptied.
TEST_ACCOUNT = """
CREATE TABLE IF NOT EXISTS test_account (
  email TEXT PRIMARY KEY,
  at    INTEGER NOT NULL
);
"""

#: What a test account holds, emptied at its sign-out: every table keyed by `person`.
#: `tests/test_test_account.py` holds this against the schema, so a table added tomorrow
#: with a person column fails there until it is named here or in `WIPE_BY_HAND`.
WIPED = (
    "word",
    "meaning",
    "phrase",
    "doc",
    "day",
    "section",
    "place",
    "reading",
    "event",
    "chosen",
    "slip",
    "telegram",
    "oauth_token",
    "oauth_grant",
    "prompt",
    "session",
    "link",
)
#: Keyed by person and emptied by hand in `Store.wipe`, their children first.
WIPE_BY_HAND = ("chat", "playlist", "subscription")

#: What can be subscribed to (design.md §12, "A subscription is the account's",
#: 2026-10-09): targum's series, a news topic, one outlet, a YouTube channel, a podcast.
SUB_KINDS = ("series", "topic", "outlet", "channel", "podcast")
#: The two that get each new item ready by themselves, inside a monthly cap.
SUB_BUILDS = ("channel", "podcast")
SUB_STATES = ("on", "paused", "off")
#: The caps a reader chooses from, in credits a month, and the one chosen for them
#: (David, 2026-10-08: sixty credits, an hour).
CAPS = (30, 60, 120, 240)
DEFAULT_CAP = 60
#: A credit is a minute of audio or video (design.md §12, 2026-09-23) — the same minute
#: as `serve.SECONDS_A_CREDIT`, said here because the store counts a cap in it.
SECONDS_A_CREDIT = 60

# Who is not a reader but the person running the box. An address here is exempt from the
# per-account spend rails — see `serve.Library.claim` — because the limits exist to stop
# a reader running up somebody else's bill, and the person paying it is not that reader.
#
# An address rather than a column on `person`, for the same reason `invited` is a table:
# it has to be settable before anybody has signed in, and it has to survive `uninvite`,
# which deliberately leaves an existing account alone. Nobody's own address is written
# down here in the source — this repository is public — so the first admin is made from
# the command line on the box, the same way the first invitation is.
ADMIN = """
CREATE TABLE IF NOT EXISTS admin (
  email TEXT PRIMARY KEY,
  at    INTEGER NOT NULL
);

-- The allowlist `chosen` replaced: which languages an address had been marked as
-- reading, from the command line. Still created so the migration below has something
-- to read on a database that never had it; nothing writes here any more.
CREATE TABLE IF NOT EXISTS reads (
  email    TEXT NOT NULL,
  language TEXT NOT NULL,
  at       INTEGER NOT NULL,
  PRIMARY KEY (email, language)
);
"""

# What a person said about their languages: which they are learning, and which they read
# well enough to be handed a translation in. The reader's own answer, from the profile
# page, where the `reads` table above was somebody else's answer from a terminal.
#
# Keyed by person rather than by address, unlike `admin` and `invited`: those say
# something about an address before anybody has signed in, and a preference cannot
# exist before its owner does. One row per language per kind; the next language is a
# row. Absent means the default — see `learning` and `reads` on the store.
# What a reader did in a text (targum-internal#127): a word looked up, a stretch of a
# recording played, a page turned, a section finished, where a sitting stopped, a control
# pressed. "It is worthless retroactively", which is the whole argument for keeping it.
#
# **Appended, never merged, and never sent back.** Everything else a reader keeps goes
# through `/sync`, which is last-write-wins on a key — the reason `day.count` is a constant
# 1, because a real tally written from two browsers is destroyed by the merge. A log has no
# key to fight over: each row is a thing that happened once. And it is not pulled down
# again, because a log that synced to every browser would fill `localStorage` without
# limit; what a page needs is the totals, and `Store.totals` derives those.
#
# What is decided (David, 2026-09-19), so nobody has to work it out from the columns: on
# from a reader's first session, with a switch and an erase on the account page; kept for
# as long as the account is; an aggregate across readers only per segment, bearing no
# person, and only over texts whose licence lets them leave — never over an upload. A
# control pressed carries no document and no segment: a name, a width and a day.
#
# A look-up carries the word, as its dictionary form (David, 2026-09-28,
# targum-internal#105): the week's sheet lists the words a reader looked up, and the
# segment alone could not say which. Only a look-up carries one; the aggregate never reads it.
#
# And what is *not* decided here: the privacy notice names a legal basis for every
# category of data it lists, and this is a new category. So the whole of it stands behind
# `TARGUM_EVENTS`, off unless the deployment says otherwise — see `serve.py`.
EVENTS = """
CREATE TABLE IF NOT EXISTS event (
  id        INTEGER PRIMARY KEY,
  person    INTEGER NOT NULL,
  kind      TEXT    NOT NULL,
  day       TEXT    NOT NULL,
  at        INTEGER NOT NULL DEFAULT 0,
  language  TEXT    NOT NULL DEFAULT '',
  medium    TEXT    NOT NULL DEFAULT '',
  document  TEXT    NOT NULL DEFAULT '',
  segment   TEXT    NOT NULL DEFAULT '',
  amount    REAL    NOT NULL DEFAULT 0,
  control   TEXT    NOT NULL DEFAULT '',
  width     TEXT    NOT NULL DEFAULT '',
  word      TEXT    NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS event_person_day ON event (person, day);
CREATE INDEX IF NOT EXISTS event_segment ON event (document, segment, kind);
"""

#: What can happen, and what `amount` is for each: seconds for a stretch played, words for
#: a page or a section, a fraction of the text for where a sitting stopped, nothing else.
EVENT_KINDS = ("lookup", "play", "replay", "page", "section", "stop", "control")
#: What a text is, to whoever is at it (targum-internal#337).
EVENT_MEDIA = ("read", "listen", "watch")
EVENT_WIDTHS = ("phone", "narrow", "desk")
#: The most one request may hand over. A sitting is a few hundred events; a page that
#: sends more than this is broken or is not a page.
EVENT_BATCH = 500

CHOSEN = """
CREATE TABLE IF NOT EXISTS chosen (
  person   INTEGER NOT NULL,
  kind     TEXT    NOT NULL,
  language TEXT    NOT NULL,
  at       INTEGER NOT NULL,
  PRIMARY KEY (person, kind, language)
);
"""

MIGRATIONS: tuple[str, ...] = (
    "ALTER TABLE person ADD COLUMN leaving INTEGER",
    # Which surface a mistake came from: '' is targum's own chat and is every row
    # written before 2026-09-22; 'connector' is a line checked through Claude or ChatGPT
    # (targum-internal#80). Not a quality mark — one judge writes both.
    "ALTER TABLE slip ADD COLUMN source TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE job ADD COLUMN spent REAL NOT NULL DEFAULT 0",
    "ALTER TABLE job ADD COLUMN chapters INTEGER NOT NULL DEFAULT 1",
    "ALTER TABLE person ADD COLUMN name TEXT NOT NULL DEFAULT ''",
    # A URL, for the day a sign-in provider hands one over. Empty until then, and the
    # avatar falls back to initials — which is what it draws either way when the picture
    # will not load.
    "ALTER TABLE person ADD COLUMN picture TEXT NOT NULL DEFAULT ''",
    # How the conversation addresses them in Hebrew, where every "you" and every present
    # tense "I" has a gender (2026-09-14): 'm', 'f', or empty for "either", which the
    # conversation answers with forms that do not choose.
    "ALTER TABLE person ADD COLUMN address TEXT NOT NULL DEFAULT ''",
    # Whether a word was worked up to known from a level below it, rather than ticked off
    # as already known. Nothing can recover this for words marked before it existed, so
    # it starts at nought for everybody and counts forward.
    "ALTER TABLE word ADD COLUMN learned INTEGER NOT NULL DEFAULT 0",
    # When the reader said they had finished a text, or 0. One press at the foot of the
    # last part; pressing again takes it back, so a text is finished once however often
    # the button is pressed. Synced and exported with the rest of what they did.
    "ALTER TABLE doc ADD COLUMN done INTEGER NOT NULL DEFAULT 0",
    # Seconds a job consumed from the monthly allowance. Two things are metered by time:
    # an uploaded audio or video file, and since 2026-09-05 a turn of conversation, typed
    # or spoken (`chat/hebrew.py` says how a typed one becomes seconds). Text uploads and
    # everything in the library are zero. See `serve.UPLOAD_SECONDS`.
    "ALTER TABLE job ADD COLUMN length REAL NOT NULL DEFAULT 0",
    # What kind of work the row is. `build` is every row written before 2026-09-05; a
    # `chat` row is one turn of conversation, claimed and settled the same way so the
    # rails see it, and never queued — see `chat/session.py`.
    "ALTER TABLE job ADD COLUMN kind TEXT NOT NULL DEFAULT 'build'",
    # What a conversation is for: `find` (things to read) or `talk` (in Hebrew). The
    # reader switches it; the mode decides which contract the model is given.
    "ALTER TABLE chat ADD COLUMN mode TEXT NOT NULL DEFAULT 'find'",
    # The words of the answer to a turn, read the way a text is read (2026-09-06): JSON
    # on the reader's row, so a page that comes back to the conversation draws every
    # word with its state without reading the lines again. See `chat/record.py`.
    "ALTER TABLE chat_turn ADD COLUMN words TEXT NOT NULL DEFAULT ''",
    # What a reader said they came to read, on arrival. Empty for everybody who arrived
    # before there was a question, and for anybody who has not answered it.
    "ALTER TABLE person ADD COLUMN interest TEXT NOT NULL DEFAULT ''",
    # When a build stopped, so that how long one takes can be counted. Zero for every
    # row that predates it, which is why the reckoning below ignores zeros rather than
    # treating them as instant builds.
    "ALTER TABLE job ADD COLUMN finished INTEGER NOT NULL DEFAULT 0",
    # The language the front door was in when an address joined the waitlist, so the
    # invitation is written in it. Empty for everybody who joined before the door had a
    # second language, which is the truth about them rather than a gap.
    "ALTER TABLE waiting ADD COLUMN language TEXT NOT NULL DEFAULT ''",
    # Which door the last knock at a host went through. Everything knocked before this
    # existed was knocked from the box itself, so `direct` is the right thing for a row
    # that predates the column as well as the default for a new one.
    "ALTER TABLE reached ADD COLUMN egress TEXT NOT NULL DEFAULT 'direct'",
    # When the person last opened a conversation (2026-09-11): `seen` moves with every
    # turn, the answer's included, so it cannot say whether an answer arrived while they
    # were away. This can.
    "ALTER TABLE chat ADD COLUMN opened INTEGER NOT NULL DEFAULT 0",
    # What the prompt cache did on a job, and what that part came to (2026-09-15,
    # targum-internal#239): tokens read back, tokens written, and their dollars. Already
    # inside `spent`; kept apart so the receipt can say whether caching saved anything.
    "ALTER TABLE job ADD COLUMN cache_read INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE job ADD COLUMN cache_write INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE job ADD COLUMN cache_cost REAL NOT NULL DEFAULT 0",
    # `interest` held one word describing a shelf and now holds a list of subjects. The
    # two that have a subject keep it; `video` was a format rather than a subject and
    # nothing it meant survives translation, so it goes back to unanswered and the
    # reader is asked again. Idempotent: after the first run no row holds the old words.
    # When the reader said they know a line they once got wrong (2026-09-18), or 0. It
    # takes the line out of What to work on and nothing else: the slip is still the
    # record, still exported and still read by the conversation's recurring rules.
    "ALTER TABLE slip ADD COLUMN known INTEGER NOT NULL DEFAULT 0",
    "UPDATE person SET interest = 'everyday' WHERE interest = 'spoken'",
    "UPDATE person SET interest = 'judaism' WHERE interest = 'portion'",
    "UPDATE person SET interest = '' WHERE interest = 'video'",
    # The rung a reader named on arrival. Empty for everybody who was never asked, who
    # skipped the question, or who arrived while it was not being asked.
    "ALTER TABLE person ADD COLUMN declared TEXT NOT NULL DEFAULT ''",
    # Whether this reader has stopped the record of what they do in a text: '' for kept,
    # 'off' for stopped (targum-internal#127). On from the first session, by decision; the
    # switch is theirs, on the account page.
    "ALTER TABLE person ADD COLUMN events TEXT NOT NULL DEFAULT ''",
    # How a word came to be in the ledger: '' for one met in a text and marked there,
    # 'claimed' for one ticked off on "Words you may already know". Nothing can recover
    # this for words marked before it existed, and '' is the honest answer for them —
    # they were met in a text, because that was the only door there was.
    "ALTER TABLE word ADD COLUMN source TEXT NOT NULL DEFAULT ''",
    # Which judge made this correction, as a pseudonym (targum-internal#164, David
    # 2026-09-22). `who` is a role and stays one; this is what tells two readers agreeing
    # from one reader twice, which is most of the gold set. Empty on every row written
    # before, and on the author's own hand, which has no account behind it.
    "ALTER TABLE correction ADD COLUMN judge TEXT NOT NULL DEFAULT ''",
    # Where a correction stands (targum-internal#164, door 3). '' for a judgement that
    # simply happened — a grounding, the author's own hand — and 'proposed', 'accepted'
    # or 'rejected' for a reader's suggestion and what became of it. A reader's
    # correction is a proposal until somebody with standing accepts it: this card's own
    # words, "not a vote".
    "ALTER TABLE correction ADD COLUMN state TEXT NOT NULL DEFAULT ''",
    # When this reader accepted the contribution grant, or 0. It gates the control
    # rather than the recording: no grant, no way to offer a correction at all.
    "ALTER TABLE person ADD COLUMN granted INTEGER NOT NULL DEFAULT 0",
    # The language the reader was following in (targum-internal#289), the way
    # `waiting.language` records the door they came through. A follower is keyed by
    # address and needs no account, so there is nowhere else to read it from at send
    # time — and the mail and the page it leads to were English for everybody, beside a
    # library the same reader had in Russian. Empty means English, which is what every
    # row written before this held in fact.
    "ALTER TABLE follow ADD COLUMN language TEXT NOT NULL DEFAULT ''",
    # The set a finished playlist offered at its end (targum-internal#367): NULL until
    # the end is reached, then the playlist it quoted, or 0 when none could be made. A
    # column on a table that exists on the box since #364, so it is added here.
    "ALTER TABLE playlist ADD COLUMN next_set INTEGER",
    # What a link is for (targum-internal#328): 'sign-in', which every row written before
    # this was, or 'telegram', which binds a chat and signs nobody in.
    "ALTER TABLE link ADD COLUMN purpose TEXT NOT NULL DEFAULT 'sign-in'",
    # The language somebody asked for the weekly in (targum-internal#288), the way
    # `follow.language` is a series'. The weekly went out in English to everybody, and
    # since 2026-09-27 there is a Russian edition every issue to send instead. Empty
    # means English, which is what every row written before this was sent.
    "ALTER TABLE subscriber ADD COLUMN language TEXT NOT NULL DEFAULT ''",
    # Which of targum's pages somebody joined the waitlist from (targum-internal#388).
    # Empty is unknown, and the truth about every row written before it.
    "ALTER TABLE waiting ADD COLUMN page TEXT NOT NULL DEFAULT ''",
    # The link somebody tried on the front page and joined with (targum-internal#399).
    "ALTER TABLE waiting ADD COLUMN link TEXT NOT NULL DEFAULT ''",
    # The dictionary form a look-up was for (targum-internal#105, 2026-09-28): the lemma
    # the ledger keys a word on, so a week's look-ups meet the reader's own words and
    # meanings. Empty on every lookup recorded before it and on every other kind.
    "ALTER TABLE event ADD COLUMN word TEXT NOT NULL DEFAULT ''",
    # Bumped by every write to the record that `revision` does not stamp (2026-10-06):
    # see `Store.ledger_stamp`. Zero for everybody until their first such write, which
    # is a key like any other.
    "ALTER TABLE person ADD COLUMN ledger INTEGER NOT NULL DEFAULT 0",
    # Where in a playlist the reader is and when they were last in it (#434): the one
    # visited last is the one they are in, until they have gone through it.
    "ALTER TABLE playlist ADD COLUMN at INTEGER",
    "ALTER TABLE playlist ADD COLUMN visited INTEGER",
    # Every follow, carried to its account (schema 43, design.md §12, 2026-10-09) with
    # its stop token, so a link in a mail already sent still stops it, and with what it
    # last sent, so nothing is mailed twice. A follow whose address has no account has
    # nowhere to go and stays where it was. `OR IGNORE`: a row already carried, or made
    # since, is never overwritten — this runs on every open, like everything here.
    "INSERT OR IGNORE INTO subscription"
    " (person, kind, key, language, state, stop, since, ended, sent, instalment, said)"
    " SELECT person.id, 'series', follow.series, 'he', follow.state, follow.stop,"
    " follow.since, follow.ended, follow.sent, follow.instalment, follow.language"
    " FROM follow JOIN person ON person.email = follow.email",
    # And each account's own weekly, which lived only in `subscriber`. Its mail stays
    # there — the Monday mailout reads `subscriber`, and its anonymous subscribers are
    # left exactly as they are — and this row is what the Subscriptions tab shows.
    "INSERT OR IGNORE INTO subscription"
    " (person, kind, key, language, state, stop, since, said)"
    " SELECT person.id, 'series', 'weekly', 'he', 'on', lower(hex(randomblob(16))),"
    " MAX(subscriber.joined, subscriber.asked), subscriber.language"
    " FROM subscriber JOIN person ON person.email = subscriber.email"
    " WHERE subscriber.state = 'on'",
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS person (
  id         INTEGER PRIMARY KEY,
  email      TEXT    NOT NULL UNIQUE,
  made       INTEGER NOT NULL,
  revision   INTEGER NOT NULL DEFAULT 0,
  -- What to call them and what to show, neither of which an email can answer. Both
  -- empty until somebody says otherwise; the avatar draws initials in the meantime.
  name       TEXT    NOT NULL DEFAULT '',
  picture    TEXT    NOT NULL DEFAULT '',
  -- When they asked to be forgotten. Everything goes at the end of the grace period;
  -- until then they are signed out and the account is unusable, so the only thing the
  -- delay buys is the chance to undo a mistake.
  leaving  INTEGER,
  -- When they accepted the contribution grant (targum-internal#164, door 3), or 0.
  -- CONTRIBUTING.md holds the sentence; this holds that they read it.
  granted  INTEGER NOT NULL DEFAULT 0
);

-- How often an address has asked for a link. A sign-in endpoint that anyone can call
-- is a way to send mail from someone else's domain to someone else's inbox.
CREATE TABLE IF NOT EXISTS asked (
  who   TEXT    NOT NULL,
  made  INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS asked_when ON asked (who, made);

CREATE TABLE IF NOT EXISTS link (
  hash    TEXT    PRIMARY KEY,
  person  INTEGER NOT NULL REFERENCES person(id),
  made    INTEGER NOT NULL,
  used    INTEGER,
  purpose TEXT    NOT NULL DEFAULT 'sign-in'
);

-- A Telegram chat, bound to the person who opened a one-time link from /account
-- (targum-internal#328). One chat is one person; a person may bind more than one, a
-- phone and a desktop. Only the binding: no message is kept, and what a chat sends
-- becomes an ordinary job and an ordinary private import. `/stop` in the chat, or the
-- row on /account, deletes it, and the chat is a stranger again.
CREATE TABLE IF NOT EXISTS telegram (
  chat_id INTEGER PRIMARY KEY,
  person  INTEGER NOT NULL REFERENCES person(id),
  linked  INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS telegram_person ON telegram (person);

CREATE TABLE IF NOT EXISTS session (
  hash   TEXT    PRIMARY KEY,
  person INTEGER NOT NULL REFERENCES person(id),
  made   INTEGER NOT NULL,
  seen   INTEGER NOT NULL
);

-- A word is one row per person per language per dictionary form. The client keys its
-- own store exactly this way, so nothing has to be reshaped in either direction.
CREATE TABLE IF NOT EXISTS word (
  person   INTEGER NOT NULL,
  language TEXT    NOT NULL,
  lemma    TEXT    NOT NULL,
  surface  TEXT    NOT NULL DEFAULT '',
  status   INTEGER,
  meaning  TEXT    NOT NULL DEFAULT '',
  note     TEXT    NOT NULL DEFAULT '',
  band     TEXT    NOT NULL DEFAULT '',
  learned  INTEGER NOT NULL DEFAULT 0,
  -- How the word got here: '' for one met in a text, 'claimed' for one ticked off on
  -- "Words you may already know" (targum-internal#245).
  source   TEXT    NOT NULL DEFAULT '',
  at       INTEGER NOT NULL DEFAULT 0,
  seen     INTEGER NOT NULL DEFAULT 0,
  gone     INTEGER NOT NULL DEFAULT 0,
  revision INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (person, language, lemma)
);

-- A phrase belongs to the sentence it was cut from, so it carries the document and
-- segment it came from and the span within that segment. `id` is minted by whichever
-- browser first kept it: position in a list is not a name, because deleting the first
-- phrase renames every phrase after it.
CREATE TABLE IF NOT EXISTS phrase (
  person     INTEGER NOT NULL,
  id         TEXT    NOT NULL,
  document   TEXT    NOT NULL DEFAULT '',
  segment    TEXT    NOT NULL DEFAULT '',
  span_start INTEGER NOT NULL DEFAULT 0,
  span_end   INTEGER NOT NULL DEFAULT 0,
  text       TEXT    NOT NULL DEFAULT '',
  status     INTEGER,
  note       TEXT    NOT NULL DEFAULT '',
  meaning    TEXT    NOT NULL DEFAULT '',
  at         INTEGER NOT NULL DEFAULT 0,
  seen       INTEGER NOT NULL DEFAULT 0,
  gone       INTEGER NOT NULL DEFAULT 0,
  revision   INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (person, id)
);

-- Which texts someone has open, and when they last looked at one. The library sorts by
-- it, and the words page uses it to tell which language a phrase belongs to.
CREATE TABLE IF NOT EXISTS doc (
  person   INTEGER NOT NULL,
  hash     TEXT    NOT NULL,
  title    TEXT    NOT NULL DEFAULT '',
  language TEXT    NOT NULL DEFAULT '',
  updated  INTEGER NOT NULL DEFAULT 0,
  opened   INTEGER NOT NULL DEFAULT 0,
  done     INTEGER NOT NULL DEFAULT 0,
  seen     INTEGER NOT NULL DEFAULT 0,
  gone     INTEGER NOT NULL DEFAULT 0,
  revision INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (person, hash)
);

-- What a word or a phrase means, to somebody reading one language in another.
--
-- A word belongs to a language; a meaning belongs to a language pair. `word.meaning` was
-- one slot for a fact that has an answer per language, and the merge below is
-- last-write-wins on a whole row — so a reader with an English text and a Russian one had
-- two devices overwriting each other's meanings under a rule that could not tell them
-- apart. Splitting the meaning off leaves the word, its level and every count that reads
-- them exactly where they were: a Hebrew word known is a Hebrew word, whichever language
-- it was learned through.
--
-- `term` is a dictionary form, or `phrase:<id>` for what a kept phrase reads as. One
-- table rather than two: it is the same fact about the same pair, and a second table for
-- a handful of rows is furniture. `note` is here beside `meaning` because a note is a
-- meaning the reader wrote themselves, and one written in Russian is no more use on an
-- English page than a Russian gloss would be.
CREATE TABLE IF NOT EXISTS meaning (
  person   INTEGER NOT NULL,
  source   TEXT    NOT NULL,
  target   TEXT    NOT NULL,
  term     TEXT    NOT NULL,
  meaning  TEXT    NOT NULL DEFAULT '',
  note     TEXT    NOT NULL DEFAULT '',
  at       INTEGER NOT NULL DEFAULT 0,
  seen     INTEGER NOT NULL DEFAULT 0,
  gone     INTEGER NOT NULL DEFAULT 0,
  revision INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (person, source, target, term)
);

-- The days somebody read on. One row per calendar day, and the day is the reader's own
-- local one rather than UTC, because "did I read yesterday" is a question about the
-- reader's evening and not about Greenwich.
--
-- `count` is always 1. It is presence, not a tally: `_merge` below is last-write-wins on
-- `seen`, so a real per-day count would be lost the moment two devices both read on the
-- same day and the second one pushed a smaller number. A constant makes the merge
-- harmless, and how many times you opened a text on a Tuesday is not something anything
-- asks. `gone` is carried because the generic sync code selects it; nothing ever sets
-- it, because a day that happened cannot un-happen.
CREATE TABLE IF NOT EXISTS day (
  person   INTEGER NOT NULL,
  day      TEXT    NOT NULL,
  count    INTEGER NOT NULL DEFAULT 0,
  seen     INTEGER NOT NULL DEFAULT 0,
  gone     INTEGER NOT NULL DEFAULT 0,
  revision INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (person, day)
);

-- One row per part of a text the reader has finished. A targum finishes at the end of a
-- chapter rather than at the end of a book (targum-internal#173): Genesis is one
-- document, so `doc.done` is one timestamp fifty chapters in, and a reader who read
-- three chapters had finished nothing.
--
-- A row rather than a column on `doc` holding a map of them, and that is the whole
-- design. The merge in `_merge` keeps whichever version of a *record* is newer, so a
-- map of chapters pushed from a phone that had not heard about the laptop's would
-- replace the laptop's wholesale and take a morning's reading with it. Chapters merge
-- like saved words merge: one row each, independently, and a chapter un-finished
-- travels as a `gone` row the way a dropped word does.
CREATE TABLE IF NOT EXISTS section (
  person   INTEGER NOT NULL,
  hash     TEXT    NOT NULL,
  section  TEXT    NOT NULL,
  at       INTEGER NOT NULL DEFAULT 0,
  seen     INTEGER NOT NULL DEFAULT 0,
  gone     INTEGER NOT NULL DEFAULT 0,
  revision INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (person, hash, section)
);

-- Where a reader left off in a text, one row a text (targum-internal#430): which part of
-- it, which sentence, and how far into its recording. Continue reads it, on whichever
-- device the reader picks the text up on next.
--
-- One row a text rather than a row a part, because the question it answers is "where
-- was I", and that has one answer per text: a reader who went back to chapter two to
-- look something up has their place in chapter two. Last write wins on `seen`, like
-- every other kind, so the device read on most recently is the one that says. `path` is
-- the page's own address on this box, for a row that has to link without the contents
-- page in hand; `seconds` is 0 for a text with no recording or one not started.
CREATE TABLE IF NOT EXISTS place (
  person   INTEGER NOT NULL,
  hash     TEXT    NOT NULL,
  section  TEXT    NOT NULL DEFAULT '',
  path     TEXT    NOT NULL DEFAULT '',
  segment  TEXT    NOT NULL DEFAULT '',
  seconds  REAL    NOT NULL DEFAULT 0,
  at       INTEGER NOT NULL DEFAULT 0,
  seen     INTEGER NOT NULL DEFAULT 0,
  gone     INTEGER NOT NULL DEFAULT 0,
  revision INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (person, hash)
);

-- What a reader knew of a section, the moment they finished it (targum-internal#291):
-- its running words, names and numbers left out, and how many of them their ledger held
-- as known right then. Written once, when the section's row first arrives on a push, and
-- never recomputed — a row is a fact about a day, and the line on Your Progress is only
-- honest because the words marked since cannot reach back into it. Not a sync kind: the
-- browser never writes it, and a section finished again finds its row already here.
CREATE TABLE IF NOT EXISTS reading (
  person   INTEGER NOT NULL,
  language TEXT    NOT NULL,
  at       INTEGER NOT NULL,
  hash     TEXT    NOT NULL,
  section  TEXT    NOT NULL,
  tokens   INTEGER NOT NULL,
  known    INTEGER NOT NULL,
  PRIMARY KEY (person, hash, section)
);

-- The work queue. Builds used to live in a dictionary on the server and money spent
-- in a float beside it, so a restart lost every running build and handed the budget
-- back to whoever asked next. Both belong on disk, and `claimed` is the whole spend
-- accounting: what is still committed is the sum of it, so there is no second counter
-- to drift away from the truth.
CREATE TABLE IF NOT EXISTS job (
  id       TEXT    PRIMARY KEY,
  owner    INTEGER,
  home     TEXT    NOT NULL,
  source   TEXT    NOT NULL,
  options  TEXT    NOT NULL DEFAULT '{}',
  stage    TEXT    NOT NULL DEFAULT 'reading',
  title    TEXT    NOT NULL DEFAULT '',
  language TEXT    NOT NULL DEFAULT '',
  segments INTEGER NOT NULL DEFAULT 0,
  chapters INTEGER NOT NULL DEFAULT 1,
  estimate REAL    NOT NULL DEFAULT 0,
  done     INTEGER NOT NULL DEFAULT 0,
  total    INTEGER NOT NULL DEFAULT 0,
  message  TEXT    NOT NULL DEFAULT '',
  error    TEXT    NOT NULL DEFAULT '',
  reader   TEXT    NOT NULL DEFAULT '',
  lemmas   INTEGER NOT NULL DEFAULT 0,
  meanings REAL    NOT NULL DEFAULT 0,
  blocked  TEXT    NOT NULL DEFAULT '',
  claimed  REAL    NOT NULL DEFAULT 0,
  spent    REAL    NOT NULL DEFAULT 0,
  length   REAL    NOT NULL DEFAULT 0,
  made     INTEGER NOT NULL DEFAULT 0,
  kind     TEXT    NOT NULL DEFAULT 'build',
  cache_read  INTEGER NOT NULL DEFAULT 0,
  cache_write INTEGER NOT NULL DEFAULT 0,
  cache_cost  REAL    NOT NULL DEFAULT 0,
  -- When it stopped, however it stopped. Zero while it is still running, and zero for
  -- every row written before this column existed.
  finished    INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS word_since   ON word   (person, revision);
CREATE INDEX IF NOT EXISTS phrase_since ON phrase (person, revision);
CREATE INDEX IF NOT EXISTS meaning_since ON meaning (person, revision);
CREATE INDEX IF NOT EXISTS job_claimed  ON job    (claimed);
CREATE INDEX IF NOT EXISTS doc_since    ON doc    (person, revision);
CREATE INDEX IF NOT EXISTS day_since    ON day    (person, revision);
CREATE INDEX IF NOT EXISTS link_person  ON link   (person);
CREATE INDEX IF NOT EXISTS session_seen ON session(seen);

-- Who asked for the weekly issue. Deliberately not a person: a subscriber has no
-- account, no words and no library, and nothing here may turn into one. The two are
-- joined by an address and by nothing else, which is the point — unsubscribing must not
-- touch an account, and closing an account must not leave targum still mailing them.
--
-- Schema 10 adds this. It is a new table, so `CREATE TABLE IF NOT EXISTS` is the whole
-- of it and MIGRATIONS gets nothing: that list is for columns on tables already sitting
-- on somebody's disk.
CREATE TABLE IF NOT EXISTS subscriber (
  email   TEXT    PRIMARY KEY,
  -- pending until the address is confirmed, on once it is, off once they stop. A row
  -- is never deleted: "they asked to stop" and "they were never here" are different
  -- facts, and only one of them means it is safe to mail again.
  state   TEXT    NOT NULL DEFAULT 'pending',
  -- Hashed, like a sign-in link, because it grants "yes, mail this address".
  confirm TEXT,
  -- In the clear, and deliberately asymmetric with the line above. Its only power is to
  -- stop mail to its own address, and hashing it would make it unmintable at send time —
  -- every issue carries an unsubscribe link, so the token has to be readable to be put
  -- in one. The worst it allows somebody who can read this table is unsubscribing an
  -- address they can already see, which is strictly less than they can already do.
  stop    TEXT    NOT NULL,
  asked   INTEGER NOT NULL,
  joined  INTEGER NOT NULL DEFAULT 0,
  ended   INTEGER NOT NULL DEFAULT 0,
  -- When the last issue went, and which one it was. Together these are what make a
  -- resumed mailout skip whoever already has it: a run that re-sends the whole list is
  -- the failure that costs a sending domain its reputation.
  sent    INTEGER NOT NULL DEFAULT 0,
  issue   TEXT    NOT NULL DEFAULT '',
  bounces INTEGER NOT NULL DEFAULT 0,
  -- The language they asked in, and so the one they are written to and sent the
  -- edition in (targum-internal#288). Empty means English.
  language TEXT   NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS subscriber_state ON subscriber (state);

-- Who follows which series (2026-09-11): the weekly portion, a learning cycle — anything
-- that comes out on its own clock and is not the weekly, which has `subscriber` above.
-- Keyed by address for the same reason: stopping must not touch an account. A row is
-- never deleted; `state` says whether it is on. `instalment` is the last one mailed, so
-- an announcement that runs twice mails nobody the second time.
CREATE TABLE IF NOT EXISTS follow (
  email      TEXT    NOT NULL,
  series     TEXT    NOT NULL,
  state      TEXT    NOT NULL DEFAULT 'on',
  stop       TEXT    NOT NULL,
  since      INTEGER NOT NULL,
  ended      INTEGER NOT NULL DEFAULT 0,
  sent       INTEGER NOT NULL DEFAULT 0,
  instalment TEXT    NOT NULL DEFAULT '',
  -- The language they were following in, as `waiting.language` is the door they came
  -- through. Empty means English. There is no account behind a follow, so this is the
  -- only place the mail and the stop page can learn which language to be in.
  language   TEXT    NOT NULL DEFAULT '',
  PRIMARY KEY (email, series)
);

-- A conversation, and its turns. Server-side, unlike a reader's words, which the
-- browser keeps and the account mirrors: the same conversation has to be resumable
-- from another client altogether, and a chat is not a reader. `person` is NULL on a
-- machine somebody runs themselves with nobody signed in, the way `job.owner` is.
CREATE TABLE IF NOT EXISTS chat (
  id       TEXT    PRIMARY KEY,
  person   INTEGER,
  title    TEXT    NOT NULL DEFAULT '',
  language TEXT    NOT NULL DEFAULT 'he',
  made     INTEGER NOT NULL DEFAULT 0,
  seen     INTEGER NOT NULL DEFAULT 0,
  spent    REAL    NOT NULL DEFAULT 0,
  saved    TEXT    NOT NULL DEFAULT '',
  gone     INTEGER NOT NULL DEFAULT 0,
  mode     TEXT    NOT NULL DEFAULT 'find'
);
-- One row per API message, in order: the reader's line, the model's answer, and the
-- tool calls and results between them. `content` is the content-block array verbatim,
-- because tool-use blocks have to be replayed exactly; `said` is the text a page shows,
-- empty on a row that is only tool traffic. `stage` and `error` live on the reader's
-- own row and say what became of the answer to it.
CREATE TABLE IF NOT EXISTS chat_turn (
  chat     TEXT    NOT NULL,
  n        INTEGER NOT NULL,
  role     TEXT    NOT NULL,
  content  TEXT    NOT NULL,
  said     TEXT    NOT NULL DEFAULT '',
  stage    TEXT    NOT NULL DEFAULT 'done',
  error    TEXT    NOT NULL DEFAULT '',
  spent    REAL    NOT NULL DEFAULT 0,
  made     INTEGER NOT NULL DEFAULT 0,
  words    TEXT    NOT NULL DEFAULT '',
  PRIMARY KEY (chat, n)
);
CREATE INDEX IF NOT EXISTS chat_person ON chat (person, seen);

-- A reader's build proposed for the shelf, and what became of it. Written by
-- `promote.candidate` after a build finishes; decided in the back office, or by the
-- machine where the licence is certain by construction. See `promote.py`.
CREATE TABLE IF NOT EXISTS proposed (
  id           TEXT    PRIMARY KEY,
  job          TEXT    NOT NULL DEFAULT '',
  owner        INTEGER,
  home         TEXT    NOT NULL DEFAULT '',
  folder       TEXT    NOT NULL DEFAULT '',
  source       TEXT    NOT NULL DEFAULT '',
  title        TEXT    NOT NULL DEFAULT '',
  author       TEXT    NOT NULL DEFAULT '',
  language     TEXT    NOT NULL DEFAULT '',
  words        INTEGER NOT NULL DEFAULT 0,
  difficulty   INTEGER NOT NULL DEFAULT 0,
  register     TEXT    NOT NULL DEFAULT '',
  kind         TEXT    NOT NULL DEFAULT '',
  licence      TEXT    NOT NULL DEFAULT '',
  standing     TEXT    NOT NULL DEFAULT '',
  catalogue_ok INTEGER NOT NULL DEFAULT 0,
  corpus_ok    INTEGER NOT NULL DEFAULT 0,
  because      TEXT    NOT NULL DEFAULT '',
  state        TEXT    NOT NULL DEFAULT 'proposed',
  by           TEXT    NOT NULL DEFAULT '',
  made         INTEGER NOT NULL DEFAULT 0
);
-- What readers asked for that the shelf could not answer: a query with no library
-- match, a link somebody had described. Counts, so the operator can see that eleven
-- readers wanted a text one licence email away. No reader is named on a row.
CREATE TABLE IF NOT EXISTS wanted (
  query    TEXT    NOT NULL DEFAULT '',
  source   TEXT    NOT NULL DEFAULT '',
  standing TEXT    NOT NULL DEFAULT '',
  count    INTEGER NOT NULL DEFAULT 0,
  first    INTEGER NOT NULL DEFAULT 0,
  last     INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (query, source)
);

-- What the fetch door found when it knocked. A property of this box's network and not
-- of any reader, so no row names one: an Israeli publisher that refuses an address
-- outside Israel refuses it for everybody here. Written by `describe_source` on the way
-- past, read back so the model is not left offering readers doors that will not open.
-- Deliberately not seeded from `chat/sources.py:UNREACHABLE`, which was measured from a
-- laptop: a box in another country is a different caller and has to knock for itself.
-- `open` is what the last knock found, so a host that comes back clears itself.
-- `egress` is which door the last knock went through: `direct`, or `proxy` where the
-- fetch was refused here and retried through the egress. `open = 1, egress = 'proxy'` is
-- a host targum can reach only because it pays to, which is worth knowing separately
-- from one that answers anybody (targum-internal#226).
CREATE TABLE IF NOT EXISTS reached (
  host   TEXT    NOT NULL PRIMARY KEY,
  open   INTEGER NOT NULL DEFAULT 0,
  why    TEXT    NOT NULL DEFAULT '',
  tries  INTEGER NOT NULL DEFAULT 0,
  first  INTEGER NOT NULL DEFAULT 0,
  last   INTEGER NOT NULL DEFAULT 0,
  egress TEXT    NOT NULL DEFAULT 'direct'
);

-- Schema 14 adds this (targum-internal#164, door 1). Every human judgement about a
-- word, kept with provenance: what stood before, what stands after, who decided, under
-- what licence the judgement is held, and the sentence they saw. Today the author's
-- hand edits on a gloss (`targum correct`) and a grounding at a reader's tap write
-- here; the editor's and the reader's doors come later. A row is a labelled example
-- and the only training data the company owns outright; nothing here is deleted by
-- applying it. `who` is author, editor, reader or model — never a name or an id.
CREATE TABLE IF NOT EXISTS correction (
  id       INTEGER PRIMARY KEY AUTOINCREMENT,
  at       INTEGER NOT NULL,
  stage    TEXT    NOT NULL,
  language TEXT    NOT NULL DEFAULT '',
  target   TEXT    NOT NULL DEFAULT '',
  term     TEXT    NOT NULL DEFAULT '',
  text     TEXT    NOT NULL DEFAULT '',
  span     TEXT    NOT NULL DEFAULT '',
  before   TEXT    NOT NULL DEFAULT '',
  after    TEXT    NOT NULL DEFAULT '',
  who      TEXT    NOT NULL,
  -- Which judge, as a pseudonym: `who` says what kind of judge and this says which one,
  -- without saying who they are (targum-internal#164). It is what tells two readers
  -- agreeing from one reader correcting twice. Empty where there is no account behind
  -- the judgement, which is the author's own hand.
  judge    TEXT    NOT NULL DEFAULT '',
  -- '', 'proposed', 'accepted' or 'rejected'. A reader's correction is a proposal until
  -- somebody with standing settles it; the author's own hand needs no state.
  state    TEXT    NOT NULL DEFAULT '',
  licence  TEXT    NOT NULL DEFAULT '',
  context  TEXT    NOT NULL DEFAULT '',
  reason   TEXT    NOT NULL DEFAULT ''
);

-- The secret a judge's pseudonym is made with (targum-internal#164). One row, minted on
-- first use and never rotated: a rotating salt would give one person a different
-- pseudonym in each window, and two windows of one reader would then read as two readers
-- agreeing — manufacturing exactly the false corroboration the pseudonym exists to
-- prevent. Anonymity here is against what leaves, not against the operator: the salt
-- never goes out with an export, and without it a pseudonym cannot be tied to a person.
CREATE TABLE IF NOT EXISTS judging (
  id   INTEGER PRIMARY KEY CHECK (id = 1),
  salt TEXT    NOT NULL
);

-- What a reader got wrong, kept (2026-09-18, targum-internal#290).
--
-- Dmitry Z, 2026-09-16, on why a scheduler does not work for him: "anki srs is kinda dumb
-- in the sense it doesnt really know what you get wrong beyond what you tell it". A
-- scheduler only knows what you type into it. targum sits in the one place where a
-- mistake is visible without anybody typing anything — the reader writes a line of Hebrew
-- in the chat and the model rewrites it — and until now that correction was shown once and
-- thrown away, which is the same bookkeeping problem moved inside the product.
--
-- One row per line the reader wrote that came back changed. A line that was already right
-- writes nothing, so this is a record of mistakes and not a log of turns.
--
-- **Not `correction`.** That table is #164: human judgements about *Hebrew*, where `who`
-- is a role and never a person, so that what it holds can be reasoned about as evidence
-- about the language. A learner's own mistakes are a fact about the learner. They stay
-- here, they are exported by `everything`, they go with the account in `forget`, they
-- never enter the corpus and they are not one of the four exportable layers —
-- `private-imports-never-train` holds without amendment.
CREATE TABLE IF NOT EXISTS slip (
  id       INTEGER PRIMARY KEY AUTOINCREMENT,
  person   INTEGER NOT NULL,
  language TEXT    NOT NULL DEFAULT 'he',
  at       INTEGER NOT NULL,
  chat     TEXT    NOT NULL DEFAULT '',
  turn     INTEGER NOT NULL DEFAULT 0,
  -- What they wrote and what came back. Both whole: a diff without its sentences is a
  -- list of words nobody can read later.
  wrote    TEXT    NOT NULL,
  recast   TEXT    NOT NULL,
  -- The tokens that changed, as JSON. The same diff #242 needs for its label.
  changed  TEXT    NOT NULL DEFAULT '[]',
  -- The model's own one-sentence reason, where it gave one: the `~ ` line.
  why      TEXT    NOT NULL DEFAULT '',
  gone     INTEGER NOT NULL DEFAULT 0,
  -- When the reader said "I know this" about it in What to work on, or 0.
  known    INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS slip_person ON slip (person, at);

-- Who is waiting for a way in (2026-09-16, targum-internal#69). The front door takes an
-- address and nothing else, and this is where it goes.
--
-- Deliberately not `subscriber`, which is the weekly, and not `follow`, which is a
-- series with instalments: this is neither, and filing it under either would make
-- "stop the weekly" and "take me off the waitlist" the same press. Deliberately not
-- `invited` either — that table says who may open an account, and being let in is a
-- second act by a person, not what joining does.
--
-- The states are the ones `subscriber` uses and mean the same things: pending until the
-- address answers its confirmation, on once it has, off once they ask to come off. A row
-- is never deleted, for the reason written there: "asked to leave" and "never came" are
-- different facts. `invited` is stamped when they are let in, so a second opening does
-- not mail the same people twice.
--
-- Schema 17 adds this, so `CREATE TABLE IF NOT EXISTS` is the whole of it.
CREATE TABLE IF NOT EXISTS waiting (
  email    TEXT    PRIMARY KEY,
  state    TEXT    NOT NULL DEFAULT 'pending',
  -- Hashed, like a sign-in link: it grants "yes, this address is mine".
  confirm  TEXT,
  -- In the clear, and for the reason `subscriber.stop` is: every mail carries the way
  -- out, so the token has to be readable at send time to be put in one.
  stop     TEXT    NOT NULL,
  asked    INTEGER NOT NULL,
  joined   INTEGER NOT NULL DEFAULT 0,
  ended    INTEGER NOT NULL DEFAULT 0,
  invited  INTEGER NOT NULL DEFAULT 0,
  -- The language the front door was in when they joined. Empty means English, which is
  -- what the door was before it had a second language to be in.
  language TEXT    NOT NULL DEFAULT '',
  -- Which of targum's own pages they pressed Join on: '/', '/aliyah', '/weekly'.
  -- Empty means unknown. Never where they were before targum (targum-internal#388).
  page     TEXT    NOT NULL DEFAULT '',
  -- The link they tried on the front page and joined with, never fetched again until
  -- they are let in. Empty when they joined without one (targum-internal#399).
  link     TEXT    NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS waiting_state ON waiting (state);

-- What each paid service's console said was left, and when somebody read it there
-- (`services.py`). Typed in from the back office, never fetched: most of the consoles
-- say it only to an admin key. Every reading is kept and the newest is the balance, so
-- a mistyped figure is corrected by typing the right one, not by editing the old.
--
-- Schema 22 adds this, so `CREATE TABLE IF NOT EXISTS` is the whole of it.
CREATE TABLE IF NOT EXISTS balance (
  service TEXT    NOT NULL,
  said    TEXT    NOT NULL,
  at      INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS balance_service ON balance (service, at);

-- The connector's three tables (targum-internal#80, 2026-09-22). targum is an
-- authorization server for exactly one resource, its own `/mcp`, so a reader can add
-- targum to Claude or ChatGPT by pressing Connect.
--
-- **Why an authorization server and not an API key.** Both connector directories require
-- the OAuth flow, and a key pasted into somebody else's client is a bearer credential
-- with no scopes and no revocation story. `serve.py` already reasons this way about the
-- start-up key: hosted has none at all, because "a key in the address would only be a
-- bearer token riding in every URL".
--
-- **Nothing here is stored in the clear**, for the reason at the top of this file: codes,
-- access tokens and refresh tokens are held as digests, exactly as `link` and `session`
-- are. What a client holds exists only in the client.
--
-- Schema 29 adds all three, so `CREATE TABLE IF NOT EXISTS` is the whole migration.

-- A client that registered itself (RFC 7591). The directories expect dynamic
-- registration, so this is written by strangers and holds nothing that is trusted: the
-- name is shown to the reader on the approval page as *the client's claim about itself*,
-- never as a fact about who it is.
CREATE TABLE IF NOT EXISTS oauth_client (
  id          TEXT PRIMARY KEY,
  name        TEXT    NOT NULL DEFAULT '',
  redirects   TEXT    NOT NULL DEFAULT '[]',
  made        INTEGER NOT NULL
);

-- An authorization code, between the reader pressing Approve and the client exchanging
-- it. Single-use and short-lived: `spent` is stamped rather than the row deleted, so a
-- replayed code is a code we can recognise as replayed instead of one we have forgotten.
-- `challenge` is the PKCE S256 challenge; there is no other kind, and a client that sends
-- no challenge is refused rather than downgraded.
CREATE TABLE IF NOT EXISTS oauth_grant (
  hash        TEXT PRIMARY KEY,
  person      INTEGER NOT NULL,
  client      TEXT    NOT NULL,
  scopes      TEXT    NOT NULL DEFAULT '',
  redirect    TEXT    NOT NULL DEFAULT '',
  challenge   TEXT    NOT NULL DEFAULT '',
  resource    TEXT    NOT NULL DEFAULT '',
  made        INTEGER NOT NULL,
  spent       INTEGER NOT NULL DEFAULT 0
);

-- An access or refresh token. One row per token, `kind` saying which, `parent` chaining a
-- refresh token to the one it replaced so a rotation is a fact and not a deletion.
--
-- `scopes` is the whole of what a token may do, and it is read from this row on every
-- request — never from anything the client sends. That is the same rule `chat/tools.py`
-- states about ownership: it comes from the context the server built, never from an
-- argument.
CREATE TABLE IF NOT EXISTS oauth_token (
  hash        TEXT PRIMARY KEY,
  person      INTEGER NOT NULL,
  client      TEXT    NOT NULL,
  kind        TEXT    NOT NULL DEFAULT 'access',
  scopes      TEXT    NOT NULL DEFAULT '',
  resource    TEXT    NOT NULL DEFAULT '',
  parent      TEXT    NOT NULL DEFAULT '',
  made        INTEGER NOT NULL,
  expires     INTEGER NOT NULL DEFAULT 0,
  seen        INTEGER NOT NULL DEFAULT 0,
  revoked     INTEGER NOT NULL DEFAULT 0
);
-- A prompt a reader wrote for themselves (targum-internal#80, notes 11 and 17).
--
-- MCP prompts appear in the host by name — in effect a slash command targum ships into
-- Claude or ChatGPT. targum's own set is fixed and lives in `mcp_http.PROMPTS`; this is
-- where a reader's own go, so what appears beside ours is theirs.
--
-- "Enable users to use targum their way" was note 17, and this is the smallest thing
-- that is actually that rather than a value: a text box, and what they write is in their
-- host next to ours the moment they save it.
--
-- `says` is what the model is told. It is the reader's own words going to a model, which
-- is a thing they do every time they use the chat, and it can only ever reach their own
-- record — `prompts/get` reads it through the same `Ctx` every tool does, so a prompt
-- naming somebody else's shelf is a prompt asking for nothing.
--
-- A tombstone rather than a delete, like every other thing a reader keeps, so that one
-- device removing a prompt does not have another put it back.
CREATE TABLE IF NOT EXISTS prompt (
  id      INTEGER PRIMARY KEY AUTOINCREMENT,
  person  INTEGER NOT NULL,
  name    TEXT    NOT NULL,
  says    TEXT    NOT NULL,
  made    INTEGER NOT NULL,
  gone    INTEGER NOT NULL DEFAULT 0
);
CREATE UNIQUE INDEX IF NOT EXISTS prompt_named ON prompt (person, name);
-- A playlist: texts a reader keeps in an order, to swipe through one after another
-- (targum-internal#364; design.md §12, "A playlist is swiped, and one press takes the
-- set", 2026-09-23). The reader's, whoever made it: `made_by` says whose hand, never whose
-- it is. A tombstone rather than a delete, like everything else a reader keeps.
CREATE TABLE IF NOT EXISTS playlist (
  id       INTEGER PRIMARY KEY AUTOINCREMENT,
  person   INTEGER NOT NULL,
  name     TEXT    NOT NULL,
  made_by  TEXT    NOT NULL DEFAULT 'reader',
  made     INTEGER NOT NULL,
  gone     INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS playlist_person ON playlist (person, gone);
-- One text in a playlist, at a position counted from 0. `reader` is the built reader's
-- folder name — what `/reader/<name>/reader/index.html` opens — once there is one; `job`
-- is the build making it until then (#365), and `failed` marks one that could not be
-- made, which the swipe passes over (#366). `title` is kept so a row can be named before
-- its text exists.
CREATE TABLE IF NOT EXISTS playlist_item (
  playlist INTEGER NOT NULL,
  position INTEGER NOT NULL,
  reader   TEXT,
  job      TEXT,
  title    TEXT    NOT NULL,
  failed   INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (playlist, position)
);
CREATE INDEX IF NOT EXISTS playlist_item_job ON playlist_item (job);

-- What a reader subscribed to (design.md §12, "A subscription is the account's",
-- 2026-10-09): one of targum's series, a news topic or outlet, a YouTube channel or a
-- podcast. On the account, where `follow` was a fact about an address. A row is never
-- deleted while the account stands: `state` is on, paused or off, because "they asked to
-- stop" and "they never subscribed" are different facts, as they are for `subscriber`.
--
-- `key` is what the kind names it by: the series' id, the topic, the outlet's key in
-- sources.json, the channel's id (UC…), the podcast's feed address. `source` is the
-- address the reader gave, where there was one. `language` is the language of what it
-- brings; `said` the one the reader reads targum in, which the mail and the stop page are
-- in. `cap` is the month's credits a channel or a podcast may build with (the second
-- press that lasts, design.md §12); 0 for everything else, which builds nothing. `stop`
-- is in the clear for the reason `subscriber.stop` is. `sent` and `instalment` are what
-- the per-series mail last sent, carried from `follow`.
CREATE TABLE IF NOT EXISTS subscription (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  person     INTEGER NOT NULL,
  kind       TEXT    NOT NULL,
  key        TEXT    NOT NULL,
  name       TEXT    NOT NULL DEFAULT '',
  language   TEXT    NOT NULL DEFAULT '',
  source     TEXT    NOT NULL DEFAULT '',
  cap        INTEGER NOT NULL DEFAULT 0,
  state      TEXT    NOT NULL DEFAULT 'on',
  stop       TEXT    NOT NULL,
  since      INTEGER NOT NULL,
  paused     INTEGER NOT NULL DEFAULT 0,
  ended      INTEGER NOT NULL DEFAULT 0,
  polled     INTEGER NOT NULL DEFAULT 0,
  sent       INTEGER NOT NULL DEFAULT 0,
  instalment TEXT    NOT NULL DEFAULT '',
  said       TEXT    NOT NULL DEFAULT '',
  UNIQUE (person, kind, key)
);
CREATE INDEX IF NOT EXISTS subscription_stop ON subscription (stop);

-- One thing a subscription brought: an instalment, an article, a video, an episode. Keyed
-- by what its source calls it, so finding it twice finds it once. `state` says what it is
-- now: `ready` (it opens, at `reader`), `listed` (a link with a press each: news, and
-- anything from before subscribing or from while paused), `due` (a channel's or a
-- podcast's, to be got ready by itself), `building` (its `job` is running), `waiting`
-- (`why` says on what: the cap, the plan, the box) or `failed`. `came` is '' for what
-- came out while subscribed, `before` for what was already out and `paused` for what came
-- out while paused: those two are never built by themselves. `seen` is when the reader
-- opened it from home, `mailed` when it went out in a mail.
CREATE TABLE IF NOT EXISTS sub_item (
  subscription INTEGER NOT NULL,
  key        TEXT    NOT NULL,
  title      TEXT    NOT NULL DEFAULT '',
  link       TEXT    NOT NULL DEFAULT '',
  reader     TEXT    NOT NULL DEFAULT '',
  published  INTEGER NOT NULL DEFAULT 0,
  found      INTEGER NOT NULL,
  seconds    REAL    NOT NULL DEFAULT 0,
  state      TEXT    NOT NULL DEFAULT 'listed',
  why        TEXT    NOT NULL DEFAULT '',
  job        TEXT    NOT NULL DEFAULT '',
  credits    INTEGER NOT NULL DEFAULT 0,
  came       TEXT    NOT NULL DEFAULT '',
  seen       INTEGER NOT NULL DEFAULT 0,
  mailed     INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (subscription, key)
);
CREATE INDEX IF NOT EXISTS sub_item_state ON sub_item (state);

CREATE INDEX IF NOT EXISTS oauth_token_person ON oauth_token (person, kind, revoked);
CREATE INDEX IF NOT EXISTS oauth_grant_person ON oauth_grant (person);
"""


#: What a reader is told about a line targum was answering when it restarted.
CHAT_RESTARTED = "We restarted while we were answering. Ask again."


def now() -> int:
    """Milliseconds, because the client's own timestamps are `Date.now()`."""
    return int(time.time() * 1000)


def _prompt_name(name: str) -> str:
    """A prompt's name, as a host will draw it: one lowercase word, hyphens for spaces.

    A host lists these as things to pick by name, and several draw them as slash
    commands — where a space is the end of the name and the start of an argument. So a
    name is narrowed here rather than shown to be wrong later in somebody else's app.
    """
    kept = re.sub(r"[^a-z0-9-]+", "-", name.strip().lower()).strip("-")
    return kept[:40]


def digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _language_code(language: str) -> str:
    """`ru-RU` as `ru`, and nothing as nothing: what a language column holds."""
    return (language or "").strip().split("-")[0].lower()


def tidy(email: str) -> str:
    """An address in the one form it is stored and compared in.

    Addresses are case-insensitive in practice whatever the RFC permits, and somebody
    signing in from their phone will capitalise the first letter. Two accounts for one
    person is a worse outcome than a rare over-merge.
    """
    return email.strip().lower()


def plausible(email: str) -> bool:
    """Enough of a check to catch a typo, and no more.

    Validating an address properly means sending to it, which is what the next step
    does anyway. This only rejects what cannot possibly be one.
    """
    address = tidy(email)
    # No address has a space in it, and one that arrives with a space is a form that
    # was decoded wrong or a paste that brought its neighbour: `+` in a posted body
    # means space, so `you+list@example.com` sent unencoded arrives broken and was
    # being stored and mailed to (found live, 2026-09-16).
    if len(address) < 3 or len(address) > 254 or address.count("@") != 1:
        return False
    if any(c.isspace() for c in address):
        return False
    local, _, host = address.partition("@")
    return bool(local) and "." in host and not host.startswith(".") and not host.endswith(".")


@dataclass(frozen=True)
class Person:
    id: int
    email: str
    #: Whether the spend rails apply to them. Resolved from the `admin` table when the
    #: person is loaded, rather than stored on the row: it is a fact about who runs the
    #: box, not about the account.
    admin: bool = False


@dataclass(frozen=True)
class Kept:
    """One word of a reader's week, with what it means to them: `Store.looked_up_between`
    and `Store.kept_between`."""

    language: str
    lemma: str
    surface: str
    #: Their own note where they wrote one, else the meaning the page gave when they kept
    #: it, else "". Either may run on past its first sense; the sheet cuts it there.
    meaning: str


def _kept(row: sqlite3.Row) -> Kept:
    return Kept(
        language=str(row["language"]),
        lemma=str(row["lemma"]),
        surface=str(row["surface"] or ""),
        # Theirs before the page's, and the meaning table's — which is per language —
        # before the word row's, which is what it held before that table was split off
        # and may be in another language.
        meaning=str(row["note"] or row["meaning"] or row["own"] or row["said"] or ""),
    )


# The four kinds of thing a person accumulates, and the columns each one syncs. Kept as
# data rather than four near-identical functions, because the merge is the same
# argument four times and the only thing that differs is the shape.
# Fields that default to a number rather than to empty text when nothing is known.
NUMERIC = frozenset(
    {"at", "updated", "opened", "done", "span_start", "span_end", "count", "seconds"}
)


def exportable_corrections(
    rows: list[dict[str, Any]], may_leave: Callable[[str], bool]
) -> list[dict[str, Any]]:
    """Corrections as they may leave targum (targum-internal#164, acceptance 5).

    > Rows about non-exportable texts appear in no export with their context; their spans
    > and judgements do.

    The judgement is a fact about *Hebrew* — this word, in this position, means that —
    and it is targum's own to give away whatever the text it was noticed in allows. The
    sentence quoted beside it is a piece of that text, and a NonCommercial or unknown
    licence reaches it. So the context is dropped and everything else stays: the term, the
    span, what stood, what stands, the stage and the judge.

    A row naming no text keeps its context. That is the author's own hand at the lexicon,
    which was never about a particular text and quotes nobody.

    `may_leave` is asked about the text rather than baked in, so the licence rule lives in
    `licensing.py` where it is already written and this function can be tested without a
    catalogue.
    """
    out: list[dict[str, Any]] = []
    for row in rows:
        text = str(row.get("text") or "")
        if not text or may_leave(text):
            out.append(dict(row))
            continue
        kept = dict(row)
        kept["context"] = ""
        # Said rather than merely missing: an empty context that means "there was none"
        # and one that means "you may not have this" are different facts about a row.
        kept["context_withheld"] = True
        out.append(kept)
    return out


def initials(name: str, email: str) -> str:
    """One or two letters for an avatar, from whatever there is to go on.

    A name gives its first letters; an address gives the first letter of the part before
    the @, and the letter after a dot or underscore where the address has one — which is
    how most people's addresses are shaped, and it turns djlangellotti into DL rather
    than into D.
    """
    words = [word for word in str(name).split() if word]
    if words:
        return "".join(word[0] for word in words[:2]).upper()
    local = str(email).split("@")[0]
    parts = [part for part in re.split(r"[._-]+", local) if part]
    if len(parts) > 1:
        return (parts[0][0] + parts[1][0]).upper()
    return local[:2].upper() if local else "?"


@dataclass(frozen=True)
class Kind:
    table: str
    key: tuple[str, ...]
    fields: tuple[str, ...]


#: The word stages that put a word on the list: being learned. Known (9) and ignored (0)
#: are not on it (`plans.LISTED` says the same for the pages).
LISTED = (1, 2, 3)

KINDS: dict[str, Kind] = {
    "words": Kind(
        table="word",
        key=("language", "lemma"),
        fields=("surface", "status", "meaning", "note", "band", "learned", "source", "at"),
    ),
    "meanings": Kind(
        table="meaning",
        key=("source", "target", "term"),
        fields=("meaning", "note", "at"),
    ),
    "phrases": Kind(
        table="phrase",
        key=("id",),
        fields=(
            "document",
            "segment",
            "span_start",
            "span_end",
            "text",
            "status",
            "note",
            "meaning",
            "at",
        ),
    ),
    "docs": Kind(
        table="doc",
        key=("hash",),
        fields=("title", "language", "updated", "opened", "done"),
    ),
    # A set, written as a table. The day string is the whole record; see the `day` table
    # above for why the count beside it is always 1.
    "days": Kind(table="day", key=("day",), fields=("count",)),
    # Which parts of a text the reader has finished. Keyed by the document and the
    # section number the build gave that part, which is the identity its filename, its
    # row on the contents page and its pager all already use.
    "sections": Kind(table="section", key=("hash", "section"), fields=("at",)),
    # Where the reader left off in each text (targum-internal#430). One row a text; the
    # browser writes it as the reader reads and pushes it at most every half minute, and
    # on the way out — see `sync.js`.
    "places": Kind(
        table="place", key=("hash",), fields=("section", "path", "segment", "seconds", "at")
    ),
}


class Store:
    """The database, and the only thing that touches it.

    One file, opened once per thread. `ThreadingHTTPServer` hands each request to
    whichever thread is free and SQLite connections are not safe to share across
    threads, so the connection is thread-local rather than guarded by a lock: a lock
    would serialise reads that have no reason to wait for each other.

    A thread that is about to end has to call `close()` itself. A thread-local does not
    release what it holds when its thread does; the cyclic collector gets to it later,
    and on a big heap later is far enough away that a request-per-thread server runs
    out of file descriptors first. The request handler does this in `finish()`.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        # Not inside `write()`: executescript issues its own COMMIT first, which ends
        # the transaction out from under whoever opened it.
        self.db.executescript(SCHEMA)
        self.db.executescript(INVITED)
        self.db.executescript(ADMIN)
        self.db.executescript(TEST_ACCOUNT)
        self.db.executescript(CHOSEN)
        self.db.executescript(EVENTS)
        self._migrate()
        self._adopt_reads()
        self.db.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    def _migrate(self) -> None:
        """Bring a database written by an older targum up to date.

        Every statement runs every time, and each is written to fail harmlessly when it
        has already been applied. The obvious alternative — skip anything at or below
        the recorded version — was here first and was a trap: a migration that is added
        but never reached still lets the version stamp advance, and the file is then
        marked as migrated while missing a column. That failure is silent until the
        first query naming the column, which is a long way from the cause.

        A few no-op ALTERs on open cost nothing and cannot get this wrong.
        """
        for statement in MIGRATIONS:
            try:
                self.db.execute(statement)
            except sqlite3.OperationalError as error:
                if "duplicate column" not in str(error).lower():
                    raise

    def _adopt_reads(self) -> None:
        """Carry the old allowlist across as the person's own choice.

        A marking on an address that has since signed in becomes that person's
        `reading` rows — with English beside it, because the allowlist always offered
        English and a Russian-only row read across on its own would take it away. An
        address nobody has signed in with is left where it is: they get the default when
        they arrive and tick Russian themselves.

        Runs on every open and does nothing the second time: the insert ignores rows
        that are already there, and a person who has since unticked a language has
        rows of their own that say so — which is why this only writes for a person
        with no `reading` rows at all.
        """
        with self.write() as db:
            marked = db.execute(
                "SELECT person.id AS id, reads.language AS language"
                " FROM reads JOIN person ON person.email = reads.email"
                " WHERE NOT EXISTS ("
                "   SELECT 1 FROM chosen WHERE chosen.person = person.id AND kind = 'reading')"
            ).fetchall()
            for row in marked:
                for code in (str(row["language"]), "en"):
                    db.execute(
                        "INSERT OR IGNORE INTO chosen (person, kind, language, at)"
                        " VALUES (?, 'reading', ?, ?)",
                        (int(row["id"]), code, now()),
                    )

    # -- plumbing ---------------------------------------------------------------

    @property
    def db(self) -> sqlite3.Connection:
        connection = getattr(self._local, "db", None)
        if connection is None:
            connection = sqlite3.connect(self.path, isolation_level=None)
            connection.row_factory = sqlite3.Row
            # Readers do not block the writer, which matters the moment two tabs sync
            # at once. Off by default, and it survives in the file, but setting it on
            # every connection costs nothing and removes a way to get this wrong.
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA busy_timeout = 5000")
            self._local.db = connection
        return connection

    class _Transaction:
        def __init__(self, db: sqlite3.Connection) -> None:
            self.db = db

        def __enter__(self) -> sqlite3.Connection:
            self.db.execute("BEGIN IMMEDIATE")
            return self.db

        def __exit__(self, kind: Any, value: Any, trace: Any) -> None:
            if kind is None:
                self.db.execute("COMMIT")
            else:
                self.db.execute("ROLLBACK")

    def write(self) -> Store._Transaction:
        """A write transaction, taken immediately rather than on first write.

        `BEGIN IMMEDIATE` up front turns a lost race into a wait; deferred, the same
        race is an error partway through, after some of the work is done.
        """
        return Store._Transaction(self.db)

    def close(self) -> None:
        connection = getattr(self._local, "db", None)
        if connection is not None:
            connection.close()
            self._local.db = None

    # -- signing in -------------------------------------------------------------

    def anyone(self) -> bool:
        """Whether anybody has an account here at all.

        The question behind it is what "signed out" means. On a machine nobody has ever
        signed up on, it means nothing — there is one person, it is theirs, and asking
        them to make an account to read their own files would be absurd. Once an account
        exists, the machine is being used as targum-with-accounts and signing out is a
        thing somebody chose to do.
        """
        return self.db.execute("SELECT 1 FROM person LIMIT 1").fetchone() is not None

    def person_by_id(self, person_id: int) -> Person | None:
        """Who a job belongs to. The thread that ran it has no session to ask."""
        row = self.db.execute("SELECT id, email FROM person WHERE id = ?", (person_id,)).fetchone()
        return Person(row["id"], row["email"], self.is_admin(row["email"])) if row else None

    def person_by_email(self, email: str) -> Person | None:
        row = self.db.execute(
            "SELECT id, email FROM person WHERE email = ?", (tidy(email),)
        ).fetchone()
        return Person(row["id"], row["email"], self.is_admin(row["email"])) if row else None

    # -- who somebody is ---------------------------------------------------

    #: Longest display name kept. Room for any real name; short enough that a corner
    #: pill and a greeting cannot be made to hold a paragraph.
    NAME_LIMIT = 60

    def profile(self, person: Person) -> dict[str, Any]:
        """Who this person is, for the corner and the profile page.

        Read separately from `Person` rather than folded into it: a Person is the answer
        to "who is asking", which every request needs, and this is the answer to "who are
        they", which two pages need.
        """
        row = self.db.execute(
            "SELECT email, name, picture, made, address, interest, declared "
            "FROM person WHERE id = ?",
            (person.id,),
        ).fetchone()
        if row is None:
            return {}
        return {
            "email": row["email"],
            "name": row["name"],
            "picture": row["picture"],
            "initials": initials(row["name"], row["email"]),
            "since": row["made"],
            "address": row["address"] or "",
            # A list since 2026-09-17, and sent as one: a page that has to split a
            # string on a comma is a page that will one day forget to.
            "interest": list(self.interests_of(str(row["interest"] or ""))),
            # Handed back so a second browser does not ask again. It is the reader's own
            # answer going back to the reader's own page; no page prints it.
            "declared": self.declared_of(str(row["declared"] or "")),
        }

    #: What a reader can say they are interested in, asked when they arrive
    #: (targum-internal#294, rewritten as subjects 2026-09-17).
    #:
    #: **Subjects, in the words somebody uses about themselves.** The first version
    #: asked in the library's own terms — "Everyday Hebrew, spoken", "The week's Torah
    #: portion", "Something to watch" — which are a register, a collection and a file
    #: format. Nobody describes themselves that way. They say they like sport, or
    #: history, or archaeology, and the shelf is the thing that should do the
    #: translating.
    #:
    #: **Longer than the shelf can answer.** Every subject is offered, including the
    #: several with nothing behind them yet, and texts are filed under them as they
    #: arrive. That drops the rule the first version held to — a door with nothing
    #: seeded behind it is left out rather than drawn and disappointing — and the rule
    #: was right for what it governed: one answer that had to route straight to a text,
    #: where an empty door was a dead end on the first press. Three answers are a
    #: profile rather than a routing decision. A profile is allowed to name something
    #: the library has not got, and that it was named is the most useful thing anybody
    #: can say about what to build next.
    #:
    #: Kept in step with `catalogue.Tag`: `targum.catalogue` files the texts and this
    #: asks the question, and `tests/test_catalogue.py` pins that neither grows a
    #: subject the other has never heard of.
    INTERESTS: tuple[str, ...] = (
        "everyday",
        "israel",
        "judaism",
        "news",
        "sport",
        "stories",
        "poetry",
        "history",
        "archaeology",
        "science",
        "technology",
        "health",
        "food",
        "travel",
        "music",
        "art",
        "politics",
        "business",
        "philosophy",
        "language",
    )

    #: The arrival offers eight of these and asks for none in particular (design.md §12,
    #: "The arrival is three plain questions", 2026-10-09); the rest stay so an answer
    #: given when all twenty were offered still reads.

    def interest(self, person_id: int | None) -> tuple[str, ...]:
        """The subjects they named, or empty where they have not answered."""
        if person_id is None:
            return ()
        row = self.db.execute(
            "SELECT interest FROM person WHERE id = ?", (int(person_id),)
        ).fetchone()
        return self.interests_of(str(row["interest"] or "")) if row is not None else ()

    @classmethod
    def interests_of(cls, stored: str) -> tuple[str, ...]:
        """The stored column read back as subjects, dropping anything retired.

        Forgiving on the way out and strict on the way in: a column written by a newer
        targum and read by an older one should lose the word it does not know rather
        than refuse the whole row.
        """
        found = [word.strip().lower() for word in str(stored or "").split(",")]
        return tuple(word for word in found if word in cls.INTERESTS)

    def set_interest(self, person: Person, interest: str | Iterable[str]) -> tuple[str, ...]:
        """Keep the subjects they named; anything not on the list is refused.

        Settable again rather than once: somebody who came for the portion and now wants
        the news should be able to say so, and a question that can only be answered once
        is a question people answer carefully instead of quickly.

        Order is the vocabulary's, not the order they pressed in, so the column reads
        the same for two readers who chose the same three.
        """
        if isinstance(interest, str):
            asked = [word.strip().lower() for word in interest.split(",")]
        else:
            asked = [str(word).strip().lower() for word in interest]
        named = {word for word in asked if word}
        unknown = named - set(self.INTERESTS)
        if unknown:
            raise ValueError("No such choice.")
        kept = tuple(word for word in self.INTERESTS if word in named)
        with self.write() as db:
            db.execute("UPDATE person SET interest = ? WHERE id = ?", (",".join(kept), person.id))
        return kept

    #: The rungs a reader can say they are on, aleph to vav: `level.ULPAN`'s, by the ids
    #: the arrival uses (targum-internal#306, 2026-09-19).
    DECLARED = (
        "aleph",
        "aleph-plus",
        "bet",
        "bet-plus",
        "gimel",
        "dalet",
        "hey",
        "vav",
    )

    def declared(self, person_id: int | None) -> str:
        """The rung they named on arrival, or "" where they named none."""
        if person_id is None:
            return ""
        row = self.db.execute(
            "SELECT declared FROM person WHERE id = ?", (int(person_id),)
        ).fetchone()
        return self.declared_of(str(row["declared"] or "")) if row is not None else ""

    @classmethod
    def declared_of(cls, stored: str) -> str:
        """The stored column read back, dropping a rung this targum does not know."""
        said = str(stored or "").strip().lower()
        return said if said in cls.DECLARED else ""

    def set_declared(self, person: Person, rung: str) -> str:
        """Keep the rung they named; "" takes it back, and anything else is refused.

        Settable again, like the subjects: it is a seed and not a record, and a reader
        who said bet and meant gimel loses nothing by saying so.
        """
        said = str(rung or "").strip().lower()
        if said and said not in self.DECLARED:
            raise ValueError("No such choice.")
        with self.write() as db:
            db.execute(
                "UPDATE person SET declared = ?, ledger = ledger + 1 WHERE id = ?",
                (said, person.id),
            )
        return said

    # -- what a reader did in a text (targum-internal#127) -------------------------

    def collects(self, person_id: int | None) -> bool:
        """Whether this reader's record is being kept: true until they stop it."""
        if person_id is None:
            return False
        row = self.db.execute(
            "SELECT events FROM person WHERE id = ?", (int(person_id),)
        ).fetchone()
        return row is not None and str(row["events"] or "") != "off"

    def set_collects(self, person: Person, on: bool) -> bool:
        with self.write() as db:
            db.execute(
                "UPDATE person SET events = ? WHERE id = ?", ("" if on else "off", person.id)
            )
        return on

    def add_events(self, person: Person, events: Iterable[dict[str, Any]]) -> int:
        """Append what happened; answer how many rows were kept.

        Strict about shape and forgiving about content: an event of a kind this targum
        does not know, or with no day, is dropped rather than refusing the batch — a page
        cached from a newer build should lose the event it invented, not the sitting. A
        reader who has stopped the record keeps nothing, whatever their page sends.
        """
        if not self.collects(person.id):
            return 0
        rows: list[tuple[Any, ...]] = []
        for raw in list(events)[:EVENT_BATCH]:
            if not isinstance(raw, dict):
                continue
            kind = str(raw.get("kind") or "")
            day = str(raw.get("day") or "")[:10]
            if kind not in EVENT_KINDS or len(day) != 10:
                continue
            try:
                amount = max(0.0, float(raw.get("amount") or 0))
                at = max(0, int(raw.get("at") or 0))
            except (TypeError, ValueError):
                continue
            medium = str(raw.get("medium") or "")
            width = str(raw.get("width") or "")
            control = kind == "control"
            rows.append(
                (
                    person.id,
                    kind,
                    day,
                    # A control pressed says which day and nothing finer.
                    0 if control else at,
                    "" if control else str(raw.get("language") or "")[:12],
                    "" if control or medium not in EVENT_MEDIA else medium,
                    # Nor which text, nor where in it: decided, and enforced here rather
                    # than trusted to the page.
                    "" if control else str(raw.get("document") or "")[:80],
                    "" if control else str(raw.get("segment") or "")[:40],
                    0.0 if control else min(amount, 86400.0),
                    str(raw.get("control") or "")[:60] if control else "",
                    width if control and width in EVENT_WIDTHS else "",
                    # Which word, and only for a look-up: nothing else is about a word.
                    str(raw.get("word") or "")[:80] if kind == "lookup" else "",
                )
            )
        if not rows:
            return 0
        with self.write() as db:
            db.executemany(
                "INSERT INTO event (person, kind, day, at, language, medium, document, "
                "segment, amount, control, width, word)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                rows,
            )
        return len(rows)

    def totals(self, person_id: int | None) -> list[dict[str, Any]]:
        """Seconds listened, seconds watched and words read, by day, language and medium.

        Derived, never stored: the figures on Your Progress are a reading of the log, so
        they are the sum across every device by construction. Listening and watching are
        one kind of event told apart by whether the picture was up.
        """
        if person_id is None:
            return []
        found = self.db.execute(
            "SELECT day, language, medium, "
            "SUM(CASE WHEN kind = 'play' AND medium != 'watch' THEN amount ELSE 0 END) AS heard, "
            "SUM(CASE WHEN kind = 'play' AND medium = 'watch' THEN amount ELSE 0 END) AS watched, "
            "SUM(CASE WHEN kind IN ('page', 'section') THEN amount ELSE 0 END) AS words "
            "FROM event WHERE person = ? AND kind IN ('play', 'page', 'section') "
            "GROUP BY day, language, medium ORDER BY day",
            (int(person_id),),
        ).fetchall()
        return [
            {
                "day": str(row["day"]),
                "language": str(row["language"]),
                "medium": str(row["medium"]),
                "listened": round(float(row["heard"] or 0)),
                "watched": round(float(row["watched"] or 0)),
                "words": round(float(row["words"] or 0)),
            }
            for row in found
        ]

    def forget_events(self, person: Person) -> int:
        """Erase the record, at the reader's own press. The switch is left as it was."""
        with self.write() as db:
            gone = db.execute("DELETE FROM event WHERE person = ?", (person.id,)).rowcount
        return int(gone or 0)

    def pressed(self) -> list[dict[str, Any]]:
        """How often each control of the reader is pressed, by width — for the audit of
        what should be within reach (targum-internal#341). Across everybody, and of nobody:
        the rows it reads carry no document and no segment, and it returns no person."""
        found = self.db.execute(
            "SELECT control, width, COUNT(*) AS presses, COUNT(DISTINCT person) AS readers "
            "FROM event WHERE kind = 'control' GROUP BY control, width ORDER BY presses DESC"
        ).fetchall()
        return [
            {
                "control": str(row["control"]),
                "width": str(row["width"]),
                "presses": int(row["presses"]),
                "readers": int(row["readers"]),
            }
            for row in found
        ]

    #: What counts as stalling, and why each one does. A word tapped for a gloss is a
    #: word that was not known; a segment replayed is one that was not caught; a stop is
    #: where somebody put the text down. targum-internal#127 names these three.
    STALL_KINDS = ("lookup", "replay", "stop")

    def stalls(self, document: str) -> list[dict[str, Any]]:
        """Where readers stall in one text, by segment — targum-internal#127's read path.

        In segment order, so it plots as the text reads rather than as a league table;
        the counts are there for whoever wants to rank them.

        **Aggregate, and of nobody.** It returns counts and a reader tally and never a
        person or a day, which is the granularity the privacy notice describes (clause
        3.7, aggregate records of use) rather than the per-reader log clause 3.6 covers.
        `readers` is there because a segment ten people looked up is a hard word and a
        segment one person looked up ten times is one person having a bad morning, and
        the counts alone cannot tell those apart.

        Keyed on the segment id, so a re-cut that keeps its ids keeps its history — the
        same property translations and annotations already have.
        """
        marks = ", ".join(f"'{kind}'" for kind in self.STALL_KINDS)
        found = self.db.execute(
            "SELECT segment, "
            "SUM(kind = 'lookup') AS lookups, "
            "SUM(kind = 'replay') AS replays, "
            "SUM(kind = 'stop') AS stops, "
            "COUNT(DISTINCT person) AS readers "
            f"FROM event WHERE document = ? AND segment <> '' AND kind IN ({marks}) "
            "GROUP BY segment ORDER BY segment",
            (document,),
        ).fetchall()
        return [
            {
                "segment": str(row["segment"]),
                "lookups": int(row["lookups"] or 0),
                "replays": int(row["replays"] or 0),
                "stops": int(row["stops"] or 0),
                "readers": int(row["readers"] or 0),
            }
            for row in found
        ]

    #: How the conversation may address somebody in Hebrew: as a man, as a woman, or
    #: without choosing.
    ADDRESSES = ("", "m", "f")

    def address(self, person_id: int | None) -> str:
        """'m', 'f', or '' where they have not said."""
        if person_id is None:
            return ""
        row = self.db.execute(
            "SELECT address FROM person WHERE id = ?", (int(person_id),)
        ).fetchone()
        return str(row["address"] or "") if row is not None else ""

    def set_address(self, person: Person, address: str) -> str:
        """Keep how they want to be addressed; anything else is refused."""
        value = str(address or "").strip().lower()
        if value not in self.ADDRESSES:
            raise ValueError("No such choice.")
        with self.write() as db:
            db.execute(
                "UPDATE person SET address = ?, ledger = ledger + 1 WHERE id = ?",
                (value, person.id),
            )
        return value

    def rename(self, person: Person, name: str) -> str:
        """Set what to call them, and return what was stored.

        Empty is allowed and means "go back to having none": the avatar falls back to the
        address, which is what it did before anybody typed anything.
        """
        tidied = " ".join(str(name).split())[: self.NAME_LIMIT]
        with self.write() as db:
            db.execute("UPDATE person SET name = ? WHERE id = ?", (tidied, person.id))
        return tidied

    def asking_too_often(self, who: str, limit: int = ASKS_PER_HOUR) -> bool:
        """Whether this address has asked for too many links in the last hour.

        Recorded per address rather than per connection: an address is the thing that
        receives the mail, and it is the inbox being protected.
        """
        window = now() - 60 * 60 * 1000
        with self.write() as db:
            db.execute("DELETE FROM asked WHERE made < ?", (window,))
            row = db.execute(
                "SELECT COUNT(*) AS n FROM asked WHERE who = ? AND made >= ?", (tidy(who), window)
            ).fetchone()
            if int(row["n"]) >= limit:
                return True
            db.execute("INSERT INTO asked (who, made) VALUES (?, ?)", (tidy(who), now()))
            return False

    # -- the weekly ------------------------------------------------------------
    #
    # A subscriber is not an account and never becomes one. Different table, no foreign
    # key, no `person` row, `invited` untouched, and the mail carries no sign-in link —
    # only the public issue and the way out. The one thing the two share is an address,
    # which is what makes the pleasant case work by itself: somebody who subscribed
    # signed out and later opens an account finds the box already ticked, because both
    # doors write the same row.

    def following(self, email: str) -> bool:
        address = tidy(email)
        row = self.db.execute("SELECT state FROM subscriber WHERE email = ?", (address,)).fetchone()
        return row is not None and str(row["state"]) == "on"

    def subscribe(self, email: str, language: str = "") -> str | None:
        """The public door. Mint a token to confirm this address, or None if it is on.

        Idempotent: asking twice re-mints rather than making a second row, because
        asking twice is what somebody does when the first mail did not arrive.

        `language` is the one the page was in when they asked (targum-internal#288). A
        second ask overwrites it, as a second ask at the waitlist does: the door they came
        through most recently is the better guess at what they read.
        """
        address = tidy(email)
        if not address:
            raise ValueError("No address given.")
        if self.following(address):
            return None
        token = secrets.token_urlsafe(TOKEN_BYTES)
        spoken = _language_code(language)
        with self.write() as db:
            db.execute(
                """
                INSERT INTO subscriber (email, state, confirm, stop, asked, language)
                VALUES (?, 'pending', ?, ?, ?, ?)
                ON CONFLICT(email) DO UPDATE SET
                    state = 'pending', confirm = ?, asked = ?, language = ?
                """,
                (
                    address,
                    digest(token),
                    secrets.token_urlsafe(TOKEN_BYTES),
                    now(),
                    spoken,
                    digest(token),
                    now(),
                    spoken,
                ),
            )
        return token

    def follow(self, email: str, on: bool = True, language: str = "") -> bool:
        """The signed-in door, and it confirms nothing.

        Somebody with a session proved they control this address by following a link to
        get in. Mailing them to ask whether they control it would be asking them to
        confirm what they confirmed at the door.

        `language` is the one they were reading targum in as they pressed, written on
        every press for the reason `follow_series` gives, and left alone on a stop.
        """
        address = tidy(email)
        if not address:
            raise ValueError("No address given.")
        spoken = _language_code(language)
        with self.write() as db:
            if not on:
                db.execute(
                    "UPDATE subscriber SET state = 'off', ended = ? WHERE email = ?",
                    (now(), address),
                )
                self._weekly_row(db, address, False, "")
                return False
            db.execute(
                """
                INSERT INTO subscriber (email, state, confirm, stop, asked, joined, language)
                VALUES (?, 'on', NULL, ?, ?, ?, ?)
                ON CONFLICT(email) DO UPDATE SET
                    state = 'on', confirm = NULL, joined = ?, language = ?
                """,
                (
                    address,
                    secrets.token_urlsafe(TOKEN_BYTES),
                    now(),
                    now(),
                    spoken,
                    now(),
                    spoken,
                ),
            )
            self._weekly_row(db, address, True, spoken)
        return True

    def subscription_language(self, token: str) -> str:
        """The language behind a weekly token, for the page it opens.

        Matched on either token, as `waiting_language` is: `confirm` is hashed and `stop`
        is in the clear. A token that is neither answers English. Only the confirm door
        may use this — the stop door has to answer the same for a real token and a
        made-up one, so it takes the request's language instead.
        """
        if not token:
            return "en"
        row = self.db.execute(
            "SELECT language FROM subscriber WHERE confirm = ? OR stop = ?",
            (digest(token), token),
        ).fetchone()
        return str(row["language"] or "en") if row is not None else "en"

    def peek_subscription(self, token: str) -> str | None:
        """Whose address this token would confirm, without spending it.

        The same reason `/account/enter` stopped being a bare GET: a mail client that
        fetches every link in a message would otherwise confirm the subscription before
        the person had read the sentence asking whether they wanted it.
        """
        row = self.db.execute(
            "SELECT email FROM subscriber WHERE confirm = ? AND state = 'pending'",
            (digest(token),),
        ).fetchone()
        return str(row["email"]) if row else None

    def confirm_subscription(self, token: str) -> str | None:
        """Spend a confirmation. Returns the address, or None if it was not one."""
        with self.write() as db:
            row = db.execute(
                "SELECT email FROM subscriber WHERE confirm = ? AND state = 'pending'",
                (digest(token),),
            ).fetchone()
            if row is None:
                return None
            db.execute(
                "UPDATE subscriber SET state = 'on', confirm = NULL, joined = ? WHERE email = ?",
                (now(), row["email"]),
            )
            # An account at this address sees it on its Subscriptions tab too.
            self._weekly_row(db, str(row["email"]), True, "")
            return str(row["email"])

    def stop_subscription(self, token: str) -> bool:
        """One click, from an email, with no account and no JavaScript."""
        if not token:
            return False
        with self.write() as db:
            row = db.execute("SELECT email FROM subscriber WHERE stop = ?", (token,)).fetchone()
            if row is None:
                return False
            db.execute(
                "UPDATE subscriber SET state = 'off', ended = ? WHERE email = ?",
                (now(), row["email"]),
            )
            self._weekly_row(db, str(row["email"]), False, "")
            return True

    # -- the waitlist (2026-09-16) ----------------------------------------------------
    #
    # The front door's only form. Somebody waiting is not an account, is not a
    # subscriber, and becomes neither by waiting: the address sits in `waiting` until a
    # person decides to let them in, and letting them in is `allow` on `invited`, which
    # is a separate act with a separate record.

    def join_waitlist(
        self, email: str, language: str = "", page: str = "", link: str = ""
    ) -> str | None:
        """Take an address. Mint a token to confirm it, or None if it is already on.

        Idempotent for the same reason `subscribe` is: asking twice is what somebody
        does when the first mail did not arrive, and it should re-mint rather than make
        a second row or a second person.

        `language` is the language the front door was in when they pressed, and it is
        kept so the invitation can be written in it. A second ask overwrites it: the
        door they came through most recently is the better guess at what they read.

        `page` is which of targum's pages they pressed Join on, already narrowed to one
        the caller recognises; empty is unknown. A second ask keeps the first answer,
        because the question it answers is which page brought them.

        `link` is what they tried in the front page's box before joining, already vetted
        by the caller (targum-internal#399). A second ask with a link replaces it; one
        without keeps what was there.
        """
        address = tidy(email)
        if not address:
            raise ValueError("No address given.")
        if self.waiting_state(address) == "on":
            return None
        token = secrets.token_urlsafe(TOKEN_BYTES)
        spoken = tidy(language)
        with self.write() as db:
            db.execute(
                """
                INSERT INTO waiting (email, state, confirm, stop, asked, language, page, link)
                VALUES (?, 'pending', ?, ?, ?, ?, ?, ?)
                ON CONFLICT(email) DO UPDATE SET
                    state = 'pending', confirm = ?, asked = ?, language = ?,
                    page = CASE WHEN page = '' THEN excluded.page ELSE page END,
                    link = CASE WHEN excluded.link = '' THEN link ELSE excluded.link END
                """,
                (
                    address,
                    digest(token),
                    secrets.token_urlsafe(TOKEN_BYTES),
                    now(),
                    spoken,
                    page,
                    link,
                    digest(token),
                    now(),
                    spoken,
                ),
            )
        return token

    def waiting_state(self, email: str) -> str:
        """`pending`, `on`, `off`, or empty for an address that never asked."""
        row = self.db.execute(
            "SELECT state FROM waiting WHERE email = ?", (tidy(email),)
        ).fetchone()
        return "" if row is None else str(row["state"])

    def peek_waiting(self, token: str) -> str | None:
        """Whose address this token would confirm, without spending it.

        For the reason `peek_subscription` exists: a mail client that fetches every link
        in a message would otherwise answer for the person it was sent to.
        """
        row = self.db.execute(
            "SELECT email FROM waiting WHERE confirm = ? AND state = 'pending'",
            (digest(token),),
        ).fetchone()
        return None if row is None else str(row["email"])

    def waiting_language(self, token: str) -> str:
        """The language behind a waitlist token, for the page and the mail it opens.

        `join_waitlist` has recorded the door somebody came through since
        targum-internal#292, and until 2026-09-22 only the invitation read it back — so
        somebody who joined at the Russian front door was answered in English at every
        step between joining and being invited (targum-internal#288).

        Matched on either token, because one row has two: `confirm` is hashed like a
        sign-in link, and `stop` is in the clear so it can be minted into a mail. A token
        that is neither answers English rather than raising: these pages are followed out
        of a mail client and have to draw for somebody who already pressed once.
        """
        if not token:
            return "en"
        row = self.db.execute(
            "SELECT language FROM waiting WHERE confirm = ? OR stop = ?",
            (digest(token), token),
        ).fetchone()
        return str(row["language"] or "en") if row is not None else "en"

    def confirm_waiting(self, token: str) -> str | None:
        """Spend a confirmation. Returns the address, or None if it was not one."""
        if not token:
            return None
        with self.write() as db:
            row = db.execute(
                "SELECT email FROM waiting WHERE confirm = ? AND state = 'pending'",
                (digest(token),),
            ).fetchone()
            if row is None:
                return None
            db.execute(
                "UPDATE waiting SET state = 'on', confirm = NULL, joined = ? WHERE email = ?",
                (now(), row["email"]),
            )
            return str(row["email"])

    def leave_waitlist(self, token: str) -> bool:
        """One press, from a mail, with no account and no JavaScript."""
        if not token:
            return False
        with self.write() as db:
            row = db.execute("SELECT email FROM waiting WHERE stop = ?", (token,)).fetchone()
            if row is None:
                return False
            db.execute(
                # The link goes with them: it was kept only to hand back when they
                # were let in (targum-internal#399).
                "UPDATE waiting SET state = 'off', ended = ?, link = '' WHERE email = ?",
                (now(), row["email"]),
            )
            return True

    def waiting_count(self) -> dict[str, int]:
        """How many are waiting, by state. What the back office shows."""
        rows = self.db.execute("SELECT state, COUNT(*) AS n FROM waiting GROUP BY state").fetchall()
        counted = {str(row["state"]): int(row["n"]) for row in rows}
        return {state: counted.get(state, 0) for state in ("pending", "on", "off")}

    def waiting_for_a_way_in(self, limit: int = 0) -> list[tuple[str, str]]:
        """Confirmed addresses not yet let in, oldest first, each with the language it
        joined in: the order they would be let in, and what to write to them in.

        Oldest first because the front door promises it — "The earlier you join, the
        earlier that is" — and a waitlist that let people in in any other order would be
        making that sentence untrue quietly.
        """
        sql = (
            "SELECT email, language FROM waiting WHERE state = 'on' AND invited = 0 ORDER BY asked"
        )
        rows = self.db.execute(
            sql + (" LIMIT ?" if limit else ""), (limit,) if limit else ()
        ).fetchall()
        return [(str(row["email"]), str(row["language"] or "")) for row in rows]

    def waiting_invited(self, email: str) -> None:
        """Stamp an address as let in, so a second opening does not mail them twice."""
        with self.write() as db:
            db.execute("UPDATE waiting SET invited = ? WHERE email = ?", (now(), tidy(email)))

    def waiting_link(self, email: str) -> str:
        """The link somebody tried on the front page and joined with, or "" (#399)."""
        row = self.db.execute("SELECT link FROM waiting WHERE email = ?", (tidy(email),)).fetchone()
        return "" if row is None else str(row["link"] or "")

    def account_for_invited(self, email: str) -> Person | None:
        """The account an invited address will sign in to, made now if it is not there.

        The same row `start_sign_in` makes on the first link, made a little earlier: when
        somebody is let in with a saved link, the build of it has to belong to somebody
        before they have signed in (targum-internal#399). Only for an address already on
        the guest list, so this cannot open an account the door did not.
        """
        address = tidy(email)
        with self.write() as db:
            if db.execute("SELECT 1 FROM invited WHERE email = ?", (address,)).fetchone() is None:
                return None
            db.execute(
                "INSERT INTO person (email, made) VALUES (?, ?) ON CONFLICT(email) DO NOTHING",
                (address, now()),
            )
        return self.person_by_email(address)

    # -- subscriptions (design.md §12, "A subscription is the account's", 2026-10-09) ---
    #
    # What a reader subscribed to is a row on their account. A series' follow was a row
    # keyed by address (`follow`, 2026-09-11) and is carried across by MIGRATIONS; the
    # methods that spoke of following keep their names and their answers, and read and
    # write `subscription` underneath, so the per-series mail and its stop page go on
    # working on the rows they always had.

    def _subscription_row(self, row: sqlite3.Row | None) -> dict[str, Any] | None:
        return dict(row) if row is not None else None

    def add_subscription(
        self,
        person_id: int,
        kind: str,
        key: str,
        *,
        name: str = "",
        language: str = "",
        source: str = "",
        cap: int = 0,
        said: str = "",
    ) -> dict[str, Any]:
        """Subscribe, or subscribe again. Returns the row.

        A subscription that was off is on again from now: what came out while it was off
        is from before, and is listed rather than built (design.md §12). One that is
        paused stays paused — subscribing is not resuming, which is its own press. `cap`
        is written only where one is given; `said` on every press, for the reason
        `follow_series` gave.
        """
        if kind not in SUB_KINDS or not key:
            raise ValueError("No such subscription.")
        code = _language_code(said) if said else ""
        stamp = now()
        with self.write() as db:
            db.execute(
                """
                INSERT INTO subscription
                    (person, kind, key, name, language, source, cap, state, stop, since, said)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'on', ?, ?, ?)
                ON CONFLICT(person, kind, key) DO UPDATE SET
                    since = CASE WHEN state = 'off' THEN excluded.since ELSE since END,
                    ended = CASE WHEN state = 'off' THEN 0 ELSE ended END,
                    state = CASE WHEN state = 'off' THEN 'on' ELSE state END,
                    name = CASE WHEN excluded.name != '' THEN excluded.name ELSE name END,
                    language = CASE WHEN excluded.language != '' THEN excluded.language
                        ELSE language END,
                    source = CASE WHEN excluded.source != '' THEN excluded.source
                        ELSE source END,
                    cap = CASE WHEN excluded.cap > 0 THEN excluded.cap ELSE cap END,
                    said = CASE WHEN excluded.said != '' THEN excluded.said ELSE said END
                """,
                (
                    person_id,
                    kind,
                    key,
                    name,
                    language,
                    source,
                    max(0, int(cap)),
                    secrets.token_urlsafe(TOKEN_BYTES),
                    stamp,
                    code,
                ),
            )
            row = db.execute(
                "SELECT * FROM subscription WHERE person = ? AND kind = ? AND key = ?",
                (person_id, kind, key),
            ).fetchone()
        return dict(row)

    def set_subscription_state(self, person_id: int, sub_id: int, state: str) -> bool:
        """Pause, resume or stop one of this reader's subscriptions. False where it is not
        theirs or is already off. Pausing stops the building and the mail; resuming
        builds nothing that came out meanwhile — the poll listed it as `paused`."""
        if state not in SUB_STATES:
            raise ValueError("No such state.")
        stamp = now()
        with self.write() as db:
            found = db.execute(
                "SELECT state FROM subscription WHERE id = ? AND person = ?", (sub_id, person_id)
            ).fetchone()
            if found is None or (str(found["state"]) == "off" and state != "on"):
                return False
            db.execute(
                "UPDATE subscription SET state = ?,"
                " paused = CASE WHEN ? = 'paused' THEN ? ELSE 0 END,"
                " ended = CASE WHEN ? = 'off' THEN ? ELSE 0 END,"
                " since = CASE WHEN state = 'off' THEN ? ELSE since END"
                " WHERE id = ?",
                (state, state, stamp, state, stamp, stamp, sub_id),
            )
            # A paused or stopped subscription builds nothing: what was waiting for its
            # turn is listed with a press, never left to go by itself on a resume.
            if state != "on":
                db.execute(
                    "UPDATE sub_item SET state = 'listed', why = '', came = 'paused'"
                    " WHERE subscription = ? AND state IN ('due', 'waiting')",
                    (sub_id,),
                )
        return True

    def set_subscription_cap(self, person_id: int, sub_id: int, cap: int) -> bool:
        """Change a channel's or a podcast's monthly cap, on the reader's own press. Only
        to one of the caps the page offers; anything else changes nothing."""
        if cap not in CAPS:
            return False
        with self.write() as db:
            done = db.execute(
                "UPDATE subscription SET cap = ? WHERE id = ? AND person = ?"
                " AND kind IN ('channel', 'podcast')",
                (cap, sub_id, person_id),
            ).rowcount
        return bool(done)

    def subscription(self, person_id: int | None, sub_id: int) -> dict[str, Any] | None:
        """One of this reader's subscriptions, or None — never somebody else's."""
        if person_id is None:
            return None
        return self._subscription_row(
            self.db.execute(
                "SELECT * FROM subscription WHERE id = ? AND person = ?", (sub_id, person_id)
            ).fetchone()
        )

    def subscription_for(self, person_id: int | None, kind: str, key: str) -> dict[str, Any] | None:
        if person_id is None:
            return None
        return self._subscription_row(
            self.db.execute(
                "SELECT * FROM subscription WHERE person = ? AND kind = ? AND key = ?",
                (person_id, kind, key),
            ).fetchone()
        )

    def subscriptions(self, person_id: int | None, *, every: bool = False) -> list[dict[str, Any]]:
        """This reader's subscriptions, the ones they stopped left out unless `every`:
        each row, with how many of its items are new to them and its newest item."""
        if person_id is None:
            return []
        rows = self.db.execute(
            "SELECT * FROM subscription WHERE person = ?"
            + ("" if every else " AND state != 'off'")
            + " ORDER BY since",
            (person_id,),
        ).fetchall()
        out: list[dict[str, Any]] = []
        for row in rows:
            one = dict(row)
            latest = self.db.execute(
                "SELECT * FROM sub_item WHERE subscription = ? AND came = ''"
                " ORDER BY published DESC, found DESC LIMIT 1",
                (one["id"],),
            ).fetchone()
            one["latest"] = dict(latest) if latest is not None else None
            fresh = self.db.execute(
                "SELECT COUNT(*) AS n FROM sub_item WHERE subscription = ? AND came = ''"
                " AND seen = 0 AND state IN ('ready', 'listed')",
                (one["id"],),
            ).fetchone()
            one["new"] = int(fresh["n"])
            out.append(one)
        return out

    def live_subscriptions(self) -> list[dict[str, Any]]:
        """Every subscription that is on or paused, for the poll: a paused one is still
        looked at, so what comes out meanwhile can be listed when it resumes."""
        rows = self.db.execute(
            "SELECT s.*, p.email AS email FROM subscription s JOIN person p ON p.id = s.person"
            " WHERE s.state IN ('on', 'paused') AND p.leaving IS NULL ORDER BY s.polled, s.id"
        ).fetchall()
        return [dict(row) for row in rows]

    def polled(self, sub_id: int) -> None:
        """Stamp a subscription as looked at: the poll's checkpoint, written once its
        items are, so a run that dies resumes with the ones it had not reached."""
        with self.write() as db:
            db.execute("UPDATE subscription SET polled = ? WHERE id = ?", (now(), sub_id))

    def sub_items(self, sub_id: int, limit: int = 60) -> list[dict[str, Any]]:
        """What one subscription brought, newest first."""
        rows = self.db.execute(
            "SELECT * FROM sub_item WHERE subscription = ?"
            " ORDER BY published DESC, found DESC LIMIT ?",
            (sub_id, limit),
        ).fetchall()
        return [dict(row) for row in rows]

    def add_sub_items(self, sub_id: int, items: Iterable[Mapping[str, Any]]) -> int:
        """Write what a look found. An item already here is left as it is, so a look that
        runs twice finds nothing the second time. Returns how many were new."""
        stamp = now()
        added = 0
        with self.write() as db:
            for item in items:
                key = str(item.get("key") or "")
                if not key:
                    continue
                added += db.execute(
                    "INSERT OR IGNORE INTO sub_item"
                    " (subscription, key, title, link, reader, published, found, seconds,"
                    " state, came)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        sub_id,
                        key,
                        str(item.get("title") or ""),
                        str(item.get("link") or ""),
                        str(item.get("reader") or ""),
                        int(item.get("published") or 0),
                        stamp,
                        float(item.get("seconds") or 0),
                        str(item.get("state") or "listed"),
                        str(item.get("came") or ""),
                    ),
                ).rowcount
        return added

    #: What `set_sub_item` may change.
    SUB_ITEM_FIELDS = frozenset({"state", "why", "job", "reader", "credits", "seen", "mailed"})

    def set_sub_item(self, sub_id: int, key: str, **fields: Any) -> None:
        wrong = set(fields) - self.SUB_ITEM_FIELDS
        if wrong or not fields:
            raise ValueError(f"Not a field of a subscription's item: {sorted(wrong)}")
        sets = ", ".join(f"{name} = ?" for name in fields)
        with self.write() as db:
            db.execute(
                f"UPDATE sub_item SET {sets} WHERE subscription = ? AND key = ?",
                (*fields.values(), sub_id, key),
            )

    def sub_items_in(self, states: Iterable[str]) -> list[dict[str, Any]]:
        """Every item in these states, with its subscription's owner, kind and cap."""
        wanted = tuple(states)
        holes = ", ".join("?" for _ in wanted)
        rows = self.db.execute(
            "SELECT i.*, s.person AS person, s.kind AS kind, s.cap AS cap, s.state AS sub_state,"
            " s.language AS language, s.said AS said"
            f" FROM sub_item i JOIN subscription s ON s.id = i.subscription"
            f" WHERE i.state IN ({holes}) ORDER BY i.published, i.found",
            wanted,
        ).fetchall()
        return [dict(row) for row in rows]

    def month_credits(self, person_id: int, sub_id: int, month_from: int) -> int:
        """What one subscription has built with this month, in credits — read off its own
        job rows, the same `length` `claim` holds the plan to, so there is one ledger."""
        row = self.db.execute(
            "SELECT COALESCE(SUM(length), 0) AS used FROM job"
            " WHERE kind = 'subscription' AND owner = ? AND made >= ?"
            " AND json_extract(options, '$.subscription') = ?",
            (person_id, month_from, sub_id),
        ).fetchone()
        return round(float(row["used"]) / SECONDS_A_CREDIT)

    def new_sub_items(self, person_id: int | None, limit: int = 6) -> list[dict[str, Any]]:
        """What this reader's subscriptions brought that they have not opened from home,
        newest first: Continue's New cards. Only what came while they were subscribed and
        that opens or is a link — nothing still being made, and nothing paused."""
        if person_id is None:
            return []
        rows = self.db.execute(
            "SELECT i.*, s.kind AS kind, s.key AS sub_key, s.name AS sub_name,"
            " s.language AS language FROM sub_item i JOIN subscription s"
            " ON s.id = i.subscription"
            " WHERE s.person = ? AND s.state = 'on' AND i.came = '' AND i.seen = 0"
            " AND i.state IN ('ready', 'listed') AND i.found >= s.since"
            " ORDER BY i.published DESC, i.found DESC LIMIT ?",
            (person_id, limit),
        ).fetchall()
        return [dict(row) for row in rows]

    def saw_sub_item(self, person_id: int, sub_id: int, key: str) -> bool:
        """The reader opened it from home: it is no longer New."""
        with self.write() as db:
            done = db.execute(
                "UPDATE sub_item SET seen = ? WHERE subscription = ? AND key = ?"
                " AND subscription IN (SELECT id FROM subscription WHERE person = ?)",
                (now(), sub_id, key, person_id),
            ).rowcount
        return bool(done)

    def items_to_mail(self, since: int) -> list[dict[str, Any]]:
        """Everything new that has not been mailed, found since `since`, with whose it is
        and where its subscription stops: the one mail a day (design.md §12, "Everything
        new comes in one mail a day", 2026-10-09). A paused or stopped subscription is
        left out, and so is the weekly, which keeps its own Monday mail. What waits on its
        cap is in it, so the reader hears once; what is still being made is not yet."""
        rows = self.db.execute(
            "SELECT i.*, s.id AS sub, s.kind AS kind, s.key AS sub_key, s.name AS sub_name,"
            " s.language AS language, s.said AS said, s.stop AS stop, s.since AS sub_since,"
            " p.id AS person, p.email AS email"
            " FROM sub_item i JOIN subscription s ON s.id = i.subscription"
            " JOIN person p ON p.id = s.person"
            " WHERE s.state = 'on' AND p.leaving IS NULL AND i.mailed = 0 AND i.came = ''"
            " AND i.found >= ? AND NOT (s.kind = 'series' AND s.key = 'weekly')"
            " AND (i.state IN ('ready', 'listed') OR (i.state = 'waiting' AND i.why = 'cap'))"
            " ORDER BY p.id, s.since, s.id, i.published DESC, i.found DESC",
            (since,),
        ).fetchall()
        return [dict(row) for row in rows]

    def mark_mailed(self, items: Iterable[tuple[int, str]]) -> None:
        """Stamp items as mailed, so a run that is started again sends none of them."""
        stamp = now()
        with self.write() as db:
            for sub_id, key in items:
                db.execute(
                    "UPDATE sub_item SET mailed = ? WHERE subscription = ? AND key = ?",
                    (stamp, sub_id, key),
                )

    def waiting_mailed(self, sub_id: int, since: int) -> bool:
        """Whether this subscription has told its reader this month that something waits:
        they hear once, and what waits with it is not mailed again."""
        row = self.db.execute(
            "SELECT 1 FROM sub_item WHERE subscription = ? AND state = 'waiting'"
            " AND why = 'cap' AND mailed >= ? LIMIT 1",
            (sub_id, since),
        ).fetchone()
        return row is not None

    def subscription_by_stop(self, token: str) -> dict[str, Any] | None:
        """The subscription a stop link names, for the page it opens."""
        if not token:
            return None
        return self._subscription_row(
            self.db.execute("SELECT * FROM subscription WHERE stop = ?", (token,)).fetchone()
        )

    def _weekly_row(self, db: sqlite3.Connection, email: str, on: bool, said: str) -> None:
        """Keep an account's own weekly row in step with `subscriber`, which is where the
        Monday mail is read from. Nothing for an address without an account."""
        person = db.execute("SELECT id FROM person WHERE email = ?", (tidy(email),)).fetchone()
        if person is None:
            return
        stamp = now()
        if on:
            db.execute(
                "INSERT INTO subscription (person, kind, key, language, state, stop, since, said)"
                " VALUES (?, 'series', 'weekly', 'he', 'on', ?, ?, ?)"
                " ON CONFLICT(person, kind, key) DO UPDATE SET state = 'on', ended = 0,"
                " said = CASE WHEN excluded.said != '' THEN excluded.said ELSE said END",
                (int(person["id"]), secrets.token_urlsafe(TOKEN_BYTES), stamp, said),
            )
        else:
            # A paused weekly is left paused: pausing is what turned its mail off.
            db.execute(
                "UPDATE subscription SET state = 'off', ended = ?"
                " WHERE person = ? AND kind = 'series' AND key = 'weekly' AND state = 'on'",
                (stamp, int(person["id"])),
            )

    # -- series (2026-09-11), on the subscription rows since 2026-10-09 --------------

    def follow_series(self, email: str, series: str, on: bool = True, language: str = "") -> bool:
        """Subscribe to, or stop, one series, for the account at this address.

        `language` is the one the reader was reading in when they pressed, kept so the
        mail and the stop page can be in it (targum-internal#289). Written on every press,
        and never cleared on a stop. An address with no account behind it has nothing to
        subscribe with since 2026-10-09, and is answered False.
        """
        address = tidy(email)
        if not address or not series:
            raise ValueError("No address or no series given.")
        person = self.person_by_email(address)
        if person is None:
            return False
        if not on:
            found = self.subscription_for(person.id, "series", series)
            if found is not None:
                self.set_subscription_state(person.id, int(found["id"]), "off")
            return False
        self.add_subscription(person.id, "series", series, language="he", said=language)
        return True

    def series_followed(self, email: str) -> list[str]:
        """The series this address's account is subscribed to, the weekly left out: it is
        `subscriber`'s, and `following` answers for it."""
        rows = self.db.execute(
            "SELECT s.key FROM subscription s JOIN person p ON p.id = s.person"
            " WHERE p.email = ? AND s.kind = 'series' AND s.key != 'weekly'"
            " AND s.state = 'on' ORDER BY s.key",
            (tidy(email),),
        ).fetchall()
        return [str(row["key"]) for row in rows]

    def followers(self, series: str, not_sent: str = "") -> list[tuple[str, str, str]]:
        """Everyone to mail about this instalment, with the token that stops it and the
        language they subscribed in.

        Selected on "has not had this one", as the weekly's are, so a run that died
        halfway resumes and one started twice sends nothing the second time. A paused
        subscription is not mailed.
        """
        rows = self.db.execute(
            "SELECT p.email AS email, s.stop AS stop, s.said AS said"
            " FROM subscription s JOIN person p ON p.id = s.person"
            " WHERE s.kind = 'series' AND s.key = ? AND s.state = 'on'"
            " AND p.leaving IS NULL AND (? = '' OR s.instalment != ?) ORDER BY s.since",
            (series, not_sent, not_sent),
        ).fetchall()
        return [(str(row["email"]), str(row["stop"]), str(row["said"] or "en")) for row in rows]

    def following_language(self, token: str) -> str:
        """The language behind a stop token, for the page it opens.

        A stop link is followed with no session and no account — that is the whole point
        of it — so the token is the only thing the page has to go on.
        """
        found = self.subscription_by_stop(token)
        return str(found["said"] or "en") if found is not None else "en"

    def following_series(self, token: str) -> str:
        """Which series a stop token is for, or "" — so the page it opens can name it."""
        found = self.subscription_by_stop(token)
        if found is None or found["kind"] != "series":
            return ""
        return str(found["key"])

    def stop_following(self, token: str) -> bool:
        """One click, from an email, with no account and no JavaScript: stops the one
        subscription the link names. True where the token names one."""
        found = self.subscription_by_stop(token)
        if found is None:
            return False
        with self.write() as db:
            db.execute(
                "UPDATE subscription SET state = 'off', ended = ? WHERE id = ?",
                (now(), int(found["id"])),
            )
            db.execute(
                "UPDATE sub_item SET state = 'listed', why = '', came = 'paused'"
                " WHERE subscription = ? AND state IN ('due', 'waiting')",
                (int(found["id"]),),
            )
            if found["kind"] == "series" and found["key"] == "weekly":
                db.execute(
                    "UPDATE subscriber SET state = 'off', ended = ?"
                    " WHERE email = (SELECT email FROM person WHERE id = ?)",
                    (now(), int(found["person"])),
                )
        return True

    def subscribers(self, not_sent: str = "") -> list[tuple[str, str, str]]:
        """Everyone to mail about this issue, with the token that stops it and the
        language they asked for it in ("en" where they said nothing).

        Selecting on "has not had this one" rather than on "is subscribed" is what makes
        a mailout safe to resume: a run that died halfway picks up where it stopped, and
        one started twice sends nothing the second time.

        And on "has not had a later one", which is what makes announcing the wrong week
        harmless. Rows carry the last issue sent, not a history, so a plain "not this
        one" would post last week's issue to everybody who already had this week's.
        """
        rows = self.db.execute(
            "SELECT email, stop, language FROM subscriber WHERE state = 'on' "
            # Not this issue, and not one already past it. The column holds the last
            # issue sent rather than a history, so "not this one" alone would re-send
            # last week to everybody the moment somebody typed the wrong week — and an
            # email is the one thing here that cannot be taken back. Issue ids are
            # `YYYY-wNN`, zero-padded, so they sort in the order the weeks happened.
            "AND (issue IS NULL OR issue < ?) "
            "ORDER BY joined",
            (not_sent,),
        ).fetchall()
        return [(str(row["email"]), str(row["stop"]), str(row["language"] or "en")) for row in rows]

    def subscribed(self) -> int:
        """How many people this database could mail at all, whatever issue is being sent.

        `subscribers` answers "who has not had this one", which is empty both when a run
        has already finished and when there is nobody here to mail. Those are different
        facts and one of them is a defect (targum-internal#346), so the mailout asks
        this before calling an empty list a finished job.
        """
        row = self.db.execute("SELECT COUNT(*) AS n FROM subscriber WHERE state = 'on'").fetchone()
        return int(row["n"])

    def mark_sent(self, email: str, issue_id: str) -> None:
        with self.write() as db:
            db.execute(
                "UPDATE subscriber SET sent = ?, issue = ?, bounces = 0 WHERE email = ?",
                (now(), issue_id, tidy(email)),
            )

    def bounced(self, email: str, limit: int = 3) -> bool:
        """Count a failure, and stop mailing an address that keeps failing.

        Returns whether this was the one that stopped it. Three, because a full mailbox
        and a domain that is briefly unreachable both clear up, and an address that has
        genuinely gone will fail every time.
        """
        address = tidy(email)
        with self.write() as db:
            db.execute("UPDATE subscriber SET bounces = bounces + 1 WHERE email = ?", (address,))
            row = db.execute(
                "SELECT bounces FROM subscriber WHERE email = ?", (address,)
            ).fetchone()
            if row is None or int(row["bounces"]) < limit:
                return False
            db.execute(
                "UPDATE subscriber SET state = 'off', ended = ? WHERE email = ?",
                (now(), address),
            )
            return True

    def invite(self, email: str) -> str:
        """Let one address open an account. Returns the address as it was stored."""
        address = tidy(email)
        if not address:
            raise ValueError("No address given.")
        with self.write() as db:
            db.execute(
                "INSERT INTO invited (email, at) VALUES (?, ?) ON CONFLICT(email) DO NOTHING",
                (address, now()),
            )
        return address

    def uninvite(self, email: str) -> bool:
        """Take an address off the list. Any account it already has is untouched.

        Deliberately: this decides who may *join*, and someone who has been reading for a
        month should not be locked out of their own words by an edit to a guest list.
        Use `forget` to remove a person.
        """
        with self.write() as db:
            return db.execute("DELETE FROM invited WHERE email = ?", (tidy(email),)).rowcount > 0

    # -- test accounts (2026-09-28) ------------------------------------------------

    def make_test_account(self, email: str) -> str:
        """Mark an address as a test account, and invite it.

        Refused for an address that already has an account and is not a test account:
        the next thing that happens to a test account is that it is emptied, and a real
        reader's words must never be one typo away from that. A test account that
        already exists is marked again, harmlessly.
        """
        address = tidy(email)
        if not address or "@" not in address:
            raise ValueError("That doesn't look like an email address.")
        row = self.db.execute("SELECT id FROM person WHERE email = ?", (address,)).fetchone()
        if row is not None and not self.is_test_account_email(address):
            raise ValueError(
                f"{address} already has an account, so it can't become a test account: "
                "signing out of a test account empties it. Use a new address."
            )
        with self.write() as db:
            db.execute(
                "INSERT INTO test_account (email, at) VALUES (?, ?) ON CONFLICT(email) DO NOTHING",
                (address, now()),
            )
            db.execute(
                "INSERT INTO invited (email, at) VALUES (?, ?) ON CONFLICT(email) DO NOTHING",
                (address, now()),
            )
        return address

    def test_accounts(self) -> list[str]:
        return [
            row["email"] for row in self.db.execute("SELECT email FROM test_account ORDER BY at")
        ]

    def is_test_account_email(self, email: str) -> bool:
        address = tidy(email)
        found = self.db.execute("SELECT 1 FROM test_account WHERE email = ?", (address,))
        return found.fetchone() is not None

    def is_test_account(self, person: Person | None) -> bool:
        return person is not None and self.is_test_account_email(person.email)

    def test_sign_in(self, email: str) -> str:
        """A sign-in token for a test account, for the operator to hand over by hand.

        The mailed link proves an address by sending something to it; a test account is
        shared by the people testing, and one of them cannot read the mail. So the box's
        operator can mint the link — for a test account and for nothing else, which is
        what keeps this from being a way into a real reader's account.
        """
        address = tidy(email)
        if not self.is_test_account_email(address):
            raise ValueError(f"{address} is not a test account.")
        return self.start_sign_in(address)

    def wipe(self, person: Person) -> None:
        """Empty a test account, keeping the account and its invitation.

        Everything a reader holds goes — their words, what they marked and finished, what
        they said on arrival, conversations, lists, connections, their name and picture —
        and every session and link with it, so a second browser still signed in is
        signed out too rather than left holding a history that no longer exists. The
        caller empties the account's folder of texts. Refuses anything but a test account.
        """
        if not self.is_test_account(person):
            raise ValueError("Only a test account is wiped.")
        with self.write() as db:
            for table in WIPED:
                db.execute(f"DELETE FROM {table} WHERE person = ?", (person.id,))
            db.execute(
                "DELETE FROM chat_turn WHERE chat IN (SELECT id FROM chat WHERE person = ?)",
                (person.id,),
            )
            db.execute("DELETE FROM chat WHERE person = ?", (person.id,))
            db.execute(
                "DELETE FROM playlist_item WHERE playlist IN"
                " (SELECT id FROM playlist WHERE person = ?)",
                (person.id,),
            )
            db.execute("DELETE FROM playlist WHERE person = ?", (person.id,))
            db.execute(
                "DELETE FROM sub_item WHERE subscription IN"
                " (SELECT id FROM subscription WHERE person = ?)",
                (person.id,),
            )
            db.execute("DELETE FROM subscription WHERE person = ?", (person.id,))
            # Kept by address rather than by person: the series it followed before
            # 2026-10-09, and a language the operator marked it as reading.
            db.execute("DELETE FROM follow WHERE email = ?", (person.email,))
            db.execute("DELETE FROM reads WHERE email = ?", (person.email,))
            db.execute(
                "UPDATE person SET name = '', picture = '', address = '', interest = '',"
                " declared = '', events = '', granted = 0, revision = revision + 1,"
                " ledger = ledger + 1"
                " WHERE id = ?",
                (person.id,),
            )

    def invitations(self) -> list[str]:
        return [row["email"] for row in self.db.execute("SELECT email FROM invited ORDER BY at")]

    def make_admin(self, email: str) -> str:
        """Put an address beyond the spend rails, and on the guest list while we are here.

        Both, because an admin who cannot sign in is not an admin. Making somebody an
        admin is a statement that they may be here, and having to say it twice is a way
        of getting it half done.
        """
        address = tidy(email)
        if not address:
            raise ValueError("No address given.")
        with self.write() as db:
            db.execute(
                "INSERT INTO admin (email, at) VALUES (?, ?) ON CONFLICT(email) DO NOTHING",
                (address, now()),
            )
            db.execute(
                "INSERT INTO invited (email, at) VALUES (?, ?) ON CONFLICT(email) DO NOTHING",
                (address, now()),
            )
        return address

    def unadmin(self, email: str) -> bool:
        """Put an address back under the rails. The invitation and the account stay."""
        with self.write() as db:
            return db.execute("DELETE FROM admin WHERE email = ?", (tidy(email),)).rowcount > 0

    def admins(self) -> list[str]:
        return [row["email"] for row in self.db.execute("SELECT email FROM admin ORDER BY at")]

    # -- languages ----------------------------------------------------------------

    def _chosen(
        self, person_id: int | None, kind: str, offered: set[str], default: str
    ) -> set[str]:
        """What a person said for one kind, kept to the languages targum still has.

        Nobody — no id — is an empty set rather than the default, because the callers
        that work from a home directory use "nothing" to mean "no one to ask" and
        offer everything. A person with no rows gets the default: the app's own
        assumption until they say otherwise.
        """
        if not person_id:
            return set()
        rows = self.db.execute(
            "SELECT language FROM chosen WHERE person = ? AND kind = ?", (int(person_id), kind)
        )
        said = {str(row["language"]) for row in rows} & offered
        return said or {default}

    def learning(self, person_id: int | None) -> set[str]:
        """Which languages this person is learning: what the reading pages offer a
        switcher for, and what an upload may claim to be."""
        from .translate.prompts import READING

        return self._chosen(person_id, "learning", {code for code, _ in READING}, "he")

    def reads(self, person_id: int | None) -> set[str]:
        """Which languages this person reads well enough to be handed a translation in.

        The cost of guessing is a reader handed a page in a language they cannot read
        — and a definition in it following them around every text they own. So this is
        their own answer, and English until they give one.
        """
        from .translate.prompts import INTO

        return self._chosen(person_id, "reading", {code for code, _ in INTO}, "en")

    def said_reading(self, person_id: int | None) -> bool:
        """Whether this person has ever said what they read, in anybody's hand.

        `reads` answers English for an account that has said nothing, which is the right
        default and the wrong thing to ask twice about: the arrival asks a new reader
        which language they read (2026-09-20), and "English because nobody asked" and
        "English because they said so" have to be told apart. A row is a row whoever
        wrote it — the profile page, the conversation's question, or the operator who
        marked an invited address as a Russian reader before it ever signed in.
        """
        if not person_id:
            return False
        row = self.db.execute(
            "SELECT 1 FROM chosen WHERE person = ? AND kind = 'reading' LIMIT 1",
            (int(person_id),),
        ).fetchone()
        return row is not None

    def language(self, person_id: int | None) -> str:
        """The language this person is in right now: the one the switcher shows.

        Their own choice (2026-09-13), kept as a `current` row in `chosen`, the one place a
        language is kept; the browser keeps a copy. A choice they are no longer learning
        falls back rather than failing: Hebrew where they learn it, then the first of the
        rest. The fallback is the rule the conversation used before there was a choice
        (targum-internal#228: alphabetical order put Aramaic ahead of Hebrew).
        """
        learning = self.learning(person_id) if person_id else {"he"}
        if person_id:
            row = self.db.execute(
                "SELECT language FROM chosen WHERE person = ? AND kind = 'current'",
                (int(person_id),),
            ).fetchone()
            if row is not None and str(row["language"]) in learning:
                return str(row["language"])
        return "he" if "he" in learning or not learning else sorted(learning)[0]

    def use_language(self, person: Person, language: str) -> str:
        """Put this person in a language they are learning. Refuses one they are not."""
        from .translate.prompts import language_name

        code = str(language or "").strip().lower()
        if code not in self.learning(person.id):
            raise ValueError(f"{language_name(code) or 'That'} isn't one of your languages.")
        with self.write() as db:
            db.execute("DELETE FROM chosen WHERE person = ? AND kind = 'current'", (person.id,))
            db.execute(
                "INSERT INTO chosen (person, kind, language, at) VALUES (?, 'current', ?, ?)",
                (person.id, code, now()),
            )
        return code

    def choose(self, person: Person, kind: str, languages: list[str]) -> set[str]:
        """Replace one kind wholesale, which is the shape a form that submits a set wants.

        Refuses rather than repairs: an empty set is not a state a reader can be in,
        because a page with no translation beside the source is not a reader at all,
        and a learner of nothing has nothing to be shown. The sentence raised is the one
        the page shows.
        """
        from .translate.prompts import INTO, READING, REQUIRED_LEARNING, language_name

        if kind == "learning":
            offered = {code for code, _ in READING}
        elif kind == "reading":
            offered = {code for code, _ in INTO}
        else:
            raise ValueError("No such choice.")
        wanted = {str(code or "").strip().lower() for code in languages}
        wanted.discard("")
        strange = sorted(wanted - offered)
        if strange:
            raise ValueError(f"We don't offer {language_name(strange[0])}.")
        if not wanted:
            raise ValueError("Keep at least one language ticked.")
        if kind == "learning" and not wanted >= set(REQUIRED_LEARNING):
            raise ValueError(f"{language_name(REQUIRED_LEARNING[0])} stays on.")
        with self.write() as db:
            db.execute("DELETE FROM chosen WHERE person = ? AND kind = ?", (person.id, kind))
            db.executemany(
                "INSERT INTO chosen (person, kind, language, at) VALUES (?, ?, ?, ?)",
                [(person.id, kind, code, now()) for code in sorted(wanted)],
            )
        return wanted

    def also_learning(self, person_id: int, language: str) -> bool:
        """Add one language to what a person is learning, keeping the rest.

        `choose` replaces a kind wholesale, which is what a form submitting a set wants
        and the wrong shape for this: a reader who says, in Claude, that they would like
        to practise French has said nothing about Hebrew, and a wholesale write would be
        this deciding what they meant about a language they never mentioned.

        **Written where something is already being kept, and nowhere else** (2026-09-23).
        An account set to Hebrew alone refused the request outright — "ton compte Targum
        est configuré pour l'hébreu seulement" — when asking to practise French in your
        own words is the plainest way there is of saying what you are learning. Talking
        is free and writes nothing; it is the first line the reader writes and has kept
        that turns the language on, because that is the first moment anything of theirs
        is recorded, and it happens under the one scope that says it records.

        False when the language is already there or is not one targum offers to learn, so
        a caller can tell a change from a no-op without reading the set back.
        """
        from .translate.prompts import READING

        code = str(language or "").strip().lower()
        if not person_id or code not in {offered for offered, _ in READING}:
            return False
        # What they are learning *now*, which for almost everybody is the default and not
        # a row: `_chosen` answers a person with no rows with `{"he"}`. Inserting one row
        # beside that would turn an implicit Hebrew into an explicit French and drop
        # Hebrew on the way — silently, for every reader who never opened the picker,
        # which is most of them. So the effective set is written down whole, the first
        # time anything is added to it.
        current = self.learning(person_id)
        if code in current:
            return False
        held = {
            str(row["language"])
            for row in self.db.execute(
                "SELECT language FROM chosen WHERE person = ? AND kind = 'learning'",
                (int(person_id),),
            )
        }
        with self.write() as db:
            db.executemany(
                "INSERT INTO chosen (person, kind, language, at) VALUES (?, 'learning', ?, ?)",
                [(int(person_id), one, now()) for one in sorted((current | {code}) - held)],
            )
        return True

    def is_admin(self, email: str) -> bool:
        address = tidy(email)
        if not address:
            return False
        found = self.db.execute("SELECT 1 FROM admin WHERE email = ?", (address,)).fetchone()
        return found is not None

    def may_join(self, email: str) -> bool:
        """Whether this address may open an account here.

        Called only in hosted mode. An empty list therefore means *nobody* rather than
        everybody, which is the safe way round: standing a box up on a public address
        with a funded API key should not, by default, let whoever finds it spend money.
        The first invitation comes from the command line on the box itself, which makes
        having the box the root of the whole thing.
        """
        address = tidy(email)
        if not address:
            return False
        found = self.db.execute("SELECT 1 FROM invited WHERE email = ?", (address,)).fetchone()
        return found is not None

    def is_leaving(self, email: str) -> bool:
        """Whether this address's account is inside its deletion grace period.

        Every door refuses such an account, and each used to say why wrongly — "That
        link no longer works", "targum isn't open yet" — so a person who changed their
        mind was never told how to keep it (copy audit, 2026-09-28)."""
        address = tidy(email)
        if not address:
            return False
        row = self.db.execute("SELECT leaving FROM person WHERE email = ?", (address,)).fetchone()
        return row is not None and row["leaving"] is not None

    def leaving_link(self, token: str) -> bool:
        """Whether this sign-in link would have worked but for its account closing."""
        cutoff = now() - LINK_MINUTES * 60 * 1000
        row = self.db.execute(
            "SELECT 1 FROM link JOIN person ON person.id = link.person "
            "WHERE link.hash = ? AND link.used IS NULL AND link.made >= ? "
            "AND link.purpose = ? AND person.leaving IS NOT NULL",
            (digest(token), cutoff, SIGN_IN),
        ).fetchone()
        return row is not None

    def start_sign_in(self, email: str) -> str:
        """Mint a link for this address, making the account if there is not one.

        Signing up and signing in are the same act on purpose. There is no form to
        fill in, nothing to confirm, and no state where an account half exists.
        """
        address = tidy(email)
        token = secrets.token_urlsafe(TOKEN_BYTES)
        with self.write() as db:
            db.execute(
                "INSERT INTO person (email, made) VALUES (?, ?) ON CONFLICT(email) DO NOTHING",
                (address, now()),
            )
            row = db.execute("SELECT id FROM person WHERE email = ?", (address,)).fetchone()
            # Any link minted earlier is void: asking for a new one is what someone does
            # when the first did not arrive, and two live links is one more than needed.
            db.execute("DELETE FROM link WHERE person = ? AND purpose = ?", (row["id"], SIGN_IN))
            db.execute(
                "INSERT INTO link (hash, person, made, used, purpose) VALUES (?, ?, ?, NULL, ?)",
                (digest(token), row["id"], now(), SIGN_IN),
            )
        return token

    def sign_in_verified(self, email: str) -> tuple[Person, str] | None:
        """Sign in an address somebody else has proved, and hand back a session.

        The mailed link proves an address by sending something to it. A sign-in provider
        proves the same address a different way, and this is where that proof is spent:
        no link is minted, because a token sitting in an inbox is the thing the provider
        was used to avoid.

        **The caller must have verified it.** This makes an account for any address it is
        handed, exactly as `start_sign_in` does, so `serve` checks `may_join` and the
        provider's own `email_verified` before ever reaching here (targum-internal#304).

        None for somebody on their way out, the one refusal `finish_sign_in` also makes:
        a person inside their deletion grace period does not get to sign in again by
        another door.
        """
        address = tidy(email)
        if not address:
            return None
        with self.write() as db:
            db.execute(
                "INSERT INTO person (email, made) VALUES (?, ?) ON CONFLICT(email) DO NOTHING",
                (address, now()),
            )
            row = db.execute(
                "SELECT id, email, leaving FROM person WHERE email = ?", (address,)
            ).fetchone()
            if row is None or row["leaving"] is not None:
                return None
            session = secrets.token_urlsafe(TOKEN_BYTES)
            db.execute(
                "INSERT INTO session (hash, person, made, seen) VALUES (?, ?, ?, ?)",
                (digest(session), row["id"], now(), now()),
            )
        return Person(int(row["id"]), str(row["email"]), self.is_admin(str(row["email"]))), session

    def peek_sign_in(self, token: str) -> Person | None:
        """Who this link would sign in, without spending it.

        The landing page has to say whose account it is before anyone presses the
        button, and reading must not be the thing that consumes the link — that is the
        whole reason the link stopped being a plain GET.
        """
        cutoff = now() - LINK_MINUTES * 60 * 1000
        row = self.db.execute(
            "SELECT person.id AS id, person.email AS email FROM link "
            "JOIN person ON person.id = link.person "
            "WHERE link.hash = ? AND link.used IS NULL AND link.made >= ? "
            "AND link.purpose = ? AND person.leaving IS NULL",
            (digest(token), cutoff, SIGN_IN),
        ).fetchone()
        return Person(row["id"], row["email"], self.is_admin(row["email"])) if row else None

    def finish_sign_in(self, token: str) -> tuple[Person, str] | None:
        """Spend a link and hand back a session. None if it is spent, stale or wrong."""
        cutoff = now() - LINK_MINUTES * 60 * 1000
        with self.write() as db:
            # By purpose: a Telegram link is a bearer token too, and it must never be
            # a way to sign in (targum-internal#328).
            row = db.execute(
                "SELECT person, made, used FROM link WHERE hash = ? AND purpose = ?",
                (digest(token), SIGN_IN),
            ).fetchone()
            if row is None or row["used"] is not None or row["made"] < cutoff:
                return None
            leaving = db.execute(
                "SELECT leaving FROM person WHERE id = ?", (row["person"],)
            ).fetchone()
            if leaving is None or leaving["leaving"] is not None:
                return None
            db.execute("UPDATE link SET used = ? WHERE hash = ?", (now(), digest(token)))
            who = db.execute(
                "SELECT id, email FROM person WHERE id = ?", (row["person"],)
            ).fetchone()
            session = secrets.token_urlsafe(TOKEN_BYTES)
            db.execute(
                "INSERT INTO session (hash, person, made, seen) VALUES (?, ?, ?, ?)",
                (digest(session), who["id"], now(), now()),
            )
        return Person(who["id"], who["email"], self.is_admin(who["email"])), session

    def whoever(self, session: str | None) -> Person | None:
        """The person holding this session, or nobody.

        Touches `seen`, which is what makes a session last as long as it is used.
        """
        if not session:
            return None
        cutoff = now() - SESSION_DAYS * 24 * 60 * 60 * 1000
        row = self.db.execute(
            "SELECT person.id AS id, person.email AS email,"
            " session.seen AS seen"
            " FROM session JOIN person ON person.id = session.person"
            " WHERE session.hash = ?",
            (digest(session),),
        ).fetchone()
        if row is None or row["seen"] < cutoff:
            return None
        # Written at most once a minute: every read of every page would otherwise be a
        # write, and the only thing this timestamp decides is a ninety-day expiry.
        if now() - row["seen"] > 60_000:
            with self.write() as db:
                db.execute("UPDATE session SET seen = ? WHERE hash = ?", (now(), digest(session)))
        return Person(row["id"], row["email"], self.is_admin(row["email"]))

    def sign_out(self, session: str | None) -> None:
        if not session:
            return
        with self.write() as db:
            db.execute("DELETE FROM session WHERE hash = ?", (digest(session),))

    def forget(self, person: Person) -> None:
        """Start forgetting someone. The other half of being allowed to keep it.

        Nothing is deleted yet. They are signed out of everywhere, the account stops
        working, and the data goes at the end of the grace period. Deleting an account
        is one click on a bad day, and the only thing that makes that safe is time.
        """
        with self.write() as db:
            db.execute("UPDATE person SET leaving = ? WHERE id = ?", (now(), person.id))
            db.execute("DELETE FROM session WHERE person = ?", (person.id,))
            db.execute("DELETE FROM link WHERE person = ?", (person.id,))
            # And every Telegram chat, for the same reason: a bound chat is a way to
            # build on the account, from a phone somewhere else.
            db.execute("DELETE FROM telegram WHERE person = ?", (person.id,))
            # And every connector. Signed out of everywhere has to mean everywhere, and
            # a token left live would be a way into an account that has asked to end —
            # from a client on somebody else's machine, which is worse than a cookie.
            db.execute("DELETE FROM oauth_token WHERE person = ?", (person.id,))
            db.execute("DELETE FROM oauth_grant WHERE person = ?", (person.id,))
            # And what they wrote for it. Their words, so they go with them.
            db.execute("DELETE FROM prompt WHERE person = ?", (person.id,))
            # And the lists they kept. Their choices, so they go with them.
            db.execute(
                "DELETE FROM playlist_item WHERE playlist IN"
                " (SELECT id FROM playlist WHERE person = ?)",
                (person.id,),
            )
            db.execute("DELETE FROM playlist WHERE person = ?", (person.id,))
            # And what they subscribed to: nothing more is built or mailed for them.
            db.execute(
                "DELETE FROM sub_item WHERE subscription IN"
                " (SELECT id FROM subscription WHERE person = ?)",
                (person.id,),
            )
            db.execute("DELETE FROM subscription WHERE person = ?", (person.id,))
            # The weekly stops too. A subscription is deliberately not part of the
            # account — it outlives one, and that is the point of keeping it in its own
            # table — but somebody who asked to be forgotten did not mean "keep mailing
            # me". Reversed by subscribing again, which they can do without an account.
            db.execute(
                "UPDATE subscriber SET state = 'off', ended = ? WHERE email = ?",
                (now(), person.email),
            )

    def stay(self, person: Person) -> None:
        """Change their mind, while there is still something to change it about."""
        with self.write() as db:
            db.execute("UPDATE person SET leaving = NULL WHERE id = ?", (person.id,))

    def purge(self, days: int = GRACE_DAYS) -> list[int]:
        """Delete everyone whose grace period is up, and say whose files still stand.

        The store knows nothing about the output directory, so the rows go here and the
        ids come back for the caller to finish the job on disk.
        """
        cutoff = now() - days * 24 * 60 * 60 * 1000
        with self.write() as db:
            rows = db.execute(
                "SELECT id FROM person WHERE leaving IS NOT NULL AND leaving < ?", (cutoff,)
            ).fetchall()
            gone = [int(row["id"]) for row in rows]
            for person_id in gone:
                for table in (
                    "word",
                    "meaning",
                    "phrase",
                    "doc",
                    "day",
                    # Which chapters they finished. Missing from this list until
                    # 2026-09-20, so those rows outlived the account they belonged to;
                    # found while adding the one below.
                    "section",
                    # And what they knew of each one (targum-internal#291).
                    "reading",
                    # And where they left off in each text (targum-internal#430).
                    "place",
                    # And what they did in each text (targum-internal#127).
                    "event",
                    "chosen",
                    "session",
                    "link",
                    "telegram",
                    # What they got wrong is theirs too (targum-internal#290), and it is
                    # the most personal row in the database: a record of a learner's own
                    # mistakes, in their own sentences.
                    "slip",
                ):
                    db.execute(f"DELETE FROM {table} WHERE person = ?", (person_id,))
                # Conversations too: half of every one is what the person said.
                db.execute(
                    "DELETE FROM chat_turn WHERE chat IN (SELECT id FROM chat WHERE person = ?)",
                    (person_id,),
                )
                db.execute("DELETE FROM chat WHERE person = ?", (person_id,))
                db.execute(
                    "DELETE FROM sub_item WHERE subscription IN"
                    " (SELECT id FROM subscription WHERE person = ?)",
                    (person_id,),
                )
                db.execute("DELETE FROM subscription WHERE person = ?", (person_id,))
                db.execute("DELETE FROM person WHERE id = ?", (person_id,))
        return gone

    # -- syncing ----------------------------------------------------------------

    def _next_revision(self, db: sqlite3.Connection, person: Person) -> int:
        db.execute("UPDATE person SET revision = revision + 1 WHERE id = ?", (person.id,))
        row = db.execute("SELECT revision FROM person WHERE id = ?", (person.id,)).fetchone()
        return int(row["revision"])

    def revision(self, person: Person) -> int:
        row = self.db.execute("SELECT revision FROM person WHERE id = ?", (person.id,)).fetchone()
        return int(row["revision"]) if row else 0

    @staticmethod
    def _bump_ledger(db: sqlite3.Connection, person_id: int) -> None:
        db.execute("UPDATE person SET ledger = ledger + 1 WHERE id = ?", (person_id,))

    def ledger_stamp(self, person_id: int | None) -> tuple[int, int, int] | None:
        """What changes whenever anything a reader's record says changes, or None.

        The connector's answers are worked out from the record — the words, what they
        finished, the days they read, their slips, the rung and address they named — and
        kept under this (`chat.tools`, 2026-10-06), so this has to move on every write to
        any of it. `revision` already does for everything a sync writes, which is the
        words and the rest of `KINDS`; `ledger` is bumped by the few writes that are not a
        sync (`_bump_ledger` and the statements beside it). `made` is there because an
        `INTEGER PRIMARY KEY` can be given again to a person made after the last one was
        deleted, and that person's zero counters must not be the old one's.

        Read from the database rather than counted in memory, so a write made by another
        process — the command line, a second server — moves it too. One row, by its key.
        """
        if person_id is None:
            return None
        row = self.db.execute(
            "SELECT made, revision, ledger FROM person WHERE id = ?", (int(person_id),)
        ).fetchone()
        if row is None:
            return None
        return (int(row["made"]), int(row["revision"]), int(row["ledger"]))

    def push(
        self,
        person: Person,
        changes: dict[str, list[dict[str, Any]]],
        *,
        word_cap: int | None = None,
    ) -> int:
        """Take a browser's changes, keeping whichever version of each record is newer.

        Everything lands in one transaction and under one revision number, so a client
        pulling at the same moment sees either all of a push or none of it. Half a
        push is how a phrase arrives without the document it belongs to.

        `word_cap` is a free word list's (design.md §12, "Free and Plan, behind a switch",
        2026-10-09): a word that would go on the list — into stages 1 to 3 from anywhere
        else — once it already holds that many is not taken. A word already on it moves
        between stages freely, and known or ignored are never held. None, as it is with
        plans off, takes everything as it always did.
        """
        with self.write() as db:
            stamp = self._next_revision(db, person)
            for name, items in changes.items():
                kind = KINDS.get(name)
                if kind is None:
                    continue
                for item in items:
                    if (
                        word_cap is not None
                        and name == "words"
                        and self._over_cap(db, person, item, word_cap)
                    ):
                        continue
                    self._merge(db, person, kind, item, stamp)
            return stamp

    @staticmethod
    def _over_cap(db: sqlite3.Connection, person: Person, item: dict[str, Any], cap: int) -> bool:
        """Whether this word would go on a list already holding `cap` words."""
        try:
            status = int(item.get("status"))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return False
        if item.get("gone") or status not in LISTED:
            return False
        was = db.execute(
            "SELECT status, gone FROM word WHERE person = ? AND language = ? AND lemma = ?",
            (person.id, str(item.get("language") or ""), str(item.get("lemma") or "")),
        ).fetchone()
        if was is not None and not was["gone"] and was["status"] in LISTED:
            return False
        held = db.execute(
            "SELECT COUNT(*) AS n FROM word WHERE person = ? AND gone = 0 AND status IN (1, 2, 3)",
            (person.id,),
        ).fetchone()
        return int(held["n"]) >= cap

    def listed_words(self, person_id: int) -> int:
        """How many words this reader is learning (stages 1 to 3), across every language:
        what a free word list's cap counts."""
        row = self.db.execute(
            "SELECT COUNT(*) AS n FROM word WHERE person = ? AND gone = 0 AND status IN (1, 2, 3)",
            (person_id,),
        ).fetchone()
        return int(row["n"])

    def _merge(
        self,
        db: sqlite3.Connection,
        person: Person,
        kind: Kind,
        item: dict[str, Any],
        stamp: int,
    ) -> None:
        key = tuple(str(item.get(name, "")) for name in kind.key)
        if not all(key):
            return  # a record with no name is not a record
        seen = int(item.get("seen") or item.get("at") or 0)
        where = " AND ".join(f"{name} = ?" for name in kind.key)
        existing = db.execute(
            f"SELECT * FROM {kind.table} WHERE person = ? AND {where}", (person.id, *key)
        ).fetchone()
        # The whole of the merge rule, in one line: an older edit does not overwrite a
        # newer one, whichever browser it came from and whichever order they arrive in.
        if existing is not None and int(existing["seen"]) >= seen:
            return

        # A field the push does not mention keeps whatever is already stored, rather
        # than reverting to a default. Clients send whole records, so this should never
        # fire — but the cost of being wrong about that is a browser quietly erasing a
        # meaning somebody typed on another device, and the cost of the guard is a
        # dictionary lookup.
        def value(name: str) -> Any:
            if name in item:
                return item[name]
            if existing is not None:
                return existing[name]
            return None if name == "status" else (0 if name in NUMERIC else "")

        columns = ["person", *kind.key, *kind.fields, "seen", "gone", "revision"]
        row = [
            person.id,
            *key,
            *(value(name) for name in kind.fields),
            seen,
            1 if item.get("gone") else 0,
            stamp,
        ]
        marks = ", ".join("?" for _ in columns)
        db.execute(
            f"INSERT OR REPLACE INTO {kind.table} ({', '.join(columns)}) VALUES ({marks})",
            row,
        )

    def pull(self, person: Person, since: int = 0) -> dict[str, Any]:
        """Everything that changed after `since`, and the revision that reaches.

        A client that has never synced passes 0 and gets the lot. One that synced a
        minute ago passes what it got back then and gets almost nothing, which is what
        makes it reasonable to do this on every page load.
        """
        out: dict[str, Any] = {"revision": self.revision(person)}
        for name, kind in KINDS.items():
            columns = [*kind.key, *kind.fields, "seen", "gone"]
            rows = self.db.execute(
                f"SELECT {', '.join(columns)} FROM {kind.table}"
                " WHERE person = ? AND revision > ? ORDER BY revision",
                (person.id, since),
            ).fetchall()
            out[name] = [dict(row) for row in rows]
        return out

    def everything(self, person: Person) -> dict[str, Any]:
        """Everything targum holds about one person, for them to take away.

        The point is that it needs nobody's help: somebody who wants their data should
        not have to ask the person who runs the server for it.

        Complete except for one deliberate omission. Sessions and sign-in links are
        credentials, not data — writing them into a file somebody downloads, mails to
        themselves and leaves in a downloads folder would be handing out live keys to
        their own account. What is here is everything they wrote or caused. The same
        line divides a connector: *that* they connected Claude, with which scopes and
        when, is a fact about them and is here; the token is a credential and is not.

        Everything the account keeps goes through `KINDS`, and this loops `KINDS` rather
        than naming tables, so a kind added tomorrow is exported tomorrow without anyone
        remembering to add it here. The days somebody read on are one of them: the
        progress page is a view of these same records, drawn in the browser, and holds
        nothing of its own — so what is here is what that page is made of, and a count
        it shows tomorrow that is not derivable from this is a bug there, not here. The
        nightly copy (`backup.py`) is the other half of the same promise and needs no
        list at all: it takes the database whole.
        """
        account = self.db.execute(
            "SELECT email, name, picture, made FROM person WHERE id = ?", (person.id,)
        ).fetchone()
        out: dict[str, Any] = {
            "account": {
                "email": account["email"],
                "joined": account["made"],
                # What they asked to be called and what they chose to show. Theirs in
                # the plainest sense: they typed it.
                "name": account["name"],
                "picture": account["picture"],
            },
            # What they said about their languages — which they are learning, which they
            # read — as the rows they wrote, not the defaulted sets `learning()` and
            # `reads()` compute. The export is what somebody said, not what targum
            # assumed on their behalf when they had said nothing.
            "languages": [
                dict(row)
                for row in self.db.execute(
                    "SELECT kind, language, at FROM chosen WHERE person = ?"
                    " ORDER BY kind, language",
                    (person.id,),
                )
            ],
            "exported": now(),
        }
        for name, kind in KINDS.items():
            columns = [*kind.key, *kind.fields, "seen"]
            rows = self.db.execute(
                f"SELECT {', '.join(columns)} FROM {kind.table}"
                " WHERE person = ? AND gone = 0 ORDER BY at DESC"
                if "at" in kind.fields
                else f"SELECT {', '.join(columns)} FROM {kind.table} WHERE person = ? AND gone = 0",
                (person.id,),
            ).fetchall()
            out[name] = [dict(row) for row in rows]

        # What they got wrong, in their own sentences (targum-internal#290). The most
        # personal rows in the database, so the first thing that had to be true of them
        # is that somebody can take them away.
        out["slips"] = self.slips(person.id, limit=100_000)

        # What they said to targum and what it said back. Theirs in the plainest sense.
        out["chats"] = [
            {
                **chat,
                "turns": [
                    {"role": turn["role"], "said": turn["said"], "made": turn["made"]}
                    for turn in self.chat_turns(str(chat["id"]))
                    if turn["said"]
                ],
            }
            for chat in self.chats(person.id)
        ]
        # What they built, and what it cost. Theirs as much as their words are, and the
        # only place the spend is written down.
        out["builds"] = [
            dict(row)
            for row in self.db.execute(
                "SELECT source, title, language, stage, spent, made FROM job"
                " WHERE owner = ? AND kind IN ('build', 'subscription') ORDER BY made DESC",
                (person.id,),
            )
        ]
        # Which clients they connected, and what they let each one do. The digests stay
        # out, for the reason at the top of this method.
        out["connections"] = self.connections(person.id)
        # What they subscribed to, and its cap: their choices, as their playlists are. The
        # stop token stays out — it is a way to change the row, not a fact about it.
        out["subscriptions"] = [
            {
                key: row[key]
                for key in ("kind", "key", "name", "language", "source", "cap", "state", "since")
            }
            for row in self.subscriptions(person.id, every=True)
        ]
        # And what they wrote for those clients to offer. Theirs in the plainest sense:
        # they typed it.
        out["prompts"] = self.prompts(person.id)
        # And what they knew of each section they finished, as it was measured then
        # (targum-internal#291). Derived, but not derivable later: the ledger it was
        # measured against has moved on since.
        out["readings"] = self.readings(person.id)
        # And the Telegram chats they bound (targum-internal#328): which, and since when.
        out["telegram"] = self.telegram_chats(person.id)
        # And the lists they kept, each with what is in it.
        out["playlists"] = [
            self.playlist(person.id, int(one["id"])) for one in self.playlists(person.id)
        ]
        return out

    # -- what a reader knew of what they read (targum-internal#291) ----------------

    def unmeasured(self, person: Person, rows: list[dict[str, Any]]) -> list[tuple[str, str]]:
        """Which finished sections in a push have no reading row yet, as (hash, section).

        A section un-finished travels as a `gone` row and is not a finish; one finished
        before, and finished again, already has its row and is left alone.
        """
        out: list[tuple[str, str]] = []
        for row in rows:
            hash_, section = str(row.get("hash") or ""), str(row.get("section") or "")
            if not hash_ or not section or row.get("gone") or (hash_, section) in out:
                continue
            had = self.db.execute(
                "SELECT 1 FROM reading WHERE person = ? AND hash = ? AND section = ?",
                (person.id, hash_, section),
            ).fetchone()
            if had is None:
                out.append((hash_, section))
        return out

    def keep_reading(
        self,
        person: Person,
        language: str,
        at: int,
        hash_: str,
        section: str,
        tokens: int,
        known: int,
    ) -> bool:
        """Keep one finished section's measurement, unless it is already kept.

        `INSERT OR IGNORE`, never a replace: the first measurement is the one that was
        true that day, and a later one would be today's ledger passed off as then's.
        Whether a row was written, so the caller can tell a first finish from another.
        """
        with self.write() as db:
            done = db.execute(
                "INSERT OR IGNORE INTO reading"
                " (person, language, at, hash, section, tokens, known)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    person.id,
                    language.split("-")[0].lower(),
                    int(at),
                    hash_,
                    section,
                    int(tokens),
                    int(known),
                ),
            )
            return bool(done.rowcount)

    def readings(self, person_id: int | None, language: str = "") -> list[dict[str, Any]]:
        """Every kept measurement, oldest first; one language's where one is named."""
        if person_id is None:
            return []
        query = "SELECT language, at, hash, section, tokens, known FROM reading WHERE person = ?"
        values: list[Any] = [person_id]
        if language:
            query += " AND language = ?"
            values.append(language.split("-")[0].lower())
        rows = self.db.execute(query + " ORDER BY at", values).fetchall()
        return [dict(row) for row in rows]

    def finished(self, person_id: int | None) -> list[tuple[str, str, int]]:
        """Every section this person has finished and not un-finished, as (document hash,
        section, at), oldest first — what `occurrences.met` calls meeting a word."""
        if person_id is None:
            return []
        rows = self.db.execute(
            "SELECT hash, section, at FROM section WHERE person = ? AND gone = 0 ORDER BY at",
            (person_id,),
        ).fetchall()
        return [(str(row["hash"]), str(row["section"]), int(row["at"] or 0)) for row in rows]

    def finished_sections(self, person_id: int | None, document: str) -> set[str]:
        """The sections of one text this person has finished and not un-finished — what a
        contents page checks as Read or Watched."""
        if person_id is None or not document:
            return set()
        rows = self.db.execute(
            "SELECT section FROM section WHERE person = ? AND hash = ? AND gone = 0",
            (person_id, document),
        ).fetchall()
        return {str(row["section"]) for row in rows}

    def marked(self, person: Person, language: str) -> dict[str, int]:
        """Every dictionary form this person has marked in one language, and how well.

        One query per language rather than one per text: a shelf of twenty books in Hebrew
        asks this once and measures all twenty against the answer.
        """
        rows = self.db.execute(
            "SELECT lemma, status FROM word WHERE person = ? AND language = ? AND gone = 0",
            (person.id, language.split("-")[0].lower()),
        )
        return {row["lemma"]: row["status"] for row in rows if row["status"] is not None}

    def meanings(self, person: Person, language: str) -> list[tuple[str, str, int | None]]:
        """Every word this person keeps in one language, with the meaning they wrote for
        it and how well they know it: what search meets English against, since an
        English line finds a word only on the reader's own list (design.md §12, "One
        search, everywhere", 2026-10-09)."""
        rows = self.db.execute(
            "SELECT lemma, meaning, status FROM word WHERE person = ? AND language = ?"
            " AND gone = 0",
            (person.id, language.split("-")[0].lower()),
        )
        return [(str(row["lemma"]), str(row["meaning"] or ""), row["status"]) for row in rows]

    def counts(self, person: Person) -> dict[str, int]:
        """What someone has, for the sake of saying so on the page."""
        out = {}
        for name, kind in KINDS.items():
            row = self.db.execute(
                f"SELECT COUNT(*) AS n FROM {kind.table} WHERE person = ? AND gone = 0",
                (person.id,),
            ).fetchone()
            out[name] = int(row["n"])
        return out

    def words_with_bands(
        self, person_id: int | None, language: str
    ) -> list[tuple[str, int | None, str, int]]:
        """Every word in one language with its status, band and when it was marked —
        what the ulpan ladder in `level.py` weighs."""
        if person_id is None:
            return []
        rows = self.db.execute(
            "SELECT lemma, status, band, at FROM word"
            " WHERE person = ? AND language = ? AND gone = 0",
            (person_id, language.split("-")[0].lower()),
        )
        return [
            (str(row["lemma"]), row["status"], str(row["band"] or ""), int(row["at"] or 0))
            for row in rows
        ]

    def known_forms(self, person_id: int | None, language: str) -> set[str]:
        """Every form the reader has marked known — the dictionary form and the surface
        it was met in — bare of points, for the cheap known-share estimate
        (`level.known_share`, targum-internal#244)."""
        if person_id is None:
            return set()
        from .vocalize.base import strip_nikkud

        rows = self.db.execute(
            "SELECT lemma, surface FROM word"
            " WHERE person = ? AND language = ? AND gone = 0 AND status = 9",
            (person_id, language.split("-")[0].lower()),
        )
        out: set[str] = set()
        for row in rows:
            for form in (row["lemma"], row["surface"]):
                if form:
                    out.add(strip_nikkud(str(form))[0])
        return out

    def kept_between(
        self,
        person_id: int | None,
        start: int,
        end: int,
        *,
        languages: Iterable[str],
        target: str,
    ) -> list[Kept]:
        """The words a reader first kept between two moments (ms), still learning, in the
        order they were kept — the week's sheet's list where there are no look-ups to read
        (targum-internal#105): the record is off, stopped, or older than the word it carries.

        A word kept this week and since marked known, or ignored, is not one to carry into
        Shabbat. Names and numbers are not vocabulary. The meaning is the one in `target`,
        the language the sheet is read in.
        """
        codes = sorted({code.split("-")[0].lower() for code in languages})
        if person_id is None or not codes:
            return []
        marks = ", ".join("?" for _ in codes)
        rows = self.db.execute(
            "SELECT w.language, w.lemma, w.surface, w.note AS own, w.meaning AS said,"
            " m.note AS note, m.meaning AS meaning FROM word w"
            " LEFT JOIN meaning m ON m.person = w.person AND m.source = w.language"
            " AND m.target = ? AND m.term = w.lemma AND m.gone = 0"
            " WHERE w.person = ? AND w.gone = 0 AND w.status IN (1, 2, 3)"
            " AND w.at >= ? AND w.at < ? AND w.band NOT IN ('name', 'number')"
            f" AND w.language IN ({marks}) ORDER BY w.at",
            (target.split("-")[0].lower(), int(person_id), int(start), int(end), *codes),
        ).fetchall()
        return [_kept(row) for row in rows]

    def learning_words(
        self, person_id: int | None, *, languages: Iterable[str], target: str
    ) -> dict[str, tuple[int, str]]:
        """Every word the reader is learning — steps 1 to 3, the reader's marks — by its
        dictionary form and the form they met it in, bare of points, with the step and the
        meaning they keep for it in `target`, as `kept_between` gives one ("" where they
        keep none). What the week's sheet lights (targum-internal#415). Names and numbers
        are not vocabulary."""
        codes = sorted({code.split("-")[0].lower() for code in languages})
        if person_id is None or not codes:
            return {}
        from .vocalize.base import strip_nikkud

        marks = ", ".join("?" for _ in codes)
        rows = self.db.execute(
            "SELECT w.language, w.lemma, w.surface, w.status, w.note AS own,"
            " w.meaning AS said, m.note AS note, m.meaning AS meaning FROM word w"
            " LEFT JOIN meaning m ON m.person = w.person AND m.source = w.language"
            " AND m.target = ? AND m.term = w.lemma AND m.gone = 0"
            " WHERE w.person = ? AND w.gone = 0 AND w.status IN (1, 2, 3)"
            " AND (w.band IS NULL OR w.band NOT IN ('name', 'number'))"
            f" AND w.language IN ({marks})",
            (target.split("-")[0].lower(), int(person_id), *codes),
        ).fetchall()
        out: dict[str, tuple[int, str]] = {}
        for row in rows:
            kept = _kept(row)
            for form in (kept.lemma, kept.surface):
                bare = strip_nikkud(form)[0] if form else ""
                if bare and bare not in out:
                    out[bare] = (int(row["status"]), kept.meaning)
        return out

    def looked_up_between(
        self,
        person_id: int | None,
        start: int,
        end: int,
        *,
        languages: Iterable[str],
        target: str,
    ) -> list[Kept]:
        """The words a reader looked up between two moments (ms), once each, in the order
        they were first looked up — what the week's sheet lists (targum-internal#105).

        Read off the event log's look-ups, which name their word since 2026-09-28; one
        recorded before that, or by a box that keeps no record, names none and is not here.
        A word looked up and then marked known, or ignored, has been answered already, and
        a name or a number is not vocabulary, where the ledger says so. The meaning is the
        reader's in `target`, as `kept_between` gives it.
        """
        codes = sorted({code.split("-")[0].lower() for code in languages})
        if person_id is None or not codes:
            return []
        marks = ", ".join("?" for _ in codes)
        rows = self.db.execute(
            "SELECT e.language AS language, e.word AS lemma, MIN(e.at) AS first,"
            " COALESCE(w.surface, '') AS surface, w.note AS own, w.meaning AS said,"
            " m.note AS note, m.meaning AS meaning FROM event e"
            " LEFT JOIN word w ON w.person = e.person AND w.language = e.language"
            " AND w.lemma = e.word AND w.gone = 0"
            " LEFT JOIN meaning m ON m.person = e.person AND m.source = e.language"
            " AND m.target = ? AND m.term = e.word AND m.gone = 0"
            " WHERE e.person = ? AND e.kind = 'lookup' AND e.word <> ''"
            " AND e.at >= ? AND e.at < ?"
            f" AND e.language IN ({marks})"
            " AND (w.status IS NULL OR w.status IN (1, 2, 3))"
            " AND COALESCE(w.band, '') NOT IN ('name', 'number')"
            " GROUP BY e.language, e.word ORDER BY first",
            (target.split("-")[0].lower(), int(person_id), int(start), int(end), *codes),
        ).fetchall()
        return [_kept(row) for row in rows]

    def activity(self, person_id: int | None) -> dict[str, Any]:
        """The days someone read on, and how many sections and texts they finished."""
        if person_id is None:
            return {"days": [], "sections": 0, "texts": 0}
        days = [
            str(row["day"])
            for row in self.db.execute(
                "SELECT day FROM day WHERE person = ? AND gone = 0 ORDER BY day", (person_id,)
            )
        ]
        sections = self.db.execute(
            "SELECT COUNT(*) AS n FROM section WHERE person = ? AND gone = 0", (person_id,)
        ).fetchone()
        texts = self.db.execute(
            "SELECT COUNT(*) AS n FROM doc WHERE person = ? AND gone = 0 AND done > 0",
            (person_id,),
        ).fetchone()
        return {"days": days, "sections": int(sections["n"]), "texts": int(texts["n"])}

    def opened_documents(self, person_id: int | None) -> set[str]:
        """The hashes of every text this person has had open, on any device.

        `doc` is written by the reader's own sync, so this is the one place the server
        can tell which of the shared shelf a reader has actually read — the shelf itself
        is the same folder for everybody.
        """
        if person_id is None:
            return set()
        rows = self.db.execute(
            "SELECT hash FROM doc WHERE person = ? AND gone = 0 AND opened > 0",
            (person_id,),
        ).fetchall()
        return {str(row["hash"]) for row in rows}

    #: The most places one read hands back. Home shows a few; the rest is the export's.
    PLACES_AT_MOST = 20

    def places(
        self, person_id: int | None, limit: int = 5, document: str = ""
    ) -> list[dict[str, Any]]:
        """Where this person left off, newest first: the last `limit` texts they were in,
        each with the part, the sentence and the second of its recording, and the
        title and language its `doc` row carries (targum-internal#430).

        For Continue — the contents page asks for one text's, home for the last few. A
        text taken off the shelf is left out; its place stays, so putting it back
        brings it back where it was.
        """
        if person_id is None:
            return []
        limit = max(1, min(self.PLACES_AT_MOST, int(limit)))
        where = "p.person = ? AND p.gone = 0 AND COALESCE(d.gone, 0) = 0"
        args: list[Any] = [person_id]
        if document:
            where += " AND p.hash = ?"
            args.append(document)
        rows = self.db.execute(
            "SELECT p.hash, p.section, p.path, p.segment, p.seconds, p.at,"
            " COALESCE(d.title, '') AS title, COALESCE(d.language, '') AS language"
            " FROM place p LEFT JOIN doc d ON d.person = p.person AND d.hash = p.hash"
            f" WHERE {where} ORDER BY p.at DESC LIMIT ?",
            (*args, limit),
        ).fetchall()
        return [dict(row) for row in rows]

    def read_times(self, person_id: int | None) -> dict[str, dict[str, int]]:
        """When this person last opened each text and when they finished it, by hash, in
        the milliseconds the page clocks them in. `doc.opened` is written by the reader
        on every open and synced from every device, so it is the shelf's own clock; a
        text opened on no device is left out. `finished` is the later of `doc.done` and
        the last chapter finished, because a targum finishes a chapter at a time."""
        if person_id is None:
            return {}
        rows = self.db.execute(
            "SELECT d.hash, d.opened, d.done, COALESCE(MAX(s.at), 0) AS chapter"
            " FROM doc d LEFT JOIN section s"
            " ON s.person = d.person AND s.hash = d.hash AND s.gone = 0"
            " WHERE d.person = ? AND d.gone = 0 AND d.opened > 0"
            " GROUP BY d.hash",
            (person_id,),
        ).fetchall()
        return {
            str(row["hash"]): {
                "opened": int(row["opened"]),
                "finished": max(int(row["done"] or 0), int(row["chapter"] or 0)),
            }
            for row in rows
        }

    def hours_used(self, owner: int | None, month_from: int) -> float:
        """Seconds of recording this person's builds have spent since a moment — the
        same sum `claim` holds them to, read without claiming anything."""
        row = self.db.execute(
            "SELECT COALESCE(SUM(length), 0) AS used FROM job "
            "WHERE length > 0 AND made >= ? AND owner IS ?",
            (month_from, owner),
        ).fetchone()
        return float(row["used"])

    # -- conversations ----------------------------------------------------------

    def chat_seconds(self, chat_id: str) -> float:
        """How long one conversation has run, in the seconds its turns were metered in:
        the same `length` the allowance is kept in, summed over this conversation's
        rows and nobody else's."""
        row = self.db.execute(
            "SELECT COALESCE(SUM(length), 0) AS used FROM job WHERE source = ? AND kind = 'chat'",
            (f"chat:{chat_id}",),
        ).fetchone()
        return float(row["used"])

    def recent_phrases(self, person_id: int | None, since: int, limit: int = 6) -> list[str]:
        """The phrases this person kept most recently, newest first."""
        if person_id is None:
            return []
        rows = self.db.execute(
            "SELECT text FROM phrase WHERE person = ? AND gone = 0 AND at >= ? AND text != ''"
            " ORDER BY at DESC LIMIT ?",
            (person_id, since, limit),
        ).fetchall()
        return [str(row["text"]) for row in rows]

    def chat_open(self, person_id: int | None, language: str = "he", mode: str = "talk") -> str:
        """Start a conversation. Its id is a bearer token in the sense a job's is:
        unguessable, and still checked against the asker on every read."""
        chat_id = secrets.token_urlsafe(9)
        with self.write() as db:
            db.execute(
                "INSERT INTO chat (id, person, language, made, seen, mode)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (chat_id, person_id, language, now(), now(), mode if mode in MODES else "find"),
            )
        return chat_id

    def chats(
        self, person_id: int | None, limit: int = 50, offset: int = 0, language: str = ""
    ) -> list[dict[str, Any]]:
        """Somebody's conversations, most recent first, a page at a time — in one
        language where one is named, since each language has its own (2026-09-13)."""
        rows = self.db.execute(
            "SELECT chat.id, chat.title, chat.language, chat.made, chat.seen, chat.spent,"
            "       chat.saved, chat.mode, chat.opened,"
            "       (SELECT COUNT(*) FROM chat_turn"
            "         WHERE chat_turn.chat = chat.id AND said != '') AS turns,"
            # When targum last finished answering, so the bell can say an answer arrived
            # while the person was away (2026-09-11): later than `opened`, it did.
            "       (SELECT COALESCE(MAX(made), 0) FROM chat_turn"
            "         WHERE chat_turn.chat = chat.id AND role = 'assistant'"
            "         AND stage = 'done') AS answered"
            " FROM chat WHERE person IS ? AND gone = 0 AND (? = '' OR chat.language = ?)"
            " ORDER BY seen DESC LIMIT ? OFFSET ?",
            (person_id, language, language, limit, offset),
        ).fetchall()
        return [dict(row) for row in rows]

    def chat_opened(self, chat_id: str) -> None:
        """The person opened this conversation now."""
        with self.write() as db:
            db.execute("UPDATE chat SET opened = ? WHERE id = ?", (now(), chat_id))

    def chat_owned(self, person_id: int | None, chat_id: str) -> dict[str, Any] | None:
        """One conversation, but only if it is the asker's."""
        row = self.db.execute(
            "SELECT id, person, title, language, made, seen, spent, saved, mode FROM chat"
            " WHERE id = ? AND person IS ? AND gone = 0",
            (chat_id, person_id),
        ).fetchone()
        return dict(row) if row else None

    def chat_said(self, chat_id: str, n: int) -> str:
        """What was said on one turn, as it was said. Empty where there is no such turn.

        `chat_turns` reads a whole conversation to answer this, which is the right shape
        for drawing one and the wrong one for asking about a single line as it lands.
        """
        row = self.db.execute(
            "SELECT said FROM chat_turn WHERE chat = ? AND n = ?", (chat_id, n)
        ).fetchone()
        return str(row["said"]) if row else ""

    def chat_turns(self, chat_id: str) -> list[dict[str, Any]]:
        """Every API message in a conversation, in order, content decoded."""
        rows = self.db.execute(
            "SELECT n, role, content, said, stage, error, spent, made, words FROM chat_turn"
            " WHERE chat = ? ORDER BY n",
            (chat_id,),
        ).fetchall()
        out: list[dict[str, Any]] = []
        for row in rows:
            turn = dict(row)
            try:
                turn["content"] = json.loads(str(row["content"]))
            except json.JSONDecodeError:
                turn["content"] = str(row["content"])
            # The words of the answer to this turn, or None where none were read.
            try:
                turn["words"] = json.loads(str(row["words"])) if row["words"] else None
            except json.JSONDecodeError:
                turn["words"] = None
            out.append(turn)
        return out

    def chat_say(
        self,
        chat_id: str,
        role: str,
        content: str | list[dict[str, Any]],
        said: str,
        *,
        stage: str = "done",
    ) -> int:
        """Append one API message and return its place. The first thing the reader said
        names the conversation until somebody renames it."""
        stored = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
        with self.write() as db:
            last = db.execute(
                "SELECT COALESCE(MAX(n), 0) AS n FROM chat_turn WHERE chat = ?", (chat_id,)
            ).fetchone()
            n = int(last["n"]) + 1
            db.execute(
                "INSERT INTO chat_turn (chat, n, role, content, said, stage, made)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (chat_id, n, role, stored, said, stage, now()),
            )
            db.execute("UPDATE chat SET seen = ? WHERE id = ?", (now(), chat_id))
            if role == "user" and said:
                db.execute(
                    "UPDATE chat SET title = ? WHERE id = ? AND title = ''",
                    (said.strip().splitlines()[0][:60], chat_id),
                )
        return n

    def chat_turn_update(
        self,
        chat_id: str,
        n: int,
        *,
        stage: str | None = None,
        error: str | None = None,
        spent: float | None = None,
        words: str | None = None,
    ) -> None:
        sets = []
        values: list[Any] = []
        for column, value in (
            ("stage", stage),
            ("error", error),
            ("spent", spent),
            ("words", words),
        ):
            if value is not None:
                sets.append(f"{column} = ?")
                values.append(value)
        if not sets:
            return
        with self.write() as db:
            db.execute(
                f"UPDATE chat_turn SET {', '.join(sets)} WHERE chat = ? AND n = ?",
                (*values, chat_id, n),
            )

    def chat_title(self, chat_id: str) -> str:
        row = self.db.execute("SELECT title FROM chat WHERE id = ?", (chat_id,)).fetchone()
        return str(row["title"]) if row else ""

    def chat_saved(self, chat_id: str, saved: str) -> None:
        """Which build this conversation was written down as, once it has been."""
        with self.write() as db:
            db.execute("UPDATE chat SET saved = ? WHERE id = ?", (saved, chat_id))

    def chat_add_spent(self, chat_id: str, spent: float) -> None:
        with self.write() as db:
            db.execute("UPDATE chat SET spent = spent + ? WHERE id = ?", (spent, chat_id))

    # -- the shelf's door ---------------------------------------------------------

    def propose(self, fields: dict[str, Any]) -> None:
        columns = ", ".join(fields)
        holes = ", ".join("?" for _ in fields)
        with self.write() as db:
            db.execute(f"INSERT INTO proposed ({columns}) VALUES ({holes})", tuple(fields.values()))

    def proposals(self, state: str = "proposed") -> list[dict[str, Any]]:
        rows = self.db.execute(
            "SELECT * FROM proposed WHERE state = ? ORDER BY made DESC", (state,)
        ).fetchall()
        return [dict(row) for row in rows]

    def proposal(self, proposal_id: str) -> dict[str, Any] | None:
        row = self.db.execute("SELECT * FROM proposed WHERE id = ?", (proposal_id,)).fetchone()
        return dict(row) if row else None

    def proposal_state(self, proposal_id: str, state: str, by: str) -> None:
        with self.write() as db:
            db.execute(
                "UPDATE proposed SET state = ?, by = ? WHERE id = ?", (state, by, proposal_id)
            )

    # --- corrections (targum-internal#164, door 1) ---------------------------------

    def grant(self, person_id: int) -> None:
        """Record that this reader accepted the contribution grant (#164, door 3).

        The sentence lives in `CONTRIBUTING.md`; this records that they met it. It gates
        the *control* and not the recording: a reader who has not accepted is never shown
        a way to offer a correction, so there is nothing to refuse later.
        """
        with self.write() as db:
            db.execute("UPDATE person SET granted = ? WHERE id = ?", (now(), person_id))

    def has_granted(self, person_id: int) -> bool:
        row = self.db.execute("SELECT granted FROM person WHERE id = ?", (person_id,)).fetchone()
        return bool(row and int(row["granted"] or 0))

    def propose_correction(self, **fields: Any) -> int:
        """A reader's suggestion, which is a proposal and not yet a judgement.

        Named apart from `propose`, which is the shelf's build proposal and a different
        feature entirely. Written under `CONTRIBUTOR_GRANT` so the row carries the terms
        it arrived under, as acceptance 2 asks — the licence is recorded at the moment of
        the offer, because that is the one moment anybody knows which sentence was shown.
        """
        fields.setdefault("licence", CONTRIBUTOR_GRANT)
        return self.correct(state="proposed", **fields)

    def proposed_corrections(self, limit: int = 100) -> list[dict[str, Any]]:
        """What readers have offered and nobody has settled, oldest first: a queue.

        Named apart from `proposals`, which is the shelf's — the second time these two
        features have wanted the same word, and the reason `propose_correction` is not
        `propose` either.
        """
        rows = self.db.execute(
            "SELECT * FROM correction WHERE state = 'proposed' ORDER BY at, id LIMIT ?", (limit,)
        ).fetchall()
        return [dict(row) for row in rows]

    def settle_correction(
        self, correction_id: int, *, accept: bool, by: str = "author", judge: str = ""
    ) -> int:
        """Accept or refuse a reader's proposal, and write the decision down.

        **Acceptance is itself a row** — this card's words. So the proposal keeps its own
        row and gains a state, and a second row records who decided and which way. The
        decision row is written `state = 'accepted'` or `'rejected'` too, so it is never
        mistaken for an ordinary judgement and `agreed` counts only what was accepted.

        Applying the change to the gloss is the caller's: this store does not know what a
        gloss is, and the same decision may settle a lemma or a pointing later.

        `by` is the role that settled it and `judge` which one of them, where there is an
        account or an editor behind it (`editor_judge`). The author and a paid editor
        both settle, and either verdict closes the proposal the same way (design.md §12,
        "An editor settles a reader's proposal — 2026-09-27"; targum-internal#354). An
        editor's decision row is `who = 'editor'` under their own pseudonym, so an
        accepted proposal counts as the reader and that editor agreeing: two judges in
        `agreed`. `by` defaults to the author.
        """
        state = "accepted" if accept else "rejected"
        with self.write() as db:
            row = db.execute(
                "SELECT * FROM correction WHERE id = ? AND state = 'proposed'", (correction_id,)
            ).fetchone()
            if row is None:
                raise KeyError(f"no proposal {correction_id}")
            db.execute("UPDATE correction SET state = ? WHERE id = ?", (state, correction_id))
        return self.correct(
            str(row["stage"]),
            who=by,
            term=str(row["term"]),
            language=str(row["language"]),
            target=str(row["target"]),
            text=str(row["text"]),
            before=str(row["before"]),
            after=str(row["after"]),
            judge=judge,
            state=state,
            licence="targum",
            reason=f"{state} a reader's proposal",
        )

    def judge_for(self, person_id: int) -> str:
        """One reader's pseudonym as a judge (targum-internal#164, David 2026-09-22).

        `who` says what *kind* of judge made a correction; this says *which one*, without
        saying who they are. It is the whole of what tells two readers agreeing from one
        reader correcting the same word twice — and since most rows will be readers'
        groundings, that is most of the gold set.

        **The salt is minted once and never rotated**, which is a correction to how this
        was first proposed. A rotating salt gives one person a different pseudonym in each
        window, so two windows of one reader would read as two readers agreeing — it would
        manufacture exactly the false corroboration the pseudonym exists to prevent.

        The anonymity that matters here is against what *leaves*. The salt never goes out
        with an export and is not derivable from one, so a pseudonym cannot be tied to a
        person by anybody holding only the rows. Inside the store, where the person table
        already lives, no pseudonym was ever going to hide anybody from the operator.
        """
        return self._pseudonym(str(int(person_id)))

    def editor_judge(self, name: str) -> str:
        """One editor's pseudonym as a judge (targum-internal#354).

        An editor is paid, not signed in, so there is no account id to salt; the name
        they are known by here stands in for one. Salted the same way and with the same
        never-rotated salt, for the same reason: two editors agreeing are two judges, and
        one editor's second pass over a word is still one. The name is folded to lower
        case and trimmed so "Dana" on Monday and "dana " on Friday are one editor.

        Prefixed so it can never meet a reader's: a reader's pseudonym salts a bare
        account number, and no account number begins "editor:".
        """
        folded = " ".join(name.split()).casefold()
        if not folded:
            raise ValueError("an editor's pseudonym needs a name")
        return self._pseudonym(f"editor:{folded}")

    def _pseudonym(self, key: str) -> str:
        import hmac

        with self.write() as db:
            row = db.execute("SELECT salt FROM judging WHERE id = 1").fetchone()
            if row is None:
                salt = secrets.token_hex(32)
                db.execute("INSERT INTO judging (id, salt) VALUES (1, ?)", (salt,))
            else:
                salt = str(row["salt"])
        return hmac.new(salt.encode("utf-8"), key.encode("utf-8"), hashlib.sha256).hexdigest()[:16]

    def editor_pass(
        self, stage: str, rows: list[dict[str, str]], *, judge: str = ""
    ) -> tuple[list[int], int]:
        """Write a paid editor's pass down as rows (targum-internal#354, door 2).

        The pass arrives as a file and is kept as rows, never applied as a corrected
        file: a corrected file is a snapshot the next rebuild overwrites, and the
        judgements in it are lost when they are applied. Every row is `who = "editor"`
        and `licence = "targum"` — a paid editor's judgement is targum's outright, which
        is written on the row rather than inferred later from the role.

        **It can be run twice.** A row already in the store from this editor — same
        stage, word, line, before and after — is skipped rather than written again,
        because a duplicate is a second judge who does not exist and `agreed` counts
        judges. Returns the ids written and how many were already there.
        """
        todo = self.unkept_editor_rows(stage, rows, judge=judge)
        written = [
            self.correct(
                stage,
                who="editor",
                judge=judge,
                licence="targum",
                **{k: str(row.get(k, "")) for k in (*EDITOR_FIELDS, "text", "context", "reason")},
            )
            for row in todo
        ]
        return written, len(rows) - len(todo)

    def unkept_editor_rows(
        self, stage: str, rows: list[dict[str, str]], *, judge: str = ""
    ) -> list[dict[str, str]]:
        """The rows of an editor's pass that this editor has not already had written down,
        and each of those once, in the order given — what `editor_pass` would write."""
        held = {
            tuple(str(row[k]) for k in EDITOR_FIELDS)
            for row in self.db.execute(
                "SELECT * FROM correction WHERE stage = ? AND who = 'editor' AND judge = ?",
                (stage, judge),
            ).fetchall()
        }
        todo = []
        for row in rows:
            key = tuple(str(row.get(k, "")) for k in EDITOR_FIELDS)
            if key not in held:
                held.add(key)
                todo.append(row)
        return todo

    def correct(
        self,
        stage: str,
        *,
        who: str,
        term: str = "",
        language: str = "",
        target: str = "",
        text: str = "",
        span: str = "",
        before: str = "",
        after: str = "",
        judge: str = "",
        state: str = "",
        licence: str = "",
        context: str = "",
        reason: str = "",
    ) -> int:
        """Write one judgement down. Returns the row's id.

        `who` is a role, never a person: the store is the company's record of what was
        decided about Hebrew, and a reader's name is not part of that. The sentence is
        cut short because a judgement wants the line it was made on, not the page.
        """
        with self.write() as db:
            cursor = db.execute(
                "INSERT INTO correction (at, stage, language, target, term, text, span,"
                " before, after, who, judge, state, licence, context, reason)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    now(),
                    stage,
                    language,
                    target,
                    term,
                    text,
                    span,
                    before,
                    after,
                    who,
                    judge,
                    state,
                    licence,
                    context[:500],
                    reason[:300],
                ),
            )
            return int(cursor.lastrowid or 0)

    def corrections(self, stage: str = "", limit: int = 100) -> list[dict[str, Any]]:
        """The latest judgements, newest first, all stages or one."""
        if stage:
            rows = self.db.execute(
                "SELECT * FROM correction WHERE stage = ? ORDER BY at DESC, id DESC LIMIT ?",
                (stage, limit),
            ).fetchall()
        else:
            rows = self.db.execute(
                "SELECT * FROM correction ORDER BY at DESC, id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(row) for row in rows]

    def agreed(self, stage: str = "", least: int = 2) -> list[dict[str, Any]]:
        """Judgements two different kinds of judge reached independently — the candidate
        gold set of targum-internal#164, acceptance 4.

        Three rules, each of which throws rows away on purpose:

        **`model` is not a judge.** This card is "every *human* judgement about a word",
        and a sense the model produced agreeing with itself is not corroboration.

        **A deletion is not an answer.** `after = ''` says the old gloss was wrong and
        offers nothing to stand instead, so it cannot be a gold example. Two judges
        agreeing to delete is real signal and is a different question.

        **One judge counts once, however many times they say it.** A judge is the
        pseudonym where there is one (`judge_for`, since David's decision of 2026-09-22)
        and the role where there is not — the author's own hand has no account behind it,
        and rows written before the column existed have none either. So two groundings by
        one reader are one judge, two readers agreeing are two, and the author agreeing
        with a reader is two. Before the pseudonym this could only be counted by role,
        which made the set correct but small: reader-corroborating-reader, which is most
        of it, was uncountable.
        """
        # The judge, or the role standing in for one. `who` is never empty, so this is
        # never null, and a role can never collide with a 16-hex-digit pseudonym.
        judge = "CASE WHEN judge <> '' THEN judge ELSE who END"
        # A proposal nobody has accepted is not a judgement yet, and one that was
        # refused is a judgement that it was *wrong* — counting either would let a reader
        # put an answer into the gold set by suggesting it, which is the whole thing
        # "not a vote" is guarding against.
        where = ["who <> 'model'", "after <> ''", "state IN ('', 'accepted')"]
        values: list[Any] = []
        if stage:
            where.append("stage = ?")
            values.append(stage)
        values.append(least)
        rows = self.db.execute(
            "SELECT stage, language, target, term, span, after,"
            f" COUNT(DISTINCT {judge}) AS judges, GROUP_CONCAT(DISTINCT who) AS roles,"
            " COUNT(*) AS seen, MIN(at) AS first_at, MAX(at) AS last_at"
            f" FROM correction WHERE {' AND '.join(where)}"
            " GROUP BY stage, language, target, term, span, after"
            f" HAVING COUNT(DISTINCT {judge}) >= ?"
            " ORDER BY judges DESC, last_at DESC",
            values,
        ).fetchall()
        return [dict(row) for row in rows]

    # --- slips: what the reader got wrong (targum-internal#290) --------------------

    def slip(
        self,
        person_id: int,
        *,
        wrote: str,
        recast: str,
        changed: list[str],
        language: str = "he",
        chat: str = "",
        turn: int = 0,
        why: str = "",
        source: str = "",
    ) -> int:
        """Write down one line that came back changed. Returns the row's id.

        Only called where the diff is non-empty, so a correct line writes nothing: the
        table is a record of mistakes and not a log of turns. Keyed to a person, unlike
        `correct` above, because this is a fact about a learner and not about Hebrew.
        """
        with self.write() as db:
            cursor = db.execute(
                "INSERT INTO slip (person, language, at, chat, turn, wrote, recast,"
                " changed, why, source) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    person_id,
                    language,
                    now(),
                    chat,
                    turn,
                    wrote,
                    recast,
                    json.dumps(changed, ensure_ascii=False),
                    why,
                    source,
                ),
            )
            self._bump_ledger(db, person_id)
            return int(cursor.lastrowid or 0)

    def slips(
        self,
        person_id: int | None,
        language: str = "",
        limit: int = 50,
        oldest: bool = False,
        open_only: bool = False,
    ) -> list[dict[str, Any]]:
        """One person's slips. Newest first, or oldest for the queue.

        Oldest first is what the queue wants, for the reason the word queue wants it
        (targum-internal#103): the thing worth coming back to is what has been sitting
        there longest, and it is the only order the record can honestly support.
        `open_only` leaves out the lines the reader has said they know, which is what
        the queue is and nothing else is: the record keeps them.
        """
        if person_id is None:
            return []
        order = "ASC" if oldest else "DESC"
        where = "person = ? AND gone = 0"
        if open_only:
            where += " AND known = 0"
        args: list[Any] = [person_id]
        if language:
            where += " AND language = ?"
            args.append(language)
        args.append(limit)
        rows = self.db.execute(
            f"SELECT id, language, at, chat, turn, wrote, recast, changed, why, known, source"
            f" FROM slip"
            f" WHERE {where} ORDER BY at {order}, id {order} LIMIT ?",
            args,
        ).fetchall()
        out = []
        for row in rows:
            got = dict(row)
            try:
                got["changed"] = json.loads(got["changed"] or "[]")
            except json.JSONDecodeError:
                got["changed"] = []
            out.append(got)
        return out

    def know_slip(self, person_id: int, slip_id: int, known: bool = True) -> bool:
        """Say a reader knows a line they once got wrong, or take it back.

        Only their own: the id is matched with the person, so another reader's slip is
        not found rather than changed. Returns whether a row was.
        """
        with self.write() as db:
            cursor = db.execute(
                "UPDATE slip SET known = ? WHERE id = ? AND person = ? AND gone = 0",
                (now() if known else 0, slip_id, person_id),
            )
            if cursor.rowcount > 0:
                self._bump_ledger(db, person_id)
            return cursor.rowcount > 0

    # --- what a reader wrote for their own connector (targum-internal#80) ----------

    def write_prompt(self, person_id: int, name: str, says: str) -> dict[str, Any] | None:
        """Save a prompt under a name, replacing one of the same name. None if refused.

        The name is what appears in their host, so it is narrowed to what a host will
        show as one word and what a slash command can be: a name with a space in it reads
        as two commands in every client that draws them.
        """
        name = _prompt_name(name)
        says = says.strip()[:PROMPT_LENGTH]
        if not name or not says:
            return None
        with self.write() as db:
            standing = db.execute(
                "SELECT COUNT(*) AS n FROM prompt WHERE person = ? AND gone = 0 AND name != ?",
                (person_id, name),
            ).fetchone()
            if int(standing["n"]) >= MOST_PROMPTS:
                return None
            db.execute(
                "INSERT INTO prompt (person, name, says, made) VALUES (?, ?, ?, ?)"
                " ON CONFLICT(person, name) DO UPDATE SET"
                "   says = excluded.says, made = excluded.made, gone = 0",
                (person_id, name, says, now()),
            )
            row = db.execute(
                "SELECT id, name, says, made FROM prompt WHERE person = ? AND name = ?",
                (person_id, name),
            ).fetchone()
        return dict(row) if row else None

    def prompts(self, person_id: int | None) -> list[dict[str, Any]]:
        """One reader's own prompts, oldest first — the order they wrote them in."""
        if person_id is None:
            return []
        rows = self.db.execute(
            "SELECT id, name, says, made FROM prompt WHERE person = ? AND gone = 0"
            " ORDER BY made, id",
            (person_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def drop_prompt(self, person_id: int, name: str) -> bool:
        """Take one away. A tombstone, like everything else a reader keeps."""
        with self.write() as db:
            cursor = db.execute(
                "UPDATE prompt SET gone = ? WHERE person = ? AND name = ? AND gone = 0",
                (now(), person_id, _prompt_name(name)),
            )
            return cursor.rowcount > 0

    # --- playlists: texts a reader keeps in an order (targum-internal#364) -----------

    def make_playlist(
        self, person_id: int, name: str, made_by: str = "reader"
    ) -> dict[str, Any] | None:
        """A new, empty playlist. None if it has no name or they already keep the most."""
        name = " ".join(name.split())[:PLAYLIST_NAME]
        if not name or made_by not in PLAYLIST_MAKERS:
            return None
        with self.write() as db:
            standing = db.execute(
                "SELECT COUNT(*) AS n FROM playlist WHERE person = ? AND gone = 0",
                (person_id,),
            ).fetchone()
            if int(standing["n"]) >= MOST_PLAYLISTS:
                return None
            cursor = db.execute(
                "INSERT INTO playlist (person, name, made_by, made) VALUES (?, ?, ?, ?)",
                (person_id, name, made_by, now()),
            )
            made = int(cursor.lastrowid or 0)
        return self.playlist(person_id, made)

    def playlists(self, person_id: int | None) -> list[dict[str, Any]]:
        """One reader's playlists, newest first, each with how many texts it holds and
        the reader its first built text opens, where there is one."""
        if person_id is None:
            return []
        rows = self.db.execute(
            "SELECT p.id, p.name, p.made_by, p.made, p.at, p.visited,"
            " (SELECT COUNT(*) FROM playlist_item i WHERE i.playlist = p.id) AS count,"
            " (SELECT i.reader FROM playlist_item i WHERE i.playlist = p.id"
            "   AND i.reader IS NOT NULL AND i.failed = 0 ORDER BY i.position LIMIT 1) AS first"
            " FROM playlist p WHERE p.person = ? AND p.gone = 0 ORDER BY p.made DESC, p.id DESC",
            (person_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def playlists_holding(self, person_id: int | None) -> dict[str, list[str]]:
        """Which of one reader's playlists hold each text, by reader name: what a shelf
        row names on its fact line (design.md §12, 2026-09-24). One query for the shelf."""
        if person_id is None:
            return {}
        rows = self.db.execute(
            "SELECT i.reader, p.name FROM playlist_item i JOIN playlist p ON p.id = i.playlist"
            " WHERE p.person = ? AND p.gone = 0 AND i.reader IS NOT NULL"
            " ORDER BY p.made, p.id",
            (person_id,),
        ).fetchall()
        holding: dict[str, list[str]] = {}
        for row in rows:
            names = holding.setdefault(str(row["reader"]), [])
            if row["name"] not in names:
                names.append(str(row["name"]))
        return holding

    def playlist(self, person_id: int | None, playlist_id: int) -> dict[str, Any] | None:
        """One playlist and everything in it, in order. None if it is not theirs — the
        same answer as one that does not exist, deliberately."""
        if person_id is None:
            return None
        row = self.db.execute(
            "SELECT id, name, made_by, made, at, visited FROM playlist"
            " WHERE id = ? AND person = ? AND gone = 0",
            (playlist_id, person_id),
        ).fetchone()
        if row is None:
            return None
        items = self.db.execute(
            "SELECT position, reader, job, title, failed FROM playlist_item"
            " WHERE playlist = ? ORDER BY position",
            (playlist_id,),
        ).fetchall()
        out = dict(row)
        out["items"] = [{**dict(item), "failed": bool(item["failed"])} for item in items]
        return out

    def next_set(self, person_id: int, playlist_id: int) -> int | None:
        """The set this playlist offered at its end: a playlist id, 0 when one was looked
        for and none could be made, or None when its end has not been reached yet."""
        row = self.db.execute(
            "SELECT next_set FROM playlist WHERE id = ? AND person = ? AND gone = 0",
            (playlist_id, person_id),
        ).fetchone()
        return None if row is None or row["next_set"] is None else int(row["next_set"])

    def offer_next_set(self, person_id: int, playlist_id: int, next_id: int) -> bool:
        """Remember the one set a playlist's end offered, once. False when it had one
        already — the first writer keeps it, so two visits at once cannot offer two."""
        with self.write() as db:
            done = db.execute(
                "UPDATE playlist SET next_set = ? WHERE id = ? AND person = ? AND gone = 0"
                " AND next_set IS NULL",
                (next_id, playlist_id, person_id),
            )
        return done.rowcount > 0

    def add_to_playlist(
        self,
        person_id: int,
        playlist_id: int,
        title: str,
        reader: str | None = None,
        job: str | None = None,
    ) -> dict[str, Any] | None:
        """Put a text at the end of a playlist. None if the playlist is not theirs, is
        full, or was given nothing to hold. A text already in it is not added twice: the
        item already there comes back."""
        title = " ".join(title.split())[:200] or (reader or "")
        if not (reader or job) or not title:
            return None
        with self.write() as db:
            owned = db.execute(
                "SELECT 1 FROM playlist WHERE id = ? AND person = ? AND gone = 0",
                (playlist_id, person_id),
            ).fetchone()
            if owned is None:
                return None
            if reader:
                there = db.execute(
                    "SELECT position, reader, job, title, failed FROM playlist_item"
                    " WHERE playlist = ? AND reader = ?",
                    (playlist_id, reader),
                ).fetchone()
                if there is not None:
                    return {**dict(there), "failed": bool(there["failed"])}
            count = int(
                db.execute(
                    "SELECT COUNT(*) AS n FROM playlist_item WHERE playlist = ?", (playlist_id,)
                ).fetchone()["n"]
            )
            if count >= MOST_IN_PLAYLIST:
                return None
            db.execute(
                "INSERT INTO playlist_item (playlist, position, reader, job, title)"
                " VALUES (?, ?, ?, ?, ?)",
                (playlist_id, count, reader, job, title),
            )
        return {"position": count, "reader": reader, "job": job, "title": title, "failed": False}

    def move_in_playlist(self, person_id: int, playlist_id: int, position: int, by: int) -> bool:
        """Move one text up (-1) or down (+1) a place. False if there is no such place."""
        if by not in (-1, 1):
            return False
        with self.write() as db:
            owned = db.execute(
                "SELECT 1 FROM playlist WHERE id = ? AND person = ? AND gone = 0",
                (playlist_id, person_id),
            ).fetchone()
            if owned is None:
                return False
            other = position + by
            both = db.execute(
                "SELECT COUNT(*) AS n FROM playlist_item WHERE playlist = ? AND position IN (?, ?)",
                (playlist_id, position, other),
            ).fetchone()
            if int(both["n"]) != 2:
                return False
            # Through -1, because the key is (playlist, position) and a swap in place
            # would collide halfway.
            for old, new in ((position, -1), (other, position), (-1, other)):
                db.execute(
                    "UPDATE playlist_item SET position = ? WHERE playlist = ? AND position = ?",
                    (new, playlist_id, old),
                )
            # The place the reader is at follows the text they are on (#434).
            db.execute(
                "UPDATE playlist SET at = CASE at WHEN ? THEN ? WHEN ? THEN ? ELSE at END"
                " WHERE id = ?",
                (position, other, other, position, playlist_id),
            )
        return True

    def move_to_in_playlist(self, person_id: int, playlist_id: int, position: int, to: int) -> bool:
        """Move one text from its place to another, the ones between closing up behind it
        or opening in front of it: a drag (targum-internal#434). False if either place is
        not there. The place the reader is at follows the text they are on."""
        with self.write() as db:
            owned = db.execute(
                "SELECT at FROM playlist WHERE id = ? AND person = ? AND gone = 0",
                (playlist_id, person_id),
            ).fetchone()
            if owned is None:
                return False
            count = int(
                db.execute(
                    "SELECT COUNT(*) AS n FROM playlist_item WHERE playlist = ?", (playlist_id,)
                ).fetchone()["n"]
            )
            if not (0 <= position < count and 0 <= to < count):
                return False
            if position == to:
                return True
            step = 1 if to > position else -1
            # Out of the way at -1, then each between shifted one place towards the gap,
            # then into its new place: the key is (playlist, position), and a shift in
            # one statement would collide halfway.
            db.execute(
                "UPDATE playlist_item SET position = -1 WHERE playlist = ? AND position = ?",
                (playlist_id, position),
            )
            between = range(position + step, to + step, step)
            for old in between:
                db.execute(
                    "UPDATE playlist_item SET position = ? WHERE playlist = ? AND position = ?",
                    (old - step, playlist_id, old),
                )
            db.execute(
                "UPDATE playlist_item SET position = ? WHERE playlist = ? AND position = -1",
                (to, playlist_id),
            )
            at = owned["at"]
            if at is not None:
                at = int(at)
                if at == position:
                    at = to
                elif at in between:
                    at -= step
                db.execute("UPDATE playlist SET at = ? WHERE id = ?", (at, playlist_id))
        return True

    def playlist_here(self, person_id: int, playlist_id: int, position: int) -> bool:
        """The reader is at this place in this playlist, now (targum-internal#434). A
        place past the last item is a playlist gone through, which no longer counts as the
        one they are in."""
        with self.write() as db:
            cursor = db.execute(
                "UPDATE playlist SET at = ?, visited = ? WHERE id = ? AND person = ? AND gone = 0",
                (max(0, position), now(), playlist_id, person_id),
            )
            return cursor.rowcount > 0

    def current_playlist(self, person_id: int | None) -> dict[str, Any] | None:
        """The playlist the reader is in: the one they were in last, while there is still
        something in it after where they are. None when there is none, or they finished
        the last one they were in."""
        if person_id is None:
            return None
        row = self.db.execute(
            "SELECT p.id, p.name, p.at,"
            " (SELECT COUNT(*) FROM playlist_item i WHERE i.playlist = p.id) AS count"
            " FROM playlist p WHERE p.person = ? AND p.gone = 0 AND p.visited IS NOT NULL"
            " ORDER BY p.visited DESC, p.id DESC LIMIT 1",
            (person_id,),
        ).fetchone()
        if row is None or row["at"] is None or int(row["at"]) >= int(row["count"]):
            return None
        return {"id": int(row["id"]), "name": str(row["name"]), "at": int(row["at"])}

    def play_next(
        self, person_id: int, playlist_id: int, title: str, reader: str
    ) -> dict[str, Any] | None:
        """Put a text straight after the one the reader is on (targum-internal#434): added
        if it is not in the playlist, moved if it is. None where it could not be — not
        theirs, or full."""
        added = self.add_to_playlist(person_id, playlist_id, title, reader=reader)
        if added is None:
            return None
        found = self.playlist(person_id, playlist_id)
        if found is None:
            return None
        at = found.get("at")
        here = int(at) if at is not None else -1
        position = int(added["position"])
        to = here + 1 if position > here else here
        to = max(0, min(to, len(found["items"]) - 1))
        self.move_to_in_playlist(person_id, playlist_id, position, to)
        return {**added, "position": to}

    def drop_from_playlist(self, person_id: int, playlist_id: int, position: int) -> bool:
        """Take one text out, closing the gap it leaves."""
        with self.write() as db:
            owned = db.execute(
                "SELECT 1 FROM playlist WHERE id = ? AND person = ? AND gone = 0",
                (playlist_id, person_id),
            ).fetchone()
            if owned is None:
                return False
            cursor = db.execute(
                "DELETE FROM playlist_item WHERE playlist = ? AND position = ?",
                (playlist_id, position),
            )
            if cursor.rowcount == 0:
                return False
            later = db.execute(
                "SELECT position FROM playlist_item WHERE playlist = ? AND position > ?"
                " ORDER BY position",
                (playlist_id, position),
            ).fetchall()
            for row in later:
                db.execute(
                    "UPDATE playlist_item SET position = ? WHERE playlist = ? AND position = ?",
                    (int(row["position"]) - 1, playlist_id, int(row["position"])),
                )
            db.execute(
                "UPDATE playlist SET at = at - 1 WHERE id = ? AND at > ?", (playlist_id, position)
            )
        return True

    def playlist_made_by(self, person_id: int, playlist_id: int, made_by: str) -> bool:
        """Whose hand made a playlist, said after it was made: the end card's next set is
        quoted through the chat's tool and is targum's pick (#435)."""
        if made_by not in PLAYLIST_MAKERS:
            return False
        with self.write() as db:
            cursor = db.execute(
                "UPDATE playlist SET made_by = ? WHERE id = ? AND person = ? AND gone = 0",
                (made_by, playlist_id, person_id),
            )
            return cursor.rowcount > 0

    def rename_playlist(self, person_id: int, playlist_id: int, name: str) -> bool:
        name = " ".join(name.split())[:PLAYLIST_NAME]
        if not name:
            return False
        with self.write() as db:
            cursor = db.execute(
                "UPDATE playlist SET name = ? WHERE id = ? AND person = ? AND gone = 0",
                (name, playlist_id, person_id),
            )
            return cursor.rowcount > 0

    def drop_playlist(self, person_id: int, playlist_id: int) -> bool:
        """Take a playlist away. A tombstone; the texts in it stay on the shelf."""
        with self.write() as db:
            cursor = db.execute(
                "UPDATE playlist SET gone = ? WHERE id = ? AND person = ? AND gone = 0",
                (now(), playlist_id, person_id),
            )
            return cursor.rowcount > 0

    def playlist_item_built(self, job: str, reader: str) -> int:
        """A build a playlist was waiting on has its reader now (#365). Every item
        naming that job takes it; how many did."""
        with self.write() as db:
            cursor = db.execute(
                "UPDATE playlist_item SET reader = ?, failed = 0 WHERE job = ?", (reader, job)
            )
            return cursor.rowcount

    def playlist_item_failed(self, job: str) -> int:
        """A build a playlist was waiting on could not be made (#365). The swipe passes
        over it (#366); the others stand."""
        with self.write() as db:
            cursor = db.execute("UPDATE playlist_item SET failed = 1 WHERE job = ?", (job,))
            return cursor.rowcount

    # --- the connector: clients, grants and tokens (targum-internal#80) -------------

    def register_client(self, name: str, redirects: list[str]) -> str:
        """Take a client's word for what it is, and give it an id (RFC 7591).

        Dynamic registration means strangers write this row, so nothing in it is trusted.
        The name is the client's claim about itself and is shown to the reader as one;
        the redirect list is the only part that has to be right, and it is checked by
        exact match at both the authorize and the token door.
        """
        client_id = secrets.token_urlsafe(TOKEN_BYTES)
        with self.write() as db:
            db.execute(
                "INSERT INTO oauth_client (id, name, redirects, made) VALUES (?, ?, ?, ?)",
                (client_id, name.strip()[:200], json.dumps(redirects[:16]), now()),
            )
        return client_id

    def registering_too_often(self, limit: int = REGISTRATIONS_PER_HOUR) -> bool:
        """Whether the box has handed out too many client ids in the last hour.

        Keyed on nothing, because there is nothing to key it on: a client registering
        itself has no account and no name we would believe. So this counts the act, over
        the same `asked` table and the same hour the sign-in door uses.
        """
        return self.asking_too_often("oauth-register", limit)

    def client(self, client_id: str) -> dict[str, Any] | None:
        """One registered client, with its redirects already parsed."""
        if not client_id:
            return None
        row = self.db.execute(
            "SELECT id, name, redirects, made FROM oauth_client WHERE id = ?", (client_id,)
        ).fetchone()
        if row is None:
            return None
        got = dict(row)
        try:
            got["redirects"] = json.loads(got["redirects"] or "[]")
        except json.JSONDecodeError:
            got["redirects"] = []
        return got

    def start_grant(
        self,
        person_id: int,
        client_id: str,
        *,
        scopes: str,
        redirect: str,
        challenge: str,
        resource: str = "",
    ) -> str:
        """Mint an authorization code for a reader who has just pressed Approve.

        The code is returned once and held as a digest, like a sign-in link. What it
        carries is what the reader agreed to — the scopes are written here, from the
        approval page, and never read back off anything the client sends later.
        """
        code = secrets.token_urlsafe(TOKEN_BYTES)
        with self.write() as db:
            db.execute(
                "INSERT INTO oauth_grant (hash, person, client, scopes, redirect,"
                " challenge, resource, made) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    digest(code),
                    person_id,
                    client_id,
                    scopes,
                    redirect,
                    challenge,
                    resource,
                    now(),
                ),
            )
        return code

    def spend_grant(self, code: str, minutes: int = GRANT_MINUTES) -> dict[str, Any] | None:
        """Spend a code, once. None if it is spent, stale, or not a code.

        Marked rather than deleted: a replayed code should be recognisable as replayed.
        Whoever calls this must check the PKCE verifier against `challenge` and the
        client and redirect against what was stored — this only guarantees the code was
        fresh and is now gone.

        The cutoff is inclusive, so a lifetime of zero refuses everything rather than
        accepting whatever was minted inside the same millisecond. It reads as a detail
        and it is the difference between a test that pins the boundary and one that
        passes whenever the clock happens to tick.
        """
        if not code:
            return None
        cutoff = now() - minutes * 60 * 1000
        with self.write() as db:
            row = db.execute(
                "SELECT hash, person, client, scopes, redirect, challenge, resource,"
                " made, spent FROM oauth_grant WHERE hash = ?",
                (digest(code),),
            ).fetchone()
            if row is None or row["spent"] or row["made"] <= cutoff:
                return None
            db.execute("UPDATE oauth_grant SET spent = ? WHERE hash = ?", (now(), digest(code)))
            return dict(row)

    def mint_token(
        self,
        person_id: int,
        client_id: str,
        *,
        kind: str = "access",
        scopes: str,
        resource: str = "",
        parent: str = "",
        minutes: int = ACCESS_MINUTES,
    ) -> str:
        """Write one token and hand it back. It exists in the clear only in the reply."""
        token = secrets.token_urlsafe(TOKEN_BYTES)
        expires = 0 if kind == "refresh" else now() + minutes * 60 * 1000
        with self.write() as db:
            db.execute(
                "INSERT INTO oauth_token (hash, person, client, kind, scopes, resource,"
                " parent, made, expires) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    digest(token),
                    person_id,
                    client_id,
                    kind,
                    scopes,
                    resource,
                    parent,
                    now(),
                    expires,
                ),
            )
        return token

    def bearer(self, token: str | None) -> tuple[Person, str] | None:
        """Who is holding this access token, and what they let it do.

        The scopes come off the row, never off the request: that is the same rule
        `chat/tools.py` states about ownership, and it is what makes the registry safe to
        expose to a client targum does not control. An account that is leaving is nobody,
        the way it is nobody to `whoever`.

        Touches `seen`, at most once a minute, so the account page can say when a
        connector last asked. That is the only thing it decides.
        """
        if not token:
            return None
        row = self.db.execute(
            "SELECT oauth_token.person AS id, oauth_token.scopes AS scopes,"
            " oauth_token.expires AS expires, oauth_token.revoked AS revoked,"
            " oauth_token.seen AS seen, person.email AS email, person.leaving AS leaving"
            " FROM oauth_token JOIN person ON person.id = oauth_token.person"
            " WHERE oauth_token.hash = ? AND oauth_token.kind = 'access'",
            (digest(token),),
        ).fetchone()
        if row is None or row["revoked"] or row["leaving"] is not None:
            return None
        if row["expires"] and row["expires"] < now():
            return None
        if now() - row["seen"] > 60_000:
            with self.write() as db:
                db.execute("UPDATE oauth_token SET seen = ? WHERE hash = ?", (now(), digest(token)))
        return Person(row["id"], row["email"], self.is_admin(row["email"])), row["scopes"]

    def rotate_refresh(self, token: str) -> dict[str, Any] | None:
        """Spend a refresh token and say what it was for, so a new pair can be written.

        Rotation, not reuse: the old row is revoked here and the caller chains the new one
        to it through `parent`. A refresh token presented twice is a token that leaked.

        **And a leaked one takes the whole family down.** Refusing the second use alone
        would leave whatever was minted from the first still working, which is the wrong
        half to keep: by the time a rotated token is presented again, one of the two
        holding it is not the reader, and nothing here can say which. So every token this
        client holds for this person is revoked, both kinds, and the reader connects
        again — one press in the app it came from, against an account nobody else is
        still inside.
        """
        if not token:
            return None
        with self.write() as db:
            row = db.execute(
                "SELECT hash, person, client, scopes, resource, revoked FROM oauth_token"
                " WHERE hash = ? AND kind = 'refresh'",
                (digest(token),),
            ).fetchone()
            if row is None:
                return None
            if row["revoked"]:
                db.execute(
                    "UPDATE oauth_token SET revoked = ? WHERE person = ? AND client = ?"
                    " AND revoked = 0",
                    (now(), row["person"], row["client"]),
                )
                return None
            db.execute("UPDATE oauth_token SET revoked = ? WHERE hash = ?", (now(), digest(token)))
            return dict(row)

    def revoke_token(self, token: str) -> bool:
        """Revoke one token by its value, whichever kind it is (RFC 7009)."""
        if not token:
            return False
        with self.write() as db:
            cursor = db.execute(
                "UPDATE oauth_token SET revoked = ? WHERE hash = ? AND revoked = 0",
                (now(), digest(token)),
            )
            return cursor.rowcount > 0

    def disconnect(self, person_id: int, client_id: str) -> int:
        """Revoke everything one client holds for one person — the account page's press.

        Both kinds at once: revoking the access token and leaving the refresh token would
        be a disconnection that reconnects itself within the hour.
        """
        with self.write() as db:
            cursor = db.execute(
                "UPDATE oauth_token SET revoked = ? WHERE person = ? AND client = ?"
                " AND revoked = 0",
                (now(), person_id, client_id),
            )
            return cursor.rowcount

    def connections(self, person_id: int | None) -> list[dict[str, Any]]:
        """Which clients this person has connected, and what each may do.

        One row per client rather than per token, because a client holding an access
        token and the refresh token that will replace it is one connection and reads as
        two. Never the digests: see `everything`.
        """
        if person_id is None:
            return []
        rows = self.db.execute(
            "SELECT oauth_token.client AS client, oauth_client.name AS name,"
            " MAX(oauth_token.scopes) AS scopes, MIN(oauth_token.made) AS made,"
            " MAX(oauth_token.seen) AS seen"
            " FROM oauth_token LEFT JOIN oauth_client ON oauth_client.id = oauth_token.client"
            " WHERE oauth_token.person = ? AND oauth_token.revoked = 0"
            " GROUP BY oauth_token.client ORDER BY made DESC",
            (person_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    # -- telegram (targum-internal#328) ----------------------------------------

    def start_telegram_link(self, person_id: int) -> str:
        """Mint the one-time token a `t.me/<bot>?start=<token>` link carries.

        The `link` table's rules — hashed, single use, `LINK_MINUTES` long — with its
        own purpose, so it can bind a chat and cannot sign anybody in, and a sign-in
        link cannot bind a chat. Minting one voids any earlier one of the same purpose,
        as a sign-in link does; a sign-in link on its way through the mail is left be.
        """
        token = secrets.token_urlsafe(TOKEN_BYTES)
        with self.write() as db:
            db.execute("DELETE FROM link WHERE person = ? AND purpose = ?", (person_id, TELEGRAM))
            db.execute(
                "INSERT INTO link (hash, person, made, used, purpose) VALUES (?, ?, ?, NULL, ?)",
                (digest(token), person_id, now(), TELEGRAM),
            )
        return token

    def finish_telegram_link(self, token: str, chat_id: int) -> Person | None:
        """Spend a Telegram link on this chat, and say whose it now is.

        None where the token is spent, stale, wrong, a sign-in link, or belongs to
        somebody on their way out. A chat bound to somebody else before is bound to
        this person now: whoever holds the phone opened the link.
        """
        cutoff = now() - LINK_MINUTES * 60 * 1000
        with self.write() as db:
            row = db.execute(
                "SELECT person, made, used FROM link WHERE hash = ? AND purpose = ?",
                (digest(token), TELEGRAM),
            ).fetchone()
            if row is None or row["used"] is not None or row["made"] < cutoff:
                return None
            who = db.execute(
                "SELECT id, email, leaving FROM person WHERE id = ?", (row["person"],)
            ).fetchone()
            if who is None or who["leaving"] is not None:
                return None
            db.execute("UPDATE link SET used = ? WHERE hash = ?", (now(), digest(token)))
            db.execute(
                "INSERT INTO telegram (chat_id, person, linked) VALUES (?, ?, ?)"
                " ON CONFLICT(chat_id) DO UPDATE SET person = excluded.person,"
                " linked = excluded.linked",
                (int(chat_id), who["id"], now()),
            )
        return Person(int(who["id"]), str(who["email"]), self.is_admin(str(who["email"])))

    def telegram_person(self, chat_id: int) -> Person | None:
        """Whose this chat is, or nobody's. Nobody's for an account on its way out."""
        row = self.db.execute(
            "SELECT person.id AS id, person.email AS email FROM telegram"
            " JOIN person ON person.id = telegram.person"
            " WHERE telegram.chat_id = ? AND person.leaving IS NULL",
            (int(chat_id),),
        ).fetchone()
        if row is None:
            return None
        return Person(int(row["id"]), str(row["email"]), self.is_admin(row["email"]))

    def telegram_chats(self, person_id: int | None) -> list[dict[str, Any]]:
        """The chats bound to this person, newest first."""
        if person_id is None:
            return []
        rows = self.db.execute(
            "SELECT chat_id, linked FROM telegram WHERE person = ? ORDER BY linked DESC",
            (person_id,),
        ).fetchall()
        return [{"chat": int(row["chat_id"]), "linked": int(row["linked"])} for row in rows]

    def unlink_telegram(self, person_id: int, chat_id: int | None = None) -> int:
        """Unbind one of this person's chats, or all of them. How many went."""
        with self.write() as db:
            if chat_id is None:
                gone = db.execute("DELETE FROM telegram WHERE person = ?", (person_id,))
            else:
                gone = db.execute(
                    "DELETE FROM telegram WHERE person = ? AND chat_id = ?",
                    (person_id, int(chat_id)),
                )
            return int(gone.rowcount)

    def stop_telegram(self, chat_id: int) -> Person | None:
        """`/stop` in the chat: unbind it, and say whose it was."""
        was = self.telegram_person(chat_id)
        with self.write() as db:
            db.execute("DELETE FROM telegram WHERE chat_id = ?", (int(chat_id),))
        return was

    def sweep_tokens(self, days: int = TOKEN_SWEEP_DAYS) -> int:
        """Drop rows nothing can use any more: spent grants and long-dead tokens.

        Kept for a while rather than deleted on expiry, so that "this token expired" and
        "this token never existed" stay different answers for as long as they are useful
        to tell apart.
        """
        cutoff = now() - days * 24 * 60 * 60 * 1000
        with self.write() as db:
            gone = db.execute("DELETE FROM oauth_grant WHERE made < ?", (cutoff,)).rowcount
            gone += db.execute(
                "DELETE FROM oauth_token WHERE (revoked > 0 AND revoked < ?)"
                " OR (expires > 0 AND expires < ?)",
                (cutoff, cutoff),
            ).rowcount
            return gone

    def want(self, query: str, source: str, standing: str = "") -> None:
        """Count one ask the shelf could not answer. Keyed on the words and the link,
        never on who asked."""
        query = query.strip()[:200]
        source = source.strip()[:500]
        if not query and not source:
            return
        with self.write() as db:
            db.execute(
                "INSERT INTO wanted (query, source, standing, count, first, last)"
                " VALUES (?, ?, ?, 1, ?, ?)"
                " ON CONFLICT(query, source) DO UPDATE SET"
                "   count = count + 1, last = excluded.last,"
                "   standing = CASE WHEN excluded.standing != '' THEN excluded.standing"
                "                   ELSE wanted.standing END",
                (query, source, standing, now(), now()),
            )

    def reach(self, host: str, open: bool, why: str = "", egress: str = "direct") -> None:
        """Record what the fetch door found at a host, and through which door.

        Keyed on the host alone. `egress` is what the last knock used, so a host that
        only answers the proxy reads `open = 1, egress = 'proxy'` — the pair that says
        the egress is earning its keep (targum-internal#226).
        """
        host = host.strip().lower()[:200]
        if not host:
            return
        with self.write() as db:
            db.execute(
                "INSERT INTO reached (host, open, why, tries, first, last, egress)"
                " VALUES (?, ?, ?, 1, ?, ?, ?)"
                " ON CONFLICT(host) DO UPDATE SET"
                "   open = excluded.open, why = excluded.why,"
                "   tries = tries + 1, last = excluded.last, egress = excluded.egress",
                (host, 1 if open else 0, why.strip()[:200], now(), now(), egress[:16]),
            )

    def closed(self, days: int = 30, limit: int = 12) -> list[str]:
        """Hosts whose last knock was refused, most recently first.

        Bounded in time and in number because it goes into a prompt: it is a hint about
        where not to send a reader, not a blocklist. Nothing here refuses anybody — a
        reader who pastes one of these links is still fetched, and may still be right
        that it works now (targum-internal#126).
        """
        rows = self.db.execute(
            "SELECT host FROM reached WHERE open = 0 AND last >= ? ORDER BY last DESC LIMIT ?",
            (now() - days * 24 * 60 * 60 * 1000, limit),
        ).fetchall()
        return [str(row["host"]) for row in rows]

    def wanted(self, limit: int = 20) -> list[dict[str, Any]]:
        rows = self.db.execute(
            "SELECT query, source, standing, count, first, last FROM wanted"
            " ORDER BY count DESC, last DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]

    # -- what the services have left ---------------------------------------------

    def balance_read(self, service: str, said: str) -> None:
        """Record what a service's console said was left, as of now."""
        with self.write() as db:
            db.execute(
                "INSERT INTO balance (service, said, at) VALUES (?, ?, ?)",
                (service, said, now()),
            )

    def balances(self) -> dict[str, dict[str, Any]]:
        """The newest reading for each service, by service."""
        rows = self.db.execute(
            "SELECT service, said, MAX(at) AS at FROM balance GROUP BY service"
        ).fetchall()
        return {str(row["service"]): {"said": row["said"], "at": row["at"]} for row in rows}

    # -- housekeeping -----------------------------------------------------------

    def sweep(self) -> None:
        """Drop what has expired. Cheap, and safe to call whenever."""
        with self.write() as db:
            db.execute("DELETE FROM link WHERE made < ?", (now() - LINK_MINUTES * 60 * 1000,))
            db.execute(
                "DELETE FROM session WHERE seen < ?",
                (now() - SESSION_DAYS * 24 * 60 * 60 * 1000,),
            )
            db.execute("DELETE FROM asked WHERE made < ?", (now() - 60 * 60 * 1000,))

    # -- the work queue ---------------------------------------------------------

    def save_job(self, fields: dict[str, Any]) -> None:
        """Write a build's whole state, so a restart can say what became of it."""
        columns = ", ".join(fields)
        holes = ", ".join("?" for _ in fields)
        updates = ", ".join(f"{name} = excluded.{name}" for name in fields if name != "id")
        with self.write() as db:
            db.execute(
                f"INSERT INTO job ({columns}) VALUES ({holes}) "
                f"ON CONFLICT(id) DO UPDATE SET {updates}",
                tuple(fields.values()),
            )

    #: How many finished builds it takes before their middle is worth quoting. Below
    #: this a box has an anecdote rather than a rate, and a "ready in about" drawn from
    #: three builds is a number that will be wrong in a way somebody remembers.
    ENOUGH_TO_QUOTE = 12

    def how_long_builds_take(self, language: str = "", audio: bool | None = None) -> float:
        """Seconds a build of this shape has taken, as the middle of the last hundred.

        The median rather than the mean: one build that sat behind an annotator rename
        for two hours would otherwise move the number for every build after it, and the
        question being answered is "how long will mine take", not "how long have they
        taken in total".

        Zero where this box has not finished enough of them to say. That is the honest
        answer and the page shows nothing rather than a guess — the whole reason this
        column exists is that "ready in about four minutes" was never counted from
        anything (targum-internal#303).

        Rows written before `finished` existed have a zero in it, and are left out
        rather than read as builds that took no time at all.
        """
        clauses = [
            "finished > 0",
            "made > 0",
            "finished >= made",
            "kind IN ('build', 'subscription')",
            "stage = 'done'",
        ]
        params: list[Any] = []
        if language:
            clauses.append("language = ?")
            params.append(language)
        if audio is not None:
            # An imported recording is metered in seconds; everything else is not. It is
            # the one division that changes the answer by an order of magnitude.
            clauses.append("length > 0" if audio else "length = 0")
        rows = self.db.execute(
            "SELECT (finished - made) AS took FROM job WHERE "
            + " AND ".join(clauses)
            + " ORDER BY made DESC LIMIT 100",
            tuple(params),
        ).fetchall()
        took = sorted(int(row["took"]) for row in rows)
        if len(took) < self.ENOUGH_TO_QUOTE:
            return 0.0
        middle = len(took) // 2
        pick = took[middle] if len(took) % 2 else (took[middle - 1] + took[middle]) / 2
        return float(pick) / 1000

    def jobs(self, since: int | None = None) -> list[dict[str, Any]]:
        """Job rows, oldest first. With `since`, only what a process has to hold: every
        job not yet settled, whenever it was made, and the rest made since then
        (targum-internal#231). The table itself is never trimmed."""
        if since is None:
            rows = self.db.execute("SELECT * FROM job ORDER BY made").fetchall()
        else:
            rows = self.db.execute(
                "SELECT * FROM job WHERE stage NOT IN ('done', 'failed', 'blocked')"
                " OR made >= ? ORDER BY made",
                (since,),
            ).fetchall()
        return [dict(row) for row in rows]

    def job(self, job_id: str) -> dict[str, Any] | None:
        """One job's row, for a job the process no longer holds."""
        row = self.db.execute("SELECT * FROM job WHERE id = ?", (job_id,)).fetchone()
        return dict(row) if row is not None else None

    def committed(self, since: int, owner: int | None = -1) -> float:
        """What is still spoken for, counting only the window the budget covers.

        Derived rather than kept: a separate running total is a second source of truth,
        and the two drift the first time a process dies between updating them.

        `owner` of -1 means everyone — the whole box, which is the ceiling that keeps
        one machine from running away. Anything else is that one account.
        """
        if owner == -1:
            row = self.db.execute(
                "SELECT COALESCE(SUM(claimed), 0) AS spent FROM job "
                "WHERE claimed > 0 AND made >= ?",
                (since,),
            ).fetchone()
        else:
            row = self.db.execute(
                "SELECT COALESCE(SUM(claimed), 0) AS spent FROM job "
                "WHERE claimed > 0 AND made >= ? AND owner IS ?",
                (since, owner),
            ).fetchone()
        return float(row["spent"])

    def spending(self, since: int) -> list[dict[str, Any]]:
        """What every account has cost since a moment, most expensive first.

        Two numbers, because they answer different questions. `spent` is what the API
        really charged, once it said — the one that reconciles against a bill. `claimed`
        is what the ceilings actually count, which is the same figure after a build
        settles, the estimate while one is still running, and nothing at all for a build
        that failed and handed its reservation back.

        Left joined, so work done before there were accounts — or by somebody since
        forgotten — still shows up rather than quietly leaving the total short.
        """
        rows = self.db.execute(
            "SELECT person.email AS email, "
            "       COUNT(job.id) AS jobs, "
            "       COALESCE(SUM(job.spent), 0) AS spent, "
            "       COALESCE(SUM(job.claimed), 0) AS claimed, "
            "       COALESCE(SUM(job.cache_read), 0) AS cache_read, "
            "       COALESCE(SUM(job.cache_write), 0) AS cache_write, "
            "       COALESCE(SUM(job.cache_cost), 0) AS cache_cost, "
            "       MAX(job.made) AS last "
            "FROM job LEFT JOIN person ON person.id = job.owner "
            "WHERE job.made >= ? "
            "GROUP BY job.owner "
            "ORDER BY spent DESC, claimed DESC",
            (since,),
        ).fetchall()
        return [dict(row) for row in rows]

    def claim(
        self,
        job_id: str,
        amount: float,
        ceiling: float,
        since: int,
        *,
        owner: int | None = None,
        per_account: float | None = None,
        month_from: int | None = None,
        length: float = 0.0,
        per_month_length: float | None = None,
        kind: str | None = None,
    ) -> str:
        """Take money from every budget, or say which one refused — in one transaction.

        Two builds starting together would otherwise both read the same balance and
        both pass, which is exactly how a budget is overrun. `BEGIN IMMEDIATE` makes
        the second one wait rather than race, and it holds across processes as well as
        threads, which a lock in one server never did.

        Three ceilings, because they stop three different things. The per-account day is
        a rate limit: it stops one afternoon running away. The per-account month is the
        plan limit — what a reader is actually allowed — and until it existed the daily
        rail was doing that job badly, since thirty days of it is thirty times the number
        anybody had agreed to. The whole-box day is what stops every reader at once from
        emptying the card, and no per-account limit can do that on its own.

        Any of them may be `None`, which is how an admin passes: the rails exist to stop
        a reader running up somebody else's bill, and the person paying it is not that
        reader. The box ceiling is not waived for anybody — it is the runaway guard.

        A fourth ceiling, and the only one a reader is ever told about: the monthly
        allowance for uploaded recordings, in seconds. The three above are denominated
        in money, which is the right unit for protecting a card and the wrong one for
        making a promise — "eight hours a month" is a sentence somebody can plan around,
        where "$10 of model spend" is not something they should ever have to think
        about. Money still guards the box; hours are what the plan actually allows.

        Only recordings are counted. Transcription is bought by the minute and is the
        one cost that rises with the clock, so the clock is what meters it; a text
        upload is bounded by the money rails alone.

        `kind` narrows the per-account ceiling to rows of one kind: the chat's own rail
        counts only chat turns, while a build's rail counts everything the account spent.
        The box ceiling never narrows — it is the runaway guard, whatever is running.
        """
        with self.write() as db:
            if per_account is not None:
                narrowed = " AND kind = ?" if kind is not None else ""
                params: tuple[Any, ...] = (since, owner, kind) if kind else (since, owner)
                mine = db.execute(
                    "SELECT COALESCE(SUM(claimed), 0) AS spent FROM job "
                    "WHERE claimed > 0 AND made >= ? AND owner IS ?" + narrowed,
                    params,
                ).fetchone()
                if float(mine["spent"]) + amount > per_account:
                    return "account"
            # Summed on `length` rather than on `claimed`, because the two measure
            # different things: a recording whose transcript was already cached costs
            # nothing and is still an hour of listening. The reader was promised hours,
            # so hours are counted whether or not the build happened to be free.
            if per_month_length is not None and month_from is not None and length > 0:
                used = db.execute(
                    "SELECT COALESCE(SUM(length), 0) AS used FROM job "
                    "WHERE length > 0 AND made >= ? AND owner IS ?",
                    (month_from, owner),
                ).fetchone()
                if float(used["used"]) + length > per_month_length:
                    return "hours"
            row = db.execute(
                "SELECT COALESCE(SUM(claimed), 0) AS spent FROM job "
                "WHERE claimed > 0 AND made >= ?",
                (since,),
            ).fetchone()
            if float(row["spent"]) + amount > ceiling:
                return "everyone"
            db.execute(
                "UPDATE job SET claimed = ?, length = ? WHERE id = ?", (amount, length, job_id)
            )
            return ""

    def claim_all(
        self,
        claims: list[tuple[str, float, float]],
        ceiling: float,
        since: int,
        *,
        owner: int | None = None,
        per_account: float | None = None,
        month_from: int | None = None,
        per_month_length: float | None = None,
    ) -> tuple[str, float]:
        """Claim a set of builds together, or none of them (#365, design.md §12).

        `claims` is `(job id, amount, length)` for each, and the rails are `claim`'s,
        checked against the set's totals in one transaction: one press takes the whole
        set, so the reader is never left holding half of what the page quoted. Returns
        which rail refused, or "", and — where the monthly seconds refused — how many
        seconds were left, so the page can say how many credits would fit.
        """
        amount = sum(one[1] for one in claims)
        length = sum(one[2] for one in claims)
        with self.write() as db:
            if per_account is not None:
                mine = db.execute(
                    "SELECT COALESCE(SUM(claimed), 0) AS spent FROM job "
                    "WHERE claimed > 0 AND made >= ? AND owner IS ?",
                    (since, owner),
                ).fetchone()
                if float(mine["spent"]) + amount > per_account:
                    return "account", 0.0
            if per_month_length is not None and month_from is not None and length > 0:
                used = db.execute(
                    "SELECT COALESCE(SUM(length), 0) AS used FROM job "
                    "WHERE length > 0 AND made >= ? AND owner IS ?",
                    (month_from, owner),
                ).fetchone()
                if float(used["used"]) + length > per_month_length:
                    return "hours", max(0.0, per_month_length - float(used["used"]))
            row = db.execute(
                "SELECT COALESCE(SUM(claimed), 0) AS spent FROM job "
                "WHERE claimed > 0 AND made >= ?",
                (since,),
            ).fetchone()
            if float(row["spent"]) + amount > ceiling:
                return "everyone", 0.0
            for job_id, each, seconds in claims:
                db.execute(
                    "UPDATE job SET claimed = ?, length = ? WHERE id = ?", (each, seconds, job_id)
                )
            return "", 0.0

    def settle(
        self,
        job_id: str,
        spent: float,
        length: float | None = None,
        cache: tuple[int, int, float] | None = None,
    ) -> None:
        """Replace what a build reserved with what it really cost.

        Claiming takes the estimate up front, because the decision to allow a build has
        to be made before it runs. Settling is the other half: once the API has said
        what it charged, the ledger holds that instead of a guess, and the budget stops
        being an approximation of itself. A turn of conversation settles its seconds the
        same way — reserved from the words asked, held at the words said.

        `cache` is what the prompt cache did — tokens read, tokens written, and their
        dollars, which are already inside `spent` — so the receipt can say whether caching
        saved anything (targum-internal#239).
        """
        if cache is not None:
            with self.write() as db:
                db.execute(
                    "UPDATE job SET cache_read = ?, cache_write = ?, cache_cost = ? WHERE id = ?",
                    (int(cache[0]), int(cache[1]), float(cache[2]), job_id),
                )
        with self.write() as db:
            if length is None:
                db.execute(
                    "UPDATE job SET claimed = ?, spent = ? WHERE id = ?", (spent, spent, job_id)
                )
            else:
                db.execute(
                    "UPDATE job SET claimed = ?, spent = ?, length = ? WHERE id = ?",
                    (spent, spent, length, job_id),
                )

    def unclaim(self, job_id: str) -> None:
        """Give back what a failed build never spent — the money and the hours both.

        The hours go back for a reason the money does not share: a refused or broken
        build transcribed nothing, so the reader heard none of what it would have cost
        them. Charging for it would be charging for an hour that does not exist.
        """
        with self.write() as db:
            db.execute("UPDATE job SET claimed = 0, length = 0 WHERE id = ?", (job_id,))

    def interrupt_running(self) -> list[str]:
        """Mark builds that were mid-flight when the process died.

        Called once at start-up. A build cannot be resumed from the middle — the work
        happened in a thread that no longer exists — but it can be told the truth about
        itself instead of sitting at "working" forever.

        **Its claim is kept, deliberately.** A build that was working had very likely
        started paying for batches, and nothing on disk records how much, because usage
        is not plumbed through yet. Releasing the claim would hand the budget back for
        money that really was spent, so a crash loop could spend without limit — which
        is the hole this whole change exists to close. Over-counting a build that died
        early costs a reader one refusal; under-counting costs money. The claim ages out
        of the window on its own within the day.

        **Its hours go back.** They are counted over the month, not the day, so a kept
        length did not age out: a video that OOM-killed the box four times in an hour
        (2026-09-14) charged its reader four times its length for nothing. The reader
        heard none of it, which is `unclaim`'s reason, and a retry claims the hours again.
        The sweep also clears rows an earlier start-up failed with the length kept.
        """
        with self.write() as db:
            rows = db.execute("SELECT id FROM job WHERE stage IN ('working', 'queued')").fetchall()
            db.execute(
                "UPDATE job SET stage = 'failed', error = ?, length = 0 WHERE stage = 'working'",
                (
                    "targum restarted while this was building. Start it again — "
                    "anything already translated is cached, so it will not be paid for twice.",
                ),
            )
            db.execute(
                "UPDATE job SET length = 0 WHERE stage = 'failed' AND length > 0 "
                "AND error LIKE 'targum restarted while this was building%'"
            )
            # A build still waiting in line when the process died is in no line now: the
            # queue was memory, and nothing puts a recovered job back on it. It sat at
            # "queued" for good, and the bell said "We'll start it after four other
            # texts" for days (2026-09-14). It never started, so nothing was spent, and
            # unlike a working build its claim goes back.
            db.execute(
                "UPDATE job SET stage = 'failed', error = ?, claimed = 0, length = 0 "
                "WHERE stage = 'queued'",
                ("targum restarted before this one started. Start it again.",),
            )
            # A conversation's turn is the same story in a different table. Its job row
            # of kind `chat` was caught above, claim kept; the reader's line was not, and
            # sat at "working" for good — a page that opened it again waited on a stream
            # nobody would write (targum-internal#269). Every deploy restarts the box.
            db.execute(
                "UPDATE chat_turn SET stage = 'failed', error = ? WHERE stage = 'working'",
                (CHAT_RESTARTED,),
            )
        return [row["id"] for row in rows]
