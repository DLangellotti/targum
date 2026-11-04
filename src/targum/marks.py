"""An edition's marks given to texts already built (design.md §12, "A text keeps the
shape its edition gives it", 2026-11-04).

Since `sefaria/6` a Sefaria text keeps what its edition sets apart beside its words: the
citations Torat Emet prints small, a commentary's bold catchwords, a translator's
footnotes. A text built before then has none of them, and building it again would read
them — but a build is the whole pipeline, and a pipeline that finds anything different
buys. So this reads each Sefaria text again from Sefaria, and only ever copies marks
across: a text whose words come back different by a single character is left exactly as
it was and said so. Nothing is bought, by construction.

What it writes: the marks and notes into `document.json`, with the ingester's new name so
a later build does not read it a third time, and into each published translation's
`aligned.*.json`, whose text is checked the same way. The readers are rendered again
afterwards, from the artifacts, which spends nothing either.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from .ids import slug
from .models import Alignment, Document, Translation, read_artifact

#: The scheme this reads. Every other text is passed over without a fetch.
SEFARIA = "sefaria:"


@dataclass
class Marked:
    """What one run did, folder by folder."""

    written: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    refused: list[tuple[str, str]] = field(default_factory=list)


def _identifier(translation: Translation) -> str | None:
    """The Sefaria text a published rendering was read from: its name is the reference
    (`commentary_ref` names a commentary so; an English edition is titled by its ref)."""
    language = translation.target_language.split("-")[0].lower()
    if translation.kind != "aligned":
        return None
    if language == "he":
        return f"{SEFARIA}{translation.name}"
    if language == "en":
        return f"{SEFARIA}en:{translation.name}"
    return None


def _same_words(held: Document, fresh: Document) -> bool:
    if held.recompute_hash() != fresh.recompute_hash():
        return False
    return [(b.id, b.text) for b in held.blocks] == [(b.id, b.text) for b in fresh.blocks]


def give(folder: Path, load: Callable[[str], Document]) -> tuple[str, str]:
    """Give one built text its edition's marks. Returns what happened and why.

    "written", "unchanged" (nothing to add, or not a Sefaria text) or "refused", with the
    reason. `load` reads a source the way `ingest.load` does; it is the one network call.
    """
    from .align import to_translation
    from .segment import HebrewSegmenter, segment_document

    path = folder / "document.json"
    held = read_artifact(Document, path)
    if held is None or not held.source.startswith(SEFARIA):
        return "unchanged", "not a Sefaria text"
    try:
        fresh = load(held.source)
    except Exception as error:  # noqa: BLE001 - one text, not the whole run
        return "refused", f"could not be read again ({error})"
    if not _same_words(held, fresh):
        return "refused", "its words came back different, so nothing was touched"
    wrote = False
    if any(b.marks or b.notes for b in fresh.blocks) or held.ingester != fresh.ingester:
        by_id = {block.id: block for block in fresh.blocks}
        for block in held.blocks:
            found = by_id[block.id]
            block.marks = found.marks
            block.notes = found.notes
        held.ingester = fresh.ingester
        held.write(path)
        wrote = True

    reasons: list[str] = []
    for aligned in sorted((folder / "translations").glob("aligned.*.json")):
        translation = read_artifact(Translation, aligned)
        identifier = _identifier(translation) if translation is not None else None
        if translation is None or identifier is None:
            continue
        alignment = read_artifact(
            Alignment,
            folder / "alignments" / f"{slug(translation.name)}.{translation.target_language}.json",
        )
        if alignment is None:
            continue
        try:
            source = load(identifier)
        except Exception as error:  # noqa: BLE001 - one rendering, not the whole run
            reasons.append(f"{translation.name}: could not be read again ({error})")
            continue
        target = segment_document(source, HebrewSegmenter())
        projected = to_translation(alignment, target, document=source)
        if projected.segments != translation.segments:
            reasons.append(f"{translation.name}: its text came back different, left alone")
            continue
        if projected.marks == translation.marks and projected.notes == translation.notes:
            continue
        translation.marks = projected.marks
        translation.notes = projected.notes
        translation.write(aligned)
        wrote = True
    if reasons and not wrote:
        return "refused", "; ".join(reasons)
    return ("written" if wrote else "unchanged"), "; ".join(reasons)


def give_all(folders: list[Path], load: Callable[[str], Document]) -> Marked:
    done = Marked()
    for folder in folders:
        what, why = give(folder, load)
        # By home and name, which is how `rebuild --only` names a folder unambiguously.
        name = f"{folder.parent.name}/{folder.name}"
        if what == "written":
            done.written.append(name)
        elif what == "refused":
            done.refused.append((name, why))
        else:
            done.unchanged.append(name)
    return done
