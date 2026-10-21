"""The script that drafts a Russian title for every catalogue text: how it is told to
name a book of the Tanakh (David, 2026-10-21). No model is called."""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path
from typing import Any

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "russian_titles.py"


def load_script() -> Any:
    spec = importlib.util.spec_from_file_location("russian_titles", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_a_book_is_named_in_the_interfaces_jewish_russian_spelling() -> None:
    prompt = load_script().TANAKH
    for name in ("Берейшит", "Теилим", "Млахим", "Диврей а-Ямим", "Коэлет", "Шмуэль I", "Иов"):
        assert name in prompt, name


def test_no_synodal_name_in_brackets_and_no_g_for_he() -> None:
    prompt = load_script().TANAKH
    assert not re.search(r"\([А-Яа-яЁё][^)]*\)", prompt), "no bracketed Synodal name"
    for synodal in ("Бытие", "Псалтирь", "Царств", "Паралипоменон", "Екклесиаст"):
        assert synodal not in prompt, synodal
    for old in ("Берешит", "Мелахим", "Теѓилим", "Коѓелет", "ѓа-ямим", "Теhилим"):
        assert old not in prompt, old
    assert "ѓ" not in prompt.replace("«ѓ»", "")
