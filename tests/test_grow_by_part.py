"""A recording grows a part at a time, and only the new part is read (2026-11-23).

Part 8 of a two-hour podcast sat on the box for over half an hour: every part moves the
document hash, so the vowel points and the words of parts 1 to 7 were made again, and
each part took longer than the one before. The engines are asked about new sentences
only, and what they said about the rest is kept.
"""

from __future__ import annotations

from pathlib import Path

from targum.annotate import Annotator
from targum.models import Segment, SegmentedDocument, Token
from targum.pipeline import Build
from targum.vocalize.base import LETTERS, has_nikkud

FIRST = "שלום לכם"
SECOND = "מה נשמע היום"
THIRD = "אני הולך הביתה"


class Diacritizer:
    name = "fake/1"
    model = "fake-model"

    def __init__(self) -> None:
        self.asked: list[list[str]] = []

    def available(self) -> tuple[bool, str]:
        return True, ""

    def vocalize(self, segments: list[Segment], language: str) -> dict[str, str]:
        self.asked.append([segment.id for segment in segments])
        return {
            segment.id: "".join(
                c + ("ַ" if ord(c) in LETTERS and not has_nikkud(c) else "") for c in segment.text
            )
            for segment in segments
        }


class Lemmatizer:
    name = "fake-lemma/1"

    def __init__(self) -> None:
        self.asked: list[list[str]] = []

    def lemmas(self, segments, language):  # type: ignore[no-untyped-def]
        self.asked.append([segment.id for segment in segments])
        out: dict[str, list[Token]] = {}
        for segment in segments:
            tokens, offset = [], 0
            for word in segment.text.split(" "):
                tokens.append(
                    Token(start=offset, end=offset + len(word), surface=word, lemma=word, band=1)
                )
                offset += len(word) + 1
            out[segment.id] = tokens
        return out


class Bands:
    name = "fake-bands/1"
    method = "curated:test"
    note = "A test list."

    def supports(self, language: str) -> bool:
        return True

    def band(self, lemma: str, language: str) -> int:
        return 2


def heard(*texts: str) -> SegmentedDocument:
    return SegmentedDocument(
        document_hash=str(abs(hash(texts))),
        language="he",
        segmenter="fake",
        segments=[
            Segment(id=f"s{i}", block_id=f"b{i}", block_index=i, index=0, text=text)
            for i, text in enumerate(texts)
        ],
    )


def test_a_new_part_is_pointed_and_read_alone(tmp_path: Path) -> None:
    engine, lemmatizer = Diacritizer(), Lemmatizer()

    def build() -> Build:
        return Build(
            "https://example.com/talk.mp3",
            target_language="en",
            provider_name="null",
            out=tmp_path / "talk-he",
            difficulty=True,
            vocalizer=engine,  # type: ignore[arg-type]
            annotator=Annotator(lemmatizer=lemmatizer, bands=Bands()),  # type: ignore[arg-type]
        )

    for texts in ((FIRST,), (FIRST, SECOND), (FIRST, SECOND, THIRD)):
        doing = build()
        doing._resolved_out = tmp_path / "talk-he"
        segmented = heard(*texts)
        pointed = doing.vocalize(segmented)
        words = doing.annotate(segmented, pointed)
        assert pointed is not None and words is not None
        assert set(pointed.segments) == {f"s{i}" for i in range(len(texts))}
        assert set(words.tokens) == {f"s{i}" for i in range(len(texts))}

    assert engine.asked == [["s0"], ["s1"], ["s2"]], "each part pointed once"
    assert lemmatizer.asked == [["s0"], ["s1"], ["s2"]], "each part read once"


def test_a_sentence_that_changed_is_asked_again(tmp_path: Path) -> None:
    """A correction to a heard sentence moves its text, so it is pointed and read anew."""
    engine, lemmatizer = Diacritizer(), Lemmatizer()

    def build() -> Build:
        return Build(
            "https://example.com/talk.mp3",
            target_language="en",
            provider_name="null",
            out=tmp_path / "talk-he",
            difficulty=True,
            vocalizer=engine,  # type: ignore[arg-type]
            annotator=Annotator(lemmatizer=lemmatizer, bands=Bands()),  # type: ignore[arg-type]
        )

    for texts in ((FIRST, SECOND), (FIRST, THIRD)):
        doing = build()
        doing._resolved_out = tmp_path / "talk-he"
        segmented = heard(*texts)
        doing.annotate(segmented, doing.vocalize(segmented))

    assert engine.asked == [["s0", "s1"], ["s1"]]
    assert lemmatizer.asked == [["s0", "s1"], ["s1"]]
