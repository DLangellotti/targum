"""A written track typed the way it was heard gets its full stops, like a hearing does.

The Doña Gracia video (2026-11-14): a creator's own Hebrew track, 2,873 words with one
full stop and one comma, cues back to back with no breath between them. It was taken as
the source and never punctuated, so its 25 minutes read as four paragraphs and six
"sentences", the longest 878 words. No test here reaches a model: the punctuator is
handed a stub that answers what claude-sonnet-5 would.
"""

from __future__ import annotations

import json
from pathlib import Path

from targum.ingest.subtitles import (
    WALL_WORDS,
    load_cues,
    owes_punctuation,
    punctuated,
    refined_from,
)
from targum.pipeline import Build
from targum.transcribe.null import NullTranscriber
from targum.transcribe.refine.punctuate import Punctuator
from targum.transcribe.refine.rules import RuleRefiner

#: Cues as the track wrote them: no marks, and each runs straight into the next.
CUES = [
    "היום אני אשתדל לא להתלהב יותר מידי כי",
    "אני נמצא במסגד מאוד מאוד פנסי אבל יכול",
    "להיות שאני אתלהב והכל שלי יעלה המוסד הזה",
    "הוא אחד המוסדות הדתיים הכי חשובים באסלאם",
    "הסוני כבר יותר מאלף שנים",
]

#: What the model answers for them: marks, a paragraph, and every word as it was.
MARKED = (
    "היום אני אשתדל לא להתלהב יותר מידי, כי אני נמצא במסגד מאוד מאוד פנסי. "
    "אבל יכול להיות שאני אתלהב והכל שלי יעלה.\n\nהמוסד הזה הוא אחד המוסדות הדתיים "
    "הכי חשובים באסלאם הסוני כבר יותר מאלף שנים."
)


def srt(cues: list[str], step: float = 4.0) -> str:
    def clock(seconds: float) -> str:
        whole = int(seconds)
        return f"00:{whole // 60:02d}:{whole % 60:02d},{int(seconds * 1000) % 1000:03d}"

    return "\n".join(
        f"{n + 1}\n{clock(n * step)} --> {clock((n + 1) * step)}\n{text}\n"
        for n, text in enumerate(cues)
    )


def stub(answer: str) -> tuple[list[str], object]:
    asked: list[str] = []

    def ask(prompt: str) -> tuple[str, int, int]:
        asked.append(prompt)
        return answer, 100, 90

    return asked, ask


def track(tmp_path: Path, cues: list[str] = CUES) -> Path:
    path = tmp_path / "talk.he.srt"
    path.write_text(srt(cues), encoding="utf-8")
    return path


def test_a_track_with_no_full_stops_is_owed_them_and_a_marked_one_is_not(tmp_path) -> None:  # type: ignore[no-untyped-def]
    bare = refined_from(load_cues(track(tmp_path)), language="he")
    assert len(bare.paragraphs) == 1, "back-to-back cues never break a paragraph"
    assert owes_punctuation(bare)
    marked = track(tmp_path, [cue + "." for cue in CUES])
    assert not owes_punctuation(refined_from(load_cues(marked), language="he"))


def test_punctuation_ends_sentences_inside_cues_and_keeps_every_word(tmp_path) -> None:  # type: ignore[no-untyped-def]
    bare = refined_from(load_cues(track(tmp_path)), language="he")
    asked, ask = stub(MARKED)
    done = punctuated(bare, Punctuator(ask=ask))  # type: ignore[arg-type]

    assert len(asked) == 1
    assert done.refiner == "subtitles/2+punctuate/1"
    assert done.provider == "subtitles", "still the track's words, never a hearing"
    assert not owes_punctuation(done), "and it is not asked twice"
    texts = [p.text for p in done.paragraphs]
    assert texts == [
        "היום אני אשתדל לא להתלהב יותר מידי, כי אני נמצא במסגד מאוד מאוד פנסי. "
        "אבל יכול להיות שאני אתלהב והכל שלי יעלה.",
        "המוסד הזה הוא אחד המוסדות הדתיים הכי חשובים באסלאם הסוני כבר יותר מאלף שנים.",
    ], "the model's paragraph closes at its sentence end, inside the third cue"
    strip = str.maketrans("", "", ".,?!")
    assert " ".join(texts).translate(strip).split() == " ".join(CUES).split()

    # The third cue was cut where the paragraph closes inside it, its halves sharing
    # its clock in order; the second, a sentence ending inside it, stays whole.
    words = [word for p in done.paragraphs for word in p.words]
    assert words[1].text == "אני נמצא במסגד מאוד מאוד פנסי. אבל יכול"
    assert (words[1].start, words[1].end) == (4.0, 8.0)
    assert [w.text for w in words[2:4]] == ["להיות שאני אתלהב והכל שלי יעלה.", "המוסד הזה"]
    assert words[2].start == 8.0 and words[3].end == 12.0
    assert 8.0 < words[2].end == words[3].start < 12.0
    for paragraph in done.paragraphs:
        assert paragraph.text == " ".join(word.text for word in paragraph.words)


def test_a_long_track_is_drawn_into_paragraphs_at_sentence_ends(tmp_path) -> None:  # type: ignore[no-untyped-def]
    cues = CUES * 12
    bare = refined_from(load_cues(track(tmp_path, cues)), language="he")
    _, ask = stub("\n".join([MARKED.replace("\n\n", " ")] * 12))
    done = punctuated(bare, Punctuator(ask=ask))  # type: ignore[arg-type]
    assert len(done.paragraphs) > 3
    for paragraph in done.paragraphs:
        assert paragraph.text.endswith("."), "no paragraph stops mid-sentence"
        assert len(paragraph.text.split()) < 60 + 30


def test_a_refused_answer_still_breaks_the_wall_at_cues(tmp_path) -> None:  # type: ignore[no-untyped-def]
    cues = CUES * 12
    bare = refined_from(load_cues(track(tmp_path, cues)), language="he")
    _, ask = stub("something else entirely")
    done = punctuated(bare, Punctuator(ask=ask))  # type: ignore[arg-type]
    assert len(done.paragraphs) > 1
    longest = max(len(p.text.split()) for p in done.paragraphs)
    assert longest < WALL_WORDS + 10
    assert not owes_punctuation(done), "a part the model could not mark is not bought again"


class Splits:
    name = "fake/1"

    def split(self, texts: list[str], language: str) -> list[list[str]]:
        out = []
        for text in texts:
            pieces = [p.strip() + "." for p in text.replace("\n", " ").split(".") if p.strip()]
            out.append(pieces or [text])
        return out


class Deaf(NullTranscriber):
    """A paid transcriber that must never be asked: the track is the transcript."""

    def price_per_minute(self) -> float:
        return 0.006

    def transcribe(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("a written track was heard")


def test_a_build_buys_the_tracks_full_stops_and_never_a_hearing(
    fake_audio, tmp_path, monkeypatch
) -> None:
    fake_audio.duration = 30.0
    source = tmp_path / "talk.mp3"
    source.write_bytes(b"audio")

    def build(punctuator: Punctuator | None) -> Build:
        monkeypatch.setattr(Build, "_refiner", lambda self: RuleRefiner(punctuator))
        return Build(
            str(source),
            target_language="en",
            source_language="he",
            provider_name="null",
            segmenter=Splits(),
            transcriber=Deaf(text="", language="he"),
            transcript=track(tmp_path),
            out_root=tmp_path / "out",
        )

    # Without a punctuator (no key, or a free test build) the track stands as it came.
    plain = build(None)
    plain.run()
    refined = plain.resolved_out / "audio" / "refined" / "part-001.json"
    assert json.loads(refined.read_text())["refiner"] == "subtitles/2+unmarked"
    # Built bare, it stays bare (re-marking it would re-buy its English unpriced). Put
    # back to fresh, it stands for a first build that can buy the marks.
    (plain.resolved_out / "audio" / "refined" / "part-001.json").write_text(
        refined.read_text().replace("subtitles/2+unmarked", "subtitles/2")
    )

    asked, ask = stub(MARKED)
    buying = build(Punctuator(ask=ask))  # type: ignore[arg-type]
    plan = buying.plan()
    assert plan.audio is not None
    assert plan.audio.buying_parts == [1]
    assert plan.audio.transcription > 0, "the full stops are on the quote"
    assert plan.audio.translation_guess == 0, "the words are known, not guessed at"
    assert plan.audio.transcription < 0.01, "and priced as marks, never as a hearing"

    buying.run()
    written = json.loads(refined.read_text())
    assert written["refiner"] == "subtitles/2+punctuate/1"
    assert len(written["paragraphs"]) == 2
    assert buying.spent.calls >= 1, "the marks are on the receipt"
    segments = json.loads((buying.resolved_out / "segments.json").read_text())["segments"]
    sentences = [s for s in segments if s["kind"] == "paragraph"]
    assert len(sentences) == 3, "three sentences, where the bare track was one"

    # Done once: the next build owes nothing and asks nothing.
    again = build(Punctuator(ask=ask))  # type: ignore[arg-type]
    calls = len(asked)
    again.run()
    assert len(asked) == calls


def test_the_quote_for_a_subtitled_video_prices_its_full_stops(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from targum.serve import _punctuation_rate

    monkeypatch.setenv("ANTHROPIC_API_KEY", "not-used")
    assert _punctuation_rate(0.0) == 0.0, "nothing heard, nothing written: nothing to mark"
    assert _punctuation_rate(0.0, written=True) > 0.0
    assert _punctuation_rate(0.0, written=True) == _punctuation_rate(0.006)


def test_a_punctuated_track_with_no_pauses_is_not_one_paragraph_a_part(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """The other reader on the box: a track with its full stops, cues back to back, so
    every twelve-minute part was one paragraph of up to 1,951 words. Drawn for free."""
    sentences = MARKED.replace("\n\n", " ")
    words = sentences.split()
    cues = [" ".join(words[n : n + 7]) for n in range(0, len(words), 7)] * 10
    refined = refined_from(load_cues(track(tmp_path, cues)), language="he")
    assert not owes_punctuation(refined), "nothing to buy"
    assert len(refined.paragraphs) > 3
    for paragraph in refined.paragraphs[:-1]:
        assert paragraph.text.endswith("."), "closed at a sentence end, inside a cue or not"
        assert len(paragraph.text.split()) < 60 + 30
    flat = [cue.text for p in refined.paragraphs for cue in p.words]
    assert " ".join(flat).split() == " ".join(cues).split(), "every word, in order"


def test_a_track_written_before_727_or_already_sent_is_never_owed(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Old parts were translated as they stood: re-marking one re-buys its English."""
    from targum.audio.subtitle_words import aligned_name, is_aligned

    bare = refined_from(load_cues(track(tmp_path)), language="he")
    assert bare.refiner == "subtitles/2"
    assert not owes_punctuation(bare.model_copy(update={"refiner": "subtitles/1"}))
    assert not owes_punctuation(bare.model_copy(update={"refiner": "subtitles/1+ctc-x/2"}))
    # A part sent once and re-timed on the laptop after keeps the mark of the purchase.
    sent = aligned_name("ctc-x/2", "subtitles/2+punctuate/1")
    assert sent == "subtitles/2+punctuate/1+ctc-x/2"
    assert not owes_punctuation(bare.model_copy(update={"refiner": sent}))
    assert is_aligned(bare.model_copy(update={"refiner": sent}), "ctc-x/2")
    # Re-timed before it was ever sent: still owed, the words are still bare.
    assert owes_punctuation(bare.model_copy(update={"refiner": "subtitles/2+ctc-x/2"}))


def test_commas_without_full_stops_or_hidden_by_direction_marks(tmp_path) -> None:  # type: ignore[no-untyped-def]
    commas = [cue + "," for cue in CUES] * 6
    spliced = refined_from(load_cues(track(tmp_path, commas)), language="he")
    assert owes_punctuation(spliced), "a comma every seven words, and no sentence ever ends"
    rtl = [cue + ".\u200f" for cue in CUES] * 6
    marked = refined_from(load_cues(track(tmp_path, rtl)), language="he")
    assert not owes_punctuation(marked), "a full stop with an RLM after it is a full stop"
    assert len(marked.paragraphs) > 1


def two_parts(tmp_path: Path, step: float = 4.0) -> Path:
    """A 25-minute track: the cues in part 1's first minute and part 2's first minute."""
    from targum.audio import PAD  # noqa: F401 - the parts are cut with it either side

    def clock(seconds: float) -> str:
        whole = int(seconds)
        return f"00:{whole // 60:02d}:{whole % 60:02d},000"

    rows = []
    n = 0
    for base in (10.0, 800.0):
        for k, text in enumerate(CUES):
            n += 1
            at = base + k * step
            rows.append(f"{n}\n{clock(at)} --> {clock(at + step)}\n{text}\n")
    path = tmp_path / "talk.he.srt"
    path.write_text("\n".join(rows), encoding="utf-8")
    return path


def test_a_part_press_marks_the_pressed_part_and_never_a_built_one(
    fake_audio, tmp_path, monkeypatch
) -> None:
    """qa-claude on #1238: part 1 already built bare, part 2 pressed. The press is
    claimed at part 2's price, so only part 2 may be marked — part 1 re-marked would
    re-buy its English on nobody's quote."""
    fake_audio.duration = 1500.0
    source = tmp_path / "talk.mp3"
    source.write_bytes(b"audio")
    script = two_parts(tmp_path)

    def build(punctuator: Punctuator | None) -> Build:
        monkeypatch.setattr(Build, "_refiner", lambda self: RuleRefiner(punctuator))
        return Build(
            str(source),
            target_language="en",
            source_language="he",
            provider_name="null",
            segmenter=Splits(),
            transcriber=Deaf(text="", language="he"),
            transcript=script,
            out_root=tmp_path / "out",
        )

    first = build(None)
    first.run(chapters=1)
    workspace = first.resolved_out / "audio"
    refined = [workspace / "refined" / f"part-00{n}.json" for n in (1, 2)]
    assert [json.loads(p.read_text())["refiner"] for p in refined] == [
        "subtitles/2+unmarked",
        "subtitles/2",
    ], "part 1 was built bare, and says so; part 2 is not built yet"

    asked, ask = stub(MARKED)
    press = build(Punctuator(ask=ask))  # type: ignore[arg-type]
    plan = press.plan(chapters=1)
    assert plan.audio is not None and plan.audio.buying_parts == [], "nothing on a reopen"
    assert press._parts_owed(1, [2]) == [2]
    press.run(chapters=1, also=[2])
    assert len(asked) == 1
    assert [json.loads(p.read_text())["refiner"] for p in refined] == [
        "subtitles/2+unmarked",
        "subtitles/2+punctuate/1",
    ]


def test_the_same_track_in_a_new_folder_does_not_buy_its_marks_again(
    fake_audio, tmp_path, monkeypatch
) -> None:
    fake_audio.duration = 30.0
    source = tmp_path / "talk.mp3"
    source.write_bytes(b"audio")
    asked, ask = stub(MARKED)
    monkeypatch.setattr(
        Build,
        "_refiner",
        lambda self: RuleRefiner(Punctuator(ask=ask)),  # type: ignore[arg-type]
    )
    for out in ("one", "two"):
        Build(
            str(source),
            target_language="en",
            source_language="he",
            provider_name="null",
            segmenter=Splits(),
            transcriber=Deaf(text="", language="he"),
            transcript=track(tmp_path),
            out_root=tmp_path / out,
        ).run()
    assert len(asked) == 1, "the second folder's marks came from the cache"
    for out in ("one", "two"):
        (written,) = (tmp_path / out).glob("*/audio/refined/part-001.json")
        assert json.loads(written.read_text())["refiner"] == "subtitles/2+punctuate/1"
