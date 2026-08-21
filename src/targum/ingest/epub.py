"""EPUB, read with the standard library.

An EPUB is a zip of XHTML plus a package file naming the reading order. Chapters are
read in spine order, which is the order a reader would turn pages in, rather than the
order files happen to sit in the archive.

Parsed directly rather than through an EPUB library on purpose: the one mature Python
option is AGPL-licensed, and this project is MIT with a hosted future, where that
licence's network clause would bind the whole service. The format is simple enough
that the dependency bought very little.
"""

from __future__ import annotations

import posixpath
import warnings
import zipfile
from pathlib import Path
from urllib.parse import unquote

from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

from ..errors import TargumError
from ..models import Document
from .base import (
    Paragraph,
    blocks_from_paragraphs,
    build_document,
    normalize,
    with_front_matter,
)
from .htmltext import paragraphs_from_html


def _soup(text: str) -> BeautifulSoup:
    """Package XML through the lenient HTML parser, without the warning.

    The tags looked for here (item, itemref, rootfile, dc:title) survive HTML parsing
    unchanged, and the lenient parser also copes with the malformed OPF files real
    books ship with.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", XMLParsedAsHTMLWarning)
        return BeautifulSoup(text, "html.parser")


def _attr(tag: object, name: str) -> str:
    """A tag attribute as plain text; bs4 types attributes as possibly-lists."""
    value = tag.get(name) if tag is not None and hasattr(tag, "get") else None
    return value if isinstance(value, str) else ""


_DOCUMENT_TYPES = {"application/xhtml+xml", "text/html"}
_DOCUMENT_SUFFIXES = (".xhtml", ".html", ".htm")


class EpubIngester:
    name = "epub/3"

    def load(self, source: str) -> Document:
        path = Path(source)
        try:
            with zipfile.ZipFile(path) as archive:
                return self._read(archive, path)
        except (zipfile.BadZipFile, OSError, KeyError) as exc:
            raise TargumError(f"Could not read the EPUB: {path.name}", str(exc)) from exc

    def _read(self, archive: zipfile.ZipFile, path: Path) -> Document:
        opf_name = self._package_path(archive)
        opf = _soup(self._text(archive, opf_name))
        base = posixpath.dirname(opf_name)

        # Manifest: what each id names. Spine: the ids in reading order. The item
        # marked as the navigation document is a table of contents, not the text.
        manifest: dict[str, tuple[str, str, str]] = {}
        for item in opf.find_all("item"):
            href = unquote(_attr(item, "href"))
            manifest[_attr(item, "id")] = (
                posixpath.normpath(posixpath.join(base, href)) if href else "",
                _attr(item, "media-type").lower(),
                _attr(item, "properties"),
            )

        ordered: list[str] = []
        for ref in opf.find_all("itemref"):
            href, media_type, properties = manifest.get(_attr(ref, "idref"), ("", "", ""))
            if not href or "nav" in properties.split():
                continue
            if media_type in _DOCUMENT_TYPES or href.lower().endswith(_DOCUMENT_SUFFIXES):
                ordered.append(href)

        if not ordered:
            # Some books have an unusable spine. Fall back to every document, skipping
            # the declared navigation file.
            skip = {
                href for href, _, properties in manifest.values() if "nav" in properties.split()
            }
            ordered = [
                name
                for name in archive.namelist()
                if name.lower().endswith(_DOCUMENT_SUFFIXES) and name not in skip
            ]

        paragraphs: list[Paragraph] = []
        for name in ordered:
            try:
                html = self._text(archive, name)
            except KeyError:
                continue  # a spine entry pointing at a missing file is the book's bug
            paragraphs.extend(paragraphs_from_html(html))
        paragraphs = [(kind, level, normalize(text)) for kind, level, text in paragraphs]

        title = _metadata(opf, "dc:title") or path.stem
        author = _metadata(opf, "dc:creator")
        language = _metadata(opf, "dc:language")

        return build_document(
            str(path),
            blocks_from_paragraphs(with_front_matter(paragraphs, title, author)),
            ingester=self.name,
            language=language,
            title=title,
            author=author,
        )

    @staticmethod
    def _package_path(archive: zipfile.ZipFile) -> str:
        container = _soup(archive.read("META-INF/container.xml").decode("utf-8", "replace"))
        full_path = _attr(container.find("rootfile"), "full-path")
        if not full_path:
            raise TargumError("This EPUB names no package document.")
        return full_path

    @staticmethod
    def _text(archive: zipfile.ZipFile, name: str) -> str:
        return archive.read(name).decode("utf-8", "replace")


def _metadata(opf: BeautifulSoup, tag: str) -> str | None:
    found = opf.find(tag)
    text = found.get_text(strip=True) if found else ""
    return text or None
