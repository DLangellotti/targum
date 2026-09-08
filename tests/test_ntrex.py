"""NTREX-128 as the recast eval's third reference: two plain files joined by line
number, and said out loud when they disagree (targum-internal#222)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from targum.chat import flores, ntrex
from targum.errors import TargumError


def test_the_files_are_joined_by_line_number_and_blank_lines_are_left_out() -> None:
    assert ntrex.parse("One.\n\nThree.\n", "אחת.\n\nשלוש.\n") == [
        flores.Pair("1", "One.", "אחת."),
        flores.Pair("3", "Three.", "שלוש."),
    ]


def test_files_of_different_lengths_are_refused_rather_than_zipped_short() -> None:
    """Off by one from the first gap onward, every score after it would be of the wrong
    sentence, and nothing in the numbers would show it."""
    with pytest.raises(TargumError, match="disagree on length"):
        ntrex.parse("One.\nTwo.\n", "אחת.\n")


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(ntrex, "root", lambda: tmp_path / "gold")
    return tmp_path / "gold"


class Answer:
    def __init__(self, text: str) -> None:
        self.text = text

    def raise_for_status(self) -> None:
        return None


def test_the_fetch_takes_the_source_english_and_the_hebrew_reference_plainly(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    asked: list[str] = []

    def get(url: str, **kwargs: object) -> Answer:
        asked.append(url)
        assert "headers" not in kwargs, "NTREX is not gated: no token travels"
        return Answer("One.\n" if "eng" in url else "אחת.\n")

    monkeypatch.setattr("httpx.get", get)
    assert ntrex.fetch() == 2
    assert [url.rsplit("/", 1)[1] for url in asked] == [
        "newstest2019-src.eng.txt",
        "newstest2019-ref.heb.txt",
    ], "the source English, not one of the three English references"
    assert ntrex.available()
    assert ntrex.load() == [flores.Pair("1", "One.", "אחת.")]
    assert ntrex.fetch() == 2 and len(asked) == 2, "files already here are left alone"


def test_loading_before_fetching_names_the_command(home: Path) -> None:
    with pytest.raises(TargumError) as refused:
        ntrex.load()
    assert refused.value.hint == "Run: targum models fetch ntrex"


def test_the_eval_draws_ntrex_rows_under_its_own_corpus_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spec = importlib.util.spec_from_file_location(
        "eval_recast", Path(__file__).parent.parent / "scripts" / "eval_recast.py"
    )
    assert spec is not None and spec.loader is not None
    eval_recast = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(eval_recast)

    monkeypatch.setattr(ntrex, "load", lambda: [flores.Pair("4", "Four.", "ארבע.")])
    assert eval_recast.reference_rows("ntrex", None, "devtest", None) == [
        {"id": "4", "en": "Four.", "he": "ארבע."}
    ]
    assert eval_recast.CORPUS["ntrex"] == "ntrex-128"
