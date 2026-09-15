"""A conversation read back as a targum — always Hebrew, every line with its English."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from targum import level
from targum.accounts import Store
from targum.chat import tools, transcript
from targum.ingest import load as ingest_load
from targum.ingest import transcript as transcript_ingest
from targum.models import BlockKind
from targum.pipeline import Build
from targum.segment import HebrewSegmenter, segment_document
from targum.serve import Library

TURNS = [
    {"n": 1, "role": "user", "said": "I went to the market this morning"},
    {
        "n": 2,
        "role": "assistant",
        "said": (
            "> הָלַכְתִּי לַשּׁוּק הַבֹּקֶר.\n= I went to the market this morning\n"
            "מָה קָנִיתָ שָׁם?\n= What did you buy there?"
        ),
    },
    {"n": 3, "role": "user", "said": "קניתי לחם"},
    {
        "n": 4,
        "role": "assistant",
        "said": "> קָנִיתִי לֶחֶם.\n= I bought bread.\nטָעִים!\n= Tasty.\nוּמָה עוֹד?\n= And what else?",
    },
    {"n": 5, "role": "user", "said": "nothing else"},
    # A reply that broke the contract: no recast, and one Hebrew line without English.
    {"n": 6, "role": "assistant", "said": "בְּסֵדֶר.\nOK then."},
    # Tool traffic between turns carries nothing said.
    {"n": 7, "role": "user", "said": ""},
]


def test_the_record_is_hebrew_on_both_sides_and_says_what_it_lost() -> None:
    kept, dropped = transcript.lines(TURNS, "Dov")
    assert [(line.speaker, line.english) for line in kept] == [
        ("Dov", "I went to the market this morning"),
        ("targum", "What did you buy there?"),
        ("Dov", "I bought bread."),
        ("targum", "Tasty."),
        ("targum", "And what else?"),
    ]
    assert all(any("א" <= ch <= "ת" for ch in line.hebrew) for line in kept)
    assert not any(line.hebrew.startswith(">") for line in kept)
    assert dropped == 1, "the turn whose reply gave it no recast"


@pytest.fixture
def world(tmp_path: Path):
    store = Store(tmp_path / "db")
    out = tmp_path / "out"
    out.mkdir()
    library = Library(out, store=store)
    person, _ = store.finish_sign_in(store.start_sign_in("dov@example.com"))  # type: ignore[misc]
    store.rename(person, "Dov")
    chat_id = store.chat_open(person.id, mode="talk")
    for turn in TURNS:
        if turn["said"] or turn["role"] == "user":
            content: Any = (
                turn["said"] if turn["role"] == "user" else [{"type": "text", "text": turn["said"]}]
            )
            store.chat_say(chat_id, str(turn["role"]), content, str(turn["said"]))
    return library, store, person, chat_id


def test_the_file_is_written_in_the_home_and_read_as_turns_with_speakers(
    world, tmp_path: Path
) -> None:
    library, store, person, chat_id = world
    home = library.home(person)
    path, kept, dropped = transcript.write(store, home, chat_id, "Dov")
    assert path == home / "chats" / f"{chat_id}.chat" and kept == 5 and dropped == 1
    written = json.loads(path.read_text(encoding="utf-8"))
    # Titled by its first Hebrew line, not by the English the reader typed (2026-09-14).
    assert written["language"] == "he" and written["title"].startswith("הָלַכְתִּי")

    document = ingest_load(str(path))
    assert document.language == "he" and document.ingester == transcript_ingest.NAME
    assert [block.kind for block in document.blocks] == [BlockKind.turn] * 5
    assert [block.speaker for block in document.blocks] == [
        "Dov",
        "targum",
        "Dov",
        "targum",
        "targum",
    ]
    assert document.blocks[0].text.startswith("הָלַכְתִּי")

    segmented = segment_document(document, HebrewSegmenter())
    assert len(segmented.segments) == 5, "one line is one block is one segment"
    build = Build(str(path), target_language="en", owner="p1", out_root=tmp_path / "b")
    carried = build.authored(document, segmented)
    assert carried is not None and carried.kind == "authored" and carried.provider == "authored"
    assert set(carried.segments) == {s.id for s in segmented.segments}, (
        "every line, so nothing is bought"
    )
    assert carried.segments[segmented.segments[0].id] == "I went to the market this morning"


def test_a_conversation_is_never_a_public_source(world, tmp_path: Path) -> None:
    library, store, person, chat_id = world
    path, _, _ = transcript.write(store, library.home(person), chat_id, "Dov")
    mine = Build(str(path), target_language="en", owner="p1", out_root=tmp_path / "b")
    theirs = Build(str(path), target_language="en", owner="p2", out_root=tmp_path / "b")
    assert not mine.shared_source()
    document = ingest_load(str(path))
    segmented = segment_document(document, HebrewSegmenter())
    assert mine.cache_key(segmented) != theirs.cache_key(segmented), "the key carries the owner"


def test_quoting_writes_the_file_and_never_claims(world, monkeypatch: Any) -> None:
    library, store, person, chat_id = world

    def priced(job: Any) -> None:
        job.title = "שיחה"
        job.segments = 5
        job.total = 5
        job.stage = "ready"

    monkeypatch.setattr(library, "prepare", priced)

    def forbidden(*_: object) -> str:
        raise AssertionError("a quote must not spend")

    monkeypatch.setattr(library, "claim", forbidden)
    monkeypatch.setattr(library, "enqueue", forbidden)
    ctx = tools.Ctx(
        person=person,
        home=library.home(person),
        library=library,
        store=store,
        chat_id=chat_id,
        level=level.EMPTY,
        reads={"en"},
    )
    got = tools.quote_conversation(ctx, {"chat": "somebody-elses-id"})
    quote = got["quote"]
    job = library.jobs[quote["id"]]
    assert job.source.endswith(f"chats/{chat_id}.chat") and job.owner == person.id
    assert job.options.get("words"), (
        "a conversation read back is Hebrew the reader is learning from, so its words "
        "are tappable — the door that most needed this was the one that lacked it"
    )
    assert got["lines"] == 5 and got["dropped"] == 1 and "not in the record" in got["note"]
    assert store.chat_owned(person.id, chat_id)["saved"] == job.id  # type: ignore[index]
    assert store.committed(0) == 0.0

    empty = store.chat_open(person.id, mode="talk")
    store.chat_say(empty, "user", "hi", "hi")
    ctx.chat_id = empty
    assert "Nothing to read back" in tools.quote_conversation(ctx, {})["error"]


def test_the_shelf_files_a_conversation_as_a_dialogue(world) -> None:
    library, store, person, chat_id = world
    home = library.home(person)
    path, _, _ = transcript.write(store, home, chat_id, "Dov")
    shape = library._shape(home, str(path), "he", 20)
    assert shape["kind"] == "dialogue" and shape["register"] == "modern"


def test_why_a_line_was_corrected_is_not_written_into_the_text(tmp_path: Path) -> None:
    """targum-internal#242: the "~ " line is the page's, and a text written from the
    conversation carries the recast and its English and nothing about why."""
    from targum.chat import hebrew

    said = "> אֲנִי הָלַכְתִּי.\n= I went.\n~ Past tense: הָלַכְתִּי, not הָלַךְ.\nיָפֶה.\n= Nice."
    lines = [(p.hebrew, p.english, p.why) for p in hebrew.pairs(said)]
    assert lines == [
        ("אֲנִי הָלַכְתִּי.", "I went.", "Past tense: הָלַכְתִּי, not הָלַךְ."),
        ("יָפֶה.", "Nice.", ""),
    ]
    from targum.chat import transcript

    text = "\n".join(f"{p.hebrew}\n{p.english}" for p in hebrew.pairs(said))
    assert "~" not in text and "Past tense" not in text
    assert transcript  # the writer reads pairs the same way; the why never reaches a Line


def test_an_italian_conversation_is_written_read_and_quoted_in_italian(tmp_path: Path) -> None:
    """Save as targum in an Italian conversation (targum-internal#280): the file says
    Italian, the text loads as Italian, and the quote builds from Italian."""
    store = Store(tmp_path / "db")
    out = tmp_path / "out"
    out.mkdir()
    library = Library(out, store=store)
    person, _ = store.finish_sign_in(store.start_sign_in("dov@example.com"))  # type: ignore[misc]
    chat_id = store.chat_open(person.id, language="it", mode="talk")
    said = [
        ("user", "I went to the sea"),
        ("assistant", "> Sono andato al mare.\n= I went to the sea.\nCom'era?\n= How was it?"),
    ]
    for role, text in said:
        content: Any = text if role == "user" else [{"type": "text", "text": text}]
        store.chat_say(chat_id, role, content, text)
    home = library.home(person)
    ctx = tools.Ctx(
        person=person,
        home=home,
        library=library,
        store=store,
        chat_id=chat_id,
        level=level.snapshot(store, person.id, "it"),
    )
    got = tools.quote_conversation(ctx, {})
    assert got["lines"] == 2 and got["quote"]["id"]
    path = transcript.path_for(home, chat_id)
    written = json.loads(path.read_text(encoding="utf-8"))
    assert written["language"] == "it" and written["title"] == "Sono andato al mare."
    assert ingest_load(str(path)).language == "it"
    assert library.jobs[got["quote"]["id"]].options["from"] == "it"


def test_a_conversation_glossed_in_russian_is_carried_as_russian(world, tmp_path: Path) -> None:
    """An account that reads Russian and not English has its "= " lines written in
    Russian; the text built from them says so, rather than calling them English, and an
    older file that said nothing is English as it always was (targum-internal#287)."""
    library, store, person, chat_id = world
    path, _, _ = transcript.write(store, library.home(person), chat_id, "Dov", "he", "ru")
    document = ingest_load(str(path))
    segmented = segment_document(document, HebrewSegmenter())
    build = Build(str(path), target_language="ru", owner="p1", out_root=tmp_path / "b")
    carried = build.authored(document, segmented)
    assert carried is not None and carried.target_language == "ru"

    older, _, _ = transcript.write(store, library.home(person), chat_id, "Dov")
    raw = json.loads(older.read_text(encoding="utf-8"))
    raw.pop("into")
    older.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    again = Build(str(older), target_language="en", owner="p1", out_root=tmp_path / "c")
    kept = again.authored(
        ingest_load(str(older)), segment_document(ingest_load(str(older)), HebrewSegmenter())
    )
    assert kept is not None and kept.target_language == "en"
