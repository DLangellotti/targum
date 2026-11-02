"""The corrections ledger (targum-internal#585, language tables spec §4): before, after,
why and stage for every fix, kept as rows.

It is not a store of its own. It is the `correction` table of #164, in the account
database, with three more columns (schema 57): `kind`, the class of mistake, from the
closed list `KINDS`; `tool`, what made the "before" (`claude-sonnet-5`,
`dicta/menaked/1`, a voice); and `run`, the batch it was fixed in.

**`record` is the one door**, and it is public so the private half can call it: the
dialogue writer's editor and director passes and the weekly's writer import it like any
other public module. That direction is the safe one. The lazy-import rule is about the
public half reaching into the private half, which never happens here.

- **A failed write never fails a run.** It is logged and `record` returns None, as the
  corpus ledger does: a fix that could not be kept is a lost row, and a run stopped for
  it would lose the work as well.
- **One fix is one row.** The same stage, unit, before and after (and the same judge,
  which for a model or the author is nobody) is never a second row, so a run that meets
  a mistake twice, or is run twice, or is pushed twice, keeps one. This is
  `scripts/scene_corrections.py`'s duplicate skip, made the rule.
- **`unit` is where**: the line or section the fix was made on, such as `he-06 t3`. It
  is written to the row's `span`, which is what that column has always held.

`recurrence` is the count of mistakes that recur, by kind and by tool. `gold` is the
eval set: the author's own hand, a paid editor's own fixes, and what a person accepted
(spec, Q5; David, 2026-11-02, for the editor). A model's fix counts toward the
recurrence and stays out of the gold set until somebody accepts it, and so does a
reader's proposal.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..accounts import Store

log = logging.getLogger(__name__)

#: The classes of mistake, closed: a recurrence count over free text counts spellings.
KINDS = ("nikkud", "gender", "wording", "stress", "lifted", "gloss", "segmentation", "other")

#: Who made a fix, as a role and never a person, as everywhere in `correction`.
ROLES = ("author", "editor", "reader", "model")

#: What `recurrence` may group by.
BY = ("kind", "tool", "stage", "who", "run")

#: The roles whose rows a laptop carries to the box. A reader's rows are the box's own;
#: one on the laptop was made by somebody testing a local server.
#:
#: An editor's judge is a pseudonym salted per database (`Store.editor_judge`), so the
#: same editor filed on the laptop and on the box would be two judges there. Editor
#: passes are filed in one place only, the laptop (David, 2026-11-02), so nothing
#: re-keys them; filing one on the box as well would need that first.
PUSHED = ("author", "editor", "model")

#: The hands whose own fixes are gold without anybody accepting them: the author's,
#: and a paid human editor's (David, 2026-11-02).
GOLD_HANDS = ("author", "editor")


def record(
    store: Store | Path | str,
    *,
    stage: str,
    before: str,
    after: str,
    why: str,
    kind: str,
    tool: str = "",
    unit: str = "",
    who: str = "model",
    run: str = "",
    term: str = "",
    language: str = "he",
    target: str = "",
    text: str = "",
    context: str = "",
    state: str = "",
    licence: str = "targum",
    judge: str = "",
) -> int | None:
    """Keep one fix. Returns the new row's id, 0 when this fix is already kept, or None
    when it could not be written, which is logged and never raised.

    `stage` is where it was caught: editor, director, asr, voice, author, reader, or a
    pipeline stage such as scene or gloss. `who` is the role behind the "after": a
    model's pass is `model`, and only `author` and `editor` rows and accepted ones are
    gold. An ASR
    flag is written `state="proposed"` until a person settles it. `term` is read off
    `before` (its letters, points taken off) where it is not given.
    """
    try:
        if kind not in KINDS:
            log.warning("fixes: kind %r is not one of %s; kept as other", kind, ", ".join(KINDS))
            kind = "other"
        if who not in ROLES:
            raise ValueError(f"who {who!r} is not one of {', '.join(ROLES)}")
        if not stage:
            raise ValueError("a fix needs its stage")
        if before == after:
            raise ValueError("before and after are the same, so nothing was fixed")
        keeping = _store(store)
        return keeping.correct_once(
            stage,
            who=who,
            term=term or _letters(before or after),
            language=language,
            target=target,
            text=text,
            span=unit,
            before=before,
            after=after,
            judge=judge,
            state=state,
            licence=licence,
            context=context,
            reason=why,
            kind=kind,
            tool=tool,
            run=run,
        )
    except (sqlite3.Error, OSError, ValueError, TypeError) as error:
        log.warning("fixes: a %s fix in %s was not kept: %s", stage, unit or "?", error)
        return None


def kind_of(before: str, after: str) -> str:
    """`nikkud` where the letters are the same and only the points moved, `wording`
    where the letters changed: the one split a pair of strings can make on its own."""
    return "nikkud" if _letters(before) == _letters(after) else "wording"


def _letters(text: str) -> str:
    from ..dialogue.checks import bare

    return bare(text)


def _store(store: Store | Path | str) -> Store:
    from ..accounts import Store

    return store if isinstance(store, Store) else Store(Path(store).expanduser())


# --- reading the ledger -------------------------------------------------------------

#: One fix, however many rows hold it: a proposal and its acceptance are two rows and
#: one fix.
_FIX = "stage || char(31) || span || char(31) || before || char(31) || after"


def recurrence(store: Store, by: Sequence[str] = ("kind",)) -> list[dict[str, Any]]:
    """How many fixes each kind (or tool, stage, role, run) holds, most first.

    `fixes` counts a fix once however many rows hold it, `units` the places they were
    made, and `recurring` the before → after pairs made in more than one place: the
    mistakes that come back. A refused proposal is not a fix and is left out; a model's
    fix and an unsettled ASR flag are counted, because a mistake caught is a mistake
    made whether or not a person has looked yet.
    """
    wrong = [one for one in by if one not in BY]
    if wrong:
        raise ValueError(f"cannot group by {', '.join(wrong)}: say {', '.join(BY)}")
    columns = list(dict.fromkeys(by)) or ["kind"]
    group = ", ".join(columns)
    rows = store.db.execute(
        f"WITH fix AS (SELECT {group}, span, before, after, {_FIX} AS one FROM correction"
        " WHERE state <> 'rejected' AND before <> after),"
        f" pair AS (SELECT {group}, before, after FROM fix GROUP BY {group}, before, after"
        " HAVING COUNT(DISTINCT span) > 1)"
        f" SELECT {group}, COUNT(DISTINCT one) AS fixes, COUNT(DISTINCT span) AS units,"
        f" (SELECT COUNT(*) FROM pair WHERE "
        + " AND ".join(f"pair.{c} = fix.{c}" for c in columns)
        + f") AS recurring FROM fix GROUP BY {group} ORDER BY fixes DESC, {group}"
    ).fetchall()
    return [dict(row) for row in rows]


def recurring(store: Store, limit: int = 20) -> list[dict[str, Any]]:
    """The before → after pairs fixed in the most places, with their kind and stage."""
    rows = store.db.execute(
        "SELECT stage, kind, before, after, COUNT(DISTINCT span) AS units,"
        " GROUP_CONCAT(DISTINCT tool) AS tools FROM correction"
        " WHERE state <> 'rejected' AND before <> after"
        " GROUP BY stage, kind, before, after HAVING COUNT(DISTINCT span) > 1"
        " ORDER BY units DESC, stage, before LIMIT ?",
        (limit,),
    ).fetchall()
    return [dict(row) for row in rows]


#: What a gold row carries. The judge's pseudonym stays home, and so does the row id.
GOLD_FIELDS = (
    "stage",
    "kind",
    "tool",
    "language",
    "target",
    "term",
    "span",
    "before",
    "after",
    "who",
    "reason",
    "context",
    "text",
    "licence",
    "at",
)


def gold(store: Store, stage: str = "") -> list[dict[str, Any]]:
    """The eval set (spec, Q5): the author's own hand, a paid editor's own fixes, and
    every fix a person accepted (David, 2026-11-02, for the editor: a paid human
    editor is a person, so their fix needs nobody's acceptance to be gold).

    A model's fix and an unsettled proposal are not here, nor is a refused one, nor
    the row that refused it. A
    deletion (`after` empty) is not an answer to score against and is left out, as
    `Store.agreed` leaves it. A proposal and the row that accepted it are one fix and
    one line, the earlier of the two.
    """
    hands = ", ".join("?" for _ in GOLD_HANDS)
    where = [
        f"((who IN ({hands}) AND state = '') OR state = 'accepted')",
        "after <> ''",
        "before <> after",
    ]
    values: list[Any] = list(GOLD_HANDS)
    if stage:
        where.append("stage = ?")
        values.append(stage)
    rows = store.db.execute(
        f"SELECT * FROM correction WHERE {' AND '.join(where)} ORDER BY at, id", values
    ).fetchall()
    seen: set[tuple[str, ...]] = set()
    out: list[dict[str, Any]] = []
    for row in rows:
        key = tuple(str(row[k]) for k in ("stage", "language", "target", "term", "span"))
        key += (str(row["before"]), str(row["after"]))
        if key in seen:
            continue
        seen.add(key)
        out.append({k: row[k] for k in GOLD_FIELDS})
    return out


# --- carrying the laptop's rows to the box (targum-internal#587) --------------------


def export(store: Store) -> Iterator[str]:
    """The fixes this machine holds by a hand that travels, one JSON line each, beside
    the tables' own lines in `targum tables push`. A reader's rows never travel."""
    from ..accounts import CORRECTION_FIELDS

    marks = ", ".join("?" for _ in PUSHED)
    for row in store.db.execute(
        f"SELECT * FROM correction WHERE who IN ({marks}) ORDER BY at, id", PUSHED
    ).fetchall():
        line = {name: row[name] for name in ("at", *CORRECTION_FIELDS)}
        yield json.dumps({"correction": line}, ensure_ascii=False, sort_keys=True)


def is_fix_line(raw: str) -> bool:
    """Whether one line of a push is a fix rather than a table contribution."""
    return raw.lstrip().startswith('{"correction"')


@dataclass
class Imported:
    added: int = 0
    unchanged: int = 0
    refused: int = 0


def take(store: Store, lines: Iterable[str]) -> Imported:
    """Keep the fixes another machine exported. Run twice, it adds nothing: a fix
    already here is the same row (`Store.correct_once`)."""
    from ..accounts import CORRECTION_FIELDS

    result = Imported()
    for raw in lines:
        try:
            row = json.loads(raw)["correction"]
            fields = {name: str(row.get(name) or "") for name in CORRECTION_FIELDS}
            stage, who = fields.pop("stage"), fields.pop("who")
            if not stage or who not in PUSHED:
                raise ValueError(f"not a fix that travels: {stage!r} by {who!r}")
            written = store.correct_once(stage, who=who, at=int(row.get("at") or 0), **fields)
        except (ValueError, KeyError, TypeError, sqlite3.Error) as error:
            log.warning("fixes: a pushed line was refused: %s", error)
            result.refused += 1
            continue
        if written:
            result.added += 1
        else:
            result.unchanged += 1
    return result
