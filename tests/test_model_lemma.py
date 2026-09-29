"""Words read by the model, for the languages no clean tagger reads (2026-09-13).

Offline: the model is a fake that answers from a table. What is under test is what the
code around it does — where offsets come from, what is cached, and that nothing is bought
without a press.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from targum.annotate import model_lemma
from targum.annotate.model_lemma import ModelLemmatizer
from targum.cache import Cache
from targum.errors import TargumError
from targum.models import BlockKind, Segment


def segment(n: int, text: str) -> Segment:
    return Segment(
        id=f"0000.{n:03d}-x",
        block_id="b0000",
        block_index=0,
        index=n,
        kind=BlockKind.paragraph,
        text=text,
    )


@dataclass
class Answer:
    text: str
    stop_reason: str = "end_turn"
    input_tokens: int = 100
    output_tokens: int = 50

    @property
    def content(self) -> list[Any]:
        return [type("Block", (), {"text": self.text})()]

    @property
    def usage(self) -> Any:
        return type(
            "Usage", (), {"input_tokens": self.input_tokens, "output_tokens": self.output_tokens}
        )()


#: What the fake "knows": a surface form's lemma and tag.
LEXICON = {
    "Le": ("le", "DET"),
    "chat": ("chat", "NOUN"),
    "dort": ("dormir", "VERB"),
    "l'": ("le", "DET"),
    "homme": ("homme", "NOUN"),
    "mange": ("manger", "VERB"),
    "Paris": ("Paris", "PROPN"),
    "Кошка": ("кошка", "NOUN"),
    "спит": ("спать", "VERB"),
}


@dataclass
class FakeModel:
    """Answers each numbered segment a line per word it knows, in order."""

    asked: list[str] = field(default_factory=list)
    cut_after: int | None = None

    def client(self) -> Any:
        return self

    @property
    def messages(self) -> Any:
        return self

    def available(self) -> tuple[bool, str]:
        return True, "fake"

    def create(self, **kwargs: Any) -> Answer:
        body = kwargs["messages"][0]["content"]
        self.asked.append(body)
        lines: list[str] = []
        for chunk in body.split("\n\n"):
            number, _, text = chunk.partition(". ")
            for word in text.replace("l'", "l' ").replace(".", " ").split():
                if word in LEXICON:
                    lemma, pos = LEXICON[word]
                    lines.append(f"{number}\t{word}\t{lemma}\t{pos}")
        if self.cut_after is not None and len(lines) > self.cut_after:
            return Answer("\n".join(lines[: self.cut_after]), stop_reason="max_tokens")
        return Answer("\n".join(lines))


def reader(tmp_path: Path, fake: FakeModel, **kwargs: Any) -> ModelLemmatizer:
    lemmatizer = ModelLemmatizer(cache=Cache(tmp_path / "cache"), **kwargs)
    lemmatizer._provider = fake
    return lemmatizer


def test_offsets_are_found_in_the_text_and_never_trusted() -> None:
    text = "Le chat dort. L'homme mange à Paris."
    answer = "\n".join(
        [
            "1\tLe\tle\tDET",
            "1\tchat\tchat\tNOUN",
            "1\tdort\tdormir\tVERB",
            "1\t.\t.\tPUNCT",
            # Spelled differently from the text: dropped, not put over the wrong letters.
            "1\tmangé\tmanger\tVERB",
            "1\tL'\tle\tDET",
            "1\thomme\thomme\tNOUN",
            "1\tmange\tmanger\tVERB",
            "1\tParis\tParis\tPROPN",
            "not a line",
        ]
    )
    [tokens] = model_lemma.parse(answer, [text])
    assert tokens is not None
    assert [(t.surface, t.lemma, t.pos) for t in tokens] == [
        ("Le", "le", "DET"),
        ("chat", "chat", "NOUN"),
        ("dort", "dormir", "VERB"),
        ("L'", "le", "DET"),
        ("homme", "homme", "NOUN"),
        ("mange", "manger", "VERB"),
        ("Paris", "Paris", "PROPN"),
    ]
    assert all(text[t.start : t.end] == t.surface for t in tokens)
    assert model_lemma.parse("", ["Le chat."]) == [None], "never mentioned is not empty"
    # The segment number sometimes arrives with the word's place after it.
    [placed] = model_lemma.parse("1.1\tLe\tle\tDET\n1.2\tchat\tchat\tNOUN", ["Le chat."])
    assert placed is not None and [t.surface for t in placed] == ["Le", "chat"]


def test_a_curly_apostrophe_places_a_straight_one() -> None:
    """French and Italian are written with ’ and the model often answers with ': the
    article is placed all the same, spelled as the text spells it (targum-internal#262)."""
    text = "L’homme mange à l’école."
    answer = "\n".join(
        [
            "1\tL'\tle\tDET",
            "1\thomme\thomme\tNOUN",
            "1\tmange\tmanger\tVERB",
            "1\tà\tà\tADP",
            "1\tl'\tle\tDET",
            "1\técole\técole\tNOUN",
            "1\t.\t.\tPUNCT",
        ]
    )
    [tokens] = model_lemma.parse(answer, [text], "fr")
    assert tokens is not None
    assert [t.surface for t in tokens] == ["L’", "homme", "mange", "à", "l’", "école"]
    assert all(text[t.start : t.end] == t.surface for t in tokens)
    # And the other way round, with the modifier letter the Italian texts sometimes carry.
    [back] = model_lemma.parse("1\tdell’\tdi\tADP\n1\tanno\tanno\tNOUN", ["dellʼanno"], "it")
    assert back is not None and [t.surface for t in back] == ["dellʼ", "anno"]


def test_a_word_is_never_placed_inside_another() -> None:
    """The model wrote `de` for `d’`, and it was found inside *solde* further on, which
    lost every word between. A bare `l` takes the apostrophe the text gives it."""
    text = "au cours d’une année due au solde naturel"
    answer = "\n".join(
        [
            "1\tau\tà\tADP",
            "1\tcours\tcours\tNOUN",
            "1\tde\tde\tADP",
            "1\tune\tun\tDET",
            "1\tannée\tannée\tNOUN",
            "1\tdue\tdû\tADJ",
        ]
    )
    [tokens] = model_lemma.parse(answer, [text], "fr")
    assert tokens is not None
    assert [t.surface for t in tokens] == ["au", "cours", "une", "année", "due"]
    [bare] = model_lemma.parse("1\tl\tle\tDET\n1\tallure\tallure\tNOUN", ["prend l’allure"], "fr")
    assert bare is not None and [t.surface for t in bare] == ["l’", "allure"]


def test_nothing_is_bought_without_a_press(tmp_path: Path) -> None:
    """Every lemmatizer reads from the cache alone unless it was made to buy. Pricing a
    card, repairing a paragraph and rebuilding a shelf all make it that way."""
    fake = FakeModel()
    words = reader(tmp_path, fake).lemmas([segment(0, "Le chat dort.")], "fr")
    assert fake.asked == [] and words == {}

    bought = reader(tmp_path, fake, buy=True)
    first = bought.lemmas([segment(0, "Le chat dort.")], "fr")
    assert len(fake.asked) == 1 and [t.lemma for t in first["0000.000-x"]] == [
        "le",
        "chat",
        "dormir",
    ]
    assert bought.spent.calls == 1 and bought.spent.cost() > 0

    again = reader(tmp_path, fake).lemmas([segment(0, "Le chat dort.")], "fr")
    assert len(fake.asked) == 1, "read once, kept"
    assert again == first


def test_a_build_buys_only_the_chapters_it_is_buying(tmp_path: Path) -> None:
    fake = FakeModel()
    first, second = segment(0, "Le chat dort."), segment(1, "L'homme mange.")
    words = reader(tmp_path, fake, buy=True, allowed={first.id}).lemmas([first, second], "fr")
    assert set(words) == {first.id}
    assert "homme" not in fake.asked[0]


def test_an_answer_cut_off_is_asked_again_in_halves(tmp_path: Path) -> None:
    fake = FakeModel(cut_after=3)
    segments = [
        segment(n, text)
        for n, text in enumerate(["Le chat dort.", "L'homme mange.", "Кошка спит."])
    ]
    words = reader(tmp_path, fake, buy=True).lemmas(segments, "fr")
    assert len(fake.asked) > 1
    assert set(words) == {s.id for s in segments}


def test_a_run_that_fails_partway_keeps_what_it_paid_for(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A book is an hour of batches. When one call failed — credit ran out at 11:41 on
    2026-09-14 — every batch already answered was thrown away with it, about $3. Kept as
    each batch returns, the rerun asks only for the batches that never came back."""
    from targum.errors import ProviderError

    class FailsOnSecond(FakeModel):
        def create(self, **kwargs: Any) -> Answer:
            if len(self.asked) == 1:
                self.asked.append(kwargs["messages"][0]["content"])
                raise ProviderError("Anthropic API error 400 while reading the words.")
            return super().create(**kwargs)

    monkeypatch.setattr(model_lemma, "BATCH_SEGMENTS", 1)
    first, second = segment(0, "Le chat dort."), segment(1, "L'homme mange.")
    failing = FailsOnSecond()
    with pytest.raises(ProviderError):
        reader(tmp_path, failing, buy=True).lemmas([first, second], "fr")
    assert len(failing.asked) == 2

    # Read from the cache alone: the first batch is there, under the key it always had.
    kept = reader(tmp_path, FakeModel()).lemmas([first, second], "fr")
    assert set(kept) == {first.id}

    fresh = FakeModel()
    words = reader(tmp_path, fresh, buy=True).lemmas([first, second], "fr")
    assert set(words) == {first.id, second.id}
    assert len(fresh.asked) == 1
    assert "homme" in fresh.asked[0] and "chat" not in fresh.asked[0]


def test_a_language_it_does_not_read_is_refused(tmp_path: Path) -> None:
    with pytest.raises(TargumError, match="does not read"):
        reader(tmp_path, FakeModel(), buy=True).lemmas([segment(0, "שלום עולם.")], "he")


def test_the_price_is_quoted_net_of_what_is_read(tmp_path: Path) -> None:
    cache = Cache(tmp_path / "cache")
    segments = [segment(0, "Le chat dort."), segment(1, "L'homme mange."), segment(2, "123")]
    owed = model_lemma.unpaid(segments, "fr", model_lemma.provider_name(), cache)
    assert [s.id for s in owed] == [segments[0].id, segments[1].id], "nothing to read in 123"
    assert model_lemma.estimate(owed, "fr") > 0 and model_lemma.estimate([], "fr") == 0.0
    fake = FakeModel()
    lemmatizer = ModelLemmatizer(cache=cache, buy=True)
    lemmatizer._provider = fake
    lemmatizer.lemmas(segments[:1], "fr")
    assert model_lemma.unpaid(segments, "fr", model_lemma.provider_name(), cache) == [segments[1]]


def test_hebrew_keeps_its_chain_and_its_name() -> None:
    """The Hebrew annotator's name embeds its delegate's, so routing Hebrew through anything
    new would read the whole shelf again. `for_text` only adds the model's languages."""
    from targum.annotate.lemma import for_source, for_text

    assert for_text("sefaria:Ruth", "he").name == for_source("sefaria:Ruth").name
    assert for_text("x.md", "he-IL").name == for_source("x.md").name
    for language in ("fr", "ru", "it", "yi"):
        chosen = for_text("x.md", language)
        assert isinstance(chosen, ModelLemmatizer) and chosen.buy is False
    assert for_text("x.md", "fr", buy=True).buy is True


def test_the_grammar_comes_with_the_word() -> None:
    """A fifth column of features, kept only from the list a card can say something with,
    written in one order whatever order the model used (targum-internal#258)."""
    text = "Он взял её руку."
    answer = "\n".join(
        [
            "1\tОн\tон\tPRON\tPerson=3|Gender=Masc|Number=Sing|Case=Nom",
            "1\tвзял\tвзять\tVERB\tTense=Past|Aspect=Perf|Gender=Masc|Number=Sing|VerbForm=Fin",
            # Invented features and values are dropped rather than shipped.
            "1\tеё\tона\tDET\tCase=Acc|Poss=Yes|Gender=Hmm",
            "1\tруку\tрука\tNOUN\tNumber=Sing|Case=Acc|Gender=Fem|Animacy=Inan",
        ]
    )
    [tokens] = model_lemma.parse(answer, [text])
    assert tokens is not None
    assert [t.feats for t in tokens] == [
        "UPOS=PRON|Case=Nom|Gender=Masc|Number=Sing|Person=3",
        "UPOS=VERB|Gender=Masc|Number=Sing|Aspect=Perf|Tense=Past|VerbForm=Fin",
        "UPOS=DET|Case=Acc",
        "UPOS=NOUN|Case=Acc|Gender=Fem|Number=Sing|Animacy=Inan",
    ]
    # An answer that left the column off still has its words, with only the tag.
    [bare] = model_lemma.parse("1\tОн\tон\tPRON\n1\tвзял\tвзять\tVERB\t_", [text])
    assert bare is not None and [t.feats for t in bare] == ["UPOS=PRON", "UPOS=VERB"]


def test_the_grammar_is_kept_with_the_words(tmp_path: Path) -> None:
    fake = FakeModel()
    first = reader(tmp_path, fake, buy=True).lemmas([segment(0, "Кошка спит.")], "ru")
    again = reader(tmp_path, fake).lemmas([segment(0, "Кошка спит.")], "ru")
    assert len(fake.asked) == 1 and again == first
    assert [t.feats for t in again["0000.000-x"]] == ["UPOS=NOUN", "UPOS=VERB"]


def test_the_question_is_version_three_and_names_the_features() -> None:
    """Prompt 3 lets the imparfait be said and asks a French clitic's role
    (targum-internal#264); a stored prompt-2 row is under another key."""
    assert model_lemma.provider_name().endswith("/3")
    assert "Case (Nom Gen Dat Acc Ins Loc Par Voc)" in model_lemma.SYSTEM
    assert "Tense (Past Pres Fut Imp)" in model_lemma.SYSTEM
    assert "Role (Obj Iobj En Y Refl)" in model_lemma.SYSTEM
    for name in model_lemma.FEATURES:
        assert name in model_lemma.SYSTEM


def test_a_language_keeps_only_the_grammar_it_has() -> None:
    """French has no case to show, and the model's case for a French pronoun was measured
    to be a guess; Yiddish has case and no aspect."""
    line = "Case=Acc|Gender=Fem|Number=Sing|Aspect=Perf|Animacy=Anim"
    assert model_lemma.features(line, "PRON", "fr") == "UPOS=PRON|Gender=Fem|Number=Sing"
    assert model_lemma.features(line, "NOUN", "yi") == "UPOS=NOUN|Case=Acc|Gender=Fem|Number=Sing"
    assert model_lemma.features(line, "NOUN", "ru") == (
        "UPOS=NOUN|Case=Acc|Gender=Fem|Number=Sing|Animacy=Anim|Aspect=Perf"
    )


def test_the_imparfait_is_kept_and_a_role_only_in_french() -> None:
    """*mangeait* is `Tense=Imp` from prompt 3; a role is kept on a French pronoun and
    dropped from an Italian or a Russian one, where nothing asked for it."""
    assert model_lemma.features("Tense=Imp|Person=3|Number=Sing", "VERB", "fr") == (
        "UPOS=VERB|Number=Sing|Tense=Imp|Person=3"
    )
    assert model_lemma.features("Tense=Imp", "VERB", "it") == "UPOS=VERB|Tense=Imp"
    line = "Gender=Masc|Number=Sing|Person=3|Role=Obj"
    assert model_lemma.features(line, "PRON", "fr").endswith("|Person=3|Role=Obj")
    for language in ("it", "ru", "yi"):
        assert "Role" not in model_lemma.features(line, "PRON", language)


def test_a_pronoun_says_what_it_stands_for() -> None:
    """The sixth column names the words, in this segment or the one before, and they are
    kept only where the text has them: before the pronoun in its own segment, or anywhere
    in the one before. A phrase the model made up, a segment out of reach and a reflexive
    all keep nothing (targum-internal#264)."""
    texts = ["Marie a acheté le livre.", "Elle le lit et en parle à Paul, qui s’en moque."]
    answer = "\n".join(
        [
            "1\tMarie\tMarie\tPROPN\t_",
            "1\tlivre\tlivre\tNOUN\tGender=Masc|Number=Sing",
            "2\tElle\til\tPRON\tPerson=3|Gender=Fem|Number=Sing",
            "2\tle\tle\tPRON\tGender=Masc|Number=Sing|Person=3|Role=Obj\t1:le livre",
            "2\tlit\tlire\tVERB\tTense=Pres|Person=3|Number=Sing",
            "2\ten\ten\tPRON\tRole=En\t1:le roman",
            "2\tparle\tparler\tVERB\tTense=Pres",
            "2\tPaul\tPaul\tPROPN\t_",
            "2\ts’\tse\tPRON\tPerson=3|Role=Refl\t2:Paul",
            "2\ten\ten\tPRON\tRole=En\t2:Paul",
            "2\tmoque\tmoquer\tVERB\tTense=Pres",
        ]
    )
    [first, second] = model_lemma.parse(answer, texts, "fr")
    assert first is not None and second is not None
    said = {(t.surface, t.start): t.stands_for for t in second}
    assert said[("le", 5)] == (1, "le livre")
    assert said[("en", 15)] is None, "le roman is not in the text"
    assert said[("s’", 36)] is None, "a reflexive stands for its subject"
    assert said[("en", 38)] == (0, "Paul")
    [alone] = model_lemma.parse("1\tle\tle\tPRON\tRole=Obj\t0:le livre", ["Il le lit."], "fr")
    assert alone is not None and alone[0].stands_for is None, "no segment before the first"
    [italian] = model_lemma.parse(
        "1\tlo\tlo\tPRON\tRole=Obj\t1:Il\n", ["Il libro, lo leggo."], "it"
    )
    assert italian is not None and italian[0].stands_for is None


def test_what_it_stands_for_is_kept_and_settled_against_the_text(tmp_path: Path) -> None:
    """Kept in the cache as a seventh column, and settled against the segment before this
    one in the text being read: the reading is shared by every text with the sentence,
    and another text's sentence before may not name the book."""
    from targum.models import Token

    cache = Cache(tmp_path / "cache")
    text = "Je le lis."
    held = [
        Token(
            start=3,
            end=5,
            surface="le",
            lemma="le",
            band=0,
            pos="PRON",
            feats="UPOS=PRON|Role=Obj",
            stands_for=(1, "le livre"),
        ),
    ]
    provider = model_lemma.provider_name()
    cache.put(
        "lemma",
        model_lemma.key(cache, text, "fr", provider),
        {"text": text, "provider": provider, "tokens": model_lemma._stored(held)},
    )
    here = [segment(0, "Paul a le livre."), segment(1, text)]
    elsewhere = [segment(0, "Paul a la clé."), segment(1, text)]
    got = ModelLemmatizer(cache=cache).lemmas(here, "fr")
    assert got[here[1].id][0].stands_for == (1, "le livre")
    got = ModelLemmatizer(cache=cache).lemmas(elsewhere, "fr")
    assert got[elsewhere[1].id][0].stands_for is None
    assert model_lemma._restored([[3, 5, "le", "le", "PRON", "", [2, "x"]]], text) == [
        held[0].model_copy(update={"feats": None, "stands_for": None})
    ], "a row that reaches further back than one segment keeps nothing of it"


def test_an_earlier_question_still_serves_a_text_nobody_is_buying(tmp_path: Path) -> None:
    """A French text read with prompt 2 keeps its words through a rebuild, which buys
    nothing, rather than losing them to the new key; the name says it took them, so the
    page does not call its past the passé simple and the next rebuild after a re-read
    takes the new reading. A reader that is buying asks again. Prompt 1 had no grammar
    and serves nothing."""
    cache = Cache(tmp_path / "cache")
    fake = FakeModel()
    text = segment(0, "Le chat dort.")
    rows = [[0, 2, "Le", "le", "DET", "UPOS=DET"]]
    for version in (1, 2):
        provider = model_lemma.provider_name(version=version)
        cache.put(
            "lemma",
            model_lemma.key(cache, text.text, "fr", provider),
            {"text": text.text, "provider": provider, "tokens": rows},
        )

    rebuilding = ModelLemmatizer(cache=cache)
    assert rebuilding.name == model_lemma.provider_name()
    words = rebuilding.lemmas([text], "fr")
    assert [t.surface for t in words[text.id]] == ["Le"]
    assert rebuilding.name == model_lemma.provider_name() + "/with-2"
    assert not model_lemma.tenses_apart(f"{rebuilding.name}+wordfreq")

    buying = reader(tmp_path, fake, buy=True)
    bought = buying.lemmas([text], "fr")
    assert len(fake.asked) == 1 and buying.name == model_lemma.provider_name()
    assert [t.lemma for t in bought[text.id]] == ["le", "chat", "dormir"]
    assert model_lemma.tenses_apart(f"{buying.name}+wordfreq+register/2")

    first = ModelLemmatizer(cache=Cache(tmp_path / "other"))
    provider = model_lemma.provider_name(version=1)
    first.cache.put(
        "lemma",
        model_lemma.key(first.cache, text.text, "fr", provider),
        {"text": text.text, "provider": provider, "tokens": rows},
    )
    assert first.lemmas([text], "fr") == {} and first.name == model_lemma.provider_name()


def test_tenses_are_apart_only_under_the_third_question() -> None:
    assert model_lemma.tenses_apart("model-lemma/claude-haiku-4-5/3+wordfreq+register/2")
    assert not model_lemma.tenses_apart("model-lemma/claude-haiku-4-5/2+wordfreq+register/2")
    assert not model_lemma.tenses_apart("model-lemma/claude-haiku-4-5/3/with-2+wordfreq")
    assert not model_lemma.tenses_apart("dicta/1+wordfreq")
    assert not model_lemma.tenses_apart("")


def test_the_antecedent_waits_for_its_measure(monkeypatch: pytest.MonkeyPatch) -> None:
    """The card names what a pronoun stands for only at a precision of 0.9 or better, and
    nothing has measured it yet (targum-internal#264, criterion 2)."""
    assert model_lemma.ANTECEDENT_PRECISION is None and not model_lemma.antecedents_shown()
    monkeypatch.setattr(model_lemma, "ANTECEDENT_PRECISION", 0.89)
    assert not model_lemma.antecedents_shown()
    monkeypatch.setattr(model_lemma, "ANTECEDENT_PRECISION", 0.9)
    assert model_lemma.antecedents_shown()


def test_a_chapter_merged_into_an_older_reading_is_not_apart() -> None:
    """A chapter bought under prompt 3 beside chapters read under prompt 2 makes a book
    whose finite pasts are not all the passé simple, and its name says so."""
    new = "model-lemma/claude-haiku-4-5/3+wordfreq"
    old = "model-lemma/claude-haiku-4-5/2+wordfreq"
    assert model_lemma.merged(old, new) == "model-lemma/claude-haiku-4-5/3/with-2+wordfreq"
    assert not model_lemma.tenses_apart(model_lemma.merged(old, new))
    assert model_lemma.merged(new, new) == new
    assert model_lemma.merged("dicta/1+x", "dicta/2+x") == "dicta/2+x"
