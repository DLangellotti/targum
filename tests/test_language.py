"""A block can name its own language, and the stages honour it.

Daniel and Ezra turn into Aramaic mid-book and back, and a document with one language
sent their Aramaic through the Hebrew pipeline: Stanza tagged half the tokens as names
and read יָת, the object marker, as the Hebrew verb נתן (targum-internal#66). What is
defended here is the rule that stops that — a block in another language than its
document's is carried through the segmenter, left unread by the annotator, and counted
by nothing — and that the field which carries it costs no existing artifact its
validity.
"""

from __future__ import annotations

from targum.annotate import Annotator
from targum.annotate.base import LANGUAGES
from targum.annotate.difficulty import hard_share
from targum.models import Block, BlockKind, Document, Segment, SegmentedDocument, Token
from targum.segment import segment_document

HEBREW = "ויאמר המלך לחכמים"
ARAMAIC = "מלכא לעלמין חיי אמר חלמא לעבדך"


# -- the field ---------------------------------------------------------------


def test_a_block_with_no_language_of_its_own_still_reads() -> None:
    """Every artifact on the shelf was written before a block could say its language.

    The field defaults to None, meaning the document's, so a `document.json` from before
    it existed parses exactly as it did — which is what keeps this from being a schema
    bump, and a schema bump from re-buying every translation in the library.
    """
    before = {"id": "b0001", "kind": "verse", "text": HEBREW, "ref": "Daniel 1:1"}
    block = Block.model_validate(before)
    assert block.language is None
    assert Block.model_validate(block.model_dump(mode="json")).language is None


def test_a_block_that_names_its_language_keeps_it_through_the_round_trip() -> None:
    block = Block(id="b0002", kind=BlockKind.verse, text=ARAMAIC, ref="Daniel 2:4", language="arc")
    written = block.model_dump(mode="json")
    assert written["language"] == "arc"
    assert Block.model_validate(written).language == "arc"


def test_the_language_is_not_part_of_the_body() -> None:
    """Marking a text's Aramaic must cost a re-ingest and not a re-translation."""
    plain = Document(source="x", language="he", blocks=[Block(id="b0001", text=ARAMAIC)])
    marked = Document(
        source="x", language="he", blocks=[Block(id="b0001", text=ARAMAIC, language="arc")]
    )
    assert plain.recompute_hash() == marked.recompute_hash()


# -- the segmenter -----------------------------------------------------------


class _AlwaysSplits:
    """Cuts every text it is given in half, and records what it was given."""

    name = "always-splits/1"

    def __init__(self) -> None:
        self.asked: list[str] = []

    def split(self, texts: list[str], language: str) -> list[list[str]]:
        self.asked.extend(texts)
        return [[text[: len(text) // 2], text[len(text) // 2 :]] for text in texts]


def test_a_segment_carries_its_block_s_language() -> None:
    document = Document(
        source="x",
        language="he",
        blocks=[
            Block(id="b0000", kind=BlockKind.verse, text=HEBREW, ref="Daniel 2:3"),
            Block(id="b0001", kind=BlockKind.verse, text=ARAMAIC, ref="Daniel 2:4", language="arc"),
        ],
    )
    segmented = segment_document(document, _AlwaysSplits())
    assert [s.language for s in segmented.segments] == [None, "arc"]
    assert [s.language_in("he") for s in segmented.segments] == ["he", "arc"]


def test_a_paragraph_in_another_language_is_never_handed_to_the_segmenter() -> None:
    """The segmenter is built for one language and refuses `arc` outright.

    Today every Aramaic block is a verse, which is kept whole anyway; this is the rule
    for the paragraph of Aramaic that has not arrived yet, so that when it does it is not
    cut by a Hebrew sentence model that never saw the language.
    """
    document = Document(
        source="x",
        language="he",
        blocks=[
            Block(id="b0000", kind=BlockKind.paragraph, text=HEBREW),
            Block(id="b0001", kind=BlockKind.paragraph, text=ARAMAIC, language="arc"),
        ],
    )
    segmenter = _AlwaysSplits()
    segmented = segment_document(document, segmenter)
    assert segmenter.asked == [HEBREW], "only the Hebrew reached the segmenter"
    kept = [s for s in segmented.segments if s.block_id == "b0001"]
    assert [s.text for s in kept] == [ARAMAIC], "the Aramaic was kept whole"


# -- the annotator -----------------------------------------------------------


class _Lemmatizer:
    """Answers one token per word, and records which segments it was asked about."""

    name = "recording-lemma/1"

    def __init__(self) -> None:
        self.asked: list[str] = []

    def lemmas(self, segments: list[Segment], language: str) -> dict[str, list[Token]]:
        out: dict[str, list[Token]] = {}
        for segment in segments:
            self.asked.append(segment.id)
            tokens: list[Token] = []
            at = 0
            for word in segment.text.split(" "):
                tokens.append(Token(start=at, end=at + len(word), surface=word, lemma=word, band=0))
                at += len(word) + 1
            out[segment.id] = tokens
        return out


class _Bands:
    name = "fake-bands/1"
    method = "curated:test"
    note = "A test list."

    def supports(self, language: str) -> bool:
        return True

    def band(self, lemma: str, language: str) -> int:
        return 6


def _segmented(*rows: tuple[str, str | None]) -> SegmentedDocument:
    return SegmentedDocument(
        document_hash="h",
        language="he",
        segmenter="fake/1",
        segments=[
            Segment(
                id=f"{n:04d}.000-aaaaaa",
                block_id=f"b{n:04d}",
                block_index=n,
                index=0,
                kind=BlockKind.verse,
                text=text,
                language=language,
            )
            for n, (text, language) in enumerate(rows)
        ],
    )


def test_a_block_in_another_language_is_left_without_tokens() -> None:
    """The whole of the fix. No token is a word the reader can still read and cannot
    tap; a Hebrew token on an Aramaic word is a card that lies."""
    lemmatizer = _Lemmatizer()
    segmented = _segmented((HEBREW, None), (ARAMAIC, "arc"))
    annotation = Annotator(lemmatizer=lemmatizer, bands=_Bands()).annotate(segmented)

    hebrew, aramaic = (segment.id for segment in segmented.segments)
    assert hebrew in annotation.tokens
    assert aramaic not in annotation.tokens, "the Aramaic was glossed as Hebrew"
    assert lemmatizer.asked == [hebrew], "and the lemmatizer was never asked about it"


def test_a_block_in_the_document_s_own_language_reads_as_before() -> None:
    """Saying the language out loud must change nothing for the block that says it."""
    lemmatizer = _Lemmatizer()
    segmented = _segmented((HEBREW, "he"), (HEBREW, None))
    annotation = Annotator(lemmatizer=lemmatizer, bands=_Bands()).annotate(segmented)
    assert len(annotation.tokens) == 2


def test_the_rule_is_in_the_annotator_s_name() -> None:
    """Every Daniel and Ezra on the shelf was annotated before a block could say it was
    Aramaic, and carries a Hebrew reading of it. The name is what decides whether an
    annotation is reused, so the rule has to be in it — and re-reading is free."""
    assert LANGUAGES in Annotator(lemmatizer=_Lemmatizer(), bands=_Bands()).name


# -- difficulty --------------------------------------------------------------


def test_an_unread_block_counts_for_nothing() -> None:
    """Daniel is measured on its Hebrew. Six chapters of Aramaic read as Hebrew would
    band as the rarest words in the language and move the book a shelf up the library."""
    annotator = Annotator(lemmatizer=_Lemmatizer(), bands=_Bands())
    with_aramaic = annotator.annotate(_segmented((HEBREW, None), (ARAMAIC, "arc")))
    without = annotator.annotate(_segmented((HEBREW, None)))
    assert hard_share(with_aramaic, "he") == hard_share(without, "he")
