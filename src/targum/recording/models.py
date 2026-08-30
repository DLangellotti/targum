"""What a recording is.

Addressed by ref throughout — "Ruth 1:1" — and never by position. A recording is aligned
to a text once and then outlives every rebuild of it: the segmenter may change, the
edition may be re-fetched, the ids are hashes of the words. The verse number is the one
thing the recording and the text will still agree on in a year, which is why the ref was
put on the block at ingest rather than worked out here.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class Part(BaseModel):
    """One file of a recording, and where each verse is inside it.

    A file per chapter rather than per book or per verse. Per book is unplayable in a
    reader that fetches nothing — a chapter of Genesis would carry ninety megabytes of
    Exodus with it. Per verse is a folder of a thousand files and a fetch for each, which
    is the same rule broken from the other end.
    """

    #: What this part covers, as a person would say it: "Ruth 1".
    ref: str
    #: The audio file, named relative to the recording's own folder, so the folder can be
    #: copied between machines without rewriting anything.
    audio: str
    #: Verse ref to [start, end] in seconds, into this part's own file.
    spans: dict[str, list[float]] = Field(default_factory=dict)


class Recording(BaseModel):
    """Somebody's reading of a text, aligned to it verse by verse."""

    #: The document this belongs to, as the document names itself: "sefaria:Ruth".
    source: str
    #: Who read it. Not optional: every recording the library can use is used under a
    #: licence that requires the reader be named, and a credit that lives only in a
    #: spreadsheet is a credit the person listening never sees.
    credit: str
    #: The licence, as it is written — "CC BY-SA 4.0".
    licence: str
    #: Where the licence itself can be read. Shown as a link, so it is left empty rather
    #: than guessed: a wrong licence link is worse than none.
    licence_url: str = ""
    parts: list[Part] = Field(default_factory=list)

    def part_for(self, refs: list[str]) -> Part | None:
        """The part that holds these verses, or None if no part holds any of them.

        By what the spans actually contain rather than by the order the parts are in. A
        reader may be built for one chapter, for a range, or for a whole book, and the
        section it is asking about is not reliably the nth part of anything.
        """
        wanted = [ref for ref in refs if ref]
        if not wanted:
            return None
        for part in self.parts:
            if any(ref in part.spans for ref in wanted):
                return part
        return None
