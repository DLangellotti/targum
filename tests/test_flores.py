"""FLORES+ as the recast eval's second reference: fetched with a token, joined on its own
ids, and used for exactly one thing (targum-internal#221)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from targum.chat import flores
from targum.errors import TargumError


def a_file(rows: list[tuple[str, str]]) -> str:
    return "\n".join(
        json.dumps({"id": key, "text": text}, ensure_ascii=False) for key, text in rows
    )


def test_the_two_files_are_joined_on_the_id_in_the_english_order() -> None:
    english = a_file([("2", "The cat sat."), ("1", "It rained."), ("3", "Alone.")])
    hebrew = a_file([("1", "ירד גשם."), ("2", "החתול ישב."), ("9", "בלי אנגלית.")])
    assert flores.parse(english, hebrew) == [
        flores.Pair("2", "The cat sat.", "החתול ישב."),
        flores.Pair("1", "It rained.", "ירד גשם."),
    ]


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(flores, "root", lambda: tmp_path / "gold")
    for name in flores.TOKEN_VARIABLES:
        monkeypatch.delenv(name, raising=False)
    return tmp_path / "gold"


def test_without_a_token_the_fetch_stops_and_says_where_to_click(home: Path) -> None:
    """A 401 reported as a network fault sends somebody to check their connection. The
    dataset is gated, and the fetch says so before asking anything."""
    with pytest.raises(TargumError) as refused:
        flores.fetch()
    assert "HF_TOKEN" in (refused.value.hint or "")
    assert flores.CONDITIONS in (refused.value.hint or "")
    assert not home.exists() or not list(home.iterdir())


class Answer:
    def __init__(self, status_code: int, text: str = "") -> None:
        self.status_code = status_code
        self.text = text


def test_the_fetch_carries_the_token_writes_both_halves_and_is_idempotent(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HF_TOKEN", "hf_test")
    asked: list[tuple[str, str]] = []

    def get(url: str, headers: dict[str, str], **_: object) -> Answer:
        asked.append((url, headers["Authorization"]))
        return Answer(200, a_file([("1", "a" if "eng" in url else "א")]))

    monkeypatch.setattr("httpx.get", get)
    assert flores.fetch() == 2
    assert [auth for _url, auth in asked] == ["Bearer hf_test"] * 2
    assert {url.rsplit("/", 1)[1] for url, _auth in asked} == {"eng_Latn.jsonl", "heb_Hebr.jsonl"}
    assert all("/devtest/" in url for url, _auth in asked)
    assert flores.available()
    assert flores.load() == [flores.Pair("1", "a", "א")]

    monkeypatch.delenv("HF_TOKEN")
    assert flores.fetch() == 2, "files already here are left alone, and no token is needed"
    assert len(asked) == 2


def test_a_token_the_dataset_has_not_been_granted_to_is_said_as_such(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HUGGINGFACE_HUB_TOKEN", "hf_other")
    monkeypatch.setattr("httpx.get", lambda *_a, **_k: Answer(401))
    with pytest.raises(TargumError) as refused:
        flores.fetch()
    assert "accept the conditions" in (refused.value.hint or "")
    assert not flores.available()


def test_a_split_that_does_not_exist_is_refused_by_name(home: Path) -> None:
    with pytest.raises(TargumError, match="No such FLORES\\+ split"):
        flores.fetch(splits=("train",))


def test_loading_before_fetching_names_the_command(home: Path) -> None:
    with pytest.raises(TargumError) as refused:
        flores.load()
    assert refused.value.hint == "Run: targum models fetch flores"


def test_the_eval_draws_flores_rows_in_the_pools_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    """The rest of `eval_recast.py` does not know which reference it scores against, and
    the long news sentences are capped wider than Tatoeba's, or the split would be its
    short tenth."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "eval_recast", Path(__file__).parent.parent / "scripts" / "eval_recast.py"
    )
    assert spec is not None and spec.loader is not None
    eval_recast = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(eval_recast)

    short = flores.Pair("7", "Short.", "קצר.")
    long = flores.Pair("8", "Long.", " ".join(["מילה"] * 31))
    monkeypatch.setattr(flores, "load", lambda split: [short, long])
    rows = eval_recast.reference_rows("flores", None, "devtest", None)
    assert rows == [{"id": "7", "en": "Short.", "he": "קצר."}]
    assert eval_recast.reference_rows("flores", None, "devtest", 40) == [
        {"id": "7", "en": "Short.", "he": "קצר."},
        {"id": "8", "en": "Long.", "he": long.he},
    ]
    assert eval_recast.CORPUS["flores"] == "flores-plus"
