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
    """The page as a reader gets it, drawn as the **table**.

    The library is browsed as cards since 2026-09-17 (design.md §12) and the table is one
    press away. Almost everything asserted here is about a column — the kind, the
    register, the length, the two shares — and a column is a thing only the table has, so
    these ask for the table by name rather than testing a shape the page no longer opens
    in. What the cards draw is asserted by `browse()`, and which of the two a reader gets
    is asserted on its own.

    A first visit is the exception: there is no remembered view to carry the shape, which
    is the whole meaning of `firstVisit`, so those tests get the cards and say so.
    """
    from targum.catalogue import CATALOGUE, collections

    if not payload.get("firstVisit"):
        views = payload.setdefault("views", {}) if "views" in payload else None
        if views is not None:
            for one in views.values():
                one.setdefault("shape", "list")
        else:
            payload.setdefault("view", {}).setdefault("shape", "list")
    payload.setdefault("catalogue", [entry.state() for entry in CATALOGUE])
    # The real collections, for the same reason the catalogue is real: a fixture of them
    # would be a second copy of the thing under test.
    payload.setdefault("collections", [group.state() for group in collections()])
    payload.setdefault("readers", [])
    # Most of these tests are about what a row shows, not about which rows are folded
    # away. `unfolded` opens every collection, so each text is a row again and the
    # assertion is the one it always was.
    if payload.pop("unfolded", False):
        payload["opened"] = {group["id"]: True for group in payload["collections"]}
    where = tmp_path / "payload.json"
    where.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    done = subprocess.run(
        ["node", str(HARNESS), str(where)], capture_output=True, text=True, timeout=60
    )
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def test_every_hebrew_text_is_counted_whether_or_not_it_has_a_row(tmp_path: Path) -> None:
    """The tally counts texts; the list draws rows, and a collection is one row over many.

    It used to be able to assert both with one number. Once the shelf folded, "36 of 352"
    would have been counting two different things in one sentence and both of them true.
    """
    from targum.catalogue import CATALOGUE

    drawn = draw(tmp_path)

    hebrew = [entry for entry in CATALOGUE if entry.language.startswith("he")]
    assert drawn["tally"] == f"{len(hebrew)} texts"
    assert len(drawn["rows"]) < len(hebrew), "the shelf is folded"
    assert drawn["columns"][:2] == ["Text", "Kind"]


def test_the_page_says_its_words_in_the_readers_language(tmp_path: Path) -> None:
    """A Russian reader's library says Russian, down to the plural the count takes, and
    a word the catalogue has not filled is said in English rather than as its key
    (targum-internal#184)."""
    from targum.catalogue import CATALOGUE

    hebrew = len([entry for entry in CATALOGUE if entry.language.startswith("he")])
    drawn = draw(
        tmp_path,
        strings={
            "language": "ru",
            "strings": {
                "library.column.title": "Текст",
                "library.tally.all.one": "{n} текст",
                "library.tally.all.few": "{n} текста",
                "library.tally.all.many": "{n} текстов",
                "library.tally.all.other": "{n} текста",
            },
        },
    )
    assert drawn["columns"][:2] == ["Текст", "Kind"]
    form = {"one": "текст", "few": "текста", "many": "текстов", "other": "текста"}
    last, tens = hebrew % 10, hebrew % 100
    rule = (
        "one"
        if last == 1 and tens != 11
        else "few"
        if 2 <= last <= 4 and not 12 <= tens <= 14
        else "many"
    )
    assert drawn["tally"] == f"{hebrew} {form[rule]}"


# -- collections --------------------------------------------------------------


def test_a_collection_is_one_row_until_it_is_opened(tmp_path: Path) -> None:
    """The reason any of this exists: thirteen rows of `הלכות …` is not a shelf a reader
    can see past, and the Mishnah would be sixty-three of them."""
    shut = draw(tmp_path)
    folded = next(row for row in shut["rows"] if row["group"] == "tanakh")
    assert folded["title"] == "תנ״ך"
    assert folded["after"] == " · 6 texts"
    assert folded["expanded"] == "false"
    assert not any(row["title"] == "רות" for row in shut["rows"])

    open_ = draw(tmp_path, opened={"tanakh": True})
    assert next(row for row in open_["rows"] if row["group"] == "tanakh")["expanded"] == "true"
    inside = [row for row in open_["rows"] if row["member"]]
    assert {"רות", "אסתר"} <= {row["title"] for row in inside}


def test_an_ordered_collection_keeps_its_own_order(tmp_path: Path) -> None:
    """A work read front to back does not rearrange itself under a column sort:
    Deuteronomy above Genesis because it measures easier is not a Torah."""
    for direction in (1, -1):
        drawn = draw(
            tmp_path,
            view={"sort": "minutes", "dir": direction},
            opened={"tanakh": True},
        )
        inside = [row["title"] for row in drawn["rows"] if row["member"]]
        assert inside == ["בראשית", "רות", "אסתר", "קהלת", "איוב", "תהילים"]


def test_the_portions_keep_the_order_of_the_year_under_every_sort(tmp_path: Path) -> None:
    """Fifty-four rows in one ordered collection, בראשית to וזאת הברכה whatever column
    the page is sorted on — and a title sort would otherwise put פרשה 10 before פרשה 2
    (targum-internal #145)."""
    ids = [f"parasha-p{n:02d}" for n in range(1, 55)]
    titles = [f"פרשה {n}" for n in range(1, 55)]
    catalogue = [
        {
            "id": entry_id,
            "title": title,
            "english": entry_id,
            "author": "בראשית",
            "language": "he",
            "source": f"sefaria:{entry_id}",
            "blurb": "",
            "words": 0,
            "minutes": (n * 13) % 40,
            "kind": "prose",
            "register": "biblical",
            "difficulty": (n * 7) % 50,
            "spoken": False,
            "tags": ["tanakh"],
            "translations": [],
        }
        for n, (entry_id, title) in enumerate(zip(ids, titles, strict=True), start=1)
    ]
    # A text outside the collection, because a list that is *only* one collection is
    # drawn as that collection — and the real shelf has four hundred others.
    catalogue.append({**catalogue[0], "id": "ruth", "title": "רות", "english": "Ruth"})
    group = {
        "id": "torah-portions",
        "title": "פרשות השבוע",
        "english": "The Torah, by portion",
        "blurb": "",
        "members": ids,
        "ordered": True,
    }
    for sort in ("title", "minutes", "difficulty"):
        for direction in (1, -1):
            drawn = draw(
                tmp_path,
                catalogue=catalogue,
                collections=[group],
                view={"sort": sort, "dir": direction},
                opened={"torah-portions": True},
            )
            inside = [row["title"] for row in drawn["rows"] if row["member"]]
            assert inside == titles, (sort, direction)
    shut = draw(tmp_path, catalogue=catalogue, collections=[group])
    assert [row["title"] for row in shut["rows"]] == ["רות", "פרשות השבוע"], (
        "one row, not fifty-four"
    )


def test_an_author_shelf_takes_the_readers_sort(tmp_path: Path) -> None:
    """The order a shelf of stories is in is the order somebody typed them in, and the
    reader's own question is the better one."""
    down = draw(tmp_path, view={"sort": "minutes", "dir": -1}, opened={"by-herzl": True})
    up = draw(tmp_path, view={"sort": "minutes", "dir": 1}, opened={"by-herzl": True})
    longest = [row["title"] for row in down["rows"] if row["member"]]
    shortest = [row["title"] for row in up["rows"] if row["member"]]
    assert longest == list(reversed(shortest))
    assert longest[0] == "תל־אביב", "sixty thousand words against twenty-five"


def test_a_list_that_is_one_collection_is_that_collection(tmp_path: Path) -> None:
    """Picking the Scenes chip and being shown a single row saying "Scenes · 100 texts"
    is the filter answering a question with the question."""
    drawn = draw(tmp_path, view={"kind": "dialogue"})
    assert not any(row["group"] for row in drawn["rows"])
    assert len(drawn["rows"]) == 4


def test_a_search_opens_what_it_found(tmp_path: Path) -> None:
    """A reader who types a title and is shown one shut row has been told it failed."""
    drawn = draw(tmp_path, view={"find": "אסתר"})
    assert [row["title"] for row in drawn["rows"]] == ["אסתר"]


def test_a_search_reaches_a_text_through_the_work_it_is_part_of(tmp_path: Path) -> None:
    """ "The Hebrew Bible" appears in none of its books."""
    titles = {row["title"] for row in draw(tmp_path, view={"find": "hebrew bible"})["rows"]}
    assert "רות" in titles


def test_being_sent_to_a_text_opens_the_collection_holding_it(tmp_path: Path) -> None:
    """Opening one shelf is a smaller thing to do to a reader's page than lifting every
    filter they set, so it is tried first."""
    drawn = draw(tmp_path, hash="#ruth")
    assert drawn["pointed"] == ["רות"]


def test_a_collection_carries_what_its_texts_agree_on(tmp_path: Path) -> None:
    drawn = draw(tmp_path)
    tanakh = next(row for row in drawn["rows"] if row["group"] == "tanakh")
    assert tanakh["cells"][0] == "", "narrative and poetry agree about nothing"
    assert tanakh["cells"][1] == "Biblical"
    herzl = next(row for row in drawn["rows"] if row["group"] == "by-herzl")
    assert herzl["cells"][1] == "Revival"


def test_a_collection_is_as_long_as_its_texts_together(tmp_path: Path) -> None:
    """A row that says how much there is, so a reader can tell a shelf from a text."""
    drawn = draw(tmp_path)
    herzl = next(row for row in drawn["rows"] if row["group"] == "by-herzl")
    assert herzl["cells"][2].endswith("hr"), "eighty-five thousand words is not minutes"


def test_a_row_carries_what_the_filters_sort_on(tmp_path: Path) -> None:
    """Whatever a row shows has to be the same vocabulary the catalogue is written in,
    or the filters and the rows are describing different things."""
    row = next(r for r in draw(tmp_path, unfolded=True)["rows"] if r["title"] == "תהילים")

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

    drawn = draw(tmp_path, view={"sort": "minutes", "dir": 1}, unfolded=True)
    titles = [row["title"] for row in drawn["rows"]]

    minutes = {entry.title: entry.minutes for entry in CATALOGUE}
    # Texts only, and only the ones the sort acts on: a collection is a row too, its
    # length is its members' added up, and inside it they keep their own order.
    titles = [row["title"] for row in drawn["rows"] if not row["group"] and not row["member"]]
    lengths = [minutes[title] for title in titles]
    assert lengths == sorted(lengths), "shortest first"
    # The shortest text in the catalogue is a twenty-word scene, and the scenes are one
    # row now. What leads the list is the shortest *row*, which may be a whole shelf.
    shortest = min(
        (entry for entry in CATALOGUE if entry.language.startswith("he")),
        key=lambda entry: entry.minutes,
    )
    assert shortest.title not in titles, "it is inside a collection"


def test_the_catalogue_and_your_own_texts_are_two_lists(tmp_path: Path) -> None:
    """They were one list with a Public/Private word on every row and a filter called
    Access. They are two different questions — what is there to read, and what have I put
    here — so they are two tabs, and neither list has to say which it is on every row."""
    both = [shelf("psalms", "תהילים-he"), shelf("", "my-article-he")]

    catalogue = {row["title"] for row in draw(tmp_path, readers=both, unfolded=True)["rows"]}
    assert "תהילים" in catalogue
    assert "my-article-he" not in catalogue, "an upload is not in the catalogue"

    mine = draw(tmp_path, readers=both, view={"where": "mine"}, unfolded=True)["rows"]
    assert {row["title"] for row in mine} == {"my-article-he"}


def test_a_text_you_have_opens_and_one_you_do_not_is_a_button(tmp_path: Path) -> None:
    """A link goes straight to the reader; a button is pressed, and pressing it spends."""
    drawn = draw(tmp_path, readers=[shelf("psalms", "תהילים-he")], unfolded=True)
    rows = {row["title"]: row for row in drawn["rows"]}

    assert rows["תהילים"]["opens"] == "a"
    assert rows["איוב"]["opens"] == "button"


def test_an_empty_tab_says_which_kind_of_empty_it_is(tmp_path: Path) -> None:
    """ "Nothing here matches that" is what a filter says. A reader who has uploaded
    nothing has not filtered anything out."""
    drawn = draw(tmp_path, view={"where": "mine"})
    assert drawn["empty"] == "You haven't added anything yet. Use Add to bring your own."

    filtered = draw(tmp_path, view={"find": "zzzzz"})
    assert filtered["empty"] == "Nothing here matches that."


def test_drawing_a_cover_is_offered_only_where_it_could_work(tmp_path: Path) -> None:
    """Three things have to hold: the server has a key, the text is on the shelf, and it
    has no cover yet. A page that offers what the server cannot do is worse than one that
    offers nothing."""
    on_shelf = [shelf("psalms", "תהילים-he")]

    assert draw(tmp_path, readers=on_shelf, covers=True, unfolded=True)["rows"]
    offered = {
        row["title"]: row["draws"]
        for row in draw(tmp_path, readers=on_shelf, covers=True, unfolded=True)["rows"]
    }
    assert offered["תהילים"] == "Draw cover"
    assert offered["איוב"] == "", "not on the shelf, so there is nothing to draw for"

    without = {
        row["title"]: row["draws"]
        for row in draw(tmp_path, readers=on_shelf, covers=False, unfolded=True)["rows"]
    }
    assert without["תהילים"] == "", "no key on the server, so nothing is offered"

    drawn_already = [shelf("psalms", "תהילים-he", drawn=True)]
    already = {
        row["title"]: row["draws"]
        for row in draw(tmp_path, readers=drawn_already, covers=True, unfolded=True)["rows"]
    }
    assert already["תהילים"] == "", "it already has one"


def test_the_list_opens_on_what_a_learner_can_read_now(tmp_path: Path) -> None:
    """The default sort used to be access, which ordered forty texts by who may read them
    — a fact about permission, not about whether this reader stands a chance. Somebody
    learning Hebrew is asking which of these they can read, so the list answers that
    first and the easiest one is at the top."""
    from targum.catalogue import CATALOGUE

    rows = draw(tmp_path, unfolded=True)["rows"]
    # The rows the sort actually acts on. A collection's members follow their own order
    # inside it, so the list as drawn interleaves two orders — see `within()`.
    shares = [int(row["cells"][3].rstrip("%")) for row in rows if not row["member"]]
    assert shares == sorted(shares), "easiest first"

    # Zero is a measurement on a catalogue text — a twenty-word scene with no uncommon
    # word in it — so the easiest texts in the library read "0%" rather than reading "—"
    # and being anybody's guess. They no longer lead the list: they are scenes, the scenes
    # are one row, and a collection's share is the middle of its own texts.
    assert min(entry.difficulty for entry in CATALOGUE if entry.language.startswith("he")) == 0
    assert all(row["cells"][3] == "0%" for row in rows if row["title"] in {"בבית קפה", "שני קפה"})


def test_the_hardest_column_says_what_it_counts(tmp_path: Path) -> None:
    """ "Looked up" is what the measurement is called. "Hard words" is what the number
    counts: words rare in the language, not words new to this reader (2026-09-14)."""
    columns = draw(tmp_path)["columns"]
    # The sorted column carries its arrow, so this is a prefix rather than an equality.
    assert any(name.startswith("Hard words") for name in columns), columns
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
    rows = draw(tmp_path, unfolded=True)["rows"]
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
    """`build()` writes "We're getting it ready…", then "We're lining it up…", then the
    progress into a `.row-state` cell. When the Public/Private word moved out of the rows
    and into the two tabs, that cell went with it and pressing any unbuilt row threw on a
    null."""
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
    drawn = draw(tmp_path, readers=[shelf("esther", "אסתר", known=0.82)], unfolded=True)
    by_title = {row["title"]: row for row in drawn["rows"]}
    assert by_title["אסתר"]["fit"] == "you know 82% of its words"
    others = [row["fit"] for title, row in by_title.items() if title != "אסתר"]
    assert set(others) == {""}, "and nothing is claimed for a text never measured"

    # "You know 0% of its words" is true and unkind; the line starts once there is
    # something to say, exactly as Learn's does.
    nothing = draw(tmp_path, readers=[shelf("esther", "אסתר", known=0.0)], unfolded=True)
    assert {row["title"]: row for row in nothing["rows"]}["אסתר"]["fit"] == ""


def vocabulary(*lemmas: str) -> dict[str, str]:
    """A store with those words marked known, the shape the reader writes."""
    kept = {lemma: {"surface": lemma, "status": 9, "band": "moderate", "at": 0} for lemma in lemmas}
    return {"targum:vocab:he": json.dumps(kept, ensure_ascii=False)}


def test_the_line_under_the_controls_says_what_the_active_one_means(tmp_path: Path) -> None:
    """The one sentence on the page written for a reader who cannot yet read a title.
    It used to live in tooltips, which is nowhere on a phone."""
    assert (
        draw(tmp_path)["note"]
        == "Hard words — the share of a text's words that are rare in everyday use."
    )
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
    assert unmeasured["note"].endswith("— means we haven't measured it yet.")


def test_the_gauge_stops_promising_what_is_new_to_you(tmp_path: Path) -> None:
    """The share is a fact about the text — how much of its vocabulary is hard, in the
    word the reader page puts on a tapped word. A reader who knows no words looks up all
    twenty-two of a text that says 0%, so "will be new to you" was a promise the number
    could not keep."""
    labels = draw(tmp_path)["gauges"]
    assert any("is hard" in label for label in labels)
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
    assert drawn["shareHead"] == {"text": "Hard words ↑", "disabled": False}


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
    drawn = draw(tmp_path, readers=[shelf("", "my-upload-he")], unfolded=True)
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


# --- the scenes as a path, in the list ----------------------------------------------


def seeded(entry_id: str, title: str, **extra: Any) -> dict[str, Any]:
    row = shelf(entry_id, title + "-he", shared=True, document=entry_id + "-h", **extra)
    row["title"] = title
    return row


SCENES = [
    seeded("scene-01-nice-to-meet-you", "נעים מאוד", kind="dialogue", difficulty=5),
    seeded("scene-02-in-a-cafe", "בבית קפה", kind="dialogue", difficulty=0),
    seeded("scene-03-which-way", "איפה הרחוב", kind="dialogue", difficulty=2),
    seeded("scene-18-two-coffees", "שני קפה", kind="dialogue", difficulty=0),
]


def test_a_shared_text_opens_and_offers_nothing_else(tmp_path: Path) -> None:
    """Seeded rows used to be invisible to this page, so a scene showed as an unbuilt
    button and pressing it built a personal copy. Now it opens, and nothing on it can be
    drawn, bought or trashed."""
    drawn = draw(tmp_path, shared=SCENES, covers=True, view={"kind": "dialogue"})
    rows = {row["title"]: row for row in drawn["rows"]}
    assert rows["נעים מאוד"]["opens"] == "a"
    assert rows["נעים מאוד"]["draws"] == "", "no cover drawn for what is not theirs"
    assert rows["נעים מאוד"]["scene"] == "Scene 1"
    assert [row["scene"] for row in drawn["rows"]] == ["Scene 1", "Scene 2", "Scene 3", "Scene 18"]


def test_the_next_scene_is_chipped_start_here_then_next(tmp_path: Path) -> None:
    drawn = draw(tmp_path, shared=SCENES, view={"kind": "dialogue"})
    assert [row["chip"] for row in drawn["rows"]] == ["Start here", "", "", ""]

    done = {"targum:docs": json.dumps({"scene-01-nice-to-meet-you-h": {"done": 9}})}
    later = draw(tmp_path, shared=SCENES, view={"kind": "dialogue"}, stored=done)
    assert [row["chip"] for row in later["rows"]] == ["", "Next", "", ""]
    assert [row["state"] for row in later["rows"]] == ["finished", "", "", ""]


def test_a_finished_text_says_so_in_its_state_column(tmp_path: Path) -> None:
    done = {"targum:docs": json.dumps({"h": {"done": 9}})}
    drawn = draw(tmp_path, readers=[shelf("esther", "אסתר")], stored=done, unfolded=True)
    rows = {row["title"]: row for row in drawn["rows"]}
    assert rows["אסתר"]["state"] == "finished"
    assert rows["רות"]["state"] == ""


def test_your_own_copy_wins_over_the_shared_one(tmp_path: Path) -> None:
    own = shelf("scene-01-nice-to-meet-you", "mine-he", known=0.5)
    drawn = draw(tmp_path, readers=[own], shared=SCENES, view={"kind": "dialogue"}, covers=True)
    first = drawn["rows"][0]
    assert first["fit"] == "you know 50% of its words"
    assert first["draws"] == "Draw cover", "theirs, so a cover can be drawn"


def test_a_video_import_is_told_apart_from_an_audio_one(tmp_path: Path) -> None:
    """A lecture with its slides and a podcast episode were the same row. One word
    beside the title now says which — and only one word, since a video can be
    listened to as well and "audio video" says less than "video" does."""
    mine = [
        shelf("", "lecture-he", spoken=True, video=True),
        shelf("", "podcast-he", spoken=True),
        shelf("", "essay-he"),
    ]
    rows = {
        row["title"]: row["media"]
        for row in draw(tmp_path, readers=mine, view={"where": "mine"})["rows"]
    }
    assert rows == {"lecture-he": "Video", "podcast-he": "Audio", "essay-he": ""}


def test_with_video_finds_the_video_and_with_audio_still_finds_both(tmp_path: Path) -> None:
    """One direction each, like the audio filter: "With video" is worth offering,
    "without video" is not — and a video is still something to listen to."""
    mine = [
        shelf("", "lecture-he", spoken=True, video=True),
        shelf("", "podcast-he", spoken=True),
        shelf("", "essay-he"),
    ]
    videos = draw(tmp_path, readers=mine, view={"where": "mine", "spoken": "video"})
    assert {row["title"] for row in videos["rows"]} == {"lecture-he"}
    assert videos["note"].startswith("With video — ")
    heard = draw(tmp_path, readers=mine, view={"where": "mine", "spoken": "yes"})
    assert {row["title"] for row in heard["rows"]} == {"lecture-he", "podcast-he"}


# -- a view per language ---------------------------------------------------------------


def test_filters_set_on_one_language_stay_with_it(tmp_path: Path) -> None:
    """David, 2026-09-14: "If you set filters for one language in the library, those
    filters should not remain in another." Poetry and a search typed on the Hebrew shelf
    are a question about Hebrew texts; switching to Russian opens Russian's own view, and
    switching back finds Hebrew's where it was left."""
    russian = shelf("", "otets-sergiy-ru", language="ru", languages=["ru"], kind="story")
    hebrew = {"kind": "poetry", "find": "שיר", "level": "easy"}

    there = draw(tmp_path, readers=[russian], view=hebrew, switchTo="ru")
    assert there["kindOn"] != "Poetry", "the Hebrew chip did not follow"
    assert there["find"] == ""
    # And the Hebrew view is still in the store under its own language.
    assert there["views"]["he"]["kind"] == "poetry"
    assert there["views"]["he"]["find"] == "שיר"
    assert there["views"]["ru"]["kind"] == ""

    views = {"he": {"kind": "poetry"}, "ru": {"kind": "story", "find": "сергий"}}
    back = draw(tmp_path, readers=[russian], views=views, language="ru", switchTo="he")
    assert back["kindOn"] == "Poetry"
    assert back["find"] == ""
    searched = {"he": {"find": "שיר"}, "ru": {}}
    assert (
        draw(tmp_path, readers=[russian], views=searched, language="ru", switchTo="he")["find"]
        == "שיר"
    )


def test_a_view_from_before_languages_had_their_own_is_hebrews(tmp_path: Path) -> None:
    """A store written before 2026-09-14 is one flat view. It was set on the Hebrew shelf,
    which is where it stays; Russian starts clean."""
    russian = shelf("", "otets-sergiy-ru", language="ru", languages=["ru"], kind="story")
    kept = draw(tmp_path, readers=[russian], view={"kind": "poetry"})
    assert kept["kindOn"] == "Poetry"
    assert set(kept["views"]) == {"he"}

    moved = draw(tmp_path, readers=[russian], view={"kind": "poetry"}, language="ru")
    assert moved["kindOn"] != "Poetry"
    assert moved["views"]["ru"]["kind"] == ""
    assert moved["views"]["he"]["kind"] == "poetry"


def test_the_aramaic_shelf_is_aramaic_texts_and_not_the_hebrew_torah(tmp_path: Path) -> None:
    """David, 2026-09-14: "why is it I just see hebrew tanakh in the aramaic library?" A
    Torah book with Onkelos as a column was filed under Aramaic. Under Aramaic the shelf is
    the targums, and Daniel for its Aramaic chapters; Genesis is Hebrew's."""
    from targum.catalogue import Entry, Kind, Register, Rendering

    def entry(id_: str, title: str, language: str, source: str, *renderings: str) -> Entry:
        return Entry(
            id=id_,
            title=title,
            author="",
            language=language,
            source=source,
            blurb="",
            english=title,
            words=1000,
            tags=frozenset(),
            translations=[Rendering(name="r", source=one) for one in renderings],
            kind=Kind.prose,
            register=Register.biblical if language == "he" else Register.none,
        )

    shelf_ = [
        entry(
            "genesis",
            "בראשית",
            "he",
            "sefaria:Genesis",
            "sefaria:en:Genesis",
            "sefaria:arc:Genesis",
        ),
        entry("daniel", "דניאל", "he", "sefaria:Daniel", "sefaria:en:Daniel"),
        entry("onkelos-genesis", "תרגום אונקלוס על בראשית", "arc", "sefaria:arc:Genesis"),
        entry(
            "targum-jonathan-jonah",
            "תרגום יונתן על יונה",
            "arc",
            "sefaria:arc:Targum Jonathan on Jonah",
            "sefaria:en:Targum Jonathan on Jonah",
        ),
    ]
    catalogue = [one.state() for one in shelf_]
    titles = {
        row["title"]
        for row in draw(tmp_path, catalogue=catalogue, collections=[], language="arc")["rows"]
    }
    assert titles == {"תרגום אונקלוס על בראשית", "תרגום יונתן על יונה", "דניאל"}
    hebrew = {row["title"] for row in draw(tmp_path, catalogue=catalogue, collections=[])["rows"]}
    assert hebrew == {"בראשית", "דניאל"}


# --- a title in the reader's own language (targum-internal#289) --------------------


def test_a_russian_reader_sees_a_russian_title_where_the_catalogue_has_one(
    tmp_path: Path,
) -> None:
    """The front door sells in Russian and the shelf behind it was entirely English."""
    entry = {
        "id": "ruth",
        "title": "רות",
        "english": "Ruth",
        "named": {"ru": "Руфь"},
        "author": "",
        "language": "he",
        "source": "sefaria:he:Ruth",
        "blurb": "A short book.",
        "blurbs": {"ru": "Короткая книга."},
        "words": 100,
        "minutes": 4,
        "kind": "prose",
        "register": "biblical",
        "difficulty": 20,
    }
    russian = draw(
        tmp_path,
        catalogue=[entry],
        collections=[],
        strings={"language": "ru", "strings": {}},
    )
    row = next(r for r in russian["rows"] if r["title"] == "רות")
    assert row["english"].startswith("Руфь")
    assert row["englishLang"] == "ru", "the cell claimed to be English"


def test_english_is_the_fallback_and_is_never_wrong_only_foreign(tmp_path: Path) -> None:
    """A row the catalogue has not drafted yet shows what it always showed."""
    entry = {
        "id": "ruth",
        "title": "רות",
        "english": "Ruth",
        "author": "",
        "language": "he",
        "source": "sefaria:he:Ruth",
        "blurb": "A short book.",
        "words": 100,
        "minutes": 4,
        "kind": "prose",
        "register": "biblical",
        "difficulty": 20,
    }
    russian = draw(
        tmp_path, catalogue=[entry], collections=[], strings={"language": "ru", "strings": {}}
    )
    row = next(r for r in russian["rows"] if r["title"] == "רות")
    assert row["english"].startswith("Ruth")
    assert row["englishLang"] == "en"


def test_an_english_reader_is_unaffected(tmp_path: Path) -> None:
    entry = {
        "id": "ruth",
        "title": "רות",
        "english": "Ruth",
        "named": {"ru": "Руфь"},
        "author": "",
        "language": "he",
        "source": "sefaria:he:Ruth",
        "blurb": "A short book.",
        "words": 100,
        "minutes": 4,
        "kind": "prose",
        "register": "biblical",
        "difficulty": 20,
    }
    drawn = draw(tmp_path, catalogue=[entry], collections=[])
    row = next(r for r in drawn["rows"] if r["title"] == "רות")
    assert row["english"].startswith("Ruth")
    assert row["englishLang"] == "en"


# --- the library is browsed (design.md §12, 2026-09-17) -----------------------------
#
# `draw()` above asks for the table, because almost everything it asserts is a column.
# These are about the shape a reader actually gets, and about the two controls the browse
# view is steered by: what a text is about, and how much of the library is in reach.
#
# They bring their own catalogue. The fixture is twenty-two texts with one subject among
# them, which cannot exercise a row of subject chips at all — and a test that leaned on
# the private catalogue instead would pass here and fail in CI, which has none.


def text(entry_id: str, title: str, **extra: Any) -> dict[str, Any]:
    """One catalogue entry, as the page receives it."""
    row = {
        "id": entry_id,
        "title": title,
        "english": entry_id.replace("-", " ").title(),
        "author": "",
        "language": "he",
        "source": f"wikisource:{entry_id}",
        "blurb": "",
        "words": 900,
        "minutes": 7,
        "kind": "story",
        "register": "modern",
        "difficulty": 18,
        "tags": [],
    }
    row.update(extra)
    return row


#: A shelf with enough shape to browse: three subjects, one text under two of them, and
#: a third of it filed under nothing — which is the catalogue's real proportion.
SHELF = [
    text("news-one", "ידיעה", kind="article", tags=["journalism"]),
    text("news-two", "ידיעה שנייה", kind="article", tags=["journalism"]),
    text("match", "משחק", kind="article", tags=["journalism", "sport"]),
    text("league", "ליגה", kind="article", tags=["sport"]),
    text("physics", "פיזיקה", kind="talk", tags=["science"], spoken=True, video=True),
    text("chemistry", "כימיה", kind="talk", tags=["science"], spoken=True),
    text("story-one", "סיפור"),
    text("story-two", "סיפור שני"),
    text("story-three", "סיפור שלישי"),
    text("story-four", "סיפור רביעי"),
]


def browse(tmp_path: Path, **payload: Any) -> dict[str, Any]:
    """The page as a reader gets it: cards, which is what it opens in."""
    view = dict(payload.pop("view", {}))
    view["shape"] = "cards"
    payload.setdefault("catalogue", SHELF)
    payload.setdefault("collections", [])
    return draw(tmp_path, view=view, **payload)


def test_the_library_opens_as_cards_and_the_table_is_one_press_away(tmp_path: Path) -> None:
    """A card cannot be sorted, which is what retired the last card grid and was fair.
    The sortable thing is kept rather than argued with."""
    fresh = draw(tmp_path, firstVisit=True)
    assert fresh["shape"] == "cards", "a reader who has chosen nothing browses"
    assert fresh["shapeOn"] == "Cards"

    listed = draw(tmp_path, view={"shape": "list"})
    assert listed["shape"] == "list"
    assert listed["shapeOn"] == "List"
    assert listed["columns"][:2] == ["Text", "Kind"], "the table keeps its columns"


def test_only_the_subjects_with_texts_behind_them_are_offered(tmp_path: Path) -> None:
    """`Tag` runs well past what is filed, on purpose: the arrival draws a door before
    anything is tagged into it. On this page that same door is a dead end."""
    from targum.catalogue import Tag

    offered = browse(tmp_path)["subjects"]
    assert offered == ["All", "News", "Sport", "Science"], offered
    assert len(offered) - 1 < len(list(Tag)), "not the whole vocabulary"


def test_a_shelf_with_one_subject_offers_none(tmp_path: Path) -> None:
    """ "All" and one word is not a choice — the rule the kinds already follow."""
    only = [row for row in SHELF if row["tags"] in ([], ["journalism"])]
    assert browse(tmp_path, catalogue=only)["subjects"] == []


def test_a_subject_chip_carries_its_count(tmp_path: Path) -> None:
    """Tanakh and Judaica are the two biggest Hebrew subjects. A bare row of names tells a
    modern-Hebrew learner this is a religious library; the numbers tell them what is
    really there."""
    drawn = browse(tmp_path)
    assert drawn["subjectCounts"] == [10, 3, 2, 2], drawn["subjectCounts"]
    assert drawn["subjectCounts"][0] == len(SHELF), "All is every text on the shelf"


def test_a_subject_narrows_and_the_other_subjects_stay(tmp_path: Path) -> None:
    """The row is computed with its own filter lifted, the way the kinds already are.
    Without it, choosing News would leave All and News and no way back."""
    everything = browse(tmp_path)
    news = browse(tmp_path, view={"subject": "journalism"})
    assert news["subjectOn"] == "News"
    assert news["subjects"] == everything["subjects"], "no subject disappears"
    assert {row["title"] for row in news["rows"]} == {"ידיעה", "ידיעה שנייה", "משחק"}


def test_a_text_under_two_subjects_is_found_under_both(tmp_path: Path) -> None:
    """A match report is journalism and sport at once. Tags are a list, not a value."""
    for subject in ("journalism", "sport"):
        titles = {row["title"] for row in browse(tmp_path, view={"subject": subject})["rows"]}
        assert "משחק" in titles, f"the match belongs under {subject}"


def test_a_text_filed_under_nothing_is_still_on_the_shelf(tmp_path: Path) -> None:
    """Nearly half the Hebrew shelf carries no subject at all. Subject as the page's one
    division would hide them; as a filter over everything it does not."""
    titles = {row["title"] for row in browse(tmp_path)["rows"]}
    assert "סיפור" in titles


def test_a_stranger_is_shown_everything_rather_than_a_guess(tmp_path: Path) -> None:
    """The fallback measure is the text's own hard-word share, which is a fact about the
    text and not about the reader. A page greeting somebody it knows nothing about with
    "showing the 358 you can read now" would be making a claim it cannot support."""
    drawn = browse(tmp_path, readers=[])
    assert drawn["fitOn"] == "everything"
    assert drawn["said"].startswith(f"{len(SHELF)} texts")
    assert len(drawn["rows"]) == len(SHELF)


def test_a_reader_with_a_vocabulary_opens_on_what_they_can_read(tmp_path: Path) -> None:
    """ "I want to be able to immediately choose a reading AT MY LEVEL" — answered by the
    list already being there, not by a control that could be found."""
    known = {row["id"]: {"known": 0.9} for row in SHELF[:7]}
    known.update({row["id"]: {"known": 0.3} for row in SHELF[7:]})
    drawn = browse(tmp_path, catalogueKnown=known)
    assert drawn["fitOn"] == "you can read now"
    assert len(drawn["rows"]) == 7, "the ones they know nine words in ten of"


def test_the_page_never_opens_on_an_almost_empty_shelf(tmp_path: Path) -> None:
    """Somebody who has marked a dozen words honestly reads 2% known on every row, and
    nothing is within reach yet. The default is the narrowest band that still leaves a
    screen's worth, so it widens on its own rather than greeting them with nothing."""
    barely = {row["id"]: {"known": 0.02} for row in SHELF}
    drawn = browse(tmp_path, catalogueKnown=barely)
    assert drawn["fitOn"] == "everything", "not a greeting of nothing"
    assert len(drawn["rows"]) == len(SHELF)


def test_a_reader_who_asks_for_a_band_gets_it_however_little_it_leaves(tmp_path: Path) -> None:
    """The self-correcting default is a greeting, not a rule. A chosen band is an answer,
    and an empty one is an answer too."""
    barely = {row["id"]: {"known": 0.02} for row in SHELF}
    drawn = browse(tmp_path, catalogueKnown=barely, view={"fit": "now"})
    assert drawn["fitOn"] == "you can read now"
    assert drawn["rows"] == []


def test_a_card_says_what_there_is_to_play_without_opening_anything(tmp_path: Path) -> None:
    """ "Without playing w/ checkboxes or dropdowns I want to see immediately what media is
    available." One mark, never two: a video can be listened to as well."""
    marks = {row["title"]: row["media"] for row in browse(tmp_path)["rows"]}
    assert marks["פיזיקה"] == "Video"
    assert marks["כימיה"] == "Audio"
    assert marks["סיפור"] == ""


def test_a_card_carries_the_facts_a_reader_chooses_by(tmp_path: Path) -> None:
    """What it is, how long it takes, how hard its words are — and what share of them
    this reader knows, which is the line the front door sells."""
    known = {"story-one": {"known": 0.72}}
    rows = browse(tmp_path, catalogueKnown=known)["rows"]
    one = next(row for row in rows if row["title"] == "סיפור")
    assert one["meta"] == "Stories · 7 min · 18% hard words"
    assert "72%" in one["known"]
    two = next(row for row in rows if row["title"] == "סיפור שני")
    assert two["known"] == "New to you", "never 0%, which is a claim about the reader"


def test_a_card_keeps_the_cell_a_build_narrates_itself_in(tmp_path: Path) -> None:
    """`build()` finds it with `open.querySelector`, so a state cell hung on the list item
    rather than inside the pressed element is one it throws on."""
    row = browse(tmp_path)["rows"][0]
    assert row["state"] == "", "empty until a build speaks"


def test_an_unbuilt_card_is_a_button_and_a_built_one_is_a_link(tmp_path: Path) -> None:
    """What pressing an unbuilt row does is start spending. A card must not quietly
    become a cheaper way to do that."""
    own = shelf("story-one", "mine-he")
    rows = browse(tmp_path, readers=[own])["rows"]
    opens = {row["title"]: row["opens"] for row in rows}
    assert opens["סיפור"] == "a", "a text this reader has built is a link"
    assert opens["סיפור שני"] == "button", "one they have not is pressed"


def test_being_sent_to_a_text_lifts_the_subject_and_the_band(tmp_path: Path) -> None:
    """Being sent is a stronger claim than a setting made earlier, and the one text
    somebody was sent for is exactly the one a "what you can read now" list may hide."""
    known = {row["id"]: {"known": 0.9} for row in SHELF[:7]}
    known.update({"story-four": {"known": 0.1}})
    drawn = browse(
        tmp_path,
        catalogueKnown=known,
        view={"subject": "journalism"},
        hash="#story-four",
    )
    assert drawn["pointed"] == ["סיפור רביעי"], drawn["pointed"]
    assert drawn["subjectOn"] == "All"
    assert drawn["fitOn"] == "everything"


def test_the_subjects_survive_the_kind_the_page_opens_on(tmp_path: Path) -> None:
    """The page opens a new reader on the Scenes, and no scene is filed under a subject.
    Computed with the kind still standing, the one row this page is browsed by vanished
    on the first visit of every reader who had it — found on the running page, not here.
    """
    scenes = SHELF + [
        text(f"scene-{n:02d}", f"סצנה {n}", kind="dialogue", spoken=True) for n in range(1, 5)
    ]
    drawn = browse(tmp_path, catalogue=scenes, view={"kind": "dialogue"})
    assert drawn["subjects"] == ["All", "News", "Sport", "Science"], drawn["subjects"]
    assert {row["title"] for row in drawn["rows"]} == {f"סצנה {n}" for n in range(1, 5)}


def test_a_chips_count_is_what_pressing_it_leaves(tmp_path: Path) -> None:
    """Picking a subject is going somewhere, not narrowing where you are: the kind is a
    refinement inside the place you were, and it is dropped. So the number on the chip is
    the number of texts that actually arrive."""
    scenes = SHELF + [
        text(f"scene-{n:02d}", f"סצנה {n}", kind="dialogue", spoken=True) for n in range(1, 5)
    ]
    shown = browse(tmp_path, catalogue=scenes, view={"kind": "dialogue"})
    promised = dict(zip(shown["subjects"], shown["subjectCounts"], strict=True))
    # What the press leaves: the subject set and the kind dropped, which is what the
    # chip's own handler does. A stored pair of both is a reader who chose both, and an
    # empty list is the honest answer to that.
    pressed = browse(tmp_path, catalogue=scenes, view={"kind": "", "subject": "science"})
    assert len(pressed["rows"]) == promised["Science"]
    assert pressed["subjectOn"] == "Science"


def test_a_collection_is_a_card_of_its_own_shape(tmp_path: Path) -> None:
    """A shelf, not a text: no cover, a caret, and a press that opens rather than reads.

    The first attempt reused the table's row here, and it looked exactly like what it was
    — a row of grid cells with no grid around them, stacked upright in the middle of a
    grid of cards. Found on the running page.
    """
    drawn = draw(tmp_path, view={"shape": "cards"})
    folded = next(row for row in drawn["rows"] if row["group"] == "tanakh")
    assert folded["opens"] == "button", "a collection is pressed open"
    assert folded["expanded"] == "false"
    assert folded["title"] == "תנ״ך"
    assert "6 texts" in folded["meta"], folded["meta"]
    assert folded["cells"] == [], "it is a card, so it has no columns"

    opened = draw(tmp_path, view={"shape": "cards"}, opened={"tanakh": True})
    shelf_row = next(row for row in opened["rows"] if row["group"] == "tanakh")
    assert shelf_row["expanded"] == "true"
    inside = {row["title"] for row in opened["rows"] if not row["group"]}
    assert {"רות", "אסתר"} <= inside, "and its texts are cards beside it"


def test_being_sent_to_build_a_text_lands_on_its_press(tmp_path: Path) -> None:
    """`/open/<id>` sends `#build:<id>` when this reader has not built the text yet
    (targum-internal#313). It means the same as a bare id and adds one thing: the row's
    own offer goes under the reader's hand, so they land one press from reading rather
    than on a marked line with nothing to press."""
    from targum.catalogue import CATALOGUE

    wanted = next(entry for entry in CATALOGUE if entry.language.startswith("he"))
    sent = draw(tmp_path, hash=f"#build:{wanted.id}")
    assert sent["pointed"] == [wanted.title], sent["pointed"]


def test_the_build_prefix_never_starts_a_build(tmp_path: Path) -> None:
    """An address is not consent. The row is marked and its press is focused; nothing is
    quoted and nothing is bought, which is the half of this that must not bend."""
    from targum.catalogue import CATALOGUE

    wanted = next(entry for entry in CATALOGUE if entry.language.startswith("he"))
    sent = draw(tmp_path, hash=f"#build:{wanted.id}")
    row = next(row for row in sent["rows"] if row["title"] == wanted.title)
    # Still the unpressed button it was: a build writes its own sentence into this cell.
    assert row["opens"] == "button"
    assert row["state"] == "", row["state"]


def test_the_newest_sort_puts_the_lately_added_first(tmp_path: Path) -> None:
    """ "I want to see what was recently added right away." The catalogue carried no date
    at all before targum-internal#315."""
    shelf = [
        text("old-one", "ישן", added="2026-01-05"),
        text("newest", "חדש", added="2026-09-16"),
        text("middle", "אמצעי", added="2026-05-01"),
    ]
    drawn = browse(tmp_path, catalogue=shelf, view={"sort": "added"})
    order = [row["title"] for row in drawn["rows"]]
    assert order == ["חדש", "אמצעי", "ישן"], order


def test_a_text_nobody_dated_sorts_last_and_not_first(tmp_path: Path) -> None:
    """Nine hundred rows predate the field. "We do not know when this arrived" must never
    read as "this just arrived", which is what an empty date sorting first would say."""
    shelf = [
        text("undated", "ללא תאריך"),
        text("old-one", "ישן", added="2026-01-05"),
        text("newest", "חדש", added="2026-09-16"),
    ]
    drawn = browse(tmp_path, catalogue=shelf, view={"sort": "added"})
    order = [row["title"] for row in drawn["rows"]]
    assert order[-1] == "ללא תאריך", order


def test_a_text_that_arrived_lately_says_so_on_its_card(tmp_path: Path) -> None:
    """Answered by the card rather than by a sort, so it is true of the page whatever
    order the reader has it in."""
    import datetime

    today = datetime.date.today()
    shelf = [
        text("fresh", "טרי", added=(today - datetime.timedelta(days=2)).isoformat()),
        text("stale", "ישן", added=(today - datetime.timedelta(days=90)).isoformat()),
        text("undated", "ללא תאריך"),
    ]
    marks = {row["title"]: row["fresh"] for row in browse(tmp_path, catalogue=shelf)["rows"]}
    assert marks["טרי"] == "New"
    assert marks["ישן"] == "", "a text from three months ago is not news"
    assert marks["ללא תאריך"] == "", "and neither is one nobody dated"


def test_a_date_in_the_future_is_not_new_for_ever(tmp_path: Path) -> None:
    """A row dated tomorrow by a bad clock or a bad hand would otherwise sit marked
    New until somebody noticed, which is the kind of thing nobody notices."""
    import datetime

    ahead = (datetime.date.today() + datetime.timedelta(days=30)).isoformat()
    shelf = [text("ahead", "מחר", added=ahead), text("fine", "היום", added="2020-01-01")]
    marks = {row["title"]: row["fresh"] for row in browse(tmp_path, catalogue=shelf)["rows"]}
    assert marks["מחר"] == "", marks


def test_undated_rows_keep_the_order_the_catalogue_put_them_in(tmp_path: Path) -> None:
    """Nine hundred rows predate the field and nothing can date them. Without this,
    "Newest" would be alphabetical among them, which is no order at all — so they fall
    back to where they sit in the file, which is where they were appended.

    Evidence of order, never of date: it can never lift an undated row above a dated one,
    and it never marks one New.
    """
    shelf = [
        text("first-in", "ראשון"),
        text("second-in", "שני"),
        text("third-in", "שלישי"),
        text("dated", "מתוארך", added="2020-01-01"),
    ]
    drawn = browse(tmp_path, catalogue=shelf, view={"sort": "added"})
    order = [row["title"] for row in drawn["rows"]]
    assert order[0] == "מתוארך", f"a dated row outranks every undated one: {order}"
    assert order[1:] == ["שלישי", "שני", "ראשון"], order
    assert all(row["fresh"] == "" for row in drawn["rows"]), "and none of them is New"


# --- a build is on the shelf while it is building (design.md §12, 2026-09-17) ---------


def job(**extra):
    """One build in progress, as `/jobs` describes it."""
    row = {
        "id": "j1",
        "title": "ספר חדש",
        "english": "A new book",
        "language": "he",
        "stage": "working",
        "done": 3,
        "total": 10,
        "message": "Adding vowel points…",
        "error": "",
        "reader": "",
        "behind": 0,
    }
    row.update(extra)
    return row


def test_a_text_being_built_is_on_the_shelf_already(tmp_path: Path) -> None:
    """ "I need a more obvious place to see the progress — the notifications tab is too
    easy to miss." The bell follows the reader everywhere, which is what makes it
    ambient; the shelf is where they were going."""
    drawn = browse(tmp_path, jobs=[job()], view={"where": "mine"})
    row = next(row for row in drawn["rows"] if row["title"] == "ספר חדש")
    assert row["making"] == "Building"
    assert row["meta"] == "We're adding vowel points…", row["meta"]
    assert row["opens"] == "span", "not a link and not a button: nothing to press yet"


def test_a_build_is_filed_under_your_uploads_and_not_the_catalogue(tmp_path: Path) -> None:
    """That tab is "texts of mine", and a build is exactly that until it exists."""
    mine = browse(tmp_path, jobs=[job()], view={"where": "mine"})
    assert any(row["title"] == "ספר חדש" for row in mine["rows"])
    everybody = browse(tmp_path, jobs=[job()], view={"where": "library"})
    assert not any(row["title"] == "ספר חדש" for row in everybody["rows"])


def test_no_filter_can_hide_the_text_you_are_waiting_on(tmp_path: Path) -> None:
    """Nothing about a build is measured yet — no kind, no register, no hard-word share —
    so every narrowing control would hide it, and the one row the reader is actually
    waiting on would be the one they could not find."""
    narrow = {"where": "mine", "kind": "poetry", "register": "biblical", "fit": "now"}
    drawn = browse(tmp_path, jobs=[job()], view=narrow)
    assert [row["title"] for row in drawn["rows"]] == ["ספר חדש"], drawn["rows"]


def test_a_finished_or_failed_build_is_not_a_row(tmp_path: Path) -> None:
    """It became a text, or it did not happen. Either way the shelf has the truth about
    it and this row would be a second, older copy of that truth."""
    made = job(stage="done", reader="mine-he/reader")
    done = browse(tmp_path, jobs=[made], view={"where": "mine"})
    assert not any(row["title"] == "ספר חדש" for row in done["rows"])
    broke = browse(tmp_path, jobs=[job(error="it broke")], view={"where": "mine"})
    assert not any(row["title"] == "ספר חדש" for row in broke["rows"])


def test_a_build_waiting_its_turn_says_so_rather_than_looking_stuck(tmp_path: Path) -> None:
    """A second build behind a first one showed no progress at all and read as broken."""
    queued = job(stage="queued", behind=2, message="")
    drawn = browse(tmp_path, jobs=[queued], view={"where": "mine"})
    row = next(row for row in drawn["rows"] if row["title"] == "ספר חדש")
    assert row["meta"] == "Waiting behind 2 builds", row["meta"]


def test_a_text_inside_a_shut_shelf_that_a_filter_also_hides_is_still_reached(
    tmp_path: Path,
) -> None:
    """Two things stood between the reader and the text, and one flag covered both.

    `lifted` meant "I have opened a collection" and "I have lifted the filters" at once,
    so opening the collection spent the one chance to lift them: the second pass found
    nothing and gave up before it looked at the filters. Found on the running page
    following `/open/ruth`, which opens Ketuvim and then needs the band lifted too.
    """
    from targum.catalogue import CATALOGUE, collections

    inside = {member: group.id for group in collections() for member in group.members}
    wanted = next(
        entry for entry in CATALOGUE if entry.id in inside and entry.language.startswith("he")
    )
    sent = draw(
        tmp_path,
        # Shut, and narrowed to something this text is not.
        view={"kind": "dialogue", "register": "modern", "level": "hard"},
        hash=f"#build:{wanted.id}",
    )
    assert sent["pointed"] == [wanted.title], sent["pointed"]
