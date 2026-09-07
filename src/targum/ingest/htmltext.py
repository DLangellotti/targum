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

# Page furniture, matched against the `id`, `class` and `role` a publisher wrote. There
# are two lists because there are two kinds of word, and one regex over both was a bug
# for as long as it existed (2026-09-07): a long distinctive word can be looked for
# anywhere inside a name, and a short generic one cannot. `widget` inside
# `elementor-widget` is Elementor's namespace for the block holding the article, and
# `toc` inside `vector-toc-available` is MediaWiki's flag saying a contents list is
# possible — matching those threw whole pages away. Classes vary by publisher, so these
# still match shapes rather than an enumeration; they just match them where the word
# actually begins.

#: Long enough to mean only itself wherever it appears in a name.
_STRIP_ANYWHERE = re.compile(
    r"(footnote|endnote|noteref|sidenote|marginnote|breadcrumb|mw-editsection|"
    r"reflist|catlinks|navbox|printfooter|jump-to-nav|hatnote|authority-control|"
    r"vector-toc|advert|newsletter|paywall|byline-social|most-read|outbrain|taboola)",
    re.I,
)

#: Generic enough that a vendor prefix turns it into something else, so it counts only
#: where a name begins: `widget-area` is furniture, `elementor-widget` is the page.
_STRIP_AT_START = re.compile(
    r"(fn\d|pagenum|page-number|toc|navigation|reference|siteSub|dablink|rellink|"
    r"noprint|metadata|licence|license|infobox|"
    # What a news page wraps around the article: the promo rail, the ad slots, the
    # share row, the comment thread, the cookie banner.
    r"promo|sponsor|subscri|share|social|recirc|teaser|widget|banner|masthead|"
    r"sitemap|comment|trending|read-?more|next-?story|dfp|gpt-ad)",
    re.I,
)


def _furniture(identity: str) -> bool:
    """Whether an element's `id`/`class`/`role` says it is not the text."""
    if _STRIP_ANYWHERE.search(identity):
        return True
    return any(_STRIP_AT_START.match(token) for token in identity.split())


# The elements a document *is*, which are never its furniture however they are
# classed. A skin writes its feature flags on the root — MediaWiki's Vector 2022 puts
# `vector-toc-available` on <html> — so without this every Wikipedia page decomposed
# to nothing and came back as a blank
# article with no Hebrew on it (2026-09-07). Not <article>: a news site wraps its
# recirculation cards in one, and those are exactly what the patterns are for.
_NEVER_STRIP = frozenset({"html", "body", "main"})

# Furniture is a minority of a page, by definition. A framework that namespaces its own
# class names can still put a furniture word where `_STRIP_AT_START` will find it. This
# is the backstop for the framework nobody has met yet: refuse to strip an element that
# holds most
# of the page: whatever it is classed, an element carrying this much of the text is the
# page. Both conditions are needed — the share alone would protect the apparatus in a
# two-line document, where a footnote outweighs the sentence it hangs off.
KEEPS_THE_PAGE = 0.5
ENOUGH_TO_BE_THE_PAGE = 400

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
    # After the furniture tags are gone, so the denominator is the text a reader could
    # plausibly have come for and not the navigation that was always going.
    whole = len(soup.get_text())
    for tag in list(soup.find_all(True)):
        # Decomposing a parent leaves its descendants in this list with attrs cleared.
        if not isinstance(tag, Tag) or tag.attrs is None:
            continue
        if tag.name in _NEVER_STRIP:
            continue
        identity = " ".join(
            [str(tag.get("id") or ""), " ".join(tag.get("class") or []), str(tag.get("role") or "")]
        )
        if not identity.strip() or not _furniture(identity):
            continue
        # Measured only where the patterns already matched, which is rare: `get_text()`
        # on every element of a large page is quadratic, and on a match it is not.
        held = len(tag.get_text())
        if held >= ENOUGH_TO_BE_THE_PAGE and held >= whole * KEEPS_THE_PAGE:
            continue
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
