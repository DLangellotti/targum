"""The brand guidelines, enforced.

`Design.pdf` in the vault is the source; these are the parts of it a machine can check.
They are here rather than in a review checklist because a guideline nobody can run is a
guideline that drifts: the palette held for three months and then a stray #b4553f
arrived for an error state, and nothing said so.

What cannot be tested lives in the document and not here — whether motion is
*purposeful*, whether the voice sounds like a designer-engineer explaining a decision.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ASSETS = Path(__file__).resolve().parents[1] / "src/targum/render/assets"
TEMPLATES = Path(__file__).resolve().parents[1] / "src/targum/render/templates"
SERVE = Path(__file__).resolve().parents[1] / "src/targum/serve.py"

STYLESHEETS = sorted(ASSETS.glob("*.css"))
SCRIPTS = sorted(ASSETS.glob("*.js"))
PAGES = sorted(TEMPLATES.glob("*.j2"))

# §4. Every colour the interface is allowed to be.
PALETTE = {
    "#fbf9f5": "page, light",
    "#171614": "page, dark",
    "#f3efe7": "page raised, light",
    "#201e1b": "page raised, dark",
    "#e2dcd1": "rule, light",
    "#322e29": "rule, dark",
    "#1c1a17": "ink, light",
    "#e6e1d8": "ink, dark",
    "#6b645c": "muted, light",
    "#9a9288": "muted, dark",
    "#7a5c38": "accent working, light",
    "#c8a778": "accent working, dark / the wash",
    "#b8935e": "focus ring",
    "#a5824f": "the mark's translation column on paper",
    "#ab8555": "knowledge ramp",
    "#8b6840": "knowledge ramp",
    "#6b4f2e": "knowledge ramp",
    "#7d6039": "knowledge ramp, dark",
    "#e8d3b0": "knowledge ramp, dark",
    "#c3bdb1": "chart off, light",
    "#e7e1d6": "chart grid, light",
    "#cfc7ba": "chart axis, light",
    "#4a453e": "chart off, dark",
    "#2a2622": "chart grid, dark",
    "#3a3530": "chart axis, dark",
}

# §8. Radii are exact, and never snapped.
RADII = {"4px", "5px", "6px", "8px", "999px", "50%", "0"}

# §5. The type scale. `em` sizes are relative to a component already on the scale.
SIZES = {"1.75rem", "1.5rem", "1.5em", "1.0625rem", "0.9375rem", "0.8125rem", "0.6875rem"}


def hexes(text: str) -> set[str]:
    out = set()
    for raw in re.findall(r"#[0-9a-fA-F]{3,8}\b", text):
        value = raw.lower()
        if len(value) == 4:
            value = "#" + "".join(c * 2 for c in value[1:])
        out.add(value[:7])
    return out


@pytest.mark.parametrize("sheet", STYLESHEETS, ids=lambda p: p.name)
def test_only_brand_colours(sheet: Path) -> None:
    """One warm hue and its neutrals. No burgundy, no orange, no blue, no invented reds."""
    stray = hexes(sheet.read_text(encoding="utf-8")) - set(PALETTE)
    assert not stray, f"{sheet.name} uses colours that are not in the palette: {sorted(stray)}"


@pytest.mark.parametrize("sheet", STYLESHEETS, ids=lambda p: p.name)
def test_radii_are_on_the_scale(sheet: Path) -> None:
    """4 controls, 5 rows, 6 cards, 8 panels, 999 pills."""
    for value in re.findall(r"border-radius:\s*([^;]+);", sheet.read_text(encoding="utf-8")):
        for corner in value.split():
            assert corner in RADII, (
                f"{sheet.name}: border-radius {value.strip()!r} is off the scale"
            )


@pytest.mark.parametrize("sheet", STYLESHEETS, ids=lambda p: p.name)
def test_absolute_type_sizes_are_on_the_scale(sheet: Path) -> None:
    """Sizes in rem or px are the scale itself; em sizes are relative and exempt."""
    for value in re.findall(r"font-size:\s*([^;]+);", sheet.read_text(encoding="utf-8")):
        size = value.strip()
        if size.endswith("em") and not size.endswith("rem"):
            continue
        if size.startswith("var(") or size.endswith("%"):
            continue
        assert size in SIZES, f"{sheet.name}: font-size {size!r} is off the scale"


def test_the_focus_ring_does_not_change_with_the_theme() -> None:
    """§4 gives one focus colour. It is a supporting value, not a themed one."""
    text = (ASSETS / "reader.css").read_text(encoding="utf-8")
    rings = set(re.findall(r"--focus:\s*([^;]+);", text))
    assert rings == {"#b8935e"}, f"focus ring should be #b8935e everywhere, found {rings}"


@pytest.mark.parametrize("path", STYLESHEETS + SCRIPTS + PAGES, ids=lambda p: p.name)
def test_no_emoji(path: Path) -> None:
    """§6 and §7. No emoji, anywhere — not in copy, not standing in for an icon."""
    found = re.findall(
        r"[\U0001F300-\U0001FAFF☀-➿️⬀-⯿]",
        path.read_text(encoding="utf-8"),
    )
    assert not found, f"{path.name} contains emoji: {found[:5]}"


def test_motion_is_always_optional() -> None:
    """§8. Everything honours prefers-reduced-motion."""
    for sheet in STYLESHEETS:
        text = sheet.read_text(encoding="utf-8")
        if not re.search(r"\b(transition|animation):", text):
            continue
        assert "prefers-reduced-motion" in text, (
            f"{sheet.name} animates something but never offers to stop"
        )


def prose(path: Path) -> list[str]:
    """What a reader actually sees: quoted strings, and template text outside the tags."""
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".j2":
        text = re.sub(r"\{[#{%].*?[#}%]\}", " ", text, flags=re.S)  # Jinja
        text = re.sub(r"<[^>]+>", " ", text)  # markup, attributes included
        return [line for line in text.splitlines() if line.strip()]
    found = re.findall(r'"([^"\\\n]{4,})"', text) + re.findall(r"'([^'\\\n]{4,})'", text)
    # Copy has spaces in it. A header name, a CSS selector and an identifier do not,
    # and those are protocol rather than something a reader is shown.
    return [f for f in found if " " in f.strip()]


def test_the_name_is_always_lowercase() -> None:
    """§6. targum, even at the start of a sentence. Class names are code, not copy."""
    for path in PAGES + SCRIPTS + [SERVE]:
        for line in prose(path):
            assert "Targum" not in line, f"{path.name} capitalises the name: {line.strip()[:60]!r}"


def test_no_exclamation_marks_and_no_gamification() -> None:
    """§6. Nothing is celebrated at the reader; nothing is scored."""
    banned = re.compile(r"\b(streak|streaks|xp|badge|badges|achievement|congratulations)\b", re.I)
    for path in PAGES + SCRIPTS + [SERVE]:
        text = path.read_text(encoding="utf-8")
        for quoted in re.findall(r'"([^"\\\n]{4,})"', text):
            assert "!" not in quoted, f"{path.name}: exclamation mark in {quoted[:50]!r}"
            assert not banned.search(quoted), f"{path.name}: gamification in {quoted[:50]!r}"
