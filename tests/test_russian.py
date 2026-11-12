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
from targum.annotate.russian import (
    Analysis,
    Piece,
    RussianLemmatizer,
    Tagged,
    pronoun,
    settle,
    stanza_asked,
    with_yo,
    yo_checked,
    yo_repaired,
)
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


def test_stanza_is_asked_without_the_yo() -> None:
    """Stanza's treebank never writes ё, and asked ёлке it answered блок
    (targum-internal#650). It is asked елке; the ё goes back afterwards."""

    def piece(text: str, pos: str = "NOUN") -> Piece:
        return Piece(text=text, idx=0, pos=pos, morph="", dep="", head=0, lemma=text)

    asked = stanza_asked([[piece("ёлке"), piece("Ёжик"), piece("дом")], [], [piece("всё", "")]])
    assert [[word["text"] for word in sentence] for sentence in asked] == [
        ["елке", "Ежик", "дом"],
        ["все"],
    ]
    assert asked[0][0] == {"id": 1, "text": "елке", "upos": "NOUN"}
    assert asked[1][0]["upos"] == "X"


def test_a_yo_word_stanza_misread_takes_the_dictionarys_one_form() -> None:
    """Asked недотепа, Stanza answered недотеп; the dictionary reads недотёпа and gives
    one form (targum-internal#650)."""
    assert yo_checked("недотёпа", "недотеп", ["недотёпа"]) == "недотёпа"
    assert yo_checked("копчёная", "копченой", ["копчёный"]) == "копчёный"
    # Stanza's answer is the dictionary's, ё or not: it stands, and with_yo has the ё.
    assert yo_checked("ёлке", "ёлка", ["ёлка"]) == "ёлка"
    assert yo_checked("осёл", "осел", ["осёл", "осесть"]) == "осел"
    # Two forms in the dictionary, or no ё in the word: not a spelling rule's to choose.
    assert yo_checked("щёлке", "щелок", ["щёлка", "щёлок"]) == "щелок"
    assert yo_checked("дома", "дом", ["дома"]) == "дом"


def parsed(*words: tuple[str, str, str, int]) -> list[Piece]:
    """A sentence as spaCy might parse it: (text, pos, dep, head) for each word. A
    subject is in the nominative."""
    out, idx = [], 0
    for text, pos, dep, head in words:
        morph = "Case=Nom" if dep.startswith("nsubj") else ""
        out.append(Piece(text=text, idx=idx, pos=pos, morph=morph, dep=dep, head=head, lemma=text))
        idx += len(text) + 1
    return out


def never(word: str, grammeme: str) -> bool:
    """A dictionary with every word a noun, no verb transitive, nobody animate."""
    return grammeme == "NOUN"


def test_a_learner_looks_her_and_everything_up_by_their_own_words() -> None:
    """Possessive её is её, as их is их; её the object is она. всё, everything, is всё;
    всё agreeing with a noun is весь's (targum-internal#650)."""
    sees_her = parsed(
        ("я", "PRON", "nsubj", 1), ("вижу", "VERB", "ROOT", 1), ("её", "PRON", "obj", 1)
    )
    assert pronoun(sees_her, 2, "PRON", never) == "она"
    her_house = parsed(("Её", "DET", "det", 1), ("дом", "NOUN", "ROOT", 1))
    assert pronoun(her_house, 0, "DET", never) == "её"
    assert pronoun(parsed(("Всё", "PROPN", "ROOT", 0)), 0, "PROPN", never) == "всё"
    assert pronoun(parsed(("всё", "PRON", "ROOT", 0)), 0, "PRON", never) == "всё"
    assert (
        pronoun(parsed(("всё", "DET", "det", 1), ("время", "NOUN", "ROOT", 1)), 0, "DET", never)
        is None
    )
    assert pronoun(parsed(("дом", "NOUN", "ROOT", 0)), 0, "NOUN", never) is None


def test_possessive_his_goes_before_its_noun_and_is_no_verbs_object() -> None:
    """Possessive его is его, as её and их are, whatever spaCy tags it: it goes before the
    noun it hangs off, or straight after it. After a verb it is the verb's object, unless
    the noun is (targum-internal#683)."""

    def his(*words: tuple[str, str, str, int]) -> str | None:
        sentence = parsed(*words)
        at = next(n for n, w in enumerate(sentence) if w.text.lower() in {"его", "её", "их"})
        return pronoun(sentence, at, sentence[at].pos, reads)

    def reads(word: str, grammeme: str) -> bool:
        if grammeme == "NOUN":
            return word not in {"Одел", "убей"}
        if grammeme == "VERB":
            return word in {"Одел", "убей"}
        if grammeme in {"ADVB", "ADJF"}:
            return False
        tran = {"хлопнув", "ожидают", "видел", "Одел", "сияет"}
        return word in (tran if grammeme == "tran" else {"просители", "сапожник"})

    assert (
        his(("Его", "PRON", "nmod", 1), ("жена", "NOUN", "nsubj", 2), ("пришла", "VERB", "ROOT", 2))
        == "его"
    )
    assert (
        his(
            ("о", "ADP", "case", 3),
            ("его", "DET", "det", 3),
            ("новой", "ADJ", "amod", 3),
            ("книге", "NOUN", "ROOT", 3),
        )
        == "его"
    )
    assert (
        his(("у", "ADP", "case", 1), ("отца", "NOUN", "ROOT", 1), ("его", "PRON", "nmod", 1))
        == "его"
    )
    assert (
        his(("видел", "VERB", "ROOT", 0), ("его", "PRON", "nmod", 2), ("брата", "NOUN", "obj", 0))
        == "его"
    )
    assert his(("их", "PRON", "nmod", 1), ("дом", "NOUN", "ROOT", 1)) == "их"
    # The objects ling-ru found filed as possessives.
    assert (
        his(("хлопнув", "VERB", "ROOT", 0), ("его", "DET", "det", 2), ("рукою", "NOUN", "obl", 0))
        == "он"
    )
    assert (
        his(
            ("ожидают", "VERB", "ROOT", 0),
            ("его", "DET", "det", 2),
            ("просители", "NOUN", "nsubj", 0),
        )
        == "он"
    )
    assert (
        his(
            ("где", "ADV", "advmod", 2), ("его", "DET", "det", 2), ("похоронили", "VERB", "ROOT", 2)
        )
        == "он"
    )
    assert (
        his(("я", "PRON", "nsubj", 1), ("вижу", "VERB", "ROOT", 1), ("его", "PRON", "obj", 1))
        == "он"
    )
    assert (
        his(("Его", "PRON", "nsubj", 1), ("не", "PART", "advmod", 2), ("было", "VERB", "ROOT", 2))
        == "он"
    )
    assert his(("Это", "PRON", "nsubj", 1), ("его", "PRON", "ROOT", 1)) == "он"
    assert (
        his(("я", "PRON", "nsubj", 1), ("вижу", "VERB", "ROOT", 1), ("их", "PRON", "obj", 1))
        == "они"
    )
    # After a verb, before its subject: a person's is the object, a thing's the possessive.
    assert (
        his(("Одел", "VERB", "ROOT", 0), ("его", "DET", "det", 2), ("сапожник", "NOUN", "nsubj", 0))
        == "он"
    )
    assert (
        his(("сияет", "VERB", "ROOT", 0), ("его", "DET", "det", 2), ("лицо", "NOUN", "nsubj", 0))
        == "его"
    )
    # After a subject pronoun, or a word that is no noun whatever spaCy says: the object.
    assert (
        his(
            ("мы", "PRON", "nsubj", 3),
            ("его", "DET", "det", 2),
            ("духом", "NOUN", "obl", 3),
            ("поймаем", "VERB", "ROOT", 3),
        )
        == "он"
    )
    assert his(("Одел", "NOUN", "ROOT", 0), ("его", "PRON", "nmod", 0)) == "он"
    assert (
        his(("хоть", "ADV", "advmod", 2), ("его", "PRON", "det", 2), ("убей", "NOUN", "ROOT", 2))
        == "он"
    )
    # A quantity's genitive is the pronoun's: тысячи их.
    assert his(("тысячи", "NOUN", "ROOT", 0), ("их", "PRON", "nmod", 0)) == "они"


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


def test_a_yo_word_takes_the_e_reading_only_where_it_repairs_the_tag() -> None:
    """spaCy read идёт as a noun; asked идет it reads a verb. The е reading is taken only
    for a ё-word whose own tag the dictionary has no reading under: землёю, a noun, keeps
    it, and a word with no ё keeps its own however the е reading moved it
    (targum-internal#683)."""
    pymorphy3 = pytest.importorskip("pymorphy3")
    morph = pymorphy3.MorphAnalyzer()
    words = parsed(
        ("Идёт", "NOUN", "ROOT", 0), ("землёю", "NOUN", "obl", 0), ("Вынимай", "VERB", "conj", 0)
    )
    folded = parsed(
        ("Идет", "VERB", "ROOT", 0), ("землею", "VERB", "obl", 0), ("Вынимай", "PART", "conj", 0)
    )
    read = yo_repaired(words, folded, morph)
    assert [(w.text, w.pos, w.lemma) for w in read] == [
        ("Идёт", "VERB", ""),
        ("землёю", "NOUN", "землёю"),
        ("Вынимай", "VERB", "Вынимай"),
    ]
    # Read apart differently, the е reading is not taken at all.
    assert yo_repaired(words, folded[:2], morph) == words


def test_a_word_with_a_yo_keeps_its_own_dictionary_form(monkeypatch: pytest.MonkeyPatch) -> None:
    """ёлке was filed under блок, мёда under мёда and осёл under осела: Stanza had no
    letter for ё (targum-internal#650)."""
    here = all(
        importlib.util.find_spec(name) is not None
        for name in ("spacy", russian.SPACY_MODEL, "pymorphy3", "stanza")
    )
    if not here or not russian.is_fetched():
        pytest.skip("the russian extra and Stanza's Russian lemmatizer are not here")
    monkeypatch.setattr(russian, "available", lambda: True)
    texts = [
        "Мальчик у Христа на ёлке.",
        "Ёлке было холодно.",
        "Мы купили мёда и нашли ёжика.",
        "Учёного пришёл встретить осёл.",
        "Не понимая, в чём дело, Тётка и Фёдор Тимофеич жались.",
        "Она обо всём аккуратно расспрашивала.",
        "Её дочь поведала об этом.",
        "Всё в порядке.",
        "Его жена видела его брата, а я вижу его.",
        "Эх ты… недотёпа!",
        "Здравствуйте! У вас есть копчёная рыба?",
        "Своими вздохами, нытьём, своими тёмными очками он давил нас всех.",
    ]
    segments = [
        Segment(id=f"{at:04d}.000-x", block_id="b0000", block_index=0, index=at, text=text)
        for at, text in enumerate(texts)
    ]
    read = RussianLemmatizer(auto_download=False).lemmas(segments, "ru")
    by = {token.surface: token.lemma for tokens in read.values() for token in tokens}
    assert by["ёлке"] == "ёлка"
    assert by["Ёлке"] == "ёлка"
    assert by["мёда"] == "мёд"
    assert by["ёжика"] == "ёжик"
    assert by["осёл"] == "осёл"
    # The fold cost these their lemma, or their ё; what restores it.
    assert by["чём"] == "что"
    assert by["всём"] == "весь"
    assert by["Её"] == "её"
    assert by["Всё"] == "всё"
    # Possessive его is его; the object его is он (targum-internal#683).
    assert by["Его"] == "его"
    his = [t for tokens in read.values() for t in tokens if t.surface == "его"]
    assert [t.lemma for t in his] == ["его", "он"]
    assert by["недотёпа"] == "недотёпа"
    assert by["копчёная"] == "копчёный"
    assert by["нытьём"] == "нытьё"
