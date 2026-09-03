"""What a media candidate has to prove before anybody reads it, let alone Stanza.

`scripts/screen_candidates.py` screens text: too short, too long, not in its own script.
A video's text is its subtitle track, and everything that can go wrong between a track
and its recording is invisible to a screen that reads the track alone. Twelve Khan
Academy videos, all licence-verified, went through the text screen and all twelve passed;
one of them served the subtitle file of a different video (targum-internal#139). Its
cues stopped at 54% of the way through. The reader would have had a page whose words had
nothing to do with its sound, and nothing in a word count said so.

So three measurements are taken off the artefact rather than off its metadata, and all
three are cheap enough to run before the model is loaded:

- **The audio track's own language tag.** Not the channel's, not the title's. Seventeen
  of the 174 licence-clean Khan videos were English under a Hebrew title.
- **Coverage**: the last cue's end over the recording's duration. Clean tracks sit at
  97–100%; the mismatched one at 54%. A gate at 95% is decisive and costs nothing.
- **Words per minute**, as a flag rather than a gate: the clean tracks cluster at 80–118.
  A transcript far outside that is probably not a transcript of this recording, but
  "probably" is a reason to look, not a reason to drop.

The parsing and the gating live here and not in the script for the reason
`annotate/difficulty.py` gives: the script owns the sweep, and the rule has to be
importable so it can be tested on a fixture rather than on a download.

Nothing here fetches. `video/youtube.py` asks yt-dlp; `audio/tools.py` asks ffprobe;
this module is handed what they said.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .ingest.subtitles import Cue
from .licensing import Standing, verdict

#: Below this share of the recording, the track is not a track of this recording.
COVERAGE_MIN = 95

#: Where clean Hebrew subtitle tracks sit, in words per minute of media. Outside it is a
#: flag: a sanity band, not a rule about how fast people talk.
WPM_BAND = (80, 118)

#: How far a cue may run past the end of its recording before it is a mistake rather
#: than a rounding. Durations are reported to the second and cues to the millisecond,
#: so a last cue can legitimately outrun the file by a little; a 99:59:59 sentinel cue
#: on a seventeen-minute video outruns it by a hundred hours.
CUE_SLACK_S = 60.0

#: YouTube still says `iw` for Hebrew, as it has since the tag was retired in 1989.
_RETIRED = {"iw": "he", "ji": "yi", "in": "id"}


def same_language(tag: str, language: str) -> bool:
    """Whether two tags name the same language, ignoring region and retired spellings."""

    def bare(value: str) -> str:
        head = (value or "").split("-")[0].lower()
        return _RETIRED.get(head, head)

    return bool(tag) and bare(tag) == bare(language)


@dataclass(frozen=True)
class Media:
    """What a recording says about itself, from whichever tool was asked."""

    source: str
    title: str
    #: Seconds. Zero when nothing said, which fails coverage rather than dividing by it.
    duration: float
    #: Language tags on the audio tracks, most preferred first. Empty means untagged,
    #: which is not the same as Hebrew and not the same as English.
    audio: tuple[str, ...] = ()
    #: Languages with a subtitle track somebody wrote, as opposed to one YouTube guessed.
    subtitles: tuple[str, ...] = ()
    licence: str = ""


def from_ytdlp(info: dict[str, Any]) -> Media:
    """A `yt-dlp -J` answer, read for the four things the gates need.

    Audio languages come off the formats rather than the video's `language`, because
    the video's tag is what the uploader set and the format's is what the track is
    marked as. `automatic_captions` are deliberately not subtitles: a track YouTube
    guessed is not a transcript anybody checked.
    """
    tagged: list[tuple[int, str]] = []
    for fmt in info.get("formats") or []:
        if fmt.get("acodec") in (None, "none"):
            continue
        tag = str(fmt.get("language") or "")
        if tag and tag not in (t for _, t in tagged):
            tagged.append((int(fmt.get("language_preference") or 0), tag))
    tagged.sort(key=lambda pair: -pair[0])
    return Media(
        source=str(info.get("webpage_url") or info.get("original_url") or info.get("id") or ""),
        title=str(info.get("title") or ""),
        duration=float(info.get("duration") or 0),
        audio=tuple(tag for _, tag in tagged),
        subtitles=tuple(str(key) for key in (info.get("subtitles") or {})),
        licence=str(info.get("license") or ""),
    )


def from_ffprobe(answer: dict[str, Any], path: Path, *, licence: str = "") -> Media:
    """An ffprobe answer for a local file, read the same way."""
    form = answer.get("format") or {}
    tags = {str(k).lower(): str(v) for k, v in (form.get("tags") or {}).items()}
    audio: list[str] = []
    for stream in answer.get("streams") or []:
        if stream.get("codec_type") != "audio":
            continue
        tag = str((stream.get("tags") or {}).get("language") or "")
        if tag and tag != "und" and tag not in audio:
            audio.append(tag)
    try:
        duration = float(form.get("duration") or 0)
    except (TypeError, ValueError):
        duration = 0.0
    return Media(
        source=str(path),
        title=tags.get("title", "") or path.stem,
        duration=duration,
        audio=tuple(audio),
        licence=licence,
    )


def usable(cues: Iterable[Cue], duration: float) -> tuple[list[Cue], int]:
    """The cues that belong to a recording this long, and how many did not.

    Two of the twelve Khan tracks carried a cue at 99:59:59, which is not a time in any
    video and breaks a naive "last cue end". A cue that starts after the recording has
    ended, or ends more than `CUE_SLACK_S` past it, is dropped and counted rather than
    allowed to say the track covers a hundred hours.
    """
    kept: list[Cue] = []
    dropped = 0
    for cue in cues:
        if duration > 0 and (cue.start >= duration or cue.end > duration + CUE_SLACK_S):
            dropped += 1
            continue
        kept.append(cue)
    return kept, dropped


def coverage(cues: list[Cue], duration: float) -> int:
    """How much of the recording the track reaches, as a percentage, capped at 100."""
    if duration <= 0 or not cues:
        return 0
    last = max(cue.end for cue in cues)
    return min(100, round(100 * last / duration))


def words_per_minute(cues: list[Cue], duration: float) -> int:
    """Words over the recording's minutes — the recording's, not the track's, so a
    track that stops halfway reads slow as well as short."""
    if duration <= 0:
        return 0
    words = sum(len(cue.text.split()) for cue in cues)
    return round(words / (duration / 60))


@dataclass(frozen=True)
class Gate:
    """What the pre-gates found. `reason` is empty when the candidate may go on."""

    audio: str
    coverage: int
    wpm: int
    dropped: int
    reason: str = ""
    flags: tuple[str, ...] = ()

    @property
    def passed(self) -> bool:
        return not self.reason


def gate(
    media: Media,
    cues: Iterable[Cue],
    *,
    language: str = "he",
    min_coverage: int = COVERAGE_MIN,
    wpm_band: tuple[int, int] = WPM_BAND,
) -> Gate:
    """Whether this recording and this track belong together, and in this language.

    Drops are for what is decisive: an audio track tagged as another language, and a
    track that stops short. Flags are for what deserves a look: an untagged track, a
    second audio language, a wpm outside the band, cues that had to be thrown away.
    """
    kept, dropped = usable(cues, media.duration)
    covered = coverage(kept, media.duration)
    wpm = words_per_minute(kept, media.duration)
    heard = media.audio[0] if media.audio else ""
    flags: list[str] = []
    reason = ""

    if media.audio and not any(same_language(tag, language) for tag in media.audio):
        reason = f"audio {heard}"
    elif media.duration <= 0:
        reason = "no duration"
    elif covered < min_coverage:
        reason = f"{covered}% covered"

    if not media.audio:
        flags.append("audio untagged")
    elif len(media.audio) > 1:
        flags.append("audio also " + ",".join(t for t in media.audio if t != heard))
    if not reason and not wpm_band[0] <= wpm <= wpm_band[1]:
        flags.append(f"{wpm} wpm")
    if dropped:
        flags.append(f"{dropped} cue{'s' if dropped > 1 else ''} past the end")

    return Gate(heard, covered, wpm, dropped, reason, tuple(flags))


@dataclass(frozen=True)
class Flags:
    """Which pool a candidate may enter, and the two are not one boolean.

    ivrit.ai is publishable in a reader that is free to use and cannot leave in a
    commercial corpus; a recording with no licence recorded is exportable nowhere and
    publishable nowhere either. Decided per targum-internal#139 (2026-09-01).
    """

    reader_publishable: bool
    corpus_exportable: bool
    because: str


def licence_flags(licence: str) -> Flags:
    """Both flags off the one verdict `licensing.py` already computes."""
    call = verdict(licence)
    return Flags(
        reader_publishable=call.standing is not Standing.unknown and call.derivatives,
        corpus_exportable=call.exportable,
        because=call.because,
    )


#: The library's bands, `library.js:245`. Written here so ranking against the shelf and
#: drawing the shelf cannot disagree about where mid begins.
EASY_MAX = 20
MID_MAX = 28


def band(difficulty: int) -> str:
    if difficulty <= EASY_MAX:
        return "easy"
    return "mid" if difficulty <= MID_MAX else "hard"


def shelf_bands(difficulties: Iterable[int]) -> dict[str, int]:
    """How many measured texts the shelf holds in each band. Unmeasured ones — zero —
    are not counted, so until targum-internal#131 measures the rest, this is the shelf
    as measured and not the shelf."""
    counts = {"easy": 0, "mid": 0, "hard": 0}
    for difficulty in difficulties:
        if difficulty > 0:
            counts[band(difficulty)] += 1
    return counts
