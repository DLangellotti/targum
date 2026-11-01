"""What learners bring, pooled (David, 2026-11-01; design.md §12, "What learners bring is
counted in the tables, never kept"): every reader's own material counted into the
`imports` register of the language tables, as counts and nothing else.

A reader's home (`p<id>`) holds what they brought: links pasted, files uploaded, pages
photographed and read, a channel subscribed to. Each night this reads those homes'
`annotation.json` files, the same files a fold reads, and writes one contribution per
table, `words`, `phrases` and `roots`, under the register `imports`. The rules:

- **Ten readers a key.** A row (a key in a variant) is written only once the material of
  at least `FLOOR` distinct readers holds it. Below that it was only ever in memory.
- **A reader can say no.** A reader who has turned counting off on the account page
  (`accounts.Store.counts_material`) is never read, nor an operator, an admin or a test
  account, nor a home with no account behind it. The pool is made again from nothing
  every night, so a reader who turns it off, or leaves, is out of it by the next morning.
- **Nothing leads back.** The contribution's unit is the pool itself, `imports:pool`,
  never a document: the corpus ledger already holds a private text's home and its tokens
  (`ledger.text_homes`, the mirrored `tokens`), so a count filed by document, or by any
  hash of one, or a per-text bag of lemmas, could be matched to its reader. Who brought
  what is worked out in memory, one reader at a time, and only the floor's verdict
  leaves: no reader id, no count of readers, no document hash and no text is written,
  and the night before's pool is deleted, not superseded (`Store.replace_pool`).
- **Their text never.** A tally holds lemmas, runs of lemmas, roots, parts of speech and
  counts, as every table does.
- **Not what a model wrote.** A rewrite, a chat's speech, a scene and the weekly sit in a
  home too, and none of them is something a reader brought.

A text two readers brought is counted once, and both stand behind its keys. The whole
pool is off unless `TARGUM_IMPORT_COUNTS=1`: turning it on and publishing the privacy
notice's sentence about it are one decision (`on`), and with it off the pool is deleted.
No lemma below the floor is ever handed to anything, a model included, because none is
ever written down or returned.
"""

from __future__ import annotations

import json
import logging
import os
from collections import Counter
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .. import ledger as ledger_module
from . import roots
from .registers import IMPORTS
from .store import Contribution, Store
from .words import LANGUAGES, PHRASES, RULE, WORDS, count

log = logging.getLogger(__name__)

#: The switch, in the deployment's environment.
ENV = "TARGUM_IMPORT_COUNTS"

#: How many distinct readers' material must hold a key before it is written: the
#: privacy notice's "at least ten Data Subjects".
FLOOR = 10

#: The pooling rule's version, the pool's `tool`: a change to who is read or how a row
#: passes is a new number.
POOL_RULE = f"imports/1+floor{FLOOR}"

#: The pool's one unit: never a document.
UNIT = "imports:pool"
SOURCE = "readers' material"
LICENCE = "the readers' own material: counts only, no text, no reader, ten readers a row"

#: Every table the pool writes: the tables a fold writes, so what readers bring is
#: counted exactly as the shelf is.
TABLES = (WORDS, PHRASES, roots.ROOTS)

#: Sources a model wrote, which may sit in a home but no reader brought.
MODEL_WRITTEN = ("dialogue:", "weekly:", "chat:")


def on() -> bool:
    """Whether what readers bring is counted on this deployment.

    Off unless the deployment says so, as `TARGUM_EVENTS` was: the privacy notice names a
    legal basis for every category of processing, and publishing the sentence that
    covers this and switching it on are one decision, not a merge.
    """
    return os.environ.get(ENV, "").strip().lower() in {"1", "true", "yes"}


@dataclass
class PoolResult:
    """What one night's pool did. Counts of homes and texts only: never which."""

    #: Homes read: readers counted tonight.
    readers: int = 0
    #: Homes passed over: counting turned off, an operator, an admin, a test account, or
    #: no account at all.
    left_out: int = 0
    texts: int = 0
    #: Texts in a home that a model wrote (a rewrite, a chat's speech, a scene).
    model_written: int = 0
    unreadable: int = 0
    #: Rows written, by table.
    rows: dict[str, int] = field(default_factory=dict)
    #: Rows held in memory and dropped for being under the floor, by table.
    under_floor: dict[str, int] = field(default_factory=dict)


def _contribution(table: str) -> Contribution:
    rule = roots.rule() if table == roots.ROOTS else RULE
    return Contribution(
        table=table,
        register=IMPORTS,
        unit=UNIT,
        source=SOURCE,
        licence=LICENCE,
        tool=POOL_RULE,
        rule=rule,
    )


def homes(library: Path) -> dict[int, list[Path]]:
    """Each reader's home under `library` with its built texts, by person id. `local`,
    the laptop's home, belongs to no account and is never read."""
    found: dict[int, list[Path]] = {}
    for folder in ledger_module.text_folders(library):
        home = ledger_module.home_of(folder, library)
        if home is None or not home.startswith("p"):
            continue
        try:
            person = int(home[1:])
        except ValueError:
            continue
        found.setdefault(person, []).append(folder)
    return found


def _model_written(folder: Path, annotation: Mapping[str, Any]) -> bool:
    from ..rewrite import made_from

    if made_from(folder) is not None:
        return True
    try:
        document = json.loads((folder / "document.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        document = {}
    source = str((document or {}).get("source") or "") if isinstance(document, dict) else ""
    return source.startswith(MODEL_WRITTEN)


def _tallies(
    annotation: Mapping[str, Any], languages: Sequence[str]
) -> dict[str, Counter[tuple[str, str]]] | None:
    language = str(annotation.get("language") or "")
    if not any(language == one or language.startswith(f"{one}-") for one in languages):
        return None
    tokens = annotation.get("tokens")
    if not isinstance(tokens, Mapping):
        raise ValueError("the annotation has no tokens")
    return {**count(tokens), roots.ROOTS: roots.count(tokens, language)}


def pool(
    library: Path,
    store: Store,
    counted: Collection[int],
    *,
    floor: int = FLOOR,
    languages: Sequence[str] = LANGUAGES,
) -> PoolResult:
    """Make tonight's imports pool from the homes under `library` and put it in place of
    last night's. `counted` is the person ids whose material may be counted
    (`accounts.Store.counted_readers`); every other home is passed over unread.

    Reads files and writes the tables; runs no annotator and spends nothing.
    """
    result = PoolResult()
    #: (table) -> key -> how many readers' material holds it. In memory only.
    readers: dict[str, Counter[tuple[str, str]]] = {table: Counter() for table in TABLES}
    totals: dict[str, Counter[tuple[str, str]]] = {table: Counter() for table in TABLES}
    seen: set[str] = set()
    for person, folders in sorted(homes(library).items()):
        if person not in counted:
            result.left_out += 1
            continue
        result.readers += 1
        mine: dict[str, set[tuple[str, str]]] = {table: set() for table in TABLES}
        for folder in folders:
            file = folder / "annotation.json"
            if not file.is_file() or ledger_module._escapes(file, library):
                continue
            try:
                annotation = json.loads(file.read_text(encoding="utf-8"))
                if not isinstance(annotation, dict):
                    raise ValueError("not an annotation")
                if _model_written(folder, annotation):
                    result.model_written += 1
                    continue
                tallies = _tallies(annotation, languages)
            except (OSError, ValueError, TypeError, AttributeError) as error:
                log.warning("tables: a reader's text was not pooled: %s", type(error).__name__)
                result.unreadable += 1
                continue
            if tallies is None:
                continue
            result.texts += 1
            document = str(annotation.get("document_hash") or "")
            first = not document or document not in seen
            if document:
                seen.add(document)
            for table in TABLES:
                mine[table].update(tallies[table])
                if first:
                    totals[table].update(tallies[table])
        for table in TABLES:
            readers[table].update(mine[table])
    passed: dict[str, dict[tuple[str, str], int]] = {}
    for table in TABLES:
        passed[table] = {
            key: n for key, n in totals[table].items() if n > 0 and readers[table][key] >= floor
        }
        result.rows[table] = len(passed[table])
        result.under_floor[table] = len(totals[table]) - len(passed[table])
    store.replace_pool([_contribution(table) for table in TABLES], passed)
    return result
