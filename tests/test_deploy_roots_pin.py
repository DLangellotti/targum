"""`deploy/roots.pin` names the root lexicon each deploy ships (targum-internal#592), so
moving a lexicon on is a reviewed change. The function is cut out of deploy.sh and run on
its own against a pin file and a home of the test's."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "deploy" / "deploy.sh"


def resolve(where: Path, pin: str | None, language: str) -> str:
    """What deploy.sh would ship for `language`, under its own `set -euo pipefail`."""
    found = re.search(r"^pinned_roots\(\) \{\n.*?^\}\n", SCRIPT.read_text(), re.S | re.M)
    assert found is not None, "deploy.sh reads the pin"
    (where / "deploy").mkdir(parents=True, exist_ok=True)
    if pin is not None:
        (where / "deploy" / "roots.pin").write_text(pin, encoding="utf-8")
    run = subprocess.run(
        ["bash", "-c", f"set -euo pipefail\n{found.group(0)}pinned_roots {language}"],
        env={"ROOT": str(where), "HOME": "/home/x", "PATH": "/usr/bin:/bin"},
        capture_output=True,
        text=True,
        check=True,
    )
    return run.stdout.strip()


def test_a_pinned_language_ships_the_file_the_pin_names(tmp_path: Path) -> None:
    pin = "# a comment naming he roots-he-old.json\nhe roots-he-2026-11-18.json\n"
    assert resolve(tmp_path, pin, "he") == "/home/x/.targum/roots-he-2026-11-18.json"


def test_a_language_with_no_line_or_no_pin_ships_the_usual_file(tmp_path: Path) -> None:
    assert resolve(tmp_path / "a", "he roots-he-2026-11-18.json\n", "ru") == (
        "/home/x/.targum/roots-ru.json"
    )
    assert resolve(tmp_path / "b", None, "he") == "/home/x/.targum/roots-he.json"


def test_the_pin_in_the_tree_names_the_hebrew_lexicon_of_2026_11_18() -> None:
    lines = [
        line.split()
        for line in (ROOT / "deploy" / "roots.pin").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]
    assert lines == [["he", "roots-he-2026-11-18.json"]]
