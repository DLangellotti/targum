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

**A text that carries media opens as its media.** The player stands and is named; a
picture is on. Nothing plays until pressed, and the text is still the page. This replaced
"the reader is a reader, not a player" on 2026-09-03 — see §12. What that sentence also
meant still holds: engagement is welcome, arcade is not. Streaks,
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

Two registers, and which one applies depends on who is reading.

- **Inside the product:** literary, precise, unpatronising — a designer-engineer explaining
  a decision. Somebody who has already chosen targum is not sold to again.
- **On public pages — landing, pricing, the weekly's front — the copy sells.** A stranger
  owes targum nothing and will leave in seconds, so lead with what they get, name it in
  their words rather than ours, and ask for the sign-up plainly. Feature names that only
  make sense inside the team ("the shelf", "scenes", "the weekly") are the failure mode
  here, not enthusiasm.
- **Persuasion yes, inflation no.** No superlatives, no manufactured urgency, no claim the
  product cannot keep. The strongest line is usually the specific one: "an English
  translation beside every line" beats "the best way to read Hebrew."
- Second person for the reader's actions ("Tap a word…").
- An error says in words what went wrong; colour alone never carries it — see §4.
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
  ink-filled calls to action, accent links and working buttons, ink-bordered secondary
  buttons, leaf progress, iris novelty. **A beige button on a beige card is forbidden.**
- **Calls to action are ink.** The button that asks somebody to act — sign in, start
  reading, the door on a public page — is the max-contrast pair: ink-filled, paper text,
  weight 600; on an inverted block it flips to paper with ink text. The accent keeps the
  product's working actions (play, Save, Send it) and links, where its calm is the
  point — as a call to action on warm paper it whispered. Added 2026-08-31; see §12.
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
- Ritual objects **in the identity** — the mark, the lockup, the wordmark, the app icon,
  anything that stands for targum itself. A Hebrew letterform may be used as pure form
  there, never as an identity signal. Content surfaces are a different question and the
  answer changed on 2026-09-01: see §12.
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

Fifteen places. Each was a deliberate decision with a date, kept here so nobody "corrects"
the code back to a rule that was already retired.

### A video text opens as video, and the picture never floats — 2026-09-03

The section below reversed the default the same day: a text that carries media opens as
its media. It stopped one step short of the thing it had just argued for. The picture came
on, but it came on beside a page of text, in the band, at the size a panel is — which is
what a reader who has just been told *this is a video* does not see.

Two rules, decided together because they pull opposite ways and only settle as a pair.

- **A text carrying a video sidecar opens full-screen as video, its Hebrew and English
  overlaid as subtitles.** This is the mode a reader lands in. Leaving it for the reading
  page is one press and is remembered per text, the same way the panel's own closure
  already is. It is scoped to the sidecar and nothing else: a text with audio, a text with
  neither, and every page of the Tanakh open exactly as they did.

  This amends the last bullet of the section below — *the player and the picture stay
  occupants of the band* — for video only. The sentence was written when the picture was
  a panel and it is right about the panel; it is wrong about a reader who imported an
  hour of speech to watch it. The reading column keeps its measure in every mode the
  reader can be in with the text in front of them, which is what that sentence was
  protecting. It is not protecting a thumbnail.

- **The picture is never dragged.** It docks. Learn mode puts the video in one of four
  corners, the reader chooses which once and it is remembered, and the dock is a resident
  of the band in the sense "A word's card covers the page on a phone" gives that word: it
  takes its room out of the layout, and the reading is laid out around it.

  The note this came from asked for a draggable player, and the reason it asked is real —
  a picture parked over the sentence being read is the whole complaint. A drag solves that
  once, per session, per device, with a thumb, while reading. A corner solves it for good.
  The rule that a control fixed over a page of text takes its room out of the layout was
  settled five days earlier and it survives this: what changed is where the picture may
  stand, not whether the page is laid out around it.

Written from a note dated 2026-09-03. Built under targum-internal #182.

### A text that carries media opens as its media — 2026-09-03

§1 said *the reader is a reader, not a player*, and the 2026-08-31 departure below leaned on
it to keep the video panel shut until pressed. The sentence was written against the
language-app arcade, and for the reader the research corpus knew: the Biblical autodidact
who reads first and listens beside. Both halves were decided before anyone outside the
household had seen a page.

On 2026-09-03 the first stranger — an olah, a designer, the modern segment the corpus had
almost nothing on — was shown a scene that had a recording. She did not find out it could
be heard, and she said the thing the corpus could not: *I like to start with media and
learn from that; this is just a boring text.* That is not one person's taste. It is the
comprehensible-input method, and it is how the modern learner arrives. David withdrew the
sentence the same day.

What stands in its place:

- **A text with a recording opens with the player standing and named.** Not a button in
  the bar to be discovered, and not a strip that reads as chrome: the first thing a
  stranger can say about the page is that it can be heard.
- **A text with video opens with its picture on.** The toggle stays, so the picture can be
  put away; the default reverses. *Carried further 2026-09-03, see "A video text opens as
  video" above: the picture is not on beside the page, it is the page until the reader
  says otherwise.*
- **Nothing plays until pressed.** Autoplay is the arcade's move, and a reader on a train
  is still a reader.
- **A text with neither opens exactly as before.** The Tanakh page is untouched by this.
- **The text is still the page.** The media is how it opens, not what it is: the player
  and the picture stay occupants of the band, and the reading column keeps its measure.
  *Amended for video 2026-09-03, see "A video text opens as video" above: a text carrying
  a video sidecar opens full-screen with its text as subtitles, and the picture is an
  occupant of the band only in learn mode. Audio is untouched — the player is still an
  occupant, always.*

The other half of the withdrawn sentence — engagement yes, arcade no; streaks and goals as
a ledger in serif tabular numbers — is unchanged and `test_brand.py` still enforces it.
Recorded in the vault: *Targum user session 2026-09-03 — designer olah*. Built under
targum-internal #168.

### A word's card covers the page on a phone; it does not move it — 2026-09-03

The band at the foot of a narrow window was built on one rule: a control fixed over a
page of text takes its room out of the layout, never out of the reading. The sheet, the
keys, the menu and the video panel still do. A word's card and a phrase's chip no longer
do. They are drawn over the page, the strip, the arrows and the sheet, and the page is
not laid out again for them.

The rule was right for the things that stay and wrong for the thing that lasts a moment.
With the card in the band, every tap on a word cut the chapter into different pages
(measured: 60 pages became 80 with a card up and 60 again when it closed), so the words
in front of the reader changed twice for one look at one meaning, and the reader said so
(targum-internal#155): the screen must not move, and the words on it must not change
until they turn the page. A card over the last lines of a page is a card they can pull
down. A page that moves under their finger is not something they can do anything about.

### A daily page carries an artefact, not an invented face — 2026-09-01

The daily learning pages take the parasha's band: a seam down the middle, words on the
ink half, a picture on the other. What is in the picture is the decision.

Each cycle shows **something that exists** — the Kaufmann Mishnah, the Aleppo Codex, the
Leningrad Codex, and for Tehillim the sixth-century synagogue floor at Gaza with David and
his lyre on it. What is refused is not a face; it is an invented one.

The line runs between them like this. There is no likeness of Judah the Prince, and every
"portrait" of a sage of the Mishnah is a nineteenth-century artist's guess — printing one
as the hero of a page about his book is a fabrication presented as a fact, and the one
photograph of anything connected to him is CC BY-SA besides, which this shelf refuses
everywhere else and cannot start accepting for a decoration. The Gaza mosaic is the other
thing entirely: a floor a Jewish community laid in 508 and labelled דויד in tesserae, as
much an artefact of how the Psalms were read as a codex is. A picture may be of a thing
and must not be a claim about one. `COVER_RULES` says "no faces" about images a model is
asked to invent, which is the same rule from the other end.

The band was one column here for an afternoon, while the page had no picture, and half of
it was empty black with the headline wrapping inside a column measured for something
standing beside it — which is what a grid built for two things does when it is given one.
Recorded because the fix was to add the picture, not to change the grid.

`assets/manuscripts/README.md` carries the provenance and the licence of each.

### The library folds — 2026-09-01

§9 says one raised layer per view, and the library page's own rule is one row per text in
one list you can sort and sift. Both still hold. What changed is that one row per text
stopped being readable: the Mishneh Torah is thirteen rows of `הלכות …`, Berdichevsky is
thirty-nine stories, the hundred scenes are a hundred, and the Mishnah would be
sixty-three tractates. Three hundred and fifty-two rows is not a shelf somebody browses.

So several texts may now be one row that opens where it stands. It is not a second layer
and must not become one: the collection sits on the same seven-column grid as every other
row, its members line up with everything above them, and what marks them is a hairline
down their leading edge — §9's "if a card needs a card, use a hairline". The disclosure
takes the place of the cover rather than claiming a column of its own, because a column of
its own would push the whole list out of true.

The list stays one list, and the controls still act on all of it: a collection is built
out of the rows that survived the filters, so opening one never shows a text the reader
filtered away, and a search opens what it found rather than reporting one shut row.

### Which Hebrew is five answers, not two — 2026-09-01

The register filter offered Biblical and Modern for as long as the shelf was scripture and
journalism. It was lying to more than half of it. A hundred and fifty-nine entries filed
`modern` were written between 1853 and 1930 — Mapu, Mendele, Ahad Ha'am, Ben-Yehuda's own
journalism, Brenner, Gnessin, Berdichevsky — in a literary Hebrew built deliberately out of
the biblical and rabbinic layers, before anybody spoke the language. The measurement agrees
with the reader: Gnessin comes out at 26–31% hard words against 11–19 for the news filed
beside him.

Five now, and they read oldest to newest: Biblical, Rabbinic, Medieval, Revival, Modern.
Never sorted alphabetically — the field is a ramp a learner climbs, and Modern above
Rabbinic because M precedes R would throw that away. §5's switch was documented for "two
or three answers"; it wraps rather than scrolls, because a filter whose options you cannot
see is not a filter.

### A ritual object may stand on a content page — 2026-09-01

§10 banned ritual objects outright. That was written for the identity, where it still
holds without exception: nothing that stands for targum itself carries a scroll, a
menorah, a crown or a pointer, because the product is a reader for texts and not a badge
for one tradition, and a mark that says otherwise says it on every shelf including the
ones with no Hebrew on them.

A page about the week's Torah portion is not the identity. It is a content surface, about
one text, for somebody who came looking for that text — and refusing it a picture of the
thing it is about was the rule doing a job it was never written for. So on a content
surface a ritual object is allowed, under the conditions the rest of this document already
implies: it is imagery and never chrome, it never enters the mark or the lockup, it is
`aria-hidden` decoration rather than a control, it obeys §9's hue budget, and it never
arrives with the heritage-gold, metallic, bevelled finish §10's first line still bans —
that look is the wrong century whatever it is a picture of.

David's call, recorded here rather than argued in a code comment, and the reason the
paragraph above it now says "in the identity".

### Scripture has a third form of its text — 2026-09-01

A reader shows a sentence two ways: bare, or everything the edition wrote. Scripture now
shows a third — the vowels with the chanting marks taken off — and `/parasha` is why. The
te'amim are the whole point for somebody preparing to leyn and noise on top of the vowels
for somebody still learning to read, and those are the same page.

This is the second time it has been built. The first was a middle step in the vowel switch,
0 to 2, and it went inside a day: three positions on one control is a state to get lost in,
and the word arrows broke on the new form. Neither carries over. It is a **separate
two-position control** — the vowel switch still has its two — and it sits in the ⋯ menu,
where a setting made once by somebody who knows what it is belongs. The arrows work because
the reason they broke was fixed elsewhere in the meantime: `markMap` in `reader.js` derives
a cell's offsets from that cell's own characters, so a form nobody had thought of when it
was written maps like every other. Measured on Ruth: nineteen word spans in both forms,
each carrying its own marks inside its own span.

Every text without cantillation is untouched — two cells, one switch, no second button —
and `test_render.py` holds both halves of that.

**And the page's picture is a scroll.** `/parasha` opens on a band the width of the
window, split down the middle: the words on ink, a photograph of a Torah scroll's columns
beside them. The seam is upright rather than a scrim over the picture, because a headline
set over a photograph *of writing* is a fight whose only win is dimming the photograph
until it stops being one — turning the seam means no word is ever over the picture, so the
type keeps its contrast and the picture keeps its strength. On a phone the seam turns with
the layout and the picture takes the top.

Three things about it are worth writing down. It is §9's one inverted block, spent here.
Its colours are **constants, not tokens** — `#171614`, `#e6e1d8`, `#fffdf9`, `#c8a778`,
every one of them out of §4's table — because the max-contrast pair flips with the theme,
and flipping turns the band into a pale panel sitting on a dark page; held still, the band
is the dark surface in both themes, and in dark mode it merges with the ground so the
photograph is left floating. And the photograph is a stand-in: `assets/scroll/README.md`
says whose it is, that it is CC0, and that a commissioned one is what should ship.

### A reader that carries moving pictures — 2026-08-31

An imported video keeps its pictures, and three rules bend to carry them:

- **The reader folder gains a `video/` sidecar.** The one-file reader stays one file for
  text and sound; a part of video is ten times the whole page, so it is the single thing
  too heavy to inline. It stands beside the file with a relative address — a folder that
  travels to a disk keeps its picture, and the page still fetches nothing from any
  network. `test_render.py`'s no-network rules hold unchanged.
- **The video panel is off by default and toggled** — *superseded 2026-09-03, see "A text
  that carries media opens as its media" above: the picture now opens on.* As written on
  2026-08-31: §1's "a reader is a reader, not a player" stands: the transport is still the
  player strip, the picture is optional, and a reader who never presses the button reads
  exactly the page they had. On a narrow window the panel is an occupant of the band like
  the sheet, the keys and the menu, one at a time; the word cards are drawn over it (see
  "A word's card covers the page on a phone" above).
- **The serve policy's `media-src` gains `'self'`** — for exactly these sidecars, and
  nothing else. The embedded recordings stay `data:`; no address leaves the origin.
- **A video fetched from YouTube links home, at the line being read** (2026-09-02).
  The bar gains one link beside the video toggle — the only control in it that is a
  link — opening YouTube's own page at the second the sentence in front of the reader
  starts. It is drawn as its neighbours are and is second to the toggle: the sidecar
  plays on a plane and the link does not. It appears only where there is a home to go
  to; an uploaded file has none, and a dead "open the original" is a control that
  lies. `test_render.py` pins the address as the third outbound allowance, beside the
  conjugation tables and the licence, each with its reason written next to it.

### The weekly landing carries the press — 2026-08-31

The weekly landing page needed to read as news at a glance, and nothing in the identity
says news. Two things now do, and both bend rules written for targum's own paint:

- **Third-party press marks appear in their own colours.** The hero carries "From this
  week's reporting in" followed by the wordmarks of the outlets the issue actually cites
  — and ynet's is red, walla's is orange. §4 and §10 ban those hues for *targum's*
  identity and interface, and still do; an outlet's mark in an outlet's colour is that
  outlet speaking, not us. The marks are nominative attribution, sized to the text
  around them, only ever for outlets cited in the issue on the page. They live in
  `assets/press/` with their licences recorded beside them.
- **The hero's newspaper stack is imagery, and imagery may sit up.** Beside the pitch,
  a small stack of photographed Israeli front pages carries the §9 gloss recipe and the
  `--lift` shadow although it is not a floating overlay. §8's "shadows exist only on
  floating overlays" governs surfaces the interface rests things on; the stack is an
  illustration of an object that casts one. It is `aria-hidden`, square-cornered (a
  newspaper has no radius), printed as it was printed in both themes, and never
  carries controls. The photographs are not free files — a front page is a copyrighted
  work — and shipping them was David's decision, made knowingly on 2026-08-31;
  `assets/press/README.md` records which files and what to do if an outlet objects.

### Calls to action are ink, not accent — 2026-08-31

§9 used to give "accent links and primary buttons" one treatment. The accent's calm is
its whole point inside the product, and exactly wrong on the one button a stranger has
to notice: on warm paper, `#7a5c38` whispered. The palette already held the strongest
move it owns — §9's max-contrast pair — so a call to action takes it: ink-filled, paper
text, weight 600, paper-on-ink inside an inverted block. Working buttons inside the
product keep the accent; nothing else moved.

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
where a reader would otherwise be confused about a limit, but not as a default shape for
every message.
