"""Forced alignment: a transcript the reader supplied, timed against their recording.

Local and unpaid — `ctc-forced-aligner` on the MMS alignment model, which covers Hebrew
through romanisation — because paying a transcriber by the minute to align a text you
already have inherits the transcriber's errors at every mismatch. Optional, like the
embedding aligner: without the extra installed the recording plays straight through,
which is the `_read_through` shape and not a failure.

Unpaid is not unencumbered. The aligner is CC BY-NC 4.0 and the model it fetches is in
Meta's MMS lineage, also NonCommercial, which is why this is an extra and never a
default. `LICENSING.md` names it. The algorithm is free; only the acoustic model is
encumbered, so swapping that model leaves this file's shape intact.
"""

from __future__ import annotations

import os
from pathlib import Path

from ..errors import TargumError
from ..paths import model_dir
from .spans import normalise

NAME = "ctc-mms-fa/1"

#: A word the aligner scored below this is trimmed from a window's edges; a part whose
#: mean score sits below the floor gets no spans at all. Measured against a real clip
#: at implementation of the supplied-text flow; conservative until then.
SCORE_FLOOR = -10.0
MATCH_FLOOR = -6.0


class CtcAligner:
    name = NAME

    def available(self) -> tuple[bool, str]:
        try:
            import ctc_forced_aligner  # noqa: F401
        except ImportError:
            return False, "uv sync --extra speech-align  (the forced aligner)"
        return True, self.name

    def align(
        self, audio: Path, words: list[str], language: str
    ) -> list[tuple[float, float, float]]:
        """One (start, end, score) per word, in seconds into the audio file.

        The model lands in the models directory like every other, so a box that ships
        models ships this one the same way.
        """
        usable, hint = self.available()
        if not usable:
            raise TargumError("The forced aligner is not installed.", hint)
        os.environ.setdefault("TORCH_HOME", str(model_dir()))
        import torch
        from ctc_forced_aligner import (
            generate_emissions,
            get_alignments,
            get_spans,
            load_alignment_model,
            load_audio,
            postprocess_results,
            preprocess_text,
        )

        device = "cpu"
        model, tokenizer = load_alignment_model(device, dtype=torch.float32)
        waveform = load_audio(str(audio), model.dtype, model.device)
        emissions, stride = generate_emissions(model, waveform)
        cleaned = [normalise(word) or "-" for word in words]
        tokens, text_starred = preprocess_text(
            " ".join(cleaned), romanize=True, language=language.split("-")[0]
        )
        segments, scores, blank = get_alignments(emissions, tokens, tokenizer)
        spans = get_spans(tokens, segments, blank)
        results = postprocess_results(text_starred, spans, stride, scores)
        return [
            (float(row["start"]), float(row["end"]), float(row.get("score") or 0.0))
            for row in results
        ]
