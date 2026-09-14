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


def test_the_question_is_version_two_and_names_the_features() -> None:
    """Prompt 2 asks the grammar; a stored prompt-1 row is under another key and is read
    again rather than shown without it."""
    assert model_lemma.provider_name().endswith("/2")
    assert "Case (Nom Gen Dat Acc Ins Loc Par Voc)" in model_lemma.SYSTEM
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
