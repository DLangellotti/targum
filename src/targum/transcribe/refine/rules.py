"""Refinement without a model: drop what was never speech, break where the voice did.

The seam the eventual model-backed refiner will fill is already the whole contract
here: paragraphs, each carrying its own words, so the clocks survive whatever the text
becomes. The one thing rules cannot do is hear where a sentence ended, so a transcript
that came back without punctuation has it put back first (`punctuate.py`), where a
punctuator is given — every word kept, only marks added.
"""

from __future__ import annotations

from ...usage import Usage
from ..models import Refined, RefinedParagraph, Transcript, Word
from .punctuate import Punctuator, ends_sentence, needs_punctuation, sparse

#: A pause this long between words is a paragraph, not a breath.
PARAGRAPH_PAUSE_S = 1.2

#: A paragraph longer than this is cut at its longest pause. Someone talking over music
#: never stops for 1.2 s, and Whisper's Hebrew barely punctuates, so a 57-minute video
#: came back as paragraphs of hundreds of words, each one segment: a line nobody can
#: follow along, cut off by the lemmatizer at 512 tokens, and at sixteen to a batch the
#: reason the box was OOM-killed four times in an hour (2026-09-14).
MAX_PARAGRAPH_WORDS = 40

#: Neither side of a cut is shorter than this, so a pause near an edge does not leave a
#: paragraph of two words.
LEAST_PARAGRAPH_WORDS = 10

#: What ends a sentence, where a transcript has it. A cut after one of these is taken
#: before a longer pause in the middle of a sentence.
SENTENCE_ENDS = (".", "?", "!", "׃")

#: Words the provider was less sure of than this are kept but marked; a reader is owed
#: the doubt, and a dropped word is a hole in a sentence somebody is following.
LOW_CONFIDENCE = 0.5


class RuleRefiner:
    """rules/3: rules/2, with punctuation put back where it was missing, and a pause
    that breaks a paragraph only where a sentence has ended — in a punctuated
    transcript, a breath mid-sentence is not the end of a thought."""

    def __init__(self, punctuator: Punctuator | None = None) -> None:
        self.punctuator = punctuator

    @property
    def name(self) -> str:
        return f"rules/3+{self.punctuator.name}" if self.punctuator else "rules/3"

    @property
    def spent(self) -> Usage:
        return self.punctuator.spent if self.punctuator else Usage()

    def keeps(self, kept: Refined) -> bool:
        """Whether a part an earlier set of rules refined stands without being redone.

        Redoing one re-cuts its segments, buys their translation again and moves its
        reader's place, so rules/1 and rules/2 — which differ from this only in where a
        long paragraph is cut — stand (2026-09-14). Except where the words came back with
        no punctuation and this can put it back: that text is the one a learner cannot
        read, and the hearing under it is cached, so the redo buys marks and a
        translation and never the hearing (2026-09-15).
        """
        if kept.refiner == self.name:
            return True
        if not kept.refiner.startswith("rules/"):
            return False
        if self.punctuator is None:
            return True
        return not needs_punctuation([word for p in kept.paragraphs for word in p.words])

    def refine(self, transcript: Transcript) -> Refined:
        words = [word for word in transcript.words if not word.event and word.text.strip()]
        opens: set[int] = set()
        if (
            self.punctuator is not None
            and needs_punctuation(words)
            and self.punctuator.available()[0]
        ):
            words, opens = self.punctuator.restore(words, transcript.language)
        punctuated = not sparse(words)

        paragraphs: list[RefinedParagraph] = []
        current: list[Word] = []

        def close() -> None:
            if not current:
                return
            for piece in _cut(list(current)):
                paragraphs.append(
                    RefinedParagraph(
                        text=" ".join(word.text for word in piece).strip(),
                        speaker=piece[0].speaker,
                        words=piece,
                    )
                )
            current.clear()

        last: Word | None = None
        for index, word in enumerate(words):
            if last is not None:
                voices = bool(word.speaker or last.speaker) and word.speaker != last.speaker
                paused = word.start - last.end >= PARAGRAPH_PAUSE_S and (
                    not punctuated or ends_sentence(last.text)
                )
                if voices or paused or index in opens:
                    close()
            current.append(word)
            last = word
        close()
        return Refined(
            refiner=self.name,
            provider=transcript.provider,
            language=transcript.language,
            paragraphs=[p for p in paragraphs if p.text],
        )


def _cut(words: list[Word]) -> list[list[Word]]:
    """One paragraph, or several where it runs past `MAX_PARAGRAPH_WORDS`.

    Each cut is the longest pause that leaves both sides `LEAST_PARAGRAPH_WORDS` long,
    and a pause after a sentence end beats a longer one inside a sentence. The words keep
    their clocks; only where one paragraph stops and the next starts is decided here.
    """
    if len(words) <= MAX_PARAGRAPH_WORDS:
        return [words]
    places = range(LEAST_PARAGRAPH_WORDS, len(words) - LEAST_PARAGRAPH_WORDS + 1)
    middle = len(words) / 2

    def rank(at: int) -> tuple[bool, bool, float, float]:
        before = words[at - 1].text.rstrip()
        # After a sentence, then after a clause, then at the longest breath.
        return (
            before.endswith(SENTENCE_ENDS),
            before.endswith((",", ";", ":")),
            words[at].start - words[at - 1].end,
            -abs(at - middle),
        )

    at = max(places, key=rank)
    return _cut(words[:at]) + _cut(words[at:])
