"""A Russian word's lemma and grammar checked against OpenRussian at page-build and count
time (`annotate.russian_check`; ling-ru's analyser read of 2026-11-13, targum-internal#708,
#709, #710).

Offline: the dictionary is a handful of rows in the tables' own shape, and the sentences
are ling-ru's, each token as the annotator stored it.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from targum.annotate import openrussian
from targum.annotate.lemma_check import mended
from targum.models import Annotation, BlockKind, Segment, SegmentedDocument, Token
from targum.occurrences import count_text

LOCAL = "ru-local/ru_core_news_lg-3.8.0+stanza-1.14.0/syntagrus_nocharlm+pymorphy3-2.0.6/1"


def entry(
    kind: str, written: str, aspect: str = "", partners: str = "", gender: str = "", **forms: str
):
    return openrussian.Entry(
        kind,
        written,
        aspect=aspect,
        partners=tuple(p for p in partners.split(";") if p),
        gender=gender,
        forms={column: [v.strip() for v in value.split(",")] for column, value in forms.items()},
    )


ROWS: dict[str, list[openrussian.Entry]] = {
    "строгий": [
        entry(
            "adjective",
            "стро'гий",
            comparative="стро'же",
            short_m="стро'г",
            short_f="строга'",
            short_n="стро'го",
            short_pl="стро'ги строги'",
            decl_m_nom="стро'гий",
            decl_f_nom="стро'гая",
        )
    ],
    "пустой": [
        entry(
            "adjective",
            "пусто'й",
            short_m="пу'ст",
            short_f="пуста'",
            short_n="пу'сто",
            short_pl="пусты'",
            decl_m_nom="пусто'й",
        )
    ],
    "высокий": [
        entry(
            "adjective",
            "высо'кий",
            comparative="вы'ше",
            short_m="высо'к",
            short_f="высока'",
            decl_m_nom="высо'кий",
            decl_f_nom="высо'кая",
        )
    ],
    "лукавый": [entry("adjective", "лука'вый", short_n="лука'во", decl_m_nom="лука'вый")],
    "подписать": [
        entry(
            "verb",
            "подписа'ть",
            "perfective",
            "подписывать",
            presfut_sg1="подпишу'",
            past_pl="подписа'ли",
        )
    ],
    "быть": [entry("verb", "быть", "imperfective", imperative_sg="бу'дь", past_f="была'")],
    "войти": [
        entry(
            "verb",
            "войти'",
            "perfective",
            "входить",
            imperative_sg="войди'",
            presfut_sg1="войду'",
            presfut_sg2="войдёшь",
        )
    ],
    "брать": [
        entry("verb", "брать", "imperfective", "взять", imperative_sg="бери'", presfut_sg1="беру'")
    ],
    "пить": [
        entry("verb", "пить", "imperfective", "выпить", imperative_sg="пе'й", presfut_sg1="пью'")
    ],
    "дать": [
        entry("verb", "дать", "perfective", "давать", imperative_sg="да'й", presfut_sg3="да'ст")
    ],
    "давать": [
        entry(
            "verb",
            "дава'ть",
            "imperfective",
            "дать",
            imperative_sg="дава'й",
            presfut_sg3="даёт",
        )
    ],
    "сказать": [
        entry(
            "verb", "сказа'ть", "perfective", "говорить", presfut_sg3="ска'жет", past_n="сказа'ло"
        )
    ],
    "плакать": [
        entry("verb", "пла'кать", "imperfective", imperative_sg="пла'чь", presfut_sg3="пла'чет")
    ],
    "пир": [entry("noun", "пир", gender="m", sg_nom="пи'р", sg_dat="пи'ру", pl_prep="пира'х")],
    "уха": [entry("noun", "уха'", gender="f", sg_nom="уха'", sg_acc="уху'")],
    "ухо": [entry("noun", "у'хо", gender="n", sg_nom="у'хо", sg_dat="у'ху", sg_acc="у'хо")],
    "вино": [entry("noun", "вино'", gender="n", sg_nom="вино'", sg_gen="вина'")],
    "вина": [entry("noun", "вина'", gender="f", sg_nom="вина'", sg_gen="вины'")],
    "невеста": [
        entry(
            "noun",
            "неве'ста",
            gender="f",
            sg_nom="неве'ста",
            sg_dat="неве'сте",
            sg_prep="неве'сте",
        )
    ],
    "фон": [entry("noun", "фон", gender="m", sg_nom="фо'н")],
    "вера": [entry("noun", "ве'ра", gender="f", sg_nom="ве'ра")],
    "эка": [entry("other", "эка")],
    "нет": [entry("other", "нет")],
}


@pytest.fixture(autouse=True)
def lexicon(monkeypatch: pytest.MonkeyPatch) -> openrussian.Lexicon:
    table = openrussian.Lexicon(entries=ROWS)
    monkeypatch.setattr(openrussian, "lexicon", lambda: table)
    return table


def tokens(text: str, *words: tuple[str, str, str, str]) -> list[dict[str, Any]]:
    """Each (surface, lemma, pos, feats) at its place in `text`, as annotation.json stores
    it."""
    out, at = [], 0
    for surface, lemma, pos, feats in words:
        found = re.compile(rf"(?<!\w){re.escape(surface)}(?!\w)").search(text, at)
        assert found is not None, surface
        start = found.start()
        at = start + len(surface)
        out.append(
            Token(
                start=start,
                end=at,
                surface=surface,
                lemma=lemma,
                band=1,
                pos=pos,
                feats=f"UPOS={pos}|{feats}" if feats else f"UPOS={pos}",
            ).model_dump()
        )
    return out


def read(*sentences: tuple[str, list[dict[str, Any]]]) -> list[list[Token]]:
    """The sentences as the page reads them, each word checked."""
    segments = [
        Segment(id=f"s{n}", block_id=f"b{n}", block_index=n, index=0, text=text)
        for n, (text, _) in enumerate(sentences)
    ]
    annotation = Annotation(
        document_hash="h",
        language="ru",
        annotator=LOCAL,
        method="test",
        method_note="",
        tokens={
            f"s{n}": [Token.model_validate(row) for row in rows]
            for n, (_, rows) in enumerate(sentences)
        },
    )
    document = SegmentedDocument(document_hash="h", language="ru", segmenter="t", segments=segments)
    out = mended(annotation, document)
    return [out.tokens[f"s{n}"] for n in range(len(sentences))]


def one(text: str, *words: tuple[str, str, str, str]) -> list[Token]:
    return read((text, tokens(text, *words)))[0]


def feats(token: Token) -> dict[str, str]:
    return dict(part.split("=", 1) for part in (token.feats or "").split("|"))


# -- #708: a short form takes no case -----------------------------------------------


def test_a_short_adjective_loses_its_case() -> None:
    words = one(
        "я была слишком строга",
        ("я", "я", "PRON", "Case=Nom|Number=Sing|Person=1"),
        ("была", "быть", "AUX", "Gender=Fem|Number=Sing|Tense=Past|VerbForm=Fin"),
        ("слишком", "слишком", "ADV", ""),
        ("строга", "строгий", "ADJ", "Case=Nom|Gender=Fem|Number=Sing"),
    )
    said = feats(words[3])
    assert "Case" not in said
    assert said["Variant"] == "Short"
    assert said["Gender"] == "Fem" and said["Number"] == "Sing"
    assert words[3].lemma == "строгий"


def test_a_plural_short_adjective_loses_its_case() -> None:
    words = one(
        "Улицы были совершенно пусты",
        ("пусты", "пустой", "ADJ", "Case=Nom|Number=Plur"),
    )
    assert feats(words[0]) == {"UPOS": "ADJ", "Number": "Plur", "Variant": "Short"}


def test_a_short_participle_loses_its_case() -> None:
    words = one(
        "подписаны правительством",
        (
            "подписаны",
            "подписать",
            "VERB",
            "Aspect=Perf|Case=Nom|Number=Plur|Tense=Past|VerbForm=Part|Voice=Pass",
        ),
    )
    said = feats(words[0])
    assert "Case" not in said
    assert said["Variant"] == "Short" and said["Number"] == "Plur" and said["Tense"] == "Past"


def test_a_comparative_has_no_case_gender_or_number() -> None:
    words = one(
        "гора выше других",
        ("выше", "высокий", "ADJ", "Case=Nom|Gender=Fem|Number=Sing"),
    )
    assert feats(words[0]) == {"UPOS": "ADJ", "Degree": "Cmp"}


def test_a_full_adjective_keeps_its_case() -> None:
    words = one("строгая мать", ("строгая", "строгий", "ADJ", "Case=Nom|Gender=Fem|Number=Sing"))
    assert feats(words[0])["Case"] == "Nom"


def test_a_finite_past_that_is_a_short_participle_is_one() -> None:
    words = one(
        "сказано",
        (
            "сказано",
            "сказать",
            "VERB",
            "Aspect=Perf|Gender=Neut|Number=Sing|Tense=Past|VerbForm=Fin",
        ),
    )
    said = feats(words[0])
    assert said["VerbForm"] == "Part" and said["Variant"] == "Short" and "Case" not in said


# -- #709: the future, and imperatives ------------------------------------------------


def test_budesh_is_a_future() -> None:
    words = one(
        "что будешь делать?",
        ("будешь", "быть", "AUX", "Aspect=Imp|Number=Sing|Person=2|Tense=Pres|VerbForm=Fin"),
    )
    assert feats(words[0])["Tense"] == "Fut"


def test_a_perfective_present_is_its_future() -> None:
    # промыслить is not in the table: the tagger's own aspect says it.
    words = one(
        "что в полдень промыслишь!",
        (
            "промыслишь",
            "промыслить",
            "VERB",
            "Aspect=Perf|Mood=Ind|Number=Sing|Person=2|Tense=Pres|VerbForm=Fin",
        ),
    )
    assert feats(words[0])["Tense"] == "Fut"


def test_an_imperative_read_as_a_future_is_one() -> None:
    words = one(
        "войди в купель",
        (
            "войди",
            "войти",
            "VERB",
            "Aspect=Perf|Mood=Ind|Number=Sing|Person=1|Tense=Fut|VerbForm=Fin",
        ),
    )
    said = feats(words[0])
    assert said["Mood"] == "Imp" and said["Person"] == "2" and "Tense" not in said


def test_a_capitalised_imperative_is_not_a_name() -> None:
    words = one(
        "— Бери его и поезжай в церковь.",
        ("Бери", "Бери", "PROPN", "Case=Nom|Gender=Masc|Number=Sing"),
    )
    assert (words[0].lemma, words[0].pos, feats(words[0])["Mood"]) == ("брать", "VERB", "Imp")
    words = one("Пей, батюшка", ("Пей", "пить", "PROPN", "Case=Nom|Number=Sing"))
    assert (words[0].lemma, words[0].pos) == ("пить", "VERB")


def test_an_imperative_tagged_as_an_adverb_is_one() -> None:
    words = one("пей, батюшка", ("пей", "пить", "ADV", ""))
    assert (words[0].pos, feats(words[0])["Mood"]) == ("VERB", "Imp")


def test_a_name_the_text_uses_as_a_name_is_left_alone() -> None:
    # Бери capitalised inside a sentence is somebody called Бери.
    first = tokens("Бери ушёл.", ("Бери", "Бери", "PROPN", "Case=Nom"))
    second = tokens(
        "Мы ждали, а Бери ушёл.", ("а", "а", "CCONJ", ""), ("Бери", "Бери", "PROPN", "Case=Nom")
    )
    words = read(("Бери ушёл.", first), ("Мы ждали, а Бери ушёл.", second))
    assert words[0][0].pos == "PROPN" and words[1][1].pos == "PROPN"


def test_a_form_of_the_partner_is_the_partners() -> None:
    words = one(
        "он даёт",
        ("даёт", "дать", "VERB", "Aspect=Perf|Number=Sing|Person=3|Tense=Pres|VerbForm=Fin"),
    )
    said = feats(words[0])
    assert words[0].lemma == "давать"
    assert said["Aspect"] == "Imp" and said["Tense"] == "Pres"


# -- #710: lemmas the table witnesses ---------------------------------------------------


def test_an_invented_lemma_takes_the_tables() -> None:
    words = one(
        "на своих пирах",
        ("пирах", "пира", "NOUN", "Case=Loc|Gender=Fem|Number=Plur"),
    )
    assert words[0].lemma == "пир"
    assert feats(words[0])["Gender"] == "Masc"


def test_a_form_not_in_its_lemmas_tagged_cell_takes_the_word_whose_it_is() -> None:
    words = one("в уху", ("уху", "ухо", "NOUN", "Case=Acc|Gender=Neut|Number=Sing"))
    assert words[0].lemma == "уха"
    words = one(
        "он приносит еще вина",
        ("вина", "вина", "NOUN", "Case=Gen|Gender=Fem|Number=Sing"),
    )
    assert words[0].lemma == "вино"


def test_the_nominative_of_vina_stays_guilt() -> None:
    words = one("его вина", ("вина", "вина", "NOUN", "Case=Nom|Gender=Fem|Number=Sing"))
    assert words[0].lemma == "вина"


def test_a_hyphen_particle_is_not_in_the_lemma() -> None:
    words = one(
        "плакать-то ему хочется",
        ("плакать-то", "плакать-то", "VERB", "Aspect=Imp|VerbForm=Inf"),
    )
    assert words[0].lemma == "плакать"


def test_a_lower_case_name_is_the_tables_common_word() -> None:
    words = one(
        "Татьяна Борисовна лукаво улыбнулась",
        ("лукаво", "лукаво", "PROPN", "Case=Nom|Number=Sing"),
    )
    assert (words[0].lemma, words[0].pos) == ("лукаво", "ADV")


def test_a_name_particle_stays_a_name() -> None:
    words = one("г-н фон Рихтер", ("фон", "фон", "PROPN", "Case=Nom"))
    assert words[0].pos == "PROPN"


def test_a_capitalised_word_opening_a_sentence_is_common_where_the_text_says_so() -> None:
    first = tokens(
        "— Невесте идет принарядиться, — сказала бабушка.",
        ("Невесте", "Невеста", "PROPN", "Case=Loc|Gender=Masc|Number=Sing"),
    )
    second = tokens("Где же невеста?", ("невеста", "невеста", "NOUN", "Case=Nom|Number=Sing"))
    words = read(
        ("— Невесте идет принарядиться, — сказала бабушка.", first),
        ("Где же невеста?", second),
    )
    assert (words[0][0].lemma, words[0][0].pos) == ("невеста", "NOUN")
    assert feats(words[0][0])["Gender"] == "Fem"


def test_a_name_opening_a_sentence_stays_one_without_the_text_saying_otherwise() -> None:
    words = one("Вера сказала.", ("Вера", "Вера", "PROPN", "Case=Nom|Gender=Fem|Number=Sing"))
    assert words[0].pos == "PROPN"


def test_an_interjection_tagged_as_a_name_loses_the_name() -> None:
    words = one("— Эка дура!", ("Эка", "Эка", "PROPN", "Case=Nom|Gender=Fem|Number=Sing"))
    assert (words[0].lemma, words[0].pos) == ("эка", "X")


def test_a_small_word_is_never_another_words_form() -> None:
    words = one("нет", ("нет", "нет", "VERB", "Aspect=Imp|VerbForm=Fin"))
    assert words[0].lemma == "нет"


def test_a_machine_without_the_tables_reads_as_before(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(openrussian, "lexicon", lambda: None)
    words = one("на своих пирах", ("пирах", "пира", "NOUN", "Case=Loc|Number=Plur"))
    assert words[0].lemma == "пира"


# -- the count reads the word the page shows -------------------------------------------


def test_the_count_files_the_word_under_the_lemma_the_page_shows(tmp_path: Path) -> None:
    folder = tmp_path / "text"
    folder.mkdir()
    text = "— Бери вина на своих пирах."
    segment = Segment(
        id="s1", block_id="b1", block_index=0, index=0, kind=BlockKind.paragraph, text=text
    )
    document = SegmentedDocument(
        document_hash="h", language="ru", segmenter="test", segments=[segment]
    )
    (folder / "segments.json").write_text(document.model_dump_json(), encoding="utf-8")
    rows = tokens(
        text,
        ("Бери", "Бери", "PROPN", "Case=Nom"),
        ("вина", "вина", "NOUN", "Case=Gen|Gender=Fem|Number=Sing"),
        ("пирах", "пира", "NOUN", "Case=Loc|Number=Plur"),
    )
    (folder / "annotation.json").write_text(
        json.dumps({"annotator": LOCAL, "language": "ru", "tokens": {"s1": rows}}),
        encoding="utf-8",
    )
    counted = count_text(folder)
    assert counted is not None
    assert counted.count("пир") == 1 and counted.count("пира") == 0
    assert counted.count("вино") == 1
    # A name is not counted; an imperative is a word.
    assert counted.count("брать") == 1
