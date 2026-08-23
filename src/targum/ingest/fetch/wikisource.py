"""Wikisource, by page title.

    targum build wikisource:he:מגילת_העצמאות
    targum build "wikisource:Declaration of Independence"

The language prefix picks the subdomain and defaults to English. Titles are taken as
typed, with spaces allowed, since a page title is not a URL.
"""

from __future__ import annotations

import json
from typing import Any

from ...errors import TargumError
from ...models import BlockKind, Document
from ..base import Paragraph, blocks_from_paragraphs, build_document, normalize
from ..htmltext import paragraphs_from_html
from ..url import get

API = "https://{language}.wikisource.org/w/api.php"
DEFAULT_LANGUAGE = "en"

# Sections that are the wiki talking about the text rather than the text itself. They
# are always last, and without this they are ingested, priced, translated, pointed and
# glossed like any other prose: a four-line "see also" block on a Bialik poem came back
# as a chapter of its own, in the reader, paid for.
#
# Matched only at the end of a page and only against this list, so a work that happens
# to contain one of these words in a real heading keeps it.
_NAVIGATION = frozenset(
    {
        # Hebrew
        "ראו גם",
        "קישורים חיצוניים",
        "הערות שוליים",
        "לקריאה נוספת",
        "מקורות",
        "הערות",
        # English
        "see also",
        "external links",
        "references",
        "notes",
        "footnotes",
        "further reading",
        "sources",
        "bibliography",
        # Russian
        "см. также",
        "примечания",
        "ссылки",
        "литература",
        "источники",
        # French
        "voir aussi",
        "notes et références",
        "références",
        "liens externes",
        # Spanish
        "véase también",
        "referencias",
        "enlaces externos",
        "notas",
        # German
        "siehe auch",
        "einzelnachweise",
        "weblinks",
        "anmerkungen",
        "literatur",
    }
)


def _heading_key(text: str) -> str:
    return text.strip().strip(":：.،,").casefold()


def drop_trailing_navigation(paragraphs: list[Paragraph]) -> list[Paragraph]:
    """Cut the wiki's own apparatus off the end of a page.

    Only from the end, and only one known heading at a time, so the first thing that is
    not navigation stops it.
    """
    out = list(paragraphs)
    while True:
        last = None
        for index in range(len(out) - 1, -1, -1):
            if out[index][0] is BlockKind.heading:
                last = index
                break
        if last is None or last == 0 or _heading_key(out[last][2]) not in _NAVIGATION:
            return out
        out = out[:last]


# Wikisource subdomains are language codes already, with a few historic exceptions.
_TAGS = {"iw": "he"}


def split_identifier(identifier: str) -> tuple[str, str]:
    """'he:מגילת העצמאות' -> ('he', 'מגילת העצמאות'). A bare title means English."""
    head, sep, rest = identifier.partition(":")
    if sep and head and len(head) <= 3 and head.isalpha() and head.islower():
        return _TAGS.get(head, head), rest.replace("_", " ").strip()
    return DEFAULT_LANGUAGE, identifier.replace("_", " ").strip()


def _plain(html: str | None) -> str:
    if not html:
        return ""
    from bs4 import BeautifulSoup

    return BeautifulSoup(html, "html.parser").get_text(" ", strip=True)


class WikisourceFetcher:
    name = "wikisource/1"

    def load(self, identifier: str) -> Document:
        language, title = split_identifier(identifier)
        if not title:
            raise TargumError("Wikisource needs a page title.", "wikisource:he:מגילת העצמאות")

        payload: Any = json.loads(
            get(
                API.format(language=language),
                params={
                    "action": "parse",
                    "page": title,
                    "prop": "text|displaytitle",
                    "redirects": "1",
                    "formatversion": "2",
                    "format": "json",
                },
            )
        )
        if "error" in payload:
            raise TargumError(
                f"Wikisource has no page '{title}' in {language}.",
                str(payload["error"].get("info", "")),
            )

        parsed = payload.get("parse", {})
        paragraphs: list[Paragraph] = [
            (kind, level, normalize(text))
            for kind, level, text in paragraphs_from_html(parsed.get("text", ""))
        ]
        paragraphs = drop_trailing_navigation(paragraphs)
        if not paragraphs:
            raise TargumError(f"Wikisource page '{title}' has no readable text.")

        # displaytitle arrives as HTML, carrying the span the wiki uses to set the
        # title's direction. The reader wants the words.
        display = _plain(parsed.get("displaytitle")) or title
        if not any(kind is BlockKind.heading for kind, _, _ in paragraphs[:1]):
            paragraphs.insert(0, (BlockKind.heading, 1, display))

        return build_document(
            f"wikisource:{language}:{title}",
            blocks_from_paragraphs(paragraphs),
            ingester=self.name,
            language=language,
            title=display,
        )
