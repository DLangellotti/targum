"""A web page, reduced to the text a reader came for."""

from __future__ import annotations

from typing import Any

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

USER_AGENT = "targum/0.1 (+https://github.com/DLangellotti/targum)"
TIMEOUT = 30.0


def get(url: str, params: dict[str, str] | None = None) -> str:
    """One place for every outbound request, so the timeout and agent are consistent."""
    import httpx

    try:
        response = httpx.get(
            url,
            params=params,
            timeout=TIMEOUT,
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT},
        )
        response.raise_for_status()
    except Exception as exc:
        raise TargumError(f"Could not fetch {url}", str(exc)) from exc
    return response.text


class UrlIngester:
    name = "url/2"

    def load(self, source: str) -> Document:
        import trafilatura

        html = get(source)
        # trafilatura decides what on the page is the article. Asking it for HTML
        # rather than text keeps the headings and paragraph boundaries.
        extracted: Any = trafilatura.extract(
            html,
            output_format="html",
            include_comments=False,
            include_tables=False,
            include_formatting=False,
            favor_recall=True,
        )
        paragraphs: list[Paragraph] = (
            paragraphs_from_html(extracted) if extracted else paragraphs_from_html(html)
        )
        if not paragraphs:
            raise TargumError(
                f"No readable text found at {source}",
                "Save the page as .txt or .md and point targum at the file.",
            )
        paragraphs = [(kind, level, normalize(text)) for kind, level, text in paragraphs]

        metadata = trafilatura.extract_metadata(html)
        title = getattr(metadata, "title", None)
        author = getattr(metadata, "author", None)

        return build_document(
            source,
            blocks_from_paragraphs(with_front_matter(paragraphs, title, author)),
            ingester=self.name,
            title=title or source,
            author=author,
        )
