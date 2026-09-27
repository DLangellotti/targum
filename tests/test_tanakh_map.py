"""The Tanakh map's data: every chapter counted once, and a reader's share of each.

A handful of made-up verses go through the script's own `build`, so the shape and the
arithmetic are checked without the tagging on disk. The shipped file is then checked for
what the map promises about it — 929 chapters in the Hebrew count, the Aramaic ones
marked — and, where the tagging is on this machine, for being what a recount would write.
"""

from __future__ import annotations

import importlib.util
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from targum import coverage
from targum.annotate import oshb

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "tanakh_map.py"


def load_script() -> Any:
    spec = importlib.util.spec_from_file_location("tanakh_map", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


tanakh_map = load_script()

#: Where the real tagging is, read before any test points the model directory elsewhere.
TAGGING = oshb.root()


def word(text: str, morph: str = "Ncmsa", lexeme: str = "1") -> oshb.Word:
    """One tagged word with no lexicon behind it, so it is filed under its own letters."""
    return oshb.Word(text, (text,), (lexeme,), (morph,), "")


def verse(*texts: str) -> tuple[oshb.Word, ...]:
    return tuple(word(text) for text in texts)


#: Genesis 1 twice over, a name and a paragraph marker in it; Jeremiah 10 with its one
#: Aramaic verse; Daniel 2 turning to Aramaic at the fifth word of verse 4.
VERSES: list[tuple[str, tuple[oshb.Word, ...]]] = [
    # Deliberately out of order: the file is in the Hebrew order whatever it is handed.
    ("Dan.2.4", verse("דבר", "כשדי", "מלך", "ארמית", "מלכא", "חיי")),
    ("Dan.2.5", verse("ענה", "מלכא")),
    ("Jer.10.11", verse("כדנה", "תאמרון")),
    ("Jer.10.12", verse("עשה", "ארץ", "כח")),
    ("Gen.1.1", (*verse("ברא", "ארץ", "ארץ"), word("משה", morph="Np"))),
    ("Gen.1.2", (*verse("ארץ", "היה"), word("פ", morph="x"))),
]


@pytest.fixture(autouse=True)
def no_lexicon(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("TARGUM_MODEL_DIR", str(tmp_path / "models"))
    oshb.forget()
    yield
    oshb.forget()


@pytest.fixture
def made(tmp_path: Path) -> tuple[dict[str, Any], Path]:
    built = tanakh_map.build(VERSES)
    path = tmp_path / "tanakh_chapters.json"
    path.write_text(json.dumps(built, ensure_ascii=False), encoding="utf-8")
    return built, path


def test_chapters_are_in_the_hebrew_order_with_their_verses(made: tuple[dict, Path]) -> None:
    built, _ = made
    assert list(built["chapters"]) == ["Genesis 1", "Jeremiah 10", "Daniel 2"]
    assert [c["verses"] for c in built["chapters"].values()] == [2, 2, 2]
    assert built["books"] == [
        ["Genesis", "torah", 1],
        ["Jeremiah", "prophets", 1],
        ["Daniel", "writings", 1],
    ]
    assert built["version"] == coverage.MAP_VERSION
    assert built["licence"] == "CC BY 4.0"


def test_names_and_paragraph_markers_are_not_running_words(made: tuple[dict, Path]) -> None:
    genesis = made[0]["chapters"]["Genesis 1"]
    assert genesis["he"]["tokens"] == 5  # ברא ארץ ארץ, ארץ היה — not משה, not פ
    assert "משה" not in made[0]["words"]["he"]
    assert "פ" not in made[0]["words"]["he"]


def test_each_language_is_ranked_by_its_own_count(made: tuple[dict, Path]) -> None:
    words = made[0]["words"]
    # ארץ comes round four times, every other Hebrew word once, ties by spelling.
    assert words["he"][0] == "ארץ"
    assert words["he"][1:] == sorted(words["he"][1:])
    assert words["arc"][0] == "מלכא"
    assert set(words["arc"]) == {"מלכא", "חיי", "ענה", "כדנה", "תאמרון"}


def test_a_profile_is_each_word_with_its_count_and_the_same_words_by_band(
    made: tuple[dict, Path],
) -> None:
    built = made[0]
    for chapter in built["chapters"].values():
        for language in ("he", "arc"):
            part = chapter.get(language)
            if part is None:
                continue
            flat = part["words"]
            assert sum(flat[1::2]) == part["tokens"] == sum(part["bands"])
            assert len(part["bands"]) == len(built["cuts"]) + 1
    assert built["chapters"]["Genesis 1"]["he"]["words"][:2] == [0, 3]  # ארץ, three times


def test_the_aramaic_is_counted_apart_and_decides_the_chapter(made: tuple[dict, Path]) -> None:
    chapters = made[0]["chapters"]
    daniel = chapters["Daniel 2"]
    # Verse 4 is Hebrew for four words and Aramaic from "the king, live for ever".
    assert daniel["he"]["tokens"] == 4
    assert daniel["arc"]["tokens"] == 4
    # A tie goes to Hebrew; in the real Daniel 2 the Aramaic is 760 words to 38.
    assert daniel["language"] == "he"
    jeremiah = chapters["Jeremiah 10"]
    assert jeremiah["language"] == "he"
    assert jeremiah["arc"]["tokens"] == 2
    assert jeremiah["he"]["tokens"] == 3


def test_the_aramaic_table_reads_a_switch_mid_verse() -> None:
    assert tanakh_map.language_of("Dan.2.4", 3) == "he"
    assert tanakh_map.language_of("Dan.2.4", 4) == "arc"
    assert tanakh_map.language_of("Dan.2.3", 9) == "he"
    assert tanakh_map.language_of("Dan.7.28", 0) == "arc"
    assert tanakh_map.language_of("Dan.8.1", 0) == "he"
    assert tanakh_map.language_of("Ezra.4.7", 0) == "he"
    assert tanakh_map.language_of("Ezra.6.18", 0) == "arc"
    assert tanakh_map.language_of("Ezra.6.19", 0) == "he"
    assert tanakh_map.language_of("Ezra.7.11", 0) == "he"
    assert tanakh_map.language_of("Ezra.7.26", 0) == "arc"
    assert tanakh_map.language_of("Gen.31.47", 2) == "he"
    assert tanakh_map.language_of("Gen.31.47", 3) == "arc"
    assert tanakh_map.language_of("Gen.31.47", 5) == "he"


def test_the_share_is_of_running_words_not_of_distinct_ones(made: tuple[dict, Path]) -> None:
    _, path = made
    shares = coverage.chapter_map({"ארץ"}, path=path)
    # One of Genesis 1's three distinct forms, but three of its five running words.
    assert shares["Genesis 1"] == pytest.approx(3 / 5)
    # Jeremiah's Aramaic verse is out of its Hebrew count: one of three, not of five.
    assert shares["Jeremiah 10"] == pytest.approx(1 / 3)
    assert coverage.chapter_map(set(), path=path)["Genesis 1"] == 0.0


def test_a_chapter_in_another_language_is_not_measured(
    made: tuple[dict, Path], tmp_path: Path
) -> None:
    built, _ = made
    built["chapters"]["Daniel 2"]["language"] = "arc"
    path = tmp_path / "aramaic.json"
    path.write_text(json.dumps(built, ensure_ascii=False), encoding="utf-8")
    assert coverage.chapter_map({"מלכא", "דבר"}, path=path)["Daniel 2"] is None
    aramaic = coverage.chapter_map({"מלכא"}, "arc", path=path)
    assert aramaic["Daniel 2"] == pytest.approx(2 / 4)
    assert aramaic["Genesis 1"] is None


def test_an_estimate_weighs_each_chapter_by_its_bands(made: tuple[dict, Path]) -> None:
    _, path = made
    # Everything in this fixture is in the first band: ranks 1–100.
    assert coverage.chapter_estimate([0.5], path=path)["Genesis 1"] == pytest.approx(0.5)
    assert coverage.chapter_estimate([], path=path)["Genesis 1"] == 0.0
    assert coverage.chapter_estimate([2.0], path=path)["Genesis 1"] == 1.0


def test_no_file_or_another_shape_measures_nothing(tmp_path: Path) -> None:
    assert coverage.chapter_map({"ארץ"}, path=tmp_path / "absent.json") == {}
    wrong = tmp_path / "wrong.json"
    wrong.write_text(json.dumps({"version": 99, "chapters": {"Genesis 1": {}}}), encoding="utf-8")
    assert coverage.chapter_map({"ארץ"}, path=wrong) == {}


# -- the file that ships -------------------------------------------------------------


def test_the_shipped_file_is_every_chapter_in_the_hebrew_count() -> None:
    shipped = coverage.read_map()
    assert len(shipped.chapters) == 929
    by_part: dict[str, int] = {}
    for _name, part, count in shipped.books:
        by_part[part] = by_part.get(part, 0) + count
    assert by_part == {"torah": 187, "prophets": 380, "writings": 362}
    assert next(iter(shipped.chapters)) == "Genesis 1"
    assert list(shipped.chapters)[-1] == "II Chronicles 36"
    assert shipped.cuts == tanakh_map.CUTS


def test_the_shipped_file_marks_the_aramaic_chapters() -> None:
    shipped = coverage.read_map()
    aramaic = [ref for ref, chapter in shipped.chapters.items() if chapter.language == "arc"]
    assert aramaic == [
        "Daniel 2",
        "Daniel 3",
        "Daniel 4",
        "Daniel 5",
        "Daniel 6",
        "Daniel 7",
        "Ezra 4",
        "Ezra 5",
        "Ezra 6",
        "Ezra 7",
    ]
    shares = coverage.chapter_map(set(shipped.words["he"][:300]))
    assert all(shares[ref] is None for ref in aramaic)
    assert sum(share is not None for share in shares.values()) == 919
    # Jeremiah 10:11 is left out of Jeremiah 10's Hebrew, and the chapter is still shaded.
    assert shipped.chapters["Jeremiah 10"].parts["arc"].tokens > 0
    assert shares["Jeremiah 10"] is not None


def test_the_shipped_file_is_keyed_as_scripture_is_read() -> None:
    """Under `headword_of`'s bare headwords — the key a reader's marks are kept under."""
    shipped = coverage.read_map()
    genesis = shipped.chapters["Genesis 1"].parts["he"]
    have = {shipped.words["he"][at] for at in genesis.positions}
    assert {"ברא", "אלהים", "ארץ", "שמים", "ראשית"} <= have
    assert shipped.words["he"][0] == "את"


@pytest.mark.skipif(not oshb.available(), reason="the Hebrew Bible tagging is not on disk")
def test_the_shipped_file_is_what_a_recount_writes(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stale the day `headword_of` or the Aramaic table changes without a recount."""
    monkeypatch.setenv("TARGUM_MODEL_DIR", str(TAGGING.parent))
    oshb.forget()
    recount = tanakh_map.build(
        (osis, words)
        for code in dict.fromkeys(oshb.BOOKS.values())
        for osis, words in oshb.verses(code)
    )
    assert recount == json.loads(coverage.MAP.read_text(encoding="utf-8"))
