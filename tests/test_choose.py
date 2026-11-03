"""One chooser for what to read next, on running words (design.md §12, "What to read next
is chosen on running words", 2026-10-31; targum-internal#612)."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from targum import catalogue as catalogue_module
from targum import choose
from targum import estimate as estimate_module
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
        person_id = 1

    # Marks alone, as Phase 0 chose: the estimate's own tests are below.
    monkeypatch.setattr(
        estimate_module,
        "for_reader",
        lambda store, person_id, language, level=None: estimate_module.Estimate(
            "he", 0.0, {}, ranked=False
        ),
    )
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


# -- learning value (design.md §12, "What to read next teaches words that come back",
# 2026-11-01; targum-internal#614) ---------------------------------------------------------


@pytest.fixture
def teaching(library: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    """Two texts inside the aim, one whose new word comes round and one whose new words
    are each met once, and a lexicon that says what each is about."""
    from targum import learning
    from targum.finds import interests

    ctx, _, _ = library
    entries = [entry("once-story"), entry("again-story", kind="essay"), entry("food-talk", "talk")]
    lemmas = tmp_path / "teaching.json"
    write_index(
        lemmas,
        index_of(
            {
                # 96% known; four new words, each met once.
                "once-story": {"ים": 96, "ספר": 1, "שולחן": 1, "חתול": 1, "כלב": 1},
                # 95% known; one new word, met five times.
                "again-story": {"ים": 95, "ספר": 5},
                # 95% known; one new word met five times, on food.
                "food-talk": {"ים": 95, "לחם": 5},
            }
        ),
    )
    monkeypatch.setattr(catalogue_module, "everything", lambda: list(entries))
    monkeypatch.setattr(catalogue_module, "lemmas_path", lambda: lemmas)
    weights = {word: 0.001 for word in ("ספר", "שולחן", "חתול", "כלב", "לחם")}
    monkeypatch.setattr(learning, "usefulness", lambda language: learning.Usefulness("he", weights))
    lexicon = interests.from_lemmas({"לחם": ["food"], "ספר": ["school"]}, ["food", "school"])
    monkeypatch.setattr(interests, "lexicon", lambda file=None: lexicon)
    learning.forget()
    return ctx, entries, lemmas


def test_inside_the_aim_the_text_whose_new_words_come_back_comes_first(teaching: Any) -> None:
    ctx, _, _ = teaching
    got = tools.suggest_next(ctx, {"limit": 3})["suggestions"]
    ids = [row["id"] for row in got]
    assert ids[-1] == "once-story", "four words met once teach less than one met five times"
    assert all(row["fit"] == "band" for row in got)
    assert got[0]["learn"] > 0 and got[-1]["learn"] == 0
    assert {row["id"]: row.get("about") for row in got}["food-talk"] == ["food"]


def test_something_else_changes_topic_too(teaching: Any) -> None:
    ctx, _, _ = teaching
    first = tools.suggest_next(ctx, {"limit": 1})["suggestions"][0]["id"]
    other = tools.suggest_next(ctx, {"limit": 1, "instead_of": first})["suggestions"][0]
    assert other["id"] != first
    assert other.get("about") != tools.suggest_next(ctx, {"limit": 1})["suggestions"][0].get(
        "about"
    )


def test_progress_weighs_what_a_text_teaches_as_home_does(teaching: Any) -> None:
    from targum import touchstones
    from targum.coverage import read_index

    ctx, entries, lemmas = teaching
    index = read_index(lemmas)
    marked = ctx.store.marked(None, "he")
    taught = tools.teaching(None, None, "he", index, index.statuses(marked), None, {}, set())
    listed = touchstones.at_level(entries, index, marked, "he", limit=10, taught=taught)
    home = [row["id"] for row in tools.suggest_next(ctx, {"limit": 10})["suggestions"]]
    assert [row["id"] for row in listed] == home


def test_under_answers_only_the_real_texts_under_the_floor(library: Any) -> None:
    """Home's "Show me something harder" (design.md §12, 2026-11-02) ranks from these;
    Read next itself is never asked for them."""
    ctx, _, _ = library
    got = tools.suggest_next(ctx, {"under": True, "limit": 200})["suggestions"]
    assert [row["id"] for row in got] == ["hard-story"]
    assert got[0]["fit"] == choose.UNDER


# -- an older Hebrew waits until it is asked for (design.md §12, 2026-11-03) --------------


def older(id_: str, register: str, kind: str = "prose") -> catalogue_module.Entry:
    return catalogue_module._entry(
        {
            "id": id_,
            "title": id_,
            "language": "he",
            "source": f"test:{id_}",
            "kind": kind,
            "register": register,
            "words": 100,
            "difficulty": 10,
        }
    )


@pytest.fixture
def registers(library: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    """The beta review's B1 reader abroad (2026-11-03): modern texts in the band and
    under it, and Esther, Kings and Brenner rated in the band by an estimate that reads
    every word off the modern frequency list."""
    ctx, _, _ = library
    entries = [
        entry("news-story"),  # 95%, in the aim
        entry("hard-story", difficulty=40),  # 50%, under the floor
        older("esther", "biblical"),  # 96%: the estimate's figure, not a reader's
        older("ii-kings", "biblical"),  # 93%
        older("brenner-asonot", "revival", kind="story"),  # 94%
    ]
    lemmas = tmp_path / "registers.json"
    write_index(
        lemmas,
        index_of(
            {
                "news-story": {"ים": 19, "ספר": 1},
                "hard-story": {"ים": 1, "ספר": 1},
                "esther": {"ים": 24, "ספר": 1},
                "ii-kings": {"ים": 13, "ספר": 1},
                "brenner-asonot": {"ים": 47, "ספר": 3},
            }
        ),
    )
    monkeypatch.setattr(catalogue_module, "everything", lambda: list(entries))
    monkeypatch.setattr(catalogue_module, "lemmas_path", lambda: lemmas)
    said: list[str] = []

    class Store:
        def marked(self, person: Any, language: str) -> dict[str, int]:
            return {"ים": KNOWN, "בית": KNOWN}

        def interest(self, person_id: Any) -> tuple[str, ...]:
            return tuple(said)

    ctx.store = Store()
    return ctx, entries, lemmas, said


def test_a_modern_reader_is_never_offered_the_tanakh_as_at_their_level(registers: Any) -> None:
    """F-01: the card offered Esther and II Kings "where you already know 90%", and
    Something else walked on to Haggai, Ecclesiastes, Brenner and Genesis. A modern text
    under the floor now comes before them."""
    ctx, _, _, _ = registers
    got = tools.suggest_next(ctx, {"limit": 5})["suggestions"]
    ids = [row["id"] for row in got]
    assert ids[:2] == ["news-story", "hard-story"], ids
    assert {row["id"] for row in got if row.get("held")} == {"esther", "ii-kings", "brenner-asonot"}
    walked = []
    shown = "news-story"
    for _ in range(3):
        pick = tools.suggest_next(ctx, {"limit": 1, "instead_of": shown, "skip": walked})
        shown = pick["suggestions"][0]["id"]
        walked.append(shown)
    assert walked[0] == "hard-story", "Something else stays in modern Hebrew while it can"


def test_torah_and_judaism_opens_the_tanakh_and_not_the_revival(registers: Any) -> None:
    ctx, _, _, said = registers
    said.append("judaism")
    got = tools.suggest_next(ctx, {"limit": 5})["suggestions"]
    fits = [row["id"] for row in got if row["fit"] == "band" and not row.get("held")]
    assert set(fits) == {"news-story", "esther", "ii-kings"}
    assert [row["id"] for row in got if row.get("held")] == ["brenner-asonot"]


def test_a_register_asked_for_by_name_or_opened_before_is_open(registers: Any) -> None:
    ctx, _, _, _ = registers
    named = tools.suggest_next(ctx, {"limit": 5, "register": "revival"})["suggestions"]
    assert [row["id"] for row in named] == ["brenner-asonot"] and not named[0].get("held")
    opened = tools.suggest_next(ctx, {"limit": 5, "skip": ["ii-kings"]})["suggestions"]
    assert not any(row.get("held") for row in opened if row["id"] == "esther"), (
        "a reader who opened II Kings has asked for the Tanakh"
    )


def test_progress_never_lists_an_older_hebrew_the_reader_has_not_asked_for(
    registers: Any,
) -> None:
    """F-02: "Texts at your level now" listed Esther and II Kings."""
    from targum import touchstones
    from targum.coverage import read_index

    ctx, entries, lemmas, _ = registers
    marked = ctx.store.marked(None, "he")
    index = read_index(lemmas)
    modern = choose.opened((), ())
    listed = touchstones.at_level(entries, index, marked, "he", limit=10, registers=modern)
    assert [row["id"] for row in listed] == ["news-story"]
    scripture = choose.opened(("judaism",), ())
    listed = touchstones.at_level(entries, index, marked, "he", limit=10, registers=scripture)
    assert {row["id"] for row in listed} == {"news-story", "esther", "ii-kings"}


def test_a_waiting_text_comes_after_every_other_tier() -> None:
    assert choose.key(None) < choose.key(0.95, waits=True)
    assert choose.key(0.2) < choose.key(0.95, waits=True)
    assert choose.held("biblical", frozenset()) and not choose.held("modern", frozenset())
    assert not choose.held("biblical", choose.opened(("judaism",)))
    assert choose.held("revival", choose.opened(("judaism", "stories")))
