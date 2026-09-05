"""A reader's build offered to the shelf — the one place the licence bites.

Import is not gated on licence; promotion is. These tests hold both halves: what may
never be proposed, what a person must decide, what the machine may decide alone, and
that accepting touches exactly the catalogue file and the shared cache and nothing of
the reader's.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from targum import catalogue, promote
from targum.accounts import Store
from targum.errors import TargumError
from targum.serve import Job, Library

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "catalogue.json"


@pytest.fixture
def shelf(tmp_path: Path, monkeypatch: Any):
    """A writable copy of the fixture catalogue, put back when the test is done."""
    copy = tmp_path / "catalogue.json"
    shutil.copy(FIXTURE, copy)
    monkeypatch.setenv("TARGUM_CATALOGUE", str(copy))
    before = list(catalogue.CATALOGUE)
    collections = list(catalogue.COLLECTIONS)
    yield copy
    catalogue.CATALOGUE[:] = before
    catalogue.COLLECTIONS[:] = collections


def built(home: Path, name: str, source: str, *, licence: str = "", words: int = 30) -> Path:
    folder = home / name
    (folder / "reader").mkdir(parents=True)
    (folder / "reader" / "index.html").write_text("<html></html>", encoding="utf-8")
    (folder / "document.json").write_text(
        json.dumps(
            {
                "schema_version": 4,
                "source": source,
                "title": "מאמר",
                "author": "פלוני",
                "language": "he",
                "blocks": [
                    {
                        "id": "b0000",
                        "kind": "paragraph",
                        "level": 0,
                        "text": " ".join(["מילה"] * words),
                    }
                ],
                "content_hash": "h",
                "source_hash": "s",
                "ingester": "test",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    if licence:
        (folder / "audio.json").write_text(json.dumps({"licence": licence}), encoding="utf-8")
    return folder


def finished(library: Library, home: Path, name: str, source: str, owner: int | None = 1) -> Job:
    return Job(
        id=f"j-{name}",
        source=source,
        owner=owner,
        home=home,
        stage="done",
        reader=f"{name}/reader/index.html",
    )


@pytest.fixture
def world(tmp_path: Path):
    store = Store(tmp_path / "db")
    out = tmp_path / "out"
    out.mkdir()
    library = Library(out, store=store)
    home = out / "p1"
    return library, store, home


def test_unknown_is_never_a_candidate(world, shelf) -> None:
    library, store, home = world
    built(home, "art-he", "https://news.example/a")  # no licence anywhere
    assert (
        promote.candidate(
            library, store, finished(library, home, "art-he", "https://news.example/a")
        )
        is None
    )
    assert store.proposals() == []


def test_noncommercial_is_a_candidate_for_nothing(world, shelf) -> None:
    library, store, home = world
    built(home, "vid-he", "https://www.youtube.com/watch?v=x", licence="CC BY-NC 4.0")
    assert (
        promote.candidate(
            library, store, finished(library, home, "vid-he", "https://www.youtube.com/watch?v=x")
        )
        is None
    )


def test_an_upload_and_a_conversation_are_never_proposed(world, shelf) -> None:
    library, store, home = world
    built(home, "up-he", str(home / "imports" / "file.txt"), licence="CC0")
    assert (
        promote.candidate(
            library, store, finished(library, home, "up-he", str(home / "imports" / "file.txt"))
        )
        is None
    )
    built(home, "talk-he", str(home / "chats" / "abc.chat"), licence="CC0")
    assert (
        promote.candidate(
            library,
            store,
            finished(library, home, "talk-he", str(home / "chats" / "abc.chat")),
        )
        is None
    )


def test_a_text_already_in_the_library_is_not_proposed_again(world, shelf) -> None:
    library, store, home = world
    built(home, "ruth-he", "test:ruth", licence="Public Domain")
    assert (
        promote.candidate(library, store, finished(library, home, "ruth-he", "test:ruth")) is None
    )


def test_by_sa_is_proposed_for_a_person_and_reaches_both(world, shelf) -> None:
    """ShareAlike sells and cannot be kept: catalogue yes, corpus yes, and a person
    decides because the credit is theirs to write."""
    library, store, home = world
    built(home, "vid-he", "https://www.youtube.com/watch?v=y", licence="CC BY-SA 4.0")
    got = promote.candidate(
        library, store, finished(library, home, "vid-he", "https://www.youtube.com/watch?v=y")
    )
    assert got is not None and got.catalogue_ok and got.corpus_ok and got.standing == "owed"
    assert got.kind == "article" and got.register == "modern" and got.words == 30
    waiting = store.proposals()
    assert [row["id"] for row in waiting] == [got.id] and waiting[0]["state"] == "proposed"
    assert catalogue.by_id("vid-he") is None, "nothing joined the shelf without a press"


def test_accepting_needs_a_credit_for_owed_and_then_merges_and_warms(
    world, shelf, monkeypatch: Any
) -> None:
    library, store, home = world
    folder = built(home, "vid-he", "https://www.youtube.com/watch?v=y", licence="CC BY 4.0")
    got = promote.candidate(
        library, store, finished(library, home, "vid-he", "https://www.youtube.com/watch?v=y")
    )
    assert got is not None
    warmed: list[Path] = []
    monkeypatch.setattr(promote, "warm_folder", lambda f, cache, model=None: warmed.append(f) or 3)

    with pytest.raises(TargumError, match="credit"):
        promote.accept(library, store, got.id)
    assert catalogue.by_id("vid-he") is None

    answer = promote.accept(
        library, store, got.id, credit="Kan, CC BY 4.0", register="modern", kind="talk"
    )
    assert answer == {"entry": "vid-he", "warmed": 3, "corpus": True}
    assert warmed == [folder], "the reader's own folder is what is warmed — nothing moved"
    entry = catalogue.by_id("vid-he")
    assert entry is not None and entry.licence == "CC BY 4.0" and entry.credit == "Kan, CC BY 4.0"
    assert entry.kind.value == "talk" and entry.register.value == "modern" and entry.words == 30
    written = json.loads(shelf.read_text(encoding="utf-8"))
    assert any(row["id"] == "vid-he" for row in written["entries"]), "the file, not just the list"
    assert (folder / "document.json").is_file() and (folder / "reader" / "index.html").is_file()
    assert (
        store.proposal(got.id)["state"] == "accepted" and store.proposal(got.id)["by"] == "person"
    )
    with pytest.raises(TargumError):
        promote.accept(library, store, got.id, credit="x"), "decided once"


def test_a_public_domain_fetcher_promotes_itself_and_says_who(
    world, shelf, monkeypatch: Any
) -> None:
    library, store, home = world
    monkeypatch.setattr(promote, "warm_folder", lambda f, cache, model=None: 1)
    built(home, "hazon-he", "wikisource:חזון")
    got = promote.candidate(library, store, finished(library, home, "hazon-he", "wikisource:חזון"))
    assert got is not None and got.licence == "Public Domain" and got.standing == "free"
    assert (
        store.proposal(got.id)["state"] == "accepted" and store.proposal(got.id)["by"] == "machine"
    )
    assert catalogue.by_id("hazon-he") is not None


def test_declining_is_final_and_touches_nothing(world, shelf) -> None:
    library, store, home = world
    built(home, "vid-he", "https://www.youtube.com/watch?v=y", licence="CC BY 4.0")
    got = promote.candidate(
        library, store, finished(library, home, "vid-he", "https://www.youtube.com/watch?v=y")
    )
    assert got is not None
    promote.decline(store, got.id)
    assert store.proposal(got.id)["state"] == "declined" and store.proposals() == []
    with pytest.raises(TargumError):
        promote.accept(library, store, got.id, credit="x")


def test_accepting_never_touches_the_reader_s_ledger(world, shelf, monkeypatch: Any) -> None:
    library, store, home = world
    person, _ = store.finish_sign_in(store.start_sign_in("reader@example.com"))  # type: ignore[misc]
    store.push(
        person,
        {
            "words": [
                {"language": "he", "lemma": "מילה", "status": 9, "band": "easy", "at": 1, "seen": 1}
            ]
        },
    )
    monkeypatch.setattr(promote, "warm_folder", lambda f, cache, model=None: 0)
    built(home, "vid-he", "https://www.youtube.com/watch?v=y", licence="CC0")
    got = promote.candidate(
        library,
        store,
        finished(library, home, "vid-he", "https://www.youtube.com/watch?v=y", owner=person.id),
    )
    assert got is not None
    promote.accept(library, store, got.id)
    assert store.marked(person, "he") == {"מילה": 9}
    assert store.counts(person)["words"] == 1


def test_warming_an_empty_folder_writes_nothing(tmp_path: Path) -> None:
    from targum.cache import Cache

    assert promote.warm_folder(tmp_path, Cache(tmp_path / "cache")) == 0


def test_a_finished_build_offers_itself_and_a_failure_there_never_fails_the_build(
    world, shelf, monkeypatch: Any
) -> None:
    library, store, home = world
    seen: list[str] = []
    monkeypatch.setattr(promote, "candidate", lambda lib, st, job: seen.append(job.id))
    job = finished(library, home, "vid-he", "https://x")
    library.propose(job)
    assert seen == ["j-vid-he"]

    def boom(*_: Any) -> None:
        raise RuntimeError("shelf trouble")

    monkeypatch.setattr(promote, "candidate", boom)
    library.propose(job)  # printed, not raised
    assert job.stage == "done"


def test_the_shelf_counts_what_was_wanted(world) -> None:
    library, store, home = world
    store.want("קישוט", "")
    store.want("קישוט", "")
    store.want("", "https://news.example/a", "unknown")
    rows = store.wanted()
    assert rows[0]["query"] == "קישוט" and rows[0]["count"] == 2
    assert rows[1]["source"] == "https://news.example/a" and rows[1]["standing"] == "unknown"
    store.want("", "")  # nothing is not an ask
    assert len(store.wanted()) == 2


def test_the_back_office_decides_and_a_stranger_cannot(world, shelf, monkeypatch: Any) -> None:
    """The route is the page's own door: an admin session, and 404 for anyone else."""
    import threading
    from http.client import HTTPConnection
    from http.server import ThreadingHTTPServer
    from urllib.parse import urlencode

    from targum.mail import ConsoleMailer
    from targum.serve import Handler

    library, store, home = world
    monkeypatch.setattr(promote, "warm_folder", lambda f, cache, model=None: 0)
    built(home, "vid-he", "https://www.youtube.com/watch?v=y", licence="CC BY 4.0")
    got = promote.candidate(
        library, store, finished(library, home, "vid-he", "https://www.youtube.com/watch?v=y")
    )
    assert got is not None

    admin, admin_session = store.finish_sign_in(store.start_sign_in("owner@example.com"))  # type: ignore[misc]
    store.make_admin("owner@example.com")
    _, reader_session = store.finish_sign_in(store.start_sign_in("reader@example.com"))  # type: ignore[misc]

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    handler = type(
        "BackOfficeHandler",
        (Handler,),
        {
            "library": library,
            "token": "k",
            "page": "<html></html>",
            "store": store,
            "mailer": ConsoleMailer(),
            "address": f"http://127.0.0.1:{port}",
        },
    )
    server.RequestHandlerClass = handler
    threading.Thread(target=server.serve_forever, daemon=True).start()

    def post(session: str, form: dict[str, str]) -> tuple[int, str]:
        connection = HTTPConnection("127.0.0.1", port, timeout=5)
        connection.request(
            "POST",
            "/back-office/promote",
            body=urlencode(form),
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Cookie": f"targum_session={session}",
            },
        )
        response = connection.getresponse()
        response.read()
        connection.close()
        return response.status, response.getheader("Location") or ""

    try:
        assert post(reader_session, {"id": got.id, "action": "accept"})[0] == 404
        assert store.proposal(got.id)["state"] == "proposed"
        status, where = post(admin_session, {"id": got.id, "action": "accept"})
        assert status == 303 and "said=" in where, "owed with no credit is sent back with why"
        assert store.proposal(got.id)["state"] == "proposed"
        status, where = post(
            admin_session, {"id": got.id, "action": "accept", "credit": "Kan", "kind": "talk"}
        )
        assert (status, where) == (303, "/back-office")
        assert store.proposal(got.id)["state"] == "accepted"
        assert catalogue.by_id("vid-he").kind.value == "talk"  # type: ignore[union-attr]
    finally:
        server.shutdown()
        server.server_close()
