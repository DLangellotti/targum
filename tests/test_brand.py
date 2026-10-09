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
    # §12, 2026-10-09 ("The boards are the desk"): every desk page's title, on the desk under
    # the bar, and the boards' big figures — 34px at a 1440 window. A section's title is the
    # serif at 1.5rem (24px), already on the scale.
    "1.9375rem",
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
    """§13: the desk names its corners once, in the stylesheet every page loads (§11)."""
    text = (ASSETS / "tokens.css").read_text(encoding="utf-8")
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
    """§4 gives one focus colour, and it is defined once, with the tokens (§11)."""
    text = (ASSETS / "tokens.css").read_text(encoding="utf-8")
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
    # The row under a video's picture, the switch beside it in the bar, the transcript
    # panel's ×, the speed's picks and the step in ⋯ (targum-internal#422, 2026-10-05).
    # They replaced the picture's mode, corner, close, grip and size keys.
    ".film-play",
    ".film-rate",
    ".film-loop",
    ".film-transcript",
    ".film-view",
    ".film-panel-close",
    ".film-rate-pick",
    ".more-back",
    ".more-on",
    # Theatre's size grip on the picture's foot (design.md §12, 2026-10-07).
    ".film-size",
    # Saving for offline (design.md §12, 2026-10-09): save, stop, try again and remove, in
    # a reader's ⋯ and on a playlist's page.
    ".offline-go",
    ".offline-stop",
    ".offline-again",
    ".offline-remove",
    # Beside, the line between the picture and the transcript (design.md §12, 2026-10-08).
    ".film-split",
    # The next part under the picture, and its Try again (design.md §12, 2026-10-07).
    ".film-next-go",
    ".film-next-again",
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
    # And the one search's own presses (design.md §12, "One search, everywhere",
    # 2026-10-09): a result, a recent search's ×, the field's ×, the way back on a phone,
    # the language it searches in and each of its rows, and the level.
    ".palette-hit",
    ".palette-drop",
    ".palette-clear",
    ".palette-back",
    ".palette-lang",
    ".palette-lang-row",
    ".palette-level-pick",
    # (The row of doors above Learn's sheet and its subscriptions menu went with Learn,
    # design.md §12, 2026-10-08.)
    # And the door that makes a silent section's audio (2026-09-10, #246).
    ".voice-go",
    # And the Weekly portion shelf's Diaspora / Israel switch (targum-internal#411).
    "#portion-schedule .segment",
    # And the Add page's box (2026-09-13, targum-internal#249): Choose a file, Bring a
    # post, Upload, the × on a file in the box, Change, the presses on a priced card,
    # and Choose file for a translation or a transcript. (Ask targum went with the
    # board, 2026-10-09.)
    ".bring-choose",
    ".bring-post",
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
    ".yours-tabs .tab",
    # Your targums' find field (P4, 2026-10-09); its chips and order are gone.
    ".yours-card > .find",
    ".series-back",
    # The Library's kind doors and See all's menus (design.md §12, "The Library stands on
    # the ground", 2026-10-09); its Filters fold is gone.
    ".lib-door",
    ".see-menu-press",
    ".see-menu-item",
    ".claim-table label",
    ".chat-claim label",
    # A post's one way home (design.md §12, "A post keeps its shape", 2026-09-27).
    ".post-home",
    # "inferred" after a reading on a word card (design.md §12, 2026-09-27).
    ".gloss-card .inferred",
    # The fold over the words to know before a chapter (design.md §12, 2026-09-28).
    ".preread > summary",
    # The root on a word card, where it opens the words of it a reader has met
    # (targum-internal#96, behind `TARGUM_OCCURRENCES`).
    ".gloss-card .verb .root-open",
    # The vowel switch on /how (targum-internal#401).
    ".how-switch",
    # The Tanakh map's Read, the press a phone's tap on a square leads to (design.md §12,
    # "The Tanakh map is the knowledge ramp", 2026-09-28).
    ".tanakh-read",
    # The reader's bar as one row (targum-internal#421, 2026-10-05): Aa, print and ⋯,
    # Listen and the reading inside it, the rows and steps of Aa, the picks of the print
    # and the reading, the rows of ⋯, and the + that brings a column back.
    ".bar .bar-tool",
    ".bar .listen-play",
    ".bar .listen-voice",
    ".bar .aa-switch",
    ".bar .aa-step",
    ".bar-pop .recordings .recording-key",
    ".bar-pop .to-sheet .more-sheet",
    ".cmp-add",
    # The bar by how often it is pressed (design.md §12, 2026-10-08): the view's three
    # drawings stand in the bar. The speed and the marks are `.bar-tool`s.
    ".bar .bar-tools > .modes button",
    # Aa and ⋯ as the board draws them (design.md §12, 2026-10-09): every row, every
    # part of a segmented control, the rows Save for offline draws, and a sheet's handle.
    ".m-menu .m-row",
    ".bar .m-menu .seg > *",
    ".m-menu .offline-go",
    ".m-menu .offline-stop",
    ".m-menu .offline-remove",
    ".sheet-grab",
    # The build card's door, in somebody else's chat (design.md §12, 2026-10-06).
    ".card-door",
    # And the text card's Listen, beside its door (2026-10-06).
    ".card-play",
    # Home (design.md §12, "Home is Your targums, and Continue leads it", 2026-10-08):
    # a Continue card, the next one's Open, and the upload.
    ".home-card-open",
    ".try-open",
    ".upload-card",
    # A refusal's way on (design.md §12, 2026-10-09): Try again in a line or the
    # banner, and the one button of a panel or a whole page.
    ".fault-act",
    ".fault-go",
    # The components (design.md §12, "The desk's controls are one layer", 2026-10-09):
    # a button, a part of a choice of a few, a tab, and a field's well.
    ".btn",
    ".seg > *",
    ".tab",
    ".well",
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
    `aria-pressed` and `.is-picked` in `learn.js` (now `arrival.js`), and the one rule
    that styled them was a grouped selector —
    `.arrival-door[aria-pressed="true"], .arrival-rung[...]`. A clean-up that dropped
    every rule naming `.arrival-rung` took the door half with it, so picking a subject
    changed nothing on screen and nothing failed.

    Checked from the script, not from a list here: whatever `arrival.js` marks as pressed
    is what `arrival.css` has to answer for, so a new toggle cannot be added without one.
    """
    import re

    script = (ASSETS / "arrival.js").read_text(encoding="utf-8")
    sheet = (ASSETS / "arrival.css").read_text(encoding="utf-8")
    # The class given to the *same* element that is marked `aria-pressed`. Bound by the
    # variable, not by nearness: a first cut looked within 400 characters and caught
    # `arrival-rung-letter`, a span inside the button, which is never pressed itself.
    pressed = {
        name
        for holder, name in re.findall(r"(\w+)\.className\s*=\s*\"([a-z-]+)\"", script)
        if re.search(re.escape(holder) + r'\.setAttribute\("aria-pressed"', script)
    }
    assert pressed, "no pressable control found in arrival.js — has the arrival moved?"
    for name in sorted(pressed):
        assert re.search(r"\." + re.escape(name) + r'\[aria-pressed="true"\]', sheet), (
            f".{name} is marked aria-pressed by arrival.js and styled by nothing in arrival.css"
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


#: The card's two columns (design.md §12, "The dark reading", 2026-10-06). A card is the
#: one surface that takes a theme, because it is drawn inside somebody else's page, and
#: its dark column is §4's "on ink" values and nothing invented. The edge on light is
#: ink at 8%, the desk's hairline, which is not a hex and so is not pinned here.
CARD_LIGHT = {
    "--card": "#fffdf9",
    "--ink": "#1c1a17",
    "--muted": "#6b645c",
    "--teal": "#1f6f6b",
    "--teal-ink": "#fffdf9",
    "--leaf": "#5a7340",
    "--track": "#ece7de",
}
CARD_DARK = {
    "--card": "#201e1b",
    "--ink": "#e6e1d8",
    "--muted": "#9a9288",
    "--edge": "#322e29",
    "--teal": "#6fb8b3",
    "--teal-ink": "#0f1a19",
    "--leaf": "#a8c37e",
    "--track": "#322e29",
}


def _block(css: str, selector: str) -> dict[str, str]:
    body = css[css.index(selector + " {") :]
    body = body[: body.index("}")]
    return dict(re.findall(r"(--[\w-]+):\s*([^;]+);", body))


def test_the_card_reads_the_palette_light_and_dark() -> None:
    """§12: a card follows the host's theme in a dark reading of the same palette. Each
    value is pinned, and every dark one is a colour §4 already gives a job on ink."""
    css = re.sub(r"/\*.*?\*/", " ", (ASSETS / "card.css").read_text(encoding="utf-8"), flags=re.S)
    light = _block(css, ":root")
    dark = _block(css, ':root[data-theme="dark"]')
    for token, value in CARD_LIGHT.items():
        assert light.get(token) == value, f"light {token} is {light.get(token)}, not {value}"
    for token, value in CARD_DARK.items():
        assert dark.get(token) == value, f"dark {token} is {dark.get(token)}, not {value}"
        assert value in PALETTE, f"dark {token} {value} is not in the palette"
    # The dark block swaps colours and nothing else: no size, face or corner of its own.
    assert set(dark) <= set(CARD_DARK) | {"--shadow"}, sorted(set(dark) - set(CARD_DARK))
    # And the card says the scheme it is in, so the browser draws no backdrop behind it.
    assert "color-scheme: dark" in css and "color-scheme: light" in css


def test_the_card_names_its_faces_and_carries_none() -> None:
    """§12: the chrome's sans, named and never fetched. No @font-face, no url()."""
    css = re.sub(r"/\*.*?\*/", " ", (ASSETS / "card.css").read_text(encoding="utf-8"), flags=re.S)
    assert "@font-face" not in css and "url(" not in css
    assert '"Source Sans 3"' in css


# -- the desk and the reader, apart (design.md §11 and §13, 2026-10-09) ----------------
#
# The design review of 2026-10-09 found most of the desk drawn in the platform's face:
# every desk page inlined the reader's whole sheet, `words.css` named system-ui on the
# body after `chrome.css` had named the chrome's face, and whichever came last won. A page
# passed every test above in the wrong face. These hold the cascade itself.


def _page_sheets(template: Path, seen: set[str] | None = None) -> list[str]:
    """Every stylesheet a page inlines, its partials' included, in order."""
    seen = set() if seen is None else seen
    if template.name in seen or not template.exists():
        return []
    seen.add(template.name)
    text = template.read_text(encoding="utf-8")
    sheets = re.findall(r"asset\('([\w-]+\.css)'\)", text)
    for partial in re.findall(r"""\{%-?\s*include\s+['"]([^'"]+)['"]""", text):
        sheets += _page_sheets(TEMPLATES / partial, seen)
    return sheets


#: §13: a desk page stands on the ground in the chrome's face — the app's pages, which
#: carry `chrome.css`, and the doors in front of it, which carry `signin.css`.
DESK_PAGES = [
    page
    for page in PAGES
    if not page.name.startswith("_") and {"chrome.css", "signin.css"} & set(_page_sheets(page))
]
DESK_SHEETS = sorted({sheet for page in DESK_PAGES for sheet in _page_sheets(page)})


def _declarations(css: str) -> list[tuple[str, str, str]]:
    """(selector, property, value) for every declaration, comments dropped."""
    css = re.sub(r"/\*.*?\*/", " ", css, flags=re.S)
    out = []
    for selector, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css):
        for prop, value in re.findall(r"([\w-]+)\s*:\s*([^;]+)", body):
            out.append((selector.strip(), prop.strip(), value.strip()))
    return out


def test_every_page_carries_the_tokens_and_no_desk_page_carries_the_reader() -> None:
    """§11: the tokens are `tokens.css`, which every page carries first; the reader's
    own rules are `reader.css`, and a desk page never carries them, so no rule of the
    reader's decides how the desk looks by where it sits in the cascade."""
    assert DESK_PAGES, "no desk page found"
    for page in DESK_PAGES:
        sheets = _page_sheets(page)
        assert "reader.css" not in sheets, f"{page.name} carries the reader's sheet"
        assert sheets[:2] == ["tokens.css", "shared.css"], f"{page.name}: {sheets[:3]}"
    for page in PAGES:
        sheets = _page_sheets(page)
        if "reader.css" in sheets:
            at = sheets.index("reader.css")
            assert sheets[at - 2 : at] == ["tokens.css", "shared.css"], page.name


def test_each_page_wears_one_body_class() -> None:
    """A body's classes were stacked history — `words you playlists` — and every one of
    them was a selector some sheet could still reach. One page, one name (2026-10-09)."""
    for page in DESK_PAGES:
        body = re.search(r'<body class="([^"{]*)', page.read_text(encoding="utf-8"))
        assert body is not None, f"{page.name} has no body class"
        assert len(body.group(1).split()) == 1, f"{page.name}: {body.group(1)!r}"


@pytest.mark.parametrize("sheet", DESK_SHEETS, ids=lambda name: name)
def test_the_desk_names_no_platform_face(sheet: str) -> None:
    """§13: the chrome speaks in Source Sans 3, with "Segoe UI", system-ui as the
    fallback inside `--chrome` and nowhere else. A desk rule names a face by its token
    (`--chrome`, `--ui`, `--reading`); one that names system-ui is the rule that put
    1,157 runs of See all in the platform's face."""
    css = (ASSETS / sheet).read_text(encoding="utf-8")
    for selector, prop, value in _declarations(css):
        if prop not in ("font-family", "font"):
            continue
        bare = re.sub(r"var\([^)]*\)", "var()", value)
        assert "system-ui" not in bare, f"{sheet}: {selector} names system-ui"


@pytest.mark.parametrize("sheet", DESK_SHEETS, ids=lambda name: name)
def test_no_press_on_the_desk_is_a_gradient(sheet: str) -> None:
    """§13: a button is filled, tonal or ghost, and each is a flat fill — the primary,
    its tint, or nothing — on surfaces that are flat too. The black sheen on the doors'
    one button was the last gradient on the desk (2026-10-09)."""
    css = (ASSETS / sheet).read_text(encoding="utf-8")
    for selector, prop, value in _declarations(css):
        if prop.startswith("background") and "gradient(" in value:
            raise AssertionError(f"{sheet}: {selector} draws {value}")


def test_a_press_in_the_primary_is_flat_everywhere() -> None:
    """§13 gives the filled button to the primary, and the reader's own chrome takes the
    desk's buttons (phase 5): so a press filled in teal is flat on the reader's page too —
    the end of a part, Next part under a picture."""
    for sheet in STYLESHEETS:
        for selector, prop, value in _declarations(sheet.read_text(encoding="utf-8")):
            if prop.startswith("background") and "var(--teal)" in value:
                assert "gradient(" not in value, f"{sheet.name}: {selector} draws {value}"


def test_modern_hebrew_stays_a_sans_where_the_boards_draw_a_serif() -> None:
    """design.md §12, "The boards are the desk" (2026-10-09): the boards win over this
    file everywhere but here. They set modern Hebrew in Frank Ruhl; David kept it in Noto
    Sans Hebrew ("The modern shelf reads in a sans", 2026-09-17), and the Tanakh keeps
    its accented face."""
    from targum.render.builder import BIBLICAL_FACE, MODERN_FACE

    assert MODERN_FACE[0] == "Noto Sans Hebrew"
    assert BIBLICAL_FACE[0] == "Taamey Frank CLM"


def test_the_boards_rulings_are_recorded_and_the_rules_they_retire_say_so() -> None:
    """The rulings are in §12 once, as the global rule, and each rule they overturn is
    marked where it stands, so nobody follows it back (design.md §12, 2026-10-09)."""
    text = DESIGN.read_text(encoding="utf-8")
    assert text.count("### The boards are the desk — 2026-10-09") == 1
    entry = text.split("### The boards are the desk — 2026-10-09", 1)[1].split("\n### ", 1)[0]
    for ruling in (
        "1248px",
        "34px",
        "Talk pill is ink",
        "tinted pills",
        "always shown",
        "No flags",
        "new system",
        "Noto Sans Hebrew",
        "Plain words",
        "Continue and Your targums",
        "bell and the foot stay",
        "one in-app page",
    ):
        assert ruling in entry, ruling
    # §13's own lines, each marked where it stands.
    desk = text.split("## 13 · The desk", 1)[1]
    for retired in (
        "A 62rem column *(superseded 2026-10-09",
        "Section titles 1.25rem/700 *(superseded 2026-10-09",
        "one pill in the primary *(in ink since 2026-10-09",
        "more than one language. *(Superseded 2026-10-09",
    ):
        assert retired in desk, retired


# -- one shell for every desk page (design.md §12, "The boards are the desk", 2026-10-09) --


def test_every_desk_page_stands_in_the_one_column() -> None:
    """The boards' 1248px at a 1440 window, one token for the bar's row, the title, the
    page and the foot. #680 drew it on Your Progress alone; a page-local copy, or the old
    62rem, is a page that has drifted out of the shell."""
    chrome = (ASSETS / "chrome.css").read_text(encoding="utf-8")
    chrome = re.sub(r"/\*.*?\*/", " ", chrome, flags=re.S)
    assert "--column: 73.75rem" in chrome
    for sheet in DESK_SHEETS:
        css = re.sub(r"/\*.*?\*/", " ", (ASSETS / sheet).read_text(encoding="utf-8"), flags=re.S)
        assert "62rem" not in css, f"{sheet} keeps the old column"
        assert "--progress-column" not in css, f"{sheet} keeps a page's own column"


def test_the_talk_pill_is_ink() -> None:
    """The boards draw Talk to targum as the call to action: paper on ink (§9), not the
    primary."""
    chrome = (ASSETS / "chrome.css").read_text(encoding="utf-8")
    said = [
        (prop, value)
        for selector, prop, value in _declarations(chrome)
        if selector == ".talk-cta" and prop in ("background", "color")
    ]
    assert dict(said)["background"] == "var(--ink)"
    assert dict(said)["color"] == "var(--page-max)"


def test_a_page_title_stands_on_the_desk_under_the_bar() -> None:
    """The title leaves the bar for the ground below it, in the reading serif at 34px and
    weight 500, on every desk page that has one."""
    nav = (TEMPLATES / "_nav.html.j2").read_text(encoding="utf-8")
    assert nav.index("</header>") < nav.index('class="page-title"')
    chrome = (ASSETS / "chrome.css").read_text(encoding="utf-8")
    title: dict[str, str] = {}
    for selector, prop, value in _declarations(chrome):
        if selector == ".page-title":
            title.setdefault(prop, value)  # the desk's own; a phone's comes later
    assert title["font-family"] == "var(--reading)"
    assert title["font-size"] == "1.9375rem" and title["font-weight"] == "500"


def test_the_language_menu_draws_no_flag() -> None:
    """No board draws a flag, and §1's "no flags" holds everywhere again."""
    for name in ("lang.js", "chrome.css"):
        text = (ASSETS / name).read_text(encoding="utf-8")
        code = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
        assert "lang-flag" not in code and "FLAGS" not in code, name


# -- the components (design.md §12, "The desk's controls are one layer", 2026-10-09) --------


def _rules(sheet: str) -> dict[str, dict[str, str]]:
    """selector -> its declarations, first rule of each selector winning, comments dropped."""
    found: dict[str, dict[str, str]] = {}
    for selector, prop, value in _declarations((ASSETS / sheet).read_text(encoding="utf-8")):
        found.setdefault(selector, {}).setdefault(prop, value)
    return found


def test_the_components_wear_the_boards_values() -> None:
    """One button, one row of tabs, one card, one field, one meter, one tag, one choice of
    a few and one section title, at the boards' values, each defined once."""
    shared = _rules("shared.css")
    chrome = _rules("chrome.css")

    button = shared[".btn"]
    assert button["border-radius"] == "999px" and button["font-weight"] == "600"
    assert button["min-block-size"] == "2.5rem"
    assert shared[".btn.filled"] == {"background": "var(--teal)", "color": "var(--teal-ink)"}
    assert shared[".btn.tonal"]["background"] == "var(--teal-wash)"
    assert shared[".btn.ghost"]["background"] == "transparent"
    assert shared[".btn.text"]["color"] == "var(--teal)"
    assert shared[".btn.danger"]["color"] == "var(--clay)"

    tab = chrome[".tab"]
    assert tab["border-radius"] == "999px" and tab["background"] == "var(--teal-wash)"
    chosen = (
        '.tab[aria-current="page"],\n.tab[aria-current="true"],\n'
        '.tab[aria-selected="true"],\n.tab[aria-pressed="true"]'
    )
    assert chrome[chosen]["background"] == "var(--teal)"
    assert chrome[chosen]["color"] == "var(--teal-ink)"

    card = chrome[".card,\n.panel"]
    assert card["background"] == "var(--card)"
    assert card["border-radius"] == "var(--radius-card)"
    assert card["box-shadow"] == "var(--shadow-rest)"
    assert card["border"] == "0"

    well = chrome[".field input,\n.field select,\n.field textarea,\n.well"]
    assert well["border-radius"] == "var(--radius-row)" and well["background"] == "var(--field)"
    focus = chrome[".field input:focus,\n.field select:focus,\n.field textarea:focus,\n.well:focus"]
    assert focus["border-color"] == "var(--teal)"

    assert chrome[".meter"]["block-size"] == "6px"
    assert chrome[".meter"]["background"] == "var(--rule)"
    assert chrome[".meter > span"]["background"] == "var(--leaf)"
    assert chrome[".tag"]["border"] == "1px solid var(--rule)"
    assert chrome[".tag"]["border-radius"] == "999px"

    title = chrome[".section-title"]
    assert title["font-family"] == "var(--reading)"
    assert title["font-size"] == "1.5rem" and title["font-weight"] == "500"

    seg = shared[".seg"]
    assert seg["border"] == "1px solid var(--rule)"
    assert seg["border-radius"] == "var(--radius-control)"
    live = shared[
        '.seg > .on,\n.seg > [aria-pressed="true"],\n.seg > [aria-checked="true"],\n'
        ".seg > [aria-current],\n.seg > .here"
    ]
    assert live["background"] == "var(--teal-wash)" and live["color"] == "var(--teal)"
    assert shared[".scrim"]["background"] == "var(--scrim)"


def _desk_sheets_but(owner: str) -> list[str]:
    return [sheet for sheet in DESK_SHEETS if sheet != owner]


@pytest.mark.parametrize(
    ("needle", "owner"),
    [(r"\.btn", "shared.css"), (r"\.tab", "chrome.css"), (r"\.seg", "shared.css")],
)
def test_a_component_is_drawn_in_one_sheet(needle: str, owner: str) -> None:
    """A page may place a component — its width, its margin — but its look (fill, colour,
    corners, border) is the component's own sheet's alone, so a second copy cannot drift
    (P2, 2026-10-09: there were five copies of the button and three of the tab)."""
    look = {"background", "background-color", "color", "border-radius", "border", "box-shadow"}
    alone = re.compile(needle + r"(?![\w-])")
    for sheet in _desk_sheets_but(owner):
        for selector, prop, _ in _declarations((ASSETS / sheet).read_text(encoding="utf-8")):
            if prop in look and any(alone.search(part.strip()) for part in selector.split(",")):
                # A component's look is its sheet's; a page may still say how a part of it
                # sits (`body.front .btn.cta` is the public pages' own call to action).
                if sheet == "front.css" and ".cta" in selector:
                    continue
                if sheet == "front.css" and ".tonal:hover" in selector:
                    continue
                raise AssertionError(f"{sheet}: {selector} draws {prop} of a component")


@pytest.mark.parametrize("sheet", DESK_SHEETS, ids=lambda name: name)
def test_no_tab_is_underlined(sheet: str) -> None:
    """Tabs are tinted pills (design.md §12, "The boards are the desk"). The Library's tabs
    were underlined, Your targums' strip copied them, and Your Words' meaning languages
    drew a third kind; a tab that wears a line under it is one of those come back."""
    tabbish = re.compile(r"\.(?:tab|tabs|[\w-]+-tabs?)(?![\w-])")
    for selector, prop, value in _declarations((ASSETS / sheet).read_text(encoding="utf-8")):
        if not tabbish.search(selector):
            continue
        underline = (
            prop in ("border-block-end", "border-bottom", "border-block-end-color")
            or (prop == "text-decoration" and "underline" in value)
            or (prop == "box-shadow" and "inset 0 -" in value)
        )
        assert not underline, f"{sheet}: {selector} underlines a tab ({prop}: {value})"


@pytest.mark.parametrize("sheet", STYLESHEETS, ids=lambda p: p.name)
def test_no_choice_of_a_few_is_filled_in_ink(sheet: Path) -> None:
    """A choice of a few marks its live part in the teal wash, the reader's and the desk's
    alike; the saved page's pair was the last one filled in ink."""
    for selector, prop, value in _declarations(sheet.read_text(encoding="utf-8")):
        if not re.search(r"seg(?:ment)?(?![\w-])", selector) or not prop.startswith("background"):
            continue
        assert value not in ("var(--ink)", "var(--ink-soft)"), f"{sheet.name}: {selector}"


@pytest.mark.parametrize("sheet", DESK_SHEETS, ids=lambda name: name)
def test_a_letter_tile_never_rests_on_beige(sheet: str) -> None:
    """A tile without a picture is its letter on the colour of its kind (thumbs.py
    `TONES`), never a beige box (P2, 2026-10-09; the boards' fallback tile)."""
    for selector, prop, value in _declarations((ASSETS / sheet).read_text(encoding="utf-8")):
        if "is-letter" in selector and prop.startswith("background"):
            assert value not in ("var(--paper-raised)", "var(--desk)", "var(--paper)"), (
                f"{sheet}: {selector} puts a letter on {value}"
            )


def test_every_tile_is_drawn_by_one_path() -> None:
    """`TargumCovers.picture()` draws every text's tile on the desk: home, the shelf, the
    Library, a playlist's mosaic and a subscription. A page that calls `tile()` with an
    address of its own is a second path, which is how the beige boxes survived."""
    for name in ("home.js", "shelf.js", "library.js", "playlists.js", "subs.js"):
        code = (ASSETS / name).read_text(encoding="utf-8")
        assert "TargumCovers.tile(" not in code and "covers.tile(" not in code, name
    covers = (ASSETS / "covers.js").read_text(encoding="utf-8")
    assert '"tone-" + tone(' in covers
