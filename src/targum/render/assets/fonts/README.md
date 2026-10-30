# The Hebrew faces targum carries

Two, one per shelf, because a page that only *asks* for a font is a page that gets
whatever the machine happens to have.

- **Taamey Frank CLM** — the Tanakh. Cut for pointed and accented scripture; its accents
  are designed rather than tolerated, and its letters hold one size. Koren Type is the face this shelf would want, and it
  is © Koren Publishers Jerusalem, so it is not an option at any price.
- **Noto Sans Hebrew** — everything else, since 2026-09-17. Everyday Hebrew is sans: news
  sites, apps, signage, the ulpan handout. The modern shelf was Frank Ruhl Libre until
  then, a serif chosen so a Hebrew column and the Latin one beside it would read as one
  document; the first stranger to read a modern scene called it "too much like these hard
  to read Torah fonts they always use", and design.md §12 (2026-09-17) records the change
  and what it costs.
- **Frank Ruhl Libre** — carried no longer, but the licence note below is kept: it is the
  face to come back to if the sans does not hold up with the next Israeli readers.

Taamey Frank CLM is Yoram Gnat's, from the [Culmus](https://culmus.sourceforge.io/) project
— though not from the 0.133 tarball; see *Rebuilding them* below. Frank Ruhl Libre is from
[the Frank Ruhl Libre project](https://github.com/fontef/frankruhllibre) by way of Google
Fonts. Noto Sans Hebrew is from [the Noto project](https://github.com/notofonts/hebrew).

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
which is also what a reader that fetches nothing from any other site, and loads no files
at all off a disk or from a saved copy, already requires of every other asset here.

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

Three, one per face.

**Noto Sans Hebrew** — SIL Open Font License 1.1 (`LICENSE.notosanshebrew`), which permits
embedding outright. Copyright 2022 The Noto Project Authors.

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

### Source Sans 3's Cyrillic subset

The chrome's face carries a second cut on a page rendered in Russian (design.md §13,
"Russian is carried too", 2026-10-21; targum-internal#476): `SourceSans3-Cyrillic.woff2`
(upright, variable 200–900, 21.9 kB) and `SourceSans3-Cyrillic-Italic.woff2` (italic,
instanced at 400 as the carried Latin italic is, 11.3 kB), each subset to U+0400–04FF with
the non-breaking hyphen (U+2011) and № (U+2116), keeping the layout features the Latin cut
keeps. They are a second `@font-face` of the same family with that `unicode-range`, so the
Latin glyphs still come from the Latin file. Same licence as the Latin cut (SIL OFL 1.1,
Adobe's, Reserved Font Name "Source"; `LICENSE.sourcesans3`), from Adobe's 3.052 release:

In a scratch folder of its own, never the checkout (a downloaded archive is untrusted until
its sum is checked, and its files are not the repository's):

```
work="$(mktemp -d)"
curl -sSL -o "$work/VF-source-sans-3.052R.zip" \
  'https://github.com/adobe-fonts/source-sans/releases/download/3.052R/VF-source-sans-3.052R.zip'
shasum -a 256 "$work/VF-source-sans-3.052R.zip"
# d8e2ac355e06e6a0f0e0a0b1ac0c2451afa707584d7bb9d6b11ef9e4b749904c
unzip -q "$work/VF-source-sans-3.052R.zip" -d "$work"
.venv/bin/python scripts/cyrillic_face.py "$work/VF"
```

### Noto Sans Hebrew's letters at 600

Your Progress leads with the ulpan letter at the page title's step in 600 (design.md §12,
"Your level, v3", 2026-10-29; targum-internal#561), and the carried Regular is 400 only, so
a 600 asked of it is a bold the browser fakes. `NotoSansHebrew-Letters600.woff2` (2.8 kB)
is the variable font instanced at weight 600 and full width, subset to the 27 letters with
their finals (U+05D0–05EA), the geresh (U+05F3) and the plus. It is a second `@font-face`
of the same family at `font-weight: 600`, carried on Your Progress only, where nothing but
a letter, its geresh and its plus is ever set at that weight. Same licence as the Regular (SIL OFL 1.1, `LICENSE.notosanshebrew`),
version 3.001 from Google Fonts' repository:

In a scratch folder of its own, never the checkout:

```
work="$(mktemp -d)"
curl -sSL -o "$work/NotoSansHebrew-VF.ttf" \
  "https://github.com/google/fonts/raw/main/ofl/notosanshebrew/NotoSansHebrew%5Bwdth%2Cwght%5D.ttf"
shasum -a 256 "$work/NotoSansHebrew-VF.ttf"
# 7ef36a2c3593758cdb622e1bdef4f84523e92fbc3ccc667438dd80ff54c2de88
.venv/bin/python scripts/hebrew_letter_face.py "$work/NotoSansHebrew-VF.ttf"
```
