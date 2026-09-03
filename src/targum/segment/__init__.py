"""Segmentation."""

from __future__ import annotations

from .base import Segmenter, segment_document
from .hebrew import HebrewSegmenter
from .stanza_segmenter import (
    StanzaSegmenter,
    download,
    downloaded_languages,
    has_processors,
    is_downloaded,
    remove,
    stanza_code,
)

__all__ = [
    "HebrewSegmenter",
    "Segmenter",
    "StanzaSegmenter",
    "download",
    "downloaded_languages",
    "has_processors",
    "is_downloaded",
    "remove",
    "segment_document",
    "stanza_code",
]
