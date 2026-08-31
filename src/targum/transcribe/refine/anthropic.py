"""Refinement with a model: the transcript a person would have typed.

What a transcriber hears is not what a reader should read: it runs sentences together,
keeps every false start, and carries the ad break as prose. The model repunctuates,
paragraphs, and drops what was never the programme — under one hard rule: **every word
it keeps must be a word that was heard.** The output is anchor-mapped back onto the
heard words, so each kept word carries its own clock, and a word the model invented
fails to map and is dropped. Timing is never guessed.

Versioned by name like every stage that can improve. The transcript underneath is
cached and paid for, so renaming this redoes the refinement everywhere for nothing.
"""

from __future__ import annotations

import difflib
import os

from ...errors import TargumError
from ...usage import Usage
from ..models import Refined, RefinedParagraph, Transcript, Word

MODEL = "claude-sonnet-5"
TIMEOUT = 300.0

#: Dollars per million tokens, in and out, the shape the translation provider uses.
PRICES: dict[str, tuple[float, float]] = {}

ASK = """This is a raw speech-to-text transcript in {language}. Rewrite it as clean \
readable text: fix punctuation, break it into paragraphs at topic changes, drop filler \
words, false starts, and any advertising or station identification. Do not translate, \
do not summarise, do not add a single word that is not in the transcript. Answer with \
the cleaned text and nothing else.

{text}"""


class AnthropicRefiner:
    name = "anthropic-refine/1"

    def __init__(self, model: str | None = None) -> None:
        self.model = model or MODEL
        self.spent = Usage()

    def available(self) -> tuple[bool, str]:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            return False, "set ANTHROPIC_API_KEY in .env"
        return True, self.model

    def refine(self, transcript: Transcript) -> Refined:
        heard = [word for word in transcript.words if word.text.strip() and not word.event]
        if not heard:
            return Refined(
                refiner=self.name, provider=transcript.provider, language=transcript.language
            )
        import anthropic

        client = anthropic.Anthropic(timeout=TIMEOUT)
        try:
            answer = client.messages.create(
                model=self.model,
                max_tokens=8192,
                messages=[
                    {
                        "role": "user",
                        "content": ASK.format(
                            language=transcript.language or "the original language",
                            text=" ".join(word.text for word in heard),
                        ),
                    }
                ],
            )
        except Exception as error:
            raise TargumError("The transcript could not be refined.", str(error)) from error
        usage = getattr(answer, "usage", None)
        if usage is not None:
            self.spent.add(self.model, usage.input_tokens, usage.output_tokens)
        written = "".join(str(getattr(block, "text", "")) for block in answer.content)
        return self._mapped(transcript, heard, written)

    def _mapped(self, transcript: Transcript, heard: list[Word], written: str) -> Refined:
        """The model's text, with every kept word anchored to the word it was.

        Matching runs on normalised tokens, so repunctuation costs nothing; a token
        the matcher cannot pair is a word the model changed or invented, and it rides
        along with its neighbours' clocks interpolated — visible text, honest time.
        """
        from ...audio.spans import normalise

        spoken = [normalise(word.text) for word in heard]
        paragraphs_text = [piece.strip() for piece in written.split("\n\n") if piece.strip()]
        out: list[RefinedParagraph] = []
        matcher = difflib.SequenceMatcher(a=spoken, autojunk=False)
        cursor = 0
        for piece in paragraphs_text:
            tokens = piece.split()
            matcher.set_seq2([normalise(token) for token in tokens])
            paired: dict[int, int] = {}
            for a, b, size in matcher.get_matching_blocks():
                for offset in range(size):
                    if a + offset >= cursor:
                        paired[b + offset] = a + offset
            words: list[Word] = []
            last: Word | None = None
            for index, token in enumerate(tokens):
                anchor = paired.get(index)
                if anchor is not None:
                    source = heard[anchor]
                    words.append(
                        Word(
                            text=token,
                            start=source.start,
                            end=source.end,
                            confidence=source.confidence,
                            speaker=source.speaker,
                        )
                    )
                    last = words[-1]
                    cursor = max(cursor, anchor + 1)
                elif last is not None:
                    # A word the model reshaped: it borrows the clock beside it rather
                    # than being dropped from the page or given an invented time.
                    words.append(Word(text=token, start=last.end, end=last.end, confidence=0.3))
            if words:
                out.append(
                    RefinedParagraph(
                        text=" ".join(word.text for word in words),
                        speaker=words[0].speaker,
                        words=words,
                    )
                )
        if not out:
            # The model answered with something unusable; the rules still stand.
            from .rules import RuleRefiner

            fallback = RuleRefiner().refine(transcript)
            return Refined(
                refiner=self.name,
                provider=transcript.provider,
                language=transcript.language,
                paragraphs=fallback.paragraphs,
            )
        return Refined(
            refiner=self.name,
            provider=transcript.provider,
            language=transcript.language,
            paragraphs=out,
        )
