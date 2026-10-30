"""Root lexicons (targum-internal#592, #596): the answers' rules, the checks, the scores,
and the lemma list drawn from public texts alone. Placeholder lemmas and a handful of
dictionary words; no sentence, no reader, no model call.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from targum import root_lexicon as rl
from targum import tables
from targum.tables.store import Contribution, Store
from targum.tables.words import WORDS
from targum.topics import Lemma


def _lemma(lemma: str, pos: str = "NOUN", register: str = "news") -> Lemma:
    return Lemma(lemma, pos, lemma, "gloss", "", 10, register)


def _he(**fields: Any) -> rl.HebrewRoot:
    row = {"root": "", "pattern": "", "borrowed": False, "meaning": "", "transparent": ""}
    row |= {"pointed": "", "confidence": "high"} | fields
    return rl.HebrewRoot(**row)


def _ru(spellings: str, prefixes: tuple[str, ...] = (), **fields: Any) -> rl.RussianRoot:
    first, *variants = spellings.split("/")
    row: dict[str, Any] = {"suffixes": (), "transparency": "transparent", "borrowed": False}
    row |= {"confidence": "high"} | fields
    return rl.RussianRoot((rl.Morph(first, tuple(variants)),), prefixes, **row)


# -- Hebrew rules -------------------------------------------------------------------------


def test_a_root_is_letters_joined_by_a_maqaf_with_finals_folded() -> None:
    assert rl.root_key("כ-ת-ב") == "כ־ת־ב"
    assert rl.root_key("ש־ל־ם") == rl.root_key("שׁלם") == "ש־ל־מ"
    assert rl.root_key(None) == rl.root_key("") == ""


def test_letters_in_order_allow_only_a_weak_radical_to_be_missing() -> None:
    assert rl.in_order("כ־ת־ב", "מכתב")
    assert rl.in_order("י־ר־ד", "הוריד"), "a weak first radical matched late must not block"
    assert rl.in_order("נ־פ־ל", "יפול")
    assert rl.in_order("ק־ו־ם", "קם")
    assert rl.in_order("ס־ב־ב", "סב"), "a geminate's repeat may be missing"
    assert not rl.in_order("ש־מ־ר", "מכתב")
    assert not rl.in_order("ב־ת־כ", "מכתב"), "out of order"
    assert not rl.in_order("א־ב־ג־ד־ה", "אבגדה"), "five radicals is no root"


def test_a_template_spells_the_lemma_once_the_root_is_put_in() -> None:
    assert rl.template_fits("מִקְטָל", "כ־ת־ב", "מכתב") is True
    assert rl.template_fits("קִטּוּל", "כ־ת־ב", "כיתוב") is True, "plene spelling is allowed"
    assert rl.template_fits("קֶטֶל", "כ־ת־ב", "מכתב") is False
    assert rl.template_fits("פעל", "כ־ת־ב", "כתב") is None, "a binyan is no template"
    assert rl.template_fits("מִקְטָל", "י־ר־ד", "מורד") is None, "a weak root is not asked"


def test_a_hebrew_answer_is_normalised_and_a_bad_root_fails_the_row() -> None:
    text = json.dumps(
        {
            "rows": [
                {
                    "id": 1,
                    "root": "כ-ת-ב",
                    "pattern": "פעל",
                    "borrowed": False,
                    "meaning": "Write",
                    "transparent": "yes",
                    "pointed": "כָּתַב",
                    "confidence": "high",
                },
                {
                    "id": 1,
                    "root": "ש־מ־ר",
                    "pattern": None,
                    "borrowed": False,
                    "meaning": None,
                    "transparent": None,
                    "pointed": "",
                    "confidence": "high",
                },
                {
                    "id": 2,
                    "root": None,
                    "pattern": None,
                    "borrowed": True,
                    "meaning": "x",
                    "transparent": "yes",
                    "pointed": "טֶלֶפוֹן",
                    "confidence": "low",
                },
                {
                    "id": 3,
                    "root": "א",
                    "pattern": None,
                    "borrowed": False,
                    "meaning": None,
                    "transparent": None,
                    "pointed": "",
                    "confidence": "high",
                },
                {
                    "id": 9,
                    "root": "כ־ת־ב",
                    "pattern": None,
                    "borrowed": False,
                    "meaning": None,
                    "transparent": None,
                    "pointed": "",
                    "confidence": "high",
                },
            ]
        },
        ensure_ascii=False,
    )
    answers = rl.parse("he", text, [1, 2, 3])
    assert set(answers) == {1, 2}
    assert answers[1] == _he(
        root="כ־ת־ב", pattern="פעל", meaning="write", transparent="yes", pointed="כָּתַב"
    )
    assert answers[2].root == "" and answers[2].borrowed and answers[2].meaning == ""
    assert answers[2].transparent == "", "no root, so nothing is transparent"
    assert rl.parse("he", "not json", [1]) == {}


def test_two_hebrew_answers_settle_the_root_and_leave_a_disputed_field_empty() -> None:
    first = _he(root="כ־ת־ב", pattern="מִקְטָל", meaning="write", transparent="yes")
    second = _he(root="כ־ת־ב", pattern="מַקְטֵל", meaning="writing", transparent="yes")
    settled = rl.agreed(first, second)
    assert settled is not None
    assert settled["root"] == "כ־ת־ב" and settled["pattern"] is None
    assert settled["transparent"] == "yes"
    assert rl.agreed(first, _he(root="ש־מ־ר")) is None
    assert rl.agreed(_he(borrowed=True), _he(borrowed=True)) == {
        "root": None,
        "pattern": None,
        "borrowed": True,
        "meaning": None,
        "transparent": None,
    }, "two answers of no root agree"
    assert rl.agreed(first, None) is None


def test_the_hebrew_checks_count_only_what_they_can_ask() -> None:
    lemmas = [
        _lemma("כתב", "VERB"),
        _lemma("מכתב"),
        _lemma("טלפון"),
        _lemma("מלך", register="bible"),
    ]
    answers = {
        0: _he(root="כ־ת־ב", pattern="פעל"),
        1: _he(root="כ־ת־ב", pattern="מִקְטָל"),
        2: _he(borrowed=True),
        3: _he(root="ש־ל־כ"),
    }
    out = rl.check_he(
        lemmas,
        answers,
        cc0=lambda lemma: "כתב" if lemma == "כתב" else "",
        wiktionary={"מכתב": frozenset({"כ־ת־ב"}), "מלכ": frozenset({"מ־ל־כ"})},
        strongs={"מלכ": frozenset({"מ־ל־כ"})},
    )
    assert out["rooted"] == 3 and out["no_root"] == 1 and out["borrowed"] == 1
    assert out["cc0_verb_roots"]["asked"] == 1 and out["cc0_verb_roots"]["agreed"] == 1
    assert out["wiktionary"]["asked"] == 2 and out["wiktionary"]["agreed"] == 1
    assert out["strongs_bible"]["asked"] == 1 and out["strongs_bible"]["agreed"] == 0
    assert out["strongs_bible"]["misses"] == [("מלך", "ש־ל־כ", "מ־ל־כ")]
    assert out["letters_in_order"]["agreed"] == 2, "ש־ל־כ cannot be read off מלך"
    assert out["template_fits"] == {"asked": 1, "agreed": 1, "rate": 1.0, "misses": []}


def test_strongs_derivations_are_followed_back_to_a_primitive_root(tmp_path: Path) -> None:
    xml = """<?xml version="1.0" encoding="utf-8"?>
<lexicon xmlns="http://openscriptures.github.com/morphhb/namespace">
<entry id="H1"><w pos="v" xml:lang="heb">כָּתַב</w><source>a primitive root;</source></entry>
<entry id="H2"><w pos="n-m" xml:lang="heb">מִכְתָּב</w><source>from <w src="H1">1</w>;</source></entry>
<entry id="H3"><w pos="n-m" xml:lang="heb">כְּתָב</w><source>from <w src="H2">2</w>;</source></entry>
<entry id="H4"><w xml:lang="x-pn">כִּתְבִי</w><source>from <w src="H1">1</w>;</source></entry>
<entry id="H5"><w pos="n-m" xml:lang="heb">אֲבַגְתָא</w><source>of foreign origin;</source></entry>
</lexicon>"""
    file = tmp_path / "strong.xml"
    file.write_text(xml, encoding="utf-8")
    roots = rl.strongs_roots(file)
    assert roots == {
        "כתב": frozenset({"כ־ת־ב"}),
        "מכתב": frozenset({"כ־ת־ב"}),
    }, "a name and a foreign word reach no root; H3 shares H1's spelling"


# -- Russian rules ------------------------------------------------------------------------


def test_russian_spellings_fold_stress_and_yo_but_keep_short_i() -> None:
    assert rl.fold_ru("Взя́ть") == "взять"
    assert rl.fold_ru("ёлка") == "елка"
    assert rl.fold_ru("й") == "й"


def test_a_russian_answer_needs_a_root_and_folds_its_affixes() -> None:
    text = json.dumps(
        {
            "rows": [
                {
                    "id": 4,
                    "roots": [{"morph": "Пис", "variants": ["пиш", "пис"], "sense": "Write"}],
                    "prefixes": ["на"],
                    "suffixes": ["а"],
                    "transparency": "transparent",
                    "borrowed": False,
                    "confidence": "high",
                },
                {
                    "id": 5,
                    "roots": [],
                    "prefixes": [],
                    "suffixes": [],
                    "transparency": "opaque",
                    "borrowed": False,
                    "confidence": "high",
                },
            ]
        },
        ensure_ascii=False,
    )
    answers = rl.parse("ru", text, [4, 5])
    assert set(answers) == {4}
    answer = answers[4]
    assert isinstance(answer, rl.RussianRoot)
    assert answer.roots == (rl.Morph("пис", ("пиш",), "write"),)
    assert answer.spellings == {"пис", "пиш"}


def test_two_russian_roots_agree_when_their_spellings_meet() -> None:
    assert rl.same_root(_ru("пис/пиш"), _ru("пиш"))
    assert not rl.same_root(_ru("вод"), _ru("ход/хож"))
    settled = rl.agreed(_ru("пис/пиш", ("на",)), _ru("пиш", ("на",), transparency="partial"))
    assert settled is not None
    assert settled["prefixes"] == ["на"] and settled["transparency"] is None


def test_the_russian_checks_read_edges_between_answered_words() -> None:
    lemmas = [_lemma("писать", "VERB"), _lemma("написать", "VERB"), _lemma("вода")]
    answers = {0: _ru("пис/пиш"), 1: _ru("пис", ("на",)), 2: _ru("ход")}
    out = rl.check_ru(
        lemmas,
        answers,
        derivbase=[("писать", "написать", "PFX"), ("вода", "водный", "SFX")],
        morphynet=[("писать", "написать", "на", "prefix"), ("вода", "подвода", "под", "prefix")],
    )
    assert out["root_in_lemma"]["asked"] == 3 and out["root_in_lemma"]["agreed"] == 2
    assert out["derivbase_edges_share_root"] == {"asked": 1, "agreed": 1, "rate": 1.0, "misses": []}
    assert out["morphynet_affix_listed"]["agreed"] == 1
    assert out["prefixes_start_lemma"]["agreed"] == 3


def test_agreement_is_field_by_field_over_rows_both_answered() -> None:
    first = {0: _he(root="כ־ת־ב", pattern="פעל"), 1: _he(root="ש־מ־ר"), 2: _he()}
    second = {0: _he(root="כ־ת־ב", pattern="פיעל"), 1: _he(root="ש־מ־ר")}
    out = rl.agreement("he", first, second)
    assert out["rows_both_answered"] == 2
    assert out["root"] == 1.0 and out["pattern"] == 0.5 and out["root_and_pattern"] == 0.5


# -- The blind set ------------------------------------------------------------------------


def test_a_filled_blind_set_scores_each_answer(tmp_path: Path) -> None:
    gold = tmp_path / "gold.csv"
    gold.write_text(
        "row,lemma,pointed,pos,gloss,root,pattern,borrowed,notes\n"
        "1,כתב,,VERB,write,כ-ת-ב,פעל,,\n"
        "2,טלפון,,NOUN,phone,-,,yes,\n"
        "3,שמר,,VERB,guard,ש-מ-ר,,,\n"
        "4,לא,,ADV,no,,,,unlabelled\n",
        encoding="utf-8",
    )
    answers = {10: _he(root="כ־ת־ב", pattern="פעל"), 11: _he(borrowed=True), 12: _he(root="ש־ב־ר")}
    out = rl.score("he", gold, answers, {1: 10, 2: 11, 3: 12, 4: 13})
    assert out["root"]["asked"] == 3 and out["root"]["agreed"] == 2
    assert out["pattern"] == {"asked": 1, "agreed": 1, "rate": 1.0, "misses": []}
    assert out["borrowed"]["agreed"] == 3

    ru = tmp_path / "gold-ru.csv"
    ru.write_text(
        "row,lemma,stressed,pos,gloss,roots,prefixes,suffixes,transparency,borrowed,notes\n"
        "1,написать,,VERB,write,пис (пиш),на,а,transparent,,\n",
        encoding="utf-8",
    )
    out = rl.score("ru", ru, {7: _ru("пиш/пис", ("на",))}, {1: 7})
    assert out["root"]["agreed"] == 1 and out["prefixes"]["agreed"] == 1


# -- The lemmas ---------------------------------------------------------------------------


def _store(tmp_path: Path, counts: dict[str, dict[tuple[str, str], int]]) -> Store:
    store = Store(tmp_path / "corpus.db")
    for register, tallies in counts.items():
        store.write(
            Contribution("words", register, f"unit-{register}", "src", "CC0", "tool", "words/1"),
            tallies,
        )
    return store


def test_the_universe_draws_from_the_tables_and_gives_russian_its_stress(tmp_path: Path) -> None:
    store = _store(
        tmp_path,
        {
            "news": {
                ("рука", "NOUN"): 9,
                ("и", "CCONJ"): 50,
                ("знать", "VERB"): 5,
                ("нет", "NOUN"): 1,
            }
        },
    )
    asked: list[str] = []

    def gloss(filed: str) -> tuple[str, str] | None:
        asked.append(filed)
        return None if filed.startswith("нет") else ("a gloss", "")

    lemmas, dropped, missing = rl.universe(
        store,
        "ru",
        modern=10,
        registers=["news"],
        gloss=gloss,
        stress=lambda lemma: {"рука": "рука́"}.get(lemma, ""),
    )
    assert [(one.lemma, one.pointed) for one in lemmas] == [("рука", "рука́"), ("знать", "")]
    assert missing == ["нет"]
    assert "и" not in asked, "a function word is never even looked up"
    assert all(set(one) == {"lemma", "pos", "gloss", "why"} for one in dropped)


def test_russian_is_folded_into_its_own_store_and_never_from_a_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TARGUM_LEDGER", str(tmp_path / "corpus.db"))
    library = tmp_path / "library"

    def built(folder: Path, digest: str, language: str, lemma: str = "слово") -> None:
        folder.mkdir(parents=True)
        document = {"content_hash": digest, "source": f"test:{digest[:4]}"}
        (folder / "document.json").write_text(json.dumps(document), encoding="utf-8")
        token = {"start": 0, "end": 1, "surface": "w", "lemma": lemma, "band": 1, "pos": "NOUN"}
        annotation = {
            "document_hash": digest,
            "language": language,
            "annotator": "ru-local/1",
            "tokens": {"s0": [token]},
        }
        (folder / "annotation.json").write_text(json.dumps(annotation), encoding="utf-8")

    built(library / "p1" / "mine", "a" * 64, "ru")
    built(library / "shared" / "theirs", "b" * 64, "ru")
    built(library / "shared" / "hebrew", "c" * 64, "he", "w1")

    store, result = rl.russian_store(library, tmp_path / "ru.db")
    assert result.private == 1 and result.folded == 1
    assert store.top(WORDS, "unfiled") == [("слово", 1)]
    # The corpus ledger's own sweep still counts Hebrew only.
    corpus = Store(tmp_path / "corpus.db")
    assert tables.sweep(library, corpus).folded == 1
    assert corpus.top(WORDS, "unfiled") == [("w1", 1)]


def test_prompts_and_schemas_are_stable_and_name_every_field() -> None:
    for language in rl.LANGUAGES:
        assert rl.system_prompt(language) == rl.system_prompt(language), "cached prefix"
        required = rl.schema(language)["properties"]["rows"]["items"]["required"]
        for name in required:
            if name != "id":
                assert f"`{name}`" in rl.system_prompt(language)
    message = rl.user_message("ru", [Lemma("рука", "NOUN", "рука", "hand", "рука́", 1, "news")], 7)
    assert message.endswith("7\tрука (рука́)\tNOUN\thand")
