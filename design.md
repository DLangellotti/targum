# targum — design

**This file governs every visible surface.** It is not advisory and it is not a starting
point to riff on. Read it before changing anything visual.

It replaced `Design updated.pdf` on 2026-08-29 as the authority. The PDF is where all of
this came from and is still worth looking at for the drawings — the mark at four sizes, the
lockups, the type specimens — but where the two disagree, **this file wins**, and a change
made here is the change. The PDF cannot be edited by the people and processes that edit the
code, which is how it came to be out of date in three places while still being called
binding.

Section numbers are the PDF's, kept because the stylesheets cite them: `reader.css` says
"Functional colour (§4)" and "Gloss (§9) is light on glass" and those references should keep
resolving. §12 is new and records where the code knowingly departs.

`tests/test_brand.py` enforces the half a machine can check — palette, radii, type scale,
focus colour, no emoji, lowercase name, no exclamation marks, no gamification, motion always
optional. **When a brand test fails, the code is wrong, not the test.** Change the test only
when this file changes first.

---

## 1 · The idea

targum is a reading app for language learners: a text and its translation held in parallel,
sentence by sentence. The identity extends the reading surface rather than sitting on top of
it — **the brand is the page**.

The identity is matte; the UI may shine, measured. **The mark, lockup and wordmark are flat
forever** — no gradients, bevels or metallic ramps on them, ever. Interactive and celebratory
UI elements may carry the gloss recipe and hover lift in §9. Metallic gold ramps stay banned
everywhere.

**The reader is a reader, not a player.** Engagement is welcome, arcade is not. Streaks,
goals and milestones are a ledger: real counts in serif tabular numbers, leaf for
achievement, iris for novelty, celebration in type rather than motion. No mascots, no flags,
no emoji.

Positions deliberately avoided: heritage gold (the Orthodox-publisher shelf), Koren's
burgundy `#800020`, the language-app orange, and everyone's blue.

## 2 · The mark

Two staggered columns: the source begins, the translation follows one line later. **The ink
column is always the source; the accent column is always the translation.** Script-neutral by
construction — it carries Hebrew, Arabic, Cyrillic and Latin equally.

- Clear space: half the mark's height on all sides.
- Minimum size: 16 px on screen, 4 mm in print.
- Single-colour versions — all-ink on paper, all-paper on ink, all-accent — are all legal.
  The accent is optional in the mark; it is never the mark.
- Two-colour on brand surfaces; single-colour everywhere small or third-party.

## 3 · The lockup

- The wordmark is the reading face at weight 600, **always lowercase** — even at sentence
  start — with −0.01em tracking.
- Lockup minimum width 72 px / 18 mm; below 24 px the wordmark drops and the monogram
  stands alone.
- RTL: the mark mirrors legitimately. The stagger flips with the page — that is the mark
  reading right-to-left, not a mistake — and leads from the right. The Hebrew wordmark is
  תרגום, same face and weight.
- **The mark always leads the reading direction.**

## 4 · Colour

Warm paper, warm ink, one accent hue. The accent does not move between themes — **it
splits**: a deep cut works on paper, a pale cut works on ink. The pale cut appears on light
surfaces only as a 12–22% wash (kept words, highlights, row tints). What keeps this off the
ArtScroll shelf is not the hue but the finish: **always flat, never a ramp, never a large
field, never text below the ratios shown.**

| role | light surface | dark surface | use |
|---|---|---|---|
| page | `#fbf9f5` | `#171614` | surface |
| page · raised | `#f3efe7` | `#201e1b` | cards, hovers |
| rule | `#e2dcd1` | `#322e29` | hairlines only |
| ink | `#1c1a17` · 15.7:1 | `#e6e1d8` · 13.9:1 | reading text — AAA |
| muted | `#6b645c` · 5.5:1 | `#9a9288` · 5.9:1 | translation, chrome — AA |
| accent · working | `#7a5c38` · 5.8:1 | `#c8a778` · 8.0:1 | links, buttons, interactive |
| accent · wash | `#c8a778` at 12–22% | `#c8a778` at 12–22% | kept words, highlights; never text |

**One accent hue, and it is rationed.** Reserved for the single primary action in a view and
for what the reader has kept. Selection is quiet ink (`#6b645c` with paper text), never
accent. The accent is never body text and never a large field.

### Functional colour

The page stays calm; the moments get colour. Three brighter hues are allowed in UI features
— feedback, progress, badges, charts — **never in the identity**. One functional hue per
moment; flat always; text only at these working cuts; washes at 12–22%.

- **leaf** `#5a7340` (5.0:1) · dark `#a8c37e` (9.3:1) — progress, success, "known"
- **clay** `#b4553f` (4.6:1) · dark `#e0937d` (7.4:1) — cost, errors, destructive
- **iris** `#6b5a8e` (5.7:1) · dark `#b3a3d6` (7.9:1) — phrases, discovery, "new"

Green and purple are the two positions nobody in the category owns; blue and orange stay
out. The mark, lockup and wordmark remain ink + gold only.

Worth knowing while reading the code: clay sits close to the accent under protanopia, so an
error must never rest on colour alone — the wording carries it too, which §6 already
requires.

### Bright set — peak moments

Four vivid colours for highs and rare circumstances. They live on ink panels as fills, chips
and glyphs; on paper only as ≥3:1 graphics; text at these colours only on ink. Still one hue
per moment.

- **sun** `#e2a33c` (8.2:1 on ink) — streak milestones, the daily spark
- **leaf-bright** `#7ba646` — goal smashed, personal best
- **iris-bright** `#8e74c9` (4.7:1) — rare finds, a perfect week
- **rose** `#c2517a` (4.1:1, large glyphs only) — records, special events

Measured, `--sun` (2.09:1) and `--leaf-bright` (2.70:1) do not reach 3:1 on paper, so those
two are **ink-panel only**.

### Supporting

Focus ring `#b8935e`. The mark's translation column on paper is its own value, `#a5824f` —
the working accent goes muddy at 22 px wide. Deep paper is structural: desk `#ece7de`, rail
`#e7e1d6`, divider `#e6e1d8` — never a text background.

**The knowledge ramp climbs to leaf, not gold** — see §12.

## 5 · Type

Type is where targum's presence comes from. The wordmark face is the reading face — the brand
is the page.

- **Reading (Latin):** Iowan Old Style → Palatino Linotype → Palatino → Georgia → Times New
  Roman → serif.
- **Reading (Hebrew):** its own stack, not appended to the Latin one, and **carried in the
  page rather than named** — see §12.
- **UI:** `system-ui`. **Details:** `ui-monospace` for keys, hexes and counts (tabular
  numerals).
- **Scale:** display 1.75rem/600 · headings 1.5em/600 · reading 1.0625rem (17px) · gloss
  0.9375rem · UI 0.8125rem · labels 0.6875rem uppercase at 0.06em.
- **Landing display:** 2.75rem/600, 2.25rem under 40rem — the one headline of a public
  landing page, and nowhere inside the product. Line-height 1.1, `text-wrap: balance`.
  Added 2026-08-31; see §12.
- **Measure:** one reading column is 34rem; the source–translation gutter is 2.5rem.

**Bilingual parity:** Hebrew and Latin share every screen at the same font-size — **never
scale Hebrew down**. Parity comes from leading: **1.75 Latin, 1.95 Hebrew**.

## 6 · Voice

- Literary, precise, unpatronising — a designer-engineer explaining a decision, never
  marketing.
- Second person for the reader's actions ("Tap a word…"); plain honesty about limits
  ("roughly 90% right on modern Hebrew, less on classical. Guessed sentences are marked.").
- **The name is always lowercase: targum**, even at sentence start.
- No emoji, no exclamation marks, **no invented currency** — engagement counts real things
  ("12 days reading", "500 words known"), never XP, points or levels. Milestones brag the
  brand's way: "the page is 31% quieter than when you began." Missed streak days are quiet,
  never red.
- **And short.** Buttons and links are one or two words: "Send a link", not "Email me a
  link"; "Delete", not "Move to the trash". State what happened without justifying it,
  softening it, or answering the question nobody asked — see §12.

## 7 · Iconography

No icon font, no emoji, no icon library. Icons are tiny inline SVG strokes at text weight:
**16px viewBox, no fill, stroke `currentColor` at 1.4, round caps** — line diagrams of what
they do (the three reading-mode glyphs are literally the three layouts). Typed characters
elsewhere: ← → per reading direction, × to close and after a number as a multiplier
(1.25×), A− A+ ? as themselves.

## 8 · Surfaces, states, motion

- Resting surfaces are flat: raised paper, 1px rule border, radii 4–8px — exactly 4
  controls, 5 rows, 6 cards, 8 panels, 999 pills, never snapped. Shadows exist only on
  floating overlays (gloss card, menus, tips).
- Hover lifts muted to ink; row hovers are 7–10% accent washes. Selection is ink-soft with
  paper text. Focus is a 2px `#b8935e` ring.
- **Motion is rare and purposeful:** the mode pill slides 240ms on
  `cubic-bezier(0.32, 0.72, 0, 1)`; mode switches settle with a 200ms fade. Everything
  honours `prefers-reduced-motion`.
- **RTL is structural, not cosmetic:** logical CSS properties throughout, so every layout
  mirrors itself. Never `left`/`right`.

## 9 · Building screens

The palette is warm, but screens must not be a wash of brown on beige. **Contrast is the
engagement mechanism:** near-white pages, full-ink text, hue concentrated where the reader
acts.

- **Text is ink.** Anything the reader came for — body text, headings, numbers they earned —
  is full ink (15.7:1 light, 13.9:1 dark). Muted `#6b645c` is for genuinely secondary lines
  only (translations at rest, captions, metadata), never for primary content, and never
  below 13px on raised paper. Brown `#7a5c38` is a link-and-button colour, never a text
  colour for paragraphs.
- **The page is near-white, not beige.** Text sits on `#fbf9f5` / `#faf8f4` only. The deep
  paper tones are structural — desks, rails, dividers — never a text background.
- **One raised layer per view.** Raised paper `#f3efe7` marks one level of grouping; stacking
  beige on beige is exactly what makes a screen sleepy. If a card needs a card, use a
  hairline.
- **Ink inversion is the wake-up move.** One block per screen may invert to the dark surface
  (`#171614` with `#e6e1d8` text and pale-cut hues) — stats, a milestone, a hero moment. It
  is the highest contrast available; spent on one block it is striking, spent on three it is
  a dark theme.
- **Hue budget:** roughly 80% paper + ink, 15% structural neutrals, 5% hue — and the 5% goes
  where the reader acts or achieved something, never into decoration.
- **Interactive means visibly different.** Every tappable element carries ink or a hue:
  accent links and primary buttons, ink-bordered secondary buttons, leaf progress, iris
  novelty. **A beige button on a beige card is forbidden.**
- **Numbers at display sizes are ink or leaf.** Gold is the record colour inside charts, not
  a headline colour; gold display type on cream is the sleepy publisher look this brand
  exists to avoid.
- **Max-contrast pair.** Feature and engagement screens may step up from paper/ink to
  `#fffdf9` on `#121110` (18.6:1 measured) when the moment should feel switched on.
- **Gloss recipe.** Interactive and celebratory elements may carry a top-down white sheen:
  ≤14% (`--gloss`) on primary buttons and progress fills, ≤22% (`--gloss-strong`) on
  celebration chips, plus a soft hover lift (`--lift`: 0 2px 10px at 10%). Gloss is **light
  on glass, never metal**: one sheen per element, never on the mark or lockup, never a
  gold-to-gold ramp, never on a resting text surface.

## 10 · Never

- Metallic golds, bevels, emblems, or any gradient on the mark, lockup or wordmark —
  "printed sefer" is the wrong century and the wrong product. (UI gloss per §9 is the only
  permitted sheen.)
- Mascots, squircle app-mark clichés, flag imagery — texts, not countries.
- Burgundy `#800020` (Koren's), orange (the language-app default), blue (everyone's).
- Ritual objects of any tradition. A Hebrew letterform may be used as pure form, never as an
  identity signal.
- Scaling Hebrew below Latin; mirroring a letterform; the accent as body text or a large
  field.

## 11 · Files

The mark, lockup, favicons and app icons live in the design-system project, not this
repository: `assets/` holds `mark.svg` / `mark-dark.svg` / `mark-mono.svg`, `favicon.svg`
(auto light–dark) plus `favicon-16/32.png`, app-icon SVGs and full-bleed PNGs
(1024/512/192, apple-touch-180), `lockup.svg` / `lockup-dark.svg` / `lockup-rtl.svg`, and
mark-512 PNGs.

Lockup SVGs carry live text in the reading-face stack — outline before print use on systems
without Iowan Old Style or Palatino.

In *this* repository: tokens are the `:root` block of
`src/targum/render/assets/reader.css`, which every page carries; the Hebrew reading faces are
`src/targum/render/assets/fonts/`; the enforced rules are `tests/test_brand.py`.

## 12 · Where the code departs, and why

Four places. Each was a deliberate decision with a date, kept here so nobody "corrects" the
code back to a rule that was already retired.

### A landing page has a headline the reader never needs — 2026-08-31

§5's scale topped out at display 1.75rem, which is right for a page somebody reads and wrong
for the one page that has to be read from across a room. `/weekly` is a stranger's first
introduction to targum, and its headline was the size of a chapter title. The scale gains a
**landing display** step — 2.75rem, 2.25rem on a phone — for the single headline of a public
landing page. It does not appear inside the product, and `test_brand.py` allows it only
because this paragraph exists.

### The knowledge ramp climbs to leaf, not gold — 2026-08-28

§4 described four gold steps for the chart ramp (`#c8a778 → #ab8555 → #8b6840 → #6b4f2e`).
The code stopped painting them: gold on warm paper made every chart on the page read brown,
and §4 gives "known" to leaf by name. The ramp is now tints of `--leaf` mixed against
`--paper`, so one definition serves the light surface and the dark one and "known" is the
most present step on each.

**The structure §4 asks for is unchanged** — one hue, monotone, four steps, the end nearest
the surface clear of it, "known" carrying on both surfaces. Only the hue moved.

### The Hebrew reading face is carried, and there are two of it — 2026-08-29

§5 said the reading stack was Latin-first with `Taamey Frank CLM → Frank Ruhl CLM → SBL
Hebrew` appended, "so nikkud never falls to a platform default." That intent is right. The
mechanism was not, and it failed twice.

**First, appending was slow.** Every pointed Hebrew cluster walked four Latin faces before
reaching one that could carry it, and a base letter with its marks is one cluster to
resolve, not one character. Measured on the Declaration: 901ms to first frame against 5ms.
The reader was not slow; the page could not be laid out. Hebrew got its own stack.

**Second, naming a font is not having it.** None of Taamey Frank CLM, Frank Ruhl CLM or SBL
Hebrew ships with a stock operating system, so every reader fell through to New Peninim MT —
which cannot draw one of the 31 Hebrew accents, nor meteg, paseq, sof pasuq or qamats qatan.
That was invisible while the Tanakh arrived with its accents stripped out. The day it arrived
whole, every accented letter was borrowed from another font, and WebKit substitutes the whole
cluster, so the letter changed size too. A verse came out in two fonts at once.

So targum carries its own, one per register, embedded in the page:

- **Taamey Frank CLM** on the Tanakh — cut for pointed and accented scripture; its accents
  are designed rather than tolerated, and its letters hold one size. Taamey Ashkenaz, beside
  it in the same collection, does not: its shin, mem and final mem draw visibly larger than
  their neighbours, which on a page of verses reads as broken text rather than as a face. Koren Type is the face this shelf would want and it
  is © Koren Publishers Jerusalem, so it is not an option at any price; this is the nearest
  a licence allows.
- **Frank Ruhl Libre** everywhere else — a modern cut of the Hebrew book serif. A serif on
  purpose: these pages are parallel text, and a Hebrew sans beside a Latin serif reads as
  two documents rather than one.

**A font a page merely names is a font some readers do not have.** Each page inlines only
the face it needs — and which face it needs follows *the text*, not the shelf: a modern
essay that quotes one accented verse takes the biblical face, because the modern one has no
accents in it and a page must be able to draw its own text. `test_render.py` checks the
biblical face against the whole Masoretic repertoire and the modern one against everything
a modern text can hold.

**A third failure, from the fix itself.** `:lang(he)` matches an element's *inherited*
language, so `<html lang="he">` handed the Hebrew face to `<body>` and every wrapper below
it, outranking the `font-family` on `body` — and the English translation column inherited
it. Harmless for as long as the Hebrew stack could not draw Latin at all; the day the page
carried a Hebrew face with Latin glyphs of its own, every translation on the Tanakh shelf
was set in them. The rule matches `[lang|="he"]:not(html)` now: what declares itself
Hebrew, and not the page around it.

Two more consequences worth keeping: the faces are `font-display: block`, and `reader.js`
re-measures on `document.fonts.ready` — a page paginated in a fallback's metrics puts its
last verse outside the window. Taamey Frank CLM is GPL v2 with the font-embedding
exception and Frank Ruhl Libre is OFL, so a reader carrying either is not itself GPL. That
exception is per author rather than per project, and the Culmus collection is mixed — Taamey
David CLM sits beside the others without one — so `assets/fonts/README.md` says how to check
a candidate before shipping it.

**A fourth failure, and the one that reached a reader.** `targum serve` sends a
Content-Security-Policy of `default-src 'none'` with a `data:` exception for images only.
Fonts fall under the default, so the embedded face was refused by policy on every served
page: `document.fonts` reported it as an error and the text fell through the stack to a face
with no accents — the original bug, back. Every check had opened the file directly, where no
policy applies, so every check passed. The policy now names `font-src data:`,
`test_serve.py` pins it, and the lesson is recorded here: **a reader is checked the way a
reader is served.**

### The voice is terser than "reasons given" — 2026-08-24

§6 asks for complete sentences with "reasons given", which is what produced 131 words on a
sign-in page. David cut that by half and the terser reading wins. Reasons are still given
where a reader would otherwise be confused about a limit — that part of §6 stands — but not
as a default shape for every message.
