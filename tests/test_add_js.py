"""Add's description box (targum-internal#253), run rather than read.

Add had no harness at all until this card put a spending path on it: a description
pressed with Continue runs one turn of conversation in place, and that press is what
spends. The acceptance is about what the page does *not* do as much as what it does, and
that is not a thing reading the source establishes.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import pytest

HARNESS = Path(__file__).resolve().parent / "js" / "add.js"

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")


def run(**payload: Any) -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as where:
        path = Path(where) / "payload.json"
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        done = subprocess.run(
            ["node", str(HARNESS), str(path)], capture_output=True, text=True, timeout=60
        )
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


#: A turn that found two things, in two media. The rows are what `search_sources` puts
#: on the feed and `_chat_turn_state` hands back under `found`.
FOUND = {
    "/chat/say": {"chat": "c1", "turn": 1},
    "/chat/turn/c1/1": {
        "done": True,
        "text": "Here are a few.",
        "quotes": [],
        "found": [
            {
                "title": "A podcast about food",
                "link": "https://a.example/1",
                "kind": "podcast",
                "publisher": "Kan",
                "seconds": 900,
                "known_share": 0.7,
            },
            {"title": "An article about food", "link": "https://b.example/2", "kind": "news"},
        ],
    },
    "/job/chat-c1-1": {"seconds": 42},
}


def test_the_line_under_the_box_says_that_looking_spends_before_it_does() -> None:
    """The card asks for it in as many words: the line says *before* sending that looking
    is a turn of conversation. A page that only said so afterwards would be telling
    somebody what they had already spent."""
    said = run(typed="something funny about food", answers=FOUND)
    assert "Press Continue and we'll look" in said["under"]
    assert "one turn of conversation" in said["under"]
    assert "off your hours" in said["under"]


def test_a_description_looks_in_place_and_never_prices_anything_itself() -> None:
    """Acceptance 1: *a description never quotes or builds by itself*.

    Asserted on what was asked rather than on what was drawn, because that is where the
    money is: the press reaches `/chat/say` and nothing else. No `/prepare`, which is
    where a text is priced, and no `/build`, which is where one is paid for.
    """
    said = run(typed="something funny about food", answers=FOUND)
    paths = [one["path"] for one in said["asked"]]

    assert "/chat/say" in paths, "the turn ran"
    assert "/prepare" not in paths, "nothing was priced"
    assert "/build" not in paths, "nothing was bought"

    turn = next(one for one in said["asked"] if one["path"] == "/chat/say")
    assert turn["method"] == "POST"
    assert turn["body"]["text"] == "something funny about food"


def test_the_results_carry_more_than_one_medium() -> None:
    """Acceptance 2: results carry at least two media when the search found them. The
    card's whole argument is that a description is answered with podcasts, articles and
    videos together rather than with a list of one kind."""
    said = run(typed="something funny about food", answers=FOUND)
    assert said["cards"], "two results were found, so two cards are drawn"
    drawn = " ".join(" ".join(card) for card in said["cards"])
    assert "a recording" in drawn and "an article" in drawn

    # And each says what it is worth knowing before choosing: how long, and how much of
    # it this reader already knows.
    assert "15:00" in drawn
    assert "7 words in ten you know" in drawn


def test_what_the_turn_cost_is_said_after_it_is_over() -> None:
    """The other half of the card's sentence about cost. In the clock the rest of the
    page uses and never in money — design.md takes that position and this keeps it."""
    said = run(typed="something funny about food", answers=FOUND)
    assert "Looking used 0:42 of your hours." in said["status"]
    assert not [line for line in said["status"] if "$" in line]


def test_choose_is_the_pasted_link_path_rather_than_a_copy_of_it() -> None:
    """Acceptance 1's other half: *Choose then the reader's press does*.

    Choose puts the link in the box and presses Continue, so what a chosen result gets is
    not a second implementation of the found card and the price — it is the one a pasted
    link gets, reached the same way. `/describe` then `/prepare` is exactly that path.
    """
    said = run(typed="something funny about food", answers=FOUND, choose=0)
    assert said["afterChoose"]["box"] == "https://a.example/1", "the link is in the box"
    assert said["afterChoose"]["asked"] == ["/describe", "/prepare"]
    # Still nothing bought: `/prepare` prices, and the reader's next press is what buys.
    assert "/build" not in said["afterChoose"]["asked"]


def test_a_search_that_found_nothing_says_so_and_still_says_what_it_cost() -> None:
    """A turn that found nothing was still a turn, and the reader is told what it took.
    Saying nothing would read as a page that had not noticed."""
    said = run(
        typed="something nobody has written",
        answers={
            "/chat/say": {"chat": "c2", "turn": 1},
            "/chat/turn/c2/1": {"done": True, "text": "", "quotes": [], "found": []},
            "/job/chat-c2-1": {"seconds": 12},
        },
    )
    assert said["cards"] == []
    assert any("didn't find anything" in line for line in said["status"])
    assert "Looking used 0:12 of your hours." in said["status"]


def test_a_turn_that_fails_says_so_rather_than_drawing_an_empty_block() -> None:
    said = run(
        typed="something funny about food",
        answers={
            "/chat/say": {"chat": "c3", "turn": 1},
            "/chat/turn/c3/1": {"done": True, "error": "The model is not reachable.", "found": []},
        },
    )
    assert any("not reachable" in line for line in said["status"])
    assert said["cards"] == []
