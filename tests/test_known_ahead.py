"""How many of the next thing's words a reader already knows, counted by targum's own
server (targum-internal#335; David on targum#476, "count on the server").

The first finished foot says it: "You already know 14 words in this one." A page on the
shared shelf is built once for everybody, so the page can carry neither the count nor the
offer's words. It asks `/known-ahead`, naming the page it is on and the offer, and gets
back one number. The page half is `test_reader_js.py` and `test_reader_browser.py`.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import test_serve
from test_reading_line import built, word
from test_serve import Postbox, call, sign_in

from targum import coverage

KNOWN = 9

served = test_serve.served
postbox = test_serve.postbox


def book(out: Path) -> None:
    """A shared text of two sections. The second has one word the first has not (עץ) and
    a name, which is never a word anybody has to know."""
    built(
        out / "shared" / "book",
        {
            1: [[word("ספר"), word("בית"), word("ים")] * 7],
            2: [[word("ים"), word("ספר"), word("עץ"), word("דוד", "PROPN")] * 5],
        },
    )


def test_the_next_section_is_counted_against_the_readers_own_marks(
    served: tuple[int, str, Path], postbox: Postbox
) -> None:
    """The account's ledger, plus the words of the page the reader is on that the page
    says it holds as known — the press's, which the sync may not have carried yet. Only
    words really on that page are taken from it; only a number comes back."""
    port, token, out = served
    book(out)
    cookie = sign_in(port, postbox)
    status, answer, _ = call(
        port,
        "POST",
        f"/sync?k={token}",
        {
            "words": [
                {"language": "he", "lemma": "ספר", "status": KNOWN, "at": 1, "seen": 1},
                {"language": "he", "lemma": "עץ", "status": 2, "at": 1, "seen": 1},
            ]
        },
        cookie=cookie,
    )
    assert status == 200, answer

    ask = {"document": "book", "section": 1, "next": 2, "entry": ""}
    status, answer, _ = call(port, "POST", f"/known-ahead?k={token}", ask, cookie=cookie)
    assert status == 200 and answer == {"known": 1, "connect": False}, (
        "ספר; עץ is being learned; a name is no word"
    )

    # The press just marked ים on this page. עץ is not on this page, so the page cannot
    # say it for the next one, and a word on neither counts for nothing.
    pressed = {**ask, "known": ["ים", "עץ", "זר"]}
    status, answer, _ = call(port, "POST", f"/known-ahead?k={token}", pressed, cookie=cookie)
    assert status == 200 and answer == {"known": 2, "connect": False}


def test_one_readers_marks_are_never_another_readers_count(
    served: tuple[int, str, Path], postbox: Postbox
) -> None:
    port, token, out = served
    book(out)
    first = sign_in(port, postbox)
    call(
        port,
        "POST",
        f"/sync?k={token}",
        {"words": [{"language": "he", "lemma": "ספר", "status": KNOWN, "at": 1, "seen": 1}]},
        cookie=first,
    )
    second = sign_in(port, postbox, "someone.else@example.com")
    ask = {"document": "book", "section": 1, "next": 2}
    status, answer, _ = call(port, "POST", f"/known-ahead?k={token}", ask, cookie=second)
    assert status == 200 and answer == {"known": 0, "connect": False}


def test_signed_out_there_is_nobody_to_count_for(served: tuple[int, str, Path]) -> None:
    port, token, out = served
    book(out)
    ask = {"document": "book", "section": 1, "next": 2, "known": ["ים"]}
    status, answer, _ = call(port, "POST", f"/known-ahead?k={token}", ask)
    assert status == 401 and answer == {"signedIn": False}


def test_a_catalogue_text_is_counted_from_the_index(
    served: tuple[int, str, Path], postbox: Postbox, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The library's next text, by its id, from the index beside the catalogue — which
    the browser never sees. A text the index has not measured, or a page this server has
    no build of, is not measured: None, and the page says nothing."""
    port, token, out = served
    book(out)
    index = out / "lemmas.json"
    coverage.write_index(index, coverage.build_index({"story": ["ספר", "ים", "חדש"]}))
    monkeypatch.setenv("TARGUM_CATALOGUE_LEMMAS", str(index))
    cookie = sign_in(port, postbox)
    call(
        port,
        "POST",
        f"/sync?k={token}",
        {"words": [{"language": "he", "lemma": "ספר", "status": KNOWN, "at": 1, "seen": 1}]},
        cookie=cookie,
    )
    ask = {"document": "book", "section": 2, "entry": "story", "known": ["ים"]}
    status, answer, _ = call(port, "POST", f"/known-ahead?k={token}", ask, cookie=cookie)
    assert status == 200 and answer == {"known": 2, "connect": False}

    for unmeasured in ({**ask, "entry": "unknown"}, {**ask, "document": "elsewhere"}):
        status, answer, _ = call(port, "POST", f"/known-ahead?k={token}", unmeasured, cookie=cookie)
        assert status == 200 and answer == {"known": None, "connect": False}


def test_the_finish_says_whether_to_offer_the_connector(
    served: tuple[int, str, Path],
    postbox: Postbox,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The one moment the page asks about the reader is where the reader's line about
    Claude and ChatGPT is decided (design.md §12, "The connector is met on the way in").
    Only while the connector is open, and only to a reader holding no connection — the
    rule the banner keeps. A connection made anywhere puts it away."""
    from targum.accounts import Store

    port, token, out = served
    book(out)
    cookie = sign_in(port, postbox)
    ask = {"document": "book", "section": 1, "next": 2, "entry": ""}

    status, answer, _ = call(port, "POST", f"/known-ahead?k={token}", ask, cookie=cookie)
    assert status == 200 and answer["connect"] is False, "dark, it is never offered"

    monkeypatch.setenv("TARGUM_CONNECTOR", "1")
    status, answer, _ = call(port, "POST", f"/known-ahead?k={token}", ask, cookie=cookie)
    assert status == 200 and answer["connect"] is True
    # Where the offer cannot be measured the count is not said, and the offer still is.
    elsewhere = {**ask, "document": "elsewhere"}
    status, answer, _ = call(port, "POST", f"/known-ahead?k={token}", elsewhere, cookie=cookie)
    assert answer == {"known": None, "connect": True}

    store = Store(tmp_path / "words.db")
    person = store.person_by_email("reader@example.com")
    assert person is not None
    client = store.register_client("Claude", ["https://claude.ai/api/mcp/auth_callback"])
    store.mint_token(person.id, client, scopes="read")
    status, answer, _ = call(port, "POST", f"/known-ahead?k={token}", ask, cookie=cookie)
    assert status == 200 and answer["connect"] is False, "connected, never asked again"
