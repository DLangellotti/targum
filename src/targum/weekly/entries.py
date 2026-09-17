"""Published issues, as catalogue entries.

The catalogue is curated data that arrives from a laptop; this is generated content that
lives on the box. They are different things with different clocks, and joining them here
rather than in `catalogue.json` is what lets a Monday issue appear without a deploy.
"""

from __future__ import annotations

from ..catalogue import Entry, Kind, Register, Tag
from . import index
from .models import LEVELS, Issue, Level, identifier

#: The byline, which is also the marking. It rides on `Document.author`, so it is drawn
#: on the contents page of every built reader by machinery that already exists, and it
#: cannot be lost by a change to a template.
#:
#: What issues written before 2026-09-17 carry, in Hebrew, and nothing new does.
#:
#: There was a byline — "Compiled by the targum team" — and a notice under the reader:
#: "Compiled by a model from this week's reporting and curated by the targum team before
#: it went out." Both were accurate while a person read every issue and pressed publish.
#:
#: On 2026-09-17 that gate came out: `deploy/weekly-run.sh` writes, builds, publishes,
#: announces and ships an issue on a schedule, and nobody reads it first. David's call,
#: made knowing the alternative, was that neither line survives — an issue carries its
#: sources at the foot and says nothing about how it was made, rather than saying
#: something that used to be true.
#:
#: These two stay because **old issues still carry them**. An issue published before the
#: change was curated, its byline is a fact about it, and `pipeline.byline_for` still
#: renders the Hebrew one into English so those issues read as they always did. Nothing
#: new is composed with a byline: `weekly draft` passes an empty author now.
BYLINE_HE = "נערך בידי מערכת ״תרגום״"

#: And what it said before 2026-09-14. "חובר בידי צוות תרגום" is a book's colophon rather
#: than a paper's, and it reads as "compiled by the translation team": תרגום is the
#: ordinary word, and nothing marked it as a name. The gershayim did.
BYLINES_HE = (BYLINE_HE, "חובר בידי צוות תרגום")

#: The English those old Hebrew bylines are rendered as. Not put on anything new.
BYLINE_WAS = "Compiled by the targum team"


def title_for(issue: Issue, level: Level) -> str:
    return f"{issue.title} · {LEVELS[level].label}"


def entries_for(issue: Issue) -> list[Entry]:
    out: list[Entry] = []
    for edition in issue.editions:
        out.append(
            Entry(
                id=edition.entry_id,
                title=title_for(issue, edition.level),
                # No author since 2026-09-17: nobody reads an issue before it goes out,
                # so there is nobody to name. Issues published before then keep theirs.
                author="",
                language="he",
                # The prefix `Build.PUBLIC_SOURCES` recognises, so the English is bought
                # once and shared by every reader rather than per person. It is one
                # public text; charging the second reader for it would be wrong.
                source=f"weekly:{identifier(issue.id, edition.level)}",
                blurb=issue.blurb,
                words=edition.words,
                tags=frozenset({Tag.journalism}),
                kind=Kind.article,
                register=Register.modern,
                difficulty=edition.difficulty,
                # Deliberately no `translations`: nobody published an English of this.
                #
                # And deliberately no `model` either, which is not the same as forgetting
                # one. `Entry.model` names the model a text's *English* was bought with,
                # and `Issue.model` is the one that wrote the Hebrew — a different and
                # more expensive model. Recording the writer here would make the server
                # translate on it, at four times the price, and miss the cache of every
                # reader built the ordinary way. Empty means "the hosted default", which
                # is what `serve` already falls back to and what is wanted.
                model="",
                # The weekly's Hebrew is targum's own writing, and `licensing.verdict`
                # reads `targum` as nothing owed to anybody — the standing an empty
                # field would misreport as unknown (targum-internal#115).
                licence="targum",
            )
        )
    return out


def entries() -> list[Entry]:
    """Every edition somebody can open.

    A draft appears nowhere — not in the library, not in the sitemap, not at its own
    URL — because a draft is not published. Nor does a published edition whose reader
    was never built or never arrived: a row on the shelf that leads to a 404 is worse
    than a row that is not there yet.
    """
    out: list[Entry] = []
    for issue in index.readable():
        out.extend(entries_for(issue))
    return out
