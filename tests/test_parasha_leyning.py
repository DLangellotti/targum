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


def test_the_download_cache_is_not_inside_the_recordings_shelf(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """PocketTorah's own mp3s are held between runs, and they are not a recording.

    They used to be held at `<recordings>/pockettorah`, which is a folder in the shelf
    with no `recording.json` in it. `ship-audio.sh` refuses the whole shelf on one of
    those — rightly, because a half-cut book and a bag of source files look identical
    from outside — so the first ship after somebody ran `parasha leyning` stopped dead
    and carried nothing. It cost a deploy on 2026-09-04.
    """
    from targum.parasha.leyning import downloads_root
    from targum.recording import index as recording_index

    monkeypatch.setenv("TARGUM_RECORDING_DIR", str(tmp_path / "targum-out" / "recordings"))
    shelf = recording_index.root()
    cache = downloads_root()
    assert shelf not in cache.parents, f"{cache} is inside the shelf at {shelf}"
    assert cache.name == "pockettorah"


def test_the_aligner_s_words_are_kept_rather_than_collapsed(tmp_path, monkeypatch) -> None:
    """targum-internal#329. Each verse keeps one clock per word, in order, and the verse
    span is still there, read off them. The words handed to the aligner are exactly the
    ones handed to it before the change, so an alignment already cached is found again
    and re-attaching a portion costs no alignment at all."""
    from targum.recording.models import verse_spans
    from targum.vocalize import strip_taamim

    monkeypatch.setenv("TARGUM_CACHE_DIR", str(tmp_path / "cache"))
    heard: list[list[str]] = []

    class Aligner:
        def available(self) -> tuple[bool, str]:
            return True, "fake"

        def align(self, audio: Path, words: list[str], language: str) -> list[tuple]:
            heard.append(list(words))
            return [(n * 1.0, n + 0.8, -0.1) for n in range(len(words))]

    monkeypatch.setattr(leyning, "CtcAligner", Aligner)
    audio = tmp_path / "aliyah-01.mp3"
    audio.write_bytes(b"ID3not-really-audio")
    verses = [
        ("Genesis 1:1", "בְּרֵאשִׁ֖ית בָּרָ֣א אֱלֹהִ֑ים אֵ֥ת הַשָּׁמַ֖יִם וְאֵ֥ת הָאָֽרֶץ׃"),
        ("Genesis 1:3", "וַיֹּ֥אמֶר אֱלֹהִ֖ים יְהִ֣י א֑וֹר וַֽיְהִי־אֽוֹר׃"),
    ]
    clocks = leyning.clocks_for(audio, verses, lambda _: None)
    assert heard == [[word for _, text in verses for word in strip_taamim(text).split()]]
    assert [len(rows) for rows in clocks.values()] == [7, 5]
    assert clocks["Genesis 1:3"][0] == [7.0, 7.8]
    assert verse_spans(clocks) == {"Genesis 1:1": [0.0, 6.8], "Genesis 1:3": [7.0, 11.8]}

    again = leyning.clocks_for(audio, verses, lambda _: None)
    assert again == clocks and len(heard) == 1, "the second attach reads the cache"


def test_the_names_that_do_not_meet_closed_up_are_respelled() -> None:
    """targum-internal#413. Hebcal's "Va'etchanan" and "V'Zot HaBerachah" are
    "Vaethanan" and "VezotHaberakhah" in the collection; flattening alone left both
    portions silent with their files on the disk."""
    grouped = leyning.stems(
        [f"Vaethanan-{n}.mp3" for n in range(1, 8)]
        + [f"VezotHaberakhah-{n}.mp3" for n in range(1, 8)]
    )
    made = cal.always()[0]
    assert made.name == "V'Zot HaBerachah"
    assert leyning.files_for(made, grouped)[1] == "VezotHaberakhah-1.mp3"
    assert leyning.pocket_name("Va'etchanan") == "vaethanan"
    assert leyning.pocket_name("Noach") == "noach"


def test_a_haftarah_file_is_found_and_is_not_an_aliyah() -> None:
    files = ["Noach-1.mp3", "Noach-H.mp3", "Lech-Lecha-H.mp3", "haftarah-3.mp3", "cover.jpg"]
    assert leyning.haftarah_files(files) == {
        "noach": "Noach-H.mp3",
        "lechlecha": "Lech-Lecha-H.mp3",
    }
    assert "H" not in str(leyning.stems(files)), "the haftarah is not an eighth aliyah"


def test_a_haftarah_file_that_reads_something_else_is_refused(tmp_path, monkeypatch) -> None:
    """PocketTorah's choice of haftarah is not always the corpus's, so the match is
    measured: an alignment scoring below the floor leaves nothing on the shelf, not even
    an empty folder, which `ship-audio` would refuse the whole shelf over."""
    from types import SimpleNamespace

    from targum.models import BlockKind

    monkeypatch.setenv("TARGUM_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("TARGUM_RECORDING_DIR", str(tmp_path / "recordings"))
    score = {"value": -9.0}

    class Aligner:
        def available(self) -> tuple[bool, str]:
            return True, "fake"

        def align(self, audio: Path, words: list[str], language: str) -> list[tuple]:
            return [(n * 1.0, n + 0.8, score["value"]) for n in range(len(words))]

    monkeypatch.setattr(leyning, "CtcAligner", Aligner)
    keep = tmp_path / "downloads"
    keep.mkdir()
    (keep / "Noach-H.mp3").write_bytes(b"ID3not-really-audio")
    verse = SimpleNamespace(kind=BlockKind.verse, ref="Isaiah 54:1", text="רָנִּי עֲקָרָה לֹא יָלָדָה")
    portion = SimpleNamespace(
        segmented=SimpleNamespace(segments=[verse]),
        document=SimpleNamespace(source="sefaria:Isaiah 54:1-55:5"),
    )

    refused = leyning.attach_haftarah(
        "Noach", portion, "Noach-H.mp3", downloads=keep, notify=lambda _: None
    )
    assert refused is None
    assert not (tmp_path / "recordings").exists() or not any((tmp_path / "recordings").iterdir())

    score["value"] = -1.0
    (keep / "Noach-H.mp3").write_bytes(b"ID3not-really-audio, again")
    made = leyning.attach_haftarah(
        "Noach", portion, "Noach-H.mp3", downloads=keep, notify=lambda _: None
    )
    assert made is not None and len(made.parts) == 1
    assert made.parts[0].audio == "haftarah.mp3"
    assert made.parts[0].spans == {"Isaiah 54:1": [0.0, 3.8]}
    assert leyning.attached("sefaria:Isaiah 54:1-55:5")


def test_a_doubled_week_is_clocked_a_file_at_a_time(tmp_path, monkeypatch) -> None:
    """targum-internal#413. One pass of `forced_align` over a forty-minute doubled week
    died with SIGSEGV (Tazria-Metzora, Chukat-Balak). Each file is one aliyah of one half,
    so each is aligned against that aliyah's verses alone and moved along by the length
    of the files before it — the clock one pass over the joined file would have given."""
    from types import SimpleNamespace

    from targum.models import BlockKind
    from targum.parasha.calendar import Aliyah

    monkeypatch.setenv("TARGUM_CACHE_DIR", str(tmp_path / "cache"))
    heard: list[tuple[str, int]] = []

    class Aligner:
        def available(self) -> tuple[bool, str]:
            return True, "fake"

        def align(self, audio: Path, words: list[str], language: str) -> list[tuple]:
            heard.append((audio.name, len(words)))
            return [(n * 1.0, n + 0.5, -0.1) for n in range(len(words))]

    monkeypatch.setattr(leyning, "CtcAligner", Aligner)

    def verse(ref: str) -> SimpleNamespace:
        return SimpleNamespace(kind=BlockKind.verse, ref=ref, text="אֵ֥ת הַשָּׁמַ֖יִם")

    refs = ["Leviticus 12:1", "Leviticus 12:2", "Leviticus 14:1", "Leviticus 14:2"]
    portion = SimpleNamespace(segmented=SimpleNamespace(segments=[verse(r) for r in refs]))
    halves = [
        SimpleNamespace(aliyot=[Aliyah(1, "Leviticus", "12:1", "12:2", 2)]),
        SimpleNamespace(aliyot=[Aliyah(1, "Leviticus", "14:1", "14:2", 2)]),
    ]
    files = [tmp_path / "Tazria-1.mp3", tmp_path / "Metzora-1.mp3"]
    for one in files:
        one.write_bytes(b"ID3" + one.name.encode())

    clocks = leyning._clocks_by_file(halves, portion, files, lambda _: 100.0, lambda _: None)
    assert clocks is not None
    assert heard == [("Tazria-1.mp3", 4), ("Metzora-1.mp3", 4)], "a file at a time"
    assert clocks["Leviticus 12:1"] == [[0.0, 0.5], [1.0, 1.5]]
    assert clocks["Leviticus 14:1"][0] == [100.0, 100.5], "after the first file's length"
    assert clocks["Leviticus 14:2"][-1] == [103.0, 103.5]

    assert leyning._clocks_by_file(halves, portion, files[:1], lambda _: 1.0, print) is None, (
        "files that do not pair up with the aliyot fall back to the single pass"
    )
