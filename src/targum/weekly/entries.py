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
#: "Compiled and curated" rather than "written by AI" because that is the accurate
#: description and not merely the softer one — a model assembles the issue from the fact
#: base, and a person reads it and presses publish. It is true only while that gate is
#: manual. Automate the gate and this sentence has to change with it; see `publish`.
#: The byline, and only the byline: who this is from.
#:
#: It said "compiled by a model, curated by the targum team" and now does not, because
#: a byline is not the place for a disclosure. The disclosure is under the reader, in
#: full, where somebody reading the issue meets it having read the issue rather than
#: instead of it. See `NOTICE`, and see the note below about where that leaves a reader
#: who never sees the page around it.
BYLINE = "Compiled by the targum team"

#: The same line, in the language of the text it stands under.
#:
#: The byline is a block of the document, so it is set in the source column and read as
#: source: annotated, tokenised, tappable. In English it came out as English words on
#: the Hebrew side of a Hebrew page, with the translation column repeating them back
#: identically — not a byline, a bug that happens to be legible. A Hebrew paper's byline
#: is in Hebrew, the translation column renders the English for free, and `Entry.author`
#: keeps the English for the library, where the surrounding page is English too.
BYLINE_HE = "חובר בידי צוות תרגום"

NOTICE = (
    "Compiled by a model from this week's reporting and curated by the targum team "
    "before it went out. The sources are listed at the foot."
)


def title_for(issue: Issue, level: Level) -> str:
    return f"{issue.title} · {LEVELS[level].label}"


def entries_for(issue: Issue) -> list[Entry]:
    out: list[Entry] = []
    for edition in issue.editions:
        out.append(
            Entry(
                id=edition.entry_id,
                title=title_for(issue, edition.level),
                author=BYLINE,
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
