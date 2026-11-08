"""deploy.sh's remote script is an unquoted heredoc, so the laptop expands every `$name`
in it before the box sees a byte. A variable the remote script sets for itself (a loop
variable, an assignment) has to be written `\\$name`, or the laptop's `set -u` stops the
deploy halfway: on 2026-11-06 `$finds_language` (targum-internal#629) did exactly that,
after the keys and covers had gone and before the backup and the install."""

import re
from pathlib import Path

DEPLOY = Path(__file__).resolve().parent.parent / "deploy" / "deploy.sh"


def _remote_script() -> str:
    lines = DEPLOY.read_text(encoding="utf-8").splitlines()
    start = next(i for i, line in enumerate(lines) if line.rstrip().endswith('-s" <<EOF'))
    end = next(i for i in range(start + 1, len(lines)) if lines[i] == "EOF")
    return "\n".join(lines[start + 1 : end])


def test_a_name_the_remote_script_sets_is_never_expanded_on_the_laptop() -> None:
    body = _remote_script()
    own = set(re.findall(r"\bfor\s+([a-z_][a-z0-9_]*)\s+in\b", body))
    own |= set(re.findall(r"^\s*(?:local\s+)?([a-z_][a-z0-9_]*)=", body, re.M))
    assert "finds_language" in own
    unescaped = {
        name
        for name in own
        for found in re.finditer(r"(?<!\\)\$\{?" + re.escape(name) + r"\b", body)
        if found
    }
    assert not unescaped, f"expanded on the laptop, set on the box: {sorted(unescaped)}"
