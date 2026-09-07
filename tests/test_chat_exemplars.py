"""Sentences a Hebrew speaker wrote, inside the reader's words: private data, public code,
an empty default (targum-internal#218)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from targum.chat import exemplars

FIXTURE = Path(__file__).parent / "fixtures" / "exemplars.jsonl"


def test_no_file_means_no_exemplars_and_no_block(monkeypatch: Any, tmp_path: Path) -> None:
    monkeypatch.setenv("TARGUM_EXEMPLARS", str(tmp_path / "missing.jsonl"))
    assert exemplars.pool_path() is None
    assert exemplars.load() == []
    assert exemplars.block([]) == ""
    assert exemplars.pick([], {"בוקר"}) == []


def test_the_pool_is_read_and_a_row_without_its_lemmas_is_not_yet_in_it(
    monkeypatch: Any,
) -> None:
    monkeypatch.setenv("TARGUM_EXEMPLARS", str(FIXTURE))
    assert exemplars.pool_path() == FIXTURE
    pool = exemplars.load()
    assert [row.id for row in pool] == [329714, 329718, 1000001, 1000002, 1000003], (
        "the row still waiting for its tranche is not retrievable"
    )
    morning = pool[0]
    assert morning.original and morning.by == "YURY0608" and morning.english == "Good morning."
    assert morning.lemmas == {"בוקר", "טוב"}
    tom = next(row for row in pool if row.id == 1000001)
    assert "טום" not in tom.lemmas, "a name is not vocabulary, on the ledger or here"
    assert tom.lemmas == {"קנה", "לחם", "שוק"}
    assert "tatoeba.org/sentences/show/329714" in morning.credit and "YURY0608" in morning.credit


def test_only_sentences_inside_the_readers_words_are_picked() -> None:
    pool = exemplars.load(FIXTURE)
    allowed = {"בוקר", "טוב", "מה", "את", "עושה", "קנה", "לחם"}
    picked = exemplars.pick(pool, allowed)
    assert {row.id for row in picked} == {329714, 329718}, (
        "the market sentence needs שוק, the storm needs a storm, and a bare 'yes' teaches nothing"
    )
    assert exemplars.pick(pool, {"שלום"}) == []


def test_a_saved_word_claims_first_place_and_originals_come_before_translations() -> None:
    pool = exemplars.load(FIXTURE)
    allowed = {"בוקר", "טוב", "מה", "את", "עושה", "קנה", "לחם", "שוק", "סערה", "מנע", "מן", "יצא"}
    picked = exemplars.pick(pool, allowed, lately=["סערה"], count=3)
    assert picked[0].id == 1000002, "the sentence carrying the saved word leads"
    assert [row.original for row in picked[1:]] == [True, True], "originals before translations"
    for seed in (1, 2, 3):
        again = exemplars.pick(pool, allowed, lately=["סערה"], count=3, seed=seed)
        assert again == exemplars.pick(pool, allowed, lately=["סערה"], count=3, seed=seed)
        assert again[0].id == 1000002
    orders = {tuple(row.id for row in exemplars.pick(pool, allowed, seed=s)) for s in range(12)}
    assert len(orders) > 1, "another seed, another draw"


def test_the_block_says_what_the_sentences_are_for_and_carries_the_english() -> None:
    pool = exemplars.load(FIXTURE)
    text = exemplars.block(exemplars.pick(pool, {"בוקר", "טוב"}))
    assert text.startswith("Sentences a Hebrew speaker wrote, inside the reader's words (1)")
    assert "not lines to repeat" in text and "unpointed" in text
    assert "בוקר טוב. = Good morning." in text


def test_a_turns_seed_is_stable_and_moves_with_the_turn() -> None:
    assert exemplars.turn_seed("c1", 1) == exemplars.turn_seed("c1", 1)
    assert exemplars.turn_seed("c1", 1) != exemplars.turn_seed("c1", 2)
    assert exemplars.turn_seed("c1", 1) != exemplars.turn_seed("c2", 1)
