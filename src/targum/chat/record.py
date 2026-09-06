"""The record forming: a turn's Hebrew, read the way a text is read, as it lands.

A conversation in Hebrew is drawn on the page as the text it will become on the shelf
(design.md §12, 2026-09-06): every line the model writes is annotated the moment it is
whole — the same lemmatizer a build uses, the same bands — so the page can give each
word its state on the reader's ledger while they are still reading it, and count what
they have not met. Meanings come from the glossary cache and are never bought here: a
word the cache does not hold is shown bare, and the reader's own press looks it up.

Measured before it was built (`scripts/measure_line_annotation.py`): on a laptop the
model loads in about nine seconds and then reads a line in about sixty milliseconds, a
five-line turn in a fifth of a second. The load is paid once per process, warmed when
the chat's workers start, so no reader waits for it.
"""

from __future__ import annotations

import threading
import traceback
from collections.abc import Callable
from typing import Any

from ..annotate.base import NOT_VOCABULARY, Bands, Lemmatizer
from ..annotate.frequency import FrequencyBands
from ..models import Segment
from ..vocalize.base import map_span, pointed_positions, strip_nikkud

#: Which languages the record reads. One: the record is Hebrew on both sides.
LANGUAGE = "he"


def _segments(lines: list[str]) -> list[Segment]:
    """One segment per line, bare of its points: the model is trained unpointed, and
    `Annotator.annotate` says what pointed text does to it."""
    out = []
    for index, line in enumerate(lines):
        plain, _ = strip_nikkud(line)
        out.append(Segment(id=f"l{index}", block_id="turn", block_index=0, index=index, text=plain))
    return out


class Recorder:
    """Reads a turn's lines and says what each word is."""

    def __init__(
        self,
        lemmatizer: Lemmatizer | None = None,
        glosses: Callable[[str, str, str], str] | None = None,
        bands: Bands | None = None,
    ) -> None:
        self._lemmatizer = lemmatizer
        self._glosses = glosses
        self.bands: Bands = bands or FrequencyBands()
        # One model, one line at a time. The weights are shared across instances
        # (`dicta._LOADED`); what is serialised here is the call.
        self.lock = threading.Lock()

    def lemmatizer(self) -> Lemmatizer:
        if self._lemmatizer is None:
            from ..annotate import lemma

            # The modern reader: the record is conversation, never scripture, so the
            # scripture lookup is never wrapped around it.
            self._lemmatizer = lemma.for_source("chat:record")
        return self._lemmatizer

    def warm(self) -> None:
        """Load the model now, so the first turn does not wait nine seconds for it.
        Any failure is the operator's to read; the record then annotates late, or not."""
        try:
            with self.lock:
                self.lemmatizer().lemmas(_segments(["שלום"]), LANGUAGE)
        except Exception:  # noqa: BLE001 - a warm-up that fails must not take the server
            traceback.print_exc()

    def gloss(self, lemma: str, language: str = LANGUAGE, target: str = "en") -> str:
        """The meaning already held for a word, or nothing. Never spends."""
        if self._glosses is not None:
            return self._glosses(lemma, language, target)
        from ..annotate.gloss import GLOSS_MODEL, AnthropicGlosses, cached_gloss

        held = cached_gloss(lemma, language, target, AnthropicGlosses(GLOSS_MODEL).name)
        return held.gloss if held else ""

    def annotate(
        self, lines: list[str], language: str = LANGUAGE, target: str = "en"
    ) -> list[list[dict[str, Any]]]:
        """Each line's words: where each sits in the pointed line, its dictionary form,
        its part of speech, its band, and the meaning held for it, if one is."""
        if not lines:
            return []
        segments = _segments(lines)
        with self.lock:
            read = self.lemmatizer().lemmas(segments, language)
        rated = self.bands.supports(language)
        meanings: dict[str, str] = {}
        bands: dict[str, int] = {}
        out: list[list[dict[str, Any]]] = []
        for index, line in enumerate(lines):
            positions = pointed_positions(line)
            words: list[dict[str, Any]] = []
            for token in read.get(f"l{index}", []):
                start, end = map_span(token.start, token.end, positions)
                vocabulary = token.pos not in NOT_VOCABULARY
                if vocabulary and token.lemma not in bands:
                    bands[token.lemma] = self.bands.band(token.lemma, language) if rated else 0
                if vocabulary and token.lemma not in meanings:
                    meanings[token.lemma] = self.gloss(token.lemma, language, target)
                words.append(
                    {
                        "start": start,
                        "end": end,
                        "surface": line[start:end],
                        "lemma": token.lemma,
                        "pos": token.pos or "",
                        "band": bands.get(token.lemma, 0) if vocabulary else 0,
                        "meaning": meanings.get(token.lemma, "") if vocabulary else "",
                    }
                )
            out.append(words)
        return out


def outside_share(lines: list[list[dict[str, Any]]], allowed: set[str]) -> float:
    """What share of a turn's vocabulary lies outside the words the model was given.

    The number the grading claim rests on (`scripts/eval_grading.py`, targum-internal
    #213), measured on every turn and kept with it. Names and numbers are not vocabulary
    and are not counted either way.
    """
    total = 0
    outside = 0
    for words in lines:
        for word in words:
            if word.get("pos") in NOT_VOCABULARY:
                continue
            total += 1
            if word.get("lemma") not in allowed:
                outside += 1
    return outside / total if total else 0.0
