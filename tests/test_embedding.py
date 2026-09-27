"""The aligner's encoder, read from the file, against transformers reading the same weights.

A BERT of a few thousand parameters, written in LaBSE's layout, so the suite needs no
download: what is checked is that mapping the weights and applying the head by hand
gives the vectors the full load would, and that a model of any other shape is refused.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

torch = pytest.importorskip("torch")
transformers = pytest.importorskip("transformers")
tokenizers = pytest.importorskip("tokenizers")
safetensors_torch = pytest.importorskip("safetensors.torch")

from targum.align import embedding  # noqa: E402
from targum.errors import TargumError  # noqa: E402

WORDS = ["[PAD]", "[UNK]", "[CLS]", "[SEP]", "[MASK]", "light", "let", "there", "be"]
WORDS += ["אור", "יהי", "свет", "да", "будет", "luce", "sia", "la", ".", ",", "##s"]


def write_model(folder: Path, *, pooling: str = "cls") -> None:
    """A random BERT, a dense head and a WordPiece tokenizer, laid out as LaBSE is."""
    torch.manual_seed(7)
    config = transformers.BertConfig(
        vocab_size=len(WORDS),
        hidden_size=16,
        num_hidden_layers=2,
        num_attention_heads=2,
        intermediate_size=32,
        max_position_embeddings=64,
        # Wide, so that four sentences come out as four different vectors: at BERT's
        # own 0.02 a model this small maps everything to nearly the same one.
        initializer_range=1.0,
    )
    bert = transformers.BertModel(config, add_pooling_layer=False)
    folder.mkdir(parents=True)
    config.save_pretrained(folder)
    safetensors_torch.save_file(
        {k: v.contiguous() for k, v in bert.state_dict().items()}, folder / "model.safetensors"
    )
    (folder / "2_Dense").mkdir()
    dense = torch.nn.Linear(16, 16)
    safetensors_torch.save_file(
        {"linear.weight": dense.weight.data, "linear.bias": dense.bias.data},
        folder / "2_Dense" / "model.safetensors",
    )
    (folder / "2_Dense" / "config.json").write_text("{}")
    (folder / "1_Pooling").mkdir()
    (folder / "1_Pooling" / "config.json").write_text(
        json.dumps({"pooling_mode_cls_token": pooling == "cls"})
    )
    (folder / "sentence_bert_config.json").write_text(json.dumps({"max_seq_length": 32}))
    modules = ["Transformer", "Pooling", "Dense", "Normalize"]
    (folder / "modules.json").write_text(
        json.dumps([{"type": f"sentence_transformers.models.{m}"} for m in modules])
    )

    from tokenizers import Tokenizer, models, normalizers, pre_tokenizers, processors

    tokenizer = Tokenizer(models.WordPiece({w: i for i, w in enumerate(WORDS)}, unk_token="[UNK]"))
    tokenizer.normalizer = normalizers.BertNormalizer(lowercase=False)
    tokenizer.pre_tokenizer = pre_tokenizers.BertPreTokenizer()
    tokenizer.post_processor = processors.BertProcessing(("[SEP]", 3), ("[CLS]", 2))
    tokenizer.save(str(folder / "tokenizer.json"))


@pytest.fixture
def model(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setenv("TARGUM_MODEL_DIR", str(tmp_path / "models"))
    name = "test/tiny-labse"
    snapshot = embedding.embeddings_dir() / "models--test--tiny-labse" / "snapshots" / "one"
    write_model(snapshot)
    return name


def reference(folder: Path, sentences: list[str]) -> object:
    """What transformers makes of the same files, loaded the ordinary way."""
    from tokenizers import Tokenizer

    bert = transformers.BertModel.from_pretrained(folder, add_pooling_layer=False).eval()
    dense = safetensors_torch.load_file(folder / "2_Dense" / "model.safetensors")
    tokenizer = Tokenizer.from_file(str(folder / "tokenizer.json"))
    rows = []
    with torch.inference_mode():
        for sentence in sentences:
            ids = torch.tensor([tokenizer.encode(sentence).ids])
            first = bert(input_ids=ids).last_hidden_state[:, 0]
            vector = torch.tanh(first @ dense["linear.weight"].T + dense["linear.bias"])
            rows.append(torch.nn.functional.normalize(vector, dim=-1)[0])
    return torch.stack(rows).numpy()


def test_mapped_vectors_are_the_loaded_ones(model: str) -> None:
    import numpy as np

    sentences = ["let there be light .", "יהי אור", "да будет свет", "sia la luce , lights"]
    encoder = embedding.MappedEncoder(model, batch_size=3)
    got = encoder.encode(sentences)
    folder = embedding.fetch(model)
    want = reference(folder, sentences)
    # Batched and padded against one at a time, in a different order: the same vectors.
    assert abs(got - want).max() < 1e-5
    similarity = encoder.similarity(sentences[:2], sentences)
    assert abs(np.array(similarity) - want[:2] @ want.T).max() < 1e-5
    assert similarity[0][0] > max(similarity[0][1:]), "a sentence is nearest itself"


def test_the_weights_stay_in_the_file(model: str, monkeypatch: pytest.MonkeyPatch) -> None:
    handed: dict[str, object] = {}
    original = embedding.mapped

    def recording(path: Path) -> dict[str, object]:
        tensors = original(path)
        handed.update(tensors)
        return tensors

    monkeypatch.setattr(embedding, "mapped", recording)
    _, bert, _ = embedding.MappedEncoder(model).load()
    # The very memory the mapping handed over, not a copy of it: a load that copied
    # would hold the 1.5 GB table in the process, which is what this exists to avoid.
    table = bert.embeddings.word_embeddings.weight
    assert table.data_ptr() == handed["embeddings.word_embeddings.weight"].data_ptr()  # type: ignore[attr-defined]
    layer = bert.encoder.layer[0].attention.self.query.weight
    assert layer.data_ptr() == handed["encoder.layer.0.attention.self.query.weight"].data_ptr()  # type: ignore[attr-defined]


def test_the_name_is_the_model_so_cached_alignments_hold(model: str) -> None:
    assert embedding.MappedEncoder(model).name == model
    assert embedding.MappedEncoder().name == "sentence-transformers/LaBSE"


def test_a_model_of_another_shape_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TARGUM_MODEL_DIR", str(tmp_path / "models"))
    snapshot = embedding.embeddings_dir() / "models--test--mean" / "snapshots" / "one"
    write_model(snapshot, pooling="mean")
    with pytest.raises(TargumError, match="not shaped like LaBSE"):
        embedding.MappedEncoder("test/mean").load()


def test_a_partial_download_is_not_downloaded(model: str) -> None:
    assert embedding.is_downloaded(model)
    (embedding.fetch(model) / "tokenizer.json").unlink()
    assert not embedding.is_downloaded(model)
