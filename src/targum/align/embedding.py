"""Cross-lingual sentence embeddings.

The model is not imported or downloaded until an alignment actually runs, and it lands
in the same managed directory as the language models so `targum models` can list and
remove it.

**Read from the file, not loaded into memory** (2026-09-18). LaBSE through
sentence-transformers took 2.2 GB of the process: 1.9 GB of weights copied out of the
file, 385M of its 471M parameters a vocabulary table of 501,153 rows of which one text
touches a few thousand, and 400 MB more for the tokenizer that wrapper builds. The box
never had the `align` extra, so every catalogue row carrying a published translation
failed there; installing it would have put that 2.2 GB beside DICTA on the box whose
out-of-memory kills were already DICTA's. So the weights are mapped from the
safetensors file where they lie — pages the kernel reads in as a sentence touches them
and drops again under pressure, rather than memory the process holds — and the
tokenizer is the Rust one without the transformers wrapper: 118 MB, the same ids. The
head that sentence-transformers adds to BERT is three steps (the first token, a dense
layer under tanh, unit length) and is applied here. Measured on the laptop: 734 MB peak
against 2.2 GB, the vectors within 2.2e-7 of sentence-transformers' own, and so the
same `name` — every alignment already cached stays good.

Nothing here needs a package targum does not already carry: torch comes with Stanza,
and transformers with it brings `tokenizers`, `safetensors` and `huggingface_hub`.
"""

from __future__ import annotations

import json
import struct
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from ..errors import TargumError
from ..paths import ensure, model_dir

# LaBSE is trained for exactly this job, bitext mining across 109 languages including
# Hebrew and Russian.
DEFAULT_MODEL = "sentence-transformers/LaBSE"

#: The files the encoder reads. The repository also holds a pytorch_model.bin and a
#: TensorFlow copy of the same weights, which would treble the download for nothing.
FILES = (
    "config.json",
    "model.safetensors",
    "tokenizer.json",
    "modules.json",
    "sentence_bert_config.json",
    "1_Pooling/config.json",
    "2_Dense/config.json",
    "2_Dense/model.safetensors",
)


def embeddings_dir() -> Any:
    return ensure(model_dir() / "embeddings")


def _folder(model: str) -> Path:
    # The hub's cache layout, which sentence-transformers used too: models--<org>--<name>.
    return Path(embeddings_dir()) / ("models--" + model.replace("/", "--"))


def is_downloaded(model: str = DEFAULT_MODEL) -> bool:
    return _snapshot(model) is not None


def _snapshot(model: str) -> Path | None:
    """The downloaded copy holding every file in `FILES`, or None."""
    snapshots = _folder(model) / "snapshots"
    if not snapshots.is_dir():
        return None
    for snapshot in sorted(snapshots.iterdir()):
        if all((snapshot / name).is_file() for name in FILES):
            return snapshot
    return None


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
    folder = _folder(model)
    if not folder.is_dir():
        return 0
    # The hub keeps one blob per file and a tree of symlinks pointing at it, so walking
    # the folder naively counts every weight twice: 3.8 GB reported for the 1.8 GB
    # download the fetch command promises. Count each inode once, and never the links.
    seen: set[tuple[int, int]] = set()
    total = 0
    for path in folder.rglob("*"):
        if path.is_symlink() or not path.is_file():
            continue
        info = path.stat()
        key = (info.st_dev, info.st_ino)
        if key in seen:
            continue
        seen.add(key)
        total += info.st_size
    return total


def fetch(model: str = DEFAULT_MODEL) -> Path:
    """The model's folder, downloading what is missing of it first."""
    found = _snapshot(model)
    if found is not None:
        return found
    try:
        from huggingface_hub import snapshot_download

        path = snapshot_download(model, cache_dir=str(embeddings_dir()), allow_patterns=list(FILES))
    except Exception as exc:
        raise TargumError(f"Could not download the embedding model {model}.", str(exc)) from exc
    return Path(path)


def mapped(path: Path) -> dict[str, Any]:
    """Every tensor in a safetensors file, backed by the file rather than by memory.

    Copy-on-write, so a tensor is writable as torch expects and the file is never
    touched; nothing here writes to a weight, so no page is ever copied.
    """
    import numpy as np
    import torch

    with path.open("rb") as handle:
        (length,) = struct.unpack("<Q", handle.read(8))
        header = json.loads(handle.read(length))
    kinds = {"F32": np.float32, "F16": np.float16, "BF16": np.uint16, "I64": np.int64}
    out: dict[str, Any] = {}
    for name, info in header.items():
        if name == "__metadata__":
            continue
        if info["dtype"] not in kinds:
            raise TargumError(f"Cannot read {info['dtype']} weights in {path.name}.", "")
        start, _ = info["data_offsets"]
        shape = tuple(info["shape"])
        array = np.memmap(
            path, dtype=kinds[info["dtype"]], mode="c", offset=8 + length + start, shape=shape
        )
        tensor = torch.from_numpy(array)
        out[name] = tensor.view(torch.bfloat16) if info["dtype"] == "BF16" else tensor
    return out


class MappedEncoder:
    """Similarity between two lists of sentences, in any pair of supported languages.

    Reads a sentence-transformers model of LaBSE's shape — BERT, the first token, an
    optional dense layer, unit length — and refuses any other rather than embedding
    with the wrong head.
    """

    def __init__(self, model: str = DEFAULT_MODEL, *, batch_size: int = 64) -> None:
        self.model = model
        self.batch_size = batch_size
        self._loaded: tuple[Any, Any, Any] | None = None

    @property
    def name(self) -> str:
        # The model's own name, as it was when sentence-transformers read it: the vectors
        # are the same, so the alignments cached under this name are too.
        return self.model

    def load(self) -> tuple[Any, Any, Any]:
        """The tokenizer, the BERT and the head, reading them the first time."""
        if self._loaded is not None:
            return self._loaded
        folder = fetch(self.model)
        try:
            self._loaded = self._read(folder)
        except TargumError:
            raise
        except Exception as exc:
            raise TargumError(
                f"Could not load the embedding model {self.model}.", str(exc)
            ) from exc
        return self._loaded

    def _read(self, folder: Path) -> tuple[Any, Any, Any]:
        import torch
        from tokenizers import Tokenizer
        from transformers import BertConfig, BertModel

        modules = [m["type"].rsplit(".", 1)[-1] for m in _json(folder / "modules.json")]
        pooling = _json(folder / "1_Pooling" / "config.json")
        if modules[:2] != ["Transformer", "Pooling"] or not pooling.get("pooling_mode_cls_token"):
            raise TargumError(
                f"{self.model} is not shaped like LaBSE.",
                "The aligner reads a BERT whose sentence is its first token.",
            )

        config = BertConfig.from_pretrained(folder)
        # Built on the meta device so that nothing is allocated for weights that are
        # about to be replaced by the file's own.
        with torch.device("meta"):
            bert = BertModel(config, add_pooling_layer=False)  # type: ignore[no-untyped-call]
        bert.load_state_dict(mapped(folder / "model.safetensors"), strict=False, assign=True)
        # The two buffers the checkpoint does not carry, made here as BERT makes them.
        positions = config.max_position_embeddings
        bert.embeddings.register_buffer(
            "position_ids", torch.arange(positions).expand((1, -1)), persistent=False
        )
        bert.embeddings.register_buffer(
            "token_type_ids", torch.zeros((1, positions), dtype=torch.long), persistent=False
        )
        left = [name for name, t in [*bert.named_parameters(), *bert.named_buffers()] if t.is_meta]
        if left:
            raise TargumError(f"{self.model} is missing weights.", ", ".join(left[:5]))
        bert.eval()  # type: ignore[no-untyped-call]

        head = None
        if "Dense" in modules:
            weights = mapped(folder / "2_Dense" / "model.safetensors")
            head = (weights["linear.weight"], weights["linear.bias"])

        tokenizer = Tokenizer.from_file(str(folder / "tokenizer.json"))
        longest = _json(folder / "sentence_bert_config.json").get("max_seq_length") or 256
        tokenizer.enable_truncation(int(longest))
        tokenizer.enable_padding(pad_id=tokenizer.token_to_id("[PAD]") or 0, pad_token="[PAD]")
        return tokenizer, bert, head

    def encode(self, sentences: Sequence[str]) -> Any:
        """Unit vectors, one row a sentence, in the order given."""
        import numpy as np
        import torch

        tokenizer, bert, head = self.load()
        # Longest first and batched by length, as sentence-transformers did: a batch pads
        # to its longest sentence, so mixing lengths spends the time on padding.
        order = sorted(range(len(sentences)), key=lambda i: -len(sentences[i]))
        rows: list[Any] = [None] * len(sentences)
        with torch.inference_mode():
            for start in range(0, len(order), self.batch_size):
                batch = order[start : start + self.batch_size]
                encoded = tokenizer.encode_batch([sentences[i] for i in batch])
                hidden = bert(
                    input_ids=torch.tensor([e.ids for e in encoded]),
                    attention_mask=torch.tensor([e.attention_mask for e in encoded]),
                    token_type_ids=torch.tensor([e.type_ids for e in encoded]),
                ).last_hidden_state[:, 0]
                if head is not None:
                    hidden = torch.tanh(hidden @ head[0].T + head[1])
                vectors = torch.nn.functional.normalize(hidden, dim=-1).numpy()
                for index, vector in zip(batch, vectors, strict=True):
                    rows[index] = vector
        return np.stack(rows)

    def similarity(self, source: Sequence[str], target: Sequence[str]) -> list[list[float]]:
        if not source or not target:
            return [[] for _ in source]
        matrix: list[list[float]] = (self.encode(source) @ self.encode(target).T).tolist()
        return matrix


def _json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))
