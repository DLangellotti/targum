"""A curated video, read off disk as the text of its soundtrack.

The document was made once, on a laptop, by the ordinary audio ingest — a subtitle track
or a transcription, cut into blocks the same way any recording is. What this fetcher does
is hand that back, so a catalogue row can name a video the box is not allowed to fetch.

The source is `video:<id>` and the id is the folder's name, so the same video keys
identically on a laptop and on the box — the reason the dialogues and the weekly address
themselves by name too, rather than by wherever their files happen to sit.
"""

from __future__ import annotations

from ...errors import TargumError
from ...ids import content_hash
from ...models import Document
from ...video import store


class VideoFetcher:
    # Bump when what is read off the store changes shape, so a video on disk re-ingests
    # rather than serving a stale document. The text's own body is hashed as well, which
    # is what catches a re-curation between one build and the next.
    name = "video/1"

    def load(self, identifier: str) -> Document:
        held = store.load(identifier)
        document = store.document(identifier)
        if held is None or document is None:
            known = ", ".join(store.every()[:6]) or "none yet"
            raise TargumError(
                f"There is no curated video called {identifier}.",
                f"Looked in {store.root()}. Videos there: {known}.",
            )
        # The store's own copy carries this already; setting it here means a document
        # written by an older curation is still served under the name of the fetcher
        # that read it, which is what decides whether a build re-ingests.
        document.source = f"video:{identifier}"
        document.ingester = self.name
        document.content_hash = document.recompute_hash()
        document.source_hash = content_hash(document.body())
        return document
