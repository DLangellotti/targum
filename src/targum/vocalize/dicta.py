"""DICTA's menaked, for the vowel points on modern Hebrew (targum-internal#148).

`dictabert-large-char-menaked` is a character-level BERT fine-tuned to add nikkud, CC BY
4.0 on its card, 1.2 GB of weights fetched from Hugging Face and never vendored. Measured
on two held-out sets before it was let near a reader (`scripts/measure_pointing.py`,
`evals/ledger.jsonl`, stage `vocalize`): on DICTA's own Wikipedia test corpus it is 0.969
to Nakdimon's 0.960 on vowels per letter and 0.890 to 0.854 on exact words; on pointed
prose and poetry from Project Ben-Yehuda, by authors neither model was trained on, 0.906
to 0.893 and 0.700 to 0.677. It writes the qamats qatan (U+05C7), which Nakdimon never
does and which phonikud needs to say כָּל as `kol`. It emits no stress mark; #132 owns that.

**Its card says it is not for biblical, rabbinic or premodern Hebrew, nor for poetry.**
Scripture and the pinned editions never reach any model, and `vocalize.for_source` keeps
the rabbinic and medieval shelves on Nakdimon. The revival shelf goes to the menaked
because that is what the Ben-Yehuda measurement was of, and it won there.

**Two things the model card gets wrong that a wrapper has to get right**, both found by
the measurement and both pinned by test:

- Under transformers 5 the card's `AutoTokenizer.from_pretrained` rebuilds a word-level
  BERT tokenizer from `vocab.txt`, hands the model one `[UNK]` per Hebrew word, and the
  model points nothing. The model's own `tokenizer.json` is the character tokenizer it
  was trained with, and that is what is loaded here.
- The card's `predict` walks the tokens and copies the input slice each one covers, so a
  character the tokenizer NFKC-expands is written once per piece: `…` came back as
  `………`, and 24 of 250 Ben-Yehuda lines failed the skeleton check for an ellipsis. Here
  the *input* is walked and each character looks its token up, so every character is
  emitted exactly once, and the skeleton check in `vocalize/base.py` still runs on every
  output afterwards, as it does on Nakdimon's.

A letter the model calls a mater lectionis is kept and left bare — the card's
`mark_matres_lectionis` with nothing to mark it by — which is what makes the letters come
back. That was the whole objection to this model family, answered.

The weights live beside the annotator's under `HF_HOME`, come down through `targum
models fetch menaked` (or `fetch he`, with the annotator's), and are never fetched in the
middle of a build: a machine without them points with Nakdimon and says so.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from ..errors import TargumError
from ..models import Segment
from ..paths import model_dir
from .base import LETTERS

LOG = logging.getLogger(__name__)

#: Named in full because the name rides into every vocalization and onto the credit.
MODEL = "dicta-il/dictabert-large-char-menaked"
CREDIT = "DICTA"
LICENCE = "CC BY 4.0"
LICENCE_URL = "https://creativecommons.org/licenses/by/4.0/"
MODEL_URL = f"https://huggingface.co/{MODEL}"

#: What the model's head answers for a letter it reads as a mater lectionis.
MAT_LECT = "<MAT_LECT>"
#: The model's own ceiling, characters plus the two sentinel tokens. A segment past it
#: is truncated by the tokenizer and its tail comes back bare; the letters are still
#: all there, so the skeleton holds.
MAX_CHARS = 2048

#: Loaded once per process and shared, the way the annotator's weights are: a rebuild
#: that points a hundred texts loads 1.2 GB once.
_LOADED: dict[str, tuple[Any, Any]] = {}


def hub_root() -> Path:
    """Where the Hugging Face cache lives: beside the language models, as the annotator
    keeps its own, so one directory is the whole of what a box has to be given."""
    return model_dir() / "hf"


def snapshot_dir() -> Path:
    return hub_root() / "hub" / f"models--{MODEL.replace('/', '--')}" / "snapshots"


def downloaded() -> bool:
    """Whether the weights and the tokenizer are on disk. A filesystem question, asked
    without importing anything, because a build asks it for every Hebrew text."""
    snapshots = snapshot_dir()
    return any(snapshots.glob("*/model.safetensors")) and any(snapshots.glob("*/tokenizer.json"))


def size() -> int:
    """Bytes on disk, for the fetch command to say what it brought."""
    return sum(path.stat().st_size for path in snapshot_dir().rglob("*") if path.is_file())


def assemble(
    text: str,
    offsets: Sequence[tuple[int, int]],
    nikud: Sequence[int],
    shin: Sequence[int],
    classes: Sequence[str],
    shin_classes: Sequence[str],
) -> str:
    """The pointed text from the model's per-token answers, walking the input.

    `offsets[i]` is the span of `text` that token `i` covers; a character-sized span is
    a letter with an answer, anything else — the sentinels, an expanded character's
    extra pieces — has none. Every character of `text` is written exactly once, whatever
    the tokenizer did to it, and a letter with no token (past the truncation ceiling) is
    written bare.
    """
    token_of: dict[int, int] = {}
    for token, (start, end) in enumerate(offsets):
        if end - start == 1:
            token_of.setdefault(start, token)
    out: list[str] = []
    for at, char in enumerate(text):
        out.append(char)
        index = token_of.get(at)
        if index is None or ord(char) not in LETTERS:
            continue
        if char == "ש":
            out.append(shin_classes[shin[index]])
        marks = classes[nikud[index]]
        out.append("" if marks == MAT_LECT else marks)
    return "".join(out)


def infer(
    model: Any, tokenizer: Any, text: str
) -> tuple[list[tuple[int, int]], list[int], list[int]]:
    """One forward pass: each token's span, and the head's two answers for it."""
    inputs = tokenizer([text], return_tensors="pt", truncation=True, return_offsets_mapping=True)
    offsets: list[tuple[int, int]] = [
        (int(start), int(end)) for start, end in inputs.pop("offset_mapping")[0].tolist()
    ]
    logits = model(**{k: v.to(model.device) for k, v in inputs.items()}, return_dict=True).logits
    return (
        offsets,
        logits.nikud_logits[0].argmax(-1).tolist(),
        logits.shin_logits[0].argmax(-1).tolist(),
    )


def point(model: Any, tokenizer: Any, text: str) -> str:
    offsets, nikud, shin = infer(model, tokenizer, text)
    return assemble(
        text, offsets, nikud, shin, model.config.nikud_classes, model.config.shin_classes
    )


class DictaVocalizer:
    # 1, and the name is the cache key: a text pointed by Nakdimon names Nakdimon, so
    # the swap reaches it on the next build or `rebuild --words` — free of money, since
    # the model runs here, but not of time: about 0.3 s a sentence on a box without a
    # GPU. CLAUDE.md: a rename is a scheduled operation, not a side effect of a deploy.
    name = "dicta/menaked/1"

    def __init__(self, *, auto_download: bool = False) -> None:
        #: Off by default, and on only for `targum models fetch`. A build never reaches
        #: for the network: a machine without the weights points with Nakdimon instead.
        self.auto_download = auto_download

    @property
    def model(self) -> str | None:
        return MODEL

    def available(self) -> tuple[bool, str]:
        if self.auto_download or downloaded():
            return True, ""
        return False, f"{MODEL} is not downloaded. Run: targum models fetch menaked"

    def load(self) -> tuple[Any, Any]:
        """The weights and the character tokenizer, loaded once and kept.

        `HF_HOME` rather than `cache_dir`, for the annotator's reason: the code that
        `trust_remote_code` fetches lands beside the weights rather than in the home
        directory. Offline unless this is the fetch, so a build on a box never finds
        itself downloading a gigabyte halfway through a job.
        """
        if MODEL in _LOADED:
            return _LOADED[MODEL]
        os.environ.setdefault("HF_HOME", str(hub_root()))
        try:
            import torch
            from huggingface_hub import hf_hub_download
            from tokenizers import Tokenizer
            from transformers import AutoModel, PreTrainedTokenizerFast
        except ImportError as missing:  # pragma: no cover — a broken install only
            raise TargumError(
                "Pointing with DICTA needs transformers, which is not installed.",
                "pip install 'transformers>=4.40'",
            ) from missing

        offline = not self.auto_download
        try:
            tokenizer = PreTrainedTokenizerFast(  # type: ignore[no-untyped-call]
                tokenizer_object=Tokenizer.from_file(
                    hf_hub_download(MODEL, "tokenizer.json", local_files_only=offline)
                ),
                model_max_length=MAX_CHARS,
                cls_token="[CLS]",
                sep_token="[SEP]",
                pad_token="[PAD]",
                unk_token="[UNK]",
                mask_token="[MASK]",
            )
            model = AutoModel.from_pretrained(
                MODEL, trust_remote_code=True, local_files_only=offline
            )
        except Exception as error:  # noqa: BLE001 — the loader raises whatever it likes
            raise TargumError(
                f"Could not load {MODEL}.",
                str(error) if self.auto_download else "Run: targum models fetch menaked",
            ) from error
        model.eval()
        torch.set_grad_enabled(False)
        _LOADED[MODEL] = (model, tokenizer)
        return _LOADED[MODEL]

    def vocalize(self, segments: list[Segment], language: str) -> dict[str, str]:
        import torch

        model, tokenizer = self.load()
        out: dict[str, str] = {}
        failed = 0
        with torch.inference_mode():
            for segment in segments:
                text = segment.text
                if not text.strip():
                    continue
                # Per sentence, for Nakdimon's reason: one sentence a model dislikes
                # must not cost the document its vowels.
                try:
                    out[segment.id] = point(model, tokenizer, text)
                except Exception as error:  # noqa: BLE001 - a third-party model, not our code
                    failed += 1
                    LOG.debug("no vowel points for %s: %s", segment.id, error)
        if failed:
            LOG.warning(
                "the diacritizer could not point %d of %d sentences; the rest are pointed",
                failed,
                len(segments),
            )
        return out


def fetch(notify: Callable[[str], None] | None = None) -> int:
    """Bring the weights down, or find them here. Returns the bytes on disk.

    Idempotent: `from_pretrained` finds a complete snapshot and fetches nothing. The
    model is loaded to prove the download whole, then left for the process to drop.
    """
    say = notify or (lambda _message: None)
    if downloaded():
        say(f"{MODEL} is already downloaded.")
        return size()
    say(f"Fetching {MODEL}, about 1.2 GB…")
    DictaVocalizer(auto_download=True).load()
    _LOADED.pop(MODEL, None)
    return size()
