"""The pronunciation dictionary the speech hints read (targum-internal#584; language
tables spec §3), with synthetic words only and nothing voiced: the voicer is a fake.

Acceptance 1: a word fixed once by `voice_shelf.py --hint` is hinted on its next
occurrence in another scene. Acceptance 2: an ASR row still `proposed` never reaches
the hints.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

from targum.accounts import Store
from targum.dialogue.checks import pronunciation_hints
from targum.tables import fixes
from targum.tables import pronunciation as pron
from targum.tables.yardstick import directory

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"

#: Made-up words in Hebrew letters, pointed, so no content text is in the suite.
ZOLPIT = "זוֹלְפִית"  # stands where עוֹשָׂה stood: one spelling, two readings
ZOLPET = "זוֹלֶפִית"  # the same letters, pointed otherwise
GORBEN = "גּוֹרְבֵּן"
HINT = f'Read {ZOLPIT} as "zol-PIT", stressed last'


def load(name: str) -> Any:
    sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def scene(sid: str, lines: tuple[str, str]) -> dict[str, Any]:
    return {
        "id": sid,
        "language": "he",
        "english": "",
        "gloss": "",
        "cast": {
            "A": {"voice": "Leda", "gender": "f", "name": "A"},
            "B": {"voice": "Charon", "gender": "m", "name": "B"},
        },
        "turns": [
            {"who": "A", "text": lines[0], "english": "", "start": 0.0, "end": 2.0},
            {"who": "B", "text": lines[1], "english": "", "start": 2.5, "end": 4.0},
        ],
    }


def written(keep: Store) -> dict[str, Any]:
    made = pron.build(keep)
    pron.write(made.lexicon, directory())
    return made.lexicon["forms"]


def test_a_word_fixed_once_by_hint_is_hinted_in_another_scene(tmp_path: Path) -> None:
    """Acceptance 1, end to end through the real writer and the real prompt: the hint
    is given to one turn of one scene, the scene is voiced (by a fake), the hint
    becomes the author's row, the dictionary is written, and the same word in a
    different scene's prompt carries it, with no hint given there."""
    shelf = load("voice_shelf")
    vs = shelf.vs
    keep = Store(tmp_path / "targum.db")
    first = scene("he-91", (f"הִיא {ZOLPIT} עַכְשָׁו.", "טוֹב."))
    later = scene("he-92", ("מָה?", f"אֲנִי {ZOLPIT} מָחָר."))
    assert HINT not in vs.prompt_for(later, 1), "nothing known before the fix"

    shelf.give_hints([first], shelf.read_hints([f"he-91:0={HINT}"]))
    args = type("A", (), {"keep": keep, "hint_kind": "stress", "run_id": "r1"})()
    assert shelf.keep_hints(first, args) == 1
    forms = written(keep)
    assert forms[ZOLPIT]["source"] == "correction"
    assert (directory() / pron.FILE).is_file()

    prompt = vs.prompt_for(later, 1)
    assert f'{ZOLPIT} as "zol-PIT", stressed last' in prompt
    assert f'Read {ZOLPIT} as "zol-PIT"' in prompt, "said inside the list's own Read"
    assert "Read Read" not in prompt
    # The same letters pointed otherwise are another word, and are left alone.
    assert pronunciation_hints(f"הוּא {ZOLPET}") == []
    # A leading conjunction does not change the word.
    assert pronunciation_hints(f"וְ{ZOLPIT}") == [f'{ZOLPIT} as "zol-PIT", stressed last']


def test_an_asr_row_still_proposed_never_reaches_the_hints(tmp_path: Path) -> None:
    """Acceptance 2 (spec, Q5): an ASR flag waits for a human ear. Proposed, it is
    counted as waiting and said nowhere; accepted by a person, it is said; refused,
    it is gone. Whoever filed it, an ASR row needs that acceptance."""
    keep = Store(tmp_path / "targum.db")
    for who in ("model", "author"):
        fixes.record(
            keep,
            stage="asr",
            who=who,
            before=f"אֲנִי {GORBEN} פֹּה",
            after=f'Say {GORBEN} as "gor-BEN"',
            why="heard otherwise by the ASR check",
            kind="stress",
            unit=f"he-93 t{0 if who == 'model' else 1}",
            state="proposed",
        )
    made = pron.build(keep)
    assert made.lexicon["forms"] == {}
    assert made.unsettled == 2
    pron.write(made.lexicon, directory())
    assert pronunciation_hints(f"{GORBEN} בָּא") == []

    waiting = keep.proposed_corrections()
    keep.settle_correction(int(waiting[0]["id"]), accept=True)
    keep.settle_correction(int(waiting[1]["id"]), accept=False)
    forms = written(keep)
    assert set(forms) == {GORBEN}
    assert forms[GORBEN]["evidence"] == 1, "a proposal and its acceptance are one fix"
    assert pronunciation_hints(f"{GORBEN} בָּא") == [f'{GORBEN} as "gor-BEN"']


def test_a_model_fix_is_not_said_until_accepted(tmp_path: Path) -> None:
    keep = Store(tmp_path / "targum.db")
    fixes.record(
        keep,
        stage="voice",
        who="model",
        before=GORBEN,
        after="Say gor-BEN",
        why="x",
        kind="stress",
        unit="he-94 t0",
    )
    assert pron.build(keep).lexicon["forms"] == {}


def test_a_hint_with_no_hebrew_lands_on_a_one_word_line_only(tmp_path: Path) -> None:
    keep = Store(tmp_path / "targum.db")
    for unit, before in (("he-95 t0", f"{GORBEN}!"), ("he-95 t1", f"{GORBEN} {ZOLPET}")):
        fixes.record(
            keep,
            stage="voice",
            who="author",
            before=before,
            after="Say gor-BEN",
            why="x",
            kind="stress",
            unit=unit,
        )
    made = pron.build(keep)
    assert made.lexicon["forms"][GORBEN]["say"] == f"{GORBEN}: gor-BEN"
    assert made.unplaced == 1, "two words and no word named: not guessed"


def test_a_correction_outranks_an_observation(tmp_path: Path) -> None:
    keep = Store(tmp_path / "targum.db")
    fixes.record(
        keep,
        stage="human",
        who="author",
        before=ZOLPIT,
        after=HINT,
        why="settled by ear",
        kind="stress",
        unit="he-96 t0",
    )
    seen = {
        ZOLPIT: {pron.observed_variant(2, False): 12},
        ZOLPET: {pron.observed_variant(1, False): 12},
    }
    forms = pron.build(keep, seen).lexicon["forms"]
    assert forms[ZOLPIT]["source"] == "correction"
    assert forms[ZOLPIT]["say"] == f'{ZOLPIT} as "zol-PIT", stressed last'
    assert forms[ZOLPIT]["stress"] == 2, "the observation is kept as evidence"
    assert forms[ZOLPET]["source"] == "observed"


def test_an_observation_counts_only_past_the_floor_and_where_letters_are_ambiguous() -> None:
    v1, v2 = pron.observed_variant(1, False), pron.observed_variant(2, True)
    few = {ZOLPIT: {v1: pron.FLOOR_SEEN - 1}, ZOLPET: {v2: 40}}
    assert set(pron.observed(few)) == {ZOLPET}
    assert pron.observed(few)[ZOLPET].say == "", "no other reading past the floor"

    split = {ZOLPIT: {v1: 6, v2: 4}, ZOLPET: {v2: 40}}
    assert ZOLPIT not in pron.observed(split), "60% is not agreement"
    near = {ZOLPIT: {v1: 18, v2: 2}, ZOLPET: {v2: 40}}
    assert ZOLPIT not in pron.observed(near), "90% is under David's 95%"
    at = {ZOLPIT: {v1: 19, v2: 1}, ZOLPET: {v2: 40}}
    assert ZOLPIT in pron.observed(at), "95% is enough"

    assert (pron.FLOOR_SEEN, pron.FLOOR_SHARE) == (10, 0.95), "David, 2026-11-08"

    both = {ZOLPIT: {v1: 20}, ZOLPET: {v2: 40}, GORBEN: {v1: 30}}
    seen = pron.observed(both)
    assert seen[ZOLPIT].say == f"{ZOLPIT}: stressed on the last syllable"
    said = f'{ZOLPET}: stressed on the second-to-last syllable, its qamats said "o"'
    assert seen[ZOLPET].say == said
    assert seen[GORBEN].say == "", "one reading of its letters: nothing to say"


def test_the_dictionary_never_goes_into_the_repository(tmp_path: Path) -> None:
    repo = Path(__file__).resolve().parents[1]
    with pytest.raises(ValueError, match="inside the repository"):
        pron.write({"forms": {}}, repo / "src")
    file = pron.write({"forms": {}}, tmp_path / "tables")
    assert json.loads(file.read_text(encoding="utf-8")) == {"forms": {}}


def test_no_dictionary_leaves_the_hints_as_they_were() -> None:
    assert not (directory() / pron.FILE).exists()
    assert pronunciation_hints("לָמָּה עָזַבְתְּ?", "f") == ['עזבת: ends "-t", the feminine']


def test_tables_pronunciation_writes_the_file(tmp_path: Path) -> None:
    from typer.testing import CliRunner

    from targum.cli import app

    db = tmp_path / "targum.db"
    keep = Store(db)
    fixes.record(
        keep,
        stage="voice",
        who="author",
        before=ZOLPIT,
        after=HINT,
        why="x",
        kind="stress",
        unit="he-97 t0",
    )
    out = tmp_path / "tables"
    result = CliRunner().invoke(
        app, ["tables", "pronunciation", "--store", str(db), "--out", str(out)]
    )
    assert result.exit_code == 0, result.output
    forms = json.loads((out / pron.FILE).read_text(encoding="utf-8"))["forms"]
    assert set(forms) == {ZOLPIT}
