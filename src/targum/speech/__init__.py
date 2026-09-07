"""Speech out: a line of Hebrew read aloud, on a path a reader can trigger.

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
**Counted, not yet priced:** no rate for this model is written in any `PRICES` table, so
`Usage.cost()` counts its seconds and charges nothing, which `usage.py` says is the honest
answer to an unknown price. The rate belongs beside `transcribe.PRICES` the day it is read
off the console, and until then a spoken reply costs the reader hours and the box a
figure the ledger does not know.
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
#: What `Usage` records the seconds under. Not in `transcribe.PRICES`, on purpose: see
#: the module docstring.
NAME = f"gemini/{MODEL}"
#: The voice the weekly narrates in.
VOICE = "Leda"
#: Where the key comes from. Its own variable rather than the weekly's key file, because
#: a box has an environment file and no laptop's filing.
KEY = "TARGUM_TTS_KEY"

ASK = "Read this Hebrew aloud, unhurried, as a teacher would to a learner. Say only this:\n\n"

#: 24 kHz, mono, 16-bit: what the API answers with, and what the header below declares.
RATE = 24000
BYTES_PER_SECOND = RATE * 2


def available() -> tuple[bool, str]:
    if not os.environ.get(KEY):
        return False, f"set {KEY} in the environment"
    return True, MODEL


def say(text: str, voice: str = VOICE, key: str | None = None) -> bytes:
    """One request, one clip. Returns WAV bytes."""
    import base64
    import urllib.request

    token = key or os.environ.get(KEY, "")
    if not token:
        raise TargumError("No voice on this box.", available()[1])
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key={token}"
    body = {
        "contents": [{"parts": [{"text": ASK + text}]}],
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
        raise TargumError("The voice did not answer.", "Try again in a moment.") from error
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


def render(text: str, into: Path, voice: str = VOICE) -> Clip:
    """Say `text` and write the clip beside `into` (its suffix chosen here): mp3 where
    ffmpeg is present, at the bitrate the rest of the shelf's speech is at; the WAV
    itself where it is not. The seconds come off the WAV either way."""
    spoken = say(text, voice)
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
