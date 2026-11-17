"""A short story targum wrote, read off disk as a document of paragraphs.

    story:fr-01-un-dimanche-a-lyon

The narrative counterpart of `dialogue:`: a text written and checked by the scene loop
(targum-internal `scenes/`, French A2 since 2026-11-17), kept as a file on a shelf of
its own rather than as a link, so a laptop and the box key the same text identically and
the box can build it again. Unlike a scene, a story is prose, so each paragraph is an
ordinary paragraph block, split into sentences and measured as any reader is; its voice
is a reading attached on the recordings shelf, not a scene's own audio.

A story file is `<id>.json`:
`{"id": …, "language": "fr", "title": …, "english": …, "gloss": …,
"paragraphs": [{"text": …, "english": …}]}`. The shelf is the first of
`TARGUM_STORY_DIR` and a `stories` folder beside the dialogue shelf, so a deployment
that has its dialogues somewhere has its stories next to them with nothing else to set.
The stories are content and never enter this repository.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from ...errors import OffHere
from ...ids import content_hash
from ...models import Block, BlockKind, Document


def root() -> Path:
    named = os.environ.get("TARGUM_STORY_DIR", "").strip()
    if named:
        return Path(named).expanduser()
    from ...dialogue import index

    return index.root().parent / "stories"


def read(identifier: str) -> dict[str, Any]:
    from ...dialogue import index

    path = root() / f"{index.checked(identifier, 'story')}.json"
    if not path.exists():
        known = ", ".join(sorted(p.stem for p in root().glob("*.json"))[:6]) or "none yet"
        raise OffHere(
            f"There is no story called {identifier}.",
            f"Looked in {root()}. Stories there: {known}.",
            key="shelf.unavailable",
        )
    loaded: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return loaded


class StoryFetcher:
    # Bump when the block shape changes, so a story on disk re-ingests.
    name = "story/1"

    def load(self, identifier: str) -> Document:
        story = read(identifier)
        paragraphs = [str(p["text"]) for p in story["paragraphs"] if str(p["text"]).strip()]
        document = Document(
            source=f"story:{identifier}",
            title=str(story["title"]),
            language=str(story["language"]),
            blocks=[
                Block(id=f"b{n:04d}", kind=BlockKind.paragraph, text=text)
                for n, text in enumerate(paragraphs)
            ],
            ingester=self.name,
        )
        document.content_hash = document.recompute_hash()
        # The file is the source of truth, as a dialogue's is: an edited story re-ingests.
        document.source_hash = content_hash("\n".join(paragraphs))
        return document
