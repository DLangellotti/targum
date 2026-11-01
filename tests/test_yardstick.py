"""The yardsticks and the coverage measured on them (targum-internal#579, for #575).

Every row is synthetic: placeholder lemmas made of Hebrew letters, no sentence of any
text, no reader. The snapshot files go to a temporary directory, never the real one.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from targum import level
from targum.cli import app
from targum.tables import yardstick
from targum.tables.store import Contribution, Store

LETTERS = "אבגדהוזחטיכלמנסעפצקרשת"


def _lemma(index: int) -> str:
    """A distinct made-up lemma for each index, three letters long."""
    a, rest = divmod(index, len(LETTERS) ** 2)
    b, c = divmod(rest, len(LETTERS))
    return LETTERS[a % len(LETTERS)] + LETTERS[b] + LETTERS[c]


def _counts(lemmas: int, *, scale: int = 1000) -> dict[tuple[str, str], int]:
    """A Zipf-shaped register: lemma i counted scale*… / (i+1) times, as nouns, plus a
    function word and a name that are counted but never weighed."""
    counts = {(_lemma(i), "NOUN"): max(1, scale * 100 // (i + 1)) for i in range(lemmas)}
    counts[("של", "ADP")] = scale * 500
    counts[("<NAME>", "PROPN")] = scale * 300
    return counts


def _store(tmp_path: Path, register: str = "news", lemmas: int = 400, scale: int = 1000) -> Store:
    store = Store(tmp_path / "corpus.db")
    store.write(
        Contribution(
            table="words",
            register=register,
            unit=f"unit-{register}-{scale}",
            source=f"synthetic:{register}",
            licence="CC0",
            tool="test/1",
            rule="words/1",
        ),
        _counts(lemmas, scale=scale),
    )
    return store


NOW = datetime(2026, 10, 30, 12, tzinfo=UTC)


def test_a_snapshot_is_the_registers_content_lemmas_weighted_to_one(tmp_path: Path) -> None:
    store = _store(tmp_path)
    done = yardstick.write(store, "news", tmp_path / "tables", now=NOW)
    assert done.outcome == "written" and done.version == 1
    assert done.file == tmp_path / "tables" / "yardstick-news-v1.json"
    raw = json.loads(done.file.read_text(encoding="utf-8"))
    assert raw["register"] == "news" and raw["version"] == 1 and raw["rule"] == yardstick.RULE
    assert abs(sum(raw["weights"].values()) - 1) < 1e-9
    assert "של" not in raw["weights"], "a function word is counted, never weighed"
    assert "<NAME>" not in raw["weights"], "and a name is no word to know"
    assert raw["provenance"][0]["licence"] == "CC0"
    assert raw["provenance"][0]["sources"] == ["synthetic:news"]


def test_known_top_lemmas_give_their_share_and_a_function_word_moves_nothing(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    yardstick.write(store, "news", tmp_path / "tables", now=NOW)
    stick = yardstick.load("news", tmp_path / "tables")
    assert stick is not None
    counts = {key: n for (key, pos), n in _counts(400).items() if pos == "NOUN"}
    total = sum(counts.values())
    top = [_lemma(i) for i in range(10)]
    expected = sum(counts[one] for one in top) / total
    share = level.coverage_on("news", top, tmp_path / "tables")
    assert share == pytest.approx(expected)
    assert level.coverage_on("news", [*top, "של"], tmp_path / "tables") == share
    assert level.coverage_on("news", [], tmp_path / "tables") == 0
    everything = [_lemma(i) for i in range(400)]
    assert level.coverage_on("news", everything, tmp_path / "tables") == pytest.approx(1)


def test_a_pointed_headword_meets_the_lists_bare_lemma(tmp_path: Path) -> None:
    store = _store(tmp_path)
    yardstick.write(store, "news", tmp_path / "tables", now=NOW)
    pointed = _lemma(0)[0] + "ָ" + _lemma(0)[1:]
    assert level.coverage_on("news", [pointed], tmp_path / "tables") == level.coverage_on(
        "news", [_lemma(0)], tmp_path / "tables"
    )


def test_a_register_with_no_snapshot_is_absent_not_nought(tmp_path: Path) -> None:
    store = _store(tmp_path)
    yardstick.write_all(store, tmp_path / "tables", now=NOW)
    assert level.coverage_on("bible", [_lemma(0)], tmp_path / "tables") is None
    assert level.coverage_days("bible", [], began=0, where=tmp_path / "tables") is None
    assert level.coverage_on("scenes", [_lemma(0)], tmp_path / "tables") is None


def test_a_register_under_the_floor_gets_no_list(tmp_path: Path) -> None:
    store = _store(tmp_path, lemmas=5, scale=1)
    done = yardstick.write(store, "news", tmp_path / "tables", now=NOW)
    assert done.outcome == "short" and done.file is None
    assert yardstick.versions("news", tmp_path / "tables") == []


def test_scenes_and_the_weekly_are_never_a_yardstick(tmp_path: Path) -> None:
    store = _store(tmp_path, register="scenes")
    _store(tmp_path, register="weekly")
    done = yardstick.write_all(store, tmp_path / "tables", now=NOW)
    assert {one.register for one in done} == {
        "news",
        "bible",
        "literature",
        "conversation",
        "imports",
    }
    assert all(one.outcome == "short" for one in done), "the five are empty here"


def test_what_learners_bring_is_offered_once_its_pool_crosses_the_floor(tmp_path: Path) -> None:
    """design.md §12, "What learners bring is counted in the tables, never kept"
    (2026-11-01): the imports pool gets a list, and so a place in the picker, by the same
    50,000-word floor as any register; every row of it already stands on ten readers."""
    from targum.tables import imports

    store = Store(tmp_path / "corpus.db")
    where = tmp_path / "tables"
    made = [imports._contribution("words")]
    store.replace_pool(made, {"words": _counts(20, scale=10)})
    assert yardstick.write(store, "imports", where, now=NOW).outcome == "short"
    assert yardstick.load("imports", where) is None, "absent from the picker, never 0%"
    store.replace_pool(made, {"words": _counts(400)})
    assert yardstick.write(store, "imports", where, now=NOW).outcome == "written"
    stick = yardstick.load("imports", where)
    assert stick is not None and "של" not in stick.weights


def test_a_list_stands_until_the_month_turns(tmp_path: Path) -> None:
    store = _store(tmp_path)
    where = tmp_path / "tables"
    assert yardstick.write(store, "news", where, now=NOW).outcome == "written"
    # More counts arrive the same month: the list a reader is measured on stays put.
    _store(tmp_path, scale=2000)
    later = datetime(2026, 10, 31, 2, tzinfo=UTC)
    assert yardstick.write(store, "news", where, now=later).outcome == "held"
    turned = datetime(2026, 11, 1, 2, 30, tzinfo=UTC)
    done = yardstick.write(store, "news", where, now=turned)
    assert done.outcome == "written" and done.version == 2
    assert yardstick.load("news", where).version == 2  # type: ignore[union-attr]
    # Nothing new by December: the same list is never written twice.
    december = datetime(2026, 12, 1, 2, 30, tzinfo=UTC)
    assert yardstick.write(store, "news", where, now=december).outcome == "unchanged"
    assert [v for v, _ in yardstick.versions("news", where)] == [1, 2]


def test_force_writes_now(tmp_path: Path) -> None:
    store = _store(tmp_path)
    where = tmp_path / "tables"
    yardstick.write(store, "news", where, now=NOW)
    _store(tmp_path, scale=3000)
    assert yardstick.write(store, "news", where, force=True, now=NOW).outcome == "written"


DAY = 86_400_000
BEGAN = int(datetime(2026, 10, 1, tzinfo=UTC).timestamp() * 1000)


def test_history_is_base_plus_gains_and_recomputes_to_the_same_numbers(tmp_path: Path) -> None:
    store = _store(tmp_path)
    where = tmp_path / "tables"
    yardstick.write(store, "news", where, now=NOW)
    dated: list[tuple[str, int | None]] = [(_lemma(i), None) for i in range(5)]
    dated += [(_lemma(5), BEGAN + 2 * DAY), (_lemma(6), BEGAN + 2 * DAY + 5)]
    dated += [(_lemma(7), BEGAN + 9 * DAY), ("של", BEGAN + 9 * DAY)]
    got = level.coverage_days("news", dated, began=BEGAN, where=where)
    assert got is not None
    assert got["base"] == pytest.approx(
        level.coverage_on("news", [_lemma(i) for i in range(5)], where)
    )
    assert [day["day"] for day in got["days"]] == ["2026-10-03", "2026-10-10"]
    # Each day's point is the share of the words known by then, measured afresh.
    by_then = got["base"] + got["days"][0]["gain"]
    assert by_then == pytest.approx(level.coverage_on("news", [_lemma(i) for i in range(7)], where))
    assert got["share"] == pytest.approx(by_then + got["days"][1]["gain"])
    assert got["share"] == pytest.approx(
        level.coverage_on("news", [one for one, _ in dated], where)
    )
    again = level.coverage_days("news", list(reversed(dated)), began=BEGAN, where=where)
    assert again == got, "the same snapshot gives the same points"


def test_a_word_known_before_the_record_began_is_in_the_base(tmp_path: Path) -> None:
    store = _store(tmp_path)
    where = tmp_path / "tables"
    yardstick.write(store, "news", where, now=NOW)
    got = level.coverage_days("news", [(_lemma(0), BEGAN - DAY)], began=BEGAN, where=where)
    assert got is not None and got["days"] == [] and got["base"] == got["share"] > 0


def test_the_snapshot_command_writes_and_reports(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = _store(tmp_path)
    monkeypatch.setenv("TARGUM_LEDGER", str(store.file))
    result = CliRunner().invoke(app, ["tables", "snapshot", "--out", str(tmp_path / "out")])
    assert result.exit_code == 0, result.output
    assert "news: wrote v1" in result.output
    assert "bible: not yet" in result.output
    assert (tmp_path / "out" / "yardstick-news-v1.json").is_file()


def test_the_directory_follows_the_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TARGUM_TABLES_DIR", str(tmp_path / "here"))
    assert yardstick.directory() == tmp_path / "here"


def test_the_account_gives_each_known_word_with_its_date(tmp_path: Path) -> None:
    from targum.accounts import Store as Accounts

    store = Accounts(tmp_path / "db")
    person, _ = store.finish_sign_in(store.start_sign_in("r@example.com"))  # type: ignore[misc]
    began = store.began()

    def word(lemma: str, status: int, seen: int, band: str = "") -> dict[str, object]:
        return {
            "language": "he",
            "lemma": lemma,
            "status": status,
            "at": seen,
            "seen": seen,
            "band": band,
        }

    store.push(
        person,
        {
            "words": [
                word("ים", 9, began - DAY),
                word("ספר", 9, began + 10),
                word("בית", 2, began + 20),
                word("משה", 9, began + 30, band="name"),
            ]
        },
    )
    assert sorted(store.known_dated(person.id, "he")) == sorted([("ים", None), ("ספר", began + 10)])
    assert store.known_dated(None, "he") == []


def _pool(store: Store, counts: dict[tuple[str, str], int]) -> None:
    from targum.tables import imports

    store.replace_pool([imports._contribution("words")], {"words": counts})


def test_what_learners_bring_is_blended_into_conversation_and_news_past_its_floor(
    tmp_path: Path,
) -> None:
    """David, 2026-11-01: past 200,000 content words the pool is mixed into conversation
    and news, by its share of the two together, and never more than half of either."""
    store = _store(tmp_path, register="news")
    _store(tmp_path, register="literature")
    alone = yardstick.build(store, "news")
    assert alone is not None and "blend" not in alone

    # A pool under the floor changes nothing, not even the digest.
    _pool(store, {("פול", "NOUN"): yardstick.BLEND_FLOOR - 1})
    under = yardstick.build(store, "news")
    assert under is not None and under["digest"] == alone["digest"]
    assert "פול" not in under["weights"]

    # Past it, the pool's words come into the list at its share, capped at half.
    _pool(store, {("פול", "NOUN"): yardstick.BLEND_FLOOR * 100})
    blended = yardstick.build(store, "news")
    assert blended is not None
    assert blended["blend"]["imports_share"] == yardstick.BLEND_CAP
    assert blended["weights"]["פול"] == pytest.approx(0.5)
    assert sum(blended["weights"].values()) == pytest.approx(1.0)
    assert blended["digest"] != alone["digest"]
    assert any(row["tool"].startswith("imports/") for row in blended["provenance"])

    # Literature and the Bible are never blended.
    literature = yardstick.build(store, "literature")
    assert literature is not None and "פול" not in literature["weights"]
    assert "blend" not in literature


def test_a_small_pool_is_blended_by_its_size() -> None:
    assert yardstick.blend_share(1_000_000, yardstick.BLEND_FLOOR - 1) == 0.0
    assert yardstick.blend_share(800_000, 200_000) == pytest.approx(0.2)
    assert yardstick.blend_share(100_000, 900_000) == yardstick.BLEND_CAP
    assert yardstick.blend_share(0, 900_000) == 0.0
