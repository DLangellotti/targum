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
from collections.abc import Callable, Iterable
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
# Not to be confused with `models.SCHEMA_VERSION`, which is a cache key: bumping that one
# invalidates every stage and forces paid re-translation of every text. This one versions
# the sqlite file behind an account and costs a column.
SCHEMA_VERSION = 29

#: What a conversation is for. `find` is the door onto the shelf; `talk` is Hebrew.
#: `talk` since 2026-09-06, when the two modes became one: every conversation is in
#: Hebrew. `find` survives on rows written before that and means the same thing now.
MODES = ("find", "talk")

#: What a reader's correction is held under (targum-internal#164, David 2026-09-22): a
#: licence to targum rather than the public domain, whose sentence is in CONTRIBUTING.md.
#: Dated, because if that sentence ever changes, the rows written under the old one must
#: still say which one they meant.
CONTRIBUTOR_GRANT = "reader-grant-2026-09-22"

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
  width     TEXT    NOT NULL DEFAULT ''
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
  hash   TEXT    PRIMARY KEY,
  person INTEGER NOT NULL REFERENCES person(id),
  made   INTEGER NOT NULL,
  used   INTEGER
);

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
  bounces INTEGER NOT NULL DEFAULT 0
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
  language TEXT    NOT NULL DEFAULT ''
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
CREATE INDEX IF NOT EXISTS oauth_token_person ON oauth_token (person, kind, revoked);
CREATE INDEX IF NOT EXISTS oauth_grant_person ON oauth_grant (person);
"""


#: What a reader is told about a line targum was answering when it restarted.
CHAT_RESTARTED = "We restarted while we were answering. Ask again."


def now() -> int:
    """Milliseconds, because the client's own timestamps are `Date.now()`."""
    return int(time.time() * 1000)


def digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


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


# The four kinds of thing a person accumulates, and the columns each one syncs. Kept as
# data rather than four near-identical functions, because the merge is the same
# argument four times and the only thing that differs is the shape.
# Fields that default to a number rather than to empty text when nothing is known.
NUMERIC = frozenset({"at", "updated", "opened", "done", "span_start", "span_end", "count"})


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

    #: How many a reader is asked for. One is a label and two is a preference; three is
    #: the first number that describes somebody, and it is cheap to give. The page
    #: holds the reader to it — this is not enforced here, because clearing the answer
    #: is a legitimate thing to do and a floor would make it impossible.
    INTERESTS_WANTED = 3

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
            db.execute("UPDATE person SET declared = ? WHERE id = ?", (said, person.id))
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
                )
            )
        if not rows:
            return 0
        with self.write() as db:
            db.executemany(
                "INSERT INTO event (person, kind, day, at, language, medium, document, "
                "segment, amount, control, width) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
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
            db.execute("UPDATE person SET address = ? WHERE id = ?", (value, person.id))
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

    def subscribe(self, email: str) -> str | None:
        """The public door. Mint a token to confirm this address, or None if it is on.

        Idempotent: asking twice re-mints rather than making a second row, because
        asking twice is what somebody does when the first mail did not arrive.
        """
        address = tidy(email)
        if not address:
            raise ValueError("No address given.")
        if self.following(address):
            return None
        token = secrets.token_urlsafe(TOKEN_BYTES)
        with self.write() as db:
            db.execute(
                """
                INSERT INTO subscriber (email, state, confirm, stop, asked)
                VALUES (?, 'pending', ?, ?, ?)
                ON CONFLICT(email) DO UPDATE SET state = 'pending', confirm = ?, asked = ?
                """,
                (
                    address,
                    digest(token),
                    secrets.token_urlsafe(TOKEN_BYTES),
                    now(),
                    digest(token),
                    now(),
                ),
            )
        return token

    def follow(self, email: str, on: bool = True) -> bool:
        """The signed-in door, and it confirms nothing.

        Somebody with a session proved they control this address by following a link to
        get in. Mailing them to ask whether they control it would be asking them to
        confirm what they confirmed at the door.
        """
        address = tidy(email)
        if not address:
            raise ValueError("No address given.")
        with self.write() as db:
            if not on:
                db.execute(
                    "UPDATE subscriber SET state = 'off', ended = ? WHERE email = ?",
                    (now(), address),
                )
                return False
            db.execute(
                """
                INSERT INTO subscriber (email, state, confirm, stop, asked, joined)
                VALUES (?, 'on', NULL, ?, ?, ?)
                ON CONFLICT(email) DO UPDATE SET state = 'on', confirm = NULL, joined = ?
                """,
                (address, secrets.token_urlsafe(TOKEN_BYTES), now(), now(), now()),
            )
        return True

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
            return True

    # -- the waitlist (2026-09-16) ----------------------------------------------------
    #
    # The front door's only form. Somebody waiting is not an account, is not a
    # subscriber, and becomes neither by waiting: the address sits in `waiting` until a
    # person decides to let them in, and letting them in is `allow` on `invited`, which
    # is a separate act with a separate record.

    def join_waitlist(self, email: str, language: str = "") -> str | None:
        """Take an address. Mint a token to confirm it, or None if it is already on.

        Idempotent for the same reason `subscribe` is: asking twice is what somebody
        does when the first mail did not arrive, and it should re-mint rather than make
        a second row or a second person.

        `language` is the language the front door was in when they pressed, and it is
        kept so the invitation can be written in it. A second ask overwrites it: the
        door they came through most recently is the better guess at what they read.
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
                INSERT INTO waiting (email, state, confirm, stop, asked, language)
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
                "UPDATE waiting SET state = 'off', ended = ? WHERE email = ?",
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

    # -- series (2026-09-11) ---------------------------------------------------------

    def follow_series(self, email: str, series: str, on: bool = True, language: str = "") -> bool:
        """Follow, or stop following, one series. Signed in, so nothing is confirmed.

        `language` is the one the reader was reading in when they pressed, kept so the
        mail and the stop page can be in it (targum-internal#289). It is written on every
        press rather than only the first, because a reader who changed language and
        followed again means the new one; and it is never cleared on a stop, so somebody
        who follows again after stopping keeps what they last said.
        """
        address = tidy(email)
        if not address or not series:
            raise ValueError("No address or no series given.")
        code = language.split("-")[0].lower() if language else ""
        with self.write() as db:
            if not on:
                db.execute(
                    "UPDATE follow SET state = 'off', ended = ? WHERE email = ? AND series = ?",
                    (now(), address, series),
                )
                return False
            db.execute(
                """
                INSERT INTO follow (email, series, state, stop, since, language)
                VALUES (?, ?, 'on', ?, ?, ?)
                ON CONFLICT(email, series)
                    DO UPDATE SET state = 'on', since = ?, language = ?
                """,
                (
                    address,
                    series,
                    secrets.token_urlsafe(TOKEN_BYTES),
                    now(),
                    code,
                    now(),
                    code,
                ),
            )
        return True

    def series_followed(self, email: str) -> list[str]:
        rows = self.db.execute(
            "SELECT series FROM follow WHERE email = ? AND state = 'on' ORDER BY series",
            (tidy(email),),
        ).fetchall()
        return [str(row["series"]) for row in rows]

    def followers(self, series: str, not_sent: str = "") -> list[tuple[str, str, str]]:
        """Everyone to mail about this instalment, with the token that stops it and the
        language they follow in.

        Selected on "has not had this one", as the weekly's are, so a run that died
        halfway resumes and one started twice sends nothing the second time.
        """
        rows = self.db.execute(
            "SELECT email, stop, language FROM follow WHERE series = ? AND state = 'on' "
            "AND (? = '' OR instalment != ?) ORDER BY since",
            (series, not_sent, not_sent),
        ).fetchall()
        return [(str(row["email"]), str(row["stop"]), str(row["language"] or "en")) for row in rows]

    def following_language(self, token: str) -> str:
        """The language behind a stop token, for the page it opens.

        A stop link is followed with no session and no account — that is the whole point
        of it — so the token is the only thing the page has to go on.
        """
        if not token:
            return "en"
        row = self.db.execute("SELECT language FROM follow WHERE stop = ?", (token,)).fetchone()
        return str(row["language"] or "en") if row is not None else "en"

    def mark_series_sent(self, email: str, series: str, instalment: str) -> None:
        with self.write() as db:
            db.execute(
                "UPDATE follow SET sent = ?, instalment = ? WHERE email = ? AND series = ?",
                (now(), instalment, tidy(email), series),
            )

    def stop_following(self, token: str) -> bool:
        """One click, from an email, with no account and no JavaScript."""
        if not token:
            return False
        with self.write() as db:
            row = db.execute("SELECT email, series FROM follow WHERE stop = ?", (token,)).fetchone()
            if row is None:
                return False
            db.execute(
                "UPDATE follow SET state = 'off', ended = ? WHERE email = ? AND series = ?",
                (now(), row["email"], row["series"]),
            )
            return True

    def subscribers(self, not_sent: str = "") -> list[tuple[str, str]]:
        """Everyone to mail about this issue, with the token that stops it.

        Selecting on "has not had this one" rather than on "is subscribed" is what makes
        a mailout safe to resume: a run that died halfway picks up where it stopped, and
        one started twice sends nothing the second time.

        And on "has not had a later one", which is what makes announcing the wrong week
        harmless. Rows carry the last issue sent, not a history, so a plain "not this
        one" would post last week's issue to everybody who already had this week's.
        """
        rows = self.db.execute(
            "SELECT email, stop FROM subscriber WHERE state = 'on' "
            # Not this issue, and not one already past it. The column holds the last
            # issue sent rather than a history, so "not this one" alone would re-send
            # last week to everybody the moment somebody typed the wrong week — and an
            # email is the one thing here that cannot be taken back. Issue ids are
            # `YYYY-wNN`, zero-padded, so they sort in the order the weeks happened.
            "AND (issue IS NULL OR issue < ?) "
            "ORDER BY joined",
            (not_sent,),
        ).fetchall()
        return [(str(row["email"]), str(row["stop"])) for row in rows]

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
            raise ValueError("Keep at least one.")
        if kind == "learning" and not wanted >= set(REQUIRED_LEARNING):
            raise ValueError(f"{language_name(REQUIRED_LEARNING[0])} stays on.")
        with self.write() as db:
            db.execute("DELETE FROM chosen WHERE person = ? AND kind = ?", (person.id, kind))
            db.executemany(
                "INSERT INTO chosen (person, kind, language, at) VALUES (?, ?, ?, ?)",
                [(person.id, kind, code, now()) for code in sorted(wanted)],
            )
        return wanted

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
            db.execute("DELETE FROM link WHERE person = ?", (row["id"],))
            db.execute(
                "INSERT INTO link (hash, person, made, used) VALUES (?, ?, ?, NULL)",
                (digest(token), row["id"], now()),
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
            "AND person.leaving IS NULL",
            (digest(token), cutoff),
        ).fetchone()
        return Person(row["id"], row["email"], self.is_admin(row["email"])) if row else None

    def finish_sign_in(self, token: str) -> tuple[Person, str] | None:
        """Spend a link and hand back a session. None if it is spent, stale or wrong."""
        cutoff = now() - LINK_MINUTES * 60 * 1000
        with self.write() as db:
            row = db.execute(
                "SELECT person, made, used FROM link WHERE hash = ?", (digest(token),)
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
            # And every connector. Signed out of everywhere has to mean everywhere, and
            # a token left live would be a way into an account that has asked to end —
            # from a client on somebody else's machine, which is worse than a cookie.
            db.execute("DELETE FROM oauth_token WHERE person = ?", (person.id,))
            db.execute("DELETE FROM oauth_grant WHERE person = ?", (person.id,))
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
                    # And what they did in each text (targum-internal#127).
                    "event",
                    "chosen",
                    "session",
                    "link",
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

    def push(self, person: Person, changes: dict[str, list[dict[str, Any]]]) -> int:
        """Take a browser's changes, keeping whichever version of each record is newer.

        Everything lands in one transaction and under one revision number, so a client
        pulling at the same moment sees either all of a push or none of it. Half a
        push is how a phrase arrives without the document it belongs to.
        """
        with self.write() as db:
            stamp = self._next_revision(db, person)
            for name, items in changes.items():
                kind = KINDS.get(name)
                if kind is None:
                    continue
                for item in items:
                    self._merge(db, person, kind, item, stamp)
            return stamp

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
                " WHERE owner = ? AND kind = 'build' ORDER BY made DESC",
                (person.id,),
            )
        ]
        # Which clients they connected, and what they let each one do. The digests stay
        # out, for the reason at the top of this method.
        out["connections"] = self.connections(person.id)
        return out

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

    def settle_correction(self, correction_id: int, *, accept: bool, by: str = "author") -> int:
        """Accept or refuse a reader's proposal, and write the decision down.

        **Acceptance is itself a row** — this card's words. So the proposal keeps its own
        row and gains a state, and a second row records who decided and which way. The
        decision row is written `state = 'accepted'` or `'rejected'` too, so it is never
        mistaken for an ordinary judgement and `agreed` counts only what was accepted.

        Applying the change to the gloss is the caller's: this store does not know what a
        gloss is, and the same decision may settle a lemma or a pointing later.
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
        import hmac

        with self.write() as db:
            row = db.execute("SELECT salt FROM judging WHERE id = 1").fetchone()
            if row is None:
                salt = secrets.token_hex(32)
                db.execute("INSERT INTO judging (id, salt) VALUES (1, ?)", (salt,))
            else:
                salt = str(row["salt"])
        return hmac.new(
            salt.encode("utf-8"), str(int(person_id)).encode("utf-8"), hashlib.sha256
        ).hexdigest()[:16]

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
    ) -> int:
        """Write down one line that came back changed. Returns the row's id.

        Only called where the diff is non-empty, so a correct line writes nothing: the
        table is a record of mistakes and not a log of turns. Keyed to a person, unlike
        `correct` above, because this is a fact about a learner and not about Hebrew.
        """
        with self.write() as db:
            cursor = db.execute(
                "INSERT INTO slip (person, language, at, chat, turn, wrote, recast,"
                " changed, why) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
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
                ),
            )
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
            f"SELECT id, language, at, chat, turn, wrote, recast, changed, why, known FROM slip"
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
            return cursor.rowcount > 0

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
            if row is None or row["spent"] or row["made"] < cutoff:
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

        Rotation, not reuse: the old row is revoked here and the caller chains the new
        one to it through `parent`. A refresh token presented twice is therefore a token
        whose second use finds it revoked, which is the signal that it leaked.
        """
        if not token:
            return None
        with self.write() as db:
            row = db.execute(
                "SELECT hash, person, client, scopes, resource, revoked FROM oauth_token"
                " WHERE hash = ? AND kind = 'refresh'",
                (digest(token),),
            ).fetchone()
            if row is None or row["revoked"]:
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
            "kind = 'build'",
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

    def jobs(self) -> list[dict[str, Any]]:
        rows = self.db.execute("SELECT * FROM job ORDER BY made").fetchall()
        return [dict(row) for row in rows]

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
