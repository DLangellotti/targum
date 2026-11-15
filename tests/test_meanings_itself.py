"""Meanings in the language itself, bought a tap at a time (targum-internal#538, design.md
§12, 2026-11-14).

A reader who chose it for a learned language gets a word's meaning in that language on a
card, bought one word at a time through `/gloss` and its shared cache. Nobody else can
make targum buy one, a build never does, and the Words page never asks. The model is
faked throughout: nothing here spends.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from collections.abc import Callable, Iterator
from http.client import HTTPConnection
from pathlib import Path
from typing import Any

import pytest

from targum import serve
from targum.accounts import MEANINGS_IN_ITSELF, Store, meanings_open
from targum.annotate import gloss as gloss_module
from targum.annotate.gloss import (
    SYSTEM,
    Sense,
    build_glossary,
    gloss_key,
    gloss_one,
    system_for,
    unpointed,
)
from targum.cache import Cache
from targum.models import Annotation, Token

ASSETS = Path(__file__).parents[1] / "src" / "targum" / "render" / "assets"


class FakeGlosses:
    """A provider that records what it is asked and answers every word."""

    name = "fake-gloss/1"

    def __init__(self) -> None:
        self.asked: list[tuple[list[str], str, str]] = []

    def gloss(self, lemmas, source_language, target_language, on_progress=None, contexts=None):  # type: ignore[no-untyped-def]
        self.asked.append((list(lemmas), source_language, target_language))
        return {lemma: Sense(f"{target_language} meaning of {lemma}", "noun") for lemma in lemmas}


def annotation_with(*lemmas: str) -> Annotation:
    return Annotation(
        document_hash="h",
        language="he",
        annotator="t",
        method="frequency",
        method_note="n",
        tokens={
            "s1": [Token(start=0, end=1, surface=lemma, lemma=lemma, band=2) for lemma in lemmas]
        },
    )


# -- the prompt and the cache ---------------------------------------------------------


def test_a_pair_keeps_its_prompt_and_the_language_itself_has_its_own() -> None:
    """Every pair already bought is asked exactly as before, so nothing held is bought
    again; only source == target is asked for a definition in the language, and Hebrew's
    is asked unpointed (Decision 3)."""
    assert system_for("he", "en") == SYSTEM.format(source="Hebrew", target="English")
    assert system_for("he", "ru") == SYSTEM.format(source="Hebrew", target="Russian")
    itself = system_for("he", "he")
    assert itself != SYSTEM.format(source="Hebrew", target="Hebrew")
    assert "simple Hebrew" in itself and "without nikkud" in itself
    assert "Never the word itself" in itself
    assert "without nikkud" not in system_for("fr", "fr")


def test_a_hebrew_definition_loses_any_nikkud_the_model_wrote() -> None:
    assert unpointed("מָקוֹם שֶׁגָּרִים בּוֹ") == "מקום שגרים בו"
    # The maqaf is punctuation, not a point, and stays.
    assert unpointed("בֵּית־סֵפֶר") == "בית־ספר"


def test_the_provider_asks_the_language_itself_and_keeps_it_unpointed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Through the real provider with its client faked: the in-language prompt is the
    system prompt, and the gloss comes back without points while the citation keeps
    them."""
    asked: list[str] = []

    class Usage:
        input_tokens = 10
        output_tokens = 5

    class Messages:
        def parse(self, **kwargs: Any) -> Any:
            asked.append(kwargs["system"])
            batch = gloss_module._Batch(
                entries=[
                    gloss_module._Entry(
                        lemma="בית",
                        gloss="מָקוֹם שֶׁגָּרִים בּוֹ",
                        part_of_speech="noun",
                        plural="בָּתִּים",
                    )
                ]
            )
            return type("R", (), {"parsed_output": batch, "usage": Usage()})()

    provider = gloss_module.AnthropicGlosses(gloss_module.GLOSS_MODEL)
    monkeypatch.setattr(
        provider._provider, "client", lambda: type("C", (), {"messages": Messages()})()
    )
    found = provider.gloss(["בית"], "he", "he")
    assert asked == [system_for("he", "he")]
    assert found["בית"].gloss == "מקום שגרים בו"
    assert found["בית"].plural == "בָּתִּים"
    provider.gloss(["בית"], "he", "en")
    assert asked[-1] == SYSTEM.format(source="Hebrew", target="English")


def test_a_tap_in_the_language_itself_buys_once_under_its_own_key(tmp_path: Path) -> None:
    cache = Cache(tmp_path / "cache")
    provider = FakeGlosses()
    # An English meaning held for the word is never the answer in Hebrew.
    cache.put(
        "gloss",
        gloss_key(cache, "בית", "he", "en", provider.name),
        {"gloss": "house", "grounded": True},
    )
    first = gloss_one("בית", "he", "he", provider, cache=cache, context="הלכתי הביתה")
    assert first is not None and first.gloss == "he meaning of בית"
    again = gloss_one("בית", "he", "he", provider, cache=cache, context="בית גדול")
    assert again == first
    assert provider.asked == [(["בית"], "he", "he")], "bought once, then the cache"
    held = cache.get("gloss", gloss_key(cache, "בית", "he", "he", provider.name))
    assert held["gloss"] == "he meaning of בית"
    english = cache.get("gloss", gloss_key(cache, "בית", "he", "en", provider.name))
    assert english["gloss"] == "house", "the English meaning is untouched"


def test_a_build_never_buys_a_meaning_in_the_language_itself(tmp_path: Path) -> None:
    cache = Cache(tmp_path / "cache")
    provider = FakeGlosses()
    glossary, owed = build_glossary(annotation_with("בית", "ספר"), "he", provider, cache=cache)
    assert provider.asked == []
    assert glossary.entries == {} and owed == 2
    # The translation pair still buys, as it always did.
    build_glossary(annotation_with("בית"), "en", provider, cache=cache)
    assert provider.asked == [(["בית"], "he", "en")]


# -- the account ----------------------------------------------------------------------


def test_the_choice_is_kept_per_language(tmp_path: Path) -> None:
    store = Store(tmp_path / "targum.db")
    # A test account, so that `wipe` below may empty it.
    store.make_test_account("tester@example.com")
    token = store.start_sign_in("tester@example.com")
    signed = store.finish_sign_in(token)
    assert signed is not None
    person = signed[0]
    assert store.meanings_in_itself(person.id) == []
    assert store.set_meanings(person, "he", True) == ["he"]
    assert store.set_meanings(person, "ru", True) == ["he", "ru"]
    assert store.set_meanings(person, "he", False) == ["ru"], "the others stay"
    assert store.meanings_in_itself(person.id) == ["ru"]
    for code in ("arc", "yi", "en", "", "../he"):
        with pytest.raises(ValueError):
            store.set_meanings(person, code, True)
    assert store.meanings_in_itself(person.id) == ["ru"]
    assert store.everything(person)["settings"]["meanings_in_itself"] == ["ru"]
    # A wiped account says nothing of it (deleting one takes the row, and this with it).
    store.wipe(person)
    assert store.meanings_in_itself(person.id) == []


def test_aramaic_and_yiddish_are_never_offered(monkeypatch: pytest.MonkeyPatch) -> None:
    assert "arc" not in MEANINGS_IN_ITSELF and "yi" not in MEANINGS_IN_ITSELF
    monkeypatch.setenv("TARGUM_MEANINGS_OPEN", "he,arc,yi,de")
    assert meanings_open() == frozenset({"he"})
    monkeypatch.delenv("TARGUM_MEANINGS_OPEN")
    # Off on every install until each language's read has passed.
    assert meanings_open() == frozenset()


def test_an_account_from_before_the_column_opens(tmp_path: Path) -> None:
    path = tmp_path / "targum.db"
    store = Store(path)
    token = store.start_sign_in("reader@example.com")
    assert store.finish_sign_in(token) is not None
    store.close()
    # As schema 70 left it: no `meanings` on person.
    db = sqlite3.connect(path)
    db.execute("ALTER TABLE person DROP COLUMN meanings")
    db.execute("PRAGMA user_version = 70")
    db.commit()
    db.close()
    again = Store(path)
    row = again.db.execute("SELECT meanings FROM person").fetchone()
    assert row["meanings"] == ""
    assert again.db.execute("PRAGMA user_version").fetchone()[0] >= 71


# -- the server -----------------------------------------------------------------------


@pytest.fixture(scope="module")
def hosted(
    tmp_path_factory: pytest.TempPathFactory, free_port: Callable[[], int]
) -> Iterator[tuple[int, str, Path]]:
    tmp = tmp_path_factory.mktemp("itself")
    store_path = tmp / "targum.db"
    store = Store(store_path)
    token = store.start_sign_in("reader@example.com")
    signed_in = store.finish_sign_in(token)
    assert signed_in is not None
    port = free_port()
    threading.Thread(
        target=lambda: serve.start(
            out=tmp / "out",
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


def post(port: int, session: str, path: str, payload: dict[str, Any]) -> tuple[int, Any]:
    body = json.dumps(payload).encode()
    conn = HTTPConnection("127.0.0.1", port, timeout=5)
    conn.putrequest("POST", path, skip_host=True)
    conn.putheader("Host", "targum.page")
    conn.putheader("Cookie", f"targum_session={session}")
    conn.putheader("Content-Type", "application/json")
    conn.putheader("Content-Length", str(len(body)))
    conn.endheaders()
    conn.send(body)
    response = conn.getresponse()
    out = json.loads(response.read())
    conn.close()
    return response.status, out


def get(port: int, session: str, path: str) -> Any:
    conn = HTTPConnection("127.0.0.1", port, timeout=5)
    conn.putrequest("GET", path, skip_host=True)
    conn.putheader("Host", "targum.page")
    conn.putheader("Cookie", f"targum_session={session}")
    conn.endheaders()
    response = conn.getresponse()
    out = json.loads(response.read())
    conn.close()
    return out


@pytest.fixture
def bought(monkeypatch: pytest.MonkeyPatch) -> list[tuple[list[str], str, str]]:
    """What the server's provider was asked to buy, with the model faked."""
    asked: list[tuple[list[str], str, str]] = []

    def fake(self, lemmas, source, target, on_progress=None, contexts=None):  # type: ignore[no-untyped-def]
        asked.append((list(lemmas), source, target))
        return {lemma: Sense("מקום שגרים בו", "noun") for lemma in lemmas}

    monkeypatch.setattr(gloss_module.AnthropicGlosses, "gloss", fake)
    monkeypatch.setattr(gloss_module.AnthropicGlosses, "available", lambda self: (True, ""))
    return asked


NOT_THERE = "We can't look words up in that language."


def test_not_chosen_a_meaning_in_the_language_itself_is_refused(
    hosted: tuple[int, str, Path],
    bought: list[tuple[list[str], str, str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    port, session, _ = hosted
    monkeypatch.setenv("TARGUM_MEANINGS_OPEN", "he")
    tap = {"lemma": "חלון", "source": "he", "target": "he", "sentence": "פתחתי את החלון"}
    status, answer = post(port, session, "/gloss", tap)
    assert status == 400 and answer["error"] == NOT_THERE
    assert bought == [], "nothing refused reached the model"


def test_chosen_a_tap_buys_once_and_the_cache_answers_after(
    hosted: tuple[int, str, Path],
    bought: list[tuple[list[str], str, str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    port, session, _ = hosted
    monkeypatch.setenv("TARGUM_MEANINGS_OPEN", "he")
    me = get(port, session, "/account/me")
    assert me["meaningsOffered"] == ["he"] and me["meaningsInItself"] == []

    status, answer = post(port, session, "/account/meanings", {"language": "he", "itself": True})
    assert status == 200 and answer["meaningsInItself"] == ["he"]
    assert get(port, session, "/account/me")["meaningsInItself"] == ["he"]
    assert bought == [], "saving the choice buys nothing"

    peek = {"lemma": "בית", "source": "he", "target": "he", "free": True}
    status, answer = post(port, session, "/gloss", peek)
    assert status == 200 and answer["meaning"] is None and bought == []

    tap = {"lemma": "בית", "source": "he", "target": "he", "sentence": "הלכתי הביתה"}
    status, answer = post(port, session, "/gloss", tap)
    assert status == 200 and answer["meaning"] == "מקום שגרים בו"
    status, answer = post(port, session, "/gloss", tap)
    assert status == 200 and answer["meaning"] == "מקום שגרים בו"
    assert bought == [(["בית"], "he", "he")], "bought once, then the shared cache"
    status, answer = post(port, session, "/gloss", peek)
    assert answer["meaning"] == "מקום שגרים בו" and answer["cached"] is True

    # Only the language chosen: another pair the page names is still refused.
    status, answer = post(port, session, "/gloss", {**tap, "source": "fr", "target": "fr"})
    assert status == 400 and answer["error"] == NOT_THERE
    status, answer = post(port, session, "/gloss", {**tap, "target": "de"})
    assert status == 400

    # And only while the row is offered here.
    monkeypatch.delenv("TARGUM_MEANINGS_OPEN")
    status, answer = post(port, session, "/gloss", {**tap, "lemma": "ספר"})
    assert status == 400 and answer["error"] == NOT_THERE
    assert get(port, session, "/account/me")["meaningsInItself"] == []
    assert len(bought) == 1

    monkeypatch.setenv("TARGUM_MEANINGS_OPEN", "he")
    status, answer = post(port, session, "/account/meanings", {"language": "he", "itself": False})
    assert status == 200 and answer["meaningsInItself"] == []


def test_the_choice_is_refused_where_it_is_not_offered(
    hosted: tuple[int, str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    port, session, _ = hosted
    monkeypatch.delenv("TARGUM_MEANINGS_OPEN", raising=False)
    status, _ = post(port, session, "/account/meanings", {"language": "he", "itself": True})
    assert status == 400, "the switch is off until the read passes"
    monkeypatch.setenv("TARGUM_MEANINGS_OPEN", "he,fr,ru,it")
    for code in ("arc", "yi"):
        status, _ = post(port, session, "/account/meanings", {"language": code, "itself": True})
        assert status == 400, code
    # French is offered here but not learned by this account.
    status, _ = post(port, session, "/account/meanings", {"language": "fr", "itself": True})
    assert status == 400


# -- the pages that never buy ---------------------------------------------------------


def test_your_words_and_practice_never_ask_for_a_meaning() -> None:
    """The Words page and the practice card show a meaning in the language itself only
    where a card already bought it: neither script so much as names `/gloss`."""
    for name in ("lists.js", "charts.js", "yours.js"):
        assert "/gloss" not in (ASSETS / name).read_text(encoding="utf-8"), name
