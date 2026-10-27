"""The corpus ledger's first slice: the `vocalize` stage, as rows (targum-internal#162).

Three promises, each with a test: with the flag off nothing changes, byte for byte; a
value goes in as rows and comes back as the same bytes; and the cache can be rebuilt
from the rows alone.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from targum import ledger
from targum.cache import Cache
from targum.models import Annotation, Segment, Token, Vocalization
from targum.paths import cache_dir

POINTED = Vocalization(
    document_hash="doc123",
    language="he",
    vocalizer="dicta/menaked/1",
    model="dictabert-large-char-menaked",
    # Out of document order on purpose, and `machine` in an order of its own: the rows
    # have to keep both, or the file they rebuild is not the file that was written.
    segments={"s2": "אַבָּא בָּא.", "s0": "שָׁלוֹם.", "s1": "אִמָּא בָּאָה."},
    machine=["s1", "s2"],
    # A rejected segment has no pointed form: it is in no other list.
    rejected=["s3"],
).model_dump(mode="json")


def _tree(root: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file() and "models" not in path.relative_to(root).parts
    }


class Named:
    """Points every alef, and counts how often it was asked."""

    model = None

    def __init__(self, name: str) -> None:
        self.name = name
        self.asked = 0

    def available(self) -> tuple[bool, str]:
        return True, ""

    def vocalize(self, segments: list[Segment], language: str) -> dict[str, str]:
        self.asked += 1
        return {segment.id: segment.text.replace("א", "אַ") for segment in segments}


def _build(source: Path, out: Path, segmenter: object, engine: Named) -> None:
    from targum.pipeline import Build

    Build(
        str(source),
        provider_name="null",
        out=out,
        segmenter=segmenter,  # type: ignore[arg-type]
        target_language="en",
        vocalizer=engine,
    ).run()


@pytest.fixture
def source(tmp_path: Path) -> Path:
    path = tmp_path / "text.md"
    path.write_text("# כותרת\n\nאבא בא. אמא באה.\n", encoding="utf-8")
    return path


class TestTheFlagOff:
    def test_off_is_the_default_and_opens_no_database(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        def refuse(*args: Any, **kwargs: Any) -> None:
            raise AssertionError("the ledger opened a database with the flag off")

        monkeypatch.setattr(ledger.sqlite3, "connect", refuse)
        assert ledger.path() is None
        cache = Cache(tmp_path / "cache")
        cache.put("vocalize", "ab" + "0" * 62, POINTED)
        cache.drop("vocalize", "ab" + "0" * 62)

    def test_a_build_writes_the_same_bytes_with_the_flag_off_as_on(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        source: Path,
        fake_segmenter: object,
    ) -> None:
        """Every cache file and the reader's pointing, compared byte for byte; and with
        the flag off, no ledger file anywhere."""
        trees = {}
        for flag in ("off", "on"):
            monkeypatch.setenv("TARGUM_CACHE_DIR", str(tmp_path / flag / "cache"))
            if flag == "on":
                monkeypatch.setenv(ledger.ENV, str(tmp_path / "ledger" / "corpus.db"))
            _build(source, tmp_path / flag / "out", fake_segmenter, Named("fake/1"))
            trees[flag] = _tree(cache_dir())
            trees[flag]["vocalization.json"] = (
                tmp_path / flag / "out" / "vocalization.json"
            ).read_bytes()
        assert any(name.startswith("vocalize/") for name in trees["off"])
        assert trees["off"] == trees["on"]
        assert not list((tmp_path / "off").rglob("*.db"))
        assert (tmp_path / "ledger" / "corpus.db").is_file()

    def test_a_ledger_that_cannot_write_costs_the_cache_nothing(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        (tmp_path / "taken").mkdir()
        monkeypatch.setenv(ledger.ENV, str(tmp_path / "taken"))
        cache = Cache(tmp_path / "cache")
        key = "cd" + "1" * 62
        cache.put("vocalize", key, POINTED)
        assert cache.get("vocalize", key) == POINTED

    def test_other_stages_are_not_recorded(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setenv(ledger.ENV, str(tmp_path / "corpus.db"))
        Cache(tmp_path / "cache").put("translate", "ef" + "2" * 62, {"segments": {}})
        assert not (tmp_path / "corpus.db").exists()


class TestRoundTrip:
    def test_a_value_comes_back_as_the_same_bytes(self, tmp_path: Path) -> None:
        book = ledger.Ledger(tmp_path / "corpus.db")
        book.record("vocalize", "k1", POINTED)
        back = book.get("vocalize", "k1")
        assert json.dumps(back, ensure_ascii=False) == json.dumps(POINTED, ensure_ascii=False)

    def test_each_row_names_its_tool_and_version(self, tmp_path: Path) -> None:
        book = ledger.Ledger(tmp_path / "corpus.db")
        book.record("vocalize", "k1", POINTED)
        with sqlite3.connect(book.file) as db:
            row = db.execute(
                "SELECT stage, document_hash, tool, tool_version FROM vocalizations"
            ).fetchone()
            pointings = db.execute("SELECT COUNT(*) FROM pointings").fetchone()[0]
        assert row == ("vocalize", "doc123", "dicta/menaked/1", "dictabert-large-char-menaked")
        assert pointings == 4

    def test_a_renamed_tool_adds_rows_and_keeps_the_old(self, tmp_path: Path) -> None:
        book = ledger.Ledger(tmp_path / "corpus.db")
        book.record("vocalize", "k1", POINTED)
        book.record("vocalize", "k2", {**POINTED, "vocalizer": "dicta/menaked/2"})
        with sqlite3.connect(book.file) as db:
            tools = [row[0] for row in db.execute("SELECT tool FROM vocalizations ORDER BY id")]
        assert tools == ["dicta/menaked/1", "dicta/menaked/2"]

    def test_the_same_key_again_answers_with_the_new_and_keeps_the_old(
        self, tmp_path: Path
    ) -> None:
        """David, 2026-10-03: a rewrite under the same key keeps history, so a forced
        rebuild leaves a comparison behind. The key still has one answer."""
        book = ledger.Ledger(tmp_path / "corpus.db")
        book.record("vocalize", "k1", POINTED)
        fewer = {**POINTED, "segments": {"s0": "שָׁלוֹם."}, "machine": [], "rejected": []}
        book.record("vocalize", "k1", fewer)
        assert book.get("vocalize", "k1") == fewer
        assert [key for key, _ in book.entries("vocalize")] == ["k1"], "one answer a key"
        held = book.history("vocalize", "k1")
        assert [value for _, _, value in held] == [POINTED, fewer]
        assert held[0][1] is not None and held[1][1] is None, "the old one is stamped"

    def test_a_dropped_answer_is_kept_as_history(self, tmp_path: Path) -> None:
        book = ledger.Ledger(tmp_path / "corpus.db")
        book.record("vocalize", "k1", POINTED)
        assert book.drop("vocalize", "k1")
        assert book.get("vocalize", "k1") is None
        assert not book.drop("vocalize", "k1"), "nothing current is left to drop"
        assert [value for _, _, value in book.history("vocalize", "k1")] == [POINTED]
        book.record("vocalize", "k1", POINTED)
        assert book.get("vocalize", "k1") == POINTED

    def test_a_ledger_written_under_schema_1_is_brought_up_in_place(self, tmp_path: Path) -> None:
        """The box has had a `corpus.db` since 2026-10-04. Its rows come across as they
        were, current, and the key can be written again without a UNIQUE refusal."""
        file = tmp_path / "corpus.db"
        old = ledger.Ledger(file)
        old.record("vocalize", "k1", POINTED)
        with sqlite3.connect(file) as db:
            # The schema-1 table, as the box has it: the key UNIQUE, no stamp.
            db.executescript(
                "CREATE TABLE v1 AS SELECT id, stage, cache_key, document_hash, language,"
                " tool, tool_version, schema_version, written_at FROM vocalizations;"
                " DROP TABLE vocalizations;"
                " CREATE TABLE vocalizations (id INTEGER PRIMARY KEY, stage TEXT NOT NULL,"
                " cache_key TEXT NOT NULL UNIQUE, document_hash TEXT NOT NULL,"
                " language TEXT NOT NULL, tool TEXT NOT NULL, tool_version TEXT,"
                " schema_version INTEGER NOT NULL, written_at TEXT NOT NULL);"
                " INSERT INTO vocalizations SELECT * FROM v1; DROP TABLE v1;"
                " DROP INDEX IF EXISTS vocalizations_current;"
                " UPDATE meta SET value = '1' WHERE key = 'schema';"
            )
        book = ledger.Ledger(file)
        assert book.get("vocalize", "k1") == POINTED
        book.record("vocalize", "k1", {**POINTED, "machine": []})
        assert len(book.history("vocalize", "k1")) == 2
        with sqlite3.connect(file) as db:
            assert db.execute("SELECT value FROM meta WHERE key = 'schema'").fetchone() == (
                str(ledger.LEDGER_SCHEMA),
            )
            assert db.execute("SELECT COUNT(*) FROM pointings").fetchone()[0] == 8

    def test_a_migration_that_died_part_way_is_finished_by_the_next_open(
        self, tmp_path: Path
    ) -> None:
        """Review, 2026-10-08: a copy that failed after making `vocalizations_2` left it
        behind, and every later open failed on it, so the ledger stopped recording and a
        departed reader's rows were never forgotten."""
        file = tmp_path / "corpus.db"
        ledger.Ledger(file).record("vocalize", "k1", POINTED)
        with sqlite3.connect(file) as db:
            db.executescript(
                "CREATE TABLE v1 AS SELECT id, stage, cache_key, document_hash, language,"
                " tool, tool_version, schema_version, written_at FROM vocalizations;"
                " DROP TABLE vocalizations;"
                " CREATE TABLE vocalizations (id INTEGER PRIMARY KEY, stage TEXT NOT NULL,"
                " cache_key TEXT NOT NULL UNIQUE, document_hash TEXT NOT NULL,"
                " language TEXT NOT NULL, tool TEXT NOT NULL, tool_version TEXT,"
                " schema_version INTEGER NOT NULL, written_at TEXT NOT NULL);"
                " INSERT INTO vocalizations SELECT * FROM v1; DROP TABLE v1;"
                " DROP INDEX IF EXISTS vocalizations_current;"
                " UPDATE meta SET value = '1' WHERE key = 'schema';"
                # What a migration that died after its first statement left behind.
                " CREATE TABLE vocalizations_2 (id INTEGER PRIMARY KEY);"
            )
        book = ledger.Ledger(file)
        assert book.get("vocalize", "k1") == POINTED
        book.record("vocalize", "k1", {**POINTED, "machine": []})
        with sqlite3.connect(file) as db:
            assert db.execute("SELECT value FROM meta WHERE key = 'schema'").fetchone() == (
                str(ledger.LEDGER_SCHEMA),
            )
            assert not db.execute(
                "SELECT 1 FROM sqlite_master WHERE name = 'vocalizations_2'"
            ).fetchone()

    def test_the_same_value_again_adds_no_history(self, tmp_path: Path) -> None:
        """A rebuild that changed nothing writes nothing: otherwise every `rebuild --words`
        adds a copy of every text's tokens (review, 2026-10-08)."""
        book = ledger.Ledger(tmp_path / "corpus.db")
        book.record("vocalize", "k1", POINTED)
        book.record("vocalize", "k1", POINTED)
        book.record("tokens", "t", _annotation("grammar/2"))
        book.record("tokens", "t", _annotation("grammar/2"))
        assert len(book.history("vocalize", "k1")) == 1
        assert len(book.history("tokens", "t")) == 1

    @pytest.mark.parametrize(
        "value",
        [
            {**POINTED, "extra": 1},
            {**POINTED, "machine": ["s1", "s1"]},
            {"segments": {}},
        ],
        ids=["an unknown field", "a repeated segment", "not a vocalization"],
    )
    def test_what_the_rows_could_not_give_back_is_refused_whole(
        self, tmp_path: Path, value: dict[str, Any]
    ) -> None:
        book = ledger.Ledger(tmp_path / "corpus.db")
        with pytest.raises(ValueError):
            book.record("vocalize", "k1", value)
        assert book.get("vocalize", "k1") is None

    def test_a_dropped_answer_is_dropped_from_the_ledger_too(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setenv(ledger.ENV, str(tmp_path / "corpus.db"))
        cache = Cache(tmp_path / "cache")
        cache.put("vocalize", "ab" + "3" * 62, POINTED)
        assert cache.drop("vocalize", "ab" + "3" * 62)
        assert ledger.Ledger(tmp_path / "corpus.db").get("vocalize", "ab" + "3" * 62) is None, (
            "no longer the answer, though kept as history"
        )


class TestRebuildFromRows:
    def test_the_cache_comes_back_from_the_rows_alone(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        source: Path,
        fake_segmenter: object,
    ) -> None:
        """Build with the flag on, delete the stage's cache, rebuild it from rows: the
        files are the same bytes, and a new build reads them rather than pointing again."""
        monkeypatch.setenv(ledger.ENV, str(tmp_path / "corpus.db"))
        _build(source, tmp_path / "first", fake_segmenter, Named("fake/1"))
        cache = Cache()
        before = _tree(cache.root / "vocalize")
        assert before

        for file in (cache.root / "vocalize").rglob("*.json"):
            file.unlink()
        written = ledger.rebuild(ledger.Ledger(tmp_path / "corpus.db"), cache)

        assert written == len(before)
        assert _tree(cache.root / "vocalize") == before
        again = Named("fake/1")
        _build(source, tmp_path / "second", fake_segmenter, again)
        assert again.asked == 0, "the rebuilt cache was not read"
        assert (tmp_path / "second" / "vocalization.json").read_bytes() == (
            tmp_path / "first" / "vocalization.json"
        ).read_bytes()

    def test_backfill_reads_today_s_cache_into_rows(self, tmp_path: Path) -> None:
        """The migration in small: an existing cache, no flag, read into rows."""
        cache = Cache(tmp_path / "cache")
        cache.put("vocalize", "ab" + "4" * 62, POINTED)
        cache.put("vocalize", "cd" + "5" * 62, {**POINTED, "vocalizer": "nakdimon/2"})
        cache.put("translate", "ef" + "6" * 62, {"segments": {}})
        (tmp_path / "cache" / "vocalize" / "zz").mkdir()
        (tmp_path / "cache" / "vocalize" / "zz" / "torn.json").write_text("{", encoding="utf-8")
        book = ledger.Ledger(tmp_path / "corpus.db")

        assert ledger.backfill(book, cache) == (2, 1)
        assert dict(book.entries("vocalize")) == {
            "ab" + "4" * 62: POINTED,
            "cd" + "5" * 62: {**POINTED, "vocalizer": "nakdimon/2"},
        }


def _annotation(annotator: str, lemma_of_bayit: str = "בית") -> dict[str, Any]:
    """An annotation as the pipeline writes one: segments out of order, a token with a
    nested field, and the method fields only a reader of the file wants."""
    return Annotation(
        document_hash="doc123",
        language="he",
        annotator=annotator,
        method="test",
        method_note="two segments",
        scripture_share=0.5,
        tokens={
            "s1": [
                Token(
                    start=0,
                    end=3,
                    surface="בית",
                    lemma=lemma_of_bayit,
                    band=1,
                    pos="NOUN",
                    feats="Gender=Masc",
                ),
                Token(start=4, end=8, surface="גדול", lemma="גדול", band=2, pos="ADJ"),
            ],
            "s0": [Token(start=0, end=4, surface="שלום", lemma="שלום", band=0, pos="INTJ")],
        },
    ).model_dump(mode="json")


class TestTokens:
    """The second stage (David, 2026-10-03): one annotator's pass over a text, as rows."""

    def test_an_annotation_comes_back_as_the_same_bytes(self, tmp_path: Path) -> None:
        book = ledger.Ledger(tmp_path / "corpus.db")
        value = _annotation("grammar/2")
        book.record("tokens", "doc123:grammar/2", value)
        back = book.get("tokens", "doc123:grammar/2")
        assert json.dumps(back, ensure_ascii=False) == json.dumps(value, ensure_ascii=False)
        with sqlite3.connect(book.file) as db:
            rows = db.execute(
                "SELECT segment_id, ord, form, lemma, pos, features, band FROM tokens"
                " ORDER BY segment_ord, ord"
            ).fetchall()
        assert rows == [
            ("s1", 0, "בית", "בית", "NOUN", "Gender=Masc", 1),
            ("s1", 1, "גדול", "גדול", "ADJ", None, 2),
            ("s0", 0, "שלום", "שלום", "INTJ", None, 0),
        ]

    def test_two_annotators_on_one_text_can_be_compared_token_by_token(
        self, tmp_path: Path
    ) -> None:
        """Criterion 2: a rename keeps the old pass, and agreement is one self-join."""
        book = ledger.Ledger(tmp_path / "corpus.db")
        book.record("tokens", "doc123:grammar/2", _annotation("grammar/2"))
        book.record("tokens", "doc123:grammar/3", _annotation("grammar/3", "בַּיִת"))
        with sqlite3.connect(book.file) as db:
            agree, total = db.execute(
                "SELECT SUM(a.lemma = b.lemma), COUNT(*) FROM tokens a"
                " JOIN annotations x ON x.id = a.annotation_id AND x.tool = 'grammar/2'"
                " JOIN tokens b ON b.segment_id = a.segment_id AND b.ord = a.ord"
                " JOIN annotations y ON y.id = b.annotation_id AND y.tool = 'grammar/3'"
                "  AND y.document_hash = x.document_hash"
            ).fetchone()
        assert (agree, total) == (2, 3)

    def test_the_same_pass_again_keeps_the_old_as_history(self, tmp_path: Path) -> None:
        book = ledger.Ledger(tmp_path / "corpus.db")
        book.record("tokens", "k", _annotation("grammar/2"))
        book.record("tokens", "k", _annotation("grammar/2", "בַּיִת"))
        assert [key for key, _ in book.entries("tokens")] == ["k"]
        assert len(book.history("tokens", "k")) == 2
        assert book.get("tokens", "k")["tokens"]["s1"][0]["lemma"] == "בַּיִת"

    @pytest.mark.parametrize(
        "broken",
        [
            lambda v: {k: v[k] for k in v if k != "tokens"},
            lambda v: {**v, "tokens": {"s0": "not a list"}},
            lambda v: {**v, "tokens": {"s0": []}},
        ],
        ids=["no tokens", "a segment that is not a list", "an empty segment"],
    )
    def test_what_the_rows_could_not_give_back_is_refused(self, tmp_path: Path, broken) -> None:
        book = ledger.Ledger(tmp_path / "corpus.db")
        with pytest.raises(ValueError):
            book.record("tokens", "k", broken(_annotation("grammar/2")))
        assert book.get("tokens", "k") is None

    def test_the_pipeline_records_the_pass_it_writes(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Where `annotation.json` is written, with the flag on, keyed by text and tool."""
        monkeypatch.setenv(ledger.ENV, str(tmp_path / "corpus.db"))
        value = _annotation("grammar/2")
        ledger.mirror_put("tokens", "doc123:grammar/2", value)
        assert ledger.Ledger(tmp_path / "corpus.db").get("tokens", "doc123:grammar/2") == value
        import inspect

        from targum import pipeline

        said = inspect.getsource(pipeline.Build.annotate)
        assert "mirror_put(" in said and '"tokens"' in said, (
            "the build writes its pass to the ledger"
        )


class TestADepartedReader:
    """Decided 2026-10-03: account deletion reaches `corpus.db`. Their own texts go,
    history and all; a text the shared shelf or anybody else also has stays."""

    @staticmethod
    def _text(folder: Path, document_hash: str) -> None:
        folder.mkdir(parents=True)
        (folder / "vocalization.json").write_text(
            json.dumps({**POINTED, "document_hash": document_hash}, indent=2), encoding="utf-8"
        )

    def test_the_ledger_forgets_only_what_was_theirs_alone(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        from targum.accounts import Store
        from targum.serve import Library

        monkeypatch.setenv(ledger.ENV, str(tmp_path / "corpus.db"))
        store = Store(tmp_path / "targum.db")
        person, _ = store.finish_sign_in(store.start_sign_in("leaving@example.com"))  # type: ignore[misc]
        library = Library(tmp_path / "out", store=store)
        home = library.home(person)
        self._text(home / "my-upload", "a" * 64)
        self._text(home / "genesis", "b" * 64)
        self._text(library.shared / "genesis", "b" * 64)

        book = ledger.Ledger(tmp_path / "corpus.db")
        for hash_ in ("a" * 64, "b" * 64):
            book.record("vocalize", f"k-{hash_[0]}", {**POINTED, "document_hash": hash_})
            book.record(
                "tokens", f"{hash_}:grammar/2", {**_annotation("grammar/2"), "document_hash": hash_}
            )
        book.record("vocalize", "k-a", {**POINTED, "document_hash": "a" * 64, "machine": []})

        with store.write() as db:
            db.execute("UPDATE person SET leaving = 1 WHERE id = ?", (person.id,))
        assert library.purge_departed() == [person.id]

        assert not home.exists()
        assert book.get("vocalize", "k-a") is None
        assert book.history("vocalize", "k-a") == [], "history too: they asked for it to go"
        assert book.get("tokens", f"{'a' * 64}:grammar/2") is None
        assert book.get("vocalize", "k-b") is not None, "the shared shelf's Genesis stays"
        assert book.get("tokens", f"{'b' * 64}:grammar/2") is not None
        with sqlite3.connect(book.file) as db:
            assert db.execute("SELECT COUNT(*) FROM pointings").fetchone()[0] == 4
            orphans = db.execute(
                "SELECT COUNT(*) FROM tokens"
                " WHERE annotation_id NOT IN (SELECT id FROM annotations)"
            ).fetchone()[0]
        assert orphans == 0

    def test_with_the_ledger_off_a_departure_opens_no_database(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.delenv(ledger.ENV, raising=False)
        assert ledger.forget({"a" * 64}) == 0
        assert ledger.documents_under(tmp_path / "nowhere") == set()


class TestTexts:
    """The `texts` table (2026-10-27): one row a source document, and the two export bits
    every other row will copy, computed from the licence and never typed."""

    def test_the_bits_come_from_the_licence_and_whether_it_is_private(self, tmp_path: Path) -> None:
        book = ledger.Ledger(tmp_path / "corpus.db")
        book.record_text(ledger.Text("a" * 64, "gutenberg:1", "Public Domain"))
        book.record_text(ledger.Text("b" * 64, "https://x.example/a", "CC BY-NC 4.0"))
        book.record_text(ledger.Text("c" * 64, "upload.pdf", "CC BY 4.0", frozenset({"p7"})))
        book.record_text(ledger.Text("d" * 64, "https://x.example/b", ""))
        assert book.terms("a" * 64) == (True, True)
        assert book.terms("b" * 64) == (False, True)
        assert book.terms("c" * 64) == (False, False), "a private import, whatever its licence"
        assert book.terms("d" * 64) == (False, False), "no licence exports nowhere"
        assert book.terms("e" * 64) is None
        with sqlite3.connect(book.file) as db:
            exported = db.execute("SELECT COUNT(*) FROM texts WHERE exportable").fetchone()[0]
        assert exported == 1

    def test_a_corrected_licence_keeps_the_old_verdict_as_history(self, tmp_path: Path) -> None:
        book = ledger.Ledger(tmp_path / "corpus.db")
        first = ledger.Text("a" * 64, "https://x.example/a", "")
        assert book.record_text(first)
        assert not book.record_text(first), "the same row again is not history"
        assert book.record_text(ledger.Text("a" * 64, "https://x.example/a", "CC BY-SA 4.0"))
        assert book.terms("a" * 64) == (True, True)
        with sqlite3.connect(book.file) as db:
            rows = db.execute(
                "SELECT licence, exportable, superseded_at IS NULL FROM texts ORDER BY id"
            ).fetchall()
        assert rows == [("", 0, 0), ("CC BY-SA 4.0", 1, 1)]

    def test_a_schema_2_ledger_gains_the_table_in_place(self, tmp_path: Path) -> None:
        file = tmp_path / "corpus.db"
        ledger.Ledger(file).record("vocalize", "k1", POINTED)
        with sqlite3.connect(file) as db:
            db.executescript("DROP TABLE texts; UPDATE meta SET value = '2' WHERE key = 'schema';")
        book = ledger.Ledger(file)
        assert book.get("vocalize", "k1") == POINTED
        book.record_text(ledger.Text("a" * 64, "gutenberg:1", "Public Domain"))
        with sqlite3.connect(file) as db:
            assert db.execute("SELECT value FROM meta WHERE key = 'schema'").fetchone() == (
                str(ledger.LEDGER_SCHEMA),
            )

    @staticmethod
    def _built(folder: Path, document_hash: str, source: str) -> None:
        folder.mkdir(parents=True)
        document = {
            "schema_version": 4,
            "source": source,
            "language": "he",
            "blocks": [],
            "content_hash": document_hash,
            "ingester": "markdown/1",
        }
        (folder / "document.json").write_text(json.dumps(document), encoding="utf-8")

    def test_backfill_reads_the_shelf_and_marks_what_only_a_home_holds(
        self, tmp_path: Path
    ) -> None:
        out = tmp_path / "out"
        self._built(out / "shared" / "genesis", "a" * 64, "sefaria:Genesis")
        self._built(out / "p7" / "genesis", "a" * 64, "sefaria:Genesis")
        self._built(out / "p7" / "my-upload", "b" * 64, "upload.pdf")
        self._built(out / "weekly" / "issue-1", "c" * 64, "weekly:1")
        (out / "p7" / "broken").mkdir()
        licences = {"sefaria:Genesis": "CC BY-SA 4.0", "upload.pdf": "Public Domain"}

        book = ledger.Ledger(tmp_path / "corpus.db")
        recorded = ledger.backfill_texts(book, out, licence_of=lambda _f, s: licences.get(s, ""))
        assert recorded == (3, 0)
        assert ledger.backfill_texts(book, out, licence_of=lambda _f, s: licences.get(s, "")) == (
            0,
            3,
        ), "run again, it adds nothing"
        genesis = book.text("a" * 64)
        assert genesis is not None and genesis.homes == frozenset(), "the shelf holds it: corpus"
        assert genesis.ingester == "markdown/1" and genesis.schema_version == 4
        upload = book.text("b" * 64)
        assert upload is not None and upload.homes == {"p7"}
        assert book.terms("b" * 64) == (False, False)
        assert book.terms("a" * 64) == (True, True)
        assert book.terms("c" * 64) == (False, False), "no licence recorded for it"

    def test_a_departed_reader_s_text_row_goes_with_them(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setenv(ledger.ENV, str(tmp_path / "corpus.db"))
        book = ledger.Ledger(tmp_path / "corpus.db")
        book.record_text(ledger.Text("a" * 64, "upload.pdf", "", frozenset({"p7"})))
        book.record_text(ledger.Text("a" * 64, "upload.pdf", "CC BY 4.0", frozenset({"p7"})))
        book.record_text(ledger.Text("b" * 64, "gutenberg:1", "Public Domain"))
        ledger.forget({"a" * 64})
        assert book.text("a" * 64) is None
        with sqlite3.connect(book.file) as db:
            left = db.execute("SELECT document_hash FROM texts").fetchall()
        assert left == [("b" * 64,)], "history too, and nobody else's"

    def test_a_departed_reader_leaves_no_trace_on_a_text_another_still_holds(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Clause 3.14 (qa-claude on #942): p3 and p7 both imported one article; p3
        leaves. The text stays, as p7's, and no row and no history row names p3."""
        from targum.accounts import Store
        from targum.serve import Library

        monkeypatch.setenv(ledger.ENV, str(tmp_path / "corpus.db"))
        store = Store(tmp_path / "targum.db")
        leaving, _ = store.finish_sign_in(store.start_sign_in("leaving@example.com"))  # type: ignore[misc]
        staying, _ = store.finish_sign_in(store.start_sign_in("staying@example.com"))  # type: ignore[misc]
        library = Library(tmp_path / "out", store=store)
        gone, kept = library.home(leaving), library.home(staying)
        for home in (gone, kept):
            self._built(home / "article", "a" * 64, "https://x.example/a")
        book = ledger.Ledger(tmp_path / "corpus.db")
        assert ledger.backfill_texts(book, tmp_path / "out", licence_of=lambda _f, _s: "") == (1, 0)
        # And a history row written while both held it.
        ledger.backfill_texts(book, tmp_path / "out", licence_of=lambda _f, _s: "CC BY 4.0")
        assert book.text("a" * 64).homes == {gone.name, kept.name}  # type: ignore[union-attr]

        with store.write() as db:
            db.execute("UPDATE person SET leaving = 1 WHERE id = ?", (leaving.id,))
        assert library.purge_departed() == [leaving.id]

        held = book.text("a" * 64)
        assert held is not None and held.homes == {kept.name}
        assert book.terms("a" * 64) == (False, False), "still private: p7's"
        with sqlite3.connect(book.file) as db:
            every = " ".join(
                str(cell)
                for table in ("texts", "text_homes")
                for row in db.execute(f"SELECT * FROM {table}")  # noqa: S608
                for cell in row
            )
            assert len(db.execute("SELECT * FROM texts").fetchall()) == 2
        assert gone.name not in every.split()

    def test_a_changed_rule_supersedes_a_row_whose_facts_did_not_change(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """qa-claude on #942: rows written before David put our own writing in the
        commercial export read (False, False) until the verdict is part of "unchanged"."""
        from targum import licensing

        book = ledger.Ledger(tmp_path / "corpus.db")
        text = ledger.Text("a" * 64, "dialogue:1", "targum")
        monkeypatch.setattr(
            licensing, "export_terms", lambda _l, private=False: licensing.ExportTerms(False, False)
        )
        assert book.record_text(text)
        assert book.terms("a" * 64) == (False, False)
        monkeypatch.undo()
        assert book.record_text(text), "the rule moved, so the row is rewritten"
        assert book.terms("a" * 64) == (True, True)
        assert not book.record_text(text)
        with sqlite3.connect(book.file) as db:
            assert db.execute("SELECT COUNT(*) FROM texts").fetchone()[0] == 2

    def test_only_a_reader_s_home_is_private(self, tmp_path: Path) -> None:
        """The laptop's parasha, Russian shelf and dialogues are the library's own; only
        `p<id>` and `local` are homes. A text built straight into the library is public."""
        out = tmp_path / "out"
        self._built(out / "parasha" / "noach", "a" * 64, "parasha:noach")
        self._built(out / "russian" / "biryuk", "b" * 64, "wikisource:ru:Бирюк")
        self._built(out / "local" / "mine", "c" * 64, "mine.md")
        self._built(out / "declaration-he", "d" * 64, "declaration.md")
        book = ledger.Ledger(tmp_path / "corpus.db")
        assert ledger.backfill_texts(book, out, licence_of=lambda _f, _s: "Public Domain") == (
            4,
            0,
        )
        assert [book.terms(c * 64) for c in "abcd"] == [
            (True, True),
            (True, True),
            (False, False),
            (True, True),
        ]
        assert ledger.is_home("p12") and ledger.is_home("local")
        assert not ledger.is_home("parasha") and not ledger.is_home("pages")

    def test_the_command_refuses_with_the_ledger_off(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        from typer.testing import CliRunner

        from targum.cli import app

        monkeypatch.delenv(ledger.ENV, raising=False)
        result = CliRunner().invoke(app, ["cache", "ledger-texts", "--out", str(tmp_path)])
        assert result.exit_code != 0
        assert "ledger is off" in result.output

    def test_the_command_records_the_shelf(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        from typer.testing import CliRunner

        from targum.cli import app

        monkeypatch.setenv(ledger.ENV, str(tmp_path / "corpus.db"))
        self._built(tmp_path / "out" / "shared" / "one", "a" * 64, "gutenberg:1")
        result = CliRunner().invoke(app, ["cache", "ledger-texts", "--out", str(tmp_path / "out")])
        assert result.exit_code == 0, result.output
        assert "Recorded 1 texts" in result.output
        assert ledger.Ledger(tmp_path / "corpus.db").terms("a" * 64) == (True, True)


def _bits(file: Path, table: str) -> list[tuple[int, int]]:
    with sqlite3.connect(file) as db:
        return db.execute(f"SELECT exportable, research FROM {table} ORDER BY id").fetchall()  # noqa: S608


class TestTheBitsTravel:
    """Slice 2 (2026-10-27): every row made from a text carries the text's export bits,
    copied from `texts`, so an export of any table is one `WHERE`; and a build writes its
    text's row as it runs."""

    def test_rows_copy_their_text_s_bits_whichever_is_written_first(self, tmp_path: Path) -> None:
        book = ledger.Ledger(tmp_path / "corpus.db")
        book.record("vocalize", "k1", POINTED)
        assert _bits(book.file, "vocalizations") == [(0, 0)], "no text row: exports nowhere"
        book.record_text(ledger.Text("doc123", "gutenberg:1", "Public Domain"))
        assert _bits(book.file, "vocalizations") == [(1, 1)]
        book.record("tokens", "doc123:grammar/2", _annotation("grammar/2"))
        assert _bits(book.file, "annotations") == [(1, 1)], "written after: copied on write"
        book.record("vocalize", "k1", {**POINTED, "machine": []})
        book.record_text(ledger.Text("doc123", "gutenberg:1", "CC BY-NC 4.0"))
        assert _bits(book.file, "vocalizations") == [(0, 1), (0, 1)], "history too"
        assert _bits(book.file, "annotations") == [(0, 1)]
        with sqlite3.connect(book.file) as db:
            exportable = db.execute(
                "SELECT COUNT(*) FROM vocalizations WHERE exportable"
            ).fetchone()[0]
        assert exportable == 0

    def test_a_schema_3_ledger_gains_the_bits_in_place(self, tmp_path: Path) -> None:
        file = tmp_path / "corpus.db"
        ledger.Ledger(file).record("vocalize", "k1", POINTED)
        ledger.Ledger(file).record("tokens", "doc123:grammar/2", _annotation("grammar/2"))
        with sqlite3.connect(file) as db:
            db.executescript(
                "ALTER TABLE vocalizations DROP COLUMN exportable;"
                " ALTER TABLE vocalizations DROP COLUMN research;"
                " ALTER TABLE annotations DROP COLUMN exportable;"
                " ALTER TABLE annotations DROP COLUMN research;"
                " UPDATE meta SET value = '3' WHERE key = 'schema';"
            )
        book = ledger.Ledger(file)
        assert book.get("vocalize", "k1") == POINTED
        assert book.get("tokens", "doc123:grammar/2") == _annotation("grammar/2")
        assert book.record_text(ledger.Text("doc123", "gutenberg:1", "Public Domain"))
        assert _bits(file, "vocalizations") == [(1, 1)]
        assert _bits(file, "annotations") == [(1, 1)]
        with sqlite3.connect(file) as db:
            assert db.execute("SELECT value FROM meta WHERE key = 'schema'").fetchone() == ("4",)

    def test_an_unchanged_text_still_stamps_rows_written_before_it(self, tmp_path: Path) -> None:
        """A text recorded before its rows had the columns: running the backfill again
        changes no text row, and still brings the rows' bits up to it."""
        book = ledger.Ledger(tmp_path / "corpus.db")
        text = ledger.Text("doc123", "gutenberg:1", "Public Domain")
        book.record_text(text)
        book.record("vocalize", "k1", POINTED)
        with sqlite3.connect(book.file) as db:
            db.execute("UPDATE vocalizations SET exportable = 0, research = 0")
        assert not book.record_text(text)
        assert _bits(book.file, "vocalizations") == [(1, 1)]

    def test_a_reader_s_copy_of_a_shelf_text_leaves_it_public(self, tmp_path: Path) -> None:
        book = ledger.Ledger(tmp_path / "corpus.db")
        shelf = ledger.Text("a" * 64, "gutenberg:1", "Public Domain")
        book.hold(shelf, None)
        book.hold(shelf, "p3")
        assert book.text("a" * 64).homes == frozenset()  # type: ignore[union-attr]
        assert book.terms("a" * 64) == (True, True)

    def test_homes_gather_until_the_shelf_takes_the_text(self, tmp_path: Path) -> None:
        book = ledger.Ledger(tmp_path / "corpus.db")
        article = ledger.Text("a" * 64, "https://x.example/a", "CC BY 4.0")
        book.hold(article, "p3")
        book.hold(article, "p7")
        assert book.text("a" * 64).homes == {"p3", "p7"}  # type: ignore[union-attr]
        assert book.terms("a" * 64) == (False, False), "private, whatever its licence"
        book.hold(article, None)
        assert book.text("a" * 64).homes == frozenset()  # type: ignore[union-attr]
        assert book.terms("a" * 64) == (True, True)

    def test_a_build_records_its_text_and_its_rows_carry_the_bits(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        source: Path,
        fake_segmenter: object,
    ) -> None:
        monkeypatch.setenv("TARGUM_CACHE_DIR", str(tmp_path / "cache"))
        monkeypatch.setenv(ledger.ENV, str(tmp_path / "corpus.db"))
        monkeypatch.setattr(ledger, "_licence_of", lambda _folder, _source: "Public Domain")
        _build(source, tmp_path / "out" / "p5" / "text-he", fake_segmenter, Named("fake/1"))
        document = json.loads(
            (tmp_path / "out" / "p5" / "text-he" / "document.json").read_text(encoding="utf-8")
        )
        book = ledger.Ledger(tmp_path / "corpus.db")
        held = book.text(document["content_hash"])
        assert held is not None and held.homes == {"p5"} and held.licence == "Public Domain"
        assert _bits(book.file, "vocalizations") == [(0, 0)], "a reader's import"

        _build(source, tmp_path / "out" / "shared" / "text-he", fake_segmenter, Named("fake/1"))
        assert book.text(document["content_hash"]).homes == frozenset()  # type: ignore[union-attr]
        assert _bits(book.file, "vocalizations") == [(1, 1)]

    def test_a_text_that_cannot_be_recorded_costs_the_build_nothing(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setenv(ledger.ENV, str(tmp_path / "corpus.db"))
        (tmp_path / "p1" / "empty").mkdir(parents=True)
        ledger.mirror_text(tmp_path / "p1" / "empty")
        (tmp_path / "p1" / "empty" / "document.json").write_text("[]", encoding="utf-8")
        ledger.mirror_text(tmp_path / "p1" / "empty")

    def test_with_the_flag_off_a_build_opens_no_ledger(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        def refuse(*args: Any, **kwargs: Any) -> None:
            raise AssertionError("the ledger opened a database with the flag off")

        monkeypatch.delenv(ledger.ENV, raising=False)
        monkeypatch.setattr(ledger.sqlite3, "connect", refuse)
        ledger.mirror_text(tmp_path)
