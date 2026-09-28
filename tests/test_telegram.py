"""The Telegram door (targum-internal#328, slices 1 and 2), driven by recorded updates.

The updates below are the shapes the Bot API posts to a webhook — a voice note, a
forwarded text, a photo, a document, a command — trimmed to the fields that matter and
with the forward's sender kept in, because dropping it is one of the things tested.
Telegram itself is a stand-in: nothing here reaches the network.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from collections.abc import Callable
from http.client import HTTPConnection
from pathlib import Path
from typing import Any

import pytest

from targum import serve
from targum import telegram as telegram_module
from targum.accounts import Person, Store
from targum.serve import Library
from targum.telegram import Door, TooBig

PUBLIC = "https://targum.page"
HOST = "targum.page"
SECRET = "s3cret-webhook"
CHAT = 424242


class Stand:
    """Telegram, as the door sees it: what it was told, and the files it can hand over."""

    def __init__(self, files: dict[str, bytes] | None = None) -> None:
        self.sent: list[tuple[int, str]] = []
        #: Messages sent with a button: chat, text, the button's label and its data.
        self.offered: list[tuple[int, str, str, str]] = []
        #: Presses answered: the query's id and any toast.
        self.answered: list[tuple[str, str]] = []
        #: Messages said again: chat, message id, the new text.
        self.edited: list[tuple[int, int, str]] = []
        self.typed: list[int] = []
        self.fetched: list[str] = []
        self.files = files or {}

    def send(self, chat_id: int, text: str) -> None:
        self.sent.append((chat_id, text))

    def offer(self, chat_id: int, text: str, button: str, data: str) -> None:
        self.offered.append((chat_id, text, button, data))

    def answer(self, query_id: str, text: str = "") -> None:
        self.answered.append((query_id, text))

    def edit(self, chat_id: int, message_id: int, text: str) -> None:
        self.edited.append((chat_id, message_id, text))

    def typing(self, chat_id: int) -> None:
        self.typed.append(chat_id)

    def download(self, file_id: str, most: int) -> bytes:
        self.fetched.append(file_id)
        data = self.files[file_id]
        if len(data) > most:
            raise TooBig
        return data


# --- recorded updates --------------------------------------------------------------


def _message(update_id: int, chat: int = CHAT, **fields: Any) -> dict[str, Any]:
    return {
        "update_id": update_id,
        "message": {
            "message_id": update_id,
            "from": {
                "id": chat,
                "is_bot": False,
                "first_name": "Dana",
                "language_code": "en",
            },
            "chat": {"id": chat, "first_name": "Dana", "type": "private"},
            "date": 1790000000,
            **fields,
        },
    }


def command(update_id: int, text: str, chat: int = CHAT) -> dict[str, Any]:
    head = text.split(" ")[0]
    return _message(
        update_id,
        chat,
        text=text,
        entities=[{"offset": 0, "length": len(head), "type": "bot_command"}],
    )


def voice(update_id: int, file_id: str = "VOICE1", size: int = 9000) -> dict[str, Any]:
    return _message(
        update_id,
        voice={
            "duration": 300,
            "mime_type": "audio/ogg",
            "file_id": file_id,
            "file_unique_id": "AgAD" + file_id,
            "file_size": size,
        },
    )


FORWARDED_BY = "Moshe Hidden-Sender"
#: The forwarder's Telegram id. Long and odd on purpose: the test looks for it in a dump
#: of the whole database, and a short one ("777") turned up inside a random link token on
#: CI (2026-09-27), failing a test whose promise had been kept.
FORWARDER_ID = 5_318_008_271_139


def forwarded_text(update_id: int, text: str) -> dict[str, Any]:
    """A text forwarded from somebody else: their name rides in two places."""
    return _message(
        update_id,
        forward_origin={
            "type": "user",
            "sender_user": {"id": FORWARDER_ID, "is_bot": False, "first_name": FORWARDED_BY},
            "date": 1789990000,
        },
        forward_from={"id": FORWARDER_ID, "is_bot": False, "first_name": FORWARDED_BY},
        forward_date=1789990000,
        text=text,
    )


def document(update_id: int, name: str, size: int, file_id: str = "DOC1") -> dict[str, Any]:
    return _message(
        update_id,
        document={
            "file_name": name,
            "mime_type": "application/octet-stream",
            "file_id": file_id,
            "file_unique_id": "AgAD" + file_id,
            "file_size": size,
        },
    )


def link(update_id: int, url: str, chat: int = CHAT) -> dict[str, Any]:
    return _message(
        update_id, chat, text=url, entities=[{"offset": 0, "length": len(url), "type": "url"}]
    )


def pressed(update_id: int, data: str, chat: int = CHAT, message_id: int = 77) -> dict[str, Any]:
    """A press on a Build button, as the Bot API posts a `callback_query`."""
    return {
        "update_id": update_id,
        "callback_query": {
            "id": f"q{update_id}",
            "from": {"id": chat, "is_bot": False, "first_name": "Dana", "language_code": "en"},
            "message": {
                "message_id": message_id,
                "from": {"id": 1, "is_bot": True, "first_name": "targum"},
                "chat": {"id": chat, "first_name": "Dana", "type": "private"},
                "date": 1790000000,
                "text": "the quote",
            },
            "chat_instance": "-8123",
            "data": data,
        },
    }


ARTICLE = "https://www.haaretz.co.il/news/politics/2026-09-27/ty-article/abc"


def photo(update_id: int) -> dict[str, Any]:
    return _message(
        update_id,
        photo=[
            {"file_id": "SMALL", "file_unique_id": "a", "file_size": 900, "width": 90},
            {"file_id": "BIG", "file_unique_id": "b", "file_size": 90000, "width": 1280},
        ],
        caption=f"from {FORWARDED_BY}",
    )


# --- the world ---------------------------------------------------------------------


def signed_in(store: Store, email: str) -> Person:
    token = store.start_sign_in(email)
    signed = store.finish_sign_in(token)
    assert signed is not None
    return signed[0]


class World:
    def __init__(self, tmp_path: Path) -> None:
        self.store = Store(tmp_path / "targum.db")
        out = tmp_path / "out"
        out.mkdir()
        self.out = out
        self.library = Library(out, store=self.store)
        self.person = signed_in(self.store, "reader@example.com")
        self.telegram = Stand()
        self.door = Door(
            self.library,
            self.store,
            self.telegram,
            PUBLIC,
            "targum_bot",
            SECRET,
            run=lambda work: work(),
        )
        #: How long `prepare` says a recording is, in seconds.
        self.seconds = 300.0
        #: The title `prepare` finds for a link, and whether the link is a recording.
        self.title = "מה קרה השבוע בכנסת"
        self.link_audio = False

    def link(self, chat: int = CHAT) -> None:
        token = self.store.start_telegram_link(self.person.id)
        assert self.store.finish_telegram_link(token, chat) is not None

    def said(self) -> list[str]:
        return [text for _, text in self.telegram.sent]


@pytest.fixture
def world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> World:
    here = World(tmp_path)

    def priced(job: serve.Job) -> None:
        """What `Library.prepare` leaves on a job it could price, without the pipeline."""
        linked = job.source.startswith("https://")
        job.title = here.title if linked else Path(job.source).stem
        job.language = "he"
        job.segments = 4
        job.total = 4
        job.estimate = 0.0
        if (linked and here.link_audio) or Path(job.source).suffix in {".ogg", ".mp3", ".mp4"}:
            job.audio = True
            job.seconds = here.seconds
        job.stage = "ready"

    monkeypatch.setattr(here.library, "prepare", priced)
    return here


def uploads(world: World) -> list[Path]:
    root = world.library.home(world.person) / "uploads"
    return sorted(path for path in root.rglob("*") if path.is_file()) if root.is_dir() else []


# --- a stranger --------------------------------------------------------------------


def test_an_unlinked_chat_gets_one_reply_and_nothing_is_kept(world: World) -> None:
    world.telegram.files["VOICE1"] = b"ogg" * 100
    world.door.handle(voice(1))
    assert len(world.telegram.sent) == 1
    chat, text = world.telegram.sent[0]
    assert chat == CHAT
    assert f"{PUBLIC}/you" in text and "Link this chat to your targum account first" in text
    # Nothing fetched, nothing written, nothing built, nothing spent.
    assert world.telegram.fetched == []
    assert not [path for path in world.out.rglob("*") if path.is_file()]
    assert not world.library.jobs
    assert world.store.db.execute("SELECT COUNT(*) FROM job").fetchone()[0] == 0
    assert world.store.db.execute("SELECT COUNT(*) FROM telegram").fetchone()[0] == 0


def test_a_group_chat_is_not_answered(world: World) -> None:
    update = voice(1)
    update["message"]["chat"] = {"id": -100, "title": "Class", "type": "group"}
    world.door.handle(update)
    assert world.telegram.sent == []


def test_a_stranger_is_answered_in_the_language_their_app_is_in(world: World) -> None:
    update = voice(1)
    update["message"]["from"]["language_code"] = "ru"
    world.door.handle(update)
    assert "Сначала подключите" in world.said()[0]


# --- linking -----------------------------------------------------------------------


def test_the_deep_link_binds_the_chat_once(world: World) -> None:
    token = world.store.start_telegram_link(world.person.id)
    world.door.handle(command(1, f"/start {token}"))
    assert world.store.telegram_person(CHAT) == world.person
    assert "linked to your targum" in world.said()[0]
    # Single use: a second chat holding the same link gets nothing.
    world.door.handle(command(2, f"/start {token}", chat=CHAT + 1))
    assert world.store.telegram_person(CHAT + 1) is None
    assert "expired" in world.said()[1]


def test_a_sign_in_link_cannot_bind_a_chat_and_a_telegram_link_cannot_sign_in(
    world: World,
) -> None:
    store = world.store
    signing = store.start_sign_in("other@example.com")
    binding = store.start_telegram_link(world.person.id)
    assert store.finish_telegram_link(signing, CHAT) is None
    assert store.telegram_person(CHAT) is None
    assert store.peek_sign_in(binding) is None
    assert store.finish_sign_in(binding) is None
    # Neither refusal spent the other: each still does its own job.
    assert store.finish_sign_in(signing) is not None
    assert store.finish_telegram_link(binding, CHAT) == world.person


def test_minting_one_purpose_leaves_the_other_alone(world: World) -> None:
    store = world.store
    binding = store.start_telegram_link(world.person.id)
    signing = store.start_sign_in(world.person.email)
    assert store.finish_telegram_link(binding, CHAT) is not None
    fresh = store.start_telegram_link(world.person.id)
    assert store.finish_sign_in(signing) is not None
    assert fresh


def test_a_link_row_from_before_the_purpose_column_is_a_sign_in_link(tmp_path: Path) -> None:
    path = tmp_path / "old.db"
    old = sqlite3.connect(path)
    old.execute(
        "CREATE TABLE link (hash TEXT PRIMARY KEY, person INTEGER NOT NULL,"
        " made INTEGER NOT NULL, used INTEGER)"
    )
    old.execute("INSERT INTO link VALUES ('h', 1, 0, NULL)")
    old.commit()
    old.close()
    store = Store(path)
    row = store.db.execute("SELECT purpose FROM link WHERE hash = 'h'").fetchone()
    assert row["purpose"] == "sign-in"


def test_stop_unlinks_and_the_chat_is_a_stranger_again(world: World) -> None:
    world.link()
    world.door.handle(command(1, "/stop"))
    assert world.store.telegram_person(CHAT) is None
    assert "Unlinked" in world.said()[0]
    world.door.handle(voice(2))
    assert "Link this chat to your targum account first" in world.said()[1]
    assert world.telegram.fetched == []


def test_closing_the_account_unbinds_every_chat(world: World) -> None:
    world.link()
    world.link(CHAT + 1)
    world.store.forget(world.person)
    assert world.store.telegram_person(CHAT) is None
    assert world.store.telegram_chats(world.person.id) == []


# --- what a linked chat sends ------------------------------------------------------


def test_a_short_voice_note_builds_on_send_through_the_same_job_path(world: World) -> None:
    world.link()
    world.telegram.files["VOICE1"] = b"OggS" + b"\0" * 400
    world.door.handle(voice(1))
    [job] = world.library.jobs.values()
    assert job.owner == world.person.id and job.kind == "build"
    assert job.stage == "queued", "claimed and queued, as a press on /build is"
    assert job.options == {"to": "en", "from": "he", "words": True, "gloss": False}
    # A job row the rails see, with its length counted against the month.
    row = world.store.db.execute("SELECT owner, length FROM job WHERE id = ?", (job.id,)).fetchone()
    assert row["owner"] == world.person.id and row["length"] == pytest.approx(300.0)
    # Kept where the Add page keeps a recording, and nowhere else.
    [kept] = [path for path in uploads(world) if not path.name.startswith(".")]
    assert kept.read_bytes() == world.telegram.files["VOICE1"]
    assert kept.suffix == ".ogg"
    assert world.said() == [
        "Thanks. We're getting it ready, and it'll be in Your targums. "
        f"Follow it here: {PUBLIC}/build/{job.id}"
    ]


def test_a_recording_over_ten_minutes_asks_before_it_builds(world: World) -> None:
    world.link()
    world.seconds = 11 * 60 + 5
    world.telegram.files["VOICE1"] = b"OggS" + b"\0" * 400
    world.door.handle(voice(1))
    [job] = world.library.jobs.values()
    assert job.stage == "ready", "quoted, not claimed"
    assert world.library.queue.empty()
    assert world.store.db.execute("SELECT length FROM job WHERE id = ?", (job.id,)).fetchone()[
        "length"
    ] in (None, 0, 0.0)
    # The same button a link gets, and its press is what starts it.
    assert world.said() == []
    [(chat, text, button, data)] = world.telegram.offered
    assert (chat, text, button) == (CHAT, "Voice note. It uses 12 credits.", "Open this")
    world.door.handle(pressed(2, data))
    assert job.stage == "queued"
    assert world.store.db.execute("SELECT length FROM job WHERE id = ?", (job.id,)).fetchone()[
        "length"
    ] == pytest.approx(11 * 60 + 5)


def test_a_refusal_comes_back_in_the_claims_own_words(world: World) -> None:
    world.link()
    world.library.upload_seconds = 60.0
    world.telegram.files["VOICE1"] = b"OggS" + b"\0" * 400
    world.door.handle(voice(1))
    [job] = world.library.jobs.values()
    assert job.stage == "blocked" and job.blocked
    assert world.said() == [f"{job.blocked} {PUBLIC}/you"]
    assert world.library.queue.empty()


def test_a_forward_keeps_its_content_and_never_its_sender(world: World) -> None:
    world.link()
    text = "שלום עולם. זה טקסט קצר על הבוקר."
    world.door.handle(forwarded_text(1, text))
    [job] = world.library.jobs.values()
    assert job.stage == "queued"
    [kept] = uploads(world)
    assert kept.read_text(encoding="utf-8") == text
    assert kept.name == "שלום עולם.txt", "titled as the Add page titles a paste"
    # Nowhere on disk and nowhere in the database.
    for path in world.out.rglob("*"):
        if path.is_file():
            assert FORWARDED_BY not in path.read_bytes().decode("utf-8", "replace")
    dump = "\n".join(world.store.db.iterdump())
    assert FORWARDED_BY not in dump, "the forwarder's name is never kept"
    assert str(FORWARDER_ID) not in dump, "nor their id"


def test_a_photo_is_read_as_a_page_and_its_caption_is_not_kept(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    from targum import vision

    monkeypatch.setattr(vision, "probe", lambda path: (1280, 960))
    world.link()
    world.telegram.files["BIG"] = b"\xff\xd8jpeg"
    world.door.handle(photo(1))
    assert world.telegram.fetched == ["BIG"], "the largest size Telegram made"
    [job] = world.library.jobs.values()
    folder = Path(job.source)
    assert folder.is_dir() and [path.name for path in folder.iterdir()] == ["01-Picture.jpg"]
    dump = "\n".join(world.store.db.iterdump())
    assert FORWARDED_BY not in dump


def test_a_file_over_twenty_megabytes_is_refused_by_name(world: World) -> None:
    world.link()
    world.door.handle(document(1, "lecture.mp3", 25 * 1024 * 1024))
    assert world.telegram.fetched == []
    assert world.said() == [
        "lecture.mp3 is over 20 MB, and Telegram won't hand us anything bigger. "
        f"Send it on {PUBLIC}/add."
    ]
    assert not world.library.jobs


def test_a_file_that_turns_out_too_big_is_refused_the_same_way(world: World) -> None:
    world.link()
    world.telegram.files["DOC1"] = b"x" * (telegram_module.MOST_BYTES + 1)
    world.door.handle(document(1, "talk.mp3", 0))
    assert "talk.mp3 is over 20 MB" in world.said()[0]
    assert not world.library.jobs and not uploads(world)


# --- a link, and its Build button (slice 2) ----------------------------------------


def _claims(world: World, monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Every `Library.claim`, by job id, still doing what it does."""
    claimed: list[str] = []
    real = world.library.claim

    def counting(job: serve.Job) -> str:
        claimed.append(job.id)
        return real(job)

    monkeypatch.setattr(world.library, "claim", counting)
    return claimed


def test_a_link_is_quoted_with_a_build_button_and_nothing_is_spent(world: World) -> None:
    world.link()
    world.door.handle(link(1, ARTICLE))
    [job] = world.library.jobs.values()
    assert job.source == ARTICLE and job.options["source"] == ARTICLE
    assert job.owner == world.person.id and job.stage == "ready", "priced, not pressed"
    assert world.library.queue.empty() and world.said() == []
    row = world.store.db.execute("SELECT claimed, length FROM job WHERE id = ?", (job.id,))
    assert tuple(row.fetchone()) in {(None, None), (0, 0), (0.0, 0.0)}
    [(chat, text, button, data)] = world.telegram.offered
    assert chat == CHAT and button == "Open this"
    assert text == "מה קרה השבוע בכנסת. It's a text, so it uses none of your credits."
    # Telegram's limit, and nothing in it a stranger could make for themselves.
    assert data.startswith("b:") and len(data.encode()) <= 64


def test_a_recording_behind_a_link_is_quoted_in_credits(world: World) -> None:
    world.link()
    world.link_audio = True
    world.seconds = 61.0
    world.door.handle(link(1, "https://example.org/episode.mp3"))
    [(_, text, _, _)] = world.telegram.offered
    assert text == "מה קרה השבוע בכנסת. It uses 2 credits."
    assert "$" not in text


def test_a_link_without_its_scheme_is_still_a_link(world: World) -> None:
    world.link()
    world.door.handle(_message(1, text="www.ynet.co.il/news/article/abc"))
    [job] = world.library.jobs.values()
    assert job.source == "https://www.ynet.co.il/news/article/abc"
    assert len(world.telegram.offered) == 1


def test_the_press_claims_once_through_library_press(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The press is `Library.press` — the road `/build` takes — and so one claim."""
    world.link()
    world.link_audio = True
    world.door.handle(link(1, ARTICLE))
    [job] = world.library.jobs.values()
    [(_, quote, _, data)] = world.telegram.offered
    claimed = _claims(world, monkeypatch)
    presses: list[str] = []
    real_press = world.library.press

    def spying(pressed_job: serve.Job) -> str:
        presses.append(pressed_job.id)
        return real_press(pressed_job)

    monkeypatch.setattr(world.library, "press", spying)
    world.door.handle(pressed(2, data))
    assert presses == [job.id] and claimed == [job.id]
    assert job.stage == "queued" and world.library.queue.qsize() == 1
    row = world.store.db.execute("SELECT length FROM job WHERE id = ?", (job.id,)).fetchone()
    assert row["length"] == pytest.approx(300.0), "counted against the month, as /build counts"
    assert world.telegram.answered == [("q2", "")]
    # The quote is said again with the way to it, and its button is gone.
    started = (
        "Thanks. We're getting it ready, and it'll be in Your targums. "
        f"Follow it here: {PUBLIC}/build/{job.id}"
    )
    assert world.telegram.edited == [(CHAT, 77, f"{quote}\n{started}")]


def test_a_second_press_is_heard_and_changes_nothing(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    world.link()
    world.door.handle(link(1, ARTICLE))
    [job] = world.library.jobs.values()
    [(_, _, _, data)] = world.telegram.offered
    claimed = _claims(world, monkeypatch)
    world.door.handle(pressed(2, data))
    world.door.handle(pressed(3, data))
    assert claimed == [job.id] and world.library.queue.qsize() == 1
    assert world.telegram.answered == [("q2", ""), ("q3", "We're already getting it ready.")]
    assert len(world.telegram.edited) == 1 and world.said() == []


def test_two_presses_at_once_claim_once(world: World, monkeypatch: pytest.MonkeyPatch) -> None:
    world.link()
    world.door.handle(link(1, ARTICLE))
    [job] = world.library.jobs.values()
    [(_, _, _, data)] = world.telegram.offered
    claimed = _claims(world, monkeypatch)
    threads = [
        threading.Thread(target=world.door.handle, args=(pressed(10 + n, data),)) for n in range(4)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert claimed == [job.id] and world.library.queue.qsize() == 1


def test_a_stranger_cannot_press_somebody_elses_button(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    world.link()
    world.door.handle(link(1, ARTICLE))
    [job] = world.library.jobs.values()
    [(_, _, _, data)] = world.telegram.offered
    claimed = _claims(world, monkeypatch)
    # Another reader's chat, holding the very same data.
    other = signed_in(world.store, "other@example.com")
    token = world.store.start_telegram_link(other.id)
    assert world.store.finish_telegram_link(token, CHAT + 1) is not None
    world.door.handle(pressed(2, data, chat=CHAT + 1))
    # A chat with no account behind it.
    world.door.handle(pressed(3, data, chat=CHAT + 2))
    # The job id alone, or with a seal made up.
    world.door.handle(pressed(4, f"b:{job.id}"))
    world.door.handle(pressed(5, f"b:{job.id}:AAAAAAAAAAAAAAAAAAAAAA"))
    assert claimed == [] and job.stage == "ready" and world.library.queue.empty()
    stale = "That button doesn't work any more. Send it to us again."
    assert world.telegram.sent == [
        (CHAT + 1, stale),
        (CHAT + 2, f"Link this chat to your targum account first: {PUBLIC}/you"),
        (CHAT, stale),
        (CHAT, stale),
    ]
    assert [query for query, _ in world.telegram.answered] == ["q2", "q3", "q4", "q5"]


def test_a_chat_linked_to_somebody_else_since_cannot_press_its_old_quotes(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    world.link()
    world.door.handle(link(1, ARTICLE))
    [(_, _, _, data)] = world.telegram.offered
    world.door.handle(command(2, "/stop"))
    other = signed_in(world.store, "other@example.com")
    token = world.store.start_telegram_link(other.id)
    assert world.store.finish_telegram_link(token, CHAT) is not None
    claimed = _claims(world, monkeypatch)
    world.door.handle(pressed(3, data))
    assert claimed == []
    assert world.said()[-1] == "That button doesn't work any more. Send it to us again."


def test_a_press_on_a_quote_that_is_gone_is_refused_politely(world: World) -> None:
    world.link()
    world.door.handle(link(1, ARTICLE))
    [(_, _, _, data)] = world.telegram.offered
    world.library.jobs = {}
    world.door.handle(pressed(2, data))
    assert world.said() == ["That button doesn't work any more. Send it to us again."]
    assert world.telegram.answered == [("q2", "")]


def test_a_press_the_rails_refuse_says_so_and_keeps_its_button(world: World) -> None:
    world.link()
    world.link_audio = True
    world.library.upload_seconds = 60.0
    world.door.handle(link(1, ARTICLE))
    [job] = world.library.jobs.values()
    [(_, _, _, data)] = world.telegram.offered
    world.door.handle(pressed(2, data))
    assert job.stage == "blocked" and job.blocked
    assert world.said() == [f"{job.blocked} {PUBLIC}/you"]
    assert world.telegram.edited == [] and world.library.queue.empty()


def _add_says(world: World, url: str) -> str:
    """What the Add page's `/prepare` hands back for a pasted link: `Library.prepare`
    on a job of its own."""
    job = serve.Job(id="addpage0addpage0", source=url, options={"source": url})
    Library.prepare(world.library, job)
    assert job.stage == "failed"
    return job.error


@pytest.mark.parametrize(
    "url",
    [
        "https://vimeo.com/76979871",
        "https://x.com/someone/status/1790000000000000000",
    ],
)
def test_a_link_the_add_page_refuses_is_refused_in_the_same_words(
    world: World, monkeypatch: pytest.MonkeyPatch, url: str
) -> None:
    monkeypatch.delenv("TARGUM_X", raising=False)
    monkeypatch.delattr(world.library, "prepare")
    world.link()
    world.door.handle(link(1, url))
    expected = _add_says(world, url)
    assert expected and world.said() == [expected]
    assert world.telegram.offered == []
    assert all(job.stage == "failed" for job in world.library.jobs.values())


def test_a_link_with_no_address_is_not_fetched(world: World) -> None:
    world.link()
    world.door.handle(_message(1, text="https://"))
    assert world.said() == [f"We can't fetch that link. Check it, or paste it on {PUBLIC}/add."]
    assert not world.library.jobs


def test_a_link_is_quoted_in_the_accounts_language(world: World) -> None:
    world.store.choose(world.person, "reading", ["ru"])
    world.link()
    world.link_audio = True
    world.seconds = 5 * 60
    world.door.handle(link(1, ARTICLE))
    [(_, text, button, _)] = world.telegram.offered
    assert text.endswith("Займёт 5 кредитов.") and button == "Подготовить"


def test_the_bot_api_sends_the_button_as_telegram_reads_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import httpx

    posted: list[tuple[str, dict[str, Any]]] = []

    class Answer:
        def json(self) -> dict[str, Any]:
            return {"ok": True, "result": True}

    def post(url: str, json: dict[str, Any], timeout: float) -> Answer:
        posted.append((url.rsplit("/", 1)[1], json))
        return Answer()

    monkeypatch.setattr(httpx, "post", post)
    api = telegram_module.BotApi("1:not-a-real-token")
    api.offer(CHAT, "A quote.", "Build", "b:0123456789abcdef:seal")
    api.answer("q1")
    api.edit(CHAT, 77, "Said again.")
    assert posted[0] == (
        "sendMessage",
        {
            "chat_id": CHAT,
            "text": "A quote.",
            "link_preview_options": {"is_disabled": True},
            "reply_markup": {
                "inline_keyboard": [[{"text": "Build", "callback_data": "b:0123456789abcdef:seal"}]]
            },
        },
    )
    assert posted[1] == ("answerCallbackQuery", {"callback_query_id": "q1"})
    assert posted[2][0] == "editMessageText" and "reply_markup" not in posted[2][1]


def test_a_file_targum_cannot_read_is_said_so(world: World) -> None:
    world.link()
    world.door.handle(document(1, "sheet.xlsx", 1000))
    assert world.said()[0].startswith("We can't read that kind of message.")
    assert world.telegram.fetched == [] and not world.library.jobs


def test_a_linked_chat_is_answered_in_the_accounts_language(world: World) -> None:
    world.store.choose(world.person, "reading", ["ru"])
    world.link()
    world.door.handle(command(1, "/help"))
    assert world.said()[0].startswith("Пришлите нам")


def test_an_update_telegram_sends_twice_is_answered_once(world: World) -> None:
    world.link()
    update = forwarded_text(7, "שלום לכולם.")
    world.door.accept(update)
    world.door.accept(update)
    assert len(world.library.jobs) == 1 and len(world.telegram.sent) == 1


def test_the_secret_is_compared_and_never_empty() -> None:
    assert telegram_module.authentic(SECRET, SECRET)
    assert not telegram_module.authentic("wrong", SECRET)
    assert not telegram_module.authentic(None, SECRET)
    assert not telegram_module.authentic("", "")


def test_dark_without_all_three_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("TARGUM_TELEGRAM_TOKEN", "TARGUM_TELEGRAM_SECRET", "TARGUM_TELEGRAM_BOT"):
        monkeypatch.delenv(name, raising=False)
    assert telegram_module.configured() is None
    monkeypatch.setenv("TARGUM_TELEGRAM_TOKEN", "1:abc")
    monkeypatch.setenv("TARGUM_TELEGRAM_SECRET", SECRET)
    assert telegram_module.configured() is None
    monkeypatch.setenv("TARGUM_TELEGRAM_BOT", "@targum_bot")
    assert telegram_module.configured() == ("1:abc", SECRET, "targum_bot")


# --- through a real server ---------------------------------------------------------


def _serve(tmp: Path, port: int) -> tuple[Store, str]:
    store_path = tmp / "targum.db"
    store = Store(store_path)
    signed = store.finish_sign_in(store.start_sign_in("reader@example.com"))
    assert signed is not None
    threading.Thread(
        target=lambda: serve.start(
            out=tmp / "out",
            port=port,
            open_browser=False,
            store=store_path,
            require_account=True,
            public_address=PUBLIC,
        ),
        daemon=True,
    ).start()
    for _ in range(100):
        try:
            probe = HTTPConnection("127.0.0.1", port, timeout=1)
            probe.request("GET", "/health")
            probe.getresponse().read()
            probe.close()
            break
        except OSError:
            time.sleep(0.1)
    return store, signed[1]


def request(
    port: int,
    method: str,
    path: str,
    body: bytes = b"",
    headers: dict[str, str] | None = None,
    session: str = "",
) -> tuple[int, bytes]:
    conn = HTTPConnection("127.0.0.1", port, timeout=5)
    conn.putrequest(method, path, skip_host=True)
    conn.putheader("Host", HOST)
    conn.putheader("Content-Type", "application/json")
    conn.putheader("Content-Length", str(len(body)))
    if session:
        conn.putheader("Cookie", f"targum_session={session}")
    for name, value in (headers or {}).items():
        conn.putheader(name, value)
    conn.endheaders()
    conn.send(body)
    response = conn.getresponse()
    got = response.read()
    conn.close()
    return response.status, got


SETTINGS = {
    "TARGUM_TELEGRAM_TOKEN": "1:not-a-real-token",
    "TARGUM_TELEGRAM_SECRET": SECRET,
    "TARGUM_TELEGRAM_BOT": "targum_bot",
}


@pytest.fixture(scope="module")
def armed(
    tmp_path_factory: pytest.TempPathFactory, free_port: Callable[[], int]
) -> tuple[int, str, Stand]:
    """A hosted server with a bot, whose Telegram is a stand-in."""
    stand = Stand()
    real = telegram_module.BotApi
    telegram_module.BotApi = lambda token, timeout=60.0: stand  # type: ignore[assignment,misc]
    saved = {name: os.environ.get(name) for name in SETTINGS}
    os.environ.update(SETTINGS)
    try:
        port = free_port()
        _, session = _serve(tmp_path_factory.mktemp("armed"), port)
    finally:
        # Read once, at start-up: the server holds its door, and nothing else in the
        # suite should find a bot in the environment.
        telegram_module.BotApi = real  # type: ignore[misc]
        for name, value in saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
    return port, session, stand


def _wait_for(stand: Stand, count: int) -> None:
    for _ in range(100):
        if len(stand.sent) >= count:
            return
        time.sleep(0.05)


def test_the_webhook_is_a_404_without_the_secret(armed: tuple[int, str, Stand]) -> None:
    port, _, stand = armed
    body = json.dumps(voice(1)).encode()
    assert request(port, "POST", telegram_module.HOOK, body)[0] == 404
    wrong = {telegram_module.SECRET_HEADER: "guess"}
    assert request(port, "POST", telegram_module.HOOK, body, wrong)[0] == 404
    time.sleep(0.2)
    assert stand.sent == []


def test_the_webhook_answers_telegram_and_the_bot_replies(
    armed: tuple[int, str, Stand],
) -> None:
    port, _, stand = armed
    right = {telegram_module.SECRET_HEADER: SECRET}
    before = len(stand.sent)
    status, _ = request(port, "POST", telegram_module.HOOK, json.dumps(voice(90)).encode(), right)
    assert status == 200
    _wait_for(stand, before + 1)
    assert "Link this chat to your targum account first" in stand.sent[before][1]


def test_account_hands_over_a_link_and_takes_a_chat_back(
    armed: tuple[int, str, Stand],
) -> None:
    port, session, stand = armed
    status, body = request(port, "GET", "/account/me", session=session)
    assert status == 200 and json.loads(body)["telegram"] == {"chats": []}
    status, body = request(port, "POST", "/account/telegram", b"{}", session=session)
    link = json.loads(body)["link"]
    assert status == 200 and link.startswith("https://t.me/targum_bot?start=")
    token = link.split("start=")[1]
    right = {telegram_module.SECRET_HEADER: SECRET}
    before = len(stand.sent)
    request(
        port,
        "POST",
        telegram_module.HOOK,
        json.dumps(command(91, f"/start {token}", chat=5150)).encode(),
        right,
    )
    _wait_for(stand, before + 1)
    assert "linked to your targum" in stand.sent[before][1]
    _, body = request(port, "GET", "/account/me", session=session)
    [chat] = json.loads(body)["telegram"]["chats"]
    assert chat["chat"] == 5150
    status, body = request(
        port, "POST", "/account/telegram", json.dumps({"unlink": 5150}).encode(), session=session
    )
    assert status == 200 and json.loads(body) == {"unlinked": 1, "chats": []}
    # Signed out, nothing.
    assert request(port, "POST", "/account/telegram", b"{}")[0] == 401


def test_without_a_bot_every_door_is_shut(
    tmp_path_factory: pytest.TempPathFactory,
    free_port: Callable[[], int],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in SETTINGS:
        monkeypatch.delenv(name, raising=False)
    port = free_port()
    _, session = _serve(tmp_path_factory.mktemp("dark"), port)
    right = {telegram_module.SECRET_HEADER: SECRET}
    assert request(port, "POST", telegram_module.HOOK, b"{}", right)[0] == 404
    _, body = request(port, "GET", "/account/me", session=session)
    assert "telegram" not in json.loads(body)
    assert request(port, "POST", "/account/telegram", b"{}", session=session)[0] == 404


def test_a_press_through_the_webhook_is_answered(armed: tuple[int, str, Stand]) -> None:
    port, _, stand = armed
    right = {telegram_module.SECRET_HEADER: SECRET}
    before = len(stand.sent)
    update = pressed(92, "b:0123456789abcdef:seal", chat=6160)
    status, _ = request(port, "POST", telegram_module.HOOK, json.dumps(update).encode(), right)
    assert status == 200
    _wait_for(stand, before + 1)
    assert "Link this chat to your targum account first" in stand.sent[before][1]
    assert ("q92", "") in stand.answered


def test_library_press_never_puts_a_job_in_line_twice(world: World) -> None:
    """The road every button shares: `/build`, `/build/<id>` and the Build button. A job
    already in line is left there, where a second `enqueue` would have built it twice."""
    world.link()
    world.door.handle(link(1, ARTICLE))
    [job] = world.library.jobs.values()
    assert world.library.press(job) == ""
    assert world.library.press(job) == ""
    assert job.stage == "queued" and world.library.queue.qsize() == 1
