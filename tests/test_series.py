"""What comes out on its own clock (`series.py`, 2026-09-11)."""

from __future__ import annotations

from typing import Any

import pytest


def test_every_series_is_named_even_with_nothing_built(monkeypatch: pytest.MonkeyPatch) -> None:
    from targum import series
    from targum.parasha.models import Index

    monkeypatch.setattr("targum.weekly.index.readable", lambda: [])
    monkeypatch.setattr("targum.parasha.build.load", lambda: Index())
    monkeypatch.setattr("targum.daily.calendar.for_day", lambda *a, **k: None)
    got = series.current()
    ids = [one["id"] for one in got]
    assert ids[:2] == ["weekly", "parasha"] and len(ids) > 2, "the weekly, the portion, the cycles"
    assert all(one["instalment"] is None for one in got)
    assert all(one["name"] and one["page"] and one["what"] for one in got)


def test_a_box_that_keeps_its_shelves_shut_offers_the_weekly_alone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from targum import series

    monkeypatch.setattr("targum.weekly.index.readable", lambda: [])
    assert [one["id"] for one in series.current(public=False)] == ["weekly"]


def test_the_weekly_s_instalment_carries_one_reader_a_level(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from targum import series
    from targum.weekly.models import Edition, Issue, Level, folder

    issue = Issue(
        id="2026-09-07",
        dated="2026-09-07",
        title="מבט השבוע",
        editions=[Edition(level=Level.aleph, entry_id="e", folder="f", ok=True)],
    )
    monkeypatch.setattr("targum.weekly.index.readable", lambda: [issue])
    got = series.current(public=False)[0]
    inst = got["instalment"]
    assert inst["id"] == "2026-09-07" and inst["when"] == "2026-09-07"
    (level,) = inst["levels"]
    assert level["level"] == "aleph" and level["folder"] == folder("2026-09-07", Level.aleph)
    assert level["reader"] == f"/reader/{level['folder']}/reader/index.html"


def test_a_series_that_cannot_be_read_is_left_out_rather_than_failing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from targum import series

    def broken() -> Any:
        raise RuntimeError("no index here")

    monkeypatch.setattr("targum.weekly.index.readable", broken)
    monkeypatch.setattr("targum.parasha.build.load", broken)
    monkeypatch.setattr("targum.daily.calendar.for_day", lambda *a, **k: None)
    ids = [one["id"] for one in series.current()]
    assert "weekly" not in ids and "parasha" not in ids and ids, "the cycles still answer"


# -- telling followers (2026-09-11) ---------------------------------------------------------

PORTION = {
    "id": "parasha",
    "name": "The weekly portion",
    "what": "This Shabbat's reading.",
    "page": "/parasha",
    "instalment": {"id": "ki-tavo", "title": "Ki Tavo", "hebrew": "כי תבוא", "when": "2026-09-12"},
}
WEEKLY = {
    "id": "weekly",
    "name": "Weekly News Digest",
    "what": "",
    "page": "/weekly",
    "instalment": {"id": "w", "title": "t"},
}
QUIET = {
    "id": "mishna-yomi",
    "name": "Mishna Yomi",
    "what": "",
    "page": "/mishna-yomi",
    "instalment": None,
}


def test_followers_are_told_once_about_an_instalment_and_the_weekly_is_left_to_its_own(
    tmp_path: Any,
) -> None:
    import io

    from targum import series
    from targum.accounts import Store
    from targum.mail import ConsoleMailer

    store = Store(tmp_path / "words.db")
    store.follow_series("a@example.org", "parasha")
    store.follow_series("b@example.org", "parasha")
    store.follow_series("c@example.org", "mishna-yomi")
    store.follow("d@example.org", True)
    box = io.StringIO()
    report = series.announce(
        store, ConsoleMailer(box), "https://targum.page", [WEEKLY, PORTION, QUIET], pause=0
    )
    assert report.sent == ["a@example.org", "b@example.org"], "the portion's followers"
    told = box.getvalue()
    assert "The weekly portion: Ki Tavo" in told and "כי תבוא" in told
    assert "https://targum.page/parasha" in told and "/series/stop?t=" in told
    assert "d@example.org" not in told, "the weekly has a mailout of its own"
    again = series.announce(
        store, ConsoleMailer(io.StringIO()), "https://targum.page", [PORTION], pause=0
    )
    assert again.sent == [], "running it twice sends nothing the second time"
    landed = dict(PORTION, instalment=dict(PORTION["instalment"], id="nitzavim", title="Nitzavim"))
    later = series.announce(
        store, ConsoleMailer(io.StringIO()), "https://targum.page", [landed], pause=0
    )
    assert later.sent == ["a@example.org", "b@example.org"], "the next instalment is news again"


def test_one_click_stops_a_series_and_unfollowing_does_too(tmp_path: Any) -> None:
    import io

    from targum import series
    from targum.accounts import Store
    from targum.mail import ConsoleMailer

    store = Store(tmp_path / "words.db")
    store.follow_series("a@example.org", "parasha")
    ((email, stop),) = store.followers("parasha")
    assert email == "a@example.org" and store.series_followed("a@example.org") == ["parasha"]
    assert store.stop_following(stop) and store.followers("parasha") == []
    assert store.series_followed("a@example.org") == []
    assert not store.stop_following("nonsense") and not store.stop_following("")
    store.follow_series("a@example.org", "parasha")
    store.follow_series("a@example.org", "parasha", False)
    report = series.announce(
        store, ConsoleMailer(io.StringIO()), "https://targum.page", [PORTION], pause=0
    )
    assert report.sent == []
