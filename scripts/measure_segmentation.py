"""What the rule-based Hebrew splitter changes, measured on the shelf as it stands.

targum-internal#146 replaced Stanza's Hebrew tokenizer — trained on a NonCommercial
treebank — with the rules in `segment/hebrew.py`. Two of that issue's acceptance items
are numbers rather than code, and this is where they come from:

- **How many boundaries move**, on which texts, and a sample of the disagreements to read.
- **What a moved boundary would cost.** A segment is the unit the translation cache is
  keyed on, so every stored segment whose text the new splitter does not reproduce is a
  translation that would be bought again *if* the text were re-segmented. It is not:
  `pipeline.segment` reuses `segments.json` by document hash, so the number printed here
  is what a forced rebuild would spend, and the reason nothing forces one.

Nothing here runs Stanza. The comparison is against the segmentation each reader already
has on disk, which is the one its translations were bought under — the exact thing the
cost is about. Reads only; writes nothing.

    .venv/bin/python scripts/measure_segmentation.py [--out targum-out/local] [--sample 12]
"""

from __future__ import annotations

import argparse
import random
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from targum.models import Document, SegmentedDocument, Translation, read_artifact  # noqa: E402
from targum.segment import HebrewSegmenter, segment_document  # noqa: E402
from targum.segment.base import UNSPLIT  # noqa: E402
from targum.translate.anthropic_provider import (  # noqa: E402
    CHARS_PER_TOKEN,
    AnthropicProvider,
    batches,
)


def ends(block: str, pieces: list[str]) -> set[int]:
    """Where each sentence ends in its block, as offsets; the thing two splitters can
    agree or disagree about."""
    out: set[int] = set()
    at = 0
    for piece in pieces:
        at = block.index(piece, at) + len(piece)
        out.add(at)
    return out


def around(text: str, at: int) -> tuple[str, str]:
    return text[max(0, at - 40) : at], text[at : at + 30]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path("targum-out/local"))
    parser.add_argument("--sample", type=int, default=12)
    parser.add_argument("--seed", type=int, default=146)
    args = parser.parse_args()

    segmenter = HebrewSegmenter()
    provider = AnthropicProvider()
    rows: list[tuple[str, int, int, int, int, int, int]] = []
    added: list[tuple[str, str, str]] = []
    removed: list[tuple[str, str, str]] = []
    tails: Counter[str] = Counter()
    totals = Counter()

    for reader in sorted(args.out.iterdir()):
        document = read_artifact(Document, reader / "document.json")
        stored = read_artifact(SegmentedDocument, reader / "segments.json")
        if document is None or stored is None or stored.language != "he":
            continue
        if stored.document_hash != document.content_hash:
            print(f"{reader.name}: segments.json is stale against document.json, skipped")
            continue
        fresh = segment_document(document, segmenter)

        translated: set[str] = set()
        for path in (reader / "translations").glob("*.json"):
            translation = read_artifact(Translation, path)
            if translation is not None:
                translated |= set(translation.segments)

        old_by_block: dict[str, list[str]] = {}
        for segment in stored.segments:
            old_by_block.setdefault(segment.block_id, []).append(segment.text)
        new_by_block: dict[str, list[str]] = {}
        for segment in fresh.segments:
            new_by_block.setdefault(segment.block_id, []).append(segment.text)

        moved = 0
        boundaries = 0
        for block in document.blocks:
            if block.kind in UNSPLIT:
                continue
            old = ends(block.text, old_by_block.get(block.id, []))
            new = ends(block.text, new_by_block.get(block.id, []))
            boundaries += len(old)
            moved += len(old ^ new)
            for at in sorted(new - old):
                added.append((reader.name, *around(block.text, at)))
                tails["+" + block.text[max(0, at - 2) : at]] += 1
            for at in sorted(old - new):
                removed.append((reader.name, *around(block.text, at)))
                tails["-" + block.text[max(0, at - 2) : at]] += 1

        new_texts = {segment.text for segment in fresh.segments}
        changed = [segment for segment in stored.segments if segment.text not in new_texts]
        bought = [segment for segment in changed if segment.id in translated]
        words = sum(len(segment.text.split()) for segment in bought)
        body = "\n".join(segment.text for segment in bought)
        cost = provider.estimate_from_counts(
            len(body) / CHARS_PER_TOKEN["he"], len(list(batches(bought, provider.batch_size)))
        )
        rows.append(
            (reader.name, boundaries, moved, len(stored.segments), len(changed), len(bought), words)
        )
        totals.update(
            boundaries=boundaries,
            moved=moved,
            segments=len(stored.segments),
            changed=len(changed),
            bought=len(bought),
            words=words,
        )
        totals["usd"] += cost

    head = ("reader", "bounds", "moved", "segs", "changed", "paid", "words")
    print(f"{head[0]:28} " + " ".join(f"{h:>7}" for h in head[1:]))
    for name, boundaries, moved, segments, changed, bought, words in rows:
        cells = (boundaries, moved, segments, changed, bought, words)
        print(f"{name:28} " + " ".join(f"{cell:7}" for cell in cells))
    print()
    print(f"readers: {len(rows)}")
    print(
        f"boundaries: {totals['boundaries']}   moved: {totals['moved']} "
        f"({100 * totals['moved'] / max(1, totals['boundaries']):.1f}%)"
    )
    print(
        f"stored segments: {totals['segments']}   whose text changes: {totals['changed']} "
        f"({100 * totals['changed'] / max(1, totals['segments']):.1f}%)"
    )
    print(
        f"of those already translated: {totals['bought']} segments, {totals['words']} words — "
        f"about ${totals['usd']:.2f} to buy again on {provider.model}, if anything forced it"
    )
    print()
    print("what the moved boundaries end on (+ new boundary, - old one gone):")
    for tail, count in tails.most_common(16):
        print(f"  {count:6}  {tail!r}")

    random.seed(args.seed)
    for label, found in (("new boundaries", added), ("boundaries gone", removed)):
        print()
        print(f"{label}: {len(found)}, a sample of {min(args.sample, len(found))}")
        for name, before, after in random.sample(found, min(args.sample, len(found))):
            print(f"  [{name}] …{before} | {after}…")


if __name__ == "__main__":
    main()
