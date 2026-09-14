"""Wikisource, by page title.

    targum build wikisource:he:מגילת_העצמאות
    targum build "wikisource:Declaration of Independence"
    targum build "wikisource:it:Cenere"

The language prefix picks the subdomain and defaults to English. Titles are taken as
typed, with spaces allowed, since a page title is not a URL.

**A book is often a contents page.** On it.wikisource most works are an index whose
chapters are subpages — `Cenere` links `Cenere/Parte I/I` and eighteen more, and says
nothing of its own — so reading the one page answered "no readable text" for Cenere,
Cuore and Il Principe, and thirty words of titles for Novelle rusticane (2026-09-14).
A page that links two or more of its own subpages and has next to no words besides is
read as that contents: each subpage in the order the page lists it, under a heading of
its own name, one level deeper for each level of the title, with the wiki's apparatus
(`ws-noexport`: the edition box, the previous-and-next bar) taken out first. A page
with text of its own is read as it always was, links or no links: the Declaration
links its pointed copy, `/מנוקד`, and must not become two copies of itself.
"""

from __future__ import annotations

import json
import re
from typing import Any

from ...errors import TargumError
from ...models import BlockKind, Document
from ...vocalize.base import strip_nikkud
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
        # Italian
        "note",
        "voci correlate",
        "collegamenti esterni",
        "bibliografia",
        # German
        "siehe auch",
        "einzelnachweise",
        "weblinks",
        "anmerkungen",
        "literatur",
    }
)


# What the wiki says about where it got the text, in the boxed notice it puts above it.
# The same idea as `_NAVIGATION` and matched the same narrow way — a short list, and only
# at the end of the page it is at. Three of the Kuzari's five ma'amarim open with
# "טקסט זה הועתק מפרויקט בן-יהודה", which is true, is a credit the licence does not ask
# for here, and is not the book: left in, it is translated, pointed, glossed and read.
_NOTICES = re.compile(r"^טקסט זה (?:הועתק|נלקח|מבוסס)\b")


def drop_leading_notices(paragraphs: list[Paragraph]) -> list[Paragraph]:
    """Cut the wiki's sourcing note off the front of a page."""
    out = list(paragraphs)
    while out and out[0][0] is not BlockKind.heading and _NOTICES.match(out[0][2].strip()):
        out = out[1:]
    return out


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


# A section the page itself labels as the vowel-less copy of what is above it. Wikisource
# routinely carries a poem twice under two headings — "עם ניקוד" and "ללא ניקוד" — and
# both were ingested, so both were segmented, priced, translated, pointed and glossed.
# The Bialik page came back as four "sections", the third being a partial bare copy of the
# second, and the learner paid for the poem twice. The vowels are a toggle in the reader;
# a second copy of the words is not a second text.
#
# **The heading is the only reliable signal, and this was not obvious.** Matching the two
# copies by their letters cannot work: pointed Hebrew is written defectively and bare
# Hebrew is written full, so the same line is צִפֹּרָה / ציפור and הַחֹם / החום — different
# strings by convention rather than by accident. On the real page not one of the five bare
# paragraphs was a character-for-character strip of the pointed poem, and they were not
# even cut the same way: the pointed copy is one block of 2,512 characters and the bare one
# is five of about ninety. Nothing short of fuzzy matching would pair them, and fuzzy
# matching over a text this product is about to charge somebody to translate is not a
# trade worth making. The page says what it is; believe it.
_BARE_COPIES = (
    "ללא ניקוד",
    "ללא נקוד",
    "בלי ניקוד",
    "בלי נקוד",
    "לא מנוקד",
    "unpointed",
    "without vowels",
    "without nikkud",
    "without niqqud",
)


def _pointed(text: str) -> bool:
    """Whether this text carries vowel points, asked the way the vocalizer asks it.

    Stripping is the definition, so there is no second list of which marks count.
    """
    return strip_nikkud(text)[0] != text


def drop_unpointed_copies(paragraphs: list[Paragraph]) -> list[Paragraph]:
    """Cut a section the page labels as the bare copy of a work it also carries pointed.

    Only when there is something pointed to prefer: a page that is bare throughout is a
    bare work, not a copy of anything, and its headings are its own. The heading is
    matched by its opening words, because the real one reads "ללא ניקוד (חלקי)" — the wiki
    saying its copy is partial, which is exactly the case that must still go.
    """
    if not any(kind is not BlockKind.heading and _pointed(text) for kind, _, text in paragraphs):
        return list(paragraphs)

    out: list[Paragraph] = []
    dropping = False
    for kind, level, text in paragraphs:
        if kind is BlockKind.heading:
            key = _heading_key(text)
            dropping = any(key.startswith(one) for one in _BARE_COPIES)
            if dropping:
                continue
        elif dropping:
            continue
        out.append((kind, level, text))
    return out


# Wikisource subdomains are language codes already, with a few historic exceptions.
_TAGS = {"iw": "he"}


def split_identifier(identifier: str) -> tuple[str, str]:
    """'he:מגילת העצמאות' -> ('he', 'מגילת העצמאות'). A bare title means English."""
    head, sep, rest = identifier.partition(":")
    if sep and head and len(head) <= 3 and head.isalpha() and head.islower():
        return _TAGS.get(head, head), rest.replace("_", " ").strip()
    return DEFAULT_LANGUAGE, identifier.replace("_", " ").strip()


# A paragraph is a link list — the wiki's own furniture — when nearly all of it is inside
# links and there are several of them. Wikisource puts one at the top of every volume of a
# multi-part work: the Kuzari's first ma'amar opens with three rows of edition links and
# then the hundred and seventeen numerals of its own contents, which
# `drop_trailing_navigation` never sees, because they are at the front and under no
# heading at all.
#
# Measured over letters rather than characters, which is what makes the threshold hold
# still. A navigation row is links separated by bullets and middots, and counting those
# separators against the links puts a row of a hundred and seventeen chapter numerals at
# 0.63 — indistinguishable from prose by the number, and nothing like it to read. Ignoring
# everything that is not a letter or a digit, the Kuzari's four rows measure 0.77 to 1.00
# and the one real sentence on the page that carries three links measures 0.61.
_LINK_SHARE = 0.75
_LINK_COUNT = 3


def _letters(text: str) -> int:
    return sum(1 for character in text if character.isalpha() or character.isdigit())


def drop_link_lists(html: str) -> str:
    """Take the wiki's navigation rows out before the text is read.

    Before rather than after, because link density is a fact about the markup and
    `paragraphs_from_html` hands back plain strings with that fact already thrown away.
    """
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all(["p", "div", "center"]):
        links = tag.find_all("a")
        if len(links) < _LINK_COUNT:
            continue
        whole = _letters(tag.get_text())
        linked = sum(_letters(link.get_text()) for link in links)
        if whole and linked / whole >= _LINK_SHARE:
            tag.decompose()
    return str(soup)


#: Fewer words than this outside the links to its own subpages, and a page is a table of
#: contents. Novelle rusticane's is 30; the shortest real page on the Hebrew shelf is
#: thousands.
_INDEX_WORDS = 200
#: How many pages one work may be read from. Cuore is 111; a crawl past this is a
#: collection rather than a book, and is refused rather than fetched page by page.
MAX_SUBPAGES = 400


def _soup(html: str) -> Any:
    from bs4 import BeautifulSoup

    return BeautifulSoup(html, "html.parser")


def drop_apparatus(html: str) -> str:
    """The page without what Wikisource itself leaves out of an export.

    `ws-noexport` marks the edition box, the quality badge and the chapter bar with its
    previous and next links: the wiki's own furniture, named by the wiki.
    """
    soup = _soup(html)
    for tag in soup.select(".ws-noexport"):
        tag.decompose()
    return str(soup)


def subpages(html: str, title: str) -> list[str]:
    """The page's own subpages, in the order it links them, once each.

    Only what exists (a red link carries `new`) and only what is linked from the text
    rather than the apparatus.
    """
    prefix = f"{title}/"
    out: list[str] = []
    for link in _soup(drop_apparatus(html)).find_all("a", title=True):
        named = str(link["title"])
        if named.startswith(prefix) and "new" not in (link.get("class") or []):
            if named not in out:
                out.append(named)
    return out


def _own_words(html: str, linked: list[str]) -> int:
    """Words on the page that are not the names of the subpages it links."""
    soup = _soup(drop_apparatus(html))
    for tag in soup.find_all(["style", "script"]):
        tag.decompose()
    total = len(soup.get_text(" ").split())
    inside = sum(
        len(link.get_text(" ").split())
        for link in soup.find_all("a", title=True)
        if link["title"] in linked
    )
    return total - inside


def _same_name(line: str, name: str) -> bool:
    def key(text: str) -> str:
        return _heading_key(text.replace("’", "'"))

    return key(line) == key(name)


def _is_contents(html: str, linked: list[str]) -> bool:
    return len(linked) >= 2 and _own_words(html, linked) < _INDEX_WORDS


def _plain(html: str | None) -> str:
    if not html:
        return ""
    from bs4 import BeautifulSoup

    return BeautifulSoup(html, "html.parser").get_text(" ", strip=True)


def _read(html: str) -> list[Paragraph]:
    """One page's text, with the wiki's furniture cut from the top and the bottom."""
    paragraphs: list[Paragraph] = [
        (kind, level, normalize(text))
        for kind, level, text in paragraphs_from_html(drop_link_lists(html))
    ]
    return drop_unpointed_copies(drop_leading_notices(drop_trailing_navigation(paragraphs)))


class WikisourceFetcher:
    # 2: the wiki's own link rows and its sourcing note are dropped from the top of a
    # page as well as its navigation from the bottom. 3: a contents page is read as the
    # work its subpages make; every page with text of its own reads byte for byte as it
    # did under 2, and the bump is so that a contents page already ingested as its list of
    # titles is read again rather than kept as though somebody had edited it. Free to
    # bump; nothing downstream is bought again.
    name = "wikisource/3"

    def _parse(self, language: str, title: str) -> dict[str, Any]:
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
        parsed: dict[str, Any] = payload.get("parse", {})
        return parsed

    def _work(self, language: str, root: str, listed: list[str]) -> list[Paragraph]:
        """Every subpage a contents page lists, in its order, each under its own name.

        A subpage that is itself contents — `Cenere/Parte I` — is a heading and then its
        own subpages. The root lists those too, usually, and each is read once.
        """
        out: list[Paragraph] = []
        seen: set[str] = set()

        def walk(pages: list[str]) -> None:
            for page in pages:
                if page in seen:
                    continue
                seen.add(page)
                if len(seen) > MAX_SUBPAGES:
                    raise TargumError(
                        f"Wikisource's '{root}' runs past {MAX_SUBPAGES} pages.",
                        "Name one part of it instead.",
                    )
                html = drop_apparatus(str(self._parse(language, page).get("text", "")))
                inner = subpages(html, page)
                name = page.rsplit("/", 1)[-1]
                level = min(6, 2 + page[len(root) + 1 :].count("/"))
                out.append((BlockKind.heading, level, name))
                if not _is_contents(html, inner):
                    body = _read(html)
                    # The chapter's own title, printed again as its first line: `I.` under
                    # the heading `I`, `COS’È IL RE` under `Cos'è il re`.
                    if body and _same_name(body[0][2], name):
                        body = body[1:]
                    for kind, inner_level, text in body:
                        if kind is BlockKind.heading:
                            # Kept under the chapter it is in, never beside it.
                            inner_level = min(6, max(inner_level or 0, level + 1))
                        out.append((kind, inner_level, text))
                walk(inner)

        walk(listed)
        return out

    def load(self, identifier: str) -> Document:
        language, title = split_identifier(identifier)
        if not title:
            raise TargumError("Wikisource needs a page title.", "wikisource:he:מגילת העצמאות")

        parsed = self._parse(language, title)
        html = str(parsed.get("text", ""))
        # Subpages hang off the title the wiki settled on, after any redirect.
        page = str(parsed.get("title") or title)
        listed = subpages(html, page)
        work = _is_contents(html, listed)
        paragraphs = self._work(language, page, listed) if work else _read(html)
        if not paragraphs:
            raise TargumError(f"Wikisource page '{title}' has no readable text.")

        # displaytitle arrives as HTML, carrying the span the wiki uses to set the
        # title's direction. The reader wants the words.
        display = _plain(parsed.get("displaytitle")) or title
        if work or not any(kind is BlockKind.heading for kind, _, _ in paragraphs[:1]):
            paragraphs.insert(0, (BlockKind.heading, 1, display))

        return build_document(
            f"wikisource:{language}:{title}",
            blocks_from_paragraphs(paragraphs),
            ingester=self.name,
            language=language,
            title=display,
        )
