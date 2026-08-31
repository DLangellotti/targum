"""Audio import: what a recording is allowed to be, before anything is spent on it.

The helpers here are deliberately public. Probing a file, planning its parts and mapping
words onto sentences is not content and not a moat — it is where the codec bugs live,
and kept private it would sit where CI can never run it. The recordings themselves are a
reader's own files and never enter the repository.
"""

from __future__ import annotations

import shutil
from pathlib import Path

#: What an import may arrive as. A closed list rather than "whatever ffmpeg reads":
#: ffmpeg reads video containers too, and a gigabyte of film for five minutes of sound
#: is the wrong trade against a storage quota.
AUDIO_SUFFIXES = frozenset({".mp3", ".m4a", ".m4b", ".aac", ".ogg", ".opus", ".flac", ".wav"})

#: Audible's containers. Refused by name before a byte is stored: the protection is the
#: point of the format, and failing at the probe would waste the whole upload first.
DRM_SUFFIXES = frozenset({".aax", ".aa"})

#: Twelve hours. Longer than any audiobook worth splitting by hand; short enough that a
#: mistake — a looped stream, a concatenated archive — is refused with a reason.
MAX_DURATION_S = 43_200.0
MIN_DURATION_S = 1.0

#: Margin either side of a cut, so a part never opens or closes mid-word. The same
#: value the recordings use, for the same reason.
PAD = 0.35

#: Mono at 48k, the bitrate the rest of the library's speech is at.
BITRATE = "48k"

#: What Hebrew speech runs at, for pricing a translation before any text exists.
#: 150 rather than the 120 first guessed: measured on real imports (2026-08-31), a
#: conversational podcast estimated within 3% at 120, but scripted narration ran 30%
#: over — and an estimate should sit on the high side of the bill, not the low one.
SPEECH_WORDS_PER_MINUTE = 150
WORDS_PER_SENTENCE = 12
#: Hebrew runs dense against a tokenizer; measured against the fixtures this sits a
#: little high, which is the side an estimate should sit on.
TOKENS_PER_SPOKEN_WORD = 2.2

#: What stands in for a feed that will not say how long its episode runs: an hour,
#: which errs on the side a budget wants to err on.
TARGET_MINUTES_GUESS = 60

#: How much is heard before a part is bought, when nothing says what language this is.
#: A minute costs under a cent and answers the one question that decides whether the
#: rest is worth buying at all.
LANGUAGE_PROBE_S = 60.0

#: What an upload is read as when nothing says otherwise. The product's own language.
DEFAULT_LANGUAGE = "he"


def is_audio(source: str) -> bool:
    """Whether this source names an audio file, by its suffix alone."""
    return Path(source).suffix.lower() in AUDIO_SUFFIXES


def is_drm(source: str) -> bool:
    return Path(source).suffix.lower() in DRM_SUFFIXES


def ffmpeg_available() -> tuple[bool, str]:
    """Whether audio can be read at all, and what to do about it if not."""
    if shutil.which("ffmpeg") and shutil.which("ffprobe"):
        return True, "ffmpeg"
    return False, "install ffmpeg. Audio imports are off until it is."
