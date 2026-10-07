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


def test_the_line_under_the_box_says_what_continue_will_do() -> None:
    """The line says *before* sending that Continue will look. It no longer prices the
    look: a look is a chat turn, and chatting is included (design.md §12, 2026-09-24;
    COPY_QUESTIONS 14, David 2026-09-28)."""
    said = run(typed="something funny about food", answers=FOUND)
    assert "Press Continue and we'll look for it" in said["under"]
    assert "credits" not in said["under"]


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
    assert "You know about 7 words in 10" in drawn


def test_a_search_says_no_cost_because_chatting_is_included() -> None:
    """It used to say what the turn took, as a clock: "Looking used 0:42 of your
    credits". A search is a turn of chat, and chatting is included (design.md §12,
    2026-09-24), so the line priced something that costs nothing (copy audit, Q14)."""
    said = run(typed="something funny about food", answers=FOUND)
    assert not [line for line in said["status"] if "Looking used" in line]
    assert not [line for line in said["status"] if "$" in line]
    assert "/job/chat-c1-1" not in [one["path"] for one in said["asked"]]


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


def test_a_search_that_found_nothing_says_so() -> None:
    """Saying nothing would read as a page that had not noticed."""
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
    assert not [line for line in said["status"] if "Looking used" in line]


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


def test_a_paste_is_titled_by_its_first_sentence_or_whole_words() -> None:
    """A paste was titled by its first sixty characters, cut through a word: "…ולחם טר"
    for "…ולחם טרי" (2026-09-27)."""
    source = (HARNESS.parents[2] / "src/targum/render/assets/add.js").read_text(encoding="utf-8")
    start = source.index("  var PASTE_TITLE")
    end = source.index("\n  }\n", start) + 4
    lines = [
        "בבוקר הלכתי לשוק עם אמא שלי. קנינו עגבניות, מלפפונים ולחם טרי.",
        "קנינו עגבניות מלפפונים ולחם טרי והמוכר חייך ואמר שהיום יש מבצע על תפוזים",
        "x" * 80,
    ]
    said = f"\nconsole.log(JSON.stringify({json.dumps(lines)}.map(pasteTitle)));"
    script = source[start:end] + said
    done = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=30)
    assert done.returncode == 0, done.stderr
    first, words, long = json.loads(done.stdout)
    assert first == "בבוקר הלכתי לשוק עם אמא שלי"
    assert len(words) <= 60 and lines[1].startswith(words) and lines[1][len(words)] == " "
    assert long == "x" * 60


def test_a_press_that_spends_says_what_beside_it() -> None:
    """Copy audit, 2026-09-28 (Q11). The Add page's card and the chat's card pressed with
    no cost beside them, where the press page, the set page and Telegram said "Uses N
    credits". A recording counts a credit a minute, any part of one a whole one, as
    `builder.credits_of` does; a text uses none; an unknown length says nothing."""
    bring = HARNESS.parents[2] / "src/targum/render/assets/bring.js"
    source = bring.read_text(encoding="utf-8")
    start = source.index("  function uses(job) {")
    end = source.index("\n  }\n", start) + 4
    stubs = (
        "var t = function (k, e) { return e; };"
        "var tn = function (k, n, one, other) {"
        " return (n === 1 ? one : other).replace('{n}', n); };"
    )
    jobs = [
        {"audio": True, "seconds": 62},
        {"audio": True, "seconds": 60},
        {"audio": True, "seconds": 20},
        {"audio": True, "seconds": 0},
        {"audio": False, "segments": 40},
        # One press gets every part (design.md §12, 2026-10-07): the whole length's
        # credits, and how it arrives.
        {"audio": True, "seconds": 1500, "parts": 2},
    ]
    script = (
        stubs + source[start:end] + f"console.log(JSON.stringify({json.dumps(jobs)}.map(uses)));"
    )
    done = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=30)
    assert done.returncode == 0, done.stderr
    assert json.loads(done.stdout) == [
        "Uses 2 credits",
        "Uses 1 credit",
        "Uses 1 credit",
        "",
        "Uses none of your credits",
        "Uses 25 credits · in 2 parts, each made as you reach it",
    ]
    assert "var spends = uses(job);" in source, "on the chat's card"
    add = (HARNESS.parents[2] / "src/targum/render/assets/add.js").read_text(encoding="utf-8")
    offered = add[add.index("  function offer(job) {") :][:2000]
    assert "bringing.uses(job)" in offered, "and on Add's"
