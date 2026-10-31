"""One chooser for what to read next, on running words (design.md §12, "What to read next
is chosen on running words", 2026-10-31; targum-internal#612)."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from targum import catalogue as catalogue_module
from targum import choose
from targum import level as level_module
from targum.chat import tools
from targum.coverage import IGNORED, KNOWN, build_index, write_index


def index_of(texts: dict[str, dict[str, int]]) -> Any:
    return build_index({entry: list(counts) for entry, counts in texts.items()}, texts)


# -- running words ---------------------------------------------------------------------


def test_running_coverage_weighs_a_word_by_how_often_it_comes_round() -> None:
    """One word known that is nine of a text's ten running words is 90% of it, where the
    distinct count says half."""
    index = index_of({"t": {"ים": 9, "בית": 1}})
    marked = {"ים": KNOWN}
    running = index.running("t", marked)
    assert running is not None and running.known == 0.9 and running.total == 10
    assert running.fresh == 1, "בית is not on the list"
    distinct = index.against("t", marked)
    assert distinct is not None and distinct.known == 0.5


def test_running_coverage_leaves_out_ignored_words_and_prefix_letters() -> None:
    """A word set aside as not vocabulary comes out of the total, as it does from the
    distinct share; a one-letter clitic is never a word to learn and never counted."""
    index = index_of({"t": {"ים": 6, "בית": 2, "ו": 40, "ספר": 2}})
    running = index.running("t", {"ים": KNOWN, "ספר": IGNORED})
    assert running is not None and running.total == 8 and running.known == 0.75


def test_running_coverage_is_not_measured_where_nothing_was_counted() -> None:
    index = build_index({"t": ["ים"]})  # no tallies: indexed, never counted
    assert index.running("t", {"ים": KNOWN}) is None
    assert index.running("absent", {}) is None


def test_the_statuses_walk_answers_what_the_lookup_answers() -> None:
    index = index_of({"t": {"ים": 3, "בית": 1}, "u": {"ספר": 2, "ים": 2}})
    marked = {"ים": KNOWN, "ספר": 2, "nowhere": KNOWN}
    held = index.statuses(marked)
    for entry in ("t", "u"):
        assert index.running(entry, marked, held) == index.running(entry, marked)


# -- the band ----------------------------------------------------------------------------


def test_a_text_at_99_percent_never_outranks_one_at_95() -> None:
    assert choose.key(0.95) < choose.key(0.996)
    assert choose.key(0.95) < choose.key(0.99), "inside the band, the aim is nearer"
    assert choose.key(0.91) < choose.key(0.999)


def test_inside_the_band_the_aim_comes_first() -> None:
    order = sorted([0.90, 0.99, 0.955, 0.93, 0.975], key=choose.key)
    assert order[0] == 0.955
    assert order.index(0.93) < order.index(0.90)


def test_a_real_text_comes_before_a_scene_when_both_fit() -> None:
    assert choose.key(0.91) < choose.key(0.95, scene=True)
    # Under the floor nothing fits, and the nearer comes first whatever it is.
    assert choose.key(0.85, scene=True) < choose.key(0.80)


def test_under_the_floor_is_offered_before_too_easy_and_unmeasured_last() -> None:
    assert choose.key(0.95) < choose.key(0.5) < choose.key(1.0) < choose.key(None, gentle=12)
    assert choose.key(None, gentle=12) < choose.key(None)
    assert [choose.fit(s) for s in (0.89, 0.9, 0.995, None)] == [
        choose.UNDER,
        choose.BAND,
        choose.EASY,
        choose.UNMEASURED,
    ]


def test_something_else_is_another_kind_in_the_same_tier_never_a_worse_one() -> None:
    def row(kind: str, collection: str = "") -> dict[str, Any]:
        return {"kind": kind, "collection": collection, "register": "modern"}

    ranked = [
        (choose.key(0.95), row("story")),
        (choose.key(0.93), row("story")),
        (choose.key(0.92), row("talk")),
        (choose.key(0.5), row("poetry")),
    ]
    assert choose.alternative(ranked, ("story", "modern")) == 2
    # Nothing else of another kind in the band: the next best, not the poem under it.
    assert choose.alternative(ranked[:2] + ranked[3:], ("story", "modern")) == 0


# -- the two places that choose ------------------------------------------------------------


def entry(id_: str, kind: str = "story", difficulty: int = 10) -> catalogue_module.Entry:
    return catalogue_module._entry(
        {
            "id": id_,
            "title": id_,
            "language": "he",
            "source": f"test:{id_}",
            "kind": kind,
            "register": "modern",
            "words": 100,
            "difficulty": difficulty,
        }
    )


@pytest.fixture
def library(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    """Four catalogue texts, an index with counts, and a reader who knows ים and בית."""
    entries = [
        entry("easy-story"),  # all known: too easy
        entry("band-story"),  # 95%
        entry("band-talk", kind="talk"),  # 92%
        entry("scene-01-nice-to-meet-you", kind="dialogue"),  # a scene at 96%
        entry("hard-story", difficulty=40),  # 50%
    ]
    lemmas = tmp_path / "lemmas.json"
    write_index(
        lemmas,
        index_of(
            {
                "easy-story": {"ים": 10, "בית": 10},
                "band-story": {"ים": 15, "בית": 4, "ספר": 1},
                "band-talk": {"ים": 20, "בית": 3, "ספר": 2},
                "scene-01-nice-to-meet-you": {"ים": 24, "ספר": 1},
                "hard-story": {"ים": 1, "ספר": 1},
            }
        ),
    )
    monkeypatch.setattr(catalogue_module, "everything", lambda: list(entries))
    monkeypatch.setattr(catalogue_module, "lemmas_path", lambda: lemmas)
    monkeypatch.setattr(tools, "_collections", lambda: {})
    monkeypatch.setattr(tools, "_shelf", lambda ctx, measured=True: ([], []))

    class Store:
        def marked(self, person: Any, language: str) -> dict[str, int]:
            return {"ים": KNOWN, "בית": KNOWN}

    class Ctx:
        level = replace(level_module.EMPTY, language="he")
        store = Store()
        person = object()

    return Ctx(), entries, lemmas


def test_home_offers_the_text_in_the_band_never_the_one_known_through(library: Any) -> None:
    ctx, _, _ = library
    got = tools.suggest_next(ctx, {"limit": 5})["suggestions"]
    ids = [row["id"] for row in got]
    assert ids[:3] == ["band-story", "band-talk", "scene-01-nice-to-meet-you"], (
        "nearest the aim first, then the band's edge, and the scene after the real texts"
    )
    assert ids.index("hard-story") < ids.index("easy-story"), "a stretch before nothing new"
    top = got[0]
    assert top["fit"] == "band" and top["running_share"] == 0.95
    assert top["distinct_share"] == round(2 / 3, 4), "the old figure, kept beside it"
    assert top["because"] == "You know 95% of the words here."


def test_something_else_sets_the_text_aside_for_another_kind(library: Any) -> None:
    ctx, _, _ = library
    got = tools.suggest_next(ctx, {"limit": 1, "instead_of": "band-story"})["suggestions"]
    assert got[0]["id"] == "band-talk", "a talk, not another story"
    again = tools.suggest_next(
        ctx, {"limit": 1, "instead_of": "band-talk", "skip": ["band-story"]}
    )["suggestions"]
    assert again[0]["id"] == "scene-01-nice-to-meet-you"


def test_progress_lists_what_home_would_offer_in_the_same_order(library: Any) -> None:
    from targum import touchstones
    from targum.coverage import read_index

    ctx, entries, lemmas = library
    marked = ctx.store.marked(None, "he")
    listed = touchstones.at_level(entries, read_index(lemmas), marked, "he", limit=10)
    home = [row["id"] for row in tools.suggest_next(ctx, {"limit": 10})["suggestions"]]
    assert [row["id"] for row in listed] == [one for one in home if one != "hard-story"]
    assert [row["known"] for row in listed] == [95, 92, 96, 100]


def test_candidates_come_from_a_list_of_sources_and_say_which(
    library: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """#619 plugs a fresh find in as a second source; its rows say so, and a text two
    sources offer is the first's."""
    ctx, entries, _ = library
    found = entry("found-story")
    monkeypatch.setattr(
        tools,
        "CANDIDATE_SOURCES",
        [*tools.CANDIDATE_SOURCES, ("find", lambda ctx: [found, entries[1]])],
    )
    got = tools.suggest_next(ctx, {"limit": 10})["suggestions"]
    origins = {row["id"]: row["origin"] for row in got}
    assert origins["found-story"] == "find" and origins["band-story"] == "shelf"
    assert set(origins.values()) <= set(choose.ORIGINS)
