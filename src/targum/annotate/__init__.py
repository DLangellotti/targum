"""Word-level difficulty."""

from __future__ import annotations

from ..models import Annotation, Segment, SegmentedDocument, Token
from ..vocalize.base import map_span, pointed_positions, strip_nikkud
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
        # Lemmatize the bare text, never the pointed text. Stanza's Hebrew models are
        # trained unpointed, and fed nikkud they return lemmas that are not words:
        # נַּפְשִׁי comes back as נַּ'ְשִׁ, שׁוּבֵךְ as הוּבֵך. Every band, gloss and saved-word
        # grouping downstream is keyed to the lemma, so one pointed source poisons all
        # three. Offsets are mapped back onto the segment as ingested afterwards, which
        # keeps this invisible to every later stage.
        plain: list[Segment] = []
        to_source: dict[str, list[int]] = {}
        for segment in segmented.segments:
            text, _ = strip_nikkud(segment.text)
            if text != segment.text:
                to_source[segment.id] = pointed_positions(segment.text)
                segment = segment.model_copy(update={"text": text})
            plain.append(segment)

        by_segment = self.lemmatizer.lemmas(plain, segmented.language)
        source_text = {segment.id: segment.text for segment in segmented.segments}
        banded: dict[str, list[Token]] = {}
        cache: dict[str, int] = {}

        for segment_id, tokens in by_segment.items():
            positions = to_source.get(segment_id)
            marked: list[Token] = []
            for token in tokens:
                if token.lemma not in cache:
                    # A text has far fewer distinct lemmas than tokens.
                    cache[token.lemma] = self.bands.band(token.lemma, segmented.language)
                update: dict[str, object] = {"band": cache[token.lemma]}
                if positions is not None:
                    # Back into the segment's own coordinates, so a token still spans
                    # exactly its own text and carries the marks belonging to it.
                    start, end = map_span(token.start, token.end, positions)
                    update |= {
                        "start": start,
                        "end": end,
                        "surface": source_text[segment_id][start:end],
                    }
                marked.append(token.model_copy(update=update))
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
