"""Russian words read here (`annotate/russian.py`, targum-internal#310).

Offline, and mostly without spaCy: what is under test is the part that is targum's — which
case and aspect win, where ё goes back, which lemmatizer a Russian text is handed. The last
test reads a real sentence, and skips where the `russian` extra or Stanza's Russian
lemmatizer is not on this machine, which is CI.
"""

from __future__ import annotations

import importlib.util
from dataclasses import dataclass, field

import pytest

from targum.annotate import lemma, model_lemma, russian
from targum.annotate.model_lemma import ModelLemmatizer
from targum.annotate.russian import Analysis, RussianLemmatizer, Tagged, settle, with_yo
from targum.models import BlockKind, Segment


def noun(text: str, case: str, number: str = "Sing", **kw: object) -> Tagged:
    return Tagged(text=text, pos="NOUN", feats={"Case": case, "Number": number}, **kw)  # type: ignore[arg-type]


def test_a_subject_is_nominative_and_an_object_accusative() -> None:
    """Where the ending cannot tell them apart, the parse can, and a word agreeing with
    one takes its case."""
    words = [
        Tagged(text="новый", pos="ADJ", feats={"Case": "Acc"}, dep="amod", head=1),
        noun("дом", "Acc", dep="nsubj"),
        Tagged(text="видит", pos="VERB", feats={}, dep="ROOT"),
        noun("сад", "Nom", dep="obj", head=-1),
    ]
    got = settle(words)
    assert [said.get("Case") for said in got] == ["Nom", "Nom", None, "Acc"]
    assert words[1].feats["Case"] == "Acc", "the words themselves are not changed"


def test_a_case_the_form_cannot_be_in_is_replaced() -> None:
    """алгорифм cannot be genitive; the likeliest reading in the number given wins."""
    word = noun(
        "алгорифм",
        "Gen",
        analyses=[
            Analysis("Nom", "sing", "NOUN", 0.6),
            Analysis("Acc", "sing", "NOUN", 0.4),
            Analysis("Dat", "plur", "NOUN", 0.9),
        ],
    )
    assert settle([word])[0]["Case"] == "Nom"


def test_a_case_the_form_can_be_in_is_kept() -> None:
    word = noun(
        "руки",
        "Gen",
        analyses=[Analysis("Nom", "plur", "NOUN", 0.7), Analysis("Gen", "sing", "NOUN", 0.3)],
    )
    assert settle([word])[0]["Case"] == "Gen"


def test_a_verb_is_given_no_case_unless_it_is_a_participle() -> None:
    reading = [Analysis("Nom", "sing", "PRTF", 1.0)]
    finite = Tagged(text="читал", pos="VERB", feats={"VerbForm": "Fin"}, analyses=reading)
    participle = Tagged(text="читавший", pos="VERB", feats={"VerbForm": "Part"}, analyses=reading)
    assert "Case" not in settle([finite])[0]
    assert settle([participle])[0]["Case"] == "Nom"


def test_the_aspect_is_the_dictionarys_where_it_gives_one() -> None:
    one = Tagged(text="сказал", pos="VERB", feats={"Aspect": "Imp"}, aspects=frozenset({"perf"}))
    both = Tagged(
        text="женил", pos="VERB", feats={"Aspect": "Imp"}, aspects=frozenset({"perf", "impf"})
    )
    assert settle([one])[0]["Aspect"] == "Perf"
    assert settle([both])[0]["Aspect"] == "Imp"


def test_the_yo_goes_back_where_one_spelling_has_it() -> None:
    assert with_yo("ученый", ["учёный", "учёный"]) == "учёный"
    assert with_yo("Семен", ["семён"]) == "Семён"
    assert with_yo("дом", ["дом"]) == "дом"
    assert with_yo("весь", ["всё", "весь"]) == "весь"


def test_the_yo_stays_out_where_a_reading_is_spelled_without_it() -> None:
    """совершенный is "perfect" and совершённый "accomplished": two words, and which one
    this is is not a spelling rule's to say."""
    assert with_yo("совершенный", ["совершённый", "совершенный"]) == "совершенный"


def test_a_verb_keeps_its_own_aspect() -> None:
    """Stanza files взял under брать; the dictionary's infinitive for the form wins."""
    assert russian.own_aspect("брать", ["взять"]) == "взять"
    assert russian.own_aspect("стать", ["стать", "стать"]) == "стать"
    # Two infinitives the form could be: not a spelling rule's to choose.
    assert russian.own_aspect("печь", ["печь", "печься"]) == "печь"
    assert russian.own_aspect("делать", []) == "делать"


@dataclass
class FakeParse:
    normal_form: str
    is_known: bool = True


def test_a_word_stanza_invented_is_the_dictionarys() -> None:
    assert russian.known("барынь", [FakeParse("барыня")]) == "барыня"  # type: ignore[list-item]
    assert russian.known("барынь", [FakeParse("барынь", is_known=False)]) == "барынь"  # type: ignore[list-item]
    two = [FakeParse("стекло"), FakeParse("стечь")]
    assert russian.known("стекл", two) == "стекл"  # type: ignore[arg-type]


def test_a_name_is_its_nominative_in_its_own_case_first() -> None:
    assert russian.as_name("Герасима", [("Gen", 0.5, "герасим")], "Gen") == "Герасим"
    readings = [("Loc", 0.03, "ленор"), ("Dat", 0.03, "ленора")]
    assert russian.as_name("Ленор", readings, "Dat") == "Ленора"
    assert russian.as_name("Муму", [], "Nom") == "Муму"
    assert russian.as_name("Ростов", [("Nom", 1.0, "ростов-на-дону")], "Nom") == "Ростов-на-Дону"


def test_the_person_is_written_as_the_card_writes_it() -> None:
    assert russian.parse_feats("Number=Sing|Person=Third|Tense=Pres") == {
        "Number": "Sing",
        "Person": "3",
        "Tense": "Pres",
    }


@dataclass
class FakeToken:
    """What `pieces` reads of a spaCy token."""

    i: int
    text: str
    idx: int
    pos_: str
    whitespace_: str = " "
    dep_: str = "dep"
    morph: str = ""
    lemma_: str = ""
    head_at: int = 0
    is_space: bool = False
    sentence: list[FakeToken] = field(default_factory=list, repr=False)

    @property
    def head(self) -> FakeToken:
        return self.sentence[self.head_at]


def sentence(*words: tuple[str, str, str, int]) -> list[FakeToken]:
    """(text, part of speech, whitespace after, head) per token, offsets worked out."""
    out: list[FakeToken] = []
    at = 0
    for i, (text, pos, space, head) in enumerate(words):
        out.append(FakeToken(i, text, at, pos, space, head_at=head, lemma_=text.lower()))
        at += len(text) + len(space)
    for token in out:
        token.sentence = out
    return out


def test_a_word_with_a_hyphen_inside_is_one_word() -> None:
    """Read split, as spaCy's tagger learned, and joined afterwards: из-за takes за's
    grammar, каких-то takes каких's, and a dash between words is left alone."""
    doc = sentence(
        ("из", "ADP", "", 2),
        ("-", "PUNCT", "", 2),
        ("за", "ADP", " ", 6),
        ("каких", "DET", "", 6),
        ("-", "PUNCT", "", 3),
        ("то", "PART", " ", 3),
        ("людей", "NOUN", " ", 6),
        ("-", "PUNCT", " ", 6),
        ("вот", "PART", "", 6),
    )
    got = russian.pieces(doc)
    assert [p.text for p in got] == ["из-за", "каких-то", "людей", "-", "вот"]
    assert [p.pos for p in got] == ["ADP", "DET", "NOUN", "PUNCT", "PART"]
    assert [p.idx for p in got] == [0, 6, 15, 21, 23]
    # Heads are counted among the joined words: людей is the third.
    assert got[0].head == 2 and got[1].head == 2 and got[2].head == 2


def test_russian_goes_to_the_model_where_this_machine_cannot_read_it() -> None:
    assert model_lemma.reads("ru")
    chosen = lemma.for_text("x.md", "ru")
    assert isinstance(chosen, ModelLemmatizer) and chosen.buy is False


def test_russian_is_read_here_where_it_can_be(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(russian, "available", lambda: True)
    assert not model_lemma.reads("ru-RU")
    assert model_lemma.reads("fr"), "the other languages are the model's as before"
    assert isinstance(lemma.for_text("x.md", "ru"), RussianLemmatizer)
    # What `rebuild` and `seed` hand over: the shared chain, replaced per text.
    assert isinstance(lemma.for_language(lemma.for_source("x.md"), "ru"), RussianLemmatizer)
    assert isinstance(
        lemma.for_language(lemma.for_source("sefaria:Genesis"), "ru"), RussianLemmatizer
    )
    # A lemmatizer somebody chose is kept.
    chosen = ModelLemmatizer()
    assert lemma.for_language(chosen, "ru") is chosen
    # Hebrew keeps its chain and its name.
    assert lemma.for_text("x.md", "he").name == lemma.for_source("x.md").name


def test_the_name_says_what_read_it_before_anything_is_loaded() -> None:
    name = RussianLemmatizer().name
    assert name.startswith(f"ru-local/{russian.SPACY_MODEL}-")
    assert russian.LEMMA_PACKAGE in name and name.endswith(f"/{russian.VERSION}")


def test_a_real_sentence(monkeypatch: pytest.MonkeyPatch) -> None:
    here = all(
        importlib.util.find_spec(name) is not None
        for name in ("spacy", russian.SPACY_MODEL, "pymorphy3", "stanza")
    )
    if not here or not russian.is_fetched():
        pytest.skip("the russian extra and Stanza's Russian lemmatizer are not here")
    monkeypatch.setattr(russian, "available", lambda: True)
    text = "Учёные из-за дождя сидели в своих домах и читали книги."
    segment = Segment(
        id="0000.000-x",
        block_id="b0000",
        block_index=0,
        index=0,
        kind=BlockKind.paragraph,
        text=text,
    )
    tokens = RussianLemmatizer(auto_download=False).lemmas([segment], "ru")[segment.id]
    by = {token.surface: token for token in tokens}
    assert "." not in by and "из-за" in by
    assert by["Учёные"].lemma == "учёный"
    assert by["домах"].lemma == "дом" and "Case=Loc" in (by["домах"].feats or "")
    assert by["читали"].lemma == "читать" and "Aspect=Imp" in (by["читали"].feats or "")
    assert (by["книги"].feats or "").startswith("UPOS=NOUN|")
    for token in tokens:
        assert text[token.start : token.end] == token.surface
