"""The arrival's script, run rather than read.

The questions a new reader is asked, one a screen, on `/welcome` since Learn was taken
apart (design.md §12, "Home is Your targums, and Continue leads it", 2026-10-08). These
were Learn's tests; what they asked of the sheet under the arrival — which text it chose —
is asked of the choice itself now (`first`), and of where the last answer goes.

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

HARNESS = Path(__file__).resolve().parent / "js" / "arrival.js"

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


THREE = [{"subject": "Sport"}, {"subject": "History"}, {"subject": "Archaeology"}]


def test_the_page_does_not_quietly_give_up_drawing() -> None:
    """`arrival.js` catches around its whole draw and goes home, so a bug in it reads as
    a page with nothing to ask. A new reader is asked; one who has answered goes home."""
    assert draw([], {}, shared=seeded())["arrival"], "a new reader is asked"
    for stamps in ({"targum:arrived": "sport"}, {"targum:arrived": "judaism,sport,food"}):
        answered = draw([], stamps, shared=seeded())
        assert answered["arrival"] == [] and answered["home"].startswith("/"), stamps


def test_a_new_reader_is_asked_what_they_are_interested_in() -> None:
    """In subjects, in the words somebody uses about themselves — not in the register,
    collection and file format the library happens to be built from."""
    drawn = draw([], shared=seeded())
    assert drawn["arrival"][:4] == [
        "Everyday conversation",
        "Life in Israel: money, health, school, home",
        "Torah and Judaism",
        "News",
    ]
    assert "Archaeology" in drawn["arrival"]
    assert not drawn["home"], "and the page stays for the answer"


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
    assert len(thin["arrival"]) == 20  # "Life in Israel" made it twenty (#393)


def test_the_arrival_is_one_question_a_screen() -> None:
    """targum-internal#334: "one question page", "always clear what next step is".

    The subjects are the first screen and the only thing on it; the ladder is not drawn
    beside them. Each screen says where it is, in words.
    """
    first = draw([], shared=seeded())
    assert first["subjectsUp"] and first["levels"] == []
    assert first["step"] == "1 of 2"
    assert first["arriving"], "the page knows the arrival is up, so a phone can make it the screen"

    second = draw([], shared=seeded(), do=[*THREE, {"press": "arrival-done"}])
    assert not second["subjectsUp"], "the subjects have gone"
    assert second["step"] == "2 of 2"
    assert len(second["levels"]) == 8
    assert second["levels"][0].startswith("Just starting")
    # What a person can follow, not what they can read: many come to listen and watch.
    assert any(row.startswith("I follow the news") for row in second["levels"])
    assert not any("read" in row.lower() for row in second["levels"])
    # Pressing a row is the answer, so the second screen has no Next to press.
    assert not second["nextShown"]


def test_three_subjects_wake_next() -> None:
    """One subject is a label and two is a preference; three is the first number that
    describes somebody."""
    two = draw([], shared=seeded(), do=[{"subject": "Sport"}, {"subject": "History"}])
    assert two["done"] is False, "two is not enough"
    assert two["counted"] == "Pick 1 more"

    three = draw([], shared=seeded(), do=THREE)
    assert three["done"] is True, "three subjects and Next is live"
    assert three["counted"] == ""


def test_either_question_may_be_skipped() -> None:
    """A question a reader may not decline is a gate, and the arrival is not one. Skip is
    live from the first moment — the only filled button on a new reader's first screen
    used to be a disabled one, with no way past it but to answer."""
    past = draw([], shared=seeded(), do=[{"press": "arrival-skip"}])
    assert past["step"] == "2 of 2", "skipping the subjects goes on to the ladder"
    assert "targum:arrived" not in (past.get("kept") or {}), "and keeps nothing it was not told"

    out = draw([], shared=seeded(), do=[{"press": "arrival-skip"}, {"press": "arrival-skip"}])
    assert out["arrival"] == [] and not out["arriving"]
    assert not any("/account/level" in str(where) for where in out["posted"])
    assert "/reader/" in out["went"], "and still opens a text: the track's own start"


def test_the_last_answer_opens_the_text_it_chose() -> None:
    """Not Learn with a card to find. The next step after the last question is the
    reader, open (design.md §12, 2026-09-19)."""
    after = draw(
        [],
        shared=seeded(),
        do=[
            {"subject": "Sport"},
            {"subject": "History"},
            {"subject": "Archaeology"},
            {"press": "arrival-done"},
            {"rung": "I can hold a simple conversation"},
        ],
    )
    assert "/reader/holon" in after["went"], after["went"]


def test_the_rung_is_kept_on_the_account_and_in_the_browser() -> None:
    """The fifth state of #306. It was asked and thrown away (2026-09-17) and then not
    asked (2026-09-18); since 2026-09-19 it is asked and **kept**, as a seed."""
    after = draw(
        [],
        shared=seeded(),
        do=[*THREE, {"press": "arrival-done"}, {"rung": "I follow the news"}],
    )
    assert (after.get("kept") or {}).get("targum:declared") == "gimel"
    sent = [call for call in after["sent"] if "/account/level" in call["path"]]
    assert sent and sent[0]["body"] == {"level": "gimel"}
    assert any("/account/interest" in str(where) for where in after["posted"])


def hard_and_easy() -> list[dict[str, Any]]:
    return [
        reader(
            "easy", "קל", "easy", kind="article", register="modern", tags=["sport"], difficulty=5
        ),
        reader(
            "mid", "בינוני", "mid", kind="article", register="modern", tags=["sport"], difficulty=20
        ),
        reader(
            "hard", "קשה", "hard", kind="article", register="modern", tags=["sport"], difficulty=45
        ),
    ]


def test_the_rung_picks_how_hard_the_first_text_is() -> None:
    """Aleph takes the easiest a subject can answer and vav the hardest. The reader at
    gimel who is handed Scene 1 has been patronised before pressing anything (#306)."""
    stamps = {"targum:arrived": "sport,history,art"}
    low = draw([], {**stamps, "targum:declared": "aleph"}, shared=hard_and_easy())
    assert low["first"] == "קל"
    high = draw([], {**stamps, "targum:declared": "vav"}, shared=hard_and_easy())
    assert high["first"] == "קשה"
    unsaid = draw([], stamps, shared=hard_and_easy())
    assert unsaid["first"] == "קל", "no rung, and the shelf's own order is the order"


def leveled(name: str, title: str, rung: str, **extra: Any) -> dict[str, Any]:
    """A modern row that says which rung of `level.py`'s ladder it was written for."""
    return reader(
        name,
        title,
        name,
        kind="article",
        register="modern",
        level={"rung": "", "name": rung, "cefr": ""},
        **extra,
    )


def test_the_rung_reads_the_level_a_text_was_written_for() -> None:
    """Where the shelf says what rung a row was written for, that is what is matched,
    not its place in a sort. By place alone the one row under a subject was every
    rung's answer (David, 2026-09-28: finished the arrival at "Just starting" and was
    not handed a text he could read). The pick is the hardest at or under the rung
    said, and "aleph plus" on a row is "aleph-plus" in the arrival."""
    shelf = [
        leveled("easy", "קל", "aleph", tags=["sport"]),
        leveled("some", "קצת", "aleph plus", tags=["sport"]),
        leveled("hard", "קשה", "vav", tags=["sport"]),
    ]
    stamps = {"targum:arrived": "sport,history,art"}
    assert draw([], {**stamps, "targum:declared": "aleph"}, shared=shelf)["first"] == "קל"
    assert draw([], {**stamps, "targum:declared": "gimel"}, shared=shelf)["first"] == "קצת", (
        "gimel is past aleph plus and short of vav: the hardest it can follow"
    )
    assert draw([], {**stamps, "targum:declared": "vav"}, shared=shelf)["first"] == "קשה"
    # Where place and level part: two rows, and gimel sits past the middle of the
    # ladder, so by place it took the vav one. By level it is the one it can follow.
    pair = [shelf[0], shelf[2]]
    assert draw([], {**stamps, "targum:declared": "gimel"}, shared=pair)["first"] == "קל"


def test_a_subject_past_reach_gives_way_to_the_rung() -> None:
    """A vav article is not "Sport" to somebody just starting. A subject whose rows are
    all more than a rung past what the reader said gives way to the next subject, and
    where none is left the rung picks from the modern shelf — a text they can follow
    over a subject they cannot read."""
    shelf = [
        leveled("hard", "קשה", "vav", tags=["sport"]),
        leveled("food", "אוכל", "bet", tags=["food"]),
        leveled("easy", "קל", "aleph"),
    ]
    stamps = {"targum:arrived": "sport,food,art", "targum:declared": "aleph"}
    assert draw([], stamps, shared=shelf)["first"] == "קל", "sport and food are past aleph"
    stretch = {**stamps, "targum:declared": "aleph-plus"}
    assert draw([], stretch, shared=shelf)["first"] == "אוכל", "one rung up is a stretch"
    fluent = {**stamps, "targum:declared": "vav"}
    assert draw([], fluent, shared=shelf)["first"] == "קשה", "and sport, at vav"


def test_where_the_rung_decides_reach_comes_before_a_voice() -> None:
    """The second moment is the voice, and it is found on a page the reader can follow:
    with no subject to go on, a silent text at their rung beats a heard one far past it."""
    shelf = [
        leveled("loud", "קול", "vav", spoken=True),
        leveled("quiet", "שקט", "aleph"),
    ]
    came = draw(
        [], {"targum:arrived": "archaeology,art,music", "targum:declared": "aleph"}, shared=shelf
    )
    assert came["first"] == "שקט"


def test_a_measured_rung_outvotes_the_one_they_said() -> None:
    """The rule that keeps a declared level small: the first measurement retires it.
    A reader whose own marked words reach aleph is routed by nothing they said."""
    known = {
        f"w{n}": {"surface": f"w{n}", "status": 9, "band": "easy", "at": 1} for n in range(400)
    }
    stamps = {
        "targum:arrived": "sport,history,art",
        "targum:declared": "vav",
        "targum:vocab:he": json.dumps(known),
    }
    measured = draw([], stamps, shared=hard_and_easy())
    assert measured["first"] == "קל", "vav was said, and is not consulted"


def test_the_account_hands_the_rung_back_to_a_second_browser() -> None:
    """Asked on a phone, not asked again on a laptop — and the laptop's Library and first
    text are seeded by the same answer."""
    me = {"signedIn": True, "interest": ["sport", "history", "art"], "declared": "dalet"}
    adopted = draw([], shared=seeded(), me=me)
    assert (adopted.get("kept") or {}).get("targum:declared") == "dalet"


def test_nothing_prints_the_rung_back() -> None:
    """It is never shown. Your Progress shows the measured rung and only that, and no
    sentence anywhere says "you said gimel" (design.md §12)."""
    from pathlib import Path as _P

    root = _P(__file__).resolve().parent.parent / "src" / "targum" / "render"
    for page in ("progress.js", "lists.js", "account.js", "chat.js"):
        source = (root / "assets" / page).read_text(encoding="utf-8")
        assert "targum:declared" not in source and "DECLARED" not in source, page
    for page in ("progress.html.j2", "you.html.j2"):
        assert "declared" not in (root / "templates" / page).read_text(encoding="utf-8"), page


def test_the_measured_rung_is_untouched_by_this() -> None:
    """`level.py` still climbs the ulpan ladder off words the reader actually marked, and
    Your Progress still shows it — that is the level §12 sanctions. Pinned when the asked
    rung was taken out (2026-09-18) so a clean-up could not take this with it, and kept
    now that the asked one is back, for the same reason."""
    from pathlib import Path as _P

    root = _P(__file__).resolve().parent.parent
    assert (root / "src" / "targum" / "level.py").is_file()
    progress = (root / "src" / "targum" / "render" / "templates" / "progress.html.j2").read_text(
        encoding="utf-8"
    )
    assert "rung" in progress, "the measured rung still has its panel"


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
    assert came["first"] == "רות", "judaism is offered before sport"

    # Nothing seeded for archaeology or history, so the one subject that is answerable
    # decides the sheet rather than the whole answer falling back to the default track.
    thin = draw([], {"targum:arrived": "archaeology,history,sport"}, shared=seeded())
    assert thin["first"] == "הפועל"


def test_a_subject_nothing_is_filed_under_falls_back_to_the_track() -> None:
    """Three subjects the shelf cannot answer is not a reason to draw no sheet."""
    none = draw([], {"targum:arrived": "archaeology,art,music"}, shared=seeded())
    assert none["first"] == "", "no subject answers, and no rung was said"
    skipped = draw([], shared=seeded(), do=[{"press": "arrival-skip"}, {"press": "arrival-skip"}])
    assert "/reader/" in skipped["went"], "the track's own start opens instead"


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
    assert asked["first"] == "", "the old word chooses nothing"


def test_a_first_text_is_one_that_can_be_heard_where_the_subject_has_one() -> None:
    """The second thing a new reader should find out is that the page has a voice — the
    first stranger never did — and nobody finds that out on a silent text."""
    shelf = [
        reader("quiet", "שקט", "quiet", kind="article", register="modern", tags=["sport"]),
        reader(
            "loud", "קול", "loud", kind="article", register="modern", tags=["sport"], spoken=True
        ),
    ]
    came = draw([], {"targum:arrived": "sport,history,art"}, shared=shelf)
    assert came["first"] == "קול"
    # Where nothing in the subject is voiced, the subject still wins: it is what they asked for.
    silent = draw([], {"targum:arrived": "sport,history,art"}, shared=shelf[:1])
    assert silent["first"] == "שקט"


def test_a_rung_without_a_subject_is_heard_first_too() -> None:
    """A reader who skipped the subjects and named a rung is as new as one who named
    three: the modern text the rung lands on is one with a voice, where there is one."""
    shelf = [
        reader("quiet", "שקט", "quiet", kind="article", register="modern", difficulty=10),
        reader(
            "loud", "קול", "loud", kind="article", register="modern", difficulty=30, spoken=True
        ),
    ]
    came = draw([], {"targum:declared": "aleph"}, shared=shelf)
    assert came["first"] == "קול", "the easiest heard one, over an easier silent one"
    silent = draw([], {"targum:declared": "aleph"}, shared=shelf[:1])
    assert silent["first"] == "שקט", "and a silent one where nothing is heard"


def test_the_arrival_opens_a_book_at_its_first_chapter_not_its_contents() -> None:
    """Regression: ISSUE-001 — the arrival's last answer opened a book's contents page.
    Found by /qa on 2026-09-20. A book's own address is its list of chapters, so a new
    reader who had just answered two questions landed one more press from a line of
    Hebrew. It opens the first chapter that is ready; a text with no chapters opens as
    itself."""
    chapters = [
        {"number": 1, "title": "א", "file": "sec-0001.html", "ready": False},
        {"number": 2, "title": "ב", "file": "sec-0002.html", "ready": True},
    ]
    book = reader("ruth", "רות", "ruth", register="biblical", tags=["tanakh"], chapters=chapters)
    went = draw(
        [],
        shared=[book],
        do=[
            {"subject": "Torah and Judaism"},
            {"subject": "History"},
            {"subject": "Art"},
            {"press": "arrival-done"},
            {"rung": "Just starting"},
        ],
    )["went"]
    assert "/reader/ruth/reader/sec-0002.html" in went, went

    single = reader("holon", "הפועל", "holon", kind="article", register="modern", tags=["sport"])
    went = draw(
        [],
        shared=[single],
        do=[
            {"subject": "Sport"},
            {"subject": "History"},
            {"subject": "Art"},
            {"press": "arrival-done"},
            {"press": "arrival-skip"},
        ],
    )["went"]
    assert "/reader/holon/reader/index.html" in went, went


# --- the connector's banner, above the row (design.md §12, 2026-09-24) ----------------


UNCONNECTED = {"signedIn": True, "connections": []}


ANSWERED = [
    {"subject": "Sport"},
    {"subject": "History"},
    {"subject": "Art"},
    {"press": "arrival-done"},
    {"rung": "Just starting"},
]


def test_the_arrival_ends_on_the_connector_and_continue_is_still_one_press() -> None:
    """After the rung, a last card for a signed-in reader with no connection, said to be
    optional (2026-09-28: "this makes it seem like installing the MCP is mandatory"):
    the address to copy, and Continue as its only press, so the text the answers chose is
    one press away. No Skip beside it: it did the same thing, and read like a step to get
    past."""
    shelf = [reader("holon", "הפועל", "holon", kind="article", register="modern", tags=["sport"])]
    up = draw([], shared=shelf, me=UNCONNECTED, do=ANSWERED)
    assert up["connectUp"], "the rung leads to the card, not straight into the text"
    assert up["step"] == "", "optional, so not counted as a step to get through"
    assert up["connectAddress"].endswith("/mcp"), "this site's own address, as /connect shows"
    assert up["doneSays"] == "Continue" and up["nextShown"] and up["done"]
    assert not up["skipShown"], "one way on, not two that do the same"
    assert not up["went"], "nothing is opened until the press"

    opened = draw([], shared=shelf, me=UNCONNECTED, do=[*ANSWERED, {"press": "arrival-done"}])
    assert "/reader/holon/" in opened["went"], opened["went"]


@pytest.mark.parametrize(
    ("me", "connector"),
    [
        ({"signedIn": True, "connections": [{"client": "c"}]}, True),
        (UNCONNECTED, False),
        (None, True),
    ],
    ids=["connected", "dark", "signed-out"],
)
def test_the_connector_card_is_only_for_somebody_who_can_take_it_up(
    me: dict[str, Any] | None, connector: bool
) -> None:
    """The banner's rule: open, signed in, and no connection yet. Anybody else goes from
    the rung straight into the text, as before."""
    shelf = [reader("holon", "הפועל", "holon", kind="article", register="modern", tags=["sport"])]
    done = draw([], shared=shelf, me=me, connector=connector, do=ANSWERED)
    assert not done["connectUp"]
    assert "/reader/holon/" in done["went"], done["went"]


def test_a_new_reader_is_welcomed_before_anything_is_asked() -> None:
    """ "Very weird to come and see this as first screen. No welcome, no telling you where
    you are, no asking your name, just a question" (David, 2026-09-28). The welcome says
    where they are and asks what to call them; it is not a question, so the bars do not
    count it and there is nothing to skip."""
    page = draw([], shared=seeded(), me=UNCONNECTED, welcome=True)
    assert page["welcomeUp"] and not page["subjectsUp"]
    assert page["nameAsked"], "an account can keep a name"
    assert page["doneSays"] == "Continue" and page["done"] and not page["skipShown"]
    on = draw([], shared=seeded(), me=UNCONNECTED, welcome=True, do=[{"press": "arrival-done"}])
    assert on["subjectsUp"] and on["step"] == "1 of 2", "the questions, and only they, counted"


def test_a_name_given_is_kept() -> None:
    page = draw(
        [],
        shared=seeded(),
        me=UNCONNECTED,
        welcome=True,
        do=[{"name": "  David "}, {"press": "arrival-done"}],
    )
    named = [c["body"] for c in page["sent"] if c["path"].split("?")[0] == "/account/name"]
    assert named == [{"name": "David"}]
    quiet = draw([], shared=seeded(), me=UNCONNECTED, welcome=True, do=[{"press": "arrival-done"}])
    assert not [c for c in quiet["sent"] if c["path"].split("?")[0] == "/account/name"]


def test_somebody_signed_out_is_welcomed_and_not_asked_a_name() -> None:
    """Nothing could keep it, so nothing is asked."""
    page = draw([], shared=seeded(), welcome=True)
    assert page["welcomeUp"] and not page["nameAsked"]
