"""A PDF with a text layer: a handout, an exported article, a printed page saved as one.

Read with `pypdf`, page by page, and no model. Two things about Hebrew in a text layer,
both measured on 2026-09-07 with a page Chromium printed:

- pypdf's default extraction returns a Hebrew line in reading order, and its "layout"
  mode and pdfminer both return it backwards. So the default it is, and no layout.
- The layer spells ayin and a few other letters as their presentation forms (U+FB20…)
  when the font subset did. NFKC folds them back; NFC alone does not.

A line that mixes Hebrew and English comes out with the two halves swapped by every
extractor tried. It is kept, and counted as doubtful, so the card says how many lines
it could not read cleanly rather than passing a scrambled one off as the page.

A PDF whose pages have no text layer is a scan, and scans are #197's: refused here in
one sentence, before anything is priced. Thirty pages is the ceiling, the same as a
set of pictures — a book is a book.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from pathlib import Path
from typing import Any

from ..errors import TargumError, UnsupportedSource
from ..models import Document
from ..vision import MAX_PAGES
from .base import normalize
from .pages import document_from_pages, mixed

#: Below this many letters a page, on average, the PDF is pictures of pages.
SCAN_LETTERS_PER_PAGE = 20

SCAN = "This PDF is a scan, and targum does not read scans yet."
PROTECTED = "This PDF is protected, so targum cannot read it."
MISSING = "Reading PDFs needs the `bring` extra: uv sync --extra bring"

_LETTER = re.compile(r"[^\W\d_]")


def _reader(path: Path) -> Any:
    try:
        from pypdf import PdfReader
    except ImportError as missing:  # pragma: no cover - the extra is installed in CI
        raise TargumError(MISSING) from missing
    try:
        reader = PdfReader(str(path))
        if reader.is_encrypted:
            try:
                reader.decrypt("")
            except Exception as locked:
                raise TargumError(PROTECTED) from locked
        return reader
    except TargumError:
        raise
    except Exception as broken:
        raise TargumError("That PDF could not be opened.") from broken


def page_count(path: Path) -> int:
    """How many pages, asked at the upload door so a book is refused before it is read."""
    return len(_reader(path).pages)


def page_lines(path: Path) -> list[list[str]]:
    """Every page's lines, in reading order, with presentation forms folded back and a
    blank line where the page left a gap.

    A text layer has no paragraphs, only lines, and a page handed over as one paragraph
    reads as one paragraph. The layer does know where each line sits, though: pypdf's
    visitor reports a position for every run of text, and a gap between two lines that
    is half again the usual one is a paragraph break. Where the positions cannot be
    matched to the lines, a line that ends the way a sentence ends is taken to end a
    paragraph — which splits a paragraph too often and joins two never.
    """
    reader = _reader(path)
    if len(reader.pages) > MAX_PAGES:
        raise TargumError(
            f"That PDF is {len(reader.pages)} pages. targum reads up to {MAX_PAGES} at a time."
        )
    pages: list[list[str]] = []
    for page in reader.pages:
        rows: list[float] = []
        try:
            text = page.extract_text(visitor_text=_noting(rows)) or ""
        except Exception:
            text = ""
        folded = unicodedata.normalize("NFKC", text)
        lines = [normalize(line) for line in folded.split("\n") if line.strip()]
        pages.append(spaced(lines, rows))
    return pages


def _noting(rows: list[float]) -> Any:
    """pypdf's visitor, writing each run's vertical position into `rows`."""

    def seen(text: str, cm: Any, tm: Any, font: Any, size: Any) -> None:
        if text.strip():
            rows.append(round(float(tm[5]), 1))

    return seen


#: A gap this many times the line height is a paragraph break. The line height is the
#: smallest gap on the page: two wrapped lines of one paragraph sit as close as any
#: two lines do, and every paragraph gap is wider.
GAP = 1.5


def spaced(lines: list[str], rows: list[float]) -> list[str]:
    """The lines with a blank one wherever the page had a gap."""
    tops: list[float] = []
    for row in rows:
        if not tops or abs(row - tops[-1]) > 2.0:
            tops.append(row)
    if len(tops) == len(lines) and len(lines) > 2:
        gaps = [abs(tops[n + 1] - tops[n]) for n in range(len(tops) - 1)]
        usual = min(gaps)
        out: list[str] = []
        for n, line in enumerate(lines):
            out.append(line)
            if n < len(gaps) and usual > 0 and gaps[n] > GAP * usual:
                out.append("")
        return out
    out = []
    for line in lines:
        out.append(line)
        if line.rstrip()[-1:] in ".!?׃":
            out.append("")
    return out


def looks_scanned(pages: list[list[str]]) -> bool:
    if not pages:
        return True
    letters = sum(len(_LETTER.findall(line)) for lines in pages for line in lines)
    return letters / len(pages) < SCAN_LETTERS_PER_PAGE


def doubtful_lines(pages: list[list[str]]) -> int:
    return sum(1 for lines in pages for line in lines if mixed(line))


class PdfIngester:
    name = "pdf/1"

    def load(self, source: str) -> Document:
        path = Path(source)
        pages = page_lines(path)
        if looks_scanned(pages):
            raise UnsupportedSource(SCAN)
        document = document_from_pages(
            str(path),
            pages,
            ingester=self.name,
            source_hash=hashlib.sha256(path.read_bytes()).hexdigest(),
            title=_title(path, pages),
        )
        if not document.blocks:
            raise UnsupportedSource(SCAN)
        return document


def _title(path: Path, pages: list[list[str]]) -> str | None:
    """The document's own title if the file carries one, else the first line's."""
    try:
        meta = _reader(path).metadata
        named = str(getattr(meta, "title", "") or "").strip() if meta else ""
    except Exception:
        named = ""
    if named and not named.lower().endswith((".doc", ".docx", ".pdf", ".odt")):
        return named
    return None
