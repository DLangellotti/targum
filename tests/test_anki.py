"""The Anki deck with each word's sound (targum-internal#496): the `.apkg` the server
builds, and the export that makes the sounds a deck still needs."""

from __future__ import annotations

import io
import json
import sqlite3
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Any

import pytest
import test_serve
from test_serve import Postbox, call, sign_in

from targum import anki

served = test_serve.served
postbox = test_serve.postbox


def opened(package: bytes) -> tuple[dict[str, str], list[tuple[str, str]], dict[str, bytes]]:
    """The media map, each note's fields and tags, and the media files, from an apkg."""
    with zipfile.ZipFile(io.BytesIO(package)) as archive:
        media = json.loads(archive.read("media"))
        files = {name: archive.read(number) for number, name in media.items()}
        with tempfile.TemporaryDirectory() as where:
            path = Path(where) / "c.anki2"
            path.write_bytes(archive.read("collection.anki2"))
            connection = sqlite3.connect(path)
            notes = connection.execute("SELECT flds, tags FROM notes ORDER BY id").fetchall()
            cards = connection.execute("SELECT count(*) FROM cards").fetchone()[0]
            col = connection.execute("SELECT ver, models, decks FROM col").fetchone()
            connection.close()
    assert cards == len(notes), "a card per note"
    assert col[0] == 11, "schema 11, which every Anki since 2.1 imports"
    assert "targum word" in col[1] and "targum Hebrew" in col[2]
    return media, notes, files


def test_a_deck_carries_a_word_s_sound_and_a_word_without_one_imports_silently(
    tmp_path: Path,
) -> None:
    clip = tmp_path / "clip.mp3"
    clip.write_bytes(b"ID3 fake mp3")
    package = anki.build(
        "targum Hebrew",
        [
            anki.Note("סֵפֶר", "book", ("targum", "targum::level-2"), "he:ספר", clip),
            anki.Note("דֶּרֶךְ", "road", ("targum",), "he:דרך", None),
        ],
    )
    media, notes, files = opened(package)
    assert len(media) == 1
    (name,) = media.values()
    assert files[name] == b"ID3 fake mp3"
    by_word = {fields.split("\x1f")[0]: (fields.split("\x1f"), tags) for fields, tags in notes}
    assert by_word["סֵפֶר"][0] == ["סֵפֶר", "book", f"[sound:{name}]"]
    assert by_word["סֵפֶר"][1].split() == ["targum", "targum::level-2"]
    assert by_word["דֶּרֶךְ"][0][2] == "", "no sound, and still a note"


def test_a_word_s_note_is_the_same_note_in_the_next_export() -> None:
    first = anki.build("targum Hebrew", [anki.Note("ספר", "book", (), "he:ספר")])
    second = anki.build("targum Hebrew", [anki.Note("ספר", "a book", (), "he:ספר")])

    def ids(package: bytes) -> list[tuple[int, str]]:
        with zipfile.ZipFile(io.BytesIO(package)) as archive, tempfile.TemporaryDirectory() as w:
            path = Path(w) / "c.anki2"
            path.write_bytes(archive.read("collection.anki2"))
            connection = sqlite3.connect(path)
            rows = connection.execute("SELECT id, guid FROM notes").fetchall()
            connection.close()
            return rows

    assert ids(first) == ids(second), "importing again updates, never duplicates"


def wait(port: int, token: str, cookie: str, deck: str) -> dict[str, Any]:
    for _ in range(100):
        _, said, _ = call(port, "GET", f"/account/anki?id={deck}&k={token}", cookie=cookie)
        if said.get("state") != "making":
            return said
        time.sleep(0.05)
    raise AssertionError("the deck never finished")


def keep(port: int, token: str, cookie: str, *words: tuple[str, str, int]) -> None:
    """Words on the account, as a reader's page syncs them: (lemma, surface, status)."""
    rows = [
        {"language": "he", "lemma": lemma, "surface": surface, "status": status, "at": n + 1,
         "seen": n + 1}
        for n, (lemma, surface, status) in enumerate(words)
    ]  # fmt: skip
    status, said, _ = call(port, "POST", f"/sync?k={token}", {"words": rows}, cookie=cookie)
    assert status == 200, said


@pytest.fixture
def voice(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> list[str]:
    from targum import speech

    monkeypatch.setenv("TARGUM_CACHE_DIR", str(tmp_path / "cache"))
    said: list[str] = []

    def render(text: str, into: Path, voice: str = speech.VOICE, language: str = "he") -> Any:
        said.append(text)
        into.parent.mkdir(parents=True, exist_ok=True)
        target = into.with_suffix(".wav")
        target.write_bytes(speech.wav(b"\x00" * speech.BYTES_PER_SECOND))
        return speech.Clip(target, "audio/wav", 1.0)

    monkeypatch.setattr(speech, "render", render)
    monkeypatch.setenv(speech.KEY, "k")
    return said


def test_the_export_makes_the_sounds_a_deck_still_needs_on_targum(
    served: tuple[int, str, Path], postbox: Postbox, voice: list[str]
) -> None:
    import urllib.request

    port, token, _ = served
    status, refused, _ = call(port, "POST", f"/account/anki?k={token}", {"language": "he"})
    assert status == 401, refused

    cookie = sign_in(port, postbox)
    keep(port, token, cookie, ("ספר", "ספר", 2), ("דרך", "דרך,", 1), ("שם", "שם", 0))
    payload = {"language": "he", "deck": "targum Hebrew", "backs": {"ספר": "book <b>"}}
    status, started, _ = call(port, "POST", f"/account/anki?k={token}", payload, cookie=cookie)
    assert status == 200 and started["id"], started
    done = wait(port, token, cookie, started["id"])
    assert done["state"] == "ready" and done["silent"] == 0 and done["total"] == 2, done
    assert sorted(voice) == ["דרך", "ספר"], "each saved word once, comma trimmed, ignored left out"

    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/account/anki/deck?id={started['id']}&k={token}",
        headers={"Cookie": cookie},
    )
    with urllib.request.urlopen(request) as response:
        package = response.read()
        assert "attachment" in response.headers["Content-Disposition"]
    media, notes, _ = opened(package)
    assert len(media) == 2 and len(notes) == 2
    assert any("book &lt;b&gt;" in fields for fields, _tags in notes), "the back is escaped"

    # The clips are kept by the word: a second export says nothing again and claims nothing.
    status, again, _ = call(port, "POST", f"/account/anki?k={token}", payload, cookie=cookie)
    assert wait(port, token, cookie, again["id"])["state"] == "ready"
    assert len(voice) == 2
    gone, _, _ = call(
        port, "GET", f"/account/anki/deck?id={started['id']}&k={token}", cookie=cookie
    )
    assert gone == 404, "fetched once, then gone"


def test_a_request_cannot_have_the_voice_say_what_the_account_does_not_keep(
    served: tuple[int, str, Path], postbox: Postbox, voice: list[str]
) -> None:
    """qa on #854: the words come from the account, and the guard /say-word keeps holds."""
    port, token, _ = served
    cookie = sign_in(port, postbox)
    long = "א" * 70
    keep(port, token, cookie, ("ספר", "ספר", 2), ("ארוך", long, 2))
    payload = {"language": "he", "words": [{"term": "anything at all", "lemma": "x"}]}
    _, started, _ = call(port, "POST", f"/account/anki?k={token}", payload, cookie=cookie)
    done = wait(port, token, cookie, started["id"])
    assert voice == ["ספר"], "only a saved word, and never one past the guard"
    assert done["silent"] == 1


def test_the_month_s_cap_holds_across_exports(
    served: tuple[int, str, Path],
    postbox: Postbox,
    voice: list[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from targum import serve

    monkeypatch.setattr(serve, "ANKI_MOST", 1)
    port, token, _ = served
    cookie = sign_in(port, postbox)
    keep(port, token, cookie, ("ספר", "ספר", 2), ("דרך", "דרך", 2))
    payload = {"language": "he"}
    _, first, _ = call(port, "POST", f"/account/anki?k={token}", payload, cookie=cookie)
    got = wait(port, token, cookie, first["id"])
    assert got["silent"] == 1, got
    _, second, _ = call(port, "POST", f"/account/anki?k={token}", payload, cookie=cookie)
    assert wait(port, token, cookie, second["id"])["silent"] == 1
    assert len(voice) == 1, "the month's one new sound was made once, not once an export"


def test_without_the_voice_the_deck_still_comes_silent(
    served: tuple[int, str, Path], postbox: Postbox, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from targum import speech

    port, token, _ = served
    monkeypatch.setenv("TARGUM_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.delenv(speech.KEY, raising=False)
    monkeypatch.delenv(speech.VERTEX_KEY, raising=False)
    cookie = sign_in(port, postbox)
    keep(port, token, cookie, ("ספר", "ספר", 2))
    _, started, _ = call(
        port, "POST", f"/account/anki?k={token}", {"language": "he"}, cookie=cookie
    )
    done = wait(port, token, cookie, started["id"])
    assert done["state"] == "ready" and done["silent"] == 1 and done["making"] == 0


def test_making_stops_at_the_claim(
    served: tuple[int, str, Path], postbox: Postbox, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """qa on #854: the claim is two seconds a word; a voice that runs long stops there."""
    from targum import speech

    monkeypatch.setenv("TARGUM_CACHE_DIR", str(tmp_path / "cache"))
    said: list[str] = []

    def long_render(text: str, into: Path, voice: str = speech.VOICE, language: str = "he") -> Any:
        said.append(text)
        into.parent.mkdir(parents=True, exist_ok=True)
        target = into.with_suffix(".wav")
        target.write_bytes(speech.wav(b"\x00" * speech.BYTES_PER_SECOND))
        return speech.Clip(target, "audio/wav", 5.0)  # far past two seconds

    monkeypatch.setattr(speech, "render", long_render)
    monkeypatch.setenv(speech.KEY, "k")
    port, token, _ = served
    cookie = sign_in(port, postbox)
    keep(port, token, cookie, ("ספר", "ספר", 2), ("דרך", "דרך", 2), ("עיר", "עיר", 2))
    _, started, _ = call(
        port, "POST", f"/account/anki?k={token}", {"language": "he"}, cookie=cookie
    )
    done = wait(port, token, cookie, started["id"])
    # Claimed 6 s; the second clip brings the made seconds to 10, so the third is not made.
    assert len(said) == 2 and done["silent"] == 1, (said, done)


def test_the_deck_is_the_words_on_screen(
    served: tuple[int, str, Path], postbox: Postbox, voice: list[str]
) -> None:
    port, token, _ = served
    cookie = sign_in(port, postbox)
    keep(port, token, cookie, ("ספר", "ספר", 2), ("דרך", "דרך", 2))
    payload = {"language": "he", "lemmas": ["ספר", "not-saved"]}
    _, started, _ = call(port, "POST", f"/account/anki?k={token}", payload, cookie=cookie)
    done = wait(port, token, cookie, started["id"])
    assert done["total"] == 1 and voice == ["ספר"], "what the page shows, and only if saved"
    status, said, _ = call(
        port, "POST", f"/account/anki?k={token}", {"language": "he", "lemmas": []}, cookie=cookie
    )
    assert status == 400 and said["error"] == "There are no saved words here to put in a deck."


def test_a_capped_deck_says_so(
    served: tuple[int, str, Path],
    postbox: Postbox,
    voice: list[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from targum import serve

    monkeypatch.setattr(serve, "ANKI_MOST", 1)
    port, token, _ = served
    cookie = sign_in(port, postbox)
    keep(port, token, cookie, ("ספר", "ספר", 2), ("דרך", "דרך", 2))
    _, started, _ = call(
        port, "POST", f"/account/anki?k={token}", {"language": "he"}, cookie=cookie
    )
    assert wait(port, token, cookie, started["id"])["capped"] is True
