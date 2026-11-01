"""The words check on the arrival, run rather than read (design.md §12, "The arrival asks
which words you know", 2026-11-01; targum-internal#613).

After the level, a Hebrew reader is shown two rounds of words to tap, the second chosen
from the first; then a line of thanks, and the first text. Skip goes straight home. Same
harness as `test_arrival_js.py`, with the check's lists handed in as the page has them.
"""

from __future__ import annotations

import itertools
import shutil
from typing import Any

import pytest

from targum import check
from tests.test_arrival_js import draw, seeded

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")

SIGNED_IN = {"signedIn": True, "learning": ["he"], "readsSaid": True}
#: Past the language, the subjects (one the seeded shelf can answer) and the level.
TO_CHECK = [
    {"press": "arrival-done"},
    {"subject": "News"},
    {"press": "arrival-done"},
    {"rung": "I can read simple"},
    {"press": "arrival-done"},
]


def run(do: list[dict[str, Any]], **options: Any) -> dict[str, Any]:
    options.setdefault("me", SIGNED_IN)
    return draw([], shared=seeded(), check=check.page_data(), do=do, **options)


def test_after_the_level_a_hebrew_reader_is_asked_which_words_they_know() -> None:
    """Round one: eighteen real words and four made-up, in one mixed order, none pressed,
    the step counted with the rest, Skip beside Next."""
    page = run(TO_CHECK)
    assert page["checkUp"] and not page["levelUp"]
    assert page["step"] == "4 of 5"
    real, made = check.first_round()
    assert sorted(page["words"]) == sorted([*real, *made])
    assert page["words"] != [*real, *made], "mixed, so the commonest do not come first"
    assert page["ticked"] == [] and page["tapped"] == "None tapped"
    assert page["skipShown"] and page["doneSays"] == "Next" and page["backShown"]


def test_the_step_count_says_five_for_hebrew_and_three_for_the_rest() -> None:
    """The check is Hebrew's: the count says so from the first screen, and changes with
    the language pressed."""
    assert run([])["step"] == "1 of 5"
    russian = run([{"learn": "Russian"}])
    assert russian["step"] == "1 of 3"
    to_level = run([{"learn": "Russian"}, {"press": "arrival-done"}, {"press": "arrival-done"}])
    assert to_level["levelUp"] and to_level["step"] == "3 of 3"
    ends = run(
        [
            {"learn": "Russian"},
            {"press": "arrival-done"},
            {"press": "arrival-done"},
            {"rung": "I read almost anything"},
            {"press": "arrival-done"},
        ]
    )
    assert not ends["checkUp"] and "/account/check" not in ends["posted"]


def test_a_tap_presses_a_word_and_a_second_lets_it_go() -> None:
    page = run([*TO_CHECK, {"tick": "עכשיו"}, {"tick": "דרך"}, {"tick": "תלבוטה"}])
    assert sorted(page["ticked"]) == sorted(["עכשיו", "דרך", "תלבוטה"])
    assert page["tapped"] == "3 tapped"
    again = run([*TO_CHECK, {"tick": "עכשיו"}, {"tick": "עכשיו"}])
    assert again["ticked"] == [] and again["tapped"] == "None tapped"


def test_round_two_is_the_round_check_py_would_draw() -> None:
    """Round two follows from round one's ticks by the same rules on the page and on the
    server, which is what lets the account keep the ticks alone."""
    ticks = [*check.BANDS[0][:3], *check.BANDS[1][:3], *check.BANDS[2][:2]]
    page = run([*TO_CHECK, *({"tick": word} for word in ticks), {"press": "arrival-done"}])
    assert page["checkUp"] and page["step"] == "5 of 5" and page["doneSays"] == "Done"
    real, made = check.second_round(ticks)
    assert sorted(page["words"]) == sorted([*real, *made])
    assert page["ticked"] == [], "round two's words are new"


def test_the_page_and_check_py_agree_on_every_round_two() -> None:
    """Every edge, and patterns that are not a clean climb."""
    first = [band[: check.FIRST] for band in check.BANDS]
    patterns: list[list[str]] = [[]]
    for at in range(len(check.BANDS)):
        patterns.append([word for band in first[: at + 1] for word in band])
    for one, two in itertools.combinations(range(len(check.BANDS)), 2):
        patterns.append([*first[one][:2], *first[two][:1]])
        patterns.append([*first[two][:2], check.MADE_UP[0]])
    page = draw([], shared=seeded(), check=check.page_data(), secondFrom=patterns)
    first_real, first_made = check.first_round()
    assert [item["word"] for item in page["checkFirst"]] == [*first_real, *first_made]
    for ticks, drawn in zip(patterns, page["checkSecond"], strict=True):
        real, made = check.second_round(ticks)
        assert [item["word"] for item in drawn] == [*real, *made], ticks


def test_done_sends_the_ticks_alone_and_thanks_them() -> None:
    """Both rounds' ticks go to the account with the lists' version; the thanks has no
    count over it and no way back, and Continue opens the first text."""
    page = run(
        [
            *TO_CHECK,
            {"tick": "עכשיו"},
            {"tick": "תלבוטה"},
            {"press": "arrival-done"},
            {"tick": check.BANDS[1][3]},
            {"press": "arrival-done"},
        ]
    )
    assert page["thanksUp"] and not page["checkUp"]
    assert page["step"] == "" and not page["backShown"] and not page["skipShown"]
    assert page["doneSays"] == "Continue"
    sent = [call["body"] for call in page["sent"] if call["path"].startswith("/account/check")]
    assert sent == [{"version": check.VERSION, "ticked": ["עכשיו", "תלבוטה", check.BANDS[1][3]]}]
    assert not page["went"], "the thanks waits for Continue"
    opened = run(
        [*TO_CHECK, {"press": "arrival-done"}, {"press": "arrival-done"}, {"press": "arrival-done"}]
    )
    assert "/reader/" in opened["went"], "Continue opens the first text"
    assert opened["kept"].get("targum:welcomed") == "1"


def test_the_first_text_goes_by_the_rung_the_check_measured() -> None:
    """The account answers with the rung the estimate now stands nearest; the first text
    is picked by it, where the level said would have picked another."""
    shelf = [
        dict(row, level={"name": name})
        for row, name in zip(
            [
                *seeded()[:1],
                *(
                    {**seeded()[2], "name": f"t-{name}", "title": name, "document": f"t-{name}"}
                    for name in ("easy", "hard")
                ),
            ],
            ("aleph", "bet", "hey"),
            strict=True,
        )
    ]
    finish = [{"press": "arrival-done"}] * 3
    said = draw([], shared=shelf, check=check.page_data(), me=SIGNED_IN, do=[*TO_CHECK, *finish])
    measured = draw(
        [],
        shared=shelf,
        check=check.page_data(),
        me=SIGNED_IN,
        checked={"signedIn": True, "rung": "hey"},
        do=[*TO_CHECK, *finish],
    )
    assert "t-easy" in said["went"], said["went"]
    assert "t-hard" in measured["went"], measured["went"]


def test_skip_goes_straight_home_and_keeps_nothing_of_the_check() -> None:
    """Past the thanks (David, 2026-11-01): home, the level they said kept, the arrival
    over, and no tick sent — not even round one's."""
    for at_round_two in (False, True):
        steps = [*TO_CHECK, {"tick": "עכשיו"}]
        if at_round_two:
            steps.append({"press": "arrival-done"})
        page = run([*steps, {"skip": True}])
        assert page["home"] == "/?k=k", page["home"]
        assert not page["went"]
        assert "/account/check" not in page["posted"]
        assert {"path": "/account/level?k=k", "body": {"level": "bet"}} in page["sent"]
        assert page["kept"].get("targum:welcomed") == "1"
        assert "targum:arrival-ticked" not in page["visit"]


def test_back_from_round_two_keeps_round_ones_ticks() -> None:
    page = run([*TO_CHECK, {"tick": "עכשיו"}, {"press": "arrival-done"}, {"back": True}])
    assert page["checkUp"] and page["step"] == "4 of 5"
    assert page["ticked"] == ["עכשיו"]


def test_a_reload_on_round_two_draws_the_round_the_first_chose() -> None:
    """The ticks are kept for the tab, so a reload does not redraw round two as if round
    one had been left empty."""
    ticks = [word for band in check.BANDS[:5] for word in band[: check.FIRST]]
    import json

    page = run(
        [],
        visit={
            "targum:arrival-underway": "check2",
            "targum:arrival-ticked": json.dumps(ticks, ensure_ascii=False),
        },
    )
    assert page["checkUp"] and page["step"] == "5 of 5"
    real, made = check.second_round(ticks)
    assert sorted(page["words"]) == sorted([*real, *made])


def test_not_sure_still_shows_a_page_at_once() -> None:
    """ "I'm not sure, show me a page" promises a page, and keeps the promise: the check
    is the way on from a level said, not from not saying one."""
    page = run([{"press": "arrival-done"}, {"press": "arrival-done"}, {"unsure": True}])
    assert "/reader/" in page["went"] and not page["checkUp"]
