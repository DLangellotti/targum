"""The local page, and the one endpoint a reader talks back to.

A reader opens before its word meanings are looked up and then asks for them. That
request crosses the only door this server has, so the containment and the key matter as
much as the answer.
"""

from __future__ import annotations

import gc
import gzip
import io
import json
import os
import threading
from collections.abc import Iterator
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import pytest

from targum.accounts import Store
from targum.mail import ConsoleMailer
from targum.serve import Handler, Library


class Postbox(io.StringIO):
    """Somewhere for the sign-in link to land where a test can read it back."""

    @property
    def link(self) -> str:
        """The most recent link sent, since asking again is what voids the one before."""
        for line in reversed(self.getvalue().splitlines()):
            if "/account/enter?t=" in line:
                return line.strip()
        raise AssertionError(f"no link was sent:\n{self.getvalue()}")


@pytest.fixture
def postbox() -> Postbox:
    return Postbox()


@pytest.fixture
def served(tmp_path: Path, postbox: Postbox) -> Iterator[tuple[int, str, Path]]:
    """A running server on a free port. Returns the port, the key, and the output dir."""
    out = tmp_path / "targum-out"
    out.mkdir()
    token = "test-key"
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    handler = type(
        "TestHandler",
        (Handler,),
        {
            "library": Library(out),
            "token": token,
            "page": "<html>start</html>",
            "progress": "<html>your progress</html>",
            "shelf": "<html>library</html>",
            "lists": {
                "texts": "<html>your targums</html>",
                "words": "<html>your words</html>",
                "phrases": "<html>your phrases</html>",
            },
            "store": Store(tmp_path / "words.db"),
            "mailer": ConsoleMailer(postbox),
            "address": f"http://127.0.0.1:{port}",
        },
    )
    server.RequestHandlerClass = handler
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield port, token, out
    finally:
        server.shutdown()
        server.server_close()


def open_files() -> int:
    """How many descriptors this process holds. `/dev/fd` is the process's own table on
    macOS and, on Linux, `/proc/self/fd` by another name."""
    return len(os.listdir("/dev/fd"))


def test_a_request_thread_lets_go_of_its_database_connection(served: tuple[int, str, Path]) -> None:
    """Every request runs on its own thread and opens its own connection; the thread
    ending does not close it, so each answered request must.

    The collector is switched off for the burst: on a laptop it runs often enough to
    tidy up behind the leak and the test would pass by luck, which is exactly how the
    leak reached the box — where the heap is large, the old generation is rarely
    visited, and 500 requests were 1000 descriptors and a 502 on every page after.
    """
    port, token, _ = served
    for _ in range(3):
        assert get(port, f"/glossary/book-he?k={token}")[0] == 200  # warm: templates, caches
    gc.disable()
    try:
        before = open_files()
        for _ in range(40):
            status, _ = get(port, f"/glossary/book-he?k={token}")
            assert status == 200
        after = open_files()
    finally:
        gc.enable()
    # Two descriptors per leaked connection — the file and its WAL — so 40 requests
    # left behind would be eighty. A handful of slack for the sockets in flight.
    assert after - before < 10, f"{after - before} descriptors gained over 40 requests"


def get(port: int, path: str) -> tuple[int, Any]:
    connection = HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        connection.request("GET", path)
        response = connection.getresponse()
        body = response.read()
        try:
            return response.status, json.loads(body)
        except json.JSONDecodeError:
            return response.status, body
    finally:
        connection.close()


def write_glossary(
    out: Path, folder: str, entries: dict[str, str], target: str = "en", name: str = ""
) -> None:
    """One built glossary on disk.

    `name` writes it under a filename of the test's choosing, which is how the reading
    of a `glossary.json` from before the name carried a language gets exercised.
    """
    # Signed out, a build lands in the shared local home rather than at the root.
    build = out / "local" / folder
    build.mkdir(parents=True, exist_ok=True)
    (build / (name or f"glossary.{target}.json")).write_text(
        json.dumps(
            {
                "schema_version": 4,
                "source_language": "he",
                "target_language": target,
                "provider": "test",
                "entries": entries,
                "parts_of_speech": {},
            }
        ),
        encoding="utf-8",
    )


def test_the_glossary_needs_the_key(served: tuple[int, str, Path]) -> None:
    port, _, out = served
    write_glossary(out, "book-he", {"שלום": "peace"})
    status, _ = get(port, "/glossary/book-he")
    assert status == 403


def test_not_yet_is_a_normal_answer(served: tuple[int, str, Path]) -> None:
    """The file appears when the lookups finish. Until then the reader keeps asking."""
    port, key, _ = served
    status, body = get(port, f"/glossary/book-he?k={key}")
    assert status == 200
    assert body == {"ready": False, "target": "en"}


def test_it_hands_over_the_meanings_once_they_exist(served: tuple[int, str, Path]) -> None:
    port, key, out = served
    write_glossary(out, "book-he", {"שלום": "peace", "עם": "people"})
    status, body = get(port, f"/glossary/book-he?k={key}")
    assert status == 200
    assert body == {
        "ready": True,
        "target": "en",
        "entries": {"שלום": "peace", "עם": "people"},
    }


def test_each_language_gets_its_own_meanings(served: tuple[int, str, Path]) -> None:
    """A text read in two languages keeps a glossary for each, and the reader asks for
    the one it is showing. Handing over the other would be handing a reader a definition
    in a language they did not ask for, which is the whole reason the file has a name."""
    port, key, out = served
    write_glossary(out, "book-he", {"שלום": "peace"}, target="en")
    write_glossary(out, "book-he", {"שלום": "мир"}, target="ru")

    _, english = get(port, f"/glossary/book-he?to=en&k={key}")
    _, russian = get(port, f"/glossary/book-he?to=ru&k={key}")

    assert english == {"ready": True, "target": "en", "entries": {"שלום": "peace"}}
    assert russian == {"ready": True, "target": "ru", "entries": {"שלום": "мир"}}


def test_a_glossary_from_before_the_name_carried_a_language_is_english(
    served: tuple[int, str, Path],
) -> None:
    """Every text built before this was built into English. The file is read where it
    lies rather than renamed: a migration that moves files is a migration that can fail
    half way, and this one never has to run at all."""
    port, key, out = served
    write_glossary(out, "book-he", {"שלום": "peace"}, name="glossary.json")

    _, english = get(port, f"/glossary/book-he?to=en&k={key}")
    _, russian = get(port, f"/glossary/book-he?to=ru&k={key}")

    assert english == {"ready": True, "target": "en", "entries": {"שלום": "peace"}}
    # And it is not offered up as an answer about a language it says nothing about.
    assert russian == {"ready": False, "target": "ru"}


def test_a_language_nobody_translates_into_is_refused(served: tuple[int, str, Path]) -> None:
    """`to` decides a filename, so it is checked against the languages targum actually
    translates into before it reaches one — an allowlist, not a pattern."""
    port, key, out = served
    write_glossary(out, "book-he", {"שלום": "peace"})
    for attempt in ("de", "../../etc/passwd", "en/../.."):
        status, body = get(port, f"/glossary/book-he?to={attempt}&k={key}")
        assert (status, body) == (404, {"error": "not found"}), attempt

    # Asking without naming a language is English, which is what every reader built
    # before the question existed is asking about.
    status, body = get(port, f"/glossary/book-he?k={key}")
    assert (status, body["target"]) == (200, "en")


def test_it_will_not_climb_out_of_the_output_directory(
    served: tuple[int, str, Path], tmp_path: Path
) -> None:
    """The same containment `_serve_reader` has, on a path that also names a file."""
    (tmp_path / "glossary.json").write_text('{"entries": {"secret": "leaked"}}', encoding="utf-8")
    port, key, _ = served
    for attempt in ("..", "%2e%2e", "../..", "book-he/../.."):
        status, body = get(port, f"/glossary/{attempt}?k={key}")
        assert (status, body) in [
            (404, {"error": "not found"}),
            (200, {"ready": False, "target": "en"}),
        ], attempt
        assert body != {"ready": True, "entries": {"secret": "leaked"}}


def test_a_half_written_file_reads_as_not_yet(served: tuple[int, str, Path]) -> None:
    """Written while the reader happens to ask. It will ask again in a moment."""
    port, key, out = served
    build = out / "book-he"
    build.mkdir(parents=True)
    (build / "glossary.en.json").write_text('{"entries": {"שלו', encoding="utf-8")
    status, body = get(port, f"/glossary/book-he?k={key}")
    assert (status, body) == (200, {"ready": False, "target": "en"})


def test_the_progress_page_is_behind_the_key(served: tuple[int, str, Path]) -> None:
    """It is a view of everything you have kept, so it is a door like any other."""
    port, token, _ = served
    status, _ = get(port, "/progress")
    assert status == 403
    status, body = get(port, f"/progress?k={token}")
    assert status == 200
    assert b"your progress" in body


def test_the_old_words_address_lands_on_the_words(served: tuple[int, str, Path]) -> None:
    """The page was called Words, then it redirected to Your Progress, and now it is the
    word list itself. Somebody with the old bookmark wanted the words, and that is what
    is at this address again."""
    port, token, _ = served
    status, body, _ = call(port, "GET", f"/words?k={token}")
    assert status == 200
    assert b"your words" in body

    status, _, _ = call(port, "GET", "/words")
    assert status == 403, "and without a key it is the same shut door it always was"


def test_each_list_has_a_page_of_its_own(served: tuple[int, str, Path]) -> None:
    """Learn caps every list it draws. These are where the rest of each one is."""
    port, token, _ = served
    for route, expected in (
        ("/texts", b"your targums"),
        ("/words", b"your words"),
        ("/phrases", b"your phrases"),
    ):
        status, body, _ = call(port, "GET", f"{route}?k={token}")
        assert status == 200, route
        assert expected in body, route


# --- accounts ---------------------------------------------------------------
#
# The point of all of this is one sentence: the same account shows the same words on a
# second device, and a browser nobody is signed into shows nothing. Everything below is
# some part of that claim.


def call(
    port: int, method: str, path: str, body: Any = None, cookie: str = ""
) -> tuple[int, Any, str]:
    """A request that can carry a session and report the one it is handed back."""
    connection = HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        headers = {"Content-Type": "application/json"}
        if cookie:
            headers["Cookie"] = cookie
        connection.request(
            method, path, json.dumps(body).encode("utf-8") if body is not None else None, headers
        )
        response = connection.getresponse()
        raw = response.read()
        handed = response.getheader("Set-Cookie") or ""
        location = response.getheader("Location") or ""
        try:
            return response.status, json.loads(raw), handed or location
        except json.JSONDecodeError:
            return response.status, raw, handed or location
    finally:
        connection.close()


def form(port: int, path: str, fields: dict[str, str], cookie: str = "") -> tuple[int, Any, str]:
    """A plain form post. The landing page is a page in an email, not an app."""
    connection = HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        if cookie:
            headers["Cookie"] = cookie
        connection.request("POST", path, urlencode(fields).encode("utf-8"), headers)
        response = connection.getresponse()
        raw = response.read()
        handed = response.getheader("Set-Cookie") or ""
        return response.status, raw, handed or (response.getheader("Location") or "")
    finally:
        connection.close()


def sign_in(port: int, postbox: Postbox, email: str = "reader@example.com") -> str:
    """Go all the way through the front door, and come back with a session cookie.

    Two steps now: the link opens a page, and pressing its button is what spends it.
    """
    status, payload, _ = call(port, "POST", "/account/sign-in", {"email": email})
    assert status == 200 and payload["sent"], payload
    link = postbox.link
    token = link.split("t=", 1)[1]
    status, body, _ = call(port, "GET", link[link.index("/account/enter") :])
    assert status == 200 and b"Sign in as" in body, "the link should open a page"
    status, _, handed = form(port, "/account/enter", {"t": token})
    assert "targum_session=" in handed, handed
    return handed.split(";", 1)[0]


def test_a_signed_out_browser_is_shown_nothing(served: tuple[int, str, Path]) -> None:
    """No session, no word list. The whole reason there is a session at all."""
    port, token, _ = served
    status, payload = get(port, f"/account/me?k={token}")
    assert status == 200
    assert payload == {"signedIn": False}

    status, payload, _ = call(port, "POST", f"/sync?k={token}", {"since": 0})
    assert status == 401
    assert payload["signedIn"] is False


def test_a_link_signs_you_in_and_only_once(served: tuple[int, str, Path], postbox: Postbox) -> None:
    """A magic link is a bearer token that has to survive being in an inbox.

    Single use is what stops a forwarded email, a shared screenshot, or a mail server
    that keeps a copy from being a way in later.
    """
    port, token, _ = served
    cookie = sign_in(port, postbox)
    status, payload = get(port, f"/account/me?k={token}")
    assert payload == {"signedIn": False}, "the key alone is not a person"

    status, payload, _ = call(port, "GET", f"/account/me?k={token}", cookie=cookie)
    assert payload["signedIn"] is True
    assert payload["email"] == "reader@example.com"

    # The same link a second time is spent, and lands on a page offering another
    # rather than on an error: clicking an old email twice is an ordinary thing to do.
    link = postbox.link
    status, body, _ = call(port, "GET", link[link.index("/account/enter") :])
    assert status == 200
    assert b"has been used" in body


def test_an_address_is_never_confirmed_or_denied(served: tuple[int, str, Path]) -> None:
    """The sign-in form must not become a way of asking who has an account here."""
    port, _, _ = served
    first = call(port, "POST", "/account/sign-in", {"email": "known@example.com"})[1]
    second = call(port, "POST", "/account/sign-in", {"email": "stranger@example.com"})[1]
    assert first == second

    status, payload, _ = call(port, "POST", "/account/sign-in", {"email": "not-an-address"})
    assert status == 400


def test_words_follow_the_account_to_another_device(
    served: tuple[int, str, Path], postbox: Postbox
) -> None:
    """The done-when for the whole feature, written as a test.

    Two cookies for one account stand in for a laptop and a phone. What one keeps, the
    other is handed on its next sync, and neither has to know the other exists.
    """
    port, token, _ = served
    laptop = sign_in(port, postbox)
    phone = sign_in(port, postbox)  # same address, second browser

    status, pushed, _ = call(
        port,
        "POST",
        f"/sync?k={token}",
        {
            "since": 0,
            "words": [
                {
                    "language": "he",
                    "lemma": "ספר",
                    "surface": "הספר",
                    "status": 2,
                    "meaning": "book",
                    "at": 1000,
                    "seen": 1000,
                }
            ],
            "docs": [{"hash": "abc", "title": "A text", "language": "he", "seen": 1000}],
        },
        cookie=laptop,
    )
    assert status == 200

    status, got, _ = call(port, "POST", f"/sync?k={token}", {"since": 0}, cookie=phone)
    assert [word["lemma"] for word in got["words"]] == ["ספר"]
    assert got["words"][0]["meaning"] == "book"
    assert [doc["hash"] for doc in got["docs"]] == ["abc"]

    # And having taken it, the phone is not handed it again on every sync afterwards.
    status, again, _ = call(
        port, "POST", f"/sync?k={token}", {"since": got["revision"]}, cookie=phone
    )
    assert again["words"] == []


def test_the_days_you_read_on_follow_the_account(
    served: tuple[int, str, Path], postbox: Postbox
) -> None:
    """Twelve days reading has to mean twelve, not twelve on this laptop.

    Days are a set and nothing else: they merge by union, they never carry a tombstone,
    and pushing the same day twice is not an edit. That last part is the one worth
    pinning — the rows go up with `seen: 0` precisely so a browser syncing all afternoon
    rewrites nothing.
    """
    port, token, _ = served
    laptop = sign_in(port, postbox)
    phone = sign_in(port, postbox)

    status, _, _ = call(
        port,
        "POST",
        f"/sync?k={token}",
        {"since": 0, "days": [{"day": "2026-08-24", "count": 1, "seen": 0}]},
        cookie=laptop,
    )
    assert status == 200

    status, _, _ = call(
        port,
        "POST",
        f"/sync?k={token}",
        {"since": 0, "days": [{"day": "2026-08-25", "count": 1, "seen": 0}]},
        cookie=phone,
    )
    assert status == 200

    # Either browser, asked from scratch, has both days rather than its own.
    _, got, _ = call(port, "POST", f"/sync?k={token}", {"since": 0}, cookie=laptop)
    assert sorted(row["day"] for row in got["days"]) == ["2026-08-24", "2026-08-25"]
    assert got["counts"]["days"] == 2

    # And a second push of a day already up there changes nothing, so the row does not
    # come back down to the other browser under a new revision every time.
    settled = got["revision"]
    call(
        port,
        "POST",
        f"/sync?k={token}",
        {"since": settled, "days": [{"day": "2026-08-24", "count": 1, "seen": 0}]},
        cookie=laptop,
    )
    _, after, _ = call(port, "POST", f"/sync?k={token}", {"since": settled}, cookie=phone)
    assert after["days"] == []


def test_a_row_that_is_not_a_record_is_skipped_rather_than_raising(
    served: tuple[int, str, Path], postbox: Postbox
) -> None:
    """The allowlist checked that the value was a list and never what was in it, so a
    list of strings reached the merge and raised on `.get`. A signed-in reader could only
    do that to themselves, but a 500 is the wrong answer to nonsense."""
    port, token, _ = served
    cookie = sign_in(port, postbox)

    status, answer, _ = call(
        port,
        "POST",
        f"/sync?k={token}",
        {"since": 0, "words": ["nonsense", None, 7], "days": [{"day": "2026-08-25"}]},
        cookie=cookie,
    )
    assert status == 200
    assert answer["counts"]["words"] == 0, "the rubbish was dropped"
    assert answer["counts"]["days"] == 1, "and the record beside it still landed"


def test_a_language_nobody_said_they_read_is_not_sold_to_them(
    served: tuple[int, str, Path], postbox: Postbox
) -> None:
    """A new account is learning Hebrew and reads English; anything else has to be said.

    The cost of guessing is a reader handed a page they cannot read, paid for out of
    their own rails — and every word they keep from it carrying a meaning in that
    language into every text they own. It is their own answer now, given on the profile
    page, and the refusal says so.
    """
    port, token, _ = served
    cookie = sign_in(port, postbox)

    status, answer, _ = call(
        port,
        "POST",
        f"/prepare?k={token}",
        {"source": "sefaria:Genesis", "to": "ru", "from": "he"},
        cookie=cookie,
    )
    assert status == 400 and answer["error"] == "Russian is not in your profile."

    _, me, _ = call(port, "GET", f"/account/me?k={token}", cookie=cookie)
    assert me["learning"] == ["he"] and me["reads"] == ["en"]

    status, saved, _ = call(
        port,
        "POST",
        f"/account/languages?k={token}",
        {"learning": ["he", "yi"], "reads": ["en", "ru"]},
        cookie=cookie,
    )
    assert status == 200 and saved["learning"] == ["he", "yi"] and saved["reads"] == ["en", "ru"]

    _, me, _ = call(port, "GET", f"/account/me?k={token}", cookie=cookie)
    assert me["learning"] == ["he", "yi"] and me["reads"] == ["en", "ru"]

    # A source language they have not ticked is refused the same way.
    status, answer, _ = call(
        port,
        "POST",
        f"/prepare?k={token}",
        {"source": "sefaria:Genesis", "to": "en", "from": "arc"},
        cookie=cookie,
    )
    assert status == 400 and answer["error"] == "Aramaic is not in your profile."


@pytest.mark.parametrize(
    ("asked", "said"),
    [
        ({"learning": ["he"], "reads": []}, "Keep at least one."),
        ({"learning": ["yi"], "reads": ["en"]}, "Hebrew stays on."),
        ({"learning": ["he"], "reads": ["fr"]}, "targum does not have French."),
    ],
)
def test_a_profile_nobody_can_read_with_is_refused_whole(
    served: tuple[int, str, Path], postbox: Postbox, asked: dict[str, list[str]], said: str
) -> None:
    """Nobody can untick everything: a reader with no language to read into has no
    reader, and in this version Hebrew is what everybody is learning. Refused whole, and
    the answer carries what still stands so the page can put its boxes back."""
    port, token, _ = served
    cookie = sign_in(port, postbox)

    status, answer, _ = call(port, "POST", f"/account/languages?k={token}", asked, cookie=cookie)
    assert status == 400 and answer["error"] == said
    assert answer["learning"] == ["he"] and answer["reads"] == ["en"]


def test_an_old_marking_arrives_as_the_persons_own_choice(tmp_path: Path) -> None:
    """`targum languages` marked an address as reading Russian, from a terminal. The
    profile replaces it, and a person who was marked keeps Russian — with English
    beside it, because the marking always offered English too."""
    from targum.accounts import Store

    where = tmp_path / "words.db"
    keeping = Store(where)
    keeping.start_sign_in("marked@example.com")
    person = keeping.person_by_email("marked@example.com")
    assert person is not None
    with keeping.write() as db:
        db.execute("INSERT INTO reads (email, language, at) VALUES ('marked@example.com', 'ru', 1)")

    reopened = Store(where)
    assert reopened.reads(person.id) == {"en", "ru"}
    # And having unticked one, the marking does not come back on the next open.
    reopened.choose(person, "reading", ["ru"])
    assert Store(where).reads(person.id) == {"ru"}
    # Somebody who never signed in has no person to carry it to, and gets the default
    # the day they do.
    assert Store(where).reads(None) == set()


def test_a_reader_is_written_without_a_language_its_owner_does_not_read(
    tmp_path: Path,
) -> None:
    """A reader is a file, so this is the only moment the question can be asked.

    A targum that already holds two translations stops offering the one its owner does
    not read, the next time it is written — which is what `targum languages` ends by
    doing.
    """
    from targum.models import (
        Annotation,
        Block,
        BlockKind,
        Document,
        Segment,
        SegmentedDocument,
        Translation,
    )
    from targum.render import render

    segment = Segment(id="0001.000-a", block_id="b1", block_index=0, index=0, text="שלום")
    document = Document(
        source="memory",
        title="A text",
        language="he",
        blocks=[Block(id="b1", kind=BlockKind.paragraph, text="שלום")],
        content_hash="h",
    )
    segmented = SegmentedDocument(
        document_hash="h", language="he", segmenter="t/1", segments=[segment]
    )

    def saying(code: str, text: str) -> Translation:
        return Translation(
            name=code.upper(),
            document_hash="h",
            source_language="he",
            target_language=code,
            provider="null",
            segments={segment.id: text},
        )

    both = [saying("ru", "мир"), saying("en", "peace")]
    annotation = Annotation(
        document_hash="h",
        language="he",
        annotator="t/1",
        method="frequency",
        method_note="a test",
        tokens={},
    )

    only_english = render(
        document, segmented, both, tmp_path / "en", annotation=annotation, reads=["en"]
    )[0].read_text(encoding="utf-8")
    assert "peace" in only_english
    assert "мир" not in only_english, "a language its owner does not read was offered"
    assert only_english.count("<option") == 0, "one translation needs no picker"

    # Asked of nobody — the command line, and a machine somebody runs themselves.
    everything = render(document, segmented, both, tmp_path / "all", annotation=annotation)[
        0
    ].read_text(encoding="utf-8")
    assert "мир" in everything and "peace" in everything


def test_a_reader_left_with_nothing_keeps_what_it_had(tmp_path: Path) -> None:
    """The one exception, and it only arises where somebody stopped reading a language
    they had already built in: a page with no translation beside the source is not a
    reader at all, which is the worse of the two answers."""
    from targum.models import Block, BlockKind, Document, Segment, SegmentedDocument, Translation
    from targum.render import render

    segment = Segment(id="0001.000-a", block_id="b1", block_index=0, index=0, text="שלום")
    document = Document(
        source="memory",
        title="A text",
        language="he",
        blocks=[Block(id="b1", kind=BlockKind.paragraph, text="שלום")],
        content_hash="h",
    )
    segmented = SegmentedDocument(
        document_hash="h", language="he", segmenter="t/1", segments=[segment]
    )
    russian = Translation(
        name="RU",
        document_hash="h",
        source_language="he",
        target_language="ru",
        provider="null",
        segments={segment.id: "мир"},
    )

    page = render(document, segmented, [russian], tmp_path / "r", reads=["en"])[0]
    assert "мир" in page.read_text(encoding="utf-8")


def test_a_meaning_belongs_to_a_pair_and_a_word_to_a_language(
    served: tuple[int, str, Path], postbox: Postbox
) -> None:
    """The account keeps the two apart, which is the whole of it.

    One Hebrew word read in English and in Russian is one row in `word` — one level, one
    line in every count — and two rows in `meaning`. Pushing what it means in Russian
    must not touch what it means in English, and must not touch the word at all.
    """
    port, token, _ = served
    cookie = sign_in(port, postbox)
    word = {"language": "he", "lemma": "ספר", "surface": "ספר", "status": 2, "seen": 100}
    english = {"source": "he", "target": "en", "term": "ספר", "meaning": "book", "seen": 100}
    russian = {"source": "he", "target": "ru", "term": "ספר", "meaning": "книга", "seen": 200}

    call(port, "POST", f"/sync?k={token}", {"since": 0, "words": [word]}, cookie=cookie)
    call(
        port,
        "POST",
        f"/sync?k={token}",
        {"since": 0, "meanings": [english, russian]},
        cookie=cookie,
    )
    _, state, _ = call(port, "POST", f"/sync?k={token}", {"since": 0}, cookie=cookie)

    said = {(m["target"], m["term"]): m["meaning"] for m in state["meanings"]}
    assert said == {("en", "ספר"): "book", ("ru", "ספר"): "книга"}
    # One word, one level, counted once. This is the invariant the split exists to keep:
    # a Hebrew word known is a Hebrew word, whichever language it was learned through.
    assert len(state["words"]) == 1
    assert state["words"][0]["status"] == 2
    assert state["counts"]["words"] == 1


def test_a_phrase_reading_rides_with_the_meanings(
    served: tuple[int, str, Path], postbox: Postbox
) -> None:
    """Under its own id, in the same table: it is the same fact about the same pair, and
    a second table for a handful of rows is furniture."""
    port, token, _ = served
    cookie = sign_in(port, postbox)
    reading = {
        "source": "he",
        "target": "ru",
        "term": "phrase:p1-abc",
        "meaning": "и было так",
        "seen": 100,
    }
    call(port, "POST", f"/sync?k={token}", {"since": 0, "meanings": [reading]}, cookie=cookie)

    _, state, _ = call(port, "POST", f"/sync?k={token}", {"since": 0}, cookie=cookie)
    assert state["meanings"][0]["term"] == "phrase:p1-abc"
    assert state["meanings"][0]["meaning"] == "и было так"


def test_forgetting_somebody_forgets_what_they_read_it_in(
    served: tuple[int, str, Path], postbox: Postbox
) -> None:
    """A table added after the forget-a-person loop was written is a table that outlives
    the person who asked to be forgotten."""
    from targum.accounts import Store

    port, token, out = served
    cookie = sign_in(port, postbox)
    call(
        port,
        "POST",
        f"/sync?k={token}",
        {
            "since": 0,
            "meanings": [
                {"source": "he", "target": "ru", "term": "ספר", "meaning": "книга", "seen": 1}
            ],
        },
        cookie=cookie,
    )

    # The same file the server is using: `served` puts it beside the output directory.
    store = Store(out.parent / "words.db")
    person = store.person_by_email("reader@example.com")
    assert person is not None
    store.forget(person)
    # A grace period already over, rather than one of exactly zero: the flag was written
    # this millisecond and `purge` asks whether it is older than the cutoff.
    assert store.purge(days=-1) == [person.id]
    with store.write() as db:
        left = db.execute("SELECT COUNT(*) AS n FROM meaning").fetchone()["n"]
    assert left == 0, "her meanings outlived her asking to be forgotten"


def test_a_newer_edit_wins_and_a_delete_sticks(
    served: tuple[int, str, Path], postbox: Postbox
) -> None:
    """Last-write-wins, and tombstones.

    Without the tombstone, deleting a word on one device is indistinguishable from a
    word the other device has not heard of, and it comes straight back.
    """
    port, token, _ = served
    laptop = sign_in(port, postbox)
    phone = sign_in(port, postbox)

    base = {"language": "he", "lemma": "אור", "meaning": "light", "at": 100, "seen": 100}
    call(port, "POST", f"/sync?k={token}", {"since": 0, "words": [base]}, cookie=laptop)

    # An edit made earlier does not overwrite one made later, whichever order they land.
    call(
        port,
        "POST",
        f"/sync?k={token}",
        {"since": 0, "words": [{**base, "status": 3, "seen": 300}]},
        cookie=phone,
    )
    call(
        port,
        "POST",
        f"/sync?k={token}",
        {"since": 0, "words": [{**base, "status": 1, "seen": 200}]},
        cookie=laptop,
    )
    _, state, _ = call(port, "POST", f"/sync?k={token}", {"since": 0}, cookie=laptop)
    assert state["words"][0]["status"] == 3
    assert state["words"][0]["meaning"] == "light", "a partial push must not erase"

    call(
        port,
        "POST",
        f"/sync?k={token}",
        {"since": 0, "words": [{**base, "gone": 1, "seen": 400}]},
        cookie=laptop,
    )
    _, state, _ = call(port, "POST", f"/sync?k={token}", {"since": 0}, cookie=phone)
    assert state["words"][0]["gone"] == 1


def test_signing_out_ends_it_on_that_browser_only(
    served: tuple[int, str, Path], postbox: Postbox
) -> None:
    """One browser signing out must not sign out the other, or lose anything."""
    port, token, _ = served
    laptop = sign_in(port, postbox)
    phone = sign_in(port, postbox)

    call(
        port,
        "POST",
        f"/sync?k={token}",
        {"since": 0, "words": [{"language": "he", "lemma": "בית", "seen": 10}]},
        cookie=laptop,
    )
    status, payload, handed = call(port, "POST", "/account/sign-out", {}, cookie=laptop)
    assert status == 200 and "Max-Age=0" in handed

    _, mine, _ = call(port, "GET", f"/account/me?k={token}", cookie=laptop)
    assert mine == {"signedIn": False}

    _, theirs, _ = call(port, "GET", f"/account/me?k={token}", cookie=phone)
    assert theirs["signedIn"] is True
    assert theirs["counts"]["words"] == 1


def test_a_session_outlives_a_restart_where_the_key_does_not(
    served: tuple[int, str, Path], postbox: Postbox
) -> None:
    """Signing in has to fix the thing it looks like it should fix.

    The start-up key changes every run, which is why a bookmark never worked. A session
    is on disk, so once somebody has signed in their bookmark starts working — and that
    means the key cannot be the only thing that opens the door.
    """
    port, _, _ = served
    cookie = sign_in(port, postbox)

    status, payload, _ = call(port, "GET", "/account/me", cookie=cookie)
    assert status == 200
    assert payload["signedIn"] is True

    status, body, _ = call(port, "GET", "/progress", cookie=cookie)
    assert status == 200 and b"your progress" in body

    # And without either, still nothing — the holding page now, rather than the
    # stale-session error, because once an account exists on a machine "signed out" is
    # a state somebody chose rather than a key that expired.
    status, body, _ = call(port, "GET", "/progress")
    assert b"<html>words</html>" not in body, "the words page must not be served"
    assert b"Coming soon" in body or status == 403


# --- one person's readers are their own ---------------------------------------


def test_homes_do_not_contain_one_another(tmp_path: Path) -> None:
    """The containment guard is only worth anything if no home sits inside another."""
    from targum.accounts import Person
    from targum.serve import Library

    library = Library(tmp_path)
    alice = library.home(Person(1, "alice@example.com"))
    bob = library.home(Person(2, "bob@example.com"))
    anon = library.home(None)

    assert len({alice, bob, anon}) == 3
    for a in (alice, bob, anon):
        for b in (alice, bob, anon):
            if a != b:
                assert a not in b.parents, f"{b} sits inside {a}"


def test_a_person_only_lists_their_own_readers(tmp_path: Path) -> None:
    from targum.accounts import Person
    from targum.serve import Library

    library = Library(tmp_path)
    alice, bob = Person(1, "a@x.com"), Person(2, "b@x.com")
    for person, name in ((alice, "hers-he"), (bob, "his-he")):
        reader = library.home(person) / name / "reader"
        reader.mkdir(parents=True)
        (reader / "index.html").write_text("<p>x</p>", encoding="utf-8")

    assert [r["name"] for r in library.readers(library.home(alice))] == ["hers-he"]
    assert [r["name"] for r in library.readers(library.home(bob))] == ["his-he"]
    assert library.readers(library.home(None)) == []


def test_readers_built_before_homes_existed_are_adopted(tmp_path: Path) -> None:
    """Upgrading must not hide the readers already on disk."""
    from targum.serve import Library

    old = tmp_path / "book-he"
    (old / "reader").mkdir(parents=True)
    (old / "reader" / "index.html").write_text("<p>x</p>", encoding="utf-8")
    (old / "document.json").write_text("{}", encoding="utf-8")
    # Ingested and never translated: no reader, but the work is still on disk.
    stub = tmp_path / "stub-he"
    stub.mkdir()
    (stub / "document.json").write_text("{}", encoding="utf-8")

    library = Library(tmp_path)

    assert (tmp_path / "local" / "book-he" / "reader" / "index.html").is_file()
    assert (tmp_path / "local" / "stub-he" / "document.json").is_file()
    assert not old.exists() and not stub.exists()
    assert [r["name"] for r in library.readers(library.home(None))] == ["book-he"]


def test_adopting_twice_changes_nothing(tmp_path: Path) -> None:
    from targum.serve import Library

    old = tmp_path / "book-he"
    (old / "reader").mkdir(parents=True)
    (old / "reader" / "index.html").write_text("<p>x</p>", encoding="utf-8")
    (old / "document.json").write_text("{}", encoding="utf-8")

    Library(tmp_path)
    Library(tmp_path)  # a restart

    assert (tmp_path / "local" / "book-he" / "reader" / "index.html").is_file()
    assert not (tmp_path / "local" / "local").exists()


def test_adopting_does_not_overwrite_a_name_already_taken(tmp_path: Path) -> None:
    """Two documents can slug the same and hold different texts.

    Renaming one over the other loses work, and on a non-empty directory it does not
    even fail cleanly: it raises part-way through start-up and the server never comes
    up. Which is what happened.
    """
    from targum.serve import Library

    (tmp_path / "local" / "declaration-he").mkdir(parents=True)
    (tmp_path / "local" / "declaration-he" / "document.json").write_text(
        '{"title": "the one already adopted"}', encoding="utf-8"
    )
    (tmp_path / "declaration-he").mkdir()
    (tmp_path / "declaration-he" / "document.json").write_text(
        '{"title": "a different text with the same slug"}', encoding="utf-8"
    )

    Library(tmp_path)  # must not raise

    kept = (tmp_path / "local" / "declaration-he" / "document.json").read_text()
    moved = (tmp_path / "local" / "declaration-he-2" / "document.json").read_text()
    assert "already adopted" in kept
    assert "different text" in moved
    assert not (tmp_path / "declaration-he").exists()


def test_a_text_whose_name_starts_with_p_is_still_adopted(tmp_path: Path) -> None:
    """A home is `p` and a number. "poem-he" is a text, not somebody's home."""
    from targum.serve import Library

    for name in ("poem-he", "p12", "portrait-en"):
        (tmp_path / name).mkdir()
        (tmp_path / name / "document.json").write_text("{}", encoding="utf-8")

    Library(tmp_path)

    assert (tmp_path / "local" / "poem-he").is_dir()
    assert (tmp_path / "local" / "portrait-en").is_dir()
    # p12 looks exactly like a person's home, so it is left alone.
    assert (tmp_path / "p12").is_dir()
    assert not (tmp_path / "local" / "p12").exists()


def test_old_builds_belong_to_the_one_person_on_the_machine(tmp_path: Path) -> None:
    """Signing in must not empty your library.

    Everything built before homes existed went to the signed-out home, which is right
    until you remember that the person who built it has an account and is signed in.
    They then see nothing at all.
    """
    from targum.accounts import Store
    from targum.serve import Library

    store = Store(tmp_path / "targum.db")
    store.start_sign_in("reader@example.com")
    person = store.person_by_email("reader@example.com")
    assert person is not None

    out = tmp_path / "out"
    (out / "book-he" / "reader").mkdir(parents=True)
    (out / "book-he" / "reader" / "index.html").write_text("<p>x</p>", encoding="utf-8")
    (out / "book-he" / "document.json").write_text("{}", encoding="utf-8")

    library = Library(out, store=store)

    assert [r["name"] for r in library.readers(library.home(person))] == ["book-he"]
    assert library.readers(library.home(None)) == []


def test_builds_already_in_the_signed_out_home_are_carried_over(tmp_path: Path) -> None:
    """The upgrade path for anyone who ran the version that got this wrong."""
    from targum.accounts import Store
    from targum.serve import Library

    store = Store(tmp_path / "targum.db")
    store.start_sign_in("reader@example.com")
    person = store.person_by_email("reader@example.com")
    assert person is not None

    out = tmp_path / "out"
    (out / "local" / "book-he" / "reader").mkdir(parents=True)
    (out / "local" / "book-he" / "reader" / "index.html").write_text("<p>x</p>", encoding="utf-8")

    library = Library(out, store=store)

    assert [r["name"] for r in library.readers(library.home(person))] == ["book-he"]
    assert not (out / "local" / "book-he").exists()


def test_with_two_accounts_nobody_inherits_anything(tmp_path: Path) -> None:
    """Who owns an old build is then a guess, and it is not made."""
    from targum.accounts import Store
    from targum.serve import Library

    store = Store(tmp_path / "targum.db")
    store.start_sign_in("one@example.com")
    store.start_sign_in("two@example.com")
    one = store.person_by_email("one@example.com")
    assert one is not None

    out = tmp_path / "out"
    (out / "book-he" / "reader").mkdir(parents=True)
    (out / "book-he" / "reader" / "index.html").write_text("<p>x</p>", encoding="utf-8")
    (out / "book-he" / "document.json").write_text("{}", encoding="utf-8")

    library = Library(out, store=store)

    assert library.readers(library.home(one)) == []
    assert [r["name"] for r in library.readers(library.home(None))] == ["book-he"]


# --- the front door -----------------------------------------------------------


def test_a_mail_client_reading_the_link_does_not_spend_it(
    served: tuple[int, str, Path], postbox: Postbox
) -> None:
    """The reason the link stopped being a plain GET.

    Mail clients fetch links to preview them. When the GET was the sign-in, the reader
    clicked a link that had already been used by their own inbox.
    """
    port, token, _ = served
    call(port, "POST", "/account/sign-in", {"email": "reader@example.com"})
    link = postbox.link
    where = link[link.index("/account/enter") :]

    # Three prefetches, the way a mail client might.
    for _ in range(3):
        status, body, handed = call(port, "GET", where)
        assert status == 200
        assert b"Sign in as reader@example.com" in body
        assert "targum_session=" not in handed, "reading the page signed somebody in"

    # And it still works when a person actually presses the button.
    status, _, handed = form(port, "/account/enter", {"t": link.split("t=", 1)[1]})
    assert "targum_session=" in handed


def test_the_landing_page_names_the_account_without_spending_the_link(
    served: tuple[int, str, Path], postbox: Postbox
) -> None:
    port, _, _ = served
    call(port, "POST", "/account/sign-in", {"email": "someone@example.com"})
    link = postbox.link
    status, body, _ = call(port, "GET", link[link.index("/account/enter") :])
    assert status == 200
    assert b"someone@example.com" in body


def test_asking_for_too_many_links_is_refused(served: tuple[int, str, Path]) -> None:
    """Anyone can call this route, and every call sends mail to an address they chose."""
    port, _, _ = served
    codes = [
        call(port, "POST", "/account/sign-in", {"email": "flood@example.com"})[0] for _ in range(8)
    ]
    assert 200 in codes and 429 in codes, codes
    # A different address is unaffected: the limit is per inbox, not a global tap.
    assert call(port, "POST", "/account/sign-in", {"email": "other@example.com"})[0] == 200


def test_signed_out_is_shown_the_door_when_an_account_is_required(tmp_path: Path) -> None:
    from targum.serve import Handler

    assert Handler.require_account is False, "a local run must not need an account"


def test_deleting_an_account_waits_out_the_grace_period(tmp_path: Path) -> None:
    """Deleting is one click on a bad day. Time is what makes that survivable."""
    from targum.accounts import GRACE_DAYS, Store, now

    store = Store(tmp_path / "targum.db")
    store.start_sign_in("leaving@example.com")
    person = store.person_by_email("leaving@example.com")
    assert person is not None

    store.forget(person)
    # Gone as far as anyone can tell, but still recoverable.
    assert store.purge() == []
    assert store.person_by_email("leaving@example.com") is not None
    token = store.start_sign_in("leaving@example.com")
    assert store.finish_sign_in(token) is None, "a leaving account must not sign in"

    store.stay(person)
    token = store.start_sign_in("leaving@example.com")
    assert store.finish_sign_in(token) is not None, "changing their mind should work"

    store.forget(person)
    with store.write() as db:
        stale = now() - (GRACE_DAYS + 1) * 24 * 60 * 60 * 1000
        db.execute("UPDATE person SET leaving = ? WHERE id = ?", (stale, person.id))
    assert store.purge() == [person.id]
    assert store.person_by_email("leaving@example.com") is None


def test_the_grace_period_actually_ends_when_targum_starts(tmp_path: Path) -> None:
    """`purge` had nothing calling it: "Delete account" ended the session, and the rows
    and the readers on disk stayed for good. Start-up is when the trash is emptied, and
    this is the same promise — a deletion that waits, and then happens."""
    from targum.accounts import GRACE_DAYS, Store, now
    from targum.serve import Library

    store = Store(tmp_path / "targum.db")
    store.start_sign_in("leaving@example.com")
    person = store.person_by_email("leaving@example.com")
    assert person is not None
    home = tmp_path / "out" / f"p{person.id}"
    (home / "a-text").mkdir(parents=True)
    store.forget(person)
    with store.write() as db:
        stale = now() - (GRACE_DAYS + 1) * 24 * 60 * 60 * 1000
        db.execute("UPDATE person SET leaving = ? WHERE id = ?", (stale, person.id))

    Library(tmp_path / "out", store=store)

    assert store.person_by_email("leaving@example.com") is None
    assert not home.exists(), "their readers went with them"


def test_an_older_database_gains_the_columns_it_is_missing(tmp_path: Path) -> None:
    """The failure a suite of temporary files cannot see.

    `CREATE TABLE IF NOT EXISTS` does nothing to a table that already exists, so a
    column added later is missing on every database but a brand new one. This is what
    that looks like: a v1 file, opened by the current code.
    """
    import sqlite3

    from targum.accounts import Store

    path = tmp_path / "old.db"
    raw = sqlite3.connect(path)
    raw.executescript(
        "CREATE TABLE person (id INTEGER PRIMARY KEY, email TEXT NOT NULL UNIQUE,"
        " made INTEGER NOT NULL, revision INTEGER NOT NULL DEFAULT 0);"
        "INSERT INTO person (email, made) VALUES ('old@example.com', 1);"
        "PRAGMA user_version = 1;"
    )
    raw.commit()
    raw.close()

    store = Store(path)
    person = store.person_by_email("old@example.com")
    assert person is not None, "the account from the old file should still be there"
    # The query that used to raise "no such column: person.leaving".
    assert store.purge() == []
    store.forget(person)
    assert store.peek_sign_in("nonsense") is None
    from targum.accounts import SCHEMA_VERSION

    assert int(store.db.execute("PRAGMA user_version").fetchone()[0]) == SCHEMA_VERSION


def test_opening_a_current_database_twice_is_fine(tmp_path: Path) -> None:
    from targum.accounts import Store

    Store(tmp_path / "x.db")
    Store(tmp_path / "x.db")


def test_the_emailed_link_names_an_address_a_reader_can_reach(
    tmp_path: Path, postbox: Postbox
) -> None:
    """Loopback is right for the server and useless in an email.

    Hosted, a link pointing at 127.0.0.1 arrives in an inbox on someone else's laptop
    and opens their machine, not targum.
    """
    from targum.serve import Handler

    for given, expected in (
        ("https://targum.page", "https://targum.page/account/enter"),
        ("https://targum.page/", "https://targum.page/account/enter"),
        ("", "http://127.0.0.1:8420/account/enter"),
    ):
        address = (given or "http://127.0.0.1:8420").rstrip("/")
        assert f"{address}/account/enter" == expected

    assert Handler.require_account is False


# --- what a served page is allowed to do --------------------------------------


def test_a_page_carries_a_policy_naming_its_own_blocks(served: tuple[int, str, Path]) -> None:
    """Inline script and style are the design — a reader is one file that works off a
    disk. So the policy names each block by the hash of its contents rather than
    allowing inline generally, which would permit whatever a defect managed to inject.
    """
    import base64
    import hashlib
    import re
    from http.client import HTTPConnection

    port, token, _ = served
    connection = HTTPConnection("127.0.0.1", port, timeout=5)
    connection.request("GET", f"/?k={token}")
    response = connection.getresponse()
    response.read()
    policy = response.getheader("Content-Security-Policy") or ""
    connection.close()

    assert "default-src 'none'" in policy
    assert "frame-ancestors 'none'" in policy
    assert "base-uri 'none'" in policy
    assert "form-action 'self'" in policy
    assert "'unsafe-inline'" not in policy, "hashes, not a blanket permission"
    # The Hebrew faces ride inside the page as data: URIs, and `default-src 'none'`
    # refuses a font it does not name. Without this the font failed by policy in every
    # served reader while every check that opened the file directly passed — a page with
    # no accents in its face, found by a reader rather than a test.
    assert "font-src data:" in policy, "the embedded Hebrew face is refused by policy"
    # And the recordings, which ride in the page the same way and fail the same way. The
    # player reported "this recording would not play" on every served page while every
    # check that opened the file passed, because a file has no policy — the identical
    # blind spot the line above was written for, two months apart. `'self'` joined when
    # video became a sidecar file beside the reader (design.md §12): without it the
    # served page refuses the file sitting next to it, the same bug a third time.
    assert "media-src 'self' data:" in policy, "the recording or its sidecar is refused by policy"

    # The fixture serves a stub, so the hashing itself is checked against a page that
    # has the shape a real one does: inline style, inline script, and a data block.
    from targum.serve import Handler

    real = (
        b"<html><head><style>body{color:red}</style></head>"
        b'<body><script type="application/json">{"a":1}</script>'
        b"<script>window.x = 1</script></body></html>"
    )
    named = Handler._policy(real)
    blocks = re.findall(rb"<(?:script|style)[^>]*>(.*?)</(?:script|style)>", real, re.S)
    assert len(blocks) == 3
    for block in blocks:
        digest = base64.b64encode(hashlib.sha256(block).digest()).decode("ascii")
        assert f"'sha256-{digest}'" in named, "a block the page contains is not allowed to run"
    assert "'unsafe-inline'" not in named


def test_the_policy_travels_with_html_and_not_with_data(served: tuple[int, str, Path]) -> None:
    from http.client import HTTPConnection

    port, token, _ = served
    connection = HTTPConnection("127.0.0.1", port, timeout=5)
    connection.request("GET", f"/account/me?k={token}")
    response = connection.getresponse()
    response.read()
    assert response.getheader("Content-Security-Policy") is None
    assert response.getheader("Referrer-Policy") == "no-referrer"
    connection.close()


def test_the_policy_still_lets_the_sign_in_form_post(
    served: tuple[int, str, Path], postbox: Postbox
) -> None:
    """The regression this file did not catch the first time.

    `form-action 'none'` reads as obviously right — a reader has no forms — and it
    silently broke the one page in targum that is a real form. The landing page has to
    work with no JavaScript, because it arrives from an email in whatever browser opened
    it, so the browser posts it and the policy decides whether that is allowed.
    """
    from http.client import HTTPConnection

    port, _, _ = served

    connection = HTTPConnection("127.0.0.1", port, timeout=5)
    connection.request("GET", "/account/signin")
    response = connection.getresponse()
    body = response.read()
    policy = response.getheader("Content-Security-Policy") or ""
    connection.close()

    assert b"<form" in body, "the door is a form, and must stay one"
    assert "form-action 'self'" in policy, "the policy must allow it to post back"
    assert "form-action 'none'" not in policy

    # And end to end: the link opens a page, the button posts, a session comes back.
    call(port, "POST", "/account/sign-in", {"email": "reader@example.com"})
    link = postbox.link
    status, page, _ = call(port, "GET", link[link.index("/account/enter") :])
    assert status == 200 and b"<form" in page
    _, _, handed = form(port, "/account/enter", {"t": link.split("t=", 1)[1]})
    assert "targum_session=" in handed


# --- what a stranger sees ------------------------------------------------------


def hosted(tmp_path: Path) -> tuple[int, threading.Thread, ThreadingHTTPServer]:
    """A server in the shape targum.page runs in: an account required for everything."""
    from targum.mail import ConsoleMailer
    from targum.render.builder import holding_page, signin_page

    handler = type(
        "Hosted",
        (Handler,),
        {
            "library": Library(tmp_path / "out", store=Store(tmp_path / "w.db")),
            "require_account": True,
            "token": "key",
            "store": Store(tmp_path / "w.db"),
            "mailer": ConsoleMailer(stream=io.StringIO()),
            "address": "https://targum.page",
            "page": "<html>start</html>",
            "progress": "<html>your progress</html>",
            "shelf": "<html>library</html>",
        },
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    assert holding_page() and signin_page()
    return server.server_address[1], thread, server


def test_a_stranger_sees_the_holding_page_and_nothing_else(tmp_path: Path) -> None:
    """The product stays shut to anyone without an account.

    The shelves are the deliberate exception and are tested below: they are the shop
    window, and a catalogue nobody outside can see is a catalogue nobody arrives
    through. Everything else a signed-out visitor asks for is still the door.
    """
    port, _, server = hosted(tmp_path)
    try:
        for route in ("/", "/progress"):
            status, body, _ = call(port, "GET", route)
            assert status == 200, route
            assert b"Coming soon" in body, f"{route} should be the holding page"
            assert b'href="/account/signin"' in body, f"{route} has no way in"
            # None of the product leaks through.
            assert b"start</html>" not in body and b"library</html>" not in body
    finally:
        server.shutdown()


def test_the_catalogue_is_shut(tmp_path: Path) -> None:
    """Nothing is open to strangers yet, and that is a decision rather than an oversight.

    The public surface is built and tested — see the test below — but it stays closed
    until there is something worth arriving at and a whitelist deciding who may come in.
    """
    port, _, server = hosted(tmp_path)
    try:
        for route in ("/library", "/library/il-declaration", "/library/ruth"):
            status, body, _ = call(port, "GET", route)
            assert b"The Land of Israel" not in body, f"{route} leaked a text"
            if status == 200:
                assert b"Coming soon" in body, f"{route} should be the door"
            else:
                assert status == 404, route
    finally:
        server.shutdown()


def test_a_shut_site_tells_crawlers_to_stay_out(tmp_path: Path) -> None:
    """The half-open state is the harmful one.

    A robots.txt that invites a crawler while every page it can reach says "Coming soon"
    gets the holding page indexed — and that is then what ranks for the product's own
    name later, long after there is something better to show.
    """
    port, _, server = hosted(tmp_path)
    try:
        status, robots, _ = call(port, "GET", "/robots.txt")
        assert status == 200
        assert b"Disallow: /\n" in robots
        assert b"Allow:" not in robots
        assert call(port, "GET", "/sitemap.xml")[0] == 404, "nothing to offer yet"
    finally:
        server.shutdown()


def test_the_catalogue_opens_when_the_deployment_says_so(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The machinery is proven now so that opening it later is one variable, not a build.

    Signed out, /library is the public index: the texts and no more than the texts — no
    shelf of somebody's own builds, no trash, nothing belonging to a person.
    """
    monkeypatch.setenv("TARGUM_PUBLIC_SHELVES", "1")
    port, _, server = hosted(tmp_path)
    try:
        status, body, _ = call(port, "GET", "/library")
        assert status == 200
        assert b"Coming soon" not in body, "/library is the shop window now"
        assert b'href="/account/signin"' in body, "/library has no way in"
        assert b"Your targums" not in body, "/library leaked the product"
        assert b"Trash" not in body, "/library leaked the product"

        status, body, _ = call(port, "GET", "/library/il-declaration")
        assert status == 200 and b"The Land of Israel" in body

        assert call(port, "GET", "/sitemap.xml")[0] == 200
        assert b"Disallow: /\n" not in call(port, "GET", "/robots.txt")[1]
    finally:
        server.shutdown()


def test_the_holding_page_offers_one_thing_to_press(tmp_path: Path) -> None:
    """ "Coming soon" was a pill first and read as a button on a page with nothing else
    to press, which is a promise the page cannot keep."""
    from targum.render.builder import holding_page

    page = holding_page()
    assert "Coming soon" in page
    soon = page[page.index('class="soon"') : page.index("</p>", page.index('class="soon"'))]
    assert "<button" not in soon
    css = (Path(__file__).resolve().parents[1] / "src/targum/render/assets/holding.css").read_text()
    rule = css[css.index(".middle .soon {") : css.index("}", css.index(".middle .soon {"))]
    assert "border" not in rule and "radius" not in rule, "it must not look pressable"


def test_data_routes_answer_as_data(tmp_path: Path) -> None:
    port, _, server = hosted(tmp_path)
    try:
        status, body, _ = call(port, "GET", "/readers")
        assert status == 401
        assert body["signIn"] == "/account/signin"
    finally:
        server.shutdown()


def test_the_door_is_still_reachable_without_an_account(tmp_path: Path) -> None:
    port, _, server = hosted(tmp_path)
    try:
        status, body, _ = call(port, "GET", "/account/signin")
        assert status == 200
        assert b'type="email"' in body, "the sign-in page must still be a form"
        assert b"Coming soon" not in body
    finally:
        server.shutdown()


def test_the_about_page_is_open_to_strangers(tmp_path: Path) -> None:
    """It is the one page whose whole point is being readable without an account."""
    port, _, server = hosted(tmp_path)
    try:
        status, body, _ = call(port, "GET", "/about")
        assert status == 200
        assert b"under construction" in body
        assert b"Coming soon" not in body, "the holding page must not swallow it"
    finally:
        server.shutdown()


def test_the_holding_page_links_to_it(tmp_path: Path) -> None:
    port, _, server = hosted(tmp_path)
    try:
        _, body, _ = call(port, "GET", "/")
        assert b'href="/about"' in body
    finally:
        server.shutdown()


def test_signing_out_shows_the_holding_page_once_an_account_exists(tmp_path: Path) -> None:
    """What "signed out" means depends on whether anybody ever signed in.

    A fresh install has one person, it is theirs, and asking them to make an account to
    read their own files would be absurd — so it opens and works. The moment somebody
    signs up, the machine is being used as targum-with-accounts and signing out means
    what it means everywhere else. Without this, the holding page was only ever visible
    with an environment variable set, which is to say never.
    """
    from targum.accounts import Store

    store = Store(tmp_path / "w.db")
    assert store.anyone() is False

    store.start_sign_in("someone@example.com")
    assert store.anyone() is True


def test_the_about_page_is_reachable_from_inside_the_app() -> None:
    """It is the open-source half made visible, and a link only on the front door means
    nobody who is signed in ever finds it."""
    from targum.render.builder import add_page, learn_page, library_page, progress_page

    for page in (library_page("k"), learn_page("k"), progress_page("k"), add_page("k")):
        assert 'href="/about"' in page


def _book(folder: Path, chapters: int, translated: int) -> None:
    """A book on disk with `translated` of its `chapters` already paid for."""
    from targum.models import BlockKind, Segment, SegmentedDocument, Translation

    segments, ids = [], []
    for c in range(1, chapters + 1):
        segments.append(
            Segment(
                id=f"h{c}",
                block_id=f"b{c}",
                block_index=c,
                index=len(segments),
                text=f"Chapter {c}",
                kind=BlockKind.heading,
                level=1,
            )
        )
        for n in range(3):
            segments.append(
                Segment(
                    id=f"s{c}-{n}",
                    block_id=f"b{c}",
                    block_index=c,
                    index=len(segments),
                    text=f"line {n}",
                    kind=BlockKind.paragraph,
                )
            )
            ids.append((c, f"s{c}-{n}"))
    folder.mkdir(parents=True, exist_ok=True)
    SegmentedDocument(
        document_hash="book", language="he", segmenter="t/1", segments=segments
    ).write(folder / "segments.json")
    (folder / "reader").mkdir(exist_ok=True)
    (folder / "reader" / "index.html").write_text("<p>x</p>", encoding="utf-8")
    (folder / "document.json").write_text(
        json.dumps({"title": "A Book", "language": "he", "content_hash": "book"}),
        encoding="utf-8",
    )
    done = {sid: "translated" for c, sid in ids if c <= translated}
    done |= {f"h{c}": "Chapter" for c in range(1, translated + 1)}
    Translation(
        name="English",
        document_hash="book",
        source_language="he",
        target_language="en",
        provider="null",
        segments=done,
    ).write(folder / "translations" / "null.natural.en.json")


def test_a_chapter_already_translated_is_not_bought_again(
    served: tuple[int, str, Path],
) -> None:
    """The regression that costs money.

    The reader asks for the next chapter once you are 60% through this one, every time,
    knowing nothing about what is on disk. A catalogue text is free and arrives complete,
    so every one of its chapters is ready from the start — and every prefetch against one
    was a purchase waiting to happen. It happened: Song of Songs 4 was machine-translated
    for $0.023 beside the published Metsudah text that already covered it, and the reader
    then offered a choice between them.
    """
    port, key, out = served
    _book(out / "local" / "book-he", chapters=3, translated=1)

    status, answer, _ = call(port, "POST", f"/chapter?k={key}", {"name": "book-he", "number": 1})
    assert status == 200
    assert answer == {"ready": True}, "chapter 1 is already translated"
    assert "id" not in answer, "and no job was made to translate it again"


def test_a_chapter_that_is_missing_is_still_bought(served: tuple[int, str, Path]) -> None:
    """Or the guard has turned the feature off rather than fixed it."""
    port, key, out = served
    _book(out / "local" / "book-he", chapters=3, translated=1)

    status, answer, _ = call(port, "POST", f"/chapter?k={key}", {"name": "book-he", "number": 3})
    assert status == 200
    assert answer.get("id"), "chapter 3 has no translation, so it is a job"
    assert answer.get("ready") is not True


def test_a_page_is_compressed_for_a_browser_that_takes_it(served: tuple[int, str, Path]) -> None:
    """A reader page is around 180 kB, most of it the same stylesheet and script every
    other page carries. In production Caddy compresses; served straight from here,
    nothing else will."""
    port, key, out = served
    build = out / "local" / "book-he" / "reader"
    build.mkdir(parents=True)
    page = "<html><body>" + ("שלום עולם " * 4000) + "</body></html>"
    (build / "index.html").write_text(page, encoding="utf-8")

    connection = HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        connection.request(
            "GET",
            f"/reader/book-he/reader/index.html?k={key}",
            headers={"Accept-Encoding": "gzip"},
        )
        response = connection.getresponse()
        body = response.read()
        assert response.status == 200
        assert response.getheader("Content-Encoding") == "gzip"
        assert response.getheader("Vary") == "Accept-Encoding"
        assert len(body) < len(page.encode("utf-8")) / 2
        assert gzip.decompress(body).decode("utf-8") == page
    finally:
        connection.close()


def test_a_browser_that_does_not_ask_gets_it_whole(served: tuple[int, str, Path]) -> None:
    port, key, out = served
    build = out / "local" / "book-he" / "reader"
    build.mkdir(parents=True)
    page = "<html><body>" + ("שלום עולם " * 4000) + "</body></html>"
    (build / "index.html").write_text(page, encoding="utf-8")

    connection = HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        connection.request(
            "GET",
            f"/reader/book-he/reader/index.html?k={key}",
            headers={"Accept-Encoding": "identity"},
        )
        response = connection.getresponse()
        body = response.read()
        assert response.getheader("Content-Encoding") is None
        assert body.decode("utf-8") == page
    finally:
        connection.close()


def _video_part(out: Path, body: bytes) -> str:
    """A sidecar part under a reader, and the address that reaches it."""
    build = out / "local" / "book-he" / "reader" / "video"
    build.mkdir(parents=True)
    (build / "part-001.mp4").write_bytes(body)
    return "/reader/book-he/reader/video/part-001.mp4"


def _ask(port: int, path: str, **headers: str) -> tuple[Any, bytes]:
    connection = HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        connection.request("GET", path, headers=headers)
        response = connection.getresponse()
        return response, response.read()
    finally:
        connection.close()


def test_a_video_part_is_served_as_video_not_text(served: tuple[int, str, Path]) -> None:
    """The general file route says text/plain for everything that is not a page, and a
    video sent as text is a video no browser plays."""
    port, key, out = served
    reel = b"\x00\x00\x00\x18ftypmp42" + bytes(range(256)) * 8
    where = _video_part(out, reel)

    response, body = _ask(port, f"{where}?k={key}", **{"Accept-Encoding": "gzip"})
    assert response.status == 200
    assert response.getheader("Content-Type") == "video/mp4"
    assert response.getheader("Accept-Ranges") == "bytes", "Safari will not play without this"
    assert response.getheader("Content-Encoding") is None, "the codec already compressed it"
    assert body == reel


def test_safaris_two_byte_probe_gets_a_real_206(served: tuple[int, str, Path]) -> None:
    """Safari opens every video with `bytes=0-1` and refuses to play unless the answer
    is a real 206 — the failure is silent, and only on Safari."""
    port, key, out = served
    reel = bytes(range(256))
    where = _video_part(out, reel)

    response, body = _ask(port, f"{where}?k={key}", Range="bytes=0-1")
    assert response.status == 206
    assert response.getheader("Content-Range") == f"bytes 0-1/{len(reel)}"
    assert body == reel[:2]


def test_a_seek_is_an_open_ended_range(served: tuple[int, str, Path]) -> None:
    port, key, out = served
    reel = bytes(range(256))
    where = _video_part(out, reel)

    response, body = _ask(port, f"{where}?k={key}", Range="bytes=100-")
    assert response.status == 206
    assert response.getheader("Content-Range") == f"bytes 100-255/{len(reel)}"
    assert body == reel[100:]


def test_the_tail_index_is_a_suffix_range(served: tuple[int, str, Path]) -> None:
    """A plain mp4 keeps its index at the end, and a player reads it as `bytes=-N`."""
    port, key, out = served
    reel = bytes(range(256))
    where = _video_part(out, reel)

    response, body = _ask(port, f"{where}?k={key}", Range="bytes=-4")
    assert response.status == 206
    assert response.getheader("Content-Range") == f"bytes 252-255/{len(reel)}"
    assert body == reel[-4:]


def test_a_range_past_the_end_is_refused(served: tuple[int, str, Path]) -> None:
    port, key, out = served
    where = _video_part(out, bytes(256))

    response, body = _ask(port, f"{where}?k={key}", Range="bytes=999999-")
    assert response.status == 416
    assert response.getheader("Content-Range") == "bytes */256"
    assert body == b""


def test_a_malformed_range_gets_the_whole_file_and_an_inverted_one_is_refused(
    served: tuple[int, str, Path],
) -> None:
    """Per the RFC an unparseable Range is ignored; a parseable lie is refused."""
    port, key, out = served
    reel = bytes(range(256))
    where = _video_part(out, reel)

    response, body = _ask(port, f"{where}?k={key}", Range="bytes=abc")
    assert response.status == 200
    assert body == reel
    response, _body = _ask(port, f"{where}?k={key}", Range="bytes=5-2")
    assert response.status == 416


def test_a_kept_part_is_revalidated_not_refetched(served: tuple[int, str, Path]) -> None:
    """A part is tens of megabytes and content-stable: the browser that kept it asks
    again with If-Modified-Since, and 304 is the whole answer."""
    port, key, out = served
    where = _video_part(out, bytes(64))

    response, _body = _ask(port, f"{where}?k={key}")
    stamp = response.getheader("Last-Modified")
    assert stamp, "no validator means a full re-download every day"
    again, body = _ask(port, f"{where}?k={key}", **{"If-Modified-Since": stamp})
    assert again.status == 304
    assert body == b""


def test_a_video_outside_the_reader_roots_stays_unreachable(
    served: tuple[int, str, Path],
) -> None:
    """The media branch answers inside the same three guarded roots, not a new door."""
    port, key, out = served
    (out / "elsewhere.mp4").write_bytes(bytes(64))

    response, _ = _ask(port, f"/reader/../elsewhere.mp4?k={key}")
    assert response.status == 404


def test_a_shelf_row_says_what_the_text_is(tmp_path: Path) -> None:
    """The library sorts and filters on these, and it draws them for the reader's own
    texts as well as for catalogue ones — an article somebody pasted in this morning is
    in the same list as Genesis."""
    from targum.models import Block, BlockKind, Document, Segment, SegmentedDocument, Translation
    from targum.render import render

    out = tmp_path / "targum-out"
    folder = out / "local" / "article-he"
    folder.mkdir(parents=True)
    document = Document(
        source="https://www.ynet.co.il/news/article/x",
        title="A News Article",
        language="he",
        blocks=[Block(id="b0", kind=BlockKind.paragraph, text=" ".join(["מלה"] * 260))],
    )
    document.content_hash = document.recompute_hash()
    segment = Segment(id="s1", block_id="b0", block_index=0, index=0, text="מלה")
    segmented = SegmentedDocument(
        document_hash=document.content_hash, language="he", segmenter="t/1", segments=[segment]
    )
    translation = Translation(
        name="English",
        document_hash=document.content_hash,
        source_language="he",
        target_language="en",
        provider="null",
        segments={segment.id: "word"},
    )
    document.write(folder / "document.json")
    segmented.write(folder / "segments.json")
    (folder / "translations").mkdir()
    translation.write(folder / "translations" / "null.natural.en.json")
    render(document, segmented, [translation], folder / "reader")

    row = Library(out).readers(out / "local")[0]

    assert row["kind"] == "article", "a web address is a piece of journalism"
    assert row["register"] == "modern"
    assert row["words"] == 260
    assert row["minutes"] == 2, "260 words at 130 a minute"


def test_a_catalogue_text_is_described_by_the_catalogue(tmp_path: Path) -> None:
    """Its difficulty is measured off the whole text by a script that runs for minutes.
    Nothing worked out at page-draw time could be better than that."""
    from targum.catalogue import CATALOGUE
    from targum.models import Block, BlockKind, Document, Segment, SegmentedDocument, Translation
    from targum.render import render

    entry = next(e for e in CATALOGUE if e.id == "psalms")
    out = tmp_path / "targum-out"
    folder = out / "local" / "psalms-he"
    folder.mkdir(parents=True)
    document = Document(
        source=entry.source,
        title=entry.title,
        language="he",
        blocks=[Block(id="b0", kind=BlockKind.paragraph, text="שלום")],
    )
    document.content_hash = document.recompute_hash()
    segment = Segment(id="s1", block_id="b0", block_index=0, index=0, text="שלום")
    segmented = SegmentedDocument(
        document_hash=document.content_hash, language="he", segmenter="t/1", segments=[segment]
    )
    translation = Translation(
        name="English",
        document_hash=document.content_hash,
        source_language="he",
        target_language="en",
        provider="null",
        segments={segment.id: "peace"},
    )
    document.write(folder / "document.json")
    segmented.write(folder / "segments.json")
    (folder / "translations").mkdir()
    translation.write(folder / "translations" / "null.natural.en.json")
    render(document, segmented, [translation], folder / "reader")

    row = Library(out).readers(out / "local")[0]

    assert row["entry"] == "psalms"
    assert row["kind"] == "poetry" and row["register"] == "biblical"
    assert row["difficulty"] == entry.difficulty
    assert row["minutes"] == entry.minutes, "the whole book, not the one line built here"
    assert row["english"] == "Psalms", "and the title a reader with no Hebrew can read"

    # The reader carries it too — its tab title and its bar — with no cache key touched:
    # it is render-time context, like the cover. One section, so this is the standalone
    # reader rather than a contents page.
    page = (folder / "reader" / "index.html").read_text(encoding="utf-8")
    assert '<span class="bar-english" lang="en" dir="ltr">Psalms</span>' in page
    assert "<title>תהילים · Psalms</title>" in page


def test_an_upload_has_no_english_title_anywhere(tmp_path: Path) -> None:
    """The reader gave it a Hebrew title and that is what every page shows: no line, no
    fallback to a description, and the row says so with an empty string."""
    from targum.models import Block, BlockKind, Document, Segment, SegmentedDocument, Translation
    from targum.render import render

    out = tmp_path / "targum-out"
    folder = out / "local" / "mine-he"
    folder.mkdir(parents=True)
    document = Document(
        source="paste:mine",
        title="שלי",
        language="he",
        blocks=[Block(id="b0", kind=BlockKind.paragraph, text="שלום")],
    )
    document.content_hash = document.recompute_hash()
    segment = Segment(id="s1", block_id="b0", block_index=0, index=0, text="שלום")
    segmented = SegmentedDocument(
        document_hash=document.content_hash, language="he", segmenter="t/1", segments=[segment]
    )
    translation = Translation(
        name="English",
        document_hash=document.content_hash,
        source_language="he",
        target_language="en",
        provider="null",
        segments={segment.id: "peace"},
    )
    document.write(folder / "document.json")
    segmented.write(folder / "segments.json")
    (folder / "translations").mkdir()
    translation.write(folder / "translations" / "null.natural.en.json")
    render(document, segmented, [translation], folder / "reader")

    row = Library(out).readers(out / "local")[0]
    assert row["entry"] == "" and row["english"] == ""
    page = (folder / "reader" / "index.html").read_text(encoding="utf-8")
    # The stylesheet inlined into every reader names `.bar-english`; the markup is what
    # must be absent.
    assert '<span class="bar-english"' not in page and '<p class="english"' not in page
    assert "<title>שלי</title>" in page


def test_a_cover_is_served_and_only_from_the_covers_directory(
    served: tuple[int, str, Path],
) -> None:
    port, key, out = served
    thumbs = out / "thumbs"
    thumbs.mkdir()
    (thumbs / "psalms.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 40)
    (out / "secret.png").write_bytes(b"not yours")

    def fetch(path: str) -> tuple[int, bytes]:
        # Not `get`: a cover is bytes, and that helper reads every body as JSON.
        connection = HTTPConnection("127.0.0.1", port, timeout=5)
        try:
            connection.request("GET", path)
            response = connection.getresponse()
            return response.status, response.read()
        finally:
            connection.close()

    status, body = fetch(f"/thumb/psalms?k={key}")
    assert status == 200
    assert body.startswith(b"\x89PNG")

    missing, _ = fetch(f"/thumb/nothing-here?k={key}")
    assert missing == 404, "a text with no cover drawn yet is not an error"

    climbing, _ = fetch(f"/thumb/..%2Fsecret?k={key}")
    assert climbing == 404


def built_catalogue_text(out: Path, entry_id: str, titles: list[str]) -> Path:
    """One catalogue text on disk, with chapters, as a build would leave it."""
    from targum.catalogue import CATALOGUE
    from targum.models import (
        Block,
        BlockKind,
        Document,
        Segment,
        SegmentedDocument,
        Translation,
    )

    entry = next(e for e in CATALOGUE if e.id == entry_id)
    folder = out / "local" / f"{entry_id}-he"
    folder.mkdir(parents=True, exist_ok=True)
    blocks, segments = [], []
    for index, title in enumerate(titles):
        blocks.append(Block(id=f"h{index}", kind=BlockKind.heading, level=2, text=title))
        blocks.append(Block(id=f"b{index}", kind=BlockKind.paragraph, text="שלום עולם"))
        segments.append(
            Segment(
                id=f"s{index}h",
                block_id=f"h{index}",
                block_index=index * 2,
                index=0,
                kind=BlockKind.heading,
                level=2,
                text=title,
            )
        )
        segments.append(
            Segment(
                id=f"s{index}b",
                block_id=f"b{index}",
                block_index=index * 2 + 1,
                index=0,
                text="שלום עולם",
            )
        )
    document = Document(source=entry.source, title=entry.title, language="he", blocks=blocks)
    document.content_hash = document.recompute_hash()
    segmented = SegmentedDocument(
        document_hash=document.content_hash, language="he", segmenter="t/1", segments=segments
    )
    document.write(folder / "document.json")
    segmented.write(folder / "segments.json")
    (folder / "translations").mkdir(exist_ok=True)
    Translation(
        name="English",
        document_hash=document.content_hash,
        source_language="he",
        target_language="en",
        provider="null",
        segments={segment.id: "x" for segment in segments},
    ).write(folder / "translations" / "null.natural.en.json")
    (folder / "reader").mkdir(exist_ok=True)
    (folder / "reader" / "index.html").write_text("<p>x</p>", encoding="utf-8")
    return folder


def test_only_chapters_that_name_something_are_drawn(tmp_path: Path) -> None:
    """A hundred and fifty psalms are numbered rather than titled, and "Psalms, chapter
    1" is not a subject anything could draw. Those fall back to the book's cover, which
    costs nothing and matches it exactly."""
    out = tmp_path / "targum-out"
    folder = built_catalogue_text(out, "judenstaat", ["פתח דבר", "פרק א", "השאלה היהודית"])

    entry, plan = Library(out).cover_plan(folder, chapters=True)

    assert entry is not None and entry.id == "judenstaat"
    names = [name for name, _ in plan]
    assert names[0] == "judenstaat", "the book comes first, so its chapters can match it"
    assert len(names) == 3, "the numbered chapter is not drawn"
    assert all(name.startswith("judenstaat-c") for name in names[1:])


def test_a_text_the_catalogue_never_heard_of_is_drawn_from_itself(tmp_path: Path) -> None:
    """A catalogue cover is drawn from what the catalogue says a text is — its author,
    the sentence describing it — and an upload has none of that. It has a title and an
    opening, which is enough, and the picture is filed under its own folder rather than a
    catalogue id — with the shelf in front of it, because `thumbs/` is one directory for
    the whole box and a folder name is unique only within one home. It belongs to one
    text on one shelf, and the name has to say which."""
    from targum.models import Block, BlockKind, Document

    out = tmp_path / "targum-out"
    folder = out / "local" / "mine-he"
    folder.mkdir(parents=True)
    document = Document(
        source="https://example.invalid/x",
        title="Mine",
        language="he",
        blocks=[Block(id="b0", kind=BlockKind.paragraph, text="שלום")],
    )
    document.content_hash = document.recompute_hash()
    document.write(folder / "document.json")

    entry, plan = Library(out).cover_plan(folder, chapters=True)

    assert entry is not None and entry.id == "local-mine-he"
    assert [name for name, _ in plan] == ["local-mine-he"], "the book, and no chapters"
    assert "Mine" in plan[0][1] and "שלום" in plan[0][1]
    assert "no lettering" in plan[0][1].lower(), "and the brand's rules, the same as any"


def test_a_folder_with_nothing_in_it_is_not_drawn(tmp_path: Path) -> None:
    out = tmp_path / "targum-out"
    folder = out / "local" / "empty-he"
    folder.mkdir(parents=True)

    assert Library(out).cover_plan(folder, chapters=False) == (None, [])


def test_a_chapter_is_drawn_in_the_style_of_its_book(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """The cover goes first and is handed to every chapter after it as a reference. That
    is what makes a set look like a set — more than any amount of describing a palette."""
    from targum import covers as covers_module
    from targum.serve import Job

    asked: list[tuple[str, bytes | None]] = []

    def picture(shade: int) -> bytes:
        """A real image, because what comes back is really decoded and shrunk."""
        from io import BytesIO

        from PIL import Image

        kept = BytesIO()
        Image.new("RGB", (1024, 1536), (shade, shade, shade)).save(kept, format="PNG")
        return kept.getvalue()

    class Fake:
        name = "fake/1"
        price = 0.04

        def available(self) -> tuple[bool, str]:
            return True, "fake"

        def draw(self, prompt: str, reference: bytes | None = None) -> bytes:
            asked.append((prompt, reference))
            return picture(len(asked))

    monkeypatch.setattr(covers_module, "build", Fake)

    out = tmp_path / "targum-out"
    folder = built_catalogue_text(out, "judenstaat", ["פתח דבר", "השאלה היהודית"])
    library = Library(out)
    entry, plan = library.cover_plan(folder, chapters=True)
    job = Job(id="j1", source=entry.source, options={"cover": entry.id, "plan": plan})

    library.run_covers(job)

    assert job.stage == "done"
    assert len(asked) == 3, "the book and both of its chapters"
    assert asked[0][1] is None, "a book has nothing to match"
    # The cover as it came back, not the tile kept from it: a 320px thumbnail is a poor
    # thing to hand an image model as a reference.
    assert asked[1][1] == picture(1), "and every chapter matches the book"
    assert asked[2][1] == picture(1)

    kept = out / "thumbs" / "judenstaat.webp"
    assert kept.is_file()
    assert kept.stat().st_size < len(picture(1)) / 10, "and what is kept is a tile"
    assert job.spent == pytest.approx(3 * 0.04), "what was drawn, not what was reserved"


def test_nothing_is_drawn_without_a_key(served: tuple[int, str, Path]) -> None:
    """The one provider here that is not Anthropic, and the app runs fine without it:
    every tile falls back to the text's own first letter."""
    from targum import covers

    assert covers.build().available()[0] is False
    port, key, out = served
    built_catalogue_text(out, "judenstaat", ["פתח דבר"])
    status, body, _ = call(port, "POST", f"/cover?k={key}", {"name": "judenstaat-he"})
    assert status == 400
    assert "OPENAI_API_KEY" in str(body.get("error", ""))


# -- who you are, over the wire --------------------------------------------------


def test_a_name_is_yours_to_set_and_is_not_the_address(
    served: tuple[int, str, Path], postbox: Postbox
) -> None:
    """An address is what signs you in; a name is what the app calls you. Until one is
    given, the initials come off the address so the corner is never empty."""
    port, token, _ = served
    cookie = sign_in(port, postbox, "yosef.cohen@example.com")

    _, before, _ = call(port, "GET", f"/account/me?k={token}", cookie=cookie)
    assert before["name"] == ""
    assert before["initials"] == "YC", "the address stands in until a name arrives"

    status, after, _ = call(
        port, "POST", f"/account/name?k={token}", {"name": "  Yosef  Cohen  "}, cookie=cookie
    )
    assert status == 200
    assert after["name"] == "Yosef Cohen", "tidied on the way in"
    assert after["initials"] == "YC"

    _, again, _ = call(port, "GET", f"/account/me?k={token}", cookie=cookie)
    assert again["name"] == "Yosef Cohen", "and it stayed"


def test_naming_needs_a_session(served: tuple[int, str, Path]) -> None:
    """The key opens the door to the app; only a session says which account."""
    port, token, _ = served
    status, payload, _ = call(port, "POST", f"/account/name?k={token}", {"name": "Nobody"})
    assert status == 401
    assert payload["signedIn"] is False


# -- bringing your own ------------------------------------------------------------


def test_a_translation_you_already_have_is_taken_and_lined_up(
    served: tuple[int, str, Path], postbox: Postbox
) -> None:
    """Supplying one is what makes a build free: the pipeline pays for a machine
    translation only when nothing else was handed to it. What arrives here is written
    down and named in the job's options, where the builder reads it."""
    import base64

    port, token, out = served
    cookie = sign_in(port, postbox)
    hebrew = base64.b64encode("שלום עולם.\nזה טקסט.".encode()).decode()
    english = base64.b64encode(b"Hello world.\nThis is a text.").decode()

    status, job, _ = call(
        port,
        "POST",
        f"/prepare?k={token}",
        {
            "name": "mine.txt",
            "content": hebrew,
            "translationName": "mine.en.txt",
            "translationContent": english,
            "to": "en",
            "from": "he",
        },
        cookie=cookie,
    )
    assert status == 200, job
    assert not job.get("error"), job

    # Both files are on disk under this deployment's own uploads, never at a path the
    # request named. The job carries the translation's path in its options, which is
    # where `Build` reads it from — see `_builder`.
    written = sorted(path.name for path in out.rglob("uploads/*/*"))
    assert written == ["mine.en.txt", "mine.txt"]
    theirs = next(out.rglob("uploads/*/mine.en.txt"))
    assert theirs.read_bytes() == base64.b64decode(english)


def test_a_translation_has_to_be_something_targum_can_read(
    served: tuple[int, str, Path], postbox: Postbox
) -> None:
    import base64

    port, token, _ = served
    cookie = sign_in(port, postbox)
    status, answer, _ = call(
        port,
        "POST",
        f"/prepare?k={token}",
        {
            "name": "mine.txt",
            "content": base64.b64encode("שלום".encode()).decode(),
            "translationName": "mine.pdf",
            "translationContent": base64.b64encode(b"%PDF-1.4").decode(),
        },
        cookie=cookie,
    )
    assert status == 400
    assert "pdf" in answer["error"].lower()


@pytest.mark.parametrize(
    ("view", "expected"),
    [
        ({"to": "de"}, "translates into"),
        ({"from": "fr"}, "reads"),
    ],
)
def test_a_pair_the_page_does_not_offer_is_refused(
    served: tuple[int, str, Path], postbox: Postbox, view: dict[str, str], expected: str
) -> None:
    """A picker is not a boundary. The page offers three languages in and two out because
    those are the pairs an upload has been taken end to end in; anything else is refused
    before a file is written rather than half-built."""
    import base64

    port, token, _ = served
    cookie = sign_in(port, postbox)
    status, answer, _ = call(
        port,
        "POST",
        f"/prepare?k={token}",
        {"name": "mine.txt", "content": base64.b64encode("שלום".encode()).decode(), **view},
        cookie=cookie,
    )
    assert status == 400
    assert expected in answer["error"]


def test_working_out_the_language_is_still_allowed(
    served: tuple[int, str, Path], postbox: Postbox
) -> None:
    """Hebrew, Aramaic and Yiddish look alike on a page in a script they share. Somebody
    with an unlabelled text can hand the question over, and an empty `from` means that."""
    import base64

    port, token, _ = served
    cookie = sign_in(port, postbox)
    status, answer, _ = call(
        port,
        "POST",
        f"/prepare?k={token}",
        {"name": "mine.txt", "content": base64.b64encode("שלום".encode()).decode(), "from": ""},
        cookie=cookie,
    )
    assert status == 200, answer


def test_an_uploaded_texts_cover_is_not_the_whole_boxs(tmp_path: Path) -> None:
    """`thumbs/` is one directory for the whole box, and a folder name is unique only
    within one shelf: `free_name` keeps two of a reader's own texts apart and knows
    nothing of anybody else's. Two readers who each upload something called "notes" must
    not share one file — the second would be told it was already drawn and shown the
    first reader's picture of the first reader's text."""
    from targum.models import Block, Document
    from targum.serve import Library

    library = Library(tmp_path)
    plans = []
    for home in ("p3", "p7"):
        folder = tmp_path / home / "notes"
        folder.mkdir(parents=True)
        Document(
            source="upload:notes",
            title="Notes",
            language="he",
            blocks=[Block(id="b1", text="שלום")],
        ).write(folder / "document.json")
        mine, plan = library.cover_plan(folder, chapters=False)
        plans.append((mine.id, plan))

    assert plans[0][0] == "p3-notes" and plans[1][0] == "p7-notes"
    assert plans[0][1] and plans[1][1], "neither reader is told the other's is theirs"


def test_a_catalogue_cover_is_still_shared(tmp_path: Path) -> None:
    """The prefix is only for uploads. A catalogue text is the same text for everyone,
    so its cover is drawn once and shown to all of them."""
    from targum.catalogue import CATALOGUE
    from targum.serve import OWNED

    for entry in CATALOGUE:
        assert not OWNED.match(entry.id), f"{entry.id} reads as somebody's upload"


def test_one_readers_cover_is_not_served_to_another(served: tuple[int, str, Path]) -> None:
    """The route puts the asker's own home on the name. Asking for a name that already
    carries one is asking for a file by somebody else's key, and `thumbs/` being one
    directory for the whole box is what would answer."""
    port, key, out = served
    thumbs = out / "thumbs"
    thumbs.mkdir(exist_ok=True)
    (thumbs / "p3-notes.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 40)
    (thumbs / "local-notes.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"1" * 40)

    def fetch(path: str) -> tuple[int, bytes]:
        connection = HTTPConnection("127.0.0.1", port, timeout=5)
        try:
            connection.request("GET", path)
            response = connection.getresponse()
            return response.status, response.read()
        finally:
            connection.close()

    borrowed, _ = fetch(f"/thumb/p3-notes?k={key}")
    assert borrowed == 404, "another reader's upload is not reachable by its own key"

    # This server answers signed out, so `local` is the home it puts on — the reader
    # asks for the text's name and gets their own file, never the other one.
    own, body = fetch(f"/thumb/notes?k={key}")
    assert own == 200
    assert body.endswith(b"1" * 40), "the asker's own, not the p3 shelf's"
