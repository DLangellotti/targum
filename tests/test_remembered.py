"""The shelf answers from what it kept, and works a text out again only when it changed.

Learn waited 31 s on the live box on 2026-09-14 because every request re-read every
reader's whole document, segmentation and translations to draw rows a few hundred bytes
long. These pin the saving and, harder, that a saving never shows a stale row.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from test_chapter_ui import book

from targum.models import Translation
from targum.remembered import SHELF
from targum.serve import Library


def refuse(*_args: object, **_kwargs: object) -> object:
    raise AssertionError("worked out again when nothing had changed")


def test_a_restart_draws_the_shelf_without_reading_the_texts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = Library(tmp_path).home(None)
    book(home / "book-he", chapters=5, translated=2)
    first = Library(tmp_path).readers(home)
    assert (home / "book-he" / SHELF).is_file()

    # A new process holds nothing in memory; only what was kept beside the reader.
    again = Library(tmp_path)
    monkeypatch.setattr(Library, "chapters", staticmethod(refuse))
    monkeypatch.setattr(Library, "targets", staticmethod(refuse))
    monkeypatch.setattr(Library, "_document_facts", staticmethod(refuse))
    monkeypatch.setattr(Library, "_own_difficulty", staticmethod(refuse))

    assert again.readers(home) == first


def test_buying_a_chapter_shows_on_the_next_request(tmp_path: Path) -> None:
    library = Library(tmp_path)
    home = library.home(None)
    book(home / "book-he", chapters=5, translated=2)
    assert library.readers(home)[0]["readyChapters"] == 2

    book(home / "book-he", chapters=5, translated=3)

    assert library.readers(home)[0]["readyChapters"] == 3


def test_a_translation_into_another_language_is_a_new_target(tmp_path: Path) -> None:
    library = Library(tmp_path)
    home = library.home(None)
    book(home / "book-he", chapters=3, translated=3)
    assert library.readers(home)[0]["targets"] == ["en"]

    Translation(
        name="Russian",
        document_hash="book",
        source_language="he",
        target_language="ru",
        provider="null",
        segments={"s1-0": "строка"},
    ).write(home / "book-he" / "translations" / "null.natural.ru.json")

    assert library.readers(home)[0]["targets"] == ["en", "ru"]


def test_a_retitled_document_is_read_again(tmp_path: Path) -> None:
    library = Library(tmp_path)
    home = library.home(None)
    book(home / "book-he", chapters=2, translated=1)
    assert library.readers(home)[0]["title"] == "A Book"

    document = home / "book-he" / "document.json"
    document.write_text(json.dumps({"title": "Another Book", "language": "he"}), "utf-8")

    assert library.readers(home)[0]["title"] == "Another Book"


def test_a_torn_saving_is_worked_out_again(tmp_path: Path) -> None:
    home = Library(tmp_path).home(None)
    book(home / "book-he", chapters=2, translated=1)
    first = Library(tmp_path).readers(home)

    (home / "book-he" / SHELF).write_text("{not json", encoding="utf-8")

    assert Library(tmp_path).readers(home) == first


@pytest.mark.skipif(os.geteuid() == 0, reason="root writes through a read-only folder")
def test_a_folder_it_cannot_write_still_gets_its_row(tmp_path: Path) -> None:
    library = Library(tmp_path)
    home = library.home(None)
    book(home / "book-he", chapters=2, translated=1)
    folder = home / "book-he"
    folder.chmod(0o555)
    try:
        rows = library.readers(home)
    finally:
        folder.chmod(0o755)

    assert rows[0]["title"] == "A Book"
    assert not (folder / SHELF).exists()
