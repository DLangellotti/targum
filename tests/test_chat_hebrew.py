"""The Hebrew mode's contract, read back by the same rule it is written to."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from targum import level
from targum.accounts import Store
from targum.chat import hebrew

TURN = """> אֲנִי הָלַכְתִּי לַשּׁוּק הַבֹּקֶר.
= I went to the market this morning.
מָה קָנִיתָ שָׁם?
= What did you buy there?
קָנִיתִי לֶחֶם.
= I bought bread.
"""


def test_a_turn_is_read_back_as_pairs_with_the_recast_marked() -> None:
    got = hebrew.pairs(TURN)
    assert [(p.recast, p.english) for p in got] == [
        (True, "I went to the market this morning."),
        (False, "What did you buy there?"),
        (False, "I bought bread."),
    ]
    assert got[0].hebrew.startswith("אֲנִי") and not got[0].hebrew.startswith(">")


def test_a_hebrew_line_the_model_forgot_to_translate_is_kept_and_a_stray_english_line_is_not() -> (
    None
):
    got = hebrew.pairs("שָׁלוֹם\nHow are you?\nמַה שְּׁלוֹמְךָ?\n= How are you?")
    assert [(p.hebrew, p.english) for p in got] == [("שָׁלוֹם", ""), ("מַה שְּׁלוֹמְךָ?", "How are you?")]
    assert hebrew.pairs("") == [] and hebrew.pairs("Just English.") == []


def test_words_become_seconds_at_the_conversational_rate() -> None:
    assert hebrew.seconds_for(120) == 60.0
    assert hebrew.seconds_for(0) == 0.0 and hebrew.seconds_for(-5) == 0.0
    assert hebrew.words_in("שלום עולם", "hi there friend") == 5
    assert 89 < hebrew.CONVERSATION_WORDS_PER_MINUTE < 150, (
        "between the read-aloud and the estimate"
    )


@pytest.mark.skipif(
    shutil.which("python3") is None or not hebrew.common_words(5), reason="wordfreq missing"
)
def test_the_common_words_are_the_first_two_bands_most_common_first() -> None:
    from wordfreq import zipf_frequency

    words = hebrew.common_words(50)
    assert len(words) == 50 and words[0] in ("את", "של", "לא")
    assert all(zipf_frequency(w, "he") >= hebrew.BAND_FLOOR_ZIPF for w in words)


def test_the_ledger_block_carries_the_words_and_never_a_level(tmp_path: Path) -> None:
    store = Store(tmp_path / "db")
    person, _ = store.finish_sign_in(store.start_sign_in("r@example.com"))  # type: ignore[misc]
    store.push(
        person,
        {
            "words": [
                {
                    "language": "he",
                    "lemma": "שלום",
                    "status": 9,
                    "band": "easy",
                    "at": 1,
                    "seen": 1,
                },
                {"language": "he", "lemma": "בית", "status": 9, "band": "easy", "at": 3, "seen": 3},
                {"language": "he", "lemma": "דוד", "status": 9, "band": "name", "at": 2, "seen": 2},
                {"language": "he", "lemma": "רעב", "status": 2, "band": "hard", "at": 4, "seen": 4},
            ]
        },
    )
    known = hebrew.known_words(store, person.id, "he")
    assert known == ["בית", "שלום"], "known only, names out, newest first"
    block = hebrew.ledger_block(level.snapshot(store, person.id, "he"), known, ["את", "של"])
    assert "known words (2): בית שלום" in block and "Common words" in block
    assert "not a placement" in block
    empty = hebrew.ledger_block(level.EMPTY, [], [])
    assert "no words known yet" in empty


def test_the_contract_says_the_shape_and_the_rule() -> None:
    said = " ".join(hebrew.CONTRACT.split())  # the prose is wrapped; the words are what count
    assert '"= "' in said and '"> "' in said
    assert "vowel points" in said and "At most one word outside" in said
    assert "never tell the reader they are at a level" in said.lower()
    assert "!" not in said
