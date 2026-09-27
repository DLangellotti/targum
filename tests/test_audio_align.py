"""The forced aligner, on the parts of it that do not need a model.

The acoustic model is 1.2 GB and the alignment itself is `torchaudio`'s, tested by
torchaudio. What is targum's here is the shape around it: which languages it will answer
for, how a word becomes letters the model has symbols for, and what happens to a word it
has no symbols for at all. Those are the parts that were wrong in a draft, so those are
the parts with tests.

The measurement that matters — whether the spans are any good — is not here and could
not be: it is a comparison against a real reading, recorded on targum-internal#117 and
in `LICENSING.md`. Median 20 ms against the aligner this replaced, over 408 words.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from targum.audio import align as align_module
from targum.audio.align import MODEL, NAME, CtcAligner, _bare
from targum.errors import TargumError


def test_the_name_says_which_model_made_a_span() -> None:
    """A stored span carries the aligner's name, so a rename is what makes a recording
    align again. The old name was `ctc-mms-fa/1`; anything holding that was timed by the
    NonCommercial model and has to be re-derived. `/2` since spans are moved to the voice
    (2026-09-27): a cached `/1` span is the narrower CTC path and is not reused."""
    assert NAME == "ctc-xlsr-he/2"
    assert CtcAligner.name == NAME
    assert "mms" not in NAME, "the MMS model is gone and the name must not claim it"


def test_the_model_is_the_permissive_one() -> None:
    """The whole point of the swap. Pinned in a test because a quiet edit back to an
    MMS-lineage model would put a NonCommercial term into every timing targum makes,
    and nothing else in the suite would notice."""
    assert MODEL == "imvladikon/wav2vec2-large-xlsr-53-hebrew"
    assert "mms" not in MODEL.lower()


def test_the_marks_come_off_before_the_model_sees_a_word() -> None:
    """The model was trained on unpointed Hebrew and has no symbol for a nikkud or a
    taam. Handing it a pointed word is handing it letters it cannot align."""
    assert _bare("בְּרֵאשִׁ֖ית") == "בראשית"
    assert _bare("וַיֹּ֥אמֶר") == "ויאמר"


def test_a_final_form_is_kept_because_the_model_has_one() -> None:
    """`ך ם ן ף ץ` are in this model's vocabulary, which is the advantage of aligning
    Hebrew as Hebrew rather than through a romanisation."""
    assert _bare("מים") == "מים"
    assert _bare("שלום") == "שלום"
    assert _bare("ארץ־ישראל") == "ארץישראל", "the maqaf is not a letter"


def test_everything_that_is_not_a_letter_goes() -> None:
    """A transcript carries punctuation, digits and — in a Ben-Yehuda text — the URL it
    was downloaded from. None of it is alignable."""
    assert _bare("הבאה:https://benyehuda.org/read/1513") == "הבאה"
    assert _bare("1948") == ""
    assert _bare("") == ""


def test_a_language_this_model_cannot_read_is_refused_rather_than_guessed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """MMS was multilingual and this is not, which is the one thing the swap gave up.

    Refused out loud rather than aligned badly: a Russian reading timed against a Hebrew
    acoustic model would produce spans that look like spans and are noise.
    """
    monkeypatch.setattr(CtcAligner, "available", lambda self: (True, NAME))
    with pytest.raises(TargumError, match="Hebrew, French, Russian and Italian"):
        CtcAligner().align(tmp_path / "x.mp3", ["געזונט"], "yi")


def test_a_language_with_no_model_says_so_before_anything_loads() -> None:
    usable, why = CtcAligner("yi").available()
    assert usable is False and "'yi'" in why


def test_each_language_has_its_own_permissive_model_and_name() -> None:
    """Hebrew keeps its model and its name byte for byte: the name keys every stored span.
    French, Russian and Italian each get an Apache-2.0 XLS-R fine-tune of their own."""
    assert align_module.MODELS["he"] == (MODEL, NAME)
    for code in ("fr", "ru", "it"):
        model, name = align_module.MODELS[code]
        assert name == f"ctc-xlsr-{code}/2" and "mms" not in model.lower()
        aligner = CtcAligner(code)
        assert aligner.name == name and aligner.model == model
    assert CtcAligner("he-IL").name == NAME


def test_a_latin_or_cyrillic_word_keeps_its_accents_and_loses_the_rest() -> None:
    assert _bare("L’Été,", "fr") == "l'été"
    assert _bare("Привет!", "ru") == "привет"
    assert _bare("1948", "it") == ""


def test_hebrew_is_accepted_by_its_bare_tag_and_its_dialect_tag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`he`, `he-IL`, `HE` — the caller's tag is not normalised before it gets here.

    Asserted as what did *not* happen, because what happens after the gate depends on the
    machine: with the extra installed the run goes on to look for the audio file, and
    without it the import of `torchaudio` is what stops it first. Neither is this test's
    business — CI installs no extra, and a first draft that asserted the happy path failed
    there for exactly that reason.
    """
    monkeypatch.setattr(CtcAligner, "available", lambda self: (True, NAME))
    for tag in ("he", "he-IL", "HE"):
        with pytest.raises(Exception) as refused:  # noqa: B017
            CtcAligner().align(Path("no-such-file.mp3"), ["שלום"], tag)
        assert "reads Hebrew, not" not in str(refused.value), f"{tag} was refused as foreign"


def test_without_the_extra_it_says_what_to_install() -> None:
    """The `_read_through` shape: absent, the recording plays and the page does not
    follow along. The hint has to name the extra or the reader cannot act on it."""
    aligner = CtcAligner()
    usable, hint = aligner.available()
    if usable:
        assert hint == NAME
    else:
        assert "speech-align" in hint


def test_a_word_with_no_letters_still_gets_a_row(monkeypatch: pytest.MonkeyPatch) -> None:
    """The caller zips the answer against the words it handed in, so a list that is
    shorter than the words is an off-by-one through every span after it.

    A URL or a bare numeral has nothing the model can align. It gets a zero-width span
    rather than being dropped, and a floor score so the trimming in `recording/models.py`
    takes it off an edge.
    """
    monkeypatch.setattr(CtcAligner, "available", lambda self: (True, NAME))
    # Every word is unalignable, so the model is never reached: the file below does not
    # exist, and reaching for it would be the failure. The first draft loaded 1.2 GB of
    # weights and decoded the audio before finding out there was nothing to align.
    monkeypatch.setattr(
        CtcAligner, "_emissions", lambda self, audio: pytest.fail("loaded the model for nothing")
    )
    got = CtcAligner().align(Path("x.mp3"), ["1948", "https://example.com", "..."], "he")
    assert len(got) == 3
    assert all(start == end for start, end, _ in got)
    assert all(score == align_module.SCORE_FLOOR for *_, score in got)


def test_a_word_the_model_cannot_spell_does_not_count_against_the_match() -> None:
    """English inside a Hebrew transcript is placed at the floor score; averaged in, a
    few English phrases took following along away from a part the model matched well
    (2026-09-14). Only the words it has letters for are asked how well they matched."""
    from targum.audio.align import MATCH_FLOOR, SCORE_FLOOR, match_score

    words = ["היום", "אנחנו", "ב", "MIT", "וזה", "really", "amazing", "trip", "2024"]
    scores = [-1.0, -1.5, -2.0, SCORE_FLOOR, -1.0] + [SCORE_FLOOR] * 4
    assert sum(scores) / len(scores) < MATCH_FLOOR, "the old mean failed this part"
    matched = match_score(words, scores, "he")
    assert matched is not None and matched == -1.375
    assert match_score(["MIT", "2024"], [SCORE_FLOOR, SCORE_FLOOR], "he") is None
    assert match_score(["rivière"], [-2.0], "fr") == -2.0, "a French word is French's"


# -- spans moved to the voice (2026-09-27) ----------------------------------------------


def test_a_frame_is_voiced_relative_to_its_own_recording() -> None:
    """A quiet studio and a loud car differ by tens of dB; the line is drawn between each
    recording's own quiet and loud, so the same shape of speech reads the same in both."""
    from targum.audio.align import voiced_frames

    quiet = [-60.0] * 10 + [-20.0] * 10
    assert voiced_frames(quiet) == [False] * 10 + [True] * 10
    assert voiced_frames([level + 30 for level in quiet]) == voiced_frames(quiet)
    assert voiced_frames([]) == []


def _moved(spans: list[tuple[int, int] | None], voiced: str) -> list[tuple[int, int] | None]:
    from targum.audio.align import to_the_voice

    return to_the_voice(spans, [v == "1" for v in voiced], lead=2, reach_back=10, reach_on=25)


def test_a_word_after_a_pause_starts_where_the_voice_does() -> None:
    """CTC places the first letter a few frames into the sound. After a silence the
    voice's own onset is plain, and the start walks back to it and no further."""
    voiced = "1111" + "000000" + "11111111111" + "0000"
    #         word 0   pause     word 1 voiced from frame 10
    got = _moved([(0, 3), (13, 18)], voiced)
    assert got[1] == (10, 21), "starts on the first voiced frame, ends where the voice stops"
    assert got[0] == (0, 4)


def test_words_run_together_move_by_the_measured_lead_and_tile() -> None:
    """With no quiet between two words the voice cannot say where one ends, so the start
    moves back by the measured lag alone and the earlier word runs up to it: nothing
    goes unlit in the middle of a phrase."""
    voiced = "1" * 30
    got = _moved([(0, 8), (14, 20)], voiced)
    assert got[1][0] == 12
    assert got[0] == (0, 12)


def test_a_start_never_crosses_the_word_before_it() -> None:
    voiced = "1" * 30
    got = _moved([(0, 10), (11, 20)], voiced)
    assert got[1][0] == 10 and got[0][1] == 10


def test_the_walks_are_bounded() -> None:
    """A hum above the line before a word, or a noise after it, is not the word."""
    voiced = "0" + "1" * 60
    got = _moved([(40, 45)], voiced)
    assert got[0] == (38, 61), "no quiet within reach: the lead alone"
    long_tail = "1" * 100
    assert _moved([(0, 5)], long_tail)[0] == (0, 30)


def test_a_word_the_path_did_not_place_stays_unplaced() -> None:
    got = _moved([(2, 4), None, (10, 12)], "0011111111110000")
    assert got[1] is None
    assert got[0] == (2, 8) and got[2] == (8, 12)


def test_a_spoken_word_the_model_cannot_spell_takes_the_gap_it_left() -> None:
    """targum-internal#380: "Lubbock" in a Hebrew text came out a point, and the word
    before it lit while it was said. It takes the frames between its neighbours now."""
    from targum.audio.align import share_the_gap, to_the_voice

    spans = [(0, 10), None, (30, 40)]
    shared = share_the_gap(spans, [0, 7, 0], total=50)
    assert shared == [(0, 10), (10, 30), (30, 40)]
    widened = to_the_voice(shared, [True] * 50, lead=2, reach_back=10, reach_on=25)
    assert widened[0] is not None and widened[1] is not None
    assert widened[0][1] <= widened[1][0], "the word before stops where the name starts"


def test_a_run_of_them_shares_the_gap_by_length() -> None:
    from targum.audio.align import share_the_gap

    shared = share_the_gap([(0, 10), None, None, (40, 50)], [0, 2, 4, 0], total=60)
    assert shared[1] == (10, 20) and shared[2] == (20, 40)


def test_punctuation_stays_unplaced() -> None:
    """A dash is not said. It stays a point, as it was."""
    from targum.audio.align import share_the_gap

    assert share_the_gap([(0, 10), None, (10, 20)], [0, 0, 0], total=30)[1] is None


def test_no_room_leaves_it_unplaced() -> None:
    """Where the neighbours touch there is nothing to share, and no word is invented."""
    from targum.audio.align import share_the_gap

    assert share_the_gap([(0, 10), None, (10, 20)], [0, 7, 0], total=30)[1] is None
