"""A multi-part text's contents page is a page of the desk (design.md §12, "A contents page
is a page of its own, not a small reader", 2026-10-09; boards PartsBookA, PartsVideoA and
PartsTanakh).

The build writes what the page is drawn from, `contents.json`, beside the reader's pages;
the server answers the reader's own `index.html` with the page, drawn for whoever asks.
A reader built before the change, and one opened off a disk, keep the page the build
wrote.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from test_chapter_ui import book
from test_serve import Postbox, call, get, postbox, served, sign_in  # noqa: F401

from targum.models import Document, SegmentedDocument, Translation, read_artifact
from targum.render import render
from targum.render.builder import CONTENTS, clock, contents_page, first_line, is_label


def built(folder: Path, chapters: int = 3) -> Path:
    """A book of `chapters` chapters, every one translated, rendered beside itself."""
    book(folder, chapters=chapters, translated=chapters)
    segmented = read_artifact(SegmentedDocument, folder / "segments.json")
    translation = read_artifact(Translation, folder / "translations" / "null.natural.en.json")
    assert segmented is not None and translation is not None
    document = Document(source="m", title="A Book", language="he", blocks=[], content_hash="book")
    render(document, segmented, [translation], folder / "reader", folder=folder)
    return folder


@pytest.mark.parametrize(
    "title",
    ["Section 4", "Part 3", "VI", "פרק א", "Глава 2", "חלק 2 · 10:01–24:38", "12", "Chapter 1", ""],
)
def test_a_heading_that_only_says_where_it_falls_is_a_label(title: str) -> None:
    assert is_label(title)


@pytest.mark.parametrize("title", ["המסות הגדולות בדרך", "Отец Сергий", "Vision of the night"])
def test_a_heading_that_says_what_it_is_about_is_a_title(title: str) -> None:
    assert not is_label(title)


def test_a_first_line_is_cut_at_a_word() -> None:
    assert first_line("short line") == "short line"
    long = " ".join(["word"] * 40)
    cut = first_line(long)
    assert cut.endswith("…") and len(cut) <= 91 and not cut[:-1].endswith(" ")


def test_a_clock_is_a_players() -> None:
    assert clock(252) == "4:12"
    assert clock(3729) == "1:02:09"


def test_the_build_writes_what_the_page_is_drawn_from(tmp_path: Path) -> None:
    folder = built(tmp_path / "book-he")
    manifest = json.loads((folder / "reader" / CONTENTS).read_text(encoding="utf-8"))
    assert manifest["version"] == 1 and manifest["layout"] == "book"
    assert manifest["document"] == "book"
    rows = manifest["sections"]
    assert [row["file"] for row in rows] == ["sec-0001.html", "sec-0002.html", "sec-0003.html"]
    # "Chapter 1" is only a label, so the row's title will be its first line.
    assert rows[0]["label"] and rows[0]["first"] == "line 0 of chapter 1"
    assert rows[0]["words"] > 0 and rows[0]["minutes"] >= 1
    # And the page the build wrote is still there, for a reader opened off a disk.
    assert (folder / "reader" / "index.html").is_file()


def test_a_single_page_text_has_no_contents(tmp_path: Path) -> None:
    folder = built(tmp_path / "short-he", chapters=1)
    assert not (folder / "reader" / CONTENTS).exists()


def manifest_of(folder: Path) -> dict:
    return json.loads((folder / "reader" / CONTENTS).read_text(encoding="utf-8"))


def test_a_rows_title_is_the_text_never_a_label(tmp_path: Path) -> None:
    page = contents_page(manifest_of(built(tmp_path / "book-he")), {})
    page = re.sub(r"</?bdi>", "", page)
    names = re.findall(r'class="parts-name"[^>]*>([^<]+)<', page)
    assert names == ["line 0 of chapter 1", "line 0 of chapter 2", "line 0 of chapter 3"]
    assert re.findall(r'class="parts-kicker"[^>]*>([^<]+)<', page)[0] == "Chapter 1"
    # Untouched, it opens on the medium's verb, at the first chapter.
    assert 'href="sec-0001.html"' in page and "Start reading" in page
    # The desk, never the reader's sheet.
    assert '<body class="parts">' in page and ".bar-title" not in page


def test_the_page_says_where_the_reader_stopped_and_what_they_finished(tmp_path: Path) -> None:
    state = {
        "signed_in": True,
        "place": {"section": "2", "seconds": 0},
        "finished": {"1"},
        "known": {1: (10, 9, 1), 2: (10, 5, 4), 3: (10, 0, 10)},
    }
    page = contents_page(manifest_of(built(tmp_path / "book-he")), state)
    assert re.search(r'id="start"[^>]*href="sec-0002.html"', page.replace("\n", " "))
    assert "Continue: chapter 2" in page and "Start from the beginning" in page
    assert "You know 46% of its words" in page and "1 of 3 read" in page
    assert "90% known" in page and "4 new words" in page
    assert re.search(r'class="parts-row here"[^>]*data-chapter="2"', page)
    assert re.search(r'class="parts-row read"[^>]*data-chapter="1"', page)
    # No style attribute: the desk's policy refuses one, so a share is a <progress>.
    assert "style=" not in page.split("<body", 1)[1]
    assert '<progress class="parts-meter" max="100" value="46"' in page


def test_the_page_speaks_russian_where_the_reader_does(tmp_path: Path) -> None:
    state = {"place": {"section": "3"}, "known": {}}
    page = contents_page(manifest_of(built(tmp_path / "book-he")), state, language="ru")
    assert "Продолжить: глава 3" in page and "Содержание" in page


def test_a_film_is_a_filmstrip_at_its_own_times(tmp_path: Path) -> None:
    manifest = {
        "version": 1,
        "document": "film",
        "title": "A talk",
        "language": "he",
        "medium": "watch",
        "layout": "film",
        "seconds": 3000,
        "sections": [
            {"number": 1, "file": "sec-0001.html", "title": "A talk", "label": True,
             "first": "שלום לכולם", "words": 700, "minutes": 6, "parts": [1],
             "start": 0.0, "end": 724.0, "frame": "../frames/part-001.jpg"},
            {"number": 2, "file": "sec-0002.html", "title": "חלק 2", "label": True,
             "first": "", "words": 5, "minutes": 1, "parts": [2],
             "start": 724.0, "end": 1450.0, "frame": ""},
        ],
        "groups": [{"portion": None, "sections": [1, 2]}],
    }
    state = {"place": {"section": "1", "seconds": 252}, "finished": set(), "known": {}}
    page = contents_page(manifest, state)
    assert "Continue: part 1, 4:12" in page and "You stopped at 4:12" in page
    assert '<img src="../frames/part-001.jpg"' in page
    assert "1 · 0:00–12:04" in page and "Getting ready" in page
    assert "50 min in all" in page and "2 parts" in page


def test_the_server_answers_a_readers_index_with_the_page(
    served: tuple[int, str, Path],  # noqa: F811
    postbox: Postbox,  # noqa: F811
) -> None:
    port, key, out = served
    cookie = sign_in(port, postbox)
    # The first account on a fresh store, whose home is `p1`.
    built(out / "p1" / "book-he")
    status, body, _ = call(port, "GET", "/reader/book-he/reader/index.html", cookie=cookie)
    assert status == 200
    text = body.decode("utf-8")
    assert '<body class="parts">' in text and "Uploaded by you" in text
    # Its own file is still beside it, and a chapter is served as it always was.
    status, chapter, _ = call(port, "GET", "/reader/book-he/reader/sec-0002.html", cookie=cookie)
    assert status == 200 and b'<body class="parts">' not in chapter


def test_a_reader_built_before_the_change_keeps_its_page(
    served: tuple[int, str, Path],  # noqa: F811
) -> None:
    port, key, out = served
    folder = built(out / "local" / "old-he")
    (folder / "reader" / CONTENTS).unlink()
    status, body = get(port, f"/reader/old-he/reader/index.html?k={key}")
    assert status == 200 and b'<body class="contents">' in body


def test_a_shared_text_stands_in_the_library(
    served: tuple[int, str, Path],  # noqa: F811
) -> None:
    port, key, out = served
    built(out / "shared" / "genesis-he")
    status, body = get(port, f"/reader/genesis-he/reader/index.html?k={key}")
    text = body.decode("utf-8")
    assert status == 200 and '<a href="/library">Library</a>' in text
    assert "Uploaded by you" not in text
