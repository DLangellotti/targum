"""Words to know first on Home's one card (design.md §12, "Home's one card offers the
words to learn first, and a pick moves easier or harder", 2026-11-05; targum-internal#614):
which words, and `POST /find`'s `words` question."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from test_find_button import on  # noqa: F401 - `on` is a fixture
from test_finds import home, keep  # noqa: F401 - `home` is a fixture
from test_serve import call, sign_in

from targum import preteach
from targum.annotate import gloss
from targum.annotate.gloss import Sense
from targum.finds import button

UNKNOWN = {
    "פיקד": 0.1, "ספד": 0.2, "תרדמת": 0.0, "סיעה": 0.3, "קידם": 0.1, "נוכחי": 0.4,
    "שיבא": 0.0, "בלי": 0.0, "ה": 0.0,
}  # fmt: skip


def p_known(lemma: str) -> float | None:
    if lemma == "התעלם":
        return None
    return UNKNOWN.get(lemma, 0.95)


MEANINGS = {
    "פיקד": "to command",
    "ספד": "to mourn",
    "תרדמת": "coma",
    "סיעה": "faction",
    "קידם": "advance; promote",
    "נוכחי": "current",
    "שיבא": "Sheba Medical Center",
}


def test_the_words_are_unknown_ones_met_three_times_most_often_first_at_most_five() -> None:
    counts = {
        "פיקד": 5, "ספד": 4, "תרדמת": 3, "סיעה": 3, "קידם": 6, "נוכחי": 7,
        "בית": 40,  # known
        "חדש": 2,  # met twice
        "התעלם": 9,  # ignored
    }  # fmt: skip
    got = preteach.words(counts, p_known, MEANINGS.get)
    assert [(one.lemma, one.count) for one in got] == [
        ("נוכחי", 7), ("קידם", 6), ("פיקד", 5), ("ספד", 4), ("סיעה", 3),
    ]  # fmt: skip
    assert got[0].state() == {"lemma": "נוכחי", "meaning": "current", "count": 7}


def test_a_name_and_a_word_with_no_meaning_are_left_out_and_under_three_is_nothing() -> None:
    counts = {"שיבא": 9, "פיקד": 5, "ספד": 4, "תרדמת": 3, "בלי": 8}
    got = preteach.words(counts, p_known, lambda lemma: MEANINGS.get(lemma, ""))
    assert [one.lemma for one in got] == ["פיקד", "ספד", "תרדמת"]
    fewer = preteach.words({"פיקד": 5, "ספד": 4, "שיבא": 9}, p_known, MEANINGS.get)
    assert fewer == [], "two words is no list"


def test_a_clitic_is_never_a_word_to_learn() -> None:
    from targum.touchstones import a_word

    counts = {"ה": 30, "פיקד": 5, "ספד": 4, "תרדמת": 3}
    got = preteach.words(counts, p_known, lambda lemma: "the", a_word)
    assert [one.lemma for one in got] == ["פיקד", "ספד", "תרדמת"]


@pytest.mark.parametrize(
    ("meaning", "named"),
    [("Sheba Medical Center", True), ("Шиба", True), ("to command", False), ("кома", False),
     ("", False), ("(of) faction", False)],
)  # fmt: skip
def test_a_meaning_with_a_capital_reads_as_a_name(meaning: str, named: bool) -> None:
    assert preteach.looks_like_a_name(meaning) is named


def test_post_find_words_answers_a_find_s_words_with_the_glossary_s_meanings(
    home: Any,  # noqa: F811
    on: None,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from targum import estimate

    monkeypatch.setattr(
        estimate, "for_reader", lambda *args, **kwargs: SimpleNamespace(p_known=p_known)
    )
    bought: list[str] = []

    def cached(lemma: str, source: str, target: str, provider: str, cache: Any = None) -> Any:
        bought.append(lemma)
        if lemma == "פיקד (verb)":
            return Sense("to command")
        said = {k: v for k, v in MEANINGS.items() if k != "פיקד"}.get(lemma)
        return Sense(said) if said else None

    monkeypatch.setattr(gloss, "cached_gloss", cached)
    found = keep(home.store, "https://a.example/sharon", {"פיקד": 5, "ספד": 4, "תרדמת": 3,
                                                           "שיבא": 6, "בית": 40})  # fmt: skip
    cookie = sign_in(home.port, home.postbox)
    status, got, _ = call(
        home.port, "POST", "/find", {"language": "he", "words": {"find": found}}, cookie=cookie
    )
    assert status == 200, got
    assert [one["lemma"] for one in got["words"]] == ["פיקד", "ספד", "תרדמת"], got
    assert got["words"][0] == {"lemma": "פיקד", "meaning": "to command", "count": 5}
    assert got["into"] == "en"
    assert "פיקד (verb)" in bought, "a verb's meaning is filed under its verb key"
    status, none, _ = call(
        home.port, "POST", "/find", {"language": "he", "words": {"find": 999}}, cookie=cookie
    )
    assert status == 200 and none["words"] == []
    status, shelf, _ = call(
        home.port, "POST", "/find", {"language": "he", "words": {"id": "nowhere"}}, cookie=cookie
    )
    assert status == 200 and shelf["words"] == []


def test_post_find_words_is_behind_the_switch(home: Any) -> None:  # noqa: F811
    assert not button.on()
    cookie = sign_in(home.port, home.postbox)
    status, _, _ = call(
        home.port, "POST", "/find", {"language": "he", "words": {"find": 1}}, cookie=cookie
    )
    assert status == 404
