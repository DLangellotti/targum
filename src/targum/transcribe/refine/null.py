"""A refiner that changes nothing: one paragraph per transcript, words kept."""

from __future__ import annotations

from ..models import Refined, RefinedParagraph, Transcript


class NullRefiner:
    name = "none"

    def refine(self, transcript: Transcript) -> Refined:
        words = [w for w in transcript.words if w.text.strip() and not w.event]
        return Refined(
            refiner=self.name,
            provider=transcript.provider,
            language=transcript.language,
            paragraphs=(
                [
                    RefinedParagraph(
                        text=" ".join(w.text for w in words),
                        speaker=words[0].speaker,
                        words=words,
                    )
                ]
                if words
                else []
            ),
        )
