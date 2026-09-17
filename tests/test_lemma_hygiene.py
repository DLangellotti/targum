"""What may be stored as a lemma, and what may not (targum-internal#305).

The lemma is the identity for everything: the ledger is keyed on it, the gloss is bought
against it, the ulpan ladder counts it. So a lemmatizer's failure token and a
mis-tagged part of speech are not cosmetic — they are a word nobody knows entering
somebody's vocabulary, and a conjugation table offered for a word that has none.

Measured over every built annotation on 2026-09-17: `[unk]` 318 tokens, `יש` tagged VERB
2,521 times. The third thing the card named — verb lemmas carrying an unstripped vav —
is 2,089 tokens, 0.55% of all verb tokens, and is *not* fixed here: it is the
lemmatizer's own output and wants work in the lemmatizer. See the card.
"""

from __future__ import annotations

from targum.annotate import Annotator
from targum.annotate.base import NEVER_A_VERB, NOT_A_WORD, Bands
from targum.models import Segment, SegmentedDocument, Token


class Fixed:
    """A lemmatizer that says exactly what it is told to, so the guard is what is tested."""

    name = "fixed/1"

    def __init__(self, tokens: list[Token]) -> None:
        self.tokens = tokens

    def lemmas(self, segments: list[Segment], language: str) -> dict[str, list[Token]]:
        return {segments[0].id: self.tokens} if segments else {}


class Flat(Bands):
    """One band for everything: the banding is not what these tests are about."""

    name = "flat/1"
    method = "flat"
    note = "flat, for a test"

    def band(self, lemma: str, language: str = "he") -> int:
        return 3

    def supports(self, language: str) -> bool:
        return True


def read(tokens: list[Token], text: str = "יש דבר", language: str = "he") -> list[Token]:
    document = SegmentedDocument(
        document_hash="h",
        language=language,
        segmenter="t",
        segments=[Segment(id="s1", block_id="b0", block_index=0, index=0, text=text)],
    )
    annotated = Annotator(lemmatizer=Fixed(tokens), bands=Flat()).annotate(document)
    return annotated.tokens.get("s1", [])


def test_a_token_the_lemmatizer_could_not_read_is_not_a_word() -> None:
    """`[unk]` went into ledgers as a word nobody knows, banded hardest."""
    out = read(
        [
            Token(start=0, end=2, surface="יש", lemma="[unk]", pos="NOUN", band=0),
            Token(start=3, end=6, surface="דבר", lemma="דבר", pos="NOUN", band=0),
        ]
    )
    assert [t.lemma for t in out] == ["דבר"], "the unreadable token is read past"


def test_every_shape_of_failure_token_is_refused() -> None:
    for failure in NOT_A_WORD:
        out = read([Token(start=0, end=2, surface="יש", lemma=failure, pos="NOUN", band=0)])
        assert out == [], f"{failure!r} is not a word"


def test_yesh_is_not_a_verb_however_often_it_is_tagged_one() -> None:
    """The ledger survives it — the lemma is right. The card does not: it would offer
    the conjugations of a word that has none."""
    out = read([Token(start=0, end=2, surface="יֵשׁ", lemma="יֵשׁ", pos="VERB", band=0)])
    assert len(out) == 1
    assert out[0].pos == "AUX"
    assert out[0].lemma == "יֵשׁ", "the lemma is untouched; only the tagging was wrong"


def test_the_correction_is_only_for_verbs() -> None:
    """Tagged anything else, it is left alone — this fixes one wrong tag, not the tagger."""
    out = read([Token(start=0, end=2, surface="יש", lemma="יש", pos="AUX", band=0)])
    assert out[0].pos == "AUX"
    out = read([Token(start=0, end=2, surface="יש", lemma="יש", pos="NOUN", band=0)])
    assert out[0].pos == "NOUN"


def test_a_real_verb_is_untouched() -> None:
    out = read([Token(start=0, end=3, surface="אמר", lemma="אמר", pos="VERB", band=0)], text="אמר")
    assert out[0].pos == "VERB"


def test_another_language_keeps_its_words() -> None:
    """The guard compares raw lemmas. An earlier draft reached for `canonical.bare`,
    which keeps only Hebrew letters — it would have emptied every Russian and Italian
    lemma and dropped the token with it."""
    out = read(
        [
            Token(start=0, end=6, surface="сказал", lemma="сказать", pos="VERB", band=0),
            Token(start=7, end=11, surface="дело", lemma="дело", pos="NOUN", band=0),
        ],
        text="сказал дело",
        language="ru",
    )
    assert [t.lemma for t in out] == ["сказать", "дело"]


def test_the_tables_are_written_bare() -> None:
    """They are compared against a lemma with its nikkud stripped, so a pointed entry
    in the table would never match anything."""
    for word in NEVER_A_VERB:
        assert word == word.strip()
        assert not any("֑" <= ch <= "ׇ" for ch in word), f"{word} carries marks"
