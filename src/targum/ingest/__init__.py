"""Ingest dispatch: pick a reader for the source, or say plainly what is missing."""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlparse

from ..audio import is_audio, is_drm
from ..errors import TargumError, UnsupportedSource
from ..ids import content_hash
from ..models import Document
from ..video import is_video
from . import fetch
from .audio import AudioIngester
from .base import Ingester, detect_language, normalize, parse_frontmatter, to_markdown
from .epub import EpubIngester
from .markdown import MarkdownIngester
from .plaintext import PlainTextIngester
from .subtitles import SubtitleIngester
from .url import UrlIngester

__all__ = [
    "Ingester",
    "detect_language",
    "load",
    "normalize",
    "parse_frontmatter",
    "sources",
    "to_markdown",
]

_BY_SUFFIX: dict[str, Ingester] = {
    ".txt": PlainTextIngester(),
    ".text": PlainTextIngester(),
    ".md": MarkdownIngester(),
    ".markdown": MarkdownIngester(),
    ".epub": EpubIngester(),
    ".srt": SubtitleIngester(),
    ".vtt": SubtitleIngester(),
}


def sources() -> list[str]:
    from ..audio import AUDIO_SUFFIXES

    return sorted(
        {*_BY_SUFFIX, *AUDIO_SUFFIXES, "http(s)://", *(f"{name}:" for name in fetch.FETCHERS)}
    )


def load(source: str, language: str | None = None) -> Document:
    document = _load(source)
    path = Path(source)
    if path.exists() and path.is_file() and not document.source_hash:
        # What the file held when it was read. Lets a rerun tell "the user edited the
        # artifact" apart from "the user pointed this at a different text". Only where
        # the ingester did not already say: an audio document's hash states which parts
        # have been transcribed, and decoding a recording as UTF-8 says nothing anyway.
        document.source_hash = content_hash(path.read_bytes().decode("utf-8", "replace"))
    if language:
        document.language = language
    return document


# Two letters or more, so a Windows drive letter is a path rather than a scheme.
_SCHEME = re.compile(r"^[a-z][a-z0-9+.-]+:", re.I)


def _load(source: str) -> Document:
    if fetch.is_identifier(source):
        return fetch.load(source)

    if urlparse(source).scheme in {"http", "https"}:
        return UrlIngester().load(source)

    if _SCHEME.match(source) and not Path(source).exists():
        # It was addressed like an identifier, so answer as one rather than reporting
        # a missing file the user never meant to name.
        raise UnsupportedSource(
            f"targum does not know the source '{source.split(':', 1)[0]}'.",
            f"Supported: {', '.join(sources())}",
        )

    path = Path(source)
    suffix = path.suffix.lower()

    if suffix == ".pdf":
        raise UnsupportedSource("PDF ingest is not supported yet.")
    if is_drm(source):
        raise UnsupportedSource("This file is protected, so targum cannot read it.")
    if not path.exists():
        raise TargumError(f"No such file: {source}")
    if is_audio(source) or is_video(source):
        # A video is the audio import with pictures kept: the same ingester reads the
        # same transcripts, and the pictures never enter the document at all.
        return AudioIngester().load(source)

    ingester = _BY_SUFFIX.get(suffix)
    if ingester is None:
        raise UnsupportedSource(
            f"targum does not read '{suffix or path.name}' files.",
            f"Supported: {', '.join(sources())}",
        )
    return ingester.load(source)
