"""`scripts/repair_unpunctuated.py` (targum-internal#727): a one-off that spends outside
`Library.claim`, so it touches only the parts it is told to and says what it spent."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

from targum.ingest.audio import refined_path
from targum.ingest.subtitles import FRESH
from targum.transcribe.models import Refined, RefinedParagraph, Word, write
from targum.usage import Usage

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "repair_unpunctuated.py"


def load() -> Any:
    spec = importlib.util.spec_from_file_location("repair_unpunctuated", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def old_part(text: str) -> Refined:
    words = [Word(text=t, start=n * 1.0, end=n * 1.0 + 0.5) for n, t in enumerate(text.split())]
    return Refined(
        refiner="subtitles/1",
        provider="subtitles",
        language="he",
        paragraphs=[RefinedParagraph(text=text, words=words)],
    )


def test_redraw_touches_only_the_named_parts(tmp_path: Path) -> None:
    """qa-claude on #1238: `--redraw` redrew every `subtitles/1` part in the folder, so a
    part not rebuilt kept English keyed to paragraphs it no longer had."""
    script = load()
    for number in (1, 2, 3):
        write(refined_path(tmp_path / "audio", number), old_part("שלום עולם. מה שלומך."))
    fresh = script.redrawn(tmp_path, [1, 3, 9])
    assert sorted(fresh) == [1, 3], "a named part with no file is skipped, an unnamed one left"
    assert all(part.refiner == FRESH for part in fresh.values())
    script.write_redrawn(tmp_path, fresh)
    from targum.transcribe.models import load as read

    untouched = read(Refined, refined_path(tmp_path / "audio", 2))
    assert untouched is not None and untouched.refiner == "subtitles/1"
    assert (tmp_path / "audio" / "refined.pre727" / "part-002.json").exists()


def test_the_receipt_says_what_was_really_spent() -> None:
    """It spends outside `Library.claim`, so its last lines are what goes on #727."""
    script = load()
    spent = Usage()
    spent.add("claude-sonnet-5", 12_000, 3_000)
    lines = script.receipt(spent)
    assert lines[0] == f"spent ${spent.cost():.4f} outside Library.claim, calls: 1"
    assert spent.cost() > 0
    assert any("claude-sonnet-5: 12000 tokens in, 3000 out" in line for line in lines)
    assert lines[-1] == "record this on targum-internal#727"
    assert script.receipt(Usage())[0] == "spent $0.0000 outside Library.claim, calls: 0"
