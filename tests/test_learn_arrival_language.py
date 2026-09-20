"""Which language a new reader reads, asked first (design.md §12, 2026-09-20).

An account's `reads` decides the language of the line under each Hebrew one and the
language the desk speaks, and a new account was English in both whatever the person
read: the only ways out were a profile page and a question the conversation asks once,
of a browser that already says Russian. So the arrival asks, before it asks anything a
reader would have to read — in every language it offers at once.
"""

from __future__ import annotations

import shutil
from typing import Any

import pytest
from test_learn_js import THREE, draw, reader, seeded

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")

BOTH = ["en", "ru"]
NEW = {"signedIn": True, "learning": ["he"], "reads": ["en"], "readsSaid": False}


def languages_sent(page: dict[str, Any]) -> list[dict[str, Any]]:
    return [call["body"] for call in page["sent"] if "/account/languages" in call["path"]]


def test_a_new_reader_is_asked_which_language_first_and_in_both() -> None:
    first = draw([], shared=seeded(), into=BOTH, me=NEW)
    assert first["step"] == "1 of 3"
    assert first["tongues"] == ["English", "Русский", "Other · Другой"], "each in its own name"
    assert first["tongueAsks"] == ["What is your native language?", "Какой у вас родной язык?"]
    assert not first["subjectsUp"] and first["levels"] == [], "one question a screen"
    assert not first["nextShown"], "pressing a row is the answer, as on the ladder"
    assert not first["backShown"], "and there is nowhere to go back to"


def test_russian_is_kept_told_to_the_account_and_the_page_loaded_again() -> None:
    after = draw([], shared=seeded(), into=BOTH, me=NEW, do=[{"tongue": "Русский"}])
    assert after["heldInto"] == "ru"
    assert after["kept"].get("targum:asked-read") == "1", "so the conversation does not ask again"
    assert languages_sent(after) == [{"learning": ["he"], "reads": ["ru"]}]
    assert after["reloaded"] == 1, "a desk page is drawn by the server in one language"
    assert after["visit"].get("targum:arrival-tongue") == "1"


def test_the_page_comes_back_on_the_second_of_three() -> None:
    """Loaded again in Russian, the arrival is where the reader left it: the subjects,
    as the second of three, with the language one Back away."""
    back = draw(
        [],
        shared=seeded(),
        into=BOTH,
        me={**NEW, "reads": ["ru"], "readsSaid": True},
        held="ru",
        pageLanguage="ru",
        stored={"targum:asked-read": "1"},
        visit={"targum:arrival-tongue": "1"},
    )
    assert back["step"] == "2 of 3" and back["subjectsUp"]
    assert back["backShown"]
    assert back["reloaded"] == 0 and languages_sent(back) == []


def test_english_goes_straight_on_with_nothing_loaded_again() -> None:
    after = draw([], shared=seeded(), into=BOTH, me=NEW, do=[{"tongue": "English"}])
    assert after["heldInto"] == "en"
    assert languages_sent(after) == [{"learning": ["he"], "reads": ["en"]}]
    assert after["reloaded"] == 0
    assert after["step"] == "2 of 3" and after["subjectsUp"]


def test_the_language_may_be_skipped_and_nothing_is_kept() -> None:
    past = draw([], shared=seeded(), into=BOTH, me=NEW, do=[{"press": "arrival-skip"}])
    assert past["step"] == "2 of 3" and past["subjectsUp"]
    assert past["heldInto"] == "" and languages_sent(past) == []
    assert "targum:asked-read" not in past["kept"]


def test_signed_out_the_browser_keeps_it_and_no_account_is_told() -> None:
    local = draw([], shared=seeded(), into=BOTH, do=[{"tongue": "Русский"}])
    assert local["heldInto"] == "ru"
    assert languages_sent(local) == [] and local["reloaded"] == 0
    assert local["step"] == "2 of 3"


@pytest.mark.parametrize(
    "already",
    [
        {"me": {**NEW, "readsSaid": True}},  # said on the profile page, or marked by the operator
        {"me": NEW, "pageLanguage": "ru"},  # the page arrived in Russian: the account reads it
        {"me": NEW, "stored": {"targum:asked-read": "1"}},  # the conversation asked
        {"me": NEW, "into": ["en"]},  # nothing to choose between
    ],
)
def test_somebody_who_has_already_said_is_not_asked(already: dict[str, Any]) -> None:
    options = {"into": BOTH, **already}
    page = draw([], shared=seeded(), **options)
    assert page["step"] == "1 of 2" and page["subjectsUp"] and page["tongues"] == []


def test_a_press_on_the_front_door_is_handed_to_the_new_account() -> None:
    """The switcher on the landing page, carried through sign-in by `signin.js` as what
    this browser reads into. The account has never heard it, so it is told — and the
    reader is not asked a question they answered before they had an account."""
    page = draw([], shared=seeded(), into=BOTH, me=NEW, held="ru")
    assert page["tongues"] == [] and page["step"] == "1 of 2"
    assert languages_sent(page) == [{"learning": ["he"], "reads": ["ru"]}]
    assert page["reloaded"] == 1, "and the page comes back in Russian"


def test_a_choice_the_account_already_has_is_not_sent_again() -> None:
    page = draw([], shared=seeded(), into=BOTH, me={**NEW, "readsSaid": True}, held="ru")
    assert languages_sent(page) == []


def test_the_first_text_is_one_with_their_language_under_it() -> None:
    """The shelf is English throughout and Russian in places. A reader who said Русский
    opens the text in their subjects that has Russian, not the one that would otherwise
    have been picked."""

    def shelf(russian: str) -> list[dict[str, Any]]:
        rows = [
            *seeded(),
            reader("derby", "דרבי", "derby", kind="article", register="modern", tags=["sport"]),
        ]
        for row in rows:
            row["targets"] = ["en", "ru"] if row["name"] == russian else ["en"]
        return rows

    answers = [*THREE, {"press": "arrival-done"}, {"rung": "Just starting"}]
    ordinary = draw([], shared=shelf(""), into=BOTH, held="en", do=answers)["went"]
    assert "/reader/" in ordinary
    # Whichever of the two sport texts the ordinary pick is not, given Russian.
    other = "derby" if "holon" in ordinary else "holon"

    russian = draw([], shared=shelf(other), into=BOTH, held="ru", do=answers)
    assert other in russian["went"], f"the one with Russian under it: {russian['went']}"

    english = draw([], shared=shelf(other), into=BOTH, held="en", do=answers)
    assert english["went"] == ordinary, "a reader of English is sent where they always were"

    nowhere = draw([], shared=shelf(""), into=BOTH, held="ru", do=answers)
    assert nowhere["went"] == ordinary, "and where none has it, what they asked for anyway"


def test_other_is_an_answer_and_reads_english() -> None:
    """A native speaker of neither. Skip says "not now" and keeps nothing; this reader
    means "neither", which is an answer: English, the only other language there is to
    read into, and never asked again."""
    after = draw([], shared=seeded(), into=BOTH, me=NEW, do=[{"tongue": "Other · Другой"}])
    assert after["heldInto"] == "en"
    assert after["kept"].get("targum:asked-read") == "1"
    assert languages_sent(after) == [{"learning": ["he"], "reads": ["en"]}]
    assert after["reloaded"] == 0 and after["step"] == "2 of 3"
