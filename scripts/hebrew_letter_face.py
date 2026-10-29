"""Cut the Hebrew letters at 600 from Noto Sans Hebrew, for the level letter (design.md
§12, "Your level, v3", 2026-10-29; targum-internal#561).

    .venv/bin/python scripts/hebrew_letter_face.py <NotoSansHebrew[wdth,wght].ttf>

Your Progress leads with the ulpan letter (ד׳) at the page title's step in 600, and the
page carries Noto Sans Hebrew at 400 only: asked for 600 the browser fakes a bold, which
smears at that size. This instances the variable font at weight 600 and full width and
subsets it to the 27 letters, the geresh and the plus, so `NotoSansHebrew-Letters600.woff2`
is a couple of kilobytes and a reader fetches nothing. Nothing here is fetched: the
variable font is downloaded by hand from Google Fonts' repository,
https://github.com/google/fonts/tree/main/ofl/notosanshebrew, and its sha256 checked
against the one in `fonts/README.md`. SIL OFL 1.1, as the Regular is.
"""

from __future__ import annotations

import sys
from pathlib import Path

from fontTools import subset
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

#: The letters with their final forms, the geresh and the plus a plus rung carries.
UNICODES = "U+05D0-05EA,U+05F3,U+002B"
OUT = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "targum"
    / "render"
    / "assets"
    / "fonts"
    / "NotoSansHebrew-Letters600.woff2"
)


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print(__doc__)
        return 2
    font = instancer.instantiateVariableFont(TTFont(argv[0]), {"wght": 600, "wdth": 100})
    options = subset.Options()
    options.unicodes = subset.parse_unicodes(UNICODES)
    options.layout_features = ["ccmp", "kern", "mark", "mkmk"]
    options.flavor = "woff2"
    options.name_IDs = ["*"]
    options.notdef_outline = True
    subsetter = subset.Subsetter(options)
    subsetter.populate(unicodes=options.unicodes)
    subsetter.subset(font)
    font.flavor = "woff2"
    font.save(OUT)
    print(f"{OUT.name}: {OUT.stat().st_size} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
