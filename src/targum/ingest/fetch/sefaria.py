"""Tanakh, from Sefaria, by book.

    targum build sefaria:Jonah
    targum build "sefaria:Genesis 1-11"
    targum build sefaria:en:Ruth

Hebrew unless a language is named. One request per book: the API returns a whole book as
chapters of verses, and the largest of them is a fraction of what `url.get` will carry,
so looping over 150 chapters would be a hundred and fifty times the traffic for the same
answer.

**Why this exists at all.** Hebrew Wikisource's Tanakh "books" are pages listing their
chapters rather than pages holding them, and the editions laid out as parallel tables
lose their bodies to `htmltext`, which strips tables. Sefaria hands over the text itself,
verse by verse, on both sides — which is also what lets a Tanakh pair for nothing at all.

**Versions are pinned, and the licence is checked rather than assumed.** Two reasons, and
neither is theoretical. `Metsudah Chumash, Metsudah Publications, 2009` is CC-BY while
`… 2009 [with Onkelos translation]` is CC-BY-NC, which a paid product may not use — they
differ by a bracketed suffix, so a name match would quietly ship the wrong one. And an
unpinned version can change what it points at without warning.

**The Hebrew is the accented edition, and the shorter name is a trap.** Sefaria also
carries `Tanach with Nikkud`, which sounds like precisely what a reader of vowels wants.
It is not an edition; it is this one with the accents deleted by machine, and that delete
is lossy. Unicode gives meteg and silluq one codepoint, U+05BD, so a program removing
te'amim takes the metagim with them — and meteg is what separates a qamats gadol from a
qamats qatan. The whole of Ruth in that version contains no U+05BD at all. Taking the
complete text and hiding the accents in the reader is the only way round it, so that is
what targum does. Do not shorten this name.
"""

from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import quote

from ...errors import TargumError
from ...ids import block_id
from ...models import BlockKind, Document
from ..base import Paragraph, blocks_from_paragraphs, build_document, normalize
from ..url import get

API = "https://www.sefaria.org/api/v3/texts/{ref}?version={version}"

DEFAULT_LANGUAGE = "he"

# What may be served commercially, with attribution where the licence asks for it.
# CC-BY-NC is deliberately absent: it forbids exactly what this product is.
#
# `PD` is here because Sefaria spells public domain two ways and means the same thing by
# both. Surveyed across twelve works, 85 editions said "Public Domain" and 5 said "PD" —
# and those five include the only modern-Hebrew Tanakh on the shelf (Miqra Mevoar) and
# the Kaufmann Mishnah. A set that knows one spelling refuses free texts on a typo.
#
# CC-BY-SA is deliberately still absent, and it is a real decision rather than an
# oversight: ShareAlike permits commercial use, so the CC-BY-NC reasoning does not reach
# it, but a build makes derivatives and ShareAlike would carry onto them. It costs the
# Wikisource Talmud Bavli, which is the only Hebrew Talmud here under any free licence.
USABLE = frozenset({"Public Domain", "PD", "CC0", "CC-BY"})

# Exact titles, checked against the licence the API reports for each. Hebrew is one
# edition throughout; English is whichever Orthodox translation covers the book, because
# an Orthodox reader is who most of this shelf is for and JPS is not what they reach for.
HEBREW = "Tanach with Ta'amei Hamikra"

#: The fallback English, named once so the eleven books that use it are obviously the
#: same decision rather than eleven separate ones — and so removing it is one search.
JPS = "The Holy Scriptures: A New Translation (JPS 1917)"

# Metsudah covers Torah, the Five Megillot and part of Nevi'im; Silverstein's Rashi
# Ketuvim covers the rest of what is worth reading. A book with neither is not on the
# shelf — which is why there is no Jonah here, its only Orthodox English being CC-BY-NC.
#
# JPS 1917 is public domain and covers every book in the Tanakh, so nothing legal keeps a
# book off this list. What kept these eleven off was editorial: JPS is not the English an
# Orthodox reader reaches for, and its 1917 register — thee, thou, hath — is a second
# language to learn on top of the Hebrew.
#
# They are here anyway, deliberately and for now, because the alternative was worse: the
# recordings of these books are cut and aligned and were reaching nobody. A shelf that
# offers Isaiah in dated English is more use than one that does not offer Isaiah. Replace
# each of them the moment an Orthodox English under a usable licence exists, and take the
# JPS line out when you do — the recording and the Hebrew do not change, so it is a
# one-line swap and a rebuild.
ENGLISH: dict[str, str] = {
    "Genesis": "Metsudah Chumash, Metsudah Publications, 2009",
    "Exodus": "Metsudah Chumash, Metsudah Publications, 2009",
    "Leviticus": "Metsudah Chumash, Metsudah Publications, 2009",
    "Numbers": "Metsudah Chumash, Metsudah Publications, 2009",
    "Deuteronomy": "Metsudah Chumash, Metsudah Publications, 2009",
    "Ruth": "The Metsudah Five Megillot, Lakewood, N.J., 2001",
    "Esther": "The Metsudah Five Megillot, Lakewood, N.J., 2001",
    "Song of Songs": "The Metsudah Five Megillot, Lakewood, N.J., 2001",
    "Ecclesiastes": "The Metsudah Five Megillot, Lakewood, N.J., 2001",
    "Lamentations": "The Metsudah Five Megillot, Lakewood, N.J., 2001",
    "Judges": "The Metsudah Tanach series, Lakewood, N.J",
    "I Samuel": "The Metsudah Tanach series, Lakewood, N.J",
    "II Samuel": "The Metsudah Tanach series, Lakewood, N.J",
    "I Kings": "The Metsudah Tanach series, Lakewood, N.J",
    "Psalms": "The Rashi Ketuvim by Rabbi Shraga Silverstein",
    "Proverbs": "The Rashi Ketuvim by Rabbi Shraga Silverstein",
    "Job": "The Rashi Ketuvim by Rabbi Shraga Silverstein",
    # Silverstein covers these two whole — 357 and 280 verses, none empty — so they join
    # on the edition already here rather than on a new decision about which English.
    "Daniel": "The Rashi Ketuvim by Rabbi Shraga Silverstein",
    "Ezra": "The Rashi Ketuvim by Rabbi Shraga Silverstein",
    # Provisional, on JPS 1917. See the note above before adding another.
    "Joshua": JPS,
    "II Kings": JPS,
    "Isaiah": JPS,
    "Jonah": JPS,
    "Obadiah": JPS,
    "Nahum": JPS,
    "Habakkuk": JPS,
    "Zephaniah": JPS,
    "Haggai": JPS,
    "Zechariah": JPS,
    "Malachi": JPS,
}

_TAG = {"he": "hebrew", "en": "english"}
_MARKUP = re.compile(r"<[^>]+>")

# Hebrew numerals for chapter headings. A Latin digit inside a Hebrew heading is the
# bidi mess `isolate()` exists to paper over, and there is no reason to create it here.
_ONES = " אבגדהוזחטי"
_TENS = " יכלמנסעפצ"
_HUNDREDS = " קרשת"


def hebrew_numeral(number: int) -> str:
    """1 -> א, 15 -> ט״ו, 150 -> ק״נ.

    Fifteen and sixteen are written ט״ו and ט״ז rather than י״ה and י״ו, which would
    spell the Name. Everybody who reads this shelf would notice.
    """
    if number <= 0:
        return str(number)
    letters = ""
    rest = number
    hundreds, rest = divmod(rest, 100)
    while hundreds > 4:  # 500 and up are written as repeated ת
        letters += "ת"
        hundreds -= 4
    if hundreds:
        letters += _HUNDREDS[hundreds]
    if rest == 15:
        letters += "טו"
    elif rest == 16:
        letters += "טז"
    else:
        tens, ones = divmod(rest, 10)
        if tens:
            letters += _TENS[tens]
        if ones:
            letters += _ONES[ones]
    if len(letters) == 1:
        return letters + "׳"
    return letters[:-1] + "״" + letters[-1]


def split_ref(identifier: str) -> tuple[str, str]:
    """`sefaria:en:Ruth` -> ("en", "Ruth"). Hebrew when no language is named.

    Only the two languages this shelf has, spelled out, rather than wikisource's looser
    "any short lowercase head is a language" rule — Sefaria book names are capitalised,
    so a wrong guess would be a confusing error rather than an obvious one.
    """
    rest = identifier
    if rest.lower().startswith("sefaria:"):
        # The registry hands the fetcher what follows the scheme, but a Document's own
        # `source` keeps the whole thing, and both end up here.
        rest = rest.split(":", 1)[1]
    head, sep, tail = rest.partition(":")
    if sep and head.lower() in _TAG:
        return head.lower(), tail.replace("_", " ").strip()
    return DEFAULT_LANGUAGE, rest.replace("_", " ").strip()


def book_of(ref: str) -> str:
    """`Genesis 1-11` -> `Genesis`. What decides which translation covers it."""
    return re.sub(r"\s+\d+(?:[:.]\d+)?(?:-\d+(?:[:.]\d+)?)?\s*$", "", ref).strip()


def version_for(language: str, ref: str) -> str:
    """The pinned edition for this side of this book."""
    if language == "he":
        return HEBREW
    book = book_of(ref)
    if book not in ENGLISH:
        raise TargumError(
            f"targum has no English edition for {book}.",
            "The shelf carries only translations that may be served commercially. "
            f"Books with one: {', '.join(sorted(ENGLISH))}.",
        )
    return ENGLISH[book]


def _payload(ref: str, language: str) -> dict[str, Any]:
    version = version_for(language, ref)
    url = API.format(ref=quote(ref), version=quote(f"{_TAG[language]}|{version}", safe="|"))
    try:
        body = json.loads(get(url))
    except json.JSONDecodeError as error:
        raise TargumError(
            f"Sefaria sent something that is not JSON for {ref}.", str(error)
        ) from error

    editions = body.get("versions") or []
    if not editions:
        offered = [v.get("versionTitle", "") for v in (body.get("available_versions") or [])][:5]
        raise TargumError(
            f"Sefaria has no '{version}' of {ref}.",
            f"It offers: {', '.join(offered)}" if offered else "Check the reference.",
        )
    edition = editions[0]

    licence = (edition.get("license") or "").strip()
    if licence not in USABLE:
        raise TargumError(
            f"'{version}' is licensed {licence or 'unclearly'}, which targum may not serve.",
            "Only public domain, CC0 and CC-BY editions go on the shelf.",
        )
    # Talmud and the commentaries are shaped differently, and a wrong shape here would
    # produce headings over the wrong things rather than an error.
    if body.get("isComplex") or body.get("textDepth") != 2:
        raise TargumError(
            f"{ref} is not a plain chapters-and-verses text.",
            "This reads Tanakh. Other shapes need their own handling.",
        )
    return {"edition": edition, "body": body, "licence": licence, "version": version}


def chapters(payload: dict[str, Any]) -> list[list[str]]:
    """The text as chapters of verses, whatever shape one chapter came back in."""
    text = payload["edition"].get("text") or []
    if text and isinstance(text[0], str):
        return [list(text)]  # a single chapter arrives flat
    return [list(chapter) for chapter in text]


def first_chapter(payload: dict[str, Any]) -> int:
    """Where the numbering starts, so a range is labelled with its real chapters."""
    sections = payload["body"].get("sections") or []
    if sections and str(sections[0]).isdigit():
        return int(sections[0])
    return 1


def document_from_payload(payload: dict[str, Any], ref: str, language: str) -> Document:
    """A Document of verse blocks under chapter headings.

    Separated from the fetching so every structural rule here is testable against a
    saved response rather than against the network.
    """
    body = payload["body"]
    start = first_chapter(payload)
    named = body.get("heRef") if language == "he" else body.get("ref")
    title = str(named or ref)

    # The English book name, whatever language the text is in: a ref is an address, and
    # an address has to be the same one the recording and Sefaria itself use. The Hebrew
    # title is what the reader sees; it is not what a verse is called.
    named_in_english = book_of(str(body.get("ref") or ref))

    paragraphs: list[Paragraph] = []
    # Which verse each paragraph is, by its place in the list. Kept beside the paragraphs
    # rather than inside them: `Paragraph` is the shape every ingester builds, and only a
    # numbered text has anything to put here.
    refs: dict[int, str] = {}
    for offset, verses in enumerate(chapters(payload)):
        number = start + offset
        label = hebrew_numeral(number) if language == "he" else str(number)
        paragraphs.append((BlockKind.heading, 2, f"{book_of(title)} {label}".strip()))
        for count, verse in enumerate(verses, start=1):
            # An empty verse still takes a place. Dropping it would shorten one side of a
            # pairing that only works because both sides count the same.
            clean = normalize(_MARKUP.sub("", verse or "")).strip()
            refs[len(paragraphs)] = f"{named_in_english} {number}:{count}".strip()
            paragraphs.append((BlockKind.verse, None, clean or "—"))

    blocks = blocks_from_paragraphs(paragraphs)
    # By id rather than by position: `blocks_from_paragraphs` drops an empty paragraph and
    # numbers what is left by its original index, so zipping the two lists would silently
    # slide every ref after the first gap onto the wrong verse.
    by_id = {block_id(index): text for index, text in refs.items()}
    for block in blocks:
        block.ref = by_id.get(block.id, "")

    return build_document(
        f"sefaria:{ref}" if language == DEFAULT_LANGUAGE else f"sefaria:{language}:{ref}",
        blocks,
        ingester=SefariaFetcher.name,
        language=language,
        title=title,
    )


class SefariaFetcher:
    # A version, so a change to any rule above re-ingests rather than looking like
    # somebody hand-edited the document on disk. 2: the accented Hebrew edition. 3: every
    # verse carries its ref. Free to bump — the hash a document is keyed by is its text,
    # and the text has not changed, so nothing downstream is bought again.
    name = "sefaria/3"

    def load(self, identifier: str) -> Document:
        language, ref = split_ref(identifier)
        if not ref:
            raise TargumError("No book named.", "Try: sefaria:Ruth")
        return document_from_payload(_payload(ref, language), ref, language)
