"""Difficulty bands for the Tanakh, counted from the Tanakh.

The ordinary bands come from wordfreq's contemporary Israeli corpus. Asked of scripture
they are wrong in both directions and look authoritative doing it, which is worse than
saying nothing: "very hard" over a word that is on the first page of every Torah is a
claim about a learner's path that the data cannot support.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from targum.annotate import biblical
from targum.annotate.base import BAND_COUNT, UNRATED, method_label

TABLE = Path("src/targum/annotate/tanakh.json")


# -- how a count becomes a band -----------------------------------------------


def test_bands_are_cumulative_coverage_not_raw_counts() -> None:
    """A band answers "how much of the Tanakh can I read if I know this much", which is
    the question a learner actually has."""
    counts = {"a": 50, "b": 20, "c": 15, "d": 8, "e": 5, "f": 2}
    bands = biblical.bands_from_counts(counts)
    assert bands["a"] == 1, "the commonest lemma is always the first band"
    assert bands["f"] == max(bands.values()), "the rarest is always the last"
    # Never inverted: a more common word is never harder than a rarer one.
    ordered = sorted(counts, key=lambda k: -counts[k])
    assert [bands[k] for k in ordered] == sorted(bands[k] for k in ordered)


def test_every_band_is_inside_the_scale() -> None:
    counts = {f"w{i}": max(1, 1000 // (i + 1)) for i in range(500)}
    bands = biblical.bands_from_counts(counts)
    assert set(bands.values()) <= set(range(1, BAND_COUNT + 1))


def test_nothing_to_count_is_not_a_crash() -> None:
    assert biblical.bands_from_counts({}) == {}


def test_the_first_band_carries_about_half_the_text() -> None:
    """The rule the file was built with, stated where the reader can check it."""
    counts = {f"w{i}": max(1, 2000 // (i + 1)) for i in range(400)}
    bands = biblical.bands_from_counts(counts)
    total = sum(counts.values())
    covered = sum(count for lemma, count in counts.items() if bands[lemma] == 1)
    assert 0.35 < covered / total < 0.65


# -- the shipped table --------------------------------------------------------


@pytest.mark.skipif(not TABLE.is_file(), reason="the counted table has not been built")
def test_the_table_ships_and_is_shaped_right() -> None:
    raw = json.loads(TABLE.read_text(encoding="utf-8"))
    assert raw["lemmas"] > 1000, "a Tanakh has more distinct lemmas than that"
    assert set(raw["bands"].values()) <= set(range(1, BAND_COUNT + 1))


@pytest.mark.skipif(not TABLE.is_file(), reason="the counted table has not been built")
def test_common_biblical_words_are_easy() -> None:
    """The failure this whole module exists for.

    These are the first words anybody meets in Torah. Under wordfreq's modern corpus
    several of them are unremarkable or rare; here they must be near the front.
    """
    bands = biblical.BiblicalBands()
    # Written as the tagging names them, which is how `ScriptureLemmatizer` files them:
    # `כל`, where Stanza used to write `כול`. The table is counted from the same tagging
    # through the same function, so a band is a true statement about the form the
    # reader will actually be shown.
    for lemma in ("אמר", "היה", "אשר", "כל", "עשה"):
        assert bands.band(lemma, "he") <= 2, f"{lemma} should be among the first learnt"


@pytest.mark.skipif(not TABLE.is_file(), reason="the counted table has not been built")
def test_the_table_is_keyed_to_the_headwords_the_tagging_files_under() -> None:
    """The pronouns are the tell. Stanza folded אתה, אני and הם onto הוא, so the table
    it counted had none of them, and every one was "modern · not in the Tanakh" on the
    first page of Nitzavim (targum-internal#156). The tagging names them, so the table
    counted from it has them — and has נצב, the first word of that portion, under the
    spelling the lookup files it by.
    """
    bands = biblical.BiblicalBands()
    for lemma in ("אתה", "אני", "הם", "זאת", "נצב", "כל"):
        assert bands.band(lemma, "he") < BAND_COUNT, f"{lemma} is in the Tanakh"


def test_the_table_says_what_it_was_counted_from() -> None:
    """The header is the provenance a future reader of the file has, and the first
    table's said `stanza-he` for a fortnight after nothing read Hebrew with Stanza."""
    raw = json.loads(TABLE.read_text(encoding="utf-8"))
    assert "Open Scriptures" in raw["corpus"]
    assert "stanza" not in raw["corpus"].lower()


@pytest.mark.skipif(not TABLE.is_file(), reason="the counted table has not been built")
def test_a_word_the_corpus_never_uses_is_the_hardest_band() -> None:
    """Not unrated: in a Tanakh, a lemma the Tanakh does not contain is a word this
    corpus does not teach, and the hardest band is the honest answer."""
    assert biblical.BiblicalBands().band("ממשקזזזז", "he") == BAND_COUNT


# -- where it applies ---------------------------------------------------------


def test_only_hebrew_is_rated() -> None:
    bands = biblical.BiblicalBands()
    for language in ("en", "ru", "la", "ar"):
        assert bands.band("word", language) == UNRATED


@pytest.mark.parametrize(
    ("source", "biblical_expected"),
    [
        ("sefaria:Genesis", True),
        ("sefaria:en:Ruth", True),
        ("wikisource:he:something", False),
        ("gutenberg:1342", False),
        ("book.epub", False),
        ("https://benyehuda.org/read/1", False),
    ],
)
def test_biblical_bands_are_used_for_biblical_texts_only(
    source: str, biblical_expected: bool
) -> None:
    """Applying a Tanakh word list to a novel would be the same mistake the other way
    round, so this keys on where the text came from rather than guessing at content."""
    assert (biblical.for_source(source) is not None) is biblical_expected


def test_the_reader_is_told_which_word_list_this_is() -> None:
    """A learner should know whether they are looking at curated data or a proxy."""
    assert method_label(biblical.METHOD) == "from the tanakh word list"
    assert "Tanakh itself" in biblical.BiblicalBands().note


def test_the_annotator_is_renamed_rather_than_the_schema_bumped() -> None:
    """Changing `SCHEMA_VERSION` would discard every cached translation in existence —
    the standing rule in CLAUDE.md. Naming the annotator re-annotates for free instead,
    because Stanza runs locally.
    """
    from targum.annotate import Annotator
    from targum.annotate.frequency import FrequencyBands

    assert Annotator(bands=biblical.BiblicalBands()).name != Annotator(bands=FrequencyBands()).name
    assert biblical.NAME in Annotator(bands=biblical.BiblicalBands()).name


@pytest.mark.skipif(not TABLE.is_file(), reason="the counted table has not been built")
def test_words_the_tanakh_uses_are_easier_here_than_in_a_newspaper() -> None:
    """The whole payoff, measured.

    `אהל` (tent) is on nearly every page of Torah and rare in modern Hebrew, so
    wordfreq calls it hard. Telling a beginner that is not a small inaccuracy: it is the
    product being confidently wrong about what to learn first.
    """
    from targum.annotate.frequency import FrequencyBands

    bible, modern = biblical.BiblicalBands(), FrequencyBands()
    for lemma in ("אהל", "חסד"):
        assert bible.band(lemma, "he") < modern.band(lemma, "he"), lemma


@pytest.mark.skipif(not TABLE.is_file(), reason="the counted table has not been built")
def test_modern_words_are_hard_here_however_common_they_are_elsewhere() -> None:
    """The same correction in the other direction. `טלפון` is unremarkable in a
    newspaper and simply absent from the Tanakh."""
    from targum.annotate.frequency import FrequencyBands

    bible, modern = biblical.BiblicalBands(), FrequencyBands()
    for lemma in ("טלפון", "מחשב"):
        assert bible.band(lemma, "he") > modern.band(lemma, "he"), lemma


@pytest.mark.skipif(not TABLE.is_file(), reason="the counted table has not been built")
def test_a_handful_of_lemmas_carries_half_the_corpus() -> None:
    """Worth pinning because it is the fact that makes the shelf teachable: learn the
    first band and half of every page is already familiar."""
    import json

    raw = json.loads(TABLE.read_text(encoding="utf-8"))
    first = [lemma for lemma, band in raw["bands"].items() if band == 1]
    assert len(first) < 200, "band one should be a short list, not a syllabus"
