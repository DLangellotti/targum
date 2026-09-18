"""The record forming: a turn's Hebrew, read the way a text is read, as it lands.

A conversation in Hebrew is drawn on the page as the text it will become on the shelf
(design.md §12, 2026-09-06): every line the model writes is annotated the moment it is
whole — the same lemmatizer a build uses, the same bands — so the page can give each
word its state on the reader's ledger while they are still reading it, and count what
they have not met. Meanings come from the glossary cache and are never bought here: a
word the cache does not hold is shown bare, and the reader's own press looks it up.

The same holds in Italian since 2026-09-15 (targum-internal#280), read by the model
rather than by a local tagger, because nothing permissively licensed reads Italian
(`annotate/model_lemma`). That reading costs a little, and it is part of the turn: what it
spent is handed back to be settled on the turn's own job, never kept on a counter of its
own.

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

from ..annotate.base import NOT_VOCABULARY, Bands, Lemmatizer, in_script
from ..annotate.frequency import FrequencyBands
from ..models import Segment
from ..usage import Usage
from ..vocalize.base import js_span, map_span, pointed_positions, strip_nikkud

#: The record's first language, and the one its local model is warmed for.
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
        self,
        lines: list[str],
        language: str = LANGUAGE,
        target: str = "en",
        spent: Usage | None = None,
    ) -> list[list[dict[str, Any]]]:
        """Each line's words: where each sits in the pointed line, its dictionary form,
        its part of speech, its band, and the meaning held for it, if one is.

        `spent` is the turn's own usage, and what reading the words cost is added to it:
        nothing for Hebrew, which is read here, and the model's reading for a language
        only the model reads."""
        if not lines:
            return []
        segments = _segments(lines)
        from ..annotate import model_lemma

        if self._lemmatizer is None and model_lemma.reads(language):
            # Bought: the turn this is part of was claimed before its first token, and the
            # reading is settled with it. A fresh reader a turn, so what it spent is this
            # turn's and no other's; no lock, since nothing local is loaded.
            reader = model_lemma.ModelLemmatizer(buy=True)
            try:
                read = reader.lemmas(segments, language)
            finally:
                if spent is not None:
                    spent.merge(reader.spent)
        else:
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
                surface = line[start:end]
                if not in_script(surface, language):
                    # An emoji, a time, an English word inside the Hebrew: read past,
                    # as the annotator reads past it (`annotate.base.in_script`).
                    continue
                # Shipped as the browser counts, since chat.js slices the line itself.
                start, end = js_span(line, start, end)
                vocabulary = token.pos not in NOT_VOCABULARY
                if vocabulary and token.lemma not in bands:
                    bands[token.lemma] = self.bands.band(token.lemma, language) if rated else 0
                if vocabulary and token.lemma not in meanings:
                    meanings[token.lemma] = self.gloss(token.lemma, language, target)
                words.append(
                    {
                        "start": start,
                        "end": end,
                        "surface": surface,
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


# --- what changed between what they wrote and what came back ---------------------------

#: Stripped from the edge of a word before it is compared. A recast is a clean sentence
#: and a reader's line is usually not: the maqaf and the geresh are Hebrew's own, and the
#: rest is what either of them might end on.
PUNCTUATION = ".,!?;:\u05be\u05f3\u05f4\"'()[]\u2014\u2013-\u2026"


def _bare(word: str) -> str:
    """One word without its points or the punctuation around it.

    `strip_nikkud` answers with its index map too, which is what a span needs and not
    what a comparison does. The punctuation goes because a recast ends in a full stop the
    reader's line often does not, and "sentence." against "sentence" is not a correction.
    """
    bare, _ = strip_nikkud(word)
    return bare.strip(PUNCTUATION)


def changed_words(wrote: str, recast: str) -> list[str]:
    """The words of the recast that the reader did not write, in the recast's order.

    The diff behind two things at once: the label #242 wants on a corrected line, and the
    record #290 keeps of what a reader got wrong. One implementation, because two diffs
    of the same pair would eventually disagree about whether a line was corrected.

    **Compared without vowel points.** The model is asked to point every word it writes
    and the reader almost never does, so a comparison that counted the points would call
    every line wrong — and the one thing this must never do is report a correction that
    did not happen. `strip_nikkud` is the same normalisation the annotator uses, so a
    word matches here exactly when it is the same word there.

    **Order is not a change.** Hebrew word order is one of the things a recast fixes, and
    a reader who wrote the right words in the wrong order has made a mistake worth
    keeping — but the words themselves are not what changed, and listing all of them
    would say they were all wrong. Multiplicity is kept, so a word written once and
    recast twice shows the second.
    """
    mine = [_bare(word) for word in wrote.split() if word.strip()]
    theirs = [(word, _bare(word)) for word in recast.split() if word.strip()]
    spare: dict[str, int] = {}
    for bare in mine:
        spare[bare] = spare.get(bare, 0) + 1
    out: list[str] = []
    for word, bare in theirs:
        if spare.get(bare, 0) > 0:
            spare[bare] -= 1
            continue
        out.append(word)
    return out


def rewritten(wrote: str, recast: str) -> bool:
    """Whether the recast changed the reader's Hebrew at all.

    Not `wrote != recast`: the recast is pointed and the reader's line is usually not, so
    the strings differ on nearly every correct sentence. What makes a line a slip is that
    a word is there which the reader did not write, or that one they wrote is gone.
    """
    if not wrote.strip() or not recast.strip():
        return False
    mine = sorted(_bare(word) for word in wrote.split() if word.strip())
    theirs = sorted(_bare(word) for word in recast.split() if word.strip())
    return mine != theirs
