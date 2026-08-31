"""The audio build end to end: parts bought like chapters, nothing paid for twice."""

from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

from targum.audio import manifest as manifest_module
from targum.errors import TargumError
from targum.ingest.audio import refined_path
from targum.pipeline import Build
from targum.transcribe.null import NullTranscriber
from targum.usage import Usage


class SplitsOnFullStops:
    name = "fake/1"

    def split(self, texts: list[str], language: str) -> list[list[str]]:
        return [[part.strip() + "." for part in text.split(".") if part.strip()] for text in texts]


SAID = (
    "the winter that year came early and stayed long. "
    "nobody in the village remembered a colder one. "
    "the river froze from bank to bank before december."
)


def recording(tmp_path: Path) -> Path:
    source = tmp_path / "a-winter-talk.mp3"
    source.write_bytes(b"audio")
    return source


def builder(tmp_path: Path, source: Path, **extra: object) -> Build:
    options: dict[str, object] = {
        "target_language": "en",
        "source_language": "en",
        "provider_name": "null",
        "segmenter": SplitsOnFullStops(),
        "transcriber": NullTranscriber(text=SAID, language="en"),
        "out_root": tmp_path / "out",
    }
    options.update(extra)
    return Build(str(source), **options)  # type: ignore[arg-type]


def test_the_first_build_buys_one_part_of_a_ten_hour_book(fake_audio, tmp_path: Path) -> None:
    """FIRST_CHAPTERS semantics: a long recording costs one part up front, not four
    dollars before the reader sees a page."""
    fake_audio.duration = 36_000.0
    build = builder(tmp_path, recording(tmp_path))
    result = build.run(chapters=1)
    workspace = result.out_dir / "audio"
    assert refined_path(workspace, 1).exists()
    assert not refined_path(workspace, 2).exists()
    kept = manifest_module.load(result.out_dir)
    assert kept is not None
    assert kept.parts[0].transcribed
    assert not kept.parts[1].transcribed
    assert len(kept.parts) == 50


def test_a_transcribed_part_is_never_paid_for_twice_across_rebuilds(
    fake_audio, tmp_path: Path
) -> None:
    fake_audio.duration = 1400.0
    source = recording(tmp_path)
    first = builder(tmp_path, source)
    first.run()
    heard = first.spent.seconds_by_model.get("null", 0.0)
    assert heard > 0
    second = builder(tmp_path, source)
    second.run()
    assert second.spent.seconds_by_model.get("null", 0.0) == 0.0


def test_buying_part_nine_before_part_two_leaves_part_nines_translation_reachable(
    fake_audio, tmp_path: Path
) -> None:
    """The addendum's guard: reserved id ranges plus per-chapter cache entries mean an
    out-of-order purchase never orphans paid work."""
    fake_audio.duration = 7200.0  # ten parts
    source = recording(tmp_path)
    first = builder(tmp_path, source)
    first.run(chapters=1, also=[9])
    out = first.resolved_out
    translated = json.loads(
        (out / "translations" / "null.natural.en.json").read_text(encoding="utf-8")
    )
    nine_before = {
        sid: text for sid, text in translated["segments"].items() if sid.startswith("9000")
    }
    assert nine_before, "part nine was bought"

    second = builder(tmp_path, source)
    second.run(chapters=1, also=[2])
    translated = json.loads(
        (out / "translations" / "null.natural.en.json").read_text(encoding="utf-8")
    )
    nine_after = {
        sid: text for sid, text in translated["segments"].items() if sid.startswith("9000")
    }
    assert nine_after == nine_before
    # And the manifest — what speech() reads — marks every heard part, with spans.
    kept = manifest_module.load(out)
    assert kept is not None
    flags = {part.number: (part.transcribed, bool(part.spans)) for part in kept.parts}
    assert flags[1] == (True, True)
    assert flags[2] == (True, True)
    assert flags[9] == (True, True)
    assert flags[5] == (False, False)
    # And each heard part carries its word clocks, for the card's own ear.
    clocked = {part.number: bool(part.words) for part in kept.parts}
    assert clocked[1] and clocked[2] and clocked[9] and not clocked[5]
    a_row = next(iter(next(part for part in kept.parts if part.number == 1).words.values()))[0]
    assert len(a_row) == 4 and a_row[1] > a_row[0] and a_row[3] > a_row[2]


def test_the_manifest_beside_document_json_is_what_speech_reads_with_no_restart(
    fake_audio, tmp_path: Path
) -> None:
    """No @cache, no registry: the manifest sits beside the reader or it does not."""
    from targum.render.builder import speech

    fake_audio.duration = 600.0
    build = builder(tmp_path, recording(tmp_path))
    result = build.run()
    segments = [s for s in result.segmented.segments if s.ref.startswith("part 1:")]
    spoken = speech(result.document, segments, result.out_dir)
    assert spoken.audio.startswith("data:audio/")
    assert spoken.spans
    assert spoken.credit == ""


def test_nothing_said_in_the_first_part_is_an_honest_sentence(fake_audio, tmp_path: Path) -> None:
    fake_audio.duration = 600.0
    build = builder(tmp_path, recording(tmp_path), transcriber=NullTranscriber(text=""))
    with pytest.raises(TargumError, match="Nothing was said in the first"):
        build.run()


def test_usage_counts_seconds_by_model_and_prices_them_per_minute() -> None:
    spent = Usage()
    spent.add_seconds("openai/whisper-1", 600.0)
    assert spent.cost() == pytest.approx(0.06)
    assert spent.state()["seconds"] == 600.0
    merged = spent + spent
    assert merged.seconds_by_model["openai/whisper-1"] == 1200.0


def test_a_model_nobody_priced_counts_its_seconds_and_costs_nothing() -> None:
    """An unknown price is not zero, but pretending to know it is worse."""
    spent = Usage()
    spent.add_seconds("null", 600.0)
    assert spent.cost() == 0.0
    assert spent.state()["seconds"] == 600.0


def test_a_supplied_srt_costs_no_transcription(fake_audio, tmp_path: Path) -> None:
    """Timings the reader already has are used as given; the transcriber never runs."""

    class Refuses:
        name = "refuses"
        model = ""
        needs_key = False
        spent = Usage()

        def available(self) -> tuple[bool, str]:
            return True, ""

        def price_per_minute(self) -> float:
            return 99.0

        def transcribe(self, audio: Path, language: str = "", on_progress: object = None):
            raise AssertionError("a supplied transcript is not a thing to transcribe")

    fake_audio.duration = 90.0
    lines = (
        "1\n00:00:01,000 --> 00:00:04,000\nthe winter came early.\n\n"
        "2\n00:00:05,000 --> 00:00:09,000\nthe river froze over.\n"
    )
    script = tmp_path / "talk.srt"
    script.write_text(lines, encoding="utf-8")
    build = builder(tmp_path, recording(tmp_path), transcriber=Refuses(), transcript=script)
    result = build.run()
    kept = manifest_module.load(result.out_dir)
    assert kept is not None
    assert kept.parts[0].transcribed
    assert kept.parts[0].spans


def test_a_recording_page_inlines_only_its_own_part(fake_audio, tmp_path: Path) -> None:
    """A chapter of Genesis must not carry ninety megabytes of Exodus — the rule that
    shaped the recordings decides this too."""
    fake_audio.duration = 1440.0  # two parts
    fake_audio.pauses = [(719.0, 721.0)]
    build = builder(tmp_path, recording(tmp_path))
    result = build.run()
    pages = {page.name: page.read_text(encoding="utf-8") for page in result.pages}
    one = base64.b64encode(b"part-001.mp3").decode("ascii")
    two = base64.b64encode(b"part-002.mp3").decode("ascii")
    first = next(text for name, text in pages.items() if name == "sec-0001.html")
    second = next(text for name, text in pages.items() if name == "sec-0002.html")
    assert one in first and two not in first
    assert two in second and one not in second


def test_an_imported_recording_has_no_credit_line(fake_audio, tmp_path: Path) -> None:
    """A licence targum cannot verify is one it must not print."""
    fake_audio.duration = 600.0
    build = builder(tmp_path, recording(tmp_path))
    result = build.run()
    for page in result.pages:
        assert "Read by" not in page.read_text(encoding="utf-8")


def test_an_untranscribed_part_says_not_transcribed_yet_and_offers_to_transcribe(
    fake_audio, tmp_path: Path
) -> None:
    fake_audio.duration = 1440.0
    fake_audio.pauses = [(719.0, 721.0)]
    build = builder(tmp_path, recording(tmp_path))
    result = build.run(chapters=1)
    waiting = next(page for page in result.pages if page.name == "sec-0002.html")
    text = waiting.read_text(encoding="utf-8")
    assert "Not transcribed yet." in text
    assert ">Transcribe<" in text
    ready = next(page for page in result.pages if page.name == "sec-0001.html")
    assert "Not transcribed yet." not in ready.read_text(encoding="utf-8")


def test_a_text_transcript_without_the_aligner_plays_straight_through(
    fake_audio, tmp_path: Path, monkeypatch
) -> None:
    """The extra is optional, like the embedding aligner: absent, the audio still
    plays, the page just does not follow along — a shape, not a failure."""
    from targum.audio.align import CtcAligner

    # Absent by declaration rather than by environment: on a machine with the extra
    # installed this test used to align the fake audio for real, which is a different
    # test and a model download inside this one.
    monkeypatch.setattr(
        CtcAligner, "available", lambda self: (False, "uv sync --extra speech-align")
    )
    fake_audio.duration = 90.0
    script = tmp_path / "talk.txt"
    script.write_text("the winter came early. the river froze over.", encoding="utf-8")
    said: list[str] = []
    build = builder(tmp_path, recording(tmp_path), transcript=script)
    build.notify = said.append
    result = build.run()
    kept = manifest_module.load(result.out_dir)
    assert kept is not None
    # Nothing was transcribed and nothing aligned: the parts stay waiting.
    if not any(part.transcribed for part in kept.parts):
        assert any("without following along" in line or "speech-align" in line for line in said)
