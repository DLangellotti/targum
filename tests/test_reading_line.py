"""What a reader knew of what they read, month by month (targum-internal#291).

One row a finished section, measured when it is finished against the ledger as it stood,
and never again; one line a language, a point a month. The server half is here and in
`test_serve.py` (the push that writes the row); the page half is `test_progress_js.py`.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path

import test_serve
from test_serve import Postbox, call, sign_in

from targum import coverage
from targum.accounts import Store
from targum.models import BlockKind, Segment, SegmentedDocument

KNOWN = 9

# The running server and the postbox its sign-in links land in, borrowed rather than
# built again: `/sync` is only worth testing through the door the page uses.
served = test_serve.served
postbox = test_serve.postbox


def ms(year: int, month: int, day: int = 10) -> int:
    return int(datetime(year, month, day, tzinfo=UTC).timestamp() * 1000)


def built(folder: Path, sections: dict[int, list[list[dict[str, str]]]], pages: int = 0) -> Path:
    """A built text: each section a heading and some lines, each line its tokens.

    `pages` is how many `sec-NNNN.html` the reader has, defaulting to one per section.
    """
    segments: list[Segment] = []
    tokens: dict[str, list[dict[str, object]]] = {}
    for number, lines in sections.items():
        segments.append(
            Segment(
                id=f"h{number}",
                block_id=f"b{number}",
                block_index=number,
                index=len(segments),
                text=f"Chapter {number}",
                kind=BlockKind.heading,
                level=1,
            )
        )
        for n, line in enumerate(lines):
            sid = f"s{number}-{n}"
            segments.append(
                Segment(
                    id=sid,
                    block_id=f"b{number}",
                    block_index=number,
                    index=len(segments),
                    text="line",
                )
            )
            tokens[sid] = [{"start": 0, "end": 1, **token} for token in line]
    folder.mkdir(parents=True, exist_ok=True)
    SegmentedDocument(
        document_hash="book", language="he", segmenter="t/1", segments=segments
    ).write(folder / "segments.json")
    (folder / "annotation.json").write_text(json.dumps({"tokens": tokens}), encoding="utf-8")
    (folder / "document.json").write_text(
        json.dumps({"title": "A Book", "language": "he", "content_hash": "book"}),
        encoding="utf-8",
    )
    reader = folder / "reader"
    reader.mkdir(exist_ok=True)
    (reader / "index.html").write_text("<p>x</p>", encoding="utf-8")
    for number in range(1, (pages or len(sections)) + 1):
        (reader / f"sec-{number:04d}.html").write_text("<p>x</p>", encoding="utf-8")
    return folder


def word(lemma: str, pos: str = "NOUN") -> dict[str, str]:
    return {"lemma": lemma, "pos": pos}


def test_a_section_is_measured_by_its_own_running_words(tmp_path: Path) -> None:
    """The section the page names and no other; every running word, so the commonest
    come round as often as they did on the page; names and numbers left out, as every
    count of vocabulary leaves them."""
    folder = built(
        tmp_path / "book",
        {
            1: [[word("ספר"), word("ספר"), word("בית")], [word("דוד", "PROPN")]],
            2: [[word("ים"), word("ים"), word("ים"), word("שלוש", "NUM")]],
        },
    )
    measured = coverage.section_reading(folder, 1, {"ספר": KNOWN, "בית": 2})
    assert measured == coverage.Reading(tokens=3, known=2)
    assert coverage.section_reading(folder, 2, {"ספר": KNOWN}) == coverage.Reading(3, 0)
    assert coverage.section_reading(folder, 3, {}) is None, "no such section is not measured"


def test_a_text_rendered_whole_is_one_section_of_everything(tmp_path: Path) -> None:
    folder = built(tmp_path / "book", {1: [[word("ספר")]], 2: [[word("ים")]]}, pages=1)
    assert coverage.section_reading(folder, 1, {"ים": KNOWN}) == coverage.Reading(2, 1)


def test_a_text_with_no_annotation_is_not_measured(tmp_path: Path) -> None:
    folder = built(tmp_path / "book", {1: [[word("ספר")]]})
    (folder / "annotation.json").unlink()
    assert coverage.section_reading(folder, 1, {"ספר": KNOWN}) is None


def test_finishing_a_section_keeps_one_row_and_finishing_it_again_keeps_none(
    tmp_path: Path,
) -> None:
    store = Store(tmp_path / "words.db")
    signed = store.finish_sign_in(store.start_sign_in("reader@example.com"))
    assert signed is not None
    person = signed[0]
    row = {"hash": "book", "section": "1", "at": ms(2026, 8), "seen": ms(2026, 8)}
    assert store.unmeasured(person, [row]) == [("book", "1")]
    assert store.keep_reading(person, "he", ms(2026, 8), "book", "1", 100, 70)
    assert store.unmeasured(person, [row]) == [], "finished again, already measured"
    assert store.unmeasured(person, [{**row, "section": "2", "gone": 1}]) == [], (
        "an un-finish is not a finish"
    )
    assert not store.keep_reading(person, "he", ms(2026, 9), "book", "1", 100, 95)
    assert store.readings(person.id) == [
        {"language": "he", "at": ms(2026, 8), "hash": "book", "section": "1", "tokens": 100,
         "known": 70}
    ]  # fmt: skip


def test_a_row_is_never_recomputed_when_the_ledger_moves(tmp_path: Path) -> None:
    """The row is the ledger as it stood. Words marked known since do not reach back."""
    store = Store(tmp_path / "words.db")
    signed = store.finish_sign_in(store.start_sign_in("reader@example.com"))
    assert signed is not None
    person = signed[0]
    store.keep_reading(person, "he", ms(2026, 8), "book", "1", 10, 3)
    store.push(
        person,
        {"words": [{"language": "he", "lemma": "ים", "status": KNOWN, "at": 5, "seen": 5}]},
    )
    assert [r["known"] for r in store.readings(person.id, "he")] == [3]


def test_the_line_is_a_point_a_month_weighted_by_words(tmp_path: Path) -> None:
    rows = [
        {"at": ms(2026, 6), "tokens": 100, "known": 80},
        {"at": ms(2026, 6, 20), "tokens": 300, "known": 120},
        {"at": ms(2026, 7), "tokens": 50, "known": 40},
        {"at": ms(2026, 8), "tokens": 200, "known": 100},
        # A month of under twenty words is a guess, and not a point.
        {"at": ms(2026, 9), "tokens": 5, "known": 5},
    ]
    assert coverage.monthly(rows) == [
        {"month": "2026-06", "tokens": 400, "known": 200, "sections": 2},
        {"month": "2026-07", "tokens": 50, "known": 40, "sections": 1},
        {"month": "2026-08", "tokens": 200, "known": 100, "sections": 1},
    ]


def test_under_three_months_there_is_no_line() -> None:
    rows = [
        {"at": ms(2026, 7), "tokens": 50, "known": 40},
        {"at": ms(2026, 8), "tokens": 200, "known": 100},
    ]
    assert coverage.monthly(rows) == []
    assert len(coverage.by_month(rows)) == 2, "and the page can still say how many there are"


def test_the_block_says_no_percentage_no_level_and_no_score() -> None:
    """§6: a count in ten, never a percentage, a level or a score — in every language the
    page speaks, and in the script that draws it."""
    root = Path(__file__).resolve().parents[1] / "src" / "targum"
    for code in ("en", "ru"):
        said = json.loads((root / "strings" / f"{code}.json").read_text(encoding="utf-8"))
        block = {k: v for k, v in said.items() if k.startswith("progress.reading.")}
        assert len(block) >= 14, code
        for key, text in block.items():
            lowered = text.lower()
            assert "%" not in text and "!" not in text, f"{code}: {key}"
            for banned in ("percent", "score", "level", "points", "xp", "процент", "балл",
                           "уровень", "keep going", "great", "don't worry"):  # fmt: skip
                assert banned not in lowered, f"{code}: {key} says {banned!r}"
    script = (root / "render" / "assets" / "progress.js").read_text(encoding="utf-8")
    drawn = script[script.index("function tenths(") : script.index("function askReading(")]
    assert "%" not in re.sub(r"//.*|/\*.*?\*/", "", drawn, flags=re.S)
    assert "clay" not in re.sub(r"//.*|/\*.*?\*/", "", drawn, flags=re.S), "a fall is not a verdict"


def test_a_section_finished_on_the_page_is_measured_once_on_the_push(
    served: tuple[int, str, Path], postbox: Postbox
) -> None:
    """End to end, through `/sync`: the push that carries a finished section writes its
    row, against the words that push carried too; the same section again writes none;
    and a word marked known later does not reach back into the row."""
    port, token, out = served
    built(
        out / "shared" / "book",
        {
            1: [[word("ספר"), word("ספר"), word("בית"), word("ים")] * 5],
            2: [[word("ים"), word("ספר")] * 10],
            3: [[word("ים"), word("בית")] * 10],
        },
    )
    cookie = sign_in(port, postbox)

    def sync(**changes: object) -> None:
        status, answer, _ = call(port, "POST", f"/sync?k={token}", changes, cookie=cookie)
        assert status == 200 and answer["signedIn"], answer

    def reading() -> dict[str, object]:
        status, answer, _ = call(port, "GET", f"/account/reading?k={token}", cookie=cookie)
        assert status == 200, answer
        return dict(answer["reading"].get("he") or {})

    known = {"language": "he", "lemma": "ספר", "status": KNOWN, "at": 1, "seen": 1}
    sync(
        words=[known],
        sections=[{"hash": "book", "section": "1", "at": ms(2026, 7), "seen": ms(2026, 7)}],
    )
    assert reading() == {"line": [], "months": 1, "sections": 1}

    # Un-finished and finished again: the row it has stands.
    sync(sections=[{"hash": "book", "section": "1", "gone": 1, "seen": ms(2026, 7, 11)}])
    sync(sections=[{"hash": "book", "section": "1", "at": ms(2026, 8), "seen": ms(2026, 8)}])
    assert reading()["sections"] == 1

    # Now ים is known too, and two more months are read.
    sync(
        words=[{**known, "lemma": "ים", "at": 2, "seen": 2}],
        sections=[
            {"hash": "book", "section": "2", "at": ms(2026, 8), "seen": ms(2026, 8)},
            {"hash": "book", "section": "3", "at": ms(2026, 9), "seen": ms(2026, 9)},
        ],
    )
    line = reading()["line"]
    assert line == [
        # Section 1 as it was measured in July: ספר twice in every four, ים not yet.
        {"month": "2026-07", "tokens": 20, "known": 10, "sections": 1},
        {"month": "2026-08", "tokens": 20, "known": 20, "sections": 1},
        {"month": "2026-09", "tokens": 20, "known": 10, "sections": 1},
    ]


def test_a_section_nobody_can_measure_is_synced_and_keeps_no_row(
    served: tuple[int, str, Path], postbox: Postbox
) -> None:
    """A finished section of a text this server has no build of — a parasha page, a
    deleted text — still syncs; it just keeps no measurement."""
    port, token, _ = served
    cookie = sign_in(port, postbox)
    status, answer, _ = call(
        port,
        "POST",
        f"/sync?k={token}",
        {"sections": [{"hash": "elsewhere", "section": "1", "at": 5, "seen": 5}]},
        cookie=cookie,
    )
    assert status == 200 and answer["sections"][0]["hash"] == "elsewhere", (
        "and the section itself reaches the account, which it did not before #291"
    )
    status, said, _ = call(port, "GET", f"/account/reading?k={token}", cookie=cookie)
    assert said == {"signedIn": True, "reading": {}}


def test_the_line_is_nobodys_business_signed_out(served: tuple[int, str, Path]) -> None:
    port, token, _ = served
    status, said, _ = call(port, "GET", f"/account/reading?k={token}")
    assert status == 401 and said == {"signedIn": False}
