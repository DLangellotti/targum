"""Forced alignment: a transcript the reader supplied, timed against their recording.

Local and unpaid — because paying a transcriber by the minute to align a text you
already have inherits the transcriber's errors at every mismatch. Optional, like the
embedding aligner: without the extra installed the recording plays straight through,
which is the `_read_through` shape and not a failure.

**Permissively licensed, which it was not.** Until 2026-09-02 this ran
`ctc-forced-aligner` (CC BY-NC 4.0) on a model in Meta's MMS lineage (NonCommercial as
well), and every word timing targum held had been made by a NonCommercial tool. The
algorithm was never the encumbered part: CTC forced alignment is
`torchaudio.functional.forced_align`, which is BSD-2, and only the acoustic model
carried the term. So the model changed and the shape did not.

What runs now is `imvladikon/wav2vec2-large-xlsr-53-hebrew` — Apache-2.0, fine-tuned
from XLS-R (Apache-2.0) on Common Voice (CC0). Nothing in that chain restricts use.

**It aligns Hebrew as Hebrew.** The MMS model reached Hebrew by romanising it first,
so every span was decided in a transliteration of the text rather than the text. This
model's vocabulary is the Hebrew alphabet, final forms included, and the letters it is
aligning are the letters on the page.

**Hebrew, and since 2026-09-13 French, Russian and Italian** — one permissive model per
language (`MODELS`) rather than one multilingual NonCommercial one. A language with no row
reports itself unavailable and plays through, exactly as a missing install does.

**A span is moved to the voice after it is found** (2026-09-27, targum-internal#225). CTC
emits a letter as a spike and fills the rest of the sound with blanks, so the span the
path gives a word is narrower than the word: measured against the acoustic edges of words
that follow or precede a pause, the path started words 15-70 ms after the voice did and
ended them 25-220 ms before it stopped, on chanted Torah (six PocketTorah aliyot) and on
read speech (two LibriVox readers) alike. `to_the_voice` widens each span into the blank
frames either side, as far as the audio stays voiced. See its docstring for the rule.
"""

from __future__ import annotations

import os
import re
import unicodedata
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from ..errors import TargumError
from ..paths import model_dir
from .tools import samples

#: Apache-2.0, and the name says which model made a span. Stored spans carry the
#: aligner's name, so changing this is what makes a recording align again.
MODEL = "imvladikon/wav2vec2-large-xlsr-53-hebrew"
NAME = "ctc-xlsr-he/2"

#: The rate the model was trained at. Not a preference.
RATE = 16000

#: Emissions are made a window at a time, with context either side that is thrown away
#: after. A reading is an hour long and one forward pass over an hour of audio asks for
#: more memory than a laptop has — measured: 400 seconds in one pass did not finish in
#: ten minutes, where the same audio in windows takes under a minute. The context is
#: what stops a word that straddles a seam from being aligned against silence.
WINDOW_S = 30
CONTEXT_S = 2
BATCH = 4

#: A word the aligner scored below this is trimmed from a window's edges; a part whose
#: mean score sits below the floor gets no spans at all. Measured against a real clip
#: at implementation of the supplied-text flow; conservative until then.
SCORE_FLOOR = -10.0
MATCH_FLOOR = -6.0

#: How `to_the_voice` moves a span (2026-09-27). Measured, not chosen: at the words where
#: the voice's own edge can be seen — after or before a pause — the path's start trailed
#: the voice by a median of 15-70 ms per recording (about two frames) and its end fell
#: short by 25-220 ms. `LEAD_S` is that start lag, applied only where the voice gives no
#: edge to walk to. The two reaches bound the walk: a start is never pulled back more
#: than about three times the worst per-recording lag, and an end never carried on past
#: half a second, which covers the latest measured end (a held note in Devarim-1, 330 ms
#: at the upper quartile) without letting a word swallow a cough that follows it.
LEAD_S = 0.04
REACH_BACK_S = 0.2
REACH_ON_S = 0.5

#: A frame is voiced when it is louder than a quarter of the way from the recording's
#: quiet (its 10th percentile, in dB) to its loud (its 95th). Relative to the recording,
#: because a phone in a car and a studio have different floors.
QUIET_Q = 0.10
LOUD_Q = 0.95
VOICED_AT = 0.25

#: The language the module's own `MODEL` and `NAME` are for.
LANGUAGE = "he"

#: One acoustic model per language, and the name its spans are stored under (2026-09-13).
#: Each is XLS-R fine-tuned by one author and published Apache-2.0: French and Italian on
#: Common Voice 6.1 (CC0), Russian on Common Voice 6.1 and CSS10 (Apache-2.0). The same
#: clean chain Hebrew's model has, checked the same way, and the reason there is no
#: Yiddish or Aramaic row: nothing permissive is trained for either. Hebrew's row is the
#: constants above, byte for byte, because its name is part of every stored span's key.
MODELS: dict[str, tuple[str, str]] = {
    LANGUAGE: (MODEL, NAME),
    "fr": ("jonatasgrosman/wav2vec2-large-xlsr-53-french", "ctc-xlsr-fr/2"),
    "ru": ("jonatasgrosman/wav2vec2-large-xlsr-53-russian", "ctc-xlsr-ru/2"),
    "it": ("jonatasgrosman/wav2vec2-large-xlsr-53-italian", "ctc-xlsr-it/2"),
}

_LETTERS = re.compile(r"[^א-ת]")


def _code(language: str) -> str:
    return (language or "").split("-")[0].lower()


def _bare(word: str, language: str = LANGUAGE) -> str:
    """The letters, which is all the model has symbols for.

    Nikkud and cantillation are marks on a letter rather than letters; the Hebrew model was
    trained on unpointed Common Voice and has no symbol for either. Stripping them here
    is the same normalisation `annotate` does before it asks a lemmatizer anything.

    The other models spell in lowercase with their accents on: `é` is one symbol to the
    French model, so an accented letter is kept whole (composed) and only what is not a
    letter at all goes. Their vocabularies also carry the apostrophe, which `align` keeps
    when the model has a symbol for it.
    """
    if _code(language) == LANGUAGE:
        plain = "".join(
            ch for ch in unicodedata.normalize("NFC", word or "") if not unicodedata.combining(ch)
        )
        return _LETTERS.sub("", plain)
    composed = unicodedata.normalize("NFC", word or "").lower()
    return "".join(ch for ch in composed if ch.isalpha() or ch in "'’").replace("’", "'")


def match_score(words: list[str], scores: list[float], language: str) -> float | None:
    """How closely a stretch of text matched its recording: the mean score of the words
    the model has letters for, or None where it has letters for none of them.

    A word it cannot spell — English inside Hebrew, a numeral — is placed by its
    neighbours at `SCORE_FLOOR`, and averaged in with the rest a travel vlog's few English
    phrases pulled a well-matched part under `MATCH_FLOOR`, and the part lost following
    along for words the model was never asked about (2026-09-14).
    """
    heard = [score for word, score in zip(words, scores, strict=True) if _bare(word, language)]
    return sum(heard) / len(heard) if heard else None


def voiced_frames(levels_db: Sequence[float]) -> list[bool]:
    """Which frames are voiced, given each frame's level in dB. See `VOICED_AT`."""
    if not levels_db:
        return []
    ordered = sorted(levels_db)

    def at(share: float) -> float:
        return ordered[min(len(ordered) - 1, int(share * (len(ordered) - 1)))]

    quiet, loud = at(QUIET_Q), at(LOUD_Q)
    line = quiet + VOICED_AT * (loud - quiet)
    return [level > line for level in levels_db]


def share_the_gap(
    spans: Sequence[tuple[int, int] | None],
    spoken: Sequence[int],
    total: int,
) -> list[tuple[int, int] | None]:
    """Place a spoken word the model has no letters for in the gap its neighbours leave.

    `spoken[i]` is how many letters word `i` has that the model cannot spell — a Latin
    name in a Hebrew text — and 0 for everything else, punctuation included. The CTC path
    leaves such a word unplaced, but it leaves its sound too: the frames between the
    placed words either side. A run of them shares that gap by length. Placed, they are
    boundaries `to_the_voice` stops at, where unplaced the word before would stretch over
    the name and light while it is said (targum-internal#380, 2026-09-27: "Lubbock" in
    Ahad Ha'am went from 121.36-121.74 s to a point).
    """
    placed = list(spans)
    index = 0
    while index < len(placed):
        if placed[index] is not None or not spoken[index]:
            index += 1
            continue
        run_end = index
        while run_end < len(placed) and placed[run_end] is None and spoken[run_end]:
            run_end += 1
        before = next((placed[i] for i in range(index - 1, -1, -1) if placed[i]), None)
        after = next((placed[i] for i in range(run_end, len(placed)) if placed[i]), None)
        low = before[1] if before else 0
        high = after[0] if after else total
        weight = sum(spoken[index:run_end])
        if high - low >= run_end - index and weight:
            at = float(low)
            for i in range(index, run_end):
                width = (high - low) * spoken[i] / weight
                placed[i] = (round(at), max(round(at) + 1, round(at + width)))
                at += width
        index = run_end
    return placed


def to_the_voice(
    spans: Sequence[tuple[int, int] | None],
    voiced: Sequence[bool],
    lead: int,
    reach_back: int,
    reach_on: int,
) -> list[tuple[int, int] | None]:
    """Each word's [start, end) frames, widened from the CTC path to the voice.

    `None` is a word the path did not place, and stays `None`. Starts first, walking back
    from the path's start through the blank frames before it, never into the previous
    word: where a quiet frame is met, the word starts on the first voiced frame after it,
    which is the voice's onset. Where the walk finds no quiet — the words run into each
    other, or the recording has no floor — the voice cannot place the boundary, and the
    start moves back by the measured `lead` alone. Then ends, walking on through voiced
    frames until the voice stops or the next word starts, so words said without a break
    between them tile and nothing goes unlit in the middle of a phrase.
    """
    placed = [list(span) if span else None for span in spans]
    previous_end = 0
    for span in placed:
        if span is None:
            continue
        start = span[0]
        at = start
        met_quiet = False
        while at > previous_end and start - at < reach_back:
            if at - 1 < len(voiced) and not voiced[at - 1]:
                met_quiet = True
                break
            at -= 1
        span[0] = at if met_quiet else max(previous_end, start - lead)
        previous_end = span[1]
    following: int | None = None
    for span in reversed(placed):
        if span is None:
            continue
        ceiling = following if following is not None else len(voiced)
        end = at = span[1]
        while at < ceiling and at - end < reach_on and at < len(voiced) and voiced[at]:
            at += 1
        span[1] = max(end, at)
        following = span[0]
    return [(span[0], span[1]) if span else None for span in placed]


class CtcAligner:
    """Word timings for a recording, in a language `MODELS` has an acoustic model for."""

    name = NAME

    def __init__(self, language: str = LANGUAGE) -> None:
        self.language = _code(language)
        found = MODELS.get(self.language)
        self.model = found[0] if found else ""
        # The class attribute stays Hebrew's name, so what was stored before a language
        # could be asked for keeps its key.
        self.name = found[1] if found else f"ctc-xlsr-{self.language}/unavailable"

    def available(self) -> tuple[bool, str]:
        if not self.model:
            return False, f"No acoustic model aligns {self.language!r} yet"
        try:
            import torchaudio.functional  # noqa: F401
            import transformers  # noqa: F401
        except ImportError:
            return False, "uv sync --extra speech-align  (the forced aligner)"
        return True, self.name

    def _emissions(self, audio: Path) -> tuple[Any, float, Any, list[bool]]:
        """Log probabilities per frame, how long a frame is, and which frames are voiced.

        Windowed, because the whole file at once does not fit. Each window is given
        `CONTEXT_S` of real audio either side and the frames covering that context are
        dropped, so the seams are aligned with a model that could hear across them.
        """
        import torch
        from transformers import Wav2Vec2ForCTC, Wav2Vec2Processor

        os.environ.setdefault("HF_HOME", str(model_dir() / "hf"))
        os.environ.setdefault("TORCH_HOME", str(model_dir()))
        processor = Wav2Vec2Processor.from_pretrained(self.model)
        # Annotated rather than inferred: with the extra installed the class is typed
        # and `.eval()` reads as an untyped call, and without it there is no class to
        # read at all. CI has no `transformers`, so an ignore that silences the first
        # case is an unused ignore in the second — which is also an error.
        model: Any = Wav2Vec2ForCTC.from_pretrained(self.model)
        model.eval()

        heard = processor(samples(audio, RATE), sampling_rate=RATE, return_tensors="pt")
        wave = heard.input_values[0]
        stride = model.config.inputs_to_logits_ratio
        window, context = WINDOW_S * RATE, CONTEXT_S * RATE
        # Frame for frame with the logits: frame t is the audio from t strides in. The
        # processor's normalising is one scale and one shift for the whole file, which
        # moves every level by the same number of dB and so leaves `voiced_frames` alone.
        whole = wave.numel() // stride
        power = wave[: whole * stride].reshape(whole, stride).float().pow(2).mean(dim=1)
        voiced = voiced_frames((10 * torch.log10(power + 1e-10)).tolist())

        if wave.numel() <= window:
            with torch.inference_mode():
                logits = model(wave.unsqueeze(0)).logits
            return torch.log_softmax(logits[0].float(), dim=-1), stride / RATE, processor, voiced

        # Padded so every window is the same width, which is what lets them be batched.
        over = -wave.numel() % window
        padded = torch.nn.functional.pad(wave, (context, context + over))
        windows = padded.unfold(0, window + 2 * context, window)
        made = []
        with torch.inference_mode():
            for start in range(0, windows.size(0), BATCH):
                made.append(model(windows[start : start + BATCH]).logits)
        logits = torch.cat(made, dim=0)
        keep = context // stride
        logits = logits[:, keep : keep + window // stride].flatten(0, 1)
        if over:
            logits = logits[: -(over // stride)]
        return torch.log_softmax(logits.float(), dim=-1), stride / RATE, processor, voiced

    def align(
        self, audio: Path, words: list[str], language: str
    ) -> list[tuple[float, float, float]]:
        """One (start, end, score) per word, in seconds into the audio file.

        A word the model has no letters for — a bare numeral, a URL in the transcript —
        gets a zero-width span at the previous word's end rather than a wrong one. It is
        in the list because the caller counts on the list matching the words it handed in.
        """
        usable, hint = self.available()
        if not usable:
            raise TargumError("The forced aligner is not installed.", hint)
        code = _code(language)
        if code not in MODELS:
            raise TargumError(
                f"The forced aligner reads Hebrew, French, Russian and Italian, not {language!r}.",
                "Recordings in other languages play without following along.",
            )
        if code != self.language:
            # Asked about a language other than the one this aligner loads: answered by
            # the one that does, so the name on the spans is the model that made them.
            return CtcAligner(code).align(audio, words, code)

        spelled = [_bare(word, code) for word in words]
        if not any(spelled):
            # Nothing here the model has symbols for — a part whose transcript is a URL
            # and a page number. Answered before the model is loaded rather than after:
            # this is the cheap case and it should not cost a gigabyte of weights and a
            # decode of the audio to find out.
            return [(0.0, 0.0, SCORE_FLOOR) for _ in words]

        import torch
        import torchaudio.functional as alignment

        log_probs, per_frame, processor, voiced = self._emissions(audio)
        vocab = processor.tokenizer.get_vocab()
        # The blank the model emits, which is not `<pad>`: the tokenizer carries four
        # added special tokens the head never has an output class for, and handing one
        # of those to `forced_align` is out of range rather than wrong-looking.
        blank = vocab["[PAD]"]
        divider = vocab["|"]

        targets: list[int] = []
        owner: list[int] = []
        for index, word in enumerate(spelled):
            letters = [vocab[ch] for ch in word if ch in vocab]
            if not letters:
                continue
            if targets:
                targets.append(divider)
                owner.append(-1)
            targets.extend(letters)
            owner.extend([index] * len(letters))
        if not targets:
            return [(0.0, 0.0, SCORE_FLOOR) for _ in words]

        paths, scores = alignment.forced_align(
            log_probs.unsqueeze(0), torch.tensor([targets], dtype=torch.int32), blank=blank
        )
        merged = alignment.merge_tokens(paths[0], scores[0], blank=blank)

        found: dict[int, list[int]] = {}
        heard: dict[int, list[float]] = {}
        for span, who in zip(merged, owner, strict=True):
            if who < 0:
                continue
            edges = found.setdefault(who, [span.start, span.end])
            edges[1] = span.end
            heard.setdefault(who, []).append(float(span.score))

        # A spoken word with no letters the model knows, counted, for `share_the_gap`.
        spoken = [
            0
            if i in found or any(ch in vocab for ch in spelled[i])
            else sum(1 for ch in word if ch.isalpha())
            for i, word in enumerate(words)
        ]
        frames = to_the_voice(
            share_the_gap(
                [(found[i][0], found[i][1]) if i in found else None for i in range(len(words))],
                spoken,
                len(voiced),
            ),
            voiced,
            lead=round(LEAD_S / per_frame),
            reach_back=round(REACH_BACK_S / per_frame),
            reach_on=round(REACH_ON_S / per_frame),
        )
        out: list[tuple[float, float, float]] = []
        clock = 0.0
        for index, placed in enumerate(frames):
            if placed is not None:
                start, end = placed[0] * per_frame, placed[1] * per_frame
                # A word `share_the_gap` placed was never heard by the model: its score
                # is the floor, as an unplaced word's always was.
                marks = heard.get(index, [SCORE_FLOOR])
                clock = end
                out.append((start, end, sum(marks) / len(marks)))
            else:
                out.append((clock, clock, SCORE_FLOOR))
        return out
