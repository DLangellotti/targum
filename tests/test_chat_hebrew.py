"""The Hebrew mode's contract, read back by the same rule it is written to."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import pytest

from targum import level
from targum.accounts import Store
from targum.chat import hebrew

TURN = """> אֲנִי הָלַכְתִּי לַשּׁוּק הַבֹּקֶר.
= I went to the market this morning.
מָה קָנִיתָ שָׁם?
= What did you buy there?
קָנִיתִי לֶחֶם.
= I bought bread.
"""


def test_a_turn_is_read_back_as_pairs_with_the_recast_marked() -> None:
    got = hebrew.pairs(TURN)
    assert [(p.recast, p.english) for p in got] == [
        (True, "I went to the market this morning."),
        (False, "What did you buy there?"),
        (False, "I bought bread."),
    ]
    assert got[0].hebrew.startswith("אֲנִי") and not got[0].hebrew.startswith(">")


def test_a_hebrew_line_the_model_forgot_to_translate_is_kept_and_a_stray_english_line_is_not() -> (
    None
):
    got = hebrew.pairs("שָׁלוֹם\nHow are you?\nמַה שְּׁלוֹמְךָ?\n= How are you?")
    assert [(p.hebrew, p.english) for p in got] == [("שָׁלוֹם", ""), ("מַה שְּׁלוֹמְךָ?", "How are you?")]
    assert hebrew.pairs("") == [] and hebrew.pairs("Just English.") == []


def test_words_become_seconds_at_the_conversational_rate() -> None:
    assert hebrew.seconds_for(120) == 60.0
    assert hebrew.seconds_for(0) == 0.0 and hebrew.seconds_for(-5) == 0.0
    assert hebrew.words_in("שלום עולם", "hi there friend") == 5
    assert 89 < hebrew.CONVERSATION_WORDS_PER_MINUTE < 150, (
        "between the read-aloud and the estimate"
    )


@pytest.mark.skipif(
    shutil.which("python3") is None or not hebrew.common_words(5), reason="wordfreq missing"
)
def test_the_common_words_are_the_first_two_bands_most_common_first() -> None:
    from wordfreq import zipf_frequency

    words = hebrew.common_words(50)
    assert len(words) == 50 and words[0] in ("את", "של", "לא")
    assert all(zipf_frequency(w, "he") >= hebrew.BAND_FLOOR_ZIPF for w in words)


def test_the_ledger_block_carries_the_words_and_never_a_level(tmp_path: Path) -> None:
    store = Store(tmp_path / "db")
    person, _ = store.finish_sign_in(store.start_sign_in("r@example.com"))  # type: ignore[misc]
    store.push(
        person,
        {
            "words": [
                {
                    "language": "he",
                    "lemma": "שלום",
                    "status": 9,
                    "band": "easy",
                    "at": 1,
                    "seen": 1,
                },
                {"language": "he", "lemma": "בית", "status": 9, "band": "easy", "at": 3, "seen": 3},
                {"language": "he", "lemma": "דוד", "status": 9, "band": "name", "at": 2, "seen": 2},
                {"language": "he", "lemma": "רעב", "status": 2, "band": "hard", "at": 4, "seen": 4},
            ]
        },
    )
    known = hebrew.known_words(store, person.id, "he")
    assert known == ["בית", "שלום"], "known only, names out, newest first"
    block = hebrew.ledger_block(level.snapshot(store, person.id, "he"), known, ["את", "של"])
    assert "known words (2): בית שלום" in block and "Common words" in block
    assert "not a placement" in block
    empty = hebrew.ledger_block(level.EMPTY, [], [])
    assert "no words known yet" in empty
    assert "ask what they have read" in empty and "never what level" in empty, (
        "a first day has no ledger: the way to one is a text"
    )
    assert "read in Hebrew so far" in empty


def test_a_first_day_in_another_language_asks_about_that_language() -> None:
    """An Italian conversation with an empty Italian ledger was told to ask what the reader
    had read in Hebrew, and offered a Hebrew text (2026-09-15)."""
    from dataclasses import replace

    italian = hebrew.ledger_block(replace(level.EMPTY, language="it"), [], [])
    assert "The reader is learning Italian" in italian
    assert "read in Italian so far" in italian
    assert "Hebrew" not in italian, italian


def test_the_contract_says_the_shape_and_the_rule() -> None:
    said = " ".join(hebrew.CONTRACT.split())  # the prose is wrapped; the words are what count
    assert '"= "' in said and '"> "' in said
    assert "vowel points" in said and "Natural first" in said
    assert "never bend a sentence" in said and "two or three in" in said, (
        "naturalness before the list; new words on purpose, and not many"
    )
    assert "ktiv male" in said and "לִקְרוֹא" in said, "the full spelling a modern reader meets"
    # Read off a real transcript (2026-09-07): a conversation that was good and still
    # obviously a machine thinking in English — em dashes in half the lines, "note:" and
    # "and one more thing:" lead-ins, English glosses in brackets inside the Hebrew,
    # "לְקַלֵּק" for pressing, and "X, or Y?" closing every single reply.
    assert "No em dashes between clauses" in said
    assert "No colon lead-ins" in said and "שִׂים לֵב:" in said
    assert "No English inside a Hebrew line" in said and "(is saved)" in said
    assert "לְקַלֵּק" in said and "לִלְחוֹץ" in said
    assert 'not "2 הַיָּמִים"' in said and "הֶסְבֵּר" in said
    assert "Do not end every reply the same way" in said and "X, or Y?" in said
    assert "Begin every reply with the reader's own line" in said, (
        "every reader turn carries its English"
    )
    # Literal Hebrew, 2026-09-06: a recast that carried the reader's English grammar
    # mistakes and word order, and the model's own lines read as translated English.
    assert "Never carry their grammar mistakes" in said
    assert "Write your own lines in Hebrew first" in said and "no calques" in said
    assert "the English for the Hebrew you wrote" in said
    assert "never tell the reader they are at a level" in said.lower()
    assert "its path" in said and "draws it as a door" in said, "opened, not declared open"
    assert "!" not in said


def word(lemma: str, status: int, at: int, band: str = "hard") -> dict[str, Any]:
    return {"language": "he", "lemma": lemma, "status": status, "band": band, "at": at, "seen": at}


def test_the_readers_words_come_back_by_status_if_a_newspaper_would_use_them(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The one thing the chat-first products never do: a saved word returns — and by
    where it stands (2026-09-07), from the whole ledger and not only this week's, so the
    words are met even when the reader is not reading. Filtered to words a modern
    conversation can carry — a word saved in Judges that no newspaper uses stays in
    Judges — and never named as an exercise."""
    from targum.annotate import frequency

    store = Store(tmp_path / "db")
    person, _ = store.finish_sign_in(store.start_sign_in("r@example.com"))  # type: ignore[misc]
    now = 10 * hebrew.LATELY_MS
    old = now - 2 * hebrew.LATELY_MS
    fresh = now - hebrew.LATELY_MS // 2
    store.push(
        person,
        {
            "words": [
                word("מצפה", 1, fresh),
                word("ספר", 2, old),
                word("גשם", 3, old),
                word("לחץ", 9, fresh, "easy"),
                word("ויכום", 1, fresh),
                word("רמון", 1, fresh, "name"),
                word("בית", 9, old, "easy"),
            ],
            "phrases": [
                {"id": "p1", "text": "בשבוע שעבר", "at": fresh, "seen": fresh},
                {"id": "p2", "text": "מזמן", "at": old, "seen": old},
            ],
        },
    )

    # A newspaper's words are the common ones here; ויכום is nobody's.
    monkeypatch.setattr(
        frequency.FrequencyBands, "band", lambda self, lemma, language: 6 if lemma == "ויכום" else 3
    )
    back = hebrew.bring_back(store, person.id, "he", now_ms=now)
    assert back.new == ["מצפה"], "a name left out, the biblical form left out"
    assert back.learning == ["ספר"] and back.nearly == ["גשם"]
    assert back.known == ["בית", "לחץ"], "known, the one ticked off longest ago first"
    assert back.phrases == ["בשבוע שעבר"], "this week's phrases"
    block = hebrew.ledger_block(level.EMPTY, [], [], back)
    assert "met once, not yet known (1): מצפה" in block
    assert "learning (1): ספר" in block and "nearly known (1): גשם" in block
    assert "known, from a while ago (2): בית לחץ" in block
    assert "ask the reader to use two" in block and "never say a word's status" in block
    assert "Phrases they kept lately (1): בשבוע שעבר" in block
    assert "carry back" not in hebrew.ledger_block(level.EMPTY, [], [])
    assert not hebrew.bring_back(store, None, "he", now_ms=now), "nobody signed in"


def test_the_ledger_is_walked_a_slice_a_conversation_and_a_short_status_passes_its_share_on(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from targum.annotate import frequency

    monkeypatch.setattr(frequency.FrequencyBands, "band", lambda self, lemma, language: 3)
    store = Store(tmp_path / "db")
    person, _ = store.finish_sign_in(store.start_sign_in("r@example.com"))  # type: ignore[misc]
    met = [f"מילה{n}" for n in range(8)]
    store.push(person, {"words": [word(lemma, 1, n) for n, lemma in enumerate(met)]})
    first = hebrew.bring_back(store, person.id, "he", seed=1)
    second = hebrew.bring_back(store, person.id, "he", seed=2)
    assert len(first.new) == 8 and first.new != second.new, (
        "with nothing learning or nearly known, the met-once words take the whole list, "
        "and the next conversation starts further along (by seed since #239)"
    )
    assert set(first.new) == set(met) == set(second.new)
    store.push(person, {"words": [word(f"לומד{n}", 2, n) for n in range(20)]})
    back = hebrew.bring_back(store, person.id, "he", seed=1)
    assert len(back.new) == 8 and len(back.learning) == 4, (
        "the met-once share is five and takes the four nobody nearly knows; learning keeps its own"
    )
    assert len(hebrew.rotate(list("abc"), 5, 0)) == 3 and hebrew.rotate([], 3, 0) == []


def test_a_slice_of_the_ledger_is_drawn_by_conversation_not_by_turn() -> None:
    """targum-internal#239: the same seed gives the same slice, and the next seed the
    next slice, so two conversations walk the ledger between them while one holds
    still — and the block after the cache breakpoint holds still with it."""
    pool = [f"w{n}" for n in range(10)]
    assert hebrew.rotate(pool, 3, 7) == hebrew.rotate(pool, 3, 7)
    assert hebrew.rotate(pool, 3, 7) != hebrew.rotate(pool, 3, 8)
    assert hebrew.rotate(pool, 3, 0) == ["w0", "w1", "w2"]
    assert hebrew.rotate(pool, 3, 1) == ["w3", "w4", "w5"]


def test_why_a_recast_changed_something_rides_with_the_recast_and_nowhere_else() -> None:
    """targum-internal#242: one "~ " line, directly under the recast's English, is the
    recast's; a "~ " anywhere else is the contract broken and is dropped."""
    said = (
        "> אֲנִי הָלַכְתִּי אֶתְמוֹל.\n= I went yesterday.\n~ Past tense: הָלַכְתִּי, not הָלַךְ.\n"
        "יָפֶה.\n= Nice.\n~ stray\nעוֹד.\n= More."
    )
    read = hebrew.pairs(said)
    assert [p.why for p in read] == ["Past tense: הָלַכְתִּי, not הָלַךְ.", "", ""]
    assert read[0].recast and read[0].english == "I went yesterday."
    assert hebrew.length(said) == 2, "a why line is not Hebrew the reader is asked to read"
    plain = hebrew.pairs("> שָׁלוֹם.\n= Hello.\nמָה שְׁלוֹמְךָ?\n= How are you?")
    assert all(p.why == "" for p in plain)


def test_a_why_line_belonging_to_no_recast_is_counted(  # targum-internal#242
) -> None:
    """The page never shows a stray `~ ` — `pairs()` drops it — so nothing could see the
    contract being broken, and acceptance criterion 3 asks for it counted. `stray_why`
    answers by difference against the parser itself, so the two cannot drift apart."""
    said = (
        "> אֲנִי הָלַכְתִּי אֶתְמוֹל.\n= I went yesterday.\n~ Past tense: הָלַכְתִּי, not הָלַךְ.\n"
        "יָפֶה.\n= Nice.\n~ stray\nעוֹד.\n= More."
    )
    assert hebrew.stray_why(said) == 1, "one belongs to the recast, one to nothing"

    kept = "> שָׁלוֹם.\n= Hello.\n~ A greeting takes no article.\nמָה שְׁלוֹמְךָ?\n= How are you?"
    assert hebrew.stray_why(kept) == 0, "the one the contract allows is not a breach"

    assert hebrew.stray_why("שָׁלוֹם.\n= Hello.") == 0, "no why line, no breach"
    assert hebrew.stray_why("~ out of nowhere\nשָׁלוֹם.\n= Hello.") == 1, "before any recast"
    assert hebrew.stray_why(ITALIAN_REPLY, "it") == 0, "the same rule in the other language"


def test_a_reader_with_no_ledger_is_told_once_where_the_common_words_are() -> None:
    """targum-internal#245: a reader who already reads Hebrew arrives with a ledger of
    nothing; the way up is Words you may already know, said once, never a level."""
    block = hebrew.ledger_block(level.EMPTY, [], ["של", "את"])
    assert "Words you may already know" in block and "never what level they are" in block


# -- Italian, the second language held in the talk shape (targum-internal#280) ----------

ITALIAN_REPLY = (
    "> Sono andato al mare ieri.\n= I went to the sea yesterday.\n"
    "~ Andare takes essere in the past.\n"
    "Com'era l'acqua?\n= What was the water like?\n"
    "/reader/due-amiche-it/reader/index.html"
)


def test_an_italian_reply_is_read_back_as_pairs_and_a_path_is_never_a_line() -> None:
    said = hebrew.pairs(ITALIAN_REPLY, "it")
    assert [(p.hebrew, p.english, p.recast) for p in said] == [
        ("Sono andato al mare ieri.", "I went to the sea yesterday.", True),
        ("Com'era l'acqua?", "What was the water like?", False),
    ]
    assert said[0].why == "Andare takes essere in the past."
    assert hebrew.pairs(ITALIAN_REPLY) == [], "read as Hebrew, an Italian reply has no lines"
    assert hebrew.length(ITALIAN_REPLY, "it") == 2, "Com'era and l'acqua; the recast not counted"


def test_the_italian_contract_keeps_the_shape_and_none_of_hebrew_s_own_rules() -> None:
    assert hebrew.contract_for("he") == hebrew.CONTRACT, "a Hebrew turn is held to what it was"
    said = " ".join(hebrew.contract_for("it", "Russian").split())
    assert said.startswith("This conversation is in Italian")
    assert 'every "= " line is in Russian' in said
    assert '"> "' in said and '"~ "' in said and "Natural first" in said
    for hebrew_only in ("nikkud", "ktiv male", "maqaf", "Hebrew"):
        assert hebrew_only not in said, hebrew_only


# --- the three that landed with the connector (#281–#283) ------------------------


def test_every_language_that_talks_has_a_contract_and_the_other_way_round() -> None:
    """A language in one list and not the other is either a conversation with no rules
    or a contract nothing uses."""
    assert set(hebrew.CONTRACTS) | {"he"} == set(hebrew.TALKED)


def test_aramaic_holds_no_conversation() -> None:
    """#284, deferred 2026-09-22: design.md §12 ruled the parallel case for biblical
    Hebrew, and Onkelos and the Gemara are that shelf."""
    assert "arc" not in hebrew.TALKED
    assert "arc" not in hebrew.CONTRACTS
    assert hebrew.contract_for("arc") == hebrew.CONTRACT, "it falls back, and is never reached"


@pytest.mark.parametrize(
    ("code", "named", "own"),
    [
        ("fr", "French", ("accent", "être", "tu", "calques")),
        ("ru", "Russian", ("case", "aspect", "ты", "ё")),
        ("yi", "Yiddish", ("YIVO", "Hebrew alphabet", "German in Hebrew letters", "דו")),
    ],
)
def test_each_new_contract_keeps_the_shape_and_says_its_own_language_s_rules(
    code: str, named: str, own: tuple[str, ...]
) -> None:
    said = " ".join(hebrew.contract_for(code, "Russian").split())
    assert said.startswith(f"This conversation is in {named}")
    assert 'every "= " line is in Russian' in said
    assert '"> "' in said and '"~ "' in said and "Natural first" in said
    assert "never tell the reader they are at a level" in said
    for rule in own:
        assert rule in said, rule


@pytest.mark.parametrize("code", ["fr", "ru", "yi"])
def test_a_new_contract_carries_none_of_hebrew_s_own_spelling_rules(code: str) -> None:
    said = " ".join(hebrew.contract_for(code).split())
    for hebrew_only in ("nikkud", "ktiv male", "maqaf"):
        assert hebrew_only not in said, hebrew_only


@pytest.mark.parametrize("code", ["fr", "ru", "yi", "it"])
def test_none_of_them_corrects_the_reader_s_own_gender(code: str) -> None:
    """The same rule in four languages, because it is the same false correction: a
    woman's sentence put into the masculine is wrong about her, not about her grammar."""
    said = " ".join(hebrew.contract_for(code).split())
    assert "Never change the gender of the reader's own words" in said


def test_yiddish_refuses_the_error_it_exists_to_refuse() -> None:
    """A model asked for Yiddish writes German in Hebrew letters, and it reads as Yiddish
    to anybody who does not know better."""
    said = " ".join(hebrew.contract_for("yi").split())
    assert "Write Yiddish, not German in Hebrew letters" in said
    assert "pass as German with the letters swapped" in said
    # And the spelling rule that is the opposite of Hebrew's.
    assert "YIVO" in said and "takes no points" in said


def test_russian_treats_aspect_as_meaning_rather_than_polish() -> None:
    said = " ".join(hebrew.contract_for("ru").split())
    assert "Aspect is meaning, not polish" in said
    assert "correcting a choice that was not wrong" in said


FRENCH_REPLY = """> Je suis allé à la mer hier.
= I went to the sea yesterday.
~ Aller takes être in the passé composé.
Elle était comment, l'eau ?
= What was the water like?"""

RUSSIAN_REPLY = """> Я вчера ходил на море.
= I went to the sea yesterday.
~ Ходил is the imperfective: it says you went and came back.
А вода была тёплая?
= And was the water warm?"""

YIDDISH_REPLY = """> איך בין געגאַנגען צום ים נעכטן.
= I went to the sea yesterday.
~ צו takes the dative.
װי אַזױ איז געװען דאָס װאַסער?
= What was the water like?"""


@pytest.mark.parametrize(
    ("code", "reply", "recast", "why"),
    [
        ("fr", FRENCH_REPLY, "Je suis allé à la mer hier.", "Aller takes être"),
        ("ru", RUSSIAN_REPLY, "Я вчера ходил на море.", "Ходил is the imperfective"),
        ("yi", YIDDISH_REPLY, "איך בין געגאַנגען צום ים נעכטן.", "צו takes the dative."),
    ],
)
def test_a_reply_in_each_is_read_back_as_pairs(
    code: str, reply: str, recast: str, why: str
) -> None:
    said = hebrew.pairs(reply, code)
    assert len(said) == 2, said
    assert said[0].hebrew == recast and said[0].recast is True
    assert said[0].english == "I went to the sea yesterday."
    assert why in said[0].why
    assert said[1].recast is False and said[1].english


def test_a_french_reply_read_as_hebrew_has_no_lines() -> None:
    """The script settles it where the script can, which is why Yiddish is in
    `HEBREW_SCRIPT` and French is not."""
    assert hebrew.pairs(FRENCH_REPLY) == []
    assert hebrew.pairs(RUSSIAN_REPLY) == []
    assert hebrew.pairs(YIDDISH_REPLY, "yi") == hebrew.pairs(YIDDISH_REPLY, "he")
