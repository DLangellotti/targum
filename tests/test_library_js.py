"""The library page's script, run rather than read.

Every other test of the reader's JavaScript checks that a line of source exists. That
caught nothing twice: two shipped bugs lived in this code, and a third — searching for
"herzl" matching nothing, because every title and byline in the catalogue is in Hebrew —
was found by running it. This runs it.

The harness is a stub document in `tests/js/`, not a browser. It cannot see a layout, a
style or an event, so nothing here asserts about appearance; what it asserts is what the
page decided: which rows, in which order, with which columns and which controls. That is
where the bugs were.

The catalogue comes from the package rather than a fixture, so the data these assertions
run against is the data a reader gets.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

HERE = Path(__file__).resolve().parent
HARNESS = HERE / "js" / "library.js"
ASSETS = HERE.parent / "src/targum/render/assets"

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")


def shelf(entry_id: str, name: str, **extra: Any) -> dict[str, Any]:
    """A reader's own copy of a text, as `/readers` describes one."""
    row = {
        "name": name,
        "title": name,
        "language": "he",
        "document": "h",
        "words": 1000,
        "minutes": 8,
        "kind": "prose",
        "register": "modern",
        "difficulty": 20,
        "entry": entry_id,
        "drawn": False,
        "sections": 1,
        "chapters": [],
        "readyChapters": 0,
        "built": 0,
    }
    row.update(extra)
    return row


def draw(tmp_path: Path, **payload: Any) -> dict[str, Any]:
    from targum.catalogue import CATALOGUE

    payload.setdefault("catalogue", [entry.state() for entry in CATALOGUE])
    payload.setdefault("readers", [])
    where = tmp_path / "payload.json"
    where.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    done = subprocess.run(
        ["node", str(HARNESS), str(where)], capture_output=True, text=True, timeout=60
    )
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def test_every_hebrew_text_gets_a_row(tmp_path: Path) -> None:
    from targum.catalogue import CATALOGUE

    drawn = draw(tmp_path)

    hebrew = [entry for entry in CATALOGUE if entry.language.startswith("he")]
    assert len(drawn["rows"]) == len(hebrew)
    assert drawn["tally"] == f"{len(hebrew)} texts"
    assert drawn["columns"][:2] == ["Text", "Kind"]


def test_a_row_carries_what_the_filters_sort_on(tmp_path: Path) -> None:
    """Whatever a row shows has to be the same vocabulary the catalogue is written in,
    or the filters and the rows are describing different things."""
    row = next(r for r in draw(tmp_path)["rows"] if r["title"] == "תהילים")

    assert row["cells"][0] == "Poetry"
    assert row["cells"][1] == "Biblical"
    assert row["cells"][2].endswith("hr"), "a hundred and fifty psalms is not minutes"
    assert row["cells"][3].endswith("%"), "how much of it you would look up"


@pytest.mark.parametrize(
    ("view", "expected"),
    [
        ({"kind": "novel"}, {"ספר הקבצנים", "תל־אביב"}),
        ({"register": "biblical", "level": "easy"}, {"אסתר", "קהלת"}),
        ({"kind": "document"}, {"מגילת העצמאות", "הכרזת העצמאות של ארצות הברית"}),
    ],
)
def test_a_filter_narrows_to_what_it_says(
    tmp_path: Path, view: dict[str, str], expected: set[str]
) -> None:
    drawn = draw(tmp_path, view=view)
    assert {row["title"] for row in drawn["rows"]} == expected


def test_search_reaches_a_hebrew_title_through_its_english(tmp_path: Path) -> None:
    """The bug this harness was written to catch. Every title and byline in the catalogue
    is in Hebrew, so a reader typing "herzl" — or any Latin name — found nothing at all
    until the describing sentence and the entry's own id joined the haystack."""
    for typed, wanted in (("herzl", "תל־אביב"), ("mendele", "ספר הקבצנים")):
        titles = {row["title"] for row in draw(tmp_path, view={"find": typed})["rows"]}
        assert wanted in titles, f"searching {typed!r} should reach {wanted}"


def test_nothing_matching_says_so(tmp_path: Path) -> None:
    drawn = draw(tmp_path, view={"find": "אין כזה דבר"})
    assert drawn["rows"] == []
    assert drawn["empty"] == "Nothing here matches that."


def test_shortest_first_is_shortest_first(tmp_path: Path) -> None:
    from targum.catalogue import CATALOGUE

    drawn = draw(tmp_path, view={"sort": "minutes", "dir": 1})
    titles = [row["title"] for row in drawn["rows"]]

    minutes = {entry.title: entry.minutes for entry in CATALOGUE}
    assert minutes[titles[0]] <= minutes[titles[1]] <= minutes[titles[-1]]
    assert minutes[titles[0]] == min(
        entry.minutes for entry in CATALOGUE if entry.language.startswith("he")
    )


def test_the_catalogue_and_your_own_texts_are_two_lists(tmp_path: Path) -> None:
    """They were one list with a Public/Private word on every row and a filter called
    Access. They are two different questions — what is there to read, and what have I put
    here — so they are two tabs, and neither list has to say which it is on every row."""
    both = [shelf("psalms", "תהילים-he"), shelf("", "my-article-he")]

    catalogue = {row["title"] for row in draw(tmp_path, readers=both)["rows"]}
    assert "תהילים" in catalogue
    assert "my-article-he" not in catalogue, "an upload is not in the catalogue"

    mine = draw(tmp_path, readers=both, view={"where": "mine"})["rows"]
    assert {row["title"] for row in mine} == {"my-article-he"}


def test_a_text_you_have_opens_and_one_you_do_not_is_a_button(tmp_path: Path) -> None:
    """A link goes straight to the reader; a button is pressed, and pressing it spends."""
    drawn = draw(tmp_path, readers=[shelf("psalms", "תהילים-he")])
    rows = {row["title"]: row for row in drawn["rows"]}

    assert rows["תהילים"]["opens"] == "a"
    assert rows["איוב"]["opens"] == "button"


def test_an_empty_tab_says_which_kind_of_empty_it_is(tmp_path: Path) -> None:
    """ "Nothing here matches that" is what a filter says. A reader who has uploaded
    nothing has not filtered anything out."""
    drawn = draw(tmp_path, view={"where": "mine"})
    assert drawn["empty"] == "Nothing uploaded yet. Paste your own from Upload Text."

    filtered = draw(tmp_path, view={"find": "zzzzz"})
    assert filtered["empty"] == "Nothing here matches that."


def test_drawing_a_cover_is_offered_only_where_it_could_work(tmp_path: Path) -> None:
    """Three things have to hold: the server has a key, the text is on the shelf, and it
    has no cover yet. A page that offers what the server cannot do is worse than one that
    offers nothing."""
    on_shelf = [shelf("psalms", "תהילים-he")]

    assert draw(tmp_path, readers=on_shelf, covers=True)["rows"]
    offered = {
        row["title"]: row["draws"] for row in draw(tmp_path, readers=on_shelf, covers=True)["rows"]
    }
    assert offered["תהילים"] == "Draw cover"
    assert offered["איוב"] == "", "not on the shelf, so there is nothing to draw for"

    without = {
        row["title"]: row["draws"] for row in draw(tmp_path, readers=on_shelf, covers=False)["rows"]
    }
    assert without["תהילים"] == "", "no key on the server, so nothing is offered"

    drawn_already = [shelf("psalms", "תהילים-he", drawn=True)]
    already = {
        row["title"]: row["draws"]
        for row in draw(tmp_path, readers=drawn_already, covers=True)["rows"]
    }
    assert already["תהילים"] == "", "it already has one"


def test_the_list_opens_on_what_a_learner_can_read_now(tmp_path: Path) -> None:
    """The default sort used to be access, which ordered forty texts by who may read them
    — a fact about permission, not about whether this reader stands a chance. Somebody
    learning Hebrew is asking which of these they can read, so the list answers that
    first and the easiest one is at the top."""
    from targum.catalogue import CATALOGUE

    rows = draw(tmp_path)["rows"]
    shares = [int(row["cells"][3].rstrip("%")) for row in rows]
    assert shares == sorted(shares), "easiest first"

    # Zero is a measurement on a catalogue text — a twenty-word scene with no uncommon
    # word in it — so the easiest texts in the library read "0%" and come first, rather
    # than reading "—" and being anybody's guess.
    least = min(entry.difficulty for entry in CATALOGUE if entry.language.startswith("he"))
    assert shares[0] == least == 0
    assert all(row["cells"][3] == "0%" for row in rows if row["title"] in {"בבית קפה", "שני קפה"})


def test_the_hardest_column_says_what_it_counts(tmp_path: Path) -> None:
    """ "Looked up" is what the measurement is called. "New words" is what a reader
    choosing a text is asking about."""
    columns = draw(tmp_path)["columns"]
    # The sorted column carries its arrow, so this is a prefix rather than an equality.
    assert any(name.startswith("New words") for name in columns), columns
    assert not any(name.startswith("Looked up") for name in columns), columns


def test_only_the_kinds_that_are_actually_there_are_offered(tmp_path: Path) -> None:
    """Seven chips where three of them find nothing is seven things to try and four dead
    ends — and one of the dead ends was "Documents", which nobody browses by. What is
    offered is what the rest of the filters leave standing."""
    assert draw(tmp_path, view={"register": "biblical"})["kinds"] == [
        "All",
        "Bible narrative",
        "Poetry",
    ]
    modern = draw(tmp_path, view={"register": "modern"})["kinds"]
    assert "Bible narrative" not in modern and "Poetry" not in modern
    # Scenes first — where a reader with no words starts — then the biggest ones.
    assert modern[:4] == ["All", "Scenes", "Stories", "News"]


def test_a_kind_is_called_what_a_reader_would_call_it(tmp_path: Path) -> None:
    """ "Prose" is the catalogue's word for the narrative books of the Tanakh. Beside
    "Novels" and "Stories", which are also prose, it says nothing to anybody."""
    rows = draw(tmp_path)["rows"]
    genesis = next(row for row in rows if row["title"] == "בראשית")
    assert genesis["cells"][0] == "Bible narrative", "not bare Narrative beside Novels and Stories"
    assert "News" in {row["cells"][0] for row in rows}
    assert "Scenes" in {row["cells"][0] for row in rows}, "not Dialogues"
    assert "Prose" not in {row["cells"][0] for row in rows}
    assert "Articles" not in {row["cells"][0] for row in rows}


def test_choosing_a_kind_does_not_hide_the_other_kinds(tmp_path: Path) -> None:
    """The row of chips is computed with its own filter lifted. Without that, choosing
    Stories would leave "All" and "Stories" and no way back to anything else."""
    chosen = draw(tmp_path, view={"kind": "story"})["kinds"]
    assert "News" in chosen and "Novels" in chosen


def test_a_row_keeps_the_cell_a_build_narrates_itself_in(tmp_path: Path) -> None:
    """`build()` writes "Getting ready…", then "Lining up…", then the progress into a
    `.row-state` cell. When the Public/Private word moved out of the rows and into the
    two tabs, that cell went with it and pressing any unbuilt row threw on a null."""
    row = draw(tmp_path)["rows"][0]
    assert row["cells"][-1] == "", "empty until there is something to say"

    source = (ASSETS / "library.js").read_text(encoding="utf-8")
    assert 'el("span", "row-state")' in source
    assert 'open.querySelector(".row-state")' in source, "and the build still looks for it"


def test_being_sent_to_a_text_lifts_a_filter_that_would_hide_it(tmp_path: Path) -> None:
    """Learn links here with the id in the hash, and the filters are remembered between
    visits. A reader who last narrowed the catalogue to poetry and is then sent to a
    document arrived at the top of a list the suggestion was not in, with nothing on the
    page to say why. Being sent is a stronger claim than a filter set on an earlier visit.
    """
    from targum.catalogue import CATALOGUE

    wanted = next(
        entry
        for entry in CATALOGUE
        if entry.language.startswith("he") and entry.kind.value != "poetry"
    )

    hidden = draw(tmp_path, view={"kind": "poetry"})
    assert wanted.title not in {row["title"] for row in hidden["rows"]}, (
        "the filter has to hide it, or this proves nothing"
    )

    sent = draw(tmp_path, view={"kind": "poetry"}, hash="#" + wanted.id)
    assert wanted.title in {row["title"] for row in sent["rows"]}
    assert sent["pointed"] == [wanted.title]


def test_a_filter_still_holds_when_nobody_was_sent(tmp_path: Path) -> None:
    """The lift is for an arrival with a hash and nothing else: a reader who set a filter
    themselves and came back to it should find it where they left it."""
    drawn = draw(tmp_path, view={"kind": "poetry"})
    assert drawn["rows"], "poetry should match something"
    assert all(row["cells"][0] == "Poetry" for row in drawn["rows"])
    assert drawn["pointed"] == []


def test_a_text_on_the_shelf_says_how_much_of_it_is_yours(tmp_path: Path) -> None:
    """Plain words for a text you have no history against; your own share once you do.
    "Beginners cannot understand library listings" — a percentage of an abstract
    measurement is not something a beginner can act on."""
    drawn = draw(tmp_path, readers=[shelf("esther", "אסתר", known=0.82)])
    by_title = {row["title"]: row for row in drawn["rows"]}
    assert by_title["אסתר"]["fit"] == "you know 82% of its words"
    others = [row["fit"] for title, row in by_title.items() if title != "אסתר"]
    assert set(others) == {""}, "and nothing is claimed for a text never measured"

    # "You know 0% of its words" is true and unkind; the line starts once there is
    # something to say, exactly as Learn's does.
    nothing = draw(tmp_path, readers=[shelf("esther", "אסתר", known=0.0)])
    assert {row["title"]: row for row in nothing["rows"]}["אסתר"]["fit"] == ""


def vocabulary(*lemmas: str) -> dict[str, str]:
    """A store with those words marked known, the shape the reader writes."""
    kept = {lemma: {"surface": lemma, "status": 9, "band": "moderate", "at": 0} for lemma in lemmas}
    return {"targum:vocab:he": json.dumps(kept, ensure_ascii=False)}


def test_the_line_under_the_controls_says_what_the_active_one_means(tmp_path: Path) -> None:
    """The one sentence on the page written for a reader who cannot yet read a title.
    It used to live in tooltips, which is nowhere on a phone."""
    assert draw(tmp_path)["note"] == "New words — the share of a text that is uncommon Hebrew."
    assert draw(tmp_path, view={"kind": "dialogue"})["note"].startswith(
        "Scenes — numbered conversations with audio. Start at 1."
    )
    assert draw(tmp_path, view={"kind": "prose"})["note"].startswith("Bible narrative —")
    assert draw(tmp_path, view={"register": "biblical"})["note"].startswith(
        "Biblical — the Hebrew of the Bible."
    )
    assert draw(tmp_path, view={"spoken": "yes", "register": "modern"})["note"] == (
        "Modern — Hebrew as it is written today. · With audio — a recording, line by line."
    )
    # Never more than two clauses, kind before register before audio before the sort;
    # a kind with nothing to explain (Stories) takes no slot.
    three = draw(tmp_path, view={"kind": "story", "register": "modern", "spoken": "yes"})["note"]
    assert (
        three == "Modern — Hebrew as it is written today. · With audio — a recording, line by line."
    )
    four = draw(tmp_path, view={"kind": "prose", "register": "biblical", "spoken": "yes"})["note"]
    assert (
        four == "Bible narrative — the Bible's story books. · Biblical — the Hebrew of the Bible."
    )


def test_a_dash_is_explained_only_while_one_is_on_screen(tmp_path: Path) -> None:
    """Zero on a catalogue text is a measurement and reads 0%. An upload built without
    word-level annotation is not measured, reads "—", and the line says so — but only
    then."""
    plain = draw(tmp_path)
    assert "—" not in {row["cells"][3] for row in plain["rows"]}
    assert "not measured" not in plain["note"]

    unmeasured = draw(
        tmp_path, readers=[shelf("", "my-upload-he", difficulty=0)], view={"where": "mine"}
    )
    (row,) = unmeasured["rows"]
    assert row["cells"][3] == "—"
    assert unmeasured["note"].endswith("— means not measured yet.")


def test_the_gauge_stops_promising_what_is_new_to_you(tmp_path: Path) -> None:
    """The share is a fact about the text — how much of it is uncommon Hebrew. A reader
    who knows no words looks up all twenty-two of a text that says 0%, so "will be new
    to you" was a promise the number could not keep."""
    labels = draw(tmp_path)["gauges"]
    assert any("is uncommon" in label for label in labels)
    assert not any("new to you" in label for label in labels)


def test_a_first_visit_that_knows_nothing_opens_on_the_scenes(tmp_path: Path) -> None:
    """No view remembered, no word marked, nothing of their own: the list opens on the
    Scenes, in scene order, with the line that says to start at 1 above every control,
    and the share column says what order the list is in and cannot be pressed."""
    drawn = draw(tmp_path, firstVisit=True)
    assert drawn["kindOn"] == "Scenes"
    assert drawn["noteLeads"] is True
    assert drawn["note"].startswith("Scenes — numbered conversations with audio. Start at 1.")
    assert [row["title"] for row in drawn["rows"]] == [
        "נעים מאוד",
        "בבית קפה",
        "איפה הרחוב",
        "שני קפה",
    ]
    assert drawn["shareHead"] == {"text": "Scene number", "disabled": True}


def test_a_first_visit_with_words_or_texts_of_your_own_is_left_alone(tmp_path: Path) -> None:
    """The opening is for the reader who knows nothing. Anybody with a word marked or a
    text of their own has started already, and gets the list as it is."""
    with_words = draw(tmp_path, firstVisit=True, stored=vocabulary("שלום"))
    assert with_words["kindOn"] == "All"
    assert with_words["noteLeads"] is False

    with_texts = draw(tmp_path, firstVisit=True, readers=[shelf("", "my-upload-he")])
    assert with_texts["kindOn"] == "All"


def test_a_remembered_view_wins_over_the_opening(tmp_path: Path) -> None:
    """Once the reader has been here, their own choices stand — including having chosen
    nothing. The opening happens once, never on every visit with an empty store."""
    drawn = draw(tmp_path, view={})
    assert drawn["kindOn"] == "All"
    assert drawn["noteLeads"] is False
    assert drawn["shareHead"] == {"text": "New words ↑", "disabled": False}


def test_under_the_scenes_chip_the_list_is_in_scene_order(tmp_path: Path) -> None:
    """Their measured shares are noise at twenty words — scene 18 scores lower than
    scene 1 — and a numbered sequence has one order whatever column was last sorted."""
    drawn = draw(tmp_path, view={"kind": "dialogue", "sort": "difficulty", "dir": 1})
    assert [row["title"] for row in drawn["rows"]] == [
        "נעים מאוד",
        "בבית קפה",
        "איפה הרחוב",
        "שני קפה",
    ]
    by_minutes = draw(tmp_path, view={"kind": "dialogue", "sort": "minutes", "dir": -1})
    assert [row["title"] for row in by_minutes["rows"]] == [
        "נעים מאוד",
        "בבית קפה",
        "איפה הרחוב",
        "שני קפה",
    ]
    assert drawn["shareHead"]["text"] == "Scene number"


def test_every_catalogue_row_carries_its_title_in_english(tmp_path: Path) -> None:
    """Under the Hebrew, in ink, with the byline after it. For the reader who cannot yet
    read the line above, this is the title. An upload has none and shows none."""
    drawn = draw(tmp_path, readers=[shelf("", "my-upload-he")])
    by_title = {row["title"]: row for row in drawn["rows"]}
    assert by_title["רות"]["english"] == "Ruth · Ketuvim · Ruth" or by_title["רות"][
        "english"
    ].startswith("Ruth")
    assert by_title["נעים מאוד"]["english"].startswith("Nice to meet you")
    assert all(row["english"] for row in drawn["rows"]), "every catalogue row"

    mine = draw(tmp_path, readers=[shelf("", "my-upload-he")], view={"where": "mine"})["rows"]
    assert mine[0]["english"] == ""


def test_search_reaches_a_text_through_its_english_title(tmp_path: Path) -> None:
    titles = {row["title"] for row in draw(tmp_path, view={"find": "meet"})["rows"]}
    assert "נעים מאוד" in titles


def test_sorting_by_title_sorts_by_the_english_where_there_is_one(tmp_path: Path) -> None:
    """For the reader this page is sorted for, the Hebrew titles are not yet in an order."""
    drawn = draw(tmp_path, view={"sort": "title", "dir": 1, "kind": "dialogue"})
    # Under Scenes the order is scene number (see above); sort by title on the catalogue:
    drawn = draw(tmp_path, view={"sort": "title", "dir": 1})
    english = [row["english"].split(" · ")[0] for row in drawn["rows"]]
    assert english == sorted(english, key=str.lower)
