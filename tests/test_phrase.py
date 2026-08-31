"""A run of words inside a sentence, translated against the translation already there.

No model is called: a fake provider answers, and what is tested is what is done with the
answer — cached, checked against the translation, and never taken on trust when it
claims to be a quotation.
"""

from __future__ import annotations

from pathlib import Path

from targum.annotate.phrase import (
    PhraseAnswer,
    cached_phrase,
    entry_for,
    phrase_key,
    phrase_one,
    quoted_piece,
    within_limits,
)
from targum.cache import Cache

SENTENCE = 'השבוע: השב"כ מאשר איום על בנו של ראש הממשלה, ובאיסטנבול נפתחת ועדה צבאית חדשה.'
TRANSLATION = (
    "This week: the Shin Bet confirms a threat against the prime minister's son, "
    "and in Istanbul a new military committee opens."
)
RUN = "ועדה צבאית חדשה"


class FakePhrases:
    name = "fake/phrases"

    def __init__(self, answer: PhraseAnswer | None = None) -> None:
        self.answer = answer or PhraseAnswer("a new military committee", True)
        self.asked: list[str] = []

    def explain(
        self,
        phrase: str,
        sentence: str,
        translation: str,
        source_language: str,
        target_language: str,
    ) -> PhraseAnswer:
        self.asked.append(phrase)
        return self.answer


def test_a_phrase_is_bought_once(tmp_path: Path) -> None:
    cache = Cache(tmp_path)
    provider = FakePhrases()
    first = phrase_one(RUN, SENTENCE, TRANSLATION, "he", "en", provider, cache=cache)
    second = phrase_one(RUN, SENTENCE, TRANSLATION, "he", "en", provider, cache=cache)
    assert first == second == PhraseAnswer("a new military committee", True)
    assert provider.asked == [RUN], "the second reader was answered from the cache"


def test_a_quote_that_is_not_in_the_translation_is_not_a_quote(tmp_path: Path) -> None:
    """A model asked to quote sometimes paraphrases and says it quoted. The caption on
    the card claims the words are in the parallel text, so the claim is checked."""
    cache = Cache(tmp_path)
    provider = FakePhrases(PhraseAnswer("a fresh army panel", True))
    answer = phrase_one(RUN, SENTENCE, TRANSLATION, "he", "en", provider, cache=cache)
    assert answer == PhraseAnswer("a fresh army panel", False)


def test_a_quote_is_returned_as_the_translation_spells_it(tmp_path: Path) -> None:
    """Quotation marks, capitals and doubled spaces the model added come off: what the
    reader sees is the piece of the translation, letter for letter."""
    cache = Cache(tmp_path)
    provider = FakePhrases(PhraseAnswer("“A New  Military Committee”", True))
    answer = phrase_one(RUN, SENTENCE, TRANSLATION, "he", "en", provider, cache=cache)
    assert answer == PhraseAnswer("a new military committee", True)


def test_a_rendering_stays_a_rendering(tmp_path: Path) -> None:
    """Even when the words happen to be in the translation, a model that said it did not
    quote is believed: `quoted` only ever goes from true to false here, never up."""
    cache = Cache(tmp_path)
    provider = FakePhrases(PhraseAnswer("a new military committee", False))
    answer = phrase_one(RUN, SENTENCE, TRANSLATION, "he", "en", provider, cache=cache)
    assert answer == PhraseAnswer("a new military committee", False)


def test_an_empty_answer_is_not_remembered(tmp_path: Path) -> None:
    cache = Cache(tmp_path)
    provider = FakePhrases(PhraseAnswer(""))
    empty = phrase_one(RUN, SENTENCE, TRANSLATION, "he", "en", provider, cache=cache)
    assert empty == PhraseAnswer("")
    phrase_one(RUN, SENTENCE, TRANSLATION, "he", "en", provider, cache=cache)
    assert provider.asked == [RUN, RUN], "nothing was cached, so it was asked again"


def test_the_key_turns_on_the_translation(tmp_path: Path) -> None:
    """A sentence translated again is a different question: the old answer might quote
    words that are no longer on the page. Whitespace is not a different question."""
    cache = Cache(tmp_path)
    same = phrase_key(cache, RUN, SENTENCE, TRANSLATION, "he", "en", "p")
    assert phrase_key(cache, RUN, SENTENCE, TRANSLATION + " Really.", "he", "en", "p") != same
    assert phrase_key(cache, RUN, SENTENCE, TRANSLATION, "he", "ru", "p") != same
    assert phrase_key(cache, RUN, SENTENCE, TRANSLATION, "he", "en", "q") != same
    assert (
        phrase_key(cache, RUN, "  " + SENTENCE, TRANSLATION.replace(" ", "  "), "he", "en", "p")
        == same
    )


def test_quoted_piece_forgives_case_and_quotes_but_not_words() -> None:
    assert quoted_piece("Prime Minister's son", TRANSLATION) == "prime minister's son"
    assert quoted_piece("'the Shin Bet'", TRANSLATION) == "the Shin Bet"
    assert quoted_piece("the Mossad", TRANSLATION) is None
    assert quoted_piece("“”", TRANSLATION) is None


def test_the_entry_carries_all_three_on_their_own_lines() -> None:
    assert (
        entry_for(" ועדה  צבאית ", "a\nb", "c  d")
        == "sentence: a b\ntranslation: c d\nrun: ועדה צבאית"
    )


def test_limits_keep_this_a_phrase_service() -> None:
    assert within_limits(RUN, SENTENCE, TRANSLATION)
    assert not within_limits("שלום", SENTENCE, TRANSLATION), "not in the sentence"
    assert not within_limits("", SENTENCE, TRANSLATION)
    assert not within_limits(RUN, SENTENCE, "")
    assert not within_limits("א", "א" * 601, TRANSLATION), "a paragraph, not a sentence"
    assert not within_limits(RUN, SENTENCE, "x" * 901)


def test_a_kind_the_card_teaches_is_only_ever_one_of_the_four(tmp_path: Path) -> None:
    """ "idiom", "construct chain", "verb + preposition", "fixed expression" — anything
    else the model says is dropped rather than shown. A category invented once is a
    category the card teaches."""
    cache = Cache(tmp_path)
    provider = FakePhrases(PhraseAnswer("a new military committee", True, "idiom", "לִשְׁבֹּר אֶת הָרֹאשׁ"))
    kept = phrase_one(RUN, SENTENCE, TRANSLATION, "he", "en", provider, cache=cache)
    assert kept.kind == "idiom" and kept.citation == "לִשְׁבֹּר אֶת הָרֹאשׁ"

    invented = FakePhrases(PhraseAnswer("a new military committee", True, "proverb-ish"))
    assert (
        phrase_one("ועדה צבאית", SENTENCE, TRANSLATION, "he", "en", invented, cache=cache).kind
        == ""
    )


def test_an_answer_bought_before_kind_existed_still_stands(tmp_path: Path) -> None:
    """What was paid for is never re-bought: an old cache entry comes back with kind and
    citation empty, and the card simply says less about it."""
    cache = Cache(tmp_path)
    key = phrase_key(cache, RUN, SENTENCE, TRANSLATION, "he", "en", "fake/phrases")
    cache.put("phrase", key, {"meaning": "a new military committee", "quoted": True})
    held = cached_phrase(RUN, SENTENCE, TRANSLATION, "he", "en", "fake/phrases", cache=cache)
    assert held == PhraseAnswer("a new military committee", True, "", "")
