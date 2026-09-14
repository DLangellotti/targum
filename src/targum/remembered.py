"""What a shelf row says about a reader, kept beside it so it is worked out once.

A row on the shelf is a few hundred bytes: a title, a word count, which chapters are
ready. Working it out read the reader's whole document, its segmentation, every
translation (twice), its annotation and its audio manifest, and did it for every text on
the shelf on every request. On 2026-09-14 that was 65 MB of JSON for a shelf of 163, and
Learn waited on it: 0.6 s while the box still held those files in memory, 31 s once it
had let them go — which a box that also holds a BERT model does often.

So each answer is written into `shelf.json` beside the reader, stamped with the size and
modification time of every file it was read from, the same way `coverage.lemmas` keeps
its answer. A request stats those files and reads one small file. A rebuilt text changes
its stamp and is worked out again; a copy that kept the times is still right, and one
that did not is recounted. Nothing that depends on the running code rather than the files
— what the catalogue says, whether a cover has been drawn — belongs in here.
"""

from __future__ import annotations

import contextlib
import json
import threading
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

from .paths import write_atomic

SHELF = "shelf.json"

#: Raise this when what is worked out changes rather than what it is read from — a new
#: field, or a chapter split drawn another way — and every kept answer is worked out again.
FORMAT = 1


def stamp(inputs: Iterable[Path]) -> list[list[Any]]:
    """The size and time of each file an answer was read from, and of each one missing."""
    marks: list[list[Any]] = [["format", FORMAT, 0]]
    for path in inputs:
        try:
            stat = path.stat()
            marks.append([path.name, stat.st_mtime_ns, stat.st_size])
        except OSError:
            marks.append([path.name, 0, -1])
    return marks


class Remembered:
    """Answers about readers, held in memory and in each reader's own `shelf.json`."""

    def __init__(self) -> None:
        self._held: dict[Path, dict[str, Any]] = {}
        # One writer at a time: `write_atomic` names its temporary file by process, so
        # two threads writing one folder's file would write the same temporary.
        self._writing = threading.Lock()

    def _entries(self, folder: Path) -> dict[str, Any]:
        entries = self._held.get(folder)
        if entries is None:
            try:
                loaded = json.loads((folder / SHELF).read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                loaded = None
            entries = loaded if isinstance(loaded, dict) else {}
            self._held[folder] = entries
        return entries

    def get(self, folder: Path, key: str, inputs: Iterable[Path], work: Callable[[], Any]) -> Any:
        """The answer to `key` for this reader, worked out again only if an input changed.

        `work` must return something JSON can hold, and must read nothing but `inputs`.
        """
        marks = stamp(inputs)
        entries = self._entries(folder)
        kept = entries.get(key)
        if isinstance(kept, dict) and kept.get("stamp") == marks:
            return kept.get("value")
        value = work()
        with self._writing:
            entries[key] = {"stamp": marks, "value": value}
            text = json.dumps(entries, ensure_ascii=False)
            # A read-only or full disk costs the saving, not the answer. And a folder the
            # trash emptied while this was being worked out stays gone: `write_atomic`
            # would make it again, holding nothing but this.
            if folder.is_dir():
                with contextlib.suppress(OSError):
                    write_atomic(folder / SHELF, text)
        return value
