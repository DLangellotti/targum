"""Word-level difficulty."""

from __future__ import annotations

from ..models import Annotation, SegmentedDocument, Token
from .base import (
    BAND_COUNT,
    BAND_NAMES,
    HIGHLIGHT_LABELS,
    Bands,
    Lemmatizer,
    highlight_levels,
    method_label,
)
from .frequency import FrequencyBands
from .frequency import available as frequency_available
from .lemma import StanzaLemmatizer

__all__ = [
    "BAND_COUNT",
    "BAND_NAMES",
    "HIGHLIGHT_LABELS",
    "Annotator",
    "Bands",
    "FrequencyBands",
    "Lemmatizer",
    "StanzaLemmatizer",
    "annotate",
    "frequency_available",
    "highlight_levels",
    "method_label",
]


class Annotator:
    """Lemmatize, then band. In that order, because the other way round misses most
    of the vocabulary in a morphologically rich language."""

    def __init__(self, lemmatizer: Lemmatizer | None = None, bands: Bands | None = None) -> None:
        self.lemmatizer: Lemmatizer = lemmatizer or StanzaLemmatizer()
        self.bands: Bands = bands or FrequencyBands()

    @property
    def name(self) -> str:
        return f"{self.lemmatizer.name}+{self.bands.name}"

    def annotate(self, segmented: SegmentedDocument) -> Annotation:
        by_segment = self.lemmatizer.lemmas(list(segmented.segments), segmented.language)
        banded: dict[str, list[Token]] = {}
        cache: dict[str, int] = {}

        for segment_id, tokens in by_segment.items():
            marked: list[Token] = []
            for token in tokens:
                if token.lemma not in cache:
                    # A text has far fewer distinct lemmas than tokens.
                    cache[token.lemma] = self.bands.band(token.lemma, segmented.language)
                marked.append(token.model_copy(update={"band": cache[token.lemma]}))
            if marked:
                banded[segment_id] = marked

        rated = self.bands.supports(segmented.language)
        return Annotation(
            document_hash=segmented.document_hash,
            language=segmented.language,
            annotator=self.name,
            method=self.bands.method if rated else "none",
            method_note=(
                self.bands.note
                if rated
                else f"No word frequency data exists for {segmented.language}, "
                "so words are not rated here."
            ),
            tokens=banded,
        )


def annotate(segmented: SegmentedDocument, annotator: Annotator | None = None) -> Annotation:
    return (annotator or Annotator()).annotate(segmented)
