"""What was built, day by day, and what the log keeps to itself (2026-09-29).

Nobody reads a day's lines before /about shows them, so these are the reading. The first
half holds every line in `built.txt` to `about.refused`; the second holds `refused` to
what it was written to stop, because a guard that lets everything through passes the
first half perfectly.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from targum import about


def test_every_line_written_down_may_be_shown() -> None:
    """The one that fails when a day's lines say too much. The message is the line and
    the reason, which is everything whoever wrote it needs to write it again."""
    days = about.written()
    assert days, "built.txt holds no day at all"
    refused = [
        f"{day}: {line!r} — {why}"
        for day, lines in days
        for line in lines
        if (why := about.refused(line))
    ]
    assert not refused, "\n".join(refused)


def test_a_day_is_a_line_or_three_and_is_not_tomorrow() -> None:
    today = date.today().isoformat()
    for day, lines in about.written():
        assert 1 <= len(lines) <= about.MOST, f"{day} has {len(lines)} lines"
        assert len(set(lines)) == len(lines), f"{day} says the same thing twice"
        # One day's grace, for the reason `_from_git` has it: a date is written in the
        # writer's timezone and read in the runner's.
        assert day <= today or (date.fromisoformat(day) - date.today()).days <= 1, day


@pytest.mark.parametrize(
    "line",
    [
        # The back office.
        "Copies of the data are kept on a second server.",
        "The backup is written with a key that cannot delete.",
        "Each person on the waitlist is let in by hand.",
        "Visitors are counted a day at a time.",
        "The admin pages are four tabs.",
        "Nobody joins unless invited.",
        # Where a text comes from.
        "Forty stories from StoryWeaver are in the Library.",
        "Every text records its licence.",
        "The clips are CC BY, found by search.",
        "Eleven more books, on JPS 1917 for now.",
        "A video from YouTube can be read along with.",
        "The texts are in the public domain.",
        # The workings.
        "French cards wait behind TARGUM_FRENCH_IPA.",
        "The scene gate is scored, as targum-internal#134 asked.",
        "One command, `targum eval`, runs any stage.",
        "The reply is parsed even when the JSON is broken.",
        "The whole run cost $0.044.",
        "CI runs every browser test.",
        "The cache is kept between deploys.",
        "The lemma index is written down.",
        "See https://targum.page/about for more.",
        # Design.md §6.
        "Targum speaks Russian.",
        "The whole interface speaks Russian!",
        "The whole interface speaks Russian",
        "Playlists are here \N{PARTY POPPER}.",
        "David chose the flags.",
        "",
        "A line " + "that goes on " * 10 + "and on.",
    ],
)
def test_the_guard_refuses_what_the_log_does_not_say(line: str) -> None:
    assert about.refused(line), f"{line!r} would have been shown"


@pytest.mark.parametrize(
    "line",
    [
        "A first visit opens a text you can follow.",
        "targum works inside Claude and ChatGPT.",
        "The report on Your Progress reads the way a person would say it.",
        "A Russian word's card marks stress only where two sources agree.",
        "The language menu carries flags.",
        "A word in scripture says «probably» where its reading was worked out.",
        "The word שלום opens its card.",
    ],
)
def test_the_guard_lets_plain_lines_through(line: str) -> None:
    """The other way to be useless: `repo` must not stop "report", and a word of Hebrew
    or Russian is not an emoji."""
    assert not about.refused(line), about.refused(line)


def test_a_refused_line_is_not_drawn_and_the_day_keeps_its_others(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The test above can be skipped, merged past or not run. The page asks again, so a
    line that reached the file is still not a line that reached a visitor."""
    from targum.render.builder import about_page

    log = tmp_path / "built.txt"
    log.write_text(
        "# a note to the editor\n\n"
        "2026-09-02\nThe page remembers where you stopped.\n"
        "The backup was copying an empty file.\n\n"
        "2026-09-01\nThe waitlist is open.\n\n"
        "not a date\nThis block is left out.\n\n"
        "2025-12-31\nA day in another year says its year.\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(about, "BUILT", log)

    assert [day.isoformat() for day, _ in about.built()] == ["2026-09-02", "2025-12-31"]
    page = about_page()
    assert "The page remembers where you stopped." in page
    assert '<time datetime="2026-09-02">2 September</time>' in page
    assert '<time datetime="2025-12-31">31 December 2025</time>' in page
    for unsaid in ("backup", "waitlist", 'datetime="2026-09-01"', "left out", "a note to"):
        assert unsaid not in page, f"{unsaid!r} reached the page"


def test_the_page_stands_without_the_log(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from targum.render.builder import about_page

    monkeypatch.setattr(about, "BUILT", tmp_path / "nothing.txt")
    assert about.built() == []
    page = about_page()
    assert "targum is built in public" in page and 'class="built"' not in page


def test_the_lines_are_english_on_a_russian_page_and_say_so() -> None:
    """The days are written once, in English (David, 2026-09-29). A Russian page says its
    own words and its own dates around them, and marks the list as English so nothing
    reads it aloud in a Russian voice."""
    from targum.render.builder import about_page

    page = about_page(language="ru")
    assert "targum строится открыто" in page
    assert '<div class="built" lang="en" dir="ltr">' in page
    newest, lines = about.built()[0]
    assert lines[0] in page
    assert f'<time datetime="{newest.isoformat()}">{newest.day} ' in page
    assert newest.strftime("%B") not in page.split('class="built"')[1].split("</h2>")[0]


def test_the_log_is_packed_into_the_wheel() -> None:
    """The box has no repository, so the page there reads what the wheel carries. The
    log is tracked, and hatchling packs a tracked file beside the code — so the way to
    lose it is to ignore it, which is what happened to the stamp's neighbours."""
    root = Path(__file__).resolve().parents[1]
    assert about.BUILT.is_file() and about.BUILT.parent == root / "src/targum"
    ignored = (root / ".gitignore").read_text(encoding="utf-8")
    assert "built.txt" not in ignored
