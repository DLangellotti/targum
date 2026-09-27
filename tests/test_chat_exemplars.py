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


def test_a_saved_word_the_reader_does_not_know_yet_is_still_brought_back() -> None:
    """A word saved last week is on the ledger as learning, not known, so the known
    list does not carry it — and a sentence using it is the bring-back the research
    asks for. Found on the first full pool (2026-09-07): with לחם saved and 14,360
    sentences inside a 300-word ledger, not one carried bread."""
    pool = exemplars.load(FIXTURE)
    allowed = {"בוקר", "טוב", "קנה", "שוק"}
    assert exemplars.pick(pool, allowed) == [pool[0]], "the market sentence needs לחם"
    picked = exemplars.pick(pool, allowed, lately=["לחם"])
    assert picked[0].id == 1000001, "saved, so inside the reader's words, and first"


# -- the gloss follows the reader's language (targum-internal#286, item 5) --------------


def _said(hebrew: str, english: str, russian: str = "") -> exemplars.Exemplar:
    return exemplars.Exemplar(
        id=1,
        hebrew=hebrew,
        english=english,
        russian=russian,
        lemmas=frozenset({hebrew.split()[0]}),
        by="anna",
        russian_by="dmitri" if russian else "",
    )


def test_an_exemplar_is_glossed_in_the_language_the_reader_reads() -> None:
    """The model is being shown what the reader will see. A block glossed in English
    while the conversation glosses in Russian was teaching it the wrong shape of answer,
    in the one place the prompt claims to be showing it the right one."""
    both = _said("שלום לך", "hello to you", "привет тебе")
    only_english = _said("בוקר טוב", "good morning")

    assert both.said_in("ru") == "привет тебе"
    assert both.said_in("ru-RU") == "привет тебе", "a regional tag is the language"
    assert both.said_in("en") == "hello to you"
    # Most rows have no Russian — 6,682 of 165,454 — and the English there is never
    # wrong, only foreign, which is the fallback every other string on the shelf makes.
    assert only_english.said_in("ru") == "good morning"

    russian = exemplars.block([both, only_english], "ru")
    assert "שלום לך = привет тебе" in russian
    assert "בוקר טוב = good morning" in russian, "the row with no Russian keeps its English"
    assert "hello to you" not in russian

    english = exemplars.block([both, only_english], "en")
    assert "שלום לך = hello to you" in english
    assert "привет тебе" not in english

    # The instruction stays English in both, because the prompt is English. What follows
    # the reader is the gloss, which is the half they would recognise.
    for made in (russian, english):
        assert made.startswith("Sentences a Hebrew speaker wrote")

    assert exemplars.block([both]) == exemplars.block([both], "en"), "English is the default"


def test_a_pool_row_keeps_the_russian_and_who_wrote_it(monkeypatch: Any) -> None:
    """Tatoeba is CC BY per sentence per contributor, and LICENSING.md says the credit
    lives in the row — so the row keeps `ru_by` whether or not anything shows it."""
    made = exemplars._row(
        {
            "id": 7,
            "he": "שלום",
            "en": "hello",
            "ru": "привет",
            "ru_by": "dmitri",
            "words": [["שלום", "NOUN"]],
            "by": "anna",
        }
    )
    assert made is not None
    assert made.russian == "привет" and made.russian_by == "dmitri"

    without = exemplars._row(
        {"id": 8, "he": "שלום", "en": "hello", "words": [["שלום", "NOUN"]], "by": "anna"}
    )
    assert without is not None and without.russian == "" and without.russian_by == ""
