"""The media pre-gates: what a recording and its subtitle track must prove before Stanza.

Every fixture here is parsed, never fetched. The shapes are copied from a real
`yt-dlp -J` answer for `oWtGZmz4xOo` — the Khan Academy video that serves another
video's subtitles (targum-internal#139) — so the rejection the issue asks for is
asserted on the numbers that video actually reports, without anybody downloading it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from targum import screen
from targum.ingest.subtitles import parse
from targum.licensing import verdict


def ytdlp(duration: float, *, audio: tuple[str, ...] = ("iw",), **more: Any) -> dict[str, Any]:
    """The corners of a `yt-dlp -J` answer the screen reads."""
    formats: list[dict[str, Any]] = [
        {"format_id": "137", "acodec": "none", "vcodec": "avc1", "language": None}
    ]
    for n, tag in enumerate(audio):
        formats.append(
            {
                "format_id": str(140 + n),
                "acodec": "mp4a.40.2",
                "vcodec": "none",
                "language": tag,
                "language_preference": 10 if n == 0 else -1,
            }
        )
    info: dict[str, Any] = {
        "id": "oWtGZmz4xOo",
        "webpage_url": "https://www.youtube.com/watch?v=oWtGZmz4xOo",
        "title": "מחזור חומצה ציטרית / קרבס",
        "duration": duration,
        "license": "Creative Commons Attribution license (reuse allowed)",
        "language": "iw",
        "formats": formats,
        "subtitles": {"iw": [{"ext": "srt"}, {"ext": "vtt"}]},
        "automatic_captions": {"en": [{"ext": "vtt"}], "iw": [{"ext": "vtt"}]},
    }
    info.update(more)
    return info


def track(until: float, *, every: float = 4.0, words: int = 6) -> str:
    """An SRT of `words`-word cues, one every `every` seconds, ending at `until`."""

    def clock(seconds: float) -> str:
        hours, rest = divmod(seconds, 3600)
        minutes, rest = divmod(rest, 60)
        return f"{int(hours):02d}:{int(minutes):02d}:{rest:06.3f}".replace(".", ",")

    cues = []
    start = 0.0
    n = 1
    while start + every <= until:
        end = start + every
        cues.append(f"{n}\n{clock(start)} --> {clock(end)}\n{' '.join(['מילה'] * words)}\n")
        start = end
        n += 1
    return "\n".join(cues)


#: `oWtGZmz4xOo` runs 17m47s; the track it serves belongs to a 9m38s video and stops
#: at 577.93 s. Real numbers, from the fetch the issue records.
KREBS_S = 1067.0
MYOSIN_TRACK_END_S = 578.0


def test_the_mismatched_khan_track_is_rejected_on_coverage_without_anybody_watching() -> None:
    """Acceptance line two of the issue. The words are Hebrew, the licence is clean, the
    audio is tagged Hebrew, and the text screen passed it. Only the recording's length
    against the track's last cue says the two do not belong together."""
    media = screen.from_ytdlp(ytdlp(KREBS_S))
    cues = parse(track(MYOSIN_TRACK_END_S))
    found = screen.gate(media, cues)
    assert found.coverage == 54
    assert not found.passed
    assert found.reason == "54% covered"


def test_a_track_that_reaches_the_end_passes_and_ninety_five_is_the_line() -> None:
    """The nine clean Khan tracks sit at 97–100%. The gate sits under them and above the
    one defect, and it is a parameter so the number can move when the sample grows."""
    media = screen.from_ytdlp(ytdlp(1000.0))
    assert screen.gate(media, parse(track(992.0))).passed
    at_94 = screen.gate(media, parse(track(940.0)))
    assert at_94.coverage == 94 and not at_94.passed
    assert screen.gate(media, parse(track(940.0)), min_coverage=90).passed


def test_an_english_audio_track_is_dropped_whatever_the_title_says() -> None:
    """Seventeen of 174 licence-clean Khan videos were English under a Hebrew title.
    The tag on the audio format is the artefact; the title is metadata."""
    media = screen.from_ytdlp(ytdlp(1000.0, audio=("en",)))
    found = screen.gate(media, parse(track(1000.0)))
    assert found.reason == "audio en"
    assert found.audio == "en"


def test_youtube_still_says_iw_and_that_is_hebrew() -> None:
    assert screen.same_language("iw", "he")
    assert screen.same_language("he-IL", "he")
    assert not screen.same_language("", "he")
    assert screen.from_ytdlp(ytdlp(1000.0)).audio == ("iw",)


def test_an_untagged_track_is_flagged_and_not_dropped() -> None:
    """No tag is no evidence either way. A drop would throw away every recording ffprobe
    reads without a language tag, which is most local files."""
    media = screen.from_ytdlp(ytdlp(1000.0, audio=()))
    found = screen.gate(media, parse(track(1000.0)))
    assert found.passed
    assert "audio untagged" in found.flags


def test_a_second_audio_language_is_a_flag_and_the_first_is_what_is_reported() -> None:
    """A dubbed video carries both. The original — yt-dlp's highest preference — is what
    the reader would hear, so it is what is reported; the dub is named so somebody looks."""
    media = screen.from_ytdlp(ytdlp(1000.0, audio=("iw", "en")))
    found = screen.gate(media, parse(track(1000.0)))
    assert found.passed
    assert found.audio == "iw"
    assert "audio also en" in found.flags


def test_words_per_minute_outside_the_band_is_a_flag_not_a_drop() -> None:
    """Clean tracks cluster at 80–118 wpm. Far outside that is probably not a transcript of
    this recording, and "probably" earns a look rather than a verdict."""
    media = screen.from_ytdlp(ytdlp(600.0))
    # Six words every four seconds is 90 wpm: inside the band, nothing to say.
    inside = screen.gate(media, parse(track(600.0)))
    assert inside.wpm == 90 and inside.passed and not inside.flags
    # Twenty words every four seconds is 300 wpm: a transcript of something else.
    outside = screen.gate(media, parse(track(600.0, words=20)))
    assert outside.wpm == 300 and outside.passed
    assert "300 wpm" in outside.flags


def test_the_malformed_ninety_nine_hours_cue_is_dropped_rather_than_read_as_coverage() -> None:
    """Two of the twelve Khan tracks end on a cue at 99:59:59. Read naively, that track
    covers a hundred hours of a seventeen-minute video and passes every gate; dropped,
    the real last cue answers, and the drop is named so nobody wonders where it went."""
    srt = track(1060.0) + "\n999\n99:59:59,000 --> 99:59:59,999\n.\n"
    cues = parse(srt)
    assert cues[-1].start == 99 * 3600 + 59 * 60 + 59
    media = screen.from_ytdlp(ytdlp(KREBS_S))
    found = screen.gate(media, cues)
    assert found.passed
    assert found.coverage == 99
    assert found.dropped == 1
    assert "1 cue past the end" in found.flags


def test_a_last_cue_a_few_seconds_past_a_rounded_duration_is_kept() -> None:
    """yt-dlp reports whole seconds and cues carry milliseconds, so a real last cue may
    outrun the file by a little. That is a rounding, not a sentinel, and it is capped at
    100% rather than reported as 101."""
    media = screen.from_ytdlp(ytdlp(600.0))
    cues = parse("1\n00:09:55,000 --> 00:10:03,500\nמילה מילה\n")
    found = screen.gate(media, cues)
    assert found.dropped == 0 and found.coverage == 100


def test_a_recording_without_a_duration_cannot_pass() -> None:
    """Zero is what an answer with no duration reads as, and dividing by it is not a
    coverage. It fails, and says why, rather than passing at 0%."""
    media = screen.from_ytdlp(ytdlp(0))
    assert screen.gate(media, parse(track(100.0))).reason == "no duration"


def test_automatic_captions_are_not_subtitles() -> None:
    """A track YouTube guessed is not a transcript anybody checked, and the screen is
    looking for exactly the mismatch a guess would paper over."""
    media = screen.from_ytdlp(ytdlp(1000.0))
    assert media.subtitles == ("iw",)
    assert media.licence == "Creative Commons Attribution license (reuse allowed)"


def test_a_local_recording_is_read_off_ffprobe_the_same_way(tmp_path: Path) -> None:
    answer = {
        "format": {"duration": "612.480000", "tags": {"title": "שיחה"}},
        "streams": [
            {"codec_type": "video", "tags": {}},
            {"codec_type": "audio", "tags": {"language": "heb"}},
            {"codec_type": "audio", "tags": {"language": "und"}},
        ],
    }
    media = screen.from_ffprobe(answer, tmp_path / "talk.mp4", licence="CC BY-NC 4.0")
    assert media.title == "שיחה"
    assert media.duration == 612.48
    assert media.audio == ("heb",)
    assert media.licence == "CC BY-NC 4.0"


def test_the_two_licence_flags_are_not_one_boolean() -> None:
    """ivrit.ai and NonCommercial audio are exact inverses of nothing-recorded: the first
    may be read for free and may not leave; the second may do neither. And CC BY may do
    both. One column cannot say all three, which is why the output carries two."""
    nc = screen.licence_flags("CC BY-NC 4.0")
    assert nc.reader_publishable and not nc.corpus_exportable
    by = screen.licence_flags("Creative Commons Attribution license (reuse allowed)")
    assert by.reader_publishable and by.corpus_exportable
    nd = screen.licence_flags("CC BY-ND 4.0")
    assert not nd.reader_publishable and not nd.corpus_exportable
    blank = screen.licence_flags("")
    assert not blank.reader_publishable and not blank.corpus_exportable


def test_the_flags_are_the_licensing_modules_verdict_and_not_a_second_reading() -> None:
    """`licensing.py` is where a licence string becomes a decision. The screen asks it
    rather than matching strings of its own, so the two can never disagree."""
    for licence in ("CC BY-SA 3.0", "public domain", "CC BY-NC-SA 4.0", "MIT", "nonsense"):
        call = verdict(licence)
        flags = screen.licence_flags(licence)
        assert flags.corpus_exportable is call.exportable, licence
        assert flags.because == call.because, licence


def test_the_shelf_is_counted_in_the_librarys_own_bands() -> None:
    """≤20 easy, ≤28 mid, per library.js. Unmeasured entries — 0 — are not a band, so a
    shelf with 77 unmeasured texts is counted as the shelf as measured, and the
    ranking says so rather than calling a guess a gap."""
    assert screen.band(20) == "easy" and screen.band(21) == "mid"
    assert screen.band(28) == "mid" and screen.band(29) == "hard"
    counts = screen.shelf_bands([0, 0, 7, 20, 21, 28, 35])
    assert counts == {"easy": 2, "mid": 2, "hard": 1}
