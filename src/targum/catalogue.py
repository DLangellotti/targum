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
"""

from __future__ import annotations

import json
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
        model=BOUGHT_WITH,
    ),
]


def beit_midrash() -> list[Entry]:
    """What a reader who wants only Jewish texts would be left with.

    The catalogue is one list and stays one list; this is the predicate a Beit Midrash
    mode would filter by, defined now so the tagging can be shown to be sufficient for
    it. Nothing in the product calls this yet.
    """
    return [entry for entry in CATALOGUE if entry.tags]


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
