"""Refinement: from words heard to text a reader can follow, clocks intact."""

from __future__ import annotations

from targum.transcribe.models import Transcript, Word
from targum.transcribe.refine.anthropic import AnthropicRefiner
from targum.transcribe.refine.rules import RuleRefiner


def heard(text: str, step: float = 1.0, speaker: str = "") -> list[Word]:
    return [
        Word(text=piece, start=round(n * step, 3), end=round(n * step + 0.8, 3), speaker=speaker)
        for n, piece in enumerate(text.split())
    ]


def test_a_long_pause_breaks_a_paragraph_and_a_short_one_does_not() -> None:
    words = heard("one two")
    words += [Word(text="three", start=5.0, end=5.5)]
    refined = RuleRefiner().refine(
        Transcript(provider="null", language="he", duration=6.0, words=words)
    )
    assert [p.text for p in refined.paragraphs] == ["one two", "three"]


def test_the_model_backed_refiner_maps_every_kept_word_back_to_its_clock() -> None:
    """The one hard rule: timing is never guessed. A repunctuated word keeps the clock
    of the word it was; the ad break the model dropped takes its clocks with it."""
    transcript = Transcript(
        provider="test",
        language="he",
        duration=8.0,
        words=heard("שלום לכם היום נדבר על חורף"),
    )
    written = "שלום לכם.\n\nהיום נדבר על חורף."
    refined = AnthropicRefiner()._mapped(transcript, list(transcript.words), written)
    assert [p.text for p in refined.paragraphs] == ["שלום לכם.", "היום נדבר על חורף."]
    first = refined.paragraphs[0].words
    assert first[0].start == 0.0
    assert first[1].start == 1.0
    second = refined.paragraphs[1].words
    assert second[0].start == 2.0  # "היום" keeps its own clock across the break


def test_a_word_the_model_invented_borrows_its_neighbours_clock() -> None:
    transcript = Transcript(
        provider="test", language="he", duration=3.0, words=heard("אחת שתיים שלוש")
    )
    refined = AnthropicRefiner()._mapped(transcript, list(transcript.words), "אחת בערך שתיים שלוש")
    words = refined.paragraphs[0].words
    assert words[0].start == 0.0
    invented = words[1]
    assert invented.text == "בערך"
    assert invented.start == words[0].end  # borrowed, not guessed
    assert invented.confidence < 1.0


def test_dropped_advertising_takes_its_clocks_with_it() -> None:
    transcript = Transcript(
        provider="test",
        language="he",
        duration=6.0,
        words=heard("תוכן אמיתי פרסומת ארוכה כאן חוזרים לתוכן"),
    )
    refined = AnthropicRefiner()._mapped(
        transcript, list(transcript.words), "תוכן אמיתי\n\nחוזרים לתוכן"
    )
    assert [p.text for p in refined.paragraphs] == ["תוכן אמיתי", "חוזרים לתוכן"]
    assert refined.paragraphs[1].words[0].start == 5.0


def test_a_replaced_refiner_redoes_its_half_without_paying_to_hear_again(
    fake_audio, tmp_path, monkeypatch
) -> None:
    """The transcript is cached; a better refiner's arrival re-reads it for nothing
    and rewrites only the refinement — the seam the moat is built on."""

    from targum.pipeline import Build
    from targum.transcribe.null import NullTranscriber

    class Splits:
        name = "fake/1"

        def split(self, texts: list[str], language: str) -> list[list[str]]:
            return [[t] for t in texts]

    fake_audio.duration = 600.0
    source = tmp_path / "talk.mp3"
    source.write_bytes(b"audio")

    def build() -> Build:
        return Build(
            str(source),
            target_language="en",
            source_language="en",
            provider_name="null",
            segmenter=Splits(),
            transcriber=NullTranscriber(text="one two three", language="en"),
            out_root=tmp_path / "out",
        )

    first = build()
    first.run()
    folder = first.resolved_out
    refined = folder / "audio" / "refined" / "part-001.json"
    import json

    assert json.loads(refined.read_text())["refiner"] == "rules/1"

    monkeypatch.setenv("TARGUM_REFINER", "none")  # the null refiner stands in for a new one
    second = build()
    second.run()
    assert json.loads(refined.read_text())["refiner"] == "none"
    # Nothing was heard twice: the transcript came from the cache.
    assert second.spent.seconds_by_model.get("null", 0.0) == 0.0
