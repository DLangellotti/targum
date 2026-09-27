"""targum's own playlists on the shared shelf (targum-internal#368; design.md §12, "A
playlist is swiped, and one press takes the set", 2026-09-23).

A swipe collection in the catalogue file, whose members are built once on the shared
shelf, opened by a reader as a playlist of their own for nothing — and the same copy the
second time, whatever language the interface was in.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest

from targum import catalogue
from targum.accounts import MOST_IN_PLAYLIST, Store
from targum.serve import Library


def entry(n: int) -> catalogue.Entry:
    return catalogue._entry(
        {
            "id": f"reel-{n}",
            "title": f"סרטון {n}",
            "english": f"Reel {n}",
            "language": "he",
            "source": f"video:reel-{n}",
        }
    )


def built(shared: Path, n: int) -> None:
    folder = shared / f"reel-{n}"
    (folder / "reader").mkdir(parents=True)
    (folder / "reader" / "index.html").write_text("<html></html>", encoding="utf-8")
    (folder / "document.json").write_text(
        json.dumps({"source": f"video:reel-{n}", "title": f"סרטון {n}"}), encoding="utf-8"
    )


@pytest.fixture
def shelf(tmp_path: Path) -> Iterator[tuple[Library, int, int]]:
    """A box with a kitchen set of five, three of them built, and two signed-in readers."""
    entries, collections = list(catalogue.CATALOGUE), list(catalogue.COLLECTIONS)
    catalogue.CATALOGUE[:] = [entry(n) for n in range(5)]
    catalogue.COLLECTIONS[:] = [
        catalogue._collection(
            {
                "id": "kitchen",
                "title": "במטבח",
                "english": "In the kitchen",
                "named": {"ru": "На кухне"},
                "members": [f"reel-{n}" for n in range(5)],
                "swipe": True,
            }
        ),
        catalogue._collection(
            {"id": "torah", "title": "תורה", "english": "Torah", "members": ["reel-0", "reel-1"]}
        ),
    ]
    store = Store(tmp_path / "targum.db")
    one = store.finish_sign_in(store.start_sign_in("one@example.com"))
    two = store.finish_sign_in(store.start_sign_in("two@example.com"))
    assert one is not None and two is not None
    library = Library(tmp_path / "out", store=store)
    for n in (0, 2, 4):
        built(library.shared, n)
    try:
        yield library, one[0].id, two[0].id
    finally:
        catalogue.CATALOGUE[:] = entries
        catalogue.COLLECTIONS[:] = collections


def test_the_flag_is_read_and_defaults_off() -> None:
    """An older catalogue file, with no `swipe` anywhere, loads exactly as it did."""
    plain = catalogue._collection({"id": "a", "title": "א"})
    assert plain.swipe is False and plain.state()["swipe"] is False
    marked = catalogue._collection({"id": "b", "title": "ב", "swipe": True})
    assert marked.swipe is True and marked.state()["swipe"] is True


def test_only_swipe_collections_are_offered_and_only_what_is_built(
    shelf: tuple[Library, int, int],
) -> None:
    library, _, _ = shelf
    offered = library.targum_sets()
    assert [collection.id for collection, _ in offered] == ["kitchen"]
    assert [folder for _, folder in offered[0][1]] == ["reel-0", "reel-2", "reel-4"]


def test_opening_one_copies_it_and_claims_nothing(shelf: tuple[Library, int, int]) -> None:
    library, me, _ = shelf
    assert library.store is not None
    before = library.store.committed(0, owner=me)
    opened = library.open_targum_set(me, "kitchen", "en")
    assert opened["name"] == "In the kitchen" and opened["made_by"] == "targum"
    assert [item["reader"] for item in opened["items"]] == ["reel-0", "reel-2", "reel-4"]
    assert all(item["job"] is None for item in opened["items"])
    assert library.store.committed(0, owner=me) == before, "nothing was claimed"
    assert not library.jobs, "nothing was made"


def test_opening_it_again_is_the_same_copy_in_any_language(
    shelf: tuple[Library, int, int],
) -> None:
    library, me, _ = shelf
    assert library.store is not None
    first = library.open_targum_set(me, "kitchen", "en")
    again = library.open_targum_set(me, "kitchen", "ru")
    assert again["id"] == first["id"]
    assert len(library.store.playlists(me)) == 1


def test_another_reader_gets_a_copy_of_their_own(shelf: tuple[Library, int, int]) -> None:
    library, me, them = shelf
    mine = library.open_targum_set(me, "kitchen", "en")
    theirs = library.open_targum_set(them, "kitchen", "ru")
    assert theirs["id"] != mine["id"] and theirs["name"] == "На кухне"
    assert library.store is not None and library.store.playlist(me, int(theirs["id"])) is None


def test_a_set_this_box_does_not_offer_is_unknown(shelf: tuple[Library, int, int]) -> None:
    library, me, _ = shelf
    assert library.open_targum_set(me, "torah", "en") == {"error": "unknown"}
    assert library.open_targum_set(me, "nothing", "en") == {"error": "unknown"}


def test_a_set_holds_a_playlist_s_worth(shelf: tuple[Library, int, int]) -> None:
    library, me, _ = shelf
    catalogue.CATALOGUE[:] = [entry(n) for n in range(MOST_IN_PLAYLIST + 3)]
    for n in range(5, MOST_IN_PLAYLIST + 3):
        built(library.shared, n)
    catalogue.COLLECTIONS[:] = [
        catalogue._collection(
            {
                "id": "long",
                "title": "ארוך",
                "english": "Long",
                "members": [f"reel-{n}" for n in range(MOST_IN_PLAYLIST + 3)],
                "swipe": True,
            }
        )
    ]
    opened = library.open_targum_set(me, "long", "en")
    assert len(opened["items"]) == MOST_IN_PLAYLIST
