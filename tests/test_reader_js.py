"""The reader's script, run rather than read — the parts of it that need no browser.

Two of them shipped bugs, both found by a person looking at a screen, which is the
expensive way. Both are also decidable without one: where a card lands beside a word is
arithmetic, and whether a hover survives the keypress that marked the word under it is a
two-state machine.

The third is the word queue the arrow keys walk. It never shipped a bug because it is
new, and it is here for the same reason the other two are: it is settled entirely in the
chapter data and the vocabulary, without asking the page anything.

**What this does not cover.** Everything else in `reader.js` — marking words, rebuilding
a sentence's spans, the word list, and reaching a queued word once the queue has chosen
it — goes through `innerHTML` and a `TreeWalker`, and a stub document cannot honestly
pretend to be either. That half still wants a real browser, and the engineering notes
still say so. This is the part that can be had for free.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

HARNESS = Path(__file__).resolve().parent / "js" / "reader.js"

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")

#: The window a reader is most likely to be in, and a card with something in it — a verb
#: with its root, a note field, the levels row.
WINDOW = {"width": 1200, "height": 800}
CARD = {"width": 320, "height": 200}


def word(top: int, height: int = 24, left: int = 500, width: int = 60) -> dict[str, int]:
    return {"top": top, "bottom": top + height, "left": left, "width": width}


def run(
    words: list[dict[str, int]],
    card: dict[str, int] | None = None,
    **chapter: Any,
) -> dict[str, Any]:
    payload = {"window": WINDOW, "card": card or CARD, "words": words, **chapter}
    where = Path(subprocess.run(["mktemp"], capture_output=True, text=True).stdout.strip())
    where.write_text(json.dumps(payload), encoding="utf-8")
    try:
        done = subprocess.run(
            ["node", str(HARNESS), str(where)], capture_output=True, text=True, timeout=60
        )
    finally:
        where.unlink(missing_ok=True)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def placed(words: list[dict[str, int]], card: dict[str, int] | None = None) -> list[dict[str, Any]]:
    return [row["card"] for row in run(words, card)["placed"]]


def test_a_card_sits_below_a_word_with_room_under_it() -> None:
    (card,) = placed([word(60)])
    assert card["top"] > 84, "below the word, not on it"


def test_a_card_goes_above_a_word_near_the_bottom() -> None:
    (card,) = placed([word(700)])
    assert card["bottom"] <= 700, "clear of the word"


@pytest.mark.parametrize("top", [40, 200, 380, 500, 700])
def test_a_card_never_covers_the_word_it_is_about(top: int) -> None:
    """The bug, at every height a word can sit at.

    A card taller than the space above used to be pushed back down over the word by a
    floor of 8px — which is precisely the word you are looking at while you decide what
    to do with it.
    """
    tall = {"width": 320, "height": 600}
    (card,) = placed([word(top)], tall)
    here = word(top)
    overlaps = card["top"] < here["bottom"] and card["bottom"] > here["top"]
    assert not overlaps, f"card {card['top']}–{card['bottom']} over word {top}–{here['bottom']}"


def test_a_card_too_tall_for_either_side_is_capped_rather_than_moved() -> None:
    """Neither side can hold it, so it takes the roomier one and scrolls inside it.
    Covering the word is never the answer."""
    (card,) = placed([word(380)], {"width": 320, "height": 600})
    assert card["capped"], "it has to give somewhere, and height is where"
    assert card["height"] < 600
    assert 0 <= card["top"] and card["bottom"] <= WINDOW["height"], "and stays on screen"


@pytest.mark.parametrize("left", [0, 40, 600, 1140, 1190])
def test_a_card_stays_inside_the_window(left: int) -> None:
    """A word at the edge of an RTL page is at the right, and a card centred on it would
    hang off the side."""
    (card,) = placed([word(200, left=left)])
    assert card["left"] >= 12
    assert card["left"] + CARD["width"] <= WINDOW["width"] - 12 + 1


def test_hover_lets_go_of_a_word_marked_from_the_keyboard() -> None:
    """`:hover` does not end until the pointer moves, so a word marked known while the
    pointer sat on it stayed lit — known, and still highlighted as though it were being
    looked up."""
    hover = run([word(100)])["hover"]

    assert hover["started"] is True, "hovering is the ordinary state"
    assert hover["afterKey"] == {"hovering": False, "marked": True}, "the key turns it off"
    assert hover["afterMove"] == {"hovering": True, "marked": False}, "the pointer gives it back"


# --- the word queue the arrows walk ----------------------------------------------

#: A chapter is `{segment id: [[start, end, band, split, lemma index], ...]}`, which is
#: what `builder.py` embeds. Offsets are into the bare text of that one sentence.
KNOWN = 9
IGNORED = 0


def chapter(*sentences: list[str]) -> tuple[dict[str, list[list[int]]], list[str]]:
    """Sentences of words, written out as the reader receives them.

    The words are spelt rather than numbered, and their offsets follow from their
    lengths — so a test reads as a sentence and the arithmetic is nobody's job.
    """
    lemmas: list[str] = []
    words: dict[str, list[list[int]]] = {}
    for index, sentence in enumerate(sentences):
        rows: list[list[int]] = []
        at = 0
        for surface in sentence:
            if surface not in lemmas:
                lemmas.append(surface)
            rows.append([at, at + len(surface), 3, 0, lemmas.index(surface)])
            at += len(surface) + 1
        words[f"s{index}"] = rows
    return words, lemmas


def walk(
    *sentences: list[str],
    vocab: dict[str, int] | None = None,
    steps: Any = (),
    levels: Any = (),
) -> dict[str, Any]:
    words, lemmas = chapter(*sentences)
    kept = {lemma: {"status": status} for lemma, status in (vocab or {}).items()}
    return run([], chapter=words, lemmas=lemmas, vocab=kept, steps=list(steps), levels=list(levels))


def queued(*sentences: list[str], vocab: dict[str, int] | None = None) -> list[str]:
    return [item["lemma"] for item in walk(*sentences, vocab=vocab)["queue"]]


def test_the_queue_is_the_chapter_in_reading_order() -> None:
    assert queued(["a", "b"], ["c", "d"]) == ["a", "b", "c", "d"]


def test_a_word_is_asked_about_once_however_often_it_is_written() -> None:
    """A common word you leave at a level would otherwise stop you on every line of the
    chapter, and the count in the header would be counting appearances rather than
    words — a figure you could not act on."""
    assert queued(["the", "cat"], ["the", "dog", "the"]) == ["the", "cat", "dog"]


def test_a_word_is_asked_about_where_it_first_appears() -> None:
    """Still reading order, with the repeats taken out rather than the words reordered:
    walking the queue is walking the chapter."""
    queue = walk(["one", "two"], ["two", "three"])["queue"]
    (first,) = [item for item in queue if item["lemma"] == "two"]
    assert first["segment"] == "s0"
    assert first["start"] == 4


def test_what_you_have_finished_with_is_not_in_the_queue() -> None:
    assert queued(["a", "b", "c"], vocab={"a": KNOWN, "c": IGNORED}) == ["b"]


def test_what_you_are_still_learning_is() -> None:
    """The queue is everything you have not finished with, not only what is new. A word
    you met once and put at 1 is exactly the word worth being asked about again."""
    assert queued(["a", "b", "c"], vocab={"a": 1, "b": 3}) == ["a", "b", "c"]


def test_a_word_known_by_its_second_appearance_never_enters_by_its_first() -> None:
    """The first appearance is what claims the word, and it has to claim it whether or
    not the word is queued — or a word you know would go on being offered from every
    line before the one it was learnt in."""
    assert queued(["new", "old"], ["old", "new"], vocab={"old": KNOWN}) == ["new"]


def test_a_chapter_you_have_finished_has_no_queue() -> None:
    assert queued(["a", "b"], vocab={"a": KNOWN, "b": IGNORED}) == []


def test_a_chapter_with_no_words_has_no_queue() -> None:
    """A text with no annotation carries none, and the arrows go on meaning sentences
    there rather than doing nothing."""
    assert walk()["queue"] == []


def where(segment: str, start: int) -> dict[str, Any]:
    return {"segment": segment, "start": start}


def test_stepping_forward_and_back_from_a_word() -> None:
    ahead, behind = walk(
        ["one", "two", "three"],
        steps=[
            {"from": where("s0", 4), "forward": True},
            {"from": where("s0", 4), "forward": False},
        ],
    )["steps"]
    assert ahead["lemma"] == "three"
    assert behind["lemma"] == "one"


def test_going_back_reaches_a_word_you_have_already_marked() -> None:
    """The back key walks the chapter, not the queue. Marking a word takes it out of the
    queue, so a back key built on the queue stepped over everything the reader had just
    dealt with and landed somewhere earlier — walking back past their own work rather
    than retracing it. Forward still means "the next word I have not finished with"; the
    two arrows are not each other's mirror and the card says so."""
    ahead, behind = walk(
        ["one", "two", "three"],
        vocab={"two": KNOWN},
        steps=[
            {"from": where("s0", 8), "forward": True},
            {"from": where("s0", 8), "forward": False},
        ],
    )["steps"]
    # Forward skips the word that is finished with, which is the whole point of the queue.
    assert ahead is None or ahead["lemma"] != "two"
    # Back does not: "two" is exactly the word being stepped back to look at.
    assert behind["lemma"] == "two"


def test_going_back_is_the_word_before_this_one_whatever_you_said_about_it() -> None:
    """Every word on the page, in reading order, whether known, ignored or untouched."""
    behind = walk(
        ["one", "two", "three"],
        vocab={"one": KNOWN, "two": IGNORED},
        steps=[{"from": where("s0", 8), "forward": False}],
    )["steps"][0]
    assert behind["lemma"] == "two"


def test_stepping_across_a_sentence() -> None:
    (found,) = walk(
        ["one", "two"],
        ["three"],
        steps=[{"from": where("s0", 4), "forward": True}],
    )["steps"]
    assert found == {"segment": "s1", "lemma": "three", "start": 0}


def test_there_is_nothing_past_either_end() -> None:
    """Answered with nothing rather than with the other end. Wrapping round would put a
    reader back at the top of a chapter they had just finished, which reads as the page
    having lost their place."""
    last, first = walk(
        ["one", "two"],
        steps=[
            {"from": where("s0", 4), "forward": True},
            {"from": where("s0", 0), "forward": False},
        ],
    )["steps"]
    assert last is None
    assert first is None


def test_nothing_is_where_you_start_from() -> None:
    """No word open yet, so the arrows take the first or the last of the chapter."""
    first, last = walk(
        ["one", "two"],
        ["three"],
        steps=[{"from": None, "forward": True}, {"from": None, "forward": False}],
    )["steps"]
    assert first["lemma"] == "one"
    assert last["lemma"] == "three"


def test_saying_you_know_a_word_hands_you_the_next_one() -> None:
    """The whole of the loop: one key a word, and the queue is shorter for it."""
    (found,) = walk(
        ["one", "two", "three"],
        vocab={"two": KNOWN},
        steps=[{"from": where("s0", 4), "forward": True}],
    )["steps"]
    assert found["lemma"] == "three"


def test_saying_you_are_still_learning_a_word_also_hands_you_the_next_one() -> None:
    """A level leaves the word in the queue, so asking for the first word *past* where
    you were is what carries you over it. Asking for the first word still queued would
    hand you back the one you had just answered, for ever."""
    (found,) = walk(
        ["one", "two", "three"],
        vocab={"two": 2},
        steps=[{"from": where("s0", 4), "forward": True}],
    )["steps"]
    assert found["lemma"] == "three"


# --- the way back from the wrong key ------------------------------------------


def test_taking_back_a_level_puts_the_word_back_in_the_queue() -> None:
    """`k` is one key away from `1`, `2` and `3`, and it is the one that takes the word
    out of the queue the arrows walk — so a mis-keyed `k` had no way back to it from the
    keyboard at all. `u` puts the word back where it was, not at the end."""
    said = walk(
        ["one", "two", "three"],
        levels=[{"word": "two", "status": KNOWN}, {"undo": True}],
    )["said"]
    marked, taken_back = (state["queue"] for state in said)
    assert [item["lemma"] for item in marked] == ["one", "three"]
    assert [item["lemma"] for item in taken_back] == ["one", "two", "three"]


def test_taking_back_a_level_restores_the_one_it_replaced() -> None:
    """Undo is not "unmarked". A word you had at 2 and then said you knew goes back to
    2, because that is what the key replaced."""
    said = walk(
        ["one", "two"],
        vocab={"two": 2},
        levels=[{"word": "two", "status": KNOWN}, {"undo": True}],
    )["said"]
    assert [item["lemma"] for item in said[0]["queue"]] == ["one"]
    # Back in the queue at a level, rather than out of the vocabulary altogether.
    assert [item["lemma"] for item in said[1]["queue"]] == ["one", "two"]
    assert said[1]["spoken"] == "two, getting there. 2 left."


def test_undo_goes_back_as_many_words_as_you_answered() -> None:
    """A reader sweeping a chapter notices the wrong key a word or two later, not at
    once. One step of undo would be a fix that only works when you are already looking."""
    said = walk(
        ["one", "two", "three"],
        levels=[
            {"word": "one", "status": KNOWN},
            {"word": "two", "status": KNOWN},
            {"word": "three", "status": KNOWN},
            {"undo": True},
            {"undo": True},
            {"undo": True},
        ],
    )["said"]
    assert [item["lemma"] for item in said[2]["queue"]] == []
    assert [item["lemma"] for item in said[-1]["queue"]] == ["one", "two", "three"]


def test_a_level_says_what_it_did_and_how_much_is_left() -> None:
    """Marking a word from the keyboard moved a ring and a number in the opposite corner
    of the bar, and announced neither. Working the queue by keyboard alone is exactly the
    case where nothing else confirms the key landed."""
    said = walk(
        ["one", "two", "three"],
        levels=[{"word": "one", "status": KNOWN}, {"word": "two", "status": 1}],
    )["said"]
    assert said[0]["spoken"] == "one, known. 2 left."
    assert said[1]["spoken"] == "two, just met it. 2 left."


def test_saying_a_level_a_word_already_has_takes_it_off() -> None:
    """The same key both grades a word and undoes itself, and "not marked" is a real
    answer rather than silence."""
    said = walk(
        ["one", "two"],
        vocab={"one": KNOWN},
        levels=[{"word": "one", "status": KNOWN}],
    )["said"]
    assert said[0]["spoken"] == "one, not marked. 2 left."
    assert [item["lemma"] for item in said[0]["queue"]] == ["one", "two"]


# -- the list beside the text ---------------------------------------------------


def listed(
    *sentences: list[str], vocab: dict[str, int] | None = None, **rest: Any
) -> list[dict[str, Any]]:
    words, lemmas = chapter(*sentences)
    kept = {lemma: {"status": status} for lemma, status in (vocab or {}).items()}
    return run([], chapter=words, lemmas=lemmas, vocab=kept, **rest)["list"]


def test_the_last_word_you_saved_is_at_the_top() -> None:
    """ "The last word you saved should go to the top of the list on the left." It went to
    the bottom, which in a list longer than the panel was off the screen."""
    rows = listed(
        ["a", "b", "c"],
        levels=[{"word": "a", "status": 1}, {"word": "b", "status": 2}, {"word": "c", "status": 1}],
    )
    assert [row["lemma"] for row in rows] == ["c", "b", "a"]


def test_a_word_saved_as_known_stays_in_sight() -> None:
    """The list is what you are still working on, so a known word is not on it — except
    the one you finished with just now. A word that vanished the moment you said you knew
    it read as a save that had failed."""
    rows = listed(
        ["a", "b", "c"],
        vocab={"c": 9},
        levels=[{"word": "a", "status": 1}, {"word": "b", "status": 1}, {"word": "a", "status": 9}],
    )
    assert [(row["lemma"], row["status"], row["done"]) for row in rows] == [
        ("b", 1, False),
        ("a", 9, True),
    ], "the finished word keeps its place; the one known before you came is not listed"


def test_a_word_you_ignore_stays_in_sight_too() -> None:
    rows = listed(["a", "b"], levels=[{"word": "a", "status": 0}])
    assert [(row["lemma"], row["status"], row["done"]) for row in rows] == [("a", 0, True)]


# -- the first time ---------------------------------------------------------------


def test_the_first_time_says_what_to_do() -> None:
    """A reader who has never marked a word is told the one thing the page is for, and
    the first word they mark turns that into the keys. Then it is gone for good."""
    words, lemmas = chapter(["a", "b"])
    before = run([], chapter=words, lemmas=lemmas, vocab={})["first"]
    assert before == {"hidden": False, "text": "Tap a word to say how well you know it."}

    after = run([], chapter=words, lemmas=lemmas, vocab={}, levels=[{"word": "a", "status": 1}])
    assert after["first"]["hidden"] is False
    assert after["first"]["text"].startswith("k known · 1 2 3")


def test_a_reader_with_words_already_is_not_told_how_to_mark_one() -> None:
    words, lemmas = chapter(["a", "b"])
    drawn = run([], chapter=words, lemmas=lemmas, vocab={"c": {"status": 2}})["first"]
    assert drawn["hidden"] is True


# -- the offer at the foot of a part ---------------------------------------------


def test_the_rest_is_offered_and_one_press_marks_it_known() -> None:
    """ "Words should be marked as known automatically when I'm done with the article."
    Offered, never done for you: the words you never marked, in one press, with the
    number said. The ones you are working on are left alone."""
    words, lemmas = chapter(["a", "b", "c"])
    before = run([], chapter=words, lemmas=lemmas, vocab={}, levels=[{"word": "a", "status": 2}])
    assert before["rest"] == {
        "hidden": False,
        "text": "",
        "button": "Mark 2 words as known",
        "undo": False,
    }
    after = run(
        [],
        chapter=words,
        lemmas=lemmas,
        vocab={},
        levels=[{"word": "a", "status": 2}],
        markRest=True,
    )
    assert [item["lemma"] for item in after["queue"]] == ["a"], "still learning a; b and c known"
    assert after["rest"]["text"] == "2 words marked known"
    assert after["rest"]["undo"] is True


def test_one_undo_takes_the_whole_batch_back() -> None:
    words, lemmas = chapter(["a", "b", "c", "d"])
    done = run([], chapter=words, lemmas=lemmas, vocab={}, markRest=True, undoAfter=True)
    assert [item["lemma"] for item in done["queue"]] == ["a", "b", "c", "d"]
    assert done["rest"]["button"] == "Mark 4 words as known"


def test_marking_the_rest_takes_the_names_with_it_but_never_counts_them() -> None:
    """The whole point is a clean page, so a name is marked with the rest — and it still
    counts for nothing, because its record keeps "name" as its band, which is what every
    count reads."""
    rows = {"s0": [[0, 1, 3, 0, 0, 0, 0], [2, 3, 0, 0, 1, 0, 1], [4, 5, 3, 0, 2, 0, 0]]}
    done = run([], chapter=rows, lemmas=["a", "Name", "c"], vocab={}, markRest=True)
    assert done["rest"]["text"] == "3 words marked known"
    assert done["queue"] == [], "nothing left lit"
    assert done["list"] == [], "and nothing on the list"


def test_nothing_is_offered_on_a_part_with_nothing_left() -> None:
    words, lemmas = chapter(["a"])
    done = run([], chapter=words, lemmas=lemmas, vocab={"a": {"status": 9}})
    assert done["rest"]["hidden"] is True


# -- pages, not a scroll ----------------------------------------------------------


def pages(tops: list[int], heights: list[int], room: int) -> list[list[int]]:
    words, lemmas = chapter(["a"])
    return run(
        [], chapter=words, lemmas=lemmas, pages={"tops": tops, "heights": heights, "room": room}
    )["pages"]


def test_a_page_is_the_pairs_that_fit_the_room() -> None:
    """A page is a contiguous run of pairs, decided from where each starts and how tall
    it is — margins included, since the next pair's top carries them. Nothing is fixed
    at build time: how many fit depends on the window, the type and the vowels."""
    assert pages([0, 100, 200, 300, 400], [90, 90, 90, 90, 90], 250) == [[0, 1], [2, 3], [4, 4]]


def test_a_pair_too_tall_for_the_room_is_a_page_of_its_own() -> None:
    """Rather than a page nobody can turn to. That page scrolls, which is honest."""
    assert pages([0, 500, 560], [480, 50, 50], 250) == [[0, 0], [1, 2]]


def test_no_pairs_is_no_pages() -> None:
    assert pages([], [], 250) == []


def test_which_page_a_pair_is_on() -> None:
    words, lemmas = chapter(["a"])
    laid = [[0, 1], [2, 3], [4, 4]]
    for index, page in ((0, 0), (1, 0), (2, 1), (4, 2)):
        found = run([], chapter=words, lemmas=lemmas, pageFor={"index": index, "pages": laid})
        assert found["pageFor"] == page, index


# -- finished with the text --------------------------------------------------------


def test_done_is_said_once_however_often_it_is_pressed() -> None:
    """targum-internal#112. One press at the foot of the last part finishes the text and
    says when; pressing again takes it back. Finished twice is finished once, so the
    count on the progress page can only ever move by one."""
    words, lemmas = chapter(["a"])
    fresh = run([], chapter=words, lemmas=lemmas)["finished"]
    assert fresh["at"] == 0 and fresh["button"] == "Done" and fresh["said"] == ""

    done = run([], chapter=words, lemmas=lemmas, finish=[True])["finished"]
    assert done["at"] > 0 and done["record"] == done["at"], "written where the sync reads it"
    assert done["button"] == "Undo"
    assert done["said"].startswith("You finished a targum.")
    assert "1st" in done["said"], "and how many so far"

    back = run([], chapter=words, lemmas=lemmas, finish=[True, False])["finished"]
    assert back["at"] == 0 and back["button"] == "Done"


def test_finishing_survives_everything_else_the_reader_writes() -> None:
    """`updateDocs` rewrites the text's record on every change to a word."""
    words, lemmas = chapter(["a", "b"])
    kept = run(
        [], chapter=words, lemmas=lemmas, finish=[True], levels=[{"word": "a", "status": 9}]
    )["finished"]
    assert kept["record"] > 0
