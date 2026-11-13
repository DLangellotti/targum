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
    assert "Press Upload and we'll look for it" in said["under"]
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
    assert "You know 70% of the words" in drawn
    assert "in 10" not in drawn


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
    offered = add[add.index("  function offer(job) {") :][:2600]
    assert "bringing.uses(job)" in offered, "and on Add's"


def test_a_verse_of_the_torah_opens_its_portion_and_is_never_a_search() -> None:
    """Continue on "Genesis 12:1" opens the portion that reads it (targum-internal#446).
    Asked of `/already` before anything else, because a press can come before the answer
    to the typing has: unasked, the reference was a description, and a description is a
    turn of the conversation."""
    said = run(
        typed="Genesis 12:1",
        answers={"/already": {"id": "parasha-lech-lecha", "opens": "/torah/Genesis.12.1"}},
    )
    paths = [one["path"] for one in said["asked"]]
    assert said["went"].startswith("/torah/Genesis.12.1")
    assert "/chat" not in paths and not [path for path in paths if path.startswith("/job")]
    assert "/prepare" not in paths and "/describe" not in paths


def test_words_that_are_not_a_reference_go_on_as_they_did() -> None:
    said = run(typed="something funny about food", answers=FOUND)
    assert "/torah/" not in str(said["went"]), "it went nowhere"
    assert "/already" in [one["path"] for one in said["asked"]]


def test_the_chat_card_says_an_exact_percentage() -> None:
    """David, 2026-10-29 (targum-internal#560): the chat's press card says how much of a
    text you know as an exact percentage, the way `level.known_line` does, and never
    rounds into a lie."""
    bring = HARNESS.parents[2] / "src/targum/render/assets/bring.js"
    source = bring.read_text(encoding="utf-8")
    start = source.index("  function knownLine(share, estimated) {")
    end = source.index("\n  }\n", start) + 4
    stubs = "var t = function (k, e, fill) { return e.replace('{n}', fill ? fill.n : '{n}'); };"
    shares = [0.72, 0.123, 1, 0, 0.996, 0.004, None]
    script = (
        stubs
        + source[start:end]
        + f"console.log(JSON.stringify({json.dumps(shares)}.map((s) => knownLine(s))"
        + ".concat([knownLine(0.934, true)])));"
    )
    done = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=30)
    assert done.returncode == 0, done.stderr
    assert json.loads(done.stdout) == [
        "You know 72% of the words here.",
        "You know 12% of the words here.",
        "You know 100% of the words here.",
        "You know 0% of the words here.",
        "You know 99% of the words here.",
        "You know 1% of the words here.",
        "",
        # Our estimate says so (design.md §12, 2026-11-04).
        "You know about 93% of the words here (our estimate).",
    ]


def test_the_found_rows_never_round_into_a_lie() -> None:
    """qa on targum#993: 0.996 is never 100% and 0.004 never 0%, on the add page as in
    `level.known_percent`."""
    found = json.loads(json.dumps(FOUND))
    rows = found["/chat/turn/c1/1"]["found"]
    rows[0]["known_share"] = 0.996
    rows[1]["known_share"] = 0.004
    said = run(typed="something funny about food", answers=found)
    drawn = " ".join(" ".join(card) for card in said["cards"])
    assert "You know 99% of the words" in drawn and "You know 1% of the words" in drawn
    assert "100%" not in drawn and " 0%" not in drawn


def test_the_text_card_never_rounds_into_a_lie() -> None:
    """card-text.js keeps the same rule as `level.known_percent` (qa on targum#993)."""
    card = HARNESS.parents[2] / "src/targum/render/assets/card-text.js"
    source = card.read_text(encoding="utf-8")
    start = source.index("  function known(share) {")
    end = source.index("\n  }\n", start) + 4
    stubs = "var said = function (name, fill) { return fill.n + '%'; };"
    shares = [0.996, 0.004, 1, 0, 0.72, None, ""]
    script = (
        stubs + source[start:end] + f"console.log(JSON.stringify({json.dumps(shares)}.map(known)));"
    )
    done = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=30)
    assert done.returncode == 0, done.stderr
    assert json.loads(done.stdout) == ["99%", "1%", "100%", "0%", "72%", "", ""]


# -- the finish bar on Upload (targum-internal#715) ------------------------------------

VIDEO = "https://www.youtube.com/watch?v=abcdefghijk"
QUOTED = {
    "id": "j1",
    "stage": "ready",
    "audio": True,
    "seconds": 600,
    "title": "סרטון על אוכל",
    "language": "he",
    "known_share": 0.87,
    "show": "Kan Educational",
    "presenter": "Dana",
}


def card(**payload: Any) -> dict[str, Any]:
    return run(typed=VIDEO, card=True, **payload)


def test_a_video_quote_says_how_much_you_know_when_what_was_found_cannot() -> None:
    """A video's lookup carries no share, and "What we found" drawn above the card hid
    the card's own 87% (design, P2-2)."""
    said = card(answers={"/describe": {"kind": "video", "seconds": 600}, "/prepare": QUOTED})
    assert "You know 87% of the words here." in said["status"]
    # Where what was found said it, it is said once.
    found = card(
        answers={
            "/describe": {"kind": "article", "minutes": 4, "known_share": 0.5},
            "/prepare": {**QUOTED, "audio": False, "known_share": 0.5},
        }
    )
    assert sum("50%" in line for line in found["status"][-12:]) == 1


def test_the_quote_names_the_show_and_who_presents_it() -> None:
    """#691 asked for title, show and who on the card (design, P2-3)."""
    said = card(answers={"/describe": {}, "/prepare": QUOTED})
    names = [run_ for run_ in said["drawn"] if run_["tag"] == "bdi"]
    assert [one["text"] for one in names] == ["Kan Educational", "Dana"]
    assert all(one["dir"] == "auto" and one["lang"] == "" for one in names), names


def test_in_the_library_keeps_one_filled_press_and_puts_the_line_away() -> None:
    """Upload and Open were both filled, and "We'll work out how long it'll take" stood
    beside "…is in the Library, ready to open" (design, P2-4, P2-8). The title is set
    as Hebrew (P2-5)."""
    said = card(
        answers={
            "/prepare": {
                "catalogue": {
                    "id": "t1",
                    "title": "שלום עולם",
                    "language": "he",
                    "shelved": True,
                    "translations": [],
                }
            }
        }
    )
    filled = [p["text"] for p in said["presses"] if "filled" in p["className"].split()]
    assert filled == ["Open"] and said["go"] == ["tonal"]
    assert said["underHidden"], "the line under the box is put away"
    (title,) = [one for one in said["drawn"] if one["tag"] == "b"]
    assert title["lang"] == "he" and title["dir"] == "auto"


def test_done_keeps_one_filled_press() -> None:
    said = card(
        answers={
            "/describe": {},
            "/prepare": QUOTED,
            "/build": {"id": "j1", "stage": "queued"},
            "/job/j1": {"id": "j1", "stage": "done", "reader": "t/reader"},
        },
        press=["Confirm"],
    )
    assert "Open it" in [p["text"] for p in said["presses"]]
    assert said["go"] == ["tonal"], "Upload steps back while Open it is up"


def test_a_stopped_build_ends_with_a_way_on() -> None:
    """Cancelled and stopped ended on a sentence with nothing to press (design, P2-7)."""
    said = card(
        answers={
            "/describe": {},
            "/prepare": QUOTED,
            "/build": {"id": "j1", "stage": "queued"},
            "/job/j1": {
                "id": "j1",
                "stage": "cancelled",
                "said": "You stopped it. It used 2 credits.",
            },
        },
        press=["Confirm"],
    )
    assert "You stopped it. It used 2 credits." in said["status"]
    assert "Upload something else" in [p["text"] for p in said["presses"]]


def test_waiting_behind_others_is_said_once() -> None:
    """ "Waiting behind 2 builds" and "It's waiting to start, behind 2 other texts." said
    one thing twice, in two words (design, P2-6). The card's own Cancel says Cancel."""
    waiting = {
        "id": "j1",
        "stage": "queued",
        "behind": 2,
        "said": "It's waiting to start, behind 2 other texts.",
        "cancellable": True,
    }
    said = card(
        answers={
            "/describe": {},
            "/prepare": QUOTED,
            "/build": waiting,
            "/job/j1": waiting,
        },
        press=["Confirm"],
    )
    words = " ".join(said["status"])
    assert "Waiting behind" not in words and "build" not in words
    assert "It's waiting to start, behind 2 other texts." in said["status"]
    assert "Cancel" in [p["text"] for p in said["presses"]]


def test_the_description_search_sets_a_hebrew_title_as_hebrew() -> None:
    found = json.loads(json.dumps(FOUND))
    found["/chat/turn/c1/1"]["found"][0]["title"] = "פודקאסט על אוכל"
    found["/chat/turn/c1/1"]["found"][0]["language"] = "he"
    said = run(typed="something funny about food", answers=found, card=True)
    titles = [one for one in said["drawn"] if one["className"] == "found-title"]
    hebrew = [one for one in titles if one["text"] == "פודקאסט על אוכל"]
    assert hebrew and hebrew[0]["lang"] == "he" and hebrew[0]["dir"] == "auto", titles


def test_file_sizes_are_said_in_the_page_language() -> None:
    """«9 KB» on the Russian page (ling-ru, P2-11): the units are strings now."""
    source = (HARNESS.parents[2] / "src/targum/render/assets/add.js").read_text(encoding="utf-8")
    assert '+ " KB"' not in source and '+ " MB"' not in source
    ru = json.loads((HARNESS.parents[2] / "src/targum/strings/ru.json").read_text(encoding="utf-8"))
    assert ru["add.size.kb"] == "{n} КБ" and ru["add.size.mb"] == "{n} МБ"
    assert all(
        ru[f"add.quote.left.{form}"].startswith("Баллов")
        for form in ("one", "few", "many", "other")
    )
