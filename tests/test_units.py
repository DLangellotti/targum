"""Multiword units: an idiom is one word to know (design.md §12, "An idiom is one word to
know", 2026-11-05; targum-internal#614)."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import pytest

from targum import coverage, units
from targum.coverage import KNOWN, build_index, measure_running, units_in


def token(surface: str, lemma: str, start: int, pos: str = "ADV", lead: int = 0) -> dict[str, Any]:
    return {
        "start": start,
        "end": start + len(surface),
        "surface": surface,
        "lemma": lemma,
        "pos": pos,
        "entity": None,
        "syntax": {"prefixes": [], "lead": lead},
    }


def sentence(*words: tuple[str, str] | tuple[str, str, str] | tuple[str, str, str, int]) -> list:
    """Tokens one space apart."""
    out = []
    at = 0
    for word in words:
        surface, lemma = word[0], word[1]
        pos = word[2] if len(word) > 2 else "ADV"  # type: ignore[misc]
        lead = word[3] if len(word) > 3 else 0  # type: ignore[misc]
        out.append(token(surface, lemma, at, pos, lead))
        at += len(surface) + 1
    return out


def built(folder: Path, *segments: list[dict[str, Any]], language: str = "he") -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    tokens = {f"s{n}": tokens for n, tokens in enumerate(segments)}
    (folder / "annotation.json").write_text(
        json.dumps({"language": language, "tokens": tokens}, ensure_ascii=False),
        encoding="utf-8",
    )
    return folder


AFTERWARDS = sentence(("הוא", "הוא", "PRON"), ("בא", "בא", "VERB"), ("אחר", "אחר"), ("כך", "כך"))


def test_the_list_ships_with_every_key_of_two_words_or_three() -> None:
    found = units.load()
    assert len(found) == 174
    assert all(2 <= len(unit.parts) <= 3 for unit in found)
    assert "אחר כך" in units.keys()


def test_a_sentence_with_achar_kach_counts_one_unit_not_two(tmp_path: Path) -> None:
    folder = built(tmp_path / "t", AFTERWARDS)
    counts = coverage.tally(folder)
    assert counts == {"הוא": 1, "בא": 1, "אחר": 1, "כך": 1}, "a word's own count is unchanged"
    assert units_in(folder) == {"אחר כך": 1}
    marked = dict.fromkeys(counts, KNOWN)
    measured = measure_running(counts, marked, units=units_in(folder))
    assert measured.total == 3, "three running words: הוא, בא, and אחר כך"
    assert measured.known == pytest.approx(2 / 3), "the expression is not marked"
    kept = units.with_phrases(marked, ["אַחַר כָּךְ"])
    assert measure_running(counts, kept, units=units_in(folder)).known == 1.0
    assert coverage.running_against(folder, kept) == measure_running(
        counts, kept, units=units_in(folder)
    )


def test_coverage_moves_as_the_unit_and_its_words_are_known(tmp_path: Path) -> None:
    folder = built(tmp_path / "t", AFTERWARDS)
    counts = coverage.tally(folder)
    joined = units_in(folder)
    nothing = measure_running(counts, {}, units=joined)
    assert nothing.known == 0.0 and nothing.total == 3
    words = measure_running(counts, {"הוא": KNOWN, "בא": KNOWN}, units=joined)
    assert words.known == pytest.approx(2 / 3)
    before = measure_running(counts, {"הוא": KNOWN, "בא": KNOWN})
    assert before.known == 0.5 and before.total == 4, "as it was, counted as words"


def test_the_estimate_gives_a_unit_the_product_of_its_words_chances(tmp_path: Path) -> None:
    folder = built(tmp_path / "t", AFTERWARDS)
    counts = coverage.tally(folder)

    class Guess:
        def chance(self, lemma: str) -> float:
            return {"אחר": 0.8, "כך": 0.5}.get(lemma, 1.0)

    marked = {"הוא": KNOWN, "בא": KNOWN}
    measured = measure_running(counts, marked, Guess(), units_in(folder))
    assert measured.expected == pytest.approx((2 + 0.8 * 0.5) / 3)
    one_known = measure_running(counts, {**marked, "כך": KNOWN}, Guess(), units_in(folder))
    assert one_known.expected == pytest.approx((2 + 0.8) / 3), "a mark on a word wins"
    learning = measure_running(counts, {**marked, "כך": 2}, Guess(), units_in(folder))
    assert learning.expected == pytest.approx(2 / 3)


def test_the_catalogue_index_counts_a_unit_as_one_word(tmp_path: Path) -> None:
    folder = built(tmp_path / "t", AFTERWARDS)
    counts = coverage.tally(folder)
    index = build_index({"t": list(counts)}, {"t": counts}, {"t": units_in(folder)})
    assert "אחר כך" in index.words and "אחר כך" not in index.lemmas_for("t")
    assert index.count_in("t", "אחר") == 1, "a word's own count is unchanged"
    marked = dict.fromkeys(counts, KNOWN)
    running = index.running("t", marked)
    assert running is not None and running.total == 3 and running.known == pytest.approx(2 / 3)
    kept = units.with_phrases(marked, ["אחר כך"])
    running = index.running("t", kept)
    assert running is not None and running.known == 1.0
    chances = [0.5] * len(index.words)
    statuses = index.statuses({"הוא": KNOWN, "בא": KNOWN})
    assert index.expected("t", statuses, chances) == pytest.approx((2 + 0.25) / 3)
    written = tmp_path / "lemmas.json"
    coverage.write_index(written, index)
    assert coverage.read_index(written).units == index.units


def test_a_key_that_needs_its_prefix_matches_only_with_it() -> None:
    with_it = sentence(("מכל", "כול", "DET", 1), ("מקום", "מקום", "NOUN"))
    without = sentence(("כל", "כול", "DET"), ("מקום", "מקום", "NOUN"))
    assert [unit.key for _, unit in units.match(with_it)] == ["כול מקום"]
    assert units.match(without) == []
    school = sentence(("ובית", "בית", "NOUN", 1), ("הספר", "ספר", "NOUN", 1))
    assert [unit.key for _, unit in units.match(school)] == ["בית ספר"], "a prefix is allowed"


def test_a_unit_is_never_matched_across_punctuation() -> None:
    apart = [token("אחר", "אחר", 0), token("כך", "כך", 5)]
    assert units.match(apart) == []
    joined = [token("אחר", "אחר", 0), token("כך", "כך", 4)]
    assert len(units.match(joined)) == 1


def test_a_word_not_counted_stays_out_of_the_unit(tmp_path: Path) -> None:
    """DICTA tags the אחד of אף אחד a numeral, which no count keeps."""
    folder = built(tmp_path / "t", sentence(("אף", "אף"), ("אחד", "אחד", "NUM"), ("בא", "בא")))
    counts = coverage.tally(folder)
    assert counts == {"אף": 1, "בא": 1}
    assert units_in(folder) == {"אף אחד|אף": 1}
    measured = measure_running(counts, {"אף": KNOWN, "בא": KNOWN}, units=units_in(folder))
    assert measured.total == 2 and measured.known == 0.5
    kept = units.with_phrases({"אף": KNOWN, "בא": KNOWN}, ["אַף אֶחָד"])
    assert measure_running(counts, kept, units=units_in(folder)).known == 1.0


def test_a_kept_phrase_is_matched_by_its_written_form_with_a_prefix() -> None:
    assert units.from_phrases(["ובכל זאת,"]) >= {"כול זה", "כל זאת"}
    assert units.from_phrases(["על פי"]) == {"על פה"}
    assert units.from_phrases(["בעל פה"]) == {"על פה"}, "one key, two meanings"
    assert units.from_phrases(["ספר טוב"]) == frozenset()


def test_another_language_has_no_units(tmp_path: Path) -> None:
    folder = built(tmp_path / "t", AFTERWARDS, language="ru")
    assert units_in(folder) == {}


def test_a_count_cached_before_units_is_counted_again(tmp_path: Path) -> None:
    folder = built(tmp_path / "t", AFTERWARDS)
    stat = (folder / "annotation.json").stat()
    (folder / "lemmas.json").write_text(
        json.dumps(
            {
                "stamp": [stat.st_mtime_ns, stat.st_size],
                "lemmas": ["אחר", "בא", "הוא", "כך"],
                "counts": {"הוא": 1, "בא": 1, "אחר": 1, "כך": 1},
            }
        ),
        encoding="utf-8",
    )
    assert units_in(folder) == {"אחר כך": 1}


def test_a_text_with_no_units_is_measured_as_before() -> None:
    counts = {"בית": 3, "ספר": 1}
    plain = measure_running(counts, {"בית": KNOWN})
    assert measure_running(counts, {"בית": KNOWN}, units={}) == plain
    assert math.isclose(plain.known, 0.75)
