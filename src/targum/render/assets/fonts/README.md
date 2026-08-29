# The Hebrew faces targum carries

Two, one per shelf, because a page that only *asks* for a font is a page that gets
whatever the machine happens to have.

- **Taamey Frank CLM** — the Tanakh. Cut for pointed and accented scripture; its accents
  are designed rather than tolerated, and its letters hold one size. Koren Type is the face this shelf would want, and it
  is © Koren Publishers Jerusalem, so it is not an option at any price.
- **Frank Ruhl Libre** — everything else. A modern cut of the Hebrew book serif, and a
  serif on purpose: a Hebrew column and the Latin one beside it should read as one
  document, which is what §5 asks for.

Taamey Frank CLM is Yoram Gnat's, from the [Culmus](https://culmus.sourceforge.io/) project
— though not from the 0.133 tarball; see *Rebuilding them* below. Frank Ruhl Libre is from
[the Frank Ruhl Libre project](https://github.com/fontef/frankruhllibre) by way of Google
Fonts.

## Why they are in the repository at all

Until 2026-08-29 the stylesheet named `"Taamey Frank CLM", "Frank Ruhl CLM", "SBL Hebrew",
"New Peninim MT", David, serif` and got none of the first three: they do not ship with any
stock operating system. Every reader on a Mac therefore read in **New Peninim MT**, which
cannot draw a single one of the 31 Hebrew accents, nor meteg, paseq, sof pasuq or qamats
qatan — 39 characters of the block.

That was invisible while the Tanakh arrived with its accents stripped out. The moment it
arrived whole, every letter carrying one had to be borrowed from another font, and WebKit
substitutes the entire cluster — so the letter itself changed size. A verse came out in
two fonts at once.

A font a page merely names is a font some readers do not have. The only fix is to carry it,
which is also what `readers must fetch nothing` already requires of every other asset here.

`tests/test_render.py` checks that each face can draw the whole repertoire, so a face that
cannot never reaches a reader again.

## Three things that bit, and are now pinned

**The face must not leak into Latin.** `:lang(he)` matches an element's *inherited*
language, so on a reader whose `<html>` says `lang="he"` it also matched `<body>` and every
wrapper — and the English translation column inherited the Hebrew face, whose Latin glyphs
are not the reading face. `reader.css` matches `[lang|="he"]:not(html)` instead.

**The page must not be measured before the face arrives.** A page paginated in a
fallback's metrics puts its last verse outside the window. The faces are `font-display:
block`, and `reader.js` re-measures on `document.fonts.ready`.

**The server must let the face through.** `targum serve` sends `default-src 'none'`, which
covers fonts unless `font-src` names them. Without `font-src data:` the embedded face is
refused by policy — `document.fonts` reports `error` — and the page falls back exactly as
if the face were not there. Opening the file directly has no policy, so every headless
check passed while every served page was broken. Check a reader the way it is served.

## Licence

Two, one per face.

**Frank Ruhl Libre** — SIL Open Font License 1.1 (`LICENSE.frankruhllibre`), which permits
embedding outright and declares no Reserved Font Name, so the copy here may keep the name.
It is modified: the variable font instanced at weight 400, then converted to WOFF2.

**Taamey Frank CLM** — GPL v2, with the font-embedding exception it carries:

> As a special exception, if you create a document which uses this font, and embed this
> font or unaltered portions of this font into the document, this font does not by itself
> cause the resulting document to be covered by the GNU General Public License.

A built reader is exactly that document, so carrying the face does not put the reader
under the GPL. Culmus 0.133's own LICENSE predates this face and does not name it, so the
notice carried inside the font is the record: `LICENSE.taameyfrankclm`, extracted verbatim.

Taamey Frank CLM here is modified too: converted from TrueType to WOFF2, and nothing else — no
subsetting, no reshaping, no change to a glyph or a positioning rule. WOFF2 is a compressed
container, so the conversion is not bit-for-bit and the word "unaltered" above should not
be leaned on. As the licence permits a modifier to do, targum extends the same exception to
this converted copy: embedding it in a document does not place that document under the GPL.
It remains GPL v2 in its own right.

**The exception is per author, not per project, and the collection is mixed.** Yoram Gnat's
own faces — Taamey Frank CLM, Taamey Ashkenaz, Keter YG, Keter Aram Tsova, Shofar — carry
it. Maxim Iorsh's do not: Frank Ruehl CLM, David CLM, Nachlieli, Drugulin.

**Taamey David CLM is the trap.** It sits beside the others in the same Culmus folder and
looks like one of Gnat's, but its Hebrew glyphs are Iorsh's and it carries no exception —
so a page with it baked in is arguably a GPL v2 derivative, which a paid AGPL-3.0 product
cannot be. Read name ID 13 of any candidate before shipping it:

```
uv run --with fonttools python -c 'from fontTools.ttLib import TTFont
import sys; print(TTFont(sys.argv[1])["name"].getDebugName(13))' Candidate.ttf
```

## Rebuilding them

```
uv run --with 'fonttools[woff]' python -c 'from fontTools.ttLib import TTFont
f = TTFont("TaameyFrankCLM-Medium.ttf"); f.flavor = "woff2"
f.save("TaameyFrankCLM-Medium.woff2")'
```

Taamey Frank CLM is not in the Culmus 0.133 tarball; it comes from the
[aharonium/fonts](https://github.com/aharonium/fonts) collection, under
`Fonts/Hebrew Letters with Vowels and Cantillation/Culmus Project (GPL+FE)/Yoram Gnat (GPL+FE)/Taamey-Culmus/TaameyFrank/`.

Frank Ruhl Libre is a variable font, instanced at one weight before conversion:

```
curl -sSL -o FrankRuhlLibre.ttf \
  'https://raw.githubusercontent.com/google/fonts/main/ofl/frankruhllibre/FrankRuhlLibre%5Bwght%5D.ttf'
uv run --with 'fonttools[woff]' python -c 'from fontTools.ttLib import TTFont
from fontTools.varLib import instancer
f = instancer.instantiateVariableFont(TTFont("FrankRuhlLibre.ttf"), {"wght": 400})
f.flavor = "woff2"; f.save("FrankRuhlLibre-Regular.woff2")'
```
