"""Where a word comes round, and where a reader met it (targum-internal#95, #96).

Built with no UI (David, 2026-09-27), so what is under test is the index a later card
will ask: counts per text, across the library, and the places a reader met a word —
which means inside a section they finished, and nowhere else.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from targum import occurrences
from targum.accounts import Store
from targum.cli import app
from targum.coverage import build_index, read_index, write_index
from targum.models import BlockKind, Segment, SegmentedDocument
from targum.occurrences import (
    OCCURRENCES,
    Meeting,
    Place,
    count_text,
    in_tanakh,
    met,
    text_occurrences,
)

# Jonah, cut down: two chapters, each a section of the reader's page.
VERSES: list[tuple[str, str, list[tuple[str, str]]]] = [
    ("heading", "", []),
    (
        "verse",
        "Jonah 1:1",
        [("היה", "VERB"), ("דבר", "NOUN"), ("יונה", "PROPN"), ("בן", "NOUN")],
    ),
    ("verse", "Jonah 1:4", [("רוח", "NOUN"), ("ים", "NOUN"), ("רוח", "NOUN"), ("2", "NUM")]),
    ("heading", "", []),
    ("verse", "Jonah 2:1", [("דג", "NOUN"), ("ים", "NOUN")]),
]


def _jonah(folder: Path, *, sections: int = 2) -> Path:
    """A built text laid out the way a build leaves it: document, segments, annotation,
    and one reader page a section."""
    folder.mkdir(parents=True)
    segments = []
    tokens: dict[str, list[dict[str, object]]] = {}
    for n, (kind, ref, words) in enumerate(VERSES):
        sid = f"{n:04d}.000-x"
        text = "ספר יונה" if kind == "heading" else " ".join(w for w, _ in words)
        segments.append(
            Segment(
                id=sid,
                block_id=f"b{n:04d}",
                block_index=n,
                index=0,
                kind=BlockKind.heading if kind == "heading" else BlockKind.verse,
                level=2 if kind == "heading" else None,
                text=text,
                ref=ref,
            )
        )
        if words:
            tokens[sid] = [
                {"start": 0, "end": 1, "surface": w, "lemma": w, "pos": pos} for w, pos in words
            ]
    document = SegmentedDocument(
        document_hash="jonah-hash", language="he", segmenter="test", segments=segments
    )
    (folder / "segments.json").write_text(document.model_dump_json(), encoding="utf-8")
    (folder / "annotation.json").write_text(json.dumps({"tokens": tokens}), encoding="utf-8")
    (folder / "document.json").write_text(
        json.dumps({"source": "test:jonah", "content_hash": "jonah-hash", "language": "he"}),
        encoding="utf-8",
    )
    reader = folder / "reader"
    reader.mkdir()
    for number in range(1, sections + 1):
        (reader / f"sec-{number:04d}.html").write_text("", encoding="utf-8")
    return folder


@pytest.fixture(autouse=True)
def _fresh_cache() -> None:
    occurrences._cached.cache_clear()


def test_a_text_counts_each_word_where_it_comes_round(tmp_path: Path) -> None:
    counted = count_text(_jonah(tmp_path / "jonah"))
    assert counted is not None
    assert counted.count("רוח") == 2
    assert counted.count("ים") == 2
    assert counted.where("ים") == [
        Place(section=1, ref="Jonah 1:4", count=1),
        Place(section=2, ref="Jonah 2:1", count=1),
    ]
    assert counted.where("רוח") == [Place(section=1, ref="Jonah 1:4", count=2)]


def test_names_and_numbers_are_not_counted(tmp_path: Path) -> None:
    """The same words `coverage.lemmas` counts, so the two never disagree about a text."""
    counted = count_text(_jonah(tmp_path / "jonah"))
    assert counted is not None
    assert counted.count("יונה") == 0
    assert "2" not in counted.lemmas


def test_a_text_rendered_whole_is_one_section(tmp_path: Path) -> None:
    counted = count_text(_jonah(tmp_path / "jonah", sections=1))
    assert counted is not None
    assert {place.section for place in counted.where("ים")} == {1}


def test_a_text_with_no_annotation_is_not_counted(tmp_path: Path) -> None:
    folder = _jonah(tmp_path / "jonah")
    (folder / "annotation.json").unlink()
    assert count_text(folder) is None
    assert text_occurrences(folder) is None


def test_the_cache_is_written_beside_the_text_and_read_back(tmp_path: Path) -> None:
    folder = _jonah(tmp_path / "jonah")
    first = text_occurrences(folder)
    assert (folder / OCCURRENCES).is_file()
    occurrences._cached.cache_clear()
    assert text_occurrences(folder) == first


def test_a_rewritten_annotation_is_counted_again(tmp_path: Path) -> None:
    """Derivable, never a source of truth: the cache is stamped with what it read."""
    folder = _jonah(tmp_path / "jonah")
    assert (text_occurrences(folder) or pytest.fail()).count("דג") == 1
    tokens = json.loads((folder / "annotation.json").read_text(encoding="utf-8"))
    tokens["tokens"]["0004.000-x"].append({"start": 2, "end": 3, "lemma": "דג", "pos": "NOUN"})
    (folder / "annotation.json").write_text(json.dumps(tokens), encoding="utf-8")
    assert (text_occurrences(folder) or pytest.fail()).count("דג") == 2


def test_the_library_index_carries_counts_and_answers_per_text(tmp_path: Path) -> None:
    index = build_index(
        {"jonah": ["ים", "רוח", "דג"], "ruth": ["שדה", "ים"], "old": ["ים"]},
        {"jonah": {"ים": 4, "רוח": 2, "דג": 3}, "ruth": {"שדה": 7, "ים": 1}},
    )
    path = tmp_path / "lemmas.json"
    write_index(path, index)
    back = read_index(path)
    assert back.count_in("jonah", "ים") == 4
    assert back.count_in("ruth", "רוח") == 0, "counted, and not there"
    assert back.count_in("old", "ים") is None, "indexed before counts: not counted"
    assert back.count_in("nowhere", "ים") is None
    assert back.count_across("ים") == (5, 2)
    assert back.count_across("ים", ["ruth"]) == (1, 1)
    assert back.count_across("nothing") == (0, 0)


def test_an_index_without_counts_still_reads(tmp_path: Path) -> None:
    """A file an older targum wrote: the version did not move, and it reads uncounted."""
    path = tmp_path / "lemmas.json"
    path.write_text(json.dumps({"version": 1, "words": ["ים"], "texts": {"a": [0]}}), "utf-8")
    back = read_index(path)
    assert back.lemmas_for("a") == ["ים"]
    assert back.count_in("a", "ים") is None


def test_a_row_of_counts_that_does_not_line_up_is_dropped(tmp_path: Path) -> None:
    path = tmp_path / "lemmas.json"
    path.write_text(
        json.dumps(
            {"version": 1, "words": ["ים", "רוח"], "texts": {"a": [0, 1]}, "counts": {"a": [3]}}
        ),
        "utf-8",
    )
    assert read_index(path).count_in("a", "ים") is None


def test_the_tanakh_is_counted_without_a_build() -> None:
    """The chapter file ships in the package, so this needs nothing on the shelf."""
    assert in_tanakh("ים") > 300
    assert in_tanakh("not a word") == 0
    assert in_tanakh("ים", language="arc") < in_tanakh("ים")


def test_a_reader_met_a_word_only_in_sections_they_finished(tmp_path: Path) -> None:
    folder = _jonah(tmp_path / "jonah")

    def folder_for(document: str) -> tuple[Path, str] | None:
        return (folder, "he") if document == "jonah-hash" else None

    finished = [("jonah-hash", "1", 100), ("elsewhere", "3", 50)]
    assert met("ים", finished, folder_for) == [
        Meeting(document="jonah-hash", section=1, ref="Jonah 1:4", count=1, at=100)
    ]
    assert met("דג", finished, folder_for) == [], "chapter 2 was never finished"
    assert met("ים", finished, folder_for, language="arc") == []


def test_met_reads_the_store_s_finished_sections(tmp_path: Path) -> None:
    """End to end from the `section` rows a finished chapter syncs, un-finishes included."""
    folder = _jonah(tmp_path / "jonah")
    store = Store(tmp_path / "db")
    person, _ = store.finish_sign_in(store.start_sign_in("reader@example.com"))  # type: ignore[misc]
    store.push(
        person,
        {
            "sections": [
                {"hash": "jonah-hash", "section": "1", "at": 10, "seen": 10},
                {"hash": "jonah-hash", "section": "2", "at": 20, "seen": 20},
            ]
        },
    )
    store.push(
        person, {"sections": [{"hash": "jonah-hash", "section": "2", "gone": 1, "seen": 30}]}
    )

    finished = store.finished(person.id)
    assert finished == [("jonah-hash", "1", 10)]
    places = met("ים", finished, lambda h: (folder, "he") if h == "jonah-hash" else None)
    assert [(m.ref, m.count) for m in places] == [("Jonah 1:4", 1)]
    assert store.finished(None) == []


def test_catalogue_lemmas_writes_the_counts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixtures = Path(__file__).parent / "fixtures" / "catalogue.json"
    monkeypatch.setenv("TARGUM_CATALOGUE", str(fixtures))
    out = tmp_path / "targums"
    folder = _jonah(out / "shared" / "declaration")
    (folder / "document.json").write_text(
        json.dumps({"source": "test:il-declaration"}), encoding="utf-8"
    )
    written = tmp_path / "var" / "catalogue-lemmas.json"

    got = CliRunner().invoke(app, ["catalogue-lemmas", "--out", str(out), "--write", str(written)])

    assert got.exit_code == 0, got.output
    index = read_index(written)
    assert index.count_in("il-declaration", "רוח") == 2
    assert index.count_across("ים") == (2, 1)
    assert (folder / OCCURRENCES).is_file(), "the text's places are left cached"
