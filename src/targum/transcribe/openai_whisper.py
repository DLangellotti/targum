"""OpenAI's whisper-1, over plain HTTP.

Not the `openai` package — the covers took this position first and for the same
reason: one dependency for one endpoint, reached the same way the other providers are.
whisper-1 rather than the gpt-4o transcription family because only whisper-1 returns
word timestamps, and the timestamps are the entire point here.
"""

from __future__ import annotations

import json
import math
import os
import re
from pathlib import Path
from typing import Any

from ..errors import OffHere, TargumError
from ..usage import Usage
from .base import Progress, language_tag
from .models import Transcript, Word

URL = "https://api.openai.com/v1/audio/transcriptions"
TIMEOUT = 300.0

#: The API refuses files over 25 MB; a margin below it, because the request carries
#: more than the file.
MAX_BYTES = 24 * 1024 * 1024

#: whisper invents fluent text over silence and music, and says so obliquely: the
#: segment's no-speech probability is high *and* its mean log-probability is low. Words
#: in such a segment are dropped — a reader cannot tell a hallucinated sentence from a
#: heard one, and the difficulty measurement counts every invented word.
#:
#: Both, as whisper's own decoder asks, never the first alone. On Hebrew the no-speech
#: probability runs high over plain speech: measured on a ten-minute interview
#: (2026-09-14), two minutes of it read 0.90–0.98 while whisper was sure of every word
#: (−0.17), and the old either-one rule threw away 463 of 1,283 words — a gap a reader
#: saw as a big chunk of the transcript missing.
NO_SPEECH = 0.6

#: How much of a title is handed to whisper as its prompt. It reads the last 224 tokens.
PROMPT_CHARS = 400
LOW_SEGMENT_LOGPROB = -1.0


class WhisperTranscriber:
    MODEL = "whisper-1"
    needs_key = True

    def __init__(self, model: str | None = None) -> None:
        self.model = model or self.MODEL
        self.spent = Usage()

    @property
    def name(self) -> str:
        return f"openai/{self.model}"

    def available(self) -> tuple[bool, str]:
        if not os.environ.get("OPENAI_API_KEY"):
            return False, "set OPENAI_API_KEY in .env, beside the Anthropic one"
        return True, self.model

    def price_per_minute(self) -> float:
        from . import PRICES

        return PRICES.get(self.name, 0.0)

    def transcribe(
        self,
        audio: Path,
        language: str = "",
        on_progress: Progress | None = None,
        hint: str = "",
    ) -> Transcript:
        pieces = self._pieces(audio)
        words: list[Word] = []
        total = 0.0
        spoken_language = ""
        for piece, offset in pieces:
            answer = self._ask(piece, language, hint)
            spoken_language = spoken_language or str(answer.get("language") or "")
            length = float(answer.get("duration") or 0.0)
            total = max(total, offset + length)
            words.extend(self._words(answer, offset))
            self.spent.add_seconds(self.name, length)
            if on_progress:
                on_progress(1)
        return Transcript(
            provider=self.name,
            model=self.model,
            language=_tag(spoken_language) or language,
            duration=total,
            words=words,
        )

    def _pieces(self, audio: Path) -> list[tuple[Path, float]]:
        """The file whole, or in chunks the API will take, cut at pauses.

        Timings come back per chunk, so each carries the offset that puts its words
        back on the part's own clock.
        """
        from ..audio import tools

        size = audio.stat().st_size
        if size <= MAX_BYTES:
            return [(audio, 0.0)]
        length = tools.duration(audio)
        count = math.ceil(size / MAX_BYTES)
        edges = [length * n / count for n in range(1, count)]
        seams: list[float] = []
        for edge in edges:
            window = 30.0
            pauses = tools.silences(audio, max(0.0, edge - window), window * 2)
            if pauses:
                a, b = max(pauses, key=lambda pair: pair[1] - pair[0])
                seams.append(round((a + b) / 2, 3))
            else:
                seams.append(round(edge, 3))
        bounds = [0.0, *seams, length]
        pieces: list[tuple[Path, float]] = []
        for n, (start, end) in enumerate(zip(bounds[:-1], bounds[1:], strict=True)):
            piece = audio.with_name(f"{audio.stem}-chunk-{n:02d}.mp3")
            tools.cut(audio, piece, start, end)
            pieces.append((piece, start))
        return pieces

    def _ask(self, audio: Path, language: str, hint: str = "") -> dict[str, Any]:
        import httpx

        key = os.environ.get("OPENAI_API_KEY", "")
        if not key:
            raise OffHere("No transcriber key.", self.available()[1])
        data: dict[str, Any] = {
            "model": self.model,
            "response_format": "verbose_json",
            "timestamp_granularities[]": ["word", "segment"],
        }
        if language:
            data["language"] = language.split("-")[0]
        if hint.strip():
            # The title, as whisper's prompt: the names in it are spelled as written.
            data["prompt"] = hint.strip()[:PROMPT_CHARS]
        with httpx.Client(timeout=TIMEOUT) as client:
            with audio.open("rb") as handle:
                response = client.post(
                    URL,
                    headers={"Authorization": f"Bearer {key}"},
                    data=data,
                    files={"file": (audio.name, handle, "audio/mpeg")},
                )
        if response.status_code >= 400:
            # Their message, not ours: it says which of the many things went wrong.
            raise TargumError("The recording could not be transcribed.", response.text[:200])
        try:
            answer: dict[str, Any] = response.json()
        except json.JSONDecodeError as error:
            raise TargumError("The recording could not be transcribed.") from error
        return answer

    @staticmethod
    def _words(answer: dict[str, Any], offset: float) -> list[Word]:
        # Which stretches of the clock were hallucinated, from the segments' own
        # confessions; every word inside one is dropped.
        invented: list[tuple[float, float]] = []
        shaky: list[tuple[float, float]] = []
        for segment in answer.get("segments") or []:
            start = float(segment.get("start") or 0.0)
            end = float(segment.get("end") or 0.0)
            unsure = float(segment.get("avg_logprob") or 0.0) < LOW_SEGMENT_LOGPROB
            if unsure and float(segment.get("no_speech_prob") or 0.0) > NO_SPEECH:
                invented.append((start, end))
            elif unsure:
                shaky.append((start, end))

        def inside(moment: float, spans: list[tuple[float, float]]) -> bool:
            return any(a <= moment < b for a, b in spans)

        words: list[Word] = []
        for text, start, end in _printed(answer):
            if not text or inside(start, invented):
                continue
            words.append(
                Word(
                    text=text,
                    start=round(offset + start, 3),
                    end=round(offset + end, 3),
                    confidence=0.3 if inside(start, shaky) else 1.0,
                )
            )
        return words


_CHUNK = re.compile(r"\w+")


def _printed(answer: dict[str, Any]) -> list[tuple[str, float, float]]:
    """Each heard word as the segments print it, on the word list's clock.

    whisper-1's word list is bare: no punctuation, and every apostrophe gone, so French
    "j'ai" came back as "j" and "ai" and the page read "j ai pu commencer" (David,
    2026-10-10). The segments' text, in the same answer, has the marks. The two are
    matched letter-run by letter-run, and a printed token whose every run was heard, by
    words heard for it alone, takes their place: one word, from the first one's start to
    the last one's end. Anything that does not line up keeps the bare word, so the words
    on the page are still the words whisper heard, each on its own clock.
    """
    import difflib

    heard = [
        (
            str(word.get("word") or "").strip(),
            float(word.get("start") or 0.0),
            float(word.get("end") or 0.0),
        )
        for word in answer.get("words") or []
    ]
    bare = [(text, start, end) for text, start, end in heard if text]
    text = " ".join(str(segment.get("text") or "") for segment in answer.get("segments") or [])
    tokens = text.split() or str(answer.get("text") or "").split()
    if not tokens:
        return bare
    # Letter runs on each side, each run knowing whose it is.
    said: list[str] = []
    said_by: list[int] = []
    for index, (spelled, _, _) in enumerate(bare):
        for run in _CHUNK.findall(spelled):
            said.append(run.casefold())
            said_by.append(index)
    printed: list[str] = []
    printed_by: list[int] = []
    for index, written in enumerate(tokens):
        for run in _CHUNK.findall(written):
            printed.append(run.casefold())
            printed_by.append(index)
    token_of: dict[int, int] = {}
    matcher = difflib.SequenceMatcher(a=said, b=printed, autojunk=False)
    for block in matcher.get_matching_blocks():
        for step in range(block.size):
            token_of[block.a + step] = printed_by[block.b + step]
    runs_of_word: dict[int, list[int]] = {}
    for at, heard_as in enumerate(said_by):
        runs_of_word.setdefault(heard_as, []).append(at)
    runs_of_token: dict[int, int] = {}
    for written_as in printed_by:
        runs_of_token[written_as] = runs_of_token.get(written_as, 0) + 1
    # The token each word was wholly heard as, where it was.
    whole: dict[int, int] = {}
    for heard_as, ats in runs_of_word.items():
        owners = {token_of[at] for at in ats if at in token_of}
        if len(owners) == 1 and all(at in token_of for at in ats):
            whole[heard_as] = owners.pop()
    out: list[tuple[str, float, float]] = []
    index = 0
    while index < len(bare):
        if index not in whole:
            out.append(bare[index])
            index += 1
            continue
        owner = whole[index]
        group = [index]
        while whole.get(group[-1] + 1) == owner:
            group.append(group[-1] + 1)
        covered = sum(len(runs_of_word[one]) for one in group)
        if covered == runs_of_token.get(owner, 0):
            out.append((tokens[owner], bare[group[0]][1], bare[group[-1]][2]))
        else:
            out.extend(bare[one] for one in group)
        index = group[-1] + 1
    return out


def _tag(language: str) -> str:
    """whisper answers with a language name — "hebrew" — rather than a tag."""
    return language_tag(language)
