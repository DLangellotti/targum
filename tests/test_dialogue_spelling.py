"""A scene's two spellings: full for the plain cell, ktiv menukad for the pointed one
(targum-internal#568).

Made-up lines only: the scenes are proprietary and this repository is public. What the
change does to the 127 real scenes is measured outside it and reported on the card.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from unicodedata import normalize

import pytest

from targum.dialogue import spelling
from targum.dialogue.models import Cast, Dialogue, Speaker, Turn
from targum.ingest.fetch.dialogue import DialogueFetcher
from targum.segment.base import segment_document
from targum.vocalize import aligned_positions, pointed_positions, strip_nikkud

HARNESS = Path(__file__).resolve().parent / "js" / "reader.js"


def nfc(text: str) -> str:
    return normalize("NFC", text)


def scene(*turns: Turn) -> Dialogue:
    return Dialogue(
        id="he-00-test",
        title="בדיקה",
        english="A test",
        cast=Cast(
            A=Speaker(voice="Leda", gender="f", name="דנה"),
            B=Speaker(voice="Charon", gender="m", name="עידו"),
        ),
        turns=list(turns),
    )


# ------------------------------------------------------------------- the alignment

#: (pointed line, plain line it stands for).
LINES = [
    ("חִבּוּר יָפֶה, בֹּקֶר טוֹב.", "חיבור יפה, בוקר טוב."),  # matres dropped mid-word
    ("יָפֶה מְאוֹד", "יפה מאוד"),  # the same letters: the old map exactly
    ("אַסְתְּמָה קַלָּה", "אסטמה קלה"),  # a letter written differently
    ("שִׁשִּׁי וְהַטֶּלֶפוֹן עֲדַיִן", "שישי והטלפון עדיין"),  # dropped at the end of a word
    ("", ""),
]


def words(text: str) -> list[tuple[int, int]]:
    out, at = [], 0
    for piece in text.split(" "):
        out.append((at, at + len(piece)))
        at += len(piece) + 1
    return out


@pytest.mark.parametrize(("pointed", "plain"), LINES)
def test_every_plain_word_lands_on_its_pointed_word(pointed: str, plain: str) -> None:
    pointed, plain = nfc(pointed), nfc(plain)
    index = aligned_positions(pointed, plain)
    assert len(index) == len(plain) + 1
    assert index == sorted(index)
    shown = [pointed[index[start] : index[end]] for start, end in words(plain)]
    assert shown == pointed.split(" ")


def test_the_same_letters_give_the_map_there_always_was() -> None:
    line = nfc("שָׁלוֹם, מָה שְׁלוֹמֵךְ?")
    assert aligned_positions(line, strip_nikkud(line)[0]) == pointed_positions(line)


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_the_browser_aligns_exactly_as_the_build_does(tmp_path: Path) -> None:
    pairs = [[nfc(p), nfc(b)] for p, b in LINES]
    payload = {
        "window": {"width": 1200, "height": 800},
        "card": {"width": 320, "height": 200},
        "words": [],
        "align": pairs,
    }
    where = tmp_path / "payload.json"
    where.write_text(json.dumps(payload), encoding="utf-8")
    done = subprocess.run(
        ["node", str(HARNESS), str(where)], capture_output=True, text=True, timeout=60
    )
    assert done.returncode == 0, done.stderr
    browser = json.loads(done.stdout)["align"]
    assert browser == [aligned_positions(p, b) for p, b in pairs]


# ------------------------------------------------------------- the scene's lines


def test_a_scene_without_pointed_lines_derives_them() -> None:
    written = scene(Turn(who="A", text="חִיבּוּר יֹופִי", english="A nice link"))
    assert nfc(spelling.pointed_line(written.turns[0], spelling.names(written))) == nfc("חִבּוּר יֹפִי")


def test_a_scene_s_own_pointed_line_wins() -> None:
    turn = Turn(who="A", text="חִיבּוּר", pointed="חִבּוּר", english="")
    assert spelling.pointed_line(turn, []) == "חִבּוּר"


def test_an_unpointed_line_has_no_pointed_cell() -> None:
    assert spelling.pointed_line(Turn(who="A", text="שלום"), []) == ""


def test_a_name_in_the_cast_keeps_its_spelling() -> None:
    written = scene(Turn(who="A", text="שָׁלוֹם עִידּוֹ"))
    assert spelling.pointed_line(written.turns[0], spelling.names(written)) == "שָׁלוֹם עִידּוֹ"


def test_the_gate_refuses_full_spelling_and_a_word_out_of_step() -> None:
    assert spelling.refusals(scene(Turn(who="A", text="חִיבּוּר"))) == []
    left = scene(Turn(who="A", text="חִיבּוּר", pointed="חִיבּוּר"))
    assert len(spelling.refusals(left)) == 1
    apart = scene(Turn(who="A", text="חִיבּוּר טוֹב", pointed="חִבּוּר"))
    assert "number of words" in spelling.refusals(apart)[0]


def segmented_of(written: Dialogue, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    monkeypatch.setenv("TARGUM_DIALOGUE_DIR", str(tmp_path))
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / f"{written.id}.json").write_text(written.model_dump_json(), encoding="utf-8")
    from targum.segment.hebrew import HebrewSegmenter

    return segment_document(DialogueFetcher().load(written.id), HebrewSegmenter())


def test_the_vocalization_is_the_scene_s_pointed_lines(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    written = scene(
        Turn(who="A", text="בּוֹקֶר טוֹב. מָה נִשְׁמָע?"),
        Turn(who="B", text="הַכּוֹל בְּסֵדֶר", pointed="הַכֹּל בְּסֵדֶר"),
        Turn(who="A", text="יופי"),
    )
    segmented = segmented_of(written, tmp_path, monkeypatch)
    assert len(segmented.segments) == 3  # a turn is never split
    out = spelling.vocalization(written, segmented)
    assert out.vocalizer == spelling.VOCALIZER
    assert [nfc(out.segments[s.id]) for s in segmented.segments[:2]] == [
        nfc("בֹּקֶר טוֹב. מָה נִשְׁמָע?"),
        nfc("הַכֹּל בְּסֵדֶר"),
    ]
    assert segmented.segments[2].id not in out.segments
    # And the plain cell is what it always was: the text, its points stripped.
    assert [strip_nikkud(s.text)[0] for s in segmented.segments][0] == "בוקר טוב. מה נשמע?"


def test_the_build_points_a_scene_from_the_scene(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from targum.pipeline import Build

    written = scene(Turn(who="A", text="חִיבּוּר טוֹב"))
    segmented_of(written, tmp_path / "scenes", monkeypatch)
    build = Build(f"dialogue:{written.id}", target_language="en", out=tmp_path / "out")
    vocalization = build.vocalize(build.segment(build.ingest()))
    assert vocalization is not None and vocalization.vocalizer == spelling.VOCALIZER
    assert nfc(next(iter(vocalization.segments.values()))) == nfc("חִבּוּר טוֹב")


def test_a_scene_the_gate_refuses_builds_without_vowels(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from targum.pipeline import Build

    written = scene(Turn(who="A", text="חִיבּוּר", pointed="חִיבּוּר"))
    segmented_of(written, tmp_path / "scenes", monkeypatch)
    said: list[str] = []
    build = Build(
        f"dialogue:{written.id}", target_language="en", out=tmp_path / "out", notify=said.append
    )
    assert build.vocalize(build.segment(build.ingest())) is None
    assert any("not ready to ship" in line for line in said)


# ------------------------------------------------------- repairing the pointing


def test_repair_puts_the_pointing_right_without_the_writer() -> None:
    line, left = spelling.repair("תַּחְתֹּם פֶּה בְּבִיט, בְּלִי חִיבּוּר", "Sign here by Bit, no link.", [])
    assert nfc(line) == nfc("תַּחְתֹּם פֹּה בְּבִּיט, בְּלִי חִבּוּר")
    assert left == []


def test_repair_keeps_a_prefix_and_its_dagesh() -> None:
    line, _ = spelling.repair("הַזָּקֵן שֶׁלּוֹ", "His beard.", [])
    assert nfc(line) == nfc("הַזָּקָן שֶׁלּוֹ")


def test_repair_leaves_what_it_cannot_decide_for_a_reader() -> None:
    line, left = spelling.repair("קָנִיתְ", "You bought.", [])
    assert [f.kind for f in left] == ["pointing"]


def test_the_gate_names_a_vav_lost_by_hand() -> None:
    lost = scene(Turn(who="A", text="שָׁלוֹם", pointed="שָׁלֹם"))
    assert "vav" in spelling.refusals(lost)[0]
