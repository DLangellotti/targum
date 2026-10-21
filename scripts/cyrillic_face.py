"""Cut the chrome face's Cyrillic subset from Source Sans 3 (design.md §13, "Russian is
carried too", 2026-10-21; targum-internal#476, B1).

    .venv/bin/python scripts/cyrillic_face.py <folder with SourceSans3VF-Upright.ttf and
      SourceSans3VF-Italic.ttf, from Adobe's VF-source-sans-3.052R.zip>

Writes `src/targum/render/assets/fonts/SourceSans3-Cyrillic.woff2` (the upright, variable
200-900) and `SourceSans3-Cyrillic-Italic.woff2` (the italic, instanced at 400 as the
carried Latin italic is), each subset to the Cyrillic block with № and the non-breaking
hyphen, keeping the layout features the Latin cut keeps. Nothing here is fetched: the
release zip is downloaded by hand, from
https://github.com/adobe-fonts/source-sans/releases/tag/3.052R, and its sha256 checked
against the one in `fonts/README.md`.
"""

from __future__ import annotations

import sys
from pathlib import Path

from fontTools import subset
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

#: The Cyrillic block, the non-breaking hyphen and the numero sign.
UNICODES = "U+0400-04FF,U+2011,U+2116"
#: The layout features the Latin cut keeps (read off `SourceSans3.woff2`).
FEATURES = "ccmp,dnom,frac,liga,locl,numr,pnum,kern,mark,mkmk"
OUT = Path(__file__).resolve().parents[1] / "src" / "targum" / "render" / "assets" / "fonts"


def cut(font: TTFont, out: Path) -> None:
    options = subset.Options()
    options.unicodes = subset.parse_unicodes(UNICODES)
    options.layout_features = FEATURES.split(",")
    options.flavor = "woff2"
    options.name_IDs = ["*"]
    options.notdef_outline = True
    subsetter = subset.Subsetter(options)
    subsetter.populate(unicodes=options.unicodes)
    subsetter.subset(font)
    font.flavor = "woff2"
    font.save(out)
    print(f"{out.name}: {out.stat().st_size} bytes")


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print(__doc__)
        return 2
    folder = Path(argv[0])
    cut(TTFont(folder / "SourceSans3VF-Upright.ttf"), OUT / "SourceSans3-Cyrillic.woff2")
    italic = instancer.instantiateVariableFont(
        TTFont(folder / "SourceSans3VF-Italic.ttf"), {"wght": 400}
    )
    cut(italic, OUT / "SourceSans3-Cyrillic-Italic.woff2")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
