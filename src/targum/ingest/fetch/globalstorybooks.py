"""Global Storybooks, by site, story number and language.

    targum build globalstorybooks:sbc/0001/ru
    targum build globalstorybooks:sbc/0001/en

Global Storybooks puts the same openly licensed picture books into dozens of languages,
one site a collection: Storybooks Canada, LIDA Stories for adults learning a language
where they have just arrived, and a site for each of several countries. Every site keeps
its text on GitHub as a `<site>-source` repository under `global-asp`, one folder a
language and one markdown file a story, and the story's number is the same in every
folder. That is the whole address: the site, the number, and the language —
`sbc/0001/ru` is `sbc-source/ru/0001_очень-высокий-человек.md`, and `sbc/0001/en` is the
same story in English, so a catalogue row names the one as the other's translation.

**The number is in the file's name, and the rest of the name is not ours to guess.** A
file is named for its title in its own language, so the Russian slug cannot be worked
out from the number. The folder is listed once (GitHub's contents API) and the file
whose name starts with the number is read (raw.githubusercontent.com). Listings are kept
for the life of the process, because GitHub answers sixty unsigned listings an hour, and
a shelf of seventy stories lives in four folders.

**A file is a story.** `# ` is the title, a line of `##` turns the page, and the last
page is a list of what the story owes: `* License:`, `* Text:`, `* Illustration:`,
`* Translation:`. One paragraph a page, as StoryWeaver's books are read, because the page
is where a translator never moves a sentence across and so what alignment anchors on.

**The licence line is read in every file rather than assumed for a site.** Most of it is
CC BY, and "most" is the reason: 22 of the 57 Russian stories on Storybooks Canada and
LIDA are NonCommercial, written in the same folder in the same format. A story whose own
file does not state terms this shelf may serve is refused, with its terms named. The file
names the licence's family and not its version (`[CC-BY]`, `CC BY-NC-SA`), and the
version is not filled in from the site's badge: the credit says what the file says.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

from ...errors import TargumError, Unreachable
from ...licensing import Standing, verdict
from ...models import BlockKind, Document
from ..base import Paragraph, blocks_from_paragraphs, build_document, normalize, with_front_matter
from ..url import get

LISTING = "https://api.github.com/repos/global-asp/{repo}/contents/{language}?ref=master"
RAW = "https://raw.githubusercontent.com/global-asp/{repo}/master/{language}/{name}"
PAGE = "https://github.com/global-asp/{repo}/blob/master/{language}/{name}"

#: The sites whose source repositories are laid out as this reads them, by the prefix of
#: the repository's name, with the name each site goes by for the credit. Read on
#: 2026-09-15. `lcb-source` is left out: a folder a story, not a folder a language.
SITES = {
    "asp": "African Storybook",
    "isb": "Indigenous Storybooks",
    "lida": "LIDA Stories",
    "sbc": "Storybooks Canada",
    "sbjm": "Storybooks Jamaica",
    "sbk": "Storybooks Kenya",
    "sbno": "Storybooks Norge",
    "sbug": "Storybooks Uganda",
    "sbuk": "Storybooks UK",
}

#: The standings a story may have to be on the shelf: public domain, or owed a credit
#: (CC BY) or a share-alike (CC BY-SA). NonCommercial and anything nobody here recognises
#: are refused.
_SERVABLE = frozenset({Standing.free, Standing.owed})

# A folder is named for its language, and a few carry a variety after it: `lgg-official`,
# `tw-akua`. Only a plain two- or three-letter code is handed on as the document's
# language; a variety is detected from the text, the way a file's is.
_LANGUAGE = re.compile(r"^[a-z]{2,3}(?:-[a-z0-9]+)*$")
_PLAIN_LANGUAGE = re.compile(r"^[a-z]{2,3}$")
_FIELD = re.compile(r"^\*\s*([^:]+?)\s*:\s*(.*)$")


@dataclass(frozen=True)
class Address:
    site: str
    story: str
    language: str

    @property
    def repo(self) -> str:
        return f"{self.site}-source"

    @property
    def key(self) -> str:
        return f"globalstorybooks:{self.site}/{self.story}/{self.language}"


def address(identifier: str) -> Address:
    """`sbc/0001/ru`. The number may drop its zeros, `sbc/1/ru`, and is padded back."""
    parts = identifier.strip().strip("/").split("/")
    hint = "Site, story number and language: globalstorybooks:sbc/0001/ru"
    if len(parts) != 3:
        raise TargumError(
            f"Global Storybooks wants a site/number/language, not '{identifier}'.", hint
        )
    site, story, language = (part.strip().lower() for part in parts)
    if site not in SITES:
        raise TargumError(
            f"Global Storybooks has no site we read called '{site}'.",
            f"We read {', '.join(sorted(SITES))}.",
        )
    if not story.isdigit():
        raise TargumError(f"'{story}' is not a story number.", hint)
    if not _LANGUAGE.match(language):
        raise TargumError(f"'{language}' is not a language folder.", hint)
    return Address(site, story.zfill(4), language)


# -- the file ----------------------------------------------------------------------------


@dataclass(frozen=True)
class Story:
    title: str
    pages: tuple[str, ...]
    #: The list at the foot of the file, keyed in lower case: `license`, `text`,
    #: `illustration`, `translation`, and now and then `adaptation` or `translated by`.
    fields: dict[str, str]

    @property
    def licence_as_written(self) -> str:
        return self.fields.get("license", "")

    @property
    def licence(self) -> str:
        """The licence, written the way the rest of the shelf writes one: `CC BY-NC`.

        The files write it two ways, `[CC-BY-NC]` and `CC BY-NC-SA`, depending on the site.
        """
        written = self.licence_as_written.strip().strip("[]").strip()
        if written.upper().startswith("CC-"):
            written = "CC " + written[3:]
        return written

    @property
    def author(self) -> str:
        return self.fields.get("text", "")

    def words(self) -> int:
        return sum(len(page.split()) for page in self.pages)


def parse(markdown: str) -> Story:
    """A story file, as its title, its pages and the list of what it owes."""
    title = ""
    sections: list[list[str]] = [[]]
    for line in normalize(markdown).split("\n"):
        stripped = line.strip()
        if stripped == "##":
            sections.append([])
        elif stripped.startswith("# ") and not title and len(sections) == 1:
            title = " ".join(stripped[2:].split())
        elif stripped:
            sections[-1].append(stripped)

    pages: list[str] = []
    fields: dict[str, str] = {}
    for lines in sections[1:]:
        found = [_FIELD.match(line) for line in lines]
        if lines and all(found):
            for match in found:
                assert match is not None
                fields[match.group(1).lower()] = " ".join(match.group(2).split())
        elif lines:
            # A page can run over several lines, and a blank line inside one is a pause
            # the translator left, not a page turn.
            pages.append(" ".join(" ".join(lines).split()))
    return Story(title, tuple(pages), fields)


def credit(story: Story, site: str) -> str:
    """The credit CC BY asks for, in one line, in the file's own words."""
    fields = story.fields
    parts = [story.title or "Untitled"]
    for key, label in (
        ("text", "text by"),
        ("adaptation", "adapted by"),
        ("illustration", "illustrations by"),
        ("translation", "translated by"),
        ("translated by", "translated by"),
    ):
        if fields.get(key):
            parts.append(f"{label} {fields[key]}")
    return ", ".join(parts) + f". Via {SITES.get(site, site)}, Global Storybooks."


def refuse_unservable(where: Address, story: Story) -> None:
    found = verdict(story.licence)
    if found.standing not in _SERVABLE:
        written = story.licence_as_written
        raise TargumError(
            f"Global Storybooks story {where.site}/{where.story}/{where.language} is not ours "
            f"to use: it is {'under ' + written if written else 'under no stated licence'}.",
            f"{found.because}. We read CC BY, CC BY-SA, CC0 and public domain stories.",
        )


# -- the fetcher -------------------------------------------------------------------------


_listings: dict[tuple[str, str], tuple[str, ...]] = {}


def _listing(repo: str, language: str) -> tuple[str, ...]:
    """The names of the story files in one language folder."""
    held = _listings.get((repo, language))
    if held is not None:
        return held
    try:
        raw = get(LISTING.format(repo=repo, language=language))
    except Unreachable as error:
        if error.status == 404:
            return ()
        if error.status in (403, 429):
            raise TargumError(
                "GitHub stopped listing Global Storybooks for us for now.",
                "It answers sixty unsigned listings an hour. Wait an hour and try again.",
            ) from error
        raise
    try:
        names = names_in(raw)
    except json.JSONDecodeError as error:
        raise TargumError(
            f"GitHub sent something other than the {repo} {language} folder."
        ) from error
    _listings[(repo, language)] = names
    return names


def names_in(listing: str) -> tuple[str, ...]:
    """The markdown files named in a contents API answer for one folder."""
    entries: Any = json.loads(listing)
    return tuple(
        str(entry.get("name") or "")
        for entry in (entries if isinstance(entries, list) else [])
        if isinstance(entry, dict) and str(entry.get("name") or "").endswith(".md")
    )


def pick(names: tuple[str, ...], story: str) -> str | None:
    """The file for a story number among a folder's names: `0001_…`, and only `0001_`."""
    return next((name for name in names if name.startswith(f"{story}_")), None)


def file_name(where: Address) -> str | None:
    """The story's file in its language folder, or None where the site has no such story."""
    return pick(_listing(where.repo, where.language), where.story)


def _read(where: Address) -> tuple[str, Story]:
    name = file_name(where)
    if name is None:
        raise TargumError(
            f"{SITES[where.site]} has no story {where.story} in '{where.language}'.",
            f"The folder is github.com/global-asp/{where.repo}/tree/master/{where.language}",
        )
    markdown = get(RAW.format(repo=where.repo, language=where.language, name=quote(name)))
    return name, parse(markdown)


def document_from(where: Address, story: Story, ingester: str) -> Document:
    """A read story, as a document: title, byline, and a paragraph a page."""
    refuse_unservable(where, story)
    if not story.pages:
        raise TargumError(f"Global Storybooks story {where.key} has no words in it.")
    paragraphs: list[Paragraph] = [(BlockKind.paragraph, None, page) for page in story.pages]
    return build_document(
        where.key,
        blocks_from_paragraphs(with_front_matter(paragraphs, story.title, story.author or None)),
        ingester=ingester,
        language=where.language if _PLAIN_LANGUAGE.match(where.language) else None,
        title=story.title or None,
        author=story.author or None,
    )


@dataclass(frozen=True)
class Terms:
    """What a catalogue row carries for a story, read off its own file."""

    licence: str
    credit: str
    #: Empty: the file names no version, so there is no one deed to link to.
    licence_url: str
    #: The file on GitHub, where the licence line can be checked by a person.
    page: str


class GlobalStorybooksFetcher:
    name = "globalstorybooks/1"

    def load(self, identifier: str) -> Document:
        where = address(identifier)
        _, story = _read(where)
        return document_from(where, story, self.name)

    def terms(self, identifier: str) -> Terms:
        where = address(identifier)
        name, story = _read(where)
        page = PAGE.format(repo=where.repo, language=where.language, name=quote(name))
        return Terms(story.licence, credit(story, where.site), "", page)

    def english_source(self, identifier: str) -> str | None:
        """The same story in the site's English folder, or None.

        A story keeps its number in every language folder, so the English is the same
        address with `en` at the end. The file does not say which language came first; the
        English is a published translation beside it either way, and not one to buy.
        """
        where = address(identifier)
        if where.language == "en":
            return None
        english = Address(where.site, where.story, "en")
        return english.key if file_name(english) is not None else None
