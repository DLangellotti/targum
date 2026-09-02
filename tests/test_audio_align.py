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
    NonCommercial model and has to be re-derived."""
    assert NAME == "ctc-xlsr-he/1"
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
    with pytest.raises(TargumError, match="Hebrew"):
        CtcAligner().align(tmp_path / "x.mp3", ["привет"], "ru")


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
