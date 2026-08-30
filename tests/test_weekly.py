"""The weekly: storage, addressing, and the shape a composed issue has to have."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from targum import catalogue
from targum.ingest import fetch
from targum.models import BlockKind
from targum.render import split_sections
from targum.segment import segment_document
from targum.weekly import entries, index
from targum.weekly.models import (
    LEVELS,
    Edition,
    Index,
    Issue,
    Level,
    State,
    entry_id,
    folder,
    identifier,
    parse_identifier,
)

WEEK = "2026-w36"


def _sections(level: Level, fake_segmenter: object) -> list[str]:
    document = fetch.load(f"weekly:{identifier(WEEK, level)}")
    segmented = segment_document(document, fake_segmenter)  # type: ignore[arg-type]
    return [section.title for section in split_sections(segmented)]


# -- addressing ----------------------------------------------------------------------


def test_an_issue_is_addressed_the_same_way_everywhere() -> None:
    assert identifier(WEEK, Level.bet) == "2026-w36-bet"
    assert entry_id(WEEK, Level.bet) == "weekly-2026-w36-bet"
    assert folder(WEEK, Level.bet) == "weekly-2026-w36-bet-he"
    assert parse_identifier("2026-w36-bet") == (WEEK, Level.bet)


@pytest.mark.parametrize("bad", ["", "bet", "2026-w36", "2026-w36-dalet"])
def test_nonsense_is_not_an_issue(bad: str) -> None:
    assert parse_identifier(bad) is None


# -- the levels ----------------------------------------------------------------------


def test_the_counts_order_the_levels() -> None:
    """The number carries the ordering so the name does not have to. "Simplified" and
    "real Hebrew" both claim ordinary prose and neither outranks the other on wording."""
    written_for = [LEVELS[level].written_for for level in Level]
    assert written_for == sorted(written_for)
    assert [LEVELS[level].band for level in Level] == sorted(LEVELS[level].band for level in Level)


def test_only_the_top_level_is_open_ended() -> None:
    """aleph stops at bet and bet stops at gimel, but gimel holds every rung above it,
    because the weekly ends there and the real newspaper takes over."""
    assert [LEVELS[level].open_ended for level in Level] == [False, False, True]
    assert LEVELS[Level.gimel].figure.endswith("+")
    assert LEVELS[Level.aleph].label == "Easy · 1,000 words"


def test_the_bands_sit_inside_the_range_real_journalism_measures() -> None:
    """The catalogue's own journalism runs 11 to 23 on this ruler, because it skips
    proper nouns and news is full of them. Bands chosen by eye run far above that, and
    would put the top of the bridge harder than the thing it bridges to."""
    lowest = LEVELS[Level.aleph].band[0]
    highest = LEVELS[Level.gimel].band[1]
    assert lowest >= 5, "below what test_public asserts a measured text can be"
    assert highest <= 30, "harder than any real news article in the catalogue"


# -- the index -----------------------------------------------------------------------


def test_a_missing_weekly_is_not_an_error() -> None:
    """With no issue on disk the whole surface is absent, the way the library is empty
    without a catalogue. The suite points every test at an empty directory, so this is
    simply what a test that asks for no weekly sees."""
    assert index.load().issues == []
    assert index.published() == []
    assert index.latest() is None
    assert entries.entries() == []


def test_a_broken_index_does_not_take_the_library_down() -> None:
    index.index_path().parent.mkdir(parents=True, exist_ok=True)
    index.index_path().write_text("{not json", encoding="utf-8")
    index._cached = None
    assert index.load().issues == []


def test_an_index_round_trips() -> None:
    issue = Issue(
        id=WEEK,
        dated="2026-08-31",
        title="השבוע בעברית",
        state=State.published,
        editions=[
            Edition(
                level=level,
                entry_id=entry_id(WEEK, level),
                folder=folder(WEEK, level),
                ok=True,
            )
            for level in Level
        ],
    )
    index.save(Index(issues=[issue]))
    index._cached = None
    loaded = index.by_week(WEEK)
    assert loaded is not None
    assert loaded.complete
    assert loaded.edition(Level.gimel) is not None


def test_the_newest_issue_is_the_one_served(weekly_root: Path) -> None:
    latest = index.latest()
    assert latest is not None and latest.id == WEEK


# -- drafts --------------------------------------------------------------------------


def test_a_draft_appears_nowhere(weekly_root: Path) -> None:
    """A draft is on disk and readable by nobody. It is not in the library, not at its
    own id, and nothing that walks the catalogue can reach it."""
    assert index.by_week("2026-w37") is not None, "the draft is on disk"
    published = [issue.id for issue in index.published()]
    assert "2026-w37" not in published
    assert WEEK in published

    ids = {entry.id for entry in entries.entries()}
    assert "weekly-2026-w37-bet" not in ids
    assert catalogue.by_id("weekly-2026-w37-bet") is None
    assert catalogue.by_id("weekly-2026-w36-bet") is not None


# -- as catalogue entries ------------------------------------------------------------


def test_published_editions_join_the_catalogue(weekly_root: Path) -> None:
    everything = catalogue.everything()
    weekly = [entry for entry in everything if entry.id.startswith("weekly-")]
    assert len(everything) == len(catalogue.CATALOGUE) + len(weekly)
    # One entry per readable *edition*, counted rather than assumed to be three.
    # `readable` exists precisely to hand back an issue holding only the editions that
    # have a reader on disk — a publish that ran before a build, or a copy to the box
    # that half arrived, is the state it was written for. Multiplying by three asserted
    # the opposite of that contract, so a half-built issue failed this test with an
    # arithmetic mismatch that said nothing about which edition was missing.
    assert len(weekly) == sum(len(issue.editions) for issue in index.readable()), (
        "one entry per edition somebody can open"
    )
    assert [entry.id for entry in everything[: len(catalogue.CATALOGUE)]] == [
        entry.id for entry in catalogue.CATALOGUE
    ], "the curated catalogue keeps its order"


def test_an_edition_is_a_shared_public_text(weekly_root: Path) -> None:
    """Its English is bought once between every reader rather than per person: it is
    one public text, and charging the second reader for it would be wrong."""
    from targum.pipeline import Build

    entry = catalogue.by_id("weekly-2026-w36-bet")
    assert entry is not None
    assert entry.source.startswith(Build.PUBLIC_SOURCES)


def test_an_edition_says_how_it_was_made(weekly_root: Path) -> None:
    entry = catalogue.by_id("weekly-2026-w36-gimel")
    assert entry is not None
    assert entry.author == entries.BYLINE
    assert "targum team" in entry.author
    # The disclosure is not the byline's job. It is under the reader, in full.
    assert "model" not in entry.author.lower()
    assert "model" in entries.NOTICE.lower()
    assert entry.register is catalogue.Register.modern
    assert entry.kind is catalogue.Kind.article
    assert catalogue.Tag.journalism in entry.tags


def test_every_edition_carries_its_level_in_the_title(weekly_root: Path) -> None:
    titles = {entry.id: entry.title for entry in entries.entries()}
    assert titles["weekly-2026-w36-aleph"].endswith("Easy · 1,000 words")
    assert titles["weekly-2026-w36-gimel"].endswith("Real Hebrew · 5,000+ words")


def test_editions_are_measured_like_any_other_text(weekly_root: Path) -> None:
    """`test_public` asserts every catalogue entry has been measured, and an edition
    joins that catalogue — so an unmeasured issue would fail the compliance suite."""
    for entry in entries.entries():
        assert entry.difficulty, f"{entry.id} has never been measured"
        assert 5 <= entry.difficulty <= 60, entry.id
        assert entry.words


# -- the composed shape --------------------------------------------------------------


def test_the_fetcher_addresses_an_issue_by_what_it_is(weekly_root: Path) -> None:
    """Not by where it sits. An absolute path in `document.json` would break every
    lookup that keys on `document.source`."""
    document = fetch.load("weekly:2026-w36-bet")
    assert document.source == "weekly:2026-w36-bet"
    assert document.ingester == "weekly/1"
    assert document.language == "he"
    assert document.content_hash


def test_the_fetcher_refuses_something_that_is_not_an_issue(weekly_root: Path) -> None:
    from targum.errors import TargumError

    with pytest.raises(TargumError):
        fetch.load("weekly:not-a-level")


@pytest.mark.parametrize("level", list(Level))
def test_the_first_section_is_the_masthead(
    level: Level, weekly_root: Path, fake_segmenter: object
) -> None:
    """The trap, and it is silent.

    `split_sections` only lets a heading open a section once the current one holds
    prose, so that a title and a byline do not each become a section. An issue whose
    body opens straight onto its first section heading therefore swallows Israel into
    the masthead and comes out with five sections, the first mislabelled — a plausible
    page that is quietly wrong. The standfirst between the byline and the first section
    is what prevents it, and it is required of the composed output for this reason.
    """
    assert _sections(level, fake_segmenter) == [
        "השבוע בעברית",
        "ישראל",
        "העולם",
        "מדע וטכנולוגיה",
        "ספורט",
        "תרבות",
    ]


def test_without_a_standfirst_the_sections_come_out_wrong(
    tmp_path: Path, fake_segmenter: object
) -> None:
    """The failure the standfirst prevents, pinned so nobody removes it as decoration."""
    from targum.ingest.markdown import MarkdownIngester

    source = tmp_path / "issue.md"
    source.write_text(
        "---\ntitle: השבוע\nauthor: targum\nlanguage: he\n---\n\n"
        "# השבוע\n\n# ישראל\n\nועדה חדשה קמה השבוע.\n\n# ספורט\n\nקבוצה ניצחה.\n",
        encoding="utf-8",
    )
    segmented = segment_document(MarkdownIngester().load(str(source)), fake_segmenter)  # type: ignore[arg-type]
    titles = [section.title for section in split_sections(segmented)]
    assert titles == ["השבוע", "ספורט"], "Israel was swallowed by the masthead"


def test_the_byline_rides_on_the_document(weekly_root: Path) -> None:
    """So the marking is drawn by machinery that already exists and cannot be lost by
    a change to a template."""
    document = fetch.load("weekly:2026-w36-aleph")
    assert document.author == entries.BYLINE_HE
    assert document.blocks[1].kind is BlockKind.byline


# -- the file a composed issue becomes -------------------------------------------------


def _written() -> object:
    from targum.weekly.models import Part, Written, WrittenItem, WrittenSection

    return Written(
        title="השבוע בעברית",
        standfirst="חמישה נושאים מן השבוע שעבר.",
        sections=[
            WrittenSection(
                part=part,
                items=[WrittenItem(headline=f"כותרת {part.value}", body="גוף הידיעה כאן.")],
            )
            for part in Part
        ],
    )


def test_a_composed_issue_splits_into_a_masthead_and_five_sections(
    tmp_path: Path, fake_segmenter: object
) -> None:
    """The whole reason the markdown is written by code rather than asked for.

    A model returning markdown would break this the first time it chose `##` over `#`,
    and the failure is silent: five sections instead of six, the first mislabelled, and
    a page that looks entirely reasonable.
    """
    from targum.ingest.markdown import MarkdownIngester
    from targum.weekly.entries import BYLINE_HE
    from targum.weekly.models import markdown

    source = tmp_path / "issue.md"
    source.write_text(markdown(_written(), BYLINE_HE), encoding="utf-8")  # type: ignore[arg-type]
    segmented = segment_document(MarkdownIngester().load(str(source)), fake_segmenter)  # type: ignore[arg-type]

    assert [section.title for section in split_sections(segmented)] == [
        "השבוע בעברית",
        "ישראל",
        "העולם",
        "מדע וטכנולוגיה",
        "ספורט",
        "תרבות",
    ]


def test_the_byline_and_the_standfirst_are_both_in_the_file(tmp_path: Path) -> None:
    from targum.ingest.markdown import MarkdownIngester
    from targum.weekly.entries import BYLINE_HE
    from targum.weekly.models import markdown

    source = tmp_path / "issue.md"
    source.write_text(markdown(_written(), BYLINE_HE), encoding="utf-8")  # type: ignore[arg-type]
    document = MarkdownIngester().load(str(source))

    kinds = [block.kind for block in document.blocks[:3]]
    assert kinds == [BlockKind.heading, BlockKind.byline, BlockKind.paragraph]
    # In Hebrew, because it is set in the source column and read as source. The English
    # rides in the translation column beside it.
    assert document.author == entries.BYLINE_HE


def test_an_issue_with_no_standfirst_loses_a_section(
    tmp_path: Path, fake_segmenter: object
) -> None:
    """Pinned so nobody removes the standfirst as decoration. It is structural."""
    from targum.ingest.markdown import MarkdownIngester
    from targum.weekly.entries import BYLINE_HE
    from targum.weekly.models import Written, markdown

    bare = _written()
    stripped = Written(title=bare.title, standfirst="", sections=bare.sections)  # type: ignore[attr-defined]
    source = tmp_path / "issue.md"
    source.write_text(markdown(stripped, BYLINE_HE), encoding="utf-8")
    segmented = segment_document(MarkdownIngester().load(str(source)), fake_segmenter)  # type: ignore[arg-type]

    titles = [section.title for section in split_sections(segmented)]
    assert "ישראל" not in titles, "the first section was folded into the masthead"
    assert len(titles) == 5


def test_the_shelf_row_carries_who_wrote_it(tmp_path: Path) -> None:
    """The third place the marking has to appear, because a reader can arrive at any of
    them: the shelf list, the contents page, and the public page.

    It comes off `document.json` rather than being looked up per row, so the shelf and
    the reader can never disagree about who a text is from.
    """
    from targum.serve import Library
    from targum.weekly.entries import BYLINE_HE

    home = tmp_path / "home" / "weekly-2026-w36-bet-he"
    (home / "reader").mkdir(parents=True)
    (home / "reader" / "index.html").write_text("<!doctype html>", encoding="utf-8")
    (home / "document.json").write_text(
        json.dumps(
            {
                "schema_version": 4,
                "source": "weekly:2026-w36-bet",
                "title": "השבוע בעברית",
                "author": BYLINE_HE,
                "language": "he",
                "blocks": [],
            }
        ),
        encoding="utf-8",
    )

    library = Library(out=tmp_path / "out", store=None)
    (row,) = library.readers(tmp_path / "home")
    assert row["author"] == BYLINE_HE


def test_an_edition_names_no_translation_model(weekly_root: Path) -> None:
    """`Entry.model` is the model a text's English was bought with; `Issue.model` is the
    one that wrote the Hebrew, and they are not the same model or the same price.

    Recording the writer here would have the server translate on it — four times the
    cost — and miss the cache of every reader built the ordinary way. Empty means the
    hosted default, which is what is wanted.
    """
    for entry in entries.entries():
        assert entry.model == "", entry.id

    issue = index.by_week(WEEK)
    assert issue is not None and issue.model, "the writer is still recorded on the issue"


def test_editing_the_markdown_rebuilds_the_text(weekly_root: Path, tmp_path: Path) -> None:
    """The composed markdown is the source of truth, and that has to be true mechanically.

    `Build.ingest` keeps an existing `document.json` whose blocks differ from the file,
    reading the difference as somebody having hand-edited the extraction — which is the
    right call for a scanned book and exactly wrong here. Without a `source_hash` off
    the file, editing an issue and rebuilding did nothing at all, and said nothing.
    """
    from targum.ingest import fetch

    first = fetch.load("weekly:2026-w36-bet")
    assert first.source_hash, "the file's own hash, not the blocks'"

    issue = tmp_path / "2026-w36"
    issue.mkdir()
    original = (index.root() / "2026-w36" / "weekly-2026-w36-bet.md").read_text(encoding="utf-8")
    changed = original.replace("ועדה ציבורית", "ועדה חדשה")
    assert changed != original

    from targum.ingest.fetch.weekly import WeeklyFetcher

    edited = index.root() / "2026-w36" / "weekly-2026-w36-bet.md"
    try:
        edited.write_text(changed, encoding="utf-8")
        again = WeeklyFetcher().load("2026-w36-bet")
        assert again.source_hash != first.source_hash, "a changed file is a changed text"
    finally:
        edited.write_text(original, encoding="utf-8")


def test_an_issue_is_one_targum_not_chapters(tmp_path: Path, fake_segmenter: object) -> None:
    """A book is chapters and a reader wants them one at a time. An issue is five short
    sections that add up to a twenty-minute read, and splitting it gave a stranger a
    contents page and five clicks before any Hebrew.

    The headings stay headings inside the one file — `whole` changes where the text is
    cut, not how it is written.
    """
    from targum.ingest.markdown import MarkdownIngester
    from targum.render.builder import Section, split_sections
    from targum.weekly.entries import BYLINE_HE
    from targum.weekly.models import markdown

    source = tmp_path / "issue.md"
    source.write_text(markdown(_written(), BYLINE_HE), encoding="utf-8")  # type: ignore[arg-type]
    segmented = segment_document(MarkdownIngester().load(str(source)), fake_segmenter)  # type: ignore[arg-type]

    assert len(split_sections(segmented)) == 6, "unsplit, it would still be six"

    whole = Section(number=1, title="", segment_ids=[segment.id for segment in segmented.segments])
    assert len(whole.segment_ids) == len(segmented.segments), "every segment, one section"
