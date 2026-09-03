"""The aligner against hand-checked gold links, per language pair.

Off by default: it needs the embedding model and a Stanza model per language. Run it
with TARGUM_BENCHMARK=1 after changing anything in targum.align, and read the printed
report rather than only the pass or fail.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from targum import ingest
from targum.align import Aligner, SentenceTransformerEncoder, as_indices, load_gold, score
from targum.align.embedding import is_downloaded as embeddings_downloaded
from targum.segment import HebrewSegmenter, is_downloaded, segment_document, stanza_code

CORPUS = Path(__file__).parent / "fixtures" / "corpus"

# strict F1, pairwise F1, null recall. The he-en set is paired from the texts and is
# the honest one. The en-he set was corrected from a draft run, so its floor is set as
# a regression guard rather than as a claim about accuracy; read its gold file's note.
FLOORS = {
    "il-declaration.he-en.gold.json": (0.95, 0.95, 1.0),
    "us-declaration.en-he.gold.json": (0.90, 0.93, 1.0),
}


@pytest.fixture(scope="module")
def aligner() -> Aligner:
    return Aligner(encoder=SentenceTransformerEncoder())


@pytest.fixture(scope="module")
def segmenter() -> HebrewSegmenter:
    return HebrewSegmenter(auto_download=False)


@pytest.mark.benchmark
@pytest.mark.parametrize("gold_file", sorted(FLOORS))
def test_scores_against_gold(
    gold_file: str, aligner: Aligner, segmenter: HebrewSegmenter, capsys: pytest.CaptureFixture[str]
) -> None:
    if not os.environ.get("TARGUM_BENCHMARK"):
        pytest.skip("set TARGUM_BENCHMARK=1 to score the aligner")
    if not embeddings_downloaded():
        pytest.skip("embedding model not downloaded")

    gold = load_gold(CORPUS / gold_file)
    for language in gold["pair"].split("-"):
        # Hebrew is split by rule and needs nothing on disk.
        if stanza_code(language) != "he" and not is_downloaded(language):
            pytest.skip(f"{language} model not downloaded")

    source = segment_document(ingest.load(str(CORPUS / gold["source"])), segmenter)
    target = segment_document(ingest.load(str(CORPUS / gold["target"])), segmenter)

    # Gold links are segment positions, so a change in segmentation invalidates them
    # rather than quietly scoring against the wrong sentences.
    assert len(source.segments) == gold["expected_counts"]["source"], "source segmentation moved"
    assert len(target.segments) == gold["expected_counts"]["target"], "target segmentation moved"

    alignment = aligner.align(source, target, "gold run")
    result = score(
        as_indices(
            alignment.links,
            [segment.id for segment in source.segments],
            [segment.id for segment in target.segments],
        ),
        gold["links"],
        gold["pair"],
    )
    with capsys.disabled():
        print("\n  " + result.report())

    strict, pairwise, nulls = FLOORS[gold_file]
    assert result.strict_f1 >= strict, result.report()
    assert result.pair_f1 >= pairwise, result.report()
    assert result.null_recall >= nulls, result.report()
