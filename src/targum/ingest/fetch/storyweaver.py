"""StoryWeaver, by story number.

    targum build storyweaver:7686

Pratham Books' platform for openly licensed picture books: written mostly in English or
an Indian language, and translated by volunteers into everything else. The number is the
one in the address — storyweaver.org.in/stories/7686-la-luna-e-il-cappello is
`storyweaver:7686`.

One call reads a book. `/api/v1/stories/{id}/read` hands back every page as HTML: the
cover, the story pages, the attribution pages and the back cover. `/api/v1/stories/{id}`
carries the same credits as structured data, and nothing this fetcher needs that the
pages do not, so it is never asked. The host puts a bot check in front of anybody who
knocks too often. `url.get` already waits a second and a half between two knocks on one
host, and a challenge that comes anyway is waited out (`CHALLENGE_WAITS`).

**The attribution page is the licence, and it is read rather than assumed.** StoryWeaver
is CC BY 4.0 almost throughout, and "almost" is the reason. Every credit on the page
states its own terms — the book's footer, the translation, the story it was translated
from, the original, each picture — and a book is refused if any one of them is not a
licence this shelf may serve, with the one that failed named. The pictures never reach a
reader, and are checked anyway: a book whose own page mixes its terms is a book somebody
should look at before it is on a shelf.

**Some translators typed every page twice.** The second copy is in capitals, for children
learning their letters, and left in it would be segmented, aligned and read as a second
sentence saying the same thing. `drop_capital_copies` takes it out, and only where the
capitals really are a copy of the page.

**A translation says where it came from, and that is the English beside it.** The pages
name the story a translation was made from and the original it goes back to, each with
its number. `english_source` walks that chain to the nearest English version, so a
catalogue row can name a published English instead of buying one. About a third of the
Italian went through a third language on the way; the walk finds the English wherever it
sits in the chain.
"""

from __future__ import annotations

import difflib
import json
import re
import time
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from ...errors import TargumError, Unreachable
from ...licensing import Standing, verdict
from ...models import BlockKind, Document
from ..base import Paragraph, blocks_from_paragraphs, build_document, normalize, with_front_matter
from ..url import get

READ = "https://storyweaver.org.in/api/v1/stories/{id}/read"
PAGE = "https://storyweaver.org.in/stories/{slug}"

# StoryWeaver names languages; targum speaks BCP-47. Only the languages targum reads or
# translates into, and the ones a chain of translations commonly passes through. A
# language not named here is detected from the text, the way a file's is.
_LANGUAGE_TAGS = {
    "english": "en",
    "italian": "it",
    "french": "fr",
    "spanish": "es",
    "german": "de",
    "russian": "ru",
    "hebrew": "he",
    "arabic": "ar",
    "portuguese": "pt",
    "hindi": "hi",
    "yiddish": "yi",
}

#: The standings a book may have to be on the shelf: public domain, or owed a credit
#: (CC BY) or a share-alike (CC BY-SA). NonCommercial, NoDerivatives and anything nobody
#: here recognises are refused.
_SERVABLE = frozenset({Standing.free, Standing.owed})

#: How far up a chain of translations `english_source` will walk. A bound on a loop that
#: follows links somebody else wrote, not a claim about how long the chains are.
MAX_HOPS = 6


def language_tag(name: str) -> str | None:
    return _LANGUAGE_TAGS.get((name or "").strip().lower())


def book_id(identifier: str) -> int:
    """`7686`, or the slug the address carries, `7686-la-luna-e-il-cappello`."""
    head = identifier.strip().split("-", 1)[0]
    if not head.isdigit():
        raise TargumError(
            f"StoryWeaver wants a story number, not '{identifier.strip()}'.",
            "The number in the address: storyweaver.org.in/stories/7686-… is storyweaver:7686",
        )
    return int(head)


# -- the pages ---------------------------------------------------------------------------


def _clean(text: str) -> str:
    # Soft hyphens and a byte-order mark both turn up inside words on these pages, typed
    # by whoever pasted the text in, and neither is visible or a character of the story.
    text = text.replace("\xad", "").replace("﻿", "").replace("​", "")
    return " ".join(normalize(text).split())


def _plain(html: Any) -> str:
    """One element's words, with a line break read as a space."""
    for br in html.find_all("br"):
        br.replace_with(" ")
    return _clean(html.get_text(""))


def _shouting(text: str) -> bool:
    """Whether a line is written in capitals: nine in ten of its cased letters."""
    cased = [c for c in text if c.lower() != c.upper()]
    return bool(cased) and sum(c.isupper() for c in cased) >= 0.9 * len(cased)


def _letters(text: str) -> str:
    """The letters of a line and nothing else, accents taken off, in capitals.

    Accents come off because the copy is typed on a keyboard that has no capital À: the
    lower-case `Papà` is `PAPA'` in the capitals underneath it.
    """
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if c.isalnum()).upper()


#: How alike the capitals and the rest of a page must be for the capitals to be a copy.
#: Measured over the 13,115 story pages of the Italian books on 2026-09-14: of the 287
#: pages carrying both, 102 copies match at 0.9 or better, three more at 0.80-0.85 where
#: the translator shortened the copy as they typed it, and every page that is not a copy
#: — a `CRAC!` over a paragraph of prose, a bird's call under its name — measures 0.39 or
#: less. The line sits in the gap.
COPY_LIKENESS = 0.75


def drop_repeated_half(lines: list[str]) -> list[str]:
    """Take the second half off a page that is its first half twice, in the same case.

    StoryWeaver's editor can carry a page's text box over into a second box on the same
    page, so the page reads through once and then again, beside or instead of the
    capitals: nine of the 12,180 Italian pages with words on them. Matched exactly, letter
    for letter, and only as the whole page, because a line a picture book says twice on
    purpose is said once more and never the whole page over.
    """
    for split in range(1, len(lines)):
        first = _letters(" ".join(lines[:split]))
        if first and first == _letters(" ".join(lines[split:])):
            return lines[:split]
    return lines


def drop_capital_copies(lines: list[str]) -> list[str]:
    """Take the capitals off a page that is the page typed twice.

    Only the whole page at once, and only where both halves are there. A page written in
    capitals throughout is written that way, and a shout inside a page of prose is part
    of the story; neither is a copy of anything, and the copies were never measured
    splitting across two pages. The page may also carry its lower-case text twice, one
    box copied into the next, and that is taken out first or the capitals would be
    measured against two copies and kept.
    """
    capitals = [line for line in lines if _shouting(line)]
    rest = drop_repeated_half([line for line in lines if not _shouting(line)])
    if not capitals or not rest:
        return drop_repeated_half(lines)
    likeness = difflib.SequenceMatcher(
        None, _letters(" ".join(capitals)), _letters(" ".join(rest)), autojunk=False
    ).ratio()
    return rest if likeness >= COPY_LIKENESS else drop_repeated_half(lines)


#: How alike every pair of pages must be for a book to be a book with each page twice.
#: Measured over the 1,020 Italian books on 2026-09-14: *Buonanotte, Tinku!* (7751), whose
#: twenty-two pages are its eleven twice, pairs at 0.99 at the worst; no other book of
#: four pages or more pairs above 0.71 throughout.
DOUBLED_LIKENESS = 0.95


def drop_doubled_pages(pages: list[str]) -> list[str]:
    """Keep one of each page of a book that carries every page twice running.

    The whole book or nothing, and never under four pages: a picture book turns a page
    on a line it has just said often enough, and "Oh, no!" over "OH, NO!" is two pages of
    the story. What this catches is every page followed by itself, which no story does.
    """
    if len(pages) < 4 or len(pages) % 2:
        return pages
    for first, second in zip(pages[::2], pages[1::2], strict=True):
        likeness = difflib.SequenceMatcher(
            None, _letters(first), _letters(second), autojunk=False
        ).ratio()
        if likeness < DOUBLED_LIKENESS:
            return pages
    return pages[::2]


def page_text(html: str) -> str:
    """What one story page says, as one paragraph.

    One paragraph a page rather than one a line, because the page is what the English and
    the Italian share: two translators break a page into lines differently and never
    move a sentence across a page turn, so the page is the landmark alignment anchors on.
    """
    from bs4 import BeautifulSoup

    # A page's text is in a box or several. A book laid out in StoryWeaver's newer editor
    # floats a box over each part of the picture — a speech bubble here, a caption there —
    # and leaves the page's own box empty. Reading only the first, 135 of the 1,020
    # Italian books came back with no words at all.
    lines: list[str] = []
    for box in BeautifulSoup(html, "html.parser").select("div.content"):
        # Outermost only. Pasted text nests a <p> inside a <p>, and html.parser keeps the
        # nesting, so every paragraph under another was read twice.
        paragraphs = [p for p in box.find_all("p") if p.find_parent("p") is None]
        if paragraphs:
            lines.extend(_plain(p) for p in paragraphs)
        else:
            lines.append(_plain(box))
    return " ".join(drop_capital_copies([line for line in lines if line]))


def _cover(pages: list[dict[str, Any]]) -> tuple[str, list[str]]:
    """The title and the authors, as the front cover prints them."""
    from bs4 import BeautifulSoup

    for page in pages:
        if page.get("pageType") != "FrontCoverPage":
            continue
        soup = BeautifulSoup(page.get("html") or "", "html.parser")
        title = soup.select_one(".cover_title")
        author = soup.select_one("#author_names")
        names = _split_names(_plain(author)) if author is not None else []
        return (_plain(title) if title is not None else ""), names
    return "", []


def _split_names(text: str) -> list[str]:
    return [name.strip() for name in re.split(r",|\band\b", text) if name.strip()]


# -- the attribution page ----------------------------------------------------------------


@dataclass(frozen=True)
class Credit:
    """One story on the attribution page: this one, the one it came from, or the original."""

    title: str
    #: Who wrote it, or who translated it.
    names: tuple[str, ...]
    #: `written` or `translated`, as the page says it. Empty for the stories it came from,
    #: which the page names without saying which.
    made: str
    #: Whose © it is, and since when. The translator, for a translation; often the
    #: publisher, for an original.
    holder: str
    year: str
    licence: str
    #: The story's own number, for a story this one came from. None for this one.
    story: int | None = None


@dataclass(frozen=True)
class Picture:
    page: str
    names: tuple[str, ...]
    holder: str
    licence: str


@dataclass(frozen=True)
class Attribution:
    """Everything the attribution page says a book owes, and under what terms."""

    story: Credit
    parent: Credit | None
    original: Credit | None
    pictures: tuple[Picture, ...]
    #: The book's own licence, off the footer every attribution page carries.
    licence: str
    #: The licence's own address, as the footer links it.
    licence_url: str

    def terms(self) -> list[tuple[str, str]]:
        """Every licence the page states, beside what it is the licence of."""
        found = [("the book", self.licence), ("the text", self.story.licence)]
        if self.parent is not None:
            found.append((f"'{self.parent.title}', which it came from", self.parent.licence))
        if self.original is not None:
            found.append((f"the original, '{self.original.title}'", self.original.licence))
        found.extend((f"the picture on the {p.page.lower()}", p.licence) for p in self.pictures)
        return found

    @property
    def credit(self) -> str:
        """The credit CC BY asks for, in one line: who made the words, who made the
        pictures, and where it was found."""
        story = self.story
        parts = [f"{story.title}, {story.made or 'written'} by {_names(story.names)}"]
        parts[0] += _held(story)
        for came, label in ((self.parent, "from"), (self.original, "based on")):
            if came is not None:
                parts.append(f"{label} '{came.title}' by {_names(came.names)}{_held(came)}")
        line = ", ".join(parts) + "."

        drawn: dict[tuple[str, ...], str] = {}
        for picture in self.pictures:
            drawn.setdefault(picture.names, picture.holder)
        if drawn:
            line += " Illustrations by " + "; ".join(
                _names(names) + (f" (© {holder})" if holder else "")
                for names, holder in drawn.items()
            )
            line += "."
        return line + " Via StoryWeaver, Pratham Books."


def _names(names: tuple[str, ...]) -> str:
    if len(names) <= 1:
        return "".join(names) or "unnamed"
    return ", ".join(names[:-1]) + " and " + names[-1]


def _held(credit: Credit) -> str:
    if not credit.holder:
        return ""
    return f" (© {credit.holder}{', ' + credit.year if credit.year else ''})"


# Case matters: "CC BY 4.0 license" and "Public Domain Mark by Pratham Books" are both
# written here, and the licence's BY is in capitals where the publisher's by is not.
_RELEASED = re.compile(r"Released under (?!licen[cs]e\b)(.+?)(?:\s+licen[cs]e\b|\s+by\s|\.?\s*$)")
_HELD = re.compile(r"©\s*(?:for this translation lies with\s*)?(.+?)\s*,\s*(\d{4})")
_TITLE = re.compile(r"This story:\s*(.+?)\s+is\s+(written|translated|adapted|illustrated)\b")
_QUOTED = re.compile(r"'\s*(.+?)\s*'")
_STORY_LINK = re.compile(r"/stories/(\d+)")

#: The footer links the licence it states. A Creative Commons licence is named the way
#: the rest of the shelf writes it, `CC BY 4.0`.
_CC_LINK = re.compile(
    r"creativecommons\.org/licenses/((?:by|nc|nd|sa)(?:-(?:by|nc|nd|sa))*)/(\d\.\d)"
)
_CC0_LINK = re.compile(r"creativecommons\.org/publicdomain/zero/(\d\.\d)")
_PDM_LINK = re.compile(r"creativecommons\.org/(?:about/pdm|publicdomain/mark)")
_FOOTER_TEXT = re.compile(r"This book is\s+(\S+)\s+licensed", re.I)


def _licence_of(link: str, text: str) -> str:
    if found := _CC_LINK.search(link):
        return f"CC {found.group(1).upper()} {found.group(2)}"
    if found := _CC0_LINK.search(link):
        return f"CC0 {found.group(1)}"
    if _PDM_LINK.search(link):
        return "Public Domain Mark"
    if found := _FOOTER_TEXT.search(text):
        # `CC-BY-4.0`, which is how the footer's own sentence writes it.
        family, _, version = found.group(1).upper().rpartition("-")
        return f"CC {family.removeprefix('CC-')} {version}".strip()
    return ""


def _released(text: str) -> str:
    found = _RELEASED.search(text)
    return found.group(1).strip() if found else ""


def _people(span: Any) -> tuple[str, ...]:
    return tuple(
        _clean(a.get_text("")) for a in span.find_all("a") if "/users/" in (a.get("href") or "")
    )


def _credit(span: Any, *, own: bool) -> Credit:
    text = _clean(span.get_text(" "))
    held = _HELD.search(text)
    if own:
        titled = _TITLE.search(text)
        title, made = (titled.group(1), titled.group(2)) if titled else ("", "")
        story = None
    else:
        quoted = _QUOTED.search(text)
        title, made = (quoted.group(1) if quoted else ""), ""
        linked = next(
            (
                _STORY_LINK.search(a.get("href") or "")
                for a in span.find_all("a")
                if _STORY_LINK.search(a.get("href") or "")
            ),
            None,
        )
        story = int(linked.group(1)) if linked else None
    return Credit(
        title=title,
        names=_people(span),
        made=made,
        holder=held.group(1) if held else "",
        year=held.group(2) if held else "",
        licence=_released(text),
        story=story,
    )


def attribution(data: dict[str, Any]) -> Attribution:
    """Read the attribution pages of a book, as `/read` returns them.

    A long book's credits run over several attribution pages, each with the same footer,
    so every one is read and the stories are taken from the first that names them.
    """
    from bs4 import BeautifulSoup

    story: Credit | None = None
    parent: Credit | None = None
    original: Credit | None = None
    pictures: list[Picture] = []
    licence = licence_url = ""

    for page in data.get("pages") or []:
        if page.get("pageType") != "BackInnerCoverPage":
            continue
        soup = BeautifulSoup(page.get("html") or "", "html.parser")
        if (span := soup.select_one("span.self-attribution")) is not None and story is None:
            story = _credit(span, own=True)
        if (
            span := soup.select_one("span.parent-story-attribution")
        ) is not None and parent is None:
            parent = _credit(span, own=False)
        if (
            span := soup.select_one("span.original-story-attribution")
        ) is not None and original is None:
            original = _credit(span, own=False)
        for span in soup.select("span.illustration-attribution"):
            text = _clean(span.get_text(" "))
            held = re.search(r"©\s*(.+?)\s*,\s*\d{4}", text)
            pictures.append(
                Picture(
                    page=text.split(":", 1)[0],
                    names=_people(span),
                    holder=held.group(1) if held else "",
                    licence=_released(text),
                )
            )
        footer = soup.select_one(".cc_footer")
        if footer is not None and not licence:
            link = next((str(a.get("href") or "") for a in footer.find_all("a")), "")
            licence = _licence_of(link, _clean(footer.get_text(" ")))
            licence_url = link if licence else ""

    if story is None:
        raise TargumError(
            "This StoryWeaver book has no attribution page, so its terms are unknown.",
            "A book is only read where its own pages say what it is licensed under.",
        )
    return Attribution(story, parent, original, tuple(pictures), licence, licence_url)


def refuse_unservable(number: int, credits: Attribution) -> None:
    """Refuse a book any of whose stated terms this shelf may not serve, naming which."""
    for what, licence in credits.terms():
        found = verdict(licence)
        if found.standing not in _SERVABLE:
            raise TargumError(
                f"StoryWeaver story {number} is not ours to use: {what} is "
                f"{'under ' + licence if licence else 'under no stated licence'}.",
                f"{found.because}. We read CC BY, CC BY-SA, CC0 and public domain books.",
            )


# -- the fetcher -------------------------------------------------------------------------


#: How long to wait before knocking again when the host answers with a bot check, in
#: seconds, one wait a retry. A second and a half between knocks is not always enough:
#: on 2026-09-14 a pilot run of twenty-one books was challenged after twenty-one calls
#: at that pace, and the same address was let through again a few minutes later. So a
#: challenge is waited out rather than reported at once, and reported only after these.
CHALLENGE_WAITS: tuple[float, ...] = (20.0, 60.0, 120.0)


def _read(number: int) -> dict[str, Any]:
    for wait in (*CHALLENGE_WAITS, None):
        try:
            raw = get(READ.format(id=number))
            break
        except Unreachable as error:
            if not error.challenge:
                raise
            if wait is None:
                raise TargumError(
                    "StoryWeaver asked for a bot check instead of the book.",
                    "It does that to anybody knocking too often. Wait a few minutes and try again.",
                ) from error
            time.sleep(wait)
    try:
        payload: Any = json.loads(raw)
    except json.JSONDecodeError as error:
        raise TargumError(
            f"StoryWeaver sent something other than story {number}.",
            "Usually a bot check served as a page. Wait a minute and try again.",
        ) from error
    if not isinstance(payload, dict) or not payload.get("ok"):
        raise TargumError(f"StoryWeaver has no story {number}.")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise TargumError(f"StoryWeaver has no story {number}.")
    return data


def document_from(number: int, data: dict[str, Any], ingester: str) -> Document:
    """A read book, as a document: title, byline, and a paragraph a page."""
    refuse_unservable(number, attribution(data))
    pages = data.get("pages") or []
    texts = [
        page_text(page.get("html") or "") for page in pages if page.get("pageType") == "StoryPage"
    ]
    paragraphs: list[Paragraph] = [
        (BlockKind.paragraph, None, text) for text in drop_doubled_pages([t for t in texts if t])
    ]
    if not paragraphs:
        raise TargumError(f"StoryWeaver story {number} has no words in it.", "A wordless book.")

    title, authors = _cover(pages)
    return build_document(
        f"storyweaver:{number}",
        blocks_from_paragraphs(with_front_matter(paragraphs, title, ", ".join(authors) or None)),
        ingester=ingester,
        language=language_tag(str(data.get("language") or "")),
        title=title or None,
        author=", ".join(authors) or None,
    )


def english_in(
    number: int,
    data: dict[str, Any],
    read: Callable[[int], dict[str, Any]] | None = None,
) -> str | None:
    """The nearest English version up the chain a book was translated along, or None.

    A book written in English has no English source: it is one. `read` is how the next
    book up is fetched, and is `_read` unless a caller has the pages already.
    """
    fetch = read or _read
    if language_tag(str(data.get("language") or "")) == "en":
        return None
    seen = {number}
    credits = attribution(data)
    for _ in range(MAX_HOPS):
        above = credits.parent or credits.original
        if above is None or above.story is None or above.story in seen:
            return None
        seen.add(above.story)
        upper = fetch(above.story)
        if language_tag(str(upper.get("language") or "")) == "en":
            return f"storyweaver:{above.story}"
        credits = attribution(upper)
    return None


@dataclass(frozen=True)
class Terms:
    """What a catalogue row carries for a StoryWeaver book, read off its own pages."""

    licence: str
    credit: str
    licence_url: str
    #: The story's page, for a person to check the claim against.
    page: str


def terms_from(data: dict[str, Any]) -> Terms:
    credits = attribution(data)
    return Terms(
        credits.licence,
        credits.credit,
        credits.licence_url,
        PAGE.format(slug=data.get("slug") or ""),
    )


class StoryWeaverFetcher:
    name = "storyweaver/1"

    def load(self, identifier: str) -> Document:
        number = book_id(identifier)
        return document_from(number, _read(number), self.name)

    def terms(self, identifier: str) -> Terms:
        return terms_from(_read(book_id(identifier)))

    def english_source(self, identifier: str) -> str | None:
        """`storyweaver:<id>` of the English this book was translated from, or None."""
        number = book_id(identifier)
        return english_in(number, _read(number))
