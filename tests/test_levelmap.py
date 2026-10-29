"""The level map: where the catalogue sits on the weekly's levels (targum-internal#382).

Pinned here: that a text is placed by both halves and never by the share alone, that
an unmeasured text is never counted as easy, that the Easy spec is the strict count with
its floors and its length, and that a sentence length the catalogue lacks is read off a
build without anything fetched.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from targum import levelmap
from targum.annotate.difficulty import sentence_length
from targum.catalogue import Entry
from targum.coverage import Index
from targum.models import BlockKind, Segment, SegmentedDocument
from targum.weekly.models import Level


def entry(
    source: str = "url:x",
    *,
    language: str = "he",
    difficulty: int = 10,
    sentence: float = 7.0,
    words: int = 260,
) -> Entry:
    return Entry(
        id=source,
        title="t",
        author="a",
        language=language,
        source=source,
        blurb="b",
        words=words,
        difficulty=difficulty,
        sentence=sentence,
    )


def segmented(*texts: str, heading: str = "") -> SegmentedDocument:
    segments = [
        Segment(id=f"s{i}", block_id="b", block_index=0, index=i, text=text)
        for i, text in enumerate(texts, start=1)
    ]
    if heading:
        segments.insert(
            0,
            Segment(
                id="s0", block_id="h", block_index=0, index=0, kind=BlockKind.heading, text=heading
            ),
        )
    return SegmentedDocument(document_hash="h", language="he", segmenter="r", segments=segments)


def nothing(source: str) -> bool:
    return False


# The measure.


def test_sentence_length_is_words_per_sentence_without_the_title() -> None:
    assert sentence_length(segmented("a b c", "a b c d e", heading="a b c d e f g h")) == 4.0


def test_no_sentences_is_unmeasured_not_zero_words() -> None:
    assert sentence_length(segmented(heading="only a title")) == 0.0
    assert sentence_length(segmented("   ")) == 0.0


# Placing a text.


@pytest.mark.parametrize(
    ("difficulty", "sentence", "level"),
    [
        (10, 7.0, Level.aleph),
        # Under both floors is easier, not unplaceable.
        (2, 3.0, Level.aleph),
        # Easy words, long sentences: the share alone would have called this Easy.
        (10, 12.0, Level.bet),
        # Short sentences, hard words.
        (18, 7.0, Level.bet),
        (25, 7.0, Level.gimel),
        (10, 20.0, Level.gimel),
    ],
)
def test_a_text_is_placed_by_both_halves(difficulty: int, sentence: float, level: Level) -> None:
    assert levelmap.place(difficulty, sentence) == level


def test_zero_on_either_half_is_unmeasured() -> None:
    assert levelmap.place(0, 7.0) is None
    assert levelmap.place(10, 0.0) is None


def test_the_easy_spec_keeps_its_floors_and_its_length() -> None:
    assert levelmap.meets_easy(10, 7.0, 2)
    assert not levelmap.meets_easy(2, 7.0, 2), "under the share's floor"
    assert not levelmap.meets_easy(10, 3.0, 2), "under the sentence floor"
    assert not levelmap.meets_easy(10, 7.0, 4), "too long to finish in a sitting"
    assert not levelmap.meets_easy(10, 7.0, 0)


def test_medium_is_asked_the_way_the_library_asks() -> None:
    assert levelmap.medium("video:abc", spoken=nothing, video=nothing) == "video"
    assert levelmap.medium("recording", spoken=lambda s: True, video=lambda s: True) == "video"
    assert levelmap.medium("dialogue:1", spoken=lambda s: True, video=nothing) == "audio"
    assert levelmap.medium("url:x", spoken=nothing, video=nothing) == "text"


# Counting a shelf.


def test_tally_counts_levels_media_and_the_easy_spec() -> None:
    entries = [
        entry("url:a"),
        entry("video:b"),
        entry("url:c", difficulty=25),
        entry("url:d", difficulty=0),
        entry("url:e", words=1000),  # Easy by its bands, too long for the spec
        entry("url:f", language="ru"),
    ]
    shelves = levelmap.tally(entries, sentence=lambda e: e.sentence, spoken=nothing, video=nothing)
    assert list(shelves) == ["he", "ru"], "largest shelf first"
    he = shelves["he"]
    assert he.cells[("aleph", "text")] == 2
    assert he.cells[("aleph", "video")] == 1
    assert he.cells[("gimel", "text")] == 1
    assert he.cells[(levelmap.UNMEASURED, "text")] == 1
    assert he.easy == {"text": 1, "video": 1}
    rows = dict(levelmap.rows(he))
    assert rows["Easy"] == [2, 0, 1, 3]
    assert rows["Unmeasured"] == [1, 0, 0, 1]
    assert rows[f"Easy spec (target {levelmap.TARGET})"] == [1, 0, 1, 2]


def test_a_language_with_no_target_is_counted_and_not_held_to_one() -> None:
    shelves = levelmap.tally(
        [entry("sefaria:Onkelos", language="arc")],
        sentence=lambda e: e.sentence,
        spoken=nothing,
        video=nothing,
    )
    assert not shelves["arc"].targeted
    assert "Easy spec" in dict(levelmap.rows(shelves["arc"]))


# Where a missing sentence length comes from.


def build_at(root: Path, home: str, source: str, *texts: str) -> Path:
    folder = root / home / "text"
    folder.mkdir(parents=True)
    (folder / "document.json").write_text(json.dumps({"source": source}), encoding="utf-8")
    (folder / "segments.json").write_text(segmented(*texts).model_dump_json(), encoding="utf-8")
    return folder


def test_the_catalogue_row_wins(tmp_path: Path) -> None:
    build_at(tmp_path, "library", "url:a", "a b")
    assert levelmap.Sentences(tmp_path)(entry("url:a", sentence=9.0)) == 9.0


def test_a_missing_length_is_read_off_the_build_library_first(tmp_path: Path) -> None:
    build_at(tmp_path, "aaa", "url:a", "a b c d e f")
    build_at(tmp_path, "library", "url:a", "a b")
    assert levelmap.Sentences(tmp_path)(entry("url:a", sentence=0.0)) == 2.0


def test_a_curated_video_is_segmented_on_the_spot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The video shelf keeps its document and not its segmentation, which the box makes
    again for free. So does the map — with the rules, and no download."""
    from targum import segment
    from targum.models import Document

    folder = tmp_path / "videos" / "abc"
    folder.mkdir(parents=True)
    document = Document(source="video:abc", title="t", language="he", ingester="i", blocks=[])
    (folder / "document.json").write_text(document.model_dump_json(), encoding="utf-8")
    made: list[bool] = []

    class Rules:
        def __init__(self, *, auto_download: bool) -> None:
            made.append(auto_download)

    monkeypatch.setattr(segment, "HebrewSegmenter", Rules)
    monkeypatch.setattr(segment, "segment_document", lambda document, segmenter: segmented("a b c"))
    sentences = levelmap.Sentences(tmp_path / "out", tmp_path / "videos")
    assert sentences(entry("video:abc", sentence=0.0)) == 3.0
    assert sentences(entry("video:abc", sentence=0.0)) == 3.0
    assert made == [False], "one segmenter, and it may not download"


def test_nothing_on_disk_is_unmeasured(tmp_path: Path) -> None:
    sentences = levelmap.Sentences(tmp_path / "missing", tmp_path / "missing")
    assert sentences(entry("url:a", sentence=0.0)) == 0.0
    assert sentences(entry("video:zzz", sentence=0.0)) == 0.0


# -- the text ruler (design.md §12, "Your level, v3", 2026-10-29) ---------------------


def words_at(language: str, *places: int) -> list[str]:
    """The word at each place in the language's frequency list."""
    from targum.annotate.frequency import ranks

    by_place = {place: word for word, place in ranks(language).items()}
    return [by_place[place] for place in places]


def ruled(language: str, counts: dict[str, int]) -> Index:
    from targum.coverage import build_index

    return build_index({"n": list(counts)}, {"n": counts})


def native(language: str = "he") -> Entry:
    return Entry(
        id="n",
        title="t",
        author="a",
        language=language,
        source="url:n",
        blurb="b",
        words=2000,
        difficulty=25,
        sentence=20,
    )


@pytest.mark.parametrize(
    ("hardest", "level"),
    [(3000, "B2"), (6500, "B2"), (6501, "C1"), (9000, "C1"), (11_000, "C2"), (15_000, "past-C2")],
)
def test_a_native_text_is_placed_by_the_rank_that_covers_85_percent(
    hardest: int, level: str
) -> None:
    """80 running words from the commonest hundred and 20 at `hardest`: the rank that
    covers 85% is the rare word's. Against the ulpan's dalet 6,500, hey 9,000 and vav
    12,000, never below B2 for a Native text, and past vav is Past C2."""
    common, rare = words_at("he", 50, hardest)
    assert levelmap.text_level(native(), ruled("he", {common: 80, rare: 20})) == level
    # Fifteen in a hundred is inside the 85%: the common word decides.
    assert levelmap.text_level(native(), ruled("he", {common: 85, rare: 15})) == "B2"


def test_a_form_the_list_never_ranked_is_left_out_of_the_count() -> None:
    """A lemma spelling, a transliteration or a missed name is not a rare word: it is not
    counted, so it cannot push a text past vav (2026-10-29 calibration)."""
    (common,) = words_at("he", 10)
    index = ruled("he", {common: 50, "לאמילהבכלל": 50})
    assert levelmap.ruler_rank("n", "he", index) == 10
    assert levelmap.text_level(native(), index) == "B2"
    assert levelmap.ruler_rank("n", "he", ruled("he", {"לאמילהבכלל": 9})) is None


def test_the_european_scale_is_not_ruled_yet() -> None:
    """The CEFR rungs count known common words, not a rank: French, Russian and Italian
    Native texts stay on B2 until that scale has a ruler of its own."""
    common, rare = words_at("fr", 20, 9000)
    assert levelmap.text_level(native("fr"), ruled("fr", {common: 50, rare: 50})) == "B2"


#: The rank that covers 85% of each built Hebrew text's ranked running words, by the
#: level the shelf gives it, measured off the laptop's library on 2026-10-29 (numbers
#: only: no word of any text). The calibration is pinned to these.
MEASURED = {
    "A1": (1002, 1069, 1127, 1149, 1172, 1429, 1491, 1618, 1699, 1764, 1786, 1993, 1993,
           2087, 2103, 2124, 2139, 2155, 2177, 2284, 2294, 2294, 2310, 2310, 2363, 2363,
           2363, 2456, 2462, 2464, 2494, 2618, 2642, 2649, 2753, 2854, 2935, 3012, 3138,
           3145, 3513, 3513, 3667, 3683, 3744, 3744, 4201, 4302, 4323, 4324, 4382, 4830,
           5030, 5047, 5168, 5203, 5299, 6332, 6508),
    "A2": (1293, 1316, 1388, 1497, 1497, 1639, 1639, 1694, 1951, 1992, 2100, 2284, 2341,
           2444, 2464, 2539, 2557, 2823, 2980, 3473, 3513, 3728, 5050, 5502),
    "Native": (4910, 4933, 5097, 5168, 5348, 5590, 5881, 7333, 7347, 8871, 10496),
}  # fmt: skip


def rung_of(needed: int) -> str:
    """The CEFR of the first ulpan rung whose vocabulary reaches `needed`, or past vav."""
    from targum.level import ULPAN

    return next((rung.cefr for rung in ULPAN if rung.at >= needed), "past")


#: The long tail every real text has: rarer ranked words, one or two each, past vav.
TAIL = (12_500, 13_100, 13_800, 14_600, 15_400, 16_300, 17_200, 18_100, 19_000)


def a_text_needing(needed: int) -> Index:
    """A text whose 85th percentile of ranked running words falls on the word at rank
    `needed`, with a long tail of rarer ranked words above it, as a real text has: 84
    running words from the commonest hundred, 2 at `needed` and 14 in the tail, and six
    forms no list ranks. At 85% of the ranked words the ruler reads `needed`; at 95%, or
    with the unranked forms counted as past vav, it reads the tail, which is what the
    first setting did to the built library."""
    common, middle = words_at("he", 50, needed)
    tail = words_at("he", *TAIL)
    counts = {common: 84, middle: 2}
    for at, word in enumerate(tail):
        counts[word] = 2 if at < 5 else 1
    assert sum(counts.values()) == 100
    # And forms no frequency list ranks, as the built texts carry: counted as past every
    # rung, they would push the 85th percentile into the tail too.
    for n in range(6):
        counts[f"לאמילה{'א' * (n + 1)}"] = 1
    return ruled("he", counts)


def test_the_calibration_keeps_easy_texts_low_and_spreads_native_ones() -> None:
    """Pinned on the 2026-10-29 calibration (targum-internal#561): what the shelf calls A1
    and A2 lands at B1 or below, mostly A1 to A2+; Native texts land on B2, C1 and C2, and
    none past vav."""
    for shelf in ("A1", "A2"):
        rungs = [
            rung_of(levelmap.ruler_rank("n", "he", a_text_needing(one)) or 0)
            for one in MEASURED[shelf]
        ]
        low = sum(1 for one in rungs if one in {"A1", "A2", "A2+"})
        at_most_b1 = sum(1 for one in rungs if one in {"A1", "A2", "A2+", "B1"})
        assert low * 2 > len(rungs), (shelf, rungs)
        assert at_most_b1 >= 0.8 * len(rungs), (shelf, rungs)
    placed = [levelmap.text_level(native(), a_text_needing(one)) for one in MEASURED["Native"]]
    assert set(placed) <= {"B2", "C1", "C2"}, placed
    assert len(set(placed)) == 3, "spread across all three"


def test_a_native_text_the_index_has_not_counted_stays_on_b2() -> None:
    """No index, an uncounted text, or a language with no ladder: B2, as before the
    ruler, never a guess further up."""
    from targum.coverage import EMPTY, build_index

    assert levelmap.text_level(native(), EMPTY) == "B2"
    uncounted = build_index({"n": ["שלום"]})
    assert levelmap.text_level(native(), uncounted) == "B2"
    assert levelmap.text_level(native("yi"), ruled("yi", {"און": 100})) == "B2"


def test_easier_texts_are_not_ruled() -> None:
    """The ruler splits Native only: Easy and Simplified keep their levels."""
    from targum.coverage import EMPTY

    assert levelmap.text_level(entry(difficulty=17, sentence=12), EMPTY) == "B1"


def test_b2_and_up_is_an_alias_for_the_four_native_levels() -> None:
    assert levelmap.levels_named("B2+") == ("B2", "C1", "C2", "past-C2")
    assert levelmap.levels_named("C1") == ("C1",)
    assert levelmap.levels_named("Z9") == ()
    assert levelmap.TEXT_LEVELS == ("A1", "A2", "B1", "B2", "C1", "C2", "past-C2")
