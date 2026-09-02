"""The map from the lemmas Stanza gave to the ones DICTA gives (targum-internal#141).

A reader's marked words are stored by lemma, so re-annotating a text under a new
annotator orphans every mark whose lemma moved — measured at 23.4% of real marks. This
builds the table that carries them across.

It is deliberately a by-product of what a rebuild already does rather than a pass of its
own: a reader that has been annotated once has `annotation.json` holding the old lemma
for every token, offsets and all, so the only new work is reading the same segments with
the new annotator. Run it over the shelf and the map for every text on it comes out; run
it over one reader and you get that reader's.

The reading goes through `Annotator` rather than straight to the lemmatizer, and that is
not ceremony. Two fifths of the segments on this shelf carry nikkud, `Annotator.annotate`
is where the points are stripped before a lemmatizer ever sees them, and it is also what
maps the offsets back onto the text as ingested. Handing DICTA the pointed text instead
produced a map that looked fine — the offsets still lined up, so every token still paired
— and was quietly built out of lemmas read off vowels no lemmatizer is trained on.

    python scripts/lemma_map.py targum-out/local --out targum-out/lemma-map.json

Two tables come out, because one is not enough. `lemmas` is old → new where every
occurrence of that old lemma agrees on where it went, and is what migrates a mark that
carries only a lemma. `surfaces` is the word itself → its new lemma, and is what settles
a mark whose old lemma split several ways — הוא went to אני, לו and הוא at once, and only
the surface a reader marked can say which card is theirs. `vocab.js` stores both.

Nothing here may be applied unscreened. 15% of the moves in the first full run pointed at
a **different word**: הבליח → מבצבץ, הכסיף → מכוסה, a place name → סובייטי. Carrying a
mark across one of those is worse than losing it — the reader keeps a word they never
learned, filed under a meaning that is not theirs. So every move is checked for whether
the two spellings still share a run of letters, the way a derivation of one word does,
and the ones that do not are held back rather than emitted as migrations. It is a screen
and not a verdict: הללו → אלה is held by it and is arguably right.
"""

from __future__ import annotations

import argparse
import collections
import gc
import json
import sys
from pathlib import Path

# Sentences per batch. Small on purpose: a box running a build alongside this killed a
# run that asked for two hundred at once.
BATCH = 16


def readers(root: Path) -> list[Path]:
    """Every reader under `root` that has been annotated and still has its text."""
    if (root / "annotation.json").is_file():
        return [root]
    return sorted(
        path
        for path in root.iterdir()
        if (path / "annotation.json").is_file() and (path / "segments.json").is_file()
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("shelf", type=Path, help="a reader, or a directory of them")
    parser.add_argument("--out", type=Path, default=Path("lemma-map.json"))
    args = parser.parse_args()

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
    from targum.annotate import Annotator
    from targum.annotate.dicta import DictaLemmatizer

    # One implementation of the screen, shared with what the build ships to a reader: a
    # script that decided this differently from `annotate/moves.py` would be reporting on
    # a migration nobody performs.
    from targum.annotate.moves import same_word
    from targum.models import Segment, SegmentedDocument

    found = readers(args.shelf)
    if not found:
        print(f"no annotated readers under {args.shelf}", file=sys.stderr)
        return 1

    lemmatizer = DictaLemmatizer()
    annotator = Annotator(lemmatizer=lemmatizer)
    went: dict[str, collections.Counter[str]] = collections.defaultdict(collections.Counter)
    surfaces: dict[str, collections.Counter[str]] = collections.defaultdict(collections.Counter)
    # Which old lemmas a surface was filed under, so the surface table can be cut down to
    # the words that actually need it rather than every word in the library.
    filed: dict[str, set[str]] = collections.defaultdict(set)
    was: set[str] = set()
    tokens = 0

    for reader in found:
        annotation = json.loads((reader / "annotation.json").read_text(encoding="utf-8"))
        if annotation.get("language") != "he":
            continue
        was.add(str(annotation.get("annotator", "")))
        document = json.loads((reader / "segments.json").read_text(encoding="utf-8"))
        texts = {
            segment["id"]: segment.get("text", "")
            for segment in document.get("segments", [])
            if isinstance(segment, dict) and segment.get("id") in annotation["tokens"]
        }
        held = [
            Segment(
                id=sid,
                text=text,
                ref=sid,
                kind="paragraph",
                block_id="b1",
                block_index=1,
                index=n,
            )
            for n, (sid, text) in enumerate(texts.items())
            if text.strip()
        ]
        for start in range(0, len(held), BATCH):
            batch = SegmentedDocument(
                document_hash=str(annotation.get("document_hash", "")),
                language="he",
                segmenter="shelf/1",
                segments=held[start : start + BATCH],
            )
            for sid, read in annotator.annotate(batch).tokens.items():
                # Paired by where the word sits, which is the only thing both annotators
                # agree on: a token either annotator split still spans the same string.
                before = {(t["start"], t["end"]): t for t in annotation["tokens"].get(sid, [])}
                for token in read:
                    old = before.get((token.start, token.end))
                    if old is None:
                        continue
                    tokens += 1
                    went[old["lemma"]][token.lemma] += 1
                    surfaces[token.surface][token.lemma] += 1
                    filed[token.surface].add(old["lemma"])
            gc.collect()
        print(f"  {reader.name}: {tokens} tokens paired so far", flush=True)

    moved = {old: how for old, how in went.items() if set(how) != {old}}
    one_way = {old: how.most_common(1)[0][0] for old, how in moved.items() if len(how) == 1}
    settled = {old: new for old, new in one_way.items() if same_word(old, new)}
    held = {old: new for old, new in one_way.items() if not same_word(old, new)}
    split = {old: dict(how) for old, how in moved.items() if len(how) > 1}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(
            {
                "from": sorted(was),
                "to": lemmatizer.name,
                "lemmas": settled,
                "surfaces": {
                    surface: how.most_common(1)[0][0]
                    for surface, how in surfaces.items()
                    # Only where the lemma alone cannot answer, and not screened by
                    # spelling — see `annotate/moves.py` for why the surface is the
                    # guarantee there rather than the spelling.
                    if filed[surface] & set(split) and "##" not in how.most_common(1)[0][0]
                },
                "split": split,
                # Emitted so they can be read, never applied: these are the moves that
                # land on a different word.
                "held": held,
            },
            ensure_ascii=False,
            indent=1,
        ),
        encoding="utf-8",
    )

    print(f"\nreaders: {len(found)}   tokens paired: {tokens}")
    share = 100.0 * len(moved) / max(len(went), 1)
    print(f"lemmas seen: {len(went)}   moved: {len(moved)} ({share:.1f}%)")
    print(f"  settled on one new lemma: {len(settled)}")
    print(f"  held back as a different word: {len(held)}")
    print(f"  split across several:     {len(split)}")
    print(f"written to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
