"""Sefaria, by reference.

    targum build sefaria:Jonah
    targum build "sefaria:Genesis 1-11"
    targum build sefaria:en:Ruth
    targum build "sefaria:Mishneh Torah, Repentance"
    targum build "sefaria:en:Kuzari 1"

Hebrew unless a language is named. One request per book: the API returns a whole book as
chapters of verses, and the largest of them is a fraction of what `url.get` will carry,
so looping over 150 chapters would be a hundred and fifty times the traffic for the same
answer.

**Anything shaped like chapters and verses reads through here.** A section of the Mishneh
Torah is chapters of halakhot and the Kuzari is parts of numbered speeches, which is the
same shape a book of the Tanakh arrives in and the same reason both sides pair for
nothing: the halakhah a translator numbered 3:4 is the halakhah the Hebrew numbers 3:4.
What is Tanakh-specific is not the reading, it is which edition to ask for, and that is
`ENGLISH` and `BEYOND_TANAKH` — see the note above each.

**`fill_in_missing_segments` is a licence hole, and must never be used.** It is the
API's own answer to a patchy translation: ask for a version and get the gaps filled in
from whatever else Sefaria holds. What comes back is still labelled with the version you
asked for and its licence, and the filled text is not that version at all. Asked for the
CC0 Community Translation of `Mishneh Torah, Damages to Property`, it returns 216 of 216
halakhot, says CC0, and hands over Touger's Moznaim translation, which is CC-BY-NC. The
licence check in `_payload` cannot see this, because the response lies to it. So the gaps
stay: an untranslated halakhah is an em dash in the reader, and that is the honest answer.

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
from dataclasses import dataclass
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
# it, but a build makes derivatives and ShareAlike would carry onto them. What it costs is
# the Ibn Tibbon Kuzari, the Wikisource Mishneh Torah and Shulchan Aruch, `Miqra according
# to the Masorah`, and a vocalized Orchot Tzadikim.
#
# It does not cost the Talmud, whatever the version list suggests. `language: "he"` on a
# Sefaria version means Hebrew *script*, not Hebrew: the Bavli is tagged `he` and is
# Aramaic. The index carries no language field at all — `era` and `categories` are the
# only signal, and `era` is `A` for Amoraim there against `T` for the Mishnah. Anything
# that starts trusting that `he` should read this line first.
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
#
# The nine that finished the Tanakh joined them on 2026-09-01, on the same reasoning and
# for a second one: Nach Yomi reads a chapter of Nevi'im or Ketuvim every day and walks
# all thirty-four books, so a daily page built on twenty-five of them would have stopped
# at the first book that was not there. Jeremiah and Ezekiel are the two largest absences
# on this shelf by a wide margin; Chronicles is the one nobody misses until a cycle
# reaches it.
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
    # The nine that complete it.
    "Jeremiah": JPS,
    "Ezekiel": JPS,
    "Hosea": JPS,
    "Joel": JPS,
    "Amos": JPS,
    "Micah": JPS,
    "Nehemiah": JPS,
    "I Chronicles": JPS,
    "II Chronicles": JPS,
}


@dataclass(frozen=True)
class Pair:
    """The two editions one text is read in. An empty side means there is not one."""

    hebrew: str
    english: str


# Everything that is not Tanakh, keyed by the reference's own name. Pinned the same way
# and for the same reasons as `ENGLISH`, and arrived at the same way: fetch both sides,
# count the words, and only then write it down.
#
# **Two extra checks, because outside the Tanakh a version list flatters itself.**
#
# The first is shape. `align/parallel.py` pairs chapter by chapter and refuses a
# translation with more units in a chapter than the source, because pairing through a
# disagreement is a durable, silent mistranslation. Outside the Tanakh that refusal bites
# constantly: an editor who splits one long halakhah in two has made an edition that
# cannot be paired, however good it is. Hyamson's Repentance is complete and excellent and
# runs one paragraph long in chapter 10, so Glazer is here instead. The rule for adding a
# section is therefore: the English that fits, then the English that covers most.
#
# The second is emptiness. `Sefaria Community Translation` is a crowd translation and its
# Mishneh Torah is mostly chapter-shaped holes — `Damages to Property` has two translated
# halakhot in two hundred and sixteen, and the API reports it as a version of the section
# like any other. Coverage has to be measured, never assumed from the version list. Only
# `Rest on the Tenth of Tishrei` is complete enough to be here.
#
# What that leaves is thirteen of the Mishneh Torah's eighty-eight sections — the whole of
# Sefer HaMadda, two of Sefer Ahavah, six of Sefer Zemanim, and three others. The other
# seventy-five have no usable Hebrew, no English that fits, or an English that is a stub.
# `scripts/survey_sefaria.py` is what measured this; run it again before adding a section.
#: The Mishnah: one pair of editions for the whole of it, which is why it is a rule rather
#: than sixty-three rows. Torat Emet 357 is public domain and pointed throughout (0.76 to
#: 0.85 marks per letter, measured across all sixty-three), and Joshua Kulp's is CC-BY,
#: complete, and segmented one unit to one mishnah. Every tractate pairs: identical chapter
#: counts, no English chapter longer than its Hebrew, and not one untranslated mishnah in
#: four thousand one hundred and eighty-seven.
#:
#: Pinning by prefix pins the same thing a row would — the edition — and the licence is
#: still asserted per fetch in `_payload`. What it does not do is offer sixty-three chances
#: to mistype a version title that is the same on all of them.
#:
#: The two editions this passes over are worth knowing about. `Mishnah, ed. Romm, Vilna
#: 1913` is public domain and the standard printing, and carries no vowels at all. Dan
#: Be'eri's edition of the Kaufmann manuscript is public domain, pointed, and the better
#: text — and it re-divides the mishnayot, sets them stichometrically, and prints their
#: numerals inside the text, so it cannot pair with an English numbered to the printed
#: division. Bikkurim is the exception that proves it: see the note in the catalogue.
MISHNAH = Pair("Torat Emet 357", "Mishnah Yomit by Dr. Joshua Kulp")


def is_mishnah(book: str) -> bool:
    """Whether a reference names a tractate of the Mishnah.

    `Mishnah Berakhot`, and `Pirkei Avot`, which Sefaria files under its own name rather
    than as `Mishnah Avot` — the one tractate whose index title does not say what it is.
    A commentary reads `Bartenura on Mishnah Berakhot` and is not one of these; the
    Mishneh Torah is `Mishneh`, not `Mishnah`, and is a different word.
    """
    return book.startswith("Mishnah ") or book == "Pirkei Avot"


BEYOND_TANAKH: dict[str, Pair] = {
    # The Kuzari's English is Hirschfeld's, and there is no Hebrew here on purpose:
    # Sefaria's Ibn Tibbon is Ben-Yehuda's and CC-BY-SA. The vocalized Zifroni text of the
    # same translation is on Hebrew Wikisource, so the Hebrew side is
    # `wikisource:he:ספר הכוזרי מאמר ראשון (אבן תיבון)` and the two are aligned by
    # embeddings rather than by number.
    "Kuzari": Pair("", "Kitab al Khazari, translated by Hartwig Hirschfeld, 1905"),
    # Sefer Madda
    "Mishneh Torah, Foundations of the Torah": Pair(
        "Torat Emet 363",
        "Mishnah Torah, Yod ha-hazakah, trans. by Simon Glazer, 1927",
    ),
    "Mishneh Torah, Human Dispositions": Pair(
        "Torat Emet 363",
        "Mishnah Torah, Yod ha-hazakah, trans. by Simon Glazer, 1927",
    ),
    "Mishneh Torah, Torah Study": Pair(
        "Torat Emet 363",
        "Mishnah Torah, Yod ha-hazakah, trans. by Simon Glazer, 1927",
    ),
    "Mishneh Torah, Foreign Worship and Customs of the Nations": Pair(
        "Torat Emet 363",
        "The Mishneh Torah by Maimonides. trans. by Moses Hyamson, 1937-1949",
    ),
    "Mishneh Torah, Repentance": Pair(
        "Torat Emet 363",
        "Mishnah Torah, Yod ha-hazakah, trans. by Simon Glazer, 1927",
    ),
    # Sefer Ahavah. The other five sections have no Hebrew edition Sefaria will name a
    # licence for — `Torat Emet 370` is the same digitizer as 363 and is tagged `unknown`
    # on them, which is almost certainly a metadata gap and is still not something to
    # guess at.
    "Mishneh Torah, Reading the Shema": Pair(
        "Torat Emet 370",
        "The Mishneh Torah by Maimonides. trans. by Moses Hyamson, 1937-1949",
    ),
    "Mishneh Torah, Prayer and the Priestly Blessing": Pair(
        "Torat Emet 370",
        "The Mishneh Torah by Maimonides. trans. by Moses Hyamson, 1937-1949",
    ),
    # Sefer Zemanim
    "Mishneh Torah, Sabbath": Pair(
        "Torat Emet 363",
        "Sefaria Edition. Translated by R. Francis Nataf, 2019",
    ),
    "Mishneh Torah, Rest on the Tenth of Tishrei": Pair(
        "Torat Emet 363",
        "Sefaria Community Translation",
    ),
    "Mishneh Torah, Shofar, Sukkah and Lulav": Pair(
        "Torat Emet 363",
        "Sefaria Edition. Translated by R. Francis Nataf, 2019",
    ),
    "Mishneh Torah, Fasts": Pair(
        "Torat Emet 363",
        "Sefaria Edition. Translated by R. Francis Nataf, 2019",
    ),
    # Sefer Zeraim, Sefer Shoftim
    "Mishneh Torah, Gifts to the Poor": Pair(
        "Torat Emet 363",
        "Gifts for the Poor, Trans. by Joseph B. Meszler, Williamsburg, Virginia, 2003",
    ),
    "Mishneh Torah, Kings and Wars": Pair(
        "Torat Emet 363",
        "Laws of Kings and Wars. trans. Reuven Brauner, 2012",
    ),
}


_TAG = {"he": "hebrew", "en": "english"}
_MARKUP = re.compile(r"<[^>]+>")
# Whether a verse carries an apparatus rather than only formatting. Cheap enough to ask
# of every verse, and it keeps the Tanakh — which carries neither — on the regex path.
_APPARATUS = re.compile(r'class="(?:footnote|footnote-marker)"')


def plain(text: str) -> str:
    """The words, with the publisher's notes taken out.

    Metsudah's siddur prints its commentary as footnotes, and the API hands them over
    inline: `<sup class="footnote-marker">1</sup><i class="footnote">…</i>` sits inside
    the sentence it annotates. Stripping tags and keeping what is between them — which is
    what every other edition on this shelf needs — glues a paragraph of Avudraham into the
    middle of the blessing, and it is three times the words of the prayer. So a verse that
    says it has an apparatus is parsed rather than scrubbed, and the notes are dropped
    whole. They are worth reading; they are not what the Hebrew beside them says.
    """
    if not _APPARATUS.search(text):
        return _MARKUP.sub("", text)
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(text, "html.parser")
    for tag in soup.select("sup.footnote-marker, i.footnote, .footnote"):
        tag.decompose()
    return soup.get_text()


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


#: A range of chapters written in Hebrew numerals — `א׳-ג׳` — which is how `heRef` comes
#: back for a ranged reference. Only a range: `שמואל א` is the name of a book of the Tanakh
#: and its last word is not a chapter number, so nothing without a hyphen is touched.
_HEBREW_RANGE = re.compile(
    r"\s+[\u05D0-\u05EA]{1,3}[\u05F3\u05F4\"']?[\u05D0-\u05EA]{0,2}"
    r"\s*[-\u2013]\s*"
    r"[\u05D0-\u05EA]{1,3}[\u05F3\u05F4\"']?[\u05D0-\u05EA]{0,2}\s*$"
)


def book_of(ref: str) -> str:
    """`Genesis 1-11` -> `Genesis`. What decides which translation covers it.

    And what a chapter heading is written under, which is why the Hebrew form is here
    too: `heRef` for a ranged reference comes back as `משנה ביכורים א׳-ג׳`, and a heading
    built on that reads "משנה ביכורים א׳-ג׳ א׳".
    """
    without = re.sub(r"\s+\d+(?:[:.]\d+)?(?:-\d+(?:[:.]\d+)?)?\s*$", "", ref).strip()
    return _HEBREW_RANGE.sub("", without).strip()


def version_for(language: str, ref: str) -> str:
    """The pinned edition for this side of this text.

    The Tanakh answers from `HEBREW` and `ENGLISH`; everything else from
    `BEYOND_TANAKH`, which pins both sides because outside the Tanakh there is no one
    Hebrew edition covering the shelf.
    """
    book = book_of(ref)
    if is_mishnah(book):
        return MISHNAH.hebrew if language == "he" else MISHNAH.english
    beyond = BEYOND_TANAKH.get(book)
    if beyond is not None:
        chosen = beyond.hebrew if language == "he" else beyond.english
        if not chosen:
            raise TargumError(
                f"targum has no {_TAG.get(language, language)} edition of {book}.",
                "Every edition Sefaria holds is licensed in a way this shelf may not "
                "serve. Where the text itself is old enough to be free, Wikisource "
                "often has it: try wikisource:he: and the page title.",
            )
        return chosen
    if language == "he":
        return HEBREW
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
            clean = normalize(plain(verse or "")).strip()
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
    # verse carries its ref. 4: works beyond the Tanakh, and footnotes dropped rather than
    # inlined. Free to bump — the hash a document is keyed by is its text, and the text has
    # not changed, so nothing downstream is bought again.
    name = "sefaria/4"

    def load(self, identifier: str) -> Document:
        language, ref = split_ref(identifier)
        if not ref:
            raise TargumError("No book named.", "Try: sefaria:Ruth")
        return document_from_payload(_payload(ref, language), ref, language)
