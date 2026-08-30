"""What an issue of the weekly is, on disk.

Deliberately not `models.Artifact`. `read_artifact` returns None on a schema mismatch,
which is right for a cache — a stale entry should be recomputed — and catastrophic for a
publication record, where the same rule would silently empty the archive the first time
the pipeline's schema moved. These carry their own clock in `Index.index_version` and
never touch `models.SCHEMA_VERSION`.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field, model_validator


class Level(StrEnum):
    """The three the same week is written at.

    Named for the ulpan rungs in `render/assets/progress.js`, which is where they get
    their meaning: a rung is a reader's own marked vocabulary, weighted by how common
    each word is. These are identifiers — ids, folders, URLs — and never what a reader
    is shown. See `LEVELS` for that.
    """

    aleph = "aleph"
    bet = "bet"
    gimel = "gimel"


class Part(StrEnum):
    """The five sections, in the order they run."""

    israel = "israel"
    world = "world"
    tech = "tech"
    sport = "sport"
    culture = "culture"


#: Each section's Hebrew heading. These are rendered as level-1 headings by the compose
#: step rather than asked of the model, so `render.builder.split_sections` cannot be
#: broken by a model that decides to write `##`.
PART_TITLES: dict[Part, str] = {
    Part.israel: "ישראל",
    Part.world: "העולם",
    Part.tech: "מדע וטכנולוגיה",
    Part.sport: "ספורט",
    Part.culture: "תרבות",
}


class LevelSpec(BaseModel):
    """What a level is called and what it asks of a reader.

    The name and the count are separate fields because the pair does separate work: the
    count carries the ordering, which frees the name from having to prove it outranks
    its neighbour. "Simplified" and "real Hebrew" both assert ordinary unsimplified
    prose and neither wins on wording; 5,000 against 3,000 settles it first.
    """

    name: str
    #: The vocabulary this level is written for, rounded on purpose. The ladder itself
    #: is round for the same reason: "the figures behind ulpan levels vary between
    #: ulpanim, and false precision here would be a claim nobody can support."
    written_for: int
    #: Only the top level is open-ended, and the plus is what says so. aleph stops at
    #: bet and bet stops at gimel, but gimel holds every rung above it, because the
    #: weekly ends there and the real newspaper takes over.
    open_ended: bool = False
    #: The share of running words a reader would look up, as `annotate.difficulty`
    #: counts it. Tiled onto the 40 journalism entries already in the catalogue, which
    #: measure 11 to 23 — bands chosen by eye run far too high, because the ruler skips
    #: proper nouns and real news therefore measures low despite reading hard.
    band: tuple[int, int]

    #: Mean words per sentence, and the reason it is here rather than in a comment.
    #:
    #: The word ruler alone cannot tell the first two levels apart. Measured on the
    #: first real issue: 15%, 14%, 24% — the easy edition came out *harder* than the
    #: simplified one, because writing for a small vocabulary means explaining who
    #: everybody is, and an explanation is more words rather than commoner ones. What
    #: separated them cleanly was sentence length: 6.7, 11.4, 14.4.
    #:
    #: The codebase already knew this in general — "difficulty counts words and says
    #: nothing about syntax; Brenner measures the same as Esther and reads far harder" —
    #: and the weekly runs straight into it, because what makes these three levels
    #: different is mostly syntax. So the gate measures both. The bands overlap, which
    #: is harmless: a level is only ever checked against its own.
    sentence: tuple[float, float]

    @property
    def figure(self) -> str:
        return f"{self.written_for:,}{'+' if self.open_ended else ''}"

    @property
    def label(self) -> str:
        """What a reader sees: the name, then the count that orders it."""
        return f"{self.name} · {self.figure} words"


# The two bands do different jobs, and the widths say which.
#
# `band` is wide and mostly overlapping: it asks whether this is Hebrew of roughly the
# right register at all, and it is the only thing that can catch an issue drifting into
# scholarly or archaic vocabulary. It cannot tell the first two levels apart — measured
# twice on real output, the easy edition came out at 11% and the simplified one at 9%,
# the wrong way round both times, because writing for a small vocabulary means
# explaining who everybody is and an explanation is more words rather than commoner ones.
#
# `sentence` is tight and barely overlaps, and it is what actually discriminates:
# 6.7, 11.4, 14.4 on the same three editions, in order, every time. What separates these
# levels is syntax, and the library's own column was never measuring syntax.
LEVELS: dict[Level, LevelSpec] = {
    Level.aleph: LevelSpec(name="Easy", written_for=1000, band=(5, 15), sentence=(4, 9.5)),
    Level.bet: LevelSpec(name="Simplified", written_for=3000, band=(7, 20), sentence=(9, 14)),
    Level.gimel: LevelSpec(
        name="Real Hebrew", written_for=5000, open_ended=True, band=(14, 28), sentence=(12.5, 26)
    ),
}


class State(StrEnum):
    draft = "draft"
    published = "published"
    withdrawn = "withdrawn"


#: Tier 1 named a licence and may be drawn on. Tier 2 gave facts and nothing else.
FACTS_ONLY = 2


class Story(BaseModel):
    """One clustered item of the fact base, kept so a published issue can be audited
    back to what it was written from."""

    section: Part
    headline: str
    facts: list[str] = Field(default_factory=list)
    #: How many independent outlets carried it. A free importance signal, and the
    #: reason selection needs no model of its own.
    outlets: list[str] = Field(default_factory=list)
    links: list[str] = Field(default_factory=list)
    #: 1 where the licence lets the text be used, 2 where only the facts may be.
    tier: int = 2
    licence: str = ""
    #: Tier 1 only, and enforced below rather than remembered.
    excerpt: str = ""
    #: The week's biggest story, by how many independent outlets carried it. Exactly one
    #: per brief. Only the top level treats it differently, by writing it at length.
    lead: bool = False

    @model_validator(mode="after")
    def _only_a_licensed_source_is_quoted(self) -> Story:
        """A facts-only story cannot hold an excerpt, because the type will not carry
        one.

        This could as easily live in the gatherer, and it lived there first. It is here
        because the gatherer is the private half and does not ship: the one rule that
        keeps somebody else's prose out of an issue would then be enforced by code no
        test on any other machine ever runs. A structure that cannot represent the
        violation needs no discipline to maintain.
        """
        if self.excerpt and self.tier >= FACTS_ONLY:
            raise ValueError(
                "a facts-only source gives facts: tier 2 carries a headline and a hook, "
                "never text to draw on"
            )
        return self


class Edition(BaseModel):
    """One level of one issue, and how it measured."""

    level: Level
    entry_id: str
    folder: str
    words: int = 0
    difficulty: int = 0
    #: Whether it landed inside its level's band. A false here keeps the whole issue
    #: out of the library: a mislabelled level is worse than a missing one.
    #: Mean words per sentence, kept because it is half of what decided `ok` and a
    #: person looking at an issue that failed needs to see which half.
    sentence: float = 0.0
    ok: bool = False
    attempts: int = 0
    #: Runs of a facts-only source's own wording that survived into this level. Empty is
    #: the only acceptable value, and it is a different kind of failure from a missed
    #: band: a band is a labelling problem a person may knowingly publish through, and
    #: this is not. `publish` refuses an edition with anything here, `--anyway` included.
    lifted: list[str] = Field(default_factory=list)


class Issue(BaseModel):
    id: str
    #: The Monday it belongs to, ISO.
    dated: str
    title: str
    blurb: str = ""
    state: State = State.draft
    made: int = 0
    published_at: int = 0
    model: str = ""
    editions: list[Edition] = Field(default_factory=list)
    sources: list[Story] = Field(default_factory=list)
    #: What the generator wants a person to look at before publishing.
    notes: str = ""

    def edition(self, level: Level) -> Edition | None:
        return next((e for e in self.editions if e.level is level), None)

    @property
    def complete(self) -> bool:
        return len(self.editions) == len(Level) and all(e.ok for e in self.editions)


# -- what the model returns, and the file it becomes ---------------------------------
#
# Public, though what is *said* to the model is not. These are the shape of an issue and
# the function that turns it into a file, and the file's shape is the safety-critical
# half: get the heading levels wrong and `render.builder.split_sections` folds the first
# section into the masthead, producing a plausible issue that is quietly one section
# short. That is worth a test on every push, which means it cannot live in the half that
# does not ship.


class WrittenItem(BaseModel):
    headline: str
    body: str


class WrittenSection(BaseModel):
    part: Part
    items: list[WrittenItem] = Field(default_factory=list)


class Written(BaseModel):
    """One issue as the model hands it back.

    Asked for as a structured object rather than as markdown, so the section headings
    are written by code below. A model returning markdown would break the structure the
    first time it chose `##` over `#`, and nothing would say so.
    """

    title: str
    standfirst: str
    sections: list[WrittenSection] = Field(default_factory=list)


def markdown(written: Written, byline: str) -> str:
    """The composed issue, as a file a person can edit.

    Masthead heading, byline, standfirst, then one level-1 heading per section. The
    standfirst is required and is not decoration: `split_sections` only lets a heading
    open a section once the current one holds prose, so without a paragraph between the
    byline and the first section heading the issue comes out one section short with the
    first one mislabelled.
    """
    lines = [
        "---",
        f"title: {written.title}",
        f"author: {byline}",
        "language: he",
        "---",
        "",
        f"# {written.title}",
        "",
        written.standfirst.strip(),
    ]
    for section in written.sections:
        lines += ["", f"# {PART_TITLES[section.part]}"]
        for item in section.items:
            # Level 3 deliberately. `split_sections` opens a new section on a heading
            # of level 1 or 2, so `##` here would make every item its own section; and
            # `**bold**` — which this was — is flattened by the markdown ingester, so
            # the headlines disappeared into the prose and no reader could tell where
            # one story ended and the next began.
            lines += ["", f"### {item.headline.strip()}", "", item.body.strip()]
    return "\n".join(lines) + "\n"


class Brief(BaseModel):
    """What goes to the model, and what an issue can be audited back to.

    Written to disk beside the composed markdown so a published issue can always be
    checked against what it was written from — which is the whole answer to "where did
    this claim come from", and the only way the licence boundary can be inspected after
    the fact rather than trusted.
    """

    week: str
    #: When it was gathered, so a brief and the feeds it came from can be lined up.
    made: int = 0
    stories: list[Story] = Field(default_factory=list)

    def section(self, part: Part) -> list[Story]:
        return [story for story in self.stories if story.section is part]

    @property
    def facts_only(self) -> list[Story]:
        """The stories whose wording may never appear in the issue."""
        return [story for story in self.stories if story.tier >= 2]


class Index(BaseModel):
    """Every issue the box knows about. Its own version, so the pipeline's can move
    without touching the archive."""

    index_version: int = 1
    issues: list[Issue] = Field(default_factory=list)


# -- how an issue is addressed --------------------------------------------------------
#
# One issue is three texts, not one text with three variants. `Entry`, `Build`, the
# reader folder, the cache key and the `doc` table's content hash are every one of them
# one-source-one-output, and a variant would have had to reach into all of them. Three
# ids cost nothing, and a reader moving up a level getting a fresh reading position is
# right rather than a bug: they are different texts.


def identifier(week: str, level: Level) -> str:
    """What the fetcher is handed: `2026-w36-bet`."""
    return f"{week}-{level.value}"


def parse_identifier(text: str) -> tuple[str, Level] | None:
    week, _, name = text.rpartition("-")
    if not week or name not in set(Level):
        return None
    return week, Level(name)


def entry_id(week: str, level: Level) -> str:
    return f"weekly-{identifier(week, level)}"


def folder(week: str, level: Level) -> str:
    """The built reader's directory, under the weekly root."""
    return f"{entry_id(week, level)}-he"
