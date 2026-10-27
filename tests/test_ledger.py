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
from targum.models import Annotation, Segment, Token, Translation, Vocalization
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
            assert db.execute("SELECT value FROM meta WHERE key = 'schema'").fetchone() == (
                str(ledger.LEDGER_SCHEMA),
            )

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
        (tmp_path / "out" / "shared").mkdir(parents=True)  # what makes it a library
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

    def test_a_held_lock_costs_a_build_at_most_the_short_timeout(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """qa-claude on #943: another process holding the write lock made a reader's
        build wait the full 30 s sqlite timeout before its vowels."""
        import time

        file = tmp_path / "corpus.db"
        monkeypatch.setenv(ledger.ENV, str(file))
        monkeypatch.setattr(ledger, "_licence_of", lambda _folder, _source: "Public Domain")
        monkeypatch.setattr(ledger, "MIRROR_TIMEOUT", 0.5)
        ledger.Ledger(file).record_text(ledger.Text("b" * 64, "gutenberg:2", "Public Domain"))
        folder = tmp_path / "p1" / "text-he"
        folder.mkdir(parents=True)
        (folder / "document.json").write_text(
            json.dumps({"content_hash": "a" * 64, "source": "gutenberg:1"}), encoding="utf-8"
        )
        holder = sqlite3.connect(file, isolation_level=None)
        try:
            holder.execute("BEGIN IMMEDIATE")
            began = time.monotonic()
            ledger.mirror_text(folder)
            waited = time.monotonic() - began
        finally:
            holder.execute("ROLLBACK")
            holder.close()
        assert waited < 5, f"waited {waited:.1f} s for the lock"
        assert ledger.Ledger(file).text("a" * 64) is None, "gone on without the row"
        ledger.mirror_text(folder)
        assert ledger.Ledger(file).text("a" * 64) is not None


def _rendering(document_hash: str = "doc123", **change: Any) -> dict[str, Any]:
    # Segments out of document order, and coarse and confidence fields only some carry.
    value = Translation(
        name="English (Claude)",
        document_hash=document_hash,
        source_language="he",
        target_language="en",
        provider="claude",
        model="claude-test",
        segments={"s2": "Father came.", "s0": "Hello.", "s1": "Mother came."},
        coarse=["s1"],
        confidence={"s1": 0.5, "s2": 0.9},
    ).model_dump(mode="json")
    return {**value, **change}


class TestTranslations:
    """Slice 4 (2026-10-27): renderings and their aligned pairs, read from the files a
    build already wrote. Nothing is translated to fill them."""

    def test_a_rendering_comes_back_as_the_same_bytes(self, tmp_path: Path) -> None:
        book = ledger.Ledger(tmp_path / "corpus.db")
        book.record(
            "translations",
            "doc123:claude.natural.en",
            _rendering(),
            licence="Public Domain",
            sources={"s0": "שלום.", "s1": "אמא באה."},
        )
        back = book.get("translations", "doc123:claude.natural.en")
        assert json.dumps(back, ensure_ascii=False) == json.dumps(_rendering(), ensure_ascii=False)
        with sqlite3.connect(book.file) as db:
            pairs = db.execute(
                "SELECT segment_id, source, target, confidence, coarse FROM pairs ORDER BY ord"
            ).fetchall()
        assert pairs == [
            ("s2", None, "Father came.", 0.9, 0),
            ("s0", "שלום.", "Hello.", None, 0),
            ("s1", "אמא באה.", "Mother came.", 0.5, 1),
        ]

    def test_its_bits_are_its_text_s_and_its_own_licence_s(self, tmp_path: Path) -> None:
        book = ledger.Ledger(tmp_path / "corpus.db")
        book.record("translations", "doc123:mine", _rendering(), licence="Public Domain")
        book.record(
            "translations", "doc123:theirs", _rendering(kind="aligned"), licence="CC BY-NC 4.0"
        )
        assert _bits(book.file, "translations") == [(0, 0), (0, 0)], "no text row yet"
        book.record_text(ledger.Text("doc123", "gutenberg:1", "Public Domain"))
        assert _bits(book.file, "translations") == [(0, 1), (0, 1)], "machine: research only"
        book.record(
            "translations", "doc123:ours", _rendering(kind="authored"), licence="Public Domain"
        )
        assert _bits(book.file, "translations")[-1] == (1, 1), "authored follows its licence"
        book.record_text(ledger.Text("doc123", "upload.pdf", "Public Domain", frozenset({"p4"})))
        assert set(_bits(book.file, "translations")) == {(0, 0)}, "a reader's text: private"

    def test_a_corrected_licence_on_the_same_rendering_keeps_the_old_as_history(
        self, tmp_path: Path
    ) -> None:
        book = ledger.Ledger(tmp_path / "corpus.db")
        book.record("translations", "k", _rendering(kind="aligned"), licence="")
        book.record("translations", "k", _rendering(kind="aligned"), licence="")
        book.record("translations", "k", _rendering(kind="aligned"), licence="CC BY 4.0")
        assert len(book.history("translations", "k")) == 2
        with sqlite3.connect(book.file) as db:
            held = db.execute(
                "SELECT licence, own_exportable FROM translations WHERE superseded_at IS NULL"
            ).fetchall()
        assert held == [("CC BY 4.0", 1)]

    def test_a_departed_reader_s_renderings_go_with_their_text(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setenv(ledger.ENV, str(tmp_path / "corpus.db"))
        book = ledger.Ledger(tmp_path / "corpus.db")
        book.record("translations", "k", _rendering("a" * 64), licence="")
        book.record("translations", "k", _rendering("a" * 64, name="again"), licence="")
        ledger.forget({"a" * 64})
        with sqlite3.connect(book.file) as db:
            assert db.execute("SELECT COUNT(*) FROM translations").fetchone()[0] == 0
            assert db.execute("SELECT COUNT(*) FROM pairs").fetchone()[0] == 0

    @staticmethod
    def _folder(folder: Path, source: str, *renderings: tuple[str, dict[str, Any]]) -> None:
        (folder / "translations").mkdir(parents=True)
        document = {"source": source, "language": "he", "blocks": [], "content_hash": "doc123"}
        (folder / "document.json").write_text(json.dumps(document), encoding="utf-8")
        segments = {
            "document_hash": "doc123",
            "language": "he",
            "segmenter": "fake",
            "segments": [{"id": "s0", "text": "שלום."}],
        }
        (folder / "segments.json").write_text(json.dumps(segments), encoding="utf-8")
        for stem, value in renderings:
            (folder / "translations" / f"{stem}.json").write_text(
                json.dumps(value, ensure_ascii=False), encoding="utf-8"
            )

    def test_backfill_reads_the_files_and_buys_nothing(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        from targum import catalogue

        # No network at all: the suite refuses any connection, so a backfill that tried to
        # buy a translation would fail here rather than spend.
        monkeypatch.setattr(ledger, "_licence_of", lambda _folder, _source: "Public Domain")
        rendering = catalogue.Rendering(
            name="JPS", source="sefaria:en:Genesis", licence="CC BY-NC 4.0"
        )
        entry = type("Entry", (), {"translations": [rendering]})()
        monkeypatch.setattr(catalogue, "matching", lambda _source: entry)
        out = tmp_path / "out"
        self._folder(
            out / "shared" / "genesis",
            "sefaria:Genesis",
            ("claude.natural.en", _rendering()),
            ("aligned.jps.en", _rendering(kind="aligned", name="JPS")),
        )
        book = ledger.Ledger(tmp_path / "corpus.db")
        assert ledger.backfill_texts(book, out) == (1, 0)
        assert ledger.backfill_translations(book, out) == (2, 0)
        assert ledger.backfill_translations(book, out) == (2, 0), "again: the same rows"
        with sqlite3.connect(book.file) as db:
            rows = db.execute(
                "SELECT cache_key, licence, exportable, research FROM translations ORDER BY id"
            ).fetchall()
            assert db.execute("SELECT COUNT(*) FROM translations").fetchone()[0] == 2
            source = db.execute("SELECT source FROM pairs WHERE segment_id = 's0'").fetchone()
        assert rows == [
            ("doc123:aligned.jps.en", "CC BY-NC 4.0", 0, 1),
            ("doc123:claude.natural.en", "Public Domain", 0, 1),
        ]
        assert source == ("שלום.",)

    def test_a_published_rendering_the_catalogue_does_not_know_exports_nowhere(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        from targum import catalogue

        monkeypatch.setattr(catalogue, "matching", lambda _source: None)
        folder = tmp_path / "out" / "shared" / "x"
        self._folder(folder, "https://x.example/a", ("aligned.x.en", _rendering(kind="aligned")))
        book = ledger.Ledger(tmp_path / "corpus.db")
        assert ledger.record_translations(book, folder) == (1, 0)
        with sqlite3.connect(book.file) as db:
            assert db.execute("SELECT licence FROM translations").fetchone() == ("",)

    def test_a_build_records_its_renderings(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        source: Path,
        fake_segmenter: object,
    ) -> None:
        monkeypatch.setenv("TARGUM_CACHE_DIR", str(tmp_path / "cache"))
        monkeypatch.setenv(ledger.ENV, str(tmp_path / "corpus.db"))
        monkeypatch.setattr(ledger, "_licence_of", lambda _folder, _source: "Public Domain")
        _build(source, tmp_path / "out" / "shared" / "text-he", fake_segmenter, Named("fake/1"))
        folder = tmp_path / "out" / "shared" / "text-he"
        stems = sorted(one.stem for one in (folder / "translations").glob("*.json"))
        assert stems, "the build wrote a translation"
        document = json.loads((folder / "document.json").read_text(encoding="utf-8"))
        book = ledger.Ledger(tmp_path / "corpus.db")
        for stem in stems:
            on_disk = json.loads((folder / "translations" / f"{stem}.json").read_text("utf-8"))
            held = book.get("translations", f"{document['content_hash']}:{stem}")
            assert held == on_disk
        assert set(_bits(book.file, "translations")) == {(0, 1)}, "machine: research only"

    def test_the_command_records_the_library(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        from typer.testing import CliRunner

        from targum.cli import app

        monkeypatch.setenv(ledger.ENV, str(tmp_path / "corpus.db"))
        monkeypatch.setattr(ledger, "_licence_of", lambda _folder, _source: "Public Domain")
        self._folder(
            tmp_path / "out" / "p2" / "x", "upload.pdf", ("claude.natural.en", _rendering())
        )
        ledger.Ledger(tmp_path / "corpus.db").record_text(
            ledger.Text("doc123", "upload.pdf", "", frozenset({"p2"}))
        )
        result = CliRunner().invoke(
            app, ["cache", "ledger-translations", "--out", str(tmp_path / "out")]
        )
        assert result.exit_code == 0, result.output
        assert "Recorded 1 translations" in result.output
        result = CliRunner().invoke(app, ["cache", "ledger-translations"], env={ledger.ENV: ""})
        assert result.exit_code != 0 and "ledger is off" in result.output

    def test_a_chapter_bought_later_is_recorded(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        source: Path,
        fake_segmenter: object,
    ) -> None:
        """The server's Translate buys a chapter through `Build.translate(only=…)`, after
        the build's own pass; that path records the rendering too."""
        from targum.models import Document, SegmentedDocument, read_artifact
        from targum.pipeline import Build

        monkeypatch.setenv("TARGUM_CACHE_DIR", str(tmp_path / "cache"))
        folder = tmp_path / "out" / "shared" / "text-he"
        _build(source, folder, fake_segmenter, Named("fake/1"))
        monkeypatch.setenv(ledger.ENV, str(tmp_path / "corpus.db"))
        segmented = read_artifact(SegmentedDocument, folder / "segments.json")
        document = read_artifact(Document, folder / "document.json")
        assert segmented is not None and document is not None
        builder = Build(str(source), provider_name="null", out=folder, target_language="en")
        builder.out_dir(document)
        builder.translate(segmented, only=segmented.segments[:1])
        with sqlite3.connect(tmp_path / "corpus.db") as db:
            assert db.execute("SELECT COUNT(*) FROM translations").fetchone()[0] >= 1

    def test_a_reader_s_copy_of_a_shelf_text_does_not_overwrite_the_shelf_s(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """qa-claude on #945: the shelf's copy and a reader's partial copy share a key.
        While the text is public only the public folder records; a private text still
        records from its home."""
        monkeypatch.setattr(ledger, "_licence_of", lambda _folder, _source: "Public Domain")
        whole = _rendering()
        part = _rendering(segments={"s0": "Hello."}, coarse=[], confidence={})
        out = tmp_path / "out"
        self._folder(out / "shared" / "x", "gutenberg:1", ("claude.natural.en", whole))
        self._folder(out / "p3" / "x", "gutenberg:1", ("claude.natural.en", part))
        book = ledger.Ledger(tmp_path / "corpus.db")
        ledger.backfill_texts(book, out)
        ledger.backfill_translations(book, out)
        ledger.backfill_translations(book, out)
        assert book.get("translations", "doc123:claude.natural.en") == whole
        assert len(book.history("translations", "doc123:claude.natural.en")) == 1

        alone = tmp_path / "alone"
        self._folder(alone / "p3" / "x", "upload.pdf", ("claude.natural.en", part))
        other = ledger.Ledger(tmp_path / "other.db")
        ledger.backfill_texts(other, alone)
        assert ledger.backfill_translations(other, alone) == (1, 0)
        assert other.get("translations", "doc123:claude.natural.en") == part

    def test_the_glossary_beside_the_renderings_is_not_one(self, tmp_path: Path) -> None:
        folder = tmp_path / "out" / "shared" / "x"
        self._folder(folder, "https://x.example/a", ("claude.natural.en", _rendering()))
        (folder / "translations" / "words.en.json").write_text("{}", encoding="utf-8")
        book = ledger.Ledger(tmp_path / "corpus.db")
        assert ledger.record_translations(book, folder) == (1, 0), "not refused, skipped"


class TestReadThrough:
    """Slice 5 (2026-10-27): `Cache.get` asks the ledger first for a stage
    `TARGUM_LEDGER_READ` names, and only while the cache file exists and the row is at
    least as new as it. Anything else falls through to the file — never to running the
    stage, and never to an answer the cache no longer holds (qa-claude on #946)."""

    KEY = "ab" + "0" * 62

    @staticmethod
    def _on(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Cache:
        monkeypatch.setenv(ledger.ENV, str(tmp_path / "corpus.db"))
        monkeypatch.setenv(ledger.READ_ENV, "vocalize")
        return Cache(tmp_path / "cache")

    @staticmethod
    def _reads_of_the_file(monkeypatch: pytest.MonkeyPatch) -> list[Path]:
        """Every cache file of the `vocalize` stage read as text from here on."""
        read: list[Path] = []
        original = Path.read_text

        def spy(self: Path, *args: Any, **kwargs: Any) -> str:
            if "vocalize" in self.parts and self.suffix == ".json" and "cache" in self.parts:
                read.append(self)
            return original(self, *args, **kwargs)

        monkeypatch.setattr(Path, "read_text", spy)
        return read

    def test_it_is_a_second_flag_and_off_by_default(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        cache = self._on(monkeypatch, tmp_path)
        cache.put("vocalize", self.KEY, POINTED)
        monkeypatch.delenv(ledger.READ_ENV)
        read = self._reads_of_the_file(monkeypatch)
        assert cache.get("vocalize", self.KEY) == POINTED
        assert read, "flag off: the file is read"
        monkeypatch.setenv(ledger.READ_ENV, "vocalize, translate")
        assert ledger.read_stages() == {"vocalize"}, "only a stage the rows give back"
        read.clear()
        assert cache.get("vocalize", self.KEY) == POINTED
        assert not read, "flag on: served from the rows"

    def test_a_put_the_ledger_could_not_take_is_served_from_the_file(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """qa-claude's first: under a held lock the write and the stamp both fail, and
        the ledger still holds the older value. The newer file wins."""
        cache = self._on(monkeypatch, tmp_path)
        cache.put("vocalize", self.KEY, POINTED)
        newer = {**POINTED, "machine": []}

        def locked(*args: Any, **kwargs: Any) -> None:
            raise sqlite3.OperationalError("database is locked")

        monkeypatch.setattr(ledger.Ledger, "record", locked)
        monkeypatch.setattr(ledger.Ledger, "drop", locked)
        cache.put("vocalize", self.KEY, newer)
        assert ledger.Ledger(tmp_path / "corpus.db").get("vocalize", self.KEY) == POINTED
        assert cache.get("vocalize", self.KEY) == newer

    def test_a_dropped_answer_never_comes_back_from_the_ledger(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """qa-claude's second: the ledger's drop fails under a held lock, the file goes."""
        cache = self._on(monkeypatch, tmp_path)
        cache.put("vocalize", self.KEY, POINTED)

        def locked(*args: Any, **kwargs: Any) -> bool:
            raise sqlite3.OperationalError("database is locked")

        monkeypatch.setattr(ledger.Ledger, "drop", locked)
        assert cache.drop("vocalize", self.KEY)
        assert ledger.Ledger(tmp_path / "corpus.db").get("vocalize", self.KEY) == POINTED
        assert cache.get("vocalize", self.KEY) is None

    def test_a_cleared_cache_is_cleared_for_reads_too(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """qa-claude's third: `cache clear` leaves the ledger (it is the corpus, not
        scratch), and a read no longer reaches past the missing file to it."""
        cache = self._on(monkeypatch, tmp_path)
        cache.put("vocalize", self.KEY, POINTED)
        cache.clear()
        assert ledger.Ledger(tmp_path / "corpus.db").get("vocalize", self.KEY) == POINTED
        assert cache.get("vocalize", self.KEY) is None

    def test_whatever_a_ledger_read_raises_reads_the_file(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        cache = self._on(monkeypatch, tmp_path)
        cache.put("vocalize", self.KEY, POINTED)

        def boom(*args: Any, **kwargs: Any) -> None:
            raise RuntimeError("anything at all")

        monkeypatch.setattr(ledger, "_read_row", boom)
        assert cache.get("vocalize", self.KEY) == POINTED
        (tmp_path / "corpus.db").write_bytes(b"this is not a database")
        assert cache.get("vocalize", self.KEY) == POINTED, "a broken ledger: the cache's"

    def test_a_read_opens_the_ledger_read_only(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """A read never migrates or writes, so it never takes the write lock: a ledger an
        older schema left stays exactly as it was."""
        cache = self._on(monkeypatch, tmp_path)
        cache.put("vocalize", self.KEY, POINTED)
        with sqlite3.connect(tmp_path / "corpus.db") as db:
            db.executescript("DROP TABLE texts; UPDATE meta SET value = '2' WHERE key = 'schema';")
        assert cache.get("vocalize", self.KEY) == POINTED
        with sqlite3.connect(tmp_path / "corpus.db") as db:
            assert db.execute("SELECT value FROM meta WHERE key = 'schema'").fetchone() == ("2",)
            assert not db.execute("SELECT 1 FROM sqlite_master WHERE name = 'texts'").fetchone()

    def test_a_held_lock_costs_a_read_at_most_the_short_timeout(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        import time

        cache = self._on(monkeypatch, tmp_path)
        monkeypatch.setattr(ledger, "MIRROR_TIMEOUT", 0.5)
        cache.put("vocalize", self.KEY, POINTED)
        holder = sqlite3.connect(tmp_path / "corpus.db", isolation_level=None)
        try:
            holder.execute("BEGIN EXCLUSIVE")
            began = time.monotonic()
            assert cache.get("vocalize", self.KEY) == POINTED
            waited = time.monotonic() - began
        finally:
            holder.execute("ROLLBACK")
            holder.close()
        assert waited < 5, f"waited {waited:.1f} s"

    def test_a_row_from_before_slice_5_is_compared_by_its_second(self) -> None:
        assert ledger._not_older("2026-10-27T10:00:00+00:00", 1_793_095_200.5)
        assert not ledger._not_older("2026-10-27T10:00:00+00:00", 1_793_095_201.5)
        assert ledger._not_older("2026-10-27T10:00:00.500000+00:00", 1_793_095_200.4)
        assert not ledger._not_older("2026-10-27T10:00:00.500000+00:00", 1_793_095_200.6)

    def test_a_build_served_from_the_ledger_runs_nothing_and_spends_nothing(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        source: Path,
        fake_segmenter: object,
    ) -> None:
        """The vowels come from the rows: the vocalizer is not asked, the cache file is
        not read, and the build's `Usage` counts nothing."""
        from targum.pipeline import Build

        monkeypatch.setenv("TARGUM_CACHE_DIR", str(tmp_path / "cache"))
        self._on(monkeypatch, tmp_path)
        _build(source, tmp_path / "first", fake_segmenter, Named("fake/1"))
        read = self._reads_of_the_file(monkeypatch)
        engine = Named("fake/1")
        result = Build(
            str(source),
            provider_name="null",
            out=tmp_path / "second",
            segmenter=fake_segmenter,  # type: ignore[arg-type]
            target_language="en",
            vocalizer=engine,
        ).run()
        assert engine.asked == 0
        assert not read, "served from the ledger, not the file"
        assert result.spent.calls == 0 and result.spent.input_tokens == 0
        assert result.spent.output_tokens == 0 and not result.spent.by_model
        assert (tmp_path / "second" / "vocalization.json").read_bytes() == (
            tmp_path / "first" / "vocalization.json"
        ).read_bytes()

    def test_with_the_ledger_broken_a_build_reads_the_cache_and_runs_nothing(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        source: Path,
        fake_segmenter: object,
    ) -> None:
        monkeypatch.setenv("TARGUM_CACHE_DIR", str(tmp_path / "cache"))
        monkeypatch.setenv(ledger.READ_ENV, "vocalize")
        _build(source, tmp_path / "first", fake_segmenter, Named("fake/1"))
        (tmp_path / "corpus.db").write_bytes(b"not a database")
        monkeypatch.setenv(ledger.ENV, str(tmp_path / "corpus.db"))
        engine = Named("fake/1")
        _build(source, tmp_path / "second", fake_segmenter, engine)
        assert engine.asked == 0


class TestAnyDepth:
    """The laptop check of 2026-10-27 found the fill one level deep: the parasha sits at
    `parasha/read/<slug>/print` and 604 texts three levels down. A text is any folder
    holding its files; private or public is the top folder's call."""

    @staticmethod
    def _built(folder: Path, document_hash: str, source: str) -> None:
        folder.mkdir(parents=True)
        document = {"source": source, "language": "he", "blocks": [], "content_hash": document_hash}
        (folder / "document.json").write_text(json.dumps(document), encoding="utf-8")

    def test_the_fill_finds_texts_at_any_depth_and_the_top_folder_decides(
        self, tmp_path: Path
    ) -> None:
        out = tmp_path / "out"
        self._built(out / "parasha" / "read" / "noach" / "print", "a" * 64, "parasha:noach")
        self._built(out / "russian" / "globalvoices" / "story", "b" * 64, "https://gv/1")
        self._built(out / "local" / "videos" / "clip", "c" * 64, "https://yt/1")
        self._built(out / "p3" / "local" / "upload", "d" * 64, "upload.pdf")
        self._built(out / "declaration-he", "e" * 64, "declaration.md")
        # A built text's own pages are not walked for texts.
        self._built(out / "library" / "ruth" / "reader" / "stray", "f" * 64, "stray")
        book = ledger.Ledger(tmp_path / "corpus.db")
        assert ledger.backfill_texts(book, out, licence_of=lambda _f, _s: "Public Domain") == (
            5,
            0,
        )
        homes = {c: book.text(c * 64).homes for c in "abcde"}  # type: ignore[union-attr]
        assert homes == {
            "a": frozenset(),
            "b": frozenset(),
            "c": {"local"},
            "d": {"p3"},
            "e": frozenset(),
        }, "p3/local is p3's, local/videos is local's"
        assert book.text("f" * 64) is None

    def test_a_text_found_at_two_depths_is_one_text(self, tmp_path: Path) -> None:
        out = tmp_path / "out"
        self._built(out / "shared" / "noach", "a" * 64, "parasha:noach")
        self._built(out / "parasha" / "read" / "noach" / "print", "a" * 64, "parasha:noach")
        self._built(out / "p1" / "deep" / "noach", "a" * 64, "parasha:noach")
        book = ledger.Ledger(tmp_path / "corpus.db")
        assert ledger.backfill_texts(book, out, licence_of=lambda _f, _s: "Public Domain") == (
            1,
            0,
        )
        assert book.text("a" * 64).homes == frozenset()  # type: ignore[union-attr]

    def test_a_link_back_up_the_tree_does_not_loop(self, tmp_path: Path) -> None:
        out = tmp_path / "out"
        self._built(out / "russian" / "story", "a" * 64, "https://gv/1")
        (out / "russian" / "loop").symlink_to(out, target_is_directory=True)
        (out / "linked").symlink_to(out / "russian" / "story", target_is_directory=True)
        assert ledger.text_folders(out) == [out / "russian" / "story"]

    def test_a_build_in_a_nested_home_is_private_to_the_top_home(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setenv(ledger.ENV, str(tmp_path / "corpus.db"))
        monkeypatch.setattr(ledger, "_licence_of", lambda _folder, _source: "Public Domain")
        out = tmp_path / "out"
        (out / "weekly").mkdir(parents=True)  # what makes it a library
        cases = {
            "a": (out / "local" / "videos" / "clip", {"local"}),
            "b": (out / "p3" / "local" / "upload", {"p3"}),
            "c": (out / "parasha" / "read" / "noach" / "print", set()),
            # Deeper than four levels, and a home's name lower down in a public folder:
            # the top folder decides both (qa-claude on #949).
            "d": (out / "p3" / "a" / "b" / "c" / "d" / "x", {"p3"}),
            "e": (out / "demos" / "olim" / "shelf" / "p1" / "x", set()),
        }
        for name, (folder, _homes) in cases.items():
            self._built(folder, name * 64, f"source-{name}")
            ledger.mirror_text(folder)
        book = ledger.Ledger(tmp_path / "corpus.db")
        for name, (_folder, homes) in cases.items():
            assert book.text(name * 64).homes == homes, name  # type: ignore[union-attr]

    def test_an_old_weekly_issue_is_our_own_writing(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """David, 2026-10-27: the weekly is licence `targum`, in the catalogue or not."""
        from targum import catalogue

        monkeypatch.setattr(catalogue, "matching", lambda _source: None)
        assert ledger._licence_of(tmp_path, "weekly:2026-w35-aleph") == "targum"
        assert ledger._licence_of(tmp_path, "https://example.com/a") == ""

    def test_a_departed_reader_s_nested_texts_are_forgotten_too(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        from targum.accounts import Store
        from targum.serve import Library

        monkeypatch.setenv(ledger.ENV, str(tmp_path / "corpus.db"))
        store = Store(tmp_path / "targum.db")
        person, _ = store.finish_sign_in(store.start_sign_in("leaving@example.com"))  # type: ignore[misc]
        library = Library(tmp_path / "out", store=store)
        home = library.home(person)
        clip = home / "videos" / "clip"
        clip.mkdir(parents=True)
        (clip / "vocalization.json").write_text(
            json.dumps({**POINTED, "document_hash": "a" * 64}, indent=2), encoding="utf-8"
        )
        book = ledger.Ledger(tmp_path / "corpus.db")
        book.record("vocalize", "k-a", {**POINTED, "document_hash": "a" * 64})
        with store.write() as db:
            db.execute("UPDATE person SET leaving = 1 WHERE id = ?", (person.id,))
        assert library.purge_departed() == [person.id]
        assert book.history("vocalize", "k-a") == []

    def test_a_text_the_shelf_holds_twice_keeps_one_rendering_and_no_churn(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Found re-running the laptop fill: `shared/<x>` and `parasha/read/<x>/print`
        hold one text, and their files under one key differ. Each fill added both to the
        history again. Now the fullest is recorded, once."""
        monkeypatch.setattr(ledger, "_licence_of", lambda _folder, _source: "Public Domain")
        out = tmp_path / "out"
        whole = _rendering()
        part = _rendering(segments={"s0": "Hello."}, coarse=[], confidence={})
        for folder, value in (
            (out / "parasha" / "read" / "x" / "print", whole),
            (out / "shared" / "x", part),
        ):
            TestTranslations._folder(folder, "parasha:x", ("claude.natural.en", value))
        book = ledger.Ledger(tmp_path / "corpus.db")
        ledger.backfill_texts(book, out)
        for _ in range(3):
            ledger.backfill_translations(book, out)
        assert book.get("translations", "doc123:claude.natural.en") == whole
        assert len(book.history("translations", "doc123:claude.natural.en")) == 1

    def test_a_newer_write_replaces_a_fuller_row_outside_a_fill(self, tmp_path: Path) -> None:
        """Fullest-wins is only a fill's choice among copies: a build that writes a
        re-translation with fewer sentences replaces the row (qa-claude on #949)."""
        folder = tmp_path / "out" / "shared" / "x"
        shorter = _rendering(segments={"s0": "Hi."}, coarse=[], confidence={})
        TestTranslations._folder(folder, "https://x.example/a", ("claude.natural.en", shorter))
        book = ledger.Ledger(tmp_path / "corpus.db")
        book.record("translations", "doc123:claude.natural.en", _rendering(), licence="")
        ledger.record_translations(book, folder)
        assert book.get("translations", "doc123:claude.natural.en") == shorter

    def test_a_public_text_s_rendering_is_chosen_among_public_folders_only(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """qa-claude on #949: a home's fuller copy of a shelf text was chosen, refused
        there, and the shelf's own copy was never recorded."""
        monkeypatch.setattr(ledger, "_licence_of", lambda _folder, _source: "Public Domain")
        out = tmp_path / "out"
        whole = _rendering()
        part = _rendering(segments={"s0": "Hello."}, coarse=[], confidence={})
        TestTranslations._folder(out / "shared" / "x", "gutenberg:1", ("claude.natural.en", part))
        TestTranslations._folder(
            out / "p3" / "local" / "x", "gutenberg:1", ("claude.natural.en", whole)
        )
        book = ledger.Ledger(tmp_path / "corpus.db")
        ledger.backfill_texts(book, out)
        ledger.backfill_translations(book, out)
        assert book.get("translations", "doc123:claude.natural.en") == part

    def test_a_document_linked_from_outside_the_library_is_not_read(self, tmp_path: Path) -> None:
        outside = tmp_path / "elsewhere"
        self._built(outside, "a" * 64, "secret.md")
        out = tmp_path / "out"
        (out / "shared" / "x").mkdir(parents=True)
        (out / "shared" / "x" / "document.json").symlink_to(outside / "document.json")
        book = ledger.Ledger(tmp_path / "corpus.db")
        assert ledger.backfill_texts(book, out, licence_of=lambda _f, _s: "Public Domain") == (
            0,
            0,
        )
