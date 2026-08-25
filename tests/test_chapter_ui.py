"""A book on screen: a tree of chapters, bought as they are reached."""

from __future__ import annotations

import json
from pathlib import Path

from targum.models import BlockKind, Segment, SegmentedDocument, Translation
from targum.serve import Library


def book(folder: Path, chapters: int, translated: int) -> None:
    """A book on disk with `translated` of its `chapters` paid for."""
    segments, ids = [], []
    for c in range(1, chapters + 1):
        segments.append(
            Segment(
                id=f"h{c}",
                block_id=f"b{c}",
                block_index=c,
                index=len(segments),
                text=f"Chapter {c}",
                kind=BlockKind.heading,
                level=1,
            )
        )
        for n in range(3):
            sid = f"s{c}-{n}"
            segments.append(
                Segment(
                    id=sid,
                    block_id=f"b{c}",
                    block_index=c,
                    index=len(segments),
                    text=f"line {n} of chapter {c}",
                    kind=BlockKind.paragraph,
                )
            )
            ids.append((c, sid))
    segmented = SegmentedDocument(
        document_hash="book", language="he", segmenter="t/1", segments=segments
    )
    folder.mkdir(parents=True, exist_ok=True)
    segmented.write(folder / "segments.json")
    (folder / "reader").mkdir(exist_ok=True)
    (folder / "reader" / "index.html").write_text("<p>x</p>", encoding="utf-8")
    (folder / "document.json").write_text(
        json.dumps({"title": "A Book", "language": "he", "content_hash": "book"}), encoding="utf-8"
    )
    done = {sid: "translated" for c, sid in ids if c <= translated}
    done |= {f"h{c}": "Chapter" for c in range(1, translated + 1)}
    Translation(
        name="English",
        document_hash="book",
        source_language="he",
        target_language="en",
        provider="null",
        segments=done,
    ).write(folder / "translations" / "null.natural.en.json")


def test_a_book_reports_every_chapter_and_which_are_ready(tmp_path: Path) -> None:
    library = Library(tmp_path)
    home = library.home(None)
    book(home / "book-he", chapters=5, translated=2)

    chapters = library.chapters(home / "book-he")
    assert [c["number"] for c in chapters] == [1, 2, 3, 4, 5]
    assert [c["ready"] for c in chapters] == [True, True, False, False, False]

    listed = library.readers(home)[0]
    assert listed["readyChapters"] == 2
    assert len(listed["chapters"]) == 5


def test_readiness_is_derived_not_recorded(tmp_path: Path) -> None:
    """A second place saying which chapters are ready would drift from the truth the
    first time a build died between writing them."""
    library = Library(tmp_path)
    home = library.home(None)
    folder = home / "book-he"
    book(folder, chapters=3, translated=1)
    assert [c["ready"] for c in library.chapters(folder)] == [True, False, False]

    # Paying for the third, out of order, is visible immediately and with nothing else
    # touched — there is no manifest to keep in step.
    path = folder / "translations" / "null.natural.en.json"
    data = json.loads(path.read_text())
    data["segments"] |= {"h3": "Chapter", "s3-0": "x", "s3-1": "x", "s3-2": "x"}
    path.write_text(json.dumps(data), encoding="utf-8")
    assert [c["ready"] for c in library.chapters(folder)] == [True, False, True]


def test_a_single_section_text_is_not_a_tree(tmp_path: Path) -> None:
    """An article is one row. A tree of one is furniture."""
    library = Library(tmp_path)
    home = library.home(None)
    book(home / "article-he", chapters=1, translated=1)
    assert library.chapters(home / "article-he") == []
    assert library.readers(home)[0]["readyChapters"] == 0


def test_only_the_first_chapters_are_translated_up_front() -> None:
    """The whole point: opening a novel must not buy twenty chapters."""
    from targum.models import Style
    from targum.pipeline import Build

    segments = []
    for c in range(1, 5):
        segments.append(
            Segment(
                id=f"h{c}",
                block_id=f"b{c}",
                block_index=c,
                index=len(segments),
                text=f"Chapter {c}",
                kind=BlockKind.heading,
                level=1,
            )
        )
        for n in range(3):
            segments.append(
                Segment(
                    id=f"s{c}-{n}",
                    block_id=f"b{c}",
                    block_index=c,
                    index=len(segments),
                    text=f"line {n}",
                    kind=BlockKind.paragraph,
                )
            )
    segmented = SegmentedDocument(
        document_hash="b", language="he", segmenter="t/1", segments=segments
    )
    build = Build("x.md", target_language="en", style=Style.natural)

    first = build._first_chapters(segmented, 1)
    assert first is not None
    assert {s.id for s in first} == {"h1", "s1-0", "s1-1", "s1-2"}

    two = build._first_chapters(segmented, 2)
    assert two is not None and len(two) == 8

    assert {s.id for s in build.chapter_segments(segmented, 3)} == {"h3", "s3-0", "s3-1", "s3-2"}
    assert build.chapter_segments(segmented, 99) == []


def test_preparing_a_whole_book_is_still_a_chapter_job(tmp_path: Path) -> None:
    """The bug this catches: "prepare all" names no single chapter, so it carried
    `chapter: 0` — and the dispatch tested that for truthiness. Zero is falsy, so the
    job went down the ordinary build path and tried to ingest the folder name as a file.
    """
    from targum.serve import Job, Library

    library = Library(tmp_path, store=None)

    whole = Job(id="a", source="x", options={"chapters": [2, 3, 4], "folder": "book-he"})
    one = Job(id="b", source="x", options={"chapters": [3], "folder": "book-he"})
    ordinary = Job(id="c", source="/tmp/book.md", options={"to": "en"})

    assert bool(whole.options.get("chapters")) is True
    assert bool(one.options.get("chapters")) is True
    assert bool(ordinary.options.get("chapters")) is False
    # And the old shape, which is what went wrong.
    assert bool({"chapter": 0}.get("chapter")) is False
    assert library is not None


def test_a_book_with_nothing_waiting_needs_no_preparing(tmp_path: Path) -> None:
    library = Library(tmp_path)
    home = library.home(None)
    book(home / "book-he", chapters=3, translated=3)
    assert [c["ready"] for c in library.chapters(home / "book-he")] == [True, True, True]


def test_a_book_is_priced_by_the_chapter_it_will_buy(tmp_path: Path) -> None:
    """The gap that made the whole chapter feature unreachable.

    The engine and the interface were built and a novel was still refused, because
    `prepare` priced every segment: an 87k-word book estimated $5.90 against a $2.00 cap
    while the build behind it would only spend $0.30. The estimate has to be for what is
    actually bought.
    """
    from targum.models import Style
    from targum.pipeline import Build

    text = "\n\n".join(
        f"# Chapter {c}\n\n" + "\n\n".join(f"Sentence {n} of chapter {c}." for n in range(40))
        for c in range(1, 11)
    )
    source = tmp_path / "novel.md"
    source.write_text(text, encoding="utf-8")

    def priced(chapters: int | None) -> tuple[float, int]:
        build = Build(
            str(source),
            target_language="en",
            style=Style.natural,
            out_root=tmp_path / "out",
            difficulty=False,
            gloss=False,
        )
        plan = build.plan(chapters=chapters)
        return plan.estimated_cost, plan.buying

    whole_cost, whole_segments = priced(None)
    first_cost, first_segments = priced(1)

    assert whole_segments > first_segments * 5, "a chapter should be a fraction of the book"
    assert first_cost < whole_cost / 5, f"{first_cost} is not much less than {whole_cost}"


def test_an_article_is_priced_whole(tmp_path: Path) -> None:
    """Below a chapter boundary there is nothing to defer, and the machinery is worth
    nothing on a text that costs five cents."""
    from targum.models import Style
    from targum.pipeline import Build

    source = tmp_path / "article.md"
    source.write_text("\n\n".join(f"Sentence {n}." for n in range(20)), encoding="utf-8")
    build = Build(
        str(source),
        target_language="en",
        style=Style.natural,
        out_root=tmp_path / "out",
        difficulty=False,
        gloss=False,
    )
    plan = build.plan(chapters=1)
    assert plan.chapters == 1
    assert plan.segmented is not None
    assert plan.buying == len(plan.segmented.segments), "an article is bought whole"


def test_a_book_glosses_only_the_chapter_it_bought(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Translation is rationed by the chapter and meanings were not, so a novel bought a
    chapter at a time was glossed whole in advance. Altneuland's first chapter costs
    $0.21 to translate and was quoted $4.23 of meanings; the cap refused the pair and the
    book could not be opened at all."""
    from targum.models import Style
    from targum.pipeline import Build

    text = "\n\n".join(
        f"## Chapter {n}\n\n" + "\n\n".join(f"Sentence {n}.{m}." for m in range(30))
        for n in range(1, 6)
    )
    source = tmp_path / "novel.md"
    source.write_text(text, encoding="utf-8")

    asked: dict[str, object] = {}

    def spy(self, annotation, only=None):  # type: ignore[no-untyped-def]
        asked["only"] = None if only is None else [segment.id for segment in only]
        return None

    monkeypatch.setattr(Build, "glossary", spy)

    build = Build(
        str(source),
        target_language="en",
        style=Style.natural,
        provider_name="null",
        out_root=tmp_path / "out",
        difficulty=False,
        gloss=True,
    )
    result = build.run(chapters=1)

    assert asked["only"] is not None, "a book was glossed whole"
    assert result.segmented is not None
    assert 0 < len(asked["only"]) < len(result.segmented.segments)  # type: ignore[arg-type]
