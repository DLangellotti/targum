"""Real texts, not toy ones.

Everything here is drawn from the M1 fixture: unvocalized Hebrew carrying Latin script,
Gregorian years, Hebrew year abbreviations, maqaf and geresh.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from targum.pipeline import Build
from targum.render import isolate


@pytest.fixture
def reader(tmp_path: Path, hebrew_source: Path, fake_segmenter: object) -> str:
    builder = Build(
        str(hebrew_source),
        target_language="en",
        provider_name="null",
        out=tmp_path / "out",
        segmenter=fake_segmenter,  # type: ignore[arg-type]
    )
    return builder.run().index.read_text(encoding="utf-8")


def test_the_declaration_builds(reader: str) -> None:
    assert "מדינת ישראל" in reader
    assert 'dir="rtl"' in reader


def test_years_are_isolated_inside_hebrew(reader: str) -> None:
    # Without <bdi> the closing paren jumps to the wrong end of the line.
    assert "<bdi>1897</bdi>" in reader
    assert "<bdi>1948</bdi>" in reader


def test_gershayim_survives_rendering(reader: str) -> None:
    assert "תש״ח" in reader
    assert "ה׳ אייר" in reader


def test_maqaf_is_not_mistaken_for_a_hyphen(reader: str) -> None:
    assert "בארץ־ישראל" in reader


def test_latin_names_inside_hebrew_are_isolated() -> None:
    out = str(isolate("החברה Magma Devs נוסדה", "rtl"))
    assert "<bdi>Magma Devs</bdi>" in out


def test_a_hebrew_date_range_keeps_its_numbers_together() -> None:
    out = str(isolate("ב־29 בנובמבר 1947 קיבלה", "rtl"))
    assert "<bdi>29</bdi>" in out and "<bdi>1947</bdi>" in out


def test_niqqud_passes_through(tmp_path: Path, fake_segmenter: object) -> None:
    source = tmp_path / "vocalized.txt"
    source.write_text("בְּרֵאשִׁית בָּרָא אֱלֹהִים.", encoding="utf-8")
    builder = Build(
        str(source),
        target_language="en",
        provider_name="null",
        out=tmp_path / "out",
        segmenter=fake_segmenter,  # type: ignore[arg-type]
    )
    assert "בְּרֵאשִׁית" in builder.run().index.read_text(encoding="utf-8")
