"""The mail's English as notes in the Obsidian vault and back (scripts/mail_notes.py).

David, 2026-09-28: "give me a way to edit this text myself, in obsidian". Run against a
copy of the catalogue, so a test never writes the real one.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "mail_notes.py"
REAL = Path(__file__).resolve().parent.parent / "src" / "targum" / "strings"


@pytest.fixture
def notes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    spec = importlib.util.spec_from_file_location("mail_notes", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    strings = tmp_path / "strings"
    strings.mkdir()
    for name in ("en.json", "ru.json"):
        shutil.copy(REAL / name, strings / name)
    monkeypatch.setattr(module, "STRINGS", strings)
    return module


def test_every_mail_is_a_note_and_an_untouched_note_changes_nothing(
    notes: ModuleType, tmp_path: Path
) -> None:
    folder = tmp_path / "vault"
    written = {path.name for path in notes.push(folder)}
    assert "Invitation.md" in written and "Waitlist.md" in written
    text = (folder / "Invitation.md").read_text(encoding="utf-8")
    assert "## Subject\n<!-- mail.invitation.subject -->" in text
    assert notes.pull(folder) == [], "a round trip is the catalogue it started from"
    assert not notes.push(folder), "a note already there is not written over"


def test_an_edit_in_the_note_is_the_mail(notes: ModuleType, tmp_path: Path) -> None:
    folder = tmp_path / "vault"
    notes.push(folder)
    path = folder / "Invitation.md"
    text = path.read_text(encoding="utf-8").replace(
        "It's your turn: targum is open for you", "Welcome in: targum is open"
    )
    path.write_text(text, encoding="utf-8")
    assert notes.pull(folder) == ["mail.invitation.subject"]
    saved = json.loads((notes.STRINGS / "en.json").read_text(encoding="utf-8"))
    assert saved["mail.invitation.subject"] == "Welcome in: targum is open"
    assert notes.stale(["mail.invitation.subject"]) == {"ru": ["mail.invitation.subject"]}


def test_a_note_that_drops_a_link_is_refused_and_nothing_is_written(
    notes: ModuleType, tmp_path: Path
) -> None:
    folder = tmp_path / "vault"
    notes.push(folder)
    path = folder / "Invitation.md"
    before = (notes.STRINGS / "en.json").read_text(encoding="utf-8")
    path.write_text(
        path.read_text(encoding="utf-8").replace("connect it: {link}", "connect it."),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match=r"\{link\}"):
        notes.pull(folder)
    assert (notes.STRINGS / "en.json").read_text(encoding="utf-8") == before
