"""Topic tags on Hebrew lemmas (targum-internal#605): the answer's rules, the price and
its cap, the lemma list drawn from the tables alone, and the share a synthetic reader
gets. Every row is synthetic: placeholder lemmas, no sentence, no reader, no model call.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from targum import topics
from targum.cli import app
from targum.tables.store import Contribution, Store


def _store(tmp_path: Path, counts: dict[str, dict[tuple[str, str], int]]) -> Store:
    store = Store(tmp_path / "corpus.db")
    for register, tallies in counts.items():
        store.write(
            Contribution("words", register, f"unit-{register}", "src", "CC0", "tool", "words/1"),
            tallies,
        )
    return store


# -- the answer ---------------------------------------------------------------------------


def test_an_answer_keeps_at_most_two_topics_and_general_alone() -> None:
    assert topics.checked(["food", "family", "money"]) == topics.Tag(("food", "family"), "high")
    assert topics.checked(["general", "food"]) == topics.Tag(("food",), "high")
    assert topics.checked(["general"], "low") == topics.Tag(("general",), "low")
    assert topics.checked(["food", "food"]) == topics.Tag(("food",), "high")
    assert topics.checked(["cooking"]) is None, "a code off the list fails the row"
    assert topics.checked([]) is None


def test_parse_keeps_only_the_ids_asked_and_each_once() -> None:
    text = json.dumps(
        {
            "tags": [
                {"id": 3, "topics": ["food"], "confidence": "high"},
                {"id": 3, "topics": ["money"], "confidence": "high"},
                {"id": 4, "topics": ["nonsense"], "confidence": "high"},
                {"id": 99, "topics": ["law"], "confidence": "low"},
                {"id": 5, "topics": ["law", "politics"], "confidence": "low"},
            ]
        }
    )
    tags = topics.parse(text, [3, 4, 5])
    assert tags == {
        3: topics.Tag(("food",), "high"),
        5: topics.Tag(("law", "politics"), "low"),
    }
    assert topics.parse("not json", [1]) == {}


def test_two_models_settle_what_they_share_and_leave_the_rest() -> None:
    food = topics.Tag(("food",), "high")
    both = topics.Tag(("food", "money"), "high")
    law = topics.Tag(("law",), "high")
    assert topics.agreed(food, food) == ("food",)
    assert topics.agreed(food, both) == ("food",)
    assert topics.agreed(food, law) is None
    assert topics.agreed(food, None) is None


def test_the_schema_names_every_topic_and_general() -> None:
    enum = topics.schema()["properties"]["tags"]["items"]["properties"]["topics"]["items"]["enum"]
    assert set(enum) == {*topics.TOPICS, topics.GENERAL}
    assert len(topics.TOPICS) == 16


def test_the_prompt_sends_four_fields_and_no_sentence() -> None:
    one = topics.Lemma("לחם", "NOUN", "לחם", "bread", "לֶחֶם", 9, "modern")
    message = topics.user_message([one], 7)
    assert message.endswith("7\tלחם (לֶחֶם)\tNOUN\tbread")
    prompt = topics.system_prompt()
    for code in [*topics.TOPICS, topics.GENERAL]:
        assert f"`{code}`" in prompt


def test_every_worked_example_keeps_the_rules() -> None:
    for _, _, _, _, answer in topics.EXAMPLES:
        assert topics.checked(answer) == topics.Tag(answer, "high")


# -- the price ----------------------------------------------------------------------------


def test_the_batch_halves_the_price_and_the_cache_reads_at_a_tenth() -> None:
    usage = topics.Usage(input_tokens=1_000_000, output_tokens=1_000_000)
    assert topics.cost("claude-opus-5-5", usage, batch=False) == pytest.approx(24.0)
    assert topics.cost("claude-opus-5-5", usage, batch=True) == pytest.approx(12.0)
    cached = topics.Usage(cache_read_tokens=1_000_000)
    assert topics.cost("claude-sonnet-5-5", cached, batch=False) == pytest.approx(0.2)


def test_the_worst_case_is_never_below_a_real_request() -> None:
    real = topics.Usage(input_tokens=5000, output_tokens=3000)
    ceiling = topics.worst_case("claude-opus-5-5", 5000, 3000, batch=True)
    assert ceiling >= topics.cost("claude-opus-5-5", real, batch=True)


# -- the lemmas ---------------------------------------------------------------------------


def test_the_lemmas_come_from_the_tables_with_their_main_part_of_speech(tmp_path: Path) -> None:
    store = _store(
        tmp_path,
        {
            "news": {("ממשלה", "NOUN"): 50, ("אמר", "VERB"): 40, ("של", "ADP"): 500},
            "conversation": {("אמר", "VERB"): 30, ("אמר", "NOUN"): 2, ("ארנב", "NOUN"): 20},
            "bible": {("כהן", "NOUN"): 70, ("אמר", "VERB"): 900},
        },
    )
    glosses = {"ממשלה": ("government", ""), "אמר (verb)": ("to say", "לומר"), "כהן": ("priest", "")}
    lemmas, missing = topics.universe(store, modern=3, bible=2, gloss=glosses.get)
    assert [(one.lemma, one.pos, one.register) for one in lemmas] == [
        ("אמר", "VERB", "modern"),
        ("ממשלה", "NOUN", "modern"),
        ("כהן", "NOUN", "bible"),
    ]
    assert lemmas[0].glossed_as == "אמר (verb)" and lemmas[0].pointed == "לומר"
    assert "ארנב" in missing, "no gloss, so it waits"
    assert all(one.lemma != "של" for one in lemmas), "a function word is never tagged"


def test_the_screen_leaves_out_what_is_not_a_topic_word() -> None:
    # Counts as the tables held them for pilot 1 (2026-10-30).
    assert topics.screened("אל", {"ADP": 5697, "PART": 706, "NOUN": 247}) == "function word"
    assert topics.screened("חמישה", {"NUM": 444, "PROPN": 31, "NOUN": 3}) == "number"
    assert topics.screened("מיאמי", {"PROPN": 11}) == "name"
    assert topics.screened("כ", {"ADV": 42, "NUM": 40}) == "one letter"
    assert topics.screened("הפועל", {"NOUN": 18, "PROPN": 10}, {"NOUN": 29}) == "clitic prefix"
    assert topics.screened("אבא", {"PROPN": 42, "NOUN": 24}) is None, "DICTA's PROPN is noisy"
    assert topics.screened("לחם", {"NOUN": 90}) is None
    # A real word that starts with a clitic letter, beside a bare form that is a verb or rarer.
    assert topics.screened("הצעה", {"NOUN": 14}, {"VERB": 5}) is None
    assert topics.screened("כתבה", {"NOUN": 110}, {"NOUN": 28}) is None


def test_screen_keeps_the_order_and_says_why(tmp_path: Path) -> None:
    store = _store(
        tmp_path,
        {"news": {("לחם", "NOUN"): 9, ("אל", "ADP"): 90, ("אל", "NOUN"): 3, ("עיר", "NOUN"): 50}},
    )
    store.write(
        Contribution("words", "news", "unit-b", "src", "CC0", "tool", "words/1"),
        {("בעיר", "NOUN"): 4},
    )

    def lemma(key: str) -> topics.Lemma:
        return topics.Lemma(key, "NOUN", key, "x", "", 1, "modern")

    kept, dropped = topics.screen(store, [lemma("אל"), lemma("לחם"), lemma("בעיר")])
    assert [one.lemma for one in kept] == ["לחם"]
    assert [(one["lemma"], one["why"]) for one in dropped] == [
        ("אל", "function word"),
        ("בעיר", "clitic prefix"),
    ]


def test_the_prompt_puts_the_commonest_sense_over_the_gloss() -> None:
    prompt = topics.system_prompt()
    assert "The gloss is a hint, not the sense" in prompt
    assert "not words that are religious only in a secondary or biblical sense" in prompt
    assert "everyday devices and their use (phone, screen, message, app) are Everyday life" in (
        prompt
    )


def test_prompt_3_keeps_time_words_and_media_verbs_general() -> None:
    prompt = topics.system_prompt()
    assert "Time as such (time, moment, period, occasion, the past, the future)" in prompt
    assert "Verbs of publishing, reporting, announcing, quoting and revealing" in prompt
    answers = {lemma: answer for lemma, _, _, _, answer in topics.EXAMPLES}
    for lemma in ("תקופה", "פעם", "עתיד", "הודיע", "ציטט", "חשף"):
        assert answers[lemma] == (topics.GENERAL,)
    # The topics a time or media word does keep, so the rule is not read as "all general".
    assert answers["חודש"] == ("everyday",)
    assert answers["ערוץ"] == ("culture",)
    assert topics.PROMPT_VERSION == "prompt/3"


def test_variants_counts_each_part_of_speech_over_every_register(tmp_path: Path) -> None:
    store = _store(
        tmp_path, {"news": {("x", "NOUN"): 2}, "bible": {("x", "NOUN"): 3, ("x", "VERB"): 1}}
    )
    assert store.variants("words", ["x", "y"]) == {"x": {"NOUN": 5, "VERB": 1}}


# -- the share ----------------------------------------------------------------------------


def test_a_share_is_weighted_and_a_word_in_two_topics_counts_in_both() -> None:
    lexicon = {"a": ("food",), "b": ("food", "money"), "c": ("money",), "d": ("general",)}
    weights = {"a": 3.0, "b": 1.0, "c": 1.0, "d": 5.0}
    shares = {s.topic: s for s in topics.shares(lexicon, ["a", "b", "d"], weights, {})}
    assert shares["food"].share == pytest.approx(1.0)
    assert shares["money"].share == pytest.approx(0.5)
    assert shares["food"].known == 2 and shares["money"].lemmas == 2
    assert not shares["food"].drawn, "two lemmas is below the topic floor"
    assert "general" not in shares


def test_religion_falls_back_to_the_bible_weights() -> None:
    lexicon = {"כהן": ("religion",), "שבת": ("religion",)}
    shares = {s.topic: s for s in topics.shares(lexicon, ["כהן"], {"שבת": 1.0}, {"כהן": 1.0})}
    assert shares["religion"].share == pytest.approx(0.5)


def test_share_reads_only_a_synthetic_reader(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = _store(
        tmp_path,
        {"conversation": {("לחם", "NOUN"): 9, ("כסף", "NOUN"): 4}, "news": {("לחם", "NOUN"): 1}},
    )
    lexicon = tmp_path / "topics.json"
    lexicon.write_text(
        json.dumps({"version": "topics/1", "lemmas": {"לחם": ["food"], "כסף": ["money"]}}),
        encoding="utf-8",
    )
    monkeypatch.setenv("TARGUM_LEDGER", str(store.file))
    runner = CliRunner()
    done = runner.invoke(
        app, ["topics", "share", "--person", "beginner", "--lexicon", str(lexicon)]
    )
    assert done.exit_code == 0, done.output
    assert "Food & drink" in done.output and "100.0%" in done.output
    assert "not shown" in done.output, "money has not passed the gold set"
    refused = runner.invoke(app, ["topics", "share", "--person", "7", "--lexicon", str(lexicon)])
    assert refused.exit_code != 0
    assert "Real readers are not read here" in refused.output


# -- what a page may show -----------------------------------------------------------------


def test_only_shown_topics_are_drawn() -> None:
    lexicon = {f"w{i}": ("food",) for i in range(topics.TOPIC_FLOOR)}
    lexicon |= {f"m{i}": ("money",) for i in range(topics.TOPIC_FLOOR)}
    weights = dict.fromkeys(lexicon, 1.0)
    by = {s.topic: s for s in topics.shares(lexicon, [], weights, {}, shown=("food",))}
    assert by["food"].drawn and by["food"].shown
    assert not by["money"].drawn and not by["money"].shown, "money has not passed the gold set"
    assert set(topics.SHOWN) == {"food", "security", "school", "family", "law"}
    assert set(topics.SHOWN) <= set(topics.TOPICS)


def test_the_lexicon_file_names_what_is_shown(tmp_path: Path) -> None:
    file = tmp_path / "topics.json"
    assert topics.load_shown(file) == (), "no lexicon, nothing to draw"
    file.write_text(json.dumps({"lemmas": {}}), encoding="utf-8")
    assert topics.load_shown(file) == topics.SHOWN, "no list falls back to the constant"
    file.write_text(json.dumps({"shown": ["law", "food", "nonsense"], "lemmas": {}}), "utf-8")
    assert topics.load_shown(file) == ("food", "law"), "in the order of TOPICS, codes only"


def test_a_topic_joins_shown_only_past_the_gate() -> None:
    assert topics.passes_show(15, 0.9, 0.8)
    assert not topics.passes_show(14, 1.0, 1.0), "too few gold rows"
    assert not topics.passes_show(20, 0.89, 1.0)
    assert not topics.passes_show(20, 1.0, 0.79)
    assert not topics.passes_show(20, None, 1.0)


def test_shown_takes_each_topic_that_passes_and_none_past_a_failed_gate() -> None:
    held = {
        "gate": {"passes": True},
        "per_topic": {
            "food": {"gold": 15, "P": 0.95, "R": 0.9},
            "family": {"gold": 14, "P": 1.0, "R": 1.0},
            "health": {"gold": 20, "P": 0.8, "R": 1.0},
            "everyday": {"gold": 30, "P": 0.9, "R": 0.85},
            "general": {"gold": 40, "P": 1.0, "R": 1.0},
        },
    }
    assert topics.shown_from(held) == ("everyday", "food")
    assert topics.shown_from({**held, "gate": {"passes": False}}) == ()
    # Recall alone keeps a topic out, at the edge as well (religion sat at exactly 0.80).
    edge = {"gate": {"passes": True}, "per_topic": {"law": {"gold": 15, "P": 1.0, "R": 0.79}}}
    assert topics.shown_from(edge) == ()
    edge["per_topic"]["law"]["R"] = 0.8
    assert topics.shown_from(edge) == ("law",)


def test_the_gate_fails_on_general_alone_and_holds_it_at_85() -> None:
    # Ten topic rows all right, so topic precision is 1.0; `general` is said on twenty
    # rows, of which `right` are general in gold and the rest carry a topic.
    def held(right: int) -> dict[str, object]:
        gold = {f"t{i}": {"food"} for i in range(10)}
        predicted: dict[str, set[str]] = {f"t{i}": {"food"} for i in range(10)}
        for i in range(20):
            gold[f"g{i}"] = {topics.GENERAL} if i < right else {"travel"}
            predicted[f"g{i}"] = {topics.GENERAL}
        return topics.score(gold, predicted)

    assert held(17)["precision"] == 1.0 and held(17)["general_precision"] == 0.85
    assert held(17)["gate"]["passes"], "general at exactly 85% passes"
    assert held(16)["precision"] == 1.0 and held(16)["general_precision"] == 0.8
    assert not held(16)["gate"]["passes"], "general under 85% fails a perfect topic score"


def test_wilson_brackets_the_point_and_narrows_with_more_rows() -> None:
    low, high = topics.wilson(14, 15) or (0.0, 0.0)
    assert low < 14 / 15 < high <= 1.0
    assert topics.wilson(15, 15) == (pytest.approx(0.796, abs=0.001), 1.0)
    wide, narrow = topics.wilson(9, 10), topics.wilson(90, 100)
    assert wide and narrow and (wide[1] - wide[0]) > (narrow[1] - narrow[0])
    assert topics.wilson(0, 0) is None


@pytest.mark.parametrize(
    ("note", "expected"),
    [
        ("feeling; or health", ("health",)),
        ("or law (oath in court), religion", ("law", "religion")),
        ("or money/culture", ("money", "culture")),
        ("metal; or science, or health (iron deficiency)", ("science", "health")),
        ("phone/TV screen; science or culture also defensible", ("science", "culture")),
        ("submission (school) or serving (food)", ("school", "food")),
        ("killed in attacks or accidents; general would be defensible", ("general",)),
        ("road accident; could be health", ("health",)),
        ("lemmatisation error: article + Hapoel (name) or the verb (grammar)", ()),
        ("", ()),
    ],
)
def test_alternatives_read_the_labels_a_note_offers(note: str, expected: tuple[str, ...]) -> None:
    assert topics.alternatives(note) == expected


# -- hints --------------------------------------------------------------------------------


def test_a_hint_goes_in_the_gloss_column_and_only_then_is_explained() -> None:
    plain = topics.Lemma("עצב", "NOUN", "עצב", "to be sad; nerve", "", 3, "modern")
    assert "commonest modern sense" not in topics.user_message([plain], 0)
    hinted = topics.hinted(plain, "sadness", False, [])
    message = topics.user_message([hinted], 0)
    assert "to be sad; nerve [commonest modern sense: sadness]" in message
    assert "names the sense to tag" in message
    assert topics.hinted(plain, "sadness", True, ["x"]) is plain, "a gloss that leads with it"


def test_other_senses_come_from_the_lemmas_other_keys() -> None:
    held = {"גר": ("stranger; convert", ""), "גר (verb)": ("to live; reside", "לגור")}
    assert topics.other_senses("גר", "NOUN", "stranger; convert", held.get) == ["to live; reside"]
    one = topics.Lemma("גר", "NOUN", "גר", "stranger; convert", "", 1, "modern")
    assert topics.hinted(one, "lives", False, ["to live; reside"]).hint == (
        "lives; also to live; reside"
    )


def test_parse_hints_keeps_only_the_ids_asked_and_good_rows() -> None:
    text = json.dumps(
        {
            "senses": [
                {"id": 1, "sense": " phone   charger ", "first": False},
                {"id": 1, "sense": "again", "first": True},
                {"id": 2, "sense": "", "first": True},
                {"id": 9, "sense": "not asked", "first": True},
            ]
        }
    )
    assert topics.parse_hints(text, [1, 2]) == {1: ("phone charger", False)}
    assert topics.parse_hints("not json", [1]) == {}


def test_an_old_lemma_list_without_hints_still_loads() -> None:
    row = {
        "lemma": "לחם",
        "pos": "NOUN",
        "glossed_as": "לחם",
        "gloss": "bread",
        "pointed": "",
        "count": 1,
        "register": "modern",
    }
    assert topics.Lemma(**row).hint == ""


# -- Russian (targum-internal#638) ---------------------------------------------------------


def test_russian_has_its_own_prompt_file_and_nothing_shown() -> None:
    hebrew, russian = topics.system_prompt(), topics.system_prompt("ru")
    assert hebrew == topics.system_prompt("he"), "Hebrew's cached prompt is unchanged"
    assert russian != hebrew and "Russian dictionary words" in russian
    for code in [*topics.TOPICS, topics.GENERAL]:
        assert f"`{code}`" in russian
    assert "Knesset" not in russian and "reserve duty" not in russian
    assert topics.PROMPT_VERSIONS == {"he": "prompt/3", "ru": "ru-prompt/3"}
    assert topics.lexicon_file("ru") != topics.lexicon_file("he") == topics.LEXICON
    assert topics.run_lexicon("ru", "p").name == "topics-ru-p.json"
    assert topics.run_lexicon("he", "p").name == "topics-p.json"
    assert topics.SHOWN_FOR["ru"] == (), "Hebrew's pass is never lent to Russian"
    assert "ling-ru" in topics.shown_rule("ru") and "ling-he" in topics.shown_rule("he")
    with pytest.raises(ValueError):
        topics.language_code("fr")


def test_a_russian_request_names_the_stress_and_hebrews_the_pointing() -> None:
    one = topics.Lemma("хлеб", "NOUN", "хлеб", "bread", "хле́б", 9, "modern")
    assert "lemma (stressed form)" in topics.user_message([one], 1, "ru")
    assert topics.user_message([one], 1, "ru").endswith("1\tхлеб (хле́б)\tNOUN\tbread")
    assert "lemma (pointed form)" in topics.user_message([one], 1)


def test_every_russian_example_keeps_the_rules_and_is_russian() -> None:
    for lemma, _, _, _, answer in topics.EXAMPLES_RU:
        assert topics.checked(answer) == topics.Tag(answer, "high")
        assert all("а" <= ch <= "я" or ch == "ё" for ch in lemma), lemma
    lemmas = [one[0] for one in topics.EXAMPLES_RU]
    assert len(lemmas) == len(set(lemmas))
    assert topics.examples("ru") is topics.EXAMPLES_RU and topics.examples() is topics.EXAMPLES


def test_a_russian_file_without_a_list_shows_nothing(tmp_path: Path) -> None:
    file = tmp_path / "topics-ru.json"
    file.write_text(json.dumps({"lemmas": {"хлеб": ["food"]}}), encoding="utf-8")
    assert topics.load_shown(file, "ru") == ()
    assert topics.load_shown(file) == topics.SHOWN
    assert topics.load(file, "ru") == {"хлеб": ("food",)}


def test_the_score_is_micro_over_topic_labels_and_gates_at_hebrews_bar() -> None:
    gold = {
        "хлеб": {"food"},
        "суп": {"food"},
        "школа": {"school"},
        "стул": {"family"},
        "думать": {"general"},
        "налог": {"money", "politics"},
    }
    predicted = {
        "хлеб": {"food"},
        "суп": {"food"},
        "школа": {"school"},
        "стул": {"family", "everyday"},
        "думать": {"general"},
        "налог": {"money"},
        "extra": {"law"},
    }
    held = topics.score(gold, predicted, also={"стул": {"everyday"}})
    assert held["scored"] == 6 and held["unanswered"] == []
    assert held["tp_fp_fn"] == [5, 1, 1]
    assert held["precision"] == round(5 / 6, 3) and held["recall"] == round(5 / 6, 3)
    assert held["precision_lenient"] == 1.0, "a defensible label is excused, leniently only"
    assert held["general_precision"] == 1.0
    assert not held["gate"]["passes"], "83% is under the 90% Hebrew was held to"
    assert topics.PILOT_PRECISION == topics.SHOW_PRECISION == 0.90
    predicted["стул"] = {"family"}
    assert topics.score(gold, predicted)["gate"]["passes"]
    lost = topics.score({"a": {"food"}}, {})
    assert lost["unanswered"] == ["a"] and not lost["gate"]["passes"]


#: Every lemma of ling-ru's gold set (`topic-gold-ru-review-2026-11-06-v3.csv`, 670 rows:
#: v2's 133, whose lemmas are v1's, and 537 drawn blind with seed 6382): no Russian word
#: the prompt shows, in an example or a rule, may be one of them, or the prompt is taught
#: the test.
GOLD_RU = frozenset(
    """
    высовывать бай косица служить заспанный кинуть беспредельный перегибаться гнев
    переступать неодолимый значит убранство ссылаться закрытый прочитать сокрыть
    туалет почерневший помаленьку навеки медленно достижение замолчать послышаться
    сморкаться философия маска культура элемент тщательно двинуть наиболее доскакать
    ссадить член повязать блюститель спор недосягаемый уездный милостыня выжить
    рукавица высота глотать выместить отвозить молодо-зелено кисточка майский
    насмешить сначала великодушный больной прадедовский упрекать мечеть
    караван-сарай покойник ива нянька курьер рана масло ссора ломоть пресс бытовой
    лето есть силовой жеребец труд караул горбоносый иезуит настроение детская
    виновный крыжовник кокошник дрозд кушак вода шейка свинья чемодан вычитать
    сторож вечерок самонадеянный ротик суп люстра скрипка квартирка мебель воин
    расцеловать долететь бешмет композиция отравиться орех укроп лёд стадион
    болтливый ребёнок император помиловать прачечный тратить шайка внимательность
    кормить цветочный убираться возок рак-отшельник телёнок денежка жар художник
    куртка стишок выборка скоромное образованный приголубить тест жилье брюзжать
    детка вставлять вата затаить романсы хутор выгнуть веко кольцо затворяться
    вдохновенье прошлое огляниуться талия окружить болен вымаливать соцсеть вдова
    балалайка встретиться отобрать развитый мерка съедать сентябрь категория
    замужество валенка крестьянство сушенье свист гладкий раскачиваться попробовать
    генерал скользить прошептать слезать летать подпираться режим башмачник сима
    виноватый хам пью-с изорвать деть гулять бабка белобрысый трава непреодолимый
    весть кликать роиться подбородок чудак красный оглядеться пространство отставать
    покоситься попятиться желательный ребятишки граница дьявольщина уничтожиться
    сияние юридический знакомый деликатный мастер внести предстоять подпояска
    образчик пистолет трогай поворотить мимолётный сгорбленный запрашивать
    вывалиться попытка записать перспективный эффектный равнина блин подвергнуться
    позиция роща отношение доступ будущий взвешивать бархат ловить поторапливаться
    рожа давать фуражка поздороваться переводчик затягивать ругать склонить
    вырываться клеветать конный ошибка завертеться убежать забывать дозволяться
    осыпаться добыча запись угнетать товар поднять причина остолбенеть сабля
    наблюдаться завязать частый проворный сложённый общество роспись обморушка горох
    самоуверенный тогдашний отец-старик напомнить откашляться стихотворец сафьян
    чепуха обратиться издавать возвышение вихрь мармотка раскрыть богатой дружка
    усмотреть владеть рыхлый тащить присылка отвечать приседать мелькнуть денежный
    ставня презабавный попасть ученый удлинить усадьба кубарь далекий источник
    доходить неловкость едкий педагог крутить сдержать окаменеть ашика подбежать
    ветхий дергать раздеваться сомнение подкрасться проникать отправить невод
    силиться переставлять царственный класть оглядка выдающийся берёза липа
    перепалка темперамент приливать дубленый щель дорожный взволнованный сказка
    созвать чиновный кафтан исправительный пролепетать крастись копеечка козий
    деньжонка король конский предписание дьявол петь идти паралич фрукт цветной
    высокопоставленный считаться святочный белый надеть трудящийся послушаться
    приличный продавать прислуживаться уличный ермолка подъехать отваливаться
    ветреный сигара машина составить деться пламенный пустынь убраться гостиница
    нация обшарить фортепьяно проезд платный нарисовать староста концерт побагроветь
    учиться марать интервью учительский протечь веселье станционный исцеление
    сбиваться участвовать кататься править стремянный воскреснуть советник бедро
    подмастерье проезжий лжец залить грамота ручонка лаборатория поколение женин
    клешня поверенный шнурок ставить прощанье совещание мороженое статья паспорт
    пригнать страстной па потухнуть самолюбие засвистать отгадать казна судья
    философ хожалый человеческий оторвать учительница меняться осёл отпустить
    главный травка булочник натягивать полоскать царский предпринимать покорный язык
    обряд благословение деревенька расстроенный политический сумма сутуловатый
    взятка озлобление прелесть пешеход платёж жалованье набраться рубль освобождение
    нашитый дорогой неправ сержант бесчестие затрястись минарет федеральный выложить
    акция этажерка жертвовать прок барышня прилечь портной отделяться лекарство
    необычный забавляться утёс дойти побожиться жалование противник праотец
    подставить распространенный ребёночек перенять проснуться странствовать воск
    отрывистый бездна доказывать верность рождественский повывести девочка
    золотистый почка заверять стряпать ребеночек вознесение пачули грешница учёный
    кондиционер сражаться слезай речка раскаяние подняться унести воспитанный
    степняк пиво обучение словарь нравиться студентик слышит экономический ясность
    попенять исключение подрастать понедельник отредактировать остолоп самолёт
    август забота побаловать холостой доспех орлиный дачный висячий подкупить
    умеренно-либеральный обыватель украсть осыпать обнажённый снежный раствориться
    поза погладить женить капитал битва приказный уровень незрячий охранять шлёпнуть
    взвесить воля провод посапывать выбежать денщик зимовать заболеть голубь
    преступник жестокость запахнуться озябнуть штраф изогнуться убедительный слыхать
    легкий поражать тенор нагрянуть стянутый статистика четверть определённый
    устраивать прихотливый порох задрожать пирожок устройство младенец присяжный
    обшить щелкать теплота рябой приводить струсить соседство канат разбитный вар
    образовательный сотня уединение начальство уставить возглас клясться развитой
    потеряться миновать угорь дума попутать казнь административный трехрублевый
    экспериментальный радушие стоптанный верхушка рынок дипломатический бонжур театр
    выезжать инспекторша ночной доесть другой некрасивый пустыня шептать крикливый
    исследовательский соловей посветлеть спасение корочка стрельба красноречие
    армейский армянин лезгинка студенческий колесо плетня призыв разомлеть привлечь
    земский взглядывать скрюченный колебаться детский инженерный полюбиться камушек
    стукнуть математика данные ток научный ии естественник наука
    """.split()
)


#: Every lemma of the first predicted-tag sample (ling-ru, seed 20261106638, 2026-11-06):
#: ru-prompt/3 was written after it, so none of its words may be in the prompt.
SAMPLED_RU = frozenset(
    """
    адъютантский аккорд аккуратный алкоголь аллея анкета аптекарь безопасность
    безрасходный берёзовый бесплатно бесплатный благоразумный благословенный
    богатырь богиня божия большак борт будни будочник буква буфетчик ват вахмистра
    ввек вдобавок ведомство верховный вещество вздорный взрадоваться взыскать витязь
    вишня вкус вкусно вложить воинский вокзал волнообразный воспитание
    воспитательный вселенная вторник въехать выбоина выборы выбрить выговор
    выздороветь выключить выкуп выливать выстрелить гидростатика гнушаться город
    господь гостить государь готовить градусник гробовщик грудной грыжа губернатор
    гувернёр гусар гусарский дача дворник девица декламировать деньга держаться
    детство дефицит диктатор договор долг должность допрашивать драматический дуплет
    железо жеманиться жертва жир завещать завтрак заграничный задумать законный
    занятие заняться запад заповедь запомнить зарабатывать застав захромать зеленый
    зуб избить измерение износиться изобрести изумить изучать интернет интерфейс
    исправник исследование исследователь кабинет камыш капитан карета кверху
    кипарисовый кирпич кличка клубника коленка колокольный комната коровый
    корпорация кошелёк красть крестить кружево крыша кукла купец купчика кухонный
    лавка лампа лечить лисица лицо ложка лунный лыток манкировать мариновать мать
    медник мелочь мельник мешкать молебен молоко монета монисто мужчина музыка
    мученик надменно наесться наковырять накрапывать напевать нарушение нарядный
    наследство научить негодование незаконный нездоровый незначительный
    неподвижность неучёность нормально ночлег обидеть обложка обнять образок оброк
    обуть обучаться окончательный орган оскорбить отвалиться отвезти отправиться
    отпуск отрицательно оттушеванный отъезд офис офранцузить пазуха палача пальчик
    папироса пароль пастух патер патриот пение перевод переводить передняя
    переезжать перемешиваться переписка переправа пересесть переслать песет пирожное
    планета плотник плясун по-немецки погасить поговорка подлец подобострастие
    подпапка подсудимый подъезд поездка поиграть покоряться полковник положенный
    полынь пополам поправляться попудриться порасти посол постный почувствовать
    правитель привлечение придворный приклад прилетать пристав приходский проект
    проехать промышленный прописать проработать просвещение профессия прутик
    псалтырь психолог пуля пчела пчелка пьянство работница развестись разновидность
    разуться районный ранта распухнуть рассказчик резвость реклама родильница родина
    роковой ролик россиянин рояль ручей рыло сайт салат самолично сани свалиться
    свидетель свято святость святыня семейный семья сеть синенький сконфуженно
    скушать слово служака смоль смочить снаряд снетка совершение солдат солдатка
    солдатский сорочка сот сочинение спутник сражение среда ссылка стонать страна
    суд сум сундучок сценарий сыро тарелка тетка тетрадь торговать тюрьма тёплый
    тётка убыток ударение ударить удерживать улитка умереть умывальник уныло
    упоминать фальцет фильм финансист фискал фрак фронт функционал холодно христос
    царствие цена церковь циркулярно чай чайник чернильница чинишка читальня чтение
    шандал шляпка штат энергия ягода ярмарка ясно
    """.split()
)


def test_no_russian_word_in_the_prompt_is_a_gold_word() -> None:
    import re

    assert len(GOLD_RU) == 670
    assert len(SAMPLED_RU) == 360
    # Four ru-prompt/1 examples were drawn into the first sample, which did not exclude
    # them; every word ru-prompt/3 added is new to both sets.
    older = {"солдат", "выборы", "исследование", "церковь"}
    seen = GOLD_RU | SAMPLED_RU
    assert {one[0] for one in topics.EXAMPLES_RU} & seen == older
    import unicodedata

    # A stress mark (U+0301) would split a word in two, so stress marks are stripped
    # first; ё keeps its dots.
    decomposed = unicodedata.normalize("NFD", topics.system_prompt("ru").lower())
    bare = unicodedata.normalize("NFC", decomposed.replace("\u0301", "").replace("\u0300", ""))
    shown = set(re.findall(r"[а-яё-]+", bare))
    assert shown & seen == older
    assert "пресс" not in shown, "the media are СМИ or пресса, never пресс (David, 2026-11-06)"
    assert topics.PROMPT_VERSIONS["ru"] == "ru-prompt/3"


def test_a_pilot_sample_takes_in_every_gold_lemma() -> None:
    import importlib.util

    where = Path(__file__).resolve().parents[1] / "scripts" / "tag_topics.py"
    spec = importlib.util.spec_from_file_location("tag_topics", where)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    universe = [
        topics.Lemma(f"слово{i}", "NOUN", f"слово{i}", "word", "", 100 - i, "modern")
        for i in range(10)
    ]
    sample = module.spread(universe, 3)
    held = module.with_included(universe, sample, frozenset({"слово5", "слово0", "нет"}))
    assert [one.lemma for one in held] == ["слово0", "слово3", "слово5", "слово6"]
    assert module.with_included(universe, sample, frozenset()) == sample


def _score_script() -> object:
    import importlib.util

    where = Path(__file__).resolve().parents[1] / "scripts" / "score_topics.py"
    spec = importlib.util.spec_from_file_location("score_topics", where)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


GOLD_HEADER = "row,lemma,pointed,pos,gloss,topic_1,topic_2,notes,provenance\n"


def test_score_leaves_label_selected_rows_out_of_the_gate_and_shown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    script: object = _score_script()
    monkeypatch.setattr(topics, "RESEARCH", tmp_path)
    run = tmp_path / "ru-run"
    run.mkdir()
    rows = ["lemma\tsonnet-5-5\topus-5-5\tagreed"]
    gold = [GOLD_HEADER]
    # Twenty drawn rows: food rows the models get right, and general rows half of which
    # they wrongly call food; then twenty rows kept because their label is food, all right.
    for i in range(10):
        rows.append(f"f{i}\tfood\tfood\tfood")
        gold.append(f"{i},f{i},,NOUN,x,food,,,phase A\n")
    for i in range(10):
        rows.append(f"g{i}\tfood\tfood\tfood" if i < 5 else f"g{i}\tgeneral\tgeneral\t")
        gold.append(f"{10 + i},g{i},,NOUN,x,general,,,phase B systematic\n")
    for i in range(20):
        rows.append(f"s{i}\tfood\tfood\tfood")
        gold.append(f"{20 + i},s{i},,NOUN,x,food,,,phase B topic\n")
    gold.append("40,bad,,NOUN,x,food,,data fault,phase A\n")
    (run / "review.tsv").write_text("\n".join(rows) + "\n", encoding="utf-8")
    csv_file = tmp_path / "gold.csv"
    csv_file.write_text("".join(gold), encoding="utf-8")
    lexicon = tmp_path / "topics-ru.json"
    lexicon.write_text(
        json.dumps({"version": "topics/1+ru-prompt/3-ru-run", "shown": ["food"], "lemmas": {}}),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "sys.argv",
        ["score_topics.py", "--run", "ru-run", "--gold", str(csv_file), "--lexicon", str(lexicon)],
    )
    code = script.main()  # type: ignore[attr-defined]

    out = json.loads((run / "gold-score.json").read_text(encoding="utf-8"))
    agreed = out["agreed"]
    assert out["scored_rows"] == 20 and len(out["excluded_label_selected"]) == 20
    assert out["excluded_data_fault"] == ["bad"]
    # With the selected rows, food would be 30 of 35 (0.857); without, 10 of 15.
    assert agreed["precision"] == round(10 / 15, 3)
    assert not agreed["gate"]["passes"] and code == 4
    assert out["label_selected"]["per_topic"]["food"]["P"] == 1.0
    assert json.loads(lexicon.read_text(encoding="utf-8"))["shown"] == []


def test_label_selected_reads_the_phase_marks() -> None:
    script: object = _score_script()
    picks = script.label_selected  # type: ignore[attr-defined]
    assert picks({"provenance": "new v3, seed 6382 draw 12, phase B topic"})
    assert picks({"notes": "", "x": "new v3, seed 6382 draw 4450, phase C science"})
    assert not picks({"provenance": "new v3, seed 6382 draw 3, phase A"})
    assert not picks({"provenance": "new v3, seed 6382 draw 30, phase B systematic"})
    assert not picks({"provenance": "agree"})
    # Fails closed: a phase spelled any other way is never scored.
    assert picks({"provenance": "new v3, seed 6382 draw 12, phase B-topic"})
    assert picks({"provenance": "phase D"})


def test_a_topic_shows_only_when_its_sample_proves_ninety_percent() -> None:
    sample = [("food", {"food"})] * 35
    sample += [("law", {"law"})] * 34
    sample += [("travel", {"travel"})] * 18 + [("travel", {"everyday"})] * 2
    sample += [("health", {"health"})] * 44 + [("health", {"general"})] * 1
    sample += [("general", {"general"})] * 40
    held = topics.sampled_precision(sample)
    assert held["food"]["P_lower"] == 0.901 and held["food"]["shown"], "35 of 35 proves it"
    assert held["law"]["P"] == 1.0 and not held["law"]["shown"], "34 of 34 does not"
    assert held["travel"]["P"] == 0.9 and not held["travel"]["shown"], (
        "a point estimate is not proof"
    )
    assert held["health"]["P_lower"] is not None and held["health"]["P_lower"] < 0.9
    assert not held["health"]["shown"]
    assert not held["general"]["shown"], "general is never a bar"
    assert topics.shown_from_sample(held) == ("food",)


def _general_rows(right: int, of: int = 40) -> list[tuple[str, set[str]]]:
    return [("general", {"general"})] * right + [("general", {"food"})] * (of - right)


def test_a_sample_shows_nothing_past_its_general_or_micro_bar() -> None:
    topical = [("food", {"food"})] * 40
    shown = lambda rows: topics.shown_from_sample(topics.sampled_precision(rows))  # noqa: E731
    assert shown(topical + _general_rows(34)) == ("food",), "general at exactly 85% passes"
    assert shown(topical + _general_rows(33)) == ()
    assert shown(topical) == (), "no general stratum"
    # Food passes alone, but over all topics the sample is under 90%.
    weak = [("travel", {"general"})] * 20 + [("travel", {"travel"})] * 20
    assert shown(topical + weak + _general_rows(40)) == ()


def _sample_case(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, health_right: int, version: str = ""
) -> tuple[object, Path, Path]:
    script: object = _score_script()
    monkeypatch.setattr(topics, "RESEARCH", tmp_path)
    (tmp_path / "ru-run").mkdir()
    (tmp_path / "ru-run" / "lemmas.json").write_text('{"language": "ru"}', encoding="utf-8")
    lemmas = {f"f{i}": ["food"] for i in range(40)}
    lemmas |= {f"h{i}": ["health"] for i in range(40)}
    lemmas |= {f"g{i}": ["general"] for i in range(40)}
    held = {"version": "topics/1+ru-prompt/3-ru-run", "shown": [], "lemmas": lemmas}
    version = version or held["version"]
    lines = ["row,lemma,stratum,predicted,lexicon_version,topic_1,topic_2,notes"]
    lines += [f"{i},f{i},food,food,{version},food,," for i in range(40)]
    lines += [
        f"{40 + i},h{i},health,health,{version},{'health' if i < health_right else 'general'},,"
        for i in range(40)
    ]
    lines += [f"{80 + i},g{i},general,general,{version},general,," for i in range(40)]
    lines += [f"120,bad,health,health,{version},health,,data fault"]
    sample = tmp_path / "sample.csv"
    sample.write_text("\n".join(lines) + "\n", encoding="utf-8")
    lexicon = tmp_path / "topics-ru.json"
    lexicon.write_text(json.dumps(held), encoding="utf-8")
    monkeypatch.setattr(
        "sys.argv",
        ["score_topics.py", "--run", "ru-run", "--sample", str(sample), "--lexicon", str(lexicon)],
    )
    return script, sample, lexicon


def test_score_sample_writes_shown_from_the_predicted_tag_sample(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    script, _, lexicon = _sample_case(tmp_path, monkeypatch, health_right=39)
    assert script.main() == 0  # type: ignore[attr-defined]
    out = json.loads((tmp_path / "ru-run" / "sample-score.json").read_text(encoding="utf-8"))
    assert out["per_topic"]["health"]["sampled"] == 40 and out["per_topic"]["health"]["right"] == 39
    assert out["gate"]["passes"] and len(out["tags_sha256"]) == 64
    held = json.loads(lexicon.read_text(encoding="utf-8"))
    assert held["shown"] == ["food"], "39 of 40 does not prove 90%"
    assert held["shown_rule"] == topics.SAMPLE_SHOWN_RULE
    assert held["shown_tags_sha256"] == out["tags_sha256"]


def test_score_sample_exits_4_and_shows_nothing_when_no_topic_passes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    script, _, lexicon = _sample_case(tmp_path, monkeypatch, health_right=0)
    held = json.loads(lexicon.read_text(encoding="utf-8"))
    held["shown"] = ["food"]
    lexicon.write_text(json.dumps(held), encoding="utf-8")
    assert script.main() == 4  # type: ignore[attr-defined]
    assert json.loads(lexicon.read_text(encoding="utf-8"))["shown"] == []


def test_score_sample_refuses_a_sample_of_another_lexicon(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    script, _, lexicon = _sample_case(
        tmp_path, monkeypatch, health_right=40, version="topics/1+ru-prompt/2-ru-old"
    )
    before = lexicon.read_text(encoding="utf-8")
    assert script.main() == 5  # type: ignore[attr-defined]
    assert lexicon.read_text(encoding="utf-8") == before
    assert not (tmp_path / "ru-run" / "sample-score.json").exists()


def test_score_sample_refuses_a_row_whose_tags_have_changed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    script, _, lexicon = _sample_case(tmp_path, monkeypatch, health_right=40)
    held = json.loads(lexicon.read_text(encoding="utf-8"))
    held["lemmas"]["h3"] = ["people"]
    lexicon.write_text(json.dumps(held), encoding="utf-8")
    assert script.main() == 5  # type: ignore[attr-defined]
    assert json.loads(lexicon.read_text(encoding="utf-8"))["shown"] == []


def test_score_gold_refuses_another_runs_lexicon(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    script: object = _score_script()
    monkeypatch.setattr(topics, "RESEARCH", tmp_path)
    (tmp_path / "ru-run").mkdir()
    (tmp_path / "ru-run" / "review.tsv").write_text(
        "lemma\tsonnet-5-5\topus-5-5\tagreed\nf\tfood\tfood\tfood\n", encoding="utf-8"
    )
    gold = tmp_path / "gold.csv"
    gold.write_text(GOLD_HEADER + "1,f,,NOUN,x,food,,,\n", encoding="utf-8")
    lexicon = tmp_path / "topics-ru.json"
    lexicon.write_text(json.dumps({"version": "topics/1+ru-prompt/2-other", "shown": []}))
    monkeypatch.setattr(
        "sys.argv",
        ["score_topics.py", "--run", "ru-run", "--gold", str(gold), "--lexicon", str(lexicon)],
    )
    assert script.main() == 5  # type: ignore[attr-defined]


def test_score_sample_refuses_a_row_with_a_second_tag_since(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    script, _, lexicon = _sample_case(tmp_path, monkeypatch, health_right=40)
    held = json.loads(lexicon.read_text(encoding="utf-8"))
    held["lemmas"]["h3"] = ["health", "people"]
    lexicon.write_text(json.dumps(held), encoding="utf-8")
    assert script.main() == 5  # type: ignore[attr-defined]


def test_score_sample_refuses_a_stratum_the_lexicon_does_not_give(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    script, sample, _ = _sample_case(tmp_path, monkeypatch, health_right=40)
    text = sample.read_text(encoding="utf-8").replace(",h3,health,health,", ",h3,food,health,")
    sample.write_text(text, encoding="utf-8")
    assert script.main() == 5  # type: ignore[attr-defined]


def test_score_sample_refuses_a_lexicon_of_another_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    other = "topics/1+ru-prompt/3-ru-other"
    script, _, lexicon = _sample_case(tmp_path, monkeypatch, health_right=40, version=other)
    held = json.loads(lexicon.read_text(encoding="utf-8"))
    held["version"] = other
    lexicon.write_text(json.dumps(held), encoding="utf-8")
    assert script.main() == 5  # type: ignore[attr-defined]
