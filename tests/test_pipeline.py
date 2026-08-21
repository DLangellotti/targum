from __future__ import annotations

import json
from pathlib import Path

import pytest

from targum.errors import TargumError
from targum.models import Document, Style, Translation, read_artifact
from targum.pipeline import Build


def build(source: Path, out: Path, segmenter: object, **kwargs: object) -> Build:
    return Build(
        str(source),
        target_language="en",
        provider_name="null",
        out=out,
        segmenter=segmenter,  # type: ignore[arg-type]
        **kwargs,  # type: ignore[arg-type]
    )


@pytest.fixture
def source(tmp_path: Path) -> Path:
    path = tmp_path / "declaration.md"
    path.write_text(
        "# הכרזה\n\nבארץ־ישראל קם העם היהודי. בה עוצבה דמותו.\n\nבשנת תרנ״ז נתכנס הקונגרס.\n",
        encoding="utf-8",
    )
    return path


def test_writes_every_artifact(source: Path, tmp_path: Path, fake_segmenter: object) -> None:
    out = tmp_path / "out"
    result = build(source, out, fake_segmenter).run()

    assert (out / "document.json").exists()
    assert (out / "segments.json").exists()
    assert (out / "translations" / "null.natural.en.json").exists()
    assert result.index.exists()


def test_artifacts_are_readable_json(source: Path, tmp_path: Path, fake_segmenter: object) -> None:
    out = tmp_path / "out"
    build(source, out, fake_segmenter).run()
    data = json.loads((out / "document.json").read_text(encoding="utf-8"))
    from targum.models import SCHEMA_VERSION

    assert data["schema_version"] == SCHEMA_VERSION
    assert data["language"] == "he"


def test_a_second_run_redoes_nothing(source: Path, tmp_path: Path, fake_segmenter: object) -> None:
    out = tmp_path / "out"
    build(source, out, fake_segmenter).run()
    again = build(source, out, fake_segmenter).run()
    assert "document" in again.reused
    assert "segments" in again.reused
    assert any(item.startswith("translation") for item in again.reused)


def test_force_redoes_everything(source: Path, tmp_path: Path, fake_segmenter: object) -> None:
    out = tmp_path / "out"
    build(source, out, fake_segmenter).run()
    again = build(source, out, fake_segmenter, force=True).run()
    assert again.reused == []


def test_a_hand_edited_document_wins(source: Path, tmp_path: Path, fake_segmenter: object) -> None:
    # Fixing a bad extraction by editing the artifact and rerunning is how this is
    # meant to work, so the next run must not overwrite the edit.
    out = tmp_path / "out"
    build(source, out, fake_segmenter).run()

    path = out / "document.json"
    document = read_artifact(Document, path)
    assert document is not None
    document.blocks[1].text = "טקסט מתוקן."
    document.write(path)

    result = build(source, out, fake_segmenter).run()
    assert "document (edited)" in result.reused
    assert any("טקסט מתוקן" in segment.text for segment in result.segmented.segments)


def test_editing_the_document_reruns_segmentation(
    source: Path, tmp_path: Path, fake_segmenter: object
) -> None:
    out = tmp_path / "out"
    first = build(source, out, fake_segmenter).run()
    path = out / "document.json"
    document = read_artifact(Document, path)
    assert document is not None
    document.blocks.pop()
    document.write(path)

    second = build(source, out, fake_segmenter).run()
    assert "segments" not in second.reused
    assert len(second.segmented.segments) < len(first.segmented.segments)


def test_a_schema_bump_invalidates_artifacts(
    source: Path, tmp_path: Path, fake_segmenter: object
) -> None:
    out = tmp_path / "out"
    build(source, out, fake_segmenter).run()
    path = out / "segments.json"
    stale = json.loads(path.read_text(encoding="utf-8"))
    stale["schema_version"] = 0
    path.write_text(json.dumps(stale), encoding="utf-8")

    result = build(source, out, fake_segmenter).run()
    assert "segments" not in result.reused


def test_the_translation_cache_survives_a_new_output_directory(
    source: Path, tmp_path: Path, fake_segmenter: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TARGUM_CACHE_DIR", str(tmp_path / "cache"))
    build(source, tmp_path / "one", fake_segmenter).run()
    elsewhere = build(source, tmp_path / "two", fake_segmenter).run()
    assert "translation (cache)" in elsewhere.reused


def test_style_is_part_of_the_cache_key(
    source: Path, tmp_path: Path, fake_segmenter: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TARGUM_CACHE_DIR", str(tmp_path / "cache"))
    build(source, tmp_path / "one", fake_segmenter).run()
    other = build(source, tmp_path / "two", fake_segmenter, style=Style.direct).run()
    assert "translation (cache)" not in other.reused


def test_translation_covers_every_segment(
    source: Path, tmp_path: Path, fake_segmenter: object
) -> None:
    result = build(source, tmp_path / "out", fake_segmenter).run()
    assert set(result.translation.segments) == {s.id for s in result.segmented.segments}


def test_empty_source_says_so(tmp_path: Path, fake_segmenter: object) -> None:
    empty = tmp_path / "empty.txt"
    empty.write_text("   \n\n  \n", encoding="utf-8")
    with pytest.raises(TargumError, match="No text found"):
        build(empty, tmp_path / "out", fake_segmenter).run()


def test_default_output_directory_is_named_for_the_source(
    source: Path, tmp_path: Path, fake_segmenter: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    builder = Build(
        str(source),
        target_language="en",
        provider_name="null",
        segmenter=fake_segmenter,  # type: ignore[arg-type]
    )
    result = builder.run()
    assert result.out_dir == tmp_path / "targum-out" / "declaration-he"


def test_translation_carries_its_provenance(
    source: Path, tmp_path: Path, fake_segmenter: object
) -> None:
    out = tmp_path / "out"
    build(source, out, fake_segmenter, style=Style.direct).run()
    translation = read_artifact(Translation, out / "translations" / "null.direct.en.json")
    assert translation is not None
    assert translation.provider == "null"
    assert translation.style is Style.direct
    assert translation.kind == "machine"


def test_a_new_ingester_version_re_ingests(
    source: Path, tmp_path: Path, fake_segmenter: object
) -> None:
    """An ingester change is stale extraction, not a hand edit, so the artifact loses.

    Without this the two cases are indistinguishable by hash and every improvement to
    an ingester is invisible on documents built before it.
    """
    out = tmp_path / "out"
    build(source, out, fake_segmenter).run()

    path = out / "document.json"
    document = read_artifact(Document, path)
    assert document is not None
    document.ingester = "markdown/0"
    document.blocks[1].text = "stale extraction"
    document.content_hash = document.recompute_hash()
    document.write(path)

    result = build(source, out, fake_segmenter).run()
    assert "document (edited)" not in result.reused
    assert not any("stale extraction" in s.text for s in result.segmented.segments)


def test_a_changed_source_file_wins_over_the_artifact(
    source: Path, tmp_path: Path, fake_segmenter: object
) -> None:
    """Editing document.json is a fix. Editing the source is a different text."""
    out = tmp_path / "out"
    build(source, out, fake_segmenter).run()
    source.write_text("# אחר\n\nטקסט אחר לגמרי.\n", encoding="utf-8")

    result = build(source, out, fake_segmenter).run()
    assert "document (edited)" not in result.reused
    assert any("לגמרי" in segment.text for segment in result.segmented.segments)
