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
import re
from dataclasses import dataclass, field
from enum import StrEnum
from functools import cache
from pathlib import Path


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
    """The opening lines, kept as data beside this module.

    Not written inline below, for two reasons: real sentences are longer than the line
    limit this codebase holds itself to, and a catalogue of two dozen Tanakh books would
    bury the entries under their own excerpts. It is content, so it lives in a file.
    """
    path = Path(__file__).with_name("samples.json")
    if not path.is_file():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
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
        return {
            "id": self.id,
            "title": self.title,
            "author": self.author,
            "language": self.language,
            "source": self.source,
            "blurb": self.blurb,
            "words": self.words,
            "minutes": self.minutes,
            "kind": self.kind.value,
            "register": self.register.value,
            "difficulty": self.difficulty,
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
#: again.
BOUGHT_WITH = "claude-opus-5"

CATALOGUE: list[Entry] = [
    Entry(
        id="il-declaration",
        title="מגילת העצמאות",
        author="State of Israel, 1948",
        language="he",
        source="wikisource:he:מגילת העצמאות של מדינת ישראל",
        blurb=(
            "The founding declaration, in the formal register Hebrew keeps for occasions. "
            "Short, and every sentence of it is quoted somewhere."
        ),
        words=655,
        kind=Kind.document,
        register=Register.modern,
        difficulty=18,
        translations=[
            Rendering(
                name="Official English",
                source="wikisource:Declaration of Independence (Israel)",
                note="Published by the State of Israel alongside the Hebrew.",
            )
        ],
    ),
    Entry(
        id="us-declaration-he",
        title="הכרזת העצמאות של ארצות הברית",
        author="Thomas Jefferson, 1776",
        language="he",
        source="wikisource:he:הכרזת העצמאות של ארצות הברית",
        blurb=(
            "A Hebrew translation of a text you very likely already know in English, "
            "which makes it an easy way in: you can guess ahead and check yourself."
        ),
        words=998,
        kind=Kind.document,
        register=Register.modern,
        difficulty=20,
        translations=[
            Rendering(
                name="The English original",
                source="wikisource:United States Declaration of Independence (engrossed copy)",
                note="Not a translation but the text it was translated from.",
            )
        ],
    ),
    Entry(
        id="father-sergius",
        title="Отец Сергий",
        author="Лев Толстой, 1898",
        language="ru",
        source="wikisource:ru:Отец Сергий (Толстой)",
        blurb=(
            "Late Tolstoy, novella length, plain sentences and a plot that pulls. "
            "Long enough to be a real reading project rather than an afternoon."
        ),
        words=13806,
        kind=Kind.story,
        register=Register.none,
        difficulty=24,
        translations=[
            Rendering(
                name="Louise and Aylmer Maude",
                source="gutenberg:985",
                note="The Maudes knew Tolstoy and he approved of their translations.",
            )
        ],
    ),
    Entry(
        id="ruth",
        title="רות",
        author="Ketuvim · Ruth",
        language="he",
        source="sefaria:Ruth",
        blurb="Four chapters, and the shortest way in: one family, one harvest, plain narrative.",
        words=1129,
        kind=Kind.prose,
        register=Register.biblical,
        difficulty=24,
        tags=frozenset({Tag.tanakh}),
        translations=[
            Rendering(
                name="The Metsudah Five Megillot, Lakewood, N.J., 2001",
                source="sefaria:en:Ruth",
                note="A linear translation, made to be read beside the Hebrew.",
                publisher="Metsudah Publications, Lakewood N.J.",
                licence="CC-BY",
            )
        ],
    ),
    Entry(
        id="esther",
        title="אסתר",
        author="Ketuvim · Esther",
        language="he",
        source="sefaria:Esther",
        blurb="Read whole every Purim. Court intrigue, and not one mention of God.",
        words=2609,
        kind=Kind.prose,
        register=Register.biblical,
        difficulty=17,
        tags=frozenset({Tag.tanakh}),
        translations=[
            Rendering(
                name="The Metsudah Five Megillot, Lakewood, N.J., 2001",
                source="sefaria:en:Esther",
                note="A linear translation, made to be read beside the Hebrew.",
                publisher="Metsudah Publications, Lakewood N.J.",
                licence="CC-BY",
            )
        ],
    ),
    Entry(
        id="song-of-songs",
        title="שיר השירים",
        author="Ketuvim · Song of Songs",
        language="he",
        source="sefaria:Song of Songs",
        blurb="Love poetry, and the Hebrew repays every minute it takes.",
        words=1142,
        kind=Kind.poetry,
        register=Register.biblical,
        difficulty=31,
        tags=frozenset({Tag.tanakh}),
        translations=[
            Rendering(
                name="The Metsudah Five Megillot, Lakewood, N.J., 2001",
                source="sefaria:en:Song of Songs",
                note="A linear translation, made to be read beside the Hebrew.",
                publisher="Metsudah Publications, Lakewood N.J.",
                licence="CC-BY",
            )
        ],
    ),
    Entry(
        id="lamentations",
        title="איכה",
        author="Ketuvim · Lamentations",
        language="he",
        source="sefaria:Lamentations",
        blurb="Five acrostics on the fall of Jerusalem. The alphabet is visible down the page.",
        words=1405,
        kind=Kind.poetry,
        register=Register.biblical,
        difficulty=33,
        tags=frozenset({Tag.tanakh}),
        translations=[
            Rendering(
                name="The Metsudah Five Megillot, Lakewood, N.J., 2001",
                source="sefaria:en:Lamentations",
                note="A linear translation, made to be read beside the Hebrew.",
                publisher="Metsudah Publications, Lakewood N.J.",
                licence="CC-BY",
            )
        ],
    ),
    Entry(
        id="ecclesiastes",
        title="קהלת",
        author="Ketuvim · Ecclesiastes",
        language="he",
        source="sefaria:Ecclesiastes",
        blurb="Everything you have heard quoted in English, in the Hebrew it was written in.",
        words=2594,
        kind=Kind.prose,
        register=Register.biblical,
        difficulty=18,
        tags=frozenset({Tag.tanakh}),
        translations=[
            Rendering(
                name="The Metsudah Five Megillot, Lakewood, N.J., 2001",
                source="sefaria:en:Ecclesiastes",
                note="A linear translation, made to be read beside the Hebrew.",
                publisher="Metsudah Publications, Lakewood N.J.",
                licence="CC-BY",
            )
        ],
    ),
    Entry(
        id="psalms",
        title="תהילים",
        author="Ketuvim · Psalms",
        language="he",
        source="sefaria:Psalms",
        blurb="A hundred and fifty, and you can begin at any one of them.",
        words=17255,
        kind=Kind.poetry,
        register=Register.biblical,
        difficulty=35,
        tags=frozenset({Tag.tanakh}),
        translations=[
            Rendering(
                name="The Rashi Ketuvim by Rabbi Shraga Silverstein",
                source="sefaria:en:Psalms",
                note=(
                    "Translated with Rashi's commentary in view. "
                    "Psalm 82:8 has no English in this edition."
                ),
                publisher="Rabbi Shraga Silverstein",
                licence="CC-BY",
            )
        ],
    ),
    Entry(
        id="proverbs",
        title="משלי",
        author="Ketuvim · Proverbs",
        language="he",
        source="sefaria:Proverbs",
        blurb="Self-contained verses, which makes it the easiest thing here to read a little of.",
        words=6080,
        kind=Kind.poetry,
        register=Register.biblical,
        difficulty=32,
        tags=frozenset({Tag.tanakh}),
        translations=[
            Rendering(
                name="The Rashi Ketuvim by Rabbi Shraga Silverstein",
                source="sefaria:en:Proverbs",
                note="Translated with Rashi's commentary in view.",
                publisher="Rabbi Shraga Silverstein",
                licence="CC-BY",
            )
        ],
    ),
    Entry(
        id="job",
        title="איוב",
        author="Ketuvim · Job",
        language="he",
        source="sefaria:Job",
        blurb="The hardest Hebrew in the catalogue, and for many people the reason to learn it.",
        words=7164,
        kind=Kind.poetry,
        register=Register.biblical,
        difficulty=33,
        tags=frozenset({Tag.tanakh}),
        translations=[
            Rendering(
                name="The Rashi Ketuvim by Rabbi Shraga Silverstein",
                source="sefaria:en:Job",
                note="Translated with Rashi's commentary in view.",
                publisher="Rabbi Shraga Silverstein",
                licence="CC-BY",
            )
        ],
    ),
    Entry(
        id="genesis",
        title="בראשית",
        author="Torah · Genesis",
        language="he",
        source="sefaria:Genesis",
        blurb="Where it begins, and the chapters everybody knows are near the front.",
        words=17676,
        kind=Kind.prose,
        register=Register.biblical,
        difficulty=23,
        tags=frozenset({Tag.tanakh}),
        translations=[
            Rendering(
                name="Metsudah Chumash, Metsudah Publications, 2009",
                source="sefaria:en:Genesis",
                note="A linear translation, made to be read beside the Hebrew.",
                publisher="Metsudah Publications",
                licence="CC-BY",
            )
        ],
    ),
    Entry(
        id="exodus",
        title="שמות",
        author="Torah · Exodus",
        language="he",
        source="sefaria:Exodus",
        blurb="Slavery, departure, and the law. The narrative half reads easiest.",
        words=14282,
        kind=Kind.prose,
        register=Register.biblical,
        difficulty=27,
        tags=frozenset({Tag.tanakh}),
        translations=[
            Rendering(
                name="Metsudah Chumash, Metsudah Publications, 2009",
                source="sefaria:en:Exodus",
                note="A linear translation, made to be read beside the Hebrew.",
                publisher="Metsudah Publications",
                licence="CC-BY",
            )
        ],
    ),
    Entry(
        id="leviticus",
        title="ויקרא",
        author="Torah · Leviticus",
        language="he",
        source="sefaria:Leviticus",
        blurb="The priestly law, in the register it was set down in.",
        words=10078,
        kind=Kind.prose,
        register=Register.biblical,
        difficulty=28,
        tags=frozenset({Tag.tanakh}),
        translations=[
            Rendering(
                name="Metsudah Chumash, Metsudah Publications, 2009",
                source="sefaria:en:Leviticus",
                note="A linear translation, made to be read beside the Hebrew.",
                publisher="Metsudah Publications",
                licence="CC-BY",
            )
        ],
    ),
    Entry(
        id="numbers",
        title="במדבר",
        author="Torah · Numbers",
        language="he",
        source="sefaria:Numbers",
        blurb="Forty years of wandering, two censuses, and Balaam's donkey.",
        words=14137,
        kind=Kind.prose,
        register=Register.biblical,
        difficulty=26,
        tags=frozenset({Tag.tanakh}),
        translations=[
            Rendering(
                name="Metsudah Chumash, Metsudah Publications, 2009",
                source="sefaria:en:Numbers",
                note="A linear translation, made to be read beside the Hebrew.",
                publisher="Metsudah Publications",
                licence="CC-BY",
            )
        ],
    ),
    Entry(
        id="deuteronomy",
        title="דברים",
        author="Torah · Deuteronomy",
        language="he",
        source="sefaria:Deuteronomy",
        blurb="Moses saying it again before the end. The book the rest of the Tanakh quotes most.",
        words=12404,
        kind=Kind.prose,
        register=Register.biblical,
        difficulty=27,
        tags=frozenset({Tag.tanakh}),
        translations=[
            Rendering(
                name="Metsudah Chumash, Metsudah Publications, 2009",
                source="sefaria:en:Deuteronomy",
                note="A linear translation, made to be read beside the Hebrew.",
                publisher="Metsudah Publications",
                licence="CC-BY",
            )
        ],
    ),
    Entry(
        id="judges",
        title="שופטים",
        author="Nevi'im · Judges",
        language="he",
        source="sefaria:Judges",
        blurb="Before the kings: twelve leaders, and the years between them.",
        words=8453,
        kind=Kind.prose,
        register=Register.biblical,
        difficulty=23,
        tags=frozenset({Tag.tanakh}),
        translations=[
            Rendering(
                name="The Metsudah Tanach series, Lakewood, N.J",
                source="sefaria:en:Judges",
                note="A linear translation, made to be read beside the Hebrew.",
                publisher="Metsudah Publications, Lakewood N.J.",
                licence="CC-BY",
            )
        ],
    ),
    Entry(
        id="i-samuel",
        title="שמואל א",
        author="Nevi'im · I Samuel",
        language="he",
        source="sefaria:I Samuel",
        blurb="Samuel, Saul, and the young David.",
        words=11424,
        kind=Kind.prose,
        register=Register.biblical,
        difficulty=25,
        tags=frozenset({Tag.tanakh}),
        translations=[
            Rendering(
                name="The Metsudah Tanach series, Lakewood, N.J",
                source="sefaria:en:I Samuel",
                note="A linear translation, made to be read beside the Hebrew.",
                publisher="Metsudah Publications, Lakewood N.J.",
                licence="CC-BY",
            )
        ],
    ),
    Entry(
        id="ii-samuel",
        title="שמואל ב",
        author="Nevi'im · II Samuel",
        language="he",
        source="sefaria:II Samuel",
        blurb="David reigning, and paying for it.",
        words=9399,
        kind=Kind.prose,
        register=Register.biblical,
        difficulty=22,
        tags=frozenset({Tag.tanakh}),
        translations=[
            Rendering(
                name="The Metsudah Tanach series, Lakewood, N.J",
                source="sefaria:en:II Samuel",
                note="A linear translation, made to be read beside the Hebrew.",
                publisher="Metsudah Publications, Lakewood N.J.",
                licence="CC-BY",
            )
        ],
    ),
    Entry(
        id="i-kings",
        title="מלכים א",
        author="Nevi'im · I Kings",
        language="he",
        source="sefaria:I Kings",
        blurb="Solomon, the Temple, and a kingdom splitting in two.",
        words=11255,
        kind=Kind.prose,
        register=Register.biblical,
        difficulty=22,
        tags=frozenset({Tag.tanakh}),
        translations=[
            Rendering(
                name="The Metsudah Tanach series, Lakewood, N.J",
                source="sefaria:en:I Kings",
                note="A linear translation, made to be read beside the Hebrew.",
                publisher="Metsudah Publications, Lakewood N.J.",
                licence="CC-BY",
            )
        ],
    ),
    # --- Modern Hebrew prose, translated once and paid for once -------------------
    #
    # The other half of the catalogue. Nobody has published an English these are worth
    # reading beside, so targum bought one: Opus 5, once, in August 2026. Public sources
    # cache with no owner, so the second reader of any of them pays nothing — provided
    # the build names the model the first one used, which is what `model` below is for.
    #
    # All six are on Ben Yehuda, whose plain-text downloads carry no title of their own:
    # the first line of the file is the title and the author, as prose. The title here is
    # what names the targum on somebody's shelf.
    Entry(
        id="judenstaat",
        title="מדינת היהודים",
        author="בנימין זאב הרצל, תרגם מיכל ברקוביץ, 1896",
        language="he",
        source="https://benyehuda.org/download/6600.txt",
        blurb=(
            "The pamphlet that started it, in the Hebrew it was read in at the time. "
            "Short, argued rather than dreamt, and still surprising."
        ),
        words=20173,
        kind=Kind.essay,
        register=Register.modern,
        difficulty=19,
        model=BOUGHT_WITH,
    ),
    Entry(
        id="mendele-binyamin",
        title="מסעות בנימין השלישי",
        author="מנדלי מוכר ספרים, 1878",
        language="he",
        source="https://benyehuda.org/download/6408.txt",
        blurb=(
            "A Jewish Don Quixote who sets out from a small town to find the lost tribes "
            "and gets about as far as the next province. The funniest book on this shelf."
        ),
        words=24387,
        kind=Kind.novel,
        register=Register.modern,
        difficulty=24,
        model=BOUGHT_WITH,
    ),
    Entry(
        id="mendele-kabtzanim",
        title="ספר הקבצנים",
        author="מנדלי מוכר ספרים, 1909",
        language="he",
        source="https://benyehuda.org/download/4094.txt",
        blurb=(
            "The book that taught modern Hebrew prose how to describe poverty without "
            "either flinching or sentimentalising. Mendele's own Hebrew of his Yiddish."
        ),
        words=42966,
        kind=Kind.novel,
        register=Register.modern,
        difficulty=26,
        model=BOUGHT_WITH,
    ),
    Entry(
        id="mapu-ahavat-tzion",
        title="אהבת ציון",
        author="אברהם מאפו, 1853",
        language="he",
        source="https://benyehuda.org/download/957.txt",
        blurb=(
            "The first modern Hebrew novel: a romance set in the days of Isaiah, written "
            "in deliberate Biblical Hebrew. Easier than it sounds if you have read Tanakh."
        ),
        words=55342,
        kind=Kind.novel,
        register=Register.modern,
        difficulty=25,
        model=BOUGHT_WITH,
    ),
    Entry(
        id="herzl-altneuland",
        title="תל־אביב",
        author="בנימין זאב הרצל, תרגם נחום סוקולוב, 1902",
        language="he",
        source="https://benyehuda.org/download/7260.txt",
        blurb=(
            "Herzl's novel of the country he expected, and the translation that gave Tel "
            "Aviv its name. Sokolow's Hebrew is the period's, not ours."
        ),
        words=62932,
        kind=Kind.novel,
        register=Register.modern,
        difficulty=19,
        model=BOUGHT_WITH,
    ),
    Entry(
        id="brenner-shkhol",
        title="שכול וכשלון",
        author="יוסף חיים ברנר, 1920",
        language="he",
        source="https://benyehuda.org/download/869.txt",
        blurb=(
            "Bereavement and failure, and it means both. The hardest and best of the "
            "early novels, written in a Hebrew that was still being made up as it went."
        ),
        words=66040,
        kind=Kind.novel,
        register=Register.modern,
        difficulty=17,
        model=BOUGHT_WITH,
    ),
    # --- Global Voices, where the Hebrew is itself the translation -----------------
    #
    # The one modern source found that is both openly licensed and already translated by
    # a person, so these build free the way the Tanakh does. The direction is reversed
    # from everything above: the English is the original and the Hebrew is somebody's
    # translation of it, which is stated on each entry rather than left to be inferred.
    #
    # CC BY 3.0, verified in the page footer of each. **Check the byline before adding a
    # fourth.** Global Voices republishes partner material — one candidate turned out to
    # be PRI's, whose licence is not theirs to give — so an entry needs an author who
    # writes for Global Voices, not merely an article that appears on it.
    Entry(
        id="gv-baloch-march",
        title="האישה שצעדה אלפי קילומטרים למען אחיה",
        author="Jahanzeb Hussain, תרגמה Gallia Hoz, 2014",
        language="he",
        source="https://he.globalvoices.org/2014/09/27/261/",
        blurb=(
            "Farzana Majeed walked from Quetta to Islamabad for a brother nobody would "
            "account for. Told plainly, which is what makes it hard to put down."
        ),
        words=978,
        kind=Kind.article,
        register=Register.modern,
        difficulty=15,
        tags=frozenset({Tag.journalism}),
        translations=[
            Rendering(
                name="The English original",
                source="https://globalvoices.org/2014/07/15/farzana-majeed-heads-international-voices-baloch-missing-persons/",
                note="The Hebrew is a translation of this, not the other way round.",
                publisher="Global Voices",
                licence="CC-BY",
            )
        ],
    ),
    # --- Hebrew Wikinews, and the first news register in the catalogue -------------
    #
    # CC BY 4.0: attribution only, no ShareAlike, so a bought translation stays ours.
    # Nobody has published an English, so these are the bought kind — but unlike the
    # prose canon above, **the translation has not been paid for yet.** The first reader
    # to open one buys it, at roughly nine cents for two thousand words, and every reader
    # after them reads it free. Warm them before launch rather than after.
    Entry(
        id="news-sharon",
        title="אריאל שרון הלך לעולמו והוא בן 85",
        author="ויקיחדשות, 2014",
        language="he",
        source="https://he.wikinews.org/wiki/אריאל_שרון_הלך_לעולמו_והוא_בן_85",
        blurb=(
            "Written the day he died, and it opens by saying that whether you loved him "
            "is beside the point. Israeli news Hebrew at full stretch."
        ),
        words=2093,
        kind=Kind.article,
        register=Register.modern,
        difficulty=14,
        tags=frozenset({Tag.journalism}),
        model=BOUGHT_WITH,
    ),
    Entry(
        id="news-pope",
        title="לראשונה מזה 600 שנה: האפיפיור פורש מתפקידו",
        author="ויקיחדשות, 2013",
        language="he",
        source="https://he.wikinews.org/wiki/לראשונה_מזה_600_שנה:_האפיפיור_פורש_מתפקידו",
        blurb=(
            "The first pope to resign in six hundred years, reported in Hebrew. World "
            "news is a different register from Israeli news and worth meeting."
        ),
        words=1546,
        kind=Kind.article,
        register=Register.modern,
        difficulty=23,
        tags=frozenset({Tag.journalism}),
        model=BOUGHT_WITH,
    ),
    Entry(
        id="news-ferguson",
        title="פרגוסון עוזב את מנצ׳סטר יונייטד",
        author="ויקיחדשות, 2013",
        language="he",
        source="https://he.wikinews.org/wiki/פרגוסון_עוזב_את_מנצ'סטר_יונייטד",
        blurb=(
            "Twenty-seven years at Manchester United, ended in one announcement. Sports "
            "Hebrew is the fastest here, and this is the gentle way into it."
        ),
        words=1425,
        kind=Kind.article,
        register=Register.modern,
        difficulty=13,
        tags=frozenset({Tag.journalism, Tag.sport}),
        model=BOUGHT_WITH,
    ),
    # --- Something short enough to finish -----------------------------------------
    #
    # Everything literary above is a novel of twenty to sixty thousand words, which is a
    # month for a learner. Berdyczewski wrote hundreds of short stories and they are on
    # Ben Yehuda beside the novels: one sitting each, the same Hebrew, no commitment.
    # Bought, and not yet warmed, exactly as the news above.
    Entry(
        id="mjb-havera",
        title="החברה",
        author="מיכה יוסף ברדיצ׳בסקי",
        language="he",
        source="https://benyehuda.org/download/2631.txt",
        blurb=(
            "She was not beautiful in the ordinary sense, but her charm was great. Six "
            "hundred words, one woman, and a whole life implied around her."
        ),
        words=667,
        kind=Kind.story,
        register=Register.modern,
        difficulty=15,
        model=BOUGHT_WITH,
    ),
    Entry(
        id="mjb-habikur",
        title="הביקור",
        author="מיכה יוסף ברדיצ׳בסקי",
        language="he",
        source="https://benyehuda.org/download/4896.txt",
        blurb=(
            "A man arrives from Rome with his servant, and the visit goes the way visits "
            "go. Berdyczewski at his driest."
        ),
        words=1011,
        kind=Kind.story,
        register=Register.modern,
        difficulty=13,
        model=BOUGHT_WITH,
    ),
    Entry(
        id="mjb-haakhbar",
        title="העכבר",
        author="מיכה יוסף ברדיצ׳בסקי",
        language="he",
        source="https://benyehuda.org/download/7519.txt",
        blurb=(
            "A small, thin man who walked, they said, like a bent nun. A portrait that "
            "turns quietly into something else."
        ),
        words=1784,
        kind=Kind.story,
        register=Register.modern,
        difficulty=17,
        model=BOUGHT_WITH,
    ),
    # --- Global Voices, the rest of the archive ------------------------------------
    #
    # Thirty-two Hebrew posts exist in total and the site stopped publishing in Nov 2016;
    # these are the ones over three hundred words with a Global Voices byline. Two were
    # left out for the licence rather than the writing: one is PRI's and one is NACLA's,
    # and Global Voices cannot grant what it does not hold.
    Entry(
        id="gv-syria-killers",
        title="בסוריה הפכנו כולנו לרוצחים",
        author="Omid Memarian, תרגם Gallia Hoz, 2014",
        language="he",
        source="https://he.globalvoices.org/2014/06/27/251/",
        blurb=("A Syrian writer on what the war did to the people who never fought in it."),
        words=955,
        kind=Kind.article,
        register=Register.modern,
        difficulty=15,
        tags=frozenset({Tag.journalism}),
        translations=[
            Rendering(
                name="The English original",
                source="https://globalvoices.org/2014/06/27/we-have-all-become-killers-in-syria/",
                note="The Hebrew is a translation of this, not the other way round.",
                publisher="Global Voices",
                licence="CC-BY",
            )
        ],
    ),
    Entry(
        id="gv-syria-dictator",
        title="לו הייתי דיקטטור, הייתי רואה בכם אויב",
        author="Omid Memarian, תרגם Gallia Hoz, 2014",
        language="he",
        source="https://he.globalvoices.org/2014/07/19/265/",
        blurb=(
            "Four activists taken in Douma, and the open letter written for them. The title is "
            "what the letter says a dictator would think."
        ),
        words=1108,
        kind=Kind.article,
        register=Register.modern,
        difficulty=16,
        tags=frozenset({Tag.journalism}),
        translations=[
            Rendering(
                name="The English original",
                source="https://globalvoices.org/2014/07/14/syria-isis-kidnapping-douma4/",
                note="The Hebrew is a translation of this, not the other way round.",
                publisher="Global Voices",
                licence="CC-BY",
            )
        ],
    ),
    Entry(
        id="gv-venezuela-selfcensorship",
        title="אנחנו צריכים להיות זהירים אפילו עם מה שאנחנו חושבים",
        author="Marianne Díaz Hernández, תרגם Gal Yadlin, 2015",
        language="he",
        source="https://he.globalvoices.org/2015/02/09/309/",
        blurb=(
            "How self-censorship works once nobody has to be told to do it. Venezuela, reported "
            "from inside."
        ),
        words=972,
        kind=Kind.article,
        register=Register.modern,
        difficulty=17,
        tags=frozenset({Tag.journalism}),
        translations=[
            Rendering(
                name="The English original",
                source="https://advox.globalvoices.org/2015/02/09/we-need-to-be-careful-even-of-what-we-think-self-censorship-in-venezuela/",
                note="The Hebrew is a translation of this, not the other way round.",
                publisher="Global Voices",
                licence="CC-BY",
            )
        ],
    ),
    Entry(
        id="gv-social-censorship",
        title="כל מה שרציתם לדעת על צנזורה ברשתות חברתיות",
        author="Omid Memarian, תרגם Gal Podjarny, 2016",
        language="he",
        source="https://he.globalvoices.org/2016/11/07/463/",
        blurb=(
            "What actually happens when a social network takes a post down, set out in three "
            "languages at once."
        ),
        words=690,
        kind=Kind.article,
        register=Register.modern,
        difficulty=14,
        tags=frozenset({Tag.journalism}),
        translations=[
            Rendering(
                name="The English original",
                source="https://globalvoices.org/2016/11/04/demystifying-social-media-censorship-in-arabic-spanish-and-english/",
                note="The Hebrew is a translation of this, not the other way round.",
                publisher="Global Voices",
                licence="CC-BY",
            )
        ],
    ),
    # --- More Hebrew Wikinews, and the sport shelf ---------------------------------
    #
    # CC BY 4.0. The Euro 2008 match reports are the fastest and most colloquial Hebrew in
    # the catalogue, which is why they get a tag of their own rather than a corner of
    # `journalism`. All bought and none warmed; see the note above.
    Entry(
        id="news-chavez",
        title="נפטר נשיא ונצואלה, הוגו צ׳אבס",
        author="ויקיחדשות, 2013",
        language="he",
        source="https://he.wikinews.org/wiki/נפטר_נשיא_ונצואלה,_הוגו_צ'אבס",
        blurb=(
            "Hugo Chavez dead at fifty-eight after a long illness, reported in Hebrew the day it "
            "happened."
        ),
        words=1330,
        kind=Kind.article,
        register=Register.modern,
        difficulty=16,
        tags=frozenset({Tag.journalism}),
        model=BOUGHT_WITH,
    ),
    Entry(
        id="news-livni",
        title="ציפי לבני תהיה שרת המשפטים",
        author="ויקיחדשות, 2013",
        language="he",
        source="https://he.wikinews.org/wiki/ציפי_לבני_תהיה_שרת_המשפטים",
        blurb=(
            "Tzipi Livni takes the justice ministry, and the sentence shapes of Israeli political "
            "reporting come with it."
        ),
        words=1233,
        kind=Kind.article,
        register=Register.modern,
        difficulty=11,
        tags=frozenset({Tag.journalism}),
        model=BOUGHT_WITH,
    ),
    Entry(
        id="news-election-night",
        title="99% מהקולות נספרו",
        author="ויקיחדשות, 2009",
        language="he",
        source="https://he.wikinews.org/wiki/99%_מהקולות_נספרו_-_קדימה_מובילה_במנדט,_הימין_ב-10",
        blurb=(
            "One seat between the two blocs with the count almost done. Election-night Hebrew: "
            "numbers, verbs, and almost no adjectives."
        ),
        words=934,
        kind=Kind.article,
        register=Register.modern,
        difficulty=19,
        tags=frozenset({Tag.journalism}),
        model=BOUGHT_WITH,
    ),
    Entry(
        id="news-jaffa-conference",
        title="כנס יפו לדיון בבעיות המגזר הערבי",
        author="ויקיחדשות, 2008",
        language="he",
        source="https://he.wikinews.org/wiki/כנס_יפו_התכנס_היום_בפעם_השלישית_לדיון_בבעיות_המגזר_הערבי",
        blurb=(
            "The Jaffa conference meets a third time. Municipal Hebrew, which is what a letter "
            "from the council is written in."
        ),
        words=933,
        kind=Kind.article,
        register=Register.modern,
        difficulty=17,
        tags=frozenset({Tag.journalism}),
        model=BOUGHT_WITH,
    ),
    Entry(
        id="news-kanievsky",
        title="תמה הלוויית הרב חיים קניבסקי",
        author="ויקיחדשות, 2022",
        language="he",
        source="https://he.wikinews.org/wiki/תמה_הלוויית_הרב_חיים_קניבסקי",
        blurb=(
            "The funeral of Rabbi Chaim Kanievsky and the crowd that came to it, written from "
            "inside the world it describes."
        ),
        words=745,
        kind=Kind.article,
        register=Register.modern,
        difficulty=19,
        tags=frozenset({Tag.journalism}),
        model=BOUGHT_WITH,
    ),
    Entry(
        id="sport-villa-sweden",
        title="שער בתוספת הזמן מעניק נצחון לספרד על שבדיה",
        author="ויקיחדשות, 2008",
        language="he",
        source="https://he.wikinews.org/wiki/דויד_וייה_עשה_זאת_שוב:_שער_בתוספת_הזמן_מעניק_נצחון_ראוי_לספרד_על_שבדיה",
        blurb=(
            "David Villa scores in stoppage time and Spain get what they deserved. Match Hebrew at "
            "full speed."
        ),
        words=1653,
        kind=Kind.article,
        register=Register.modern,
        difficulty=20,
        tags=frozenset({Tag.journalism, Tag.sport}),
        model=BOUGHT_WITH,
    ),
    Entry(
        id="sport-arshavin-holland",
        title="רוסיה של ארשאווין הביסה את הולנד 3:1 בהארכה",
        author="ויקיחדשות, 2008",
        language="he",
        source="https://he.wikinews.org/wiki/רוסיה_החדשה_של_ארשאווין_הביסה_את_הולנד_3:1_בהארכה",
        blurb=(
            "Arshavin's Russia beat the Netherlands in extra time, and nobody had expected it, the "
            "reporter least of all."
        ),
        words=1686,
        kind=Kind.article,
        register=Register.modern,
        difficulty=18,
        tags=frozenset({Tag.journalism, Tag.sport}),
        model=BOUGHT_WITH,
    ),
    Entry(
        id="sport-spain-italy",
        title="ספרד בחצי הגמר לראשונה זה עשורים",
        author="ויקיחדשות, 2008",
        language="he",
        source="https://he.wikinews.org/wiki/ספרד_בחצי_הגמר_לראשונה_זה_עשורים_לאחר_דו_קרב_פנדלים_מול_איטליה",
        blurb=("A semi-final for the first time in decades, decided on penalties against Italy."),
        words=1051,
        kind=Kind.article,
        register=Register.modern,
        difficulty=19,
        tags=frozenset({Tag.journalism, Tag.sport}),
        model=BOUGHT_WITH,
    ),
    Entry(
        id="sport-holland-france",
        title="הולנד ברבע הגמר - 4-1 על צרפת",
        author="ויקיחדשות, 2008",
        language="he",
        source="https://he.wikinews.org/wiki/הולנד_ברבע_הגמר_לאחר_נצחון_מרשים_נוסף_-_4-1_על_צרפת",
        blurb=(
            "Four-one against France, the Netherlands through, and the best football of the "
            "tournament so far."
        ),
        words=886,
        kind=Kind.article,
        register=Register.modern,
        difficulty=15,
        tags=frozenset({Tag.journalism, Tag.sport}),
        model=BOUGHT_WITH,
    ),
    Entry(
        id="sport-holland-italy",
        title="הולנד הפתיעה בנצחון מוחץ על אלופת העולם איטליה",
        author="ויקיחדשות, 2008",
        language="he",
        source="https://he.wikinews.org/wiki/הולנד_הפתיעה_בנצחון_מוחץ_על_אלופת_העולם_איטליה",
        blurb=(
            "The Netherlands take the world champions apart. The report is as surprised as the "
            "crowd was."
        ),
        words=674,
        kind=Kind.article,
        register=Register.modern,
        difficulty=21,
        tags=frozenset({Tag.journalism, Tag.sport}),
        model=BOUGHT_WITH,
    ),
    Entry(
        id="sport-israeli-coaches",
        title="סבבי מאמנים בליגת העל בכדורגל",
        author="ויקיחדשות, 2008",
        language="he",
        source="https://he.wikinews.org/wiki/סבבי_מאמנים_בליגת_העל_בכדורגל",
        blurb=(
            "Coaches moving between clubs across the Israeli league in a single week. Local "
            "football Hebrew, names and all."
        ),
        words=701,
        kind=Kind.article,
        register=Register.modern,
        difficulty=14,
        tags=frozenset({Tag.journalism, Tag.sport}),
        model=BOUGHT_WITH,
    ),
    Entry(
        id="sport-euro2008-preview",
        title="יורו 2008 בקו הזינוק",
        author="ויקיחדשות, 2008",
        language="he",
        source="https://he.wikinews.org/wiki/הנבחרות_מוכנות,_האצטדיונים_מוכנים,_האוהדים_מוכנים_-_יורו_2008_בקו_הזינוק",
        blurb=(
            "The teams are ready, the stadiums are ready, the fans are ready. Written the day "
            "before it began."
        ),
        words=738,
        kind=Kind.article,
        register=Register.modern,
        difficulty=17,
        tags=frozenset({Tag.journalism, Tag.sport}),
        model=BOUGHT_WITH,
    ),
    # --- More short fiction from Ben Yehuda ----------------------------------------
    #
    # Berdyczewski wrote hundreds of these and Gnessin a smaller, harder set. Gnessin is
    # the most difficult Hebrew in the catalogue and the measured numbers say so, which is
    # the point of measuring rather than judging. Bought and not warmed.
    Entry(
        id="mjb-hashmua",
        title="השמועה",
        author="מיכה יוסף ברדיצ׳בסקי",
        language="he",
        source="https://benyehuda.org/download/503.txt",
        blurb=(
            "A rumour reaches the house of study a quarter of an hour before the lesson ends, and "
            "the lesson does not survive it."
        ),
        words=1949,
        kind=Kind.story,
        register=Register.modern,
        difficulty=17,
        model=BOUGHT_WITH,
    ),
    Entry(
        id="mjb-hazar",
        title="הזר",
        author="מיכה יוסף ברדיצ׳בסקי",
        language="he",
        source="https://benyehuda.org/download/6994.txt",
        blurb=(
            "A Hebrew reading room in a large German city where Hebrew readers are few. The "
            "stranger who walks in is the story."
        ),
        words=3003,
        kind=Kind.story,
        register=Register.modern,
        difficulty=18,
        model=BOUGHT_WITH,
    ),
    Entry(
        id="mjb-kinat-ahim",
        title="קנאת אחים",
        author="מיכה יוסף ברדיצ׳בסקי",
        language="he",
        source="https://benyehuda.org/download/6662.txt",
        blurb=(
            "Two brothers and the envy that never needed a reason. Berdyczewski's usual subject at "
            "his usual temperature."
        ),
        words=2986,
        kind=Kind.story,
        register=Register.modern,
        difficulty=16,
        model=BOUGHT_WITH,
    ),
    Entry(
        id="mjb-ashir-veani",
        title="עשיר ועני",
        author="מיכה יוסף ברדיצ׳בסקי",
        language="he",
        source="https://benyehuda.org/download/5765.txt",
        blurb=(
            "A lecture hall, an old professor, and two students who stop being equals the moment "
            "they leave it."
        ),
        words=1044,
        kind=Kind.story,
        register=Register.modern,
        difficulty=18,
        model=BOUGHT_WITH,
    ),
    Entry(
        id="mjb-bead-hahalon",
        title="בעד החלון",
        author="מיכה יוסף ברדיצ׳בסקי",
        language="he",
        source="https://benyehuda.org/download/7322.txt",
        blurb=(
            "He left a wife and two sons and went abroad to finish his studies. What happens to "
            "the window he looked out of is the rest."
        ),
        words=2346,
        kind=Kind.story,
        register=Register.modern,
        difficulty=19,
        model=BOUGHT_WITH,
    ),
    Entry(
        id="mjb-hasovev",
        title="הסובב",
        author="מיכה יוסף ברדיצ׳בסקי",
        language="he",
        source="https://benyehuda.org/download/5628.txt",
        blurb=(
            "Menachem-Ezra was not handsome, but he was polite and careful about his clothes. That "
            "is all of him, and it is enough."
        ),
        words=2534,
        kind=Kind.story,
        register=Register.modern,
        difficulty=17,
        model=BOUGHT_WITH,
    ),
    Entry(
        id="gnessin-shmuel",
        title="שמואל בן שמואל",
        author="אורי ניסן גנסין",
        language="he",
        source="https://benyehuda.org/download/3909.txt",
        blurb=(
            "Shmuel son of Shmuel opens his eyes, and Gnessin follows the thought rather than the "
            "day."
        ),
        words=3529,
        kind=Kind.story,
        register=Register.modern,
        difficulty=26,
        model=BOUGHT_WITH,
    ),
    Entry(
        id="gnessin-ktata",
        title="קטטה",
        author="אורי ניסן גנסין",
        language="he",
        source="https://benyehuda.org/download/669.txt",
        blurb=(
            "A brawl among the flour wagons. Gnessin writing something with an outside to it, "
            "which is rare."
        ),
        words=3509,
        kind=Kind.story,
        register=Register.modern,
        difficulty=31,
        model=BOUGHT_WITH,
    ),
    Entry(
        id="gnessin-baganim",
        title="בגנים",
        author="אורי ניסן גנסין",
        language="he",
        source="https://benyehuda.org/download/1513.txt",
        blurb=("A white cloud crosses the morning sun, and the whole story happens underneath it."),
        words=3115,
        kind=Kind.story,
        register=Register.modern,
        difficulty=26,
        model=BOUGHT_WITH,
    ),
    Entry(
        id="gnessin-seuda",
        title="סעודה מפסקת",
        author="אורי ניסן גנסין",
        language="he",
        source="https://benyehuda.org/download/6341.txt",
        blurb=(
            "The last meal before the fast, one room, one evening. The shortest way into Gnessin "
            "there is."
        ),
        words=2054,
        kind=Kind.story,
        register=Register.modern,
        difficulty=30,
        model=BOUGHT_WITH,
    ),
    Entry(
        id="gnessin-jenia",
        title="ג׳ניה",
        author="אורי ניסן גנסין",
        language="he",
        source="https://benyehuda.org/download/2900.txt",
        blurb=(
            "From the notes of a public man in the provinces. Long, interior, and the Hebrew of "
            "somebody inventing a modern prose as he goes."
        ),
        words=8972,
        kind=Kind.story,
        register=Register.modern,
        difficulty=20,
        model=BOUGHT_WITH,
    ),
    Entry(
        id="gnessin-beinotayim",
        title="בינותיים",
        author="אורי ניסן גנסין",
        language="he",
        source="https://benyehuda.org/download/1394.txt",
        blurb=(
            "At first there was a different wind about the place. Gnessin at full length, which is "
            "hard and worth it."
        ),
        words=8233,
        kind=Kind.story,
        register=Register.modern,
        difficulty=29,
        model=BOUGHT_WITH,
    ),
    # --- Screened, not hand-picked --------------------------------------------------
    #
    # Thirty-six short stories from Ben Yehuda's public-domain authors, found by
    # `scripts/screen_candidates.py` over 315 candidates: 183 were the wrong length, 59
    # measured harder than 20, 22 would not fetch, and none failed the language rule —
    # Ben Yehuda is Hebrew all the way down, which is what made Global Voices the anomaly
    # rather than the norm.
    #
    # The screen decides fitness and a person still decides worth. Fifteen survivors were
    # dropped by hand after it ran: ten Shestov essays translated by Gnessin, and five of
    # Berdyczewski's aphorism collections. Both are legally clean and both are abstract,
    # and difficulty flatters them because it counts words rather than what is being done
    # with them — the limitation `measure_difficulty.py` states about itself.
    #
    # Bought and not warmed, like the rest of the modern shelf.
    Entry(
        id="mjb-zo-betzad-zo",
        title="זו בצד זו",
        author="מיכה יוסף ברדיצ׳בסקי",
        language="he",
        source="https://benyehuda.org/download/2193.txt",
        blurb=(
            "He loved Leah a little, for her red hair and because she knew Hebrew. He was fond of "
            "her younger sister too, and that is the trouble."
        ),
        words=1157,
        kind=Kind.story,
        register=Register.modern,
        difficulty=13,
        model=BOUGHT_WITH,
    ),
    Entry(
        id="mjb-shtei-shanim",
        title="שתי שנים ומחצה",
        author="מיכה יוסף ברדיצ׳בסקי",
        language="he",
        source="https://benyehuda.org/download/4029.txt",
        blurb=(
            "He met her husband on a student bench in Leipzig. Some years pass, the studies end, "
            "and nothing else does."
        ),
        words=1933,
        kind=Kind.story,
        register=Register.modern,
        difficulty=13,
        model=BOUGHT_WITH,
    ),
    Entry(
        id="mjb-egalat-habarzel",
        title="בעגלת הברזל",
        author="מיכה יוסף ברדיצ׳בסקי",
        language="he",
        source="https://benyehuda.org/download/2066.txt",
        blurb=(
            "Third class, between two cities, on a wet evening. Jews sitting side by side and "
            "talking, which is the whole of it."
        ),
        words=1052,
        kind=Kind.story,
        register=Register.modern,
        difficulty=14,
        model=BOUGHT_WITH,
    ),
    Entry(
        id="mjb-yehonatan",
        title="יהונתן",
        author="מיכה יוסף ברדיצ׳בסקי",
        language="he",
        source="https://benyehuda.org/download/3711.txt",
        blurb=(
            "Yonatan the Clever, so called by friends who meant the opposite. Enrolled at the "
            "university for years without attending a lecture."
        ),
        words=1267,
        kind=Kind.story,
        register=Register.modern,
        difficulty=15,
        model=BOUGHT_WITH,
    ),
    Entry(
        id="mjb-hamevohal",
        title="המבוהל",
        author="מיכה יוסף ברדיצ׳בסקי",
        language="he",
        source="https://benyehuda.org/download/6470.txt",
        blurb=(
            "Alarmed was his character and there is no other word for him. Tall, thin, red hair "
            "down over his eyes, and nothing to do but talk."
        ),
        words=1325,
        kind=Kind.story,
        register=Register.modern,
        difficulty=15,
        model=BOUGHT_WITH,
    ),
    Entry(
        id="mjb-pesach",
        title="פסח",
        author="מיכה יוסף ברדיצ׳בסקי",
        language="he",
        source="https://benyehuda.org/download/1314.txt",
        blurb=(
            "A small shop selling pots, thread, pens, ink and incense, and the man who stands in "
            "it from morning until night waiting for a customer."
        ),
        words=648,
        kind=Kind.story,
        register=Register.modern,
        difficulty=16,
        model=BOUGHT_WITH,
    ),
    Entry(
        id="mjb-arbaat-haahim",
        title="ארבעת האחים",
        author="מיכה יוסף ברדיצ׳בסקי",
        language="he",
        source="https://benyehuda.org/download/5887.txt",
        blurb=(
            "A father who sits in his room like a man already dead, a midwife mother who is rarely "
            "home, and the four sons that leaves."
        ),
        words=767,
        kind=Kind.story,
        register=Register.modern,
        difficulty=16,
        model=BOUGHT_WITH,
    ),
    Entry(
        id="mjb-ben-pesha",
        title="בן־פשע",
        author="מיכה יוסף ברדיצ׳בסקי",
        language="he",
        source="https://benyehuda.org/download/4897.txt",
        blurb=(
            "Arkady Drebitz-Yablonsky. Two surnames, which were the making of him and then the "
            "undoing."
        ),
        words=1417,
        kind=Kind.story,
        register=Register.modern,
        difficulty=16,
        model=BOUGHT_WITH,
    ),
    Entry(
        id="mjb-bebeten-imam",
        title="בבטן אמם",
        author="מיכה יוסף ברדיצ׳בסקי",
        language="he",
        source="https://benyehuda.org/download/611.txt",
        blurb=(
            "Two young Hasidim, not the studious kind, who spend months at a time at the rebbe's "
            "court. The days I am describing are not our days."
        ),
        words=1379,
        kind=Kind.story,
        register=Register.modern,
        difficulty=17,
        model=BOUGHT_WITH,
    ),
    Entry(
        id="mjb-hamenushak",
        title="המנושק",
        author="מיכה יוסף ברדיצ׳בסקי",
        language="he",
        source="https://benyehuda.org/download/2756.txt",
        blurb=(
            "A Galician who married into a town on the border between the dark country and "
            "enlightened Germany."
        ),
        words=1724,
        kind=Kind.story,
        register=Register.modern,
        difficulty=17,
        model=BOUGHT_WITH,
    ),
    Entry(
        id="mjb-anshei-hasadeh",
        title="אנשי השדה",
        author="מיכה יוסף ברדיצ׳בסקי",
        language="he",
        source="https://benyehuda.org/download/7123.txt",
        blurb=(
            "Among Jews a man's name rarely fits him. Three brothers all called Field will teach "
            "you that much."
        ),
        words=617,
        kind=Kind.story,
        register=Register.modern,
        difficulty=18,
        model=BOUGHT_WITH,
    ),
    Entry(
        id="mjb-hayeshenim",
        title="הישנים והערים",
        author="מיכה יוסף ברדיצ׳בסקי",
        language="he",
        source="https://benyehuda.org/download/6799.txt",
        blurb=(
            "Elsewhere youth is a preparation for earning a living. Here it is the reverse, and "
            "the town does not notice."
        ),
        words=1791,
        kind=Kind.story,
        register=Register.modern,
        difficulty=18,
        model=BOUGHT_WITH,
    ),
    Entry(
        id="mjb-hanistar",
        title="הנסתר",
        author="מיכה יוסף ברדיצ׳בסקי",
        language="he",
        source="https://benyehuda.org/download/4220.txt",
        blurb=(
            "A simple thing happened in Kitov: the old beadle's eldest son died. Half the place is "
            "a town and half of it is a village."
        ),
        words=1818,
        kind=Kind.story,
        register=Register.modern,
        difficulty=18,
        model=BOUGHT_WITH,
    ),
    Entry(
        id="mjb-baal-hasipur",
        title="בעל הסיפור",
        author="מיכה יוסף ברדיצ׳בסקי",
        language="he",
        source="https://benyehuda.org/download/3141.txt",
        blurb=(
            "Married, a daughter in the cradle, and he leaves his small Lithuanian town for Vilna "
            "to see to his future. He has a great many thoughts."
        ),
        words=2036,
        kind=Kind.story,
        register=Register.modern,
        difficulty=18,
        model=BOUGHT_WITH,
    ),
    Entry(
        id="mjb-hashnayim",
        title="השניים",
        author="מיכה יוסף ברדיצ׳בסקי",
        language="he",
        source="https://benyehuda.org/download/6018.txt",
        blurb=(
            "Three women among the Russian and Polish students in the capital's suburb, always "
            "seen walking together, and not alike in the least."
        ),
        words=2281,
        kind=Kind.story,
        register=Register.modern,
        difficulty=18,
        model=BOUGHT_WITH,
    ),
    Entry(
        id="mjb-hatzli",
        title="הצלי בהיכל",
        author="מיכה יוסף ברדיצ׳בסקי",
        language="he",
        source="https://benyehuda.org/download/7580.txt",
        blurb=(
            "I did not see this myself, I heard it from a reliable man. If it turns out not to be "
            "true, the invention is not mine."
        ),
        words=870,
        kind=Kind.story,
        register=Register.modern,
        difficulty=19,
        model=BOUGHT_WITH,
    ),
    Entry(
        id="mjb-hamehalchim",
        title="המהלכים והעומדים",
        author="מיכה יוסף ברדיצ׳בסקי",
        language="he",
        source="https://benyehuda.org/download/5374.txt",
        blurb=(
            "The town is called Plain and is nothing of the kind. You climb and descend, climb and "
            "descend, until you reach the old streets by the stream."
        ),
        words=1093,
        kind=Kind.story,
        register=Register.modern,
        difficulty=19,
        model=BOUGHT_WITH,
    ),
    Entry(
        id="mjb-meigra-rama",
        title="מאיגרא רמה",
        author="מיכה יוסף ברדיצ׳בסקי",
        language="he",
        source="https://benyehuda.org/download/5755.txt",
        blurb=(
            "The door opened and a student I had never met jumped in and began arguing with me "
            "about the Jews, Zionism, Herzl and Lassalle."
        ),
        words=2000,
        kind=Kind.story,
        register=Register.modern,
        difficulty=19,
        model=BOUGHT_WITH,
    ),
    Entry(
        id="mjb-din-torah",
        title="דין תורה",
        author="מיכה יוסף ברדיצ׳בסקי",
        language="he",
        source="https://benyehuda.org/download/5373.txt",
        blurb=(
            "A scandal in Radia: the rich man struck Ephraim-Reuven in the synagogue, in front of "
            "the whole congregation. Right hand, left cheek."
        ),
        words=937,
        kind=Kind.story,
        register=Register.modern,
        difficulty=20,
        model=BOUGHT_WITH,
    ),
    Entry(
        id="mjb-shnei-yosef",
        title="שני יוסף",
        author="מיכה יוסף ברדיצ׳בסקי",
        language="he",
        source="https://benyehuda.org/download/8612.txt",
        blurb=(
            "Another notable deserves his monument: Gedalyahu of the post office, who answers to "
            "nobody."
        ),
        words=1082,
        kind=Kind.story,
        register=Register.modern,
        difficulty=20,
        model=BOUGHT_WITH,
    ),
    Entry(
        id="brenner-asonot",
        title="אסונות",
        author="יוסף חיים ברנר",
        language="he",
        source="https://benyehuda.org/download/408.txt",
        blurb=(
            "In a cart on the road she falls into conversation. One of the Jaffa expellees? No, "
            "she has never been to Jaffa. She has heard of it."
        ),
        words=693,
        kind=Kind.story,
        register=Register.modern,
        difficulty=14,
        model=BOUGHT_WITH,
    ),
    Entry(
        id="brenner-nkhe-ruach",
        title="נכא רוח",
        author="יוסף חיים ברנר",
        language="he",
        source="https://benyehuda.org/download/725.txt",
        blurb=(
            "Back from the Congress, and his prophecy has come true. A pessimist's prophecy always "
            "does, which is not the comfort he wants it to be."
        ),
        words=828,
        kind=Kind.story,
        register=Register.modern,
        difficulty=17,
        model=BOUGHT_WITH,
    ),
    Entry(
        id="brenner-gazlanim",
        title="גזלנים",
        author="יוסף חיים ברנר",
        language="he",
        source="https://benyehuda.org/download/494.txt",
        blurb=(
            "He kept a grocery in Jaffa. After the expulsion he bought a bald donkey and a two- "
            "wheeled cart and started moving other people's belongings."
        ),
        words=830,
        kind=Kind.story,
        register=Register.modern,
        difficulty=18,
        model=BOUGHT_WITH,
    ),
    Entry(
        id="brenner-tzavaa",
        title="צוואה",
        author="יוסף חיים ברנר",
        language="he",
        source="https://benyehuda.org/download/496.txt",
        blurb=(
            "The librarian is exact and devout about his duties. Then a boy of fifteen begins "
            "coming twice a week, and he is a little strange."
        ),
        words=1007,
        kind=Kind.story,
        register=Register.modern,
        difficulty=18,
        model=BOUGHT_WITH,
    ),
    Entry(
        id="brenner-hu-siper",
        title="הוא סיפר לעצמו",
        author="יוסף חיים ברנר",
        language="he",
        source="https://benyehuda.org/download/799.txt",
        blurb=(
            "Half a year since the news reached him, and four days more since the thing itself. "
            "Twenty-five weeks turning inside a frozen riddle."
        ),
        words=2024,
        kind=Kind.story,
        register=Register.modern,
        difficulty=18,
        model=BOUGHT_WITH,
    ),
    Entry(
        id="brenner-tarumet",
        title="תרעומת",
        author="יוסף חיים ברנר",
        language="he",
        source="https://benyehuda.org/download/747.txt",
        blurb=(
            "A new journal begins and every writer in the provinces descends on its office, some "
            "to be paid and some to find a reason to go on."
        ),
        words=605,
        kind=Kind.story,
        register=Register.modern,
        difficulty=19,
        model=BOUGHT_WITH,
    ),
    Entry(
        id="brenner-hidushim",
        title="חידושים",
        author="יוסף חיים ברנר",
        language="he",
        source="https://benyehuda.org/download/559.txt",
        blurb=(
            "You are impressed by missionaries overseas who dress and talk like Jews? You need not "
            "travel that far."
        ),
        words=1237,
        kind=Kind.story,
        register=Register.modern,
        difficulty=19,
        model=BOUGHT_WITH,
    ),
    Entry(
        id="brenner-beino-leveino",
        title="בינו לבינו",
        author="יוסף חיים ברנר",
        language="he",
        source="https://benyehuda.org/download/388.txt",
        blurb=(
            "He lost a job that paid ten shillings a week for twelve-hour days, and did not look "
            "for another. He said to himself: on the contrary."
        ),
        words=1937,
        kind=Kind.story,
        register=Register.modern,
        difficulty=19,
        model=BOUGHT_WITH,
    ),
    Entry(
        id="ysteinberg-hetz-teshua",
        title="חץ תשועה",
        author="יהודה שטיינברג",
        language="he",
        source="https://benyehuda.org/download/53496.txt",
        blurb=(
            "In the days of the Hasmonean wars, a village smith with one son of eleven and a "
            "daughter two years younger. Fully pointed."
        ),
        words=1620,
        kind=Kind.story,
        register=Register.modern,
        difficulty=18,
        model=BOUGHT_WITH,
    ),
    Entry(
        id="ysteinberg-kshatot",
        title="קשתות ל״ג בעומר",
        author="יהודה שטיינברג",
        language="he",
        source="https://benyehuda.org/download/53389.txt",
        blurb=(
            "Rabbi Shimon bar Yochai and Rabbi Yehuda were true friends who agreed about almost "
            "nothing. They were unalike as children already."
        ),
        words=1953,
        kind=Kind.story,
        register=Register.modern,
        difficulty=19,
        model=BOUGHT_WITH,
    ),
    Entry(
        id="ysteinberg-afar-hakodesh",
        title="עפר הקודש",
        author="יהודה שטיינברג",
        language="he",
        source="https://benyehuda.org/download/44610.txt",
        blurb=(
            "Benayahu saw no silver in his parents' house, no watch on a chain, no earrings. So he "
            "never saw a lock or a key there either."
        ),
        words=2579,
        kind=Kind.story,
        register=Register.modern,
        difficulty=19,
        model=BOUGHT_WITH,
    ),
    Entry(
        id="ysteinberg-nes-hanuka",
        title="נס חנוכה",
        author="יהודה שטיינברג",
        language="he",
        source="https://benyehuda.org/download/53497.txt",
        blurb=(
            "On the first night the children stand packed together waiting for their father to "
            "finish the blessings and hand out the Hanukkah money."
        ),
        words=2925,
        kind=Kind.story,
        register=Register.modern,
        difficulty=19,
        model=BOUGHT_WITH,
    ),
    Entry(
        id="ysteinberg-askan",
        title="עסקן במצוות",
        author="יהודה שטיינברג",
        language="he",
        source="https://benyehuda.org/download/53399.txt",
        blurb=(
            "Shmuelon came home from the reading of the Megillah insulted: no pastries, nothing. "
            "And he had fasted the day before like a grown man."
        ),
        words=1137,
        kind=Kind.story,
        register=Register.modern,
        difficulty=20,
        model=BOUGHT_WITH,
    ),
    Entry(
        id="jsteinberg-hanshika",
        title="הנשיקה",
        author="יעקב שטיינברג",
        language="he",
        source="https://benyehuda.org/download/22934.txt",
        blurb=(
            "Yosef was not yet two when both his parents died, and the neighbours who buried his "
            "mother began discussing what should be done with him."
        ),
        words=1400,
        kind=Kind.story,
        register=Register.modern,
        difficulty=16,
        model=BOUGHT_WITH,
    ),
    Entry(
        id="frishman-kriat-hatorah",
        title="קריאת התורה",
        author="דוד פרישמן",
        language="he",
        source="https://benyehuda.org/download/10890.txt",
        blurb=(
            "An abandoned city. Facing the stream stands the synagogue, and in its ark seven "
            "scrolls. Pointed, and nearer a poem than a story."
        ),
        words=704,
        kind=Kind.story,
        register=Register.modern,
        difficulty=18,
        model=BOUGHT_WITH,
    ),
    Entry(
        id="gnessin-nietzsche",
        title="אחרי מותו של ניטשה",
        author="אורי ניסן גנסין",
        language="he",
        source="https://benyehuda.org/download/3713.txt",
        blurb=(
            "Weimar, the twenty-fifth of August 1900, a quarter to twelve in the morning. Gnessin "
            "on a death that was days old when he wrote."
        ),
        words=614,
        kind=Kind.essay,
        register=Register.modern,
        difficulty=18,
        model=BOUGHT_WITH,
    ),
    # --- Screened Wikinews: basketball, an election, a collider ---------------------
    #
    # Twenty of 126 candidates, through the same screen. Five mechanically-sound
    # survivors were dropped by hand: a self-promoting piece about a teenager's vlog, and
    # four items on attacks and military operations — a learner's shelf that opens with
    # those is making a claim about the country rather than about the Hebrew.
    Entry(
        id="sport-holon-basketball",
        title="הפועל חולון אלופת המדינה בכדורסל",
        author="ויקיחדשות, 2008",
        language="he",
        source="https://he.wikinews.org/wiki/הפועל_חולון_היא_אלופת_המדינה_בכדורסל",
        blurb=(
            "Hapoel Holon take the Israeli basketball title. The easiest text in the catalogue, "
            "and the fastest."
        ),
        words=608,
        kind=Kind.article,
        register=Register.modern,
        difficulty=13,
        tags=frozenset({Tag.journalism, Tag.sport}),
        model=BOUGHT_WITH,
    ),
    Entry(
        id="news-italy-election",
        title="הבחירות באיטליה",
        author="ויקיחדשות, 2013",
        language="he",
        source="https://he.wikinews.org/wiki/הבחירות_באיטליה:_פער_זעום_בין_קואליציית_המרכז-שמאל_של_ברסני_לקואליציית_הימין_של_ברלוסקוני",
        blurb=(
            "A hair's breadth between Bersani's centre-left and Berlusconi's right. Foreign "
            "politics in Hebrew is its own register."
        ),
        words=682,
        kind=Kind.article,
        register=Register.modern,
        difficulty=13,
        tags=frozenset({Tag.journalism}),
        model=BOUGHT_WITH,
    ),
    Entry(
        id="news-knesset-19",
        title="הושבעו חברי הכנסת ה־19",
        author="ויקיחדשות, 2013",
        language="he",
        source="https://he.wikinews.org/wiki/הושבעו_חברי_הכנסת_ה-19",
        blurb=(
            "The nineteenth Knesset is sworn in and a hundred and twenty people declare allegiance "
            "one after another."
        ),
        words=840,
        kind=Kind.article,
        register=Register.modern,
        difficulty=13,
        tags=frozenset({Tag.journalism}),
        model=BOUGHT_WITH,
    ),
    Entry(
        id="news-winograd",
        title="אחרי וינוגרד: ביקורת על אולמרט",
        author="ויקיחדשות, 2008",
        language="he",
        source="https://he.wikinews.org/wiki/אחרי_וינוגרד:_ביקורת_מפנים_ומחוץ_על_אולמרט",
        blurb=(
            "The day after the Winograd report, criticism of Olmert arrives from inside his "
            "government and outside it. It was expected."
        ),
        words=641,
        kind=Kind.article,
        register=Register.modern,
        difficulty=14,
        tags=frozenset({Tag.journalism}),
        model=BOUGHT_WITH,
    ),
    Entry(
        id="news-bagatz-mazuz",
        title="בג״ץ בצו ביניים למזוז",
        author="ויקיחדשות, 2007",
        language="he",
        source='https://he.wikinews.org/wiki/בג"ץ_בצו_ביניים_למזוז:_מדוע_לא_לבטל_עסקת_הטיעון',
        blurb=(
            "The High Court asks the attorney general why the plea bargain should not be struck "
            "down. Legal Hebrew at its shortest."
        ),
        words=628,
        kind=Kind.article,
        register=Register.modern,
        difficulty=15,
        tags=frozenset({Tag.journalism}),
        model=BOUGHT_WITH,
    ),
    Entry(
        id="sport-beitar-arson",
        title="הוצתו משרדי בית״ר ירושלים",
        author="ויקיחדשות, 2013",
        language="he",
        source='https://he.wikinews.org/wiki/הוצתו_משרדי_בית"ר_ירושלים',
        blurb=(
            "Beitar Jerusalem's offices burn after the club signs two Muslim players and a part of "
            "its own support turns on it."
        ),
        words=674,
        kind=Kind.article,
        register=Register.modern,
        difficulty=16,
        tags=frozenset({Tag.journalism, Tag.sport}),
        model=BOUGHT_WITH,
    ),
    Entry(
        id="sport-maccabi-siena",
        title="פיינל פור: מכבי בדרך לגמר",
        author="ויקיחדשות, 2008",
        language="he",
        source="https://he.wikinews.org/wiki/פיינל_פור:_מכבי_התגברה_על_פיגור_מוקדם_וניצחה_את_סיינה_בדרך_לגמר",
        blurb=(
            "Maccabi Tel Aviv come back from an early deficit against Siena and reach the final. "
            "Basketball moves faster than football, in Hebrew too."
        ),
        words=755,
        kind=Kind.article,
        register=Register.modern,
        difficulty=16,
        tags=frozenset({Tag.journalism, Tag.sport}),
        model=BOUGHT_WITH,
    ),
    Entry(
        id="sport-russia-sweden",
        title="רוסיה היממה את שבדיה",
        author="ויקיחדשות, 2008",
        language="he",
        source="https://he.wikinews.org/wiki/רוסיה_היממה_את_שבדיה_עם_2:0_ועלתה_לרבע_הגמר",
        blurb=(
            "Russia are not exactly lions, says the report, and then they beat Sweden two-nil and "
            "go through."
        ),
        words=923,
        kind=Kind.article,
        register=Register.modern,
        difficulty=16,
        tags=frozenset({Tag.journalism, Tag.sport}),
        model=BOUGHT_WITH,
    ),
    Entry(
        id="sport-germany-croatia",
        title="גרמניה נתקלה במשוכה גבוהה מדי",
        author="ויקיחדשות, 2008",
        language="he",
        source="https://he.wikinews.org/wiki/גרמניה_נתקלה_במשוכה_גבוהה_מדי_בדרך_לרבע_הגמר:_2-1_לקרואטיה",
        blurb=(
            "Croatia put a hurdle in front of Germany that turns out to be too high, on the way to "
            "the quarter-finals."
        ),
        words=658,
        kind=Kind.article,
        register=Register.modern,
        difficulty=17,
        tags=frozenset({Tag.journalism, Tag.sport}),
        model=BOUGHT_WITH,
    ),
    Entry(
        id="news-big-bang",
        title="שחזור של המפץ הגדול",
        author="ויקיחדשות, 2008",
        language="he",
        source="https://he.wikinews.org/wiki/שחזור_של_המפץ_הגדול_ייערך_בתוך_שבועות",
        blurb=(
            "Could the first time travellers be real? The collider is weeks from switching on, "
            "written in Hebrew for people who are not physicists."
        ),
        words=705,
        kind=Kind.article,
        register=Register.modern,
        difficulty=17,
        tags=frozenset({Tag.journalism}),
        model=BOUGHT_WITH,
    ),
    Entry(
        id="sport-romania-france",
        title="הקורבן הראשון של בית המוות",
        author="ויקיחדשות, 2008",
        language="he",
        source='https://he.wikinews.org/wiki/הקורבן_הראשון_של_"בית_המוות":_הקהל;_שעמום_בתיקו_מאופס_בין_רומניה_לצרפת',
        blurb=(
            "The group of death claims its first victim: the crowd. A goalless draw between "
            "Romania and France, by somebody who sat through it."
        ),
        words=603,
        kind=Kind.article,
        register=Register.modern,
        difficulty=18,
        tags=frozenset({Tag.journalism, Tag.sport}),
        model=BOUGHT_WITH,
    ),
    Entry(
        id="sport-ronaldo-czech",
        title="רונאלדו: ההבטחה שמומשה",
        author="ויקיחדשות, 2008",
        language="he",
        source="https://he.wikinews.org/wiki/כריסטיאנו_רונאלדו_מציג:_ההבטחה_שמומשה;_פורטוגל_ניצחה_3-1_את_צ'כיה",
        blurb=(
            "Cristiano Ronaldo makes good on the promise and Portugal beat the Czechs three-one."
        ),
        words=633,
        kind=Kind.article,
        register=Register.modern,
        difficulty=18,
        tags=frozenset({Tag.journalism, Tag.sport}),
        model=BOUGHT_WITH,
    ),
    Entry(
        id="sport-spain-russia",
        title="ספרד הדהימה את רוסיה",
        author="ויקיחדשות, 2008",
        language="he",
        source="https://he.wikinews.org/wiki/ספרד_הדהימה_את_רוסיה:_4-1_במשחק_הראשון_בבית_ד'",
        blurb=(
            "Euro 2008 brings out the best in Spain, and Russia are on the receiving end of it, "
            "four-one."
        ),
        words=783,
        kind=Kind.article,
        register=Register.modern,
        difficulty=18,
        tags=frozenset({Tag.journalism, Tag.sport}),
        model=BOUGHT_WITH,
    ),
    Entry(
        id="sport-turkey-germany",
        title="חצי הגמר הראשון: טורקיה־גרמניה",
        author="ויקיחדשות, 2008",
        language="he",
        source="https://he.wikinews.org/wiki/חצי_הגמר_הראשון:_לא_כל_יום_עסל_-_טורקיה_הפסידה_2-3_לגרמניה",
        blurb=(
            "Fourteen available players and Turkey still go out three-two. The headline borrows "
            "the Arabic word for honey, as Hebrew does."
        ),
        words=900,
        kind=Kind.article,
        register=Register.modern,
        difficulty=18,
        tags=frozenset({Tag.journalism, Tag.sport}),
        model=BOUGHT_WITH,
    ),
    Entry(
        id="sport-swiss-portugal",
        title="שווייץ הצילה כבודה",
        author="ויקיחדשות, 2008",
        language="he",
        source="https://he.wikinews.org/wiki/שווייץ_הצילה_כבודה_מול_פורטוגל_ב'_-_2:0_ונצחון_פרידה_למארחת",
        blurb=(
            "Switzerland save their dignity against a second-string Portugal, and the hosts go "
            "home with a win at least."
        ),
        words=628,
        kind=Kind.article,
        register=Register.modern,
        difficulty=19,
        tags=frozenset({Tag.journalism, Tag.sport}),
        model=BOUGHT_WITH,
    ),
    Entry(
        id="sport-croatia-poland",
        title="קרואטיה לא ריחמה על פולין",
        author="ויקיחדשות, 2008",
        language="he",
        source="https://he.wikinews.org/wiki/קרואטיה_לא_ריחמה_על_פולין_-_1:0_ופולין_תחכה_ליורו_2012",
        blurb=("Croatia show Poland no mercy, and Poland settle down to wait for 2012."),
        words=643,
        kind=Kind.article,
        register=Register.modern,
        difficulty=19,
        tags=frozenset({Tag.journalism, Tag.sport}),
        model=BOUGHT_WITH,
    ),
    Entry(
        id="sport-greece-russia",
        title="היוונים חיכו לשווא",
        author="ויקיחדשות, 2008",
        language="he",
        source="https://he.wikinews.org/wiki/היוונים_חיכו_לשווא_לפרצה_בהגנה_הרוסית:_1-0_לרוסיה_ויוון_היא_האלופה_היוצאת",
        blurb=("Greece wait in vain for a gap in the Russian defence, and the holders go out."),
        words=794,
        kind=Kind.article,
        register=Register.modern,
        difficulty=19,
        tags=frozenset({Tag.journalism, Tag.sport}),
        model=BOUGHT_WITH,
    ),
    Entry(
        id="sport-croatia-turkey",
        title="מי שלא כובש - סופג",
        author="ויקיחדשות, 2008",
        language="he",
        source="https://he.wikinews.org/wiki/מי_שלא_כובש_-_סופג;_קרואטיה_לא_ניצלה_הזדמנויות_ונכנעה_3:1_בפנדלים_לטורקיה",
        blurb=(
            "Miss enough chances and you concede. Croatia go out to Turkey on penalties, which the "
            "headline saw coming."
        ),
        words=1094,
        kind=Kind.article,
        register=Register.modern,
        difficulty=19,
        tags=frozenset({Tag.journalism, Tag.sport}),
        model=BOUGHT_WITH,
    ),
    Entry(
        id="sport-romania-italy",
        title="תיקו מותח בין רומניה ואיטליה",
        author="ויקיחדשות, 2008",
        language="he",
        source="https://he.wikinews.org/wiki/תיקו_1-1_מותח_ורב_הפתעות_בין_רומניה_ואיטליה",
        blurb=(
            "Four days on and back to Group C, for a one-all draw with more surprises in it than "
            "the score admits."
        ),
        words=908,
        kind=Kind.article,
        register=Register.modern,
        difficulty=20,
        tags=frozenset({Tag.journalism, Tag.sport}),
        model=BOUGHT_WITH,
    ),
    Entry(
        id="sport-germany-austria",
        title="גרמניה ברבע הגמר",
        author="ויקיחדשות, 2008",
        language="he",
        source="https://he.wikinews.org/wiki/גרמניה_ברבע_הגמר_עם_1:0_על_אוסטריה,_שלא_יכלה_להגנה_הגרמנית",
        blurb=("Germany give Austria nothing at all and go through one-nil."),
        words=1021,
        kind=Kind.article,
        register=Register.modern,
        difficulty=20,
        tags=frozenset({Tag.journalism, Tag.sport}),
        model=BOUGHT_WITH,
    ),
    # --- The Steinbergs, and why the author list was reweighted ---------------------
    #
    # A second screen of 408 candidates, aimed away from Berdyczewski and Brenner, who
    # already had thirty entries between them and one mood between them. 152 survived.
    #
    # The weighting worked on length and failed on kind: Frishman came back 117 strong and
    # almost all of it is literary criticism — a numbered serial of letters about
    # literature, and obituaries of other writers. Abstract, and flattered by a difficulty
    # that counts words. None of it was taken. What the screen found instead was Yehuda
    # Steinberg, who wrote hundreds of short Hasidic tales with people in them, which is
    # the most learner-shaped writing anywhere in the public domain.
    Entry(
        id="ysteinberg-klapei-lia",
        title="כלפי ליא",
        author="יהודה שטיינברג",
        language="he",
        source="https://benyehuda.org/download/701.txt",
        blurb=(
            "Avraham-Hirsh the schoolmaster and Baruch-Shlomo the scribe. The title is the Aramaic "
            "a Talmudist reaches for when he wants to know who exactly is being accused."
        ),
        words=1252,
        kind=Kind.story,
        register=Register.modern,
        difficulty=15,
        model=BOUGHT_WITH,
    ),
    Entry(
        id="ysteinberg-hazaken-nechadav",
        title="הזקן בין נכדיו",
        author="יהודה שטיינברג",
        language="he",
        source="https://benyehuda.org/download/1786.txt",
        blurb=(
            "Old Avraham-Shlomo has a great sorrow, and it comes over him precisely when he is "
            "sitting at home surrounded by his grandchildren."
        ),
        words=1140,
        kind=Kind.story,
        register=Register.modern,
        difficulty=16,
        model=BOUGHT_WITH,
    ),
    Entry(
        id="ysteinberg-balaila-hahu",
        title="בלילה ההוא",
        author="יהודה שטיינברג",
        language="he",
        source="https://benyehuda.org/download/1236.txt",
        blurb=(
            "It was the custom of the young men of the kloyz, the moment evening prayers were "
            "finished. That night it went differently."
        ),
        words=1530,
        kind=Kind.story,
        register=Register.modern,
        difficulty=16,
        model=BOUGHT_WITH,
    ),
    Entry(
        id="ysteinberg-gedalyahu",
        title="גדליהו",
        author="יהודה שטיינברג",
        language="he",
        source="https://benyehuda.org/download/5864.txt",
        blurb=(
            "He scraped a living out of dry schoolteaching, and there was a good deal more to him "
            "than that, which nobody in the town required."
        ),
        words=1601,
        kind=Kind.story,
        register=Register.modern,
        difficulty=16,
        model=BOUGHT_WITH,
    ),
    Entry(
        id="ysteinberg-kria-vezman",
        title="קריאה וזמן",
        author="יהודה שטיינברג",
        language="he",
        source="https://benyehuda.org/download/5799.txt",
        blurb=(
            "Old Baruch-Bendit takes off the second pair of tefillin and is left with the whole "
            "morning and nothing to put in it."
        ),
        words=727,
        kind=Kind.story,
        register=Register.modern,
        difficulty=17,
        model=BOUGHT_WITH,
    ),
    Entry(
        id="ysteinberg-politika",
        title="עסקי פוליטיקה",
        author="יהודה שטיינברג",
        language="he",
        source="https://benyehuda.org/download/4456.txt",
        blurb=(
            "Whenever old Yeruham hears the young men talking politics he has something to say "
            "about it, and they would very much rather he did not."
        ),
        words=1154,
        kind=Kind.story,
        register=Register.modern,
        difficulty=17,
        model=BOUGHT_WITH,
    ),
    Entry(
        id="ysteinberg-mitoch-kaas",
        title="מתוך כעס",
        author="יהודה שטיינברג",
        language="he",
        source="https://benyehuda.org/download/3817.txt",
        blurb=(
            "She does not put on airs with the neighbours about being the one learned woman among "
            "them. That is not at all the same as forgiving them."
        ),
        words=817,
        kind=Kind.story,
        register=Register.modern,
        difficulty=18,
        model=BOUGHT_WITH,
    ),
    Entry(
        id="ysteinberg-avraham-meir",
        title="אברהם־מאיר הזקן ואלקנה האברך",
        author="יהודה שטיינברג",
        language="he",
        source="https://benyehuda.org/download/3496.txt",
        blurb=(
            "Old Avraham-Meir falls silent in the middle of his conversation with Elkanah, and the "
            "silence is the story."
        ),
        words=951,
        kind=Kind.story,
        register=Register.modern,
        difficulty=18,
        model=BOUGHT_WITH,
    ),
    Entry(
        id="ysteinberg-zeidel",
        title="זיידיל השען",
        author="יהודה שטיינברג",
        language="he",
        source="https://benyehuda.org/download/3242.txt",
        blurb=(
            "Zeidel the watchmaker is a Hasid in everything he does, except his clothes, about "
            "which he is not particular in the least."
        ),
        words=1139,
        kind=Kind.story,
        register=Register.modern,
        difficulty=18,
        model=BOUGHT_WITH,
    ),
    Entry(
        id="ysteinberg-kidush-levana",
        title="בשל קידוש לבנה",
        author="יהודה שטיינברג",
        language="he",
        source="https://benyehuda.org/download/1850.txt",
        blurb=(
            "Hirsh-Mendel told it. The whole thing turned on the blessing of the new moon, and on "
            "somebody arriving late for it."
        ),
        words=797,
        kind=Kind.story,
        register=Register.modern,
        difficulty=19,
        model=BOUGHT_WITH,
    ),
    Entry(
        id="ysteinberg-leil-pesach",
        title="בליל שני של פסח",
        author="יהודה שטיינברג",
        language="he",
        source="https://benyehuda.org/download/6774.txt",
        blurb=(
            "On the second night of Passover they used to sit together, year after year. This is "
            "what happened on one of them."
        ),
        words=827,
        kind=Kind.story,
        register=Register.modern,
        difficulty=19,
        model=BOUGHT_WITH,
    ),
    Entry(
        id="ysteinberg-kochvei-habitza",
        title="כוכבי הבצה",
        author="יהודה שטיינברג",
        language="he",
        source="https://benyehuda.org/download/5603.txt",
        blurb=(
            "Do you know the stars, boys? The good ones, that look down at you kindly. This is "
            "about the other kind."
        ),
        words=867,
        kind=Kind.story,
        register=Register.modern,
        difficulty=19,
        model=BOUGHT_WITH,
    ),
    Entry(
        id="ysteinberg-leil-nedudim",
        title="ליל נדודים",
        author="יהודה שטיינברג",
        language="he",
        source="https://benyehuda.org/download/4775.txt",
        blurb=(
            "Berki and Yomtil, two bachelors permanently installed in the rebbe's kloyz, and one "
            "night when neither of them sleeps."
        ),
        words=964,
        kind=Kind.story,
        register=Register.modern,
        difficulty=19,
        model=BOUGHT_WITH,
    ),
    Entry(
        id="ysteinberg-tzadik-sasov",
        title="הצדיק מסוסוב",
        author="יהודה שטיינברג",
        language="he",
        source="https://benyehuda.org/download/4521.txt",
        blurb=(
            "It is well known that the tzaddik of Sasov loved every Jew, whichever sort of Jew he "
            "turned out on inspection to be."
        ),
        words=974,
        kind=Kind.story,
        register=Register.modern,
        difficulty=19,
        model=BOUGHT_WITH,
    ),
    Entry(
        id="ysteinberg-bein-ziv",
        title="בין זיו לזיו",
        author="יהודה שטיינברג",
        language="he",
        source="https://benyehuda.org/download/8069.txt",
        blurb=(
            "R' Shammai the elder sits among the young married men in the kloyz and sets about "
            "sweetening a harsh judgement."
        ),
        words=1094,
        kind=Kind.story,
        register=Register.modern,
        difficulty=19,
        model=BOUGHT_WITH,
    ),
    Entry(
        id="ysteinberg-shalom-aleichem",
        title="שלום עליכם",
        author="יהודה שטיינברג",
        language="he",
        source="https://benyehuda.org/download/5157.txt",
        blurb=(
            "They asked old R' Henikh what peace in the house is actually worth. He told them, at "
            "length, and with an example."
        ),
        words=1449,
        kind=Kind.story,
        register=Register.modern,
        difficulty=19,
        model=BOUGHT_WITH,
    ),
    Entry(
        id="jsteinberg-atzamot",
        title="עצמות יבשות",
        author="יעקב שטיינברג",
        language="he",
        source="https://benyehuda.org/download/22964.txt",
        blurb=(
            "A company of young men and women who came up like blossom in the changing times. The "
            "title is Ezekiel's, and it is meant."
        ),
        words=676,
        kind=Kind.story,
        register=Register.modern,
        difficulty=16,
        model=BOUGHT_WITH,
    ),
    Entry(
        id="jsteinberg-aruchat-boker",
        title="ארוחת בוקר",
        author="יעקב שטיינברג",
        language="he",
        source="https://benyehuda.org/download/22960.txt",
        blurb=(
            "A man of thirty, light in heart and in eye, finds himself at breakfast in somebody "
            "else's family house."
        ),
        words=750,
        kind=Kind.story,
        register=Register.modern,
        difficulty=18,
        model=BOUGHT_WITH,
    ),
    Entry(
        id="jsteinberg-sharav",
        title="שרב",
        author="יעקב שטיינברג",
        language="he",
        source="https://benyehuda.org/download/22957.txt",
        blurb=(
            "Oh, the sharav. You hear the cry a thousand times a summer, and here is somebody who "
            "stopped to look at what the heat actually does."
        ),
        words=903,
        kind=Kind.story,
        register=Register.modern,
        difficulty=18,
        model=BOUGHT_WITH,
    ),
    Entry(
        id="jsteinberg-baal-hon",
        title="בעל הון",
        author="יעקב שטיינברג",
        language="he",
        source="https://benyehuda.org/download/10317.txt",
        blurb=(
            "In a poor shtetl hidden in the marsh forests of Polesia, the narrator has business to "
            "finish with a man of means."
        ),
        words=2520,
        kind=Kind.story,
        register=Register.modern,
        difficulty=20,
        model=BOUGHT_WITH,
    ),
    # --- Plays, which is where the spoken language was hiding ----------------------
    #
    # Nothing in the catalogue was conversation until now. Ben Yehuda has a genre index
    # nobody here had used — 401 plays — and a play is a named speaker and a line and
    # almost nothing else, which is both the register that was missing and a good shape
    # for a sentence-aligned reader. They arrive pointed, so Nakdimon is not consulted.
    #
    # **The filter is Ben Yehuda's own per-work badge**, which reads נחלת הכלל and says in
    # so many words that any use is permitted, commercial included. It is not boilerplate:
    # it correctly withholds itself from the works they host by permission, which is the
    # distinction that matters and the one the catalogue plan asks for. 113 of 397 carry
    # it; 28 of those survived the screen at up to 8,000 words.
    #
    # **Open question, and it wants a person.** Three of these are Shimshon Meltzer's
    # translations from the Yiddish, and Meltzer died in 1985 — life+70 would not release
    # them until 2056, while the badge says they are free now. The badge is the record and
    # the arithmetic disagrees with it. Settle that before the paid tier ships; the same
    # doubt covers the Chekhov and Reisen translators, whose dates were not checked.
    # Peretz's own Hebrew — `play-bagan-hair`, `play-al-yad-hahalon` — carries no such
    # doubt, and neither does Katzenelson, who died in 1944.
    #
    # Verse tragedy was left out on purpose. Tchernichovsky's Sophocles is dialogue in
    # form and nothing like speech, which is the opposite of what these are here for.
    Entry(
        id="play-achat",
        title="אחת",
        author="יצחק קצנלסון",
        language="he",
        source="https://benyehuda.org/download/52746.txt",
        blurb=(
            "A mother and four children between five and nine, one room and two doors. Written for "
            "children to act, which makes it the plainest spoken Hebrew in the catalogue."
        ),
        words=947,
        kind=Kind.play,
        register=Register.modern,
        difficulty=17,
        model=BOUGHT_WITH,
    ),
    Entry(
        id="play-bimkom-drasha",
        title="במקום דרשה",
        author="ישראל חיים טביוב",
        language="he",
        source="https://benyehuda.org/download/24753.txt",
        blurb=(
            "Ahituv turns thirteen and does not want to make the speech. His sister, four friends "
            "aged eight to thirteen, and a teacher all have views. The easiest play here."
        ),
        words=2896,
        kind=Kind.play,
        register=Register.modern,
        difficulty=15,
        model=BOUGHT_WITH,
    ),
    Entry(
        id="play-olam-haba",
        title="עולם הבא",
        author="יצחק ליבוש פרץ, תרגם שמשון מלצר",
        language="he",
        source="https://benyehuda.org/download/32067.txt",
        blurb=(
            "Late evening, a table laid for supper, a turner's bench under a failing paraffin "
            "lamp. The next world comes up, the way it does at that hour."
        ),
        words=1138,
        kind=Kind.play,
        register=Register.modern,
        difficulty=17,
        model=BOUGHT_WITH,
    ),
    Entry(
        id="play-mordechai-vehaman",
        title="מרדכי והמן",
        author="קדיש יהודה סילמן",
        language="he",
        source="https://benyehuda.org/download/10857.txt",
        blurb=(
            "Mordechai knocks on Haman's door and asks who lives here. A Purim play, four children "
            "in the cast and a crowd behind them."
        ),
        words=1737,
        kind=Kind.play,
        register=Register.modern,
        difficulty=18,
        model=BOUGHT_WITH,
    ),
    Entry(
        id="play-baohel",
        title="באוהל",
        author="יצחק קצנלסון",
        language="he",
        source="https://benyehuda.org/download/13951.txt",
        blurb=(
            "Jacob's sons in a dark tent, whispering in a temper, and Issachar standing in the "
            "doorway holding the torn coat."
        ),
        words=2230,
        kind=Kind.play,
        register=Register.modern,
        difficulty=19,
        model=BOUGHT_WITH,
    ),
    Entry(
        id="play-leachar-hakvura",
        title="לאחר הקבורה",
        author="יצחק ליבוש פרץ, תרגם שמשון מלצר",
        language="he",
        source="https://benyehuda.org/download/32068.txt",
        blurb=(
            "A widow and two aunts, the mirror turned to the wall and a memorial candle on the "
            "sill. The talk after a funeral, which is never about the dead."
        ),
        words=1162,
        kind=Kind.play,
        register=Register.modern,
        difficulty=20,
        model=BOUGHT_WITH,
    ),
    Entry(
        id="play-laila-bebeit-hakvarot",
        title="לילה בבית הקברות",
        author="יצחק ליבוש פרץ, תרגם שמשון מלצר",
        language="he",
        source="https://benyehuda.org/download/32069.txt",
        blurb=(
            "A corner of a graveyard, a leaning fence, a few thin trees and some very new graves. "
            "Peretz subtitled it a play for the nerves."
        ),
        words=1498,
        kind=Kind.play,
        register=Register.modern,
        difficulty=20,
        model=BOUGHT_WITH,
    ),
    Entry(
        id="play-hadov",
        title="הדוב",
        author="אנטון צ׳כוב, תרגם בן־ציון ידידיה",
        language="he",
        source="https://benyehuda.org/download/32078.txt",
        blurb=(
            "A young widow in mourning, a landowner arriving about a debt, and an old servant who "
            "can see exactly where this is going. Chekhov's one-act farce."
        ),
        words=3860,
        kind=Kind.play,
        register=Register.modern,
        difficulty=20,
        model=BOUGHT_WITH,
    ),
    Entry(
        id="play-bagan-hair",
        title="בגן העיר",
        author="יצחק ליבוש פרץ",
        language="he",
        source="https://benyehuda.org/download/1381.txt",
        blurb=(
            "Malka and Yosef sit under an oak in the town garden saying almost nothing. Twice "
            "nothing, Yosef offers, is a broken heart."
        ),
        words=1101,
        kind=Kind.play,
        register=Register.modern,
        difficulty=21,
        model=BOUGHT_WITH,
    ),
    Entry(
        id="play-al-yad-hahalon",
        title="על יד החלון",
        author="יצחק ליבוש פרץ",
        language="he",
        source="https://benyehuda.org/download/1031.txt",
        blurb=(
            "Miriam is alone at the window. Her father is in his grave and her mother is in prison "
            "over a stolen hen. Menachem comes up out of the dark."
        ),
        words=789,
        kind=Kind.play,
        register=Register.modern,
        difficulty=22,
        model=BOUGHT_WITH,
    ),
    Entry(
        id="play-achashverosh",
        title="אחשורוש מלך טפש",
        author="יצחק קצנלסון",
        language="he",
        source="https://benyehuda.org/download/32005.txt",
        blurb=(
            "Two girls put on the Purim story, in which the king of Persia and Media is not the "
            "sharpest man in it. The title settles that before the curtain."
        ),
        words=2204,
        kind=Kind.play,
        register=Register.modern,
        difficulty=22,
        model=BOUGHT_WITH,
    ),
    Entry(
        id="play-bat-hashadchan",
        title="בת השדכן",
        author="אברהם רייזן, תרגמה פנינה לשצ׳ינסקי",
        language="he",
        source="https://benyehuda.org/download/40973.txt",
        blurb=(
            "Neta Chikin has a broad greying beard, scheming eyes, and clothes that are half the "
            "old world and half the new. A matchmaker's comedy in one act."
        ),
        words=2604,
        kind=Kind.play,
        register=Register.modern,
        difficulty=22,
        model=BOUGHT_WITH,
    ),
]


def beit_midrash() -> list[Entry]:
    """What a reader who wants only Jewish texts would be left with.

    The catalogue is one list and stays one list; this is the predicate a Beit Midrash
    mode would filter by, defined now so the tagging can be shown to be sufficient for
    it. Nothing in the product calls this yet.
    """
    return [entry for entry in CATALOGUE if entry.tags & JEWISH]


def by_id(entry_id: str) -> Entry | None:
    for entry in CATALOGUE:
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
    for entry in CATALOGUE:
        if _key(entry.source) == wanted:
            return entry
        for rendering in entry.translations:
            if _key(rendering.source) == wanted:
                return entry
    return None
