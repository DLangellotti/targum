"""What a series' page says about one reader (design.md §12, "A series is one page of the
desk, for everyone", 2026-10-09): Read and Started, never "missed", and the weekly's level
chosen for whoever is asking."""

from __future__ import annotations

from typing import Any

import pytest

from targum import series_view
from targum.weekly.models import Edition, Issue, Level


class Asking(series_view.Reader):
    """A reader whose record is handed in rather than kept in a store."""

    def __init__(
        self,
        finished: dict[str, set[str]] | None = None,
        places: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(None, None)
        self._finished = finished or {}
        self._places = places or {}

    @property
    def signed_in(self) -> bool:
        return True

    def finished(self, document: str) -> set[str]:
        return self._finished.get(document, set())

    def place(self, document: str) -> dict[str, Any] | None:
        return self._places.get(document)

    def marked(self, language: str = "he") -> dict[str, int]:
        return {}


def test_a_reading_is_read_started_or_not_marked_at_all() -> None:
    reader = Asking(
        finished={"all": {"1", "2", "3"}, "some": {"1"}},
        places={"opened": {"section": "2", "at": 5}},
    )
    assert reader.mark("all", 3)["state"] == "read"
    assert reader.mark("some", 3)["state"] == "started"
    opened = reader.mark("opened", 3)
    assert opened["state"] == "started" and opened["here"] == "2"
    assert reader.mark("never", 3)["state"] == "", "a reading not opened is not missed"
    assert reader.mark("whole", 0)["state"] == ""


def test_a_stranger_has_no_marks() -> None:
    stranger = series_view.Reader(None, None)
    assert not stranger.signed_in
    assert stranger.mark("any", 3) == {"state": "", "finished": set(), "here": ""}


def _issue() -> Issue:
    return Issue(
        id="2026-w40",
        dated="2026-09-28",
        title="t",
        editions=[
            Edition(level=one, entry_id=f"e-{one.value}", folder=f"f-{one.value}")
            for one in (Level.aleph, Level.bet, Level.gimel)
        ],
    )


@pytest.mark.parametrize(
    ("known", "chosen"),
    [
        ({"aleph": 97, "bet": 92, "gimel": 83}, Level.bet),
        ({"aleph": 97, "bet": 95, "gimel": 91}, Level.gimel),
        ({"aleph": 60, "bet": 50, "gimel": 40}, Level.aleph),
    ],
)
def test_the_weekly_opens_at_the_hardest_level_the_reader_would_follow(
    monkeypatch: pytest.MonkeyPatch, known: dict[str, int], chosen: Level
) -> None:
    monkeypatch.setattr(series_view, "weekly_known", lambda reader, issue: known)
    assert series_view.weekly_level(Asking(), _issue(), [], Level.bet) == chosen


def test_with_nothing_to_measure_it_opens_at_the_level_read_last(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(series_view, "weekly_known", lambda reader, issue: {})
    monkeypatch.setattr(
        series_view, "_weekly_document", lambda issue_id, level: (f"doc-{level.value}", 3)
    )
    issue = _issue()
    reader = Asking(places={"doc-gimel": {"section": "1", "at": 9}, "doc-aleph": {"at": 3}})
    assert series_view.weekly_level(reader, issue, [issue], Level.bet) == Level.gimel
    assert series_view.weekly_level(Asking(), issue, [issue], Level.bet) == Level.bet


def test_a_cycles_month_is_read_off_the_hebrew_date() -> None:
    assert series_view._month_of("27 Tishrei 5787") == ("Tishrei", "5787")
    assert series_view._month_of("3 Adar II 5787") == ("Adar II", "5787")
    assert series_view._month_of("") == ("", "")
