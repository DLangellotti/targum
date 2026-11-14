"""Upload's polish and Your targums' nits (targum-internal#715 P2-12, qa-claude on #1222).

The palette keeps its own copy of a text's one figure, for the pages that do not carry
`figure.js`; the two copies are held to each other here so an edit to one that misses
the other fails rather than drifting silently.
"""

from __future__ import annotations

import re
from pathlib import Path

ASSETS = Path(__file__).resolve().parents[1] / "src" / "targum" / "render" / "assets"


def rule(source: str) -> list[str]:
    """The figure rule's lines, from the words gate to its return, whitespace folded."""
    body = source[source.index("function figure(row) {") :]
    body = body[: body.index("\n  }\n")]
    start = body.index("// A row that says how many words it counted")
    return [re.sub(r"\s+", " ", line).strip() for line in body[start:].splitlines() if line.strip()]


def test_the_palette_s_figure_is_figure_js_s_rule_line_for_line() -> None:
    shared = rule((ASSETS / "figure.js").read_text(encoding="utf-8"))
    palette = rule((ASSETS / "palette.js").read_text(encoding="utf-8"))
    assert shared and palette == shared
    assert any('"words" in row && !row.words' in line for line in palette), (
        "a row that counted no words is not measured, in the palette too"
    )


def test_the_palette_says_the_figure_through_the_shared_words() -> None:
    palette = (ASSETS / "palette.js").read_text(encoding="utf-8")
    assert "strings.figureSaid(found, marked)" in palette
