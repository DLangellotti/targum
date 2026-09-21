"""The Russian side of the Tatoeba pool, and the eval reading it (targum-internal#286).

#222 concluded that Tatoeba, not NTREX, is the recast's yardstick, so the Russian number
has to be taken here. Tatoeba's own `heb-rus` link file supplies the pairing; nothing is
lemmatized again, because every row that matches was lemmatized when the pool was built.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


@pytest.fixture(scope="module")
def ru():  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location(
        "tatoeba_russian", Path(__file__).parent.parent / "scripts" / "tatoeba_russian.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def eval_recast():  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location(
        "eval_recast", Path(__file__).parent.parent / "scripts" / "eval_recast.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_link_file_is_read_hebrew_first(ru, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    """The file is named for its direction and the Hebrew is the first column. Verified
    on the real export rather than assumed: of 11,516 rows, 11,515 have their *second*
    column in the Russian sentences and none has its first."""
    path = tmp_path / "heb-rus_links.tsv"
    path.write_text("100\t900\n100\t901\n101\t902\n", encoding="utf-8")
    assert ru.linked(path) == {"100": ["900", "901"], "101": ["902"]}


def test_only_the_wanted_russian_sentences_are_held(ru, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    """The export is 1.2 million rows and about ten thousand are linked to Hebrew.
    Holding all of it is what a previous pool run learned not to do on an 8 GB laptop."""
    path = tmp_path / "rus_sentences_detailed.tsv"
    path.write_text(
        "900\trus\tОдин\tanna\t2008\t2012\n"
        "901\trus\tДва\tboris\t2008\t2012\n"
        "902\tdeu\tDrei\tclara\t2008\t2012\n"
        "903\trus\t   \tdmitri\t2008\t2012\n",
        encoding="utf-8",
    )
    held = ru.russian(path, {"900", "902", "903"})
    assert held == {"900": ("Один", "anna")}, "not asked for, not Russian, and blank are all out"


def test_the_shortest_linked_sentence_wins(ru) -> None:  # type: ignore[no-untyped-def]
    said = {"900": ("Длинное предложение здесь", "anna"), "901": ("Да.", "boris")}
    assert ru.shortest(["900", "901"], said) == ("Да.", "boris")
    assert ru.shortest(["999"], said) is None, "a link with no sentence is no sentence"
    assert ru.shortest([], said) is None


def a_pool(path: Path) -> Path:
    rows = [
        # Hebrew translated out of English, with a Russian sentence too
        {
            "id": 1,
            "he": "אתה צבוע",
            "en": "You hypocrite",
            "ru": "Ты лицемер",
            "from_english": True,
        },
        # written in Hebrew first, so not an English original — but it has a Russian
        {"id": 2, "he": "שלום לך", "en": "Hello to you", "ru": "Привет", "from_english": False},
        # English original, no Russian
        {"id": 3, "he": "בוקר טוב", "en": "Good morning", "from_english": True},
        # too long on the Hebrew side
        {"id": 4, "he": " ".join(["מילה"] * 13), "en": "x", "ru": "у", "from_english": True},
    ]
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8"
    )
    return path


def test_a_russian_run_reads_ru_and_ignores_from_english(  # type: ignore[no-untyped-def]
    eval_recast, tmp_path: Path
) -> None:
    """`from_english` says the *Hebrew* was translated out of English. That is the right
    guard for an English turn and says nothing about a Russian one, so a sentence written
    in Hebrew first is still a fair thing to ask a Russian speaker to have written."""
    rows = eval_recast.pool_rows(a_pool(tmp_path / "pool.jsonl"), source="ru")
    assert [row["id"] for row in rows] == [1, 2], "the long one and the one with no Russian are out"
    assert rows[0]["said"] == "Ты лицемер"
    assert rows[1]["said"] == "Привет", "written in Hebrew first, and still usable"


def test_an_english_run_still_requires_an_english_original(  # type: ignore[no-untyped-def]
    eval_recast, tmp_path: Path
) -> None:
    """Adding a source language must not quietly widen what the English run draws."""
    rows = eval_recast.pool_rows(a_pool(tmp_path / "pool.jsonl"), source="en")
    assert [row["id"] for row in rows] == [1, 3]
    assert all(row["said"] for row in rows)


def test_the_russian_tatoeba_run_gets_its_own_ledger_line(eval_recast) -> None:  # type: ignore[no-untyped-def]
    assert eval_recast.corpus_of("tatoeba", "en") == "tatoeba"
    assert eval_recast.corpus_of("tatoeba", "ru") == "tatoeba-ru"
