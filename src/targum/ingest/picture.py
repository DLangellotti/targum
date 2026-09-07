"""Pictures: a screenshot, a phone photo, or a folder of them that is one text.

The reading is `vision.read_pages`, and it is cached by the picture's bytes, so the
ingester asks for it whether or not anything has been read yet: on the server the
price quote read the pictures already and this costs nothing; on the command line
this is the reading, on the operator's own key. A folder is a set — the pages of one
handout, photographed one after another — and its files are read in name order, which
is the order the upload door numbered them in.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from .. import vision
from ..errors import TargumError
from ..models import Document
from ..usage import Usage
from .pages import document_from_pages


def pages_of(source: str | Path) -> list[Path]:
    """The pictures a source stands for, in the order they are read."""
    path = Path(source)
    if path.is_dir():
        found = sorted(p for p in path.iterdir() if p.is_file() and vision.is_picture(p))
        if not found:
            raise TargumError(f"No pictures in {path.name}.")
        return found
    return [path]


def is_pictures(source: str | Path) -> bool:
    path = Path(source)
    if path.is_dir():
        return any(p.is_file() and vision.is_picture(p) for p in path.iterdir())
    return vision.is_picture(path)


def bytes_hash(paths: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in paths:
        digest.update(path.read_bytes())
        digest.update(b"\x00")
    return digest.hexdigest()


class PictureIngester:
    name = "picture/2"

    def __init__(self, usage: Usage | None = None) -> None:
        # Where the reading's tokens land when this is the reading. The server reads at
        # prepare with the job's own; a bare call keeps its own count.
        self.usage = usage if usage is not None else Usage()

    def load(self, source: str) -> Document:
        paths = pages_of(source)
        reads = vision.read_pages(paths, usage=self.usage)
        pages = [read.lines for read in reads]
        if not any(line.strip() for lines in pages for line in lines):
            raise TargumError(
                "No text could be read in that picture.",
                "A clearer photo, or a screenshot, reads better.",
            )
        document = document_from_pages(
            str(source),
            pages,
            ingester=self.name,
            source_hash=bytes_hash(paths),
            # One chat photographed over several screens is one conversation: the
            # first page says what it is, and the rest are read the same way.
            conversation=any(read.conversation for read in reads),
        )
        if not document.blocks:
            raise TargumError("No text could be read in that picture.")
        return document
