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
