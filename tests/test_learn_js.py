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


def test_a_shelf_row_is_a_row_of_columns() -> None:
    """It was a stack of two-line entries with the controls floating off to the right —
    three alignments in one row, which reads as none. One cell each now, under a heading
    that says what it is."""
    drawn = draw(
        [
            reader("psalms-he", "תהילים", entry="psalms", opened=2),
            reader(
                "genesis-he",
                "בראשית",
                entry="genesis",
                opened=1,
                chapters=[{"number": n} for n in range(50)],
                readyChapters=50,
            ),
        ]
    )

    # The first goes into the carry panel; the shelf holds the rest.
    (row,) = drawn["shelf"]
    assert drawn["head"] is False, "the columns are labelled"
    assert row["title"] == "בראשית"
    assert row["cover"] is not None
    assert row["chapters"] == "50 chapters", (
        "all of it bought, said as a count rather than a fraction"
    )
    assert "ago" in row["opened"] or row["opened"] == "not opened yet"
    assert row["controls"] == ["Chapters", "Delete"]


def test_a_text_with_one_part_says_so_rather_than_counting_to_one() -> None:
    drawn = draw(
        [
            reader("psalms-he", "תהילים", entry="psalms", opened=2),
            reader("article-he", "כתבה", opened=1),
        ]
    )

    (row,) = drawn["shelf"]
    assert row["chapters"] == "—", "nothing to count, and nothing pretending there is"
    assert row["controls"] == ["Delete"], "and no chapters to open"


def test_a_text_the_catalogue_never_heard_of_still_gets_a_row() -> None:
    """Covers are drawn on the project's budget, for the library's own texts. Most of a
    reader's shelf is their own, has no cover and never will, and a shelf of empty frames
    would be worse than a shelf of letters — so the tile rests on the text's own first
    letter instead."""
    drawn = draw(
        [
            reader("psalms-he", "תהילים", entry="psalms", opened=2),
            reader("ynet-he", "כתבה על משהו", opened=1),
        ]
    )

    (row,) = drawn["shelf"]
    assert row["title"] == "כתבה על משהו"
    assert row["cover"] is not None, "the row keeps its shape"
    assert row["cover"]["letter"] == "כ", "and rests on the text's own letter"


def test_an_empty_shelf_says_nothing_about_covers() -> None:
    drawn = draw([])
    assert drawn["carry"]["hidden"] is True
    assert drawn["shelf"] == []


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
    assert (
        drawn["known"] == "Read, tap the words you do not know, and talk to targum about any line."
    )
    nine = draw([reader("a", "א")], vocabulary(*(word(f"מ{n}", "w", status=9) for n in range(9))))
    assert (
        nine["known"] == "Read, tap the words you do not know, and talk to targum about any line."
    )
    ten = draw([reader("a", "א")], vocabulary(*(word(f"מ{n}", "w", status=9) for n in range(10))))
    assert ten["known"] == "You know 10 Hebrew words."


def test_knowing_nothing_yet_asks_rather_than_scoring_zero() -> None:
    """ "You know 0 words" is a score of zero, which is the arcade the brand keeps out."""
    drawn = draw([reader("a", "א")], vocabulary(word("ספר", "book", status=1)))
    assert (
        drawn["known"] == "Read, tap the words you do not know, and talk to targum about any line."
    )


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
    top = page[page.index('<div class="front" id="front">') : page.index('id="shelf-panel"')]
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


def test_the_shelf_shows_the_first_few_and_says_where_the_rest_are() -> None:
    """Twelve texts is a page of twelve rows, and this is a page somebody lands on. The
    top of the list belongs here; the list belongs on its own page."""
    shelf = [reader(f"r{n}", f"ספר {n}", built=100 - n) for n in range(9)]
    drawn = draw(shelf)
    # One of the nine is the carry panel above, so eight are left for the shelf.
    assert len(drawn["shelf"]) == 5, "five rows, whatever the shelf holds"
    assert drawn["seeAll"]["shelf"] == "See all 8 →"


def test_a_short_shelf_is_not_offered_a_page_of_its_own() -> None:
    drawn = draw([reader("a", "א"), reader("b", "ב")])
    assert drawn["seeAll"]["shelf"] == "", "one row left, and nowhere else to go"


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
    assert "/library" in drawn["carry"]["href"] and drawn["carry"]["href"].endswith("#easy")


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
    assert drawn["carry"]["meta"].startswith("About where you are reading")


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
    assert (
        fresh["known"] == "Read, tap the words you do not know, and talk to targum about any line."
    )
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


def test_a_shelf_with_some_chapters_still_to_come_says_so() -> None:
    """ "2 of 4" is a fraction with nothing to say what it is a fraction of."""
    drawn = draw(
        [
            reader("psalms-he", "תהילים", entry="psalms", opened=2),
            reader(
                "genesis-he",
                "בראשית",
                entry="genesis",
                opened=1,
                chapters=[{"number": n} for n in range(4)],
                readyChapters=2,
            ),
        ]
    )
    (row,) = drawn["shelf"]
    assert row["chapters"] == "2 of 4 translated"


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
    assert [row["title"] for row in drawn["shelf"]] == [], "not repeated below"


def test_an_account_that_knows_nothing_starts_on_scene_one() -> None:
    """The sheet at Start here on Scene 1, which says which scene of how many, how long,
    and that it can be heard. Nothing says "ready", and Open opens a built text."""
    drawn = draw([], shared=SCENES + [RUTH])
    assert (
        drawn["known"] == "Read, tap the words you do not know, and talk to targum about any line."
    )
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
    assert (
        drawn["known"] == "Read, tap the words you do not know, and talk to targum about any line."
    )


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
    assert (
        drawn["known"] == "Read, tap the words you do not know, and talk to targum about any line."
    )


def test_a_scene_finished_on_another_device_is_not_a_start() -> None:
    """`done` syncs; `opened` does not. A new browser has the finish and no last-opened
    text, and the door reads Up next rather than sending the reader back to Scene 1."""
    done = {"targum:docs": json.dumps({"scene-01-nice-to-meet-you-he": {"done": 9}})}
    drawn = draw([], done, shared=SCENES + [RUTH])
    assert drawn["carry"]["heading"] == "Up next" and drawn["carry"]["title"] == "בבית קפה"
    assert (
        drawn["known"] == "Read, tap the words you do not know, and talk to targum about any line."
    ), "every word ignored and Done pressed is not a score of zero"


def test_past_the_last_scene_the_modern_door_steps_up() -> None:
    done = {"targum:docs": json.dumps({s["document"]: {"done": 9} for s in SCENES})}
    drawn = draw([], done, shared=SCENES + [RUTH], catalogue=CATALOGUE)
    assert drawn["carry"]["heading"] == "Start here", "nothing built yet on this track"
    assert drawn["carry"]["title"] == "קל"
    assert "/library" in drawn["carry"]["href"] and drawn["carry"]["href"].endswith("#easy")


def test_an_upload_takes_the_door_of_its_own_hebrew() -> None:
    mine = reader("mine-he", "שלי")
    drawn = draw([mine], {"targum:opened": json.dumps({"mine-he": 3})}, shared=SCENES + [RUTH])
    assert drawn["carry"]["heading"] == "Continue reading" and drawn["carry"]["title"] == "שלי"
    assert [row["title"] for row in drawn["shelf"]] == [], "the sheet's text is not repeated below"


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
        "Good morning",
        "Good afternoon",
        "Good evening",
    ), "no Shabbat shalom: somebody on the internet on Shabbat does not get one"
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
        ("Subscriptions", False),
    ]
    assert drawn["menu"] == {
        "open": False,
        "items": [{"id": "series:parasha", "label": "The weekly portion", "fresh": False}],
    }, "one door however many subscriptions, with a menu under it"
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
        ("The weekly portion", True),
    ], "the door says which subscription is in the sheet"
    both = dict(stored, **{"targum:follows": json.dumps({"parasha": 1, "weekly": 1})})
    unseen = draw([mine], dict(both, **{"targum:series-seen": "{}"}), series=[portion, digest])
    assert [(i["label"], i["fresh"]) for i in unseen["menu"]["items"]] == [
        ("The weekly portion", False),
        ("Weekly News Digest", True),
    ], "the newest lands in the sheet and is seen; the other keeps its dot"
    alone = draw([mine], {"targum:opened": json.dumps({"d3": 5})}, series=[portion, digest])
    assert alone["doors"] == [], "one door is no choice"
    nothing = draw([], {})
    assert nothing["doors"] == [], "no text in the sheet, no row"


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
    assert [d["label"] for d in drawn["doors"]] == ["Continue reading", "Suggested"]
    pressed = draw([mine], stored, suggest=pick, do=[{"door": "suggested"}])
    assert (
        pressed["carry"]["title"] == "אסתר" and pressed["carry"]["heading"] == "Suggested for you"
    )
    assert pressed["carry"]["meta"] == "You know 50% of its words. · 25 min"
    assert pressed["carry"]["frame"] == "", "not built for this reader: nothing to frame"
    assert pressed["carry"]["href"] == "/library?k=k#esther", "Open goes to its library row"
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
    assert none["doors"] == [], "nothing suggested and nothing followed: one door, no row"


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
    assert asked == ["/suggest?skip=esther&k=k"], "finished, by catalogue id, and nothing else"
    assert [d["label"] for d in drawn["doors"]] == ["Continue reading", "Suggested"]
    nothing_done = draw(
        [mine],
        {"targum:opened": json.dumps({"d3": 5})},
        shared=[esther],
        suggest={"id": "esther", "title": "אסתר", "because": "You know 50% of its words."},
    )
    asked = [a["path"] for a in nothing_done["asked"] if a["path"].startswith("/suggest")]
    assert asked == ["/suggest?k=k"]


def test_suggested_falls_back_to_the_catalogue_s_next_step() -> None:
    """The door is never simply missing (2026-09-11, live: "Suggested on learn page is
    missing"): with no pick from the server, the catalogue's own next step — worked out
    here from what this browser knows — is the suggestion, and Open goes to its row."""
    mine = reader("mine", "ספר שלי", document="d3", opened=5, difficulty=20)
    stored = {"targum:opened": json.dumps({"d3": 5})}
    catalogue = [entry("easy", "קל", 10), entry("harder", "קשה", 30), entry("hardest", "הכי", 50)]
    drawn = draw([mine], stored, catalogue=catalogue)
    assert [d["label"] for d in drawn["doors"]] == ["Continue reading", "Suggested"]
    pressed = draw([mine], stored, catalogue=catalogue, do=[{"door": "suggested"}])
    assert pressed["carry"]["title"] == "קשה" and pressed["carry"]["heading"] == "Suggested for you"
    assert pressed["carry"]["meta"].startswith("A step up from what you have read")
    assert pressed["carry"]["href"] == "/library?k=k#harder"
