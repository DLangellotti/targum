"""Where a word comes round, on the card (targum-internal#95, #96), behind a switch.

Built on David's call of 2026-09-28: both cards were gated on readers, a gate that cannot
be met while there are none, so the card line is built now and shown only where the box
says `TARGUM_OCCURRENCES`. Off, `/word/met` is not there and the card is the card it was,
which is the half of this file that matters most. On, the card says how often the word
comes round in this text and in the Tanakh, where the reader met it, and how many words
of its root they have met — with the root the way in to them.

The index itself is `test_occurrences.py`; the card in a browser is
`test_occurrences_card_browser.py`.
"""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlencode

import pytest
import test_serve
from test_occurrences import _jonah, rooted
from test_serve import Postbox, call, sign_in

from targum import occurrences

served = test_serve.served
postbox = test_serve.postbox

KNOWN = 9


@pytest.fixture(autouse=True)
def _fresh_cache() -> None:
    occurrences._cached.cache_clear()


def shelf(out: Path) -> None:
    """Jonah on the shared shelf, with roots, and a paper with no verses on it."""
    rooted(_jonah(out / "shared" / "jonah"))
    paper = rooted(_jonah(out / "shared" / "paper"))
    segments = json.loads((paper / "segments.json").read_text(encoding="utf-8"))
    segments["document_hash"] = "paper-hash"
    for segment in segments["segments"]:
        segment["ref"] = ""
    (paper / "segments.json").write_text(json.dumps(segments), encoding="utf-8")
    (paper / "document.json").write_text(
        json.dumps({"title": "A Paper", "content_hash": "paper-hash", "language": "he"}),
        encoding="utf-8",
    )


def finish(port: int, token: str, cookie: str) -> None:
    """Chapter 1 of Jonah and all of the paper finished; ים known, דג being learned."""
    rows = [
        {"hash": "jonah-hash", "section": "1", "at": 10, "seen": 10},
        {"hash": "paper-hash", "section": "1", "at": 20, "seen": 20},
        {"hash": "paper-hash", "section": "2", "at": 30, "seen": 30},
    ]
    words = [
        {"language": "he", "lemma": "ים", "status": KNOWN, "at": 1, "seen": 1},
        {"language": "he", "lemma": "דג", "status": 2, "at": 1, "seen": 1},
    ]
    status, answer, _ = call(
        port, "POST", f"/sync?k={token}", {"sections": rows, "words": words}, cookie=cookie
    )
    assert status == 200, answer


def ask(token: str, **fields: str) -> str:
    """The card's question, on Jonah 2 — which the reader has not finished — by default."""
    asked = {"k": token, "document": "jonah-hash", "section": "2", "lemma": "ים", "root": "ימם"}
    return "/word/met?" + urlencode({**asked, **fields})


def test_off_the_route_is_not_there_and_the_account_says_so(
    served: tuple[int, str, Path], postbox: Postbox, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("TARGUM_OCCURRENCES", raising=False)
    port, token, out = served
    shelf(out)
    cookie = sign_in(port, postbox)
    status, answer, _ = call(port, "GET", f"/account/me?k={token}", cookie=cookie)
    assert status == 200 and answer["occurrences"] is False
    status, _, _ = call(port, "GET", ask(token), cookie=cookie)
    assert status == 404


def test_on_the_card_is_told_where_the_word_comes_round(
    served: tuple[int, str, Path], postbox: Postbox, monkeypatch: pytest.MonkeyPatch
) -> None:
    """In this text and in the Tanakh; met in Jonah 1:4 by verse and in the paper by its
    title, once; and the root's words met — ים and, from the paper, דג — one of them known.
    The reader is on Jonah 2, which they have not finished, so it names nothing."""
    monkeypatch.setenv("TARGUM_OCCURRENCES", "1")
    port, token, out = served
    shelf(out)
    cookie = sign_in(port, postbox)
    status, answer, _ = call(port, "GET", f"/account/me?k={token}", cookie=cookie)
    assert answer["occurrences"] is True
    finish(port, token, cookie)

    status, answer, _ = call(port, "GET", ask(token), cookie=cookie)
    assert status == 200, answer
    assert answer["here"] == 2
    assert answer["tanakh"] == occurrences.in_tanakh("ים") > 300
    assert answer["met"] == ["A Paper", "Jonah 1:4"], "latest first; the paper once, by title"
    assert answer["more"] == 0
    assert answer["family"] == {"met": 2, "known": 1, "words": ["ים", "דג"]}

    # On the page it was met on, that page is not a place it was met.
    status, answer, _ = call(port, "GET", ask(token, section="1", root=""), cookie=cookie)
    assert answer["met"] == ["A Paper"] and "family" not in answer, "no root asked, none said"


def test_on_one_readers_meetings_are_never_anothers(
    served: tuple[int, str, Path], postbox: Postbox, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TARGUM_OCCURRENCES", "1")
    port, token, out = served
    shelf(out)
    finish(port, token, sign_in(port, postbox))
    other = sign_in(port, postbox, "someone.else@example.com")
    status, answer, _ = call(port, "GET", ask(token), cookie=other)
    assert status == 200
    assert answer["met"] == [] and answer["family"] == {"met": 0, "known": 0, "words": []}
    assert answer["here"] == 2, "how often it comes round is nobody's in particular"


def test_on_signed_out_there_is_nobody_to_have_met_it(
    served: tuple[int, str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TARGUM_OCCURRENCES", "1")
    port, token, out = served
    shelf(out)
    status, answer, _ = call(port, "GET", ask(token))
    assert status == 401 and answer == {"signedIn": False}
