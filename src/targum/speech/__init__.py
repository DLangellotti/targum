"""Speech out: a line read aloud, on a path a reader can trigger.

The client lived in `weekly/voice.py`, which is gitignored: it is content tooling, run by
the operator on a laptop, and a public checkout — CI's, and the wheel on the box — has
never had it. A reader pressing "hear" on the chat page is a different thing: it runs on
the box, from the wheel, and has to be testable where the private half is absent. So the
client is here, public, and the weekly's script can import it.

What is honest about it, and is said rather than hidden: this is a whole-utterance
`generateContent` call that returns a clip, not a stream. A spoken reply is seconds to
first sound. That is push-to-talk, and the page calls it that.

**Metered by the clip, not the text.** Speech out draws on the same eight hours a
recording does (decided 2026-09-05), and the seconds charged are read off the WAV the API
returned — 24 kHz mono 16-bit, so `len(pcm) / 48000` — never estimated from the words.
**Priced since 2026-09-13.** Until then no rate was written anywhere, so `Usage.cost()`
counted the seconds and charged nothing, and every money ceiling — the box's day, the
account's, the chat's — was blind to speech: a claim of nothing is invisible to a sum of
claims. The rate is `PRICES` below, in this module rather than beside
`transcribe.PRICES`, because that table's dearest row is the fallback rate for a
transcriber with no key, and a voice in it would raise every recording's quote.
"""

from __future__ import annotations

import json
import os
import shutil
import struct
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from ..errors import TargumError

MODEL = "gemini-3.1-flash-tts-preview"
#: What `Usage` records the seconds under, and the key of its row in `PRICES`.
NAME = f"gemini/{MODEL}"
#: USD per minute of speech out. Google's published rate for this model is $20 per
#: million audio tokens at 25 tokens a second — 1,500 a minute, so $0.03 — and $1 per
#: million text tokens in, which at a sentence a request is a rounding error and is left
#: out (read off ai.google.dev/gemini-api/docs/pricing on 2026-09-13). Charged on the
#: clip's seconds, which are measured, rather than on tokens nobody here reads back.
PRICES: dict[str, float] = {NAME: 0.03}
#: The voice the weekly narrates in.
VOICE = "Leda"
#: Where the key comes from. Its own variable rather than the weekly's key file, because
#: a box has an environment file and no laptop's filing.
KEY = "TARGUM_TTS_KEY"

ASK = "Read this Hebrew aloud, unhurried, as a teacher would to a learner. Say only this:\n\n"

#: The languages the voice reads, and asks for by name (2026-09-13). Gemini's speech model
#: lists all four; it lists neither Yiddish nor Aramaic, and a Hebrew reading of either
#: would be a voice saying the letters in the wrong language, so neither is offered.
SPOKEN = frozenset({"he", "fr", "ru", "it"})


def _code(language: str) -> str:
    return (language or "he").split("-")[0].lower()


def speaks(language: str) -> bool:
    """Whether the voice reads this language."""
    return _code(language) in SPOKEN


def ask(language: str = "he") -> str:
    """The instruction in front of the text, naming the language it is in. Hebrew's is
    `ASK`, byte for byte."""
    code = _code(language)
    if code == "he":
        return ASK
    from ..translate.prompts import language_name

    return ASK.replace("Hebrew", language_name(code))


#: 24 kHz, mono, 16-bit: what the API answers with, and what the header below declares.
RATE = 24000
BYTES_PER_SECOND = RATE * 2


def available() -> tuple[bool, str]:
    if not os.environ.get(KEY):
        return False, f"set {KEY} in the environment"
    return True, MODEL


def priced() -> bool:
    """Whether the voice has a rate in `PRICES` — the condition on which it may be sold
    to a reader (decided 2026-09-10, targum-internal#246): without the row, seconds are
    counted and not costed, and nothing on a page offers them."""
    return NAME in PRICES


class Interrupted(TargumError):
    """The voice stopped after some of the speech was already made, and paid for.

    `seconds` is how much: the lines said before the one that failed, or the whole clip
    when it was said and could not be written. Releasing the claim on a failure like
    this would hand money back to the budget that Google has already taken.
    """

    def __init__(self, message: str, hint: str | None = None, *, seconds: float) -> None:
        super().__init__(message, hint)
        self.seconds = seconds


def say(text: str, voice: str = VOICE, key: str | None = None, language: str = "he") -> bytes:
    """One request, one clip, in the language named. Returns WAV bytes."""
    import base64
    import urllib.request

    if not speaks(language):
        raise TargumError("We can't read that language aloud yet.")
    token = key or os.environ.get(KEY, "")
    if not token:
        raise TargumError("We can't make a voice here.", available()[1])
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key={token}"
    body = {
        "contents": [{"parts": [{"text": ask(language) + text}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}}},
        },
    }
    request = urllib.request.Request(
        url, json.dumps(body).encode("utf-8"), {"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as answer:
            payload = json.loads(answer.read())
        raw = payload["candidates"][0]["content"]["parts"][0]["inlineData"]["data"]
    except Exception as error:  # noqa: BLE001 - one sentence for the reader, whatever the API said
        raise TargumError("The voice didn't answer.", "Try again in a moment.") from error
    return wav(base64.b64decode(raw))


def wav(pcm: bytes) -> bytes:
    """A WAV header on raw 24 kHz mono 16-bit PCM, so ffmpeg and a browser both read it."""
    head = b"RIFF" + struct.pack("<I", 36 + len(pcm)) + b"WAVEfmt "
    head += struct.pack("<IHHIIHH", 16, 1, 1, RATE, BYTES_PER_SECOND, 2, 16) + b"data"
    head += struct.pack("<I", len(pcm))
    return head + pcm


def duration(clip: bytes) -> float:
    """Seconds of speech in a WAV this module made, read off the header — measured."""
    if len(clip) < 44 or clip[:4] != b"RIFF":
        return 0.0
    (size,) = struct.unpack("<I", clip[40:44])
    return float(size) / BYTES_PER_SECOND


@dataclass(frozen=True)
class Clip:
    path: Path
    kind: str
    seconds: float


def render(text: str, into: Path, voice: str = VOICE, language: str = "he") -> Clip:
    """Say `text` and write the clip beside `into` (its suffix chosen here): mp3 where
    ffmpeg is present, at the bitrate the rest of the shelf's speech is at; the WAV
    itself where it is not. The seconds come off the WAV either way."""
    spoken = say(text, voice, language=language)
    try:
        return write(spoken, into)
    except Exception as error:
        raise Interrupted(
            "The voice was made and could not be kept.",
            "Try again in a moment.",
            seconds=duration(spoken),
        ) from error


def render_lines(
    lines: list[str], into: Path, voice: str = VOICE, language: str = "he"
) -> tuple[Clip, list[tuple[float, float]]]:
    """Say each line and write them as one clip, with where each line sits in it.

    One request a line, and the seconds of each read off its own WAV, so the spans are
    exact without an aligner — the thing a reader's per-line play needs and a
    whole-section clip could not give (targum-internal#246). The clip is one file for
    the same reason an import's part is: a reader plays a slice of one file, and a
    page that carries its audio inline carries one.
    """
    pcm = b""
    spans: list[tuple[float, float]] = []
    for line in lines:
        try:
            spoken = say(line, voice, language=language) if line.strip() else wav(b"")
        except TargumError as error:
            raise Interrupted(
                error.message, error.hint, seconds=len(pcm) / BYTES_PER_SECOND
            ) from error
        start = len(pcm) / BYTES_PER_SECOND
        pcm += spoken[44:]
        end = len(pcm) / BYTES_PER_SECOND
        spans.append((round(start, 3), round(end, 3)))
    try:
        return write(wav(pcm), into), spans
    except Exception as error:
        raise Interrupted(
            "The voice was made and could not be kept.",
            "Try again in a moment.",
            seconds=len(pcm) / BYTES_PER_SECOND,
        ) from error


def write(spoken: bytes, into: Path) -> Clip:
    """One WAV this module made, written beside `into` as mp3 where ffmpeg is present."""
    seconds = duration(spoken)
    into.parent.mkdir(parents=True, exist_ok=True)
    if shutil.which("ffmpeg"):
        target = into.with_suffix(".mp3")
        with tempfile.NamedTemporaryFile(suffix=".wav") as raw:
            raw.write(spoken)
            raw.flush()
            subprocess.run(
                [
                    "ffmpeg",
                    "-nostdin",
                    "-v",
                    "error",
                    "-y",
                    "-i",
                    raw.name,
                    "-ac",
                    "1",
                    "-b:a",
                    "48k",
                    str(target),
                ],
                check=True,
            )
        return Clip(target, "audio/mpeg", seconds)
    target = into.with_suffix(".wav")
    target.write_bytes(spoken)
    return Clip(target, "audio/wav", seconds)
