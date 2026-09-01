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
    #: The words the reading opens with, pointed and accented as the Masorah wrote them.
    #: A portion is named for them, and they are what the page tells a search engine it
    #: is about — the one line that says which reading this is to somebody who knows.
    opening: str = ""
    #: The first verse's reference, under the opening words: "Deuteronomy 29:9".
    opening_ref: str = ""
    #: The folder under the corpus root holding this portion's reader.
    folder: str = ""

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


class Week(BaseModel):
    """One Shabbat, and what is read on it, on one schedule."""

    #: ISO date of the Shabbat.
    day: str
    schedule: Schedule
    slug: str
    hdate: str = ""


class Index(BaseModel):
    """The corpus and the calendar it is pointed at by."""

    index_version: int = 1
    built_at: str = ""
    #: Every portion built, by slug.
    portions: dict[str, Portion] = Field(default_factory=dict)
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
