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

# §4. Every colour the interface is allowed to be. There is one look (design.md §12,
# 2026-09-19), so "on ink" below means §9's inverted block, a film's letterbox or the
# public pages' band — a dark *surface on a light page* — and never a dark page.
PALETTE = {
    "#fbf9f5": "page",
    "#171614": "the ink surface",
    "#f3efe7": "page raised",
    "#201e1b": "raised, on ink",
    "#e2dcd1": "rule",
    "#322e29": "rule, on ink",
    "#1c1a17": "ink",
    "#e6e1d8": "text on ink",
    "#6b645c": "muted",
    "#9a9288": "muted, on ink",
    "#7a5c38": "accent working",
    "#c8a778": "accent working, on ink / the wash",
    "#b8935e": "focus ring",
    "#a5824f": "the mark's translation column on paper",
    # The knowledge ramp used to be four gold steps written out per surface, and it is why
    # every chart on the progress page read brown. It climbs to leaf now — tints of
    # --leaf mixed against --paper, so "known"
    # is the most present step (words.css). §4 gives "known" to leaf by name, so
    # the scale and the functional colour finally agree. The five gold steps that are
    # left over are not listed here any more: unlisted means a stray, which is what a
    # reintroduced brown ramp would be.
    "#c3bdb1": "chart off",
    "#e7e1d6": "chart grid",
    "#cfc7ba": "chart axis",
    # Functional colour (§4): UI features only, never the identity.
    "#5a7340": "leaf",
    "#a8c37e": "leaf, on ink",
    "#b4553f": "clay",
    "#e0937d": "clay, on ink",
    "#6b5a8e": "iris",
    "#b3a3d6": "iris, on ink",
    # The bright set (§4): peak moments, one hue at a time.
    "#e2a33c": "sun",
    "#7ba646": "leaf-bright",
    "#8e74c9": "iris-bright",
    "#c2517a": "rose",
    # Deep paper (§9): structural only, never a text background.
    "#ece7de": "desk",
    # The desk's own values (§13, 2026-09-11): the one cool hue that marks a control, on
    # paper and on ink, and the text on it; the well's rule; the ink bar. The ground, the
    # card and the glass bar are values already here.
    "#1f6f6b": "teal",
    "#6fb8b3": "teal, on ink",
    "#0f1a19": "text on teal, on ink",
    "#cfc7b9": "well",
    "#0c0b0a": "the ink bar",
    # The other two deep paper tones are already above: #e7e1d6 doubles as the chart
    # grid and #e6e1d8 as the text on an ink surface. Same values, different jobs.
    # The max-contrast pair (§9).
    "#fffdf9": "page, switched on",
    "#121110": "ink, switched on",
}

# §4. The bright set lives on ink. On paper it is allowed only as a graphic at 3:1 or
# better, and two of the four do not reach that, so they are ink-panel only.
INK_ONLY = {"#e2a33c": 2.09, "#7ba646": 2.70}

# §1 and §10. The identity is flat forever; the gloss recipe is for UI only.
IDENTITY = ("brand-mark", "brand", "lockup", "wordmark")

# §8. Radii are exact, and never snapped: the reader's 4/5/6/8, and since 2026-09-11 the
# desk's own 8/12/16/24 (§13), which a rule names by its token.
RADII = {"4px", "5px", "6px", "8px", "12px", "16px", "24px", "999px", "50%", "0"}
RADIUS_TOKENS = {
    "--radius-control": "8px",
    "--radius-row": "12px",
    "--radius-card": "16px",
    "--radius-sheet": "24px",
}

# §5. The type scale. `em` sizes are relative to a component already on the scale.
# §5, plus the landing display step §12 records (2026-08-31): a public landing page's one
# headline, 2.75rem on a wide window and 2.25rem on a phone, and nowhere inside the product.
SIZES = {
    "2.75rem",
    "2.25rem",
    "1.75rem",
    "1.5rem",
    "1.5em",
    # §13: section titles and meta on the desk.
    "1.25rem",
    "0.875rem",
    "1.0625rem",
    "0.9375rem",
    "0.8125rem",
    "0.6875rem",
}


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
    """The reader's 4 controls, 5 rows, 6 cards, 8 panels; the desk's 8, 12, 16, 24; 999
    pills. A rule may name a corner by its token, and the token is on the scale."""
    for value in re.findall(r"border-radius:\s*([^;]+);", sheet.read_text(encoding="utf-8")):
        for corner in value.split():
            if corner.startswith("var(--radius-"):
                assert corner[4:-1] in RADIUS_TOKENS, f"{sheet.name}: {corner} is no token"
                continue
            assert corner in RADII, (
                f"{sheet.name}: border-radius {value.strip()!r} is off the scale"
            )


def test_the_radius_tokens_are_the_scale() -> None:
    """§13: the desk names its corners once, in the stylesheet every page loads."""
    text = (ASSETS / "reader.css").read_text(encoding="utf-8")
    for token, size in RADIUS_TOKENS.items():
        found = set(re.findall(rf"{token}:\s*([^;]+);", text))
        assert found == {size}, f"{token} should be {size} everywhere, found {found}"


@pytest.mark.parametrize("sheet", STYLESHEETS, ids=lambda p: p.name)
def test_absolute_type_sizes_are_on_the_scale(sheet: Path) -> None:
    """Sizes in rem or px are the scale itself; em sizes are relative and exempt."""
    for value in re.findall(r"font-size:\s*([^;]+);", sheet.read_text(encoding="utf-8")):
        size = value.strip()
        if size.endswith("em") and not size.endswith("rem"):
            continue
        if size.startswith("var(") or size.endswith("%"):
            continue
        # §13: the desk's rem scales with the screen, from 16px on a phone to 22px on a
        # television, on the root and nowhere else. The one clamp the scale allows.
        if size.startswith("clamp(") and sheet.name == "chrome.css":
            continue
        assert size in SIZES, f"{sheet.name}: font-size {size!r} is off the scale"


def test_the_focus_ring_is_one_colour() -> None:
    """§4 gives one focus colour, and it is defined once."""
    text = (ASSETS / "reader.css").read_text(encoding="utf-8")
    rings = set(re.findall(r"--focus:\s*([^;]+);", text))
    assert rings == {"#b8935e"}, f"focus ring should be #b8935e everywhere, found {rings}"


#: §8. Every control a thumb presses. This list IS the rule: a new control in the strip,
#: the picture's keys or the bar belongs here the day it is drawn.
#:
#: `.pair.voiced .say` is here and is safe: it stands in the gutter at
#: `inset-inline-end: -1.9rem`, outside the pair, so its reach crosses a margin and never
#: the words. A control that sat among them could not take this.
THUMBED = (
    # Shnayim mikra's presses (2026-09-13, targum-internal#202): the way it is kept, the
    # press on under a verse, and the press at the foot of a section.
    ".practice-key",
    ".practice-row button",
    ".practice-step button",
    ".player-play",
    ".player-back",
    ".player-on",
    ".player-rate-now",
    ".player-video",
    ".player-get",
    ".player-close",
    ".video-mode",
    ".video-corner",
    ".video-close",
    # And the picture's grip and size key, on a wide touch screen (2026-09-13).
    ".video-grip",
    ".video-size",
    # What to work on (2026-09-18, targum-internal#103): the two answers a word row has.
    ".work-keys button",
    ".fold",
    ".pair.voiced .say",
    # The chat's controls (2026-09-05): the button that sends, the door to a fresh
    # conversation, and the rows that open an old one.
    ".chat-send",
    ".chat-new",
    ".chat-list button",
    # And the pill that opens the list as a sheet on a phone, and More at its foot
    # (2026-09-10, targum-internal#238).
    ".chat-open-list",
    ".chat-more",
    # And the chips — the things most readers ask — and Another under the card the
    # first hands back (2026-09-10, targum-internal#240).
    ".chat-ask",
    ".chat-another",
    # And Show English at the head of the thread (2026-09-10, targum-internal#241).
    ".chat-english",
    # And the first visit's two answers (2026-09-10, targum-internal#243).
    ".chat-first-yes",
    ".chat-first-no",
    # And the two presses under Words you may already know (2026-09-10, #245).
    ".claim-yes",
    ".claim-no",
    # And the bar's own presses (2026-09-11): the four places, at the foot of a phone,
    # the pill that opens the conversation, the bell and the account.
    ".site-nav a",
    ".talk-cta",
    ".notices > button",
    # And the panel's own presses (2026-09-14): each line's × and Clear all.
    ".notices-clear",
    ".notices-list button",
    ".account > button",
    ".palette-open",
    ".palette-row",
    # And the row of doors above the sheet on Learn, and the subscriptions menu's rows
    # (2026-09-11).
    ".way",
    ".ways-item",
    ".ways-link",
    # And the door that makes a silent section's audio (2026-09-10, #246).
    ".voice-go",
    # And the Add page's box (2026-09-13, targum-internal#249): Choose files, Ask
    # targum, Continue, the × on a file in the box, Change, the presses on a priced card,
    # and Choose file for a translation or a transcript.
    ".bring-choose",
    ".bring-ask",
    ".add .go",
    ".given-file-x",
    ".add .change",
    ".add .status button",
    ".drop.small button",
    # And the button on a quote that starts a build — the one press that spends.
    ".quote-go",
    # And the door a path becomes: the reader opens a text, never the model.
    ".chat-door",
    # And the switch between finding and talking.
    # And the two voice controls: speak a line, hear an answer.
    ".chat-mic",
    ".chat-play",
    # And the `+` on the box (2026-09-06): bring a file, a link or a recording.
    ".chat-bring",
    # And the × on a held file's chip (2026-09-07): let it go before Send.
    ".chat-drop",
    # And Ask, on a word's card (2026-09-06), with the field the question is typed in.
    ".gloss-card .ask-go",
    ".gloss-card .ask-field",
    # And saying a meaning is wrong (2026-09-22, targum-internal#164): the opener, the
    # field the right meaning is typed in, and Send. Controls, not a line of text — §8's
    # exception is for a passage that answers a tap, and these are drawn to be pressed.
    ".gloss-card .fix-open",
    ".gloss-card .fix-field",
    ".gloss-card .fix-go",
    # And the record's two presses (2026-09-06): look a word up, save the conversation.
    ".chat-look",
    ".chat-save",
    # And the switch between renderings in the bar (2026-09-07, targum-internal#199):
    # Onkelos or English, on a text that carries both.
    ".renderings .rendering",
    # And the keys the audit of 2026-09-14 found with no reach: copy and hear on a card
    # line, the sheet's grab, the words tab, Keep on a phrase, the pager, a weekly's level
    # links, look it up, a note's Save, Translate on a waiting chapter, Undo under the
    # rest, and the press that starts a build from a Library row.
    ".copy",
    ".hear",
    ".grab",
    ".list-tab",
    ".pick-card button",
    ".pager a",
    ".bar .levels .level",
    ".gloss-card .look-up",
    ".vocab-editor .note-save",
    ".waiting-note button",
    # The foot's quiet press, Back on its line, and Undo where a press landed (2026-09-25).
    ".foot-plain",
    ".list-nav .list-back",
    ".arrived button",
    ".rows > li > .row-go",
    # And a part of this week's reading on the parasha page (2026-09-15, #203).
    ".week-part",
    # And Hear first, in the player strip (2026-09-15, targum-internal#265).
    ".player-first",
    # The connect page's own (2026-09-24): an app's tab, the Copy beside an address,
    # the examples under the conversation, and a step, which shows its picture.
    ".plat",
    ".copy",
    ".scene",
    ".steps > li",
)


def test_every_thumbed_control_reaches_44px() -> None:
    """§8: a control a thumb presses answers a tap over 44px.

    The rule lived as two coarse-pointer selector lists that nobody had written down, and
    it drifted: the picture's × had its 44px while the mode and corner keys beside it did
    not, and neither did the speed or the picture toggle. Both lists count, because the
    reach is given in either — what matters is that no control is in neither.

    Read at the source because this is what the stylesheet promises;
    `test_reader_browser.py` measures what a tap actually reaches, which is the half a
    stylesheet cannot prove — a box with `overflow: hidden` promises 44px and clips it.
    """
    # Every stylesheet, not the reader's alone: the chat page draws controls of its own
    # in `chat.css`, and a registry that only read one file would let a second drift.
    text = "\n".join(sheet.read_text(encoding="utf-8") for sheet in STYLESHEETS)
    blocks = []
    at = text.find("@media (hover: none) and (pointer: coarse)")
    while at != -1:
        close = text.find("\n}\n", at)
        block = text[at : close if close != -1 else len(text)]
        if "44px" in block:
            blocks.append(re.sub(r"/\*.*?\*/", "", block, flags=re.S))
        at = text.find("@media (hover: none) and (pointer: coarse)", at + 1)
    assert blocks, "§8's 44px reach is given in a coarse-pointer block, and there is none"

    reach = "\n".join(blocks)
    missing = [sel for sel in THUMBED if sel not in reach]
    assert not missing, "§8: these answer a tap under a thumb and are given no reach: " + ", ".join(
        missing
    )


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


def test_a_page_that_can_be_heard_says_so_in_ink() -> None:
    """§1, §9, and the §12 entry of 2026-09-03.

    A text that carries media opens as its media, and the player's own name is what says
    the page can be heard. §9 keeps muted for "genuinely secondary lines only — captions,
    metadata", so the name is ink: at 13px in `--ink-soft` it read as chrome to the first
    stranger, a designer, who looked straight at it and never found the audio.
    """
    text = (ASSETS / "reader.css").read_text(encoding="utf-8")
    rule = re.search(r"\.player-said\s*\{([^}]*)\}", text)
    assert rule is not None, "the player still names itself"
    body = rule.group(1)
    assert "var(--ink)" in body, ".player-said must be ink, not muted (§9)"
    assert "--ink-soft" not in body, "the name of the thing is not metadata (§9)"


def test_the_streak_is_the_longest_one_and_the_foot_moves_nothing() -> None:
    """§12 (2026-09-03), targum-internal#175. The longest run of days is built and the
    current one is refused: a count that can be destroyed is the mechanism that makes
    people quit in the week they break it. So nothing anywhere names a current streak or
    the gap since the last reading day, `charts.js` has no function for either, and the
    foot that delivers the ledger's increment celebrates in type, never in motion (§1),
    and counts real things only (§6) — no score, no points, no level."""
    for path in PAGES + SCRIPTS:
        for line in prose(path):
            said = line.lower()
            for banned in ("current streak", "streak broken", "days in a row", "keep your streak"):
                assert banned not in said, f"{path.name} says {banned!r}"
    charts = (ASSETS / "charts.js").read_text(encoding="utf-8")
    assert "function longest(" in charts
    assert "function current(" not in charts and "function gap(" not in charts

    css = re.sub(r"/\*.*?\*/", " ", (ASSETS / "reader.css").read_text(encoding="utf-8"), flags=re.S)
    for selector, body in re.findall(r"([^{}]+)\{([^}]*)\}", css):
        if ".finished" in selector or ".move" in selector:
            assert "animation" not in body and "transition" not in body, selector.strip()

    reader = (ASSETS / "reader.js").read_text(encoding="utf-8")
    foot = reader[reader.index("function lookedRead") : reader.index("function renderFinished")]
    for currency in ("score", "point", "level", "xp"):
        assert currency not in foot.lower(), f"the foot invents a currency: {currency!r}"
    # And the words that cost (targum-internal#174): no percentage, no grade, no clay.
    # The finished box's one share, "N% known here", is the header's own figure and is
    # drawn in `renderFinished`, outside this span (§12, 2026-09-25).
    for verdict in ("%", "accuracy", "grade", "clay"):
        assert verdict not in foot.lower(), f"the foot passes a verdict: {verdict!r}"


def _catalogues() -> list[tuple[str, dict[str, str]]]:
    from targum import strings

    return [(code, strings.catalogue(code)) for code in strings.languages() if code != "en"]


def test_every_language_keeps_the_rules_that_are_not_about_english() -> None:
    """§12, "The interface speaks Russian". No exclamation marks, no emoji, and the name
    Latin and lowercase in every language: «targum», never Targum, never таргум."""
    for code, said in _catalogues():
        for key, text in said.items():
            assert "!" not in text, f"{code}: {key} exclaims: {text!r}"
            assert not re.findall(r"[\U0001F300-\U0001FAFF☀-➿️⬀-⯿]", text), f"{code}: {key}"
            assert "Targum" not in text, f"{code}: {key} capitalises the name"
            assert "таргум" not in text.lower(), f"{code}: {key} spells the name in Cyrillic"


def test_a_translated_label_stays_near_the_length_of_its_english() -> None:
    """§12, "The interface speaks Russian". A button, a tab or a column head was sized
    against its English; a translation that runs past 1.6 times that, or six characters
    more where the English is short, is caught here rather than by a screenshot."""
    from targum import strings

    english = strings.catalogue("en")
    for code, said in _catalogues():
        for key, text in said.items():
            base, _, form = key.rpartition(".")
            source = english.get(key) or english.get(f"{base}.other")
            if source is None or "{" in source or len(source.split()) > 3:
                continue
            if re.search(r"[.?:…]$", source.strip()):
                continue  # a sentence, not a label
            limit = max(1.6 * len(source), len(source) + 6)
            assert len(text) <= limit, f"{code}: {key} {text!r} is long for {source!r}"


def test_a_toggle_the_page_marks_pressed_is_styled_pressed() -> None:
    """A control the script toggles must look toggled, or the press does nothing visible.

    Shipped broken on 2026-09-17 and deployed: the arrival's subject chips set
    `aria-pressed` and `.is-picked` in `learn.js`, and the one rule that styled them was
    a grouped selector — `.arrival-door[aria-pressed="true"], .arrival-rung[...]`. A
    clean-up that dropped every rule naming `.arrival-rung` took the door half with it,
    so picking a subject changed nothing on screen and nothing failed.

    Checked from the script, not from a list here: whatever `learn.js` marks as pressed
    is what `learn.css` has to answer for, so a new toggle cannot be added without one.
    """
    import re

    script = (ASSETS / "learn.js").read_text(encoding="utf-8")
    sheet = (ASSETS / "learn.css").read_text(encoding="utf-8")
    # The class given to the *same* element that is marked `aria-pressed`. Bound by the
    # variable, not by nearness: a first cut looked within 400 characters and caught
    # `arrival-rung-letter`, a span inside the button, which is never pressed itself.
    pressed = {
        name
        for holder, name in re.findall(r"(\w+)\.className\s*=\s*\"([a-z-]+)\"", script)
        if re.search(re.escape(holder) + r'\.setAttribute\("aria-pressed"', script)
    }
    assert pressed, "no pressable control found in learn.js — has the arrival moved?"
    for name in sorted(pressed):
        assert re.search(r"\." + re.escape(name) + r'\[aria-pressed="true"\]', sheet), (
            f".{name} is marked aria-pressed by learn.js and styled by nothing in learn.css"
        )


def test_the_queue_waits_and_never_chases() -> None:
    """targum-internal#103. The list that maintains itself is the paid surface, and the
    constraint came in the same minute as the request: "if smth gonna ping me or bother
    me like duolingo I'll fucking delete it" (Dmitry Z, 2026-09-16).

    So it is pull and never push. `workOn` reads rows that already exist; nothing about
    it is scheduled, owed or counted, and §6's rule that engagement counts real things
    is what keeps it a view rather than a debt.
    """
    lists = (ASSETS / "lists.js").read_text(encoding="utf-8")
    fold = lists[lists.index("function workOn(") : lists.index("/* --- the word table")]
    # The code, not the prose about it: the comments in here name every one of these
    # words in order to say the fold does not do them, and a check that read them would
    # be a check that can only pass on undocumented code.
    fold = re.sub(r"/\*.*?\*/", " ", fold, flags=re.S)
    fold = re.sub(r"//.*", " ", fold)

    # Nothing that implies a clock or an obligation.
    for owed in ("due", "overdue", "interval", "schedule", "remind", "notify", "streak", "goal"):
        assert owed not in fold.lower(), f"the fold says {owed!r}"
    # And nothing that puts a number on what is waiting: "12 words due" is the sentence
    # this card exists not to say, and a count is how it starts.
    assert "length +" not in fold and "count" not in fold.lower()

    # The heading is a question answered rather than an instruction, and carries no
    # number beside it the way the table's title does.
    yours = (TEMPLATES / "yours.html.j2").read_text(encoding="utf-8")
    assert "What to work on" in yours
    assert "work-title" not in yours, "no counted heading: that is the table's, and earned"
