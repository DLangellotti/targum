"""A conversation, written down as the text a targum is built from.

Always Hebrew (decided 2026-09-05). Both speakers' lines are Hebrew: the model's because
it wrote them so, the reader's because every reply opens with a `> ` recast of what the
reader said — as they wrote it if their Hebrew was right, corrected if not, translated if
it was another language — with their own words on the `= ` line under it. So the
reader's turn in the record is the recast, and their raw line is its translation. Nothing
the reader typed in English ever stands as a Hebrew sentence, and nothing without its
English is written down: the pipeline takes a carried translation whole (`Build.run`
uses `plan.carried` as the translation and buys nothing), so a line with no English
would open as a blank, and the record must not.

The file sits in the reader's own home, addressed by path and never by a scheme.
`Build.PUBLIC_SOURCES` gives `dialogue:` and every other public prefix a cache key with no
owner on it; a conversation filed under one would translate into the shared cache and be
reachable from another account. A path scopes the key to `p<id>` and enters no fetcher,
no catalogue and no sitemap. `promote.candidate` refuses it besides.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..paths import write_atomic
from . import hebrew

if TYPE_CHECKING:
    from ..accounts import Store

#: Its own suffix, so `ingest.load` routes it and nothing else is ever read as one.
SUFFIX = ".chat"

#: What targum is called on its side of the page.
TARGUM = "targum"


@dataclass(frozen=True)
class Line:
    speaker: str
    hebrew: str
    english: str

    def state(self) -> dict[str, str]:
        return asdict(self)


def lines(turns: list[dict[str, Any]], reader: str) -> tuple[list[Line], int]:
    """The conversation as speaker-and-line pairs, and how many reader turns were lost.

    A reader's turn is kept only through the recast the model gave it; a model reply that
    broke the contract and gave none loses that turn from the record, and the count says
    so rather than the record standing a line in the wrong language.
    """
    out: list[Line] = []
    dropped = 0
    awaiting_recast = False
    for turn in turns:
        role = str(turn.get("role") or "")
        said = str(turn.get("said") or "")
        if role == "user" and said:
            awaiting_recast = True
            continue
        if role != "assistant" or not said:
            continue
        recast_seen = False
        for pair in hebrew.pairs(said):
            if not pair.english:
                continue
            if pair.recast:
                recast_seen = True
                out.append(Line(reader, pair.hebrew, pair.english))
            else:
                out.append(Line(TARGUM, pair.hebrew, pair.english))
        if awaiting_recast and not recast_seen:
            dropped += 1
        awaiting_recast = False
    if awaiting_recast:
        dropped += 1
    return out, dropped


def path_for(home: Path, chat_id: str) -> Path:
    return home / "chats" / f"{chat_id}{SUFFIX}"


def write(store: Store, home: Path, chat_id: str, reader: str) -> tuple[Path, int, int]:
    """Write the conversation down in the reader's home. (path, lines kept, turns lost)."""
    turns = store.chat_turns(chat_id)
    kept, dropped = lines(turns, reader or "you")
    title = store.chat_title(chat_id)
    payload = {
        "chat": chat_id,
        "title": title or (kept[0].hebrew if kept else chat_id),
        "language": "he",
        "speakers": {"reader": reader or "you", "targum": TARGUM},
        "lines": [line.state() for line in kept],
        "dropped": dropped,
    }
    target = path_for(home, chat_id)
    write_atomic(target, json.dumps(payload, ensure_ascii=False, indent=1))
    return target, len(kept), dropped


def read(path: Path) -> dict[str, Any]:
    loaded = json.loads(path.read_text(encoding="utf-8"))
    return loaded if isinstance(loaded, dict) else {}
