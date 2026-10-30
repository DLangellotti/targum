"""How much Hebrew you understand (targum-internal#575), run rather than read.

design.md §12, "How much Hebrew you understand is measured on a fixed yardstick"
(2026-10-30): the share of a fixed list's running words the reader's known words cover,
on a yardstick they pick, by Week or Month. The server half is `test_understand.py`; this
is the page's own arithmetic, through the `test_progress_js.py` harness.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any

from test_progress_js import day, draw, vocab


def ms(when: date) -> int:
    """Noon on a local day, in milliseconds: a moment no zone pushes into another day."""
    return int(datetime.combine(when, time(12)).timestamp() * 1000)


def months_back(n: int) -> date:
    today = date.today()
    year, month = today.year, today.month - n
    while month < 1:
        month += 12
        year -= 1
    return date(year, month, 1)


def month_name(when: date) -> str:
    return when.strftime("%B") + ("" if when.year == date.today().year else f" {when.year}")


def entry(percent: int, base: float, *gains: tuple[date, float]) -> dict[str, Any]:
    return {
        "percent": percent,
        "base": base,
        "days": [{"day": when.isoformat(), "gain": gain} for when, gain in gains],
    }


def understand(began: date, **registers: dict[str, Any]) -> dict[str, Any]:
    return {"he": {"began": ms(began), "registers": registers}}


HEBREW = {"targum:vocab:he": vocab(known=3)}


def three_months() -> dict[str, Any]:
    """Began two months ago: 79% then, 83% at the end of last month, 87% now on news."""
    began = months_back(2)
    last_month = months_back(1)
    return understand(
        began,
        news=entry(87, 0.79, (last_month + timedelta(days=3), 0.04), (date.today(), 0.04)),
        conversation=entry(93, 0.93),
        bible=entry(54, 0.50, (last_month + timedelta(days=3), 0.04)),
    )


def test_news_opens_and_the_card_stands_in_place_of_words_you_knew() -> None:
    drawn = draw(
        HEBREW,
        reading={"he": {"line": [], "months": 0, "days": [day(date.today(), 90)], "sections": 1}},
        understand=three_months(),
    )
    card = drawn["understand"]
    assert card["shown"] and not drawn["reading"]["shown"], "one card, not two"
    assert card["register"] == "news" and card["chosen"] == "a news article"
    assert card["open"] == "Compare with: a news article"
    # Each choice with its own percentage, in the picker's order; literature has no list
    # yet and is left out rather than said as 0%.
    assert card["options"] == [
        {
            "register": "conversation",
            "name": "Everyday conversation",
            "figure": "93%",
            "selected": "false",
        },
        {"register": "news", "name": "A news article", "figure": "87%", "selected": "true"},
        {"register": "bible", "name": "The Bible", "figure": "54%", "selected": "false"},
    ]


def test_months_draw_a_line_that_climbs_and_the_sentence_says_from_where() -> None:
    began = months_back(2)
    card = draw(HEBREW, understand=three_months())["understand"]
    assert card["by"] == "month", "the coarsest view with two points"
    assert card["figures"] == ["79%", "83%", "87%"]
    assert card["months"] == [
        month_name(began),
        month_name(months_back(1)),
        month_name(months_back(0)),
    ]
    assert card["bold"] == "87%"
    assert card["said"] == (
        "You know 87% of the words in a typical news article,"
        f" up from 79% in {began.strftime('%B')}."
    )
    # Twelve months would reach back past the day the word records began.
    assert card["since"].startswith("Counted since ")


def test_picking_a_yardstick_changes_the_card_and_nothing_else() -> None:
    drawn = draw(HEBREW, understand=three_months(), pick="bible")
    card = drawn["understand"]
    assert card["register"] == "bible" and card["chosen"] == "the Bible"
    assert card["said"].startswith("You know 54% of the words in the Bible, up from 50% in")
    assert [one["selected"] for one in card["options"]] == ["false", "false", "true"]


def test_a_flat_line_says_no_up_from() -> None:
    card = draw(HEBREW, understand=three_months(), pick="conversation")["understand"]
    assert card["said"] == "You know 93% of the words in everyday conversation."


def test_on_the_first_day_it_is_week_one_point_and_says_from_when() -> None:
    today = date.today()
    card = draw(HEBREW, understand=understand(today, news=entry(41, 0.41)))["understand"]
    assert card["shown"] and card["by"] == "week"
    assert card["empty"] == "We'll draw the line once there are two weeks to show."
    assert card["said"] == "You know 41% of the words in a typical news article."
    assert card["since"].startswith("Counted since ")


def test_news_with_no_list_yet_opens_on_the_next_in_order() -> None:
    card = draw(HEBREW, understand=understand(months_back(1), bible=entry(30, 0.3)))["understand"]
    assert card["register"] == "bible"
    assert [one["register"] for one in card["options"]] == ["bible"]


def test_what_was_read_this_month_is_one_small_line() -> None:
    reading = {
        "he": {
            "line": [],
            "months": 1,
            "days": [day(date.today(), 91, tokens=100), day(months_back(1), 10, tokens=100)],
            "sections": 2,
        }
    }
    card = draw(HEBREW, reading=reading, understand=three_months())["understand"]
    assert card["read"] == "In what you read this month you knew 91% of the words."


def test_nothing_known_on_any_list_is_no_card() -> None:
    drawn = draw(HEBREW, understand=understand(months_back(1), news=entry(0, 0.0)))
    assert not drawn["understand"]["shown"]


def test_a_language_with_no_yardstick_keeps_words_you_knew() -> None:
    reading = {
        "he": {
            "line": [],
            "months": 2,
            "days": [day(months_back(1) + timedelta(days=9), 50), day(date.today(), 70)],
            "sections": 2,
        }
    }
    drawn = draw(HEBREW, reading=reading, understand={})
    assert drawn["reading"]["shown"] and not drawn["understand"]["shown"]


def test_a_point_is_never_rounded_into_a_lie() -> None:
    began = months_back(1)
    card = draw(
        HEBREW,
        understand=understand(began, news=entry(99, 0.004, (date.today(), 0.992))),
    )["understand"]
    assert card["figures"] == ["1%", "99%"], "above none is never 0%, under all never 100%"
