"""A scene's two spellings: full for the plain cell, standard ktiv menukad for the pointed
one (targum-internal#568).

Unpointed Hebrew is written in full spelling (חיבור, בוקר) and pointed Hebrew in
defective (חִבּוּר, בֹּקֶר). A scene used to hold one string per turn, pointed in full
spelling, and the plain cell was that string with its points stripped: right unpointed,
wrong pointed, which is ling-he's 1,151 words (#563). Now a turn keeps both. `text` stays
the full spelling everything is measured against, and `pointed` is the pointed cell.

A scene written before this has no `pointed`, and its line is derived from `text` by the
normaliser, so the 127 scenes on the shelf read correctly the day this ships without a
file being touched. The writer stores both from then on, so a hand correction to the
pointing has somewhere to live.

**The gate.** A pointed line with full spelling left under its points refuses
(`menukad.residue`), as does one whose words do not stand one for one with the plain
line's: the reader carries every tap, gloss and audio clock across word by word
(`vocalize.aligned_positions`, `alignMap` in reader.js), and a word too many would put
every tap after it on its neighbour.
"""

from __future__ import annotations

import unicodedata

from ..errors import TargumError
from ..models import SegmentedDocument, Vocalization
from ..vocalize import menukad
from ..vocalize.base import has_nikkud
from .checks import Finding
from .models import Dialogue, Turn

#: The name a scene's vocalization goes under: its pointing is the scene's own.
VOCALIZER = "scene/1"


def names(scene: Dialogue) -> list[str]:
    return [scene.cast.A.name, scene.cast.B.name]


def pointed_line(turn: Turn, cast: list[str]) -> str:
    """The turn's pointed cell: its own, or derived from its full spelling. "" where the
    turn carries no points at all, which leaves the line with nothing to toggle."""
    if turn.pointed:
        return turn.pointed
    if not has_nikkud(turn.text):
        return ""
    return menukad.normalise(turn.text, cast)[0]


def refusals(scene: Dialogue) -> list[str]:
    """What stops a scene's pointed lines from shipping, one line each, or nothing."""
    cast = names(scene)
    out: list[str] = []
    for n, turn in enumerate(scene.turns):
        line = pointed_line(turn, cast)
        if not line:
            continue
        if len(line.split()) != len(turn.text.split()):
            out.append(f"t{n}: the pointed line has a different number of words from the text")
        for rule, word in menukad.residue(line, cast, source=turn.text):
            if rule == "lost vav":
                out.append(f"t{n} «{word}»: a vav lost that no rule takes out")
            else:
                out.append(f"t{n} «{word}»: still in full spelling under its points ({rule})")
    return out


def repair(line: str, english: str, cast: list[str]) -> tuple[str, list[Finding]]:
    """A line's pointing put right without the writer, and what is still wrong with it.

    `pointing` and `homograph` findings are the diacritizer's, not the writer's: the
    writer writes unpointed Hebrew and never sees a point, so sending them back as a
    repair asks for something it cannot do (qa on #986). They come here instead: the
    normaliser, then each homograph the English decides turned to the word it asks for
    (צִיּוֹן to צִיּוּן beside "grade"), and Bit given its dagesh, then everything checked
    again. What is left goes to ling-he's read with the scene, never back to the writer.
    `speaker` and `addressee` findings are about the words, not the points, and are not
    looked at here.
    """
    from . import checks

    fixed = unicodedata.normalize("NFC", menukad.normalise(line, cast)[0])
    for found in list(checks.homographs(fixed, english, 0)):
        if found.fix:
            fixed = fixed.replace(found.word, _turned(found.word, found.fix), 1)
    for found in list(checks.bit_without_dagesh(fixed, 0)):
        fixed = fixed.replace(found.word, _bit(found.word), 1)
    left = [
        found
        for found in checks.check_turn(fixed, english, 0)
        if found.kind in checks.POINTING_KINDS
    ]
    return fixed, left


def _turned(word: str, meant: str) -> str:
    """`word` with its homograph replaced by `meant`, its prefixes and its first letter's
    dagesh (which a prefix gives or takes) kept as they were."""
    from .checks import DAGESH, units

    have, want = units(word), units(meant)
    cut = len(have) - len(want)
    head = "".join(letter + marks for letter, marks in have[:cut])
    first, marks = want[0]
    marks = marks.replace(DAGESH, "")
    if DAGESH in have[cut][1]:
        marks = DAGESH + marks
    rest = "".join(letter + marks for letter, marks in want[1:])
    return unicodedata.normalize("NFC", head + first + marks + rest)


def _bit(word: str) -> str:
    from .checks import DAGESH, bare, units

    seen = units(word)
    at = bare(word).rfind("ביט")
    return unicodedata.normalize(
        "NFC",
        "".join(
            letter + (DAGESH + marks if n == at and DAGESH not in marks else marks)
            for n, (letter, marks) in enumerate(seen)
        ),
    )


def vocalization(scene: Dialogue, segmented: SegmentedDocument) -> Vocalization:
    """The scene's pointed cells, by segment. A turn is never split, so a segment's block
    index is its turn's index. Raises where `refusals` finds anything."""
    found = refusals(scene)
    if found:
        raise TargumError(
            f"The pointing of {scene.id} is not ready to ship.",
            "; ".join(found[:5]) + (f"; and {len(found) - 5} more" if len(found) > 5 else ""),
        )
    cast = names(scene)
    pointed: dict[str, str] = {}
    for segment in segmented.segments:
        if segment.block_index >= len(scene.turns):
            continue
        line = pointed_line(scene.turns[segment.block_index], cast)
        if line:
            pointed[segment.id] = line
    return Vocalization(
        document_hash=segmented.document_hash,
        language=segmented.language,
        vocalizer=VOCALIZER,
        model=None,
        segments=pointed,
        machine=[],
        rejected=[],
    )
