"""Word-level difficulty."""

from __future__ import annotations

from ..models import Annotation, Segment, SegmentedDocument, Token, Vocalization
from ..vocalize.base import map_span, pointed_positions, strip_nikkud
from .base import (
    BAND_COUNT,
    BAND_NAMES,
    HIGHLIGHT_LABELS,
    Bands,
    Lemmatizer,
    Pronouncer,
    highlight_levels,
    method_label,
)
from .frequency import FrequencyBands
from .frequency import available as frequency_available
from .lemma import StanzaLemmatizer
from .pronounce import PhonikudPronouncer
from .pronounce import supports as pronounceable

__all__ = [
    "BAND_COUNT",
    "BAND_NAMES",
    "HIGHLIGHT_LABELS",
    "Annotator",
    "Bands",
    "FrequencyBands",
    "Lemmatizer",
    "PhonikudPronouncer",
    "Pronouncer",
    "StanzaLemmatizer",
    "annotate",
    "frequency_available",
    "highlight_levels",
    "method_label",
    "pronounceable",
]


class Annotator:
    """Lemmatize, then band. In that order, because the other way round misses most
    of the vocabulary in a morphologically rich language."""

    def __init__(
        self,
        lemmatizer: Lemmatizer | None = None,
        bands: Bands | None = None,
        pronouncer: Pronouncer | None = None,
    ) -> None:
        self.lemmatizer: Lemmatizer = lemmatizer or StanzaLemmatizer()
        self.bands: Bands = bands or FrequencyBands()
        # No default. A machine without phonikud installed produces an annotation with no
        # readings and says so in its name, so the machine that has it redoes the text
        # rather than inheriting a silent gap.
        self.pronouncer = pronouncer

    @property
    def name(self) -> str:
        base = f"{self.lemmatizer.name}+{self.bands.name}"
        return base if self.pronouncer is None else f"{base}+{self.pronouncer.name}"

    def annotate(
        self, segmented: SegmentedDocument, vocalization: Vocalization | None = None
    ) -> Annotation:
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

        banded = self._pronounce(banded, segmented, vocalization)

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

    def _pronounce(
        self,
        banded: dict[str, list[Token]],
        segmented: SegmentedDocument,
        vocalization: Vocalization | None,
    ) -> dict[str, list[Token]]:
        """A reading for every token whose word has vowels above it.

        Runs on the pointed text rather than the bare text, which is the opposite of
        everything above it: the lemmatizer must not see nikkud and the phonemizer cannot
        work without it. The two coordinate systems are bridged the way the builder
        bridges them — through the bare form, which is the one thing both agree on.
        """
        if self.pronouncer is None or vocalization is None:
            return banded
        if not pronounceable(segmented.language):
            return banded

        source_text = {segment.id: segment.text for segment in segmented.segments}
        # The pointed word behind each token, in the order the tokens came in, so the
        # readings can be put back without matching on anything.
        surfaces: dict[str, list[str]] = {}
        distinct: set[str] = set()
        for segment_id, tokens in banded.items():
            pointed = vocalization.segments.get(segment_id)
            source = source_text.get(segment_id)
            # A segment with no marks at all never reaches the vocalization, and there is
            # nothing here to read.
            if pointed is None or source is None:
                continue
            # Token offsets are measured against the segment as ingested; the pointed
            # form may carry marks that segment never had. Both share a bare skeleton —
            # `splice` refuses anything else — so that is the way across.
            _, to_bare = strip_nikkud(source)
            to_pointed = pointed_positions(pointed)
            found: list[str] = []
            for token in tokens:
                bare_start, bare_end = map_span(token.start, token.end, to_bare)
                if bare_end >= len(to_pointed):
                    found.append("")
                    continue
                start, end = map_span(bare_start, bare_end, to_pointed)
                word = pointed[start:end]
                found.append(word)
                distinct.add(word)
            surfaces[segment_id] = found

        if not distinct:
            return banded
        # One reading per distinct form rather than one per token. Measured, phonikud
        # returns the same string for a word alone as for the same word inside its
        # sentence — the vowels have already settled everything the context could — so
        # this is a saving rather than a compromise.
        readings = self.pronouncer.say(sorted(distinct))
        if not readings:
            return banded

        said: dict[str, list[Token]] = {}
        for segment_id, tokens in banded.items():
            found = surfaces.get(segment_id, [])
            rows: list[Token] = []
            for index, token in enumerate(tokens):
                word = found[index] if index < len(found) else ""
                reading = readings.get(word)
                rows.append(token if reading is None else token.model_copy(update={"ipa": reading}))
            said[segment_id] = rows
        return said


def annotate(
    segmented: SegmentedDocument,
    annotator: Annotator | None = None,
    vocalization: Vocalization | None = None,
) -> Annotation:
    return (annotator or Annotator()).annotate(segmented, vocalization)
