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


def test_an_instalment_names_the_document_its_reader_is(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    """Learn's subscriptions menu marks an instalment read through (2026-09-11), which it
    can only do if the series names the document the way the reader does: the content
    hash off `document.json` beside the reader, and how many sections it has. A folder
    with no document says nothing rather than something wrong."""
    import json

    from targum import series
    from targum.weekly.models import Edition, Issue, Level, folder

    issue = Issue(
        id="2026-09-07",
        dated="2026-09-07",
        title="מבט השבוע",
        editions=[
            Edition(level=Level.aleph, entry_id="e", folder="f", ok=True),
            Edition(level=Level.bet, entry_id="g", folder="h", ok=True),
        ],
    )
    built = tmp_path / folder("2026-09-07", Level.aleph)
    (built / "reader").mkdir(parents=True)
    (built / "document.json").write_text(json.dumps({"content_hash": "abc123"}), encoding="utf-8")
    for n in (1, 2, 3):
        (built / "reader" / f"sec-000{n}.html").write_text("<p>", encoding="utf-8")
    monkeypatch.setattr("targum.weekly.index.readable", lambda: [issue])
    monkeypatch.setattr("targum.weekly.index.root", lambda: tmp_path)
    aleph, bet = series.current(public=False)[0]["instalment"]["levels"]
    assert aleph["document"] == "abc123" and aleph["sections"] == 3
    assert "document" not in bet and "sections" not in bet, "nothing built: nothing said"


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
    "name": "Mishnah Yomit",
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
    ((email, stop, said),) = store.followers("parasha")
    assert email == "a@example.org" and store.series_followed("a@example.org") == ["parasha"]
    assert said == "en", "nobody said a language, so it is the one targum is written in"
    assert store.stop_following(stop) and store.followers("parasha") == []
    assert store.series_followed("a@example.org") == []
    assert not store.stop_following("nonsense") and not store.stop_following("")
    store.follow_series("a@example.org", "parasha")
    store.follow_series("a@example.org", "parasha", False)
    report = series.announce(
        store, ConsoleMailer(io.StringIO()), "https://targum.page", [PORTION], pause=0
    )
    assert report.sent == []


# -- a series says its name in the reader's language (targum-internal#289) --------------


def test_a_series_row_is_said_in_the_readers_language() -> None:
    """The follow page drew "Weekly News Digest" beside a Russian interface. The names and
    blurbs were hard-coded English in `series.py` and `daily/cycles.py`, so they were the
    one row on that page that could not be anything else."""
    from targum import series

    row = {
        "id": "weekly",
        "name": "Weekly News Digest",
        "hebrew": "מבט השבוע",
        "what": "Hebrew news, written three ways, every week.",
        "page": "/weekly",
    }

    english = series.said_in(row, "en")
    assert english["name"] == "Weekly News Digest"
    assert english["what"].startswith("Hebrew news")

    russian = series.said_in(row, "ru")
    assert russian["name"] == "Недельный обзор новостей"
    assert russian["what"].startswith("Новости")
    assert series.said_in(row, "ru-RU") == russian, "a regional tag is the language"

    # The Hebrew name is the series' name in Hebrew and stays Hebrew in every language.
    assert russian["hebrew"] == "מבט השבוע"
    # And nothing else about the row moves.
    assert russian["page"] == "/weekly"


def test_a_series_with_nothing_written_for_it_keeps_its_english() -> None:
    """English beside it is never wrong, only foreign — the same fallback the catalogue's
    own names make."""
    from targum import series

    row = {"id": "nobody-wrote-this", "name": "A Series", "what": "What it is."}
    for language in ("ru", "fr", "xx"):
        assert series.said_in(row, language) == row


def test_every_cycle_and_series_has_its_words_in_the_catalogue() -> None:
    """Asked of the list rather than of a hand-written set, so a cycle added later is
    covered the day it is added rather than the day somebody notices."""
    from targum.daily.cycles import CYCLES
    from targum.strings import catalogue

    english = catalogue("en")
    for slug in [cycle.slug for cycle in CYCLES] + ["weekly", "parasha"]:
        for part in ("name", "what"):
            assert f"series.{slug}.{part}" in english, f"series.{slug}.{part}"


# -- and the mail, and the page it leads to (targum-internal#289) -----------------------


PORTION_RU = {
    "id": "parasha",
    "name": "The weekly portion",
    "what": "This Shabbat's reading, with its cantillation, every week.",
    "page": "/parasha",
    "instalment": {"id": "bereshit", "title": "Bereshit", "hebrew": "בראשית"},
}


def test_a_follower_is_written_down_with_the_language_they_followed_in(tmp_path: Any) -> None:
    """There is no account behind a follow row — it is keyed by address so that stopping
    never touches one — so the press is the only moment the language can be learnt."""
    from targum.accounts import Store

    store = Store(tmp_path / "words.db")
    store.follow_series("r@example.org", "parasha", language="ru-RU")
    ((_, stop, said),) = store.followers("parasha")
    assert said == "ru", "a regional tag is the language"
    assert store.following_language(stop) == "ru"

    # Following again in another language means the new one; stopping does not forget it,
    # so somebody who comes back is still read in what they last said.
    store.follow_series("r@example.org", "parasha", language="en")
    assert store.following_language(stop) == "en"
    store.follow_series("r@example.org", "parasha", False)
    assert store.following_language(stop) == "en"

    # A token matching no row is English rather than an error: it is a link out of a mail
    # client, and the page it opens has to draw either way.
    assert store.following_language("nonsense") == "en" and store.following_language("") == "en"


def test_the_letter_is_written_in_the_language_its_reader_follows_in() -> None:
    """The last thing in this file still English for everybody, on a series whose name and
    blurb the same reader already had in Russian."""
    from targum import series

    subject, body = series.letter(PORTION_RU, "https://targum.page", "tok", "ru")
    assert "Недельная глава" in subject and "Bereshit" in subject
    assert "Уже на targum: https://targum.page/parasha" in body
    assert "https://targum.page/series/stop?t=tok" in body
    assert "You are getting this" not in body

    english = series.letter(PORTION_RU, "https://targum.page", "tok")[1]
    assert "You are getting this because you follow The weekly portion" in english


def test_one_russian_follower_does_not_make_everyone_elses_letter_russian() -> None:
    """The series is read once for everybody and its name is resolved into *somebody's*
    language before `announce` loops. A letter that took the row's name as given would say
    the Russian name to every English reader as soon as a Russian follower sorted first.
    """
    from targum import series

    already = series.said_in(PORTION_RU, "ru")
    assert already["name"] == "Недельная глава"
    subject, body = series.letter(already, "https://targum.page", "tok", "en")
    assert "The weekly portion" in subject and "Недельная глава" not in body
