"""What the built corpus is, on disk.

Its own clock, like the weekly's index and for the same reason: this is a publication
record, not a cache. `read_artifact` returns None on a schema mismatch, which is right
for something that can be recomputed and wrong for the list of what a reader can open —
the first time the pipeline's schema moved, the whole shelf would quietly empty.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from .calendar import ReadingKind, Schedule


class Portion(BaseModel):
    """One reading, built and on disk."""

    #: `nitzavim-vayeilech`, `pesach-shabbat-chol-ha-moed`. The URL and the folder.
    slug: str
    name: str
    hebrew: str
    kind: ReadingKind = ReadingKind.parasha
    #: Which portions of the annual cycle, 1-54. Two on a doubled week, none on a
    #: festival.
    numbers: list[int] = Field(default_factory=list)
    #: Hebcal's own range line: "Deuteronomy 29:9-31:30".
    summary: str
    #: Which book or books the reading is in, in reading order.
    books: list[str] = Field(default_factory=list)
    verses: int = 0
    aliyot: int = 0
    #: Running words, and the share of them that are hard. Both are measured at build
    #: time and written down here, because the library draws a row from the catalogue
    #: and the catalogue is written from this index — a portion with neither reads as a
    #: text with nothing in it, which is how the fifty-four first reached the shelf.
    words: int = 0
    difficulty: int = 0
    #: The words the reading opens with, pointed and accented as the Masorah wrote them.
    #: A portion is named for them, and they are what the page tells a search engine it
    #: is about — the one line that says which reading this is to somebody who knows.
    opening: str = ""
    #: The first verse's reference, under the opening words: "Deuteronomy 29:9".
    opening_ref: str = ""
    #: The folder under the corpus root holding this portion's reader.
    folder: str = ""
    #: The haftarah this portion has on an ordinary Shabbat, as a key into
    #: `Index.haftarot`; "" where it has none. What the page shows for a portion asked
    #: for by name. On a given Shabbat the week may say otherwise — a Shabbat Rosh
    #: Chodesh reads Isaiah 66 whatever the portion — and then `Week.haftarah` wins.
    haftarah: str = ""
    #: The Sephardic reading for the same, as Hebcal's range line, where it differs.
    #: Recorded and not shown.
    haftarah_sephardic: str = ""
    #: The annotator name the book's annotation carried when this was cut from it. The
    #: corpus keeps no artifact beside its readers, so this one string is the only thing
    #: that can say whether a portion's words are behind the shelf it came from — and
    #: without it the deploy's "all texts on the current annotator" was true of every
    #: text that keeps artifacts and silent about the fifty-four that do not
    #: (targum-internal#227). "" on a corpus cut before this was written down, which
    #: `annotate.versions.survey_corpus` counts as unknown rather than as current.
    annotator: str = ""

    @property
    def doubled(self) -> bool:
        return len(self.numbers) > 1

    def listed(self, covered: set[int] | None = None) -> bool:
        """Whether the library shows it.

        The 54 are what somebody browses, so a portion read on its own is listed and a
        festival — which belongs to a date rather than to the cycle — is not.

        A doubled week is the awkward one. It is a real reading and gets its own build,
        because the page shows it whole on the week it is read, and listing it beside
        both its halves would put the same chapters on the shelf three times. But some
        pairs are almost never read apart: Matot and Masei come separately about once a
        decade, so a corpus built from the next two years has neither of them and the
        shelf would be missing the end of Numbers entirely. So a doubled portion is
        listed exactly when its halves are not there — the shelf covers the whole Torah,
        and never twice.
        """
        if self.kind is not ReadingKind.parasha:
            return False
        if not self.doubled:
            return True
        return not any(number in (covered or set()) for number in self.numbers)


class Haftarah(BaseModel):
    """One haftarah, built and on disk.

    Keyed by what it is rather than when it is read, because the same one comes round
    on more than one Shabbat: see `calendar.Haftarah.key`. Which Shabbat reads it, and
    why, is the week's to say.
    """

    #: `isaiah-61-10-63-9`. The key into `Index.haftarot`.
    key: str
    #: Hebcal's own line: "Isaiah 61:10-63:9".
    summary: str
    #: Which book or books it is read from, in reading order, as Hebcal names them.
    books: list[str] = Field(default_factory=list)
    #: The same in Hebrew, joined the way the shelf joins a byline: "הושע · יואל".
    hebrew: str = ""
    verses: int = 0
    words: int = 0
    difficulty: int = 0
    opening: str = ""
    opening_ref: str = ""
    #: The folder under the corpus root holding the reader, or "" where the text is not
    #: on the shelf: the reference is carried either way.
    folder: str = ""
    #: Which file of the reader the page frames. A haftarah is one section, and the
    #: renderer writes a one-section text as `index.html` alone — no `sec-0001.html` —
    #: so pointing at the first section unconditionally is a 404 on most of them. A
    #: long one that the renderer splits on length opens on its first section, the way
    #: the portion does. Decided at build from what was written, the way `daily.opens_at`
    #: decides it off the disk.
    opens: str = "index.html"
    #: As `Portion.annotator`: what the book's annotation was called when this was cut.
    annotator: str = ""


class Week(BaseModel):
    """One Shabbat, and what is read on it, on one schedule."""

    #: ISO date of the Shabbat.
    day: str
    schedule: Schedule
    slug: str
    hdate: str = ""
    #: The haftarah read on this Shabbat, as a key into `Index.haftarot`. The
    #: portion's own on most weeks; a special Shabbat's on the weeks that have one.
    haftarah: str = ""
    #: Why it is not the portion's own — "Shabbat Shekalim" — or "".
    haftarah_reason: str = ""
    #: The Sephardic reading for the same Shabbat, as Hebcal's range line, where it
    #: differs. Recorded and not shown.
    haftarah_sephardic: str = ""


class Index(BaseModel):
    """The corpus and the calendar it is pointed at by."""

    index_version: int = 1
    built_at: str = ""
    #: Every portion built, by slug.
    portions: dict[str, Portion] = Field(default_factory=dict)
    #: Every haftarah the pointed weeks and the portions name, by key.
    haftarot: dict[str, Haftarah] = Field(default_factory=dict)
    #: Which portion each Shabbat reads, per schedule. The pointer, and the only part
    #: that changes from week to week.
    weeks: list[Week] = Field(default_factory=list)

    def week(self, day: str, schedule: Schedule) -> Week | None:
        for week in self.weeks:
            if week.day == day and week.schedule is schedule:
                return week
        return None

    def on(self, day: str, schedule: Schedule) -> Portion | None:
        found = self.week(day, schedule)
        return self.portions.get(found.slug) if found is not None else None

    def haftarah_on(self, day: str, schedule: Schedule) -> tuple[Haftarah | None, str]:
        """The haftarah read on one Shabbat, and why it is not the portion's own.

        The week's, where the week names one; the portion's ordinary one otherwise, so
        an index written before weeks carried a haftarah still answers. The reason is ""
        whenever the answer is the portion's own.
        """
        found = self.week(day, schedule)
        if found is None:
            return None, ""
        if found.haftarah:
            return self.haftarot.get(found.haftarah), found.haftarah_reason
        portion = self.portions.get(found.slug)
        if portion is None or not portion.haftarah:
            return None, ""
        return self.haftarot.get(portion.haftarah), ""

    def listed(self) -> list[Portion]:
        """The cycle, in order — what the library shows.

        Singles first decide what is covered, then the doubled weeks fill the gaps they
        left, so the shelf runs from בראשית to וזאת הברכה with nothing missing and
        nothing on it twice.
        """
        covered = {
            number
            for one in self.portions.values()
            if one.kind is ReadingKind.parasha and not one.doubled
            for number in one.numbers
        }
        return sorted(
            (one for one in self.portions.values() if one.listed(covered)),
            key=lambda one: one.numbers[0] if one.numbers else 999,
        )


def neighbours(portion: Portion, listed: list[Portion]) -> tuple[Portion | None, Portion | None]:
    """The portion read before this one and the one read after it.

    In the order of the year, and the year wraps: after וזאת הברכה comes בראשית, because
    that is what happens on Simchat Torah. A doubled week stands between the portion
    before its first half and the one after its second, whether or not its halves are on
    the shelf beside it. A festival reading belongs to a date rather than to the cycle
    and has neither — the same line `Portion.listed` draws.

    `listed` is what the shelf shows, so a neighbour is always somewhere a reader can go.
    """
    if portion.kind is not ReadingKind.parasha or not portion.numbers:
        return None, None
    cycle = sorted(
        (one for one in listed if one.numbers and one.slug != portion.slug),
        key=lambda one: one.numbers[0],
    )
    if not cycle:
        return None, None
    first, last = portion.numbers[0], portion.numbers[-1]
    before = [one for one in cycle if one.numbers[-1] < first]
    after = [one for one in cycle if one.numbers[0] > last]
    return (before[-1] if before else cycle[-1]), (after[0] if after else cycle[0])
