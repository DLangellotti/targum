"""Word-level difficulty."""

from __future__ import annotations

from collections.abc import Mapping

from ..models import Annotation, Segment, SegmentedDocument, Token, Vocalization
from ..vocalize.base import map_span, pointed_positions, strip_nikkud
from . import register as register_module
from .base import (
    BAND_COUNT,
    BAND_NAMES,
    HIGHLIGHT_LABELS,
    NOT_VOCABULARY,
    UNRATED,
    Bands,
    Lemmatizer,
    Pronouncer,
    highlight_levels,
    method_label,
)
from .dictionary import Entry as DictionaryEntry
from .frequency import FrequencyBands
from .frequency import available as frequency_available
from .lemma import StanzaLemmatizer
from .moves import letters as _letters
from .moves import shared as _shared
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


def _spells(root: str, surface: str) -> bool:
    """Whether a word actually writes the root it is about to be given.

    The radicals of a Hebrew root appear in order inside every form built on it, give or
    take the one a weak root drops. Two of three is the bar, which is the same screen
    `moves.same_word` uses for the same reason — a real derivation keeps its letters and
    a wrong word does not share them.
    """
    have = _letters(root)
    if not have:
        return False
    return _shared(root, surface) >= max(2, len(have) - 1)


class Annotator:
    """Lemmatize, then band. In that order, because the other way round misses most
    of the vocabulary in a morphologically rich language."""

    def __init__(
        self,
        lemmatizer: Lemmatizer | None = None,
        bands: Bands | None = None,
        pronouncer: Pronouncer | None = None,
        dictionary: Mapping[str, DictionaryEntry] | None = None,
        dictionary_name: str = "",
    ) -> None:
        # What a dictionary says about each form, where one has been bought. It answers
        # the facts that belong to the word rather than to the occurrence — the root and
        # the binyan — and it is a mapping rather than a provider because nothing here
        # may reach the network or spend: the entries are built before a text is
        # annotated and handed in. See `annotate/dictionary.py`.
        self.dictionary: Mapping[str, DictionaryEntry] = dictionary or {}
        self.dictionary_name = dictionary_name if self.dictionary else ""
        self.lemmatizer: Lemmatizer = lemmatizer or StanzaLemmatizer()
        self.bands: Bands = bands or FrequencyBands()
        # No default. A machine without phonikud installed produces an annotation with no
        # readings and says so in its name, so the machine that has it redoes the text
        # rather than inheriting a silent gap.
        self.pronouncer = pronouncer

    @property
    def name(self) -> str:
        # The register is in here unconditionally, even for a language it has nothing to
        # say about. The name is the annotator's, not the document's, and an annotator
        # that would now record something it did not record before is a different one —
        # which is exactly what makes a text built before this get built again.
        base = f"{self.lemmatizer.name}+{self.bands.name}+{register_module.NAME}"
        if self.dictionary_name:
            # A text read with a dictionary behind it carries facts the same text read
            # without one does not, so it is a different annotation and says so.
            base = f"{base}+{self.dictionary_name}"
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
        # Beside the band cache and for the same reason: a text has far fewer distinct
        # lemmas than tokens, and both questions are asked of the dictionary form.
        registers: dict[str, str | None] = {}

        for segment_id, tokens in by_segment.items():
            positions = to_source.get(segment_id)
            marked: list[Token] = []
            for token in tokens:
                if token.pos in NOT_VOCABULARY:
                    # A name is rare in any corpus, and rating it would call every name
                    # in a chronicle "extremely hard". It has no difficulty: it is a
                    # token the reader can tap, not a word they have to learn. The same
                    # goes for its register — אחשורוש is not modern Hebrew for having
                    # stayed out of the Tanakh.
                    band = UNRATED
                    in_register = None
                else:
                    if token.lemma not in cache:
                        # A text has far fewer distinct lemmas than tokens.
                        cache[token.lemma] = self.bands.band(token.lemma, segmented.language)
                        registers[token.lemma] = register_module.of(token.lemma, segmented.language)
                    band = cache[token.lemma]
                    in_register = registers[token.lemma]
                update: dict[str, object] = {"band": band, "word_register": in_register}
                update |= self._from_dictionary(token)
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

    def _from_dictionary(self, token: Token) -> dict[str, object]:
        """The root and the binyan a dictionary holds for this word, where it holds them.

        **Only fields that are not keys.** A reader's marked words and every bought gloss
        are filed under the lemma, so moving a lemma orphans both — 23.4% of real marks,
        measured (targum-internal#141). The root and the binyan are on the card and in
        nobody's storage, so they can be corrected on any build and cost nothing. The
        dictionary form the entry also carries is deliberately not applied here: it is
        the same migration, and it is taken once, deliberately, with a map built first.

        Nothing already found is overwritten. Scripture reads its binyan and root off the
        hand tagging, and a model does not get to overrule an editor.

        **And the root has to be spelled in the word it is shown on.** The dictionary
        answers about the form it was given, and the form it was given is whatever the
        tagger called this word — which for a verb is the wrong word 44% of the time.
        Ask it about `עשה` and it correctly says ע־שׂ־ה; put that on a card over `הייתה`
        and the reader is told a lie with a straight face, which is worse than the gap
        it replaces. So the radicals have to appear, in order, in the surface: two of
        three, because a weak root really does drop one — ניתן writes its נ once.
        Measured on the treebanks, this is what takes the roots that reach a card from
        91.7% right to 98%, at a cost of about a twentieth of the coverage.
        """
        entry = self.dictionary.get(token.lemma)
        if entry is None or token.pos != "VERB":
            return {}
        found: dict[str, object] = {}
        if entry.root and not token.root and _spells(entry.root, token.surface):
            found["root"] = entry.root
        if entry.binyan and not token.binyan and (not entry.root or "root" in found):
            # The binyan and the root are one answer about one word. Keeping the binyan
            # after refusing the root would say פיעל over a word the dictionary was
            # never really looking at.
            found["binyan"] = entry.binyan
        return found

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
