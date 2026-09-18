"""The paid services targum calls, and where each one is topped up.

The back office lists them, each with the balance last read off its console and a
button to that console (2026-09-18). The balance is typed in, not fetched. Of the five,
only ElevenLabs says what is left to the key the box already holds; Anthropic and OpenAI
say it only to an admin key, which can do far more than read a number, and Google and
DataImpulse do not say it to a key at all. So the balance is what somebody read off the
console, with the day they read it, and the page says so. A figure with its date is
honest; a figure fetched live from three places and guessed at for two is not.

Only whether a key is set is read from the environment, never the key.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Service:
    """One paid API, as the back office shows it."""

    id: str
    name: str
    #: What targum spends it on, in the page's words.
    used_for: str
    #: The variables any one of which means it is set up here.
    env: tuple[str, ...]
    #: Where it is topped up. The billing page itself, not the dashboard's front.
    console: str

    def configured(self) -> bool:
        return any(os.environ.get(name, "").strip() for name in self.env)


SERVICES: tuple[Service, ...] = (
    Service(
        "anthropic",
        "Anthropic",
        "translation, meanings, chat, the weekly",
        ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"),
        "https://platform.claude.com/settings/billing",
    ),
    Service(
        "openai",
        "OpenAI",
        "transcription, covers",
        ("OPENAI_API_KEY",),
        "https://platform.openai.com/settings/organization/billing/overview",
    ),
    Service(
        "elevenlabs",
        "ElevenLabs",
        "transcription",
        ("ELEVENLABS_API_KEY",),
        "https://elevenlabs.io/app/subscription",
    ),
    Service(
        "gemini",
        "Google Gemini",
        "spoken audio",
        ("TARGUM_TTS_KEY",),
        "https://aistudio.google.com/billing",
    ),
    Service(
        "dataimpulse",
        "DataImpulse",
        "YouTube egress",
        ("TARGUM_YTDLP_PROXY",),
        "https://app.dataimpulse.com/plans",
    ),
)

BY_ID = {service.id: service for service in SERVICES}

#: As long as a console writes a balance: "$41.20", "12,400 credits", "2.1 GB".
SAID_MAX = 60
