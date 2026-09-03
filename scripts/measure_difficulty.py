"""How hard each catalogue text is, measured off the text itself.

The library filters on difficulty, and a filter is only worth having if the number
behind it is true. So this counts rather than judges.

**What it counts:** the share of running words whose dictionary form is uncommon in the
language as it is written today — bands 4 to 6 of the reader's own six-band scale, which
is where a learner starts looking things up. Psalms comes out at 24%, Genesis at 12%,
Esther at 10%, and those are in the order any Hebrew reader would put them. (Those were
35, 23 and 17 under Stanza; the whole shelf was re-measured after the DICTA swap on
2026-09-03, and the numbers moved down, not the texts.)

**Scripture is read by the hand tagging or it is not read.** The Open Scriptures
morphology and the modern model are two different readings of the same book, they write
the same annotator name, and the modern one rates the Torah roughly twice as hard as it
is. Both the copy chosen off disk and the annotator built to measure a text afresh now
say which path they are on, and a biblical text that can only be read the modern way is
refused rather than guessed at — targum-internal#172, where the numbers are.

**One ruler for everything.** A Tanakh is banded against the Tanakh when it is read —
that is the honest question for someone reading scripture, and `annotate/biblical.py`
explains why. It is the wrong ruler here: a library that mixes Samuel with a news
article cannot rank them by two different scales and call the result a difficulty. So
this re-bands every text against modern frequency, and the library's register filter is
what says which Hebrew a text is in.

**Two things it does not measure.** Sentence length and syntax, both of which make
Brenner harder than his vocabulary suggests. The number is about words, and the library
says so.

Run when the catalogue changes; write what it prints into `catalogue.py`. Kept out of
the package because it is minutes of Stanza over a hundred thousand words, and no reader
should ever wait for it — but the counting itself moved into `annotate/difficulty.py`,
because the weekly measures an issue before publishing it and does that from the
installed package, which cannot import a script.

    uv run python scripts/measure_difficulty.py [--out targum-out] [--only <id>]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from targum import ingest  # noqa: E402
from targum.annotate import Annotator, biblical, lemma  # noqa: E402
from targum.annotate.difficulty import hard_share  # noqa: E402
from targum.catalogue import CATALOGUE, Entry  # noqa: E402
from targum.models import Annotation, is_biblical, read_artifact  # noqa: E402
from targum.segment import HebrewSegmenter, segment_document  # noqa: E402

#: The part of speech only the hand tagging emits. `annotate/scripture.py` maps the Open
#: Scriptures morphology onto targum's tagset and code `T` becomes `PART`; the modern path
#: is Universal Dependencies, which has no such tag for Hebrew and spells those words
#: ADP, SCONJ, DET or AUX instead. So a token tagged PART is proof the scripture path ran,
#: and its absence across a whole biblical text is proof it did not.
SCRIPTURE_TAG = "PART"


def by_scripture_path(annotation: Annotation) -> bool:
    """Whether this annotation came through the hand tagging rather than the model.

    Asked of the tokens because nothing else in the artifact can answer it. Both paths
    write the same `annotator` name and both band against the Tanakh, so `annotator` and
    `method` are identical on the two copies — verified on the three Genesis copies of
    2026-09-03 (targum-internal#172). The tags are the only place they differ.
    """
    return any(
        token.pos == SCRIPTURE_TAG for tokens in annotation.tokens.values() for token in tokens
    )


def on_disk(root: Path, source: str) -> Annotation | None:
    """An annotation a build already wrote, which is the same lemmas for free.

    The bands in it may have been counted against the Tanakh; only the lemmas are read
    here, and they are re-banded against one ruler above.

    **A text has several homes and the copies are not interchangeable.** The same source
    annotated through the scripture path and through the modern one are two different
    readings of the same book: on Genesis the first tags 1,958 particles and comes out at
    12, the second tags none and comes out at 17. Taking whichever copy the filesystem
    happened to hand back first made the number depend on directory order, and ten sources
    on this shelf had copies that disagreed (targum-internal#172).

    So: walk in sorted order, and for scripture prefer a copy that came through the hand
    tagging. `library/` breaks a remaining tie because that is the corpus the box ships.
    """
    candidates: list[tuple[Path, Annotation]] = []
    for document in sorted(root.glob("*/*/document.json")):
        try:
            if json.loads(document.read_text(encoding="utf-8")).get("source") != source:
                continue
        except (OSError, json.JSONDecodeError):
            continue
        annotation = read_artifact(Annotation, document.parent / "annotation.json")
        if annotation is not None:
            candidates.append((document.parent, annotation))
    if not candidates:
        return None

    def rank(candidate: tuple[Path, Annotation]) -> tuple[int, int]:
        home, annotation = candidate
        # Scripture read as scripture first, then the shipped corpus. Neither test says
        # anything about a text that is not scripture, where every copy is the same
        # reading and sorted order alone is enough to make the choice repeatable.
        wrong_path = is_biblical(source) and not by_scripture_path(annotation)
        return (int(wrong_path), 0 if home.parent.name == "library" else 1)

    return min(candidates, key=rank)[1]


def measured(entry: Entry, root: Path) -> tuple[int | None, str]:
    """This text's difficulty, or None where it cannot be measured honestly.

    Scripture read on the modern path comes out far too hard — the Torah portions moved
    11 to 21, 12 to 26, 15 to 29 — and writing those numbers into the catalogue would
    have silently undone targum#67. So a biblical text is measured through the hand
    tagging or it is not measured: the existing value is a better answer than a wrong new
    one (targum-internal#172).
    """
    scripture = is_biblical(entry.source)
    annotation = on_disk(root, entry.source)
    if annotation is not None and not (scripture and not by_scripture_path(annotation)):
        return hard_share(annotation, entry.language), "on disk"
    # Nothing built yet, or nothing built the right way: fetch it and read it here. No
    # spend — the network, the rule splitter and DICTA — though DICTA on a box without a
    # GPU is about a minute a text.
    document = ingest.load(entry.source)
    segmented = segment_document(document, HebrewSegmenter())
    # Built the way `rebuild` builds it (`cli.py`, the `annotate` closure). A bare
    # `Annotator()` is the modern path, so every biblical entry not already on disk was
    # measured as though it were a news article, deterministically and without a word of
    # complaint.
    annotation = Annotator(
        lemmatizer=lemma.for_source(document.source),
        bands=biblical.for_source(document.source),
    ).annotate(segmented)
    if scripture and not by_scripture_path(annotation):
        # `lemma.for_source` wraps the scripture lookup only where the Open Scriptures
        # tagging is actually on disk, so a box without that data quietly returns the
        # modern reading under the same annotator name. Refusing is the whole point.
        return None, "refused — the hand tagging is not on this box"
    return hard_share(annotation, entry.language), "measured now"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path("targum-out"))
    parser.add_argument("--only", default="", help="One entry id, for a quick check.")
    args = parser.parse_args()

    for entry in CATALOGUE:
        if args.only and entry.id != args.only:
            continue
        try:
            share, how = measured(entry, args.out)
        except Exception as error:  # a catalogue entry that will not fetch is not fatal
            print(f"{entry.id:22} — {error}", flush=True)
            continue
        if share is None:
            # Printed rather than skipped: a run that measures nothing and says nothing
            # reads exactly like a run that measured everything.
            print(f"{entry.id:22} keeping {entry.difficulty:3}  ({how})", flush=True)
            continue
        print(f"{entry.id:22} difficulty={share:3}  ({how}, was {entry.difficulty})", flush=True)


if __name__ == "__main__":
    main()
