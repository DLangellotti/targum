"""The French ending → gender table (targum-internal#263)."""

from __future__ import annotations

import json

from targum.annotate import endings


def test_the_table_keeps_only_endings_that_tell_the_gender() -> None:
    """Counted from Grammalecte's lexicon, each kept where 90% or more of at least fifty
    plain nouns share a gender; the source and its licence travel with it."""
    raw = json.loads(endings._TABLE.read_text(encoding="utf-8"))
    assert raw["licence"] == "MPL-2.0" and "grammalecte" in raw["source"].lower()
    assert raw["endings"], "the table is empty"
    for row in raw["endings"]:
        assert row["share"] >= 0.9 and row["nouns"] >= 50, row
        assert row["gender"] in ("m", "f"), row


def test_a_word_is_given_its_longest_telling_ending() -> None:
    assert endings.ending_of("nation") == "f:tion"
    assert endings.ending_of("fromage") == "m:age"
    assert endings.ending_of("Nation") == "f:tion"
    assert endings.ending_of("livre") == ""
    assert endings.ending_of("l'eau") == "", "not a plain word"
