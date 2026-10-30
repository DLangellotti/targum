"""The language tables (targum-internal#576, slice 1 is #577): measured data about the
language, left behind by everything targum builds, kept in the corpus ledger and never
published.

Slice 1 is the store (`store`), the fold for `words` and `phrases` (`words`) and, by
the same fold, `roots` (`roots`, sublexical slice 1), the sweep over the texts already
built, and the guard: `public_text` is the only way into a fold,
and it fails closed on anything a reader imported. No page shows a table, no export
carries one, and no row names a reader or holds a sentence.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .. import ledger as ledger_module
from .registers import register_of
from .store import Store
from .words import TABLES, contribution_for, fold

__all__ = ["PublicText", "Store", "SweepResult", "fold", "public_text", "register_of", "sweep"]

log = logging.getLogger(__name__)

#: Only `public_text` holds this, so only it can make a `PublicText` that `fold` accepts.
_SEAL = object()


@dataclass(frozen=True)
class PublicText:
    """A built text the library holds publicly, and so one the tables may count."""

    folder: Path
    document_hash: str
    source: str
    licence: str
    register: str
    _seal: object = field(default=None, repr=False, compare=False)

    @property
    def sealed(self) -> bool:
        return self._seal is _SEAL


def public_text(folder: Path, root: Path | None = None) -> PublicText | None:
    """The built text in `folder`, if the tables may count it; None otherwise.

    None when the library root is not known (neither registered by a running `Library`
    nor passed as `root`), when the folder is in a reader's home (`p<id>` or `local`, as
    `ledger.home_of` decides it), when the ledger's row for the document says it is a
    private import, when `document.json` is a link out of the library, and when the
    folder has no readable `document.json`. Every doubt is a None: a text left uncounted
    costs a count, and a private one counted cannot be taken back out of a total.
    """
    library = ledger_module._registered_for(folder) or root
    if library is None:
        return None
    if ledger_module.home_of(folder, library) is not None:
        return None
    try:
        folder.resolve().relative_to(library.resolve())
    except (ValueError, OSError):
        return None
    document_file = folder / "document.json"
    if ledger_module._escapes(document_file, library):
        return None
    try:
        document = json.loads(document_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(document, dict):
        return None
    document_hash = str(document.get("content_hash") or "")
    source = str(document.get("source") or "")
    if not document_hash or not source:
        return None
    file = ledger_module.path()
    held = None
    if file is not None and file.is_file():
        book = ledger_module.Ledger(file)
        if book.is_private(document_hash):
            return None
        held = book.text(document_hash)
    licence = held.licence if held is not None else ledger_module._licence_of(folder, source)
    return PublicText(
        folder=folder,
        document_hash=document_hash,
        source=source,
        licence=licence,
        register=register_of(source),
        _seal=_SEAL,
    )


@dataclass
class SweepResult:
    """What one sweep did, folder by folder."""

    folded: int = 0
    #: Already counted under this annotator, or in a language the tables do not fold.
    unchanged: int = 0
    private: int = 0
    unreadable: int = 0
    by_register: dict[str, int] = field(default_factory=dict)


#: The two fields of an annotation a sweep needs before deciding to read the rest; both
#: are among the first the pipeline writes, and the file can be tens of megabytes.
_HASH = re.compile(r'"document_hash":\s*"([0-9a-f]{16,})"')
_ANNOTATOR = re.compile(r'"annotator":\s*"((?:[^"\\]|\\.)*)"')
_HEAD_BYTES = 4096


def _head(file: Path) -> tuple[str, str] | None:
    try:
        with file.open("rb") as handle:
            head = handle.read(_HEAD_BYTES).decode("utf-8", "ignore")
    except OSError:
        return None
    found_hash, found_tool = _HASH.search(head), _ANNOTATOR.search(head)
    if found_hash is None or found_tool is None:
        return None
    tool: Any = json.loads(f'"{found_tool.group(1)}"')
    return found_hash.group(1), str(tool)


def sweep(library: Path, store: Store) -> SweepResult:
    """Fold every public `annotation.json` under `library` that has no current
    contribution. Reads files and writes the tables; runs no annotator and spends
    nothing. Every reader's home is skipped, whatever lies beneath it.
    """
    result = SweepResult()
    for folder in ledger_module.text_folders(library):
        annotation_file = folder / "annotation.json"
        if not annotation_file.is_file():
            continue
        text = public_text(folder, library)
        if text is None:
            result.private += 1
            continue
        head = _head(annotation_file)
        if head is not None and head[0] == text.document_hash:
            ids = [contribution_for(text, table, head[1]).id for table in TABLES]
            if all(store.is_current(one) for one in ids):
                result.unchanged += 1
                continue
        try:
            annotation = json.loads(annotation_file.read_text(encoding="utf-8"))
            written = fold(text, annotation, store)
        except (OSError, ValueError, TypeError, AttributeError) as error:
            log.warning("tables: %s not folded: %s", folder, error)
            result.unreadable += 1
            continue
        if written:
            result.folded += 1
            result.by_register[text.register] = result.by_register.get(text.register, 0) + 1
        else:
            result.unchanged += 1
    return result
