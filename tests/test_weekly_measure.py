"""Measuring a hand-edited level again, with nothing drafted (targum-internal#396)."""

from __future__ import annotations

from pathlib import Path

import pytest
import typer

from targum.weekly import index as weekly_index
from targum.weekly import verify
from targum.weekly.models import Edition, Index, Issue, Level, State, Story, entry_id, folder
from targum.weekly.verify import Gauge

WEEK = "2026-w40"


@pytest.fixture
def drafted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """w40 as it was on 2026-09-29: Simplified refused for its sentences, then edited."""
    monkeypatch.setenv("TARGUM_WEEKLY_DIR", str(tmp_path))
    monkeypatch.setattr(weekly_index, "_cached", None)
    # The ruler is DICTA, which this test does not need: what is measured is decided by
    # what the page says, so the page carries its own numbers.
    monkeypatch.setattr(
        verify,
        "gauge",
        lambda page, language="he": Gauge(
            difficulty=17, sentence=11.2 if "joined" in page else 8.3
        ),
    )
    issue = Issue(
        id=WEEK,
        dated="2026-09-28",
        title="השבוע",
        sources=[Story(section="israel", headline="מישהו כתב את המשפט הזה בדיוק כך", tier=2)],
        editions=[
            Edition(
                level=Level.bet,
                entry_id=entry_id(WEEK, Level.bet),
                folder=folder(WEEK, Level.bet),
                difficulty=17,
                sentence=8.3,
                ok=False,
            )
        ],
        notes="Simplified: Sentences averaged 8.3 words.",
    )
    weekly_index.save(Index(issues=[issue]))
    weekly_index._cached = None
    (tmp_path / WEEK).mkdir()
    return tmp_path / WEEK / f"weekly-{WEEK}-{Level.bet.value}.md"


def _issue() -> Issue:
    weekly_index._cached = None
    found = weekly_index.by_week(WEEK)
    assert found is not None
    return found


def test_an_edited_level_passes_when_it_measures_inside(drafted: Path) -> None:
    from targum.cli import weekly_measure

    drafted.write_text("# השבוע\n\nשורות קצרות joined לשורות ארוכות.\n", encoding="utf-8")
    weekly_measure(WEEK)
    edition = _issue().editions[0]
    assert edition.ok and edition.sentence == 11.2
    assert _issue().notes == "", "the old refusal does not linger"
    assert _issue().state is State.draft, "measuring is not publishing"


def test_an_unchanged_level_is_still_refused_for_the_same_reason(drafted: Path) -> None:
    from targum.cli import weekly_measure

    drafted.write_text("# השבוע\n\nשורות קצרות.\n", encoding="utf-8")
    weekly_measure(WEEK)
    issue = _issue()
    assert not issue.editions[0].ok
    assert "Sentences averaged 8.3 words" in issue.notes


def test_a_source_s_own_wording_is_still_caught(drafted: Path) -> None:
    """The licence check is one of the three, not left to the draft."""
    from targum.cli import weekly_measure

    drafted.write_text("# השבוע\n\njoined מישהו כתב את המשפט הזה בדיוק כך.\n", encoding="utf-8")
    weekly_measure(WEEK)
    edition = _issue().editions[0]
    assert not edition.ok and edition.lifted


def test_machine_writing_is_still_caught(drafted: Path) -> None:
    from targum.cli import weekly_measure

    drafted.write_text("# השבוע\n\njoined חשוב לציין שזה כך.\n", encoding="utf-8")
    weekly_measure(WEEK)
    assert not _issue().editions[0].ok
    assert "machine-written" in _issue().notes


def test_a_published_issue_is_not_measured_again(drafted: Path) -> None:
    from targum.cli import weekly_measure

    issue = _issue()
    issue.state = State.published
    weekly_index.save(Index(issues=[issue]))
    with pytest.raises(typer.Exit):
        weekly_measure(WEEK)


def test_the_scheduled_run_measures_a_draft_rather_than_drafting_it_again() -> None:
    """Drafting again throws a hand edit away and spends on a new one."""
    root = Path(__file__).resolve().parents[1]
    script = (root / "deploy" / "weekly-run.sh").read_text(encoding="utf-8")
    code = "\n".join(line for line in script.splitlines() if not line.lstrip().startswith("#"))
    draft = code.index('weekly draft "$WEEK"')
    assert 'if [ "$STATE" = "missing" ]; then' in code[:draft]
    assert 'elif [ "$STATE" = "draft" ]' in code
    assert '"$TARGUM" weekly measure "$WEEK"' in code
