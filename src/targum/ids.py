"""Stable identifiers for documents and segments.

A segment ID is position plus content. Editing a sentence gives it a new ID, which is
what we want: a translation or annotation keyed to the old text should not silently
rebind to different words.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata


def content_hash(*parts: str) -> str:
    h = hashlib.sha256()
    for part in parts:
        h.update(part.encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()


def short_hash(text: str, length: int = 6) -> str:
    normalized = unicodedata.normalize("NFC", text).strip()
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:length]


def block_id(index: int) -> str:
    return f"b{index:04d}"


def segment_id(block_index: int, sentence_index: int, text: str) -> str:
    return f"{block_index:04d}.{sentence_index:03d}-{short_hash(text)}"


# Characters a filesystem or a shell would rather not see. Letters in any script are
# fine: a Hebrew text deserves a Hebrew filename, not a hash.
_UNSAFE = re.compile(r'[\\/:*?"<>|\x00-\x1f]+')
_SPACE = re.compile(r"[\s_]+")
_TRIM = re.compile(r"^[-.]+|[-.]+$")


def slug(text: str, fallback: str = "text") -> str:
    """A filesystem-safe name that keeps the script it came in."""
    cleaned = _TRIM.sub("", _SPACE.sub("-", _UNSAFE.sub("", text)).strip())
    cleaned = cleaned[:60].rstrip("-")
    if not cleaned:
        return f"{fallback}-{short_hash(text)}"
    return cleaned.lower() if cleaned.isascii() else cleaned
