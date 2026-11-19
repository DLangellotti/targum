"""Every paid `/gloss` buy goes through the rails (David, 2026-11-19; qa on targum#1335).

A meaning bought on a tap is a job row of kind `gloss`, claimed against the box's daily
ceiling and settled to what the call cost, so the ceiling and the ledger see it. A tap the
cache answers claims nothing and makes no row. A refused claim buys nothing, and the card
keeps what it holds. The hourly limit per account still applies. The model is faked, and
nothing here spends.
"""

from __future__ import annotations

import sqlite3
import threading
import time
from collections.abc import Callable, Iterator
from http.client import HTTPConnection
from pathlib import Path
from typing import Any

import pytest
from test_meanings_itself import post

from targum import serve
from targum.accounts import Store
from targum.annotate import gloss as gloss_module
from targum.annotate.gloss import NO_MEANING, Sense, gloss_key, one_word_estimate, would_buy
from targum.cache import Cache


@pytest.fixture
def hosted(tmp_path: Path, free_port: Callable[[], int]) -> Iterator[tuple[int, str, Path]]:
    """A server of its own for each test, so a day's spending or an hour's taps in one
    never reaches the next."""
    store_path = tmp_path / "targum.db"
    store = Store(store_path)
    token = store.start_sign_in("reader@example.com")
    signed_in = store.finish_sign_in(token)
    assert signed_in is not None
    port = free_port()
    threading.Thread(
        target=lambda: serve.start(
            out=tmp_path / "out",
            port=port,
            open_browser=False,
            store=store_path,
            require_account=True,
            public_address="https://targum.page",
        ),
        daemon=True,
    ).start()
    for _ in range(60):
        try:
            probe = HTTPConnection("127.0.0.1", port, timeout=1)
            probe.request("GET", "/health")
            probe.getresponse().read()
            probe.close()
            break
        except OSError:
            time.sleep(0.1)
    yield port, signed_in[1], store_path


@pytest.fixture
def buys(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Each word the faked model was asked about. Every answer costs a little, as a real
    one does, so a claim is settled to something."""
    asked: list[str] = []

    def fake(self, lemmas, source, target, on_progress=None, contexts=None):  # type: ignore[no-untyped-def]
        asked.extend(lemmas)
        self._provider.spent.add(self.model or "", 400, 30)
        return {lemma: Sense(f"meaning of {lemma}", "noun") for lemma in lemmas}

    monkeypatch.setattr(gloss_module.AnthropicGlosses, "gloss", fake)
    monkeypatch.setattr(gloss_module.AnthropicGlosses, "available", lambda self: (True, ""))
    return asked


def gloss_rows(store: Path) -> list[sqlite3.Row]:
    db = sqlite3.connect(store)
    db.row_factory = sqlite3.Row
    try:
        return db.execute(
            "SELECT id, kind, claimed, spent, gift, stage, source FROM job WHERE kind = 'gloss'"
        ).fetchall()
    finally:
        db.close()


def tap(port: int, session: str, lemma: str, sentence: str = "J'habite ici.") -> tuple[int, Any]:
    return post(
        port,
        session,
        "/gloss",
        {"lemma": lemma, "source": "fr", "target": "en", "sentence": sentence},
    )


def test_a_buy_is_one_claimed_and_settled_job_row(hosted, buys) -> None:  # type: ignore[no-untyped-def]
    port, session, store = hosted
    status, answer = tap(port, session, "maison")
    assert status == 200 and answer["meaning"] == "meaning of maison"
    rows = gloss_rows(store)
    assert len(rows) == 1, "one claim for one buy"
    one = rows[0]
    assert one["gift"] == 1 and one["stage"] == "done" and one["source"] == "gloss:fr-en"
    assert one["spent"] > 0 and one["claimed"] == one["spent"], "settled to what it cost"


def test_a_cached_tap_claims_nothing(hosted, buys) -> None:  # type: ignore[no-untyped-def]
    port, session, store = hosted
    tap(port, session, "jardin")
    assert len(gloss_rows(store)) == 1
    # Grounded now: asked again with a sentence, or peeked, it is the cache's.
    for _ in range(3):
        status, answer = tap(port, session, "jardin")
        assert status == 200 and answer["meaning"] == "meaning of jardin"
    status, _ = post(
        port, session, "/gloss", {"lemma": "jardin", "source": "fr", "target": "en", "free": True}
    )
    assert status == 200
    assert buys == ["jardin"] and len(gloss_rows(store)) == 1, "no row for a cached tap"


def test_the_box_ceiling_refuses_a_buy_and_nothing_is_bought(hosted, buys) -> None:  # type: ignore[no-untyped-def]
    port, session, store = hosted
    # The day's spending already at the ceiling, on rows of any kind.
    db = sqlite3.connect(store)
    db.execute(
        "INSERT INTO job (id, owner, home, source, stage, kind, claimed, made)"
        " VALUES ('spent-day', NULL, '', 'x', 'done', 'build', 1000000, ?)",
        (serve.now(),),
    )
    db.commit()
    db.close()
    status, answer = tap(port, session, "fenêtre")
    assert status == 429 and answer.get("error"), "said plainly, not a failure"
    assert buys == [], "refused: nothing bought"
    refused = gloss_rows(store)
    assert len(refused) == 1 and refused[0]["stage"] == "blocked" and refused[0]["claimed"] == 0


def test_refused_a_held_bare_meaning_is_kept(hosted, buys) -> None:  # type: ignore[no-untyped-def]
    port, session, store = hosted
    # Held without a sentence, as a build buys it: a tap with a sentence would ground it.
    cache = Cache()
    key = gloss_key(
        cache, "porte", "fr", "en", gloss_module.gloss_provider_name(gloss_module.GLOSS_MODEL)
    )
    cache.put(
        "gloss",
        key,
        {
            "gloss": "door",
            "part_of_speech": "noun",
            "citation": "",
            "plural": "",
            "grounded": False,
        },
    )
    db = sqlite3.connect(store)
    db.execute(
        "INSERT INTO job (id, owner, home, source, stage, kind, claimed, made)"
        " VALUES ('spent-day', NULL, '', 'x', 'done', 'build', 1000000, ?)",
        (serve.now(),),
    )
    db.commit()
    db.close()
    status, answer = tap(port, session, "porte")
    assert status == 200 and answer["meaning"] == "door" and answer["grounded"] is False
    assert buys == []


def test_the_hourly_limit_still_holds(hosted, buys, monkeypatch: pytest.MonkeyPatch) -> None:  # type: ignore[no-untyped-def]
    port, session, store = hosted
    monkeypatch.setattr(serve, "GLOSSES_PER_HOUR", 1)
    assert tap(port, session, "chien")[0] == 200
    status, _ = tap(port, session, "chat")
    assert status == 429
    assert buys == ["chien"] and len(gloss_rows(store)) == 1, "the limit refuses before a claim"


def test_would_buy_reads_the_cache_as_gloss_one_decides(tmp_path: Path) -> None:
    cache = Cache(tmp_path / "cache")
    name = "fake/1"
    assert would_buy("mot", "fr", "en", name, cache=cache), "nothing held"
    key = gloss_key(cache, "mot", "fr", "en", name)
    cache.put("gloss", key, {"gloss": "word", "grounded": False})
    assert not would_buy("mot", "fr", "en", name, cache=cache), "held, no sentence"
    assert would_buy("mot", "fr", "en", name, context="Un mot.", cache=cache), "bare, grounding"
    cache.put("gloss", key, {"gloss": "word", "grounded": True})
    assert not would_buy("mot", "fr", "en", name, context="Un mot.", cache=cache)
    # Settled as no meaning in the language itself: never asked again.
    itself = gloss_key(cache, "mot", "fr", "fr", name)
    cache.put("gloss", itself, {"gloss": "", NO_MEANING: True, "grounded": True})
    assert not would_buy("mot", "fr", "fr", name, context="Un mot.", cache=cache)


def test_one_words_reserve_covers_its_prompt() -> None:
    """The claim reserves at least what a single word's call can cost on its prompt alone,
    and stays a fraction of a cent."""
    reserve = one_word_estimate("he", "he", gloss_module.GLOSS_MODEL)
    assert 0 < reserve < 0.01
    assert one_word_estimate("he", "he", gloss_module.GLOSS_MODEL) > gloss_module.estimate(
        1, gloss_module.GLOSS_MODEL
    )
