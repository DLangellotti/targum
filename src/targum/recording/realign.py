"""Align an attached prose recording's words again, without cutting or fetching anything.

    python -m targum.recording.realign RECORDING_FOLDER [RECORDING_FOLDER ...]

A prose recording keeps its word timings in `words-NNN.json`, written when it was
attached. Those timings are only as good as the aligner that made them, and until now the
only way to replace them was a re-attach: fetch the text again, re-align the whole reading
and cut every part again. A re-cut changes the part files wherever the seams move, and the
reading's source files have to still be on disk.

This does the smaller job. For each part in the manifest it aligns the part's own mp3
against the words its `words-NNN.json` already lists, in the same order, and writes the
new clocks back into that file. The mp3, the manifest and the list of words stay as they
are, so the only thing a build sees change is where each word starts and ends.

**Only the stretch the words were found in.** A part's stored words were trimmed at
attach, so the audio around them can hold speech the list does not name: "this is a
LibriVox recording", or a heading the text spells and the reader did not say. Forced
alignment has to account for every frame it is given, and speech it has no words for
gets pulled onto the nearest word. So the aligner hears the part from `BEFORE_S` ahead of
the first stored start to `AFTER_S` past the last stored end. The margins are wider than
the old timings' error, and `BEFORE_S` is wider than `to_the_voice` can walk back.

Local and unpaid. A folder is rewritten one part at a time, and each file is replaced
whole, so a crash never leaves a half-written file.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import wave
from array import array
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Protocol

from ..errors import TargumError
from .index import MANIFEST, load_folder
from .models import Row

#: How much of the part the aligner hears either side of the stored words. It must be more
#: than the old timings could be wrong by. The aligner swap moved starts by tens of
#: milliseconds, and `to_the_voice` walks a start back at most 200 ms. It must also be
#: less than the untranscribed speech a part can open with.
BEFORE_S = 0.3
AFTER_S = 0.6

RATE = 16000


class Aligner(Protocol):
    name: str

    def align(
        self, audio: Path, words: list[str], language: str
    ) -> list[tuple[float, float, float]]: ...


def _write_wav(path: Path, pcm: Sequence[float]) -> None:
    """Mono 16-bit PCM at `RATE`, which the aligner's ffmpeg decode reads as it is."""
    frames = array("h", (max(-32768, min(32767, round(x * 32767))) for x in pcm))
    if sys.byteorder != "little":
        frames.byteswap()
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(RATE)
        out.writeframes(frames.tobytes())


def realigned(
    audio: Path,
    rows: list[Row],
    aligner: Aligner,
    language: str,
    read: Callable[[Path, int], Sequence[float]],
) -> list[Row]:
    """The same rows with new clocks, in seconds into `audio`: same words, same order."""
    if not rows:
        return []
    words = [str(row[0]) for row in rows]
    pcm = read(audio, RATE)
    duration = len(pcm) / RATE
    lo = max(0.0, float(rows[0][1]) - BEFORE_S)
    hi = min(duration, float(rows[-1][2]) + AFTER_S)
    window = pcm[int(lo * RATE) : int(hi * RATE)]
    offset = int(lo * RATE) / RATE
    del pcm
    with tempfile.TemporaryDirectory() as scratch:
        heard = Path(scratch) / "window.wav"
        _write_wav(heard, window)
        del window
        timed = aligner.align(heard, words, language)
    if len(timed) != len(words):
        raise TargumError(
            f"The aligner returned {len(timed)} clocks for {len(words)} words in {audio.name}."
        )

    def clock(at: float) -> float:
        return round(min(max(0.0, at + offset), duration), 3)

    return [
        [word, clock(start), clock(end), round(score, 3)]
        for word, (start, end, score) in zip(words, timed, strict=True)
    ]


def realign_folder(
    folder: Path,
    aligner: Aligner,
    language: str = "he",
    read: Callable[[Path, int], Sequence[float]] | None = None,
    notify: Callable[[str], None] = print,
) -> int:
    """Rewrite every part's `words` file in one recording folder. Returns the part count.

    Only the files the manifest names are touched. A stray file in the folder is left
    alone, because the manifest is what a build reads.
    """
    if read is None:
        from ..audio.tools import samples

        read = samples
    recording = load_folder(folder)
    if recording is None:
        raise TargumError(f"{folder / MANIFEST} is missing or does not read.")
    done = 0
    for part in recording.parts:
        if not part.words:
            notify(f"  {part.audio}: no words file (scripture spans), left alone")
            continue
        path = folder / part.words
        rows: list[Row] = json.loads(path.read_text(encoding="utf-8"))
        fresh = realigned(folder / part.audio, rows, aligner, language, read)
        staged = path.with_name(path.name + ".tmp")
        staged.write_text(json.dumps(fresh, ensure_ascii=False), encoding="utf-8")
        os.replace(staged, path)
        done += 1
        notify(f"  {part.words}: {len(fresh)} words")
    return done


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folders", nargs="+", type=Path, help="Recording folders to realign.")
    parser.add_argument("--language", default="he")
    args = parser.parse_args()
    from ..audio.align import CtcAligner

    aligner = CtcAligner(args.language)
    usable, hint = aligner.available()
    if not usable:
        raise SystemExit(f"The forced aligner is not installed: {hint}")
    for folder in args.folders:
        print(f"== {folder} ({aligner.name})")
        realign_folder(folder, aligner, args.language)


if __name__ == "__main__":
    main()
