"""What the dictionary says about a Hebrew form, against a fake provider.

Nothing here reaches the network or spends. The provider is a stub that records what it
was asked, which is the pattern `test_annotate.py` uses for glosses and for the same
reason: the interesting behaviour is the caching, the cleaning and what is allowed to
overrule what, none of which needs a model to exercise.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from targum.annotate import Annotator
from targum.annotate.dictionary import (
    DICTIONARY_MODEL,
    PROMPT_VERSION,
    Entry,
    build,
    cached,
    clean_binyan,
    clean_root,
    estimate,
    provider_name,
    unpaid,
)
from targum.cache import Cache
from targum.models import Segment, SegmentedDocument, Token


class FakeDictionary:
    """Answers from a table, and remembers every form it was asked about."""

    name = "fake-dictionary/1"

    def __init__(self, answers: dict[str, Entry] | None = None) -> None:
        self.answers = answers or {}
        self.asked: list[str] = []

    def look_up(self, forms: list[str], on_progress: object = None) -> dict[str, Entry]:
        self.asked.extend(forms)
        return {form: self.answers[form] for form in forms if form in self.answers}


ZORAM = Entry(dictionary_form="זרם", part="verb", root="זרם", binyan="פעל")


def test_a_form_is_asked_about_once_and_then_it_is_free(tmp_path: Path) -> None:
    """The whole economic argument for the stage: a text has far fewer distinct forms
    than tokens, and the second book is nearly free."""
    cache = Cache(tmp_path / "cache")
    provider = FakeDictionary({"זורם": ZORAM})
    held, owing = build(["זורם", "זורם"], provider, cache=cache)
    assert held == {"זורם": ZORAM} and owing == 0
    assert provider.asked == ["זורם"], "a repeated form is asked about once"

    again = FakeDictionary({"זורם": ZORAM})
    held, owing = build(["זורם"], again, cache=cache)
    assert held == {"זורם": ZORAM} and again.asked == []


def test_a_form_the_dictionary_declines_is_written_down_as_declined(tmp_path: Path) -> None:
    """Otherwise a word that is not a word is asked about on every build for ever, and
    the one thing more expensive than a wrong answer is a question with no answer."""
    cache = Cache(tmp_path / "cache")
    build(["##לבים"], FakeDictionary(), cache=cache)
    second = FakeDictionary()
    held, owing = build(["##לבים"], second, cache=cache)
    assert second.asked == [] and held == {} and owing == 0


def test_nothing_is_bought_when_nothing_may_be(tmp_path: Path) -> None:
    """`buy=False` is what a rebuild uses: it fills from what is held and says what
    finishing would cost, exactly as `build_glossary` does."""
    cache = Cache(tmp_path / "cache")
    provider = FakeDictionary({"זורם": ZORAM})
    held, owing = build(["זורם", "רוצה"], provider, cache=cache, buy=False)
    assert held == {} and owing == 2 and provider.asked == []


def test_the_price_is_quoted_net_of_what_is_already_held(tmp_path: Path) -> None:
    cache = Cache(tmp_path / "cache")
    build(["זורם"], FakeDictionary({"זורם": ZORAM}), cache=cache)
    assert unpaid(["זורם", "רוצה"], "fake-dictionary/1", cache) == ["רוצה"]
    assert cached("זורם", "fake-dictionary/1", cache) == ZORAM
    assert estimate(0) == 0 and estimate(1000) > 0


def test_the_model_and_the_question_are_both_in_the_provider_name() -> None:
    """The model, for the reason `serve._gloss_word` records: a server and a build that
    disagree about it buy the whole library twice, on the dearer one.

    And the prompt, because the prompt is half of what produced the answer. Sharpening
    it and re-running returned the old answers off disk and reported that nothing had
    changed, which is the same trap the annotator's name exists to avoid.
    """
    assert provider_name().startswith(f"anthropic/{DICTIONARY_MODEL}/")
    assert provider_name("claude-opus-5") != provider_name()
    assert provider_name(version=PROMPT_VERSION + 1) != provider_name()


@pytest.mark.parametrize(
    ("said", "want"),
    [
        ("ז־ר־ם", "זרם"),
        ("ז.ר.ם", "זרם"),
        ("ז ר ם", "זרם"),
        ("זרם", "זרם"),
        ("כרסם", "כרסם"),
        # Not a root, whatever it is: two letters, five letters, a word in English.
        ("זר", ""),
        ("זרםםם", ""),
        ("z-r-m", ""),
        ("", ""),
    ],
)
def test_a_root_is_letters_or_it_is_nothing(said: str, want: str) -> None:
    """A model asked for a root writes it the way a grammar book does. The reader puts
    the maqafs in, so they come out here — and anything that is not three or four Hebrew
    letters is dropped rather than shown, which is the bargain `hebrew.py` strikes."""
    assert clean_root(said) == want


@pytest.mark.parametrize(
    ("said", "want"),
    [
        ("פעל", "פעל"),
        ("HITPAEL", "התפעל"),
        ("hitpael", "התפעל"),
        ("hiphil", "הפעיל"),
        ("qal", "פעל"),
        # Outside the seven, or not a binyan at all.
        ("polel", ""),
        ("shafel", ""),
        ("", ""),
    ],
)
def test_a_binyan_is_a_name_the_reader_already_knows(said: str, want: str) -> None:
    assert clean_binyan(said) == want


def _document(text: str) -> SegmentedDocument:
    return SegmentedDocument(
        document_hash="d",
        language="he",
        segmenter="fake/1",
        segments=[
            Segment(
                id="s1", text=text, ref="", kind="paragraph", block_id="b1", block_index=1, index=0
            )
        ],
    )


class OneVerb:
    """A lemmatizer that returns a single verb with no root and no binyan, which is what
    DICTA returns for the participles it lemmatizes to themselves."""

    name = "one-verb/1"

    def __init__(self, lemma: str = "זורם", pos: str = "VERB") -> None:
        self.lemma = lemma
        self.pos = pos

    def lemmas(self, segments: list[Segment], language: str) -> dict[str, list[Token]]:
        return {
            segments[0].id: [
                Token(
                    start=0,
                    end=len(self.lemma),
                    surface=self.lemma,
                    lemma=self.lemma,
                    band=0,
                    pos=self.pos,
                )
            ]
        }


class NoBands:
    name = "no-bands/1"
    method = "none"
    note = ""

    def supports(self, language: str) -> bool:
        return False

    def band(self, lemma: str, language: str) -> int:
        return 0


def test_the_dictionary_fills_the_root_and_binyan_the_tagger_had_none_of() -> None:
    """DICTA tags no binyan and lemmatizes many verbs to the participle, which spells no
    pattern — so the root goes with it. This is the gap the dictionary closes."""
    annotator = Annotator(
        lemmatizer=OneVerb(),
        bands=NoBands(),
        dictionary={"זורם": ZORAM},
        dictionary_name="fake-dictionary/1",
    )
    token = annotator.annotate(_document("זורם")).tokens["s1"][0]
    assert (token.binyan, token.root) == ("פעל", "זרם")


def test_the_lemma_is_never_moved_by_the_dictionary() -> None:
    """A lemma is a key — every bought gloss and every marked word is filed under it, and
    moving one orphans both. The dictionary form is carried in the entry and applied
    only by the migration that builds a map first (targum-internal#141)."""
    annotator = Annotator(
        lemmatizer=OneVerb(),
        bands=NoBands(),
        dictionary={"זורם": ZORAM},
        dictionary_name="fake-dictionary/1",
    )
    assert annotator.annotate(_document("זורם")).tokens["s1"][0].lemma == "זורם"


def test_a_fact_that_was_looked_up_is_never_overruled_by_one_that_was_guessed() -> None:
    """Scripture reads its binyan and root off the hand tagging. A model does not get to
    correct an editor."""

    class Tagged(OneVerb):
        def lemmas(self, segments: list[Segment], language: str) -> dict[str, list[Token]]:
            got = super().lemmas(segments, language)
            got["s1"][0] = got["s1"][0].model_copy(update={"binyan": "התפעל", "root": "הלך"})
            return got

    annotator = Annotator(
        lemmatizer=Tagged(),
        bands=NoBands(),
        dictionary={"זורם": ZORAM},
        dictionary_name="fake-dictionary/1",
    )
    token = annotator.annotate(_document("זורם")).tokens["s1"][0]
    assert (token.binyan, token.root) == ("התפעל", "הלך")


def test_only_a_verb_is_given_a_binyan_from_the_dictionary() -> None:
    """A noun with a binyan on its card is a lie the reader has no way to check, and an
    entry can carry a root for a noun built on a verbal root."""
    annotator = Annotator(
        lemmatizer=OneVerb("זרימה", pos="NOUN"),
        bands=NoBands(),
        dictionary={"זרימה": Entry(part="noun", root="זרם")},
        dictionary_name="fake-dictionary/1",
    )
    token = annotator.annotate(_document("זרימה")).tokens["s1"][0]
    assert token.binyan is None and token.root is None


def test_a_text_read_with_a_dictionary_is_a_different_annotation() -> None:
    """The name is the whole invalidation mechanism: a text that would now carry facts it
    did not carry before has to be read again, and reading again is free."""
    plain = Annotator(lemmatizer=OneVerb(), bands=NoBands())
    with_book = Annotator(
        lemmatizer=OneVerb(),
        bands=NoBands(),
        dictionary={"זורם": ZORAM},
        dictionary_name="fake-dictionary/1",
    )
    assert "fake-dictionary/1" in with_book.name
    assert "fake-dictionary/1" not in plain.name


def test_an_empty_dictionary_leaves_the_name_alone() -> None:
    """A box that has bought nothing must not claim to have read with a dictionary, or
    every text on it is re-annotated for a difference that is not there."""
    assert (
        Annotator(lemmatizer=OneVerb(), bands=NoBands(), dictionary={}, dictionary_name="d/1").name
        == Annotator(lemmatizer=OneVerb(), bands=NoBands()).name
    )
