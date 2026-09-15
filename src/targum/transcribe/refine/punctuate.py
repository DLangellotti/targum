"""Punctuation, put back into a transcript that was heard without any.

whisper-1 writes Hebrew down as one unbroken run of words: no full stop, no comma, no
question mark. A learner cannot find where a sentence ends, the segmenter cannot either —
so a "sentence" is forty words cut at a breath — and each of those is translated as one
line. Measured on a 14-minute talk (2026-09-15): 1,300 words and not one mark.

The model is asked for the marks and for nothing else, and it is not trusted to have
given only that. Every token it returns is matched back to the token that was heard, and
a mark is kept only where the heard word appears in the answer letter for letter with
nothing but marks around it. A word it corrected, split, merged or invented keeps the
heard spelling and no mark. So the words on the page are the words the transcriber heard,
each on its own clock, whatever the model did — the refiner's one hard rule.

Run only where it is missing: a transcript that already punctuates (Scribe does) is
left as it came, and costs nothing here.
"""

from __future__ import annotations

import difflib
import os
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

from ...usage import Usage
from ..models import Word

NAME = "punctuate/1"
MODEL = "claude-sonnet-5"
TIMEOUT = 120.0

#: What ends a sentence, as the transcript or the model writes it.
ENDS = (".", "?", "!", "…", "׃")

#: The marks a heard word may gain. No quotes, apostrophes, geresh or gershayim: in
#: Hebrew those are letters of a word (ד"ר, וכו'), and a mark that changes a word is not
#: punctuation.
MARKS = frozenset(".,?!;:…()–—")

#: Fewer sentence ends than one in this many words is a transcript heard without
#: punctuation. Scribe's Hebrew runs at about one in twelve; whisper's at none in 1,300.
SPARSE_WORDS = 40

#: Too few words to need a sentence end at all.
LEAST_WORDS = 20

#: Words per request. Small enough that a part's requests run side by side and a bad
#: answer loses one stretch rather than a part; large enough that a sentence is seldom
#: cut in two at the seam.
CHUNK_WORDS = 300

#: How many requests one part runs at once.
WORKERS = 4

#: Tokens per Hebrew word, each way, measured against claude-sonnet-5 on the talk above:
#: 255 words came to 1,050 in (with the instruction) and 973 out. For the estimate.
TOKENS_PER_WORD = 4.0

#: An answer whose words match fewer of the heard ones than this was not a punctuation of
#: them, and none of its marks are taken.
LEAST_AGREEMENT = 0.9

ASK = """Below is a speech-to-text transcript in {language}, with no punctuation. Add the \
punctuation a careful editor would: full stops, commas and question marks. The reader is \
learning the language, so end a sentence wherever the speaker has finished a thought rather \
than joining thoughts with commas. Put a blank line between paragraphs where the topic turns.

Change nothing else. Keep every word exactly as written, in the same order, even where it \
looks misheard or repeated. Do not correct, add, remove, merge or split a word. Answer with \
the punctuated text and nothing else.

<transcript>
{text}
</transcript>"""

#: One request: the prompt in, and the answer with its input and output tokens out.
Ask = Callable[[str], tuple[str, int, int]]


def ends_sentence(text: str) -> bool:
    return text.rstrip(")").endswith(ENDS)


def sparse(words: list[Word]) -> bool:
    """Whether these words hold fewer sentence ends than a punctuated text would."""
    tokens = [token for word in words for token in word.text.split()]
    ends = sum(1 for token in tokens if ends_sentence(token))
    return ends * SPARSE_WORDS < len(tokens)


def needs_punctuation(words: list[Word]) -> bool:
    """Whether these words were heard without the marks a reader needs."""
    return sum(len(word.text.split()) for word in words) >= LEAST_WORDS and sparse(words)


class Punctuator:
    name = NAME

    def __init__(self, model: str | None = None, ask: Ask | None = None) -> None:
        self.model = model or MODEL
        self.spent = Usage()
        self._ask = ask

    def available(self) -> tuple[bool, str]:
        if self._ask is not None:
            return True, self.model
        if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"):
            return True, self.model
        return False, "set ANTHROPIC_API_KEY in .env"

    def dollars_per_minute(self) -> float:
        """What a minute of speech costs to punctuate, on the high side like every
        estimate: speech at the rate translation is guessed at."""
        from ...audio import SPEECH_WORDS_PER_MINUTE
        from ...translate.anthropic_provider import DEFAULT_MODEL, PRICES

        in_price, out_price = PRICES.get(self.model, PRICES[DEFAULT_MODEL])
        tokens = SPEECH_WORDS_PER_MINUTE * TOKENS_PER_WORD
        return tokens * (in_price + out_price) / 1_000_000

    def restore(self, words: list[Word], language: str) -> tuple[list[Word], set[int]]:
        """The same words, with marks where the model put them, and where it broke
        paragraphs: the index of each word that opens a new one.

        Every word keeps its clock, its speaker and its letters. Only `text` gains marks.
        """
        tokens = [(index, token) for index, word in enumerate(words) for token in word.text.split()]
        if not tokens:
            return list(words), set()
        chunks = _chunks(words, tokens)
        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            answers = list(pool.map(lambda chunk: self._one(chunk, tokens, language), chunks))
        texts = [token for _, token in tokens]
        breaks: set[int] = set()
        for (start, _), (marked, opens, used) in zip(chunks, answers, strict=True):
            if used is not None:
                # Counted here rather than in the workers: `Usage` is not a lock.
                self.spent.add(self.model, *used)
            for offset, text in marked.items():
                texts[start + offset] = text
            breaks.update(tokens[start + offset][0] for offset in opens)
        joined: dict[int, list[str]] = {}
        for (index, _), text in zip(tokens, texts, strict=True):
            joined.setdefault(index, []).append(text)
        out = [
            word.model_copy(update={"text": " ".join(joined[index])}) if index in joined else word
            for index, word in enumerate(words)
        ]
        return out, {index for index in breaks if index > 0}

    def _one(
        self, chunk: tuple[int, int], tokens: list[tuple[int, str]], language: str
    ) -> tuple[dict[int, str], set[int], tuple[int, int] | None]:
        from ...translate.prompts import language_name

        start, end = chunk
        heard = [token for _, token in tokens[start:end]]
        prompt = ASK.format(
            language=language_name(language) if language else "its original language",
            text=" ".join(heard),
        )
        try:
            written, used_in, used_out = (self._ask or self._request)(prompt)
        except Exception as error:  # noqa: BLE001 - one stretch without marks, not a failed part
            import logging

            logging.getLogger(__name__).warning("punctuation skipped a stretch: %s", error)
            return {}, set(), None
        return (*transfer(heard, written), (used_in, used_out))

    def _request(self, prompt: str) -> tuple[str, int, int]:
        import anthropic

        client = anthropic.Anthropic(timeout=TIMEOUT)
        answer = client.messages.create(
            model=self.model,
            max_tokens=8192,
            # Off, not low: putting commas into words already written is not a problem
            # to reason about, and a thinking budget made the cost of a part a coin toss
            # — the same 1,848 words came to 17,093 tokens out with it and ~7,000 without.
            thinking={"type": "disabled"},
            messages=[{"role": "user", "content": prompt}],
        )
        written = "".join(str(getattr(block, "text", "")) for block in answer.content)
        usage = answer.usage
        return written, usage.input_tokens, usage.output_tokens


def transfer(heard: list[str], written: str) -> tuple[dict[int, str], set[int]]:
    """The marks the answer put on each heard token, and the tokens opening a paragraph.

    Returns only what changed: token offset to its marked text. A heard token is marked
    only where the answer holds it letter for letter with nothing but `MARKS` either side.
    """
    from ...audio.spans import normalise

    answer: list[str] = []
    opens_at: set[int] = set()
    for paragraph in (piece for piece in written.split("\n\n") if piece.strip()):
        opens_at.add(len(answer))
        answer.extend(paragraph.split())
    if not heard or not answer:
        return {}, set()
    matcher = difflib.SequenceMatcher(
        a=[normalise(token) for token in heard],
        b=[normalise(token) for token in answer],
        autojunk=False,
    )
    pairs = {
        b + offset: a + offset
        for a, b, size in matcher.get_matching_blocks()
        for offset in range(size)
    }
    if len(pairs) < LEAST_AGREEMENT * len(heard):
        return {}, set()
    marked: dict[int, str] = {}
    for b, a in pairs.items():
        spoken, given = heard[a], answer[b]
        at = given.find(spoken)
        if given == spoken or at < 0:
            continue
        around = given[:at] + given[at + len(spoken) :]
        if all(character in MARKS for character in around):
            marked[a] = given
    opens = {pairs[b] for b in opens_at if b in pairs and b > 0}
    return marked, opens


def _chunks(words: list[Word], tokens: list[tuple[int, str]]) -> list[tuple[int, int]]:
    """Token ranges of about `CHUNK_WORDS`, each ending at the longest pause in its last
    sixth, so a seam falls where the speaker breathed rather than inside a sentence."""
    chunks: list[tuple[int, int]] = []
    start = 0
    while start < len(tokens):
        end = min(len(tokens), start + CHUNK_WORDS)
        if end < len(tokens):
            low = max(start + 1, end - CHUNK_WORDS // 6)

            def pause(at: int) -> float:
                before, after = words[tokens[at - 1][0]], words[tokens[at][0]]
                return after.start - before.end

            end = max(range(low, end + 1), key=pause)
        chunks.append((start, end))
        start = end
    return chunks
