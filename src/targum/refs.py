"""Give artifacts written before `sefaria/3` their verse refs.

A recording is addressed by verse — "Ruth 1:1" — and refs arrived with ingester
`sefaria/3`. A targum ingested before that has segments with nothing to map a recording
onto, so it stays silent however often the page is rewritten: `rebuild` renders from
those same segments and cannot invent what is not in them.

Re-ingesting the whole text would fix it and costs nothing at a model, but it re-runs the
lemmatizer over every word and rewrites the annotation a reader's own marks are keyed to.
That is a great deal of machinery, and a change to somebody's words, to add a field that
was already decided the moment the text was fetched.

So this asks the source for the document again — a fetch, no model, no Stanza — and
copies the refs onto the segments already on disk.

**Matched in order and checked by text at every step.** A verse is never split, so the
nth verse segment is the nth verse block and its text is identical; where that stops
being true the whole file is left alone rather than half-written. Position is how they
are paired and text is what proves the pairing, which is the only way position is safe
to use here.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from .models import BlockKind, Document, SegmentedDocument, is_biblical, read_artifact


def wants_refs(document: Document, segmented: SegmentedDocument) -> bool:
    """Whether this text is one a recording could reach but cannot yet."""
    if not is_biblical(document.source):
        return False
    verses = [s for s in segmented.segments if s.kind is BlockKind.verse]
    return bool(verses) and not any(segment.ref for segment in verses)


def refs_from(document: Document, segmented: SegmentedDocument) -> dict[str, str] | None:
    """Segment id to ref, or None where the two do not line up exactly.

    None rather than a partial answer: a recording mapped onto the wrong verses is a
    reader hearing words that are not the ones in front of them, and there is nothing in
    the page that would show it.
    """
    blocks = [block for block in document.blocks if block.kind is BlockKind.verse]
    verses = [segment for segment in segmented.segments if segment.kind is BlockKind.verse]
    if len(blocks) != len(verses):
        return None
    out: dict[str, str] = {}
    for block, segment in zip(blocks, verses, strict=True):
        if block.text != segment.text or not block.ref:
            return None
        out[segment.id] = block.ref
    return out


def backfill(
    root: Path,
    fetch: Callable[[str], Document],
    notify: Callable[[str], None] = lambda message: None,
) -> tuple[int, int]:
    """Walk every targum under `root` and give the older ones their refs.

    Returns how many were filled and how many were left alone. Idempotent: a text that
    already has refs is skipped without a fetch, so this is safe to run again and safe to
    run over a shelf that is half migrated.
    """
    filled = skipped = 0
    fetched: dict[str, Document] = {}
    for path in sorted(root.rglob("segments.json")):
        folder = path.parent
        document = read_artifact(Document, folder / "document.json")
        segmented = read_artifact(SegmentedDocument, path)
        if document is None or segmented is None or not wants_refs(document, segmented):
            continue
        if document.source not in fetched:
            try:
                fetched[document.source] = fetch(document.source)
            except Exception as why:  # noqa: BLE001 - one unreachable book is not the rest
                notify(f"{document.source}: could not fetch it again ({why})")
                fetched[document.source] = document  # refless, so `refs_from` declines
        refs = refs_from(fetched[document.source], segmented)
        if refs is None:
            notify(f"{folder.name}: the text on disk is not the text the source sends now")
            skipped += 1
            continue
        for segment in segmented.segments:
            if segment.id in refs:
                segment.ref = refs[segment.id]
        segmented.write(path)
        filled += 1
        notify(f"{folder.name}: {len(refs)} verses can now be reached by a recording")
    return filled, skipped
