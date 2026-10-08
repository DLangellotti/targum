"""The score ledger: that a number, once taken, survives the next one."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from targum import evals


def row(**over: object) -> evals.Row:
    base: dict[str, object] = {
        "at": "2026-09-04",
        "stage": "lemma",
        "system": "dicta/joint",
        "version": "1",
        "metric": "lemma",
        "score": 0.842,
        "n": 200,
        "corpus": "iahltwiki",
    }
    base.update(over)
    return evals.Row(**base)  # type: ignore[arg-type]


def test_a_ledger_that_is_not_there_reads_as_empty(tmp_path: Path) -> None:
    assert evals.read(tmp_path / "nothing.jsonl") == []


def test_a_row_survives_the_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "ledger.jsonl"
    assert evals.append([row()], path) == 1
    assert evals.read(path) == [row()]


def test_appending_keeps_what_was_there(tmp_path: Path) -> None:
    path = tmp_path / "ledger.jsonl"
    evals.append([row(score=0.80)], path)
    evals.append([row(score=0.84, version="2")], path)
    scores = [entry.score for entry in evals.read(path)]
    assert scores == [0.80, 0.84], "an append that loses the earlier number is not a ledger"


def test_the_same_version_twice_is_recorded_twice(tmp_path: Path) -> None:
    """#163's fourth criterion: a second run of one version appends an identical score.

    Nothing here may collapse them, because two rows agreeing is the only evidence that
    the harness is deterministic, and a file that de-duplicates has thrown it away.
    """
    path = tmp_path / "ledger.jsonl"
    evals.append([row()], path)
    evals.append([row()], path)
    kept = evals.read(path)
    assert len(kept) == 2
    assert kept[0] == kept[1]


def test_movement_is_measured_against_a_different_version(tmp_path: Path) -> None:
    rows = [
        row(version="1", score=0.80),
        row(version="1", score=0.80),
        row(version="2", score=0.84),
    ]
    pair = evals.moved(rows, rows[0].key())
    assert pair is not None
    older, newer = pair
    assert (older.version, newer.version) == ("1", "2")
    assert round(newer.score - older.score, 4) == 0.04


def test_one_version_has_not_moved_yet(tmp_path: Path) -> None:
    assert evals.moved([row()], row().key()) is None


def test_a_rerun_of_one_version_reports_no_movement() -> None:
    """Two rows of the same version are the determinism check, not a trend. Reading
    them as a trend would report nothing moved and hide the move before them."""
    rows = [
        row(version="1", score=0.80),
        row(version="2", score=0.84),
        row(version="2", score=0.84),
    ]
    pair = evals.moved(rows, rows[0].key())
    assert pair is not None
    assert (pair[0].version, pair[1].version) == ("1", "2")


def test_a_new_system_still_moves_the_same_measurement() -> None:
    """The reason the system is not part of the key. In this codebase an annotator's name
    *is* its version — the name is the cache key — so keying on it would file every
    change under a heading of its own and nothing would ever be seen to move. Stanza to
    DICTA on one corpus is the trend the harness exists to show."""
    rows = [
        row(system="stanza", version="1.14.0", score=0.71),
        row(system="dicta-il/dictabert-joint", version="joint", score=0.842),
    ]
    pair = evals.moved(rows, rows[0].key())
    assert pair is not None
    assert pair[0].system == "stanza" and pair[1].system.startswith("dicta")
    assert round(pair[1].score - pair[0].score, 4) == 0.132


def test_latest_takes_the_last_row_not_the_latest_date() -> None:
    rows = [row(at="2026-09-04", score=0.80), row(at="2026-09-04", score=0.84)]
    assert evals.latest(rows)[rows[0].key()].score == 0.84


def test_a_scorecard_becomes_rows() -> None:
    payload = {
        "gold": {"corpus": "iahltwiki"},
        "cards": [
            {
                "annotator": "dicta-il/dictabert-joint",
                "corpus": "iahltwiki",
                "paired": 4321,
                "rates": {"lemma": 0.842, "pos": 0.974, "binyan_accuracy": None},
            }
        ],
    }
    rows = evals.rows_from_scorecard(payload, at="2026-09-04")
    assert {entry.metric for entry in rows} == {"lemma", "pos"}, "a null rate is not a score"
    assert all(entry.n == 4321 and entry.stage == "lemma" for entry in rows)


def test_a_metric_with_nothing_to_measure_is_left_out() -> None:
    """A base of zero is not a score of zero. Writing it down as one would read, on the
    next run, as a stage that collapsed rather than one that never ran."""
    payload = {"cards": [{"annotator": "x", "corpus": "c", "paired": 0, "rates": {"root": None}}]}
    assert evals.rows_from_scorecard(payload) == []


# -- the gold a row was scored on (targum-internal#351) ---------------------------------


def test_one_file_is_fingerprinted_as_its_own_sha256(tmp_path: Path) -> None:
    """So `shasum -a 256 <file>` re-checks a one-file pin without any of this code."""
    import hashlib

    gold = tmp_path / "gold.txt"
    gold.write_bytes("שָׁלוֹם\n".encode())
    assert evals.fingerprint([gold]) == hashlib.sha256(gold.read_bytes()).hexdigest()[:12]
    assert len(evals.fingerprint([gold])) == 12


def test_a_changed_byte_changes_the_fingerprint_and_order_does_not(tmp_path: Path) -> None:
    first, second = tmp_path / "en.txt", tmp_path / "he.txt"
    first.write_text("one\n")
    second.write_text("אחת\n")
    both = evals.fingerprint([first, second])
    assert evals.fingerprint([second, first]) == both, "the order the script lists is not the set"
    second.write_text("אחד\n")
    assert evals.fingerprint([first, second]) != both


def test_a_directory_is_the_files_in_it(tmp_path: Path) -> None:
    folder = tmp_path / "works"
    (folder / "inner").mkdir(parents=True)
    (folder / "a.txt").write_text("a")
    (folder / "inner" / "b.txt").write_text("b")
    pinned = evals.fingerprint([folder])
    (folder / "inner" / "b.txt").write_text("c")
    assert evals.fingerprint([folder]) != pinned


def test_a_missing_file_is_fingerprinted_rather_than_raised(tmp_path: Path) -> None:
    """The fingerprint is taken after a run that may have spent; it must not lose it."""
    there = tmp_path / "there.txt"
    there.write_text("x")
    gone = evals.fingerprint([there, tmp_path / "gone.txt"])
    assert gone != evals.fingerprint([there])
    assert len(gone) == 12


def test_the_pin_goes_on_the_end_of_the_note(tmp_path: Path) -> None:
    gold = tmp_path / "gold.txt"
    gold.write_text("x")
    mark = f"gold={evals.fingerprint([gold])}"
    assert evals.pinned("", [gold]) == mark
    said = "sentences=120 spent=$0.000"
    assert evals.pinned(said, [gold]) == f"{said} {mark}"
    assert evals.pinned("hand word onsets", [gold]) == f"hand word onsets; {mark}"


def test_a_pinned_row_still_reads_and_checks(tmp_path: Path) -> None:
    """The pin lives in the note, so the schema, `read` and the floors are untouched."""
    gold = tmp_path / "gold.txt"
    gold.write_text("x")
    path = tmp_path / "ledger.jsonl"
    evals.append([row(note=evals.pinned("sentences=1", [gold]))], path)
    (kept,) = evals.read(path)
    assert kept.note.endswith(f"gold={evals.fingerprint([gold])}")
    assert evals.breaches([kept], []) == []


def test_a_scorecard_s_fingerprint_reaches_its_rows() -> None:
    payload = {
        "gold": {"fingerprints": {"iahltwiki": "0123456789ab"}},
        "cards": [
            {"annotator": "a", "corpus": "iahltwiki", "paired": 1, "rates": {"lemma": 0.9}},
            {"annotator": "a", "corpus": "iahltwiki+dict", "paired": 1, "rates": {"lemma": 0.9}},
            {"annotator": "a", "corpus": "other", "paired": 1, "rates": {"lemma": 0.9}},
        ],
    }
    notes = [entry.note for entry in evals.rows_from_scorecard(payload, note="run=1")]
    assert notes == ["run=1 gold=0123456789ab", "run=1 gold=0123456789ab", "run=1"]


def test_the_table_says_what_moved(tmp_path: Path) -> None:
    rows = [row(version="1", score=0.80), row(version="2", score=0.84)]
    drawn = evals.table(rows)
    assert "lemma" in drawn and "+0.0400" in drawn


def test_an_empty_ledger_says_so() -> None:
    assert "No scores" in evals.table([])


def test_rows_are_written_one_per_line_and_stay_readable(tmp_path: Path) -> None:
    """The file is read by `git log -p` as much as by this module."""
    path = tmp_path / "ledger.jsonl"
    evals.append([row(), row(version="2")], path)
    lines = path.read_text().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["stage"] == "lemma"


# --- targum eval: one command for any stage ---------------------------------------

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"


def test_every_eval_script_has_a_name_and_every_name_a_script() -> None:
    """A harness added to `scripts/` without a line in the table is one nobody finds."""
    named = set(evals.SCRIPTS.values())
    assert {path.name for path in SCRIPTS_DIR.glob("eval_*.py")} <= named
    assert all((SCRIPTS_DIR / script).exists() for script in named)
    assert {name.split("/")[0] for name in evals.SCRIPTS} <= set(evals.STAGES)


def test_a_stage_measured_two_ways_names_both_rather_than_picking() -> None:
    assert evals.script_for("lemma/iahlt") == "score_annotation.py"
    with pytest.raises(ValueError, match="lemma/iahlt, lemma/ud"):
        evals.script_for("lemma")
    with pytest.raises(ValueError, match="no eval called 'segment'"):
        evals.script_for("segment")


def test_targum_eval_hands_the_rest_to_the_script_and_its_exit_code_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import subprocess

    from typer.testing import CliRunner

    from targum.cli import app

    ran: list[list[str]] = []

    def run(argv: list[str], check: bool) -> subprocess.CompletedProcess[str]:
        ran.append(argv)
        return subprocess.CompletedProcess(argv, 3)

    monkeypatch.setattr(subprocess, "run", run)
    result = CliRunner().invoke(
        app, ["eval", "vocalize", "--corpus", "dicta-modern", "--ledger", "x.jsonl"]
    )
    assert result.exit_code == 3, result.output
    assert Path(ran[0][1]) == SCRIPTS_DIR / "measure_pointing.py"
    assert ran[0][2:] == ["--corpus", "dicta-modern", "--ledger", "x.jsonl"]


def test_targum_eval_on_a_bare_split_stage_runs_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    import subprocess

    from typer.testing import CliRunner

    from targum.cli import app

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: pytest.fail("ran a script"))
    result = CliRunner().invoke(app, ["eval", "stress"])
    assert result.exit_code == 2
    assert "stress/tanakh-taamim" in result.output


# --- floors: the line a PR may not cross ------------------------------------------


def floor(**over: object) -> evals.Floor:
    base: dict[str, object] = {
        "stage": "lemma",
        "corpus": "iahltwiki",
        "metric": "lemma",
        "system": "dicta",
        "at_least": 0.8,
    }
    base.update(over)
    return evals.Floor(**base)  # type: ignore[arg-type]


def test_a_floor_is_read_off_the_newest_row_of_its_own_system() -> None:
    """The ledger holds every system ever measured against a key. A comparison run of a
    worse system is a measurement, not a regression, so the floor names its system, and
    a name that carries a revision after it still matches."""
    rows = [
        row(system="stanza/1", score=0.70),
        row(system="dicta/joint", version="2", score=0.85),
        row(system="stanza/1", score=0.69),
    ]
    assert evals.breaches(rows, [floor()]) == []
    dropped = rows + [row(system="dicta/joint", version="3", score=0.79)]
    (crossed,) = evals.breaches(dropped, [floor()])
    assert crossed.row.version == "3" and "wanted at least 0.8" in str(crossed)


def test_a_count_of_failures_wants_a_ceiling() -> None:
    rows = [row(metric="unpaired", score=1.0), row(metric="unpaired", score=7.0)]
    assert evals.breaches(rows, [floor(metric="unpaired", at_least=None, at_most=5)])
    assert not evals.breaches(rows[:1], [floor(metric="unpaired", at_least=None, at_most=5)])


def test_a_floor_nobody_has_measured_yet_is_not_a_breach() -> None:
    """A gate that failed on a stage nobody has run would be a gate everybody learns to
    ignore. The floor waits."""
    assert evals.breaches([row()], [floor(stage="align", corpus="", metric="f1")]) == []
    assert evals.breaches([], [floor()]) == []


def test_a_floor_sets_exactly_one_line(tmp_path: Path) -> None:
    path = tmp_path / "floors.json"
    path.write_text(json.dumps([{"stage": "lemma", "corpus": "", "metric": "m", "system": "s"}]))
    with pytest.raises(ValueError, match="exactly one"):
        evals.floors(path)
    path.write_text(
        json.dumps([{"stage": "lemma", "corpus": "", "metric": "m", "system": "s", "at_most": 1}])
    )
    assert evals.floors(path)[0].line() == "at most 1"
    assert evals.floors(tmp_path / "none.json") == []


def test_the_committed_ledger_holds_every_floor_in_the_repository() -> None:
    """The gate itself. A PR that appends a score below its floor fails here, and the
    way through is to move the floor in `evals/floors.json` in the same PR, where the
    reviewer sees the number go down (targum-internal#163, criterion 5)."""
    here = Path(__file__).parent.parent / "evals"
    limits = evals.floors(here / "floors.json")
    assert limits, "the floors file is part of the repository"
    crossed = evals.breaches(evals.read(here / "ledger.jsonl"), limits)
    assert not crossed, "\n".join(str(one) for one in crossed)


# -- the aligner's own eval (targum-internal#265, acceptance 2) -------------------------


def _eval_align():  # type: ignore[no-untyped-def]
    import importlib.util
    from pathlib import Path as P

    spec = importlib.util.spec_from_file_location(
        "eval_align", P(__file__).parent.parent / "scripts" / "eval_align.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_a_word_is_scored_against_its_own_speech_not_the_join() -> None:
    """targum-internal#265, rescored 2026-10-08. Each word is said alone and the clips are
    joined, so a join sits in the silence the voice leaves around a word. Scored against
    the join, an aligner that found every word was 340-400 ms "out"; scored against where
    each clip's speech is, it is the aligner's own error."""
    align = _eval_align()
    # Speech at 0.3-0.8, 1.3-1.9, 2.25-2.8; joins at 1.0 and 2.0.
    spans = [(0.3, 0.8), (1.3, 1.9), (2.25, 2.8)]
    found = [(0.32, 0.8, 1.0), (1.3, 1.98, 1.0), (2.25, 2.8, 1.0)]
    marks = align.scored(found, spans, [1.0, 2.0, 3.0])
    assert marks["onset_ms_median"] == 0.0 and marks["onset_ms_mean"] == round(20 / 3, 1)
    assert marks["end_ms_median"] == 0.0 and marks["end_ms_mean"] == round(80 / 3, 1)
    assert marks["within_50ms"] == round(2 / 3, 4), "the 80 ms end is not close"
    assert marks["seam_in_gap"] == 1.0, "both joins fall between the words they divide"
    late = [(0.3, 1.2, 1.0), (1.3, 1.9, 1.0), (2.25, 2.8, 1.0)]
    assert align.scored(late, spans, [1.0, 2.0, 3.0])["seam_in_gap"] == 0.5


def test_a_clip_s_speech_is_read_off_its_loudness(tmp_path: Path) -> None:
    import math
    import struct
    import wave

    align = _eval_align()
    rate = align.ALIGN_RATE
    pcm = []
    for start, stop in ((0.2, 0.6), (0.3, 0.7)):  # two one-second clips, a tone in each
        clip = [0.0] * rate
        for n in range(int(start * rate), int(stop * rate)):
            clip[n] = 0.5 * math.sin(2 * math.pi * 220 * n / rate)
        pcm += clip
    path = tmp_path / "two.wav"
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(rate)
        out.writeframes(b"".join(struct.pack("<h", int(x * 32767)) for x in pcm))
    spans = align.spoken_spans(path, [1.0, 2.0])
    assert abs(spans[0][0] - 0.2) < 0.02 and abs(spans[0][1] - 0.6) < 0.02
    assert abs(spans[1][0] - 1.3) < 0.02 and abs(spans[1][1] - 1.7) < 0.02


def test_a_mismatched_alignment_is_refused_rather_than_scored_short() -> None:
    """`strict=True` on the zip: an aligner that answered with fewer words than it was
    given would otherwise score only the ones it managed, which reads as a better number
    the worse it did."""
    import pytest as _pytest

    align = _eval_align()
    with _pytest.raises(ValueError):
        align.scored([(0.0, 1.0, 1.0)], [(0.0, 1.0), (1.0, 2.0)])


def test_the_words_drawn_stop_at_what_was_asked_for() -> None:
    align = _eval_align()
    assert len(align.words_of("he", 5)) == 5
    assert align.words_of("he", 0) == []
    assert align.words_of("xx", 5) == [], "a language with no lines draws nothing"
    for code in ("he", "fr", "ru", "it"):
        assert len(align.words_of(code, 999)) >= 20, f"{code} has enough to measure with"


# -- the aligner on real audio (targum-internal#225) ------------------------------------


def test_pockettorah_labels_are_onsets_separated_by_commas() -> None:
    align = _eval_align()
    assert align.labels_of("2.0,3.5,4.25\n") == [2.0, 3.5, 4.25]
    assert align.labels_of("1,2,") == [1.0, 2.0], "a trailing comma is not a word"


def test_an_aliyah_is_the_apps_words_across_a_chapter_boundary() -> None:
    """The labels index the app's own word list, so the words must be cut exactly as it
    cuts them: a `w` each, the `/` morpheme marks out, a trailing null chapter ignored."""
    align = _eval_align()
    book = {
        "Tanach": {
            "tanach": {
                "book": {
                    "c": [
                        {"v": [{"w": ["בְּ/רֵאשִׁ֖ית", "בָּרָ֣א"]}, {"w": ["וְ/הָ/אָ֗רֶץ"]}]},
                        {"v": {"w": ["וַ/יְכֻלּ֛וּ"]}},
                        None,
                    ]
                }
            }
        }
    }
    assert align.aliyah_words(book, "1:2", "2:1") == ["וְהָאָ֗רֶץ", "וַיְכֻלּ֛וּ"]
    assert align.aliyah_words(book, "1:1", "1:1") == ["בְּרֵאשִׁ֖ית", "בָּרָ֣א"]


def test_onsets_are_scored_both_unsigned_and_as_a_lag() -> None:
    align = _eval_align()
    onsets = [1.0, 2.0, 3.0, 4.0]
    # 50 ms late, 150 ms late, 300 ms early, exact.
    found = [(1.05, 1.9, 0.0), (2.15, 2.9, 0.0), (2.7, 3.9, 0.0), (4.0, 4.5, 0.0)]
    marks = align.onsets_scored(found, onsets)
    assert marks["onset_ms_median"] == 100.0
    assert marks["onset_ms_mean"] == 125.0
    assert marks["onset_ms_lag_median"] == 25.0, "signed: two late, one early, one exact"
    assert marks["onset_within_100ms"] == 0.5
    assert marks["onset_within_250ms"] == 0.75


def test_onsets_for_a_short_alignment_are_refused() -> None:
    align = _eval_align()
    with pytest.raises(ValueError):
        align.onsets_scored([(1.0, 2.0, 0.0)], [1.0, 2.0])
    with pytest.raises(ValueError):
        align.lit_share([(1.0, 2.0, 0.0)], [1.0, 2.0], 3.0)


def test_the_right_word_is_lit_for_the_share_of_time_it_is_lit() -> None:
    """Both sides light a word from its start to the next start: an aligner that is late
    on one word is wrong only for the time it is late, not for the whole word."""
    align = _eval_align()
    onsets = [0.0, 1.0, 2.0]
    exact = [(0.0, 0.5, 0.0), (1.0, 1.5, 0.0), (2.0, 2.5, 0.0)]
    assert align.lit_share(exact, onsets, 3.0) == 1.0
    # The second word starts half a second late: from 1.0 to 1.5 the first is still lit.
    late = [(0.0, 0.5, 0.0), (1.5, 1.8, 0.0), (2.0, 2.5, 0.0)]
    assert align.lit_share(late, onsets, 3.0) == round(2.5 / 3.0, 4)
    # Before the aligner's first word nothing is lit, which is never the right word.
    slow = [(0.5, 0.9, 0.0), (1.0, 1.5, 0.0), (2.0, 2.5, 0.0)]
    assert align.lit_share(slow, onsets, 3.0) == round(2.5 / 3.0, 4)


def test_a_word_placed_in_the_wrong_clip_is_counted_wrong() -> None:
    align = _eval_align()
    bounds = [(0.0, 2.0), (2.0, 4.0)]
    owners = [0, 0, 1]
    found = [(0.2, 0.6, 0.0), (1.8, 2.6, 0.0), (2.5, 3.0, 0.0)]
    # The second word's middle is at 2.2, in the next clip.
    assert align.in_its_clip(found, owners, bounds) == round(2 / 3, 4)


def test_common_voice_rows_are_read_in_file_order_quotes_and_all(tmp_path: Path) -> None:
    """Common Voice's .tsv is unquoted: a sentence may hold a `"` and must be read as
    written, not as the start of a quoted field that swallows the next rows."""
    align = _eval_align()
    (tmp_path / "test.tsv").write_text(
        "client_id\tpath\tsentence\n"
        'a\tone.mp3\tהוא אמר "שלום" ויצא\n'
        "b\ttwo.mp3\t\n"
        "c\tthree.mp3\tמחר נלך\n"
        "d\tfour.mp3\tאחרון\n",
        encoding="utf-8",
    )
    rows = align.clip_rows(tmp_path, "test", 2)
    assert rows == [
        (tmp_path / "clips" / "one.mp3", 'הוא אמר "שלום" ויצא'),
        (tmp_path / "clips" / "three.mp3", "מחר נלך"),
    ], "an empty sentence is skipped and the count stops at what was asked for"


def test_joined_clips_know_where_each_one_sits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import wave

    align = _eval_align()
    lengths = {"a.mp3": 16000, "b.mp3": 8000}
    monkeypatch.setattr(align, "samples", lambda path, rate: [0.1] * lengths[path.name])
    into = tmp_path / "joined.wav"
    bounds = align.joined_clips([(tmp_path / "a.mp3", "x"), (tmp_path / "b.mp3", "y")], into)
    assert bounds == [(0.0, 1.0), (1.0, 1.5)]
    with wave.open(str(into)) as made:
        assert made.getframerate() == 16000
        assert made.getnframes() == 24000


def test_an_app_name_finds_the_mp3_however_either_side_spells_it(tmp_path: Path) -> None:
    align = _eval_align()
    for name in ("AchreiMot-3.mp3", "Bereshit-1.mp3"):
        (tmp_path / name).write_bytes(b"")
    assert align._audio_for("Achrei Mot-3", tmp_path) == tmp_path / "AchreiMot-3.mp3"
    assert align._audio_for("Bereshit-1", tmp_path) == tmp_path / "Bereshit-1.mp3"
    assert align._audio_for("Bereshit-2", tmp_path) is None


def test_only_the_seven_aliyot_are_asked_for(tmp_path: Path) -> None:
    """The maftir and the haftarah are labelled against other passages; asking for one
    fails before anything is fetched."""
    align = _eval_align()
    for name in ("Bereshit-H", "Bereshit-8", "Bereshit"):
        with pytest.raises(ValueError):
            align.pockettorah_case(name, tmp_path)
    assert not any(tmp_path.iterdir()), "nothing was fetched"


def test_a_pockettorah_pin_covers_the_table_the_books_and_the_labels(tmp_path: Path) -> None:
    """The run's `runs/` output sits in the same folder and must not move the pin."""
    align = _eval_align()
    table = {
        "parshiot": {
            "parsha": [
                {"_id": "Bereshit", "_verse": "Genesis 1:1 - 6:8"},
                {"_id": "Noach", "_verse": "Genesis 6:9 - 11:32"},
                {"_id": "Shemot", "_verse": "Exodus 1:1 - 6:1"},
            ]
        }
    }
    (tmp_path / "aliyah.json").write_text(json.dumps(table))
    files = align.pockettorah_files(["Bereshit-1", "Noach-2", "Shemot-2"], tmp_path)
    assert [one.relative_to(tmp_path).as_posix() for one in files] == [
        "aliyah.json",
        "Exodus.json",
        "Genesis.json",
        "labels/Bereshit-1.txt",
        "labels/Noach-2.txt",
        "labels/Shemot-2.txt",
    ]


def test_the_two_ends_of_a_recast_run_never_share_a_ledger_line() -> None:
    """`ntrex-128-ru` means a Russian speaker's turn against the Hebrew reference
    (targum-internal#286). An English turn against the Russian reference is a different
    measurement, and two of those on one trend line would each look like the other
    moving — which is the whole reason `corpus_of` exists (#357)."""
    import importlib.util
    from pathlib import Path

    where = Path(__file__).resolve().parents[1] / "scripts" / "eval_recast.py"
    spec = importlib.util.spec_from_file_location("eval_recast", where)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    said = {
        module.corpus_of("ntrex", "en", "he"),
        module.corpus_of("ntrex", "ru", "he"),
        module.corpus_of("ntrex", "en", "ru"),
        module.corpus_of("ntrex", "en", "fr"),
    }
    assert len(said) == 4, said
    assert module.corpus_of("ntrex", "en", "he") == "ntrex-128", "the default keeps its name"
    assert module.corpus_of("ntrex", "ru", "he") == "ntrex-128-ru", "#286's line is unmoved"
    assert module.corpus_of("ntrex", "en", "ru") == "ntrex-128-in-ru"


def test_a_recast_keeps_the_reply_it_was_read_from() -> None:
    """targum-internal#359: 65 of 200 Yiddish turns had no `> ` line, and the run kept
    only the line, so nothing said why. The reply and its stop reason are kept now, and a
    missing line is still "" — never a line guessed from the rest."""
    import importlib.util
    from pathlib import Path
    from types import SimpleNamespace

    from targum.usage import Usage

    where = Path(__file__).resolve().parents[1] / "scripts" / "eval_recast.py"
    spec = importlib.util.spec_from_file_location("eval_recast", where)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    def client(text: str, stop: str) -> object:
        reply = SimpleNamespace(
            content=[SimpleNamespace(text=text)],
            stop_reason=stop,
            usage=SimpleNamespace(input_tokens=1, output_tokens=1),
        )
        return SimpleNamespace(messages=SimpleNamespace(create=lambda **_: reply))

    marked = "> איך האָב געזען דעם הונט.\n= I saw the dog."
    turn = module.recast(client(marked, "end_turn"), [], "I seen the dog", Usage(), "yi")
    assert turn.line == "איך האָב געזען דעם הונט." and turn.stop == "end_turn"
    assert turn.raw == marked

    cut = "איך האָב געזען"
    turn = module.recast(client(cut, "max_tokens"), [], "I seen the dog", Usage(), "yi")
    assert turn.line == "" and turn.raw == cut and turn.stop == "max_tokens"


def test_a_language_with_no_word_list_is_still_scored_as_a_reader_who_knows_words(
    monkeypatch: Any,
) -> None:
    """targum-internal#359. With no wordfreq list, the Yiddish reader had marked nothing,
    the ledger said it was their first day and to offer a text, and with no tools the
    model wrote the call out instead of the recast: 13 of 14 empty turns. The stand-in
    ledger is FLORES-200's `dev` split, disjoint from the `devtest` being scored."""
    import importlib.util
    from pathlib import Path

    from targum.chat import flores200

    where = Path(__file__).resolve().parents[1] / "scripts" / "eval_recast.py"
    spec = importlib.util.spec_from_file_location("eval_recast", where)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    asked: list[tuple[list[str], str]] = []
    monkeypatch.setattr(
        flores200, "fetch", lambda languages, split="devtest", **_: asked.append((languages, split))
    )
    lines = ["דער הונט איז גרויס", "דער קאַץ איז קליין", "דער הונט לויפט"]
    monkeypatch.setattr(
        flores200,
        "load",
        lambda language, split: [flores200.Pair(str(n), "x", line) for n, line in enumerate(lines)],
    )
    known = module.stand_in_known("yi", 2)
    assert known == ["דער", "איז"], known  # a tie goes to the spelling, so it is stable
    assert asked == [(["yi"], "dev")], "the dev split, never the one scored"
    assert module.stand_in_known("arc", 300) == [], "nothing to stand in with"


def test_the_judge_is_asked_about_the_conversation_s_language() -> None:
    """targum-internal#358: the template said Hebrew four times and never used `named`,
    so a French recast was judged as Hebrew and marked wrong for being French."""
    import importlib.util
    from pathlib import Path

    where = Path(__file__).resolve().parents[1] / "scripts" / "eval_recast.py"
    spec = importlib.util.spec_from_file_location("eval_recast", where)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    said = dict(language="English", said="s", reference="r", candidate="c")
    french = module.JUDGE.format(named="French", **said)
    assert "Hebrew" not in french and french.count("French") == 4
    hebrew = module.JUDGE.format(named="Hebrew", **said)
    assert hebrew.startswith("You are checking one line of Hebrew written by")
