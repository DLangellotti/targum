"""Refinement without a model: drop what was never speech, break where the voice did.

The seam the eventual model-backed refiner will fill is already the whole contract
here: paragraphs, each carrying its own words, so the clocks survive whatever the text
becomes.
"""

from __future__ import annotations

from ..models import Refined, RefinedParagraph, Transcript, Word

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
    name = "rules/2"
    #: What this replaces without redoing. rules/1 read the same words and differs only
    #: in long paragraphs; redoing it would re-cut the segments of every recording
    #: already heard, and so buy their translations again and move their readers' places.
    keeps = frozenset({"rules/1"})

    def refine(self, transcript: Transcript) -> Refined:
        paragraphs: list[RefinedParagraph] = []
        current: list[Word] = []

        def close() -> None:
            if not current:
                return
            for words in _cut(list(current)):
                paragraphs.append(
                    RefinedParagraph(
                        text=" ".join(word.text for word in words).strip(),
                        speaker=words[0].speaker,
                        words=words,
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

    def rank(at: int) -> tuple[bool, float, float]:
        ends = words[at - 1].text.rstrip().endswith(SENTENCE_ENDS)
        return (ends, words[at].start - words[at - 1].end, -abs(at - middle))

    at = max(places, key=rank)
    return _cut(words[:at]) + _cut(words[at:])
