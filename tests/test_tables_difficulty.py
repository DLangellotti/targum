"""How hard a word is found at each level, pooled across readers (targum-internal#586;
design.md §12, "How hard a word is, counted across readers").

What the card asks a test to show: no id in any row, a reader who erases their record
gone after the next run, a cell under the floor read as absent, and no count of readers
on a page. And what holds those up: operators left out, only public redistributable
texts counted, a private import never, and the job refusing until the served privacy
notice carries its clause. Every token is synthetic: placeholder lemmas, no sentence.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import subprocess
import sys
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from targum.accounts import Store as AccountStore
from targum.cli import app
from targum.models import BlockKind, Segment, SegmentedDocument
from targum.render.builder import legal_page
from targum.tables import difficulty
from targum.tables.store import DIFFICULTY, Contribution, Store

ROOT = Path(__file__).resolve().parent.parent
DEPLOY = ROOT / "deploy"

#: Stands for a sentence of a text: in the annotation, and in no row the tables hold.
SENTENCE = "zz-a-sentence-of-the-text-zz"

#: A day the events happen on, and the moment inside it.
DAY = "2026-11-01"
AT = int(datetime(2026, 11, 1, 12, tzinfo=UTC).timestamp() * 1000)

#: Two sections of words.
SECTIONS = {1: ["w1", "w2", "w3"], 2: ["w4"]}


def _built(library: Path, home: str, name: str, *, source: str = "", ingester: str = "") -> str:
    """A built text as a build leaves it, one reader page a section; its content hash."""
    folder = library / home / name
    folder.mkdir(parents=True)
    document_hash = name.encode().hex().ljust(64, "0")[:64]
    segments, tokens = [], {}
    # A heading before each section, as a chapter opens one: the build's own split.
    for n, (section, words) in enumerate(SECTIONS.items()):
        for at, kind in enumerate((BlockKind.heading, BlockKind.verse)):
            sid = f"{n:04d}.{at:03d}-x"
            segments.append(
                Segment(
                    id=sid,
                    block_id=f"b{n:04d}{at}",
                    block_index=2 * n + at,
                    index=0,
                    kind=kind,
                    level=2 if kind is BlockKind.heading else None,
                    text=SENTENCE,
                    ref="" if kind is BlockKind.heading else f"X {section}:1",
                )
            )
        tokens[sid] = [
            {"start": 0, "end": 1, "surface": SENTENCE, "lemma": w, "pos": "NOUN"} for w in words
        ]
    segmented = SegmentedDocument(
        document_hash=document_hash, language="he", segmenter="test", segments=segments
    )
    (folder / "segments.json").write_text(segmented.model_dump_json(), encoding="utf-8")
    annotation = {"document_hash": document_hash, "language": "he", "tokens": tokens}
    (folder / "annotation.json").write_text(json.dumps(annotation), encoding="utf-8")
    document = {
        "content_hash": document_hash,
        "source": source or f"gutenberg:{name}",
        "ingester": ingester,
        "language": "he",
    }
    (folder / "document.json").write_text(json.dumps(document), encoding="utf-8")
    reader = folder / "reader"
    reader.mkdir()
    for number in SECTIONS:
        (reader / f"sec-{number:04d}.html").write_text("", encoding="utf-8")
    return document_hash


@pytest.fixture
def book(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    file = tmp_path / "corpus.db"
    monkeypatch.setenv("TARGUM_LEDGER", str(file))
    monkeypatch.delenv("TARGUM_OPERATORS", raising=False)
    return file


@pytest.fixture
def library(tmp_path: Path) -> Path:
    root = tmp_path / "library"
    root.mkdir()
    return root


@pytest.fixture
def accounts(tmp_path: Path) -> AccountStore:
    return AccountStore(tmp_path / "targum.db")


def _person(accounts: AccountStore, email: str) -> Any:
    accounts.start_sign_in(email)
    person = accounts.person_by_email(email)
    assert person is not None
    return person


def _readers(accounts: AccountStore, n: int, prefix: str = "reader") -> list[Any]:
    return [_person(accounts, f"{prefix}{one}@x.test") for one in range(n)]


def _finish(accounts: AccountStore, person: Any, document: str, section: int = 1) -> None:
    accounts.add_events(
        person,
        [
            {
                "kind": "section",
                "day": DAY,
                "at": AT,
                "document": document,
                "segment": str(section),
                "amount": len(SECTIONS[section]),
                "language": "he",
            }
        ],
    )


def _look_up(accounts: AccountStore, person: Any, document: str, word: str) -> None:
    accounts.add_events(
        person,
        [
            {
                "kind": "lookup",
                "day": DAY,
                "at": AT,
                "document": document,
                "segment": "0000.000-x",
                "word": word,
                "language": "he",
            }
        ],
    )


def _know(
    accounts: AccountStore, person: Any, lemma: str, *, at: int = AT, source: str = ""
) -> None:
    with accounts.write() as db:
        db.execute(
            "INSERT OR REPLACE INTO word (person, language, lemma, status, band, source, at,"
            " known_at) VALUES (?, 'he', ?, 9, 'easy', ?, ?, ?)",
            (person.id, lemma, source, at, at),
        )


def _pool(library: Path, book: Path, accounts: AccountStore) -> difficulty.PoolResult:
    with sqlite3.connect(f"file:{accounts.path}?mode=ro", uri=True) as db:
        return difficulty.pool(
            library, Store(book), db, accounts.pooled_readers(), today=date(2026, 11, 2)
        )


def _rows(book: Path) -> list[tuple[str, str, int]]:
    with sqlite3.connect(book) as db:
        return [
            (str(key), str(variant), int(n))
            for key, variant, n in db.execute(
                "SELECT t.key, t.variant, t.n FROM tally t JOIN contribution c"
                " ON c.id = t.contribution_id WHERE c.tbl = ? ORDER BY 1, 2",
                (DIFFICULTY,),
            )
        ]


def _every_cell(file: Path) -> str:
    with sqlite3.connect(file) as db:
        names = [row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        cells = []
        for name in names:
            for row in db.execute(f"SELECT * FROM {name}"):  # noqa: S608
                cells.extend(str(value) for value in row)
    return "\n".join(cells)


# -- what the card asks -----------------------------------------------------------------


def test_no_row_holds_a_person_a_document_or_a_text(
    book: Path, library: Path, accounts: AccountStore
) -> None:
    text = _built(library, "shared", "alpha")
    readers = _readers(accounts, 10)
    for one in readers:
        _finish(accounts, one, text)
        _look_up(accounts, one, text, "w1")
    result = _pool(library, book, accounts)
    assert result.readers == 10 and result.cells == 3
    assert difficulty.held(Store(book)) == ["pool-2026-11-02"], "the unit is the night"

    for key, variant, _n in _rows(book):
        assert key in {"w1", "w2", "w3", "w4"}, key
        rung, measure = variant.split("|")
        assert measure in difficulty.MEASURES
        assert rung == difficulty.UNRANKED or re.fullmatch(r"[a-z ]+|[ABC][12]", rung)
    everything = _every_cell(book)
    for leaked in (text, "alpha", SENTENCE, "gutenberg", "x.test", "reader0", str(library)):
        assert leaked not in everything, leaked
    with sqlite3.connect(book) as db:
        columns = {row[1] for row in db.execute("PRAGMA table_info(tally)")}
    assert columns == {"contribution_id", "key", "variant", "n"}, "no column for a person"


def test_a_cell_under_the_floor_reads_as_absent(
    book: Path, library: Path, accounts: AccountStore
) -> None:
    assert difficulty.FLOOR == 10, "David, 2026-10-30: ten, not twenty"
    text = _built(library, "shared", "alpha")
    readers = _readers(accounts, 9)
    for one in readers:
        _finish(accounts, one, text)
    _pool(library, book, accounts)
    store = Store(book)
    assert ("w1", f"{difficulty.UNRANKED}|readers", 9) in _rows(book), "written, and kept"
    assert difficulty.cell("w1", difficulty.UNRANKED, store=store) is None, "but read as absent"

    _finish(accounts, _person(accounts, "tenth@x.test"), text)
    _pool(library, book, accounts)
    found = difficulty.cell("w1", difficulty.UNRANKED, store=store)
    assert found == difficulty.Cell(looked_up=0.0, known=0.0, skipped=1.0)


def test_a_reader_who_erases_their_record_is_gone_after_the_next_run(
    book: Path, library: Path, accounts: AccountStore
) -> None:
    text = _built(library, "shared", "alpha")
    readers = _readers(accounts, 10)
    for one in readers:
        _finish(accounts, one, text)
    leaving = readers[0]
    _look_up(accounts, leaving, text, "w1")
    _know(accounts, leaving, "w2")
    _pool(library, book, accounts)
    store = Store(book)
    assert difficulty.cell("w1", difficulty.UNRANKED, store=store) is not None
    before = dict(((key, variant), n) for key, variant, n in _rows(book))
    assert before[("w1", f"{difficulty.UNRANKED}|lookups")] == 1
    known = [
        variant for key, variant, n in _rows(book) if key == "w2" and variant.endswith("known")
    ]
    assert known and sum(before[("w2", one)] for one in known) == 1

    accounts.forget_events(leaving)
    _pool(library, book, accounts)
    after = dict(((key, variant), n) for key, variant, n in _rows(book))
    assert after[("w1", f"{difficulty.UNRANKED}|readers")] == 9
    assert after[("w1", f"{difficulty.UNRANKED}|lookups")] == 0
    # The mark is still on their list, and counts for nothing: it hung off the record.
    assert sum(n for (key, variant), n in after.items() if key == "w2" and "known" in variant) == 0
    assert difficulty.cell("w1", difficulty.UNRANKED, store=store) is None
    with sqlite3.connect(book) as db:
        nights = db.execute("SELECT COUNT(*) FROM contribution WHERE tbl = ?", (DIFFICULTY,))
        assert nights.fetchone()[0] == 1, "last night is deleted, not kept beside tonight"


def test_nothing_on_a_page_reads_the_pool_and_no_count_of_readers_leaves_it() -> None:
    assert set(difficulty.Cell.__dataclass_fields__) == {"looked_up", "known", "skipped"}
    surfaces = [ROOT / "src" / "targum" / "serve.py", *(ROOT / "src/targum/render").rglob("*")]
    for file in surfaces:
        if file.is_file() and file.suffix in {".py", ".j2", ".js", ".html"}:
            body = file.read_text(encoding="utf-8")
            assert "tables.difficulty" not in body and "difficulty.cell" not in body, file


# -- who and what counts ----------------------------------------------------------------


def test_operators_admins_tests_leavers_and_the_record_off_are_not_read(
    accounts: AccountStore,
) -> None:
    reader = _person(accounts, "reader@x.test")
    operator = _person(accounts, "o.wner+beta@gmail.com")
    accounts.make_admin("admin@x.test")
    accounts.make_test_account("tester@x.test")
    _person(accounts, "admin@x.test")
    _person(accounts, "tester@x.test")
    quiet = _person(accounts, "quiet@x.test")
    accounts.set_collects(quiet, False)
    leaver = _person(accounts, "leaver@x.test")
    with accounts.write() as db:
        db.execute("UPDATE person SET leaving = 1 WHERE id = ?", (leaver.id,))
    assert accounts.pooled_readers(["owner@gmail.com"]) == {reader.id}
    assert accounts.pooled_readers() == {reader.id, operator.id}, "the operator is named"
    accounts.set_collects(quiet, True)
    assert quiet.id in accounts.pooled_readers(["owner@gmail.com"])


def test_only_public_redistributable_texts_count_and_never_a_private_import(
    book: Path, library: Path, accounts: AccountStore
) -> None:
    public = _built(library, "shared", "alpha")
    home = _built(library, "p1", "mine", source="https://x.test/a", ingester="url/6")
    course = _built(library, "shared", "lesson", source="course:it:book:1", ingester="course/1")
    unlicensed = _built(library, "shared", "news", source="https://x.test/n", ingester="url/6")
    assert set(difficulty.counted_texts(library)) == {public}
    readers = _readers(accounts, 10)
    for one in readers:
        for text in (home, course, unlicensed):
            _finish(accounts, one, text, section=2)
            _look_up(accounts, one, text, "w4")
    result = _pool(library, book, accounts)
    assert result.cells == 0 and result.withheld == 60
    assert _rows(book) == []


def test_a_skip_is_a_word_neither_looked_up_there_nor_known(
    book: Path, library: Path, accounts: AccountStore
) -> None:
    text = _built(library, "shared", "alpha")
    readers = _readers(accounts, 10)
    for one in readers:
        _finish(accounts, one, text)
    _look_up(accounts, readers[0], text, "w1")
    _know(accounts, readers[1], "w2", source="claimed")
    _pool(library, book, accounts)
    rows = dict(((key, variant), n) for key, variant, n in _rows(book))
    assert rows[("w1", f"{difficulty.UNRANKED}|skips")] == 9
    assert rows[("w3", f"{difficulty.UNRANKED}|skips")] == 10
    # A word ticked on "Words you may already know" is not passed over, and is not a
    # mark known either.
    assert rows[("w2", f"{difficulty.UNRANKED}|skips")] == 9
    assert not any(
        key == "w2" and variant.endswith("|known") and n for (key, variant), n in rows.items()
    )


def test_the_rung_is_the_one_the_reader_had_at_the_time(
    book: Path, library: Path, accounts: AccountStore
) -> None:
    text = _built(library, "shared", "alpha")
    readers = _readers(accounts, 10)
    later = AT + 86_400_000
    for one in readers:
        _finish(accounts, one, text)
        # 320 easy words known a day after the section was finished: aleph, from then.
        with accounts.write() as db:
            db.executemany(
                "INSERT INTO word (person, language, lemma, status, band, at, known_at)"
                " VALUES (?, 'he', ?, 9, 'easy', ?, ?)",
                [(one.id, f"k{n}", later, later) for n in range(320)],
            )
        accounts.add_events(
            one,
            [
                {
                    "kind": "lookup",
                    "day": "2026-11-02",
                    "at": later + 1,
                    "document": text,
                    "word": "w4",
                    "language": "he",
                }
            ],
        )
    _pool(library, book, accounts)
    store = Store(book)
    assert difficulty.cell("w1", difficulty.UNRANKED, store=store) is not None
    assert difficulty.cell("w4", "aleph", store=store) == difficulty.Cell(
        looked_up=1.0, known=0.0, skipped=None
    ), "ten readers looked it up at aleph, none of them having met it in a finished section"
    assert difficulty.cell("w4", difficulty.UNRANKED, store=store) is None


# -- the clause, and the box ------------------------------------------------------------


def test_the_notice_carries_the_clause_word_for_word() -> None:
    """David approved the sentence on 2026-10-30 with the floor at ten."""
    assert "at least ten Data Subjects, and each count is made afresh daily" in difficulty.CLAUSE
    assert difficulty.notice_carries_clause(legal_page("privacy"))
    assert not difficulty.notice_carries_clause(legal_page("terms"))


def _notice(tmp_path: Path, page: str) -> str:
    file = tmp_path / "privacy.html"
    file.write_text(page, encoding="utf-8")
    return file.as_uri()


def test_the_job_refuses_and_deletes_the_pool_unless_the_served_notice_carries_the_clause(
    book: Path, library: Path, accounts: AccountStore, tmp_path: Path
) -> None:
    text = _built(library, "shared", "alpha")
    for one in _readers(accounts, 10):
        _finish(accounts, one, text)
    command = ["tables", "pool", "--library", str(library), "--store", str(accounts.path)]

    live = _notice(tmp_path, legal_page("privacy"))
    done = CliRunner().invoke(app, [*command, "--notice", live])
    assert done.exit_code == 0, done.output
    assert difficulty.held(Store(book)), "pooled"

    stale = _notice(tmp_path, legal_page("privacy").replace("passed over", "skipped"))
    done = CliRunner().invoke(app, [*command, "--notice", stale])
    assert done.exit_code != 0
    assert "does not carry clause 3.7" in done.output
    assert difficulty.held(Store(book)) == [], "and the pool it had is gone"

    shut = (tmp_path / "nowhere.html").as_uri()
    done = CliRunner().invoke(app, [*command, "--notice", shut])
    assert done.exit_code != 0, "a notice that cannot be read is not live"


def test_the_pool_runs_in_a_fresh_process_without_a_model(
    book: Path, library: Path, accounts: AccountStore, tmp_path: Path
) -> None:
    text = _built(library, "shared", "alpha")
    for one in _readers(accounts, 10):
        _finish(accounts, one, text)
    live = _notice(tmp_path, legal_page("privacy"))
    probe = (
        "import sys\n"
        "from targum.cli import app\n"
        "try:\n"
        f"    app(['tables', 'pool', '--library', {str(library)!r}, '--store',"
        f" {str(accounts.path)!r}, '--notice', {live!r}])\n"
        "except SystemExit as stop:\n"
        "    assert not stop.code, stop.code\n"
        "heavy = sorted(m for m in sys.modules if m.split('.')[0] in"
        " __import__('targum.tables', fromlist=['x']).MODEL_PACKAGES)\n"
        "print('HEAVY', heavy)\n"
    )
    env = {"TARGUM_LEDGER": str(book), "PATH": "/usr/bin:/bin"}
    env.update({key: os.environ[key] for key in ("PYTHONPATH", "HOME") if key in os.environ})
    done = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, text=True, env=env, check=False
    )
    assert done.returncode == 0, done.stderr
    assert "Pooled 3 cells from 10 readers" in done.stdout
    assert "HEAVY []" in done.stdout


def _unit(name: str) -> dict[str, list[str]]:
    fields: dict[str, list[str]] = {}
    for line in (DEPLOY / name).read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.startswith(("#", "[")):
            key, value = line.split("=", 1)
            fields.setdefault(key.strip(), []).append(value.strip())
    return fields


def test_the_nightly_unit_reads_the_served_notice_and_talks_to_nothing_else() -> None:
    service = _unit("targum-difficulty.service")
    assert service["ExecStart"] == [
        "/usr/local/bin/targum tables pool --library /var/lib/targum/targums"
        " --store /var/lib/targum/targum.db --notice http://127.0.0.1:8420/privacy"
    ]
    assert difficulty.NOTICE == "http://127.0.0.1:8420/privacy"
    assert service["User"] == ["targum"] and service["Group"] == ["targum"], "never root"
    assert service["IPAddressDeny"] == ["any"] and service["IPAddressAllow"] == ["localhost"]
    assert service["MemoryMax"] == ["1G"]
    timer = _unit("targum-difficulty.timer")
    sweep = _unit("targum-tables.timer")["OnCalendar"][0]
    backup = _unit("targum-backup.timer")["OnCalendar"][0]
    assert sweep < timer["OnCalendar"][0] < backup, "after the sweep, in the night's backup"
    script = (DEPLOY / "deploy.sh").read_text(encoding="utf-8")
    assert "deploy/targum-difficulty.service deploy/targum-difficulty.timer" in script
    loop = next(line for line in script.splitlines() if line.strip().startswith("for unit in"))
    assert "targum-difficulty.service targum-difficulty.timer" in loop
    enable = next(line for line in script.splitlines() if "systemctl enable --now --quiet" in line)
    assert "targum-difficulty.timer" in enable


def test_only_the_pool_writes_the_table_and_no_push_carries_it(book: Path, tmp_path: Path) -> None:
    store = Store(book)
    made = difficulty.contribution("he", "2026-11-02")
    with pytest.raises(ValueError, match="difficulty"):
        store.write(made, {("w1", "unranked|readers"): 10})
    store.replace_difficulty([made], {made.id: {("w1", "unranked|readers"): 10}})
    other = Contribution("words", "modern", "a" * 64, "test:a", "CC BY 4.0", "t/1", "words/1")
    store.write(other, {("w1", "NOUN"): 1})
    lines = list(store.export())
    assert len(lines) == 1 and DIFFICULTY not in lines[0], "the laptop's push never carries it"
    line = json.loads(lines[0])
    line["contribution"].update(id="b" * 64, tbl=DIFFICULTY, unit="pool-2026-11-03")
    assert Store(tmp_path / "box.db").import_rows([json.dumps(line)]).refused == 1
