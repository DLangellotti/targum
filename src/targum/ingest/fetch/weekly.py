"""An issue of the weekly, read off disk.

The composed Hebrew is markdown with front matter and it is the source of truth: a level
that came out stilted is fixed by editing the file, the same way a bad extraction is
fixed by editing `document.json`. This reads it the way the markdown ingester reads any
other file, and differs only in where it looks and what it calls the source.

Not the server's inline-text path, which writes an upload to a machine path and hands
that path over as the source. An absolute path baked into `document.json` would break
`Library.readers`, `cover_name` and `measure_difficulty.on_disk`, all of which key on
`document.source`.
"""

from __future__ import annotations

from pathlib import Path

from ...errors import TargumError
from ...ids import content_hash
from ...models import Document
from ...weekly import index
from ...weekly.models import Level, parse_identifier
from ..markdown import MarkdownIngester


def markdown_path(week: str, level: Level) -> str:
    return str(index.root() / week / f"weekly-{week}-{level.value}.md")


class WeeklyFetcher:
    # Bump when the composed shape changes, so an issue on disk re-ingests rather than
    # serving a stale document. The composed text itself is hashed too, which is what
    # catches a hand-edit between one build and the next.
    name = "weekly/1"

    def load(self, identifier: str) -> Document:
        parsed = parse_identifier(identifier)
        if parsed is None:
            raise TargumError(
                f"Not an issue of the weekly: {identifier}",
                "Name it as <week>-<level>, for example 2026-w36-bet.",
            )
        week, level = parsed
        path = markdown_path(week, level)
        source = Path(path).read_text(encoding="utf-8")
        document = MarkdownIngester().load(path)
        # Addressed by what it is rather than by where it happens to sit, so the same
        # issue keys the same on a laptop and on the box — and so `PUBLIC_SOURCES`
        # recognises it and the English is paid for once between every reader.
        # `source_hash` is what makes the markdown the source of truth rather than a
        # first draft. Without it `Build.ingest` finds a `document.json` whose blocks no
        # longer match the file, reads that as somebody having hand-edited the
        # extraction, and keeps the old one — so editing the issue and rebuilding did
        # nothing at all, silently. Hashing the file makes a changed file a changed
        # text, which is what it is.
        return document.model_copy(
            update={
                "source": f"weekly:{identifier}",
                "ingester": self.name,
                "source_hash": content_hash(source),
            }
        )
