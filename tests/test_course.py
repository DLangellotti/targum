"""A course book's lesson becomes a reader beside its own translation (targum-internal#652).

Every line here is invented for the test. A course book is in copyright, and none of its
text belongs in this repository, a fixture included.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from test_sefaria import _WholeBlocks

from targum import ingest
from targum.align import parallel
from targum.errors import TargumError
from targum.ingest.fetch import course
from targum.models import BlockKind
from targum.segment import segment_document


def book() -> dict:
    return {
        "title": "A Made-up Course",
        "language": "it",
        "translation": "en",
        "lessons": {
            "1": {
                "title": {
                    "it": ["LEZIONE UNO (lehtsyauneh)", "Al mercato"],
                    "en": ["LESSON ONE", "At the Market"],
                },
                "lines": {
                    "1": {
                        "it": "— Buongiorno! Vorrei due mele. (1)",
                        "en": "— Good morning! [I]'d like two apples.",
                    },
                    "2": {
                        "it": "— Ecco le mele. Altro? (2) (N.1)",
                        "en": "— Here are the apples. Anything else?",
                    },
                    "3": {"it": "— No, grazie.", "en": ""},
                },
                "notes": {
                    "1": "Vorrei is the polite way to ask for something.",
                    "2": "Ecco points at what is there.",
                },
                "pronuncia": ["bwon-djorrr-noh"],
                "exercises": {"it": {"1": "Vorrei una mela."}, "en": {"1": "I'd like an apple."}},
                "gaps": {"1": "Here it is. || ___ ."},
                "key": {"1": "Ecco"},
            },
            "2": {
                "title": {"it": ["LEZIONE DUE", "REVISIONE"], "en": ["(Revision)", "LESSON TWO"]},
                "lines": {},
                "notes": {"1": "Ecco and vorrei, once more.", "2": "Numbers: uno, due."},
            },
        },
    }


def pair_of(held: dict, number: int):
    return course.documents(held, number, "it", "en", name="made-up")


def test_a_lesson_becomes_two_sides_that_pair_line_for_line() -> None:
    italian, english = pair_of(book(), 1)
    assert italian.source == "course:it:made-up:1" and english.source == "course:en:made-up:1"
    assert italian.ingester == "course/1" and italian.language == "it" and english.language == "en"
    verses = [b for b in italian.blocks if b.kind is BlockKind.verse]
    assert [b.ref for b in verses] == ["L1:1", "L1:2", "L1:3"]
    assert parallel.parallel_key(italian) == parallel.parallel_key(english) is not None
    alignment = parallel.pair(
        segment_document(italian, _WholeBlocks()),
        segment_document(english, _WholeBlocks()),
        "lesson 1",
    )
    assert alignment.coverage() == 1.0 and alignment.aligner == parallel.NAME


def test_markers_leave_the_text_and_notes_land_on_the_translation_line() -> None:
    italian, english = pair_of(book(), 1)
    lines = [b for b in italian.blocks if b.kind is BlockKind.verse]
    assert lines[0].text == "— Buongiorno! Vorrei due mele."
    assert all("(" not in b.text for b in italian.blocks)
    assert all(not b.notes for b in italian.blocks)
    first, second, third = (b for b in english.blocks if b.kind is BlockKind.verse)
    assert first.notes and first.notes[0].mark == "1" and first.notes[0].at == len(first.text)
    assert first.notes[0].text.startswith("Vorrei is the polite")
    # (N.1) points at the revision lesson's first section, which the extract holds.
    assert [n.mark for n in second.notes or []] == ["2", "N.1"]
    assert second.notes[1].text == "Ecco and vorrei, once more."
    # A line the translation lacks keeps its place, so the next line still pairs.
    assert third.text == "—"


def test_the_heading_drops_the_respelling_and_the_shouting() -> None:
    italian, english = pair_of(book(), 1)
    assert italian.blocks[0].kind is BlockKind.heading
    assert italian.blocks[0].text == "Lezione uno — Al mercato"
    assert english.blocks[0].text == "Lesson one — At the Market"
    assert italian.title == "Lezione uno — Al mercato"


def test_what_the_reader_leaves_out_stays_out() -> None:
    italian, english = pair_of(book(), 1)
    said = " ".join(b.text for doc in (italian, english) for b in doc.blocks)
    for kept_for_later in ("bwon-djorrr-noh", "Vorrei una mela.", "I'd like an apple.", "___"):
        assert kept_for_later not in said


def test_a_revision_lesson_is_a_reader_with_its_sections_on_the_heading() -> None:
    italian, english = pair_of(book(), 2)
    assert [b.kind for b in italian.blocks] == [BlockKind.heading]
    assert english.blocks[0].text == "Revision — Lesson two"
    assert [n.mark for n in english.blocks[0].notes or []] == ["1", "2"]
    alignment = parallel.pair(
        segment_document(italian, _WholeBlocks()),
        segment_document(english, _WholeBlocks()),
        "lesson 2",
    )
    assert alignment.coverage() == 1.0


def test_a_line_misread_with_no_italian_is_refused() -> None:
    held = book()
    held["lessons"]["1"]["lines"]["2"]["it"] = ""
    with pytest.raises(TargumError):
        pair_of(held, 1)
    with pytest.raises(TargumError):
        pair_of(book(), 9)


def test_the_extract_is_read_from_the_courses_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "made-up.json").write_text(json.dumps(book(), ensure_ascii=False), "utf-8")
    monkeypatch.setenv("TARGUM_COURSES", str(tmp_path))
    italian = ingest.load("course:it:made-up:1")
    english = ingest.load("course:en:made-up:1")
    assert italian.language == "it" and english.language == "en"
    assert parallel.parallel_key(italian) == parallel.parallel_key(english)
    with pytest.raises(TargumError):
        ingest.load("course:fr:made-up:1")
    with pytest.raises(TargumError):
        ingest.load("course:it:no-such-book:1")
    # A book is a name, never a path: an extract one folder up is there to be read, and
    # still is not (qa-claude on #1121).
    (tmp_path.parent / "made-up.json").write_text(json.dumps(book()), "utf-8")
    with pytest.raises(TargumError, match="names its language"):
        ingest.load("course:it:../made-up:1")


def test_no_request_can_name_a_course() -> None:
    """A course extract is a reader's copy of a book in copyright: the Add page, the chat
    and Telegram take only what `fetchable` allows, and it never allows a course."""
    assert ingest.fetch.is_identifier("course:it:made-up:1")
    assert not ingest.fetchable("course:it:made-up:1")
    assert not ingest.fetch.addressable("course:it:made-up:1")
    assert ingest.fetchable("published:ru:Genesis")
    assert "course:" not in ingest.sources()


# -- a course is private wherever it was built (qa-claude on #1121) ---------------------


@pytest.mark.parametrize(
    ("source", "ingester", "private"),
    [
        ("course:it:made-up:1", "course/1", True),
        ("COURSE:it:made-up:1", "", True),
        # Its ingester alone says so, whatever the source was renamed to.
        ("lesson-one.json", "course/1", True),
        ("  Course:it:made-up:1", "", True),
        # The public kinds, and what is left to where it sits.
        ("sefaria:Ruth", "sefaria/3", False),
        ("published:ru:Genesis", "", False),
        ("weekly:12", "", False),
        ("https://x.test/a", "url/6", False),
        ("/srv/upload/a.txt", "text/5", False),
        ("a.txt", "text/5", False),
        # A course read under a public scheme is still a course, by what read it.
        ("https://x.test/a", "course/1", True),
    ],
)
def test_what_a_source_is_says_whether_it_is_private(
    source: str, ingester: str, private: bool
) -> None:
    assert ingest.fetch.private_source(source, ingester) is private


#: A string that stands for a line of a lesson: it must reach no table.
LINE = "zz-a-line-of-the-lesson-zz"


def _built(folder: Path, source: str, document_hash: str, ingester: str = "course/1") -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    document = {"content_hash": document_hash, "source": source, "ingester": ingester}
    (folder / "document.json").write_text(json.dumps(document), "utf-8")
    token = {"start": 0, "end": 1, "surface": LINE, "lemma": "lemmaccio", "pos": "NOUN"}
    annotation = {
        "schema_version": 1,
        "document_hash": document_hash,
        "language": "he",
        "annotator": "dicta/test/1",
        "text": LINE,
        "tokens": {"s0": [token, dict(token, lemma="vorrei", pos="VERB")]},
    }
    (folder / "annotation.json").write_text(json.dumps(annotation), "utf-8")
    return folder


@pytest.fixture
def ledger_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    file = tmp_path / "corpus.db"
    monkeypatch.setenv("TARGUM_LEDGER", str(file))
    return file


@pytest.mark.parametrize("ledger_on", [True, False])
def test_a_course_built_outside_a_home_never_enters_the_tables(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, ledger_on: bool
) -> None:
    """`targum build` into the library's own folder, or into `./targum-out`: no home says
    it is private, so what it is has to (qa-claude on #1121)."""
    from targum import ledger, tables
    from targum.tables.store import Store

    file = tmp_path / "corpus.db"
    if ledger_on:
        monkeypatch.setenv("TARGUM_LEDGER", str(file))
    else:
        monkeypatch.delenv("TARGUM_LEDGER", raising=False)
    library = tmp_path / "library"
    lesson = _built(library / "shared" / "lesson", "course:it:made-up:1", "c" * 64)
    shelf = _built(library / "shared" / "ruth", "sefaria:Ruth", "d" * 64, "sefaria/3")
    if ledger_on:
        assert ledger.backfill_texts(ledger.Ledger(file), library) == (1, 0)
        book = ledger.Ledger(file)
        assert book.text("c" * 64) is None and book.terms("c" * 64) is None
        assert book.text("d" * 64) is not None and not book.is_private("d" * 64)
    assert tables.public_text(lesson, library) is None
    assert tables.public_text(shelf, library) is not None, "the guard is not a wall"
    store = Store(tmp_path / "tables.db")
    swept = tables.sweep(library, store)
    assert swept.private == 1 and swept.folded == 1
    held = (tmp_path / "tables.db").read_bytes()
    assert LINE.encode() not in held and b"c" * 64 not in held
    assert ("vorrei", 1) not in dict(store.top("words", "unfiled", limit=100, weighed=False))


@pytest.mark.parametrize("top", ["shared", "p1"])
def test_a_course_is_never_a_row_in_the_ledger(tmp_path: Path, ledger_file: Path, top: str) -> None:
    """Not even a private one: the corpus is what trains, and a course book is somebody's
    copy of a book in copyright (qa-claude on #1121)."""
    from targum import ledger

    library = tmp_path / "library"
    folder = _built(library / top / "lesson", "course:en:made-up:1", "e" * 64)
    ledger.mirror_text(folder, library)
    book = ledger.Ledger(ledger_file)
    assert book.text("e" * 64) is None
    assert not book.hold(ledger.Text("e" * 64, "course:en:made-up:1", "CC0"), "p1")
    # Whatever licence the extract claims, by its source or by what read it.
    for text in (
        ledger.Text("2" * 64, "course:it:made-up:2", "CC0"),
        ledger.Text("3" * 64, "/tmp/made-up.txt", "CC0", ingester="course/1"),
    ):
        assert not book.record_text(text) and book.terms(text.document_hash) is None
    assert book.record_text(ledger.Text("1" * 64, "gutenberg:1", "CC0")), "the test can fail"
    assert book.terms("1" * 64) == (True, True)


def test_ten_readers_bringing_a_course_pool_nothing(tmp_path: Path, ledger_file: Path) -> None:
    """The pool counts what readers bring, a private import included, as counts. A course
    book is not that: it is somebody's copy of a book in copyright, never counted."""
    from targum.tables import imports
    from targum.tables.store import Store

    library = tmp_path / "library"
    for person in range(1, 11):
        _built(library / f"p{person}" / "lesson", "course:it:made-up:1", f"{person:064x}")
    store = Store(ledger_file)
    result = imports.pool(library, store, set(range(1, 11)))
    assert result.withheld == 10 and result.texts == 0
    assert store.top("words", "imports", limit=100, weighed=False) == []
    assert LINE.encode() not in ledger_file.read_bytes()
    # The same ten, bringing a link instead, are pooled: the test can fail.
    for person in range(1, 11):
        _built(library / f"p{person}" / "lesson", "https://x.test/a", f"{person:064x}", "url/6")
    result = imports.pool(library, store, set(range(1, 11)))
    assert result.withheld == 0 and result.texts == 10


def test_a_course_never_reaches_the_yardsticks(tmp_path: Path) -> None:
    """The word map the yardsticks are drawn from reads only through `public_text`."""
    from targum.finds import score

    library = tmp_path / "library"
    _built(library / "shared" / "lesson", "course:it:made-up:1", "f" * 64)
    _built(library / "shared" / "link", "https://x.test/b", "a" * 64, "url/6")
    keys = [text.key for text in score.annotated(library, ["he"])]
    assert keys == ["a" * 64]


def test_the_chat_cannot_describe_a_course(tmp_path: Path) -> None:
    """`describe_source` hands a fetcher's identifier back to be quoted as it is; a course
    is never one it hands back (qa-claude on #1121)."""
    from targum import level
    from targum.accounts import Store as AccountStore
    from targum.chat import tools

    ctx = tools.Ctx(
        person=None,
        home=tmp_path,
        library=None,
        store=AccountStore(tmp_path / "words.db"),
        chat_id="c",
        level=level.EMPTY,
    )
    got = tools._describe(ctx, {"url": "course:it:made-up:1"})
    assert got.get("kind") != "fetcher" and "error" in got
    assert tools._describe(ctx, {"url": "sefaria:Ruth"})["kind"] == "fetcher"


def test_a_lesson_builds_beside_its_book_s_translation_and_buys_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The book's own translation is the translation: no machine one is asked for, the
    pair is stated by the book's numbers, and the notes reach the page."""
    from targum.pipeline import Build

    courses = tmp_path / "courses"
    courses.mkdir()
    (courses / "made-up.json").write_text(json.dumps(book(), ensure_ascii=False), "utf-8")
    monkeypatch.setenv("TARGUM_COURSES", str(courses))

    def bought(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("a course lesson is never machine-translated")

    monkeypatch.setattr(Build, "translate", bought)
    build = Build(
        "course:it:made-up:1",
        target_language="en",
        translations=["course:en:made-up:1"],
        out_root=tmp_path / "out",
        segmenter=_WholeBlocks(),
    )
    assert build.machine is False
    result = build.run()
    held = " ".join(one.read_text("utf-8") for one in result.out_dir.rglob("*.json"))
    assert f'"aligner": "{parallel.NAME}"' in held or f'"aligner":"{parallel.NAME}"' in held
    page = " ".join(one.read_text("utf-8") for one in result.out_dir.rglob("*.html"))
    assert "Vorrei is the polite way" in page
    assert 'class="verse-number"' in page


def _counts(file: Path) -> dict[str, int]:
    import sqlite3
    from contextlib import closing

    with closing(sqlite3.connect(file)) as db:
        names = [
            row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        ]
        return {
            name: db.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]  # noqa: S608
            for name in names
        }


@pytest.mark.parametrize("top", ["shared", "p1"])
def test_building_a_lesson_leaves_the_ledger_as_it_was(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, ledger_file: Path, top: str
) -> None:
    """A lesson built into the library's own folder or into a reader's home: no `texts`
    row, no rendering, no pair, not a byte, whichever writer asks (qa-claude on #1121)."""
    from targum import ledger
    from targum.pipeline import Build

    monkeypatch.setattr(ledger, "_WITHHELD", set())
    courses = tmp_path / "courses"
    courses.mkdir()
    (courses / "made-up.json").write_text(json.dumps(book(), ensure_ascii=False), "utf-8")
    monkeypatch.setenv("TARGUM_COURSES", str(courses))
    library = tmp_path / "library"
    shelf = _built(library / "shared" / "ruth", "sefaria:Ruth", "d" * 64, "sefaria/3")
    ledger.mirror_text(shelf, library)
    before, held = _counts(ledger_file), ledger_file.read_bytes()
    assert before["texts"] == 1

    build = Build(
        "course:it:made-up:1",
        target_language="en",
        translations=["course:en:made-up:1"],
        out_root=library / top,
        library=library,
        segmenter=_WholeBlocks(),
    )
    result = build.run()
    folder = result.out_dir
    document = json.loads((folder / "document.json").read_text("utf-8"))
    assert document["content_hash"] in ledger._WITHHELD
    assert list((folder / "translations").glob("*.json")), "nothing to record"
    assert ledger_file.read_bytes() == held

    # Every writer again, by what the folder is and not by what the build withheld.
    ledger._WITHHELD.clear()
    ledger.mirror_text(folder, library)
    assert ledger.record_translations(ledger.Ledger(ledger_file), folder, root=library) == (0, 0)
    ledger.backfill_texts(ledger.Ledger(ledger_file), library)
    ledger.backfill_translations(ledger.Ledger(ledger_file), library)
    assert _counts(ledger_file) == before
    assert ledger_file.read_bytes() == held
    for line in ("Buongiorno", "Ecco le mele", "Good morning", "apples"):
        assert line.encode() not in ledger_file.read_bytes()

    # The same folder as a link a reader brought is recorded: the test can fail.
    document.update(source="https://x.test/a", ingester="url/6")
    (folder / "document.json").write_text(json.dumps(document), "utf-8")
    ledger.mirror_text(folder, library)
    ledger.mirror_translations(folder, library)
    after = _counts(ledger_file)
    assert after["texts"] == 2 and after["pairs"] > before["pairs"]
    assert b"Buongiorno" in ledger_file.read_bytes()


def test_a_withheld_text_is_put_by_no_stage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, ledger_file: Path
) -> None:
    """`Cache.put`'s second write and a direct `record` both skip a withheld text."""
    from targum import ledger

    monkeypatch.setattr(ledger, "_WITHHELD", set())
    value = {
        "schema_version": 1,
        "document_hash": "9" * 64,
        "language": "it",
        "annotator": "test/1",
        "tokens": {},
    }
    ledger.withhold("9" * 64)
    ledger.mirror_put("tokens", "k1", value)
    ledger.Ledger(ledger_file).record("tokens", "k2", value)
    assert ledger.Ledger(ledger_file).get("tokens", "k1") is None
    assert ledger.Ledger(ledger_file).get("tokens", "k2") is None
    ledger._WITHHELD.clear()
    ledger.mirror_put("tokens", "k1", value)
    assert ledger.Ledger(ledger_file).get("tokens", "k1") is not None, "the test can fail"
    ledger.withhold("9" * 64)
    ledger.Ledger(ledger_file).record("tokens", "k1", dict(value, annotator="test/2"))
    assert ledger.Ledger(ledger_file).get("tokens", "k1") == value


class _FakeVocalizer:
    """Points nothing and changes nothing, so the vocalize stage runs and puts its row
    without a diacritizer on disk."""

    name = "fake-vocalizer/1"
    model = None

    def available(self) -> tuple[bool, str]:
        return True, ""

    def vocalize(self, segments: list, language: str) -> dict[str, str]:
        return {segment.id: segment.text for segment in segments}


def hebrew_book() -> dict:
    """Invented lines, no course's: Hebrew with English beside it."""
    return {
        "title": "A Made-up Hebrew Course",
        "language": "he",
        "translation": "en",
        "lessons": {
            "1": {
                "title": {"he": ["שיעור אחד"], "en": ["LESSON ONE"]},
                "lines": {
                    "1": {"he": "אני רוצה שני תפוחים.", "en": "I want two apples."},
                    "2": {"he": "הנה התפוחים שלך.", "en": "Here are your apples."},
                },
            }
        },
    }


@pytest.mark.parametrize("withheld", [True, False])
def test_a_hebrew_lesson_s_stage_rows_never_reach_the_ledger(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, ledger_file: Path, withheld: bool
) -> None:
    """A `course:he:` lesson is vowelled, so its build puts a `vocalize` row: the
    ledger is still byte-identical after it. Without `Build.run`'s withhold the same
    build writes it, which is what makes the first half worth asserting (qa-claude on
    #1121)."""
    from test_pipeline import FakeAnnotator

    from targum import ledger
    from targum.pipeline import Build

    monkeypatch.setattr(ledger, "_WITHHELD", set())
    if not withheld:
        monkeypatch.setattr(Build, "_withhold_if_private", lambda self, plan: None)
    courses = tmp_path / "courses"
    courses.mkdir()
    (courses / "made-up.json").write_text(json.dumps(hebrew_book(), ensure_ascii=False), "utf-8")
    monkeypatch.setenv("TARGUM_COURSES", str(courses))
    library = tmp_path / "library"
    shelf = _built(library / "shared" / "ruth", "sefaria:Ruth", "d" * 64, "sefaria/3")
    ledger.mirror_text(shelf, library)
    before, held = _counts(ledger_file), ledger_file.read_bytes()

    build = Build(
        "course:he:made-up:1",
        target_language="en",
        translations=["course:en:made-up:1"],
        out_root=library / "p1",
        library=library,
        segmenter=_WholeBlocks(),
        annotator=FakeAnnotator(),  # type: ignore[arg-type]
        vocalizer=_FakeVocalizer(),  # type: ignore[arg-type]
    )
    result = build.run()
    assert (result.out_dir / "vocalization.json").is_file(), "no stage ran"
    if withheld:
        assert ledger_file.read_bytes() == held
        assert _counts(ledger_file) == before
    else:
        after = _counts(ledger_file)
        assert after["vocalizations"] > before["vocalizations"]
