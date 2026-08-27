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
    """One entry of `targum:vocab:he`, as the reader writes it."""
    row = {"surface": lemma, "meaning": meaning, "status": status, "band": "moderate", "at": 0}
    row.update(extra)
    return {lemma: row}


def vocabulary(*words: dict[str, Any]) -> dict[str, str]:
    """A `stored` payload holding those words, for the harness's localStorage."""
    together: dict[str, Any] = {}
    for one in words:
        together.update(one)
    return {"targum:vocab:he": json.dumps(together, ensure_ascii=False)}


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
    assert drawn["carry"]["href"].endswith("reader/index.html?k=k"), (
        "and the whole box opens the book — the cover and the title are not their own links"
    )


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
    assert row["chapters"] == "50 of 50", "how much of it is bought, on its own"
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
    drawn = draw(
        [reader("a", "אהבת ציון")],
        vocabulary(
            word("ספר", "book", status=9),
            word("בית", "house", status=9),
            word("דרך", "road", status=2),
        ),
    )
    assert drawn["known"] == "You know 2 Hebrew words."


def test_one_word_known_is_not_said_in_the_plural() -> None:
    drawn = draw([reader("a", "א")], vocabulary(word("ספר", "book", status=9)))
    assert drawn["known"] == "You know 1 Hebrew word."


def test_knowing_nothing_yet_asks_rather_than_scoring_zero() -> None:
    """ "You know 0 words" is a score of zero, which is the arcade the brand keeps out."""
    drawn = draw([reader("a", "א")], vocabulary(word("ספר", "book", status=1)))
    assert drawn["known"] == "Mark a word while reading and it starts here."


def test_the_word_list_starts_on_what_you_are_still_learning() -> None:
    """Known words are the ones that need no more work. The list opens on the ones that
    do, which is what the markup's selected option says and what the page must obey."""
    drawn = draw(
        [reader("a", "א")],
        vocabulary(
            word("ספר", "book", status=9),
            word("דרך", "road", status=2),
            word("עיר", "city", status=0),
        ),
    )
    assert [row["term"] for row in drawn["words"]] == ["דרך"]
    assert drawn["wordsTitle"] == "Your Words (1)"


def test_every_word_is_there_when_that_is_what_was_asked_for() -> None:
    drawn = draw(
        [reader("a", "א")],
        vocabulary(word("ספר", "book", status=9), word("דרך", "road", status=2)),
        filter="all",
    )
    assert sorted(row["term"] for row in drawn["words"]) == ["דרך", "ספר"]


def test_a_search_looks_at_the_word_its_dictionary_form_and_its_meaning() -> None:
    """Three columns, because a reader who remembers only the English is the one most in
    need of the search."""
    kept = vocabulary(
        word("ספר", "book", status=2),
        word("הלך", "walked", status=2, surface="הולך"),
        word("עיר", "city", status=2),
    )
    assert [row["term"] for row in draw([reader("a", "א")], kept, search="book")["words"]] == [
        "ספר"
    ]
    assert [row["term"] for row in draw([reader("a", "א")], kept, search="הלך")["words"]] == [
        "הולך"
    ]
    assert (
        draw([reader("a", "א")], kept, search="zzz")["wordsEmpty"] == "Nothing here matches that."
    )


def test_your_own_meaning_is_the_one_shown() -> None:
    """A definition the reader corrected beats the one the machine wrote, here as in the
    reader itself."""
    drawn = draw(
        [reader("a", "א")],
        vocabulary(word("ספר", "book", status=2, note="scroll")),
    )
    assert drawn["words"][0]["meaning"] == "scroll"


def test_phrases_are_grouped_by_the_text_they_came_from() -> None:
    """A phrase out of its text is a string of words nobody can place."""
    stored = {
        "targum:docs": json.dumps({"h1": {"language": "he", "title": "אהבת ציון"}}),
        "targum:picked:h1": json.dumps({"s1": [{"text": "לב טוב", "meaning": "a good heart"}]}),
    }
    drawn = draw([reader("a", "א")], stored)
    assert drawn["phrases"] == {"אהבת ציון": ["לב טוב"]}
    assert drawn["phrasesTitle"] == "Your Phrases (1)"


def test_nothing_offers_an_export_to_a_browser_with_no_account() -> None:
    """An export comes from the account. Signed out there is nothing to hand back but a
    subset of one browser, with no sign that anything is missing."""
    drawn = draw([reader("a", "א")], vocabulary(word("ספר", "book", status=2)))
    assert drawn["exports"] == {"words": True, "phrases": True}, "hidden, both of them"


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
    top = page[page.index('<div class="doors">') : page.index('id="shelf-panel"')]
    assert top.count('<a class="door') == 1, "carrying on is a link: it goes to a reader"
    assert top.count('<button type="button" class="door') == 1, "the suggestion acts"
    assert top.count('<a class="step"') == 3, "the library, the upload and the progress"
    assert 'id="suggest"' in top, "and the suggestion is only there when there is one"
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


def test_the_word_list_stops_at_ten_and_points_at_the_rest() -> None:
    words = vocabulary(*(word(f"מילה{n}", f"word {n}", status=2) for n in range(24)))
    drawn = draw([reader("a", "א")], words)
    assert len(drawn["words"]) == 10
    assert drawn["seeAll"]["words"] == "See all 24 →"


def test_the_phrase_list_stops_at_five() -> None:
    stored = {
        "targum:docs": json.dumps({"h1": {"language": "he", "title": "אהבת ציון"}}),
        "targum:picked:h1": json.dumps(
            {f"s{n}": [{"text": f"לב טוב {n}", "meaning": "a good heart"}] for n in range(9)}
        ),
    }
    drawn = draw([reader("a", "א")], stored)
    assert sum(len(rows) for rows in drawn["phrases"].values()) == 5
    assert drawn["seeAll"]["phrases"] == "See all 9 →"


# -- folding a list away ---------------------------------------------------------


def test_every_list_starts_open() -> None:
    drawn = draw([reader("a", "א")])
    for name, state in drawn["folds"].items():
        assert state == {"open": "true", "shown": True}, name


def test_folding_a_list_shuts_it_and_is_remembered() -> None:
    """Which lists somebody wants open is theirs to decide. Kept in this browser: it is
    the state of a screen, not a fact about a person."""
    drawn = draw([reader("a", "א")], do=[{"fold": "words"}])
    assert drawn["folds"]["words"] == {"open": "false", "shown": False}
    assert drawn["folds"]["shelf"]["shown"] is True, "and only the one pressed"
    assert json.loads(drawn["remembered"]) == {"words-body": 1}


def test_a_list_folded_last_time_starts_folded() -> None:
    drawn = draw([reader("a", "א")], {"targum:folded": json.dumps({"phrases-body": 1})})
    assert drawn["folds"]["phrases"] == {"open": "false", "shown": False}
    assert drawn["folds"]["words"]["shown"] is True


def test_unfolding_forgets_it_rather_than_remembering_a_negative() -> None:
    drawn = draw(
        [reader("a", "א")],
        {"targum:folded": json.dumps({"words-body": 1})},
        do=[{"fold": "words"}],
    )
    assert drawn["folds"]["words"] == {"open": "true", "shown": True}
    assert json.loads(drawn["remembered"]) == {}


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


def test_a_reader_with_no_texts_is_pointed_at_the_easiest_thing() -> None:
    """Words kept but nothing on the shelf — someone who has read in the reader and
    deleted it, or is starting again. There is no level to step up from, so the answer is
    where everybody starts. (A browser with nothing at all gets the empty state instead,
    which is a different page.)"""
    drawn = draw([], vocabulary(word("ספר", "book", status=2)), catalogue=CATALOGUE)
    assert drawn["suggested"]["title"] == "קל"
    assert drawn["suggested"]["why"] == "Where most people start · 10 min"
    assert drawn["suggested"]["entry"] == "easy", "and pressing it would build that one"


def test_the_suggestion_is_a_step_up_from_the_hardest_thing_read() -> None:
    """Level is the difficulty of what they have actually built — the share of running
    words needing a lookup — rather than a guess about the person."""
    shelf = [reader("a", "א", difficulty=24), reader("b", "ב", difficulty=16)]
    drawn = draw(shelf, catalogue=CATALOGUE)
    assert drawn["suggested"]["title"] == "קשה", "the easiest one harder than 24"
    assert drawn["suggested"]["why"].startswith("A step up")


def test_something_already_built_is_not_suggested_again() -> None:
    shelf = [reader("a", "א", entry="harder", difficulty=32)]
    drawn = draw(shelf, catalogue=CATALOGUE)
    assert drawn["suggested"]["title"] == "הקשה", "the next one up, not the one they have"


def test_a_reader_past_the_whole_catalogue_is_told_the_truth() -> None:
    shelf = [reader("a", "א", difficulty=99)]
    drawn = draw(shelf, catalogue=CATALOGUE)
    assert drawn["suggested"]["why"].startswith("About where you are reading")


def test_nothing_is_suggested_when_there_is_nothing_left() -> None:
    """An empty row saying nothing is worse than no row."""
    shelf = [reader(name, name, entry=name, difficulty=20) for name in ("easy", "middling")]
    drawn = draw(shelf, catalogue=[entry("easy", "קל", 16), entry("middling", "בינוני", 24)])
    assert drawn["suggested"] is None


def test_the_progress_step_carries_the_two_numbers_behind_it() -> None:
    kept = vocabulary(word("ספר", "book", status=9))
    stored = dict(kept)
    stored["targum:days"] = json.dumps({"2026-08-24": 1, "2026-08-25": 1})
    drawn = draw([reader("a", "א")], stored)
    assert drawn["progress"] == "1 word, 2 days"


def test_the_suggestion_is_a_card_with_a_picture_and_a_reason() -> None:
    """A line of text in a list is not something anybody takes up. It gets the same shape
    as the book you were already reading: a cover, a title, and a line about it."""
    drawn = draw(
        [reader("a", "א", difficulty=16)],
        catalogue=[entry("psalms", "תהילים", 24, blurb="A hundred and fifty of them.")],
    )
    assert drawn["suggested"]["blurb"] == "A hundred and fifty of them."
    assert drawn["suggested"]["cover"] is not None, "the same tile the shelf draws"
    assert drawn["suggested"]["cover"]["letter"] == "ת", "or the text's own first letter"


def test_pressing_the_suggestion_builds_the_text_it_offered() -> None:
    """The card acts rather than pointing somewhere.

    It used to be a link to the catalogue with this text outlined somewhere in it, which
    handed back the choice that had just been made for the reader — and the outline was
    lost altogether whenever the library had a filter remembered from last time.

    What is asserted is which text was sent. A card offering one book and building its
    neighbour would be unnoticeable, and expensive.
    """
    shelf = [reader("a", "א", difficulty=28)]
    drawn = draw(shelf, catalogue=CATALOGUE, do=[{"press": "suggest"}])

    assert drawn["suggested"]["entry"] == "harder", "the easiest one harder than 28"
    started = [call for call in drawn["asked"] if "/prepare" in call["path"]]
    assert len(started) == 1, "one press, one build"
    assert started[0]["body"]["source"] == "s:harder"
    assert started[0]["body"]["from"] == "he"
    # Every published translation, not the first. The reader switches between them, so a
    # build that sent one would quietly halve what the finished text offers.
    assert started[0]["body"]["translations"] == ["t:hard", "t:hard2"]


def test_a_text_nobody_has_translated_is_still_built() -> None:
    """Most of the catalogue has a published translation and some of it does not. The
    build is the same call either way — an empty list, not a missing key, which is what
    `/prepare` reads to mean there is nothing to line up against."""
    drawn = draw(
        [reader("a", "א", difficulty=28)],
        catalogue=[CATALOGUE[3]],
        do=[{"press": "suggest"}],
    )
    started = [call for call in drawn["asked"] if "/prepare" in call["path"]]
    assert started[0]["body"]["source"] == "s:hardest"
    assert started[0]["body"]["translations"] == []


def test_the_card_says_what_it_is_doing_and_cannot_be_pressed_twice() -> None:
    """A build takes minutes. The line that said why the text was suggested has done its
    job by then, so it is where the build narrates — and a card that stayed pressable
    would start a second build over the first, which costs twice."""
    drawn = draw(
        [reader("a", "א", difficulty=28)],
        catalogue=CATALOGUE,
        do=[{"press": "suggest"}, {"press": "suggest"}, {"press": "suggest"}],
    )
    assert drawn["suggested"]["why"] != "", "it says something"
    assert not drawn["suggested"]["why"].startswith("A step up"), "and it is not the reason"
    assert drawn["suggested"]["disabled"] is True
    started = [call for call in drawn["asked"] if "/prepare" in call["path"]]
    assert len(started) == 1, "three presses, one build"
