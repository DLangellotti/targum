"""What a text would teach one reader: new words that come back (design.md §12, "What to
read next teaches words that come back", 2026-11-01; targum-internal#614)."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

from targum import choose, learning
from targum.coverage import IGNORED, KNOWN, build_index
from targum.finds.interests import from_lemmas


@pytest.fixture(autouse=True)
def fresh() -> Iterator[None]:
    learning.forget()
    yield
    learning.forget()


def index_of(texts: dict[str, dict[str, int]]) -> Any:
    return build_index({entry: list(counts) for entry, counts in texts.items()}, texts)


#: Everyday words with a rate per million each; anything else is not on the yardstick.
USEFUL = learning.Usefulness(
    "he", {"ספר": 0.001, "בית": 0.001, "ים": 0.001, "חתול": 0.00001, "שולחן": 0.001}
)


def score(index: Any, entry: str, marked: dict[str, int] | None = None, **kwargs: Any) -> float:
    held = index.statuses(marked or {})
    who = learning.reader(index, held, None, kwargs.pop("met", ()), kwargs.pop("liked", ()))
    got = learning.value(index, entry, who, learning.useful_table(index, USEFUL), **kwargs)
    assert got is not None
    return got


def test_a_word_met_once_teaches_nothing_and_three_times_teaches_most() -> None:
    assert [learning.repeat(n) for n in (1, 2, 3, 9)] == [0.0, 0.5, 1.0, 1.0]
    index = index_of({"once": {"ים": 99, "ספר": 1}, "thrice": {"ים": 97, "ספר": 3}})
    marked = {"ים": KNOWN}
    assert score(index, "once", marked) == 0.0
    assert score(index, "thrice", marked) == pytest.approx(1.0)  # 1 word per 100


def test_a_word_known_ignored_or_rare_teaches_nothing() -> None:
    index = index_of({"t": {"ים": 90, "ספר": 5, "חתול": 0, "זנב": 5}})
    assert score(index, "t", {"ים": KNOWN, "ספר": KNOWN}) == 0.0, "זנב is on no yardstick"
    assert score(index, "t", {"ים": KNOWN, "ספר": IGNORED}) == 0.0
    # A word being learned is certainly unknown, whatever the estimate says.
    assert score(index, "t", {"ים": KNOWN, "ספר": 2}) > 0


def test_the_score_is_per_hundred_running_words() -> None:
    short = index_of({"t": {"ים": 47, "ספר": 3}})
    long = index_of({"t": {"ים": 470, "ספר": 30, "בית": 0}})
    assert score(short, "t", {"ים": KNOWN}) == pytest.approx(2.0)
    assert score(long, "t", {"ים": KNOWN}) == pytest.approx(0.2)


def test_a_word_that_comes_back_next_or_was_met_before_counts_double() -> None:
    index = index_of({"t": {"ים": 97, "ספר": 3}, "next": {"ספר": 4, "ים": 10}})
    alone = score(index, "t", {"ים": KNOWN})
    assert score(index, "t", {"ים": KNOWN}, following=("next",)) == pytest.approx(2 * alone)
    assert score(index, "t", {"ים": KNOWN}, met=("ספר",)) == pytest.approx(2 * alone)
    assert score(index, "t", {"ים": KNOWN}, continuing=True) == pytest.approx(
        learning.CONTINUING * alone
    )


def test_a_word_of_a_topic_the_text_or_reader_has_counts_half_again() -> None:
    lexicon = from_lemmas({"ספר": ["school"], "ים": ["nature"]}, ["school", "nature"])
    index = index_of({"t": {"ים": 97, "ספר": 3}})
    alone = score(index, "t", {"ים": KNOWN})
    topical = score(index, "t", {"ים": KNOWN}, topics=("school",), lexicon=lexicon)
    assert topical == pytest.approx(1.5 * alone)
    liked = score(index, "t", {"ים": KNOWN}, liked=("school",), lexicon=lexicon)
    assert liked == pytest.approx(1.5 * alone)


def test_the_estimate_weighs_an_unmarked_word_by_its_chance_of_being_unknown() -> None:
    index = index_of({"t": {"ים": 97, "ספר": 3}})
    held = index.statuses({"ים": KNOWN})
    chances = [0.0] * len(index.words)
    chances[index._position("ספר")] = 0.75
    who = learning.reader(index, held, chances)
    got = learning.value(index, "t", who, learning.useful_table(index, USEFUL))
    assert got == pytest.approx(0.25)


def test_usefulness_is_log_damped_and_off_the_list_is_nothing() -> None:
    assert USEFUL.of("ספר") == 1.0
    assert 0.3 < USEFUL.of("חתול") < 0.4, "ten per million is about a third"
    assert USEFUL.of("זנב") == 0.0
    assert USEFUL.of("סֵפֶר") == 1.0, "points are not part of the key"


def test_narrow_reading_continues_an_ordered_collection_at_the_next_unread_part() -> None:
    parts = ("p1", "p2", "p3", "p4", "p5")
    got = learning.narrow([(parts, True), (("a", "b", "c"), False)], read={"p1", "p2", "b"})
    assert got.continuing == {"p3", "a", "c"}
    assert got.following["p3"] == ("p4", "p5")
    assert got.following["p1"] == ("p3", "p4", "p5"), "the next three unread"
    assert got.following["c"] == ("a",), "an unordered one wraps round"
    nobody = learning.narrow([(parts, True)], read=())
    assert nobody.continuing == frozenset()


def test_bag_value_scores_a_found_page_the_same_way() -> None:
    def p_known(lemma: str) -> float | None:
        return {"ים": 1.0, "ספר": 0.0, "בית": None}.get(lemma, 0.0)

    bag = {"ים": 90, "ספר": 3, "בית": 5, "זנב": 2}
    assert learning.bag_value(bag, 100, p_known, USEFUL) == pytest.approx(1.0)
    assert learning.bag_value(bag, 100, p_known, USEFUL, met=("ספר",)) == pytest.approx(2.0)
    assert learning.bag_value(bag, 0, p_known, USEFUL) == 0.0


def test_a_text_has_the_topics_its_running_words_are_about() -> None:
    lexicon = from_lemmas(
        {"ספר": ["school"], "ים": ["nature"], "שולחן": ["family"]}, ["school", "nature"]
    )
    index = index_of({"t": {"ים": 10, "ספר": 2, "שולחן": 40, "בית": 48}})
    got = learning.text_topics(index, "t", lexicon)
    assert got == {"nature": 0.1}, "school is under 3%, family is not shown"
    assert learning.main_topic(got) == "nature"
    assert learning.text_topics(index, "t", None) == {}
    assert learning.text_topics(index, "absent", lexicon) == {}


# -- the key ------------------------------------------------------------------------------


def test_audio_with_no_text_has_a_higher_floor() -> None:
    assert choose.fit(0.93) == choose.BAND
    assert choose.fit(0.93, choose.AUDIO) == choose.UNDER
    assert choose.fit(0.96, choose.AUDIO) == choose.BAND
    assert choose.medium_of("podcast", text_on_screen=False) == choose.AUDIO
    assert choose.medium_of("podcast") == choose.TEXT, "a transcript on screen reads as text"
    assert choose.medium_of("talk", source="video:abc") == choose.VIDEO
    assert choose.band(choose.VIDEO) == choose.band(choose.TEXT)
    assert choose.LIGHT == 0.98


def test_fit_comes_first_then_what_a_text_teaches_then_interest_then_fresh() -> None:
    # A text nearer the aim beats one further off whatever it teaches.
    assert choose.key(0.95, learn=0.0) < choose.key(0.92, learn=5.0)
    # Inside the aim every text fits as well, and the one that teaches more comes first.
    assert choose.key(0.97, learn=1.0) < choose.key(0.95, learn=0.0)
    # Teaching as much, the one on the reader's topics; then the fresher.
    assert choose.key(0.97, learn=1.0, interest=1) < choose.key(0.95, learn=1.1)
    assert choose.key(0.96, fresh=2) < choose.key(0.95, fresh=0)
    # Never past the band's tiers: a text under the floor that teaches a lot is still under.
    assert choose.key(0.995, learn=0.0) > choose.key(0.95)
    assert choose.key(0.89) > choose.key(0.99, learn=0.0)
    assert choose.key(0.95, scene=True, learn=9.0) > choose.key(0.91)


def test_freshness_is_a_found_items_and_the_shelf_has_none() -> None:
    day = 86_400_000
    now = 100 * day
    assert [choose.freshness(at, now) for at in (now, now - 3 * day, now - 30 * day, 0)] == [
        2,
        1,
        0,
        0,
    ]


def test_something_else_changes_topic_where_one_as_good_does() -> None:
    def row(kind: str, collection: str, about: list[str]) -> dict[str, Any]:
        return {"kind": kind, "collection": collection, "about": about}

    ranked = [
        (choose.key(0.95), row("story", "a", ["food"])),
        (choose.key(0.95), row("talk", "b", ["food"])),
        (choose.key(0.95), row("essay", "c", ["travel"])),
    ]
    assert choose.alternative(ranked, ("story", "a"), "food") == 2
    assert choose.alternative(ranked[:2], ("story", "a"), "food") == 1, "else another kind"
    assert choose.alternative(ranked, ("story", "a")) == 1
