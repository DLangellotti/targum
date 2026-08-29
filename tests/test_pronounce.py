"""How a word is said, and the two ways of getting it wrong.

The interesting property is not that a reading appears. It is that the same dictionary
form gets two different readings in two sentences, because the reading belongs to the
occurrence — which is exactly what a table keyed on the lemma could not have expressed,
and the reason this rides on the token.
"""

from __future__ import annotations

import pytest

from targum.annotate import Annotator, PhonikudPronouncer, pronounceable
from targum.annotate.pronounce import PREFIX_MARK, sayable
from targum.models import Annotation, Segment, SegmentedDocument, Token, Vocalization
from targum.vocalize.base import TAAMIM, strip_taamim

pytestmark = pytest.mark.skipif(
    not PhonikudPronouncer().available()[0], reason="phonikud is not installed"
)

# "I ate an onion and bread. Afterwards I sat in the shade of the big tree." The same
# four letters, בצל, twice: an onion, then in the shade. Nothing but the vowels decides.
ONION = "אכלתי בצל ולחם."
SHADE = "אחר כך ישבתי בצל העץ הגדול."

POINTED = {
    "s0": "אָכַלְתִּי בָּצָל וְלֶחֶם.",
    "s1": "אַחַר כָּךְ יָשַׁבְתִּי בְּצֵל הָעֵץ הַגָּדוֹל.",
}


def document(texts: dict[str, str], language: str = "he") -> SegmentedDocument:
    return SegmentedDocument(
        document_hash="hash",
        language=language,
        segmenter="test",
        segments=[
            Segment(id=sid, block_id="b0000", block_index=i, index=i, text=text)
            for i, (sid, text) in enumerate(texts.items())
        ],
    )


def vocalization(pointed: dict[str, str], language: str = "he") -> Vocalization:
    return Vocalization(
        document_hash="hash",
        language=language,
        vocalizer="test/1",
        model=None,
        segments=pointed,
        machine=list(pointed),
        rejected=[],
    )


class OneWordPerToken:
    """Tokens at fixed offsets, so the test does not need Stanza to have an opinion."""

    name = "fake/1"

    def lemmas(self, segments: list[Segment], language: str) -> dict[str, list[Token]]:
        out: dict[str, list[Token]] = {}
        for segment in segments:
            tokens: list[Token] = []
            offset = 0
            for word in segment.text.split(" "):
                bare = word.rstrip(".")
                if bare:
                    tokens.append(
                        Token(
                            start=offset,
                            end=offset + len(bare),
                            surface=bare,
                            # Both occurrences of בצל share a lemma on purpose.
                            lemma=bare,
                            band=1,
                        )
                    )
                offset += len(word) + 1
            out[segment.id] = tokens
        return out


class FlatBands:
    name = "flat/1"
    method = "frequency"
    note = "made up"

    def supports(self, language: str) -> bool:
        return True

    def band(self, lemma: str, language: str) -> int:
        return 1


def annotate(texts: dict[str, str], pointed: dict[str, str] | None) -> Annotation:
    annotator = Annotator(
        lemmatizer=OneWordPerToken(), bands=FlatBands(), pronouncer=PhonikudPronouncer()
    )
    return annotator.annotate(
        document(texts), vocalization(pointed) if pointed is not None else None
    )


def readings(annotation: Annotation) -> dict[str, list[str]]:
    """Every reading found, grouped by the word it was read from."""
    out: dict[str, list[str]] = {}
    for tokens in annotation.tokens.values():
        for token in tokens:
            if token.ipa:
                out.setdefault(token.surface, []).append(token.ipa)
    return out


def test_one_lemma_two_readings() -> None:
    """The whole point. בצל is an onion in one sentence and shade in the next."""
    found = readings(annotate({"s0": ONION, "s1": SHADE}, POINTED))
    assert found["בצל"] == ["batsˈal", "btsˈel"]


def test_the_stress_is_marked() -> None:
    """Which syllable carries it is not in the spelling and not in a dictionary entry."""
    found = readings(annotate({"s0": ONION, "s1": SHADE}, POINTED))
    assert all("ˈ" in reading for readings_ in found.values() for reading in readings_)


def test_nothing_is_read_without_vowels() -> None:
    """Bare בצל comes back from phonikud as `vˈtsl`, which is not a word.

    A word with no reading is a gap the reader can see past. A confident wrong one is
    the failure this guard exists for, and it is the same rule the root derivation keeps.
    """
    assert annotate({"s0": ONION}, None).tokens["s0"][0].ipa is None
    bare = {"s0": ONION}
    assert readings(annotate(bare, bare)) == {}


def test_a_word_with_no_hebrew_is_not_read() -> None:
    """phonikud returns Latin unchanged, which would have the card claim it is a reading."""
    assert not sayable("hello")
    assert not sayable("1948")
    assert sayable("בָּצָל")


def test_the_prefix_mark_never_reaches_the_phonemizer() -> None:
    """phonikud's own diacritizer writes an ASCII pipe for a prefix boundary.

    It is not a combining mark, so it survives `strip_nikkud` and would be read as a word
    break here and as a changed letter by `splice`. Nothing emits one today; the guard is
    what makes adopting that diacritizer later a decision rather than an incident.
    """
    said = PhonikudPronouncer().say([f"בְּ{PREFIX_MARK}צֵל"])
    assert said[f"בְּ{PREFIX_MARK}צֵל"] == "btsˈel"


def test_a_reading_is_the_same_word_by_word_as_in_its_sentence() -> None:
    """Which is what lets the readings be deduplicated per distinct form.

    If this ever stops holding, the table in the builder is silently wrong rather than
    merely stale, so it is pinned here rather than left as a comment.
    """
    import phonikud

    sentence = POINTED["s1"]
    whole = phonikud.phonemize(sentence).replace(".", "").split()
    apart = [phonikud.phonemize(word.rstrip(".")) for word in sentence.split()]
    assert whole == apart


def test_the_annotator_says_it_read_the_words() -> None:
    """The name is the cache key. Without it a book built yesterday keeps its silence."""
    plain = Annotator(lemmatizer=OneWordPerToken(), bands=FlatBands())
    speaking = Annotator(
        lemmatizer=OneWordPerToken(), bands=FlatBands(), pronouncer=PhonikudPronouncer()
    )
    assert speaking.name != plain.name
    assert speaking.name.endswith("+phonikud/2")


def test_another_language_is_left_alone() -> None:
    """Russian has vowels in the spelling; the marks these rules read are Hebrew ones."""
    assert pronounceable("he")
    assert not pronounceable("ru")
    annotator = Annotator(
        lemmatizer=OneWordPerToken(), bands=FlatBands(), pronouncer=PhonikudPronouncer()
    )
    russian = SegmentedDocument(
        document_hash="hash",
        language="ru",
        segmenter="test",
        segments=[Segment(id="s0", block_id="b0000", block_index=0, index=0, text="дом стоит")],
    )
    annotated = annotator.annotate(russian, vocalization({"s0": "дом стоит"}, language="ru"))
    assert all(token.ipa is None for token in annotated.tokens["s0"])


# Ruth 1:1, as a Masoretic edition hands it over: vowels and chanting marks together.
# The accents are the point of these tests — they are where the stress already is.
ACCENTED = "וַיְהִ֗י בִּימֵי֙ שְׁפֹ֣ט הַשֹּׁפְטִ֔ים וַיְהִ֥י רָעָ֖ב בָּאָֽרֶץ׃"


def test_the_chanting_marks_never_reach_the_phonemizer() -> None:
    """Fed שְׁפֹ֣ט whole, phonikud reads the accent as a letter and loses the vowel.

    It answers `ʃˈftˈ`, which is not a word and not a warning either — it looks like a
    reading. Every pointed Tanakh reaches this stage with its accents on, so the guard is
    not for a rare document; it is for the shelf's largest one.
    """
    import phonikud

    assert phonikud.phonemize("שְׁפֹ֣ט").strip() == "ʃˈftˈ"
    said = PhonikudPronouncer().say(["שְׁפֹ֣ט"])
    assert said["שְׁפֹ֣ט"] == "ʃfˈot"


def test_the_accent_places_the_stress() -> None:
    """בָּאָ֑רֶץ is a segolate: ba-A-rets, and the etnahta is sitting on the A.

    Strip the accents and phonikud puts the stress on the last syllable, as it does for
    every word it has not been told about. Keep them, and the Masoretes answer.
    """
    from targum.annotate.pronounce import stressed

    word = "בָּאָ֑רֶץ"
    import phonikud

    assert phonikud.phonemize(strip_taamim(word)).strip() == "baʔaʁˈets"
    assert PhonikudPronouncer().say([word])[word] == "baʔˈaʁets"
    assert stressed(word) is not None


def test_an_unplaced_accent_is_not_believed() -> None:
    """Pashta is written on the last letter whatever syllable carries the stress.

    Reading a stress off one would be a confident wrong answer, which is the thing this
    module refuses everywhere else, so the word falls back to the ordinary default.
    """
    from targum.annotate.pronounce import stressed

    assert stressed("בִּימֵי֙") is None
    assert PhonikudPronouncer().say(["בִּימֵי֙"])["בִּימֵי֙"] == "bimˈej"


def test_a_verse_is_read_whole() -> None:
    """Every word of Ruth 1:1 comes back a word, with no accent left in the reading."""
    said = PhonikudPronouncer().say(ACCENTED.replace("׃", "").split())
    assert len(said) == 7
    for word, reading in said.items():
        assert not any(ord(char) in TAAMIM for char in reading), word
        assert "ˈ" in reading, word


def test_meteg_is_not_a_vowel() -> None:
    """U+05BD is meteg and silluq both, and phonikud reads it as an `e`.

    בָּאָֽרֶץ — the verse-final form, where the mark is silluq — comes back
    `baʔaeʁˈets`, a syllable the word does not have. The vocalizer keeps the mark
    because it is what separates a qamats gadol from a qamats qatan; the phonemizer
    cannot use it and must not sound it.
    """
    import phonikud

    assert phonikud.phonemize("בָּאָֽרֶץ").strip() == "baʔaeʁˈets"
    assert PhonikudPronouncer().say(["בָּאָֽרֶץ"])["בָּאָֽרֶץ"] == "baʔaʁˈets"
