"""Difficulty bands and glosses, against fake components so the suite stays offline."""

from __future__ import annotations

import pytest

from targum.annotate import BAND_COUNT, BAND_NAMES, Annotator
from targum.annotate.frequency import CUTS, FrequencyBands
from targum.annotate.gloss import build_glossary, entries_for, estimate, gloss_one, unique_lemmas
from targum.annotate.hebrew import binyan_of, root_of
from targum.cache import Cache
from targum.models import Annotation, Segment, SegmentedDocument, Token


class FakeLemmatizer:
    """Strips a leading Hebrew prefix letter, which is the shape of the real problem.

    Deliberately naive, and wrong in the same way a naive implementation is wrong: it
    strips the ש of שלום, where that letter is part of the word rather than a prefix.
    Test words are chosen to avoid that, since what is under test here is the plumbing,
    not the linguistics.
    """

    name = "fake-lemma/1"
    PREFIXES = "והבכלמש"

    def lemmas(self, segments, language):  # type: ignore[no-untyped-def]
        out: dict[str, list[Token]] = {}
        for segment in segments:
            tokens: list[Token] = []
            offset = 0
            for word in segment.text.split(" "):
                if word.strip(".,;:"):
                    bare = word.strip(".,;:")
                    split = len(bare) > 2 and bare[0] in self.PREFIXES
                    tokens.append(
                        Token(
                            start=offset,
                            end=offset + len(bare),
                            surface=bare,
                            lemma=(bare[1:] if split else bare).lower(),
                            band=0,
                            split=split,
                        )
                    )
                offset += len(word) + 1
            out[segment.id] = tokens
        return out


class FakeBands:
    name = "fake-bands/1"
    method = "curated:test"
    note = "A test list."

    def supports(self, language: str) -> bool:
        return True

    def band(self, lemma: str, language: str) -> int:
        return min(BAND_COUNT, max(1, len(lemma) - 1))


class NoBands(FakeBands):
    """A language nothing can rate, which is Latin's situation."""

    def supports(self, language: str) -> bool:
        return False

    def band(self, lemma: str, language: str) -> int:
        return 0


class FakeGlosses:
    name = "fake-gloss/1"

    def __init__(self) -> None:
        self.asked: list[list[str]] = []

    def gloss(self, lemmas, source_language, target_language, on_progress=None):  # type: ignore[no-untyped-def]
        self.asked.append(list(lemmas))
        if on_progress:
            on_progress(len(lemmas))
        return {lemma: (f"meaning of {lemma}", "noun") for lemma in lemmas}


def document(texts: list[str], language: str = "he") -> SegmentedDocument:
    return SegmentedDocument(
        document_hash="h",
        language=language,
        segmenter="fake/1",
        segments=[
            Segment(id=f"0{i:03d}.000-aaaaaa", block_id=f"b{i:04d}", block_index=i, index=0, text=t)
            for i, t in enumerate(texts)
        ],
    )


def annotator() -> Annotator:
    return Annotator(lemmatizer=FakeLemmatizer(), bands=FakeBands())


# --- bands -------------------------------------------------------------------


def test_bands_run_from_one_to_six() -> None:
    assert BAND_COUNT == 6
    assert len(CUTS) == BAND_COUNT - 1
    assert sorted(BAND_NAMES) == list(range(1, BAND_COUNT + 1))


def test_cuts_are_ordered_common_to_rare() -> None:
    assert list(CUTS) == sorted(CUTS, reverse=True)


def test_frequency_bands_rank_a_common_word_below_a_rare_one() -> None:
    bands = FrequencyBands()
    assert bands.band("שלום", "he") < bands.band("קוממיות", "he")
    assert bands.band("the", "en") < bands.band("perspicacious", "en")
    assert bands.band("дом", "ru") < bands.band("престол", "ru")


def test_an_unknown_word_lands_in_the_rarest_band() -> None:
    assert FrequencyBands().band("zzqxwv", "en") == BAND_COUNT


def test_the_method_is_stated() -> None:
    bands = FrequencyBands()
    assert bands.method == "frequency"
    assert "curated" in bands.note  # says plainly that no curated list is behind it


# --- annotation --------------------------------------------------------------


def test_every_token_is_banded() -> None:
    annotation = annotator().annotate(document(["שלום עולם גדול"]))
    tokens = next(iter(annotation.tokens.values()))
    assert len(tokens) == 3
    assert all(token.band >= 1 for token in tokens)


def test_offsets_point_at_the_right_words() -> None:
    text = "שלום עולם גדול"
    annotation = annotator().annotate(document([text]))
    for token in next(iter(annotation.tokens.values())):
        assert text[token.start : token.end] == token.surface


def test_a_split_token_is_marked() -> None:
    # Hebrew attaches prefixes, so the same string can be one word or two readings.
    annotation = annotator().annotate(document(["בארץ עולם"]))
    tokens = next(iter(annotation.tokens.values()))
    assert tokens[0].split is True
    assert tokens[0].lemma == "ארץ"
    assert tokens[0].surface == "בארץ"
    assert tokens[1].split is False


def test_the_method_is_recorded_on_the_artifact() -> None:
    annotation = annotator().annotate(document(["שלום"]))
    assert annotation.method == "curated:test"
    assert annotation.method_note
    assert "fake-lemma" in annotation.annotator


def test_counts_add_up() -> None:
    annotation = annotator().annotate(document(["שלום עולם", "גדול מאוד יפה"]))
    assert sum(annotation.counts().values()) == 5


def test_lemmas_are_banded_once_each() -> None:
    calls: list[str] = []

    class Counting(FakeBands):
        def band(self, lemma: str, language: str) -> int:
            calls.append(lemma)
            return 1

    Annotator(lemmatizer=FakeLemmatizer(), bands=Counting()).annotate(
        document(["עולם עולם עולם ארץ"])
    )
    assert calls == ["עולם", "ארץ"]


# --- glosses -----------------------------------------------------------------


def annotation_with(lemmas: dict[str, int]) -> Annotation:
    return Annotation(
        document_hash="h",
        language="he",
        annotator="t",
        method="frequency",
        method_note="n",
        tokens={
            "s1": [
                Token(start=0, end=1, surface=lemma, lemma=lemma, band=band)
                for lemma, band in lemmas.items()
            ]
        },
    )


def test_unique_lemmas_are_rarest_first() -> None:
    # A cut list should keep the useful end.
    assert unique_lemmas(annotation_with({"common": 1, "rare": 6, "middling": 3})) == [
        "rare",
        "middling",
        "common",
    ]


def test_a_band_floor_narrows_the_list() -> None:
    assert unique_lemmas(annotation_with({"a": 1, "b": 5}), min_band=4) == ["b"]


def test_cost_scales_with_distinct_lemmas() -> None:
    assert estimate(1000, "claude-opus-5") > estimate(100, "claude-opus-5")
    assert estimate(0, "claude-opus-5") == 0


def test_glossing_pays_once_per_lemma(tmp_path) -> None:  # type: ignore[no-untyped-def]
    cache = Cache(tmp_path / "cache")
    provider = FakeGlosses()
    annotation = annotation_with({"ארץ": 2, "שלום": 1})

    first, paid = build_glossary(annotation, "en", provider, cache=cache)
    assert paid == 2
    assert first.entries["ארץ"] == "meaning of ארץ"

    second, paid_again = build_glossary(annotation, "en", provider, cache=cache)
    assert paid_again == 0
    assert second.entries == first.entries
    assert len(provider.asked) == 1


def test_the_cache_is_shared_across_texts(tmp_path) -> None:  # type: ignore[no-untyped-def]
    # A text has far fewer distinct lemmas than tokens, and the second book in a
    # language should cost a fraction of the first.
    cache = Cache(tmp_path / "cache")
    provider = FakeGlosses()
    build_glossary(annotation_with({"ארץ": 2}), "en", provider, cache=cache)
    _, paid = build_glossary(annotation_with({"ארץ": 2, "שלום": 1}), "en", provider, cache=cache)
    assert paid == 1
    assert provider.asked[-1] == ["שלום"]


def test_a_different_language_pair_is_a_different_cache_entry(tmp_path) -> None:  # type: ignore[no-untyped-def]
    cache = Cache(tmp_path / "cache")
    provider = FakeGlosses()
    build_glossary(annotation_with({"ארץ": 2}), "en", provider, cache=cache)
    _, paid = build_glossary(annotation_with({"ארץ": 2}), "ru", provider, cache=cache)
    assert paid == 1


@pytest.mark.stanza
def test_hebrew_prefixes_are_stripped_for_real(needs_hebrew_model: None) -> None:
    from targum.annotate import StanzaLemmatizer
    from targum.annotate.lemma import PROCESSORS
    from targum.segment import has_processors

    if not has_processors("he", PROCESSORS):
        pytest.skip("Hebrew lemmatizer not downloaded")

    segmented = document(["בה חי חיי קוממיות ממלכתית, בה עוצבה דמותו הרוחנית, הדתית והמדינית."])
    annotation = Annotator(lemmatizer=StanzaLemmatizer()).annotate(segmented)
    tokens = next(iter(annotation.tokens.values()))
    lemmas = {token.surface: token.lemma for token in tokens}
    # ו + ה + מדינית, three morphemes deep, resolved to the dictionary form.
    assert lemmas.get("והמדינית") == "מדיני"
    assert lemmas.get("הרוחנית") == "רוחני"
    assert all(token.split for token in tokens if token.surface.startswith("ה"))
    bands = {token.surface: token.band for token in tokens}
    assert bands.get("קוממיות", 0) >= 4  # archaic, and banded as such


def test_a_language_with_no_frequency_data_is_not_rated() -> None:
    """Latin has dictionary forms but no frequency data. Rating every word as rare
    would look like an answer rather than the absence of one."""
    annotation = Annotator(lemmatizer=FakeLemmatizer(), bands=NoBands()).annotate(
        document(["Gallia est omnis divisa"], "la")
    )
    tokens = next(iter(annotation.tokens.values()))
    assert tokens, "the words are still found and still tappable"
    assert {token.band for token in tokens} == {0}
    assert annotation.method == "none"
    assert "no word frequency data" in annotation.method_note.lower()


def test_a_word_is_glossed_in_the_sentence_it_was_met_in() -> None:
    """עם is "with" and "people", and a gloss with no sentence behind it is a guess at
    which one the reader needs. The sentence goes to the model with the form; the form
    goes alone where there is none; and the answer is still filed under the lemma, so
    the second text is as cheap as it was."""
    assert entries_for(["עם", "בית"], {"עם": "  וַיֵּצֵא   עִם\nהָעָם "}) == (
        "form: עם\nin: וַיֵּצֵא עִם הָעָם\n\nform: בית"
    )
    assert entries_for(["בית"]) == "form: בית"


def test_looking_one_word_up_carries_its_sentence_and_is_free_the_second_time(
    tmp_path,  # type: ignore[no-untyped-def]
) -> None:
    class Contextual(FakeGlosses):
        def __init__(self) -> None:
            super().__init__()
            self.contexts: list[dict[str, str] | None] = []

        def gloss(self, lemmas, source_language, target_language, on_progress=None, contexts=None):  # type: ignore[no-untyped-def]
            self.contexts.append(dict(contexts) if contexts else None)
            return super().gloss(lemmas, source_language, target_language, on_progress)

    cache = Cache(tmp_path)
    provider = Contextual()
    assert (
        gloss_one("עם", "he", "en", provider, cache=cache, context="ויצא עם העם") == "meaning of עם"
    )
    assert provider.contexts == [{"עם": "ויצא עם העם"}]
    # Cached under the lemma alone: met again in another sentence, nothing is asked.
    assert (
        gloss_one("עם", "he", "en", provider, cache=cache, context="עם ישראל חי") == "meaning of עם"
    )
    assert provider.asked == [["עם"]]
    # And a word with no sentence behind it is asked for the old way.
    gloss_one("בית", "he", "en", provider, cache=cache)
    assert provider.contexts == [{"עם": "ויצא עם העם"}, None]


def test_unrated_words_are_still_worth_glossing() -> None:
    from targum.models import Annotation, Token

    annotation = Annotation(
        document_hash="h",
        language="la",
        annotator="t",
        method="none",
        method_note="n",
        tokens={"s1": [Token(start=0, end=6, surface="Gallia", lemma="gallia", band=0)]},
    )
    assert unique_lemmas(annotation) == ["gallia"]


def test_frequency_bands_know_what_they_cannot_rate() -> None:
    bands = FrequencyBands()
    assert bands.supports("he") and bands.supports("ru") and bands.supports("en")
    assert not bands.supports("la")
    assert bands.band("gallia", "la") == 0


# --- Hebrew verbs: root and binyan, worked out here rather than bought -------


def test_binyan_is_read_off_the_features_stanza_already_produced() -> None:
    assert binyan_of("Gender=Masc|HebBinyan=HITPAEL|Number=Sing") == "התפעל"
    assert binyan_of("Gender=Masc|Number=Sing|Tense=Past") is None
    assert binyan_of(None) is None


@pytest.mark.parametrize(
    ("lemma", "binyan", "root"),
    [
        ("כתב", "פעל", "כתב"),
        ("בנה", "פעל", "בנה"),
        ("נכתב", "נפעל", "כתב"),
        ("דיבר", "פיעל", "דבר"),
        ("כיסה", "פיעל", "כסה"),
        ("דובר", "פועל", "דבר"),
        ("הסביר", "הפעיל", "סבר"),
        ("הוסבר", "הופעל", "סבר"),
        ("התלבש", "התפעל", "לבש"),
        # The ת of התפעל swaps places with a sibilant, and turns into a ד after ז.
        ("השתמש", "התפעל", "שמש"),
        ("הזדקן", "התפעל", "זקן"),
        ("הצטלם", "התפעל", "צלם"),
        # A final letter is written as one: the root of הזמין is ז־מ־ן, not ז־מ־נ.
        ("הזמין", "הפעיל", "זמן"),
        # A root that begins with י writes it as a ו in הפעיל.
        ("הוריש", "הפעיל", "ירש"),
        ("הודיע", "הפעיל", "ידע"),
        ("שילם", "פיעל", "שלם"),
    ],
)
def test_the_root_behind_a_regular_verb(lemma: str, binyan: str, root: str) -> None:
    assert root_of(lemma, binyan) == root


@pytest.mark.parametrize(
    ("lemma", "binyan"),
    [
        # Hollow roots keep their middle letter nowhere in the written form: קם is
        # ק־ו־ם and no rule recovers the ו.
        ("קם", "פעל"),
        ("בא", "פעל"),
        # הקים is ק־ו־ם and הגיש is נ־ג־ש. The same three letters, two different
        # roots, and nothing in the spelling to tell them apart.
        ("הקים", "הפעיל"),
        ("הגיש", "הפעיל"),
        ("הבין", "הפעיל"),
    ],
)
def test_a_root_that_cannot_be_had_is_not_invented(lemma: str, binyan: str) -> None:
    """A gap is a gap. Pealim answers it; a confident wrong root does not."""
    assert root_of(lemma, binyan) is None


def test_no_binyan_means_no_root() -> None:
    assert root_of("כתב", None) is None
    assert root_of("", "פעל") is None


def in_segments(lemmas: dict[str, list[str]]) -> Annotation:
    """An annotation where each segment has its own words."""
    return Annotation(
        document_hash="h",
        language="he",
        annotator="t",
        method="frequency",
        method_note="n",
        tokens={
            segment: [Token(start=0, end=1, surface=lemma, lemma=lemma, band=3) for lemma in words]
            for segment, words in lemmas.items()
        },
    )


def test_only_narrows_the_lookup_to_what_is_being_bought() -> None:
    """Meanings are the expensive half of a build. Looking them up for a whole novel
    when one chapter of it was bought is what made a long book cost more than the cap
    allowed, so it could never be opened at all."""
    annotation = in_segments({"s1": ["ארץ"], "s2": ["שלום"], "s3": ["מלך"]})

    assert sorted(unique_lemmas(annotation)) == ["ארץ", "מלך", "שלום"]
    assert unique_lemmas(annotation, only={"s1"}) == ["ארץ"]
    assert sorted(unique_lemmas(annotation, only={"s1", "s3"})) == ["ארץ", "מלך"]


def test_a_build_pays_only_for_the_chapter_it_bought(tmp_path) -> None:  # type: ignore[no-untyped-def]
    cache = Cache(tmp_path / "cache")
    provider = FakeGlosses()
    annotation = in_segments({"s1": ["ארץ"], "s2": ["שלום"], "s3": ["מלך"]})

    glossary, paid = build_glossary(annotation, "en", provider, only={"s1"}, cache=cache)
    assert paid == 1
    assert list(glossary.entries) == ["ארץ"]

    # And the rest arrives when the rest is bought.
    _, later = build_glossary(annotation, "en", provider, only={"s1", "s2"}, cache=cache)
    assert later == 1


def test_a_lemma_already_looked_up_is_not_quoted_for(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Glosses are cached per lemma across every text, so most of a second Hebrew book
    is already bought. Quoting for it prices work that is about to be free."""
    from targum.annotate.gloss import unpaid

    cache = Cache(tmp_path / "cache")
    provider = FakeGlosses()
    assert unpaid(["ארץ", "שלום"], "he", "en", provider.name, cache) == ["ארץ", "שלום"]

    build_glossary(annotation_with({"ארץ": 2}), "en", provider, cache=cache)

    assert unpaid(["ארץ", "שלום"], "he", "en", provider.name, cache) == ["שלום"]


def test_filling_from_the_cache_buys_nothing(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """A card should open with a meaning targum already holds, not with a button. That
    means handing over what the cache has for a text whose meanings were never bought —
    without buying the rest."""
    from targum.cache import Cache

    cache = Cache(tmp_path)
    paid = FakeGlosses()
    build_glossary(annotation_with({"ארץ": 2}), "en", paid, cache=cache)
    assert len(paid.asked) == 1

    quiet = FakeGlosses()
    held, owed = build_glossary(
        annotation_with({"ארץ": 2, "שלום": 1}), "en", quiet, cache=cache, buy=False
    )
    assert quiet.asked == [], "buy=False means buy nothing"
    assert held.entries == {"ארץ": "meaning of ארץ"}
    assert owed == 1, "and says what it would have cost"


def test_a_rebuild_fills_a_reader_from_the_cache(tmp_path) -> None:  # type: ignore[no-untyped-def]
    from targum.annotate.gloss import fill_from_cache, gloss_key, gloss_provider_name
    from targum.cache import Cache

    cache = Cache(tmp_path)
    annotation = annotation_with({"ארץ": 2, "שלום": 1})
    cache.put(
        "gloss",
        gloss_key(cache, "ארץ", annotation.language, "en", gloss_provider_name()),
        {"gloss": "land", "part_of_speech": "noun"},
    )
    grown = fill_from_cache(annotation, {}, ["en"], cache=cache)
    assert grown["en"].entries == {"ארץ": "land"}
    assert grown["en"].parts_of_speech == {"ארץ": "noun"}
    again = fill_from_cache(annotation, grown, ["en"], cache=cache)
    assert again == {}, "nothing new, nothing written"
