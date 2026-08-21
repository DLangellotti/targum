"""HTML into blocks.

Shared by EPUB, Wikisource and URL ingest, so a fix to footnote handling or heading
detection lands in all three at once.
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup, Tag

from ..models import BlockKind

Paragraph = tuple[BlockKind, int | None, str]

# Page furniture: never the text a reader came for.
_STRIP_TAGS = (
    "script",
    "style",
    "nav",
    "header",
    "footer",
    "aside",
    "form",
    "figure",
    "figcaption",
    "table",
    "noscript",
)

# Footnote apparatus. Classes vary by publisher, so match on the common shapes rather
# than trying to enumerate them.
_STRIP_PATTERNS = re.compile(
    r"(footnote|endnote|fn\d|noteref|sidenote|marginnote|pagenum|page-number|"
    r"toc|navigation|breadcrumb|mw-editsection|reference|reflist|catlinks|navbox|"
    r"printfooter|siteSub|jump-to-nav|hatnote|dablink|rellink|noprint|metadata|"
    r"licence|license|infobox|authority-control|"
    # What a news page wraps around the article: the promo rail, the ad slots, the
    # newsletter box, the share row, the comment thread, the cookie banner.
    r"advert|promo|sponsor|newsletter|subscri|paywall|share|social|recirc|teaser|"
    r"widget|banner|masthead|sitemap|comment|byline-social|most-read|trending|"
    r"read-?more|next-?story|outbrain|taboola|dfp|gpt-ad)",
    re.I,
)

_HEADINGS = {"h1": 1, "h2": 2, "h3": 3, "h4": 4, "h5": 5, "h6": 6}
_WHITESPACE = re.compile(r"\s+")

# Joining inline elements with a space leaves "the word , and" wherever a link or span
# ended before punctuation. Only the marks that never take a leading space in any of
# the supported languages are tightened: French keeps its space before ; : ! ?
_TIGHTEN_BEFORE = re.compile(r"\s+([,.)\]}])")
_TIGHTEN_AFTER = re.compile(r"([(\[{])\s+")
# A maqaf joins two Hebrew words and never takes a space on either side.
_TIGHTEN_MAQAF = re.compile(r"\s*\u05be\s*")
# Transcriptions render the fill rules of an original document as runs of underscores
# or dashes. They are typography, not words, and a translator should never see them.
_RULES = re.compile(r"[_\u2014\u2013-]{3,}")


def _clean(soup: BeautifulSoup) -> None:
    for tag in soup(list(_STRIP_TAGS)):
        tag.decompose()
    # Superscript note markers leave stray digits mid-sentence if they survive.
    for tag in soup("sup"):
        tag.decompose()
    for tag in list(soup.find_all(True)):
        # Decomposing a parent leaves its descendants in this list with attrs cleared.
        if not isinstance(tag, Tag) or tag.attrs is None:
            continue
        identity = " ".join(
            [str(tag.get("id") or ""), " ".join(tag.get("class") or []), str(tag.get("role") or "")]
        )
        if identity.strip() and _STRIP_PATTERNS.search(identity):
            tag.decompose()


def _text(tag: Tag) -> str:
    # Join inline elements with nothing, not with a space. Hebrew attaches its
    # prefixes directly to the following word, and a wiki link that starts after the
    # prefix ("ב[[הצהרת בלפור]]") would otherwise come out as two words. The markup
    # already carries whitespace wherever the text has it.
    text = _WHITESPACE.sub(" ", tag.get_text()).strip()
    text = _WHITESPACE.sub(" ", _RULES.sub(" ", text)).strip()
    text = _TIGHTEN_AFTER.sub(r"\1", _TIGHTEN_BEFORE.sub(r"\1", text))
    return _TIGHTEN_MAQAF.sub("\u05be", text)


def paragraphs_from_html(html: str) -> list[Paragraph]:
    """Headings, paragraphs, blockquotes and verse lines, in document order."""
    soup = BeautifulSoup(html, "html.parser")
    _clean(soup)

    out: list[Paragraph] = []
    seen: set[int] = set()
    body = soup.body or soup

    for tag in body.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "p", "blockquote", "li", "div"]):
        if any(id(parent) in seen for parent in tag.parents):
            continue
        name = tag.name
        text = _text(tag)
        if not text:
            continue

        if name in _HEADINGS:
            out.append((BlockKind.heading, _HEADINGS[name], text))
        elif name == "blockquote":
            seen.add(id(tag))
            out.append((BlockKind.blockquote, None, text))
        elif name == "p":
            out.append((BlockKind.paragraph, None, text))
        elif name == "li":
            out.append((BlockKind.paragraph, None, text))
        elif name == "div":
            # Only a div that holds text directly, so a wrapper does not duplicate
            # every paragraph inside it.
            direct = "".join(
                str(child) for child in tag.children if not isinstance(child, Tag)
            ).strip()
            if direct and not tag.find(["p", "div", "h1", "h2", "h3", "h4", "h5", "h6"]):
                out.append((BlockKind.paragraph, None, text))
    return out
