"""Russian function words are glossed from a hand table (targum-internal#712).

A meaning is filed once a lemma and shared by every text, and a function word's used to
be decided by the first sentence a reader tapped it in: every как on every Russian card
said "however (concessive: 'no matter how')", уж "already; grass snake", пора "it's time"
under "с тех пор". These are written once, ahead of anything bought, in the glossary a
build writes and on the card's own lookup. Offline: nothing is bought.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from test_gloss_rails import gloss_rows, hosted, post  # noqa: F401

from targum.annotate import closed
from targum.annotate import gloss as gloss_module
from targum.annotate.gloss import Sense, build_glossary, gloss_key
from targum.cache import Cache
from targum.models import Annotation, Token

#: The commonest Russian function lemmas on the laptop's readers, counted 2026-11-19
#: over the closed classes: a sample of the top two hundred, each of which must have a
#: hand-written meaning.
COMMONEST = (
    "и в не что на с как а весь к но то свой так же за у который мой ты тот по это мы "
    "себя один только да о от из бы когда такой вот уже ни теперь очень какой до чтобы "
    "самый ну ещё для или сам ли если даже вдруг опять потом под кто нет без потому "
    "перед наш уж другой тут тоже где наконец там ведь ничто после никогда будто через "
    "каждый тогда всегда надо больше совсем ничего никто здесь можно над зачем при "
    "между хотя назад куда хоть про пока сквозь кроме мимо вместо вокруг"
).split()


def test_the_cards_words_say_their_common_sense() -> None:
    kak = closed.function_gloss("ru", "как")
    assert kak.startswith("how; as; like") and "concessive" not in kak
    assert "snake" not in closed.function_gloss("ru", "уж")
    assert closed.function_gloss("ru", "уж").startswith("already")
    assert "since then" in closed.function_gloss("ru", "пора")
    assert "until now" in closed.function_gloss("ru", "пора")


def test_the_commonest_function_words_are_all_written() -> None:
    missing = [word for word in COMMONEST if not closed.function_gloss("ru", word)]
    assert missing == []


@pytest.mark.parametrize("lemma,meaning", sorted(closed.RUSSIAN.items()))
def test_each_meaning_is_in_the_house_style(lemma: str, meaning: str) -> None:
    """Short, senses after semicolons, nothing a card would show as a note."""
    assert lemma == lemma.lower() and lemma.strip() == lemma
    assert meaning and meaning == meaning.strip() and not meaning.endswith(".")
    assert len(meaning) <= 100
    for note in ("concessive", "grass snake", "(", ")"):
        assert note not in meaning, (lemma, note)


def test_only_russian_into_english_is_answered() -> None:
    assert closed.function_gloss("ru-RU", "как", "en")
    assert closed.function_gloss("ru", "как", "he") == ""
    assert closed.function_gloss("he", "как") == ""
    assert closed.function_gloss("ru", "дом") == "", "a content word is the glossary's"


def _annotation(*lemmas: str) -> Annotation:
    return Annotation(
        document_hash="h",
        language="ru",
        annotator="t",
        method="frequency",
        method_note="n",
        tokens={
            "s1": [Token(start=0, end=1, surface=lemma, lemma=lemma, band=2) for lemma in lemmas]
        },
    )


class Bought:
    name = "fake-gloss/1"

    def __init__(self) -> None:
        self.asked: list[str] = []

    def gloss(self, lemmas, source, target, on_progress=None, contexts=None):  # type: ignore[no-untyped-def]
        self.asked.extend(lemmas)
        return {lemma: Sense(f"bought {lemma}", "noun") for lemma in lemmas}


def test_a_glossary_takes_the_hand_table_over_a_wrong_cached_sense(tmp_path: Path) -> None:
    """The laptop's cache holds как as "however (concessive …)", grounded; a build or a
    free rebuild writes the hand-written meaning instead, and still buys a content word."""
    cache = Cache(tmp_path / "cache")
    provider = Bought()
    for lemma, wrong in (
        ("как", "however (concessive: 'no matter how')"),
        ("уж", "already; grass snake"),
        ("пора", "it's time"),
        ("дом", "house"),
    ):
        cache.put(
            "gloss",
            gloss_key(cache, lemma, "ru", "en", provider.name),
            {"gloss": wrong, "grounded": True},
        )
    glossary, owed = build_glossary(
        _annotation("как", "уж", "пора", "дом", "окно"), "en", provider, cache=cache
    )
    assert glossary.entries["как"].startswith("how; as; like")
    assert "snake" not in glossary.entries["уж"]
    assert "since then" in glossary.entries["пора"]
    assert glossary.entries["дом"] == "house", "a content word keeps what was bought"
    assert provider.asked == ["окно"] and owed == 1, "nothing bought for a function word"


@pytest.fixture
def buys(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    asked: list[str] = []

    def fake(self, lemmas, source, target, on_progress=None, contexts=None):  # type: ignore[no-untyped-def]
        asked.extend(lemmas)
        self._provider.spent.add(self.model or "", 400, 30)
        return {lemma: Sense("however (concessive)", "adverb") for lemma in lemmas}

    monkeypatch.setattr(gloss_module.AnthropicGlosses, "gloss", fake)
    monkeypatch.setattr(gloss_module.AnthropicGlosses, "available", lambda self: (True, ""))
    return asked


def test_a_card_tap_on_a_function_word_answers_the_table_and_buys_nothing(hosted, buys) -> None:  # type: ignore[no-untyped-def]  # noqa: F811
    port, session, store = hosted
    for payload in (
        {"lemma": "как", "source": "ru", "target": "en", "free": True},
        {"lemma": "как", "source": "ru", "target": "en", "sentence": "Как ни старайся."},
    ):
        status, answer = post(port, session, "/gloss", payload)
        assert status == 200
        assert answer["meaning"].startswith("how; as; like") and answer["grounded"] is True
    assert buys == [] and gloss_rows(store) == [], "free: no buy, no claim"
    # A content word still goes to the glossary, and is bought.
    status, answer = post(
        port, session, "/gloss", {"lemma": "окно", "source": "ru", "target": "en"}
    )
    assert status == 200 and buys == ["окно"]


# -- every reader of a held meaning (qa on targum#1340) ---------------------------------


def _wrong_kak(cache: Cache) -> None:
    cache.put(
        "gloss",
        gloss_key(cache, "как", "ru", "en", gloss_module.gloss_provider_name()),
        {"gloss": "however (concessive: 'no matter how')", "grounded": True},
    )


def test_a_held_meaning_is_the_tables_wherever_it_is_read(tmp_path: Path) -> None:
    """`cached_gloss` is what Your Progress, the commonest words, the words to learn first
    and a conversation's lines all read; the table stands ahead of the cache there."""
    cache = Cache(tmp_path / "cache")
    _wrong_kak(cache)
    held = gloss_module.cached_gloss("как", "ru", "en", gloss_module.gloss_provider_name(), cache)
    assert held is not None and held.gloss.startswith("how; as; like") and held.grounded
    assert gloss_module.cached_gloss("как", "ru", "he", "x", cache) is None, "into English only"


def test_your_progress_says_the_tables_meaning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`Handler._held_meaning`, the meaning beside each word met on Your Progress."""
    from targum import serve

    monkeypatch.setattr(gloss_module, "Cache", lambda root=None: Cache(tmp_path / "cache"))
    _wrong_kak(Cache(tmp_path / "cache"))
    reader = type("Reader", (), {"_reading_language": lambda self: "en"})()
    assert serve.Handler._held_meaning(reader, "ru")("как").startswith("how; as; like")


def test_a_conversations_lines_say_the_tables_meaning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`chat/record.py`'s `Recorder.gloss`, the meaning under a word in a conversation."""
    from targum.chat.record import Recorder

    monkeypatch.setattr(gloss_module, "Cache", lambda root=None: Cache(tmp_path / "cache"))
    _wrong_kak(Cache(tmp_path / "cache"))
    assert Recorder().gloss("как", "ru", "en").startswith("how; as; like")


def test_the_commonest_words_say_the_tables_meaning(hosted, monkeypatch) -> None:  # type: ignore[no-untyped-def]  # noqa: F811
    """`/words/common` ("Words you may already know") for a reader learning Russian."""
    import sqlite3

    from test_meanings_itself import get

    port, session, store = hosted
    db = sqlite3.connect(store)
    person = db.execute("SELECT id FROM person WHERE email = 'reader@example.com'").fetchone()[0]
    db.execute(
        "INSERT INTO chosen (person, kind, language, at) VALUES (?, 'learning', 'ru', 1)",
        (person,),
    )
    db.commit()
    db.close()
    from urllib.parse import quote

    answer = get(port, session, "/words/common?language=ru&forms=" + quote("как,уж"))
    meanings = {row["form"]: row["meaning"] for row in answer["words"]}
    assert meanings["как"].startswith("how; as; like")
    assert "snake" not in meanings["уж"]


def test_the_words_to_learn_first_read_through_the_held_meaning() -> None:
    """`Handler._pick_words` asks `cached_gloss` for each word and nothing else, so the
    table stands ahead of the cache there too (its rows need a built shelf to draw)."""
    import inspect

    from targum import serve

    source = inspect.getsource(serve.Handler._pick_words)
    assert "cached_gloss(" in source and 'cache.get("gloss"' not in source


def test_correct_refuses_a_function_word_and_names_the_table(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from typer.testing import CliRunner

    from targum.cli import app

    monkeypatch.setattr(gloss_module, "Cache", lambda root=None: Cache(tmp_path / "cache"))
    said = CliRunner().invoke(
        app,
        ["correct", "как", "--source", "ru", "--meaning", "how", "--store", str(tmp_path / "w.db")],
    )
    assert said.exit_code != 0
    assert "closed.py" in said.output and "function word" in said.output
    # A content word is still corrected, and recorded.
    fine = CliRunner().invoke(
        app,
        [
            "correct",
            "дом",
            "--source",
            "ru",
            "--meaning",
            "house",
            "--store",
            str(tmp_path / "w.db"),
        ],
    )
    assert fine.exit_code == 0, fine.output


def test_ling_ru_s_three_meanings() -> None:
    assert closed.function_gloss("ru", "за") == "behind; beyond; for; after; in [time: за час]"
    assert closed.function_gloss("ru", "к") == "to; towards; by [time: к пяти]"
    assert closed.function_gloss("ru", "о") == "about; of; against [о стену]"
