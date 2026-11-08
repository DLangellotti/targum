"""A course's playlist holds the whole course (design.md §12, 2026-11-07).

One book, one playlist: a playlist whose every text is a lesson of one course may hold up
to `MOST_IN_COURSE`; every other playlist keeps `MOST_IN_PLAYLIST`. The course here is
made up, and so are its lessons.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from targum import serve
from targum.accounts import MOST_IN_COURSE, MOST_IN_PLAYLIST, Person, Store, playlist_most
from targum.kinds import course_book
from targum.remembered import Remembered

BOOK = "made-up-course"
OTHER = "another-made-up-course"


def lesson(book: str, n: int) -> str:
    return f"course:xx:{book}:{n}"


def a_store(tmp_path: Path) -> tuple[Store, int]:
    store = Store(tmp_path / "targum.db")
    one = store.finish_sign_in(store.start_sign_in("one@example.com"))
    assert one is not None
    return store, one[0].id


def a_library(tmp_path: Path) -> serve.Library:
    library = serve.Library.__new__(serve.Library)
    library.shared = tmp_path / "shared"
    library.remembered = Remembered()
    library.jobs = {}  # type: ignore[assignment]
    return library


def a_text(home: Path, name: str, source: str) -> str:
    (home / name).mkdir(parents=True)
    (home / name / "document.json").write_text(
        json.dumps({"title": name, "language": "xx", "source": source, "blocks": []}),
        encoding="utf-8",
    )
    return name


def fill(
    store: Store, library: serve.Library, home: Path, me: int, pid: int, names: list[str]
) -> list[bool]:
    """Add each text the way the page does: ask the rule, then the store."""
    added = []
    for name in names:
        found = store.playlist(me, pid) or {}
        most = library.playlist_most(home, found, name)
        added.append(store.add_to_playlist(me, pid, name, reader=name, most=most) is not None)
    return added


# --- the rule ----------------------------------------------------------------------


def test_a_course_lesson_names_its_book() -> None:
    assert course_book(lesson(BOOK, 3)) == BOOK
    assert course_book("COURSE:xx:Made-Up-Course:3") == BOOK
    for not_one in ("", "https://example.com/a:1", "course:xx:made-up-course", "sefaria:Ruth.1"):
        assert course_book(not_one) == ""


def test_only_one_whole_course_is_held_past_twenty() -> None:
    assert playlist_most([lesson(BOOK, n) for n in range(1, 30)]) == MOST_IN_COURSE
    assert playlist_most([lesson(BOOK, 1), lesson(OTHER, 2)]) == MOST_IN_PLAYLIST
    assert playlist_most([lesson(BOOK, 1), "https://example.com/news"]) == MOST_IN_PLAYLIST
    assert playlist_most([lesson(BOOK, 1), None]) == MOST_IN_PLAYLIST, "a text still being made"
    assert playlist_most([]) == MOST_IN_PLAYLIST


def test_the_store_never_holds_more_than_a_course(tmp_path: Path) -> None:
    store, me = a_store(tmp_path)
    pid = int((store.make_playlist(me, "x") or {})["id"])
    for n in range(MOST_IN_COURSE):
        assert store.add_to_playlist(me, pid, f"t{n}", reader=f"r{n}", most=10_000) is not None
    assert store.add_to_playlist(me, pid, "one more", reader="r-more", most=10_000) is None


# --- through the library, as the page and the tools ask ----------------------------


def test_a_course_goes_past_twenty(tmp_path: Path) -> None:
    store, me = a_store(tmp_path)
    library, home = a_library(tmp_path), tmp_path / "home"
    names = [a_text(home, f"lesson-{n:02d}", lesson(BOOK, n)) for n in range(1, 31)]
    pid = int((store.make_playlist(me, "The made-up course") or {})["id"])
    assert all(fill(store, library, home, me, pid, names))
    found = store.playlist(me, pid) or {}
    assert [item["reader"] for item in found["items"]] == names, "in the book's order"
    assert library.playlist_most(home, found) == MOST_IN_COURSE


def test_a_mixed_playlist_stops_at_twenty(tmp_path: Path) -> None:
    store, me = a_store(tmp_path)
    library, home = a_library(tmp_path), tmp_path / "home"
    names = [a_text(home, f"lesson-{n:02d}", lesson(BOOK, n)) for n in range(1, 21)]
    news = a_text(home, "the-news", "https://example.com/news/1")
    pid = int((store.make_playlist(me, "Mixed") or {})["id"])
    assert all(fill(store, library, home, me, pid, names))
    assert fill(store, library, home, me, pid, [news]) == [False], "not a lesson, past twenty"
    late = a_text(home, "lesson-21", lesson(BOOK, 21))
    pid2 = int((store.make_playlist(me, "Mixed early") or {})["id"])
    assert all(fill(store, library, home, me, pid2, [news, *names[:19]]))
    assert fill(store, library, home, me, pid2, [late]) == [False], "a mixed one stays twenty"


def test_two_courses_in_one_playlist_stop_at_twenty(tmp_path: Path) -> None:
    store, me = a_store(tmp_path)
    library, home = a_library(tmp_path), tmp_path / "home"
    mine = [a_text(home, f"a-{n:02d}", lesson(BOOK, n)) for n in range(1, 11)]
    theirs = [a_text(home, f"b-{n:02d}", lesson(OTHER, n)) for n in range(1, 13)]
    pid = int((store.make_playlist(me, "Two books") or {})["id"])
    assert fill(store, library, home, me, pid, [*mine, *theirs]) == [True] * 20 + [False] * 2


def test_a_text_still_being_made_holds_a_course_to_twenty(tmp_path: Path) -> None:
    """A course's playlist past twenty holds only texts already made, so its one press
    has nothing to claim."""
    store, me = a_store(tmp_path)
    library, home = a_library(tmp_path), tmp_path / "home"
    names = [a_text(home, f"lesson-{n:02d}", lesson(BOOK, n)) for n in range(1, 22)]
    pid = int((store.make_playlist(me, "Waiting") or {})["id"])
    store.add_to_playlist(me, pid, "Something being made", job="job-1")
    added = fill(store, library, home, me, pid, names)
    assert added == [True] * 19 + [False] * 2
    big = int((store.make_playlist(me, "Made") or {})["id"])
    assert all(fill(store, library, home, me, big, names))
    found = store.playlist(me, big) or {}
    assert len(found["items"]) == 21 and not any(item["job"] for item in found["items"])
    assert library.playlist_most(home, found, job="job-2") == MOST_IN_PLAYLIST


# --- the chat and the connector ----------------------------------------------------


def test_a_model_adds_a_course_past_twenty_and_nothing_else(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from targum import level
    from targum.chat import tools

    store, me = a_store(tmp_path)
    library, home = a_library(tmp_path), tmp_path / "home"
    names = [a_text(home, f"lesson-{n:02d}", lesson(BOOK, n)) for n in range(1, 23)]
    news = a_text(home, "the-news", "https://example.com/news/1")
    shelf = [{"name": name, "title": name} for name in [*names, news]]
    monkeypatch.setattr(tools, "_shelf", lambda ctx: (shelf, []))
    ctx = tools.Ctx(
        person=Person(id=me, email="one@example.com"),
        home=home,
        library=library,
        store=store,
        chat_id="",
        level=level.EMPTY,
        press_at="",
    )
    for name in names:
        assert tools.add_to_playlist(ctx, {"playlist": "Course", "text": name}).get("added")
    refused = tools.add_to_playlist(replace(ctx), {"playlist": "Course", "text": news})
    assert refused["error"] == "That playlist holds 20 texts, the most it can. Start another."
    pid = int(store.playlists(me)[0]["id"])
    assert len((store.playlist(me, pid) or {})["items"]) == 22
