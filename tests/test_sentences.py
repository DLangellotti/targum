"""The Sentences tab (design.md §12, "Sentences: dictation and fill the gap", 2026-10-27):
which lines are offered for dictation, which words are taken out for a gap, and the whole
of `/account/sentences` end to end."""

from __future__ import annotations

import random
from pathlib import Path
from typing import Any

import test_serve
from test_meetings import text, w
from test_reading_line import ms
from test_serve import Postbox, call, sign_in

from targum import sentences
from targum.audio.manifest import AudioManifest, ManifestPart, write
from targum.coverage import KNOWN

served = test_serve.served
postbox = test_serve.postbox

LINE = "הילד הלך אל הבית"
SHORT = "שלום לך"


def recorded(folder: Path, spans: dict[str, list[float]]) -> Path:
    """A recording beside the text, as an import or a voice bought on Hear keeps one."""
    (folder / "audio").mkdir(exist_ok=True)
    played = folder / "audio" / "part-001.mp3"
    played.write_bytes(b"ID3" + b"x" * 97)
    write(
        folder,
        AudioManifest(
            source=str(played),
            sha256="0",
            duration=30.0,
            language="he",
            parts=[
                ManifestPart(number=1, start=0.0, end=30.0, audio="audio/part-001.mp3", spans=spans)
            ],
        ),
    )
    return played


def book(folder: Path, **kwargs: Any) -> Path:
    return text(
        folder,
        {
            1: [(LINE, [w("ילד", "ילד"), w("בית", "בית")]), (SHORT, [w("שלום", "שלום")])],
            2: [("ספר חדש על השולחן", [w("ספר", "ספר")])],
        },
        **kwargs,
    )


def test_only_a_line_a_recording_already_says_is_offered(tmp_path: Path) -> None:
    folder = book(tmp_path / "t", translation={"s1-0": "The boy went home."})
    played = recorded(folder, {"s1-0": [1.0, 3.5], "s1-1": [4.0, 5.0], "s2-0": [6.0, 8.0]})
    folders = {"book": (folder, "he")}
    heard = sentences.heard_lines([("book", "1", ms(2026, 9))], folders.get, "he")
    assert [line.segment for line in heard] == ["s1-0"], (
        "two words is too short, and section 2 was never finished"
    )
    (line,) = heard
    assert line.path == played and (line.start, line.end) == (1.0, 3.5)
    said = sentences.dictation_item(line, "en", "/heard?t=x")
    assert said["line"] == LINE and said["translation"] == "The boy went home."
    assert said["src"] == "/heard?t=x" and said["chapter"] == 1


def test_a_text_with_no_recording_has_no_dictation(tmp_path: Path) -> None:
    folder = book(tmp_path / "t")
    folders = {"book": (folder, "he")}
    assert sentences.heard_lines([("book", "1", 1)], folders.get, "he") == []


def test_a_line_too_long_to_hold_in_the_ear_is_left_out(tmp_path: Path) -> None:
    folder = book(tmp_path / "t")
    recorded(folder, {"s1-0": [0.0, sentences.SECONDS + 1]})
    folders = {"book": (folder, "he")}
    assert sentences.heard_lines([("book", "1", 1)], folders.get, "he") == []


def test_a_gap_is_a_word_still_being_learned_in_a_line_it_was_met_in(tmp_path: Path) -> None:
    folder = book(tmp_path / "t", pointed={"s1-0": "הַיֶּלֶד הָלַךְ אֶל הַבַּיִת"})
    folders = {"book": (folder, "he")}
    gaps = sentences.gap_items(
        ["בית", "ספר"], [("book", "1", 1)], folders.get, "he", "en", rng=random.Random(1)
    )
    (gap,) = gaps
    assert gap["lemma"] == "בית" and gap["word"] == "בַּיִת"
    assert gap["line"][gap["start"] : gap["end"]] == gap["word"], "the gap is the word marked"


# -- /account/sentences, end to end -----------------------------------------------------


def test_the_sentences_are_nobodys_business_signed_out(served: tuple[int, str, Path]) -> None:
    port, token, _ = served
    status, said, _ = call(port, "GET", f"/account/sentences?language=he&k={token}")
    assert status == 401 and said == {"signedIn": False}


def test_the_sentences_play_from_a_token_and_take_out_a_learning_word(
    served: tuple[int, str, Path], postbox: Postbox
) -> None:
    port, token, out = served
    folder = book(out / "shared" / "one", content_hash="one")
    recorded(folder, {"s1-0": [1.0, 3.5]})
    cookie = sign_in(port, postbox)
    words = [
        {"language": "he", "lemma": "ילד", "status": KNOWN, "at": 1, "seen": 1},
        {"language": "he", "lemma": "בית", "status": 2, "at": 1, "seen": 1},
    ]
    sections = [{"hash": "one", "section": "1", "at": ms(2026, 9), "seen": ms(2026, 9)}]
    status, answer, _ = call(
        port, "POST", f"/sync?k={token}", {"words": words, "sections": sections}, cookie=cookie
    )
    assert status == 200, answer

    status, said, _ = call(port, "GET", f"/account/sentences?language=he&k={token}", cookie=cookie)
    assert status == 200, said
    (line,) = said["dictation"]
    assert line["line"] == LINE and (line["start"], line["end"]) == (1.0, 3.5)
    assert line["src"].startswith("/heard?t=") and "part-001" not in line["src"]
    status, played, _ = call(port, "GET", line["src"])
    assert status == 200 and played.startswith(b"ID3"), "the token opens the recording"
    (gap,) = said["gaps"]
    assert gap["lemma"] == "בית", "a known word is never taken out"
