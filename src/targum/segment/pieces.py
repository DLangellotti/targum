"""One long segment as pieces a model can read whole.

Both DICTA models stop reading at a fixed length and hand back the rest bare: the
lemmatizer at 512 tokens, the diacritizer at 2,048 characters. A segment is normally a
sentence and nowhere near either. A transcript nobody punctuated is not, and the words
past the ceiling came back with no dictionary form and no vowels (2026-09-14).
"""

from __future__ import annotations


def at_spaces(text: str, limit: int) -> list[tuple[int, int]]:
    """`(start, end)` spans no longer than `limit`, cut at whitespace, covering `text`.

    The spans are contiguous, so the pieces joined back together are `text` exactly, and
    each piece's own offsets plus its `start` are offsets into the whole. A cut falls on
    the last space inside the limit; a run with no space in it is cut at the limit, which
    only a string no model would read as words can produce.
    """
    spans: list[tuple[int, int]] = []
    start = 0
    while len(text) - start > limit:
        end = start + limit
        space = max(text.rfind(" ", start + 1, end + 1), text.rfind("\n", start + 1, end + 1))
        if space > start:
            end = space
        spans.append((start, end))
        start = end
    spans.append((start, len(text)))
    return spans
