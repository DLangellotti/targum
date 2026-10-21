"""An Anki deck with sound: the `.apkg` Your Words exports (targum-internal#496).

A beta reader, 2026-10-21: "I love the export to anki … but it doesn't export the sound."
The deck had been a tab-separated file the browser wrote, which Anki imports natively but
which cannot carry media: `[sound:x.mp3]` plays only where the file is already in the
collection's media folder. An `.apkg` carries both, so the server builds one (David,
2026-10-21; design.md §12, "The Anki deck carries each word's sound").

An `.apkg` is a zip holding `collection.anki2`, a SQLite collection in Anki's schema 11
(which every Anki since 2.1 imports), a `media` file mapping each numbered media file to
its name, and the media files themselves as `0`, `1`, …. Only what an import reads is
written: one notetype, one deck, a note and a card per word. Nothing here talks to a
network or a model; the sounds are handed in as files.

A note's id and guid are fixed by the word and language, so exporting again and
importing over an earlier deck updates its notes rather than duplicating them.
"""

from __future__ import annotations

import hashlib
import html
import json
import sqlite3
import tempfile
import time
import zipfile
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

#: The notetype's id: fixed, so every targum deck shares one notetype in a collection.
MODEL_ID = 1729000000496
FIELDS = ("Word", "Meaning", "Sound")

#: Front and back, as Anki's own Basic draws them, with the sound on the front so it plays
#: when the card is shown.
FRONT = '<div class="word">{{Word}}</div>{{Sound}}'
BACK = '{{FrontSide}}<hr id="answer">{{Meaning}}'
CSS = (
    ".card { font-family: sans-serif; font-size: 24px; text-align: center; color: black; "
    "background-color: white; }\n.word { font-size: 40px; }"
)


@dataclass(frozen=True)
class Note:
    """One word: its face, its back, its tags, and the sound file to play, if any."""

    word: str
    meaning: str
    tags: tuple[str, ...]
    key: str
    sound: Path | None = None


def _id(*parts: str) -> int:
    """A stable positive 63-bit id from text."""
    digest = hashlib.sha1("\x1f".join(parts).encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") & ((1 << 62) - 1) or 1


def _csum(text: str) -> int:
    return int(hashlib.sha1(text.encode("utf-8")).hexdigest()[:8], 16)


SCHEMA = """
CREATE TABLE col (id integer primary key, crt integer not null, mod integer not null,
  scm integer not null, ver integer not null, dty integer not null, usn integer not null,
  ls integer not null, conf text not null, models text not null, decks text not null,
  dconf text not null, tags text not null);
CREATE TABLE notes (id integer primary key, guid text not null, mid integer not null,
  mod integer not null, usn integer not null, tags text not null, flds text not null,
  sfld integer not null, csum integer not null, flags integer not null, data text not null);
CREATE TABLE cards (id integer primary key, nid integer not null, did integer not null,
  ord integer not null, mod integer not null, usn integer not null, type integer not null,
  queue integer not null, due integer not null, ivl integer not null, factor integer not null,
  reps integer not null, lapses integer not null, left integer not null, odue integer not null,
  odid integer not null, flags integer not null, data text not null);
CREATE TABLE revlog (id integer primary key, cid integer not null, usn integer not null,
  ease integer not null, ivl integer not null, lastIvl integer not null, factor integer not null,
  time integer not null, type integer not null);
CREATE TABLE graves (usn integer not null, oid integer not null, type integer not null);
CREATE INDEX ix_notes_usn on notes (usn);
CREATE INDEX ix_cards_usn on cards (usn);
CREATE INDEX ix_revlog_usn on revlog (usn);
CREATE INDEX ix_cards_nid on cards (nid);
CREATE INDEX ix_cards_sched on cards (did, queue, due);
CREATE INDEX ix_revlog_cid on revlog (cid);
CREATE INDEX ix_notes_csum on notes (csum);
"""


def _model(now: int, deck_id: int) -> dict[str, object]:
    return {
        "id": MODEL_ID,
        "name": "targum word",
        "type": 0,
        "mod": now,
        "usn": -1,
        "sortf": 0,
        "did": deck_id,
        "tmpls": [
            {
                "name": "Card 1",
                "ord": 0,
                "qfmt": FRONT,
                "afmt": BACK,
                "did": None,
                "bqfmt": "",
                "bafmt": "",
            }
        ],
        "flds": [
            {"name": name, "ord": n, "sticky": False, "rtl": False, "font": "Arial", "size": 20}
            for n, name in enumerate(FIELDS)
        ],
        "css": CSS,
        "latexPre": "",
        "latexPost": "",
        "tags": [],
        "vers": [],
        "req": [[0, "any", [0]]],
    }


def _deck(deck_id: int, name: str, now: int) -> dict[str, object]:
    return {
        "id": deck_id,
        "name": name,
        "mod": now,
        "usn": -1,
        "lrnToday": [0, 0],
        "revToday": [0, 0],
        "newToday": [0, 0],
        "timeToday": [0, 0],
        "collapsed": False,
        "desc": "",
        "dyn": 0,
        "conf": 1,
        "extendNew": 10,
        "extendRev": 50,
    }


DCONF = {
    "1": {
        "id": 1,
        "name": "Default",
        "mod": 0,
        "usn": 0,
        "maxTaken": 60,
        "autoplay": True,
        "timer": 0,
        "replayq": True,
        "dyn": False,
        "new": {
            "delays": [1, 10],
            "ints": [1, 4, 7],
            "initialFactor": 2500,
            "order": 1,
            "perDay": 20,
            "bury": True,
        },
        "rev": {"perDay": 200, "ease4": 1.3, "fuzz": 0.05, "maxIvl": 36500, "bury": True},
        "lapse": {"delays": [10], "mult": 0, "minInt": 1, "leechFails": 8, "leechAction": 0},
    }
}


def build(deck_name: str, notes: Iterable[Note]) -> bytes:
    """The `.apkg` for these notes, as bytes."""
    now = int(time.time())
    deck_id = _id("deck", deck_name)
    with tempfile.TemporaryDirectory() as where:
        folder = Path(where)
        database = folder / "collection.anki2"
        connection = sqlite3.connect(database)
        try:
            connection.executescript(SCHEMA)
            default = _deck(1, "Default", now)
            connection.execute(
                "INSERT INTO col VALUES (1, ?, ?, ?, 11, 0, 0, 0, ?, ?, ?, ?, '{}')",
                (
                    now,
                    now * 1000,
                    now * 1000,
                    json.dumps({"nextPos": 1, "curModel": str(MODEL_ID)}),
                    json.dumps({str(MODEL_ID): _model(now, deck_id)}, ensure_ascii=False),
                    json.dumps(
                        {"1": default, str(deck_id): _deck(deck_id, deck_name, now)},
                        ensure_ascii=False,
                    ),
                    json.dumps(DCONF),
                ),
            )
            media: dict[str, str] = {}
            files: list[tuple[str, Path]] = []
            for position, note in enumerate(notes):
                sound = ""
                if note.sound is not None and note.sound.is_file():
                    name = f"targum-{_id('sound', note.key):x}{note.sound.suffix}"
                    if name not in media.values():
                        number = str(len(files))
                        media[number] = name
                        files.append((number, note.sound))
                    sound = f"[sound:{name}]"
                # Anki draws fields as HTML: the reader's own words are escaped, so a
                # meaning with a < in it reads as < (qa on #854).
                fields = "\x1f".join((html.escape(note.word), html.escape(note.meaning), sound))
                note_id = _id("note", note.key)
                connection.execute(
                    "INSERT OR REPLACE INTO notes VALUES (?, ?, ?, ?, -1, ?, ?, ?, ?, 0, '')",
                    (
                        note_id,
                        f"targum-{note_id:x}",
                        MODEL_ID,
                        now,
                        " " + " ".join(note.tags) + " ",
                        fields,
                        note.word,
                        _csum(note.word),
                    ),
                )
                connection.execute(
                    "INSERT OR REPLACE INTO cards VALUES "
                    "(?, ?, ?, 0, ?, -1, 0, 0, ?, 0, 0, 0, 0, 0, 0, 0, 0, '')",
                    (_id("card", note.key), note_id, deck_id, now, position + 1),
                )
            connection.commit()
        finally:
            connection.close()
        out = folder / "deck.apkg"
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as package:
            package.write(database, "collection.anki2")
            package.writestr("media", json.dumps(media))
            for number, path in files:
                package.write(path, number)
        return out.read_bytes()
