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
            assert db.execute("SELECT value FROM meta WHERE key = 'schema'").fetchone() == ("2",)
            assert db.execute("SELECT COUNT(*) FROM pointings").fetchone()[0] == 8

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
