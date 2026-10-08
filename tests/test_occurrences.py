"""Where a word comes round, and where a reader met it (targum-internal#95, #96).

Built with no UI (David, 2026-09-27); the card asks it since 2026-09-28, behind
`TARGUM_OCCURRENCES`. What is under test here is the index: counts per text, across the
library, the places a reader met a word — which means inside a section they finished, and
nowhere else — the words of a root they met, and how the card names the places. The
route and the card are `test_occurrences_card.py`.
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
    family,
    finished_chapters,
    in_tanakh,
    met,
    places_named,
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


def test_a_chapter_is_read_when_every_verse_of_it_is_in_a_finished_section(
    tmp_path: Path,
) -> None:
    """The Tanakh map's check (targum-internal#144), named as the map names a
    chapter. A text that cuts a chapter in two finishes it with its second section."""
    folder = _jonah(tmp_path / "jonah")

    def folder_for(document: str) -> tuple[Path, str] | None:
        return (folder, "he") if document == "jonah-hash" else None

    assert finished_chapters([("jonah-hash", "1", 10)], folder_for) == {"Jonah 1"}
    both = [("jonah-hash", "1", 10), ("jonah-hash", "2", 20), ("elsewhere", "1", 5)]
    assert finished_chapters(both, folder_for) == {"Jonah 1", "Jonah 2"}
    assert finished_chapters(both, folder_for, language="arc") == set()
    assert finished_chapters([], folder_for) == set()


def test_half_a_chapter_is_not_a_chapter_read(tmp_path: Path, monkeypatch) -> None:
    """Jonah 1 cut across two sections: the first alone reads none of it."""
    import targum.occurrences as occurrences

    folder = _jonah(tmp_path / "jonah")
    counted = occurrences.text_occurrences(folder)
    assert counted is not None
    split = occurrences.Occurrences(
        places=((1, "Jonah 1:1"), (2, "Jonah 1:4"), (3, "Jonah 2:1")),
        lemmas=counted.lemmas,
    )
    monkeypatch.setattr(occurrences, "text_occurrences", lambda _folder: split)

    def folder_for(document: str) -> tuple[Path, str] | None:
        return (folder, "he")

    assert finished_chapters([("jonah-hash", "1", 10)], folder_for) == set()
    assert finished_chapters([("jonah-hash", "1", 10), ("jonah-hash", "2", 20)], folder_for) == {
        "Jonah 1"
    }


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


# -- what the card asks (behind TARGUM_OCCURRENCES, 2026-09-28) -------------------------

#: Two forms given one root, so a family has more than one member; a made-up root, since
#: what is under test is that the annotation's root is the one used, not what it is.
ROOTS = {"ים": "ימם", "דג": "ימם", "רוח": "רוח"}


def rooted(folder: Path) -> Path:
    """The annotation as a build leaves it for a verb: each token carrying its root."""
    tokens = json.loads((folder / "annotation.json").read_text(encoding="utf-8"))
    for found in tokens["tokens"].values():
        for token in found:
            if token["lemma"] in ROOTS:
                token["root"] = ROOTS[token["lemma"]]
    (folder / "annotation.json").write_text(json.dumps(tokens), encoding="utf-8")
    return folder


def test_a_text_keeps_the_root_its_annotation_gave_and_caches_it(tmp_path: Path) -> None:
    folder = rooted(_jonah(tmp_path / "jonah"))
    counted = text_occurrences(folder)
    assert counted is not None and counted.roots == ROOTS
    occurrences._cached.cache_clear()
    assert text_occurrences(folder) == counted, "read back from the cache, roots and all"


def test_a_cache_from_before_the_roots_is_counted_again(tmp_path: Path) -> None:
    """Version 1 had no roots. It is rebuilt, which is free: it is read off the annotation."""
    folder = rooted(_jonah(tmp_path / "jonah"))
    text_occurrences(folder)
    cached = json.loads((folder / OCCURRENCES).read_text(encoding="utf-8"))
    cached.update(version=1)
    del cached["roots"]
    (folder / OCCURRENCES).write_text(json.dumps(cached), encoding="utf-8")
    occurrences._cached.cache_clear()
    assert (text_occurrences(folder) or pytest.fail()).roots == ROOTS


def test_a_family_is_the_forms_of_a_root_met_in_finished_sections(tmp_path: Path) -> None:
    folder = rooted(_jonah(tmp_path / "jonah"))

    def folder_for(document: str) -> tuple[Path, str] | None:
        return (folder, "he") if document == "jonah-hash" else None

    one = [("jonah-hash", "1", 10)]
    both = [*one, ("jonah-hash", "2", 20)]
    assert family("ימם", one, folder_for) == ["ים"], "דג is in chapter 2, not yet finished"
    assert family("ימם", both, folder_for) == ["ים", "דג"]
    assert family("ימם", both, folder_for, language="arc") == []
    assert family("", both, folder_for) == [], "no root, no family"
    assert family("היה", both, folder_for) == [], "a form the annotation gave no root has none"


def meeting(document: str, section: int, ref: str, at: int) -> Meeting:
    return Meeting(document=document, section=section, ref=ref, count=1, at=at)


def test_the_card_names_verses_by_reference_and_the_rest_by_title() -> None:
    """Latest finish first; a text with no verses once, by its title, however many of its
    sections the word came round in; the page the reader is on is not a place they met
    it; three named, and how many more."""
    titles = {"jonah": "יונה", "news": "A Paper", "gone": ""}
    meetings = [
        meeting("jonah", 1, "Jonah 1:4", 10),
        meeting("news", 1, "p1", 20),
        meeting("news", 2, "part 1:2", 30),
        meeting("jonah", 2, "Jonah 2:1", 40),
        meeting("gone", 1, "", 45),
        meeting("ruth", 2, "Ruth 2:1", 50),
        meeting("talmud", 1, "Berakhot 2a:3", 60),
    ]
    named, more = places_named(meetings, lambda d: titles.get(d, ""))
    assert named == ["Berakhot 2a:3", "Ruth 2:1", "Jonah 2:1"]
    assert more == 2, "A Paper, once, and Jonah 1:4; a text with no title is not named"

    named, more = places_named(meetings, titles.__getitem__, leave_out=("jonah", 2), most=10)
    assert "Jonah 2:1" not in named and "Jonah 1:4" in named
    assert more == 0
    assert places_named([], str) == ([], 0)
