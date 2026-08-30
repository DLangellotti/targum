"""Difficulty bands and glosses, against fake components so the suite stays offline."""

from __future__ import annotations

from pathlib import Path

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


def test_scripture_and_the_rest_are_read_with_different_tokenizers() -> None:
    """Stanza's default Hebrew tokenizer hands שרוצים over whole, and the lemmatizer then
    returns שרץ: a modern dialogue banded hard and told it was quoting Leviticus. The build
    with a character model behind it splits the clitic, and is worse on the Tanakh, whose
    band table was counted with the default. So the source decides, the way it does for
    the bands — and the scripture name is the old name, so no Tanakh is redone."""
    from targum.annotate.lemma import MODERN_TOKENIZERS, StanzaLemmatizer, for_source

    tanakh = for_source("sefaria:Ruth")
    dialogue = for_source("dialogue:08-that-is-my-spot")
    assert tanakh.scripture and not dialogue.scripture
    assert tanakh.packages("he") == {}
    assert dialogue.packages("he") == {"tokenize": MODERN_TOKENIZERS["he"]}
    assert dialogue.packages("iw") == dialogue.packages("he"), "the same language"
    assert dialogue.packages("ru") == {}, "only Hebrew has a second build to choose"
    assert tanakh.name == StanzaLemmatizer(scripture=True).name
    assert dialogue.name != tanakh.name, "a modern text built before is read again"
    assert dialogue.name.startswith(tanakh.name), "and the old name is still in it"
    assert StanzaLemmatizer().name == dialogue.name, "the default is the modern reading"


def test_a_named_build_is_missing_until_that_file_is_on_disk(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Any tokenizer on disk used to mean the tokenizer was on disk, and a machine with
    the default build would then fail to load the named one and be told to fetch what it
    already had."""
    from targum.segment import has_processors

    monkeypatch.setenv("TARGUM_MODEL_DIR", str(tmp_path))
    for processor, build in (("tokenize", "combined_nocharlm"), ("pos", "x"), ("lemma", "x")):
        (tmp_path / "he" / processor).mkdir(parents=True)
        (tmp_path / "he" / processor / f"{build}.pt").write_bytes(b"")
    assert has_processors("he", "tokenize,pos,lemma")
    assert not has_processors("he", "tokenize,pos,lemma", {"tokenize": "combined_charlm"})
    (tmp_path / "he" / "tokenize" / "combined_charlm.pt").write_bytes(b"")
    assert has_processors("he", "tokenize,pos,lemma", {"tokenize": "combined_charlm"})


@pytest.mark.stanza
def test_a_modern_verb_behind_a_clitic_is_not_a_rare_biblical_word(
    needs_hebrew_model: None,
) -> None:
    """שֶׁרוֹצִים in a dialogue is ש + רוצים, "that they want". Read whole it became שרץ,
    "to swarm": hard, rooted שר״ץ, and "from the Tanakh, rare today"."""
    from targum.annotate.lemma import PROCESSORS, for_source
    from targum.segment import has_processors

    lemmatizer = for_source("dialogue:08-that-is-my-spot")
    if not has_processors("he", PROCESSORS, lemmatizer.packages("he")):
        pytest.skip("Hebrew lemmatizer not downloaded")

    segmented = document(["קוראים לזה איך שרוצים."])
    annotation = Annotator(lemmatizer=lemmatizer).annotate(segmented)
    tokens = {token.surface: token for token in next(iter(annotation.tokens.values()))}
    assert tokens["שרוצים"].lemma == "רצה"
    assert tokens["שרוצים"].split
    assert tokens["שרוצים"].word_register != "biblical"
    assert tokens["שרוצים"].band <= 2


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


# -- every word is a word ---------------------------------------------------------


class Word:
    """The shape of a Stanza word, as `_content_word` reads it."""

    def __init__(self, upos: str, text: str, lemma: str | None = None) -> None:
        self.upos = upos
        self.text = text
        self.lemma = text if lemma is None else lemma
        self.feats = None


def _lemma(*words: Word) -> str | None:
    from targum.annotate.lemma import _content_word

    chosen = _content_word(list(words))
    return None if chosen is None else chosen.lemma


def test_a_prefixed_name_keeps_the_name_and_not_the_prefix() -> None:
    """הַמֶּלֶךְ is ה + PROPN to Stanza, which tags titles and definite nouns that way all the
    time. Dropping the PROPN before choosing left the lemma of "the king" as ה — so one
    press of `k` on it marked every הָעִיר and הַפּוּר in the language known at once. That
    was the alpha reader's "why are some words already marked as known?"."""
    assert _lemma(Word("DET", "ה"), Word("PROPN", "מלך")) == "מלך"
    assert _lemma(Word("CCONJ", "ו"), Word("PROPN", "אסתר")) == "אסתר"


def test_a_spelled_out_numeral_is_a_word() -> None:
    assert _lemma(Word("NUM", "שמונים")) == "שמונים"


def test_a_prefixed_numeral_is_not_a_preposition() -> None:
    assert _lemma(Word("ADP", "ב"), Word("NUM", "1948")) == "1948"


def test_a_garbage_token_never_outranks_a_real_noun() -> None:
    """X is what Stanza says when it cannot say. It is outside FUNCTION_POS, so on length
    alone a scrap of it would beat the noun beside it."""
    assert _lemma(Word("NOUN", "ספר"), Word("X", "xxxxxxxx")) == "ספר"
    assert _lemma(Word("X", "xxxxxxxx")) == "xxxxxxxx", "but alone it is still a token"


def test_punctuation_alone_is_not_a_token() -> None:
    assert _lemma(Word("PUNCT", ".")) is None
    assert _lemma(Word("PUNCT", "—"), Word("SYM", "§")) is None


def test_the_annotator_name_changed_so_old_annotations_are_redone() -> None:
    """The name is the whole invalidation mechanism: the pipeline compares it and redoes
    an annotation for free, and SCHEMA_VERSION is never bumped for a word-level change."""
    from targum.annotate.lemma import FEATURES, StanzaLemmatizer

    assert "everyword" in FEATURES
    assert FEATURES in StanzaLemmatizer().name


def test_a_token_records_its_part_of_speech() -> None:
    """Read by nothing in the reader; it is how a difficulty count leaves names out."""
    from targum.models import Token

    token = Token(start=0, end=3, surface="מלך", lemma="מלך", band=0)
    assert token.pos is None, "absent on annotations written before it existed"
    assert Token(start=0, end=3, surface="מלך", lemma="מלך", band=0, pos="PROPN").pos == "PROPN"


def test_names_do_not_count_toward_difficulty(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Every name in a chronicle is rare by corpus frequency, and counting them would move
    Esther a shelf up the library. A name is a token the reader can tap, not a word they
    have to learn."""
    pytest.importorskip("wordfreq")
    from targum.serve import Library

    def token(lemma: str, pos: str) -> Token:
        return Token(start=0, end=1, surface=lemma, lemma=lemma, band=0, pos=pos)

    common = [token("של", "ADP"), token("היה", "VERB"), token("לא", "PART")]
    names = [token("אחשורוש", "PROPN"), token("ושתי", "PROPN"), token("שמונים", "NUM")]
    annotation = Annotation(
        document_hash="h",
        language="he",
        annotator="t",
        method="frequency",
        method_note="",
        tokens={"s1": common + names},
    )
    path = tmp_path / "annotation.json"
    annotation.write(path)
    assert Library._own_difficulty(str(path), 1.0, "he") == 0, "three everyday words"

    # Counted the old way the names would be looked up, and the text would be a third
    # "hard" — the number the alpha reader's shelf used to show.
    counted = [t.model_copy(update={"pos": None}) for t in common + names]
    Annotation(
        document_hash="h",
        language="he",
        annotator="t",
        method="frequency",
        method_note="",
        tokens={"s1": counted},
    ).write(path)
    assert Library._own_difficulty(str(path), 2.0, "he") > 0


def test_the_lemma_cache_is_rewritten_when_the_annotation_is() -> None:
    """The cache used to be a bare list that outlived every rewrite of the annotation
    beside it. After `rebuild --words` half the shelf would have reported a denominator a
    tenth too small, with nothing to say so."""
    import json
    import os
    import tempfile
    from pathlib import Path

    from targum.coverage import LEMMAS, lemmas

    with tempfile.TemporaryDirectory() as raw:
        folder = Path(raw)
        note = folder / "annotation.json"
        note.write_text(json.dumps({"tokens": {"s": [{"lemma": "א"}, {"lemma": "ב"}]}}))
        assert lemmas(folder) == ["א", "ב"]
        assert isinstance(json.loads((folder / LEMMAS).read_text())["stamp"], list)

        note.write_text(
            json.dumps({"tokens": {"s": [{"lemma": "א"}, {"lemma": "ב"}, {"lemma": "ג"}]}})
        )
        os.utime(note, ns=(note.stat().st_atime_ns, note.stat().st_mtime_ns + 1))
        assert lemmas(folder) == ["א", "ב", "ג"], "a rewritten annotation is read again"

        # A cache from before the stamp existed is stale by definition.
        (folder / LEMMAS).write_text(json.dumps(["stale"]))
        assert lemmas(folder) == ["א", "ב", "ג"]


class NamingLemmatizer(FakeLemmatizer):
    """The fake above, with one word tagged as a name."""

    name = "fake-lemma/2"

    def lemmas(self, segments, language):  # type: ignore[no-untyped-def]
        out = super().lemmas(segments, language)
        for tokens in out.values():
            for index, token in enumerate(tokens):
                if token.lemma == "אסתר":
                    tokens[index] = token.model_copy(update={"pos": "PROPN"})
        return out


def test_a_name_has_no_difficulty() -> None:
    """Rated by corpus frequency, every name in a chronicle is "extremely hard". It has no
    difficulty at all: it is a token to tap, not a word to learn."""
    from targum.annotate import UNRATED
    from targum.models import BlockKind, Segment, SegmentedDocument

    segment = Segment(
        id="s", block_id="b", block_index=0, index=0, text="אסתר נערה", kind=BlockKind.paragraph
    )
    document = SegmentedDocument(
        document_hash="h", language="he", segmenter="t", segments=[segment]
    )
    annotation = Annotator(lemmatizer=NamingLemmatizer(), bands=FakeBands()).annotate(document)
    by_lemma = {token.lemma: token for token in annotation.tokens["s"]}
    assert by_lemma["אסתר"].band == UNRATED
    assert by_lemma["נערה"].band > 0


def test_a_name_is_not_in_the_lemma_count() -> None:
    """The shelf's "% of its words you know" divides by the distinct lemmas; a book of
    names could never be read if they were in the denominator."""
    import json
    import tempfile
    from pathlib import Path

    from targum.coverage import lemmas

    with tempfile.TemporaryDirectory() as raw:
        folder = Path(raw)
        tokens = [
            {"lemma": "מלך"},
            {"lemma": "אסתר", "pos": "PROPN"},
            {"lemma": "שבע", "pos": "NUM"},
        ]
        (folder / "annotation.json").write_text(json.dumps({"tokens": {"s": tokens}}))
        assert lemmas(folder) == ["מלך"]


# --- register ----------------------------------------------------------------


def test_the_register_is_recorded_beside_the_band() -> None:
    """Real Hebrew, because the point of the field is the two real corpora behind it.

    זבח is everywhere in the Tanakh and has left the street; אוטובוס is on every street
    and is not in the Tanakh; בית is in both and so has nothing to say for itself.
    """
    annotation = annotator().annotate(document(["זבח אוטובוס בית"]))
    (tokens,) = annotation.tokens.values()
    assert [token.word_register for token in tokens] == ["biblical", "modern", None]


def test_a_name_has_no_register() -> None:
    """A name is not vocabulary, which is already why it has no band.

    The same word tagged PROPN, so the only thing that changed is whether it is a word
    the reader has to learn. אוטובוס is modern Hebrew as a word and says nothing as a
    name — a foreign name is not a modern Hebrew coinage for having stayed out of the
    Tanakh, and neither is a numeral.
    """
    from targum.annotate import register

    class Named(FakeLemmatizer):
        """Everything is a name here, which is what a chronicle of them looks like."""

        def lemmas(self, segments, language):  # type: ignore[no-untyped-def]
            found = super().lemmas(segments, language)
            return {
                sid: [token.model_copy(update={"pos": "PROPN"}) for token in tokens]
                for sid, tokens in found.items()
            }

    assert register.of("אוטובוס", "he") == "modern", "the lexicon would say so"
    annotation = Annotator(lemmatizer=Named(), bands=FakeBands()).annotate(document(["אוטובוס"]))
    (tokens,) = annotation.tokens.values()
    assert tokens[0].word_register is None
    assert tokens[0].band == 0, "and no band either, for the same reason"


def test_a_language_with_no_second_register_is_not_asked() -> None:
    annotation = annotator().annotate(document(["mundus"], language="la"))
    (tokens,) = annotation.tokens.values()
    assert all(token.word_register is None for token in tokens)


def test_the_annotator_is_named_for_the_register_too() -> None:
    """Which is what makes a text built before this get built again — free, since this
    runs on the machine doing the reading. `SCHEMA_VERSION` would have cost a library
    of re-translation to do the same job."""
    from targum.annotate import register

    assert register.NAME in annotator().name
