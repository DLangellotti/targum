"""The Learn page's script, run rather than read.

Learn is where a reader lands, and it says the same thing twice at two sizes: the text
they were in the middle of, and the shelf under it. Both now carry a cover, and both are
worth pinning, because the cover is drawn from the catalogue and most of a reader's own
shelf is not in the catalogue — a news article pasted in this morning will never have one
and must not look broken for it.

Same harness as `test_library_js.py`: a stub document in `tests/js/`, not a browser.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import pytest

HARNESS = Path(__file__).resolve().parent / "js" / "learn.js"

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")


def reader(name: str, title: str, entry: str = "", **extra: Any) -> dict[str, Any]:
    row = {
        "name": name,
        "title": title,
        "language": "he",
        "document": name,
        "entry": entry,
        "drawn": bool(entry),
        "sections": 1,
        "chapters": [],
        "readyChapters": 0,
        "built": 0,
        "opened": 0,
        "words": 500,
        "minutes": 4,
        "kind": "prose",
        "register": "modern",
        "difficulty": 20,
        # What the text is about, so the arrival's subject doors can be answered from
        # the shelf (2026-09-17). A reader's own text carries none.
        "tags": [],
    }
    row.update(extra)
    return row


def word(lemma: str, meaning: str, status: int = 1, **extra: Any) -> dict[str, Any]:
    """One kept word, and what it means in English.

    Two records, because they are two different facts: the word belongs to Hebrew and is
    the same word whatever you read it in, while the meaning belongs to Hebrew-into-
    English and has a different answer in Hebrew-into-Russian. `note` follows the meaning
    for the same reason — a note is a meaning you wrote yourself.
    """
    note = extra.pop("note", "")
    row = {"surface": lemma, "status": status, "band": "moderate", "at": 0}
    row.update(extra)
    return {lemma: (row, {"meaning": meaning, "note": note, "at": 0, "seen": 1})}


def vocabulary(*words: dict[str, Any], into: str = "en") -> dict[str, str]:
    """A `stored` payload holding those words, for the harness's localStorage."""
    kept: dict[str, Any] = {}
    means: dict[str, Any] = {}
    for one in words:
        for lemma, (row, meaning) in one.items():
            kept[lemma] = row
            means[lemma] = meaning
    return {
        "targum:vocab:he": json.dumps(kept, ensure_ascii=False),
        f"targum:meanings:he:{into}": json.dumps(means, ensure_ascii=False),
    }


def draw(
    readers: list[dict[str, Any]],
    stored: dict[str, str] | None = None,
    **options: Any,
) -> dict[str, Any]:
    """Run the page. `do` is a list of things to press; everything else is fixture."""
    with tempfile.TemporaryDirectory() as where:
        payload = Path(where) / "payload.json"
        payload.write_text(
            json.dumps({"readers": readers, "stored": stored or {}, **options}, ensure_ascii=False),
            encoding="utf-8",
        )
        done = subprocess.run(
            ["node", str(HARNESS), str(payload)], capture_output=True, text=True, timeout=60
        )
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def test_the_text_you_are_carrying_on_with_shows_its_cover() -> None:
    """The most prominent thing on the page a reader lands on. It used to be the one
    place a book's picture was not."""
    drawn = draw([reader("psalms-he", "תהילים", entry="psalms")])

    assert drawn["carry"]["hidden"] is False
    assert drawn["carry"]["title"] == "תהילים"
    assert drawn["carry"]["cover"] is not None, "the panel carries one"
    assert drawn["carry"]["frame"].endswith("reader/index.html?k=k&preview=1"), (
        "the sheet's window is the reader, told it is on the front page"
    )
    assert drawn["carry"]["href"].endswith("reader/index.html?k=k"), (
        "and Open goes to the reader's own page"
    )


def test_a_text_offered_in_the_conversation_opens_in_the_sheet() -> None:
    """2026-09-11: "if the user is offered a text in the chat, it should be opened first
    in the reader on this page, then they can ... go to the dedicated page". The drawer
    hands the reader's path to the page; the page draws it in the sheet with what the
    shelf knows of it, and Open goes to its own page. A page of words marked known in the
    drawer has the page drawn again."""
    shelf = [
        reader("psalms-he", "תהילים", entry="psalms", opened=2),
        reader("genesis-he", "בראשית", entry="genesis", opened=1),
    ]
    drawn = draw(shelf, do=[{"offer": "genesis-he/reader/sec-0003.html"}])
    assert (
        drawn["carry"]["title"] == "בראשית" and drawn["carry"]["heading"] == "From the conversation"
    )
    assert drawn["carry"]["frame"].endswith("genesis-he/reader/sec-0003.html?k=k&preview=1")
    assert drawn["carry"]["href"].endswith("genesis-he/reader/sec-0003.html?k=k")
    unknown = draw(shelf, do=[{"offer": "negev-he/reader/index.html"}])
    assert unknown["carry"]["title"] == "negev-he", "a text the shelf has not heard of yet"
    assert unknown["carry"]["frame"].endswith("negev-he/reader/index.html?k=k&preview=1")
    assert drawn["hands"] == ["open", "changed"], "what the drawer may ask of the page"


def test_recently_read_is_a_menu_in_the_row_with_the_way_to_the_whole_list() -> None:
    """David, 2026-09-11: "'my targums' removed from underneath, and added to a menu next
    to the subscriptions ... titled something like 'Recently read', and it only shows the
    last few and a link to full history". The reader's own texts opened lately, newest
    first, five at most, each a row that puts the text in the sheet; All your targums at
    the foot goes to the whole list. A text never opened is on that list and not here."""
    shelf = [reader(f"r{n}", f"ספר {n}", built=100 - n, opened=50 - n) for n in range(8)]
    shelf.append(reader("fresh", "חדש", built=200, opened=0))
    stamps = {"targum:opened": json.dumps({f"r{n}": 50 - n for n in range(8)})}
    drawn = draw(shelf, stamps)
    assert [(d["label"], d["on"]) for d in drawn["doors"]] == [
        ("Continue reading", True),
        ("Recently read", False),
    ]
    recent = drawn["recent"]
    assert [i["label"] for i in recent["items"]] == [f"ספר {n}" for n in range(5)], (
        "the last few, newest first"
    )
    assert all("ago" in i["when"] or i["when"] == "just now" for i in recent["items"])
    assert recent["link"] == {"label": "All your targums", "href": "/texts?k=k"}
    assert not recent["open"] and not any(i["done"] for i in recent["items"])

    pressed = draw(shelf, stamps, do=[{"door": "recent"}, {"door": "recent:r2"}])
    assert pressed["carry"]["title"] == "ספר 2"
    assert pressed["carry"]["heading"] == "Continue reading"
    assert pressed["carry"]["frame"].endswith("r2/reader/index.html?k=k&preview=1")
    assert [(d["label"], d["on"]) for d in pressed["doors"]] == [
        ("Continue reading", False),
        ("Recently read", True),
    ], "the door says which way the sheet was reached"
    assert [i["on"] for i in pressed["recent"]["items"]] == [False, False, True, False, False]
    assert not pressed["recent"]["open"], "a press closes the menu"

    none = draw([reader("fresh", "חדש", built=200)])
    assert none["doors"] == [] and none["recent"]["items"] == [], (
        "nothing opened yet: nothing recently read, and one door is no row"
    )


def test_a_text_read_through_carries_a_check_in_the_menu() -> None:
    """2026-09-11: "once user has finished reading it, there should be some kind of mark
    for that in the drop down menu, maybe a green checkmark". Every section finished, as
    this browser records it, and the row says Finished; a half-read book says nothing."""
    whole = reader("whole", "שלם", document="whole", sections=3, opened=3)
    half = reader("half", "חצי", document="half", sections=2, opened=2)
    one = reader("one", "אחד", document="one", opened=1)
    docs = {
        "whole": {"sections": {"1": 1, "2": 1, "3": 1}},
        "half": {"sections": {"1": 1}},
        "one": {"done": 1},
    }
    drawn = draw(
        [whole, half, one],
        {
            "targum:opened": json.dumps({"whole": 3, "half": 2, "one": 1}),
            "targum:docs": json.dumps(docs),
        },
    )
    assert [(i["label"], i["done"]) for i in drawn["recent"]["items"]] == [
        ("שלם", True),
        ("חצי", False),
        ("אחד", True),
    ]


def test_nothing_under_the_sheet() -> None:
    """The shelf and the trash left Learn on 2026-09-11 for the Recently read menu and
    Your targums."""
    page = (
        Path(__file__).resolve().parents[1] / "src/targum/render/templates/learn.html.j2"
    ).read_text(encoding="utf-8")
    assert 'id="library-list"' not in page and 'id="trash-panel"' not in page
    assert 'id="shelf-more"' not in page and "<h2><span>Your targums</span></h2>" not in page


# -- what you are learning -------------------------------------------------------


def test_the_page_opens_by_saying_how_many_words_you_know() -> None:
    """The first line on the page, and a count of a real thing. Known only: a word
    somebody is halfway through is not one they know."""
    known = [word(f"מילה{n}", "w", status=9) for n in range(12)]
    drawn = draw([reader("a", "אהבת ציון")], vocabulary(*known, word("דרך", "road", status=2)))
    assert drawn["known"] == "You know 12 Hebrew words."


def test_a_count_under_ten_says_what_to_do_rather_than_how_little() -> None:
    """2026-09-11: "You know 1 Hebrew word" is true and deflating on the first line a new
    reader sees. Until ten, the line says what to do here — decided with David on
    2026-09-11: one quiet sentence for a new reader — which is what makes the count."""
    drawn = draw([reader("a", "א")], vocabulary(word("ספר", "book", status=9)))
    assert drawn["known"] == "Read, tap the words you don't know and talk to targum about any line."
    nine = draw([reader("a", "א")], vocabulary(*(word(f"מ{n}", "w", status=9) for n in range(9))))
    assert nine["known"] == "Read, tap the words you don't know and talk to targum about any line."
    ten = draw([reader("a", "א")], vocabulary(*(word(f"מ{n}", "w", status=9) for n in range(10))))
    assert ten["known"] == "You know 10 Hebrew words."


def test_knowing_nothing_yet_asks_rather_than_scoring_zero() -> None:
    """ "You know 0 words" is a score of zero, which is the arcade the brand keeps out."""
    drawn = draw([reader("a", "א")], vocabulary(word("ספר", "book", status=1)))
    assert drawn["known"] == "Read, tap the words you don't know and talk to targum about any line."


def test_the_card_and_every_step_beside_it_is_one_whole_target() -> None:
    """A card with a link in the corner asks a reader to aim at it. The whole card takes
    the click, which also means nothing focusable inside anything focusable — and every
    row of the list beside it is a link too, rather than a line of text with one in it.

    The suggestion is a button rather than a link because it acts rather than goes: one
    press builds the text and lands you in it. Same card, same whole-box target."""
    from pathlib import Path

    page = (
        Path(__file__).resolve().parents[1] / "src/targum/render/templates/learn.html.j2"
    ).read_text(encoding="utf-8")
    foot = "{% include '_foot.html.j2' %}"
    top = page[page.index('<div class="front" id="front">') : page.index(foot)]
    assert top.count('<a class="open" id="carry"') == 1, (
        "the sheet's Open goes to the reader's own page (§13)"
    )
    assert 'id="carry-frame"' in top and 'id="carry-expand"' not in top, (
        "the reader itself, framed and working; Expand went with the card it expanded over"
    )
    assert 'id="talk-frame"' not in top and "Talk to targum" not in top, (
        "the conversation is the pill at the foot of every page, not a card here"
    )
    assert 'id="suggest"' not in page and 'class="door' not in page, (
        "the suggestion card and the steps left Learn on 2026-09-11: the Library has them"
    )
    assert "<h2><a " not in top, "no heading is a link; the box around it is"
    assert "<h2><button" not in top
    assert 'id="carry-cover"' in top and '<a class="carry-cover' not in top


# -- how much of a list this page holds ------------------------------------------


# -- folding a list away ---------------------------------------------------------


# -- what to read next -----------------------------------------------------------


def entry(id: str, title: str, difficulty: int, minutes: int = 30, **extra: Any) -> dict[str, Any]:
    """One catalogue row, trimmed the way the page carries it."""
    row = {
        "id": id,
        "title": title,
        "language": "he",
        "blurb": "A line about " + title + ".",
        "difficulty": difficulty,
        "minutes": minutes,
        # A track: every catalogue row is one Hebrew or the other.
        "register": "modern",
    }
    row.update(extra)
    return row


#: `source` and `translations` because the suggestion is taken up on this page rather
#: than somewhere else: pressing the card starts a build, and a build is started from
#: those two. The page carries the translations already reduced to their sources, which
#: is the shape `/prepare` wants.
CATALOGUE = [
    entry("easy", "קל", 16, minutes=10, source="s:easy", translations=["t:easy"]),
    entry("middling", "בינוני", 24, source="s:middling", translations=["t:mid"]),
    entry("harder", "קשה", 32, source="s:harder", translations=["t:hard", "t:hard2"]),
    entry("hardest", "הקשה", 40, source="s:hardest", translations=[]),
]

#: The same four, as scripture. The Biblical door is the one that builds a step up —
#: the modern track's next step past the scenes is a link to the library row — so the
#: tests of pressing a card to build run on this Hebrew.
SCRIPTURE = [dict(row, register="biblical") for row in CATALOGUE]

#: A store in which the reader's text "a" is finished: a door offers the step up only
#: once the text last opened on that track is done.
FINISHED_A = {"targum:docs": json.dumps({"a": {"done": 1, "language": "he", "title": "א"}})}


def test_a_reader_with_no_texts_is_pointed_at_the_easiest_thing() -> None:
    """Words kept but nothing on the shelf — someone who has read in the reader and
    deleted it, or is starting again. There is no level to step up from, so the answer is
    where everybody starts. (A browser with nothing at all gets the empty state instead,
    which is a different page.)"""
    drawn = draw([], vocabulary(word("ספר", "book", status=2)), catalogue=CATALOGUE)
    # Nothing seeded either, so the modern door offers the catalogue's easiest itself —
    # as a link to its library row, where building is pressed for.
    assert drawn["carry"]["heading"] == "Start here"
    assert drawn["carry"]["title"] == "קל"
    assert drawn["carry"]["meta"] == "Where most people start · 10 min"
    assert drawn["carry"]["entry"] == "easy"
    # `/open/<id>` since targum-internal#313: the door, which sends them to their copy
    # where they have one and to its row with the offer up where they have not.
    assert drawn["carry"]["href"].startswith("/open/easy")


def test_the_suggestion_is_a_step_up_from_the_hardest_thing_read() -> None:
    """Level is the difficulty of what they have actually built — the share of running
    words needing a lookup — rather than a guess about the person."""
    shelf = [reader("a", "א", difficulty=24, opened=2), reader("b", "ב", difficulty=16, opened=1)]
    done = {"targum:docs": json.dumps({"a": {"done": 1}, "b": {"done": 1}})}
    drawn = draw(shelf, done, catalogue=CATALOGUE)
    assert drawn["carry"]["heading"] == "A step up"
    assert drawn["carry"]["title"] == "קשה", "the easiest one harder than 24"
    assert drawn["carry"]["meta"].startswith("A step up")


def test_something_already_built_is_not_suggested_again() -> None:
    shelf = [reader("a", "א", entry="harder", difficulty=32, opened=1)]
    done = {"targum:docs": json.dumps({"a": {"done": 1}})}
    drawn = draw(shelf, done, catalogue=CATALOGUE)
    assert drawn["carry"]["heading"] == "A step up"
    assert drawn["carry"]["title"] == "הקשה", "the next one up, not the one they have"


def test_a_reader_past_the_whole_catalogue_is_told_the_truth() -> None:
    shelf = [reader("a", "א", difficulty=99, opened=1)]
    done = {"targum:docs": json.dumps({"a": {"done": 1}})}
    drawn = draw(shelf, done, catalogue=CATALOGUE)
    assert drawn["carry"]["meta"].startswith("About where you're reading")


def test_an_unfinished_text_of_your_own_is_the_door_whatever_the_catalogue_offers() -> None:
    """The step up waits until the text last opened is finished: a door that swapped a
    half-read text for a harder one would be taking the reader's place away."""
    drawn = draw([reader("a", "א", difficulty=24, opened=1)], catalogue=CATALOGUE)
    assert drawn["carry"]["heading"] == "Continue reading" and drawn["carry"]["title"] == "א"


def test_a_reader_with_nothing_is_handed_the_shared_text() -> None:
    """ "When alpha user logs in, no idea where to start." The first card on the page is
    where to start: a text already built, so there is nothing to choose and nothing to
    wait for."""
    drawn = draw([], shared=[reader("ruth", "רות")])
    assert drawn["carry"]["hidden"] is False
    assert drawn["carry"]["heading"] == "Start here"
    assert drawn["carry"]["title"] == "רות"


def test_the_shared_text_stays_out_of_the_way_of_your_own() -> None:
    drawn = draw([reader("a", "א")], shared=[reader("ruth", "רות")])
    assert drawn["carry"]["heading"] == "Continue reading"
    assert drawn["carry"]["title"] == "א"


def test_nothing_known_is_not_said_on_the_first_card() -> None:
    """ "You know 0% of its words" is true and unkind on the first card a new reader
    sees. The line starts once there is something to say."""
    drawn = draw([], shared=[reader("ruth", "רות", "ruth", known=0.0)])
    assert drawn["carry"]["known"] == ""
    later = draw([reader("a", "א", known=0.4)])
    assert later["carry"]["known"] == "You know 40%"


def test_the_sheet_takes_the_hebrew_opened_most_recently() -> None:
    """One sheet, two tracks (2026-09-11: Learn is the room you learn in, and the
    Biblical door that stood beside the sheet is on the Library). A first visit opens
    on modern Hebrew; once either track has been opened, the sheet is that one."""
    holon = reader("holon", "הפועל חולון", "sport-holon-basketball", kind="article")
    ruth = reader("ruth", "רות", "ruth", register="biblical")
    fresh = draw([], shared=[ruth, holon])
    assert fresh["carry"]["track"] == "Modern Hebrew" and fresh["carry"]["title"] == "הפועל חולון"
    assert fresh["carry"]["heading"] == "Start here"
    assert fresh["known"] == "Read, tap the words you don't know and talk to targum about any line."
    biblical = draw([], {"targum:opened": json.dumps({"ruth": 7})}, shared=[holon, ruth])
    assert biblical["carry"]["track"] == "Biblical Hebrew" and biblical["carry"]["title"] == "רות"
    assert biblical["carry"]["heading"] == "Continue reading"
    both = draw(
        [],
        {"targum:opened": json.dumps({"ruth": 7, "holon": 9})},
        shared=[ruth, holon],
    )
    assert both["carry"]["title"] == "הפועל חולון", "the one opened last"


def test_a_text_with_no_uncommon_word_in_it_is_still_offered() -> None:
    """Zero is a measurement, not a missing one.

    A twenty-word beginner scene has no word in it that a learner would look up, and
    the share of running words needing one is honestly nought. Read as "nobody has
    measured this" it took the seven easiest texts in the library out of the one list a
    beginner is shown — which is the list they are shown *because* they are beginners.
    """
    shelf = [
        entry("scene", "סצנה", 0, minutes=1, source="dialogue:scene", translations=[]),
        *CATALOGUE,
    ]
    drawn = draw([], vocabulary(word("ספר", "book", status=2)), catalogue=shelf)
    # Nothing seeded, so the modern door offers the catalogue's easiest text itself.
    assert drawn["carry"]["entry"] == "scene"
    assert drawn["carry"]["title"] == "סצנה"


def test_a_card_carries_the_title_in_english_under_the_hebrew() -> None:
    """Both doors, from the same field the library shows; an upload has none and the
    line stays away."""
    drawn = draw([reader("ruth-he", "רות", entry="ruth", english="Ruth", opened=2)])
    assert drawn["carry"]["english"] == "Ruth"

    plain = draw([reader("mine-he", "שלי", opened=2)])
    assert plain["carry"]["english"] == ""

    offered = draw(
        [],
        catalogue=[
            entry(
                "altneuland",
                "תל־אביב",
                19,
                english="Old New Land",
                source="test:a",
                translations=[],
            )
        ],
    )
    assert offered["carry"]["english"] == "Old New Land", "a catalogue pick carries it too"


# --- the scenes as the modern path ------------------------------------------------


def scene(number: int, slug: str, title: str, **extra: Any) -> dict[str, Any]:
    """A seeded scene, as `/readers` lists a shared one."""
    row = reader(
        f"scene-{number:02d}-{slug}-he",
        title,
        f"scene-{number:02d}-{slug}",
        kind="dialogue",
        words=22,
        minutes=1,
        spoken=True,
        shared=True,
        difficulty=0,
    )
    row.update(extra)
    return row


SCENES = [
    scene(1, "nice-to-meet-you", "נעים מאוד", english="Nice to meet you"),
    scene(2, "in-a-cafe", "בבית קפה", english="In a café", words=19),
    scene(3, "which-way", "איפה הרחוב", english="Which way", words=18),
]
RUTH = reader(
    "ruth-he",
    "רות",
    "ruth",
    register="biblical",
    chapters=[{}] * 4,
    readyChapters=4,
    spoken=True,
    shared=True,
    english="Ruth",
)


def test_a_text_of_another_register_opened_last_takes_the_sheet() -> None:
    """Mendele is revival Hebrew, neither modern nor Biblical, and the sheet used to skip
    it for a track's door. Opened more recently than either track, it is what the reader
    came back for (2026-09-11)."""
    mendele = reader("mendele-he", "מסעות בנימין", register="revival", opened=9)
    drawn = draw(
        [mendele], {"targum:opened": json.dumps({"mendele-he": 9})}, shared=SCENES + [RUTH]
    )
    assert (
        drawn["carry"]["title"] == "מסעות בנימין"
        and drawn["carry"]["heading"] == "Continue reading"
    )
    assert drawn["carry"]["frame"].endswith("mendele-he/reader/index.html?k=k&preview=1")
    assert [i["label"] for i in drawn["recent"]["items"]] == ["מסעות בנימין"], (
        "and it is what was read lately"
    )


def test_an_account_that_knows_nothing_starts_on_scene_one() -> None:
    """The sheet at Start here on Scene 1, which says which scene of how many, how long,
    and that it can be heard. Nothing says "ready", and Open opens a built text."""
    drawn = draw([], shared=SCENES + [RUTH])
    assert drawn["known"] == "Read, tap the words you don't know and talk to targum about any line."
    assert drawn["carry"]["track"] == "Modern Hebrew" and drawn["carry"]["heading"] == "Start here"
    assert (
        drawn["carry"]["title"] == "נעים מאוד" and drawn["carry"]["english"] == "Nice to meet you"
    )
    assert drawn["carry"]["meta"] == "Scene 1 of 3 · 22 words · audio"
    assert drawn["carry"]["href"].endswith(
        "/reader/scene-01-nice-to-meet-you-he/reader/index.html?k=k"
    )
    assert not [call for call in drawn["asked"] if "/prepare" in call["path"]]
    assert drawn["carry"]["frame"].endswith(
        "scene-01-nice-to-meet-you-he/reader/index.html?k=k&preview=1"
    )


def test_a_scene_half_read_is_continued_with_the_words_left() -> None:
    opened = {"targum:opened": json.dumps({"scene-01-nice-to-meet-you-he": 5})}
    first = dict(SCENES[0], fresh=12)
    drawn = draw([], opened, shared=[first, *SCENES[1:], RUTH])
    assert drawn["carry"]["heading"] == "Continue reading"
    assert drawn["carry"]["meta"] == "Scene 1 of 3 · 12 words left · audio"
    assert drawn["known"] == "Read, tap the words you don't know and talk to targum about any line."


def test_a_finished_scene_hands_over_to_the_next() -> None:
    done = {
        "targum:opened": json.dumps({"scene-01-nice-to-meet-you-he": 5}),
        "targum:docs": json.dumps({"scene-01-nice-to-meet-you-he": {"done": 9, "language": "he"}}),
        **vocabulary(*(word(w, w, status=9) for w in ("א", "ב", "ג"))),
    }
    drawn = draw([], done, shared=SCENES + [RUTH])
    assert drawn["carry"]["heading"] == "Up next"
    assert drawn["carry"]["title"] == "בבית קפה"
    assert drawn["carry"]["meta"] == "Scene 2 of 3 · 19 words · audio"
    assert drawn["known"] == "Read, tap the words you don't know and talk to targum about any line."


def test_a_scene_finished_on_another_device_is_not_a_start() -> None:
    """`done` syncs; `opened` does not. A new browser has the finish and no last-opened
    text, and the door reads Up next rather than sending the reader back to Scene 1."""
    done = {"targum:docs": json.dumps({"scene-01-nice-to-meet-you-he": {"done": 9}})}
    drawn = draw([], done, shared=SCENES + [RUTH])
    assert drawn["carry"]["heading"] == "Up next" and drawn["carry"]["title"] == "בבית קפה"
    assert (
        drawn["known"] == "Read, tap the words you don't know and talk to targum about any line."
    ), "every word ignored and Done pressed is not a score of zero"


def test_past_the_last_scene_the_modern_door_steps_up() -> None:
    done = {"targum:docs": json.dumps({s["document"]: {"done": 9} for s in SCENES})}
    drawn = draw([], done, shared=SCENES + [RUTH], catalogue=CATALOGUE)
    assert drawn["carry"]["heading"] == "Start here", "nothing built yet on this track"
    assert drawn["carry"]["title"] == "קל"
    # `/open/<id>` since targum-internal#313: the door, which sends them to their copy
    # where they have one and to its row with the offer up where they have not.
    assert drawn["carry"]["href"].startswith("/open/easy")


def test_an_upload_takes_the_door_of_its_own_hebrew() -> None:
    mine = reader("mine-he", "שלי")
    drawn = draw([mine], {"targum:opened": json.dumps({"mine-he": 3})}, shared=SCENES + [RUTH])
    assert drawn["carry"]["heading"] == "Continue reading" and drawn["carry"]["title"] == "שלי"


def test_nothing_on_learn_says_ready() -> None:
    assets = Path(__file__).resolve().parent.parent / "src/targum/render/assets"
    source = (assets / "learn.js").read_text(encoding="utf-8")
    assert "ready to read" not in source and "both ready" not in source


def test_a_door_onto_a_video_says_video_and_not_audio() -> None:
    """The same one word the library's rows use: a lecture that kept its slides is
    told apart from a podcast, and never says both."""
    lecture = scene(1, "a-lecture", "הרצאה", english="A lecture", video=True)
    drawn = draw([], shared=[lecture, scene(2, "in-a-cafe", "בבית קפה", english="In a café")])
    assert drawn["carry"]["meta"] == "Scene 1 of 2 · 22 words · video"


# -- a subscription that landed (2026-09-11) ---------------------------------------------

PORTION = {
    "id": "parasha",
    "name": "The weekly portion",
    "hebrew": "פרשת השבוע",
    "what": "This Shabbat's reading.",
    "page": "/parasha",
    "instalment": {
        "id": "ki-tavo",
        "title": "Ki Tavo",
        "hebrew": "כי תבוא",
        "when": "2026-09-12",
        "reader": "/parasha/read/ki-tavo/reader/sec-0001.html",
    },
}


def test_a_followed_series_newest_instalment_takes_the_sheet_once_and_rings_the_bell() -> None:
    """Following one on the Library "puts its newest instalment into the sheet on Learn as
    Continue when it lands, and into the bell". The first visit after it lands: the sheet
    is the instalment, framed from its own page, Open goes to the series' page, and the
    bell is told. Seen once, the next visit is the reader's own text again."""
    mine = reader("mine-he", "שלי")
    drawn = draw([mine], {"targum:follows": json.dumps({"parasha": 1})}, series=[PORTION])
    assert drawn["carry"]["heading"] == "New: The weekly portion"
    assert drawn["carry"]["title"] == "כי תבוא" and drawn["carry"]["english"] == "Ki Tavo"
    assert drawn["carry"]["frame"] == "/parasha/read/ki-tavo/reader/sec-0001.html?k=k&preview=1"
    assert drawn["carry"]["href"] == "/parasha/read/ki-tavo/reader/sec-0001.html?k=k", (
        "Open opens the reader"
    )
    assert drawn["seen"] == {"parasha": "ki-tavo"}
    assert drawn["notices"] == [
        {
            "id": "series:parasha:ki-tavo",
            "text": "The weekly portion: כי תבוא",
            "href": "/parasha?k=k",
        }
    ]
    again = draw(
        [mine],
        {
            "targum:follows": json.dumps({"parasha": 1}),
            "targum:series-seen": json.dumps({"parasha": "ki-tavo"}),
        },
        series=[PORTION],
    )
    assert again["carry"]["title"] == "שלי" and again["notices"] == [], "seen once"
    unfollowed = draw([mine], series=[PORTION])
    assert unfollowed["carry"]["title"] == "שלי" and unfollowed["notices"] == []


def test_the_sheet_says_how_long_is_left_from_what_the_reader_finished() -> None:
    """2026-09-11: a thin line along the sheet's foot and "about 12 min left", from the
    sections the reader records as finished and the text's own length. A text not yet
    started says its length; one finished says so."""
    book = reader(
        "book-he", "ספר", minutes=40, chapters=[{"number": n} for n in range(4)], readyChapters=4
    )
    fresh = draw([book], {"targum:opened": json.dumps({"book-he": 3})})
    assert "about 40 min" in fresh["carry"]["meta"] and "left" not in fresh["carry"]["meta"]
    assert fresh["carry"]["progress"] == ""
    half = draw(
        [book],
        {
            "targum:opened": json.dumps({"book-he": 3}),
            "targum:docs": json.dumps({"book-he": {"sections": {"1": 5, "2": 6}}}),
        },
    )
    assert "about 20 min left" in half["carry"]["meta"]
    assert half["carry"]["progress"] == "0.5"
    done = draw(
        [book],
        {
            "targum:opened": json.dumps({"book-he": 3}),
            "targum:docs": json.dumps({"book-he": {"sections": {"1": 1, "2": 1, "3": 1, "4": 1}}}),
        },
    )
    assert "finished" in done["carry"]["meta"] and done["carry"]["progress"] == "1"


def test_the_page_greets_you_and_says_what_today_is() -> None:
    """Decided with David on 2026-09-11 ("I definitely don't know what I'm looking at"):
    the first line is a greeting with the account's name, under it the date and the
    week's portion where the box carries it, and the count at the end of the row."""
    portion = {
        "id": "parasha",
        "name": "The weekly portion",
        "page": "/parasha",
        "instalment": {
            "id": "haazinu",
            "title": "Ha'azinu",
            "hebrew": "האזינו",
            "when": "2026-09-12",
        },
    }
    drawn = draw([reader("a", "א")], me={"signedIn": True, "name": "David"}, series=[portion])
    assert drawn["greeting"].endswith(", David.") and drawn["greeting"].split(",")[0] in (
        "Boker tov",
        "Shalom",
        "Erev tov",
    ), "Hebrew's, in Latin letters; and no Shabbat shalom on a Saturday"
    assert drawn["today"].endswith(" · This week: האזינו") and len(drawn["today"]) > 20
    inside = re.search(r"\((.*)\)", drawn["today"])
    assert inside and re.search(r"[\u05d0-\u05ea]", inside.group(1)), (
        "the Hebrew date, in parentheses"
    )
    assert not re.search(r"\d", inside.group(1)), "in Hebrew letters, not digits: כ״ט אלול תשפ״ו"
    assert "״" in inside.group(1)
    unnamed = draw([reader("a", "א")], me={"signedIn": True, "name": ""})
    assert "," not in unnamed["greeting"] and unnamed["greeting"].endswith(".")
    assert "This week" not in unnamed["today"], "no portion on a box without one"


@pytest.mark.parametrize(
    ("code", "said"),
    [
        ("he", ("Boker tov", "Shalom", "Erev tov")),
        ("arc", ("Tzafra tava", "Shlama", "Ramsha tava")),
        ("yi", ("Gut morgn", "Gutn tog", "Gutn ovnt")),
        ("fr", ("Bonjour", "Bonsoir")),
        ("ru", ("Dobroye utro", "Dobry den", "Dobry vecher")),
        ("it", ("Buongiorno", "Buonasera")),
    ],
)
def test_the_greeting_is_in_the_language_the_page_is_in(code: str, said: tuple[str, ...]) -> None:
    """David, 2026-09-14: "the greeting in that language, but written in Latin" — the
    first words on the page are ones the reader can say before they can read the script."""
    drawn = draw([reader("a", "א")], me={"signedIn": True, "name": "David"}, language=code)
    first = drawn["greeting"].split(",")[0]
    assert first in said, drawn["greeting"]
    assert drawn["greeting"].endswith(", David.")
    assert re.fullmatch(r"[A-Za-z ]+", first), "in Latin letters"


def test_the_row_is_your_subscriptions_and_continue_reading() -> None:
    """David, 2026-09-11: "buttons should bring you to your subscriptions, to continue
    reading" — and then "remove the 'let's talk about it' button, too much since we
    already have a talk to targum button on the page". A followed series with a current
    instalment is a door; a press draws it in the sheet. A series not followed is not
    in the row, and one door alone is no row."""
    mine = reader("mine", "ספר שלי", document="d3", opened=5)
    portion = {
        "id": "parasha",
        "name": "The weekly portion",
        "page": "/parasha",
        "instalment": {
            "id": "haazinu",
            "title": "Ha'azinu",
            "hebrew": "האזינו",
            "when": "2026-09-12",
            "reader": "/parasha/read/haazinu/reader/sec-0001.html",
        },
    }
    digest = {
        "id": "weekly",
        "name": "Weekly News Digest",
        "page": "/weekly",
        "instalment": {
            "id": "2026-w37",
            "title": "Issue 37",
            "when": "2026-09-07",
            "reader": "/reader/w37/reader/index.html",
        },
    }
    stored = {
        "targum:opened": json.dumps({"d3": 5}),
        "targum:follows": json.dumps({"parasha": 1}),
        "targum:series-seen": json.dumps({"parasha": "haazinu"}),
    }
    drawn = draw([mine], stored, series=[portion, digest])
    assert [(d["label"], d["on"]) for d in drawn["doors"]] == [
        ("Continue reading", True),
        ("Recently read", False),
        ("Subscriptions", False),
    ]
    assert not drawn["menu"]["open"] and drawn["menu"]["link"] is None
    assert [(i["id"], i["label"], i["fresh"]) for i in drawn["menu"]["items"]] == [
        ("series:parasha", "The weekly portion", False)
    ], "one door however many subscriptions, with a menu under it"
    assert drawn["carry"]["title"] == "ספר שלי"
    opened = draw([mine], stored, series=[portion, digest], do=[{"door": "subscriptions"}])
    assert opened["menu"]["open"], "the door opens its menu"
    week = draw([mine], stored, series=[portion, digest], do=[{"door": "series:parasha"}])
    assert week["carry"]["title"] == "האזינו" and week["carry"]["heading"] == "The weekly portion"
    assert week["carry"]["frame"].startswith("/parasha/read/haazinu/reader/sec-0001.html")
    assert week["carry"]["href"] == "/parasha/read/haazinu/reader/sec-0001.html?k=k", (
        "Open goes to the reader, not the series' own page (David, 2026-09-11)"
    )
    assert [(d["label"], d["on"]) for d in week["doors"]] == [
        ("Continue reading", False),
        ("Recently read", False),
        ("The weekly portion", True),
    ], "the door says which subscription is in the sheet"
    both = dict(stored, **{"targum:follows": json.dumps({"parasha": 1, "weekly": 1})})
    unseen = draw([mine], dict(both, **{"targum:series-seen": "{}"}), series=[portion, digest])
    assert [(i["label"], i["fresh"]) for i in unseen["menu"]["items"]] == [
        ("The weekly portion", False),
        ("Weekly News Digest", True),
    ], "the newest lands in the sheet and is seen; the other keeps its dot"
    alone = draw([mine], {"targum:opened": json.dumps({"d3": 5})}, series=[portion, digest])
    assert [d["label"] for d in alone["doors"]] == ["Continue reading", "Recently read"], (
        "nothing followed: no subscriptions door"
    )
    nothing = draw([], {})
    assert nothing["doors"] == [], "no text in the sheet, no row"


def test_a_subscription_read_through_carries_a_check_in_its_menu() -> None:
    """2026-09-11: "for anything in subscriptions, once user has finished reading it,
    there should be some kind of mark". The series names the document its reader is and
    how many sections it has; every one finished in this browser is a check on the row.
    The weekly is three readers, one a level, and any of them read through counts."""
    mine = reader("mine", "ספר שלי", document="d3", opened=5)
    portion = {
        "id": "parasha",
        "name": "The weekly portion",
        "page": "/parasha",
        "instalment": {
            "id": "haazinu",
            "title": "Ha'azinu",
            "hebrew": "האזינו",
            "when": "2026-09-12",
            "reader": "/parasha/read/haazinu/reader/sec-0001.html",
            "document": "p-haazinu",
            "sections": 2,
        },
    }
    digest = {
        "id": "weekly",
        "name": "Weekly News Digest",
        "page": "/weekly",
        "instalment": {
            "id": "2026-w37",
            "title": "Issue 37",
            "when": "2026-09-07",
            "levels": [
                {"level": "aleph", "reader": "/reader/a/reader/index.html", "document": "w-a"},
                {"level": "bet", "reader": "/reader/b/reader/index.html", "document": "w-b"},
            ],
        },
    }
    stored = {
        "targum:opened": json.dumps({"d3": 5}),
        "targum:follows": json.dumps({"parasha": 1, "weekly": 1}),
        "targum:series-seen": json.dumps({"parasha": "haazinu", "weekly": "2026-w37"}),
    }

    def marks(docs: dict[str, Any]) -> list[tuple[str, bool]]:
        kept = dict(stored, **{"targum:docs": json.dumps(docs)})
        drawn = draw([mine], kept, series=[portion, digest])
        return [(i["label"], i["done"]) for i in drawn["menu"]["items"]]

    assert marks({}) == [("The weekly portion", False), ("Weekly News Digest", False)]
    assert marks({"p-haazinu": {"sections": {"1": 1}}}) == [
        ("The weekly portion", False),
        ("Weekly News Digest", False),
    ], "one section of two is not read through"
    assert marks({"p-haazinu": {"sections": {"1": 1, "2": 1}}, "w-b": {"done": 1}}) == [
        ("The weekly portion", True),
        ("Weekly News Digest", True),
    ], "every section; and any level of the weekly"


# The row over the sheet with one text of the reader's own and a suggestion (2026-09-11).
ROW = ["Continue reading", "Suggested", "Recently read"]


def test_suggested_is_a_text_that_fits_with_no_conversation() -> None:
    """David, 2026-09-11: "add also 'suggested' which brings you to a text that fits
    your level and interests, without needing to chat". The server's one pick is a
    door after Continue reading; a press draws it in the sheet with why, and Open goes
    to its library row — or the text is framed where it is built already."""
    mine = reader("mine", "ספר שלי", document="d3", opened=5)
    stored = {"targum:opened": json.dumps({"d3": 5})}
    pick = {
        "id": "esther",
        "title": "אסתר",
        "english": "Esther",
        "language": "he",
        "minutes": 25,
        "register": "biblical",
        "because": "You know 50% of its words.",
        "known_share": 0.5,
        "reader": "",
    }
    drawn = draw([mine], stored, suggest=pick)
    assert [d["label"] for d in drawn["doors"]] == ROW
    pressed = draw([mine], stored, suggest=pick, do=[{"door": "suggested"}])
    assert (
        pressed["carry"]["title"] == "אסתר" and pressed["carry"]["heading"] == "Suggested for you"
    )
    assert pressed["carry"]["meta"] == "You know 50% of its words. · 25 min"
    assert pressed["carry"]["frame"] == "", "not built for this reader: nothing to frame"
    # The door, not the shelf (targum-internal#313). It sends a reader straight to their
    # copy where they have one and to its row with the offer up where they have not —
    # which is what this text is, and which the library row still handles.
    assert pressed["carry"]["href"] == "/open/esther?k=k", "Open goes to the text"
    assert pressed["carry"]["known"] == "You know 50%"
    built_ = draw(
        [mine],
        stored,
        suggest=dict(pick, reader="/reader/esther-he/reader/index.html"),
        do=[{"door": "suggested"}],
    )
    assert built_["carry"]["frame"].startswith("/reader/esther-he/reader/index.html?k=k"), (
        "built on the shared shelf: framed in the sheet"
    )
    none = draw([mine], stored)
    assert [d["label"] for d in none["doors"]] == ["Continue reading", "Recently read"], (
        "nothing suggested and nothing followed: no Suggested door"
    )


def test_a_finished_suggestion_makes_way_for_the_next() -> None:
    """David, 2026-09-11: "once a user has finished a 'suggested' text, a new one should
    populate the suggested tab". What this browser records as finished goes up with the
    ask, by catalogue id, so the server's pick is the next one; and the door is asked
    again when the framed reader writes a finish."""
    esther = reader("esther-he", "אסתר", "esther", document="esther-he", shared=True)
    mine = reader("mine", "ספר שלי", document="d3", opened=5)
    docs = {"esther-he": {"done": 1}, "d3": {"sections": {"1": 0}}}
    drawn = draw(
        [mine],
        {"targum:opened": json.dumps({"d3": 5}), "targum:docs": json.dumps(docs)},
        shared=[esther],
        suggest={"id": "ruth", "title": "רות", "because": "Not measured yet."},
    )
    asked = [a["path"] for a in drawn["asked"] if a["path"].startswith("/suggest")]
    assert asked == ["/suggest?language=he&skip=esther&k=k"], (
        "finished, by catalogue id, and nothing else"
    )
    assert [d["label"] for d in drawn["doors"]] == ROW
    nothing_done = draw(
        [mine],
        {"targum:opened": json.dumps({"d3": 5})},
        shared=[esther],
        suggest={"id": "esther", "title": "אסתר", "because": "You know 50% of its words."},
    )
    asked = [a["path"] for a in nothing_done["asked"] if a["path"].startswith("/suggest")]
    assert asked == ["/suggest?language=he&k=k"], "in the language Learn is in"


def test_suggested_falls_back_to_the_catalogue_s_next_step() -> None:
    """The door is never simply missing (2026-09-11, live: "Suggested on learn page is
    missing"): with no pick from the server, the catalogue's own next step — worked out
    here from what this browser knows — is the suggestion, and Open goes to its row."""
    mine = reader("mine", "ספר שלי", document="d3", opened=5, difficulty=20)
    stored = {"targum:opened": json.dumps({"d3": 5})}
    catalogue = [entry("easy", "קל", 10), entry("harder", "קשה", 30), entry("hardest", "הכי", 50)]
    drawn = draw([mine], stored, catalogue=catalogue)
    assert [d["label"] for d in drawn["doors"]] == ROW
    pressed = draw([mine], stored, catalogue=catalogue, do=[{"door": "suggested"}])
    assert pressed["carry"]["title"] == "קשה" and pressed["carry"]["heading"] == "Suggested for you"
    assert pressed["carry"]["meta"].startswith("A step up from what you've read")
    assert pressed["carry"]["href"] == "/open/harder?k=k"


def test_past_the_modern_catalogue_suggested_offers_another_register() -> None:
    """Live (2026-09-11): a reader who has built every modern text saw no Suggested door
    at all. Past the modern catalogue the fallback offers what is left in any register."""
    built_all = [
        reader("m1", "מ1", "m1", document="m1", opened=5, difficulty=10),
        reader("m2", "מ2", "m2", document="m2", opened=4, difficulty=30),
    ]
    stored = {"targum:opened": json.dumps({"m1": 5, "m2": 4})}
    catalogue = [
        entry("m1", "מ1", 10, register="modern"),
        entry("m2", "מ2", 30, register="modern"),
        entry("ruth", "רות", 12, register="biblical"),
    ]
    drawn = draw(built_all, stored, catalogue=catalogue, do=[{"door": "suggested"}])
    assert [d["label"] for d in drawn["doors"]] == ROW
    assert drawn["carry"]["title"] == "רות" and drawn["carry"]["heading"] == "Suggested for you"


def test_the_date_follows_the_language_the_page_is_in() -> None:
    """2026-09-14: the Hebrew date is for Hebrew, Aramaic and Yiddish, with the week's
    portion. In French, Italian or Russian the date is the country's, in its language,
    and the portion is not this page's to mention."""
    portion = {
        "id": "parasha",
        "name": "Parashat HaShavua",
        "instalment": {
            "id": "haazinu",
            "title": "Ha'azinu",
            "hebrew": "האזינו",
            "when": "2026-09-12",
        },
    }
    aramaic = draw([reader("a", "א")], series=[portion], language="arc")
    assert "This week: האזינו" in aramaic["today"]
    assert re.search(r"\(.*[\u05d0-\u05ea].*\)", aramaic["today"]), "the Hebrew date"

    french = draw([reader("a", "א")], series=[portion], language="fr")
    inside = re.search(r"\((.*)\)", french["today"])
    assert inside and not re.search(r"[\u05d0-\u05ea]", french["today"])
    assert re.search(r"(lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche)", inside.group(1))
    assert "This week" not in french["today"]

    russian = draw([reader("a", "א")], language="ru")
    assert re.search(r"[\u0400-\u04ff]", russian["today"]), "in Russian"


def test_the_page_says_its_words_in_the_readers_language() -> None:
    """A Russian reader's Learn counts in Russian, with the plural Russian's rules choose,
    and a door the catalogue has not filled says its English (targum-internal#184)."""
    known = [word(f"מילה{n}", "w", status=9) for n in range(12)]
    drawn = draw(
        [],
        vocabulary(*known),
        catalogue=CATALOGUE,
        strings={
            "language": "ru",
            "strings": {
                "learn.known-words.many": "Вы знаете {n} слов: {language}.",
                "learn.known-words.other": "Вы знаете {n} слова: {language}.",
                "learn.minutes": "{n} мин",
            },
        },
    )
    assert drawn["known"] == "Вы знаете 12 слов: Hebrew."
    assert drawn["carry"]["heading"] == "Start here"
    assert drawn["carry"]["meta"] == "Where most people start · 10 мин"


# --- the arrival (targum-internal#294, subjects since 2026-09-17) -------------------


def seeded() -> list[dict[str, Any]]:
    """Shelves the arrival can answer, each carrying the subject it is filed under.

    `tags` are `catalogue.Tag` values and arrive on the `/readers` row; `kind` is what it
    always was. The first version of these fixtures invented `kind="video"`, which made
    the tests pass against a data model that does not exist — the shapes here are the
    ones `/readers` really sends.
    """
    return [
        reader("scene-1", "סצנה", "scene-1", kind="dialogue", register="modern"),
        reader("ruth", "רות", "ruth", register="biblical", tags=["tanakh"]),
        reader("holon", "הפועל", "holon", kind="article", register="modern", tags=["sport"]),
    ]


def test_the_page_does_not_quietly_give_up_drawing() -> None:
    """`learn.js` catches around its whole draw, so a bug in it shows as "we couldn't
    load your texts" rather than as a stack trace. Every arrival fixture is checked."""
    for stamps in ({}, {"targum:arrived": "sport"}, {"targum:arrived": "judaism,sport,food"}):
        assert not draw([], stamps, shared=seeded())["broke"], stamps


def test_a_new_reader_is_asked_what_they_are_interested_in() -> None:
    """In subjects, in the words somebody uses about themselves — not in the register,
    collection and file format the library happens to be built from."""
    drawn = draw([], shared=seeded())
    assert not drawn["broke"]
    assert drawn["arrival"][:4] == ["Everyday life in Israel", "Torah and Judaism", "News", "Sport"]
    assert "Archaeology" in drawn["arrival"]
    # And the sheet is open under it: ignoring the question costs nothing.
    assert not drawn["carry"]["hidden"]


def test_every_subject_is_offered_including_the_ones_with_nothing_behind_them() -> None:
    """The rule the one-door version held to — a door with nothing seeded behind it is
    left out — belonged to an answer that routed straight to a text. Three answers are a
    profile, and a profile may name something the library has not got yet. That it was
    named is the most useful thing anybody can say about what to build next."""
    thin = draw(
        [], shared=[reader("scene-1", "סצנה", "scene-1", kind="dialogue", register="modern")]
    )
    assert "Archaeology" in thin["arrival"], "asked for whether or not it can be answered"
    assert "Poetry" in thin["arrival"]
    assert len(thin["arrival"]) == 19


def test_the_ladder_is_the_ulpan_one_and_says_it_in_words() -> None:
    """targum-internal#306, decided 2026-09-17: the rung is asked, narrowly.

    Eight rungs, aleph to vav, the ladder `level.py` already climbs. The words come
    first and the kitah second, because the letter is the whole label to somebody who
    did an ulpan and noise to everybody else.
    """
    drawn = draw([], shared=seeded())
    assert len(drawn["levels"]) == 8
    assert drawn["levels"][0].startswith("Just starting")
    assert drawn["levels"][0].endswith("\u05d0"), "the kitah beside the words, not instead"
    assert drawn["levels"][-1].endswith("\u05d5")


def test_three_subjects_and_a_rung_before_the_answer_is_taken() -> None:
    """One subject is a label and two is a preference; three is the first number that
    describes somebody. The rung is the other half of the question."""
    two = draw([], shared=seeded(), do=[{"subject": "Sport"}, {"subject": "History"}])
    assert two["done"] is False, "two is not enough"
    assert two["counted"] == "Pick 1 more"

    three = draw(
        [],
        shared=seeded(),
        do=[{"subject": "Sport"}, {"subject": "History"}, {"subject": "Archaeology"}],
    )
    assert three["done"] is False, "the subjects are not the whole question"
    assert three["counted"] == ""

    both = draw(
        [],
        shared=seeded(),
        do=[
            {"subject": "Sport"},
            {"subject": "History"},
            {"subject": "Archaeology"},
            {"rung": "I read slowly, with help"},
        ],
    )
    assert both["done"] is True


def test_the_rung_is_kept_nowhere() -> None:
    """The whole of #306's decision: asked, used once, thrown away.

    The subjects are kept — they are a profile and they travel between devices. The rung
    is not: no key in the browser, nothing posted to the account, no column behind it. A
    number nobody keeps is a number nobody can be wrong about a month later.
    """
    after = draw(
        [],
        shared=seeded(),
        do=[
            {"subject": "Sport"},
            {"subject": "Torah and Judaism"},
            {"subject": "Archaeology"},
            {"rung": "I read almost anything"},
            {"press": "arrival-done"},
        ],
    )
    kept = after.get("kept") or {}
    posted = after.get("posted") or []
    # The harness would have shown it: the subjects went both places on the same press.
    assert "targum:arrived" in kept, "the subjects are kept, so this test can see keeping"
    assert any("/account/interest" in str(where) for where in posted), (
        "the subjects are posted, so this test can see posting"
    )
    assert not any("level" in key for key in kept), f"the rung was stored: {kept}"
    assert not any("level" in str(where) for where in posted), f"the rung was posted: {posted}"


def test_a_subject_pressed_twice_is_put_back() -> None:
    off = draw(
        [],
        shared=seeded(),
        do=[{"subject": "Sport"}, {"subject": "History"}, {"subject": "Sport"}],
    )
    assert off["picked"] == ["History"]


def test_the_answer_goes_away_and_picks_the_first_subject_the_shelf_can_answer() -> None:
    """Most of the nineteen have nothing behind them. The sheet is chosen from whichever
    of the reader's subjects the shelf can actually satisfy, in the order offered."""
    came = draw([], {"targum:arrived": "judaism,sport,archaeology"}, shared=seeded())
    assert came["arrival"] == [], "answered once, never asked again"
    assert came["carry"]["title"] == "רות", "judaism is offered before sport"

    # Nothing seeded for archaeology or history, so the one subject that is answerable
    # decides the sheet rather than the whole answer falling back to the default track.
    thin = draw([], {"targum:arrived": "archaeology,history,sport"}, shared=seeded())
    assert thin["carry"]["title"] == "הפועל"


def test_a_subject_nothing_is_filed_under_falls_back_to_the_track() -> None:
    """Three subjects the shelf cannot answer is not a reason to draw no sheet."""
    none = draw([], {"targum:arrived": "archaeology,art,music"}, shared=seeded())
    assert not none["broke"]
    assert not none["carry"]["hidden"], "the default track still has the sheet"


def test_a_reader_already_reading_is_never_asked() -> None:
    """It is a question for somebody who has just arrived, not an interruption."""
    already = draw([], {"targum:opened": json.dumps({"scene-1": 7})}, shared=seeded())
    assert already["arrival"] == []


def test_a_retired_answer_is_dropped_and_the_question_asked_again(tmp_path: Path) -> None:
    """`spoken`, `portion` and `video` were the old vocabulary. The account's copy is
    migrated; a browser holding one of them is not, so the word is dropped on the way in
    and the reader is asked in the new terms rather than routed on a word nothing
    means any more."""
    asked = draw(
        [],
        {"targum:arrived": "video"},
        shared=[
            reader("scene-1", "סצנה", "scene-1", kind="dialogue", register="modern"),
            reader("ruth", "רות", "ruth", register="biblical", tags=["tanakh"]),
        ],
    )
    assert asked["arrival"], "asked again rather than acted on"
    assert asked["carry"]["title"] == "סצנה", "its register's own door, not nothing"
