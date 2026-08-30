"""A dialogue, read off disk as a document of turns.

One block per line, kind `turn`, with the speaker beside the text rather than inside it.
That separation is the whole reason this is a fetcher and not a markdown file: written as
`א: שלום` the speaker would be pointed by the diacritizer, counted by the lemmatizer as a
word the reader has learned, and read aloud by the voice.

The title is the scene's Hebrew name and the source is `dialogue:<id>`, so the same scene
keys identically on a laptop and on the box — the reason the weekly addresses itself by
name too, rather than by wherever its file happens to sit.
"""

from __future__ import annotations

from ...dialogue import index
from ...ids import content_hash
from ...models import Block, BlockKind, Document


class DialogueFetcher:
    # Bump when the block shape changes, so a scene on disk re-ingests rather than serving
    # a stale document. The scene's own text is hashed as well, which is what catches an
    # edit between one build and the next.
    name = "dialogue/1"

    def load(self, identifier: str) -> Document:
        scene = index.load(identifier)
        blocks = [
            Block(
                id=f"b{n:04d}",
                kind=BlockKind.turn,
                text=turn.text,
                speaker=turn.who,
            )
            for n, turn in enumerate(scene.turns)
        ]
        document = Document(
            source=f"dialogue:{identifier}",
            title=scene.title,
            language="he",
            blocks=blocks,
            ingester=self.name,
        )
        document.content_hash = document.recompute_hash()
        # What makes the file on disk the source of truth rather than a first draft: a
        # changed scene is a changed text, and `Build.ingest` re-ingests instead of
        # deciding somebody hand-edited the extraction and keeping the old one.
        document.source_hash = content_hash(
            "\n".join(f"{t.who}\t{t.text}\t{t.english}" for t in scene.turns)
        )
        return document
