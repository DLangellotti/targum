"""The design guidelines, enforced.

`design.md` at the root of this repository is the source. It replaced `Design updated.pdf`
on 2026-08-29, which had itself replaced `Design.pdf` on Aug 24 2026 — and the reason it
moved out of the vault and into the repository is the reason this file exists: a guideline
nobody can run is a guideline that drifts. The palette held for three months and then a
stray #b4553f arrived for an error state, and nothing said so. The PDF drifted the same
way, in three places, while still being called binding.

These are the parts of design.md a machine can check. What cannot be tested lives there
and not here — whether motion is *purposeful*, whether the voice sounds like a
designer-engineer explaining a decision.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ASSETS = Path(__file__).resolve().parents[1] / "src/targum/render/assets"
TEMPLATES = Path(__file__).resolve().parents[1] / "src/targum/render/templates"
SERVE = Path(__file__).resolve().parents[1] / "src/targum/serve.py"

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "design.md"

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
    # The knowledge ramp used to be four gold steps written out per theme, and it is why
    # every chart on the progress page read brown. It climbs to leaf now — tints of
    # --leaf mixed against --paper, so one definition serves both surfaces and "known"
    # is the most present step on each (words.css). §4 gives "known" to leaf by name, so
    # the scale and the functional colour finally agree. The five gold steps that are
    # left over are not listed here any more: unlisted means a stray, which is what a
    # reintroduced brown ramp would be.
    "#c3bdb1": "chart off, light",
    "#e7e1d6": "chart grid, light",
    "#cfc7ba": "chart axis, light",
    "#4a453e": "chart off, dark",
    "#2a2622": "chart grid, dark",
    "#3a3530": "chart axis, dark",
    # Functional colour (§4): UI features only, never the identity.
    "#5a7340": "leaf, light",
    "#a8c37e": "leaf, dark",
    "#b4553f": "clay, light",
    "#e0937d": "clay, dark",
    "#6b5a8e": "iris, light",
    "#b3a3d6": "iris, dark",
    # The bright set (§4): peak moments, one hue at a time.
    "#e2a33c": "sun",
    "#7ba646": "leaf-bright",
    "#8e74c9": "iris-bright",
    "#c2517a": "rose",
    # Deep paper (§9): structural only, never a text background.
    "#ece7de": "desk",
    # The other two deep paper tones are already above: #e7e1d6 doubles as the chart
    # grid and #e6e1d8 as ink on the dark surface. Same values, different jobs.
    # The max-contrast pair (§9).
    "#fffdf9": "page, switched on",
    "#121110": "ink, switched on",
}

# §4. The bright set lives on ink. On paper it is allowed only as a graphic at 3:1 or
# better, and two of the four do not reach that, so they are ink-panel only.
INK_ONLY = {"#e2a33c": 2.09, "#7ba646": 2.70}

# §1 and §10. The identity is flat forever; the gloss recipe is for UI only.
IDENTITY = ("brand-mark", "brand", "lockup", "wordmark")

# §8. Radii are exact, and never snapped.
RADII = {"4px", "5px", "6px", "8px", "999px", "50%", "0"}

# §5. The type scale. `em` sizes are relative to a component already on the scale.
SIZES = {"1.75rem", "1.5rem", "1.5em", "1.0625rem", "0.9375rem", "0.8125rem", "0.6875rem"}


def hexes(text: str) -> set[str]:
    # Comments explain the palette and name colours that are deliberately not used.
    # What matters is what the interface paints with.
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
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


def test_no_exclamation_marks() -> None:
    """§6. Nothing is exclaimed at the reader.

    The guidelines pair this with "no gamification vocabulary", which is deliberately
    not asserted here: David's position is that streaks and scores are unbuilt rather
    than forbidden, and a test would block the decision rather than record it.
    """
    for path in PAGES + SCRIPTS + [SERVE]:
        for line in prose(path):
            assert "!" not in line, f"{path.name}: exclamation mark in {line.strip()[:50]!r}"


def test_the_identity_never_carries_a_sheen() -> None:
    """§1, §9, §10. The mark, lockup and wordmark are flat forever.

    The UI may shine — that is new in the August 2026 revision — but the sheen is for
    interactive and celebratory elements, never for the identity and never on a
    resting text surface.
    """
    for sheet in STYLESHEETS:
        text = re.sub(r"/\*.*?\*/", " ", sheet.read_text(encoding="utf-8"), flags=re.S)
        for rule in re.findall(r"([^{}]+)\{([^}]*)\}", text):
            selector, body = rule[0], rule[1]
            if not re.search(r"--gloss|linear-gradient", body):
                continue
            assert not any(name in selector for name in IDENTITY), (
                f"{sheet.name}: the identity carries a sheen in {selector.strip()[:60]!r}"
            )


def test_the_ink_only_brights_never_touch_paper() -> None:
    """§4. The bright set lives on ink panels; on paper it is allowed only as a graphic at
    3:1 or better, and two of the four do not reach it.

    `INK_ONLY` recorded that measurement for a year and nothing asserted it, because
    nothing used the colours. The progress page spends `--leaf-bright` on its one
    inverted block, which is the moment the rule becomes checkable: a rule with a use is
    a rule that can drift.

    Selector-based rather than clever. The inverted block carries `.ledger`, and anything
    painting one of these two outside it is on paper by elimination.
    """
    inverted = "ledger"
    tokens = {"#e2a33c": "--sun", "#7ba646": "--leaf-bright"}
    for sheet in STYLESHEETS:
        text = re.sub(r"/\*.*?\*/", " ", sheet.read_text(encoding="utf-8"), flags=re.S)
        for selector, body in re.findall(r"([^{}]+)\{([^}]*)\}", text):
            # The declarations block, not the :root definitions — naming a value is how
            # the palette exists at all.
            if ":root" in selector or selector.strip().startswith("@"):
                continue
            for hexed, name in tokens.items():
                if f"var({name})" not in body and hexed not in body.lower():
                    continue
                assert inverted in selector, (
                    f"{sheet.name}: {name} does not reach 3:1 on paper, and "
                    f"{selector.strip()[:60]!r} is not the inverted block"
                )


def gradients(text: str) -> list[str]:
    r"""The inside of every `linear-gradient(...)`, with the parens balanced.

    A regex cannot do this and the one here did not: `linear-gradient\(([^;]*?)\)\s`
    stops at the first `)` followed by whitespace, which in
    `linear-gradient(\n  to right,\n  var(--accent) var(--share), ...)` is the one
    closing `var(--accent`. The captured text then held no complete `var(--…)` token, so
    the assertion below ran against an empty list and passed. Every multi-line gradient
    went unread, including the one colour ramp in the codebase.
    """
    out = []
    for opened in re.finditer(r"linear-gradient\(", text):
        depth, start, i = 1, opened.end(), opened.end()
        while i < len(text) and depth:
            depth += (text[i] == "(") - (text[i] == ")")
            i += 1
        if not depth:
            out.append(text[start : i - 1])
    return out


def test_no_gradient_is_a_colour_ramp() -> None:
    """§9. Gloss is light on glass, never metal — never a gold-to-gold ramp."""
    for sheet in STYLESHEETS:
        text = re.sub(r"/\*.*?\*/", " ", sheet.read_text(encoding="utf-8"), flags=re.S)
        for gradient in gradients(text):
            stops = re.findall(r"#[0-9a-fA-F]{3,8}|var\(--[a-z-]+\)", gradient)
            named = [x for x in stops if not x.startswith("var(--gloss")]
            assert not named, (
                f"{sheet.name}: gradient mixes colours rather than adding a sheen: "
                f"{gradient[:60]!r}"
            )


# -- the document itself ------------------------------------------------------


def test_the_file_that_governs_is_in_the_repository() -> None:
    """The move that makes the rest of this file mean something.

    A design document living somewhere the tools cannot edit goes quietly out of date
    while still being called binding, which is what happened to the PDF. This one is
    beside the code, changes in the same commits, and is what CLAUDE.md sends a reader to.
    """
    assert DESIGN.is_file(), "design.md governs every visible surface, and it is missing"
    claude = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    assert "design.md" in claude, "nothing sends a reader to the file that governs"


def test_every_section_the_code_cites_is_a_section_that_exists() -> None:
    """The stylesheets reason with themselves in section numbers — "Functional colour
    (§4)", "Gloss (§9) is light on glass, never metal". A citation that resolves to
    nothing is worse than no citation: it reads as authority and carries none. This is
    also what stops the sections being renumbered out from under the code.
    """
    headings = set(re.findall(r"^## (\d+) ·", DESIGN.read_text(encoding="utf-8"), re.M))
    assert headings, "design.md has no numbered sections to cite"

    cited: set[str] = set()
    for path in STYLESHEETS + SCRIPTS + sorted((ROOT / "src/targum").rglob("*.py")):
        cited.update(re.findall(r"§(\d+)", path.read_text(encoding="utf-8")))

    missing = sorted(cited - headings, key=int)
    assert not missing, "the code cites §" + ", §".join(missing) + ", which design.md lacks"
