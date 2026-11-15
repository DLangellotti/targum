"""The Onkelos starter: a week of real Onkelos under the Hebrew (targum-internal#530).

Aramaic is never written by a model (design.md §12, 2026-10-25), so every Aramaic word
this set shows has to be a word of the edition already on the shelf, in the verse it is
said to be in. These read the set's own lines against both sides of every verse it
covers, saved from Sefaria by `scripts/file_onkelos_starter.py --fixture` into
`fixtures/sefaria/onkelos-starter.json`: the public-domain Onkelos and the Hebrew it
translates.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path
from types import ModuleType

import pytest

from targum import catalogue
from targum.accounts import MOST_IN_PLAYLIST
from targum.annotate import aramaic, aramaic_frequency
from targum.ingest.fetch import sefaria

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "file_onkelos_starter.py"
SAVED = Path(__file__).parent / "fixtures" / "sefaria" / "onkelos-starter.json"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("file_onkelos_starter", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


starter = _load()
VERSES: dict[str, dict[str, str]] = json.loads(SAVED.read_text(encoding="utf-8"))


def words(text: str) -> set[str]:
    """A verse's words as the hand table files a spelling: letters only, no points, no
    accents, final forms folded. With every one-letter prefix taken off as well, so
    `וְאַרְעָא` answers for `אַרְעָא`."""
    out: set[str] = set()
    for word in re.split(r"[\s־]+", text):
        folded = aramaic.key(word)
        while folded:
            out.add(folded)
            if len(folded) < 3 or folded[0] not in "ודבלמכה":
                break
            folded = folded[1:]
    return out


def side(ref: str, language: str) -> str:
    return VERSES[ref][language]


def in_set(ref: str) -> int:
    """Which day a verse is read on, or 0."""
    for day in starter.DAYS:
        if ref in starter.verses(day.ref):
            return int(day.number)
    return 0


# -- the passages are real verses -------------------------------------------------


def test_seven_days_genesis_1_first() -> None:
    assert [day.number for day in starter.DAYS] == list(range(1, 8))
    assert starter.DAYS[0].ref == "Genesis 1:1-5"


def test_every_verse_of_every_day_is_a_verse_of_onkelos_and_of_the_hebrew() -> None:
    covered: list[str] = []
    for day in starter.DAYS:
        refs = starter.verses(day.ref)
        assert 5 <= len(refs) <= 15, f"day {day.number} is {len(refs)} verses"
        for ref in refs:
            assert ref in VERSES, f"{ref} is not in the saved edition"
            for language in ("arc", "he"):
                text = side(ref, language)
                assert text.strip() not in ("", "—"), f"{ref} has no {language}"
        covered += refs
    assert len(covered) == len(set(covered)), "a verse is read twice"
    assert sorted(covered) == sorted(VERSES), "the saved edition is exactly the set"


def test_the_verse_ranges_end_where_their_chapters_do() -> None:
    """The ranges are counted on `LENGTHS`, so a wrong length would put a verse in the set
    that Genesis does not have, or drop one that it does."""
    assert starter.verses("Genesis 1:20-2:3")[11:] == [
        "Genesis 1:31",
        "Genesis 2:1",
        "Genesis 2:2",
        "Genesis 2:3",
    ]
    for chapter, last in starter.LENGTHS.items():
        held = [ref for ref in VERSES if ref.startswith(f"Genesis {chapter}:")]
        assert all(int(ref.rsplit(":", 1)[1]) <= last for ref in held)


def test_each_row_reads_one_passage_on_all_three_sides() -> None:
    for day in starter.DAYS:
        row = starter.row(day)
        entry = catalogue._entry(row)
        assert entry.source == f"sefaria:{day.ref}" and entry.language == "he"
        assert [t.source for t in entry.translations] == [
            f"sefaria:en:{day.ref}",
            f"sefaria:arc:{day.ref}",
        ]
        # The Aramaic is the public-domain Onkelos and nothing else, asked for by its
        # own index; the English the edition the `genesis` row reads.
        assert sefaria.version_for("arc", day.ref) == sefaria.ONKELOS["Genesis"]
        assert sefaria.asked_as(day.ref, "arc") == f"Onkelos {day.ref}"
        assert sefaria.version_for("en", day.ref) == starter.METSUDAH
        # Nothing on the row asks a model for anything.
        assert not entry.model


# -- every word the lines name is in its verse ------------------------------------


def test_each_pair_a_day_names_is_in_its_verse() -> None:
    for day in starter.DAYS:
        for ref, aramaic_word, hebrew_word in day.pairs:
            assert in_set(ref) == day.number, f"{ref} is not read on day {day.number}"
            assert aramaic.key(aramaic_word) in words(side(ref, "arc")), (ref, aramaic_word)
            assert aramaic.key(hebrew_word) in words(side(ref, "he")), (ref, hebrew_word)


def test_every_hebrew_letter_word_in_a_line_is_in_that_day_s_verses() -> None:
    """The line is the one place a person's words meet the Aramaic, so it may only quote:
    every word in Hebrew letters is in that day's passage, on one side or the other.
    A letter alone (ש, ת) and an ending (־א) are spoken of, not quoted."""
    for day in starter.DAYS:
        refs = starter.verses(day.ref)
        found = set().union(*(words(side(ref, lang)) for ref in refs for lang in ("arc", "he")))
        for quoted in re.findall(r"[֐-׿]+", day.blurb):
            if quoted.startswith("־") or len(aramaic.key(quoted)) < 2:
                continue
            assert aramaic.key(quoted) in found, f"day {day.number} quotes {quoted}"


def test_the_set_s_own_name_and_line_quote_no_aramaic() -> None:
    assert not re.search(r"[֐-׿]", starter.BLURB + starter.ENGLISH)


def test_each_sound_shift_is_a_real_pair_in_a_verse_of_the_set() -> None:
    taught = set()
    for hebrew_letter, aramaic_letter, ref, aramaic_word, hebrew_word in starter.SHIFTS:
        assert in_set(ref), f"{ref} is not in the set"
        assert aramaic.key(aramaic_word) in words(side(ref, "arc")), (ref, aramaic_word)
        assert aramaic.key(hebrew_word) in words(side(ref, "he")), (ref, hebrew_word)
        assert hebrew_letter in aramaic.key(hebrew_word)
        assert aramaic_letter in aramaic.key(aramaic_word)
        taught.add((hebrew_letter, aramaic_letter))
    assert taught == {("ש", "ת"), ("ז", "ד"), ("צ", "ע")}


def test_the_emphatic_ending_is_met_on_day_one() -> None:
    first = starter.verses(starter.DAYS[0].ref)
    ending = [w for ref in first for w in words(side(ref, "arc")) if w.endswith("א")]
    assert {"ארעא", "שמיא", "נהורא"} <= set(ending)


# -- the forty words ---------------------------------------------------------------


@pytest.mark.skipif(not aramaic_frequency.available(), reason="no Aramaic frequency list")
def test_forty_function_words_from_the_top_of_the_frequency_list() -> None:
    chosen = starter.FUNCTION_WORDS
    assert len(chosen) == 40 and len(set(chosen)) == 40
    for lemma in chosen:
        rank = aramaic_frequency.rank(lemma)
        assert rank is not None and rank <= 250, f"{lemma} ranks {rank}"


def test_every_function_word_is_met_in_a_line_of_the_set() -> None:
    """Met the way the reader meets it: tapped in Onkelos beside the Hebrew, where the
    card files the word under the same name the frequency list counts."""
    met: dict[str, str] = {}
    for ref in VERSES:
        for token in aramaic.rendering_tokens(side(ref, "arc"), f"Onkelos {ref}"):
            met.setdefault(token.lemma, ref)
    missing = [lemma for lemma in starter.FUNCTION_WORDS if lemma not in met]
    assert not missing, f"never met: {missing}"


# -- the set ----------------------------------------------------------------------


def test_the_set_is_one_of_targum_s_playlists_in_reading_order() -> None:
    group = catalogue._collection(starter.collection())
    assert group.swipe and group.ordered and group.door == "targum"
    assert list(group.members) == [day.id for day in starter.DAYS]
    assert len(group.members) <= MOST_IN_PLAYLIST
    assert group.english and group.title and group.blurb


def test_the_last_day_hands_on_to_the_week_s_portion() -> None:
    assert "this week's portion" in starter.DAYS[-1].blurb


def test_di_is_met_every_day_from_day_three() -> None:
    """Day 3's line says so: "From here on you'll meet it every day"."""
    for day in starter.DAYS[2:]:
        lemmas = {
            token.lemma
            for ref in starter.verses(day.ref)
            for token in aramaic.rendering_tokens(side(ref, "arc"), f"Onkelos {ref}")
        }
        assert "די" in lemmas, f"no דִּי on day {day.number}"
