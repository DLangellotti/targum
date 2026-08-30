"""Dialogues: scenes written for a learner, and the audio of them being spoken.

The shelf a beginner needs and the library cannot supply. Tanakh and journalism are real
Hebrew and neither is six turns long, so the bottom of the ladder was empty — a reader
who could not yet hold a verse had nothing to hold at all.

**What is here and what is not.** This package serves a dialogue: the shape of one, where
they live, and the reader that opens them. It does not write them. The scenes themselves,
and the code that composes and voices them, are content — the same split `catalogue.py`
and `weekly/` already make, for the same reason. `write.py` is gitignored beside
`weekly/write.py`, and the dialogues sit under `dialogue.index.root()`, which is inside
`targum-out/` and never enters the repository.

**Why a source rather than a file format.** A dialogue could have been a markdown file
with the speakers written into the text, and then the speaker labels would be part of the
Hebrew — counted as vocabulary, read aloud, and pointed by the diacritizer. Addressing it
as `dialogue:<id>` keeps the turn structure out of the prose, which is what lets a turn
carry a speaker, a gender and a span of audio without any of them being words on the page.
"""

from __future__ import annotations

from .models import Cast, Dialogue, Speaker, Turn

__all__ = ["Cast", "Dialogue", "Speaker", "Turn"]
