"""NTREX-128 as the recast eval's third reference: two plain files joined by line
number, and said out loud when they disagree (targum-internal#222)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from targum.chat import ntrex
from targum.errors import TargumError


def test_the_files_are_joined_by_line_number_and_blank_lines_are_left_out() -> None:
    assert ntrex.parse("One.\n\nThree.\n", "אחת.\n\nשלוש.\n") == [
        ntrex.Line("1", "One.", "אחת."),
        ntrex.Line("3", "Three.", "שלוש."),
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
        if "eng" in url:
            return Answer("One.\n")
        if "rus" in url:
            return Answer("Один.\n")
        return Answer("Un.\n" if "fra" in url else "אחת.\n")

    monkeypatch.setattr("httpx.get", get)
    # Four since 2026-09-23: French joined as a *reference* end, where Russian is there
    # as a *source* (#286, #357). One file serves either, because every NTREX rendering
    # is of the same English line.
    assert ntrex.fetch() == 4
    assert [url.rsplit("/", 1)[1] for url in asked] == [
        "newstest2019-src.eng.txt",
        "newstest2019-ref.heb.txt",
        "newstest2019-ref.rus.txt",
        "newstest2019-ref.fra.txt",
    ], "the source English, not one of the three English references, and the rest beside it"
    assert ntrex.available() and ntrex.available("ru") and ntrex.complete()
    assert ntrex.load() == [ntrex.Line("1", "One.", "אחת.")]
    assert ntrex.load("ru") == [ntrex.Line("1", "Один.", "אחת.")], (
        "the Russian line against the Hebrew written for that same source line"
    )
    # The other end, named (#357): the English line against the French written for it.
    assert ntrex.load(into="fr") == [ntrex.Line("1", "One.", "Un.")]
    assert ntrex.fetch() == 4 and len(asked) == 4, "files already here are left alone"


def test_a_language_it_does_not_carry_is_refused_by_name(home: Path) -> None:
    """Yiddish is not among NTREX's 128, which is why `flores200.py` exists (#283)."""
    with pytest.raises(TargumError) as refused:
        ntrex.load(into="yi")
    assert "Yiddish" in str(refused.value) or "yi" in str(refused.value)
    assert "FLORES-200" in (refused.value.hint or "")


def test_a_language_is_never_scored_against_itself(home: Path) -> None:
    with pytest.raises(TargumError):
        ntrex.load("ru", into="ru")


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

    monkeypatch.setattr(
        ntrex, "load", lambda source="en", into="he": [ntrex.Line("4", "Four.", "ארבע.")]
    )
    assert eval_recast.reference_rows("ntrex", None, "devtest", None) == [
        {"id": "4", "said": "Four.", "he": "ארבע."}
    ]
    assert eval_recast.CORPUS["ntrex"] == "ntrex-128"


def test_a_russian_run_gets_its_own_ledger_line() -> None:
    """`evals.Row.key()` is (stage, corpus, metric), so a Russian run filed under
    `ntrex-128` would share a trend line with the English one and each would look like
    the other moving (targum-internal#286)."""
    spec = importlib.util.spec_from_file_location(
        "eval_recast", Path(__file__).parent.parent / "scripts" / "eval_recast.py"
    )
    assert spec is not None and spec.loader is not None
    eval_recast = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(eval_recast)

    assert eval_recast.corpus_of("ntrex", "en") == "ntrex-128"
    assert eval_recast.corpus_of("ntrex", "ru") == "ntrex-128-ru"
    assert eval_recast.corpus_of("ntrex", "en") != eval_recast.corpus_of("ntrex", "ru")


def test_the_length_refusal_names_the_source_language() -> None:
    with pytest.raises(TargumError, match="1 Russian lines"):
        ntrex.parse("Один.\n", "אחת.\nשתיים.\n", "ru")
