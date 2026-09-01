"""Mapping PocketTorah's recordings onto the portions.

Nothing here touches the network or the aligner: the question is which file reads which
aliyah, and which readings correctly get no audio at all.
"""

from __future__ import annotations

import shutil
from datetime import date
from pathlib import Path

import pytest

from targum.parasha import calendar as cal
from targum.parasha import leyning

FIXTURES = Path(__file__).parent / "fixtures" / "parasha"

#: The shape of the collection, as archive.org actually lists it: a stem per portion,
#: seven numbered parts each, and the spellings that disagree with Hebcal's.
NAMES = [
    *(f"Bereshit-{n}.mp3" for n in range(1, 8)),
    *(f"Noach-{n}.mp3" for n in range(1, 8)),
    *(f"AchreiMot-{n}.mp3" for n in range(1, 8)),
    *(f"KiTisa-{n}.mp3" for n in range(1, 8)),
    *(f"Nitzavim-{n}.mp3" for n in range(1, 8)),
    *(f"Vayeilech-{n}.mp3" for n in range(1, 8)),
    *(f"Matot-{n}.mp3" for n in range(1, 8)),
    *(f"Masei-{n}.mp3" for n in range(1, 8)),
    "3megillot-1.mp3",
    "PocketTorah.pdf",
    "cover.jpg",
]


@pytest.fixture
def corpus(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("TARGUM_PARASHA_DIR", str(tmp_path))
    (tmp_path / "calendar").mkdir(parents=True)
    for one in FIXTURES.glob("*.json"):
        shutil.copy(one, tmp_path / "calendar" / one.name)
    return tmp_path


def have() -> dict[str, dict[int, str]]:
    return leyning.stems(NAMES)


def test_only_the_numbered_mp3s_are_taken() -> None:
    grouped = have()
    assert "pockettorah" not in grouped, "a PDF is not a recording"
    assert "cover" not in grouped
    assert set(grouped["bereshit"]) == set(range(1, 8))


def test_the_two_spellings_of_a_name_meet_in_the_middle() -> None:
    """Hebcal writes "Achrei Mot" and "Ki Tisa"; PocketTorah writes them closed up."""
    grouped = have()
    assert "achreimot" in grouped
    assert "kitisa" in grouped
    assert leyning._flat("Achrei Mot") == "achreimot"
    assert leyning._flat("Ki Tisa") == "kitisa"
    assert leyning._flat("V'Zot HaBerachah") == "vzothaberachah"


def test_a_single_portion_finds_its_seven_files(corpus: Path) -> None:
    reading = cal.for_shabbat(date(2026, 1, 3), cal.Schedule.diaspora)
    assert reading is not None and reading.name == "Vayechi"
    # Vayechi is not in the fixture collection, so it is silent rather than wrong.
    assert leyning.files_for(reading, have()) == {}

    made_up = cal.always()[0]
    assert made_up.name == "V'Zot HaBerachah"
    assert leyning.files_for(made_up, have()) == {}, "not in this collection either"


def test_a_doubled_week_is_never_matched_up_file_for_file(corpus: Path) -> None:
    """The trap. PocketTorah has Nitzavim and Vayeilech separately, and the combined
    reading divides the same verses into seven aliyot in different places — so pairing
    file 3 with aliyah 3 would put the wrong sound under most of the sections."""
    reading = cal.for_shabbat(date(2026, 9, 5), cal.Schedule.diaspora)
    assert reading is not None and reading.doubled
    grouped = have()
    assert "nitzavim" in grouped and "vayeilech" in grouped
    assert leyning.files_for(reading, grouped) == {}


def test_a_doubled_week_takes_both_halves_whole_and_in_order(corpus: Path) -> None:
    """What it does instead: the fourteen files are one continuous reading of exactly
    these verses, so they are joined and cut where this week actually divides."""
    reading = cal.for_shabbat(date(2026, 9, 5), cal.Schedule.diaspora)
    assert reading is not None
    names = leyning.halves_of(reading, have())
    assert len(names) == 14
    assert names[:2] == ["Nitzavim-1.mp3", "Nitzavim-2.mp3"]
    assert names[6] == "Nitzavim-7.mp3", "the first portion runs out before the second starts"
    assert names[7] == "Vayeilech-1.mp3"
    assert names[-1] == "Vayeilech-7.mp3"


def test_a_single_portion_is_not_sent_down_the_doubled_path(corpus: Path) -> None:
    reading = cal.for_shabbat(date(2026, 1, 3), cal.Schedule.diaspora)
    assert reading is not None and not reading.doubled
    assert leyning.halves_of(reading, have()) == []


def test_a_doubled_week_missing_one_half_is_silent(corpus: Path) -> None:
    """Half a reading is worse than none: the second portion would simply stop."""
    reading = cal.for_shabbat(date(2026, 9, 5), cal.Schedule.diaspora)
    assert reading is not None
    only_first = {k: v for k, v in have().items() if k != "vayeilech"}
    assert leyning.halves_of(reading, only_first) == []


def test_a_doubled_week_with_a_gap_in_one_half_is_silent(corpus: Path) -> None:
    """Files 1, 2 and 4 are not a reading — the join would skip what is missing without
    saying so, and every span after it would be wrong."""
    reading = cal.for_shabbat(date(2026, 9, 5), cal.Schedule.diaspora)
    assert reading is not None
    gapped = dict(have())
    gapped["vayeilech"] = {1: "Vayeilech-1.mp3", 2: "Vayeilech-2.mp3", 4: "Vayeilech-4.mp3"}
    assert leyning.halves_of(reading, gapped) == []


def test_a_festival_gets_no_audio(corpus: Path) -> None:
    reading = cal.for_shabbat(date(2026, 5, 23), cal.Schedule.diaspora)
    assert reading is not None
    assert reading.kind is cal.ReadingKind.festival
    assert leyning.files_for(reading, have()) == {}


def test_a_portion_missing_a_part_is_silent_rather_than_partial() -> None:
    """Six aliyot of seven is a reader whose last section goes quiet with no warning."""
    short = leyning.stems([f"Bereshit-{n}.mp3" for n in range(1, 7)])
    made = cal.always()[0]
    assert len(made.aliyot) == 7
    assert len(short["bereshit"]) == 6
    # Stand the fixture's name in for the reading's, to ask the length question alone.
    assert leyning.files_for(made, {"vzothaberachah": short["bereshit"]}) == {}


def test_the_licence_is_recorded_and_is_not_no_derivatives() -> None:
    """The audio bar: ND is out because the pipeline makes derivatives. SA is in."""
    assert leyning.LICENCE == "CC BY-SA 3.0"
    assert "ND" not in leyning.LICENCE
    assert leyning.CREDIT
    assert leyning.LICENCE_URL.startswith("https://creativecommons.org/")


def test_both_kinds_of_reading_reach_the_attacher(corpus: Path) -> None:
    """The guard the CLI uses, asserted here rather than only in the CLI.

    `parasha leyning` skipped any reading `files_for` had nothing for — and `files_for`
    returns nothing for every doubled week by design, so `halves_of` and the whole
    re-division path were unreachable from the only command that calls `attach`. Every
    doubled week would have stayed silent. Both questions have to be asked.
    """
    grouped = have()
    doubled = cal.for_shabbat(date(2026, 9, 5), cal.Schedule.diaspora)
    single = cal.always()[0]
    assert doubled is not None and doubled.doubled

    def reaches(reading: cal.Reading) -> bool:
        return bool(leyning.files_for(reading, grouped)) or bool(
            leyning.halves_of(reading, grouped)
        )

    assert reaches(doubled), "a doubled week has halves even though it has no files"
    assert not leyning.files_for(doubled, grouped), "and asking only that question skips it"

    # A festival has neither, and is correctly silent.
    festival = cal.for_shabbat(date(2026, 5, 23), cal.Schedule.diaspora)
    assert festival is not None and festival.kind is cal.ReadingKind.festival
    assert not reaches(festival)
    assert not reaches(single), "V'Zot HaBerachah is not in this fixture collection"
