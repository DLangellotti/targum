"""ElevenLabs Scribe, over plain HTTP.

The default where its key is present: of the hosted engines with word timestamps its
Hebrew is the strongest, and the reader lives with the transcript. It also says which
voice said what and what was music rather than speech — both of which the refiner
wants and whisper cannot give.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from ..errors import TargumError
from ..usage import Usage
from .base import Progress
from .models import Transcript, Word

URL = "https://api.elevenlabs.io/v1/speech-to-text"
TIMEOUT = 300.0


class ScribeTranscriber:
    MODEL = "scribe_v2"
    needs_key = True

    def __init__(self, model: str | None = None) -> None:
        self.model = model or self.MODEL
        self.spent = Usage()

    @property
    def name(self) -> str:
        return f"elevenlabs/{self.model}"

    def available(self) -> tuple[bool, str]:
        if not os.environ.get("ELEVENLABS_API_KEY"):
            return False, "set ELEVENLABS_API_KEY in .env, beside the Anthropic one"
        return True, self.model

    def price_per_minute(self) -> float:
        from . import PRICES

        return PRICES.get(self.name, 0.0)

    def transcribe(
        self,
        audio: Path,
        language: str = "",
        on_progress: Progress | None = None,
    ) -> Transcript:
        import httpx

        key = os.environ.get("ELEVENLABS_API_KEY", "")
        if not key:
            raise TargumError("No transcriber key.", self.available()[1])
        data: dict[str, Any] = {
            "model_id": self.model,
            "diarize": "true",
            "tag_audio_events": "true",
            "timestamps_granularity": "word",
        }
        if language:
            data["language_code"] = language.split("-")[0]
        with httpx.Client(timeout=TIMEOUT) as client:
            with audio.open("rb") as handle:
                response = client.post(
                    URL,
                    headers={"xi-api-key": key},
                    data=data,
                    files={"file": (audio.name, handle, "audio/mpeg")},
                )
        if response.status_code >= 400:
            raise TargumError("The recording could not be transcribed.", response.text[:200])
        try:
            answer: dict[str, Any] = response.json()
        except json.JSONDecodeError as error:
            raise TargumError("The recording could not be transcribed.") from error

        words: list[Word] = []
        voices: dict[str, str] = {}
        length = 0.0
        for word in answer.get("words") or []:
            kind = str(word.get("type") or "word")
            if kind == "spacing":
                continue
            text = str(word.get("text") or "").strip()
            if not text:
                continue
            end = float(word.get("end") or 0.0)
            length = max(length, end)
            voice = str(word.get("speaker_id") or "")
            if voice and voice not in voices:
                # speaker_0 becomes "1": a number a page can show beside a line
                # without pretending to know anybody's name.
                voices[voice] = str(len(voices) + 1)
            words.append(
                Word(
                    text=text,
                    start=round(float(word.get("start") or 0.0), 3),
                    end=round(end, 3),
                    confidence=float(word.get("logprob") or 0.0) >= -1.5 and 1.0 or 0.3,
                    speaker=voices.get(voice, ""),
                    event=kind == "audio_event",
                )
            )
        self.spent.add_seconds(self.name, length)
        if on_progress:
            on_progress(len(words))
        return Transcript(
            provider=self.name,
            model=self.model,
            language=str(answer.get("language_code") or "") or language,
            duration=length,
            words=words,
        )
