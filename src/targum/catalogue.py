"""Texts worth reading that already have a published translation.

Every entry here is a pair: a source, and one or more translations somebody has
already made and put in the public domain. Building from one costs nothing at all —
no model is asked to translate anything, the two texts are matched to each other with
embeddings on this machine — and the reading is better for it, because a translator
who worked on a text for a year beats a model that saw it once.

Each entry has been fetched and checked. Wikisource is full of index pages that look
like texts and turn out to be four links: a Hebrew Tanakh book is usually a list of
its chapters, not the chapters. Nothing goes in here until both sides come back with
a plausible amount of prose in them, so add entries the same way — fetch both, look
at the word counts, and only then write them down.

**And count the script, which is the check that was missing.** A text must be at least
95% in the language it claims, measured over its letters. Global Voices taught this the
expensive way: its house style is to quote a source in the original and translate
underneath, so a Hebrew article about Acapulco came back 54% Spanish. Nothing about that
is visible in a word count. What it costs is real — the reader taps a Spanish word and is
handed a Hebrew lemma, and the difficulty measurement, counting Spanish against Hebrew
frequency, called a news brief harder than Gnessin.
"""

from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass, field
from enum import StrEnum
from functools import cache
from pathlib import Path
from typing import Any


class Tag(StrEnum):
    """What a text *is*, rather than where it is filed.

    There was a Beit Midrash shelf here once, and splitting the catalogue in two turned
    out to be the wrong shape: a reader looking for something to read wants one list, and
    a Tanakh is not hidden from them by being in a room they have to know to enter.

    What the split was really for survives, and is the reason this is data rather than a
    heading: some readers — ultra-Orthodox ones especially — would rather not be shown
    secular material at all. Tagging says which texts those readers came for, so a Beit
    Midrash mode can one day show only them. Nothing filters on this today.
    """

    #: The twenty-four books.
    tanakh = "tanakh"
    #: Jewish and religious, but not Tanakh — liturgy, Mishnah, rabbinic commentary.
    #: Nothing in the catalogue carries it yet; it is here so `tanakh` is a vocabulary
    #: rather than a synonym for the whole idea.
    judaica = "judaica"
    #: Reported writing, written to be read the week it happened. The register a learner
    #: meets in a newspaper and nowhere else on this shelf.
    journalism = "journalism"
    #: Match reports. Their own tag rather than a corner of `journalism`, because they are
    #: the fastest, most colloquial Hebrew in the catalogue and a reader either wants them
    #: or does not.
    sport = "sport"


#: The tags a Beit Midrash mode would keep. Named explicitly because `Tag` stopped being a
#: Jewish-only vocabulary the moment journalism arrived: "has any tag at all" used to mean
#: "came for this" and would now hand an Orthodox reader a football report.
JEWISH: frozenset[Tag] = frozenset({Tag.tanakh, Tag.judaica})


class Kind(StrEnum):
    """What sort of thing a text is, which is the first question a reader asks of a list.

    Not a genre taxonomy — six values a reader would actually filter by. Scripture is
    split from poetry on purpose: Psalms and Genesis are both in the Tanakh and are not
    the same reading, and a reader with twenty minutes wants to know which they are
    about to get.
    """

    prose = "prose"
    poetry = "poetry"
    novel = "novel"
    story = "story"
    essay = "essay"
    document = "document"
    #: Journalism. Nothing in the catalogue is one; a reader's own shelf is full of them.
    article = "article"
    #: A play. Its own value rather than a corner of `prose` because it is the only thing
    #: here that is written to be spoken: a named speaker, then a line, and almost nothing
    #: else. It is the closest the public domain gets to conversational Hebrew, and a
    #: reader looking for that will not find it filed under narrative.
    play = "play"
    #: A dialogue written to be learned from — two people, an everyday situation, and a
    #: recording of it. Shaped like a play on the page and nothing like one to a reader
    #: looking through a library: Peretz wrote drama, and these are a scene at a pharmacy
    #: written so somebody can learn to ask for something at a pharmacy. Filed together,
    #: the fifteen minutes a learner has goes to the wrong one.
    dialogue = "dialogue"


class Register(StrEnum):
    """Which Hebrew this is, which decides whether a reader can read it at all.

    Someone fluent in the news is not fluent in Samuel, and the reverse is commoner
    still. The distinction matters more here than in most languages, so it is a field
    rather than something to be inferred from a tag downstream.
    """

    biblical = "biblical"
    modern = "modern"
    #: Anything not in Hebrew, where the axis does not apply.
    none = ""


@dataclass(frozen=True)
class Line:
    """One sentence of a text beside its translation.

    A handful of these ship with each entry so the public page has real reading on it.
    Fetching them at render time would put the network between a visitor and a page, and
    a page that sometimes fails to load is a page that does not get indexed.
    """

    source: str
    target: str


@cache
def _samples() -> dict[str, list[Line]]:
    """The opening lines, from the catalogue file: content, beside the entries it belongs to."""
    raw = _read().get("samples") or {}
    return {
        entry_id: [Line(source=line["source"], target=line["target"]) for line in lines]
        for entry_id, lines in raw.items()
    }


def sample_for(entry_id: str) -> list[Line]:
    """The opening of one text, or nothing if none has been chosen yet."""
    return _samples().get(entry_id, [])


@dataclass(frozen=True)
class Rendering:
    """One published translation of a catalogue text.

    `publisher` and `licence` are not bookkeeping. A reader decides whether to trust a
    translation of scripture by who made it, so both are shown wherever the text is —
    and naming the licence is also how a CC-BY obligation gets discharged by the code
    rather than remembered by a person.
    """

    name: str
    source: str
    note: str = ""
    publisher: str = ""
    licence: str = ""


@dataclass(frozen=True)
class Entry:
    id: str
    title: str
    author: str
    language: str
    source: str
    blurb: str
    words: int
    #: The title in English, under the Hebrew one wherever a title is shown. Every title
    #: and byline in the catalogue is Hebrew script, which for a reader who cannot yet
    #: read it is a list of things they cannot tell apart. Drafted once by
    #: `scripts/english_titles.py` and reviewed by hand; empty means nothing is shown,
    #: never a fallback to the blurb, which in a title's place reads as a title.
    english: str = ""
    tags: frozenset[Tag] = frozenset()
    translations: list[Rendering] = field(default_factory=list)

    #: What it is and which Hebrew it is in. Both are what the library filters on.
    kind: Kind = Kind.prose
    register: Register = Register.none

    #: How hard the words are, on the reader's own six-band scale, measured rather than
    #: judged: the band at which half the running text is covered, counted off the same
    #: annotation the reader marks words with. 0 where nothing has been measured yet.
    #: `scripts/measure_difficulty.py` prints these; they are written down here so a
    #: library page costs no lemmatiser to draw.
    difficulty: int = 0

    @property
    def minutes(self) -> int:
        """How long this takes to read, at the 130 words a minute a learner manages."""
        return max(1, round(self.words / 130))

    #: The model this text's English was bought with, where nobody had published one.
    #:
    #: An entry is one of two things. Most carry a `Rendering`: somebody translated the
    #: text and a build asks no model for anything. The rest were translated once, by us,
    #: and paid for once — the cache is keyed on the model among other things, so a build
    #: that does not name the same model would translate the whole book again at the
    #: reader's expense. Naming it here is what makes the second kind free too, and it is
    #: read from the catalogue rather than from the request: a model that arrived in a
    #: payload would be a way to spend somebody else's money.
    model: str = ""

    @property
    def sample(self) -> list[Line]:
        """The opening, both languages, for the public page.

        Looked up by id rather than stored on the entry, so the excerpt and the entry
        cannot drift apart. Empty is allowed: the page drops the section rather than
        showing a heading over nothing.
        """
        return sample_for(self.id)

    def state(self) -> dict[str, object]:
        from .spoken import is_spoken as _is_spoken

        return {
            "id": self.id,
            "title": self.title,
            "author": self.author,
            "language": self.language,
            "source": self.source,
            "blurb": self.blurb,
            "english": self.english,
            "words": self.words,
            "minutes": self.minutes,
            "kind": self.kind.value,
            "register": self.register.value,
            "difficulty": self.difficulty,
            # Whether it can be listened to. Asked of the disk rather than stored here,
            # so an entry never claims a recording this machine has not got — see
            # `spoken.py`. Imported inside the method for the same reason `everything`
            # does it: this module reads the catalogue file and nothing else.
            "spoken": _is_spoken(self.source),
            "tags": sorted(tag.value for tag in self.tags),
            # Not the model: the page has no use for it and it is not the browser's to
            # ask for. The server reads it back from here when a build starts.
            "translations": [
                {
                    "name": t.name,
                    "source": t.source,
                    "note": t.note,
                    "publisher": t.publisher,
                    "licence": t.licence,
                }
                for t in self.translations
            ],
        }


#: What a drawn cover has to obey, which is most of §10 of the brand guidelines said in
#: the second person. An image model asked for "a Hebrew book cover" will return a scroll,
#: a menorah and a flag every time, and all three are named in the guidelines as things
#: this brand never does — texts, not countries; a letterform may be pure form, never an
#: identity signal. The palette is named in hex because "warm" is not a colour.
COVER_RULES = (
    "Flat matte illustration, no gradients, no metallic sheen, no drop shadows. "
    "Warm off-white paper (#fbf9f5), near-black ink (#1c1a17), and one muted brown-gold "
    "(#7a5c38) used sparingly. No lettering, no numerals, no calligraphy, no logos, no "
    "watermark. No religious or ritual objects of any tradition, no scrolls, no candelabra, "
    "no flags, no maps of any country, no mascots or characters. No faces. "
    "Portrait (2:3), printed endpaper rather than photograph, calm and unhurried."
)


def cover_prompt(entry: Entry) -> str:
    """What to ask an image model for, for one text.

    The subject comes from the text itself — its title, who wrote it, and the sentence
    the catalogue already uses to describe it — and the rest is the brand telling the
    model what not to do. Kept here rather than in the script that runs it so a cover
    and the entry it belongs to cannot drift apart.
    """
    kind = {
        Kind.prose: "a narrative",
        Kind.poetry: "a book of poetry",
        Kind.novel: "a novel",
        Kind.story: "a short story",
        Kind.essay: "an essay",
        Kind.document: "a founding document",
        Kind.article: "an article",
        Kind.play: "a play",
    }[entry.kind]
    return (
        f"A cover image for {kind}: {entry.title} — {entry.author}. {entry.blurb} "
        f"Read the sentence above for its subject and mood, and draw that: "
        f"one still image, a landscape, an interior, or an abstract arrangement of shapes. "
        f"{COVER_RULES}"
    )


def cover_prompt_for(title: str, opening: str = "") -> str:
    """What to ask an image model for, for a text that is not in the catalogue.

    Somebody's own upload has no entry behind it — no kind, no author, no sentence
    describing it — so the subject is what there is: the title, and the first line or two
    of the text itself. The rules are the same rules, because a cover drawn for an upload
    sits on the same shelf as a cover drawn for the catalogue.
    """
    said = " ".join(str(opening).split())[:240]
    return (
        f"A cover image for a text titled: {title}. "
        + (f"It opens: {said} " if said else "")
        + COVER_RULES
    )


#: A chapter numeral, in any of the forms a Hebrew book writes one: א׳, כ״ב, פרק ג,
#: chapter 4, IV, 12. A title that is only this names nothing — `תהילים א׳` is "Psalms 1",
#: and it is the book's name with a number after it.
_NUMBERED = re.compile(
    r"^(?:(?:פרק|chapter|section|part)\s+)?"
    # A Hebrew numeral puts its mark before the last letter once it passes ten: א׳ is 1
    # and ל״ב is 32, so the mark is not a suffix and cannot be matched as one.
    r"(?:[IVXLC]{1,7}|\d{1,3}|[\u05D0-\u05EA]{1,3}(?:[\u05F3\u05F4\"'][\u05D0-\u05EA]{0,2})?)"
    r"[.:]?$",
    re.I,
)


def names_something(title: str, book: str) -> bool:
    """Whether a chapter title is a subject or only a number.

    This is what decides whether a chapter is worth drawing. Most of the library's
    chapters are numerals — a hundred and fifty psalms, fifty chapters of Genesis — and
    asking an image model for "Psalms, chapter 1" gets an invention, confidently drawn.
    Herzl writes `השאלה היהודית` at the top of his, and that is a picture.
    """
    line = " ".join(title.split())
    if book and line.startswith(book):
        line = line[len(book) :].strip()
    return bool(line) and not _NUMBERED.match(line)


def chapter_prompt(entry: Entry, title: str) -> str:
    """What to ask for, for one chapter of a text that already has a cover.

    Consistency is not a thing to describe twice: the rules below are the same rules the
    cover was drawn to, and the drawing script hands the finished cover back as a
    reference image. What changes is the subject, which is the chapter's own title.
    """
    return (
        f"One image in a set, for a chapter of {entry.title} by {entry.author}. "
        f"The set already has a cover; this must sit beside it as obviously the same hand "
        f"and the same series — same palette, same flatness, same weight of mark. "
        f'The chapter is called "{title}". Draw its subject, not the book\'s. '
        f"{COVER_RULES}"
    )


#: What the prose canon's English was translated with, once, in August 2026. Named in one
#: place because the cache is keyed on it: a build that says anything else buys the book
#: again. The catalogue file may say otherwise; this is the default.
BOUGHT_WITH = "claude-opus-5"


# -- the catalogue is data, and the data is private ----------------------------------
#
# The entries — what is in the library, where each text comes from, which published
# translation it pairs with, how hard it measured — are not in this repository. They are
# the product, and the code here is the reader of them. `catalogue.json` is read from the
# first of: TARGUM_CATALOGUE, ~/.targum/catalogue.json, /etc/targum/catalogue.json. With
# none of those the library is empty and says so; nothing else changes.


def catalogue_path() -> Path | None:
    """Where the catalogue is. A path named in the environment is the path, found or
    not — falling back from a wrong one to the machine's own would hand a test suite
    the real catalogue and a deployment somebody else's."""
    named = os.environ.get("TARGUM_CATALOGUE", "").strip()
    if named:
        return Path(named) if Path(named).is_file() else None
    for path in (Path.home() / ".targum" / "catalogue.json", Path("/etc/targum/catalogue.json")):
        if path.is_file():
            return path
    return None


def _entry(raw: dict[str, Any]) -> Entry:
    return Entry(
        id=str(raw["id"]),
        title=str(raw["title"]),
        author=str(raw.get("author", "")),
        language=str(raw["language"]),
        source=str(raw["source"]),
        blurb=str(raw.get("blurb", "")),
        english=str(raw.get("english", "")),
        words=int(raw.get("words", 0)),
        tags=frozenset(Tag(tag) for tag in raw.get("tags", [])),
        translations=[
            Rendering(
                name=str(t["name"]),
                source=str(t["source"]),
                note=str(t.get("note", "")),
                publisher=str(t.get("publisher", "")),
                licence=str(t.get("licence", "")),
            )
            for t in raw.get("translations", [])
        ],
        kind=Kind(raw.get("kind", Kind.prose.value)),
        register=Register(raw.get("register", Register.none.value)),
        difficulty=int(raw.get("difficulty", 0)),
        model=str(raw.get("model", "")),
    )


@cache
def _read() -> dict[str, Any]:
    path = catalogue_path()
    if path is None:
        sys.stderr.write(
            "targum: no catalogue file — the library is empty. "
            "Put one at ~/.targum/catalogue.json or name it in TARGUM_CATALOGUE.\n"
        )
        return {}
    loaded = json.loads(path.read_text(encoding="utf-8"))
    return loaded if isinstance(loaded, dict) else {}


def load() -> list[Entry]:
    """Every entry in the catalogue file, in its order."""
    return [_entry(raw) for raw in _read().get("entries", [])]


BOUGHT_WITH = str(_read().get("bought_with") or BOUGHT_WITH)

CATALOGUE: list[Entry] = load()


def beit_midrash() -> list[Entry]:
    """What a reader who wants only Jewish texts would be left with.

    The catalogue is one list and stays one list; this is the predicate a Beit Midrash
    mode would filter by, defined now so the tagging can be shown to be sufficient for
    it. Nothing in the product calls this yet.
    """
    return [entry for entry in CATALOGUE if entry.tags & JEWISH]


def everything() -> list[Entry]:
    """The curated catalogue, plus whatever the box has published this week.

    `CATALOGUE` stays exactly what it is — a list, built once at import, that tests
    replace wholesale — because making it mutable would make every reader of it racy
    for the sake of one caller. The weekly is generated content with its own clock and
    its own file, so it is joined on at the point of asking rather than merged in.

    Imported here rather than at the top so `catalogue` keeps importing nothing from
    the rest of the package: the weekly reads `Entry` from this module.
    """
    from .weekly import entries as weekly_entries

    return [*CATALOGUE, *weekly_entries.entries()]


def by_id(entry_id: str) -> Entry | None:
    for entry in everything():
        if entry.id == entry_id:
            return entry
    return None


def _key(source: str) -> str:
    """A source flattened enough that two spellings of one text match.

    Wikisource titles arrive with underscores or spaces and in either case, and a
    Gutenberg id can be typed with or without the prefix.
    """
    return source.strip().lower().replace("_", " ").rstrip("/")


def matching(source: str) -> Entry | None:
    """The catalogue entry a source is already, if it is one.

    Used to stop someone paying to translate a text that is sitting here with a
    published translation attached to it.
    """
    wanted = _key(source)
    if not wanted:
        return None
    for entry in everything():
        if _key(entry.source) == wanted:
            return entry
        for rendering in entry.translations:
            if _key(rendering.source) == wanted:
                return entry
    return None
