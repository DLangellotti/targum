"""One figure per text, and our estimate until the reader's marks settle it (design.md §12,
"A text's figure is our estimate until your marks settle it" and "Your level comes from
your words check until your marks reach one", both 2026-11-04; David, 2026-11-03).

The reader is the public-beta review's B1 reader abroad (2026-11-03,
intermediate-abroad F-01, F-02, F-05, F-07): "I read the news with help", a strong words
check with no made-up word ticked, and a handful of words marked. Home's card said "7%
known" under a promise of 90%, Your Progress listed texts at 6–8% under "Texts at your
level now", and the level said "Start with beginner texts".
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from targum import catalogue as catalogue_module
from targum import check, coverage, touchstones
from targum import estimate as est
from targum import level as level_module
from targum.accounts import Person, Store
from targum.chat import tools
from targum.coverage import KNOWN, build_index, write_index
from targum.serve import Handler

#: A modern text of everyday Hebrew: one word the reader marked, the rest common words
#: they have not, and two rare ones. Running words, a hundred in all.
TEXT = {
    "בית": 7,  # marked known: the 7% the card printed
    "של": 30,
    "זה": 30,
    "עכשיו": 8,
    "יום": 8,
    "כסף": 8,
    "מקלדת": 5,
    "קוואזר": 4,
}


def _hebrew_list() -> None:
    pytest.importorskip("wordfreq")
    from targum.annotate import frequency

    if not frequency.ranks("he"):
        pytest.skip("wordfreq has no Hebrew list here")


def strong_check() -> list[str]:
    """As the review's reader answered: 17 of round one's 18 real words, most of round
    two's, and no made-up word."""
    first, _ = check.first_round()
    ticked = first[:-1]
    second, _ = check.second_round(ticked)
    ticked += second[:-3]
    return check.kept(ticked)


def signed_in(store: Store) -> Person:
    signed = store.finish_sign_in(store.start_sign_in("abroad@example.com"))
    assert signed is not None
    return signed[0] if isinstance(signed, tuple) else signed


@pytest.fixture
def b1(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    _hebrew_list()
    est.forget()
    news = catalogue_module._entry(
        {
            "id": "everyday-news",
            "title": "everyday-news",
            "language": "he",
            "source": "test:everyday-news",
            "kind": "article",
            "register": "modern",
            "words": 100,
            "difficulty": 10,
        }
    )
    entries = [news]
    lemmas = tmp_path / "lemmas.json"
    write_index(lemmas, build_index({"everyday-news": list(TEXT)}, {"everyday-news": TEXT}))
    monkeypatch.setattr(catalogue_module, "everything", lambda: list(entries))
    monkeypatch.setattr(catalogue_module, "lemmas_path", lambda: lemmas)
    monkeypatch.setattr(tools, "_collections", lambda: {})
    monkeypatch.setattr(tools, "_shelf", lambda ctx, measured=True: ([], []))

    store = Store(tmp_path / "words.db")
    person = signed_in(store)
    store.set_declared(person, "gimel")
    store.set_checked(person, "he", check.VERSION, strong_check())
    store.push(
        person,
        {"words": [{"language": "he", "lemma": "בית", "status": KNOWN, "at": 1, "seen": 1}]},
    )

    class Ctx:
        level = level_module.snapshot(store, person.id, "he")

    ctx = Ctx()
    ctx.store = store  # type: ignore[attr-defined]
    ctx.person = person  # type: ignore[attr-defined]
    ctx.person_id = person.id  # type: ignore[attr-defined]
    return ctx, entries, lemmas, store, person


def test_home_s_card_says_our_estimate_labelled_where_it_said_seven_percent(b1: Any) -> None:
    """F-01: the card's own figure is the one it chose on, and says it is ours."""
    ctx, _, _, _, _ = b1
    row = tools.suggest_next(ctx, {"limit": 1})["suggestions"][0]
    assert row["running_share"] == 0.07, "what the reader marked, as the review saw it"
    assert row["fit"] == "band"
    reason = row["reason"]
    assert reason["key"] == "suggest.estimated" and reason["share"] >= 90, reason
    assert row["estimated"] is True
    said = tools.because_in(row, "en")
    assert said == f"You know about {reason['share']}% of its words (our estimate)."
    assert "около" in tools.because_in(row, "ru")


def test_progress_lists_the_card_s_figure_labelled(b1: Any) -> None:
    """F-02: "Texts at your level now" listed texts at 6–8%."""
    ctx, entries, lemmas, store, person = b1
    index = coverage.read_index(lemmas)
    chances = est.for_reader(store, person.id, "he", ctx.level).chances(index)
    listed = touchstones.at_level(entries, index, store.marked(person, "he"), "he", chances=chances)
    card = tools.suggest_next(ctx, {"limit": 1})["suggestions"][0]
    assert [(row["id"], row["known"], row["estimated"]) for row in listed] == [
        ("everyday-news", card["reason"]["share"], True)
    ]


def test_the_library_says_the_same_figure(b1: Any) -> None:
    """F-07: Library "Not measured yet", Upload 41%, Progress 0%, the chooser 94% — one
    text, four figures. The Library's row now carries the card's."""
    ctx, _, _, store, person = b1
    handler = Handler.__new__(Handler)
    handler.store = store  # type: ignore[misc]
    handler._person = lambda: person  # type: ignore[method-assign]
    row = handler._measure_catalogue()["everyday-news"]
    card = tools.suggest_next(ctx, {"limit": 1})["suggestions"][0]
    assert row["known"] == 0.07, "the marked share is still sent, and still marks only"
    assert round(row["estimated"] * 100) == card["reason"]["share"]


def test_a_text_the_marks_settle_says_what_was_marked(b1: Any) -> None:
    """Once every word of it is marked, the estimate adds nothing and the page says what
    the reader marked, unlabelled."""
    ctx, _, _, store, person = b1
    store.push(
        person,
        {
            "words": [
                {"language": "he", "lemma": lemma, "status": KNOWN, "at": 2, "seen": 2}
                for lemma in TEXT
            ]
        },
    )
    est.forget()
    ctx.level = level_module.snapshot(store, person.id, "he")
    row = tools.suggest_next(ctx, {"limit": 1})["suggestions"][0]
    assert row["reason"]["key"] == "suggest.known" and "estimated" not in row


def test_the_chat_and_the_connector_use_the_chooser_s_estimate(b1: Any) -> None:
    """The chat's own figure for a page counted the commonest words as known for
    everybody. It reads the chooser's estimate now, labelled, and agrees with the card."""
    ctx, _, _, _, _ = b1
    text = " ".join(lemma for lemma, n in TEXT.items() for _ in range(n))
    share, estimated = tools._known_figure(ctx, text)
    card = tools.suggest_next(ctx, {"limit": 1})["suggestions"][0]
    assert estimated is True
    assert level_module.known_percent(share) == card["reason"]["share"]
    assert "של" not in tools._known_forms(ctx), "the commonest words are not known for free"


def test_with_no_mark_and_no_estimate_nothing_is_said() -> None:
    assert est.shown(None, None) == (None, False)
    assert level_module.estimated_line(None) == ""
    assert level_module.estimated_line(0.934) == (
        "You know about 93% of the words here (our estimate)."
    )
