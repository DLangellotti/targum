"""Cross-lingual sentence embeddings.

The model is not imported or downloaded until an alignment actually runs, and it lands
in the same managed directory as the language models so `targum models` can list and
remove it.
"""

from __future__ import annotations

import contextlib
import io
import logging
import os
from collections.abc import Sequence
from typing import Any

from ..errors import TargumError
from ..paths import ensure, model_dir

# LaBSE is trained for exactly this job, bitext mining across 109 languages including
# Hebrew and Russian. The e5 models are smaller and worth trying on a given pair.
DEFAULT_MODEL = "sentence-transformers/LaBSE"
ALTERNATIVES = ("intfloat/multilingual-e5-small", "intfloat/multilingual-e5-base")

MISSING = (
    "Alignment needs the embedding model, which is not installed.",
    "uv tool install 'targum[align]'  (or: pip install 'targum[align]')",
)


def embeddings_dir() -> Any:
    return ensure(model_dir() / "embeddings")


def is_downloaded(model: str = DEFAULT_MODEL) -> bool:
    # sentence-transformers stores a hub cache: models--<org>--<name>.
    folder = embeddings_dir() / ("models--" + model.replace("/", "--"))
    return folder.is_dir() and any(folder.rglob("*.safetensors")) or any(folder.rglob("*.bin"))


def downloaded_models() -> list[str]:
    root = embeddings_dir()
    if not root.is_dir():
        return []
    return sorted(
        child.name.removeprefix("models--").replace("--", "/")
        for child in root.iterdir()
        if child.is_dir() and child.name.startswith("models--")
    )


def model_size(model: str = DEFAULT_MODEL) -> int:
    folder = embeddings_dir() / ("models--" + model.replace("/", "--"))
    if not folder.is_dir():
        return 0
    return sum(f.stat().st_size for f in folder.rglob("*") if f.is_file())


class SentenceTransformerEncoder:
    """Similarity between two lists of sentences, in any pair of supported languages."""

    def __init__(self, model: str = DEFAULT_MODEL, *, batch_size: int = 64) -> None:
        self.model = model
        self.batch_size = batch_size
        self._encoder: Any = None

    @property
    def name(self) -> str:
        return self.model

    def encoder(self) -> Any:
        if self._encoder is not None:
            return self._encoder
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise TargumError(*MISSING) from exc

        # Keep downloads inside targum's model directory rather than a global cache,
        # and keep the loader's progress bars and hub notices off the CLI's output.
        os.environ.setdefault("HF_HOME", str(embeddings_dir()))
        os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
        os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
        for noisy in ("transformers", "sentence_transformers", "huggingface_hub"):
            logging.getLogger(noisy).setLevel(logging.ERROR)
        try:
            with (
                contextlib.redirect_stdout(io.StringIO()),
                contextlib.redirect_stderr(io.StringIO()),
            ):
                self._encoder = SentenceTransformer(self.model, cache_folder=str(embeddings_dir()))
        except Exception as exc:
            raise TargumError(
                f"Could not load the embedding model {self.model}.", str(exc)
            ) from exc
        return self._encoder

    def similarity(self, source: Sequence[str], target: Sequence[str]) -> list[list[float]]:
        if not source or not target:
            return [[] for _ in source]
        model = self.encoder()
        vectors_source = model.encode(
            list(source),
            batch_size=self.batch_size,
            normalize_embeddings=True,
            show_progress_bar=False,
            convert_to_numpy=True,
        )
        vectors_target = model.encode(
            list(target),
            batch_size=self.batch_size,
            normalize_embeddings=True,
            show_progress_bar=False,
            convert_to_numpy=True,
        )
        matrix: list[list[float]] = (vectors_source @ vectors_target.T).tolist()
        return matrix
