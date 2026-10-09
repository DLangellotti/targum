"""The arrival's script, run rather than read.

The three questions a new reader is asked on `/welcome` — which language, what they like,
how much they read — one a screen, as the FirstRun boards draw them (design.md §12, "The
arrival is three plain questions", 2026-10-09). What the answers choose is asked of the
choice itself (`first`), and of where the last answer goes.

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
        reader(
            "holon",
            "הפועל",
            "holon",
            kind="article",
            register="modern",
            tags=["sport", "journalism"],
        ),
    ]


#: Past the first question with Hebrew, as it stands pressed.
HEBREW = [{"press": "arrival-done"}]
#: And past the second with one subject the seeded shelf can answer.
LIKES_NEWS = [*HEBREW, {"subject": "News"}, {"press": "arrival-done"}]


def test_the_page_does_not_quietly_give_up_drawing() -> None:
    """`arrival.js` catches around its whole draw and goes home, so a bug in it reads as
    a page with nothing to ask. A new reader is asked; one who has answered goes home."""
    assert draw([], {}, shared=seeded())["arrival"], "a new reader is asked"
    for stamps in ({"targum:arrived": "sport"}, {"targum:arrived": "judaism,sport,food"}):
        answered = draw([], stamps, shared=seeded())
        assert answered["arrival"] == [] and answered["home"].startswith("/"), stamps


def test_the_first_question_is_which_language_with_its_badge() -> None:
    """Six languages, each in its own greeting and wearing how far along it is (David,
    2026-10-08 and 2026-10-09), Hebrew pressed to start with so Continue is never asleep."""
    page = draw([], shared=seeded())
    assert page["learningUp"] and not page["subjectsUp"] and not page["levelUp"]
    assert page["step"] == "1 of 3"
    assert page["langs"] == [
        "שָׁלוֹםHebrewBeta",
        "ЗдравствуйтеRussianAlpha",
        "BonjourFrenchAlpha",
        "CiaoItalianAlpha",
        "בְּקַדְמִיןAramaicExperimental",
        "אַ גוטן טאָגYiddishExperimental",
    ]
    assert page["chosen"] == "he" and page["done"] is True
    assert page["footNote"] == "You can add a second language later."
    assert not page["backShown"], "nothing to go back to"
    assert not page["home"], "and the page stays for the answer"


def test_the_second_question_is_a_few_subjects_and_none_is_an_answer() -> None:
    """A few, not twenty (2026-10-09). Continue is live with nothing pressed: liking
    nothing in particular is an answer, and three was a quota."""
    page = draw([], shared=seeded(), do=HEBREW)
    assert page["subjectsUp"] and page["step"] == "2 of 3"
    assert page["arrival"] == [
        "Everyday conversation",
        "News",
        "Stories and novels",
        "History",
        "Torah and Judaism",
        "Science and nature",
        "Travel and places",
        "Food and cooking",
    ]
    assert page["done"] is True and page["backShown"]


def test_the_third_question_is_plain_words_with_no_letter() -> None:
    """No rung letters, no codes (the review's "level codes leak", 2026-10-09): what a
    person reads, in four sentences, and Continue waits for one."""
    page = draw([], shared=seeded(), do=[*HEBREW, {"press": "arrival-done"}])
    assert page["levelUp"] and page["step"] == "3 of 3"
    assert page["levelAsks"] == "How much Hebrew can you read?"
    assert page["levels"] == [
        "I’m learning the letters",
        "I can read short, simple sentences",
        "I read the news with a dictionary nearby",
        "I read most things without help",
    ]
    assert not any(any("\u05d0" <= c <= "\u05ea" for c in row) for row in page["levels"])
    assert page["done"] is False, "nothing said yet"
    picked = draw(
        [], shared=seeded(), do=[*HEBREW, {"press": "arrival-done"}, {"rung": "I can read short"}]
    )
    assert picked["done"] is True and picked["levelUp"], "a press marks it; Continue goes on"


def test_the_level_is_asked_in_the_language_chosen() -> None:
    page = draw(
        [],
        shared=seeded(),
        do=[{"learn": "Russian"}, {"press": "arrival-done"}, {"press": "arrival-done"}],
    )
    assert page["levelAsks"] == "How much Russian can you read?"
    assert page["levels"][1] == "I can read a short story (Chekhov)"
    french = draw(
        [],
        shared=seeded(),
        do=[{"learn": "French"}, {"press": "arrival-done"}, {"press": "arrival-done"}],
    )
    assert french["levels"] == ["I’m just starting", "I can read a short story"]


def test_a_language_is_turned_on_without_dropping_hebrew() -> None:
    """`/account/language` with `add`, the menu's own way (§12, 2026-10-07): an account
    with no rows learns Hebrew by default, and the wholesale form would drop it."""
    me = {"signedIn": True, "learning": ["he"]}
    page = draw([], shared=seeded(), me=me, do=[{"learn": "Russian"}, {"press": "arrival-done"}])
    said = [c["body"] for c in page["sent"] if c["path"].split("?")[0] == "/account/language"]
    assert said == [{"language": "ru", "add": True}]
    assert not [c for c in page["sent"] if c["path"].split("?")[0] == "/account/languages"]
    assert page["languageSet"] == "ru"

    out = draw([], shared=seeded(), do=[{"learn": "Russian"}, {"press": "arrival-done"}])
    assert not [c for c in out["sent"] if "/account/language" in c["path"]], "nobody to tell"
    assert json.loads(out["kept"]["targum:learning"]) == ["he", "ru"]


def test_the_last_answer_opens_the_text_it_chose() -> None:
    """The next step after the last question is the reader, open (design.md §12)."""
    after = draw(
        [],
        shared=seeded(),
        do=[*LIKES_NEWS, {"rung": "I can read short"}, {"press": "arrival-done"}],
    )
    assert "/reader/holon" in after["went"], after["went"]
    assert after["kept"].get("targum:welcomed") == "1", "answered, and not asked again"


def test_the_hebrew_answer_is_kept_as_the_rung_it_stands_for() -> None:
    """The fifth state of #306 still holds: Hebrew's level is kept, as a seed, on the
    ladder `accounts.Store.DECLARED` knows. Four sentences stand for four of its rungs."""
    after = draw(
        [],
        shared=seeded(),
        do=[*LIKES_NEWS, {"rung": "I read the news"}, {"press": "arrival-done"}],
    )
    assert after["kept"].get("targum:declared") == "gimel"
    sent = [call for call in after["sent"] if "/account/level" in call["path"]]
    assert sent and sent[0]["body"] == {"level": "gimel"}
    liked = [c["body"] for c in after["sent"] if "/account/interest" in c["path"]]
    assert liked == [{"interest": ["news"]}]


def test_not_sure_keeps_no_level_and_shows_a_page() -> None:
    """ "I'm not sure, show me a page" is an answer: no rung is kept, an earlier one is
    taken back, and the track's own start opens."""
    out = draw([], shared=seeded(), do=[*HEBREW, {"press": "arrival-done"}, {"unsure": True}])
    sent = [call["body"] for call in out["sent"] if "/account/level" in call["path"]]
    assert sent == [{"level": ""}]
    assert "/reader/scene-1" in out["went"], out["went"]


def russian_shelf() -> list[dict[str, Any]]:
    return [
        reader("mumu", "Муму", "", language="ru", kind="story", difficulty=30),
        reader("kashtanka", "Каштанка", "", language="ru", kind="story", difficulty=10),
        reader("sergius", "Отец Сергий", "", language="ru", kind="novel", difficulty=60),
        *seeded(),
    ]


def test_another_language_opens_a_text_in_it_placed_by_what_they_read() -> None:
    """Nothing reads a level for Russian yet, so the answer is kept nowhere and places
    the first text along that shelf by difficulty."""
    pick = [{"learn": "Russian"}, {"press": "arrival-done"}, {"press": "arrival-done"}]
    novel = draw(
        [],
        shared=russian_shelf(),
        do=[*pick, {"rung": "I can read a novel"}, {"press": "arrival-done"}],
    )
    assert "/reader/sergius" in novel["went"], novel["went"]
    assert not [c for c in novel["sent"] if "/account/level" in c["path"]], "kept nowhere"
    assert "targum:declared" not in novel["kept"]
    unsure = draw([], shared=russian_shelf(), do=[*pick, {"unsure": True}])
    assert "/reader/kashtanka" in unsure["went"], "the easiest page there is"


def test_a_language_with_nothing_on_the_shelf_goes_home_in_it() -> None:
    """Yiddish has no library yet: home in Yiddish, which is upload-first."""
    out = draw(
        [],
        shared=seeded(),
        do=[
            {"learn": "Yiddish"},
            {"press": "arrival-done"},
            {"press": "arrival-done"},
            {"unsure": True},
        ],
    )
    assert out["home"] == "/?learning=yi&k=k", out["home"]
    assert not out["went"]


def test_back_keeps_what_was_pressed() -> None:
    page = draw(
        [],
        shared=seeded(),
        do=[
            {"learn": "Italian"},
            {"press": "arrival-done"},
            {"subject": "History"},
            {"back": True},
        ],
    )
    assert page["learningUp"] and page["chosen"] == "it"
    again = draw(
        [],
        shared=seeded(),
        do=[*HEBREW, {"subject": "History"}, {"press": "arrival-done"}, {"back": True}],
    )
    assert again["subjectsUp"] and again["picked"] == ["History"]


def test_nothing_but_the_three_questions_is_on_the_way() -> None:
    """No welcome card, no name, no connector card: the boards draw none (2026-10-09)."""
    root = Path(__file__).resolve().parent.parent / "src" / "targum" / "render"
    page = (root / "templates" / "welcome.html.j2").read_text(encoding="utf-8")
    for gone in ("arrival-welcome", "arrival-name", "arrival-connect", "arrival-skip"):
        assert gone not in page, gone


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
    the ladder stays in the chart kit. Pinned when the asked rung was taken out
    (2026-09-18) so a clean-up could not take this with it. Your Progress places a reader
    on touchstones since 2026-10-09 (§12, "Your Progress is a story in three parts"), and
    the rung is no longer drawn there; the kit keeps it for the Library's seed."""
    from pathlib import Path as _P

    root = _P(__file__).resolve().parent.parent
    assert (root / "src" / "targum" / "level.py").is_file()
    charts = (root / "src" / "targum" / "render" / "assets" / "charts.js").read_text(
        encoding="utf-8"
    )
    assert "function ladderFor(" in charts and "function standingIn(" in charts
    progress = (root / "src" / "targum" / "render" / "templates" / "progress.html.j2").read_text(
        encoding="utf-8"
    )
    assert 'id="touchstones"' in progress, "where you are is said in kinds of text"


def test_a_subject_pressed_twice_is_put_back() -> None:
    off = draw(
        [],
        shared=seeded(),
        do=[*HEBREW, {"subject": "News"}, {"subject": "History"}, {"subject": "News"}],
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
    skipped = draw([], shared=seeded(), do=[*HEBREW, {"press": "arrival-done"}, {"unsure": True}])
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
            *HEBREW,
            {"subject": "Torah and Judaism"},
            {"press": "arrival-done"},
            {"rung": "I’m learning the letters"},
            {"press": "arrival-done"},
        ],
    )["went"]
    assert "/reader/ruth/reader/sec-0002.html" in went, went

    single = reader("holon", "הפועל", "holon", kind="article", register="modern", tags=["sport"])
    went = draw([], shared=[single], do=[*HEBREW, {"press": "arrival-done"}, {"unsure": True}])[
        "went"
    ]
    assert "/reader/holon/reader/index.html" in went, went
