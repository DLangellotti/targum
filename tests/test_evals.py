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


def test_the_boundary_score_is_off_the_ends_and_not_counted_twice() -> None:
    """A start is the previous end by construction here — the words were said one at a
    time and joined — so scoring both would count every boundary twice and halve the
    error it reports."""
    align = _eval_align()
    # Three words, true ends at 1.0, 2.0, 3.0; found 20ms, 80ms and 0ms out.
    found = [(0.0, 1.02, 1.0), (1.02, 1.92, 1.0), (1.92, 3.0, 1.0)]
    truth = [1.0, 2.0, 3.0]
    marks = align.scored(found, truth)
    assert marks["boundary_ms_mean"] == round((20 + 80 + 0) / 3, 1)
    assert marks["boundary_ms_median"] == 20.0
    assert marks["within_50ms"] == round(2 / 3, 4), "the 80ms one is not close"


def test_a_mismatched_alignment_is_refused_rather_than_scored_short() -> None:
    """`strict=True` on the zip: an aligner that answered with fewer words than it was
    given would otherwise score only the ones it managed, which reads as a better number
    the worse it did."""
    import pytest as _pytest

    align = _eval_align()
    with _pytest.raises(ValueError):
        align.scored([(0.0, 1.0, 1.0)], [1.0, 2.0])


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
