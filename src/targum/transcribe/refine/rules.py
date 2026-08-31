"""Refinement without a model: drop what was never speech, break where the voice did.

The seam the eventual model-backed refiner will fill is already the whole contract
here: paragraphs, each carrying its own words, so the clocks survive whatever the text
becomes.
"""

from __future__ import annotations

from ..models import Refined, RefinedParagraph, Transcript, Word

#: A pause this long between words is a paragraph, not a breath.
PARAGRAPH_PAUSE_S = 1.2

#: Words the provider was less sure of than this are kept but marked; a reader is owed
#: the doubt, and a dropped word is a hole in a sentence somebody is following.
LOW_CONFIDENCE = 0.5


class RuleRefiner:
    name = "rules/1"

    def refine(self, transcript: Transcript) -> Refined:
        paragraphs: list[RefinedParagraph] = []
        current: list[Word] = []

        def close() -> None:
            if not current:
                return
            paragraphs.append(
                RefinedParagraph(
                    text=" ".join(word.text for word in current).strip(),
                    speaker=current[0].speaker,
                    words=list(current),
                )
            )
            current.clear()

        last: Word | None = None
        for word in transcript.words:
            if word.event or not word.text.strip():
                continue
            starts_paragraph = last is not None and (
                word.start - last.end >= PARAGRAPH_PAUSE_S
                or (word.speaker or last.speaker)
                and word.speaker != last.speaker
            )
            if starts_paragraph:
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
