"""Send to Anki, the page half (targum-internal#540; design.md §12, "Send to Anki talks to
the Anki on your own computer", 2026-11-14), run against a fake AnkiConnect.

The page talks to the reader's own AnkiConnect at 127.0.0.1 and nowhere else; the words
and every clip come from targum's own origin. Anki's `Sent` field is the only record of
what was sent, so a second press with nothing changed writes nothing.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import pytest

HARNESS = Path(__file__).resolve().parent / "js" / "anki_send.js"

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")

NOTETYPE = "targum word and sentence"


def run(**payload: Any) -> dict[str, Any]:
    payload.setdefault("words", [word("ספר", "book"), word("בית", "house")])
    with tempfile.TemporaryDirectory() as where:
        file = Path(where) / "payload.json"
        file.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        done = subprocess.run(
            ["node", str(HARNESS), str(file)], capture_output=True, text=True, timeout=60
        )
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def word(lemma: str, meaning: str, *, stage: int = 2, **more: Any) -> dict[str, Any]:
    """One word as `/account/anki/notes` answers it."""
    one = {
        "key": f"he:{lemma}",
        "lemma": lemma,
        "term": lemma,
        "meaning": meaning,
        "stage": stage,
        "add": stage in (1, 2, 3, 4),
        "before": "",
        "gap": "",
        "after": "",
        "translation": "",
        "source": "",
        "sound": "",
        "soundFile": "",
        "line": "",
        "lineFile": "",
        "tags": f"targum targum::he targum::level-{stage} targum::sent",
        "hash": f"h-{lemma}-{meaning}-{stage}",
    }
    one.update(more)
    return one


def actions(said: dict[str, Any], *, inner: bool = True) -> list[str]:
    return [call["action"] for call in said["calls"] if inner or not call.get("inner")]


def test_send_adds_new_words_then_nothing_the_second_time() -> None:
    said = run(presses=2)
    first, second = said["said"]
    assert first == "Added 2 words to Anki."
    assert second == "Anki already has all your words."
    sent = [note for note in said["notes"] if note["model"] == NOTETYPE]
    assert len(sent) == 2 and {note["deck"] for note in sent} == {"targum Hebrew"}
    assert {note["fields"]["targum"] for note in sent} == {"he:ספר", "he:בית"}
    later = [call["action"] for call in said["calls"][said["callsAt"][0] :]]
    assert not {"addNotes", "updateNoteFields", "updateNoteTags", "storeMediaFile"} & set(later)


def test_a_changed_meaning_updates_one_note_and_never_your_notes() -> None:
    words = [word("ספר", "book"), word("בית", "house")]
    said = run(
        words=words,
        presses=2,
        editBetween=[{"at": 1, "set": {"meaning": "home", "hash": "h-changed"}}],
        anki={},
    )
    assert said["said"][1] == "Updated 1."
    updates = [call for call in said["calls"] if call["action"] == "updateNoteFields"]
    (update,) = updates
    assert update["params"]["note"]["fields"]["Meaning"] == "home"
    assert "Your notes" not in update["params"]["note"]["fields"]
    assert "Word card" not in update["params"]["note"]["fields"]


def test_the_reader_s_own_notes_survive_an_update() -> None:
    old = word("בית", "house")
    held = {
        "model": NOTETYPE,
        "fields": {"targum": "he:בית", "Sent": "old", "Meaning": "house", "Your notes": "mine"},
    }
    said = run(words=[old], anki={"notes": [held], "models": [NOTETYPE]})
    (note,) = said["notes"]
    assert note["fields"]["Your notes"] == "mine" and note["fields"]["Sent"] == old["hash"]


def test_the_page_calls_only_the_allowlisted_actions() -> None:
    allowed = {
        "requestPermission",
        "version",
        "deckNames",
        "createDeck",
        "modelNames",
        "createModel",
        "findNotes",
        "notesInfo",
        "addNotes",
        "updateNoteFields",
        "updateNoteTags",
        "storeMediaFile",
        "multi",
    }
    said = run(
        words=[
            word("ספר", "book", sound="/account/anki/sound?key=he%3Aספר", soundFile="targum-a.wav")
        ],
        presses=2,
        editBetween=[{"at": 0, "set": {"hash": "new"}}],
    )
    assert set(actions(said)) <= allowed
    assert "deleteNotes" not in actions(said)
    for call in said["calls"]:
        assert not call.get("contentType"), "no Content-Type, so no preflight"
    source = (
        Path(__file__).resolve().parent.parent / "src/targum/render/assets/anki-send.js"
    ).read_text(encoding="utf-8")
    for never in ("deleteNotes", "forgetCards", "suspend", "setEaseFactors", "answerCards"):
        assert never not in source, never


def test_deck_and_notetype_are_made_once() -> None:
    said = run(presses=2, editBetween=[{"at": 0, "set": {"hash": "x"}}])
    assert actions(said).count("createDeck") == 1
    assert actions(said).count("createModel") == 1
    (model,) = [call for call in said["calls"] if call["action"] == "createModel"]
    params = model["params"]
    assert params["modelName"] == NOTETYPE and params["isCloze"] is False
    assert [card["Name"] for card in params["cardTemplates"]] == ["Word", "Gap"]
    word_card, gap_card = params["cardTemplates"]
    assert word_card["Front"].startswith("{{#Word card}}") and word_card["Front"].endswith(
        "{{/Word card}}"
    )
    assert gap_card["Front"].startswith("{{#Gap}}") and gap_card["Front"].endswith("{{/Gap}}")
    assert 'dir="auto"' in word_card["Front"] and 'dir="auto"' in gap_card["Back"]
    assert params["inOrderFields"][-1] == "Your notes"


def test_the_clips_come_from_targum_and_go_in_by_their_names() -> None:
    said = run(
        words=[
            word(
                "בית",
                "house",
                sound="/account/anki/sound?key=he%3A%D7%91",
                soundFile="targum-w.mp3",
                line="/account/anki/line?key=he%3A%D7%91",
                lineFile="targum-line-l.mp3",
                before="אל ה",
                gap="בית",
                after="",
            )
        ]
    )
    assert sorted(said["media"]) == ["targum-line-l.mp3", "targum-w.mp3"]
    assert all(url.startswith("/account/anki/") for url in said["targum"])
    (note,) = said["notes"]
    assert note["fields"]["Sound"] == "[sound:targum-w.mp3]"
    assert note["fields"]["Sentence sound"] == "[sound:targum-line-l.mp3]"
    assert note["fields"]["Word card"] == "y"


def test_an_apkg_word_gets_only_its_gap_card() -> None:
    imported = {
        "model": "targum word",
        "fields": {"Word": "בית", "Meaning": "house", "Sound": ""},
        "tags": ["targum", "targum::he"],
    }
    said = run(
        words=[word("בית", "house", gap="בית", before="אל ה"), word("ספר", "book")],
        anki={"notes": [imported]},
    )
    sent = {n["fields"]["targum"]: n for n in said["notes"] if n["model"] == NOTETYPE}
    assert sent["he:בית"]["fields"]["Word card"] == ""
    assert sent["he:ספר"]["fields"]["Word card"] == "y"


def test_a_known_word_is_updated_and_never_added() -> None:
    known = word("עיר", "city", stage=9)
    said = run(words=[known])
    assert said["notes"] == [] and said["said"] == ["Anki already has all your words."]
    held = {"model": NOTETYPE, "fields": {"targum": "he:עיר", "Sent": "old"}}
    said = run(words=[known], anki={"notes": [held], "models": [NOTETYPE]})
    assert said["said"] == ["Updated 1."]


def test_every_value_is_escaped() -> None:
    said = run(words=[word("ספר", "<b>book</b> & 'co'", before='<i>"', gap="ספר")])
    (note,) = said["notes"]
    assert note["fields"]["Meaning"] == "&lt;b&gt;book&lt;/b&gt; &amp; &#39;co&#39;"
    assert note["fields"]["Before"] == "&lt;i&gt;&quot;"


def test_a_word_anki_refuses_is_counted() -> None:
    said = run(anki={"refuse": "he:בית"})
    assert said["said"] == ["Added 1 word to Anki. 1 word couldn't be added."]


# -- every state its line ---------------------------------------------------------------


def test_anki_closed_is_unreachable() -> None:
    said = run(anki={"unreachable": True})
    (line,) = said["said"]
    assert line == (
        "We couldn't reach Anki on this computer. "
        "Open Anki and check that AnkiConnect is installed."
    )


def test_a_browser_that_blocks_the_local_network_says_so() -> None:
    said = run(anki={"unreachable": True}, lna="denied")
    assert said["said"][0].startswith("Your browser is blocking targum from reaching Anki.")


def test_no_in_anki_is_refused() -> None:
    said = run(anki={"permission": "denied"})
    assert said["said"] == ["Anki said no. Press Send to Anki again and choose Yes in Anki."]
    assert actions(said) == ["requestPermission"]


def test_a_key_asked_shows_the_key_field_and_is_sent_after() -> None:
    said = run(anki={"key": "s3cret"}, presses=2, keyBetween="s3cret")
    assert said["said"][0] == "Anki asks for a key. Copy it from AnkiConnect's settings in Anki."
    assert said["said"][1] == "Added 2 words to Anki."
    later = said["calls"][said["callsAt"][0] :]
    assert all(call["key"] == "s3cret" for call in later if not call.get("inner"))
    assert said["keyForm"] is False


def test_an_old_ankiconnect_asks_for_an_update() -> None:
    said = run(anki={"version": 5})
    assert said["said"][0].startswith("AnkiConnect needs an update.")


def test_anki_busy_says_busy() -> None:
    said = run(anki={"busy": "deckNames"})
    assert said["said"] == ["Anki is busy. Close any open windows in Anki and try again."]


def test_offline_says_so_and_asks_nothing() -> None:
    said = run(online=False)
    assert said["said"] == ["You're offline. Send to Anki when you're back online."]
    assert said["calls"] == [] and said["targum"] == []


def test_stopped_midway_says_how_far_and_the_next_press_finishes() -> None:
    many = [word(f"מילה{n}", f"word {n}") for n in range(60)]
    # Nine calls are the set-up and the first batch of 50; the tenth, the second batch, drops.
    said = run(words=many, presses=2, anki={"dropAfter": 9})
    assert said["said"][0] == (
        "We sent 50 of 60 words before the connection dropped. Press Send to Anki to send the rest."
    )
    assert said["said"][1] == "Added 10 words to Anki."
    assert len([n for n in said["notes"] if n["model"] == NOTETYPE]) == 60


# -- where it shows ---------------------------------------------------------------------


def test_send_is_hidden_on_a_coarse_pointer() -> None:
    said = run(fine=False, presses=0)
    assert said["offered"] == {"button": False, "help": False}


def test_send_is_hidden_signed_out() -> None:
    said = run(signedIn=False, presses=0)
    assert said["offered"] == {"button": False, "help": False}


def test_send_shows_at_a_desk_signed_in_and_its_help_opens() -> None:
    said = run(presses=0, help=True)
    assert said["offered"] == {"button": True, "help": True}
    assert said["help"] == {
        "open": True,
        "expanded": "true",
        "scope": "Sends every word you're learning in Hebrew.",
    }
